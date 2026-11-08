"""Catalog MCP tools for target profiles and archetypes."""

from __future__ import annotations

from appbuilder.core import AppArchetype
from appbuilder.mcp.models import ArchetypeSummary, ProfileDetail, ProfileSummary
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

_PROFILE_DESCRIPTIONS = {
    "springboot-legacy-compatible": (
        "Java 17 Spring Boot 4.1.1 profile for fresh apps with H2 compatibility defaults; no Boot 3 migration."
    ),
    "springboot-enterprise-postgres-java17": (
        "Java 17 Spring Boot 4.1.1 enterprise profile for fresh apps with PostgreSQL and audit defaults; no Boot 3 migration."
    ),
    "springboot-standard-enterprise": (
        "Java 21 Spring Boot 4.1.1 enterprise profile for fresh apps with PostgreSQL and audit defaults; no Boot 3 migration."
    ),
}

_ARCHETYPE_DESCRIPTIONS = {
    AppArchetype.CRUD.value: "Contract-preserving CRUD Spring Boot application.",
    AppArchetype.PASSTHROUGH_ROUTER.value: (
        "Stateless passthrough router for upstream-to-downstream request forwarding."
    ),
    AppArchetype.KAFKA_INTEGRATION.value: (
        "Kafka async mediation archetype for manifest-declared topic-to-topic adapters."
    ),
}


def list_target_profiles() -> list[ProfileSummary]:
    """List available target profiles with non-sensitive metadata."""

    return [
        _profile_summary(profile)
        for profile in sorted(TARGET_PROFILES.values(), key=lambda item: item.name)
    ]


def describe_target_profile(profile_name: str) -> ProfileDetail:
    """Return non-sensitive target profile details."""

    try:
        profile = TARGET_PROFILES[profile_name]
    except KeyError as exc:
        available = ", ".join(sorted(TARGET_PROFILES))
        raise ValueError(
            f"Unknown target profile '{profile_name}'. Available profiles: {available}"
        ) from exc

    summary = _profile_summary(profile)
    return ProfileDetail(
        **summary.model_dump(),
        language=profile.language,
        framework=profile.framework,
        spring_boot_version=profile.spring_boot_baseline or "",
        emit_flyway=profile.emit_flyway,
        emit_spring_batch=profile.emit_spring_batch,
        emit_security=profile.emit_security,
        supports_xml=profile.supports_xml,
        datasource_url_template=profile.datasource_url_template,
        datasource_driver_class_name=profile.datasource_driver_class_name,
    )


def list_archetypes() -> list[ArchetypeSummary]:
    """List supported app archetypes."""

    return [
        ArchetypeSummary(
            name=archetype.value,
            description=_ARCHETYPE_DESCRIPTIONS[archetype.value],
        )
        for archetype in AppArchetype
    ]


def _profile_summary(profile: TargetProfile) -> ProfileSummary:
    return ProfileSummary(
        name=profile.name,
        description=_PROFILE_DESCRIPTIONS.get(profile.name, profile.name),
        java_version=profile.java_baseline or "",
        database=profile.runtime_database_dependency,
        emit_audit=profile.emit_audit,
    )
