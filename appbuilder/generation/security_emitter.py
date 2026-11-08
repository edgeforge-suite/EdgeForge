"""Emit Spring Security resource-server scaffolding when enabled."""

from __future__ import annotations

from pathlib import Path

from appbuilder.metadata.models import MetadataProject
from appbuilder.target_profiles.catalog import TargetProfile

from .utils import _java_file, base_package, package_path


def emit_security_sources(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
) -> list[Path]:
    if not target_profile.emit_security:
        return []

    root_package = base_package(metadata)
    config_dir = output_dir / "src" / "main" / "java" / package_path(root_package) / "config"
    security_config_path = config_dir / "SecurityConfig.java"
    security_config_path.parent.mkdir(parents=True, exist_ok=True)
    security_config_path.write_text(
        _render_security_config(
            root_package=root_package,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    return [security_config_path]


def _render_security_config(
    *,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    body = [
        "@Configuration",
        "@EnableWebSecurity",
        "public class SecurityConfig {",
        "",
        "    @Bean",
        "    public SecurityFilterChain securityFilterChain(HttpSecurity httpSecurity) throws Exception {",
        "        httpSecurity",
        "            .csrf(AbstractHttpConfigurer::disable)",
        "            .sessionManagement(session ->",
        "                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))",
        "            .authorizeHttpRequests(authorize -> authorize",
        "                .requestMatchers(\"/actuator/health\").permitAll()",
        "                .anyRequest().authenticated()",
        "            )",
        "            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));",
        "",
        "        return httpSecurity.build();",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.config",
        imports=[
            "org.springframework.context.annotation.Bean",
            "org.springframework.context.annotation.Configuration",
            "org.springframework.security.config.Customizer",
            "org.springframework.security.config.annotation.web.builders.HttpSecurity",
            "org.springframework.security.config.annotation.web.configuration.EnableWebSecurity",
            "org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer",
            "org.springframework.security.config.http.SessionCreationPolicy",
            "org.springframework.security.web.SecurityFilterChain",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )
