import shutil
from pathlib import Path

import pytest
import yaml

from appbuilder.cli import _print_generation_summary
from appbuilder.generation import generate_application
from appbuilder.generation.java_emitter import _field_validation_annotations
from appbuilder.generation.passthrough_helpers import (
    _passthrough_field_validation_annotations,
    _render_dto,
)
from appbuilder.ingestion.openapi_classifier import ingest_openapi_operations
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.models import CanonicalField, CanonicalFieldType
from appbuilder.metadata.translation import _validate_passthrough_configuration
from appbuilder.target_profiles import TARGET_PROFILES


def test_generate_country_router_passthrough_application(tmp_path: Path) -> None:
    metadata = build_metadata_project(_country_router_manifest())

    report = generate_application(
        metadata,
        tmp_path / "CountryRouter",
        source_manifest=str(_country_router_manifest()),
        generation_run_id="pt-router-test",
    )

    assert report.files_created
    assert report.harness_report is None
    assert report.warnings == []


def test_passthrough_generation_propagates_translation_warnings_to_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    metadata = build_metadata_project(_country_router_manifest())
    metadata.warnings = ["first contextual warning", "first contextual warning", "second warning"]

    report = generate_application(
        metadata,
        tmp_path / "CountryRouterWarnings",
        source_manifest=str(_country_router_manifest()),
        generation_run_id="pt-warning-test",
    )
    _print_generation_summary(report)

    assert report.warnings == ["first contextual warning", "second warning"]
    output = capsys.readouterr().out
    assert "Generation warnings:" in output
    assert output.count("first contextual warning") == 1
    assert "second warning" in output


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
@pytest.mark.parametrize("failure_kind", ["missing", "cyclic", "allof-cyclic"])
def test_nested_reference_diagnostic_reaches_metadata_report_and_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    openapi_version: str,
    failure_kind: str,
) -> None:
    package = tmp_path / "country-router"
    shutil.copytree(_country_router_manifest().parent, package)
    manifest = package / "app-definition.yaml"
    spec_path = package / "upstream/payments-openapi.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    spec["openapi"] = openapi_version
    request_schema = spec["components"]["schemas"]["PaymentRequest"]
    request_schema["properties"]["optionalEnvelope"] = {
        "type": "object",
        "properties": {
            "code": {"$ref": "#/components/schemas/DiagnosticCode"},
        },
    }
    if failure_kind == "cyclic":
        spec["components"]["schemas"]["DiagnosticCode"] = {
            "$ref": "#/components/schemas/DiagnosticCodeAlias"
        }
        spec["components"]["schemas"]["DiagnosticCodeAlias"] = {
            "$ref": "#/components/schemas/DiagnosticCode"
        }
    elif failure_kind == "allof-cyclic":
        spec["components"]["schemas"]["DiagnosticCode"] = {
            "allOf": [{"$ref": "#/components/schemas/DiagnosticCodeAlias"}]
        }
        spec["components"]["schemas"]["DiagnosticCodeAlias"] = {
            "allOf": [{"$ref": "#/components/schemas/DiagnosticCode"}]
        }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest)
    report = generate_application(
        metadata,
        tmp_path / "generated",
        source_manifest=str(manifest),
        generation_run_id="nested-reference-diagnostic",
    )
    _print_generation_summary(report)

    assert len(metadata.warnings) == 1
    warning = metadata.warnings[0]
    assert "OpenAPI interface 'inbound-payments-api'" in warning
    assert "operation 'routePayment' request" in warning
    assert "field 'optionalEnvelope.code'" in warning
    expected_reason = (
        "does not resolve to a schema"
        if failure_kind == "missing"
        else "Cyclic local OpenAPI schema reference"
    )
    assert expected_reason in warning
    assert report.warnings == [warning]
    output = capsys.readouterr().out
    assert "Generation warnings:" in output
    assert output.count(warning) == 1


