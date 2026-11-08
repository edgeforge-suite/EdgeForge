"""Structured result models for the EdgeForge Engine MCP tools."""

from __future__ import annotations

from pydantic import BaseModel


class ValidationResult(BaseModel):
    """Manifest validation summary."""

    valid: bool
    errors: list[str]
    warnings: list[str]


class TranslationResult(BaseModel):
    """Small translation summary for MCP callers."""

    app_name: str
    app_archetype: str
    entity_count: int
    operation_count: int
    warnings: list[str]


class GenerationResult(BaseModel):
    """Small generation summary for MCP callers."""

    success: bool
    output_dir: str
    files_written: list[str]
    warnings: list[str]
    errors: list[str]


class ProfileSummary(BaseModel):
    """Non-sensitive target profile summary."""

    name: str
    description: str
    java_version: str
    database: str
    emit_audit: bool


class ProfileDetail(ProfileSummary):
    """Non-sensitive target profile details."""

    language: str
    framework: str
    spring_boot_version: str
    emit_flyway: bool
    emit_spring_batch: bool
    emit_security: bool
    supports_xml: bool
    datasource_url_template: str | None
    datasource_driver_class_name: str | None


class ArchetypeSummary(BaseModel):
    """Supported application archetype summary."""

    name: str
    description: str
