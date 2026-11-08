"""OpenAPI classification and entity extraction helpers."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from appbuilder.metadata.models import (
        CanonicalEntity,
        CanonicalField,
        CanonicalFieldType,
        CanonicalOperation,
        HttpMethod,
        OperationParameter,
        PathParameter,
        ResponseShape,
    )

_CRUD_HTTP_METHODS = ("get", "post", "put", "delete", "patch")
_INFRASTRUCTURE_NAMES = {
    "PageableObject",
    "Pageable",
    "SortObject",
    "Sort",
    "SliceObject",
    "Error",
    "ApiError",
    "Problem",
    "ValidationError",
    "ErrorResponse",
}
_RESPONSE_ENVELOPE_ARRAY_KEYS = ("content", "results", "items")
_RESPONSE_ENVELOPE_OBJECT_KEYS = ("data", "result", "item")
_RESPONSE_ENVELOPE_METADATA_KEYS = {
    "changes",
    "companyId",
    "dataConnectionKey",
    "dataType",
    "empty",
    "first",
    "last",
    "links",
    "_links",
    "number",
    "numberOfElements",
    "page",
    "pageNumber",
    "pageSize",
    "pageable",
    "pushOperationKey",
    "size",
    "sort",
    "status",
    "statusCode",
    "timeoutInMinutes",
    "timeoutInSeconds",
    "totalElements",
    "totalPages",
    "totalResults",
}
_COMPLEX_OPERATION_KEYWORDS = (
    "debit",
    "credit",
    "transaction",
    "earmark",
    "release",
    "payment",
    "sweep",
    "interest",
)


def classify_openapi_schemas(spec: dict) -> dict[str, str]:
    """Classify OpenAPI component schemas into entity, dto, or infrastructure."""

    schemas = _component_schemas(spec)
    response_refs = _response_schema_refs(spec)
    classifications: dict[str, str] = {}

    for schema_name, schema_def in schemas.items():
        if _is_infrastructure_schema_name(schema_name):
            classifications[schema_name] = "infrastructure"
            continue
        if schema_name.endswith(("Request", "Response")):
            classifications[schema_name] = "dto"
            continue
        if schema_name in response_refs and isinstance(schema_def, dict) and _schema_has_properties(schema_def):
            classifications[schema_name] = "entity"
            continue
        classifications[schema_name] = "infrastructure"

    return classifications


def ingest_openapi_operations(
    spec: dict,
    interface_name: str,
    *,
    fail_on_unrepresentable_required_request_fields: bool = False,
    resolve_nested_request_properties: bool | None = None,
    diagnose_nested_reference_failures: bool = False,
    warnings_out: list[str] | None = None,
) -> list[CanonicalOperation]:
    """Extract REST operation metadata from an OpenAPI spec.

    Each path+method combination produces a CanonicalOperation with HTTP method,
    route pattern, path parameters, request body flag, and response shape.
    Phase 1a: builds the operation model the emitter reads instead of guessing.
    """
    from appbuilder.metadata.models import (
        CanonicalOperation,
        HttpMethod,
    )

    _http_method_map = {
        "get": HttpMethod.GET,
        "post": HttpMethod.POST,
        "put": HttpMethod.PUT,
        "delete": HttpMethod.DELETE,
    }

    reader_first_request_resolution = (
        fail_on_unrepresentable_required_request_fields
        if resolve_nested_request_properties is None
        else resolve_nested_request_properties
    )
    operations: list[CanonicalOperation] = []
    operation_warnings = warnings_out if warnings_out is not None else []
    paths = spec.get("paths", {})
    compatibility_schemas = _component_schemas(spec)
    reader_schemas = _component_schema_nodes(spec)
    request_schemas = (
        reader_schemas if reader_first_request_resolution else compatibility_schemas
    )
    diagnostic_schemas = reader_schemas if diagnose_nested_reference_failures else None
    ref_siblings_apply = _openapi_ref_siblings_apply(spec)
    if not isinstance(paths, dict):
        return operations

    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method in _CRUD_HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict) or method not in _http_method_map:
                continue

            http_method = _http_method_map[method]
            operation_id = operation.get("operationId") or (
                f"{method}{_resource_entity_name_from_path(path) or 'Resource'}"
            )
            read_input_errors: list[str] = []
            parameter_defs = _merge_parameter_definitions(
                path_item, operation, spec=spec, errors=read_input_errors,
            )
            _validate_read_parameter_declarations(spec, operation, path, parameter_defs, read_input_errors)

            operations.append(
                CanonicalOperation(
                    name=operation_id,
                    interface_name=interface_name,
                    request_entity=_resource_entity_name_from_path(path),
                    response_entity=_resource_entity_name_from_path(path),
                    http_method=http_method,
                    path=path,
                    path_parameters=_extract_path_parameters(path, parameter_defs),
                    operation_parameters=_extract_operation_parameters(parameter_defs),
                    read_input_errors=read_input_errors,
                    has_request_body="requestBody" in operation,
                    response_shape=_derive_response_shape(http_method, operation),
                    request_fields=_extract_operation_request_fields(
                        operation,
                        schemas=request_schemas,
                        diagnostic_schemas=diagnostic_schemas,
                        interface_name=interface_name,
                        operation_name=operation_id,
                        ref_siblings_apply=ref_siblings_apply,
                        fail_on_unrepresentable_required=(
                            fail_on_unrepresentable_required_request_fields
                        ),
                        resolve_nested_properties=reader_first_request_resolution,
                        diagnose_nested_reference_failures=(
                            diagnose_nested_reference_failures
                        ),
                        warnings_out=operation_warnings,
                    ),
                    response_fields=_extract_operation_response_fields(
                        operation,
                        schemas=compatibility_schemas,
                        diagnostic_schemas=diagnostic_schemas,
                        interface_name=interface_name,
                        operation_name=operation_id,
                        ref_siblings_apply=ref_siblings_apply,
                        resolve_nested_properties=False,
                        diagnose_nested_reference_failures=(
                            diagnose_nested_reference_failures
                        ),
                        warnings_out=operation_warnings,
                    ),
                )
            )

    return operations


def required_nullable_request_fields(spec: dict) -> list[tuple[str, str]]:
    """Return operation/field pairs whose required request fields allow null."""

    schemas = _component_schema_nodes(spec)
    ref_siblings_apply = _openapi_ref_siblings_apply(spec)
    findings: list[tuple[str, str]] = []
    for path, method, operation in _iter_path_operations(spec):
        request_schema = _request_body_schema(operation)
        if not isinstance(request_schema, dict):
            continue
        operation_name = operation.get("operationId") or (
            f"{method}{_resource_entity_name_from_path(path) or 'Resource'}"
        )
        findings.extend(
            (operation_name, field_path)
            for field_path in _required_nullable_field_paths(
                request_schema,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
            )
        )
    return findings


def _required_nullable_field_paths(
    schema: dict[str, Any],
    *,
    schemas: dict[str, dict | bool],
    ref_siblings_apply: bool,
    prefix: str = "",
) -> list[str]:
    properties, required_fields = _collect_properties_and_required(
        schema,
        schemas=schemas,
        ref_siblings_apply=ref_siblings_apply,
    )
    findings: list[str] = []
    for field_name, property_schema in properties.items():
        if field_name not in required_fields:
            continue
        field_path = f"{prefix}.{field_name}" if prefix else field_name
        if isinstance(property_schema, bool):
            if property_schema:
                findings.append(field_path)
            continue
        if not isinstance(property_schema, dict):
            continue
        if _schema_allows_null(
            property_schema,
            schemas=schemas,
            ref_siblings_apply=ref_siblings_apply,
        ):
            findings.append(field_path)
            continue
        findings.extend(
            _required_nullable_field_paths(
                property_schema,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
                prefix=field_path,
            )
        )
    return findings


def _schema_allows_null(
    schema: dict[str, Any] | bool,
    *,
    schemas: dict[str, dict | bool],
    ref_siblings_apply: bool,
    seen_refs: frozenset[str] = frozenset(),
) -> bool:
    """Return whether a null instance satisfies the composed schema."""

    if isinstance(schema, bool):
        return schema

    ref = schema.get("$ref")
    if isinstance(ref, str):
        if ref in seen_refs:
            ref_allows_null = False
        else:
            resolved = _resolve_component_schema(schema, schemas=schemas)
            ref_allows_null = resolved is not schema and _schema_allows_null(
                resolved,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
                seen_refs=seen_refs | {ref},
            )
        if not ref_siblings_apply:
            return ref_allows_null
    else:
        ref_allows_null = None

    constraints: list[bool] = []
    if ref_allows_null is not None:
        constraints.append(ref_allows_null)
    nullable = schema.get("nullable") is True
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        constraints.append(nullable or schema_type == "null")
    elif isinstance(schema_type, list):
        constraints.append(nullable or "null" in schema_type)
    elif nullable:
        constraints.append(True)

    if "const" in schema:
        constraints.append(schema["const"] is None)
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and None in enum_values:
        constraints.append(True)
    elif isinstance(enum_values, list):
        constraints.append(False)

    variants = schema.get("anyOf")
    if isinstance(variants, list):
        constraints.append(
            any(
                isinstance(variant, (dict, bool))
                and _schema_allows_null(
                    variant,
                    schemas=schemas,
                    ref_siblings_apply=ref_siblings_apply,
                    seen_refs=seen_refs,
                )
                for variant in variants
            )
        )

    variants = schema.get("oneOf")
    if isinstance(variants, list):
        matching_variants = sum(
            1
            for variant in variants
            if isinstance(variant, (dict, bool))
            and _schema_allows_null(
                variant,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
                seen_refs=seen_refs,
            )
        )
        constraints.append(matching_variants == 1)

    variants = schema.get("allOf")
    if isinstance(variants, list):
        constraints.append(
            bool(variants)
            and all(
                isinstance(variant, (dict, bool))
                and _schema_allows_null(
                    variant,
                    schemas=schemas,
                    ref_siblings_apply=ref_siblings_apply,
                    seen_refs=seen_refs,
                )
                for variant in variants
            )
        )

    negated = schema.get("not")
    if isinstance(negated, (dict, bool)):
        constraints.append(
            not _schema_allows_null(
                negated,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
                seen_refs=seen_refs,
            )
        )

    # Keywords such as maxLength do not apply to null. With no type or
    # combinator excluding it, null therefore satisfies the schema.
    return all(constraints) if constraints else True


def _resolve_component_schema(
    schema: dict[str, Any],
    *,
    schemas: dict[str, dict | bool],
) -> dict[str, Any] | bool:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    resolved = schemas.get(_schema_name_from_ref(ref))
    return resolved if isinstance(resolved, (dict, bool)) else schema


def _extract_operation_request_fields(
    operation: dict[str, Any],
    *,
    schemas: dict[str, dict | bool],
    diagnostic_schemas: dict[str, dict | bool] | None,
    interface_name: str,
    operation_name: str,
    ref_siblings_apply: bool,
    fail_on_unrepresentable_required: bool,
    resolve_nested_properties: bool,
    diagnose_nested_reference_failures: bool,
    warnings_out: list[str],
) -> list[CanonicalField]:
    request_schema = _request_body_schema(operation)
    if not isinstance(request_schema, dict):
        return []
    raw_warnings: list[str] = []
    try:
        fields = _extract_operation_shape_fields(
            request_schema,
            schemas=schemas,
            diagnostic_schemas=diagnostic_schemas,
            interface_name=interface_name,
            fallback_name=f"{operation_name}Request",
            ref_siblings_apply=ref_siblings_apply,
            fail_on_unrepresentable_required=fail_on_unrepresentable_required,
            resolve_nested_properties=resolve_nested_properties,
            diagnose_nested_reference_failures=diagnose_nested_reference_failures,
            warnings_out=raw_warnings,
        )
    except ValueError as exc:
        raise ValueError(
            f"OpenAPI interface '{interface_name}' operation '{operation_name}' request "
            f"contract cannot be represented safely: {exc}"
        ) from exc
    _append_contextual_operation_warnings(
        warnings_out,
        raw_warnings,
        interface_name=interface_name,
        operation_name=operation_name,
        shape_role="request",
    )
    return fields


def _extract_operation_response_fields(
    operation: dict[str, Any],
    *,
    schemas: dict[str, dict | bool],
    diagnostic_schemas: dict[str, dict | bool] | None,
    interface_name: str,
    operation_name: str,
    ref_siblings_apply: bool,
    resolve_nested_properties: bool,
    diagnose_nested_reference_failures: bool,
    warnings_out: list[str],
) -> list[CanonicalField]:
    fields_by_name: OrderedDict[str, CanonicalField] = OrderedDict()
    raw_warnings: list[str] = []
    for response_schema in _response_schemas(operation):
        for schema_name, schema_def in _entity_schemas_from_response_schema(
            response_schema,
            schemas=schemas,
            fallback_name=f"{operation_name}Response",
            ref_siblings_apply=ref_siblings_apply,
        ):
            for field in extract_entity_fields(
                schema_name,
                schema_def,
                source_name=interface_name,
                schemas=schemas,
                diagnostic_schemas=diagnostic_schemas,
                warnings_out=raw_warnings,
                ref_siblings_apply=ref_siblings_apply,
                resolve_nested_properties=resolve_nested_properties,
                diagnose_nested_reference_failures=(
                    diagnose_nested_reference_failures
                ),
            ):
                fields_by_name.setdefault(field.name, field)
    _append_contextual_operation_warnings(
        warnings_out,
        raw_warnings,
        interface_name=interface_name,
        operation_name=operation_name,
        shape_role="response",
    )
    return list(fields_by_name.values())


def _extract_operation_shape_fields(
    schema: dict[str, Any],
    *,
    schemas: dict[str, dict | bool],
    diagnostic_schemas: dict[str, dict | bool] | None = None,
    interface_name: str,
    fallback_name: str,
    ref_siblings_apply: bool,
    fail_on_unrepresentable_required: bool = False,
    resolve_nested_properties: bool = False,
    diagnose_nested_reference_failures: bool = False,
    warnings_out: list[str] | None = None,
) -> list[CanonicalField]:
    fields_by_name: OrderedDict[str, CanonicalField] = OrderedDict()
    shape_warnings = warnings_out if warnings_out is not None else []
    for schema_name, schema_def in _schemas_from_schema(
        schema,
        schemas=schemas,
        fallback_name=fallback_name,
        ref_siblings_apply=ref_siblings_apply,
    ):
        for field in extract_entity_fields(
            schema_name,
            schema_def,
            source_name=interface_name,
            schemas=schemas,
            diagnostic_schemas=diagnostic_schemas,
            warnings_out=shape_warnings,
            ref_siblings_apply=ref_siblings_apply,
            fail_on_unrepresentable_required=fail_on_unrepresentable_required,
            resolve_nested_properties=resolve_nested_properties,
            diagnose_nested_reference_failures=diagnose_nested_reference_failures,
        ):
            fields_by_name.setdefault(field.name, field)
    return list(fields_by_name.values())


def _append_contextual_operation_warnings(
    destination: list[str],
    warnings: list[str],
    *,
    interface_name: str,
    operation_name: str,
    shape_role: str,
) -> None:
    for warning in warnings:
        contextual = (
            f"OpenAPI interface '{interface_name}' operation '{operation_name}' "
            f"{shape_role}: {warning}"
        )
        if contextual not in destination:
            destination.append(contextual)


def _resolve_local_reference(parameter: Any, spec: dict, *, kind: str) -> dict:
    seen: set[str] = set()
    while isinstance(parameter, dict) and "$ref" in parameter:
        reference = parameter["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ValueError(f"{kind} reference must be a local document JSON pointer")
        if reference in seen or len(seen) >= 32:
            raise ValueError(f"cyclic or excessively deep {kind} reference")
        seen.add(reference)
        # A Reference Object is not a Parameter Object: classification belongs
        # on its target, never on a sibling ignored by OpenAPI 3.0.
        if kind == "parameter" and "x-edgeforge-read-input-role" in parameter:
            raise ValueError("read-input classification must be on the referenced Parameter Object")
        parameter = spec
        for token in reference[2:].split("/"):
            if re.search(r"~(?![01])", token):
                raise ValueError(f"malformed {kind} JSON pointer")
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(parameter, dict) or token not in parameter:
                raise ValueError(f"unresolved {kind} reference")
            parameter = parameter[token]
    if not isinstance(parameter, dict):
        raise ValueError(f"{kind} must resolve to an object")
    return parameter


def _resolve_parameter_reference(parameter: Any, spec: dict) -> dict:
    parameter = _resolve_local_reference(parameter, spec, kind="parameter")
    name, location = parameter.get("name"), parameter.get("in")
    if not isinstance(name, str) or not name or not isinstance(location, str) or location not in {"path", "query", "header", "cookie"}:
        raise ValueError("parameter requires a nonempty name and valid location")
    return parameter


def _merge_parameter_definitions(
    path_item: dict, operation: dict, *, spec: dict | None = None,
    errors: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Merge path-item and operation-level parameters, letting operation override path-level."""

    merged: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
    errors = errors if errors is not None else []
    for owner in (path_item, operation):
        parameters = owner.get("parameters", [])
        if not isinstance(parameters, list):
            errors.append("parameters must be an array")
            continue
        owner_keys: set[tuple[str, str]] = set()
        for raw_parameter in parameters:
            try:
                param = _resolve_parameter_reference(raw_parameter, spec or {})
            except ValueError as exc:
                errors.append(str(exc))
                continue
            name, location = param["name"], param["in"]
            if location == "header" and name.lower() in {"authorization", "accept", "content-type"}:
                continue
            key = (name.lower() if location == "header" else name, location)
            if key in owner_keys:
                errors.append(f"duplicate {location} parameter '{name}'")
            owner_keys.add(key)
            merged[key] = param
    return list(merged.values())