def test_passthrough_generation_emits_expected_files_and_omits_crud_files(tmp_path: Path) -> None:
    metadata = build_metadata_project(_country_router_manifest())
    report = generate_application(
        metadata,
        tmp_path / "CountryRouter",
        source_manifest=str(_country_router_manifest()),
        generation_run_id="pt-files-test",
    )
    relative_files = {path.relative_to(report.output_dir).as_posix() for path in report.files_created}

    assert "pom.xml" in relative_files
    assert "Dockerfile" in relative_files
    assert "README.md" in relative_files
    assert ".gitignore" in relative_files
    assert ".dockerignore" in relative_files
    assert "src/main/resources/application.yaml" in relative_files
    assert "src/main/java/com/appbuilder/payments/controller/InboundController.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/service/TransformService.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/service/RoutingService.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/dto/InboundRequestDto.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/dto/InboundResponseDto.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/dto/OutboundRequestDto.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/dto/OutboundResponseDto.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/client/AppAClient.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/client/AppBClient.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/client/AppCClient.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/CountryRouterApplication.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/config/SecurityHeadersFilter.java" in relative_files
    assert "src/main/java/com/appbuilder/payments/exception/ErrorResponse.java" in relative_files
    assert (
        "src/main/java/com/appbuilder/payments/exception/GlobalExceptionHandler.java"
        in relative_files
    )

    assert not list(report.output_dir.rglob("*Entity.java"))
    assert not list(report.output_dir.rglob("*Repository.java"))
    assert not (report.output_dir / "src/main/resources/db/migration").exists()
    assert not list(report.output_dir.rglob("*BatchJob.java"))
    assert not list(report.output_dir.rglob("*BatchTrigger*.java"))


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
def test_response_and_downstream_dtos_preserve_legacy_nested_contracts(
    tmp_path: Path,
    openapi_version: str,
) -> None:
    package = tmp_path / "country-router"
    shutil.copytree(_country_router_manifest().parent, package)
    manifest = package / "app-definition.yaml"

    upstream_path = package / "upstream/payments-openapi.yaml"
    upstream = yaml.safe_load(upstream_path.read_text(encoding="utf-8"))
    upstream["openapi"] = openapi_version
    _add_legacy_nested_contract_shapes(
        upstream["components"]["schemas"],
        request_schema_name=None,
        response_schema_name="PaymentResponse",
    )
    upstream_path.write_text(
        yaml.safe_dump(upstream, sort_keys=False),
        encoding="utf-8",
    )

    downstream_path = package / "downstream/app-a-openapi.yaml"
    downstream = yaml.safe_load(downstream_path.read_text(encoding="utf-8"))
    downstream["openapi"] = openapi_version
    _add_legacy_nested_contract_shapes(
        downstream["components"]["schemas"],
        request_schema_name="OutboundPaymentRequest",
        response_schema_name="OutboundPaymentResponse",
    )
    downstream_path.write_text(
        yaml.safe_dump(downstream, sort_keys=False),
        encoding="utf-8",
    )

    metadata = build_metadata_project(manifest)
    upstream_operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    downstream_operation = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "app-a-api"
    )
    baseline_upstream_operation = ingest_openapi_operations(
        upstream,
        "inbound-payments-api",
    )[0]
    baseline_downstream_operation = ingest_openapi_operations(
        downstream,
        "app-a-api",
    )[0]
    assert [
        field.model_dump(mode="json")
        for field in upstream_operation.response_fields
    ] == [
        field.model_dump(mode="json")
        for field in baseline_upstream_operation.response_fields
    ]
    assert [
        field.model_dump(mode="json")
        for field in downstream_operation.request_fields
    ] == [
        field.model_dump(mode="json")
        for field in baseline_downstream_operation.request_fields
    ]
    assert [
        field.model_dump(mode="json")
        for field in downstream_operation.response_fields
    ] == [
        field.model_dump(mode="json")
        for field in baseline_downstream_operation.response_fields
    ]
    assert [
        field.name
        for field in upstream_operation.response_fields
        if "Details" in field.name
    ] == ["composedDetailsCode"]
    assert [
        field.name
        for field in downstream_operation.request_fields
        if "Envelope" in field.name
    ] == ["composedEnvelopeCode"]
    assert [
        field.name
        for field in downstream_operation.response_fields
        if "Details" in field.name
    ] == ["composedDetailsCode"]
    assert next(
        field
        for field in upstream_operation.response_fields
        if field.name == "composedDetailsCode"
    ).max_length is None
    assert next(
        field
        for field in downstream_operation.request_fields
        if field.name == "composedEnvelopeCode"
    ).max_length is None

    output = tmp_path / "generated"
    generate_application(
        metadata,
        output,
        source_manifest="app-definition.yaml",
        generation_run_id="legacy-response-downstream-contracts",
    )
    baseline_metadata = metadata.model_copy(deep=True)
    for operation in baseline_metadata.operations:
        if operation.interface_name == "inbound-payments-api":
            operation.response_fields = baseline_upstream_operation.response_fields
        elif operation.interface_name == "app-a-api":
            operation.request_fields = baseline_downstream_operation.request_fields
            operation.response_fields = baseline_downstream_operation.response_fields
    baseline_output = tmp_path / "baseline-generated"
    generate_application(
        baseline_metadata,
        baseline_output,
        source_manifest="app-definition.yaml",
        generation_run_id="legacy-response-downstream-contracts",
    )
    dto_root = output / "src/main/java/com/appbuilder/payments/dto"
    baseline_dto_root = (
        baseline_output / "src/main/java/com/appbuilder/payments/dto"
    )
    inbound_response = (dto_root / "InboundResponseDto.java").read_text(
        encoding="utf-8"
    )
    outbound_request = (dto_root / "OutboundRequestDto.java").read_text(
        encoding="utf-8"
    )
    outbound_response = (dto_root / "OutboundResponseDto.java").read_text(
        encoding="utf-8"
    )
    assert "refDetailsCode" not in inbound_response
    assert "composedDetailsCode" in inbound_response
    assert "refEnvelopeCode" not in outbound_request
    assert "composedEnvelopeCode" in outbound_request
    assert "refDetailsCode" not in outbound_response
    assert "composedDetailsCode" in outbound_response
    for dto_name in (
        "InboundResponseDto.java",
        "OutboundRequestDto.java",
        "OutboundResponseDto.java",
    ):
        assert (dto_root / dto_name).read_bytes() == (
            baseline_dto_root / dto_name
        ).read_bytes()


