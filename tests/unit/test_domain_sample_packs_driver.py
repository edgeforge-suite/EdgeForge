from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.smoke import domain_sample_packs as driver


def _proof(pack_id: str, *, archetype: str = "crud") -> dict[str, object]:
    return {
        "pack_id": pack_id,
        "archetype": archetype,
        "target_profile": "springboot-legacy-compatible",
        "expected_entities": ["Account"],
        "expected_manifest_schema_version": "2.0",
        "expected_export_warnings": [],
        "expected_generation_warnings": [],
        "expected_harness_warnings": [],
        "harness_applies": archetype == "crud",
        "min_studio_project_schema_version": "1.0",
        "expected_export_dir": pack_id,
        "expected_exported_artifacts": ["app-definition.yaml"],
    }


def _spec(pack_id: str, *, archetype: str = "crud") -> driver.PackSpec:
    return driver.PackSpec(
        pack_id=pack_id,
        pack_dir=Path("/studio/docs/sample-packs") / pack_id,
        project_path=Path("/studio/project.json"),
        proof=_proof(pack_id, archetype=archetype),
    )


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["test"],
        returncode=returncode,
        stdout=stdout,
    )


def _passed_pack(spec: driver.PackSpec) -> dict[str, object]:
    pack = driver._new_pack_result(spec)
    pack["export"] = {"status": "passed", "warnings": []}
    for name in ("A10", "A11", "A12", "A13", "A14", "A16"):
        pack["checks"][name] = driver._check(True, "passed")
    return pack


def _prepare_pack_tree(pack_root: Path) -> None:
    for pack_id in driver.PACK_IDS:
        pack_dir = pack_root / pack_id
        project_dir = pack_dir / "project"
        project_dir.mkdir(parents=True)
        (project_dir / f"{pack_id}.edgeforge-project.json").write_text(
            '{"studio_project_schema_version": "1.4"}\n',
            encoding="utf-8",
        )
        (pack_dir / "expected-proof.json").write_text(
            json.dumps(_proof(pack_id), indent=2),
            encoding="utf-8",
        )


def test_cli_requires_explicit_studio_checkout(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        driver._build_parser().parse_args([])

    assert exc_info.value.code == 2
    assert "--studio-checkout" in capsys.readouterr().err


@pytest.mark.parametrize("checkout", [Path("relative/studio"), Path("/missing/studio")])
def test_checkout_must_be_absolute_existing_git_worktree(checkout: Path) -> None:
    with pytest.raises(driver.DomainSamplePackError, match="absolute|not a directory"):
        driver.validate_studio_checkout(checkout)


def test_checkout_rejects_non_git_directory(tmp_path: Path) -> None:
    studio = tmp_path / "studio"
    studio.mkdir()

    with pytest.raises(driver.DomainSamplePackError, match="not a Git worktree"):
        driver.validate_studio_checkout(studio.resolve())


def test_checkout_rejects_structurally_invalid_studio_tree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    studio = (tmp_path / "studio").resolve()
    (studio / ".git").mkdir(parents=True)
    monkeypatch.setattr(
        driver,
        "_run_command",
        lambda *args, **kwargs: _completed(0, f"{studio}\n"),
    )

    with pytest.raises(driver.DomainSamplePackError, match="production export source"):
        driver.validate_studio_checkout(studio)


def test_pack_inventory_rejects_unexpected_fourth_pack_before_export(tmp_path: Path) -> None:
    pack_root = tmp_path / "sample-packs"
    _prepare_pack_tree(pack_root)
    (pack_root / "unexpected-fourth-pack").mkdir()

    with pytest.raises(driver.DomainSamplePackError, match="must be exactly"):
        driver.load_pack_specs(pack_root)


def test_pack_inventory_requires_one_project_and_proof_per_pack(tmp_path: Path) -> None:
    pack_root = tmp_path / "sample-packs"
    _prepare_pack_tree(pack_root)
    (pack_root / driver.PACK_IDS[0] / "expected-proof.json").unlink()

    with pytest.raises(driver.DomainSamplePackError, match="expected-proof.json is missing"):
        driver.load_pack_specs(pack_root)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda proof: proof.pop("harness_applies"), "missing harness_applies"),
        (lambda proof: proof.__setitem__("pack_id", "wrong"), "pack_id does not match"),
        (
            lambda proof: proof.__setitem__("min_studio_project_schema_version", 1),
            "must be a non-empty string",
        ),
        (
            lambda proof: proof.__setitem__(
                "min_studio_project_schema_version", "not-a-version"
            ),
            "must use '<major>.<minor>'",
        ),
        (
            lambda proof: proof.__setitem__("expected_generation_warnings", ["drift"]),
            "must remain empty",
        ),
    ],
)
def test_proof_metadata_fails_closed(mutation, message: str) -> None:
    proof = _proof("sample")
    mutation(proof)

    with pytest.raises(driver.DomainSamplePackError, match=message):
        driver._validate_proof("sample", proof)


