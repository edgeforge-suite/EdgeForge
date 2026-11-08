import pytest

from appbuilder.ingestion.openapi_classifier import (
    classify_openapi_schemas,
    extract_entity_fields,
    ingest_openapi_entities,
    ingest_openapi_operations,
    openapi_type_to_canonical_type,
    required_nullable_request_fields,
    summarize_openapi_assessment,
)


def test_classify_infrastructure_schemas() -> None:
    spec = {
        "components": {
            "schemas": {
                "PageCustomerResponse": {"type": "object"},
                "PageableObject": {"type": "object"},
                "SortObject": {"type": "object"},
            }
        }
    }

    classifications = classify_openapi_schemas(spec)

    assert classifications == {
        "PageCustomerResponse": "infrastructure",
        "PageableObject": "infrastructure",
        "SortObject": "infrastructure",
    }


def test_classify_dto_schemas() -> None:
    spec = {
        "components": {
            "schemas": {
                "CreateCustomerRequest": {"type": "object"},
                "CustomerResponse": {"type": "object"},
                "UpdateAccountRequest": {"type": "object"},
            }
        }
    }

    classifications = classify_openapi_schemas(spec)

    assert classifications == {
        "CreateCustomerRequest": "dto",
        "CustomerResponse": "dto",
        "UpdateAccountRequest": "dto",
    }


def test_classify_entity_schemas() -> None:
    spec = {
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "properties": {"customerId": {"type": "string"}},
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

    classifications = classify_openapi_schemas(spec)

    assert classifications["Customer"] == "entity"


def test_extract_entity_fields_types() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "createdAt": {"type": "string", "format": "date-time"},
                "balance": {"type": "number"},
            },
        },
    )

    assert [field.type.value for field in fields] == [
        "integer",
        "string",
        "datetime",
        "decimal",
    ]


def test_openapi_type_to_canonical_type_handles_nullable_type_lists() -> None:
    assert openapi_type_to_canonical_type(["string", "null"], None).value == "string"
    assert openapi_type_to_canonical_type(["string", "null"], "date-time").value == "datetime"
    assert openapi_type_to_canonical_type(["number", "null"], None).value == "decimal"
    assert openapi_type_to_canonical_type(["null"], None).value == "string"


def test_extract_entity_fields_handles_nullable_type_lists() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "properties": {
                "nickname": {"type": ["string", "null"]},
                "creditLimit": {"type": ["number", "null"]},
            },
        },
    )

    field_lookup = {field.name: field for field in fields}
    assert field_lookup["nickname"].type.value == "string"
    assert field_lookup["creditLimit"].type.value == "decimal"


def test_extract_entity_fields_preserves_scalar_ref_constraints() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "required": ["customerLabel"],
            "properties": {
                "customerLabel": {"$ref": "#/components/schemas/CustomerLabel"},
            },
        },
        schemas={
            "CustomerLabel": {
                "type": "string",
                "format": "uuid",
                "maxLength": 12,
                "enum": ["PRIMARY", "SECONDARY"],
            }
        },
    )

    assert len(fields) == 1
    field = fields[0]
    assert field.name == "customerLabel"
    assert field.type.value == "string"
    assert field.required is True
    assert field.format == "uuid"
    assert field.max_length == 12
    assert field.allowed_values == ["PRIMARY", "SECONDARY"]


def test_extract_entity_fields_composes_openapi_31_ref_siblings_through_chain() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "required": ["customerLabel"],
            "properties": {
                "customerLabel": {
                    "$ref": "#/components/schemas/CustomerLabelAlias",
                    "maxLength": 12,
                },
            },
        },
        schemas={
            "CustomerLabelAlias": {"$ref": "#/components/schemas/CustomerLabel"},
            "CustomerLabel": {"type": "string", "maxLength": 20},
        },
        ref_siblings_apply=True,
    )

    assert len(fields) == 1
    assert fields[0].max_length == 12


