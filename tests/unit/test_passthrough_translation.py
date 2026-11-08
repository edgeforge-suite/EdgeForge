import copy
import shutil
from pathlib import Path

import pytest
import yaml

from appbuilder.cli import main
from appbuilder.contracts import load_project_definition
from appbuilder.core import AppArchetype
from appbuilder.metadata import build_metadata_project


def test_load_country_router_manifest() -> None:
    definition = load_project_definition(_country_router_manifest())

    assert definition.app_name == "CountryRouter"
    assert definition.schema_version == "2.0"
    assert definition.app_archetype == AppArchetype.PASSTHROUGH_ROUTER
    assert definition.rules == ["rules/payment-routing.yaml"]


def test_translate_passthrough_manifest_populates_routing_rules_and_transforms() -> None:
    metadata = build_metadata_project(_country_router_manifest())

    assert metadata.app_archetype == AppArchetype.PASSTHROUGH_ROUTER
    assert metadata.routing_rules[0].route_field == "countryCode"
    assert [(route.match, route.target) for route in metadata.routing_rules[0].routes] == [
        ("US", "APP_A"),
        ("GB", "APP_B"),
    ]
    assert metadata.routing_rules[0].default_target == "APP_C"
    assert [(mapping.source, mapping.target, mapping.default) for mapping in metadata.transform_mappings] == [
        ("amount", "paymentAmount", None),
        ("currency", "currencyCode", None),
        ("senderName", "originatorName", "UNKNOWN"),
        ("recipientName", "beneficiaryName", None),
    ]


def test_translate_passthrough_manifest_populates_systems_and_no_entities() -> None:
    metadata = build_metadata_project(_country_router_manifest())

    assert metadata.entities == []
    assert {participant.name for participant in metadata.systems if participant.role == "downstream"} == {
        "APP_A",
        "APP_B",
        "APP_C",
    }


def test_translate_passthrough_manifest_captures_operation_shapes() -> None:
    metadata = build_metadata_project(_country_router_manifest())

    upstream_operation = next(
        operation for operation in metadata.operations if operation.interface_name == "inbound-payments-api"
    )
    assert upstream_operation.name == "routePayment"
    assert {field.name for field in upstream_operation.request_fields} == {
        "amount",
        "currency",
        "countryCode",
        "senderName",
        "recipientName",
    }
    assert {field.name for field in upstream_operation.response_fields} == {
        "paymentId",
        "status",
    }

    downstream_operation = next(
        operation for operation in metadata.operations if operation.interface_name == "app-a-api"
    )
    assert {field.name for field in downstream_operation.request_fields} == {
        "paymentAmount",
        "currencyCode",
        "originatorName",
        "beneficiaryName",
    }


