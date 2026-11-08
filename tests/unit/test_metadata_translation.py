import json
import shutil
from pathlib import Path

import pytest

from appbuilder.contracts import load_project_definition
from appbuilder.mapping import MappingCompletenessReport, MappingDirection
from appbuilder.metadata import CanonicalFieldType, IdGenerationStrategy, build_metadata_project
from appbuilder.metadata.translation import (
    _auto_include_unmapped_response_sample_fields,
    _flatten_sample_field_names,
    _infer_canonical_type,
    _schema_field_hints,
)


def _write_sample_based_project(
    project_root: Path,
    *,
    request_payload: dict,
    response_payload: dict,
    request_mappings: list[tuple[str, str]],
    response_mappings: list[tuple[str, str]],
    pageable: bool = False,
    entity_name: str = "Customer",
    operation_name: str = "createCustomer",
    identity_overrides: list[tuple[str, str]] | None = None,
) -> Path:
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "upstream" / "create-customer-request.json").write_text(
        json.dumps(request_payload),
        encoding="utf-8",
    )
    (project_root / "upstream" / "create-customer-response.json").write_text(
        json.dumps(response_payload),
        encoding="utf-8",
    )

    lines = [
        "interface: customer-api",
        f"entity: {entity_name}",
        "operations:",
        f"  - name: {operation_name}",
    ]
    if request_mappings:
        lines.append("    request_mappings:")
        for source, target in request_mappings:
            lines.extend(
                [
                    f"      - source: {source}",
                    f"        target: {target}",
                ]
            )
    else:
        lines.append("    request_mappings: []")
    if response_mappings:
        lines.append("    response_mappings:")
        for source, target in response_mappings:
            lines.extend(
                [
                    f"      - source: {source}",
                    f"        target: {target}",
                ]
            )
    else:
        lines.append("    response_mappings: []")
    (project_root / "upstream" / "customer-mapping.yaml").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Customer Modernization",
                "bounded_context: customers",
                "schema_version: \"2.0\"",
                *(
                    [
                        "identity_overrides:",
                        *[
                            "\n".join(
                                [
                                    f"  - entity: {entity}",
                                    f"    persistence_id: {persistence_id}",
                                ]
                            )
                            for entity, persistence_id in identity_overrides
                        ],
                    ]
                    if identity_overrides
                    else []
                ),
                "upstream_interfaces:",
                "  - name: customer-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec_url: https://example.com/customer-api.json",
                "    mapping: upstream/customer-mapping.yaml",
                "    operations:",
                f"      - name: {operation_name}",
                "        request_sample: upstream/create-customer-request.json",
                "        response_sample: upstream/create-customer-response.json",
                f"        pageable: {str(pageable).lower()}",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )
    return project_root / "app-definition.yaml"


def _write_identity_project(
    project_root: Path,
    *,
    entity_name: str,
    response_payload: dict,
    response_mappings: list[tuple[str, str]],
    identity_overrides: list[tuple[str, str]] | None = None,
) -> Path:
    return _write_sample_based_project(
        project_root,
        request_payload={},
        response_payload=response_payload,
        request_mappings=[],
        response_mappings=response_mappings,
        entity_name=entity_name,
        operation_name=f"create{entity_name}",
        identity_overrides=identity_overrides,
    )


def _write_id_generation_project(
    project_root: Path,
    *,
    entity_name: str = "Loan",
    field_type: str,
    id_field_name: str,
    id_generation_overrides: list[dict[str, str]] | None = None,
    identity_overrides: list[dict[str, str]] | None = None,
    server_generated_id: bool = True,
) -> Path:
    id_value = 1001 if field_type == "integer" else "id-1001"
    request_payload = {"name": "Test Loan"}
    request_mappings = [("name", f"{entity_name}.name")]
    if not server_generated_id:
        request_payload[id_field_name] = id_value
        request_mappings.insert(0, (id_field_name, f"{entity_name}.{id_field_name}"))

    response_payload = {
        id_field_name: id_value,
        "name": "Test Loan",
    }

    manifest_path = _write_sample_based_project(
        project_root,
        request_payload=request_payload,
        response_payload=response_payload,
        request_mappings=request_mappings,
        response_mappings=[
            (id_field_name, f"{entity_name}.{id_field_name}"),
            ("name", f"{entity_name}.name"),
        ],
        entity_name=entity_name,
        operation_name=f"create{entity_name}",
        identity_overrides=[
            (override["entity"], override["persistence_id"])
            for override in (identity_overrides or [])
        ],
    )

    if id_generation_overrides:
        manifest_lines = manifest_path.read_text(encoding="utf-8").splitlines()
        insert_at = next(
            index for index, line in enumerate(manifest_lines) if line == "upstream_interfaces:"
        )
        override_lines = ["id_generation_overrides:"]
        for override in id_generation_overrides:
            override_lines.append(f"  - entity: {override['entity']}")
            if override.get("field") is not None:
                override_lines.append(f"    field: {override['field']}")
            override_lines.append(f"    strategy: {override['strategy']}")
            if override.get("sequence_name") is not None:
                override_lines.append(f"    sequence_name: {override['sequence_name']}")
        manifest_lines[insert_at:insert_at] = override_lines
        manifest_path.write_text("\n".join(manifest_lines), encoding="utf-8")

    return manifest_path


def test_build_metadata_project_matches_xyz_golden_fixture() -> None:
    metadata = build_metadata_project(
        "examples/input-projects/xyz-accounts-modernization/app-definition.yaml"
    )
    golden_path = Path("tests/golden_contracts/xyz_accounts_metadata.json")
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    actual = metadata.model_dump(mode="json")

    # The exact fetch exception detail for a failed spec_url lookup can vary
    # by environment. Keep the golden check exact for the structural metadata,
    # but normalize that one advisory note before comparison.
    actual["contracts"][0]["ingestion_notes"] = ["<normalized-spec-url-fetch-failure>"]
    expected["contracts"][0]["ingestion_notes"] = ["<normalized-spec-url-fetch-failure>"]

    assert json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)

    note = metadata.contracts[0].ingestion_notes[0]
    assert note.startswith(
        "spec_url fetch failed: Failed to fetch OpenAPI spec from "
        "https://bank-internal.example.com/xyz/swagger.json:"
    )


def test_operation_pageable_flag_is_additive_manifest_metadata(tmp_path: Path) -> None:
    manifest_path = _write_sample_based_project(
        tmp_path,
        request_payload={"name": "Ada"},
        response_payload={"customerId": "C-1", "name": "Ada"},
        request_mappings=[("name", "Customer.name")],
        response_mappings=[
            ("customerId", "Customer.customerId"),
            ("name", "Customer.name"),
        ],
        pageable=True,
    )

    metadata = build_metadata_project(manifest_path)

    assert metadata.operations[0].pageable is True


