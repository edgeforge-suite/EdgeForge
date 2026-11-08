"""Generation-facing MCP tools for the EdgeForge Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from appbuilder.contracts import validate_package
from appbuilder.core.path_safety import (
    ALLOWED_ROOTS_ENV,
    resolve_allowed_file,
    resolve_allowed_path,
)
from appbuilder.generation import generate_application
from appbuilder.mcp.models import GenerationResult, TranslationResult, ValidationResult
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.models import MetadataProject

_ALLOWED_ROOTS_ENV = ALLOWED_ROOTS_ENV


def validate_manifest(manifest_path: str) -> ValidationResult:
    """
    Validate a manifest YAML file against the Engine schema.

    This intentionally matches validate_package() behavior and does not load
    referenced package files.
    """

    resolved_manifest = _resolve_allowed_file(manifest_path, purpose="manifest_path")
    try:
        with resolved_manifest.open("r", encoding="utf-8") as handle:
            raw: Any = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        return ValidationResult(valid=False, errors=[f"Invalid YAML: {exc}"], warnings=[])
    except OSError as exc:
        return ValidationResult(valid=False, errors=[str(exc)], warnings=[])

    errors = validate_package(raw)
    return ValidationResult(valid=not errors, errors=errors, warnings=[])


def translate_project(manifest_path: str) -> TranslationResult:
    """
    Translate a manifest package into a small canonical metadata summary.

    This is read-only and never invokes generated-app emitters.
    """

    resolved_manifest = _resolve_allowed_file(manifest_path, purpose="manifest_path")
    metadata = build_metadata_project(resolved_manifest)
    return TranslationResult(
        app_name=metadata.app_name,
        app_archetype=metadata.app_archetype.value,
        entity_count=len(metadata.entities),
        operation_count=len(metadata.operations),
        warnings=_collect_translation_warnings(metadata),
    )


def generate_app(manifest_path: str, output_dir: str) -> GenerationResult:
    """Translate a manifest package and emit a generated Spring Boot application."""

    resolved_manifest = _resolve_allowed_file(manifest_path, purpose="manifest_path")
    resolved_output_dir = _resolve_allowed_path(output_dir, purpose="output_dir")
    try:
        metadata = build_metadata_project(resolved_manifest)
        report = generate_application(
            metadata,
            resolved_output_dir,
            source_manifest=str(resolved_manifest),
        )
    except Exception as exc:
        return GenerationResult(
            success=False,
            output_dir=str(resolved_output_dir),
            files_written=[],
            warnings=[],
            errors=[str(exc)],
        )

    files_written = sorted(
        path.resolve().relative_to(resolved_output_dir).as_posix()
        for path in report.files_created
    )
    return GenerationResult(
        success=True,
        output_dir=str(report.output_dir.resolve()),
        files_written=files_written,
        warnings=list(report.warnings),
        errors=[],
    )


def _collect_translation_warnings(metadata: MetadataProject) -> list[str]:
    warnings: list[str] = []
    for report in metadata.mapping_reports:
        for issue in report.issues:
            warnings.append(f"{report.contract_name}: {issue.message}")
    warnings.extend(metadata.warnings)
    return warnings


def _resolve_allowed_file(path_value: str, *, purpose: str) -> Path:
    return resolve_allowed_file(path_value, purpose=purpose, mode="required")


def _resolve_allowed_path(path_value: str, *, purpose: str) -> Path:
    return resolve_allowed_path(path_value, purpose=purpose, mode="required")
