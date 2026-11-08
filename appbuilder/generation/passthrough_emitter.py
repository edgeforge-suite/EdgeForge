"""Emit Java sources for the passthrough-router archetype."""

from __future__ import annotations

from pathlib import Path

from appbuilder.metadata.models import CanonicalField, CanonicalOperation, MetadataProject
from appbuilder.target_profiles.catalog import TargetProfile

from .java_emitter import _render_application_test
from .passthrough_helpers import (
    _application_class_name,
    _client_class_name,
    _client_field_name,
    _downstream_clients,
    _escape_java_string,
    _first_downstream_operation,
    _java_imports_for_fields,
    _java_literal,
    _mapping_annotation,
    _render_application_class,
    _render_client,
    _render_dto,
    _upstream_contract_name,
    _write_java_file,
)
from .utils import _java_file, base_package, package_path, to_java_method_name, to_pascal_case


def emit_passthrough_sources(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
) -> list[Path]:
    from .write_contract import validate_write_contracts
    validate_write_contracts(metadata)
    root_package = base_package(metadata)
    root_path = output_dir / "src" / "main" / "java" / package_path(root_package)
    root_path.mkdir(parents=True, exist_ok=True)

    upstream_contract_name = _upstream_contract_name(metadata)
    upstream_operations = [
        operation for operation in metadata.operations if operation.interface_name == upstream_contract_name
    ]
    if not upstream_operations:
        raise ValueError("Passthrough-router metadata must include at least one upstream operation.")

    first_upstream_operation = upstream_operations[0]
    first_downstream_operation = _first_downstream_operation(metadata)
    downstream_clients = _downstream_clients(metadata)

    files: list[Path] = []
    files.append(
        _write_java_file(
            root_path / f"{_application_class_name(metadata)}.java",
            _render_application_class(
                metadata=metadata,
                root_package=root_package,
                target_profile=target_profile,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            ),
        )
    )
    if target_profile.experimental_boot41:
        test_root = output_dir / "src" / "test" / "java" / package_path(root_package)
        files.append(
            _write_java_file(
                test_root / f"{to_pascal_case(metadata.bounded_context)}ApplicationTest.java",
                _render_application_test(
                    metadata=metadata,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )

    dto_dir = root_path / "dto"
    files.extend(
        [
            _write_java_file(
                dto_dir / "InboundRequestDto.java",
                _render_dto(
                    class_name="InboundRequestDto",
                    package_name=f"{root_package}.dto",
                    fields=first_upstream_operation.request_fields,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                    emit_inbound_validation=True,
                ),
            ),
            _write_java_file(
                dto_dir / "InboundResponseDto.java",
                _render_dto(
                    class_name="InboundResponseDto",
                    package_name=f"{root_package}.dto",
                    fields=first_upstream_operation.response_fields,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            ),
            _write_java_file(
                dto_dir / "OutboundRequestDto.java",
                _render_dto(
                    class_name="OutboundRequestDto",
                    package_name=f"{root_package}.dto",
                    fields=first_downstream_operation.request_fields,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            ),
            _write_java_file(
                dto_dir / "OutboundResponseDto.java",
                _render_dto(
                    class_name="OutboundResponseDto",
                    package_name=f"{root_package}.dto",
                    fields=first_downstream_operation.response_fields,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            ),
        ]
    )

    service_dir = root_path / "service"
    files.extend(
        [
            _write_java_file(
                service_dir / "TransformService.java",
                _render_transform_service(
                    metadata=metadata,
                    root_package=root_package,
                    outbound_fields=first_downstream_operation.request_fields,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            ),
            _write_java_file(
                service_dir / "RoutingService.java",
                _render_routing_service(
                    metadata=metadata,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            ),
        ]
    )

    client_dir = root_path / "client"
    for system_name, operation in downstream_clients:
        files.append(
            _write_java_file(
                client_dir / f"{_client_class_name(system_name)}.java",
                _render_client(
                    root_package=root_package,
                    system_name=system_name,
                    operation=operation,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )

    controller_dir = root_path / "controller"
    files.append(
        _write_java_file(
            controller_dir / "InboundController.java",
            _render_inbound_controller(
                metadata=metadata,
                root_package=root_package,
                upstream_operations=upstream_operations,
                downstream_clients=downstream_clients,
                target_profile=target_profile,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            ),
        )
    )

    exception_dir = root_path / "exception"
    files.extend(
        [
            _write_java_file(
                exception_dir / "ErrorResponse.java",
                _render_passthrough_error_response(
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            ),
            _write_java_file(
                exception_dir / "GlobalExceptionHandler.java",
                _render_passthrough_validation_exception_handler(
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            ),
        ]
    )

    return files


def _render_transform_service(
    *,
    metadata: MetadataProject,
    root_package: str,
    outbound_fields: list[CanonicalField],
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    outbound_field_lookup = {field.name: field for field in outbound_fields}
    body = [
        "@Service",
        "public class TransformService {",
        "",
        "    public OutboundRequestDto transform(InboundRequestDto request) {",
        "        OutboundRequestDto outbound = new OutboundRequestDto();",
    ]
    for mapping in metadata.transform_mappings:
        target_field = outbound_field_lookup[mapping.target]
        target_suffix = to_pascal_case(mapping.target)
        source_suffix = to_pascal_case(mapping.source)
        if mapping.default is None:
            body.append(f"        outbound.set{target_suffix}(request.get{source_suffix}());")
            continue
        body.append(
            "        outbound.set"
            f"{target_suffix}(request.get{source_suffix}() != null ? "
            f"request.get{source_suffix}() : {_java_literal(target_field, mapping.default)});"
        )
    body.extend(
        [
            "        return outbound;",
            "    }",
            "}",
        ]
    )
    imports = sorted(
        {
            f"{root_package}.dto.InboundRequestDto",
            f"{root_package}.dto.OutboundRequestDto",
            "org.springframework.stereotype.Service",
            *_java_imports_for_fields(outbound_fields),
        }
    )
    return _java_file(
        package_name=f"{root_package}.service",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_routing_service(
    *,
    metadata: MetadataProject,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    routing_rule = metadata.routing_rules[0]
    route_suffix = to_pascal_case(routing_rule.route_field)
    route_variable_name = routing_rule.route_field
    body = [
        "@Service",
        "public class RoutingService {",
        "",
        "    public String route(InboundRequestDto request) {",
        f"        String {route_variable_name} = request.get{route_suffix}();",
    ]
    for index, route in enumerate(routing_rule.routes):
        keyword = "if" if index == 0 else "else if"
        body.append(
            f"        {keyword} (\"{_escape_java_string(route.match)}\".equals({route_variable_name})) {{"
        )
        body.append(f"            return \"{_escape_java_string(route.target)}\";")
        body.append("        }")
    body.extend(
        [
            f"        return \"{_escape_java_string(routing_rule.default_target)}\";",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.service",
        imports=[
            f"{root_package}.dto.InboundRequestDto",
            "org.springframework.stereotype.Service",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_inbound_controller(
    *,
    metadata: MetadataProject,
    root_package: str,
    upstream_operations: list[CanonicalOperation],
    downstream_clients: list[tuple[str, CanonicalOperation]],
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    client_classes = [_client_class_name(system_name) for system_name, _ in downstream_clients]
    imports = [
        f"{root_package}.dto.InboundRequestDto",
        f"{root_package}.dto.InboundResponseDto",
        f"{root_package}.dto.OutboundRequestDto",
        f"{root_package}.dto.OutboundResponseDto",
        f"{root_package}.service.RoutingService",
        f"{root_package}.service.TransformService",
        *[f"{root_package}.client.{client_class}" for client_class in client_classes],
        "org.springframework.http.ResponseEntity",
        "jakarta.validation.Valid",
        "org.springframework.web.bind.annotation.DeleteMapping",
        "org.springframework.web.bind.annotation.GetMapping",
        "org.springframework.web.bind.annotation.PostMapping",
        "org.springframework.web.bind.annotation.PutMapping",
        "org.springframework.web.bind.annotation.RequestBody",
        "org.springframework.web.bind.annotation.RestController",
    ]
    body = [
        "@RestController",
        "public class InboundController {",
        "",
        "    private final TransformService transformService;",
        "    private final RoutingService routingService;",
    ]
    for system_name, _ in downstream_clients:
        body.append(f"    private final {_client_class_name(system_name)} {_client_field_name(system_name)};")
    body.append("")

    constructor_parameters = [
        "TransformService transformService",
        "RoutingService routingService",
        *[
            f"{_client_class_name(system_name)} {_client_field_name(system_name)}"
            for system_name, _ in downstream_clients
        ],
    ]
    body.append(f"    public InboundController({', '.join(constructor_parameters)}) {{")
    body.append("        this.transformService = transformService;")
    body.append("        this.routingService = routingService;")
    for system_name, _ in downstream_clients:
        body.append(f"        this.{_client_field_name(system_name)} = {_client_field_name(system_name)};")
    body.append("    }")
    body.append("")

    downstream_response_fields = {field.name for field in _first_downstream_operation(metadata).response_fields}
    for operation in upstream_operations:
        from .write_contract import passthrough_operation_response

        status, has_response_body = passthrough_operation_response(metadata, operation)
        response_line = (
            "        return ResponseEntity.ok(response);" if status == "200" and has_response_body
            else f"        return ResponseEntity.status({status}).body(response);" if has_response_body
            else f"        return ResponseEntity.status({status}).build();"
        )
        method_name = to_java_method_name(operation.name, fallback="routeRequest")
        body.extend(
            [
                f"    {_mapping_annotation(operation)}",
                f"    public ResponseEntity<InboundResponseDto> {method_name}(@Valid @RequestBody InboundRequestDto request) {{",
                "        OutboundRequestDto outboundRequest = transformService.transform(request);",
                "        String target = routingService.route(request);",
                "        OutboundResponseDto outboundResponse;",
            ]
        )
        for index, (system_name, _client_operation) in enumerate(downstream_clients):
            keyword = "if" if index == 0 else "else if"
            body.append(f"        {keyword} (\"{_escape_java_string(system_name)}\".equals(target)) {{")
            body.append(f"            outboundResponse = {_client_field_name(system_name)}.send(outboundRequest);")
            body.append("        }")
        body.extend(
            [
                "        else {",
                "            throw new IllegalStateException(\"No passthrough client configured for target: \" + target);",
                "        }",
                "        InboundResponseDto response = new InboundResponseDto();",
            ]
        )
        for field in operation.response_fields:
            if field.name not in downstream_response_fields:
                continue
            suffix = to_pascal_case(field.name)
            body.append(f"        response.set{suffix}(outboundResponse.get{suffix}());")
        body.extend(
            [
                response_line,
                "    }",
                "",
            ]
        )
    body.append("}")
    return _java_file(
        package_name=f"{root_package}.controller",
        imports=sorted(set(imports)),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_passthrough_error_response(
    *,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    body = [
        "public class ErrorResponse {",
        "",
        "    private final String timestamp;",
        "    private final int status;",
        "    private final String error;",
        "    private final String message;",
        "    private final String path;",
        "",
        "    public ErrorResponse(String timestamp, int status, String error, String message, String path) {",
        "        this.timestamp = timestamp;",
        "        this.status = status;",
        "        this.error = error;",
        "        this.message = message;",
        "        this.path = path;",
        "    }",
        "",
        "    public String getTimestamp() { return timestamp; }",
        "    public int getStatus() { return status; }",
        "    public String getError() { return error; }",
        "    public String getMessage() { return message; }",
        "    public String getPath() { return path; }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.exception",
        imports=[],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_passthrough_validation_exception_handler(
    *,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    body = [
        "@RestControllerAdvice",
        "public class GlobalExceptionHandler {",
        "",
        "    @ExceptionHandler(MethodArgumentNotValidException.class)",
        "    @ResponseStatus(HttpStatus.BAD_REQUEST)",
        "    public ErrorResponse handleValidation(",
        "            MethodArgumentNotValidException ex,",
        "            HttpServletRequest request) {",
        "        String message = ex.getBindingResult().getFieldErrors().stream()",
        '            .map(error -> error.getField() + ": " + error.getCode())',
        "            .sorted()",
        '            .collect(java.util.stream.Collectors.joining("; "));',
        "        return new ErrorResponse(",
        "            java.time.Instant.now().toString(),",
        "            HttpStatus.BAD_REQUEST.value(),",
        '            "Bad Request",',
        "            message,",
        "            request.getRequestURI()",
        "        );",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.exception",
        imports=[
            "jakarta.servlet.http.HttpServletRequest",
            "org.springframework.http.HttpStatus",
            "org.springframework.web.bind.MethodArgumentNotValidException",
            "org.springframework.web.bind.annotation.ExceptionHandler",
            "org.springframework.web.bind.annotation.ResponseStatus",
            "org.springframework.web.bind.annotation.RestControllerAdvice",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )
