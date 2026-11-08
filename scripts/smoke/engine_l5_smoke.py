#!/usr/bin/env python3
"""Engine L5 acceptance smoke entrypoints.

This runner is intentionally Engine-only.  It exposes suite-callable functions
for the full generated-app runtime leg, the regenerate/apply leg, and the Change
Plan leg while keeping generated output under /tmp and generated apps standalone.
Runtime/Postgres scenarios are skip-guarded so lightweight CI is not broken when
Docker is unavailable.
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Script execution: scripts/smoke is on sys.path.
    import engine_l1_l3_smoke as l1_l3
    from generated_app_independence import verify_generated_app_independence
except ImportError:  # Test/import execution from the repository root.
    from scripts.smoke import engine_l1_l3_smoke as l1_l3
    from scripts.smoke.generated_app_independence import (
        verify_generated_app_independence,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMP_ROOT = Path("/tmp/edgeforge-suite-smoke-engine-l5")
RUNTIME_ROOT = TEMP_ROOT / "runtime"
CHANGE_PLAN_ROOT = TEMP_ROOT / "change-plan"
APPLY_ISOLATION_ROOT = TEMP_ROOT / "apply-isolation"

L1_L3_FIXTURE_ROOT = REPO_ROOT / "scripts" / "smoke" / "fixtures" / "engine-l1-l3"
TEST_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"

POSTGRES_CONTAINER = "edgeforge-suite-smoke-l5-postgres"
APP_CONTAINER = "edgeforge-suite-smoke-l5-app"
POSTGRES_PORT = 15435
APP_PORT = 18199
MOCK_SOAP_PORT = 18200
POSTGRES_DB = "edgeforge_l5"
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "postgres"
POSTGRES_IMAGE = "postgres:16-alpine"
APP_IMAGE = "edgeforge-suite-smoke-l5-generated-app:local"
SOAP_ENVELOPE_MAX_BYTES = 1_048_576
SOAP_PROBE_CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"


class ScenarioSkip(RuntimeError):
    """Raised when an optional external dependency is unavailable."""


@dataclass
class EngineL5ScenarioResult:
    """Structured result returned by suite-callable L5 entrypoints."""

    name: str
    status: str
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)

    @classmethod
    def passed(
        cls,
        name: str,
        steps: list[str],
        *,
        artifacts: dict[str, str] | None = None,
        warnings: list[str] | None = None,
    ) -> EngineL5ScenarioResult:
        return cls(
            name=name,
            status="passed",
            steps=steps,
            warnings=warnings or [],
            artifacts=artifacts or {},
        )

    @classmethod
    def skipped(cls, name: str, reason: str) -> EngineL5ScenarioResult:
        return cls(name=name, status="skipped", warnings=[reason])

    @classmethod
    def failed(cls, name: str, error: str) -> EngineL5ScenarioResult:
        return cls(name=name, status="failed", error=error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "steps": self.steps,
            "warnings": self.warnings,
            "error": self.error,
            "artifacts": self.artifacts,
        }


def run_engine_l5_runtime(
    *,
    keep: bool = False,
    require_services: bool = False,
) -> EngineL5ScenarioResult:
    """Run the generated-app runtime L5 scenario.

    The scenario generates a combined edge-contract fixture, builds the app
    image, runs the app as its non-root Docker user against Postgres and a
    bounded mock SOAP service, and exercises REST, file, XML, inbound SOAP, and
    outbound SOAP paths.
    """

    scenario = "engine-l5-runtime"
    steps: list[str] = []
    try:
        if not _docker_available():
            return _skip_or_fail(
                scenario,
                "Docker is unavailable; skipping generated-app runtime L5 scenario.",
                require_services,
            )

        _prepare_scenario_root(RUNTIME_ROOT)
        fixture_dir = _prepare_combined_edge_contract_fixture(RUNTIME_ROOT / "fixture")
        generated_app = RUNTIME_ROOT / "generated-app"
        input_dir = RUNTIME_ROOT / "inputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        _prepare_runtime_input_files(fixture_dir, input_dir)

        mock_server = _MockSoapServer(MOCK_SOAP_PORT)
        postgres_started = False
        app_started = False
        try:
            mock_server.start()
            _start_postgres_container()
            postgres_started = True
            steps.append("started Postgres container and bounded mock SOAP service")

            _generate_app(fixture_dir / "app-definition.yaml", generated_app, "suite-smoke-l5-runtime")
            steps.append("generated combined edge-contract fixture app")

            _write_soap_transport_header_regression_test(generated_app)
            _run(
                ["mvn", "-q", "-Dtest=SoapMessageFactoryTransportHeaderTest", "test"],
                cwd=generated_app,
            )
            steps.append("proved SOAPAction and Content-Type survive hardened envelope replay")

            _run(["mvn", "-q", "-DskipTests", "package"], cwd=generated_app)
            steps.append("compiled generated app with Maven")

            _build_app_image(generated_app)
            _start_generated_app_container()
            app_started = True
            _wait_for_http(f"http://127.0.0.1:{APP_PORT}/actuator/health", expected_status=200)
            steps.append("started generated app Docker image")

            _assert_container_runs_non_root_and_can_write()
            steps.append("confirmed generated app container runs non-root and writes under /app")

            _assert_standalone_generated_app(generated_app)
            steps.append("confirmed generated app has no Engine/Studio/KS/MCP/TestBench imports")

            _exercise_rest_and_soap(mock_server)
            steps.append("exercised REST create/get plus inbound and outbound SOAP")

            _exercise_file_and_xml_runtime(input_dir)
            steps.append("exercised file ingest/output and XML/XSD ingest/output")

            l1_l3._assert_ka_off_artifacts_absent(RUNTIME_ROOT)
            steps.append("confirmed KA/KS/MCP-off artifact posture")

            artifacts = {
                "generated_app": generated_app.as_posix(),
                "fixture": fixture_dir.as_posix(),
                "app_url": f"http://127.0.0.1:{APP_PORT}",
                "mock_soap_requests": str(mock_server.request_count),
            }
            return EngineL5ScenarioResult.passed(scenario, steps, artifacts=artifacts)
        finally:
            if app_started:
                _remove_container(APP_CONTAINER, check=False)
            if postgres_started:
                _remove_container(POSTGRES_CONTAINER, check=False)
            mock_server.stop()
            if not keep:
                shutil.rmtree(RUNTIME_ROOT, ignore_errors=True)
    except ScenarioSkip as exc:
        return _skip_or_fail(scenario, str(exc), require_services)
    except Exception as exc:  # pragma: no cover - surfaced by manual smoke output.
        return EngineL5ScenarioResult.failed(scenario, str(exc))


def run_engine_l5_regen(
    *,
    keep: bool = False,
    require_services: bool = False,
) -> EngineL5ScenarioResult:
    """Run the regeneration/apply L5 scenario by reusing the Engine L1/L3 runner."""

    scenario = "engine-l5-regenerate"
    if not _docker_available():
        return _skip_or_fail(
            scenario,
            "Docker is unavailable; skipping Postgres-backed regeneration L5 scenario.",
            require_services,
        )
    try:
        args = ["--keep"] if keep else []
        exit_code = l1_l3.main(args)
        if exit_code != 0:
            return EngineL5ScenarioResult.failed(
                scenario,
                f"Engine L1/L3 regeneration runner exited with {exit_code}.",
            )
        steps = [
            "developer-owned service preservation proven by L1/L3 runner",
            "generated ServiceBase refresh and prior Flyway migration immutability proven",
            "schema baseline update and additive migration applied to real Postgres",
            "destructive apply and plan-hash drift refused",
        ]
        return EngineL5ScenarioResult.passed(scenario, steps)
    except Exception as exc:  # pragma: no cover - surfaced by manual smoke output.
        return EngineL5ScenarioResult.failed(scenario, str(exc))


def run_engine_l5_change_plan(*, keep: bool = False) -> EngineL5ScenarioResult:
    """Run the Change Plan L5 scenario without mutating the generated package."""

    scenario = "engine-l5-change-plan"
    steps: list[str] = []
    try:
        _prepare_scenario_root(CHANGE_PLAN_ROOT)
        package_dir = CHANGE_PLAN_ROOT / "generated-app"
        initial_manifest = L1_L3_FIXTURE_ROOT / "initial" / "app-definition.yaml"
        evolved_manifest = L1_L3_FIXTURE_ROOT / "evolved" / "app-definition.yaml"

        _generate_app(initial_manifest, package_dir, "suite-smoke-l5-change-plan")
        steps.append("generated baseline regeneration fixture")

        before = l1_l3._package_snapshot(package_dir)
        plan_a = l1_l3._run_plan(evolved_manifest, package_dir, [])
        plan_b = l1_l3._run_plan(evolved_manifest, package_dir, [])
        after = l1_l3._package_snapshot(package_dir)
        l1_l3._assert(plan_a == plan_b, "Change Plan JSON was not stable")
        l1_l3._assert(plan_a["plan_hash"] == plan_b["plan_hash"], "plan_hash was not stable")
        l1_l3._assert(before == after, "Change Plan dry-run wrote into the package")
        steps.append("dry-run plan stable and read-only")

        initial_plan = l1_l3._run_plan(initial_manifest, package_dir, [])
        l1_l3._assert(
            initial_plan["plan_hash"] != plan_a["plan_hash"],
            "plan_hash did not change when manifest changed",
        )
        steps.append("plan_hash changes when manifest changes")

        l1_l3._assert_package_state_hash_sensitivity(
            source_package=package_dir,
            evolved_manifest=evolved_manifest,
            reference_plan=plan_a,
            command_outputs=[],
        )
        steps.append("package_state_hash changes for package/developer/Flyway drift")

        l1_l3._assert_baseline_hash_sensitivity(
            source_package=package_dir,
            evolved_manifest=evolved_manifest,
            reference_plan=plan_a,
            command_outputs=[],
        )
        steps.append("plan_hash changes when baseline changes")

        l1_l3._assert_fail_closed_classification(plan_a)
        _assert_edge_contract_impact(plan_a)
        steps.append("destructive/unsafe classification and edge-contract impact surfaced")

        artifacts = {
            "generated_app": package_dir.as_posix(),
            "plan_hash": plan_a["plan_hash"],
        }
        if not keep:
            shutil.rmtree(CHANGE_PLAN_ROOT, ignore_errors=True)
        return EngineL5ScenarioResult.passed(scenario, steps, artifacts=artifacts)
    except Exception as exc:
        return EngineL5ScenarioResult.failed(scenario, str(exc))


def run_engine_l5_apply_isolation(*, keep: bool = False) -> EngineL5ScenarioResult:
    """Prove ``appbuilder apply`` is shared-mode/root confined.

    This is the L5 promotion of the unit-level apply isolation checks.  It
    drives the real CLI under shared-mode environment settings and asserts both
    fail-closed negatives and a positive in-root apply write-confinement proof.
    """

    scenario = "engine-l5-apply-isolation"
    steps: list[str] = []
    try:
        _prepare_scenario_root(APPLY_ISOLATION_ROOT)
        layout = _ApplyIsolationLayout(APPLY_ISOLATION_ROOT)

        no_roots_target = APPLY_ISOLATION_ROOT / "no-roots-package"
        before = _file_snapshot(APPLY_ISOLATION_ROOT)
        missing_roots = _run_allow_failure(
            [
                sys.executable,
                "-m",
                "appbuilder.cli",
                "apply",
                "--manifest",
                str(layout.in_root_additive_manifest),
                "--package",
                str(no_roots_target),
                "--approved-plan-hash",
                "irrelevant",
            ],
            cwd=REPO_ROOT,
            env=_apply_isolation_env(shared_mode=True, allowed_root=None),
        )
        l1_l3._assert(missing_roots.returncode != 0, "apply succeeded with no allowed roots")
        l1_l3._assert(
            "EDGEFORGE_MCP_ALLOWED_ROOTS must be set" in missing_roots.stdout,
            "apply no-roots refusal did not mention allowed roots",
        )
        l1_l3._assert(_file_snapshot(APPLY_ISOLATION_ROOT) == before, "apply no-roots refusal wrote files")
        steps.append("apply shared-mode no allowed roots fail-closed")

        shared_env = _apply_isolation_env(shared_mode=True, allowed_root=layout.allowed_root)
        manifest_cases = [
            ("absolute out-of-root manifest", layout.outside_additive_manifest.as_posix(), layout.outside_additive_manifest),
            ("traversal manifest", "../outside/additive/app-definition.yaml", layout.outside_additive_manifest),
            ("symlink manifest", "linked-outside/additive/app-definition.yaml", layout.outside_additive_manifest),
            ("sibling-session manifest", layout.sibling_additive_manifest.as_posix(), layout.sibling_additive_manifest),
        ]
        for label, manifest_arg, plan_manifest in manifest_cases:
            plan = _run_plan_json(plan_manifest, layout.in_root_package)
            before = _file_snapshot(APPLY_ISOLATION_ROOT)
            rejected = _run_allow_failure(
                [
                    sys.executable,
                    "-m",
                    "appbuilder.cli",
                    "apply",
                    "--manifest",
                    manifest_arg,
                    "--package",
                    layout.in_root_package.as_posix(),
                    "--approved-plan-hash",
                    plan["plan_hash"],
                    "--generation-run-id",
                    f"l5-apply-isolation-{label.replace(' ', '-')}",
                ],
                cwd=layout.allowed_root,
                env=shared_env,
            )
            l1_l3._assert(rejected.returncode != 0, f"apply accepted {label}")
            l1_l3._assert(
                "manifest_path must resolve inside an allowed root" in rejected.stdout,
                f"apply manifest rejection did not identify allowed-root violation for {label}",
            )
            l1_l3._assert(_file_snapshot(APPLY_ISOLATION_ROOT) == before, f"apply rejection wrote files for {label}")
        steps.append("apply out-of-root manifest rejected")

        package_cases = [
            ("absolute out-of-root package", layout.outside_package.as_posix(), layout.outside_package),
            ("traversal package", "../outside/package", layout.outside_package),
            ("symlink package", "linked-outside/package", layout.outside_package),
            ("sibling-session package", layout.sibling_package.as_posix(), layout.sibling_package),
        ]
        for label, package_arg, plan_package in package_cases:
            plan = _run_plan_json(layout.in_root_additive_manifest, plan_package)
            before = _file_snapshot(APPLY_ISOLATION_ROOT)
            rejected = _run_allow_failure(
                [
                    sys.executable,
                    "-m",
                    "appbuilder.cli",
                    "apply",
                    "--manifest",
                    layout.in_root_additive_manifest.as_posix(),
                    "--package",
                    package_arg,
                    "--approved-plan-hash",
                    plan["plan_hash"],
                    "--generation-run-id",
                    f"l5-apply-isolation-{label.replace(' ', '-')}",
                ],
                cwd=layout.allowed_root,
                env=shared_env,
            )
            l1_l3._assert(rejected.returncode != 0, f"apply accepted {label}")
            l1_l3._assert(
                "package must resolve inside an allowed root" in rejected.stdout,
                f"apply package rejection did not identify allowed-root violation for {label}",
            )
            l1_l3._assert(_file_snapshot(APPLY_ISOLATION_ROOT) == before, f"apply rejection wrote files for {label}")
        steps.append("apply out-of-root package rejected")

        plan = _run_plan_json(
            layout.in_root_additive_manifest,
            layout.in_root_package,
            cwd=layout.allowed_root,
            env=shared_env,
        )
        before = _file_snapshot(APPLY_ISOLATION_ROOT)
        applied = _run(
            [
                sys.executable,
                "-m",
                "appbuilder.cli",
                "apply",
                "--manifest",
                layout.in_root_additive_manifest.as_posix(),
                "--package",
                layout.in_root_package.as_posix(),
                "--approved-plan-hash",
                plan["plan_hash"],
                "--generation-run-id",
                "l5-apply-isolation-positive",
                "--validate-schema",
            ],
            cwd=layout.allowed_root,
            env=shared_env,
        )
        l1_l3._assert("Applied Change Plan:" in applied.stdout, "positive apply did not report success")
        touched = _touched_paths(before, _file_snapshot(APPLY_ISOLATION_ROOT))
        l1_l3._assert(touched, "positive apply did not touch package files")
        l1_l3._assert(
            all(_path_is_relative_to(path, layout.in_root_package) for path in touched),
            "apply wrote outside the resolved package path",
        )
        steps.append("apply wrote only under resolved package path")

        artifacts = {"apply_isolation_root": APPLY_ISOLATION_ROOT.as_posix()}
        if not keep:
            shutil.rmtree(APPLY_ISOLATION_ROOT, ignore_errors=True)
        return EngineL5ScenarioResult.passed(scenario, steps, artifacts=artifacts)
    except Exception as exc:
        return EngineL5ScenarioResult.failed(scenario, str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Engine L5 acceptance smoke scenarios.")
    parser.add_argument(
        "--scenario",
        choices=("all", "runtime", "regen", "change-plan", "apply-isolation"),
        default="all",
        help="Scenario to run. Runtime/regen require Docker and are skip-guarded by default.",
    )
    parser.add_argument("--keep", action="store_true", help="Retain /tmp smoke output.")
    parser.add_argument(
        "--require-services",
        action="store_true",
        help="Treat unavailable Docker/Postgres runtime dependencies as failures instead of skips.",
    )
    args = parser.parse_args(argv)

    selected = (
        ["runtime", "regen", "change-plan", "apply-isolation"]
        if args.scenario == "all"
        else [args.scenario]
    )
    results: list[EngineL5ScenarioResult] = []
    for scenario in selected:
        if scenario == "runtime":
            result = run_engine_l5_runtime(
                keep=args.keep,
                require_services=args.require_services,
            )
        elif scenario == "regen":
            result = run_engine_l5_regen(
                keep=args.keep,
                require_services=args.require_services,
            )
        elif scenario == "change-plan":
            result = run_engine_l5_change_plan(keep=args.keep)
        else:
            result = run_engine_l5_apply_isolation(keep=args.keep)
        results.append(result)
        prefix = result.status.upper()
        print(f"[{prefix}] {result.name}")
        for step in result.steps:
            print(f"  - {step}")
        for warning in result.warnings:
            print(f"  ! {warning}")
        if result.error:
            print(f"  x {result.error}")

    print(json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True))
    return 1 if any(result.status == "failed" for result in results) else 0


def _skip_or_fail(
    scenario: str,
    reason: str,
    require_services: bool,
) -> EngineL5ScenarioResult:
    if require_services:
        return EngineL5ScenarioResult.failed(scenario, reason)
    return EngineL5ScenarioResult.skipped(scenario, reason)


def _prepare_scenario_root(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


def _prepare_combined_edge_contract_fixture(destination: Path) -> Path:
    """Create a temp combined fixture from proven committed family fixtures."""

    if destination.exists():
        shutil.rmtree(destination)
    for relative in ("upstream", "downstream", "contracts", "mappings", "samples"):
        (destination / relative).mkdir(parents=True, exist_ok=True)

    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/fixed-width-downstream-record-types/upstream/account-api-spec.yaml",
        destination / "upstream/account-api-spec.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/fixed-width-downstream-record-types/upstream/account-mapping.yaml",
        destination / "upstream/account-mapping.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/fixed-width-downstream-record-types/upstream/create-account-request.json",
        destination / "upstream/create-account-request.json",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/fixed-width-downstream-record-types/upstream/create-account-response.json",
        destination / "upstream/create-account-response.json",
    )

    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/fixed-width-inbound-trailer-reconciliation/upstream/account-inbound-layout.yaml",
        destination / "upstream/account-inbound-layout.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/fixed-width-inbound-trailer-reconciliation/upstream/account-inbound-mapping.yaml",
        destination / "upstream/account-inbound-mapping.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/fixed-width-inbound-trailer-reconciliation/upstream/sample-account-inbound.txt",
        destination / "upstream/sample-account-inbound.txt",
    )

    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/csv-inbound-trailer-reconciliation/upstream/account-csv-inbound-layout.yaml",
        destination / "upstream/account-csv-inbound-layout.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/csv-inbound-trailer-reconciliation/upstream/account-csv-inbound-mapping.yaml",
        destination / "upstream/account-csv-inbound-mapping.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/csv-inbound-trailer-reconciliation/upstream/sample-account-inbound.csv",
        destination / "upstream/sample-account-inbound.csv",
    )

    _copy_file(
        TEST_FIXTURE_ROOT / "edgecontracts/xml-xsd/account-roundtrip-runtime/contracts/account.xsd",
        destination / "contracts/account.xsd",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/xml-xsd/account-roundtrip-runtime/upstream/account-inbound-mapping.yaml",
        destination / "upstream/account-xml-inbound-mapping.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/xml-xsd/account-roundtrip-runtime/downstream/account-outbound-mapping.yaml",
        destination / "downstream/account-xml-outbound-mapping.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT / "edgecontracts/xml-xsd/account-roundtrip-runtime/samples/account.xml",
        destination / "samples/account.xml",
    )

    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/fixed-width-downstream-record-types/downstream/account-eod-layout.yaml",
        destination / "downstream/account-eod-layout.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "file-contracts/fixed-width-downstream-record-types/downstream/account-eod-mapping.yaml",
        destination / "downstream/account-eod-mapping.yaml",
    )

    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/upstream/customer-api-spec.yaml",
        destination / "upstream/customer-api-spec.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/upstream/customer-mapping.yaml",
        destination / "upstream/customer-mapping.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/upstream/create-customer-request.json",
        destination / "upstream/create-customer-request.json",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/upstream/customer-response.json",
        destination / "upstream/customer-response.json",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/contracts/customer-service.wsdl",
        destination / "contracts/customer-service.wsdl",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/mappings/customer-soap-operation-mapping.yaml",
        destination / "mappings/customer-soap-operation-mapping.yaml",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/contracts/customer-sync-service.wsdl",
        destination / "contracts/customer-sync-service.wsdl",
    )
    _copy_file(
        TEST_FIXTURE_ROOT
        / "edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/mappings/customer-soap-outbound-canonical-mapping.yaml",
        destination / "mappings/customer-soap-outbound-canonical-mapping.yaml",
    )

    (destination / "app-definition.yaml").write_text(_combined_manifest(), encoding="utf-8")
    return destination


def _combined_manifest() -> str:
    return """app_name: Engine L5 Combined Edge Contract Smoke
