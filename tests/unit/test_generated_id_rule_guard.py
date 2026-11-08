"""Tests for server-generated ID rule guardrails."""

from __future__ import annotations

import json
import re
from pathlib import Path

from appbuilder.generation import GenerationReport, generate_application
from appbuilder.metadata import MetadataProject, build_metadata_project


def _write_generated_id_guard_project(
    project_root: Path,
    *,
    customer_request_includes_id: bool = False,
    customer_id_rule_lines: list[str] | None = None,
    account_customer_id_rule_lines: list[str] | None = None,
    account_id_rule_lines: list[str] | None = None,
) -> Path:
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "contracts").mkdir(parents=True)
    (project_root / "rules").mkdir(parents=True)

    (project_root / "contracts" / "customer-api-spec.json").write_text("{}\n", encoding="utf-8")
    (project_root / "contracts" / "account-api-spec.json").write_text("{}\n", encoding="utf-8")

    customer_request_payload = {"customerName": "Alice"}
    if customer_request_includes_id:
        customer_request_payload["customerId"] = "CUST01"

    (project_root / "upstream" / "create-customer-request.json").write_text(
        json.dumps(customer_request_payload),
        encoding="utf-8",
    )
    (project_root / "upstream" / "create-customer-response.json").write_text(
        json.dumps({"customerId": "CUST01", "customerName": "Alice"}),
        encoding="utf-8",
    )
    (project_root / "upstream" / "create-account-request.json").write_text(
        json.dumps({"customerId": "CUST01", "currency": "USD", "status": "Active"}),
        encoding="utf-8",
    )
    (project_root / "upstream" / "create-account-response.json").write_text(
        json.dumps(
            {
                "accountId": "ACCOUNT0001",
                "customerId": "CUST01",
                "currency": "USD",
                "status": "Active",
            }
        ),
        encoding="utf-8",
    )

    customer_mapping_lines = [
        "interface: dda-customer-api",
        "entity: Customer",
        "operations:",
        "- name: createCustomer",
        "  request_mappings:",
    ]
    if customer_request_includes_id:
        customer_mapping_lines.extend(
            [
                "  - source: customerId",
                "    target: Customer.customerId",
            ]
        )
    customer_mapping_lines.extend(
        [
            "  - source: customerName",
            "    target: Customer.customerName",
            "  response_mappings:",
            "  - source: customerId",
            "    target: Customer.customerId",
            "  - source: customerName",
            "    target: Customer.customerName",
        ]
    )
    (project_root / "upstream" / "customer-mapping.yaml").write_text(
        "\n".join(customer_mapping_lines) + "\n",
        encoding="utf-8",
    )

    (project_root / "upstream" / "account-mapping.yaml").write_text(
        "\n".join(
            [
                "interface: dda-account-api",
                "entity: Account",
                "operations:",
                "- name: createAccount",
                "  request_mappings:",
                "  - source: customerId",
                "    target: Account.customerId",
                "  - source: currency",
                "    target: Account.currency",
                "  - source: status",
                "    target: Account.status",
                "  response_mappings:",
                "  - source: accountId",
                "    target: Account.accountId",
                "  - source: customerId",
                "    target: Account.customerId",
                "  - source: currency",
                "    target: Account.currency",
                "  - source: status",
                "    target: Account.status",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    customer_rules = ["entity: Customer"]
    if customer_id_rule_lines:
        customer_rules.append("rules:")
        customer_rules.extend(customer_id_rule_lines)
    else:
        customer_rules.append("rules: []")
    (project_root / "rules" / "customer-rules.yaml").write_text(
        "\n".join(customer_rules) + "\n",
        encoding="utf-8",
    )

    account_rules = ["entity: Account", "rules:"]
    account_rules.extend(
        [
            "- field: customerId",
            "  type: cross-entity-exists",
            "  target-entity: Customer",
        ]
    )
    if account_customer_id_rule_lines:
        account_rules.extend(account_customer_id_rule_lines)
    if account_id_rule_lines:
        account_rules.extend(account_id_rule_lines)
    (project_root / "rules" / "account-rules.yaml").write_text(
        "\n".join(account_rules) + "\n",
        encoding="utf-8",
    )

    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Generated ID Guard Test",
                "bounded_context: dda",
                "schema_version: \"2.0\"",
                "target_profile: springboot-legacy-compatible",
                "upstream_interfaces:",
                "  - name: dda-customer-api",
                "    system: SyntheticRegistry",
                "    type: rest-json",
                "    spec: contracts/customer-api-spec.json",
                "    mapping: upstream/customer-mapping.yaml",
                "    operations:",
                "      - name: createCustomer",
                "        request_sample: upstream/create-customer-request.json",
                "        response_sample: upstream/create-customer-response.json",
                "  - name: dda-account-api",
                "    system: SyntheticRegistry",
                "    type: rest-json",
                "    spec: contracts/account-api-spec.json",
                "    mapping: upstream/account-mapping.yaml",
                "    operations:",
                "      - name: createAccount",
                "        request_sample: upstream/create-account-request.json",
                "        response_sample: upstream/create-account-response.json",
                "rules:",
                "  - rules/customer-rules.yaml",
                "  - rules/account-rules.yaml",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root / "app-definition.yaml"


def _build_guard_metadata(
    tmp_path: Path,
    *,
    customer_request_includes_id: bool = False,
    customer_id_rule_lines: list[str] | None = None,
    account_customer_id_rule_lines: list[str] | None = None,
    account_id_rule_lines: list[str] | None = None,
) -> MetadataProject:
    manifest_path = _write_generated_id_guard_project(
        tmp_path / "generated-id-guard",
        customer_request_includes_id=customer_request_includes_id,
        customer_id_rule_lines=customer_id_rule_lines,
        account_customer_id_rule_lines=account_customer_id_rule_lines,
        account_id_rule_lines=account_id_rule_lines,
    )
    return build_metadata_project(manifest_path)


def _entity_field(metadata: MetadataProject, entity_name: str, field_name: str):
    entity = next(entity for entity in metadata.entities if entity.name == entity_name)
    return next(field for field in entity.fields if field.name == field_name)


def _generate_guard_app(
    tmp_path: Path,
    *,
    customer_request_includes_id: bool = False,
    customer_id_rule_lines: list[str] | None = None,
    account_customer_id_rule_lines: list[str] | None = None,
    account_id_rule_lines: list[str] | None = None,
) -> tuple[MetadataProject, GenerationReport, Path]:
    metadata = _build_guard_metadata(
        tmp_path,
        customer_request_includes_id=customer_request_includes_id,
        customer_id_rule_lines=customer_id_rule_lines,
        account_customer_id_rule_lines=account_customer_id_rule_lines,
        account_id_rule_lines=account_id_rule_lines,
    )
    output_dir = tmp_path / "generated"
    report = generate_application(
        metadata=metadata,
        output_dir=output_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="generated-id-guard",
    )
    return metadata, report, output_dir


def _warning_contains(report: GenerationReport, snippet: str) -> bool:
    return any(snippet in warning for warning in report.warnings)


def test_server_generated_id_does_not_propagate_max_length_to_fk(tmp_path: Path) -> None:
    metadata = _build_guard_metadata(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
    )

    customer_id = _entity_field(metadata, "Customer", "customerId")
    account_customer_id = _entity_field(metadata, "Account", "customerId")

    assert customer_id.server_generated_id is True
    assert account_customer_id.max_length is None


def test_server_generated_id_does_not_render_generic_id_maxlength(tmp_path: Path) -> None:
    _, report, output_dir = _generate_guard_app(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
        account_id_rule_lines=[
            "- field: accountId",
            "  type: max-length",
            "  value: '10'",
        ],
    )

    html = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")
    for input_id in ("get-id-Customer", "update-id-Customer", "delete-id-Customer"):
        assert re.search(rf'id="{input_id}"[^>]*maxlength=', html) is None
    for input_id in ("get-id-Account", "update-id-Account", "delete-id-Account"):
        assert re.search(rf'id="{input_id}"[^>]*maxlength=', html) is None

    assert _warning_contains(
        report,
        "Customer.customerId: input/UI constraints were suppressed because the field is a server-generated ID.",
    )


def test_server_generated_id_rule_emits_warning(tmp_path: Path) -> None:
    _, report, _ = _generate_guard_app(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
    )

    assert _warning_contains(
        report,
        "Customer: customerId: rule 'max-length' targets a server-generated ID and was ignored for input/FK constraint generation.",
    )


def test_cross_entity_exists_still_enforced_without_shape_propagation(tmp_path: Path) -> None:
    _, _, output_dir = _generate_guard_app(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
    )

    service = (
        output_dir
            / "src/main/java/com/appbuilder/dda/service/AccountServiceBase.java"
    ).read_text(encoding="utf-8")
    request_dto = (
        output_dir
        / "src/main/java/com/appbuilder/dda/adapter/inbound/CreateAccountRequest.java"
    ).read_text(encoding="utf-8")

    assert "customerRepository.existsById" in service
    assert "@CodePointLength(max=6)" not in request_dto


def test_client_supplied_id_still_propagates_constraints_normally(tmp_path: Path) -> None:
    metadata, report, output_dir = _generate_guard_app(
        tmp_path,
        customer_request_includes_id=True,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
    )

    account_customer_id = _entity_field(metadata, "Account", "customerId")
    assert account_customer_id.max_length == 6

    html = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")
    assert 'id="createAccount-customerId"' in html and 'maxlength="6"' in html
    assert 'id="get-id-Customer"' in html and 'maxlength="6"' in html
    assert not _warning_contains(report, "targets a server-generated ID")


def test_generated_basic_dda_like_case_warns_and_avoids_broken_constraints(tmp_path: Path) -> None:
    _, report, output_dir = _generate_guard_app(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
        account_id_rule_lines=[
            "- field: accountId",
            "  type: max-length",
            "  value: '10'",
        ],
    )

    html = (output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")
    assert re.search(r'id="createAccount-customerId"[^>]*maxlength="6"', html) is None
    assert re.search(r'id="get-id-Account"[^>]*maxlength="10"', html) is None
    assert _warning_contains(
        report,
        "Account: customerId: cross-entity-exists target 'Customer.customerId' is server-generated, so ID shape constraints were not propagated.",
    )
    assert _warning_contains(
        report,
        "Account: accountId: rule 'max-length' targets a server-generated ID and was ignored for input/FK constraint generation.",
    )


def test_server_generated_id_default_and_allowed_values_rules_do_not_generate_service_logic(
    tmp_path: Path,
) -> None:
    _, report, output_dir = _generate_guard_app(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: default",
            "  value: CUST01",
            "- field: customerId",
            "  type: allowed-values",
            "  values:",
            "  - CUST01",
            "  - CUST02",
        ],
    )

    service = (
        output_dir
        / "src/main/java/com/appbuilder/dda/service/CustomerServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "ALLOWED_CUSTOMER_ID_VALUES" not in service
    assert "Invalid value for customerId" not in service
    assert "if (customer.getCustomerId() == null)" not in service
    assert _warning_contains(
        report,
        "Customer: customerId: rule 'default' targets a server-generated ID and was ignored for input/FK constraint generation.",
    )
    assert _warning_contains(
        report,
        "Customer: customerId: rule 'allowed-values' targets a server-generated ID and was ignored for input/FK constraint generation.",
    )
