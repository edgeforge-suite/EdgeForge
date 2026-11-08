import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from appbuilder.contracts import load_project_definition
from appbuilder.metadata.kafka_models import KafkaTransformMapping
from appbuilder.metadata.kafka_translation import (
    _json_schema_to_java_type,
    translate_kafka_project,
)
from appbuilder.metadata.translation import build_metadata_project

_ROUTER_FIXTURE = Path("tests/fixtures/kafka-router-contract")


def test_translate_kafka_project_produces_metadata_from_fixture() -> None:
    manifest = Path("tests/fixtures/kafka-integration/manifest.yaml")
    definition = load_project_definition(manifest)

    metadata = translate_kafka_project(definition, project_root=manifest.parent)

    assert metadata.consumer_group == "payment-mediation-group"
    assert metadata.concurrency == 1
    assert metadata.java_package == "com.appbuilder.payment_mediation"
    assert metadata.artifact_id == "payment-mediation-adapter"
    assert len(metadata.routes) == 2
    route = metadata.routes[0]
    assert route.name == "payment-initiated"
    assert route.route_class_prefix == "PaymentInitiated"
    assert route.upstream_topic_name == "abc.payments.initiated.v1"
    assert route.downstream_topic_name == "xyz.settlement.request.v1"
    assert any(
        field.name == "amount" and field.java_type == "BigDecimal"
        for field in route.upstream_message.fields
    )
    assert any(
        field.name == "paymentId" and field.java_type == "String"
        for field in route.upstream_message.fields
    )
    assert len(route.transform_mappings) >= 2


def test_translate_kafka_project_maps_json_schema_types_correctly() -> None:
    assert _json_schema_to_java_type({"type": "string"}) == "String"
    assert _json_schema_to_java_type({"type": "number"}) == "BigDecimal"
    assert _json_schema_to_java_type({"type": "integer"}) == "Long"
    assert _json_schema_to_java_type({"type": "boolean"}) == "Boolean"
    assert _json_schema_to_java_type({"type": "string", "format": "date"}) == "LocalDate"
    assert (
        _json_schema_to_java_type({"type": "string", "format": "date-time"})
        == "OffsetDateTime"
    )
    assert _json_schema_to_java_type({"type": "array"}) == "String"


def test_translate_kafka_project_raises_on_missing_schema_file(tmp_path: Path) -> None:
    manifest = Path("tests/fixtures/kafka-integration/manifest.yaml")
    definition = load_project_definition(manifest).model_copy(deep=True)
    assert definition.async_routes is not None
    definition.async_routes[0].upstream_topic.message_schema = "schemas/missing.json"

    with pytest.raises(FileNotFoundError, match="missing.json"):
        translate_kafka_project(definition, project_root=tmp_path)


def test_kafka_transform_mapping_requires_source_constant_or_default() -> None:
    with pytest.raises(ValueError, match="source, constant, or default"):
        KafkaTransformMapping(target="settlementAmount")


def test_kafka_transform_mapping_rejects_unknown_type_coercion() -> None:
    with pytest.raises(ValueError, match="type_coercion"):
        KafkaTransformMapping(
            source="amount",
            target="settlementAmount",
            type_coercion="round_somehow",
        )


def test_translate_request_reply_route_produces_reply_fields() -> None:
    manifest = Path("tests/fixtures/kafka-request-reply/manifest.yaml")
    definition = load_project_definition(manifest)

    metadata = translate_kafka_project(definition, project_root=manifest.parent)

    route = metadata.routes[0]
    assert route.pattern == "request-reply"
    assert route.upstream_reply_topic_name == "payments.verification.reply.v1"
    assert route.downstream_reply_topic_name == "core.account.verify.reply.v1"
    assert route.correlation_id_source == "header"
    assert route.correlation_id_field_name == "X-Correlation-ID"
    assert route.reply_timeout_ms == 5000
    assert route.downstream_reply_message is not None
    assert route.upstream_reply_message is not None
    assert route.response_transform_mappings is not None
    assert len(route.response_transform_mappings) >= 2