@pytest.mark.parametrize(
    ("openapi_version", "nullable_schema"),
    [
        ("3.0.3", {"type": "string", "nullable": True}),
        ("3.1.0", {"type": ["string", "null"]}),
        ("3.1.0", {"oneOf": [{"type": "string"}, {"type": "null"}]}),
        (
            "3.1.0",
            {"allOf": [{"type": ["string", "null"]}, {"maxLength": 12}]},
        ),
        ("3.1.0", {"allOf": [{"type": ["string", "null"]}, True]}),
        ("3.1.0", {"anyOf": [{"type": "string"}, True]}),
        ("3.1.0", {"oneOf": [{"type": "string"}, True]}),
        ("3.1.0", True),
    ],
)
def test_passthrough_rejects_required_nullable_request_fields(
    tmp_path: Path,
    openapi_version: str,
    nullable_schema: dict | bool,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = openapi_version
    spec["components"]["schemas"]["PaymentRequest"]["properties"][
        "recipientName"
    ] = nullable_schema
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "Passthrough interface 'inbound-payments-api'" in message
    assert "operation 'routePayment'" in message
    assert "required request field 'recipientName'" in message
    assert "Required-nullable presence semantics are not currently representable" in message


def test_passthrough_rejects_required_nullable_request_field_through_ref_all_of(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    spec["components"]["schemas"]["NullableRecipient"] = {
        "allOf": [
            {"type": ["string", "null"]},
            {"maxLength": 12},
        ]
    }
    spec["components"]["schemas"]["PaymentRequest"]["properties"]["recipientName"] = {
        "$ref": "#/components/schemas/NullableRecipient"
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "Passthrough interface 'inbound-payments-api'" in message
    assert "operation 'routePayment'" in message
    assert "required request field 'recipientName'" in message


@pytest.mark.parametrize(
    ("openapi_version", "nullable_schema"),
    [
        ("3.0.3", {"type": "string", "nullable": True}),
        ("3.1.0", {"type": ["string", "null"]}),
    ],
)
def test_passthrough_rejects_required_nullable_field_through_chained_combiner_ref(
    tmp_path: Path,
    openapi_version: str,
    nullable_schema: dict,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = openapi_version
    spec["components"]["schemas"]["NullableExtras"] = {
        "type": "object",
        "required": ["nullableExtra"],
        "properties": {"nullableExtra": nullable_schema},
    }
    spec["components"]["schemas"]["NullableExtrasAlias"] = {
        "$ref": "#/components/schemas/NullableExtras"
    }
    spec["components"]["schemas"]["PaymentRequest"]["allOf"] = [
        {"$ref": "#/components/schemas/NullableExtrasAlias"}
    ]
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "Passthrough interface 'inbound-payments-api'" in message
    assert "operation 'routePayment'" in message
    assert "required request field 'nullableExtra'" in message
    assert "Required-nullable presence semantics are not currently representable" in message


def test_passthrough_rejects_openapi_30_required_nullable_field_behind_ref_siblings(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.0.3"
    spec["components"]["schemas"]["NullableRecipient"] = {
        "type": "string",
        "nullable": True,
    }
    spec["components"]["schemas"]["NullableRecipientAlias"] = {
        "$ref": "#/components/schemas/NullableRecipient"
    }
    spec["components"]["schemas"]["PaymentRequest"]["properties"][
        "recipientName"
    ] = {
        "$ref": "#/components/schemas/NullableRecipientAlias",
        "type": "string",
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "Passthrough interface 'inbound-payments-api'" in message
    assert "operation 'routePayment'" in message
    assert "required request field 'recipientName'" in message
    assert "Required-nullable presence semantics are not currently representable" in message


def test_passthrough_rejects_required_nullable_request_field_through_boolean_ref(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    spec["components"]["schemas"]["AcceptAnything"] = True
    spec["components"]["schemas"]["PaymentRequest"]["properties"]["recipientName"] = {
        "allOf": [
            {"type": ["string", "null"]},
            {"$ref": "#/components/schemas/AcceptAnything"},
        ]
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "Passthrough interface 'inbound-payments-api'" in message
    assert "operation 'routePayment'" in message
    assert "required request field 'recipientName'" in message


def test_passthrough_rejects_different_multi_operation_validation_contracts(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["components"]["schemas"]["AlternatePaymentRequest"] = {
        "type": "object",
        "required": ["countryCode"],
        "properties": {"countryCode": {"type": "string"}},
    }
    _add_upstream_operation(
        spec,
        path="/alternate-payments",
        operation_id="routeAlternatePayment",
        request_schema="AlternatePaymentRequest",
    )
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "Passthrough interface 'inbound-payments-api'" in message
    assert "operations 'routePayment' and 'routeAlternatePayment'" in message
    assert "different request-validation contracts" in message
    assert "shared InboundRequestDto cannot enforce both safely" in message


def test_passthrough_rejects_scalar_ref_max_length_mismatch_between_operations(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    schemas = spec["components"]["schemas"]
    schemas["RecipientName12"] = {"type": "string", "maxLength": 12}
    schemas["RecipientName20"] = {"type": "string", "maxLength": 20}
    payment_request = schemas["PaymentRequest"]
    payment_request["properties"]["recipientName"] = {
        "$ref": "#/components/schemas/RecipientName12"
    }
    schemas["AlternatePaymentRequest"] = copy.deepcopy(payment_request)
    schemas["AlternatePaymentRequest"]["properties"]["recipientName"] = {
        "$ref": "#/components/schemas/RecipientName20"
    }
    _add_upstream_operation(
        spec,
        path="/alternate-payments",
        operation_id="routeAlternatePayment",
        request_schema="AlternatePaymentRequest",
    )
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "operations 'routePayment' and 'routeAlternatePayment'" in message
    assert "different request-validation contracts" in message


def test_passthrough_rejects_openapi_31_ref_sibling_max_length_mismatch(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    schemas = spec["components"]["schemas"]
    schemas["RecipientName"] = {"type": "string", "maxLength": 20}
    payment_request = schemas["PaymentRequest"]
    payment_request["properties"]["recipientName"] = {
        "$ref": "#/components/schemas/RecipientName",
        "maxLength": 12,
    }
    schemas["AlternatePaymentRequest"] = copy.deepcopy(payment_request)
    schemas["AlternatePaymentRequest"]["properties"]["recipientName"] = {
        "$ref": "#/components/schemas/RecipientName"
    }
    _add_upstream_operation(
        spec,
        path="/alternate-payments",
        operation_id="routeAlternatePayment",
        request_schema="AlternatePaymentRequest",
    )
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "operations 'routePayment' and 'routeAlternatePayment'" in message
    assert "different request-validation contracts" in message


@pytest.mark.parametrize("branch_max_lengths", [(12, 20), (20, 12)])
def test_passthrough_composes_repeated_all_of_max_length_order_independently(
    tmp_path: Path,
    branch_max_lengths: tuple[int, int],
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    payment_request = spec["components"]["schemas"]["PaymentRequest"]
    payment_request["properties"]["recipientName"] = {
        "type": "string",
        "maxLength": 30,
    }
    payment_request["allOf"] = [
        {
            "type": "object",
            "properties": {
                "recipientName": {
                    "type": "string",
                    "maxLength": max_length,
                }
            },
        }
        for max_length in branch_max_lengths
    ]
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)

    operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    recipient_name = next(
        field for field in operation.request_fields if field.name == "recipientName"
    )
    assert recipient_name.max_length == 12


def test_passthrough_intersects_repeated_all_of_type_nullability(tmp_path: Path) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    payment_request = spec["components"]["schemas"]["PaymentRequest"]
    payment_request["properties"]["recipientName"] = {"type": "string"}
    payment_request["allOf"] = [
        {
            "type": "object",
            "properties": {
                "recipientName": {"type": ["string", "null"]},
            },
        }
    ]
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)

    operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    recipient_name = next(
        field for field in operation.request_fields if field.name == "recipientName"
    )
    assert recipient_name.required
    assert recipient_name.type.value == "string"


def test_passthrough_resolves_chained_request_component_refs(tmp_path: Path) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    spec["components"]["schemas"]["PaymentRequestAlias"] = {
        "$ref": "#/components/schemas/PaymentRequest"
    }
    request_schema = spec["paths"]["/payments"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    request_schema["$ref"] = "#/components/schemas/PaymentRequestAlias"
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)

    upstream_operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    assert {field.name for field in upstream_operation.request_fields} == {
        "amount",
        "currency",
        "countryCode",
        "senderName",
        "recipientName",
    }


def test_passthrough_preserves_required_scalar_all_of_fields_used_and_unused(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    schemas = spec["components"]["schemas"]
    schemas["RecipientNameBase"] = {"type": "string", "maxLength": 20}
    schemas["RecipientName"] = {
        "allOf": [
            {"$ref": "#/components/schemas/RecipientNameBase"},
            {"maxLength": 12},
        ]
    }
    schemas["ReviewCodeBase"] = {"type": "string", "maxLength": 10}
    schemas["ReviewCode"] = {
        "allOf": [
            {"$ref": "#/components/schemas/ReviewCodeBase"},
            {"maxLength": 8},
        ]
    }
    request_schema = schemas["PaymentRequest"]
    request_schema["properties"]["recipientName"] = {
        "$ref": "#/components/schemas/RecipientName"
    }
    request_schema["properties"]["reviewCode"] = {
        "$ref": "#/components/schemas/ReviewCode"
    }
    request_schema["required"].append("reviewCode")
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)

    operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    fields = {field.name: field for field in operation.request_fields}
    assert fields["recipientName"].required
    assert fields["recipientName"].max_length == 12
    assert fields["reviewCode"].required
    assert fields["reviewCode"].max_length == 8


def test_passthrough_fails_closed_for_unrepresentable_required_scalar_all_of(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    schemas = spec["components"]["schemas"]
    schemas["RecipientName"] = {
        "allOf": [
            {"type": "string"},
            {"const": "PRIMARY"},
        ]
    }
    schemas["PaymentRequest"]["properties"]["recipientName"] = {
        "$ref": "#/components/schemas/RecipientName"
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "OpenAPI interface 'inbound-payments-api'" in message
    assert "operation 'routePayment'" in message
    assert "Property 'recipientName'" in message
    assert "unsupported allOf constraint(s): const" in message


def test_passthrough_allows_optional_upstream_all_of_pattern(tmp_path: Path) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    schemas = spec["components"]["schemas"]
    schemas["AuditRef"] = {
        "allOf": [
            {"type": "string"},
            {"pattern": "^[A-Z0-9-]+$"},
        ]
    }
    schemas["PaymentRequest"]["properties"]["auditRef"] = {
        "$ref": "#/components/schemas/AuditRef"
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)

    operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    audit_ref = next(field for field in operation.request_fields if field.name == "auditRef")
    assert not audit_ref.required
    assert audit_ref.type.value == "string"


def test_passthrough_allows_optional_upstream_unrepresentable_all_of(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = "3.1.0"
    schemas = spec["components"]["schemas"]
    schemas["AuditRef"] = {
        "allOf": [
            {"type": "string"},
            {"const": "PRIMARY"},
        ]
    }
    schemas["PaymentRequest"]["properties"]["auditRef"] = {
        "$ref": "#/components/schemas/AuditRef"
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)

    operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    assert "auditRef" not in {field.name for field in operation.request_fields}
    assert metadata.warnings == [
        "OpenAPI interface 'inbound-payments-api' operation 'routePayment' request: "
        "field 'auditRef' in schema 'PaymentRequest' uses an unsupported composed "
        "shape that cannot be represented safely; field skipped"
    ]


def test_passthrough_allows_optional_downstream_unrepresentable_all_of(
    tmp_path: Path,
) -> None:
    manifest, _spec_path, _spec = _mutable_country_router(tmp_path)
    downstream_path = manifest.parent / "downstream/app-a-openapi.yaml"
    downstream = yaml.safe_load(downstream_path.read_text(encoding="utf-8"))
    schemas = downstream["components"]["schemas"]
    schemas["AuditRef"] = {
        "allOf": [
            {"type": "string"},
            {"const": "PRIMARY"},
        ]
    }
    schemas["OutboundPaymentRequest"]["properties"]["auditRef"] = {
        "$ref": "#/components/schemas/AuditRef"
    }
    downstream_path.write_text(
        yaml.safe_dump(downstream, sort_keys=False),
        encoding="utf-8",
    )

    metadata = build_metadata_project(manifest)

    operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "app-a-api"
    )
    assert "auditRef" not in {field.name for field in operation.request_fields}
    assert metadata.warnings == [
        "OpenAPI interface 'app-a-api' operation 'sendPaymentToAppA' request: "
        "Field 'auditRef' in 'OutboundPaymentRequest': nested object has no properties "
        "— field skipped."
    ]


def test_passthrough_allows_multi_operation_shared_validation_contract(
    tmp_path: Path,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    _add_upstream_operation(
        spec,
        path="/retry-payments",
        operation_id="retryPayment",
        request_schema="PaymentRequest",
    )
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)

    upstream_operation_names = {
        operation.name
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    }
    assert upstream_operation_names == {"routePayment", "retryPayment"}


def test_passthrough_allows_optional_nullable_request_fields(tmp_path: Path) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    request_schema = spec["components"]["schemas"]["PaymentRequest"]
    request_schema["required"].remove("recipientName")
    request_schema["properties"]["recipientName"]["nullable"] = True
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)
    upstream_operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    recipient_name = next(
        field for field in upstream_operation.request_fields if field.name == "recipientName"
    )
    assert recipient_name.required is False


@pytest.mark.parametrize(
    ("openapi_version", "nullable_schema"),
    [
        ("3.0.3", {"type": "string", "nullable": True}),
        ("3.1.0", {"type": ["string", "null"]}),
    ],
)
def test_passthrough_preserves_nested_required_nullable_fail_closed(
    tmp_path: Path,
    openapi_version: str,
    nullable_schema: dict,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = openapi_version
    request = spec["components"]["schemas"]["PaymentRequest"]
    request["required"].append("envelope")
    request["properties"]["envelope"] = {
        "type": "object",
        "required": ["nullableCode"],
        "properties": {"nullableCode": nullable_schema},
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "Passthrough interface 'inbound-payments-api'" in message
    assert "operation 'routePayment'" in message
    assert "required request field 'envelope.nullableCode'" in message


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
def test_passthrough_rejects_required_parent_with_only_optional_children(
    tmp_path: Path,
    openapi_version: str,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = openapi_version
    request_schema = spec["components"]["schemas"]["PaymentRequest"]
    request_schema["required"].append("envelope")
    request_schema["properties"]["envelope"] = {
        "type": "object",
        "properties": {
            "note": {"type": "string", "maxLength": 8},
        },
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        build_metadata_project(manifest)

    message = str(exc_info.value)
    assert "OpenAPI interface 'inbound-payments-api'" in message
    assert "operation 'routePayment'" in message
    assert "required field 'envelope'" in message
    assert "presence cannot be preserved after flattening" in message
    assert "all nested properties are optional" in message


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
def test_passthrough_keeps_optional_parent_with_optional_children_supported(
    tmp_path: Path,
    openapi_version: str,
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    spec["openapi"] = openapi_version
    request_schema = spec["components"]["schemas"]["PaymentRequest"]
    request_schema["properties"]["envelope"] = {
        "type": "object",
        "properties": {
            "note": {"type": "string", "maxLength": 8},
        },
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)

    operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    envelope_note = next(
        field for field in operation.request_fields if field.name == "envelopeNote"
    )
    assert not envelope_note.required
    assert envelope_note.max_length == 8


def test_passthrough_required_shape_failure_creates_no_output_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, spec_path, spec = _mutable_country_router(tmp_path)
    request = spec["components"]["schemas"]["PaymentRequest"]
    request["required"].append("items")
    request["properties"]["items"] = {
        "type": "array",
        "items": {"type": "string"},
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    output_dir = tmp_path / "must-not-exist"

    exit_code = main(
        [
            "generate",
            "--manifest",
            str(manifest),
            "--output",
            str(output_dir),
            "--generation-run-id",
            "fail-closed-proof",
        ]
    )

    assert exit_code == 1
    assert not output_dir.exists()
    error = capsys.readouterr().err
    assert "OpenAPI interface 'inbound-payments-api'" in error
    assert "required field 'items'" in error


def _country_router_manifest() -> Path:
    return Path("examples/input-projects/country-router/app-definition.yaml")


def _mutable_country_router(tmp_path: Path) -> tuple[Path, Path, dict]:
    package = tmp_path / "country-router"
    shutil.copytree(_country_router_manifest().parent, package)
    spec_path = package / "upstream/payments-openapi.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    return package / "app-definition.yaml", spec_path, spec


def _add_upstream_operation(
    spec: dict,
    *,
    path: str,
    operation_id: str,
    request_schema: str,
) -> None:
    spec["paths"][path] = {
        "post": {
            "operationId": operation_id,
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "$ref": f"#/components/schemas/{request_schema}",
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Routed payment response",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/PaymentResponse",
                            }
                        }
                    },
                }
            },
        }
    }
