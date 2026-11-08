"""Deterministic schema baseline emission for regeneration-aware generation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from appbuilder.metadata.models import CanonicalEntity, MetadataProject
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile, equivalent_profiles

from .batch_metadata import (
    BATCH_METADATA_SCHEMA_CONTRACT_VERSION,
    BATCH_METADATA_SCHEMA_ID,
    batch_metadata_internal_schema,
    owns_batch_metadata,
)
from .durable_json import load_durable_json
from .file_writer import write_generated_file
from .java_emitter import (
    CANONICAL_TO_SQL,
    _entity_java_artifact_plan,
    _fallback_create_request_class,
    _fallback_response_class,
    _fallback_update_request_class,
    _field_requires_persistence_constraint,
)
from .sql_emitter import (
    _AUDIT_SQL_COLUMNS,
    _column_check_constraints,
    _is_server_generated_uuid_string_id,
    _is_uuid_reference_field,
    _ordered_entities,
    _relationships_for_entity,
    _resolve_database,
    _sql_literal,
)
from .staging_idempotency import reconcile_staging_internal_schemas
from .utils import (
    base_package,
    entity_id_field,
    package_path,
    to_snake_case,
)

BASELINE_SCHEMA_VERSION = "1.0"
SCHEMA_BASELINE_RELATIVE_PATH = Path("db") / "schema-baseline.json"


def emit_schema_baseline(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    flyway_high_water_mark: int | None = None,
    previous_baseline: dict[str, Any] | None = None,
) -> Path:
    """Write the deterministic in-package schema baseline."""

    baseline_path = output_dir / SCHEMA_BASELINE_RELATIVE_PATH
    content = render_schema_baseline(
        metadata=metadata,
        target_profile=target_profile,
        flyway_high_water_mark=flyway_high_water_mark,
        previous_baseline=previous_baseline,
    )
    return write_generated_file(baseline_path, content, ownership="generated")


def load_schema_baseline(output_dir: Path) -> dict[str, Any] | None:
    """Return the committed schema baseline if one exists and parses."""

    baseline_path = output_dir / SCHEMA_BASELINE_RELATIVE_PATH
    if not baseline_path.exists():
        return None
    return load_durable_json(baseline_path)


def render_schema_baseline(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    flyway_high_water_mark: int | None = None,
    previous_baseline: dict[str, Any] | None = None,
) -> str:
    """Render a stable JSON snapshot of the currently emitted schema."""

    baseline = build_schema_baseline(
        metadata=metadata,
        target_profile=target_profile,
        flyway_high_water_mark=flyway_high_water_mark,
        previous_baseline=previous_baseline,
    )
    return json.dumps(baseline, indent=2, sort_keys=True) + "\n"


def build_schema_baseline(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    flyway_high_water_mark: int | None = None,
    previous_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ordered_entities = [entity for entity in _ordered_entities(metadata) if entity.fields]
    staging_tables = [
        {
            "name": table_name,
            "ddl_sha256": _sha256_text(ddl_content),
        }
        for table_name, ddl_content in sorted(metadata.staging_table_ddls.items())
    ]
    internal_schemas = _internal_schema_snapshots(
        metadata=metadata,
        target_profile=target_profile,
        previous_baseline=previous_baseline,
    )
    projected_high_water_mark = _flyway_high_water_mark(
        ordered_entities=ordered_entities,
        staging_table_count=len(staging_tables),
        target_profile=target_profile,
    )
    if owns_batch_metadata(metadata, target_profile) and target_profile.emit_flyway:
        projected_high_water_mark += 1 + sum(
            contract.run_semantics is not None for contract in metadata.contracts
        )
    retained_high_water_mark = (previous_baseline or {}).get("flyway_high_water_mark")
    if isinstance(retained_high_water_mark, int):
        projected_high_water_mark = max(projected_high_water_mark, retained_high_water_mark)
    baseline = {
        "baseline_schema_version": BASELINE_SCHEMA_VERSION,
        "engine_version": _engine_version(),
        "manifest_schema_version": metadata.schema_version,
        "manifest_hash": _manifest_hash(metadata),
        "target_profile": target_profile.name,
        "database": _resolve_database(target_profile),
        "emit_audit": bool(target_profile.emit_audit),
        "flyway_high_water_mark": (
            flyway_high_water_mark
            if flyway_high_water_mark is not None
            else projected_high_water_mark
        ),
        "entities": [
            _entity_schema_snapshot(
                metadata=metadata,
                entity=entity,
                target_profile=target_profile,
            )
            for entity in ordered_entities
        ],
        "staging_tables": staging_tables,
    }
    if internal_schemas:
        baseline["internal_schemas"] = internal_schemas
    return baseline


def _internal_schema_snapshots(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    previous_baseline: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Carry package-owned internal schemas across binding removal.

    The singleton belongs to the managed package, not to an individual handoff.
    A removed run-semantics binding therefore cannot silently remove its Flyway
    ownership record or cause a later re-enable to allocate another migration.
    """

    previous_entries = _validated_internal_schema_inventory(previous_baseline)
    previous_batch = previous_entries.get(BATCH_METADATA_SCHEMA_ID)
    projected_entries = reconcile_staging_internal_schemas(
        metadata=metadata,
        target_profile=target_profile,
        previous_entries=previous_entries,
    )

    if not owns_batch_metadata(metadata, target_profile):
        return _ordered_internal_schema_entries(projected_entries)

    current_batch = batch_metadata_internal_schema(target_profile)
    if previous_batch is None:
        projected_entries[BATCH_METADATA_SCHEMA_ID] = current_batch
        return _ordered_internal_schema_entries(projected_entries)

    if equivalent_profiles(previous_batch.get("target_profile"), current_batch["target_profile"]):
        retained_profile = target_profile.model_copy(update={"name": previous_batch["target_profile"]})
        if previous_batch.get("content_sha256") != batch_metadata_internal_schema(retained_profile)["content_sha256"]:
            raise ValueError(
                "Engine integrity failure: retained internal schema "
                f"'{BATCH_METADATA_SCHEMA_ID}' fingerprint drifted without a version change."
            )
        # Keep the committed bytes exactly; this is the no-op/re-enable path.
        projected_entries[BATCH_METADATA_SCHEMA_ID] = previous_batch
        return _ordered_internal_schema_entries(projected_entries)

    # Target-profile changes are represented for Change Plan classification. Apply
    # remains fail-closed on the resulting unsafe internal-schema delta.
    projected_entries[BATCH_METADATA_SCHEMA_ID] = current_batch
    return _ordered_internal_schema_entries(projected_entries)