def _validate_read_parameter_declarations(
    spec: dict, operation: dict, path: str, parameters: list[dict], errors: list[str],
) -> None:
    path_names = re.findall(r"\{([^}]+)\}", path)
    declared_paths = [param["name"] for param in parameters if param["in"] == "path"]
    if sorted(path_names) != sorted(declared_paths):
        errors.append("declared path parameters must match route placeholders exactly")
    security = operation.get("security", spec.get("security", []))
    components = spec.get("components", {})
    schemes = components.get("securitySchemes", {}) if isinstance(components, dict) else {}
    schemes = schemes if isinstance(schemes, dict) else {}
    security_headers = set()
    if any("x-edgeforge-read-input-role" in parameter for parameter in parameters):
        if not isinstance(security, list) or any(
            not isinstance(item, dict) or any(not isinstance(key, str) for key in item)
            for item in security
        ):
            errors.append("cannot verify header classification against malformed security requirements")
        else:
            for key in sorted({key for requirement in security for key in requirement}):
                try:
                    scheme = _resolve_local_reference(schemes.get(key), spec, kind="security scheme")
                    if scheme.get("type") not in ("apiKey", "http", "oauth2", "openIdConnect"):
                        raise ValueError("unsupported or malformed security scheme type")
                    if scheme["type"] == "apiKey":
                        name, location = scheme.get("name"), scheme.get("in")
                        if not isinstance(name, str) or not name or location not in ("header", "query", "cookie"):
                            raise ValueError("malformed API-key security scheme")
                        if location == "header":
                            security_headers.add(name.lower())
                except ValueError as exc:
                    errors.append(f"cannot verify header classification: {exc}")
    for parameter in parameters:
        name, location = parameter["name"], parameter["in"]
        role = parameter.get("x-edgeforge-read-input-role")
        if "x-edgeforge-read-input-role" in parameter:
            if location != "header" or role not in ("metadata", "gateway-rate-limit"):
                errors.append(f"parameter '{name}' has invalid read-input classification; only ordinary headers support metadata or gateway-rate-limit")
            if name.lower() in security_headers:
                errors.append(f"header '{name}' classification contradicts its security-scheme usage")
        if location == "cookie":
            errors.append(f"cookie selector '{name}' is unsupported")
        if location == "path" and parameter.get("required") is not True:
            errors.append(f"path parameter '{name}' must be required")
        schema = parameter.get("schema")
        if not isinstance(schema, dict) or "$ref" in schema or schema.get("type") not in ("string", "integer", "number", "boolean"):
            errors.append(f"parameter '{name}' requires a supported inline scalar schema")
        elif location == "path" and (
            schema.get("type") not in ("string", "integer")
            or parameter.get("style", "simple") != "simple"
        ):
            errors.append(f"path parameter '{name}' requires supported simple string/integer binding")