def test_build_metadata_project_produces_expected_counts() -> None:
    metadata = build_metadata_project(
        "examples/input-projects/xyz-accounts-modernization/app-definition.yaml"
    )

    assert metadata.schema_version == "2.0"
    assert metadata.app_archetype.value == "crud"
    assert len(metadata.systems) == 3
    assert len(metadata.contracts) == 3
    assert len(metadata.operations) == 3
    assert len(metadata.entities) == 1
    assert len(metadata.mappings) == 13
    assert len(metadata.mapping_reports) == 3
    assert len(metadata.rules) == 3
    assert metadata.entities[0].name == "Account"
    assert [field.name for field in metadata.entities[0].fields] == [
        "customerId",
        "accountType",
        "currency",
        "accountId",
        "status",
        "createdDate",
    ]
    assert metadata.entities[0].fields[0].is_id is False
    assert metadata.entities[0].fields[3].required is True
    assert metadata.entities[0].fields[3].is_id is True
    assert metadata.entities[0].fields[5].type == CanonicalFieldType.DATE
    assert metadata.contracts[2].physical_name == "acct_staging_tbl"
    assert metadata.mapping_reports[0].status == "complete"
    assert metadata.mapping_reports[1].status == "complete"
    assert metadata.mapping_reports[2].status == "error"
    assert metadata.mapping_reports[2].issues[0].message == (
        "Contract target 'batch_flag' is required but not mapped."
    )


def test_unmapped_response_sample_fields_auto_included(tmp_path: Path) -> None:
    manifest_path = _write_sample_based_project(
        tmp_path / "response-auto-include",
        request_payload={"customerName": "Alice Merchant"},
        response_payload={
            "customerId": "C001",
            "customerName": "Alice Merchant",
            "address": "100 Main Street",
            "vip": True,
            "loginCount": 3,
            "creditLimit": 1250.75,
            "notes": None,
        },
        request_mappings=[
            ("customerName", "Customer.customerName"),
        ],
        response_mappings=[
            ("customerId", "Customer.customerId"),
            ("customerName", "Customer.customerName"),
        ],
    )

    metadata = build_metadata_project(manifest_path)

    entity = next(entity for entity in metadata.entities if entity.name == "Customer")
    fields = {field.name: field for field in entity.fields}

    assert fields["address"].type.value == "string"
    assert fields["vip"].type.value == "boolean"
    assert fields["loginCount"].type.value == "integer"
    assert fields["creditLimit"].type.value == "decimal"
    assert fields["notes"].type.value == "string"
    assert fields["address"].required is False
    assert fields["vip"].required is False
    assert fields["loginCount"].required is False
    assert fields["creditLimit"].required is False
    assert fields["notes"].required is False

    response_targets = {
        mapping.target_path
        for mapping in metadata.mappings
        if mapping.contract_name == "customer-api"
        and mapping.operation_name == "createCustomer"
        and ".response." in mapping.source_path
    }
    assert "Customer.address" in response_targets
    assert "Customer.vip" in response_targets
    assert "Customer.loginCount" in response_targets
    assert "Customer.creditLimit" in response_targets
    assert "Customer.notes" in response_targets

    warnings = [
        issue.message
        for report in metadata.mapping_reports
        if report.contract_name == "customer-api"
        for issue in report.issues
    ]
    assert (
        "Sample field 'address' in operation 'createCustomer' response "
        "auto-included in canonical model; add an explicit mapping to silence "
        "this warning."
    ) in warnings


def test_infer_canonical_type_detects_iso_dates_and_datetimes() -> None:
    assert _infer_canonical_type("2024-01-15") == CanonicalFieldType.DATE
    assert _infer_canonical_type("2024-01-15T10:30:00Z") == CanonicalFieldType.DATETIME
    assert _infer_canonical_type("2024-01-15T10:30:00.123+05:30") == CanonicalFieldType.DATETIME
    assert _infer_canonical_type("some-string") == CanonicalFieldType.STRING


def test_spec_url_field_hints_reuse_prefetched_openapi_spec(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "account-modernization"
    manifest_path = _write_sample_based_project(
        project_root,
        request_payload={"customerName": "Alice Merchant"},
        response_payload={
            "customerId": "C001",
            "customerName": "Alice Merchant",
            "createdDate": "2024-01-15",
        },
        request_mappings=[
            ("customerName", "Customer.customerName"),
        ],
        response_mappings=[
            ("customerId", "Customer.customerId"),
            ("customerName", "Customer.customerName"),
            ("createdDate", "Customer.createdDate"),
        ],
    )

    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/customers": {
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
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "customerId": {"type": "string"},
                                            "customerName": {"type": "string"},
                                            "createdDate": {"type": "string", "format": "date"},
                                        },
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
    }
    fetch_calls: list[str] = []

    def _fake_fetch(url: str) -> dict:
        fetch_calls.append(url)
        return spec

    monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", _fake_fetch)

    metadata = build_metadata_project(manifest_path)

    entity = next(entity for entity in metadata.entities if entity.name == "Customer")
    field_lookup = {field.name: field for field in entity.fields}

    assert fetch_calls == ["https://example.com/customer-api.json"]
    assert field_lookup["createdDate"].type == CanonicalFieldType.DATE
    assert field_lookup["createdDate"].format == "date"


def test_schema_field_hints_remains_raw_for_crud_sample_compatibility() -> None:
    hints = _schema_field_hints(
        {
            "type": "object",
            "required": ["direct", "referenced", "composed"],
            "properties": {
                "direct": {"type": "string", "format": "date", "maxLength": 12},
                "referenced": {"$ref": "#/components/schemas/Referenced"},
                "composed": {"allOf": [{"type": "string"}, {"maxLength": 8}]},
            },
        }
    )

    assert hints["direct"].type == CanonicalFieldType.DATE
    assert hints["direct"].format == "date"
    assert hints["direct"].max_length == 12
    assert hints["referenced"].type == CanonicalFieldType.STRING
    assert hints["referenced"].format is None
    assert hints["referenced"].max_length is None
    assert hints["composed"].type == CanonicalFieldType.STRING
    assert hints["composed"].format is None
    assert hints["composed"].max_length is None


def test_flatten_sample_field_names_recurses_nested_dicts_and_skips_lists() -> None:
    assert _flatten_sample_field_names({"status": "ACTIVE"}) == {"status"}
    assert _flatten_sample_field_names({"Data": {"ConsentId": "C-1"}}) == {
        "Data.ConsentId",
    }
    assert _flatten_sample_field_names(
        {
            "Data": {
                "Initiation": {
                    "InstructionIdentification": "WIRE-1",
                    "Creditor": {"Name": "ACME"},
                }
            }
        }
    ) == {
        "Data.Initiation.InstructionIdentification",
        "Data.Initiation.Creditor.Name",
    }
    assert _flatten_sample_field_names(
        {
            "Data": {"ConsentId": "C-1"},
            "Items": [{"status": "ACTIVE"}],
            "Results": [],
        }
    ) == {"Data.ConsentId"}