def test_extract_entity_fields_composes_scalar_all_of_through_ref_chain() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "required": ["customerLabel"],
            "properties": {
                "customerLabel": {
                    "$ref": "#/components/schemas/CustomerLabelAlias",
                },
            },
        },
        schemas={
            "CustomerLabelAlias": {"$ref": "#/components/schemas/CustomerLabel"},
            "CustomerLabel": {
                "allOf": [
                    {"$ref": "#/components/schemas/CustomerLabelBase"},
                    {"maxLength": 12},
                ]
            },
            "CustomerLabelBase": {"type": "string", "maxLength": 20},
        },
        ref_siblings_apply=True,
    )

    assert len(fields) == 1
    field = fields[0]
    assert field.name == "customerLabel"
    assert field.type.value == "string"
    assert field.required
    assert field.max_length == 12


def test_extract_entity_fields_allows_non_request_all_of_pattern() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "properties": {
                "auditRef": {"$ref": "#/components/schemas/AuditRef"},
            },
        },
        schemas={
            "AuditRef": {
                "allOf": [
                    {"type": "string"},
                    {"pattern": "^[A-Z0-9-]+$"},
                ]
            }
        },
        ref_siblings_apply=True,
    )

    assert [field.name for field in fields] == ["auditRef"]
    assert fields[0].type.value == "string"


def test_extract_entity_fields_flattens_required_object_all_of_inheritance() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "required": ["address"],
            "properties": {
                "address": {"$ref": "#/components/schemas/Address"},
            },
        },
        schemas={
            "Address": {
                "allOf": [
                    {"$ref": "#/components/schemas/AddressBase"},
                    {
                        "type": "object",
                        "required": ["postalCode"],
                        "properties": {
                            "postalCode": {"type": "string", "maxLength": 12},
                        },
                    },
                ]
            },
            "AddressBase": {
                "type": "object",
                "required": ["lineOne"],
                "properties": {"lineOne": {"type": "string", "maxLength": 80}},
            },
        },
        ref_siblings_apply=True,
        fail_on_unrepresentable_required=True,
    )

    fields_by_name = {field.name: field for field in fields}
    assert fields_by_name["addressLineOne"].required
    assert fields_by_name["addressLineOne"].max_length == 80
    assert fields_by_name["addressPostalCode"].required
    assert fields_by_name["addressPostalCode"].max_length == 12


def test_extract_entity_fields_ignores_openapi_30_ref_constraint_siblings() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "properties": {
                "customerLabel": {
                    "$ref": "#/components/schemas/CustomerLabel",
                    "maxLength": 12,
                },
            },
        },
        schemas={"CustomerLabel": {"type": "string", "maxLength": 20}},
        ref_siblings_apply=False,
    )

    assert len(fields) == 1
    assert fields[0].max_length == 20


def test_extract_entity_fields_rejects_unsupported_openapi_31_ref_sibling() -> None:
    with pytest.raises(ValueError, match="sibling constraint 'pattern'"):
        extract_entity_fields(
            "Customer",
            {
                "type": "object",
                "properties": {
                    "customerLabel": {
                        "$ref": "#/components/schemas/CustomerLabel",
                        "pattern": "^[A-Z]+$",
                    },
                },
            },
            schemas={"CustomerLabel": {"type": "string", "maxLength": 20}},
            ref_siblings_apply=True,
        )


def test_extract_entity_fields_rejects_cyclic_local_ref_chain() -> None:
    with pytest.raises(ValueError, match="Cyclic local OpenAPI schema reference"):
        extract_entity_fields(
            "Customer",
            {
                "type": "object",
                "properties": {
                    "customerLabel": {"$ref": "#/components/schemas/CustomerLabelA"},
                },
            },
            schemas={
                "CustomerLabelA": {"$ref": "#/components/schemas/CustomerLabelB"},
                "CustomerLabelB": {"$ref": "#/components/schemas/CustomerLabelA"},
            },
            ref_siblings_apply=True,
        )


def test_extract_entity_fields_resolves_chained_ref_inside_all_of() -> None:
    fields = extract_entity_fields(
        "Customer",
        {"allOf": [{"$ref": "#/components/schemas/CustomerExtrasAlias"}]},
        schemas={
            "CustomerExtrasAlias": {"$ref": "#/components/schemas/CustomerExtras"},
            "CustomerExtras": {
                "type": "object",
                "required": ["customerLabel"],
                "properties": {"customerLabel": {"type": "string"}},
            },
        },
        ref_siblings_apply=True,
    )

    assert [field.name for field in fields] == ["customerLabel"]
    assert fields[0].required


