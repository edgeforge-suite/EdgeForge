"""Static compatibility checks for generated applications."""

from __future__ import annotations

import re
from pathlib import Path

from appbuilder.generation.utils import (
    base_package,
    canonical_field_name,
    contract_field_name,
    filter_mappings,
    operation_mapping_transport_context,
    output_field_name,
    package_path,
    parse_sql_table_columns,
    staging_operational_column_role,
    to_pascal_case,
    to_snake_case,
)
from appbuilder.mapping import MappingDirection
from appbuilder.metadata.models import CanonicalOperation, MetadataProject
from appbuilder.target_profiles.catalog import TARGET_PROFILES

from .models import HarnessCheck, HarnessCheckSeverity


def check_upstream_dto_request_fields(
    metadata: MetadataProject, output_dir: Path
) -> HarnessCheck:
    return _check_upstream_dto_group(
        metadata=metadata,
        output_dir=output_dir,
        role="request",
        check_name="upstream_dto_fields_match_contract",
    )


def check_upstream_dto_response_fields(
    metadata: MetadataProject, output_dir: Path
) -> HarnessCheck:
    return _check_upstream_dto_group(
        metadata=metadata,
        output_dir=output_dir,
        role="response",
        check_name="upstream_response_dto_fields_match_contract",
    )


def check_flyway_columns_match_entity(
    metadata: MetadataProject, output_dir: Path
) -> HarnessCheck:
    target_profile = TARGET_PROFILES[metadata.target_profile]
    if not target_profile.emit_flyway:
        return HarnessCheck(
            name="flyway_columns_match_canonical_entity",
            severity=HarnessCheckSeverity.INFO,
            passed=True,
            message="Flyway generation is disabled for the selected target profile.",
        )

    migration_dir = output_dir / "src" / "main" / "resources" / "db" / "migration"
    issues: list[str] = []
    for entity in metadata.entities:
        # Use glob to find V{n}__create_{entity}_table.sql regardless of version number
        pattern = f"V*__create_{to_snake_case(entity.name)}_table.sql"
        matches = sorted(migration_dir.glob(pattern)) if migration_dir.exists() else []
        if not matches:
            issues.append(f"{entity.name}: missing migration file matching {pattern}")
            continue

        alter_pattern = f"V*__alter_{to_snake_case(entity.name)}_*.sql"
        alter_matches = sorted(migration_dir.glob(alter_pattern)) if migration_dir.exists() else []
        content = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [*matches, *alter_matches]
        )
        missing_columns = [
            to_snake_case(field.name)
            for field in entity.fields
            if re.search(rf"\b{re.escape(to_snake_case(field.name))}\b", content) is None
        ]
        if missing_columns:
            issues.append(
                f"{entity.name}: missing columns: {', '.join(missing_columns)}"
            )

    if issues:
        return HarnessCheck(
            name="flyway_columns_match_canonical_entity",
            severity=HarnessCheckSeverity.ERROR,
            passed=False,
            message="Flyway migration gaps detected: " + "; ".join(issues),
        )
    return HarnessCheck(
        name="flyway_columns_match_canonical_entity",
        severity=HarnessCheckSeverity.ERROR,
        passed=True,
        message="Flyway migrations include every canonical column for all entities.",
    )


