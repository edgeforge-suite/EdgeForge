"""Emit Flyway SQL migrations from canonical metadata."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalRelationship,
    IdGenerationStrategy,
    MetadataProject,
)
from appbuilder.target_profiles.catalog import TargetProfile

from .audit import render_generated_file_header
from .batch_metadata import batch_metadata_schema_sql, has_run_semantics, owns_batch_metadata
from .java_emitter import CANONICAL_TO_SQL, _field_requires_persistence_constraint
from .staging_idempotency import (
    reconcile_staging_internal_schemas,
    staging_unique_constraint_sql,
)
from .utils import all_entities, entity_id_field, to_snake_case

_AUDIT_SQL_COLUMNS = {
    "created_by": "created_by VARCHAR(255)",
    "created_at": "created_at TIMESTAMP",
    "modified_by": "modified_by VARCHAR(255)",
    "modified_at": "modified_at TIMESTAMP",
}

_INTEGER_LITERAL_PATTERN = re.compile(r"^[+-]?\d+$")
_DECIMAL_LITERAL_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


def emit_sql_files(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
    preserve_existing_migrations: bool = False,
    seed_migrations_if_absent: bool = False,
) -> list[Path]:
    if not target_profile.emit_flyway:
        return []

    migration_dir = output_dir / "src" / "main" / "resources" / "db" / "migration"
    migration_dir.mkdir(parents=True, exist_ok=True)
    if preserve_existing_migrations:
        existing_migrations = sorted(migration_dir.glob("V*.sql"))
        if existing_migrations or not seed_migrations_if_absent:
            return existing_migrations
    _clear_generated_migrations(migration_dir)

    ordered_entities = [entity for entity in _ordered_entities(metadata) if entity.fields]

    files: list[Path] = []
    for index, entity in enumerate(ordered_entities, start=1):
        migration_path = migration_dir / f"V{index}__create_{to_snake_case(entity.name)}_table.sql"
        migration_path.write_text(
            _render_migration(
                metadata=metadata,
                entity=entity,
                relationships=_relationships_for_entity(metadata, entity.name),
                target_profile=target_profile,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            ),
            encoding="utf-8",
        )
        files.append(migration_path)

    # emit Flyway migrations for staging/handoff tables.
    # The decoded DDL text is copied unchanged from the contract spec after translation
    # has enforced the fail-closed staging-DDL executable-input boundary. The accepted
    # spec remains authoritative; unsupported SQL is rejected rather than rewritten.
    # If a column is too narrow for UUID FK values, a generation warning is raised at
    # translation time (see translation.py _ingest_data_handoff) rather than silently
    # rewriting the contract here.
    staging_migration_start = len(ordered_entities) + 1
    internal_schemas = (
        reconcile_staging_internal_schemas(
            metadata=metadata,
            target_profile=target_profile,
            previous_entries={},
        )
        if has_run_semantics(metadata)
        else {}
    )
    schema_id_by_table = {
        entry["staging_table"]: schema_id
        for schema_id, entry in internal_schemas.items()
        if schema_id.startswith("m5a-staging-")
    }
    staging_table_items = list(metadata.staging_table_ddls.items())
    if internal_schemas:
        staging_table_items.sort(
            key=lambda item: (
                schema_id_by_table.get(item[0], "~"),
                item[0],
            )
        )
    for i, (table_name, ddl_content) in enumerate(staging_table_items):
        migration_path = migration_dir / f"V{staging_migration_start + i}__create_{table_name}_table.sql"
        header = render_generated_file_header(
            source_manifest=source_manifest,
            target_profile=target_profile.name,
            generation_run_id=generation_run_id,
            comment_style="sql",
        )
        migration_path.write_text(header + "\n" + ddl_content, encoding="utf-8")
        files.append(migration_path)

    if owns_batch_metadata(metadata, target_profile):
        batch_version = staging_migration_start + len(metadata.staging_table_ddls)
        migration_path = migration_dir / f"V{batch_version}__create_pkg_batch_metadata.sql"
        migration_path.write_text(
            _render_batch_metadata_migration(
                target_profile=target_profile,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            ),
            encoding="utf-8",
        )
        files.append(migration_path)

        staging_entries = [
            entry
            for schema_id, entry in sorted(internal_schemas.items())
            if schema_id.startswith("m5a-staging-")
        ]
        for offset, entry in enumerate(staging_entries, start=1):
            version = batch_version + offset
            migration_path = (
                migration_dir / f"V{version}__add_{entry['id'].replace('-', '_')}_unique.sql"
            )
            migration_path.write_text(
                _render_staging_unique_migration(
                    entry=entry,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
                encoding="utf-8",
            )
            files.append(migration_path)

    return files


def _render_batch_metadata_migration(
    *,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    """Render the package-scoped, Flyway-owned Spring Batch metadata migration."""

    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="sql",
    )
    return header + "\n" + batch_metadata_schema_sql(target_profile)


def _render_staging_unique_migration(
    *,
    entry: dict[str, Any],
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="sql",
    )
    return header + "\n" + staging_unique_constraint_sql(entry) + "\n"


def _clear_generated_migrations(migration_dir: Path) -> None:
    """Remove prior generated create-table migrations before rewriting the app.

    Studio Build & Run can regenerate into the same output directory multiple times.
    Without clearing old generated Flyway files first, stale versions like
    V2__create_account_table.sql can coexist with a newly emitted
    V2__create_multi_leg_posting_table.sql, causing Flyway startup failure with
    duplicate version numbers.
    """
    for migration_path in migration_dir.glob("V*__create_*_table.sql"):
        if _is_edgeforge_generated_migration(migration_path):
            migration_path.unlink()
    for migration_path in migration_dir.glob("V*__add_m5a_staging_*_unique.sql"):
        if _is_edgeforge_generated_migration(migration_path):
            migration_path.unlink()


def _is_edgeforge_generated_migration(migration_path: Path) -> bool:
    try:
        header = migration_path.read_text(encoding="utf-8", errors="ignore").splitlines()[:4]
    except OSError:
        return False
    return any("Generated by EdgeForge" in line for line in header)


def _render_migration(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    relationships: list[CanonicalRelationship],
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        comment_style="sql",
    )
    id_field = entity_id_field(entity)
    sequence_preamble: list[str] = []
    if id_field.id_generation_strategy == IdGenerationStrategy.DB_SEQUENCE:
        seq_name = id_field.id_sequence_name or f"{to_snake_case(id_field.name)}_seq"
        sequence_preamble.extend([f"CREATE SEQUENCE {seq_name};", ""])

    columns = [
        _render_column_definition(
            metadata=metadata,
            entity=entity,
            relationships=relationships,
            field=field,
            is_primary_key=field.name == id_field.name,
            target_profile=target_profile,
        )
        for field in entity.fields
    ]
    pattern_comments = [
        f"-- PATTERN: {to_snake_case(field.name)} => {field.pattern}"
        for field in entity.fields
        if field.pattern is not None
    ]
    if target_profile.emit_audit:
        existing_column_names = {to_snake_case(field.name) for field in entity.fields}
        for column_name, definition in _AUDIT_SQL_COLUMNS.items():
            if column_name not in existing_column_names:
                columns.append(definition)
    statements = [
        header,
        *sequence_preamble,
        *pattern_comments,
        f"CREATE TABLE {to_snake_case(entity.name)} (",
        ",\n".join(f"    {column}" for column in columns),
        ");",
    ]
    statements.extend(_render_foreign_key_constraints(entity, relationships))
    statements.append("")
    return "\n".join(statements)


def _render_column_definition(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    relationships: list[CanonicalRelationship],
    field: CanonicalField,
    is_primary_key: bool,
    target_profile: TargetProfile,
) -> str:
    column_name = to_snake_case(field.name)
    if field.format == "iso-4217":
        sql_type = "CHAR(3)"
    else:
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
                # Caller-supplied arbitrary string IDs remain wide; do not shrink them to
                # UUID width unless metadata proves Engine-owned UUID semantics.
                effective_length = 255
            else:
                effective_length = field.max_length or 255
            sql_type = sql_type.format(max_length=effective_length)
    parts = [f"{column_name} {sql_type}"]
    # DEFAULT is a column value clause, preceding H2's column constraints.
    if field.default_value is not None:
        parts.append(f"DEFAULT {_sql_literal(field)}")
    if _field_requires_persistence_constraint(
        metadata=metadata,
        entity=entity,
        field=field,
    ):
        parts.append("NOT NULL")
    for check_constraint in _column_check_constraints(field, column_name):
        parts.append(check_constraint)
    if is_primary_key and field.id_generation_strategy is not None:
        strategy = field.id_generation_strategy
        db = _resolve_database(target_profile)
        if strategy == IdGenerationStrategy.DB_IDENTITY:
            parts[0] = f"{column_name} BIGINT"
            if db == "postgresql":
                parts.append("GENERATED ALWAYS AS IDENTITY")
            elif db == "h2":
                parts.append("AUTO_INCREMENT")
        elif strategy == IdGenerationStrategy.DB_SEQUENCE:
            parts[0] = f"{column_name} BIGINT"
    if is_primary_key:
        parts.append("PRIMARY KEY")
    return " ".join(parts)


def _is_server_generated_uuid_string_id(
    field: CanonicalField,
    *,
    is_primary_key: bool,
) -> bool:
    if not is_primary_key or field.type.value != "string":
        return False
    if field.id_generation_strategy == IdGenerationStrategy.UUID:
        return True
    if field.id_generation_strategy is not None:
        return False
    return field.server_generated_id


def _is_uuid_reference_field(
    *,
    metadata: MetadataProject,
    relationships: list[CanonicalRelationship],
    field: CanonicalField,
) -> bool:
    if field.type.value != "string":
        return False
    for relationship in relationships:
        if relationship.source_field != field.name:
            continue
        target_entity = next(
            (
                candidate
                for candidate in metadata.entities
                if candidate.name == relationship.target_entity
            ),
            None,
        )
        if target_entity is None:
            continue
        target_id = entity_id_field(target_entity)
        if relationship.target_field != target_id.name:
            continue
        if _is_server_generated_uuid_string_id(target_id, is_primary_key=True):
            return True
    return False


def _resolve_database(target_profile: TargetProfile) -> str:
    """Return the normalized database identifier for DDL branching."""

    return target_profile.runtime_database_dependency


def _sql_literal(field: CanonicalField) -> str:
    raw_default = "" if field.default_value is None else str(field.default_value)
    if field.type.value == "integer":
        if not _INTEGER_LITERAL_PATTERN.fullmatch(raw_default):
            raise ValueError(
                f"Invalid SQL default for field '{field.name}': "
                "integer defaults must be integer literals."
            )
        return raw_default
    if field.type.value == "decimal":
        if not _DECIMAL_LITERAL_PATTERN.fullmatch(raw_default):
            raise ValueError(
                f"Invalid SQL default for field '{field.name}': "
                "decimal defaults must be numeric literals."
            )
        return raw_default
    if field.type.value == "boolean":
        normalized = raw_default.lower()
        if normalized not in {"true", "false"}:
            raise ValueError(
                f"Invalid SQL default for field '{field.name}': "
                "boolean defaults must be true or false."
            )
        return normalized
    return f"'{_escape_sql_string_default(field, raw_default)}'"


def _escape_sql_string_default(field: CanonicalField, value: str) -> str:
    for char in value:
        if ord(char) < 0x20:
            raise ValueError(
                f"Invalid SQL default for field '{field.name}': "
                "string/date defaults must not contain control characters."
            )
    return value.replace("'", "''")


def _column_check_constraints(field: CanonicalField, column_name: str) -> list[str]:
    checks: list[str] = []
    if field.type.value == "string" and field.min_length is not None:
        checks.append(f"CHECK (LENGTH({column_name}) >= {field.min_length})")

    range_clauses: list[str] = []
    if field.range_min is not None:
        range_clauses.append(f"{column_name} >= {_format_numeric_constraint(field.range_min)}")
    if field.range_max is not None:
        range_clauses.append(f"{column_name} <= {_format_numeric_constraint(field.range_max)}")
    if range_clauses:
        checks.append(f"CHECK ({' AND '.join(range_clauses)})")
    return checks


def _format_numeric_constraint(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _relationships_for_entity(
    metadata: MetadataProject,
    entity_name: str,
) -> list[CanonicalRelationship]:
    return [
        relationship
        for relationship in metadata.relationships
        if relationship.source_entity == entity_name
    ]


def _ordered_entities(metadata: MetadataProject) -> list[CanonicalEntity]:
    entities = all_entities(metadata)
    entity_lookup = {entity.name: entity for entity in entities}
    dependents: dict[str, list[str]] = {entity.name: [] for entity in entities}
    indegree: dict[str, int] = {entity.name: 0 for entity in entities}

    for relationship in metadata.relationships:
        if relationship.source_entity == relationship.target_entity:
            continue
        if (
            relationship.source_entity not in entity_lookup
            or relationship.target_entity not in entity_lookup
        ):
            continue
        dependents[relationship.target_entity].append(relationship.source_entity)
        indegree[relationship.source_entity] += 1

    queue = [entity.name for entity in entities if indegree[entity.name] == 0]
    ordered_names: list[str] = []

    while queue:
        current = queue.pop(0)
        ordered_names.append(current)
        for dependent in dependents[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)

    if len(ordered_names) != len(entities):
        remaining = sorted(name for name, degree in indegree.items() if degree > 0)
        raise ValueError(
            "Entity relationship cycle detected while ordering Flyway migrations: "
            f"{remaining}. Relationship cycles are not supported in Phase 1b v1."
        )

    return [entity_lookup[name] for name in ordered_names]


def _render_foreign_key_constraints(
    entity: CanonicalEntity,
    relationships: list[CanonicalRelationship],
) -> list[str]:
    statements: list[str] = []
    for relationship in relationships:
        constraint_name = (
            f"fk_{to_snake_case(entity.name)}_{to_snake_case(relationship.source_field)}"
        )
        statements.append(
            "ALTER TABLE "
            f"{to_snake_case(entity.name)} "
            f"ADD CONSTRAINT {constraint_name} "
            f"FOREIGN KEY ({to_snake_case(relationship.source_field)}) "
            f"REFERENCES {to_snake_case(relationship.target_entity)}"
            f"({to_snake_case(relationship.target_field)});"
        )
    return statements
