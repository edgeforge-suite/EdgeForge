from __future__ import annotations

import copy
import io
import shutil
from collections.abc import Callable
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any

import pytest
import yaml

from appbuilder.cli import main
from appbuilder.contracts import load_project_definition, validate_package
from appbuilder.core.path_safety import ALLOWED_ROOTS_ENV
from appbuilder.mcp.tools.generation import validate_manifest
from appbuilder.metadata import build_metadata_project

_FIXTURE_DIR = Path("tests/fixtures/manifest-v2-cut")
_MANIFEST_NAME = "v2-run-semantics-app-definition.yaml"


def _copy_fixture(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    package_dir = tmp_path / "package"
    shutil.copytree(_FIXTURE_DIR, package_dir)
    manifest_path = package_dir / _MANIFEST_NAME
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return manifest_path, payload


def _write_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    manifest_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def _assert_raw_and_package_reject(
    manifest_path: Path,
    payload: dict[str, Any],
    *,
    diagnostic: str = "run_semantics",
) -> None:
    errors = validate_package(payload)
    assert errors
    assert any(diagnostic in error for error in errors)
    _write_manifest(manifest_path, payload)
    with pytest.raises(ValueError, match=diagnostic):
        load_project_definition(manifest_path)


def test_valid_run_semantics_has_raw_package_and_mcp_parity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)

    assert validate_package(payload) == []
    definition = load_project_definition(manifest_path)
    run_semantics = definition.data_handoffs[0].run_semantics
    assert run_semantics is not None
    assert run_semantics.run_id == "caller_supplied"
    assert run_semantics.restart == "resume"
    assert run_semantics.dedup_key == ["widget_id", "payload_key"]
    assert run_semantics.internal_schema_id is None

    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(tmp_path))
    mcp_result = validate_manifest(str(manifest_path))
    assert mcp_result.valid is True
    assert mcp_result.errors == []


def test_unknown_run_semantics_member_has_raw_package_and_mcp_rejection_parity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    payload["data_handoffs"][0]["run_semantics"]["unknown_member"] = True
    _write_manifest(manifest_path, payload)
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(tmp_path))

    errors = validate_package(payload)
    assert any("run_semantics" in error and "unknown_member" in error for error in errors)
    with pytest.raises(ValueError, match=r"run_semantics.*unknown_member"):
        load_project_definition(manifest_path)
    mcp_result = validate_manifest(str(manifest_path))
    assert mcp_result.valid is False
    assert any(
        "run_semantics" in error and "unknown_member" in error
        for error in mcp_result.errors
    )


@pytest.mark.parametrize(
    "app_archetype",
    ["passthrough-router", "kafka-integration"],
)
def test_non_crud_run_semantics_fails_all_public_validation_and_generation_paths(
    app_archetype: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    payload["app_archetype"] = app_archetype
    if app_archetype == "kafka-integration":
        payload["kafka_config"] = {"consumer_group": "m5a-s1-rejection"}
        payload["async_routes"] = [
            {
                "name": "rejection-route",
                "pattern": "fire-and-forget",
                "upstream_topic": {
                    "name": "synthetic.input.v1",
                    "system": "SYNTHETIC_SOURCE",
                    "message_schema": "schemas/input.json",
                },
                "downstream_topic": {
                    "name": "synthetic.output.v1",
                    "system": "SYNTHETIC_TARGET",
                    "message_schema": "schemas/output.json",
                },
                "transform_mapping": "mappings/transform.yaml",
            }
        ]
    _write_manifest(manifest_path, payload)
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(tmp_path))

    errors = validate_package(payload)
    assert any(
        "run_semantics" in error and "app_archetype: crud" in error
        for error in errors
    )
    with pytest.raises(ValueError, match=r"run_semantics.*app_archetype: crud"):
        load_project_definition(manifest_path)
    mcp_result = validate_manifest(str(manifest_path))
    assert mcp_result.valid is False
    assert any(
        "run_semantics" in error and "app_archetype: crud" in error
        for error in mcp_result.errors
    )

    output_dir = tmp_path / "generated"
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        exit_code = main(
            [
                "generate",
                "--manifest",
                str(manifest_path),
                "--output",
                str(output_dir),
                "--validate-schema",
            ]
        )
    assert exit_code == 1
    assert "run_semantics" in stderr.getvalue()
    assert "app_archetype: crud" in stderr.getvalue()
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda block: block.clear(),
        lambda block: block.pop("run_id"),
        lambda block: block.pop("restart"),
        lambda block: block.pop("dedup_key"),
        lambda block: block.__setitem__("dedup_key", []),
        lambda block: block.__setitem__("run_id", "execution_derived"),
        lambda block: block.__setitem__("restart", "none"),
        lambda block: block.__setitem__("unknown_member", True),
        lambda block: block.__setitem__("dedup_key", ["widget-id"]),
        lambda block: block.__setitem__("internal_schema_id", "m5a-staging-000"),
    ],
    ids=[
        "empty",
        "missing-run-id",
        "missing-restart",
        "missing-dedup-key",
        "empty-dedup-key",
        "unsupported-run-id",
        "unsupported-restart",
        "unknown-member",
        "invalid-physical-identifier",
        "invalid-internal-schema-id",
    ],
)
def test_malformed_run_semantics_fails_raw_and_package_validation(
    mutation: Callable[[dict[str, Any]], Any],
    tmp_path: Path,
) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    mutation(payload["data_handoffs"][0]["run_semantics"])

    _assert_raw_and_package_reject(manifest_path, payload)


