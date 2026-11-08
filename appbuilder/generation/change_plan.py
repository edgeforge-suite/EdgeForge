"""Read-only regenerate/maintain Change Plan dry-run support."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator

from appbuilder.core import AppArchetype
from appbuilder.mapping import FieldMapping
from appbuilder.metadata.models import MetadataProject
from appbuilder.target_profiles.catalog import TARGET_PROFILES, equivalent_profiles

from .batch_metadata import (
    BATCH_METADATA_SCHEMA_ID,
    reserved_batch_metadata_objects_in_sql,
)
from .framework_provenance import require_compatible_package
from .java_emitter import _validate_computed_read_runtime_support
from .regeneration import detect_generation_context, read_edgeforge_ownership
from .schema_baseline import (
    SCHEMA_BASELINE_RELATIVE_PATH,
    _engine_version,
    build_schema_baseline,
    flyway_high_water_mark_from_paths,
)
from .staging_idempotency import (
    internal_schema_migration_inventory_issues,
    staging_constraint_name_matches_entry,
    staging_unique_columns_match_entry,
    staging_unique_constraints_in_sql,
    unclassifiable_staging_unique_statements,
)

CHANGE_PLAN_SCHEMA_VERSION = "1.0"
CHANGE_PLAN_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "schema" / "change-plan-v1.schema.json"
)

ChangeClassification = Literal["none", "additive", "unsafe", "destructive"]


def build_change_plan(
    *,
    metadata: MetadataProject,
    package_dir: str | Path,
) -> dict[str, Any]:
    """Build a deterministic read-only Change Plan for an existing package."""

    from .write_contract import validate_write_contracts
    validate_write_contracts(metadata)
    if metadata.app_archetype == AppArchetype.CRUD:
        _validate_computed_read_runtime_support(metadata)
    package_path = Path(package_dir)
    target_profile = TARGET_PROFILES[metadata.target_profile]
    require_compatible_package(package_path, target_profile)
    generation_context = detect_generation_context(package_path)
    previous_baseline = generation_context.baseline
    new_baseline = build_schema_baseline(
        metadata=metadata,
        target_profile=target_profile,
        previous_baseline=previous_baseline,
    )

    baseline_hash = _stable_hash(previous_baseline) if previous_baseline else None
    package_state = _package_state_snapshot(package_path)
    package_state_hash = _stable_hash(package_state)
    warnings = list(generation_context.warnings)

    if previous_baseline:
        deltas = _schema_deltas(
            previous_baseline=previous_baseline,
            new_baseline=new_baseline,
        )
        deltas.extend(
            _internal_schema_inventory_deltas(
                package_path=package_path,
                deltas=deltas,
                previous_baseline=previous_baseline,
            )
        )
        deltas.sort(
            key=lambda delta: (
                str(delta.get("kind") or ""),
                str(delta.get("entity") or ""),
                str(delta.get("field") or ""),
                str(delta.get("change") or ""),
            )
        )
        mode = generation_context.mode
    else:
        deltas = _manifest_preview_deltas(new_baseline)
        mode = "manifest-only"
        warnings.append(
            "No committed schema baseline was found; Change Plan is manifest-only "
            "and contains no authoritative DB migration deltas."
        )

    edge_contract_impact = _edge_contract_impacts(
        metadata=metadata,
        deltas=deltas,
    )
    required_manual_actions = _required_manual_actions(deltas, edge_contract_impact)
    classification = _overall_classification(deltas)
    db_migration_deltas = [
        delta for delta in deltas if delta.get("db_migration_delta") is True
    ]

    plan_without_hash = {
        "change_plan_schema_version": CHANGE_PLAN_SCHEMA_VERSION,
        "engine_version": _engine_version(),
        "manifest_hash": new_baseline["manifest_hash"],
        "baseline_hash": baseline_hash,
        "target_profile": metadata.target_profile,
        "generated_app_id": {
            "app_name": metadata.app_name,
            "bounded_context": metadata.bounded_context,
            "package_name": package_path.name,
        },
        "package_state_hash": package_state_hash,
        "mode": mode,
        "classification": classification,
        "deltas": deltas,
        "db_migration_deltas": db_migration_deltas,
        "edge_contract_impact": edge_contract_impact,
        "required_manual_actions": required_manual_actions,
        "warnings": warnings,
    }
    plan_hash = _stable_hash(
        {
            "manifest_hash": plan_without_hash["manifest_hash"],
            "baseline_hash": baseline_hash,
            "package_state_hash": package_state_hash,
            "deltas": deltas,
            "classification": classification,
            "edge_contract_impact": edge_contract_impact,
            "required_manual_actions": required_manual_actions,
            "warnings": warnings,
        }
    )
    plan = {
        **plan_without_hash,
        "plan_id": f"change-plan-{plan_hash[:16]}",
        "plan_hash": plan_hash,
    }
    validate_change_plan(plan)
    return plan


def render_change_plan_json(plan: dict[str, Any]) -> str:
    """Render a stable Change Plan JSON document."""

    validate_change_plan(plan)
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def validate_change_plan(plan: dict[str, Any]) -> None:
    """Validate a Change Plan against the published v1 schema."""

    schema = json.loads(CHANGE_PLAN_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(plan)


def _schema_deltas(
    *,
    previous_baseline: dict[str, Any],
    new_baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []

    previous_profile = previous_baseline.get("target_profile")
    new_profile = new_baseline.get("target_profile")
    if previous_profile != new_profile and not equivalent_profiles(previous_profile, new_profile):
        deltas.append(
            {
                "kind": "profile",
                "change": "modified",
                "classification": "unsafe",
                "entity": None,
                "field": None,
                "db_migration_delta": False,
                "message": (
                    f"Target profile changed from '{previous_profile}' to '{new_profile}'."
                ),
                "details": {"previous": previous_profile, "current": new_profile},
            }
        )

    previous_entities = _entities_by_name(previous_baseline)
    new_entities = _entities_by_name(new_baseline)

    for entity_name in sorted(new_entities.keys() - previous_entities.keys()):
        deltas.append(
            {
                "kind": "entity",
                "change": "added",
                "classification": "additive",
                "entity": entity_name,
                "field": None,
                "db_migration_delta": True,
                "message": f"Entity '{entity_name}' is new and can be created additively.",
                "details": {"table": new_entities[entity_name].get("table")},
            }
        )

    for entity_name in sorted(previous_entities.keys() - new_entities.keys()):
        deltas.append(
            {
                "kind": "entity",
                "change": "removed",
                "classification": "destructive",
                "entity": entity_name,
                "field": None,
                "db_migration_delta": True,
                "message": (
                    f"Entity '{entity_name}' was removed; dropping tables is destructive."
                ),
                "details": {"table": previous_entities[entity_name].get("table")},
            }
        )

    for entity_name in sorted(previous_entities.keys() & new_entities.keys()):
        deltas.extend(
            _field_deltas(
                entity_name=entity_name,
                previous_entity=previous_entities[entity_name],
                new_entity=new_entities[entity_name],
            )
        )
        deltas.extend(
            _foreign_key_deltas(
                entity_name=entity_name,
                previous_entity=previous_entities[entity_name],
                new_entity=new_entities[entity_name],
            )
        )

    deltas.extend(_staging_table_deltas(previous_baseline, new_baseline))
    deltas.extend(_internal_schema_deltas(previous_baseline, new_baseline))
    return sorted(
        deltas,
        key=lambda delta: (
            str(delta.get("kind")),
            str(delta.get("entity") or ""),
            str(delta.get("field") or ""),
            str(delta.get("change")),
            str(delta.get("message")),
        ),
    )


def _field_deltas(
    *,
    entity_name: str,
    previous_entity: dict[str, Any],
    new_entity: dict[str, Any],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    previous_fields = _field_columns_by_name(previous_entity)
    new_fields = _field_columns_by_name(new_entity)

    for field_name in sorted(new_fields.keys() - previous_fields.keys()):
        new_column = new_fields[field_name]
        if new_column.get("nullable") is True or new_column.get("default") is not None:
            classification: ChangeClassification = "additive"
            message = (
                f"Field '{entity_name}.{field_name}' is new and nullable/defaulted."
            )
        else:
            classification = "unsafe"
            message = (
                f"Field '{entity_name}.{field_name}' is new and NOT NULL without a default; "
                "manual backfill is required."
            )
        deltas.append(
            {
                "kind": "field",
                "change": "added",
                "classification": classification,
                "entity": entity_name,
                "field": field_name,
                "db_migration_delta": True,
                "message": message,
                "details": {"current": _column_delta_view(new_column)},
            }
        )

    for field_name in sorted(previous_fields.keys() - new_fields.keys()):
        old_column = previous_fields[field_name]
        deltas.append(
            {
                "kind": "field",
                "change": "removed",
                "classification": "destructive",
                "entity": entity_name,
                "field": field_name,
                "db_migration_delta": True,
                "message": (
                    f"Field '{entity_name}.{field_name}' was removed; dropping columns is destructive."
                ),
                "details": {"previous": _column_delta_view(old_column)},
            }
        )

    for field_name in sorted(previous_fields.keys() & new_fields.keys()):
        old_column = previous_fields[field_name]
        new_column = new_fields[field_name]
        if _column_delta_view(old_column) == _column_delta_view(new_column):
            continue
        classification, reasons = _classify_column_modification(old_column, new_column)
        deltas.append(
            {
                "kind": "field",
                "change": "modified",
                "classification": classification,
                "entity": entity_name,
                "field": field_name,
                "db_migration_delta": True,
                "message": (
                    f"Field '{entity_name}.{field_name}' changed: {', '.join(reasons)}."
                ),
                "details": {
                    "previous": _column_delta_view(old_column),
                    "current": _column_delta_view(new_column),
                    "reasons": reasons,
                },
            }
        )
    return deltas


def _foreign_key_deltas(
    *,
    entity_name: str,
    previous_entity: dict[str, Any],
    new_entity: dict[str, Any],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    previous_keys = _foreign_keys_by_name(previous_entity)
    new_keys = _foreign_keys_by_name(new_entity)

    for constraint_name in sorted(new_keys.keys() - previous_keys.keys()):
        new_key = new_keys[constraint_name]
        field_name = _field_name_for_column(new_entity, new_key.get("column"))
        deltas.append(
            {
                "kind": "foreign_key",
                "change": "added",
                "classification": "additive",
                "entity": entity_name,
                "field": field_name,
                "db_migration_delta": True,
                "message": (
                    f"Foreign key '{constraint_name}' on '{entity_name}.{field_name}' "
                    "is new and can be added additively."
                ),
                "details": {"current": _foreign_key_delta_view(new_key)},
            }
        )

    for constraint_name in sorted(previous_keys.keys() - new_keys.keys()):
        old_key = previous_keys[constraint_name]
        field_name = _field_name_for_column(previous_entity, old_key.get("column"))
        deltas.append(
            {
                "kind": "foreign_key",
                "change": "removed",
                "classification": "destructive",
                "entity": entity_name,
                "field": field_name,
                "db_migration_delta": True,
                "message": (
                    f"Foreign key '{constraint_name}' on '{entity_name}.{field_name}' "
                    "was removed; dropping constraints is destructive."
                ),
                "details": {"previous": _foreign_key_delta_view(old_key)},
            }
        )

    for constraint_name in sorted(previous_keys.keys() & new_keys.keys()):
        old_key = previous_keys[constraint_name]
        new_key = new_keys[constraint_name]
        if _foreign_key_delta_view(old_key) == _foreign_key_delta_view(new_key):
            continue
        field_name = _field_name_for_column(
            new_entity,
            new_key.get("column"),
        ) or _field_name_for_column(
            previous_entity,
            old_key.get("column"),
        )
        deltas.append(
            {
                "kind": "foreign_key",
                "change": "modified",
                "classification": "destructive",
                "entity": entity_name,
                "field": field_name,
                "db_migration_delta": True,
                "message": (
                    f"Foreign key '{constraint_name}' on '{entity_name}.{field_name}' "
                    "changed; constraint changes are destructive without explicit migration policy."
                ),
                "details": {
                    "previous": _foreign_key_delta_view(old_key),
                    "current": _foreign_key_delta_view(new_key),
                },
            }
        )
    return deltas


def _classify_column_modification(
    previous_column: dict[str, Any],
    new_column: dict[str, Any],
) -> tuple[ChangeClassification, list[str]]:
    reasons: list[str] = []
    classes: list[ChangeClassification] = []

    previous_sql_type = previous_column.get("sql_type")
    new_sql_type = new_column.get("sql_type")
    if previous_sql_type != new_sql_type:
        widening = _varchar_length_change(previous_sql_type, new_sql_type)
        if widening == "widening":
            classes.append("unsafe")
            reasons.append(
                f"SQL type widened from {previous_sql_type} to {new_sql_type}; review required"
            )
        elif widening == "narrowing":
            classes.append("destructive")
            reasons.append(f"SQL type narrowed from {previous_sql_type} to {new_sql_type}")
        else:
            classes.append("destructive")
            reasons.append(f"SQL type changed from {previous_sql_type} to {new_sql_type}")

    if previous_column.get("nullable") != new_column.get("nullable"):
        if previous_column.get("nullable") is True and new_column.get("nullable") is False:
            classes.append("unsafe")
            reasons.append(
                "nullability tightened from nullable to NOT NULL; manual backfill is required"
            )
        else:
            classes.append("unsafe")
            reasons.append("nullability relaxed from NOT NULL to nullable; review required")

    if previous_column.get("default") != new_column.get("default"):
        classes.append("unsafe")
        reasons.append(
            f"default changed from {previous_column.get('default')} to {new_column.get('default')}"
        )

    if previous_column.get("check_constraints") != new_column.get("check_constraints"):
        classes.append("unsafe")
        reasons.append("check constraints changed")

    if previous_column.get("primary_key") != new_column.get("primary_key"):
        classes.append("unsafe")
        reasons.append("primary-key participation changed")

    if previous_column.get("canonical_type") != new_column.get("canonical_type"):
        classes.append("destructive")
        reasons.append(
            f"canonical type changed from {previous_column.get('canonical_type')} "
            f"to {new_column.get('canonical_type')}"
        )

    if not reasons:
        classes.append("unsafe")
        reasons.append("column metadata changed")

    return _max_classification(classes), reasons


def _staging_table_deltas(
    previous_baseline: dict[str, Any],
    new_baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    previous_tables = {
        table.get("name"): table
        for table in previous_baseline.get("staging_tables", [])
        if table.get("name")
    }
    new_tables = {
        table.get("name"): table
        for table in new_baseline.get("staging_tables", [])
        if table.get("name")
    }
    deltas: list[dict[str, Any]] = []
    for table_name in sorted(new_tables.keys() - previous_tables.keys()):
        deltas.append(
            {
                "kind": "staging_table",
                "change": "added",
                "classification": "additive",
                "entity": None,
                "field": None,
                "db_migration_delta": True,
                "message": f"Staging table '{table_name}' is new.",
                "details": {"current": new_tables[table_name]},
            }
        )
    for table_name in sorted(previous_tables.keys() - new_tables.keys()):
        deltas.append(
            {
                "kind": "staging_table",
                "change": "removed",
                "classification": "destructive",
                "entity": None,
                "field": None,
                "db_migration_delta": True,
                "message": f"Staging table '{table_name}' was removed.",
                "details": {"previous": previous_tables[table_name]},
            }
        )
    for table_name in sorted(previous_tables.keys() & new_tables.keys()):
        if previous_tables[table_name] == new_tables[table_name]:
            continue
        deltas.append(
            {
                "kind": "staging_table",
                "change": "modified",
                "classification": "unsafe",
                "entity": None,
                "field": None,
                "db_migration_delta": True,
                "message": f"Staging table '{table_name}' DDL checksum changed.",
                "details": {
                    "previous": previous_tables[table_name],
                    "current": new_tables[table_name],
                },
            }
        )
    return deltas


def _internal_schema_deltas(
    previous_baseline: dict[str, Any],
    new_baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    """Classify package-owned internal schema lifecycle changes.

    Removal is intentionally absent here: ``build_schema_baseline`` carries a
    retained schema forward after a run-semantics binding is removed, because
    dropping its Flyway-owned tables is destructive and never implicit.
    """

    previous_entries = {
        entry.get("id"): entry
        for entry in previous_baseline.get("internal_schemas", [])
        if isinstance(entry, dict) and entry.get("id")
    }
    new_entries = {
        entry.get("id"): entry
        for entry in new_baseline.get("internal_schemas", [])
        if isinstance(entry, dict) and entry.get("id")
    }
    deltas: list[dict[str, Any]] = []
    for schema_id in sorted(new_entries.keys() - previous_entries.keys()):
        current = new_entries[schema_id]
        rename_like = False
        if str(schema_id).startswith("m5a-staging-"):
            rename_like = any(
                str(previous_id).startswith("m5a-staging-")
                and (
                    previous.get("handoff_name") == current.get("handoff_name")
                    or previous.get("staging_table") == current.get("staging_table")
                )
                for previous_id, previous in previous_entries.items()
            )
        deltas.append(
            {
                "kind": "internal_schema",
                "change": "added",
                "classification": "destructive" if rename_like else "additive",
                "entity": None,
                "field": None,
                "db_migration_delta": True,
                "message": (
                    f"Internal schema '{schema_id}' is an unannotated handoff/table replacement; "
                    "the retained schema cannot be removed or renamed automatically."
                    if rename_like
                    else f"Internal schema '{schema_id}' is new and Flyway-owned."
                ),
                "details": {"current": current},
            }
        )
    for schema_id in sorted(previous_entries.keys() & new_entries.keys()):
        previous_entry = previous_entries[schema_id]
        new_entry = new_entries[schema_id]
        if previous_entry == new_entry:
            continue
        deltas.append(
            {
                "kind": "internal_schema",
                "change": "modified",
                "classification": "unsafe",
                "entity": None,
                "field": None,
                "db_migration_delta": True,
                "message": (
                    f"Internal schema '{schema_id}' changed version, profile, or fingerprint; "
                    "manual reconciliation is required."
                ),
                "details": {"previous": previous_entry, "current": new_entry},
            }
        )
    return deltas


def _internal_schema_inventory_deltas(
    *,
    package_path: Path,
    deltas: list[dict[str, Any]],
    previous_baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate retained ownership and reject untracked additive collisions."""

    inventory_deltas = [
        {
            "kind": "internal_schema",
            "change": "modified",
            "classification": "unsafe",
            "entity": None,
            "field": None,
            "db_migration_delta": False,
            "message": issue["message"],
            "details": issue,
        }
        for issue in internal_schema_migration_inventory_issues(
            package_path=package_path,
            entries=[
                entry
                for entry in previous_baseline.get("internal_schemas", [])
                if isinstance(entry, dict)
            ],
        )
    ]

    added_entries = [
        (delta.get("details") or {}).get("current", {})
        for delta in deltas
        if delta.get("kind") == "internal_schema"
        and delta.get("change") == "added"
        and delta.get("classification") == "additive"
    ]
    if not added_entries:
        return inventory_deltas
    migration_dir = package_path / "src/main/resources/db/migration"
    migration_paths = _flyway_sql_migration_paths(migration_dir)
    added_singleton = any(
        entry.get("id") == BATCH_METADATA_SCHEMA_ID for entry in added_entries
    )
    staging_entries = [
        entry
        for entry in added_entries
        if str(entry.get("id", "")).startswith("m5a-staging-")
    ]
    collision_paths: set[Path] = set()
    if added_singleton:
        collision_paths.update(
            path
            for path in migration_paths
            if path.name.startswith("V")
            and path.name.endswith("__create_pkg_batch_metadata.sql")
        )
    for entry in staging_entries:
        expected_suffix = f"__add_{entry['id'].replace('-', '_')}_unique.sql"
        collision_paths.update(
            path for path in migration_paths if path.name.endswith(expected_suffix)
        )
    reserved_objects_by_path: dict[Path, list[str]] = {}
    unclassifiable_unique_by_path: dict[Path, list[str]] = {}
    for migration_path in migration_paths:
        migration_sql = migration_path.read_text(encoding="utf-8")
        reserved_objects = reserved_batch_metadata_objects_in_sql(migration_sql)
        if reserved_objects and added_singleton:
            collision_paths.add(migration_path)
            reserved_objects_by_path[migration_path] = reserved_objects
        for entry in staging_entries:
            constraints = staging_unique_constraints_in_sql(
                migration_sql,
                target_profile_name=entry["target_profile"],
            )
            if any(
                staging_constraint_name_matches_entry(constraint, entry)
                or staging_unique_columns_match_entry(constraint, entry)
                for constraint in constraints
            ):
                collision_paths.add(migration_path)
            unclassifiable = unclassifiable_staging_unique_statements(
                migration_sql,
                entry=entry,
            )
            if unclassifiable:
                collision_paths.add(migration_path)
                unclassifiable_unique_by_path.setdefault(migration_path, []).extend(
                    unclassifiable
                )
    collisions = sorted(collision_paths)
    if not collisions:
        return inventory_deltas
    return inventory_deltas + [
        {
            "kind": "internal_schema",
            "change": "modified",
            "classification": "unsafe",
            "entity": None,
            "field": None,
            "db_migration_delta": False,
            "message": (
                "Package already contains an untracked M5a internal-schema migration, "
                "reserved Batch object, equivalent staging UNIQUE constraint, or "
                "unclassifiable executable UNIQUE targeting the managed staging table: "
                f"{', '.join(path.name for path in collisions)}."
            ),
            "details": {
                "paths": [path.name for path in collisions],
                "reserved_objects": {
                    path.name: reserved_objects_by_path[path]
                    for path in sorted(reserved_objects_by_path)
                },
                "unclassifiable_unique": {
                    path.name: unclassifiable_unique_by_path[path]
                    for path in sorted(unclassifiable_unique_by_path)
                },
            },
        }
    ]