def check_staging_table_required_columns_mapped(
    metadata: MetadataProject, output_dir: Path
) -> HarnessCheck:
    del output_dir

    staging_contracts = [contract for contract in metadata.contracts if contract.type == "staging-table"]
    if not staging_contracts:
        return HarnessCheck(
            name="staging_table_non_nullable_columns_all_mapped",
            severity=HarnessCheckSeverity.INFO,
            passed=True,
            message="No staging-table contracts are defined for this metadata project.",
        )

    required_missing: list[str] = []
    optional_missing: list[str] = []
    for contract in staging_contracts:
        entities = _entities_for_contract(
            metadata,
            contract_name=contract.name,
            direction=MappingDirection.CANONICAL_TO_HANDOFF,
        )
        if not entities:
            optional_missing.append(f"{contract.name}: unable to resolve entity scope")
            continue
        mappings = filter_mappings(
            metadata,
            direction=MappingDirection.CANONICAL_TO_HANDOFF,
            contract_name=contract.name,
        )
        for entity in entities:
            mapped_fields = {
                mapping.source_path.split(".", 1)[1]
                for mapping in mappings
                if mapping.source_path.startswith(f"{entity.name}.")
            }
            in_scope_fields = {
                field.name
                for field in entity.fields
                if any(path.startswith(f"{contract.name}.") for path in field.source_paths)
            } | mapped_fields

            for field in entity.fields:
                if field.name not in in_scope_fields or field.name in mapped_fields:
                    continue
                label = f"{contract.name}.{entity.name}.{field.name}"
                if field.required:
                    required_missing.append(label)
                else:
                    optional_missing.append(label)

    if required_missing:
        return HarnessCheck(
            name="staging_table_non_nullable_columns_all_mapped",
            severity=HarnessCheckSeverity.ERROR,
            passed=False,
            message=(
                "Required staging mappings are missing for canonical fields: "
                + ", ".join(sorted(required_missing))
            ),
        )
    if optional_missing:
        return HarnessCheck(
            name="staging_table_non_nullable_columns_all_mapped",
            severity=HarnessCheckSeverity.WARNING,
            passed=False,
            message=(
                "Optional staging mappings are missing for canonical fields: "
                + ", ".join(sorted(optional_missing))
            ),
        )
    return HarnessCheck(
            name="staging_table_non_nullable_columns_all_mapped",
            severity=HarnessCheckSeverity.ERROR,
            passed=True,
            message="All staging-table-relevant canonical fields are mapped for every entity.",
        )


def check_staging_table_run_identity_contract(
    metadata: MetadataProject, output_dir: Path
) -> list[HarnessCheck]:
    """Return one independently graded run-identity result per staging handoff."""
    del output_dir

    staging_contracts = sorted(
        (
            contract
            for contract in metadata.contracts
            if contract.type == "staging-table"
        ),
        key=lambda contract: contract.name,
    )
    if not staging_contracts:
        return [
            HarnessCheck(
                name="staging_table_run_identity_contract",
                severity=HarnessCheckSeverity.INFO,
                passed=True,
                message="No staging-table contracts are defined for this metadata project.",
            )
        ]

    checks: list[HarnessCheck] = []
    for contract in staging_contracts:
        issues: list[str] = []
        opted_in = contract.run_semantics is not None
        table_name = contract.physical_name or contract.name.replace("-", "_")
        ddl_content = metadata.staging_table_ddls.get(table_name)
        if not ddl_content:
            issues.append("unable to inspect staging DDL")
        else:
            database = TARGET_PROFILES[
                metadata.target_profile
            ].runtime_database_dependency
            columns = parse_sql_table_columns(ddl_content, database=database)
            if not any(bool(column["primary_key"]) for column in columns.values()):
                issues.append("staging table lacks primary key")
            if opted_in:
                declared_run_id = contract.run_semantics.physical_run_id_column
                if (
                    declared_run_id not in columns
                    or staging_operational_column_role(declared_run_id) != "run_id"
                ):
                    issues.append(
                        "staging table lacks run identity: declared column "
                        f"'{declared_run_id}' is absent or not recognized"
                    )
            elif not any(
                staging_operational_column_role(column_name) == "run_id"
                for column_name in columns
            ):
                issues.append("staging table lacks run identity")

        severity = (
            HarnessCheckSeverity.ERROR
            if opted_in
            else HarnessCheckSeverity.WARNING
        )
        check_name = f"staging_table_run_identity_contract:{contract.name}"
        if issues:
            posture = (
                "required for declared run_semantics"
                if opted_in
                else "rerun/restart semantics may not be production-ready"
            )
            checks.append(
                HarnessCheck(
                    name=check_name,
                    severity=severity,
                    passed=False,
                    message=f"{contract.name}: {', '.join(issues)}; {posture}",
                )
            )
            continue

        checks.append(
            HarnessCheck(
                name=check_name,
                severity=severity,
                passed=True,
                message=(
                    f"{contract.name}: staging table declares primary key and "
                    "run identity support."
                ),
            )
        )
    return checks