def _extract_path_parameters(path: str, parameters: list[dict[str, Any]]) -> list[PathParameter]:
    """Extract path parameter definitions from path template and operation spec."""
    from appbuilder.metadata.models import PathParameter

    # Find {param} placeholders in the path
    param_names = re.findall(r"\{([^}]+)\}", path)
    if not param_names:
        return []

    # Build type lookup from merged path/operation parameters
    param_type_map: dict[str, str] = {}
    for param in parameters:
        if param.get("in") != "path":
            continue
        param_name = param.get("name")
        if not param_name:
            continue
        schema = param.get("schema", {})
        openapi_type = schema.get("type", "string") if isinstance(schema, dict) else "string"
        openapi_format = schema.get("format", "") if isinstance(schema, dict) else ""
        java_type = _openapi_path_param_to_java_type(openapi_type, openapi_format)
        param_type_map[param_name] = java_type

    return [
        PathParameter(name=name, type=param_type_map.get(name, "String"))
        for name in param_names
    ]


def _extract_operation_parameters(parameters: list[dict[str, Any]]) -> list[OperationParameter]:
    from appbuilder.metadata.models import OperationParameter, OperationParameterLocation

    operation_parameters: list[OperationParameter] = []
    for param in parameters:
        location = param.get("in")
        if location not in {"query", "header"}:
            continue
        name = param.get("name")
        if not isinstance(name, str) or not name:
            continue
        schema = param.get("schema", {})
        if not isinstance(schema, dict):
            schema = {}
        operation_parameters.append(
            OperationParameter(
                name=name,
                location=OperationParameterLocation(location),
                required=bool(param.get("required", False)),
                type=openapi_type_to_canonical_type(
                    schema.get("type"),
                    schema.get("format"),
                ),
                format=schema.get("format") if isinstance(schema.get("format"), str) else None,
                pattern=schema.get("pattern") if isinstance(schema.get("pattern"), str) else None,
                read_input_role=param.get("x-edgeforge-read-input-role")
                if isinstance(param.get("x-edgeforge-read-input-role"), str) else None,
            )
        )
    return operation_parameters


def _openapi_path_param_to_java_type(openapi_type: Any, openapi_format: str | None) -> str:
    if _normalize_openapi_type(openapi_type) == "integer":
        return "Long"
    return "String"


def _derive_response_shape(
    http_method: HttpMethod,
    operation: dict,
) -> ResponseShape:
    """Infer response shape from HTTP method and response schemas."""
    from appbuilder.metadata.models import HttpMethod, ResponseShape

    if http_method == HttpMethod.DELETE:
        return ResponseShape.VOID
    if http_method == HttpMethod.POST:
        return ResponseShape.CREATED

    # For GET and PUT, examine response schema to distinguish LIST vs SINGLE
    for response_schema in _response_schemas(operation):
        if _normalize_openapi_type(response_schema.get("type")) == "array":
            return ResponseShape.LIST
        items = response_schema.get("items")
        if isinstance(items, dict):
            return ResponseShape.LIST

    return ResponseShape.SINGLE


def ingest_openapi_entities(spec: dict, interface_name: str) -> list[CanonicalEntity]:
    """Derive canonical entities from an OpenAPI contract.

    Phase 1a: also collects per-entity warnings for unsupported constructs
    (nested objects, arrays of objects, oneOf/anyOf) and attaches them to the
    returned CanonicalEntity objects so the CLI can surface them.

    ID ownership: when the entity's id field appears in a POST request body schema,
    the client is supplying the id — server_generated_id is set to False on that field.
    """

    from appbuilder.metadata.models import CanonicalEntity

    schemas = _component_schemas(spec)
    ref_siblings_apply = _openapi_ref_siblings_apply(spec)
    classifications = classify_openapi_schemas(spec)
    entity_fields: OrderedDict[str, OrderedDict[str, CanonicalField]] = OrderedDict()
    entity_warnings: OrderedDict[str, list[str]] = OrderedDict()
    # Tracks field names found in POST request bodies per entity.
    # Used to detect client-supplied id fields.
    post_request_field_names: OrderedDict[str, set[str]] = OrderedDict()

    for schema_name, label in classifications.items():
        if label != "entity":
            continue
        schema_def = schemas.get(schema_name)
        if not isinstance(schema_def, dict):
            continue
        entity_name = _normalize_entity_name(schema_name)
        warnings: list[str] = []
        _merge_fields(
            entity_fields,
            entity_name,
            extract_entity_fields(
                schema_name,
                schema_def,
                source_name=interface_name,
                schemas=schemas,
                warnings_out=warnings,
                ref_siblings_apply=ref_siblings_apply,
            ),
        )
        if warnings:
            entity_warnings.setdefault(entity_name, []).extend(warnings)

    for path, method, operation in _iter_path_operations(spec):
        entity_name = _resource_entity_name_from_path(path)
        if entity_name is None:
            continue

        request_schema = _request_body_schema(operation)
        if isinstance(request_schema, dict):
            for schema_name, schema_def in _schemas_from_schema(
                request_schema,
                schemas=schemas,
                fallback_name=f"{entity_name}Request",
                ref_siblings_apply=ref_siblings_apply,
            ):
                if classifications.get(schema_name) == "infrastructure":
                    continue
                warnings = []
                _merge_fields(
                    entity_fields,
                    entity_name,
                    extract_entity_fields(
                        schema_name,
                        schema_def,
                        source_name=interface_name,
                        schemas=schemas,
                        warnings_out=warnings,
                        ref_siblings_apply=ref_siblings_apply,
                    ),
                )
                if warnings:
                    entity_warnings.setdefault(entity_name, []).extend(warnings)
                # Track POST request body field names for id-ownership inference.
                # Restricted to collection-level POST paths (no path params) so
                # that command-style POSTs like POST /accounts/{id}/close are not
                # mistaken for create endpoints.
                if method == "post" and _is_create_post_path(path):
                    props, _ = _collect_properties_and_required(
                        schema_def,
                        schemas=schemas,
                        ref_siblings_apply=ref_siblings_apply,
                    )
                    post_request_field_names.setdefault(entity_name, set()).update(props.keys())

        for response_schema in _response_schemas(operation):
            for schema_name, schema_def in _entity_schemas_from_response_schema(
                response_schema,
                schemas=schemas,
                fallback_name=f"{entity_name}{method.title()}Response",
                ref_siblings_apply=ref_siblings_apply,
            ):
                if classifications.get(schema_name) == "infrastructure":
                    continue
                warnings = []
                _merge_fields(
                    entity_fields,
                    entity_name,
                    extract_entity_fields(
                        schema_name,
                        schema_def,
                        source_name=interface_name,
                        schemas=schemas,
                        warnings_out=warnings,
                        ref_siblings_apply=ref_siblings_apply,
                    ),
                )
                if warnings:
                    entity_warnings.setdefault(entity_name, []).extend(warnings)

    entities = []
    for entity_name, fields in entity_fields.items():
        if not fields:
            continue
        # ID ownership: if the id field was found in the POST request body,
        # the client is supplying it — mark server_generated_id=False.
        post_fields = post_request_field_names.get(entity_name, set())
        for field in fields.values():
            if field.is_id and field.name in post_fields:
                field.server_generated_id = False
        entities.append(
            CanonicalEntity(
                name=entity_name,
                fields=list(fields.values()),
                warnings=entity_warnings.get(entity_name, []),
            )
        )
    return entities


