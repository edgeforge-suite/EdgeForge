"""Bounded Java 17/H2 selected-write transport proof, not business certification."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml

from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project
from scripts.smoke.boot41_preview_proof import _jdk_env, _run, _source_digest
from scripts.smoke.dto_property_proof import verify_dto_properties
from scripts.smoke.generated_app_independence import verify_generated_app_independence
from tests.unit.test_write_contract import package, param


def _crud_input(root: Path) -> Path:
    manifest = package(root, parameters=[param("X-Trace"), param("branch", "query", False, "integer"),
        param("notify", "query", False, "boolean"), param("X-Dry-Run", "header", False, "boolean")])
    definition = yaml.safe_load(manifest.read_text())
    spec_path, mapping_path = root / "spec.yaml", root / "mapping.yaml"
    spec, mappings = yaml.safe_load(spec_path.read_text()), yaml.safe_load(mapping_path.read_text())
    original = spec["paths"]["/accounts"]["post"]
    for method, name, code in (("put", "updateAccount", "200"), ("delete", "deleteAccount", "204")):
        operation = json.loads(json.dumps(original))
        operation["operationId"] = name
        operation["parameters"].append(param("accountId", "path"))
        operation["responses"] = {code: operation["responses"]["201"] if method == "put" else {"description": "Deleted"}}
        if method == "delete":
            operation.pop("requestBody")
        spec["paths"].setdefault("/accounts/{accountId}", {})[method] = operation
        definition["upstream_interfaces"][0]["operations"].append({"name": name,
            "request_sample": "request.json", **({"response_sample": "response.json"} if method == "put" else {})})
        mappings["operations"].append({**mappings["operations"][0], "name": name})
    manifest.write_text(yaml.safe_dump(definition))
    spec_path.write_text(yaml.safe_dump(spec))
    mapping_path.write_text(yaml.safe_dump(mappings))
    return manifest


def _developer_probe(project: Path, payment: bool) -> None:
    name = "InternationalPayment" if payment else "Account"
    path = next(project.rglob(name + "Service.java"))
    source = path.read_text()
    if payment:
        needle = "        return super.createInternationalPayments("
        code = ('        if (!"proof-key".equals(xIdempotencyKey) || !"proof-signature".equals(xJwsSignature)\n'
                '                || !"proof-client".equals(xClientId)) {\n'
                '            throw new IllegalArgumentException("test-owned transport delivery failed");\n'
                '        }\n')
        source = source.replace(needle, code + needle)
    else:
        for method in ("createAccount", "updateAccount"):
            needle = f"        return super.{method}("
            source = source.replace(needle, '        request.setStatus(xTrace + ":" + branch);\n' + needle)
        needle = "        return super.createAccount("
        check = ('        if ("A".equals(request.getId())\n'
                 '                ? !Boolean.FALSE.equals(notify) || !Boolean.FALSE.equals(xDryRun)\n'
                 '                : notify != null || xDryRun != null) {\n'
                 '            throw new IllegalArgumentException("test-owned optional Boolean delivery failed");\n'
                 '        }\n')
        source = source.replace(needle, check + needle)
        source = source.replace("        super.delete(",
            '        if (!"delete-trace".equals(xTrace) || !Long.valueOf(17).equals(branch)) {\n'
            '            throw new IllegalArgumentException("test-owned delete delivery failed");\n'
            '        }\n        super.delete(')
    if source == path.read_text():
        raise AssertionError("Expected developer seam was not found")
    path.write_text(source)


def _request(port, method, path, body=None, headers=None):
    request = Request(f"http://127.0.0.1:{port}{path}", method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except HTTPError as exc:
        return exc.code, exc.read().decode()


def _runtime(project, env, payment, log):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    jar = next((project / "target").glob("*.jar"))
    observations = []
    with log.open("w") as stream:
        process = subprocess.Popen([str(Path(env["JAVA_HOME"]) / "bin/java"), "-jar", str(jar),
            "--server.address=127.0.0.1", f"--server.port={port}"], cwd=project, env=env,
            stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 60
            ready = False
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    status, _ = _request(port, "GET", "/actuator/health")
                    if status == 200:
                        ready = True
                        break
                except OSError:
                    pass
                time.sleep(0.2)
            if not ready:
                raise AssertionError("Application did not start with normal Flyway/DDL")
            def call(method, path, expected, body=None, headers=None):
                status, content = _request(port, method, path, body, headers)
                observations.append({"method": method, "path": path, "status": status, "body": content})
                if status != expected:
                    raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {content}")
                return json.loads(content) if content else None
            if payment:
                path = "/international-payments"
                body = {"ConsentId": "consent-proof", "InstructionIdentification": "instruction-proof",
                        "EndToEndIdentification": "end-to-end-proof", "CurrencyOfTransfer": "USD",
                        "InstructedAmount": "42.50", "CreditorName": "Synthetic recipient"}
                headers = {"x-idempotency-key": "proof-key", "x-jws-signature": "proof-signature", "x-client-id": "proof-client"}
                for missing in (None, "x-idempotency-key", "x-jws-signature"):
                    supplied = {} if missing is None else {key: value for key, value in headers.items() if key != missing}
                    call("POST", path, 400, body, supplied)
                    if call("GET", path, 200) != []:
                        raise AssertionError("Missing required header caused persistence")
                created = call("POST", path, 201, body, headers)
                if any(created[key] != body[key] for key in ("ConsentId", "CurrencyOfTransfer", "InstructedAmount")):
                    raise AssertionError("Payment response changed field names, values or types")
                identifier = created["InternationalPaymentId"]
                if not isinstance(identifier, str) or not identifier:
                    raise AssertionError("Original persistence identity was not retained")
                fetched = call("GET", path + "/" + identifier, 200)
                mapped_keys = {"InternationalPaymentId", "ConsentId", "Status", "StatusUpdateDateTime", "CurrencyOfTransfer", "InstructedAmount"}
                unintended_aliases = {key[:1].lower() + key[1:] for key in mapped_keys - {"InstructedAmount"}}
                for label, response in (("POST", created), ("GET", fetched)):
                    if not mapped_keys <= response.keys() or unintended_aliases & response.keys():
                        raise AssertionError(f"Payment {label} added mapped aliases or lost mapped keys")
                if any(fetched[key] != value for key, value in body.items()):
                    raise AssertionError("Payment GET did not retain the mapped request values")
                if fetched["InternationalPaymentId"] != identifier:
                    raise AssertionError("Payment GET changed persistence identity")
                if len(call("GET", path, 200)) != 1:
                    raise AssertionError("Accepted payment transport did not persist exactly once in this proof")
            else:
                body = {"id": "A", "status": "OPEN"}
                call("POST", "/accounts", 400, body)
                call("GET", "/accounts/A", 404)
                result = call("POST", "/accounts?branch=7&notify=false", 201, body,
                    {"X-Trace": "create-trace", "X-Dry-Run": "false"})
                if result["status"] != "create-trace:7":
                    raise AssertionError("Required header/optional query not delivered to developer create")
                call("PUT", "/accounts/A?branch=9", 400, body)
                if call("GET", "/accounts/A", 200)["status"] != "create-trace:7":
                    raise AssertionError("Rejected update changed data")
                result = call("PUT", "/accounts/A?branch=9", 200, body, {"X-Trace": "update-trace"})
                if result["status"] != "update-trace:9":
                    raise AssertionError("Write inputs not delivered to developer update")
                call("POST", "/accounts", 201, {"id": "B", "status": "OPEN"}, {"X-Trace": "optional-absent"})
                if call("GET", "/accounts/B", 200)["status"] != "optional-absent:null":
                    raise AssertionError("Absent optional input was not preserved")
                call("DELETE", "/accounts/A?branch=17", 400)
                call("GET", "/accounts/A", 200)
                call("DELETE", "/accounts/A?branch=17", 204, headers={"X-Trace": "delete-trace"})
                call("GET", "/accounts/A", 404)
            return observations
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def main():
    if not __debug__ or os.environ.get("PYTHONOPTIMIZE", "") not in {"", "0"}:
        raise SystemExit("Write proof requires unoptimized Python")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--java17-home", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    env = _jdk_env(args.java17_home)
    receipts = []
    for name, manifest in (("crud", _crud_input(args.output / "input")),
                           ("payment", Path("examples/input-projects/obie-wire-transfer/app-definition.yaml"))):
        metadata = build_metadata_project(manifest)
        project = args.output / name
        generate_application(metadata, project, generation_run_id="write-contract-proof")
        generated = _source_digest(project)
        generate_application(metadata, project, generation_run_id="write-contract-proof")
        if _source_digest(project) != generated:
            raise AssertionError("Repeated generation changed output")
        _developer_probe(project, name == "payment")
        developer = next(project.rglob(("InternationalPayment" if name == "payment" else "Account") + "Service.java"))
        preserved = developer.read_bytes()
        generate_application(metadata, project, generation_run_id="write-contract-proof")
        if developer.read_bytes() != preserved:
            raise AssertionError("Regeneration changed developer test implementation")
        before = _source_digest(project)
        verify_generated_app_independence(project, require_schema_baseline=True)
        output = _run(["mvn", "-B", "-ntp", "-o", "clean", "verify"], cwd=project, env=env, timeout=300)
        (args.output / (name + "-build.log")).write_text(output)
        if before != _source_digest(project):
            raise AssertionError("Build changed source/config")
        verify_generated_app_independence(project, require_schema_baseline=True, require_packaged_jar=True)
        observations = _runtime(project, env, name == "payment", args.output / (name + "-runtime.log"))
        (args.output / (name + "-http.json")).write_text(json.dumps(observations, indent=2) + "\n")
        counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
        for path in (project / "target/surefire-reports").glob("TEST-*.xml"):
            root = ET.parse(path).getroot()
            for key in counts:
                counts[key] += int(root.get(key, "0"))
        if counts["tests"] < 1 or any(counts[key] for key in ("failures", "errors", "skipped")):
            raise AssertionError(f"Incomplete Maven proof: {counts}")
        receipts.append({"case": name, "tests": counts, "http_assertions": len(observations),
            "normal_database_initialization": True, "independence": "source-and-packaged",
            "repeat_generation": True, "developer_preservation": True, "source_sha256": before,
            "scope": "transport only; test-owned developer implementation, no business/security certification"})
        if name == "payment":
            verify_dto_properties(args.output / "dto-properties", next((project / "target").glob("*.jar")),
                args.java17_home, metadata)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
    (args.output / "receipt.json").write_text(json.dumps({"engine_sha": head, "working_tree_dirty": dirty,
        "cases": receipts}, indent=2) + "\n")


if __name__ == "__main__":
    main()
