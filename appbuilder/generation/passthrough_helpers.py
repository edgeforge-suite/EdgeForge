"""Shared helpers for passthrough-router Java generation."""

from __future__ import annotations

from pathlib import Path

from appbuilder.metadata.models import (
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    MetadataProject,
)
from appbuilder.target_profiles.catalog import TargetProfile

from .file_writer import write_generated_file
from .utils import _java_file, to_pascal_case, to_snake_case

CANONICAL_TO_JAVA = {
    "string": "String",
    "integer": "Long",
    "decimal": "BigDecimal",
    "boolean": "Boolean",
    "date": "LocalDate",
    "datetime": "LocalDateTime",
    "binary": "byte[]",
}

JAVA_IMPORTS = {
    "BigDecimal": "java.math.BigDecimal",
    "LocalDate": "java.time.LocalDate",
    "LocalDateTime": "java.time.LocalDateTime",
}


def _write_java_file(path: Path, content: str, *, ownership: str = "generated") -> Path:
    return write_generated_file(path, content, ownership=ownership)


def _upstream_contract_name(metadata: MetadataProject) -> str:
    if not metadata.contracts:
        raise ValueError("Passthrough-router metadata must include at least one contract.")
    return metadata.contracts[0].name


def _downstream_clients(metadata: MetadataProject) -> list[tuple[str, CanonicalOperation]]:
    downstream_systems = [participant.name for participant in metadata.systems if participant.role == "downstream"]
    downstream_contracts = metadata.contracts[1 : 1 + len(downstream_systems)]
    if len(downstream_systems) != len(downstream_contracts):
        raise ValueError("Unable to align downstream systems with downstream contracts.")

    operations_by_interface = {
        operation.interface_name: operation
        for operation in metadata.operations
        if operation.interface_name != _upstream_contract_name(metadata)
    }
    clients: list[tuple[str, CanonicalOperation]] = []
    for system_name, contract in zip(downstream_systems, downstream_contracts, strict=True):
        operation = operations_by_interface.get(contract.name)
        if operation is None:
            raise ValueError(
                f"Downstream contract '{contract.name}' has no operation metadata for passthrough generation."
            )
        clients.append((system_name, operation))
    return clients


def _first_downstream_operation(metadata: MetadataProject) -> CanonicalOperation:
    downstream_clients = _downstream_clients(metadata)
    if not downstream_clients:
        raise ValueError("Passthrough-router metadata must include at least one downstream target.")
    return downstream_clients[0][1]


def _application_class_name(metadata: MetadataProject) -> str:
    return f"{to_pascal_case(metadata.app_name)}Application"