def test_warning_contract_rejects_unexpected_warning() -> None:
    with pytest.raises(driver.DomainSamplePackError, match="warnings mismatch"):
        driver._require_warning_match("sample", "generation", ["unexpected"], [])


def test_export_result_rejects_unexpected_artifact_before_generation(tmp_path: Path) -> None:
    spec = _spec("sample")
    result = {
        "status": "passed",
        "warnings": [],
        "written": ["app-definition.yaml", "unexpected.txt"],
        "project_dir": str(tmp_path / "sample"),
    }

    with pytest.raises(driver.DomainSamplePackError, match="artifact list mismatch"):
        driver._validate_export_result(
            spec,
            result,
            expected_export_root=tmp_path,
        )


def test_export_result_rejects_output_outside_temporary_root(tmp_path: Path) -> None:
    spec = _spec("sample")
    outside = tmp_path.parent / "escaped-sample"
    result = {
        "status": "passed",
        "warnings": [],
        "written": ["app-definition.yaml"],
        "project_dir": str(outside),
    }

    with pytest.raises(driver.DomainSamplePackError, match="run-specific output directory"):
        driver._validate_export_result(
            spec,
            result,
            expected_export_root=tmp_path,
        )


def test_second_export_cannot_alias_the_first_run_directory(tmp_path: Path) -> None:
    spec = _spec("sample")
    first_root = tmp_path / "exports" / "run-1" / spec.pack_id
    second_root = tmp_path / "exports" / "run-2" / spec.pack_id
    first_dir = first_root / "sample"
    first_dir.mkdir(parents=True)
    (first_dir / "app-definition.yaml").write_text(
        "schema_version: '2.0'\n",
        encoding="utf-8",
    )
    result = {
        "status": "passed",
        "warnings": [],
        "written": ["app-definition.yaml"],
        "project_dir": str(first_dir),
    }

    assert driver._validate_export_result(
        spec,
        result,
        expected_export_root=first_root,
    ) == first_dir.resolve()
    with pytest.raises(driver.DomainSamplePackError, match="run-specific output directory"):
        driver._validate_export_result(
            spec,
            result,
            expected_export_root=second_root,
        )


def test_harness_applicable_path_requires_pass_and_zero_warnings() -> None:
    spec = _spec("sample")
    harness = SimpleNamespace(passed=True, warnings=[], errors=[])

    result = driver._validate_harness(spec, harness)

    assert result["status"] == "passed"


def test_harness_not_applicable_path_requires_no_report() -> None:
    spec = _spec("sample", archetype="passthrough-router")

    result = driver._validate_harness(spec, None)

    assert result["status"] == "not-applicable"
    with pytest.raises(driver.DomainSamplePackError, match="must not run"):
        driver._validate_harness(spec, SimpleNamespace())


