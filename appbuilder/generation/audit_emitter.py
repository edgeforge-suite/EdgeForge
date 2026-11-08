"""Emit JPA auditing scaffolding when enabled."""

from __future__ import annotations

from pathlib import Path

from appbuilder.metadata.models import MetadataProject
from appbuilder.target_profiles.catalog import TargetProfile

from .utils import _java_file, base_package, package_path


def emit_audit_sources(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
) -> list[Path]:
    if not target_profile.emit_audit:
        return []

    root_package = base_package(metadata)
    config_dir = output_dir / "src" / "main" / "java" / package_path(root_package) / "config"
    audit_config_path = config_dir / "AuditConfig.java"
    audit_config_path.parent.mkdir(parents=True, exist_ok=True)
    audit_config_path.write_text(
        _render_audit_config(
            root_package=root_package,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    return [audit_config_path]


def _render_audit_config(
    *,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    imports = [
        "java.util.Optional",
        "org.springframework.context.annotation.Bean",
        "org.springframework.context.annotation.Configuration",
        "org.springframework.data.domain.AuditorAware",
        "org.springframework.data.jpa.repository.config.EnableJpaAuditing",
    ]
    body = [
        "@Configuration",
        '@EnableJpaAuditing(auditorAwareRef = "auditorProvider")',
        "public class AuditConfig {",
        "",
    ]
    if not target_profile.emit_security:
        body.extend(
            [
                "    // NOTE: emit_security=False — auditorProvider will return \"system\"",
                "    //       for all requests until SSO security is enabled.",
                "",
            ]
        )
    body.extend(
        [
            "    @Bean",
            "    public AuditorAware<String> auditorProvider() {",
        ]
    )
    if target_profile.emit_security:
        imports.extend(
            [
                "org.springframework.security.core.Authentication",
                "org.springframework.security.core.context.SecurityContextHolder",
            ]
        )
        body.extend(
            [
                "        return () -> Optional.ofNullable(",
                "            SecurityContextHolder.getContext().getAuthentication()",
                "        )",
                "            .filter(Authentication::isAuthenticated)",
                "            .map(Authentication::getName)",
                "            .map(Optional::of)",
                '            .orElse(Optional.of("system"));',
            ]
        )
    else:
        body.append('        return () -> Optional.of("system");')
    body.extend(
        [
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.config",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )
