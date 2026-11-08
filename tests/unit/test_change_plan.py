import copy
import io
import json
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from appbuilder.cli import main
from appbuilder.generation import engine as generation_engine
from appbuilder.generation import generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.change_plan import (
    build_change_plan,
    render_change_plan_json,
    validate_change_plan,
)
from appbuilder.generation.engine import GenerationReport
from appbuilder.harness.models import HarnessCheck, HarnessCheckSeverity, HarnessReport
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata import MetadataProject, build_metadata_project
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    CanonicalRelationship,
    HttpMethod,
    RelationshipType,
    ResponseShape,
)


def test_change_plan_classifies_schema_deltas_and_edge_contract_impacts(
    tmp_path: Path,
) -> None:
    original = _load_xyz_metadata()
    package_dir = tmp_path / "BuiltAppChangePlan"
    generate_application(original, package_dir, generation_run_id="baseline")

    evolved = original.model_copy(deep=True)
    account = evolved.entities[0]
    account.fields = [
        field
        for field in account.fields
        if field.name not in {"accountType", "createdDate"}
    ]
    status = next(field for field in account.fields if field.name == "status")
    status.max_length = 5
    account.fields.extend(
        [
            CanonicalField(
                name="nickname",
                type=CanonicalFieldType.STRING,
                required=False,
                max_length=50,
            ),
            CanonicalField(
                name="riskScore",
                type=CanonicalFieldType.INTEGER,
                required=True,
            ),
            CanonicalField(
                name="openedDate",
                type=CanonicalFieldType.DATE,
                required=False,
            ),
        ]
    )
    evolved.mappings.append(
        FieldMapping(
            contract_name="crm-account-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createAccount",
            source_path="crm-account-api.createAccount.request.riskScore",
            target_path="Account.riskScore",
            source_required=True,
            source_location="tests/change-plan/synthetic-mapping.yaml",
        )
    )

    plan = build_change_plan(metadata=evolved, package_dir=package_dir)
    validate_change_plan(plan)

    assert plan["classification"] == "destructive"
    deltas = {
        (delta["kind"], delta["entity"], delta["field"], delta["change"]): delta
        for delta in plan["deltas"]
    }
    assert deltas[("field", "Account", "nickname", "added")]["classification"] == "additive"
    assert deltas[("field", "Account", "riskScore", "added")]["classification"] == "unsafe"
    assert deltas[("field", "Account", "accountType", "removed")][
        "classification"
    ] == "destructive"
    assert deltas[("field", "Account", "status", "modified")][
        "classification"
    ] == "destructive"
    assert deltas[("field", "Account", "createdDate", "removed")][
        "classification"
    ] == "destructive"
    assert deltas[("field", "Account", "openedDate", "added")]["classification"] == "additive"
    assert all(delta["db_migration_delta"] for delta in plan["db_migration_deltas"])
    assert any(
        impact["contract_name"] == "crm-account-api"
        and impact["entity"] == "Account"
        and impact["field"] == "accountType"
        for impact in plan["edge_contract_impact"]
    )
    assert any("manual backfill" in action for action in plan["required_manual_actions"])


def test_existing_column_changes_fail_closed_even_when_widening_or_nullable_relaxed(
    tmp_path: Path,
) -> None:
    original = _load_xyz_metadata()
    package_dir = tmp_path / "BuiltAppExistingColumnChangePlan"
    generate_application(original, package_dir, generation_run_id="baseline")

    evolved = original.model_copy(deep=True)
    account = evolved.entities[0]
    account_type = next(field for field in account.fields if field.name == "accountType")
    account_type.required = False
    status = next(field for field in account.fields if field.name == "status")
    status.max_length = 20
    created_date = next(field for field in account.fields if field.name == "createdDate")
    created_date.required = True
    evolved.mappings.append(
        FieldMapping(
            contract_name="crm-account-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createAccount",
            source_path="crm-account-api.createAccount.request.createdDate",
            target_path="Account.createdDate",
            source_required=True,
            source_location="tests/change-plan/synthetic-mapping.yaml",
        )
    )

    plan = build_change_plan(metadata=evolved, package_dir=package_dir)

    assert plan["classification"] == "unsafe"
    deltas = {
        (delta["kind"], delta["entity"], delta["field"], delta["change"]): delta
        for delta in plan["deltas"]
    }
    account_type_delta = deltas[("field", "Account", "accountType", "modified")]
    assert account_type_delta["classification"] == "unsafe"
    assert "nullability relaxed" in account_type_delta["message"]
    status_delta = deltas[("field", "Account", "status", "modified")]
    assert status_delta["classification"] == "unsafe"
    assert "SQL type widened" in status_delta["message"]
    created_date_delta = deltas[("field", "Account", "createdDate", "modified")]
    assert created_date_delta["classification"] == "unsafe"
    assert "nullability tightened" in created_date_delta["message"]
    assert "manual backfill" in created_date_delta["message"]