def test_required_nullable_request_fields_honors_boolean_false_schemas() -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/customers": {
                "post": {
                    "operationId": "createCustomer",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["customerLabel"],
                                    "properties": {
                                        "customerLabel": {
                                            "allOf": [
                                                {"type": ["string", "null"]},
                                                {
                                                    "$ref": "#/components/schemas/RejectEverything"
                                                },
                                            ]
                                        }
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Accepted"}},
                }
            }
        },
        "components": {"schemas": {"RejectEverything": False}},
    }

    assert required_nullable_request_fields(spec) == []


@pytest.mark.parametrize(
    ("openapi_version", "nullable_schema", "expected"),
    [
        (
            "3.0.3",
            {"type": "string", "nullable": True},
            [("createCustomer", "customerLabel")],
        ),
        ("3.1.0", {"type": ["string", "null"]}, []),
    ],
)
def test_required_nullable_request_fields_applies_ref_siblings_by_dialect(
    openapi_version: str,
    nullable_schema: dict,
    expected: list[tuple[str, str]],
) -> None:
    spec = {
        "openapi": openapi_version,
        "paths": {
            "/customers": {
                "post": {
                    "operationId": "createCustomer",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["customerLabel"],
                                    "properties": {
                                        "customerLabel": {
                                            "$ref": "#/components/schemas/CustomerLabelAlias",
                                            "type": "string",
                                        }
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Accepted"}},
                }
            }
        },
        "components": {
            "schemas": {
                "CustomerLabelAlias": {
                    "$ref": "#/components/schemas/NullableCustomerLabel"
                },
                "NullableCustomerLabel": nullable_schema,
            }
        },
    }

    assert required_nullable_request_fields(spec) == expected


def test_required_nullable_request_fields_does_not_flatten_any_of_properties() -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/customers": {
                "post": {
                    "operationId": "createCustomer",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["customerLabel"],
                                    "properties": {
                                        "customerLabel": {"type": "string"}
                                    },
                                    "anyOf": [
                                        {
                                            "type": "object",
                                            "required": ["nullableExtra"],
                                            "properties": {
                                                "nullableExtra": {
                                                    "type": ["string", "null"]
                                                }
                                            },
                                        }
                                    ],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Accepted"}},
                }
            }
        },
    }

    assert required_nullable_request_fields(spec) == []


def test_extract_entity_fields_required() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "required": ["customerId", "name"],
            "properties": {
                "customerId": {"type": "string"},
                "name": {"type": "string"},
                "email": {"type": "string"},
            },
        },
    )
    field_lookup = {field.name: field for field in fields}

    assert field_lookup["customerId"].required is True
    assert field_lookup["name"].required is True
    assert field_lookup["email"].required is False


def test_extract_entity_fields_id_detection() -> None:
    fields = extract_entity_fields(
        "Customer",
        {
            "type": "object",
            "properties": {
                "customerId": {"type": "string"},
                "name": {"type": "string"},
            },
        },
    )

    assert fields[0].is_id is True
    assert fields[1].is_id is False


def test_ingest_openapi_entities_derives_domain_entity_from_dto_schemas() -> None:
    spec = {
        "components": {
            "schemas": {
                "CreateCustomerRequest": {
                    "type": "object",
                    "required": ["customerName"],
                    "properties": {
                        "customerName": {"type": "string", "maxLength": 50},
                        "email": {"type": "string"},
                    },
                },
                "CustomerResponse": {
                    "type": "object",
                    "properties": {
                        "customerId": {"type": "string"},
                        "customerName": {"type": "string", "maxLength": 50},
                        "createdAt": {"type": "string", "format": "date-time"},
                    },
                },
            }
        },
        "paths": {
            "/customers": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/CreateCustomerRequest"
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CustomerResponse"}
                                }
                            }
                        }
                    },
                }
            }
        },
    }

    entities = ingest_openapi_entities(spec, "crm-api")

    assert len(entities) == 1
    assert entities[0].name == "Customer"
    field_lookup = {field.name: field for field in entities[0].fields}
    assert field_lookup["customerId"].is_id is True
    assert field_lookup["customerName"].required is True
    assert field_lookup["createdAt"].type.value == "datetime"


