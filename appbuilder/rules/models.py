"""Normalized rule models for canonical metadata enrichment."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RuleType(str, Enum):
    """Supported Phase 1 and 2 rule types."""

    ALLOWED_VALUES = "allowed-values"
    DEFAULT = "default"
    FORMAT = "format"
    MAX_LENGTH = "max-length"
    MIN_LENGTH = "min-length"
    PATTERN = "pattern"
    RANGE = "range"
    NOT_NULL = "not-null"
    CROSS_ENTITY_EXISTS = "cross-entity-exists"
    CROSS_ENTITY_FIELD_CHECK = "cross-entity-field-check"
    CROSS_ENTITY_FIELD_COMPARE = "cross-entity-field-compare"
    CROSS_ENTITY_FIELD_IN = "cross-entity-field-in"
    FIELD_COMPARISON = "field-comparison"


class CanonicalRule(BaseModel):
    """Rule applied to one canonical field."""

    entity_name: str
    field_name: str
    type: RuleType
    source_path: str
    values: list[str] = Field(default_factory=list)
    value: str | None = None
    format: str | None = None
    max_length: int | None = None
    min_length: int | None = None
    pattern: str | None = None
    range_min: float | None = None
    range_max: float | None = None
    # cross-entity-exists: the entity whose repository is queried for FK existence
    target_entity: str | None = None
    target_field: str | None = None
    source_field: str | None = None
    operator: str | None = None
    expected_value: str | None = None
    error_message: str | None = None
    compare_to_field: str | None = None