def test_translate_fire_and_forget_route_has_no_reply_fields() -> None:
    manifest = Path("tests/fixtures/kafka-integration/manifest.yaml")
    definition = load_project_definition(manifest)

    metadata = translate_kafka_project(definition, project_root=manifest.parent)

    for route in metadata.routes:
        assert route.upstream_reply_topic_name is None
        assert route.downstream_reply_topic_name is None
        assert route.downstream_reply_message is None
        assert route.upstream_reply_message is None
        assert route.response_transform_mappings is None
        assert route.correlation_id_source is None
        assert route.correlation_id_field_name is None


def test_router_referenced_paths_include_schema_and_transform_refs() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")

    referenced = {path.as_posix() for path in definition.referenced_paths()}

    assert {
        "schemas/ro-request.json",
        "schemas/ro-response.json",
        "schemas/d1-request.json",
        "schemas/d1-response.json",
        "transforms/ro-to-d1-request.yaml",
        "transforms/d1-to-ro-response.yaml",
    }.issubset(referenced)


def test_translate_router_route_returns_router_metadata() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")

    metadata = translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)

    assert metadata.routes == []
    assert len(metadata.router_routes) == 1
    assert metadata.router_routes[0].name == "payment_router"


def test_generation_metadata_step_for_router_returns_metadata() -> None:
    metadata = build_metadata_project(_ROUTER_FIXTURE / "manifest.yaml")

    assert metadata.app_archetype.value == "kafka-integration"
    assert len(metadata.router_routes) == 1


def test_translate_router_route_rejects_missing_rule_target_id() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    assert definition.async_routes is not None
    route = definition.async_routes[0]
    assert route.router_config is not None
    route.router_config.routing_rules.rules[0].target = "missing_target"

    with pytest.raises(ValueError, match="unknown target 'missing_target'"):
        translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)


def test_translate_router_route_rejects_invalid_default_target() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    assert definition.async_routes is not None
    route = definition.async_routes[0]
    assert route.router_config is not None
    route.router_config.routing_rules.default_target = "missing_default"

    with pytest.raises(ValueError, match="default_target 'missing_default'"):
        translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)


def test_translate_router_route_rejects_routing_field_path_not_in_inbound_schema() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    assert definition.async_routes is not None
    route = definition.async_routes[0]
    assert route.router_config is not None
    route.router_config.routing_rules.routing_fields[0].json_path = "$.missingField"

    with pytest.raises(ValueError, match="routing field 'country'.*inbound schema"):
        translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)


def test_translate_router_route_rejects_condition_field_not_declared() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    assert definition.async_routes is not None
    route = definition.async_routes[0]
    assert route.router_config is not None
    route.router_config.routing_rules.rules[0].conditions[0].field = "not_declared"

    with pytest.raises(ValueError, match="undeclared routing field 'not_declared'"):
        translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)


def test_translate_router_route_rejects_unsupported_condition_operator() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    assert definition.async_routes is not None
    route = definition.async_routes[0]
    assert route.router_config is not None
    route.router_config.routing_rules.rules[0].conditions[0].operator = (
        "definitely_not_supported"
    )

    with pytest.raises(ValueError, match="unsupported operator 'definitely_not_supported'"):
        translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)


def test_load_router_manifest_rejects_empty_upstream_topics(tmp_path: Path) -> None:
    fixture = _copy_router_fixture(tmp_path)
    manifest_path = fixture / "manifest.yaml"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["async_routes"][0]["router_config"]["upstream_topics"] = []
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"async_routes\.0\.router_config\.upstream_topics.*non-empty",
    ):
        load_project_definition(manifest_path)


def test_load_router_manifest_rejects_empty_targets(tmp_path: Path) -> None:
    fixture = _copy_router_fixture(tmp_path)
    manifest_path = fixture / "manifest.yaml"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["async_routes"][0]["router_config"]["targets"] = []
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"async_routes\.0\.router_config\.targets.*non-empty",
    ):
        load_project_definition(manifest_path)


def test_load_router_manifest_rejects_fixed_nack_mode_without_fixed_topic(
    tmp_path: Path,
) -> None:
    fixture = _copy_router_fixture(tmp_path)
    manifest_path = fixture / "manifest.yaml"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["async_routes"][0]["router_config"]["nack_routing"].pop("fixed_topic")
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"async_routes\.0\.router_config\.nack_routing.*fixed_topic",
    ):
        load_project_definition(manifest_path)


