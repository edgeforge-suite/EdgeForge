"""M5a-S3 staging idempotency, retained identity, and public execution coverage."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.change_plan import build_change_plan
from appbuilder.generation.java_emitter import emit_java_sources
from appbuilder.generation.schema_baseline import build_schema_baseline
from appbuilder.generation.sql_emitter import emit_sql_files
from appbuilder.generation.staging_idempotency import staging_unique_constraints_in_sql
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


def _staging_entry(baseline: dict) -> dict:
    return next(
        entry
        for entry in baseline["internal_schemas"]
        if entry["id"].startswith("m5a-staging-")
    )


def test_greenfield_allocates_stable_staging_schema_and_orders_migrations(tmp_path: Path) -> None:
    metadata = _metadata()
    profile = TARGET_PROFILES[metadata.target_profile]

    first = build_schema_baseline(metadata=metadata, target_profile=profile)
    second = build_schema_baseline(metadata=copy.deepcopy(metadata), target_profile=profile)
    assert first == second
    entry = _staging_entry(first)
    assert entry["id"] == "m5a-staging-001"
    assert entry["handoff_name"] == "widget-staging"
    assert entry["staging_table"] == "widget_staging"
    assert entry["run_id_column"] == "run_id"
    assert entry["dedup_key"] == ["widget_id", "payload_key"]
    assert entry["constraint_name"] == "uq_m5a_staging_001"
    assert len(entry["content_sha256"]) == 64

    migrations = emit_sql_files(
        metadata=metadata,
        target_profile=profile,
        output_dir=tmp_path,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-order",
    )
    assert [path.name for path in migrations] == [
        "V1__create_widget_table.sql",
        "V2__create_widget_staging_table.sql",
        "V3__create_pkg_batch_metadata.sql",
        "V4__add_m5a_staging_001_unique.sql",
    ]
    assert (
        "ALTER TABLE widget_staging\nADD CONSTRAINT uq_m5a_staging_001\n"
        "UNIQUE (run_id, widget_id, payload_key);"
        in migrations[-1].read_text(encoding="utf-8")
    )


def test_disable_retains_and_reenable_reuses_staging_identity() -> None:
    metadata = _metadata()
    profile = TARGET_PROFILES[metadata.target_profile]
    enabled = build_schema_baseline(metadata=metadata, target_profile=profile)
    disabled_metadata = copy.deepcopy(metadata)
    disabled_metadata.contracts[0].run_semantics = None

    disabled = build_schema_baseline(
        metadata=disabled_metadata,
        target_profile=profile,
        previous_baseline=enabled,
    )
    assert disabled["internal_schemas"] == enabled["internal_schemas"]
    reenabled = build_schema_baseline(
        metadata=metadata,
        target_profile=profile,
        previous_baseline=disabled,
    )
    assert reenabled["internal_schemas"] == enabled["internal_schemas"]


def test_multi_handoff_allocation_is_independent_of_contract_traversal(
    tmp_path: Path,
) -> None:
    first = _metadata()
    second_contract = copy.deepcopy(first.contracts[0])
    second_contract.name = "alpha-staging"
    second_contract.physical_name = "alpha_staging"
    first.contracts.append(second_contract)
    first.staging_table_ddls["alpha_staging"] = first.staging_table_ddls["widget_staging"].replace(
        "widget_staging", "alpha_staging"
    )
    permuted = copy.deepcopy(first)
    permuted.contracts.reverse()
    permuted.staging_table_ddls = dict(reversed(list(permuted.staging_table_ddls.items())))
    profile = TARGET_PROFILES[first.target_profile]

    baseline = build_schema_baseline(metadata=first, target_profile=profile)
    permuted_baseline = build_schema_baseline(metadata=permuted, target_profile=profile)
    assert baseline["internal_schemas"] == permuted_baseline["internal_schemas"]
    by_handoff = {
        entry["handoff_name"]: entry["id"]
        for entry in baseline["internal_schemas"]
        if entry["id"].startswith("m5a-staging-")
    }
    assert by_handoff == {
        "alpha-staging": "m5a-staging-001",
        "widget-staging": "m5a-staging-002",
    }

    first_output = tmp_path / "first"
    permuted_output = tmp_path / "permuted"
    for project, output in ((first, first_output), (permuted, permuted_output)):
        emit_sql_files(
            metadata=project,
            target_profile=profile,
            output_dir=output,
            source_manifest="app-definition.yaml",
            generation_run_id="m5a-s3-permutation",
        )
    assert _package_bytes(first_output) == _package_bytes(permuted_output)

    duplicate = copy.deepcopy(first)
    duplicate.contracts.append(copy.deepcopy(duplicate.contracts[0]))
    with pytest.raises(ValueError, match="Duplicate M5a staging.*allocation tuple"):
        build_schema_baseline(metadata=duplicate, target_profile=profile)


def test_greenfield_invalid_schema_claim_fails_before_output_creation(tmp_path: Path) -> None:
    metadata = _metadata()
    metadata.contracts[0].run_semantics.internal_schema_id = "m5a-staging-001"
    output_dir = tmp_path / "greenfield-refused"

    with pytest.raises(ValueError, match="absent from the committed baseline"):
        generate_application(metadata, output_dir, generation_run_id="m5a-s3-greenfield-refused")

    assert not output_dir.exists()


def test_opted_in_mapping_traversal_does_not_change_generated_java(tmp_path: Path) -> None:
    first = _metadata()
    permuted = copy.deepcopy(first)
    permuted.mappings.reverse()
    profile = TARGET_PROFILES[first.target_profile]

    for project, output in (
        (first, tmp_path / "first"),
        (permuted, tmp_path / "permuted"),
    ):
        emit_java_sources(
            metadata=project,
            target_profile=profile,
            output_dir=output,
            source_manifest="app-definition.yaml",
            generation_run_id="m5a-s3-mapping-permutation",
        )
    assert _package_bytes(tmp_path / "first") == _package_bytes(tmp_path / "permuted")


def test_missing_annotation_and_renames_fail_closed_without_package_mutation(
    tmp_path: Path,
) -> None:
    initial = _metadata()
    initial.target_profile = "springboot-enterprise-postgres-java17"
    initial.contracts[0].run_semantics = None
    package_dir = tmp_path / "package"
    generate_application(
        initial,
        package_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-initial",
    )
    enabled = _metadata()
    enabled.target_profile = initial.target_profile
    enable_plan = build_change_plan(metadata=enabled, package_dir=package_dir)
    apply_change_plan(
        metadata=enabled,
        package_dir=package_dir,
        approved_plan_hash=enable_plan["plan_hash"],
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-enable",
    )
    baseline = json.loads(
        (package_dir / "db/schema-baseline.json").read_text(encoding="utf-8")
    )
    schema_id = _staging_entry(baseline)["id"]

    renamed = copy.deepcopy(enabled)
    renamed.contracts[0].name = "renamed-widget-staging"
    renamed.contracts[0].run_semantics.internal_schema_id = schema_id
    before = _package_bytes(package_dir)
    plan = build_change_plan(metadata=renamed, package_dir=package_dir)
    assert plan["classification"] == "unsafe"
    with pytest.raises(ValueError, match="Unsafe/destructive"):
        apply_change_plan(
            metadata=renamed,
            package_dir=package_dir,
            approved_plan_hash=plan["plan_hash"],
        )
    assert _package_bytes(package_dir) == before

    unannotated_rename = copy.deepcopy(enabled)
    unannotated_rename.contracts[0].name = "renamed-widget-staging"
    for mapping in unannotated_rename.mappings:
        if mapping.contract_name == "widget-staging":
            mapping.contract_name = "renamed-widget-staging"
    plan = build_change_plan(metadata=unannotated_rename, package_dir=package_dir)
    assert plan["classification"] == "destructive"
    with pytest.raises(ValueError, match="Unsafe/destructive"):
        apply_change_plan(
            metadata=unannotated_rename,
            package_dir=package_dir,
            approved_plan_hash=plan["plan_hash"],
        )
    assert _package_bytes(package_dir) == before

    bad_annotation = copy.deepcopy(enabled)
    bad_annotation.contracts[0].run_semantics.internal_schema_id = "m5a-staging-999"
    with pytest.raises(ValueError, match="absent from the committed baseline"):
        build_change_plan(metadata=bad_annotation, package_dir=package_dir)


@pytest.mark.parametrize(
    ("profile_name", "required_sql", "forbidden_sql"),
    [
        (
            "springboot-enterprise-postgres-java17",
            "ON CONFLICT (run_id, widget_id) DO UPDATE SET",
            "DuplicateKeyException",
        ),
        (
            "springboot-legacy-compatible",
            "catch (DuplicateKeyException alreadyPresent)",
            "ON CONFLICT",
        ),
    ],
)
def test_profile_specific_upsert_preserves_identity_and_removes_clear(
    profile_name: str,
    required_sql: str,
    forbidden_sql: str,
    tmp_path: Path,
) -> None:
    metadata = _metadata()
    metadata.target_profile = profile_name
    metadata.contracts[0].run_semantics.dedup_key = ["widget_id"]
    emit_java_sources(
        metadata=metadata,
        target_profile=TARGET_PROFILES[profile_name],
        output_dir=tmp_path,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-writer",
    )
    root = tmp_path / "src/main/java/com/appbuilder/m5a_run_semantics"
    writer = (root / "adapter/outbound/WidgetStagingWriter.java").read_text(encoding="utf-8")
    job = (root / "batch/WidgetEodBatchJob.java").read_text(encoding="utf-8")
    assert required_sql in writer
    assert forbidden_sql not in writer
    assert "void clear(" not in writer
    assert "stagingWriter.clear" not in job
    assert "staging_row_id =" not in writer
    assert "created_at =" not in writer
    assert "run_id = EXCLUDED.run_id" not in writer
    assert "widget_id = EXCLUDED.widget_id" not in writer
    assert 'staging_status = \'READY\'' in writer
    if profile_name == "springboot-enterprise-postgres-java17":
        assert "payload_key = EXCLUDED.payload_key" in writer
    else:
        assert "UPDATE widget_staging SET payload_key = ?, staging_status = 'READY' WHERE" in writer
        assert "SELECT COUNT(*) FROM widget_staging WHERE" in writer
        assert "MERGE INTO" not in writer
        catch_index = writer.index("catch (DuplicateKeyException alreadyPresent)")
        update_index = writer.index("UPDATE widget_staging SET")
        catch_end_index = writer.index("        }", catch_index)
        assert catch_index < update_index < catch_end_index


def test_retained_staging_identity_rejects_profile_and_fingerprint_drift() -> None:
    metadata = _metadata()
    profile = TARGET_PROFILES[metadata.target_profile]
    baseline = build_schema_baseline(metadata=metadata, target_profile=profile)

    unknown_profile = copy.deepcopy(baseline)
    _staging_entry(unknown_profile)["target_profile"] = "unknown-profile"
    with pytest.raises(ValueError, match="unknown target profile"):
        build_schema_baseline(
            metadata=metadata,
            target_profile=profile,
            previous_baseline=unknown_profile,
        )

    drifted = copy.deepcopy(baseline)
    _staging_entry(drifted)["content_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint drifted"):
        build_schema_baseline(
            metadata=metadata,
            target_profile=profile,
            previous_baseline=drifted,
        )


def test_changed_dedup_contract_is_unsafe(tmp_path: Path) -> None:
    metadata = _metadata()
    package_dir = tmp_path / "package"
    generate_application(
        metadata,
        package_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-dedup-initial",
    )
    changed = copy.deepcopy(metadata)
    changed.contracts[0].run_semantics.dedup_key = ["widget_id"]

    plan = build_change_plan(metadata=changed, package_dir=package_dir)
    assert plan["classification"] == "unsafe"
    assert any(
        delta["kind"] == "internal_schema"
        and delta["change"] == "modified"
        and delta["classification"] == "unsafe"
        for delta in plan["deltas"]
    )


def test_public_generate_plan_apply_enable_run_semantics(tmp_path: Path) -> None:
    initial = _metadata()
    initial.target_profile = "springboot-enterprise-postgres-java17"
    initial.contracts[0].run_semantics = None
    package_dir = tmp_path / "managed"
    generate_application(
        initial,
        package_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-public-initial",
    )

    enabled = _metadata()
    enabled.target_profile = initial.target_profile
    plan = build_change_plan(metadata=enabled, package_dir=package_dir)
    assert plan["classification"] == "additive"
    report = apply_change_plan(
        metadata=enabled,
        package_dir=package_dir,
        approved_plan_hash=plan["plan_hash"],
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-public-apply",
    )
    assert [path.name for path in report.migrations_created] == [
        "V4__add_m5a_staging_001_unique.sql",
    ]
    assert report.generation_report.harness_report is not None
    assert report.generation_report.harness_report.passed


def test_apply_orders_new_staging_table_before_internal_schemas(tmp_path: Path) -> None:
    initial = _metadata()
    initial.target_profile = "springboot-enterprise-postgres-java17"
    initial.contracts = []
    initial.mappings = []
    initial.operations = []
    initial.staging_table_ddls = {}
    package_dir = tmp_path / "managed"
    generate_application(
        initial,
        package_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-table-initial",
    )

    enabled = _metadata()
    enabled.target_profile = initial.target_profile
    plan = build_change_plan(metadata=enabled, package_dir=package_dir)
    assert plan["classification"] == "additive"
    report = apply_change_plan(
        metadata=enabled,
        package_dir=package_dir,
        approved_plan_hash=plan["plan_hash"],
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-table-apply",
    )
    assert [path.name for path in report.migrations_created] == [
        "V2__create_widget_staging_table.sql",
        "V3__create_pkg_batch_metadata.sql",
        "V4__add_m5a_staging_001_unique.sql",
    ]


def test_greenfield_opt_in_generation_retains_s2_console_card(tmp_path: Path) -> None:
    package_dir = tmp_path / "greenfield"
    report = generate_application(
        _metadata(),
        package_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-greenfield",
    )
    assert report.harness_report is not None
    assert report.harness_report.passed
    console = (
        package_dir / "src/main/resources/static/index.html"
    ).read_text(encoding="utf-8")
    assert "Run widgetEodJob" in console
    assert "batch-widgetEodJob-run-id" in console


def test_direct_regeneration_cannot_get_ahead_of_apply_owned_schema(tmp_path: Path) -> None:
    initial = _metadata()
    initial.target_profile = "springboot-enterprise-postgres-java17"
    initial.contracts[0].run_semantics = None
    package_dir = tmp_path / "managed"
    generate_application(initial, package_dir, generation_run_id="m5a-s3-guard-initial")
    before = _package_bytes(package_dir)

    enabled = _metadata()
    enabled.target_profile = initial.target_profile
    with pytest.raises(ValueError, match="Use appbuilder plan and approved apply"):
        generate_application(enabled, package_dir, generation_run_id="m5a-s3-guard-refused")
    assert _package_bytes(package_dir) == before


@pytest.mark.parametrize("masked_as_non_executable", [False, True])
def test_untracked_equivalent_unique_constraint_is_detected_from_sql_content(
    masked_as_non_executable: bool,
    tmp_path: Path,
) -> None:
    initial = _metadata()
    initial.target_profile = "springboot-enterprise-postgres-java17"
    initial.contracts[0].run_semantics = None
    package_dir = tmp_path / "collision"
    generate_application(initial, package_dir, generation_run_id="m5a-s3-collision-initial")
    migration = package_dir / "src/main/resources/db/migration/V8__manual.sql"
    statement = (
        "ALTER TABLE widget_staging ADD CONSTRAINT manual_unique "
        "UNIQUE (run_id, widget_id, payload_key);"
    )
    migration.write_text(
        f"-- {statement}\nSELECT $message${statement}$message$;\n"
        if masked_as_non_executable
        else statement + "\n",
        encoding="utf-8",
    )
    enabled = _metadata()
    enabled.target_profile = initial.target_profile
    plan = build_change_plan(metadata=enabled, package_dir=package_dir)
    collision_deltas = [
        delta
        for delta in plan["deltas"]
        if "equivalent staging UNIQUE constraint" in delta["message"]
    ]
    assert bool(collision_deltas) is not masked_as_non_executable
    assert plan["classification"] == (
        "unsafe" if not masked_as_non_executable else "additive"
    )


@pytest.mark.parametrize("mutation", ["delete", "edit", "duplicate"])
def test_retained_staging_schema_requires_exactly_one_immutable_migration(
    mutation: str,
    tmp_path: Path,
) -> None:
    metadata = _metadata()
    package_dir = tmp_path / mutation
    generate_application(metadata, package_dir, generation_run_id=f"m5a-s3-{mutation}")
    migration_dir = package_dir / "src/main/resources/db/migration"
    migration = next(migration_dir.glob("V*__add_m5a_staging_001_unique.sql"))
    if mutation == "delete":
        migration.unlink()
    elif mutation == "edit":
        migration.write_text(
            migration.read_text(encoding="utf-8").replace("payload_key", "staging_status"),
            encoding="utf-8",
        )
    else:
        (migration_dir / "V99__manual_duplicate_unique.sql").write_text(
            migration.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    before = _package_bytes(package_dir)

    plan = build_change_plan(metadata=metadata, package_dir=package_dir)
    assert plan["classification"] == "unsafe"
    expected_issue = {
        "delete": "missing",
        "edit": "divergent",
        "duplicate": "duplicate",
    }[mutation]
    assert any(
        "Retained internal schema 'm5a-staging-001'" in delta["message"]
        and delta.get("details", {}).get("issue") == expected_issue
        for delta in plan["deltas"]
    )
    with pytest.raises(ValueError, match="Retained internal schema 'm5a-staging-001'"):
        generate_application(
            metadata,
            package_dir,
            generation_run_id=f"m5a-s3-{mutation}-refused",
        )
    with pytest.raises(ValueError, match="Unsafe/destructive"):
        apply_change_plan(
            metadata=metadata,
            package_dir=package_dir,
            approved_plan_hash=plan["plan_hash"],
        )
    assert _package_bytes(package_dir) == before


def test_retained_batch_schema_requires_immutable_migration(tmp_path: Path) -> None:
    metadata = _metadata()
    package_dir = tmp_path / "missing-batch"
    generate_application(metadata, package_dir, generation_run_id="m5a-s3-missing-batch")
    next(
        (package_dir / "src/main/resources/db/migration").glob(
            "V*__create_pkg_batch_metadata.sql"
        )
    ).unlink()

    plan = build_change_plan(metadata=metadata, package_dir=package_dir)

    assert plan["classification"] == "unsafe"
    assert any(
        "Retained internal schema 'pkg-batch-metadata'" in delta["message"]
        for delta in plan["deltas"]
    )


@pytest.mark.parametrize(
    ("sql", "expected_name", "expected_columns"),
    [
        (
            "ALTER TABLE widget_staging ADD CONSTRAINT manual_unique "
            "UNIQUE (run_id, widget_id, payload_key);",
            "manual_unique",
            ["run_id", "widget_id", "payload_key"],
        ),
        (
            "ALTER TABLE widget_staging ADD UNIQUE (payload_key, run_id, widget_id);",
            "",
            ["payload_key", "run_id", "widget_id"],
        ),
        (
            "CREATE UNIQUE INDEX manual_unique ON widget_staging "
            "(run_id DESC, widget_id ASC, payload_key);",
            "manual_unique",
            ["run_id", "widget_id", "payload_key"],
        ),
        (
            'CREATE UNIQUE INDEX "manual_unique" ON "public"."widget_staging" '
            '("run_id", "widget_id" DESC, "payload_key");',
            "manual_unique",
            ["run_id", "widget_id", "payload_key"],
        ),
        (
            "CREATE TABLE widget_staging (run_id VARCHAR(64), widget_id VARCHAR(36), "
            "payload_key VARCHAR(64), UNIQUE (run_id, widget_id, payload_key));",
            "",
            ["run_id", "widget_id", "payload_key"],
        ),
    ],
)
def test_unique_inventory_classifies_common_executable_forms(
    sql: str,
    expected_name: str,
    expected_columns: list[str],
) -> None:
    assert staging_unique_constraints_in_sql(sql) == [
        {
            "table": "widget_staging",
            "name": expected_name,
            "columns": expected_columns,
        }
    ]


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER TABLE widget_staging ADD UNIQUE (payload_key, run_id, widget_id);",
        (
            "CREATE UNIQUE INDEX manual_unique ON widget_staging "
            "(widget_id DESC, payload_key, run_id ASC);"
        ),
        (
            'CREATE UNIQUE INDEX manual_unique ON "widget_staging" '
            '("run_id", "widget_id", "payload_key");'
        ),
        (
            "CREATE UNIQUE INDEX manual_unique ON public.widget_staging "
            "(payload_key, run_id, widget_id DESC);"
        ),
        (
            "ALTER TABLE ONLY widget_staging ADD CONSTRAINT manual_unique "
            "UNIQUE (run_id, widget_id, payload_key);"
        ),
        (
            "CREATE UNIQUE INDEX manual_unique ON widget_staging USING btree "
            "(run_id, widget_id, payload_key);"
        ),
        (
            "CREATE UNIQUE INDEX CONCURRENTLY manual_unique ON widget_staging "
            "(run_id, widget_id, payload_key);"
        ),
        (
            "ALTER TABLE widget_staging ADD CONSTRAINT manual_unique "
            "UNIQUE NULLS NOT DISTINCT (run_id, widget_id, payload_key);"
        ),
        (
            "ALTER TABLE IF EXISTS widget_staging ADD CONSTRAINT manual_unique "
            "UNIQUE (run_id, widget_id, payload_key);"
        ),
        (
            "ALTER TABLE widget_staging ADD CONSTRAINT manual_unique "
            "UNIQUE USING INDEX existing_unique;"
        ),
        (
            "CREATE TABLE widget_staging (run_id VARCHAR(64), widget_id VARCHAR(36), "
            "payload_key VARCHAR(64) UNIQUE);"
        ),
        (
            "CREATE UNIQUE INDEX manual_unique ON widget_staging "
            "(run_id text_pattern_ops, widget_id, payload_key);"
        ),
    ],
)
def test_semantically_equivalent_unique_forms_block_additive_apply(
    statement: str,
    tmp_path: Path,
) -> None:
    initial = _metadata()
    initial.target_profile = "springboot-enterprise-postgres-java17"
    initial.contracts[0].run_semantics = None
    package_dir = tmp_path / "semantic-collision"
    generate_application(initial, package_dir, generation_run_id="m5a-s3-semantic-initial")
    migration = package_dir / "src/main/resources/db/migration/V8__manual.sql"
    migration.write_text(statement + "\n", encoding="utf-8")

    enabled = _metadata()
    enabled.target_profile = initial.target_profile
    plan = build_change_plan(metadata=enabled, package_dir=package_dir)

    assert plan["classification"] == "unsafe"
    assert any(
        "equivalent staging UNIQUE constraint" in delta["message"]
        for delta in plan["deltas"]
    )


def test_unclassifiable_unique_on_other_table_does_not_block_plan(tmp_path: Path) -> None:
    initial = _metadata()
    initial.target_profile = "springboot-enterprise-postgres-java17"
    initial.contracts[0].run_semantics = None
    package_dir = tmp_path / "other-table"
    generate_application(initial, package_dir, generation_run_id="m5a-s3-other-table")
    migration = package_dir / "src/main/resources/db/migration/V8__manual.sql"
    migration.write_text(
        "CREATE UNIQUE INDEX other_unique ON other_table USING btree (run_id, widget_id);\n",
        encoding="utf-8",
    )
    enabled = _metadata()
    enabled.target_profile = initial.target_profile

    plan = build_change_plan(metadata=enabled, package_dir=package_dir)

    assert plan["classification"] == "additive"
    assert not any(
        delta.get("details", {}).get("unclassifiable_unique")
        for delta in plan["deltas"]
    )


@pytest.mark.parametrize(
    "migration_sql",
    [
        (
            "SELECT E'it\\'s CREATE UNIQUE INDEX manual_unique ON widget_staging "
            "USING btree (run_id, widget_id, payload_key);';\n"
        ),
        (
            "/* outer /* inner */ CREATE UNIQUE INDEX manual_unique ON widget_staging "
            "USING btree (run_id, widget_id, payload_key); */ SELECT 1;\n"
        ),
    ],
)
def test_non_executable_unique_forms_do_not_block_plan(
    migration_sql: str,
    tmp_path: Path,
) -> None:
    initial = _metadata()
    initial.target_profile = "springboot-enterprise-postgres-java17"
    initial.contracts[0].run_semantics = None
    package_dir = tmp_path / "non-executable-unique"
    generate_application(initial, package_dir, generation_run_id="m5a-s3-non-executable")
    migration = package_dir / "src/main/resources/db/migration/V8__message.sql"
    migration.write_text(migration_sql, encoding="utf-8")
    enabled = _metadata()
    enabled.target_profile = initial.target_profile

    plan = build_change_plan(metadata=enabled, package_dir=package_dir)

    assert plan["classification"] == "additive"
    assert not any(
        delta.get("details", {}).get("unclassifiable_unique")
        for delta in plan["deltas"]
    )


def test_edited_retained_unique_reports_unclassifiable_not_duplicate(tmp_path: Path) -> None:
    metadata = _metadata()
    metadata.target_profile = "springboot-enterprise-postgres-java17"
    package_dir = tmp_path / "retained-unclassifiable"
    generate_application(metadata, package_dir, generation_run_id="m5a-s3-unclassifiable")
    migration = next(
        (package_dir / "src/main/resources/db/migration").glob(
            "V*__add_m5a_staging_001_unique.sql"
        )
    )
    migration.write_text(
        "ALTER TABLE ONLY widget_staging ADD CONSTRAINT uq_m5a_staging_001 "
        "UNIQUE (run_id, widget_id, payload_key);\n",
        encoding="utf-8",
    )

    plan = build_change_plan(metadata=metadata, package_dir=package_dir)

    issues = [
        delta.get("details", {}).get("issue")
        for delta in plan["deltas"]
        if delta.get("details", {}).get("schema_id") == "m5a-staging-001"
    ]
    assert issues == ["unclassifiable"]


def test_h2_quoted_uppercase_unique_is_equivalent_for_retained_inventory(
    tmp_path: Path,
) -> None:
    metadata = _metadata()
    assert metadata.target_profile == "springboot-legacy-compatible"
    package_dir = tmp_path / "h2-uppercase-collision"
    generate_application(metadata, package_dir, generation_run_id="m5a-s3-h2-uppercase")
    migration = package_dir / "src/main/resources/db/migration/V99__manual_uppercase_unique.sql"
    migration.write_text(
        'CREATE UNIQUE INDEX "MANUAL_UNIQUE" ON "PUBLIC"."WIDGET_STAGING" '
        '("RUN_ID", "WIDGET_ID", "PAYLOAD_KEY");\n',
        encoding="utf-8",
    )

    plan = build_change_plan(metadata=metadata, package_dir=package_dir)

    assert plan["classification"] == "unsafe"
    assert any(
        delta.get("details", {}).get("schema_id") == "m5a-staging-001"
        and delta.get("details", {}).get("issue") == "duplicate"
        for delta in plan["deltas"]
    )


def test_legacy_writer_remains_clear_and_insert(tmp_path: Path) -> None:
    metadata = _metadata()
    metadata.contracts[0].run_semantics = None
    emit_java_sources(
        metadata=metadata,
        target_profile=TARGET_PROFILES[metadata.target_profile],
        output_dir=tmp_path,
        source_manifest="app-definition.yaml",
        generation_run_id="m5a-s3-legacy",
    )
    root = tmp_path / "src/main/java/com/appbuilder/m5a_run_semantics"
    writer = (root / "adapter/outbound/WidgetStagingWriter.java").read_text(encoding="utf-8")
    job = (root / "batch/WidgetEodBatchJob.java").read_text(encoding="utf-8")
    assert "void clear(String runId)" in writer
    assert "INSERT INTO widget_staging" in writer
    assert "MERGE INTO" not in writer
    assert "ON CONFLICT" not in writer
    assert "stagingWriter.clear" in job
