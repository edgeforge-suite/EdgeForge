"""Shared generation helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from appbuilder.core.sql_safety import validate_staging_ddl
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    HttpMethod,
    MetadataProject,
    ResponseShape,
)

from .audit import render_generated_file_header

JAVA_RESERVED_IDENTIFIERS = frozenset(
    {
        "abstract",
        "assert",
        "boolean",
        "break",
        "byte",
        "case",
        "catch",
        "char",
        "class",
        "const",
        "continue",
        "default",
        "do",
        "double",
        "else",
        "enum",
        "extends",
        "final",
        "finally",
        "float",
        "for",
        "goto",
        "if",
        "implements",
        "import",
        "instanceof",
        "int",
        "interface",
        "long",
        "native",
        "new",
        "package",
        "private",
        "protected",
        "public",
        "return",
        "short",
        "static",
        "strictfp",
        "super",
        "switch",
        "synchronized",
        "this",
        "throw",
        "throws",
        "transient",
        "try",
        "void",
        "volatile",
        "while",
        "_",
        "true",
        "false",
        "null",
    }
)


def base_package(metadata: MetadataProject) -> str:
    return f"com.appbuilder.{to_snake_case(metadata.bounded_context)}"


def package_path(package_name: str) -> Path:
    return Path(*package_name.split("."))


def to_pascal_case(value: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", value)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def spec_route_base_path(path: str) -> str:
    """Return the route base before the first path parameter segment.

    Examples::

        spec_route_base_path("/pet/{petId}")           -> "/pet"
        spec_route_base_path("/international-payments") -> "/international-payments"
        spec_route_base_path("/")                       -> "/"

    This is the canonical shared implementation used by both java_emitter and
    ui_emitter when deriving the controller / dashboard route base from a spec
    path.  Both emitters must call this function so that any future change to
    the extraction logic is applied consistently in one place.
    """
    marker = path.find("/{")
    if marker == -1:
        return path.rstrip("/") or "/"
    return path[:marker] or "/"


def spec_entity_route_base_candidate(
    *,
    path: str | None,
    http_method: HttpMethod | None,
    response_shape: ResponseShape | None,
    path_parameter_count: int,
) -> str | None:
    """Return an OpenAPI-derived entity route base when the path is safe.

    Collection routes and simple item routes define an entity controller base.
    Nested action routes and path-filtered lists can still be emitted as
    operation methods, but they must not re-root unrelated fallback CRUD routes.
    """
    if not path or http_method is None:
        return None
    if http_method == HttpMethod.POST and path_parameter_count == 0:
        return spec_route_base_path(path)
    if http_method == HttpMethod.GET and response_shape == ResponseShape.SINGLE and path_parameter_count == 1:
        return spec_route_base_path(path)
    if http_method == HttpMethod.GET and response_shape == ResponseShape.LIST and path_parameter_count == 0:
        return spec_route_base_path(path)
    if http_method in {HttpMethod.PUT, HttpMethod.DELETE} and path_parameter_count == 1:
        return spec_route_base_path(path)
    return None


def compatible_read_route_base(candidates: list[tuple[str, bool]]) -> str | None:
    """Allow static list subroutes without re-rooting the other CRUD routes."""
    bases = {base for base, _ in candidates}
    anchors = {base for base, is_list in candidates if not is_list}
    if len(anchors) > 1 or not bases:
        return None
    base = next(iter(anchors)) if anchors else min(bases, key=lambda value: (len(value), value))
    return base if all(value == base or value.startswith(base + "/") for value in bases) else None


def supports_spec_route(
    *,
    path: str | None,
    http_method: HttpMethod | None,
    response_shape: ResponseShape | None,
    path_parameter_count: int,
) -> bool:
    """Return True when an operation can preserve a shared spec route base.

    The current supported cases are:
    - POST collection routes with no path parameters, e.g. ``POST /pet``
    - GET single-resource routes with exactly one path parameter, e.g.
      ``GET /pet/{petId}``
    - GET collection list routes with no path parameters, e.g.
      ``GET /pet``
    - GET path-filtered list routes with exactly one path parameter, e.g.
      ``GET /accounts/{accountId}/transactions``
    - PUT/DELETE item routes with exactly one path parameter, e.g.
      ``PUT /pet/{petId}``
    """
    if not path or http_method is None:
        return False
    if http_method == HttpMethod.POST:
        return path_parameter_count == 0
    if http_method == HttpMethod.GET and response_shape == ResponseShape.SINGLE:
        return path_parameter_count == 1
    if http_method == HttpMethod.GET and response_shape == ResponseShape.LIST:
        return path_parameter_count in {0, 1}
    if http_method in {HttpMethod.PUT, HttpMethod.DELETE}:
        return path_parameter_count == 1
    return False


def to_snake_case(value: str) -> str:
    with_underscores = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", with_underscores)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized.lower()


_STAGING_OPERATIONAL_COLUMN_ROLES = {
    "stagingrowid": "staging_row_id",
    "runid": "run_id",
    "eodrunid": "run_id",
    "businessdate": "business_date",
    "stagingstatus": "staging_status",
    "createdat": "created_at",
    "createdtimestamp": "created_at",
}


def normalize_staging_column_name(column_name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", column_name.lower())


def staging_operational_column_role(column_name: str) -> str | None:
    return _STAGING_OPERATIONAL_COLUMN_ROLES.get(normalize_staging_column_name(column_name))


def parse_sql_table_columns(
    ddl_content: str,
    *,
    database: str,
) -> dict[str, dict[str, Any]]:
    """Return columns from the same strict model used at the ingest boundary."""

    validated = validate_staging_ddl(
        ddl_content,
        handoff_name="staging metadata",
        database=database,
    )
    return {
        column.name: {
            "raw_type": column.raw_type,
            "max_length": column.max_length,
            "required": column.required,
            "primary_key": column.primary_key,
        }
        for column in validated.columns
    }


def xml_mapping_types_compatible(
    *,
    direction: str,
    xml_field: dict,
    canonical_field: CanonicalField,
) -> bool:
    """Return whether an XML/SOAP scalar field can map to a canonical field."""

    xml_type = str(xml_field.get("type") or "string").lower()
    canonical_type = canonical_field.type
    if xml_field.get("enum_values"):
        return canonical_type == CanonicalFieldType.STRING
    if direction == "upstream":
        if canonical_type == CanonicalFieldType.STRING:
            return True
        if canonical_type == CanonicalFieldType.INTEGER:
            return xml_type in {"string", "integer", "int", "long"}
        if canonical_type == CanonicalFieldType.DECIMAL:
            return xml_type in {"string", "integer", "int", "long", "decimal"}
        if canonical_type == CanonicalFieldType.BOOLEAN:
            return xml_type in {"string", "boolean"}
        if canonical_type == CanonicalFieldType.DATE:
            return xml_type in {"string", "date"}
        if canonical_type == CanonicalFieldType.DATETIME:
            return xml_type in {"string", "datetime"}
        return False
    if xml_type == "string":
        return True
    if xml_type in {"integer", "int", "long"}:
        return canonical_type in {CanonicalFieldType.STRING, CanonicalFieldType.INTEGER}
    if xml_type == "decimal":
        return canonical_type in {
            CanonicalFieldType.STRING,
            CanonicalFieldType.INTEGER,
            CanonicalFieldType.DECIMAL,
        }
    if xml_type == "boolean":
        return canonical_type in {CanonicalFieldType.STRING, CanonicalFieldType.BOOLEAN}
    if xml_type == "date":
        return canonical_type in {CanonicalFieldType.STRING, CanonicalFieldType.DATE}
    if xml_type == "datetime":
        return canonical_type in {CanonicalFieldType.STRING, CanonicalFieldType.DATETIME}
    return False


def xml_field_type_label(field: dict) -> str:
    if field.get("enum_values"):
        return "enum"
    return str(field.get("type") or "string")


def to_java_class_name(value: str, *, fallback: str = "GeneratedType") -> str:
    return _to_java_identifier(value, fallback=fallback, upper_camel=True)


def to_java_method_name(value: str, *, fallback: str = "generatedOperation") -> str:
    return _to_java_identifier(value, fallback=fallback, upper_camel=False)


def _to_java_identifier(value: str, *, fallback: str, upper_camel: bool) -> str:
    candidate = to_pascal_case(value)
    if not candidate:
        candidate = to_pascal_case(fallback)
    if not candidate:
        candidate = "GeneratedValue" if upper_camel else "generatedValue"

    if upper_camel:
        normalized = candidate
    else:
        normalized = candidate[:1].lower() + candidate[1:]

    if normalized[0].isdigit():
        prefix = "Generated" if upper_camel else "generated"
        normalized = f"{prefix}{normalized}"

    if normalized in JAVA_RESERVED_IDENTIFIERS:
        suffix = "Type" if upper_camel else "Value"
        normalized = f"{normalized}{suffix}"

    return normalized


def primary_entity(metadata: MetadataProject) -> CanonicalEntity:
    return metadata.entities[0]


def all_entities(metadata: MetadataProject) -> list[CanonicalEntity]:
    """Return all canonical entities. Prefer over primary_entity() in emitters."""
    return list(metadata.entities)


def should_emit_demo_ui(metadata: MetadataProject) -> bool:
    """Match orchestrated demo applicability, independently of its runtime flag."""
    if metadata.operations:
        return True
    file_contract_names = {
        contract.name for contract in metadata.contracts
        if contract.type in {"file-fixed-width", "file-csv", "xml-xsd"}
    }
    return any(
        mapping.contract_name in file_contract_names
        and mapping.direction in {
            MappingDirection.UPSTREAM_TO_CANONICAL,
            MappingDirection.CANONICAL_TO_DOWNSTREAM,
        }
        for mapping in metadata.mappings
    )


def entity_id_field(entity: CanonicalEntity) -> CanonicalField:
    if not entity.fields:
        raise ValueError(
            f"Entity '{entity.name}' has no fields; cannot determine an ID field. "
            "Ensure the entity has at least one field defined in the manifest."
        )
    for field in entity.fields:
        if field.is_id:
            return field
    for field in entity.fields:
        if field.name.lower().endswith("id"):
            return field
    return entity.fields[0]


def filter_mappings(
    metadata: MetadataProject,
    *,
    direction: MappingDirection,
    contract_name: str | None = None,
    operation_name: str | None = None,
) -> list[FieldMapping]:
    results = [mapping for mapping in metadata.mappings if mapping.direction == direction]
    if contract_name is not None:
        results = [mapping for mapping in results if mapping.contract_name == contract_name]
    if operation_name is not None:
        results = [mapping for mapping in results if mapping.operation_name == operation_name]
    return results


def canonical_field_name(mapping: FieldMapping) -> str:
    return mapping.target_path.split(".", 1)[1]


def operation_entity_name(operation: CanonicalOperation) -> str | None:
    """Bind GETs to returned records, not an unrelated request-sample placeholder."""
    if operation.http_method == HttpMethod.GET:
        return operation.response_entity or operation.request_entity
    return operation.request_entity


def operation_mapping_transport_context(
    source_path: str, interface_name: str, operation_name: str,
) -> str | None:
    """Classify the selected transport prefix, not nested property names."""
    prefix = f"{interface_name}.{operation_name}."
    if not source_path.startswith(prefix):
        return None
    context, separator, field_path = source_path[len(prefix):].partition(".")
    return context if separator and field_path and context in {"request", "response"} else None


def contract_field_name(mapping: FieldMapping) -> str:
    return mapping.source_path.rsplit(".", 1)[1]


def output_field_name(mapping: FieldMapping) -> str:
    return mapping.target_path.rsplit(".", 1)[1]


def upstream_contract_name(metadata: MetadataProject, operation_name: str) -> str:
    for operation in metadata.operations:
        if operation.name == operation_name:
            return operation.interface_name
    raise ValueError(f"Unknown operation '{operation_name}'")


def _java_file(
    *,
    package_name: str,
    imports: list[str],
    body: list[str],
    source_manifest: str,
    target_profile: str,
    generation_run_id: str,
    ownership: str = "generated",
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile,
        generation_run_id=generation_run_id,
        comment_style="slash",
        ownership=ownership,
    )
    sections = [header, "", f"package {package_name};", ""]
    if imports:
        for import_name in imports:
            sections.append(f"import {import_name};")
        sections.append("")
    sections.extend(body)
    sections.append("")
    return "\n".join(sections)