def test_evidence_trail_normalizes_only_allowlisted_fields() -> None:
    first = {
        "manifest_revision_id": "one",
        "exported_at": "2026-01-01T00:00:00Z",
        "stable": "same",
    }
    second = {
        "manifest_revision_id": "two",
        "exported_at": "2026-02-01T00:00:00Z",
        "stable": "same",
    }

    assert driver._normalize_volatile_export(
        "evidence-trail.json", json.dumps(first).encode()
    ) == driver._normalize_volatile_export(
        "evidence-trail.json", json.dumps(second).encode()
    )

    second["stable"] = "changed"
    assert driver._normalize_volatile_export(
        "evidence-trail.json", json.dumps(first).encode()
    ) != driver._normalize_volatile_export(
        "evidence-trail.json", json.dumps(second).encode()
    )


def test_studio_project_normalization_is_narrow_and_recursive_only_for_revisions() -> None:
    base = {
        "updated_at": "one",
        "saved_at": "one",
        "last_export_path": "/one",
        "manifest_revisions": [
            {"revision_id": "one", "exported_at": "one", "export_path": "/one"}
        ],
        "custom_timestamp": "stable",
    }
    changed = json.loads(json.dumps(base))
    changed.update(updated_at="two", saved_at="two", last_export_path="/two")
    changed["manifest_revisions"][0].update(
        revision_id="two", exported_at="two", export_path="/two"
    )

    normalized = driver._normalize_volatile_export(
        "studio-project.json", json.dumps(base).encode()
    )
    assert normalized == driver._normalize_volatile_export(
        "studio-project.json", json.dumps(changed).encode()
    )

    changed["custom_timestamp"] = "not-normalized"
    assert normalized != driver._normalize_volatile_export(
        "studio-project.json", json.dumps(changed).encode()
    )


def test_a16_negative_control_rejects_unapproved_file_drift(tmp_path: Path) -> None:
    spec = _spec("sample")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "app-definition.yaml").write_text("first\n", encoding="utf-8")
    (second / "app-definition.yaml").write_text("second\n", encoding="utf-8")

    with pytest.raises(driver.DomainSamplePackError, match="unapproved repeated-export drift"):
        driver._compare_exports(spec, first, second)


def test_studio_subprocess_failure_is_actionable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        driver,
        "_run_command",
        lambda *args, **kwargs: _completed(1, "export exploded"),
    )

    with pytest.raises(driver.DomainSamplePackError, match="export exploded"):
        driver._run_studio_export(
            specs=[_spec(pack_id) for pack_id in driver.PACK_IDS],
            studio_checkout=tmp_path,
            studio_python=Path("/python"),
            export_root=tmp_path / "exports",
            helper_root=tmp_path / "helper",
        )


def test_engine_stages_pass_for_applicable_harness(tmp_path: Path, monkeypatch) -> None:
    spec = _spec("sample")
    export_dir = tmp_path / "export"
    generated_dir = tmp_path / "generated"
    export_dir.mkdir()
    generated_dir.mkdir()
    (export_dir / "app-definition.yaml").write_text(
        """\
schema_version: "2.0"
app_archetype: crud
target_profile: springboot-legacy-compatible
""",
        encoding="utf-8",
    )
    pack = driver._new_pack_result(spec)
    harness = SimpleNamespace(passed=True, warnings=[], errors=[])
    independence = SimpleNamespace(
        checks=[SimpleNamespace(name="repository-boundary")],
        packaged_jar="target/sample.jar",
        baseline_generated_source_count=1,
    )
    monkeypatch.setattr(driver, "validate_package_or_raise", lambda manifest: None)
    monkeypatch.setattr(
        driver,
        "build_metadata_project",
        lambda path: SimpleNamespace(entities=[SimpleNamespace(name="Account")]),
    )
    monkeypatch.setattr(
        driver,
        "_run_generation_cli",
        lambda **kwargs: driver.CliGenerationResult(
            file_count=1,
            warnings=[],
            harness_status="passed",
        ),
    )
    monkeypatch.setattr(driver, "run_compatibility_harness", lambda *args: harness)
    monkeypatch.setattr(
        driver,
        "verify_generated_app_independence",
        lambda *args, **kwargs: independence,
    )
    monkeypatch.setattr(
        driver,
        "_run_maven_build",
        lambda *args, **kwargs: {
            "command": "mvn -q clean verify",
            "java_baseline": "17",
            "java_version": "17",
            "maven_version": "Maven",
            "maven_java": "Java version: 17",
        },
    )

    driver._run_engine_acceptance(
        spec=spec,
        export_dir=export_dir,
        generated_dir=generated_dir,
        temp_root=tmp_path,
        pack=pack,
    )

    assert {pack["checks"][name]["status"] for name in ("A10", "A11", "A12", "A13", "A14")} == {
        "passed"
    }
    assert pack["independence"]["packaged_jar"] == "target/sample.jar"
    assert pack["checks"]["A13"]["detail"] == (
        "mvn -q clean verify passed with Java 17"
    )


