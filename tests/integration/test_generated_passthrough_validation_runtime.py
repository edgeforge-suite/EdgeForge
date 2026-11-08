from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project
from appbuilder.target_profiles.catalog import TARGET_PROFILES

pytestmark = pytest.mark.skipif(
    os.getenv("EDGEFORGE_RUN_GENERATED_RUNTIME_TESTS") != "1",
    reason="generated-app Maven/runtime proof runs in the generated-app compile workflow",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
@pytest.mark.parametrize(
    "target_profile",
    ("springboot-legacy-compatible",),
)
def test_generated_passthrough_validation_rejects_before_collaborator_calls(
    tmp_path: Path,
    openapi_version: str,
    target_profile: str,
) -> None:
    manifest = _write_constrained_passthrough_package(
        tmp_path / "input",
        openapi_version=openapi_version,
    )
    first_output = tmp_path / "passthrough-validation-first"
    second_output = tmp_path / "passthrough-validation-second"
    metadata = build_metadata_project(manifest)
    metadata.target_profile = target_profile

    upstream_operations = [
        operation
        for operation in metadata.operations
        if operation.interface_name == "inbound-request-api"
    ]
    assert [operation.name for operation in upstream_operations] == [
        "routeRequest",
        "retryRequest",
    ]
    upstream = upstream_operations[0]
    request_fields = {field.name: field for field in upstream.request_fields}
    assert request_fields["routeKey"].required
    assert request_fields["payload"].required
    assert request_fields["payload"].max_length == 12
    assert request_fields["auditCode"].required
    assert request_fields["auditCode"].max_length == 8
    assert request_fields["recipientRecipientCode"].required
    assert request_fields["recipientRecipientCode"].max_length == 6
    assert not request_fields["optionalEnvelopeNote"].required
    assert request_fields["optionalEnvelopeNote"].max_length == 5

    for output_dir in (first_output, second_output):
        report = generate_application(
            metadata,
            output_dir,
            source_manifest=str(manifest),
            generation_run_id="passthrough-validation-runtime",
        )
        assert report.warnings == []
        assert report.harness_report is None

    assert _project_bytes(first_output) == _project_bytes(second_output)

    inbound_dto = next(first_output.rglob("InboundRequestDto.java")).read_text(
        encoding="utf-8"
    )
    assert (
        "@NotNull\n    @CodePointLength(max=12)\n    private String payload;"
        in inbound_dto
    )
    assert (
        "@NotNull\n    @CodePointLength(max=8)\n    private String auditCode;"
        in inbound_dto
    )
    assert (
        "@NotNull\n    @CodePointLength(max=6)\n    private String recipientRecipientCode;"
        in inbound_dto
    )
    assert (
        "@CodePointLength(max=5)\n    private String optionalEnvelopeNote;"
        in inbound_dto
    )

    java_test = (
        first_output
        / "src/test/java/com/appbuilder/validationruntime/controller/InboundValidationTest.java"
    )
    java_test.parent.mkdir(parents=True, exist_ok=True)
    java_source = _JAVA_TEST
    if TARGET_PROFILES[target_profile].experimental_boot41:
        java_source = java_source.replace(
            "org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest",
            "org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest",
        ).replace(
            "org.springframework.boot.test.mock.mockito.MockBean",
            "org.springframework.test.context.bean.override.mockito.MockitoBean",
        ).replace("@MockBean", "@MockitoBean")
    java_test.write_text(java_source, encoding="utf-8")
    mock_maker = (
        first_output / "src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker"
    )
    mock_maker.parent.mkdir(parents=True, exist_ok=True)
    mock_maker.write_text("mock-maker-subclass\n", encoding="utf-8")

    subprocess.run(
        [
            "mvn",
            "-q",
            "clean",
            "verify",
            "dependency:tree",
            "-DoutputFile=target/dependency-tree.txt",
        ],
        cwd=first_output,
        check=True,
        timeout=240,
    )
    dependency_tree = (first_output / "target/dependency-tree.txt").read_text(encoding="utf-8")
    assert "org.springframework.boot:spring-boot-starter-validation" in dependency_tree
    assert "org.hibernate.validator:hibernate-validator" in dependency_tree
    lowered_tree = dependency_tree.lower()
    for forbidden in ("edgeforge", "knowledge-server", "knowledge server", "studio", "mcp"):
        assert forbidden not in lowered_tree

    subprocess.run(
        [
            sys.executable,
            str(_REPO_ROOT / "scripts/smoke/generated_app_independence.py"),
            "--package",
            str(first_output),
            "--require-packaged-jar",
        ],
        cwd=_REPO_ROOT,
        check=True,
        timeout=120,
    )


@pytest.mark.parametrize("openapi_version", ["3.0.3", "3.1.0"])
def test_required_parent_presence_fails_before_runtime_generation(
    tmp_path: Path,
    openapi_version: str,
) -> None:
    manifest = _write_constrained_passthrough_package(
        tmp_path / "input",
        openapi_version=openapi_version,
    )
    spec_path = manifest.parent / "upstream/request-openapi.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    request_schema = spec["components"]["schemas"]["InboundRequest"]
    request_schema["required"].append("optionalEnvelope")
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    output = tmp_path / "must-not-exist"

    with pytest.raises(ValueError) as exc_info:
        metadata = build_metadata_project(manifest)
        generate_application(
            metadata,
            output,
            source_manifest=str(manifest),
            generation_run_id="required-parent-presence",
        )

    message = str(exc_info.value)
    assert "OpenAPI interface 'inbound-request-api'" in message
    assert "operation 'routeRequest'" in message
    assert "required field 'optionalEnvelope'" in message
    assert "presence cannot be preserved after flattening" in message
    assert not output.exists()


def _write_constrained_passthrough_package(
    package: Path,
    *,
    openapi_version: str,
) -> Path:
    upstream = package / "upstream"
    downstream = package / "downstream"
    rules = package / "rules"
    upstream.mkdir(parents=True)
    downstream.mkdir(parents=True)
    rules.mkdir(parents=True)

    manifest = package / "app-definition.yaml"
    manifest.write_text(
        dedent(
            """\
            app_name: ValidationRuntime
            bounded_context: validationruntime
            schema_version: "2.0"
            app_archetype: passthrough-router
            upstream_interfaces:
              - name: inbound-request-api
                type: rest-json
                spec: upstream/request-openapi.yaml
            downstream_interfaces:
              - name: target-api
                system: APP_PRIMARY
                type: rest-json
                spec: downstream/target-openapi.yaml
            rules:
              - rules/routing.yaml
            target_profile: springboot-legacy-compatible
            """
        ),
        encoding="utf-8",
    )
    (upstream / "request-openapi.yaml").write_text(
        dedent(
            f"""\
            openapi: {openapi_version}
            info:
              title: Validation Runtime Input API
              version: "1.0"
            paths:
              /requests:
                post:
                  operationId: routeRequest
                  requestBody:
                    required: true
                    content:
                      application/json:
                        schema:
                          $ref: "#/components/schemas/InboundRequestAlias"
                  responses:
                    "200":
                      description: Routed response
                      content:
                        application/json:
                          schema:
                            $ref: "#/components/schemas/InboundResponse"
              /retry-requests:
                post:
                  operationId: retryRequest
                  requestBody:
                    required: true
                    content:
                      application/json:
                        schema:
                          $ref: "#/components/schemas/InboundRequestAlias"
                  responses:
                    "200":
                      description: Retried response
                      content:
                        application/json:
                          schema:
                            $ref: "#/components/schemas/InboundResponse"
            components:
              schemas:
                InboundRequestAlias:
                  $ref: "#/components/schemas/InboundRequest"
                InboundRequest:
                  type: object
                  required: [routeKey, payload, auditCode, recipient]
                  properties:
                    routeKey:
                      type: string
                      maxLength: 16
                    payload:
                      $ref: "#/components/schemas/PayloadAlias"
                      maxLength: 16
                    auditCode:
                      $ref: "#/components/schemas/AuditCodeAlias"
                    optionalNote:
                      type: string
                    optionalEnvelope:
                      type: object
                      properties:
                        note:
                          type: string
                          maxLength: 5
                    recipient:
                      $ref: "#/components/schemas/RecipientEnvelope"
                  allOf:
                    - type: object
                      properties:
                        payload:
                          type: string
                          maxLength: 12
                PayloadAlias:
                  $ref: "#/components/schemas/Payload"
                Payload:
                  allOf:
                    - $ref: "#/components/schemas/PayloadBase"
                    - maxLength: 18
                PayloadBase:
                  type: string
                  maxLength: 20
                AuditCodeAlias:
                  $ref: "#/components/schemas/AuditCode"
                AuditCode:
                  allOf:
                    - $ref: "#/components/schemas/AuditCodeBase"
                    - maxLength: 8
                AuditCodeBase:
                  type: string
                  maxLength: 10
                RecipientEnvelope:
                  allOf:
                    - $ref: "#/components/schemas/RecipientEnvelopeBase"
                RecipientEnvelopeBase:
                  type: object
                  required: [recipientCode]
                  properties:
                    recipientCode:
                      $ref: "#/components/schemas/RecipientCodeAlias"
                RecipientCodeAlias:
                  $ref: "#/components/schemas/RecipientCode"
                RecipientCode:
                  allOf:
                    - $ref: "#/components/schemas/RecipientCodeBase"
                    - maxLength: 6
                RecipientCodeBase:
                  type: string
                  maxLength: 10
                InboundResponse:
                  type: object
                  properties:
                    result:
                      type: string
            """
        ),
        encoding="utf-8",
    )
    (downstream / "target-openapi.yaml").write_text(
        dedent(
            """\
            openapi: 3.0.3
            info:
              title: Validation Runtime Target API
              version: "1.0"
            paths:
              /requests:
                post:
                  operationId: sendRequest
                  requestBody:
                    required: true
                    content:
                      application/json:
                        schema:
                          $ref: "#/components/schemas/OutboundRequest"
                  responses:
                    "200":
                      description: Accepted response
                      content:
                        application/json:
                          schema:
                            $ref: "#/components/schemas/OutboundResponse"
            components:
              schemas:
                OutboundRequest:
                  type: object
                  required: [targetPayload]
                  properties:
                    targetPayload:
                      type: string
                OutboundResponse:
                  type: object
                  properties:
                    result:
                      type: string
            """
        ),
        encoding="utf-8",
    )
    (rules / "routing.yaml").write_text(
        dedent(
            """\
            routing_rules:
              route_field: routeKey
              routes:
                - match: PRIMARY
                  target: APP_PRIMARY
              default_target: APP_PRIMARY

            transforms:
              - source: payload
                target: targetPayload
            """
        ),
        encoding="utf-8",
    )
    return manifest


def _project_bytes(project: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in sorted(project.rglob("*"))
        if path.is_file()
    }


_JAVA_TEST = """\
package com.appbuilder.validationruntime.controller;

import com.appbuilder.validationruntime.client.AppPrimaryClient;
import com.appbuilder.validationruntime.dto.InboundRequestDto;
import com.appbuilder.validationruntime.dto.OutboundRequestDto;
import com.appbuilder.validationruntime.dto.OutboundResponseDto;
import com.appbuilder.validationruntime.exception.GlobalExceptionHandler;
import com.appbuilder.validationruntime.service.RoutingService;
import com.appbuilder.validationruntime.service.TransformService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.aMapWithSize;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InboundController.class)
@Import(GlobalExceptionHandler.class)
class InboundValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private TransformService transformService;

    @MockBean
    private RoutingService routingService;

    @MockBean
    private AppPrimaryClient appPrimaryClient;

    @Test
    void rejectsMissingRequiredFieldBeforeAnyCollaborator() throws Exception {
        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"auditCode\\\":\\\"AUDIT001\\\",\\\"recipientRecipientCode\\\":\\\"ABC123\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$", aMapWithSize(5)))
            .andExpect(jsonPath("$.timestamp").isString())
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.error").value("Bad Request"))
            .andExpect(jsonPath("$.message").value("payload: NotNull"))
            .andExpect(jsonPath("$.path").value("/requests"));

        verifyNoInteractions(transformService, routingService, appPrimaryClient);
    }

    @Test
    void rejectsMissingUnusedRequiredFieldBeforeAnyCollaborator() throws Exception {
        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":\\\"BOUNDARY-001\\\",\\\"recipientRecipientCode\\\":\\\"ABC123\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("auditCode: NotNull"));

        verifyNoInteractions(transformService, routingService, appPrimaryClient);
    }

    @Test
    void rejectsUnusedStringOneCodePointAboveMaximumBeforeAnyCollaborator() throws Exception {
        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":\\\"BOUNDARY-001\\\",\\\"auditCode\\\":\\\"AUDIT0001\\\",\\\"recipientRecipientCode\\\":\\\"ABC123\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("auditCode: CodePointLength"));

        verifyNoInteractions(transformService, routingService, appPrimaryClient);
    }

    @Test
    void rejectsExplicitNullRequiredFieldBeforeAnyCollaborator() throws Exception {
        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":null,\\\"auditCode\\\":\\\"AUDIT001\\\",\\\"recipientRecipientCode\\\":\\\"ABC123\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("payload: NotNull"));

        verifyNoInteractions(transformService, routingService, appPrimaryClient);
    }

    @Test
    void rejectsAsciiStringOneCodePointAboveMaximumWithoutEchoingIt() throws Exception {
        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":\\\"REJECTED-0001\\\",\\\"auditCode\\\":\\\"AUDIT001\\\",\\\"recipientRecipientCode\\\":\\\"ABC123\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$", aMapWithSize(5)))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.error").value("Bad Request"))
            .andExpect(jsonPath("$.message").value("payload: CodePointLength"))
            .andExpect(jsonPath("$.path").value("/requests"))
            .andExpect(content().string(not(containsString("REJECTED-0001"))));

        verifyNoInteractions(transformService, routingService, appPrimaryClient);
    }

    @Test
    void rejectsSupplementaryUnicodeOneCodePointAboveMaximum() throws Exception {
        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":\\\"ABCDEFGHIJKL\\uD83D\\uDE80\\\",\\\"auditCode\\\":\\\"AUDIT001\\\",\\\"recipientRecipientCode\\\":\\\"ABC123\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("payload: CodePointLength"));

        verifyNoInteractions(transformService, routingService, appPrimaryClient);
    }

    @Test
    void rejectsMissingFlattenedNestedRequiredFieldBeforeAnyCollaborator() throws Exception {
        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":\\\"BOUNDARY-001\\\",\\\"auditCode\\\":\\\"AUDIT001\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("recipientRecipientCode: NotNull"));

        verifyNoInteractions(transformService, routingService, appPrimaryClient);
    }

    @Test
    void rejectsFlattenedNestedFieldAboveMaximumWithoutEchoingIt() throws Exception {
        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":\\\"BOUNDARY-001\\\",\\\"auditCode\\\":\\\"AUDIT001\\\",\\\"recipientRecipientCode\\\":\\\"SECRET7\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$", aMapWithSize(5)))
            .andExpect(jsonPath("$.message").value("recipientRecipientCode: CodePointLength"))
            .andExpect(content().string(not(containsString("SECRET7"))));

        verifyNoInteractions(transformService, routingService, appPrimaryClient);
    }

    @Test
    void acceptsAsciiStringExactlyAtMaximumAndRunsTheRoute() throws Exception {
        OutboundRequestDto outboundRequest = stubSuccessfulRoute();

        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":\\\"BOUNDARY-001\\\",\\\"auditCode\\\":\\\"AUDIT001\\\",\\\"recipientRecipientCode\\\":\\\"ABC123\\\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("accepted"));

        verify(transformService).transform(any(InboundRequestDto.class));
        verify(routingService).route(any(InboundRequestDto.class));
        verify(appPrimaryClient).send(outboundRequest);
    }

    @Test
    void acceptsSupplementaryUnicodeAtExactCodePointMaximum() throws Exception {
        OutboundRequestDto outboundRequest = stubSuccessfulRoute();

        mockMvc.perform(post("/requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":\\\"ABCDEFGHIJK\\uD83D\\uDE80\\\",\\\"auditCode\\\":\\\"AUDIT001\\\",\\\"recipientRecipientCode\\\":\\\"ABC123\\\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("accepted"));

        verify(transformService).transform(any(InboundRequestDto.class));
        verify(routingService).route(any(InboundRequestDto.class));
        verify(appPrimaryClient).send(outboundRequest);
    }

    @Test
    void acceptsSourceValidLaterOperationWithTheSharedValidationContract() throws Exception {
        OutboundRequestDto outboundRequest = stubSuccessfulRoute();

        mockMvc.perform(post("/retry-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"routeKey\\\":\\\"PRIMARY\\\",\\\"payload\\\":\\\"BOUNDARY-001\\\",\\\"auditCode\\\":\\\"AUDIT001\\\",\\\"recipientRecipientCode\\\":\\\"ABC123\\\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("accepted"));

        verify(transformService).transform(any(InboundRequestDto.class));
        verify(routingService).route(any(InboundRequestDto.class));
        verify(appPrimaryClient).send(outboundRequest);
    }

    private OutboundRequestDto stubSuccessfulRoute() {
        OutboundRequestDto outboundRequest = new OutboundRequestDto();
        OutboundResponseDto outboundResponse = new OutboundResponseDto();
        outboundResponse.setResult("accepted");
        when(transformService.transform(any(InboundRequestDto.class))).thenReturn(outboundRequest);
        when(routingService.route(any(InboundRequestDto.class))).thenReturn("APP_PRIMARY");
        when(appPrimaryClient.send(outboundRequest)).thenReturn(outboundResponse);
        return outboundRequest;
    }
}
"""