def test_assessment_treats_post_customer_as_crud_not_complex() -> None:
    spec = {
        "info": {"title": "CRM API", "version": "1.0"},
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "properties": {
                        "customerId": {"type": "string"},
                        "customerName": {"type": "string"},
                    },
                }
            }
        },
        "paths": {
            "/customers": {
                "post": {
                    "operationId": "postCustomer",
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
            }
        },
    }

    assessment = summarize_openapi_assessment(spec, "http://fake/v3/api-docs")

    assert assessment["summary"]["coverage"].startswith("~90%")


def test_assessment_id_field_is_none_when_no_field_is_marked_id() -> None:
    spec = {
        "info": {"title": "Reference API", "version": "1.0"},
        "components": {
            "schemas": {
                "Country": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "region": {"type": "string"},
                    },
                }
            }
        },
        "paths": {
            "/countries": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Country"}
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    assessment = summarize_openapi_assessment(spec, "http://fake/v3/api-docs")

    assert assessment["domain_entities"][0]["id_field"] is None


def test_ingest_openapi_entities_extracts_fields_from_allof_schema() -> None:
    """classify_openapi_schemas now promotes allOf schemas to entity, but
    ingest_openapi_entities must also extract their fields — previously
    extract_entity_fields() only read top-level properties and returned []
    for allOf schemas, causing ingest_openapi_entities() to return no entities.

    Spring Boot / Springdoc uses allOf for inheritance:
      Customer:
        allOf:
          - $ref: '#/components/schemas/BaseEntity'
          - type: object
            properties: {customerId: ..., name: ...}
            required: [customerId]
    """
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/customers/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "*/*": {
                                    "schema": {"$ref": "#/components/schemas/Customer"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "BaseEntity": {
                    "type": "object",
                    "properties": {"createdAt": {"type": "string", "format": "date-time"}},
                },
                "Customer": {
                    "allOf": [
                        {"$ref": "#/components/schemas/BaseEntity"},
                        {
                            "type": "object",
                            "required": ["customerId"],
                            "properties": {
                                "customerId": {"type": "string"},
                                "name": {"type": "string"},
                            },
                        },
                    ]
                },
            }
        },
    }

    entities = ingest_openapi_entities(spec, "banking-api")
    assert len(entities) == 1, "allOf schema in response ref must produce one canonical entity"
    customer = entities[0]
    assert customer.name == "Customer"
    field_names = {f.name for f in customer.fields}
    assert "customerId" in field_names, "allOf inline properties must be extracted"
    assert "name" in field_names
    assert "createdAt" in field_names, "$ref variant (BaseEntity) fields must be extracted via allOf"
    required = {f.name for f in customer.fields if f.required}
    assert "customerId" in required, "required list inside allOf variant must be respected"


