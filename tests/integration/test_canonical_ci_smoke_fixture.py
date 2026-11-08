from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from appbuilder.generation import generate_application
from appbuilder.metadata import HttpMethod, ResponseShape, build_metadata_project

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "examples/input-projects/generated-app-ci-smoke"
EXPECTED_FIXTURE_PATHS = {
    "README.md",
    "app-definition.yaml",
    "contracts/ci-smoke-openapi.yaml",
    "rules/ci-smoke-rules.yaml",
    "upstream/entry-mapping.yaml",
    "upstream/record-mapping.yaml",
    "upstream/sample-create-entry-request.json",
    "upstream/sample-create-entry-response.json",
    "upstream/sample-create-record-request.json",
    "upstream/sample-create-record-response.json",
}


def _load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _assert_fixture_shape(fixture_root: Path) -> None:
    actual_paths = {
        path.relative_to(fixture_root).as_posix()
        for path in fixture_root.rglob("*")
        if path.is_file()
    }
    assert actual_paths == EXPECTED_FIXTURE_PATHS

    manifest = _load_yaml(fixture_root / "app-definition.yaml")
    assert manifest["app_name"] == "Generated App CI Smoke"
    assert manifest["bounded_context"] == "ci_smoke"
    assert manifest["schema_version"] == "2.0"
    assert manifest["app_archetype"] == "crud"
    assert manifest["target_profile"] == "springboot-legacy-compatible"
    assert "data_handoffs" not in manifest
    assert manifest["rules"] == ["rules/ci-smoke-rules.yaml"]
    assert manifest["upstream_interfaces"] == [
        {
            "name": "record-api",
            "system": "CiSmokeSource",
            "type": "rest-json",
            "version": "1.0",
            "spec": "contracts/ci-smoke-openapi.yaml",
            "mapping": "upstream/record-mapping.yaml",
            "operations": [
                {
                    "name": "createRecord",
                    "request_sample": "upstream/sample-create-record-request.json",
                    "response_sample": "upstream/sample-create-record-response.json",
                }
            ],
        },
        {
            "name": "entry-api",
            "system": "CiSmokeSource",
            "type": "rest-json",
            "version": "1.0",
            "spec": "contracts/ci-smoke-openapi.yaml",
            "mapping": "upstream/entry-mapping.yaml",
            "operations": [
                {
                    "name": "createEntry",
                    "request_sample": "upstream/sample-create-entry-request.json",
                    "response_sample": "upstream/sample-create-entry-response.json",
                }
            ],
        },
    ]

    assert _load_yaml(fixture_root / "upstream/record-mapping.yaml") == {
        "interface": "record-api",
        "entity": "Record",
        "operations": [
            {
                "name": "createRecord",
                "request_mappings": [
                    {"source": "label", "target": "Record.label"},
                    {"source": "state", "target": "Record.state"},
                ],
                "response_mappings": [
                    {"source": "recordId", "target": "Record.recordId"},
                    {"source": "label", "target": "Record.label"},
                    {"source": "state", "target": "Record.state"},
                ],
            }
        ],
    }
    assert _load_yaml(fixture_root / "upstream/entry-mapping.yaml") == {
        "interface": "entry-api",
        "entity": "Entry",
        "operations": [
            {
                "name": "createEntry",
                "request_mappings": [
                    {"source": "note", "target": "Entry.note"},
                ],
                "response_mappings": [
                    {"source": "entryId", "target": "Entry.entryId"},
                    {"source": "note", "target": "Entry.note"},
                ],
            }
        ],
    }
    assert _load_yaml(fixture_root / "rules/ci-smoke-rules.yaml") == {
        "entity": "Record",
        "rules": [
            {
                "field": "state",
                "type": "allowed-values",
                "values": ["NEW", "ACTIVE", "CLOSED"],
            },
            {"field": "state", "type": "default", "value": "NEW"},
        ],
    }
    assert _load_json(fixture_root / "upstream/sample-create-record-request.json") == {
        "label": "First record",
        "state": "NEW",
    }
    assert _load_json(fixture_root / "upstream/sample-create-record-response.json") == {
        "recordId": "REC-0000001",
        "label": "First record",
        "state": "NEW",
    }
    assert _load_json(fixture_root / "upstream/sample-create-entry-request.json") == {
        "note": "First entry"
    }
    assert _load_json(fixture_root / "upstream/sample-create-entry-response.json") == {
        "entryId": "ENT-0000001",
        "note": "First entry",
    }

    openapi = _load_yaml(fixture_root / "contracts/ci-smoke-openapi.yaml")
    assert openapi["openapi"] == "3.0.1"
    assert set(openapi["paths"]) == {"/api/v1/records", "/api/v1/entries"}
    assert set(openapi["paths"]["/api/v1/records"]) == {"post"}
    assert set(openapi["paths"]["/api/v1/entries"]) == {"post"}
    record_post = openapi["paths"]["/api/v1/records"]["post"]
    entry_post = openapi["paths"]["/api/v1/entries"]["post"]
    assert record_post["operationId"] == "createRecord"
    assert entry_post["operationId"] == "createEntry"
    assert set(record_post["responses"]) == {"201"}
    assert set(entry_post["responses"]) == {"201"}


