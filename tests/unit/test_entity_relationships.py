"""Tests for Phase 1b entity relationships v1."""

from __future__ import annotations

from pathlib import Path

from appbuilder.generation import generate_application
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    CanonicalRelationship,
    HttpMethod,
    MetadataProject,
    RelationshipType,
    ResponseShape,
    build_metadata_project,
)
from appbuilder.metadata.translation import _infer_relationships
from appbuilder.rules import CanonicalRule, RuleType
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

_REL_PROFILE_NAME = "springboot-relationships-test"
if _REL_PROFILE_NAME not in TARGET_PROFILES:
    TARGET_PROFILES[_REL_PROFILE_NAME] = TargetProfile(
        name=_REL_PROFILE_NAME,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=True,
        emit_spring_batch=False,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )

_FIXTURE_PROFILE_NAME = "springboot-cross-entity-test"
if _FIXTURE_PROFILE_NAME not in TARGET_PROFILES:
    TARGET_PROFILES[_FIXTURE_PROFILE_NAME] = TargetProfile(
        name=_FIXTURE_PROFILE_NAME,
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


def _base_metadata(*, with_relationship: bool = True) -> MetadataProject:
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
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=10,
            ),
        ],
    )
    operations = [
        CanonicalOperation(
            name="createCustomer",
            interface_name="test-api",
            request_entity="Customer",
            response_entity="Customer",
            http_method=HttpMethod.POST,
            path="/customers",
            has_request_body=True,
            response_shape=ResponseShape.CREATED,
        ),
        CanonicalOperation(
            name="createAccount",
            interface_name="test-api",
            request_entity="Account",
            response_entity="Account",
            http_method=HttpMethod.POST,
            path="/accounts",
            has_request_body=True,
            response_shape=ResponseShape.CREATED,
        ),
    ]

    rules = [
        CanonicalRule(
            entity_name="Account",
            field_name="customerId",
            type=RuleType.CROSS_ENTITY_EXISTS,
            source_path="rules.Account.customerId.cross-entity-exists",
            target_entity="Customer",
        ),
    ]
    mappings = [
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createCustomer",
            source_path="test-api.createCustomer.response.customerId",
            target_path="Customer.customerId",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createCustomer",
            source_path="test-api.createCustomer.request.customerName",
            target_path="Customer.customerName",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createAccount",
            source_path="test-api.createAccount.response.accountId",
            target_path="Account.accountId",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createAccount",
            source_path="test-api.createAccount.request.customerId",
            target_path="Account.customerId",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createAccount",
            source_path="test-api.createAccount.request.status",
            target_path="Account.status",
        ),
    ]
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
        app_name="Relationship Test App",
        bounded_context="relationships",
        target_profile=_REL_PROFILE_NAME,
        operations=operations,
        entities=[customer, account],
        mappings=mappings,
        rules=rules,
        relationships=relationships,
    )


def test_cross_entity_rule_infers_many_to_one_relationship() -> None:
    fixture_root = Path(__file__).parent.parent / "fixtures" / "workspace-cross-entity"
    metadata = build_metadata_project(fixture_root / "app-definition.yaml")

    assert metadata.relationships
    relationship = metadata.relationships[0]
    assert relationship.source_entity == "Item"
    assert relationship.source_field == "workspaceId"
    assert relationship.target_entity == "Workspace"
    assert relationship.target_field == "workspaceId"
    assert relationship.relationship_type == RelationshipType.MANY_TO_ONE
    assert relationship.association_name == "workspace"


def test_child_entity_emits_read_only_many_to_one_association(tmp_path: Path) -> None:
    metadata = _base_metadata()
    generate_application(metadata, tmp_path, source_manifest="test.yaml", generation_run_id="rel-test")

    source = (
        tmp_path / "src/main/java/com/appbuilder/relationships/domain/Account.java"
    ).read_text(encoding="utf-8")

    assert "@JsonIgnore" in source
    assert "@ManyToOne(fetch = FetchType.LAZY)" in source
    assert (
        '@JoinColumn(name = "customer_id", referencedColumnName = "customer_id", '
        "insertable = false, updatable = false)"
    ) in source
    assert "private Customer customer;" in source
    assert "@OneToMany" not in source