def test_auto_include_unmapped_response_sample_fields_skips_object_wrappers() -> None:
    report = MappingCompletenessReport(
        contract_name="customer-api",
        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
        status="warning",
    )
    mappings = []
    lookup = {}

    _auto_include_unmapped_response_sample_fields(
        interface_name="customer-api",
        operation_name="createCustomer",
        payload={
            "Data": {"id": "1"},
            "Links": {"self": "https://example.com/customers/1"},
            "Items": [{"status": "ACTIVE"}],
            "status": "ACTIVE",
        },
        lookup=lookup,
        mappings=mappings,
        report=report,
        entity_name="Customer",
        source_location="upstream/customer-mapping.yaml",
    )

    assert lookup == {
        ("createCustomer", "response", "Data.id"): "Customer.id",
        ("createCustomer", "response", "status"): "Customer.status",
    }
    assert len(mappings) == 2
    assert {mapping.source_path for mapping in mappings} == {
        "customer-api.createCustomer.response.Data.id",
        "customer-api.createCustomer.response.status",
    }
    assert {mapping.target_path for mapping in mappings} == {
        "Customer.id",
        "Customer.status",
    }
    assert len(report.issues) == 2
    assert any("status" in issue.message for issue in report.issues)
    assert any("Data.id" in issue.message for issue in report.issues)
    assert not any("Links" in issue.message for issue in report.issues)


def test_build_metadata_project_collects_explicit_dotted_nested_response_fields(tmp_path: Path) -> None:
    manifest_path = _write_sample_based_project(
        tmp_path / "nested-response-fields",
        request_payload={
            "Data": {
                "ConsentId": "CONSENT-123",
            }
        },
        response_payload={
            "Data": {
                "customerId": "C001",
                "customerName": "Alice Merchant",
                "ExpectedExecutionDateTime": "2026-04-05T10:15:30+00:00",
                "ExpectedSettlementDateTime": "2026-04-05T10:16:00+00:00",
            },
            "Links": {"self": "https://example.com/customers/C001"},
            "Meta": {"totalPages": 1},
        },
        request_mappings=[
            ("Data.ConsentId", "Customer.consentId"),
        ],
        response_mappings=[
            ("Data.customerId", "Customer.customerId"),
            ("Data.customerName", "Customer.customerName"),
            ("Data.ExpectedExecutionDateTime", "Customer.ExpectedExecutionDateTime"),
            ("Data.ExpectedSettlementDateTime", "Customer.ExpectedSettlementDateTime"),
        ],
    )

    metadata = build_metadata_project(manifest_path)

    entity = next(entity for entity in metadata.entities if entity.name == "Customer")
    field_names = {field.name for field in entity.fields}

    assert "ExpectedExecutionDateTime" in field_names
    assert "ExpectedSettlementDateTime" in field_names


def test_generated_app_quality_minor_units_date_fixture_propagates_date_and_mapping_metadata() -> None:
    metadata = build_metadata_project(
        "tests/fixtures/generated-app-quality/crud-minor-units-date/app-definition.yaml"
    )

    entity = next(entity for entity in metadata.entities if entity.name == "Account")
    field_lookup = {field.name: field for field in entity.fields}

    assert field_lookup["openedDate"].type == CanonicalFieldType.DATE
    assert field_lookup["openedDate"].format == "date"
    assert field_lookup["availableBalance"].type == CanonicalFieldType.DECIMAL

    downstream_mappings = {
        mapping.target_path.rsplit(".", 1)[-1]: mapping
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
    }
    assert (
        downstream_mappings["available_balance_minor"].type_coercion
        == "major_to_minor_units"
    )
    assert downstream_mappings["available_balance"].type_coercion is None