bounded_context: edge_l5_smoke
schema_version: "2.0"
app_archetype: crud

upstream_interfaces:
  - name: account-api
    system: CORE
    type: rest-json
    spec: upstream/account-api-spec.yaml
    mapping: upstream/account-mapping.yaml
    operations:
      - name: createAccount
        request_sample: upstream/create-account-request.json
        response_sample: upstream/create-account-response.json
  - name: customer-api
    system: CRM
    type: rest-json
    spec: upstream/customer-api-spec.yaml
    mapping: upstream/customer-mapping.yaml
    operations:
      - name: createCustomer
        request_sample: upstream/create-customer-request.json
        response_sample: upstream/customer-response.json
      - name: getCustomer
        response_sample: upstream/customer-response.json
  - name: account-inbound-file
    system: CORE
    type: file-fixed-width
    version: "1.0"
    spec: upstream/account-inbound-layout.yaml
    mapping: upstream/account-inbound-mapping.yaml
    samples:
      - upstream/sample-account-inbound.txt
  - name: account-csv-inbound-file
    system: CORE
    type: file-csv
    version: "1.0"
    spec: upstream/account-csv-inbound-layout.yaml
    mapping: upstream/account-csv-inbound-mapping.yaml
    samples:
      - upstream/sample-account-inbound.csv
  - name: account-xml-inbound
    system: CORE
    type: xml-xsd
    xsd_path: contracts/account.xsd
    root_element: AccountMessage
    namespace: "urn:edgeforge:examples:account:v1"
    namespace_alias: acct
    mapping: upstream/account-xml-inbound-mapping.yaml
    sample: samples/account.xml
  - name: customer-soap-service
    system: CORE
    type: soap-wsdl
    wsdl_path: contracts/customer-service.wsdl
    service: CustomerService
    port: CustomerServicePort
    mapping: mappings/customer-soap-operation-mapping.yaml

