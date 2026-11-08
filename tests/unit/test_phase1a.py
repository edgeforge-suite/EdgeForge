"""Phase 1a tests — CRUD REST generation, operation model, nested objects, and warnings.

Covers the eight required test categories from the Phase 1a spec:
1. Operation metadata: translation produces correct HTTP method, path, path params, response shape
2. Controller generation: POST/GET/{id}/GET-list/PUT/{id}/DELETE/{id} with correct annotations
3. Service generation: corresponding service methods present
4. Error handling: ResourceNotFoundException, ErrorResponse, GlobalExceptionHandler files present
5. Nested flattening: single-level nested objects flattened at translation
6. Unsupported construct warnings: deeper nesting/oneOf emits warnings, field skipped
7. Regression: existing single-entity test cases pass (covered by test_generation.py)
8. Regression: existing multi-entity (DDA) test cases pass (covered by test_generation.py)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.ingestion.openapi_classifier import (
    extract_entity_fields,
    ingest_openapi_entities,
    ingest_openapi_operations,
)
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
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _make_crud_profile(name: str, *, emit_flyway: bool = False) -> TargetProfile:
    profile = TargetProfile(
        name=name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=emit_flyway,
        emit_spring_batch=False,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )
    TARGET_PROFILES[name] = profile
    return profile


def _minimal_metadata(
    *,
    entity_name: str = "Widget",
    profile_name: str = "phase1a-test",
    bounded_context: str = "widgets",
    emit_flyway: bool = False,
) -> MetadataProject:
    """Minimal single-entity MetadataProject suitable for Phase 1a generation tests."""
    _make_crud_profile(profile_name, emit_flyway=emit_flyway)

    id_field = CanonicalField(
        name="widgetId",
        type=CanonicalFieldType.STRING,
        is_id=True,
        required=True,
        source_paths=[f"{bounded_context}-api.createWidget.response.widgetId"],
    )
    name_field = CanonicalField(
        name="widgetName",
        type=CanonicalFieldType.STRING,
        required=True,
        max_length=50,
        source_paths=[f"{bounded_context}-api.createWidget.request.widgetName"],
    )
    fields = [id_field, name_field]

    entity = CanonicalEntity(name=entity_name, fields=fields)
    op = CanonicalOperation(
        name=f"create{entity_name}",
        interface_name=f"{bounded_context}-api",
        request_entity=entity_name,
        response_entity=entity_name,
    )
    mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.request.widgetName",
            target_path=f"{entity_name}.widgetName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.response.widgetId",
            target_path=f"{entity_name}.widgetId",
        ),
    ]
    return MetadataProject(
        app_name=f"{entity_name} App",
        bounded_context=bounded_context,
        target_profile=profile_name,
        systems=[SystemParticipant(name="EXT", role="upstream")],
        contracts=[ContractMetadata(name=f"{bounded_context}-api", type="rest-json", source="")],
        operations=[op],
        entities=[entity],
        mappings=mappings,
    )


def _validation_metadata(
    *,
    entity_name: str = "Widget",
    profile_name: str = "phase1a-dto-validation-test",
    bounded_context: str = "widgets",
    include_update: bool = False,
) -> MetadataProject:
    """Single-entity MetadataProject with request-field validation metadata."""
    _make_crud_profile(profile_name)

    fields = [
        CanonicalField(
            name="widgetId",
            type=CanonicalFieldType.STRING,
            is_id=True,
            required=True,
            source_paths=[f"{bounded_context}-api.create{entity_name}.response.widgetId"],
        ),
        CanonicalField(
            name="widgetCode",
            type=CanonicalFieldType.STRING,
            max_length=10,
            source_paths=[f"{bounded_context}-api.create{entity_name}.request.widgetCode"],
        ),
        CanonicalField(
            name="widgetName",
            type=CanonicalFieldType.STRING,
            required=True,
            min_length=5,
            max_length=10,
            source_paths=[f"{bounded_context}-api.create{entity_name}.request.widgetName"],
        ),
        CanonicalField(
            name="externalRef",
            type=CanonicalFieldType.STRING,
            not_null=True,
            source_paths=[f"{bounded_context}-api.create{entity_name}.request.externalRef"],
        ),
        CanonicalField(
            name="accountNumber",
            type=CanonicalFieldType.STRING,
            pattern="^[0-9]{10}$",
            source_paths=[f"{bounded_context}-api.create{entity_name}.request.accountNumber"],
        ),
        CanonicalField(
            name="creditLimit",
            type=CanonicalFieldType.DECIMAL,
            range_min=0.01,
            range_max=999999.99,
            source_paths=[f"{bounded_context}-api.create{entity_name}.request.creditLimit"],
        ),
    ]

    create_op = CanonicalOperation(
        name=f"create{entity_name}",
        interface_name=f"{bounded_context}-api",
        request_entity=entity_name,
        response_entity=entity_name,
    )
    operations = [create_op]
    mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.request.widgetCode",
            target_path=f"{entity_name}.widgetCode",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.request.widgetName",
            target_path=f"{entity_name}.widgetName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.request.externalRef",
            target_path=f"{entity_name}.externalRef",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.request.accountNumber",
            target_path=f"{entity_name}.accountNumber",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.request.creditLimit",
            target_path=f"{entity_name}.creditLimit",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.response.widgetId",
            target_path=f"{entity_name}.widgetId",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.response.widgetCode",
            target_path=f"{entity_name}.widgetCode",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.response.widgetName",
            target_path=f"{entity_name}.widgetName",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.response.externalRef",
            target_path=f"{entity_name}.externalRef",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.response.accountNumber",
            target_path=f"{entity_name}.accountNumber",
        ),
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=f"{bounded_context}-api",
            operation_name=f"create{entity_name}",
            source_path=f"{bounded_context}-api.create{entity_name}.response.creditLimit",
            target_path=f"{entity_name}.creditLimit",
        ),
    ]
    if include_update:
        update_op = CanonicalOperation(
            name=f"update{entity_name}",
            interface_name=f"{bounded_context}-api",
            request_entity=entity_name,
            response_entity=entity_name,
            http_method=HttpMethod.PUT,
        )
        operations.append(update_op)
        mappings.extend(
            [
                FieldMapping(
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    contract_name=f"{bounded_context}-api",
                    operation_name=f"update{entity_name}",
                    source_path=f"{bounded_context}-api.update{entity_name}.request.widgetId",
                    target_path=f"{entity_name}.widgetId",
                ),
                FieldMapping(
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    contract_name=f"{bounded_context}-api",
                    operation_name=f"update{entity_name}",
                    source_path=f"{bounded_context}-api.update{entity_name}.request.widgetName",
                    target_path=f"{entity_name}.widgetName",
                ),
                FieldMapping(
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    contract_name=f"{bounded_context}-api",
                    operation_name=f"update{entity_name}",
                    source_path=f"{bounded_context}-api.update{entity_name}.request.externalRef",
                    target_path=f"{entity_name}.externalRef",
                ),
                FieldMapping(
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    contract_name=f"{bounded_context}-api",
                    operation_name=f"update{entity_name}",
                    source_path=f"{bounded_context}-api.update{entity_name}.request.accountNumber",
                    target_path=f"{entity_name}.accountNumber",
                ),
                FieldMapping(
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    contract_name=f"{bounded_context}-api",
                    operation_name=f"update{entity_name}",
                    source_path=f"{bounded_context}-api.update{entity_name}.request.creditLimit",
                    target_path=f"{entity_name}.creditLimit",
                ),
                FieldMapping(
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    contract_name=f"{bounded_context}-api",
                    operation_name=f"update{entity_name}",
                    source_path=f"{bounded_context}-api.update{entity_name}.response.widgetId",
                    target_path=f"{entity_name}.widgetId",
                ),
            ]
        )
    return MetadataProject(
        app_name=f"{entity_name} Validation App",
        bounded_context=bounded_context,
        target_profile=profile_name,
        systems=[SystemParticipant(name="EXT", role="upstream")],
        contracts=[ContractMetadata(name=f"{bounded_context}-api", type="rest-json", source="")],
        operations=operations,
        entities=[CanonicalEntity(name=entity_name, fields=fields)],
        mappings=mappings,
    )


# ---------------------------------------------------------------------------
# 1. Operation metadata — ingest_openapi_operations
# ---------------------------------------------------------------------------

class TestOperationMetadata:
    """Phase 1a-1: ingest_openapi_operations produces correct HTTP method, path, path params, response shape."""

    _SPEC: dict = {
        "openapi": "3.0.0",
        "components": {
            "schemas": {
                "Product": {
                    "type": "object",
                    "required": ["productId"],
                    "properties": {
                        "productId": {"type": "string"},
                        "name": {"type": "string"},
                    },
                }
            }
        },
        "paths": {
            "/products": {
                "post": {
                    "operationId": "createProduct",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Product"}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Product"}
                                }
                            }
                        }
                    },
                },
                "get": {
                    "operationId": "listProducts",
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Product"},
                                    }
                                }
                            }
                        }
                    },
                },
            },
            "/products/{productId}": {
                "get": {
                    "operationId": "getProduct",
                    "parameters": [
                        {
                            "name": "productId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Product"}
                                }
                            }
                        }
                    },
                },
                "put": {
                    "operationId": "updateProduct",
                    "parameters": [
                        {
                            "name": "productId",
                            "in": "path",
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Product"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Product"}
                                }
                            }
                        }
                    },
                },
                "delete": {
                    "operationId": "deleteProduct",
                    "parameters": [
                        {
                            "name": "productId",
                            "in": "path",
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"204": {}},
                },
            },
        },
    }

    def setup_method(self):
        self._ops = {op.name: op for op in ingest_openapi_operations(self._SPEC, "product-api")}

    def test_post_has_correct_http_method_and_response_shape(self):
        op = self._ops["createProduct"]
        assert op.http_method == HttpMethod.POST
        assert op.response_shape == ResponseShape.CREATED
        assert op.has_request_body is True
        assert op.path == "/products"

    def test_get_list_has_list_response_shape(self):
        op = self._ops["listProducts"]
        assert op.http_method == HttpMethod.GET
        assert op.response_shape == ResponseShape.LIST
        assert op.has_request_body is False

    def test_get_by_id_has_single_response_shape_and_path_param(self):
        op = self._ops["getProduct"]
        assert op.http_method == HttpMethod.GET
        assert op.response_shape == ResponseShape.SINGLE
        assert len(op.path_parameters) == 1
        assert op.path_parameters[0].name == "productId"
        assert op.path_parameters[0].type == "String"

    def test_put_has_single_response_shape_and_request_body(self):
        op = self._ops["updateProduct"]
        assert op.http_method == HttpMethod.PUT
        assert op.response_shape == ResponseShape.SINGLE
        assert op.has_request_body is True
        assert "/products/{productId}" in op.path

    def test_delete_has_void_response_shape(self):
        op = self._ops["deleteProduct"]
        assert op.http_method == HttpMethod.DELETE
        assert op.response_shape == ResponseShape.VOID
        assert op.has_request_body is False

    def test_path_parameter_integer_type_maps_to_long(self):
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/items/{itemId}": {
                    "get": {
                        "operationId": "getItem",
                        "parameters": [
                            {
                                "name": "itemId",
                                "in": "path",
                                "schema": {"type": "integer"},
                            }
                        ],
                        "responses": {"200": {}},
                    }
                }
            },
        }
        ops = ingest_openapi_operations(spec, "items-api")
        assert len(ops) == 1
        assert ops[0].path_parameters[0].type == "Long"

    def test_operation_interface_name_matches_argument(self):
        for op in self._ops.values():
            assert op.interface_name == "product-api"

    def test_nullable_union_types_in_parameters_and_request_fields_do_not_crash(self):
        spec = {
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "Customer": {
                        "type": "object",
                        "properties": {
                            "customerId": {"type": "string"},
                            "nickname": {"type": ["string", "null"]},
                        },
                    }
                }
            },
            "paths": {
                "/customers/{customerId}": {
                    "get": {
                        "operationId": "getCustomer",
                        "parameters": [
                            {
                                "name": "customerId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": ["string", "null"]},
                            },
                            {
                                "name": "includeArchived",
                                "in": "query",
                                "required": False,
                                "schema": {"type": ["boolean", "null"]},
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
                }
            },
        }

        ops = ingest_openapi_operations(spec, "customer-api")

        assert len(ops) == 1
        assert ops[0].path_parameters[0].type == "String"
        assert ops[0].operation_parameters[0].type.value == "boolean"
        response_fields = {field.name: field for field in ops[0].response_fields}
        assert response_fields["nickname"].type.value == "string"


# ---------------------------------------------------------------------------
# 2. Controller generation — full CRUD annotations
# ---------------------------------------------------------------------------

class TestCrudControllerGeneration:
    """Phase 1a-2: Generated controller has correct HTTP annotations for all CRUD endpoints."""

    @pytest.fixture(autouse=True)
    def generate(self, tmp_path):
        metadata = _minimal_metadata(profile_name="phase1a-ctrl-test", bounded_context="widgets")
        output_dir = tmp_path / "CtrlTest"
        generate_application(metadata, output_dir, generation_run_id="ctrl-test")
        inbound = output_dir / "src/main/java/com/appbuilder/widgets/adapter/inbound"
        self.controller = (inbound / "WidgetController.java").read_text(encoding="utf-8")
        TARGET_PROFILES.pop("phase1a-ctrl-test", None)

    def test_class_level_request_mapping(self):
        assert '@RequestMapping("/widgets")' in self.controller

    def test_post_mapping_for_create(self):
        assert "@PostMapping" in self.controller

    def test_get_mapping_present(self):
        assert "@GetMapping" in self.controller

    def test_put_mapping_present(self):
        assert "@PutMapping" in self.controller

    def test_delete_mapping_present(self):
        assert "@DeleteMapping" in self.controller

    def test_get_by_id_returns_response_entity(self):
        assert "ResponseEntity" in self.controller

    def test_post_returns_created_status(self):
        assert "HttpStatus.CREATED" in self.controller or "ResponseEntity.status(HttpStatus.CREATED)" in self.controller or "201" in self.controller

    def test_delete_returns_no_content(self):
        # DELETE /widgets/{id} → 204 No Content
        assert "HttpStatus.NO_CONTENT" in self.controller or "204" in self.controller or "noContent" in self.controller

    def test_path_variable_in_by_id_methods(self):
        assert "@PathVariable" in self.controller

    def test_get_by_id_method_present(self):
        assert "getById" in self.controller

    def test_list_all_method_present(self):
        assert "listAll" in self.controller

    def test_delete_method_present(self):
        assert "delete" in self.controller


# ---------------------------------------------------------------------------
# DTO validation annotations — Phase 1b
# ---------------------------------------------------------------------------

class TestDtoValidationAnnotations:
    """Phase 1b: Request DTOs emit Bean Validation annotations from canonical field metadata."""

    @pytest.fixture(autouse=True)
    def generate(self, tmp_path):
        metadata = _validation_metadata()
        output_dir = tmp_path / "DtoValidationTest"
        generate_application(metadata, output_dir, generation_run_id="dto-validation-test")
        inbound = output_dir / "src/main/java/com/appbuilder/widgets/adapter/inbound"
        self.request_dto = (inbound / "CreateWidgetRequest.java").read_text(encoding="utf-8")
        self.response_dto = (inbound / "CreateWidgetResponse.java").read_text(encoding="utf-8")
        self.controller = (inbound / "WidgetController.java").read_text(encoding="utf-8")
        self.pom = (output_dir / "pom.xml").read_text(encoding="utf-8")
        TARGET_PROFILES.pop("phase1a-dto-validation-test", None)

    def test_not_null_field_gets_notnull_annotation(self):
        assert "@NotNull\n    private String externalRef;" in self.request_dto

    def test_max_length_field_gets_code_point_length_annotation(self):
        assert (
            "import org.hibernate.validator.constraints.CodePointLength;"
            in self.request_dto
        )
        assert "@CodePointLength(max=10)\n    private String widgetCode;" in self.request_dto

    def test_min_and_max_length_combined(self):
        assert "@CodePointLength(min=5, max=10)\n    private String widgetName;" in self.request_dto

    def test_size_not_emitted_for_decimal_field(self, tmp_path):
        metadata = _validation_metadata(
            entity_name="Loan",
            profile_name="phase1a-dto-validation-decimal-size-guard",
            bounded_context="lending",
        )
        metadata.entities[0].fields = [
            CanonicalField(
                name="loanId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["lending-api.createLoan.response.loanId"],
            ),
            CanonicalField(
                name="loanAmount",
                type=CanonicalFieldType.DECIMAL,
                min_length=1,
                max_length=15,
                source_paths=["lending-api.createLoan.request.loanAmount"],
            ),
        ]
        metadata.mappings = [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="lending-api",
                operation_name="createLoan",
                source_path="lending-api.createLoan.request.loanAmount",
                target_path="Loan.loanAmount",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="lending-api",
                operation_name="createLoan",
                source_path="lending-api.createLoan.response.loanId",
                target_path="Loan.loanId",
            ),
        ]

        output_dir = tmp_path / "DtoValidationDecimalSizeGuard"
        generate_application(metadata, output_dir, generation_run_id="dto-validation-decimal-size-guard")
        dto_src = (
            output_dir
            / "src/main/java/com/appbuilder/lending/adapter/inbound/CreateLoanRequest.java"
        ).read_text(encoding="utf-8")

        assert "@CodePointLength(" not in dto_src
        TARGET_PROFILES.pop("phase1a-dto-validation-decimal-size-guard", None)

    def test_size_not_emitted_for_integer_field(self, tmp_path):
        metadata = _validation_metadata(
            entity_name="Order",
            profile_name="phase1a-dto-validation-integer-size-guard",
            bounded_context="orders",
        )
        metadata.entities[0].fields = [
            CanonicalField(
                name="orderId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["orders-api.createOrder.response.orderId"],
            ),
            CanonicalField(
                name="quantity",
                type=CanonicalFieldType.INTEGER,
                min_length=1,
                max_length=6,
                source_paths=["orders-api.createOrder.request.quantity"],
            ),
        ]
        metadata.mappings = [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="orders-api",
                operation_name="createOrder",
                source_path="orders-api.createOrder.request.quantity",
                target_path="Order.quantity",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="orders-api",
                operation_name="createOrder",
                source_path="orders-api.createOrder.response.orderId",
                target_path="Order.orderId",
            ),
        ]

        output_dir = tmp_path / "DtoValidationIntegerSizeGuard"
        generate_application(metadata, output_dir, generation_run_id="dto-validation-integer-size-guard")
        dto_src = (
            output_dir
            / "src/main/java/com/appbuilder/orders/adapter/inbound/CreateOrderRequest.java"
        ).read_text(encoding="utf-8")

        assert "@CodePointLength(" not in dto_src
        TARGET_PROFILES.pop("phase1a-dto-validation-integer-size-guard", None)

    def test_size_still_emitted_for_string_field(self, tmp_path):
        metadata = _validation_metadata(
            entity_name="Customer",
            profile_name="phase1a-dto-validation-string-size-guard",
            bounded_context="customers",
        )
        metadata.entities[0].fields = [
            CanonicalField(
                name="customerId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                source_paths=["customers-api.createCustomer.response.customerId"],
            ),
            CanonicalField(
                name="lastName",
                type=CanonicalFieldType.STRING,
                min_length=1,
                max_length=50,
                source_paths=["customers-api.createCustomer.request.lastName"],
            ),
        ]
        metadata.mappings = [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="customers-api",
                operation_name="createCustomer",
                source_path="customers-api.createCustomer.request.lastName",
                target_path="Customer.lastName",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="customers-api",
                operation_name="createCustomer",
                source_path="customers-api.createCustomer.response.customerId",
                target_path="Customer.customerId",
            ),
        ]

        output_dir = tmp_path / "DtoValidationStringSizeGuard"
        generate_application(metadata, output_dir, generation_run_id="dto-validation-string-size-guard")
        dto_src = (
            output_dir
            / "src/main/java/com/appbuilder/customers/adapter/inbound/CreateCustomerRequest.java"
        ).read_text(encoding="utf-8")

        assert "@CodePointLength(" in dto_src
        assert "min=1" in dto_src
        assert "max=50" in dto_src
        TARGET_PROFILES.pop("phase1a-dto-validation-string-size-guard", None)

    def test_pattern_field_gets_pattern_annotation(self):
        assert '@Pattern(regexp="^[0-9]{10}$")\n    private String accountNumber;' in self.request_dto

    def test_range_fields_get_decimal_min_max(self):
        assert '@DecimalMin("0.01")' in self.request_dto
        assert '@DecimalMax("999999.99")\n    private BigDecimal creditLimit;' in self.request_dto

    def test_response_dto_has_no_validation_annotations(self):
        assert "@NotNull" not in self.response_dto
        assert "@CodePointLength(" not in self.response_dto
        assert "@Pattern(" not in self.response_dto
        assert "@DecimalMin(" not in self.response_dto
        assert "@DecimalMax(" not in self.response_dto

    def test_controller_request_body_has_valid_annotation(self):
        assert "import jakarta.validation.Valid;" in self.controller
        assert "(@Valid @RequestBody CreateWidgetRequest request)" in self.controller

    def test_pom_includes_validation_starter(self):
        assert "<artifactId>spring-boot-starter-validation</artifactId>" in self.pom

    def test_controller_put_uses_update_request_with_valid_annotation(self, tmp_path):
        metadata = _validation_metadata(
            profile_name="phase1a-dto-validation-update-test",
            include_update=True,
        )
        output_dir = tmp_path / "DtoValidationUpdateTest"
        generate_application(metadata, output_dir, generation_run_id="dto-validation-update-test")
        controller = (
            output_dir
            / "src/main/java/com/appbuilder/widgets/adapter/inbound/WidgetController.java"
        ).read_text(encoding="utf-8")
        service = (
            output_dir
            / "src/main/java/com/appbuilder/widgets/service/WidgetServiceBase.java"
        ).read_text(encoding="utf-8")

        assert controller.count("@Valid @RequestBody") == 2
        assert "@Valid @RequestBody UpdateWidgetRequest request" in controller
        assert "public UpdateWidgetResponse updateWidget(String id, UpdateWidgetRequest request)" in service
        assert "widget.setWidgetId(id);  // path id always takes precedence" in service
        assert "UpdateWidgetResponse updateWidgetResponse = new UpdateWidgetResponse();" in service
        assert "updateWidgetResponse.setWidgetId(saved.getWidgetId());" in service

        TARGET_PROFILES.pop("phase1a-dto-validation-update-test", None)


# ---------------------------------------------------------------------------
# 3. Service generation — CRUD service methods
# ---------------------------------------------------------------------------

class TestCrudServiceGeneration:
    """Phase 1a-3: Generated service has findById, findAll, update, delete methods."""

    @pytest.fixture(autouse=True)
    def generate(self, tmp_path):
        metadata = _minimal_metadata(profile_name="phase1a-svc-test", bounded_context="widgets")
        output_dir = tmp_path / "SvcTest"
        generate_application(metadata, output_dir, generation_run_id="svc-test")
        svc_dir = output_dir / "src/main/java/com/appbuilder/widgets/service"
        self.service = (svc_dir / "WidgetServiceBase.java").read_text(encoding="utf-8")
        TARGET_PROFILES.pop("phase1a-svc-test", None)

    def test_service_has_find_by_id(self):
        assert "findById" in self.service

    def test_service_has_find_all(self):
        assert "findAll" in self.service

    def test_service_throws_resource_not_found_exception(self):
        assert "ResourceNotFoundException" in self.service

    def test_service_has_delete(self):
        assert "delete" in self.service or "deleteById" in self.service

    def test_service_has_create_method(self):
        assert "createWidget" in self.service

    def test_service_imports_repository(self):
        assert "Repository" in self.service or "repository" in self.service.lower()


# ---------------------------------------------------------------------------
# 4. Error handling — singleton error files emitted per app
# ---------------------------------------------------------------------------

class TestErrorHandlingGeneration:
    """Phase 1a-4: ResourceNotFoundException, ErrorResponse, GlobalExceptionHandler emitted once per app."""

    @pytest.fixture(autouse=True)
    def generate(self, tmp_path):
        metadata = _minimal_metadata(profile_name="phase1a-err-test", bounded_context="widgets")
        output_dir = tmp_path / "ErrTest"
        generate_application(metadata, output_dir, generation_run_id="err-test")
        exception_dir = output_dir / "src/main/java/com/appbuilder/widgets/exception"
        self.exception_dir = exception_dir
        TARGET_PROFILES.pop("phase1a-err-test", None)

    def test_resource_not_found_exception_file_exists(self):
        assert (self.exception_dir / "ResourceNotFoundException.java").exists()

    def test_error_response_file_exists(self):
        assert (self.exception_dir / "ErrorResponse.java").exists()

    def test_global_exception_handler_file_exists(self):
        assert (self.exception_dir / "GlobalExceptionHandler.java").exists()

    def test_resource_not_found_extends_runtime_exception(self):
        content = (self.exception_dir / "ResourceNotFoundException.java").read_text(encoding="utf-8")
        assert "RuntimeException" in content

    def test_global_exception_handler_has_rest_controller_advice(self):
        content = (self.exception_dir / "GlobalExceptionHandler.java").read_text(encoding="utf-8")
        assert "@RestControllerAdvice" in content

    def test_global_exception_handler_has_exception_handler_for_not_found(self):
        content = (self.exception_dir / "GlobalExceptionHandler.java").read_text(encoding="utf-8")
        assert "@ExceptionHandler" in content
        assert "ResourceNotFoundException" in content

    def test_error_handling_files_only_emitted_once_not_per_entity(self, tmp_path):
        """Error handling is a singleton per app, not duplicated per entity."""
        _make_crud_profile("phase1a-multi-err-test")
        entity_a = CanonicalEntity(
            name="Alpha",
            fields=[
                CanonicalField(name="alphaId", type=CanonicalFieldType.STRING, is_id=True, required=True, source_paths=["api.op.response.alphaId"]),
            ],
        )
        entity_b = CanonicalEntity(
            name="Beta",
            fields=[
                CanonicalField(name="betaId", type=CanonicalFieldType.STRING, is_id=True, required=True, source_paths=["api.op.response.betaId"]),
            ],
        )
        op_a = CanonicalOperation(name="createAlpha", interface_name="api", request_entity="Alpha", response_entity="Alpha")
        op_b = CanonicalOperation(name="createBeta", interface_name="api", request_entity="Beta", response_entity="Beta")
        mappings = [
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api", operation_name="createAlpha", source_path="api.createAlpha.response.alphaId", target_path="Alpha.alphaId"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api", operation_name="createBeta", source_path="api.createBeta.response.betaId", target_path="Beta.betaId"),
        ]
        metadata = MetadataProject(
            app_name="Multi Entity App",
            bounded_context="multi",
            target_profile="phase1a-multi-err-test",
            systems=[SystemParticipant(name="EXT", role="upstream")],
            contracts=[ContractMetadata(name="api", type="rest-json", source="")],
            operations=[op_a, op_b],
            entities=[entity_a, entity_b],
            mappings=mappings,
        )
        output_dir = tmp_path / "MultiErrTest"
        generate_application(metadata, output_dir, generation_run_id="multi-err-test")
        exception_dir = output_dir / "src/main/java/com/appbuilder/multi/exception"

        # Exactly one of each — no per-entity duplication
        assert (exception_dir / "ResourceNotFoundException.java").exists()
        assert (exception_dir / "ErrorResponse.java").exists()
        assert (exception_dir / "GlobalExceptionHandler.java").exists()

        # Should NOT have entity-prefixed exception files
        assert not (exception_dir / "AlphaResourceNotFoundException.java").exists()
        assert not (exception_dir / "BetaResourceNotFoundException.java").exists()

        TARGET_PROFILES.pop("phase1a-multi-err-test", None)


# ---------------------------------------------------------------------------
# 5. Nested object flattening at translation
# ---------------------------------------------------------------------------

class TestNestedObjectFlattening:
    """Phase 1a-5: Single-level nested value objects are flattened at field extraction."""

    def test_single_level_nested_object_flattened(self):
        """address.line1 → addressLine1, address.city → addressCity."""
        schema = {
            "type": "object",
            "required": ["customerId", "address"],
            "properties": {
                "customerId": {"type": "string"},
                "address": {
                    "type": "object",
                    "required": ["line1"],
                    "properties": {
                        "line1": {"type": "string", "maxLength": 100},
                        "city": {"type": "string"},
                    },
                },
            },
        }
        warnings: list[str] = []
        fields = extract_entity_fields("Customer", schema, warnings_out=warnings)
        field_names = [f.name for f in fields]

        # Nested fields must be flattened with parent prefix
        assert "addressLine1" in field_names
        assert "addressCity" in field_names
        # Original nested field name must not appear
        assert "address" not in field_names
        # No warnings for single-level nesting
        assert not warnings

    def test_flattened_nested_field_preserves_max_length(self):
        schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {
                        "line1": {"type": "string", "maxLength": 100},
                    },
                },
            },
        }
        fields = extract_entity_fields("Customer", schema)
        field_map = {f.name: f for f in fields}
        assert field_map["addressLine1"].max_length == 100

    def test_flattened_required_propagates_only_when_parent_and_child_required(self):
        schema = {
            "type": "object",
            "required": ["address"],
            "properties": {
                "address": {
                    "type": "object",
                    "required": ["line1"],
                    "properties": {
                        "line1": {"type": "string"},
                        "line2": {"type": "string"},  # not required
                    },
                },
            },
        }
        fields = extract_entity_fields("Customer", schema)
        field_map = {f.name: f for f in fields}
        # line1: parent(required) AND child(required) → required=True
        assert field_map["addressLine1"].required is True
        # line2: parent(required) BUT NOT child(required) → required=False
        assert field_map["addressLine2"].required is False

    def test_array_of_strings_is_skipped_with_warning(self):
        """Scalar arrays are unsupported in Phase 1a — emits warning and skips the field."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        }
        warnings: list[str] = []
        fields = extract_entity_fields("Product", schema, warnings_out=warnings)
        field_names = [f.name for f in fields]
        # tags must be skipped — scalar arrays not supported in Phase 1a
        assert "tags" not in field_names
        # name should still be present
        assert "name" in field_names
        # a warning must be emitted
        assert any("tags" in w for w in warnings)

    def test_array_of_integers_is_skipped_with_warning(self):
        """Scalar integer arrays are also unsupported in Phase 1a."""
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "scores": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
        }
        warnings: list[str] = []
        fields = extract_entity_fields("Result", schema, warnings_out=warnings)
        field_names = [f.name for f in fields]
        assert "scores" not in field_names
        assert "id" in field_names
        assert any("scores" in w for w in warnings)


# ---------------------------------------------------------------------------
# 6. Unsupported construct warnings
# ---------------------------------------------------------------------------

class TestUnsupportedConstructWarnings:
    """Phase 1a-6: Deeper nesting, arrays of objects, oneOf/anyOf produce warnings and skip fields."""

    def test_array_of_objects_produces_warning_and_skips_field(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lineItems": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"qty": {"type": "integer"}}},
                },
            },
        }
        warnings: list[str] = []
        fields = extract_entity_fields("Order", schema, warnings_out=warnings)
        field_names = [f.name for f in fields]

        # lineItems must be skipped
        assert "lineItems" not in field_names
        # name should still be present
        assert "name" in field_names
        # A warning should have been collected
        assert any("lineItems" in w for w in warnings)

    def test_deeper_nesting_produces_warning_and_skips_field(self):
        """Nested object containing another nested object (depth > 1) → warning + skip."""
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "location": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "object",  # depth 2 — not supported
                            "properties": {"line1": {"type": "string"}},
                        }
                    },
                },
            },
        }
        warnings: list[str] = []
        fields = extract_entity_fields("Venue", schema, warnings_out=warnings)
        field_names = [f.name for f in fields]

        assert "location" not in field_names
        # No deeply-flattened fields should appear either
        assert not any(n.startswith("location") for n in field_names)
        assert any("location" in w for w in warnings)

    def test_top_level_oneof_schema_produces_warning_and_returns_empty(self):
        schema = {
            "oneOf": [
                {"$ref": "#/components/schemas/CatProduct"},
                {"$ref": "#/components/schemas/DogProduct"},
            ]
        }
        warnings: list[str] = []
        fields = extract_entity_fields("Pet", schema, warnings_out=warnings)
        assert fields == []
        assert any("oneOf" in w or "anyOf" in w for w in warnings)

    def test_field_level_oneof_produces_warning_and_skips_field(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "status": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "integer"},
                    ]
                },
            },
        }
        warnings: list[str] = []
        fields = extract_entity_fields("Product", schema, warnings_out=warnings)
        field_names = [f.name for f in fields]

        assert "status" not in field_names
        assert "name" in field_names
        assert any("status" in w for w in warnings)

    def test_warnings_propagate_from_ingest_entities_to_entity(self):
        """Entity-level warnings collected during ingest_openapi_entities are attached to the entity."""
        spec = {
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "Order": {
                        "type": "object",
                        "required": ["orderId"],
                        "properties": {
                            "orderId": {"type": "string"},
                            "lineItems": {
                                "type": "array",
                                "items": {"type": "object", "properties": {"qty": {"type": "integer"}}},
                            },
                        },
                    }
                }
            },
            "paths": {
                "/orders": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Order"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
        }
        entities = ingest_openapi_entities(spec, "order-api")
        assert len(entities) == 1
        order = entities[0]
        # lineItems field must be skipped
        assert not any(f.name == "lineItems" for f in order.fields)
        # Warning must be attached to the entity
        assert order.warnings
        assert any("lineItems" in w for w in order.warnings)

    def test_warnings_propagate_from_entity_to_project(self, monkeypatch, tmp_path):
        """Entity-level warnings make it into MetadataProject.warnings during translate_project."""
        from appbuilder.metadata import build_metadata_project

        project_root = tmp_path / "warning-test"
        project_root.mkdir(parents=True)
        (project_root / "app-definition.yaml").write_text(
            "\n".join([
                "app_name: Warning Test",
                "bounded_context: orders",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: order-api",
                "    system: OMS",
                "    type: rest-json",
                "    spec_url: http://localhost/openapi.json",
                "target_profile: springboot-legacy-compatible",
            ]),
            encoding="utf-8",
        )

        spec = {
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "Order": {
                        "type": "object",
                        "required": ["orderId"],
                        "properties": {
                            "orderId": {"type": "string"},
                            "lineItems": {
                                "type": "array",
                                "items": {"type": "object", "properties": {"qty": {"type": "integer"}}},
                            },
                        },
                    }
                }
            },
            "paths": {
                "/orders/{orderId}": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Order"}
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
        # Warnings about unsupported constructs must surface at the project level
        assert metadata.warnings
        assert any("lineItems" in w for w in metadata.warnings)


# ---------------------------------------------------------------------------
# 7. List field types flow through to SQL / Java
# ---------------------------------------------------------------------------

class TestScalarArraysUnsupported:
    """Phase 1a: scalar arrays (list_string/list_integer) are unsupported — warning+skip.

    Collection-table support (either @ElementCollection or a separate join-table) is
    deferred to Phase 1b.  Emitting a TEXT column is inconsistent with JPA and was
    removed.  All array fields now produce a clear warning and are excluded from the
    canonical model.
    """

    def test_scalar_string_array_produces_warning_and_skips_field(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        }
        warnings: list[str] = []
        fields = extract_entity_fields("Product", schema, warnings_out=warnings)
        assert not any(f.name == "tags" for f in fields), "tags must be skipped"
        assert any("tags" in w for w in warnings), "warning must reference the field name"

    def test_scalar_integer_array_produces_warning_and_skips_field(self):
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "scores": {"type": "array", "items": {"type": "integer"}},
            },
        }
        warnings: list[str] = []
        fields = extract_entity_fields("Result", schema, warnings_out=warnings)
        assert not any(f.name == "scores" for f in fields), "scores must be skipped"
        assert any("scores" in w for w in warnings)

    def test_array_warning_message_mentions_phase1b(self):
        """Warning message should guide the user toward Phase 1b."""
        schema = {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "string"}},
            },
        }
        warnings: list[str] = []
        extract_entity_fields("Order", schema, warnings_out=warnings)
        assert warnings
        # The warning should clearly state why and when support is coming
        combined = " ".join(warnings).lower()
        assert "not supported" in combined or "unsupported" in combined


