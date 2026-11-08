from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import zipfile
from contextlib import redirect_stderr
from pathlib import Path

import pytest
import yaml

from appbuilder.cli import main
from appbuilder.contracts import load_project_definition, validate_package
from appbuilder.core.path_safety import ALLOWED_ROOTS_ENV
from appbuilder.generation import generate_application
from appbuilder.mcp.tools.generation import generate_app, translate_project, validate_manifest
from appbuilder.metadata import build_metadata_project

_V1_FIXTURE = Path("tests/fixtures/manifest-v2-cut/v1-rejected-app-definition.yaml")
_RUN_SEMANTICS_FIXTURE = Path(
    "tests/fixtures/manifest-v2-cut/v2-run-semantics-app-definition.yaml"
)


def test_m5a_s1_fixture_extends_manifest_v2_validation_proof(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "run-semantics-package"
    shutil.copytree(_RUN_SEMANTICS_FIXTURE.parent, package_dir)
    manifest_path = package_dir / _RUN_SEMANTICS_FIXTURE.name
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(tmp_path))

    assert validate_package(raw) == []
    definition = load_project_definition(manifest_path)
    assert definition.data_handoffs[0].run_semantics is not None
    assert validate_manifest(str(manifest_path)).valid is True

    metadata = build_metadata_project(manifest_path)
    generated = tmp_path / "generated"
    report = generate_application(metadata, generated, generation_run_id="manifest-v2-s3")
    assert report.harness_report is not None
    assert report.harness_report.passed
    assert any(
        path.name.endswith("__add_m5a_staging_001_unique.sql")
        for path in generated.glob("src/main/resources/db/migration/V*.sql")
    )