def test_paginated_response_wrapper_fields_do_not_pollute_entity_inference() -> None:
    spec = {
        "openapi": "3.0.0",
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "customerName": {"type": "string"},
                    },
                }
            }
        },
        "paths": {
            "/customers": {
                "get": {
                    "operationId": "listCustomers",
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "content": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/Customer"},
                                            },
                                            "totalElements": {"type": "integer"},
                                            "pageNumber": {"type": "integer"},
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

    entities = ingest_openapi_entities(spec, "fixture-api")

    assert len(entities) == 1
    customer_fields = {field.name for field in entities[0].fields}
    assert customer_fields == {"id", "customerName"}

    operations = ingest_openapi_operations(spec, "fixture-api")

    assert len(operations) == 1
    response_fields = {field.name for field in operations[0].response_fields}
    assert response_fields == {"id", "customerName"}


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
def test_extract_entity_fields_resolves_nested_property_references_and_all_of(
    openapi_version: str,
) -> None:
    spec = _nested_operation_spec(openapi_version)

    operations = ingest_openapi_operations(
        spec,
        "nested-api",
        fail_on_unrepresentable_required_request_fields=True,
    )

    fields = {field.name: field for field in operations[0].request_fields}
    assert list(fields) == ["envelopeRouteKey", "envelopeRecipientCode"]
    assert fields["envelopeRouteKey"].required
    assert fields["envelopeRecipientCode"].required
    assert fields["envelopeRecipientCode"].format == "uuid"
    assert fields["envelopeRecipientCode"].max_length == 12


def test_nested_reference_siblings_follow_openapi_dialect() -> None:
    results: dict[str, int | None] = {}
    for version in ("3.0.3", "3.1.0"):
        spec = _nested_operation_spec(version)
        nested_property = spec["components"]["schemas"]["Envelope"]["allOf"][1][
            "properties"
        ]["recipientCode"]
        nested_property["maxLength"] = 8
        operation = ingest_openapi_operations(
            spec,
            "nested-api",
            fail_on_unrepresentable_required_request_fields=True,
        )[0]
        field = next(
            field
            for field in operation.request_fields
            if field.name == "envelopeRecipientCode"
        )
        results[version] = field.max_length

    assert results == {"3.0.3": 12, "3.1.0": 8}


def test_nested_all_of_resolution_is_order_independent() -> None:
    first = _nested_operation_spec("3.1.0")
    second = _nested_operation_spec("3.1.0")
    second["components"]["schemas"]["RecipientCode"]["allOf"].reverse()

    first_fields = ingest_openapi_operations(
        first,
        "nested-api",
        fail_on_unrepresentable_required_request_fields=True,
    )[0].request_fields
    second_fields = ingest_openapi_operations(
        second,
        "nested-api",
        fail_on_unrepresentable_required_request_fields=True,
    )[0].request_fields

    assert [field.model_dump(mode="json") for field in first_fields] == [
        field.model_dump(mode="json") for field in second_fields
    ]


def test_nested_child_requiredness_requires_every_containing_object() -> None:
    spec = _nested_operation_spec("3.1.0")
    spec["components"]["schemas"]["Request"]["required"] = []

    fields = ingest_openapi_operations(
        spec,
        "nested-api",
        fail_on_unrepresentable_required_request_fields=True,
    )[0].request_fields

    assert fields
    assert not any(field.required for field in fields)


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
def test_required_parent_with_only_optional_children_fails_closed(
    openapi_version: str,
) -> None:
    spec = _operation_spec_with_properties(
        {
            "envelope": {
                "type": "object",
                "properties": {
                    "note": {"type": "string", "maxLength": 8},
                },
            }
        },
        required=["envelope"],
        openapi_version=openapi_version,
    )

    with pytest.raises(ValueError) as exc_info:
        ingest_openapi_operations(
            spec,
            "parent-presence-api",
            fail_on_unrepresentable_required_request_fields=True,
        )

    message = str(exc_info.value)
    assert "OpenAPI interface 'parent-presence-api'" in message
    assert "operation 'routeRequest'" in message
    assert "required field 'envelope'" in message
    assert "presence cannot be preserved after flattening" in message
    assert "all nested properties are optional" in message


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
def test_optional_parent_with_only_optional_children_remains_supported(
    openapi_version: str,
) -> None:
    spec = _operation_spec_with_properties(
        {
            "envelope": {
                "type": "object",
                "properties": {
                    "note": {"type": "string", "maxLength": 8},
                },
            }
        },
        openapi_version=openapi_version,
    )

    operation = ingest_openapi_operations(
        spec,
        "parent-presence-api",
        fail_on_unrepresentable_required_request_fields=True,
    )[0]

    assert [field.name for field in operation.request_fields] == ["envelopeNote"]
    assert not operation.request_fields[0].required
    assert operation.request_fields[0].max_length == 8


def test_crud_entity_ingestion_retains_legacy_nested_ref_and_all_of_behavior() -> None:
    spec = _crud_nested_compatibility_spec()

    entities = ingest_openapi_entities(spec, "customer-api")

    assert len(entities) == 1
    customer = entities[0]
    fields = {field.name: field for field in customer.fields}
    assert list(fields) == ["id", "preferencesCode"]
    assert fields["id"].is_id
    assert fields["preferencesCode"].required
    assert fields["preferencesCode"].type.value == "string"
    assert fields["preferencesCode"].max_length is None
    expected_warning = (
        "Field 'address' in 'Customer': deeply nested object graph (depth > 1) "
        "is not supported in Phase 1a — field skipped (requires Phase 1b relationship modeling)."
    )
    assert customer.warnings == [expected_warning, expected_warning]


@pytest.mark.parametrize(
    ("property_schema", "field_path", "reason"),
    [
        ({"type": "array", "items": {"type": "string"}}, "items", "array/collection"),
        ({"oneOf": [{"type": "string"}, {"type": "integer"}]}, "choice", "oneOf/anyOf"),
        ({"anyOf": [{"type": "string"}, {"type": "integer"}]}, "choice", "oneOf/anyOf"),
        (
            {
                "type": "object",
                "required": ["lineOne"],
                "properties": {"lineOne": {"type": "string"}},
            },
            "envelope.address",
            "deeper than one flattened level",
        ),
        (False, "blocked", "boolean"),
        ([], "malformed", "malformed"),
    ],
)
def test_required_unrepresentable_shapes_fail_with_operation_and_field_context(
    property_schema: object,
    field_path: str,
    reason: str,
) -> None:
    if "." in field_path:
        field_name = field_path.rsplit(".", 1)[-1]
        spec = _operation_spec_with_properties(
            {
                "envelope": {
                    "type": "object",
                    "required": [field_name],
                    "properties": {field_name: property_schema},
                }
            },
            required=["envelope"],
        )
    else:
        field_name = field_path
        spec = _operation_spec_with_properties(
            {field_name: property_schema},
            required=[field_name],
        )

    with pytest.raises(ValueError) as exc_info:
        ingest_openapi_operations(
            spec,
            "unsupported-api",
            fail_on_unrepresentable_required_request_fields=True,
        )

    message = str(exc_info.value)
    assert "OpenAPI interface 'unsupported-api'" in message
    assert "operation 'routeRequest'" in message
    assert f"required field '{field_path}'" in message
    assert reason in message


def test_required_name_without_property_schema_fails_closed() -> None:
    spec = _operation_spec_with_properties({}, required=["missingField"])

    with pytest.raises(ValueError) as exc_info:
        ingest_openapi_operations(
            spec,
            "missing-property-api",
            fail_on_unrepresentable_required_request_fields=True,
        )

    message = str(exc_info.value)
    assert "OpenAPI interface 'missing-property-api'" in message
    assert "operation 'routeRequest'" in message
    assert "required field 'missingField'" in message
    assert "no matching property schema" in message


def test_required_property_referencing_boolean_schema_fails_closed() -> None:
    spec = _operation_spec_with_properties(
        {"blocked": {"$ref": "#/components/schemas/Blocked"}},
        required=["blocked"],
    )
    spec["components"]["schemas"]["Blocked"] = False

    with pytest.raises(ValueError, match="required field 'blocked'.*boolean schema"):
        ingest_openapi_operations(
            spec,
            "boolean-ref-api",
            fail_on_unrepresentable_required_request_fields=True,
        )


def test_optional_and_response_unsupported_shapes_emit_stable_contextual_warnings() -> None:
    spec = _operation_spec_with_properties(
        {
            "optionalItems": {"type": "array", "items": {"type": "string"}},
            "optionalChoice": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
        },
        response_properties={
            "responseItems": {"type": "array", "items": {"type": "string"}},
        },
    )
    warnings: list[str] = []

    operations = ingest_openapi_operations(
        spec,
        "compatibility-api",
        fail_on_unrepresentable_required_request_fields=True,
        warnings_out=warnings,
    )

    assert operations[0].request_fields == []
    assert operations[0].response_fields == []
    assert warnings == [
        "OpenAPI interface 'compatibility-api' operation 'routeRequest' request: "
        "field 'optionalItems' in schema 'Request' uses an unsupported array/collection "
        "shape that requires collection-table or relationship modeling; field skipped",
        "OpenAPI interface 'compatibility-api' operation 'routeRequest' request: "
        "field 'optionalChoice' in schema 'Request' uses unsupported field-level "
        "oneOf/anyOf polymorphism; field skipped",
        "OpenAPI interface 'compatibility-api' operation 'routeRequest' response: "
        "Field 'responseItems' in 'Response': array/collection fields are not supported "
        "in Phase 1a (requires collection-table or relationship modeling) — field skipped.",
    ]


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
@pytest.mark.parametrize("failure_kind", ["missing", "cyclic", "allof-cyclic"])
def test_non_strict_nested_reference_failures_warn_for_every_operation_role(
    openapi_version: str,
    failure_kind: str,
) -> None:
    spec = _operation_spec_with_properties(
        {
            "envelope": {
                "type": "object",
                "properties": {
                    "code": {"$ref": "#/components/schemas/Code"},
                },
            }
        },
        response_properties={
            "details": {
                "type": "object",
                "properties": {
                    "code": {"$ref": "#/components/schemas/Code"},
                },
            }
        },
        openapi_version=openapi_version,
    )
    _install_reference_failure(spec, failure_kind)

    upstream_warnings: list[str] = []
    upstream = ingest_openapi_operations(
        spec,
        "upstream-api",
        fail_on_unrepresentable_required_request_fields=True,
        diagnose_nested_reference_failures=True,
        warnings_out=upstream_warnings,
    )[0]
    downstream_warnings: list[str] = []
    downstream = ingest_openapi_operations(
        spec,
        "downstream-api",
        diagnose_nested_reference_failures=True,
        warnings_out=downstream_warnings,
    )[0]

    assert upstream.request_fields == []
    assert upstream.response_fields == []
    assert downstream.request_fields == []
    assert downstream.response_fields == []
    expected_reason = (
        "does not resolve to a schema"
        if failure_kind == "missing"
        else "Cyclic local OpenAPI schema reference"
    )
    assert len(upstream_warnings) == 2
    assert "operation 'routeRequest' request" in upstream_warnings[0]
    assert "field 'envelope.code'" in upstream_warnings[0]
    assert expected_reason in upstream_warnings[0]
    assert "operation 'routeRequest' response" in upstream_warnings[1]
    assert "field 'details.code'" in upstream_warnings[1]
    assert expected_reason in upstream_warnings[1]
    assert len(downstream_warnings) == 2
    assert "operation 'routeRequest' request" in downstream_warnings[0]
    assert "field 'envelope.code'" in downstream_warnings[0]
    assert expected_reason in downstream_warnings[0]
    assert "operation 'routeRequest' response" in downstream_warnings[1]
    assert "field 'details.code'" in downstream_warnings[1]
    assert expected_reason in downstream_warnings[1]


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
@pytest.mark.parametrize("failure_kind", ["missing", "cyclic", "allof-cyclic"])
def test_required_nested_reference_failure_remains_fail_closed(
    openapi_version: str,
    failure_kind: str,
) -> None:
    spec = _operation_spec_with_properties(
        {
            "envelope": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {"$ref": "#/components/schemas/Code"},
                },
            }
        },
        required=["envelope"],
        openapi_version=openapi_version,
    )
    _install_reference_failure(spec, failure_kind)

    with pytest.raises(ValueError) as exc_info:
        ingest_openapi_operations(
            spec,
            "upstream-api",
            fail_on_unrepresentable_required_request_fields=True,
            diagnose_nested_reference_failures=True,
        )

    message = str(exc_info.value)
    assert "OpenAPI interface 'upstream-api'" in message
    assert "operation 'routeRequest'" in message
    assert "required field 'envelope.code'" in message
    assert "cannot be resolved safely" in message


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
def test_response_and_downstream_nested_resolution_preserves_legacy_metadata(
    openapi_version: str,
) -> None:
    spec = _operation_spec_with_properties(
        {
            "routeKey": {"type": "string"},
            "refEnvelope": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {"$ref": "#/components/schemas/Code"},
                },
            },
            "composedEnvelope": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {
                        "allOf": [
                            {"$ref": "#/components/schemas/Code"},
                            {"maxLength": 8},
                        ]
                    },
                },
            },
        },
        required=["routeKey", "refEnvelope", "composedEnvelope"],
        response_properties={
            "refDetails": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {"$ref": "#/components/schemas/Code"},
                },
            },
            "composedDetails": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {
                        "allOf": [
                            {"$ref": "#/components/schemas/Code"},
                            {"maxLength": 8},
                        ]
                    },
                },
            },
        },
        openapi_version=openapi_version,
    )
    spec["components"]["schemas"]["Code"] = {
        "type": "string",
        "maxLength": 12,
    }

    upstream = ingest_openapi_operations(
        spec,
        "upstream-api",
        fail_on_unrepresentable_required_request_fields=True,
        diagnose_nested_reference_failures=True,
    )[0]
    downstream = ingest_openapi_operations(
        spec,
        "downstream-api",
        diagnose_nested_reference_failures=True,
    )[0]

    assert [field.name for field in upstream.response_fields] == [
        "composedDetailsCode"
    ]
    assert upstream.response_fields[0].max_length is None
    assert [field.name for field in downstream.request_fields] == [
        "routeKey",
        "composedEnvelopeCode",
    ]
    assert downstream.request_fields[1].max_length is None
    assert [field.name for field in downstream.response_fields] == [
        "composedDetailsCode"
    ]
    assert downstream.response_fields[0].max_length is None


