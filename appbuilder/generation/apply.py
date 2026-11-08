"""Plan-hash-gated additive regeneration apply support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from appbuilder.core import AppArchetype
from appbuilder.metadata.models import CanonicalEntity, MetadataProject
from appbuilder.target_profiles.catalog import TARGET_PROFILES

from .audit import render_generated_file_header
from .batch_metadata import (
    BATCH_METADATA_SCHEMA_ID,
    batch_metadata_internal_schema,
    batch_metadata_schema_sql,
)
from .change_plan import build_change_plan
from .engine import GenerationReport, generate_application, require_supported_preview_input
from .file_writer import write_generated_file
from .java_emitter import _validate_computed_read_runtime_support
from .schema_baseline import (
    build_schema_baseline,
    emit_schema_baseline,
    flyway_high_water_mark_from_paths,
    load_schema_baseline,
)
from .sql_emitter import (
    _ordered_entities,
    _relationships_for_entity,
    _render_migration,
)
from .staging_idempotency import staging_unique_constraint_sql
from .utils import to_snake_case


@dataclass
class ApplyReport:
    """Summary of one approved additive apply run."""

    package_dir: Path
    plan_hash: str
    migrations_created: list[Path]
    baseline_path: Path
    generation_report: GenerationReport
    plan: dict[str, Any]


def apply_change_plan(
    *,
    metadata: MetadataProject,
    package_dir: str | Path,
    approved_plan_hash: str,
    source_manifest: str = "metadata-project",
    generation_run_id: str = "apply",
) -> ApplyReport:
    """Apply an approved additive Change Plan to an existing generated package.

    The method intentionally recomputes the Change Plan from the current manifest,
    committed baseline, and package state before touching files. Any hash drift,
    destructive delta, or unsafe delta fails closed.
    """

    require_supported_preview_input(metadata)
    if metadata.app_archetype == AppArchetype.CRUD:
        _validate_computed_read_runtime_support(metadata)
    package_path = Path(package_dir)
    plan = build_change_plan(metadata=metadata, package_dir=package_path)
    if plan["plan_hash"] != approved_plan_hash:
        raise ValueError(
            "Approved Change Plan hash does not match the current package state. "
            f"approved={approved_plan_hash} current={plan['plan_hash']}. "
            "Re-run appbuilder plan and approve the refreshed plan before applying."
        )
    if plan.get("mode") != "regenerate":
        raise ValueError(
            "appbuilder apply requires an existing generated package with a committed "
            "db/schema-baseline.json baseline."
        )

    blocking = [
        delta
        for delta in plan.get("deltas", [])
        if delta.get("classification") in {"unsafe", "destructive"}
    ]
    if blocking:
        summary = "; ".join(
            f"{delta.get('classification')} {delta.get('kind')} "
            f"{delta.get('entity') or ''}.{delta.get('field') or ''}: {delta.get('message')}"
            for delta in blocking[:5]
        )
        raise ValueError(
            "appbuilder apply supports additive-only Change Plans. "
            f"Unsafe/destructive changes must be handled manually: {summary}"
        )

    target_profile = TARGET_PROFILES[metadata.target_profile]
    if plan.get("db_migration_deltas") and not target_profile.emit_flyway:
        raise ValueError(
            "appbuilder apply requires Flyway-enabled target profiles for DB migration deltas."
        )
    new_baseline = build_schema_baseline(
        metadata=metadata,
        target_profile=target_profile,
        previous_baseline=load_schema_baseline(package_path),
    )
    rollback_snapshot = _capture_package_snapshot(package_path)
    try:
        migrations_created = _emit_additive_migrations(
            metadata=metadata,
            target_profile_name=target_profile.name,
            package_dir=package_path,
            plan=plan,
            new_baseline=new_baseline,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )

        # Commit the approved schema projection inside the rollback boundary so
        # regeneration cannot get ahead of its uniqueness migration.
        emit_schema_baseline(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=package_path,
            flyway_high_water_mark=flyway_high_water_mark_from_paths(
                (package_path / "src/main/resources/db/migration").glob("V*.sql")
            ),
            previous_baseline=load_schema_baseline(package_path),
        )

        generation_report = generate_application(
            metadata,
            package_path,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
        if (
            generation_report.harness_report is not None
            and not generation_report.harness_report.passed
        ):
            errors = "; ".join(
                f"{check.name}: {check.message}"
                for check in generation_report.harness_report.errors[:5]
            )
            raise ValueError(
                "Generated package failed compatibility harness after additive apply"
                + (f": {errors}" if errors else ".")
            )
        high_water_mark = flyway_high_water_mark_from_paths(
            (package_path / "src/main/resources/db/migration").glob("V*.sql")
        )
        baseline_path = emit_schema_baseline(
            metadata=metadata,
            target_profile=target_profile,
            output_dir=package_path,
            flyway_high_water_mark=high_water_mark,
            previous_baseline=load_schema_baseline(package_path),
        )
    except Exception:
        _restore_package_snapshot(package_path, rollback_snapshot)
        raise

    return ApplyReport(
        package_dir=package_path,
        plan_hash=plan["plan_hash"],
        migrations_created=migrations_created,
        baseline_path=baseline_path,
        generation_report=generation_report,
        plan=plan,
    )


def _emit_additive_migrations(
    *,
    metadata: MetadataProject,
    target_profile_name: str,
    package_dir: Path,
    plan: dict[str, Any],
    new_baseline: dict[str, Any],
    source_manifest: str,
    generation_run_id: str,
) -> list[Path]:
    deltas = [
        delta
        for delta in plan.get("db_migration_deltas", [])
        if delta.get("classification") == "additive"
    ]
    if not deltas:
        return []

    migration_dir = package_dir / "src" / "main" / "resources" / "db" / "migration"
    migration_dir.mkdir(parents=True, exist_ok=True)
    next_version = flyway_high_water_mark_from_paths(
        (package_dir / "src/main/resources/db/migration").glob("V*.sql")
    ) + 1
    created: list[Path] = []
    for delta in sorted(deltas, key=_delta_sort_key):
        migration_path, content = _render_additive_migration(
            metadata=metadata,
            target_profile_name=target_profile_name,
            migration_dir=migration_dir,
            version=next_version,
            delta=delta,
            new_baseline=new_baseline,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
        if migration_path.exists():
            raise ValueError(
                f"Refusing to overwrite existing Flyway migration {migration_path.name}."
            )
        created.append(write_generated_file(migration_path, content, ownership="generated"))
        next_version += 1
    return created


def _render_additive_migration(
    *,
    metadata: MetadataProject,
    target_profile_name: str,
    migration_dir: Path,
    version: int,
    delta: dict[str, Any],
    new_baseline: dict[str, Any],
    source_manifest: str,
    generation_run_id: str,
) -> tuple[Path, str]:
    kind = delta.get("kind")
    change = delta.get("change")
    if kind == "entity" and change == "added":
        entity_name = _required_delta_value(delta, "entity")
        entity = _entity_by_name(metadata, entity_name)
        path = migration_dir / f"V{version}__create_{to_snake_case(entity.name)}_table.sql"
        content = _render_migration(
            metadata=metadata,
            entity=entity,
            relationships=_relationships_for_entity(metadata, entity.name),
            target_profile=TARGET_PROFILES[metadata.target_profile],
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
        return path, content

    if kind == "field" and change == "added":
        entity_name = _required_delta_value(delta, "entity")
        field_name = _required_delta_value(delta, "field")
        path = (
            migration_dir
            / f"V{version}__alter_{to_snake_case(entity_name)}_add_{to_snake_case(field_name)}.sql"
        )
        content = _render_add_column_migration(
            delta=delta,
            new_baseline=new_baseline,
            source_manifest=source_manifest,
            target_profile_name=target_profile_name,
            generation_run_id=generation_run_id,
        )
        return path, content

    if kind == "staging_table" and change == "added":
        table_name = _required_delta_value(delta, "details").get("current", {}).get("name")
        if not table_name or table_name not in metadata.staging_table_ddls:
            raise ValueError(
                "Additive staging-table apply requires the new staging DDL to be present "
                f"in metadata for delta: {delta.get('message')}"
            )
        path = migration_dir / f"V{version}__create_{table_name}_table.sql"
        header = render_generated_file_header(
            source_manifest=source_manifest,
            target_profile=target_profile_name,
            generation_run_id=generation_run_id,
            comment_style="sql",
        )
        return path, header + "\n" + metadata.staging_table_ddls[table_name]

    if kind == "internal_schema" and change == "added":
        details = _required_delta_value(delta, "details")
        internal_schema = details.get("current") or {}
        schema_id = internal_schema.get("id")
        if schema_id == BATCH_METADATA_SCHEMA_ID:
            target_profile = TARGET_PROFILES[target_profile_name]
            expected = batch_metadata_internal_schema(target_profile)
            if internal_schema != expected:
                raise ValueError(
                    "Internal schema fingerprint does not match the pinned Spring Batch metadata "
                    "contract; refusing to emit an unverified migration."
                )
            path = migration_dir / f"V{version}__create_pkg_batch_metadata.sql"
            sql = batch_metadata_schema_sql(target_profile)
        elif isinstance(schema_id, str) and schema_id.startswith("m5a-staging-"):
            baseline_entry = next(
                (
                    entry
                    for entry in new_baseline.get("internal_schemas", [])
                    if entry.get("id") == schema_id
                ),
                None,
            )
            if internal_schema != baseline_entry:
                raise ValueError(
                    f"Internal schema '{schema_id}' does not match the projected baseline."
                )
            path = migration_dir / f"V{version}__add_{schema_id.replace('-', '_')}_unique.sql"
            sql = staging_unique_constraint_sql(internal_schema)
        else:
            raise ValueError(
                "Additive apply recognizes only package Batch metadata and M5a staging "
                f"internal schemas; got {schema_id!r}."
            )
        header = render_generated_file_header(
            source_manifest=source_manifest,
            target_profile=target_profile_name,
            generation_run_id=generation_run_id,
            comment_style="sql",
        )
        return path, header + "\n" + sql + "\n"

    if kind == "foreign_key" and change == "added":
        entity_name = _required_delta_value(delta, "entity")
        details = _required_delta_value(delta, "details")
        foreign_key = details.get("current") or {}
        constraint_name = foreign_key.get("name")
        if not constraint_name:
            raise ValueError(
                f"Additive foreign-key apply requires a constraint name: {delta.get('message')}"
            )
        path = (
            migration_dir
            / f"V{version}__alter_{to_snake_case(entity_name)}_add_{constraint_name}.sql"
        )
        content = _render_add_foreign_key_migration(
            delta=delta,
            source_manifest=source_manifest,
            target_profile_name=target_profile_name,
            generation_run_id=generation_run_id,
        )
        return path, content

    raise ValueError(
        "Additive apply currently supports new entities, new nullable/defaulted fields, "
        "new foreign keys, new staging tables, and M5a internal schemas. "
        f"Unsupported additive delta: {delta.get('message')}"
    )


def _render_add_column_migration(
    *,
    delta: dict[str, Any],
    new_baseline: dict[str, Any],
    source_manifest: str,
    target_profile_name: str,
    generation_run_id: str,
) -> str:
    entity_name = _required_delta_value(delta, "entity")
    field_name = _required_delta_value(delta, "field")
    entity_snapshot = _baseline_entity(new_baseline, entity_name)
    column = _baseline_column(entity_snapshot, field_name)
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
        comment_style="sql",
    )
    return "\n".join(
        [
            header,
            "",
            f"ALTER TABLE {entity_snapshot['table']} ADD COLUMN {_column_definition(column)};",
            "",
        ]
    )


def _render_add_foreign_key_migration(
    *,
    delta: dict[str, Any],
    source_manifest: str,
    target_profile_name: str,
    generation_run_id: str,
) -> str:
    details = _required_delta_value(delta, "details")
    foreign_key = details.get("current") or {}
    required_keys = ["name", "column", "target_table", "target_column"]
    missing = [key for key in required_keys if not foreign_key.get(key)]
    if missing:
        raise ValueError(
            f"Additive foreign-key delta is missing {', '.join(missing)}: {delta.get('message')}"
        )
    entity_table = to_snake_case(_required_delta_value(delta, "entity"))
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
        comment_style="sql",
    )
    return "\n".join(
        [
            header,
            "",
            "ALTER TABLE "
            f"{entity_table} ADD CONSTRAINT {foreign_key['name']} "
            f"FOREIGN KEY ({foreign_key['column']}) "
            f"REFERENCES {foreign_key['target_table']}({foreign_key['target_column']});",
            "",
        ]
    )


def _column_definition(column: dict[str, Any]) -> str:
    parts = [f"{column['name']} {column['sql_type']}"]
    if column.get("default") is not None:
        parts.append(f"DEFAULT {column['default']}")
    if column.get("nullable") is False:
        parts.append("NOT NULL")
    parts.extend(column.get("check_constraints") or [])
    return " ".join(parts)


def _baseline_entity(baseline: dict[str, Any], entity_name: str) -> dict[str, Any]:
    for entity in baseline.get("entities", []):
        if entity.get("entity") == entity_name:
            return entity
    raise ValueError(f"New baseline does not contain entity '{entity_name}'.")


def _baseline_column(entity_snapshot: dict[str, Any], field_name: str) -> dict[str, Any]:
    for column in entity_snapshot.get("columns", []):
        if column.get("field") == field_name:
            return column
    raise ValueError(
        f"New baseline does not contain field "
        f"'{entity_snapshot.get('entity')}.{field_name}'."
    )


def _entity_by_name(metadata: MetadataProject, entity_name: str) -> CanonicalEntity:
    for entity in _ordered_entities(metadata):
        if entity.name == entity_name:
            return entity
    raise ValueError(f"Metadata does not contain entity '{entity_name}'.")


def _required_delta_value(delta: dict[str, Any], key: str) -> Any:
    value = delta.get(key)
    if value is None or value == "":
        raise ValueError(f"Change Plan delta is missing required key '{key}': {delta}")
    return value


def _delta_sort_key(delta: dict[str, Any]) -> tuple[str, str, str, str]:
    kind = str(delta.get("kind") or "")
    details = delta.get("details") or {}
    schema_id = (details.get("current") or {}).get("id", "")
    internal_order = ""
    if kind == "internal_schema":
        internal_order = "0" if schema_id == BATCH_METADATA_SCHEMA_ID else f"1:{schema_id}"
    return (
        "1:internal_schema" if kind == "internal_schema" else f"0:{kind}",
        internal_order or str(delta.get("entity") or ""),
        str(delta.get("field") or ""),
        str(delta.get("message") or ""),
    )


def _capture_package_snapshot(package_dir: Path) -> dict[str, bytes]:
    if not package_dir.exists():
        return {}
    snapshot: dict[str, bytes] = {}
    for path in sorted(package_dir.rglob("*")):
        if path.is_file() and not _skip_apply_rollback_path(path):
            snapshot[path.relative_to(package_dir).as_posix()] = path.read_bytes()
    return snapshot


def _restore_package_snapshot(package_dir: Path, snapshot: dict[str, bytes]) -> None:
    expected = set(snapshot)
    if package_dir.exists():
        for path in sorted(package_dir.rglob("*"), reverse=True):
            if not path.is_file() or _skip_apply_rollback_path(path):
                continue
            relative = path.relative_to(package_dir).as_posix()
            if relative not in expected:
                path.unlink()
    for relative, content in snapshot.items():
        path = package_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _skip_apply_rollback_path(path: Path) -> bool:
    skipped_parts = {".git", ".gradle", ".idea", ".mvn", "target", "build", "node_modules"}
    return any(part in skipped_parts for part in path.parts)
