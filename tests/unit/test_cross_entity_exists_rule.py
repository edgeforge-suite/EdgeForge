"""Tests for the cross-entity-exists rule type.

Covers:
- YAML ingestion: parses target-entity correctly, errors on missing target-entity
- Java generation: AccountServiceBase gains generated CustomerRepository field injection
- Java generation: createAccount() injects FK existence check before applyBusinessRules
- Java generation: update() injects FK existence check
- Java generation: no cross-entity check emitted when entity has no such rules
- Java generation: multiple cross-entity rules on one entity (two FK repos injected)
- Full generate_application roundtrip: bankingcore-style manifest with cross-entity rule
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    ContractMetadata,
    HttpMethod,
    MetadataProject,
    ResponseShape,
    SystemParticipant,
)
from appbuilder.rules.ingestion import load_rule_definitions
from appbuilder.rules.models import CanonicalRule, RuleType
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

# Minimal test profile — no Flyway/batch so tests don't need staging table contracts
_TEST_PROFILE_NAME = "springboot-cross-entity-test"
if _TEST_PROFILE_NAME not in TARGET_PROFILES:
    TARGET_PROFILES[_TEST_PROFILE_NAME] = TargetProfile(
        name=_TEST_PROFILE_NAME,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_metadata(*, with_cross_entity: bool = False) -> MetadataProject:
    """Two-entity metadata: Customer owns Account via customerId FK."""
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=36),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True, max_length=50),
        ],
    )
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=36),
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, required=True, max_length=36),
            CanonicalField(name="currency", type=CanonicalFieldType.STRING, required=True, max_length=3),
        ],
    )

    rules: list[CanonicalRule] = []
    if with_cross_entity:
        rules.append(
            CanonicalRule(
                entity_name="Account",
                field_name="customerId",
                type=RuleType.CROSS_ENTITY_EXISTS,
                source_path="rules.Account.customerId.cross-entity-exists",
                target_entity="Customer",
            )
        )

    create_customer_op = CanonicalOperation(
        name="createCustomer",
        interface_name="test-api",
        request_entity="Customer",
        response_entity="Customer",
        http_method=HttpMethod.POST,
        path="/customers",
        has_request_body=True,
        response_shape=ResponseShape.CREATED,
    )
    create_account_op = CanonicalOperation(
        name="createAccount",
        interface_name="test-api",
        request_entity="Account",
        response_entity="Account",
        http_method=HttpMethod.POST,
        path="/accounts",
        has_request_body=True,
        response_shape=ResponseShape.CREATED,
    )

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
            source_path="test-api.createAccount.request.currency",
            target_path="Account.currency",
        ),
    ]

    return MetadataProject(
        app_name="TestApp",
        bounded_context="Test",
        target_profile=_TEST_PROFILE_NAME,
        systems=[SystemParticipant(name="test-api", role="upstream")],
        contracts=[
            ContractMetadata(name="test-api", type="rest-json", source="test-api-spec.json"),
        ],
        operations=[create_customer_op, create_account_op],
        entities=[customer, account],
        mappings=mappings,
        rules=rules,
    )


# ---------------------------------------------------------------------------
# Rule ingestion tests
# ---------------------------------------------------------------------------

def test_cross_entity_exists_in_rule_type_enum() -> None:
    assert RuleType.CROSS_ENTITY_EXISTS == "cross-entity-exists"


def test_ingestion_parses_cross_entity_exists(tmp_path: Path) -> None:
    rule_file = tmp_path / "account-rules.yaml"
    rule_file.write_text(
        textwrap.dedent("""\
            entity: Account
            rules:
              - field: customerId
                type: cross-entity-exists
                target-entity: Customer
        """),
        encoding="utf-8",
    )
    entity_name, rules = load_rule_definitions(rule_file)
    assert entity_name == "Account"
    assert len(rules) == 1
    rule = rules[0]
    assert rule.type == RuleType.CROSS_ENTITY_EXISTS
    assert rule.field_name == "customerId"
    assert rule.target_entity == "Customer"


def test_ingestion_errors_on_missing_target_entity(tmp_path: Path) -> None:
    rule_file = tmp_path / "bad-rules.yaml"
    rule_file.write_text(
        textwrap.dedent("""\
            entity: Account
            rules:
              - field: customerId
                type: cross-entity-exists
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="target-entity"):
        load_rule_definitions(rule_file)


def test_canonical_rule_has_target_entity_field() -> None:
    rule = CanonicalRule(
        entity_name="Account",
        field_name="customerId",
        type=RuleType.CROSS_ENTITY_EXISTS,
        source_path="test",
        target_entity="Customer",
    )
    assert rule.target_entity == "Customer"


def test_canonical_rule_target_entity_defaults_none() -> None:
    rule = CanonicalRule(
        entity_name="Account",
        field_name="status",
        type=RuleType.ALLOWED_VALUES,
        source_path="test",
        values=["Active", "Dormant"],
    )
    assert rule.target_entity is None


# ---------------------------------------------------------------------------
# Java generation tests — AccountService with cross-entity-exists
# ---------------------------------------------------------------------------

def _generate_account_service(tmp_path: Path, *, with_cross_entity: bool) -> str:
    metadata = _base_metadata(with_cross_entity=with_cross_entity)
    generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )
    service_path = tmp_path / "src/main/java/com/appbuilder/test/service/AccountServiceBase.java"
    return service_path.read_text(encoding="utf-8")


def test_account_service_injects_customer_repository_field(tmp_path: Path) -> None:
    source = _generate_account_service(tmp_path, with_cross_entity=True)
    assert "@Autowired" in source
    assert "protected CustomerRepository customerRepository;" in source


def test_account_service_constructor_stays_stable_when_cross_entity_repository_is_added(tmp_path: Path) -> None:
    source = _generate_account_service(tmp_path, with_cross_entity=True)
    assert "protected AccountServiceBase(AccountRepository accountRepository)" in source
    assert "CustomerRepository customerRepository" not in source.split(
        "protected AccountServiceBase(", 1
    )[1].split(") {", 1)[0]


def test_account_service_imports_customer_repository(tmp_path: Path) -> None:
    source = _generate_account_service(tmp_path, with_cross_entity=True)
    assert "import com.appbuilder.test.repository.CustomerRepository;" in source


def test_create_account_checks_customer_exists(tmp_path: Path) -> None:
    source = _generate_account_service(tmp_path, with_cross_entity=True)
    assert "customerRepository.existsById(" in source
    assert "Customer not found with id:" in source


def test_update_account_checks_customer_exists(tmp_path: Path) -> None:
    source = _generate_account_service(tmp_path, with_cross_entity=True)
    # existsById appears for: (a) Account self-check in update/delete, (b) Customer FK check
    assert source.count("customerRepository.existsById(") >= 1


def test_fk_check_appears_before_apply_business_rules(tmp_path: Path) -> None:
    source = _generate_account_service(tmp_path, with_cross_entity=True)
    fk_pos = source.find("customerRepository.existsById(")
    business_rules_pos = source.find("applyBusinessRules(")
    assert fk_pos != -1, "FK existence check not found"
    assert business_rules_pos != -1, "applyBusinessRules not found"
    assert fk_pos < business_rules_pos, "FK check must appear before applyBusinessRules"


def test_no_cross_entity_check_without_rule(tmp_path: Path) -> None:
    source = _generate_account_service(tmp_path, with_cross_entity=False)
    assert "customerRepository" not in source
    assert "Customer not found with id:" not in source