def test_run_semantics_on_non_staging_handoff_fails_raw_and_package_validation(
    tmp_path: Path,
) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    payload["data_handoffs"][0]["type"] = "datastore"

    _assert_raw_and_package_reject(manifest_path, payload, diagnostic="staging-table")


def test_case_normalized_duplicate_dedup_key_fails_raw_and_package_validation(
    tmp_path: Path,
) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    payload["data_handoffs"][0]["run_semantics"]["dedup_key"] = [
        "widget_id",
        "WIDGET_ID",
    ]

    _assert_raw_and_package_reject(manifest_path, payload, diagnostic="case normalization")


def test_duplicate_internal_schema_id_claim_fails_raw_and_package_validation(
    tmp_path: Path,
) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    duplicate = copy.deepcopy(payload["data_handoffs"][0])
    payload["data_handoffs"][0]["run_semantics"]["internal_schema_id"] = "m5a-staging-001"
    duplicate["run_semantics"]["internal_schema_id"] = "m5a-staging-001"
    duplicate["name"] = "widget-staging-copy"
    payload["data_handoffs"].append(duplicate)

    _assert_raw_and_package_reject(manifest_path, payload, diagnostic="already claimed")


def test_translation_carries_validated_run_semantics_as_excluded_metadata(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _copy_fixture(tmp_path)

    metadata = build_metadata_project(manifest_path)
    contract = next(contract for contract in metadata.contracts if contract.name == "widget-staging")
    run_semantics = contract.run_semantics
    assert run_semantics is not None
    assert run_semantics.dedup_key == ["widget_id", "payload_key"]
    assert run_semantics.physical_run_id_column == "run_id"
    assert run_semantics.entity_name == "Widget"
    assert "run_semantics" not in contract.model_dump()
    assert all(
        "run_semantics" not in serialized_contract
        for serialized_contract in metadata.model_dump()["contracts"]
    )


@pytest.mark.parametrize(
    ("ddl_transform", "dedup_key", "mapping_transform", "diagnostic"),
    [
        (
            lambda ddl: ddl.replace("    run_id VARCHAR(64) NOT NULL,\n", ""),
            None,
            None,
            "exactly one recognized physical run-ID column",
        ),
        (
            lambda ddl: ddl.replace(
                "    run_id VARCHAR(64) NOT NULL,\n",
                "    run_id VARCHAR(64) NOT NULL,\n"
                "    eod_run_id VARCHAR(64) NOT NULL,\n",
            ),
            None,
            None,
            "found run_id, eod_run_id",
        ),
        (
            lambda ddl: ddl.replace("run_id VARCHAR(64) NOT NULL", "run_id VARCHAR(64)"),
            None,
            None,
            "run-ID column 'run_id' must be NOT NULL",
        ),
        (
            lambda ddl: ddl.replace("run_id VARCHAR(64) NOT NULL", "run_id INTEGER NOT NULL"),
            None,
            None,
            "must use a string-compatible SQL type",
        ),
        (
            None,
            ["missing_key"],
            None,
            "does not exist",
        ),
        (
            lambda ddl: ddl.replace("widget_id VARCHAR(36) NOT NULL", "widget_id VARCHAR(36)"),
            ["widget_id"],
            None,
            "dedup column 'widget_id' must be NOT NULL",
        ),
        (
            None,
            ["widget_id"],
            lambda mapping: {
                **mapping,
                "field_mappings": [
                    item
                    for item in mapping["field_mappings"]
                    if item["target"] != "widget_id"
                ],
            },
            "must have a canonical-to-handoff mapping",
        ),
        (
            None,
            ["business_date"],
            None,
            r"is operational \(business_date\)",
        ),
    ],
    ids=[
        "missing-run-id",
        "ambiguous-run-id",
        "nullable-run-id",
        "non-string-run-id",
        "missing-dedup-column",
        "nullable-dedup-column",
        "unmapped-dedup-column",
        "operational-dedup-column",
    ],
)
def test_translation_rejects_invalid_staging_contract_details(
    ddl_transform: Callable[[str], str] | None,
    dedup_key: list[str] | None,
    mapping_transform: Callable[[dict[str, Any]], dict[str, Any]] | None,
    diagnostic: str,
    tmp_path: Path,
) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    if dedup_key is not None:
        payload["data_handoffs"][0]["run_semantics"]["dedup_key"] = dedup_key
        _write_manifest(manifest_path, payload)
    if ddl_transform is not None:
        ddl_path = manifest_path.parent / "widget-staging.sql"
        ddl_path.write_text(ddl_transform(ddl_path.read_text(encoding="utf-8")), encoding="utf-8")
    if mapping_transform is not None:
        mapping_path = manifest_path.parent / "widget-staging-mapping.yaml"
        mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
        mapping_path.write_text(
            yaml.safe_dump(mapping_transform(mapping), sort_keys=False),
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match=diagnostic):
        build_metadata_project(manifest_path)


@pytest.mark.parametrize(
    "numeric_handoff_first",
    [True, False],
    ids=["numeric-before-run-semantics", "numeric-after-run-semantics"],
)
def test_translation_rejects_dedup_type_conflict_independent_of_handoff_order(
    numeric_handoff_first: bool,
    tmp_path: Path,
) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    numeric_ddl = manifest_path.parent / "widget-numeric-staging.sql"
    numeric_ddl.write_text(
        "CREATE TABLE widget_numeric_staging (\n"
        "    staging_row_id VARCHAR(36) PRIMARY KEY,\n"
        "    widget_id INTEGER NOT NULL\n"
        ");\n",
        encoding="utf-8",
    )
    numeric_mapping = manifest_path.parent / "widget-numeric-staging-mapping.yaml"
    numeric_mapping.write_text(
        "table: widget_numeric_staging\n"
        "entity: Widget\n"
        "field_mappings:\n"
        "  - source: Widget.widgetId\n"
        "    target: widget_id\n",
        encoding="utf-8",
    )
    numeric_handoff = {
        "name": "widget-numeric-staging",
        "type": "staging-table",
        "spec": numeric_ddl.name,
        "mapping": numeric_mapping.name,
    }
    if numeric_handoff_first:
        payload["data_handoffs"].insert(0, numeric_handoff)
    else:
        payload["data_handoffs"].append(numeric_handoff)
    _write_manifest(manifest_path, payload)

    with pytest.raises(ValueError, match="type compatibility error"):
        build_metadata_project(manifest_path)


def _add_downstream_file(
    manifest_path: Path,
    payload: dict[str, Any],
    *,
    entity_name: str,
    field_name: str,
) -> None:
    layout_path = manifest_path.parent / "eod-layout.yaml"
    layout_path.write_text(
        "format: csv\n"
        "encoding: UTF-8\n"
        "delimiter: ','\n"
        "has_header_row: true\n"
        "record_types:\n"
        "  data:\n"
        "    fields:\n"
        f"      - name: {field_name}\n"
        "        column: 1\n"
        "        type: string\n"
        "        required: true\n",
        encoding="utf-8",
    )
    mapping_path = manifest_path.parent / "eod-mapping.yaml"
    canonical_field = "widgetId" if entity_name == "Widget" else "entryId"
    mapping_path.write_text(
        f"entity: {entity_name}\n"
        "field_mappings:\n"
        f"  - source: {entity_name}.{canonical_field}\n"
        f"    target: {field_name}\n",
        encoding="utf-8",
    )
    payload["downstream_interfaces"] = [
        {
            "name": "eod-file",
            "system": "SYNTHETIC_OUTPUT",
            "type": "file-csv",
            "spec": layout_path.name,
            "mapping": mapping_path.name,
        }
    ]
    _write_manifest(manifest_path, payload)


def test_same_entity_mixed_staging_and_file_output_fails_ac10(tmp_path: Path) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    _add_downstream_file(
        manifest_path,
        payload,
        entity_name="Widget",
        field_name="widget_id",
    )

    with pytest.raises(ValueError, match=r"Widget.*shares its EOD job.*eod-file"):
        build_metadata_project(manifest_path)


def test_different_entity_file_output_does_not_trigger_ac10(tmp_path: Path) -> None:
    manifest_path, payload = _copy_fixture(tmp_path)
    _add_downstream_file(
        manifest_path,
        payload,
        entity_name="Entry",
        field_name="entry_id",
    )

    metadata = build_metadata_project(manifest_path)
    assert {entity.name for entity in metadata.entities} == {"Entry", "Widget"}