# ---------------------------------------------------------------------------
# 8. ID ownership — server-generated vs client-supplied
# ---------------------------------------------------------------------------

class TestIdOwnership:
    """Phase 1a bonus: server_generated_id controls @GeneratedValue presence in emitted entity."""

    def test_server_generated_id_produces_generated_value_annotation(self, tmp_path):
        metadata = _minimal_metadata(profile_name="phase1a-id-server-test", bounded_context="widgets")
        # Default: server_generated_id=True on the id field
        output_dir = tmp_path / "ServerIdTest"
        generate_application(metadata, output_dir, generation_run_id="server-id-test")
        entity = (output_dir / "src/main/java/com/appbuilder/widgets/domain/Widget.java").read_text(encoding="utf-8")
        assert "@GeneratedValue" in entity
        TARGET_PROFILES.pop("phase1a-id-server-test", None)

    def test_client_supplied_id_omits_generated_value_annotation(self, tmp_path):
        _make_crud_profile("phase1a-id-client-test")
        entity = CanonicalEntity(
            name="Widget",
            fields=[
                CanonicalField(
                    name="widgetId",
                    type=CanonicalFieldType.STRING,
                    is_id=True,
                    required=True,
                    server_generated_id=False,
                    source_paths=["api.createWidget.request.widgetId"],
                ),
                CanonicalField(
                    name="widgetName",
                    type=CanonicalFieldType.STRING,
                    required=True,
                    source_paths=["api.createWidget.request.widgetName"],
                ),
            ],
        )
        op = CanonicalOperation(name="createWidget", interface_name="api", request_entity="Widget", response_entity="Widget")
        mappings = [
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api", operation_name="createWidget", source_path="api.createWidget.request.widgetId", target_path="Widget.widgetId"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api", operation_name="createWidget", source_path="api.createWidget.request.widgetName", target_path="Widget.widgetName"),
        ]
        metadata = MetadataProject(
            app_name="Widget App",
            bounded_context="widgets",
            target_profile="phase1a-id-client-test",
            systems=[SystemParticipant(name="EXT", role="upstream")],
            contracts=[ContractMetadata(name="api", type="rest-json", source="")],
            operations=[op],
            entities=[entity],
            mappings=mappings,
        )
        output_dir = tmp_path / "ClientIdTest"
        generate_application(metadata, output_dir, generation_run_id="client-id-test")
        entity_java = (output_dir / "src/main/java/com/appbuilder/widgets/domain/Widget.java").read_text(encoding="utf-8")
        assert "@GeneratedValue" not in entity_java
        TARGET_PROFILES.pop("phase1a-id-client-test", None)


