"""Normalized mapping models for explicit contract-to-canonical translation."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

SUPPORTED_OUTPUT_TYPE_COERCIONS = {"major_to_minor_units"}


class MappingDirection(str, Enum):
    """Direction of a mapping relative to the canonical model."""

    UPSTREAM_TO_CANONICAL = "upstream-to-canonical"
    CANONICAL_TO_DOWNSTREAM = "canonical-to-downstream"
    CANONICAL_TO_HANDOFF = "canonical-to-handoff"


class MappingSeverity(str, Enum):
    """Severity for mapping completeness issues."""

    WARNING = "warning"
    ERROR = "error"


class FieldMapping(BaseModel):
    """Explicit field-level mapping between a contract and canonical metadata."""

    contract_name: str
    direction: MappingDirection
    operation_name: str | None = None
    source_path: str
    target_path: str
    source_required: bool = False
    source_location: str | None = None
    layout_width: int | None = None
    type_coercion: str | None = None
    notes: list[str] = Field(default_factory=list)


class MappingIssue(BaseModel):
    """One completeness or validation issue found while building mappings."""

    contract_name: str
    direction: MappingDirection
    severity: MappingSeverity
    message: str
    location: str | None = None


class MappingCompletenessReport(BaseModel):
    """Completeness status for one contract's explicit mappings."""

    contract_name: str
    direction: MappingDirection
    status: str
    issues: list[MappingIssue] = Field(default_factory=list)