def test_cli_only_generation_failure_cannot_be_masked_by_direct_apis(
    tmp_path: Path,
    monkeypatch,
) -> None:
    spec = _spec("sample")
    export_dir = tmp_path / "export"
    generated_dir = tmp_path / "generated"
    export_dir.mkdir()
    (export_dir / "app-definition.yaml").write_text(
        "schema_version: '2.0'\napp_archetype: crud\n"
        "target_profile: springboot-legacy-compatible\n",
        encoding="utf-8",
    )
    pack = driver._new_pack_result(spec)
    direct_api_called = False

    monkeypatch.setattr(driver, "validate_package_or_raise", lambda manifest: None)

    def direct_api(_path):
        nonlocal direct_api_called
        direct_api_called = True
        return SimpleNamespace(entities=[SimpleNamespace(name="Account")])

    monkeypatch.setattr(driver, "build_metadata_project", direct_api)
    monkeypatch.setattr(
        driver,
        "_run_command",
        lambda *args, **kwargs: _completed(23, "ERROR controlled CLI-only failure"),
    )

    driver._run_engine_acceptance(
        spec=spec,
        export_dir=export_dir,
        generated_dir=generated_dir,
        temp_root=tmp_path,
        pack=pack,
    )

    assert pack["checks"]["A11"]["status"] == "failed"
    assert "controlled CLI-only failure" in pack["checks"]["A11"]["error"]
    assert direct_api_called is False


def test_generation_cli_uses_documented_validate_schema_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    generated = tmp_path / "generated"
    seen: list[str] = []

    def run(command, **kwargs):
        seen.extend(command)
        return _completed(
            0,
            "Generated application at: temporary\n"
            "Files created: 7\n"
            "Harness: PASSED (static compatibility checks)\n",
        )

    monkeypatch.setattr(driver, "_run_command", run)

    result = driver._run_generation_cli(
        manifest_path=manifest,
        generated_dir=generated,
        temp_root=tmp_path,
    )

    assert seen[1:4] == ["-m", "appbuilder.cli", "generate"]
    assert "--validate-schema" in seen
    assert result == driver.CliGenerationResult(
        file_count=7,
        warnings=[],
        harness_status="passed",
    )


def test_generation_cli_surfaces_reported_warnings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        driver,
        "_run_command",
        lambda *args, **kwargs: _completed(
            0,
            "Generated application at: temporary\n"
            "Files created: 3\n"
            "Harness: NOT RUN\n"
            "Generation warnings:\n"
            "  - controlled warning\n",
        ),
    )

    result = driver._run_generation_cli(
        manifest_path=tmp_path / "app-definition.yaml",
        generated_dir=tmp_path / "generated",
        temp_root=tmp_path,
    )

    assert result.warnings == ["controlled warning"]
    assert result.harness_status == "not-run"


