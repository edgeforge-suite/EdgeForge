"""Deterministic M5a staging uniqueness ownership and SQL rendering."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from appbuilder.metadata.models import ContractMetadata, MetadataProject
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile, equivalent_profiles

from .batch_metadata import (
    BATCH_METADATA_SCHEMA_ID,
    batch_metadata_internal_schema,
    normalized_batch_metadata_sql_statements,
    reserved_batch_metadata_objects_in_sql,
)

STAGING_SCHEMA_CONTRACT_VERSION = 1
STAGING_SCHEMA_ID_PATTERN = re.compile(r"^m5a-staging-([0-9]{3,})$")

_SQL_IDENTIFIER_PART = r'(?:[A-Za-z_][A-Za-z0-9_$]*|"(?:[^"]|"")+")'
_SQL_QUALIFIED_IDENTIFIER = rf"{_SQL_IDENTIFIER_PART}(?:\s*\.\s*{_SQL_IDENTIFIER_PART})?"

_UNIQUE_CONSTRAINT_PATTERN = re.compile(
    rf"\bALTER\s+TABLE\s+({_SQL_QUALIFIED_IDENTIFIER})\s+"
    rf"ADD\s+(?:CONSTRAINT\s+({_SQL_IDENTIFIER_PART})\s+)?"
    rf"UNIQUE\s*\(([^)]*)\)",
    re.IGNORECASE,
)
_UNIQUE_INDEX_PATTERN = re.compile(
    rf"\bCREATE\s+UNIQUE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    rf"({_SQL_IDENTIFIER_PART})\s+"
    rf"ON\s+({_SQL_QUALIFIED_IDENTIFIER})\s*\(([^)]*)\)",
    re.IGNORECASE,
)
_CREATE_TABLE_PATTERN = re.compile(
    rf"\bCREATE\s+TABLE\s+({_SQL_QUALIFIED_IDENTIFIER})\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_TABLE_UNIQUE_PATTERN = re.compile(
    rf"(?:\bCONSTRAINT\s+({_SQL_IDENTIFIER_PART})\s+)?\bUNIQUE\s*\(([^)]*)\)",
    re.IGNORECASE,
)
_ALTER_TABLE_REFERENCE_PATTERN = re.compile(
    rf"\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?"
    rf"({_SQL_QUALIFIED_IDENTIFIER})(?=\s|\(|$)",
    re.IGNORECASE,
)
_CREATE_TABLE_REFERENCE_PATTERN = re.compile(
    rf"\bCREATE\s+(?:(?:GLOBAL|LOCAL)\s+)?(?:TEMP(?:ORARY)?\s+|UNLOGGED\s+)?"
    rf"TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({_SQL_QUALIFIED_IDENTIFIER})(?=\s|\(|$)",
    re.IGNORECASE,
)
_CREATE_UNIQUE_INDEX_TABLE_PATTERN = re.compile(
    rf"\bCREATE\s+UNIQUE\s+INDEX\b.*?\bON\s+(?:ONLY\s+)?"
    rf"({_SQL_QUALIFIED_IDENTIFIER})(?=\s|\(|$)",
    re.IGNORECASE | re.DOTALL,
)


def reconcile_staging_internal_schemas(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    previous_entries: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Project per-handoff entries without replacing the baseline registry.

    Unrecognized, ambiguous, or malformed retained state is rejected. Disabled
    entries remain byte-identical, and ordinal gaps remain permanently reserved.
    """

    previous_staging = {
        schema_id: _validated_staging_entry(entry)
        for schema_id, entry in previous_entries.items()
        if schema_id.startswith("m5a-staging-")
    }
    candidates = [_candidate(contract) for contract in metadata.contracts if contract.run_semantics]
    allocation_tuples = [candidate["allocation_tuple"] for candidate in candidates]
    if len(set(allocation_tuples)) != len(allocation_tuples):
        raise ValueError("Duplicate M5a staging internal-schema allocation tuple detected.")

    projected = {schema_id: dict(entry) for schema_id, entry in previous_entries.items()}
    claimed_ids: set[str] = set()
    unannotated: list[dict[str, Any]] = []

    for candidate in candidates:
        annotation = candidate["internal_schema_id"]
        if annotation is None:
            unannotated.append(candidate)
            continue
        prior = previous_staging.get(annotation)
        if prior is None:
            raise ValueError(
                f"run_semantics internal_schema_id '{annotation}' for handoff "
                f"'{candidate['handoff_name']}' is absent from the committed baseline."
            )
        if annotation in claimed_ids:
            raise ValueError(
                f"Internal schema '{annotation}' is claimed by more than one staging handoff."
            )
        claimed_ids.add(annotation)
        projected[annotation] = staging_internal_schema_entry(
            candidate=candidate,
            schema_id=annotation,
            target_profile=_retained_alias_profile(target_profile, prior),
        )

    unmatched: list[dict[str, Any]] = []
    for candidate in unannotated:
        exact_matches = [
            (schema_id, entry)
            for schema_id, entry in previous_staging.items()
            if schema_id not in claimed_ids
            and entry["handoff_name"] == candidate["handoff_name"]
            and entry["staging_table"] == candidate["staging_table"]
        ]
        if len(exact_matches) > 1:
            raise ValueError(
                "Ambiguous M5a staging internal-schema match for handoff "
                f"'{candidate['handoff_name']}' and table '{candidate['staging_table']}'."
            )
        if exact_matches:
            schema_id, prior = exact_matches[0]
            claimed_ids.add(schema_id)
            current = staging_internal_schema_entry(
                candidate=candidate,
                schema_id=schema_id,
                target_profile=_retained_alias_profile(target_profile, prior),
            )
            projected[schema_id] = prior if current == prior else current
        else:
            unmatched.append(candidate)

    ordinals = [_staging_schema_ordinal(schema_id) for schema_id in previous_staging]
    next_ordinal = max(ordinals, default=0) + 1
    for candidate in sorted(unmatched, key=lambda item: item["allocation_bytes"]):
        schema_id = f"m5a-staging-{next_ordinal:03d}"
        projected[schema_id] = staging_internal_schema_entry(
            candidate=candidate,
            schema_id=schema_id,
            target_profile=target_profile,
        )
        next_ordinal += 1
    return projected