def check_downstream_file_field_order(
    metadata: MetadataProject, output_dir: Path
) -> HarnessCheck:
    downstream_file_contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
    }
    file_contracts = [
        contract
        for contract in metadata.contracts
        if contract.type == "file-fixed-width"
        and contract.name in downstream_file_contract_names
    ]
    if not file_contracts:
        return HarnessCheck(
            name="downstream_file_fields_in_correct_order",
            severity=HarnessCheckSeverity.INFO,
            passed=True,
            message="No fixed-width downstream contracts are defined for this metadata project.",
        )

    issues: list[str] = []
    for contract in file_contracts:
        entities = _entities_for_contract(
            metadata,
            contract_name=contract.name,
            direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
        )
        if not entities:
            issues.append(f"{contract.name}: unable to resolve entity scope")
            continue
        for entity in entities:
            writer_class_names = _downstream_file_writer_class_names_by_contract(
                metadata, entity.name
            )
            writer_class_name = writer_class_names.get(
                contract.name,
                f"{entity.name}EodHandoffFileWriter",
            )
            writer_path = _outbound_writer_path(
                output_dir, metadata, writer_class_name
            )
            if not writer_path.exists():
                issues.append(f"{contract.name} ({entity.name}): missing writer {writer_path.name}")
                continue

            entity_mappings = [
                mapping
                for mapping in filter_mappings(
                    metadata,
                    direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                    contract_name=contract.name,
                )
                if mapping.source_path.startswith(f"{entity.name}.")
            ]
            expected_order = [output_field_name(mapping) for mapping in entity_mappings]
            source_field_to_outputs: dict[str, list[str]] = {}
            for mapping in entity_mappings:
                if "." not in mapping.source_path:
                    continue
                source_field = mapping.source_path.split(".", 1)[1]
                source_field_to_outputs.setdefault(source_field, []).append(
                    output_field_name(mapping)
                )
            getter_to_outputs = {
                to_pascal_case(source_field): list(output_fields)
                for source_field, output_fields in source_field_to_outputs.items()
            }
            content = writer_path.read_text(encoding="utf-8")
            actual_order = _downstream_writer_output_order(
                content,
                getter_to_outputs=getter_to_outputs,
            )
            if actual_order != expected_order:
                issues.append(
                    f"{contract.name} ({entity.name}): expected {expected_order}, got {actual_order}"
                )

    if issues:
        return HarnessCheck(
            name="downstream_file_fields_in_correct_order",
            severity=HarnessCheckSeverity.WARNING,
            passed=False,
            message="Downstream file field order issues detected: " + "; ".join(issues),
        )
    return HarnessCheck(
        name="downstream_file_fields_in_correct_order",
        severity=HarnessCheckSeverity.WARNING,
        passed=True,
        message="Downstream file writers preserve declared field order for all contracts.",
    )


def _downstream_file_writer_class_names_by_contract(
    metadata: MetadataProject,
    entity_name: str,
) -> dict[str, str]:
    active_contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.source_path.startswith(f"{entity_name}.")
    }
    active_contracts = [
        contract
        for contract in metadata.contracts
        if contract.name in active_contract_names
        and contract.type in {"file-fixed-width", "file-csv"}
    ]
    if len(active_contracts) == 1:
        return {active_contracts[0].name: f"{entity_name}EodHandoffFileWriter"}

    used_names: set[str] = set()
    names: dict[str, str] = {}
    for contract in active_contracts:
        base_name = f"{entity_name}{to_pascal_case(contract.name)}FileWriter"
        candidate = base_name
        suffix = 2
        while candidate in used_names:
            candidate = f"{base_name}{suffix}"
            suffix += 1
        used_names.add(candidate)
        names[contract.name] = candidate
    return names