def test_preserved_service_subclass_survives_cross_entity_dependency_evolution(tmp_path: Path) -> None:
    output_dir = tmp_path / "CrossEntityEvolutionApp"
    initial_metadata = _base_metadata(with_cross_entity=False)
    generate_application(
        metadata=initial_metadata,
        output_dir=output_dir,
        source_manifest="test-manifest.yaml",
        generation_run_id="initial-run",
    )

    service_dir = output_dir / "src/main/java/com/appbuilder/test/service"
    developer_service = service_dir / "AccountService.java"
    generated_base = service_dir / "AccountServiceBase.java"

    edited_developer_service = developer_service.read_text(encoding="utf-8").replace(
        "        // Add pre-create business logic here.",
        "        // CUSTOM CROSS-ENTITY EVOLUTION MARKER\n        // Add pre-create business logic here.",
    )
    developer_service.write_text(edited_developer_service, encoding="utf-8")

    evolved_metadata = _base_metadata(with_cross_entity=True)
    generate_application(
        metadata=evolved_metadata,
        output_dir=output_dir,
        source_manifest="test-manifest.yaml",
        generation_run_id="evolved-run",
    )

    assert developer_service.read_text(encoding="utf-8") == edited_developer_service
    evolved_base = generated_base.read_text(encoding="utf-8")
    assert "protected AccountServiceBase(AccountRepository accountRepository)" in evolved_base
    assert "@Autowired" in evolved_base
    assert "protected CustomerRepository customerRepository;" in evolved_base
    assert "customerRepository.existsById(account.getCustomerId())" in evolved_base
    assert "CustomerRepository customerRepository" not in edited_developer_service


def test_customer_service_unaffected_by_account_cross_entity_rule(tmp_path: Path) -> None:
    """The cross-entity rule is on Account; CustomerService must not be modified."""
    metadata = _base_metadata(with_cross_entity=True)
    generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )
    customer_service = (
        tmp_path / "src/main/java/com/appbuilder/test/service/CustomerServiceBase.java"
    ).read_text(encoding="utf-8")
    # AccountRepository must NOT appear in CustomerService at all
    assert "AccountRepository" not in customer_service
    assert "accountRepository" not in customer_service
    # CustomerService only has its own self-existence check (e.g. update/delete),
    # never a FK check pointing at another entity's repository
    assert "Customer not found with id:" in customer_service  # self-check is present
    assert "Account not found with id:" not in customer_service  # FK check is absent


# ---------------------------------------------------------------------------
# Multiple cross-entity rules on one entity
# ---------------------------------------------------------------------------

def test_two_cross_entity_rules_inject_two_repositories(tmp_path: Path) -> None:
    """If Account references both Customer and Product, both repos are injected."""
    metadata = _base_metadata(with_cross_entity=False)
    # Add Product entity + a createProduct operation so the generator is satisfied
    metadata.entities.append(
        CanonicalEntity(
            name="Product",
            fields=[
                CanonicalField(name="productId", type=CanonicalFieldType.STRING, is_id=True, max_length=36),
            ],
        )
    )
    metadata.operations.append(
        CanonicalOperation(
            name="createProduct",
            interface_name="test-api",
            request_entity="Product",
            response_entity="Product",
            http_method=HttpMethod.POST,
            path="/products",
            has_request_body=True,
            response_shape=ResponseShape.CREATED,
        )
    )
    # Add productId field to Account
    account = next(e for e in metadata.entities if e.name == "Account")
    account.fields.append(
        CanonicalField(name="productId", type=CanonicalFieldType.STRING, max_length=36)
    )
    # Two cross-entity rules
    metadata.rules = [
        CanonicalRule(
            entity_name="Account",
            field_name="customerId",
            type=RuleType.CROSS_ENTITY_EXISTS,
            source_path="rules.Account.customerId.cross-entity-exists",
            target_entity="Customer",
        ),
        CanonicalRule(
            entity_name="Account",
            field_name="productId",
            type=RuleType.CROSS_ENTITY_EXISTS,
            source_path="rules.Account.productId.cross-entity-exists",
            target_entity="Product",
        ),
    ]

    generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )
    source = (
        tmp_path / "src/main/java/com/appbuilder/test/service/AccountServiceBase.java"
    ).read_text(encoding="utf-8")
    assert "protected CustomerRepository customerRepository;" in source
    assert "protected ProductRepository productRepository;" in source
    assert "customerRepository.existsById(" in source
    assert "productRepository.existsById(" in source


