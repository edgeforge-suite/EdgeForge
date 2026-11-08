import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from appbuilder.contracts import load_project_definition
from appbuilder.core import AppArchetype
from appbuilder.generation import generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.build_emitter import _render_pom_xml
from appbuilder.generation.change_plan import build_change_plan
from appbuilder.generation.java_emitter import (
    _fallback_request_field_mappings,
    _fallback_response_field_mappings,
    _isolated_tmp_base_dir_default,
    _operation_contexts_for_entity,
    _render_batch_job,
    _render_controller,
    _render_dto,
    _render_entity,
    _render_service,
    _render_staging_writer,
    _validate_xml_mappings_supported,
    _xml_ingest_assignment_expression,
    emit_java_sources,
)
from appbuilder.generation.sql_emitter import emit_sql_files
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    CanonicalRelationship,
    ContractMetadata,
    HttpMethod,
    IdGenerationStrategy,
    MetadataProject,
    PathParameter,
    RelationshipType,
    ResponseShape,
    SystemParticipant,
    build_metadata_project,
    translate_project,
)
from appbuilder.metadata.models import OperationParameter, OperationParameterLocation
from appbuilder.rules import CanonicalRule, RuleType
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile


def _jobless_ownership_fixture(metadata: MetadataProject, output: Path | None = None) -> None:
    # Ownership adoption is independent of Batch; durable Boot 4 evidence is mandatory.
    metadata.contracts = [c for c in metadata.contracts if c.type not in {"staging-table", "file-fixed-width"}]
    metadata.mappings = [m for m in metadata.mappings if m.direction == MappingDirection.UPSTREAM_TO_CANONICAL]
    metadata.mapping_reports = [r for r in metadata.mapping_reports if r.direction == MappingDirection.UPSTREAM_TO_CANONICAL]
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        (output / "pom.xml").write_text(_render_pom_xml(
            metadata=metadata, target_profile=TARGET_PROFILES[metadata.target_profile],
            source_manifest="ownership-fixture", generation_run_id="ownership-fixture",
        ), encoding="utf-8")


def _extract_dashboard_descriptors(html: str) -> list[dict]:
    match = re.search(
        r"const DESCRIPTORS = (\[.*?\]);\n    const DESCRIPTOR_BY_KEY",
        html,
        re.S,
    )
    assert match, "Generated dashboard must expose inline DESCRIPTORS"
    return json.loads(match.group(1))


def _dashboard_descriptor(html: str, coverage_key: str) -> dict:
    matches = [
        descriptor
        for descriptor in _extract_dashboard_descriptors(html)
        if descriptor["coverageKey"] == coverage_key
    ]
    assert len(matches) == 1, f"Expected exactly one descriptor for {coverage_key}"
    return matches[0]


def _dashboard_entity_panel(html: str, entity_name: str) -> str:
    marker = f'id="entity-panel-{entity_name}"'
    start = html.index(marker)
    next_panel = html.find('id="entity-panel-', start + len(marker))
    end = next_panel if next_panel != -1 else html.index("</main>", start)
    return html[start:end]


def _dashboard_group_section(panel_html: str, group: str) -> str:
    marker = f'data-group="{group}"'
    marker_index = panel_html.index(marker)
    start = panel_html.rfind("<details", 0, marker_index)
    next_section = panel_html.find('<details class="group-section"', marker_index)
    live_section = panel_html.find('<div class="live-section"', marker_index)
    candidates = [index for index in [next_section, live_section] if index != -1]
    end = min(candidates) if candidates else len(panel_html)
    return panel_html[start:end]


def test_passthrough_router_archetype_generates_router_app(tmp_path: Path) -> None:
    metadata = build_metadata_project("examples/input-projects/country-router/app-definition.yaml")

    report = generate_application(
        metadata,
        tmp_path / "CountryRouter",
        source_manifest="examples/input-projects/country-router/app-definition.yaml",
        generation_run_id="pt-test",
    )

    assert report.files_created
    assert report.harness_report is None


def test_generate_xyz_accounts_produces_expected_files(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()

    report = generate_application(
        metadata,
        tmp_path / "BuiltApp1",
        source_manifest="examples/input-projects/xyz-accounts-modernization/app-definition.yaml",
        generation_run_id="test-run",
    )

    expected_files = {
        "pom.xml",
        "Dockerfile",
        "README.md",
        ".gitignore",
        ".dockerignore",
        # C1: deterministic agent-context.md emitted into every generated app
        "agent-context.md",
        "db/schema-baseline.json",
        "db/generation-provenance.json",
        "src/main/resources/application.yaml",
        "src/main/resources/static/index.html",
        "src/main/resources/db/migration/V1__create_account_table.sql",
        # staging table migration emitted from data-handoff DDL spec
        "src/main/resources/db/migration/V2__create_acct_staging_tbl_table.sql",
        "src/main/resources/db/migration/V3__create_pkg_batch_metadata.sql",
        "src/main/java/com/appbuilder/accounts/AccountsApplication.java",
        "src/main/java/com/appbuilder/accounts/config/SecurityHeadersFilter.java",
        "src/main/java/com/appbuilder/accounts/domain/Account.java",
        "src/main/java/com/appbuilder/accounts/repository/AccountRepository.java",
        "src/main/java/com/appbuilder/accounts/service/AccountServiceBase.java",
        "src/main/java/com/appbuilder/accounts/service/AccountService.java",
        "src/main/java/com/appbuilder/accounts/adapter/inbound/CreateAccountRequest.java",
        "src/main/java/com/appbuilder/accounts/adapter/inbound/CreateAccountResponse.java",
        "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountResponse.java",
        "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountUpdateRequest.java",
        "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountController.java",
        "src/main/java/com/appbuilder/accounts/adapter/outbound/AccountEodHandoffFileWriter.java",
        "src/main/java/com/appbuilder/accounts/adapter/outbound/AccountStagingWriter.java",
        "src/main/java/com/appbuilder/accounts/batch/AccountEodBatchJob.java",
        # BatchTriggerController is now emitted alongside batch jobs
        "src/main/java/com/appbuilder/accounts/adapter/inbound/BatchTriggerController.java",
        "src/test/java/com/appbuilder/accounts/AccountsApplicationTest.java",
        # Phase 1a: error-handling singletons emitted once per app
        "src/main/java/com/appbuilder/accounts/exception/ResourceNotFoundException.java",
        "src/main/java/com/appbuilder/accounts/exception/DuplicateResourceException.java",
        "src/main/java/com/appbuilder/accounts/exception/ErrorResponse.java",
        "src/main/java/com/appbuilder/accounts/exception/GlobalExceptionHandler.java",
        # DemoController — config-gated /api/demo/entities endpoints
        "src/main/java/com/appbuilder/accounts/adapter/inbound/DemoController.java",
    }

    assert {path.relative_to(report.output_dir).as_posix() for path in report.files_created} == expected_files
    assert report.generation_mode == "greenfield"


def test_generated_artifacts_do_not_leak_absolute_manifest_paths(tmp_path: Path) -> None:
    sentinel = "edgeforge-absolute-path-sentinel"
    fixture_source = Path("examples/input-projects/xyz-accounts-modernization")
    fixture_root = tmp_path / sentinel / "author-home" / "project"
    shutil.copytree(fixture_source, fixture_root)
    manifest = fixture_root / "app-definition.yaml"
    metadata = build_metadata_project(manifest)
    output_dir = tmp_path / "BuiltAppPathLeakScan"

    generate_application(
        metadata,
        output_dir,
        source_manifest=str(manifest.resolve()),
        generation_run_id="path-leak-test",
    )

    leaked_files = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        if sentinel in content or str(fixture_root) in content:
            leaked_files.append(path.relative_to(output_dir).as_posix())
    assert leaked_files == []

    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    agent_context = (output_dir / "agent-context.md").read_text(encoding="utf-8")
    application_yaml = (output_dir / "src/main/resources/application.yaml").read_text(
        encoding="utf-8"
    )
    assert "Source manifest: app-definition.yaml" in readme
    assert "- Source manifest: `app-definition.yaml`" in agent_context
    assert "Source manifest: app-definition.yaml" in application_yaml


def test_generated_file_xml_base_dir_defaults_are_instance_isolated() -> None:
    shared_file_dir = _isolated_tmp_base_dir_default("shared-context", "file-ingest")
    shared_xml_ingest_dir = _isolated_tmp_base_dir_default("shared-context", "xml-ingest")
    fallback_xml_output_dir = _isolated_tmp_base_dir_default("", "xml-output")

    assert "/tmp/shared-context/ingest" not in shared_file_dir
    assert "/tmp/shared-context/xml-ingest" not in shared_xml_ingest_dir
    assert "/tmp/app/xml-output" not in fallback_xml_output_dir
    assert "${java.io.tmpdir}/edgeforge-shared-context-" in shared_file_dir
    assert "${java.io.tmpdir}/edgeforge-app-" in fallback_xml_output_dir
    assert "${APP_INSTANCE_ID:${random.uuid}}" in shared_file_dir
    assert "${APP_INSTANCE_ID:${random.uuid}}" in shared_xml_ingest_dir
    assert "${APP_INSTANCE_ID:${random.uuid}}" in fallback_xml_output_dir
    assert (
        shared_file_dir.replace("${APP_INSTANCE_ID:${random.uuid}}", "instance-a")
        != shared_file_dir.replace("${APP_INSTANCE_ID:${random.uuid}}", "instance-b")
    )


def test_schema_baseline_captures_effective_schema_and_is_deterministic(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    first_output = tmp_path / "BuiltAppBaselineA"
    second_output = tmp_path / "BuiltAppBaselineB"

    first_report = generate_application(metadata, first_output, generation_run_id="baseline-a")
    second_report = generate_application(metadata, second_output, generation_run_id="baseline-b")

    baseline_path = first_output / "db/schema-baseline.json"
    first_baseline = baseline_path.read_text(encoding="utf-8")
    second_baseline = (second_output / "db/schema-baseline.json").read_text(encoding="utf-8")
    assert first_baseline == second_baseline
    assert baseline_path in first_report.files_created
    assert second_output / "db/schema-baseline.json" in second_report.files_created

    baseline = json.loads(first_baseline)
    assert baseline["baseline_schema_version"] == "1.0"
    assert baseline["manifest_schema_version"] == "2.0"
    assert baseline["target_profile"] == "springboot-legacy-compatible"
    assert baseline["manifest_hash"]
    assert baseline["flyway_high_water_mark"] == 3
    account = baseline["entities"][0]
    assert account["entity"] == "Account"
    assert account["table"] == "account"
    assert account["primary_key"]["field"] == "accountId"
    account_id_column = next(
        column for column in account["columns"] if column["field"] == "accountId"
    )
    assert account_id_column["name"] == "account_id"
    assert account_id_column["canonical_type"] == "string"
    assert account_id_column["sql_type"] == "VARCHAR(36)"
    assert account_id_column["nullable"] is False
    assert account_id_column["primary_key"] is True
    assert "src/main/java/com/appbuilder/accounts/service/AccountServiceBase.java" in account[
        "generated_source_files"
    ]
    generated_sources = account["generated_source_files"]
    assert generated_sources == sorted(generated_sources)
    assert not any(path.endswith("/AccountService.java") for path in generated_sources)
    for relative_path in generated_sources:
        source_path = first_output / relative_path
        assert source_path.exists(), f"baseline listed missing source: {relative_path}"
        assert (
            "// EdgeForge-ownership: generated"
            in source_path.read_text(encoding="utf-8")
        )
    assert any(path.endswith("/AccountStagingWriter.java") for path in generated_sources)
    assert any(path.endswith("/AccountEodBatchJob.java") for path in generated_sources)
    assert any(
        path.endswith("/AccountEodHandoffFileWriter.java")
        for path in generated_sources
    )
    assert baseline["staging_tables"][0]["name"] == "acct_staging_tbl"
    assert baseline["staging_tables"][0]["ddl_sha256"]


def test_crud_repository_hygiene_files_preserve_manual_edits(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltAppHygiene"
    generate_application(metadata, output_dir, generation_run_id="hygiene-first")

    for name in (".gitignore", ".dockerignore"):
        path = output_dir / name
        content = path.read_text(encoding="utf-8")
        assert "# EdgeForge-ownership: developer" in content
        assert "target/" in content
        assert "accounts-eod/" in content
        path.write_text(content + "# adopter edit\n", encoding="utf-8")

    generate_application(metadata, output_dir, generation_run_id="hygiene-second")
    for name in (".gitignore", ".dockerignore"):
        assert (output_dir / name).read_text(encoding="utf-8").endswith(
            "# adopter edit\n"
        )


def test_generation_mode_detection_reports_regenerate_and_legacy(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    regen_output = tmp_path / "BuiltAppRegenMode"

    first_report = generate_application(metadata, regen_output, generation_run_id="first")
    second_report = generate_application(metadata, regen_output, generation_run_id="second")

    assert first_report.generation_mode == "greenfield"
    assert second_report.generation_mode == "regenerate"

    legacy_output = tmp_path / "BuiltAppLegacyMode"
    _jobless_ownership_fixture(metadata, legacy_output)
    legacy_service = (
        legacy_output / "src/main/java/com/appbuilder/accounts/service/AccountService.java"
    )
    legacy_service.parent.mkdir(parents=True)
    legacy_service.write_text(
        "\n".join(
            [
                "// Generated by EdgeForge",
                "// Source manifest: old-manifest.yaml",
                "// Target profile: springboot-legacy-compatible",
                "// Generation run: old-run",
                "",
                "package com.appbuilder.accounts.service;",
                "",
                "public class AccountService {}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    legacy_report = generate_application(metadata, legacy_output, generation_run_id="legacy")

    assert legacy_report.generation_mode == "legacy"
    assert any("legacy generated package detected" in warning for warning in legacy_report.warnings)
    assert (legacy_output / "db/schema-baseline.json").exists()
    legacy_baseline = json.loads(
        (legacy_output / "db/schema-baseline.json").read_text(encoding="utf-8")
    )
    assert legacy_baseline["manifest_schema_version"] == "2.0"
    legacy_migrations = list(
        (legacy_output / "src/main/resources/db/migration").glob("V*.sql")
    )
    assert legacy_migrations
    assert legacy_baseline["flyway_high_water_mark"] == max(
        int(path.name.split("__", 1)[0][1:]) for path in legacy_migrations
    )


def test_legacy_adoption_preserves_existing_flyway_inventory_bytes(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    seed_output = tmp_path / "BuiltAppMigrationSeed"
    _jobless_ownership_fixture(metadata)
    generate_application(metadata, seed_output, generation_run_id="pre-cut-seed")

    seed_migration_dir = seed_output / "src/main/resources/db/migration"
    legacy_output = tmp_path / "BuiltAppLegacyMigrations"
    _jobless_ownership_fixture(metadata, legacy_output)
    legacy_migration_dir = legacy_output / "src/main/resources/db/migration"
    legacy_migration_dir.mkdir(parents=True)
    seed_path = next(iter(sorted(seed_migration_dir.glob("V*.sql"))))
    legacy_content = "\n".join(
        line
        for line in seed_path.read_text(encoding="utf-8").splitlines()
        if "EdgeForge-ownership:" not in line
        and "Manifest schema version:" not in line
    ) + "\n"
    legacy_path = legacy_migration_dir / "V7__legacy_manual.sql"
    legacy_bytes = legacy_content.encode("utf-8")
    legacy_path.write_bytes(legacy_bytes)
    expected_bytes = {legacy_path.name: legacy_bytes}
    expected_checksums = {
        legacy_path.name: hashlib.sha256(legacy_bytes).hexdigest()
    }

    report = generate_application(
        metadata,
        legacy_output,
        generation_run_id="approved-adoption",
    )

    assert report.generation_mode == "legacy"
    adopted_paths = sorted(legacy_migration_dir.glob("V*.sql"))
    assert [path.name for path in adopted_paths] == sorted(expected_bytes)
    assert {path.name: path.read_bytes() for path in adopted_paths} == expected_bytes
    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in adopted_paths
    } == expected_checksums
    baseline = json.loads(
        (legacy_output / "db/schema-baseline.json").read_text(encoding="utf-8")
    )
    assert baseline["manifest_schema_version"] == "2.0"
    assert baseline["flyway_high_water_mark"] == 7


def test_regenerate_mode_does_not_advance_baseline_before_additive_diff(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltAppBaselineFreeze"

    generate_application(metadata, output_dir, generation_run_id="first")
    baseline_path = output_dir / "db/schema-baseline.json"
    legacy_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    legacy_baseline.pop("manifest_schema_version")
    baseline_path.write_text(
        json.dumps(legacy_baseline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    original_baseline = baseline_path.read_text(encoding="utf-8")
    migration_dir = output_dir / "src/main/resources/db/migration"
    original_migrations = {
        path.name: path.read_bytes() for path in sorted(migration_dir.glob("V*.sql"))
    }

    evolved_metadata = metadata.model_copy(deep=True)
    evolved_metadata.entities[0].fields.append(
        CanonicalField(
            name="nickname",
            type=CanonicalFieldType.STRING,
            max_length=40,
            source_paths=["manual.nickname"],
        )
    )

    report = generate_application(evolved_metadata, output_dir, generation_run_id="second")

    assert report.generation_mode == "regenerate"
    assert baseline_path.read_text(encoding="utf-8") == original_baseline
    assert "manifest_schema_version" not in json.loads(original_baseline)
    assert {
        path.name: path.read_bytes() for path in sorted(migration_dir.glob("V*.sql"))
    } == original_migrations
    entity_source = (
        output_dir / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    ).read_text(encoding="utf-8")
    assert "private String nickname;" in entity_source


def test_malformed_schema_baseline_fails_closed(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltAppMalformedBaseline"

    generate_application(metadata, output_dir, generation_run_id="first")
    (output_dir / "db/schema-baseline.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported existing package transition"):
        generate_application(metadata, output_dir, generation_run_id="second")

    assert (output_dir / "db/schema-baseline.json").read_text(encoding="utf-8") == "{not-json"


def test_legacy_adoption_backs_up_hand_edited_generated_files(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltAppLegacyFileProtection"
    _jobless_ownership_fixture(metadata, output_dir)
    legacy_entity = output_dir / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    legacy_entity.parent.mkdir(parents=True)
    legacy_source = "\n".join(
        [
            "// Generated by EdgeForge",
            "// Source manifest: old-manifest.yaml",
            "// Target profile: springboot-legacy-compatible",
            "// Generation run: old-run",
            "",
            "package com.appbuilder.accounts.domain;",
            "",
            "public class Account {",
            "    // HAND EDITED LEGACY GENERATED ENTITY",
            "}",
            "",
        ]
    )
    legacy_entity.write_text(legacy_source, encoding="utf-8")

    report = generate_application(metadata, output_dir, generation_run_id="legacy-protect")

    backup_entity = legacy_entity.with_name("Account.java.legacy.bak")
    assert backup_entity.exists()
    assert backup_entity.read_text(encoding="utf-8") == legacy_source
    regenerated_entity_source = legacy_entity.read_text(encoding="utf-8")
    assert "// EdgeForge-ownership: generated" in regenerated_entity_source
    assert "HAND EDITED LEGACY GENERATED ENTITY" not in regenerated_entity_source
    assert any(
        "legacy generated file preserved before ownership adoption: "
        "src/main/java/com/appbuilder/accounts/domain/Account.java -> Account.java.legacy.bak"
        in warning
        for warning in report.warnings
    )


def test_regeneration_prunes_orphaned_generated_sources_and_preserves_developer_service(
    tmp_path: Path,
) -> None:
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
            CanonicalField(name="status", type=CanonicalFieldType.STRING),
        ],
    )
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
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING),
        ],
    )
    initial_metadata = MetadataProject(
        app_name="Orphan Prune",
        bounded_context="orphan",
        target_profile="springboot-legacy-compatible",
        contracts=[
            ContractMetadata(name="customer-fixed-out", type="file-fixed-width", source=""),
        ],
        entities=[account, customer],
        mappings=[
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="customer-fixed-out",
                source_path="Customer.customerName",
                target_path="customer-fixed-out.customer_name",
                layout_width=24,
            )
        ],
    )
    evolved_metadata = initial_metadata.model_copy(deep=True)
    evolved_metadata.entities = [account]
    evolved_metadata.contracts = []
    evolved_metadata.mappings = []
    output_dir = tmp_path / "OrphanPruneApp"

    generate_application(initial_metadata, output_dir, generation_run_id="first")

    java_root = output_dir / "src/main/java/com/appbuilder/orphan"
    customer_service = java_root / "service/CustomerService.java"
    developer_source = customer_service.read_text(encoding="utf-8").replace(
        "        // Add post-create business logic here.",
        "        // PRESERVED CUSTOMER BUSINESS LOGIC\n        // Add post-create business logic here.",
    )
    customer_service.write_text(developer_source, encoding="utf-8")
    customer_migration = output_dir / "src/main/resources/db/migration/V2__create_customer_table.sql"
    customer_migration_before = customer_migration.read_text(encoding="utf-8")

    report = generate_application(evolved_metadata, output_dir, generation_run_id="second")

    assert report.generation_mode == "regenerate"
    assert not (java_root / "domain/Customer.java").exists()
    assert not (java_root / "repository/CustomerRepository.java").exists()
    assert not (java_root / "service/CustomerServiceBase.java").exists()
    assert not (java_root / "adapter/inbound/CustomerController.java").exists()
    assert not (java_root / "adapter/inbound/CustomerCreateRequest.java").exists()
    assert not (java_root / "adapter/inbound/CustomerUpdateRequest.java").exists()
    assert not (java_root / "adapter/inbound/CustomerResponse.java").exists()
    archived_service = customer_service.with_name("CustomerService.java.orphaned.bak")
    assert not customer_service.exists()
    assert archived_service.read_text(encoding="utf-8") == developer_source
    assert not (java_root / "adapter/outbound/CustomerEodHandoffFileWriter.java").exists()
    assert not (java_root / "batch/CustomerEodBatchJob.java").exists()
    assert not (java_root / "adapter/inbound/DemoController.java").exists()
    assert any(
        "Customer: developer-owned orphan source preserved as "
        "CustomerService.java.orphaned.bak" in warning
        for warning in report.warnings
    )
    assert any(
        "generated test-console artifact pruned: "
        "src/main/java/com/appbuilder/orphan/adapter/inbound/DemoController.java"
        in warning
        for warning in report.warnings
    )
    assert customer_migration.exists()
    assert customer_migration.read_text(encoding="utf-8") == customer_migration_before


def test_service_generation_gap_emits_generated_base_and_developer_subclass(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()

    output_dir = tmp_path / "BuiltAppServiceSplit"
    generate_application(metadata, output_dir, generation_run_id="service-split-test")

    service_dir = output_dir / "src/main/java/com/appbuilder/accounts/service"
    base_source = (service_dir / "AccountServiceBase.java").read_text(encoding="utf-8")
    service_source = (service_dir / "AccountService.java").read_text(encoding="utf-8")
    controller_source = (
        output_dir / "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountController.java"
    ).read_text(encoding="utf-8")

    assert "// EdgeForge-ownership: generated" in base_source
    assert "// EdgeForge-ownership: developer" in service_source
    assert "public abstract class AccountServiceBase" in base_source
    assert "@Service" not in base_source
    assert "public class AccountService extends AccountServiceBase" in service_source
    assert "@Service" in service_source
    assert "public AccountService(AccountRepository accountRepository)" in service_source
    assert "super(accountRepository);" in service_source
    assert "private final AccountService accountService;" in controller_source
    assert "public CreateAccountResponse createAccount(CreateAccountRequest request)" in base_source
    assert "protected void beforeCreate(Account account)" in base_source
    assert "protected void afterCreate(Account account)" in base_source
    assert "protected void beforeUpdate(Account account)" in base_source
    assert "protected void afterUpdate(Account account)" in base_source
    assert "protected void beforeDelete(String id)" in base_source
    assert "protected final void applyBusinessRules(Account account)" in base_source
    assert "protected void afterGeneratedBusinessRules(Account account)" in base_source
    assert "protected void validateFormat(Account account, String fieldName, Object value)" in base_source
    assert "protected void compareValues(Account account, String ruleName, Object leftValue, Object rightValue, String operator)" in base_source
    assert "protected void validateComparison(Account account, String ruleName, Object leftValue, Object rightValue, String operator)" in base_source
    assert "protected Account computeDerivedRead(String operationName, Object... args)" in base_source
    assert "protected void applyBusinessRules(Account account)" not in service_source
    assert "protected void afterGeneratedBusinessRules(Account account)" in service_source


def test_regeneration_preserves_developer_service_and_refreshes_generated_base(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltAppServiceRegeneration"

    generate_application(metadata, output_dir, generation_run_id="first-run")

    service_dir = output_dir / "src/main/java/com/appbuilder/accounts/service"
    developer_service = service_dir / "AccountService.java"
    generated_base = service_dir / "AccountServiceBase.java"

    edited_developer_source = developer_service.read_text(encoding="utf-8").replace(
        "        // Add pre-create business logic here.",
        "        // CUSTOM BUSINESS LOGIC MARKER\n        // Add pre-create business logic here.",
    )
    developer_service.write_text(edited_developer_source, encoding="utf-8")
    generated_base.write_text(
        generated_base.read_text(encoding="utf-8") + "\n// STALE GENERATED BASE MARKER\n",
        encoding="utf-8",
    )

    generate_application(metadata, output_dir, generation_run_id="second-run")

    assert developer_service.read_text(encoding="utf-8") == edited_developer_source
    regenerated_base_source = generated_base.read_text(encoding="utf-8")
    assert "// STALE GENERATED BASE MARKER" not in regenerated_base_source
    assert "// Generation run: second-run" in regenerated_base_source
    assert "// Generation run: first-run" in edited_developer_source


def test_regeneration_adopts_legacy_generated_service_without_ownership_marker(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltAppLegacyServiceAdoption"
    _jobless_ownership_fixture(metadata, output_dir)
    legacy_service = (
        output_dir / "src/main/java/com/appbuilder/accounts/service/AccountService.java"
    )
    legacy_service.parent.mkdir(parents=True)
    legacy_source = "\n".join(
        [
            "// Generated by EdgeForge",
            "// Source manifest: old-manifest.yaml",
            "// Target profile: springboot-legacy-compatible",
            "// Generation run: old-run",
            "",
            "package com.appbuilder.accounts.service;",
            "",
            "public class AccountService {",
            "    // HAND EDITED LEGACY GENERATED SERVICE",
            "}",
            "",
        ]
    )
    legacy_service.write_text(legacy_source, encoding="utf-8")

    report = generate_application(metadata, output_dir, generation_run_id="adoption-run")

    backup_service = legacy_service.with_name("AccountService.java.legacy.bak")
    assert backup_service.exists()
    assert backup_service.read_text(encoding="utf-8") == legacy_source
    adopted_service_source = legacy_service.read_text(encoding="utf-8")
    assert "// EdgeForge-ownership: developer" in adopted_service_source
    assert "public class AccountService extends AccountServiceBase" in adopted_service_source
    assert "HAND EDITED LEGACY GENERATED SERVICE" not in adopted_service_source
    assert (
        "legacy generated service adopted for regeneration ownership split"
        in "\n".join(report.warnings)
    )


def test_legacy_service_adoption_uses_unique_backup_when_default_backup_exists(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltAppLegacyServiceBackupCollision"
    _jobless_ownership_fixture(metadata, output_dir)
    legacy_service = (
        output_dir / "src/main/java/com/appbuilder/accounts/service/AccountService.java"
    )
    legacy_service.parent.mkdir(parents=True)
    previous_backup_source = "// older preserved service\n"
    current_legacy_source = "\n".join(
        [
            "// Generated by EdgeForge",
            "// Source manifest: restored-legacy.yaml",
            "// Target profile: springboot-legacy-compatible",
            "// Generation run: restored-run",
            "",
            "package com.appbuilder.accounts.service;",
            "",
            "public class AccountService {",
            "    // CURRENT RESTORED LEGACY CONTENT",
            "}",
            "",
        ]
    )
    legacy_service.with_name("AccountService.java.legacy.bak").write_text(
        previous_backup_source,
        encoding="utf-8",
    )
    legacy_service.write_text(current_legacy_source, encoding="utf-8")

    generate_application(metadata, output_dir, generation_run_id="backup-collision-run")

    assert (
        legacy_service.with_name("AccountService.java.legacy.bak").read_text(encoding="utf-8")
        == previous_backup_source
    )
    collision_backup = legacy_service.with_name("AccountService.java.legacy.bak.1")
    assert collision_backup.exists()
    assert collision_backup.read_text(encoding="utf-8") == current_legacy_source
    assert "CURRENT RESTORED LEGACY CONTENT" not in legacy_service.read_text(encoding="utf-8")


def test_entity_uses_bigdecimal_for_decimal_fields(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    metadata.entities[0].fields.append(
        CanonicalField(
            name="availableBalance",
            type=CanonicalFieldType.DECIMAL,
            required=False,
            source_paths=["rules.Account.availableBalance.default"],
        )
    )

    output_dir = tmp_path / "BuiltAppDecimal"
    generate_application(metadata, output_dir, generation_run_id="decimal-test")
    entity_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    ).read_text(encoding="utf-8")

    assert "import java.math.BigDecimal;" in entity_source
    assert "private BigDecimal availableBalance;" in entity_source
    assert "double availableBalance" not in entity_source
    assert "float availableBalance" not in entity_source


def test_entity_uses_java_time_for_dates(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    metadata.entities[0].fields.extend(
        [
            CanonicalField(
                name="openedOn",
                type=CanonicalFieldType.DATE,
                required=False,
                source_paths=["rules.Account.openedOn.default"],
            ),
            CanonicalField(
                name="lastUpdatedAt",
                type=CanonicalFieldType.DATETIME,
                required=False,
                source_paths=["rules.Account.lastUpdatedAt.default"],
            ),
        ]
    )

    output_dir = tmp_path / "BuiltAppDates"
    generate_application(metadata, output_dir, generation_run_id="date-test")
    entity_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    ).read_text(encoding="utf-8")

    assert "import java.time.LocalDate;" in entity_source
    assert "import java.time.LocalDateTime;" in entity_source
    assert "private LocalDate openedOn;" in entity_source
    assert "private LocalDateTime lastUpdatedAt;" in entity_source
    assert "java.util.Date" not in entity_source


def test_controller_preserves_upstream_contract_field_names(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    metadata.mappings[0].source_path = "crm-account-api.createAccount.request.customer_id"

    output_dir = tmp_path / "BuiltAppJson"
    generate_application(metadata, output_dir, generation_run_id="json-test")
    request_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/CreateAccountRequest.java"
    ).read_text(encoding="utf-8")

    assert '@JsonProperty("customer_id")' in request_source
    assert "private String customerId;" in request_source


def test_dto_preserves_pascal_case_contract_field_names(tmp_path: Path) -> None:
    entity = CanonicalEntity(
        name="DomesticPayment",
        fields=[
            CanonicalField(
                name="ConsentId",
                type=CanonicalFieldType.STRING,
                required=True,
                source_paths=["bank-domesticpayment-api.request.Data.ConsentId"],
            ),
            CanonicalField(
                name="DomesticPaymentId",
                type=CanonicalFieldType.STRING,
                required=False,
                source_paths=["bank-domesticpayment-api.response.Data.DomesticPaymentId"],
            ),
        ],
    )
    request_mapping = FieldMapping(
        contract_name="bank-domesticpayment-api",
        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
        operation_name="CreateDomesticPayments",
        source_path="bank-domesticpayment-api.CreateDomesticPayments.request.ConsentId",
        target_path="DomesticPayment.ConsentId",
    )
    response_mappings = [
        FieldMapping(
            contract_name="bank-domesticpayment-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="CreateDomesticPayments",
            source_path="bank-domesticpayment-api.CreateDomesticPayments.response.ConsentId",
            target_path="DomesticPayment.ConsentId",
        ),
        FieldMapping(
            contract_name="bank-domesticpayment-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="CreateDomesticPayments",
            source_path="bank-domesticpayment-api.CreateDomesticPayments.response.DomesticPaymentId",
            target_path="DomesticPayment.DomesticPaymentId",
        ),
    ]

    request_source = _render_dto(
        class_name="CreateDomesticPaymentsRequest",
        package_name="com.appbuilder.bank.adapter.inbound",
        entity=entity,
        field_mappings=[request_mapping],
        emit_validation_annotations=True,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test-manifest.yaml",
        generation_run_id="pascal-case-json-test",
    )
    response_source = _render_dto(
        class_name="CreateDomesticPaymentsResponse",
        package_name="com.appbuilder.bank.adapter.inbound",
        entity=entity,
        field_mappings=response_mappings,
        emit_validation_annotations=False,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test-manifest.yaml",
        generation_run_id="pascal-case-json-test",
    )

    for source, names in ((request_source, ["ConsentId"]),
                          (response_source, ["ConsentId", "DomesticPaymentId"])):
        for name in names:
            assert source.count(f'@JsonProperty("{name}")') == 3
            assert f'@JsonProperty("{name}")\n    public String get{name}()' in source
            assert f'@JsonProperty("{name}")\n    public void set{name}(String {name})' in source


@pytest.mark.parametrize("canonical,wire,explicit", [
    ("customerId", "customerId", False),
    ("customerId", "customer_id", True),
    ("customerId", "CustomerId", True),
    ("ConsentId", "ConsentId", True),
    ("ConsentId", "consentId", True),
    ("URL", "URL", True),
    ("uRL", "link", True),
    ("external_code", "external_code", True),
])
def test_dto_mapping_links_field_and_both_accessors(canonical, wire, explicit):
    from appbuilder.generation.utils import to_pascal_case

    source = _render_dto(
        class_name="MappedRequest", package_name="proof.dto",
        entity=CanonicalEntity(name="Record", fields=[CanonicalField(
            name=canonical, type=CanonicalFieldType.STRING, required=False, source_paths=[])]),
        field_mappings=[FieldMapping(contract_name="api", direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="create", source_path=f"api.create.request.{wire}", target_path=f"Record.{canonical}")],
        emit_validation_annotations=False, target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="fixture.yaml", generation_run_id="dto-property-proof")
    annotation = f'@JsonProperty("{wire}")'
    assert source.count(annotation) == (3 if explicit else 0)
    suffix = to_pascal_case(canonical)
    assert f"private String {canonical};" in source
    assert f"return {canonical};" in source
    assert f"this.{canonical} = {canonical};" in source
    if explicit:
        assert f"{annotation}\n    public String get{suffix}()" in source
        assert f"{annotation}\n    public void set{suffix}(String {canonical})" in source


def test_duplicate_response_field_mappings_do_not_emit_duplicate_dto_members(tmp_path: Path) -> None:
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalOperation,
        ContractMetadata,
        MetadataProject,
        SystemParticipant,
    )

    entity = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(
                name="customerId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=36,
                source_paths=["customer-api.createCustomer.response.customerId"],
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=False,
                max_length=32,
                source_paths=["customer-api.createCustomer.response.status"],
            ),
        ],
    )
    operation = CanonicalOperation(
        name="createCustomer",
        interface_name="customer-api",
        request_entity="Customer",
        response_entity="Customer",
    )
    mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.request.customerId",
            target_path="Customer.customerId",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.response.status",
            target_path="Customer.status",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.response.lifecycleStatus",
            target_path="Customer.status",
        ),
    ]
    profile_name = "springboot-duplicate-response-dto-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=False,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )
    metadata = MetadataProject(
        app_name="Customer App",
        bounded_context="customers",
        target_profile=profile_name,
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[ContractMetadata(name="customer-api", type="rest-json", source="")],
        operations=[operation],
        entities=[entity],
        mappings=mappings,
    )

    try:
        output_dir = tmp_path / "CustomerApp"
        generate_application(metadata, output_dir, generation_run_id="dedupe-response-dto")
        response_source = (
            output_dir
            / "src/main/java/com/appbuilder/customers/adapter/inbound/CreateCustomerResponse.java"
        ).read_text(encoding="utf-8")

        assert response_source.count("private String status;") == 1
        assert response_source.count("public String getStatus()") == 1
        assert response_source.count("public void setStatus(String status)") == 1
    finally:
        TARGET_PROFILES.pop(profile_name, None)


def test_mapped_rest_operation_dto_wins_over_unmapped_duplicate(tmp_path: Path) -> None:
    entity = CanonicalEntity(
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
                max_length=80,
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=False,
                max_length=32,
            ),
        ],
    )
    mapped_op = CanonicalOperation(
        name="createCustomer",
        interface_name="customer-api",
        request_entity="Customer",
        response_entity="Customer",
        http_method=HttpMethod.POST,
        path="/customers",
        has_request_body=True,
        response_shape=ResponseShape.CREATED,
    )
    unmapped_duplicate_op = CanonicalOperation(
        name="createCustomer",
        interface_name="edge-contract-integrated-v1-smoke-account-api",
        request_entity="Customer",
        response_entity="Customer",
        http_method=HttpMethod.POST,
        path="/customers",
        has_request_body=True,
        response_shape=ResponseShape.CREATED,
    )
    mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.request.customerName",
            target_path="Customer.customerName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.request.status",
            target_path="Customer.status",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.response.customerId",
            target_path="Customer.customerId",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.response.customerName",
            target_path="Customer.customerName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.response.status",
            target_path="Customer.status",
        ),
    ]
    profile_name = "springboot-rest-operation-dto-collision-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=False,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )
    metadata = MetadataProject(
        app_name="Customer DTO Collision App",
        bounded_context="customers",
        target_profile=profile_name,
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[
            ContractMetadata(name="customer-api", type="rest-json", source=""),
            ContractMetadata(
                name="edge-contract-integrated-v1-smoke-account-api",
                type="rest-json",
                source="",
            ),
        ],
        operations=[mapped_op, unmapped_duplicate_op],
        entities=[entity],
        mappings=mappings,
    )

    try:
        output_dir = tmp_path / "CustomerDtoCollisionApp"
        generate_application(metadata, output_dir, generation_run_id="rest-dto-collision")
        inbound_dir = output_dir / "src/main/java/com/appbuilder/customers/adapter/inbound"
        service_dir = output_dir / "src/main/java/com/appbuilder/customers/service"
        response_source = (inbound_dir / "CreateCustomerResponse.java").read_text(encoding="utf-8")
        request_source = (inbound_dir / "CreateCustomerRequest.java").read_text(encoding="utf-8")
        service_source = (service_dir / "CustomerServiceBase.java").read_text(encoding="utf-8")
        controller_source = (inbound_dir / "CustomerController.java").read_text(encoding="utf-8")

        assert response_source.count("private String customerId;") == 1
        assert response_source.count("private String customerName;") == 1
        assert response_source.count("private String status;") == 1
        assert "public void setCustomerId(String customerId)" in response_source
        assert "public void setCustomerName(String customerName)" in response_source
        assert "public void setStatus(String status)" in response_source
        assert "private String customerName;" in request_source
        assert "private String status;" in request_source
        assert "createCustomerResponse.setCustomerId(saved.getCustomerId());" in service_source
        assert "createCustomerResponse.setCustomerName(saved.getCustomerName());" in service_source
        assert "createCustomerResponse.setStatus(saved.getStatus());" in service_source
        assert '@RequestMapping("/customers")' in controller_source
        assert '"/customers/create_customer"' not in controller_source
    finally:
        TARGET_PROFILES.pop(profile_name, None)


def test_conflicting_duplicate_rest_operation_mappings_fail_generation(tmp_path: Path) -> None:
    entity = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
            CanonicalField(name="status", type=CanonicalFieldType.STRING, required=False),
        ],
    )
    first_op = CanonicalOperation(
        name="createCustomer",
        interface_name="customer-api",
        request_entity="Customer",
        response_entity="Customer",
        http_method=HttpMethod.POST,
        path="/customers",
        response_shape=ResponseShape.CREATED,
    )
    second_op = CanonicalOperation(
        name="createCustomer",
        interface_name="duplicate-customer-api",
        request_entity="Customer",
        response_entity="Customer",
        http_method=HttpMethod.POST,
        path="/customers",
        response_shape=ResponseShape.CREATED,
    )
    mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.response.customerId",
            target_path="Customer.customerId",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="duplicate-customer-api",
            operation_name="createCustomer",
            source_path="duplicate-customer-api.createCustomer.response.status",
            target_path="Customer.status",
        ),
    ]
    profile_name = "springboot-rest-operation-conflict-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=False,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )
    metadata = MetadataProject(
        app_name="Customer Conflict App",
        bounded_context="customers",
        target_profile=profile_name,
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[
            ContractMetadata(name="customer-api", type="rest-json", source=""),
            ContractMetadata(name="duplicate-customer-api", type="rest-json", source=""),
        ],
        operations=[first_op, second_op],
        entities=[entity],
        mappings=mappings,
    )

    try:
        with pytest.raises(ValueError, match="conflicting explicit mappings"):
            generate_application(metadata, tmp_path / "CustomerConflictApp", generation_run_id="rest-dto-conflict")
    finally:
        TARGET_PROFILES.pop(profile_name, None)


def test_entity_generates_prepersist_for_required_server_set_lifecycle_field() -> None:
    entity = CanonicalEntity(
        name="InternationalPayment",
        fields=[
            CanonicalField(
                name="internationalPaymentId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["obie.CreateInternationalPayments.response.InternationalPaymentId"],
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=True,
                allowed_values=["AcceptedSettlementInProcess", "Rejected"],
                source_paths=["obie.CreateInternationalPayments.response.Status"],
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="Wire Transfer",
        bounded_context="wire_transfer",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="BANK", role="upstream")],
        contracts=[ContractMetadata(name="obie-payment-initiation-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="CreateInternationalPayments",
                interface_name="obie-payment-initiation-api",
                request_entity="InternationalPayment",
                response_entity="InternationalPayment",
            )
        ],
        entities=[entity],
        mappings=[],
        rules=[
            CanonicalRule(
                entity_name="InternationalPayment",
                field_name="status",
                type=RuleType.ALLOWED_VALUES,
                source_path="rules.InternationalPayment.status.allowed-values",
                values=["AcceptedSettlementInProcess", "Rejected"],
            )
        ],
    )

    entity_java = _render_entity(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.wire_transfer",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="prepersist-test",
    )

    assert "@PrePersist" in entity_java
    assert "protected void initializeDefaults()" in entity_java
    assert 'if (this.status == null)' in entity_java
    assert 'this.status = "AcceptedSettlementInProcess";' in entity_java


def test_entity_defaults_required_response_only_enum_from_field_allowed_values() -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["acme.createAccount.response.accountId"],
            ),
            CanonicalField(
                name="productType",
                type=CanonicalFieldType.STRING,
                required=True,
                source_paths=["acme.createAccount.request.productType"],
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=True,
                allowed_values=["PENDING", "ACTIVE", "BLOCKED", "CLOSED"],
                source_paths=["acme.createAccount.response.status"],
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="Acme Banking",
        bounded_context="acme_banking",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="Acme", role="upstream")],
        contracts=[ContractMetadata(name="acme-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="createAccount",
                interface_name="acme-api",
                request_entity="Account",
                response_entity="Account",
            )
        ],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="acme-api",
                operation_name="createAccount",
                source_path="acme-api.createAccount.request.productType",
                target_path="Account.productType",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="acme-api",
                operation_name="createAccount",
                source_path="acme-api.createAccount.response.accountId",
                target_path="Account.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="acme-api",
                operation_name="createAccount",
                source_path="acme-api.createAccount.response.status",
                target_path="Account.status",
            ),
        ],
    )

    entity_java = _render_entity(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.acme_banking",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="field-allowed-values-default-test",
    )
    service_java = _render_service(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.acme_banking",
        op_contexts=[],
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="field-allowed-values-default-test",
    )

    assert "@PrePersist" in entity_java
    assert 'if (this.status == null)' in entity_java
    assert 'this.status = "PENDING";' in entity_java
    assert "Server-set fields (status, etc.) are initialized via @PrePersist on the entity." in service_java


def test_allowed_values_service_constant_escapes_generated_java_literals() -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=True,
            ),
            CanonicalField(name="status", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    malicious_value = '"); } static { /* injected */ } //'
    metadata = MetadataProject(
        app_name="Escaping Proof",
        bounded_context="escaping",
        target_profile="springboot-legacy-compatible",
        entities=[entity],
        rules=[
            CanonicalRule(
                entity_name="Account",
                field_name="status",
                type=RuleType.ALLOWED_VALUES,
                source_path="rules.Account.status.allowed-values",
                values=[
                    'quote"value',
                    r"slash\value",
                    "line\nbreak",
                    "tab\tvalue",
                    "ctrl\x01value",
                    malicious_value,
                ],
            )
        ],
    )

    service_java = _render_service(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.escaping",
        op_contexts=[],
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="allowed-values-escaping-test",
    )

    assert 'Set.of("quote\\"value", "slash\\\\value", "line\\nbreak", "tab\\tvalue", "ctrl\\u0001value",' in service_java
    assert '"\\"); } static { /* injected */ } //"' in service_java
    assert 'Set.of("quote"value' not in service_java


def test_entity_generates_prepersist_for_required_server_set_datetime_field() -> None:
    entity = CanonicalEntity(
        name="InternationalPayment",
        fields=[
            CanonicalField(
                name="internationalPaymentId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["obie.CreateInternationalPayments.response.InternationalPaymentId"],
            ),
            CanonicalField(
                name="statusUpdateDateTime",
                type=CanonicalFieldType.DATETIME,
                required=True,
                source_paths=["obie.CreateInternationalPayments.response.StatusUpdateDateTime"],
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="Wire Transfer",
        bounded_context="wire_transfer",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="BANK", role="upstream")],
        contracts=[ContractMetadata(name="obie-payment-initiation-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="CreateInternationalPayments",
                interface_name="obie-payment-initiation-api",
                request_entity="InternationalPayment",
                response_entity="InternationalPayment",
            )
        ],
        entities=[entity],
        mappings=[],
        rules=[],
    )

    entity_java = _render_entity(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.wire_transfer",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="prepersist-datetime-test",
    )

    assert "@PrePersist" in entity_java
    assert "import java.time.LocalDateTime;" in entity_java
    assert 'if (this.statusUpdateDateTime == null)' in entity_java
    assert 'this.statusUpdateDateTime = LocalDateTime.now();' in entity_java


def test_entity_generates_prepersist_for_string_typed_temporal_field_name() -> None:
    entity = CanonicalEntity(
        name="InternationalPayment",
        fields=[
            CanonicalField(
                name="internationalPaymentId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["obie.CreateInternationalPayments.response.InternationalPaymentId"],
            ),
            CanonicalField(
                name="statusUpdateDateTime",
                type=CanonicalFieldType.STRING,
                required=True,
                source_paths=["obie.CreateInternationalPayments.response.StatusUpdateDateTime"],
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="Wire Transfer",
        bounded_context="wire_transfer",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="BANK", role="upstream")],
        contracts=[ContractMetadata(name="obie-payment-initiation-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="CreateInternationalPayments",
                interface_name="obie-payment-initiation-api",
                request_entity="InternationalPayment",
                response_entity="InternationalPayment",
            )
        ],
        entities=[entity],
        mappings=[],
        rules=[],
    )

    entity_java = _render_entity(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.wire_transfer",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="prepersist-string-datetime-test",
    )

    assert "@PrePersist" in entity_java
    assert "import java.time.LocalDateTime;" in entity_java
    assert 'if (this.statusUpdateDateTime == null)' in entity_java
    assert 'this.statusUpdateDateTime = LocalDateTime.now().toString();' in entity_java


def test_response_only_required_business_field_does_not_break_create_constraints(
    tmp_path: Path,
) -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["crm-account-api.createAccount.response.accountId"],
            ),
            CanonicalField(
                name="productType",
                type=CanonicalFieldType.STRING,
                required=True,
                source_paths=["crm-account-api.createAccount.request.productType"],
            ),
            CanonicalField(
                name="accountNumber",
                type=CanonicalFieldType.STRING,
                required=True,
                not_null=True,
                source_paths=["crm-account-api.createAccount.response.accountNumber"],
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="CRM Accounts",
        bounded_context="crm_accounts",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[ContractMetadata(name="crm-account-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="createAccount",
                interface_name="crm-account-api",
                request_entity="Account",
                response_entity="Account",
            )
        ],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-account-api",
                operation_name="createAccount",
                source_path="crm-account-api.createAccount.request.productType",
                target_path="Account.productType",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-account-api",
                operation_name="createAccount",
                source_path="crm-account-api.createAccount.response.accountId",
                target_path="Account.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-account-api",
                operation_name="createAccount",
                source_path="crm-account-api.createAccount.response.accountNumber",
                target_path="Account.accountNumber",
            ),
        ],
    )

    output_dir = tmp_path / "ResponseOnlyRequiredField"
    generate_application(metadata, output_dir, generation_run_id="response-only-required-field")

    entity_source = (
        output_dir / "src/main/java/com/appbuilder/crm_accounts/domain/Account.java"
    ).read_text(encoding="utf-8")
    request_source = (
        output_dir
        / "src/main/java/com/appbuilder/crm_accounts/adapter/inbound/CreateAccountRequest.java"
    ).read_text(encoding="utf-8")
    migration = (
        output_dir / "src/main/resources/db/migration/V1__create_account_table.sql"
    ).read_text(encoding="utf-8")

    assert '@Column(name = "product_type", nullable = false)' in entity_source
    assert "private String productType;" in entity_source
    assert '@Column(name = "account_number")' in entity_source
    assert '@Column(name = "account_number", nullable = false)' not in entity_source
    assert "private String accountNumber;" not in request_source
    assert "product_type VARCHAR(255) NOT NULL" in migration
    assert "account_number VARCHAR(255)" in migration
    assert "account_number VARCHAR(255) NOT NULL" not in migration


def test_pageable_operation_emits_page_return_type_and_pageable_parameter(
    tmp_path: Path,
) -> None:
    metadata = _pageable_list_metadata(pageable=True)

    output_dir = tmp_path / "PageableListApp"
    generate_application(metadata, output_dir, generation_run_id="pageable-list-test")

    controller_source = (
        output_dir / "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountController.java"
    ).read_text(encoding="utf-8")
    service_source = (
        output_dir / "src/main/java/com/appbuilder/accounts/service/AccountServiceBase.java"
    ).read_text(encoding="utf-8")
    request_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/ListAccountsRequest.java"
    ).read_text(encoding="utf-8")

    assert "import org.springframework.data.domain.Page;" in controller_source
    assert "import org.springframework.data.domain.PageRequest;" in controller_source
    assert "import org.springframework.data.domain.Pageable;" in controller_source
    assert "public ResponseEntity<Page<ListAccountsResponse>> listAll(" in controller_source
    assert '@RequestParam(defaultValue = "0") int page' in controller_source
    assert '@RequestParam(defaultValue = "20") int size' in controller_source
    assert "Pageable pageable = PageRequest.of(page, size);" in controller_source
    assert "accountService.findAll(pageable)" in controller_source
    assert controller_source.count("private static final int MAX_PAGE_SIZE = 200;") == 1
    assert controller_source.count("private static final long MAX_PAGE_OFFSET = 50_000L;") == 1
    page_request = controller_source.index("Pageable pageable = PageRequest.of(page, size);")
    size_guard = controller_source.index("if (size > MAX_PAGE_SIZE)", page_request)
    offset_guard = controller_source.index(
        "if (pageable.getOffset() > MAX_PAGE_OFFSET)",
        size_guard,
    )
    service_call = controller_source.index("accountService.findAll(pageable)", offset_guard)
    assert page_request < size_guard < offset_guard < service_call
    assert '"size must not exceed " + MAX_PAGE_SIZE' in controller_source
    assert '"page offset must not exceed " + MAX_PAGE_OFFSET' in controller_source

    assert "import org.springframework.data.domain.Page;" in service_source
    assert "import org.springframework.data.domain.Pageable;" in service_source
    assert "public Page<ListAccountsResponse> findAll(Pageable pageable)" in service_source
    assert "return accountRepository.findAll(pageable).map(record -> {" in service_source
    assert "listAccountsResponse.setAccountId(record.getAccountId());" in service_source
    assert "listAccountsResponse.setAccountName(record.getAccountName());" in service_source
    assert "private String accountId;" not in request_source


def test_non_pageable_operation_is_unchanged(tmp_path: Path) -> None:
    metadata = _pageable_list_metadata(pageable=False)

    output_dir = tmp_path / "NonPageableListApp"
    generate_application(metadata, output_dir, generation_run_id="non-pageable-list-test")

    controller_source = (
        output_dir / "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountController.java"
    ).read_text(encoding="utf-8")
    service_source = (
        output_dir / "src/main/java/com/appbuilder/accounts/service/AccountServiceBase.java"
    ).read_text(encoding="utf-8")
    request_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/ListAccountsRequest.java"
    ).read_text(encoding="utf-8")

    assert "public ResponseEntity<List<ListAccountsResponse>> listAll()" in controller_source
    assert "return ResponseEntity.ok(accountService.findAll());" in controller_source
    assert "public List<ListAccountsResponse> findAll()" in service_source
    assert "List<Account> records = accountRepository.findAll();" in service_source
    assert "List<ListAccountsResponse> responses = new java.util.ArrayList<>();" in service_source
    assert "listAccountsResponse.setAccountId(record.getAccountId());" in service_source
    assert "listAccountsResponse.setAccountName(record.getAccountName());" in service_source
    find_all_body = service_source.split("public List<ListAccountsResponse> findAll", 1)[1].split(
        "public AccountResponse update", 1
    )[0]
    assert "accountRepository.findById" not in find_all_body
    assert "private String accountId;" not in request_source
    assert "org.springframework.data.domain.Page" not in controller_source
    assert "org.springframework.data.domain.PageRequest" not in controller_source
    assert "org.springframework.data.domain.Pageable" not in controller_source
    assert "org.springframework.data.domain.Page" not in service_source
    assert "org.springframework.data.domain.Pageable" not in service_source
    assert "MAX_PAGE_SIZE" not in controller_source
    assert "MAX_PAGE_OFFSET" not in controller_source
    assert "pageable.getOffset()" not in controller_source


def test_update_operation_uses_request_and_response_dtos(tmp_path: Path) -> None:
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
            CanonicalField(name="email", type=CanonicalFieldType.STRING, required=False),
        ],
    )
    update_op = CanonicalOperation(
        name="updateCustomer",
        interface_name="crm-api",
        request_entity="Customer",
        response_entity="Customer",
        http_method=HttpMethod.PUT,
        path="/customers/{customerId}",
        path_parameters=[PathParameter(name="customerId", type="String")],
        response_shape=ResponseShape.SINGLE,
    )
    metadata = MetadataProject(
        app_name="Customer DTO Update",
        bounded_context="crm",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[ContractMetadata(name="crm-api", type="rest-json", source="")],
        operations=[update_op],
        entities=[customer],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-api",
                operation_name="updateCustomer",
                source_path="crm-api.updateCustomer.request.email",
                target_path="Customer.email",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-api",
                operation_name="updateCustomer",
                source_path="crm-api.updateCustomer.response.customerId",
                target_path="Customer.customerId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-api",
                operation_name="updateCustomer",
                source_path="crm-api.updateCustomer.response.email",
                target_path="Customer.email",
            ),
        ],
    )

    output_dir = tmp_path / "CustomerDtoUpdate"
    generate_application(metadata, output_dir, generation_run_id="dto-update-test")

    controller_source = (
        output_dir / "src/main/java/com/appbuilder/crm/adapter/inbound/CustomerController.java"
    ).read_text(encoding="utf-8")
    service_source = (
        output_dir / "src/main/java/com/appbuilder/crm/service/CustomerServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "@PutMapping" in controller_source
    assert "public ResponseEntity<UpdateCustomerResponse> updateCustomer(" in controller_source
    assert "@Valid @RequestBody UpdateCustomerRequest request" in controller_source
    assert "ResponseEntity<Customer> updateCustomer" not in controller_source
    assert "customerService.updateCustomer(id, request)" in controller_source

    assert "public UpdateCustomerResponse updateCustomer(String id, UpdateCustomerRequest request)" in service_source
    assert "Customer customer = customerRepository.findById(id)" in service_source
    assert "customer.setEmail(request.getEmail());" in service_source
    assert "Customer saved = customerRepository.save(customer);" in service_source
    assert "UpdateCustomerResponse updateCustomerResponse = new UpdateCustomerResponse();" in service_source
    assert "updateCustomerResponse.setCustomerId(saved.getCustomerId());" in service_source
    assert "updateCustomerResponse.setEmail(saved.getEmail());" in service_source
    assert "return updateCustomerResponse;" in service_source


def test_single_read_operation_uses_response_dto(tmp_path: Path) -> None:
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    get_op = CanonicalOperation(
        name="getCustomer",
        interface_name="crm-api",
        request_entity="Customer",
        response_entity="Customer",
        http_method=HttpMethod.GET,
        path="/customers/{customerId}",
        path_parameters=[PathParameter(name="customerId", type="String")],
        response_shape=ResponseShape.SINGLE,
    )
    metadata = MetadataProject(
        app_name="Customer DTO Read",
        bounded_context="crm",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[ContractMetadata(name="crm-api", type="rest-json", source="")],
        operations=[get_op],
        entities=[customer],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-api",
                operation_name="getCustomer",
                source_path="crm-api.getCustomer.response.customerId",
                target_path="Customer.customerId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-api",
                operation_name="getCustomer",
                source_path="crm-api.getCustomer.response.customerName",
                target_path="Customer.customerName",
            ),
        ],
    )

    output_dir = tmp_path / "CustomerDtoRead"
    generate_application(metadata, output_dir, generation_run_id="dto-read-test")

    controller_source = (
        output_dir / "src/main/java/com/appbuilder/crm/adapter/inbound/CustomerController.java"
    ).read_text(encoding="utf-8")
    service_source = (
        output_dir / "src/main/java/com/appbuilder/crm/service/CustomerServiceBase.java"
    ).read_text(encoding="utf-8")
    request_source = (
        output_dir / "src/main/java/com/appbuilder/crm/adapter/inbound/GetCustomerRequest.java"
    ).read_text(encoding="utf-8")

    assert "public ResponseEntity<GetCustomerResponse> getCustomer(" in controller_source
    assert "ResponseEntity<Customer>" not in controller_source
    assert "customerService.getCustomer(customerId)" in controller_source
    assert "public GetCustomerResponse getCustomer(String customerId)" in service_source
    assert "customerRepository.findById(customerId)" in service_source
    assert "getCustomerResponse.setCustomerId(customer.getCustomerId());" in service_source
    assert "getCustomerResponse.setCustomerName(customer.getCustomerName());" in service_source
    assert "private String customerId;" not in request_source


def test_controller_preserves_single_param_spec_route_path() -> None:
    entity = CanonicalEntity(
        name="InternationalPayment",
        fields=[
            CanonicalField(
                name="internationalPaymentId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["obie.GetInternationalPaymentsInternationalPaymentId.response.InternationalPaymentId"],
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=False,
                source_paths=["obie.GetInternationalPaymentsInternationalPaymentId.response.Status"],
            ),
        ],
    )
    operation = CanonicalOperation(
        name="GetInternationalPaymentsInternationalPaymentId",
        interface_name="obie-payment-initiation-api",
        request_entity="InternationalPayment",
        response_entity="InternationalPayment",
        http_method=HttpMethod.GET,
        path="/international-payments/{InternationalPaymentId}",
        path_parameters=[PathParameter(name="InternationalPaymentId", type="String")],
        response_shape=ResponseShape.SINGLE,
    )

    controller = _render_controller(
        entity=entity,
        root_package="com.appbuilder.wire_transfer",
        op_contexts=[
            {
                "operation_name": operation.name,
                "java_operation_name": "getInternationalPaymentsInternationalPaymentId",
                "request_class_name": "GetInternationalPaymentsInternationalPaymentIdRequest",
                "response_class_name": "GetInternationalPaymentsInternationalPaymentIdResponse",
                "path": "/international_payments",
                "spec_path": operation.path,
                "request_field_mappings": [],
                "response_field_mappings": [],
                "http_method": operation.http_method,
                "response_shape": operation.response_shape,
                "path_parameters": list(operation.path_parameters),
                "operation_parameters": [],
            }
        ],
        entity_path_base="/international_payments",
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="route-contract-test",
    )

    assert '@RequestMapping("/international-payments")' in controller
    assert '@GetMapping("/{InternationalPaymentId}")' in controller
    assert '@GetMapping("/{id}")' not in controller
    assert '@PathVariable("InternationalPaymentId") String internationalPaymentId' in controller


def _build_a3_test_metadata() -> tuple[MetadataProject, CanonicalEntity]:
    entity = CanonicalEntity(
        name="Earmark",
        fields=[
            CanonicalField(
                name="earmarkId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["fixture.releaseEarmark.response.earmarkId"],
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=False,
                source_paths=["fixture.releaseEarmark.request.status"],
            ),
            CanonicalField(
                name="balance",
                type=CanonicalFieldType.DECIMAL,
                required=False,
                source_paths=["fixture.balance.response.balance"],
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="SyntheticRegistry",
        bounded_context="earmarks",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="SyntheticRegistry", role="upstream")],
        contracts=[ContractMetadata(name="fixture-api", type="rest-json", source="")],
        entities=[entity],
        mappings=[],
        operations=[],
        rules=[],
    )
    return metadata, entity


def _a3_create_ctx() -> dict:
    return {
        "operation_name": "createEarmark",
        "java_operation_name": "createEarmark",
        "request_class_name": "CreateEarmarkRequest",
        "response_class_name": "CreateEarmarkResponse",
        "path": "/earmarks",
        "spec_path": None,
        "request_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="createEarmark",
                source_path="fixture-api.createEarmark.request.status",
                target_path="Earmark.status",
            ),
        ],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="createEarmark",
                source_path="fixture-api.createEarmark.response.earmarkId",
                target_path="Earmark.earmarkId",
            ),
        ],
        "http_method": HttpMethod.POST,
        "response_shape": ResponseShape.CREATED,
        "path_parameters": [],
        "operation_parameters": [],
    }


def test_state_transition_operation_generates_load_then_mutate_controller_and_service() -> None:
    metadata, entity = _build_a3_test_metadata()
    ctx = {
        "operation_name": "releaseEarmark",
        "java_operation_name": "releaseEarmark",
        "request_class_name": "ReleaseEarmarkRequest",
        "response_class_name": "ReleaseEarmarkResponse",
        "path": "/earmarks/release_earmark",
        "spec_path": None,
        "request_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="releaseEarmark",
                source_path="fixture-api.releaseEarmark.request.status",
                target_path="Earmark.status",
            ),
        ],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="releaseEarmark",
                source_path="fixture-api.releaseEarmark.response.status",
                target_path="Earmark.status",
            ),
        ],
        "http_method": HttpMethod.POST,
        "response_shape": ResponseShape.SINGLE,
        "path_parameters": [PathParameter(name="earmarkId", type="String")],
        "operation_parameters": [],
    }

    controller = _render_controller(
        entity=entity,
        root_package="com.appbuilder.fixture",
        op_contexts=[_a3_create_ctx(), ctx],
        entity_path_base="/earmarks",
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="a3-state-transition",
    )
    service = _render_service(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.fixture",
        op_contexts=[_a3_create_ctx(), ctx],
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="a3-state-transition",
    )

    assert '@PostMapping("/{id}/releaseEarmark")' in controller
    assert "releaseEarmark(id, request)" in controller
    assert "earmarkRepository.findById(id)" in service
    assert "earmark.setStatus(request.getStatus());" in service
    assert "earmarkRepository.save(earmark)" in service


def test_path_filtered_list_is_refused_in_mixed_controller() -> None:
    metadata, entity = _build_a3_test_metadata()
    read_ctx = {
        "operation_name": "transactionHistory",
        "java_operation_name": "transactionHistory",
        "request_class_name": "TransactionHistoryRequest",
        "response_class_name": "TransactionHistoryResponse",
        "path": "/accounts/{accountId}/transactions",
        "spec_path": "/accounts/{accountId}/transactions",
        "request_field_mappings": [],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="transactionHistory",
                source_path="fixture-api.transactionHistory.response.status",
                target_path="Earmark.status",
            ),
        ],
        "http_method": HttpMethod.GET,
        "response_shape": ResponseShape.LIST,
        "path_parameters": [PathParameter(name="accountId", type="String")],
        "operation_parameters": [],
    }
    transition_ctx = {
        "operation_name": "releaseEarmark",
        "java_operation_name": "releaseEarmark",
        "request_class_name": "ReleaseEarmarkRequest",
        "response_class_name": "ReleaseEarmarkResponse",
        "path": "/earmarks/release_earmark",
        "spec_path": None,
        "request_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="releaseEarmark",
                source_path="fixture-api.releaseEarmark.request.status",
                target_path="Earmark.status",
            ),
        ],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="releaseEarmark",
                source_path="fixture-api.releaseEarmark.response.status",
                target_path="Earmark.status",
            ),
        ],
        "http_method": HttpMethod.POST,
        "response_shape": ResponseShape.SINGLE,
        "path_parameters": [PathParameter(name="earmarkId", type="String")],
        "operation_parameters": [],
    }

    with pytest.raises(ValueError, match="collection selection inputs"):
        _render_controller(
            entity=entity,
            root_package="com.appbuilder.fixture",
            op_contexts=[read_ctx, transition_ctx],
            entity_path_base="/earmarks",
            id_java_type="String",
            target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
            source_manifest="test",
            generation_run_id="mixed-path-list-route-root-test",
        )


def test_read_list_operation_refuses_ignored_path_selector() -> None:
    metadata, entity = _build_a3_test_metadata()
    ctx = {
        "operation_name": "transactionHistory",
        "java_operation_name": "transactionHistory",
        "request_class_name": "TransactionHistoryRequest",
        "response_class_name": "TransactionHistoryResponse",
        "path": "/earmarks/transaction_history",
        "spec_path": None,
        "request_field_mappings": [],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="transactionHistory",
                source_path="fixture-api.transactionHistory.response.status",
                target_path="Earmark.status",
            ),
        ],
        "http_method": HttpMethod.GET,
        "response_shape": ResponseShape.LIST,
        "path_parameters": [PathParameter(name="earmarkId", type="String")],
        "operation_parameters": [],
    }

    with pytest.raises(ValueError, match="collection selection inputs"):
        _render_service(
            metadata=metadata, entity=entity, root_package="com.appbuilder.fixture",
            op_contexts=[_a3_create_ctx(), ctx], id_java_type="String",
            target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
            source_manifest="test", generation_run_id="a3-read-list",
        )


def test_pageable_read_list_emits_isolated_guards_and_single_constants() -> None:
    _, entity = _build_a3_test_metadata()
    list_ctx = {
        "operation_name": "listEarmarks",
        "java_operation_name": "listEarmarks",
        "request_class_name": "ListEarmarksRequest",
        "response_class_name": "ListEarmarksResponse",
        "path": "/earmarks",
        "spec_path": None,
        "request_field_mappings": [],
        "response_field_mappings": [],
        "http_method": HttpMethod.GET,
        "response_shape": ResponseShape.LIST,
        "path_parameters": [],
        "operation_parameters": [],
        "pageable": True,
    }
    read_list_ctx = {
        "operation_name": "transactionHistory",
        "java_operation_name": "transactionHistory",
        "request_class_name": "TransactionHistoryRequest",
        "response_class_name": "TransactionHistoryResponse",
        "path": "/earmarks/transaction_history",
        "spec_path": None,
        "request_field_mappings": [],
        "response_field_mappings": [],
        "http_method": HttpMethod.GET,
        "response_shape": ResponseShape.LIST,
        "path_parameters": [],
        "operation_parameters": [],
        "pageable": True,
    }

    controller = _render_controller(
        entity=entity,
        root_package="com.appbuilder.fixture",
        op_contexts=[_a3_create_ctx(), list_ctx, read_list_ctx],
        entity_path_base="/earmarks",
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="a3-pageable-read-list",
    )

    assert controller.count("private static final int MAX_PAGE_SIZE = 200;") == 1
    assert controller.count("private static final long MAX_PAGE_OFFSET = 50_000L;") == 1
    assert controller.count("Pageable pageable = PageRequest.of(page, size);") == 2
    assert controller.count("if (size > MAX_PAGE_SIZE)") == 2
    assert controller.count("if (pageable.getOffset() > MAX_PAGE_OFFSET)") == 2
    read_list_method = controller.split(
        "public ResponseEntity<Page<TransactionHistoryResponse>> transactionHistory", 1
    )[1]
    page_request = read_list_method.index("Pageable pageable = PageRequest.of(page, size);")
    size_guard = read_list_method.index("if (size > MAX_PAGE_SIZE)", page_request)
    offset_guard = read_list_method.index(
        "if (pageable.getOffset() > MAX_PAGE_OFFSET)", size_guard
    )
    service_call = read_list_method.index("earmarkService.transactionHistory(", offset_guard)
    assert page_request < size_guard < offset_guard < service_call


def test_computed_read_operation_generates_get_controller_and_find_by_id_service() -> None:
    metadata, entity = _build_a3_test_metadata()
    ctx = {
        "operation_name": "balance",
        "java_operation_name": "balance",
        "request_class_name": "BalanceRequest",
        "response_class_name": "BalanceResponse",
        "path": "/earmarks/balance",
        "spec_path": None,
        "request_field_mappings": [],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="balance",
                source_path="fixture-api.balance.response.balance",
                target_path="Earmark.balance",
            ),
        ],
        "http_method": HttpMethod.GET,
        "response_shape": ResponseShape.SINGLE,
        "path_parameters": [PathParameter(name="earmarkId", type="String")],
        "operation_parameters": [],
    }

    controller = _render_controller(
        entity=entity,
        root_package="com.appbuilder.fixture",
        op_contexts=[_a3_create_ctx(), ctx],
        entity_path_base="/earmarks",
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="a3-computed-read",
    )
    service = _render_service(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.fixture",
        op_contexts=[_a3_create_ctx(), ctx],
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="a3-computed-read",
    )

    assert '@GetMapping("/{id}/balance")' in controller
    assert "ResponseEntity<BalanceResponse> balance(" in controller
    assert "earmarkRepository.findById(id)" in service
    assert "balanceResponse.setBalance(earmark.getBalance());" in service
    assert "earmarkRepository.save(" not in service.split("public BalanceResponse balance", 1)[1]


def test_computed_read_without_path_param_refuses_placeholder_lookup() -> None:
    metadata, entity = _build_a3_test_metadata()
    ctx = {
        "operation_name": "portfolioBalance",
        "java_operation_name": "portfolioBalance",
        "request_class_name": "PortfolioBalanceRequest",
        "response_class_name": "BalanceResponse",
        "path": "/earmarks/balance",
        "spec_path": None,
        "request_field_mappings": [],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="fixture-api",
                operation_name="portfolioBalance",
                source_path="fixture-api.portfolioBalance.response.balance",
                target_path="Earmark.balance",
            ),
        ],
        "http_method": HttpMethod.GET,
        "response_shape": ResponseShape.SINGLE,
        "path_parameters": [],
        "operation_parameters": [],
    }

    with pytest.raises(ValueError, match="portfolioBalance.*Earmark.*path-parameter ID lookup"):
        _render_service(
            metadata=metadata,
            entity=entity,
            root_package="com.appbuilder.fixture",
            op_contexts=[_a3_create_ctx(), ctx],
            id_java_type="String",
            target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
            source_manifest="test",
            generation_run_id="a3-computed-read-no-id",
        )


_COMPUTED_READ_PROFILES = (
    "springboot-legacy-compatible",
    "springboot-enterprise-postgres-java17",
    "springboot-standard-enterprise",
)


def _computed_read_metadata(*, supported: bool, profile: str) -> MetadataProject:
    metadata, _ = _build_a3_test_metadata()
    metadata.target_profile = profile
    metadata.operations = [CanonicalOperation(
        name="portfolioBalance",
        interface_name="fixture-api",
        request_entity="Earmark",
        response_entity="Earmark",
        http_method=HttpMethod.GET,
        response_shape=ResponseShape.SINGLE,
        path="/earmarks/{earmarkId}/balance" if supported else "/earmarks/balance",
        path_parameters=[PathParameter(name="earmarkId", type="String")] if supported else [],
    )]
    metadata.mappings = [FieldMapping(
        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
        contract_name="fixture-api",
        operation_name="portfolioBalance",
        source_path="fixture-api.portfolioBalance.response.balance",
        target_path="Earmark.balance",
    )]
    return metadata


@pytest.mark.parametrize("profile", _COMPUTED_READ_PROFILES)
@pytest.mark.parametrize("lookup", [
    "owner", "nested", "alias", "wrong-type", "undeclared-id", "multiple-ids",
    "wrong-placeholder", "query-filter", "header-filter",
])
def test_computed_read_refuses_unbound_or_ambiguous_lookup_before_output(
    tmp_path: Path, profile: str, lookup: str,
) -> None:
    metadata = _computed_read_metadata(supported=True, profile=profile)
    operation = metadata.operations[0]
    if lookup == "owner":
        operation.path = "/owners/{ownerId}/earmarks/balance"
        operation.path_parameters = [PathParameter(name="ownerId", type="String")]
    elif lookup == "nested":
        operation.path = "/earmarks/{earmarkId}/entries/{entryId}/balance"
        operation.path_parameters.append(PathParameter(name="entryId", type="String"))
    elif lookup == "alias":
        operation.path = "/earmarks/{id}/balance"
        operation.path_parameters = [PathParameter(name="id", type="String")]
    elif lookup == "wrong-type":
        operation.path_parameters[0].type = "Long"
    elif lookup == "undeclared-id":
        metadata.entities[0].fields[0].is_id = False
    elif lookup == "multiple-ids":
        metadata.entities[0].fields[1].is_id = True
    elif lookup == "wrong-placeholder":
        operation.path = "/earmarks/{ownerId}/balance"
    else:
        operation.operation_parameters = [OperationParameter(
            name="ownerId", location=OperationParameterLocation(lookup.split("-")[0]),
            required=True,
        )]
    output = tmp_path / "not-created" / "application"

    with pytest.raises(ValueError, match="portfolioBalance.*fixture-api.*Earmark.*path-parameter ID lookup"):
        generate_application(metadata, output, generation_run_id="xr1-unbound")

    assert not output.parent.exists()


@pytest.mark.parametrize("id_name,id_type,parameter_type", [
    ("id", CanonicalFieldType.STRING, "String"),
    ("lookupKey", CanonicalFieldType.INTEGER, "Long"),
])
def test_computed_read_uses_explicit_identifier_not_entity_name_inference(
    tmp_path: Path, id_name: str, id_type: CanonicalFieldType, parameter_type: str,
) -> None:
    metadata = _computed_read_metadata(supported=True, profile="springboot-legacy-compatible")
    metadata.entities[0].fields[0].name = id_name
    metadata.entities[0].fields[0].type = id_type
    metadata.operations[0].path = f"/earmarks/{{{id_name}}}/balance"
    metadata.operations[0].path_parameters = [PathParameter(name=id_name, type=parameter_type)]
    output = tmp_path / "application"

    report = generate_application(metadata, output, generation_run_id="xr1-explicit-id")

    assert report.harness_report is not None and report.harness_report.passed
    service = next(output.rglob("EarmarkServiceBase.java")).read_text(encoding="utf-8")
    assert f"earmarkRepository.findById({id_name})" in service


@pytest.mark.parametrize("profile", _COMPUTED_READ_PROFILES)
@pytest.mark.parametrize("parameter_location", [None, *OperationParameterLocation])
def test_unsupported_computed_read_refuses_before_creating_application(
    tmp_path: Path, profile: str, parameter_location: OperationParameterLocation | None,
) -> None:
    metadata = _computed_read_metadata(supported=False, profile=profile)
    if parameter_location is not None:
        metadata.operations[0].operation_parameters = [OperationParameter(
            name="account", location=parameter_location, required=True,
        )]
    output = tmp_path / "not-yet-created" / "application"

    with pytest.raises(ValueError, match="portfolioBalance.*fixture-api.*Earmark.*path-parameter ID lookup"):
        generate_application(metadata, output, generation_run_id="xr1-refusal")

    assert not output.parent.exists()


@pytest.mark.parametrize("existing_output", ["user-files", "generated"])
@pytest.mark.parametrize("profile", _COMPUTED_READ_PROFILES)
def test_unsupported_computed_read_preserves_existing_output(
    tmp_path: Path, profile: str, existing_output: str,
) -> None:
    output = tmp_path / "application"
    output.mkdir()
    if existing_output == "generated":
        report = generate_application(
            _computed_read_metadata(supported=True, profile=profile),
            output, generation_run_id="xr1-supported",
        )
        assert report.harness_report is not None and report.harness_report.passed
        service = next(output.rglob("EarmarkServiceBase.java")).read_text(encoding="utf-8")
        assert "earmarkRepository.findById(earmarkId)" in service
        assert "findFirst()" not in service
    (output / "developer-owned.txt").write_text("keep this exact content\n", encoding="utf-8")
    before = {
        path.relative_to(output): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in output.rglob("*") if path.is_file()
    }
    before_directories = {path.relative_to(output) for path in output.rglob("*") if path.is_dir()}

    with pytest.raises(ValueError, match="portfolioBalance.*path-parameter ID lookup"):
        generate_application(
            _computed_read_metadata(supported=False, profile=profile),
            output, generation_run_id="xr1-refusal",
        )

    assert {
        path.relative_to(output): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in output.rglob("*") if path.is_file()
    } == before
    assert {path.relative_to(output) for path in output.rglob("*") if path.is_dir()} == before_directories


def test_direct_java_emission_preflights_all_computed_reads_before_writing(tmp_path: Path) -> None:
    metadata = _computed_read_metadata(supported=False, profile="springboot-legacy-compatible")
    # An earlier, supported entity must not be emitted before a later refusal.
    metadata.entities.insert(0, CanonicalEntity(name="Widget", fields=[
        CanonicalField(name="id", type=CanonicalFieldType.STRING, is_id=True),
    ]))
    metadata.operations.insert(0, CanonicalOperation(
        name="createWidget", interface_name="fixture-api", request_entity="Widget",
        response_entity="Widget", http_method=HttpMethod.POST,
        response_shape=ResponseShape.CREATED,
    ))
    metadata.mappings.append(FieldMapping(
        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
        contract_name="fixture-api", operation_name="createWidget",
        source_path="fixture-api.createWidget.request.id", target_path="Widget.id",
    ))
    output = tmp_path / "application"

    with pytest.raises(ValueError, match="portfolioBalance.*path-parameter ID lookup"):
        emit_java_sources(
            metadata=metadata, target_profile=TARGET_PROFILES[metadata.target_profile],
            output_dir=output, source_manifest="xr1", generation_run_id="xr1-refusal",
        )

    assert not output.exists()


@pytest.mark.parametrize("profile", _COMPUTED_READ_PROFILES)
@pytest.mark.parametrize("additive_field", [False, True])
@pytest.mark.parametrize("read_only", [False, True])
def test_unsupported_computed_read_apply_preserves_package_before_rollback(
    tmp_path: Path, profile: str, additive_field: bool, read_only: bool,
) -> None:
    metadata = _computed_read_metadata(supported=True, profile=profile)
    output = tmp_path / "application"
    generate_application(metadata, output, generation_run_id="xr1-supported")
    sentinel = output / ".aaa-developer-owned.txt"
    sentinel.write_text("preserve developer content\n", encoding="utf-8")
    if read_only:
        sentinel.chmod(0o444)
    before = {
        path.relative_to(output): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in output.rglob("*") if path.is_file()
    }
    before_directories = {path.relative_to(output) for path in output.rglob("*") if path.is_dir()}
    if additive_field:
        metadata.entities[0].fields.append(CanonicalField(name="note", type=CanonicalFieldType.STRING))
    plan = build_change_plan(metadata=metadata, package_dir=output)
    assert bool(plan["db_migration_deltas"]) == additive_field
    assert all(delta["classification"] == "additive" for delta in plan["db_migration_deltas"])
    # A previously approved plan cannot bypass apply's independent preflight.
    metadata.operations[0].path_parameters = []
    metadata.operations[0].path = "/earmarks/balance"

    try:
        with pytest.raises(ValueError, match="portfolioBalance.*path-parameter ID lookup"):
            apply_change_plan(
                metadata=metadata, package_dir=output,
                approved_plan_hash=plan["plan_hash"], generation_run_id="xr1-refusal",
            )
        assert {
            path.relative_to(output): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
            for path in output.rglob("*") if path.is_file()
        } == before
        assert {path.relative_to(output) for path in output.rglob("*") if path.is_dir()} == before_directories
    finally:
        sentinel.chmod(0o644)


@pytest.mark.parametrize("profile", _COMPUTED_READ_PROFILES)
def test_supported_computed_read_apply_preserves_read_only_developer_file(
    tmp_path: Path, profile: str,
) -> None:
    metadata = _computed_read_metadata(supported=True, profile=profile)
    output = tmp_path / "application"
    generate_application(metadata, output, generation_run_id="xr1-supported")
    sentinel = output / ".aaa-developer-owned.txt"
    sentinel.write_text("preserve developer content\n", encoding="utf-8")
    sentinel.chmod(0o444)
    before = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns, sentinel.stat().st_mode)
    metadata.entities[0].fields.append(CanonicalField(name="note", type=CanonicalFieldType.STRING))
    plan = build_change_plan(metadata=metadata, package_dir=output)

    try:
        report = apply_change_plan(
            metadata=metadata, package_dir=output,
            approved_plan_hash=plan["plan_hash"], generation_run_id="xr1-apply-supported",
        )
        assert report.generation_report.harness_report is not None
        assert report.generation_report.harness_report.passed
        assert (sentinel.read_bytes(), sentinel.stat().st_mtime_ns, sentinel.stat().st_mode) == before
        assert [path.name for path in report.migrations_created] == ["V2__alter_earmark_add_note.sql"]
        baseline = json.loads((output / "db/schema-baseline.json").read_text(encoding="utf-8"))
        columns = next(entity["columns"] for entity in baseline["entities"] if entity["entity"] == "Earmark")
        assert any(column["field"] == "note" for column in columns)
        service = next(output.rglob("EarmarkServiceBase.java")).read_text(encoding="utf-8")
        assert "earmarkRepository.findById(earmarkId)" in service
    finally:
        sentinel.chmod(0o644)


def _computed_read_manifest(
    project: Path, *, supported: bool, route: str | None = None,
) -> Path:
    shutil.copytree("examples/input-projects/generated-app-ci-smoke", project)
    manifest_path = project / "app-definition.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    interface = manifest["upstream_interfaces"][0]
    interface["operations"].append({
        "name": "recordSummary",
        "response_sample": "upstream/sample-create-record-response.json",
    })
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    spec_path = project / interface["spec"]
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    route = route or (
        "/api/v1/records/{recordId}/summary" if supported else "/api/v1/records/summary"
    )
    spec["paths"][route] = {"get": {
        "operationId": "recordSummary",
        "parameters": [{"name": name, "in": "path", "required": True,
                        "schema": {"type": "string"}} for name in re.findall(r"\{([^}]+)\}", route)],
        "responses": {"200": {"description": "Record summary", "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/RecordResponse"}},
        }}},
    }}
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    mapping_path = project / interface["mapping"]
    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    mapping["operations"].append({
        "name": "recordSummary", "response_mappings": [
            {"source": name, "target": f"Record.{name}"} for name in ("recordId", "label", "state")
        ],
    })
    mapping_path.write_text(yaml.safe_dump(mapping), encoding="utf-8")
    return manifest_path


def _generic_id_computed_read_manifest(project: Path, *, route: str) -> Path:
    project.mkdir(parents=True)
    fields = ("id", "ownerId", "label")
    (project / "response.json").write_text(json.dumps({
        "id": "RECORD-A", "ownerId": "OWNER-A", "label": "Original record",
    }), encoding="utf-8")
    (project / "mapping.yaml").write_text(yaml.safe_dump({"operations": [{
        "name": "recordSummary", "response_mappings": [
            {"source": name, "target": f"Record.{name}"} for name in fields
        ],
    }]}), encoding="utf-8")
    (project / "openapi.yaml").write_text(yaml.safe_dump({
        "openapi": "3.0.1", "info": {"title": "Record summary", "version": "1.0"},
        "paths": {route: {"get": {
            "operationId": "recordSummary",
            "parameters": [{"name": "id", "in": "path", "required": True,
                            "schema": {"type": "string"}}],
            "responses": {"200": {"description": "Record summary", "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/RecordResponse"}},
            }}},
        }}},
        "components": {"schemas": {"RecordResponse": {
            "type": "object", "required": list(fields),
            "properties": {name: {"type": "string"} for name in fields},
        }}},
    }), encoding="utf-8")
    manifest_path = project / "app-definition.yaml"
    manifest_path.write_text(yaml.safe_dump({
        "schema_version": "2.0", "app_name": "Record Summary", "bounded_context": "records",
        "app_archetype": "crud", "target_profile": "springboot-legacy-compatible",
        "identity_overrides": [{"entity": "Record", "persistence_id": "id"}],
        "upstream_interfaces": [{
            "name": "records-api", "type": "rest-json", "spec": "openapi.yaml",
            "mapping": "mapping.yaml", "operations": [{
                "name": "recordSummary", "response_sample": "response.json",
            }],
        }],
    }), encoding="utf-8")
    return manifest_path


@pytest.mark.parametrize("profile", _COMPUTED_READ_PROFILES)
@pytest.mark.parametrize("route", [
    "/owners/{id}/records/summary",
    "/api/v1/groups/{id}/records/summary",
    "/records/summary/{id}",
    "/archive_records/{id}/summary",
    "/records/{id}/../owners/summary",
    "/records/{id}/%2e%2e/owners/summary",
    "//records/{id}/summary",
    "/records/{id}/summary//",
    "/api/**/records/{id}/summary",
    "/api/*/records/{id}/summary",
    "/api/v*/records/{id}/summary",
    "/records/{id}/summary/*",
    "/records/{id}/**",
    "/records/{id}/summary*",
    "/records/{id}/summary{",
    "/records/{id}/summary}",
    "/api;v=1/records/{id}/summary",
    "/records/{id}/summary;view=full",
    "/records/{id}/summary;/detail",
])
@pytest.mark.parametrize("entry_point", ["service", "java", "absent", "existing", "plan", "apply"])
def test_computed_read_generic_id_resource_binding_refusal_preserves_output(
    tmp_path: Path, profile: str, route: str, entry_point: str,
) -> None:
    manifest = _generic_id_computed_read_manifest(
        tmp_path / "input", route="/api/v1/records/{id}/summary",
    )
    metadata = build_metadata_project(manifest)
    metadata.target_profile = profile
    package = tmp_path / "application"
    generate_application(metadata, package, generation_run_id="xr1-bound-control")
    sentinel = package / ".aaa-developer-owned.txt"
    sentinel.write_text("preserve the original package\n", encoding="utf-8")
    sentinel.chmod(0o444)
    before = {
        path.relative_to(package): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in package.rglob("*") if path.is_file()
    }
    before_directories = {path.relative_to(package) for path in package.rglob("*") if path.is_dir()}
    metadata.entities[0].fields.append(CanonicalField(name="note", type=CanonicalFieldType.STRING))
    plan = build_change_plan(metadata=metadata, package_dir=package)
    assert plan["db_migration_deltas"]
    metadata.operations[0].path = route
    absent = tmp_path / "not-created" / "application"
    try:
        with pytest.raises(ValueError, match="recordSummary.*Record.*path-parameter ID lookup"):
            if entry_point == "service":
                _render_service(
                    metadata=metadata, entity=metadata.entities[0], root_package="com.appbuilder.records",
                    op_contexts=_operation_contexts_for_entity(metadata, metadata.entities[0]),
                    id_java_type="String", target_profile=TARGET_PROFILES[profile],
                    source_manifest="test", generation_run_id="xr1-unbound",
                )
            elif entry_point == "java":
                emit_java_sources(
                    metadata=metadata, target_profile=TARGET_PROFILES[profile], output_dir=package,
                    source_manifest="test", generation_run_id="xr1-unbound",
                )
            elif entry_point in {"absent", "existing"}:
                generate_application(
                    metadata, absent if entry_point == "absent" else package,
                    generation_run_id="xr1-unbound",
                )
            elif entry_point == "plan":
                build_change_plan(metadata=metadata, package_dir=package)
            else:
                apply_change_plan(
                    metadata=metadata, package_dir=package, approved_plan_hash=plan["plan_hash"],
                    generation_run_id="xr1-unbound",
                )
        assert not absent.parent.exists()
        assert {
            path.relative_to(package): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
            for path in package.rglob("*") if path.is_file()
        } == before
        assert {path.relative_to(package) for path in package.rglob("*") if path.is_dir()} == before_directories
    finally:
        sentinel.chmod(0o644)


@pytest.mark.parametrize("command", ["generate", "plan", "apply"])
@pytest.mark.parametrize("route", [
    "/owners/{id}/records/summary",
    "/api/**/records/{id}/summary",
    "/api/*/records/{id}/summary",
    "/records/{id}/summary/*",
    "/records/{id}/**",
    "/records/{id}/summary{",
    "/records/{id}/summary}",
    "/api;v=1/records/{id}/summary",
    "/records/{id}/summary;view=full",
    "/records/{id}/summary;/detail",
])
def test_computed_read_cli_blocks_unsupported_resource_route_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: str,
    route: str,
) -> None:
    from appbuilder.cli import main
    from appbuilder.core.path_safety import ALLOWED_ROOTS_ENV, SHARED_MODE_ENV

    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    supported = _generic_id_computed_read_manifest(
        tmp_path / "supported", route="/records/{id}/summary",
    )
    package = tmp_path / "application"
    assert main(["generate", "--manifest", str(supported), "--output", str(package)]) == 0
    plan = build_change_plan(metadata=build_metadata_project(supported), package_dir=package)
    before = {
        path.relative_to(package): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in package.rglob("*") if path.is_file()
    }
    unsupported = _generic_id_computed_read_manifest(
        tmp_path / "unsupported", route=route,
    )
    output = tmp_path / "not-created" / "result"
    capsys.readouterr()
    args = [command, "--manifest", str(unsupported), "--validate-schema"]
    if command == "generate":
        args.extend(["--output", str(output)])
    elif command == "plan":
        args.extend(["--package", str(package), "--out", str(output)])
    else:
        args.extend(["--package", str(package), "--approved-plan-hash", plan["plan_hash"]])

    assert main(args) == 1
    captured = capsys.readouterr()
    assert "recordSummary" in captured.err and "path-parameter ID lookup" in captured.err
    assert "plan_hash" not in captured.out and "Harness: PASSED" not in captured.out
    assert not output.parent.exists()
    assert {
        path.relative_to(package): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in package.rglob("*") if path.is_file()
    } == before


@pytest.mark.parametrize("supported", [False, True])
def test_computed_read_cli_reports_only_supported_generation_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    supported: bool,
) -> None:
    from appbuilder.cli import main
    from appbuilder.core.path_safety import ALLOWED_ROOTS_ENV, SHARED_MODE_ENV

    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    manifest = _computed_read_manifest(tmp_path / "input", supported=supported)
    output = tmp_path / "application"

    result = main([
        "generate", "--manifest", str(manifest), "--output", str(output),
        "--validate-schema", "--generation-run-id", "xr1-cli",
    ])

    captured = capsys.readouterr()
    if supported:
        assert result == 0, captured.err
        assert "Harness: PASSED" in captured.out
        service = next(output.rglob("RecordServiceBase.java")).read_text(encoding="utf-8")
        assert "recordRepository.findById(recordId)" in service
    else:
        assert result == 1
        assert "recordSummary" in captured.err and "path-parameter ID lookup" in captured.err
        assert "Generated application" not in captured.out and "Harness: PASSED" not in captured.out
        assert not output.exists()


@pytest.mark.parametrize("route", [
    "/api/v1/owners/{ownerId}/records/summary",
    "/api/v1/records/{recordId}/entries/{entryId}/label",
])
def test_computed_read_cli_refuses_owner_and_nested_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    route: str,
) -> None:
    from appbuilder.cli import main
    from appbuilder.core.path_safety import ALLOWED_ROOTS_ENV, SHARED_MODE_ENV

    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    manifest = _computed_read_manifest(tmp_path / "input", supported=True, route=route)
    output = tmp_path / "application"

    assert main([
        "generate", "--manifest", str(manifest), "--output", str(output), "--validate-schema",
    ]) == 1
    captured = capsys.readouterr()
    assert "recordSummary" in captured.err and "path-parameter ID lookup" in captured.err
    assert "Harness: PASSED" not in captured.out
    assert not output.exists()


@pytest.mark.parametrize("route", [
    "/api/v1/records/summary",
    "/api/v1/owners/{ownerId}/records/summary",
    "/api/v1/records/{recordId}/entries/{entryId}/label",
])
def test_computed_read_cli_plan_blocks_unsupported_lookup_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    route: str,
) -> None:
    from appbuilder.cli import main
    from appbuilder.core.path_safety import ALLOWED_ROOTS_ENV, SHARED_MODE_ENV

    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    manifest = _computed_read_manifest(tmp_path / "supported-input", supported=True)
    package = tmp_path / "application"
    assert main(["generate", "--manifest", str(manifest), "--output", str(package)]) == 0
    capsys.readouterr()
    before = {
        path.relative_to(package): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in package.rglob("*") if path.is_file()
    }
    before_directories = {path.relative_to(package) for path in package.rglob("*") if path.is_dir()}
    manifest = _computed_read_manifest(tmp_path / "unsupported-input", supported=True, route=route)
    plan_output = tmp_path / "not-created" / "plan.json"

    assert main([
        "plan", "--manifest", str(manifest), "--package", str(package),
        "--out", str(plan_output), "--validate-schema",
    ]) == 1
    captured = capsys.readouterr()
    assert "recordSummary" in captured.err and "path-parameter ID lookup" in captured.err
    assert "plan_hash" not in captured.out
    assert not plan_output.parent.exists()
    assert {
        path.relative_to(package): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in package.rglob("*") if path.is_file()
    } == before
    assert {path.relative_to(package) for path in package.rglob("*") if path.is_dir()} == before_directories


def test_entities_without_real_create_ops_do_not_emit_generic_create_or_duplicate_methods(
    tmp_path: Path,
) -> None:
    earmark = CanonicalEntity(
        name="Earmark",
        fields=[
            CanonicalField(name="earmarkId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, required=True),
            CanonicalField(name="amount", type=CanonicalFieldType.DECIMAL, required=True),
            CanonicalField(name="status", type=CanonicalFieldType.STRING, required=False),
        ],
    )
    transaction_history = CanonicalEntity(
        name="TransactionHistory",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="currentPage", type=CanonicalFieldType.INTEGER, required=False),
            CanonicalField(name="pageSize", type=CanonicalFieldType.INTEGER, required=False),
        ],
    )
    balance = CanonicalEntity(
        name="Balance",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="accountNumber", type=CanonicalFieldType.STRING, required=False),
            CanonicalField(name="ledgerBalance", type=CanonicalFieldType.DECIMAL, required=False),
        ],
    )

    metadata = MetadataProject(
        app_name="DDA Phase 3",
        bounded_context="ddaphase3",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="DDA", role="upstream")],
        contracts=[
            ContractMetadata(name="dda-earmark-api", type="rest-json", source=""),
            ContractMetadata(name="dda-transactionhistory-api", type="rest-json", source=""),
            ContractMetadata(name="dda-balance-api", type="rest-json", source=""),
        ],
        operations=[
            CanonicalOperation(
                name="createEarmark",
                interface_name="dda-earmark-api",
                request_entity="Earmark",
                response_entity="Earmark",
                http_method=HttpMethod.POST,
                path="/earmarks",
                response_shape=ResponseShape.CREATED,
            ),
            CanonicalOperation(
                name="releaseEarmark",
                interface_name="dda-earmark-api",
                request_entity="Earmark",
                response_entity="Earmark",
                http_method=HttpMethod.POST,
                path="/earmarks/{earmarkId}/release",
                path_parameters=[PathParameter(name="earmarkId", type="String")],
                response_shape=ResponseShape.SINGLE,
            ),
            CanonicalOperation(
                name="getTransactions",
                interface_name="dda-transactionhistory-api",
                request_entity="TransactionHistory",
                response_entity="TransactionHistory",
                http_method=HttpMethod.GET,
                path="/transactions/{accountId}",
                path_parameters=[PathParameter(name="accountId", type="String")],
                response_shape=ResponseShape.SINGLE,
            ),
            CanonicalOperation(
                name="getBalance",
                interface_name="dda-balance-api",
                request_entity="Balance",
                response_entity="Balance",
                http_method=HttpMethod.GET,
                path="/balance/{accountId}",
                path_parameters=[PathParameter(name="accountId", type="String")],
                response_shape=ResponseShape.SINGLE,
            ),
        ],
        entities=[earmark, transaction_history, balance],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-earmark-api",
                operation_name="createEarmark",
                source_path="dda-earmark-api.createEarmark.request.accountId",
                target_path="Earmark.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-earmark-api",
                operation_name="createEarmark",
                source_path="dda-earmark-api.createEarmark.request.amount",
                target_path="Earmark.amount",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-earmark-api",
                operation_name="createEarmark",
                source_path="dda-earmark-api.createEarmark.response.earmarkId",
                target_path="Earmark.earmarkId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-earmark-api",
                operation_name="createEarmark",
                source_path="dda-earmark-api.createEarmark.response.status",
                target_path="Earmark.status",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-earmark-api",
                operation_name="releaseEarmark",
                source_path="dda-earmark-api.releaseEarmark.request.status",
                target_path="Earmark.status",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-earmark-api",
                operation_name="releaseEarmark",
                source_path="dda-earmark-api.releaseEarmark.response.status",
                target_path="Earmark.status",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-transactionhistory-api",
                operation_name="getTransactions",
                source_path="dda-transactionhistory-api.getTransactions.request.accountId",
                target_path="TransactionHistory.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-transactionhistory-api",
                operation_name="getTransactions",
                source_path="dda-transactionhistory-api.getTransactions.response.accountId",
                target_path="TransactionHistory.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-transactionhistory-api",
                operation_name="getTransactions",
                source_path="dda-transactionhistory-api.getTransactions.response.currentPage",
                target_path="TransactionHistory.currentPage",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-transactionhistory-api",
                operation_name="getTransactions",
                source_path="dda-transactionhistory-api.getTransactions.response.pageSize",
                target_path="TransactionHistory.pageSize",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-balance-api",
                operation_name="getBalance",
                source_path="dda-balance-api.getBalance.request.accountId",
                target_path="Balance.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-balance-api",
                operation_name="getBalance",
                source_path="dda-balance-api.getBalance.response.accountId",
                target_path="Balance.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-balance-api",
                operation_name="getBalance",
                source_path="dda-balance-api.getBalance.response.accountNumber",
                target_path="Balance.accountNumber",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="dda-balance-api",
                operation_name="getBalance",
                source_path="dda-balance-api.getBalance.response.ledgerBalance",
                target_path="Balance.ledgerBalance",
            ),
        ],
    )

    output_dir = tmp_path / "Ddaphase3Regression"
    with pytest.raises(ValueError, match="getTransactions.*own resource"):
        generate_application(metadata, output_dir, generation_run_id="a3-unsupported-alias")
    assert not output_dir.exists()
    # Preserve the no-create/read-only regression with an actual own-ID route,
    # not an owner lookup that the generator never implemented.
    metadata.operations[2].path = "/transaction-historys/{accountId}"
    generate_application(metadata, output_dir, generation_run_id="a3-readonly-create-fallback")

    service_dir = output_dir / "src" / "main" / "java" / "com" / "appbuilder" / "ddaphase3" / "service"
    inbound_dir = output_dir / "src" / "main" / "java" / "com" / "appbuilder" / "ddaphase3" / "adapter" / "inbound"
    ui_html = (output_dir / "src" / "main" / "resources" / "static" / "index.html").read_text(
        encoding="utf-8"
    )

    balance_service = (service_dir / "BalanceServiceBase.java").read_text(encoding="utf-8")
    balance_controller = (inbound_dir / "BalanceController.java").read_text(encoding="utf-8")
    transaction_service = (service_dir / "TransactionHistoryServiceBase.java").read_text(encoding="utf-8")
    transaction_controller = (inbound_dir / "TransactionHistoryController.java").read_text(encoding="utf-8")
    earmark_controller = (inbound_dir / "EarmarkController.java").read_text(encoding="utf-8")
    earmark_service = (service_dir / "EarmarkServiceBase.java").read_text(encoding="utf-8")

    assert balance_service.count("public GetBalanceResponse getBalance(") == 1
    assert "public Balance create(" not in balance_service
    assert "public ResponseEntity<Balance> create(" not in balance_controller
    assert "public ResponseEntity<GetBalanceResponse> getBalance(" in balance_controller
    assert "public ResponseEntity<Balance> getById(" not in balance_controller
    assert "@PutMapping" not in balance_controller
    assert "@DeleteMapping" not in balance_controller
    assert "public Balance update(" not in balance_service
    assert "public void delete(" not in balance_service
    assert "public GetBalanceResponse getBalance(String accountId)" in balance_service

    assert transaction_service.count("public GetTransactionsResponse getTransactions(") == 1
    assert "public TransactionHistory create(" not in transaction_service
    assert "public ResponseEntity<TransactionHistory> create(" not in transaction_controller
    assert "public ResponseEntity<GetTransactionsResponse> getTransactions(" in transaction_controller
    assert "public ResponseEntity<TransactionHistory> getById(" not in transaction_controller
    assert "@PutMapping" not in transaction_controller
    assert "@DeleteMapping" not in transaction_controller
    assert "public TransactionHistory update(" not in transaction_service
    assert "public void delete(" not in transaction_service
    assert "public GetTransactionsResponse getTransactions(String accountId" in transaction_service

    assert "public CreateEarmarkResponse createEarmark(" in earmark_service
    assert "public ReleaseEarmarkResponse releaseEarmark(" in earmark_service
    assert "@PutMapping" in earmark_controller
    assert "@DeleteMapping" in earmark_controller

    balance_panel = ui_html.split('id="entity-panel-Balance"', 1)[1].split('id="entity-panel-', 1)[0]
    transaction_panel = ui_html.split('id="entity-panel-TransactionHistory"', 1)[1].split('id="entity-panel-', 1)[0]
    earmark_panel = ui_html.split('id="entity-panel-Earmark"', 1)[1].split('id="entity-panel-', 1)[0]

    assert "Get" in balance_panel
    assert "accountId" in balance_panel
    assert "Enter accountId" in balance_panel
    assert "GET /balance/{accountId}" in balance_panel
    assert 'data-tab="update"' not in balance_panel
    assert 'data-tab="delete"' not in balance_panel

    assert "Get" in transaction_panel
    assert "accountId" in transaction_panel
    assert "Enter accountId" in transaction_panel
    assert 'data-tab="update"' not in transaction_panel
    assert 'data-tab="delete"' not in transaction_panel

    assert "Create" in earmark_panel
    assert "Update" in earmark_panel
    assert "Delete" in earmark_panel


def test_generated_app_quality_fixture_keeps_transaction_identity_and_excludes_wrappers(
    tmp_path: Path,
) -> None:
    manifest_path = (
        "tests/fixtures/generated-app-quality/"
        "transaction-identity-wrapper-valid/app-definition.yaml"
    )
    metadata = build_metadata_project(manifest_path)
    output_dir = tmp_path / "TransactionIdentityWrapper"

    with pytest.raises(ValueError, match="listTransactionsByAccount.*collection selection"):
        generate_application(metadata, output_dir, generation_run_id="unsupported-owner-filter")
    assert not output_dir.exists()
    # Keep the useful identity/wrapper rendering proof on an explicitly
    # unfiltered variant; the original fixture is ingestion-valid, not a
    # supported filtered-query implementation.
    operation = next(op for op in metadata.operations if op.name == "listTransactionsByAccount")
    operation.path = "/transaction-history"
    operation.path_parameters = []
    operation.read_input_errors = []

    generate_application(
        metadata,
        output_dir,
        source_manifest=manifest_path,
        generation_run_id="identity-wrapper-unit",
    )

    entity_source = (
        output_dir
        / "src/main/java/com/appbuilder/bankingquality/domain/TransactionHistory.java"
    ).read_text(encoding="utf-8")
    ddl_source = (
        output_dir
        / "src/main/resources/db/migration/V1__create_transaction_history_table.sql"
    ).read_text(encoding="utf-8")
    writer_source = (
        output_dir
        / "src/main/java/com/appbuilder/bankingquality/adapter/outbound/"
        "TransactionHistoryEodHandoffFileWriter.java"
    ).read_text(encoding="utf-8")
    response_dto_source = (
        output_dir
        / "src/main/java/com/appbuilder/bankingquality/adapter/inbound/"
        "ListTransactionsByAccountResponse.java"
    ).read_text(encoding="utf-8")
    request_dto_source = (
        output_dir
        / "src/main/java/com/appbuilder/bankingquality/adapter/inbound/"
        "ListTransactionsByAccountRequest.java"
    ).read_text(encoding="utf-8")
    service_source = (
        output_dir
        / "src/main/java/com/appbuilder/bankingquality/service/TransactionHistoryServiceBase.java"
    ).read_text(encoding="utf-8")
    controller_source = (
        output_dir
        / "src/main/java/com/appbuilder/bankingquality/adapter/inbound/TransactionHistoryController.java"
    ).read_text(encoding="utf-8")

    transaction_row_section = entity_source.split("private String transactionRowId;", 1)[0]
    account_section = entity_source.split("private String accountId;", 1)[0]
    transaction_id_section = entity_source.split("private String transactionId;", 1)[0]
    assert "@Id" in transaction_row_section
    assert '@Column(name = "transaction_row_id", length = 36, updatable = false)' in transaction_row_section
    assert "@Id" not in account_section.rsplit("/**", 1)[-1]
    assert "@Id" not in transaction_id_section.rsplit("/**", 1)[-1]

    assert "currentPage;" not in entity_source
    assert "pageSize;" not in entity_source
    assert "totalElements;" not in entity_source
    assert "totalPages;" not in entity_source
    assert "private String transactions;" not in entity_source

    assert "transaction_row_id VARCHAR(36) PRIMARY KEY" in ddl_source
    assert "account_id VARCHAR(255) NOT NULL" in ddl_source
    assert "transaction_id VARCHAR(255) NOT NULL" in ddl_source
    assert "current_page" not in ddl_source
    assert "page_size" not in ddl_source
    assert "total_elements" not in ddl_source
    assert "total_pages" not in ddl_source
    assert "transactions" not in ddl_source

    assert "getAccountId()" in writer_source
    assert "getTransactionId()" in writer_source
    assert "getCurrentPage()" not in writer_source
    assert "getTotalElements()" not in writer_source

    assert "private Long currentPage;" in response_dto_source
    assert "private Long pageSize;" in response_dto_source
    assert "private Long totalElements;" in response_dto_source
    assert "private Long totalPages;" in response_dto_source
    assert "private String transactions;" in response_dto_source
    assert "private String transactionRowId;" not in request_dto_source
    assert "getTransactionRowId()" not in request_dto_source
    assert "request.getTransactionRowId()" not in service_source
    assert "public Page<ListTransactionsByAccountResponse> findAll(Pageable pageable)" in service_source
    assert "transactionHistoryRepository.findAll(pageable).map(record -> {" in service_source
    assert '@RequestMapping("/transaction-history")' in controller_source
    assert '@RequestMapping("/accounts")' not in controller_source
    assert "@PostMapping\n" in controller_source
    assert "POST /transaction-history" in controller_source
    assert 'GET /transaction-history' in controller_source
    assert '@PathVariable("accountId") String accountId' not in controller_source
    assert "record.getCurrentPage()" not in service_source
    assert "record.getTotalElements()" not in service_source
    assert "Server-set fields (status, etc.) are initialized via @PrePersist on the entity." not in service_source


def test_metadata_only_identity_roles_do_not_change_generated_output(
    tmp_path: Path,
) -> None:
    source_fixture = Path("tests/fixtures/generated-app-quality/crud-dto-list-contract")
    role_fixture = tmp_path / "crud-dto-list-contract-with-identity-roles"
    shutil.copytree(source_fixture, role_fixture)
    role_manifest = role_fixture / "app-definition.yaml"
    payload = yaml.safe_load(role_manifest.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload["identity_roles"] = [
        {
            "entity": "Customer",
            "field": "customerId",
            "role": "business_key",
            "mode": "metadata_only",
        },
        {
            "entity": "Customer",
            "field": "email",
            "role": "external_reference",
            "mode": "metadata_only",
            "policy": {"generate_finder": True},
        },
    ]
    role_manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    baseline = build_metadata_project(source_fixture / "app-definition.yaml")
    with_roles = build_metadata_project(role_manifest)
    assert [role.role.value for role in with_roles.identity_roles] == [
        "business_key",
        "external_reference",
    ]

    baseline_output = tmp_path / "baseline"
    role_output = tmp_path / "with_roles"
    baseline_report = generate_application(
        baseline,
        baseline_output,
        source_manifest="role-contract-test",
        generation_run_id="role-contract-test",
    )
    role_report = generate_application(
        with_roles,
        role_output,
        source_manifest="role-contract-test",
        generation_run_id="role-contract-test",
    )

    assert {
        path.relative_to(baseline_report.output_dir).as_posix()
        for path in baseline_report.files_created
    } == {
        path.relative_to(role_report.output_dir).as_posix()
        for path in role_report.files_created
    }

    source_files = [
        "src/main/java/com/appbuilder/crmdto/domain/Customer.java",
        "src/main/java/com/appbuilder/crmdto/repository/CustomerRepository.java",
        "src/main/java/com/appbuilder/crmdto/service/CustomerServiceBase.java",
        "src/main/java/com/appbuilder/crmdto/adapter/inbound/CustomerController.java",
        "src/main/resources/db/migration/V1__create_customer_table.sql",
    ]
    for relative in source_files:
        baseline_source = (baseline_output / relative).read_text(encoding="utf-8")
        role_source = (role_output / relative).read_text(encoding="utf-8")
        assert baseline_source == role_source
        assert "identity" not in role_source.lower()
        assert "idempotency" not in role_source.lower()
        assert "unique" not in role_source.lower()
        assert "findByEmail" not in role_source


def test_metadata_only_identity_roles_reject_unknown_entity(tmp_path: Path) -> None:
    source_fixture = Path("tests/fixtures/generated-app-quality/crud-dto-list-contract")
    role_fixture = tmp_path / "crud-dto-list-contract-unknown-entity"
    shutil.copytree(source_fixture, role_fixture)
    role_manifest = role_fixture / "app-definition.yaml"
    payload = yaml.safe_load(role_manifest.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload["identity_roles"] = [
        {
            "entity": "MissingEntity",
            "field": "customerId",
            "role": "business_key",
            "mode": "metadata_only",
        }
    ]
    role_manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="identity_roles.*unknown entity.*MissingEntity"):
        build_metadata_project(role_manifest)


def test_metadata_only_identity_roles_reject_unknown_field(tmp_path: Path) -> None:
    source_fixture = Path("tests/fixtures/generated-app-quality/crud-dto-list-contract")
    role_fixture = tmp_path / "crud-dto-list-contract-unknown-field"
    shutil.copytree(source_fixture, role_fixture)
    role_manifest = role_fixture / "app-definition.yaml"
    payload = yaml.safe_load(role_manifest.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload["identity_roles"] = [
        {
            "entity": "Customer",
            "field": "missingField",
            "role": "business_key",
            "mode": "metadata_only",
        }
    ]
    role_manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="identity_roles.*unknown field.*Customer.missingField"):
        build_metadata_project(role_manifest)


def test_generated_app_quality_minor_units_and_date_fixture_outputs_expected_sources(
    tmp_path: Path,
) -> None:
    manifest_path = "tests/fixtures/generated-app-quality/crud-minor-units-date/app-definition.yaml"
    metadata = build_metadata_project(manifest_path)
    account_entity = next(entity for entity in metadata.entities if entity.name == "Account")
    account_field_names = {field.name for field in account_entity.fields}
    assert "stagingRowId" not in account_field_names
    assert "runId" not in account_field_names
    assert "businessDate" not in account_field_names
    assert "stagingStatus" not in account_field_names
    assert "createdAt" not in account_field_names

    output_dir = tmp_path / "CrudMinorUnitsDate"

    generate_application(
        metadata,
        output_dir,
        source_manifest=manifest_path,
        generation_run_id="minor-units-date-unit",
    )

    base = output_dir / "src/main/java/com/appbuilder/minorunitsdate"
    entity_source = (base / "domain/Account.java").read_text(encoding="utf-8")
    request_dto_source = (
        base / "adapter/inbound/CreateAccountRequest.java"
    ).read_text(encoding="utf-8")
    response_dto_source = (
        base / "adapter/inbound/CreateAccountResponse.java"
    ).read_text(encoding="utf-8")
    file_writer_source = (
        base / "adapter/outbound/AccountEodHandoffFileWriter.java"
    ).read_text(encoding="utf-8")
    staging_writer_source = (
        base / "adapter/outbound/AccountStagingWriter.java"
    ).read_text(encoding="utf-8")
    batch_job_source = (base / "batch/AccountEodBatchJob.java").read_text(
        encoding="utf-8"
    )
    ddl_source = (
        output_dir / "src/main/resources/db/migration/V1__create_account_table.sql"
    ).read_text(encoding="utf-8")
    staging_ddl_source = (
        output_dir / "src/main/resources/db/migration/V2__create_account_staging_tbl_table.sql"
    ).read_text(encoding="utf-8")
    application_yaml = (
        output_dir / "src/main/resources/application.yaml"
    ).read_text(encoding="utf-8")

    assert "import java.time.LocalDate;" in entity_source
    assert "private LocalDate openedDate;" in entity_source
    assert '@Column(name = "account_id", length = 36, updatable = false, nullable = false)' in entity_source
    assert "import java.time.LocalDate;" in request_dto_source
    assert "private LocalDate openedDate;" in request_dto_source
    assert "import java.time.LocalDate;" in response_dto_source
    assert "private LocalDate openedDate;" in response_dto_source
    assert "opened_date DATE NOT NULL" in ddl_source
    assert "opened_date VARCHAR" not in ddl_source
    assert "staging_row_id VARCHAR(36) NOT NULL PRIMARY KEY" in staging_ddl_source
    assert "run_id VARCHAR(64) NOT NULL" in staging_ddl_source
    assert "business_date DATE NOT NULL" in staging_ddl_source
    assert "staging_status VARCHAR(20) NOT NULL" in staging_ddl_source
    assert "created_at TIMESTAMP" in staging_ddl_source
    assert "opened_date DATE NOT NULL" in staging_ddl_source

    assert 'private static final Charset FILE_CHARSET = Charset.forName("ISO-8859-1");' in file_writer_source
    assert "Files.writeString(" in file_writer_source
    assert "FILE_CHARSET" in file_writer_source
    assert (
        "line.append(fixedWidthMinorUnitString(account.getAvailableBalance(), 14));"
        in file_writer_source
    )
    assert "value.movePointRight(2).toBigIntegerExact().toString()" in file_writer_source
    assert 'return " ".repeat(width);' in file_writer_source
    assert "if (converted.length() > width)" in file_writer_source
    assert "Minor-unit value exceeds fixed width" in file_writer_source
    assert 'return "0".repeat(width - converted.length()) + converted;' in file_writer_source
    assert "leftZeroPad" not in file_writer_source
    assert "line.append(padRight(stringValue(account.getAvailableBalance()), 14));" not in file_writer_source
    assert (
        "line.append(padRight(stringValue(account.getAvailableBalance()), 12));"
        in file_writer_source
    )
    assert "line.append(padRight(stringValue(account.getAccountNumber()), 12));" in file_writer_source
    assert "account.getOpenedDate()" in staging_writer_source
    assert "public void clear(String runId)" in staging_writer_source
    assert 'jdbcTemplate.update("DELETE FROM account_staging_tbl WHERE run_id = ?", runId);' in staging_writer_source
    assert 'jdbcTemplate.update("DELETE FROM account_staging_tbl");' not in staging_writer_source
    assert "public void write(Account account, String runId, LocalDate businessDate)" in staging_writer_source
    assert "INSERT INTO account_staging_tbl (staging_row_id, run_id, business_date, staging_status, created_at, account_id, account_number, opened_date, available_balance)" in staging_writer_source
    assert "UUID.randomUUID().toString()" in staging_writer_source
    assert "businessDate" in staging_writer_source
    assert '"READY"' in staging_writer_source
    assert "LocalDateTime.now()" in staging_writer_source

    assert "RepositoryItemReader<Account>" in batch_job_source
    assert ".<Account, Account>chunk(chunkSize, transactionManager)" in batch_job_source
    assert "reader.setPageSize(chunkSize);" in batch_job_source
    assert 'new RepositoryItemReader<>(accountRepository, Map.of("accountId", Sort.Direction.ASC))' in batch_job_source
    assert "java.util.List<Account> records = accountRepository.findAll();" not in batch_job_source
    assert "accountRepository.findAll();" not in batch_job_source
    assert "@Value(\"${app.eod.chunk-size:500}\")" in batch_job_source
    assert "@Value(\"${app.eod.business-date:}\")" in batch_job_source
    assert "stagingWriter.clear(runId);" in batch_job_source
    assert "stagingWriter.clear();" not in batch_job_source
    before_step = batch_job_source.split("public void beforeStep(StepExecution stepExecution)", 1)[1].split(
        "public ExitStatus afterStep", 1
    )[0]
    writer_chunk = batch_job_source.split("return items -> {", 1)[1].split("    @Bean", 1)[0]
    assert "String runId = resolveRunId(stepExecution);" in before_step
    assert "LocalDate businessDate = resolveBusinessDate(stepExecution);" in before_step
    assert 'context.putString("runId", runId);' in before_step
    assert 'context.putString("businessDate", businessDate.toString());' in before_step
    assert "stagingWriter.clear(runId);" in before_step
    assert "stagingWriter.clear(runId);" not in writer_chunk
    assert 'stagingWriter.write(record, context.getString("runId"), LocalDate.parse(context.getString("businessDate")));' in writer_chunk
    assert "stagingWriter.write(record);" not in writer_chunk
    assert "private String resolveRunId(StepExecution stepExecution)" in batch_job_source
    assert "private LocalDate resolveBusinessDate(StepExecution stepExecution)" in batch_job_source
    assert 'stepExecution.getJobParameters().getString("businessDate")' in batch_job_source

    assert "Step accountEodFinalizeStep" in batch_job_source
    assert ".next(accountEodFinalizeStep)" in batch_job_source
    assert "public Step accountEodFinalizeStep(" in batch_job_source
    finalize_step = batch_job_source.split("public Step accountEodFinalizeStep(", 1)[1].split(
        "public RepositoryItemReader<Account>", 1
    )[0]
    assert ".tasklet((contribution, chunkContext) -> {" in finalize_step
    assert "moveReplacing(tempFile, outputFile);" in finalize_step
    assert "return RepeatStatus.FINISHED;" in finalize_step
    after_step_body = batch_job_source.split(
        "public ExitStatus afterStep(StepExecution stepExecution)", 1
    )[1].split("return stepExecution.getExitStatus();", 1)[0]
    assert "moveReplacing(tempFile, outputFile);" not in after_step_body
    assert "Failed to finalize EOD output file" not in batch_job_source
    assert "Path tempOutputFile = Path.of(" in batch_job_source
    assert "handoffFileWriter.write(record, tempOutputFile);" in batch_job_source
    assert "Files.createFile(tempFile);" in batch_job_source
    assert (
        "Files.move(tempFile, outputFile, StandardCopyOption.REPLACE_EXISTING, "
        "StandardCopyOption.ATOMIC_MOVE)"
    ) in batch_job_source
    assert "catch (AtomicMoveNotSupportedException ex)" in batch_job_source
    assert "Files.deleteIfExists(tempFile);" in batch_job_source
    assert "Files.deleteIfExists(outputFile)" not in batch_job_source
    assert "context.putLong(\"recordCount\"" in batch_job_source
    assert "outputStatus" in batch_job_source
    assert "skipReason" in batch_job_source
    assert "NO_RECORDS" in batch_job_source
    assert "log.info(\"EOD job {} finalized {} records at {}\"" in batch_job_source
    assert "chunk-size: ${APP_EOD_CHUNK_SIZE:500}" in application_yaml


def test_generic_crud_fallback_uses_dtos_not_public_entities(tmp_path: Path) -> None:
    metadata = MetadataProject(
        app_name="Fallback CRUD",
        bounded_context="fallback",
        target_profile="springboot-legacy-compatible",
        entities=[
            CanonicalEntity(
                name="Account",
                fields=[
                    CanonicalField(
                        name="accountId",
                        type=CanonicalFieldType.STRING,
                        is_id=True,
                        required=True,
                        server_generated_id=True,
                    ),
                    CanonicalField(
                        name="accountName",
                        type=CanonicalFieldType.STRING,
                        required=True,
                    ),
                    CanonicalField(
                        name="status",
                        type=CanonicalFieldType.STRING,
                        required=True,
                        default_value="ACTIVE",
                    ),
                ],
            )
        ],
    )
    entity = metadata.entities[0]
    target_profile = TARGET_PROFILES["springboot-legacy-compatible"]

    controller_source = _render_controller(
        entity=entity,
        root_package="com.appbuilder.fallback",
        op_contexts=[],
        entity_path_base="/accounts",
        id_java_type="String",
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="fallback-dto-safety",
    )
    service_source = _render_service(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.fallback",
        op_contexts=[],
        id_java_type="String",
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="fallback-dto-safety",
    )
    create_request_source = _render_dto(
        class_name="AccountCreateRequest",
        package_name="com.appbuilder.fallback.adapter.inbound",
        entity=entity,
        field_mappings=_fallback_request_field_mappings(metadata, entity),
        emit_validation_annotations=True,
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="fallback-dto-safety",
    )
    update_request_source = _render_dto(
        class_name="AccountUpdateRequest",
        package_name="com.appbuilder.fallback.adapter.inbound",
        entity=entity,
        field_mappings=_fallback_request_field_mappings(metadata, entity),
        emit_validation_annotations=True,
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="fallback-dto-safety",
    )
    response_source = _render_dto(
        class_name="AccountResponse",
        package_name="com.appbuilder.fallback.adapter.inbound",
        entity=entity,
        field_mappings=_fallback_response_field_mappings(entity),
        emit_validation_annotations=False,
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="fallback-dto-safety",
    )

    assert "ResponseEntity<Account>" not in controller_source
    assert "ResponseEntity<List<Account>>" not in controller_source
    assert "@RequestBody Account request" not in controller_source
    assert "ResponseEntity<AccountResponse> getById(" in controller_source
    assert "ResponseEntity<List<AccountResponse>> listAll()" in controller_source
    assert "ResponseEntity<AccountResponse> create(@Valid @RequestBody AccountCreateRequest request)" in controller_source
    assert "@Valid @RequestBody AccountUpdateRequest request" in controller_source

    assert "public AccountResponse findById(String id)" in service_source
    assert "public List<AccountResponse> findAll()" in service_source
    assert "public AccountResponse create(AccountCreateRequest request)" in service_source
    assert "public AccountResponse update(String id, AccountUpdateRequest request)" in service_source
    assert "public Account findById(" not in service_source
    assert "public List<Account> findAll()" not in service_source
    assert "public Account create(Account request)" not in service_source
    assert "public Account update(String id, Account request)" not in service_source

    assert "private String accountId;" not in create_request_source
    assert "private String accountId;" not in update_request_source
    assert "private String accountName;" in create_request_source
    assert "private String accountName;" in update_request_source
    assert "private String accountId;" in response_source
    assert "private String status;" in response_source


def test_generic_crud_fallback_with_explicit_create_still_uses_fallback_dtos(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "XyzFallbackDtoSafety"

    generate_application(
        metadata,
        output_dir,
        source_manifest="examples/input-projects/xyz-accounts-modernization/app-definition.yaml",
        generation_run_id="fallback-dto-safety-explicit-create",
    )

    base = output_dir / "src/main/java/com/appbuilder/accounts"
    controller_source = (base / "adapter/inbound/AccountController.java").read_text(
        encoding="utf-8"
    )
    service_source = (base / "service/AccountServiceBase.java").read_text(encoding="utf-8")
    update_request_source = (
        base / "adapter/inbound/AccountUpdateRequest.java"
    ).read_text(encoding="utf-8")

    assert "ResponseEntity<Account>" not in controller_source
    assert "ResponseEntity<List<Account>>" not in controller_source
    assert "@RequestBody Account request" not in controller_source
    assert "ResponseEntity<AccountResponse> getById(" in controller_source
    assert "ResponseEntity<List<AccountResponse>> listAll()" in controller_source
    assert "@Valid @RequestBody AccountUpdateRequest request" in controller_source
    assert (base / "adapter/inbound/CreateAccountRequest.java").exists()
    assert not (base / "adapter/inbound/AccountCreateRequest.java").exists()

    assert "public AccountResponse findById(String id)" in service_source
    assert "public List<AccountResponse> findAll()" in service_source
    assert "public AccountResponse update(String id, AccountUpdateRequest request)" in service_source
    assert "public Account findById(" not in service_source
    assert "public List<Account> findAll()" not in service_source
    assert "private String accountId;" not in update_request_source


def test_explicit_create_with_caller_supplied_id_emits_duplicate_conflict_guard(
    tmp_path: Path,
) -> None:
    entity = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(
                name="customerId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=False,
                id_generation_strategy=IdGenerationStrategy.CALLER_SUPPLIED,
            ),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    create_op = CanonicalOperation(
        name="createCustomer",
        interface_name="customer-api",
        request_entity="Customer",
        response_entity="Customer",
    )
    update_op = CanonicalOperation(
        name="updateCustomer",
        interface_name="customer-api",
        request_entity="Customer",
        response_entity="Customer",
    )
    metadata = MetadataProject(
        app_name="Customer App",
        bounded_context="customers",
        target_profile="springboot-legacy-compatible",
        contracts=[ContractMetadata(name="customer-api", type="rest-json", source="")],
        operations=[create_op, update_op],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="customer-api",
                operation_name="createCustomer",
                source_path="customer-api.createCustomer.request.customerId",
                target_path="Customer.customerId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="customer-api",
                operation_name="createCustomer",
                source_path="customer-api.createCustomer.request.customerName",
                target_path="Customer.customerName",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="customer-api",
                operation_name="createCustomer",
                source_path="customer-api.createCustomer.response.customerId",
                target_path="Customer.customerId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="customer-api",
                operation_name="createCustomer",
                source_path="customer-api.createCustomer.response.customerName",
                target_path="Customer.customerName",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="customer-api",
                operation_name="updateCustomer",
                source_path="customer-api.updateCustomer.request.customerName",
                target_path="Customer.customerName",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="customer-api",
                operation_name="updateCustomer",
                source_path="customer-api.updateCustomer.response.customerId",
                target_path="Customer.customerId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="customer-api",
                operation_name="updateCustomer",
                source_path="customer-api.updateCustomer.response.customerName",
                target_path="Customer.customerName",
            ),
        ],
    )

    output_dir = tmp_path / "CustomerCreateDuplicateGuard"
    generate_application(metadata, output_dir, generation_run_id="create-duplicate-guard")
    base = output_dir / "src/main/java/com/appbuilder/customers"
    service_source = (base / "service/CustomerServiceBase.java").read_text(encoding="utf-8")
    handler_source = (base / "exception/GlobalExceptionHandler.java").read_text(
        encoding="utf-8"
    )

    create_body = service_source.split("public CreateCustomerResponse createCustomer", 1)[1].split(
        "public UpdateCustomerResponse updateCustomer", 1
    )[0]
    guard = "customerRepository.existsById(customer.getCustomerId())"
    assert guard in create_body
    assert 'throw new DuplicateResourceException("Customer already exists with id: " + customer.getCustomerId());' in create_body
    assert create_body.index(guard) < create_body.index("customerRepository.save(customer)")

    update_body = service_source.split("public UpdateCustomerResponse updateCustomer", 1)[1].split(
        "public CreateCustomerResponse createCustomer", 1
    )[0]
    assert "customerRepository.findById(id)" in update_body
    assert "DuplicateResourceException" not in update_body

    assert (base / "exception/DuplicateResourceException.java").exists()
    assert "@ExceptionHandler(DuplicateResourceException.class)" in handler_source
    assert "@ResponseStatus(HttpStatus.CONFLICT)" in handler_source
    assert 'HttpStatus.CONFLICT.value()' in handler_source
    assert '"Conflict"' in handler_source


def test_generic_create_fallback_with_caller_supplied_id_emits_duplicate_conflict_guard(
    tmp_path: Path,
) -> None:
    entity = CanonicalEntity(
        name="ExternalCustomer",
        fields=[
            CanonicalField(
                name="externalCustomerId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=False,
                id_generation_strategy=IdGenerationStrategy.CALLER_SUPPLIED,
            ),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    metadata = MetadataProject(
        app_name="External Customer App",
        bounded_context="externalcustomers",
        target_profile="springboot-legacy-compatible",
        entities=[entity],
    )

    service_source = _render_service(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.externalcustomers",
        op_contexts=[],
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="fallback-duplicate-guard",
    )

    create_body = service_source.split("public ExternalCustomerResponse create", 1)[1].split(
        "public void delete", 1
    )[0]
    guard = "externalCustomerRepository.existsById(externalCustomer.getExternalCustomerId())"
    assert guard in create_body
    assert (
        'throw new DuplicateResourceException("ExternalCustomer already exists with id: " '
        "+ externalCustomer.getExternalCustomerId());"
    ) in create_body
    assert create_body.index(guard) < create_body.index(
        "externalCustomerRepository.save(externalCustomer)"
    )


def test_server_generated_create_does_not_emit_duplicate_id_guard(tmp_path: Path) -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=True,
            ),
            CanonicalField(name="accountName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    metadata = MetadataProject(
        app_name="Account App",
        bounded_context="accounts",
        target_profile="springboot-legacy-compatible",
        entities=[entity],
    )

    service_source = _render_service(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.accounts",
        op_contexts=[],
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="server-generated-no-guard",
    )

    create_body = service_source.split("public AccountResponse create", 1)[1].split(
        "public void delete", 1
    )[0]
    assert "account.setAccountId(" not in create_body
    assert "accountRepository.existsById(account.getAccountId())" not in create_body
    assert "existsById(null)" not in create_body


def test_staging_operational_columns_without_run_id_generate_compile_safe_writer_and_batch() -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="Operational Staging",
        bounded_context="ops",
        target_profile="springboot-legacy-compatible",
        contracts=[
                ContractMetadata(
                    name="account-staging-table",
                    type="staging-table",
                    source="data-handoffs/account-staging-table.sql",
                    physical_name="account_staging_tbl",
                )
        ],
        entities=[entity],
        mappings=[
            FieldMapping(
                contract_name="account-staging-table",
                direction=MappingDirection.CANONICAL_TO_HANDOFF,
                source_path="Account.accountId",
                target_path="account-staging-table.account_id",
            )
        ],
        staging_table_ddls={
            "account_staging_tbl": """
            CREATE TABLE account_staging_tbl (
                staging_row_id VARCHAR(36) NOT NULL PRIMARY KEY,
                business_date DATE NOT NULL,
                created_at TIMESTAMP,
                account_id VARCHAR(36) NOT NULL
            );
            """
        },
    )
    target_profile = TARGET_PROFILES["springboot-legacy-compatible"]

    writer_source = _render_staging_writer(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.ops",
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="operational-no-run-id",
    )
    batch_source = _render_batch_job(
        entity=entity,
        root_package="com.appbuilder.ops",
        bounded_context="ops",
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="operational-no-run-id",
        staging_has_run_identity=False,
        staging_has_business_date=True,
    )

    assert "import java.time.LocalDate;" in writer_source
    assert "import java.time.LocalDateTime;" in writer_source
    assert "import java.util.UUID;" in writer_source
    assert "public void clear()" in writer_source
    assert "public void clear(String runId)" not in writer_source
    assert 'jdbcTemplate.update("DELETE FROM account_staging_tbl");' in writer_source
    assert "public void write(Account account, LocalDate businessDate)" in writer_source
    assert "UUID.randomUUID().toString()" in writer_source
    assert "businessDate" in writer_source
    assert "LocalDateTime.now()" in writer_source
    assert "runId" not in writer_source

    assert "import java.time.LocalDate;" in batch_source
    assert "import java.util.UUID;" not in batch_source
    assert "String runId = resolveRunId(stepExecution);" not in batch_source
    assert "private String resolveRunId(StepExecution stepExecution)" not in batch_source
    assert "LocalDate businessDate = resolveBusinessDate(stepExecution);" in batch_source
    assert "private LocalDate resolveBusinessDate(StepExecution stepExecution)" in batch_source
    assert "stagingWriter.clear();" in batch_source
    assert "stagingWriter.clear(runId);" not in batch_source
    assert 'stagingWriter.write(record, LocalDate.parse(context.getString("businessDate")));' in batch_source


def test_generated_staging_only_eod_batch_marks_failed_steps_failed() -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
            ),
            CanonicalField(
                name="accountName",
                type=CanonicalFieldType.STRING,
                required=True,
            ),
        ],
    )

    batch_job_source = _render_batch_job(
        entity=entity,
        root_package="com.appbuilder.accounts",
        bounded_context="accounts",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test-manifest.yaml",
        generation_run_id="staging-only-eod-status-test",
        has_file_writer=False,
    )

    assert ".next(accountEodFinalizeStep)" not in batch_job_source
    assert "public Step accountEodFinalizeStep(" not in batch_job_source
    after_step = batch_job_source.split("public ExitStatus afterStep(StepExecution stepExecution)", 1)[1]
    assert "else if (stepExecution.getStatus() != BatchStatus.COMPLETED)" in after_step
    assert "context.putString(\"outputStatus\", \"FAILED\");" in after_step
    assert "log.warn(\"EOD job {} failed after {} staging records\"" in after_step
    assert "log.info(\"EOD job {} completed with {} staging records; status={}\"" in after_step


def test_generated_controller_and_dashboard_align_on_spec_preserved_route(tmp_path: Path) -> None:
    profile_name = "springboot-spec-route-cross-emitter-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=False,
        emit_security=False,
        emit_test_console=True,
        emit_audit=False,
        supports_xml=False,
    )

    pet = CanonicalEntity(
        name="Pet",
        fields=[
            CanonicalField(
                name="petId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=36,
            ),
            CanonicalField(
                name="name",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=64,
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="Pet Store",
        bounded_context="petstore",
        target_profile=profile_name,
        systems=[SystemParticipant(name="Petstore", role="upstream")],
        contracts=[ContractMetadata(name="pet-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="addPet",
                interface_name="pet-api",
                request_entity="Pet",
                response_entity="Pet",
                http_method=HttpMethod.POST,
                path="/pet",
                response_shape=ResponseShape.CREATED,
            ),
            CanonicalOperation(
                name="getPetById",
                interface_name="pet-api",
                request_entity="Pet",
                response_entity="Pet",
                http_method=HttpMethod.GET,
                path="/pet/{petId}",
                path_parameters=[PathParameter(name="petId", type="String")],
                response_shape=ResponseShape.SINGLE,
            ),
        ],
        entities=[pet],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="pet-api",
                operation_name="addPet",
                source_path="pet-api.addPet.request.name",
                target_path="Pet.name",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="pet-api",
                operation_name="addPet",
                source_path="pet-api.addPet.response.petId",
                target_path="Pet.petId",
            ),
        ],
    )

    try:
        output_dir = tmp_path / "SpecRouteAlignedPetApp"
        generate_application(metadata, output_dir, generation_run_id="spec-route-alignment")

        controller = (
            output_dir
            / "src/main/java/com/appbuilder/petstore/adapter/inbound/PetController.java"
        ).read_text(encoding="utf-8")
        html = (
            output_dir / "src/main/resources/static/index.html"
        ).read_text(encoding="utf-8")

        assert '@RequestMapping("/pet")' in controller
        create_descriptor = _dashboard_descriptor(html, "Pet-create")
        get_descriptor = _dashboard_descriptor(html, "Pet-get")
        assert create_descriptor["actions"][0]["endpoint"] == "/pet"
        assert get_descriptor["actions"][0]["endpoint"] == "/pet/{petId}"
        assert get_descriptor["actions"][0]["inputBinding"] == "PATH_PARAM"
        assert 'POST /pet &mdash; Create Pet' in html
        assert 'GET /pet/{petId} &mdash; Get Pet by ID' in html
        assert 'PUT /pet/{id} &mdash; Update Pet' in html
        assert 'DELETE /pet/{id} &mdash; Delete Pet' in html
        assert '@RequestMapping("/pets")' not in controller
        assert '"endpoint": "/pets"' not in html
        assert 'POST /pets' not in html
        assert 'GET /pets/{id}' not in html
    finally:
        TARGET_PROFILES.pop(profile_name, None)


def test_openapi_crud_controller_and_dashboard_routes_share_source_paths(tmp_path: Path) -> None:
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="accountName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    earmark = CanonicalEntity(
        name="Earmark",
        fields=[
            CanonicalField(name="earmarkId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="status", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    transaction_posting = CanonicalEntity(
        name="TransactionPosting",
        fields=[
            CanonicalField(name="postingId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="status", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    operations = [
        CanonicalOperation(
            name="createCustomer",
            interface_name="dda-api",
            request_entity="Customer",
            response_entity="Customer",
            http_method=HttpMethod.POST,
            path="/api/v1/customers",
            response_shape=ResponseShape.CREATED,
        ),
        CanonicalOperation(
            name="getCustomer",
            interface_name="dda-api",
            request_entity="Customer",
            response_entity="Customer",
            http_method=HttpMethod.GET,
            path="/api/v1/customers/{customerId}",
            path_parameters=[PathParameter(name="customerId", type="String")],
            response_shape=ResponseShape.SINGLE,
        ),
        CanonicalOperation(
            name="listCustomers",
            interface_name="dda-api",
            request_entity="Customer",
            response_entity="Customer",
            http_method=HttpMethod.GET,
            path="/api/v1/customers",
            response_shape=ResponseShape.LIST,
        ),
        CanonicalOperation(
            name="updateCustomer",
            interface_name="dda-api",
            request_entity="Customer",
            response_entity="Customer",
            http_method=HttpMethod.PUT,
            path="/api/v1/customers/{customerId}",
            path_parameters=[PathParameter(name="customerId", type="String")],
            response_shape=ResponseShape.SINGLE,
        ),
        CanonicalOperation(
            name="createAccount",
            interface_name="dda-api",
            request_entity="Account",
            response_entity="Account",
            http_method=HttpMethod.POST,
            path="/api/v1/accounts",
            response_shape=ResponseShape.CREATED,
        ),
        CanonicalOperation(
            name="createEarmark",
            interface_name="dda-api",
            request_entity="Earmark",
            response_entity="Earmark",
            http_method=HttpMethod.POST,
            path="/api/v1/earmarks",
            response_shape=ResponseShape.CREATED,
        ),
        CanonicalOperation(
            name="releaseEarmark",
            interface_name="dda-api",
            request_entity="Earmark",
            response_entity="Earmark",
            http_method=HttpMethod.POST,
            path="/api/v1/earmarks/{earmarkId}/release",
            path_parameters=[PathParameter(name="earmarkId", type="String")],
            response_shape=ResponseShape.SINGLE,
        ),
        CanonicalOperation(
            name="postTransaction",
            interface_name="dda-api",
            request_entity="TransactionPosting",
            response_entity="TransactionPosting",
            http_method=HttpMethod.POST,
            path="/api/v1/transactions/post",
            response_shape=ResponseShape.SINGLE,
        ),
    ]
    mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="createCustomer",
            source_path="dda-api.createCustomer.request.customerName",
            target_path="Customer.customerName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="createCustomer",
            source_path="dda-api.createCustomer.response.customerId",
            target_path="Customer.customerId",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="getCustomer",
            source_path="dda-api.getCustomer.response.customerId",
            target_path="Customer.customerId",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="listCustomers",
            source_path="dda-api.listCustomers.response.customerName",
            target_path="Customer.customerName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="updateCustomer",
            source_path="dda-api.updateCustomer.request.customerName",
            target_path="Customer.customerName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="updateCustomer",
            source_path="dda-api.updateCustomer.response.customerId",
            target_path="Customer.customerId",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="createAccount",
            source_path="dda-api.createAccount.request.accountName",
            target_path="Account.accountName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="createAccount",
            source_path="dda-api.createAccount.response.accountId",
            target_path="Account.accountId",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="createEarmark",
            source_path="dda-api.createEarmark.request.status",
            target_path="Earmark.status",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="createEarmark",
            source_path="dda-api.createEarmark.response.earmarkId",
            target_path="Earmark.earmarkId",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="releaseEarmark",
            source_path="dda-api.releaseEarmark.response.status",
            target_path="Earmark.status",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="postTransaction",
            source_path="dda-api.postTransaction.request.status",
            target_path="TransactionPosting.status",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="dda-api",
            operation_name="postTransaction",
            source_path="dda-api.postTransaction.response.postingId",
            target_path="TransactionPosting.postingId",
        ),
    ]
    metadata = MetadataProject(
        app_name="Basic Ledger Demo",
        bounded_context="dda",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="DDA", role="upstream")],
        contracts=[ContractMetadata(name="dda-api", type="rest-json", source="http://localhost:8081/v3/api-docs")],
        operations=operations,
        entities=[customer, account, earmark, transaction_posting],
        mappings=mappings,
    )

    output_dir = tmp_path / "BasicDda"
    generate_application(metadata, output_dir, generation_run_id="openapi-route-alignment")
    base = output_dir / "src/main/java/com/appbuilder/dda/adapter/inbound"
    customer_controller = (base / "CustomerController.java").read_text(encoding="utf-8")
    account_controller = (base / "AccountController.java").read_text(encoding="utf-8")
    earmark_controller = (base / "EarmarkController.java").read_text(encoding="utf-8")
    posting_controller = (base / "TransactionPostingController.java").read_text(encoding="utf-8")
    html = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert '@RequestMapping("/api/v1/customers")' in customer_controller
    assert '@RequestMapping("/customers")' not in customer_controller
    assert "POST /api/v1/customers" in customer_controller
    assert '@GetMapping("/{customerId}")' in customer_controller
    assert "@GetMapping\n" in customer_controller
    assert '@PutMapping("/{id}")' in customer_controller
    assert '@DeleteMapping("/{id}")' in customer_controller

    assert '@RequestMapping("/api/v1/accounts")' in account_controller
    assert '@RequestMapping("/api/v1/earmarks")' in earmark_controller
    assert '@PostMapping("/{earmarkId}/release")' in earmark_controller
    assert '@RequestMapping("/api/v1/transactions/post")' in posting_controller
    assert '@RequestMapping("/transaction_postings")' not in posting_controller

    assert _dashboard_descriptor(html, "Customer-create")["actions"][0]["endpoint"] == "/api/v1/customers"
    assert _dashboard_descriptor(html, "Customer-get")["actions"][0]["endpoint"] == "/api/v1/customers/{customerId}"
    assert _dashboard_descriptor(html, "Customer-list")["actions"][0]["endpoint"] == "/api/v1/customers"
    assert _dashboard_descriptor(html, "Customer-update")["actions"][0]["endpoint"] == "/api/v1/customers/{id}"
    assert _dashboard_descriptor(html, "Account-create")["actions"][0]["endpoint"] == "/api/v1/accounts"
    assert _dashboard_descriptor(html, "Earmark-create")["actions"][0]["endpoint"] == "/api/v1/earmarks"
    assert (
        _dashboard_descriptor(html, "TransactionPosting-create")["actions"][0]["endpoint"]
        == "/api/v1/transactions/post"
    )
    descriptor_routes = [
        descriptor["actions"][0]["endpoint"]
        for descriptor in _extract_dashboard_descriptors(html)
        if descriptor["family"] == "rest-crud"
    ]
    assert "/customers" not in descriptor_routes
    assert "<built-in function id>" not in html
    assert 'POST /api/v1/customers &mdash; Create Customer' in html
    assert 'POST /api/v1/accounts &mdash; Create Account' in html
    assert 'POST /api/v1/earmarks &mdash; Create Earmark' in html
    assert 'POST /api/v1/transactions/post &mdash; Create TransactionPosting' in html


def test_nested_parent_context_ids_are_refused_before_crud_generation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "codat-customer-generation"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "upstream" / "create-customer-request.json").write_text(
        json.dumps({"customerName": "Alice"}), encoding="utf-8"
    )
    (project_root / "upstream" / "create-customer-response.json").write_text(
        json.dumps(
            {
                "id": "cust-001",
                "companyId": "comp-001",
                "customerName": "Alice",
            }
        ),
        encoding="utf-8",
    )
    (project_root / "upstream" / "get-customer-response.json").write_text(
        json.dumps(
            {
                "id": "cust-001",
                "companyId": "comp-001",
                "customerName": "Alice",
            }
        ),
        encoding="utf-8",
    )
    (project_root / "upstream" / "customer-mapping.yaml").write_text(
        "\n".join(
            [
                "interface: codat-customer-api",
                "entity: Customer",
                "operations:",
                "  - name: createCustomer",
                "    request_mappings:",
                "      - source: customerName",
                "        target: Customer.customerName",
                "    response_mappings:",
                "      - source: id",
                "        target: Customer.id",
                "      - source: companyId",
                "        target: Customer.companyId",
                "      - source: customerName",
                "        target: Customer.customerName",
                "  - name: getCustomer",
                "    request_mappings: []",
                "    response_mappings:",
                "      - source: id",
                "        target: Customer.id",
                "      - source: companyId",
                "        target: Customer.companyId",
                "      - source: customerName",
                "        target: Customer.customerName",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Codat Customer Generation",
                "bounded_context: customers",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: codat-customer-api",
                "    system: CODAT",
                "    type: rest-json",
                "    spec_url: http://localhost:8080/codat/openapi.yaml",
                "    mapping: upstream/customer-mapping.yaml",
                "    operations:",
                "      - name: createCustomer",
                "        request_sample: upstream/create-customer-request.json",
                "        response_sample: upstream/create-customer-response.json",
                "      - name: getCustomer",
                "        response_sample: upstream/get-customer-response.json",
                "target_profile: springboot-legacy-compatible",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    spec = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "properties": {
                        "companyId": {"type": "string"},
                        "id": {"type": "string"},
                        "customerName": {"type": "string"},
                    },
                }
            }
        },
        "paths": {
            "/companies/{companyId}/customers": {
                "post": {
                    "operationId": "createCustomer",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "customerName": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Customer"}
                                }
                            }
                        }
                    },
                }
            },
            "/companies/{companyId}/customers/{customerId}": {
                "get": {
                    "operationId": "getCustomer",
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Customer"}
                                }
                            }
                        }
                    },
                }
            },
        },
    }
    monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", lambda url: spec)

    metadata = build_metadata_project(project_root / "app-definition.yaml")
    metadata.entities = [entity for entity in metadata.entities if entity.name == "Customer"]
    output_dir = tmp_path / "generated"
    with pytest.raises(ValueError, match="getCustomer.*unsupported"):
        generate_application(metadata, output_dir, generation_run_id="nested-context-refusal")
    assert not output_dir.exists()
    # Entity/UUID ownership checks below use a separate supported own-ID read.
    operation = next(op for op in metadata.operations if op.name == "getCustomer")
    operation.path = "/customers/{id}"
    operation.path_parameters = [PathParameter(name="id", type="String")]
    operation.read_input_errors = []
    next(op for op in metadata.operations if op.name == "createCustomer").path = "/customers"
    next(op for op in metadata.operations if op.name == "createCustomer").path_parameters = []
    # Keep retained source transport aligned with this separate supported variant.
    create_contract = next(contract for contract in metadata.selected_rest_contracts if contract["operation"] == "createCustomer")
    create_contract["path"] = "/customers"
    create_contract["parameters"] = []
    create_contract["body"]["required"] = True
    generate_application(metadata, output_dir, generation_run_id="codat-id-fix")

    entity_source = (
        output_dir / "src/main/java/com/appbuilder/customers/domain/Customer.java"
    ).read_text(encoding="utf-8")
    service_source = (
        output_dir / "src/main/java/com/appbuilder/customers/service/CustomerServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "@Id" in entity_source
    assert "@GeneratedValue(strategy = GenerationType.UUID)" in entity_source
    assert "@Column(name = \"id\"" in entity_source
    assert "@Column(name = \"company_id\"" in entity_source
    assert "@Column(name = \"company_id\")\n    private String companyId;" in entity_source
    assert "@Id\n    // ID ownership: server-generated UUID (id absent from POST body schema).\n    @GeneratedValue(strategy = GenerationType.UUID)\n    @Column(name = \"id\", length = 36, updatable = false)\n    private String id;" in entity_source
    assert "createCustomerResponse.setId(saved.getId());" in service_source
    assert "request.getId()" not in service_source
    assert "request.getCompanyId()" not in service_source
    assert "customerRepository.findById(id)" in service_source


def test_hyphenated_operation_names_are_sanitized_for_java_symbols(tmp_path: Path) -> None:
    metadata = _build_single_operation_metadata("create-permission-group")

    try:
        output_dir = tmp_path / "PermissionGroups"
        generate_application(metadata, output_dir, generation_run_id="java-identifier-test")

        controller_source = (
            output_dir
            / "src/main/java/com/appbuilder/permissions/adapter/inbound/PermissionGroupController.java"
        ).read_text(encoding="utf-8")
        service_source = (
            output_dir
            / "src/main/java/com/appbuilder/permissions/service/PermissionGroupServiceBase.java"
        ).read_text(encoding="utf-8")

        assert (
            output_dir
            / "src/main/java/com/appbuilder/permissions/adapter/inbound/CreatePermissionGroupRequest.java"
        ).exists()
        assert (
            output_dir
            / "src/main/java/com/appbuilder/permissions/adapter/inbound/CreatePermissionGroupResponse.java"
        ).exists()
        assert "createPermissionGroup(" in controller_source
        assert "createPermissionGroup(" in service_source
        assert "create-permission-group(" not in controller_source
        assert "create-permission-group(" not in service_source
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_digit_prefixed_and_keyword_operation_names_are_sanitized_for_java_symbols(tmp_path: Path) -> None:
    for operation_name, expected_class_name, expected_method_name in [
        ("123-create", "Generated123Create", "generated123Create"),
        ("class", "Class", "classValue"),
    ]:
        metadata = _build_single_operation_metadata(operation_name)
        try:
            output_dir = tmp_path / expected_class_name
            generate_application(metadata, output_dir, generation_run_id=f"java-id-{expected_method_name}")

            controller_source = (
                output_dir
                / "src/main/java/com/appbuilder/permissions/adapter/inbound/PermissionGroupController.java"
            ).read_text(encoding="utf-8")
            service_source = (
                output_dir
                / "src/main/java/com/appbuilder/permissions/service/PermissionGroupServiceBase.java"
            ).read_text(encoding="utf-8")

            assert (
                output_dir
                / f"src/main/java/com/appbuilder/permissions/adapter/inbound/{expected_class_name}Request.java"
            ).exists()
            assert (
                output_dir
                / f"src/main/java/com/appbuilder/permissions/adapter/inbound/{expected_class_name}Response.java"
            ).exists()
            assert f"{expected_method_name}(" in controller_source
            assert f"{expected_method_name}(" in service_source
            assert f"{operation_name}(" not in controller_source
            assert f"{operation_name}(" not in service_source
        finally:
            TARGET_PROFILES.pop(metadata.target_profile, None)


def test_flyway_migration_matches_canonical_entity(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()

    output_dir = tmp_path / "BuiltAppSql"
    generate_application(metadata, output_dir, generation_run_id="sql-test")
    migration = (
        output_dir
        / "src/main/resources/db/migration/V1__create_account_table.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE account (" in migration
    assert "account_id VARCHAR(36) NOT NULL PRIMARY KEY" in migration
    assert "currency CHAR(3) NOT NULL" in migration
    assert "status VARCHAR(10) DEFAULT 'PENDING'" in migration


def test_iso_4217_currency_field_emits_validation(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()

    output_dir = tmp_path / "BuiltAppIso4217"
    generate_application(metadata, output_dir, generation_run_id="iso-4217-test")

    request_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/CreateAccountRequest.java"
    ).read_text(encoding="utf-8")
    entity_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    ).read_text(encoding="utf-8")
    service_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/service/AccountServiceBase.java"
    ).read_text(encoding="utf-8")
    migration = (
        output_dir
        / "src/main/resources/db/migration/V1__create_account_table.sql"
    ).read_text(encoding="utf-8")

    assert '@Pattern(regexp="[A-Z]{3}")' in request_source
    assert '@Pattern(regexp="[A-Z]{3}")' not in entity_source
    assert "import org.hibernate.annotations.JdbcTypeCode;" in entity_source
    assert "import org.hibernate.type.SqlTypes;" in entity_source
    assert "@JdbcTypeCode(SqlTypes.CHAR)" in entity_source
    assert '@Column(name = "currency", columnDefinition = "CHAR(3)", nullable = false)' in entity_source
    assert '@Column(name = "currency", length = 3, nullable = false)' not in entity_source

    assert '.matches("[A-Z]{3}")' in service_source
    assert "Invalid ISO-4217 currency code:" in service_source
    assert "// TODO: validate iso-4217 format for currency." not in service_source

    assert "currency CHAR(3) NOT NULL" in migration
    assert "currency VARCHAR(3)" not in migration


def test_pattern_annotation_uses_escaped_java_literal() -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=True,
            ),
            CanonicalField(
                name="routingCode",
                type=CanonicalFieldType.STRING,
                required=True,
                pattern="^ABC\nDEF\tGHI\x01$",
            ),
        ],
    )

    request_source = _render_dto(
        class_name="CreateAccountRequest",
        package_name="com.appbuilder.escaping.adapter.inbound",
        entity=entity,
        field_mappings=_fallback_request_field_mappings(
            MetadataProject(
                app_name="Escaping Proof",
                bounded_context="escaping",
                target_profile="springboot-legacy-compatible",
                entities=[entity],
            ),
            entity,
        ),
        emit_validation_annotations=True,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="pattern-escaping-test",
    )

    assert '@Pattern(regexp="^ABC\\nDEF\\tGHI\\u0001$")' in request_source
    pattern_line = next(line for line in request_source.splitlines() if "@Pattern" in line)
    assert "ABC\nDEF" not in pattern_line


def test_flyway_migration_applies_phase_a_constraints(tmp_path: Path) -> None:
    metadata = _load_loans_metadata()
    fields = {field.name: field for field in metadata.entities[0].fields}
    fields["borrowerId"].min_length = 5
    fields["borrowerId"].pattern = "^[A-Z0-9-]+$"
    fields["principalAmount"].range_min = 0.01
    fields["principalAmount"].range_max = 999999.99

    output_dir = tmp_path / "BuiltAppSqlConstraints"
    generate_application(metadata, output_dir, generation_run_id="sql-constraints-test")
    migration = (
        output_dir
        / "src/main/resources/db/migration/V1__create_loan_table.sql"
    ).read_text(encoding="utf-8")

    assert "-- PATTERN: borrower_id => ^[A-Z0-9-]+$" in migration
    assert "borrower_id VARCHAR(20) NOT NULL CHECK (LENGTH(borrower_id) >= 5)" in migration
    assert (
        "principal_amount DECIMAL(19,4) NOT NULL CHECK "
        "(principal_amount >= 0.01 AND principal_amount <= 999999.99)"
    ) in migration


def test_flyway_migration_keeps_not_null_when_default_is_present(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    status_field = next(field for field in metadata.entities[0].fields if field.name == "status")
    status_field.required = False
    status_field.not_null = True
    status_field.default_value = "PENDING"

    output_dir = tmp_path / "BuiltAppSqlNotNullDefault"
    generate_application(metadata, output_dir, generation_run_id="sql-not-null-default")
    migration = (
        output_dir
        / "src/main/resources/db/migration/V1__create_account_table.sql"
    ).read_text(encoding="utf-8")

    assert "status VARCHAR(10) DEFAULT 'PENDING' NOT NULL" in migration


def test_flyway_sql_defaults_are_type_safe_and_escaped(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    account = metadata.entities[0]
    status_field = next(field for field in account.fields if field.name == "status")
    status_field.default_value = "O'Hare"
    account.fields.extend(
        [
            CanonicalField(
                name="retryCount",
                type=CanonicalFieldType.INTEGER,
                default_value="+42",
            ),
            CanonicalField(
                name="creditLimit",
                type=CanonicalFieldType.DECIMAL,
                default_value=".5",
            ),
            CanonicalField(
                name="enabled",
                type=CanonicalFieldType.BOOLEAN,
                default_value="TRUE",
            ),
        ]
    )

    output_dir = tmp_path / "BuiltAppSqlEscapedDefaults"
    generate_application(metadata, output_dir, generation_run_id="sql-escaped-defaults")
    migration = (
        output_dir
        / "src/main/resources/db/migration/V1__create_account_table.sql"
    ).read_text(encoding="utf-8")

    assert "status VARCHAR(10) DEFAULT 'O''Hare'" in migration
    assert "retry_count BIGINT DEFAULT +42" in migration
    assert "credit_limit DECIMAL(19,4) DEFAULT .5" in migration
    assert "enabled BOOLEAN DEFAULT true" in migration


def test_java_field_defaults_are_type_safe_and_escaped(tmp_path: Path) -> None:
    metadata = MetadataProject(
        app_name="Escaping Proof",
        bounded_context="escaping",
        target_profile="springboot-legacy-compatible",
        entities=[
            CanonicalEntity(
                name="Account",
                fields=[
                    CanonicalField(
                        name="accountId",
                        type=CanonicalFieldType.STRING,
                        is_id=True,
                        required=True,
                        server_generated_id=True,
                    ),
                    CanonicalField(
                        name="status",
                        type=CanonicalFieldType.STRING,
                        default_value='init"); System.exit(1); String z=("',
                    ),
                    CanonicalField(
                        name="retryCount",
                        type=CanonicalFieldType.INTEGER,
                        default_value="+42",
                    ),
                    CanonicalField(
                        name="creditLimit",
                        type=CanonicalFieldType.DECIMAL,
                        default_value=".5",
                    ),
                    CanonicalField(
                        name="enabled",
                        type=CanonicalFieldType.BOOLEAN,
                        default_value="TRUE",
                    ),
                    CanonicalField(
                        name="openedOn",
                        type=CanonicalFieldType.DATE,
                        default_value="2026-01-02",
                    ),
                    CanonicalField(
                        name="updatedAt",
                        type=CanonicalFieldType.DATETIME,
                        default_value="2026-01-02T03:04:05",
                    ),
                ],
            )
        ],
    )

    output_dir = tmp_path / "BuiltAppJavaEscapedDefaults"
    generate_application(metadata, output_dir, generation_run_id="java-escaped-defaults")
    entity_source = next((output_dir / "src/main/java").rglob("Account.java")).read_text(
        encoding="utf-8"
    )

    assert 'private String status = "init\\"); System.exit(1); String z=(\\"";' in entity_source
    assert 'private String status = "init"); System.exit' not in entity_source
    assert "private Long retryCount = +42L;" in entity_source
    assert 'private BigDecimal creditLimit = new BigDecimal(".5");' in entity_source
    assert "private Boolean enabled = true;" in entity_source
    assert 'private LocalDate openedOn = LocalDate.parse("2026-01-02");' in entity_source
    assert 'private LocalDateTime updatedAt = LocalDateTime.parse("2026-01-02T03:04:05");' in entity_source


@pytest.mark.parametrize(
    ("field", "message"),
    [
        (
            CanonicalField(
                name="unsafeInteger",
                type=CanonicalFieldType.INTEGER,
                default_value="0; evilStatic()",
            ),
            "Invalid Java integer literal",
        ),
        (
            CanonicalField(
                name="unsafeDecimal",
                type=CanonicalFieldType.DECIMAL,
                default_value="0); evilStatic();",
            ),
            "Invalid Java decimal literal",
        ),
        (
            CanonicalField(
                name="unsafeBoolean",
                type=CanonicalFieldType.BOOLEAN,
                default_value="false); evil(); boolean x=(true",
            ),
            "Invalid Java boolean literal",
        ),
        (
            CanonicalField(
                name="unsafeDate",
                type=CanonicalFieldType.DATE,
                default_value='2026-01-02"); evil();//',
            ),
            "Invalid Java date literal",
        ),
    ],
)
def test_java_field_defaults_fail_closed_for_unsafe_values(
    tmp_path: Path,
    field: CanonicalField,
    message: str,
) -> None:
    metadata = MetadataProject(
        app_name="Escaping Proof",
        bounded_context="escaping",
        target_profile="springboot-legacy-compatible",
        entities=[
            CanonicalEntity(
                name="Account",
                fields=[
                    CanonicalField(
                        name="accountId",
                        type=CanonicalFieldType.STRING,
                        is_id=True,
                        required=True,
                        server_generated_id=True,
                    ),
                    field,
                ],
            )
        ],
    )

    with pytest.raises(ValueError, match=message):
        generate_application(
            metadata,
            tmp_path / f"BuiltApp{field.name}",
            generation_run_id="java-unsafe-defaults",
        )


def test_generated_java_package_scan_escapes_default_and_rule_payloads(tmp_path: Path) -> None:
    default_payload = 'java-default-sentinel"); System.exit(1); String z=("'
    expected_payload = 'java-rule-sentinel"); System.exit(2);//'
    metadata = MetadataProject(
        app_name="Escaping Proof",
        bounded_context="escaping",
        target_profile="springboot-legacy-compatible",
        entities=[
            CanonicalEntity(
                name="Account",
                fields=[
                    CanonicalField(
                        name="accountId",
                        type=CanonicalFieldType.STRING,
                        is_id=True,
                        required=True,
                        server_generated_id=True,
                    ),
                    CanonicalField(
                        name="status",
                        type=CanonicalFieldType.STRING,
                        default_value=default_payload,
                    ),
                ],
            ),
            CanonicalEntity(
                name="Transaction",
                fields=[
                    CanonicalField(
                        name="transactionId",
                        type=CanonicalFieldType.STRING,
                        is_id=True,
                        required=True,
                        server_generated_id=True,
                    ),
                    CanonicalField(
                        name="accountId",
                        type=CanonicalFieldType.STRING,
                        required=True,
                    ),
                ],
            ),
        ],
        rules=[
            CanonicalRule(
                entity_name="Transaction",
                field_name="accountId",
                type=RuleType.CROSS_ENTITY_EXISTS,
                source_path="rules.Transaction.accountId.cross-entity-exists",
                target_entity="Account",
            ),
            CanonicalRule(
                entity_name="Transaction",
                field_name="accountId",
                type=RuleType.CROSS_ENTITY_FIELD_CHECK,
                source_path="rules.Transaction.accountId.cross-entity-field-check",
                target_entity="Account",
                target_field="status",
                operator="eq",
                expected_value=expected_payload,
            ),
        ],
    )

    output_dir = tmp_path / "BuiltAppJavaInjectionScan"
    generate_application(metadata, output_dir, generation_run_id="java-injection-scan")
    java_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((output_dir / "src/main/java").rglob("*.java"))
    )

    assert default_payload not in java_sources
    assert expected_payload not in java_sources
    assert '"java-default-sentinel"); System.exit' not in java_sources
    assert '"java-rule-sentinel"); System.exit' not in java_sources
    assert 'java-default-sentinel\\"); System.exit(1); String z=(\\"' in java_sources
    assert 'java-rule-sentinel\\"); System.exit(2);//' in java_sources


@pytest.mark.parametrize(
    ("field", "message"),
    [
        (
            CanonicalField(
                name="unsafeString",
                type=CanonicalFieldType.STRING,
                default_value="bad\x00default",
            ),
            "string/date defaults must not contain control characters",
        ),
        (
            CanonicalField(
                name="unsafeInteger",
                type=CanonicalFieldType.INTEGER,
                default_value="0); DROP TABLE account; --",
            ),
            "integer defaults must be integer literals",
        ),
        (
            CanonicalField(
                name="unsafeDecimal",
                type=CanonicalFieldType.DECIMAL,
                default_value="0); DROP TABLE account; --",
            ),
            "decimal defaults must be numeric literals",
        ),
        (
            CanonicalField(
                name="unsafeBoolean",
                type=CanonicalFieldType.BOOLEAN,
                default_value="yes",
            ),
            "boolean defaults must be true or false",
        ),
    ],
)
def test_flyway_sql_defaults_fail_closed_for_unsafe_values(
    tmp_path: Path,
    field: CanonicalField,
    message: str,
) -> None:
    metadata = MetadataProject(
        app_name="Escaping Proof",
        bounded_context="escaping",
        target_profile="springboot-legacy-compatible",
        entities=[
            CanonicalEntity(
                name="Account",
                fields=[
                    CanonicalField(
                        name="accountId",
                        type=CanonicalFieldType.STRING,
                        is_id=True,
                        required=True,
                        server_generated_id=True,
                    ),
                    field,
                ],
            )
        ],
    )

    with pytest.raises(ValueError, match=message):
        emit_sql_files(
            metadata=metadata,
            target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
            output_dir=tmp_path / f"SqlApp{field.name}",
            source_manifest="test",
            generation_run_id="sql-unsafe-defaults",
        )


def test_no_flyway_when_profile_disables_it(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    metadata.target_profile = "springboot-test-no-flyway"
    TARGET_PROFILES[metadata.target_profile] = TargetProfile(
        name=metadata.target_profile,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=True,
        supports_xml=True,
    )

    try:
        output_dir = tmp_path / "BuiltAppNoFlyway"
        generate_application(metadata, output_dir, generation_run_id="noflyway-test")
        assert not (
            output_dir / "src/main/resources/db/migration/V1__create_account_table.sql"
        ).exists()
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_no_batch_when_no_handoffs_or_downstream_files(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    metadata.contracts = [
        contract
        for contract in metadata.contracts
        if contract.type not in {"staging-table", "file-fixed-width", "file-csv"}
    ]
    metadata.mappings = [
        mapping
        for mapping in metadata.mappings
        if mapping.direction
        not in {
            MappingDirection.CANONICAL_TO_HANDOFF,
            MappingDirection.CANONICAL_TO_DOWNSTREAM,
        }
    ]
    metadata.mapping_reports = [
        report
        for report in metadata.mapping_reports
        if report.direction
        not in {
            MappingDirection.CANONICAL_TO_HANDOFF,
            MappingDirection.CANONICAL_TO_DOWNSTREAM,
        }
    ]

    output_dir = tmp_path / "BuiltAppNoBatch"
    generate_application(metadata, output_dir, generation_run_id="nobatch-test")
    assert not (
        output_dir
        / "src/main/java/com/appbuilder/accounts/batch/AccountEodBatchJob.java"
    ).exists()


def test_no_file_writer_when_no_fixed_width_contract(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    metadata.contracts = [
        contract for contract in metadata.contracts if contract.type != "file-fixed-width"
    ]
    metadata.mappings = [
        mapping
        for mapping in metadata.mappings
        if mapping.direction != MappingDirection.CANONICAL_TO_DOWNSTREAM
    ]
    metadata.mapping_reports = [
        report
        for report in metadata.mapping_reports
        if report.direction != MappingDirection.CANONICAL_TO_DOWNSTREAM
    ]

    output_dir = tmp_path / "BuiltAppNoFileWriter"
    generate_application(metadata, output_dir, generation_run_id="nofilewriter-test")
    assert not (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/outbound/AccountEodHandoffFileWriter.java"
    ).exists()


def test_file_writer_renders_fixed_width_padding_and_truncation(tmp_path: Path) -> None:
    metadata = build_metadata_project("examples/input-projects/xyz-accounts-modernization/app-definition.yaml")

    output_dir = tmp_path / "BuiltAppFixedWidthWriter"
    generate_application(
        metadata,
        output_dir,
        source_manifest="examples/input-projects/xyz-accounts-modernization/app-definition.yaml",
        generation_run_id="fixed-width-writer-test",
    )
    writer_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/outbound/AccountEodHandoffFileWriter.java"
    ).read_text(encoding="utf-8")

    assert "// TODO: apply fixed-width layout padding and truncation" not in writer_source
    assert "private String padRight(String value, int width)" in writer_source
    assert "padRight(stringValue(account.getAccountId()), 12)" in writer_source
    assert "padRight(stringValue(account.getCustomerId()), 12)" in writer_source
    assert "padRight(stringValue(account.getStatus()), 10)" in writer_source
    assert "LinkedHashMap" not in writer_source
    assert '" ".repeat(' in writer_source


def test_generated_file_headers_present(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "BuiltAppHeaders", generation_run_id="header-test")

    valid_prefixes = (
        "// Generated by EdgeForge",
        "-- Generated by EdgeForge",
        "# Generated by EdgeForge",
        "<!-- Generated by EdgeForge -->",
    )
    for path in report.files_created:
        if path.name == "generation-provenance.json":
            assert json.loads(path.read_text(encoding="utf-8")) == {
                "provenance_schema_version": "1.0", "framework": "spring-boot",
                "spring_boot_version": "4.1.1",
                "dependency_policy": "ef-v5-maven-1",
            }
            continue
        if path.name == "schema-baseline.json":
            baseline = json.loads(path.read_text(encoding="utf-8"))
            assert baseline["baseline_schema_version"] == "1.0"
            assert baseline["manifest_schema_version"] == "2.0"
            continue
        content = path.read_text(encoding="utf-8")
        first_line = content.splitlines()[0]
        assert first_line.startswith(valid_prefixes)
        assert "Manifest schema version: 2.0" in content


def test_demo_ui_generated_for_xyz_accounts(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()

    output_dir = tmp_path / "BuiltAppUi"
    generate_application(metadata, output_dir, generation_run_id="ui-test")

    assert (output_dir / "src/main/resources/static/index.html").exists()


def test_demo_ui_contains_operation_name(tmp_path: Path) -> None:
    # operator dashboard shows entity names in nav + CRUD panels, not "Try it — opName"
    xyz_metadata = _load_xyz_metadata()
    xyz_output = tmp_path / "BuiltAppUiAccounts"
    generate_application(xyz_metadata, xyz_output, generation_run_id="ui-op-accounts")
    xyz_html = (xyz_output / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    loans_metadata = _load_loans_metadata()
    loans_metadata.target_profile = "springboot-legacy-compatible"
    loans_output = tmp_path / "BuiltAppUiLoans"
    generate_application(loans_metadata, loans_output, generation_run_id="ui-op-loans")
    loans_html = (loans_output / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    # New dashboard: entity name appears in sidebar nav and panel headings
    assert "Account" in xyz_html
    assert "Loan" in loans_html


def test_demo_ui_contains_form_fields(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()

    output_dir = tmp_path / "BuiltAppUiFields"
    generate_application(metadata, output_dir, generation_run_id="ui-fields")
    html_content = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    # ids are namespaced per operation to prevent duplicate ids across multi-entity forms
    for field_name in ["customerId", "accountType", "currency"]:
        assert f'id="createAccount-{field_name}"' in html_content


def test_demo_ui_renders_allowed_values_as_select(tmp_path: Path) -> None:
    metadata = _load_loans_metadata()
    metadata.target_profile = "springboot-legacy-compatible"

    output_dir = tmp_path / "BuiltAppUiAllowedValues"
    generate_application(metadata, output_dir, generation_run_id="ui-select")
    html_content = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    # id is namespaced per operation to prevent duplicate ids across multi-entity forms
    assert '<select id="openLoan-loanType"' in html_content
    for option in ["PERSONAL", "MORTGAGE", "AUTO", "BUSINESS"]:
        assert f'<option value="{option}"' in html_content


def test_demo_ui_applies_phase_a_input_constraints(tmp_path: Path) -> None:
    metadata = _load_loans_metadata()
    metadata.target_profile = "springboot-legacy-compatible"
    fields = {field.name: field for field in metadata.entities[0].fields}
    fields["borrowerId"].min_length = 5
    fields["borrowerId"].pattern = "^[A-Z0-9-]+$"
    fields["principalAmount"].range_min = 0.01
    fields["principalAmount"].range_max = 999999.99

    output_dir = tmp_path / "BuiltAppUiConstraints"
    generate_application(metadata, output_dir, generation_run_id="ui-constraints")
    html_content = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="openLoan-borrowerId"' in html_content
    assert 'minlength="5"' in html_content
    assert 'pattern="^[A-Z0-9-]+$"' in html_content
    assert 'id="openLoan-principalAmount"' in html_content
    assert 'min="0.01"' in html_content
    assert 'max="999999.99"' in html_content


def test_demo_ui_does_not_apply_staging_length_to_identifier_reference_inputs(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()

    output_dir = tmp_path / "BuiltAppUiIdentifierLengths"
    generate_application(metadata, output_dir, generation_run_id="ui-id-lengths")
    html_content = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="createAccount-customerId"' in html_content
    assert 'id="createAccount-customerId" name="createAccount-customerId" type="text" required' in html_content
    assert 'id="createAccount-customerId" name="createAccount-customerId" type="text" maxlength="20"' not in html_content


def test_security_config_generated_when_emit_security_true(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata_with_profile(
        "springboot-test-security-on",
        emit_security=True,
    )

    try:
        output_dir = tmp_path / "BuiltAppSecurityOn"
        generate_application(metadata, output_dir, generation_run_id="security-on")
        assert (
            output_dir
            / "src/main/java/com/appbuilder/accounts/config/SecurityConfig.java"
        ).exists()
        pom_xml = (output_dir / "pom.xml").read_text(encoding="utf-8")
        application_yaml = (
            output_dir / "src/main/resources/application.yaml"
        ).read_text(encoding="utf-8")
        assert "spring-boot-starter-oauth2-resource-server" in pom_xml
        assert "issuer-uri:" in application_yaml
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_security_config_not_generated_when_emit_security_false(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()

    output_dir = tmp_path / "BuiltAppSecurityOff"
    generate_application(metadata, output_dir, generation_run_id="security-off")
    assert not (
        output_dir
        / "src/main/java/com/appbuilder/accounts/config/SecurityConfig.java"
    ).exists()


def test_security_config_permits_actuator_health(tmp_path: Path) -> None:
    security_source = _generate_security_config_source(tmp_path, "security-health")

    assert '.requestMatchers("/actuator/health").permitAll()' in security_source
    assert '"/", "/index.html"' not in security_source
    assert "SessionCreationPolicy.STATELESS" in security_source


def test_security_config_requires_auth_for_api_endpoints(tmp_path: Path) -> None:
    security_source = _generate_security_config_source(tmp_path, "security-auth")

    assert ".anyRequest().authenticated()" in security_source
    assert ".oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));" in security_source


def test_shipped_profile_security_posture_matrix_is_explicit_and_closed() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "from appbuilder.target_profiles.catalog import TARGET_PROFILES; "
                "print(json.dumps({name: {"
                "'emit_security': profile.emit_security, "
                "'emit_test_console': profile.emit_test_console} "
                "for name, profile in TARGET_PROFILES.items()}, sort_keys=True))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(probe.stdout) == {
        "springboot-legacy-compatible": {
            "emit_security": False,
            "emit_test_console": True,
        },
        "springboot-enterprise-postgres-java17": {
            "emit_security": False,
            "emit_test_console": False,
        },
        "springboot-standard-enterprise": {
            "emit_security": False,
            "emit_test_console": False,
        },
    }


def test_enterprise_profiles_omit_test_console_and_demo_controller(tmp_path: Path) -> None:
    for profile_name in (
        "springboot-enterprise-postgres-java17",
        "springboot-standard-enterprise",
    ):
        metadata = _load_xyz_metadata()
        metadata.target_profile = profile_name
        output_dir = tmp_path / profile_name

        generate_application(
            metadata,
            output_dir,
            generation_run_id=f"{profile_name}-console-policy",
        )

        assert not (output_dir / "src/main/resources/static/index.html").exists()
        assert not (
            output_dir
            / "src/main/java/com/appbuilder/accounts/adapter/inbound/DemoController.java"
        ).exists()
        readme = (output_dir / "README.md").read_text(encoding="utf-8")
        assert "The non-production test console is not emitted in this generated app." in readme
        agent_context = (output_dir / "agent-context.md").read_text(encoding="utf-8")
        assert "Demo/live-data endpoints" not in agent_context


def test_legacy_profile_retains_local_only_test_console(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "legacy-local-console"

    generate_application(
        metadata,
        output_dir,
        generation_run_id="legacy-local-console",
    )

    assert (output_dir / "src/main/resources/static/index.html").exists()
    assert (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/DemoController.java"
    ).exists()
    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "The non-production test console is emitted for local development only." in readme
    assert "Do not expose it to an untrusted network." in readme
    agent_context = (output_dir / "agent-context.md").read_text(encoding="utf-8")
    assert "Demo/live-data endpoints are gated" in agent_context


def test_secured_custom_profile_documents_authenticated_console(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata_with_profile(
        "springboot-test-secured-console",
        emit_security=True,
        emit_test_console=True,
    )
    try:
        output_dir = tmp_path / "secured-console"
        generate_application(
            metadata,
            output_dir,
            generation_run_id="secured-console",
        )

        assert (output_dir / "src/main/resources/static/index.html").exists()
        readme = (output_dir / "README.md").read_text(encoding="utf-8")
        assert "requires authentication" in readme
        assert "generated OAuth2 resource-server configuration" in readme
        assert "OAuth2 resource-server security skeleton" in readme
        assert "no built-in authentication" not in readme
        assert "unauthenticated by design" not in readme
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_console_enabled_profile_without_actions_documents_non_emission(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata_with_profile(
        "springboot-test-console-without-actions",
        emit_test_console=True,
    )
    metadata.operations = []
    metadata.contracts = []
    metadata.mappings = []
    try:
        output_dir = tmp_path / "console-without-actions"
        generate_application(
            metadata,
            output_dir,
            generation_run_id="console-without-actions",
        )

        assert not (output_dir / "src/main/resources/static/index.html").exists()
        readme = (output_dir / "README.md").read_text(encoding="utf-8")
        assert "The non-production test console is not emitted in this generated app." in readme
        agent_context = (output_dir / "agent-context.md").read_text(encoding="utf-8")
        assert "Demo/live-data endpoints" not in agent_context
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_regeneration_to_enterprise_profile_prunes_generated_test_console(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    _jobless_ownership_fixture(metadata)
    output_dir = tmp_path / "console-profile-transition"
    generate_application(metadata, output_dir, generation_run_id="local-console")

    console_path = output_dir / "src/main/resources/static/index.html"
    controller_path = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/DemoController.java"
    )
    assert console_path.exists()
    assert controller_path.exists()

    metadata.target_profile = "springboot-enterprise-postgres-java17"
    report = generate_application(metadata, output_dir, generation_run_id="enterprise-console")

    assert report.generation_mode == "regenerate"
    assert not console_path.exists()
    assert not controller_path.exists()
    assert any(
        "generated test-console artifact pruned" in warning
        for warning in report.warnings
    )


def test_legacy_transition_archives_console_outside_packaged_resources(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    _jobless_ownership_fixture(metadata)
    output_dir = tmp_path / "legacy-console-profile-transition"
    generate_application(metadata, output_dir, generation_run_id="legacy-local-console")

    baseline_path = output_dir / "db/schema-baseline.json"
    baseline_path.unlink()
    console_path = output_dir / "src/main/resources/static/index.html"
    legacy_console = console_path.read_text(encoding="utf-8").replace(
        "<!-- EdgeForge-ownership: generated -->\n",
        "",
    )
    console_path.write_text(legacy_console, encoding="utf-8")

    metadata.target_profile = "springboot-enterprise-postgres-java17"
    report = generate_application(
        metadata,
        output_dir,
        generation_run_id="legacy-enterprise-console",
    )

    archive_path = (
        output_dir
        / ".edgeforge-backups/src/main/resources/static/index.html.legacy.bak"
    )
    resource_root = output_dir / "src/main/resources"
    assert report.generation_mode == "legacy"
    assert archive_path.read_text(encoding="utf-8") == legacy_console
    assert not console_path.exists()
    assert not list(resource_root.rglob("index.html*"))
    assert not any(
        "NON-PRODUCTION TEST CONSOLE" in path.read_text(encoding="utf-8", errors="ignore")
        for path in resource_root.rglob("*")
        if path.is_file()
    )


def test_audit_config_generated_when_emit_audit_true(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata_with_profile(
            "springboot-test-audit-on",
            emit_security=True,
            emit_audit=True,
    )
    try:
        output_dir = tmp_path / "BuiltAppAuditOn"
        generate_application(
            metadata,
            output_dir,
            generation_run_id="audit-on",
        )

        audit_config = (
            output_dir
            / "src/main/java/com/appbuilder/accounts/config/AuditConfig.java"
        ).read_text(encoding="utf-8")
        assert "@EnableJpaAuditing" in audit_config
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_audit_config_not_generated_when_emit_audit_false(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltAppAuditOff"
    generate_application(metadata, output_dir, generation_run_id="audit-off")
    assert not (
        output_dir
        / "src/main/java/com/appbuilder/accounts/config/AuditConfig.java"
    ).exists()


def test_entity_has_audit_fields_when_emit_audit_true(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata_with_profile(
            "springboot-test-audit-entity",
            emit_security=True,
            emit_audit=True,
    )
    try:
        output_dir = tmp_path / "BuiltAppAuditEntity"
        generate_application(
            metadata,
            output_dir,
            generation_run_id="audit-entity",
        )
        entity_source = (
            output_dir
            / "src/main/java/com/appbuilder/accounts/domain/Account.java"
        ).read_text(encoding="utf-8")

        assert "@EntityListeners(AuditingEntityListener.class)" in entity_source
        assert "private String createdBy;" in entity_source
        assert "private LocalDateTime createdAt;" in entity_source
        assert "private String modifiedBy;" in entity_source
        assert "private LocalDateTime modifiedAt;" in entity_source
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_flyway_migration_has_audit_columns_when_emit_audit_true(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata_with_profile(
            "springboot-test-audit-sql",
            emit_security=True,
            emit_audit=True,
    )
    try:
        output_dir = tmp_path / "BuiltAppAuditSql"
        generate_application(
            metadata,
            output_dir,
            generation_run_id="audit-sql",
        )
        migration = (
            output_dir
            / "src/main/resources/db/migration/V1__create_account_table.sql"
        ).read_text(encoding="utf-8")

        assert "created_by VARCHAR(255)" in migration
        assert "created_at TIMESTAMP" in migration
        assert "modified_by VARCHAR(255)" in migration
        assert "modified_at TIMESTAMP" in migration
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_audit_config_no_security_imports_when_emit_security_false(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata_with_profile(
        "springboot-test-audit-no-security",
        emit_audit=True,
    )
    try:
        output_dir = tmp_path / "BuiltAppAuditNoSecurity"
        generate_application(
            metadata,
            output_dir,
            generation_run_id="audit-no-security",
        )
        audit_config = (
            output_dir
            / "src/main/java/com/appbuilder/accounts/config/AuditConfig.java"
        ).read_text(encoding="utf-8")

        assert "SecurityContextHolder" not in audit_config
        assert "Authentication" not in audit_config
        assert 'Optional.of("system")' in audit_config
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_audit_field_merge_when_business_field_collides(tmp_path: Path) -> None:
    metadata = _build_audit_collision_metadata(
        "springboot-test-audit-created-at-collision",
        collision_fields=[
            CanonicalField(
                name="createdAt",
                type=CanonicalFieldType.DATETIME,
                required=False,
                source_paths=["ledger-api.createLedgerEntry.response.createdAt"],
            ),
        ],
    )

    try:
        output_dir = tmp_path / "BuiltAppAuditCollisionCreatedAt"
        generate_application(
            metadata,
            output_dir,
            generation_run_id="audit-created-at-collision",
        )

        entity_source = (
            output_dir
            / "src/main/java/com/appbuilder/accounts/domain/LedgerEntry.java"
        ).read_text(encoding="utf-8")
        migration = (
            output_dir
            / "src/main/resources/db/migration/V1__create_ledger_entry_table.sql"
        ).read_text(encoding="utf-8")

        assert entity_source.count("private LocalDateTime createdAt;") == 1
        assert '@CreatedDate\n    @Column(name = "created_at")\n    private LocalDateTime createdAt;' in entity_source
        assert entity_source.count("private String createdBy;") == 1
        assert entity_source.count("private String modifiedBy;") == 1
        assert entity_source.count("private LocalDateTime modifiedAt;") == 1
        assert migration.count("created_at TIMESTAMP") == 1
        assert migration.count("created_by VARCHAR(255)") == 1
        assert migration.count("modified_by VARCHAR(255)") == 1
        assert migration.count("modified_at TIMESTAMP") == 1
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_all_four_audit_fields_merge_when_all_collide(tmp_path: Path) -> None:
    metadata = _build_audit_collision_metadata(
        "springboot-test-audit-all-collisions",
        collision_fields=[
            CanonicalField(
                name="createdBy",
                type=CanonicalFieldType.STRING,
                required=False,
                max_length=64,
                source_paths=["ledger-api.createLedgerEntry.response.createdBy"],
            ),
            CanonicalField(
                name="createdAt",
                type=CanonicalFieldType.DATETIME,
                required=False,
                source_paths=["ledger-api.createLedgerEntry.response.createdAt"],
            ),
            CanonicalField(
                name="modifiedBy",
                type=CanonicalFieldType.STRING,
                required=False,
                max_length=64,
                source_paths=["ledger-api.createLedgerEntry.response.modifiedBy"],
            ),
            CanonicalField(
                name="modifiedAt",
                type=CanonicalFieldType.DATETIME,
                required=False,
                source_paths=["ledger-api.createLedgerEntry.response.modifiedAt"],
            ),
        ],
    )

    try:
        output_dir = tmp_path / "BuiltAppAuditCollisionAll"
        generate_application(
            metadata,
            output_dir,
            generation_run_id="audit-all-collisions",
        )

        entity_source = (
            output_dir
            / "src/main/java/com/appbuilder/accounts/domain/LedgerEntry.java"
        ).read_text(encoding="utf-8")
        migration = (
            output_dir
            / "src/main/resources/db/migration/V1__create_ledger_entry_table.sql"
        ).read_text(encoding="utf-8")

        assert entity_source.count("private String createdBy;") == 1
        assert entity_source.count("private LocalDateTime createdAt;") == 1
        assert entity_source.count("private String modifiedBy;") == 1
        assert entity_source.count("private LocalDateTime modifiedAt;") == 1
        assert entity_source.count("@CreatedBy") == 1
        assert entity_source.count("@CreatedDate") == 1
        assert entity_source.count("@LastModifiedBy") == 1
        assert entity_source.count("@LastModifiedDate") == 1
        assert migration.count("created_by VARCHAR(64)") == 1
        assert migration.count("created_at TIMESTAMP") == 1
        assert migration.count("modified_by VARCHAR(64)") == 1
        assert migration.count("modified_at TIMESTAMP") == 1
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_springboot_standard_enterprise_emits_audit_by_default(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    profile = TARGET_PROFILES["springboot-standard-enterprise"]
    metadata.target_profile = profile.name

    output_dir = tmp_path / "BuiltAppStandardEnterpriseAudit"
    generate_application(
        metadata,
        output_dir,
        generation_run_id="standard-enterprise-audit",
    )

    audit_config = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/config/AuditConfig.java"
    ).read_text(encoding="utf-8")
    entity_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    ).read_text(encoding="utf-8")
    migration = (
        output_dir
        / "src/main/resources/db/migration/V1__create_account_table.sql"
    ).read_text(encoding="utf-8")

    assert profile.emit_audit is True
    assert "@EnableJpaAuditing" in audit_config
    assert '// NOTE: emit_security=False — auditorProvider will return "system"' in audit_config
    assert "@CreatedBy" in entity_source
    assert "@CreatedDate" in entity_source
    assert "@LastModifiedBy" in entity_source
    assert "@LastModifiedDate" in entity_source
    assert "private String createdBy;" in entity_source
    assert "private LocalDateTime createdAt;" in entity_source
    assert "private String modifiedBy;" in entity_source
    assert "private LocalDateTime modifiedAt;" in entity_source
    assert "created_by VARCHAR(255)" in migration
    assert "created_at TIMESTAMP" in migration
    assert "modified_by VARCHAR(255)" in migration
    assert "modified_at TIMESTAMP" in migration


def test_springboot_legacy_compatible_does_not_emit_audit(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    profile = TARGET_PROFILES["springboot-legacy-compatible"]
    metadata.target_profile = profile.name

    output_dir = tmp_path / "BuiltAppLegacyCompatibleNoAudit"
    generate_application(
        metadata,
        output_dir,
        generation_run_id="legacy-compatible-no-audit",
    )

    entity_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    ).read_text(encoding="utf-8")
    migration = (
        output_dir
        / "src/main/resources/db/migration/V1__create_account_table.sql"
    ).read_text(encoding="utf-8")

    assert profile.emit_audit is False
    assert not (
        output_dir
        / "src/main/java/com/appbuilder/accounts/config/AuditConfig.java"
    ).exists()
    assert "private String createdBy;" not in entity_source
    assert "private LocalDateTime createdAt;" not in entity_source
    assert "created_by VARCHAR(255)" not in migration
    assert "created_at TIMESTAMP" not in migration


def _load_xyz_metadata() -> MetadataProject:
    payload = json.loads(
        Path("tests/golden_contracts/xyz_accounts_metadata.json").read_text(encoding="utf-8")
    )
    return MetadataProject.model_validate(copy.deepcopy(payload))


def _load_loans_metadata() -> MetadataProject:
    project = load_project_definition(
        "examples/input-projects/loans-modernization/app-definition.yaml"
    )
    return translate_project(project)


def _pageable_list_metadata(*, pageable: bool) -> MetadataProject:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=[
                    "crm-account-api.createAccount.response.accountId",
                    "crm-account-api.listAccounts.response.accountId",
                ],
            ),
            CanonicalField(
                name="accountName",
                type=CanonicalFieldType.STRING,
                source_paths=[
                    "crm-account-api.createAccount.request.accountName",
                    "crm-account-api.listAccounts.response.accountName",
                ],
            ),
        ],
    )
    create_operation = CanonicalOperation(
        name="createAccount",
        interface_name="crm-account-api",
        request_entity="Account",
        response_entity="Account",
        http_method=HttpMethod.POST,
        response_shape=ResponseShape.CREATED,
    )
    list_operation = CanonicalOperation(
        name="listAccounts",
        interface_name="crm-account-api",
        request_entity="Account",
        response_entity="Account",
        http_method=HttpMethod.GET,
        response_shape=ResponseShape.LIST,
        pageable=pageable,
    )
    return MetadataProject(
        app_name="Accounts",
        bounded_context="accounts",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[ContractMetadata(name="crm-account-api", type="rest-json", source="")],
        operations=[create_operation, list_operation],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-account-api",
                operation_name="createAccount",
                source_path="crm-account-api.createAccount.request.accountName",
                target_path="Account.accountName",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-account-api",
                operation_name="createAccount",
                source_path="crm-account-api.createAccount.response.accountId",
                target_path="Account.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-account-api",
                operation_name="listAccounts",
                source_path="crm-account-api.listAccounts.response.accountId",
                target_path="Account.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="crm-account-api",
                operation_name="listAccounts",
                source_path="crm-account-api.listAccounts.response.accountName",
                target_path="Account.accountName",
            ),
        ],
    )


def _generate_security_config_source(tmp_path: Path, run_id: str) -> str:
    metadata = _load_xyz_metadata_with_profile(
        "springboot-test-security-enabled",
        emit_security=True,
    )

    try:
        output_dir = tmp_path / run_id
        generate_application(metadata, output_dir, generation_run_id=run_id)
        return (
            output_dir
            / "src/main/java/com/appbuilder/accounts/config/SecurityConfig.java"
        ).read_text(encoding="utf-8")
    finally:
        TARGET_PROFILES.pop(metadata.target_profile, None)


def test_multi_entity_produces_separate_domain_classes(tmp_path: Path) -> None:
    """Two entities → two domain Java files, two controllers, service pairs, two repos."""
    metadata = _two_entity_metadata()

    report = generate_application(metadata, tmp_path / "MultiEntityApp", generation_run_id="multi-test")

    created = {p.relative_to(report.output_dir).as_posix() for p in report.files_created}
    pkg = "src/main/java/com/appbuilder/crm"
    assert f"{pkg}/domain/Customer.java" in created
    assert f"{pkg}/domain/Account.java" in created
    assert f"{pkg}/repository/CustomerRepository.java" in created
    assert f"{pkg}/repository/AccountRepository.java" in created
    assert f"{pkg}/adapter/inbound/CustomerController.java" in created
    assert f"{pkg}/adapter/inbound/AccountController.java" in created
    assert f"{pkg}/service/CustomerServiceBase.java" in created
    assert f"{pkg}/service/AccountServiceBase.java" in created
    assert f"{pkg}/service/CustomerService.java" in created
    assert f"{pkg}/service/AccountService.java" in created
    # One application class — not two
    assert f"{pkg}/CrmApplication.java" in created
    assert sum(1 for p in created if p.endswith("Application.java")) == 1


def test_multi_entity_produces_versioned_flyway_migrations(tmp_path: Path) -> None:
    """Two entities → V1 for first entity, V2 for second; no V1 for second entity."""
    metadata = _two_entity_metadata()
    output_dir = tmp_path / "MultiEntityApp"

    generate_application(metadata, output_dir, generation_run_id="flyway-test")

    migration_dir = output_dir / "src" / "main" / "resources" / "db" / "migration"
    assert (migration_dir / "V1__create_customer_table.sql").exists()
    assert (migration_dir / "V2__create_account_table.sql").exists()
    assert not (migration_dir / "V1__create_account_table.sql").exists()


def test_single_entity_migration_filename_unchanged(tmp_path: Path) -> None:
    """Single-entity project still produces V1__create_X_table.sql — backward compatible.
    xyz project also produces V2 for its staging DDL, so count is 2.
    """
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "SingleEntityApp"

    generate_application(metadata, output_dir, generation_run_id="single-flyway-test")

    migration_dir = output_dir / "src" / "main" / "resources" / "db" / "migration"
    assert (migration_dir / "V1__create_account_table.sql").exists()
    # V2 is now emitted for the staging table DDL from data-handoffs spec
    assert (migration_dir / "V2__create_acct_staging_tbl_table.sql").exists()
    assert {p.name for p in migration_dir.glob("V*.sql")} == {
        "V1__create_account_table.sql", "V2__create_acct_staging_tbl_table.sql",
        "V3__create_pkg_batch_metadata.sql",
    }


def test_regeneration_replaces_stale_generated_migrations(tmp_path: Path) -> None:
    output_dir = tmp_path / "RegeneratedApp"

    initial_metadata = _two_entity_metadata()
    target_profile = TARGET_PROFILES[initial_metadata.target_profile]
    emit_sql_files(
        metadata=initial_metadata,
        target_profile=target_profile,
        output_dir=output_dir,
        source_manifest="test-manifest.yaml",
        generation_run_id="regen-initial",
    )

    migration_dir = output_dir / "src" / "main" / "resources" / "db" / "migration"
    assert (migration_dir / "V2__create_account_table.sql").exists()

    regenerated_metadata = MetadataProject.model_validate(
        {
            **initial_metadata.model_dump(mode="json"),
            "entities": [
                {
                    "name": "Customer",
                    "fields": [
                        {
                            "name": "customerId",
                            "type": "string",
                            "is_id": True,
                            "required": True,
                            "server_generated_id": True,
                        },
                        {
                            "name": "customerName",
                            "type": "string",
                            "required": True,
                        },
                    ],
                },
                {
                    "name": "MultiLegPosting",
                    "fields": [
                        {
                            "name": "postingId",
                            "type": "string",
                            "is_id": True,
                            "required": True,
                            "server_generated_id": True,
                        },
                        {
                            "name": "amount",
                            "type": "decimal",
                            "required": True,
                        },
                    ],
                },
            ],
        }
    )

    emit_sql_files(
        metadata=regenerated_metadata,
        target_profile=target_profile,
        output_dir=output_dir,
        source_manifest="test-manifest.yaml",
        generation_run_id="regen-second",
    )

    migration_names = sorted(path.name for path in migration_dir.glob("V*__create_*_table.sql"))
    assert migration_names == [
        "V1__create_customer_table.sql",
        "V2__create_multi_leg_posting_table.sql",
    ]
    assert not (migration_dir / "V2__create_account_table.sql").exists()


def test_regeneration_preserves_manual_create_table_migrations(tmp_path: Path) -> None:
    output_dir = tmp_path / "RegeneratedAppManual"

    metadata = _two_entity_metadata()
    target_profile = TARGET_PROFILES[metadata.target_profile]
    emit_sql_files(
        metadata=metadata,
        target_profile=target_profile,
        output_dir=output_dir,
        source_manifest="test-manifest.yaml",
        generation_run_id="regen-initial",
    )

    migration_dir = output_dir / "src" / "main" / "resources" / "db" / "migration"
    manual_migration = migration_dir / "V9__create_manual_reporting_table.sql"
    manual_migration.write_text(
        "\n".join(
            [
                "-- Manual migration",
                "CREATE TABLE manual_reporting (",
                "    reporting_id VARCHAR(64) PRIMARY KEY",
                ");",
            ]
        ),
        encoding="utf-8",
    )

    emit_sql_files(
        metadata=metadata,
        target_profile=target_profile,
        output_dir=output_dir,
        source_manifest="test-manifest.yaml",
        generation_run_id="regen-second",
    )

    migration_names = sorted(path.name for path in migration_dir.glob("V*__create_*_table.sql"))
    assert migration_names == [
        "V1__create_customer_table.sql",
        "V2__create_account_table.sql",
        "V9__create_manual_reporting_table.sql",
    ]
    assert manual_migration.read_text(encoding="utf-8").startswith("-- Manual migration")


def test_harness_passes_with_multi_entity_generation(tmp_path: Path) -> None:
    """Harness must pass cleanly on a two-entity generated app."""
    metadata = _two_entity_metadata()

    report = generate_application(metadata, tmp_path / "HarnessMulti", generation_run_id="harness-multi")

    assert report.harness_report is not None
    assert report.harness_report.passed, (
        "Harness failed: " + "; ".join(
            f"{c.name}: {c.message}" for c in report.harness_report.checks if not c.passed
        )
    )


def test_all_entities_returns_all() -> None:
    """all_entities() returns every entity in MetadataProject.entities."""
    from appbuilder.generation.utils import all_entities

    metadata = _two_entity_metadata()
    result = all_entities(metadata)

    assert len(result) == 2
    assert {e.name for e in result} == {"Customer", "Account"}


def test_demo_ui_includes_all_entities_summary(tmp_path: Path) -> None:
    """Demo UI HTML contains entity navigation and panels for each entity.
    # upgraded dashboard uses sidebar nav instead of 'Generated Domain Entities' section.
    """
    metadata = _two_entity_metadata()
    output_dir = tmp_path / "UIMultiEntity"

    generate_application(metadata, output_dir, generation_run_id="ui-multi-test")

    ui_content = (output_dir / "src" / "main" / "resources" / "static" / "index.html").read_text(encoding="utf-8")
    # Both entity names appear as sidebar nav items and entity panel headings
    assert 'data-entity="Customer"' in ui_content
    assert 'data-entity="Account"' in ui_content
    assert "Customer" in ui_content
    assert "Account" in ui_content


def test_application_yaml_uses_bounded_context_as_db_name(tmp_path: Path) -> None:
    """Legacy-compatible profile uses bounded_context in the default H2 datasource URL."""
    metadata = _two_entity_metadata()
    output_dir = tmp_path / "DbNameApp"

    generate_application(metadata, output_dir, generation_run_id="dbname-test")

    app_yaml = (output_dir / "src" / "main" / "resources" / "application.yaml").read_text(encoding="utf-8")
    assert "jdbc:h2:mem:crm;" in app_yaml
    assert "jdbc:h2:mem:customer;" not in app_yaml
    assert "jdbc:h2:mem:account;" not in app_yaml


def test_springboot_standard_enterprise_emits_postgres_datasource_without_credential_defaults(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    profile = TARGET_PROFILES["springboot-standard-enterprise"]
    metadata.target_profile = profile.name

    output_dir = tmp_path / "BuiltAppStandardEnterprisePostgres"
    generate_application(
        metadata,
        output_dir,
        generation_run_id="standard-enterprise-postgres",
    )

    app_yaml = (
        output_dir / "src/main/resources/application.yaml"
    ).read_text(encoding="utf-8")
    pom_xml = (output_dir / "pom.xml").read_text(encoding="utf-8")
    credential_config = (
        output_dir / "src/main/java/com/appbuilder/accounts/config/DatasourceCredentialConfig.java"
    ).read_text(encoding="utf-8")

    assert profile.runtime_database_dependency == "postgresql"
    assert "jdbc:postgresql://localhost:5432/accounts" in app_yaml
    assert "driver-class-name: org.postgresql.Driver" in app_yaml
    assert "username: ${SPRING_DATASOURCE_USERNAME}" in app_yaml
    assert "password: ${SPRING_DATASOURCE_PASSWORD}" in app_yaml
    assert ("SPRING_DATASOURCE_USERNAME" + ":postgres") not in app_yaml
    assert ("SPRING_DATASOURCE_PASSWORD" + ":postgres") not in app_yaml
    assert "implements BeanFactoryPostProcessor, EnvironmentAware" in credential_config
    assert 'environment.getProperty("SPRING_DATASOURCE_USERNAME")' in credential_config
    assert 'environment.getProperty("SPRING_DATASOURCE_PASSWORD")' in credential_config
    assert "must be set for enterprise PostgreSQL profiles" in credential_config
    assert "com.h2database" not in pom_xml
    assert "<groupId>org.postgresql</groupId>" in pom_xml
    assert "<artifactId>postgresql</artifactId>" in pom_xml
    assert "<artifactId>spring-boot-starter-flyway</artifactId>" in pom_xml
    assert "<artifactId>flyway-database-postgresql</artifactId>" in pom_xml


def test_springboot_enterprise_postgres_java17_emits_postgres_datasource_without_credential_defaults(
    tmp_path: Path,
) -> None:
    metadata = _load_xyz_metadata()
    profile = TARGET_PROFILES["springboot-enterprise-postgres-java17"]
    metadata.target_profile = profile.name

    output_dir = tmp_path / "BuiltAppEnterprisePostgresJava17"
    generate_application(
        metadata,
        output_dir,
        generation_run_id="enterprise-postgres-java17",
    )

    app_yaml = (
        output_dir / "src/main/resources/application.yaml"
    ).read_text(encoding="utf-8")
    pom_xml = (output_dir / "pom.xml").read_text(encoding="utf-8")
    dockerfile = (output_dir / "Dockerfile").read_text(encoding="utf-8")
    credential_config = (
        output_dir / "src/main/java/com/appbuilder/accounts/config/DatasourceCredentialConfig.java"
    ).read_text(encoding="utf-8")

    assert profile.java_baseline == "17"
    assert profile.runtime_database_dependency == "postgresql"
    assert "jdbc:postgresql://localhost:5432/accounts" in app_yaml
    assert "driver-class-name: org.postgresql.Driver" in app_yaml
    assert "username: ${SPRING_DATASOURCE_USERNAME}" in app_yaml
    assert "password: ${SPRING_DATASOURCE_PASSWORD}" in app_yaml
    assert ("SPRING_DATASOURCE_USERNAME" + ":postgres") not in app_yaml
    assert ("SPRING_DATASOURCE_PASSWORD" + ":postgres") not in app_yaml
    assert "implements BeanFactoryPostProcessor, EnvironmentAware" in credential_config
    assert 'environment.getProperty("SPRING_DATASOURCE_USERNAME")' in credential_config
    assert 'environment.getProperty("SPRING_DATASOURCE_PASSWORD")' in credential_config
    assert "must be set for enterprise PostgreSQL profiles" in credential_config
    assert "<java.version>17</java.version>" in pom_xml
    assert "<groupId>org.postgresql</groupId>" in pom_xml
    assert "<artifactId>postgresql</artifactId>" in pom_xml
    assert "<artifactId>spring-boot-starter-flyway</artifactId>" in pom_xml
    assert "<artifactId>flyway-database-postgresql</artifactId>" in pom_xml
    assert "com.h2database" not in pom_xml
    from appbuilder.generation.container_policy import base_references
    build_base, runtime_base = base_references("17")
    assert f"FROM {build_base} AS build" in dockerfile
    assert f"FROM {runtime_base}" in dockerfile
    assert (
        output_dir / "src/main/java/com/appbuilder/accounts/config/AuditConfig.java"
    ).exists()


def test_springboot_legacy_compatible_keeps_h2_datasource_by_default(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    profile = TARGET_PROFILES["springboot-legacy-compatible"]
    metadata.target_profile = profile.name

    output_dir = tmp_path / "BuiltAppLegacyCompatibleH2"
    generate_application(
        metadata,
        output_dir,
        generation_run_id="legacy-compatible-h2",
    )

    app_yaml = (
        output_dir / "src/main/resources/application.yaml"
    ).read_text(encoding="utf-8")
    pom_xml = (output_dir / "pom.xml").read_text(encoding="utf-8")

    assert profile.runtime_database_dependency == "h2"
    assert "jdbc:h2:mem:accounts;" in app_yaml
    assert "driver-class-name: org.h2.Driver" in app_yaml
    assert "username: sa" in app_yaml
    assert "password:" in app_yaml
    assert not (
        output_dir / "src/main/java/com/appbuilder/accounts/config/DatasourceCredentialConfig.java"
    ).exists()
    assert "org.postgresql" not in pom_xml
    assert "<groupId>com.h2database</groupId>" in pom_xml
    assert "<artifactId>h2</artifactId>" in pom_xml


def test_demo_ui_field_ids_are_namespaced_per_operation(tmp_path: Path) -> None:
    """C1: Field DOM ids are namespaced with the operation name to prevent duplicate ids across forms."""
    metadata = _two_entity_metadata()
    output_dir = tmp_path / "UINamespaceTest"

    generate_application(metadata, output_dir, generation_run_id="c1-test")

    html_content = (output_dir / "src" / "main" / "resources" / "static" / "index.html").read_text(encoding="utf-8")

    # Customer fields prefixed with createCustomer-
    assert 'id="createCustomer-customerName"' in html_content

    # Account fields prefixed with createAccount-
    assert 'id="createAccount-accountType"' in html_content

    # No un-namespaced ids for shared-name fields
    assert 'id="customerName"' not in html_content
    assert 'id="accountType"' not in html_content


def test_multi_entity_batch_jobs_emitted_per_entity(tmp_path: Path) -> None:
    """C2: One EodBatchJob is emitted for each entity that has staging-table handoffs."""
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        CanonicalOperation,
        ContractMetadata,
        SystemParticipant,
    )

    # Build a two-entity metadata where BOTH entities have staging-table handoffs
    entity_a = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=12),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True, max_length=50),
        ],
    )
    entity_b = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=12),
            CanonicalField(name="balance", type=CanonicalFieldType.DECIMAL, required=False),
        ],
    )

    op_a = CanonicalOperation(name="createCustomer", interface_name="crm-api", request_entity="Customer", response_entity="Customer")
    op_b = CanonicalOperation(name="createAccount", interface_name="crm-api", request_entity="Account", response_entity="Account")

    mappings = [
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createCustomer", source_path="crm-api.createCustomer.request.customerName", target_path="Customer.customerName"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createAccount", source_path="crm-api.createAccount.request.balance", target_path="Account.balance"),
        # Staging handoffs for BOTH entities
        FieldMapping(direction=MappingDirection.CANONICAL_TO_HANDOFF, contract_name="crm-staging", operation_name="stageCustomer", source_path="Customer.customerName", target_path="crm-staging.stageCustomer.customer_name"),
        FieldMapping(direction=MappingDirection.CANONICAL_TO_HANDOFF, contract_name="crm-staging", operation_name="stageAccount", source_path="Account.balance", target_path="crm-staging.stageAccount.balance"),
    ]

    profile_name = "springboot-batch-multi"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name, language="java", framework="spring-boot",
        java_baseline="17", spring_boot_baseline="3.3.5",
        emit_flyway=False, emit_spring_batch=True, emit_security=False, emit_audit=False, supports_xml=False,
    )

    from appbuilder.metadata.models import MetadataProject
    metadata = MetadataProject(
        app_name="CRM Batch App",
        bounded_context="crm",
        target_profile=profile_name,
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[
            ContractMetadata(name="crm-api", type="rest-json", source=""),
            ContractMetadata(name="crm-staging", type="staging-table", source=""),
        ],
        operations=[op_a, op_b],
        entities=[entity_a, entity_b],
        mappings=mappings,
    )

    generate_application(metadata, tmp_path / "BatchMultiApp", generation_run_id="c2-test")

    batch_dir = tmp_path / "BatchMultiApp" / "src" / "main" / "java" / "com" / "appbuilder" / "crm" / "batch"

    # One batch job per entity with handoffs
    assert (batch_dir / "CustomerEodBatchJob.java").exists(), "CustomerEodBatchJob.java not generated"
    assert (batch_dir / "AccountEodBatchJob.java").exists(), "AccountEodBatchJob.java not generated"

    # Each job wires its own StagingWriter
    customer_job = (batch_dir / "CustomerEodBatchJob.java").read_text(encoding="utf-8")
    assert "CustomerStagingWriter" in customer_job
    assert "AccountStagingWriter" not in customer_job

    account_job = (batch_dir / "AccountEodBatchJob.java").read_text(encoding="utf-8")
    assert "AccountStagingWriter" in account_job
    assert "CustomerStagingWriter" not in account_job


def test_multi_operation_same_entity_generates_all_dtos_and_one_controller(tmp_path: Path) -> None:
    """E1: When one entity has N upstream operations, generate N DTO pairs + 1 controller + 1 service.

    Reproduces the exact scenario Codex reported: createCustomer + updateCustomer on Customer.
    The backend must emit both DTO pairs and a controller with two @PostMapping methods.
    The demo UI must advertise both forms at the correct (operation-specific) endpoints.
    """
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        CanonicalOperation,
        ContractMetadata,
        MetadataProject,
        SystemParticipant,
    )

    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=12),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True, max_length=50),
            CanonicalField(name="email", type=CanonicalFieldType.STRING, required=False, max_length=100),
        ],
    )

    create_op = CanonicalOperation(name="createCustomer", interface_name="crm-api", request_entity="Customer", response_entity="Customer")
    update_op = CanonicalOperation(name="updateCustomer", interface_name="crm-api", request_entity="Customer", response_entity="Customer")

    mappings = [
        # createCustomer request/response mappings
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createCustomer", source_path="crm-api.createCustomer.request.customerName", target_path="Customer.customerName"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createCustomer", source_path="crm-api.createCustomer.response.customerId", target_path="Customer.customerId"),
        # updateCustomer request/response mappings
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="updateCustomer", source_path="crm-api.updateCustomer.request.email", target_path="Customer.email"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="updateCustomer", source_path="crm-api.updateCustomer.response.customerId", target_path="Customer.customerId"),
    ]

    profile_name = "springboot-multi-op"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name, language="java", framework="spring-boot",
        java_baseline="17", spring_boot_baseline="3.3.5",
        emit_flyway=False, emit_spring_batch=False, emit_security=False,
        emit_test_console=True, emit_audit=False, supports_xml=False,
    )

    metadata = MetadataProject(
        app_name="CRM Multi-Op",
        bounded_context="crm",
        target_profile=profile_name,
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[ContractMetadata(name="crm-api", type="rest-json", source="")],
        operations=[create_op, update_op],
        entities=[customer],
        mappings=mappings,
    )

    output_dir = tmp_path / "MultiOpApp"
    generate_application(metadata, output_dir, generation_run_id="e1-test")

    inbound = output_dir / "src" / "main" / "java" / "com" / "appbuilder" / "crm" / "adapter" / "inbound"

    # Two DTO pairs — one per operation
    assert (inbound / "CreateCustomerRequest.java").exists()
    assert (inbound / "CreateCustomerResponse.java").exists()
    assert (inbound / "UpdateCustomerRequest.java").exists()
    assert (inbound / "UpdateCustomerResponse.java").exists()
    create_response = (inbound / "CreateCustomerResponse.java").read_text(encoding="utf-8")
    update_request = (inbound / "UpdateCustomerRequest.java").read_text(encoding="utf-8")
    update_response = (inbound / "UpdateCustomerResponse.java").read_text(encoding="utf-8")
    assert "private String customerId;" in create_response
    assert "public void setCustomerId(String customerId)" in create_response
    assert "private String email;" in update_request
    assert "private String customerId;" in update_response

    # Exactly ONE controller for the entity
    assert (inbound / "CustomerController.java").exists()
    controller = (inbound / "CustomerController.java").read_text(encoding="utf-8")

    # Phase 1a: controller uses @RequestMapping at class level + full CRUD methods
    assert '@RequestMapping("/customers")' in controller
    assert "@PostMapping" in controller      # create
    assert "@GetMapping" in controller       # listAll + getById
    assert "@PutMapping" in controller       # update
    assert "@DeleteMapping" in controller    # delete
    # create operation method is present (first/create op context)
    assert "createCustomer" in controller

    # Full CRUD path-variable methods exist
    assert "@PathVariable" in controller
    assert "getById" in controller
    assert "listAll" in controller
    assert "delete" in controller

    # Exactly one Spring service subclass plus one generated base for the entity
    service_dir = output_dir / "src" / "main" / "java" / "com" / "appbuilder" / "crm" / "service"
    assert (service_dir / "CustomerService.java").exists()
    assert (service_dir / "CustomerServiceBase.java").exists()
    service = (service_dir / "CustomerServiceBase.java").read_text(encoding="utf-8")
    # Generated base has full CRUD methods plus the mapped create op
    assert "public CreateCustomerResponse createCustomer" in service
    assert "public UpdateCustomerResponse updateCustomer" in service
    assert "findById" in service
    assert "findAll" in service
    assert "delete" in service

    # operator dashboard — entity-centric panels. Create form posts to /customers.
    ui = (output_dir / "src" / "main" / "resources" / "static" / "index.html").read_text(encoding="utf-8")
    # Entity appears as sidebar nav item
    assert 'data-entity="Customer"' in ui
    # The create form targets the entity-level route, not a per-operation sub-path.
    assert '"/customers"' in ui
    assert '"/customers/update_customer"' not in ui
    assert '"/customers/create_customer"' not in ui

    baseline = json.loads(
        (output_dir / "db" / "schema-baseline.json").read_text(encoding="utf-8")
    )
    generated_sources = baseline["entities"][0]["generated_source_files"]
    listed_names = {Path(path).name for path in generated_sources}
    assert {
        "CreateCustomerRequest.java",
        "CreateCustomerResponse.java",
        "UpdateCustomerRequest.java",
        "UpdateCustomerResponse.java",
    }.issubset(listed_names)
    assert "CustomerCreateRequest.java" not in listed_names
    assert "CustomerService.java" not in listed_names
    assert "CustomerStagingWriter.java" not in listed_names
    assert "CustomerEodBatchJob.java" not in listed_names
    for relative_path in generated_sources:
        assert (output_dir / relative_path).exists()


def test_ui_selects_create_op_when_update_listed_first(tmp_path: Path) -> None:
    """UI must pick the create operation even when update appears before create in the manifest.

    Codex finding: the previous implementation used the first operation per entity, so a
    manifest ordering of [updateCustomer, createCustomer] would build the form from the
    update request shape and post it to the create endpoint.
    """
    from appbuilder.generation.ui_emitter import generate_demo_ui
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        CanonicalOperation,
        ContractMetadata,
        MetadataProject,
        SystemParticipant,
    )

    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
            CanonicalField(name="email", type=CanonicalFieldType.STRING, required=False),
        ],
    )

    # Manifest order: updateCustomer BEFORE createCustomer — the UI must still select createCustomer.
    update_op = CanonicalOperation(name="updateCustomer", interface_name="crm-api", request_entity="Customer", response_entity="Customer")
    create_op = CanonicalOperation(name="createCustomer", interface_name="crm-api", request_entity="Customer", response_entity="Customer")

    mappings = [
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="updateCustomer", source_path="crm-api.updateCustomer.request.customerId", target_path="Customer.customerId"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="updateCustomer", source_path="crm-api.updateCustomer.request.email", target_path="Customer.email"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createCustomer", source_path="crm-api.createCustomer.request.customerName", target_path="Customer.customerName"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createCustomer", source_path="crm-api.createCustomer.response.customerId", target_path="Customer.customerId"),
    ]

    profile_name = "springboot-update-first-test"
    if profile_name not in TARGET_PROFILES:
        TARGET_PROFILES[profile_name] = TargetProfile(
            name=profile_name, language="java", framework="spring-boot",
            java_baseline="17", spring_boot_baseline="3.3.5",
            emit_flyway=False, emit_spring_batch=False, emit_security=False, emit_audit=False, supports_xml=False,
        )

    metadata = MetadataProject(
        app_name="CRM Update-First Test",
        bounded_context="crm",
        target_profile=profile_name,
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[ContractMetadata(name="crm-api", type="rest-json", source="")],
        operations=[update_op, create_op],  # update listed FIRST intentionally
        entities=[customer],
        mappings=mappings,
    )

    output_dir = tmp_path / "UpdateFirstTest"
    output_dir.mkdir()
    ui_path = generate_demo_ui(metadata, output_dir, source_manifest="test", generation_run_id="upd-first")
    ui = ui_path.read_text(encoding="utf-8")

    # operator dashboard shows entity name in Create panel heading,
    # not "Try it — opName". The create form still POSTs to /customers.
    # The entity should appear as a nav item.
    assert 'data-entity="Customer"' in ui
    # Create panel uses POST /customers — entity-level route
    assert '"/customers"' in ui
    assert '"/customers/update_customer"' not in ui

    TARGET_PROFILES.pop(profile_name, None)


def test_batch_job_omits_file_writer_when_no_fixed_width_contract(tmp_path: Path) -> None:
    """D1: Batch jobs omit EodHandoffFileWriter import/param when no fixed-width downstream contract exists."""
    from appbuilder.generation.java_emitter import _render_batch_job
    from appbuilder.metadata.models import CanonicalEntity, CanonicalField, CanonicalFieldType

    entity = CanonicalEntity(
        name="Payment",
        fields=[CanonicalField(name="paymentId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=12)],
    )
    profile_name = "springboot-standard"  # reuse if already registered
    if profile_name not in TARGET_PROFILES:
        TARGET_PROFILES[profile_name] = TargetProfile(
            name=profile_name, language="java", framework="spring-boot",
            java_baseline="17", spring_boot_baseline="3.3.5",
            emit_flyway=True, emit_spring_batch=True, emit_security=False, emit_audit=False, supports_xml=False,
        )
    profile = TARGET_PROFILES[profile_name]

    # Staging handoff only — no fixed-width downstream contract
    job_staging_only = _render_batch_job(
        entity=entity,
        root_package="com.appbuilder.payments",
        bounded_context="payments",
        target_profile=profile,
        source_manifest="test",
        generation_run_id="d1-test",
        has_file_writer=False,
    )
    assert "PaymentStagingWriter" in job_staging_only
    assert "PaymentEodHandoffFileWriter" not in job_staging_only

    # Both staging handoff AND fixed-width downstream contract
    job_with_file_writer = _render_batch_job(
        entity=entity,
        root_package="com.appbuilder.payments",
        bounded_context="payments",
        target_profile=profile,
        source_manifest="test",
        generation_run_id="d1-test",
        has_file_writer=True,
    )
    assert "PaymentStagingWriter" in job_with_file_writer
    assert "PaymentEodHandoffFileWriter" in job_with_file_writer


def test_demo_ui_per_operation_endpoints(tmp_path: Path) -> None:
    """B2: Demo UI renders one panel per entity, each POSTing to the correct entity endpoint.
    # operator dashboard uses entity-centric panels, not per-operation sections.
    """
    metadata = _two_entity_metadata()
    output_dir = tmp_path / "UIEndpointTest"

    generate_application(metadata, output_dir, generation_run_id="b2-test")

    ui_content = (output_dir / "src" / "main" / "resources" / "static" / "index.html").read_text(encoding="utf-8")

    # One entity panel per entity
    assert 'data-entity="Customer"' in ui_content
    assert 'data-entity="Account"' in ui_content

    # Entity-specific endpoints are derived into action descriptors.
    assert '"/customers"' in ui_content
    assert '"/accounts"' in ui_content

    # The bounded-context catch-all endpoint must NOT appear as the form target
    assert '"/crm"' not in ui_content


def test_create_operation_name_for_entity_raises_for_unknown_entity(tmp_path: Path) -> None:
    """B3: _create_operation_name_for_entity raises ValueError when no operation matches the entity."""
    from appbuilder.generation.java_emitter import _create_operation_name_for_entity

    metadata = _two_entity_metadata()

    # Existing entity name — must succeed
    op_name = _create_operation_name_for_entity(metadata, "Customer")
    assert op_name == "createCustomer"

    # Unknown entity name — must raise, not silently return another entity's operation
    with pytest.raises(ValueError, match="UnknownEntity"):
        _create_operation_name_for_entity(metadata, "UnknownEntity")


def test_file_writer_isolation_per_entity(tmp_path: Path) -> None:
    """B1: Each entity's file/staging writer is bound only to its own downstream contract mappings."""
    from appbuilder.generation.java_emitter import _render_file_writer
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        CanonicalOperation,
        ContractMetadata,
        SystemParticipant,
    )

    # Build a two-entity metadata with separate downstream contracts per entity
    entity_a = CanonicalEntity(
        name="OrderItem",
        fields=[
            CanonicalField(name="itemId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=10),
            CanonicalField(name="quantity", type=CanonicalFieldType.INTEGER, required=True),
        ],
    )
    entity_b = CanonicalEntity(
        name="Shipment",
        fields=[
            CanonicalField(name="shipmentId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=10),
            CanonicalField(name="destination", type=CanonicalFieldType.STRING, required=True, max_length=100),
        ],
    )

    op_a = CanonicalOperation(name="createOrderItem", interface_name="order-api", request_entity="OrderItem", response_entity="OrderItem")
    op_b = CanonicalOperation(name="createShipment", interface_name="shipment-api", request_entity="Shipment", response_entity="Shipment")

    upstream_mappings = [
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="order-api", operation_name="createOrderItem", source_path="order-api.createOrderItem.request.quantity", target_path="OrderItem.quantity"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="shipment-api", operation_name="createShipment", source_path="shipment-api.createShipment.request.destination", target_path="Shipment.destination"),
    ]
    # Separate downstream contracts — one per entity
    downstream_mappings = [
        FieldMapping(direction=MappingDirection.CANONICAL_TO_DOWNSTREAM, contract_name="order-file", operation_name="writeOrderItem", source_path="OrderItem.quantity", target_path="order-file.writeOrderItem.quantity"),
        FieldMapping(direction=MappingDirection.CANONICAL_TO_DOWNSTREAM, contract_name="shipment-file", operation_name="writeShipment", source_path="Shipment.destination", target_path="shipment-file.writeShipment.destination"),
    ]

    from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile
    profile_name = "test-isolation-profile"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name, language="java", framework="spring-boot",
        java_baseline="17", spring_boot_baseline="3.3.5",
        emit_flyway=False, emit_spring_batch=True, emit_security=False, emit_audit=False, supports_xml=False,
    )

    from appbuilder.metadata.models import MetadataProject
    metadata = MetadataProject(
        app_name="IsolationApp",
        bounded_context="isolation",
        target_profile=profile_name,
        systems=[SystemParticipant(name="IsolationSystem", role="upstream")],
        contracts=[
            ContractMetadata(name="order-api", type="rest-json", source=""),
            ContractMetadata(name="shipment-api", type="rest-json", source=""),
            ContractMetadata(name="order-file", type="file-fixed-width", source=""),
            ContractMetadata(name="shipment-file", type="file-fixed-width", source=""),
        ],
        operations=[op_a, op_b],
        entities=[entity_a, entity_b],
        mappings=upstream_mappings + downstream_mappings,
    )

    # OrderItem writer should reference order-file, NOT shipment-file
    from appbuilder.generation.utils import base_package
    pkg = base_package(metadata)
    target_profile_obj = TARGET_PROFILES[profile_name]
    writer_a = _render_file_writer(
        entity=entity_a,
        metadata=metadata,
        root_package=pkg,
        source_manifest="test",
        target_profile=target_profile_obj,
        generation_run_id="b1-test",
    )
    # writer_a must contain OrderItem's field (quantity) but NOT Shipment's field (destination)
    assert "OrderItem" in writer_a
    assert "quantity" in writer_a.lower() or "getQuantity" in writer_a
    assert "destination" not in writer_a.lower()

    # Shipment writer should reference shipment-file fields, NOT order-file fields
    writer_b = _render_file_writer(
        entity=entity_b,
        metadata=metadata,
        root_package=pkg,
        source_manifest="test",
        target_profile=target_profile_obj,
        generation_run_id="b1-test",
    )
    # writer_b must contain Shipment's field (destination) but NOT OrderItem's field (quantity)
    assert "Shipment" in writer_b
    assert "destination" in writer_b.lower() or "getDestination" in writer_b
    assert "quantity" not in writer_b.lower()


def test_file_writer_falls_back_to_raw_value_when_no_layout_width() -> None:
    from appbuilder.generation.java_emitter import _render_file_writer
    from appbuilder.generation.utils import base_package

    entity = CanonicalEntity(
        name="Payment",
        fields=[
            CanonicalField(
                name="paymentId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=36,
            ),
            CanonicalField(
                name="referenceCode",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=20,
            ),
        ],
    )
    profile_name = "test-fixed-width-raw-fallback"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=True,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )
    metadata = MetadataProject(
        app_name="Payment Writer Fallback",
        bounded_context="payments",
        target_profile=profile_name,
        systems=[SystemParticipant(name="Payments", role="upstream")],
        contracts=[ContractMetadata(name="payment-file", type="file-fixed-width", source="")],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="payment-file",
                source_path="Payment.referenceCode",
                target_path="payment-file.reference_code",
                layout_width=None,
            )
        ],
    )

    try:
        writer_source = _render_file_writer(
            entity=entity,
            metadata=metadata,
            root_package=base_package(metadata),
            source_manifest="test",
            target_profile=TARGET_PROFILES[profile_name],
            generation_run_id="fixed-width-raw-fallback",
        )
    finally:
        TARGET_PROFILES.pop(profile_name, None)

    assert "line.append(stringValue(payment.getReferenceCode()));" in writer_source
    assert "padRight(stringValue(payment.getReferenceCode())" not in writer_source
    assert "private String padRight(String value, int width)" not in writer_source


def test_file_writer_uses_minor_unit_convention_for_decimal_minor_units_target() -> None:
    from appbuilder.generation.java_emitter import _render_file_writer
    from appbuilder.generation.utils import base_package

    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
            ),
            CanonicalField(
                name="availableBalance",
                type=CanonicalFieldType.DECIMAL,
                required=True,
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=True,
            ),
        ],
    )
    profile_name = "test-fixed-width-minor-units-convention"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=True,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )
    metadata = MetadataProject(
        app_name="Account Writer Minor Units",
        bounded_context="accounts",
        target_profile=profile_name,
        systems=[SystemParticipant(name="Accounts", role="upstream")],
        contracts=[ContractMetadata(name="account-file", type="file-fixed-width", source="")],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-file",
                source_path="Account.availableBalance",
                target_path="account-file.availableBalanceMinorUnits",
                layout_width=14,
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-file",
                source_path="Account.status",
                target_path="account-file.status",
                layout_width=8,
            ),
        ],
    )

    try:
        writer_source = _render_file_writer(
            entity=entity,
            metadata=metadata,
            root_package=base_package(metadata),
            source_manifest="test",
            target_profile=TARGET_PROFILES[profile_name],
            generation_run_id="fixed-width-minor-units-convention",
        )
    finally:
        TARGET_PROFILES.pop(profile_name, None)

    assert (
        "line.append(fixedWidthMinorUnitString(account.getAvailableBalance(), 14));"
        in writer_source
    )
    assert 'return " ".repeat(width);' in writer_source
    assert "Minor-unit value exceeds fixed width" in writer_source
    assert "leftZeroPad" not in writer_source
    assert "line.append(padRight(stringValue(account.getStatus()), 8));" in writer_source
    assert "line.append(padRight(stringValue(account.getAvailableBalance()), 14));" not in writer_source


def test_file_writer_rejects_explicit_minor_unit_coercion_for_non_decimal_source() -> None:
    from appbuilder.generation.java_emitter import _render_file_writer
    from appbuilder.generation.utils import base_package

    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
            ),
            CanonicalField(
                name="availableBalanceCode",
                type=CanonicalFieldType.STRING,
                required=True,
            ),
        ],
    )
    profile_name = "test-fixed-width-minor-units-type-compatibility"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=True,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )
    metadata = MetadataProject(
        app_name="Account Writer Minor Units Compatibility",
        bounded_context="accounts",
        target_profile=profile_name,
        systems=[SystemParticipant(name="Accounts", role="upstream")],
        contracts=[ContractMetadata(name="account-file", type="file-fixed-width", source="")],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-file",
                source_path="Account.availableBalanceCode",
                target_path="account-file.available_balance_minor",
                layout_width=14,
                type_coercion="major_to_minor_units",
            ),
        ],
    )

    try:
        with pytest.raises(ValueError) as excinfo:
            _render_file_writer(
                entity=entity,
                metadata=metadata,
                root_package=base_package(metadata),
                source_manifest="test",
                target_profile=TARGET_PROFILES[profile_name],
                generation_run_id="fixed-width-minor-units-type-compatibility",
            )
    finally:
        TARGET_PROFILES.pop(profile_name, None)

    assert str(excinfo.value) == (
        "Mapping type_coercion 'major_to_minor_units' requires DECIMAL source field "
        "'Account.availableBalanceCode', got 'string'."
    )


def test_enhanced_fixed_width_downstream_generates_header_data_trailer_writer(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/file-contracts/fixed-width-downstream-record-types/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-eod-file")
    assert "file-layout: fixed-width enhanced" in contract.ingestion_notes

    output_dir = tmp_path / "generated"
    generate_application(metadata, output_dir, generation_run_id="enhanced-fixed-width")

    writer_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/outbound/AccountEodHandoffFileWriter.java"
    ).read_text(encoding="utf-8")
    assert "public void startFile(Path outputPath, String runId)" in writer_source
    assert 'private static final Charset FILE_CHARSET = Charset.forName("ISO-8859-1");' in writer_source
    assert "renderHeader(runId) + System.lineSeparator()" in writer_source
    assert "FILE_CHARSET" in writer_source
    assert "public String renderHeader(String runId)" in writer_source
    assert 'line.append("H");' in writer_source
    assert 'formatFixedWidthField("file_date", LocalDate.now(), true, "date", "yyyyMMdd", 8, false)' in writer_source
    assert 'formatFixedWidthField("run_id", runId, true, "string", null, 12, false)' in writer_source
    assert "return requireLineLength(\"header\", line.toString(), 21);" in writer_source
    assert "private String renderDataLine(Account account)" in writer_source
    assert 'line.append("D");' in writer_source
    assert 'formatFixedWidthField("account_number", account.getAccountNumber(), true, "string", null, 12, false)' in writer_source
    assert (
        'formatFixedWidthField("available_balance_minor", minorUnitString(account.getAvailableBalance()), true, "integer", null, 14, true)'
        in writer_source
    )
    assert 'formatFixedWidthField("opened_date", account.getOpenedDate(), true, "date", "yyyyMMdd", 8, false)' in writer_source
    assert "return requireLineLength(\"data\", line.toString(), 35);" in writer_source
    assert "public void finishFile(Path outputPath, long recordCount, BigDecimal totalValue)" in writer_source
    assert "public String renderTrailer(long recordCount, BigDecimal totalValue)" in writer_source
    assert 'line.append("T");' in writer_source
    assert 'formatFixedWidthField("record_count", recordCount, true, "integer", null, 8, true)' in writer_source
    assert (
        'formatFixedWidthField("total_balance_minor", minorUnitString(totalValue), true, "integer", null, 14, true)'
        in writer_source
    )
    assert "return requireLineLength(\"trailer\", line.toString(), 23);" in writer_source
    assert "public BigDecimal dataTotal(Account account)" in writer_source
    assert "total = total.add(value);" in writer_source

    batch_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/batch/AccountEodBatchJob.java"
    ).read_text(encoding="utf-8")
    assert "handoffFileWriter.startFile(tempFile, outputRunId);" in batch_source
    assert "fileTotal = fileTotal.add(handoffFileWriter.dataTotal(record));" in batch_source
    assert "handoffFileWriter.finishFile(tempFile, recordCount, fileTotal);" in batch_source


def test_multiple_downstream_file_contracts_preserve_enhanced_fixed_width_controls(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/file-contracts/fixed-width-downstream-record-types/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    metadata.contracts.append(
        ContractMetadata(
            name="account-csv-out",
            type="file-csv",
            source="",
            file_layout={
                "format": "csv",
                "delimiter": ",",
                "quote_char": '"',
                "escape_char": "\\",
                "has_header_row": True,
                "line_separator": "\n",
                "encoding": "UTF-8",
                "fields": [
                    {
                        "name": "account_number",
                        "column": 1,
                        "type": "string",
                        "required": True,
                    },
                    {
                        "name": "opened_date",
                        "column": 2,
                        "type": "date",
                        "format": "yyyyMMdd",
                        "required": True,
                    },
                ],
            },
        )
    )
    metadata.mappings.extend(
        [
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-csv-out",
                source_path="Account.accountNumber",
                target_path="account-csv-out.account_number",
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-csv-out",
                source_path="Account.openedDate",
                target_path="account-csv-out.opened_date",
            ),
        ]
    )

    output_dir = tmp_path / "generated-enhanced-plus-csv"
    generate_application(metadata, output_dir, generation_run_id="enhanced-plus-csv")

    batch_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/batch/AccountEodBatchJob.java"
    ).read_text(encoding="utf-8")
    assert "AccountAccountEodFileFileWriter accountEodFileFileWriter" in batch_source
    assert "AccountAccountCsvOutFileWriter accountCsvOutFileWriter" in batch_source
    assert "accountEodFileFileWriter.startFile(accountEodFileTempFile, outputRunId);" in batch_source
    assert (
        "accountEodFileFileTotal = accountEodFileFileTotal.add("
        "accountEodFileFileWriter.dataTotal(record));"
    ) in batch_source
    assert (
        "accountEodFileFileWriter.finishFile("
        "accountEodFileTempFile, recordCount, accountEodFileFileTotal);"
    ) in batch_source
    assert (
        "accountCsvOutFileWriter.write(record, accountCsvOutTempOutputFile);"
        in batch_source
    )
    assert 'context.put("fileTotal.account-eod-file", BigDecimal.ZERO);' in batch_source


def test_enhanced_fixed_width_downstream_rejects_unsupported_control_value_source(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/file-contracts/fixed-width-downstream-record-types/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-eod-file")
    header = next(record for record in contract.file_layout["record_types"] if record["name"] == "header")
    header["fields"][0]["value_source"] = "business_calendar_date"

    with pytest.raises(
        ValueError,
        match="unsupported value_source 'business_calendar_date'",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_enhanced_fixed_width_downstream_rejects_non_leading_indicators(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/file-contracts/fixed-width-downstream-record-types/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-eod-file")
    data_record = next(record for record in contract.file_layout["record_types"] if record["name"] == "data")
    data_record["indicator"]["position"] = 3

    with pytest.raises(
        ValueError,
        match="requires leading indicators at position 1",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_enhanced_fixed_width_downstream_rejects_invalid_trailer_sum_reference(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/file-contracts/fixed-width-downstream-record-types/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-eod-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["value_source"] = "sum(Account.missingBalance)"

    with pytest.raises(
        ValueError,
        match="references unknown field 'Account.missingBalance'",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_flat_fixed_width_generates_parser(tmp_path: Path) -> None:
    project_root = tmp_path / "flat-inbound-fixed-width"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "upstream" / "account-layout.yaml").write_text(
        "\n".join(
            [
                "encoding: ISO-8859-1",
                "fields:",
                "  - name: account_id",
                "    length: 36",
                "    type: string",
                "    required: true",
                "  - name: amount",
                "    length: 10",
                "    type: decimal",
                "    required: true",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "upstream" / "account-mapping.yaml").write_text(
        "\n".join(
            [
                "entity: Account",
                "direction: inbound",
                "field_mappings:",
                "  - source: account_id",
                "    target: Account.accountId",
                "  - source: amount",
                "    target: Account.amount",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Flat Inbound File App",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: account-flat-file",
                "    system: CORE",
                "    type: file-fixed-width",
                "    spec: upstream/account-layout.yaml",
                "    mapping: upstream/account-mapping.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    metadata = build_metadata_project(project_root / "app-definition.yaml")
    output_dir = tmp_path / "generated-flat-parser"
    generate_application(metadata, output_dir, generation_run_id="flat-fixed-width-parser")

    parser_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountFlatFileFixedWidthParser.java"
    ).read_text(encoding="utf-8")
    assert "public List<ParsedRecord> parse(Path inputPath) throws IOException" in parser_source
    assert 'private static final Charset FILE_CHARSET = Charset.forName("ISO-8859-1");' in parser_source
    assert "Files.readAllLines(inputPath, FILE_CHARSET)" in parser_source
    assert "return \"data\";" in parser_source
    assert 'requireLineLength(fileName, lineNumber, "data", line, 46);' in parser_source
    assert 'slice(line, 1, 36)' in parser_source
    assert 'slice(line, 37, 10)' in parser_source
    assert 'case "decimal", "number", "bigdecimal" -> new BigDecimal(value);' in parser_source
    assert "required field is blank" in parser_source
    assert "expected line length" in parser_source


def test_upstream_enhanced_fixed_width_generates_parser(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/file-contracts/fixed-width-inbound-parser/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    output_dir = tmp_path / "generated-enhanced-parser"
    generate_application(metadata, output_dir, generation_run_id="enhanced-fixed-width-parser")

    parser_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountInboundFileFixedWidthParser.java"
    ).read_text(encoding="utf-8")
    assert 'private static final Charset FILE_CHARSET = Charset.forName("ISO-8859-1");' in parser_source
    assert "Files.readAllLines(inputPath, FILE_CHARSET)" in parser_source
    assert 'slice(line, 1, 1).equals("D")' in parser_source
    assert 'unknown record indicator: ' in parser_source
    assert 'case "data" -> parseData(fileName, lineNumber, line);' in parser_source
    assert 'requireLineLength(fileName, lineNumber, "data", line, 69);' in parser_source
    assert 'slice(line, 2, 36)' in parser_source
    assert 'slice(line, 38, 12)' in parser_source
    assert 'slice(line, 60, 10)' in parser_source
    assert '"available_balance", slice(line, 50, 10), true, "decimal", null' in parser_source
    assert '"opened_date", slice(line, 60, 10), true, "date", "yyyy-MM-dd"' in parser_source
    assert 'case "date", "localdate" -> LocalDate.parse' in parser_source
    assert "Fixed-width parse error for interface 'account-inbound-file'" in parser_source


def test_upstream_fixed_width_ingest_validates_trailer_reconciliation(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/fixed-width-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    output_dir = tmp_path / "generated-inbound-trailer"
    generate_application(metadata, output_dir, generation_run_id="inbound-trailer")

    controller_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/FileIngestController.java"
    ).read_text(encoding="utf-8")
    assert (
        "validateIngestAccountInboundFileTrailer(inputPath, parsedRecords, entities);"
        in controller_source
    )
    assert (
        controller_source.index(
            "validateIngestAccountInboundFileTrailer(inputPath, parsedRecords, entities);"
        )
        < controller_source.index("existsById(recordId)")
        < controller_source.index("saveAll(entities)")
    )
    assert (
        "private void validateIngestAccountInboundFileTrailer("
        "Path inputPath, List<AccountInboundFileFixedWidthParser.ParsedRecord> parsedRecords, "
        "List<Account> entities)"
    ) in controller_source
    assert '.filter(record -> "trailer".equals(record.recordType()))' in controller_source
    assert "trailerRecords.size() != 1" in controller_source
    assert 'Long actualRecordCount = asLong("record_count", trailerFields.get("record_count"));' in controller_source
    assert "long expectedRecordCount = entities.size();" in controller_source
    assert "BigDecimal expectedTotalBalanceMinor = BigDecimal.ZERO;" in controller_source
    assert "expectedTotalBalanceMinor = expectedTotalBalanceMinor.add(availableBalanceValue);" in controller_source
    assert "expectedTotalBalanceMinor = expectedTotalBalanceMinor.movePointRight(2).setScale(0);" in controller_source
    assert (
        'BigDecimal actualTotalBalanceMinor = asExactBigDecimal("total_balance_minor", '
        'trailerFields.get("total_balance_minor"));'
    ) in controller_source
    assert "actualTotalBalanceMinor.compareTo(expectedTotalBalanceMinor) != 0" in controller_source
    assert "Inbound trailer validation failed for interface '" in controller_source
    assert "', record type trailer, field " in controller_source


def test_upstream_fixed_width_ingest_rejects_non_trailer_value_source(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/fixed-width-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-inbound-file")
    header = next(record for record in contract.file_layout["record_types"] if record["name"] == "header")
    header["fields"][0]["value_source"] = "system_date"

    with pytest.raises(
        ValueError,
        match="Inbound trailer validation supports only record-count and sum totals in v1",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_fixed_width_ingest_rejects_unsupported_trailer_value_source(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/fixed-width-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][0]["value_source"] = "literal:2"

    with pytest.raises(
        ValueError,
        match="Inbound trailer validation supports only record-count and sum totals in v1",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_fixed_width_ingest_rejects_wrong_sum_entity(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/fixed-width-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["value_source"] = "sum(Customer.availableBalance)"

    with pytest.raises(
        ValueError,
        match="must reference entity 'Account'",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_fixed_width_ingest_rejects_unknown_sum_field(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/fixed-width-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["value_source"] = "sum(Account.missingBalance)"

    with pytest.raises(
        ValueError,
        match="references unknown canonical field 'Account.missingBalance'",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_fixed_width_ingest_rejects_unmapped_sum_field(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/fixed-width-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    account = next(entity for entity in metadata.entities if entity.name == "Account")
    account.fields.append(
        CanonicalField(
            name="ledgerBalance",
            type=CanonicalFieldType.DECIMAL,
            required=False,
        )
    )
    contract = next(contract for contract in metadata.contracts if contract.name == "account-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["value_source"] = "sum(Account.ledgerBalance)"

    with pytest.raises(
        ValueError,
        match="must reference a canonical field mapped from the file",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_fixed_width_ingest_rejects_non_numeric_sum_field(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/fixed-width-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["value_source"] = "sum(Account.accountNumber)"
    trailer["fields"][1].pop("type_coercion", None)

    with pytest.raises(
        ValueError,
        match="requires a numeric canonical field",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_csv_trailer_value_source_fails_fast(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/file-contracts/csv-inbound/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.type == "file-csv")
    contract.file_layout["fields"][0]["value_source"] = "data_record_count"

    with pytest.raises(
        ValueError,
        match="CSV inbound trailer validation supports indicator-column routing only in this slice",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_csv_ingest_validates_indicator_routed_trailer_reconciliation(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    output_dir = tmp_path / "generated-csv-inbound-trailer"
    generate_application(metadata, output_dir, generation_run_id="csv-inbound-trailer")

    parser_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountCsvInboundFileCsvParser.java"
    ).read_text(encoding="utf-8")
    assert "private static final int INDICATOR_COLUMN = 1;" in parser_source
    assert 'case "H" -> "header";' in parser_source
    assert 'case "D" -> "data";' in parser_source
    assert 'case "T" -> "trailer";' in parser_source
    assert "unknown record indicator: " in parser_source
    assert 'case "header" -> parseHeader(fileName, lineNumber, columns);' in parser_source
    assert 'case "data" -> parseData(fileName, lineNumber, columns);' in parser_source
    assert 'case "trailer" -> parseTrailer(fileName, lineNumber, columns);' in parser_source
    assert 'requireColumnCount(fileName, lineNumber, "data", columns, 5);' in parser_source
    assert 'requireColumnCount(fileName, lineNumber, "trailer", columns, 3);' in parser_source
    assert 'return new ParsedRecord("trailer", fields);' in parser_source
    assert "CSV parse error for interface 'account-csv-inbound-file'" in parser_source

    controller_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/FileIngestController.java"
    ).read_text(encoding="utf-8")
    assert (
        "validateIngestAccountCsvInboundFileTrailer(inputPath, parsedRecords, entities);"
        in controller_source
    )
    assert (
        controller_source.index(
            "validateIngestAccountCsvInboundFileTrailer(inputPath, parsedRecords, entities);"
        )
        < controller_source.index("existsById(recordId)")
        < controller_source.index("saveAll(entities)")
    )
    assert (
        "private void validateIngestAccountCsvInboundFileTrailer("
        "Path inputPath, List<AccountCsvInboundFileCsvParser.ParsedRecord> parsedRecords, "
        "List<Account> entities)"
    ) in controller_source
    assert '.filter(record -> "trailer".equals(record.recordType()))' in controller_source
    assert "trailerRecords.size() != 1" in controller_source
    assert 'Long actualRecordCount = asLong("record_count", trailerFields.get("record_count"));' in controller_source
    assert "long expectedRecordCount = entities.size();" in controller_source
    assert "BigDecimal expectedTotalBalanceMinor = BigDecimal.ZERO;" in controller_source
    assert "expectedTotalBalanceMinor = expectedTotalBalanceMinor.add(availableBalanceValue);" in controller_source
    assert "expectedTotalBalanceMinor = expectedTotalBalanceMinor.movePointRight(2).setScale(0);" in controller_source
    assert (
        'BigDecimal actualTotalBalanceMinor = asExactBigDecimal("total_balance_minor", '
        'trailerFields.get("total_balance_minor"));'
    ) in controller_source
    assert "actualTotalBalanceMinor.compareTo(expectedTotalBalanceMinor) != 0" in controller_source
    assert "Inbound trailer validation failed for interface '" in controller_source


def test_upstream_csv_ingest_rejects_non_trailer_value_source(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-csv-inbound-file")
    header = next(record for record in contract.file_layout["record_types"] if record["name"] == "header")
    header["fields"][0]["value_source"] = "system_date"

    with pytest.raises(
        ValueError,
        match="Inbound trailer validation supports only record-count and sum totals in v1",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_csv_ingest_rejects_unsupported_trailer_value_source(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-csv-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][0]["value_source"] = "literal:2"

    with pytest.raises(
        ValueError,
        match="Inbound trailer validation supports only record-count and sum totals in v1",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_csv_ingest_rejects_wrong_sum_entity(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-csv-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["value_source"] = "sum(Customer.availableBalance)"

    with pytest.raises(
        ValueError,
        match="must reference entity 'Account'",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_csv_ingest_rejects_unknown_sum_field(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-csv-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["value_source"] = "sum(Account.missingBalance)"

    with pytest.raises(
        ValueError,
        match="references unknown canonical field 'Account.missingBalance'",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_csv_ingest_rejects_unmapped_sum_field(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    account = next(entity for entity in metadata.entities if entity.name == "Account")
    account.fields.append(
        CanonicalField(
            name="ledgerBalance",
            type=CanonicalFieldType.DECIMAL,
            required=False,
        )
    )
    contract = next(contract for contract in metadata.contracts if contract.name == "account-csv-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["value_source"] = "sum(Account.ledgerBalance)"

    with pytest.raises(
        ValueError,
        match="must reference a canonical field mapped from the file",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_csv_ingest_rejects_non_numeric_sum_field(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-csv-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["value_source"] = "sum(Account.accountNumber)"
    trailer["fields"][1].pop("type_coercion", None)

    with pytest.raises(
        ValueError,
        match="requires a numeric canonical field",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_csv_ingest_rejects_unsupported_trailer_type_coercion(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-csv-inbound-file")
    trailer = next(record for record in contract.file_layout["record_types"] if record["name"] == "trailer")
    trailer["fields"][1]["type_coercion"] = "round_to_dollars"

    with pytest.raises(
        ValueError,
        match="declares unsupported type_coercion 'round_to_dollars'",
    ):
        generate_application(metadata, tmp_path / "generated")


def test_upstream_csv_ingest_rejects_position_based_record_routing(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/app-definition.yaml"
    )
    project = load_project_definition(fixture)
    layout_path = tmp_path / "position-based-layout.yaml"
    layout = yaml.safe_load(
        Path(
            "tests/fixtures/file-contracts/csv-inbound-trailer-reconciliation/upstream/account-csv-inbound-layout.yaml"
        ).read_text(encoding="utf-8")
    )
    layout["record_types"]["trailer"]["indicator"] = {"position": "last"}
    layout_path.write_text(yaml.safe_dump(layout), encoding="utf-8")
    project.upstream_interfaces[0].spec = str(layout_path)

    with pytest.raises(
        ValueError,
        match="indicator-column routing only in this slice",
    ):
        translate_project(project, project_root=fixture.parent)


def test_downstream_file_csv_generates_writer(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/file-contracts/csv-downstream/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    output_dir = tmp_path / "generated-csv-writer"

    generate_application(metadata, output_dir, generation_run_id="csv-writer")

    writer_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/outbound/AccountEodHandoffFileWriter.java"
    ).read_text(encoding="utf-8")
    assert "public class AccountEodHandoffFileWriter" in writer_source
    assert 'private static final String DELIMITER = "|";' in writer_source
    assert 'private static final String QUOTE_CHAR = "\\"";' in writer_source
    assert 'private static final String ESCAPE_CHAR = "\\\\";' in writer_source
    assert 'private static final String LINE_SEPARATOR = "\\n";' in writer_source
    assert "private static final boolean HAS_HEADER_ROW = true;" in writer_source
    assert 'private static final Charset FILE_CHARSET = Charset.forName("ISO-8859-1");' in writer_source
    assert "Files.writeString(" in writer_source
    assert "FILE_CHARSET" in writer_source
    assert "renderHeader() + LINE_SEPARATOR" in writer_source
    assert 'encode("account_id")' in writer_source
    assert 'encode("nickname")' in writer_source
    assert (
        'formatColumn("account_id", account.getAccountId(), true, "string", null)'
        in writer_source
    )
    assert 'encode("available_balance_minor")' in writer_source
    assert (
        'formatColumn("available_balance_minor", minorUnitString(account.getAvailableBalance()), true, "integer", null)'
        in writer_source
    )
    assert (
        'formatColumn("opened_date", account.getOpenedDate(), true, "date", null)'
        in writer_source
    )
    assert 'columns.add("");' in writer_source
    assert "decimal.toPlainString()" in writer_source
    assert "minorUnitString(BigDecimal value)" in writer_source
    assert "value.movePointRight(2).toBigIntegerExact().toString()" in writer_source
    assert "value instanceof LocalDate date" in writer_source
    assert "String serialized = stringValue(value, type, format);" in writer_source
    assert "required && serialized.isBlank()" in writer_source
    assert "Required CSV field is blank: " in writer_source
    assert "shouldWriteHeader(outputPath)" in writer_source
    assert "Files.size(outputPath) == 0L" in writer_source
    assert "value.contains(DELIMITER)" in writer_source
    assert "value.contains(LINE_SEPARATOR)" in writer_source
    assert "encoded.replace(QUOTE_CHAR, ESCAPE_CHAR + QUOTE_CHAR)" in writer_source
    assert "return value;" in writer_source


def test_entity_can_write_multiple_downstream_file_contracts(tmp_path: Path) -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=True,
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="Multi File Contracts",
        bounded_context="accounts",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="Accounts", role="upstream")],
        contracts=[
            ContractMetadata(
                name="account-staging",
                type="staging-table",
                source="",
                physical_name="account_staging",
            ),
            ContractMetadata(name="account-fixed-out", type="file-fixed-width", source=""),
            ContractMetadata(
                name="account-csv-out",
                type="file-csv",
                source="",
                file_layout={
                    "format": "csv",
                    "delimiter": ",",
                    "quote_char": '"',
                    "escape_char": "\\",
                    "has_header_row": True,
                    "line_separator": "\n",
                    "encoding": "UTF-8",
                    "fields": [
                        {
                            "name": "account_id",
                            "column": 1,
                            "type": "string",
                            "required": True,
                        },
                        {
                            "name": "status",
                            "column": 2,
                            "type": "string",
                            "required": True,
                        },
                    ],
                },
            ),
        ],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_HANDOFF,
                contract_name="account-staging",
                source_path="Account.accountId",
                target_path="account-staging.account_id",
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_HANDOFF,
                contract_name="account-staging",
                source_path="Account.status",
                target_path="account-staging.status",
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-fixed-out",
                source_path="Account.accountId",
                target_path="account-fixed-out.account_id",
                layout_width=12,
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-fixed-out",
                source_path="Account.status",
                target_path="account-fixed-out.status",
                layout_width=10,
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-csv-out",
                source_path="Account.accountId",
                target_path="account-csv-out.account_id",
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-csv-out",
                source_path="Account.status",
                target_path="account-csv-out.status",
            ),
        ],
    )
    output_dir = tmp_path / "generated-multiple-file-writers"

    generate_application(metadata, output_dir, generation_run_id="multiple-file-writers")

    java_dir = output_dir / "src/main/java/com/appbuilder/accounts"
    outbound_dir = java_dir / "adapter/outbound"
    assert not (outbound_dir / "AccountEodHandoffFileWriter.java").exists()
    assert (outbound_dir / "AccountAccountFixedOutFileWriter.java").exists()
    assert (outbound_dir / "AccountAccountCsvOutFileWriter.java").exists()

    batch_source = (java_dir / "batch/AccountEodBatchJob.java").read_text(
        encoding="utf-8"
    )
    assert (
        "AccountAccountFixedOutFileWriter accountFixedOutFileWriter"
        in batch_source
    )
    assert "AccountAccountCsvOutFileWriter accountCsvOutFileWriter" in batch_source
    assert (
        "accountFixedOutFileWriter.write(record, accountFixedOutTempOutputFile);"
        in batch_source
    )
    assert (
        "accountCsvOutFileWriter.write(record, accountCsvOutTempOutputFile);"
        in batch_source
    )
    assert 'context.putString("outputFile.account-fixed-out"' in batch_source
    assert 'context.putString("outputFile.account-csv-out"' in batch_source
    assert 'context.getString("tempOutputFile.account-fixed-out")' in batch_source
    assert 'context.getString("tempOutputFile.account-csv-out")' in batch_source
    assert 'return outputDir.resolve("account-account-fixed-out-" + dateStamp + ".dat");' in batch_source
    assert 'return outputDir.resolve("account-account-csv-out-" + dateStamp + ".csv");' in batch_source


def test_file_only_entity_generates_downstream_output_job_for_all_writers(
    tmp_path: Path,
) -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=True,
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="File Only Output Jobs",
        bounded_context="file_only_output_jobs",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="Core", role="upstream")],
        contracts=[
            ContractMetadata(name="account-inbound-file", type="file-fixed-width", source=""),
            ContractMetadata(name="account-fixed-out", type="file-fixed-width", source=""),
            ContractMetadata(
                name="account-csv-out",
                type="file-csv",
                source="",
                file_layout={
                    "format": "csv",
                    "delimiter": ",",
                    "quote_char": '"',
                    "escape_char": "\\",
                    "has_header_row": True,
                    "line_separator": "\n",
                    "encoding": "UTF-8",
                    "fields": [
                        {
                            "name": "account_id",
                            "column": 1,
                            "type": "string",
                            "required": True,
                        },
                        {
                            "name": "status",
                            "column": 2,
                            "type": "string",
                            "required": True,
                        },
                    ],
                },
            ),
        ],
        operations=[
            CanonicalOperation(
                name="emitAccountDownstreamOutputs",
                interface_name="account-fixed-out",
                request_entity="Account",
                response_entity="Account",
            )
        ],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="account-inbound-file",
                source_path="account_id",
                target_path="Account.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-fixed-out",
                source_path="Account.accountId",
                target_path="account-fixed-out.account_id",
                layout_width=12,
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-fixed-out",
                source_path="Account.status",
                target_path="account-fixed-out.status",
                layout_width=10,
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-csv-out",
                source_path="Account.accountId",
                target_path="account-csv-out.account_id",
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-csv-out",
                source_path="Account.status",
                target_path="account-csv-out.status",
            ),
        ],
    )
    output_dir = tmp_path / "generated-file-only-output-jobs"

    generate_application(metadata, output_dir, generation_run_id="file-only-output-jobs")

    java_dir = output_dir / "src/main/java/com/appbuilder/file_only_output_jobs"
    outbound_dir = java_dir / "adapter/outbound"
    assert (outbound_dir / "AccountAccountFixedOutFileWriter.java").exists()
    assert (outbound_dir / "AccountAccountCsvOutFileWriter.java").exists()
    assert not (outbound_dir / "AccountStagingWriter.java").exists()
    assert (java_dir / "adapter/inbound/BatchTriggerController.java").exists()

    batch_source = (java_dir / "batch/AccountEodBatchJob.java").read_text(
        encoding="utf-8"
    )
    assert "AccountStagingWriter" not in batch_source
    assert "stagingWriter.clear" not in batch_source
    assert "stagingWriter.write" not in batch_source
    assert "AccountAccountFixedOutFileWriter accountFixedOutFileWriter" in batch_source
    assert "AccountAccountCsvOutFileWriter accountCsvOutFileWriter" in batch_source
    assert (
        "accountFixedOutFileWriter.write(record, accountFixedOutTempOutputFile);"
        in batch_source
    )
    assert (
        "accountCsvOutFileWriter.write(record, accountCsvOutTempOutputFile);"
        in batch_source
    )
    assert 'return outputDir.resolve("account-account-fixed-out-" + dateStamp + ".dat");' in batch_source
    assert 'return outputDir.resolve("account-account-csv-out-" + dateStamp + ".csv");' in batch_source

    dashboard = (output_dir / "src/main/resources/static/index.html").read_text(
        encoding="utf-8"
    )
    assert "Run Account downstream outputs" in dashboard
    assert "accountEodJob" in dashboard
    assert "POST /batch/run/accountEodJob" in dashboard
    assert _dashboard_descriptor(dashboard, "batch-accountEodJob")["actions"][0]["endpoint"] == "/batch/run/{jobName}"
    assert "account-account-fixed-out-YYYYMMDD.dat" in dashboard
    assert "account-account-csv-out-YYYYMMDD.csv" in dashboard
    assert any(
        descriptor["family"] == "batch"
        for descriptor in _extract_dashboard_descriptors(dashboard)
    )


def test_downstream_file_contracts_with_colliding_normalized_names_stay_unique(
    tmp_path: Path,
) -> None:
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
            ),
        ],
    )
    csv_layout = {
        "format": "csv",
        "delimiter": ",",
        "quote_char": '"',
        "escape_char": "\\",
        "has_header_row": True,
        "line_separator": "\n",
        "encoding": "UTF-8",
        "fields": [
            {
                "name": "account_id",
                "column": 1,
                "type": "string",
                "required": True,
            },
        ],
    }
    metadata = MetadataProject(
        app_name="Colliding File Contracts",
        bounded_context="accounts",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="Accounts", role="upstream")],
        contracts=[
            ContractMetadata(name="account-inbound-file", type="file-fixed-width", source=""),
            ContractMetadata(
                name="account-staging",
                type="staging-table",
                source="",
                physical_name="account_staging",
            ),
            ContractMetadata(
                name="account-csv-out",
                type="file-csv",
                source="",
                file_layout=copy.deepcopy(csv_layout),
            ),
            ContractMetadata(
                name="account_csv_out",
                type="file-csv",
                source="",
                file_layout=copy.deepcopy(csv_layout),
            ),
        ],
        operations=[
            CanonicalOperation(
                name="emitAccountDownstreamOutputs",
                interface_name="account-csv-out",
                request_entity="Account",
                response_entity="Account",
            )
        ],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="account-inbound-file",
                source_path="account_id",
                target_path="Account.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_HANDOFF,
                contract_name="account-staging",
                source_path="Account.accountId",
                target_path="account-staging.account_id",
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account-csv-out",
                source_path="Account.accountId",
                target_path="account-csv-out.account_id",
            ),
            FieldMapping(
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                contract_name="account_csv_out",
                source_path="Account.accountId",
                target_path="account_csv_out.account_id",
            ),
        ],
    )
    output_dir = tmp_path / "generated-colliding-file-writers"

    generate_application(metadata, output_dir, generation_run_id="colliding-file-writers")

    java_dir = output_dir / "src/main/java/com/appbuilder/accounts"
    outbound_dir = java_dir / "adapter/outbound"
    assert (outbound_dir / "AccountAccountCsvOutFileWriter.java").exists()
    assert (outbound_dir / "AccountAccountCsvOutFileWriter2.java").exists()

    batch_source = (java_dir / "batch/AccountEodBatchJob.java").read_text(
        encoding="utf-8"
    )
    assert "AccountAccountCsvOutFileWriter accountCsvOutFileWriter" in batch_source
    assert "AccountAccountCsvOutFileWriter2 accountCsvOutFileWriter2" in batch_source
    assert (
        "accountCsvOutFileWriter.write(record, accountCsvOutTempOutputFile);"
        in batch_source
    )
    assert (
        "accountCsvOutFileWriter2.write(record, accountCsvOut2TempOutputFile);"
        in batch_source
    )
    assert "private Path accountCsvOutOutputFile()" in batch_source
    assert "private Path accountCsvOutOutputFile2()" in batch_source
    assert 'return outputDir.resolve("account-account-csv-out-" + dateStamp + ".csv");' in batch_source
    assert 'return outputDir.resolve("account-account-csv-out-2-" + dateStamp + ".csv");' in batch_source
    assert 'context.putString("outputFile.account-csv-out"' in batch_source
    assert 'context.putString("outputFile.account_csv_out"' in batch_source

    dashboard = (output_dir / "src/main/resources/static/index.html").read_text(
        encoding="utf-8"
    )
    assert "account-account-csv-out-YYYYMMDD.csv" in dashboard
    assert "account-account-csv-out-2-YYYYMMDD.csv" in dashboard


def test_downstream_file_csv_rejects_incompatible_layout_type(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/file-contracts/csv-downstream/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-csv-file")
    for field in contract.file_layout["fields"]:
        if field["name"] == "active":
            field["type"] = "decimal"
            break

    with pytest.raises(
        ValueError,
        match=(
            "CSV downstream field 'active' expects layout type 'decimal', "
            "but source field 'Account.active' is boolean"
        ),
    ):
        generate_application(metadata, tmp_path / "generated-csv-writer")


def test_downstream_file_csv_rejects_incompatible_minor_unit_layout_type(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/file-contracts/csv-downstream/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    contract = next(contract for contract in metadata.contracts if contract.name == "account-csv-file")
    for field in contract.file_layout["fields"]:
        if field["name"] == "available_balance_minor":
            field["type"] = "date"
            break

    with pytest.raises(
        ValueError,
        match=(
            "CSV downstream field 'available_balance_minor' expects layout type 'date', "
            "but type_coercion 'major_to_minor_units' produces integer minor units"
        ),
    ):
        generate_application(metadata, tmp_path / "generated-csv-writer")


def test_upstream_file_csv_generates_parser(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/file-contracts/csv-inbound/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    output_dir = tmp_path / "generated-csv-parser"
    generate_application(metadata, output_dir, generation_run_id="csv-parser")

    parser_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/AccountCsvFileCsvParser.java"
    ).read_text(encoding="utf-8")
    assert "public List<ParsedRecord> parse(Path inputPath) throws IOException" in parser_source
    assert 'private static final String DELIMITER = "|";' in parser_source
    assert 'private static final String QUOTE_CHAR = "\\"";' in parser_source
    assert 'private static final String ESCAPE_CHAR = "\\\\";' in parser_source
    assert 'private static final String LINE_SEPARATOR = "\\n";' in parser_source
    assert "private static final boolean HAS_HEADER_ROW = true;" in parser_source
    assert 'private static final Charset FILE_CHARSET = Charset.forName("ISO-8859-1");' in parser_source
    assert "List<String> lines = readConfiguredLines(inputPath);" in parser_source
    assert "CSV file is empty" in parser_source
    assert "Files.readString(inputPath, FILE_CHARSET)" in parser_source
    assert "validateHeader(inputPath.toString(), parseCsvLine" in parser_source
    assert 'if (!header.get(0).trim().equals("account_id"))' in parser_source
    assert 'columns.get(0), true, "string", null' in parser_source
    assert 'columns.get(2), true, "decimal", null' in parser_source
    assert 'columns.get(3), true, "date", "yyyy-MM-dd"' in parser_source
    assert 'columns.get(4), true, "boolean", null' in parser_source
    assert 'if (inQuotes && ESCAPE_CHAR != null && value.equals(ESCAPE_CHAR))' in parser_source
    assert 'case "string", "char", "text" -> rawValue;' in parser_source
    assert "String trimmedValue = rawValue.trim();" in parser_source
    assert 'case "boolean", "bool" -> parseBoolean' in parser_source
    assert "required field is blank" in parser_source
    assert "unterminated quoted field" in parser_source
    assert "CSV parse error for interface 'account-csv-file'" in parser_source

    ingest_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/FileIngestController.java"
    ).read_text(encoding="utf-8")
    assert '@PostMapping("/ingest/{contractName}")' in ingest_source
    assert (
        'case "account-csv-file" -> ResponseEntity.ok('
        "ingestAccountCsvFile(resolveInputPath(request == null ? null : request.path())));"
    ) in ingest_source
    assert (
        ingest_source.index('case "account-csv-file"')
        < ingest_source.index("resolveInputPath(request == null ? null : request.path())")
    )
    assert (
        ingest_source.index("default -> ResponseEntity.status(HttpStatus.NOT_FOUND)")
        < ingest_source.index("    private Path resolveInputPath")
    )
    assert "accountCsvFileParser.parse(inputPath)" in ingest_source
    assert 'account.setAccountId(asString("accountId", requiredField(fields, "account_id", "Account.accountId")))' in ingest_source
    assert "Set<String> seenIds = new HashSet<>();" in ingest_source
    assert "!seenIds.add(recordId)" in ingest_source
    assert "accountRepository.existsById(recordId)" in ingest_source
    assert "accountRepository.saveAll(entities)" in ingest_source
    assert 'lowerPath.matches("^[a-z][a-z0-9+.-]*://.*")' in ingest_source
    assert "!resolved.startsWith(baseDir)" in ingest_source
    assert "Path realInputPath = resolved.toRealPath();" in ingest_source
    assert "!realInputPath.startsWith(realBaseDir)" in ingest_source

    entity_source = (
        output_dir / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    ).read_text(encoding="utf-8")
    account_id_section = entity_source.split("private String accountId;", 1)[0].rsplit("/**", 1)[-1]
    assert "ID ownership: application-assigned UUID (external ingestion may supply the id)." in account_id_section
    assert "@GeneratedValue(strategy = GenerationType.UUID)" not in account_id_section
    assert "import java.util.UUID;" in entity_source
    assert "this.accountId = UUID.randomUUID().toString();" in entity_source


def test_file_only_fixed_width_package_generates_ui_fallback(tmp_path: Path) -> None:
    fixture = _write_file_only_contract_fixture(tmp_path, file_type="file-fixed-width")
    metadata = build_metadata_project(fixture)

    output_dir = tmp_path / "generated-file-only-fixed"
    report = generate_application(metadata, output_dir, source_manifest=str(fixture))

    assert report.files_created
    dashboard = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")
    account_panel = _dashboard_entity_panel(dashboard, "Account")
    upstream_section = _dashboard_group_section(account_panel, "UPSTREAM")
    assert '<span class="group-title">Upstream</span>' in upstream_section
    assert 'data-coverage-key="file-Account-account-inbound-file"' in upstream_section
    assert "account-inbound-file" in dashboard
    assert "POST /files/ingest/account-inbound-file" in dashboard
    file_descriptor = _dashboard_descriptor(dashboard, "file-Account-account-inbound-file")
    assert file_descriptor["family"] == "file"
    assert file_descriptor["actions"][0]["endpoint"] == "/files/ingest/{contractName}"
    assert file_descriptor["actions"][0]["inputBinding"] == "JSON_BODY"
    assert "submitAction(" in dashboard
    assert "runFileIngest" not in dashboard
    assert "app.file-ingest.base-dir" in dashboard
    assert "No upstream operation with explicit mappings was found" not in dashboard
    assert list((output_dir / "src/main/java").rglob("*FixedWidthParser.java"))
    assert list((output_dir / "src/main/java").rglob("*FileWriter.java"))
    ingest_source = next(
        (output_dir / "src/main/java").rglob("FileIngestController.java")
    ).read_text(encoding="utf-8")
    assert (
        '${app.file-ingest.base-dir:${java.io.tmpdir}/edgeforge-file_only_contract-'
        '${APP_INSTANCE_ID:${random.uuid}}/file-ingest}'
    ) in ingest_source
    assert "/tmp/file_only_contract/ingest" not in ingest_source
    assert "accountInboundFileParser.parse(inputPath)" in ingest_source
    assert 'account.setAccountId(asString("accountId", requiredField(fields, "account_id", "Account.accountId")))' in ingest_source
    entity_source = next((output_dir / "src/main/java").rglob("Account.java")).read_text(
        encoding="utf-8"
    )
    account_id_section = entity_source.split("private String accountId;", 1)[0].rsplit("/**", 1)[-1]
    assert "@GeneratedValue(strategy = GenerationType.UUID)" not in account_id_section
    assert "this.accountId = UUID.randomUUID().toString();" in entity_source


def test_file_only_csv_package_generates_ui_fallback(tmp_path: Path) -> None:
    fixture = _write_file_only_contract_fixture(tmp_path, file_type="file-csv")
    metadata = build_metadata_project(fixture)

    output_dir = tmp_path / "generated-file-only-csv"
    report = generate_application(metadata, output_dir, source_manifest=str(fixture))

    assert report.files_created
    dashboard = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")
    account_panel = _dashboard_entity_panel(dashboard, "Account")
    upstream_section = _dashboard_group_section(account_panel, "UPSTREAM")
    assert '<span class="group-title">Upstream</span>' in upstream_section
    assert 'data-coverage-key="file-Account-account-inbound-file"' in upstream_section
    assert "account-inbound-file" in dashboard
    assert "POST /files/ingest/account-inbound-file" in dashboard
    file_descriptor = _dashboard_descriptor(dashboard, "file-Account-account-inbound-file")
    assert file_descriptor["family"] == "file"
    assert file_descriptor["actions"][0]["endpoint"] == "/files/ingest/{contractName}"
    assert file_descriptor["actions"][0]["inputBinding"] == "JSON_BODY"
    assert "submitAction(" in dashboard
    assert "runFileIngest" not in dashboard
    assert "No upstream operation with explicit mappings was found" not in dashboard
    assert list((output_dir / "src/main/java").rglob("*CsvParser.java"))
    assert list((output_dir / "src/main/java").rglob("*FileWriter.java"))
    ingest_source = next(
        (output_dir / "src/main/java").rglob("FileIngestController.java")
    ).read_text(encoding="utf-8")
    assert "accountInboundFileParser.parse(inputPath)" in ingest_source


def test_upstream_file_only_package_without_downstream_outputs_emits_ingest_runtime(
    tmp_path: Path,
) -> None:
    fixture = _write_file_only_contract_fixture(
        tmp_path,
        file_type="file-csv",
        include_downstream=False,
    )
    metadata = build_metadata_project(fixture)
    assert metadata.operations == []

    output_dir = tmp_path / "generated-upstream-file-only"
    generate_application(metadata, output_dir, source_manifest=str(fixture))

    dashboard = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")
    account_panel = _dashboard_entity_panel(dashboard, "Account")
    upstream_section = _dashboard_group_section(account_panel, "UPSTREAM")
    assert 'data-coverage-key="file-Account-account-inbound-file"' in upstream_section
    assert "POST /files/ingest/account-inbound-file" in dashboard
    assert all(
        descriptor["family"] != "batch"
        for descriptor in _extract_dashboard_descriptors(dashboard)
    )
    assert (
        output_dir
        / "src/main/java/com/appbuilder/file_only_contract/adapter/inbound/FileIngestController.java"
    ).exists()


def test_apps_without_upstream_file_contracts_do_not_emit_file_ingest_controller(
    tmp_path: Path,
) -> None:
    metadata = _two_entity_metadata()

    output_dir = tmp_path / "generated-no-file-ingest"
    generate_application(metadata, output_dir, generation_run_id="no-file-ingest")

    assert not list((output_dir / "src/main/java").rglob("FileIngestController.java"))


def test_file_contract_without_id_mapping_preserves_provider_uuid_generation(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/file-contracts/csv-inbound/app-definition.yaml")
    metadata = build_metadata_project(fixture)
    metadata.mappings = [
        mapping
        for mapping in metadata.mappings
        if mapping.target_path != "Account.accountId"
    ]

    output_dir = tmp_path / "generated-file-ingest-no-id-mapping"
    generate_application(metadata, output_dir, generation_run_id="file-ingest-no-id")

    entity_source = (
        output_dir / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    ).read_text(encoding="utf-8")
    account_id_section = entity_source.split("private String accountId;", 1)[0].rsplit("/**", 1)[-1]
    assert "ID ownership: server-generated UUID" in account_id_section
    assert "@GeneratedValue(strategy = GenerationType.UUID)" in account_id_section
    assert "this.accountId = UUID.randomUUID().toString();" not in entity_source

    ingest_source = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/inbound/FileIngestController.java"
    ).read_text(encoding="utf-8")
    assert "account.setAccountId(" not in ingest_source
    assert "accountRepository.existsById(recordId)" not in ingest_source


def test_file_only_ui_fallback_is_entity_scoped(tmp_path: Path) -> None:
    from appbuilder.generation.ui_emitter import generate_demo_ui
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        ContractMetadata,
        MetadataProject,
        SystemParticipant,
    )

    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="status", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    metadata = MetadataProject(
        app_name="Mixed File Contract App",
        bounded_context="mixed_file_contract",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="CORE", role="upstream")],
        contracts=[
            ContractMetadata(name="account-inbound-file", type="file-fixed-width", source="upstream/account-layout.yaml")
        ],
        operations=[],
        entities=[account, customer],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="account-inbound-file",
                operation_name=None,
                source_path="account_id",
                target_path="Account.accountId",
            )
        ],
    )

    output_dir = tmp_path / "mixed-file-ui"
    output_dir.mkdir()
    ui = generate_demo_ui(
        metadata,
        output_dir,
        source_manifest="test",
        generation_run_id="mixed-file-ui",
    ).read_text(encoding="utf-8")

    assert 'id="crud-Account-get"' not in ui
    account_panel = _dashboard_entity_panel(ui, "Account")
    account_upstream = _dashboard_group_section(account_panel, "UPSTREAM")
    assert 'data-coverage-key="file-Account-account-inbound-file"' in account_upstream
    assert "account-inbound-file" in ui
    assert 'id="crud-Customer-get"' in ui
    assert 'id="crud-Customer-list"' in ui
    customer_panel = ui.split('id="entity-panel-Customer"', 1)[1]
    assert "No upstream file contracts mapped to this entity." not in customer_panel


def test_upstream_fixed_width_fails_for_non_crud_archetype(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "kafka-inbound-fixed-width"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "schemas").mkdir()
    (project_root / "mappings").mkdir()
    (project_root / "upstream" / "account-layout.yaml").write_text(
        "\n".join(
            [
                "fields:",
                "  - name: account_id",
                "    length: 36",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "schemas" / "account-event.json").write_text("{}", encoding="utf-8")
    (project_root / "schemas" / "downstream-account-event.json").write_text("{}", encoding="utf-8")
    (project_root / "mappings" / "account-event.yaml").write_text(
        "field_mappings: []\n",
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Kafka Inbound File App",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "app_archetype: kafka-integration",
                "kafka_config:",
                "  consumer_group: account-file-group",
                "  concurrency: 1",
                "async_routes:",
                "  - name: account-event",
                "    pattern: fire-and-forget",
                "    upstream_topic:",
                "      name: core.accounts.v1",
                "      system: CORE",
                "      message_schema: schemas/account-event.json",
                "    downstream_topic:",
                "      name: downstream.accounts.v1",
                "      system: DOWNSTREAM",
                "      message_schema: schemas/downstream-account-event.json",
                "    transform_mapping: mappings/account-event.yaml",
                "upstream_interfaces:",
                "  - name: account-file",
                "    system: CORE",
                "    type: file-fixed-width",
                "    spec: upstream/account-layout.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Inbound file-fixed-width parser generation is currently implemented only",
    ):
        build_metadata_project(project_root / "app-definition.yaml")


def test_upstream_fixed_width_fails_for_passthrough_archetype(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "passthrough-inbound-fixed-width"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "upstream" / "account-layout.yaml").write_text(
        "\n".join(
            [
                "fields:",
                "  - name: account_id",
                "    length: 36",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Passthrough Inbound File App",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "app_archetype: passthrough-router",
                "upstream_interfaces:",
                "  - name: account-file",
                "    system: CORE",
                "    type: file-fixed-width",
                "    spec: upstream/account-layout.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Inbound file-fixed-width parser generation is currently implemented only",
    ):
        build_metadata_project(project_root / "app-definition.yaml")


def test_upstream_csv_fails_for_non_crud_archetype(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "kafka-inbound-csv"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "schemas").mkdir()
    (project_root / "mappings").mkdir()
    (project_root / "upstream" / "account-layout.yaml").write_text(
        "\n".join(
            [
                "format: csv",
                "delimiter: \",\"",
                "record_types:",
                "  data:",
                "    fields:",
                "      - name: account_id",
                "        column: 1",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "schemas" / "account-event.json").write_text("{}", encoding="utf-8")
    (project_root / "schemas" / "downstream-account-event.json").write_text("{}", encoding="utf-8")
    (project_root / "mappings" / "account-event.yaml").write_text(
        "field_mappings: []\n",
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Kafka Inbound CSV App",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "app_archetype: kafka-integration",
                "kafka_config:",
                "  consumer_group: account-file-group",
                "  concurrency: 1",
                "async_routes:",
                "  - name: account-event",
                "    pattern: fire-and-forget",
                "    upstream_topic:",
                "      name: core.accounts.v1",
                "      system: CORE",
                "      message_schema: schemas/account-event.json",
                "    downstream_topic:",
                "      name: downstream.accounts.v1",
                "      system: DOWNSTREAM",
                "      message_schema: schemas/downstream-account-event.json",
                "    transform_mapping: mappings/account-event.yaml",
                "upstream_interfaces:",
                "  - name: account-file",
                "    system: CORE",
                "    type: file-csv",
                "    spec: upstream/account-layout.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Inbound file-csv parser generation is currently implemented only",
    ):
        build_metadata_project(project_root / "app-definition.yaml")


def test_xml_xsd_contract_translates_to_metadata_and_generates_runtime_adapters(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/edgecontracts/xml-xsd/basic-customer/app-definition.yaml")
    metadata = build_metadata_project(fixture)

    contract = next(contract for contract in metadata.contracts if contract.name == "customer-xml-input")
    assert contract.type == "xml-xsd"
    assert contract.xml_contract is not None
    assert contract.xml_contract["xsd_path"] == "contracts/customer.xsd"
    assert contract.xml_contract["root_element"] == "CustomerMessage"
    assert contract.xml_contract["namespace"] == "urn:edgeforge:examples:customer:v1"
    assert contract.xml_contract["namespace_alias"] == "cust"
    assert "xml-contract: xsd v1 parsed" in contract.ingestion_notes

    output_dir = tmp_path / "generated-xml"
    report = generate_application(metadata, output_dir, source_manifest=str(fixture))

    model_path = (
        output_dir
        / "src/main/java/com/appbuilder/customers/adapter/xml/CustomerXmlInputXmlModel.java"
    )
    parser_path = (
        output_dir
        / "src/main/java/com/appbuilder/customers/adapter/xml/CustomerXmlInputXmlParser.java"
    )
    serializer_path = (
        output_dir
        / "src/main/java/com/appbuilder/customers/adapter/xml/CustomerXmlInputXmlSerializer.java"
    )
    test_path = (
        output_dir
        / "src/test/java/com/appbuilder/customers/adapter/xml/CustomerXmlInputXmlModelAdapterTest.java"
    )
    xsd_resource = (
        output_dir
        / "src/main/resources/xml-contracts/customer-xml-input/contracts/customer.xsd"
    )
    sample_resource = (
        output_dir
        / "src/test/resources/xml-contract-samples/customer-xml-input/customer.xml"
    )

    assert model_path in report.files_created
    assert parser_path in report.files_created
    assert serializer_path in report.files_created
    assert test_path in report.files_created
    assert xsd_resource in report.files_created
    assert sample_resource in report.files_created

    model_source = model_path.read_text(encoding="utf-8")
    parser_source = parser_path.read_text(encoding="utf-8")
    serializer_source = serializer_path.read_text(encoding="utf-8")

    assert "public enum StatusValue" in model_source
    assert "private List<String> alias = new ArrayList<>();" in model_source
    assert "private String sourceSystem;" in model_source
    assert "XSD_RESOURCE = \"/xml-contracts/customer-xml-input/contracts/customer.xsd\"" in parser_source
    assert "SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI)" in parser_source
    assert "schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, \"\")" in parser_source
    assert "disallow-doctype-decl" in parser_source
    assert "throw malformedXml(ex);" in parser_source
    assert "Malformed XML for contract customer-xml-input:" in parser_source
    assert "safeXmlMessage(ex)" in parser_source
    assert "missingRequiredXmlField(\"/CustomerMessage/customerId\")" in parser_source
    assert "XML parse error for interface 'customer-xml-input'" in parser_source
    assert "throw parseError(fieldName, \"invalid decimal value\");" in parser_source
    assert "throw parseError(fieldName, \"invalid date value\");" in parser_source
    assert "throw parseError(fieldName, \"invalid datetime value\");" in parser_source
    assert "validateRoot(root);" in parser_source
    assert "childElements(root, \"alias\")" in parser_source
    assert "rawValue == null || rawValue.isBlank()" not in parser_source
    assert "document.createElementNS(NAMESPACE, NAMESPACE_ALIAS + \":\" + ROOT_ELEMENT)" in serializer_source
    assert "transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, \"\")" in serializer_source
    assert "validateXml(xml);" in serializer_source


def test_xml_xsd_mapped_contracts_generate_canonical_ingest_and_output_runtime(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/edgecontracts/xml-xsd/account-roundtrip-runtime/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)

    assert any(
        mapping.contract_name == "account-xml-inbound"
        and mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
        and mapping.source_path == "account-xml-inbound.xml.accountId"
        and mapping.target_path == "Account.accountId"
        for mapping in metadata.mappings
    )
    assert any(
        mapping.contract_name == "account-xml-outbound"
        and mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.source_path == "Account.accountId"
        and mapping.target_path == "account-xml-outbound.accountId"
        for mapping in metadata.mappings
    )

    output_dir = tmp_path / "generated-xml-runtime"
    report = generate_application(metadata, output_dir, source_manifest=str(fixture))
    assert report.files_created

    ingest_path = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/xml/XmlIngestController.java"
    )
    output_path = (
        output_dir
        / "src/main/java/com/appbuilder/accounts/adapter/xml/XmlOutputController.java"
    )
    entity_path = output_dir / "src/main/java/com/appbuilder/accounts/domain/Account.java"
    dashboard_path = output_dir / "src/main/resources/static/index.html"

    assert ingest_path in report.files_created
    assert output_path in report.files_created

    ingest_source = ingest_path.read_text(encoding="utf-8")
    output_source = output_path.read_text(encoding="utf-8")
    entity_source = entity_path.read_text(encoding="utf-8")
    dashboard = dashboard_path.read_text(encoding="utf-8")

    assert '@RequestMapping("/xml")' in ingest_source
    assert '@PostMapping("/ingest/{contractName}")' in ingest_source
    assert 'case "account-xml-inbound"' in ingest_source
    assert (
        ingest_source.index('case "account-xml-inbound"')
        < ingest_source.index("resolveInputPath(request == null ? null : request.path())")
    )
    assert "accountXmlInboundXmlParser.parse(inputPath)" in ingest_source
    assert "account.setAccountId(requiredXmlValue" in ingest_source
    assert 'requiredXmlValue("/AccountMessage/accountId"' in ingest_source
    assert "Missing required XML field \" + xmlPath + \" mapped to \" + entityFieldName" in ingest_source
    assert 'account.setSourceSystem(requiredXmlValue("/AccountMessage/@sourceSystem"' in ingest_source
    assert 'requiredXmlValue("/AccountMessage/@sourceSystem"' in ingest_source
    assert "accountRepository.existsById(recordId)" in ingest_source
    assert "accountRepository.save(account)" in ingest_source
    assert 'lowerPath.matches("^[a-z][a-z0-9+.-]*://.*")' in ingest_source
    assert "!realInputPath.startsWith(realBaseDir)" in ingest_source
    assert (
        '${app.xml-ingest.base-dir:${java.io.tmpdir}/edgeforge-accounts-'
        '${APP_INSTANCE_ID:${random.uuid}}/xml-ingest}'
    ) in ingest_source
    assert "/tmp/accounts/xml-ingest" not in ingest_source

    assert '@PostMapping("/output/{contractName}")' in output_source
    assert 'case "account-xml-outbound"' in output_source
    assert "List<Account> records = accountRepository.findAll();" in output_source
    assert "for (Account account : records)" in output_source
    assert "accountXmlOutboundXmlSerializer.serialize(model)" in output_source
    assert '"account-xml-outbound"' in output_source
    assert "outputFileName(" in output_source
    assert "List<XmlOutputFile> pendingFiles = new ArrayList<>();" in output_source
    assert "Set<String> outputFileNames = new HashSet<>();" in output_source
    assert "XML output filename collision" in output_source
    assert "writeAllOrNothing(pendingFiles);" in output_source
    assert "Files.writeString(pendingFile.tempPath(), pendingFile.xml(), StandardCharsets.UTF_8);" in output_source
    assert "List<XmlOutputBackupFile> backupFiles = new ArrayList<>();" in output_source
    assert "backupFiles.add(new XmlOutputBackupFile(pendingFile.outputPath(), backupPath, true));" in output_source
    assert "moveAtomically(pendingFile.tempPath(), pendingFile.outputPath());" in output_source
    assert "restoreBackupFiles(backupFiles, ex);" in output_source
    assert "rollbackPublishedFiles(pendingFiles, backupFiles, ex);" in output_source
    assert "Files.deleteIfExists(pendingFile.outputPath());" in output_source
    assert "moveAtomically(backupFile.backupPath(), backupFile.outputPath());" in output_source
    assert "cleanupBackupFiles(backupFiles);" in output_source
    assert 'String.format("%05d", index) + "-" + safeId' in output_source
    assert (
        '${app.xml-output.base-dir:${java.io.tmpdir}/edgeforge-accounts-'
        '${APP_INSTANCE_ID:${random.uuid}}/xml-output}'
    ) in output_source
    assert "/tmp/accounts/xml-output" not in output_source

    account_id_section = entity_source.split("private String accountId;", 1)[0].rsplit("/**", 1)[-1]
    assert "ID ownership: application-assigned UUID (external ingestion may supply the id)." in account_id_section
    assert "@GeneratedValue(strategy = GenerationType.UUID)" not in account_id_section
    assert "this.accountId = UUID.randomUUID().toString();" in entity_source

    account_panel = _dashboard_entity_panel(dashboard, "Account")
    upstream_section = _dashboard_group_section(account_panel, "UPSTREAM")
    downstream_section = _dashboard_group_section(account_panel, "DOWNSTREAM")
    assert 'data-coverage-key="xml-Account-ingest-account-xml-inbound"' in upstream_section
    assert 'data-coverage-key="xml-Account-output-account-xml-outbound"' in downstream_section
    assert "POST /xml/ingest/account-xml-inbound" in dashboard
    assert "POST /xml/output/account-xml-outbound" in dashboard
    ingest_descriptor = _dashboard_descriptor(dashboard, "xml-Account-ingest-account-xml-inbound")
    output_descriptor = _dashboard_descriptor(dashboard, "xml-Account-output-account-xml-outbound")
    assert ingest_descriptor["family"] == "xml"
    assert ingest_descriptor["actions"][0]["endpoint"] == "/xml/ingest/{contractName}"
    assert ingest_descriptor["actions"][0]["inputBinding"] == "JSON_BODY"
    assert output_descriptor["family"] == "xml"
    assert output_descriptor["actions"][0]["endpoint"] == "/xml/output/{contractName}"
    assert output_descriptor["actions"][0]["inputBinding"] == "NONE"
    assert "submitAction(" in dashboard
    assert "runXmlIngest" not in dashboard
    assert "runXmlOutput" not in dashboard
    assert "app.xml-ingest.base-dir" in dashboard
    assert "app.xml-output.base-dir" in dashboard


def test_xml_xsd_ingest_scalar_type_conversion_is_compile_safe() -> None:
    expression = _xml_ingest_assignment_expression(
        model_var="xmlRecord",
        xml_field={
            "name": "availableBalance",
            "java_name": "availableBalance",
            "type": "string",
        },
        entity_field=CanonicalField(
            name="availableBalance",
            type=CanonicalFieldType.DECIMAL,
            required=True,
        ),
        entity_name="Account",
        xml_path="/AccountMessage/availableBalance",
    )

    assert 'asBigDecimalValue("availableBalance"' in expression
    assert (
        'requiredXmlValue("/AccountMessage/availableBalance", xmlRecord.getAvailableBalance(), '
        '"Account.availableBalance")'
    ) in expression


def test_xml_xsd_rejects_incompatible_mapping_types() -> None:
    contract = ContractMetadata(
        name="account-xml-inbound",
        type="xml-xsd",
        source="contracts/account.xsd",
        xml_contract={
            "root_element": "AccountMessage",
            "namespace": "urn:edgeforge:examples:account:v1",
            "xsd_path": "contracts/account.xsd",
            "attributes": [],
            "fields": [
                {
                    "name": "availableBalance",
                    "java_name": "availableBalance",
                    "kind": "element",
                    "type": "decimal",
                    "required": True,
                    "repeated": False,
                }
            ],
        },
    )
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True),
            CanonicalField(name="openedDate", type=CanonicalFieldType.DATE),
        ],
    )
    mapping = FieldMapping(
        contract_name="account-xml-inbound",
        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
        source_path="account-xml-inbound.xml.availableBalance",
        target_path="Account.openedDate",
    )

    with pytest.raises(ValueError, match="cannot map XML field 'availableBalance'"):
        _validate_xml_mappings_supported(
            contract=contract,
            mappings=[mapping],
            direction="upstream",
            entity=entity,
        )


def test_xml_xsd_missing_required_output_mapping_fails_generation(tmp_path: Path) -> None:
    source_fixture = Path("tests/fixtures/edgecontracts/xml-xsd/account-roundtrip-runtime")
    fixture = tmp_path / "xml-missing-output-mapping"
    shutil.copytree(source_fixture, fixture)
    mapping_path = fixture / "downstream/account-outbound-mapping.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    payload["field_mappings"] = [
        entry for entry in payload["field_mappings"] if entry["target"] != "accountNumber"
    ]
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(fixture / "app-definition.yaml")
    with pytest.raises(
        ValueError,
        match="XML/XSD interface 'account-xml-outbound' has invalid explicit mapping",
    ):
        generate_application(metadata, tmp_path / "generated-xml-missing-mapping")


def test_xml_xsd_missing_required_inbound_mapping_fails_generation(tmp_path: Path) -> None:
    source_fixture = Path("tests/fixtures/edgecontracts/xml-xsd/account-roundtrip-runtime")
    fixture = tmp_path / "xml-missing-inbound-mapping"
    shutil.copytree(source_fixture, fixture)
    mapping_path = fixture / "upstream/account-inbound-mapping.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    payload["field_mappings"] = [
        entry for entry in payload["field_mappings"] if entry["source"] != "accountNumber"
    ]
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(fixture / "app-definition.yaml")
    with pytest.raises(
        ValueError,
        match="Required XML/XSD field 'accountNumber' is not mapped",
    ):
        generate_application(metadata, tmp_path / "generated-xml-missing-inbound-mapping")


def test_soap_wsdl_contract_translates_to_metadata_and_requires_operation_mapping(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/edgecontracts/soap-wsdl/basic-customer-service/app-definition.yaml")
    metadata = build_metadata_project(fixture)

    contract = next(contract for contract in metadata.contracts if contract.name == "customer-soap-service")
    assert contract.type == "soap-wsdl"
    assert contract.soap_contract is not None
    assert contract.soap_contract["wsdl_path"] == "contracts/customer-service.wsdl"
    assert contract.soap_contract["target_namespace"] == "urn:edgeforge:examples:customer-soap:v1"
    assert contract.soap_contract["service"] == "CustomerService"
    assert contract.soap_contract["port"] == "CustomerServicePort"
    assert contract.soap_contract["binding"] == "CustomerSoapBinding"
    assert contract.soap_contract["operations"][0]["name"] == "getCustomer"
    assert contract.soap_contract["operations"][0]["soap_action"] == "urn:getCustomer"
    assert contract.soap_contract["direction"] == "upstream"
    assert "soap-contract: wsdl v1 parsed" in contract.ingestion_notes

    with pytest.raises(ValueError, match="requires an explicit operation mapping file"):
        generate_application(metadata, tmp_path / "generated-soap", source_manifest=str(fixture))


def test_soap_wsdl_inbound_endpoint_generation_emits_spring_ws_artifacts(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/basic-inbound-customer-service/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)

    contract = next(contract for contract in metadata.contracts if contract.name == "customer-soap-service")
    assert contract.soap_contract is not None
    assert contract.soap_contract["direction"] == "upstream"
    assert contract.soap_contract["operation_mappings"] == {
        "getCustomer": {
            "operation": "getCustomer",
            "mode": "adapter_only",
            "handler_method": "handleGetCustomer",
        }
    }

    output_dir = tmp_path / "generated-soap-inbound"
    report = generate_application(metadata, output_dir, source_manifest=str(fixture))

    endpoint_path = (
        output_dir
        / "src/main/java/com/appbuilder/soap_inbound_customer/adapter/soap/CustomerSoapServiceSoapEndpoint.java"
    )
    handler_path = (
        output_dir
        / "src/main/java/com/appbuilder/soap_inbound_customer/adapter/soap/CustomerSoapServiceSoapHandler.java"
    )
    config_path = (
        output_dir
        / "src/main/java/com/appbuilder/soap_inbound_customer/adapter/soap/SoapEndpointConfig.java"
    )
    application_yaml_path = output_dir / "src/main/resources/application.yaml"
    exception_path = (
        output_dir
        / "src/main/java/com/appbuilder/soap_inbound_customer/exception/SoapOperationMappingException.java"
    )
    wsdl_resource = (
        output_dir
        / "src/main/resources/soap-contracts/customer-soap-service/contracts/customer-service.wsdl"
    )
    xsd_resource = (
        output_dir
        / "src/main/resources/soap-contracts/customer-soap-service/contracts/customer-service-schema-1.xsd"
    )

    assert endpoint_path in report.files_created
    assert handler_path in report.files_created
    assert config_path in report.files_created
    assert exception_path in report.files_created
    assert wsdl_resource in report.files_created
    assert xsd_resource in report.files_created

    endpoint_source = endpoint_path.read_text(encoding="utf-8")
    handler_source = handler_path.read_text(encoding="utf-8")
    config_source = config_path.read_text(encoding="utf-8")
    application_yaml = application_yaml_path.read_text(encoding="utf-8")

    assert "@Endpoint" in endpoint_source
    assert '@PayloadRoot(namespace = NAMESPACE, localPart = "GetCustomerRequest")' in endpoint_source
    assert '@SoapAction("urn:getCustomer")' in endpoint_source
    assert "ObjectProvider<CustomerSoapServiceSoapHandler>" in endpoint_source
    assert '"/soap-contracts/customer-soap-service/contracts/customer-service-schema-1.xsd"' in endpoint_source
    assert "Source validatedPayload = validatePayload(requestPayload);" in endpoint_source
    assert "loadSchema().newValidator().validate(new DOMSource(document));" in endpoint_source
    assert "schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, \"\")" in endpoint_source
    assert "handler.handleGetCustomer(validatedPayload)" in endpoint_source
    assert "SoapOperationMappingException" in endpoint_source
    assert "configured as adapter-only" in endpoint_source
    assert "No canonical handler implementation is generated yet" in endpoint_source
    assert "provide handler bean 'CustomerSoapServiceSoapHandler'" in endpoint_source
    assert "Spring bean implementation" not in endpoint_source
    assert "Source handleGetCustomer(Source requestPayload) throws Exception;" in handler_source
    assert "MessageDispatcherServlet" not in config_source
    assert "ServletRegistrationBean" not in config_source
    assert "edgeForgeSoapMessageDispatcherServletRegistration" not in config_source
    assert "messageDispatcherServlet(ApplicationContext applicationContext)" not in config_source
    assert '@Bean(name = "messageFactory")' in config_source
    assert "HardenedSaajSoapMessageFactory extends SaajSoapMessageFactory" in config_source
    assert '@Value("${app.soap.max-envelope-bytes:1048576}") int maxEnvelopeBytes' in config_source
    assert "inputStream.readAllBytes()" not in config_source
    assert "readBoundedEnvelope(inputStream)" in config_source
    assert "SOAP envelope exceeds configured maximum of " in config_source
    assert "ReplayTransportInputStream extends TransportInputStream" in config_source
    assert "return source.getHeaderNames();" in config_source
    assert "return source.getHeaders(name);" in config_source
    assert "validateEnvelopeBeforeSaaj(envelope);" in config_source
    assert "factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);" in config_source
    assert "factory.setFeature(DISALLOW_DOCTYPE_DECL, true);" in config_source
    assert "factory.setFeature(EXTERNAL_GENERAL_ENTITIES, false);" in config_source
    assert "factory.setFeature(EXTERNAL_PARAMETER_ENTITIES, false);" in config_source
    assert "factory.setFeature(LOAD_EXTERNAL_DTD, false);" in config_source
    assert 'reader.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");' in config_source
    assert 'reader.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");' in config_source
    assert 'reader.setProperty(ENTITY_EXPANSION_LIMIT, "256");' in config_source
    assert "reader.setErrorHandler(handler);" in config_source
    assert 'throw new SoapMessageCreationException("Rejected unsafe SOAP/XML envelope.", ex);' in config_source
    assert '@Bean(name = "messageReceiverHandlerAdapter")' in config_source
    assert "EdgeForgeSoapMessageReceiverHandlerAdapter" in config_source
    assert "public void afterPropertiesSet()" in config_source
    assert "public ModelAndView handle(HttpServletRequest request, HttpServletResponse response, Object handler)" in config_source
    assert "catch (SoapMessageCreationException ex)" in config_source
    assert "writeMalformedSoapFault(response, ex)" in config_source
    assert "Malformed SOAP/XML request" in config_source
    assert "edgeForgeSoapPayloadEndpointAdapter" in config_source
    assert "edgeForgeUnknownSoapOperationEndpointMapping" in config_source
    assert "Unknown SOAP operation for generated SOAP WSDL runtime" in config_source
    assert "No generated SOAP endpoint matched the request payload" in config_source
    assert "EdgeForgeSoapFaultExceptionResolver" in config_source
    assert "safeSoapDiagnostic" in config_source
    assert "printStackTrace" not in config_source
    assert "getStackTrace" not in config_source
    assert "SimpleWsdl11Definition" in config_source
    assert '"soap-contracts/customer-soap-service/contracts/customer-service.wsdl"' in config_source
    assert "  webservices:\n    path: /ws" in application_yaml
    assert "        transformWsdlLocations: true" in application_yaml
    assert "    max-envelope-bytes: ${APP_SOAP_MAX_ENVELOPE_BYTES:1048576}" in application_yaml
    packaged_wsdl = wsdl_resource.read_text(encoding="utf-8")
    assert "https://example.invalid/customer" not in packaged_wsdl
    assert 'location="http://localhost:8080/ws"' in packaged_wsdl
    assert 'xmlns:tns="urn:edgeforge:examples:customer-soap:v1"' in packaged_wsdl
    assert 'element="tns:GetCustomerRequest"' in packaged_wsdl


def test_soap_wsdl_canonical_read_by_id_generation_emits_handler(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)

    contract = next(contract for contract in metadata.contracts if contract.name == "customer-soap-service")
    assert contract.soap_contract is not None
    operation = contract.soap_contract["operations"][0]
    assert list(operation["input_fields"]) == [
        {
            "name": "customerId",
            "path": "/GetCustomerRequest/customerId",
            "kind": "element",
            "type": "string",
            "required": True,
            "repeated": False,
        }
    ]
    assert {
        "name": "status",
        "path": "/GetCustomerResponse/status",
        "kind": "element",
        "type": "string",
        "required": True,
        "repeated": False,
    } in operation["output_fields"]
    assert contract.soap_contract["operation_mappings"]["getCustomer"]["mode"] == "canonical"
    assert (
        contract.soap_contract["operation_mappings"]["getCustomer"]["canonical_operation"]["kind"]
        == "read_by_id"
    )

    output_dir = tmp_path / "generated-soap-canonical-read"
    report = generate_application(metadata, output_dir, source_manifest=str(fixture))

    handler_path = (
        output_dir
        / "src/main/java/com/appbuilder/soap_canonical_customer/adapter/soap/CustomerSoapServiceCanonicalSoapHandler.java"
    )
    endpoint_path = (
        output_dir
        / "src/main/java/com/appbuilder/soap_canonical_customer/adapter/soap/CustomerSoapServiceSoapEndpoint.java"
    )
    assert handler_path in report.files_created

    handler_source = handler_path.read_text(encoding="utf-8")
    endpoint_source = endpoint_path.read_text(encoding="utf-8")

    assert "class CustomerSoapServiceCanonicalSoapHandler implements CustomerSoapServiceSoapHandler" in handler_source
    assert "private final CustomerRepository customerRepository;" in handler_source
    assert "String customerIdRaw = requiredText(requestDocument, \"/GetCustomerRequest/customerId\");" in handler_source
    assert "String customerId = customerIdRaw;" in handler_source
    assert "customerRepository.findById(customerId)" in handler_source
    assert "Customer not found for id:" in handler_source
    assert "buildGetCustomerResponse(record)" in handler_source
    assert "appendElement(document, root, \"customerId\", customerIdValue0);" in handler_source
    assert "appendElement(document, root, \"status\", statusValue1);" in handler_source
    assert "validateResponse(document);" in handler_source
    assert "return new DOMSource(document);" in handler_source
    assert "configured as adapter-only" not in handler_source
    assert "ObjectProvider<CustomerSoapServiceSoapHandler>" in endpoint_source
    assert "return handler.handleGetCustomer(validatedPayload);" in endpoint_source


def test_soap_wsdl_canonical_read_by_id_emits_response_in_wsdl_sequence_order(
    tmp_path: Path,
) -> None:
    source_fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service"
    )
    fixture = tmp_path / "soap-canonical-reversed-response-order"
    shutil.copytree(source_fixture, fixture)
    mapping_path = fixture / "mappings/customer-soap-operation-mapping.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    payload["operation_mappings"][0]["canonical_operation"]["response_mappings"] = list(
        reversed(payload["operation_mappings"][0]["canonical_operation"]["response_mappings"])
    )
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(fixture / "app-definition.yaml")
    output_dir = tmp_path / "generated-soap-reversed-response-order"
    generate_application(
        metadata,
        output_dir,
        source_manifest=str(fixture / "app-definition.yaml"),
    )

    handler_source = (
        output_dir
        / "src/main/java/com/appbuilder/soap_canonical_customer/adapter/soap/CustomerSoapServiceCanonicalSoapHandler.java"
    ).read_text(encoding="utf-8")
    assert handler_source.index('appendElement(document, root, "customerId"') < handler_source.index(
        'appendElement(document, root, "status"'
    )


def test_soap_wsdl_canonical_read_by_id_rejects_root_text_lookup_path(
    tmp_path: Path,
) -> None:
    source_fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service"
    )
    fixture = tmp_path / "soap-canonical-root-text-lookup"
    shutil.copytree(source_fixture, fixture)
    mapping_path = fixture / "mappings/customer-soap-operation-mapping.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    payload["operation_mappings"][0]["canonical_operation"]["lookup"][
        "request_path"
    ] = "/GetCustomerRequest"
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    wsdl_path = fixture / "contracts/customer-service.wsdl"
    wsdl_source = wsdl_path.read_text(encoding="utf-8")
    wsdl_path.write_text(
        wsdl_source.replace(
            """      <xs:element name="GetCustomerRequest">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="customerId" type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>""",
            '      <xs:element name="GetCustomerRequest" type="xs:string"/>',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="root text and nested complex paths are fail-fast"):
        build_metadata_project(fixture / "app-definition.yaml")


def test_soap_wsdl_canonical_read_by_id_requires_persistence_id_lookup(
    tmp_path: Path,
) -> None:
    source_fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service"
    )
    fixture = tmp_path / "soap-canonical-non-id"
    shutil.copytree(source_fixture, fixture)
    mapping_path = fixture / "mappings/customer-soap-operation-mapping.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    payload["operation_mappings"][0]["canonical_operation"]["lookup"]["field"] = "status"
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(fixture / "app-definition.yaml")
    with pytest.raises(ValueError, match="must be the persistence ID"):
        generate_application(metadata, tmp_path / "generated-soap-non-id", source_manifest=str(fixture))


def test_soap_wsdl_canonical_read_by_id_requires_required_response_mappings(
    tmp_path: Path,
) -> None:
    source_fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service"
    )
    fixture = tmp_path / "soap-canonical-missing-response"
    shutil.copytree(source_fixture, fixture)
    mapping_path = fixture / "mappings/customer-soap-operation-mapping.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    payload["operation_mappings"][0]["canonical_operation"]["response_mappings"] = [
        mapping
        for mapping in payload["operation_mappings"][0]["canonical_operation"]["response_mappings"]
        if mapping["target_path"] != "/GetCustomerResponse/status"
    ]
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="missing response mappings for required SOAP field"):
        build_metadata_project(fixture / "app-definition.yaml")


def test_soap_wsdl_canonical_read_by_id_rejects_type_mismatch(
    tmp_path: Path,
) -> None:
    source_fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service"
    )
    fixture = tmp_path / "soap-canonical-type-mismatch"
    shutil.copytree(source_fixture, fixture)
    api_path = fixture / "upstream/customer-api-spec.yaml"
    api_payload = yaml.safe_load(api_path.read_text(encoding="utf-8"))
    api_payload["components"]["schemas"]["CreateCustomerRequest"]["properties"]["status"] = {
        "type": "number"
    }
    api_payload["components"]["schemas"]["Customer"]["properties"]["status"] = {
        "type": "number"
    }
    api_path.write_text(yaml.safe_dump(api_payload, sort_keys=False), encoding="utf-8")
    (fixture / "upstream/create-customer-request.json").write_text(
        '{\n  "customerName": "Ada Lovelace",\n  "status": 10\n}\n',
        encoding="utf-8",
    )
    (fixture / "upstream/customer-response.json").write_text(
        '{\n  "customerId": "11111111-1111-1111-1111-111111111111",\n  "customerName": "Ada Lovelace",\n  "status": 10\n}\n',
        encoding="utf-8",
    )
    wsdl_path = fixture / "contracts/customer-service.wsdl"
    wsdl_source = wsdl_path.read_text(encoding="utf-8")
    wsdl_path.write_text(
        wsdl_source.replace('<xs:element name="status" type="xs:string"/>', '<xs:element name="status" type="xs:date"/>'),
        encoding="utf-8",
    )

    metadata = build_metadata_project(fixture / "app-definition.yaml")
    with pytest.raises(ValueError, match="cannot map canonical field 'Customer.status'"):
        generate_application(
            metadata,
            tmp_path / "generated-soap-type-mismatch",
            source_manifest=str(fixture / "app-definition.yaml"),
        )


def test_soap_wsdl_operation_mapping_rejects_canonical_block_in_adapter_only_mode(
    tmp_path: Path,
) -> None:
    source_fixture = Path("tests/fixtures/edgecontracts/soap-wsdl/basic-inbound-customer-service")
    fixture = tmp_path / "soap-adapter-canonical-block"
    shutil.copytree(source_fixture, fixture)
    mapping_path = fixture / "mappings/customer-soap-operation-mapping.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    payload["operation_mappings"][0]["mode"] = "adapter_only"
    payload["operation_mappings"][0]["canonical_operation"] = {"kind": "read_by_id"}
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot declare canonical_operation when mode is adapter_only"):
        build_metadata_project(fixture / "app-definition.yaml")


def test_soap_wsdl_operation_mapping_rejects_invalid_mode(tmp_path: Path) -> None:
    source_fixture = Path("tests/fixtures/edgecontracts/soap-wsdl/basic-inbound-customer-service")
    fixture = tmp_path / "soap-invalid-mode"
    shutil.copytree(source_fixture, fixture)
    mapping_path = fixture / "mappings/customer-soap-operation-mapping.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    payload["operation_mappings"][0]["mode"] = "magic"
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported operation mapping mode 'magic'"):
        build_metadata_project(fixture / "app-definition.yaml")


def test_soap_wsdl_canonical_operation_rejects_unsupported_kind(tmp_path: Path) -> None:
    source_fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service"
    )
    fixture = tmp_path / "soap-unsupported-canonical-kind"
    shutil.copytree(source_fixture, fixture)
    mapping_path = fixture / "mappings/customer-soap-operation-mapping.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    payload["operation_mappings"][0]["canonical_operation"]["kind"] = "create"
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="Only read_by_id is supported"):
        build_metadata_project(fixture / "app-definition.yaml")


def test_soap_wsdl_inbound_endpoint_generation_fails_without_operation_mapping(
    tmp_path: Path,
) -> None:
    fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/basic-inbound-missing-operation-mapping/app-definition.yaml"
    )
    metadata = build_metadata_project(fixture)

    with pytest.raises(ValueError, match="requires an explicit operation mapping file"):
        generate_application(metadata, tmp_path / "generated-soap-missing-mapping", source_manifest=str(fixture))


def test_soap_wsdl_downstream_client_generation_emits_spring_ws_client_artifacts(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/edgecontracts/soap-wsdl/basic-outbound-customer-client/app-definition.yaml")
    metadata = build_metadata_project(fixture)

    contract = next(contract for contract in metadata.contracts if contract.name == "customer-soap-client")
    assert contract.soap_contract is not None
    assert contract.soap_contract["direction"] == "downstream"

    output_dir = tmp_path / "generated-soap-client"
    report = generate_application(metadata, output_dir, source_manifest=str(fixture))

    client_path = (
        output_dir
        / "src/main/java/com/appbuilder/soap_outbound_customer/adapter/soap/CustomerSoapClientSoapClient.java"
    )
    config_path = (
        output_dir
        / "src/main/java/com/appbuilder/soap_outbound_customer/adapter/soap/SoapClientConfig.java"
    )
    exception_path = (
        output_dir
        / "src/main/java/com/appbuilder/soap_outbound_customer/exception/SoapClientException.java"
    )
    wsdl_resource = (
        output_dir
        / "src/main/resources/soap-contracts/customer-soap-client/contracts/customer-service.wsdl"
    )
    xsd_resource = (
        output_dir
        / "src/main/resources/soap-contracts/customer-soap-client/contracts/customer-service-schema-1.xsd"
    )
    application_yaml_path = output_dir / "src/main/resources/application.yaml"

    assert client_path in report.files_created
    assert config_path in report.files_created
    assert exception_path in report.files_created
    assert wsdl_resource in report.files_created
    assert xsd_resource in report.files_created

    client_source = client_path.read_text(encoding="utf-8")
    config_source = config_path.read_text(encoding="utf-8")
    exception_source = exception_path.read_text(encoding="utf-8")
    application_yaml = application_yaml_path.read_text(encoding="utf-8")
    packaged_wsdl = wsdl_resource.read_text(encoding="utf-8")

    assert "@Component" in client_source
    assert "WebServiceTemplate webServiceTemplate" in client_source
    assert '@Value("${app.soap.clients.customer-soap-client.uri}") String endpointUri' in client_source
    assert "public Source getCustomer(Source requestPayload)" in client_source
    assert 'validatePayload(\n                requestPayload,\n                "urn:edgeforge:examples:customer-soap:v1",\n                "GetCustomerRequest",' in client_source
    assert "webServiceTemplate.sendSourceAndReceive(" in client_source
    assert 'applySoapAction(message, "urn:getCustomer")' in client_source
    assert 'validatePayload(\n                response,\n                "urn:edgeforge:examples:customer-soap:v1",\n                "GetCustomerResponse",' in client_source
    assert "validateRootElement(document, expectedNamespace, expectedLocalName, operationName, direction);" in client_source
    assert "expected \" + direction + \" root" in client_source
    assert "schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, \"\")" in client_source
    assert "throw new SoapClientException(" in client_source
    assert "public WebServiceTemplate webServiceTemplate()" in config_source
    assert "class SoapClientException extends RuntimeException" in exception_source
    assert "  soap:\n    clients:\n      customer-soap-client:" in application_yaml
    assert "        uri: http://localhost:8080/ws" in application_yaml
    assert "  webservices:" not in application_yaml
    assert 'location="https://example.invalid/customer"' in packaged_wsdl
    assert 'xmlns:tns="urn:edgeforge:examples:customer-soap:v1"' in packaged_wsdl


def test_soap_wsdl_endpoint_generation_deduplicates_colliding_operation_method_names(
    tmp_path: Path,
) -> None:
    fixture = _write_colliding_soap_operations_fixture(tmp_path, duplicate_handler=False)
    metadata = build_metadata_project(fixture)

    output_dir = tmp_path / "generated-soap-collisions"
    generate_application(metadata, output_dir, source_manifest=str(fixture))

    endpoint_source = (
        output_dir
        / "src/main/java/com/appbuilder/soap_collision/adapter/soap/CustomerSoapServiceSoapEndpoint.java"
    ).read_text(encoding="utf-8")
    handler_source = (
        output_dir
        / "src/main/java/com/appbuilder/soap_collision/adapter/soap/CustomerSoapServiceSoapHandler.java"
    ).read_text(encoding="utf-8")

    assert "public Source getCustomer(@RequestPayload Source requestPayload)" in endpoint_source
    assert "public Source getCustomer2(@RequestPayload Source requestPayload)" in endpoint_source
    assert "Source handleGetCustomerFromKebab(Source requestPayload) throws Exception;" in handler_source
    assert "Source handleGetCustomerFromCamel(Source requestPayload) throws Exception;" in handler_source


def test_soap_wsdl_endpoint_generation_rejects_colliding_handler_method_names(
    tmp_path: Path,
) -> None:
    fixture = _write_colliding_soap_operations_fixture(tmp_path, duplicate_handler=True)
    metadata = build_metadata_project(fixture)

    with pytest.raises(ValueError, match="normalize to Java handler method 'handleGetCustomer'"):
        generate_application(metadata, tmp_path / "generated-soap-handler-collision", source_manifest=str(fixture))


def test_soap_wsdl_contract_rejects_unknown_operation_during_translation(
    tmp_path: Path,
) -> None:
    source_fixture = Path("tests/fixtures/edgecontracts/soap-wsdl/basic-customer-service")
    fixture = tmp_path / "bad-soap-operation"
    shutil.copytree(source_fixture, fixture)
    sample = fixture / "request.xml"
    sample.write_text("<request/>", encoding="utf-8")
    manifest = fixture / "app-definition.yaml"
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    payload["upstream_interfaces"][0]["operations"] = [
        {"name": "missingOperation", "request_sample": "request.xml"}
    ]
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="requested operation 'missingOperation' was not found"):
        build_metadata_project(manifest)


def test_soap_wsdl_contract_rejects_unsupported_runtime_for_kafka_archetype(
    tmp_path: Path,
) -> None:
    source_fixture = Path("tests/fixtures/edgecontracts/soap-wsdl/basic-customer-service")
    fixture = tmp_path / "kafka-soap"
    shutil.copytree(source_fixture, fixture)
    manifest = fixture / "app-definition.yaml"
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    payload["app_archetype"] = "kafka-integration"
    payload["kafka_config"] = {"consumer_group": "soap-test"}
    payload["async_routes"] = [
        {
            "name": "noop",
            "pattern": "fire-and-forget",
            "upstream_topic": {
                "name": "in",
                "system": "CORE",
                "message_schema": "schemas/in.json",
            },
            "downstream_topic": {
                "name": "out",
                "system": "DOWNSTREAM",
                "message_schema": "schemas/out.json",
            },
            "transform_mapping": "mappings/noop.yaml",
        }
    ]
    (fixture / "schemas").mkdir()
    (fixture / "schemas" / "in.json").write_text("{}", encoding="utf-8")
    (fixture / "schemas" / "out.json").write_text("{}", encoding="utf-8")
    (fixture / "mappings").mkdir()
    (fixture / "mappings" / "noop.yaml").write_text("field_mappings: []\n", encoding="utf-8")
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="SOAP/WSDL runtime generation is not implemented yet for app_archetype: kafka-integration",
    ):
        build_metadata_project(manifest)


def _write_file_only_contract_fixture(
    tmp_path: Path,
    *,
    file_type: str,
    include_downstream: bool = True,
) -> Path:
    fixture = tmp_path / f"file-only-{file_type}"
    upstream_dir = fixture / "upstream"
    downstream_dir = fixture / "downstream"
    upstream_dir.mkdir(parents=True)
    if include_downstream:
        downstream_dir.mkdir(parents=True)
    if file_type == "file-fixed-width":
        layout = "\n".join(
            [
                "fields:",
                "  - name: account_id",
                "    length: 12",
                "    required: true",
                "  - name: status",
                "    length: 10",
                "    required: true",
            ]
        )
    elif file_type == "file-csv":
        layout = "\n".join(
            [
                "format: csv",
                "delimiter: \",\"",
                "quote_char: '\"'",
                "escape_char: \"\\\\\"",
                "has_header_row: true",
                "record_types:",
                "  data:",
                "    fields:",
                "      - name: account_id",
                "        column: 1",
                "        type: string",
                "        required: true",
                "      - name: status",
                "        column: 2",
                "        type: string",
                "        required: true",
            ]
        )
    else:
        raise AssertionError(f"Unsupported file fixture type: {file_type}")
    (upstream_dir / "account-layout.yaml").write_text(layout, encoding="utf-8")
    (upstream_dir / "account-mapping.yaml").write_text(
        "\n".join(
            [
                "entity: Account",
                "direction: inbound",
                "field_mappings:",
                "  - source: account_id",
                "    target: Account.accountId",
                "  - source: status",
                "    target: Account.status",
            ]
        ),
        encoding="utf-8",
    )
    manifest_lines = [
        "app_name: File Only Edge Contract",
        "bounded_context: file_only_contract",
        "schema_version: \"2.0\"",
        "app_archetype: crud",
        "target_profile: springboot-legacy-compatible",
        "upstream_interfaces:",
        "  - name: account-inbound-file",
        "    system: CORE",
        f"    type: {file_type}",
        "    spec: upstream/account-layout.yaml",
        "    mapping: upstream/account-mapping.yaml",
    ]
    if include_downstream:
        (downstream_dir / "account-layout.yaml").write_text(layout, encoding="utf-8")
        (downstream_dir / "account-mapping.yaml").write_text(
            "\n".join(
                [
                    "entity: Account",
                    "direction: outbound",
                    "field_mappings:",
                    "  - source: Account.accountId",
                    "    target: account_id",
                    "  - source: Account.status",
                    "    target: status",
                ]
            ),
            encoding="utf-8",
        )
        manifest_lines.extend(
            [
                "downstream_interfaces:",
                "  - name: account-outbound-file",
                "    system: ARCHIVE",
                f"    type: {file_type}",
                "    spec: downstream/account-layout.yaml",
                "    mapping: downstream/account-mapping.yaml",
            ]
        )
    (fixture / "app-definition.yaml").write_text(
        "\n".join(manifest_lines),
        encoding="utf-8",
    )
    return fixture / "app-definition.yaml"


def _write_colliding_soap_operations_fixture(tmp_path: Path, *, duplicate_handler: bool) -> Path:
    fixture = tmp_path / ("soap-handler-collision" if duplicate_handler else "soap-operation-collision")
    contracts_dir = fixture / "contracts"
    mappings_dir = fixture / "mappings"
    contracts_dir.mkdir(parents=True)
    mappings_dir.mkdir(parents=True)
    (fixture / "app-definition.yaml").write_text(
        """app_name: SOAP Collision
bounded_context: soap_collision
schema_version: "2.0"
upstream_interfaces:
  - name: customer-soap-service
    system: CORE
    type: soap-wsdl
    wsdl_path: contracts/customer-service.wsdl
    service: CustomerService
    port: CustomerServicePort
    mapping: mappings/customer-soap-operation-mapping.yaml
target_profile: springboot-legacy-compatible
""",
        encoding="utf-8",
    )
    first_handler = "handleGetCustomer" if duplicate_handler else "handleGetCustomerFromKebab"
    second_handler = "handleGetCustomer" if duplicate_handler else "handleGetCustomerFromCamel"
    (mappings_dir / "customer-soap-operation-mapping.yaml").write_text(
        f"""operation_mappings:
  - operation: get-customer
    handler_method: {first_handler}
  - operation: getCustomer
    handler_method: {second_handler}
""",
        encoding="utf-8",
    )
    (contracts_dir / "customer-service.wsdl").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:edgeforge:examples:customer-soap:v1"
    targetNamespace="urn:edgeforge:examples:customer-soap:v1">
  <wsdl:types>
    <xs:schema targetNamespace="urn:edgeforge:examples:customer-soap:v1"
               xmlns:xs="http://www.w3.org/2001/XMLSchema"
               xmlns:tns="urn:edgeforge:examples:customer-soap:v1"
               elementFormDefault="qualified">
      <xs:element name="GetCustomerRequest">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="customerId" type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
      <xs:element name="GetCustomerResponse">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="customerId" type="xs:string"/>
            <xs:element name="status" type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>
  </wsdl:types>
  <wsdl:message name="GetCustomerRequestMessage">
    <wsdl:part name="parameters" element="tns:GetCustomerRequest"/>
  </wsdl:message>
  <wsdl:message name="GetCustomerResponseMessage">
    <wsdl:part name="parameters" element="tns:GetCustomerResponse"/>
  </wsdl:message>
  <wsdl:portType name="CustomerPortType">
    <wsdl:operation name="get-customer">
      <wsdl:input message="tns:GetCustomerRequestMessage"/>
      <wsdl:output message="tns:GetCustomerResponseMessage"/>
    </wsdl:operation>
    <wsdl:operation name="getCustomer">
      <wsdl:input message="tns:GetCustomerRequestMessage"/>
      <wsdl:output message="tns:GetCustomerResponseMessage"/>
    </wsdl:operation>
  </wsdl:portType>
  <wsdl:binding name="CustomerSoapBinding" type="tns:CustomerPortType">
    <soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="get-customer">
      <soap:operation soapAction="urn:get-customer"/>
      <wsdl:input><soap:body use="literal"/></wsdl:input>
      <wsdl:output><soap:body use="literal"/></wsdl:output>
    </wsdl:operation>
    <wsdl:operation name="getCustomer">
      <soap:operation soapAction="urn:getCustomer"/>
      <wsdl:input><soap:body use="literal"/></wsdl:input>
      <wsdl:output><soap:body use="literal"/></wsdl:output>
    </wsdl:operation>
  </wsdl:binding>
  <wsdl:service name="CustomerService">
    <wsdl:port name="CustomerServicePort" binding="tns:CustomerSoapBinding">
      <soap:address location="https://example.invalid/customer"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>
""",
        encoding="utf-8",
    )
    return fixture / "app-definition.yaml"


def test_xml_xsd_runtime_sanitizes_java_names_and_copies_relative_includes(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "xml-name-collision"
    contracts_dir = fixture / "contracts"
    message_dir = contracts_dir / "messages"
    message_dir.mkdir(parents=True)
    (contracts_dir / "common.xsd").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:edgeforge:examples:xml-name:v1"
           xmlns:tns="urn:edgeforge:examples:xml-name:v1">
  <xs:simpleType name="StatusCode">
    <xs:restriction base="xs:string">
      <xs:enumeration value="ACTIVE"/>
      <xs:enumeration value="ON-HOLD"/>
    </xs:restriction>
  </xs:simpleType>
</xs:schema>
""",
        encoding="utf-8",
    )
    (message_dir / "customer-message.xsd").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:edgeforge:examples:xml-name:v1"
           xmlns:tns="urn:edgeforge:examples:xml-name:v1"
           elementFormDefault="qualified">
  <xs:include schemaLocation="../common.xsd"/>
  <xs:element name="CustomerMessage">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="id" type="xs:string"/>
        <xs:element name="customer-id" type="xs:string"/>
        <xs:element name="display-name" type="xs:string" minOccurs="0"/>
        <xs:element name="status-code" type="tns:StatusCode"/>
      </xs:sequence>
      <xs:attribute name="id" type="xs:string" use="required"/>
    </xs:complexType>
  </xs:element>
</xs:schema>
""",
        encoding="utf-8",
    )
    manifest = fixture / "app-definition.yaml"
    manifest.write_text(
        """app_name: XML Name Collision
bounded_context: xml_names
schema_version: "2.0"
upstream_interfaces:
  - name: customer-xml-input
    system: CORE
    type: xml-xsd
    xsd_path: contracts/messages/customer-message.xsd
    root_element: CustomerMessage
    namespace: "urn:edgeforge:examples:xml-name:v1"
target_profile: springboot-legacy-compatible
""",
        encoding="utf-8",
    )

    metadata = build_metadata_project(manifest)
    contract = next(contract for contract in metadata.contracts if contract.name == "customer-xml-input")
    assert contract.xml_contract is not None
    assert set(contract.xml_contract["xsd_paths"]) == {
        "contracts/common.xsd",
        "contracts/messages/customer-message.xsd",
    }

    output_dir = tmp_path / "generated-xml"
    generate_application(metadata, output_dir, source_manifest=str(manifest))

    model_source = (
        output_dir
        / "src/main/java/com/appbuilder/xml_names/adapter/xml/CustomerXmlInputXmlModel.java"
    ).read_text(encoding="utf-8")
    parser_source = (
        output_dir
        / "src/main/java/com/appbuilder/xml_names/adapter/xml/CustomerXmlInputXmlParser.java"
    ).read_text(encoding="utf-8")
    serializer_source = (
        output_dir
        / "src/main/java/com/appbuilder/xml_names/adapter/xml/CustomerXmlInputXmlSerializer.java"
    ).read_text(encoding="utf-8")

    assert "private String idAttribute;" in model_source
    assert "private String idElement;" in model_source
    assert "private String customerId;" in model_source
    assert "private String displayName;" in model_source
    assert "public enum StatusCodeValue" in model_source
    assert "ON_HOLD(\"ON-HOLD\")" in model_source
    assert "root.hasAttribute(\"id\")" in parser_source
    assert "model.setIdAttribute" in parser_source
    assert "model.setIdElement" in parser_source
    assert "childElements(root, \"customer-id\")" in parser_source
    assert "root.setAttribute(\"id\", String.valueOf(model.getIdAttribute()))" in serializer_source
    assert (
        output_dir
        / "src/main/resources/xml-contracts/customer-xml-input/contracts/common.xsd"
    ).exists()
    assert (
        output_dir
        / "src/main/resources/xml-contracts/customer-xml-input/contracts/messages/customer-message.xsd"
    ).exists()


def test_xml_xsd_contract_rejects_unknown_root_during_translation(
    tmp_path: Path,
) -> None:
    source_fixture = Path("tests/fixtures/edgecontracts/xml-xsd/basic-customer")
    fixture = tmp_path / "bad-root"
    shutil.copytree(source_fixture, fixture)
    manifest = fixture / "app-definition.yaml"
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    payload["upstream_interfaces"][0]["root_element"] = "MissingRoot"
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="root element 'MissingRoot' was not found"):
        build_metadata_project(manifest)


def test_xml_xsd_contract_rejects_unsupported_runtime_for_kafka_archetype(
    tmp_path: Path,
) -> None:
    source_fixture = Path("tests/fixtures/edgecontracts/xml-xsd/basic-customer")
    fixture = tmp_path / "kafka-xml"
    shutil.copytree(source_fixture, fixture)
    manifest = fixture / "app-definition.yaml"
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    payload["app_archetype"] = "kafka-integration"
    payload["kafka_config"] = {"consumer_group": "xml-test"}
    payload["async_routes"] = [
        {
            "name": "noop",
            "pattern": "fire-and-forget",
            "upstream_topic": {
                "name": "in",
                "system": "CORE",
                "message_schema": "schemas/in.json",
            },
            "downstream_topic": {
                "name": "out",
                "system": "DOWNSTREAM",
                "message_schema": "schemas/out.json",
            },
            "transform_mapping": "mappings/noop.yaml",
        }
    ]
    (fixture / "schemas").mkdir()
    (fixture / "schemas" / "in.json").write_text("{}", encoding="utf-8")
    (fixture / "schemas" / "out.json").write_text("{}", encoding="utf-8")
    (fixture / "mappings").mkdir()
    (fixture / "mappings" / "noop.yaml").write_text("field_mappings: []\n", encoding="utf-8")
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="XML/XSD runtime generation is not implemented yet for app_archetype: kafka-integration",
    ):
        build_metadata_project(manifest)


def test_xml_xsd_contract_rejects_runtime_for_passthrough_generation(
    tmp_path: Path,
) -> None:
    metadata = MetadataProject(
        app_name="XML Passthrough",
        bounded_context="xml_passthrough",
        schema_version="2.0",
        app_archetype=AppArchetype.PASSTHROUGH_ROUTER,
        target_profile="springboot-legacy-compatible",
        systems=[],
        contracts=[
            ContractMetadata(
                name="customer-xml-input",
                type="xml-xsd",
                source="contracts/customer.xsd",
                xml_contract={
                    "root_element": "CustomerMessage",
                    "namespace": "urn:edgeforge:examples:customer:v1",
                    "xsd_path": "contracts/customer.xsd",
                    "fields": [],
                    "attributes": [],
                },
            )
        ],
        operations=[],
        entities=[],
        mappings=[],
        mapping_reports=[],
        rules=[],
        relationships=[],
    )

    with pytest.raises(
        ValueError,
        match="XML/XSD runtime generation is currently implemented only for app_archetype: crud",
    ):
        generate_application(metadata, tmp_path / "generated-passthrough-xml")


def _two_entity_metadata() -> MetadataProject:
    """Minimal two-entity (Customer + Account) MetadataProject for multi-entity tests."""
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        CanonicalOperation,
        ContractMetadata,
        SystemParticipant,
    )

    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=12),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True, max_length=50),
            CanonicalField(name="email", type=CanonicalFieldType.STRING, required=False, max_length=100),
        ],
    )
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=12),
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, required=True, max_length=12),
            CanonicalField(name="accountType", type=CanonicalFieldType.STRING, required=True, max_length=10,
                           allowed_values=["CHQ", "SAV"]),
            CanonicalField(name="balance", type=CanonicalFieldType.DECIMAL, required=False),
        ],
    )

    customer_create_op = CanonicalOperation(
        name="createCustomer",
        interface_name="crm-customer-api",
        request_entity="Customer",
        response_entity="Customer",
    )
    account_create_op = CanonicalOperation(
        name="createAccount",
        interface_name="crm-account-api",
        request_entity="Account",
        response_entity="Account",
    )

    customer_mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="crm-customer-api",
            operation_name="createCustomer",
            source_path="crm-customer-api.createCustomer.request.customerName",
            target_path="Customer.customerName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="crm-customer-api",
            operation_name="createCustomer",
            source_path="crm-customer-api.createCustomer.response.customerId",
            target_path="Customer.customerId",
        ),
    ]
    account_mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="crm-account-api",
            operation_name="createAccount",
            source_path="crm-account-api.createAccount.request.accountType",
            target_path="Account.accountType",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="crm-account-api",
            operation_name="createAccount",
            source_path="crm-account-api.createAccount.response.accountId",
            target_path="Account.accountId",
        ),
    ]

    return MetadataProject(
        app_name="CRM App",
        bounded_context="crm",
        target_profile="springboot-legacy-compatible",
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[
            ContractMetadata(name="crm-customer-api", type="rest-json", source=""),
            ContractMetadata(name="crm-account-api", type="rest-json", source=""),
        ],
        operations=[customer_create_op, account_create_op],
        entities=[customer, account],
        mappings=customer_mappings + account_mappings,
    )


def _load_xyz_metadata_with_profile(
    profile_name: str,
    *,
    emit_security: bool = False,
    emit_test_console: bool = True,
    emit_audit: bool = False,
) -> MetadataProject:
    metadata = _load_xyz_metadata()
    metadata.target_profile = profile_name
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=True,
        emit_spring_batch=True,
        emit_security=emit_security,
        emit_test_console=emit_test_console,
        emit_audit=emit_audit,
        supports_xml=True,
    )
    return metadata


def _build_audit_collision_metadata(
    profile_name: str,
    *,
    collision_fields: list[CanonicalField],
) -> MetadataProject:
    entity = CanonicalEntity(
        name="LedgerEntry",
        fields=[
            CanonicalField(
                name="ledgerEntryId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=36,
                source_paths=["ledger-api.createLedgerEntry.response.ledgerEntryId"],
            ),
            *collision_fields,
        ],
    )
    operation = CanonicalOperation(
        name="createLedgerEntry",
        interface_name="ledger-api",
        request_entity="LedgerEntry",
        response_entity="LedgerEntry",
    )
    mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="ledger-api",
            operation_name="createLedgerEntry",
            source_path="ledger-api.createLedgerEntry.response.ledgerEntryId",
            target_path="LedgerEntry.ledgerEntryId",
        ),
    ]
    for field in collision_fields:
        mappings.append(
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="ledger-api",
                operation_name="createLedgerEntry",
                source_path=f"ledger-api.createLedgerEntry.response.{field.name}",
                target_path=f"LedgerEntry.{field.name}",
            )
        )

    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=True,
        emit_spring_batch=True,
        emit_security=False,
        emit_audit=True,
        supports_xml=True,
    )
    return MetadataProject(
        app_name="Ledger Entry Collision Test",
        bounded_context="accounts",
        target_profile=profile_name,
        systems=[SystemParticipant(name="Ledger", role="upstream")],
        contracts=[ContractMetadata(name="ledger-api", type="rest-json", source="")],
        operations=[operation],
        entities=[entity],
        mappings=mappings,
    )


def _build_single_operation_metadata(operation_name: str) -> MetadataProject:
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        CanonicalOperation,
        ContractMetadata,
        MetadataProject,
        SystemParticipant,
    )

    entity = CanonicalEntity(
        name="PermissionGroup",
        fields=[
            CanonicalField(
                name="groupId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=36,
                source_paths=[f"permissions-api.{operation_name}.response.groupId"],
            ),
            CanonicalField(
                name="name",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=64,
                source_paths=[f"permissions-api.{operation_name}.request.name"],
            ),
        ],
    )
    operation = CanonicalOperation(
        name=operation_name,
        interface_name="permissions-api",
        request_entity="PermissionGroup",
        response_entity="PermissionGroup",
    )
    mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="permissions-api",
            operation_name=operation_name,
            source_path=f"permissions-api.{operation_name}.request.name",
            target_path="PermissionGroup.name",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="permissions-api",
            operation_name=operation_name,
            source_path=f"permissions-api.{operation_name}.response.groupId",
            target_path="PermissionGroup.groupId",
        ),
    ]
    profile_name = "springboot-java-identifier-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=False,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )
    return MetadataProject(
        app_name="Permission Groups",
        bounded_context="permissions",
        target_profile=profile_name,
        systems=[SystemParticipant(name="CONFIGCAT", role="upstream")],
        contracts=[ContractMetadata(name="permissions-api", type="rest-json", source="")],
        operations=[operation],
        entities=[entity],
        mappings=mappings,
    )


# ---------------------------------------------------------------------------
# B1 regression tests: string PK columns must not carry contract-driven length
# ---------------------------------------------------------------------------

def test_string_id_field_has_no_length_constraint_in_column_annotation(tmp_path: Path) -> None:
    """B1: @Column on a UUID-generated string PK must not include a length= argument.

    When a string PK field has a contract-driven max_length (e.g. VARCHAR(12) from the
    upstream contract), the emitter previously leaked that length into the @Column
    annotation.  Hibernate would then enforce VARCHAR(12) on the column, which is too
    narrow for a 36-char UUID value, causing a runtime failure.
    """
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        CanonicalOperation,
        ContractMetadata,
        MetadataProject,
        SystemParticipant,
    )

    entity = CanonicalEntity(
        name="Widget",
        fields=[
            CanonicalField(
                name="widgetId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=12,  # contract-driven length that must NOT appear in @Column
                source_paths=["widget-api.createWidget.request.widgetId"],
            ),
            CanonicalField(
                name="widgetName",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=50,
                source_paths=["widget-api.createWidget.request.widgetName"],
            ),
        ],
    )
    op = CanonicalOperation(name="createWidget", interface_name="widget-api", request_entity="Widget", response_entity="Widget")
    mappings = [
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="widget-api", operation_name="createWidget", source_path="widget-api.createWidget.request.widgetName", target_path="Widget.widgetName"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="widget-api", operation_name="createWidget", source_path="widget-api.createWidget.response.widgetId", target_path="Widget.widgetId"),
    ]
    profile_name = "springboot-b1-java-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name, language="java", framework="spring-boot",
        java_baseline="17", spring_boot_baseline="3.3.5",
        emit_flyway=False, emit_spring_batch=False, emit_security=False, emit_audit=False, supports_xml=False,
    )
    metadata = MetadataProject(
        app_name="Widget App",
        bounded_context="widgets",
        target_profile=profile_name,
        systems=[SystemParticipant(name="WIDGET", role="upstream")],
        contracts=[ContractMetadata(name="widget-api", type="rest-json", source="")],
        operations=[op],
        entities=[entity],
        mappings=mappings,
    )

    try:
        output_dir = tmp_path / "WidgetAppB1Java"
        generate_application(metadata, output_dir, generation_run_id="b1-java-test")
        entity_source = (
            output_dir / "src/main/java/com/appbuilder/widgets/domain/Widget.java"
        ).read_text(encoding="utf-8")

        # The PK field must use @GeneratedValue(strategy = GenerationType.UUID)
        assert "@GeneratedValue(strategy = GenerationType.UUID)" in entity_source
        # The @Column for the PK must use UUID width, not the contract-driven length.
        # (check specifically on the line that contains the @Id/@Column block for widgetId)
        assert "length = 12" not in entity_source
        assert 'length = 36' in entity_source.split("widgetName")[0]
        # Non-PK string fields with max_length SHOULD still carry length=
        assert "length = 50" in entity_source
    finally:
        TARGET_PROFILES.pop(profile_name, None)


def test_string_id_field_has_uuid_length_in_flyway_migration(tmp_path: Path) -> None:
    """Flyway DDL for a UUID-generated string PK must use UUID width, not VARCHAR(N).

    When the contract specifies e.g. VARCHAR(12), the sql_emitter must ignore that
    constraint and emit VARCHAR(36) so the column matches generated UUID semantics.
    """
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        CanonicalOperation,
        ContractMetadata,
        MetadataProject,
        SystemParticipant,
    )

    entity = CanonicalEntity(
        name="Widget",
        fields=[
            CanonicalField(
                name="widgetId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=12,  # contract-driven length that must NOT appear in DDL
                source_paths=["widget-api.createWidget.request.widgetId"],
            ),
            CanonicalField(
                name="widgetName",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=50,
                source_paths=["widget-api.createWidget.request.widgetName"],
            ),
        ],
    )
    op = CanonicalOperation(name="createWidget", interface_name="widget-api", request_entity="Widget", response_entity="Widget")
    mappings = [
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="widget-api", operation_name="createWidget", source_path="widget-api.createWidget.request.widgetName", target_path="Widget.widgetName"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="widget-api", operation_name="createWidget", source_path="widget-api.createWidget.response.widgetId", target_path="Widget.widgetId"),
    ]
    profile_name = "springboot-b1-sql-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name, language="java", framework="spring-boot",
        java_baseline="17", spring_boot_baseline="3.3.5",
        emit_flyway=True, emit_spring_batch=False, emit_security=False, emit_audit=False, supports_xml=False,
    )
    metadata = MetadataProject(
        app_name="Widget App",
        bounded_context="widgets",
        target_profile=profile_name,
        systems=[SystemParticipant(name="WIDGET", role="upstream")],
        contracts=[ContractMetadata(name="widget-api", type="rest-json", source="")],
        operations=[op],
        entities=[entity],
        mappings=mappings,
    )

    try:
        output_dir = tmp_path / "WidgetAppB1Sql"
        generate_application(metadata, output_dir, generation_run_id="b1-sql-test")
        migration = (
            output_dir / "src/main/resources/db/migration/V1__create_widget_table.sql"
        ).read_text(encoding="utf-8")

        # PK column must be VARCHAR(36), not VARCHAR(12)
        assert "widget_id VARCHAR(36)" in migration
        assert "widget_id VARCHAR(255)" not in migration
        assert "widget_id VARCHAR(12)" not in migration
        # Non-PK string columns with max_length should still use the constrained width
        assert "widget_name VARCHAR(50)" in migration
    finally:
        TARGET_PROFILES.pop(profile_name, None)


def test_caller_supplied_string_id_keeps_wide_persistence_column(tmp_path: Path) -> None:
    entity = CanonicalEntity(
        name="ExternalCustomer",
        fields=[
            CanonicalField(
                name="externalCustomerId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=20,
                server_generated_id=False,
                id_generation_strategy=IdGenerationStrategy.CALLER_SUPPLIED,
            ),
            CanonicalField(
                name="customerName",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=80,
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="External Customer App",
        bounded_context="external-customers",
        target_profile="springboot-legacy-compatible",
        entities=[entity],
    )

    output_dir = tmp_path / "ExternalCustomerApp"
    target_profile = TARGET_PROFILES["springboot-legacy-compatible"]
    emit_sql_files(
        metadata=metadata,
        target_profile=target_profile,
        output_dir=output_dir,
        source_manifest="test",
        generation_run_id="caller-supplied-id-test",
    )
    migration = (
        output_dir
        / "src/main/resources/db/migration/V1__create_external_customer_table.sql"
    ).read_text(encoding="utf-8")
    entity_source = _render_entity(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.externalcustomers",
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="caller-supplied-id-test",
    )

    assert "external_customer_id VARCHAR(255) NOT NULL PRIMARY KEY" in migration
    assert "external_customer_id VARCHAR(36)" not in migration
    id_section = entity_source.split("private String externalCustomerId;", 1)[0]
    assert "ID ownership: caller-supplied" in id_section
    assert "length = 36" not in id_section
    assert "@GeneratedValue(strategy = GenerationType.UUID)" not in id_section


def test_known_uuid_reference_field_uses_uuid_width(tmp_path: Path) -> None:
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(
                name="customerId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=True,
            ),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    order = CanonicalEntity(
        name="CustomerOrder",
        fields=[
            CanonicalField(
                name="orderId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=True,
            ),
            CanonicalField(
                name="customerId",
                type=CanonicalFieldType.STRING,
                required=True,
                server_generated_id=False,
            ),
            CanonicalField(name="description", type=CanonicalFieldType.STRING, required=False),
        ],
    )
    metadata = MetadataProject(
        app_name="Customer Orders",
        bounded_context="orders",
        target_profile="springboot-legacy-compatible",
        entities=[customer, order],
        relationships=[
            CanonicalRelationship(
                source_entity="CustomerOrder",
                source_field="customerId",
                target_entity="Customer",
                target_field="customerId",
                relationship_type=RelationshipType.MANY_TO_ONE,
                association_name="customer",
            )
        ],
    )

    output_dir = tmp_path / "CustomerOrders"
    target_profile = TARGET_PROFILES["springboot-legacy-compatible"]
    migrations = emit_sql_files(
        metadata=metadata,
        target_profile=target_profile,
        output_dir=output_dir,
        source_manifest="test",
        generation_run_id="uuid-reference-test",
    )
    order_migration = next(path for path in migrations if path.name.endswith("create_customer_order_table.sql"))
    migration = order_migration.read_text(encoding="utf-8")
    entity_source = _render_entity(
        metadata=metadata,
        entity=order,
        root_package="com.appbuilder.orders",
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="uuid-reference-test",
    )

    assert "order_id VARCHAR(36) NOT NULL PRIMARY KEY" in migration
    assert "customer_id VARCHAR(36) NOT NULL" in migration
    assert "customer_id VARCHAR(255)" not in migration
    customer_id_section = entity_source.split("private String customerId;", 1)[0]
    assert '@Column(name = "customer_id", length = 36, nullable = false)' in customer_id_section


def test_reference_to_non_id_field_does_not_inherit_target_uuid_width(tmp_path: Path) -> None:
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(
                name="customerId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=True,
            ),
            CanonicalField(
                name="customerCode",
                type=CanonicalFieldType.STRING,
                required=True,
                server_generated_id=False,
            ),
        ],
    )
    order = CanonicalEntity(
        name="CustomerOrder",
        fields=[
            CanonicalField(
                name="orderId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=True,
            ),
            CanonicalField(
                name="customerCode",
                type=CanonicalFieldType.STRING,
                required=True,
                server_generated_id=False,
            ),
        ],
    )
    metadata = MetadataProject(
        app_name="Customer Orders",
        bounded_context="orders",
        target_profile="springboot-legacy-compatible",
        entities=[customer, order],
        relationships=[
            CanonicalRelationship(
                source_entity="CustomerOrder",
                source_field="customerCode",
                target_entity="Customer",
                target_field="customerCode",
                relationship_type=RelationshipType.MANY_TO_ONE,
                association_name="customer",
            )
        ],
    )

    output_dir = tmp_path / "CustomerOrdersByCode"
    target_profile = TARGET_PROFILES["springboot-legacy-compatible"]
    migrations = emit_sql_files(
        metadata=metadata,
        target_profile=target_profile,
        output_dir=output_dir,
        source_manifest="test",
        generation_run_id="non-id-reference-test",
    )
    order_migration = next(path for path in migrations if path.name.endswith("create_customer_order_table.sql"))
    migration = order_migration.read_text(encoding="utf-8")
    entity_source = _render_entity(
        metadata=metadata,
        entity=order,
        root_package="com.appbuilder.orders",
        target_profile=target_profile,
        source_manifest="test",
        generation_run_id="non-id-reference-test",
    )

    assert "order_id VARCHAR(36) NOT NULL PRIMARY KEY" in migration
    assert "customer_code VARCHAR(255) NOT NULL" in migration
    assert "customer_code VARCHAR(36)" not in migration
    customer_code_section = entity_source.split("private String customerCode;", 1)[0].rsplit("/**", 1)[-1]
    assert '@Column(name = "customer_code", nullable = false)' in customer_code_section
    assert "length = 36" not in customer_code_section


def test_repayment_schedule_generation_uses_schedule_id_as_primary_key(tmp_path: Path) -> None:
    project_root = _write_repayment_schedule_project(tmp_path)
    manifest_path = project_root / "app-definition.yaml"
    metadata = build_metadata_project(manifest_path)

    output_dir = tmp_path / "LoanLite"
    with pytest.raises(ValueError, match="getRepaymentSchedule.*legacy read inputs"):
        generate_application(metadata, output_dir, generation_run_id="unsupported-legacy-selector")
    assert not output_dir.exists()
    # Keep the primary-key rendering proof with an explicitly declared own-ID
    # read rather than the old unimplemented request-sample lookup.
    operation = next(op for op in metadata.operations if op.name == "getRepaymentSchedule")
    operation.path = "/repayment-schedules/{scheduleId}"
    operation.path_parameters = [PathParameter(name="scheduleId", type="String")]
    operation.response_shape = ResponseShape.SINGLE
    metadata.mappings = [mapping for mapping in metadata.mappings if not (
        mapping.operation_name == operation.name and ".request." in mapping.source_path
    )]
    generate_application(
        metadata,
        output_dir,
        source_manifest=str(manifest_path),
        generation_run_id="repayment-id-test",
    )

    entity_source = (
        output_dir / "src/main/java/com/appbuilder/lending/domain/RepaymentSchedule.java"
    ).read_text(encoding="utf-8")
    service_source = (
        output_dir / "src/main/java/com/appbuilder/lending/service/RepaymentScheduleServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "@Id" in entity_source
    assert "private String scheduleId;" in entity_source
    assert "private String loanId;" in entity_source
    assert "@GeneratedValue(strategy = GenerationType.UUID)" in entity_source.split(
        "private String scheduleId;"
    )[0]
    assert "@GeneratedValue(strategy = GenerationType.UUID)" not in entity_source.split(
        "private String loanId;"
    )[0].split("private String scheduleId;")[-1]
    assert "repaymentSchedule.setScheduleId(id);" in service_source
    assert "repaymentScheduleRepository.findById(id)" in service_source


def test_generation_keeps_nested_upstream_response_fields_in_dto_contracts(tmp_path: Path) -> None:
    project_root = _write_nested_domestic_payment_project(tmp_path)
    manifest_path = project_root / "app-definition.yaml"
    metadata = build_metadata_project(manifest_path)

    output_dir = tmp_path / "Bank"
    report = generate_application(
        metadata,
        output_dir,
        source_manifest=str(manifest_path),
        generation_run_id="domestic-payment-nested-response",
    )

    entity_source = (
        output_dir / "src/main/java/com/appbuilder/bank/domain/DomesticPayment.java"
    ).read_text(encoding="utf-8")
    create_response_source = (
        output_dir
        / "src/main/java/com/appbuilder/bank/adapter/inbound/CreateDomesticPaymentsResponse.java"
    ).read_text(encoding="utf-8")
    get_response_source = (
        output_dir
        / "src/main/java/com/appbuilder/bank/adapter/inbound/GetDomesticPaymentsDomesticPaymentIdResponse.java"
    ).read_text(encoding="utf-8")
    service_source = (
        output_dir / "src/main/java/com/appbuilder/bank/service/DomesticPaymentServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "import java.time.LocalDateTime;" in entity_source
    assert "private LocalDateTime ExpectedExecutionDateTime;" in entity_source
    assert "private LocalDateTime ExpectedSettlementDateTime;" in entity_source
    assert "import java.time.LocalDateTime;" in create_response_source
    assert "private LocalDateTime ExpectedExecutionDateTime;" in create_response_source
    assert "private LocalDateTime ExpectedSettlementDateTime;" in create_response_source
    assert "import java.time.LocalDateTime;" in get_response_source
    assert "private LocalDateTime ExpectedExecutionDateTime;" in get_response_source
    assert "private LocalDateTime ExpectedSettlementDateTime;" in get_response_source
    assert "setExpectedExecutionDateTime(saved.getExpectedExecutionDateTime());" in service_source
    assert "setExpectedSettlementDateTime(saved.getExpectedSettlementDateTime());" in service_source
    assert report.harness_report is not None
    assert report.harness_report.passed, (
        "Harness failed: " + "; ".join(
            f"{check.name}: {check.message}"
            for check in report.harness_report.checks
            if not check.passed
        )
    )


def _write_repayment_schedule_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "repayment-modernization"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "data-handoffs").mkdir(parents=True)
    (project_root / "contracts").mkdir(parents=True)
    (project_root / "contracts" / "repayment-api-spec.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    (project_root / "upstream" / "create-repayment-request.json").write_text(
        json.dumps(
            {
                "loanId": "loan-1",
                "dueDate": "2026-03-30",
                "dueAmount": 5000,
                "paidAmount": 2500,
            }
        ),
        encoding="utf-8",
    )
    (project_root / "upstream" / "create-repayment-response.json").write_text(
        json.dumps(
            {
                "scheduleId": "schedule-1",
                "loanId": "loan-1",
                "dueDate": "2026-03-30",
                "dueAmount": 5000,
                "paidAmount": 2500,
            }
        ),
        encoding="utf-8",
    )
    (project_root / "upstream" / "get-repayment-response.json").write_text(
        json.dumps(
            {
                "scheduleId": "schedule-1",
                "loanId": "loan-1",
                "dueDate": "2026-03-30",
                "dueAmount": 5000,
                "paidAmount": 2500,
            }
        ),
        encoding="utf-8",
    )
    (project_root / "upstream" / "repayment-mapping.yaml").write_text(
        "\n".join(
            [
                "entity: RepaymentSchedule",
                "operations:",
                "  - name: createRepaymentSchedule",
                "    request_mappings:",
                "      - source: loanId",
                "        target: RepaymentSchedule.loanId",
                "      - source: dueDate",
                "        target: RepaymentSchedule.dueDate",
                "      - source: dueAmount",
                "        target: RepaymentSchedule.dueAmount",
                "      - source: paidAmount",
                "        target: RepaymentSchedule.paidAmount",
                "    response_mappings:",
                "      - source: scheduleId",
                "        target: RepaymentSchedule.scheduleId",
                "      - source: loanId",
                "        target: RepaymentSchedule.loanId",
                "      - source: dueDate",
                "        target: RepaymentSchedule.dueDate",
                "      - source: dueAmount",
                "        target: RepaymentSchedule.dueAmount",
                "      - source: paidAmount",
                "        target: RepaymentSchedule.paidAmount",
                "  - name: getRepaymentSchedule",
                "    request_mappings:",
                "      - source: scheduleId",
                "        target: RepaymentSchedule.scheduleId",
                "    response_mappings:",
                "      - source: scheduleId",
                "        target: RepaymentSchedule.scheduleId",
                "      - source: loanId",
                "        target: RepaymentSchedule.loanId",
                "      - source: dueDate",
                "        target: RepaymentSchedule.dueDate",
                "      - source: dueAmount",
                "        target: RepaymentSchedule.dueAmount",
                "      - source: paidAmount",
                "        target: RepaymentSchedule.paidAmount",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "data-handoffs" / "repayment-staging-table.sql").write_text(
        "\n".join(
            [
                "CREATE TABLE repayment_staging_tbl (",
                "    sched_id VARCHAR(36) NOT NULL,",
                "    loan_ref VARCHAR(36) NOT NULL,",
                "    due_amt DECIMAL(19,2)",
                ");",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "data-handoffs" / "repayment-staging-mapping.yaml").write_text(
        "\n".join(
            [
                "table: repayment_staging_tbl",
                "entity: RepaymentSchedule",
                "field_mappings:",
                "  - source: RepaymentSchedule.scheduleId",
                "    target: sched_id",
                "  - source: RepaymentSchedule.loanId",
                "    target: loan_ref",
                "  - source: RepaymentSchedule.dueAmount",
                "    target: due_amt",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Repayment Modernization",
                "bounded_context: lending",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: repayment-api",
                "    system: LOANS",
                "    type: rest-json",
                "    spec: contracts/repayment-api-spec.json",
                "    mapping: upstream/repayment-mapping.yaml",
                "    operations:",
                "      - name: createRepaymentSchedule",
                "        request_sample: upstream/create-repayment-request.json",
                "        response_sample: upstream/create-repayment-response.json",
                "      - name: getRepaymentSchedule",
                "        response_sample: upstream/get-repayment-response.json",
                "data_handoffs:",
                "  - name: repayment-staging-table",
                "    system: ETL",
                "    type: staging-table",
                "    spec: data-handoffs/repayment-staging-table.sql",
                "    mapping: data-handoffs/repayment-staging-mapping.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )
    return project_root


def _c9_metadata(
    *,
    strategy: IdGenerationStrategy | None,
    field_type: CanonicalFieldType = CanonicalFieldType.INTEGER,
    sequence_name: str | None = None,
    target_profile: str = "springboot-legacy-compatible",
    server_generated_id: bool = True,
) -> MetadataProject:
    return MetadataProject(
        app_name="Loan App",
        bounded_context="loans",
        target_profile=target_profile,
        systems=[SystemParticipant(name="LOANS", role="upstream")],
        contracts=[ContractMetadata(name="loan-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="createLoan",
                interface_name="loan-api",
                request_entity="Loan",
                response_entity="Loan",
            )
        ],
        entities=[
            CanonicalEntity(
                name="Loan",
                fields=[
                    CanonicalField(
                        name="loanId",
                        type=field_type,
                        is_id=True,
                        server_generated_id=server_generated_id,
                        id_generation_strategy=strategy,
                        id_sequence_name=sequence_name,
                    ),
                    CanonicalField(
                        name="loanName",
                        type=CanonicalFieldType.STRING,
                    ),
                ],
            )
        ],
    )


def _render_c9_entity_source(
    *,
    strategy: IdGenerationStrategy | None,
    field_type: CanonicalFieldType = CanonicalFieldType.INTEGER,
    sequence_name: str | None = None,
    server_generated_id: bool = True,
) -> str:
    metadata = _c9_metadata(
        strategy=strategy,
        field_type=field_type,
        sequence_name=sequence_name,
        server_generated_id=server_generated_id,
    )
    return _render_entity(
        metadata=metadata,
        entity=metadata.entities[0],
        root_package="com.appbuilder.loans",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test-manifest.yaml",
        generation_run_id="c9-java-test",
    )


def _render_c9_migration(
    tmp_path: Path,
    *,
    strategy: IdGenerationStrategy | None,
    target_profile: str,
    sequence_name: str | None = None,
) -> str:
    metadata = _c9_metadata(
        strategy=strategy,
        target_profile=target_profile,
        sequence_name=sequence_name,
    )
    output_dir = tmp_path / f"C9Sql{target_profile}"
    emit_sql_files(
        metadata=metadata,
        target_profile=TARGET_PROFILES[target_profile],
        output_dir=output_dir,
        source_manifest="test-manifest.yaml",
        generation_run_id="c9-sql-test",
    )
    migration_path = (
        output_dir
        / "src"
        / "main"
        / "resources"
        / "db"
        / "migration"
        / "V1__create_loan_table.sql"
    )
    return migration_path.read_text(encoding="utf-8")


def test_java_entity_db_identity_emits_generated_value_identity() -> None:
    entity_source = _render_c9_entity_source(strategy=IdGenerationStrategy.DB_IDENTITY)

    assert "@GeneratedValue(strategy = GenerationType.IDENTITY)" in entity_source
    assert "// ID ownership: database identity (C9 explicit)." in entity_source


def test_java_entity_db_sequence_emits_sequence_generator() -> None:
    entity_source = _render_c9_entity_source(
        strategy=IdGenerationStrategy.DB_SEQUENCE,
        sequence_name="loan_id_seq",
    )

    assert "@SequenceGenerator" in entity_source
    assert 'sequenceName = "loan_id_seq"' in entity_source
    assert "GenerationType.SEQUENCE" in entity_source


def test_java_entity_caller_supplied_no_generated_value() -> None:
    entity_source = _render_c9_entity_source(
        strategy=IdGenerationStrategy.CALLER_SUPPLIED,
        field_type=CanonicalFieldType.STRING,
        server_generated_id=False,
    )

    id_block = entity_source.split("private String loanId;")[0]
    assert "// ID ownership: caller-supplied (C9 explicit)." in id_block
    assert "@GeneratedValue" not in id_block


def test_java_entity_uuid_strategy_explicit_emits_uuid() -> None:
    entity_source = _render_c9_entity_source(
        strategy=IdGenerationStrategy.UUID,
        field_type=CanonicalFieldType.STRING,
    )

    assert "@GeneratedValue(strategy = GenerationType.UUID)" in entity_source
    assert "// ID ownership: server-generated UUID (C9 explicit)." in entity_source


def test_java_entity_no_strategy_falls_back_to_legacy_uuid() -> None:
    entity_source = _render_c9_entity_source(
        strategy=None,
        field_type=CanonicalFieldType.STRING,
        server_generated_id=True,
    )

    assert "@GeneratedValue(strategy = GenerationType.UUID)" in entity_source
    assert "id absent from POST body schema" in entity_source


def test_sql_db_identity_postgresql_emits_generated_always(tmp_path: Path) -> None:
    migration_sql = _render_c9_migration(
        tmp_path,
        strategy=IdGenerationStrategy.DB_IDENTITY,
        target_profile="springboot-enterprise-postgres-java17",
    )

    assert "loan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY" in migration_sql


def test_sql_db_identity_h2_emits_auto_increment(tmp_path: Path) -> None:
    migration_sql = _render_c9_migration(
        tmp_path,
        strategy=IdGenerationStrategy.DB_IDENTITY,
        target_profile="springboot-legacy-compatible",
    )

    assert "loan_id BIGINT AUTO_INCREMENT PRIMARY KEY" in migration_sql


def test_sql_db_sequence_prepends_create_sequence(tmp_path: Path) -> None:
    migration_sql = _render_c9_migration(
        tmp_path,
        strategy=IdGenerationStrategy.DB_SEQUENCE,
        target_profile="springboot-enterprise-postgres-java17",
        sequence_name="loan_id_seq",
    )

    assert "CREATE SEQUENCE loan_id_seq;" in migration_sql
    assert migration_sql.index("CREATE SEQUENCE loan_id_seq;") < migration_sql.index(
        "CREATE TABLE loan ("
    )


def test_sql_no_override_preserves_existing_pk_behavior(tmp_path: Path) -> None:
    migration_sql = _render_c9_migration(
        tmp_path,
        strategy=None,
        target_profile="springboot-legacy-compatible",
    )

    assert "GENERATED ALWAYS AS IDENTITY" not in migration_sql
    assert "AUTO_INCREMENT" not in migration_sql
    assert "PRIMARY KEY" in migration_sql


def _write_nested_domestic_payment_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "bank-modernization"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "rules").mkdir(parents=True)

    (project_root / "upstream" / "sample-createdomesticpayments-request.json").write_text(
        json.dumps(
            {
                "Data": {
                    "ConsentId": "CONSENT-123",
                }
            }
        ),
        encoding="utf-8",
    )
    response_payload = {
        "Data": {
            "DomesticPaymentId": "PAYMENT-12345",
            "ConsentId": "CONSENT-123",
            "CreationDateTime": "2026-04-05T10:00:00+00:00",
            "Status": "ACSP",
            "StatusUpdateDateTime": "2026-04-05T10:05:00+00:00",
            "ExpectedExecutionDateTime": "2026-04-05T10:15:30+00:00",
            "ExpectedSettlementDateTime": "2026-04-05T10:16:00+00:00",
        },
        "Links": {"self": "https://example.com/domestic-payments/PAYMENT-12345"},
        "Meta": {"totalPages": 1},
    }
    (project_root / "upstream" / "sample-createdomesticpayments-response.json").write_text(
        json.dumps(response_payload),
        encoding="utf-8",
    )
    (project_root / "upstream" / "sample-getdomesticpaymentsdomesticpaymentid-response.json").write_text(
        json.dumps(response_payload),
        encoding="utf-8",
    )
    (project_root / "upstream" / "bank-domesticpayment-api-mapping.yaml").write_text(
        "\n".join(
            [
                "interface: bank-domesticpayment-api",
                "entity: DomesticPayment",
                "operations:",
                "- name: CreateDomesticPayments",
                "  request_mappings:",
                "  - source: Data.ConsentId",
                "    target: DomesticPayment.ConsentId",
                "  response_mappings:",
                "  - source: Data.DomesticPaymentId",
                "    target: DomesticPayment.DomesticPaymentId",
                "  - source: Data.ConsentId",
                "    target: DomesticPayment.ConsentId",
                "  - source: Data.CreationDateTime",
                "    target: DomesticPayment.CreationDateTime",
                "  - source: Data.Status",
                "    target: DomesticPayment.Status",
                "  - source: Data.StatusUpdateDateTime",
                "    target: DomesticPayment.StatusUpdateDateTime",
                "  - source: Data.ExpectedExecutionDateTime",
                "    target: DomesticPayment.ExpectedExecutionDateTime",
                "  - source: Data.ExpectedSettlementDateTime",
                "    target: DomesticPayment.ExpectedSettlementDateTime",
                "- name: GetDomesticPaymentsDomesticPaymentId",
                "  response_mappings:",
                "  - source: Data.DomesticPaymentId",
                "    target: DomesticPayment.DomesticPaymentId",
                "  - source: Data.ConsentId",
                "    target: DomesticPayment.ConsentId",
                "  - source: Data.CreationDateTime",
                "    target: DomesticPayment.CreationDateTime",
                "  - source: Data.Status",
                "    target: DomesticPayment.Status",
                "  - source: Data.StatusUpdateDateTime",
                "    target: DomesticPayment.StatusUpdateDateTime",
                "  - source: Data.ExpectedExecutionDateTime",
                "    target: DomesticPayment.ExpectedExecutionDateTime",
                "  - source: Data.ExpectedSettlementDateTime",
                "    target: DomesticPayment.ExpectedSettlementDateTime",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "rules" / "domesticpayment-business-rules.yaml").write_text(
        "\n".join(
            [
                "entity: DomesticPayment",
                "rules:",
                "- field: DomesticPaymentId",
                "  type: max-length",
                "  value: '40'",
                "- field: ConsentId",
                "  type: max-length",
                "  value: '128'",
                "- field: CreationDateTime",
                "  type: not-null",
                "- field: Status",
                "  type: allowed-values",
                "  values:",
                "  - ACSP",
                "- field: StatusUpdateDateTime",
                "  type: not-null",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Bank app",
                "bounded_context: bank",
                "schema_version: '2.0'",
                "app_archetype: crud",
                "target_profile: springboot-legacy-compatible",
                "upstream_interfaces:",
                "- name: bank-domesticpayment-api",
                "  type: rest-json",
                "  spec_url: https://example.com/bank-api.json",
                "  mapping: upstream/bank-domesticpayment-api-mapping.yaml",
                "  operations:",
                "  - name: CreateDomesticPayments",
                "    request_sample: upstream/sample-createdomesticpayments-request.json",
                "    response_sample: upstream/sample-createdomesticpayments-response.json",
                "  - name: GetDomesticPaymentsDomesticPaymentId",
                "    response_sample: upstream/sample-getdomesticpaymentsdomesticpaymentid-response.json",
                "rules:",
                "- rules/domesticpayment-business-rules.yaml",
            ]
        ),
        encoding="utf-8",
    )
    return project_root