def _collect_properties_and_required(
    schema_def: dict,
    schemas: dict[str, dict | bool] | None = None,
    *,
    ref_siblings_apply: bool = False,
    seen_refs: frozenset[str] = frozenset(),
) -> tuple[dict, set[str]]:
    """Collect properties and required fields from direct and conjunctive schemas.

    Spring Boot / Springdoc uses allOf for inheritance:
      allOf:
        - $ref: '#/components/schemas/BaseEntity'   ← resolved here when schemas provided
        - type: object
          properties: {id: ..., name: ...}
          required: [id]
    Reading only schema_def.get("properties") misses all fields in allOf items.
    When *schemas* is provided, local $ref chains inside combiners are resolved
    cycle-safely so inherited fields (e.g. BaseEntity.createdAt) are included.
    Reference siblings follow the selected OpenAPI dialect. anyOf/oneOf variants
    are deliberately not flattened into one effective object shape.
    """
    properties: dict = {}
    required: set[str] = set()

    ref = schema_def.get("$ref")
    if isinstance(ref, str) and schemas is not None:
        if not ref.startswith("#/components/schemas/"):
            raise ValueError(f"Unsupported non-local OpenAPI schema reference '{ref}'.")
        if ref in seen_refs:
            raise ValueError(f"Cyclic local OpenAPI schema reference detected at '{ref}'.")
        resolved = schemas.get(_schema_name_from_ref(ref))
        if not isinstance(resolved, (dict, bool)):
            raise ValueError(f"OpenAPI schema reference '{ref}' does not resolve to a schema.")
        if isinstance(resolved, dict):
            referenced_properties, referenced_required = _collect_properties_and_required(
                resolved,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
                seen_refs=seen_refs | {ref},
            )
            properties.update(referenced_properties)
            required.update(referenced_required)
        if not ref_siblings_apply:
            return properties, required

    direct_props = schema_def.get("properties")
    if isinstance(direct_props, dict):
        for field_name, property_schema in direct_props.items():
            _merge_conjunctive_property_schema(
                properties,
                field_name,
                property_schema,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
            )
    direct_required = schema_def.get("required", [])
    if isinstance(direct_required, list):
        required.update(f for f in direct_required if isinstance(f, str))

    variants = schema_def.get("allOf", [])
    if isinstance(variants, list):
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            variant_properties, variant_required = _collect_properties_and_required(
                variant,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
                seen_refs=seen_refs,
            )
            for field_name, property_schema in variant_properties.items():
                _merge_conjunctive_property_schema(
                    properties,
                    field_name,
                    property_schema,
                    schemas=schemas,
                    ref_siblings_apply=ref_siblings_apply,
                )
            required.update(variant_required)

    return properties, required


def _merge_conjunctive_property_schema(
    properties: dict[str, Any],
    field_name: str,
    property_schema: Any,
    *,
    schemas: dict[str, dict | bool] | None,
    ref_siblings_apply: bool,
) -> None:
    if field_name not in properties:
        properties[field_name] = property_schema
        return
    existing = properties[field_name]
    if not isinstance(existing, dict) or not isinstance(property_schema, dict):
        properties[field_name] = {"allOf": [existing, property_schema]}
        return

    resolved_existing = _resolve_property_schema_for_conjunction(
        existing,
        schemas=schemas,
        ref_siblings_apply=ref_siblings_apply,
        field_name=field_name,
    )
    resolved_incoming = _resolve_property_schema_for_conjunction(
        property_schema,
        schemas=schemas,
        ref_siblings_apply=ref_siblings_apply,
        field_name=field_name,
    )
    try:
        properties[field_name] = _compose_supported_property_conjunction(
            resolved_existing,
            resolved_incoming,
            field_name=field_name,
            ref_siblings_apply=ref_siblings_apply,
        )
    except ValueError:
        properties[field_name] = {"allOf": [existing, property_schema]}


def _resolve_property_schema_for_conjunction(
    schema: dict[str, Any],
    *,
    schemas: dict[str, dict | bool] | None,
    ref_siblings_apply: bool,
    field_name: str,
) -> dict[str, Any]:
    if schemas is None:
        if "$ref" in schema or "allOf" in schema:
            raise ValueError(
                "Repeated allOf property references require object component schemas."
            )
        return schema
    resolved = _resolve_property_schema_for_extraction(
        schema,
        schemas=schemas,
        ref_siblings_apply=ref_siblings_apply,
        field_name=field_name,
    )
    if not isinstance(resolved, dict):
        raise ValueError(
            f"Property '{field_name}' resolves to a boolean schema that cannot be composed."
        )
    return resolved


def _compose_supported_property_conjunction(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    field_name: str,
    ref_siblings_apply: bool,
) -> dict[str, Any]:
    annotations = {
        "$anchor",
        "$comment",
        "$defs",
        "$dynamicAnchor",
        "$id",
        "$schema",
        "default",
        "deprecated",
        "description",
        "example",
        "examples",
        "externalDocs",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "maximum",
        "minimum",
        "multipleOf",
        "pattern",
        "readOnly",
        "summary",
        "title",
        "writeOnly",
        "xml",
    }
    supported = {"enum", "format", "maxLength", "minLength", "nullable", "type"}
    unsupported = (set(left) | set(right)) - annotations - supported
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ValueError(
            f"Property '{field_name}' uses unsupported allOf constraint(s): {names}."
        )

    effective: dict[str, Any] = {}
    type_options = _intersect_property_type_options(
        left,
        right,
        field_name=field_name,
        ref_siblings_apply=ref_siblings_apply,
    )
    if type_options is not None:
        ordered_types = sorted(type_options, key=lambda value: (value == "null", value))
        if ref_siblings_apply:
            effective["type"] = (
                ordered_types[0] if len(ordered_types) == 1 else ordered_types
            )
        else:
            nullable = "null" in type_options
            non_null_types = [value for value in ordered_types if value != "null"]
            if not non_null_types:
                effective["type"] = "null"
            else:
                effective["type"] = (
                    non_null_types[0] if len(non_null_types) == 1 else non_null_types
                )
                if nullable:
                    effective["nullable"] = True

    for key, reducer in (("maxLength", min), ("minLength", max)):
        values = [schema[key] for schema in (left, right) if key in schema]
        if values:
            if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
                raise ValueError(
                    f"Property '{field_name}' has an invalid allOf {key} constraint."
                )
            effective[key] = reducer(values)

    formats = [schema["format"] for schema in (left, right) if schema.get("format")]
    if any(not isinstance(value, str) for value in formats):
        raise ValueError(
            f"Property '{field_name}' has an invalid allOf format constraint."
        )
    if len(set(formats)) > 1:
        raise ValueError(
            f"Property '{field_name}' has incompatible allOf format constraints."
        )
    if formats:
        effective["format"] = formats[0]

    enums = [schema["enum"] for schema in (left, right) if "enum" in schema]
    if enums:
        if any(not isinstance(values, list) for values in enums):
            raise ValueError(
                f"Property '{field_name}' has an invalid allOf enum constraint."
            )
        intersection = list(enums[0])
        for values in enums[1:]:
            intersection = [value for value in intersection if value in values]
        if not intersection:
            raise ValueError(
                f"Property '{field_name}' has incompatible allOf enum constraints."
            )
        effective["enum"] = intersection

    return effective


def _intersect_property_type_options(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    field_name: str,
    ref_siblings_apply: bool,
) -> set[str] | None:
    left_types = _property_type_options(
        left,
        field_name=field_name,
        ref_siblings_apply=ref_siblings_apply,
    )
    right_types = _property_type_options(
        right,
        field_name=field_name,
        ref_siblings_apply=ref_siblings_apply,
    )
    if left_types is None:
        return right_types
    if right_types is None:
        return left_types

    intersection = left_types & right_types
    if "number" in intersection:
        intersection.discard("integer")
    elif (
        "number" in left_types
        and "integer" in right_types
        or "integer" in left_types
        and "number" in right_types
    ):
        intersection.add("integer")
    if not intersection:
        raise ValueError(
            f"Property '{field_name}' has incompatible allOf type constraints."
        )
    return intersection


def _property_type_options(
    schema: dict[str, Any],
    *,
    field_name: str,
    ref_siblings_apply: bool,
) -> set[str] | None:
    options = _schema_type_options(schema.get("type"))
    if "type" in schema and options is None:
        raise ValueError(
            f"Property '{field_name}' has an invalid allOf type constraint."
        )
    if options is None:
        return None
    if not ref_siblings_apply and schema.get("nullable") is True:
        options.add("null")
    return options