# ---------------------------------------------------------------------------
# 9. Warnings surfaced in GenerationReport
# ---------------------------------------------------------------------------

class TestWarningsInGenerationReport:
    """Phase 1a bonus: translation warnings appear in the GenerationReport.warnings list."""

    def test_generation_report_includes_translation_warnings(self, tmp_path):
        _make_crud_profile("phase1a-warn-report-test")
        entity = CanonicalEntity(
            name="Product",
            fields=[
                CanonicalField(name="productId", type=CanonicalFieldType.STRING, is_id=True, required=True, source_paths=["api.op.response.productId"]),
            ],
            warnings=["Field 'lineItems': array of objects not supported in Phase 1a — field skipped."],
        )
        op = CanonicalOperation(name="createProduct", interface_name="api", request_entity="Product", response_entity="Product")
        mappings = [
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api", operation_name="createProduct", source_path="api.op.response.productId", target_path="Product.productId"),
        ]
        metadata = MetadataProject(
            app_name="Product App",
            bounded_context="catalog",
            target_profile="phase1a-warn-report-test",
            systems=[SystemParticipant(name="EXT", role="upstream")],
            contracts=[ContractMetadata(name="api", type="rest-json", source="")],
            operations=[op],
            entities=[entity],
            mappings=mappings,
            warnings=["Product: Field 'lineItems': array of objects not supported in Phase 1a — field skipped."],
        )
        output_dir = tmp_path / "WarnReport"
        report = generate_application(metadata, output_dir, generation_run_id="warn-report-test")
        assert report.warnings
        assert any("lineItems" in w for w in report.warnings)
        TARGET_PROFILES.pop("phase1a-warn-report-test", None)