def test_passthrough_repository_hygiene_files_preserve_manual_edits(
    tmp_path: Path,
) -> None:
    metadata = build_metadata_project(_country_router_manifest())
    output_dir = tmp_path / "CountryRouter"
    generate_application(
        metadata,
        output_dir,
        source_manifest=str(_country_router_manifest()),
        generation_run_id="pt-hygiene-first",
    )

    for name in (".gitignore", ".dockerignore"):
        path = output_dir / name
        content = path.read_text(encoding="utf-8")
        assert "# EdgeForge-ownership: developer" in content
        assert "target/" in content
        assert "payments-eod/" in content
        path.write_text(content + "# adopter edit\n", encoding="utf-8")

    generate_application(
        metadata,
        output_dir,
        source_manifest=str(_country_router_manifest()),
        generation_run_id="pt-hygiene-second",
    )
    for name in (".gitignore", ".dockerignore"):
        assert (output_dir / name).read_text(encoding="utf-8").endswith(
            "# adopter edit\n"
        )


def test_passthrough_generation_emits_expected_content(tmp_path: Path) -> None:
    metadata = build_metadata_project(_country_router_manifest())
    report = generate_application(
        metadata,
        tmp_path / "CountryRouter",
        source_manifest=str(_country_router_manifest()),
        generation_run_id="pt-content-test",
    )

    pom = (report.output_dir / "pom.xml").read_text(encoding="utf-8")
    routing = (
        report.output_dir
        / "src/main/java/com/appbuilder/payments/service/RoutingService.java"
    ).read_text(encoding="utf-8")
    transform = (
        report.output_dir
        / "src/main/java/com/appbuilder/payments/service/TransformService.java"
    ).read_text(encoding="utf-8")
    application_yaml = (
        report.output_dir / "src/main/resources/application.yaml"
    ).read_text(encoding="utf-8")
    dockerfile = (report.output_dir / "Dockerfile").read_text(encoding="utf-8")
    readme = (report.output_dir / "README.md").read_text(encoding="utf-8")
    agent_context = (report.output_dir / "agent-context.md").read_text(encoding="utf-8")

    assert "spring-boot-starter-web" in pom
    assert pom.count("<artifactId>spring-boot-starter-validation</artifactId>") == 1
    assert "spring-boot-starter-data-jpa" not in pom
    assert "flyway" not in pom
    assert "countryCode" in routing
    assert "\"US\"" in routing
    assert "\"GB\"" in routing
    assert "APP_C" in routing
    assert "setPaymentAmount" in transform
    assert "UNKNOWN" in transform
    assert "downstream:" in application_yaml
    assert "base-url" in application_yaml
    assert "app-a" in application_yaml
    assert "app-b" in application_yaml
    assert "app-c" in application_yaml
    assert "server:\n  port: 8080\n  shutdown: graceful" in application_yaml
    assert "  lifecycle:\n    timeout-per-shutdown-phase: 30s" in application_yaml
    assert "      show-details: when-authorized" in application_yaml
    assert "      roles: ACTUATOR" in application_yaml
    assert "show-details: always" not in application_yaml
    assert "COPY --from=build --chown=edgeforge:edgeforge" in dockerfile
    assert "RUN chown -R edgeforge:edgeforge /app" in dockerfile
    assert "USER edgeforge" in dockerfile
    assert dockerfile.index("USER edgeforge") < dockerfile.index("ENTRYPOINT")
    for generated_guidance in (readme, agent_context):
        assert "plain HTTP and no built-in authentication" in generated_guidance
        assert "TLS-terminating, authenticated gateway" in generated_guidance
        assert (
            "application port must be unreachable except through that gateway"
            in generated_guidance
        )
        assert (
            "All authenticated callers share one authorization domain"
            in generated_guidance
        )
        assert (
            "Multi-tenant, per-user, object-level, and row-level authorization"
            in generated_guidance
        )
        assert "`config/SecurityHeadersFilter.java` is a security control" in generated_guidance
        assert "`X-Content-Type-Options: nosniff`" in generated_guidance
        assert "`X-Frame-Options: DENY`" in generated_guidance
        assert "`Referrer-Policy: no-referrer`" in generated_guidance
        assert (
            "`Content-Security-Policy: frame-ancestors 'none'`"
            in generated_guidance
        )
        assert "does not emit `Strict-Transport-Security`" in generated_guidance
        assert "configure HSTS at the TLS-terminating gateway" in generated_guidance
        assert "Rate limiting is gateway-owned" in generated_guidance
        assert "trusted local network" not in generated_guidance
    assert "does not emit the CRUD `Service`/`ServiceBase` extension seam" in readme


