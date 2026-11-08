"""
Proof tests for outbound SOAP canonical invoke_by_id contracts.

Coverage structure
------------------
Section A — WSDL fixture integrity
    Verify the syncCustomer WSDL parses correctly and exposes the expected
    operation structure.  These pass now and must stay green forever.

Section B — Translation-layer canonical mapping support
    Verify that mode: canonical on a downstream SOAP interface is accepted for
    the designed invoke_by_id MVP shape, and that structural mapping errors
    still fail clearly.

Section C — Adapter-only regression guards
    Verify that the existing adapter-only outbound SOAP client scaffold
    continues to generate correctly alongside Slice 1-5 work.
    These pass now and must stay green forever.

Section D — Canonical invoke_by_id negative translation tests
    Structural rejection tests for unsupported or unsafe downstream canonical
    metadata. These pass now and should stay green as runtime slices land.

Section E — Generation-output expectations (Slices 2-4)
    Slice 2 controller skeleton assertions are active. Later request-rendering,
    response-mapping, and runtime diagnostics stubs remain skipped.

Section F — Stub: runtime proof expectations (Slice 5)
    @pytest.mark.skip stubs documenting the generate→build→mock-SOAP→smoke
    proof sequence the build/proof threads must execute.

Fixture location
----------------
tests/fixtures/edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/

Design reference
----------------
docs/edgecontracts/outbound-soap-canonical-invocation-mvp-design.md  (PR #192)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from appbuilder.contracts.soap_contracts import load_soap_contract_spec
from appbuilder.metadata.translation import build_metadata_project

FIXTURE = Path(
    "tests/fixtures/edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client"
)
WSDL = FIXTURE / "contracts/customer-sync-service.wsdl"
CANONICAL_MANIFEST = FIXTURE / "app-definition.yaml"
ADAPTER_MANIFEST = FIXTURE / "app-definition-adapter-only.yaml"
CANONICAL_MAPPING = FIXTURE / "mappings/customer-soap-outbound-canonical-mapping.yaml"
ADAPTER_MAPPING = FIXTURE / "mappings/customer-soap-outbound-adapter-mapping.yaml"


# ---------------------------------------------------------------------------
# Section A — WSDL fixture integrity
# ---------------------------------------------------------------------------


def test_outbound_sync_wsdl_parses_as_document_literal_wrapped() -> None:
    """The syncCustomer WSDL is a valid document/literal-wrapped contract."""
    spec = load_soap_contract_spec(
        WSDL,
        interface_name="customer-sync-client",
        service="CustomerSyncService",
        port="CustomerSyncServicePort",
        package_root=FIXTURE,
    )

    assert spec.wsdl_path == str(WSDL)
    assert spec.target_namespace == "urn:edgeforge:examples:customer-sync:v1"
    assert spec.service == "CustomerSyncService"
    assert spec.port == "CustomerSyncServicePort"
    assert spec.binding == "CustomerSyncSoapBinding"
    assert len(spec.operations) == 1


def test_outbound_sync_wsdl_operation_name_and_soap_action() -> None:
    """The single operation is syncCustomer with its urn: SOAPAction."""
    spec = load_soap_contract_spec(
        WSDL,
        interface_name="customer-sync-client",
        package_root=FIXTURE,
    )

    op = spec.operations[0]
    assert op.name == "syncCustomer"
    assert op.soap_action == "urn:syncCustomer"
    assert op.input_message == "SyncCustomerRequestMessage"
    assert op.output_message == "SyncCustomerResponseMessage"
    assert op.input_element == "tns:SyncCustomerRequest"
    assert op.output_element == "tns:SyncCustomerResponse"
    assert op.faults == ()


def test_outbound_sync_wsdl_request_fields() -> None:
    """SyncCustomerRequest has customerId and status as required xs:string fields."""
    spec = load_soap_contract_spec(
        WSDL,
        interface_name="customer-sync-client",
        package_root=FIXTURE,
    )

    op = spec.operations[0]
    input_by_path = {f.path: f for f in op.input_fields}

    assert "/SyncCustomerRequest/customerId" in input_by_path
    assert "/SyncCustomerRequest/status" in input_by_path

    customer_id_field = input_by_path["/SyncCustomerRequest/customerId"]
    status_field = input_by_path["/SyncCustomerRequest/status"]

    assert customer_id_field.type == "string"
    assert customer_id_field.required is True
    assert customer_id_field.repeated is False

    assert status_field.type == "string"
    assert status_field.required is True
    assert status_field.repeated is False


def test_outbound_sync_wsdl_response_fields() -> None:
    """SyncCustomerResponse has resultCode (required) and message (optional)."""
    spec = load_soap_contract_spec(
        WSDL,
        interface_name="customer-sync-client",
        package_root=FIXTURE,
    )

    op = spec.operations[0]
    output_by_path = {f.path: f for f in op.output_fields}

    assert "/SyncCustomerResponse/resultCode" in output_by_path
    assert "/SyncCustomerResponse/message" in output_by_path

    result_code_field = output_by_path["/SyncCustomerResponse/resultCode"]
    message_field = output_by_path["/SyncCustomerResponse/message"]

    assert result_code_field.type == "string"
    assert result_code_field.required is True

    assert message_field.type == "string"
    assert message_field.required is False  # minOccurs="0"


def test_outbound_sync_wsdl_no_faults_in_mvp_operation() -> None:
    """The syncCustomer operation declares no WSDL faults in the MVP WSDL.

    The design defers fault classification to Slice 4 runtime diagnostics;
    the MVP fixture intentionally omits WSDL fault declarations so the parser
    is not constrained by a specific fault element shape before the design
    is finalised.
    """
    spec = load_soap_contract_spec(
        WSDL,
        interface_name="customer-sync-client",
        package_root=FIXTURE,
    )
    assert spec.operations[0].faults == ()


def test_outbound_sync_wsdl_source_paths_within_package_boundary() -> None:
    """WSDL source paths are relative to the fixture package root (no embedded XSD)."""
    spec = load_soap_contract_spec(
        WSDL,
        interface_name="customer-sync-client",
        source_wsdl_path="contracts/customer-sync-service.wsdl",
        package_root=FIXTURE,
    )

    assert spec.wsdl_paths == ("contracts/customer-sync-service.wsdl",)


# ---------------------------------------------------------------------------
# Section B — Translation-layer fail-fast (currently enforced)
# ---------------------------------------------------------------------------


def test_b1_canonical_mode_on_downstream_soap_translates_to_metadata() -> None:
    """[B-1] mode: canonical + invoke_by_id on downstream SOAP translates."""
    metadata = build_metadata_project(CANONICAL_MANIFEST)

    contract = next(
        (c for c in metadata.contracts if c.name == "customer-sync-client"),
        None,
    )
    assert contract is not None, "customer-sync-client contract not found in metadata"
    assert contract.type == "soap-wsdl"
    assert contract.soap_contract is not None
    assert contract.soap_contract["direction"] == "downstream"

    op_mapping = contract.soap_contract["operation_mappings"]["syncCustomer"]
    assert op_mapping["mode"] == "canonical"
    canonical_op = op_mapping["canonical_operation"]
    assert canonical_op == {
        "kind": "invoke_by_id",
        "entity": "Customer",
        "lookup": {"field": "customerId", "request_field": "id"},
        "request_mappings": [
            {
                "source": "Customer.customerId",
                "target_path": "/SyncCustomerRequest/customerId",
            },
            {"source": "Customer.status", "target_path": "/SyncCustomerRequest/status"},
        ],
        "response": {
            "mode": "return_only",
            "response_mappings": [
                {
                    "source_path": "/SyncCustomerResponse/resultCode",
                    "target": "resultCode",
                },
                {"source_path": "/SyncCustomerResponse/message", "target": "message"},
            ],
        },
    }


def test_b2_canonical_mapping_yaml_has_expected_invoke_by_id_shape() -> None:
    """[B-2] The canonical mapping YAML contains the designed invoke_by_id shape.

    This test does NOT run the Engine translation layer; it just reads the raw
    YAML to confirm the fixture encodes the intended design from PR #192 §6.
    Validates that the golden fixture remains in sync with the design doc.
    """
    raw = yaml.safe_load(CANONICAL_MAPPING.read_text(encoding="utf-8"))
    mappings = raw["operation_mappings"]

    assert len(mappings) == 1
    entry = mappings[0]

    assert entry["operation"] == "syncCustomer"
    assert entry["mode"] == "canonical"

    canonical_op = entry["canonical_operation"]
    assert canonical_op["kind"] == "invoke_by_id"
    assert canonical_op["entity"] == "Customer"

    lookup = canonical_op["lookup"]
    assert lookup["request_field"] == "id"
    assert lookup["field"] == "customerId"

    req_mappings = canonical_op["request_mappings"]
    req_paths = {m["target_path"] for m in req_mappings}
    assert "/SyncCustomerRequest/customerId" in req_paths
    assert "/SyncCustomerRequest/status" in req_paths

    response = canonical_op["response"]
    assert response["mode"] == "return_only"
    resp_targets = {m["target"] for m in response["response_mappings"]}
    assert "resultCode" in resp_targets
    assert "message" in resp_targets


def test_b3_canonical_mapping_request_paths_match_wsdl_input_fields() -> None:
    """[B-3] Every request_mapping target_path exists in the WSDL input element.

    Cross-validates the mapping fixture against the WSDL fixture so both stay
    in sync.  Does not run the translation layer.
    """
    raw = yaml.safe_load(CANONICAL_MAPPING.read_text(encoding="utf-8"))
    spec = load_soap_contract_spec(
        WSDL,
        interface_name="customer-sync-client",
        package_root=FIXTURE,
    )
    op = spec.operations[0]
    known_input_paths = {f.path for f in op.input_fields}

    canonical_op = raw["operation_mappings"][0]["canonical_operation"]
    for mapping in canonical_op["request_mappings"]:
        target_path = mapping["target_path"]
        assert target_path in known_input_paths, (
            f"request_mapping target_path '{target_path}' is not declared in "
            f"WSDL input element; known paths: {sorted(known_input_paths)}"
        )


def test_b4_canonical_mapping_response_paths_match_wsdl_output_fields() -> None:
    """[B-4] Every response_mapping source_path exists in the WSDL output element.

    Cross-validates the mapping fixture against the WSDL fixture so both stay
    in sync.  Does not run the translation layer.
    """
    raw = yaml.safe_load(CANONICAL_MAPPING.read_text(encoding="utf-8"))
    spec = load_soap_contract_spec(
        WSDL,
        interface_name="customer-sync-client",
        package_root=FIXTURE,
    )
    op = spec.operations[0]
    known_output_paths = {f.path for f in op.output_fields}

    canonical_op = raw["operation_mappings"][0]["canonical_operation"]
    for resp_mapping in canonical_op["response"]["response_mappings"]:
        source_path = resp_mapping["source_path"]
        assert source_path in known_output_paths, (
            f"response_mapping source_path '{source_path}' is not declared in "
            f"WSDL output element; known paths: {sorted(known_output_paths)}"
        )


def test_b5_canonical_mode_without_canonical_operation_block_rejected(tmp_path: Path) -> None:
    """[B-5] downstream canonical mappings require canonical_operation."""
    _write_outbound_fixture(
        tmp_path,
        mapping_content="operation_mappings:\n  - operation: syncCustomer\n    mode: canonical\n",
    )
    with pytest.raises(
        ValueError,
        match="with mode canonical requires canonical_operation",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_b6_adapter_only_with_canonical_operation_block_rejected(tmp_path: Path) -> None:
    """[B-6] mode: adapter_only with a canonical_operation block is rejected."""
    mapping_content = (
        "operation_mappings:\n"
        "  - operation: syncCustomer\n"
        "    mode: adapter_only\n"
        "    canonical_operation:\n"
        "      kind: invoke_by_id\n"
    )
    _write_outbound_fixture(tmp_path, mapping_content=mapping_content)
    with pytest.raises(
        ValueError,
        match="cannot declare canonical_operation when mode is adapter_only",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_b7_duplicate_operation_in_mapping_rejected(tmp_path: Path) -> None:
    """[B-7] Declaring the same operation twice in operation_mappings is rejected."""
    mapping_content = (
        "operation_mappings:\n"
        "  - operation: syncCustomer\n"
        "    mode: adapter_only\n"
        "  - operation: syncCustomer\n"
        "    mode: adapter_only\n"
    )
    _write_outbound_fixture(tmp_path, mapping_content=mapping_content)
    with pytest.raises(
        ValueError,
        match="mapping declares operation 'syncCustomer' more than once",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_b8_unknown_operation_in_mapping_rejected(tmp_path: Path) -> None:
    """[B-8] A mapping entry referencing an operation not in the WSDL is rejected."""
    mapping_content = (
        "operation_mappings:\n"
        "  - operation: syncCustomer\n"
        "    mode: adapter_only\n"
        "  - operation: unknownOperation\n"
        "    mode: adapter_only\n"
    )
    _write_outbound_fixture(tmp_path, mapping_content=mapping_content)
    with pytest.raises(
        ValueError,
        match="mapping references unknown operation 'unknownOperation'",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_b9_missing_operation_in_mapping_rejected(tmp_path: Path) -> None:
    """[B-9] Mapping file that omits a WSDL operation entirely is rejected."""
    # Empty mapping list — syncCustomer is not mapped at all.
    _write_outbound_fixture(
        tmp_path,
        mapping_content="operation_mappings: []\n",
    )
    # Empty list triggers "non-empty" guard before the missing-op check.
    with pytest.raises(
        ValueError,
        match="must declare a non-empty operation_mappings list",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_b10_unsupported_mapping_mode_rejected(tmp_path: Path) -> None:
    """[B-10] An unrecognised operation mapping mode is rejected."""
    mapping_content = (
        "operation_mappings:\n"
        "  - operation: syncCustomer\n"
        "    mode: passthrough\n"
    )
    _write_outbound_fixture(tmp_path, mapping_content=mapping_content)
    with pytest.raises(
        ValueError,
        match="unsupported operation mapping mode 'passthrough'",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


# ---------------------------------------------------------------------------
# Section C — Adapter-only regression guards
# ---------------------------------------------------------------------------


def test_c1_adapter_only_downstream_soap_translates_successfully() -> None:
    """[C-1] adapter_only mapping on downstream SOAP interface is accepted today."""
    metadata = build_metadata_project(ADAPTER_MANIFEST)

    contract = next(
        (c for c in metadata.contracts if c.name == "customer-sync-client"),
        None,
    )
    assert contract is not None, "customer-sync-client contract not found in metadata"
    assert contract.type == "soap-wsdl"
    assert contract.soap_contract is not None
    assert contract.soap_contract["direction"] == "downstream"
    assert "syncCustomer" in (contract.soap_contract.get("operation_mappings") or {})
    mode = contract.soap_contract["operation_mappings"]["syncCustomer"]["mode"]
    assert mode == "adapter_only"


def test_c2_adapter_only_downstream_soap_generates_client_scaffold(
    tmp_path: Path,
) -> None:
    """[C-2] Adapter-only downstream SOAP generates Spring WS client artifacts.

    Regression guard: adding the outbound canonical generation path (Slices 2-4)
    must NOT break the existing adapter-only client scaffold.
    """
    from appbuilder.generation import generate_application

    metadata = build_metadata_project(ADAPTER_MANIFEST)
    report = generate_application(
        metadata,
        tmp_path / "generated-outbound-adapter",
        source_manifest=str(ADAPTER_MANIFEST),
    )

    java_root = (
        tmp_path
        / "generated-outbound-adapter"
        / "src/main/java/com/appbuilder/soap_outbound_canonical_customer/adapter/soap"
    )
    client_path = java_root / "CustomerSyncClientSoapClient.java"
    config_path = (
        tmp_path
        / "generated-outbound-adapter"
        / "src/main/java/com/appbuilder/soap_outbound_canonical_customer/adapter/soap"
        / "SoapClientConfig.java"
    )

    assert client_path in report.files_created, (
        f"Expected SOAP client at {client_path}; files_created: {sorted(report.files_created)}"
    )
    assert config_path in report.files_created

    client_source = client_path.read_text(encoding="utf-8")
    assert "@Component" in client_source
    assert "WebServiceTemplate webServiceTemplate" in client_source
    assert "syncCustomer" in client_source
    assert 'app.soap.clients.customer-sync-client.uri' in client_source
    assert "SyncCustomerRequest" in client_source
    assert "urn:edgeforge:examples:customer-sync:v1" in client_source
    assert "urn:syncCustomer" in client_source


def test_c3_adapter_only_downstream_soap_packages_wsdl_resources(
    tmp_path: Path,
) -> None:
    """[C-3] WSDL resource is packaged under soap-contracts/ in the generated app."""
    from appbuilder.generation import generate_application

    metadata = build_metadata_project(ADAPTER_MANIFEST)
    report = generate_application(
        metadata,
        tmp_path / "generated-outbound-resources",
        source_manifest=str(ADAPTER_MANIFEST),
    )

    wsdl_resource = (
        tmp_path
        / "generated-outbound-resources"
        / "src/main/resources/soap-contracts/customer-sync-client"
        / "contracts/customer-sync-service.wsdl"
    )
    assert wsdl_resource in report.files_created
    wsdl_text = wsdl_resource.read_text(encoding="utf-8")
    assert "urn:edgeforge:examples:customer-sync:v1" in wsdl_text
    assert "SyncCustomerRequest" in wsdl_text


def test_c4_adapter_only_downstream_soap_emits_uri_config(tmp_path: Path) -> None:
    """[C-4] application.yaml includes the app.soap.clients.<contract-slug>.uri key."""
    from appbuilder.generation import generate_application

    metadata = build_metadata_project(ADAPTER_MANIFEST)
    generate_application(
        metadata,
        tmp_path / "generated-outbound-config",
        source_manifest=str(ADAPTER_MANIFEST),
    )

    app_yaml = (
        tmp_path / "generated-outbound-config" / "src/main/resources/application.yaml"
    )
    content = app_yaml.read_text(encoding="utf-8")
    assert "  soap:" in content
    assert "    clients:" in content
    assert "      customer-sync-client:" in content
    assert "        uri:" in content
    # NOTE: design doc §10 says the WSDL soap:address should eventually become
    # the generated default.  The current generator emits a localhost placeholder;
    # update this assertion when the WSDL-address-as-default behaviour is
    # implemented (Slice N).
    assert "localhost" in content or "example.invalid/customer-sync" in content


def test_c5_no_outbound_soap_action_controller_in_adapter_only_output(
    tmp_path: Path,
) -> None:
    """[C-5] Adapter-only generation does NOT emit OutboundSoapActionController.

    The controller appears only for canonical invoke_by_id manifests, never for
    adapter-only ones.
    """
    from appbuilder.generation import generate_application

    metadata = build_metadata_project(ADAPTER_MANIFEST)
    generate_application(
        metadata,
        tmp_path / "generated-outbound-adapter-no-controller",
        source_manifest=str(ADAPTER_MANIFEST),
    )

    java_root = (
        tmp_path
        / "generated-outbound-adapter-no-controller"
        / "src/main/java/com/appbuilder/soap_outbound_canonical_customer"
    )
    controller_candidates = list(java_root.rglob("*OutboundSoap*Controller*"))
    assert controller_candidates == [], (
        "OutboundSoapActionController must not be generated for adapter-only manifests; "
        f"found: {controller_candidates}"
    )


def test_c6_no_outbound_soap_action_controller_for_inbound_soap_only(
    tmp_path: Path,
) -> None:
    """[C-6] Inbound SOAP canonical read_by_id apps do not emit outbound actions."""
    _assert_no_outbound_soap_action_controller(
        Path("tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml"),
        tmp_path / "generated-inbound-soap-no-outbound-action",
    )


def test_c7_no_outbound_soap_action_controller_for_xml_only(
    tmp_path: Path,
) -> None:
    """[C-7] XML/XSD-only apps do not emit outbound SOAP actions."""
    _assert_no_outbound_soap_action_controller(
        Path("tests/fixtures/edgecontracts/xml-xsd/account-roundtrip-runtime/app-definition.yaml"),
        tmp_path / "generated-xml-no-outbound-soap-action",
    )


def test_c8_no_outbound_soap_action_controller_for_file_only(
    tmp_path: Path,
) -> None:
    """[C-8] File-contract-only apps do not emit outbound SOAP actions."""
    _assert_no_outbound_soap_action_controller(
        Path("tests/fixtures/file-contracts/csv-inbound/app-definition.yaml"),
        tmp_path / "generated-file-no-outbound-soap-action",
    )


# ---------------------------------------------------------------------------
# Section D — Canonical invoke_by_id negative translation tests
# ---------------------------------------------------------------------------


def test_d1_downstream_canonical_unsupported_kind_rejected(tmp_path: Path) -> None:
    """[D-1] mode: canonical rejects unsupported downstream canonical kinds."""
    mapping_content = (
        "operation_mappings:\n"
        "  - operation: syncCustomer\n"
        "    mode: canonical\n"
        "    canonical_operation:\n"
        "      kind: send_all\n"
        "      entity: Customer\n"
        "      lookup:\n"
        "        request_field: id\n"
        "        field: customerId\n"
        "      request_mappings: []\n"
        "      response:\n"
        "        mode: return_only\n"
        "        response_mappings: []\n"
    )
    _write_outbound_fixture(tmp_path, mapping_content=mapping_content)
    with pytest.raises(
        ValueError,
        match="Only invoke_by_id is supported for downstream SOAP interfaces",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d2_handler_method_key_on_downstream_canonical_rejected(tmp_path: Path) -> None:
    """[D-2] handler_method combined with mode: canonical is always rejected.

    Per design doc §6: a canonical mapping with handler_method is invalid
    because outbound canonical invocation is generated behavior, not
    adapter-only delegation.  This must hold for both upstream and downstream
    contracts.

    This check fires before canonical_operation parsing, so the assertion stays
    exact even as outbound canonical metadata support grows slice by slice.
    """
    mapping_content = (
        "operation_mappings:\n"
        "  - operation: syncCustomer\n"
        "    mode: canonical\n"
        "    handler_method: handleSyncCustomer\n"
    )
    _write_outbound_fixture(tmp_path, mapping_content=mapping_content)
    with pytest.raises(
        ValueError,
        match="cannot combine handler_method with mode canonical",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d3_unknown_canonical_entity_rejected(tmp_path: Path) -> None:
    """[D-3] invoke_by_id requires a known canonical entity."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["entity"] = "Ghost"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="references unknown canonical entity 'Ghost'"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d4_unknown_lookup_field_rejected(tmp_path: Path) -> None:
    """[D-4] lookup.field must reference a known canonical field."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["lookup"]["field"] = "ghostId"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="references unknown lookup field 'Customer.ghostId'"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d5_non_persistence_id_lookup_field_rejected(tmp_path: Path) -> None:
    """[D-5] lookup.field must be the canonical persistence ID for the MVP."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["lookup"]["field"] = "status"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="lookup field 'status' must be the persistence ID"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d6_lookup_request_field_must_be_id(tmp_path: Path) -> None:
    """[D-6] lookup.request_field is restricted to id in the MVP."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["lookup"][
        "request_field"
    ] = "customerId"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="supports only request_field 'id'"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d7_missing_lookup_request_field_rejected(tmp_path: Path) -> None:
    """[D-7] lookup.request_field is required for invoke_by_id."""
    raw = _canonical_mapping_payload()
    del raw["operation_mappings"][0]["canonical_operation"]["lookup"]["request_field"]
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="requires field and request_field"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d8_unknown_request_source_field_rejected(tmp_path: Path) -> None:
    """[D-8] request_mappings[].source must resolve to a canonical field."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["request_mappings"][1][
        "source"
    ] = "Customer.ghost"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(
        ValueError,
        match="request source references unknown field 'Customer.ghost'",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d9_unknown_request_target_path_rejected(tmp_path: Path) -> None:
    """[D-9] request_mappings[].target_path must exist in the SOAP input model."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["request_mappings"][1][
        "target_path"
    ] = "/SyncCustomerRequest/ghost"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="unknown target_path '/SyncCustomerRequest/ghost'"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d10_missing_required_request_mapping_rejected(tmp_path: Path) -> None:
    """[D-10] required SOAP request fields must be mapped."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["request_mappings"] = [
        raw["operation_mappings"][0]["canonical_operation"]["request_mappings"][0]
    ]
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="missing request mappings for required SOAP field"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d11_missing_response_block_rejected(tmp_path: Path) -> None:
    """[D-11] return-only response metadata is required for invoke_by_id."""
    raw = _canonical_mapping_payload()
    del raw["operation_mappings"][0]["canonical_operation"]["response"]
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="requires canonical_operation.response"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d12_unsupported_response_mode_rejected(tmp_path: Path) -> None:
    """[D-12] response.mode values other than return_only fail fast."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["response"][
        "mode"
    ] = "persist_and_return"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="Only return_only is supported"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d13_unknown_response_source_path_rejected(tmp_path: Path) -> None:
    """[D-13] response_mappings[].source_path must exist in the SOAP output model."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["response"]["response_mappings"][0][
        "source_path"
    ] = "/SyncCustomerResponse/ghost"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="unknown source_path '/SyncCustomerResponse/ghost'"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d14_malformed_response_target_name_rejected(tmp_path: Path) -> None:
    """[D-14] return DTO field names must be valid generated field names."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["response"]["response_mappings"][0][
        "target"
    ] = "result-code"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="target 'result-code' is not a supported response field name"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d15_missing_required_response_mapping_rejected(tmp_path: Path) -> None:
    """[D-15] required SOAP response fields must be mapped."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["response"]["response_mappings"] = [
        raw["operation_mappings"][0]["canonical_operation"]["response"]["response_mappings"][1]
    ]
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="missing response mappings for required SOAP field"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d16_duplicate_request_source_rejected(tmp_path: Path) -> None:
    """[D-16] request_mappings cannot reuse the same canonical source field."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["request_mappings"][1][
        "source"
    ] = "Customer.customerId"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="request source 'Customer.customerId' more than once"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d17_duplicate_request_target_rejected(tmp_path: Path) -> None:
    """[D-17] request_mappings cannot reuse the same SOAP request target path."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["request_mappings"][1][
        "target_path"
    ] = "/SyncCustomerRequest/customerId"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="request target_path '/SyncCustomerRequest/customerId' more than once"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d18_duplicate_response_source_rejected(tmp_path: Path) -> None:
    """[D-18] response_mappings cannot reuse the same SOAP response source path."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["response"]["response_mappings"][1][
        "source_path"
    ] = "/SyncCustomerResponse/resultCode"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="response source_path '/SyncCustomerResponse/resultCode' more than once"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d19_duplicate_response_target_rejected(tmp_path: Path) -> None:
    """[D-19] response_mappings cannot reuse the same return field name."""
    raw = _canonical_mapping_payload()
    raw["operation_mappings"][0]["canonical_operation"]["response"]["response_mappings"][1][
        "target"
    ] = "resultCode"
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    with pytest.raises(ValueError, match="response target 'resultCode' more than once"):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d20_request_type_mismatch_rejected(tmp_path: Path) -> None:
    """[D-20] canonical-to-SOAP request mappings must be type-compatible."""
    raw = _canonical_mapping_payload()
    _write_outbound_fixture(tmp_path, mapping_path=_write_mapping_payload(tmp_path, raw))

    api_path = tmp_path / "upstream/customer-api-spec.yaml"
    api = yaml.safe_load(api_path.read_text(encoding="utf-8"))
    api["components"]["schemas"]["CreateCustomerRequest"]["properties"]["status"][
        "type"
    ] = "number"
    api["components"]["schemas"]["Customer"]["properties"]["status"]["type"] = "number"
    api_path.write_text(yaml.safe_dump(api, sort_keys=False), encoding="utf-8")

    create_sample_path = tmp_path / "upstream/create-customer-request.json"
    create_sample = json.loads(create_sample_path.read_text(encoding="utf-8"))
    create_sample["status"] = 123.45
    create_sample_path.write_text(
        json.dumps(create_sample, indent=2), encoding="utf-8"
    )
    response_sample_path = tmp_path / "upstream/customer-response.json"
    response_sample = json.loads(response_sample_path.read_text(encoding="utf-8"))
    response_sample["status"] = 123.45
    response_sample_path.write_text(
        json.dumps(response_sample, indent=2), encoding="utf-8"
    )

    wsdl_path = tmp_path / "contracts/customer-sync-service.wsdl"
    wsdl_text = wsdl_path.read_text(encoding="utf-8")
    wsdl_path.write_text(
        wsdl_text.replace(
            '<xs:element name="status"     type="xs:string"/>',
            '<xs:element name="status"     type="xs:boolean"/>',
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="cannot map canonical field 'Customer.status' .*SOAP request field '/SyncCustomerRequest/status'.*boolean",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


def test_d21_adapter_only_missing_mode_with_canonical_block_rejected(tmp_path: Path) -> None:
    """[D-21] omitted mode remains adapter-only and cannot carry canonical metadata."""
    mapping_content = (
        "operation_mappings:\n"
        "  - operation: syncCustomer\n"
        "    canonical_operation:\n"
        "      kind: invoke_by_id\n"
        "      entity: Customer\n"
    )
    _write_outbound_fixture(tmp_path, mapping_content=mapping_content)

    with pytest.raises(
        ValueError,
        match="cannot declare canonical_operation when mode is adapter_only",
    ):
        build_metadata_project(tmp_path / "app-definition.yaml")


# ---------------------------------------------------------------------------
# Section E — Generation-output stubs (Slices 2-4, not yet run)
# ---------------------------------------------------------------------------


def test_e1_invoke_by_id_manifest_translates_to_metadata(tmp_path: Path) -> None:
    """[E-1] Slice 1: canonical invoke_by_id manifest translates successfully.

    Assertions:
    - downstream contract direction == "downstream"
    - operation_mappings["syncCustomer"]["mode"] == "canonical"
    - canonical_operation.kind == "invoke_by_id"
    - canonical_operation.entity == "Customer"
    - canonical_operation.lookup.request_field == "id"
    - canonical_operation.lookup.field == "customerId"
    - request_mappings contains /SyncCustomerRequest/customerId and /SyncCustomerRequest/status
    - response.mode == "return_only"
    - response.response_mappings contains resultCode and message targets
    """
    metadata = build_metadata_project(CANONICAL_MANIFEST)
    contract = next(c for c in metadata.contracts if c.name == "customer-sync-client")
    assert contract.soap_contract["direction"] == "downstream"
    op_mapping = contract.soap_contract["operation_mappings"]["syncCustomer"]
    assert op_mapping["mode"] == "canonical"
    canonical_op = op_mapping["canonical_operation"]
    assert canonical_op["kind"] == "invoke_by_id"
    assert canonical_op["entity"] == "Customer"
    assert canonical_op["lookup"]["request_field"] == "id"
    assert canonical_op["lookup"]["field"] == "customerId"
    req_paths = {m["target_path"] for m in canonical_op["request_mappings"]}
    assert "/SyncCustomerRequest/customerId" in req_paths
    assert "/SyncCustomerRequest/status" in req_paths
    resp = canonical_op["response"]
    assert resp["mode"] == "return_only"
    resp_targets = {m["target"] for m in resp["response_mappings"]}
    assert "resultCode" in resp_targets
    assert "message" in resp_targets


def test_e2_invoke_by_id_generates_outbound_action_controller(tmp_path: Path) -> None:
    """[E-2] Generation emits the outbound SOAP canonical invoke_by_id vertical.

    Assertions:
    - OutboundSoapActionController.java exists under adapter/soap/
    - @RestController annotation present
    - generic /soap/outbound/{contractName}/{operationName} route present
    - request body accepts {"id": "..."}
    - canonical row lookup, request rendering, SOAP client invocation, and
      response mapping are wired
    - known operation no longer returns a 501 scaffold-stub
    """
    from appbuilder.generation import generate_application

    metadata = build_metadata_project(CANONICAL_MANIFEST)
    generate_application(
        metadata, tmp_path / "generated-invoke", source_manifest=str(CANONICAL_MANIFEST)
    )
    java_soap = (
        tmp_path
        / "generated-invoke"
        / "src/main/java/com/appbuilder/soap_outbound_canonical_customer/adapter/soap"
    )
    controller_path = java_soap / "OutboundSoapActionController.java"
    assert controller_path.exists()
    src = controller_path.read_text(encoding="utf-8")
    assert "@RestController" in src
    assert '@RequestMapping("/soap/outbound")' in src
    assert '@PostMapping("/{contractName}/{operationName}")' in src
    assert "record OutboundSoapActionRequest(String id)" in src
    assert "record OutboundSoapActionSuccessResponse(" in src
    assert "record OutboundSoapActionFailureResponse(" in src
    assert 'Map.entry("customer-sync-client", Map.ofEntries(' in src
    assert 'Map.entry("customer-sync-client", Set.of("syncCustomer"))' in src
    assert (
        'Map.entry("syncCustomer", new OperationConfig("Customer", "customerId", '
        '"customer-sync-client::syncCustomer"))'
    ) in src
    assert "Unknown downstream SOAP canonical contract: " in src
    assert "Unknown downstream SOAP canonical operation: " in src
    assert "has no canonical invoke_by_id mapping." in src
    assert "Outbound SOAP canonical invoke_by_id request id is required." in src
    assert "HttpStatus.NOT_IMPLEMENTED" not in src
    assert "request rendering and SOAP client invocation are not implemented" not in src
    assert "CustomerRepository customerRepository" in src
    assert "CustomerSyncClientSoapClient customerSyncClientSoapClient" in src
    assert "customerRepository.findById(lookupId)" in src
    assert "customerSyncClientSoapClient.syncCustomer(requestPayload)" in src
    assert "invokeCustomerSyncClientSyncCustomerRequestPayload(record)" in src
    assert "invokeCustomerSyncClientSyncCustomerResponse(responsePayload)" in src
    assert '"response"' not in src  # generated source has a typed response field, not raw JSON strings
    assert "Map<String, String> response" in src
    assert 'response.put("resultCode", resultCodeValue0);' in src
    assert 'response.put("message", messageValue1);' in src
    assert "SoapFaultClientException" in src
    assert "HttpStatus.SERVICE_UNAVAILABLE" in src
    assert "HttpStatus.GATEWAY_TIMEOUT" in src
    assert "Canonical entity 'Customer' was not found" in src
    assert "import java.math.BigDecimal;" not in src
    assert "import java.time.LocalDate;" not in src
    assert "import java.time.LocalDateTime;" not in src
    assert "import java.time.format.DateTimeParseException;" not in src
    assert "private Long asLongValue" not in src
    assert "private BigDecimal asBigDecimalValue" not in src
    assert "private Boolean asBooleanValue" not in src
    assert "private LocalDate asLocalDateValue" not in src
    assert "private LocalDateTime asLocalDateTimeValue" not in src
    client_src = (java_soap / "CustomerSyncClientSoapClient.java").read_text(
        encoding="utf-8"
    )
    assert "webServiceTemplate" in client_src
    assert "sendSourceAndReceive" in client_src
    assert "CustomerSyncClientSoapClient" in src
    assert "webServiceTemplate" not in src
    assert "sendSourceAndReceive" not in src


def test_e3_invoke_by_id_generates_request_mapping_renderer(tmp_path: Path) -> None:
    """[E-3] Generated renderer builds SOAP XML in XSD order.

    Assertions:
    - A request-builder method or inner class renders customerId before status
      (XSD xs:sequence order per SyncCustomerRequest declaration).
    - The renderer calls the repository to load the canonical Customer by ID.
    - No raw SOAP string construction (must use proper DOM/marshalling).
    """
    from appbuilder.generation import generate_application

    metadata = build_metadata_project(CANONICAL_MANIFEST)
    generate_application(
        metadata, tmp_path / "generated-renderer", source_manifest=str(CANONICAL_MANIFEST)
    )
    controller_path = (
        tmp_path
        / "generated-renderer"
        / "src/main/java/com/appbuilder/soap_outbound_canonical_customer/adapter/soap"
        / "OutboundSoapActionController.java"
    )
    src = controller_path.read_text(encoding="utf-8")
    assert "customerRepository.findById(lookupId)" in src
    customer_id_append = 'appendElement(document, root, "urn:edgeforge:examples:customer-sync:v1", "customerId", customerIdValue0);'
    status_append = 'appendElement(document, root, "urn:edgeforge:examples:customer-sync:v1", "status", statusValue1);'
    assert customer_id_append in src
    assert status_append in src
    assert src.index(customer_id_append) < src.index(status_append)
    assert "Document document = documentBuilder().newDocument();" in src
    assert "createElement(document," in src
    assert "new DOMSource(document)" in src
    assert "<SyncCustomerRequest" not in src


def test_e4_invoke_by_id_generates_response_dto(tmp_path: Path) -> None:
    """[E-4] Response DTO nests mapped return-only SOAP fields under response.

    Assertions:
    - A success response DTO exists.
    - Fields: contractName, operationName, entity, id, response.
    - mapped SOAP values are stored under response, not flattened.
    - No JPA entity exposure.
    - Missing canonical row returns a 404-style response (no stack trace).
    - SOAP Fault from remote returns a deterministic mapped error.
    """
    from appbuilder.generation import generate_application

    metadata = build_metadata_project(CANONICAL_MANIFEST)
    generate_application(
        metadata, tmp_path / "generated-response", source_manifest=str(CANONICAL_MANIFEST)
    )
    controller_path = (
        tmp_path
        / "generated-response"
        / "src/main/java/com/appbuilder/soap_outbound_canonical_customer/adapter/soap"
        / "OutboundSoapActionController.java"
    )
    src = controller_path.read_text(encoding="utf-8")
    assert "public record OutboundSoapActionSuccessResponse(" in src
    assert "Map<String, String> response" in src
    assert 'response.put("resultCode", resultCodeValue0);' in src
    assert 'response.put("message", messageValue1);' in src
    assert "ResponseEntity.ok(" in src
    assert "OutboundSoapActionFailureResponse" in src
    assert "HttpStatus.NOT_FOUND" in src
    assert "Canonical entity 'Customer' was not found" in src
    assert "Remote SOAP Fault [" in src
    assert "HttpStatus.BAD_GATEWAY" in src
    assert "Customer record" in src
    assert "ResponseEntity<Customer>" not in src


@pytest.mark.skip(
    reason=(
        "Slice 4: generation-runtime diagnostics not yet implemented. "
        "Parser-level unsupported-kind rejection is covered by D-1."
    )
)
def test_e5_unsupported_invoke_kind_rejected_at_generation(tmp_path: Path) -> None:
    """[E-5] Future runtime slice: unknown canonical_operation.kind fails generation.

    Slice 1 rejects this at metadata translation time; this generation-output
    stub remains as a future guard for the action/controller runtime layer.
    """
    from appbuilder.generation import generate_application

    mapping_content = (
        "operation_mappings:\n"
        "  - operation: syncCustomer\n"
        "    mode: canonical\n"
        "    canonical_operation:\n"
        "      kind: send_all\n"
        "      entity: Customer\n"
    )
    _write_outbound_fixture(tmp_path, mapping_content=mapping_content)
    metadata = build_metadata_project(tmp_path / "app-definition.yaml")
    with pytest.raises(ValueError, match="unsupported.*kind.*send_all"):
        generate_application(
            metadata,
            tmp_path / "generated-bad-kind",
            source_manifest=str(tmp_path / "app-definition.yaml"),
        )


@pytest.mark.skip(
    reason=(
        "Slice 3: generation-runtime diagnostics not yet implemented. "
        "Parser-level non-persistence-ID rejection is covered by D-5."
    )
)
def test_e6_non_persistence_id_lookup_field_rejected(tmp_path: Path) -> None:
    """[E-6] Future runtime slice: non-ID lookup remains rejected during generation.

    Design doc §7: metadata_only business_key / external_reference roles must
    not be accepted as invoke_by_id lookup proof in the MVP.
    """
    from appbuilder.generation import generate_application

    raw = yaml.safe_load(CANONICAL_MAPPING.read_text(encoding="utf-8"))
    raw["operation_mappings"][0]["canonical_operation"]["lookup"]["field"] = "status"
    mapping_path = tmp_path / "bad-lookup-mapping.yaml"
    mapping_path.write_text(yaml.dump(raw), encoding="utf-8")
    _write_outbound_fixture(tmp_path, mapping_path=mapping_path)
    metadata = build_metadata_project(tmp_path / "app-definition.yaml")
    with pytest.raises(
        ValueError,
        match="lookup field.*must be the persistence ID|invoke_by_id.*persistence ID",
    ):
        generate_application(
            metadata,
            tmp_path / "generated-bad-lookup",
            source_manifest=str(tmp_path / "app-definition.yaml"),
        )


@pytest.mark.skip(
    reason=(
        "Slice 3: generation-runtime diagnostics not yet implemented. "
        "Parser-level request target validation is covered by D-9."
    )
)
def test_e7_unknown_request_mapping_target_path_rejected(tmp_path: Path) -> None:
    """[E-7] Future runtime slice: target_path not in WSDL input remains rejected.

    Design doc §8: source must resolve to a known field; target_path must
    resolve to a supported SOAP input XML field.
    """
    from appbuilder.generation import generate_application

    raw = yaml.safe_load(CANONICAL_MAPPING.read_text(encoding="utf-8"))
    raw["operation_mappings"][0]["canonical_operation"]["request_mappings"].append(
        {"source": "Customer.customerName", "target_path": "/SyncCustomerRequest/unknownField"}
    )
    mapping_path = tmp_path / "bad-req-path-mapping.yaml"
    mapping_path.write_text(yaml.dump(raw), encoding="utf-8")
    _write_outbound_fixture(tmp_path, mapping_path=mapping_path)
    metadata = build_metadata_project(tmp_path / "app-definition.yaml")
    with pytest.raises(ValueError, match="unknown.*target_path.*unknownField|unknownField.*not declared"):
        generate_application(
            metadata,
            tmp_path / "generated-bad-req-path",
            source_manifest=str(tmp_path / "app-definition.yaml"),
        )


@pytest.mark.skip(
    reason=(
        "Slice 4: generation-runtime diagnostics not yet implemented. "
        "Parser-level response source validation is covered by D-13."
    )
)
def test_e8_unknown_response_mapping_source_path_rejected(tmp_path: Path) -> None:
    """[E-8] Future runtime slice: source_path not in WSDL output remains rejected.

    Design doc §9: response_mappings[].source_path must resolve to supported
    SOAP output fields.
    """
    from appbuilder.generation import generate_application

    raw = yaml.safe_load(CANONICAL_MAPPING.read_text(encoding="utf-8"))
    raw["operation_mappings"][0]["canonical_operation"]["response"]["response_mappings"].append(
        {"source_path": "/SyncCustomerResponse/ghostField", "target": "ghost"}
    )
    mapping_path = tmp_path / "bad-resp-path-mapping.yaml"
    mapping_path.write_text(yaml.dump(raw), encoding="utf-8")
    _write_outbound_fixture(tmp_path, mapping_path=mapping_path)
    metadata = build_metadata_project(tmp_path / "app-definition.yaml")
    with pytest.raises(ValueError, match="unknown.*source_path.*ghostField|ghostField.*not declared"):
        generate_application(
            metadata,
            tmp_path / "generated-bad-resp-path",
            source_manifest=str(tmp_path / "app-definition.yaml"),
        )


# ---------------------------------------------------------------------------
# Section F — Runtime proof stubs (Slice 5)
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "Slice 5: runtime proof requires a buildable generated app and a "
        "local mock SOAP service.  See docs/edgecontracts/"
        "outbound-soap-canonical-invocation-mvp-design.md §17 for the "
        "expected proof sequence."
    )
)
def test_f1_generated_app_invokes_mock_soap_service(tmp_path: Path) -> None:
    """[F-1] Runtime proof: generated app calls mock SOAP service from canonical row.

    Proof sequence (design doc §17):
    1. Generate from CANONICAL_MANIFEST.
    2. mvn -q -DskipTests package in the generated app directory.
    3. Start a local mock SOAP server that responds to syncCustomer with
       resultCode=ACCEPTED, message="Customer synchronized".
    4. Start the generated app on a free port.
    5. Seed a Customer via POST /customers.
    6. Call POST /soap/outbound/customer-sync-client/syncCustomer
       with body {"id": "<seeded-customerId>"}.
    7. Assert the mock server received a valid SyncCustomerRequest with the
       correct customerId and status values.
    8. Assert the generated app response contains:
       {"contractName": "customer-sync-client",
        "operationName": "syncCustomer",
        "entity": "Customer",
        "id": "<seeded-id>",
        "response": {"resultCode": "ACCEPTED", "message": "Customer synchronized"}}
    9. Assert missing row returns a 404-style response (no stack trace).
    10. Assert server unavailable (mock stopped) returns a 502/503-style response.
    11. Assert SOAP Fault from mock returns a deterministic error (no raw SOAP).
    """
    pass


@pytest.mark.skip(
    reason=(
        "Slice 5: runtime diagnostic proof for outbound SOAP not yet implementable. "
        "Un-skip after Slice 4 lands."
    )
)
def test_f2_missing_canonical_row_returns_deterministic_error(tmp_path: Path) -> None:
    """[F-2] Runtime proof: missing canonical row returns a 404-style error.

    Expected: HTTP 404, body contains entity name and ID, no stack trace,
    no raw SOAP payload, no EdgeForge dependency reference.
    (Design doc §11, missing-canonical-row row in diagnostics table.)
    """
    pass


@pytest.mark.skip(
    reason=(
        "Slice 5: SOAP server unavailable diagnostic not yet implementable. "
        "Un-skip after Slice 4 lands."
    )
)
def test_f3_soap_server_unavailable_returns_deterministic_error(tmp_path: Path) -> None:
    """[F-3] Runtime proof: unavailable downstream SOAP service returns 502/503-style
    error.

    Expected: HTTP 502 or 503, safe message (no local paths, no WSDL paths),
    no stack trace, no raw SOAP payload.
    (Design doc §11, SOAP server unavailable row.)
    """
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical_mapping_payload() -> dict[str, Any]:
    return yaml.safe_load(CANONICAL_MAPPING.read_text(encoding="utf-8"))


def _write_mapping_payload(tmp_path: Path, payload: dict[str, Any]) -> Path:
    mapping_path = tmp_path / "custom-mapping-source.yaml"
    mapping_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return mapping_path


def _assert_no_outbound_soap_action_controller(
    manifest_path: Path,
    output_dir: Path,
) -> None:
    from appbuilder.generation import generate_application

    metadata = build_metadata_project(manifest_path)
    generate_application(metadata, output_dir, source_manifest=str(manifest_path))
    candidates = list(output_dir.rglob("OutboundSoapActionController.java"))
    assert candidates == [], (
        "OutboundSoapActionController must be generated only for downstream SOAP "
        f"canonical invoke_by_id mappings; found: {candidates}"
    )


def _write_outbound_fixture(
    tmp_path: Path,
    *,
    mapping_content: str | None = None,
    mapping_path: Path | None = None,
) -> None:
    """Write a minimal outbound SOAP downstream fixture into tmp_path.

    Copies the WSDL and upstream files from the canonical fixture, then
    writes a custom mapping file specified by either mapping_content (raw YAML
    text) or mapping_path (existing file).  Produces app-definition.yaml that
    references mappings/custom-mapping.yaml.
    """
    fixture_dir = tmp_path
    (fixture_dir / "contracts").mkdir(parents=True, exist_ok=True)
    (fixture_dir / "mappings").mkdir(parents=True, exist_ok=True)
    (fixture_dir / "upstream").mkdir(parents=True, exist_ok=True)

    shutil.copy(WSDL, fixture_dir / "contracts" / WSDL.name)
    for f in (FIXTURE / "upstream").iterdir():
        shutil.copy(f, fixture_dir / "upstream" / f.name)

    if mapping_path is not None:
        shutil.copy(mapping_path, fixture_dir / "mappings" / "custom-mapping.yaml")
    elif mapping_content is not None:
        (fixture_dir / "mappings" / "custom-mapping.yaml").write_text(
            mapping_content, encoding="utf-8"
        )
    else:
        raise ValueError("Must supply mapping_content or mapping_path")

    manifest: dict[str, Any] = {
        "app_name": "SOAP Outbound Canonical Customer Client",
        "bounded_context": "soap_outbound_canonical_customer",
        "schema_version": "2.0",
        "upstream_interfaces": [
            {
                "name": "customer-api",
                "system": "CRM",
                "type": "rest-json",
                "spec": "upstream/customer-api-spec.yaml",
                "mapping": "upstream/customer-mapping.yaml",
                "operations": [
                    {
                        "name": "createCustomer",
                        "request_sample": "upstream/create-customer-request.json",
                        "response_sample": "upstream/customer-response.json",
                    },
                    {
                        "name": "getCustomer",
                        "response_sample": "upstream/customer-response.json",
                    },
                ],
            }
        ],
        "downstream_interfaces": [
            {
                "name": "customer-sync-client",
                "system": "CUSTOMER_CORE",
                "type": "soap-wsdl",
                "wsdl_path": "contracts/customer-sync-service.wsdl",
                "service": "CustomerSyncService",
                "port": "CustomerSyncServicePort",
                "mapping": "mappings/custom-mapping.yaml",
            }
        ],
        "target_profile": "springboot-legacy-compatible",
    }
    (fixture_dir / "app-definition.yaml").write_text(
        yaml.dump(manifest, sort_keys=False), encoding="utf-8"
    )
