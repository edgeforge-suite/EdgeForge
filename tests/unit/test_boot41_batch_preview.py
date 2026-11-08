"""Effective Batch preview behavior and unchanged shipped-profile output."""

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

from appbuilder.generation import generate_application
from appbuilder.target_profiles.catalog import TARGET_PROFILES
from scripts.smoke.boot41_batch_cases import CASES, case_metadata
from scripts.smoke.boot41_batch_preview_proof import PROFILES, trigger_value
from tests.unit.test_boot41_preview import _tree_digest

# Current IDs all select the proven Batch 6 path; historical package receipts
# are separate portable refusal controls, not regenerated Boot 3 expectations.
DEFAULT_PROFILES = tuple(TARGET_PROFILES)
ALL_PROFILES = tuple(TARGET_PROFILES)


def _generate(case, profile, output):
    return generate_application(
        case_metadata(case, profile),
        output,
        source_manifest="batch-preview/" + case,
        generation_run_id="boot41-batch-proof",
    )


@pytest.mark.parametrize("case", ["ordinary", "m5a"])
@pytest.mark.parametrize(
    "profile", ALL_PROFILES
)
def test_domain_batch_type_names_are_not_rewritten(tmp_path, case, profile):
    from appbuilder.contracts import validate_package
    from appbuilder.metadata import build_metadata_project

    fixture = Path(f"tests/fixtures/boot41-batch/names-{case}-app-definition.yaml")
    assert validate_package(yaml.safe_load(fixture.read_text())) == []
    metadata = build_metadata_project(fixture)
    assert {entity.name for entity in metadata.entities} == {"JobLauncher", "JobExplorer"}
    metadata.target_profile = profile
    app = tmp_path / "app"
    assert generate_application(metadata, app).harness_report.passed
    for name in ("JobLauncher", "JobExplorer"):
        batch = next(app.rglob(f"{name}EodBatchJob.java")).read_text()
        assert f"RepositoryItemReader<{name}>" in batch
        assert f"ItemWriter<{name}>" in batch
        assert f".domain.{name};" in batch
        assert "RepositoryItemReader<JobOperator>" not in batch
        assert "RepositoryItemReader<JobRepository>" not in batch
    controller = next(app.rglob("BatchTriggerController.java")).read_text()
    preview = TARGET_PROFILES[profile].experimental_boot41
    assert f"private final {'JobOperator' if preview else 'JobLauncher'} jobLauncher;" in controller
    assert f"jobLauncher.{'start' if preview else 'run'}(job, params)" in controller
    assert f"execution.{'getJobInstanceId' if preview else 'getJobId'}()" in controller
    if case == "m5a":
        assert f"private final {'JobRepository' if preview else 'JobExplorer'} jobExplorer;" in controller
        assert f".{'isString' if preview else 'isTextual'}()" in controller
        assert f".{'stringValue' if preview else 'textValue'}()" in controller


def test_batch_import_selection_does_not_rewrite_rendered_body():
    from appbuilder.generation.java_emitter import _batch_java_file

    body = [
        "RepositoryItemReader<JobLauncher> launcher;",
        "RepositoryItemReader<JobExplorer> explorer;",
        "RepositoryItemReader<RuntimeException> domainException;",
        "catch (java.lang.RuntimeException exception) {}",
        'String label = "JobLauncher JobExplorer jobLauncher.run(job, params)";',
        "domain.isTextual(); domain.textValue(); execution.getJobId();",
    ]
    rendered = _batch_java_file(
        package_name="synthetic.domain",
        imports=["synthetic.domain.JobLauncher", "synthetic.domain.JobExplorer"],
        body=body,
        source_manifest="synthetic",
        target_profile=PROFILES[0][0],
        generation_run_id="names-regression",
    )
    for line in body:
        assert line in rendered


@pytest.mark.parametrize("profile", ["springboot-legacy-compatible", PROFILES[0][0]])
@pytest.mark.parametrize("names", [("Set", "HashSet"), ("JobExecution", "JobParameters"),
                                   ("JobLauncher", "RuntimeException")])