def _flyway_sql_migration_paths(migration_dir: Path) -> list[Path]:
    """Inventory every SQL script Flyway can discover below its migration root."""

    return sorted(path for path in migration_dir.rglob("*.sql") if path.is_file())


def _manifest_preview_deltas(new_baseline: dict[str, Any]) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for entity in new_baseline.get("entities", []):
        entity_name = entity.get("entity")
        if not entity_name:
            continue
        deltas.append(
            {
                "kind": "entity",
                "change": "added",
                "classification": "additive",
                "entity": entity_name,
                "field": None,
                "db_migration_delta": False,
                "message": (
                    f"Entity '{entity_name}' is present in the manifest preview; "
                    "no DB migration delta is authoritative without a baseline."
                ),
                "details": {"table": entity.get("table")},
            }
        )
        for column in _field_columns_by_name(entity).values():
            field_name = column.get("field")
            if not field_name:
                continue
            deltas.append(
                {
                    "kind": "field",
                    "change": "added",
                    "classification": "additive",
                    "entity": entity_name,
                    "field": field_name,
                    "db_migration_delta": False,
                    "message": (
                        f"Field '{entity_name}.{field_name}' is present in the manifest preview; "
                        "no DB migration delta is authoritative without a baseline."
                    ),
                    "details": {"current": _column_delta_view(column)},
                }
            )
    return sorted(
        deltas,
        key=lambda delta: (
            str(delta.get("kind")),
            str(delta.get("entity") or ""),
            str(delta.get("field") or ""),
        ),
    )