def test_canonical_ci_smoke_fixture_contract_and_generation(tmp_path: Path) -> None:
    _assert_fixture_shape(FIXTURE_ROOT)

    metadata = build_metadata_project(FIXTURE_ROOT / "app-definition.yaml")
    assert [entity.name for entity in metadata.entities] == ["Record", "Entry"]
    assert [[field.name for field in entity.fields] for entity in metadata.entities] == [
        ["label", "state", "recordId"],
        ["note", "entryId"],
    ]
    assert [
        [field.name for field in entity.fields if field.required]
        for entity in metadata.entities
    ] == [["label"], ["note"]]
    assert [
        [field.name for field in entity.fields if field.is_id and field.server_generated_id]
        for entity in metadata.entities
    ] == [["recordId"], ["entryId"]]

    assert [
        (
            operation.name,
            operation.http_method,
            operation.path,
            operation.has_request_body,
            operation.response_shape,
        )
        for operation in metadata.operations
    ] == [
        ("createRecord", HttpMethod.POST, "/api/v1/records", True, ResponseShape.CREATED),
        ("createEntry", HttpMethod.POST, "/api/v1/entries", True, ResponseShape.CREATED),
    ]

    output_dir = tmp_path / "generated-app"
    report = generate_application(
        metadata,
        output_dir,
        source_manifest="app-definition.yaml",
        generation_run_id="canonical-ci-smoke",
    )
    assert report.warnings == []
    assert report.harness_report is not None
    assert report.harness_report.passed

    service = (
        output_dir
        / "src/main/java/com/appbuilder/ci_smoke/service/RecordServiceBase.java"
    ).read_text(encoding="utf-8")
    assert (
        'private static final Set<String> ALLOWED_STATE_VALUES = Set.of("NEW", "ACTIVE", "CLOSED");'
        in service
    )
    assert (
        "record.getState() != null && !ALLOWED_STATE_VALUES.contains(record.getState())"
        in service
    )
    assert 'record.setState("NEW");' in service
    assert "        applyBusinessRules(record);" in service

    for entity_name in ("Record", "Entry"):
        controller = (
            output_dir
            / f"src/main/java/com/appbuilder/ci_smoke/adapter/inbound/{entity_name}Controller.java"
        ).read_text(encoding="utf-8")
        assert "ResponseEntity.status(HttpStatus.CREATED).body(created)" in controller


def test_canonical_ci_smoke_fixture_guard_rejects_unexpected_file(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "fixture"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    (fixture_copy / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(AssertionError):
        _assert_fixture_shape(fixture_copy)


def test_canonical_ci_smoke_fixture_guard_rejects_manifest_drift(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "fixture"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    manifest_path = fixture_copy / "app-definition.yaml"
    manifest = _load_yaml(manifest_path)
    manifest["app_name"] = "Drifted App"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    with pytest.raises(AssertionError):
        _assert_fixture_shape(fixture_copy)