def test_history_helper_names_preserve_valid_domain_types(tmp_path, profile, names):
    from appbuilder.contracts import validate_package
    from appbuilder.metadata import build_metadata_project
    from scripts.smoke.boot41_batch_name_collision_proof import history_name_fixture

    fixture = history_name_fixture(tmp_path, *names)
    assert validate_package(yaml.safe_load(fixture.read_text())) == []
    metadata = build_metadata_project(fixture)
    metadata.target_profile = profile
    app = tmp_path / "app"
    assert generate_application(metadata, app).harness_report.passed
    for name in names:
        source = next(app.rglob(f"{name}EodBatchJob.java")).read_text()
        assert f"RepositoryItemReader<{name}>" in source
        assert f"ItemWriter<{name}>" in source
        imports = re.findall(r"^import ([\w.]+);$", source, re.MULTILINE)
        assert sum(value.rsplit(".", 1)[-1] == name for value in imports) == 1
        assert f".domain.{name};" in source
        if name == "RuntimeException":
            assert "catch (java.lang.RuntimeException exception)" in source
            assert "catch (RuntimeException exception)" not in source


@pytest.mark.parametrize("profile", ALL_PROFILES)
@pytest.mark.parametrize("case", CASES)
def test_current_batch_generation_deterministic_and_explicit(tmp_path, case, profile):
    app, repeat = tmp_path / "app", tmp_path / "repeat"
    assert _generate(case, profile, app).harness_report.passed
    assert _generate(case, profile, repeat).harness_report.passed
    assert _tree_digest(app) == _tree_digest(repeat)
    assert "<version>4.1.1</version>" in (app / "pom.xml").read_text()
    assert "spring-boot-starter-batch-jdbc" in (app / "pom.xml").read_text()
    if case in {"m5a", "mixed"}:
        source = next(app.rglob("WidgetEodBatchJob.java")).read_text()
        assert "getJobExecutions(execution.getJobInstance())" in source
        assert "prior.getId() < origin.getId()" in source
        assert "authoritativeBusinessDate(execution, history)" in source
        assert "frozenBusinessDate = requestedBusinessDate.toString()" not in source


