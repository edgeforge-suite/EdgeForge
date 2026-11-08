"""Tests for FK constraint propagation and generic ID UI constraint rendering."""

from __future__ import annotations

import json
from pathlib import Path

from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project


def _write_constraint_propagation_project(
    project_root: Path,
    *,
    customer_request_includes_id: bool = True,
    customer_id_rule_lines: list[str] | None = None,
    account_customer_id_rule_lines: list[str] | None = None,
    account_id_rule_lines: list[str] | None = None,
) -> Path:
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "contracts").mkdir(parents=True)
    (project_root / "rules").mkdir(parents=True)

    (project_root / "contracts" / "customer-api-spec.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (project_root / "contracts" / "account-api-spec.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

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
        "\n".join(customer_mapping_lines),
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
        ),
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
                "app_name: Constraint Propagation Test",
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


def _build_constraint_metadata(
    tmp_path: Path,
    *,
    customer_request_includes_id: bool = True,
    customer_id_rule_lines: list[str] | None = None,
    account_customer_id_rule_lines: list[str] | None = None,
    account_id_rule_lines: list[str] | None = None,
):
    manifest_path = _write_constraint_propagation_project(
        tmp_path / "constraint-propagation",
        customer_request_includes_id=customer_request_includes_id,
        customer_id_rule_lines=customer_id_rule_lines,
        account_customer_id_rule_lines=account_customer_id_rule_lines,
        account_id_rule_lines=account_id_rule_lines,
    )
    return build_metadata_project(manifest_path)


def _entity_field(metadata, entity_name: str, field_name: str):
    entity = next(entity for entity in metadata.entities if entity.name == entity_name)
    return next(field for field in entity.fields if field.name == field_name)


def test_fk_field_inherits_target_id_max_length(tmp_path: Path) -> None:
    metadata = _build_constraint_metadata(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
    )

    account_customer_id = _entity_field(metadata, "Account", "customerId")
    assert account_customer_id.max_length == 6


def test_fk_field_does_not_override_explicit_source_max_length(tmp_path: Path) -> None:
    metadata = _build_constraint_metadata(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
        account_customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '4'",
        ],
    )

    account_customer_id = _entity_field(metadata, "Account", "customerId")
    assert account_customer_id.max_length == 4


def test_fk_field_inherits_target_id_pattern(tmp_path: Path) -> None:
    metadata = _build_constraint_metadata(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: pattern",
            "  value: '^[A-Z0-9]{6}$'",
        ],
    )

    account_customer_id = _entity_field(metadata, "Account", "customerId")
    assert account_customer_id.pattern == "^[A-Z0-9]{6}$"


def test_only_supported_constraints_propagate(tmp_path: Path) -> None:
    metadata = _build_constraint_metadata(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: min-length",
            "  value: '6'",
            "- field: customerId",
            "  type: allowed-values",
            "  values:",
            "  - CUST01",
            "  - CUST02",
            "- field: customerId",
            "  type: default",
            "  value: CUST01",
        ],
    )

    account_customer_id = _entity_field(metadata, "Account", "customerId")
    assert account_customer_id.min_length == 6
    assert account_customer_id.allowed_values == []
    assert account_customer_id.default_value is None
    assert account_customer_id.range_min is None
    assert account_customer_id.range_max is None


def test_create_ui_renders_propagated_fk_maxlength(tmp_path: Path) -> None:
    metadata = _build_constraint_metadata(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
    )

    report = generate_application(metadata, tmp_path / "GeneratedApp", generation_run_id="fk-ui")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert (
        'id="createAccount-customerId" name="createAccount-customerId" '
        'type="text" maxlength="6" required'
    ) in html


def test_get_update_delete_id_inputs_render_entity_id_constraints(tmp_path: Path) -> None:
    metadata = _build_constraint_metadata(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
            "- field: customerId",
            "  type: pattern",
            "  value: '^[A-Z0-9]{6}$'",
        ],
    )

    report = generate_application(metadata, tmp_path / "GeneratedApp", generation_run_id="id-ui")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="get-id-Customer"' in html and 'maxlength="6"' in html
    assert 'id="update-id-Customer"' in html and 'pattern="^[A-Z0-9]{6}$"' in html
    assert 'id="delete-id-Customer"' in html and 'maxlength="6"' in html


def test_response_only_id_rule_is_ignored_for_generic_id_inputs(tmp_path: Path) -> None:
    metadata = _build_constraint_metadata(
        tmp_path,
        account_id_rule_lines=[
            "- field: accountId",
            "  type: max-length",
            "  value: '10'",
        ],
    )

    report = generate_application(metadata, tmp_path / "GeneratedApp", generation_run_id="response-id-ui")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="get-id-Account"' in html and 'maxlength="10"' not in html
    assert 'id="update-id-Account"' in html and 'maxlength="10"' not in html
    assert 'id="delete-id-Account"' in html and 'maxlength="10"' not in html


def test_cross_entity_exists_remains_text_input_not_dropdown(tmp_path: Path) -> None:
    metadata = _build_constraint_metadata(
        tmp_path,
        customer_id_rule_lines=[
            "- field: customerId",
            "  type: max-length",
            "  value: '6'",
        ],
    )

    report = generate_application(metadata, tmp_path / "GeneratedApp", generation_run_id="fk-text-input")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="createAccount-customerId"' in html
    assert '<select id="createAccount-customerId"' not in html
    assert 'type="text"' in html


def test_generated_basic_dda_ui_contains_expected_maxlengths(tmp_path: Path) -> None:
    metadata = _build_constraint_metadata(
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

    report = generate_application(metadata, tmp_path / "GeneratedApp", generation_run_id="dda-html")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="createAccount-customerId"' in html and 'maxlength="6"' in html
    assert 'id="get-id-Customer"' in html and 'maxlength="6"' in html
    assert 'id="get-id-Account"' in html and 'maxlength="10"' not in html