def _crud_nested_compatibility_spec() -> dict:
    return {
        "openapi": "3.1.0",
        "paths": {
            "/customers/{id}": {
                "get": {
                    "operationId": "getCustomer",
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Customer"
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Street": {"type": "string", "maxLength": 12},
                "PreferenceCode": {
                    "allOf": [
                        {"type": "string", "maxLength": 20},
                        {"maxLength": 6},
                    ]
                },
                "Customer": {
                    "type": "object",
                    "required": ["id", "address", "preferences"],
                    "properties": {
                        "id": {"type": "string"},
                        "address": {
                            "type": "object",
                            "required": ["street"],
                            "properties": {
                                "street": {
                                    "$ref": "#/components/schemas/Street"
                                }
                            },
                        },
                        "preferences": {
                            "type": "object",
                            "required": ["code"],
                            "properties": {
                                "code": {
                                    "allOf": [
                                        {
                                            "$ref": "#/components/schemas/PreferenceCode"
                                        }
                                    ]
                                }
                            },
                        },
                    },
                },
            }
        },
    }


def _install_reference_failure(spec: dict, failure_kind: str) -> None:
    schemas = spec["components"]["schemas"]
    if failure_kind == "cyclic":
        schemas["Code"] = {"$ref": "#/components/schemas/CodeAlias"}
        schemas["CodeAlias"] = {"$ref": "#/components/schemas/Code"}
    elif failure_kind == "allof-cyclic":
        schemas["Code"] = {
            "allOf": [{"$ref": "#/components/schemas/CodeAlias"}]
        }
        schemas["CodeAlias"] = {
            "allOf": [{"$ref": "#/components/schemas/Code"}]
        }


def _nested_operation_spec(openapi_version: str) -> dict:
    spec = _operation_spec_with_properties(
        {"envelope": {"$ref": "#/components/schemas/Envelope"}},
        required=["envelope"],
        openapi_version=openapi_version,
    )
    schemas = spec["components"]["schemas"]
    schemas.update(
        {
            "Envelope": {
                "allOf": [
                    {"$ref": "#/components/schemas/EnvelopeBase"},
                    {
                        "type": "object",
                        "required": ["recipientCode"],
                        "properties": {
                            "recipientCode": {
                                "$ref": "#/components/schemas/RecipientCodeAlias"
                            }
                        },
                    },
                ]
            },
            "EnvelopeBase": {
                "type": "object",
                "required": ["routeKey"],
                "properties": {
                    "routeKey": {"type": "string", "maxLength": 16},
                },
            },
            "RecipientCodeAlias": {"$ref": "#/components/schemas/RecipientCode"},
            "RecipientCode": {
                "allOf": [
                    {"$ref": "#/components/schemas/RecipientCodeBase"},
                    {"maxLength": 12},
                ]
            },
            "RecipientCodeBase": {
                "type": "string",
                "format": "uuid",
                "maxLength": 20,
            },
        }
    )
    return spec


def _operation_spec_with_properties(
    request_properties: dict,
    *,
    required: list[str] | None = None,
    response_properties: dict | None = None,
    openapi_version: str = "3.1.0",
) -> dict:
    return {
        "openapi": openapi_version,
        "paths": {
            "/requests": {
                "post": {
                    "operationId": "routeRequest",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Request"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Response"}
                                }
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Request": {
                    "type": "object",
                    "required": required or [],
                    "properties": request_properties,
                },
                "Response": {
                    "type": "object",
                    "properties": response_properties or {"result": {"type": "string"}},
                },
            }
        },
    }