downstream_interfaces:
  - name: account-eod-file
    system: EOD
    type: file-fixed-width
    spec: downstream/account-eod-layout.yaml
    mapping: downstream/account-eod-mapping.yaml
  - name: account-xml-outbound
    system: ARCHIVE
    type: xml-xsd
    xsd_path: contracts/account.xsd
    root_element: AccountMessage
    namespace: "urn:edgeforge:examples:account:v1"
    namespace_alias: acct
    mapping: downstream/account-xml-outbound-mapping.yaml
  - name: customer-sync-client
    system: CUSTOMER_CORE
    type: soap-wsdl
    wsdl_path: contracts/customer-sync-service.wsdl
    service: CustomerSyncService
    port: CustomerSyncServicePort
    mapping: mappings/customer-soap-outbound-canonical-mapping.yaml

target_profile: springboot-enterprise-postgres-java17
"""


def _prepare_runtime_input_files(fixture_dir: Path, input_dir: Path) -> None:
    shutil.copy2(fixture_dir / "upstream/sample-account-inbound.txt", input_dir / "account-fw.txt")
    csv = (fixture_dir / "upstream/sample-account-inbound.csv").read_text(encoding="utf-8")
    csv = csv.replace("11111111-1111-1111-1111-111111111111", "44444444-4444-4444-4444-444444444444")
    csv = csv.replace("22222222-2222-2222-2222-222222222222", "55555555-5555-5555-5555-555555555555")
    (input_dir / "account-csv.csv").write_text(csv, encoding="utf-8")
    xml = (fixture_dir / "samples/account.xml").read_text(encoding="utf-8")
    xml = xml.replace("11111111-1111-1111-1111-111111111111", "33333333-3333-3333-3333-333333333333")
    xml = xml.replace("CHK-001", "XML-333")
    (input_dir / "account.xml").write_text(xml, encoding="utf-8")


def _write_soap_transport_header_regression_test(generated_app: Path) -> Path:
    configs = sorted(
        (generated_app / "src/main/java").rglob("SoapEndpointConfig.java")
    )
    l1_l3._assert(
        len(configs) == 1,
        f"expected one generated SoapEndpointConfig, found {len(configs)}",
    )
    package_line = next(
        line
        for line in configs[0].read_text(encoding="utf-8").splitlines()
        if line.startswith("package ")
    )
    package_name = package_line.removeprefix("package ").removesuffix(";")
    test_path = (
        generated_app
        / "src/test/java"
        / Path(*package_name.split("."))
        / "SoapMessageFactoryTransportHeaderTest.java"
    )
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(
        f"""package {package_name};

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.ws.soap.saaj.SaajSoapMessage;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;
import org.springframework.ws.transport.TransportInputStream;