def test_relationship_added_with_existing_fk_column_plans_and_applies_constraint(
    tmp_path: Path,
) -> None:
    original = _relationship_metadata(with_relationship=False)
    package_dir = tmp_path / "BuiltAppRelationshipApply"
    generate_application(original, package_dir, generation_run_id="baseline")

    evolved = _relationship_metadata(with_relationship=True)
    plan = build_change_plan(metadata=evolved, package_dir=package_dir)

    assert plan["classification"] == "additive"
    foreign_key_delta = next(
        delta for delta in plan["deltas"] if delta["kind"] == "foreign_key"
    )
    assert foreign_key_delta["change"] == "added"
    assert foreign_key_delta["classification"] == "additive"
    assert foreign_key_delta["entity"] == "Account"
    assert foreign_key_delta["field"] == "customerId"
    assert foreign_key_delta["db_migration_delta"] is True

    report = apply_change_plan(
        metadata=evolved,
        package_dir=package_dir,
        approved_plan_hash=plan["plan_hash"],
        source_manifest="tests/apply/relationship.yaml",
        generation_run_id="apply-relationship-test",
    )

    migration_path = (
        package_dir
        / "src/main/resources/db/migration/V3__alter_account_add_fk_account_customer_id.sql"
    )
    assert report.migrations_created == [migration_path]
    assert (
        "ALTER TABLE account ADD CONSTRAINT fk_account_customer_id "
        "FOREIGN KEY (customer_id) REFERENCES customer(customer_id);"
    ) in migration_path.read_text(encoding="utf-8")
    baseline = json.loads((package_dir / "db/schema-baseline.json").read_text(encoding="utf-8"))
    account = next(entity for entity in baseline["entities"] if entity["entity"] == "Account")
    assert account["foreign_keys"] == [
        {
            "column": "customer_id",
            "name": "fk_account_customer_id",
            "target_column": "customer_id",
            "target_table": "customer",
        }
    ]
    assert baseline["flyway_high_water_mark"] == 3


def test_relationship_removed_or_changed_fails_closed_in_change_plan(tmp_path: Path) -> None:
    original = _relationship_metadata(with_relationship=True)
    package_dir = tmp_path / "BuiltAppRelationshipDestructive"
    generate_application(original, package_dir, generation_run_id="baseline")

    removed = _relationship_metadata(with_relationship=False)
    removed_plan = build_change_plan(metadata=removed, package_dir=package_dir)
    removed_delta = next(
        delta for delta in removed_plan["deltas"] if delta["kind"] == "foreign_key"
    )
    assert removed_delta["change"] == "removed"
    assert removed_delta["classification"] == "destructive"

    changed = _relationship_metadata(with_relationship=True)
    changed.relationships[0].target_field = "customerName"
    changed_plan = build_change_plan(metadata=changed, package_dir=package_dir)
    changed_delta = next(
        delta for delta in changed_plan["deltas"] if delta["kind"] == "foreign_key"
    )
    assert changed_delta["change"] == "modified"
    assert changed_delta["classification"] == "destructive"


