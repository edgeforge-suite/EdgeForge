"""MCP tool exports for EdgeForge Engine."""

from .catalog import (
    describe_target_profile,
    list_archetypes,
    list_target_profiles,
)
from .generation import generate_app, translate_project, validate_manifest
from .schema import get_manifest_schema

ENGINE_MCP_TOOLS = (
    validate_manifest,
    translate_project,
    generate_app,
    list_target_profiles,
    describe_target_profile,
    list_archetypes,
    get_manifest_schema,
)

__all__ = [
    "ENGINE_MCP_TOOLS",
    "describe_target_profile",
    "generate_app",
    "get_manifest_schema",
    "list_archetypes",
    "list_target_profiles",
    "translate_project",
    "validate_manifest",
]

