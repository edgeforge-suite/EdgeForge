"""Manifest schema MCP tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from appbuilder.core import (
    CURRENT_MANIFEST_SCHEMA_FILENAME,
    CURRENT_MANIFEST_SCHEMA_VERSION,
    SUPPORTED_MANIFEST_SCHEMA_VERSIONS,
)


def get_manifest_schema(
    schema_version: str = CURRENT_MANIFEST_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Return the JSON Schema for a supported manifest version."""

    if schema_version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_MANIFEST_SCHEMA_VERSIONS))
        raise ValueError(
            "Unsupported manifest schema_version. "
            f"Supported versions: {supported}"
        )
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schema"
        / CURRENT_MANIFEST_SCHEMA_FILENAME
    )
    return json.loads(schema_path.read_text(encoding="utf-8"))
