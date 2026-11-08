from pathlib import Path

from appbuilder.mapping import (
    MappingDirection,
    build_output_mapping_artifacts,
    build_upstream_mapping_artifacts,
)


def test_build_upstream_mapping_artifacts_validates_sample_coverage(tmp_path: Path) -> None:
    mapping_path = tmp_path / "upstream-mapping.yaml"
    mapping_path.write_text(
        "\n".join(
            [
                "entity: Loan",
                "operations:",
                "  - name: createLoan",
                "    request_mappings:",
                "      - source: loanType",
                "        target: Loan.loanType",
            ]
        ),
        encoding="utf-8",
    )

    mappings, report, lookup, entity_name = build_upstream_mapping_artifacts(
        mapping_path=mapping_path,
        interface_name="crm-loan-api",
        declared_operations={"createLoan": {"request": ["loanType", "amount"]}},
    )

    assert entity_name == "Loan"
    assert len(mappings) == 1
    assert lookup[("createLoan", "request", "loanType")] == "Loan.loanType"
    assert report.status == "warning"
    assert report.issues[0].message == (
        "Sample field 'amount' in operation 'createLoan' request is not explicitly mapped."
    )


def test_build_output_mapping_artifacts_flags_unmapped_required_targets(tmp_path: Path) -> None:
    mapping_path = tmp_path / "handoff-mapping.yaml"
    mapping_path.write_text(
        "\n".join(
            [
                "entity: Loan",
                "field_mappings:",
                "  - source: Loan.loanId",
                "    target: loan_id",
            ]
        ),
        encoding="utf-8",
    )

    mappings, report, lookup, entity_name = build_output_mapping_artifacts(
        mapping_path=mapping_path,
        contract_name="loan-staging-table",
        direction=MappingDirection.CANONICAL_TO_HANDOFF,
        available_targets={"loan_id": True, "batch_flag": True, "comments": False},
    )

    assert entity_name == "Loan"
    assert len(mappings) == 1
    assert lookup["loan_id"] == "Loan.loanId"
    assert report.status == "error"
    assert [issue.message for issue in report.issues] == [
        "Contract target 'batch_flag' is required but not mapped.",
        "Contract target 'comments' is optional but not mapped.",
    ]
    assert [issue.severity.value for issue in report.issues] == ["error", "warning"]


def test_build_output_mapping_artifacts_carries_optional_type_coercion(tmp_path: Path) -> None:
    mapping_path = tmp_path / "handoff-mapping.yaml"
    mapping_path.write_text(
        "\n".join(
            [
                "entity: Account",
                "field_mappings:",
                "  - source: Account.availableBalance",
                "    target: available_balance_minor",
                "    type_coercion: major_to_minor_units",
                "  - source: Account.status",
                "    target: status",
            ]
        ),
        encoding="utf-8",
    )

    mappings, report, lookup, entity_name = build_output_mapping_artifacts(
        mapping_path=mapping_path,
        contract_name="account-eod-file",
        direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
        available_targets={"available_balance_minor": True, "status": True},
    )

    assert entity_name == "Account"
    assert report.status == "complete"
    assert lookup["available_balance_minor"] == "Account.availableBalance"
    assert mappings[0].type_coercion == "major_to_minor_units"
    assert mappings[1].type_coercion is None


def test_build_output_mapping_artifacts_rejects_unknown_type_coercion(tmp_path: Path) -> None:
    mapping_path = tmp_path / "handoff-mapping.yaml"
    mapping_path.write_text(
        "\n".join(
            [
                "entity: Account",
                "field_mappings:",
                "  - source: Account.availableBalance",
                "    target: available_balance_minor",
                "    type_coercion: major_to_minor_unit",
            ]
        ),
        encoding="utf-8",
    )

    mappings, report, lookup, entity_name = build_output_mapping_artifacts(
        mapping_path=mapping_path,
        contract_name="account-eod-file",
        direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
        available_targets={"available_balance_minor": True},
    )

    assert entity_name == "Account"
    assert mappings[0].type_coercion == "major_to_minor_unit"
    assert lookup["available_balance_minor"] == "Account.availableBalance"
    assert report.status == "error"
    assert [issue.message for issue in report.issues] == [
        "Mapping type_coercion 'major_to_minor_unit' is unsupported; "
        "supported values: major_to_minor_units."
    ]
