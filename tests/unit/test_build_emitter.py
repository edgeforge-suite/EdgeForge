"""Focused tests for build/packaging file emission."""

from __future__ import annotations

from pathlib import Path

from appbuilder.generation.build_emitter import (
    _render_dockerfile,
    _render_pom_xml,
    _to_artifact_id,
    emit_repository_hygiene_files,
)
from appbuilder.generation.utils import (
    base_package,
    supports_spec_route,
    to_pascal_case,
    to_snake_case,
)
from appbuilder.metadata.models import ContractMetadata, HttpMethod, MetadataProject, ResponseShape
from appbuilder.target_profiles.catalog import TARGET_PROFILES


def _minimal_metadata(*, app_name: str, bounded_context: str) -> MetadataProject:
    return MetadataProject(
        app_name=app_name,
        bounded_context=bounded_context,
        target_profile="springboot-legacy-compatible",
    )


def test_artifact_id_sanitizes_spaces() -> None:
    assert _to_artifact_id("Basic DDA App") == "basic-dda-app"


def test_artifact_id_sanitizes_mixed() -> None:
    assert _to_artifact_id("My App 2.0!") == "my-app-20"


def test_artifact_id_single_word_unchanged() -> None:
    assert _to_artifact_id("loanlite") == "loanlite"


