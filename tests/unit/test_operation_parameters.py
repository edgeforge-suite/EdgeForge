"""Tests for OpenAPI query/header parameter support."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.models import OperationParameterLocation


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


def _write_parameter_project(
    project_root: Path,
    *,
    spec_with_parameters: bool,
) -> Path:
    (project_root / "contracts").mkdir(parents=True)
    (project_root / "upstream").mkdir(parents=True)

    spec = (
        {
            "openapi": "3.0.0",
            "paths": {
                "/customers": {
                    "post": {
                        "operationId": "createCustomer",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Customer"}
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
                    },
                    "get": {
                        "operationId": "listCustomers",
                        "parameters": [
                            {
                                "name": "status",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "string", "pattern": "^[A-Z]+$"},
                            },
                            {
                                "name": "pageSize",
                                "in": "query",
                                "required": True,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "X-Correlation-Id",
                                "in": "header",
                                "required": False,
                                "schema": {"type": "string"},
                            },
                        ],
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Customer"},
                                        }
                                    }
                                }
                            }
                        },
                    },
                },
                "/customers/{customerId}": {
                    "get": {
                        "operationId": "getCustomer",
                        "parameters": [
                            {
                                "name": "customerId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "includeHistory",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "boolean"},
                            },
                            {
                                "name": "X-Correlation-Id",
                                "in": "header",
                                "required": False,
                                "schema": {"type": "string"},
                            },
                        ],
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
            "components": {
                "schemas": {
                    "Customer": {
                        "type": "object",
                        "required": ["customerName"],
                        "properties": {
                            "customerId": {"type": "string"},
                            "customerName": {"type": "string"},
                            "status": {"type": "string"},
                        },
                    }
                }
            },
        }
        if spec_with_parameters
        else {}
    )
    (project_root / "contracts" / "customer-api-spec.json").write_text(
        json.dumps(spec),
        encoding="utf-8",
    )

    (project_root / "upstream" / "create-customer-request.json").write_text(
        json.dumps({"customerName": "Alice", "status": "ACTIVE"}),
        encoding="utf-8",
    )
    (project_root / "upstream" / "create-customer-response.json").write_text(
        json.dumps({"customerId": "CUST01", "customerName": "Alice", "status": "ACTIVE"}),
        encoding="utf-8",
    )
    (project_root / "upstream" / "get-customer-response.json").write_text(
        json.dumps({"customerId": "CUST01", "customerName": "Alice", "status": "ACTIVE"}),
        encoding="utf-8",
    )
    (project_root / "upstream" / "list-customers-response.json").write_text(
        json.dumps({"customerId": "CUST01", "customerName": "Alice", "status": "ACTIVE"}),
        encoding="utf-8",
    )
    (project_root / "upstream" / "customer-mapping.yaml").write_text(
        "\n".join(
            [
                "interface: customer-api",
                "entity: Customer",
                "operations:",
                "  - name: createCustomer",
                "    request_mappings:",
                "      - source: customerName",
                "        target: Customer.customerName",
                "      - source: status",
                "        target: Customer.status",
                "    response_mappings:",
                "      - source: customerId",
                "        target: Customer.customerId",
                "      - source: customerName",
                "        target: Customer.customerName",
                "      - source: status",
                "        target: Customer.status",
                "  - name: getCustomer",
                "    response_mappings:",
                "      - source: customerId",
                "        target: Customer.customerId",
                "      - source: customerName",
                "        target: Customer.customerName",
                "      - source: status",
                "        target: Customer.status",
                "  - name: listCustomers",
                "    response_mappings:",
                "      - source: customerId",
                "        target: Customer.customerId",
                "      - source: customerName",
                "        target: Customer.customerName",
                "      - source: status",
                "        target: Customer.status",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / "app-definition.yaml").write_text(
        "\n".join(
            [
                "app_name: Parameterized Customer API",
                "bounded_context: crm",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: customer-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec: contracts/customer-api-spec.json",
                "    mapping: upstream/customer-mapping.yaml",
                "    operations:",
                "      - name: createCustomer",
                "        request_sample: upstream/create-customer-request.json",
                "        response_sample: upstream/create-customer-response.json",
                "      - name: getCustomer",
                "        response_sample: upstream/get-customer-response.json",
                "      - name: listCustomers",
                "        response_sample: upstream/list-customers-response.json",
                "target_profile: springboot-legacy-compatible",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root / "app-definition.yaml"


def _build_parameter_metadata(tmp_path: Path, *, spec_with_parameters: bool = True):
    return build_metadata_project(
        _write_parameter_project(
            tmp_path / ("parameterized-project" if spec_with_parameters else "sample-only-project"),
            spec_with_parameters=spec_with_parameters,
        )
    )


def test_openapi_query_parameter_is_translated(tmp_path: Path) -> None:
    metadata = _build_parameter_metadata(tmp_path)

    operation = next(op for op in metadata.operations if op.name == "listCustomers")
    status = next(param for param in operation.operation_parameters if param.name == "status")
    assert status.location == OperationParameterLocation.QUERY
    assert status.required is False
    assert status.pattern == "^[A-Z]+$"


def test_openapi_header_parameter_is_translated(tmp_path: Path) -> None:
    metadata = _build_parameter_metadata(tmp_path)

    operation = next(op for op in metadata.operations if op.name == "getCustomer")
    correlation = next(
        param for param in operation.operation_parameters if param.name == "X-Correlation-Id"
    )
    assert correlation.location == OperationParameterLocation.HEADER
    assert correlation.required is False


def test_query_parameter_not_added_to_entity_fields(tmp_path: Path) -> None:
    metadata = _build_parameter_metadata(tmp_path)

    customer = next(entity for entity in metadata.entities if entity.name == "Customer")
    field_names = {field.name for field in customer.fields}
    assert "status" in field_names
    assert "pageSize" not in field_names
    assert "X-Correlation-Id" not in field_names


def test_query_inputs_are_retained_but_unsupported_filtering_is_refused(tmp_path: Path) -> None:
    metadata = _build_parameter_metadata(tmp_path)

    output = tmp_path / "BuiltAppParamsCtrl"
    with pytest.raises(ValueError, match="declared query input"):
        generate_application(metadata, output, generation_run_id="params")
    assert not output.exists()


def _classified_metadata_only_project(tmp_path: Path):
    manifest = _write_parameter_project(tmp_path / "classified", spec_with_parameters=True)
    spec_path = manifest.parent / "contracts/customer-api-spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    for item in spec["paths"].values():
        operation = item.get("get")
        if operation:
            operation["parameters"] = [p for p in operation["parameters"] if p["in"] != "query"]
            for parameter in operation["parameters"]:
                if parameter["in"] == "header":
                    parameter["x-edgeforge-read-input-role"] = "metadata"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return build_metadata_project(manifest)


def test_controller_emits_request_header_for_header_parameter(tmp_path: Path) -> None:
    metadata = _classified_metadata_only_project(tmp_path)

    report = generate_application(metadata, tmp_path / "BuiltAppParamsHeader", generation_run_id="params")
    controller = (
        report.output_dir
        / "src/main/java/com/appbuilder/crm/adapter/inbound/CustomerController.java"
    ).read_text(encoding="utf-8")

    assert '@RequestHeader(name = "X-Correlation-Id", required = false) String xCorrelationId' in controller


def test_header_parameter_name_is_safely_sanitized_for_java_variable(tmp_path: Path) -> None:
    metadata = _classified_metadata_only_project(tmp_path)

    report = generate_application(metadata, tmp_path / "BuiltAppParamsNames", generation_run_id="params")
    controller = (
        report.output_dir
        / "src/main/java/com/appbuilder/crm/adapter/inbound/CustomerController.java"
    ).read_text(encoding="utf-8")

    assert 'String xCorrelationId' in controller
    assert 'name = "X-Correlation-Id"' in controller


def test_service_signature_retains_classified_metadata_not_unimplemented_filters(tmp_path: Path) -> None:
    metadata = _classified_metadata_only_project(tmp_path)

    report = generate_application(metadata, tmp_path / "BuiltAppParamsService", generation_run_id="params")
    service = (
        report.output_dir
        / "src/main/java/com/appbuilder/crm/service/CustomerServiceBase.java"
    ).read_text(encoding="utf-8")

    assert "public GetCustomerResponse findById(String id, String xCorrelationId)" in service
    assert "public List<ListCustomersResponse> findAll(String xCorrelationId)" in service
    assert "customerRepository.findById(id)" in service
    assert "includeHistory" not in service


def test_demo_ui_is_not_published_for_ignored_query_filters(tmp_path: Path) -> None:
    metadata = _build_parameter_metadata(tmp_path)

    with pytest.raises(ValueError, match="declared query input"):
        generate_application(metadata, tmp_path / "BuiltAppParamsUi", generation_run_id="params")
    assert not (tmp_path / "BuiltAppParamsUi/src/main/resources/static/index.html").exists()


def test_demo_ui_metadata_headers_do_not_promise_query_filtering(tmp_path: Path) -> None:
    metadata = _classified_metadata_only_project(tmp_path)

    report = generate_application(metadata, tmp_path / "BuiltAppParamsUiJs", generation_run_id="params")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    list_descriptor = _dashboard_descriptor(html, "Customer-list")
    query_hints = {
        hint["contractName"]: hint
        for hint in list_descriptor["hints"]
        if hint.get("query")
    }
    assert list_descriptor["actions"][0]["endpoint"] == "/customers"
    assert query_hints == {}


def test_sample_only_interface_does_not_infer_query_or_header_parameters(tmp_path: Path) -> None:
    metadata = _build_parameter_metadata(tmp_path, spec_with_parameters=False)

    operation = next(op for op in metadata.operations if op.name == "listCustomers")
    assert operation.operation_parameters == []
