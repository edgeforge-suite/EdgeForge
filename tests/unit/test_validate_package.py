from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from appbuilder.contracts import (
    load_project_definition,
    validate_package,
    validate_package_or_raise,
)


def test_validate_package_accepts_valid_minimal_crud_manifest() -> None:
    assert validate_package(_minimal_manifest()) == []


def test_validate_package_accepts_metadata_only_identity_role_without_policy() -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Posting",
                "field": "accountId",
                "role": "parent_reference",
                "mode": "metadata_only",
            }
        ]
    )

    assert validate_package(manifest) == []


def test_validate_package_accepts_metadata_only_identity_role_with_policy() -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Payment",
                "field": "idempotencyKey",
                "role": "idempotency_key",
                "mode": "metadata_only",
                "policy": {
                    "operations": ["createPayment"],
                    "replay_mode": "cached_response",
                    "retention_days": 30,
                    "storage": "db_table",
                },
            }
        ]
    )

    assert validate_package(manifest) == []


def test_validate_package_accepts_multiple_metadata_only_identity_roles() -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Posting",
                "field": "accountId",
                "role": "parent_reference",
                "mode": "metadata_only",
            },
            {
                "entity": "Posting",
                "field": "transactionId",
                "role": "event_id",
                "mode": "metadata_only",
            },
            {
                "entity": "Posting",
                "field": "correlationId",
                "role": "correlation_id",
                "mode": "metadata_only",
            },
        ]
    )

    assert validate_package(manifest) == []


def test_validate_package_rejects_identity_role_missing_mode() -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Posting",
                "field": "accountId",
                "role": "parent_reference",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("mode" in error for error in errors)


def test_validate_package_rejects_invalid_identity_role_mode() -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Posting",
                "field": "accountId",
                "role": "parent_reference",
                "mode": "enforced",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("enforced" in error for error in errors)


def test_validate_package_rejects_invalid_identity_role() -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Posting",
                "field": "accountId",
                "role": "routing_key",
                "mode": "metadata_only",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("routing_key" in error for error in errors)


def test_validate_package_rejects_persistence_id_identity_role_with_clear_message() -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Posting",
                "field": "postingId",
                "role": "persistence_id",
                "mode": "metadata_only",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("identity_overrides" in error for error in errors)


def test_validate_package_rejects_active_identity_role_without_policy() -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Payment",
                "field": "idempotencyKey",
                "role": "idempotency_key",
                "mode": "active",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("policy" in error and "active identity role" in error for error in errors)


def test_validate_package_rejects_active_identity_role_with_policy_as_unsupported() -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Payment",
                "field": "idempotencyKey",
                "role": "idempotency_key",
                "mode": "active",
                "policy": {
                    "operations": ["createPayment"],
                    "replay_mode": "cached_response",
                },
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("active identity role behavior is not supported yet" in error for error in errors)


def test_validate_package_rejects_identity_roles_for_passthrough_router() -> None:
    manifest = _minimal_manifest(
        app_archetype="passthrough-router",
        identity_roles=[
            {
                "entity": "Posting",
                "field": "accountId",
                "role": "parent_reference",
                "mode": "metadata_only",
            }
        ],
    )

    errors = validate_package(manifest)

    assert any("identity_roles" in error and "crud" in error for error in errors)


def test_validate_package_rejects_empty_identity_roles_for_passthrough_router() -> None:
    manifest = _minimal_manifest(
        app_archetype="passthrough-router",
        identity_roles=[],
    )

    errors = validate_package(manifest)

    assert any("identity_roles" in error and "crud" in error for error in errors)


def test_validate_package_rejects_identity_roles_for_kafka_integration() -> None:
    manifest = _kafka_manifest_payload()
    manifest["identity_roles"] = [
        {
            "entity": "Payment",
            "field": "correlationId",
            "role": "correlation_id",
            "mode": "metadata_only",
        }
    ]

    errors = validate_package(manifest)

    assert any("identity_roles" in error and "crud" in error for error in errors)


