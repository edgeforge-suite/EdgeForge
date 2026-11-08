"""Translate kafka-integration manifests into Kafka generation metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from appbuilder.contracts import ProjectDefinition
from appbuilder.metadata.kafka_models import (
    DlqPolicy,
    KafkaMetadata,
    KafkaTransformMapping,
    MessageField,
    MessageSchema,
    ResolvedAsyncRoute,
    RetryPolicy,
    RouterCorrelationStoreMetadata,
    RouterExtractionMetadata,
    RouterNackRoutingMetadata,
    RouterPayloadLoggingMetadata,
    RouterRouteMetadata,
    RouterRoutingConditionMetadata,
    RouterRoutingFieldMetadata,
    RouterRoutingRuleMetadata,
    RouterSchemaRefMetadata,
    RouterTargetMetadata,
    RouterTargetRetryMetadata,
    RouterTimeoutMetadata,
    RouterTransformRefMetadata,
    RouterUpstreamTopicMetadata,
)
from appbuilder.target_profiles.catalog import TARGET_PROFILES


def translate_kafka_project(
    definition: ProjectDefinition,
    project_root: Path,
) -> KafkaMetadata:
    """Translate a loaded kafka-integration manifest into emitter-ready metadata."""

    if definition.kafka_config is None:
        raise ValueError("kafka-integration manifests require kafka_config")
    if not definition.async_routes:
        raise ValueError("kafka-integration manifests require at least one async_routes entry")

    target_profile = TARGET_PROFILES[definition.target_profile]
    routes: list[ResolvedAsyncRoute] = []
    router_routes: list[RouterRouteMetadata] = []
    for route in definition.async_routes:
        if route.pattern == "router":
            if router_routes:
                raise ValueError(
                    "kafka-integration router request-path generation currently supports "
                    "at most one router route"
                )
            router_routes.append(translate_router_route(route, project_root=project_root))
            continue

        route_class_prefix = _to_pascal_case(route.name)
        if (
            route.upstream_topic is None
            or route.downstream_topic is None
            or route.transform_mapping is None
        ):
            raise ValueError(
                f"{route.pattern} route '{route.name}' requires upstream_topic, "
                "downstream_topic, and transform_mapping"
            )
        upstream_schema = _load_message_schema(
            project_root / route.upstream_topic.message_schema,
            package_suffix="inbound",
        )
        downstream_schema = _load_message_schema(
            project_root / route.downstream_topic.message_schema,
            package_suffix="outbound",
        )
        transform_mappings = _load_transform_mappings(project_root / route.transform_mapping)
        partition_key = route.partition_key
        downstream_reply_message = None
        upstream_reply_message = None
        response_transform_mappings = None
        upstream_reply_topic_name = None
        downstream_reply_topic_name = None
        correlation_id_source = None
        correlation_id_field_name = None
        reply_timeout_ms = route.reply_timeout_ms
        if route.pattern == "request-reply":
            if route.downstream_reply_topic is None or route.upstream_reply_topic is None:
                raise ValueError(
                    f"request-reply route '{route.name}' requires reply topic definitions"
                )
            if route.response_transform_mapping is None:
                raise ValueError(
                    f"request-reply route '{route.name}' requires response_transform_mapping"
                )
            downstream_reply_message = _load_message_schema(
                project_root / route.downstream_reply_topic.message_schema,
                package_suffix="reply/downstream",
            )
            upstream_reply_message = _load_message_schema(
                project_root / route.upstream_reply_topic.message_schema,
                package_suffix="reply/upstream",
            )
            response_transform_mappings = _load_transform_mappings(
                project_root / route.response_transform_mapping
            )
            upstream_reply_topic_name = route.upstream_reply_topic.name
            downstream_reply_topic_name = route.downstream_reply_topic.name
            correlation_id_source = (
                route.correlation_id.source if route.correlation_id is not None else "header"
            )
            correlation_id_field_name = (
                route.correlation_id.field_name
                if route.correlation_id is not None
                else "correlationId"
            )
        routes.append(
            ResolvedAsyncRoute(
                name=route.name,
                route_class_prefix=route_class_prefix,
                pattern=route.pattern,
                upstream_topic_name=route.upstream_topic.name,
                downstream_topic_name=route.downstream_topic.name,
                upstream_message=upstream_schema,
                downstream_message=downstream_schema,
                transform_mappings=transform_mappings,
                partition_key_strategy=(
                    partition_key.strategy if partition_key is not None else "round_robin"
                ),
                partition_key_source=(
                    partition_key.source if partition_key is not None else None
                ),
                upstream_reply_topic_name=upstream_reply_topic_name,
                downstream_reply_topic_name=downstream_reply_topic_name,
                downstream_reply_message=downstream_reply_message,
                upstream_reply_message=upstream_reply_message,
                response_transform_mappings=response_transform_mappings,
                correlation_id_source=correlation_id_source,
                correlation_id_field_name=correlation_id_field_name,
                reply_timeout_ms=reply_timeout_ms,
            )
        )

    retry_policy = None
    dlq_policy = None
    if definition.kafka_config.retry is not None:
        retry = definition.kafka_config.retry
        retry_policy = RetryPolicy(
            max_attempts=retry.max_attempts,
            backoff_ms=retry.backoff_ms,
            backoff_multiplier=retry.backoff_multiplier,
        )
    if definition.kafka_config.dlq is not None and definition.kafka_config.dlq.enabled:
        dlq_policy = DlqPolicy(
            enabled=True,
            topic_suffix=definition.kafka_config.dlq.topic_suffix,
        )

    return KafkaMetadata(
        app_name=definition.app_name,
        bounded_context=definition.bounded_context,
        schema_version=definition.schema_version,
        java_package="com.appbuilder." + _to_package_suffix(definition.bounded_context),
        artifact_id=_to_artifact_id(definition.app_name),
        consumer_group=definition.kafka_config.consumer_group,
        concurrency=definition.kafka_config.concurrency,
        routes=routes,
        target_profile_name=target_profile.name,
        java_version=target_profile.java_baseline or "17",
        spring_boot_version=target_profile.spring_boot_baseline or "3.3.5",
        retry_policy=retry_policy,
        dlq_policy=dlq_policy,
        router_routes=router_routes,
    )


def _load_message_schema(path: Path, *, package_suffix: str) -> MessageSchema:
    if not path.exists():
        raise FileNotFoundError(f"Kafka message schema not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Kafka message schema '{path}' must contain a JSON object")
    properties = payload.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError(f"Kafka message schema '{path}' properties must be an object")
    fields = [
        MessageField(name=str(name), java_type=_json_schema_to_java_type(schema))
        for name, schema in properties.items()
    ]
    return MessageSchema(
        class_name=_to_pascal_case(path.stem),
        package_suffix=package_suffix,
        fields=fields,
    )


def _json_schema_to_java_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "String"
    field_type = schema.get("type")
    field_format = schema.get("format")
    if field_type == "string" and field_format == "date":
        return "LocalDate"
    if field_type == "string" and field_format == "date-time":
        return "OffsetDateTime"
    if field_type == "string":
        return "String"
    if field_type == "integer":
        return "Long"
    if field_type == "number":
        return "BigDecimal"
    if field_type == "boolean":
        return "Boolean"
    return "String"


def _load_transform_mappings(path: Path) -> list[KafkaTransformMapping]:
    if not path.exists():
        raise FileNotFoundError(f"Kafka transform mapping not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Kafka transform mapping '{path}' must contain a YAML mapping")
    transforms = payload.get("transforms", [])
    if not isinstance(transforms, list):
        raise ValueError(f"'transforms' in '{path}' must be a list")
    return [
        KafkaTransformMapping(
            source=None if entry.get("source") is None else str(entry.get("source")),
            target=str(entry["target"]),
            default=None if entry.get("default") is None else str(entry.get("default")),
            constant=None if entry.get("constant") is None else str(entry.get("constant")),
            value_map=(
                {str(key): str(value) for key, value in entry["value_map"].items()}
                if isinstance(entry.get("value_map"), dict)
                else None
            ),
            type_coercion=(
                None if entry.get("type_coercion") is None else str(entry.get("type_coercion"))
            ),
        )
        for entry in transforms
    ]


def translate_router_route(route: Any, *, project_root: Path) -> RouterRouteMetadata:
    """Translate a validated router async route into router-specific metadata.

    This helper intentionally stays separate from translate_kafka_project() until
    the router runtime path is enabled.
    """

    _validate_router_route(route, project_root=project_root)
    router_config = route.router_config
    if router_config is None:
        raise ValueError(f"router route '{route.name}' requires router_config")

    return RouterRouteMetadata(
        name=route.name,
        route_class_prefix=_to_pascal_case(route.name),
        upstream_topics=[
            RouterUpstreamTopicMetadata(
                id=topic.id,
                name=topic.name,
                consumer_group=topic.consumer_group,
                source_system_extraction=_router_extraction_metadata(
                    topic.source_system_extraction
                ),
                reply_destination_extraction=_router_extraction_metadata(
                    topic.reply_destination_extraction
                ),
            )
            for topic in router_config.upstream_topics
        ],
        inbound_schema=_router_schema_ref_metadata(router_config.inbound_schema, project_root),
        routing_fields=[
            RouterRoutingFieldMetadata(name=field.name, json_path=field.json_path)
            for field in router_config.routing_rules.routing_fields
        ],
        routing_rules=[
            RouterRoutingRuleMetadata(
                id=rule.id,
                conditions=[
                    RouterRoutingConditionMetadata(
                        field=condition.field,
                        operator=condition.operator,
                        value=condition.value,
                    )
                    for condition in rule.conditions
                ],
                target=rule.target,
            )
            for rule in router_config.routing_rules.rules
        ],
        default_target=router_config.routing_rules.default_target,
        duplicate_correlation_policy=router_config.duplicate_correlation_policy,
        targets=[
            RouterTargetMetadata(
                id=target.id,
                request_topic=target.request_topic,
                response_topic=target.response_topic,
                request_schema=_router_schema_ref_metadata(target.request_schema, project_root),
                response_schema=_router_schema_ref_metadata(target.response_schema, project_root),
                request_transform=RouterTransformRefMetadata(
                    file=target.request_transform.file,
                    mappings=_load_transform_mappings(project_root / target.request_transform.file),
                ),
                response_transform=RouterTransformRefMetadata(
                    file=target.response_transform.file,
                    mappings=_load_transform_mappings(project_root / target.response_transform.file),
                ),
                retry=(
                    None
                    if target.retry is None
                    else RouterTargetRetryMetadata(
                        max_attempts=target.retry.max_attempts,
                        backoff_ms=target.retry.backoff_ms,
                        dlq_topic=target.retry.dlq_topic,
                    )
                ),
                timeout_ms=target.timeout_ms,
            )
            for target in router_config.targets
        ],
        outbound_schema=_router_schema_ref_metadata(router_config.outbound_schema, project_root),
        nack_routing=RouterNackRoutingMetadata(
            mode=router_config.nack_routing.mode,
            per_source_system=dict(router_config.nack_routing.per_source_system),
            fixed_topic=router_config.nack_routing.fixed_topic,
            default_error_topic=router_config.nack_routing.default_error_topic,
        ),
        timeout=(
            RouterTimeoutMetadata()
            if router_config.timeout is None
            else RouterTimeoutMetadata(
                behavior_with_known_reply=router_config.timeout.behavior_with_known_reply,
                behavior_without_reply=router_config.timeout.behavior_without_reply,
            )
        ),
        payload_logging=RouterPayloadLoggingMetadata(
            policy=router_config.payload_logging.policy,
            capped_raw_bytes=router_config.payload_logging.capped_raw_bytes,
        ),
        correlation_store=RouterCorrelationStoreMetadata(
            type=router_config.correlation_store.type,
            timeout_ms=router_config.correlation_store.timeout_ms,
            eviction_interval_ms=router_config.correlation_store.eviction_interval_ms,
        ),
    )


def _router_extraction_metadata(extraction: Any) -> RouterExtractionMetadata:
    return RouterExtractionMetadata(
        mode=extraction.mode,
        header_key=extraction.header_key,
        body_field_path=extraction.body_field_path,
    )


def _router_schema_ref_metadata(schema_ref: Any, project_root: Path) -> RouterSchemaRefMetadata:
    return RouterSchemaRefMetadata(
        file=schema_ref.file,
        validation_policy=schema_ref.validation_policy,
        failure_behavior=schema_ref.failure_behavior,
        content=_load_json_schema(project_root / schema_ref.file),
    )


def _validate_router_route(route: Any, *, project_root: Path) -> None:
    router_config = route.router_config
    if router_config is None:
        raise ValueError(f"router route '{route.name}' requires router_config")

    targets = {target.id: target for target in router_config.targets}
    for rule in router_config.routing_rules.rules:
        if rule.target not in targets:
            raise ValueError(
                f"router route '{route.name}' routing rule '{rule.id}' references "
                f"unknown target '{rule.target}'. Known targets: {sorted(targets)}"
            )
    default_target = router_config.routing_rules.default_target
    if default_target is not None and default_target not in targets:
        raise ValueError(
            f"router route '{route.name}' default_target '{default_target}' is not "
            f"declared in router_config.targets. Known targets: {sorted(targets)}"
        )

    inbound_schema = _load_json_schema(project_root / router_config.inbound_schema.file)
    _validate_router_routing_rules(
        route_name=route.name,
        router_config=router_config,
        inbound_schema=inbound_schema,
    )
    outbound_schema = _load_json_schema(project_root / router_config.outbound_schema.file)
    for target in router_config.targets:
        request_schema = _load_json_schema(project_root / target.request_schema.file)
        response_schema = _load_json_schema(project_root / target.response_schema.file)
        _validate_router_transform(
            transform_path=project_root / target.request_transform.file,
            source_schema=inbound_schema,
            target_schema=request_schema,
        )
        _validate_router_transform(
            transform_path=project_root / target.response_transform.file,
            source_schema=response_schema,
            target_schema=outbound_schema,
        )


def _validate_router_routing_rules(
    *,
    route_name: str,
    router_config: Any,
    inbound_schema: dict[str, Any],
) -> None:
    inbound_fields = _schema_field_lookup(inbound_schema)
    routing_fields = {
        field.name: _normalize_json_field_path(field.json_path)
        for field in router_config.routing_rules.routing_fields
    }
    for field_name, schema_field_name in routing_fields.items():
        if schema_field_name not in inbound_fields:
            raise ValueError(
                f"router route '{route_name}' routing field '{field_name}' json_path "
                f"'{schema_field_name}' is not declared in the inbound schema"
            )

    allowed_operators = {"eq", "in", "lt", "lte", "gt", "gte", "not_null"}
    for rule in router_config.routing_rules.rules:
        for condition in rule.conditions:
            if condition.field not in routing_fields:
                raise ValueError(
                    f"router route '{route_name}' routing rule '{rule.id}' condition "
                    f"references undeclared routing field '{condition.field}'"
                )
            if condition.operator not in allowed_operators:
                raise ValueError(
                    f"router route '{route_name}' routing rule '{rule.id}' condition "
                    f"uses unsupported operator '{condition.operator}'. Supported "
                    f"operators: {sorted(allowed_operators)}"
                )


def _load_json_schema(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Kafka router schema not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Kafka router schema '{path}' must contain a JSON object")
    return payload


def _validate_router_transform(
    *,
    transform_path: Path,
    source_schema: dict[str, Any],
    target_schema: dict[str, Any],
) -> None:
    if not transform_path.exists():
        raise FileNotFoundError(f"Kafka router transform mapping not found: {transform_path}")
    payload = yaml.safe_load(transform_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Kafka router transform mapping '{transform_path}' must be a YAML mapping")
    transforms = payload.get("transforms", [])
    if not isinstance(transforms, list):
        raise ValueError(f"'transforms' in '{transform_path}' must be a list")

    source_fields = _schema_field_lookup(source_schema)
    target_fields = _schema_field_lookup(target_schema)
    covered_targets: set[str] = set()
    for index, entry in enumerate(transforms):
        if not isinstance(entry, dict):
            raise ValueError(
                f"{transform_path}: mapping #{index} must be a mapping with a target field"
            )
        raw_target = entry.get("target")
        if raw_target is None:
            raise ValueError(f"{transform_path}: mapping #{index} missing target")
        target_name = _normalize_json_field_path(str(raw_target))
        if target_name not in target_fields:
            raise ValueError(
                f"{transform_path}: mapping #{index} target field '{target_name}' "
                "is not declared in the target schema"
            )
        covered_targets.add(target_name)

        raw_source = entry.get("source")
        if raw_source is None:
            if entry.get("constant") is None and entry.get("default") is None:
                raise ValueError(
                    f"{transform_path}: mapping #{index} target field '{target_name}' "
                    "requires source, constant, or default"
                )
            continue
        source_name = _normalize_json_field_path(str(raw_source))
        if source_name not in source_fields:
            raise ValueError(
                f"{transform_path}: mapping #{index} source field '{source_name}' "
                "is not declared in the source schema"
            )
        _validate_router_type_compatibility(
            transform_path=transform_path,
            index=index,
            source_name=source_name,
            source_schema=source_fields[source_name],
            target_name=target_name,
            target_schema=target_fields[target_name],
            mapping=entry,
        )

    required_targets = target_schema.get("required", [])
    if not isinstance(required_targets, list):
        required_targets = []
    for required_target in required_targets:
        target_name = str(required_target)
        if target_name not in covered_targets:
            raise ValueError(
                f"{transform_path}: required target field '{target_name}' is not "
                "mapped, defaulted, or constanted"
            )


def _schema_field_lookup(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("Kafka router JSON Schema properties must be an object")
    return {
        str(name): field_schema
        for name, field_schema in properties.items()
        if isinstance(field_schema, dict)
    }


def _normalize_json_field_path(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("$."):
        normalized = normalized[2:]
    elif normalized.startswith("$"):
        normalized = normalized[1:]
    return normalized.lstrip(".")


def _validate_router_type_compatibility(
    *,
    transform_path: Path,
    index: int,
    source_name: str,
    source_schema: dict[str, Any],
    target_name: str,
    target_schema: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    source_type = source_schema.get("type", "string")
    target_type = target_schema.get("type", "string")
    if mapping.get("value_map") is not None:
        _validate_router_value_map_coverage(
            transform_path=transform_path,
            index=index,
            source_name=source_name,
            source_schema=source_schema,
            mapping=mapping,
        )
        return
    if source_type == target_type:
        return
    if target_type == "string" and source_type in {"string", "integer", "number", "boolean"}:
        return
    if mapping.get("type_coercion") is not None and source_type in {"integer", "number"} and target_type in {
        "integer",
        "number",
    }:
        return
    raise ValueError(
        f"{transform_path}: mapping #{index} cannot map source field '{source_name}' "
        f"({source_type}) to target field '{target_name}' ({target_type}) without "
        "a supported value_map, default, constant, or type_coercion"
    )


def _validate_router_value_map_coverage(
    *,
    transform_path: Path,
    index: int,
    source_name: str,
    source_schema: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    value_map = mapping.get("value_map")
    if not isinstance(value_map, dict):
        raise ValueError(f"{transform_path}: mapping #{index} value_map must be an object")
    if mapping.get("default") is not None:
        return
    enum_values = source_schema.get("enum")
    if not isinstance(enum_values, list):
        return
    missing = [str(value) for value in enum_values if str(value) not in value_map]
    if missing:
        raise ValueError(
            f"{transform_path}: mapping #{index} value_map for source field "
            f"'{source_name}' is missing enum values: {missing}"
        )


def _to_pascal_case(value: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", value)
    return "".join(part[:1].upper() + part[1:] for part in parts if part) or "Message"


def _to_package_suffix(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return normalized or "generated"


def _to_artifact_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return normalized or "generated-app"