class SoapMessageFactoryTransportHeaderTest {{

    @Test
    void preservesSoapActionAndContentTypeAcrossHardenedReplay() throws Exception {{
        SoapEndpointConfig config = new SoapEndpointConfig();
        SaajSoapMessageFactory factory = config.edgeForgeSoapMessageFactory(4096);
        factory.afterPropertiesSet();

        SaajSoapMessage message = factory.createWebServiceMessage(
            new HeaderTransportInputStream());

        assertEquals("\\\"urn:getCustomer\\\"", message.getSoapAction());
        assertArrayEquals(
            new String[] {{"text/xml; charset=utf-8"}},
            message.getSaajMessage().getMimeHeaders().getHeader("Content-Type"));
    }}

    private static final class HeaderTransportInputStream extends TransportInputStream {{
        private static final byte[] ENVELOPE = (
            "<?xml version=\\\"1.0\\\" encoding=\\\"UTF-8\\\"?>"
                + "<soapenv:Envelope "
                + "xmlns:soapenv=\\\"http://schemas.xmlsoap.org/soap/envelope/\\\">"
                + "<soapenv:Body/></soapenv:Envelope>")
            .getBytes(StandardCharsets.UTF_8);

        @Override
        protected InputStream createInputStream() {{
            return new ByteArrayInputStream(ENVELOPE);
        }}