def _edge_contract_impacts(
    *,
    metadata: MetadataProject,
    deltas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    impacts: list[dict[str, Any]] = []
    for delta in deltas:
        if delta.get("kind") != "field":
            continue
        if delta.get("change") not in {"removed", "modified"}:
            continue
        if delta.get("change") == "modified" and not _is_retyped_delta(delta):
            continue
        entity = delta.get("entity")
        field = delta.get("field")
        if not entity or not field:
            continue
        for mapping in _mappings_referencing_field(metadata.mappings, entity, field):
            impacts.append(
                {
                    "entity": entity,
                    "field": field,
                    "change": delta.get("change"),
                    "contract_name": mapping.contract_name,
                    "direction": str(mapping.direction.value),
                    "operation_name": mapping.operation_name,
                    "source_path": mapping.source_path,
                    "target_path": mapping.target_path,
                    "impact": (
                        f"Canonical field '{entity}.{field}' is referenced by "
                        f"contract mapping '{mapping.contract_name}'."
                    ),
                }
            )
    return sorted(
        impacts,
        key=lambda impact: (
            impact["contract_name"],
            impact["entity"],
            impact["field"],
            impact.get("operation_name") or "",
            impact["source_path"],
            impact["target_path"],
        ),
    )


def _mappings_referencing_field(
    mappings: list[FieldMapping],
    entity: str,
    field: str,
) -> list[FieldMapping]:
    return [
        mapping
        for mapping in mappings
        if _path_references_field(mapping.source_path, entity, field)
        or _path_references_field(mapping.target_path, entity, field)
    ]


def _path_references_field(path: str, entity: str, field: str) -> bool:
    needle = f"{entity}.{field}"
    if path == needle:
        return True
    return bool(re.search(rf"(^|[^A-Za-z0-9_]){re.escape(needle)}($|[^A-Za-z0-9_])", path))


def _is_retyped_delta(delta: dict[str, Any]) -> bool:
    details = delta.get("details") or {}
    previous = details.get("previous") or {}
    current = details.get("current") or {}
    return previous.get("canonical_type") != current.get("canonical_type") or previous.get(
        "sql_type"
    ) != current.get("sql_type")


def _required_manual_actions(
    deltas: list[dict[str, Any]],
    impacts: list[dict[str, Any]],
) -> list[str]:
    actions: list[str] = []
    for delta in deltas:
        classification = delta.get("classification")
        if classification in {"unsafe", "destructive"}:
            actions.append(
                f"Review {classification} {delta.get('kind')} change: {delta.get('message')}"
            )
    for impact in impacts:
        actions.append(
            "Review edge-contract mapping impact for "
            f"{impact['contract_name']} -> {impact['entity']}.{impact['field']}."
        )
    return sorted(dict.fromkeys(actions))


def _overall_classification(deltas: list[dict[str, Any]]) -> ChangeClassification:
    if not deltas:
        return "none"
    return _max_classification(
        [delta.get("classification", "none") for delta in deltas]
    )


def _max_classification(classes: list[str]) -> ChangeClassification:
    rank = {"none": 0, "additive": 1, "unsafe": 2, "destructive": 3}
    highest = max(classes or ["none"], key=lambda item: rank.get(item, 0))
    if highest not in rank:
        return "unsafe"
    return highest  # type: ignore[return-value]


def _entities_by_name(baseline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        entity["entity"]: entity
        for entity in baseline.get("entities", [])
        if entity.get("entity")
    }


def _field_columns_by_name(entity_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        column["field"]: column
        for column in entity_snapshot.get("columns", [])
        if column.get("field")
    }


def _foreign_keys_by_name(entity_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        foreign_key["name"]: foreign_key
        for foreign_key in entity_snapshot.get("foreign_keys", [])
        if foreign_key.get("name")
    }


def _column_delta_view(column: dict[str, Any]) -> dict[str, Any]:
    return {
        "field": column.get("field"),
        "column": column.get("name"),
        "canonical_type": column.get("canonical_type"),
        "sql_type": column.get("sql_type"),
        "nullable": column.get("nullable"),
        "default": column.get("default"),
        "check_constraints": column.get("check_constraints", []),
        "primary_key": column.get("primary_key", False),
        "max_length": column.get("max_length"),
        "min_length": column.get("min_length"),
    }


def _foreign_key_delta_view(foreign_key: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": foreign_key.get("name"),
        "column": foreign_key.get("column"),
        "target_table": foreign_key.get("target_table"),
        "target_column": foreign_key.get("target_column"),
    }


def _field_name_for_column(entity_snapshot: dict[str, Any], column_name: Any) -> str:
    if isinstance(column_name, str):
        for column in entity_snapshot.get("columns", []):
            if column.get("name") == column_name and column.get("field"):
                return str(column["field"])
        return column_name
    return ""


def _varchar_length_change(previous_sql_type: Any, new_sql_type: Any) -> str | None:
    previous = _varchar_length(previous_sql_type)
    new = _varchar_length(new_sql_type)
    if previous is None or new is None:
        return None
    if new > previous:
        return "widening"
    if new < previous:
        return "narrowing"
    return None


def _varchar_length(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"VARCHAR\((\d+)\)", value.strip(), flags=re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1))