def test_validate_package_rejects_empty_identity_roles_for_kafka_integration() -> None:
    manifest = _kafka_manifest_payload()
    manifest["identity_roles"] = []

    errors = validate_package(manifest)

    assert any("identity_roles" in error and "crud" in error for error in errors)


def test_validate_package_reports_missing_schema_version() -> None:
    manifest = _minimal_manifest()
    manifest.pop("schema_version")

    errors = validate_package(manifest)

    assert any("schema_version" in error for error in errors)


def test_validate_package_reports_unknown_schema_version() -> None:
    manifest = _minimal_manifest(schema_version="1.0")

    errors = validate_package(manifest)

    assert any("schema_version" in error and "1.0" in error for error in errors)


def test_package_and_raw_schema_paths_report_the_same_unknown_nested_field(
    tmp_path: Path,
) -> None:
    manifest = _minimal_manifest(
        identity_roles=[
            {
                "entity": "Widget",
                "field": "widgetId",
                "role": "business_key",
                "mode": "metadata_only",
                "unexpected_nested_field": "rejected",
            }
        ],
    )
    raw_errors = validate_package(manifest)
    manifest_path = tmp_path / "app-definition.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    assert len(raw_errors) == 1
    assert raw_errors[0].startswith("identity_roles.0:")
    assert "unexpected_nested_field" in raw_errors[0]
    with pytest.raises(ValueError) as exc_info:
        load_project_definition(manifest_path)
    assert raw_errors[0] in str(exc_info.value)


def test_validate_package_reports_unknown_app_archetype() -> None:
    manifest = _minimal_manifest(app_archetype="event-router")

    errors = validate_package(manifest)

    assert any("event-router" in error for error in errors)


def test_validate_package_accepts_passthrough_router_as_reserved_schema_value() -> None:
    assert validate_package(_minimal_manifest(app_archetype="passthrough-router")) == []


def test_validate_package_accepts_kafka_integration_manifest() -> None:
    manifest = _kafka_manifest_payload()

    assert validate_package(manifest) == []


def test_validate_package_accepts_kafka_router_manifest() -> None:
    manifest = _router_manifest_payload()

    assert validate_package(manifest) == []


def test_validate_package_rejects_router_route_without_router_config() -> None:
    manifest = _router_manifest_payload()
    route = manifest["async_routes"][0]
    assert isinstance(route, dict)
    route.pop("router_config")

    errors = validate_package(manifest)

    assert any("router_config" in error for error in errors)


def test_validate_package_rejects_router_route_with_fixed_route_fields() -> None:
    manifest = _router_manifest_payload()
    route = manifest["async_routes"][0]
    assert isinstance(route, dict)
    route["upstream_topic"] = {
        "name": "abc.payments.request.v1",
        "system": "abc",
        "message_schema": "schemas/request.json",
    }

    errors = validate_package(manifest)

    assert any("upstream_topic" in error or "not" in error for error in errors)


def test_validate_package_rejects_router_routing_rule_with_invalid_operator() -> None:
    manifest = _router_manifest_payload()
    route = manifest["async_routes"][0]
    assert isinstance(route, dict)
    router_config = route["router_config"]
    assert isinstance(router_config, dict)
    routing_rules = router_config["routing_rules"]
    assert isinstance(routing_rules, dict)
    rules = routing_rules["rules"]
    assert isinstance(rules, list)
    rules[0]["conditions"][0]["operator"] = "definitely_not_supported"

    errors = validate_package(manifest)

    assert any("definitely_not_supported" in error for error in errors)


def test_validate_package_rejects_fixed_nack_mode_without_fixed_topic() -> None:
    manifest = _router_manifest_payload()
    route = manifest["async_routes"][0]
    assert isinstance(route, dict)
    router_config = route["router_config"]
    assert isinstance(router_config, dict)
    nack_routing = router_config["nack_routing"]
    assert isinstance(nack_routing, dict)
    nack_routing.pop("fixed_topic")

    errors = validate_package(manifest)

    assert any("fixed_topic" in error for error in errors)


