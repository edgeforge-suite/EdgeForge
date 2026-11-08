"""Bounded broker contracts and repeat-runtime proof for ordinary profiles."""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from appbuilder.contracts import load_project_definition
from appbuilder.generation import generate_application
from appbuilder.metadata.kafka_translation import translate_kafka_project
from scripts.smoke.boot41_preview_proof import _jdk_env, _run, _source_digest, _verify_java_home
from scripts.smoke.generated_app_independence import verify_generated_app_independence

BASES = (
    "springboot-legacy-compatible",
    "springboot-enterprise-postgres-java17",
    "springboot-standard-enterprise",
)

# Exact fixture diagnostics are observable differences, not fields to suppress.
DIAGNOSTICS = {
    "v1": (
        "ro-request",
        "$.status: is missing but it is required",
        ": required property 'status' not found",
    ),
    "v2": (
        "d1-request",
        "$.amount: must have a minimum value of 1",
        "/amount: must have a minimum value of 1",
    ),
    "v3": (
        "d1-response",
        "$.processorStatus: does not have a value in the enumeration [ACCEPTED, REJECTED, OTHER]",
        '/processorStatus: does not have a value in the enumeration ["ACCEPTED", "REJECTED", "OTHER"]',
    ),
    "v4": (
        "ro-response",
        "$.status: does not match the regex pattern ^(APPROVED|DECLINED)$",
        "/status: does not match the regex pattern ^(APPROVED|DECLINED)$",
    ),
}


def compare_wire(control: list[dict], preview: list[dict], *, same_line: bool = False) -> list[dict]:
    """Compare the bounded fixture, retaining narrowly checked diagnostic deltas."""
    if (
        not control
        or len(control) != len(preview)
        or len({r["case"] for r in control}) != len(control)
    ):
        raise AssertionError("Missing or duplicate wire observations")
    changes = []
    for left, right in zip(copy.deepcopy(control), copy.deepcopy(preview), strict=True):
        case = left["case"]
        if right["case"] != case:
            raise AssertionError("Wire case/order mismatch")
        for row in (left, right):
            body = row["payload"]
            if case in {
                "invalid-source",
                "invalid-reply",
                "v1",
                "v2",
                "v3",
                "v4",
                "duplicate",
                "timeout",
            }:
                stamp = datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00"))
                if stamp.tzinfo is None or stamp.year < 2026:
                    raise AssertionError("Invalid generated NACK timestamp")
                body["timestamp"] = "<validated-instant>"
        if case in DIAGNOSTICS:
            schema, old, new = DIAGNOSTICS[case]
            prefix = f"{case.upper()} validation failed for schema router/schemas/{schema}.json: "
            expected = (prefix + "[" + (new if same_line else old) + "]", prefix + "[" + new + "]")
            actual = (left["payload"]["errorReason"], right["payload"]["errorReason"])
            if actual != expected:
                raise AssertionError(f"Unexpected {case} diagnostic: {actual}")
            changes.append(
                {"case": case, "field": "errorReason", "control": actual[0], "preview": actual[1]}
            )
            right["payload"]["errorReason"] = left["payload"]["errorReason"]
        if case == "technical-dlq":
            for row in (left, right):
                headers = row["headers_base64"]
                for name, width in (
                    ("kafka_dlt-original-timestamp", 8),
                    ("kafka_dlt-original-offset", 8),
                    ("kafka_dlt-original-partition", 4),
                ):
                    values = headers[name]
                    raw = base64.b64decode(values[0], validate=True)
                    if (
                        len(values) != 1
                        or len(raw) != width
                        or int.from_bytes(raw, "big", signed=True) < 0
                    ):
                        raise AssertionError(f"Invalid broker metadata: {name}")
                    if name == "kafka_dlt-original-timestamp":
                        datetime.fromtimestamp(int.from_bytes(raw, "big") / 1000, timezone.utc)
                        headers[name] = ["<validated-broker-timestamp>"]
            stacks = []
            for row, cause in (
                (left, "tools.jackson.core.exc.StreamReadException" if same_line else "com.fasterxml.jackson.core.JsonParseException"),
                (right, "tools.jackson.core.exc.StreamReadException"),
            ):
                values = row["headers_base64"]["kafka_dlt-exception-stacktrace"]
                stack = base64.b64decode(values[0], validate=True).decode()
                if (
                    len(values) != 1
                    or "Caused by: " + cause not in stack
                    or "Unrecognized token 'not'" not in stack
                    or "Failed to process Kafka message" not in stack
                ):
                    raise AssertionError("Unexpected technical DLQ diagnostic")
                stacks.append(stack)
            changes.append(
                {
                    "case": case,
                    "field": "kafka_dlt-exception-stacktrace",
                    "control": stacks[0],
                    "preview": stacks[1],
                }
            )
            right["headers_base64"]["kafka_dlt-exception-stacktrace"] = left["headers_base64"][
                "kafka_dlt-exception-stacktrace"
            ]
        # Canonical JSON ignores member order, but preserves boolean/numeric/string types.
        if json.dumps(left, sort_keys=True) != json.dumps(right, sort_keys=True):
            raise AssertionError(f"Wire contract mismatch: {case}")
    return changes