        @Override
        public Iterator<String> getHeaderNames() {{
            return List.of("Content-Type", "SOAPAction").iterator();
        }}

        @Override
        public Iterator<String> getHeaders(String name) {{
            if ("Content-Type".equalsIgnoreCase(name)) {{
                return List.of("text/xml; charset=utf-8").iterator();
            }}
            if ("SOAPAction".equalsIgnoreCase(name)) {{
                return List.of("\\\"urn:getCustomer\\\"").iterator();
            }}
            return List.<String>of().iterator();
        }}
    }}
}}
""",
        encoding="utf-8",
    )
    return test_path


def _exercise_rest_and_soap(mock_server: _MockSoapServer) -> None:
    customer = _http_json(
        "POST",
        f"http://127.0.0.1:{APP_PORT}/customers",
        {"customerName": "Ada Lovelace", "status": "ACTIVE"},
        expected_status=(200, 201),
    )
    customer_id = str(customer.get("customerId") or customer.get("id") or "")
    l1_l3._assert(customer_id, "customer REST create did not return an id")

    fetched = _http_json(
        "GET",
        f"http://127.0.0.1:{APP_PORT}/customers/{customer_id}",
        expected_status=(200,),
    )
    l1_l3._assert(fetched.get("status") == "ACTIVE", "customer REST get did not return ACTIVE")

    soap_response = _http_text(
        "POST",
        f"http://127.0.0.1:{APP_PORT}/ws",
        _inbound_soap_envelope(customer_id),
        expected_status=(200,),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "urn:getCustomer",
        },
    )
    l1_l3._assert(customer_id in soap_response, "inbound SOAP response did not contain customer id")
    _assert_inbound_soap_envelope_security(customer_id)

    outbound = _http_json(
        "POST",
        f"http://127.0.0.1:{APP_PORT}/soap/outbound/customer-sync-client/syncCustomer",
        {"id": customer_id},
        expected_status=(200,),
    )
    response = outbound.get("response") or {}
    l1_l3._assert(response.get("resultCode") == "ACCEPTED", "outbound SOAP resultCode mismatch")
    l1_l3._assert(mock_server.request_count > 0, "mock SOAP service did not receive outbound call")


def _assert_inbound_soap_envelope_security(customer_id: str) -> None:
    sentinel = "EDGEFORGE_SOAP_XXE_SENTINEL"
    sentinel_path = "/tmp/edgeforge-soap-xxe-sentinel.txt"
    _docker_exec(
        APP_CONTAINER,
        ["sh", "-c", f"printf '%s' '{sentinel}' > {sentinel_path}"],
    )
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "urn:getCustomer",
    }
    for attack_name, envelope in (
        ("external-entity", _inbound_soap_xxe_envelope(sentinel_path)),
        ("entity-expansion", _inbound_soap_entity_expansion_envelope()),
        ("oversized", _inbound_soap_oversized_envelope()),
    ):
        status, response_body = _http_request(
            "POST",
            f"http://127.0.0.1:{APP_PORT}/ws",
            body=envelope.encode("utf-8"),
            headers=headers,
        )
        l1_l3._assert(
            status == 400,
            f"{attack_name} SOAP envelope expected deterministic HTTP 400: "
            f"status={status}, body={response_body}",
        )
        l1_l3._assert(
            sentinel not in response_body,
            f"{attack_name} SOAP envelope exposed external entity content",
        )
        l1_l3._assert(
            "<" + "soapenv:Fault" in response_body or "<" + "SOAP-ENV:Fault" in response_body,
            f"{attack_name} SOAP envelope did not return a bounded SOAP fault",
        )
        l1_l3._assert(
            "Malformed SOAP/XML request:" in response_body,
            f"{attack_name} SOAP envelope returned an unexpected fault taxonomy",
        )

    health_status, health_body = _http_request(
        "GET",
        f"http://127.0.0.1:{APP_PORT}/actuator/health",
    )
    l1_l3._assert(
        health_status == 200 and '"status":"UP"' in health_body.replace(" ", ""),
        "generated app was not healthy after malicious SOAP envelope probes",
    )
    recovery_status, recovery_body = _http_request(
        "POST",
        f"http://127.0.0.1:{APP_PORT}/ws",
        body=_inbound_soap_envelope(customer_id).encode("utf-8"),
        headers=headers,
    )
    l1_l3._assert(
        recovery_status == 200 and customer_id in recovery_body,
        "valid SOAP request failed after malicious envelope probes",
    )


def _exercise_file_and_xml_runtime(input_dir: Path) -> None:
    _docker_exec(APP_CONTAINER, ["mkdir", "-p", "/app/smoke/file-ingest", "/app/smoke/xml-ingest", "/app/smoke/xml-output"])
    _run(["docker", "cp", str(input_dir / "account-fw.txt"), f"{APP_CONTAINER}:/app/smoke/file-ingest/account-fw.txt"], cwd=REPO_ROOT)
    _run(["docker", "cp", str(input_dir / "account-csv.csv"), f"{APP_CONTAINER}:/app/smoke/file-ingest/account-csv.csv"], cwd=REPO_ROOT)
    _run(["docker", "cp", str(input_dir / "account.xml"), f"{APP_CONTAINER}:/app/smoke/xml-ingest/account.xml"], cwd=REPO_ROOT)

    xml_ingest = _http_json(
        "POST",
        f"http://127.0.0.1:{APP_PORT}/xml/ingest/account-xml-inbound",
        {"path": "account.xml"},
        expected_status=(200,),
    )
    l1_l3._assert(xml_ingest.get("persistedCount") == 1, "XML ingest did not persist one row")

    xml_output = _http_json(
        "POST",
        f"http://127.0.0.1:{APP_PORT}/xml/output/account-xml-outbound",
        {},
        expected_status=(200,),
    )
    l1_l3._assert(xml_output.get("rowCount", 0) >= 1, "XML output did not write rows")
    _docker_exec(APP_CONTAINER, ["sh", "-c", "grep -R '33333333-3333-3333-3333-333333333333' /app/smoke/xml-output"])

    fixed_ingest = _http_json(
        "POST",
        f"http://127.0.0.1:{APP_PORT}/files/ingest/account-inbound-file",
        {"path": "account-fw.txt"},
        expected_status=(200,),
    )
    l1_l3._assert(fixed_ingest.get("persistedCount") == 2, "fixed-width ingest did not persist two rows")

    csv_ingest = _http_json(
        "POST",
        f"http://127.0.0.1:{APP_PORT}/files/ingest/account-csv-inbound-file",
        {"path": "account-csv.csv"},
        expected_status=(200,),
    )
    l1_l3._assert(csv_ingest.get("persistedCount") == 2, "CSV ingest did not persist two rows")

    batch = _http_json(
        "POST",
        f"http://127.0.0.1:{APP_PORT}/batch/run/accountEodJob",
        {},
        expected_status=(200,),
    )
    l1_l3._assert(
        "COMPLETED" in json.dumps(batch),
        f"accountEodJob did not complete successfully: {batch}",
    )
    output_listing = _docker_exec(APP_CONTAINER, ["sh", "-c", "find /app -maxdepth 3 -type f -name '*.dat' -print"])
    l1_l3._assert("account" in output_listing.lower(), "fixed-width EOD output file was not written")


def _assert_edge_contract_impact(plan: dict[str, Any]) -> None:
    impacts = plan.get("edge_contract_impact") or []
    l1_l3._assert(impacts, "Change Plan did not surface edge-contract impact")
    l1_l3._assert(
        any(
            impact.get("contract_name") == "widget-api"
            and impact.get("entity") == "Widget"
            and impact.get("field") == "status"
            for impact in impacts
        ),
        "Change Plan did not report Widget.status contract impact",
    )


def _generate_app(manifest: Path, output: Path, run_id: str) -> None:
    l1_l3._run(
        [
            sys.executable,
            "-m",
            "appbuilder.cli",
            "generate",
            "--manifest",
            str(manifest),
            "--output",
            str(output),
            "--generation-run-id",
            run_id,
            "--validate-schema",
        ],
        cwd=REPO_ROOT,
    )


def _build_app_image(generated_app: Path) -> None:
    _run(["docker", "build", "-t", APP_IMAGE, "."], cwd=generated_app)


def _start_generated_app_container() -> None:
    _remove_container(APP_CONTAINER, check=False)
    command = [
        "docker",
        "run",
        "--name",
        APP_CONTAINER,
        "--add-host=host.docker.internal:host-gateway",
        "-p",
        f"{APP_PORT}:8080",
        "-e",
        f"SPRING_DATASOURCE_URL=jdbc:postgresql://host.docker.internal:{POSTGRES_PORT}/{POSTGRES_DB}",
        "-e",
        f"SPRING_DATASOURCE_USERNAME={POSTGRES_USER}",
        "-e",
        f"SPRING_DATASOURCE_PASSWORD={POSTGRES_PASSWORD}",
        "-e",
        "SPRING_BATCH_JDBC_INITIALIZE_SCHEMA=always",
        "-e",
        "APP_FILE_INGEST_BASE_DIR=/app/smoke/file-ingest",
        "-e",
        "APP_XML_INGEST_BASE_DIR=/app/smoke/xml-ingest",
        "-e",
        "APP_XML_OUTPUT_BASE_DIR=/app/smoke/xml-output",
        "-e",
        f"APP_SOAP_CLIENTS_CUSTOMER_SYNC_CLIENT_URI=http://host.docker.internal:{MOCK_SOAP_PORT}/customer-sync",
        "-d",
        APP_IMAGE,
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0 and "host-gateway" in result.stdout:
        command = [part for part in command if part != "--add-host=host.docker.internal:host-gateway"]
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    if result.returncode != 0:
        raise ScenarioSkip(f"generated app Docker container could not start: {result.stdout}")


def _assert_container_runs_non_root_and_can_write() -> None:
    uid = _docker_exec(APP_CONTAINER, ["id", "-u"]).strip()
    l1_l3._assert(uid and uid != "0", f"generated app container runs as root uid={uid!r}")
    _docker_exec(APP_CONTAINER, ["sh", "-c", "mkdir -p /app/l5-non-root-write-proof && test -d /app/l5-non-root-write-proof"])


def _start_postgres_container() -> None:
    _remove_container(POSTGRES_CONTAINER, check=False)
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--name",
            POSTGRES_CONTAINER,
            "-e",
            f"POSTGRES_PASSWORD={POSTGRES_PASSWORD}",
            "-e",
            f"POSTGRES_DB={POSTGRES_DB}",
            "-p",
            f"{POSTGRES_PORT}:5432",
            "-d",
            POSTGRES_IMAGE,
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise ScenarioSkip(f"Postgres container unavailable: {completed.stdout.strip()}")
    for _ in range(45):
        ready = subprocess.run(
            [
                "docker",
                "exec",
                POSTGRES_CONTAINER,
                "pg_isready",
                "-U",
                POSTGRES_USER,
                "-d",
                POSTGRES_DB,
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if ready.returncode == 0:
            return
        time.sleep(1)
    raise ScenarioSkip(f"Postgres container {POSTGRES_CONTAINER} did not become ready")


def _remove_container(name: str, *, check: bool = True) -> None:
    subprocess.run(
        ["docker", "rm", "-f", name],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def _docker_available() -> bool:
    try:
        completed = subprocess.run(
            ["docker", "info"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _docker_exec(container: str, command: list[str]) -> str:
    completed = _run(["docker", "exec", container, *command], cwd=REPO_ROOT)
    return completed.stdout


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}"
        )
    return completed


def _run_allow_failure(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _run_plan_json(
    manifest: Path,
    package_dir: Path,
    *,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    completed = _run(
        [
            sys.executable,
            "-m",
            "appbuilder.cli",
            "plan",
            "--manifest",
            manifest.as_posix(),
            "--package",
            package_dir.as_posix(),
            "--validate-schema",
        ],
        cwd=cwd,
        env=env or _apply_isolation_env(shared_mode=False, allowed_root=None),
    )
    return json.loads(completed.stdout)


def _apply_isolation_env(*, shared_mode: bool, allowed_root: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        REPO_ROOT.as_posix()
        if not existing_pythonpath
        else f"{REPO_ROOT.as_posix()}{os.pathsep}{existing_pythonpath}"
    )
    if shared_mode:
        env["EDGEFORGE_SHARED_MODE"] = "1"
    else:
        env.pop("EDGEFORGE_SHARED_MODE", None)
    if allowed_root is None:
        env.pop("EDGEFORGE_MCP_ALLOWED_ROOTS", None)
    else:
        env["EDGEFORGE_MCP_ALLOWED_ROOTS"] = allowed_root.resolve().as_posix()
    return env


class _ApplyIsolationLayout:
    def __init__(self, root: Path) -> None:
        self.allowed_root = root / "session-a"
        self.sibling_root = root / "session-b"
        self.outside_root = root / "outside"
        for path in (self.allowed_root, self.sibling_root, self.outside_root):
            path.mkdir(parents=True, exist_ok=True)

        self.in_root_initial_manifest = self.allowed_root / "initial/app-definition.yaml"
        self.in_root_additive_manifest = self.allowed_root / "additive/app-definition.yaml"
        self.outside_additive_manifest = self.outside_root / "additive/app-definition.yaml"
        self.sibling_additive_manifest = self.sibling_root / "additive/app-definition.yaml"

        _copy_apply_fixture("initial", self.allowed_root / "initial")
        _copy_apply_fixture("additive", self.allowed_root / "additive")
        _copy_apply_fixture("additive", self.outside_root / "additive")
        _copy_apply_fixture("additive", self.sibling_root / "additive")
        (self.allowed_root / "linked-outside").symlink_to(
            self.outside_root,
            target_is_directory=True,
        )

        self.in_root_package = self.allowed_root / "package"
        self.outside_package = self.outside_root / "package"
        self.sibling_package = self.sibling_root / "package"
        for package in (self.in_root_package, self.outside_package, self.sibling_package):
            _generate_apply_baseline(self.in_root_initial_manifest, package)


def _copy_apply_fixture(name: str, target: Path) -> None:
    shutil.copytree(L1_L3_FIXTURE_ROOT / name, target)


def _generate_apply_baseline(manifest: Path, package_dir: Path) -> None:
    _run(
        [
            sys.executable,
            "-m",
            "appbuilder.cli",
            "generate",
            "--manifest",
            manifest.as_posix(),
            "--output",
            package_dir.as_posix(),
            "--generation-run-id",
            "l5-apply-isolation-baseline",
            "--validate-schema",
        ],
        cwd=REPO_ROOT,
        env=_apply_isolation_env(shared_mode=False, allowed_root=None),
    )


def _file_snapshot(root: Path) -> dict[Path, bytes]:
    if not root.exists():
        return {}
    return {
        path.resolve(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _touched_paths(before: dict[Path, bytes], after: dict[Path, bytes]) -> set[Path]:
    return {
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    }


def _path_is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _wait_for_http(url: str, *, expected_status: int, timeout_seconds: int = 90) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            status, _ = _http_request("GET", url)
            if status == expected_status:
                return
            last_error = f"status={status}"
        except Exception as exc:  # noqa: BLE001 - retry probe.
            last_error = str(exc)
        time.sleep(1)
    raise AssertionError(f"{url} did not become ready: {last_error}")


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    expected_status: tuple[int, ...],
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    status, response_body = _http_request(method, url, body=body, headers=headers)
    l1_l3._assert(
        status in expected_status,
        f"{method} {url} expected {expected_status}, got {status}: {response_body}",
    )
    if not response_body:
        return {}
    return json.loads(response_body)


def _http_text(
    method: str,
    url: str,
    payload: str,
    *,
    expected_status: tuple[int, ...],
    headers: dict[str, str],
) -> str:
    status, response_body = _http_request(
        method,
        url,
        body=payload.encode("utf-8"),
        headers=headers,
    )
    l1_l3._assert(
        status in expected_status,
        f"{method} {url} expected {expected_status}, got {status}: {response_body}",
    )
    return response_body


def _http_request(
    method: str,
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _inbound_soap_envelope(customer_id: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:tns="urn:edgeforge:examples:customer-soap:v1">
  <soapenv:Body>
    <tns:GetCustomerRequest>
      <tns:customerId>{customer_id}</tns:customerId>
    </tns:GetCustomerRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""


def _inbound_soap_xxe_envelope(sentinel_path: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE soapenv:Envelope [
  <!ENTITY xxe SYSTEM "file://{sentinel_path}">
]>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:tns="urn:edgeforge:examples:customer-soap:v1">
  <soapenv:Body>
    <tns:GetCustomerRequest>
      <tns:customerId>&xxe;</tns:customerId>
    </tns:GetCustomerRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""


def _inbound_soap_entity_expansion_envelope() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE soapenv:Envelope [
  <!ENTITY a "1234567890">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
  <!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">
  <!ENTITY e "&d;&d;&d;&d;&d;&d;&d;&d;&d;&d;">
]>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:tns="urn:edgeforge:examples:customer-soap:v1">
  <soapenv:Body>
    <tns:GetCustomerRequest>
      <tns:customerId>&e;</tns:customerId>
    </tns:GetCustomerRequest>
  </soapenv:Body>
</soapenv:Envelope>
"""


