#!/usr/bin/env python3
"""Top-level EdgeForge Suite L5 acceptance orchestrator.

The orchestrator is intentionally thin: it locates sibling repos, invokes the
merged Engine / Studio / KS L5 leaves, normalizes their structured results, and
emits the §8 pass/fail checklist plus a cross-repo SHA-pin manifest.  It does
not reimplement product checks or wire into per-PR CI.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Script execution: scripts/smoke is on sys.path.
    import engine_l5_smoke
except ImportError:  # Test/import execution from the repository root.
    from scripts.smoke import engine_l5_smoke


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMP_PREFIX = "edgeforge-suite-smoke-l5-orchestrator-"
CHANGE_PLAN_FAILURE_MARKERS = (
    "plan-hash drift refused",
    "destructive apply",
    "destructive/unsafe classification",
)
STUDIO_REGEN_APPLY_SCENARIO = "regen-preview approve-apply"
EXPECTED_STUDIO_SCENARIOS = {
    "multi-session isolation",
    "Studio-to-Engine per-session outputs",
    "shared-mode security",
    "KS/KA per-session isolation",
    "Engine fail-closed out-of-root",
    "KA-OFF strict",
    "combined edge-contract author-generate",
    STUDIO_REGEN_APPLY_SCENARIO,
}
STUDIO_REGEN_APPLY_SESSIONS = ("alpha", "beta")
STUDIO_REGEN_APPLY_TOP_LEVEL_TRUE_FLAGS = {
    "ok",
    "ka_off_silent",
    "distinct_workspaces",
    "distinct_generated_outputs",
    "distinct_managed_packages",
    "alpha_under_workspace",
    "beta_under_workspace",
}
EXPECTED_KS_CHECKS = {
    "per_session_db_isolation",
    "project_scoped_search_no_bleed",
    "explicit_cross_project_filter_no_bleed",
    "allowed_root_rejects_outside_read",
    "shared_mode_requires_explicit_db_path",
    "results_do_not_leak_absolute_paths",
}
STUDIO_NO_LEAK_SCENARIOS = {
    "absolute local path leak scan",
    "absolute local path no-leak",
    "no absolute local path leaks",
}
STUDIO_ARTIFACT_DIR_KEYS = {
    "export_a",
    "export_b",
    "export_package",
    "generated_a",
    "generated_b",
    "generated_dir",
    "generated_output",
    "initial_managed_package",
    "managed_package",
    "old_managed_package",
    "output_a",
    "output_b",
    "package_dir",
    "refreshed_package",
    "workspace_root",
}
STUDIO_REQUIRED_ARTIFACT_ROOTS = {
    "combined edge-contract author-generate": {"generated_dir", "package_dir"},
    STUDIO_REGEN_APPLY_SCENARIO: {
        "alpha.workspace_root",
        "alpha.export_package",
        "alpha.generated_output",
        "alpha.initial_managed_package",
        "alpha.refreshed_package",
        "beta.workspace_root",
        "beta.export_package",
        "beta.generated_output",
        "beta.initial_managed_package",
        "beta.refreshed_package",
    },
}
LOCAL_PATH_LEAK_MARKERS = (
    "/" + "Users/",
    "/private/tmp/",
    "/var/folders/",
)
ARTIFACT_SCAN_SKIP_DIRS = {
    ".git",
    ".gradle",
    ".mvn",
    "__pycache__",
    "build",
    "node_modules",
    "target",
}
ARTIFACT_SCAN_MAX_BYTES = 2_000_000


@dataclass
class OrchestratorResult:
    name: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def ok(self) -> bool:
        return self.status == "passed"

    def skipped(self) -> bool:
        return self.status == "skipped"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "warnings": self.warnings,
            "error": self.error,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the EdgeForge Suite L5 acceptance orchestrator.")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Retain /tmp/edgeforge-suite-smoke-l5-orchestrator-* output.",
    )
    parser.add_argument(
        "--require-sibling-repos",
        action="store_true",
        help="Fail instead of skip when EDGEFORGE_STUDIO_REPO or EDGEFORGE_KS_REPO is missing.",
    )
    parser.add_argument(
        "--require-services",
        action="store_true",
        help="Pass through to Engine L5 leaves so Docker/Postgres unavailability fails instead of skips.",
    )
    parser.add_argument(
        "--allow-skipped-success",
        action="store_true",
        help="Exit 0 for a skipped discovery run. Acceptance gates should not use this.",
    )
    args = parser.parse_args(argv)

    root = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX, dir="/tmp"))
    try:
        report = run_suite_l5_acceptance(
            root=root,
            keep=args.keep,
            require_sibling_repos=args.require_sibling_repos,
            require_services=args.require_services,
        )
        print(_human_report(report))
        print(json.dumps(report, indent=2, sort_keys=True))
        if not args.keep and report.get("status") in {"passed", "skipped"}:
            shutil.rmtree(root, ignore_errors=True)
        if report.get("status") == "passed":
            return 0
        if report.get("status") == "skipped" and args.allow_skipped_success:
            return 0
        return 1
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"[INFO] retained L5 orchestrator root for triage: {root}", file=sys.stderr)
        return 1


def run_suite_l5_acceptance(
    *,
    root: Path,
    keep: bool = False,
    require_sibling_repos: bool = False,
    require_services: bool = False,
) -> dict[str, Any]:
    """Run all suite L5 leaves and return a normalized report."""

    root.mkdir(parents=True, exist_ok=True)
    studio_repo = _repo_from_env("EDGEFORGE_STUDIO_REPO")
    ks_repo = _repo_from_env("EDGEFORGE_KS_REPO")
    missing = [
        name
        for name, repo in (
            ("EDGEFORGE_STUDIO_REPO", studio_repo),
            ("EDGEFORGE_KS_REPO", ks_repo),
        )
        if repo is None
    ]
    if missing:
        message = (
            "Suite L5 orchestrator requires sibling repo env vars: "
            + ", ".join(missing)
        )
        if require_sibling_repos:
            return _empty_report(root=root, status="failed", error=message)
        return _empty_report(root=root, status="skipped", warnings=[message])

    assert studio_repo is not None
    assert ks_repo is not None

    manifest = _sha_pin_manifest(root=root, studio_repo=studio_repo, ks_repo=ks_repo)
    results = [
        _run_engine_runtime(require_services=require_services),
        _run_engine_regen(require_services=require_services),
        _run_engine_change_plan(),
        _run_engine_apply_isolation(),
        _run_studio_l5(studio_repo=studio_repo, ks_repo=ks_repo, root=root / "studio"),
        _run_ks_l5(ks_repo=ks_repo),
    ]
    checklist = _build_hard_fail_checklist(results)
    warnings = _collect_warnings(results)
    hard_failures = [item for item in checklist if item["status"] == "fail"]
    skipped = [result for result in results if result.skipped()]
    status = "failed" if hard_failures else "skipped" if skipped else "passed"

    report = {
        "status": status,
        "root": root.as_posix(),
        "sha_manifest": manifest,
        "results": [result.to_dict() for result in results],
        "checklist": checklist,
        "warnings": warnings,
    }
    _write_json(root / "l5-run-manifest.json", manifest)
    _write_json(root / "l5-report.json", report)
    if not keep and status == "passed":
        # Keep the report available through stdout; remove temp files on clean pass per §12.
        pass
    return report


def _run_engine_runtime(*, require_services: bool) -> OrchestratorResult:
    result = engine_l5_smoke.run_engine_l5_runtime(require_services=require_services)
    return _from_engine_result("engine.runtime", result)


def _run_engine_regen(*, require_services: bool) -> OrchestratorResult:
    result = engine_l5_smoke.run_engine_l5_regen(require_services=require_services)
    return _from_engine_result("engine.regenerate", result)


def _run_engine_change_plan() -> OrchestratorResult:
    result = engine_l5_smoke.run_engine_l5_change_plan()
    return _from_engine_result("engine.change_plan", result)


def _run_engine_apply_isolation() -> OrchestratorResult:
    result = engine_l5_smoke.run_engine_l5_apply_isolation()
    return _from_engine_result("engine.apply_isolation", result)


def _from_engine_result(name: str, result: Any) -> OrchestratorResult:
    payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    status = str(payload.get("status") or "failed")
    return OrchestratorResult(
        name=name,
        status=status,
        detail=payload,
        warnings=list(payload.get("warnings") or []),
        error=payload.get("error"),
    )


def _run_studio_l5(*, studio_repo: Path, ks_repo: Path, root: Path) -> OrchestratorResult:
    ks_command = _pinned_ks_python(ks_repo, env=os.environ)
    engine_command = _engine_mcp_python()
    env = os.environ.copy()
    env.update(
        {
            "EDGEFORGE_STUDIO_ENGINE_REPO": REPO_ROOT.as_posix(),
            "EDGEFORGE_STUDIO_ENGINE_MCP_COMMAND": engine_command.as_posix(),
            "EDGEFORGE_STUDIO_KS_COMMAND": ks_command.as_posix(),
            "EDGEFORGE_STUDIO_KS_REPO": ks_repo.resolve().as_posix(),
            "EDGEFORGE_STUDIO_REGEN_PREVIEW_ENABLED": "true",
            "EDGEFORGE_SHARED_MODE": "1",
        }
    )
    code = (
        "import json; "
        "from pathlib import Path; "
        "from app.integrations.ks_integration import _ks_command, _ks_repo; "
        "from tests.smoke.l5_driver import run_studio_l5_acceptance; "
        "_studio_ks_repo = _ks_repo(); "
        "_studio_ks_command = _ks_command(_studio_ks_repo); "
        f"_payload = run_studio_l5_acceptance(root=Path({str(root)!r})); "
        "_payload['studio_resolved_ks'] = {"
        "'repo': str(_studio_ks_repo.expanduser().resolve(strict=False)), "
        "'command': str(Path(_studio_ks_command).expanduser().resolve(strict=False)), "
        "'source': 'app.integrations.ks_integration'"
        "}; "
        "print(json.dumps(_payload, sort_keys=True))"
    )
    completed = _run_python_snippet(
        studio_repo,
        code,
        env=env,
        python_env_var="EDGEFORGE_STUDIO_PYTHON",
    )
    if completed.returncode != 0:
        return OrchestratorResult(
            name="studio.l5",
            status="failed",
            error=completed.stdout.strip(),
        )
    payload = _loads_last_json_line(completed.stdout)
    ks_pin = _ks_pin_detail(ks_repo=ks_repo, command=ks_command, env=os.environ)
    payload["orchestrator_pinned_ks"] = ks_pin
    if not ks_pin["valid"]:
        return OrchestratorResult(
            name="studio.l5",
            status="failed",
            detail=payload,
            error=ks_pin["error"],
        )
    validation_error = _validate_studio_payload(payload)
    artifact_scan = _scan_studio_artifacts_for_absolute_paths(payload)
    payload["orchestrator_artifact_scan"] = artifact_scan
    if validation_error:
        return OrchestratorResult(
            name="studio.l5",
            status="failed",
            detail=payload,
            error=validation_error,
        )
    studio_ks_error = _validate_studio_ks_resolution(
        payload.get("studio_resolved_ks"),
        ks_repo=ks_repo,
        expected_command=ks_command,
    )
    if studio_ks_error:
        return OrchestratorResult(
            name="studio.l5",
            status="failed",
            detail=payload,
            error=studio_ks_error,
        )
    if not artifact_scan["ok"]:
        return OrchestratorResult(
            name="studio.l5",
            status="failed",
            detail=payload,
            error=artifact_scan["error"],
        )
    scenarios = payload["scenarios"]
    ok = all(bool(scenario.get("ok")) for scenario in scenarios)
    return OrchestratorResult(
        name="studio.l5",
        status="passed" if ok else "failed",
        detail=payload,
        error=None if ok else "one or more Studio L5 scenarios failed",
    )


def _run_ks_l5(*, ks_repo: Path) -> OrchestratorResult:
    code = (
        "import json; "
        "from scripts.run_ks_l5_isolation import run_ks_l5_isolation; "
        "print(json.dumps(run_ks_l5_isolation(), sort_keys=True))"
    )
    completed = _run_python_snippet(
        ks_repo,
        code,
        env=os.environ.copy(),
        python_env_var="EDGEFORGE_KS_PYTHON",
    )
    if completed.returncode != 0:
        return OrchestratorResult(
            name="ks.l5",
            status="failed",
            error=completed.stdout.strip(),
        )
    payload = _loads_last_json_line(completed.stdout)
    validation_error = _validate_ks_payload(payload)
    if validation_error:
        return OrchestratorResult(
            name="ks.l5",
            status="failed",
            detail=payload,
            error=validation_error,
        )
    ok = bool(payload.get("success"))
    return OrchestratorResult(
        name="ks.l5",
        status="passed" if ok else "failed",
        detail=payload,
        error=None if ok else "one or more KS L5 checks failed",
    )


def _pinned_ks_python(ks_repo: Path, *, env: dict[str, str]) -> Path:
    configured = env.get("EDGEFORGE_KS_PYTHON")
    if configured:
        return Path(configured).expanduser()
    return ks_repo.resolve() / ".venv" / "bin" / "python"


def _engine_mcp_python() -> Path:
    candidate = REPO_ROOT / ".venv" / "bin" / "python"
    if candidate.exists():
        return candidate.resolve()
    return Path(sys.executable).resolve()


def _ks_pin_detail(*, ks_repo: Path, command: Path, env: dict[str, str]) -> dict[str, Any]:
    repo = ks_repo.resolve()
    command_path = command.expanduser()
    configured = env.get("EDGEFORGE_KS_PYTHON")
    command_matches_env = bool(configured and command_path == Path(configured).expanduser())
    command_under_repo = _path_is_relative_to(command_path, repo)
    valid = command_matches_env or command_under_repo
    error = None
    if not valid:
        error = (
            "Studio KS command is not pinned to EDGEFORGE_KS_REPO or EDGEFORGE_KS_PYTHON: "
            f"{command_path.as_posix()}"
        )
    return {
        "command": command_path.as_posix(),
        "command_from_edgeforge_ks_python": command_matches_env,
        "command_under_ks_repo": command_under_repo,
        "error": error,
        "ks_repo": repo.as_posix(),
        "valid": valid,
    }


def _validate_studio_ks_resolution(
    resolution: Any,
    *,
    ks_repo: Path,
    expected_command: Path,
) -> str | None:
    if not isinstance(resolution, dict):
        return "Studio L5 payload did not report the KS command/repo selected by Studio"

    actual_repo = resolution.get("repo")
    actual_command = resolution.get("command")
    if not isinstance(actual_repo, str) or not actual_repo:
        return "Studio L5 payload reported a malformed KS repo"
    if not isinstance(actual_command, str) or not actual_command:
        return "Studio L5 payload reported a malformed KS command"

    expected_repo = ks_repo.expanduser().resolve(strict=False)
    reported_repo = Path(actual_repo).expanduser().resolve(strict=False)
    if reported_repo != expected_repo:
        return (
            "Studio resolved KS repo does not match EDGEFORGE_KS_REPO: "
            f"{reported_repo.as_posix()} != {expected_repo.as_posix()}"
        )

    expected = expected_command.expanduser().resolve(strict=False)
    reported = Path(actual_command).expanduser().resolve(strict=False)
    if reported != expected:
        return (
            "Studio resolved KS command does not match the orchestrator-pinned command: "
            f"{reported.as_posix()} != {expected.as_posix()}"
        )

    return None


def _path_is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve(strict=False).relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _validate_ks_payload(payload: dict[str, Any]) -> str | None:
    if payload.get("tool_name") != "run_ks_l5_isolation":
        return "KS L5 payload did not come from run_ks_l5_isolation"
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        return "KS L5 payload did not contain a non-empty checks list"
    names = {
        check.get("name")
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }
    missing = sorted(EXPECTED_KS_CHECKS - names)
    if missing:
        return "KS L5 payload is missing expected check(s): " + ", ".join(missing)
    malformed = [
        str(index)
        for index, check in enumerate(checks)
        if not isinstance(check, dict)
        or not isinstance(check.get("name"), str)
        or "success" not in check
    ]
    if malformed:
        return "KS L5 payload contains malformed check entry index(es): " + ", ".join(malformed)
    failed = sorted(str(check["name"]) for check in checks if not bool(check.get("success")))
    if failed:
        return "KS L5 payload reported failed check(s): " + ", ".join(failed)
    if not bool(payload.get("success")):
        return "KS L5 payload success flag is false"
    return None


def _validate_studio_payload(payload: dict[str, Any]) -> str | None:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return "Studio L5 payload did not contain a non-empty scenarios list"
    names = {
        scenario.get("scenario")
        for scenario in scenarios
        if isinstance(scenario, dict) and isinstance(scenario.get("scenario"), str)
    }
    missing = sorted(EXPECTED_STUDIO_SCENARIOS - names)
    if missing:
        return "Studio L5 payload is missing expected scenario(s): " + ", ".join(missing)
    malformed = [
        str(index)
        for index, scenario in enumerate(scenarios)
        if not isinstance(scenario, dict)
        or not isinstance(scenario.get("scenario"), str)
        or "ok" not in scenario
    ]
    if malformed:
        return "Studio L5 payload contains malformed scenario entry index(es): " + ", ".join(malformed)
    artifact_contract_error = _validate_studio_artifact_root_contract(scenarios)
    if artifact_contract_error:
        return artifact_contract_error
    regen_apply_error = _validate_studio_regen_apply_contract(scenarios)
    if regen_apply_error:
        return regen_apply_error
    return None


def _validate_studio_artifact_root_contract(scenarios: list[Any]) -> str | None:
    for scenario_name, required_paths in sorted(STUDIO_REQUIRED_ARTIFACT_ROOTS.items()):
        scenario = _studio_scenario(scenarios, scenario_name)
        if scenario is None:
            continue
        detail = scenario.get("detail")
        if not isinstance(detail, dict):
            return f"Studio L5 scenario '{scenario_name}' did not expose a detail object"
        missing = sorted(path for path in required_paths if not _json_path_get(detail, path))
        if missing:
            return (
                f"Studio L5 scenario '{scenario_name}' is missing artifact root key(s): "
                + ", ".join(missing)
            )
    return None


def _validate_studio_regen_apply_contract(scenarios: list[Any]) -> str | None:
    scenario = _studio_scenario(scenarios, STUDIO_REGEN_APPLY_SCENARIO)
    if scenario is None:
        return None
    detail = scenario.get("detail")
    if not isinstance(detail, dict):
        return f"Studio L5 scenario '{STUDIO_REGEN_APPLY_SCENARIO}' did not expose a detail object"

    false_top_level = sorted(
        flag for flag in STUDIO_REGEN_APPLY_TOP_LEVEL_TRUE_FLAGS if not bool(detail.get(flag))
    )
    if false_top_level:
        return (
            f"Studio L5 scenario '{STUDIO_REGEN_APPLY_SCENARIO}' did not prove top-level flag(s): "
            + ", ".join(false_top_level)
        )

    if detail.get("ks_calls") != []:
        return f"Studio L5 scenario '{STUDIO_REGEN_APPLY_SCENARIO}' reported KS/KA calls"
    if bool(detail.get("alpha_cross_bleed")) or bool(detail.get("beta_cross_bleed")):
        return f"Studio L5 scenario '{STUDIO_REGEN_APPLY_SCENARIO}' reported cross-session bleed"

    for session_name in STUDIO_REGEN_APPLY_SESSIONS:
        session = detail.get(session_name)
        if not isinstance(session, dict):
            return (
                f"Studio L5 scenario '{STUDIO_REGEN_APPLY_SCENARIO}' did not expose "
                f"{session_name} session detail"
            )
        session_error = _validate_studio_regen_apply_session(session_name, session)
        if session_error:
            return session_error
    return None


def _validate_studio_regen_apply_session(session_name: str, session: dict[str, Any]) -> str | None:
    prefix = f"Studio L5 scenario '{STUDIO_REGEN_APPLY_SCENARIO}' {session_name}"
    if not bool(session.get("applied")):
        return f"{prefix} did not apply successfully"
    count = session.get("new_migration_count")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        return f"{prefix} did not report a positive new_migration_count"
    if not bool(session.get("migration_contains_field")):
        return f"{prefix} migration did not contain the expected field"

    workspace = session.get("workspace_root")
    if not isinstance(workspace, str) or not workspace:
        return f"{prefix} did not expose workspace_root"
    workspace_root = Path(workspace).expanduser().resolve(strict=False)
    for key in (
        "export_package",
        "generated_output",
        "initial_managed_package",
        "refreshed_package",
    ):
        value = session.get(key)
        if not isinstance(value, str) or not value:
            return f"{prefix} did not expose {key}"
        if not _path_is_relative_to(Path(value), workspace_root):
            return (
                f"{prefix} reported {key} outside "
                f"workspace_root: {value}"
            )
    migration_needle = session.get("migration_needle")
    if not isinstance(migration_needle, str) or not migration_needle:
        return f"{prefix} did not expose migration_needle"

    summary = session.get("apply_summary")
    if not isinstance(summary, dict):
        return f"{prefix} did not expose apply_summary"
    status = summary.get("status")
    if status != "none":
        return f"{prefix} apply_summary status is not the post-apply regen status 'none'"
    for key in ("generation_run_id", "managed_package_ref", "manifest_hash", "baseline_hash"):
        value = summary.get(key)
        if not isinstance(value, str) or not value:
            return f"{prefix} apply_summary did not expose {key}"
    if not isinstance(summary.get("baseline_present"), bool):
        return f"{prefix} apply_summary baseline_present is not boolean"
    return None


def _json_path_get(value: Any, dotted_path: str) -> Any:
    current = value
    for segment in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def _studio_scenario(scenarios: list[Any], scenario_name: str) -> dict[str, Any] | None:
    for scenario in scenarios:
        if isinstance(scenario, dict) and scenario.get("scenario") == scenario_name:
            return scenario
    return None


def _scan_studio_artifacts_for_absolute_paths(payload: dict[str, Any]) -> dict[str, Any]:
    explicit = _explicit_studio_no_leak_result(payload)
    if explicit is not None:
        return {
            "ok": explicit,
            "mode": "studio-scenario",
            "scanned_roots": [],
            "findings": [],
            "error": None if explicit else "Studio reported absolute local path leak check failure",
        }

    roots = _studio_artifact_roots(payload)
    if not roots:
        return {
            "ok": False,
            "mode": "orchestrator-scan",
            "scanned_roots": [],
            "findings": [],
            "error": "Studio L5 payload did not expose package/generated artifact roots for no-leak scan",
        }

    markers = _absolute_path_leak_markers(roots)
    findings: list[dict[str, str]] = []
    scanned_files = 0
    for root in roots:
        for path in _iter_scannable_artifact_files(root):
            scanned_files += 1
            text = _read_text_if_scannable(path)
            if text is None:
                continue
            for marker in markers:
                if marker in text:
                    findings.append({"file": path.as_posix(), "marker": marker})

    return {
        "ok": not findings,
        "mode": "orchestrator-scan",
        "scanned_roots": [root.as_posix() for root in roots],
        "scanned_files": scanned_files,
        "findings": findings,
        "error": None if not findings else "absolute local path leak found in Studio artifact output",
    }


def _explicit_studio_no_leak_result(payload: dict[str, Any]) -> bool | None:
    for scenario in payload.get("scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        name = str(scenario.get("scenario") or "")
        if name in STUDIO_NO_LEAK_SCENARIOS:
            return bool(scenario.get("ok"))
    for check in payload.get("checks") or []:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name") or "")
        if name in STUDIO_NO_LEAK_SCENARIOS:
            return bool(check.get("success", check.get("ok")))
    return None


def _studio_artifact_roots(payload: dict[str, Any]) -> list[Path]:
    roots: dict[str, Path] = {}
    for value in _walk_json_values(payload):
        if not isinstance(value, dict):
            continue
        for key in STUDIO_ARTIFACT_DIR_KEYS:
            candidate = value.get(key)
            if not isinstance(candidate, str) or not candidate:
                continue
            path = Path(candidate).expanduser()
            if path.exists() and path.is_dir():
                roots[path.resolve().as_posix()] = path.resolve()
    return [roots[key] for key in sorted(roots)]


def _walk_json_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(_walk_json_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_json_values(child))
    return values


def _absolute_path_leak_markers(roots: list[Path]) -> tuple[str, ...]:
    markers = set(LOCAL_PATH_LEAK_MARKERS)
    for root in roots:
        markers.add(root.as_posix())
        try:
            markers.add(root.resolve().as_posix())
        except OSError:
            continue
    return tuple(sorted(marker for marker in markers if marker))


def _iter_scannable_artifact_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in ARTIFACT_SCAN_SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def _read_text_if_scannable(path: Path) -> str | None:
    try:
        if path.stat().st_size > ARTIFACT_SCAN_MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _run_python_snippet(
    repo: Path,
    code: str,
    *,
    env: dict[str, str],
    python_env_var: str | None = None,
) -> subprocess.CompletedProcess[str]:
    python = _python_for_repo(repo, env=env, python_env_var=python_env_var)
    env = {**env, "PYTHONPATH": _prepend_path(repo, env.get("PYTHONPATH"))}
    return subprocess.run(
        [str(python), "-c", code],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _python_for_repo(
    repo: Path,
    *,
    env: dict[str, str] | None = None,
    python_env_var: str | None = None,
) -> Path:
    env = env or os.environ
    configured = env.get(python_env_var) if python_env_var else None
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            repo / ".venv" / "bin" / "python",
            repo / ".venv" / "bin" / "python3",
        ]
    )
    python311 = shutil.which("python3.11")
    if python311:
        candidates.append(Path(python311))
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def _prepend_path(path: Path, existing: str | None) -> str:
    if existing:
        return f"{path.as_posix()}{os.pathsep}{existing}"
    return path.as_posix()


def _repo_from_env(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    repo = Path(value).expanduser().resolve()
    if not repo.exists():
        return None
    return repo


def _sha_pin_manifest(*, root: Path, studio_repo: Path, ks_repo: Path) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "root": root.as_posix(),
        "repos": {
            "engine": {
                "path": REPO_ROOT.as_posix(),
                "sha": _git_sha(REPO_ROOT),
            },
            "studio": {
                "path": studio_repo.as_posix(),
                "sha": _git_sha(studio_repo),
            },
            "ks": {
                "path": ks_repo.as_posix(),
                "sha": _git_sha(ks_repo),
            },
        },
        "topology": {
            "postgres": {
                "image": engine_l5_smoke.POSTGRES_IMAGE,
                "container": engine_l5_smoke.POSTGRES_CONTAINER,
            },
            "mock_soap": {
                "implementation": "scripts.smoke.engine_l5_smoke._MockSoapServer",
                "version": "in-process-v1",
            },
            "generated_app": {
                "image": engine_l5_smoke.APP_IMAGE,
                "container": engine_l5_smoke.APP_CONTAINER,
            },
        },
    }


def _git_sha(repo: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip()


def _build_hard_fail_checklist(results: list[OrchestratorResult]) -> list[dict[str, Any]]:
    by_name = {result.name: result for result in results}
    engine_runtime = by_name.get("engine.runtime")
    engine_regen = by_name.get("engine.regenerate")
    engine_plan = by_name.get("engine.change_plan")
    engine_apply_isolation = by_name.get("engine.apply_isolation")
    studio = by_name.get("studio.l5")
    ks = by_name.get("ks.l5")

    return [
        _check("generated-app runtime failure", _result_ok(engine_runtime)),
        _check(
            "session bleed",
            _all_known(
                _studio_scenario_ok(studio, "multi-session isolation"),
                _ks_check_ok(ks, "per_session_db_isolation"),
                _ks_check_ok(ks, "project_scoped_search_no_bleed"),
                _ks_check_ok(ks, "explicit_cross_project_filter_no_bleed"),
            ),
        ),
        _check(
            "read/write outside server-owned root",
            _all_known(
                _studio_scenario_ok(studio, "Studio-to-Engine per-session outputs"),
                _studio_scenario_ok(studio, "shared-mode security"),
                _studio_scenario_ok(studio, "Engine fail-closed out-of-root"),
                _result_steps_contain(engine_apply_isolation, "apply shared-mode no allowed roots fail-closed"),
                _result_steps_contain(engine_apply_isolation, "apply out-of-root manifest rejected"),
                _result_steps_contain(engine_apply_isolation, "apply out-of-root package rejected"),
                _result_steps_contain(engine_apply_isolation, "apply wrote only under resolved package path"),
                _ks_check_ok(ks, "allowed_root_rejects_outside_read"),
                _ks_check_ok(ks, "shared_mode_requires_explicit_db_path"),
            ),
        ),
        _check(
            "hidden KS/KA/LLM call when KA is OFF",
            _all_known(
                _studio_scenario_ok(studio, "KA-OFF strict"),
                _engine_ka_off_ok(engine_runtime),
            ),
        ),
        _check("stale plan_hash accepted", _result_steps_contain(engine_regen, "plan-hash drift refused")),
        _check(
            "destructive/unsafe migration silently emitted",
            _all_known(
                _result_steps_contain(engine_regen, "destructive apply"),
                _result_steps_contain(engine_plan, "destructive/unsafe classification"),
            ),
        ),
        _check(
            "absolute local path leak in evidence/artifacts",
            _all_known(
                _ks_check_ok(ks, "results_do_not_leak_absolute_paths"),
                _studio_no_absolute_path_leak(studio),
            ),
        ),
    ]


def _check(name: str, passed: bool | None) -> dict[str, Any]:
    if passed is None:
        return {"name": name, "status": "skip"}
    return {"name": name, "status": "pass" if passed else "fail"}


def _result_ok(result: OrchestratorResult | None) -> bool | None:
    if result is None or result.skipped():
        return None
    return result.ok()


def _all_known(*values: bool | None) -> bool | None:
    if any(value is None for value in values):
        return None
    return all(bool(value) for value in values)


def _studio_scenario_ok(result: OrchestratorResult | None, scenario_name: str) -> bool | None:
    if result is None or result.skipped():
        return None
    if not result.ok():
        return False
    for scenario in result.detail.get("scenarios") or []:
        if scenario.get("scenario") == scenario_name:
            return bool(scenario.get("ok"))
    return False


def _ks_success(result: OrchestratorResult | None) -> bool | None:
    if result is None or result.skipped():
        return None
    return bool(result.ok() and result.detail.get("success"))


def _ks_check_ok(result: OrchestratorResult | None, check_name: str) -> bool | None:
    success = _ks_success(result)
    if success is None:
        return None
    if not success:
        return False
    for check in result.detail.get("checks") or []:
        if check.get("name") == check_name:
            return bool(check.get("success"))
    return False


def _engine_ka_off_ok(result: OrchestratorResult | None) -> bool | None:
    if result is None or result.skipped():
        return None
    return bool(result.ok() and _result_steps_contain(result, "KA/KS/MCP-off"))


def _result_steps_contain(result: OrchestratorResult | None, text: str) -> bool | None:
    if result is None or result.skipped():
        return None
    if not result.ok():
        return False
    steps = result.detail.get("steps") or []
    return any(text in str(step) for step in steps)


def _studio_no_absolute_path_leak(result: OrchestratorResult | None) -> bool | None:
    if result is None or result.skipped():
        return None
    if not result.ok():
        return False
    scan = result.detail.get("orchestrator_artifact_scan")
    if isinstance(scan, dict):
        return bool(scan.get("ok"))
    explicit = _explicit_studio_no_leak_result(result.detail)
    return bool(explicit) if explicit is not None else False


def _collect_warnings(results: list[OrchestratorResult]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for result in results:
        for warning in result.warnings:
            warnings.append({"source": result.name, "warning": warning})
        if result.skipped():
            warnings.append({"source": result.name, "warning": "scenario skipped"})
    return warnings


def _empty_report(
    *,
    root: Path,
    status: str,
    warnings: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    report = {
        "status": status,
        "root": root.as_posix(),
        "sha_manifest": {
            "schema_version": "1.0",
            "root": root.as_posix(),
            "repos": {
                "engine": {"path": REPO_ROOT.as_posix(), "sha": _git_sha(REPO_ROOT)},
            },
            "topology": {},
        },
        "results": [],
        "checklist": [],
        "warnings": [{"source": "orchestrator", "warning": warning} for warning in (warnings or [])],
        "error": error,
    }
    _write_json(root / "l5-run-manifest.json", report["sha_manifest"])
    _write_json(root / "l5-report.json", report)
    return report


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _loads_last_json_line(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"subprocess did not emit a JSON object: {output}")


def _human_report(report: dict[str, Any]) -> str:
    lines = [
        f"[{str(report.get('status', 'unknown')).upper()}] EdgeForge Suite L5 acceptance",
        f"root: {report.get('root')}",
        "§8 checklist:",
    ]
    for item in report.get("checklist") or []:
        marker = str(item.get("status", "fail")).upper()
        lines.append(f"  [{marker}] {item.get('name')}")
    if report.get("warnings"):
        lines.append("warnings:")
        for warning in report["warnings"]:
            lines.append(f"  - {warning.get('source')}: {warning.get('warning')}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