@pytest.mark.parametrize(
    ("profile_id", "expected"),
    [
        (
            "springboot-standard-enterprise",
            ["mvn", "-q", "clean", "package", "-DskipTests"],
        ),
        (
            "springboot-enterprise-postgres-java17",
            ["mvn", "-q", "clean", "package", "-DskipTests"],
        ),
        (
            "springboot-legacy-compatible",
            ["mvn", "-q", "clean", "verify"],
        ),
    ],
)
def test_maven_command_is_selected_from_profile_database(
    profile_id: str,
    expected: list[str],
) -> None:
    assert driver._maven_command_for_profile(driver.TARGET_PROFILES[profile_id]) == expected


def test_maven_build_reports_exact_command_and_propagates_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java_home = tmp_path / "jdk"
    java_bin = java_home / "bin" / "java"
    java_bin.parent.mkdir(parents=True)
    java_bin.write_text("", encoding="utf-8")
    command = ["mvn", "-q", "clean", "verify"]
    seen: list[list[str]] = []

    monkeypatch.setattr(driver, "_java_home_for", lambda *args, **kwargs: java_home)
    monkeypatch.setattr(driver, "_java_major", lambda path: "17")

    def run(command_arg, **kwargs):
        seen.append(command_arg)
        if command_arg == command:
            return _completed(1, "controlled Maven failure")
        if command_arg == ["mvn", "-version"]:
            return _completed(0, "Apache Maven test\nJava version: 17\n")
        return _completed(0, 'openjdk version "17"\n')

    monkeypatch.setattr(driver, "_run_command", run)

    with pytest.raises(driver.DomainSamplePackError, match="controlled Maven failure"):
        driver._run_maven_build(
            tmp_path,
            java_baseline="17",
            maven_command=command,
            temp_root=tmp_path,
        )

    assert seen[-1] == command


@pytest.mark.parametrize(
    ("maven_output", "message"),
    [
        ("Apache Maven test\n", "exactly one Java version line"),
        ("Apache Maven test\nJava version: unknown\n", "malformed Java version"),
        (
            "Apache Maven test\nJava version: 21.0.1, vendor: Test\n",
            "Maven uses Java 21, expected Java 17",
        ),
    ],
)
def test_maven_build_rejects_missing_malformed_or_mismatched_effective_java(
    tmp_path: Path,
    monkeypatch,
    maven_output: str,
    message: str,
) -> None:
    java_home = tmp_path / "jdk"
    java_bin = java_home / "bin" / "java"
    java_bin.parent.mkdir(parents=True)
    java_bin.write_text("", encoding="utf-8")
    build_command = ["mvn", "-q", "clean", "verify"]
    seen: list[list[str]] = []

    monkeypatch.setattr(driver, "_java_home_for", lambda *args, **kwargs: java_home)
    monkeypatch.setattr(driver, "_java_major", lambda path: "17")

    def run(command_arg, **kwargs):
        seen.append(command_arg)
        if command_arg == ["mvn", "-version"]:
            return _completed(0, maven_output)
        return _completed(0, 'openjdk version "17"\n')

    monkeypatch.setattr(driver, "_run_command", run)

    with pytest.raises(driver.DomainSamplePackError, match=message):
        driver._run_maven_build(
            tmp_path,
            java_baseline="17",
            maven_command=build_command,
            temp_root=tmp_path,
        )

    assert build_command not in seen