def test_change_plan_hashes_are_deterministic_and_bind_package_state(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    package_dir = tmp_path / "BuiltAppHash"
    generate_application(metadata, package_dir, generation_run_id="baseline")

    first_plan = build_change_plan(metadata=metadata, package_dir=package_dir)
    second_plan = build_change_plan(metadata=metadata, package_dir=package_dir)
    assert first_plan["package_state_hash"] == second_plan["package_state_hash"]
    assert first_plan["plan_hash"] == second_plan["plan_hash"]

    generated_edit_dir = _copy_package(package_dir, tmp_path / "GeneratedEdit")
    account_source = (
        generated_edit_dir
        / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    )
    account_source.write_text(
        account_source.read_text(encoding="utf-8") + "\n// local generated edit\n",
        encoding="utf-8",
    )
    generated_edit_plan = build_change_plan(
        metadata=metadata,
        package_dir=generated_edit_dir,
    )
    assert generated_edit_plan["package_state_hash"] != first_plan["package_state_hash"]
    assert generated_edit_plan["plan_hash"] != first_plan["plan_hash"]

    developer_file_dir = _copy_package(package_dir, tmp_path / "DeveloperFile")
    developer_file = (
        developer_file_dir
        / "src/main/java/com/appbuilder/accounts/service/AccountExtension.java"
    )
    developer_file.write_text(
        "\n".join(
            [
                "// Generated by EdgeForge",
                "// EdgeForge-ownership: developer",
                "package com.appbuilder.accounts.service;",
                "class AccountExtension {}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    developer_plan = build_change_plan(metadata=metadata, package_dir=developer_file_dir)
    assert developer_plan["package_state_hash"] != first_plan["package_state_hash"]
    assert developer_plan["plan_hash"] != first_plan["plan_hash"]

    migration_dir = _copy_package(package_dir, tmp_path / "MigrationFile")
    migration_file = (
        migration_dir
        / "src/main/resources/db/migration/V99__manual_change.sql"
    )
    migration_file.write_text("-- manual migration\n", encoding="utf-8")
    migration_plan = build_change_plan(metadata=metadata, package_dir=migration_dir)
    assert migration_plan["package_state_hash"] != first_plan["package_state_hash"]
    assert migration_plan["plan_hash"] != first_plan["plan_hash"]


def test_change_plan_schema_allows_v1_minor_additive_fields_and_rejects_v2(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    package_dir = tmp_path / "BuiltAppSchemaCompatibility"
    generate_application(metadata, package_dir, generation_run_id="baseline")

    plan = build_change_plan(metadata=metadata, package_dir=package_dir)
    compatible_minor = copy.deepcopy(plan)
    compatible_minor["change_plan_schema_version"] = "1.1"
    compatible_minor["future_minor_field"] = {"accepted": True}
    compatible_minor["deltas"] = [
        {**delta, "future_delta_field": "accepted"}
        for delta in compatible_minor["deltas"]
    ]

    validate_change_plan(compatible_minor)

    incompatible_major = copy.deepcopy(plan)
    incompatible_major["change_plan_schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        validate_change_plan(incompatible_major)


def test_manifest_only_change_plan_has_no_authoritative_db_migration_deltas(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    package_dir = tmp_path / "EmptyPackage"
    package_dir.mkdir()
    before = _package_snapshot(package_dir)

    plan = build_change_plan(metadata=metadata, package_dir=package_dir)

    assert plan["mode"] == "manifest-only"
    assert plan["baseline_hash"] is None
    assert plan["db_migration_deltas"] == []
    assert plan["deltas"]
    assert all(delta["db_migration_delta"] is False for delta in plan["deltas"])
    assert any("manifest-only" in warning for warning in plan["warnings"])
    assert _package_snapshot(package_dir) == before


def test_change_plan_cli_outputs_schema_valid_json_and_writes_no_package_files(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "BuiltAppCliPlan"
    generate_application(_load_xyz_metadata(), package_dir, generation_run_id="baseline")
    before = _package_snapshot(package_dir)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(
            [
                "plan",
                "--manifest",
                "examples/input-projects/xyz-accounts-modernization/app-definition.yaml",
                "--package",
                str(package_dir),
            ]
        )

    assert exit_code == 0
    plan = json.loads(stdout.getvalue())
    validate_change_plan(plan)
    assert render_change_plan_json(plan) == stdout.getvalue()
    assert plan["mode"] == "regenerate"
    assert plan["classification"] == "none"
    assert plan["deltas"] == []
    assert _package_snapshot(package_dir) == before


def test_change_plan_cli_refuses_to_write_out_file_inside_package(tmp_path: Path) -> None:
    package_dir = tmp_path / "BuiltAppCliPlanOut"
    generate_application(_load_xyz_metadata(), package_dir, generation_run_id="baseline")

    exit_code = main(
        [
            "plan",
            "--manifest",
            "examples/input-projects/xyz-accounts-modernization/app-definition.yaml",
            "--package",
            str(package_dir),
            "--out",
            str(package_dir / "change-plan.json"),
        ]
    )

    assert exit_code == 1
    assert not (package_dir / "change-plan.json").exists()


def test_apply_additive_plan_emits_migration_preserves_developer_service_and_updates_baseline(
    tmp_path: Path,
) -> None:
    original = _load_xyz_metadata()
    package_dir = tmp_path / "BuiltAppApplyAdditive"
    generate_application(original, package_dir, generation_run_id="baseline")
    migration_dir = package_dir / "src/main/resources/db/migration"
    baseline_path = package_dir / "db/schema-baseline.json"
    pre_cut_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    pre_cut_baseline.pop("manifest_schema_version")
    baseline_path.write_text(
        json.dumps(pre_cut_baseline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for migration_path in migration_dir.glob("V*.sql"):
        migration_path.write_text(
            "\n".join(
                line
                for line in migration_path.read_text(encoding="utf-8").splitlines()
                if "Manifest schema version:" not in line
            )
            + "\n",
            encoding="utf-8",
        )
    prior_migrations = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(migration_dir.glob("V*.sql"))
    }
    service_path = (
        package_dir / "src/main/java/com/appbuilder/accounts/service/AccountService.java"
    )
    service_marker = "// developer business rule survives apply"
    service_path.write_text(
        service_path.read_text(encoding="utf-8") + f"\n{service_marker}\n",
        encoding="utf-8",
    )

    evolved = original.model_copy(deep=True)
    evolved.entities[0].fields.append(
        CanonicalField(
            name="nickname",
            type=CanonicalFieldType.STRING,
            required=False,
            max_length=40,
        )
    )
    plan = build_change_plan(metadata=evolved, package_dir=package_dir)

    report = apply_change_plan(
        metadata=evolved,
        package_dir=package_dir,
        approved_plan_hash=plan["plan_hash"],
        source_manifest="tests/apply/additive.yaml",
        generation_run_id="apply-test",
    )

    assert report.plan_hash == plan["plan_hash"]
    migration_path = migration_dir / "V4__alter_account_add_nickname.sql"
    assert report.migrations_created == [migration_path]
    migration = migration_path.read_text(encoding="utf-8")
    assert "Manifest schema version: 2.0" in migration
    assert "ALTER TABLE account ADD COLUMN nickname VARCHAR(40);" in migration
    for name, content in prior_migrations.items():
        assert (migration_dir / name).read_text(encoding="utf-8") == content
    assert service_marker in service_path.read_text(encoding="utf-8")
    baseline = json.loads((package_dir / "db/schema-baseline.json").read_text(encoding="utf-8"))
    assert baseline["flyway_high_water_mark"] == 4
    assert baseline["manifest_schema_version"] == "2.0"
    account = next(entity for entity in baseline["entities"] if entity["entity"] == "Account")
    assert any(column["field"] == "nickname" for column in account["columns"])


@pytest.mark.parametrize(
    "profile",
    [
        "springboot-legacy-compatible",
        "springboot-enterprise-postgres-java17",
        "springboot-standard-enterprise",
    ],
)
@pytest.mark.parametrize(
    "field,definition",
    [
        (
            CanonicalField(
                name="priority",
                type=CanonicalFieldType.INTEGER,
                required=True,
                default_value="3",
                range_min=1,
                range_max=5,
            ),
            "priority BIGINT DEFAULT 3 NOT NULL CHECK (priority >= 1 AND priority <= 5)",
        ),
        (
            CanonicalField(
                name="label",
                type=CanonicalFieldType.STRING,
                required=False,
                default_value="n'a",
                min_length=2,
                max_length=20,
            ),
            "label VARCHAR(20) DEFAULT 'n''a' CHECK (LENGTH(label) >= 2)",
        ),
    ],
    ids=["required-range-default", "escaped-string-minimum-default"],
)
def test_apply_additive_defaults_precede_column_constraints(
    tmp_path: Path,
    profile: str,
    field: CanonicalField,
    definition: str,
) -> None:
    original = _load_xyz_metadata()
    original.target_profile = profile
    package = tmp_path / "AdditiveDefaults"
    generate_application(original, package, generation_run_id="additive-defaults-base")
    migrations = package / "src/main/resources/db/migration"
    previous = {
        path.name: (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
        for path in migrations.glob("V*.sql")
    }
    service = package / "src/main/java/com/appbuilder/accounts/service/AccountService.java"
    service.write_text(service.read_text() + "\n// retained developer-owned control\n")
    service.chmod(0o640)
    developer = (service.read_bytes(), service.stat().st_mode, service.stat().st_mtime_ns)
    evolved = original.model_copy(deep=True)
    evolved.entities[0].fields.append(field.model_copy(deep=True))
    plan = build_change_plan(metadata=evolved, package_dir=package)
    assert plan["classification"] == "additive"
    report = apply_change_plan(
        metadata=evolved,
        package_dir=package,
        approved_plan_hash=plan["plan_hash"],
        source_manifest="synthetic-additive-defaults",
        generation_run_id="additive-defaults",
    )
    path = migrations / f"V4__alter_account_add_{field.name}.sql"
    assert report.migrations_created == [path]
    assert f"ALTER TABLE account ADD COLUMN {definition};" in path.read_text()
    assert report.plan_hash == plan["plan_hash"]
    baseline = json.loads(report.baseline_path.read_text())
    assert baseline["flyway_high_water_mark"] == 4
    for name, snapshot in previous.items():
        prior = migrations / name
        assert (prior.read_bytes(), prior.stat().st_mode, prior.stat().st_mtime_ns) == snapshot
    assert (service.read_bytes(), service.stat().st_mode, service.stat().st_mtime_ns) == developer


def test_apply_refuses_plan_hash_drift_without_mutating_package(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    package_dir = tmp_path / "BuiltAppApplyHashDrift"
    generate_application(metadata, package_dir, generation_run_id="baseline")
    evolved = metadata.model_copy(deep=True)
    evolved.entities[0].fields.append(
        CanonicalField(name="nickname", type=CanonicalFieldType.STRING, required=False)
    )
    plan = build_change_plan(metadata=evolved, package_dir=package_dir)
    before = _package_snapshot(package_dir)

    developer_service = (
        package_dir / "src/main/java/com/appbuilder/accounts/service/AccountService.java"
    )
    developer_service.write_text(
        developer_service.read_text(encoding="utf-8") + "\n// drift after approval\n",
        encoding="utf-8",
    )
    drifted = _package_snapshot(package_dir)

    with pytest.raises(ValueError, match="Approved Change Plan hash does not match"):
        apply_change_plan(
            metadata=evolved,
            package_dir=package_dir,
            approved_plan_hash=plan["plan_hash"],
            generation_run_id="apply-test",
        )

    assert _package_snapshot(package_dir) == drifted
    assert before != drifted
    assert not (package_dir / "src/main/resources/db/migration/V4__alter_account_add_nickname.sql").exists()


def test_apply_refuses_unsafe_or_destructive_plans_without_mutating_package(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    package_dir = tmp_path / "BuiltAppApplyUnsafe"
    generate_application(metadata, package_dir, generation_run_id="baseline")
    evolved = metadata.model_copy(deep=True)
    evolved.entities[0].fields = [
        field for field in evolved.entities[0].fields if field.name != "accountType"
    ]
    evolved.entities[0].fields.append(
        CanonicalField(name="riskScore", type=CanonicalFieldType.INTEGER, required=True)
    )
    plan = build_change_plan(metadata=evolved, package_dir=package_dir)
    before = _package_snapshot(package_dir)

    with pytest.raises(ValueError, match="additive-only"):
        apply_change_plan(
            metadata=evolved,
            package_dir=package_dir,
            approved_plan_hash=plan["plan_hash"],
            generation_run_id="apply-test",
        )

    assert _package_snapshot(package_dir) == before


def test_apply_rolls_back_migration_when_generation_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _load_xyz_metadata()
    package_dir = tmp_path / "BuiltAppApplyGenerationFailure"
    generate_application(metadata, package_dir, generation_run_id="baseline")
    evolved = metadata.model_copy(deep=True)
    evolved.entities[0].fields.append(
        CanonicalField(name="nickname", type=CanonicalFieldType.STRING, required=False)
    )
    plan = build_change_plan(metadata=evolved, package_dir=package_dir)
    before = _package_snapshot(package_dir)

    def _raise_after_migration(*args, **kwargs):
        raise RuntimeError("simulated generation failure")

    monkeypatch.setattr(
        "appbuilder.generation.apply.generate_application",
        _raise_after_migration,
    )

    with pytest.raises(RuntimeError, match="simulated generation failure"):
        apply_change_plan(
            metadata=evolved,
            package_dir=package_dir,
            approved_plan_hash=plan["plan_hash"],
            generation_run_id="apply-test",
        )

    assert _package_snapshot(package_dir) == before


def test_apply_rolls_back_generation_when_harness_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _load_xyz_metadata()
    package_dir = tmp_path / "BuiltAppApplyHarnessFailure"
    generate_application(metadata, package_dir, generation_run_id="baseline")
    evolved = metadata.model_copy(deep=True)
    evolved.entities[0].fields.append(
        CanonicalField(name="nickname", type=CanonicalFieldType.STRING, required=False)
    )
    plan = build_change_plan(metadata=evolved, package_dir=package_dir)
    before = _package_snapshot(package_dir)

    def _fail_harness(*args, **kwargs) -> GenerationReport:
        report = generation_engine.generate_application(*args, **kwargs)
        output_dir = Path(args[1]) if len(args) > 1 else Path(kwargs["output_dir"])
        report.harness_report = HarnessReport(
            output_dir=output_dir,
            checks=[
                HarnessCheck(
                    name="simulated-harness",
                    severity=HarnessCheckSeverity.ERROR,
                    passed=False,
                    message="simulated harness failure",
                )
            ],
        )
        return report

    monkeypatch.setattr(
        "appbuilder.generation.apply.generate_application",
        _fail_harness,
    )

    with pytest.raises(ValueError, match="simulated harness failure"):
        apply_change_plan(
            metadata=evolved,
            package_dir=package_dir,
            approved_plan_hash=plan["plan_hash"],
            generation_run_id="apply-test",
        )

    assert _package_snapshot(package_dir) == before


def test_apply_cli_applies_additive_fixture(tmp_path: Path) -> None:
    initial_manifest = Path("scripts/smoke/fixtures/engine-l1-l3/initial/app-definition.yaml")
    additive_manifest = Path("scripts/smoke/fixtures/engine-l1-l3/additive/app-definition.yaml")
    package_dir = tmp_path / "BuiltAppApplyCli"
    generate_application(
        build_metadata_project(initial_manifest),
        package_dir,
        source_manifest=str(initial_manifest),
        generation_run_id="baseline",
    )
    plan = build_change_plan(
        metadata=build_metadata_project(additive_manifest),
        package_dir=package_dir,
    )

    exit_code = main(
        [
            "apply",
            "--manifest",
            str(additive_manifest),
            "--package",
            str(package_dir),
            "--approved-plan-hash",
            plan["plan_hash"],
            "--generation-run-id",
            "apply-cli-test",
            "--validate-schema",
        ]
    )

    assert exit_code == 0
    assert (
        package_dir
        / "src/main/resources/db/migration/V2__alter_widget_add_category.sql"
    ).exists()
    baseline = json.loads((package_dir / "db/schema-baseline.json").read_text(encoding="utf-8"))
    assert baseline["flyway_high_water_mark"] == 2


def _load_xyz_metadata() -> MetadataProject:
    payload = json.loads(
        Path("tests/golden_contracts/xyz_accounts_metadata.json").read_text(encoding="utf-8")
    )
    return MetadataProject.model_validate(copy.deepcopy(payload))


def _relationship_metadata(*, with_relationship: bool) -> MetadataProject:
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(
                name="customerId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=36,
            ),
            CanonicalField(
                name="customerName",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=50,
            ),
        ],
    )
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=36,
            ),
            CanonicalField(
                name="customerId",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=36,
            ),
        ],
    )
    relationships = (
        [
            CanonicalRelationship(
                source_entity="Account",
                source_field="customerId",
                target_entity="Customer",
                target_field="customerId",
                relationship_type=RelationshipType.MANY_TO_ONE,
                association_name="customer",
            )
        ]
        if with_relationship
        else []
    )
    return MetadataProject(
        app_name="Relationship Apply Test",
        bounded_context="relationshipapply",
        target_profile="springboot-enterprise-postgres-java17",
        entities=[customer, account],
        operations=[
            CanonicalOperation(
                name="createCustomer",
                interface_name="relationship-api",
                request_entity="Customer",
                response_entity="Customer",
                http_method=HttpMethod.POST,
                path="/customers",
                has_request_body=True,
                response_shape=ResponseShape.CREATED,
            ),
            CanonicalOperation(
                name="createAccount",
                interface_name="relationship-api",
                request_entity="Account",
                response_entity="Account",
                http_method=HttpMethod.POST,
                path="/accounts",
                has_request_body=True,
                response_shape=ResponseShape.CREATED,
            ),
        ],
        mappings=[
            FieldMapping(
                contract_name="relationship-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createCustomer",
                source_path="relationship-api.createCustomer.response.customerId",
                target_path="Customer.customerId",
            ),
            FieldMapping(
                contract_name="relationship-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createAccount",
                source_path="relationship-api.createAccount.response.accountId",
                target_path="Account.accountId",
            ),
            FieldMapping(
                contract_name="relationship-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createAccount",
                source_path="relationship-api.createAccount.request.customerId",
                target_path="Account.customerId",
            ),
        ],
        relationships=relationships,
    )


def _copy_package(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _package_snapshot(package_dir: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(package_dir.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(package_dir).as_posix()] = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
    return snapshot
