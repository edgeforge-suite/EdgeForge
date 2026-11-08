"""Emit build, packaging, and configuration files for generated applications."""

from __future__ import annotations

import re
from pathlib import Path

from appbuilder.core import AppArchetype
from appbuilder.mapping import MappingDirection
from appbuilder.metadata.models import (
    ContractMetadata,
    IdentityRoleMode,
    MetadataProject,
)
from appbuilder.rules.models import CanonicalRule, RuleType
from appbuilder.target_profiles.catalog import TargetProfile

from .audit import render_generated_file_header, safe_source_manifest_label
from .batch_metadata import has_batch_jobs, owns_batch_metadata
from .container_policy import base_references
from .dependency_policy import policy_properties
from .file_writer import write_generated_file
from .passthrough_helpers import _system_env_var, _system_property_key
from .plugin_policy import build_plugins
from .utils import to_snake_case


def _to_artifact_id(name: str) -> str:
    """Convert a human-readable app name/bounded context into a safe Maven artifactId."""
    slug = name.lower().replace(" ", "-")
    slug = re.sub(r"[^a-zA-Z0-9_-]", "", slug)
    return slug or "generated-app"


def _emits_crud_service_seam(metadata: MetadataProject) -> bool:
    """Return whether Java generation emits an entity Service/ServiceBase pair."""

    return metadata.app_archetype == AppArchetype.CRUD and any(
        entity.fields for entity in metadata.entities
    )