def _downstream_writer_output_order(
    content: str,
    *,
    getter_to_outputs: dict[str, list[str]],
) -> list[str]:
    """Return downstream writer output fields in generated Java emission order."""

    ordered_fields: list[tuple[int, str]] = []

    for match in re.finditer(r'values\.put\("([^"]+)",', content):
        ordered_fields.append((match.start(), match.group(1)))

    getter_to_output_offsets = {getter: 0 for getter in getter_to_outputs}
    append_pattern = re.compile(
        r"line\.append\(\s*"
        r"(?:(?:padRight|leftZeroPad)\(\s*)?"
        r"(?:(?:stringValue|minorUnitString)\(\s*)?"
        r"[A-Za-z_][A-Za-z0-9_]*\.get([A-Za-z0-9_]+)\(\)"
        r"|line\.append\(\s*fixedWidthMinorUnitString\(\s*"
        r"[A-Za-z_][A-Za-z0-9_]*\.get([A-Za-z0-9_]+)\(\)"
    )
    for match in append_pattern.finditer(content):
        getter_suffix = match.group(1) or match.group(2)
        ordered_fields.append(
            (
                match.start(),
                _next_output_for_getter(
                    getter_suffix,
                    getter_to_outputs=getter_to_outputs,
                    getter_to_output_offsets=getter_to_output_offsets,
                ),
            )
        )

    enhanced_field_pattern = re.compile(
        r'formatFixedWidthField\(\s*"([^"]+)",\s*'
        r"(?:(?:minorUnitString)\(\s*)?"
        r"[A-Za-z_][A-Za-z0-9_]*\.get[A-Za-z0-9_]+\(\)"
    )
    for match in enhanced_field_pattern.finditer(content):
        ordered_fields.append((match.start(), match.group(1)))

    return [field for _, field in sorted(ordered_fields, key=lambda item: item[0])]


def _next_output_for_getter(
    getter_suffix: str,
    *,
    getter_to_outputs: dict[str, list[str]],
    getter_to_output_offsets: dict[str, int],
) -> str:
    output_fields = getter_to_outputs.get(getter_suffix)
    if not output_fields:
        return f"get{getter_suffix}()"
    offset = getter_to_output_offsets.get(getter_suffix, 0)
    getter_to_output_offsets[getter_suffix] = offset + 1
    if offset >= len(output_fields):
        return f"get{getter_suffix}()"
    return output_fields[offset]


def check_no_appbuilder_runtime_imports(
    metadata: MetadataProject, output_dir: Path
) -> HarnessCheck:
    del metadata

    main_java_dir = output_dir / "src" / "main" / "java"
    offenders: list[str] = []
    for java_file in main_java_dir.rglob("*.java"):
        content = java_file.read_text(encoding="utf-8")
        if "import appbuilder." in content or "import com.appbuilder.generation." in content:
            offenders.append(java_file.relative_to(output_dir).as_posix())

    if offenders:
        return HarnessCheck(
            name="generated_app_has_no_appbuilder_imports",
            severity=HarnessCheckSeverity.ERROR,
            passed=False,
            message=(
                "Generated app contains EdgeForge runtime imports in: "
                + ", ".join(offenders)
            ),
        )
    return HarnessCheck(
        name="generated_app_has_no_appbuilder_imports",
        severity=HarnessCheckSeverity.ERROR,
        passed=True,
        message="Generated application is standalone and has no EdgeForge runtime imports.",
    )