@pytest.mark.parametrize("profile,_java", PROFILES)
@pytest.mark.parametrize("case", CASES)
def test_fresh_jdbc_jobs_and_repeat_regeneration(tmp_path, case, profile, _java):
    from appbuilder.generation.batch_metadata import batch_metadata_schema_sql

    app = tmp_path / "app"
    assert _generate(case, profile, app).harness_report.passed
    before = _tree_digest(app)
    _generate(case, profile, tmp_path / "repeat")
    _generate(case, profile, app)
    assert _tree_digest(app) == _tree_digest(tmp_path / "repeat") == before
    pom = (app / "pom.xml").read_text()
    assert "spring-boot-starter-batch-jdbc" in pom
    yaml = (app / "src/main/resources/application.yaml").read_text()
    assert "initialize-schema: never" in yaml
    baseline = json.loads((app / "db/schema-baseline.json").read_text())
    batch = next(x for x in baseline["internal_schemas"] if x["id"] == "pkg-batch-metadata")
    sql = batch_metadata_schema_sql(TARGET_PROFILES[profile])
    assert batch["spring_batch_metadata_schema_version"] == "6.0.5"
    payload = {
        "schema_contract_version": 1,
        "target_profile": profile,
        "spring_batch_metadata_schema_version": "6.0.5",
        "sql_statements": [re.sub(r"\s+", " ", s).strip() for s in sql.split(";") if s.strip()],
    }
    assert (
        batch["content_sha256"]
        == hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    migrations = list((app / "src/main/resources/db/migration").glob("*batch_metadata*.sql"))
    assert len(migrations) == 1
    assert sql in migrations[0].read_text()
    java = "\n".join(x.read_text() for x in app.rglob("*.java"))
    assert "org.springframework.batch.core.launch.JobOperator" in java
    assert "new RepositoryItemReader<>(" in java
    assert "reader.setName(" in java
    assert "reader.setRepository(" not in java
    assert "@EnableBatchProcessing" not in java
    assert "DefaultBatchConfiguration" not in java
    assert "jobLauncher.recover" not in java
    if case in {"m5a", "mixed"}:
        assert "tools.jackson.databind.JsonNode" in java
        assert '.addString("runId", runId, true)' in java
        assert '.addLocalDate("businessDate", businessDate, false)' in java


@pytest.mark.parametrize("case", CASES)
def test_no_batch5_package_transition_or_mutation(tmp_path, case):
    app = tmp_path / "app"
    from tests.unit.test_boot41_promotion import RECEIPT, retained_package
    old = next(c for c in RECEIPT["cases"] if c["shape"] == ("m5a" if case in {"m5a", "mixed"} else "ordinary") and c["profile"] == "springboot-legacy-compatible")
    retained_package(app, old)
    before = _tree_digest(app)
    with pytest.raises(ValueError, match="Unsupported existing package transition"):
        _generate(case, PROFILES[0][0], app)
    assert _tree_digest(app) == before


def test_modified_retained_batch_sql_fails_before_writes(tmp_path):
    app = tmp_path / "app"
    _generate("ordinary", PROFILES[0][0], app)
    migration = next((app / "src/main/resources/db/migration").glob("*batch_metadata*.sql"))
    migration.write_text(migration.read_text() + "\nCREATE TABLE unrelated (id INT);\n")
    before = _tree_digest(app)
    with pytest.raises(ValueError):
        _generate("ordinary", PROFILES[0][0], app)
    assert _tree_digest(app) == before


@pytest.mark.parametrize("case", ["m5a", "ordinary"])
def test_apply_cannot_adopt_batch5_as_preview(tmp_path, case):
    from appbuilder.generation.apply import apply_change_plan
    from appbuilder.generation.change_plan import build_change_plan

    app = tmp_path / "app"
    from tests.unit.test_boot41_promotion import RECEIPT, retained_package
    old = next(c for c in RECEIPT["cases"] if c["shape"] == case and c["profile"] == "springboot-legacy-compatible")
    retained_package(app, old)
    metadata = case_metadata(case, PROFILES[0][0])
    before = _tree_digest(app)
    with pytest.raises(ValueError, match="Unsupported existing package transition"):
        build_change_plan(metadata=metadata, package_dir=app)
    with pytest.raises(ValueError, match="Unsupported existing package transition"):
        apply_change_plan(metadata=metadata, package_dir=app, approved_plan_hash="old-plan")
    assert _tree_digest(app) == before


def test_same_preview_additive_apply_keeps_batch_migration(tmp_path):
    from appbuilder.generation.apply import apply_change_plan
    from appbuilder.generation.change_plan import build_change_plan

    app = tmp_path / "app"
    metadata = case_metadata("ordinary", PROFILES[0][0])
    _generate("ordinary", PROFILES[0][0], app)
    migration = next((app / "src/main/resources/db/migration").glob("*batch_metadata*.sql"))
    before = migration.read_bytes()
    plan = build_change_plan(metadata=metadata, package_dir=app)
    assert plan["db_migration_deltas"] == []
    apply_change_plan(
        metadata=metadata,
        package_dir=app,
        approved_plan_hash=plan["plan_hash"],
        source_manifest="batch-preview/ordinary",
        generation_run_id="boot41-batch-proof",
    )
    assert migration.read_bytes() == before


def test_m5a_same_job_file_is_rejected_before_output_mutation(tmp_path):
    from appbuilder.generation.engine import require_supported_preview_input
    from appbuilder.mapping import MappingDirection

    metadata = case_metadata("mixed", PROFILES[0][0])
    for mapping in metadata.mappings:
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM:
            mapping.source_path = "Widget.payloadKey"
    output = tmp_path / "untouched"
    output.mkdir()
    (output / "sentinel").write_text("keep")
    with pytest.raises(ValueError, match="cannot share an EOD file job"):
        require_supported_preview_input(metadata)
    with pytest.raises(ValueError, match="cannot share an EOD file job"):
        generate_application(metadata, output)
    assert list(output.iterdir()) == [output / "sentinel"]
    assert (output / "sentinel").read_text() == "keep"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("jobId", "1"),
        ("jobId", True),
        ("jobId", 0),
        ("startTime", "pending"),
        ("startTime", 123),
        ("startTime", "2026-99-27T12:00:00"),
        ("startTime", "2026-09-27T29:00:00"),
    ],
)
def test_wire_comparison_does_not_mask_type_or_identity(field, bad):
    value = {
        "jobName": "widgetEodJob",
        "jobId": 1,
        "startTime": "2026-09-27T12:01:02",
        "status": "COMPLETED",
        "exitCode": "COMPLETED",
        field: bad,
    }
    with pytest.raises(AssertionError):
        trigger_value((200, {"content-type": "application/json"}, json.dumps(value).encode()))


def test_error_comparison_retains_meaningful_values():
    value = {"error": "Job not found: other", "available": ["widgetEodJob"]}
    assert (
        trigger_value((404, {"content-type": "application/json"}, json.dumps(value).encode()))[2]
        == value
    )