def test_validate_package_rejects_per_source_system_nack_mode_without_map() -> None:
    manifest = _router_manifest_payload()
    route = manifest["async_routes"][0]
    assert isinstance(route, dict)
    router_config = route["router_config"]
    assert isinstance(router_config, dict)
    router_config["nack_routing"] = {
        "mode": "per_source_system",
        "per_source_system": {},
        "default_error_topic": "payment-router-error",
    }

    errors = validate_package(manifest)

    assert any("per_source_system" in error for error in errors)


def test_validate_package_requires_fixed_route_fields_for_non_router_route() -> None:
    manifest = _router_manifest_payload()
    route = manifest["async_routes"][0]
    assert isinstance(route, dict)
    route["pattern"] = "fire-and-forget"
    route.pop("router_config")

    errors = validate_package(manifest)

    assert any("upstream_topic" in error for error in errors)
    assert any("downstream_topic" in error for error in errors)
    assert any("transform_mapping" in error for error in errors)


def test_validate_package_accepts_request_reply_fixture_unchanged() -> None:
    manifest_path = Path("tests/fixtures/kafka-request-reply/manifest.yaml")
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    assert validate_package(payload) == []


def test_validate_package_requires_kafka_config_for_kafka_integration() -> None:
    manifest = _kafka_manifest_payload()
    manifest.pop("kafka_config")

    errors = validate_package(manifest)

    assert any("kafka_config" in error for error in errors)


def test_validate_package_requires_async_routes_for_kafka_integration() -> None:
    manifest = _kafka_manifest_payload()
    manifest.pop("async_routes")

    errors = validate_package(manifest)

    assert any("async_routes" in error for error in errors)


def test_validate_package_requires_reply_topics_for_request_reply_route() -> None:
    manifest = _kafka_manifest_payload()
    route = manifest["async_routes"][0]
    assert isinstance(route, dict)
    route["pattern"] = "request-reply"

    errors = validate_package(manifest)

    assert any("upstream_reply_topic" in error for error in errors)
    assert any("downstream_reply_topic" in error for error in errors)
    assert any("response_transform_mapping" in error for error in errors)


def test_validate_package_rejects_reply_topics_for_fire_and_forget_route() -> None:
    manifest = _kafka_manifest_payload()
    route = manifest["async_routes"][0]
    assert isinstance(route, dict)
    route["upstream_reply_topic"] = {
        "name": "abc.payments.response.v1",
        "message_schema": "schemas/upstream/payment-response.json",
    }

    errors = validate_package(manifest)

    assert any("fire-and-forget" in error or "not" in error for error in errors)


def test_validate_package_requires_source_for_field_value_partition_key() -> None:
    manifest = _kafka_manifest_payload()
    route = manifest["async_routes"][0]
    assert isinstance(route, dict)
    partition_key = route["partition_key"]
    assert isinstance(partition_key, dict)
    partition_key.pop("source")

    errors = validate_package(manifest)

    assert any("partition_key" in error and "source" in error for error in errors)