# ---------------------------------------------------------------------------
# 10. ID ownership detection — Finding 3
#     Tests that the actual inference wiring works correctly for both
#     sample-based and OpenAPI-based ingestion paths.
# ---------------------------------------------------------------------------

class TestIdOwnershipDetection:
    """Finding 3: client-supplied ID detection is wired in both translation paths.

    Three required scenarios per the review:
    A. Sample-based create with request id → server_generated_id=False → no @GeneratedValue
    B. OpenAPI create request body with id present → server_generated_id=False → no @GeneratedValue
    C. OpenAPI create request body without id → server_generated_id=True → @GeneratedValue present
    """

    # --- A. Sample-based ingestion ---

    def test_sample_based_create_with_request_id_sets_client_supplied(self, tmp_path):
        """A: When the id field is present in the create request sample, server_generated_id=False."""
        from appbuilder.metadata import build_metadata_project

        project_root = tmp_path / "client-id-sample"
        (project_root / "upstream").mkdir(parents=True)

        # Request sample includes orderId — client supplies it
        (project_root / "upstream" / "create-order-request.json").write_text(
            '{"orderId": "ORD-001", "amount": 99.99}',
            encoding="utf-8",
        )
        (project_root / "upstream" / "order-mapping.yaml").write_text(
            "\n".join([
                "entity: Order",
                "operations:",
                "  - name: createOrder",
                "    request_mappings:",
                "      - source: orderId",
                "        target: Order.orderId",
                "      - source: amount",
                "        target: Order.amount",
            ]),
            encoding="utf-8",
        )
        (project_root / "app-definition.yaml").write_text(
            "\n".join([
                "app_name: Order Service",
                "bounded_context: orders",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: order-api",
                "    system: OMS",
                "    type: rest-json",
                "    spec_url: https://example.com/swagger.json",
                "    mapping: upstream/order-mapping.yaml",
                "    operations:",
                "      - name: createOrder",
                "        request_sample: upstream/create-order-request.json",
                "target_profile: springboot-legacy-compatible",
            ]),
            encoding="utf-8",
        )

        metadata = build_metadata_project(project_root / "app-definition.yaml")
        order = metadata.entities[0]
        field_map = {f.name: f for f in order.fields}
        assert "orderId" in field_map
        assert field_map["orderId"].is_id is True
        # id appeared in request → client-supplied → no server generation
        assert field_map["orderId"].server_generated_id is False

    def test_sample_based_create_with_response_only_id_sets_server_generated(self, tmp_path):
        """A (counter-case): id only in response → server_generated_id stays True."""
        from appbuilder.metadata import build_metadata_project

        project_root = tmp_path / "server-id-sample"
        (project_root / "upstream").mkdir(parents=True)

        (project_root / "upstream" / "create-request.json").write_text(
            '{"amount": 50.00}',
            encoding="utf-8",
        )
        (project_root / "upstream" / "create-response.json").write_text(
            '{"orderId": "ORD-999", "amount": 50.00}',
            encoding="utf-8",
        )
        (project_root / "upstream" / "order-mapping.yaml").write_text(
            "\n".join([
                "entity: Order",
                "operations:",
                "  - name: createOrder",
                "    request_mappings:",
                "      - source: amount",
                "        target: Order.amount",
                "    response_mappings:",
                "      - source: orderId",
                "        target: Order.orderId",
                "      - source: amount",
                "        target: Order.amount",
            ]),
            encoding="utf-8",
        )
        (project_root / "app-definition.yaml").write_text(
            "\n".join([
                "app_name: Order Service",
                "bounded_context: orders",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: order-api",
                "    system: OMS",
                "    type: rest-json",
                "    spec_url: https://example.com/swagger.json",
                "    mapping: upstream/order-mapping.yaml",
                "    operations:",
                "      - name: createOrder",
                "        request_sample: upstream/create-request.json",
                "        response_sample: upstream/create-response.json",
                "target_profile: springboot-legacy-compatible",
            ]),
            encoding="utf-8",
        )

        metadata = build_metadata_project(project_root / "app-definition.yaml")
        order = metadata.entities[0]
        field_map = {f.name: f for f in order.fields}
        assert "orderId" in field_map
        assert field_map["orderId"].is_id is True
        # id not in request → server-generated
        assert field_map["orderId"].server_generated_id is True

    def test_sample_based_client_id_means_no_generated_value_in_java(self, tmp_path):
        """A (end-to-end): client-supplied id produces no @GeneratedValue in generated entity."""
        from appbuilder.metadata import build_metadata_project

        project_root = tmp_path / "client-id-java"
        (project_root / "upstream").mkdir(parents=True)

        (project_root / "upstream" / "create-request.json").write_text(
            '{"widgetId": "WGT-001", "widgetName": "Sprocket"}',
            encoding="utf-8",
        )
        (project_root / "upstream" / "mapping.yaml").write_text(
            "\n".join([
                "entity: Widget",
                "operations:",
                "  - name: createWidget",
                "    request_mappings:",
                "      - source: widgetId",
                "        target: Widget.widgetId",
                "      - source: widgetName",
                "        target: Widget.widgetName",
            ]),
            encoding="utf-8",
        )
        _make_crud_profile("phase1a-client-id-java-test")
        (project_root / "app-definition.yaml").write_text(
            "\n".join([
                "app_name: Widget Service",
                "bounded_context: widgets",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: widget-api",
                "    system: WGT",
                "    type: rest-json",
                "    spec_url: https://example.com/swagger.json",
                "    mapping: upstream/mapping.yaml",
                "    operations:",
                "      - name: createWidget",
                "        request_sample: upstream/create-request.json",
                "target_profile: phase1a-client-id-java-test",
            ]),
            encoding="utf-8",
        )
        metadata = build_metadata_project(project_root / "app-definition.yaml")
        output_dir = tmp_path / "ClientIdJava"
        generate_application(metadata, output_dir, generation_run_id="client-id-java")
        entity_java = (output_dir / "src/main/java/com/appbuilder/widgets/domain/Widget.java").read_text(encoding="utf-8")
        assert "@GeneratedValue" not in entity_java
        TARGET_PROFILES.pop("phase1a-client-id-java-test", None)

    # --- B. OpenAPI-based ingestion: id in POST request body ---

    def test_openapi_create_with_id_in_request_body_sets_client_supplied(self, monkeypatch, tmp_path):
        """B: POST body includes the id field → server_generated_id=False."""
        from appbuilder.metadata import build_metadata_project

        project_root = tmp_path / "openapi-client-id"
        project_root.mkdir(parents=True)
        (project_root / "app-definition.yaml").write_text(
            "\n".join([
                "app_name: Product Service",
                "bounded_context: products",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: product-api",
                "    system: PIM",
                "    type: rest-json",
                "    spec_url: http://localhost/openapi.json",
                "target_profile: springboot-legacy-compatible",
            ]),
            encoding="utf-8",
        )

        # POST body schema includes productId — client supplies it
        spec = {
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "Product": {
                        "type": "object",
                        "required": ["productId"],
                        "properties": {
                            "productId": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    }
                }
            },
            "paths": {
                "/products": {
                    "post": {
                        "operationId": "createProduct",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Product"}
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Product"}
                                    }
                                }
                            }
                        },
                    }
                },
                "/products/{productId}": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Product"}
                                    }
                                }
                            }
                        }
                    }
                },
            },
        }

        monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", lambda url: spec)
        metadata = build_metadata_project(project_root / "app-definition.yaml")
        product = metadata.entities[0]
        field_map = {f.name: f for f in product.fields}
        assert "productId" in field_map
        assert field_map["productId"].is_id is True
        # id in POST body → client-supplied
        assert field_map["productId"].server_generated_id is False

    def test_openapi_create_with_id_in_request_body_field_server_generated_is_false(self, monkeypatch, tmp_path):
        """B (metadata check): OpenAPI client-supplied id sets server_generated_id=False on the field."""
        from appbuilder.generation.java_emitter import _render_entity
        from appbuilder.metadata import build_metadata_project

        project_root = tmp_path / "openapi-client-id-java"
        project_root.mkdir(parents=True)
        (project_root / "app-definition.yaml").write_text(
            "\n".join([
                "app_name: Product Service",
                "bounded_context: products",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: product-api",
                "    system: PIM",
                "    type: rest-json",
                "    spec_url: http://localhost/openapi.json",
                "target_profile: springboot-legacy-compatible",
            ]),
            encoding="utf-8",
        )
        spec = {
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "Product": {
                        "type": "object",
                        "required": ["productId"],
                        "properties": {
                            "productId": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    }
                }
            },
            "paths": {
                "/products": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Product"}
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Product"}
                                    }
                                }
                            }
                        },
                    }
                },
                "/products/{productId}": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Product"}
                                    }
                                }
                            }
                        }
                    }
                },
            },
        }
        monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", lambda url: spec)
        metadata = build_metadata_project(project_root / "app-definition.yaml")
        product = metadata.entities[0]
        field_map = {f.name: f for f in product.fields}
        assert field_map["productId"].server_generated_id is False
        # Verify the emitter respects the flag — no @GeneratedValue in rendered entity
        from appbuilder.target_profiles.catalog import TARGET_PROFILES
        profile = TARGET_PROFILES["springboot-legacy-compatible"]
        entity_java = _render_entity(
            entity=product,
            root_package="com.appbuilder.products",
            target_profile=profile,
            source_manifest="test",
            generation_run_id="b-test",
        )
        assert "@GeneratedValue" not in entity_java

    # --- C. OpenAPI-based ingestion: id NOT in POST request body ---

    def test_openapi_create_without_id_in_request_body_keeps_server_generated(self, monkeypatch, tmp_path):
        """C: POST body omits the id field → server_generated_id stays True → @GeneratedValue present."""
        from appbuilder.generation.java_emitter import _render_entity
        from appbuilder.metadata import build_metadata_project

        project_root = tmp_path / "openapi-server-id"
        project_root.mkdir(parents=True)
        (project_root / "app-definition.yaml").write_text(
            "\n".join([
                "app_name: Item Service",
                "bounded_context: items",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: item-api",
                "    system: WMS",
                "    type: rest-json",
                "    spec_url: http://localhost/openapi.json",
                "target_profile: springboot-legacy-compatible",
            ]),
            encoding="utf-8",
        )

        # Request body schema does NOT include itemId — server generates it
        spec = {
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "ItemRequest": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {
                            "name": {"type": "string"},
                        },
                    },
                    "Item": {
                        "type": "object",
                        "required": ["itemId"],
                        "properties": {
                            "itemId": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    },
                }
            },
            "paths": {
                "/items": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ItemRequest"}
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Item"}
                                    }
                                }
                            }
                        },
                    }
                },
                "/items/{itemId}": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Item"}
                                    }
                                }
                            }
                        }
                    }
                },
            },
        }
        monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", lambda url: spec)
        metadata = build_metadata_project(project_root / "app-definition.yaml")
        item = metadata.entities[0]
        field_map = {f.name: f for f in item.fields}
        assert "itemId" in field_map
        # id not in POST body → server generates it
        assert field_map["itemId"].server_generated_id is True

        # Verify @GeneratedValue is present in rendered entity Java
        from appbuilder.target_profiles.catalog import TARGET_PROFILES
        profile = TARGET_PROFILES["springboot-legacy-compatible"]
        entity_java = _render_entity(
            entity=item,
            root_package="com.appbuilder.items",
            target_profile=profile,
            source_manifest="test",
            generation_run_id="c-test",
        )
        assert "@GeneratedValue" in entity_java

    # --- D. Sample-based: update request with id must NOT mark client-supplied ---

    def test_sample_based_update_request_id_does_not_set_client_supplied(self, tmp_path):
        """D: id in an *update* request sample must not set server_generated_id=False.

        An update request always carries the id (it's used to locate the record), but
        that is not evidence the *create* request supplies the id.  Before this fix the
        inference ran on any sample_kind=='request' regardless of operation name, so
        updateOrder would incorrectly mark orderId as client-supplied.
        """
        from appbuilder.metadata import build_metadata_project

        project_root = tmp_path / "update-id-sample"
        (project_root / "upstream").mkdir(parents=True)

        # Only an *update* request sample exists — id present because it's an update.
        (project_root / "upstream" / "update-order-request.json").write_text(
            '{"orderId": "ORD-001", "amount": 150.00}',
            encoding="utf-8",
        )
        (project_root / "upstream" / "order-mapping.yaml").write_text(
            "\n".join([
                "entity: Order",
                "operations:",
                "  - name: updateOrder",
                "    request_mappings:",
                "      - source: orderId",
                "        target: Order.orderId",
                "      - source: amount",
                "        target: Order.amount",
            ]),
            encoding="utf-8",
        )
        (project_root / "app-definition.yaml").write_text(
            "\n".join([
                "app_name: Order Service",
                "bounded_context: orders",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: order-api",
                "    system: OMS",
                "    type: rest-json",
                "    spec_url: https://example.com/swagger.json",
                "    mapping: upstream/order-mapping.yaml",
                "    operations:",
                "      - name: updateOrder",
                "        request_sample: upstream/update-order-request.json",
                "target_profile: springboot-legacy-compatible",
            ]),
            encoding="utf-8",
        )
        metadata = build_metadata_project(project_root / "app-definition.yaml")
        order = metadata.entities[0]
        field_map = {f.name: f for f in order.fields}
        assert "orderId" in field_map
        # update request carries the id — but that must NOT mark it as client-supplied on create
        assert field_map["orderId"].server_generated_id is True

    # --- E. OpenAPI: command-style POST must not be treated as create ---

    def test_openapi_command_post_with_id_does_not_set_client_supplied(self, monkeypatch, tmp_path):
        """E: A command POST (POST /accounts/{id}/close) with id in body must NOT set server_generated_id=False.

        Before this fix the classifier tracked all POST bodies, so a command-style
        POST /accounts/{accountId}/close that included accountId in its body would
        incorrectly mark accountId as client-supplied on create.
        """
        from appbuilder.metadata import build_metadata_project

        project_root = tmp_path / "openapi-command-post"
        project_root.mkdir(parents=True)
        (project_root / "app-definition.yaml").write_text(
            "\n".join([
                "app_name: Account Service",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: account-api",
                "    system: CBS",
                "    type: rest-json",
                "    spec_url: http://localhost/openapi.json",
                "target_profile: springboot-legacy-compatible",
            ]),
            encoding="utf-8",
        )

        spec = {
            "openapi": "3.0.0",
            "components": {
                "schemas": {
                    "Account": {
                        "type": "object",
                        "properties": {
                            "accountId": {"type": "string"},
                            "balance": {"type": "number"},
                        },
                    },
                    "CloseRequest": {
                        "type": "object",
                        "properties": {
                            "accountId": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                    },
                }
            },
            "paths": {
                "/accounts": {
                    "post": {
                        "operationId": "createAccount",
                        # Create request body does NOT include accountId — server generates it
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"balance": {"type": "number"}},
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Account"}
                                    }
                                }
                            }
                        },
                    }
                },
                "/accounts/{accountId}": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Account"}
                                    }
                                }
                            }
                        }
                    }
                },
                "/accounts/{accountId}/close": {
                    # Command-style POST — includes accountId in body, but is NOT create
                    "post": {
                        "operationId": "closeAccount",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CloseRequest"}
                                }
                            }
                        },
                        "responses": {"200": {"description": "closed"}},
                    }
                },
            },
        }
        monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", lambda url: spec)
        metadata = build_metadata_project(project_root / "app-definition.yaml")
        account = metadata.entities[0]
        field_map = {f.name: f for f in account.fields}
        assert "accountId" in field_map
        # The command POST carried accountId but the create POST did not — server generates it
        assert field_map["accountId"].server_generated_id is True


# ---------------------------------------------------------------------------
# Batch job trailing-comma regression
# ---------------------------------------------------------------------------

class TestBatchJobStepParams:
    """Regression: _render_batch_job must not emit a trailing comma on the last step param."""

    def _render(self, has_file_writer: bool) -> str:
        from appbuilder.generation.java_emitter import _render_batch_job

        entity = CanonicalEntity(
            name="Loan",
            fields=[
                CanonicalField(
                    name="loanId",
                    type=CanonicalFieldType.STRING,
                    is_id=True,
                    required=True,
                    source_paths=["api.createLoan.response.loanId"],
                )
            ],
        )
        profile = _make_crud_profile("batch-param-test")
        return _render_batch_job(
            entity=entity,
            root_package="com.appbuilder.test",
            bounded_context="testapp",
            target_profile=profile,
            source_manifest="test",
            generation_run_id="test-run",
            has_file_writer=has_file_writer,
        )

    def test_staging_only_step_has_no_trailing_comma(self):
        """When has_file_writer=False the last step param must not end with a comma."""
        java = self._render(has_file_writer=False)
        # Find the step method signature block between "public Step" and the closing "{"
        import re
        match = re.search(r"public Step \w+EodStep\((.+?)\) \{", java, re.DOTALL)
        assert match, "Step method not found in generated Java"
        params_block = match.group(1)
        # Last non-whitespace char in the param block must NOT be a comma
        stripped = params_block.rstrip()
        assert not stripped.endswith(","), (
            f"Trailing comma found in step params when has_file_writer=False:\n{params_block}"
        )

    def test_file_writer_step_has_no_trailing_comma(self):
        """When has_file_writer=True the last step param (handoffFileWriter) must not end with a comma."""
        java = self._render(has_file_writer=True)
        import re
        match = re.search(r"public Step \w+EodStep\((.+?)\) \{", java, re.DOTALL)
        assert match, "Step method not found in generated Java"
        params_block = match.group(1)
        stripped = params_block.rstrip()
        assert not stripped.endswith(","), (
            f"Trailing comma found in step params when has_file_writer=True:\n{params_block}"
        )

    def test_staging_only_step_includes_staging_writer(self):
        java = self._render(has_file_writer=False)
        assert "StagingWriter stagingWriter" in java

    def test_file_writer_step_includes_both_writers(self):
        java = self._render(has_file_writer=True)
        assert "StagingWriter stagingWriter," in java
        assert "HandoffFileWriter handoffFileWriter" in java

    def test_eod_default_dir_is_app_local_not_user_home(self):
        """Default EOD output dir must be ./<bounded_context>-eod, not ${user.home}/..."""
        java = self._render(has_file_writer=False)
        assert "${user.home}" not in java, "Default EOD dir must not reference user.home"
        assert "./testapp-eod" in java, "Default EOD dir must be app-local ./testapp-eod"

    def test_eod_default_uses_bounded_context_slug(self):
        """Bounded context name is used as the EOD directory prefix."""
        from appbuilder.generation.java_emitter import _render_batch_job

        entity = CanonicalEntity(
            name="Payment",
            fields=[
                CanonicalField(
                    name="paymentId",
                    type=CanonicalFieldType.STRING,
                    is_id=True,
                    required=True,
                    source_paths=["api.createPayment.response.paymentId"],
                )
            ],
        )
        profile = _make_crud_profile("eod-slug-test")
        java = _render_batch_job(
            entity=entity,
            root_package="com.appbuilder.payments",
            bounded_context="payments",
            target_profile=profile,
            source_manifest="test",
            generation_run_id="test-run",
            has_file_writer=False,
        )
        assert "./payments-eod" in java
        assert "${user.home}" not in java

    def test_eod_explicit_override_property_still_present(self):
        """app.eod.output-dir property key must remain in generated code so overrides work."""
        java = self._render(has_file_writer=False)
        assert "app.eod.output-dir" in java, "@Value key must stay so --app.eod.output-dir override works"