def test_relationship_preserves_scalar_fk_field(tmp_path: Path) -> None:
    metadata = _base_metadata()
    generate_application(metadata, tmp_path, source_manifest="test.yaml", generation_run_id="rel-test")

    entity_source = (
        tmp_path / "src/main/java/com/appbuilder/relationships/domain/Account.java"
    ).read_text(encoding="utf-8")
    service_source = (
        tmp_path / "src/main/java/com/appbuilder/relationships/service/AccountServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "private String customerId;" in entity_source
    assert "setCustomerId(request.getCustomerId())" in service_source
    assert "setCustomer(" not in service_source


def test_sql_emits_foreign_key_constraint(tmp_path: Path) -> None:
    metadata = _base_metadata()
    generate_application(metadata, tmp_path, source_manifest="test.yaml", generation_run_id="rel-test")

    migration = (
        tmp_path / "src/main/resources/db/migration/V2__create_account_table.sql"
    ).read_text(encoding="utf-8")

    assert (
        "ALTER TABLE account ADD CONSTRAINT fk_account_customer_id "
        "FOREIGN KEY (customer_id) REFERENCES customer(customer_id);"
    ) in migration


def test_parent_table_emitted_before_child_table(tmp_path: Path) -> None:
    metadata = _base_metadata()
    generate_application(metadata, tmp_path, source_manifest="test.yaml", generation_run_id="rel-test")

    migration_dir = tmp_path / "src/main/resources/db/migration"
    migration_files = sorted(path.name for path in migration_dir.glob("V*__create_*_table.sql"))

    assert migration_files[0] == "V1__create_customer_table.sql"
    assert migration_files[1] == "V2__create_account_table.sql"


def test_multiple_fk_fields_to_same_target_get_distinct_association_names(tmp_path: Path) -> None:
    metadata = _base_metadata(with_relationship=False)
    account = next(entity for entity in metadata.entities if entity.name == "Account")
    account.fields.append(
        CanonicalField(
            name="primaryCustomerId",
            type=CanonicalFieldType.STRING,
            required=False,
            max_length=36,
        )
    )
    account.fields.append(
        CanonicalField(
            name="secondaryCustomerId",
            type=CanonicalFieldType.STRING,
            required=False,
            max_length=36,
        )
    )
    metadata.relationships = [
        CanonicalRelationship(
            source_entity="Account",
            source_field="primaryCustomerId",
            target_entity="Customer",
            target_field="customerId",
            association_name="primaryCustomer",
        ),
        CanonicalRelationship(
            source_entity="Account",
            source_field="secondaryCustomerId",
            target_entity="Customer",
            target_field="customerId",
            association_name="secondaryCustomer",
        ),
    ]

    generate_application(metadata, tmp_path, source_manifest="test.yaml", generation_run_id="rel-test")
    source = (
        tmp_path / "src/main/java/com/appbuilder/relationships/domain/Account.java"
    ).read_text(encoding="utf-8")

    assert "private Customer primaryCustomer;" in source
    assert "private Customer secondaryCustomer;" in source


def test_no_relationship_emitted_without_cross_entity_rule() -> None:
    entities = [
        CanonicalEntity(
            name="Customer",
            fields=[CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True)],
        ),
        CanonicalEntity(
            name="Account",
            fields=[CanonicalField(name="customerId", type=CanonicalFieldType.STRING)],
        ),
    ]

    relationships = _infer_relationships(entities, [])
    assert relationships == []


def test_invalid_relationship_type_mismatch_skips_with_warning() -> None:
    customer = CanonicalEntity(
        name="Customer",
        fields=[CanonicalField(name="customerId", type=CanonicalFieldType.INTEGER, is_id=True)],
    )
    account = CanonicalEntity(
        name="Account",
        fields=[CanonicalField(name="customerId", type=CanonicalFieldType.STRING)],
    )
    rules = [
        CanonicalRule(
            entity_name="Account",
            field_name="customerId",
            type=RuleType.CROSS_ENTITY_EXISTS,
            source_path="rules.Account.customerId.cross-entity-exists",
            target_entity="Customer",
        )
    ]

    relationships = _infer_relationships([customer, account], rules)

    assert relationships == []
    assert account.warnings
    assert "does not match" in account.warnings[0]


def test_multi_entity_fixture_generates_relationships(tmp_path: Path) -> None:
    fixture_root = Path(__file__).parent.parent / "fixtures" / "workspace-cross-entity"
    metadata = build_metadata_project(fixture_root / "app-definition.yaml")
    metadata.target_profile = _REL_PROFILE_NAME

    generate_application(
        metadata,
        tmp_path,
        source_manifest=str(fixture_root / "app-definition.yaml"),
        generation_run_id="fixture-relationship",
    )
    source = (
        tmp_path / "src/main/java/com/appbuilder/workspace/domain/Item.java"
    ).read_text(encoding="utf-8")

    assert "private Workspace workspace;" in source
    assert "@JsonIgnore" in source


def test_generated_app_compile_smoke_for_multi_entity_case(tmp_path: Path) -> None:
    metadata = _base_metadata()
    generate_application(metadata, tmp_path, source_manifest="test.yaml", generation_run_id="rel-test")

    assert (
        tmp_path / "src/main/java/com/appbuilder/relationships/domain/Customer.java"
    ).exists()
    assert (
        tmp_path / "src/main/java/com/appbuilder/relationships/domain/Account.java"
    ).exists()
    assert (
        tmp_path / "src/main/resources/db/migration/V1__create_customer_table.sql"
    ).exists()
    assert (
        tmp_path / "src/main/resources/db/migration/V2__create_account_table.sql"
    ).exists()