def test_passthrough_generation_validates_only_inbound_requests(tmp_path: Path) -> None:
    metadata = build_metadata_project(_country_router_manifest())
    upstream = next(
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-payments-api"
    )
    fields = {field.name: field for field in upstream.request_fields}
    fields["countryCode"].max_length = 2
    fields["recipientName"].required = False
    fields["recipientName"].not_null = True
    fields["amount"].max_length = 9

    report = generate_application(
        metadata,
        tmp_path / "CountryRouterValidation",
        source_manifest=str(_country_router_manifest()),
        generation_run_id="pt-validation-test",
    )
    java_root = report.output_dir / "src/main/java/com/appbuilder/payments"
    controller = (java_root / "controller/InboundController.java").read_text(encoding="utf-8")
    inbound = (java_root / "dto/InboundRequestDto.java").read_text(encoding="utf-8")
    non_inbound_dtos = [
        (java_root / f"dto/{name}.java").read_text(encoding="utf-8")
        for name in ("InboundResponseDto", "OutboundRequestDto", "OutboundResponseDto")
    ]
    error_response = (java_root / "exception/ErrorResponse.java").read_text(encoding="utf-8")
    handler = (java_root / "exception/GlobalExceptionHandler.java").read_text(encoding="utf-8")

    assert "import jakarta.validation.Valid;" in controller
    assert "@Valid @RequestBody InboundRequestDto request" in controller
    assert "import jakarta.validation.constraints.NotNull;" in inbound
    assert "import org.hibernate.validator.constraints.CodePointLength;" in inbound
    assert "@NotNull\n    @CodePointLength(max=2)\n    private String countryCode;" in inbound
    assert "@NotNull\n    private String recipientName;" in inbound
    assert "@CodePointLength(max=9)\n    private BigDecimal amount;" not in inbound
    for source in non_inbound_dtos:
        assert "jakarta.validation" not in source
        assert "org.hibernate.validator.constraints" not in source
        assert "@NotNull" not in source
        assert "@CodePointLength(" not in source

    for field in ("timestamp", "status", "error", "message", "path"):
        assert (
            f"private final {'int' if field == 'status' else 'String'} {field};" in error_response
        )
    assert "@ExceptionHandler(MethodArgumentNotValidException.class)" in handler
    assert "HttpStatus.BAD_REQUEST" in handler
    assert 'error.getField() + ": " + error.getCode()' in handler
    assert ".sorted()" in handler
    assert "getRejectedValue" not in handler


