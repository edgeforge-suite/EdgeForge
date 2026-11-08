#!/usr/bin/env python3
"""Engine L1/L3 smoke runner for generated-app compile and regeneration proof.

This is intentionally Engine-only and read-mostly: it drives the existing
`appbuilder generate` and `appbuilder plan` surfaces, compiles the generated app,
asserts deterministic dry-run behavior, and proves additive apply against a
real Postgres/Flyway database once apply exists. It does not start the generated
app, call Studio/KS/KA/MCP, or run Docker Compose.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Script execution: scripts/smoke is on sys.path.
    from generated_app_independence import verify_generated_app_independence
except ImportError:  # Test/import execution from the repository root.
    from scripts.smoke.generated_app_independence import (
        verify_generated_app_independence,
    )

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "scripts" / "smoke" / "fixtures" / "engine-l1-l3"
TEMP_ROOT = Path("/tmp/edgeforge-suite-smoke-engine-l1-l3")
POSTGRES_CONTAINER = "edgeforge-suite-smoke-p3a-postgres"
POSTGRES_PORT = "15432"
POSTGRES_DB = "edgeforge_smoke"
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "postgres"
POSTGRES_IMAGE = "postgres:16-alpine"
FORBIDDEN_KA_OFF_ARTIFACT_NAMES = {
    "ka",
    "knowledge",
    "knowledge-server",
    "ks",
    "mcp",
    "suggestion",
    "suggestions",
    "testbench",
}
FORBIDDEN_KA_OFF_OUTPUT_SEGMENTS = {
    "ka",
    "knowledge",
    "ks",
    "mcp",
    "studio",
    "testbench",
}


@dataclass
class SmokeResult:
    steps: list[str] = field(default_factory=list)

    def pass_step(self, message: str) -> None:
        self.steps.append(message)
        print(f"[PASS] {message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Engine L1/L3 generated-app compile and Change Plan smoke."
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Retain /tmp/edgeforge-suite-smoke-engine-l1-l3 even when the run succeeds.",
    )
    args = parser.parse_args(argv)

    result = SmokeResult()
    try:
        _prepare_temp_root()
        command_outputs: list[tuple[str, str]] = []
        generated_package = TEMP_ROOT / "generated-app"
        initial_manifest = FIXTURE_ROOT / "initial" / "app-definition.yaml"
        additive_manifest = FIXTURE_ROOT / "additive" / "app-definition.yaml"
        evolved_manifest = FIXTURE_ROOT / "evolved" / "app-definition.yaml"

        generate_result = _run(
            [
                sys.executable,
                "-m",
                "appbuilder.cli",
                "generate",
                "--manifest",
                str(initial_manifest),
                "--output",
                str(generated_package),
                "--generation-run-id",
                "suite-smoke-l1-l3",
                "--validate-schema",
            ],
            cwd=REPO_ROOT,
        )
        command_outputs.append(("generate", generate_result.stdout))
        result.pass_step("generated minimal CRUD/REST fixture app")

        _run(["mvn", "-q", "-DskipTests", "package"], cwd=generated_package)
        result.pass_step("mvn -q -DskipTests package succeeded")

        _assert_standalone_generated_app(
            generated_package,
            require_packaged_jar=True,
        )
        result.pass_step(
            "generated app passed source, Maven, baseline, hygiene, and packaged-JAR "
            "independence checks"
        )

        baseline_path = generated_package / "db" / "schema-baseline.json"
        _assert(baseline_path.is_file(), "db/schema-baseline.json was not emitted")
        result.pass_step("db/schema-baseline.json emitted")

        before_plan_snapshot = _package_snapshot(generated_package)
        evolved_plan_a = _run_plan(evolved_manifest, generated_package, command_outputs)
        evolved_plan_b = _run_plan(evolved_manifest, generated_package, command_outputs)
        after_plan_snapshot = _package_snapshot(generated_package)
        _assert(evolved_plan_a == evolved_plan_b, "Change Plan JSON was not stable")
        _assert(
            evolved_plan_a["plan_hash"] == evolved_plan_b["plan_hash"],
            "plan_hash was not stable for identical inputs",
        )
        _assert(
            before_plan_snapshot == after_plan_snapshot,
            "appbuilder plan wrote into the generated package",
        )
        result.pass_step("Change Plan dry-run stable and wrote nothing")

        initial_plan = _run_plan(initial_manifest, generated_package, command_outputs)
        _assert(
            initial_plan["plan_hash"] != evolved_plan_a["plan_hash"],
            "plan_hash did not change when the manifest changed",
        )
        result.pass_step("plan_hash changes when the manifest changes")

        _assert_package_state_hash_sensitivity(
            source_package=generated_package,
            evolved_manifest=evolved_manifest,
            reference_plan=evolved_plan_a,
            command_outputs=command_outputs,
        )
        result.pass_step(
            "package_state_hash changes for generated-file, developer-file, and Flyway inventory drift"
        )

        _assert_baseline_hash_sensitivity(
            source_package=generated_package,
            evolved_manifest=evolved_manifest,
            reference_plan=evolved_plan_a,
            command_outputs=command_outputs,
        )
        result.pass_step("plan_hash changes when the committed baseline changes")

        _assert_fail_closed_classification(evolved_plan_a)
        result.pass_step(
            "destructive and unsafe manifest evolution classified fail-closed at dry-run level"
        )

        postgres_container_started = False
        try:
            _start_postgres_container()
            postgres_container_started = True
            _assert_additive_apply_with_postgres(
                initial_manifest=initial_manifest,
                additive_manifest=additive_manifest,
                destructive_manifest=evolved_manifest,
                command_outputs=command_outputs,
            )
        finally:
            if postgres_container_started and not args.keep:
                _remove_postgres_container()
        result.pass_step("additive apply proven against real Postgres/Flyway")

        _assert_ka_off_artifacts_absent(TEMP_ROOT)
        _assert_no_ka_ks_chatter(command_outputs)
        result.pass_step("KA/KS/MCP-off posture positively asserted")

        if args.keep:
            print(f"[INFO] retained smoke root: {TEMP_ROOT}")
            print(f"[INFO] retained Postgres container: {POSTGRES_CONTAINER}")
        else:
            shutil.rmtree(TEMP_ROOT)
            print("[PASS] cleaned up smoke temp root")
        print("[PASS] Engine L1/L3 smoke completed")
        return 0
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        print(f"[INFO] retained smoke root for triage: {TEMP_ROOT}", file=sys.stderr)
        return 1


def _prepare_temp_root() -> None:
    if TEMP_ROOT.exists():
        shutil.rmtree(TEMP_ROOT)
    TEMP_ROOT.mkdir(parents=True)
    _remove_postgres_container(check=False)


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
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


def _run_failure(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode == 0:
        raise AssertionError(
            f"command unexpectedly succeeded: {' '.join(command)}\n{completed.stdout}"
        )
    return completed


def _run_plan(
    manifest: Path,
    package_dir: Path,
    command_outputs: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    completed = _run(
        [
            sys.executable,
            "-m",
            "appbuilder.cli",
            "plan",
            "--manifest",
            str(manifest),
            "--package",
            str(package_dir),
            "--validate-schema",
        ],
        cwd=REPO_ROOT,
    )
    if command_outputs is not None:
        command_outputs.append(("plan", completed.stdout))
    return json.loads(completed.stdout)


def _assert_standalone_generated_app(
    package_dir: Path,
    *,
    require_packaged_jar: bool = False,
) -> None:
    verify_generated_app_independence(
        package_dir,
        require_packaged_jar=require_packaged_jar,
        require_schema_baseline=True,
    )


def _assert_package_state_hash_sensitivity(
    *,
    source_package: Path,
    evolved_manifest: Path,
    reference_plan: dict[str, Any],
    command_outputs: list[tuple[str, str]],
) -> None:
    generated_edit_package = _copy_package(source_package, TEMP_ROOT / "generated-edit")
    widget_domain = (
        generated_edit_package
        / "src/main/java/com/appbuilder/smoke/domain/Widget.java"
    )
    widget_domain.write_text(
        widget_domain.read_text(encoding="utf-8") + "\n// smoke generated-file drift\n",
        encoding="utf-8",
    )
    _assert_package_state_hash_changed(
        evolved_manifest,
        generated_edit_package,
        reference_plan,
        "generated-owned file edit",
        command_outputs,
    )

    developer_edit_package = _copy_package(source_package, TEMP_ROOT / "developer-edit")
    widget_service = (
        developer_edit_package
        / "src/main/java/com/appbuilder/smoke/service/WidgetService.java"
    )
    widget_service.write_text(
        widget_service.read_text(encoding="utf-8") + "\n// smoke developer-owned edit\n",
        encoding="utf-8",
    )
    _assert_package_state_hash_changed(
        evolved_manifest,
        developer_edit_package,
        reference_plan,
        "developer-owned service edit",
        command_outputs,
    )

    flyway_edit_package = _copy_package(source_package, TEMP_ROOT / "flyway-edit")
    migration = (
        flyway_edit_package
        / "src/main/resources/db/migration/V99__manual_smoke_change.sql"
    )
    migration.write_text("-- smoke manual migration\n", encoding="utf-8")
    _assert_package_state_hash_changed(
        evolved_manifest,
        flyway_edit_package,
        reference_plan,
        "Flyway migration inventory edit",
        command_outputs,
    )


def _assert_package_state_hash_changed(
    manifest: Path,
    package_dir: Path,
    reference_plan: dict[str, Any],
    reason: str,
    command_outputs: list[tuple[str, str]],
) -> None:
    changed_plan = _run_plan(manifest, package_dir, command_outputs)
    _assert(
        changed_plan["package_state_hash"] != reference_plan["package_state_hash"],
        f"package_state_hash did not change for {reason}",
    )
    _assert(
        changed_plan["plan_hash"] != reference_plan["plan_hash"],
        f"plan_hash did not change for {reason}",
    )


def _assert_baseline_hash_sensitivity(
    *,
    source_package: Path,
    evolved_manifest: Path,
    reference_plan: dict[str, Any],
    command_outputs: list[tuple[str, str]],
) -> None:
    baseline_edit_package = _copy_package(source_package, TEMP_ROOT / "baseline-edit")
    baseline_path = baseline_edit_package / "db" / "schema-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["manifest_hash"] = "smoke-baseline-drift"
    baseline_path.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    changed_plan = _run_plan(evolved_manifest, baseline_edit_package, command_outputs)
    _assert(
        changed_plan["baseline_hash"] != reference_plan["baseline_hash"],
        "baseline_hash did not change when db/schema-baseline.json changed",
    )
    _assert(
        changed_plan["plan_hash"] != reference_plan["plan_hash"],
        "plan_hash did not change when db/schema-baseline.json changed",
    )


def _assert_additive_apply_with_postgres(
    *,
    initial_manifest: Path,
    additive_manifest: Path,
    destructive_manifest: Path,
    command_outputs: list[tuple[str, str]],
) -> None:
    postgres_initial_manifest = _copy_fixture_with_target_profile(
        source_fixture_dir=initial_manifest.parent,
        destination=TEMP_ROOT / "postgres-initial",
        target_profile="springboot-enterprise-postgres-java17",
    )
    postgres_additive_manifest = _copy_fixture_with_target_profile(
        source_fixture_dir=additive_manifest.parent,
        destination=TEMP_ROOT / "postgres-additive",
        target_profile="springboot-enterprise-postgres-java17",
    )
    postgres_destructive_manifest = _copy_fixture_with_target_profile(
        source_fixture_dir=destructive_manifest.parent,
        destination=TEMP_ROOT / "postgres-destructive",
        target_profile="springboot-enterprise-postgres-java17",
    )
    package_dir = TEMP_ROOT / "apply-generated-app"

    generate_result = _run(
        [
            sys.executable,
            "-m",
            "appbuilder.cli",
            "generate",
            "--manifest",
            str(postgres_initial_manifest),
            "--output",
            str(package_dir),
            "--generation-run-id",
            "suite-smoke-p3a-baseline",
            "--validate-schema",
        ],
        cwd=REPO_ROOT,
    )
    command_outputs.append(("generate-postgres", generate_result.stdout))
    _run(["mvn", "-q", "-DskipTests", "package"], cwd=package_dir)
    initial_migrations = _migration_snapshot(package_dir)
    _run_flyway_migrate(package_dir)

    additive_plan = _run_plan(postgres_additive_manifest, package_dir, command_outputs)
    drift_package = _copy_package(package_dir, TEMP_ROOT / "apply-drift-package")
    drift_service = (
        drift_package
        / "src/main/java/com/appbuilder/smoke/service/WidgetService.java"
    )
    drift_service.write_text(
        drift_service.read_text(encoding="utf-8") + "\n// drift after approval\n",
        encoding="utf-8",
    )
    drift_result = _run_failure(
        [
            sys.executable,
            "-m",
            "appbuilder.cli",
            "apply",
            "--manifest",
            str(postgres_additive_manifest),
            "--package",
            str(drift_package),
            "--approved-plan-hash",
            additive_plan["plan_hash"],
            "--generation-run-id",
            "suite-smoke-p3a-drift",
            "--validate-schema",
        ],
        cwd=REPO_ROOT,
    )
    _assert(
        "Approved Change Plan hash does not match" in drift_result.stdout,
        "plan-hash drift refusal did not explain the mismatch",
    )
    command_outputs.append(("apply-drift-refusal", drift_result.stdout))

    service_path = package_dir / "src/main/java/com/appbuilder/smoke/service/WidgetService.java"
    developer_marker = "// smoke developer-owned edit survives additive apply"
    service_path.write_text(
        service_path.read_text(encoding="utf-8") + f"\n{developer_marker}\n",
        encoding="utf-8",
    )
    additive_plan = _run_plan(postgres_additive_manifest, package_dir, command_outputs)
    apply_result = _run(
        [
            sys.executable,
            "-m",
            "appbuilder.cli",
            "apply",
            "--manifest",
            str(postgres_additive_manifest),
            "--package",
            str(package_dir),
            "--approved-plan-hash",
            additive_plan["plan_hash"],
            "--generation-run-id",
            "suite-smoke-p3a-apply",
            "--validate-schema",
        ],
        cwd=REPO_ROOT,
    )
    command_outputs.append(("apply-additive", apply_result.stdout))

    _assert_prior_migrations_unchanged(package_dir, initial_migrations)
    additive_migration = (
        package_dir
        / "src/main/resources/db/migration/V2__alter_widget_add_category.sql"
    )
    _assert(additive_migration.exists(), "additive apply did not emit V2 add-column migration")
    _assert(
        "ALTER TABLE widget ADD COLUMN category VARCHAR(255) DEFAULT 'general';"
        in additive_migration.read_text(encoding="utf-8"),
        "additive migration did not add the expected category column",
    )
    _assert(
        developer_marker in service_path.read_text(encoding="utf-8"),
        "developer-owned WidgetService edit was not preserved across apply",
    )
    baseline = json.loads((package_dir / "db/schema-baseline.json").read_text(encoding="utf-8"))
    _assert(baseline["flyway_high_water_mark"] == 2, "baseline high-water mark was not updated")
    widget_baseline = next(
        entity for entity in baseline["entities"] if entity["entity"] == "Widget"
    )
    _assert(
        any(column.get("field") == "category" for column in widget_baseline["columns"]),
        "updated baseline does not include Widget.category",
    )
    _run(["mvn", "-q", "-DskipTests", "package"], cwd=package_dir)
    _run_flyway_migrate(package_dir)
    _assert_postgres_column_exists("widget", "category")

    destructive_plan = _run_plan(postgres_destructive_manifest, package_dir, command_outputs)
    destructive_snapshot = _package_snapshot(package_dir)
    destructive_result = _run_failure(
        [
            sys.executable,
            "-m",
            "appbuilder.cli",
            "apply",
            "--manifest",
            str(postgres_destructive_manifest),
            "--package",
            str(package_dir),
            "--approved-plan-hash",
            destructive_plan["plan_hash"],
            "--generation-run-id",
            "suite-smoke-p3a-destructive",
            "--validate-schema",
        ],
        cwd=REPO_ROOT,
    )
    _assert(
        "additive-only" in destructive_result.stdout,
        "destructive apply refusal did not explain additive-only gating",
    )
    _assert(
        _package_snapshot(package_dir) == destructive_snapshot,
        "destructive apply refusal mutated the generated package",
    )
    command_outputs.append(("apply-destructive-refusal", destructive_result.stdout))


def _copy_fixture_with_target_profile(
    *,
    source_fixture_dir: Path,
    destination: Path,
    target_profile: str,
) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source_fixture_dir, destination)
    manifest_path = destination / "app-definition.yaml"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest = re.sub(r"target_profile: .+", f"target_profile: {target_profile}", manifest)
    manifest_path.write_text(manifest, encoding="utf-8")
    return manifest_path


def _run_flyway_migrate(package_dir: Path) -> None:
    _run(
        [
            "mvn",
            "-q",
            "org.flywaydb:flyway-maven-plugin:10.20.1:migrate",
            f"-Dflyway.url=jdbc:postgresql://127.0.0.1:{POSTGRES_PORT}/{POSTGRES_DB}",
            f"-Dflyway.user={POSTGRES_USER}",
            f"-Dflyway.password={POSTGRES_PASSWORD}",
        ],
        cwd=package_dir,
    )


def _start_postgres_container() -> None:
    _run(
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
    )
    for _ in range(30):
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
        import time

        time.sleep(1)
    raise AssertionError(f"Postgres container {POSTGRES_CONTAINER} did not become ready")


def _remove_postgres_container(*, check: bool = True) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", POSTGRES_CONTAINER],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=check,
        )
    except FileNotFoundError:
        if check:
            raise


def _assert_postgres_column_exists(table_name: str, column_name: str) -> None:
    completed = _run(
        [
            "docker",
            "exec",
            POSTGRES_CONTAINER,
            "psql",
            "-U",
            POSTGRES_USER,
            "-d",
            POSTGRES_DB,
            "-tAc",
            (
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table_name}' AND column_name = '{column_name}'"
            ),
        ],
        cwd=REPO_ROOT,
    )
    _assert(
        completed.stdout.strip() == column_name,
        f"Postgres column {table_name}.{column_name} was not created; got {completed.stdout!r}",
    )


def _migration_snapshot(package_dir: Path) -> dict[str, str]:
    migration_dir = package_dir / "src/main/resources/db/migration"
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(migration_dir.glob("V*.sql"))
    }


def _assert_prior_migrations_unchanged(
    package_dir: Path,
    prior_migrations: dict[str, str],
) -> None:
    migration_dir = package_dir / "src/main/resources/db/migration"
    for name, content in prior_migrations.items():
        current_path = migration_dir / name
        _assert(current_path.exists(), f"prior migration {name} was removed")
        _assert(
            current_path.read_text(encoding="utf-8") == content,
            f"prior migration {name} was modified",
        )


def _assert_fail_closed_classification(plan: dict[str, Any]) -> None:
    deltas = plan.get("deltas", [])
    _assert(
        any(
            delta.get("entity") == "Widget"
            and delta.get("field") == "description"
            and delta.get("change") == "removed"
            and delta.get("classification") == "destructive"
            for delta in deltas
        ),
        "dropped field was not classified destructive",
    )
    _assert(
        any(
            delta.get("entity") == "Widget"
            and delta.get("field") == "status"
            and delta.get("change") == "modified"
            and delta.get("classification") == "destructive"
            for delta in deltas
        ),
        "retyped field was not classified destructive",
    )
    _assert(
        any(
            delta.get("entity") == "Widget"
            and delta.get("field") == "priority"
            and delta.get("change") == "added"
            and delta.get("classification") == "unsafe"
            for delta in deltas
        ),
        "required new field without default was not classified unsafe",
    )


def _copy_package(source: Path, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


def _package_snapshot(package_dir: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(package_dir.rglob("*")):
        relative = path.relative_to(package_dir).as_posix()
        if path.is_dir():
            snapshot[f"dir:{relative}"] = ""
        elif path.is_file():
            snapshot[f"file:{relative}"] = _sha256_bytes(
                path.read_bytes()
            )
    return snapshot


def _assert_ka_off_artifacts_absent(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        parts = [part.lower() for part in path.relative_to(root).parts]
        for part in parts:
            if part in FORBIDDEN_KA_OFF_ARTIFACT_NAMES:
                raise AssertionError(
                    f"KA/KS/MCP-off artifact unexpectedly created: {path.relative_to(root)}"
                )


def _assert_no_ka_ks_chatter(outputs: list[tuple[str, str]]) -> None:
    for label, output in outputs:
        for line_number, line in enumerate(output.splitlines(), start=1):
            if _contains_any_segment(line.lower(), FORBIDDEN_KA_OFF_OUTPUT_SEGMENTS):
                raise AssertionError(
                    f"KA/KS/MCP chatter in {label} output line {line_number}: {line}"
                )


def _contains_any_segment(value: str, forbidden: set[str]) -> bool:
    tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if token
    }
    return bool(tokens & forbidden)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    raise SystemExit(main())
