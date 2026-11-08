"""Exercise isolated, jobless Boot 4.1 outputs against independent repeat-runtime wire controls.

Run as ``python -m scripts.smoke.boot41_preview_proof`` from the Engine root.
The full mode requires a disposable PostgreSQL service and creates/drops only
uniquely named task databases on that service.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project
from appbuilder.target_profiles.catalog import TARGET_PROFILES
from scripts.smoke.generated_app_independence import verify_generated_app_independence

_FIXTURES = {
    "crud": "examples/input-projects/generated-app-ci-smoke/app-definition.yaml",
    "soap-in": "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml",
    "soap-out": "tests/fixtures/edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/app-definition.yaml",
    "passthrough": "examples/input-projects/country-router/app-definition.yaml",
}
_PROFILES = (
    ("h2-j17", "springboot-legacy-compatible", "springboot-legacy-compatible", "17", False),
    ("pg-j17", "springboot-enterprise-postgres-java17", "springboot-enterprise-postgres-java17", "17", True),
    ("pg-j21", "springboot-standard-enterprise", "springboot-standard-enterprise", "21", True),
)
_SOAP_NAMESPACE = "urn:edgeforge:examples:customer-soap:v1"
_SYNC_NAMESPACE = "urn:edgeforge:examples:customer-sync:v1"
_SOAP_ENVELOPE = "http://schemas.xmlsoap.org/soap/envelope/"
_EXPECTED_SECURITY = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "frame-ancestors 'none'",
}
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$")


def _source_digest(project: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(project.rglob("*")):
        if not path.is_file() or "target" in path.relative_to(project).parts:
            continue
        digest.update(path.relative_to(project).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 300) -> str:
    result = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode:
        detail = "\n".join((result.stdout + result.stderr).splitlines()[-70:])
        raise AssertionError(f"{' '.join(command[:3])} failed ({result.returncode}):\n{detail}")
    return result.stdout + result.stderr


def _jdk_env(java_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["JAVA_HOME"] = str(java_home)
    env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
    return env


def _verify_java_home(java_home: Path, expected: str) -> None:
    result = subprocess.run(
        [str(java_home / "bin/java"), "-version"], capture_output=True, text=True, timeout=15
    )
    if result.returncode or not re.search(rf'version "{expected}(?:\.|\")', result.stderr):
        raise ValueError(f"Java {expected} home is required for this proof")


class _Postgres:
    def __init__(self) -> None:
        self.host = os.environ.get("EDGEFORGE_BOOT41_PGHOST", "")
        self.port = os.environ.get("EDGEFORGE_BOOT41_PGPORT", "")
        self.user = os.environ.get("EDGEFORGE_BOOT41_PGUSER", "")
        self.password = os.environ.get("EDGEFORGE_BOOT41_PGPASSWORD", "")
        self.psql = os.environ.get("EDGEFORGE_BOOT41_PSQL") or shutil.which("psql")
        self.databases: list[str] = []
        if not all((self.host, self.port, self.user, self.password, self.psql)):
            raise ValueError("Full proof requires PostgreSQL host, port, user, nonblank synthetic password and psql")
        if self.host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Full proof only accepts a loopback disposable PostgreSQL service")
        self._psql("SELECT 1", database="postgres")

    def _psql(self, sql: str, *, database: str) -> str:
        env = os.environ.copy()
        env["PGPASSWORD"] = self.password
        return _run(
            [str(self.psql), "-X", "-At", "-v", "ON_ERROR_STOP=1", "-h", self.host,
             "-p", self.port, "-U", self.user, "-d", database, "-c", sql],
            cwd=Path.cwd(), env=env, timeout=20,
        ).strip()

    def create(self, label: str) -> str:
        safe = re.sub(r"[^a-z0-9]", "", label.lower())[:18]
        name = f"boot41_{safe}_{uuid.uuid4().hex[:8]}"
        self._psql(f"CREATE DATABASE {name}", database="postgres")
        self.databases.append(name)
        return name

    def jdbc(self, database: str) -> str:
        return f"jdbc:postgresql://{self.host}:{self.port}/{database}"

    def history(self, database: str) -> list[str]:
        rows = self._psql(
            "SELECT version FROM flyway_schema_history WHERE success ORDER BY installed_rank",
            database=database,
        )
        return rows.splitlines() if rows else []

    def no_batch_tables(self, database: str) -> bool:
        return self._psql(
            "SELECT count(*) FROM information_schema.tables WHERE table_name LIKE 'batch_%'",
            database=database,
        ) == "0"

    def close(self) -> None:
        errors = []
        for database in reversed(self.databases):
            try:
                self._psql(f"DROP DATABASE {database}", database="postgres")
            except Exception as exc:
                errors.append(f"{database}: {exc}")
        if errors:
            raise AssertionError("Task database cleanup failed: " + "; ".join(errors))


def _close_postgres(postgres: _Postgres | None) -> None:
    if postgres is None:
        return
    primary = sys.exc_info()[1]
    try:
        postgres.close()
    except Exception as cleanup_error:
        if primary is None:
            raise
        print(f"Cleanup error after original failure: {cleanup_error}", file=sys.stderr)


def _database_env(env: dict[str, str], postgres: _Postgres | None, database: str | None) -> dict[str, str]:
    result = env.copy()
    if postgres is not None and database is not None:
        result.update(
            SPRING_DATASOURCE_URL=postgres.jdbc(database),
            SPRING_DATASOURCE_USERNAME=postgres.user,
            SPRING_DATASOURCE_PASSWORD=postgres.password,
        )
    return result


def _build(
    *, kind: str, profile: str, java: str, postgres: _Postgres | None,
    java_homes: dict[str, Path], root: Path, maven_repo: Path | None,
    require_tests: bool,
) -> tuple[Path, dict[str, Any]]:
    fixture = _FIXTURES[kind]
    metadata = build_metadata_project(fixture)
    metadata.target_profile = profile
    project = root / f"{kind}-{profile}"
    report = generate_application(
        metadata, project, source_manifest=fixture, generation_run_id="boot41-proof"
    )
    if report.harness_report is not None and not report.harness_report.passed:
        raise AssertionError(f"Compatibility harness failed for {kind}/{profile}")
    if TARGET_PROFILES[profile].experimental_boot41:
        repeat = root / f"repeat-{kind}-{profile}"
        generate_application(
            metadata, repeat, source_manifest=fixture, generation_run_id="boot41-proof"
        )
        if _source_digest(project) != _source_digest(repeat):
            raise AssertionError(f"Nondeterministic preview output: {kind}/{profile}")
    source_digest = _source_digest(project)
    pom = (project / "pom.xml").read_text(encoding="utf-8")
    if TARGET_PROFILES[profile].experimental_boot41:
        if "<version>4.1.1</version>" not in pom or "spring-boot-starter-batch" in pom:
            raise AssertionError(f"Wrong Boot or Batch dependencies: {kind}/{profile}")
    verify_generated_app_independence(project, require_schema_baseline=kind != "passthrough")

    database = postgres.create(f"test{kind}{java}") if postgres and kind != "passthrough" else None
    env = _database_env(_jdk_env(java_homes[java]), postgres, database)
    command = ["mvn", "-B", "-ntp"]
    if maven_repo is not None:
        command.append(f"-Dmaven.repo.local={maven_repo}")
    command.extend(["clean", "verify"])
    _run(command, cwd=project, env=env)
    reports = list((project / "target/surefire-reports").glob("TEST-*.xml"))
    counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for path in reports:
        suite = ET.parse(path).getroot()
        for key in counts:
            counts[key] += int(suite.get(key, "0"))
    if require_tests and counts["tests"] < 1:
        raise AssertionError(f"No Maven tests executed for {kind}/{profile}")
    if counts["failures"] or counts["errors"] or counts["skipped"]:
        raise AssertionError(f"Maven tests failed or skipped for {kind}/{profile}: {counts}")
    if _source_digest(project) != source_digest:
        raise AssertionError(f"Maven changed generated source for {kind}/{profile}")
    verify_generated_app_independence(
        project, require_schema_baseline=kind != "passthrough", require_packaged_jar=True
    )
    jars = [p for p in (project / "target").glob("*.jar") if not p.name.endswith(".original")]
    if len(jars) != 1:
        raise AssertionError(f"Expected one packaged jar for {kind}/{profile}")
    if not TARGET_PROFILES[profile].emit_test_console:
        with ZipFile(jars[0]) as package:
            leaked = [
                name for name in package.namelist()
                if "static/index" in name or "DemoController" in name
            ]
        if leaked:
            raise AssertionError(f"Test console packaged for {kind}/{profile}: {leaked}")
    return jars[0], {
        "kind": kind, "profile": profile, "java": java,
        "database": "postgresql" if database else ("none" if kind == "passthrough" else "h2"),
        "maven_tests": counts["tests"], "source_and_jar_independent": True,
        "source_digest": source_digest,
        "jar_sha256": hashlib.sha256(jars[0].read_bytes()).hexdigest(),
        "dependency_identity": _dependency_identity(project, java_homes[java], maven_repo),
        "flyway_test_history": postgres.history(database) if database else None,
    }


def _dependency_identity(app: Path, java_home: Path, maven_repo: Path | None) -> dict:
    command = ["mvn", "-B", "-ntp"]
    if maven_repo:
        command.append(f"-Dmaven.repo.local={maven_repo}")
    _run(command + ["org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree",
                   "-DoutputType=json", "-DoutputFile=target/runtime-dependencies.json"],
         cwd=app, env=_jdk_env(java_home), timeout=180)
    tree = json.loads((app / "target/runtime-dependencies.json").read_text())
    canonical = json.dumps(tree, sort_keys=True, separators=(",", ":")).encode()
    jar = next(p for p in (app / "target").glob("*.jar") if not p.name.endswith(".original"))
    with ZipFile(jar) as archive:
        libraries = sorted(p.rsplit("/", 1)[-1] for p in archive.namelist()
                           if p.startswith("BOOT-INF/lib/") and p.endswith(".jar"))
    return {"resolved_tree": tree, "resolved_tree_sha256": hashlib.sha256(canonical).hexdigest(),
            "packaged_libraries": libraries}


def _unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def _application(
    jar: Path, *, java_home: Path, env: dict[str, str], root: Path,
    properties: dict[str, str] | None = None,
):
    port = _unused_port()
    log_path = root / f"runtime-{uuid.uuid4().hex}.log"
    args = [str(java_home / "bin/java"), "-jar", str(jar), f"--server.port={port}",
            "--server.address=127.0.0.1"]
    args.extend(f"--{key}={value}" for key, value in (properties or {}).items())
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            args, cwd=jar.parent.parent, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError("Generated runtime exited: " + "\n".join(log_path.read_text().splitlines()[-45:]))
                try:
                    status, _headers, _body = _http(port, "GET", "/actuator/health")
                    if status == 200:
                        break
                except URLError:
                    pass
                time.sleep(0.25)
            else:
                raise AssertionError("Generated runtime did not become healthy: " + "\n".join(log_path.read_text().splitlines()[-45:]))
            yield port, log_path
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _http(
    port: int, method: str, path: str, body: bytes | None = None,
    content_type: str | None = None, headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    request_headers = dict(headers or {})
    if content_type:
        request_headers["Content-Type"] = content_type
    request = Request(
        f"http://127.0.0.1:{port}{path}", data=body, headers=request_headers, method=method
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, _response_headers(response.headers), response.read()
    except HTTPError as error:
        return error.code, _response_headers(error.headers), error.read()


def _response_headers(headers: Any) -> dict[str, str]:
    for key, expected in _EXPECTED_SECURITY.items():
        if headers.get_all(key) != [expected]:
            raise AssertionError(f"Missing or duplicate security header {key}: {headers.get_all(key)}")
    if headers.get_all("strict-transport-security"):
        raise AssertionError("Plain-HTTP runtime unexpectedly emitted HSTS")
    return {key.lower(): value for key, value in headers.items()}


def _json(port: int, method: str, path: str, payload: dict[str, Any] | None = None):
    return _http(
        port, method, path,
        json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None,
        "application/json" if payload is not None else None,
    )


def _json_value(body: bytes) -> Any:
    return json.loads(body.decode("utf-8"))


def _created_id(response: tuple[int, dict[str, str], bytes], field: str) -> str:
    payload = _json_value(response[2])
    value = payload.get(field) if isinstance(payload, dict) else None
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", value
    ) or uuid.UUID(value).version != 4:
        raise AssertionError(f"{field} must be a canonical UUIDv4 string")
    return value


def _require_resource_id(body: bytes, field: str, expected: str, *, listed: bool = False) -> None:
    payload = _json_value(body)
    if listed:
        def collect(value: Any) -> list[Any]:
            if isinstance(value, dict):
                return ([value[field]] if field in value else []) + [
                    item for child in value.values() for item in collect(child)
                ]
            if isinstance(value, list):
                return [item for child in value for item in collect(child)]
            return []

        ids = collect(payload)
        if ids != [expected]:
            raise AssertionError(f"List must contain exactly the created {field}")
    elif not isinstance(payload, dict) or type(payload.get(field)) is not str or payload[field] != expected:
        raise AssertionError(f"Read must return the created {field}")


def _normalize_json(
    value: Any, *, generated_id: str | None = None, id_field: str | None = None,
    error_timestamp: bool = False,
) -> Any:
    if isinstance(value, dict):
        normalized = {}
        for key, item in sorted(value.items()):
            if key == id_field and type(item) is str and item == generated_id:
                normalized[key] = "<generated-id>"
            elif key == "timestamp" and error_timestamp:
                if not isinstance(item, str) or not _UTC_TIMESTAMP.fullmatch(item):
                    raise AssertionError("Error timestamp must be an ISO-8601 UTC string")
                datetime.fromisoformat(item.replace("Z", "+00:00"))
                normalized[key] = "<request-timestamp:iso-utc>"
            else:
                normalized[key] = _normalize_json(item, generated_id=generated_id, id_field=id_field)
        return normalized
    if isinstance(value, list):
        return [_normalize_json(item, generated_id=generated_id, id_field=id_field) for item in value]
    return (type(value).__name__, value)


def _parse_xml(body: bytes, *, generated_id: str | None = None) -> tuple[Any, ...]:
    pending: list[tuple[str, str]] = []
    stack: list[dict[str, str]] = []
    namespaces: dict[int, dict[str, str]] = {}
    parser = ET.iterparse(io.BytesIO(body), events=("start-ns", "start", "end"))
    for event, item in parser:
        if event == "start-ns":
            pending.append(item)
        elif event == "start":
            scope = stack[-1].copy() if stack else {}
            scope.update(pending)
            pending.clear()
            stack.append(scope)
            namespaces[id(item)] = scope
        else:
            stack.pop()
    return _xml_value(parser.root, generated_id=generated_id, namespaces=namespaces)


def _require_xml_resource_id(body: bytes, field: str, expected: str) -> None:
    root = ET.fromstring(body)
    values = [
        item.text for item in root.iter()
        if item.tag.rsplit("}", 1)[-1] == field
    ]
    if values != [expected]:
        raise AssertionError(f"SOAP message must contain exactly the created {field}")


def _xml_value(
    element: ET.Element, *, generated_id: str | None = None,
    namespaces: dict[int, dict[str, str]] | None = None, tail: str = "",
) -> tuple[Any, ...]:
    children = list(element)
    mixed = bool((element.text or "").strip() or any((child.tail or "").strip() for child in children))
    value = element.text or ""
    if children and not mixed:
        value = ""
    if generated_id is not None and element.tag.rsplit("}", 1)[-1] == "customerId" and value == generated_id:
        value = "<generated-id>"
    if element.tag.rsplit("}", 1)[-1] == "faultcode" and value:
        match = re.fullmatch(r"([A-Za-z_][\w.-]*):([A-Za-z_][\w.-]*)", value)
        scope = (namespaces or {}).get(id(element), {})
        if not match or match.group(1) not in scope:
            raise AssertionError("SOAP fault code must resolve to a declared namespace")
        value = ("qname", scope[match.group(1)], match.group(2))
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        value,
        tuple(
            _xml_value(
                child, generated_id=generated_id, namespaces=namespaces,
                tail=(child.tail or "") if mixed else "",
            )
            for child in children
        ),
        tail,
    )


def _content_type(value: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    header = Message()
    header["content-type"] = value
    parts = header.get_params(header="content-type") or []
    if not parts:
        raise AssertionError("Invalid Content-Type")
    return parts[0][0].lower(), tuple(sorted(
        (key.lower(), item.lower() if key.lower() == "charset" else item)
        for key, item in parts[1:]
    ))


def _capture(
    response: tuple[int, dict[str, str], bytes], *, xml: bool = False,
    generated_id: str | None = None, id_field: str | None = None,
    error_timestamp: bool = False,
) -> tuple[Any, ...]:
    status, headers, body = response
    for key, expected in _EXPECTED_SECURITY.items():
        if headers.get(key) != expected:
            raise AssertionError(f"Missing or duplicate security header {key}: {headers.get(key)}")
    selected = {
        key: _content_type(value) if key == "content-type" else value
        for key, value in headers.items()
        if key in {*_EXPECTED_SECURITY, "content-type", "location"}
    }
    if xml:
        payload = _parse_xml(body, generated_id=generated_id) if body else None
    elif body and "json" in headers.get("content-type", ""):
        payload = _normalize_json(
            _json_value(body), generated_id=generated_id, id_field=id_field,
            error_timestamp=error_timestamp and status >= 400,
        )
    else:
        payload = body
    return status, selected, payload


@contextmanager
def _synthetic_downstream(*, soap: bool = False):
    received: list[tuple[str | None, str | None, bytes]] = []
    response_suffix = [b""]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - standard-library handler API
            if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                chunks = []
                while True:
                    size = int(self.rfile.readline().split(b";", 1)[0], 16)
                    if not size:
                        self.rfile.readline()
                        break
                    chunks.append(self.rfile.read(size))
                    self.rfile.read(2)
                data = b"".join(chunks)
            else:
                data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            received.append((self.headers.get("SOAPAction"), self.headers.get("Content-Type"), data))
            if soap:
                response = (
                    f'<soap:Envelope xmlns:soap="{_SOAP_ENVELOPE}"><soap:Body>'
                    f'<tns:SyncCustomerResponse xmlns:tns="{_SYNC_NAMESPACE}">'
                    '<tns:resultCode>ACCEPTED</tns:resultCode><tns:message>queued</tns:message>'
                    '</tns:SyncCustomerResponse></soap:Body></soap:Envelope>'
                ).encode()
                content_type = "text/xml; charset=utf-8"
            else:
                response = b'{"status":"ACCEPTED"}' + response_suffix[0]
                content_type = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], received, response_suffix
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _crud_wire(port: int) -> list[tuple[Any, ...]]:
    created = _json(port, "POST", "/api/v1/records", {"label": "Preview record", "state": "NEW"})
    if created[0] != 201:
        raise AssertionError(f"CRUD create failed: {created[0]} {created[2][:250]!r}")
    record_id = _created_id(created, "recordId")
    read = _json(port, "GET", f"/api/v1/records/{record_id}")
    listed = _json(port, "GET", "/api/v1/records")
    invalid = _json(port, "POST", "/api/v1/records", {})
    if (read[0], listed[0], invalid[0]) != (200, 200, 400):
        raise AssertionError("CRUD read/list/validation contract changed")
    _require_resource_id(read[2], "recordId", record_id)
    _require_resource_id(listed[2], "recordId", record_id, listed=True)
    return [
        _capture(item, generated_id=record_id, id_field="recordId")
        for item in (created, read, listed)
    ] + [_capture(invalid, error_timestamp=True)]


def _soap_in_wire(port: int) -> list[tuple[Any, ...]]:
    created = _json(port, "POST", "/customers", {"customerName": "Ada Lovelace", "status": "ACTIVE"})
    if created[0] != 201:
        raise AssertionError(f"SOAP fixture REST create failed: {created[0]} {created[2][:250]!r}")
    customer_id = _created_id(created, "customerId")
    read = _json(port, "GET", f"/customers/{customer_id}")
    envelope = (
        f'<soap:Envelope xmlns:soap="{_SOAP_ENVELOPE}"><soap:Body>'
        f'<tns:GetCustomerRequest xmlns:tns="{_SOAP_NAMESPACE}">'
        f'<tns:customerId>{customer_id}</tns:customerId>'
        '</tns:GetCustomerRequest></soap:Body></soap:Envelope>'
    ).encode()
    soap = _http(port, "POST", "/ws", envelope, "text/xml; charset=utf-8", {"SOAPAction": "urn:getCustomer"})
    missing_envelope = envelope.replace(customer_id.encode(), b"missing-customer")
    fault = _http(port, "POST", "/ws", missing_envelope, "text/xml; charset=utf-8", {"SOAPAction": "urn:getCustomer"})
    if read[0] != 200 or soap[0] != 200 or fault[0] < 400:
        raise AssertionError(f"SOAP inbound contract changed: {[read[0],soap[0],fault[0]]}")
    _require_resource_id(read[2], "customerId", customer_id)
    _require_xml_resource_id(soap[2], "customerId", customer_id)
    return [
        _capture(created, generated_id=customer_id, id_field="customerId"),
        _capture(read, generated_id=customer_id, id_field="customerId"),
        _capture(soap, xml=True, generated_id=customer_id), _capture(fault, xml=True),
    ]


def _passthrough_wire(
    port: int, received: list[tuple[str | None, str | None, bytes]]
) -> list[tuple[Any, ...]]:
    request = {
        "amount": 42.5, "currency": "USD", "countryCode": "US",
        "senderName": "Ada", "recipientName": "Grace",
    }
    accepted = _json(port, "POST", "/payments", request)
    invalid = _json(port, "POST", "/payments", {"currency": "USD"})
    if accepted[0] != 200 or invalid[0] != 400 or len(received) != 1:
        raise AssertionError(f"Passthrough route/validation changed: {accepted[0]}, {invalid[0]}, {len(received)}")
    outbound = _normalize_json(_json_value(received[0][2]))
    return [
        _capture(accepted), _capture(invalid, error_timestamp=True),
        ("downstream-content-type", _content_type(received[0][1] or "")),
        ("downstream", outbound),
    ]


def _soap_out_wire(
    port: int, received: list[tuple[str | None, str | None, bytes]]
) -> list[tuple[Any, ...]]:
    created = _json(port, "POST", "/customers", {"customerName": "Ada Lovelace", "status": "ACTIVE"})
    if created[0] != 201:
        raise AssertionError(f"Outbound fixture REST create failed: {created[0]} {created[2][:250]!r}")
    customer_id = _created_id(created, "customerId")
    invoked = _json(port, "POST", "/soap/outbound/customer-sync-client/syncCustomer", {"id": customer_id})
    if invoked[0] != 200 or len(received) != 1:
        raise AssertionError(f"Outbound SOAP call failed: {invoked[0]} {invoked[2][:250]!r}")
    _require_resource_id(invoked[2], "id", customer_id)
    action, content_type, outbound = received[0]
    if action not in {'"urn:syncCustomer"', "urn:syncCustomer"}:
        raise AssertionError(f"Outbound SOAPAction changed: {action}")
    _require_xml_resource_id(outbound, "customerId", customer_id)
    outbound_xml = _parse_xml(outbound, generated_id=customer_id)
    return [
        _capture(created, generated_id=customer_id, id_field="customerId"),
        _capture(invoked, generated_id=customer_id, id_field="id"),
        ("soap-action", action.strip('"')),
        ("outbound-content-type", _content_type(content_type or "")),
        ("outbound", outbound_xml),
    ]


def _trailing_json_probe(port: int, kind: str) -> int:
    if kind == "crud":
        path, payload = "/api/v1/records", {"label": "Policy probe", "state": "NEW"}
    elif kind in {"soap-in", "soap-out"}:
        path, payload = "/customers", {"customerName": "Policy probe", "status": "ACTIVE"}
    else:
        path, payload = "/payments", {
            "amount": 1, "currency": "USD", "countryCode": "US",
            "senderName": "Ada", "recipientName": "Grace",
        }
    body = json.dumps(payload, separators=(",", ":")).encode() + b" {}"
    return _http(port, "POST", path, body, "application/json")[0]


def _exercise(
    *, kind: str, jar: Path, java_home: Path, postgres: _Postgres | None,
    root: Path,
) -> tuple[list[tuple[Any, ...]], dict[str, Any]]:
    database = postgres.create(f"runtime{kind}{java_home.name}") if postgres and kind != "passthrough" else None
    env = _database_env(_jdk_env(java_home), postgres, database)
    with _synthetic_downstream(soap=kind == "soap-out") as (
        downstream_port, received, response_suffix
    ):
        properties: dict[str, str] = {}
        if kind == "passthrough":
            properties = {
                f"downstream.app-{letter}.base-url": f"http://127.0.0.1:{downstream_port}"
                for letter in "abc"
            }
        if kind == "soap-out":
            properties["app.soap.clients.customer-sync-client.uri"] = f"http://127.0.0.1:{downstream_port}/soap"
        with _application(jar, java_home=java_home, env=env, root=root, properties=properties) as (port, log):
            if kind == "crud":
                observations = _crud_wire(port)
            elif kind == "soap-in":
                observations = _soap_in_wire(port)
            elif kind == "soap-out":
                observations = _soap_out_wire(port, received)
            else:
                observations = _passthrough_wire(port, received)
            trailing_status = _trailing_json_probe(port, kind)
            downstream_trailing_status = None
            if kind == "passthrough":
                response_suffix[0] = b" {}"
                downstream_trailing_status = _json(port, "POST", "/payments", {
                    "amount": 1, "currency": "USD", "countryCode": "US",
                    "senderName": "Ada", "recipientName": "Grace",
                })[0]
                response_suffix[0] = b""
            console = _http(port, "GET", "/api/demo/entities")
            if postgres and console[0] != 404:
                raise AssertionError(f"Enterprise test console unexpectedly exposed for {kind}: {console[0]}")
            observations.append(("test-console", console[0]))
            if kind != "passthrough":
                text = log.read_text(encoding="utf-8")
                if (
                    "Initialized JPA EntityManagerFactory" not in text
                    or "Successfully applied" not in text
                ):
                    raise AssertionError(f"Missing Hibernate/Flyway runtime startup evidence for {kind}")
    history = postgres.history(database) if postgres and database else None
    if database and (not history or not postgres.no_batch_tables(database)):
        raise AssertionError(f"Missing Flyway history or unexpected Batch tables for {kind}")
    return observations, {
        "kind": kind, "database": "postgresql" if database else "h2/none",
        "flyway_history": history, "trailing_json_status": trailing_status,
        "downstream_trailing_json_status": downstream_trailing_status,
    }


def _proof(args: argparse.Namespace) -> dict[str, Any]:
    java_homes = {"17": Path(args.java17_home).resolve()}
    _verify_java_home(java_homes["17"], "17")
    postgres = None
    if args.mode == "full":
        if not args.java21_home:
            raise ValueError("Full proof requires --java21-home")
        java_homes["21"] = Path(args.java21_home).resolve()
        _verify_java_home(java_homes["21"], "21")
        postgres = _Postgres()
    summary: dict[str, Any] = {"mode": args.mode, "boot41": "4.1.1", "builds": [], "runtimes": [], "wire_comparisons": []}
    try:
        work_dir = getattr(args, "work_dir", None)
        if work_dir:
            work_dir.mkdir(parents=True, exist_ok=False)
        context = nullcontext(str(work_dir)) if work_dir else tempfile.TemporaryDirectory(prefix="edgeforge-boot41-proof-")
        with context as temporary:
            root = Path(temporary)
            packages: dict[tuple[str, str], Path] = {}
            selected = _PROFILES if args.mode == "full" else _PROFILES[:1]
            for label, _base, preview, java, needs_pg in selected:
                for kind in _FIXTURES:
                    pg = postgres if needs_pg and kind != "passthrough" else None
                    jar, result = _build(
                        kind=kind, profile=_base, java=java, postgres=pg,
                        java_homes=java_homes, root=root, maven_repo=args.maven_repo,
                        require_tests=True,
                    )
                    packages[(kind, label)] = jar
                    summary["builds"].append(result)
                    print(f"preview build verified: {kind}/{label} ({result['maven_tests']} tests)", file=sys.stderr)
            for kind in _FIXTURES:
                jar, result = _build(
                    kind=kind, profile=_PROFILES[0][2], java="17", postgres=None,
                    java_homes=java_homes, root=root / "repeat-control", maven_repo=args.maven_repo,
                    require_tests=kind != "passthrough",
                )
                packages[(kind, "repeat-control")] = jar
                summary["builds"].append(result)
            for kind in _FIXTURES:
                control, control_info = _exercise(
                    kind=kind, jar=packages[(kind, "repeat-control")],
                    java_home=java_homes["17"], postgres=None, root=root,
                )
                preview, preview_info = _exercise(
                    kind=kind, jar=packages[(kind, "h2-j17")],
                    java_home=java_homes["17"], postgres=None, root=root,
                )
                if control != preview:
                    raise AssertionError(f"Repeated ordinary Boot 4.1 wire mismatch for {kind}:\n{control!r}\n{preview!r}")
                expected_input_statuses = (400, 400)
                if (
                    control_info["trailing_json_status"], preview_info["trailing_json_status"]
                ) != expected_input_statuses:
                    raise AssertionError(f"{kind} MVC Jackson input policy changed unexpectedly")
                if kind == "passthrough" and (
                    control_info["downstream_trailing_json_status"],
                    preview_info["downstream_trailing_json_status"],
                ) != (500, 500):
                    raise AssertionError("Passthrough RestTemplate input policy changed unexpectedly")
                summary["wire_comparisons"].append(kind)
                summary["runtimes"].append({
                    **preview_info, "profile": _PROFILES[0][1], "java": "17",
                    "repeat_trailing_json_status": control_info["trailing_json_status"],
                    "repeat_downstream_trailing_json_status": control_info["downstream_trailing_json_status"],
                })
                print(f"wire comparison passed: {kind}", file=sys.stderr)
            if postgres:
                for label, _base, preview, java, _needs_pg in _PROFILES[1:]:
                    for kind in ("crud", "soap-in"):
                        _observations, info = _exercise(
                            kind=kind, jar=packages[(kind, label)],
                            java_home=java_homes[java], postgres=postgres, root=root,
                        )
                        summary["runtimes"].append({**info, "profile": _base, "java": java})
                        print(f"PostgreSQL runtime passed: {kind}/{label}", file=sys.stderr)
    finally:
        _close_postgres(postgres)
    summary.update(observed_at=datetime.now(timezone.utc).isoformat(),
                   source_sha=_run(["git", "rev-parse", "HEAD"], cwd=Path.cwd(), env=os.environ.copy(), timeout=10).strip(),
                   source_dirty=bool(_run(["git", "status", "--porcelain"], cwd=Path.cwd(), env=os.environ.copy(), timeout=10).strip()))
    if work_dir:
        (work_dir / "receipt.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("h2", "full"), required=True)
    parser.add_argument("--java17-home", default=os.environ.get("JAVA17_HOME") or os.environ.get("JAVA_HOME"), required=False)
    parser.add_argument("--java21-home", default=os.environ.get("JAVA21_HOME"))
    parser.add_argument("--maven-repo", type=Path)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    if not args.java17_home:
        parser.error("--java17-home or JAVA17_HOME is required")
    print(json.dumps(_proof(args), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
