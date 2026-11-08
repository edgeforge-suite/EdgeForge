"""Tests for the MVP Generated Operator Dashboard.

# new test file covering:
# - DemoController.java generation
# - Config-gating (appbuilder.demo.enabled)
# - Entity registry in DemoController
# - Upgraded index.html: entity nav, CRUD tabs, request/response panels, live viewer
# - Route alignment between UI and backend
# - application.yaml appbuilder.demo section
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.generation.java_emitter import emit_demo_controller
from appbuilder.generation.ui_emitter import generate_demo_ui
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata import (
    CanonicalField,
    CanonicalFieldType,
    MetadataProject,
    build_metadata_project,
)
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalOperation,
    ContractMetadata,
    HttpMethod,
    PathParameter,
    ResponseShape,
    SystemParticipant,
)
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SOAP_INBOUND_FIXTURE = Path(
    "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml"
)
SOAP_OUTBOUND_FIXTURE = Path(
    "tests/fixtures/edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/app-definition.yaml"
)


def _load_xyz_metadata() -> MetadataProject:
    payload = json.loads(
        Path("tests/golden_contracts/xyz_accounts_metadata.json").read_text(encoding="utf-8")
    )
    return MetadataProject.model_validate(copy.deepcopy(payload))


def _extract_descriptors(html: str) -> list[dict]:
    match = re.search(
        r"const DESCRIPTORS = (\[.*?\]);\n    const DESCRIPTOR_BY_KEY",
        html,
        re.S,
    )
    assert match, "Generated dashboard must expose inline DESCRIPTORS"
    return json.loads(match.group(1))


def _descriptor_by_key(html: str, coverage_key: str) -> dict:
    descriptors = _extract_descriptors(html)
    matches = [
        descriptor
        for descriptor in descriptors
        if descriptor["coverageKey"] == coverage_key
    ]
    assert len(matches) == 1, f"Expected exactly one descriptor for {coverage_key}"
    return matches[0]


def _entity_panel_fragment(html: str, entity_name: str) -> str:
    marker = f'<div id="entity-panel-{entity_name}"'
    start = html.index(marker)
    next_panel = html.find('<div id="entity-panel-', start + len(marker))
    end = next_panel if next_panel != -1 else html.index("</main>", start)
    return html[start:end]


def _group_section_fragment(panel_html: str, group: str) -> str:
    marker = f'data-group="{group}"'
    marker_index = panel_html.index(marker)
    start = panel_html.rfind("<details", 0, marker_index)
    next_section = panel_html.find('<details class="group-section"', marker_index)
    live_section = panel_html.find('<div class="live-section"', marker_index)
    candidates = [idx for idx in [next_section, live_section] if idx != -1]
    end = min(candidates) if candidates else len(panel_html)
    return panel_html[start:end]


def _coverage_map_fragment(html: str) -> str:
    start = html.index('<section class="coverage-map"')
    end = html.index("<!-- per-entity dashboard panels", start)
    return html[start:end]


def _safe_test_dom_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "action"


def _extract_js_block(html: str, start_marker: str, end_marker: str) -> str:
    start = html.index(start_marker)
    end = html.index(end_marker, start)
    return html[start:end]


def _run_node_script(script: str, tmp_path: Path) -> str:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for dashboard JavaScript behavior checks")
    script_path = tmp_path / "dashboard-behavior-check.js"
    script_path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["node", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _two_entity_metadata() -> MetadataProject:
    """Two-entity (Customer + Account) metadata with minimal mappings."""
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=12),
            CanonicalField(name="customerName", type=CanonicalFieldType.STRING, required=True, max_length=50),
        ],
    )
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=12),
            CanonicalField(name="accountType", type=CanonicalFieldType.STRING, required=True, max_length=20),
        ],
    )
    op_customer = CanonicalOperation(name="createCustomer", interface_name="crm-api", request_entity="Customer", response_entity="Customer")
    op_account = CanonicalOperation(name="createAccount", interface_name="crm-api", request_entity="Account", response_entity="Account")
    mappings = [
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createCustomer", source_path="crm-api.createCustomer.request.customerName", target_path="Customer.customerName"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createCustomer", source_path="crm-api.createCustomer.response.customerId", target_path="Customer.customerId"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createAccount", source_path="crm-api.createAccount.request.accountType", target_path="Account.accountType"),
        FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="crm-api", operation_name="createAccount", source_path="crm-api.createAccount.response.accountId", target_path="Account.accountId"),
    ]
    profile_name = "springboot-dashboard-test"
    if profile_name not in TARGET_PROFILES:
        TARGET_PROFILES[profile_name] = TargetProfile(
            name=profile_name, language="java", framework="spring-boot",
            java_baseline="17", spring_boot_baseline="3.3.5",
            emit_flyway=False, emit_spring_batch=False, emit_security=False,
            emit_test_console=True, emit_audit=False, supports_xml=False,
        )
    return MetadataProject(
        app_name="CRM App",
        bounded_context="crm",
        target_profile=profile_name,
        systems=[SystemParticipant(name="CRM", role="upstream")],
        contracts=[ContractMetadata(name="crm-api", type="rest-json", source="")],
        operations=[op_customer, op_account],
        entities=[customer, account],
        mappings=mappings,
    )


def _get_profile() -> TargetProfile:
    name = "springboot-dashboard-test"
    if name not in TARGET_PROFILES:
        TARGET_PROFILES[name] = TargetProfile(
            name=name, language="java", framework="spring-boot",
            java_baseline="17", spring_boot_baseline="3.3.5",
            emit_flyway=False, emit_spring_batch=False, emit_security=False,
            emit_test_console=True, emit_audit=False, supports_xml=False,
        )
    return TARGET_PROFILES[name]


def _descriptor_family_metadata() -> MetadataProject:
    profile_name = "springboot-dashboard-descriptor-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=True,
        emit_spring_batch=True,
        emit_security=False,
        emit_test_console=True,
        emit_audit=False,
        supports_xml=False,
    )
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(
                name="accountId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=36,
            ),
            CanonicalField(
                name="accountType",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=32,
            ),
        ],
    )
    return MetadataProject(
        app_name="Descriptor App",
        bounded_context="descriptor",
        target_profile=profile_name,
        systems=[SystemParticipant(name="Core", role="upstream")],
        contracts=[
            ContractMetadata(
                name="account-api",
                type="rest-json",
                source="upstream/account-openapi.yaml",
                mapping_path="upstream/account-mapping.yaml",
            ),
            ContractMetadata(
                name="account-csv-in",
                type="file-csv",
                source="upstream/account-csv-layout.yaml",
                mapping_path="mappings/account-csv-in.yaml",
            ),
            ContractMetadata(
                name="account-xml-in",
                type="xml-xsd",
                source="contracts/account-in.xsd",
                mapping_path="mappings/account-xml-in.yaml",
            ),
            ContractMetadata(
                name="account-xml-out",
                type="xml-xsd",
                source="contracts/account-out.xsd",
                mapping_path="mappings/account-xml-out.yaml",
            ),
            ContractMetadata(name="account-staging", type="staging-table", source="handoff/account.sql"),
            ContractMetadata(name="account-eod-file", type="file-fixed-width", source="downstream/account.dat.yaml"),
        ],
        operations=[
            CanonicalOperation(
                name="createAccount",
                interface_name="account-api",
                request_entity="Account",
                response_entity="Account",
            )
        ],
        entities=[account],
        mappings=[
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="account-api", operation_name="createAccount", source_path="account-api.createAccount.request.accountType", target_path="Account.accountType"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="account-api", operation_name="createAccount", source_path="account-api.createAccount.response.accountId", target_path="Account.accountId"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="account-csv-in", operation_name="ingestAccountCsv", source_path="account-csv-in.account_id", target_path="Account.accountId"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="account-xml-in", operation_name="ingestAccountXml", source_path="account-xml-in.accountId", target_path="Account.accountId"),
            FieldMapping(direction=MappingDirection.CANONICAL_TO_DOWNSTREAM, contract_name="account-xml-out", operation_name="writeAccountXml", source_path="Account.accountId", target_path="account-xml-out.accountId"),
            FieldMapping(direction=MappingDirection.CANONICAL_TO_HANDOFF, contract_name="account-staging", operation_name="stageAccount", source_path="Account.accountId", target_path="account_staging.account_id"),
            FieldMapping(direction=MappingDirection.CANONICAL_TO_DOWNSTREAM, contract_name="account-eod-file", operation_name="emitAccountEod", source_path="Account.accountId", target_path="account-eod-file.account_id"),
        ],
    )


def _sample_hint_metadata() -> MetadataProject:
    profile_name = "springboot-dashboard-sample-hints-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=False,
        emit_security=False,
        emit_test_console=True,
        emit_audit=False,
        supports_xml=False,
    )
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(
                name="customerId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                max_length=36,
            ),
            CanonicalField(
                name="customerName",
                type=CanonicalFieldType.STRING,
                required=True,
                max_length=50,
                pattern="^C[0-9]+$",
            ),
            CanonicalField(
                name="creditLimit",
                type=CanonicalFieldType.DECIMAL,
                required=True,
                range_min=0,
                range_max=999999,
            ),
            CanonicalField(
                name="openedOn",
                type=CanonicalFieldType.DATE,
                required=False,
            ),
            CanonicalField(
                name="active",
                type=CanonicalFieldType.BOOLEAN,
                required=True,
            ),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=True,
                allowed_values=["NEW", "ACTIVE"],
            ),
            CanonicalField(
                name="segment",
                type=CanonicalFieldType.STRING,
                required=False,
                allowed_values=["RETAIL", "VIP"],
            ),
        ],
    )
    operation = CanonicalOperation(
        name="createCustomer",
        interface_name="customer-api",
        request_entity="Customer",
        response_entity="Customer",
    )
    request_fields = [
        "customerName",
        "creditLimit",
        "openedOn",
        "active",
        "status",
        "segment",
    ]
    mappings = [
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path=f"customer-api.createCustomer.request.{field_name}",
            target_path=f"Customer.{field_name}",
        )
        for field_name in request_fields
    ]
    mappings.append(
        FieldMapping(
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name="customer-api",
            operation_name="createCustomer",
            source_path="customer-api.createCustomer.response.customerId",
            target_path="Customer.customerId",
        )
    )
    return MetadataProject(
        app_name="Sample Hint App",
        bounded_context="samplehint",
        target_profile=profile_name,
        systems=[SystemParticipant(name="CustomerCore", role="upstream")],
        contracts=[
            ContractMetadata(
                name="customer-api",
                type="rest-json",
                source="upstream/customer-openapi.yaml",
                mapping_path="upstream/customer-mapping.yaml",
            )
        ],
        operations=[operation],
        entities=[customer],
        mappings=mappings,
    )


# ---------------------------------------------------------------------------
# Test 1: DemoController.java is in the file list when entities exist
# ---------------------------------------------------------------------------

def test_demo_controller_generated_for_xyz_accounts(tmp_path: Path) -> None:
    """DemoController.java is emitted as part of generate_application output.
    # regression — DemoController must appear in files_created.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "DemoCtrlApp", generation_run_id="demo-ctrl-test")

    paths = {p.relative_to(report.output_dir).as_posix() for p in report.files_created}
    assert "src/main/java/com/appbuilder/accounts/adapter/inbound/DemoController.java" in paths


def test_demo_controller_generated_for_two_entity_app(tmp_path: Path) -> None:
    """DemoController.java generated when multiple entities exist.
    # ensures multi-entity apps also get DemoController.
    """
    metadata = _two_entity_metadata()
    report = generate_application(metadata, tmp_path / "DemoCtrlMulti", generation_run_id="demo-multi-test")

    paths = {p.relative_to(report.output_dir).as_posix() for p in report.files_created}
    assert "src/main/java/com/appbuilder/crm/adapter/inbound/DemoController.java" in paths


# ---------------------------------------------------------------------------
# Test 2: DemoController is config-gated
# ---------------------------------------------------------------------------

def test_demo_controller_contains_config_gate(tmp_path: Path) -> None:
    """Generated DemoController.java contains appbuilder.demo.enabled config gate.
    # the controller must be disabled by default.
    """
    metadata = _load_xyz_metadata()
    profile = _get_profile()
    demo_path = emit_demo_controller(
        metadata=metadata,
        target_profile=profile,
        output_dir=tmp_path,
        source_manifest="test",
        generation_run_id="gate-test",
    )
    source = demo_path.read_text(encoding="utf-8")

    assert "appbuilder.demo.enabled" in source
    assert "Demo endpoints are disabled" in source
    assert "appbuilder.demo.enabled=true" in source


def test_demo_controller_returns_403_when_disabled(tmp_path: Path) -> None:
    """Generated DemoController returns 403 response body when demo is disabled.
    # 403 is the correct status for disabled demo endpoints.
    """
    metadata = _load_xyz_metadata()
    profile = _get_profile()
    demo_path = emit_demo_controller(
        metadata=metadata,
        target_profile=profile,
        output_dir=tmp_path,
        source_manifest="test",
        generation_run_id="403-test",
    )
    source = demo_path.read_text(encoding="utf-8")

    assert "ResponseEntity.status(403)" in source
    assert "demoEnabled" in source


def test_demo_controller_uses_value_annotation(tmp_path: Path) -> None:
    """DemoController uses @Value to inject appbuilder.demo.enabled config.
    # Spring @Value injection is the correct pattern.
    """
    metadata = _load_xyz_metadata()
    profile = _get_profile()
    demo_path = emit_demo_controller(
        metadata=metadata,
        target_profile=profile,
        output_dir=tmp_path,
        source_manifest="test",
        generation_run_id="value-test",
    )
    source = demo_path.read_text(encoding="utf-8")

    assert "@Value(\"${appbuilder.demo.enabled:false}\")" in source


# ---------------------------------------------------------------------------
# Test 3: DemoController entity registry
# ---------------------------------------------------------------------------

def test_demo_controller_entity_registry_contains_all_entities(tmp_path: Path) -> None:
    """DemoController constructor wires all entity repositories into the registry.
    # registry must cover every generated entity.
    """
    metadata = _two_entity_metadata()
    profile = _get_profile()
    demo_path = emit_demo_controller(
        metadata=metadata,
        target_profile=profile,
        output_dir=tmp_path,
        source_manifest="test",
        generation_run_id="registry-test",
    )
    source = demo_path.read_text(encoding="utf-8")

    # Both repositories must be injected
    assert "CustomerRepository" in source
    assert "AccountRepository" in source
    # Both entity names must appear in the registry puts
    assert '"Customer"' in source
    assert '"Account"' in source


def test_demo_controller_imports_all_repositories(tmp_path: Path) -> None:
    """DemoController imports all entity repository classes.
    # imports must be present for the code to compile.
    """
    metadata = _two_entity_metadata()
    profile = _get_profile()
    demo_path = emit_demo_controller(
        metadata=metadata,
        target_profile=profile,
        output_dir=tmp_path,
        source_manifest="test",
        generation_run_id="imports-test",
    )
    source = demo_path.read_text(encoding="utf-8")

    assert "import com.appbuilder.crm.repository.CustomerRepository;" in source
    assert "import com.appbuilder.crm.repository.AccountRepository;" in source


def test_demo_controller_has_entity_list_endpoint(tmp_path: Path) -> None:
    """DemoController has GET /api/demo/entities endpoint.
    # this endpoint returns all entity names.
    """
    metadata = _load_xyz_metadata()
    profile = _get_profile()
    demo_path = emit_demo_controller(
        metadata=metadata,
        target_profile=profile,
        output_dir=tmp_path,
        source_manifest="test",
        generation_run_id="list-ep-test",
    )
    source = demo_path.read_text(encoding="utf-8")

    assert "@GetMapping(\"/entities\")" in source
    assert "@RequestMapping(\"/api/demo\")" in source


def test_demo_controller_has_entity_rows_endpoint(tmp_path: Path) -> None:
    """DemoController has GET /api/demo/entities/{entityName} endpoint capped at 50 rows.
    # rows endpoint with stream().limit(50).
    """
    metadata = _load_xyz_metadata()
    profile = _get_profile()
    demo_path = emit_demo_controller(
        metadata=metadata,
        target_profile=profile,
        output_dir=tmp_path,
        source_manifest="test",
        generation_run_id="rows-ep-test",
    )
    source = demo_path.read_text(encoding="utf-8")

    assert "@GetMapping(\"/entities/{entityName}\")" in source
    assert ".limit(50)" in source


# ---------------------------------------------------------------------------
# Test 4: UI has entity tabs/navigation
# ---------------------------------------------------------------------------

def test_ui_has_entity_navigation(tmp_path: Path) -> None:
    """Generated index.html has sidebar nav buttons for each entity.
    # entity nav items with data-entity attribute.
    """
    metadata = _two_entity_metadata()
    report = generate_application(metadata, tmp_path / "UINavTest", generation_run_id="nav-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'data-entity="Customer"' in html
    assert 'data-entity="Account"' in html


def test_ui_has_entity_panel_ids(tmp_path: Path) -> None:
    """Generated index.html has per-entity panel divs.
    # entity-panel IDs for JS tab switching.
    """
    metadata = _two_entity_metadata()
    report = generate_application(metadata, tmp_path / "UIPanelTest", generation_run_id="panel-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="entity-panel-Customer"' in html
    assert 'id="entity-panel-Account"' in html


# ---------------------------------------------------------------------------
# Test 5: UI has CRUD action sections
# ---------------------------------------------------------------------------

def test_ui_has_crud_tabs(tmp_path: Path) -> None:
    """Generated index.html contains Create, Get by ID, List, Update, Delete CRUD tabs.
    # all CRUD operations rendered as tabs.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UICRUDTest", generation_run_id="crud-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    # CRUD tab labels must all be present
    assert "Create" in html
    assert "Get by ID" in html
    assert "List" in html
    assert "Update" in html
    assert "Delete" in html


def test_ui_has_crud_panel_ids(tmp_path: Path) -> None:
    """Generated index.html has CRUD panel div IDs per entity.
    # panel IDs used by JS showCrudTab().
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UICRUDPanelTest", generation_run_id="crud-panel-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="crud-Account-create"' in html
    assert 'id="crud-Account-get"' in html
    assert 'id="crud-Account-list"' in html
    assert 'id="crud-Account-update"' in html
    assert 'id="crud-Account-delete"' in html


# ---------------------------------------------------------------------------
# Test 6: UI shows request preview + response panel
# ---------------------------------------------------------------------------

def test_ui_has_request_preview_panel(tmp_path: Path) -> None:
    """Generated index.html contains request JSON preview panel.
    # req-preview-{entity} div for live preview.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIReqPreviewTest", generation_run_id="req-preview-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="req-preview-Account"' in html
    assert "Request Preview" in html


def test_ui_has_response_panel_for_each_crud_action(tmp_path: Path) -> None:
    """Generated index.html has response panels for all CRUD operations.
    # resp-panel-{entity}-{tab} for status/timing/body.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIRespPanelTest", generation_run_id="resp-panel-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="resp-panel-Account-create"' in html
    assert 'id="resp-panel-Account-get"' in html
    assert 'id="resp-panel-Account-list"' in html
    assert 'id="resp-panel-Account-update"' in html
    assert 'id="resp-panel-Account-delete"' in html


def test_ui_js_renders_http_status_and_timing(tmp_path: Path) -> None:
    """Generated JS includes numeric status badges, timing, and timestamp display.
    # status badge (HTTP code), ms timing, and runtime timestamp shown after submit.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIStatusTest", generation_run_id="status-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert "status-badge" in html
    assert ".status-badge.ok" in html
    assert ".status-badge.warn" in html
    assert ".status-badge.err" in html
    assert ".status-badge.fault" in html
    assert "function statusBadgeClass(kind, numericStatus)" in html
    assert "numericStatus >= 500" in html
    assert "numericStatus >= 400" in html
    assert "numericStatus >= 200 && numericStatus < 400" in html
    assert "timing" in html
    assert "function responseTimestamp()" in html
    assert "new Date().toLocaleTimeString" in html
    assert "renderBatchResponse" in html
    assert "function renderResponse(entityName" not in html


def test_ui_js_shows_in_flight_spinner_and_disables_action_button(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UISpinnerTest", generation_run_id="spinner-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert ".spinner" in html
    assert "function renderInFlightResponse(responsePanelId)" in html
    assert "function setActionInFlight(coverageKey, actionIndex, inFlight)" in html
    assert "button.disabled = true;" in html
    assert "button.disabled = false;" in html
    assert "Sending&hellip;" in html
    assert "renderInFlightResponse(responsePanelId || actionResponsePanelId(descriptor));" in html


def test_ui_json_pretty_print_is_dependency_free_and_colorized(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIPrettyJsonTest", generation_run_id="pretty-json-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert "function formatResponseBody(rawText, responseShape)" in html
    assert "function formatJsonLossless(rawText)" in html
    assert "function prettyJsonLossless(rawText)" in html
    assert "function colorizeJson(formatted)" in html
    assert ".json-key" in html
    assert ".json-string" in html
    assert ".json-number" in html
    assert ".json-literal" in html
    assert "JSON.stringify(body, null, 2)" not in html


def test_ui_response_rendering_preserves_raw_money_and_temporal_values(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIRawResponseTest", generation_run_id="raw-response-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert "const rawText = await resp.text();" in html
    assert "await resp.json()" not in html
    assert "renderActionResponse(descriptor, kind, resp.status + ' ' + resp.statusText, rawText" in html
    assert "formatJsonLossless(rawText)" in html
    # JSON response display stays on raw text so numeric lexemes like 123.40 and
    # java.time strings are not round-tripped through JSON.parse/JSON.stringify.
    assert "JSON.parse(rawText)" in html
    assert "payload = rawText ? JSON.parse(rawText) : null;" in html
    assert "formatResponseBody(String(rawBody ?? ''), responseShape || 'JSON')" in html


def test_ui_json_formatter_preserves_money_and_temporal_values_behaviorally(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "UIRawResponseBehaviorTest",
        source_manifest="raw-response-behavior",
        generation_run_id="raw-response-behavior",
    )
    html = html_path.read_text(encoding="utf-8")
    helper_block = _extract_js_block(
        html,
        "function formatJsonLossless(rawText)",
        "    // ---- Value coercion ----",
    )
    script = f"""
{helper_block}
const raw = '{{"amount":123.40,"tiny":0.001000,"large":10000000000000000000.5,"postedAt":"2026-06-07T14:03:22Z"}}';
const rendered = formatJsonLossless(raw);
for (const expected of ['123.40', '0.001000', '10000000000000000000.5', '2026-06-07T14:03:22Z']) {{
  if (!rendered.includes(expected)) {{
    throw new Error('Rendered JSON lost raw token: ' + expected + '\\n' + rendered);
  }}
}}
if (JSON.stringify(JSON.parse(raw)).includes('123.40')) {{
  throw new Error('Native JSON stringify unexpectedly preserved money scale; test is not guarding the regression.');
}}
"""
    _run_node_script(script, tmp_path)


# ---------------------------------------------------------------------------
# Test 7: UI has live data viewer
# ---------------------------------------------------------------------------

def test_ui_live_viewer_calls_demo_entities_api(tmp_path: Path) -> None:
    """Generated JS calls /api/demo/entities/{entityName} for the live viewer.
    # live data viewer backed by DemoController.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UILiveTest", generation_run_id="live-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert "/api/demo/entities/" in html


def test_ui_live_viewer_auto_refreshes(tmp_path: Path) -> None:
    """Generated JS uses setInterval for 5-second auto-refresh of live data.
    # live viewer polls every 5000ms.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIAutoRefreshTest", generation_run_id="autorefresh-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert "setInterval" in html
    assert "5000" in html


def test_ui_live_viewer_shows_graceful_fallback_message(tmp_path: Path) -> None:
    """Generated JS shows helpful message when demo endpoints return 403.
    # graceful fallback when appbuilder.demo.enabled=false.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIFallbackTest", generation_run_id="fallback-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert "appbuilder.demo.enabled=true" in html
    assert "resp.status === 403" in html
    assert "setDemoState('demo data: disabled')" in html


def test_ui_non_production_banner_shows_profile_datasource_and_demo_probe(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UINonProdBannerTest", generation_run_id="banner-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert "NON-PRODUCTION TEST CONSOLE" in html
    assert "local only" in html
    assert f"profile: {metadata.target_profile}" in html
    assert "datasource (configured default): H2" in html
    assert 'id="demo-state-indicator"' in html
    assert "setDemoState('demo data: enabled')" in html
    assert "setDemoState('demo data: disabled')" in html
    assert "/api/demo/entities/" in html


def test_ui_non_production_banner_shows_postgres_configured_datasource(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    metadata.target_profile = "springboot-enterprise-postgres-java17"
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "UIPostgresBannerTest",
        source_manifest="postgres-banner",
        generation_run_id="postgres-banner",
    )
    html = html_path.read_text(encoding="utf-8")

    assert f"profile: {metadata.target_profile}" in html
    assert "datasource (configured default): PostgreSQL" in html


def test_ui_live_viewer_uses_raw_scalar_values_for_table_cells(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UILiveRawValuesTest", generation_run_id="live-raw-values-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert "const rawText = await resp.text();" in html
    assert "const rawRows = extractRawScalarRows(rawText, rows);" in html
    assert "rawRows.length === rows.length" in html
    assert "return rawToken;" in html


def test_ui_live_viewer_raw_scalar_extraction_falls_back_for_nested_rows(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "UILiveRawValuesBehaviorTest",
        source_manifest="live-raw-values-behavior",
        generation_run_id="live-raw-values-behavior",
    )
    html = html_path.read_text(encoding="utf-8")
    helper_block = _extract_js_block(
        html,
        "function topLevelObjectTexts(rawText)",
        "    // ---- Live data viewer",
    )
    script = f"""
{helper_block}
const nestedRaw = '[{{"id":1,"meta":{{"id":99}}}}]';
const nestedRows = JSON.parse(nestedRaw);
const nestedRawRows = extractRawScalarRows(nestedRaw, nestedRows);
if (nestedRawRows.length !== 0) {{
  throw new Error('Nested rows must fall back to parsed values instead of aligning raw fragments by index.');
}}
const nestedDisplay = nestedRawRows.length === nestedRows.length
  ? rawCellDisplay(nestedRawRows[0].id, nestedRows[0].id)
  : String(nestedRows[0].id ?? '');
if (nestedDisplay !== '1') {{
  throw new Error('Nested fallback rendered the wrong id: ' + nestedDisplay);
}}

const flatRaw = '[{{"id":123.40,"postedAt":"2026-06-07T14:03:22Z"}}]';
const flatRows = JSON.parse(flatRaw);
const flatRawRows = extractRawScalarRows(flatRaw, flatRows);
if (flatRawRows.length !== 1 || flatRawRows[0].id !== '123.40') {{
  throw new Error('Flat rows should preserve raw numeric lexemes: ' + JSON.stringify(flatRawRows));
}}
"""
    _run_node_script(script, tmp_path)


def test_ui_live_viewer_has_table_for_each_entity(tmp_path: Path) -> None:
    """Generated HTML has a live-table container for each entity.
    # live-table-{entityName} div populated by JS.
    """
    metadata = _two_entity_metadata()
    report = generate_application(metadata, tmp_path / "UILiveTableTest", generation_run_id="livetable-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'id="live-table-Customer"' in html
    assert 'id="live-table-Account"' in html


def test_ui_retains_config_title_and_reserves_logo_slot(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UITitleLogoTest", generation_run_id="title-logo-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert f"<title>{metadata.app_name} — Initial Test Console</title>" in html
    assert f"<h1>{metadata.app_name} Initial Test Console</h1>" in html
    assert 'class="console-logo-slot"' in html
    assert 'data-logo-slot="reserved"' in html


def test_ui_a11y_roles_focus_and_ctrl_enter_submit(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIA11yTest", generation_run_id="a11y-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'role="tablist"' in html
    assert 'role="tab"' in html
    assert 'aria-selected="true"' in html
    assert 'aria-controls="crud-Account-create"' in html
    assert 'role="tabpanel"' in html
    assert 'aria-labelledby="crud-tab-Account-create"' in html
    assert 'aria-current="false"' in html
    assert "navBtn.setAttribute('aria-current', 'page')" in html
    assert ":focus-visible" in html
    assert "event.ctrlKey && event.key === 'Enter'" in html
    assert "button.click();" in html


# ---------------------------------------------------------------------------
# Test 8: UI routes match backend — /{entityPluralName} pattern
# ---------------------------------------------------------------------------

def test_ui_create_routes_match_backend(tmp_path: Path) -> None:
    """UI create forms POST to /{entityPluralName}, matching the generated controller.
    # route alignment — must match java_emitter.py's entity_path_base.
    """
    metadata = _two_entity_metadata()
    report = generate_application(metadata, tmp_path / "UIRouteTest", generation_run_id="route-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    # DESCRIPTORS in JS must contain entity-level endpoints.
    assert '"/customers"' in html
    assert '"/accounts"' in html


def test_ui_get_routes_use_entity_routes_map(tmp_path: Path) -> None:
    """GET descriptor uses generated controller route, not name guessing.
    # route must come from descriptor metadata so multi-word entities do not
    # fall back to name.toLowerCase()+'s'.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIGetRouteTest", generation_run_id="get-route-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    descriptor = _descriptor_by_key(html, "Account-get")
    action = descriptor["actions"][0]
    assert action["verb"] == "GET"
    assert action["endpoint"] == "/accounts/{id}"
    assert action["inputBinding"] == "PATH_PARAM"
    assert "resolveEndpointTemplate" in html
    # Old broken pattern must NOT be present in CRUD action functions
    assert "entityName.toLowerCase() + 's'" not in html


def test_ui_delete_uses_correct_route_pattern(tmp_path: Path) -> None:
    """Delete descriptor uses DELETE /{entityPluralName}/{id}, matching @DeleteMapping(\"/{id}\").
    # route alignment for DELETE.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIDeleteRouteTest", generation_run_id="delete-route-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    descriptor = _descriptor_by_key(html, "Account-delete")
    action = descriptor["actions"][0]
    assert action["verb"] == "DELETE"
    assert action["endpoint"] == "/accounts/{id}"
    assert action["inputBinding"] == "PATH_PARAM"


def test_ui_update_uses_put_method(tmp_path: Path) -> None:
    """Update descriptor uses PUT method, matching @PutMapping(\"/{id}\").
    # route alignment for PUT update.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIUpdateRouteTest", generation_run_id="update-route-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    descriptor = _descriptor_by_key(html, "Account-update")
    action = descriptor["actions"][0]
    assert action["verb"] == "PUT"
    assert action["endpoint"] == "/accounts/{id}"
    assert action["inputBinding"] == "JSON_BODY"


# ---------------------------------------------------------------------------
# Test: application.yaml includes appbuilder.demo.enabled=false
# ---------------------------------------------------------------------------

def test_application_yaml_has_demo_config(tmp_path: Path) -> None:
    """application.yaml includes appbuilder.demo.enabled: false by default.
    # demo endpoints are disabled by default via application.yaml.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "YamlDemoTest", generation_run_id="yaml-demo-test")
    yaml_text = (report.output_dir / "src/main/resources/application.yaml").read_text(encoding="utf-8")

    assert "appbuilder:" in yaml_text
    assert "demo:" in yaml_text
    assert "enabled: false" in yaml_text


# ---------------------------------------------------------------------------
# Test: generated file header present in DemoController
# ---------------------------------------------------------------------------

def test_demo_controller_has_generated_header(tmp_path: Path) -> None:
    """DemoController.java starts with the standard EdgeForge generated-file comment.
    # all generated files must have a generation header.
    """
    metadata = _load_xyz_metadata()
    profile = _get_profile()
    demo_path = emit_demo_controller(
        metadata=metadata,
        target_profile=profile,
        output_dir=tmp_path,
        source_manifest="test-manifest",
        generation_run_id="header-test",
    )
    first_line = demo_path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("// Generated by EdgeForge")


# ---------------------------------------------------------------------------
# Test: top banner includes app name, bounded context, generation metadata
# ---------------------------------------------------------------------------

def test_ui_banner_contains_app_metadata(tmp_path: Path) -> None:
    """Generated index.html banner contains app name, bounded context, and run ID.
    # banner is the top strip of the operator dashboard.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIBannerTest", generation_run_id="banner-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert metadata.app_name in html
    assert metadata.bounded_context in html
    assert "banner-test" in html


def test_ui_identifies_itself_as_initial_test_console(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UITestConsoleCopy", generation_run_id="test-console-copy")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert "Initial Test Console" in html
    assert "Generated App Test Console" in html
    assert "This generated UI is intended for local validation of generated APIs, data, and batch outputs." in html
    assert "It is not a production application UI." in html


# ---------------------------------------------------------------------------
# Descriptor endpoints use snake_case for multi-word entities.
# ---------------------------------------------------------------------------

def test_ui_entity_routes_map_uses_snake_case_for_multi_word_entities(tmp_path: Path) -> None:
    """Action descriptors use to_snake_case(name)+'s', not name.toLowerCase()+'s'.
    # LoanApplication → /loan_applications, not /loanapplications.
    """
    loan_app = CanonicalEntity(
        name="LoanApplication",
        fields=[
            CanonicalField(name="loanApplicationId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=36),
            CanonicalField(name="amount", type=CanonicalFieldType.DECIMAL, required=True),
        ],
    )
    profile_name = "springboot-dashboard-test"
    metadata = MetadataProject(
        app_name="Loan App",
        bounded_context="loans",
        target_profile=profile_name,
        systems=[SystemParticipant(name="Loan", role="upstream")],
        contracts=[ContractMetadata(name="loan-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(name="createLoanApp", interface_name="loan-api", request_entity="LoanApplication", response_entity="LoanApplication"),
        ],
        entities=[loan_app],
        mappings=[
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="loan-api", operation_name="createLoanApp", source_path="loan-api.createLoanApp.response.loanApplicationId", target_path="LoanApplication.loanApplicationId"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="loan-api", operation_name="createLoanApp", source_path="loan-api.createLoanApp.request.amount", target_path="LoanApplication.amount"),
        ],
    )
    report = generate_application(metadata, tmp_path / "UISnakeCaseRouteTest", generation_run_id="snake-route-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    # Descriptor endpoint must preserve snake_case plural route generation.
    descriptor = _descriptor_by_key(html, "LoanApplication-create")
    assert descriptor["actions"][0]["endpoint"] == "/loan_applications"
    # The broken toLowerCase version must NOT be present
    assert "/loanapplications" not in html


def test_ui_entity_routes_follow_preserved_spec_route_base(tmp_path: Path) -> None:
    """Dashboard routes mirror preserved controller paths such as /pet, not /pets."""
    _get_profile()  # ensure springboot-dashboard-test is registered; test must be self-contained
    pet = CanonicalEntity(
        name="Pet",
        fields=[
            CanonicalField(name="petId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=36),
            CanonicalField(name="name", type=CanonicalFieldType.STRING, required=True, max_length=64),
        ],
    )
    metadata = MetadataProject(
        app_name="Pet Store",
        bounded_context="pets",
        target_profile="springboot-dashboard-test",
        systems=[SystemParticipant(name="Petstore", role="upstream")],
        contracts=[ContractMetadata(name="pet-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="addPet",
                interface_name="pet-api",
                request_entity="Pet",
                response_entity="Pet",
                http_method=HttpMethod.POST,
                path="/pet",
                response_shape=ResponseShape.CREATED,
            ),
            CanonicalOperation(
                name="getPetById",
                interface_name="pet-api",
                request_entity="Pet",
                response_entity="Pet",
                http_method=HttpMethod.GET,
                path="/pet/{petId}",
                path_parameters=[PathParameter(name="petId", type="String")],
                response_shape=ResponseShape.SINGLE,
            ),
        ],
        entities=[pet],
        mappings=[
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="pet-api", operation_name="addPet", source_path="pet-api.addPet.request.name", target_path="Pet.name"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="pet-api", operation_name="addPet", source_path="pet-api.addPet.response.petId", target_path="Pet.petId"),
        ],
    )

    report = generate_application(metadata, tmp_path / "UIPreservedPetRoute", generation_run_id="pet-route-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert _descriptor_by_key(html, "Pet-create")["actions"][0]["endpoint"] == "/pet"
    assert _descriptor_by_key(html, "Pet-get")["actions"][0]["endpoint"] == "/pet/{petId}"
    assert 'POST /pet &mdash; Create Pet' in html
    assert 'GET /pet/{petId} &mdash; Get Pet by ID' in html
    assert "/pets" not in html


def test_ui_read_configs_do_not_cross_wire_response_only_routes(tmp_path: Path) -> None:
    """CRUD dashboard reads stay aligned to generated controllers.

    A response-only OpenAPI read such as getAccount should not make the
    dashboard call an original spec path unless the controller also generated
    that path. This also guards against borrowing an AccountBalance route for
    Account just because the path parameter is accountId.
    """
    _get_profile()
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=36),
            CanonicalField(name="accountType", type=CanonicalFieldType.STRING, required=True, max_length=32),
        ],
    )
    metadata = MetadataProject(
        app_name="Acme Banking",
        bounded_context="banking",
        target_profile="springboot-dashboard-test",
        systems=[SystemParticipant(name="Acme", role="upstream")],
        contracts=[ContractMetadata(name="acme-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="createAccount",
                interface_name="acme-api",
                request_entity="Account",
                response_entity="Account",
                http_method=HttpMethod.POST,
                path="/corporate/v1/corporate-accounts",
                response_shape=ResponseShape.CREATED,
            ),
            CanonicalOperation(
                name="getAccount",
                interface_name="acme-api",
                request_entity="Account",
                response_entity="Account",
                http_method=HttpMethod.GET,
                path="/accounts/v1/accounts/{accountId}",
                path_parameters=[PathParameter(name="accountId", type="String")],
                response_shape=ResponseShape.SINGLE,
            ),
            CanonicalOperation(
                name="getAccountBalance",
                interface_name="acme-api",
                request_entity=None,
                response_entity="AccountBalance",
                http_method=HttpMethod.GET,
                path="/bank-statements/v1/account-balances/{accountId}",
                path_parameters=[PathParameter(name="accountId", type="String")],
                response_shape=ResponseShape.SINGLE,
            ),
        ],
        entities=[account],
        mappings=[
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="createAccount", source_path="acme-api.createAccount.request.accountType", target_path="Account.accountType"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="createAccount", source_path="acme-api.createAccount.response.accountId", target_path="Account.accountId"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="getAccount", source_path="acme-api.getAccount.response.accountId", target_path="Account.accountId"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="getAccount", source_path="acme-api.getAccount.response.accountType", target_path="Account.accountType"),
        ],
    )

    with pytest.raises(ValueError, match="getAccount.*cannot be emitted faithfully"):
        generate_application(metadata, tmp_path / "UIAcmeRouteDrift", generation_run_id="acme-route-test")
    assert not (tmp_path / "UIAcmeRouteDrift").exists()
    # Preserve response-only-route isolation on a compatible selected surface.
    metadata.operations[0].path = "/accounts/v1/accounts"
    report = generate_application(metadata, tmp_path / "UIAcmeRouteDrift", generation_run_id="acme-route-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert _descriptor_by_key(html, "Account-get")["actions"][0]["endpoint"] == "/accounts/v1/accounts/{accountId}"
    assert 'GET /accounts/v1/accounts/{accountId} &mdash; Get Account by ID' in html
    assert '"endpoint": "/accounts/v1/accounts/{accountId}"' in html
    assert "resolveEndpointTemplate" in html
    assert '"queryParameters": [],\n      "routeTemplate": "/bank-statements/v1/account-balances/{accountId}"' not in html
    assert 'GET /bank-statements/v1/account-balances/{accountId} &mdash; Get Account' not in html
    controller_source = (
        report.output_dir
        / "src/main/java/com/appbuilder/banking/adapter/inbound/AccountController.java"
    ).read_text(encoding="utf-8")
    assert '@RequestMapping("/accounts/v1/accounts")' in controller_source
    assert '@GetMapping("/{accountId}")' in controller_source


def test_ui_create_form_omits_response_only_status_but_includes_request_status(tmp_path: Path) -> None:
    _get_profile()
    entity = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=36),
            CanonicalField(name="productType", type=CanonicalFieldType.STRING, required=True, max_length=32),
            CanonicalField(
                name="status",
                type=CanonicalFieldType.STRING,
                required=True,
                allowed_values=["PENDING", "ACTIVE"],
            ),
        ],
    )
    base_metadata = MetadataProject(
        app_name="Acme Banking",
        bounded_context="banking",
        target_profile="springboot-dashboard-test",
        systems=[SystemParticipant(name="Acme", role="upstream")],
        contracts=[ContractMetadata(name="acme-api", type="rest-json", source="")],
        operations=[
            CanonicalOperation(
                name="createAccount",
                interface_name="acme-api",
                request_entity="Account",
                response_entity="Account",
            )
        ],
        entities=[entity],
        mappings=[
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="createAccount", source_path="acme-api.createAccount.request.productType", target_path="Account.productType"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="createAccount", source_path="acme-api.createAccount.response.accountId", target_path="Account.accountId"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="createAccount", source_path="acme-api.createAccount.response.status", target_path="Account.status"),
        ],
    )

    response_only_report = generate_application(
        base_metadata,
        tmp_path / "UIResponseOnlyStatus",
        generation_run_id="response-only-status-ui",
    )
    response_only_html = (
        response_only_report.output_dir / "src/main/resources/static/index.html"
    ).read_text(encoding="utf-8")

    assert '"contractName": "productType"' in response_only_html
    assert '"contractName": "status"' not in response_only_html

    request_status_metadata = base_metadata.model_copy(deep=True)
    request_status_metadata.mappings[-1].source_path = "acme-api.createAccount.request.status"
    request_status_report = generate_application(
        request_status_metadata,
        tmp_path / "UIRequestStatus",
        generation_run_id="request-status-ui",
    )
    request_status_html = (
        request_status_report.output_dir / "src/main/resources/static/index.html"
    ).read_text(encoding="utf-8")

    assert '"contractName": "status"' in request_status_html
    assert '"allowedValues": [\n          "PENDING",\n          "ACTIVE"\n        ]' in request_status_html


def test_ui_renders_eod_batch_test_actions_for_generated_jobs(tmp_path: Path) -> None:
    profile_name = "springboot-dashboard-batch-test"
    TARGET_PROFILES[profile_name] = TargetProfile(
        name=profile_name,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=True,
        emit_spring_batch=True,
        emit_security=False,
        emit_test_console=True,
        emit_audit=False,
        supports_xml=False,
    )
    customer = CanonicalEntity(
        name="Customer",
        fields=[
            CanonicalField(name="customerId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=36),
            CanonicalField(name="fullName", type=CanonicalFieldType.STRING, required=True, max_length=64),
        ],
    )
    account = CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True, max_length=36),
            CanonicalField(name="accountType", type=CanonicalFieldType.STRING, required=True, max_length=32),
        ],
    )
    metadata = MetadataProject(
        app_name="Acme Banking",
        bounded_context="acme-banking-save-load",
        target_profile=profile_name,
        systems=[SystemParticipant(name="Acme", role="upstream")],
        contracts=[
            ContractMetadata(name="customer-eod-file", type="file-fixed-width", source=""),
            ContractMetadata(name="account-eod-file", type="file-fixed-width", source=""),
            ContractMetadata(name="customer-staging", type="staging-table", source=""),
            ContractMetadata(name="account-staging", type="staging-table", source=""),
        ],
        operations=[
            CanonicalOperation(name="createCustomer", interface_name="acme-api", request_entity="Customer", response_entity="Customer"),
            CanonicalOperation(name="createAccount", interface_name="acme-api", request_entity="Account", response_entity="Account"),
        ],
        entities=[customer, account],
        mappings=[
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="createCustomer", source_path="acme-api.createCustomer.request.fullName", target_path="Customer.fullName"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="createCustomer", source_path="acme-api.createCustomer.response.customerId", target_path="Customer.customerId"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="createAccount", source_path="acme-api.createAccount.request.accountType", target_path="Account.accountType"),
            FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="acme-api", operation_name="createAccount", source_path="acme-api.createAccount.response.accountId", target_path="Account.accountId"),
            FieldMapping(direction=MappingDirection.CANONICAL_TO_HANDOFF, contract_name="customer-staging", operation_name="stageCustomer", source_path="Customer.customerId", target_path="customer_staging.customer_id"),
            FieldMapping(direction=MappingDirection.CANONICAL_TO_HANDOFF, contract_name="account-staging", operation_name="stageAccount", source_path="Account.accountId", target_path="account_staging.account_id"),
            FieldMapping(direction=MappingDirection.CANONICAL_TO_DOWNSTREAM, contract_name="customer-eod-file", operation_name="emitCustomerEod", source_path="Customer.customerId", target_path="customer-eod-file.customer_id"),
            FieldMapping(direction=MappingDirection.CANONICAL_TO_DOWNSTREAM, contract_name="account-eod-file", operation_name="emitAccountEod", source_path="Account.accountId", target_path="account-eod-file.account_id"),
        ],
    )

    report = generate_application(metadata, tmp_path / "UIBatchActions", generation_run_id="batch-ui-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert '<details class="group-section" data-group="BATCH">' in html
    assert "Local test tooling for generated batch jobs." in html
    assert "Generate Customer EOD File" in html
    assert "Generate Account EOD File" in html
    assert "customerEodJob" in html
    assert "accountEodJob" in html
    customer_descriptor = _descriptor_by_key(html, "batch-customerEodJob")
    account_descriptor = _descriptor_by_key(html, "batch-accountEodJob")
    assert customer_descriptor["actions"][0]["endpoint"] == "/batch/run/{jobName}"
    assert account_descriptor["actions"][0]["endpoint"] == "/batch/run/{jobName}"
    assert customer_descriptor["actions"][0]["inputBinding"] == "NONE"
    assert account_descriptor["actions"][0]["inputBinding"] == "NONE"
    assert "submitAction" in html
    customer_panel = _entity_panel_fragment(html, "Customer")
    assert customer_panel.index("DELETE /customers/{id}") < customer_panel.index('data-group="BATCH"') < customer_panel.index("Live Data &mdash; Customer")
    account_panel = _entity_panel_fragment(html, "Account")
    customer_batch = _group_section_fragment(customer_panel, "BATCH")
    account_batch = _group_section_fragment(account_panel, "BATCH")
    assert 'data-coverage-key="batch-customerEodJob"' in customer_batch
    assert 'data-coverage-key="batch-accountEodJob"' not in customer_batch
    assert 'data-coverage-key="batch-accountEodJob"' in account_batch
    assert 'data-coverage-key="batch-customerEodJob"' not in account_batch
    rendered_batch_keys = set(
        re.findall(r'data-coverage-key="(batch-[^"]+)"', customer_batch + account_batch)
    )
    descriptor_batch_keys = {
        descriptor["coverageKey"]
        for descriptor in _extract_descriptors(html)
        if descriptor["family"] == "batch"
    }
    assert rendered_batch_keys == descriptor_batch_keys
    assert "./acme-banking-save-load-eod/customer-eod-YYYYMMDD.dat" in html
    assert "./acme-banking-save-load-eod/account-eod-YYYYMMDD.dat" in html
    assert "jobId" in html
    assert "exitCode" in html
    assert "startTime" in html
    assert "Job not found" in (
        report.output_dir
        / "src/main/java/com/appbuilder/acme_banking_save_load/adapter/inbound/BatchTriggerController.java"
    ).read_text(encoding="utf-8")


def test_ui_omits_batch_test_actions_when_no_jobs_exist(tmp_path: Path) -> None:
    metadata = _two_entity_metadata()
    report = generate_application(metadata, tmp_path / "UINoBatchActions", generation_run_id="no-batch-ui-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    assert 'data-group="BATCH"' not in html
    assert "POST /batch/run/" not in html
    assert "Run Batch Action" not in html
    assert all(descriptor["family"] != "batch" for descriptor in _extract_descriptors(html))


# ---------------------------------------------------------------------------
# polling stops after first 403
# ---------------------------------------------------------------------------

def test_ui_live_viewer_stops_polling_on_403(tmp_path: Path) -> None:
    """Generated JS cancels the setInterval timer when loadLiveData receives a 403.
    # without clearInterval the browser keeps hammering
    # the disabled endpoint every 5 s — wasted traffic and noisy logs.
    """
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "UIStopPollTest", generation_run_id="stoppoll-test")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")

    # clearInterval must be called inside the 403 branch
    assert "clearInterval(liveTimers[entityName])" in html
    # After clearing, the slot must be nulled out to allow future restarts
    assert "liveTimers[entityName] = null" in html


def test_action_descriptors_carry_input_binding_by_family(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "DescriptorBindings",
        source_manifest="descriptor-bindings",
        generation_run_id="descriptor-bindings",
    )
    html = html_path.read_text(encoding="utf-8")
    descriptors = {
        descriptor["coverageKey"]: descriptor
        for descriptor in _extract_descriptors(html)
    }

    assert descriptors["Account-create"]["family"] == "rest-crud"
    assert descriptors["Account-create"]["actions"][0] == {
        "verb": "POST",
        "endpoint": "/accounts",
        "inputControl": "FORM",
        "inputBinding": "JSON_BODY",
    }
    assert descriptors["Account-get"]["actions"][0]["inputBinding"] == "PATH_PARAM"
    assert descriptors["Account-list"]["actions"][0]["inputBinding"] == "NONE"
    assert descriptors["Account-update"]["actions"][0]["inputBinding"] == "JSON_BODY"
    assert descriptors["Account-delete"]["actions"][0]["inputBinding"] == "PATH_PARAM"
    assert descriptors["file-Account-account-csv-in"]["actions"][0] == {
        "verb": "POST",
        "endpoint": "/files/ingest/{contractName}",
        "inputControl": "PATH",
        "inputBinding": "JSON_BODY",
    }
    assert descriptors["xml-Account-ingest-account-xml-in"]["actions"][0] == {
        "verb": "POST",
        "endpoint": "/xml/ingest/{contractName}",
        "inputControl": "PATH",
        "inputBinding": "JSON_BODY",
    }
    assert descriptors["xml-Account-output-account-xml-out"]["actions"][0] == {
        "verb": "POST",
        "endpoint": "/xml/output/{contractName}",
        "inputControl": "NONE",
        "inputBinding": "NONE",
    }
    assert descriptors["batch-accountEodJob"]["actions"][0] == {
        "verb": "POST",
        "endpoint": "/batch/run/{jobName}",
        "inputControl": "NONE",
        "inputBinding": "NONE",
    }
    assert "owner_entity" not in descriptors["batch-accountEodJob"]
    assert "ownerEntity" not in descriptors["batch-accountEodJob"]


def test_action_cards_group_within_entity_panel_in_fixed_order(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "DescriptorGroups",
        source_manifest="descriptor-groups",
        generation_run_id="descriptor-groups",
    )
    html = html_path.read_text(encoding="utf-8")
    panel = _entity_panel_fragment(html, "Account")

    assert '<details class="group-section" data-group="UPSTREAM" open>' in panel
    assert '<details class="group-section" data-group="DOWNSTREAM">' in panel
    assert '<details class="group-section" data-group="BATCH">' in panel
    assert 'data-group="HANDOFF"' not in panel
    assert panel.index('data-group="UPSTREAM"') < panel.index('data-group="DOWNSTREAM"') < panel.index('data-group="BATCH"') < panel.index("Live Data &mdash; Account")
    assert '<span class="group-title">Upstream</span><span class="group-count">(7)</span>' in panel
    assert '<span class="group-title">Downstream</span><span class="group-count">(1)</span>' in panel
    assert '<span class="group-title">Batch</span><span class="group-count">(1)</span>' in panel
    assert 'class="group-icon" aria-hidden="true"' in panel


def test_action_cards_land_in_section_from_descriptor_group(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "DescriptorGroupPlacement",
        source_manifest="descriptor-placement",
        generation_run_id="descriptor-placement",
    )
    html = html_path.read_text(encoding="utf-8")
    panel = _entity_panel_fragment(html, "Account")
    upstream = _group_section_fragment(panel, "UPSTREAM")
    downstream = _group_section_fragment(panel, "DOWNSTREAM")
    batch = _group_section_fragment(panel, "BATCH")

    assert 'data-coverage-key="Account-create"' in upstream
    assert 'data-coverage-key="file-Account-account-csv-in"' in upstream
    assert 'data-coverage-key="xml-Account-ingest-account-xml-in"' in upstream
    assert 'data-coverage-key="xml-Account-output-account-xml-out"' not in upstream
    assert 'data-coverage-key="xml-Account-output-account-xml-out"' in downstream
    assert 'data-coverage-key="batch-accountEodJob"' in batch


def test_action_groups_omit_empty_sections_for_crud_only_entity(tmp_path: Path) -> None:
    metadata = _two_entity_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "DescriptorEmptyGroups",
        source_manifest="empty-groups",
        generation_run_id="empty-groups",
    )
    html = html_path.read_text(encoding="utf-8")
    panel = _entity_panel_fragment(html, "Customer")

    assert '<details class="group-section" data-group="UPSTREAM" open>' in panel
    assert '<span class="group-title">Upstream</span><span class="group-count">(5)</span>' in panel
    assert 'data-group="DOWNSTREAM"' not in panel
    assert 'data-group="HANDOFF"' not in panel
    assert 'data-group="BATCH"' not in panel


def test_crud_tabs_survive_inside_upstream_group(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "DescriptorCrudTabs",
        source_manifest="crud-tabs",
        generation_run_id="crud-tabs",
    )
    html = html_path.read_text(encoding="utf-8")
    panel = _entity_panel_fragment(html, "Account")
    upstream = _group_section_fragment(panel, "UPSTREAM")

    assert '<div class="crud-tabs" role="tablist" aria-label="Account actions">' in upstream
    assert 'id="crud-tab-Account-create"' in upstream
    assert 'aria-controls="crud-Account-create"' in upstream
    assert 'onclick="showCrudTab(\'Account\', \'create\')"' in upstream
    assert 'id="crud-Account-create"' in upstream
    assert 'role="tabpanel" aria-labelledby="crud-tab-Account-create"' in upstream


def test_dashboard_uses_single_generic_submit_path(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "GenericSubmit",
        source_manifest="generic-submit",
        generation_run_id="generic-submit",
    )
    html = html_path.read_text(encoding="utf-8")

    assert "const DESCRIPTORS = [" in html
    assert "function submitAction(" in html
    assert "function resolveEndpointTemplate(" in html
    assert "action.inputBinding === 'JSON_BODY'" in html
    assert "function renderResponse(entityName" not in html
    assert "execCreate" not in html
    assert "execGetById" not in html
    assert "execList" not in html
    assert "execUpdate" not in html
    assert "execDelete" not in html
    assert "runBatchAction" not in html
    assert "runFileIngest" not in html
    assert "runXmlIngest" not in html
    assert "runXmlOutput" not in html
    assert "FORM_CONFIGS" not in html
    assert "READ_CONFIGS" not in html
    assert "BATCH_ACTIONS" not in html
    assert "family ===" not in html
    assert "=== 'soap" not in html
    assert '=== "soap' not in html


def test_contract_coverage_map_lists_every_descriptor(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "CoverageMap",
        source_manifest="coverage-map",
        generation_run_id="coverage-map",
    )
    html = html_path.read_text(encoding="utf-8")
    descriptors = _extract_descriptors(html)
    coverage_map = _coverage_map_fragment(html)

    assert html.index('<section class="coverage-map"') < html.index('<div id="entity-panel-Account"')
    assert len(re.findall(r'data-coverage-entry="[^"]+"', coverage_map)) == len(descriptors)
    families = {descriptor["family"] for descriptor in descriptors}
    assert {"rest-crud", "file", "xml", "batch"} <= families
    for descriptor in descriptors:
        coverage_key = descriptor["coverageKey"]
        assert f'data-coverage-entry="{coverage_key}"' in coverage_map
        assert f'id="coverage-chip-{_safe_test_dom_id(coverage_key)}"' in coverage_map
        assert descriptor["title"] in coverage_map
        assert descriptor["family"] in coverage_map
        assert descriptor["group"] in coverage_map
    assert coverage_map.count("not yet tried") == len(descriptors)

    for fixture, expected_family in [
        (SOAP_INBOUND_FIXTURE, "soap-inbound"),
        (SOAP_OUTBOUND_FIXTURE, "soap-outbound"),
    ]:
        soap_metadata = build_metadata_project(fixture)
        soap_html_path = generate_demo_ui(
            soap_metadata,
            tmp_path / f"CoverageMap-{expected_family}",
            source_manifest=f"coverage-map-{expected_family}",
            generation_run_id=f"coverage-map-{expected_family}",
        )
        soap_html = soap_html_path.read_text(encoding="utf-8")
        soap_descriptors = _extract_descriptors(soap_html)
        soap_coverage_map = _coverage_map_fragment(soap_html)
        assert any(descriptor["family"] == expected_family for descriptor in soap_descriptors)
        for descriptor in soap_descriptors:
            if descriptor["family"] == expected_family:
                assert f'data-coverage-entry="{descriptor["coverageKey"]}"' in soap_coverage_map


def test_coverage_tracking_hook_updates_local_storage_and_chip(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "CoverageTracking",
        source_manifest="coverage-tracking",
        generation_run_id="coverage-tracking",
    )
    html = html_path.read_text(encoding="utf-8")
    js = _extract_js_block(html, "    function safeDomId", "    // ---- Value coercion ----")

    assert "recordCoverageResult(coverageKey, resp.status" in html
    assert "recordCoverageResult(coverageKey, 400, '400')" in html
    assert "recordCoverageResult(coverageKey, 0, 'NETWORK_ERROR')" in html
    assert "localStorage.setItem(COVERAGE_STORAGE_KEY" in html

    script = f"""
const DESCRIPTORS = {json.dumps(_extract_descriptors(html))};
const COVERAGE_STORAGE_KEY = 'edgeforge.testConsole.coverage.test';
const chips = {{}};
const store = {{}};
const localStorage = {{
  getItem(key) {{ return store[key] || null; }},
  setItem(key, value) {{ store[key] = value; }}
}};
const document = {{
  getElementById(id) {{
    if (!chips[id]) chips[id] = {{ className: '', textContent: '', dataset: {{}} }};
    return chips[id];
  }},
  querySelectorAll() {{ return []; }}
}};
{js}
refreshCoverageMap();
const chipId = 'coverage-chip-Account-create';
if (chips[chipId].textContent !== 'not yet tried') {{
  throw new Error('expected default not-yet-tried chip');
}}
recordCoverageResult('Account-create', 201, '201 Created');
const stored = JSON.parse(store[COVERAGE_STORAGE_KEY]);
if (!stored['Account-create'].exercised || stored['Account-create'].numericStatus !== 201) {{
  throw new Error('coverage state was not persisted');
}}
if (chips[chipId].textContent !== '201 Created' || !chips[chipId].className.includes(' ok')) {{
  throw new Error('coverage chip did not render success status');
}}
recordCoverageResult('Account-create', 0, 'NETWORK_ERROR');
if (chips[chipId].textContent !== 'NETWORK_ERROR' || !chips[chipId].className.includes(' err')) {{
  throw new Error('coverage chip did not render network errors as errors');
}}
"""
    _run_node_script(script, tmp_path)


def test_coverage_entry_click_reveals_entity_group_and_crud_tab(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "CoverageFocus",
        source_manifest="coverage-focus",
        generation_run_id="coverage-focus",
    )
    html = html_path.read_text(encoding="utf-8")
    js = _extract_js_block(html, "    function focusCoverageCard", "    // ---- Value coercion ----")

    script = f"""
const calls = [];
const ownerPanel = {{ id: 'entity-panel-Account' }};
const crudPanel = {{ id: 'crud-Account-update' }};
const groupSection = {{ open: false }};
const button = {{ focus(options) {{ calls.push(['focus', options.preventScroll]); }} }};
const card = {{
  dataset: {{ coverageKey: 'Account-update' }},
  closest(selector) {{
    if (selector === '.entity-panel') return ownerPanel;
    if (selector === '.crud-panel') return crudPanel;
    if (selector === 'details.group-section') return groupSection;
    return null;
  }},
  querySelector(selector) {{ return selector === '[data-action-button]' ? button : null; }},
  scrollIntoView(options) {{ calls.push(['scroll', options.block]); }}
}};
const document = {{
  querySelectorAll(selector) {{ return selector === '[data-coverage-key]' ? [card] : []; }}
}};
function showEntity(entityName) {{ calls.push(['entity', entityName]); }}
function showCrudTab(entityName, tabName) {{ calls.push(['tab', entityName, tabName]); }}
{js}
focusCoverageCard('Account-update');
if (!groupSection.open) throw new Error('expected collapsed group section to open');
if (JSON.stringify(calls) !== JSON.stringify([
  ['entity', 'Account'],
  ['tab', 'Account', 'update'],
  ['scroll', 'center'],
  ['focus', true]
])) {{
  throw new Error('unexpected focus/navigation calls: ' + JSON.stringify(calls));
}}
"""
    _run_node_script(script, tmp_path)


def test_action_cards_render_provenance_panel_from_descriptor(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "ProvenancePanels",
        source_manifest="provenance-panels",
        generation_run_id="provenance-panels",
    )
    html = html_path.read_text(encoding="utf-8")
    descriptors = _extract_descriptors(html)

    assert len(re.findall(r'<details\s+class="provenance-panel"', html)) == len(descriptors)
    assert 'data-provenance-contract="account-api"' in html
    assert 'data-provenance-direction="UPSTREAM"' in html
    assert 'data-provenance-source="upstream/account-openapi.yaml"' in html
    assert 'data-provenance-mapping="upstream/account-mapping.yaml"' in html
    assert "preserves account-api from upstream/account-openapi.yaml" in html
    assert 'data-provenance-contract="generated-crud"' in html
    assert "generated CRUD operation — no source contract" in html


def test_scalar_inputs_render_visible_contract_rule_summaries(tmp_path: Path) -> None:
    metadata = _sample_hint_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "RuleSummaries",
        source_manifest="rule-summaries",
        generation_run_id="rule-summaries",
    )
    html = html_path.read_text(encoding="utf-8")

    assert "Rules: required · text · max length 50 · pattern ^C[0-9]+$" in html
    assert "Rules: required · decimal · 0–999999" in html
    assert "Rules: optional · date" in html
    assert "Rules: required · boolean" in html
    assert "Rules: required · enum · allowed NEW, ACTIVE" in html
    assert "Rules: optional · enum · allowed RETAIL, VIP" in html
    assert 'maxlength="50"' in html
    assert 'pattern="^C[0-9]+$"' in html
    assert 'min="0"' in html
    assert 'max="999999"' in html


def test_fill_sample_buttons_render_only_for_scalar_hint_cards(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "FillSampleButtons",
        source_manifest="fill-sample-buttons",
        generation_run_id="fill-sample-buttons",
    )
    html = html_path.read_text(encoding="utf-8")

    assert 'data-fill-sample="Account-create"' in html
    assert "Fill typed-empty sample values; edit before sending." in html
    assert 'data-fill-sample="Account-get"' not in html
    assert 'data-fill-sample="Account-update"' not in html
    assert 'data-fill-sample="Account-delete"' not in html
    assert 'data-fill-sample="file-Account-account-csv-in"' in html
    assert 'data-fill-sample="xml-Account-ingest-account-xml-in"' in html
    assert 'data-fill-sample="xml-Account-output-account-xml-out"' not in html
    assert 'data-fill-sample="batch-accountEodJob"' not in html

    soap_html_path = generate_demo_ui(
        build_metadata_project(SOAP_INBOUND_FIXTURE),
        tmp_path / "FillSampleSoapInbound",
        source_manifest="fill-sample-soap-inbound",
        generation_run_id="fill-sample-soap-inbound",
    )
    soap_html = soap_html_path.read_text(encoding="utf-8")
    assert 'data-fill-sample="soap-inbound-Customer-customer-soap-service-getCustomer"' not in soap_html

    soap_outbound_html_path = generate_demo_ui(
        build_metadata_project(SOAP_OUTBOUND_FIXTURE),
        tmp_path / "FillSampleSoapOutbound",
        source_manifest="fill-sample-soap-outbound",
        generation_run_id="fill-sample-soap-outbound",
    )
    soap_outbound_html = soap_outbound_html_path.read_text(encoding="utf-8")
    assert 'data-fill-sample="Customer-create"' in soap_outbound_html
    assert 'data-fill-sample="Customer-get"' not in soap_outbound_html
    assert 'data-fill-sample="Customer-update"' not in soap_outbound_html
    assert 'data-fill-sample="Customer-delete"' not in soap_outbound_html
    assert 'data-fill-sample="soap-outbound-Customer-customer-sync-client-syncCustomer"' in soap_outbound_html


def test_fill_sample_uses_typed_empty_values_without_business_inference(tmp_path: Path) -> None:
    metadata = _sample_hint_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "FillSampleTypedEmpty",
        source_manifest="fill-sample-typed-empty",
        generation_run_id="fill-sample-typed-empty",
    )
    html = html_path.read_text(encoding="utf-8")
    descriptor = _descriptor_by_key(html, "Customer-create")
    js = _extract_js_block(html, "    function isFillableSampleHint", "    function collectActionInputs")
    assert "Date.now" not in js
    assert "new Date" not in js
    assert "Math.random" not in js

    script = f"""
const descriptor = {json.dumps(descriptor)};
const DESCRIPTOR_BY_KEY = {{ 'Customer-create': descriptor }};
const calls = [];
const elements = {{}};
for (const hint of descriptor.hints) {{
  elements[hint.id] = {{
    value: 'UNCHANGED',
    checked: true
  }};
}}
const document = {{
  getElementById(id) {{ return elements[id] || null; }}
}};
function descriptorEntityName() {{ return 'Customer'; }}
function updateRequestPreview(entityName, tabName) {{ calls.push([entityName, tabName]); }}
{js}
fillSample('Customer-create');
function valueFor(contractName) {{
  const hint = descriptor.hints.find(item => item.contractName === contractName);
  return elements[hint.id].value;
}}
function checkedFor(contractName) {{
  const hint = descriptor.hints.find(item => item.contractName === contractName);
  return elements[hint.id].checked;
}}
if (valueFor('customerName') !== '') throw new Error('text fields must remain empty typed skeletons');
if (valueFor('creditLimit') !== '0.00') throw new Error('decimal fields must use 0.00');
if (valueFor('openedOn') !== '2000-01-01') throw new Error('date fields must use a fixed placeholder');
if (checkedFor('active') !== false) throw new Error('boolean fields must be unchecked');
if (valueFor('status') !== 'NEW') throw new Error('required enum fields must use the first declared value');
if (valueFor('segment') !== '') throw new Error('optional enum fields must stay empty');
if (JSON.stringify(calls) !== JSON.stringify([['Customer', 'create']])) {{
  throw new Error('request preview was not refreshed');
}}
"""
    _run_node_script(script, tmp_path)


def test_fill_sample_does_not_autofill_soap_raw_body_or_update_json_body(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(
        metadata,
        tmp_path / "FillSampleUpdateBody",
        generation_run_id="fill-sample-update-body",
    )
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")
    descriptor = _descriptor_by_key(html, "Account-update")
    js = _extract_js_block(html, "    function isFillableSampleHint", "    function collectActionInputs")

    script = f"""
const descriptor = {json.dumps(descriptor)};
const DESCRIPTOR_BY_KEY = {{ 'Account-update': descriptor }};
const elements = {{}};
for (const hint of descriptor.hints) {{
  elements[hint.id] = {{
    value: hint.bodyField ? '{{"existing":true}}' : 'old-id',
    checked: true
  }};
}}
const document = {{
  getElementById(id) {{ return elements[id] || null; }}
}};
function descriptorEntityName() {{ return 'Account'; }}
function updateRequestPreview() {{}}
{js}
fillSample('Account-update');
const idHint = descriptor.hints.find(item => item.contractName === 'id');
const bodyHint = descriptor.hints.find(item => item.bodyField);
if (elements[idHint.id].value !== '') throw new Error('update id should use text typed-empty');
if (elements[bodyHint.id].value !== '{{"existing":true}}') {{
  throw new Error('freeform update JSON body must not be sample-filled');
}}
"""
    _run_node_script(script, tmp_path)

    soap_html_path = generate_demo_ui(
        build_metadata_project(SOAP_INBOUND_FIXTURE),
        tmp_path / "FillSampleSoapRawBody",
        source_manifest="fill-sample-soap-raw-body",
        generation_run_id="fill-sample-soap-raw-body",
    )
    soap_html = soap_html_path.read_text(encoding="utf-8")
    assert 'data-fill-sample="soap-inbound-Customer-customer-soap-service-getCustomer"' not in soap_html
    assert "Paste SOAP envelope here" in soap_html
    assert "<soapenv:" not in soap_html


def test_generic_submit_resolves_put_id_and_json_body_descriptor(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    report = generate_application(metadata, tmp_path / "DescriptorPut", generation_run_id="descriptor-put")
    html = (report.output_dir / "src/main/resources/static/index.html").read_text(encoding="utf-8")
    descriptor = _descriptor_by_key(html, "Account-update")

    action = descriptor["actions"][0]
    assert action["verb"] == "PUT"
    assert action["endpoint"] == "/accounts/{id}"
    assert action["inputControl"] == "FORM"
    assert action["inputBinding"] == "JSON_BODY"
    assert any(hint.get("contractName") == "id" for hint in descriptor["hints"])
    assert any(hint.get("bodyField") for hint in descriptor["hints"])
    assert "resolveEndpointTemplate(action.endpoint, inputState.values)" in html
    assert "const endpointPlaceholderNames = new Set(endpointPlaceholders(action.endpoint));" in html
    assert "action.inputControl === 'FORM' && !isEndpointPlaceholder" in html
    assert "if (action.inputBinding === 'JSON_BODY')" in html


def test_inbound_soap_canonical_card_renders_in_upstream_group(tmp_path: Path) -> None:
    metadata = build_metadata_project(SOAP_INBOUND_FIXTURE)
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "SoapInboundDashboard",
        source_manifest="soap-inbound",
        generation_run_id="soap-inbound",
    )
    html = html_path.read_text(encoding="utf-8")
    descriptor = _descriptor_by_key(
        html,
        "soap-inbound-Customer-customer-soap-service-getCustomer",
    )

    assert descriptor["family"] == "soap-inbound"
    assert descriptor["group"] == "UPSTREAM"
    assert descriptor["responseShape"] == "SOAP"
    assert descriptor["actions"][0] == {
        "verb": "POST",
        "endpoint": "/ws",
        "inputControl": "TEXTAREA",
        "inputBinding": "RAW_BODY",
        "headers": {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "urn:getCustomer",
        },
    }
    hint = descriptor["hints"][0]
    assert hint["inputType"] == "textarea"
    assert hint["defaultValue"] == ""
    assert "tns:GetCustomerRequest" in hint["helpText"]
    assert "/ws/customer-soap-service.wsdl" in hint["helpText"]
    assert "SOAPAction: urn:getCustomer" in hint["helpText"]

    panel = _entity_panel_fragment(html, "Customer")
    upstream = _group_section_fragment(panel, "UPSTREAM")
    assert 'data-coverage-key="soap-inbound-Customer-customer-soap-service-getCustomer"' in upstream
    assert 'data-group="DOWNSTREAM"' not in panel
    assert "Paste SOAP envelope here" in upstream
    assert "<soapenv:" not in upstream


def test_outbound_soap_canonical_card_renders_in_downstream_group(tmp_path: Path) -> None:
    metadata = build_metadata_project(SOAP_OUTBOUND_FIXTURE)
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "SoapOutboundDashboard",
        source_manifest="soap-outbound",
        generation_run_id="soap-outbound",
    )
    html = html_path.read_text(encoding="utf-8")
    descriptor = _descriptor_by_key(
        html,
        "soap-outbound-Customer-customer-sync-client-syncCustomer",
    )

    assert descriptor["family"] == "soap-outbound"
    assert descriptor["group"] == "DOWNSTREAM"
    assert descriptor["responseShape"] == "JSON"
    assert descriptor["actions"][0] == {
        "verb": "POST",
        "endpoint": "/soap/outbound/customer-sync-client/syncCustomer",
        "inputControl": "ID",
        "inputBinding": "JSON_BODY",
    }
    hint = descriptor["hints"][0]
    assert hint["contractName"] == "id"
    assert hint["canonicalName"] == "id"
    assert "Customer.customerId" in hint["helpText"]

    panel = _entity_panel_fragment(html, "Customer")
    upstream = _group_section_fragment(panel, "UPSTREAM")
    downstream = _group_section_fragment(panel, "DOWNSTREAM")
    assert 'data-coverage-key="soap-outbound-Customer-customer-sync-client-syncCustomer"' not in upstream
    assert 'data-coverage-key="soap-outbound-Customer-customer-sync-client-syncCustomer"' in downstream


def test_soap_id_json_body_uses_generic_submit_body_shape(tmp_path: Path) -> None:
    metadata = build_metadata_project(SOAP_OUTBOUND_FIXTURE)
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "SoapOutboundJsonBody",
        source_manifest="soap-json-body",
        generation_run_id="soap-json-body",
    )
    html = html_path.read_text(encoding="utf-8")
    descriptor = _descriptor_by_key(
        html,
        "soap-outbound-Customer-customer-sync-client-syncCustomer",
    )
    js = _extract_js_block(html, "    function coerceValue", "    function actionButtonId")
    script = f"""
const descriptor = {json.dumps(descriptor)};
const action = descriptor.actions[0];
global.document = {{
  getElementById(id) {{
    return {{ value: id === descriptor.hints[0].id ? 'CUST-123' : '', checked: false }};
  }}
}};
{js}
const inputState = collectActionInputs(descriptor, action, false);
if (inputState.errors.length) throw new Error(inputState.errors.join(', '));
const request = buildActionRequest(descriptor, action, inputState, false);
if (request.endpoint !== '/soap/outbound/customer-sync-client/syncCustomer') {{
  throw new Error('unexpected endpoint: ' + request.endpoint);
}}
console.log(request.fetchOptions.body);
"""
    assert _run_node_script(script, tmp_path).strip() == '{"id":"CUST-123"}'
    assert "fd.contractName === 'path'" not in html
    assert "action.inputBinding === 'JSON_BODY' && !isEndpointPlaceholder" in html


def test_non_soap_dashboard_omits_soap_cards(tmp_path: Path) -> None:
    metadata = _descriptor_family_metadata()
    html_path = generate_demo_ui(
        metadata,
        tmp_path / "NoSoapDashboard",
        source_manifest="no-soap",
        generation_run_id="no-soap",
    )
    html = html_path.read_text(encoding="utf-8")
    descriptors = _extract_descriptors(html)

    assert all(not descriptor["family"].startswith("soap-") for descriptor in descriptors)
    assert "soap-inbound-" not in html
    assert "soap-outbound-" not in html
    assert "family ===" not in html
    assert "=== 'soap" not in html
    assert '=== "soap' not in html