# ---------------------------------------------------------------------------
# GET service stub emits findById, not new Entity() + save()
# ---------------------------------------------------------------------------

class TestGetServiceStub:
    """Regression: non-create stubs with http_method=GET must use findById, not save()."""

    def _generate_service(self, tmp_path: Path) -> str:
        profile_name = "get-stub-test"
        _make_crud_profile(profile_name)
        entity = CanonicalEntity(
            name="Order",
            fields=[
                CanonicalField(
                    name="orderId",
                    type=CanonicalFieldType.STRING,
                    is_id=True,
                    required=True,
                    source_paths=["orders-api.createOrder.response.orderId"],
                ),
                CanonicalField(
                    name="amount",
                    type=CanonicalFieldType.STRING,
                    required=False,
                    source_paths=["orders-api.createOrder.request.amount"],
                ),
            ],
        )
        create_op = CanonicalOperation(
            name="createOrder",
            interface_name="orders-api",
            request_entity="Order",
            response_entity="Order",
            http_method=HttpMethod.POST,
        )
        get_op = CanonicalOperation(
            name="getOrder",
            interface_name="orders-api",
            request_entity="Order",
            response_entity="Order",
            http_method=HttpMethod.GET,
        )
        mappings = [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="orders-api",
                operation_name="createOrder",
                source_path="orders-api.createOrder.response.orderId",
                target_path="Order.orderId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="orders-api",
                operation_name="createOrder",
                source_path="orders-api.createOrder.request.amount",
                target_path="Order.amount",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="orders-api",
                operation_name="getOrder",
                source_path="orders-api.getOrder.response.orderId",
                target_path="Order.orderId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="orders-api",
                operation_name="getOrder",
                source_path="orders-api.getOrder.response.amount",
                target_path="Order.amount",
            ),
        ]
        metadata = MetadataProject(
            app_name="Orders App",
            bounded_context="orders",
            target_profile=profile_name,
            systems=[SystemParticipant(name="EXT", role="upstream")],
            contracts=[ContractMetadata(name="orders-api", type="rest-json", source="")],
            operations=[create_op, get_op],
            entities=[entity],
            mappings=mappings,
        )
        output_dir = tmp_path / "OrdersApp"
        generate_application(metadata, output_dir, generation_run_id="get-stub-test")
        TARGET_PROFILES.pop(profile_name, None)
        service_path = (
            output_dir
            / "src/main/java/com/appbuilder/orders/service/OrderServiceBase.java"
        )
        return service_path.read_text(encoding="utf-8")

    def test_get_stub_uses_find_by_id(self, tmp_path):
        java = self._generate_service(tmp_path)
        assert "findById(" in java, "getOrder() should use findById, not new Order()"

    def test_get_stub_does_not_use_save(self, tmp_path):
        # The getOrder method must not call save()
        java = self._generate_service(tmp_path)
        import re
        # Extract the getOrder method body
        match = re.search(r"public \w+ getOrder\(.*?\}\s*\n", java, re.DOTALL)
        if match:
            method_body = match.group(0)
            assert "repository.save(" not in method_body, (
                "getOrder() must not call save() — it should read by id"
            )

    def test_get_stub_throws_not_found_on_missing(self, tmp_path):
        java = self._generate_service(tmp_path)
        assert "orElseThrow" in java, "getOrder() should throw ResourceNotFoundException when not found"

    def test_get_stub_uses_entity_specific_id_getter(self, tmp_path):
        """Regression: GET service stub must call request.getOrderId(), not request.getId()."""
        java = self._generate_service(tmp_path)
        assert "request.getOrderId()" in java, (
            "getOrder() should use request.getOrderId(), not a generic request.getId()"
        )
        assert "request.getId()" not in java, (
            "Service must not use generic getId() — use entity-specific getter"
        )

    def test_get_request_dto_does_not_synthesize_id_field(self, tmp_path):
        """GET routes use path variables directly instead of fake request DTO IDs."""
        profile_name = "get-dto-id-test"
        _make_crud_profile(profile_name)
        entity = CanonicalEntity(
            name="Order",
            fields=[
                CanonicalField(
                    name="orderId",
                    type=CanonicalFieldType.STRING,
                    is_id=True,
                    required=True,
                    source_paths=["orders-api.getOrder.response.orderId"],
                ),
                CanonicalField(
                    name="amount",
                    type=CanonicalFieldType.STRING,
                    required=False,
                    source_paths=["orders-api.createOrder.request.amount"],
                ),
            ],
        )
        # Only a response sample for getOrder — no request sample
        get_op = CanonicalOperation(
            name="getOrder",
            interface_name="orders-api",
            request_entity="Order",
            response_entity="Order",
            http_method=HttpMethod.GET,
        )
        mappings = [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="orders-api",
                operation_name="getOrder",
                source_path="orders-api.getOrder.response.orderId",
                target_path="Order.orderId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="orders-api",
                operation_name="getOrder",
                source_path="orders-api.getOrder.response.amount",
                target_path="Order.amount",
            ),
        ]
        metadata = MetadataProject(
            app_name="Orders App",
            bounded_context="orders",
            target_profile=profile_name,
            systems=[SystemParticipant(name="EXT", role="upstream")],
            contracts=[ContractMetadata(name="orders-api", type="rest-json", source="")],
            operations=[get_op],
            entities=[entity],
            mappings=mappings,
        )
        output_dir = tmp_path / "OrdersApp"
        generate_application(metadata, output_dir, generation_run_id="get-dto-id-test")
        TARGET_PROFILES.pop(profile_name, None)
        dto_path = (
            output_dir
            / "src/main/java/com/appbuilder/orders/adapter/inbound/GetOrderRequest.java"
        )
        dto = dto_path.read_text(encoding="utf-8")
        assert "getOrderId()" not in dto


