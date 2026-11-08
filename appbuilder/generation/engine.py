"""Main orchestration for generated application output."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from appbuilder.core import AppArchetype
from appbuilder.harness import HarnessReport, run_compatibility_harness
from appbuilder.metadata.kafka_models import KafkaMetadata
from appbuilder.metadata.models import MetadataProject
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

from .audit_emitter import emit_audit_sources
from .batch_metadata import owns_batch_metadata
from .build_emitter import (
    emit_build_files,
    emit_passthrough_build_files,
    emit_repository_hygiene_files,
)
from .file_writer import write_generated_file
from .framework_provenance import emit_framework_provenance, require_compatible_package
from .java_emitter import (  # import emit_demo_controller
    _entity_java_artifact_plan,
    _validate_computed_read_runtime_support,
    _validate_file_contract_runtime_support,
    emit_demo_controller,
    emit_java_sources,
)
from .kafka_build_emitter import emit as emit_kafka_build_files
from .kafka_emitter import emit as emit_kafka_sources
from .passthrough_emitter import emit_passthrough_sources
from .regeneration import (
    GenerationContext,
    GenerationMode,
    detect_generation_context,
    protect_legacy_generated_files,
    prune_generated_artifacts,
    prune_orphaned_generated_sources,
    prune_stale_generated_java_sources,
    prune_stale_test_console_build_output,
)
from .schema_baseline import (
    build_schema_baseline,
    emit_schema_baseline,
    flyway_high_water_mark_from_paths,
)
from .security_emitter import emit_security_sources
from .security_headers_emitter import emit_security_headers_source
from .sql_emitter import emit_sql_files
from .staging_idempotency import internal_schema_migration_inventory_issues
from .ui_emitter import generate_demo_ui
from .utils import all_entities, base_package
from .utils import should_emit_demo_ui as _should_emit_demo_ui


@dataclass
class GenerationReport:
    """Summary of one generation run."""

    output_dir: Path
    files_created: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    harness_report: HarnessReport | None = None
    generation_mode: GenerationMode = "greenfield"


def generate_application(
    metadata: MetadataProject | KafkaMetadata,
    output_dir: str | Path,
    *,
    source_manifest: str = "metadata-project",
    generation_run_id: str | None = None,
) -> GenerationReport:
    """Generate a standalone application from normalized metadata."""

    archetype = metadata.app_archetype
    from .write_contract import validate_write_contracts
    validate_write_contracts(metadata)
    require_supported_preview_input(metadata)
    profile_name = metadata.target_profile_name if isinstance(metadata, KafkaMetadata) else metadata.target_profile
    require_compatible_package(Path(output_dir), TARGET_PROFILES[profile_name])
    if archetype == AppArchetype.KAFKA_INTEGRATION:
        return _generate_kafka_application(
            metadata,
            output_dir,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    if archetype == AppArchetype.CRUD:
        return _generate_crud_application(
            metadata,
            output_dir,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    if archetype == AppArchetype.PASSTHROUGH_ROUTER:
        return _generate_passthrough_application(
            metadata,
            output_dir,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    raise ValueError(f"Unknown app archetype '{archetype}'.")


def require_supported_preview_input(metadata: MetadataProject | KafkaMetadata) -> None:
    """Reject unsupported Boot 4.1 behavior before any output can be touched."""

    from .write_contract import validate_write_contracts
    validate_write_contracts(metadata)
    profile_name = (
        metadata.target_profile_name
        if isinstance(metadata, KafkaMetadata)
        else metadata.target_profile
    )
    target_profile = TARGET_PROFILES[profile_name]
    if not target_profile.experimental_boot41:
        return
    if metadata.app_archetype != AppArchetype.CRUD:
        return
    _validate_computed_read_runtime_support(metadata)
    for entity in (item for item in all_entities(metadata) if item.fields):
        plan = _entity_java_artifact_plan(
            metadata=metadata,
            entity=entity,
            target_profile=target_profile,
        )
        if _run_semantics_for_preview_entity(metadata, entity.name) and plan.has_downstream_file:
            raise ValueError(
                "M5a run_semantics cannot share an EOD file job "
                f"(entity '{entity.name}')."
            )


def _run_semantics_for_preview_entity(metadata: MetadataProject, entity_name: str) -> bool:
    return any(
        contract.run_semantics is not None
        and contract.run_semantics.entity_name == entity_name
        for contract in metadata.contracts
    )


def _generate_kafka_application(
    metadata: KafkaMetadata,
    output_dir: str | Path,
    *,
    source_manifest: str = "metadata-project",
    generation_run_id: str | None = None,
) -> GenerationReport:
    """Generate a Kafka topic-to-topic integration app."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if generation_run_id is None:
        generation_run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")

    files_created: list[Path] = []
    files_created.extend(
        _write_file_map(
            output_path,
            emit_kafka_build_files(
                metadata,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            ),
        )
    )
    files_created.extend(
        _write_file_map(
            output_path,
            emit_kafka_sources(
                metadata,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            ),
        )
    )
    files_created.append(
        emit_security_headers_source(
            root_package=metadata.java_package,
            target_profile_name=metadata.target_profile_name,
            output_dir=output_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )
    files_created.extend(
        emit_repository_hygiene_files(
            output_dir=output_path,
            bounded_context=metadata.bounded_context,
            target_profile_name=metadata.target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )

    files_created.append(emit_framework_provenance(output_path, TARGET_PROFILES[metadata.target_profile_name]))
    return GenerationReport(
        output_dir=output_path,
        files_created=files_created,
        warnings=[],
        harness_report=None,
    )


def _generate_crud_application(
    metadata: MetadataProject,
    output_dir: str | Path,
    *,
    source_manifest: str = "metadata-project",
    generation_run_id: str | None = None,
) -> GenerationReport:
    """Generate the existing entity-centric CRUD application lane."""

    from .write_contract import validate_write_contracts
    validate_write_contracts(metadata)
    _validate_computed_read_runtime_support(metadata)
    _validate_file_contract_runtime_support(metadata)

    # Guard: fail cleanly before touching the filesystem if the manifest produced
    # no entities with fields.  This catches empty / degenerate exports (e.g. from
    # Studio when no entities were classified, or when operations are present but
    # all selected entities are still fieldless) before the downstream emitters
    # crash with an unhelpful 'list index out of range' / IndexError.
    usable_entities = [e for e in metadata.entities if e.fields]
    has_xml_contracts = any(contract.type == "xml-xsd" for contract in metadata.contracts)
    has_soap_contracts = any(contract.type == "soap-wsdl" for contract in metadata.contracts)
    if not usable_entities and not has_xml_contracts and not has_soap_contracts:
        raise ValueError(
            f"Manifest '{source_manifest}' produced no entities with fields. "
            "Ensure at least one upstream interface or entity definition with "
            "at least one field is present in the manifest before generating."
        )
    target_profile = TARGET_PROFILES[metadata.target_profile]
    output_path = Path(output_dir)
    generation_context = detect_generation_context(output_path)
    _require_committed_run_semantics_schema(
        metadata=metadata,
        target_profile=target_profile,
        generation_context=generation_context,
        package_path=output_path,
    )
    output_path.mkdir(parents=True, exist_ok=True)
    legacy_warnings = (
        protect_legacy_generated_files(output_path)
        if generation_context.mode == "legacy"
        else []
    )

    if generation_run_id is None:
        generation_run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")

    emit_test_console = (
        target_profile.emit_test_console and _should_emit_demo_ui(metadata)
    )
    files_created: list[Path] = []
    files_created.extend(
        emit_build_files(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=output_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
            emit_test_console=emit_test_console,
        )
    )
    files_created.extend(
        emit_java_sources(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=output_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )
    files_created.extend(
        emit_security_sources(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=output_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )
    files_created.append(
        emit_security_headers_source(
            root_package=base_package(metadata),
            target_profile_name=target_profile.name,
            output_dir=output_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )
    files_created.extend(
        emit_audit_sources(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=output_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )
    migration_files = emit_sql_files(
        metadata=metadata,
        target_profile=target_profile,
        output_dir=output_path,
        source_manifest=source_manifest,
        generation_run_id=generation_run_id,
        preserve_existing_migrations=generation_context.mode in {"regenerate", "legacy"},
        seed_migrations_if_absent=generation_context.mode == "legacy",
    )
    files_created.extend(migration_files)
    if emit_test_console:
        files_created.append(
            generate_demo_ui(
                metadata=metadata,
                output_dir=output_path,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
        )
        # The demo controller backs the console's config-gated live-data viewer.
        files_created.append(
            emit_demo_controller(
                metadata=metadata,
                target_profile=target_profile,
                output_dir=output_path,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
        )
    console_warnings = (
        []
        if emit_test_console
        else prune_generated_artifacts(
            output_dir=output_path,
            relative_paths=(
                "src/main/resources/static/index.html",
                (
                    "src/main/java/"
                    f"{base_package(metadata).replace('.', '/')}/"
                    "adapter/inbound/DemoController.java"
                ),
            ),
            artifact_label="test-console",
        )
    )
    stale_console_build_warnings = (
        []
        if emit_test_console
        else prune_stale_test_console_build_output(
            output_dir=output_path,
            source_artifacts_pruned=bool(console_warnings),
        )
    )

    if generation_context.mode != "regenerate":
        files_created.append(
            emit_schema_baseline(
                metadata=metadata,
                target_profile=target_profile,
                output_dir=output_path,
                flyway_high_water_mark=(
                    flyway_high_water_mark_from_paths(migration_files)
                    if generation_context.mode == "legacy"
                    else None
                ),
                previous_baseline=generation_context.baseline,
            )
        )

    orphan_warnings = prune_orphaned_generated_sources(
        metadata=metadata,
        output_dir=output_path,
        previous_baseline=generation_context.baseline,
    )
    stale_java_warnings = (
        prune_stale_generated_java_sources(
            output_dir=output_path,
            current_files=files_created,
        )
        if generation_context.mode == "regenerate"
        else []
    )

    warnings = [
        *generation_context.warnings,
        *legacy_warnings,
        *console_warnings,
        *stale_console_build_warnings,
        *orphan_warnings,
        *stale_java_warnings,
        *_collect_generation_warnings(metadata),
    ]
    harness_report = run_compatibility_harness(metadata, output_path)
    warnings.extend(
        f"harness:{check.name}: {check.message}"
        for check in harness_report.checks
        if not check.passed
    )

    files_created.append(emit_framework_provenance(output_path, target_profile))
    return GenerationReport(
        output_dir=output_path,
        files_created=files_created,
        warnings=warnings,
        harness_report=harness_report,
        generation_mode=generation_context.mode,
    )


def _require_committed_run_semantics_schema(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    generation_context: GenerationContext,
    package_path: Path,
) -> None:
    """Validate internal-schema ownership before any generated file is written."""

    if generation_context.mode == "greenfield":
        if owns_batch_metadata(metadata, target_profile):
            # Projection validates allocation claims before output_dir is created.
            build_schema_baseline(metadata=metadata, target_profile=target_profile)
        return
    previous_baseline = generation_context.baseline
    if previous_baseline is None:
        if owns_batch_metadata(metadata, target_profile):
            raise ValueError(
                "Batch metadata generation into an existing package requires a committed schema "
                "baseline. Use a fresh package or appbuilder plan and approved apply."
            )
        return
    projected = build_schema_baseline(
        metadata=metadata,
        target_profile=target_profile,
        previous_baseline=previous_baseline,
    )
    inventory_issues = internal_schema_migration_inventory_issues(
        package_path=package_path,
        entries=[
            entry
            for entry in previous_baseline.get("internal_schemas", [])
            if isinstance(entry, dict)
        ],
    )
    if inventory_issues:
        raise ValueError(" ".join(issue["message"] for issue in inventory_issues))
    if not owns_batch_metadata(metadata, target_profile):
        return
    previous_entries = {
        entry.get("id"): entry for entry in previous_baseline.get("internal_schemas", [])
    }
    changed = [
        entry["id"]
        for entry in projected.get("internal_schemas", [])
        if previous_entries.get(entry["id"]) != entry
    ]
    if changed:
        raise ValueError(
            "run_semantics requires additive internal-schema migration(s) before regeneration: "
            f"{', '.join(changed)}. Use appbuilder plan and approved apply."
        )


def _generate_passthrough_application(
    metadata: MetadataProject,
    output_dir: str | Path,
    *,
    source_manifest: str = "metadata-project",
    generation_run_id: str | None = None,
) -> GenerationReport:
    """Generate the passthrough-router MVP without touching the CRUD emitters."""

    from .write_contract import validate_write_contracts
    validate_write_contracts(metadata)
    _validate_file_contract_runtime_support(metadata)

    target_profile = TARGET_PROFILES[metadata.target_profile]
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if generation_run_id is None:
        generation_run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")

    files_created: list[Path] = []
    files_created.extend(
        emit_passthrough_build_files(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=output_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )
    files_created.extend(
        emit_passthrough_sources(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=output_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )
    files_created.append(
        emit_security_headers_source(
            root_package=base_package(metadata),
            target_profile_name=target_profile.name,
            output_dir=output_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    )

    files_created.append(emit_framework_provenance(output_path, target_profile))
    return GenerationReport(
        output_dir=output_path,
        files_created=files_created,
        warnings=_collect_generation_warnings(metadata),
        harness_report=None,
    )


def _write_file_map(output_path: Path, files: dict[str, str]) -> list[Path]:
    written: list[Path] = []
    for relative_path, content in files.items():
        written.append(write_generated_file(output_path / relative_path, content))
    return written


def _collect_generation_warnings(metadata: MetadataProject) -> list[str]:
    warnings: list[str] = []
    for report in metadata.mapping_reports:
        for issue in report.issues:
            warning = f"{report.contract_name}: {issue.message}"
            if warning not in warnings:
                warnings.append(warning)
    # Include translation-time warnings (unsupported constructs, nested object skips, etc.)
    for warning in metadata.warnings:
        if warning not in warnings:
            warnings.append(warning)
    return warnings