def test_run_cleans_temporary_output_on_success(tmp_path: Path, monkeypatch) -> None:
    studio = tmp_path / "studio"
    engine = tmp_path / "engine"
    studio.mkdir()
    engine.mkdir()
    specs = [_spec(pack_id) for pack_id in driver.PACK_IDS]
    seen_temp: list[Path] = []

    monkeypatch.setattr(driver, "REPO_ROOT", engine)
    monkeypatch.setattr(driver, "validate_studio_checkout", lambda path: studio)
    monkeypatch.setattr(driver, "load_pack_specs", lambda path: specs)
    monkeypatch.setattr(driver, "_git_sha", lambda repo: f"sha-{repo.name}")
    monkeypatch.setattr(driver, "_git_status", lambda repo: b"")
    monkeypatch.setattr(driver, "_python_for_repo", lambda *args, **kwargs: Path("/python"))
    monkeypatch.setattr(driver, "_python_version", lambda path: "Python test")
    monkeypatch.setattr(driver, "_evidence_staleness_warnings", lambda **kwargs: [])

    def execute(**kwargs):
        seen_temp.append(kwargs["temp_root"])
        return {spec.pack_id: _passed_pack(spec) for spec in specs}

    monkeypatch.setattr(driver, "_execute_acceptance", execute)

    report = driver.run_acceptance(studio, temp_parent=tmp_path)

    assert report["status"] == "passed"
    assert report["repository_status"] == {
        "engine_unchanged": True,
        "studio_unchanged": True,
        "temporary_output_removed": True,
    }
    assert seen_temp and not seen_temp[0].exists()


def test_run_cleans_temporary_output_after_failure(tmp_path: Path, monkeypatch) -> None:
    studio = tmp_path / "studio"
    engine = tmp_path / "engine"
    studio.mkdir()
    engine.mkdir()
    seen_temp: list[Path] = []

    monkeypatch.setattr(driver, "REPO_ROOT", engine)
    monkeypatch.setattr(driver, "validate_studio_checkout", lambda path: studio)
    monkeypatch.setattr(driver, "load_pack_specs", lambda path: [_spec("sample")])
    monkeypatch.setattr(driver, "_git_sha", lambda repo: f"sha-{repo.name}")
    monkeypatch.setattr(driver, "_git_status", lambda repo: b"")
    monkeypatch.setattr(driver, "_python_for_repo", lambda *args, **kwargs: Path("/python"))
    monkeypatch.setattr(driver, "_python_version", lambda path: "Python test")
    monkeypatch.setattr(driver, "_evidence_staleness_warnings", lambda **kwargs: [])

    def fail(**kwargs):
        seen_temp.append(kwargs["temp_root"])
        raise RuntimeError("controlled failure")

    monkeypatch.setattr(driver, "_execute_acceptance", fail)

    report = driver.run_acceptance(studio, temp_parent=tmp_path)

    assert report["status"] == "failed"
    assert "controlled failure" in report["error"]
    assert report["repository_status"]["temporary_output_removed"] is True
    assert seen_temp and not seen_temp[0].exists()


def test_repository_status_drift_fails_a15(tmp_path: Path, monkeypatch) -> None:
    studio = tmp_path / "studio"
    engine = tmp_path / "engine"
    studio.mkdir()
    engine.mkdir()
    specs = [_spec(pack_id) for pack_id in driver.PACK_IDS]
    statuses = iter([b"", b"", b"engine-after", b""])

    monkeypatch.setattr(driver, "REPO_ROOT", engine)
    monkeypatch.setattr(driver, "validate_studio_checkout", lambda path: studio)
    monkeypatch.setattr(driver, "load_pack_specs", lambda path: specs)
    monkeypatch.setattr(driver, "_git_sha", lambda repo: f"sha-{repo.name}")
    monkeypatch.setattr(driver, "_git_status", lambda repo: next(statuses))
    monkeypatch.setattr(driver, "_python_for_repo", lambda *args, **kwargs: Path("/python"))
    monkeypatch.setattr(driver, "_python_version", lambda path: "Python test")
    monkeypatch.setattr(driver, "_evidence_staleness_warnings", lambda **kwargs: [])
    monkeypatch.setattr(
        driver,
        "_execute_acceptance",
        lambda **kwargs: {spec.pack_id: _passed_pack(spec) for spec in specs},
    )

    report = driver.run_acceptance(studio, temp_parent=tmp_path)

    assert report["status"] == "failed"
    assert report["repository_status"]["engine_unchanged"] is False
    assert all(pack["checks"]["A15"]["status"] == "failed" for pack in report["packs"].values())


