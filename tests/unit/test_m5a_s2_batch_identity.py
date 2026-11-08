"""M5a-S2 internal Batch schema and generated-runtime contract coverage."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.batch_metadata import (
    BATCH_METADATA_SCHEMA_ID,
    PREVIEW_BATCH_METADATA_SCHEMA_VERSION,
    batch_metadata_internal_schema,
    batch_metadata_schema_sql,
    reserved_batch_metadata_objects_in_sql,
)
from appbuilder.generation.build_emitter import emit_build_files
from appbuilder.generation.change_plan import _schema_deltas, build_change_plan
from appbuilder.generation.java_emitter import emit_java_sources
from appbuilder.generation.schema_baseline import build_schema_baseline
from appbuilder.generation.sql_emitter import emit_sql_files
from appbuilder.generation.ui_emitter import _batch_actions, _build_action_card_descriptors
from appbuilder.metadata.translation import build_metadata_project
from appbuilder.target_profiles.catalog import TARGET_PROFILES

_FIXTURE = Path("tests/fixtures/manifest-v2-cut/v2-run-semantics-app-definition.yaml")


def _metadata():
    return build_metadata_project(_FIXTURE)


def _package_bytes(package_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(package_dir).as_posix(): path.read_bytes()
        for path in sorted(package_dir.rglob("*"))
        if path.is_file()
    }


def test_s2_translation_carries_validated_physical_run_id_bound() -> None:
    metadata = _metadata()
    run_semantics = metadata.contracts[0].run_semantics

    assert run_semantics is not None
    assert run_semantics.physical_run_id_column == "run_id"
    assert run_semantics.physical_run_id_max_length == 64
    assert "run_semantics" not in metadata.contracts[0].model_dump()


@pytest.mark.parametrize(
    "target_profile_name",
    ["springboot-legacy-compatible", "springboot-enterprise-postgres-java17"],
)
def test_batch_metadata_singleton_is_profile_specific_and_deterministic(
    target_profile_name: str,
) -> None:
    target_profile = TARGET_PROFILES[target_profile_name]
    first = batch_metadata_internal_schema(target_profile)
    second = batch_metadata_internal_schema(target_profile)
    sql = batch_metadata_schema_sql(target_profile)

    assert first == second
    assert first["id"] == BATCH_METADATA_SCHEMA_ID
    assert first["spring_batch_metadata_schema_version"] == PREVIEW_BATCH_METADATA_SCHEMA_VERSION
    assert len(first["content_sha256"]) == 64
    assert "BATCH_JOB_EXECUTION_PARAMS" in sql
    assert "PARAMETER_VALUE VARCHAR(2500)" in sql
    assert "WRITE_SKIP_COUNT BIGINT" in sql


def test_batch_metadata_collision_scan_ignores_comments_strings_and_unrelated_objects() -> None:
    sql = """\