def _ordered_internal_schema_entries(
    entries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        entries[schema_id]
        for schema_id in sorted(
            entries,
            key=lambda value: (value != BATCH_METADATA_SCHEMA_ID, value),
        )
    ]


def _validated_internal_schema_inventory(
    previous_baseline: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Validate committed package-owned schemas before projecting by ID."""

    raw_entries = (previous_baseline or {}).get("internal_schemas", [])
    if not isinstance(raw_entries, list):
        raise ValueError("Committed baseline internal_schemas must be an array.")

    entries: dict[str, dict[str, Any]] = {}
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            raise ValueError(
                f"Committed baseline internal_schemas[{index}] must be an object."
            )
        schema_id = raw_entry.get("id")
        if not isinstance(schema_id, str) or not schema_id.strip():
            raise ValueError(
                f"Committed baseline internal_schemas[{index}].id must be a non-empty string."
            )
        if schema_id in entries:
            raise ValueError(f"Duplicate internal schema id '{schema_id}' in committed baseline.")
        entries[schema_id] = dict(raw_entry)

    for schema_id, entry in entries.items():
        version = entry.get("schema_contract_version")
        target_profile_name = entry.get("target_profile")
        fingerprint = entry.get("content_sha256")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError(
                f"Internal schema '{schema_id}' has an invalid schema_contract_version: "
                f"{version!r}."
            )
        if not isinstance(target_profile_name, str) or not target_profile_name:
            raise ValueError(
                f"Internal schema '{schema_id}' has an invalid target_profile: "
                f"{target_profile_name!r}."
            )
        if not isinstance(fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
            raise ValueError(
                f"Internal schema '{schema_id}' has an invalid content_sha256 fingerprint."
            )

    previous_batch = entries.get(BATCH_METADATA_SCHEMA_ID)
    if previous_batch is None:
        return entries
    version = previous_batch["schema_contract_version"]
    if version != BATCH_METADATA_SCHEMA_CONTRACT_VERSION:
        raise ValueError(
            "Unsupported retained internal schema version for "
            f"'{BATCH_METADATA_SCHEMA_ID}': {version!r}."
        )
    target_profile_name = previous_batch["target_profile"]
    target_profile = TARGET_PROFILES.get(target_profile_name)
    if target_profile is None:
        raise ValueError(
            f"Internal schema '{BATCH_METADATA_SCHEMA_ID}' references unsupported target profile "
            f"'{target_profile_name}'."
        )
    expected = batch_metadata_internal_schema(target_profile)
    if previous_batch.get("spring_batch_metadata_schema_version") != expected[
        "spring_batch_metadata_schema_version"
    ]:
        raise ValueError(
            f"Internal schema '{BATCH_METADATA_SCHEMA_ID}' has an unsupported Spring Batch "
            "metadata schema version."
        )
    if previous_batch["content_sha256"] != expected["content_sha256"]:
        raise ValueError(
            "Engine integrity failure: retained internal schema "
            f"'{BATCH_METADATA_SCHEMA_ID}' fingerprint drifted without a version change."
        )
    return entries


def _entity_schema_snapshot(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    target_profile: TargetProfile,
) -> dict[str, Any]:
    relationships = _relationships_for_entity(metadata, entity.name)
    id_field = entity_id_field(entity)
    columns = [
        _field_schema_snapshot(
            metadata=metadata,
            entity=entity,
            relationships=relationships,
            field=field,
            is_primary_key=field.name == id_field.name,
            target_profile=target_profile,
        )
        for field in entity.fields
    ]
    if target_profile.emit_audit:
        existing_column_names = {to_snake_case(field.name) for field in entity.fields}
        for column_name, definition in sorted(_AUDIT_SQL_COLUMNS.items()):
            if column_name not in existing_column_names:
                sql_type = definition.split(" ", 1)[1]
                columns.append(
                    {
                        "field": None,
                        "name": column_name,
                        "canonical_type": None,
                        "sql_type": sql_type,
                        "nullable": True,
                        "default": None,
                        "check_constraints": [],
                        "primary_key": False,
                        "max_length": None,
                        "min_length": None,
                    }
                )
    return {
        "entity": entity.name,
        "table": to_snake_case(entity.name),
        "primary_key": {
            "field": id_field.name,
            "column": to_snake_case(id_field.name),
            "id_generation_strategy": (
                id_field.id_generation_strategy.value
                if id_field.id_generation_strategy is not None
                else None
            ),
            "sequence_name": id_field.id_sequence_name,
            "server_generated_id": id_field.server_generated_id,
        },
        "columns": columns,
        "foreign_keys": _foreign_key_snapshots(entity=entity, relationships=relationships),
        "generated_source_files": _generated_source_files_for_entity(
            metadata=metadata,
            entity=entity,
            target_profile=target_profile,
        ),
    }


def _field_schema_snapshot(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    relationships: list,
    field,
    is_primary_key: bool,
    target_profile: TargetProfile,
) -> dict[str, Any]:
    column_name = to_snake_case(field.name)
    sql_type = _effective_sql_type(
        metadata=metadata,
        relationships=relationships,
        field=field,
        is_primary_key=is_primary_key,
        target_profile=target_profile,
    )
    return {
        "field": field.name,
        "name": column_name,
        "canonical_type": field.type.value,
        "sql_type": sql_type,
        "nullable": not _field_requires_persistence_constraint(
            metadata=metadata,
            entity=entity,
            field=field,
        ),
        "default": _sql_literal(field) if field.default_value is not None else None,
        "check_constraints": _column_check_constraints(field, column_name),
        "primary_key": is_primary_key,
        "max_length": field.max_length,
        "min_length": field.min_length,
    }


def _effective_sql_type(
    *,
    metadata: MetadataProject,
    relationships: list,
    field,
    is_primary_key: bool,
    target_profile: TargetProfile,
) -> str:
    if field.format == "iso-4217":
        return "CHAR(3)"
    sql_type = CANONICAL_TO_SQL[field.type.value]
    if "{max_length}" in sql_type:
        if _is_server_generated_uuid_string_id(field, is_primary_key=is_primary_key):
            effective_length = 36
        elif _is_uuid_reference_field(
            metadata=metadata,
            relationships=relationships,
            field=field,
        ):
            effective_length = 36
        elif is_primary_key and field.type.value == "string":
            effective_length = 255
        else:
            effective_length = field.max_length or 255
        sql_type = sql_type.format(max_length=effective_length)
    if is_primary_key and field.id_generation_strategy is not None:
        if field.id_generation_strategy.value in {"db_identity", "db_sequence"}:
            return "BIGINT"
    return sql_type


def _foreign_key_snapshots(
    *,
    entity: CanonicalEntity,
    relationships: list,
) -> list[dict[str, str]]:
    snapshots: list[dict[str, str]] = []
    for relationship in relationships:
        snapshots.append(
            {
                "name": f"fk_{to_snake_case(entity.name)}_{to_snake_case(relationship.source_field)}",
                "column": to_snake_case(relationship.source_field),
                "target_table": to_snake_case(relationship.target_entity),
                "target_column": to_snake_case(relationship.target_field),
            }
        )
    return snapshots


def _flyway_high_water_mark(
    *,
    ordered_entities: list[CanonicalEntity],
    staging_table_count: int,
    target_profile: TargetProfile,
) -> int:
    if not target_profile.emit_flyway:
        return 0
    return len(ordered_entities) + staging_table_count


def flyway_high_water_mark_from_paths(paths: Iterable[Path]) -> int:
    """Return the greatest integer Flyway version represented by migration paths."""

    high_water_mark = 0
    for path in sorted(paths):
        match = re.match(r"V(\d+)__", path.name)
        if match:
            high_water_mark = max(high_water_mark, int(match.group(1)))
    return high_water_mark


def _generated_source_files_for_entity(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    target_profile: TargetProfile,
) -> list[str]:
    """Return deterministic entity-owned source files for orphan pruning.

    This is deliberately source-file inventory, not migration inventory. Flyway
    files are immutable and are handled by the later additive-delta slice.
    """

    root = Path("src") / "main" / "java" / package_path(base_package(metadata))
    artifact_plan = _entity_java_artifact_plan(
        metadata=metadata,
        entity=entity,
        target_profile=target_profile,
    )
    files = {
        root / "domain" / f"{entity.name}.java",
        root / "repository" / f"{entity.name}Repository.java",
        root / "service" / f"{entity.name}ServiceBase.java",
        root / "adapter" / "inbound" / f"{entity.name}Controller.java",
    }

    inbound_dir = root / "adapter" / "inbound"
    for context in artifact_plan.operation_contexts:
        files.add(inbound_dir / f"{context['request_class_name']}.java")
        files.add(inbound_dir / f"{context['response_class_name']}.java")

    if artifact_plan.emit_generic_fallback_dtos:
        if artifact_plan.emit_generic_create_fallback:
            files.add(inbound_dir / f"{_fallback_create_request_class(entity)}.java")
        files.add(inbound_dir / f"{_fallback_update_request_class(entity)}.java")
        files.add(inbound_dir / f"{_fallback_response_class(entity)}.java")

    outbound_dir = root / "adapter" / "outbound"
    for context in artifact_plan.file_writer_contexts:
        files.add(root / "adapter" / "outbound" / f"{context.writer_class_name}.java")
    if artifact_plan.emit_staging_writer:
        files.add(outbound_dir / f"{entity.name}StagingWriter.java")
    if artifact_plan.emit_batch_job:
        files.add(root / "batch" / f"{entity.name}EodBatchJob.java")

    return sorted(path.as_posix() for path in files)


def _manifest_hash(metadata: MetadataProject) -> str:
    payload = metadata.model_dump(mode="json")
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _engine_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        for line in pyproject_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version ="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        return "unknown"
    return "unknown"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