def test_passthrough_validation_renderer_is_bounded_and_matches_crud_shared_constraints() -> None:
    shared_field = CanonicalField(
        name="routeKey",
        type=CanonicalFieldType.STRING,
        required=True,
        max_length=12,
    )
    assert _passthrough_field_validation_annotations(shared_field) == _field_validation_annotations(
        shared_field
    )

    explicitly_non_null = CanonicalField(
        name="requestLabel",
        type=CanonicalFieldType.STRING,
        not_null=True,
    )
    assert _passthrough_field_validation_annotations(explicitly_non_null) == ["@NotNull"]
    non_null_dto = _render_dto(
        class_name="InboundRequestDto",
        package_name="com.appbuilder.validation.dto",
        fields=[explicitly_non_null],
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="app-definition.yaml",
        generation_run_id="pt-not-null-test",
        emit_inbound_validation=True,
    )
    assert "import jakarta.validation.constraints.NotNull;" in non_null_dto
    assert "org.hibernate.validator.constraints.CodePointLength" not in non_null_dto

    unsupported = CanonicalField(
        name="attemptCount",
        type=CanonicalFieldType.INTEGER,
        max_length=8,
        min_length=2,
        pattern="[0-9]+",
        range_min=1,
        range_max=10,
        allowed_values=["1", "2"],
    )
    assert _passthrough_field_validation_annotations(unsupported) == []
    minimum_only = CanonicalField(
        name="shortLabel",
        type=CanonicalFieldType.STRING,
        min_length=2,
    )
    assert _passthrough_field_validation_annotations(minimum_only) == []

    unconstrained_dto = _render_dto(
        class_name="InboundRequestDto",
        package_name="com.appbuilder.validation.dto",
        fields=[unsupported, minimum_only],
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="app-definition.yaml",
        generation_run_id="pt-unconstrained-test",
        emit_inbound_validation=True,
    )
    assert "jakarta.validation" not in unconstrained_dto
    assert "@NotNull" not in unconstrained_dto
    assert "@CodePointLength(" not in unconstrained_dto


def test_passthrough_generation_sanitizes_hyphenated_operation_method_names(tmp_path: Path) -> None:
    metadata = build_metadata_project(_country_router_manifest())
    upstream_contract_name = metadata.contracts[0].name
    for operation in metadata.operations:
        if operation.interface_name == upstream_contract_name:
            operation.name = "route-payment-request"
    for contract in metadata.selected_rest_contracts:
        if contract["interface"] == upstream_contract_name:
            contract["operation"] = "route-payment-request"

    report = generate_application(
        metadata,
        tmp_path / "CountryRouterSanitized",
        source_manifest=str(_country_router_manifest()),
        generation_run_id="pt-sanitize-test",
    )

    controller = (
        report.output_dir
        / "src/main/java/com/appbuilder/payments/controller/InboundController.java"
    ).read_text(encoding="utf-8")

    assert "routePaymentRequest(" in controller
    assert "route-payment-request(" not in controller


def test_crud_generation_still_works_after_passthrough_emitter_lands(tmp_path: Path) -> None:
    metadata = build_metadata_project(
        "examples/input-projects/xyz-accounts-modernization/app-definition.yaml"
    )

    report = generate_application(
        metadata,
        tmp_path / "BuiltAppCrudRegression",
        source_manifest="examples/input-projects/xyz-accounts-modernization/app-definition.yaml",
        generation_run_id="crud-regression",
    )

    assert report.files_created
    assert report.harness_report is not None


def test_passthrough_validation_rejects_unknown_routing_field() -> None:
    with pytest.raises(ValueError, match="Routing field 'unknownField'"):
        _validate_passthrough_configuration(
            routing_rules=[_routing_rule("unknownField", default_target="APP_A")],
            transform_mappings=[_transform_mapping("amount", "paymentAmount")],
            upstream_request_fields={"amount", "countryCode"},
            downstream_request_fields={"paymentAmount"},
            downstream_targets={"APP_A", "APP_B"},
        )


