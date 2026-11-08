from pathlib import Path

import pytest

from appbuilder.rules import RuleType, load_rule_definitions


def test_load_rule_definitions_normalizes_supported_rule_types(tmp_path: Path) -> None:
    rule_path = tmp_path / "loan-rules.yaml"
    rule_path.write_text(
        "\n".join(
            [
                "entity: Loan",
                "rules:",
                "  - field: productCode",
                "    type: allowed-values",
                "    values: [AUTO, HOME]",
                "  - field: currency",
                "    type: iso-4217",
                "  - field: status",
                "    type: default",
                "    value: PENDING",
            ]
        ),
        encoding="utf-8",
    )

    entity_name, rules = load_rule_definitions(rule_path)

    assert entity_name == "Loan"
    assert [rule.type for rule in rules] == [
        RuleType.ALLOWED_VALUES,
        RuleType.FORMAT,
        RuleType.DEFAULT,
    ]
    assert rules[0].values == ["AUTO", "HOME"]
    assert rules[1].format == "iso-4217"
    assert rules[2].value == "PENDING"


def test_load_rule_definitions_parses_max_length_rule(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: accountNumber",
            "    type: max-length",
            '    value: "10"',
        ],
    )

    assert rule.type == RuleType.MAX_LENGTH
    assert rule.max_length == 10


def test_load_rule_definitions_parses_min_length_rule(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: accountNumber",
            "    type: min-length",
            '    value: "10"',
        ],
    )

    assert rule.type == RuleType.MIN_LENGTH
    assert rule.min_length == 10


def test_load_rule_definitions_parses_pattern_rule(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: accountNumber",
            "    type: pattern",
            '    value: "^[0-9]{10}$"',
        ],
    )

    assert rule.type == RuleType.PATTERN
    assert rule.pattern == "^[0-9]{10}$"


def test_load_rule_definitions_parses_range_rule(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: balance",
            "    type: range",
            '    min: "0.01"',
            '    max: "999999.99"',
        ],
    )

    assert rule.type == RuleType.RANGE
    assert rule.range_min == 0.01
    assert rule.range_max == 999999.99


def test_load_rule_definitions_parses_range_rule_with_only_min(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: balance",
            "    type: range",
            '    min: "0.01"',
        ],
    )

    assert rule.type == RuleType.RANGE
    assert rule.range_min == 0.01
    assert rule.range_max is None


def test_load_rule_definitions_parses_range_rule_with_only_max(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: balance",
            "    type: range",
            '    max: "999999.99"',
        ],
    )

    assert rule.type == RuleType.RANGE
    assert rule.range_min is None
    assert rule.range_max == 999999.99


def test_load_rule_definitions_parses_not_null_rule_without_extra_keys(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: customerId",
            "    type: not-null",
        ],
    )

    assert rule.type == RuleType.NOT_NULL
    assert rule.value is None
    assert rule.values == []


def test_load_rule_definitions_parses_cross_entity_field_check_rule(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: accountId",
            "    type: cross-entity-field-check",
            "    target-entity: Account",
            "    target-field: status",
            "    operator: eq",
            "    expected-value: ACTIVE",
            '    error-message: "Account is not active"',
        ],
    )

    assert rule.type == RuleType.CROSS_ENTITY_FIELD_CHECK
    assert rule.target_entity == "Account"
    assert rule.target_field == "status"
    assert rule.operator == "eq"
    assert rule.expected_value == "ACTIVE"
    assert rule.error_message == "Account is not active"


def test_load_rule_definitions_parses_cross_entity_field_compare_rule(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: accountId",
            "    type: cross-entity-field-compare",
            "    target-entity: Account",
            "    target-field: availableBalance",
            "    source-field: amount",
            "    operator: lte",
        ],
    )

    assert rule.type == RuleType.CROSS_ENTITY_FIELD_COMPARE
    assert rule.target_entity == "Account"
    assert rule.target_field == "availableBalance"
    assert rule.source_field == "amount"
    assert rule.operator == "lte"