def test_reviewed_v1_package_conversion_changes_only_schema_version(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "reviewed-package"
    shutil.copytree(_V1_FIXTURE.parent, package_dir)
    manifest_path = package_dir / _V1_FIXTURE.name
    before_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    source_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    referenced_before = {
        path.relative_to(package_dir).as_posix(): path.read_bytes()
        for path in sorted(package_dir.rglob("*"))
        if path.is_file() and path != manifest_path
    }

    with pytest.raises(ValueError, match=r"schema_version.*1\.0"):
        load_project_definition(manifest_path)

    after_manifest = dict(before_manifest)
    after_manifest["schema_version"] = "2.0"
    manifest_path.write_text(
        yaml.safe_dump(after_manifest, sort_keys=False),
        encoding="utf-8",
    )
    target_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    changed_keys = {
        key
        for key in before_manifest.keys() | after_manifest.keys()
        if before_manifest.get(key) != after_manifest.get(key)
    }
    referenced_after = {
        path.relative_to(package_dir).as_posix(): path.read_bytes()
        for path in sorted(package_dir.rglob("*"))
        if path.is_file() and path != manifest_path
    }

    assert changed_keys == {"schema_version"}
    assert source_manifest_hash != target_manifest_hash
    assert referenced_after == referenced_before
    assert validate_package(after_manifest) == []
    assert load_project_definition(manifest_path).schema_version == "2.0"


@pytest.mark.parametrize(
    "command_args",
    [
        ["generate", "--output", "generated"],
        ["plan", "--package", "generated"],
        [
            "apply",
            "--package",
            "generated",
            "--approved-plan-hash",
            "not-approved",
        ],
    ],
)
def test_cli_package_entry_points_reject_v1_before_processing(
    command_args: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    package_dir = tmp_path / "v1-package"
    shutil.copytree(_V1_FIXTURE.parent, package_dir)
    stderr = io.StringIO()

    with redirect_stderr(stderr):
        exit_code = main(
            [
                command_args[0],
                "--manifest",
                str(package_dir / _V1_FIXTURE.name),
                *command_args[1:],
            ]
        )

    assert exit_code == 1
    assert "schema_version" in stderr.getvalue()
    assert "1.0" in stderr.getvalue()


def test_mcp_raw_and_package_entry_points_reject_v1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "v1-package"
    shutil.copytree(_V1_FIXTURE.parent, package_dir)
    manifest_path = package_dir / _V1_FIXTURE.name
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(tmp_path))

    validation = validate_manifest(str(manifest_path))
    assert validation.valid is False
    assert any("schema_version" in error and "1.0" in error for error in validation.errors)
    with pytest.raises(ValueError, match=r"schema_version.*1\.0"):
        translate_project(str(manifest_path))
    generation = generate_app(str(manifest_path), str(tmp_path / "generated"))
    assert generation.success is False
    assert any("schema_version" in error and "1.0" in error for error in generation.errors)


def test_all_archetypes_emit_the_manifest_v2_provenance_matrix(tmp_path: Path) -> None:
    crud_metadata = build_metadata_project(
        "examples/input-projects/xyz-accounts-modernization/app-definition.yaml"
    )
    crud_metadata.target_profile = "springboot-enterprise-postgres-java17"
    passthrough_metadata = build_metadata_project(
        "examples/input-projects/country-router/app-definition.yaml"
    )
    kafka_metadata = build_metadata_project("tests/fixtures/kafka-integration/manifest.yaml")

    crud = tmp_path / "crud"
    passthrough = tmp_path / "passthrough"
    kafka = tmp_path / "kafka"
    generate_application(crud_metadata, crud, generation_run_id="v2-crud")
    generate_application(passthrough_metadata, passthrough, generation_run_id="v2-passthrough")
    generate_application(kafka_metadata, kafka, generation_run_id="v2-kafka")

    for output_dir in (crud, passthrough, kafka):
        readme = (output_dir / "README.md").read_text(encoding="utf-8")
        pom = (output_dir / "pom.xml").read_text(encoding="utf-8")
        assert "Manifest schema version: `2.0`" in readme
        assert "Manifest schema version: 2.0" in pom

    assert "Manifest schema version: `2.0`" in (
        crud / "agent-context.md"
    ).read_text(encoding="utf-8")
    assert "Manifest schema version: `2.0`" in (
        passthrough / "agent-context.md"
    ).read_text(encoding="utf-8")
    assert not (kafka / "agent-context.md").exists()

    baseline = json.loads((crud / "db/schema-baseline.json").read_text(encoding="utf-8"))
    assert baseline["manifest_schema_version"] == "2.0"
    assert not (passthrough / "db/schema-baseline.json").exists()
    assert not (kafka / "db/schema-baseline.json").exists()

    audit_configs = list(crud.rglob("AuditConfig.java"))
    assert len(audit_configs) == 1
    assert "Manifest schema version: 2.0" in audit_configs[0].read_text(encoding="utf-8")
    assert not list(passthrough.rglob("AuditConfig.java"))
    assert not list(kafka.rglob("AuditConfig.java"))

    deterministic_crud = tmp_path / "crud-deterministic"
    generate_application(
        crud_metadata,
        deterministic_crud,
        generation_run_id="v2-crud",
    )
    provenance_paths = [
        "README.md",
        "agent-context.md",
        "db/schema-baseline.json",
        "src/main/resources/db/migration/V1__create_account_table.sql",
    ]
    for relative_path in provenance_paths:
        assert (crud / relative_path).read_bytes() == (
            deterministic_crud / relative_path
        ).read_bytes()
    deterministic_audit = list(deterministic_crud.rglob("AuditConfig.java"))
    assert len(deterministic_audit) == 1
    assert audit_configs[0].read_bytes() == deterministic_audit[0].read_bytes()


def test_built_wheel_contains_only_active_manifest_schema(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    shutil.copytree("appbuilder", source_dir / "appbuilder")
    shutil.copytree("packaging", source_dir / "packaging")
    for source_file in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(source_file, source_dir / source_file)
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            ".",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=source_dir,
    )
    wheels = list(wheel_dir.glob("appbuilder-*.whl"))
    assert len(wheels) == 1

    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
    assert "appbuilder/schema/manifest-v2.schema.json" in names
    assert "appbuilder/schema/change-plan-v1.schema.json" in names
    assert "appbuilder/schema/manifest-v1.schema.json" not in names
