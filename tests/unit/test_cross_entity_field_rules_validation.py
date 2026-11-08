"""Validation tests for cross-entity field rule contracts."""

from __future__ import annotations

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
from appbuilder.rules.models import CanonicalRule, RuleType
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

_TEST_PROFILE_NAME = "springboot-cross-entity-field-rule-test"
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


def _base_metadata(rules: list[CanonicalRule]) -> MetadataProject:
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="status", type=CanonicalFieldType.STRING),
            CanonicalField(name="availableBalance", type=CanonicalFieldType.DECIMAL),
        ],
    )
    counterparty = CanonicalEntity(
        name="Counterparty",
        fields=[
            CanonicalField(name="counterpartyId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="sanctionsStatus", type=CanonicalFieldType.STRING),
        ],
    )
    transaction = CanonicalEntity(
        name="Transaction",
        fields=[
            CanonicalField(name="transactionId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, required=True),
            CanonicalField(name="counterpartyId", type=CanonicalFieldType.STRING),
            CanonicalField(name="amount", type=CanonicalFieldType.DECIMAL),
            CanonicalField(name="status", type=CanonicalFieldType.STRING),
        ],
    )

    operations = [
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
        CanonicalOperation(
            name="createCounterparty",
            interface_name="test-api",
            request_entity="Counterparty",
            response_entity="Counterparty",
            http_method=HttpMethod.POST,
            path="/counterparties",
            has_request_body=True,
            response_shape=ResponseShape.CREATED,
        ),
        CanonicalOperation(
            name="createTransaction",
            interface_name="test-api",
            request_entity="Transaction",
            response_entity="Transaction",
            http_method=HttpMethod.POST,
            path="/transactions",
            has_request_body=True,
            response_shape=ResponseShape.CREATED,
        ),
    ]

    mappings = [
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
            operation_name="createCounterparty",
            source_path="test-api.createCounterparty.response.counterpartyId",
            target_path="Counterparty.counterpartyId",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createTransaction",
            source_path="test-api.createTransaction.response.transactionId",
            target_path="Transaction.transactionId",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createTransaction",
            source_path="test-api.createTransaction.request.accountId",
            target_path="Transaction.accountId",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createTransaction",
            source_path="test-api.createTransaction.request.counterpartyId",
            target_path="Transaction.counterpartyId",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createTransaction",
            source_path="test-api.createTransaction.request.amount",
            target_path="Transaction.amount",
        ),
    ]

    return MetadataProject(
        app_name="TestApp",
        bounded_context="test",
        target_profile=_TEST_PROFILE_NAME,
        systems=[SystemParticipant(name="test-api", role="upstream")],
        contracts=[ContractMetadata(name="test-api", type="rest-json", source="test-api-spec.json")],
        operations=operations,
        entities=[account, counterparty, transaction],
        mappings=mappings,
        rules=rules,
    )


def _generate(tmp_path: Path, rules: list[CanonicalRule]) -> None:
    generate_application(
        metadata=_base_metadata(rules),
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )


def _cross_entity_exists_rule(
    *,
    field_name: str,
    target_entity: str,
) -> CanonicalRule:
    return CanonicalRule(
        entity_name="Transaction",
        field_name=field_name,
        type=RuleType.CROSS_ENTITY_EXISTS,
        source_path=f"rules.Transaction.{field_name}.cross-entity-exists",
        target_entity=target_entity,
    )


def test_cross_entity_field_rules_validate_successfully(tmp_path: Path) -> None:
    _generate(
        tmp_path,
        [
            _cross_entity_exists_rule(field_name="accountId", target_entity="Account"),
            _cross_entity_exists_rule(field_name="counterpartyId", target_entity="Counterparty"),
            CanonicalRule(
                entity_name="Transaction",
                field_name="accountId",
                type=RuleType.CROSS_ENTITY_FIELD_CHECK,
                source_path="rules.Transaction.accountId.cross-entity-field-check",
                target_entity="Account",
                target_field="status",
                operator="eq",
                expected_value="ACTIVE",
                error_message="Account must be active",
            ),
            CanonicalRule(
                entity_name="Transaction",
                field_name="accountId",
                type=RuleType.CROSS_ENTITY_FIELD_COMPARE,
                source_path="rules.Transaction.accountId.cross-entity-field-compare",
                target_entity="Account",
                target_field="availableBalance",
                source_field="amount",
                operator="lte",
            ),
            CanonicalRule(
                entity_name="Transaction",
                field_name="counterpartyId",
                type=RuleType.CROSS_ENTITY_FIELD_IN,
                source_path="rules.Transaction.counterpartyId.cross-entity-field-in",
                target_entity="Counterparty",
                target_field="sanctionsStatus",
                values=["CLEARED", "PENDING_REVIEW"],
            ),
        ],
    )


def test_cross_entity_field_rule_requires_matching_cross_entity_exists_rule(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires a matching 'cross-entity-exists' rule"):
        _generate(
            tmp_path,
            [
                CanonicalRule(
                    entity_name="Transaction",
                    field_name="accountId",
                    type=RuleType.CROSS_ENTITY_FIELD_CHECK,
                    source_path="rules.Transaction.accountId.cross-entity-field-check",
                    target_entity="Account",
                    target_field="status",
                    operator="eq",
                    expected_value="ACTIVE",
                )
            ],
        )


def test_cross_entity_field_check_rejects_unknown_target_entity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown entity 'Accounts'"):
        _generate(
            tmp_path,
            [
                _cross_entity_exists_rule(field_name="accountId", target_entity="Accounts"),
                CanonicalRule(
                    entity_name="Transaction",
                    field_name="accountId",
                    type=RuleType.CROSS_ENTITY_FIELD_CHECK,
                    source_path="rules.Transaction.accountId.cross-entity-field-check",
                    target_entity="Accounts",
                    target_field="status",
                    operator="eq",
                    expected_value="ACTIVE",
                )
            ],
        )


def test_cross_entity_field_check_rejects_unknown_target_field(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown target field 'state'"):
        _generate(
            tmp_path,
            [
                _cross_entity_exists_rule(field_name="accountId", target_entity="Account"),
                CanonicalRule(
                    entity_name="Transaction",
                    field_name="accountId",
                    type=RuleType.CROSS_ENTITY_FIELD_CHECK,
                    source_path="rules.Transaction.accountId.cross-entity-field-check",
                    target_entity="Account",
                    target_field="state",
                    operator="eq",
                    expected_value="ACTIVE",
                )
            ],
        )


def test_cross_entity_field_compare_rejects_unknown_source_field(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown source field 'requestedAmount'"):
        _generate(
            tmp_path,
            [
                _cross_entity_exists_rule(field_name="accountId", target_entity="Account"),
                CanonicalRule(
                    entity_name="Transaction",
                    field_name="accountId",
                    type=RuleType.CROSS_ENTITY_FIELD_COMPARE,
                    source_path="rules.Transaction.accountId.cross-entity-field-compare",
                    target_entity="Account",
                    target_field="availableBalance",
                    source_field="requestedAmount",
                    operator="lte",
                )
            ],
        )


def test_cross_entity_field_compare_rejects_non_numeric_source_field(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires numeric source-field 'status'"):
        _generate(
            tmp_path,
            [
                _cross_entity_exists_rule(field_name="accountId", target_entity="Account"),
                CanonicalRule(
                    entity_name="Transaction",
                    field_name="accountId",
                    type=RuleType.CROSS_ENTITY_FIELD_COMPARE,
                    source_path="rules.Transaction.accountId.cross-entity-field-compare",
                    target_entity="Account",
                    target_field="availableBalance",
                    source_field="status",
                    operator="lte",
                )
            ],
        )


def test_cross_entity_field_compare_rejects_non_numeric_target_field(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires numeric target-field 'status'"):
        _generate(
            tmp_path,
            [
                _cross_entity_exists_rule(field_name="accountId", target_entity="Account"),
                CanonicalRule(
                    entity_name="Transaction",
                    field_name="accountId",
                    type=RuleType.CROSS_ENTITY_FIELD_COMPARE,
                    source_path="rules.Transaction.accountId.cross-entity-field-compare",
                    target_entity="Account",
                    target_field="status",
                    source_field="amount",
                    operator="lte",
                )
            ],
        )


def test_cross_entity_field_check_rejects_incompatible_expected_value(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="expected-value 'ACTIVE'"):
        _generate(
            tmp_path,
            [
                _cross_entity_exists_rule(field_name="accountId", target_entity="Account"),
                CanonicalRule(
                    entity_name="Transaction",
                    field_name="accountId",
                    type=RuleType.CROSS_ENTITY_FIELD_CHECK,
                    source_path="rules.Transaction.accountId.cross-entity-field-check",
                    target_entity="Account",
                    target_field="availableBalance",
                    operator="eq",
                    expected_value="ACTIVE",
                )
            ],
        )


def test_cross_entity_field_compare_rejects_unsupported_named_operator(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported operator 'between'"):
        _generate(
            tmp_path,
            [
                _cross_entity_exists_rule(field_name="accountId", target_entity="Account"),
                CanonicalRule(
                    entity_name="Transaction",
                    field_name="accountId",
                    type=RuleType.CROSS_ENTITY_FIELD_COMPARE,
                    source_path="rules.Transaction.accountId.cross-entity-field-compare",
                    target_entity="Account",
                    target_field="availableBalance",
                    source_field="amount",
                    operator="between",
                )
            ],
        )


def test_cross_entity_field_in_rejects_empty_allowed_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="allowed-values"):
        _generate(
            tmp_path,
            [
                _cross_entity_exists_rule(field_name="counterpartyId", target_entity="Counterparty"),
                CanonicalRule(
                    entity_name="Transaction",
                    field_name="counterpartyId",
                    type=RuleType.CROSS_ENTITY_FIELD_IN,
                    source_path="rules.Transaction.counterpartyId.cross-entity-field-in",
                    target_entity="Counterparty",
                    target_field="sanctionsStatus",
                    values=[],
                )
            ],
        )
