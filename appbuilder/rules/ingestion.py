"""Helpers for loading canonical rules from manifest-driven input projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import CanonicalRule, RuleType

_FIELD_COMPARISON_OPERATORS = {"<=", "<", ">=", ">", "=="}
_CROSS_ENTITY_FIELD_OPERATORS = {"eq", "neq", "lt", "lte", "gt", "gte"}


def load_rule_definitions(rule_path: Path) -> tuple[str | None, list[CanonicalRule]]:
    """Load one rule file into normalized canonical rules."""

    payload = _load_yaml(rule_path)
    entity_name = payload.get("entity")
    rules: list[CanonicalRule] = []

    for rule in payload.get("rules", []):
        rule_type = str(rule["type"])
        if rule_type == "allowed-values":
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.ALLOWED_VALUES,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.allowed-values",
                    values=list(rule.get("values", [])),
                )
            )
        elif rule_type == "default":
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.DEFAULT,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.default",
                    value=str(rule.get("value")),
                )
            )
        elif rule_type == "iso-4217":
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.FORMAT,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.iso-4217",
                    format="iso-4217",
                )
            )
        elif rule_type == "max-length":
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.MAX_LENGTH,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.max-length",
                    max_length=_parse_int(rule.get("value"), rule_type, rule_path, rule["field"]),
                )
            )
        elif rule_type == "min-length":
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.MIN_LENGTH,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.min-length",
                    min_length=_parse_int(rule.get("value"), rule_type, rule_path, rule["field"]),
                )
            )
        elif rule_type == "pattern":
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.PATTERN,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.pattern",
                    pattern=_parse_string(rule.get("value"), rule_type, rule_path, rule["field"]),
                )
            )
        elif rule_type == "range":
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.RANGE,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.range",
                    range_min=_parse_float(rule.get("min"), rule_type, rule_path, rule["field"]),
                    range_max=_parse_float(rule.get("max"), rule_type, rule_path, rule["field"]),
                )
            )
        elif rule_type == "not-null":
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.NOT_NULL,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.not-null",
                )
            )
        elif rule_type == "cross-entity-exists":
            target_entity = rule.get("target-entity")
            if not target_entity:
                raise ValueError(
                    f"Rule type 'cross-entity-exists' for field '{rule['field']}' "
                    f"in '{rule_path}' requires a 'target-entity' value."
                )
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.CROSS_ENTITY_EXISTS,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.cross-entity-exists",
                    target_entity=str(target_entity),
                )
            )
        elif rule_type == "cross-entity-field-check":
            target_entity = _require_rule_value(
                rule.get("target-entity"),
                rule_type,
                rule_path,
                rule["field"],
                "target-entity",
            )
            target_field = _require_rule_value(
                rule.get("target-field"),
                rule_type,
                rule_path,
                rule["field"],
                "target-field",
            )
            operator = _require_cross_entity_operator(rule, rule_type, rule_path)
            expected_value = _require_rule_value(
                rule.get("expected-value"),
                rule_type,
                rule_path,
                rule["field"],
                "expected-value",
            )
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.CROSS_ENTITY_FIELD_CHECK,
                    source_path=(
                        f"rules.{entity_name or 'Unknown'}.{rule['field']}.cross-entity-field-check"
                    ),
                    target_entity=target_entity,
                    target_field=target_field,
                    operator=operator,
                    expected_value=expected_value,
                    error_message=_optional_string(rule.get("error-message")),
                )
            )
        elif rule_type == "cross-entity-field-compare":
            target_entity = _require_rule_value(
                rule.get("target-entity"),
                rule_type,
                rule_path,
                rule["field"],
                "target-entity",
            )
            target_field = _require_rule_value(
                rule.get("target-field"),
                rule_type,
                rule_path,
                rule["field"],
                "target-field",
            )
            source_field = _require_rule_value(
                rule.get("source-field"),
                rule_type,
                rule_path,
                rule["field"],
                "source-field",
            )
            operator = _require_cross_entity_operator(rule, rule_type, rule_path)
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.CROSS_ENTITY_FIELD_COMPARE,
                    source_path=(
                        f"rules.{entity_name or 'Unknown'}.{rule['field']}.cross-entity-field-compare"
                    ),
                    target_entity=target_entity,
                    target_field=target_field,
                    source_field=source_field,
                    operator=operator,
                    error_message=_optional_string(rule.get("error-message")),
                )
            )
        elif rule_type == "cross-entity-field-in":
            target_entity = _require_rule_value(
                rule.get("target-entity"),
                rule_type,
                rule_path,
                rule["field"],
                "target-entity",
            )
            target_field = _require_rule_value(
                rule.get("target-field"),
                rule_type,
                rule_path,
                rule["field"],
                "target-field",
            )
            allowed_values = rule.get("allowed-values")
            if not isinstance(allowed_values, list) or not allowed_values:
                raise ValueError(
                    f"Rule type '{rule_type}' for field '{rule['field']}' "
                    f"in '{rule_path}' requires a non-empty 'allowed-values' list."
                )
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.CROSS_ENTITY_FIELD_IN,
                    source_path=(
                        f"rules.{entity_name or 'Unknown'}.{rule['field']}.cross-entity-field-in"
                    ),
                    target_entity=target_entity,
                    target_field=target_field,
                    values=[str(value) for value in allowed_values],
                    error_message=_optional_string(rule.get("error-message")),
                )
            )
        elif rule_type == "field-comparison":
            operator = rule.get("operator")
            if not operator:
                raise ValueError(
                    f"Rule type 'field-comparison' for field '{rule['field']}' "
                    f"in '{rule_path}' requires an 'operator' value."
                )
            if str(operator) not in _FIELD_COMPARISON_OPERATORS:
                raise ValueError(
                    f"Rule type 'field-comparison' for field '{rule['field']}' "
                    f"in '{rule_path}' requires an operator in "
                    f"{sorted(_FIELD_COMPARISON_OPERATORS)}."
                )
            compare_to_field = rule.get("compare-to-field")
            if not compare_to_field:
                raise ValueError(
                    f"Rule type 'field-comparison' for field '{rule['field']}' "
                    f"in '{rule_path}' requires a 'compare-to-field' value."
                )
            rules.append(
                CanonicalRule(
                    entity_name=str(entity_name or "Unknown"),
                    field_name=rule["field"],
                    type=RuleType.FIELD_COMPARISON,
                    source_path=f"rules.{entity_name or 'Unknown'}.{rule['field']}.field-comparison",
                    operator=str(operator),
                    compare_to_field=str(compare_to_field),
                )
            )
        else:
            raise ValueError(f"Unsupported rule type '{rule_type}' in '{rule_path}'")

    return str(entity_name) if entity_name is not None else None, rules


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping in '{path}'")
    return payload


def _parse_int(
    value: Any,
    rule_type: str,
    rule_path: Path,
    field_name: str,
) -> int:
    if value is None:
        raise ValueError(
            f"Rule type '{rule_type}' for field '{field_name}' in '{rule_path}' requires a value."
        )
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Rule type '{rule_type}' for field '{field_name}' in '{rule_path}' requires an integer value."
        ) from exc


def _parse_float(
    value: Any,
    rule_type: str,
    rule_path: Path,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Rule type '{rule_type}' for field '{field_name}' in '{rule_path}' requires a numeric min/max value."
        ) from exc


def _parse_string(
    value: Any,
    rule_type: str,
    rule_path: Path,
    field_name: str,
) -> str:
    if value is None:
        raise ValueError(
            f"Rule type '{rule_type}' for field '{field_name}' in '{rule_path}' requires a value."
        )
    return str(value)


def _require_rule_value(
    value: Any,
    rule_type: str,
    rule_path: Path,
    field_name: str,
    key_name: str,
) -> str:
    if value is None or str(value).strip() == "":
        raise ValueError(
            f"Rule type '{rule_type}' for field '{field_name}' "
            f"in '{rule_path}' requires a '{key_name}' value."
        )
    return str(value)


def _require_cross_entity_operator(
    rule: dict[str, Any],
    rule_type: str,
    rule_path: Path,
) -> str:
    operator = rule.get("operator")
    field_name = str(rule["field"])
    if not operator:
        raise ValueError(
            f"Rule type '{rule_type}' for field '{field_name}' "
            f"in '{rule_path}' requires an 'operator' value."
        )
    normalized_operator = str(operator)
    if normalized_operator not in _CROSS_ENTITY_FIELD_OPERATORS:
        raise ValueError(
            f"Rule type '{rule_type}' for field '{field_name}' "
            f"in '{rule_path}' requires a named operator in "
            f"{sorted(_CROSS_ENTITY_FIELD_OPERATORS)}."
        )
    return normalized_operator


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
