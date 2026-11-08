#!/usr/bin/env python3
"""Run manual cross-repository acceptance for the three Studio sample packs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from appbuilder.contracts import validate_package_or_raise  # noqa: E402
from appbuilder.harness import run_compatibility_harness  # noqa: E402
from appbuilder.metadata import build_metadata_project  # noqa: E402
from appbuilder.target_profiles import TARGET_PROFILES  # noqa: E402
from scripts.smoke.generated_app_independence import (  # noqa: E402
    verify_generated_app_independence,
)

PACK_IDS = (
    "fs-account-servicing",
    "hc-authorization-status",
    "ins-claims-intake-router",
)
PROOF_KEYS = frozenset(
    {
        "pack_id",
        "archetype",
        "target_profile",
        "expected_entities",
        "expected_manifest_schema_version",
        "expected_export_warnings",
        "expected_generation_warnings",
        "expected_harness_warnings",
        "harness_applies",
        "min_studio_project_schema_version",
        "expected_export_dir",
        "expected_exported_artifacts",
    }
)
STUDIO_REQUIRED_PATHS = (
    "app/services/project_file_service.py",
    "app/services/package_writer.py",
    "docs/sample-packs/README.md",
)
NORMALIZED_EXPORT_FILES = frozenset(
    {"evidence-trail.json", "studio-project.json"}
)
TEMP_PREFIX = "edgeforge-domain-sample-packs-"
STUDIO_PYTHON_ENV = "EDGEFORGE_STUDIO_PYTHON"
JAVA_HOME_ENV = {
    "17": "EDGEFORGE_JAVA_17_HOME",
    "21": "EDGEFORGE_JAVA_21_HOME",
}


class DomainSamplePackError(RuntimeError):
    """Raised when the frozen sample-pack acceptance contract is violated."""


@dataclass(frozen=True)
class PackSpec:
    pack_id: str
    pack_dir: Path
    project_path: Path
    proof: dict[str, Any]


@dataclass(frozen=True)
class CliGenerationResult:
    file_count: int
    warnings: list[str]
    harness_status: str


_STUDIO_EXPORT_HELPER = r'''from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.models.project import ProjectSession
from app.services.package_writer import write_package_result
from app.services.project_file_service import deserialize_project, restore_session


def _forbid_process_spawn(*_args, **_kwargs):
    raise RuntimeError("sample-pack export attempted to spawn a process while KA is disabled")


def main() -> int:
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    result_path = Path(sys.argv[2])
    subprocess.Popen = _forbid_process_spawn
    results = {}
    for pack_id in request["pack_ids"]:
        try:
            pack_dir = Path(request["pack_root"]) / pack_id
            project_path = pack_dir / "project" / f"{pack_id}.edgeforge-project.json"
            project = deserialize_project(project_path.read_text(encoding="utf-8"))
            session = ProjectSession(appbuilder_repo_path="")
            restore_session(project, session)
            if session.capabilities.knowledge_assist_enabled or session.ks_active:
                raise RuntimeError("sample pack enabled Knowledge Assist or KS")
            export_root = Path(request["export_root"]) / pack_id
            result = write_package_result(session, export_root)
            results[pack_id] = {
                "status": "passed",
                "project_dir": result.project_dir.as_posix(),
                "warnings": list(result.warnings),
                "written": sorted(result.written),
            }
        except Exception as exc:
            results[pack_id] = {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
    result_path.write_text(
        json.dumps({"packs": results}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate, export, generate, and build the three Studio domain sample packs."
    )
    parser.add_argument(
        "--studio-checkout",
        required=True,
        type=Path,
        help="Absolute path to an EdgeForgeStudio Git checkout containing the maintained packs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = run_acceptance(args.studio_checkout)
    except Exception as exc:
        report = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "packs": {},
            "warnings": [],
        }
    print(_human_summary(report))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "passed" else 1


def run_acceptance(
    studio_checkout: Path,
    *,
    temp_parent: Path | None = None,
) -> dict[str, Any]:
    """Run A10-A16 and return a path-free structured result."""

    studio = validate_studio_checkout(studio_checkout)
    specs = load_pack_specs(studio / "docs" / "sample-packs")
    engine_sha = _git_sha(REPO_ROOT)
    studio_sha = _git_sha(studio)
    engine_status_before = _git_status(REPO_ROOT)
    studio_status_before = _git_status(studio)
    if engine_status_before:
        raise DomainSamplePackError(
            "Engine checkout must be clean before domain sample-pack acceptance"
        )
    if studio_status_before:
        raise DomainSamplePackError(
            "Studio checkout must be clean before domain sample-pack acceptance"
        )
    studio_python = _python_for_repo(
        studio,
        env=os.environ,
        python_env_var=STUDIO_PYTHON_ENV,
    )
    warnings = _evidence_staleness_warnings(
        engine_sha=engine_sha,
        studio_sha=studio_sha,
    )
    report: dict[str, Any] = {
        "status": "failed",
        "engine_sha": engine_sha,
        "studio_sha": studio_sha,
        "studio_python": _python_version(studio_python),
        "packs": {},
        "warnings": warnings,
        "repository_status": {
            "engine_unchanged": False,
            "studio_unchanged": False,
            "temporary_output_removed": False,
        },
    }

    temp_path: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX, dir=temp_parent) as temp_name:
            temp_path = Path(temp_name).resolve()
            report["packs"] = _execute_acceptance(
                specs=specs,
                studio_checkout=studio,
                studio_python=studio_python,
                temp_root=temp_path,
            )
    except Exception as exc:
        report["error"] = _sanitize_message(
            f"{type(exc).__name__}: {exc}",
            temp_path,
        )

    engine_status_after = _git_status(REPO_ROOT)
    studio_status_after = _git_status(studio)
    engine_head_after = _git_sha(REPO_ROOT)
    studio_head_after = _git_sha(studio)
    engine_unchanged = not engine_status_after and engine_head_after == engine_sha
    studio_unchanged = not studio_status_after and studio_head_after == studio_sha
    temp_removed = temp_path is not None and not temp_path.exists()
    report["repository_status"] = {
        "engine_unchanged": engine_unchanged,
        "studio_unchanged": studio_unchanged,
        "temporary_output_removed": temp_removed,
    }
    a15_passed = engine_unchanged and studio_unchanged and temp_removed
    a15_error = None
    if engine_status_after:
        a15_error = "Engine checkout became dirty during acceptance"
    elif engine_head_after != engine_sha:
        a15_error = "Engine HEAD changed during acceptance"
    elif studio_status_after:
        a15_error = "Studio checkout became dirty during acceptance"
    elif studio_head_after != studio_sha:
        a15_error = "Studio HEAD changed during acceptance"
    elif not temp_removed:
        a15_error = "temporary acceptance output was not removed"

    for pack in report["packs"].values():
        pack["checks"]["A15"] = _check(
            a15_passed,
            "both source repositories were unchanged and temporary output was removed",
            error=a15_error,
        )
        pack["status"] = _pack_status(pack)

    report["status"] = _overall_status(report)
    return report


def validate_studio_checkout(studio_checkout: Path) -> Path:
    if not studio_checkout.is_absolute():
        raise DomainSamplePackError("--studio-checkout must be an absolute path")
    studio = studio_checkout.expanduser().resolve()
    if not studio.is_dir():
        raise DomainSamplePackError(f"Studio checkout is not a directory: {studio}")
    if not (studio / ".git").exists():
        raise DomainSamplePackError(f"Studio checkout is not a Git worktree: {studio}")
    completed = _run_command(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=studio,
        check=False,
    )
    if completed.returncode != 0:
        raise DomainSamplePackError("Studio checkout failed Git validation")
    top_level = Path(completed.stdout.strip()).resolve()
    if top_level != studio:
        raise DomainSamplePackError(
            "--studio-checkout must point to the Studio Git worktree root"
        )
    missing = [relative for relative in STUDIO_REQUIRED_PATHS if not (studio / relative).is_file()]
    if missing:
        raise DomainSamplePackError(
            "Studio checkout is missing production export source(s): " + ", ".join(missing)
        )
    return studio


def load_pack_specs(pack_root: Path) -> list[PackSpec]:
    if not pack_root.is_dir():
        raise DomainSamplePackError(f"Studio sample-pack root is missing: {pack_root}")
    actual_ids = sorted(path.name for path in pack_root.iterdir() if path.is_dir())
    if actual_ids != sorted(PACK_IDS):
        raise DomainSamplePackError(
            "Studio sample-pack set must be exactly "
            f"{', '.join(PACK_IDS)}; found {', '.join(actual_ids) or '(none)'}"
        )

    specs: list[PackSpec] = []
    for pack_id in PACK_IDS:
        pack_dir = pack_root / pack_id
        proof_path = pack_dir / "expected-proof.json"
        project_dir = pack_dir / "project"
        expected_project = project_dir / f"{pack_id}.edgeforge-project.json"
        projects = sorted(project_dir.glob("*.edgeforge-project.json")) if project_dir.is_dir() else []
        if projects != [expected_project]:
            raise DomainSamplePackError(
                f"{pack_id}: expected exactly one canonical project at "
                f"project/{expected_project.name}"
            )
        if not proof_path.is_file():
            raise DomainSamplePackError(f"{pack_id}: expected-proof.json is missing")
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DomainSamplePackError(
                f"{pack_id}: expected-proof.json is malformed: {exc}"
            ) from exc
        _validate_proof(pack_id, proof)
        try:
            project = json.loads(expected_project.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DomainSamplePackError(
                f"{pack_id}: canonical project JSON is malformed: {exc}"
            ) from exc
        if not isinstance(project, dict):
            raise DomainSamplePackError(
                f"{pack_id}: canonical project JSON must contain an object"
            )
        actual_schema_version = project.get("studio_project_schema_version")
        minimum_schema_version = proof["min_studio_project_schema_version"]
        if _version_tuple(actual_schema_version) < _version_tuple(minimum_schema_version):
            raise DomainSamplePackError(
                f"{pack_id}: Studio project schema {actual_schema_version} is below "
                f"the required minimum {minimum_schema_version}"
            )
        specs.append(
            PackSpec(
                pack_id=pack_id,
                pack_dir=pack_dir,
                project_path=expected_project,
                proof=proof,
            )
        )
    return specs


def _validate_proof(pack_id: str, proof: Any) -> None:
    if not isinstance(proof, dict):
        raise DomainSamplePackError(f"{pack_id}: expected-proof.json must contain an object")
    keys = frozenset(proof)
    if keys != PROOF_KEYS:
        missing = sorted(PROOF_KEYS - keys)
        extra = sorted(keys - PROOF_KEYS)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise DomainSamplePackError(f"{pack_id}: malformed proof metadata ({'; '.join(details)})")
    if proof["pack_id"] != pack_id:
        raise DomainSamplePackError(f"{pack_id}: proof pack_id does not match its directory")
    for field in (
        "archetype",
        "target_profile",
        "expected_export_dir",
        "min_studio_project_schema_version",
    ):
        if not isinstance(proof[field], str) or not proof[field]:
            raise DomainSamplePackError(f"{pack_id}: proof field '{field}' must be a non-empty string")
    _version_tuple(proof["min_studio_project_schema_version"])
    if proof["expected_manifest_schema_version"] != "2.0":
        raise DomainSamplePackError(f"{pack_id}: manifest schema expectation must be 2.0")
    if not isinstance(proof["harness_applies"], bool):
        raise DomainSamplePackError(f"{pack_id}: harness_applies must be boolean")
    _require_string_list(pack_id, proof, "expected_entities")
    for warning_field in (
        "expected_export_warnings",
        "expected_generation_warnings",
        "expected_harness_warnings",
    ):
        _require_string_list(pack_id, proof, warning_field)
        if proof[warning_field]:
            raise DomainSamplePackError(
                f"{pack_id}: {warning_field} must remain empty for frozen acceptance"
            )
    artifacts = _require_string_list(pack_id, proof, "expected_exported_artifacts")
    if not artifacts or artifacts != sorted(set(artifacts)):
        raise DomainSamplePackError(
            f"{pack_id}: expected_exported_artifacts must be a sorted, unique, non-empty list"
        )
    for artifact in artifacts:
        path = PurePosixPath(artifact)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise DomainSamplePackError(
                f"{pack_id}: invalid expected exported artifact path '{artifact}'"
            )
    export_dir = PurePosixPath(proof["expected_export_dir"])
    if export_dir.is_absolute() or len(export_dir.parts) != 1 or ".." in export_dir.parts:
        raise DomainSamplePackError(f"{pack_id}: expected_export_dir must be one safe directory name")


def _version_tuple(value: Any) -> tuple[int, int]:
    if not isinstance(value, str) or re.fullmatch(r"\d+\.\d+", value) is None:
        raise DomainSamplePackError(
            f"Studio project schema versions must use '<major>.<minor>'; got {value!r}"
        )
    major, minor = value.split(".")
    return int(major), int(minor)


def _require_string_list(pack_id: str, proof: dict[str, Any], field: str) -> list[str]:
    value = proof[field]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DomainSamplePackError(f"{pack_id}: proof field '{field}' must be a string list")
    return value


def _execute_acceptance(
    *,
    specs: list[PackSpec],
    studio_checkout: Path,
    studio_python: Path,
    temp_root: Path,
) -> dict[str, Any]:
    export_roots = [
        temp_root / "exports" / f"run-{run_number}"
        for run_number in (1, 2)
    ]
    export_runs = []
    for run_number, export_root in enumerate(export_roots, start=1):
        export_runs.append(
            _run_studio_export(
                specs=specs,
                studio_checkout=studio_checkout,
                studio_python=studio_python,
                export_root=export_root,
                helper_root=temp_root / "studio-helper" / f"run-{run_number}",
            )
        )

    results: dict[str, Any] = {}
    for spec in specs:
        pack = _new_pack_result(spec)
        first = export_runs[0].get(spec.pack_id)
        second = export_runs[1].get(spec.pack_id)
        try:
            first_dir = _validate_export_result(
                spec,
                first,
                expected_export_root=export_roots[0] / spec.pack_id,
            )
            second_dir = _validate_export_result(
                spec,
                second,
                expected_export_root=export_roots[1] / spec.pack_id,
            )
            if first_dir == second_dir:
                raise DomainSamplePackError(
                    f"{spec.pack_id}: repeated exports reused the same directory"
                )
            pack["export"] = {
                "status": "passed",
                "warnings": list(first["warnings"]),
                "artifact_count": len(first["written"]),
            }
            pack["checks"]["A16"] = _compare_exports(
                spec,
                first_dir,
                second_dir,
            )
            _run_engine_acceptance(
                spec=spec,
                export_dir=first_dir,
                generated_dir=temp_root / "generated" / spec.pack_id,
                temp_root=temp_root,
                pack=pack,
            )
        except Exception as exc:
            pack["export"] = {
                "status": "failed",
                "warnings": [],
                "error": _sanitize_message(
                    f"{type(exc).__name__}: {exc}",
                    temp_root,
                ),
            }
            _fail_unset_checks(
                pack,
                _sanitize_message(f"export prerequisite failed: {exc}", temp_root),
            )
        pack["status"] = _pack_status(pack)
        results[spec.pack_id] = pack
    return results


def _run_studio_export(
    *,
    specs: list[PackSpec],
    studio_checkout: Path,
    studio_python: Path,
    export_root: Path,
    helper_root: Path,
) -> dict[str, Any]:
    helper_root.mkdir(parents=True, exist_ok=True)
    helper_path = helper_root / "studio_export_helper.py"
    request_path = helper_root / "request.json"
    result_path = helper_root / "result.json"
    helper_path.write_text(_STUDIO_EXPORT_HELPER, encoding="utf-8")
    request_path.write_text(
        json.dumps(
            {
                "pack_ids": [spec.pack_id for spec in specs],
                "pack_root": specs[0].pack_dir.parent.as_posix(),
                "export_root": export_root.as_posix(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = _prepend_path(studio_checkout, env.get("PYTHONPATH"))
    completed = _run_command(
        [str(studio_python), str(helper_path), str(request_path), str(result_path)],
        cwd=studio_checkout,
        env=env,
        check=False,
        timeout=180,
    )
    if completed.returncode != 0:
        raise DomainSamplePackError(
            "Studio export helper failed: " + _output_tail(completed.stdout, root=helper_root.parent)
        )
    if not result_path.is_file():
        raise DomainSamplePackError("Studio export helper did not produce structured results")
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DomainSamplePackError(f"Studio export helper returned malformed JSON: {exc}") from exc
    packs = payload.get("packs") if isinstance(payload, dict) else None
    if not isinstance(packs, dict) or set(packs) != set(PACK_IDS):
        raise DomainSamplePackError("Studio export helper returned an invalid pack result set")
    return packs


def _validate_export_result(
    spec: PackSpec,
    result: Any,
    *,
    expected_export_root: Path,
) -> Path:
    if not isinstance(result, dict):
        raise DomainSamplePackError(f"{spec.pack_id}: Studio export result is missing")
    if result.get("status") != "passed":
        raise DomainSamplePackError(
            f"{spec.pack_id}: Studio export failed: {result.get('error') or 'unknown error'}"
        )
    warnings = result.get("warnings")
    _require_warning_match(
        spec.pack_id,
        "export",
        warnings,
        spec.proof["expected_export_warnings"],
    )
    written = result.get("written")
    expected = spec.proof["expected_exported_artifacts"]
    if written != expected:
        raise DomainSamplePackError(
            f"{spec.pack_id}: exported artifact list mismatch; expected {expected}, got {written}"
        )
    project_dir = Path(str(result.get("project_dir", ""))).resolve()
    expected_project_dir = (
        expected_export_root / spec.proof["expected_export_dir"]
    ).resolve()
    if project_dir != expected_project_dir:
        raise DomainSamplePackError(
            f"{spec.pack_id}: export did not use its run-specific output directory"
        )
    actual = sorted(
        path.relative_to(project_dir).as_posix()
        for path in project_dir.rglob("*")
        if path.is_file()
    )
    if actual != expected:
        raise DomainSamplePackError(
            f"{spec.pack_id}: exported tree mismatch; expected {expected}, got {actual}"
        )
    return project_dir


def _compare_exports(spec: PackSpec, first: Path, second: Path) -> dict[str, Any]:
    expected = spec.proof["expected_exported_artifacts"]
    normalized: list[str] = []
    raw_count = 0
    for relative in expected:
        first_bytes = (first / relative).read_bytes()
        second_bytes = (second / relative).read_bytes()
        if relative in NORMALIZED_EXPORT_FILES:
            normalized.append(relative)
            first_bytes = _normalize_volatile_export(relative, first_bytes)
            second_bytes = _normalize_volatile_export(relative, second_bytes)
        else:
            raw_count += 1
        if first_bytes != second_bytes:
            raise DomainSamplePackError(
                f"{spec.pack_id}: A16 unapproved repeated-export drift in '{relative}'"
            )
    return _check(
        True,
        f"{raw_count} files were byte-identical; normalized only " + ", ".join(normalized),
    )


def _normalize_volatile_export(relative: str, content: bytes) -> bytes:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DomainSamplePackError(f"{relative}: volatile file is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise DomainSamplePackError(f"{relative}: volatile file must contain a JSON object")

    marker = "<volatile>"
    if relative == "evidence-trail.json":
        for field in ("manifest_revision_id", "exported_at"):
            if field not in payload:
                raise DomainSamplePackError(f"{relative}: missing volatile field '{field}'")
            payload[field] = marker
    elif relative == "studio-project.json":
        for field in ("updated_at", "saved_at", "last_export_path"):
            if field not in payload:
                raise DomainSamplePackError(f"{relative}: missing volatile field '{field}'")
            payload[field] = marker
        revisions = payload.get("manifest_revisions")
        if not isinstance(revisions, list) or not revisions:
            raise DomainSamplePackError(f"{relative}: manifest_revisions must contain the export entry")
        for revision in revisions:
            if not isinstance(revision, dict):
                raise DomainSamplePackError(f"{relative}: malformed manifest revision")
            for field in ("revision_id", "exported_at", "export_path"):
                if field not in revision:
                    raise DomainSamplePackError(
                        f"{relative}: manifest revision is missing volatile field '{field}'"
                    )
                revision[field] = marker
    else:  # pragma: no cover - guarded by NORMALIZED_EXPORT_FILES
        raise DomainSamplePackError(f"normalization is not allowed for '{relative}'")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _run_engine_acceptance(
    *,
    spec: PackSpec,
    export_dir: Path,
    generated_dir: Path,
    temp_root: Path,
    pack: dict[str, Any],
) -> None:
    manifest_path = export_dir / "app-definition.yaml"
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        validate_package_or_raise(manifest)
        if manifest.get("schema_version") != spec.proof["expected_manifest_schema_version"]:
            raise DomainSamplePackError("manifest schema version does not match proof metadata")
        if manifest.get("app_archetype") != spec.proof["archetype"]:
            raise DomainSamplePackError("manifest archetype does not match proof metadata")
        if manifest.get("target_profile") != spec.proof["target_profile"]:
            raise DomainSamplePackError("manifest target profile does not match proof metadata")
        pack["checks"]["A10"] = _check(
            True,
            "manifest 2.0 schema, archetype, and target profile validated",
        )
    except Exception as exc:
        pack["checks"]["A10"] = _check(
            False,
            "manifest validation failed",
            error=_sanitize_message(str(exc), temp_root),
        )
        _fail_checks(pack, ("A11", "A12", "A13", "A14"), "A10 failed")
        return

    try:
        cli_result = _run_generation_cli(
            manifest_path=manifest_path,
            generated_dir=generated_dir,
            temp_root=temp_root,
        )
        _require_warning_match(
            spec.pack_id,
            "generation",
            cli_result.warnings,
            spec.proof["expected_generation_warnings"],
        )
        expected_harness_status = "passed" if spec.proof["harness_applies"] else "not-run"
        if cli_result.harness_status != expected_harness_status:
            raise DomainSamplePackError(
                f"CLI harness status mismatch; expected {expected_harness_status}, "
                f"got {cli_result.harness_status}"
            )
        metadata = build_metadata_project(manifest_path)
        actual_entities = sorted(entity.name for entity in getattr(metadata, "entities", []))
        if actual_entities != sorted(spec.proof["expected_entities"]):
            raise DomainSamplePackError(
                f"expected entities {spec.proof['expected_entities']}, got {actual_entities}"
            )
        if not _is_within(generated_dir.resolve(), temp_root):
            raise DomainSamplePackError("generated output escaped the temporary root")
        pack["generation_warnings"] = list(cli_result.warnings)
        pack["checks"]["A11"] = _check(
            True,
            f"production CLI generated {cli_result.file_count} files with zero warnings",
        )
    except Exception as exc:
        pack["checks"]["A11"] = _check(
            False,
            "generation failed",
            error=_sanitize_message(str(exc), temp_root),
        )
        _fail_checks(pack, ("A12", "A13", "A14"), "A11 failed")
        return

    try:
        harness_report = (
            run_compatibility_harness(metadata, generated_dir)
            if spec.proof["harness_applies"]
            else None
        )
        pack["checks"]["A12"] = _validate_harness(spec, harness_report)
    except Exception as exc:
        pack["checks"]["A12"] = _check(
            False,
            "harness validation failed",
            error=_sanitize_message(str(exc), temp_root),
        )

    require_baseline = spec.proof["archetype"] == "crud"
    source_independence = None
    packaged_independence = None
    try:
        source_independence = verify_generated_app_independence(
            generated_dir,
            require_schema_baseline=require_baseline,
        )
    except Exception as exc:
        pack["checks"]["A14"] = _check(
            False,
            "source independence proof failed",
            error=_sanitize_message(str(exc), temp_root),
        )

    try:
        profile = TARGET_PROFILES[spec.proof["target_profile"]]
        baseline = profile.java_baseline
        if baseline is None or baseline not in JAVA_HOME_ENV:
            raise DomainSamplePackError(
                f"target profile declares unsupported Java baseline '{baseline}'"
            )
        maven_command = _maven_command_for_profile(profile)
        build = _run_maven_build(
            generated_dir,
            java_baseline=baseline,
            maven_command=maven_command,
            temp_root=temp_root,
        )
        pack["checks"]["A13"] = _check(
            True,
            f"{' '.join(maven_command)} passed with Java {baseline}",
        )
        pack["toolchain"] = build
    except Exception as exc:
        pack["checks"]["A13"] = _check(
            False,
            "Maven build failed",
            error=_sanitize_message(str(exc), temp_root),
        )

    if pack["checks"]["A13"]["status"] == "passed":
        try:
            packaged_independence = verify_generated_app_independence(
                generated_dir,
                require_packaged_jar=True,
                require_schema_baseline=require_baseline,
            )
        except Exception as exc:
            pack["checks"]["A14"] = _check(
                False,
                "packaged-JAR independence proof failed",
                error=_sanitize_message(str(exc), temp_root),
            )
    elif pack["checks"]["A14"]["status"] == "pending":
        pack["checks"]["A14"] = _check(
            False,
            "packaged-JAR independence proof not run",
            error="A13 failed",
        )

    if source_independence is not None and packaged_independence is not None:
        pack["checks"]["A14"] = _check(
            True,
            "source and packaged-JAR independence checks passed",
        )
        pack["independence"] = {
            "before_packaging_checks": [
                check.name for check in source_independence.checks
            ],
            "after_packaging_checks": [
                check.name for check in packaged_independence.checks
            ],
            "packaged_jar": packaged_independence.packaged_jar,
            "schema_baseline_generated_source_count": (
                packaged_independence.baseline_generated_source_count
            ),
        }


def _run_generation_cli(
    *,
    manifest_path: Path,
    generated_dir: Path,
    temp_root: Path,
) -> CliGenerationResult:
    command = [
        sys.executable,
        "-m",
        "appbuilder.cli",
        "generate",
        "--manifest",
        str(manifest_path),
        "--output",
        str(generated_dir),
        "--generation-run-id",
        "domain-sample-pack-acceptance",
        "--validate-schema",
    ]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = _run_command(
        command,
        cwd=REPO_ROOT,
        env=env,
        check=False,
        timeout=180,
    )
    if completed.returncode != 0:
        raise DomainSamplePackError(
            "production CLI generation failed: "
            + _output_tail(completed.stdout, root=temp_root)
        )
    file_count_match = re.search(r"^Files created: (\d+)$", completed.stdout, re.MULTILINE)
    if file_count_match is None:
        raise DomainSamplePackError("production CLI omitted its generated-file count")
    if "Harness: PASSED (static compatibility checks)" in completed.stdout:
        harness_status = "passed"
    elif "Harness: NOT RUN" in completed.stdout:
        harness_status = "not-run"
    else:
        raise DomainSamplePackError("production CLI returned an unknown harness status")
    return CliGenerationResult(
        file_count=int(file_count_match.group(1)),
        warnings=_cli_generation_warnings(completed.stdout),
        harness_status=harness_status,
    )


def _cli_generation_warnings(output: str) -> list[str]:
    lines = output.splitlines()
    if "Generation warnings:" not in lines:
        return []
    start = lines.index("Generation warnings:") + 1
    warnings: list[str] = []
    for line in lines[start:]:
        if not line.startswith("  - "):
            raise DomainSamplePackError(
                "production CLI returned malformed generation-warning output"
            )
        warnings.append(line.removeprefix("  - "))
    return warnings


def _validate_harness(spec: PackSpec, harness: Any) -> dict[str, Any]:
    if spec.proof["harness_applies"]:
        if harness is None:
            raise DomainSamplePackError(f"{spec.pack_id}: expected a harness report")
        warnings = [check.message for check in harness.warnings]
        _require_warning_match(
            spec.pack_id,
            "harness",
            warnings,
            spec.proof["expected_harness_warnings"],
        )
        if not harness.passed or harness.errors:
            errors = [check.message for check in harness.errors]
            raise DomainSamplePackError(
                f"{spec.pack_id}: harness failed: {errors or 'error-severity check failed'}"
            )
        return _check(True, "compatibility harness passed with zero warnings")
    if harness is not None:
        raise DomainSamplePackError(
            f"{spec.pack_id}: harness must not run for this archetype"
        )
    return {
        "status": "not-applicable",
        "detail": "generation correctly returned no harness report",
        "error": None,
    }


def _maven_command_for_profile(profile: Any) -> list[str]:
    database = profile.runtime_database_dependency
    if database == "postgresql":
        return ["mvn", "-q", "clean", "package", "-DskipTests"]
    if database == "h2":
        return ["mvn", "-q", "clean", "verify"]
    raise DomainSamplePackError(
        f"unsupported target-profile runtime database '{database}'"
    )


def _run_maven_build(
    generated_dir: Path,
    *,
    java_baseline: str,
    maven_command: list[str],
    temp_root: Path,
) -> dict[str, str]:
    java_home = _java_home_for(java_baseline, env=os.environ)
    env = os.environ.copy()
    env["JAVA_HOME"] = java_home.as_posix()
    env["PATH"] = _prepend_path(java_home / "bin", env.get("PATH"))
    java_result = _run_command(
        [str(java_home / "bin" / "java"), "-version"],
        cwd=generated_dir,
        env=env,
        check=False,
    )
    java_version = _first_nonempty_line(java_result.stdout)
    if _java_major(java_home) != java_baseline:
        raise DomainSamplePackError(
            f"selected JAVA_HOME does not provide Java {java_baseline}"
        )
    maven_version_result = _run_command(
        ["mvn", "-version"],
        cwd=generated_dir,
        env=env,
        check=False,
    )
    if maven_version_result.returncode != 0:
        raise DomainSamplePackError("unable to read Maven version")
    maven_lines = [line.strip() for line in maven_version_result.stdout.splitlines() if line.strip()]
    maven_java_major, maven_java_line = _maven_java_version(maven_lines)
    if maven_java_major != java_baseline:
        raise DomainSamplePackError(
            f"Maven uses Java {maven_java_major}, expected Java {java_baseline}"
        )
    completed = _run_command(
        maven_command,
        cwd=generated_dir,
        env=env,
        check=False,
        timeout=600,
    )
    if completed.returncode != 0:
        raise DomainSamplePackError(
            "Maven build failed: " + _output_tail(completed.stdout, root=temp_root)
        )
    return {
        "command": " ".join(maven_command),
        "java_baseline": java_baseline,
        "java_version": java_version,
        "maven_version": maven_lines[0] if maven_lines else "unknown",
        "maven_java": maven_java_line,
    }


def _maven_java_version(lines: list[str]) -> tuple[str, str]:
    java_lines = [line for line in lines if line.startswith("Java version:")]
    if len(java_lines) != 1:
        raise DomainSamplePackError(
            "Maven version output must contain exactly one Java version line"
        )
    match = re.fullmatch(r"Java version:\s*(?:1\.)?(\d+)(?:[.,\s].*)?", java_lines[0])
    if match is None:
        raise DomainSamplePackError("Maven returned a malformed Java version line")
    return match.group(1), java_lines[0]


def _java_home_for(version: str, *, env: dict[str, str]) -> Path:
    candidates: list[Path] = []
    configured = env.get(JAVA_HOME_ENV[version])
    if configured:
        candidates.append(Path(configured).expanduser())
    if env.get("JAVA_HOME"):
        candidates.append(Path(env["JAVA_HOME"]).expanduser())

    brew = shutil.which("brew")
    if brew:
        result = _run_command(
            [brew, "--prefix", f"openjdk@{version}"],
            cwd=REPO_ROOT,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            prefix = Path(result.stdout.strip())
            candidates.extend(
                [
                    prefix / "libexec" / "openjdk.jdk" / "Contents" / "Home",
                    prefix,
                ]
            )

    java_home_tool = Path("/usr/libexec/java_home")
    if java_home_tool.is_file():
        result = _run_command(
            [str(java_home_tool), "-v", version],
            cwd=REPO_ROOT,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            candidates.append(Path(result.stdout.strip()))

    java = shutil.which("java")
    if java:
        candidates.append(Path(java).resolve().parent.parent)
    jvm_root = Path("/usr/lib/jvm")
    if jvm_root.is_dir():
        candidates.extend(sorted(path for path in jvm_root.iterdir() if path.is_dir()))

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "bin" / "java").is_file() and _java_major(resolved) == version:
            return resolved
    raise DomainSamplePackError(
        f"Java {version} is required but was not found; set {JAVA_HOME_ENV[version]}"
    )


def _java_major(java_home: Path) -> str | None:
    result = _run_command(
        [str(java_home / "bin" / "java"), "-version"],
        cwd=REPO_ROOT,
        check=False,
    )
    match = re.search(r'version "(?:1\.)?(\d+)', result.stdout)
    return match.group(1) if match else None


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
            return candidate.resolve()
    return Path(sys.executable).resolve()


def _python_version(python: Path) -> str:
    result = _run_command([str(python), "--version"], cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        raise DomainSamplePackError(f"Studio interpreter cannot run: {python}")
    return result.stdout.strip()


def _git_sha(repo: Path) -> str:
    result = _run_command(["git", "rev-parse", "HEAD"], cwd=repo, check=False)
    if result.returncode != 0:
        raise DomainSamplePackError(f"cannot resolve Git HEAD for {repo.name}")
    return result.stdout.strip()


def _git_status(repo: Path) -> bytes:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise DomainSamplePackError(f"cannot read Git status for {repo.name}")
    return completed.stdout


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = False,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
        timeout=timeout,
    )


def _require_warning_match(
    pack_id: str,
    stage: str,
    actual: Any,
    expected: list[str],
) -> None:
    if not isinstance(actual, list) or any(not isinstance(item, str) for item in actual):
        raise DomainSamplePackError(f"{pack_id}: {stage} warnings are malformed")
    if actual != expected:
        raise DomainSamplePackError(
            f"{pack_id}: {stage} warnings mismatch; expected {expected}, got {actual}"
        )


def _new_pack_result(spec: PackSpec) -> dict[str, Any]:
    return {
        "pack_id": spec.pack_id,
        "archetype": spec.proof["archetype"],
        "target_profile": spec.proof["target_profile"],
        "status": "failed",
        "export": {"status": "pending", "warnings": []},
        "generation_warnings": [],
        "checks": {
            acceptance: {"status": "pending", "detail": "not run", "error": None}
            for acceptance in ("A10", "A11", "A12", "A13", "A14", "A15", "A16")
        },
    }


def _check(
    passed: bool,
    detail: str,
    *,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "passed" if passed else "failed",
        "detail": detail,
        "error": error,
    }


def _fail_checks(pack: dict[str, Any], checks: tuple[str, ...], reason: str) -> None:
    for name in checks:
        if pack["checks"][name]["status"] == "pending":
            pack["checks"][name] = _check(False, "not run", error=reason)


def _fail_unset_checks(pack: dict[str, Any], reason: str) -> None:
    _fail_checks(
        pack,
        ("A10", "A11", "A12", "A13", "A14", "A16"),
        reason,
    )


def _pack_status(pack: dict[str, Any]) -> str:
    if pack["export"].get("status") != "passed":
        return "failed"
    statuses = {check["status"] for check in pack["checks"].values()}
    return "failed" if "failed" in statuses or "pending" in statuses else "passed"


def _overall_status(report: dict[str, Any]) -> str:
    if report.get("error"):
        return "failed"
    packs = report.get("packs")
    if not isinstance(packs, dict) or set(packs) != set(PACK_IDS):
        return "failed"
    if any(pack.get("status") != "passed" for pack in packs.values()):
        return "failed"
    status = report.get("repository_status", {})
    if not all(status.values()):
        return "failed"
    return "passed"


def _evidence_staleness_warnings(*, engine_sha: str, studio_sha: str) -> list[str]:
    evidence = sorted((REPO_ROOT / "docs" / "test-results").glob("domain-sample-packs-*.md"))
    if not evidence:
        return ["Slice 3 pinned domain-sample-pack evidence is not recorded yet"]
    latest = evidence[-1].read_text(encoding="utf-8")
    if engine_sha not in latest or studio_sha not in latest:
        return ["Latest pinned domain-sample-pack evidence predates this Engine/Studio SHA pair"]
    return []


def _human_summary(report: dict[str, Any]) -> str:
    lines = [
        f"Domain sample-pack acceptance: {str(report.get('status', 'failed')).upper()}",
    ]
    if report.get("engine_sha") and report.get("studio_sha"):
        lines.append(
            f"Engine {str(report['engine_sha'])[:12]} | Studio {str(report['studio_sha'])[:12]}"
        )
    packs = report.get("packs")
    if isinstance(packs, dict):
        for pack_id in PACK_IDS:
            pack = packs.get(pack_id)
            if not isinstance(pack, dict):
                continue
            checks = pack.get("checks", {})
            rendered = ", ".join(
                f"{name}={checks[name]['status']}"
                for name in ("A10", "A11", "A12", "A13", "A14", "A15", "A16")
                if name in checks
            )
            lines.append(f"- {pack_id}: {pack.get('status')} ({rendered})")
    for warning in report.get("warnings", []):
        lines.append(f"WARNING: {warning}")
    if report.get("error"):
        lines.append(f"ERROR: {report['error']}")
    return "\n".join(lines)


def _prepend_path(path: Path, existing: str | None) -> str:
    return f"{path.as_posix()}{os.pathsep}{existing}" if existing else path.as_posix()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _output_tail(output: str, *, root: Path, limit: int = 20) -> str:
    sanitized = _sanitize_message(output, root)
    return " | ".join(sanitized.splitlines()[-limit:]) or "no output"


def _sanitize_message(message: str, *roots: Path | None) -> str:
    sanitized = message
    for root in roots:
        if root is not None:
            sanitized = sanitized.replace(root.as_posix(), "<temp-root>")
    return sanitized


def _first_nonempty_line(output: str) -> str:
    return next((line.strip() for line in output.splitlines() if line.strip()), "unknown")


if __name__ == "__main__":
    raise SystemExit(main())
