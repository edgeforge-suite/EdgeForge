from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project
from appbuilder.target_profiles.catalog import TARGET_PROFILES

pytestmark = pytest.mark.skipif(
    os.getenv("EDGEFORGE_RUN_GENERATED_RUNTIME_TESTS") != "1",
    reason="generated-app Maven/runtime proof runs in the generated-app compile workflow",
)

_MANIFEST = Path(
    "tests/fixtures/generated-app-quality/crud-dto-list-contract/app-definition.yaml"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "target_profile",
    ("springboot-legacy-compatible",),
)
def test_generated_crud_pagination_bounds_reject_before_service_call(
    tmp_path: Path,
    target_profile: str,
) -> None:
    first_output = tmp_path / "crud-pagination-first"
    second_output = tmp_path / "crud-pagination-second"
    metadata = build_metadata_project(_MANIFEST)
    metadata.target_profile = target_profile
    customer_name = next(
        field
        for entity in metadata.entities
        if entity.name == "Customer"
        for field in entity.fields
        if field.name == "customerName"
    )
    customer_name.max_length = 12

    for output_dir in (first_output, second_output):
        report = generate_application(
            metadata,
            output_dir,
            source_manifest=_MANIFEST.as_posix(),
            generation_run_id="crud-pagination-runtime",
        )
        assert report.warnings == []
        assert report.harness_report is not None
        assert report.harness_report.passed

    assert _project_bytes(first_output) == _project_bytes(second_output)

    java_test = (
        first_output
        / "src/test/java/com/appbuilder/crmdto/adapter/inbound/CustomerPaginationBoundsTest.java"
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
        first_output
        / "src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker"
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
    dependency_tree = (first_output / "target/dependency-tree.txt").read_text(
        encoding="utf-8"
    )
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


def _project_bytes(project: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in sorted(project.rglob("*"))
        if path.is_file()
    }


_JAVA_TEST = """\
package com.appbuilder.crmdto.adapter.inbound;

import com.appbuilder.crmdto.exception.GlobalExceptionHandler;
import com.appbuilder.crmdto.adapter.inbound.CreateCustomerRequest;
import com.appbuilder.crmdto.adapter.inbound.CreateCustomerResponse;
import com.appbuilder.crmdto.service.CustomerService;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CustomerController.class)
@Import(GlobalExceptionHandler.class)
class CustomerPaginationBoundsTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private CustomerService customerService;

    @Test
    void rejectsAsciiStringOneCodePointAboveMaximum() throws Exception {
        mockMvc.perform(post("/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"customerName\\\":\\\"ABCDEFGHIJKLM\\\",\\\"email\\\":\\\"a@example.com\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value(containsString("customerName")));

        verifyNoInteractions(customerService);
    }

    @Test
    void acceptsAsciiStringAtExactCodePointMaximum() throws Exception {
        when(customerService.createCustomer(any(CreateCustomerRequest.class)))
            .thenReturn(new CreateCustomerResponse());

        mockMvc.perform(post("/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"customerName\\\":\\\"ABCDEFGHIJKL\\\",\\\"email\\\":\\\"a@example.com\\\"}"))
            .andExpect(status().isCreated());

        verify(customerService).createCustomer(any(CreateCustomerRequest.class));
    }

    @Test
    void rejectsSupplementaryUnicodeOneCodePointAboveMaximum() throws Exception {
        mockMvc.perform(post("/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"customerName\\\":\\\"ABCDEFGHIJKL\\uD83D\\uDE80\\\",\\\"email\\\":\\\"a@example.com\\\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value(containsString("customerName")));

        verifyNoInteractions(customerService);
    }

    @Test
    void acceptsSupplementaryUnicodeAtExactCodePointMaximum() throws Exception {
        when(customerService.createCustomer(any(CreateCustomerRequest.class)))
            .thenReturn(new CreateCustomerResponse());

        mockMvc.perform(post("/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"customerName\\\":\\\"ABCDEFGHIJK\\uD83D\\uDE80\\\",\\\"email\\\":\\\"a@example.com\\\"}"))
            .andExpect(status().isCreated());

        verify(customerService).createCustomer(any(CreateCustomerRequest.class));
    }

    @Test
    void rejectsPageSizeImmediatelyAboveLimit() throws Exception {
        mockMvc.perform(get("/customers/page").param("page", "0").param("size", "201"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.error").value("Bad Request"))
            .andExpect(jsonPath("$.message").value("size must not exceed 200"))
            .andExpect(jsonPath("$.path").value("/customers/page"));

        verifyNoInteractions(customerService);
    }

    @Test
    void rejectsOffsetImmediatelyAboveLimit() throws Exception {
        mockMvc.perform(get("/customers/page").param("page", "16667").param("size", "3"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.error").value("Bad Request"))
            .andExpect(jsonPath("$.message").value("page offset must not exceed 50000"))
            .andExpect(jsonPath("$.path").value("/customers/page"));

        verifyNoInteractions(customerService);
    }

    @Test
    void acceptsMaximumPageSize() throws Exception {
        when(customerService.pageCustomers(any(Pageable.class))).thenReturn(Page.empty());

        mockMvc.perform(get("/customers/page").param("page", "0").param("size", "200"))
            .andExpect(status().isOk());

        assertRequestedPage(0, 200, 0L);
    }

    @Test
    void acceptsMaximumPageOffset() throws Exception {
        when(customerService.pageCustomers(any(Pageable.class))).thenReturn(Page.empty());

        mockMvc.perform(get("/customers/page").param("page", "250").param("size", "200"))
            .andExpect(status().isOk());

        assertRequestedPage(250, 200, 50_000L);
    }

    @Test
    void acceptsRequestBelowBothLimits() throws Exception {
        when(customerService.pageCustomers(any(Pageable.class))).thenReturn(Page.empty());

        mockMvc.perform(get("/customers/page").param("page", "2").param("size", "20"))
            .andExpect(status().isOk());

        assertRequestedPage(2, 20, 40L);
    }

    @Test
    void retainsNegativePageRejection() throws Exception {
        mockMvc.perform(get("/customers/page").param("page", "-1").param("size", "20"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.error").value("Bad Request"))
            .andExpect(jsonPath("$.message").isNotEmpty());

        verifyNoInteractions(customerService);
    }

    @Test
    void retainsZeroSizeRejection() throws Exception {
        mockMvc.perform(get("/customers/page").param("page", "0").param("size", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.error").value("Bad Request"))
            .andExpect(jsonPath("$.message").isNotEmpty());

        verifyNoInteractions(customerService);
    }

    private void assertRequestedPage(int page, int size, long offset) {
        ArgumentCaptor<Pageable> pageable = ArgumentCaptor.forClass(Pageable.class);
        verify(customerService).pageCustomers(pageable.capture());
        assertThat(pageable.getValue().getPageNumber()).isEqualTo(page);
        assertThat(pageable.getValue().getPageSize()).isEqualTo(size);
        assertThat(pageable.getValue().getOffset()).isEqualTo(offset);
    }
}
"""
