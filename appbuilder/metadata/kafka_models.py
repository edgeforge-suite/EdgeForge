"""Kafka integration metadata models.

These models support the PR 2 manifest/metadata contract only. Translation and
generation use them in later Kafka implementation slices.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from appbuilder.core import CURRENT_MANIFEST_SCHEMA_VERSION, AppArchetype


class KafkaTopicDef(BaseModel):
    name: str
    system: str
    message_schema: str
    sample: str | None = None


class CorrelationIdConfig(BaseModel):
    source: str = "header"
    field_name: str = "correlationId"


class PartitionKeyConfig(BaseModel):
    strategy: str = "round_robin"
    source: str | None = None


class AsyncRoute(BaseModel):
    name: str
    pattern: str
    upstream_topic: KafkaTopicDef
    downstream_topic: KafkaTopicDef
    transform_mapping: str
    upstream_reply_topic: KafkaTopicDef | None = None
    downstream_reply_topic: KafkaTopicDef | None = None
    response_transform_mapping: str | None = None
    correlation_id: CorrelationIdConfig | None = None
    partition_key: PartitionKeyConfig | None = None
    reply_timeout_ms: int = 30000


class KafkaConfig(BaseModel):
    consumer_group: str
    concurrency: int = 1


class MessageField(BaseModel):
    name: str
    java_type: str


class MessageSchema(BaseModel):
    class_name: str
    package_suffix: str
    fields: list[MessageField]


class KafkaTransformMapping(BaseModel):
    source: str | None = None
    target: str
    default: str | None = None
    constant: str | None = None
    value_map: dict[str, str] | None = None
    type_coercion: str | None = None

    @model_validator(mode="after")
    def validate_transform_input(self) -> KafkaTransformMapping:
        if self.source is None and self.constant is None and self.default is None:
            raise ValueError(
                "KafkaTransformMapping requires at least one of source, constant, or default"
            )
        if self.type_coercion is not None and self.type_coercion not in {
            "major_to_minor_units",
            "minor_to_major_units",
        }:
            raise ValueError(
                "KafkaTransformMapping type_coercion must be one of "
                "major_to_minor_units or minor_to_major_units"
            )
        return self


class ResolvedAsyncRoute(BaseModel):
    name: str
    route_class_prefix: str
    pattern: str
    upstream_topic_name: str
    downstream_topic_name: str
    upstream_message: MessageSchema
    downstream_message: MessageSchema
    transform_mappings: list[KafkaTransformMapping]
    partition_key_strategy: str
    partition_key_source: str | None = None
    upstream_reply_topic_name: str | None = None
    downstream_reply_topic_name: str | None = None
    downstream_reply_message: MessageSchema | None = None
    upstream_reply_message: MessageSchema | None = None
    response_transform_mappings: list[KafkaTransformMapping] | None = None
    correlation_id_source: str | None = None
    correlation_id_field_name: str | None = None
    reply_timeout_ms: int = 30000


class RetryPolicy(BaseModel):
    max_attempts: int = 3
    backoff_ms: int = 1000
    backoff_multiplier: float = 2.0


class DlqPolicy(BaseModel):
    enabled: bool = True
    topic_suffix: str = ".dlq"


class RouterExtractionMetadata(BaseModel):
    mode: str
    header_key: str | None = None
    body_field_path: str | None = None


class RouterUpstreamTopicMetadata(BaseModel):
    id: str
    name: str
    consumer_group: str
    source_system_extraction: RouterExtractionMetadata
    reply_destination_extraction: RouterExtractionMetadata


class RouterSchemaRefMetadata(BaseModel):
    file: str
    validation_policy: str = "strict"
    failure_behavior: str = "nack"
    content: dict[str, Any] | None = None


class RouterTransformRefMetadata(BaseModel):
    file: str
    mappings: list[KafkaTransformMapping]


class RouterRoutingFieldMetadata(BaseModel):
    name: str
    json_path: str


class RouterRoutingConditionMetadata(BaseModel):
    field: str
    operator: str
    value: Any = None


class RouterRoutingRuleMetadata(BaseModel):
    id: str
    conditions: list[RouterRoutingConditionMetadata]
    target: str


class RouterTargetRetryMetadata(BaseModel):
    max_attempts: int = 3
    backoff_ms: int = 1000
    dlq_topic: str


class RouterTargetMetadata(BaseModel):
    id: str
    request_topic: str
    response_topic: str
    request_schema: RouterSchemaRefMetadata
    response_schema: RouterSchemaRefMetadata
    request_transform: RouterTransformRefMetadata
    response_transform: RouterTransformRefMetadata
    retry: RouterTargetRetryMetadata | None = None
    timeout_ms: int = 30000


class RouterNackRoutingMetadata(BaseModel):
    mode: str
    per_source_system: dict[str, str] = Field(default_factory=dict)
    fixed_topic: str | None = None
    default_error_topic: str


class RouterTimeoutMetadata(BaseModel):
    behavior_with_known_reply: str = "nack"
    behavior_without_reply: str = "error_topic"


class RouterPayloadLoggingMetadata(BaseModel):
    policy: str = "none"
    capped_raw_bytes: int = 512


class RouterCorrelationStoreMetadata(BaseModel):
    type: str = "in_memory"
    timeout_ms: int = 30000
    eviction_interval_ms: int = 60000


class RouterRouteMetadata(BaseModel):
    name: str
    route_class_prefix: str
    upstream_topics: list[RouterUpstreamTopicMetadata]
    inbound_schema: RouterSchemaRefMetadata
    routing_fields: list[RouterRoutingFieldMetadata]
    routing_rules: list[RouterRoutingRuleMetadata]
    default_target: str | None = None
    duplicate_correlation_policy: str = "reject-new"
    targets: list[RouterTargetMetadata]
    outbound_schema: RouterSchemaRefMetadata
    nack_routing: RouterNackRoutingMetadata
    timeout: RouterTimeoutMetadata
    payload_logging: RouterPayloadLoggingMetadata
    correlation_store: RouterCorrelationStoreMetadata


class KafkaMetadata(BaseModel):
    app_name: str
    bounded_context: str
    schema_version: str = CURRENT_MANIFEST_SCHEMA_VERSION
    app_archetype: AppArchetype = AppArchetype.KAFKA_INTEGRATION
    java_package: str
    artifact_id: str
    consumer_group: str
    concurrency: int
    routes: list[ResolvedAsyncRoute]
    target_profile_name: str
    java_version: str
    spring_boot_version: str
    retry_policy: RetryPolicy | None = None
    dlq_policy: DlqPolicy | None = None
    router_routes: list[RouterRouteMetadata] = Field(default_factory=list)
