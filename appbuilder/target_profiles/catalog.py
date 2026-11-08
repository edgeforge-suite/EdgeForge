"""Initial target profile catalog for generated applications."""

from __future__ import annotations

from pydantic import BaseModel


class TargetProfile(BaseModel):
    """Declares generation characteristics for a runtime compatibility target."""

    name: str
    language: str
    framework: str
    java_baseline: str | None = None
    spring_boot_baseline: str | None = None
    # Historical internal selector name; ordinary profiles now use this path too.
    experimental_boot41: bool = False
    emit_flyway: bool = False
    emit_spring_batch: bool = False
    emit_security: bool = False
    # Backward-compatible for custom/local profiles; shipped enterprise profiles
    # explicitly disable this non-production surface below.
    emit_test_console: bool = True
    emit_audit: bool = False
    supports_xml: bool = False
    runtime_database_dependency: str = "h2"
    datasource_url_template: str | None = None
    datasource_driver_class_name: str | None = None
    datasource_username: str | None = None
    datasource_password: str | None = None


TARGET_PROFILES: dict[str, TargetProfile] = {
    "springboot-legacy-compatible": TargetProfile(
        name="springboot-legacy-compatible",
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="4.1.1",
        experimental_boot41=True,
        emit_flyway=True,
        emit_spring_batch=True,
        emit_test_console=True,
        emit_audit=False,
        supports_xml=True,
        runtime_database_dependency="h2",
        datasource_url_template="jdbc:h2:mem:{db_name};MODE=PostgreSQL;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        datasource_driver_class_name="org.h2.Driver",
        datasource_username="sa",
        datasource_password="",
    ),
    "springboot-enterprise-postgres-java17": TargetProfile(
        name="springboot-enterprise-postgres-java17",
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="4.1.1",
        experimental_boot41=True,
        emit_flyway=True,
        emit_spring_batch=True,
        emit_test_console=False,
        emit_audit=True,
        supports_xml=True,
        runtime_database_dependency="postgresql",
        datasource_url_template="${SPRING_DATASOURCE_URL:jdbc:postgresql://localhost:5432/{db_name}}",
        datasource_driver_class_name="org.postgresql.Driver",
        datasource_username="${SPRING_DATASOURCE_USERNAME}",
        datasource_password="${SPRING_DATASOURCE_PASSWORD}",
    ),
    "springboot-standard-enterprise": TargetProfile(
        name="springboot-standard-enterprise",
        language="java",
        framework="spring-boot",
        java_baseline="21",
        spring_boot_baseline="4.1.1",
        experimental_boot41=True,
        emit_flyway=True,
        emit_spring_batch=True,
        emit_test_console=False,
        emit_audit=True,
        supports_xml=True,
        runtime_database_dependency="postgresql",
        datasource_url_template="${SPRING_DATASOURCE_URL:jdbc:postgresql://localhost:5432/{db_name}}",
        datasource_driver_class_name="org.postgresql.Driver",
        datasource_username="${SPRING_DATASOURCE_USERNAME}",
        datasource_password="${SPRING_DATASOURCE_PASSWORD}",
    ),
}

def equivalent_profiles(left: str, right: str) -> bool:
    """Aliases must agree in every runtime intention, not merely framework major."""
    first, second = TARGET_PROFILES.get(left), TARGET_PROFILES.get(right)
    return bool(first and second and first.model_dump(exclude={"name"}) == second.model_dump(exclude={"name"}))