def test_load_router_manifest_rejects_per_source_system_nack_mode_without_map(
    tmp_path: Path,
) -> None:
    fixture = _copy_router_fixture(tmp_path)
    manifest_path = fixture / "manifest.yaml"
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    payload["async_routes"][0]["router_config"]["nack_routing"] = {
        "mode": "per_source_system",
        "per_source_system": {},
        "default_error_topic": "payment-router-error",
    }
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            r"async_routes\.0\.router_config\.nack_routing\.per_source_system"
            r".*non-empty"
        ),
    ):
        load_project_definition(manifest_path)


def test_translate_router_route_rejects_missing_schema_file() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    assert definition.async_routes is not None
    route = definition.async_routes[0]
    assert route.router_config is not None
    route.router_config.targets[0].request_schema.file = "schemas/missing-request.json"

    with pytest.raises(FileNotFoundError, match="missing-request.json"):
        translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)


def test_translate_router_route_rejects_missing_transform_file() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    assert definition.async_routes is not None
    route = definition.async_routes[0]
    assert route.router_config is not None
    route.router_config.targets[0].request_transform.file = "transforms/missing-transform.yaml"

    with pytest.raises(FileNotFoundError, match="missing-transform.yaml"):
        translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)


def test_translate_router_route_rejects_missing_required_target_field(tmp_path: Path) -> None:
    fixture = _copy_router_fixture(tmp_path)
    transform_path = fixture / "transforms/ro-to-d1-request.yaml"
    payload = yaml.safe_load(transform_path.read_text(encoding="utf-8"))
    payload["transforms"] = [
        transform for transform in payload["transforms"]
        if transform["target"] != "decisionCode"
    ]
    transform_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    definition = load_project_definition(fixture / "manifest.yaml")

    with pytest.raises(ValueError, match="required target field 'decisionCode'"):
        translate_kafka_project(definition, project_root=fixture)


def test_translate_router_route_rejects_value_map_gap(tmp_path: Path) -> None:
    fixture = _copy_router_fixture(tmp_path)
    transform_path = fixture / "transforms/ro-to-d1-request.yaml"
    payload = yaml.safe_load(transform_path.read_text(encoding="utf-8"))
    payload["transforms"][2]["value_map"].pop("DECLINED")
    transform_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    definition = load_project_definition(fixture / "manifest.yaml")

    with pytest.raises(ValueError, match="missing enum values"):
        translate_kafka_project(definition, project_root=fixture)


def test_translate_kafka_project_with_retry_policy() -> None:
    manifest = Path("tests/fixtures/kafka-retry-dlq/manifest.yaml")
    definition = load_project_definition(manifest)

    metadata = translate_kafka_project(definition, project_root=manifest.parent)

    assert metadata.retry_policy is not None
    assert metadata.retry_policy.max_attempts == 3
    assert metadata.retry_policy.backoff_ms == 500
    assert metadata.retry_policy.backoff_multiplier == 2.0


def test_translate_kafka_project_with_dlq_policy() -> None:
    manifest = Path("tests/fixtures/kafka-retry-dlq/manifest.yaml")
    definition = load_project_definition(manifest)

    metadata = translate_kafka_project(definition, project_root=manifest.parent)

    assert metadata.dlq_policy is not None
    assert metadata.dlq_policy.enabled is True
    assert metadata.dlq_policy.topic_suffix == ".dlq"


def test_translate_kafka_project_no_retry_gives_none_policy() -> None:
    manifest = Path("tests/fixtures/kafka-integration/manifest.yaml")
    definition = load_project_definition(manifest)

    metadata = translate_kafka_project(definition, project_root=manifest.parent)

    assert metadata.retry_policy is None
    assert metadata.dlq_policy is None


def test_retry_config_definition_rejects_out_of_range_max_attempts() -> None:
    from appbuilder.contracts.manifest import RetryConfigDefinition

    with pytest.raises(ValidationError):
        RetryConfigDefinition(max_attempts=11)


def test_dlq_config_definition_rejects_suffix_without_dot() -> None:
    from appbuilder.contracts.manifest import DlqConfigDefinition

    with pytest.raises(ValidationError):
        DlqConfigDefinition(topic_suffix="dlq")


def _copy_router_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "kafka-router-contract"
    shutil.copytree(_ROUTER_FIXTURE, destination)
    return destination