def _check_upstream_dto_group(
    *,
    metadata: MetadataProject,
    output_dir: Path,
    role: str,
    check_name: str,
) -> HarnessCheck:
    issues: list[str] = []
    validated_operations = 0
    for operation in _upstream_operations(metadata):
        mappings = _upstream_role_mappings(metadata, operation, role=role)
        if not mappings:
            continue
        validated_operations += 1
        dto_path = _inbound_dto_path(
            output_dir, metadata, f"{to_pascal_case(operation.name)}{to_pascal_case(role)}"
        )
        if not dto_path.exists():
            issues.append(f"{operation.name}: missing DTO file {dto_path.name}")
            continue

        content = dto_path.read_text(encoding="utf-8")
        missing_fields: list[str] = []
        for mapping in mappings:
            canonical_name = canonical_field_name(mapping)
            contract_name = contract_field_name(mapping)
            if not _java_field_declared(content, canonical_name):
                missing_fields.append(contract_name)
                continue
            if contract_name != canonical_name and not _json_property_present(
                content, contract_name, canonical_name
            ):
                missing_fields.append(contract_name)
        if missing_fields:
            issues.append(f"{operation.name}: missing fields {', '.join(missing_fields)}")

    if issues:
        return HarnessCheck(
            name=check_name,
            severity=HarnessCheckSeverity.ERROR,
            passed=False,
            message="Missing upstream DTO coverage: " + "; ".join(issues),
        )
    if validated_operations == 0:
        return HarnessCheck(
            name=check_name,
            severity=HarnessCheckSeverity.INFO,
            passed=True,
            message=f"No upstream {role} mappings were available for verification.",
        )
    return HarnessCheck(
        name=check_name,
        severity=HarnessCheckSeverity.ERROR,
        passed=True,
        message=f"All upstream {role} DTOs preserve the contract fields.",
    )


def _upstream_operations(metadata: MetadataProject) -> list[CanonicalOperation]:
    """Return all operations sourced from an upstream API interface."""

    operations: list[CanonicalOperation] = []
    for operation in metadata.operations:
        if any(
            mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
            and mapping.contract_name == operation.interface_name
            and mapping.operation_name == operation.name
            for mapping in metadata.mappings
        ):
            operations.append(operation)
    return operations


def _upstream_role_mappings(
    metadata: MetadataProject, operation: CanonicalOperation, *, role: str
) -> list:
    return [
        mapping
        for mapping in filter_mappings(
            metadata,
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=operation.interface_name,
            operation_name=operation.name,
        )
        # Unknown contexts still require checking rather than disappearing.
        if (operation_mapping_transport_context(
            mapping.source_path, operation.interface_name, operation.name,
        ) or "request") == role
    ]


def _entities_for_contract(
    metadata: MetadataProject,
    *,
    contract_name: str,
    direction: MappingDirection,
) -> list:
    entity_names = {
        mapping.source_path.split(".", 1)[0]
        for mapping in filter_mappings(
            metadata,
            direction=direction,
            contract_name=contract_name,
        )
        if "." in mapping.source_path
    }
    if not entity_names:
        entity_names = {
            entity.name
            for entity in metadata.entities
            if any(
                path.startswith(f"{contract_name}.")
                for field in entity.fields
                for path in field.source_paths
            )
        }
    return [entity for entity in metadata.entities if entity.name in entity_names]


def _inbound_dto_path(output_dir: Path, metadata: MetadataProject, class_name: str) -> Path:
    return (
        output_dir
        / "src"
        / "main"
        / "java"
        / package_path(base_package(metadata))
        / "adapter"
        / "inbound"
        / f"{class_name}.java"
    )


def _outbound_writer_path(output_dir: Path, metadata: MetadataProject, class_name: str) -> Path:
    return (
        output_dir
        / "src"
        / "main"
        / "java"
        / package_path(base_package(metadata))
        / "adapter"
        / "outbound"
        / f"{class_name}.java"
    )


def _java_field_declared(content: str, field_name: str) -> bool:
    return (
        re.search(
            rf"private\s+[A-Za-z0-9_<>\[\].]+\s+{re.escape(field_name)}\s*(?:=[^;]+)?;",
            content,
        )
        is not None
    )


def _json_property_present(content: str, contract_name: str, canonical_name: str) -> bool:
    has_annotation = re.search(
        rf'@JsonProperty\("{re.escape(contract_name)}"\)',
        content,
    ) is not None
    has_field = _java_field_declared(content, canonical_name)
    return has_annotation and has_field