def extract_entity_fields(
    schema_name: str,
    schema_def: dict,
    *,
    source_name: str | None = None,
    schemas: dict | None = None,
    diagnostic_schemas: dict[str, dict | bool] | None = None,
    warnings_out: list | None = None,
    ref_siblings_apply: bool = False,
    fail_on_unrepresentable_required: bool = False,
    resolve_nested_properties: bool = False,
    diagnose_nested_reference_failures: bool = False,
) -> list[CanonicalField]:
    """Extract canonical fields from a schema definition.

    Pass *schemas* (the full components/schemas dict) to enable resolution of
    $ref variants inside allOf/anyOf/oneOf, so inherited fields from base
    schemas (e.g. BaseEntity.createdAt) are included in the result.

    Pass *warnings_out* (a list) to collect warnings for unsupported constructs
    (deeply nested objects, oneOf/anyOf, arrays of objects). Fields that cannot
    be handled are skipped with a warning rather than causing silent failures.

    Phase 1a nested-object handling:
    - Arrays of scalars (string/int): emitted as list_string / list_integer
    - Single-level nested value objects: FLATTENED into parent (address.line1 -> addressLine1)
    - Deeper nesting or arrays of objects: WARNING + skip
    - oneOf/anyOf at field level: WARNING + skip
    """

    from appbuilder.metadata.models import CanonicalField

    if warnings_out is None:
        warnings_out = []

    if not resolve_nested_properties:
        return _extract_entity_fields_legacy_compatible(
            schema_name,
            schema_def,
            source_name=source_name,
            schemas=schemas,
            diagnostic_schemas=diagnostic_schemas,
            warnings_out=warnings_out,
            ref_siblings_apply=ref_siblings_apply,
            fail_on_unrepresentable_required=fail_on_unrepresentable_required,
            diagnose_nested_reference_failures=diagnose_nested_reference_failures,
        )

    for combiner in ("oneOf", "anyOf"):
        if schema_def.get(combiner):
            _append_unique_warning(
                warnings_out,
                f"schema '{schema_name}' uses unsupported top-level {combiner} polymorphism; "
                "schema skipped",
            )
            return []

    properties, required_fields = _collect_properties_and_required(
        schema_def,
        schemas=schemas,
        ref_siblings_apply=ref_siblings_apply,
    )
    for missing_name in sorted(required_fields - set(properties)):
        _handle_unrepresentable_field(
            schema_name=schema_name,
            field_path=missing_name,
            reason="is listed as required but has no matching property schema",
            effective_required=True,
            fail_on_unrepresentable_required=fail_on_unrepresentable_required,
            warnings_out=warnings_out,
        )
    if not properties:
        return []

    entity_name = _normalize_entity_name(schema_name)
    fields: list[CanonicalField] = []
    for index, (field_name, property_schema) in enumerate(properties.items()):
        effective_required = field_name in required_fields
        if not isinstance(property_schema, dict):
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_name,
                reason="uses a boolean or malformed schema with no representable canonical field",
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue

        resolved_schema: dict[str, Any] | bool = property_schema
        if schemas is not None:
            resolved_schema = _resolve_property_schema_for_extraction(
                property_schema,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
                field_name=field_name,
                strict=fail_on_unrepresentable_required and effective_required,
            )
        if not isinstance(resolved_schema, dict):
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_name,
                reason="resolves to a boolean schema with no representable canonical field",
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue

        openapi_type = _normalize_openapi_type(resolved_schema.get("type"))
        if any(key in resolved_schema for key in ("oneOf", "anyOf")):
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_name,
                reason="uses unsupported field-level oneOf/anyOf polymorphism",
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue

        if openapi_type == "array":
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_name,
                reason=(
                    "uses an unsupported array/collection shape that requires "
                    "collection-table or relationship modeling"
                ),
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue

        if openapi_type == "object" or isinstance(resolved_schema.get("properties"), dict):
            _flatten_single_level_object_fields(
                fields=fields,
                schema_name=schema_name,
                parent_field_name=field_name,
                parent_schema=resolved_schema,
                parent_required=effective_required,
                source_name=source_name,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue

        if not openapi_type and "allOf" in resolved_schema:
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_name,
                reason="uses an unsupported composed shape that cannot be represented safely",
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue

        fields.append(
            CanonicalField(
                name=field_name,
                type=openapi_type_to_canonical_type(
                    resolved_schema.get("type"),
                    resolved_schema.get("format"),
                ),
                is_id=_is_openapi_id_field(field_name, entity_name, is_first=index == 0),
                required=effective_required,
                max_length=resolved_schema.get("maxLength"),
                format=resolved_schema.get("format"),
                allowed_values=[
                    value
                    for value in resolved_schema.get("enum", [])
                    if isinstance(value, str)
                ],
                source_paths=[
                    f"{source_name}.openapi.{schema_name}.{field_name}"
                    if source_name
                    else f"openapi.{schema_name}.{field_name}"
                ],
            )
        )
    return fields


def _extract_entity_fields_legacy_compatible(
    schema_name: str,
    schema_def: dict,
    *,
    source_name: str | None,
    schemas: dict | None,
    diagnostic_schemas: dict[str, dict | bool] | None,
    warnings_out: list,
    ref_siblings_apply: bool,
    fail_on_unrepresentable_required: bool,
    diagnose_nested_reference_failures: bool,
) -> list[CanonicalField]:
    """Retain the approved CRUD field and diagnostic behavior.

    Passthrough operation extraction opts into the stricter reader-first path.
    CRUD entity ingestion deliberately keeps this established raw nested reader
    because resolving nested references would change its canonical persistence
    contract for existing OpenAPI inputs.
    """

    from appbuilder.metadata.models import CanonicalField

    for combiner in ("oneOf", "anyOf"):
        if schema_def.get(combiner):
            warnings_out.append(
                f"Field '{schema_name}': {combiner} / discriminator polymorphism is not supported "
                "in Phase 1a — schema skipped."
            )
            return []

    properties, required_fields = _collect_properties_and_required(
        schema_def,
        schemas=schemas,
        ref_siblings_apply=ref_siblings_apply,
    )
    if not properties:
        return []

    entity_name = _normalize_entity_name(schema_name)
    fields: list[CanonicalField] = []
    for index, (field_name, property_schema) in enumerate(properties.items()):
        if not isinstance(property_schema, dict):
            if fail_on_unrepresentable_required and field_name in required_fields:
                raise ValueError(
                    f"required field '{field_name}' uses a boolean or malformed schema "
                    "that has no representable canonical field"
                )
            continue

        resolved_schema = property_schema
        if schemas is not None:
            resolved_schema = _resolve_property_schema_for_extraction(
                property_schema,
                schemas=schemas,
                ref_siblings_apply=ref_siblings_apply,
                field_name=field_name,
                strict=(
                    fail_on_unrepresentable_required
                    and field_name in required_fields
                ),
            )

        if not isinstance(resolved_schema, dict):
            if fail_on_unrepresentable_required and field_name in required_fields:
                raise ValueError(
                    f"required field '{field_name}' resolves to a boolean schema "
                    "that has no representable canonical field"
                )
            continue

        openapi_type = _normalize_openapi_type(resolved_schema.get("type"))
        has_ref = "$ref" in property_schema

        if any(key in resolved_schema for key in ("oneOf", "anyOf")):
            warnings_out.append(
                f"Field '{field_name}' in '{schema_name}': oneOf/anyOf is not supported "
                "in Phase 1a — field skipped."
            )
            continue

        if openapi_type == "array":
            warnings_out.append(
                f"Field '{field_name}' in '{schema_name}': array/collection fields are not "
                "supported in Phase 1a (requires collection-table or relationship modeling) — "
                "field skipped."
            )
            continue

        if openapi_type == "object" or (has_ref and not openapi_type):
            nested_props = resolved_schema.get("properties", {})
            if not isinstance(nested_props, dict) or not nested_props:
                if fail_on_unrepresentable_required and field_name in required_fields:
                    raise ValueError(
                        f"required field '{field_name}' resolves to a schema with no "
                        "representable scalar type or object properties"
                    )
                warnings_out.append(
                    f"Field '{field_name}' in '{schema_name}': nested object has no properties — field skipped."
                )
                continue

            nested_required = set(resolved_schema.get("required", []))
            failed_nested_resolutions: set[str] = set()
            if diagnose_nested_reference_failures and diagnostic_schemas is not None:
                for nested_field_name, nested_prop in nested_props.items():
                    if not isinstance(nested_prop, dict) or not any(
                        key in nested_prop for key in ("$ref", "allOf")
                    ):
                        continue
                    field_path = f"{field_name}.{nested_field_name}"
                    try:
                        _resolve_property_schema_for_extraction(
                            nested_prop,
                            schemas=diagnostic_schemas,
                            ref_siblings_apply=ref_siblings_apply,
                            field_name=field_path,
                            strict=False,
                        )
                    except ValueError as exc:
                        failed_nested_resolutions.add(nested_field_name)
                        _handle_unrepresentable_field(
                            schema_name=schema_name,
                            field_path=field_path,
                            reason=f"cannot be resolved safely: {exc}",
                            effective_required=(field_name in required_fields)
                            and (nested_field_name in nested_required),
                            fail_on_unrepresentable_required=False,
                            warnings_out=warnings_out,
                        )

            has_deeper_nesting = any(
                (
                    isinstance(value, dict)
                    and (
                        _normalize_openapi_type(value.get("type")) in ("object", "array")
                        or "$ref" in value
                    )
                )
                for value in nested_props.values()
                if isinstance(value, dict)
            )
            if has_deeper_nesting:
                if not failed_nested_resolutions:
                    warnings_out.append(
                        f"Field '{field_name}' in '{schema_name}': deeply nested object graph "
                        "(depth > 1) is not supported in Phase 1a — field skipped (requires Phase 1b relationship modeling)."
                    )
                continue

            for nested_field_name, nested_prop in nested_props.items():
                if (
                    not isinstance(nested_prop, dict)
                    or nested_field_name in failed_nested_resolutions
                ):
                    continue
                flattened_name = (
                    field_name
                    + nested_field_name[:1].upper()
                    + nested_field_name[1:]
                )
                fields.append(
                    CanonicalField(
                        name=flattened_name,
                        type=openapi_type_to_canonical_type(
                            nested_prop.get("type"),
                            nested_prop.get("format"),
                        ),
                        is_id=False,
                        required=(field_name in required_fields)
                        and (nested_field_name in nested_required),
                        max_length=nested_prop.get("maxLength"),
                        format=nested_prop.get("format"),
                        source_paths=[
                            f"{source_name}.openapi.{schema_name}.{field_name}.{nested_field_name}"
                            if source_name
                            else f"openapi.{schema_name}.{field_name}.{nested_field_name}"
                        ],
                    )
                )
            continue

        fields.append(
            CanonicalField(
                name=field_name,
                type=openapi_type_to_canonical_type(
                    resolved_schema.get("type"),
                    resolved_schema.get("format"),
                ),
                is_id=_is_openapi_id_field(
                    field_name,
                    entity_name,
                    is_first=index == 0,
                ),
                required=field_name in required_fields,
                max_length=resolved_schema.get("maxLength"),
                format=resolved_schema.get("format"),
                allowed_values=[
                    value
                    for value in resolved_schema.get("enum", [])
                    if isinstance(value, str)
                ],
                source_paths=[
                    f"{source_name}.openapi.{schema_name}.{field_name}"
                    if source_name
                    else f"openapi.{schema_name}.{field_name}"
                ],
            )
        )
    return fields


def _flatten_single_level_object_fields(
    *,
    fields: list[CanonicalField],
    schema_name: str,
    parent_field_name: str,
    parent_schema: dict[str, Any],
    parent_required: bool,
    source_name: str | None,
    schemas: dict[str, dict | bool] | None,
    ref_siblings_apply: bool,
    fail_on_unrepresentable_required: bool,
    warnings_out: list[str],
) -> None:
    from appbuilder.metadata.models import CanonicalField

    nested_props, nested_required = _collect_properties_and_required(
        parent_schema,
        schemas=schemas,
        ref_siblings_apply=ref_siblings_apply,
    )
    if not nested_props:
        _handle_unrepresentable_field(
            schema_name=schema_name,
            field_path=parent_field_name,
            reason="resolves to an object with no representable properties",
            effective_required=parent_required,
            fail_on_unrepresentable_required=fail_on_unrepresentable_required,
            warnings_out=warnings_out,
        )
        return

    for missing_name in sorted(nested_required - set(nested_props)):
        field_path = f"{parent_field_name}.{missing_name}"
        _handle_unrepresentable_field(
            schema_name=schema_name,
            field_path=field_path,
            reason="is listed as required but has no matching property schema",
            effective_required=parent_required,
            fail_on_unrepresentable_required=fail_on_unrepresentable_required,
            warnings_out=warnings_out,
        )

    if (
        fail_on_unrepresentable_required
        and parent_required
        and not nested_required.intersection(nested_props)
    ):
        _handle_unrepresentable_field(
            schema_name=schema_name,
            field_path=parent_field_name,
            reason=(
                "is a required object whose presence cannot be preserved after flattening "
                "because all nested properties are optional"
            ),
            effective_required=True,
            fail_on_unrepresentable_required=True,
            warnings_out=warnings_out,
        )
        return

    for nested_field_name, nested_prop in nested_props.items():
        field_path = f"{parent_field_name}.{nested_field_name}"
        effective_required = parent_required and nested_field_name in nested_required
        if not isinstance(nested_prop, dict):
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_path,
                reason="uses a boolean or malformed schema with no representable canonical field",
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue

        resolved_nested: dict[str, Any] | bool = nested_prop
        if schemas is not None:
            try:
                resolved_nested = _resolve_property_schema_for_extraction(
                    nested_prop,
                    schemas=schemas,
                    ref_siblings_apply=ref_siblings_apply,
                    field_name=field_path,
                    strict=fail_on_unrepresentable_required and effective_required,
                )
            except ValueError as exc:
                _handle_unrepresentable_field(
                    schema_name=schema_name,
                    field_path=field_path,
                    reason=f"cannot be resolved safely: {exc}",
                    effective_required=effective_required,
                    fail_on_unrepresentable_required=(
                        fail_on_unrepresentable_required
                    ),
                    warnings_out=warnings_out,
                )
                continue
        if not isinstance(resolved_nested, dict):
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_path,
                reason="resolves to a boolean schema with no representable canonical field",
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue

        nested_type = _normalize_openapi_type(resolved_nested.get("type"))
        if any(key in resolved_nested for key in ("oneOf", "anyOf")):
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_path,
                reason="uses unsupported field-level oneOf/anyOf polymorphism",
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue
        if nested_type == "array":
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_path,
                reason=(
                    "uses an unsupported array/collection shape that requires "
                    "collection-table or relationship modeling"
                ),
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue
        if nested_type == "object" or isinstance(resolved_nested.get("properties"), dict):
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_path,
                reason="uses an unsupported object graph deeper than one flattened level",
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue
        if not nested_type and "allOf" in resolved_nested:
            _handle_unrepresentable_field(
                schema_name=schema_name,
                field_path=field_path,
                reason="uses an unsupported composed shape that cannot be represented safely",
                effective_required=effective_required,
                fail_on_unrepresentable_required=fail_on_unrepresentable_required,
                warnings_out=warnings_out,
            )
            continue

        flattened_name = (
            parent_field_name
            + nested_field_name[:1].upper()
            + nested_field_name[1:]
        )
        fields.append(
            CanonicalField(
                name=flattened_name,
                type=openapi_type_to_canonical_type(
                    resolved_nested.get("type"),
                    resolved_nested.get("format"),
                ),
                is_id=False,
                required=effective_required,
                max_length=resolved_nested.get("maxLength"),
                format=resolved_nested.get("format"),
                allowed_values=[
                    value
                    for value in resolved_nested.get("enum", [])
                    if isinstance(value, str)
                ],
                source_paths=[
                    f"{source_name}.openapi.{schema_name}.{field_path}"
                    if source_name
                    else f"openapi.{schema_name}.{field_path}"
                ],
            )
        )


def _handle_unrepresentable_field(
    *,
    schema_name: str,
    field_path: str,
    reason: str,
    effective_required: bool,
    fail_on_unrepresentable_required: bool,
    warnings_out: list[str],
) -> None:
    if fail_on_unrepresentable_required and effective_required:
        raise ValueError(f"required field '{field_path}' {reason}")
    _append_unique_warning(
        warnings_out,
        f"field '{field_path}' in schema '{schema_name}' {reason}; field skipped",
    )


def _append_unique_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def _resolve_property_schema_for_extraction(
    schema: dict[str, Any],
    *,
    schemas: dict[str, dict | bool],
    ref_siblings_apply: bool,
    field_name: str,
    strict: bool = False,
    seen_refs: frozenset[str] = frozenset(),
) -> dict[str, Any] | bool:
    """Resolve references and supported scalar allOf constraints for one property."""

    resolved = schema
    nested_seen_refs = seen_refs
    if "$ref" in resolved:
        ref = resolved.get("$ref")
        if isinstance(ref, str) and ref in seen_refs:
            raise ValueError(
                f"Cyclic local OpenAPI schema reference detected at '{ref}'."
            )
        resolved = _resolve_local_schema_reference(
            resolved,
            schemas=schemas,
            ref_siblings_apply=ref_siblings_apply,
            seen_refs=seen_refs,
        )
        if isinstance(ref, str):
            nested_seen_refs = seen_refs | {ref}

    if isinstance(resolved, bool):
        return resolved

    variants = resolved.get("allOf")
    if not isinstance(variants, list):
        return resolved

    direct = {key: value for key, value in resolved.items() if key != "allOf"}
    resolved_variants: list[dict[str, Any]] = []
    for variant in variants:
        if variant is True:
            continue
        if variant is False:
            if strict:
                raise ValueError(
                    f"field '{field_name}' has an allOf branch that rejects every value"
                )
            return resolved
        if not isinstance(variant, dict):
            if strict:
                raise ValueError(
                    f"field '{field_name}' has a malformed allOf branch"
                )
            return resolved
        resolved_variant = _resolve_property_schema_for_extraction(
            variant,
            schemas=schemas,
            ref_siblings_apply=ref_siblings_apply,
            field_name=field_name,
            strict=strict,
            seen_refs=nested_seen_refs,
        )
        if resolved_variant is True:
            continue
        if resolved_variant is False:
            if strict:
                raise ValueError(
                    f"field '{field_name}' has an allOf branch that rejects every value"
                )
            return resolved
        resolved_variants.append(resolved_variant)

    candidates = [direct, *resolved_variants]
    if any(_schema_has_object_shape(candidate) for candidate in candidates):
        properties, required = _collect_properties_and_required(
            resolved,
            schemas=schemas,
            ref_siblings_apply=ref_siblings_apply,
        )
        if not properties:
            return resolved
        return {
            "type": "object",
            "properties": properties,
            "required": sorted(required),
        }

    effective: dict[str, Any] = {}
    for candidate in candidates:
        try:
            effective = _compose_supported_property_conjunction(
                effective,
                candidate,
                field_name=field_name,
                ref_siblings_apply=ref_siblings_apply,
            )
        except ValueError:
            if strict:
                raise
            return resolved
    return effective


def _schema_has_object_shape(schema: dict[str, Any]) -> bool:
    return (
        _normalize_openapi_type(schema.get("type")) == "object"
        or isinstance(schema.get("properties"), dict)
        or isinstance(schema.get("required"), list)
    )


def _resolve_local_schema_reference(
    schema: dict[str, Any],
    *,
    schemas: dict[str, dict | bool],
    ref_siblings_apply: bool,
    seen_refs: frozenset[str] = frozenset(),
) -> dict[str, Any] | bool:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    if not ref.startswith("#/components/schemas/"):
        raise ValueError(f"Unsupported non-local OpenAPI schema reference '{ref}'.")
    if ref in seen_refs:
        raise ValueError(f"Cyclic local OpenAPI schema reference detected at '{ref}'.")

    target = schemas.get(_schema_name_from_ref(ref))
    if not isinstance(target, (dict, bool)):
        raise ValueError(f"OpenAPI schema reference '{ref}' does not resolve to a schema.")
    if isinstance(target, bool):
        if not ref_siblings_apply:
            return target
        siblings = {key: value for key, value in schema.items() if key != "$ref"}
        if not target:
            return False
        return siblings or True
    resolved = _resolve_local_schema_reference(
        target,
        schemas=schemas,
        ref_siblings_apply=ref_siblings_apply,
        seen_refs=seen_refs | {ref},
    )
    if not ref_siblings_apply:
        return resolved

    if isinstance(resolved, bool):
        if not resolved:
            return False
        siblings = {key: value for key, value in schema.items() if key != "$ref"}
        return siblings or True

    siblings = {key: value for key, value in schema.items() if key != "$ref"}
    return _compose_ref_sibling_constraints(resolved, siblings, ref=ref)


def _compose_ref_sibling_constraints(
    resolved: dict[str, Any],
    siblings: dict[str, Any],
    *,
    ref: str,
) -> dict[str, Any]:
    effective = dict(resolved)
    ignored_annotations = {
        "$anchor",
        "$comment",
        "$defs",
        "$dynamicAnchor",
        "$id",
        "$schema",
        "default",
        "deprecated",
        "description",
        "examples",
        "externalDocs",
        "nullable",
        "readOnly",
        "summary",
        "title",
        "writeOnly",
        "xml",
    }
    for key, sibling_value in siblings.items():
        if key in ignored_annotations:
            continue
        if key == "maxLength":
            existing = effective.get(key)
            effective[key] = (
                min(existing, sibling_value)
                if isinstance(existing, int) and isinstance(sibling_value, int)
                else sibling_value
            )
            continue
        if key == "minLength":
            existing = effective.get(key)
            effective[key] = (
                max(existing, sibling_value)
                if isinstance(existing, int) and isinstance(sibling_value, int)
                else sibling_value
            )
            continue
        if key == "enum":
            existing = effective.get(key)
            if isinstance(existing, list) and isinstance(sibling_value, list):
                effective[key] = [value for value in existing if value in sibling_value]
                if not effective[key]:
                    raise ValueError(
                        f"OpenAPI schema reference '{ref}' has incompatible enum siblings."
                    )
            else:
                effective[key] = sibling_value
            continue
        if key == "type":
            effective[key] = _intersect_schema_types(effective.get(key), sibling_value, ref=ref)
            continue
        if key == "format":
            existing = effective.get(key)
            if existing is not None and sibling_value is not None and existing != sibling_value:
                raise ValueError(
                    f"OpenAPI schema reference '{ref}' has incompatible format siblings."
                )
            effective[key] = sibling_value if sibling_value is not None else existing
            continue
        raise ValueError(
            f"OpenAPI 3.1 schema reference '{ref}' has sibling constraint '{key}' that "
            "cannot be represented safely."
        )
    return effective


def _intersect_schema_types(existing: Any, sibling: Any, *, ref: str) -> Any:
    existing_types = _schema_type_options(existing)
    sibling_types = _schema_type_options(sibling)
    if existing_types is None:
        return sibling
    if sibling_types is None:
        return existing

    intersection = existing_types & sibling_types
    if "number" in intersection:
        intersection.discard("integer")
    elif (
        "number" in existing_types
        and "integer" in sibling_types
        or "integer" in existing_types
        and "number" in sibling_types
    ):
        intersection.add("integer")
    if not intersection:
        raise ValueError(f"OpenAPI schema reference '{ref}' has incompatible type siblings.")
    ordered = sorted(intersection, key=lambda value: (value == "null", value))
    return ordered[0] if len(ordered) == 1 else ordered


def _schema_type_options(value: Any) -> set[str] | None:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return set(value)
    return None


def inventory_openapi_operations(spec: dict) -> OrderedDict[str, list[str]]:
    """Group discovered operations by resource name for assessment output."""

    groups: OrderedDict[str, list[str]] = OrderedDict()
    for path, method, _operation in _iter_path_operations(spec):
        group = _resource_group_name(path)
        groups.setdefault(group, []).append(f"{method.upper()} {path}")
    return groups


def summarize_openapi_assessment(spec: dict, spec_url: str) -> dict[str, Any]:
    """Build a structured assessment summary for CLI output."""

    info = spec.get("info", {}) if isinstance(spec.get("info"), dict) else {}
    classifications = classify_openapi_schemas(spec)
    entities = ingest_openapi_entities(spec, interface_name="assessment")
    operations = inventory_openapi_operations(spec)

    return {
        "title": info.get("title", "Unknown API"),
        "version": info.get("version", "unknown"),
        "spec_url": spec_url,
        "domain_entities": [
            {
                "name": entity.name,
                "field_count": len(entity.fields),
                "id_field": next(
                    (field.name for field in entity.fields if field.is_id),
                    None,
                ),
            }
            for entity in entities
        ],
        "dto_schemas": [
            schema_name
            for schema_name, label in classifications.items()
            if label == "dto"
        ],
        "infrastructure_schemas": [
            schema_name
            for schema_name, label in classifications.items()
            if label == "infrastructure"
        ],
        "operations": operations,
        "summary": {
            "domain_entities": len(entities),
            "dtos": sum(1 for label in classifications.values() if label == "dto"),
            "infrastructure": sum(
                1 for label in classifications.values() if label == "infrastructure"
            ),
            "coverage": _estimate_coverage(spec, entities, operations),
        },
    }


def openapi_type_to_canonical_type(
    openapi_type: str | None | list[str],
    openapi_format: str | None,
) -> CanonicalFieldType:
    from appbuilder.metadata.models import CanonicalFieldType

    normalized_type = _normalize_openapi_type(openapi_type)
    normalized_format = (openapi_format or "").lower()

    if normalized_type == "string":
        if normalized_format == "date-time":
            return CanonicalFieldType.DATETIME
        if normalized_format == "date":
            return CanonicalFieldType.DATE
        return CanonicalFieldType.STRING
    if normalized_type == "integer":
        return CanonicalFieldType.INTEGER
    if normalized_type == "number":
        return CanonicalFieldType.DECIMAL
    if normalized_type == "boolean":
        return CanonicalFieldType.BOOLEAN
    return CanonicalFieldType.STRING


def _normalize_openapi_type(openapi_type: Any) -> str:
    if isinstance(openapi_type, str):
        return openapi_type.lower()
    if isinstance(openapi_type, list):
        for candidate in openapi_type:
            if isinstance(candidate, str) and candidate.lower() != "null":
                return candidate.lower()
        return ""
    return ""


def _component_schemas(spec: dict) -> dict[str, dict]:
    components = spec.get("components", {})
    if not isinstance(components, dict):
        return {}
    schemas = components.get("schemas", {})
    if not isinstance(schemas, dict):
        return {}
    return {
        schema_name: schema_def
        for schema_name, schema_def in schemas.items()
        if isinstance(schema_name, str) and isinstance(schema_def, dict)
    }


def _component_schema_nodes(spec: dict) -> dict[str, dict | bool]:
    components = spec.get("components", {})
    if not isinstance(components, dict):
        return {}
    schemas = components.get("schemas", {})
    if not isinstance(schemas, dict):
        return {}
    return {
        schema_name: schema_def
        for schema_name, schema_def in schemas.items()
        if isinstance(schema_name, str) and isinstance(schema_def, (dict, bool))
    }


def _openapi_ref_siblings_apply(spec: dict) -> bool:
    version = spec.get("openapi")
    return isinstance(version, str) and version.startswith("3.1")


def _iter_path_operations(spec: dict) -> list[tuple[str, str, dict[str, Any]]]:
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return []

    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method in _CRUD_HTTP_METHODS:
            operation = path_item.get(method)
            if isinstance(operation, dict):
                operations.append((path, method, operation))
    return operations


def _schema_has_properties(schema_def: dict) -> bool:
    """Return True if a schema defines properties directly or inside allOf/anyOf/oneOf.

    Spring Boot / Springdoc commonly uses allOf for inheritance:
      allOf:
        - $ref: '#/components/schemas/BaseEntity'
        - type: object
          properties: {id: ...}
    Checking only schema_def.get("properties") misses these schemas.
    """
    if isinstance(schema_def.get("properties"), dict):
        return True
    for combiner in ("allOf", "anyOf", "oneOf"):
        variants = schema_def.get(combiner)
        if isinstance(variants, list):
            for v in variants:
                if isinstance(v, dict) and isinstance(v.get("properties"), dict):
                    return True
    return False


def _response_schema_refs(spec: dict) -> set[str]:
    refs: set[str] = set()
    for _path, _method, operation in _iter_path_operations(spec):
        for schema in _response_schemas(operation):
            refs.update(_extract_schema_refs(schema))
    return refs


def _extract_schema_refs(schema: Any) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return {_schema_name_from_ref(ref)}

    refs: set[str] = set()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for property_schema in properties.values():
            refs.update(_extract_schema_refs(property_schema))

    items = schema.get("items")
    if isinstance(items, dict):
        refs.update(_extract_schema_refs(items))

    for key in ("allOf", "anyOf", "oneOf"):
        variants = schema.get(key, [])
        if isinstance(variants, list):
            for variant in variants:
                refs.update(_extract_schema_refs(variant))
    return refs


def _schema_name_from_ref(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _is_infrastructure_schema_name(schema_name: str) -> bool:
    if schema_name.startswith("Page"):
        return True
    if schema_name in _INFRASTRUCTURE_NAMES:
        return True
    return schema_name.endswith(("Error", "Exception"))


def _merge_fields(
    entity_fields: OrderedDict[str, OrderedDict[str, CanonicalField]],
    entity_name: str,
    fields: list[CanonicalField],
) -> None:
    from appbuilder.metadata.models import CanonicalFieldType

    if not fields:
        return
    field_lookup = entity_fields.setdefault(entity_name, OrderedDict())
    for field in fields:
        existing = field_lookup.get(field.name)
        if existing is None:
            field_lookup[field.name] = field.model_copy(deep=True)
            continue

        if not existing.is_id and field.is_id:
            existing.is_id = True
        if field.required:
            existing.required = True
        if existing.max_length is None:
            existing.max_length = field.max_length
        elif field.max_length is not None:
            existing.max_length = min(existing.max_length, field.max_length)
        if existing.format is None:
            existing.format = field.format
        if field.type != CanonicalFieldType.STRING or existing.type == CanonicalFieldType.STRING:
            existing.type = field.type
        for allowed_value in field.allowed_values:
            if allowed_value not in existing.allowed_values:
                existing.allowed_values.append(allowed_value)
        for source_path in field.source_paths:
            if source_path not in existing.source_paths:
                existing.source_paths.append(source_path)


def _normalize_entity_name(name: str) -> str:
    normalized = re.sub(r"(Request|Response)$", "", name)
    normalized = re.sub(r"^(Create|Update|Delete|Get|List)", "", normalized)
    parts = re.split(r"[-_\s]+", normalized)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def _resource_entity_name_from_path(path: str) -> str | None:
    segments = [segment for segment in path.split("/") if segment and not segment.startswith("{")]
    if not segments:
        return None
    return _normalize_entity_name(_singularize(segments[0]))


def _is_create_post_path(path: str) -> bool:
    """Return True when the path has no path-parameter segments.

    A create POST targets a collection endpoint (/customers or /v1/customers).
    A command/action POST targets a specific resource (/customers/{id}/close).
    The presence of any {param} segment is the distinguishing signal.
    """
    return "{" not in path


def _resource_group_name(path: str) -> str:
    segments = [segment for segment in path.split("/") if segment and not segment.startswith("{")]
    if not segments:
        return "Other"
    normalized = re.sub(r"[-_]+", " ", segments[0]).strip()
    return normalized[:1].upper() + normalized[1:]


def _singularize(value: str) -> str:
    if value.endswith("ies"):
        return value[:-3] + "y"
    if value.endswith("ses"):
        return value[:-2]
    if value.endswith("s") and len(value) > 1:
        return value[:-1]
    return value


def _request_body_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    request_body = operation.get("requestBody", {})
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content", {})
    if not isinstance(content, dict):
        return None
    for media_type in ("application/json", "application/*+json"):
        media = content.get(media_type)
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            return media["schema"]
    return None


def _response_schemas(operation: dict[str, Any]) -> list[dict[str, Any]]:
    responses = operation.get("responses", {})
    if not isinstance(responses, dict):
        return []

    schemas: list[dict[str, Any]] = []
    for status_code, response in responses.items():
        if not str(status_code).startswith("2") or not isinstance(response, dict):
            continue
        content = response.get("content", {})
        if not isinstance(content, dict):
            continue
        # Check specific types first, then fall back to wildcard (*/*).
        # Spring Boot / Springdoc defaults to */* as the response content-type.
        for media_type in ("application/json", "application/*+json", "*/*"):
            media = content.get(media_type)
            if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                schemas.append(media["schema"])
                break
    return schemas


def _schemas_from_schema(
    schema: dict[str, Any],
    *,
    schemas: dict[str, dict],
    fallback_name: str,
    ref_siblings_apply: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        schema_name = _schema_name_from_ref(ref)
        schema_def = _resolve_local_schema_reference(
            schema,
            schemas=schemas,
            ref_siblings_apply=ref_siblings_apply,
        )
        return [(schema_name, schema_def)]

    if isinstance(schema.get("properties"), dict):
        return [(fallback_name, schema)]

    if isinstance(schema.get("items"), dict):
        return _schemas_from_schema(
            schema["items"],
            schemas=schemas,
            fallback_name=fallback_name,
            ref_siblings_apply=ref_siblings_apply,
        )

    for key in ("allOf", "anyOf", "oneOf"):
        variants = schema.get(key)
        if not isinstance(variants, list):
            continue
        collected: list[tuple[str, dict[str, Any]]] = []
        for variant in variants:
            if isinstance(variant, dict):
                collected.extend(
                    _schemas_from_schema(
                        variant,
                        schemas=schemas,
                        fallback_name=fallback_name,
                        ref_siblings_apply=ref_siblings_apply,
                    )
                )
        if collected:
            return collected
    return []


def _entity_schemas_from_response_schema(
    schema: dict[str, Any],
    *,
    schemas: dict[str, dict],
    fallback_name: str,
    ref_siblings_apply: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    collected = _schemas_from_schema(
        schema,
        schemas=schemas,
        fallback_name=fallback_name,
        ref_siblings_apply=ref_siblings_apply,
    )
    if not collected:
        return []

    unwrapped: list[tuple[str, dict[str, Any]]] = []
    for schema_name, schema_def in collected:
        envelope_candidates = _response_envelope_payload_schemas(
            schema_name,
            schema_def,
            schemas=schemas,
            ref_siblings_apply=ref_siblings_apply,
        )
        if envelope_candidates:
            unwrapped.extend(envelope_candidates)
            continue
        unwrapped.append((schema_name, schema_def))
    return unwrapped


def _response_envelope_payload_schemas(
    schema_name: str,
    schema_def: dict[str, Any],
    *,
    schemas: dict[str, dict],
    ref_siblings_apply: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    properties, _required = _collect_properties_and_required(
        schema_def,
        schemas=schemas,
        ref_siblings_apply=ref_siblings_apply,
    )
    if not properties:
        return []

    payload_candidates: list[tuple[str, dict[str, Any]]] = []
    payload_keys: set[str] = set()

    for key in _RESPONSE_ENVELOPE_ARRAY_KEYS:
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict):
            continue
        items = property_schema.get("items")
        if not isinstance(items, dict):
            continue
        payload_keys.add(key)
        payload_candidates.extend(
            _schemas_from_schema(
                items,
                schemas=schemas,
                fallback_name=_singularize(schema_name),
                ref_siblings_apply=ref_siblings_apply,
            )
        )

    for key in _RESPONSE_ENVELOPE_OBJECT_KEYS:
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict):
            continue
        payload_keys.add(key)
        payload_candidates.extend(
            _schemas_from_schema(
                property_schema,
                schemas=schemas,
                fallback_name=_singularize(schema_name),
                ref_siblings_apply=ref_siblings_apply,
            )
        )

    if not payload_candidates:
        return []

    other_keys = {key for key in properties if key not in payload_keys}
    if other_keys and not other_keys.issubset(_RESPONSE_ENVELOPE_METADATA_KEYS):
        return []

    deduped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for candidate_name, candidate_schema in payload_candidates:
        deduped.setdefault(candidate_name, candidate_schema)
    return list(deduped.items())


def _is_openapi_id_field(field_name: str, entity_name: str, *, is_first: bool) -> bool:
    normalized_field_name = field_name.lower()
    normalized_entity_name = entity_name.lower()

    if normalized_field_name == "id":
        return True
    if not normalized_field_name.endswith("id"):
        return False
    return is_first or normalized_entity_name in normalized_field_name


def _estimate_coverage(
    spec: dict,
    entities: list[CanonicalEntity],
    operations: OrderedDict[str, list[str]],
) -> str:
    if not entities:
        return "~0% (no domain entities classified)"

    operation_names: list[str] = []
    for _path, _method, operation in _iter_path_operations(spec):
        operation_id = operation.get("operationId")
        if isinstance(operation_id, str):
            operation_names.append(operation_id.lower())

    if operation_names and any(
        keyword in operation_name
        for operation_name in operation_names
        for keyword in _COMPLEX_OPERATION_KEYWORDS
    ):
        return "~50% (mixed CRUD and domain-specific operations; manual business logic expected)"

    crud_like_methods = {"GET", "POST", "PUT", "DELETE"}
    all_operations = [item for items in operations.values() for item in items]
    if all_operations and all(item.split(" ", 1)[0] in crud_like_methods for item in all_operations):
        return "~90% (CRUD-complete entities, no complex business logic detected)"

    return "~70% (core contract structure looks compatible; some manual logic may be required)"
