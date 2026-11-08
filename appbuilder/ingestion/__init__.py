"""Helpers for ingesting upstream contract sources."""

from .openapi_classifier import (
    classify_openapi_schemas,
    extract_entity_fields,
    ingest_openapi_entities,
    ingest_openapi_operations,
    inventory_openapi_operations,
    openapi_type_to_canonical_type,
    summarize_openapi_assessment,
)
from .openapi_fetcher import fetch_openapi_spec

__all__ = [
    "classify_openapi_schemas",
    "extract_entity_fields",
    "fetch_openapi_spec",
    "ingest_openapi_entities",
    "ingest_openapi_operations",
    "inventory_openapi_operations",
    "openapi_type_to_canonical_type",
    "summarize_openapi_assessment",
]