@pytest.mark.parametrize(
    ("dirty_name", "message"),
    [
        ("engine", "Engine checkout must be clean"),
        ("studio", "Studio checkout must be clean"),
    ],
)
def test_initial_repository_dirtiness_fails_before_acceptance(
    tmp_path: Path,
    monkeypatch,
    dirty_name: str,
    message: str,
) -> None:
    studio = tmp_path / "studio"
    engine = tmp_path / "engine"
    studio.mkdir()
    engine.mkdir()
    specs = [_spec(pack_id) for pack_id in driver.PACK_IDS]
    acceptance_called = False

    monkeypatch.setattr(driver, "REPO_ROOT", engine)
    monkeypatch.setattr(driver, "validate_studio_checkout", lambda path: studio)
    monkeypatch.setattr(driver, "load_pack_specs", lambda path: specs)
    monkeypatch.setattr(driver, "_git_sha", lambda repo: f"sha-{repo.name}")
    monkeypatch.setattr(
        driver,
        "_git_status",
        lambda repo: b"uncommitted" if repo == {"engine": engine, "studio": studio}[dirty_name] else b"",
    )

    def execute(**kwargs):
        nonlocal acceptance_called
        acceptance_called = True
        return {}

    monkeypatch.setattr(driver, "_execute_acceptance", execute)

    with pytest.raises(driver.DomainSamplePackError, match=message):
        driver.run_acceptance(studio, temp_parent=tmp_path)

    assert acceptance_called is False


def test_head_movement_with_clean_status_fails_a15(tmp_path: Path, monkeypatch) -> None:
    studio = tmp_path / "studio"
    engine = tmp_path / "engine"
    studio.mkdir()
    engine.mkdir()
    specs = [_spec(pack_id) for pack_id in driver.PACK_IDS]
    shas = {
        engine: iter(["engine-before", "engine-after"]),
        studio: iter(["studio-head", "studio-head"]),
    }

    monkeypatch.setattr(driver, "REPO_ROOT", engine)
    monkeypatch.setattr(driver, "validate_studio_checkout", lambda path: studio)
    monkeypatch.setattr(driver, "load_pack_specs", lambda path: specs)
    monkeypatch.setattr(driver, "_git_sha", lambda repo: next(shas[repo]))
    monkeypatch.setattr(driver, "_git_status", lambda repo: b"")
    monkeypatch.setattr(driver, "_python_for_repo", lambda *args, **kwargs: Path("/python"))
    monkeypatch.setattr(driver, "_python_version", lambda path: "Python test")
    monkeypatch.setattr(driver, "_evidence_staleness_warnings", lambda **kwargs: [])
    monkeypatch.setattr(
        driver,
        "_execute_acceptance",
        lambda **kwargs: {spec.pack_id: _passed_pack(spec) for spec in specs},
    )

    report = driver.run_acceptance(studio, temp_parent=tmp_path)

    assert report["status"] == "failed"
    assert report["repository_status"]["engine_unchanged"] is False
    assert all(
        pack["checks"]["A15"]["error"] == "Engine HEAD changed during acceptance"
        for pack in report["packs"].values()
    )


def test_summary_and_structured_json_are_deterministic() -> None:
    report = {
        "status": "failed",
        "engine_sha": "engine-sha",
        "studio_sha": "studio-sha",
        "packs": {},
        "warnings": ["evidence stale"],
        "error": "controlled",
    }

    assert driver._human_summary(report) == driver._human_summary(report)
    assert json.dumps(report, sort_keys=True) == json.dumps(report, sort_keys=True)


def test_temporary_paths_are_sanitized_from_report_messages(tmp_path: Path) -> None:
    message = f"failure under {tmp_path}/generated/sample"

    assert driver._sanitize_message(message, tmp_path) == (
        "failure under <temp-root>/generated/sample"
    )
