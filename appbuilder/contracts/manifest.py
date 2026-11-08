"""Manifest models and loader for manifest-driven input projects."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from appbuilder.core import (
    CURRENT_MANIFEST_SCHEMA_FILENAME,
    DEFAULT_APP_ARCHETYPE,
    SUPPORTED_MANIFEST_SCHEMA_VERSIONS,
    AppArchetype,
)
from appbuilder.target_profiles import TARGET_PROFILES

FILE_CONTRACT_TYPES = {"file-fixed-width", "file-csv"}
XML_XSD_CONTRACT_TYPE = "xml-xsd"
SOAP_WSDL_CONTRACT_TYPE = "soap-wsdl"
NON_HANDOFF_CONTRACT_TYPES = {
    *FILE_CONTRACT_TYPES,
    XML_XSD_CONTRACT_TYPE,
    SOAP_WSDL_CONTRACT_TYPE,
}
_PHYSICAL_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_INTERNAL_SCHEMA_ID_PATTERN = re.compile(
    r"m5a-staging-(?:00[1-9]|0[1-9][0-9]|[1-9][0-9]{2,})"
)


class InterfaceDefinition(BaseModel):
    """Describes an upstream or downstream interface source."""

    name: str
    system: str | None = None
    type: str
    version: str | None = None
    spec: str | None = None
    spec_url: str | None = None
    xsd_path: str | None = None
    wsdl_path: str | None = None
    root_element: str | None = None
    namespace: str | None = None
    namespace_alias: str | None = None
    service: str | None = None
    port: str | None = None
    binding: str | None = None
    sample: str | None = None
    mapping: str | None = None
    samples: list[str] = Field(default_factory=list)
    operations: list[InterfaceOperationDefinition] = Field(default_factory=list)

    @field_validator("name", "system", "type")
    @classmethod
    def validate_required_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("spec", "xsd_path", "wsdl_path", "sample", "mapping")
    @classmethod
    def normalize_optional_path(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _normalize_manifest_path(value, field_name=info.field_name)

    @field_validator("root_element", "namespace", "namespace_alias", "service", "port", "binding")
    @classmethod
    def normalize_optional_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("spec_url")
    @classmethod
    def validate_spec_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("spec_url must not be empty")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("spec_url must start with http:// or https://")
        return normalized

    @field_validator("samples")
    @classmethod
    def normalize_samples(cls, values: list[str]) -> list[str]:
        return [_normalize_manifest_path(value, field_name="samples") for value in values]

    @model_validator(mode="after")
    def validate_source(self) -> InterfaceDefinition:
        if self.type == XML_XSD_CONTRACT_TYPE:
            if self.spec_url is not None:
                raise ValueError("xml-xsd interfaces must use xsd_path or spec, not spec_url.")
            if self.spec is not None and self.xsd_path is not None:
                raise ValueError("xml-xsd interfaces must not declare both spec and xsd_path.")
            if (
                self.wsdl_path is not None
                or self.service is not None
                or self.port is not None
                or self.binding is not None
            ):
                raise ValueError(
                    "wsdl_path/service/port/binding are valid only for type: soap-wsdl."
                )
            if self.spec is None and self.xsd_path is None:
                raise ValueError("xml-xsd interfaces require xsd_path or spec.")
            if self.root_element is None:
                raise ValueError("xml-xsd interfaces require root_element.")
            return self
        if self.type == SOAP_WSDL_CONTRACT_TYPE:
            if self.spec_url is not None:
                raise ValueError("soap-wsdl interfaces must use wsdl_path or spec, not spec_url.")
            if self.spec is not None and self.wsdl_path is not None:
                raise ValueError("soap-wsdl interfaces must not declare both spec and wsdl_path.")
            if self.spec is None and self.wsdl_path is None:
                raise ValueError("soap-wsdl interfaces require wsdl_path or spec.")
            if (
                self.xsd_path is not None
                or self.root_element is not None
                or self.namespace is not None
                or self.namespace_alias is not None
            ):
                raise ValueError(
                    "xsd_path, root_element, namespace, and namespace_alias are valid only "
                    "for type: xml-xsd."
                )
            return self
        if (
            self.xsd_path is not None
            or self.root_element is not None
            or self.wsdl_path is not None
            or self.service is not None
            or self.port is not None
            or self.binding is not None
        ):
            raise ValueError(
                "xsd_path/root_element are valid only for type: xml-xsd; "
                "wsdl_path/service/port/binding are valid only for type: soap-wsdl."
            )
        if bool(self.spec) == bool(self.spec_url):
            raise ValueError("Exactly one of 'spec' or 'spec_url' must be provided.")
        return self


class InterfaceOperationDefinition(BaseModel):
    """Explicit operation metadata for an interface."""

    name: str
    request_sample: str | None = None
    response_sample: str | None = None
    pageable: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("request_sample", "response_sample")
    @classmethod
    def normalize_sample_paths(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _normalize_manifest_path(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_operation_samples(self) -> InterfaceOperationDefinition:
        if self.request_sample is None and self.response_sample is None:
            raise ValueError(
                "At least one of 'request_sample' or 'response_sample' must be provided."
            )
        return self


class RunSemanticsDefinition(BaseModel):
    """Opt-in M5a staging run-semantics contract recognized by Slice 1."""

    model_config = ConfigDict(extra="forbid")

    run_id: Literal["caller_supplied"]
    restart: Literal["resume"]
    dedup_key: list[str] = Field(min_length=1)
    internal_schema_id: str | None = None

    @field_validator("dedup_key")
    @classmethod
    def validate_dedup_key(cls, values: list[str]) -> list[str]:
        normalized: set[str] = set()
        for value in values:
            if _PHYSICAL_IDENTIFIER_PATTERN.fullmatch(value) is None:
                raise ValueError(
                    "dedup_key entries must be simple ASCII physical column identifiers"
                )
            key = value.lower()
            if key in normalized:
                raise ValueError(
                    "dedup_key entries must be unique after case normalization"
                )
            normalized.add(key)
        return values

    @field_validator("internal_schema_id")
    @classmethod
    def validate_internal_schema_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _INTERNAL_SCHEMA_ID_PATTERN.fullmatch(value) is None:
            raise ValueError(
                "internal_schema_id must use the form m5a-staging-001 with a positive, "
                "zero-padded ordinal"
            )
        return value


class DataHandoffDefinition(BaseModel):
    """Describes staging-table or datastore handoff contracts."""

    name: str
    system: str | None = None
    type: str
    version: str | None = None
    spec: str
    mapping: str | None = None
    run_semantics: RunSemanticsDefinition | None = None

    @field_validator("name", "system", "type")
    @classmethod
    def validate_required_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        if info.field_name == "type" and normalized in NON_HANDOFF_CONTRACT_TYPES:
            raise ValueError(
                "file contracts belong in upstream_interfaces[] or downstream_interfaces[]; "
                "XML/XSD contracts belong in upstream_interfaces[] or downstream_interfaces[]; "
                "SOAP/WSDL contracts belong in upstream_interfaces[] or downstream_interfaces[]; "
                "data_handoffs[] remains reserved for table-based contracts."
            )
        return normalized

    @field_validator("spec", "mapping")
    @classmethod
    def normalize_local_paths(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _normalize_manifest_path(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_run_semantics_handoff_type(self) -> DataHandoffDefinition:
        if self.run_semantics is not None and self.type != "staging-table":
            raise ValueError(
                "run_semantics is supported only for data_handoffs[] entries with "
                "type: staging-table"
            )
        return self


class IdentityOverride(BaseModel):
    """Explicitly declares the persistence identity for a canonical entity."""

    entity: str
    persistence_id: str

    @field_validator("entity", "persistence_id")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized


class IdGenerationOverride(BaseModel):
    """Explicitly declares the ID generation strategy for a canonical entity."""

    entity: str
    strategy: str
    field: str | None = None
    sequence_name: str | None = None

    @field_validator("entity", "strategy")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("field", "sequence_name")
    @classmethod
    def validate_optional_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_strategy_constraints(self) -> IdGenerationOverride:
        valid_strategies = {"uuid", "caller_supplied", "db_identity", "db_sequence"}
        if self.strategy not in valid_strategies:
            raise ValueError(
                f"strategy '{self.strategy}' is not valid. "
                f"Must be one of: {sorted(valid_strategies)}"
            )
        if self.strategy == "db_sequence" and not self.sequence_name:
            raise ValueError("strategy 'db_sequence' requires a non-empty sequence_name")
        if self.strategy != "db_sequence" and self.sequence_name is not None:
            raise ValueError(
                "sequence_name is only valid for strategy 'db_sequence', "
                f"not '{self.strategy}'"
            )
        return self


SUPPORTED_IDENTITY_ROLE_VALUES = {
    "parent_reference",
    "business_key",
    "event_id",
    "idempotency_key",
    "correlation_id",
    "external_reference",
}
SUPPORTED_IDENTITY_ROLE_MODES = {"metadata_only", "active"}


class IdentityRoleDefinition(BaseModel):
    """Reviewed non-persistence identity-role metadata from the manifest."""

    entity: str
    field: str
    role: str
    mode: str
    policy: dict[str, Any] | None = None

    @field_validator("entity", "field", "role", "mode")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value == "persistence_id":
            raise ValueError(
                "identity_roles must not declare role 'persistence_id'; "
                "use top-level identity_overrides for persistence identity."
            )
        if value not in SUPPORTED_IDENTITY_ROLE_VALUES:
            raise ValueError(
                f"role '{value}' is not valid. Must be one of: "
                f"{sorted(SUPPORTED_IDENTITY_ROLE_VALUES)}"
            )
        return value

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in SUPPORTED_IDENTITY_ROLE_MODES:
            raise ValueError(
                f"mode '{value}' is not valid. Must be one of: "
                f"{sorted(SUPPORTED_IDENTITY_ROLE_MODES)}"
            )
        return value

    @model_validator(mode="after")
    def validate_mode_policy(self) -> IdentityRoleDefinition:
        if self.mode == "active" and self.policy is None:
            raise ValueError(
                "policy is required for active identity role "
                f"{self.entity}.{self.field} ({self.role})."
            )
        if self.mode == "active":
            raise ValueError(
                "active identity role behavior is not supported yet for "
                f"{self.entity}.{self.field} ({self.role}). "
                "Use mode: metadata_only until Engine support is implemented."
            )
        return self


class RetryConfigDefinition(BaseModel):
    """Retry policy for Kafka message processing failures."""

    max_attempts: int = 3
    backoff_ms: int = 1000
    backoff_multiplier: float = 2.0

    @field_validator("max_attempts")
    @classmethod
    def validate_max_attempts(cls, value: int) -> int:
        if not (0 <= value <= 10):
            raise ValueError("max_attempts must be between 0 and 10")
        return value

    @field_validator("backoff_ms")
    @classmethod
    def validate_backoff_ms(cls, value: int) -> int:
        if not (100 <= value <= 60000):
            raise ValueError("backoff_ms must be between 100 and 60000")
        return value

    @field_validator("backoff_multiplier")
    @classmethod
    def validate_backoff_multiplier(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")
        return value


class DlqConfigDefinition(BaseModel):
    """Dead-letter queue policy for messages that exhaust retries."""

    enabled: bool = True
    topic_suffix: str = ".dlq"

    @field_validator("topic_suffix")
    @classmethod
    def validate_topic_suffix(cls, value: str) -> str:
        if not value.startswith("."):
            raise ValueError("topic_suffix must start with '.'")
        return value


class KafkaConfigDefinition(BaseModel):
    """Kafka application-level configuration for kafka-integration manifests."""

    consumer_group: str
    concurrency: int = 1
    retry: RetryConfigDefinition | None = None
    dlq: DlqConfigDefinition | None = None

    @field_validator("consumer_group")
    @classmethod
    def validate_consumer_group(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("consumer_group must not be empty")
        return normalized

    @field_validator("concurrency")
    @classmethod
    def validate_concurrency(cls, value: int) -> int:
        if value < 1:
            raise ValueError("concurrency must be greater than or equal to 1")
        return value


class KafkaTopicDefinition(BaseModel):
    """A Kafka topic and JSON Schema reference for an async route."""

    name: str
    system: str
    message_schema: str
    sample: str | None = None

    @field_validator("name", "system")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("message_schema", "sample")
    @classmethod
    def normalize_topic_paths(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _normalize_manifest_path(value, field_name=info.field_name)


class KafkaReplyTopicDefinition(BaseModel):
    """A request/reply Kafka topic reference."""

    name: str
    message_schema: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized

    @field_validator("message_schema")
    @classmethod
    def normalize_message_schema(cls, value: str) -> str:
        return _normalize_manifest_path(value, field_name="message_schema")


class CorrelationIdDefinition(BaseModel):
    """Correlation ID extraction strategy for request/reply Kafka routes."""

    source: str = "header"
    field_name: str = "correlationId"

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        if value not in {"header", "body_field"}:
            raise ValueError("source must be one of: header, body_field")
        return value

    @field_validator("field_name")
    @classmethod
    def validate_field_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field_name must not be empty")
        return normalized


class PartitionKeyDefinition(BaseModel):
    """Partition key strategy for Kafka producer sends."""

    strategy: str = "round_robin"
    source: str | None = None

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        if value not in {"field_value", "correlation_id", "round_robin"}:
            raise ValueError(
                "strategy must be one of: field_value, correlation_id, round_robin"
            )
        return value

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("source must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_strategy_source(self) -> PartitionKeyDefinition:
        if self.strategy == "field_value" and self.source is None:
            raise ValueError("partition_key strategy 'field_value' requires source")
        return self


class RouterExtractionDefinition(BaseModel):
    """Header or body-field extraction settings for router intake metadata."""

    mode: str
    header_key: str | None = None
    body_field_path: str | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"header", "body_field"}:
            raise ValueError("mode must be one of: header, body_field")
        return value

    @field_validator("header_key", "body_field_path")
    @classmethod
    def validate_optional_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_mode_fields(self) -> RouterExtractionDefinition:
        if self.mode == "header" and self.header_key is None:
            raise ValueError("header extraction requires header_key")
        if self.mode == "body_field" and self.body_field_path is None:
            raise ValueError("body_field extraction requires body_field_path")
        return self


class RouterUpstreamTopicDefinition(BaseModel):
    """Upstream router intake topic and extraction config."""

    id: str
    name: str
    consumer_group: str
    source_system_extraction: RouterExtractionDefinition
    reply_destination_extraction: RouterExtractionDefinition

    @field_validator("id", "name", "consumer_group")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized


class RouterSchemaReference(BaseModel):
    """Router JSON Schema file reference and validation policy."""

    file: str
    validation_policy: str = "strict"
    failure_behavior: str = "nack"

    @field_validator("file")
    @classmethod
    def normalize_file(cls, value: str) -> str:
        return _normalize_manifest_path(value, field_name="file")

    @field_validator("validation_policy")
    @classmethod
    def validate_validation_policy(cls, value: str) -> str:
        if value not in {"strict", "lenient"}:
            raise ValueError("validation_policy must be one of: strict, lenient")
        return value

    @field_validator("failure_behavior")
    @classmethod
    def validate_failure_behavior(cls, value: str) -> str:
        if value != "nack":
            raise ValueError("failure_behavior must be nack")
        return value


class RouterTransformReference(BaseModel):
    """Router transform mapping file reference."""

    file: str

    @field_validator("file")
    @classmethod
    def normalize_file(cls, value: str) -> str:
        return _normalize_manifest_path(value, field_name="file")


class RouterRoutingFieldDefinition(BaseModel):
    """Named routing field extracted from the inbound request."""

    name: str
    json_path: str

    @field_validator("name", "json_path")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized


class RouterRoutingConditionDefinition(BaseModel):
    """One deterministic routing-rule condition."""

    field: str
    operator: str
    value: Any

    @field_validator("field", "operator")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, value: str) -> str:
        if value not in {"eq", "in", "lt", "lte", "gt", "gte", "not_null"}:
            raise ValueError(
                "operator must be one of: eq, in, lt, lte, gt, gte, not_null"
            )
        return value


class RouterRoutingRuleDefinition(BaseModel):
    """One router rule that selects a downstream target."""

    id: str
    conditions: list[RouterRoutingConditionDefinition] = Field(default_factory=list)
    target: str

    @field_validator("id", "target")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized


class RouterRoutingRulesDefinition(BaseModel):
    """Router routing fields, ordered rules, and optional default target."""

    routing_fields: list[RouterRoutingFieldDefinition] = Field(default_factory=list)
    rules: list[RouterRoutingRuleDefinition] = Field(default_factory=list)
    default_target: str | None = None

    @field_validator("default_target")
    @classmethod
    def validate_default_target(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("default_target must not be empty")
        return normalized


class RouterTargetRetryDefinition(BaseModel):
    """Per-target router retry and DLQ topic config."""

    max_attempts: int = 3
    backoff_ms: int = 1000
    dlq_topic: str

    @field_validator("dlq_topic")
    @classmethod
    def validate_dlq_topic(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("dlq_topic must not be empty")
        return normalized


class RouterTargetDefinition(BaseModel):
    """One downstream router target and its request/response contracts."""

    id: str
    request_topic: str
    response_topic: str
    request_schema: RouterSchemaReference
    response_schema: RouterSchemaReference
    request_transform: RouterTransformReference
    response_transform: RouterTransformReference
    retry: RouterTargetRetryDefinition | None = None
    timeout_ms: int = 30000

    @field_validator("id", "request_topic", "response_topic")
    @classmethod
    def validate_required_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("timeout_ms")
    @classmethod
    def validate_timeout_ms(cls, value: int) -> int:
        if value < 1000:
            raise ValueError("timeout_ms must be greater than or equal to 1000")
        return value


class RouterNackRoutingDefinition(BaseModel):
    """Router NACK destination strategy."""

    mode: str
    per_source_system: dict[str, str] = Field(default_factory=dict)
    fixed_topic: str | None = None
    default_error_topic: str

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"same_as_reply", "per_source_system", "fixed", "default_error"}:
            raise ValueError(
                "mode must be one of: same_as_reply, per_source_system, fixed, default_error"
            )
        return value

    @field_validator("fixed_topic", "default_error_topic")
    @classmethod
    def validate_optional_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("per_source_system")
    @classmethod
    def validate_per_source_system(cls, value: dict[str, str]) -> dict[str, str]:
        for key, topic in value.items():
            if not key.strip():
                raise ValueError("per_source_system keys must not be empty")
            if not topic.strip():
                raise ValueError("per_source_system topics must not be empty")
        return value

    @model_validator(mode="after")
    def validate_mode_specific_config(self) -> RouterNackRoutingDefinition:
        if self.mode == "fixed" and self.fixed_topic is None:
            raise ValueError("nack_routing mode 'fixed' requires fixed_topic")
        if self.mode == "per_source_system" and not self.per_source_system:
            raise ValueError(
                "nack_routing mode 'per_source_system' requires per_source_system"
            )
        return self


class RouterTimeoutDefinition(BaseModel):
    """Router timeout behavior config."""

    behavior_with_known_reply: str = "nack"
    behavior_without_reply: str = "error_topic"

    @field_validator("behavior_with_known_reply")
    @classmethod
    def validate_known_reply_behavior(cls, value: str) -> str:
        if value not in {"nack", "error_topic"}:
            raise ValueError("behavior_with_known_reply must be one of: nack, error_topic")
        return value

    @field_validator("behavior_without_reply")
    @classmethod
    def validate_without_reply_behavior(cls, value: str) -> str:
        if value != "error_topic":
            raise ValueError("behavior_without_reply must be error_topic")
        return value


class RouterPayloadLoggingDefinition(BaseModel):
    """Router payload logging policy."""

    policy: str = "none"
    capped_raw_bytes: int = 512

    @field_validator("policy")
    @classmethod
    def validate_policy(cls, value: str) -> str:
        if value not in {"none", "hash", "redacted", "capped_raw"}:
            raise ValueError("policy must be one of: none, hash, redacted, capped_raw")
        return value


class RouterCorrelationStoreDefinition(BaseModel):
    """Router correlation-store contract for Phase R1."""

    type: str = "in_memory"
    timeout_ms: int = 30000
    eviction_interval_ms: int = 60000

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value != "in_memory":
            raise ValueError("correlation_store.type must be in_memory")
        return value


class RouterConfig(BaseModel):
    """Router-only async route config nested under pattern: router."""

    upstream_topics: list[RouterUpstreamTopicDefinition]
    inbound_schema: RouterSchemaReference
    routing_rules: RouterRoutingRulesDefinition
    duplicate_correlation_policy: str = "reject-new"
    targets: list[RouterTargetDefinition]
    outbound_schema: RouterSchemaReference
    nack_routing: RouterNackRoutingDefinition
    timeout: RouterTimeoutDefinition | None = None
    payload_logging: RouterPayloadLoggingDefinition = Field(
        default_factory=RouterPayloadLoggingDefinition
    )
    correlation_store: RouterCorrelationStoreDefinition = Field(
        default_factory=RouterCorrelationStoreDefinition
    )

    @field_validator("duplicate_correlation_policy")
    @classmethod
    def validate_duplicate_policy(cls, value: str) -> str:
        if value not in {"reject-new", "accept-last"}:
            raise ValueError(
                "duplicate_correlation_policy must be one of: reject-new, accept-last"
            )
        return value

    @model_validator(mode="after")
    def validate_router_collections(self) -> RouterConfig:
        if not self.upstream_topics:
            raise ValueError("router_config.upstream_topics must contain at least one item")
        if not self.targets:
            raise ValueError("router_config.targets must contain at least one item")
        seen: set[str] = set()
        for target in self.targets:
            if target.id in seen:
                raise ValueError(f"router_config.targets declares duplicate id '{target.id}'")
            seen.add(target.id)
        return self


class AsyncRouteDefinition(BaseModel):
    """A manifest-declared Kafka async mediation route."""

    name: str
    pattern: str
    upstream_topic: KafkaTopicDefinition | None = None
    downstream_topic: KafkaTopicDefinition | None = None
    transform_mapping: str | None = None
    upstream_reply_topic: KafkaReplyTopicDefinition | None = None
    downstream_reply_topic: KafkaReplyTopicDefinition | None = None
    response_transform_mapping: str | None = None
    router_config: RouterConfig | None = None
    correlation_id: CorrelationIdDefinition | None = None
    partition_key: PartitionKeyDefinition | None = None
    reply_timeout_ms: int = 30000

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str) -> str:
        if value not in {"fire-and-forget", "request-reply", "router"}:
            raise ValueError("pattern must be one of: fire-and-forget, request-reply, router")
        return value

    @field_validator("transform_mapping", "response_transform_mapping")
    @classmethod
    def normalize_mapping_paths(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _normalize_manifest_path(value, field_name=info.field_name)

    @field_validator("reply_timeout_ms")
    @classmethod
    def validate_reply_timeout(cls, value: int) -> int:
        if value < 1000:
            raise ValueError("reply_timeout_ms must be greater than or equal to 1000")
        return value

    @model_validator(mode="after")
    def validate_pattern_fields(self) -> AsyncRouteDefinition:
        fixed_route_fields = (
            ("upstream_topic", self.upstream_topic),
            ("downstream_topic", self.downstream_topic),
            ("transform_mapping", self.transform_mapping),
        )
        reply_fields = (
            ("upstream_reply_topic", self.upstream_reply_topic),
            ("downstream_reply_topic", self.downstream_reply_topic),
            ("response_transform_mapping", self.response_transform_mapping),
        )
        if self.pattern == "router":
            if self.router_config is None:
                raise ValueError("router routes require router_config")
            present = [
                field_name
                for field_name, value in (*fixed_route_fields, *reply_fields)
                if value is not None
            ]
            if present:
                raise ValueError(
                    "router routes must not declare " + ", ".join(sorted(present))
                )
            return self

        missing_fixed = [
            field_name for field_name, value in fixed_route_fields if value is None
        ]
        if missing_fixed:
            raise ValueError(
                f"{self.pattern} routes require " + ", ".join(sorted(missing_fixed))
            )
        if self.router_config is not None:
            raise ValueError(f"{self.pattern} routes must not declare router_config")
        if self.pattern == "request-reply":
            missing = [
                field_name
                for field_name, value in reply_fields
                if value is None
            ]
            if missing:
                raise ValueError(
                    "request-reply routes require " + ", ".join(sorted(missing))
                )
        if self.pattern == "fire-and-forget":
            present = [
                field_name
                for field_name, value in reply_fields
                if value is not None
            ]
            if present:
                raise ValueError(
                    "fire-and-forget routes must not declare "
                    + ", ".join(sorted(present))
                )
        return self


class ProjectDefinition(BaseModel):
    """Top-level manifest model for one modernization input package."""

    app_name: str
    bounded_context: str
    schema_version: str
    app_archetype: AppArchetype = DEFAULT_APP_ARCHETYPE
    upstream_interfaces: list[InterfaceDefinition] = Field(default_factory=list)
    downstream_interfaces: list[InterfaceDefinition] = Field(default_factory=list)
    data_handoffs: list[DataHandoffDefinition] = Field(default_factory=list)
    identity_overrides: list[IdentityOverride] = Field(default_factory=list)
    identity_roles: list[IdentityRoleDefinition] = Field(default_factory=list)
    id_generation_overrides: list[IdGenerationOverride] = Field(default_factory=list)
    kafka_config: KafkaConfigDefinition | None = None
    async_routes: list[AsyncRouteDefinition] | None = None
    rules: list[str] = Field(default_factory=list)
    legacy_references: list[str] = Field(default_factory=list)
    target_profile: str
    _identity_roles_declared: bool = PrivateAttr(default=False)
    _manifest_path: Path | None = PrivateAttr(default=None)

    @field_validator("app_name", "bounded_context")
    @classmethod
    def validate_required_top_level_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("schema_version must not be empty")
        if normalized not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
            supported = ", ".join(sorted(SUPPORTED_MANIFEST_SCHEMA_VERSIONS))
            raise ValueError(
                f"Unknown schema_version '{normalized}'. Supported versions: {supported}"
            )
        return normalized

    @field_validator("app_archetype", mode="before")
    @classmethod
    def normalize_app_archetype(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("app_archetype must not be empty")
            return normalized
        return value

    @field_validator("target_profile")
    @classmethod
    def validate_target_profile(cls, value: str) -> str:
        if value not in TARGET_PROFILES:
            available = ", ".join(sorted(TARGET_PROFILES))
            raise ValueError(f"Unknown target_profile '{value}'. Available profiles: {available}")
        return value

    @field_validator("rules", "legacy_references")
    @classmethod
    def normalize_project_paths(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return [_normalize_manifest_path(value, field_name=info.field_name) for value in values]

    @model_validator(mode="after")
    def validate_identity_overrides(self) -> ProjectDefinition:
        seen: set[str] = set()
        for override in self.identity_overrides:
            if override.entity in seen:
                raise ValueError(
                    f"identity_overrides declares entity '{override.entity}' more than once."
                )
            seen.add(override.entity)
        return self

    @model_validator(mode="after")
    def validate_id_generation_overrides(self) -> ProjectDefinition:
        seen: set[str] = set()
        for override in self.id_generation_overrides:
            if override.entity in seen:
                raise ValueError(
                    f"id_generation_overrides declares entity '{override.entity}' more than once."
                )
            seen.add(override.entity)
        return self

    @model_validator(mode="after")
    def validate_run_semantics_archetype(self) -> ProjectDefinition:
        opted_handoffs = [
            handoff.name
            for handoff in self.data_handoffs
            if handoff.run_semantics is not None
        ]
        if opted_handoffs and self.app_archetype != AppArchetype.CRUD:
            raise ValueError(
                "data_handoffs[].run_semantics is currently supported only for "
                "app_archetype: crud; unsupported handoff(s): "
                + ", ".join(sorted(opted_handoffs))
            )
        return self

    @model_validator(mode="after")
    def validate_run_semantics_internal_schema_ids(self) -> ProjectDefinition:
        claims: dict[str, str] = {}
        for handoff in self.data_handoffs:
            if handoff.run_semantics is None:
                continue
            internal_schema_id = handoff.run_semantics.internal_schema_id
            if internal_schema_id is None:
                continue
            if internal_schema_id in claims:
                raise ValueError(
                    "data_handoffs[] run_semantics internal_schema_id "
                    f"'{internal_schema_id}' is claimed by both '{claims[internal_schema_id]}' "
                    f"and '{handoff.name}'"
                )
            claims[internal_schema_id] = handoff.name
        return self

    @model_validator(mode="after")
    def validate_identity_roles_archetype(self) -> ProjectDefinition:
        if self._identity_roles_declared and self.app_archetype != AppArchetype.CRUD:
            raise ValueError(
                "identity_roles are currently supported only for app_archetype: crud. "
                f"Unsupported app_archetype: {self.app_archetype.value}."
            )
        return self

    @model_validator(mode="after")
    def validate_kafka_integration_configuration(self) -> ProjectDefinition:
        if self.app_archetype == AppArchetype.KAFKA_INTEGRATION:
            if self.kafka_config is None:
                raise ValueError("kafka-integration manifests require kafka_config")
            if not self.async_routes:
                raise ValueError(
                    "kafka-integration manifests require at least one async_routes entry"
                )
        return self

    def referenced_paths(self) -> list[Path]:
        """Return manifest-relative file paths that should exist locally."""

        paths: list[Path] = []
        for interface in [*self.upstream_interfaces, *self.downstream_interfaces]:
            if interface.xsd_path:
                paths.append(Path(interface.xsd_path))
            elif interface.wsdl_path:
                paths.append(Path(interface.wsdl_path))
            elif interface.spec:
                paths.append(Path(interface.spec))
            if interface.mapping:
                paths.append(Path(interface.mapping))
            if interface.sample:
                paths.append(Path(interface.sample))
            paths.extend(Path(sample) for sample in interface.samples)
            for operation in interface.operations:
                if operation.request_sample:
                    paths.append(Path(operation.request_sample))
                if operation.response_sample:
                    paths.append(Path(operation.response_sample))

        for handoff in self.data_handoffs:
            paths.append(Path(handoff.spec))
            if handoff.mapping:
                paths.append(Path(handoff.mapping))

        for route in self.async_routes or []:
            if route.pattern == "router":
                if route.router_config is None:
                    continue
                router_config = route.router_config
                paths.append(Path(router_config.inbound_schema.file))
                paths.append(Path(router_config.outbound_schema.file))
                for target in router_config.targets:
                    paths.append(Path(target.request_schema.file))
                    paths.append(Path(target.response_schema.file))
                    paths.append(Path(target.request_transform.file))
                    paths.append(Path(target.response_transform.file))
                continue

            if route.upstream_topic is not None:
                paths.append(Path(route.upstream_topic.message_schema))
                if route.upstream_topic.sample:
                    paths.append(Path(route.upstream_topic.sample))
            if route.downstream_topic is not None:
                paths.append(Path(route.downstream_topic.message_schema))
                if route.downstream_topic.sample:
                    paths.append(Path(route.downstream_topic.sample))
            if route.transform_mapping is not None:
                paths.append(Path(route.transform_mapping))
            if route.upstream_reply_topic:
                paths.append(Path(route.upstream_reply_topic.message_schema))
            if route.downstream_reply_topic:
                paths.append(Path(route.downstream_reply_topic.message_schema))
            if route.response_transform_mapping:
                paths.append(Path(route.response_transform_mapping))

        paths.extend(Path(rule) for rule in self.rules)
        paths.extend(Path(reference) for reference in self.legacy_references)
        return paths

    @property
    def manifest_path(self) -> Path:
        """Absolute path to the manifest that produced this definition."""

        if self._manifest_path is None:
            raise ValueError("ProjectDefinition is not bound to a manifest path.")
        return self._manifest_path


def validate_package(raw: Any) -> list[str]:
    """Validate raw manifest input against the committed JSON schema."""

    errors = [
        _format_schema_error(error)
        for error in _manifest_schema_validator().iter_errors(raw)
    ]
    if isinstance(raw, Mapping):
        errors.extend(_validate_identity_roles_contract(raw))
        errors.extend(_validate_run_semantics_contract(raw))
    return sorted(errors)


def validate_package_or_raise(raw: Any) -> None:
    """Raise a single ValueError containing all schema-validation failures."""

    errors = validate_package(raw)
    if errors:
        raise ValueError("\n".join(errors))


def load_project_definition(manifest_path: str | Path) -> ProjectDefinition:
    """Load and validate a project manifest from disk."""

    path = Path(manifest_path)
    with path.open("r", encoding="utf-8") as handle:
        payload: Any = yaml.safe_load(handle)

    if payload is None:
        raise ValueError(f"Manifest '{path}' is empty. Expected a YAML mapping.")
    if not isinstance(payload, dict):
        raise ValueError(f"Manifest '{path}' must contain a YAML mapping at the top level.")

    try:
        validate_package_or_raise(payload)
        definition = ProjectDefinition.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"Invalid manifest '{path}': {exc}") from exc
    definition._identity_roles_declared = "identity_roles" in payload
    try:
        definition = definition.model_validate(definition)
    except ValidationError as exc:
        raise ValueError(f"Invalid manifest '{path}': {exc}") from exc
    definition._manifest_path = path.resolve()
    _validate_local_paths(definition=definition, manifest_path=path)
    return definition


def _validate_local_paths(*, definition: ProjectDefinition, manifest_path: Path) -> None:
    project_root = manifest_path.parent
    missing = [
        str(project_root / relative_path)
        for relative_path in definition.referenced_paths()
        if not (project_root / relative_path).exists()
    ]
    if missing:
        missing_paths = ", ".join(sorted(missing))
        raise FileNotFoundError(
            f"Manifest '{manifest_path}' references missing files: {missing_paths}"
        )


@lru_cache(maxsize=1)
def _manifest_schema_validator() -> Draft202012Validator:
    schema_path = (
        Path(__file__).resolve().parent.parent
        / "schema"
        / CURRENT_MANIFEST_SCHEMA_FILENAME
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _format_schema_error(error: Any) -> str:
    location = ".".join(str(part) for part in error.absolute_path) or "$"
    return f"{location}: {error.message}"


def _validate_identity_roles_contract(raw: Mapping[str, Any]) -> list[str]:
    if "identity_roles" not in raw:
        return []
    identity_roles = raw.get("identity_roles", [])
    if identity_roles is None:
        return []
    if not isinstance(identity_roles, list):
        return []
    app_archetype = raw.get("app_archetype", "crud")
    if app_archetype != "crud":
        return [
            "identity_roles: identity_roles are currently supported only for "
            f"app_archetype: crud. Unsupported app_archetype: {app_archetype}."
        ]

    errors: list[str] = []
    for index, role in enumerate(identity_roles):
        if not isinstance(role, dict):
            continue
        entity = role.get("entity")
        field = role.get("field")
        role_name = role.get("role")
        mode = role.get("mode")
        label = f"identity_roles.{index}"
        role_label = (
            f"{entity}.{field} ({role_name})"
            if isinstance(entity, str)
            and isinstance(field, str)
            and isinstance(role_name, str)
            else label
        )
        if role_name == "persistence_id":
            errors.append(
                f"{label}.role: identity_roles must not declare role 'persistence_id'; "
                "use top-level identity_overrides for persistence identity."
            )
        if mode == "active" and "policy" not in role:
            errors.append(
                f"{label}.policy: policy is required for active identity role {role_label}."
            )
        elif mode == "active":
            errors.append(
                f"{label}.mode: active identity role behavior is not supported yet "
                f"for {role_label}; use mode: metadata_only until Engine support is implemented."
            )
    return errors


def _validate_run_semantics_contract(raw: Mapping[str, Any]) -> list[str]:
    handoffs = raw.get("data_handoffs")
    if not isinstance(handoffs, list):
        return []

    errors: list[str] = []
    internal_schema_claims: dict[str, tuple[int, str]] = {}
    for index, handoff in enumerate(handoffs):
        if not isinstance(handoff, Mapping):
            continue
        run_semantics = handoff.get("run_semantics")
        if not isinstance(run_semantics, Mapping):
            continue
        label = f"data_handoffs.{index}.run_semantics"
        app_archetype = raw.get("app_archetype", AppArchetype.CRUD.value)
        if app_archetype != AppArchetype.CRUD.value:
            errors.append(
                f"{label}: run_semantics is currently supported only for "
                f"app_archetype: crud; found {app_archetype!r}"
            )

        dedup_key = run_semantics.get("dedup_key")
        if isinstance(dedup_key, list):
            seen: set[str] = set()
            for dedup_index, value in enumerate(dedup_key):
                if not isinstance(value, str):
                    continue
                normalized = value.lower()
                if normalized in seen:
                    errors.append(
                        f"{label}.dedup_key.{dedup_index}: dedup_key entries must be unique "
                        "after case normalization"
                    )
                seen.add(normalized)

        internal_schema_id = run_semantics.get("internal_schema_id")
        if not isinstance(internal_schema_id, str):
            continue
        handoff_name = handoff.get("name")
        current_name = handoff_name if isinstance(handoff_name, str) else f"index {index}"
        previous = internal_schema_claims.get(internal_schema_id)
        if previous is not None:
            previous_index, previous_name = previous
            errors.append(
                f"{label}.internal_schema_id: internal_schema_id '{internal_schema_id}' is "
                f"already claimed by data_handoffs.{previous_index} ('{previous_name}'); "
                f"handoff '{current_name}' must declare a unique id"
            )
        else:
            internal_schema_claims[internal_schema_id] = (index, current_name)
    return errors


def _normalize_manifest_path(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")

    raw_path = PurePosixPath(normalized.replace("\\", "/"))
    if raw_path.is_absolute():
        raise ValueError(f"{field_name} must be a relative path inside the input project")

    parts: list[str] = []
    for part in raw_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError(f"{field_name} must not escape the input project root")
            parts.pop()
            continue
        parts.append(part)

    if not parts:
        raise ValueError(f"{field_name} must point to a file inside the input project")

    return PurePosixPath(*parts).as_posix()