def _package_state_snapshot(package_dir: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    package_files = sorted(package_dir.rglob("*")) if package_dir.exists() else []
    for path in package_files:
        if not path.is_file() or _should_skip_package_state_path(path):
            continue
        relative_path = path.relative_to(package_dir).as_posix()
        if relative_path == SCHEMA_BASELINE_RELATIVE_PATH.as_posix():
            continue
        ownership = read_edgeforge_ownership(path)
        is_migration = _is_flyway_migration(relative_path)
        if ownership not in {"generated", "developer"} and not is_migration:
            continue
        entries.append(
            {
                "path": relative_path,
                "sha256": _sha256_bytes(path.read_bytes()),
                "ownership": ownership,
                "kind": "flyway_migration" if is_migration else "owned_file",
            }
        )
    migrations = [entry for entry in entries if entry["kind"] == "flyway_migration"]
    return {
        "owned_files": [entry for entry in entries if entry["kind"] == "owned_file"],
        "flyway_migrations": migrations,
        "flyway_high_water_mark": flyway_high_water_mark_from_paths(
            Path(entry["path"]) for entry in migrations
        ),
    }


def _should_skip_package_state_path(path: Path) -> bool:
    skipped_parts = {".git", ".gradle", ".idea", ".mvn", "target", "build", "node_modules"}
    return any(part in skipped_parts for part in path.parts)


def _is_flyway_migration(relative_path: str) -> bool:
    return bool(
        re.fullmatch(
            r"src/main/resources/db/migration/V\d+__[^/]+\.sql",
            relative_path,
        )
    )


def _stable_hash(value: Any) -> str:
    return _sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
