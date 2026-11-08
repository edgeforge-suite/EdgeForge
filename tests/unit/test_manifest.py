from pathlib import Path

import pytest
import yaml

from appbuilder.contracts import load_project_definition
from appbuilder.metadata.models import TransformMapping


def test_load_project_definition_accepts_example_project() -> None:
    manifest = Path("examples/input-projects/xyz-accounts-modernization/app-definition.yaml")

    definition = load_project_definition(manifest)

    assert definition.app_name == "XYZ Accounts Replacement"
    assert definition.schema_version == "2.0"
    assert definition.app_archetype.value == "crud"
    assert definition.target_profile == "springboot-legacy-compatible"
    assert definition.upstream_interfaces[0].spec_url == "https://bank-internal.example.com/xyz/swagger.json"
    assert definition.upstream_interfaces[0].system == "CRM"
    assert definition.upstream_interfaces[0].version == "v1"
    assert definition.upstream_interfaces[0].mapping == "upstream/crm-account-mapping.yaml"
    assert definition.upstream_interfaces[0].operations[0].name == "createAccount"
    assert definition.downstream_interfaces[0].mapping == "downstream/eod-handoff-mapping.yaml"
    assert {path.as_posix() for path in definition.referenced_paths()} == {
        "upstream/crm-account-mapping.yaml",
        "upstream/sample-create-account-request.json",
        "upstream/sample-create-account-response.json",
        "downstream/eod-handoff-layout.yaml",
        "downstream/eod-handoff-mapping.yaml",
        "downstream/sample-output-file.txt",
        "data-handoffs/account-staging-table.sql",
        "data-handoffs/staging-table-mapping.yaml",
        "rules/account-business-rules.yaml",
        "legacy/xyz-notes.md",
    }


def test_load_project_definition_defaults_app_archetype_to_crud_when_absent(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    definition = load_project_definition(manifest)

    assert definition.app_archetype.value == "crud"


def test_load_project_definition_rejects_file_contracts_under_data_handoffs(
    tmp_path: Path,
) -> None:
    ddl = tmp_path / "file-contract.yaml"
    ddl.write_text("fields: []\n", encoding="utf-8")
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "data_handoffs:",
                "  - name: account-file",
                "    type: file-csv",
                "    spec: file-contract.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"data_handoffs\.0\.type.*not be valid"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_xml_xsd_under_data_handoffs(
    tmp_path: Path,
) -> None:
    xsd = tmp_path / "contract.xsd"
    xsd.write_text("<xs:schema xmlns:xs=\"http://www.w3.org/2001/XMLSchema\"/>", encoding="utf-8")
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "data_handoffs:",
                "  - name: account-xml",
                "    type: xml-xsd",
                "    spec: contract.xsd",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"data_handoffs\.0\.type.*not be valid"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_soap_wsdl_under_data_handoffs(
    tmp_path: Path,
) -> None:
    wsdl = tmp_path / "contract.wsdl"
    wsdl.write_text(
        "<wsdl:definitions xmlns:wsdl=\"http://schemas.xmlsoap.org/wsdl/\"/>",
        encoding="utf-8",
    )
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "data_handoffs:",
                "  - name: account-soap",
                "    type: soap-wsdl",
                "    spec: contract.wsdl",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"data_handoffs\.0\.type.*not be valid"):
        load_project_definition(manifest)


def test_load_project_definition_accepts_upstream_xml_xsd_manifest() -> None:
    manifest = Path("tests/fixtures/edgecontracts/xml-xsd/basic-customer/app-definition.yaml")

    definition = load_project_definition(manifest)

    interface = definition.upstream_interfaces[0]
    assert interface.type == "xml-xsd"
    assert interface.xsd_path == "contracts/customer.xsd"
    assert interface.root_element == "CustomerMessage"
    assert interface.namespace == "urn:edgeforge:examples:customer:v1"
    assert interface.namespace_alias == "cust"
    assert interface.sample == "samples/customer.xml"
    assert {path.as_posix() for path in definition.referenced_paths()} == {
        "contracts/customer.xsd",
        "samples/customer.xml",
    }


def test_load_project_definition_accepts_downstream_xml_xsd_manifest() -> None:
    manifest = Path("tests/fixtures/edgecontracts/xml-xsd/order-with-attributes/app-definition.yaml")

    definition = load_project_definition(manifest)

    interface = definition.downstream_interfaces[0]
    assert interface.type == "xml-xsd"
    assert interface.xsd_path == "contracts/order.xsd"
    assert interface.root_element == "ord:OrderMessage"