def _retained_alias_profile(profile: TargetProfile, prior: dict[str, Any]) -> TargetProfile:
    name = prior["target_profile"]
    return profile.model_copy(update={"name": name}) if equivalent_profiles(name, profile.name) else profile


def staging_internal_schema_entry(
    *,
    candidate: dict[str, Any],
    schema_id: str,
    target_profile: TargetProfile,
) -> dict[str, Any]:
    """Render one immutable-id, mutable-contract baseline entry."""

    return _staging_internal_schema_entry(
        candidate=candidate,
        schema_id=schema_id,
        target_profile_name=target_profile.name,
    )


def _staging_internal_schema_entry(
    *, candidate: dict[str, Any], schema_id: str, target_profile_name: str
) -> dict[str, Any]:
    """Render an entry from its stable target-profile name."""

    _staging_schema_ordinal(schema_id)
    constraint_name = staging_constraint_name(schema_id)
    entry = {
        "id": schema_id,
        "schema_contract_version": STAGING_SCHEMA_CONTRACT_VERSION,
        "target_profile": target_profile_name,
        "handoff_name": candidate["handoff_name"],
        "staging_table": candidate["staging_table"],
        "run_id_column": candidate["run_id_column"],
        "dedup_key": list(candidate["dedup_key"]),
        "constraint_name": constraint_name,
    }
    sql = staging_unique_constraint_sql(entry)
    payload = {**entry, "sql_statements": [_normalize_sql(sql)]}
    entry["content_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return entry


def staging_unique_constraint_sql(entry: dict[str, Any]) -> str:
    """Return the single additive uniqueness statement for an entry."""

    columns = [entry["run_id_column"], *entry["dedup_key"]]
    return "\n".join(
        [
            f"ALTER TABLE {entry['staging_table']}",
            f"ADD CONSTRAINT {entry['constraint_name']}",
            f"UNIQUE ({', '.join(columns)});",
        ]
    )


def staging_constraint_name(schema_id: str) -> str:
    _staging_schema_ordinal(schema_id)
    return "uq_" + schema_id.replace("-", "_")


def staging_unique_constraints_in_sql(
    sql: str,
    *,
    target_profile_name: str | None = None,
) -> list[dict[str, Any]]:
    """Classify executable UNIQUE additions while ignoring comments and literals."""

    executable = _mask_non_executable_sql(sql)
    identifier_folding = _identifier_folding(target_profile_name)
    constraints: list[dict[str, Any]] = []
    for match in _UNIQUE_CONSTRAINT_PATTERN.finditer(executable):
        _append_unique_constraint(
            constraints,
            table=match.group(1),
            name=match.group(2),
            columns_text=match.group(3),
            identifier_folding=identifier_folding,
        )
    for match in _UNIQUE_INDEX_PATTERN.finditer(executable):
        _append_unique_constraint(
            constraints,
            table=match.group(2),
            name=match.group(1),
            columns_text=match.group(3),
            identifier_folding=identifier_folding,
        )
    for table_match in _CREATE_TABLE_PATTERN.finditer(executable):
        for unique_match in _TABLE_UNIQUE_PATTERN.finditer(table_match.group(2)):
            _append_unique_constraint(
                constraints,
                table=table_match.group(1),
                name=unique_match.group(1) or "",
                columns_text=unique_match.group(2),
                identifier_folding=identifier_folding,
            )
    return constraints


def unclassifiable_staging_unique_statements(
    sql: str,
    *,
    entry: dict[str, Any],
) -> list[str]:
    """Return executable UNIQUE statements that target an entry but evade classification."""

    target_profile_name = entry["target_profile"]
    identifier_folding = _identifier_folding(target_profile_name)
    expected_table = _normalize_sql_identifier(
        entry["staging_table"],
        identifier_folding=identifier_folding,
    )
    unclassifiable: list[str] = []
    for statement in _normalized_executable_sql_statements(sql):
        unique_count = len(re.findall(r"\bUNIQUE\b", statement, re.IGNORECASE))
        if unique_count == 0 or not _statement_targets_table(
            statement,
            expected_table=expected_table,
            identifier_folding=identifier_folding,
        ):
            continue
        classified = staging_unique_constraints_in_sql(
            statement,
            target_profile_name=target_profile_name,
        )
        classified_on_table = sum(
            constraint["table"] == expected_table for constraint in classified
        )
        if classified_on_table < unique_count:
            unclassifiable.append(statement)
    return unclassifiable


def internal_schema_migration_inventory_issues(
    *,
    package_path: Path,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Verify retained Engine-owned schemas against immutable Flyway SQL.

    Existing baseline ownership is trustworthy only while exactly one matching
    migration remains on disk. Missing, edited, or duplicate migrations fail
    closed before generation or apply can mutate the package.
    """

    migration_dir = package_path / "src/main/resources/db/migration"
    migration_paths = sorted(path for path in migration_dir.rglob("*.sql") if path.is_file())
    sql_by_path = {path: path.read_text(encoding="utf-8") for path in migration_paths}
    issues: list[dict[str, Any]] = []
    for entry in entries:
        schema_id = entry.get("id")
        if schema_id == BATCH_METADATA_SCHEMA_ID:
            profile = TARGET_PROFILES.get(entry.get("target_profile"))
            if profile is None or entry != batch_metadata_internal_schema(profile):
                issues.append(_inventory_issue(schema_id, "divergent", []))
                continue
            expected_suffix = "__create_pkg_batch_metadata.sql"
            expected_statements = normalized_batch_metadata_sql_statements(profile)
            owned_objects = {
                object_name
                for sql in sql_by_path.values()
                for object_name in reserved_batch_metadata_objects_in_sql(sql)
            }
            if not owned_objects:
                issues.append(_inventory_issue(schema_id, "missing", []))
                continue
            object_paths = [
                path
                for path, sql in sql_by_path.items()
                if reserved_batch_metadata_objects_in_sql(sql)
            ]
            suffix_paths = [path for path in migration_paths if path.name.endswith(expected_suffix)]
            if len(suffix_paths) != 1 or len(object_paths) != 1 or suffix_paths != object_paths:
                issues.append(
                    _inventory_issue(schema_id, "duplicate", sorted(set(suffix_paths + object_paths)))
                )
                continue
            if (
                _normalized_executable_sql_statements(sql_by_path[suffix_paths[0]])
                != expected_statements
            ):
                issues.append(_inventory_issue(schema_id, "divergent", suffix_paths))
            continue

        if not isinstance(schema_id, str) or not schema_id.startswith("m5a-staging-"):
            continue
        expected_suffix = f"__add_{schema_id.replace('-', '_')}_unique.sql"
        suffix_paths = [path for path in migration_paths if path.name.endswith(expected_suffix)]
        equivalent_occurrences: list[Path] = []
        named_occurrences: list[Path] = []
        unclassifiable_paths: list[Path] = []
        for path, sql in sql_by_path.items():
            for constraint in staging_unique_constraints_in_sql(
                sql,
                target_profile_name=entry["target_profile"],
            ):
                if staging_constraint_name_matches_entry(constraint, entry):
                    named_occurrences.append(path)
                if staging_unique_columns_match_entry(constraint, entry):
                    equivalent_occurrences.append(path)
            if unclassifiable_staging_unique_statements(sql, entry=entry):
                unclassifiable_paths.append(path)
        if not suffix_paths:
            issues.append(_inventory_issue(schema_id, "missing", []))
            continue
        if len(suffix_paths) != 1:
            issues.append(_inventory_issue(schema_id, "duplicate", suffix_paths))
            continue
        expected_sql = _normalized_executable_sql_statements(staging_unique_constraint_sql(entry))
        if _normalized_executable_sql_statements(sql_by_path[suffix_paths[0]]) != expected_sql:
            issue = "unclassifiable" if suffix_paths[0] in unclassifiable_paths else "divergent"
            issues.append(_inventory_issue(schema_id, issue, suffix_paths))
            continue
        external_unclassifiable = [
            path for path in unclassifiable_paths if path not in suffix_paths
        ]
        if external_unclassifiable:
            issues.append(_inventory_issue(schema_id, "unclassifiable", external_unclassifiable))
            continue
        relevant_paths = sorted(set(suffix_paths + named_occurrences + equivalent_occurrences))
        if (
            len(named_occurrences) != 1
            or len(equivalent_occurrences) != 1
            or relevant_paths != suffix_paths
        ):
            issues.append(_inventory_issue(schema_id, "duplicate", relevant_paths))
    return issues


def _append_unique_constraint(
    constraints: list[dict[str, Any]],
    *,
    table: str,
    name: str | None,
    columns_text: str,
    identifier_folding: str,
) -> None:
    columns: list[str] = []
    for raw_column in columns_text.split(","):
        column_match = re.fullmatch(
            rf"\s*({_SQL_IDENTIFIER_PART})(?:\s+(?:ASC|DESC))?\s*",
            raw_column,
            re.IGNORECASE,
        )
        if column_match is None:
            return
        columns.append(
            _normalize_sql_identifier(
                column_match.group(1),
                identifier_folding=identifier_folding,
            )
        )
    if columns:
        constraints.append(
            {
                "table": _normalize_sql_identifier(
                    table,
                    identifier_folding=identifier_folding,
                ),
                "name": (
                    _normalize_sql_identifier(name, identifier_folding=identifier_folding)
                    if name
                    else ""
                ),
                "columns": columns,
            }
        )


def _normalize_sql_identifier(identifier: str, *, identifier_folding: str) -> str:
    """Normalize unquoted names and the default public schema for comparison."""

    parts = re.findall(_SQL_IDENTIFIER_PART, identifier.strip())
    normalized = [
        (
            part[1:-1].replace('""', '"')
            if part.startswith('"')
            else _fold_unquoted_identifier(part, identifier_folding)
        )
        for part in parts
    ]
    default_schema = _fold_unquoted_identifier("public", identifier_folding)
    if len(normalized) == 2 and normalized[0] == default_schema:
        return normalized[1]
    return ".".join(normalized)


def _statement_targets_table(
    statement: str,
    *,
    expected_table: str,
    identifier_folding: str,
) -> bool:
    for pattern in (
        _ALTER_TABLE_REFERENCE_PATTERN,
        _CREATE_TABLE_REFERENCE_PATTERN,
        _CREATE_UNIQUE_INDEX_TABLE_PATTERN,
    ):
        match = pattern.search(statement)
        if match is not None and _normalize_sql_identifier(
            match.group(1),
            identifier_folding=identifier_folding,
        ) == expected_table:
            return True
    return False


def _identifier_folding(target_profile_name: str | None) -> str:
    if target_profile_name is None:
        return "lower"
    target_profile = TARGET_PROFILES[target_profile_name]
    return "upper" if target_profile.runtime_database_dependency == "h2" else "lower"


def _fold_unquoted_identifier(identifier: str, identifier_folding: str) -> str:
    return identifier.upper() if identifier_folding == "upper" else identifier.lower()


def staging_constraint_name_matches_entry(
    constraint: dict[str, Any],
    entry: dict[str, Any],
) -> bool:
    identifier_folding = _identifier_folding(entry["target_profile"])
    expected_name = _normalize_sql_identifier(
        entry["constraint_name"],
        identifier_folding=identifier_folding,
    )
    return bool(constraint["name"]) and constraint["name"] == expected_name


def staging_unique_columns_match_entry(
    constraint: dict[str, Any],
    entry: dict[str, Any],
) -> bool:
    identifier_folding = _identifier_folding(entry["target_profile"])
    expected_table = _normalize_sql_identifier(
        entry["staging_table"],
        identifier_folding=identifier_folding,
    )
    expected_columns = [entry["run_id_column"], *entry["dedup_key"]]
    return constraint["table"] == expected_table and _same_unique_columns(
        constraint["columns"],
        expected_columns,
        identifier_folding=identifier_folding,
    )


def _same_unique_columns(
    actual: list[str],
    expected: list[str],
    *,
    identifier_folding: str,
) -> bool:
    normalized_expected = [
        _normalize_sql_identifier(column, identifier_folding=identifier_folding)
        for column in expected
    ]
    return len(actual) == len(normalized_expected) and set(actual) == set(normalized_expected)


def _inventory_issue(schema_id: Any, issue: str, paths: list[Path]) -> dict[str, Any]:
    article = "an" if issue == "unclassifiable" else "a"
    return {
        "schema_id": schema_id,
        "issue": issue,
        "paths": [path.name for path in paths],
        "message": (
            f"Retained internal schema '{schema_id}' has {article} {issue} "
            "Flyway migration inventory"
            + (f": {', '.join(path.name for path in paths)}" if paths else "")
            + ". Restore the immutable Engine-owned migration before continuing."
        ),
    }


def _candidate(contract: ContractMetadata) -> dict[str, Any]:
    run_semantics = contract.run_semantics
    if run_semantics is None:
        raise ValueError("M5a staging candidate requires validated run_semantics metadata.")
    table_name = contract.physical_name or contract.name.replace("-", "_")
    allocation = {
        "handoff_name": contract.name,
        "staging_table": table_name,
        "run_id_column": run_semantics.physical_run_id_column,
        "dedup_key": list(run_semantics.dedup_key),
    }
    allocation_bytes = json.dumps(
        allocation, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        **allocation,
        "allocation_tuple": (
            contract.name,
            table_name,
            run_semantics.physical_run_id_column,
            tuple(run_semantics.dedup_key),
        ),
        "allocation_bytes": allocation_bytes,
        "internal_schema_id": run_semantics.internal_schema_id,
    }


def _validated_staging_entry(entry: dict[str, Any]) -> dict[str, Any]:
    schema_id = entry.get("id")
    _staging_schema_ordinal(schema_id)
    if entry.get("schema_contract_version") != STAGING_SCHEMA_CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported retained internal schema version for '{schema_id}': "
            f"{entry.get('schema_contract_version')!r}."
        )
    required_strings = [
        "target_profile",
        "handoff_name",
        "staging_table",
        "run_id_column",
        "constraint_name",
    ]
    if any(not isinstance(entry.get(key), str) or not entry[key] for key in required_strings):
        raise ValueError(f"Internal schema '{schema_id}' has malformed staging identity fields.")
    if entry["target_profile"] not in TARGET_PROFILES:
        raise ValueError(
            f"Internal schema '{schema_id}' references unknown target profile "
            f"'{entry['target_profile']}'."
        )
    dedup_key = entry.get("dedup_key")
    if not isinstance(dedup_key, list) or not dedup_key or not all(
        isinstance(column, str) and column for column in dedup_key
    ):
        raise ValueError(f"Internal schema '{schema_id}' has an invalid dedup_key.")
    if entry["constraint_name"] != staging_constraint_name(schema_id):
        raise ValueError(f"Internal schema '{schema_id}' has an invalid constraint_name.")
    candidate = {
        "handoff_name": entry["handoff_name"],
        "staging_table": entry["staging_table"],
        "run_id_column": entry["run_id_column"],
        "dedup_key": list(dedup_key),
    }
    expected = _staging_internal_schema_entry(
        candidate=candidate,
        schema_id=schema_id,
        target_profile_name=entry["target_profile"],
    )
    if entry.get("content_sha256") != expected["content_sha256"]:
        raise ValueError(
            f"Engine integrity failure: retained internal schema '{schema_id}' fingerprint drifted."
        )
    return dict(entry)


def _staging_schema_ordinal(schema_id: Any) -> int:
    if not isinstance(schema_id, str):
        raise ValueError(f"Malformed M5a staging internal schema id: {schema_id!r}.")
    match = STAGING_SCHEMA_ID_PATTERN.fullmatch(schema_id)
    ordinal = int(match.group(1)) if match is not None else 0
    if match is None or ordinal < 1 or match.group(1) != f"{ordinal:03d}":
        raise ValueError(f"Malformed M5a staging internal schema id: '{schema_id}'.")
    return ordinal


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _normalized_executable_sql_statements(sql: str) -> list[str]:
    executable = _mask_non_executable_sql(sql)
    return [_normalize_sql(statement) for statement in executable.split(";") if statement.strip()]


def _mask_non_executable_sql(sql: str) -> str:
    masked = list(sql)
    index = 0
    while index < len(sql):
        if sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            end = len(sql) if end < 0 else end
            for position in range(index, end):
                masked[position] = " "
            index = end
            continue
        if sql.startswith("/*", index):
            end = index + 2
            depth = 1
            while end < len(sql) and depth:
                if sql.startswith("/*", end):
                    depth += 1
                    end += 2
                elif sql.startswith("*/", end):
                    depth -= 1
                    end += 2
                else:
                    end += 1
            for position in range(index, end):
                if masked[position] not in "\r\n":
                    masked[position] = " "
            index = end
            continue
        if sql[index] == "$":
            delimiter_match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[index:])
            if delimiter_match is not None:
                delimiter = delimiter_match.group(0)
                end = sql.find(delimiter, index + len(delimiter))
                end = len(sql) if end < 0 else end + len(delimiter)
                for position in range(index, end):
                    if masked[position] not in "\r\n":
                        masked[position] = " "
                index = end
                continue
        if sql[index] == "'":
            escape_string = (
                index > 0
                and sql[index - 1] in "Ee"
                and (
                    index == 1
                    or not (sql[index - 2].isalnum() or sql[index - 2] in "_$")
                )
            )
            end = index + 1
            while end < len(sql):
                if escape_string and sql[end] == "\\":
                    end = min(end + 2, len(sql))
                    continue
                if sql[end] == "'" and end + 1 < len(sql) and sql[end + 1] == "'":
                    end += 2
                    continue
                if sql[end] == "'":
                    end += 1
                    break
                end += 1
            start = index - 1 if escape_string else index
            for position in range(start, end):
                if masked[position] not in "\r\n":
                    masked[position] = " "
            index = end
            continue
        index += 1
    return "".join(masked)
