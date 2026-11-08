"""Four fresh Java17/H2 demo/batch combinations; no generated source/config patches.

Run from the Engine root with unoptimized Python. This is a development/runtime
receipt, not gateway, authorization, business, or compatibility certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from appbuilder.generation import generate_application
from appbuilder.mapping import MappingDirection
from appbuilder.metadata import build_metadata_project
from scripts.smoke.boot41_preview_proof import _jdk_env, _source_digest, _verify_java_home
from scripts.smoke.write_contract_proof import _request


def _metadata(*, demo: bool, batch: bool):
    metadata = build_metadata_project(Path("tests/fixtures/boot41-batch/ordinary-app-definition.yaml"))
    if not batch:
        metadata.contracts = [c for c in metadata.contracts if c.type != "staging-table"]
        metadata.mappings = [m for m in metadata.mappings if m.direction != MappingDirection.CANONICAL_TO_HANDOFF]
    if not demo:
        metadata.operations = []
        metadata.selected_rest_contracts = []
        metadata.contracts = [c for c in metadata.contracts if c.type != "rest-json"]
        metadata.mappings = [m for m in metadata.mappings if m.direction != MappingDirection.UPSTREAM_TO_CANONICAL]
    return metadata


def _runtime(project, env, log, *, demo, batch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [str(Path(env["JAVA_HOME"]) / "bin/java"), "-jar",
               str(next((project / "target").glob("*.jar"))),
               "--server.address=127.0.0.1", f"--server.port={port}"]
    if demo and batch:
        command.append("--appbuilder.demo.enabled=true")
    observations = []
    with log.open("w") as stream:
        process = subprocess.Popen(command, cwd=project, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 60
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    if _request(port, "GET", "/actuator/health")[0] == 200:
                        break
                except OSError:
                    pass
                time.sleep(0.2)
            else:
                raise AssertionError("Normal startup/Flyway/schema initialization did not become ready")

            def call(method, path, expected, body=None):
                status, content = _request(port, method, path, body)
                observations.append({"method": method, "path": path, "status": status, "body": content})
                log.with_suffix(".http.json").write_text(json.dumps(observations, indent=2) + "\n")
                if status != expected:
                    raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {content}")
                return json.loads(content) if content else None

            created = call("POST", "/widgets", 201, {"payloadKey": "boundary-proof"})
            identifier = created["widgetId"]
            if not identifier or call("GET", "/widgets/" + identifier, 200)["payloadKey"] != "boundary-proof":
                raise AssertionError("Representative create/own-ID read did not preserve the payload")
            rows = call("GET", "/widgets", 200)
            if len(rows) != 1:
                raise AssertionError("Generic CRUD list is not available or changed data")
            demo_status = 200 if demo and batch else 403 if demo else 404
            entities = call("GET", "/api/demo/entities", demo_status)
            entity_rows = call("GET", "/api/demo/entities/Widget", demo_status)
            if demo and batch and (entities != [{"entityName": "Widget"}]
                                   or len(entity_rows) != 1
                                   or entity_rows[0]["payloadKey"] != "boundary-proof"):
                raise AssertionError("Opt-in demo did not enumerate the persisted entity")
            execution = call("POST", "/batch/run/widgetEodJob", 200 if batch else 404)
            if batch and execution.get("status") != "COMPLETED":
                raise AssertionError(f"Ordinary batch did not complete: {execution}")
            if batch:
                call("POST", "/batch/run/missingJob", 404)
            return {"command": command, "http": observations}
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
        raise SystemExit("Endpoint boundary proof requires unoptimized Python")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--java17-home", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    _verify_java_home(args.java17_home, "17")
    env = _jdk_env(args.java17_home)
    receipt = {
        "engine_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
        "scope": "fresh Java17/H2 development proof; no gateway/authorization certification",
        "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "engine_generation_sources": {
            path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path("appbuilder/generation").glob("*.py"))
        },
        "cases": [],
    }
    receipt_path = args.output / "receipt.json"
    try:
        for demo, batch in ((False, False), (True, False), (False, True), (True, True)):
            name = f"demo-{int(demo)}-batch-{int(batch)}"
            case = {"case": name, "demo": demo, "batch": batch, "status": "started"}
            receipt["cases"].append(case)
            project = args.output / name
            metadata = _metadata(demo=demo, batch=batch)
            generate_application(metadata, project, generation_run_id="endpoint-boundary-proof")
            before = _source_digest(project)
            generate_application(metadata, project, generation_run_id="endpoint-boundary-proof")
            if before != _source_digest(project):
                raise AssertionError("Repeated generation changed source/config")
            case["source_sha256"] = before
            if bool(list(project.rglob("DemoController.java"))) != demo:
                raise AssertionError("Demo source applicability differs from input case")
            if bool(list(project.rglob("BatchTriggerController.java"))) != batch:
                raise AssertionError("Batch source applicability differs from input case")
            command = ["mvn", "-B", "-ntp", "-o", "clean", "verify"]
            case["build_command"] = command
            result = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True, timeout=300)
            (args.output / (name + "-build.log")).write_text(result.stdout + result.stderr)
            if result.returncode:
                raise AssertionError(f"{name}: Maven failed ({result.returncode}); inspect saved build log")
            counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
            for path in (project / "target/surefire-reports").glob("TEST-*.xml"):
                suite = ET.parse(path).getroot()
                for key in counts:
                    counts[key] += int(suite.get(key, "0"))
            case["tests"] = counts
            if counts["tests"] < 1 or any(counts[key] for key in ("failures", "errors", "skipped")):
                raise AssertionError(f"Generated tests did not fully execute: {counts}")
            case["runtime_log"] = str(args.output / (name + "-runtime.log"))
            case.update(_runtime(project, env, Path(case["runtime_log"]), demo=demo, batch=batch))
            if before != _source_digest(project):
                raise AssertionError("Build/runtime changed generated source/config")
            case["normal_database_initialization"] = True
            case["status"] = "passed"
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    except Exception as exc:
        receipt["failure"] = str(exc)
        raise
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