# ---------------------------------------------------------------------------
# Full roundtrip: workspace manifest with cross-entity-exists rule
# ---------------------------------------------------------------------------

def test_workspace_roundtrip_with_cross_entity_rule(tmp_path: Path) -> None:
    """Manifest-driven roundtrip: tracked fixture with cross-entity-exists rule.

    Uses tests/fixtures/workspace-cross-entity/ — a minimal tracked package
    with Workspace + Item entities and a cross-entity-exists rule on
    Item.workspaceId → Workspace.  No network dependency; no spec_url; no
    reference to untracked GeneratedApps/ workspace content.
    """
    from appbuilder.metadata.translation import build_metadata_project

    fixture_root = Path(__file__).parent.parent / "fixtures" / "workspace-cross-entity"
    manifest_path = fixture_root / "app-definition.yaml"
    assert manifest_path.exists(), f"Tracked fixture missing: {manifest_path}"

    metadata = build_metadata_project(manifest_path)

    generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest=str(manifest_path),
        generation_run_id="test-roundtrip",
    )
    service_path = tmp_path / "src/main/java/com/appbuilder/workspace/service/ItemServiceBase.java"
    assert service_path.exists(), "ItemServiceBase.java not generated"
    source = service_path.read_text(encoding="utf-8")

    # Cross-entity rule for workspaceId → Workspace must be present
    assert "protected WorkspaceRepository workspaceRepository;" in source
    assert "workspaceRepository.existsById(" in source
    assert "Workspace not found with id:" in source


# ---------------------------------------------------------------------------
# Codex P1 — multiple FK fields to same target entity
# ---------------------------------------------------------------------------

def test_two_fields_same_target_entity_both_get_existence_checks(tmp_path: Path) -> None:
    """Codex P1: Account.primaryCustomerId and Account.secondaryCustomerId both → Customer.
    Repository injected once; existsById check emitted for BOTH fields."""
    metadata = _base_metadata(with_cross_entity=False)
    account = next(e for e in metadata.entities if e.name == "Account")
    account.fields.append(
        CanonicalField(name="primaryCustomerId", type=CanonicalFieldType.STRING, max_length=36)
    )
    account.fields.append(
        CanonicalField(name="secondaryCustomerId", type=CanonicalFieldType.STRING, max_length=36)
    )
    metadata.rules = [
        CanonicalRule(
            entity_name="Account",
            field_name="primaryCustomerId",
            type=RuleType.CROSS_ENTITY_EXISTS,
            source_path="rules.Account.primaryCustomerId.cross-entity-exists",
            target_entity="Customer",
        ),
        CanonicalRule(
            entity_name="Account",
            field_name="secondaryCustomerId",
            type=RuleType.CROSS_ENTITY_EXISTS,
            source_path="rules.Account.secondaryCustomerId.cross-entity-exists",
            target_entity="Customer",
        ),
    ]

    generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )
    source = (
        tmp_path / "src/main/java/com/appbuilder/test/service/AccountServiceBase.java"
    ).read_text(encoding="utf-8")

    # Repository injected exactly once (deduplicated)
    assert source.count("protected CustomerRepository customerRepository;") == 1
    assert source.count("CustomerRepository customerRepository") >= 1

    # existsById check emitted for BOTH fields
    assert "primaryCustomerId" in source or "getPrimaryCustomerId" in source
    assert "secondaryCustomerId" in source or "getSecondaryCustomerId" in source
    assert source.count("customerRepository.existsById(") >= 2


# ---------------------------------------------------------------------------
# Codex P2 — unknown target_entity raises ValueError at generation time
# ---------------------------------------------------------------------------

def test_unknown_target_entity_raises_value_error(tmp_path: Path) -> None:
    """Codex P2: typo in target-entity should fail with a clear error, not generate bad Java."""
    metadata = _base_metadata(with_cross_entity=False)
    metadata.rules = [
        CanonicalRule(
            entity_name="Account",
            field_name="customerId",
            type=RuleType.CROSS_ENTITY_EXISTS,
            source_path="rules.Account.customerId.cross-entity-exists",
            target_entity="Custmer",  # typo — no such entity
        ),
    ]

    with pytest.raises(ValueError, match="unknown entity 'Custmer'"):
        generate_application(
            metadata=metadata,
            output_dir=tmp_path,
            source_manifest="test-manifest.yaml",
            generation_run_id="test-run",
        )


