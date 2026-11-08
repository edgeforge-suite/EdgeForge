from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from appbuilder.core.sql_safety import StagingDdlValidationError, validate_staging_ddl
from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project

_FIXTURE_ROOT = (
    Path(__file__).parents[1]
    / "fixtures"
    / "generated-app-quality"
    / "crud-minor-units-date"
)
_DDL_RELATIVE_PATH = Path("data-handoffs/account-staging-table.sql")
_MAPPING_RELATIVE_PATH = Path("data-handoffs/account-staging-mapping.yaml")


def _copy_project_with_ddl(tmp_path: Path, ddl_content: str) -> Path:
    project_root = tmp_path / "staging-ddl-project"
    shutil.copytree(_FIXTURE_ROOT, project_root)
    (project_root / _DDL_RELATIVE_PATH).write_text(ddl_content, encoding="utf-8")
    return project_root / "app-definition.yaml"


def _valid_ddl() -> str:
    return (_FIXTURE_ROOT / _DDL_RELATIVE_PATH).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("construct", "hostile_statement"),
    [
        ("DROP", "DROP TABLE account_staging_tbl;"),
        ("ALTER", "ALTER TABLE account_staging_tbl ADD COLUMN injected VARCHAR(20);"),
        ("GRANT", "GRANT SELECT ON account_staging_tbl TO PUBLIC;"),
        ("INSERT", "INSERT INTO account_staging_tbl (account_id) VALUES ('x');"),
        ("DELETE", "DELETE FROM account_staging_tbl;"),
        ("DO", "DO BEGIN PERFORM dangerous_call; END;"),
    ],
)
def test_staging_ddl_rejects_out_of_contract_statement_forms(
    tmp_path: Path,
    construct: str,
    hostile_statement: str,
) -> None:
    manifest_path = _copy_project_with_ddl(
        tmp_path,
        _valid_ddl() + "\n" + hostile_statement + "\n",
    )

    with pytest.raises(StagingDdlValidationError) as exc_info:
        build_metadata_project(manifest_path)

    message = str(exc_info.value)
    assert "account-staging-table" in message
    assert construct in message
    assert "Permitted v1 input" in message


def test_staging_ddl_rejects_statement_targeting_another_table(tmp_path: Path) -> None:
    manifest_path = _copy_project_with_ddl(
        tmp_path,
        _valid_ddl() + "\nCREATE INDEX account_idx ON unrelated_table (account_id);\n",
    )

    with pytest.raises(
        StagingDdlValidationError,
        match="CREATE INDEX target 'unrelated_table'.*handoff table 'account_staging_tbl'",
    ):
        build_metadata_project(manifest_path)


def test_staging_ddl_rejects_create_table_that_disagrees_with_mapping(tmp_path: Path) -> None:
    manifest_path = _copy_project_with_ddl(
        tmp_path,
        _valid_ddl().replace("account_staging_tbl", "unrelated_table", 1),
    )

    with pytest.raises(
        StagingDdlValidationError,
        match="CREATE TABLE target 'unrelated_table'.*declared table 'account_staging_tbl'",
    ):
        build_metadata_project(manifest_path)


def test_staging_ddl_rejects_unrecognised_sql_instead_of_skipping_it(tmp_path: Path) -> None:
    malformed = _valid_ddl().replace(
        "    account_id VARCHAR(36),",
        "    account_id VARCHAR(36) MYSTERY CLAUSE,",
    )
    manifest_path = _copy_project_with_ddl(tmp_path, malformed)

    with pytest.raises(
        StagingDdlValidationError,
        match="unsupported column construct 'MYSTERY'.*account_id",
    ):
        build_metadata_project(manifest_path)


def test_staging_ddl_rejects_quoted_identifier_outside_safe_filename_shape(
    tmp_path: Path,
) -> None:
    manifest_path = _copy_project_with_ddl(
        tmp_path,
        _valid_ddl().replace("account_staging_tbl", '"account staging"', 1),
    )

    with pytest.raises(
        StagingDdlValidationError,
        match="quoted identifier in CREATE statement.*simple identifier boundary",
    ):
        build_metadata_project(manifest_path)