def test_passthrough_validation_rejects_unknown_routing_target() -> None:
    with pytest.raises(ValueError, match="Routing target 'APP_X'"):
        _validate_passthrough_configuration(
            routing_rules=[_routing_rule("countryCode", route_target="APP_X", default_target="APP_A")],
            transform_mappings=[_transform_mapping("amount", "paymentAmount")],
            upstream_request_fields={"amount", "countryCode"},
            downstream_request_fields={"paymentAmount"},
            downstream_targets={"APP_A", "APP_B"},
        )


def test_passthrough_validation_rejects_unknown_transform_source() -> None:
    with pytest.raises(ValueError, match="Transform source 'missingSource'"):
        _validate_passthrough_configuration(
            routing_rules=[_routing_rule("countryCode", default_target="APP_A")],
            transform_mappings=[_transform_mapping("missingSource", "paymentAmount")],
            upstream_request_fields={"amount", "countryCode"},
            downstream_request_fields={"paymentAmount"},
            downstream_targets={"APP_A", "APP_B"},
        )


def test_passthrough_validation_rejects_unknown_transform_target() -> None:
    with pytest.raises(ValueError, match="Transform target 'missingTarget'"):
        _validate_passthrough_configuration(
            routing_rules=[_routing_rule("countryCode", default_target="APP_A")],
            transform_mappings=[_transform_mapping("amount", "missingTarget")],
            upstream_request_fields={"amount", "countryCode"},
            downstream_request_fields={"paymentAmount"},
            downstream_targets={"APP_A", "APP_B"},
        )


def test_passthrough_validation_rejects_empty_routing_rules() -> None:
    with pytest.raises(ValueError, match="at least one 'routing_rules'"):
        _validate_passthrough_configuration(
            routing_rules=[],
            transform_mappings=[_transform_mapping("amount", "paymentAmount")],
            upstream_request_fields={"amount", "countryCode"},
            downstream_request_fields={"paymentAmount"},
            downstream_targets={"APP_A", "APP_B"},
        )


def test_passthrough_validation_rejects_empty_transforms() -> None:
    with pytest.raises(ValueError, match="at least one entry in 'transforms'"):
        _validate_passthrough_configuration(
            routing_rules=[_routing_rule("countryCode", default_target="APP_A")],
            transform_mappings=[],
            upstream_request_fields={"amount", "countryCode"},
            downstream_request_fields={"paymentAmount"},
            downstream_targets={"APP_A", "APP_B"},
        )


def _add_legacy_nested_contract_shapes(
    schemas: dict,
    *,
    request_schema_name: str | None,
    response_schema_name: str,
) -> None:
    schemas["LegacyCode"] = {"type": "string", "maxLength": 12}
    if request_schema_name is not None:
        request_schema = schemas[request_schema_name]
        request_schema["required"].extend(["refEnvelope", "composedEnvelope"])
        request_schema["properties"].update(
            {
                "refEnvelope": {
                    "type": "object",
                    "required": ["code"],
                    "properties": {
                        "code": {"$ref": "#/components/schemas/LegacyCode"},
                    },
                },
                "composedEnvelope": {
                    "type": "object",
                    "required": ["code"],
                    "properties": {
                        "code": {
                            "allOf": [
                                {"$ref": "#/components/schemas/LegacyCode"},
                                {"maxLength": 8},
                            ]
                        }
                    },
                },
            }
        )

    response_schema = schemas[response_schema_name]
    response_schema.setdefault("required", []).extend(
        ["refDetails", "composedDetails"]
    )
    response_schema["properties"].update(
        {
            "refDetails": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {"$ref": "#/components/schemas/LegacyCode"},
                },
            },
            "composedDetails": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {
                        "allOf": [
                            {"$ref": "#/components/schemas/LegacyCode"},
                            {"maxLength": 8},
                        ]
                    }
                },
            },
        }
    )


def _routing_rule(route_field: str, *, route_target: str = "APP_A", default_target: str) -> object:
    metadata = build_metadata_project(_country_router_manifest())
    rule = metadata.routing_rules[0].model_copy(deep=True)
    rule.route_field = route_field
    rule.routes[0].target = route_target
    rule.default_target = default_target
    return rule


def _transform_mapping(source: str, target: str) -> object:
    metadata = build_metadata_project(_country_router_manifest())
    mapping = metadata.transform_mappings[0].model_copy(deep=True)
    mapping.source = source
    mapping.target = target
    return mapping


def _country_router_manifest() -> Path:
    return Path("examples/input-projects/country-router/app-definition.yaml")