def test_load_rule_definitions_parses_cross_entity_field_in_rule(tmp_path: Path) -> None:
    _, rule = _load_single_rule(
        tmp_path,
        [
            "  - field: counterpartyId",
            "    type: cross-entity-field-in",
            "    target-entity: Counterparty",
            "    target-field: sanctionsStatus",
            "    allowed-values: [CLEARED, PENDING_REVIEW]",
        ],
    )

    assert rule.type == RuleType.CROSS_ENTITY_FIELD_IN
    assert rule.target_entity == "Counterparty"
    assert rule.target_field == "sanctionsStatus"
    assert rule.values == ["CLEARED", "PENDING_REVIEW"]


@pytest.mark.parametrize(
    ("rule_lines", "message"),
    [
        (
            [
                "  - field: accountId",
                "    type: cross-entity-field-check",
                "    target-field: status",
                "    operator: eq",
                "    expected-value: ACTIVE",
            ],
            "target-entity",
        ),
        (
            [
                "  - field: accountId",
                "    type: cross-entity-field-check",
                "    target-entity: Account",
                "    operator: eq",
                "    expected-value: ACTIVE",
            ],
            "target-field",
        ),
        (
            [
                "  - field: accountId",
                "    type: cross-entity-field-compare",
                "    target-entity: Account",
                "    target-field: availableBalance",
                "    operator: lte",
            ],
            "source-field",
        ),
        (
            [
                "  - field: accountId",
                "    type: cross-entity-field-check",
                "    target-entity: Account",
                "    target-field: status",
                "    expected-value: ACTIVE",
            ],
            "operator",
        ),
        (
            [
                "  - field: accountId",
                "    type: cross-entity-field-compare",
                "    target-entity: Account",
                "    target-field: availableBalance",
                "    source-field: amount",
            ],
            "operator",
        ),
        (
            [
                "  - field: accountId",
                "    type: cross-entity-field-check",
                "    target-entity: Account",
                "    target-field: status",
                "    operator: equals",
                "    expected-value: ACTIVE",
            ],
            "named operator",
        ),
        (
            [
                "  - field: accountId",
                "    type: cross-entity-field-check",
                "    target-entity: Account",
                "    target-field: status",
                '    operator: "=="',
                "    expected-value: ACTIVE",
            ],
            "named operator",
        ),
        (
            [
                "  - field: accountId",
                "    type: cross-entity-field-check",
                "    target-entity: Account",
                "    target-field: status",
                "    operator: eq",
            ],
            "expected-value",
        ),
        (
            [
                "  - field: counterpartyId",
                "    type: cross-entity-field-in",
                "    target-entity: Counterparty",
                "    target-field: sanctionsStatus",
                "    allowed-values: []",
            ],
            "allowed-values",
        ),
    ],
)
def test_load_rule_definitions_rejects_invalid_cross_entity_field_rule_shapes(
    tmp_path: Path,
    rule_lines: list[str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _load_single_rule(tmp_path, rule_lines)


def test_load_rule_definitions_rejects_unknown_rule_type(tmp_path: Path) -> None:
    rule_path = tmp_path / "rules.yaml"
    rule_path.write_text(
        "\n".join(
            [
                "entity: Account",
                "rules:",
                "  - field: accountNumber",
                "    type: unsupported-rule",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported rule type 'unsupported-rule'"):
        load_rule_definitions(rule_path)


def _load_single_rule(tmp_path: Path, rule_lines: list[str]) -> tuple:
    rule_path = tmp_path / "account-rules.yaml"
    rule_path.write_text(
        "\n".join(
            [
                "entity: Account",
                "rules:",
                *rule_lines,
            ]
        ),
        encoding="utf-8",
    )

    entity_name, rules = load_rule_definitions(rule_path)
    assert len(rules) == 1
    return entity_name, rules[0]
