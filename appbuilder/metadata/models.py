"""Core normalized metadata models for generation."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_serializer, model_validator

from appbuilder.core import (
    CURRENT_MANIFEST_SCHEMA_VERSION,
    DEFAULT_APP_ARCHETYPE,
    AppArchetype,
)
from appbuilder.mapping import FieldMapping, MappingCompletenessReport
from appbuilder.rules import CanonicalRule


class CanonicalFieldType(str, Enum):
    """Controlled vocabulary for canonical field typing."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    BINARY = "binary"


class HttpMethod(str, Enum):
    """HTTP methods for REST operations."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class ResponseShape(str, Enum):
    """Basic response shape classification for a REST operation."""

    SINGLE = "SINGLE"    # Returns a single entity (200 + entity body)
    LIST = "LIST"        # Returns a list of entities (200 + array body)
    VOID = "VOID"        # Returns no body (204)
    CREATED = "CREATED"  # Returns 201 + created entity body


class RelationshipType(str, Enum):
    """Supported canonical entity relationship types."""

    MANY_TO_ONE = "many-to-one"


class IdGenerationStrategy(str, Enum):
    """Controlled vocabulary for C9 ID generation strategies."""

    UUID = "uuid"
    CALLER_SUPPLIED = "caller_supplied"
    DB_IDENTITY = "db_identity"
    DB_SEQUENCE = "db_sequence"


class IdentityRole(str, Enum):
    """Reviewed non-persistence identity roles carried as metadata."""

    PARENT_REFERENCE = "parent_reference"
    BUSINESS_KEY = "business_key"
    EVENT_ID = "event_id"
    IDEMPOTENCY_KEY = "idempotency_key"
    CORRELATION_ID = "correlation_id"
    EXTERNAL_REFERENCE = "external_reference"


class IdentityRoleMode(str, Enum):
    """Supported identity-role contract modes."""

    METADATA_ONLY = "metadata_only"
    ACTIVE = "active"


class PathParameter(BaseModel):
    """A single path parameter extracted from a route pattern."""

    name: str
    type: str = "String"  # Java type: String or Long


class OperationParameterLocation(str, Enum):
    """Supported non-path HTTP parameter locations."""

    QUERY = "query"
    HEADER = "header"


class OperationParameter(BaseModel):
    """A query/header parameter extracted from an upstream operation contract."""

    name: str
    location: OperationParameterLocation
    required: bool = False
    type: CanonicalFieldType = CanonicalFieldType.STRING
    format: str | None = None
    pattern: str | None = None
    read_input_role: str | None = None

    @model_serializer(mode="wrap")
    def _serialize_read_role(self, handler):
        result = handler(self)
        if self.read_input_role is None:
            result.pop("read_input_role", None)
        return result


class CanonicalField(BaseModel):
    """Field definition in the canonical internal model."""

    name: str
    type: CanonicalFieldType
    is_id: bool = False
    required: bool = False
    not_null: bool = False
    max_length: int | None = None
    min_length: int | None = None
    pattern: str | None = None
    range_min: float | None = None
    range_max: float | None = None
    format: str | None = None
    default_value: str | None = None
    allowed_values: list[str] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)
    # ID ownership: True = server-generated (@GeneratedValue), False = client-supplied
    server_generated_id: bool = True
    # C9: explicit ID generation strategy. None means preserve legacy behavior.
    # When set, takes precedence over server_generated_id inference in all emitters.
    id_generation_strategy: IdGenerationStrategy | None = None
    # C9: sequence name for db_sequence strategy. Set only when
    # id_generation_strategy == IdGenerationStrategy.DB_SEQUENCE.
    id_sequence_name: str | None = None


class CanonicalEntity(BaseModel):
    """Entity in the canonical internal model."""

    name: str
    fields: list[CanonicalField] = Field(default_factory=list)
    # Translation-time warnings for unsupported constructs
    warnings: list[str] = Field(default_factory=list)
    # Translation must establish identity without using the read being checked.
    read_identity_verified: bool = True

    @model_serializer(mode="wrap")
    def _serialize_read_identity(self, handler):
        result = handler(self)
        if self.read_identity_verified:
            result.pop("read_identity_verified", None)
        return result


class CanonicalRelationship(BaseModel):
    """Relationship inferred between canonical entities."""

    source_entity: str
    source_field: str
    target_entity: str
    target_field: str
    relationship_type: RelationshipType = RelationshipType.MANY_TO_ONE
    association_name: str


class IdentityRoleMetadata(BaseModel):
    """Manifest-declared identity role metadata after reference validation."""

    entity: str
    field: str
    role: IdentityRole
    mode: IdentityRoleMode = IdentityRoleMode.METADATA_ONLY
    policy: dict | None = None


class RunSemanticsMetadata(BaseModel):
    """Validated generation-only M5a run-semantics contract."""

    run_id: Literal["caller_supplied"]
    restart: Literal["resume"]
    dedup_key: list[str]
    internal_schema_id: str | None = None
    physical_run_id_column: str
    physical_run_id_max_length: int | None = None
    entity_name: str


class ContractMetadata(BaseModel):
    """Normalized metadata for an external contract source."""

    name: str
    type: str
    version: str | None = None
    source: str
    physical_name: str | None = None
    sample_paths: list[str] = Field(default_factory=list)
    mapping_path: str | None = None
    ingestion_notes: list[str] = Field(default_factory=list)
    # Parsed file layouts are generation-only metadata. Exclude them from
    # serialized golden metadata so existing public metadata shape stays stable.
    file_layout: dict[str, Any] | None = Field(default=None, exclude=True)
    xml_contract: dict[str, Any] | None = Field(default=None, exclude=True)
    soap_contract: dict[str, Any] | None = Field(default=None, exclude=True)
    run_semantics: RunSemanticsMetadata | None = Field(default=None, exclude=True)


class SystemParticipant(BaseModel):
    """Describes an upstream, downstream, or handoff system."""

    name: str
    role: str


class RouteEntry(BaseModel):
    """One match -> target branch in a passthrough routing rule."""

    match: str = Field(min_length=1)
    target: str = Field(min_length=1)


class RoutingRule(BaseModel):
    """Simple equality-based routing configuration for passthrough-router."""

    route_field: str = Field(min_length=1)
    routes: list[RouteEntry] = Field(default_factory=list, min_length=1)
    default_target: str = Field(min_length=1)


class TransformMapping(BaseModel):
    """Flat field-to-field passthrough transform mapping."""

    source: str | None = Field(default=None, min_length=1)
    target: str = Field(min_length=1)
    default: str | None = None
    # Additive transform operations for Kafka and future REST passthrough rules.
    constant: str | None = None
    value_map: dict[str, str] | None = None
    type_coercion: str | None = None

    @model_validator(mode="after")
    def validate_type_coercion(self) -> TransformMapping:
        valid_coercions = {"major_to_minor_units", "minor_to_major_units"}
        if self.type_coercion is not None and self.type_coercion not in valid_coercions:
            raise ValueError(
                f"type_coercion must be one of: {', '.join(sorted(valid_coercions))}"
            )
        return self

    @model_validator(mode="after")
    def validate_transform_input(self) -> TransformMapping:
        if self.source is None and self.constant is None and self.default is None:
            raise ValueError(
                "TransformMapping requires at least one of source, constant, or default"
            )
        return self


class CanonicalOperation(BaseModel):
    """Represents a canonical REST operation derived from an interface contract.

    Phase 1a strengthening: carries HTTP method, route, path parameters,
    request body presence, and response shape so emitters can make correct
    decisions without guessing from operation names.
    """

    name: str
    interface_name: str
    request_entity: str | None = None
    response_entity: str | None = None

    # Phase 1a additions — REST operation metadata
    http_method: HttpMethod | None = None
    path: str | None = None                    # e.g. /accounts or /accounts/{id}
    path_parameters: list[PathParameter] = Field(default_factory=list)
    operation_parameters: list[OperationParameter] = Field(default_factory=list)
    read_input_errors: list[str] = Field(default_factory=list)
    has_request_body: bool = False
    response_shape: ResponseShape | None = None
    # Phase 3 B7: per-operation opt-in offset/limit pagination for list reads.
    pageable: bool = False
    request_fields: list[CanonicalField] = Field(default_factory=list)
    response_fields: list[CanonicalField] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _serialize_read_input_errors(self, handler):
        result = handler(self)
        if not self.read_input_errors:
            result.pop("read_input_errors", None)
        return result


class MetadataProject(BaseModel):
    """Normalized project metadata independent of raw input formats."""

    app_name: str
    bounded_context: str
    schema_version: str = CURRENT_MANIFEST_SCHEMA_VERSION
    app_archetype: AppArchetype = DEFAULT_APP_ARCHETYPE
    target_profile: str
    systems: list[SystemParticipant] = Field(default_factory=list)
    contracts: list[ContractMetadata] = Field(default_factory=list)
    operations: list[CanonicalOperation] = Field(default_factory=list)
    # Source-selected REST transport contracts, retained before attribution/dispatch.
    selected_rest_contracts: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[CanonicalEntity] = Field(default_factory=list)
    mappings: list[FieldMapping] = Field(default_factory=list)
    mapping_reports: list[MappingCompletenessReport] = Field(default_factory=list)
    rules: list[CanonicalRule] = Field(default_factory=list)
    relationships: list[CanonicalRelationship] = Field(default_factory=list)
    identity_roles: list[IdentityRoleMetadata] = Field(default_factory=list)
    routing_rules: list[RoutingRule] = Field(default_factory=list)
    transform_mappings: list[TransformMapping] = Field(default_factory=list)
    # Project-level translation warnings (unsupported constructs, skipped fields, etc.)
    warnings: list[str] = Field(default_factory=list)
    # staging table DDL content keyed by physical table name, used by sql_emitter
    # to generate Flyway migrations for data handoff tables.
    staging_table_ddls: dict[str, str] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def _serialize_selected_rest_contracts(self, handler):
        result = handler(self)
        if not self.selected_rest_contracts:
            result.pop("selected_rest_contracts", None)
        return result
