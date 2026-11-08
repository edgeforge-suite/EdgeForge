"""Helpers for loading explicit field mappings from input projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import (
    SUPPORTED_OUTPUT_TYPE_COERCIONS,
    FieldMapping,
    MappingCompletenessReport,
    MappingDirection,
    MappingIssue,
    MappingSeverity,
)


def build_upstream_mapping_artifacts(
    *,
    mapping_path: Path,
    interface_name: str,
    declared_operations: dict[str, dict[str, list[str]]],
) -> tuple[list[FieldMapping], MappingCompletenessReport, dict[tuple[str, str, str], str], str]:
    """Load explicit upstream mappings and validate them against sampled operations."""

    payload = _load_yaml(mapping_path)
    entity_name = str(payload.get("entity") or "Record")
    mappings: list[FieldMapping] = []
    issues: list[MappingIssue] = []
    lookup: dict[tuple[str, str, str], str] = {}

    operations = payload.get("operations", [])
    declared_operation_names = set(declared_operations)
    mapped_operation_names: set[str] = set()

    for operation in operations:
        operation_name = operation["name"]
        mapped_operation_names.add(operation_name)
        if operation_name not in declared_operations:
            issues.append(
                MappingIssue(
                    contract_name=interface_name,
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    severity=MappingSeverity.ERROR,
                    message=f"Mapping declares unknown operation '{operation_name}'.",
                    location=str(mapping_path),
                )
            )
            continue

        for sample_kind, field_key in (("request", "request_mappings"), ("response", "response_mappings")):
            sample_fields = set(declared_operations[operation_name].get(sample_kind, []))
            seen_fields: set[str] = set()
            for field_mapping in operation.get(field_key, []):
                source_field = field_mapping["source"]
                target_path = field_mapping["target"]
                seen_fields.add(source_field)
                lookup[(operation_name, sample_kind, source_field)] = target_path
                mappings.append(
                    FieldMapping(
                        contract_name=interface_name,
                        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                        operation_name=operation_name,
                        source_path=f"{interface_name}.{operation_name}.{sample_kind}.{source_field}",
                        target_path=target_path,
                        source_required=sample_kind == "request",
                        source_location=str(mapping_path),
                    )
                )
                if source_field not in sample_fields:
                    issues.append(
                        MappingIssue(
                            contract_name=interface_name,
                            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                            severity=MappingSeverity.ERROR,
                            message=(
                                f"Mapping source '{source_field}' is not present in the "
                                f"{sample_kind} sample for operation '{operation_name}'."
                            ),
                            location=str(mapping_path),
                        )
                    )

            for field_name in sorted(sample_fields - seen_fields):
                issues.append(
                    MappingIssue(
                        contract_name=interface_name,
                        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                        severity=MappingSeverity.WARNING,
                        message=(
                            f"Sample field '{field_name}' in operation '{operation_name}' "
                            f"{sample_kind} is not explicitly mapped."
                        ),
                        location=str(mapping_path),
                    )
                )

    for missing_operation in sorted(declared_operation_names - mapped_operation_names):
        issues.append(
            MappingIssue(
                contract_name=interface_name,
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                severity=MappingSeverity.ERROR,
                message=f"No explicit mapping declared for operation '{missing_operation}'.",
                location=str(mapping_path),
            )
        )

    return mappings, _build_report(interface_name, MappingDirection.UPSTREAM_TO_CANONICAL, issues), lookup, entity_name


def build_output_mapping_artifacts(
    *,
    mapping_path: Path,
    contract_name: str,
    direction: MappingDirection,
    available_targets: dict[str, bool],
) -> tuple[list[FieldMapping], MappingCompletenessReport, dict[str, str], str | None]:
    """Load canonical-to-output mappings and validate contract completeness."""

    payload = _load_yaml(mapping_path)
    entity_name = payload.get("entity")
    mappings: list[FieldMapping] = []
    issues: list[MappingIssue] = []
    lookup: dict[str, str] = {}

    mapped_targets: set[str] = set()
    for field_mapping in payload.get("field_mappings", []):
        source_path = field_mapping["source"]
        target_name = field_mapping["target"]
        type_coercion = field_mapping.get("type_coercion")
        mapped_targets.add(target_name)
        lookup[target_name] = source_path
        mappings.append(
            FieldMapping(
                contract_name=contract_name,
                direction=direction,
                source_path=source_path,
                target_path=f"{contract_name}.{target_name}",
                source_location=str(mapping_path),
                type_coercion=type_coercion,
            )
        )
        if type_coercion is not None and type_coercion not in SUPPORTED_OUTPUT_TYPE_COERCIONS:
            issues.append(
                MappingIssue(
                    contract_name=contract_name,
                    direction=direction,
                    severity=MappingSeverity.ERROR,
                    message=(
                        f"Mapping type_coercion '{type_coercion}' is unsupported; "
                        "supported values: major_to_minor_units."
                    ),
                    location=str(mapping_path),
                )
            )
        if target_name not in available_targets:
            issues.append(
                MappingIssue(
                    contract_name=contract_name,
                    direction=direction,
                    severity=MappingSeverity.ERROR,
                    message=f"Mapping targets unknown contract field '{target_name}'.",
                    location=str(mapping_path),
                )
            )

    for target_name, required in available_targets.items():
        if target_name in mapped_targets:
            continue
        severity = MappingSeverity.ERROR if required else MappingSeverity.WARNING
        qualifier = "required" if required else "optional"
        issues.append(
            MappingIssue(
                contract_name=contract_name,
                direction=direction,
                severity=severity,
                message=f"Contract target '{target_name}' is {qualifier} but not mapped.",
                location=str(mapping_path),
            )
        )

    return mappings, _build_report(contract_name, direction, issues), lookup, str(entity_name) if entity_name else None


def _build_report(
    contract_name: str,
    direction: MappingDirection,
    issues: list[MappingIssue],
) -> MappingCompletenessReport:
    if any(issue.severity == MappingSeverity.ERROR for issue in issues):
        status = "error"
    elif issues:
        status = "warning"
    else:
        status = "complete"
    return MappingCompletenessReport(
        contract_name=contract_name,
        direction=direction,
        status=status,
        issues=issues,
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping in '{path}'")
    return payload