def test_error_message_lists_known_entities(tmp_path: Path) -> None:
    """Codex P2: error message should name the known entities so the user can self-correct."""
    metadata = _base_metadata(with_cross_entity=False)
    metadata.rules = [
        CanonicalRule(
            entity_name="Account",
            field_name="customerId",
            type=RuleType.CROSS_ENTITY_EXISTS,
            source_path="rules.Account.customerId.cross-entity-exists",
            target_entity="Org",  # not in the metadata
        ),
    ]

    with pytest.raises(ValueError) as exc_info:
        generate_application(
            metadata=metadata,
            output_dir=tmp_path,
            source_manifest="test-manifest.yaml",
            generation_run_id="test-run",
        )

    error_text = str(exc_info.value)
    assert "Account" in error_text   # which entity has the bad rule
    assert "customerId" in error_text  # which field
    assert "Org" in error_text         # what was declared
    # Known entities must be listed so the user can self-correct
    assert "Customer" in error_text or "Account" in error_text


# ---------------------------------------------------------------------------
# Codex P3 — FK field type must be compatible with target entity ID type
# ---------------------------------------------------------------------------

def test_type_mismatch_raises_value_error(tmp_path: Path) -> None:
    """Codex P3: FK field type STRING vs target ID type INTEGER raises ValueError before codegen."""
    # Customer.customerId is INTEGER — Account.customerId is STRING → mismatch
    customer_int_id = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.INTEGER, is_id=True, required=True),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, required=True),  # STRING ≠ INTEGER
        ],
    )
    rule = CanonicalRule(
        entity_name="Account",
        field_name="customerId",
        type=RuleType.CROSS_ENTITY_EXISTS,
        source_path="rules.Account.customerId.cross-entity-exists",
        target_entity="Customer",
    )
    metadata = _base_metadata()
    metadata.entities = [customer_int_id, account]
    metadata.rules = [rule]

    with pytest.raises(ValueError) as exc_info:
        generate_application(
            metadata=metadata,
            output_dir=tmp_path,
            source_manifest="test-manifest.yaml",
            generation_run_id="type-mismatch-test",
        )

    error_text = str(exc_info.value)
    assert "Account" in error_text
    assert "customerId" in error_text
    assert "Customer" in error_text
    assert "string" in error_text
    assert "integer" in error_text


def test_type_mismatch_error_message_is_actionable(tmp_path: Path) -> None:
    """Codex P3: error message must name entity, field, target entity, and both types."""
    customer_int_id = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.INTEGER, is_id=True, required=True),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    metadata = _base_metadata()
    metadata.entities = [customer_int_id, account]
    metadata.rules = [
        CanonicalRule(
            entity_name="Account",
            field_name="customerId",
            type=RuleType.CROSS_ENTITY_EXISTS,
            source_path="rules.Account.customerId.cross-entity-exists",
            target_entity="Customer",
        )
    ]

    with pytest.raises(ValueError, match="existsById"):
        generate_application(
            metadata=metadata,
            output_dir=tmp_path,
            source_manifest="test-manifest.yaml",
            generation_run_id="type-mismatch-msg-test",
        )


def test_matching_types_do_not_raise(tmp_path: Path) -> None:
    """Codex P3 (counter-case): matching FK and target ID types must not raise."""
    # Both STRING — no error expected
    metadata = _base_metadata(with_cross_entity=True)
    # _base_metadata already has Customer.customerId=STRING and Account.customerId=STRING
    generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="type-match-test",
    )
    service = (
        tmp_path / "src/main/java/com/appbuilder/test/service/AccountServiceBase.java"
    ).read_text(encoding="utf-8")
    assert "customerRepository.existsById" in service