def emit_repository_hygiene_files(
    *,
    output_dir: Path,
    bounded_context: str,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> list[Path]:
    """Scaffold adopter-owned repository ignore files without overwriting edits."""

    common = {
        "source_manifest": source_manifest,
        "target_profile_name": target_profile_name,
        "generation_run_id": generation_run_id,
        "bounded_context": bounded_context,
    }
    return [
        write_generated_file(
            output_dir / ".gitignore",
            _render_gitignore(**common),
            ownership="developer",
        ),
        write_generated_file(
            output_dir / ".dockerignore",
            _render_dockerignore(**common),
            ownership="developer",
        ),
    ]


def _render_gitignore(
    *,
    bounded_context: str,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
        comment_style="hash",
        ownership="developer",
    )
    return "\n".join(
        [
            header,
            "",
            "# Build output",
            "target/",
            "",
            "# IDE and operating-system metadata",
            ".idea/",
            ".vscode/",
            "*.iml",
            ".DS_Store",
            "",
            "# Local runtime state",
            "*.log",
            "*.mv.db",
            "*.trace.db",
            f"/{bounded_context}-eod/",
            "",
        ]
    )


def _render_dockerignore(
    *,
    bounded_context: str,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
        comment_style="hash",
        ownership="developer",
    )
    return "\n".join(
        [
            header,
            "",
            "# Source-control and build output",
            ".git/",
            ".github/",
            "target/",
            "",
            "# IDE and operating-system metadata",
            ".idea/",
            ".vscode/",
            "*.iml",
            ".DS_Store",
            "",
            "# Local runtime state",
            "*.log",
            "*.mv.db",
            "*.trace.db",
            f"{bounded_context}-eod/",
            "",
        ]
    )


def emit_build_files(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
    emit_test_console: bool,
    emit_tool_stubs: bool = False,
) -> list[Path]:
    files: list[Path] = []

    pom_path = output_dir / "pom.xml"
    pom_path.write_text(
        _render_pom_xml(
            metadata=metadata,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    files.append(pom_path)

    dockerfile_path = output_dir / "Dockerfile"
    dockerfile_path.write_text(
        _render_dockerfile(
            metadata=metadata,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    files.append(dockerfile_path)

    readme_path = output_dir / "README.md"
    readme_path.write_text(
        _render_readme(
            metadata=metadata,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
            emit_test_console=emit_test_console,
        ),
        encoding="utf-8",
    )
    files.append(readme_path)

    files.extend(
        _emit_agent_context_files(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=output_dir,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
            emit_test_console=emit_test_console,
            emit_tool_stubs=emit_tool_stubs,
        )
    )
    files.extend(
        emit_repository_hygiene_files(
            output_dir=output_dir,
            bounded_context=metadata.bounded_context,
            target_profile_name=target_profile.name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )

    resources_dir = output_dir / "src" / "main" / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    application_path = resources_dir / "application.yaml"
    application_path.write_text(
        _render_application_yaml(
            metadata=metadata,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    files.append(application_path)

    return files


def emit_passthrough_build_files(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
    emit_tool_stubs: bool = False,
) -> list[Path]:
    files: list[Path] = []

    pom_path = output_dir / "pom.xml"
    pom_path.write_text(
        _render_passthrough_pom_xml(
            metadata=metadata,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    files.append(pom_path)

    dockerfile_path = output_dir / "Dockerfile"
    dockerfile_path.write_text(
        _render_dockerfile(
            metadata=metadata,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    files.append(dockerfile_path)

    readme_path = output_dir / "README.md"
    readme_path.write_text(
        _render_passthrough_readme(
            metadata=metadata,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    files.append(readme_path)

    files.extend(
        _emit_agent_context_files(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=output_dir,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
            emit_test_console=False,
            emit_tool_stubs=emit_tool_stubs,
        )
    )
    files.extend(
        emit_repository_hygiene_files(
            output_dir=output_dir,
            bounded_context=metadata.bounded_context,
            target_profile_name=target_profile.name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )

    resources_dir = output_dir / "src" / "main" / "resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    application_path = resources_dir / "application.yaml"
    application_path.write_text(
        _render_passthrough_application_yaml(
            metadata=metadata,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    files.append(application_path)

    return files


def _render_pom_xml(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="xml",
    )
    artifact_id = _to_artifact_id(metadata.bounded_context)
    if target_profile.experimental_boot41:
        dependencies = [
            _dependency("org.springframework.boot", "spring-boot-starter-webmvc"),
            _dependency("org.springframework.boot", "spring-boot-starter-jackson"),
            _dependency("org.springframework.boot", "spring-boot-starter-validation"),
            _dependency("org.springframework.boot", "spring-boot-starter-data-jpa"),
            _dependency("org.springframework.boot", "spring-boot-starter-actuator"),
        ]
    else:
        dependencies = [
            _dependency("org.springframework.boot", "spring-boot-starter-web"),
            _dependency("org.springframework.boot", "spring-boot-starter-validation"),
            _dependency("org.springframework.boot", "spring-boot-starter-data-jpa"),
            _dependency("org.springframework.boot", "spring-boot-starter-actuator"),
        ]
    if _has_soap_contracts(metadata):
        dependencies.append(
            _dependency(
                "org.springframework.boot",
                "spring-boot-starter-webservices"
                if target_profile.experimental_boot41
                else "spring-boot-starter-web-services",
            )
        )
    if target_profile.emit_security:
        dependencies.append(
            _dependency(
                "org.springframework.boot",
                "spring-boot-starter-security-oauth2-resource-server"
                if target_profile.experimental_boot41
                else "spring-boot-starter-oauth2-resource-server",
            )
        )
    if target_profile.emit_spring_batch and (
        not target_profile.experimental_boot41 or has_batch_jobs(metadata, target_profile)
    ):
        dependencies.append(_dependency(
            "org.springframework.boot",
            "spring-boot-starter-batch-jdbc"
            if target_profile.experimental_boot41 else "spring-boot-starter-batch",
        ))
    if target_profile.emit_flyway:
        dependencies.append(
            _dependency(
                "org.springframework.boot" if target_profile.experimental_boot41 else "org.flywaydb",
                "spring-boot-starter-flyway" if target_profile.experimental_boot41 else "flyway-core",
            )
        )
        if target_profile.runtime_database_dependency == "postgresql":
            dependencies.append(_dependency("org.flywaydb", "flyway-database-postgresql"))
    if target_profile.runtime_database_dependency == "postgresql":
        dependencies.append(_dependency("org.postgresql", "postgresql", scope="runtime"))
    else:
        dependencies.append(_dependency("com.h2database", "h2", scope="runtime"))
    if target_profile.experimental_boot41:
        for starter in (
            "spring-boot-starter-webmvc-test",
            "spring-boot-starter-data-jpa-test",
            "spring-boot-starter-flyway-test",
        ):
            dependencies.append(_dependency("org.springframework.boot", starter, scope="test"))
        if _has_soap_contracts(metadata):
            dependencies.append(
                _dependency("org.springframework.boot", "spring-boot-starter-webservices-test", scope="test")
            )
    else:
        dependencies.append(_dependency("org.springframework.boot", "spring-boot-starter-test", scope="test"))

    return "\n".join(
        [
            header,
            "<project xmlns=\"http://maven.apache.org/POM/4.0.0\"",
            "         xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"",
            "         xsi:schemaLocation=\"http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd\">",
            "    <modelVersion>4.0.0</modelVersion>",
            "    <parent>",
            "        <groupId>org.springframework.boot</groupId>",
            "        <artifactId>spring-boot-starter-parent</artifactId>",
            f"        <version>{target_profile.spring_boot_baseline}</version>",
            "        <relativePath/>",
            "    </parent>",
            "    <groupId>com.appbuilder</groupId>",
            f"    <artifactId>{artifact_id}</artifactId>",
            "    <version>0.0.1-SNAPSHOT</version>",
            f"    <name>{metadata.app_name}</name>",
            f"    <description>{metadata.app_name} generated by EdgeForge</description>",
            "    <properties>",
            f"        <java.version>{target_profile.java_baseline}</java.version>",
            *policy_properties(target_profile.experimental_boot41),
            "    </properties>",
            "    <dependencies>",
            *dependencies,
            "    </dependencies>",
            "    <build>",
            "        <plugins>",
            *build_plugins(target_profile.experimental_boot41),
            "        </plugins>",
            "    </build>",
            "</project>",
            "",
        ]
    )


def _dependency(group_id: str, artifact_id: str, *, scope: str | None = None) -> str:
    lines = [
        "        <dependency>",
        f"            <groupId>{group_id}</groupId>",
        f"            <artifactId>{artifact_id}</artifactId>",
    ]
    if scope is not None:
        lines.append(f"            <scope>{scope}</scope>")
    lines.append("        </dependency>")
    return "\n".join(lines)


def _has_soap_contracts(metadata: MetadataProject) -> bool:
    return any(
        contract.type == "soap-wsdl"
        and contract.soap_contract
        for contract in metadata.contracts
    )


def _has_inbound_soap_contracts(metadata: MetadataProject) -> bool:
    return any(
        contract.type == "soap-wsdl"
        and contract.soap_contract
        and contract.soap_contract.get("direction") == "upstream"
        for contract in metadata.contracts
    )


def _render_dockerfile(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="hash",
    )
    java_version = target_profile.java_baseline
    artifact_name = _to_artifact_id(metadata.bounded_context)
    build_base, runtime_base = base_references(java_version)
    return "\n".join(
        [
            header,
            f"FROM {build_base} AS build",
            "WORKDIR /workspace",
            "COPY pom.xml .",
            "COPY src src",
            "RUN mvn -q -DskipTests clean package",
            "",
            f"FROM {runtime_base}",
            "WORKDIR /app",
            "RUN groupadd --system edgeforge && useradd --system --gid edgeforge --home-dir /app --shell /usr/sbin/nologin edgeforge",
            f"COPY --from=build --chown=edgeforge:edgeforge /workspace/target/{artifact_name}-0.0.1-SNAPSHOT.jar app.jar",
            "RUN chown -R edgeforge:edgeforge /app",
            "EXPOSE 8080",
            "HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget --quiet --tries=1 --spider http://localhost:8080/actuator/health || exit 1",
            "USER edgeforge",
            "ENTRYPOINT [\"java\", \"-jar\", \"/app/app.jar\"]",
            "",
        ]
    )


def _render_readme(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
    emit_test_console: bool,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="xml",
    )
    contract_lines = [f"- `{contract.name}` ({contract.type})" for contract in metadata.contracts]
    if _emits_crud_service_seam(metadata):
        ownership_lines = [
            (
                "- `src/main/java/.../service/{Entity}Service.java` is scaffolded "
                "once, marked `developer`, and preserved during regeneration. Put "
                "business logic in this subclass through its declared hooks."
            ),
            (
                "- `src/main/java/.../service/{Entity}ServiceBase.java` is marked "
                "`generated` and refreshed during regeneration."
            ),
            (
                "- Domain classes, repositories, controllers/adapters, generated "
                "DTOs, generated configuration, and generated migrations are "
                "regeneration-managed."
            ),
        ]
    else:
        ownership_lines = [
            (
                "- This adapter-only application does not emit the CRUD "
                "`Service`/`ServiceBase` extension seam. Add adopter logic in new "
                "developer-owned files rather than editing generated adapters."
            ),
            (
                "- Generated adapters, contract models/DTOs, generated "
                "configuration, and generated migrations are regeneration-managed."
            ),
        ]
    ownership_lines.extend(
        [
            (
                "- Existing generated Flyway migrations are immutable. Add schema "
                "changes through the reviewed plan/apply flow; do not rewrite an "
                "existing migration."
            ),
            (
                "- Ownership markers are authoritative: edit `developer` files; "
                "do not hand-edit `generated` files."
            ),
            "",
        ]
    )
    return "\n".join(
        [
            header,
            f"# {metadata.app_name}",
            "",
            f"Bounded context: `{metadata.bounded_context}`",
            f"Manifest schema version: `{metadata.schema_version}`",
            "",
            (
                "Generated by EdgeForge. Follow each file's `EdgeForge-ownership` "
                "marker before editing."
            ),
            "",
            (
                f"This is a `{metadata.app_archetype.value}` application generated by "
                "EdgeForge. It is **standalone** — it has no runtime dependency on "
                "EdgeForge, Studio, or the Knowledge Server, and preserves the upstream "
                "and downstream contracts listed below."
            ),
            "",
            (
                "**New here (human or AI agent)?** Read "
                "[`agent-context.md`](agent-context.md) first — it describes the preserved "
                "contracts, canonical entities, identity-role modes, rules, generation "
                "caveats, and where to add business logic."
            ),
            "",
            *_preview_readme_lines(target_profile),
            "## Ownership and regeneration",
            "",
            *ownership_lines,
            "## Build",
            "",
            "```bash",
            "mvn clean package",
            "```",
            "",
            "## Run",
            "",
            "```bash",
            "java -jar target/*.jar",
            "```",
            "",
            "Or build and run with Docker for **local development/testing only**:",
            "",
            "```bash",
            "docker build -t appbuilder-generated-app .",
            "docker run -p 127.0.0.1:8080:8080 appbuilder-generated-app",
            "```",
            "",
            *_deployment_security_note_lines(
                emit_security=target_profile.emit_security,
            ),
            *_test_console_posture_lines(
                emit_test_console=emit_test_console,
                emit_security=target_profile.emit_security,
            ),
            *(
                [
                    "## File/XML Runtime Directories",
                    "",
                    (
                        "If file or XML ingest/output actions are enabled, override "
                        "`APP_FILE_INGEST_BASE_DIR`, `APP_XML_INGEST_BASE_DIR`, and "
                        "`APP_XML_OUTPUT_BASE_DIR` to pin server-local directories. "
                        "The generated defaults include `APP_INSTANCE_ID` (falling "
                        "back to Spring `random.uuid`) to avoid shared `/tmp` "
                        "directories for co-located instances."
                    ),
                    "",
                ]
                if _has_file_or_xml_runtime_contract(metadata)
                else []
            ),
            "## Preserved Contracts",
            "",
            *contract_lines,
            "",
        ]
    )


def _deployment_security_note_lines(*, emit_security: bool = False) -> list[str]:
    return [
        "## Deployment security",
        "",
        *_deployment_security_posture_lines(emit_security=emit_security),
        "",
        "Container recipes use reviewed Noble multi-platform index pins "
        "(`ef-v5-noble-1`); recorded execution evidence is platform-specific, not ARM64 certification. "
        "Engine owns review before release or material security changes. Pins fix identity, "
        "not freshness or vulnerability status. Re-prove changed bases and plugin realms; "
        "do not silently substitute moved tags. Plugin dependencies are build-only, "
        "separate from the application BOM. Docker packaging skips tests; run the generated "
        "tests separately on the selected toolchain.",
        "",
    ]


def _preview_readme_lines(target_profile: TargetProfile) -> list[str]:
    if not target_profile.experimental_boot41:
        return []
    return [
        "## Spring Boot 4.1 Fresh Applications",
        "",
        "This profile explicitly selects Spring Boot 4.1.1 for a **fresh** "
        "application (ordinary profile IDs). Pre-v5 package/history migration is unsupported; it is not a cross-line upgrade "
        "procedure for an existing installation or Batch history. Evaluate CRUD/SOAP "
        "against a fresh database; do not reset an adopter database. "
        "Supported CRUD jobs use JDBC-backed Batch 6.0.5 with Flyway-owned metadata. "
        "Jobless output has no Batch runtime. H2 history lasts only within one JVM; "
        "PostgreSQL retains history across process replacement. Persisted running "
        "executions still require ownership review, never automatic recovery. "
        "Existing Boot 3 or ambiguous packages refuse generate/plan/apply before writes. "
        "Batch 5 history migration is not supported. Kafka uses its separate datasource-free lane.",
        "",
    ]


def _deployment_security_posture_lines(*, emit_security: bool = False) -> list[str]:
    if emit_security:
        posture_lines = [
            (
                "This generated app ships with plain HTTP and an OAuth2 resource-server "
                "security skeleton. Configure the enterprise issuer/JWKS, audience, and "
                "authority mapping before use. Deploy it behind a TLS-terminating, "
                "authenticated gateway or platform ingress."
            ),
        ]
    else:
        posture_lines = [
            (
                "This generated app ships with plain HTTP and no built-in authentication "
                "or authorization. Production deployment requires a TLS-terminating, "
                "authenticated gateway or platform ingress."
            ),
            (
                "The application port must be unreachable except through that gateway. "
                "All authenticated callers share one authorization domain and are trusted "
                "equally for all data the application exposes."
            ),
            (
                "Multi-tenant, per-user, object-level, and row-level authorization are "
                "unsupported until adopter-owned application authorization is implemented "
                "and adversarially tested."
            ),
        ]
    return [
        *posture_lines,
        "",
        (
            "Selected OpenAPI operations are not the whole emitted API. "
            "CRUD applications retain generic CRUD endpoints; their demo/batch "
            "controllers may add mappings. Review the "
            "emitted HTTP method/path surface. At the authenticated TLS gateway, expose "
            "only explicitly approved operations; keep unapproved CRUD/demo/batch "
            "operations inaccessible through it. Prohibit direct application-port access "
            "except through that gateway. Authentication is not endpoint exposure approval; "
            "neither supplies business, object, tenant, or row authorization. Engine does "
            "not generate an endpoint allowlist, gateway configuration, or endpoint suppression."
        ),
        "",
        (
            "Transport integer limitation (deferred post-v5): affected OpenAPI `int32` "
            "inputs remain Java `Long`; generated bindings do not enforce 32-bit bounds. "
            "Adopters requiring those bounds must validate them before business effects. "
            "This does not change persistence identity or database types."
        ),
        "",
        (
            "The generated `config/SecurityHeadersFilter.java` is a security control "
            "that sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, "
            "`Referrer-Policy: no-referrer`, and "
            "`Content-Security-Policy: frame-ancestors 'none'` on HTTP responses."
        ),
        (
            "It deliberately does not emit `Strict-Transport-Security`; configure HSTS "
            "at the TLS-terminating gateway after validating the complete HTTPS "
            "deployment boundary."
        ),
        "",
        (
            "Rate limiting is gateway-owned. This generated application does not enforce "
            "an in-application rate limit."
        ),
    ]


def _test_console_posture_lines(
    *,
    emit_test_console: bool,
    emit_security: bool,
) -> list[str]:
    if not emit_test_console:
        posture = "The non-production test console is not emitted in this generated app."
    elif emit_security:
        posture = (
            "The non-production test console is emitted and requires authentication "
            "through the generated OAuth2 resource-server configuration. Complete the "
            "enterprise IdP configuration before use; the console remains a "
            "non-production operator aid."
        )
    else:
        posture = (
            "The non-production test console is emitted for local development only. "
            "It is unauthenticated by design. Do not expose it to an untrusted network."
        )
    return ["## Test console", "", posture, ""]


def _has_file_or_xml_runtime_contract(metadata: MetadataProject) -> bool:
    return any(
        contract.type in {"file-fixed-width", "file-csv", "xml-xsd"}
        for contract in metadata.contracts
    )


_AGENT_CONTEXT_FILENAME = "agent-context.md"

# Opt-in only. Tool-specific stubs inside generated apps can conflict with the
# adopting organization's tooling/policy, so they are NOT emitted by default.
# They are emitted only when a caller passes emit_tool_stubs=True. Each value is
# (relative path, link prefix back to agent-context.md from that file's location).
_AGENT_TOOL_STUBS: tuple[tuple[str, str], ...] = (
    ("CLAUDE.md", ""),
    ("AGENTS.md", ""),
    (".github/copilot-instructions.md", "../"),
)


def _emit_agent_context_files(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
    emit_test_console: bool,
    emit_tool_stubs: bool = False,
) -> list[Path]:
    """Write the deterministic agent-context.md (always) and, only when opted in,
    thin tool-specific stubs that point back to it."""
    written: list[Path] = []

    agent_context_path = output_dir / _AGENT_CONTEXT_FILENAME
    agent_context_path.write_text(
        _render_agent_context(
            metadata=metadata,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
            emit_test_console=emit_test_console,
        ),
        encoding="utf-8",
    )
    written.append(agent_context_path)

    if emit_tool_stubs:
        for relative_path, link_prefix in _AGENT_TOOL_STUBS:
            stub_path = output_dir / relative_path
            stub_path.parent.mkdir(parents=True, exist_ok=True)
            stub_path.write_text(
                _render_agent_tool_stub(metadata=metadata, link_prefix=link_prefix),
                encoding="utf-8",
            )
            written.append(stub_path)

    return written


def _render_agent_tool_stub(*, metadata: MetadataProject, link_prefix: str) -> str:
    """Thin tool-specific onboarding stub (opt-in only). Points to agent-context.md
    instead of duplicating it."""
    return "\n".join(
        [
            f"# {metadata.app_name} — agent onboarding",
            "",
            (
                f"This is a `{metadata.app_archetype.value}` application generated by "
                "EdgeForge. It is standalone (no EdgeForge/Studio/Knowledge Server "
                "runtime dependency)."
            ),
            "",
            (
                f"Start from [`agent-context.md`]({link_prefix}agent-context.md) — it "
                "describes the preserved contracts, canonical entities, identity-role "
                "modes, rules, generation caveats, and where to add business logic. "
                "This file is a thin pointer; keep the canonical content there."
            ),
            "",
        ]
    )


def _contract_direction(
    contract: ContractMetadata, metadata: MetadataProject
) -> str | None:
    """Classify a preserved contract's edge direction from explicit signals only.

    Returns 'upstream', 'downstream', 'handoff', or None (unclassified). No
    inference: every result traces to a concrete metadata signal.
    """
    # 1. SOAP contracts carry an explicit direction.
    if contract.soap_contract:
        soap_direction = contract.soap_contract.get("direction")
        if soap_direction in {"upstream", "downstream"}:
            return soap_direction
    # 2. Explicit field mappings carry the authoritative edge direction.
    mapping_directions = {
        mapping.direction
        for mapping in metadata.mappings
        if mapping.contract_name == contract.name
    }
    if MappingDirection.UPSTREAM_TO_CANONICAL in mapping_directions:
        return "upstream"
    if MappingDirection.CANONICAL_TO_DOWNSTREAM in mapping_directions:
        return "downstream"
    if MappingDirection.CANONICAL_TO_HANDOFF in mapping_directions:
        return "handoff"
    # 3. An upstream REST interface is referenced by at least one operation.
    if any(operation.interface_name == contract.name for operation in metadata.operations):
        return "upstream"
    # 4. Datastore handoff: a staging table with a physical name.
    if contract.physical_name and contract.physical_name in metadata.staging_table_ddls:
        return "handoff"
    if contract.type == "staging-table":
        return "handoff"
    return None


def _rule_detail(rule: CanonicalRule) -> str:
    """A short, factual one-line descriptor of a rule's constraint (no inference)."""
    if rule.type == RuleType.ALLOWED_VALUES:
        return f"allowed values: {', '.join(rule.values)}" if rule.values else "allowed values"
    if rule.type == RuleType.DEFAULT:
        return f"default: {rule.value}"
    if rule.type == RuleType.MAX_LENGTH:
        return f"max length: {rule.max_length}"
    if rule.type == RuleType.MIN_LENGTH:
        return f"min length: {rule.min_length}"
    if rule.type == RuleType.PATTERN:
        return f"pattern: {rule.pattern}"
    if rule.type == RuleType.RANGE:
        return f"range: [{rule.range_min}, {rule.range_max}]"
    if rule.type == RuleType.NOT_NULL:
        return "not null"
    if rule.type == RuleType.FIELD_COMPARISON:
        compare = rule.compare_to_field or rule.target_field
        return f"compare {rule.operator or ''} `{compare}`".strip()
    if rule.type in {
        RuleType.CROSS_ENTITY_EXISTS,
        RuleType.CROSS_ENTITY_FIELD_CHECK,
        RuleType.CROSS_ENTITY_FIELD_COMPARE,
        RuleType.CROSS_ENTITY_FIELD_IN,
    }:
        target = ".".join(part for part in [rule.target_entity, rule.target_field] if part)
        return f"references `{target}`" if target else "cross-entity rule"
    return ""


def _render_agent_context(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
    emit_test_console: bool,
) -> str:
    """Render the deterministic agent-context.md from MetadataProject facts only.

    Same manifest + same generation run id -> byte-identical output. Every line
    traces to a MetadataProject field; nothing is inferred.
    """
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="xml",
    )

    lines: list[str] = [
        header,
        f"# Agent context — {metadata.app_name}",
        "",
        (
            "Generated by EdgeForge. This application is **standalone** — it has no "
            "runtime dependency on EdgeForge, Studio, the Knowledge Server, or MCP. "
            "Add business logic in the canonical core (see "
            "[§9 Where to add business logic](#9-where-to-add-business-logic)); keep the "
            "edges in §3 backward-compatible."
        ),
        "",
        "> Every section below is derived from the reviewed manifest — facts only, "
        "no inferred business meaning.",
        "",
    ]

    # 2. What this app is
    lines += [
        "## 2. What this app is",
        "",
        f"- Archetype: `{metadata.app_archetype.value}`",
        f"- Bounded context: `{metadata.bounded_context}`",
        f"- Manifest schema version: `{metadata.schema_version}`",
        f"- Target profile: `{metadata.target_profile}`",
        "",
        "Participating systems and their edge roles:",
        "",
    ]
    if metadata.systems:
        lines += [f"- `{system.name}` — role: {system.role}" for system in metadata.systems]
    else:
        lines.append("- (none declared)")
    lines.append("")

    # 3. Preserved contracts (the edges — do not break these)
    lines += [
        "## 3. Preserved contracts (the edges — do not break these)",
        "",
        "These are the upstream and downstream contracts this app must keep "
        "honoring. Treat their names, shapes, routes, and field names as fixed.",
        "",
    ]
    upstream = [c for c in metadata.contracts if _contract_direction(c, metadata) == "upstream"]
    downstream = [c for c in metadata.contracts if _contract_direction(c, metadata) == "downstream"]
    handoffs = [c for c in metadata.contracts if _contract_direction(c, metadata) == "handoff"]
    others = [c for c in metadata.contracts if _contract_direction(c, metadata) is None]

    lines += ["### Upstream interfaces (served by this app)", ""]
    if upstream:
        for contract in upstream:
            lines.append(f"- `{contract.name}` ({contract.type}) — source: `{contract.source}`")
            for operation in metadata.operations:
                if operation.interface_name != contract.name:
                    continue
                method = operation.http_method.value if operation.http_method else "?"
                path = operation.path or ""
                lines.append(f"    - {method} {path}".rstrip())
    else:
        lines.append("- (none)")
    lines.append("")

    lines += ["### Downstream interfaces", ""]
    if downstream:
        for contract in downstream:
            lines.append(f"- `{contract.name}` ({contract.type}) — source: `{contract.source}`")
    else:
        lines.append("- (none)")
    lines.append("")

    lines += ["### Data handoffs (datastore / staging tables)", ""]
    if handoffs:
        for contract in handoffs:
            physical = f", table `{contract.physical_name}`" if contract.physical_name else ""
            lines.append(f"- `{contract.name}` ({contract.type}{physical}) — source: `{contract.source}`")
    else:
        lines.append("- (none)")
    lines.append("")

    if others:
        lines += ["### Other preserved contracts", ""]
        lines += [
            f"- `{contract.name}` ({contract.type}) — source: `{contract.source}`"
            for contract in others
        ]
        lines.append("")

    # 4. Canonical entities & identity roles
    lines += [
        "## 4. Canonical entities & identity roles",
        "",
        "The internal canonical model. External contracts map into these entities; "
        "business logic should work against them, not the raw contract shapes.",
        "",
    ]
    if metadata.entities:
        for entity in metadata.entities:
            lines.append(f"- **{entity.name}**")
            for field in entity.fields:
                id_marker = " (id)" if field.is_id else ""
                lines.append(f"    - `{field.name}`: {field.type.value}{id_marker}")
    else:
        lines.append("- (no canonical entities)")
    lines.append("")

    lines += ["### Identity roles", ""]
    if metadata.identity_roles:
        lines.append(
            "Mode `active` = generated behavior is enforced; `metadata_only` = "
            "recorded for review but **not** enforced by generated code."
        )
        lines.append("")
        for role in metadata.identity_roles:
            enforced = (
                "generated/enforced"
                if role.mode == IdentityRoleMode.ACTIVE
                else "recorded, not enforced"
            )
            lines.append(
                f"- `{role.entity}.{role.field}`: {role.role.value} — "
                f"mode: {role.mode.value} ({enforced})"
            )
    else:
        lines.append(
            "No reviewed non-persistence identity roles. (Persistence IDs are the "
            "`(id)` fields above.)"
        )
    lines.append("")

    # 5. Business rules
    lines += [
        "## 5. Business rules",
        "",
        "Rules carried in the generated metadata are **generated and enforced** by "
        "this app (validation, defaulting, cross-entity checks). Advisory or "
        "metadata-only selections from authoring are not emitted as enforced rules "
        "and do not appear here.",
        "",
        "### Applied (generated & enforced)",
        "",
    ]
    if metadata.rules:
        for rule in metadata.rules:
            detail = _rule_detail(rule)
            suffix = f" — {detail}" if detail else ""
            lines.append(f"- `{rule.entity_name}.{rule.field_name}`: {rule.type.value}{suffix}")
    else:
        lines.append("- (none)")
    lines.append("")

    # 6. Generation notes & caveats
    ingestion_notes = [
        (contract.name, note)
        for contract in metadata.contracts
        for note in contract.ingestion_notes
    ]
    mapping_issues = [
        (report.contract_name, issue)
        for report in metadata.mapping_reports
        for issue in report.issues
    ]
    lines += ["## 6. Generation notes & caveats", ""]
    if ingestion_notes or mapping_issues or metadata.warnings:
        if ingestion_notes:
            lines += ["Ingestion notes:", ""]
            lines += [f"- `{name}`: {note}" for name, note in ingestion_notes]
            lines.append("")
        if mapping_issues:
            lines += ["Mapping completeness notes:", ""]
            lines += [
                f"- `{name}`: {issue.message} ({issue.severity.value})"
                for name, issue in mapping_issues
            ]
            lines.append("")
        if metadata.warnings:
            lines += ["Translation warnings:", ""]
            lines += [f"- {warning}" for warning in metadata.warnings]
            lines.append("")
    else:
        lines += ["- (no generation notes or warnings)", ""]

    # 7. Downstream handoff topology
    lines += ["## 7. Downstream handoff topology", ""]
    if handoffs or metadata.staging_table_ddls:
        if handoffs:
            for contract in handoffs:
                physical = contract.physical_name or "(no physical name)"
                lines.append(f"- handoff `{contract.name}` -> table `{physical}`")
        for physical_name in metadata.staging_table_ddls:
            lines.append(f"- staging-table DDL: `{physical_name}` (generated Flyway migration)")
    else:
        lines.append("- (no downstream table/datastore handoffs)")
    lines.append("")

    # 8. Config & secrets
    lines += [
        "## 8. Config & secrets",
        "",
        "Provide these via environment / `application.yaml` (no secret values are "
        "baked into the generated app):",
        "",
        "- Datasource: standard Spring datasource properties "
        "(`SPRING_DATASOURCE_URL` / `USERNAME` / `PASSWORD`) for the configured "
        "profile; the default dev profile uses in-memory H2.",
    ]
    if target_profile.emit_security:
        lines.append(
            "- OAuth2 resource-server issuer/JWK settings "
            "(`SPRING_SECURITY_OAUTH2_RESOURCESERVER_JWT_*`) — this profile emits "
            "security."
        )
    if _has_file_or_xml_runtime_contract(metadata):
        lines.append(
            "- File/XML local runtime directories can be pinned with "
            "`APP_FILE_INGEST_BASE_DIR`, `APP_XML_INGEST_BASE_DIR`, and "
            "`APP_XML_OUTPUT_BASE_DIR`; defaults include `APP_INSTANCE_ID` (or "
            "Spring `random.uuid`) so co-located instances do not share `/tmp` "
            "directories."
        )
    if emit_test_console:
        lines.append(
            "- Demo/live-data endpoints are gated by `appbuilder.demo.enabled` (off by "
            "default)."
        )
    lines += [
        "",
        "### Deployment security",
        "",
        *_deployment_security_posture_lines(
            emit_security=target_profile.emit_security,
        ),
        "",
    ]

    # 9. Where to add business logic
    lines += ["## 9. Where to add business logic", ""]
    if _emits_crud_service_seam(metadata):
        lines += [
            (
                "- **Developer-owned extension point:** "
                "`src/main/java/.../service/{Entity}Service.java` is scaffolded once "
                "and preserved. Add business logic there through the declared hooks."
            ),
            (
                "- **Generated service logic:** "
                "`src/main/java/.../service/{Entity}ServiceBase.java` is refreshed "
                "during regeneration."
            ),
            (
                "- **Regeneration-managed:** domain classes, repositories, "
                "controllers/adapters, generated DTOs, generated configuration, "
                "and generated migrations."
            ),
            (
                "- **Immutable history:** never rewrite an existing generated Flyway "
                "migration."
            ),
            (
                "- **Preserved edges:** do not change contract route paths, field "
                "names, or adapter DTO shapes without a reviewed contract change."
            ),
            (
                "- **Authority:** each file's `EdgeForge-ownership: generated` or "
                "`EdgeForge-ownership: developer` marker decides whether it may be "
                "edited and whether regeneration refreshes or preserves it."
            ),
            "",
        ]
    elif metadata.app_archetype == AppArchetype.CRUD:
        lines += [
            (
                "- This adapter-only application does not emit the CRUD "
                "`Service`/`ServiceBase` extension seam."
            ),
            (
                "- Add adopter logic in new developer-owned classes; do not "
                "hand-edit generated adapters, contract models/DTOs, or "
                "configuration."
            ),
            (
                "- **Immutable history:** never rewrite an existing generated "
                "Flyway migration."
            ),
            (
                "- **Preserved edges:** do not change contract route paths, field "
                "names, or adapter DTO shapes without a reviewed contract change."
            ),
            (
                "- **Authority:** each file's `EdgeForge-ownership: generated` or "
                "`EdgeForge-ownership: developer` marker decides whether it may be "
                "edited and whether regeneration refreshes or preserves it."
            ),
            "",
        ]
    else:
        lines += [
            (
                "- This passthrough-router archetype does **not** emit the CRUD "
                "`Service`/`ServiceBase` subclass seam."
            ),
            (
                "- Keep adopter logic in new adopter-owned classes; do not hand-edit "
                "generated transform, routing, adapter, or DTO files."
            ),
            (
                "- Preserve the route paths and field names of the §3 contracts. "
                "Ownership markers are authoritative: `generated` files are refreshed "
                "and `developer` files are preserved."
            ),
            "",
        ]

    # 10. Provenance
    lines += [
        "## 10. Provenance",
        "",
        f"- Source manifest: `{safe_source_manifest_label(source_manifest)}`",
        f"- Target profile: `{target_profile.name}`",
        f"- Generation run: `{generation_run_id}`",
        "",
    ]

    return "\n".join(lines)


def _render_application_yaml(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="hash",
    )
    db_name = to_snake_case(metadata.bounded_context)
    datasource_url_template = (
        target_profile.datasource_url_template
        or "jdbc:h2:mem:{db_name};MODE=PostgreSQL;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
    )
    datasource_driver_class_name = (
        target_profile.datasource_driver_class_name or "org.h2.Driver"
    )
    datasource_username = target_profile.datasource_username or "sa"
    datasource_password = (
        target_profile.datasource_password
        if target_profile.datasource_password is not None
        else ""
    )
    datasource_url = datasource_url_template.replace("{db_name}", db_name)
    lines = [
        header,
        "server:",
        "  port: 8080",
        "  shutdown: graceful",
        "spring:",
        "  lifecycle:",
        "    timeout-per-shutdown-phase: 30s",
        "  datasource:",
        f"    url: {datasource_url}",
        f"    driver-class-name: {datasource_driver_class_name}",
        f"    username: {datasource_username}",
        f"    password: {datasource_password}",
        "  jpa:",
        "    hibernate:",
        "      ddl-auto: validate",
        "    properties:",
        "      hibernate:",
        "        format_sql: true",
    ]
    if _has_inbound_soap_contracts(metadata):
        lines.extend(
            [
                "  webservices:",
                "    path: /ws",
                "    servlet:",
                "      init:",
                "        transformWsdlLocations: true",
            ]
        )
    batch_enabled = target_profile.emit_spring_batch and (
        not target_profile.experimental_boot41 or has_batch_jobs(metadata, target_profile)
    )
    if batch_enabled:
        lines.extend(["  batch:", "    job:", "      enabled: false"])
        if owns_batch_metadata(metadata, target_profile):
            lines.extend(["    jdbc:", "      initialize-schema: never"])
    if target_profile.emit_security:
        lines.extend(
            [
                "  security:",
                "    oauth2:",
                "      resourceserver:",
                "        jwt:",
                "          # TODO: set to your SSO provider issuer URI",
                "          # e.g. https://login.microsoftonline.com/{tenant-id}/v2.0",
                "          #      https://{issuer-domain}/oauth2/default",
                "          issuer-uri: https://replace-with-your-sso-provider.example.com/",
            ]
        )
    app_lines: list[str] = []
    if batch_enabled:
        app_lines.extend(
            [
                "  eod:",
                "    chunk-size: ${APP_EOD_CHUNK_SIZE:500}",
            ]
        )
    inbound_soap_contracts = _has_inbound_soap_contracts(metadata)
    outbound_soap_contracts = _outbound_soap_contracts(metadata)
    if inbound_soap_contracts or outbound_soap_contracts:
        app_lines.append("  soap:")
    if inbound_soap_contracts:
        app_lines.append(
            "    max-envelope-bytes: ${APP_SOAP_MAX_ENVELOPE_BYTES:1048576}"
        )
    if outbound_soap_contracts:
        app_lines.append("    clients:")
        for contract in outbound_soap_contracts:
            app_lines.extend(
                [
                    f"      {contract.name}:",
                    "        uri: http://localhost:8080/ws",
                ]
            )
    if app_lines:
        lines.extend(["app:", *app_lines])
    # appbuilder.demo section — disabled by default
    lines.extend(
        [
            "appbuilder:",
            "  demo:",
            "    enabled: false",
        ]
    )
    lines.extend(
        [
            "management:",
            "  endpoints:",
            "    web:",
            "      exposure:",
            "        include: health",
            "  endpoint:",
            "    health:",
            "      show-details: when-authorized",
            "      roles: ACTUATOR",
            "",
        ]
    )
    return "\n".join(lines)


def _outbound_soap_contracts(metadata: MetadataProject) -> list[ContractMetadata]:
    return [
        contract
        for contract in metadata.contracts
        if contract.type == "soap-wsdl"
        and contract.soap_contract
        and contract.soap_contract.get("direction") == "downstream"
    ]


def _render_passthrough_pom_xml(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="xml",
    )
    artifact_id = _to_artifact_id(metadata.bounded_context)
    if target_profile.experimental_boot41:
        dependencies = [
            _dependency("org.springframework.boot", "spring-boot-starter-webmvc"),
            _dependency("org.springframework.boot", "spring-boot-starter-restclient"),
            _dependency("org.springframework.boot", "spring-boot-starter-jackson"),
            _dependency("org.springframework.boot", "spring-boot-starter-validation"),
            _dependency("org.springframework.boot", "spring-boot-starter-actuator"),
            _dependency("org.springframework.boot", "spring-boot-starter-webmvc-test", scope="test"),
        ]
    else:
        dependencies = [
            _dependency("org.springframework.boot", "spring-boot-starter-web"),
            _dependency("org.springframework.boot", "spring-boot-starter-validation"),
            _dependency("org.springframework.boot", "spring-boot-starter-actuator"),
            _dependency("org.springframework.boot", "spring-boot-starter-test", scope="test"),
        ]
    return "\n".join(
        [
            header,
            "<project xmlns=\"http://maven.apache.org/POM/4.0.0\"",
            "         xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"",
            "         xsi:schemaLocation=\"http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd\">",
            "    <modelVersion>4.0.0</modelVersion>",
            "    <parent>",
            "        <groupId>org.springframework.boot</groupId>",
            "        <artifactId>spring-boot-starter-parent</artifactId>",
            f"        <version>{target_profile.spring_boot_baseline}</version>",
            "        <relativePath/>",
            "    </parent>",
            "    <groupId>com.appbuilder</groupId>",
            f"    <artifactId>{artifact_id}</artifactId>",
            "    <version>0.0.1-SNAPSHOT</version>",
            f"    <name>{metadata.app_name}</name>",
            f"    <description>{metadata.app_name} passthrough-router generated by EdgeForge</description>",
            "    <properties>",
            f"        <java.version>{target_profile.java_baseline}</java.version>",
            *policy_properties(target_profile.experimental_boot41),
            "    </properties>",
            "    <dependencies>",
            *dependencies,
            "    </dependencies>",
            "    <build>",
            "        <plugins>",
            *build_plugins(target_profile.experimental_boot41),
            "        </plugins>",
            "    </build>",
            "</project>",
            "",
        ]
    )


def _render_passthrough_readme(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="xml",
    )
    routing_rule = metadata.routing_rules[0]
    downstream_systems = [participant.name for participant in metadata.systems if participant.role == "downstream"]
    contract_lines = [f"- `{contract.name}` ({contract.type})" for contract in metadata.contracts]
    routing_lines = [
        f"- `{route.match}` -> `{route.target}`" for route in routing_rule.routes
    ]
    env_lines = [
        f"- `{_system_env_var(system)}` (default: `http://localhost:{8081 + index}`)"
        for index, system in enumerate(downstream_systems)
    ]
    return "\n".join(
        [
            header,
            f"# {metadata.app_name}",
            "",
            f"Bounded context: `{metadata.bounded_context}`",
            f"Manifest schema version: `{metadata.schema_version}`",
            "",
            (
                "Generated by EdgeForge. Follow each file's `EdgeForge-ownership` "
                "marker before editing; this archetype does not emit the CRUD "
                "`Service`/`ServiceBase` extension seam."
            ),
            "",
            (
                "This is a `passthrough-router` application generated by EdgeForge. It is "
                "**standalone** — no runtime dependency on EdgeForge, Studio, or the "
                "Knowledge Server."
            ),
            "",
            (
                "**New here (human or AI agent)?** Read "
                "[`agent-context.md`](agent-context.md) first for the full orientation "
                "(preserved contracts, routing, generation caveats, and where to add logic)."
            ),
            "",
            *_preview_readme_lines(target_profile),
            "## Archetype",
            "",
            "`passthrough-router` — REST in, deterministic transform, route to downstream REST targets.",
            "",
            "## Build",
            "",
            "```bash",
            "mvn clean package",
            "```",
            "",
            "## Run",
            "",
            "```bash",
            "java -jar target/*.jar",
            "```",
            "",
            *_deployment_security_note_lines(),
            "## Contracts",
            "",
            *contract_lines,
            "",
            "## Routing Rules",
            "",
            f"- route field: `{routing_rule.route_field}`",
            *routing_lines,
            f"- default -> `{routing_rule.default_target}`",
            "",
            "## Downstream Base URL Environment Variables",
            "",
            *env_lines,
            "",
        ]
    )


def _render_passthrough_application_yaml(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="hash",
    )
    downstream_systems = [participant.name for participant in metadata.systems if participant.role == "downstream"]
    lines = [
        header,
        "server:",
        "  port: 8080",
        "  shutdown: graceful",
        "spring:",
        "  lifecycle:",
        "    timeout-per-shutdown-phase: 30s",
        "downstream:",
    ]
    for index, system_name in enumerate(downstream_systems):
        default_port = 8081 + index
        property_key = _system_property_key(system_name)
        lines.extend(
            [
                f"  {property_key}:",
                f"    base-url: ${{{_system_env_var(system_name)}:http://localhost:{default_port}}}",
            ]
        )
    lines.extend(
        [
            "management:",
            "  endpoints:",
            "    web:",
            "      exposure:",
            "        include: health",
            "  endpoint:",
            "    health:",
            "      show-details: when-authorized",
            "      roles: ACTUATOR",
            "",
        ]
    )
    return "\n".join(lines)
