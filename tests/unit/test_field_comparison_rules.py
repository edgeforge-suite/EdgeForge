"""Tests for the field-comparison rule type."""

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

_TEST_PROFILE_NAME = "springboot-field-comparison-test"
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


def _field_comparison_metadata(
    *,
    entity_name: str = "Repayment",
    bounded_context: str = "payments",
    left_name: str = "paidAmount",
    right_name: str = "dueAmount",
    left_type: CanonicalFieldType = CanonicalFieldType.DECIMAL,
    right_type: CanonicalFieldType = CanonicalFieldType.DECIMAL,
    operator: str = "<=",
    include_rule: bool = True,
    rules: list[CanonicalRule] | None = None,
) -> MetadataProject:
    entity_var = entity_name[:1].lower() + entity_name[1:]
    entity_id_name = f"{entity_var}Id"
    entity = CanonicalEntity(
        name=entity_name,
        fields=[
            CanonicalField(
                name=entity_id_name,
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
            ),
            CanonicalField(name=left_name, type=left_type),
            CanonicalField(name=right_name, type=right_type),
        ],
    )

    create_op = CanonicalOperation(
        name=f"create{entity_name}",
        interface_name="test-api",
        request_entity=entity_name,
        response_entity=entity_name,
        http_method=HttpMethod.POST,
        path=f"/{entity_name.lower()}s",
        has_request_body=True,
        response_shape=ResponseShape.CREATED,
    )

    mappings = [
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name=f"create{entity_name}",
            source_path=f"test-api.create{entity_name}.request.{left_name}",
            target_path=f"{entity_name}.{left_name}",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name=f"create{entity_name}",
            source_path=f"test-api.create{entity_name}.request.{right_name}",
            target_path=f"{entity_name}.{right_name}",
        ),
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name=f"create{entity_name}",
            source_path=f"test-api.create{entity_name}.response.{entity_id_name}",
            target_path=f"{entity_name}.{entity_id_name}",
        ),
    ]

    if rules is None:
        rules = []
        if include_rule:
            rules.append(
                CanonicalRule(
                    entity_name=entity_name,
                    field_name=left_name,
                    type=RuleType.FIELD_COMPARISON,
                    source_path=f"rules.{entity_name}.{left_name}.field-comparison",
                    operator=operator,
                    compare_to_field=right_name,
                )
            )

    return MetadataProject(
        app_name="TestApp",
        bounded_context=bounded_context,
        target_profile=_TEST_PROFILE_NAME,
        systems=[SystemParticipant(name="test-api", role="upstream")],
        contracts=[ContractMetadata(name="test-api", type="rest-json", source="test-api-spec.json")],
        operations=[create_op],
        entities=[entity],
        mappings=mappings,
        rules=rules,
    )


def _generate_service(tmp_path: Path, metadata: MetadataProject, *, entity_name: str = "Repayment") -> str:
    generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )
    return (
        tmp_path
        / f"src/main/java/com/appbuilder/{metadata.bounded_context}/service/{entity_name}ServiceBase.java"
    ).read_text(encoding="utf-8")


def _generate_exception_handler(tmp_path: Path, metadata: MetadataProject) -> str:
    generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )
    return (
        tmp_path
        / f"src/main/java/com/appbuilder/{metadata.bounded_context}/exception/GlobalExceptionHandler.java"
    ).read_text(encoding="utf-8")


def test_field_comparison_rule_parsed_correctly(tmp_path: Path) -> None:
    rule_file = tmp_path / "repayment-rules.yaml"
    rule_file.write_text(
        textwrap.dedent(
            """\
            entity: Repayment
            rules:
              - field: paidAmount
                type: field-comparison
                operator: "<="
                compare-to-field: dueAmount
            """
        ),
        encoding="utf-8",
    )

    entity_name, rules = load_rule_definitions(rule_file)

    assert entity_name == "Repayment"
    assert len(rules) == 1
    rule = rules[0]
    assert rule.type == RuleType.FIELD_COMPARISON
    assert rule.operator == "<="
    assert rule.compare_to_field == "dueAmount"