def test_validate_package_rejects_interface_definition_with_both_spec_and_spec_url() -> None:
    manifest = _minimal_manifest(
        upstream_interfaces=[
            {
                "name": "crm-api",
                "type": "rest-json",
                "spec": "upstream/spec.yaml",
                "spec_url": "https://example.com/spec.yaml",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("upstream_interfaces.0" in error for error in errors)


def test_validate_package_rejects_interface_definition_with_neither_spec_nor_spec_url() -> None:
    manifest = _minimal_manifest(
        upstream_interfaces=[
            {
                "name": "crm-api",
                "type": "rest-json",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("upstream_interfaces.0" in error for error in errors)


def test_validate_package_rejects_operation_without_samples() -> None:
    manifest = _minimal_manifest(
        upstream_interfaces=[
            {
                "name": "crm-api",
                "type": "rest-json",
                "spec": "upstream/spec.yaml",
                "operations": [{"name": "createAccount"}],
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("upstream_interfaces.0.operations.0" in error for error in errors)


def test_validate_package_rejects_file_contracts_under_data_handoffs() -> None:
    manifest = _minimal_manifest(
        data_handoffs=[
            {
                "name": "account-file",
                "type": "file-fixed-width",
                "spec": "downstream/account-layout.yaml",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("data_handoffs.0.type" in error for error in errors)


def test_validate_package_accepts_xml_xsd_interface_contract() -> None:
    manifest = _minimal_manifest(
        upstream_interfaces=[
            {
                "name": "account-xml",
                "type": "xml-xsd",
                "xsd_path": "contracts/account.xsd",
                "root_element": "AccountMessage",
                "namespace": "urn:example:account",
                "sample": "samples/account.xml",
            }
        ]
    )

    assert validate_package(manifest) == []


def test_validate_package_rejects_xml_xsd_missing_root_element() -> None:
    manifest = _minimal_manifest(
        upstream_interfaces=[
            {
                "name": "account-xml",
                "type": "xml-xsd",
                "xsd_path": "contracts/account.xsd",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("upstream_interfaces.0" in error and "root_element" in error for error in errors)


def test_validate_package_rejects_xml_xsd_under_data_handoffs() -> None:
    manifest = _minimal_manifest(
        data_handoffs=[
            {
                "name": "account-xml",
                "type": "xml-xsd",
                "spec": "contracts/account.xsd",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("data_handoffs.0.type" in error for error in errors)


def test_validate_package_accepts_soap_wsdl_interface_contract() -> None:
    manifest = _minimal_manifest(
        downstream_interfaces=[
            {
                "name": "customer-soap",
                "type": "soap-wsdl",
                "wsdl_path": "contracts/customer.wsdl",
                "service": "CustomerService",
                "port": "CustomerPort",
            }
        ]
    )

    assert validate_package(manifest) == []


def test_validate_package_rejects_soap_wsdl_missing_wsdl_reference() -> None:
    manifest = _minimal_manifest(
        upstream_interfaces=[
            {
                "name": "customer-soap",
                "type": "soap-wsdl",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("upstream_interfaces.0" in error for error in errors)


def test_validate_package_rejects_xml_namespace_fields_on_soap_wsdl() -> None:
    manifest = _minimal_manifest(
        upstream_interfaces=[
            {
                "name": "customer-soap",
                "type": "soap-wsdl",
                "wsdl_path": "contracts/customer.wsdl",
                "namespace": "urn:example:soap",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("upstream_interfaces.0" in error for error in errors)


def test_validate_package_rejects_soap_wsdl_under_data_handoffs() -> None:
    manifest = _minimal_manifest(
        data_handoffs=[
            {
                "name": "customer-soap",
                "type": "soap-wsdl",
                "spec": "contracts/customer.wsdl",
            }
        ]
    )

    errors = validate_package(manifest)

    assert any("data_handoffs.0.type" in error for error in errors)


def test_validate_package_or_raise_joins_schema_errors() -> None:
    manifest = _minimal_manifest(schema_version="1.0", app_archetype="event-router")

    with pytest.raises(ValueError) as excinfo:
        validate_package_or_raise(manifest)

    message = str(excinfo.value)
    assert "\n" in message
    assert "1.0" in message
    assert "event-router" in message


def _minimal_manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "app_name": "Sample",
        "bounded_context": "accounts",
        "schema_version": "2.0",
        "app_archetype": "crud",
        "target_profile": "springboot-legacy-compatible",
    }
    manifest.update(overrides)
    return manifest


def _kafka_manifest_payload() -> dict[str, object]:
    manifest_path = Path("tests/fixtures/kafka-integration/manifest.yaml")
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _router_manifest_payload() -> dict[str, object]:
    manifest_path = Path("tests/fixtures/kafka-router-contract/manifest.yaml")
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