def test_load_project_definition_accepts_upstream_soap_wsdl_manifest() -> None:
    manifest = Path("tests/fixtures/edgecontracts/soap-wsdl/basic-customer-service/app-definition.yaml")

    definition = load_project_definition(manifest)

    interface = definition.upstream_interfaces[0]
    assert interface.type == "soap-wsdl"
    assert interface.wsdl_path == "contracts/customer-service.wsdl"
    assert interface.service == "CustomerService"
    assert interface.port == "CustomerServicePort"
    assert {path.as_posix() for path in definition.referenced_paths()} == {
        "contracts/customer-service.wsdl",
    }


def test_load_project_definition_accepts_downstream_soap_wsdl_manifest() -> None:
    manifest = Path("tests/fixtures/edgecontracts/soap-wsdl/basic-customer-client/app-definition.yaml")

    definition = load_project_definition(manifest)

    interface = definition.downstream_interfaces[0]
    assert interface.type == "soap-wsdl"
    assert interface.wsdl_path == "contracts/customer-service.wsdl"


def test_load_project_definition_rejects_soap_wsdl_missing_wsdl_path(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: account-soap",
                "    type: soap-wsdl",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"upstream_interfaces\.0.*not (?:be )?valid"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_xml_namespace_fields_on_soap_wsdl(
    tmp_path: Path,
) -> None:
    wsdl = tmp_path / "contract.wsdl"
    wsdl.write_text(
        "<wsdl:definitions xmlns:wsdl=\"http://schemas.xmlsoap.org/wsdl/\"/>",
        encoding="utf-8",
    )
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: account-soap",
                "    type: soap-wsdl",
                "    wsdl_path: contract.wsdl",
                "    namespace: urn:example:soap",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"upstream_interfaces\.0.*not (?:be )?valid"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_xml_xsd_missing_xsd_path(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: account-xml",
                "    type: xml-xsd",
                "    root_element: Account",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"upstream_interfaces\.0.*not (?:be )?valid"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_xml_xsd_missing_root_element(
    tmp_path: Path,
) -> None:
    xsd = tmp_path / "contract.xsd"
    xsd.write_text("<xs:schema xmlns:xs=\"http://www.w3.org/2001/XMLSchema\"/>", encoding="utf-8")
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: account-xml",
                "    type: xml-xsd",
                "    xsd_path: contract.xsd",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"upstream_interfaces\.0.*root_element"):
        load_project_definition(manifest)


def test_load_project_definition_accepts_metadata_only_identity_roles(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "identity_roles:",
                "  - entity: Posting",
                "    field: accountId",
                "    role: parent_reference",
                "    mode: metadata_only",
                "  - entity: Payment",
                "    field: idempotencyKey",
                "    role: idempotency_key",
                "    mode: metadata_only",
                "    policy:",
                "      operations: [createPayment]",
                "      replay_mode: cached_response",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    definition = load_project_definition(manifest)

    assert [role.role for role in definition.identity_roles] == [
        "parent_reference",
        "idempotency_key",
    ]
    assert definition.identity_roles[1].policy == {
        "operations": ["createPayment"],
        "replay_mode": "cached_response",
    }


def test_load_project_definition_rejects_persistence_id_identity_role(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "identity_roles:",
                "  - entity: Posting",
                "    field: postingId",
                "    role: persistence_id",
                "    mode: metadata_only",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="identity_overrides"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_active_identity_role_with_policy(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "identity_roles:",
                "  - entity: Payment",
                "    field: idempotencyKey",
                "    role: idempotency_key",
                "    mode: active",
                "    policy:",
                "      operations: [createPayment]",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="active identity role behavior is not supported yet"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_active_identity_role_without_policy(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "identity_roles:",
                "  - entity: Payment",
                "    field: idempotencyKey",
                "    role: idempotency_key",
                "    mode: active",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="policy is required for active identity role"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_identity_roles_for_passthrough_router(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "app_archetype: passthrough-router",
                "identity_roles:",
                "  - entity: Posting",
                "    field: accountId",
                "    role: parent_reference",
                "    mode: metadata_only",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="identity_roles.*app_archetype: crud"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_empty_identity_roles_for_passthrough_router(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "app_archetype: passthrough-router",
                "identity_roles: []",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="identity_roles.*app_archetype: crud"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_identity_roles_for_kafka_integration(
    tmp_path: Path,
) -> None:
    payload = _kafka_manifest_payload()
    payload["identity_roles"] = [
        {
            "entity": "Payment",
            "field": "correlationId",
            "role": "correlation_id",
            "mode": "metadata_only",
        }
    ]
    manifest = _write_manifest_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="identity_roles.*app_archetype: crud"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_empty_identity_roles_for_kafka_integration(
    tmp_path: Path,
) -> None:
    payload = _kafka_manifest_payload()
    payload["identity_roles"] = []
    manifest = _write_manifest_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="identity_roles.*app_archetype: crud"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_missing_schema_version(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_unknown_schema_version(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"1.0\"",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version.*1.0"):
        load_project_definition(manifest)


def test_load_project_definition_accepts_explicit_passthrough_router_archetype(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Country Router",
                "bounded_context: payments",
                "schema_version: \"2.0\"",
                "app_archetype: passthrough-router",
                "upstream_interfaces:",
                "  - name: inbound-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    definition = load_project_definition(manifest)

    assert definition.app_archetype.value == "passthrough-router"


def test_load_project_definition_accepts_kafka_integration_manifest() -> None:
    manifest = Path("tests/fixtures/kafka-integration/manifest.yaml")

    definition = load_project_definition(manifest)

    assert definition.app_name == "payment-mediation-adapter"
    assert definition.app_archetype.value == "kafka-integration"
    assert definition.kafka_config is not None
    assert definition.kafka_config.consumer_group == "payment-mediation-group"
    assert definition.kafka_config.concurrency == 1
    assert definition.async_routes is not None
    assert [route.name for route in definition.async_routes] == [
        "payment-initiated",
        "balance-updated",
    ]
    assert definition.async_routes[0].partition_key is not None
    assert definition.async_routes[0].partition_key.strategy == "field_value"
    assert {path.as_posix() for path in definition.referenced_paths()} == {
        "schemas/upstream/payment-initiated.json",
        "samples/payment-initiated.json",
        "schemas/downstream/settlement-request.json",
        "mappings/payment-to-settlement.yaml",
        "schemas/upstream/balance-updated.json",
        "schemas/downstream/ledger-update.json",
        "mappings/balance-to-ledger.yaml",
    }


def test_load_project_definition_accepts_inbound_file_csv_manifest() -> None:
    manifest = Path("tests/fixtures/file-contracts/csv-inbound/app-definition.yaml")

    definition = load_project_definition(manifest)

    assert definition.upstream_interfaces[0].type == "file-csv"
    assert {path.as_posix() for path in definition.referenced_paths()} == {
        "upstream/account-csv-layout.yaml",
        "upstream/account-csv-mapping.yaml",
        "upstream/sample-account-inbound.csv",
    }


def test_load_project_definition_accepts_downstream_file_csv_manifest() -> None:
    manifest = Path("tests/fixtures/file-contracts/csv-downstream/app-definition.yaml")

    definition = load_project_definition(manifest)

    assert definition.downstream_interfaces[0].type == "file-csv"
    assert {path.as_posix() for path in definition.referenced_paths()} == {
        "upstream/account-api-spec.yaml",
        "upstream/account-mapping.yaml",
        "upstream/create-account-request.json",
        "upstream/create-account-response.json",
        "downstream/account-csv-layout.yaml",
        "downstream/account-csv-mapping.yaml",
    }


def test_load_project_definition_accepts_enhanced_fixed_width_downstream_manifest() -> None:
    manifest = Path("tests/fixtures/file-contracts/fixed-width-downstream-record-types/app-definition.yaml")

    definition = load_project_definition(manifest)

    assert definition.downstream_interfaces[0].type == "file-fixed-width"
    assert {path.as_posix() for path in definition.referenced_paths()} == {
        "upstream/account-api-spec.yaml",
        "upstream/account-mapping.yaml",
        "upstream/create-account-request.json",
        "upstream/create-account-response.json",
        "downstream/account-eod-layout.yaml",
        "downstream/account-eod-mapping.yaml",
        "data-handoffs/account-staging-table.sql",
        "data-handoffs/account-staging-mapping.yaml",
    }


def test_load_project_definition_rejects_kafka_integration_without_kafka_config(
    tmp_path: Path,
) -> None:
    manifest = _write_kafka_manifest_variant(tmp_path, remove_keys=["kafka_config"])

    with pytest.raises(ValueError, match="kafka_config"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_kafka_integration_without_async_routes(
    tmp_path: Path,
) -> None:
    manifest = _write_kafka_manifest_variant(tmp_path, remove_keys=["async_routes"])

    with pytest.raises(ValueError, match="async_routes"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_request_reply_without_reply_topics(
    tmp_path: Path,
) -> None:
    payload = _kafka_manifest_payload()
    payload["async_routes"][0]["pattern"] = "request-reply"  # type: ignore[index]
    manifest = _write_manifest_payload(tmp_path, payload)

    with pytest.raises(ValueError, match=r"async_routes\.0.*required property"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_field_value_partition_key_without_source(
    tmp_path: Path,
) -> None:
    payload = _kafka_manifest_payload()
    partition_key = payload["async_routes"][0]["partition_key"]  # type: ignore[index]
    partition_key.pop("source")
    manifest = _write_manifest_payload(tmp_path, payload)

    with pytest.raises(ValueError, match=r"async_routes\.0\.partition_key.*source"):
        load_project_definition(manifest)


def test_transform_mapping_accepts_legacy_source_target_default_shape() -> None:
    mapping = TransformMapping(source="amount", target="paymentAmount", default="0")

    assert mapping.source == "amount"
    assert mapping.target == "paymentAmount"
    assert mapping.default == "0"
    assert mapping.constant is None
    assert mapping.value_map is None
    assert mapping.type_coercion is None


def test_transform_mapping_accepts_kafka_optional_transform_fields() -> None:
    mapping = TransformMapping(
        target="scheme",
        constant="KAFKA_BRIDGE",
        value_map={"INSTANT": "SCT_INST"},
        type_coercion="major_to_minor_units",
    )

    assert mapping.source is None
    assert mapping.constant == "KAFKA_BRIDGE"
    assert mapping.value_map == {"INSTANT": "SCT_INST"}
    assert mapping.type_coercion == "major_to_minor_units"


def test_transform_mapping_rejects_missing_source_constant_and_default() -> None:
    with pytest.raises(ValueError, match="source, constant, or default"):
        TransformMapping(target="paymentAmount")


def test_transform_mapping_rejects_unknown_type_coercion() -> None:
    with pytest.raises(ValueError, match="type_coercion"):
        TransformMapping(
            source="amount",
            target="amountMinorUnits",
            type_coercion="divide_by_pi",
        )


def test_load_project_definition_rejects_unknown_app_archetype(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "app_archetype: event-router",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="app_archetype"):
        load_project_definition(manifest)


def test_load_project_definition_normalizes_local_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    nested = tmp_path / "upstream"
    nested.mkdir()
    spec = nested / "spec.yaml"
    mapping = nested / "mapping.yaml"
    sample = nested / "sample.json"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    mapping.write_text("operations: []\n", encoding="utf-8")
    sample.write_text("{}\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: ./upstream/./spec.yaml",
                "    mapping: ./upstream/./mapping.yaml",
                "    samples:",
                "      - upstream/../upstream/sample.json",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    definition = load_project_definition(manifest)

    assert definition.upstream_interfaces[0].spec == "upstream/spec.yaml"
    assert definition.upstream_interfaces[0].mapping == "upstream/mapping.yaml"
    assert definition.upstream_interfaces[0].samples == ["upstream/sample.json"]


def test_load_project_definition_supports_explicit_operations(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    request_sample = tmp_path / "create-loan-request.json"
    request_sample.write_text('{"loanId": "L1"}\n', encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Loan Modernization",
                "bounded_context: loans",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-loan-api",
                "    system: CRM",
                "    type: rest-json",
                "    spec_url: https://example.com/loan-swagger.json",
                "    operations:",
                "      - name: createLoan",
                "        request_sample: create-loan-request.json",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    definition = load_project_definition(manifest)

    assert definition.upstream_interfaces[0].system == "CRM"
    assert definition.upstream_interfaces[0].operations[0].name == "createLoan"
    assert {path.as_posix() for path in definition.referenced_paths()} == {
        "create-loan-request.json",
    }


def test_load_project_definition_rejects_unknown_target_profile(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: does-not-exist",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown target_profile"):
        load_project_definition(manifest)


def test_load_project_definition_accepts_java17_enterprise_postgres_target_profile(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: springboot-enterprise-postgres-java17",
            ]
        ),
        encoding="utf-8",
    )

    definition = load_project_definition(manifest)

    assert definition.target_profile == "springboot-enterprise-postgres-java17"


def test_load_project_definition_rejects_both_spec_and_spec_url(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "    spec_url: https://example.com/swagger.json",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"upstream_interfaces\.0.*not (?:be )?valid"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_neither_spec_nor_spec_url(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"upstream_interfaces\.0.*not (?:be )?valid"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_empty_bounded_context(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.0.0\n", encoding="utf-8")
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: '   '",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: spec.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="bounded_context must not be empty"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_missing_referenced_file(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "upstream_interfaces:",
                "  - name: crm-api",
                "    type: rest-json",
                "    spec: missing.yaml",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="missing.yaml"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_missing_required_top_level_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "bounded_context: accounts",
                "schema_version: \"2.0\"",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="app_name"):
        load_project_definition(manifest)


def test_load_project_definition_rejects_empty_yaml_payload(tmp_path: Path) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="is empty"):
        load_project_definition(manifest)


def _kafka_manifest_payload() -> dict[str, object]:
    manifest = Path("tests/fixtures/kafka-integration/manifest.yaml")
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_kafka_manifest_variant(tmp_path: Path, *, remove_keys: list[str]) -> Path:
    payload = _kafka_manifest_payload()
    for key in remove_keys:
        payload.pop(key)
    return _write_manifest_payload(tmp_path, payload)


def _write_manifest_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return manifest