-- CREATE TABLE BATCH_JOB_INSTANCE (id BIGINT);
INSERT INTO audit_log (message) VALUES ('CREATE SEQUENCE BATCH_JOB_SEQ');
CREATE TABLE reporting_snapshot (id BIGINT);
"""

    assert reserved_batch_metadata_objects_in_sql(sql) == []


def test_baseline_adds_and_retains_batch_metadata_singleton() -> None:
    metadata = _metadata()
    target_profile = TARGET_PROFILES[metadata.target_profile]
    baseline = build_schema_baseline(metadata=metadata, target_profile=target_profile)

    assert baseline["flyway_high_water_mark"] == 4
    assert len(baseline["internal_schemas"]) == 2
    singleton = baseline["internal_schemas"][0]
    assert singleton["id"] == BATCH_METADATA_SCHEMA_ID

    disabled_metadata = copy.deepcopy(metadata)
    disabled_metadata.contracts[0].run_semantics = None
    no_opt_in_baseline = build_schema_baseline(
        metadata=disabled_metadata,
        target_profile=target_profile,
    )
    assert [entry["id"] for entry in no_opt_in_baseline["internal_schemas"]] == [BATCH_METADATA_SCHEMA_ID]
    retained = build_schema_baseline(
        metadata=disabled_metadata,
        target_profile=target_profile,
        previous_baseline=baseline,
    )
    assert retained["internal_schemas"] == baseline["internal_schemas"]
    assert retained["flyway_high_water_mark"] == 4


def test_retained_batch_metadata_rejects_unknown_version_and_fingerprint_drift() -> None:
    metadata = _metadata()
    target_profile = TARGET_PROFILES[metadata.target_profile]
    baseline = build_schema_baseline(metadata=metadata, target_profile=target_profile)

    unknown_version = copy.deepcopy(baseline)
    unknown_version["internal_schemas"][0]["schema_contract_version"] = 99
    with pytest.raises(ValueError, match="Unsupported retained internal schema version"):
        build_schema_baseline(
            metadata=metadata,
            target_profile=target_profile,
            previous_baseline=unknown_version,
        )

    fingerprint_drift = copy.deepcopy(baseline)
    fingerprint_drift["internal_schemas"][0]["content_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint drifted"):
        build_schema_baseline(
            metadata=metadata,
            target_profile=target_profile,
            previous_baseline=fingerprint_drift,
        )


@pytest.mark.parametrize(
    "internal_schemas",
    [
        "not-an-array",
        ["not-an-object"],
        [{"id": ""}],
        [
            {
                "id": "future-schema",
                "schema_contract_version": 1,
                "target_profile": "springboot-legacy-compatible",
                "content_sha256": "not-a-sha256",
            }
        ],
    ],
)
def test_retained_internal_schema_inventory_rejects_malformed_entries(
    internal_schemas: object,
) -> None:
    metadata = _metadata()
    target_profile = TARGET_PROFILES[metadata.target_profile]
    baseline = build_schema_baseline(metadata=metadata, target_profile=target_profile)
    baseline["internal_schemas"] = internal_schemas

    with pytest.raises(ValueError, match="internal_schema|Internal schema"):
        build_schema_baseline(
            metadata=metadata,
            target_profile=target_profile,
            previous_baseline=baseline,
        )


def test_s2_emits_one_flyway_metadata_migration_and_hardened_batch_yaml(tmp_path: Path) -> None:
    metadata = _metadata()
    target_profile = TARGET_PROFILES[metadata.target_profile]
    migrations = emit_sql_files(
        metadata=metadata,
        target_profile=target_profile,
        output_dir=tmp_path,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-test",
    )

    migration = next(path for path in migrations if "pkg_batch_metadata" in path.name)
    content = migration.read_text(encoding="utf-8")
    assert migration.name == "V3__create_pkg_batch_metadata.sql"
    assert "BATCH_JOB_INSTANCE" in content
    assert "WRITE_SKIP_COUNT BIGINT" in content

    emit_build_files(
        metadata=metadata,
        target_profile=target_profile,
        output_dir=tmp_path,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-test",
        emit_test_console=False,
    )
    app_yaml = (tmp_path / "src/main/resources/application.yaml").read_text(encoding="utf-8")
    assert "jdbc:\n      initialize-schema: never" in app_yaml


def test_s2_java_emission_uses_identity_step_and_closed_trigger_contract(tmp_path: Path) -> None:
    metadata = _metadata()
    target_profile = TARGET_PROFILES[metadata.target_profile]
    emit_java_sources(
        metadata=metadata,
        target_profile=target_profile,
        output_dir=tmp_path,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-test",
    )

    root = tmp_path / "src/main/java/com/appbuilder/m5a_run_semantics"
    job_source = (root / "batch/WidgetEodBatchJob.java").read_text(encoding="utf-8")
    controller_source = (
        root / "adapter/inbound/BatchTriggerController.java"
    ).read_text(encoding="utf-8")

    assert ".allowStartIfComplete(true)" in job_source
    assert 'context.putString("frozenBusinessDate", frozenBusinessDate)' in job_source
    assert "jobRepository.updateExecutionContext(execution);" in job_source
    assert 'stagingWriter.clear(runId);' not in job_source
    assert ".addString(\"runId\", runId, true)" in controller_source
    assert ".addLocalDate(\"businessDate\", businessDate, false)" in controller_source
    assert 'Map.entry("widgetEodJob", 64)' in controller_source
    assert "JobRepository" in controller_source
    assert "JobOperator" in controller_source
    assert "batch_instance_completed" in controller_source
    assert "batch_execution_running" in controller_source
    assert "batch_execution_state_changed" in controller_source
    assert "batch_execution_state_unavailable" in controller_source
    assert "ownerVerificationRequired" in controller_source
    assert "requeryRequired" in controller_source
    assert '"jobExecutionId", execution.getId()' in controller_source
    assert "@RequestBody(required = false) JsonNode request" in controller_source
    assert 'request.size() != 2' in controller_source
    assert 'Body must contain only textual runId and businessDate members' in controller_source
    assert "run.at" not in controller_source.split("private ResponseEntity", 1)[0]
    assert "private ResponseEntity<Map<String, Object>> runLegacyJob(Job job)" in controller_source
    assert '.addLong("run.at", System.currentTimeMillis())' in controller_source


@pytest.mark.parametrize(
    ("physical_max_length", "expected_limit"),
    [(8, 8), (None, 2500), (3000, 2500)],
)
def test_s2_controller_uses_the_effective_utf16_run_id_bound(
    physical_max_length: int | None,
    expected_limit: int,
    tmp_path: Path,
) -> None:
    metadata = _metadata()
    run_semantics = metadata.contracts[0].run_semantics
    assert run_semantics is not None
    run_semantics.physical_run_id_max_length = physical_max_length
    emit_java_sources(
        metadata=metadata,
        target_profile=TARGET_PROFILES[metadata.target_profile],
        output_dir=tmp_path,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-bound",
    )
    controller_source = (
        tmp_path
        / "src/main/java/com/appbuilder/m5a_run_semantics/adapter/inbound/BatchTriggerController.java"
    ).read_text(encoding="utf-8")

    assert f'Map.entry("widgetEodJob", {expected_limit})' in controller_source
    assert "runId.length() > runIdLimit" in controller_source
    assert "!runId.equals(runId.strip())" in controller_source


def test_s2_console_action_is_form_json_and_legacy_actions_remain_bodyless() -> None:
    metadata = _metadata()
    opted_in_action = _batch_actions(metadata)

    assert opted_in_action == [
        {
            "entityName": "Widget",
            "label": "Run widgetEodJob",
            "jobName": "widgetEodJob",
            "outputHint": "./m5a_run_semantics-eod",
            "runSemantics": True,
            "effectiveRunIdMax": 64,
        }
    ]
    descriptor = next(
        descriptor.to_dict()
        for descriptor in _build_action_card_descriptors(metadata, [])
        if descriptor.family == "batch"
    )
    assert descriptor["actions"][0]["inputControl"] == "FORM"
    assert descriptor["actions"][0]["inputBinding"] == "JSON_BODY"
    assert [hint["contractName"] for hint in descriptor["hints"][:2]] == [
        "runId",
        "businessDate",
    ]
    assert descriptor["hints"][0]["maxLength"] == 64

    legacy_metadata = copy.deepcopy(metadata)
    legacy_metadata.contracts[0].run_semantics = None
    legacy_descriptor = next(
        descriptor.to_dict()
        for descriptor in _build_action_card_descriptors(legacy_metadata, [])
        if descriptor.family == "batch"
    )
    assert legacy_descriptor["actions"][0]["inputControl"] == "NONE"
    assert legacy_descriptor["actions"][0]["inputBinding"] == "NONE"


def test_s2_internal_apply_lifecycle_retains_one_singleton_migration(
    tmp_path: Path,
) -> None:
    """Exercise the retained S2 singleton through the public S3 apply lifecycle."""

    initial_metadata = _metadata()
    initial_metadata.target_profile = "springboot-enterprise-postgres-java17"
    initial_metadata.contracts[0].run_semantics = None
    package_dir = tmp_path / "managed-package"
    generate_application(
        initial_metadata,
        package_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-initial",
    )
    migration_dir = package_dir / "src/main/resources/db/migration"
    prior_migrations = {
        path.name: path.read_bytes()
        for path in sorted(migration_dir.glob("V*.sql"))
    }
    assert sorted(prior_migrations) == [
        "V1__create_widget_table.sql",
        "V2__create_widget_staging_table.sql",
        "V3__create_pkg_batch_metadata.sql",
    ]

    enabled_metadata = _metadata()
    enabled_metadata.target_profile = initial_metadata.target_profile
    enable_plan = build_change_plan(metadata=enabled_metadata, package_dir=package_dir)
    assert [delta["kind"] for delta in enable_plan["db_migration_deltas"]] == [
        "internal_schema",
    ]
    apply_change_plan(
        metadata=enabled_metadata,
        package_dir=package_dir,
        approved_plan_hash=enable_plan["plan_hash"],
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-enable",
    )
    assert {
        path.name: path.read_bytes()
        for path in sorted(migration_dir.glob("V1__*.sql"))
        + sorted(migration_dir.glob("V2__*.sql"))
        + sorted(migration_dir.glob("V3__*.sql"))
    } == prior_migrations
    assert (migration_dir / "V3__create_pkg_batch_metadata.sql").exists()

    enabled_baseline = json.loads(
        (package_dir / "db/schema-baseline.json").read_text(encoding="utf-8")
    )
    assert enabled_baseline["flyway_high_water_mark"] == 4
    assert enabled_baseline["internal_schemas"][0]["id"] == BATCH_METADATA_SCHEMA_ID

    disabled_metadata = copy.deepcopy(enabled_metadata)
    disabled_metadata.contracts[0].run_semantics = None
    disable_plan = build_change_plan(metadata=disabled_metadata, package_dir=package_dir)
    assert disable_plan["db_migration_deltas"] == []
    apply_change_plan(
        metadata=disabled_metadata,
        package_dir=package_dir,
        approved_plan_hash=disable_plan["plan_hash"],
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-disable",
    )
    disabled_baseline = json.loads(
        (package_dir / "db/schema-baseline.json").read_text(encoding="utf-8")
    )
    assert disabled_baseline["internal_schemas"] == enabled_baseline["internal_schemas"]
    assert disabled_baseline["flyway_high_water_mark"] == 4

    reenable_plan = build_change_plan(metadata=enabled_metadata, package_dir=package_dir)
    assert reenable_plan["db_migration_deltas"] == []
    apply_change_plan(
        metadata=enabled_metadata,
        package_dir=package_dir,
        approved_plan_hash=reenable_plan["plan_hash"],
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-reenable",
    )
    assert sorted(path.name for path in migration_dir.glob("V*.sql")) == [
        "V1__create_widget_table.sql",
        "V2__create_widget_staging_table.sql",
        "V3__create_pkg_batch_metadata.sql",
        "V4__add_m5a_staging_001_unique.sql",
    ]


def test_s2_internal_schema_profile_transition_is_unsafe() -> None:
    metadata = _metadata()
    h2_profile = TARGET_PROFILES["springboot-legacy-compatible"]
    postgres_profile = TARGET_PROFILES["springboot-enterprise-postgres-java17"]
    h2_baseline = build_schema_baseline(metadata=metadata, target_profile=h2_profile)
    postgres_baseline = build_schema_baseline(
        metadata=metadata,
        target_profile=postgres_profile,
        previous_baseline=h2_baseline,
    )

    internal_delta = next(
        delta
        for delta in _schema_deltas(
            previous_baseline=h2_baseline,
            new_baseline=postgres_baseline,
        )
        if delta["kind"] == "internal_schema"
    )
    assert internal_delta["classification"] == "unsafe"


def test_s2_rejects_an_untracked_singleton_migration_before_apply(
    tmp_path: Path,
) -> None:
    initial_metadata = _metadata()
    initial_metadata.target_profile = "springboot-enterprise-postgres-java17"
    initial_metadata.contracts[0].run_semantics = None
    package_dir = tmp_path / "collision-package"
    generate_application(
        initial_metadata,
        package_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-collision",
    )
    collision_path = (
        package_dir
        / "src/main/resources/db/migration/V3__create_pkg_batch_metadata.sql"
    )
    collision_path.write_text("-- unrelated manual migration\n", encoding="utf-8")

    enabled_metadata = _metadata()
    enabled_metadata.target_profile = initial_metadata.target_profile
    plan = build_change_plan(metadata=enabled_metadata, package_dir=package_dir)

    collision = next(
        delta
        for delta in plan["deltas"]
        if delta.get("details", {}).get("schema_id") == "pkg-batch-metadata"
        and delta.get("details", {}).get("issue") == "missing"
    )
    assert collision["classification"] == "unsafe"
    assert collision_path.read_text(encoding="utf-8") == "-- unrelated manual migration\n"


@pytest.mark.parametrize(
    "migration_name",
    ["V7__manual_batch_schema.sql", "R__manual_batch_schema.sql"],
)
def test_s2_rejects_reserved_batch_objects_under_any_flyway_migration_name(
    tmp_path: Path,
    migration_name: str,
) -> None:
    initial_metadata = _metadata()
    initial_metadata.target_profile = "springboot-enterprise-postgres-java17"
    initial_metadata.contracts[0].run_semantics = None
    package_dir = tmp_path / "alternate-name-collision-package"
    generate_application(
        initial_metadata,
        package_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-alternate-name-collision",
    )
    migration_dir = package_dir / "src/main/resources/db/migration"
    collision_path = migration_dir / migration_name
    collision_path.write_text(
        "-- alternate filename intentionally used by this regression\n"
        + batch_metadata_schema_sql(TARGET_PROFILES[initial_metadata.target_profile]),
        encoding="utf-8",
    )
    before = _package_bytes(package_dir)

    enabled_metadata = _metadata()
    enabled_metadata.target_profile = initial_metadata.target_profile
    plan = build_change_plan(metadata=enabled_metadata, package_dir=package_dir)

    collision = next(
        delta
        for delta in plan["deltas"]
        if collision_path.name in delta["message"]
    )
    assert collision["classification"] == "unsafe"
    assert collision["details"]["issue"] == "duplicate"
    assert collision_path.name in collision["details"]["paths"]
    assert reserved_batch_metadata_objects_in_sql(collision_path.read_text()) == [
        "BATCH_JOB_EXECUTION", "BATCH_JOB_EXECUTION_CONTEXT", "BATCH_JOB_EXECUTION_PARAMS",
        "BATCH_JOB_EXECUTION_SEQ", "BATCH_JOB_INSTANCE", "BATCH_JOB_INSTANCE_SEQ",
        "BATCH_STEP_EXECUTION", "BATCH_STEP_EXECUTION_CONTEXT", "BATCH_STEP_EXECUTION_SEQ",
    ]
    with pytest.raises(ValueError, match="Unsafe/destructive"):
        apply_change_plan(
            metadata=enabled_metadata,
            package_dir=package_dir,
            approved_plan_hash=plan["plan_hash"],
            source_manifest="app-definition.yaml",
            generation_run_id="m5a-s2-refused-collision",
        )
    assert _package_bytes(package_dir) == before


def test_s2_rejects_duplicate_internal_schema_ids_without_package_mutation(
    tmp_path: Path,
) -> None:
    metadata = _metadata()
    metadata.target_profile = "springboot-enterprise-postgres-java17"
    metadata.contracts[0].run_semantics = None
    package_dir = tmp_path / "duplicate-internal-schema-package"
    generate_application(
        metadata,
        package_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s2-duplicate-baseline",
    )
    baseline_path = package_dir / "db/schema-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    valid_entry = batch_metadata_internal_schema(TARGET_PROFILES[metadata.target_profile])
    unsupported_entry = copy.deepcopy(valid_entry)
    unsupported_entry["schema_contract_version"] = 99
    baseline["internal_schemas"] = [unsupported_entry, valid_entry]
    baseline_path.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before = _package_bytes(package_dir)

    enabled_metadata = _metadata()
    enabled_metadata.target_profile = metadata.target_profile
    with pytest.raises(ValueError, match="Duplicate internal schema id 'pkg-batch-metadata'"):
        build_change_plan(metadata=enabled_metadata, package_dir=package_dir)
    assert _package_bytes(package_dir) == before