def prepare_input(root: Path) -> Path:
    fixture = root / "input"
    shutil.copytree("tests/fixtures/kafka-multi-route", fixture)
    shutil.copytree("tests/fixtures/kafka-router-contract", fixture / "router")
    manifest = yaml.safe_load((fixture / "manifest.yaml").read_text())
    manifest["app_name"] = "Kafka Preview Proof"
    manifest["bounded_context"] = "kafka-proof"
    manifest["kafka_config"]["concurrency"] = 1
    manifest["kafka_config"]["retry"].update(backoff_ms=100, backoff_multiplier=1.0)
    router = yaml.safe_load((fixture / "router/manifest.yaml").read_text())["async_routes"][0]
    config = router["router_config"]
    for entry in (config["inbound_schema"], config["outbound_schema"]):
        entry["file"] = "router/" + entry["file"]
    for target in config["targets"]:
        for key in ("request_schema", "response_schema", "request_transform", "response_transform"):
            target[key]["file"] = "router/" + target[key]["file"]
        target["timeout_ms"] = 2000
    second = copy.deepcopy(config["targets"][0])
    second.update(
        id="d2_processor", request_topic="d2-payment-request", response_topic="d2-payment-response"
    )
    config["targets"].append(second)
    config["routing_rules"]["rules"].append(
        {
            "id": "us",
            "conditions": [{"field": "country", "operator": "eq", "value": "US"}],
            "target": "d2_processor",
        }
    )
    config["upstream_topics"].append(
        {
            "id": "u2_intake",
            "name": "u2-payment-request",
            "consumer_group": "proof-u2",
            "source_system_extraction": {"mode": "body_field", "body_field_path": "$.sourceSystem"},
            "reply_destination_extraction": {
                "mode": "body_field",
                "body_field_path": "$.replyTopic",
            },
        }
    )
    config["correlation_store"].update(eviction_interval_ms=1000)
    manifest["async_routes"].append(router)
    (fixture / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
    for name in ("payment-posted-event", "ledger-entry-message"):
        path = fixture / "schemas" / f"{name}.json"
        schema = json.loads(path.read_text())
        schema["properties"].update(
            businessDate={"type": "string", "format": "date"}, note={"type": "string"}
        )
        path.write_text(json.dumps(schema, indent=2) + "\n")
    path = fixture / "mappings/payment-to-ledger.yaml"
    mapping = yaml.safe_load(path.read_text())
    mapping["transforms"].extend(
        [{"source": "businessDate", "target": "businessDate"}, {"source": "note", "target": "note"}]
    )
    path.write_text(yaml.safe_dump(mapping))
    changes = {
        "ro-request": lambda schema: schema["properties"].update(
            {k: {"type": "string"} for k in ("sourceSystem", "replyTopic", "correlationId")}
        ),
        "d1-request": lambda schema: schema["properties"]["amount"].update(minimum=1),
        "d1-response": lambda schema: schema["properties"]["processorStatus"]["enum"].append(
            "OTHER"
        ),
        "ro-response": lambda schema: schema["properties"]["status"].update(
            pattern="^(APPROVED|DECLINED)$"
        ),
    }
    for name, change in changes.items():
        path = fixture / "router/schemas" / f"{name}.json"
        schema = json.loads(path.read_text())
        change(schema)
        if name == "d1-request":
            schema["$schema"] = "http://json-schema.org/draft-07/schema#"
        path.write_text(json.dumps(schema, indent=2) + "\n")
    path = fixture / "router/transforms/d1-to-ro-response.yaml"
    mapping = yaml.safe_load(path.read_text())
    mapping["transforms"][0]["value_map"]["OTHER"] = "OTHER"
    path.write_text(yaml.safe_dump(mapping))
    return fixture


def _counts(app: Path, expected: int) -> dict:
    counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for directory in ("surefire-reports", "failsafe-reports"):
        for report in (app / "target" / directory).glob("TEST-*.xml"):
            suite = ET.parse(report).getroot()
            for key in counts:
                counts[key] += int(suite.get(key, "0"))
    if counts["tests"] != expected or any(counts[k] for k in ("failures", "errors", "skipped")):
        raise AssertionError(f"Incomplete Kafka proof: {counts}")
    return counts


def _graph(app: Path, command: list[str], java: Path, router: bool) -> dict:
    _run(
        command
        + [
            "help:effective-pom",
            "-Doutput=target/effective-pom.xml",
            "dependency:tree",
            "-DoutputType=json",
            "-DoutputFile=target/dependencies.json",
        ],
        cwd=app,
        env=_jdk_env(java),
        timeout=180,
    )
    tree = json.loads((app / "target/dependencies.json").read_text())
    artifacts = {}

    def visit(node):
        artifacts[node["groupId"] + ":" + node["artifactId"]] = {
            "version": node["version"],
            "scope": node.get("scope", "root"),
        }
        for child in node.get("children", []):
            visit(child)

    visit(tree)
    for coordinate, version in {
        "org.springframework.kafka:spring-kafka": "4.1.1",
        "org.apache.kafka:kafka-clients": "4.2.1",
        "tools.jackson.core:jackson-databind": "3.1.7",
        "tools.jackson.core:jackson-core": "3.1.7",
        "com.fasterxml.jackson.core:jackson-annotations": "2.21",
        "at.yawk.lz4:lz4-java": "1.11.4",
        "org.apache.tomcat.embed:tomcat-embed-core": "11.0.26",
        "org.apache.tomcat.embed:tomcat-embed-el": "11.0.26",
        "org.apache.tomcat.embed:tomcat-embed-websocket": "11.0.26",
        **({"com.networknt:json-schema-validator": "3.0.6"} if router else {}),
    }.items():
        if artifacts.get(coordinate, {}).get("version") != version:
            raise AssertionError(f"Unexpected resolved version: {coordinate}")
    if any(
        item["version"] != "3.1.7"
        for coordinate, item in artifacts.items()
        if coordinate.startswith("tools.jackson.")
    ):
        raise AssertionError("Unmanaged Jackson 3 module")
    if not router and "com.networknt:json-schema-validator" in artifacts:
        raise AssertionError("Unused router validator")
    pom = ET.parse(app / "target/effective-pom.xml").getroot()
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    if pom.findtext("m:parent/m:version", namespaces=ns) != "4.1.1":
        raise AssertionError("Wrong effective Boot parent")
    jar = next((app / "target").glob("*.jar"))
    with zipfile.ZipFile(jar) as stream:
        libraries = sorted(
            name.rsplit("/", 1)[-1]
            for name in stream.namelist()
            if name.startswith("BOOT-INF/lib/") and name.endswith(".jar")
        )
    for library in libraries:
        if library.startswith(
            ("jackson-databind-2", "jackson-core-2", "spring-batch-", "h2-", "postgresql-")
        ):
            raise AssertionError(f"Unexpected runtime library: {library}")
    return {
        "resolved": artifacts,
        "packaged_libraries": libraries,
        "jackson2_compatibility": [
            lib for lib in libraries if lib.startswith("jackson-annotations-")
        ],
    }


def proof(java17: Path, java21: Path | None, root: Path, repo: Path | None):
    _verify_java_home(java17, "17")
    if java21:
        _verify_java_home(java21, "21")
    root.mkdir(parents=True, exist_ok=False)
    fixture = prepare_input(root)
    rows = []
    profiles = [(base, java21 if base == BASES[2] else java17) for base in BASES]
    if not java21:
        profiles = profiles[:1]
    for base, java in profiles:
        for repetition in ("first", "second"):
            profile = base
            definition = load_project_definition(fixture / "manifest.yaml")
            definition.target_profile = profile
            metadata = translate_kafka_project(definition, fixture)
            app = root / f"{profile}-{repetition}"
            generate_application(
                metadata,
                app,
                source_manifest="kafka-proof/manifest.yaml",
                generation_run_id="kafka-proof",
            )
            repeat = root / f"{profile}-{repetition}-repeat"
            generate_application(
                metadata,
                repeat,
                source_manifest="kafka-proof/manifest.yaml",
                generation_run_id="kafka-proof",
            )
            digest = _source_digest(app)
            if _source_digest(repeat) != digest:
                raise AssertionError("Non-deterministic Kafka output")
            verify_generated_app_independence(app)
            test = Path("tests/fixtures/boot41-kafka/KafkaWireTest.java").read_text()
            app_class = f"{metadata.java_package}.KafkaPreviewProofApplication"
            test = test.replace("__APP__", app_class).replace(
                "__APP_CLASS__", "KafkaPreviewProofApplication"
            )
            test = test.replace(
                "__JACKSON__", "tools.jackson"
            )
            target = app / "src/test/java/proof/KafkaWireTest.java"
            target.parent.mkdir(parents=True)
            target.write_text(test)
            resources = app / "src/test/resources/proof"
            resources.mkdir(parents=True)
            for name, dialect in (
                ("draft7", "http://json-schema.org/draft-07/schema#"),
                ("draft2020", "https://json-schema.org/draft/2020-12/schema"),
                ("default", None),
            ):
                schema = {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date"},
                        "amount": {"$ref": "#/definitions/amount"},
                    },
                    "definitions": {"amount": {"type": "number"}},
                    "required": ["date", "amount"],
                }
                if dialect:
                    schema["$schema"] = dialect
                (resources / f"{name}.json").write_text(json.dumps(schema))
            source_with_test = _source_digest(app)
            command = ["mvn", "-B", "-ntp"] + ([f"-Dmaven.repo.local={repo}"] if repo else [])
            try:
                output = _run(
                    command + ["clean", "verify"], cwd=app, env=_jdk_env(java), timeout=360
                )
            except (AssertionError, subprocess.SubprocessError) as exc:
                (root / f"{profile}-{repetition}.log").write_text(str(exc))
                raise
            (root / f"{profile}-{repetition}.log").write_text(output)
            counts = _counts(app, 14)
            if _source_digest(app) != source_with_test:
                raise AssertionError("Build mutated generated sources")
            verify_generated_app_independence(app, require_packaged_jar=True)
            observations = json.loads((app / "target/wire-observations.json").read_text())
            expected = {
                "plain",
                "account-request",
                "account-reply",
                "router-request",
                "router-reply",
                "body-request",
                "body-reply",
                "invalid-source",
                "invalid-reply",
                "v1",
                "v2",
                "v3",
                "v4",
                "duplicate",
                "timeout",
                "technical-dlq",
                "reversal",
                "fraud-request",
                "fraud-reply",
            }
            if (
                len(observations) != len(expected)
                or {row["case"] for row in observations} != expected
            ):
                raise AssertionError("Incomplete wire contract coverage")
            rows.append(
                {
                    "profile": profile,
                    "repetition": repetition,
                    "source_digest": digest,
                    "maven": counts,
                    "observations": observations,
                    "graph": _graph(app, command, java, True),
                }
            )
    comparisons = [
        {
            "control": rows[index]["profile"],
            "repeat": rows[index + 1]["profile"],
            "diagnostic_differences": compare_wire(
                rows[index]["observations"], rows[index + 1]["observations"], same_line=True
            ),
        }
        for index in range(0, len(rows), 2)
    ]
    standalone = []
    for base, java in profiles:
        profile = base
        for kind in ("plain", "router"):
            definition = load_project_definition(fixture / "manifest.yaml")
            definition.target_profile = profile
            definition.async_routes = [
                route
                for route in definition.async_routes
                if (route.pattern == "router") == (kind == "router")
            ]
            metadata = translate_kafka_project(definition, fixture)
            app = root / f"{profile}-{kind}"
            generate_application(
                metadata,
                app,
                source_manifest="kafka-proof/manifest.yaml",
                generation_run_id="kafka-proof",
            )
            verify_generated_app_independence(app)
            test = (
                Path("tests/fixtures/boot41-kafka/KafkaRoundtripTest.java")
                .read_text()
                .replace("__APP__", f"{metadata.java_package}.KafkaPreviewProofApplication")
                .replace("__APP_CLASS__", "KafkaPreviewProofApplication")
                .replace("__JACKSON__", "tools.jackson")
                .replace("__ROUTER__", str(kind == "router").lower())
            )
            target = app / "src/test/java/proof/KafkaRoundtripTest.java"
            target.parent.mkdir(parents=True)
            target.write_text(test)
            digest = _source_digest(app)
            command = ["mvn", "-B", "-ntp"] + ([f"-Dmaven.repo.local={repo}"] if repo else [])
            try:
                output = _run(
                    command + ["clean", "verify"], cwd=app, env=_jdk_env(java), timeout=360
                )
            except (AssertionError, subprocess.SubprocessError) as exc:
                (root / f"{profile}-{kind}.log").write_text(str(exc))
                raise
            (root / f"{profile}-{kind}.log").write_text(output)
            if _source_digest(app) != digest:
                raise AssertionError("Build mutated sources")
            verify_generated_app_independence(app, require_packaged_jar=True)
            standalone.append(
                {
                    "profile": profile,
                    "kind": kind,
                    "maven": _counts(app, 1),
                    "graph": _graph(app, command, java, kind == "router"),
                }
            )
    report = {
        "builds": rows,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "comparisons": comparisons,
        "standalone": standalone,
        "source_sha": _run(
            ["git", "rev-parse", "HEAD"], cwd=Path.cwd(), env=os.environ.copy()
        ).strip(),
        "source_dirty": bool(
            _run(["git", "status", "--porcelain"], cwd=Path.cwd(), env=os.environ.copy()).strip()
        ),
        "release_acceptance": "not-established",
    }
    (root / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java17-home", type=Path, required=True)
    parser.add_argument("--java21-home", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--maven-repo", type=Path)
    args = parser.parse_args()
    result = proof(args.java17_home, args.java21_home, args.work_dir, args.maven_repo)
    print(
        json.dumps(
            {
                "source_sha": result["source_sha"],
                "builds": len(result["builds"]) + len(result["standalone"]),
                "result": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()
