"""Shared core primitives for the builder."""

from .archetypes import DEFAULT_APP_ARCHETYPE, AppArchetype
from .manifest_versions import (
    CURRENT_MANIFEST_SCHEMA_FILENAME,
    CURRENT_MANIFEST_SCHEMA_VERSION,
    SUPPORTED_MANIFEST_SCHEMA_VERSIONS,
)

__all__ = [
    "AppArchetype",
    "CURRENT_MANIFEST_SCHEMA_FILENAME",
    "CURRENT_MANIFEST_SCHEMA_VERSION",
    "DEFAULT_APP_ARCHETYPE",
    "SUPPORTED_MANIFEST_SCHEMA_VERSIONS",
]