def _inbound_soap_oversized_envelope() -> str:
    return _inbound_soap_envelope("A" * SOAP_ENVELOPE_MAX_BYTES)


class _MockSoapServer:
    def __init__(self, port: int) -> None:
        self.port = port
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.request_count = 0
        self.last_request = ""

    def start(self) -> None:
        handler_owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib override.
                length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(length).decode("utf-8")
                handler_owner.request_count += 1
                handler_owner.last_request = body
                response = _outbound_soap_response().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/xml; charset=utf-8")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature.
                return

        try:
            self._server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError as exc:
            raise ScenarioSkip(f"mock SOAP service unavailable on port {self.port}: {exc}") from exc
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        _wait_for_port("127.0.0.1", self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def _outbound_soap_response() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <ns2:SyncCustomerResponse xmlns:ns2="urn:edgeforge:examples:customer-sync:v1">
      <ns2:resultCode>ACCEPTED</ns2:resultCode>
      <ns2:message>Synced by L5 mock SOAP service</ns2:message>
    </ns2:SyncCustomerResponse>
  </soapenv:Body>
</soapenv:Envelope>
"""


def _wait_for_port(host: str, port: int, timeout_seconds: int = 10) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.1)
    raise ScenarioSkip(f"service {host}:{port} did not become reachable")


def _assert_standalone_generated_app(package_dir: Path) -> None:
    verify_generated_app_independence(
        package_dir,
        require_packaged_jar=True,
        require_schema_baseline=True,
    )


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


if __name__ == "__main__":
    raise SystemExit(main())