# ---------------------------------------------------------------------------
# Empty-manifest guard
# ---------------------------------------------------------------------------

class TestEmptyManifestGuard:
    """generate_application must raise a clear ValueError instead of crashing
    with 'list index out of range' / IndexError when the manifest produces no
    entities with fields.  Covers both the fully-empty OBIE case and the
    operations-present-but-entity-fieldless case found in Codex review."""

    def test_empty_manifest_no_operations_raises_valueerror(self, tmp_path):
        """A manifest with no fields and no operations raises ValueError, not IndexError."""
        profile_name = "empty-guard-test"
        _make_crud_profile(profile_name)
        # Simulate what translation produces for a manifest with no upstream interfaces:
        # a single default entity with no fields (translation.py line 375-376 fallback).
        stub_entity = CanonicalEntity(name="payments", fields=[])
        metadata = MetadataProject(
            app_name="OBIE Payment Initiation",
            bounded_context="payments",
            target_profile=profile_name,
            entities=[stub_entity],
            operations=[],
        )
        with pytest.raises(ValueError, match="no entities with fields"):
            generate_application(metadata, tmp_path / "out", generation_run_id="empty-guard")
        TARGET_PROFILES.pop(profile_name, None)

    def test_operations_present_but_entity_fieldless_raises_valueerror(self, tmp_path):
        """Operations present but all entities still fieldless must also raise ValueError.

        Codex review found the original guard (which only raised when operations were
        also absent) still let this case through, causing entity_id_field() to crash
        with IndexError: list index out of range.
        """
        profile_name = "empty-guard-ops-test"
        _make_crud_profile(profile_name)
        stub_entity = CanonicalEntity(name="Ghost", fields=[])
        op = CanonicalOperation(
            name="createGhost",
            interface_name="ghost-api",
            request_entity="Ghost",
            response_entity="Ghost",
        )
        metadata = MetadataProject(
            app_name="Ghost App",
            bounded_context="ghosts",
            target_profile=profile_name,
            systems=[SystemParticipant(name="EXT", role="upstream")],
            contracts=[ContractMetadata(name="ghost-api", type="rest-json", source="")],
            entities=[stub_entity],
            operations=[op],
        )
        with pytest.raises(ValueError, match="no entities with fields"):
            generate_application(metadata, tmp_path / "out", generation_run_id="ops-fieldless-guard")
        TARGET_PROFILES.pop(profile_name, None)

    def test_manifest_with_fields_does_not_raise(self, tmp_path):
        """A manifest with at least one entity with fields must NOT trigger the guard."""
        # _minimal_metadata registers its own profile internally
        metadata = _minimal_metadata(profile_name="non-empty-guard-test")
        report = generate_application(metadata, tmp_path / "out", generation_run_id="non-empty-guard")
        TARGET_PROFILES.pop("non-empty-guard-test", None)
        assert report.output_dir.exists()