def test_staging_date_can_promote_date_named_string_field(tmp_path: Path) -> None:
    project_root = tmp_path / "date-staging-modernization"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "data-handoffs").mkdir(parents=True)
    (project_root / "upstream" / "create-account-response.json").write_text(
        json.dumps({"accountId": "acct-1", "openedDate": "not-a-sample-date"}),
        encoding="utf-8",
    )
    (project_root / "upstream" / "account-mapping.yaml").write_text(
        "\n".join(
            [
                "entity: Account",
                "operations:",
                "  - name: createAccount",
                "    request_mappings: []",
                "    response_mappings:",
                "      - source: accountId",
                "        target: Account.accountId",
                "      - source: openedDate",
                "        target: Account.openedDate",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "data-handoffs" / "account-staging-table.sql").write_text(
        "\n".join(
            [
                "CREATE TABLE account_staging_tbl (",
                "    account_id VARCHAR(36),",
                "    opened_date DATE",
                ");",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "data-handoffs" / "account-staging-mapping.yaml").write_text(
        "\n".join(
            [
                "entity: Account",
                "field_mappings:",
                "  - source: Account.accountId",
                "    target: account_id",
                "  - source: Account.openedDate",
                "    target: opened_date",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Date Staging Modernization",
                "bounded_context: datestaging",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: account-api",
                "    system: CORE",
                "    type: rest-json",
                "    spec_url: https://example.com/account-api.json",
                "    mapping: upstream/account-mapping.yaml",
                "    operations:",
                "      - name: createAccount",
                "        response_sample: upstream/create-account-response.json",
                "data_handoffs:",
                "  - name: account-staging-table",
                "    system: ETL",
                "    type: staging-table",
                "    spec: data-handoffs/account-staging-table.sql",
                "    mapping: data-handoffs/account-staging-mapping.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    metadata = build_metadata_project(project_root / "app-definition.yaml")

    entity = next(entity for entity in metadata.entities if entity.name == "Account")
    field_lookup = {field.name: field for field in entity.fields}
    assert field_lookup["openedDate"].type == CanonicalFieldType.DATE
    assert field_lookup["openedDate"].format == "date"


def test_unmapped_request_sample_fields_not_auto_included(tmp_path: Path) -> None:
    manifest_path = _write_sample_based_project(
        tmp_path / "request-not-auto-include",
        request_payload={
            "customerName": "Alice Merchant",
            "email": "alice.merchant@example.com",
            "marketingOptIn": True,
        },
        response_payload={
            "customerId": "C001",
            "customerName": "Alice Merchant",
        },
        request_mappings=[
            ("customerName", "Customer.customerName"),
        ],
        response_mappings=[
            ("customerId", "Customer.customerId"),
            ("customerName", "Customer.customerName"),
        ],
    )

    metadata = build_metadata_project(manifest_path)

    entity = next(entity for entity in metadata.entities if entity.name == "Customer")
    field_names = {field.name for field in entity.fields}

    assert "email" not in field_names
    assert "marketingOptIn" not in field_names


def test_dda_createcustomer_response_includes_address_country_email(tmp_path: Path) -> None:
    manifest_path = _write_sample_based_project(
        tmp_path / "dda-like-customer",
        request_payload={
            "customerName": "Alice Merchant",
            "kycStatus": "PENDING",
        },
        response_payload={
            "customerId": "C001",
            "customerName": "Alice Merchant",
            "address": "100 Main Street, London",
            "country": "GB",
            "email": "alice.merchant@example.com",
            "kycStatus": "PENDING",
            "creationDate": "2026-03-25T10:15:30Z",
        },
        request_mappings=[
            ("customerName", "Customer.customerName"),
            ("kycStatus", "Customer.kycStatus"),
        ],
        response_mappings=[
            ("customerId", "Customer.customerId"),
            ("customerName", "Customer.customerName"),
            ("kycStatus", "Customer.kycStatus"),
            ("creationDate", "Customer.creationDate"),
        ],
    )

    metadata = build_metadata_project(manifest_path)

    entity = next(entity for entity in metadata.entities if entity.name == "Customer")
    field_names = [field.name for field in entity.fields]

    assert "address" in field_names
    assert "country" in field_names
    assert "email" in field_names


def test_build_metadata_project_keeps_upstream_type_and_required_flag_on_handoff_conflict(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "loan-modernization"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "data-handoffs").mkdir(parents=True)

    (project_root / "upstream" / "create-loan-request.json").write_text(
        '{"loanId": "L-100"}\n',
        encoding="utf-8",
    )
    (project_root / "upstream" / "loan-mapping.yaml").write_text(
        "\n".join(
            [
                "entity: Loan",
                "operations:",
                "  - name: createLoan",
                "    request_mappings:",
                "      - source: loanId",
                "        target: Loan.loanId",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "data-handoffs" / "loan-staging-table.sql").write_text(
        "\n".join(
            [
                "CREATE TABLE loan_staging_tbl (",
                "    loan_id INTEGER",
                ");",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "data-handoffs" / "loan-staging-mapping.yaml").write_text(
        "\n".join(
            [
                "table: loan_staging_tbl",
                "entity: Loan",
                "field_mappings:",
                "  - source: Loan.loanId",
                "    target: loan_id",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Loan Modernization",
                "bounded_context: loans",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-loan-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec_url: https://example.com/swagger.json",
                "    mapping: upstream/loan-mapping.yaml",
                "    operations:",
                "      - name: createLoan",
                "        request_sample: upstream/create-loan-request.json",
                "data_handoffs:",
                "  - name: loan-staging-table",
                "    system: ETL",
                "    type: staging-table",
                "    spec: data-handoffs/loan-staging-table.sql",
                "    mapping: data-handoffs/loan-staging-mapping.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    metadata = build_metadata_project(project_root / "app-definition.yaml")

    assert metadata.entities[0].fields[0].name == "loanId"
    assert metadata.entities[0].fields[0].type.value == "string"
    assert metadata.entities[0].fields[0].required is True
    assert metadata.mapping_reports[1].status == "error"
    assert metadata.mapping_reports[1].issues[0].message == (
        "Type conflict for field 'loanId': upstream declares 'string' but staging table "
        "'loan-staging-table' declares 'integer'."
    )


def test_staging_table_length_does_not_constrain_identifier_field_max_length() -> None:
    metadata = build_metadata_project(
        "examples/input-projects/xyz-accounts-modernization/app-definition.yaml"
    )

    field_lookup = {field.name: field for field in metadata.entities[0].fields}

    assert field_lookup["customerId"].max_length is None
    assert field_lookup["accountId"].max_length is None
    warnings = [
        issue.message
        for report in metadata.mapping_reports
        for issue in report.issues
        if issue.severity.value == "warning"
    ]
    assert any("cust_ref" in message and "VARCHAR(20)" in message for message in warnings)
    assert any("acct_id" in message and "VARCHAR(20)" in message for message in warnings)


def test_response_only_entity_id_can_differ_from_foreign_key(tmp_path: Path) -> None:
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

    metadata = build_metadata_project(project_root / "app-definition.yaml")

    entity = metadata.entities[0]
    field_lookup = {field.name: field for field in entity.fields}

    assert field_lookup["scheduleId"].is_id is True
    assert field_lookup["scheduleId"].server_generated_id is True
    assert field_lookup["loanId"].is_id is False


def test_ambiguous_id_inference_emits_warning(tmp_path: Path) -> None:
    project_root = tmp_path / "ambiguous-id-modernization"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "contracts").mkdir(parents=True)
    (project_root / "contracts" / "alpha-api-spec.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (project_root / "upstream" / "create-alpha-response.json").write_text(
        json.dumps(
            {
                "alphaId": "alpha-1",
                "betaId": "beta-1",
                "name": "test",
            }
        ),
        encoding="utf-8",
    )
    (project_root / "upstream" / "alpha-mapping.yaml").write_text(
        "\n".join(
            [
                "entity: Record",
                "operations:",
                "  - name: createRecord",
                "    response_mappings:",
                "      - source: alphaId",
                "        target: Record.alphaId",
                "      - source: betaId",
                "        target: Record.betaId",
                "      - source: name",
                "        target: Record.name",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Ambiguous ID Modernization",
                "bounded_context: records",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: alpha-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec: contracts/alpha-api-spec.json",
                "    mapping: upstream/alpha-mapping.yaml",
                "    operations:",
                "      - name: createRecord",
                "        response_sample: upstream/create-alpha-response.json",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    metadata = build_metadata_project(project_root / "app-definition.yaml")

    assert any(
        "Ambiguous id-field inference" in warning
        and "'alphaId'" in warning
        and "'betaId'" in warning
        for warning in metadata.warnings
    )


def test_identity_override_wins_on_multi_identifier_entity(tmp_path: Path) -> None:
    manifest_path = _write_identity_project(
        tmp_path / "transaction-posting-override",
        entity_name="TransactionRecord",
        response_payload={
            "accountId": "account-1",
            "transactionId": "txn-1",
            "postingId": "posting-1",
            "amount": 100,
        },
        response_mappings=[
            ("accountId", "TransactionRecord.accountId"),
            ("transactionId", "TransactionRecord.transactionId"),
            ("postingId", "TransactionRecord.postingId"),
            ("amount", "TransactionRecord.amount"),
        ],
        identity_overrides=[("TransactionRecord", "postingId")],
    )

    metadata = build_metadata_project(manifest_path)

    entity = next(entity for entity in metadata.entities if entity.name == "TransactionRecord")
    field_lookup = {field.name: field for field in entity.fields}
    assert field_lookup["postingId"].is_id is True
    assert field_lookup["accountId"].is_id is False
    assert field_lookup["transactionId"].is_id is False
    assert not any("Ambiguous id-field inference" in warning for warning in metadata.warnings)


def test_absent_identity_override_keeps_existing_heuristic_behavior(tmp_path: Path) -> None:
    manifest_path = _write_identity_project(
        tmp_path / "payment-record-heuristic",
        entity_name="PaymentRecord",
        response_payload={
            "accountId": "account-1",
            "transactionId": "txn-1",
            "postingId": "posting-1",
            "amount": 100,
        },
        response_mappings=[
            ("accountId", "PaymentRecord.accountId"),
            ("transactionId", "PaymentRecord.transactionId"),
            ("postingId", "PaymentRecord.postingId"),
            ("amount", "PaymentRecord.amount"),
        ],
    )

    metadata = build_metadata_project(manifest_path)

    entity = next(entity for entity in metadata.entities if entity.name == "PaymentRecord")
    field_lookup = {field.name: field for field in entity.fields}
    assert field_lookup["accountId"].is_id is True
    assert field_lookup["transactionId"].is_id is False
    assert field_lookup["postingId"].is_id is False
    assert any("Ambiguous id-field inference" in warning for warning in metadata.warnings)


def test_event_identity_inference_rejects_parent_reference_id(tmp_path: Path) -> None:
    manifest_path = _write_identity_project(
        tmp_path / "transaction-history-unsafe-parent-id",
        entity_name="TransactionHistory",
        response_payload={
            "accountId": "account-1",
            "transactionId": "txn-1",
            "postingId": "posting-1",
            "amount": 100,
        },
        response_mappings=[
            ("accountId", "TransactionHistory.accountId"),
            ("transactionId", "TransactionHistory.transactionId"),
            ("postingId", "TransactionHistory.postingId"),
            ("amount", "TransactionHistory.amount"),
        ],
    )

    with pytest.raises(
        ValueError,
        match=(
            "TransactionHistory.*accountId.*parent/reference field.*"
            "identity_overrides.*transactionRowId"
        ),
    ):
        build_metadata_project(manifest_path)


def test_event_identity_rejects_parent_token_even_when_entity_name_contains_it(
    tmp_path: Path,
) -> None:
    manifest_path = _write_identity_project(
        tmp_path / "customer-transaction-unsafe-parent-id",
        entity_name="CustomerTransaction",
        response_payload={
            "customerId": "customer-1",
            "amount": 100,
        },
        response_mappings=[
            ("customerId", "CustomerTransaction.customerId"),
            ("amount", "CustomerTransaction.amount"),
        ],
    )

    with pytest.raises(ValueError, match="CustomerTransaction.*customerId"):
        build_metadata_project(manifest_path)


def test_generated_app_quality_fixture_preserves_transaction_row_identity() -> None:
    metadata = build_metadata_project(
        "tests/fixtures/generated-app-quality/transaction-identity-wrapper-valid/app-definition.yaml"
    )

    entity = next(entity for entity in metadata.entities if entity.name == "TransactionHistory")
    field_lookup = {field.name: field for field in entity.fields}

    assert field_lookup["transactionRowId"].is_id is True
    assert field_lookup["accountId"].is_id is False
    assert field_lookup["transactionId"].is_id is False


def test_generated_app_quality_invalid_fixture_rejects_parent_id_identity() -> None:
    with pytest.raises(ValueError, match="TransactionHistory.*accountId.*identity_overrides"):
        build_metadata_project(
            "tests/fixtures/generated-app-quality/transaction-identity-wrapper-invalid/app-definition.yaml"
        )


def test_response_wrapper_fields_are_removed_from_persistence_and_output_mappings() -> None:
    metadata = build_metadata_project(
        "tests/fixtures/generated-app-quality/transaction-identity-wrapper-valid/app-definition.yaml"
    )

    entity = next(entity for entity in metadata.entities if entity.name == "TransactionHistory")
    field_names = {field.name for field in entity.fields}

    assert "transactions" not in field_names
    assert "currentPage" not in field_names
    assert "pageSize" not in field_names
    assert "totalElements" not in field_names
    assert "totalPages" not in field_names

    output_sources = {
        mapping.source_path
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
    }
    assert "TransactionHistory.currentPage" not in output_sources
    assert "TransactionHistory.totalElements" not in output_sources
    assert "TransactionHistory.accountId" in output_sources
    assert "TransactionHistory.transactionId" in output_sources

    # Upstream response mappings remain available as transport/API context; the
    # wrapper filter is scoped to persistence and output surfaces.
    upstream_response_sources = {
        mapping.source_path
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
        and ".response." in mapping.source_path
    }
    assert "transaction-api.listTransactionsByAccount.response.currentPage" in upstream_response_sources


def test_identity_override_missing_field_fails_with_clear_error(tmp_path: Path) -> None:
    manifest_path = _write_identity_project(
        tmp_path / "transaction-posting-missing-override",
        entity_name="TransactionPosting",
        response_payload={
            "accountId": "account-1",
            "transactionId": "txn-1",
        },
        response_mappings=[
            ("accountId", "TransactionPosting.accountId"),
            ("transactionId", "TransactionPosting.transactionId"),
        ],
        identity_overrides=[("TransactionPosting", "nonExistentField")],
    )

    with pytest.raises(ValueError, match="TransactionPosting.*nonExistentField"):
        build_metadata_project(manifest_path)


def test_duplicate_identity_override_entity_rejected_at_manifest_load(tmp_path: Path) -> None:
    manifest_path = tmp_path / "app-definition.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "app_name: Duplicate Identity Overrides",
                "bounded_context: customers",
                "schema_version: \"2.0\"",
                "identity_overrides:",
                "  - entity: Customer",
                "    persistence_id: customerId",
                "  - entity: Customer",
                "    persistence_id: id",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="identity_overrides.*Customer.*more than once"):
        load_project_definition(manifest_path)


def test_identity_override_bypasses_ambiguous_inference_warning(tmp_path: Path) -> None:
    manifest_path = _write_identity_project(
        tmp_path / "ambiguous-id-override",
        entity_name="Record",
        response_payload={
            "alphaId": "alpha-1",
            "betaId": "beta-1",
            "name": "test",
        },
        response_mappings=[
            ("alphaId", "Record.alphaId"),
            ("betaId", "Record.betaId"),
            ("name", "Record.name"),
        ],
        identity_overrides=[("Record", "betaId")],
    )

    metadata = build_metadata_project(manifest_path)

    entity = next(entity for entity in metadata.entities if entity.name == "Record")
    field_lookup = {field.name: field for field in entity.fields}
    assert field_lookup["betaId"].is_id is True
    assert field_lookup["alphaId"].is_id is False
    assert not any("Ambiguous id-field inference" in warning for warning in metadata.warnings)


def test_identity_overrides_do_not_affect_passthrough_router(tmp_path: Path) -> None:
    source_project = Path("examples/input-projects/country-router")
    passthrough_project = tmp_path / "country-router"
    shutil.copytree(
        source_project,
        passthrough_project,
        ignore=shutil.ignore_patterns(".DS_Store", "* copy.yaml"),
    )
    manifest_path = passthrough_project / "app-definition.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            "app_archetype: passthrough-router\n",
            "\n".join(
                [
                    "app_archetype: passthrough-router",
                    "identity_overrides:",
                    "  - entity: Payment",
                    "    persistence_id: paymentId",
                    "",
                ]
            ),
        ),
        encoding="utf-8",
    )

    baseline = build_metadata_project(source_project / "app-definition.yaml")
    metadata = build_metadata_project(manifest_path)

    assert metadata.app_archetype == baseline.app_archetype
    assert metadata.entities == baseline.entities == []
    assert [operation.name for operation in metadata.operations] == [
        operation.name for operation in baseline.operations
    ]
    assert metadata.routing_rules == baseline.routing_rules


def test_identity_override_supplies_id_for_no_candidate_entity(tmp_path: Path) -> None:
    manifest_path = _write_identity_project(
        tmp_path / "reference-record-override",
        entity_name="ReferenceRecord",
        response_payload={
            "reference": "ref-1",
            "amount": 100,
            "status": "POSTED",
        },
        response_mappings=[
            ("reference", "ReferenceRecord.reference"),
            ("amount", "ReferenceRecord.amount"),
            ("status", "ReferenceRecord.status"),
        ],
        identity_overrides=[("ReferenceRecord", "reference")],
    )

    metadata = build_metadata_project(manifest_path)

    entity = next(entity for entity in metadata.entities if entity.name == "ReferenceRecord")
    field_lookup = {field.name: field for field in entity.fields}
    assert field_lookup["reference"].is_id is True
    assert field_lookup["amount"].is_id is False
    assert field_lookup["status"].is_id is False


def test_c9_db_identity_sets_strategy_on_id_field(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-db-identity",
        field_type="integer",
        id_field_name="loanId",
        id_generation_overrides=[
            {"entity": "Loan", "field": "loanId", "strategy": "db_identity"}
        ],
    )

    metadata = build_metadata_project(manifest_path)

    loan = next(entity for entity in metadata.entities if entity.name == "Loan")
    id_field = next(field for field in loan.fields if field.is_id)
    assert id_field.name == "loanId"
    assert id_field.id_generation_strategy == IdGenerationStrategy.DB_IDENTITY


def test_c9_db_sequence_sets_strategy_and_sequence_name(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-db-sequence",
        field_type="integer",
        id_field_name="loanId",
        id_generation_overrides=[
            {
                "entity": "Loan",
                "field": "loanId",
                "strategy": "db_sequence",
                "sequence_name": "loan_id_seq",
            }
        ],
    )

    metadata = build_metadata_project(manifest_path)

    loan = next(entity for entity in metadata.entities if entity.name == "Loan")
    id_field = next(field for field in loan.fields if field.is_id)
    assert id_field.id_generation_strategy == IdGenerationStrategy.DB_SEQUENCE
    assert id_field.id_sequence_name == "loan_id_seq"


def test_c9_uuid_preserves_existing_uuid_strategy(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-uuid",
        field_type="string",
        id_field_name="loanId",
        id_generation_overrides=[{"entity": "Loan", "field": "loanId", "strategy": "uuid"}],
    )

    metadata = build_metadata_project(manifest_path)

    loan = next(entity for entity in metadata.entities if entity.name == "Loan")
    id_field = next(field for field in loan.fields if field.is_id)
    assert id_field.id_generation_strategy == IdGenerationStrategy.UUID
    assert id_field.server_generated_id is True


def test_c9_caller_supplied_sets_strategy(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-caller-supplied",
        field_type="string",
        id_field_name="loanId",
        id_generation_overrides=[
            {"entity": "Loan", "field": "loanId", "strategy": "caller_supplied"}
        ],
        server_generated_id=False,
    )

    metadata = build_metadata_project(manifest_path)

    loan = next(entity for entity in metadata.entities if entity.name == "Loan")
    id_field = next(field for field in loan.fields if field.is_id)
    assert id_field.id_generation_strategy == IdGenerationStrategy.CALLER_SUPPLIED
    assert id_field.server_generated_id is False


def test_c9_uuid_rejects_non_string_id(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-uuid-invalid",
        field_type="integer",
        id_field_name="loanId",
        id_generation_overrides=[{"entity": "Loan", "field": "loanId", "strategy": "uuid"}],
    )

    with pytest.raises(ValueError, match="uuid.*string"):
        build_metadata_project(manifest_path)


def test_c9_db_identity_rejects_string_id(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-identity-invalid",
        field_type="string",
        id_field_name="loanId",
        id_generation_overrides=[
            {"entity": "Loan", "field": "loanId", "strategy": "db_identity"}
        ],
    )

    with pytest.raises(ValueError, match="db_identity.*numeric"):
        build_metadata_project(manifest_path)


def test_c9_field_guard_mismatch_fails(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-field-guard-invalid",
        field_type="integer",
        id_field_name="loanId",
        id_generation_overrides=[
            {"entity": "Loan", "field": "wrongField", "strategy": "db_identity"}
        ],
        identity_overrides=[{"entity": "Loan", "persistence_id": "loanId"}],
    )

    with pytest.raises(ValueError, match="wrongField.*loanId"):
        build_metadata_project(manifest_path)


def test_c9_duplicate_entity_rejected_at_manifest_load(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-generation-duplicate",
        field_type="integer",
        id_field_name="loanId",
        id_generation_overrides=[
            {"entity": "Loan", "field": "loanId", "strategy": "db_identity"},
            {"entity": "Loan", "field": "loanId", "strategy": "caller_supplied"},
        ],
    )

    with pytest.raises(ValueError, match="id_generation_overrides.*more than once"):
        load_project_definition(manifest_path)


def test_c9_db_sequence_requires_sequence_name(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-sequence-missing",
        field_type="integer",
        id_field_name="loanId",
        id_generation_overrides=[
            {"entity": "Loan", "field": "loanId", "strategy": "db_sequence"}
        ],
    )

    with pytest.raises(ValueError, match="sequence_name"):
        load_project_definition(manifest_path)


def test_c9_passthrough_router_unaffected(tmp_path: Path) -> None:
    source_project = Path("examples/input-projects/country-router")
    passthrough_project = tmp_path / "country-router"
    shutil.copytree(
        source_project,
        passthrough_project,
        ignore=shutil.ignore_patterns(".DS_Store", "* copy.yaml"),
    )
    manifest_path = passthrough_project / "app-definition.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            "app_archetype: passthrough-router\n",
            "\n".join(
                [
                    "app_archetype: passthrough-router",
                    "id_generation_overrides:",
                    "  - entity: MissingEntity",
                    "    field: missingId",
                    "    strategy: db_identity",
                    "",
                ]
            ),
        ),
        encoding="utf-8",
    )

    baseline = build_metadata_project(source_project / "app-definition.yaml")
    metadata = build_metadata_project(manifest_path)

    assert metadata.app_archetype == baseline.app_archetype
    assert metadata.entities == baseline.entities == []
    assert [operation.name for operation in metadata.operations] == [
        operation.name for operation in baseline.operations
    ]
    assert metadata.routing_rules == baseline.routing_rules


def test_c9_no_override_preserves_existing_behavior(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-no-generation-override",
        field_type="string",
        id_field_name="loanId",
    )

    metadata = build_metadata_project(manifest_path)

    loan = next(entity for entity in metadata.entities if entity.name == "Loan")
    id_field = next(field for field in loan.fields if field.is_id)
    assert id_field.id_generation_strategy is None
    assert id_field.server_generated_id is True


def test_c9_db_identity_with_caller_supplied_id_fails(tmp_path: Path) -> None:
    manifest_path = _write_id_generation_project(
        tmp_path / "loan-identity-caller-conflict",
        field_type="integer",
        id_field_name="loanId",
        id_generation_overrides=[
            {"entity": "Loan", "field": "loanId", "strategy": "db_identity"}
        ],
        server_generated_id=False,
    )

    with pytest.raises(ValueError, match="database-generated.*caller-supplied"):
        build_metadata_project(manifest_path)


def test_build_metadata_project_ingests_openapi_entities_from_spec_url(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "customer-modernization"
    project_root.mkdir(parents=True)
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Customer Modernization",
                "bounded_context: customer",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: customer-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec_url: http://localhost:8080/v3/api-docs",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    spec = {
        "openapi": "3.0.0",
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "required": ["customerId", "name"],
                    "properties": {
                        "customerId": {"type": "string"},
                        "name": {"type": "string", "maxLength": 50},
                        "createdAt": {"type": "string", "format": "date-time"},
                    },
                }
            }
        },
        "paths": {
            "/customers/{customerId}": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Customer"}
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", lambda url: spec)

    metadata = build_metadata_project(project_root / "app-definition.yaml")

    assert metadata.contracts[0].ingestion_notes == [
        "OpenAPI spec ingested from http://localhost:8080/v3/api-docs: 1 domain entity classified."
    ]
    assert len(metadata.entities) == 1
    assert metadata.entities[0].name == "Customer"
    field_lookup = {field.name: field for field in metadata.entities[0].fields}
    assert field_lookup["customerId"].is_id is True
    assert field_lookup["createdAt"].type.value == "datetime"


def test_openapi_entity_scoped_terminal_path_param_can_select_generic_id_field(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "codat-customer-modernization"
    project_root.mkdir(parents=True)
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Codat Customer Modernization",
                "bounded_context: customer",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: codat-customer-api",
                "    system: CODAT",
                "    type: rest-json",
                "    spec_url: http://localhost:8080/codat/openapi.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
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

    customer = next(entity for entity in metadata.entities if entity.name == "Customer")
    field_lookup = {field.name: field for field in customer.fields}

    assert field_lookup["id"].is_id is True
    assert field_lookup["companyId"].is_id is False
    assert not any("Ambiguous id-field inference" in warning for warning in metadata.warnings)


def test_openapi_entity_enriched_with_rules_when_spec_url_used(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """B2: Rule enrichment (allowed_values, default_value) must be merged into OpenAPI entities.

    When a project uses spec_url so that OpenAPI classification runs, the resulting
    entity comes from openapi_entities.  Any rules declared in a rules file (e.g. an
    ALLOWED_VALUES rule for kycStatus) go through field_accumulators -> built_entities.
    Previously the built_entity was silently discarded because the entity name was
    already present in openapi_entities.  The fix merges the enrichment instead.
    """
    project_root = tmp_path / "kyc-modernization"
    project_root.mkdir(parents=True)
    (project_root / "rules").mkdir(parents=True)

    # Rules file: kycStatus allowed values + default
    (project_root / "rules" / "customer-rules.yaml").write_text(
        "\n".join(
            [
                "entity: Customer",
                "rules:",
                "  - field: kycStatus",
                "    type: allowed-values",
                "    values: [PENDING, VERIFIED, REJECTED]",
                "  - field: kycStatus",
                "    type: default",
                "    value: PENDING",
            ]
        ),
        encoding="utf-8",
    )

    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: KYC Modernization",
                "bounded_context: customer",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: customer-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec_url: http://localhost:8080/v3/api-docs",
                "rules:",
                "  - rules/customer-rules.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    # OpenAPI spec that classifies a Customer entity with a kycStatus field.
    # A path whose response $ref's Customer is needed for the classifier to label
    # it as an entity (and populate openapi_entities), which triggers the merge path.
    spec = {
        "openapi": "3.0.0",
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "required": ["customerId"],
                    "properties": {
                        "customerId": {"type": "string"},
                        "kycStatus": {"type": "string"},
                    },
                }
            }
        },
        "paths": {
            "/customers/{customerId}": {
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
            }
        },
    }

    monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", lambda url: spec)

    metadata = build_metadata_project(project_root / "app-definition.yaml")

    assert len(metadata.entities) == 1
    assert metadata.entities[0].name == "Customer"
    field_lookup = {f.name: f for f in metadata.entities[0].fields}

    # kycStatus must be present (it came from the OpenAPI spec)
    assert "kycStatus" in field_lookup, "kycStatus field missing from Customer entity"
    kyc = field_lookup["kycStatus"]

    # The rule-driven allowed_values must have been merged in
    assert set(kyc.allowed_values) == {"PENDING", "VERIFIED", "REJECTED"}, (
        f"Expected allowed_values to be merged from rules; got {kyc.allowed_values}"
    )

    # The rule-driven default must have been merged in
    assert kyc.default_value == "PENDING", (
        f"Expected default_value 'PENDING' from rules; got {kyc.default_value!r}"
    )


def test_openapi_entity_enriched_with_downstream_constraints_when_spec_url_used(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """B2 (extended): max_length, required, and format from downstream interfaces/handoffs
    must also be merged into OpenAPI-backed entities — not just rule-driven enrichment.

    Codex reproduced this with a downstream fixed-width layout where Customer.status
    carried length=1 and required=true.  After translate_project the OpenAPI-backed
    field still came out with required=False and max_length=None.
    """
    project_root = tmp_path / "status-modernization"
    project_root.mkdir(parents=True)
    (project_root / "layouts").mkdir(parents=True)
    (project_root / "mappings").mkdir(parents=True)

    # Downstream fixed-width layout: status column, length 1, required
    (project_root / "layouts" / "customer-eod.yaml").write_text(
        "\n".join(
            [
                "name: customer-eod",
                "fields:",
                "  - name: status",
                "    length: 1",
                "    required: true",
            ]
        ),
        encoding="utf-8",
    )

    # Mapping: downstream status <- Customer.status (canonical path)
    (project_root / "mappings" / "customer-eod-mapping.yaml").write_text(
        "\n".join(
            [
                "entity: Customer",
                "field_mappings:",
                "  - source: Customer.status",
                "    target: status",
            ]
        ),
        encoding="utf-8",
    )

    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Status Modernization",
                "bounded_context: customer",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: customer-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec_url: http://localhost:8080/v3/api-docs",
                "downstream_interfaces:",
                "  - name: customer-eod",
                "    type: fixed-width",
                "    spec: layouts/customer-eod.yaml",
                "    mapping: mappings/customer-eod-mapping.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    # OpenAPI spec: Customer entity with a status field (no constraints declared).
    # The response $ref is required so the classifier labels Customer as an entity
    # and populates openapi_entities, triggering the merge code path.
    spec = {
        "openapi": "3.0.0",
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "required": ["customerId"],
                    "properties": {
                        "customerId": {"type": "string"},
                        "status": {"type": "string"},
                    },
                }
            }
        },
        "paths": {
            "/customers/{customerId}": {
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
            }
        },
    }

    monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", lambda url: spec)

    metadata = build_metadata_project(project_root / "app-definition.yaml")

    assert len(metadata.entities) == 1
    assert metadata.entities[0].name == "Customer"
    field_lookup = {f.name: f for f in metadata.entities[0].fields}

    assert "status" in field_lookup, "status field missing from Customer entity"
    status = field_lookup["status"]

    # downstream fixed-width layout "length" is a file-format presentation
    # constraint only. It must NOT set canonical max_length (which drives DB column width
    # and UI maxlength). So max_length should remain None after translation.
    assert status.max_length is None, (
        f"Expected max_length=None after Fix 1 (layout length must not set canonical max_length); got {status.max_length!r}"
    )

    # Downstream layout marks status as required (no default) — must be promoted
    assert status.required is True, (
        f"Expected required=True from downstream layout; got {status.required!r}"
    )


def test_openapi_entity_required_not_promoted_when_default_present(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """B2 (guard): required must NOT be promoted to True when a default_value is present.

    If an accumulator field is required=True by the downstream but a rule supplies a
    default, the default wins: the field should remain required=False in the final entity.
    """
    project_root = tmp_path / "default-guard"
    project_root.mkdir(parents=True)
    (project_root / "layouts").mkdir(parents=True)
    (project_root / "mappings").mkdir(parents=True)
    (project_root / "rules").mkdir(parents=True)

    # Downstream layout: status required, length 1
    (project_root / "layouts" / "customer-eod.yaml").write_text(
        "\n".join(
            [
                "name: customer-eod",
                "fields:",
                "  - name: status",
                "    length: 1",
                "    required: true",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "mappings" / "customer-eod-mapping.yaml").write_text(
        "\n".join(
            [
                "entity: Customer",
                "field_mappings:",
                "  - source: Customer.status",
                "    target: status",
            ]
        ),
        encoding="utf-8",
    )

    # Rule: status has a default of "A" — this should suppress required=True
    (project_root / "rules" / "customer-rules.yaml").write_text(
        "\n".join(
            [
                "entity: Customer",
                "rules:",
                "  - field: status",
                "    type: default",
                "    value: A",
            ]
        ),
        encoding="utf-8",
    )

    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Default Guard",
                "bounded_context: customer",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: customer-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec_url: http://localhost:8080/v3/api-docs",
                "downstream_interfaces:",
                "  - name: customer-eod",
                "    type: fixed-width",
                "    spec: layouts/customer-eod.yaml",
                "    mapping: mappings/customer-eod-mapping.yaml",
                "rules:",
                "  - rules/customer-rules.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    spec = {
        "openapi": "3.0.0",
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "required": ["customerId"],
                    "properties": {
                        "customerId": {"type": "string"},
                        "status": {"type": "string"},
                    },
                }
            }
        },
        "paths": {
            "/customers/{customerId}": {
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
            }
        },
    }

    monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", lambda url: spec)

    metadata = build_metadata_project(project_root / "app-definition.yaml")

    field_lookup = {f.name: f for f in metadata.entities[0].fields}
    status = field_lookup["status"]

    # Default value must be present
    assert status.default_value == "A", (
        f"Expected default_value='A'; got {status.default_value!r}"
    )
    # required must remain False — the default softens the downstream required constraint
    assert status.required is False, (
        f"Expected required=False when default is present; got {status.required!r}"
    )


def test_build_metadata_project_applies_phase_a_rule_constraints_to_canonical_fields(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "constraint-modernization"
    (project_root / "upstream").mkdir(parents=True)
    (project_root / "rules").mkdir(parents=True)

    (project_root / "upstream" / "create-account-request.json").write_text(
        json.dumps(
            {
                "accountNumber": "1234567890",
                "balance": 100.0,
                "customerId": "CUST-100",
            }
        ),
        encoding="utf-8",
    )
    (project_root / "upstream" / "account-mapping.yaml").write_text(
        "\n".join(
            [
                "interface: account-api",
                "entity: Account",
                "operations:",
                "  - name: createAccount",
                "    request_mappings:",
                "      - source: accountNumber",
                "        target: Account.accountNumber",
                "      - source: balance",
                "        target: Account.balance",
                "      - source: customerId",
                "        target: Account.customerId",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "rules" / "account-rules.yaml").write_text(
        "\n".join(
            [
                "entity: Account",
                "rules:",
                "  - field: accountNumber",
                "    type: max-length",
                '    value: "10"',
                "  - field: accountNumber",
                "    type: min-length",
                '    value: "10"',
                "  - field: accountNumber",
                "    type: pattern",
                '    value: "^[0-9]{10}$"',
                "  - field: balance",
                "    type: range",
                '    min: "0.01"',
                '    max: "999999.99"',
                "  - field: customerId",
                "    type: not-null",
                "  - field: status",
                "    type: default",
                "    value: ACTIVE",
                "  - field: status",
                "    type: not-null",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Constraint Modernization",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: account-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec_url: https://example.com/account-api.json",
                "    mapping: upstream/account-mapping.yaml",
                "    operations:",
                "      - name: createAccount",
                "        request_sample: upstream/create-account-request.json",
                "rules:",
                "  - rules/account-rules.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    metadata = build_metadata_project(project_root / "app-definition.yaml")

    fields = {field.name: field for field in metadata.entities[0].fields}

    account_number = fields["accountNumber"]
    assert account_number.max_length == 10
    assert account_number.min_length == 10
    assert account_number.pattern == "^[0-9]{10}$"

    balance = fields["balance"]
    assert balance.range_min == 0.01
    assert balance.range_max == 999999.99

    customer_id = fields["customerId"]
    assert customer_id.not_null is True
    assert customer_id.required is True

    status = fields["status"]
    assert status.not_null is True
    assert status.default_value == "ACTIVE"
    assert status.required is False