def test_field_comparison_missing_operator_raises(tmp_path: Path) -> None:
    rule_file = tmp_path / "bad-rules.yaml"
    rule_file.write_text(
        textwrap.dedent(
            """\
            entity: Repayment
            rules:
              - field: paidAmount
                type: field-comparison
                compare-to-field: dueAmount
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="operator"):
        load_rule_definitions(rule_file)


def test_field_comparison_invalid_operator_raises(tmp_path: Path) -> None:
    rule_file = tmp_path / "bad-rules.yaml"
    rule_file.write_text(
        textwrap.dedent(
            """\
            entity: Repayment
            rules:
              - field: paidAmount
                type: field-comparison
                operator: "!="
                compare-to-field: dueAmount
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="operator in"):
        load_rule_definitions(rule_file)


def test_field_comparison_missing_compare_to_field_raises(tmp_path: Path) -> None:
    rule_file = tmp_path / "bad-rules.yaml"
    rule_file.write_text(
        textwrap.dedent(
            """\
            entity: Repayment
            rules:
              - field: paidAmount
                type: field-comparison
                operator: "<="
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="compare-to-field"):
        load_rule_definitions(rule_file)


def test_decimal_field_comparison_emits_compare_to_check(tmp_path: Path) -> None:
    source = _generate_service(tmp_path, _field_comparison_metadata())

    assert ".compareTo(" in source
    assert "<= 0" in source


def test_integer_field_comparison_emits_direct_comparison(tmp_path: Path) -> None:
    metadata = _field_comparison_metadata(
        entity_name="Order",
        bounded_context="orders",
        left_name="itemCount",
        right_name="maxItems",
        left_type=CanonicalFieldType.INTEGER,
        right_type=CanonicalFieldType.INTEGER,
    )

    source = _generate_service(tmp_path, metadata, entity_name="Order")

    assert "!(order.getItemCount() <= order.getMaxItems())" in source
    assert ".compareTo(" not in source


def test_field_comparison_skips_null_fields(tmp_path: Path) -> None:
    source = _generate_service(tmp_path, _field_comparison_metadata())

    assert "repayment.getPaidAmount() != null && repayment.getDueAmount() != null" in source


def test_string_field_comparison_emits_todo_comment(tmp_path: Path) -> None:
    metadata = _field_comparison_metadata(
        left_name="startCode",
        right_name="endCode",
        left_type=CanonicalFieldType.STRING,
        right_type=CanonicalFieldType.STRING,
    )

    report = generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )
    source = (
        tmp_path
        / "src/main/java/com/appbuilder/payments/service/RepaymentServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "compareValues(repayment, \"startCode\"" in source
    assert "validateComparison(repayment, \"startCode\"" in source
    assert ".compareTo(" not in source
    assert any("String comparisons are not supported in v1" in warning for warning in report.warnings)


def test_global_exception_handler_maps_illegal_argument_to_400(tmp_path: Path) -> None:
    source = _generate_exception_handler(tmp_path, _field_comparison_metadata())

    assert "@ExceptionHandler(IllegalArgumentException.class)" in source
    assert "@ResponseStatus(HttpStatus.BAD_REQUEST)" in source
    assert "public ErrorResponse handleBusinessRule(" in source


def test_field_comparison_400_message_includes_field_names_and_values(tmp_path: Path) -> None:
    source = _generate_service(tmp_path, _field_comparison_metadata())

    assert '"paidAmount must be <= dueAmount but got paidAmount="' in source
    assert 'repayment.getPaidAmount() + ", dueAmount=" + repayment.getDueAmount()' in source


def test_allowed_values_rule_also_covered_by_bad_request_handler(tmp_path: Path) -> None:
    metadata = _field_comparison_metadata(include_rule=False)
    metadata.rules = [
        CanonicalRule(
            entity_name="Repayment",
            field_name="status",
            type=RuleType.ALLOWED_VALUES,
            source_path="rules.Repayment.status.allowed-values",
            values=["PENDING", "PAID"],
        )
    ]
    metadata.entities[0].fields.append(CanonicalField(name="status", type=CanonicalFieldType.STRING))
    metadata.mappings.append(
        FieldMapping(
            contract_name="test-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createRepayment",
            source_path="test-api.createRepayment.request.status",
            target_path="Repayment.status",
        )
    )

    source = _generate_exception_handler(tmp_path, metadata)

    assert "@ExceptionHandler(IllegalArgumentException.class)" in source


def test_field_comparison_same_field_warns_and_skips(tmp_path: Path) -> None:
    metadata = _field_comparison_metadata(
        rules=[
            CanonicalRule(
                entity_name="Repayment",
                field_name="paidAmount",
                type=RuleType.FIELD_COMPARISON,
                source_path="rules.Repayment.paidAmount.field-comparison",
                operator="<=",
                compare_to_field="paidAmount",
            )
        ]
    )

    report = generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )
    source = (
        tmp_path
        / "src/main/java/com/appbuilder/payments/service/RepaymentServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "compareTo(" not in source
    assert any("compares the field to itself" in warning for warning in report.warnings)


def test_field_comparison_missing_compare_field_warns_and_skips(tmp_path: Path) -> None:
    metadata = _field_comparison_metadata(
        rules=[
            CanonicalRule(
                entity_name="Repayment",
                field_name="paidAmount",
                type=RuleType.FIELD_COMPARISON,
                source_path="rules.Repayment.paidAmount.field-comparison",
                operator="<=",
                compare_to_field="missingField",
            )
        ]
    )

    report = generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="test-run",
    )
    source = (
        tmp_path
        / "src/main/java/com/appbuilder/payments/service/RepaymentServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "compareTo(" not in source
    assert any("compare-to-field 'missingField' was not found" in warning for warning in report.warnings)
