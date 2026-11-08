"""Bounded read-contract runtime proof; reuses existing build/database helpers."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from appbuilder.generation import generate_application
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata.models import OperationParameter, OperationParameterLocation
from appbuilder.target_profiles.catalog import TARGET_PROFILES
from scripts.smoke.boot41_preview_proof import (
    _close_postgres,
    _database_env,
    _jdk_env,
    _Postgres,
    _run,
    _source_digest,
)
from scripts.smoke.generated_app_independence import verify_generated_app_independence
from tests.unit.test_read_contract import mapped_metadata


def _verify_console_list_endpoint(project: Path, profile: str) -> str | None:
    console_path = project / "src/main/resources/static/index.html"
    if not TARGET_PROFILES[profile].emit_test_console:
        if console_path.exists():
            raise AssertionError("Profile unexpectedly emitted a bundled console")
        return None
    if not console_path.is_file():
        raise AssertionError("Required generated console is missing")
    descriptor_match = re.search(r"const DESCRIPTORS = (\[.*?\]);\n    const DESCRIPTOR_BY_KEY", console_path.read_text(), re.S)
    if descriptor_match is None:
        raise AssertionError("Generated console descriptors are missing")
    lists = [item for item in json.loads(descriptor_match.group(1)) if item["coverageKey"] == "Account-list"]
    if len(lists) != 1 or lists[0]["actions"][0]["endpoint"] != "/accounts/history":
        raise AssertionError("Generated console list endpoint does not match the selected route")
    return "/accounts/history"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--java17-home", required=True, type=Path)
    parser.add_argument("--java21-home", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    postgres = None
    receipts = []
    try:
        postgres = _Postgres()
        for profile, java_home, mixed, pageable in (
            ("springboot-legacy-compatible", args.java17_home, False, False),
            ("springboot-enterprise-postgres-java17", args.java17_home, True, True),
            ("springboot-standard-enterprise", args.java21_home, False, True),
        ):
            metadata = mapped_metadata(profile, mixed=mixed, pageable=pageable)
            metadata.operations[1].path = "/accounts/history"
            computed = metadata.operations[0].model_copy(deep=True)
            computed.name = "accountSummary"
            computed.path = "/accounts/{id}/summary"
            metadata.operations.append(computed)
            metadata.mappings.extend([FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api",
                operation_name=computed.name, source_path=f"api.{computed.name}.response.{field}",
                target_path=f"Account.{field}",
            ) for field in ("id", "customerId")])
            for mapping in metadata.mappings:
                if mapping.operation_name in {metadata.operations[0].name, computed.name}:
                    field = mapping.target_path.removeprefix("Account.")
                    wrapper = "request" if field == "id" else "result"
                    mapping.source_path = f"api.{mapping.operation_name}.response.{wrapper}.{field}"
            for operation in [*metadata.operations[:2], computed]:
                operation.request_entity = "Record"
                operation.operation_parameters = [OperationParameter(
                    name="X-Correlation-Id", location=OperationParameterLocation.HEADER,
                    read_input_role="metadata",
                )]
            project = args.output / profile
            repeat = args.output / (profile + "-repeat")
            for output in (project, repeat):
                report = generate_application(metadata, output, generation_run_id="read-contract-proof",
                                              source_manifest="read-contract/synthetic")
                if report.harness_report is None or not report.harness_report.passed:
                    raise AssertionError("Static harness did not pass")
            if _source_digest(project) != _source_digest(repeat):
                raise AssertionError("Repeated generation changed source")
            console_endpoint = _verify_console_list_endpoint(project, profile)
            test = project / "src/test/java/com/appbuilder/reads/ReadContractRuntimeTest.java"
            test.parent.mkdir(parents=True, exist_ok=True)
            test.write_text(Path("tests/fixtures/read-contract/ReadContractRuntimeTest.java")
                            .read_text().replace("@PAGEABLE@", str(pageable).lower())
                            .replace("@MIXED@", str(mixed).lower()))
            before = _source_digest(project)
            verify_generated_app_independence(project, require_schema_baseline=True)
            database = None if profile == "springboot-legacy-compatible" else postgres.create("readcontract")
            env = _database_env(_jdk_env(java_home), postgres, database)
            output = _run(["mvn", "-B", "-ntp", "-o", "clean", "verify"], cwd=project, env=env, timeout=360)
            (args.output / (profile + "-build.log")).write_text(output)
            counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
            for report in (project / "target/surefire-reports").glob("TEST-*.xml"):
                suite = ET.parse(report).getroot()
                for key in counts:
                    counts[key] += int(suite.get(key, "0"))
            if counts["tests"] < 5 or any(counts[key] for key in ("failures", "errors", "skipped")):
                raise AssertionError(f"Missing, failed or skipped runtime tests: {counts}")
            if _source_digest(project) != before:
                raise AssertionError("Build changed generated sources")
            verify_generated_app_independence(project, require_schema_baseline=True, require_packaged_jar=True)
            receipts.append({"profile": profile, "mixed_crud": mixed, "pageable": pageable,
                             "read_request_entity": "Record: unmapped request-sample placeholder",
                             "read_response_entity": "Account",
                             "response_transport_context": "own-ID/computed nested request.id and result.customerId",
                             "database": "postgresql" if database else "h2", "tests": counts,
                             "source_and_packaged_independence": "passed",
                             "console_list_endpoint": console_endpoint,
                             "console_route_proof": "passed" if console_endpoint else "not-applicable: profile emits no bundled console",
                             "repeat_source_match": True, "source_sha256": before})
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
        (args.output / "receipt.json").write_text(json.dumps(
            {"engine_sha": head, "working_tree_dirty": dirty, "cases": receipts}, indent=2) + "\n")
    finally:
        _close_postgres(postgres)


if __name__ == "__main__":
    main()
