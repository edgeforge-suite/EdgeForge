import copy
import json
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.harness import (
    HarnessCheck,
    HarnessCheckSeverity,
    HarnessReport,
    run_compatibility_harness,
)
from appbuilder.harness.checks import (
    check_downstream_file_field_order,
    check_no_appbuilder_runtime_imports,
    check_staging_table_run_identity_contract,
)
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    ContractMetadata,
    MetadataProject,
    build_metadata_project,
)

_RUN_SEMANTICS_FIXTURE = Path(
    "tests/fixtures/manifest-v2-cut/v2-run-semantics-app-definition.yaml"
)


def test_harness_passes_on_xyz_accounts(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltApp1"
    generate_application(metadata, output_dir, generation_run_id="harness-pass")

    report = run_compatibility_harness(metadata, output_dir)

    assert report.passed is True
    assert report.errors == []


def test_harness_detects_missing_dto_field(tmp_path: Path) -> None:
    original = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltApp1"
    generate_application(original, output_dir, generation_run_id="missing-dto")

    metadata = _load_xyz_metadata()
    metadata.mappings.append(
        FieldMapping(
            contract_name="crm-account-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="createAccount",
            source_path="crm-account-api.createAccount.request.branchCode",
            target_path="Account.branchCode",
            source_required=True,
            source_location="test",
        )
    )

    report = run_compatibility_harness(metadata, output_dir)
    check = next(c for c in report.checks if c.name == "upstream_dto_fields_match_contract")

    assert check.passed is False
    assert check.severity == HarnessCheckSeverity.ERROR
    assert "branchCode" in check.message


def test_harness_detects_missing_flyway_column(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltApp1"
    generate_application(metadata, output_dir, generation_run_id="missing-flyway")

    mutated = _load_xyz_metadata()
    mutated.entities[0].fields.append(
        CanonicalField(
            name="openedOn",
            type=CanonicalFieldType.DATE,
            source_paths=["rules.Account.openedOn.default"],
        )
    )

    report = run_compatibility_harness(mutated, output_dir)
    check = next(c for c in report.checks if c.name == "flyway_columns_match_canonical_entity")

    assert check.passed is False
    assert check.severity == HarnessCheckSeverity.ERROR
    assert "opened_on" in check.message


def test_harness_errors_on_unmapped_required_staging_column(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltApp1"
    generate_application(metadata, output_dir, generation_run_id="required-staging")

    mutated = _load_xyz_metadata()
    mutated.mappings = [
        mapping
        for mapping in mutated.mappings
        if not (
            mapping.direction == MappingDirection.CANONICAL_TO_HANDOFF
            and mapping.contract_name == "account-staging-table"
            and mapping.source_path == "Account.accountId"
        )
    ]

    report = run_compatibility_harness(mutated, output_dir)
    check = next(
        c for c in report.checks if c.name == "staging_table_non_nullable_columns_all_mapped"
    )

    assert check.passed is False
    assert check.severity == HarnessCheckSeverity.ERROR
    assert "account-staging-table.Account.accountId" in check.message


def test_harness_warns_on_unmapped_optional_staging_column(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltApp1"
    generate_application(metadata, output_dir, generation_run_id="optional-staging")

    mutated = _load_xyz_metadata()
    mutated.mappings = [
        mapping
        for mapping in mutated.mappings
        if not (
            mapping.direction == MappingDirection.CANONICAL_TO_HANDOFF
            and mapping.contract_name == "account-staging-table"
            and mapping.source_path == "Account.status"
        )
    ]

    report = run_compatibility_harness(mutated, output_dir)
    check = next(
        c for c in report.checks if c.name == "staging_table_non_nullable_columns_all_mapped"
    )

    assert check.passed is False
    assert check.severity == HarnessCheckSeverity.WARNING
    assert "account-staging-table.Account.status" in check.message
    assert report.passed is True


def test_harness_warns_when_staging_table_lacks_run_identity() -> None:
    metadata = _load_xyz_metadata()

    [check] = check_staging_table_run_identity_contract(metadata, Path("unused"))

    assert check.passed is False
    assert check.severity == HarnessCheckSeverity.WARNING
    assert "staging table lacks run identity" in check.message
    assert "staging table lacks primary key" in check.message
    assert "rerun/restart semantics may not be production-ready" in check.message


def test_harness_accepts_declared_staging_run_identity_contract() -> None:
    metadata = _load_xyz_metadata()
    metadata.staging_table_ddls["acct_staging_tbl"] = """
    CREATE TABLE acct_staging_tbl (
        staging_row_id VARCHAR(36) NOT NULL PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL,
        status_cd VARCHAR(20)
    );
    """

    [check] = check_staging_table_run_identity_contract(metadata, Path("unused"))

    assert check.passed is True


def test_harness_reports_no_staging_contracts_as_informational() -> None:
    metadata = _load_xyz_metadata()
    metadata.contracts = [
        contract for contract in metadata.contracts if contract.type != "staging-table"
    ]
    metadata.staging_table_ddls = {}

    [check] = check_staging_table_run_identity_contract(metadata, Path("unused"))

    assert check.passed is True
    assert check.severity == HarnessCheckSeverity.INFO
    assert "No staging-table contracts" in check.message


def test_harness_accepts_generated_opted_in_run_identity_contract(
    tmp_path: Path,
) -> None:
    metadata = build_metadata_project(_RUN_SEMANTICS_FIXTURE)

    generation_report = generate_application(
        metadata,
        tmp_path / "valid-opted-in",
        generation_run_id="m5a-s4-valid-opted-in",
    )

    assert generation_report.harness_report is not None
    report = generation_report.harness_report
    check = next(
        check
        for check in report.checks
        if check.name == "staging_table_run_identity_contract:widget-staging"
    )
    assert check.passed is True
    assert check.severity == HarnessCheckSeverity.ERROR
    assert "widget-staging" in check.message
    assert report.passed is True


@pytest.mark.parametrize(
    ("ddl_mutation", "diagnostic"),
    [
        (lambda metadata: metadata.staging_table_ddls.clear(), "unable to inspect staging DDL"),
        (
            lambda metadata: metadata.staging_table_ddls.__setitem__(
                "widget_staging",
                metadata.staging_table_ddls["widget_staging"].replace(
                    "staging_row_id VARCHAR(36) PRIMARY KEY",
                    "staging_row_id VARCHAR(36)",
                ),
            ),
            "staging table lacks primary key",
        ),
        (
            lambda metadata: metadata.staging_table_ddls.__setitem__(
                "widget_staging",
                metadata.staging_table_ddls["widget_staging"].replace(
                    "run_id VARCHAR(64) NOT NULL,\n",
                    "",
                ),
            ),
            "staging table lacks run identity",
        ),
        (
            lambda metadata: metadata.staging_table_ddls.__setitem__(
                "widget_staging",
                metadata.staging_table_ddls["widget_staging"].replace(
                    "run_id VARCHAR(64) NOT NULL",
                    "eod_run_id VARCHAR(64) NOT NULL",
                ),
            ),
            "declared column 'run_id' is absent or not recognized",
        ),
    ],
    ids=[
        "missing-ddl",
        "missing-primary-key",
        "missing-run-id",
        "different-run-id-alias",
    ],
)
def test_harness_blocks_invalid_opted_in_run_identity_contract(
    ddl_mutation,
    diagnostic: str,
    tmp_path: Path,
) -> None:
    metadata = build_metadata_project(_RUN_SEMANTICS_FIXTURE)
    output_dir = tmp_path / "invalid-opted-in"
    generate_application(
        metadata,
        output_dir,
        generation_run_id="m5a-s4-invalid-opted-in",
    )
    ddl_mutation(metadata)

    report = run_compatibility_harness(metadata, output_dir)

    check = next(
        check
        for check in report.checks
        if check.name == "staging_table_run_identity_contract:widget-staging"
    )
    assert check.passed is False
    assert check.severity == HarnessCheckSeverity.ERROR
    assert "widget-staging" in check.message
    assert diagnostic in check.message
    assert report.passed is False


def test_harness_keeps_invalid_legacy_handoff_advisory_in_mixed_project(
    tmp_path: Path,
) -> None:
    metadata = build_metadata_project(_RUN_SEMANTICS_FIXTURE)
    output_dir = tmp_path / "mixed-mode"
    generate_application(
        metadata,
        output_dir,
        generation_run_id="m5a-s4-mixed-mode",
    )
    metadata.contracts.append(
        ContractMetadata(
            name="legacy-widget-staging",
            type="staging-table",
            source="data-handoffs/legacy-widget-staging.sql",
            physical_name="legacy_widget_staging",
        )
    )
    metadata.staging_table_ddls["legacy_widget_staging"] = (
        "CREATE TABLE legacy_widget_staging (payload VARCHAR(64));\n"
    )

    report = run_compatibility_harness(metadata, output_dir)

    run_identity_checks = [
        check
        for check in report.checks
        if check.name.startswith("staging_table_run_identity_contract:")
    ]
    assert [check.name for check in run_identity_checks] == [
        "staging_table_run_identity_contract:legacy-widget-staging",
        "staging_table_run_identity_contract:widget-staging",
    ]
    legacy_check, opted_in_check = run_identity_checks
    assert legacy_check.passed is False
    assert legacy_check.severity == HarnessCheckSeverity.WARNING
    assert "staging table lacks primary key" in legacy_check.message
    assert "staging table lacks run identity" in legacy_check.message
    assert opted_in_check.passed is True
    assert opted_in_check.severity == HarnessCheckSeverity.ERROR
    assert report.passed is True


def test_harness_checks_all_upstream_operations(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    output_dir = tmp_path / "BuiltApp1"
    generate_application(metadata, output_dir, generation_run_id="multi-operation")

    mutated = _load_xyz_metadata()
    mutated.operations.append(
        CanonicalOperation(
            name="getAccount",
            interface_name="crm-account-api",
            request_entity="Account",
            response_entity="Account",
        )
    )
    mutated.mappings.append(
        FieldMapping(
            contract_name="crm-account-api",
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            operation_name="getAccount",
            source_path="crm-account-api.getAccount.request.accountId",
            target_path="Account.accountId",
            source_required=True,
            source_location="test",
        )
    )

    report = run_compatibility_harness(mutated, output_dir)
    check = next(c for c in report.checks if c.name == "upstream_dto_fields_match_contract")

    assert check.passed is False
    assert check.severity == HarnessCheckSeverity.ERROR
    assert "getAccount" in check.message
    assert "GetAccountRequest.java" in check.message


def test_harness_errors_on_appbuilder_import_in_generated_code(tmp_path: Path) -> None:
    metadata = _load_xyz_metadata()
    java_dir = tmp_path / "BuiltApp1" / "src" / "main" / "java" / "com" / "example"
    java_dir.mkdir(parents=True, exist_ok=True)
    (java_dir / "Injected.java").write_text(
        "\n".join(
            [
                "package com.example;",
                "",
                "import appbuilder.generation.Foo;",
                "",
                "public class Injected {",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    check = check_no_appbuilder_runtime_imports(metadata, tmp_path / "BuiltApp1")

    assert check.passed is False
    assert check.severity == HarnessCheckSeverity.ERROR
    assert "Injected.java" in check.message


def test_downstream_file_order_check_reads_current_padded_writer_shape(tmp_path: Path) -> None:
    metadata = _file_order_metadata()
    _write_customer_writer(
        tmp_path,
        """
        public String renderLine(Customer customer) {
            StringBuilder line = new StringBuilder();
            line.append(padRight(stringValue(customer.getCustomerId()), 12));
            line.append(padRight(stringValue(customer.getCountryCode()), 2));
            line.append(padRight(stringValue(customer.getKycStatusFlag()), 1));
            return line.toString();
        }
        """,
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is True


def test_downstream_file_order_check_ignores_upstream_fixed_width_contract(
    tmp_path: Path,
) -> None:
    metadata = MetadataProject(
        app_name="Inbound File",
        bounded_context="accounts",
        target_profile="springboot-legacy-compatible",
        contracts=[
            ContractMetadata(
                name="account-inbound-file",
                type="file-fixed-width",
                source="upstream/account-inbound-layout.yaml",
            )
        ],
        entities=[
            CanonicalEntity(
                name="Account",
                fields=[
                    CanonicalField(name="accountId", type=CanonicalFieldType.STRING),
                ],
            )
        ],
        mappings=[
            FieldMapping(
                contract_name="account-inbound-file",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                source_path="account-inbound-file.file.account_id",
                target_path="Account.accountId",
            ),
        ],
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is True
    assert "No fixed-width downstream contracts" in check.message


def test_downstream_file_order_check_reads_current_unpadded_writer_shape(tmp_path: Path) -> None:
    metadata = _file_order_metadata()
    _write_customer_writer(
        tmp_path,
        """
        public String renderLine(Customer customer) {
            StringBuilder line = new StringBuilder();
            line.append(stringValue(customer.getCustomerId()));
            line.append(stringValue(customer.getCountryCode()));
            line.append(stringValue(customer.getKycStatusFlag()));
            return line.toString();
        }
        """,
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is True


def test_downstream_file_order_check_still_reads_old_values_put_shape(tmp_path: Path) -> None:
    metadata = _file_order_metadata()
    _write_customer_writer(
        tmp_path,
        """
        public Map<String, String> values(Customer customer) {
            Map<String, String> values = new LinkedHashMap<>();
            values.put("customer_id", stringValue(customer.getCustomerId()));
            values.put("country_code", stringValue(customer.getCountryCode()));
            values.put("kyc_status_flag", stringValue(customer.getKycStatusFlag()));
            return values;
        }
        """,
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is True


def test_downstream_file_order_check_preserves_repeated_source_output_fields(
    tmp_path: Path,
) -> None:
    metadata = _file_order_metadata()
    metadata.mappings.insert(
        1,
        FieldMapping(
            contract_name="payment-batch-eod-file",
            direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
            source_path="Customer.customerId",
            target_path="payment-batch-eod-file.Customer.legacy_customer_id",
            layout_width=12,
        ),
    )
    _write_customer_writer(
        tmp_path,
        """
        public String renderLine(Customer customer) {
            StringBuilder line = new StringBuilder();
            line.append(padRight(stringValue(customer.getCustomerId()), 12));
            line.append(padRight(stringValue(customer.getCustomerId()), 12));
            line.append(padRight(stringValue(customer.getCountryCode()), 2));
            line.append(padRight(stringValue(customer.getKycStatusFlag()), 1));
            return line.toString();
        }
        """,
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is True


def test_downstream_file_order_check_reads_minor_unit_writer_shape(tmp_path: Path) -> None:
    metadata = _file_order_metadata()
    metadata.mappings.insert(
        1,
        FieldMapping(
            contract_name="payment-batch-eod-file",
            direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
            source_path="Customer.customerId",
            target_path="payment-batch-eod-file.Customer.customer_id_minor",
            layout_width=12,
            type_coercion="major_to_minor_units",
        ),
    )
    _write_customer_writer(
        tmp_path,
        """
        public String renderLine(Customer customer) {
            StringBuilder line = new StringBuilder();
            line.append(padRight(stringValue(customer.getCustomerId()), 12));
            line.append(fixedWidthMinorUnitString(customer.getCustomerId(), 12));
            line.append(padRight(stringValue(customer.getCountryCode()), 2));
            line.append(padRight(stringValue(customer.getKycStatusFlag()), 1));
            return line.toString();
        }
        """,
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is True


def test_downstream_file_order_check_reads_enhanced_fixed_width_writer_shape(
    tmp_path: Path,
) -> None:
    metadata = _file_order_metadata()
    _write_customer_writer(
        tmp_path,
        """
        public String renderHeader(String runId) {
            StringBuilder line = new StringBuilder();
            line.append(formatFixedWidthField("file_date", LocalDate.now(), true, "date", "yyyyMMdd", 8, false));
            return line.toString();
        }

        private String renderDataLine(Customer customer) {
            StringBuilder line = new StringBuilder();
            line.append(formatFixedWidthField("customer_id", customer.getCustomerId(), true, "string", null, 12, false));
            line.append(formatFixedWidthField("country_code", customer.getCountryCode(), true, "string", null, 2, false));
            line.append(formatFixedWidthField("kyc_status_flag", customer.getKycStatusFlag(), true, "string", null, 1, false));
            return line.toString();
        }

        public String renderTrailer(long recordCount, BigDecimal totalValue) {
            StringBuilder line = new StringBuilder();
            line.append(formatFixedWidthField("record_count", recordCount, true, "integer", null, 8, true));
            return line.toString();
        }
        """,
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is True


def test_downstream_file_order_check_uses_per_contract_writer_names(
    tmp_path: Path,
) -> None:
    metadata = _file_order_metadata()
    metadata.contracts.append(
        ContractMetadata(name="payment-batch-recon-csv", type="file-csv", source="")
    )
    metadata.mappings.append(
        FieldMapping(
            contract_name="payment-batch-recon-csv",
            direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
            source_path="Customer.customerId",
            target_path="payment-batch-recon-csv.customer_id",
        )
    )
    _write_customer_writer(
        tmp_path,
        """
        public String renderLine(Customer customer) {
            StringBuilder line = new StringBuilder();
            line.append(padRight(stringValue(customer.getCustomerId()), 12));
            line.append(padRight(stringValue(customer.getCountryCode()), 2));
            line.append(padRight(stringValue(customer.getKycStatusFlag()), 1));
            return line.toString();
        }
        """,
        writer_class_name="CustomerPaymentBatchEodFileFileWriter",
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is True
    assert "CustomerEodHandoffFileWriter" not in check.message


def test_downstream_file_order_check_detects_missing_current_writer_field(tmp_path: Path) -> None:
    metadata = _file_order_metadata()
    _write_customer_writer(
        tmp_path,
        """
        public String renderLine(Customer customer) {
            StringBuilder line = new StringBuilder();
            line.append(padRight(stringValue(customer.getCustomerId()), 12));
            line.append(padRight(stringValue(customer.getCountryCode()), 2));
            return line.toString();
        }
        """,
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is False
    assert "kyc_status_flag" in check.message


def test_downstream_file_order_check_detects_wrong_current_writer_order(tmp_path: Path) -> None:
    metadata = _file_order_metadata()
    _write_customer_writer(
        tmp_path,
        """
        public String renderLine(Customer customer) {
            StringBuilder line = new StringBuilder();
            line.append(padRight(stringValue(customer.getCountryCode()), 2));
            line.append(padRight(stringValue(customer.getCustomerId()), 12));
            line.append(padRight(stringValue(customer.getKycStatusFlag()), 1));
            return line.toString();
        }
        """,
    )

    check = check_downstream_file_field_order(metadata, tmp_path)

    assert check.passed is False
    assert "expected ['customer_id', 'country_code', 'kyc_status_flag']" in check.message
    assert "got ['country_code', 'customer_id', 'kyc_status_flag']" in check.message


def test_harness_report_passed_property() -> None:
    report = HarnessReport(
        output_dir=Path("BuiltApp1"),
        checks=[
            HarnessCheck(
                name="error-check",
                severity=HarnessCheckSeverity.ERROR,
                passed=False,
                message="error",
            ),
            HarnessCheck(
                name="warning-check",
                severity=HarnessCheckSeverity.WARNING,
                passed=False,
                message="warning",
            ),
        ],
    )

    assert report.passed is False

    warning_only = HarnessReport(
        output_dir=Path("BuiltApp1"),
        checks=[
            HarnessCheck(
                name="warning-check",
                severity=HarnessCheckSeverity.WARNING,
                passed=False,
                message="warning",
            )
        ],
    )

    assert warning_only.passed is True


def _load_xyz_metadata() -> MetadataProject:
    payload = json.loads(
        Path("tests/golden_contracts/xyz_accounts_metadata.json").read_text(encoding="utf-8")
    )
    return MetadataProject.model_validate(copy.deepcopy(payload))


def _file_order_metadata() -> MetadataProject:
    return MetadataProject(
        app_name="Payment Batch",
        bounded_context="payments",
        target_profile="springboot-legacy-compatible",
        contracts=[
            ContractMetadata(
                name="payment-batch-eod-file",
                type="file-fixed-width",
                source="downstream/payment-batch-eod-file-layout.yaml",
            )
        ],
        entities=[
            CanonicalEntity(
                name="Customer",
                fields=[
                    CanonicalField(name="customerId", type=CanonicalFieldType.STRING),
                    CanonicalField(name="countryCode", type=CanonicalFieldType.STRING),
                    CanonicalField(name="kycStatusFlag", type=CanonicalFieldType.STRING),
                ],
            )
        ],
        mappings=[
            FieldMapping(
                contract_name="payment-batch-eod-file",
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                source_path="Customer.customerId",
                target_path="payment-batch-eod-file.Customer.customer_id",
                layout_width=12,
            ),
            FieldMapping(
                contract_name="payment-batch-eod-file",
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                source_path="Customer.countryCode",
                target_path="payment-batch-eod-file.Customer.country_code",
                layout_width=2,
            ),
            FieldMapping(
                contract_name="payment-batch-eod-file",
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                source_path="Customer.kycStatusFlag",
                target_path="payment-batch-eod-file.Customer.kyc_status_flag",
                layout_width=1,
            ),
        ],
    )


def _write_customer_writer(
    output_dir: Path,
    body: str,
    *,
    writer_class_name: str = "CustomerEodHandoffFileWriter",
) -> None:
    writer_dir = (
        output_dir
        / "src"
        / "main"
        / "java"
        / "com"
        / "appbuilder"
        / "payments"
        / "adapter"
        / "outbound"
    )
    writer_dir.mkdir(parents=True, exist_ok=True)
    (writer_dir / f"{writer_class_name}.java").write_text(body, encoding="utf-8")