def test_staging_ddl_accepts_scoped_index_and_preserves_decoded_text(tmp_path: Path) -> None:
    ddl_content = _valid_ddl().replace(
        "    staging_row_id VARCHAR(36) NOT NULL PRIMARY KEY,",
        "    staging_row_id VARCHAR(36) NOT NULL,",
    ).replace(
        "    available_balance DECIMAL(19,4) NOT NULL\n);",
        "    available_balance DECIMAL(19,4) NOT NULL,\n"
        "    CONSTRAINT account_staging_pk PRIMARY KEY (staging_row_id)\n);",
    ) + (
        "\n-- A bounded index on the declared table is part of the approved v1 input.\n"
        "CREATE UNIQUE INDEX account_staging_account_idx "
        "ON account_staging_tbl (account_id DESC);\n"
    )
    manifest_path = _copy_project_with_ddl(tmp_path, ddl_content)

    metadata = build_metadata_project(manifest_path)

    assert metadata.staging_table_ddls == {"account_staging_tbl": ddl_content}


def test_staging_ddl_rejects_mapping_with_invalid_declared_table(tmp_path: Path) -> None:
    manifest_path = _copy_project_with_ddl(tmp_path, _valid_ddl())
    mapping_path = manifest_path.parent / _MAPPING_RELATIVE_PATH
    mapping_path.write_text(
        mapping_path.read_text(encoding="utf-8").replace(
            "table: account_staging_tbl",
            "table: ''",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="field 'table' must be non-empty text"):
        build_metadata_project(manifest_path)


@pytest.mark.parametrize(
    "ddl_content",
    [
        "CREATE TABLE IF NOT EXISTS account_staging_tbl (account_id VARCHAR(36));",
        (
            "CREATE TABLE account_staging_tbl (account_id VARCHAR(36)); "
            "CREATE INDEX IF NOT EXISTS account_idx ON account_staging_tbl (account_id);"
        ),
    ],
)
def test_staging_ddl_rejects_if_not_exists(tmp_path: Path, ddl_content: str) -> None:
    manifest_path = _copy_project_with_ddl(tmp_path, ddl_content)

    with pytest.raises(StagingDdlValidationError, match="IF NOT EXISTS is not permitted"):
        build_metadata_project(manifest_path)


def test_staging_ddl_rejects_duplicate_physical_table_across_handoffs(tmp_path: Path) -> None:
    manifest_path = _copy_project_with_ddl(tmp_path, _valid_ddl())
    project_root = manifest_path.parent
    duplicate_ddl = project_root / "data-handoffs/duplicate-staging-table.sql"
    duplicate_mapping = project_root / "data-handoffs/duplicate-staging-mapping.yaml"
    duplicate_ddl.write_text(_valid_ddl(), encoding="utf-8")
    duplicate_mapping.write_text(
        (_FIXTURE_ROOT / _MAPPING_RELATIVE_PATH).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["data_handoffs"].append(
        {
            "name": "duplicate-account-staging",
            "system": "ETL",
            "type": "staging-table",
            "spec": "data-handoffs/duplicate-staging-table.sql",
            "mapping": "data-handoffs/duplicate-staging-mapping.yaml",
        }
    )
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="duplicate-account-staging.*account_staging_tbl.*account-staging-table",
    ):
        build_metadata_project(manifest_path)


@pytest.mark.parametrize("table_name", ["flyway_schema_history", "account"])
def test_staging_ddl_rejects_engine_managed_or_entity_table_collision(
    tmp_path: Path,
    table_name: str,
) -> None:
    manifest_path = _copy_project_with_ddl(
        tmp_path,
        _valid_ddl().replace("account_staging_tbl", table_name, 1),
    )
    mapping_path = manifest_path.parent / _MAPPING_RELATIVE_PATH
    mapping_path.write_text(
        mapping_path.read_text(encoding="utf-8").replace("account_staging_tbl", table_name),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=f"protected table '{table_name}'"):
        build_metadata_project(manifest_path)


def test_staging_ddl_rejects_entity_table_introduced_by_handoff_mapping(
    tmp_path: Path,
) -> None:
    manifest_path = _copy_project_with_ddl(
        tmp_path,
        _valid_ddl().replace("account_staging_tbl", "account", 1),
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["upstream_interfaces"] = []
    manifest["downstream_interfaces"] = []
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    mapping_path = manifest_path.parent / _MAPPING_RELATIVE_PATH
    mapping_path.write_text(
        mapping_path.read_text(encoding="utf-8").replace("account_staging_tbl", "account"),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="account-staging-table.*protected table 'account'.*generated entity 'Account'",
    ):
        build_metadata_project(manifest_path)


def test_table_level_primary_key_is_required_for_mapping_completeness(tmp_path: Path) -> None:
    ddl_content = _valid_ddl().replace(
        "staging_row_id VARCHAR(36) NOT NULL PRIMARY KEY,",
        "staging_row_id VARCHAR(36) NOT NULL,",
    ).replace(
        "    available_balance DECIMAL(19,4) NOT NULL\n);",
        "    available_balance DECIMAL(19,4) NOT NULL,\n"
        "    PRIMARY KEY (account_id)\n);",
    )
    manifest_path = _copy_project_with_ddl(tmp_path, ddl_content)
    mapping_path = manifest_path.parent / _MAPPING_RELATIVE_PATH
    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    mapping["field_mappings"] = [
        field_mapping
        for field_mapping in mapping["field_mappings"]
        if field_mapping["target"] != "account_id"
    ]
    mapping_path.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest_path)
    handoff_report = next(
        report for report in metadata.mapping_reports if report.contract_name == "account-staging-table"
    )

    assert handoff_report.status == "error"
    assert any(
        issue.message == "Contract target 'account_id' is required but not mapped."
        for issue in handoff_report.issues
    )


@pytest.mark.parametrize(
    ("ddl_content", "message"),
    [
        ("CREATE TABLE select (account_id INT);", "reserved word 'select'"),
        ("CREATE TABLE account_staging_tbl (from INT);", "reserved word 'from'"),
        (
            "CREATE TABLE account_staging_tbl (account_id DATE(1,2));",
            "DATE.*does not accept modifiers",
        ),
        (
            "CREATE TABLE account_staging_tbl (account_id TEXT(1,2));",
            "TEXT.*does not accept modifiers",
        ),
        (
            "CREATE TABLE account_staging_tbl (account_id VARCHAR(10,2));",
            "VARCHAR.*at most one length",
        ),
        (
            "CREATE TABLE account_staging_tbl (account_id DECIMAL(2,3));",
            "DECIMAL.*scale must be between zero and precision",
        ),
        ("CREATE TABLE ß (account_id INT);", "unrecognised token 'ß'"),
        ("CREATE TABLE user (account_id INT);", "reserved word 'user'"),
        (
            "CREATE TABLE account_staging_tbl (account_id VARCHAR(١٠));",
            "unrecognised token '١'",
        ),
        (
            "CREATE TABLE account_staging_tbl (id INT PRIMARY KEY, other INT PRIMARY KEY);",
            "multiple PRIMARY KEY definitions",
        ),
    ],
)
def test_staging_ddl_rejects_nonportable_identifiers_and_type_modifiers(
    tmp_path: Path,
    ddl_content: str,
    message: str,
) -> None:
    manifest_path = _copy_project_with_ddl(tmp_path, ddl_content)

    with pytest.raises(StagingDdlValidationError, match=message):
        build_metadata_project(manifest_path)


def test_one_line_staging_ddl_generates_complete_operational_writer(tmp_path: Path) -> None:
    ddl_content = (
        "CREATE TABLE account_staging_tbl ("
        "staging_row_id VARCHAR(36) NOT NULL PRIMARY KEY, "
        "run_id VARCHAR(64) NOT NULL, business_date DATE NOT NULL, "
        "staging_status VARCHAR(20) NOT NULL, created_at TIMESTAMP, "
        "account_id VARCHAR(36), account_number VARCHAR(12) NOT NULL, "
        "opened_date DATE NOT NULL, available_balance DECIMAL(19,4) NOT NULL);"
    )
    manifest_path = _copy_project_with_ddl(tmp_path, ddl_content)
    metadata = build_metadata_project(manifest_path)
    output_dir = tmp_path / "generated-app"

    generate_application(
        metadata,
        output_dir,
        source_manifest=manifest_path.name,
        generation_run_id="one-line-staging-ddl",
    )

    writer = (
        output_dir
        / "src/main/java/com/appbuilder/minorunitsdate/adapter/outbound/AccountStagingWriter.java"
    ).read_text(encoding="utf-8")
    assert (
        "INSERT INTO account_staging_tbl (staging_row_id, run_id, business_date, "
        "staging_status, created_at, account_id, account_number, opened_date, "
        "available_balance)"
    ) in writer
    assert "UUID.randomUUID().toString()" in writer
    assert "businessDate" in writer
    assert '"READY"' in writer


def test_h2_profile_accepts_h2_blob_staging_column(tmp_path: Path) -> None:
    manifest_path = _copy_project_with_ddl(
        tmp_path,
        _valid_ddl().replace(
            "    available_balance DECIMAL(19,4) NOT NULL\n);",
            "    available_balance DECIMAL(19,4) NOT NULL,\n"
            "    opaque_payload BLOB\n);",
        ),
    )

    metadata = build_metadata_project(manifest_path)

    assert metadata.target_profile == "springboot-legacy-compatible"


def test_postgresql_profile_rejects_h2_only_staging_type(tmp_path: Path) -> None:
    manifest_path = _copy_project_with_ddl(
        tmp_path,
        _valid_ddl().replace(
            "    available_balance DECIMAL(19,4) NOT NULL\n);",
            "    available_balance DECIMAL(19,4) NOT NULL,\n"
            "    opaque_payload BLOB\n);",
        ),
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["target_profile"] = "springboot-enterprise-postgres-java17"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        StagingDdlValidationError,
        match="column type 'BLOB' is unsupported.*valid for postgresql",
    ):
        build_metadata_project(manifest_path)


def test_postgresql_profile_accepts_portable_staging_types(tmp_path: Path) -> None:
    manifest_path = _copy_project_with_ddl(tmp_path, _valid_ddl())
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["target_profile"] = "springboot-enterprise-postgres-java17"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    metadata = build_metadata_project(manifest_path)

    assert metadata.target_profile == "springboot-enterprise-postgres-java17"


@pytest.mark.parametrize(
    ("database", "column_type", "message"),
    [
        (
            "postgresql",
            "DECIMAL(1001,0)",
            "precision 1001 exceeds postgresql maximum 1000",
        ),
        (
            "postgresql",
            "VARCHAR(10485761)",
            "length 10485761 exceeds postgresql maximum 10485760",
        ),
        (
            "h2",
            "DECIMAL(100001,0)",
            "precision 100001 exceeds h2 maximum 100000",
        ),
        (
            "h2",
            "VARCHAR(1000000001)",
            "length 1000000001 exceeds h2 maximum 1000000000",
        ),
    ],
)
def test_staging_ddl_rejects_target_modifier_max_plus_one(
    database: str,
    column_type: str,
    message: str,
) -> None:
    ddl_content = f"CREATE TABLE staging_limits (payload {column_type});"

    with pytest.raises(StagingDdlValidationError, match=message):
        validate_staging_ddl(
            ddl_content,
            handoff_name="modifier-limit-handoff",
            database=database,
        )


@pytest.mark.parametrize(
    ("database", "column_type"),
    [
        ("postgresql", "DECIMAL(1000,0)"),
        ("postgresql", "VARCHAR(10485760)"),
        ("h2", "DECIMAL(100000,0)"),
        ("h2", "VARCHAR(1000000000)"),
    ],
)
def test_staging_ddl_accepts_target_modifier_maximum(
    database: str,
    column_type: str,
) -> None:
    validated = validate_staging_ddl(
        f"CREATE TABLE staging_limits (payload {column_type});",
        handoff_name="modifier-limit-handoff",
        database=database,
    )

    assert validated.table_name == "staging_limits"


def test_staging_ddl_rejects_oversized_modifier_with_handoff_diagnostic() -> None:
    oversized_modifier = "9" * 5_000

    with pytest.raises(StagingDdlValidationError) as exc_info:
        validate_staging_ddl(
            f"CREATE TABLE staging_limits (payload VARCHAR({oversized_modifier}));",
            handoff_name="oversized-modifier-handoff",
            database="h2",
        )

    message = str(exc_info.value)
    assert "oversized-modifier-handoff" in message
    assert "type modifier has too many digits to validate safely" in message