def test_repository_hygiene_files_are_deterministic_and_preserve_adopter_edits(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    common = {
        "bounded_context": "accounts",
        "target_profile_name": "springboot-legacy-compatible",
        "source_manifest": "app-definition.yaml",
        "generation_run_id": "hygiene-test",
    }

    emit_repository_hygiene_files(output_dir=first, **common)
    emit_repository_hygiene_files(output_dir=second, **common)

    for name in (".gitignore", ".dockerignore"):
        first_content = (first / name).read_text(encoding="utf-8")
        assert first_content == (second / name).read_text(encoding="utf-8")
        assert "# EdgeForge-ownership: developer" in first_content
        assert "target/" in first_content
        assert "accounts-eod/" in first_content

    edited_gitignore = (first / ".gitignore").read_text(encoding="utf-8") + "# adopter edit\n"
    edited_dockerignore = (
        (first / ".dockerignore").read_text(encoding="utf-8") + "# adopter edit\n"
    )
    (first / ".gitignore").write_text(edited_gitignore, encoding="utf-8")
    (first / ".dockerignore").write_text(edited_dockerignore, encoding="utf-8")
    emit_repository_hygiene_files(
        output_dir=first,
        **{**common, "generation_run_id": "regeneration"},
    )
    assert (first / ".gitignore").read_text(encoding="utf-8") == edited_gitignore
    assert (first / ".dockerignore").read_text(encoding="utf-8") == edited_dockerignore

    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()
    (unmarked / ".gitignore").write_text("# adopter supplied\n", encoding="utf-8")
    emit_repository_hygiene_files(output_dir=unmarked, **common)
    assert (unmarked / ".gitignore").read_text(encoding="utf-8") == "# adopter supplied\n"


def test_generated_pom_artifact_id_has_no_spaces() -> None:
    metadata = _minimal_metadata(
        app_name="ExampleApp",
        bounded_context="Basic DDA App",
    )

    pom_xml = _render_pom_xml(
        metadata=metadata,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="tests/fixtures/basic-dda/app-definition.yaml",
        generation_run_id="build-emitter-artifact-id-test",
    )

    assert "<artifactId>Basic DDA App</artifactId>" not in pom_xml
    assert "<artifactId>basic-dda-app</artifactId>" in pom_xml
    assert "<name>ExampleApp</name>" in pom_xml


def test_generated_pom_adds_spring_ws_dependency_for_inbound_soap_contract() -> None:
    metadata = _minimal_metadata(
        app_name="SOAP Inbound",
        bounded_context="soap_inbound",
    )
    metadata.contracts = [
        ContractMetadata(
            name="customer-soap-service",
            type="soap-wsdl",
            source="contracts/customer-service.wsdl",
            soap_contract={"direction": "upstream", "operations": []},
        )
    ]

    pom_xml = _render_pom_xml(
        metadata=metadata,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="tests/fixtures/edgecontracts/soap-wsdl/basic-inbound-customer-service/app-definition.yaml",
        generation_run_id="build-emitter-soap-test",
    )

    assert "<artifactId>spring-boot-starter-webservices</artifactId>" in pom_xml


def test_generated_pom_adds_spring_ws_dependency_for_outbound_soap_contract() -> None:
    metadata = _minimal_metadata(
        app_name="SOAP Outbound",
        bounded_context="soap_outbound",
    )
    metadata.contracts = [
        ContractMetadata(
            name="customer-soap-client",
            type="soap-wsdl",
            source="contracts/customer-service.wsdl",
            soap_contract={"direction": "downstream", "operations": []},
        )
    ]

    pom_xml = _render_pom_xml(
        metadata=metadata,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="tests/fixtures/edgecontracts/soap-wsdl/basic-outbound-customer-client/app-definition.yaml",
        generation_run_id="build-emitter-soap-client-test",
    )

    assert "<artifactId>spring-boot-starter-webservices</artifactId>" in pom_xml


def test_generated_application_yaml_sets_single_spring_ws_path_for_inbound_soap() -> None:
    from appbuilder.generation.build_emitter import _render_application_yaml

    metadata = _minimal_metadata(
        app_name="SOAP Inbound",
        bounded_context="soap_inbound",
    )
    metadata.contracts = [
        ContractMetadata(
            name="customer-soap-service",
            type="soap-wsdl",
            source="contracts/customer-service.wsdl",
            soap_contract={"direction": "upstream", "operations": []},
        )
    ]

    application_yaml = _render_application_yaml(
        metadata=metadata,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="tests/fixtures/edgecontracts/soap-wsdl/basic-inbound-customer-service/app-definition.yaml",
        generation_run_id="build-emitter-soap-yaml-test",
    )

    assert "  webservices:\n    path: /ws" in application_yaml
    assert "        transformWsdlLocations: true" in application_yaml


def test_generated_application_yaml_sets_outbound_soap_client_uri() -> None:
    from appbuilder.generation.build_emitter import _render_application_yaml

    metadata = _minimal_metadata(
        app_name="SOAP Outbound",
        bounded_context="soap_outbound",
    )
    metadata.contracts = [
        ContractMetadata(
            name="customer-soap-client",
            type="soap-wsdl",
            source="contracts/customer-service.wsdl",
            soap_contract={"direction": "downstream", "operations": []},
        )
    ]

    application_yaml = _render_application_yaml(
        metadata=metadata,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="tests/fixtures/edgecontracts/soap-wsdl/basic-outbound-customer-client/app-definition.yaml",
        generation_run_id="build-emitter-soap-client-yaml-test",
    )

    assert "  soap:\n    clients:\n      customer-soap-client:" in application_yaml
    assert "        uri: http://localhost:8080/ws" in application_yaml
    assert "  webservices:" not in application_yaml


def test_generated_pom_does_not_add_spring_ws_dependency_without_inbound_soap() -> None:
    metadata = _minimal_metadata(
        app_name="Plain CRUD",
        bounded_context="plain_crud",
    )

    pom_xml = _render_pom_xml(
        metadata=metadata,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="tests/fixtures/basic-dda/app-definition.yaml",
        generation_run_id="build-emitter-no-soap-test",
    )

    assert "<artifactId>spring-boot-starter-webservices</artifactId>" not in pom_xml


def test_generated_dockerfile_uses_sanitized_jar_name() -> None:
    metadata = _minimal_metadata(
        app_name="ExampleApp",
        bounded_context="Basic DDA App",
    )

    dockerfile = _render_dockerfile(
        metadata=metadata,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="tests/fixtures/basic-dda/app-definition.yaml",
        generation_run_id="build-emitter-dockerfile-test",
    )

    assert "/workspace/target/basic-dda-app-0.0.1-SNAPSHOT.jar" in dockerfile
    assert "/workspace/target/Basic DDA App-0.0.1-SNAPSHOT.jar" not in dockerfile


def test_generated_dockerfile_runs_as_non_root() -> None:
    metadata = _minimal_metadata(
        app_name="ExampleApp",
        bounded_context="Basic DDA App",
    )

    dockerfile = _render_dockerfile(
        metadata=metadata,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="tests/fixtures/basic-dda/app-definition.yaml",
        generation_run_id="build-emitter-dockerfile-nonroot-test",
    )

    assert "RUN groupadd --system edgeforge && useradd --system --gid edgeforge" in dockerfile
    assert "COPY --from=build --chown=edgeforge:edgeforge" in dockerfile
    assert "RUN chown -R edgeforge:edgeforge /app" in dockerfile
    assert "USER edgeforge" in dockerfile
    assert dockerfile.index("USER edgeforge") < dockerfile.index("ENTRYPOINT")


def test_generated_application_yaml_hardens_health_and_shutdown() -> None:
    from appbuilder.generation.build_emitter import _render_application_yaml

    metadata = _minimal_metadata(
        app_name="ExampleApp",
        bounded_context="Basic DDA App",
    )

    application_yaml = _render_application_yaml(
        metadata=metadata,
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="tests/fixtures/basic-dda/app-definition.yaml",
        generation_run_id="build-emitter-yaml-hardening-test",
    )

    assert "server:\n  port: 8080\n  shutdown: graceful" in application_yaml
    assert "  lifecycle:\n    timeout-per-shutdown-phase: 30s" in application_yaml
    assert "      show-details: when-authorized" in application_yaml
    assert "      roles: ACTUATOR" in application_yaml
    assert "show-details: always" not in application_yaml


def test_generated_readme_and_agent_context_warn_about_tls_gateway() -> None:
    from appbuilder.generation.build_emitter import _render_agent_context, _render_readme

    metadata = _minimal_metadata(
        app_name="ExampleApp",
        bounded_context="Basic DDA App",
    )
    profile = TARGET_PROFILES["springboot-legacy-compatible"]

    readme = _render_readme(
        metadata=metadata,
        target_profile=profile,
        source_manifest="tests/fixtures/basic-dda/app-definition.yaml",
        generation_run_id="build-emitter-security-note-test",
        emit_test_console=True,
    )
    agent_context = _render_agent_context(
        metadata=metadata,
        target_profile=profile,
        source_manifest="tests/fixtures/basic-dda/app-definition.yaml",
        generation_run_id="build-emitter-security-note-test",
        emit_test_console=True,
    )

    assert "**local development/testing only**" in readme
    assert "docker run -p 127.0.0.1:8080:8080 appbuilder-generated-app" in readme
    assert "docker run -p 8080:8080" not in readme

    expected = "plain HTTP and no built-in authentication"
    gateway = "TLS-terminating, authenticated gateway"
    for generated_guidance in (readme, agent_context):
        assert expected in generated_guidance
        assert gateway in generated_guidance
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


def test_bounded_context_helpers_handle_spaces() -> None:
    metadata = _minimal_metadata(
        app_name="ExampleApp",
        bounded_context="Basic DDA App",
    )

    assert to_snake_case(metadata.bounded_context) == "basic_dda_app"
    assert to_pascal_case(metadata.bounded_context) == "BasicDDAApp"
    assert base_package(metadata) == "com.appbuilder.basic_dda_app"


def test_supports_spec_route_only_allows_supported_shapes() -> None:
    assert supports_spec_route(
        path="/pet",
        http_method=HttpMethod.POST,
        response_shape=ResponseShape.CREATED,
        path_parameter_count=0,
    )
    assert supports_spec_route(
        path="/pet/{petId}",
        http_method=HttpMethod.GET,
        response_shape=ResponseShape.SINGLE,
        path_parameter_count=1,
    )
    assert supports_spec_route(
        path="/accounts/{accountId}/transactions",
        http_method=HttpMethod.GET,
        response_shape=ResponseShape.LIST,
        path_parameter_count=1,
    )
    assert supports_spec_route(
        path="/pets",
        http_method=HttpMethod.GET,
        response_shape=ResponseShape.LIST,
        path_parameter_count=0,
    )
    assert supports_spec_route(
        path="/pet/{petId}",
        http_method=HttpMethod.PUT,
        response_shape=ResponseShape.SINGLE,
        path_parameter_count=1,
    )
    assert supports_spec_route(
        path="/pet/{petId}",
        http_method=HttpMethod.DELETE,
        response_shape=ResponseShape.VOID,
        path_parameter_count=1,
    )

    assert not supports_spec_route(
        path="/pet/{petId}",
        http_method=HttpMethod.POST,
        response_shape=ResponseShape.CREATED,
        path_parameter_count=1,
    )
    assert not supports_spec_route(
        path="/pet",
        http_method=HttpMethod.GET,
        response_shape=ResponseShape.SINGLE,
        path_parameter_count=0,
    )
    assert not supports_spec_route(
        path="/pets/{petId}/owners/{ownerId}",
        http_method=HttpMethod.GET,
        response_shape=ResponseShape.LIST,
        path_parameter_count=2,
    )