def _render_dto(
    *,
    class_name: str,
    package_name: str,
    fields: list[CanonicalField],
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
    emit_inbound_validation: bool = False,
) -> str:
    imports = _java_imports_for_fields(fields)
    validation_annotations = {
        field.name: _passthrough_field_validation_annotations(field)
        for field in fields
        if emit_inbound_validation
    }
    if any("@NotNull" in annotations for annotations in validation_annotations.values()):
        imports.add("jakarta.validation.constraints.NotNull")
    if any(
        any(annotation.startswith("@CodePointLength(") for annotation in annotations)
        for annotations in validation_annotations.values()
    ):
        imports.add("org.hibernate.validator.constraints.CodePointLength")

    body = [f"public class {class_name} {{", ""]
    for field in fields:
        for annotation in validation_annotations.get(field.name, []):
            body.append(f"    {annotation}")
        body.append(f"    private {_java_type(field)} {field.name};")
        body.append("")
    body.append(f"    public {class_name}() {{")
    body.append("    }")
    body.append("")
    for field in fields:
        suffix = to_pascal_case(field.name)
        java_type = _java_type(field)
        body.extend(
            [
                f"    public {java_type} get{suffix}() {{",
                f"        return {field.name};",
                "    }",
                "",
                f"    public void set{suffix}({java_type} {field.name}) {{",
                f"        this.{field.name} = {field.name};",
                "    }",
                "",
            ]
        )
    body.append("}")
    return _java_file(
        package_name=package_name,
        imports=sorted(imports),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _passthrough_field_validation_annotations(field: CanonicalField) -> list[str]:
    """Render only constraints carried by passthrough OpenAPI metadata."""
    annotations: list[str] = []
    if field.not_null or field.required:
        annotations.append("@NotNull")
    if field.type == CanonicalFieldType.STRING and field.max_length is not None:
        annotations.append(f"@CodePointLength(max={field.max_length})")
    return annotations


def _render_application_class(
    *,
    metadata: MetadataProject,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    class_name = _application_class_name(metadata)
    return _java_file(
        package_name=root_package,
        imports=[
            "org.springframework.boot.SpringApplication",
            "org.springframework.boot.autoconfigure.SpringBootApplication",
            "org.springframework.context.annotation.Bean",
            "org.springframework.web.client.RestTemplate",
        ],
        body=[
            "@SpringBootApplication",
            f"public class {class_name} {{",
            "",
            "    @Bean",
            "    public RestTemplate restTemplate() {",
            "        return new RestTemplate();",
            "    }",
            "",
            "    public static void main(String[] args) {",
            f"        SpringApplication.run({class_name}.class, args);",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _mapping_annotation(operation: CanonicalOperation) -> str:
    path = operation.path or "/"
    if operation.http_method is None or operation.http_method.value == "POST":
        return f"@PostMapping(\"{path}\")"
    if operation.http_method.value == "GET":
        return f"@GetMapping(\"{path}\")"
    if operation.http_method.value == "PUT":
        return f"@PutMapping(\"{path}\")"
    if operation.http_method.value == "DELETE":
        return f"@DeleteMapping(\"{path}\")"
    return f"@PostMapping(\"{path}\")"


def _client_class_name(system_name: str) -> str:
    return f"{to_pascal_case(to_snake_case(system_name))}Client"


def _client_field_name(system_name: str) -> str:
    class_name = _client_class_name(system_name)
    return class_name[:1].lower() + class_name[1:]


def _system_property_key(system_name: str) -> str:
    return to_snake_case(system_name).replace("_", "-")


def _system_env_var(system_name: str) -> str:
    return f"{to_snake_case(system_name).upper()}_BASE_URL"


def _render_client(
    *,
    root_package: str,
    system_name: str,
    operation: CanonicalOperation,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    class_name = _client_class_name(system_name)
    property_key = _system_property_key(system_name)
    path = operation.path or "/"
    body = [
        "@Service",
        f"public class {class_name} {{",
        "",
        "    private final RestTemplate restTemplate;",
        "",
        f"    @Value(\"${{downstream.{property_key}.base-url}}\")",
        "    private String baseUrl;",
        "",
        f"    public {class_name}(RestTemplate restTemplate) {{",
        "        this.restTemplate = restTemplate;",
        "    }",
        "",
        "    public OutboundResponseDto send(OutboundRequestDto request) {",
        f"        return restTemplate.postForObject(baseUrl + \"{path}\", request, OutboundResponseDto.class);",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.client",
        imports=[
            f"{root_package}.dto.OutboundRequestDto",
            f"{root_package}.dto.OutboundResponseDto",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.stereotype.Service",
            "org.springframework.web.client.RestTemplate",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _java_imports_for_fields(fields: list[CanonicalField]) -> set[str]:
    imports: set[str] = set()
    for field in fields:
        java_type = _java_type(field)
        if java_type in JAVA_IMPORTS:
            imports.add(JAVA_IMPORTS[java_type])
    return imports


def _java_literal(field: CanonicalField, value: str) -> str:
    if field.type.value == "string":
        return f"\"{_escape_java_string(value)}\""
    if field.type.value == "integer":
        return f"Long.valueOf(\"{_escape_java_string(value)}\")"
    if field.type.value == "decimal":
        return f"new java.math.BigDecimal(\"{_escape_java_string(value)}\")"
    if field.type.value == "boolean":
        return "Boolean.TRUE" if value.strip().lower() == "true" else "Boolean.FALSE"
    return f"\"{_escape_java_string(value)}\""


def _java_type(field: CanonicalField) -> str:
    return CANONICAL_TO_JAVA[field.type.value]


def _escape_java_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")
