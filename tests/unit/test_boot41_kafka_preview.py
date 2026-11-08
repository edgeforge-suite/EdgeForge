"""Kafka preview selection, API types and meaningful wire-comparator controls."""

import copy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from appbuilder.contracts import load_project_definition
from appbuilder.generation import generate_application
from appbuilder.mcp.tools.generation import _ALLOWED_ROOTS_ENV, generate_app
from appbuilder.metadata.kafka_translation import translate_kafka_project
from scripts.smoke.boot41_kafka_preview_proof import (
    BASES,
    DIAGNOSTICS,
    _counts,
    compare_wire,
    prepare_input,
)


@pytest.mark.parametrize("base", BASES)
@pytest.mark.parametrize(
    "kind",
    [
        "kafka-integration",
        "kafka-request-reply",
        "kafka-retry-dlq",
        "kafka-multi-route",
        "kafka-router-contract",
    ],
)
def test_preview_kafka_types_and_dependency_selection(tmp_path, base, kind):
    fixture = Path("tests/fixtures") / kind
    definition = load_project_definition(fixture / "manifest.yaml")
    definition.target_profile = base
    metadata = translate_kafka_project(definition, fixture)
    output = tmp_path / "output"
    generate_application(metadata, output, generation_run_id="stable")
    pom = (output / "pom.xml").read_text()
    assert "<version>4.1.1</version>" in pom
    assert "spring-boot-starter-kafka" in pom
    assert "spring-boot-starter-jackson" in pom
    assert "spring-boot-starter-webmvc" in pom
    assert "spring-boot-starter-jackson2" not in pom
    assert "spring-boot-starter-data-jpa" not in pom
    assert "spring-boot-starter-batch" not in pom
    java = "\n".join(path.read_text() for path in output.rglob("*.java"))
    assert "com.fasterxml.jackson.databind" not in java
    assert "JsonProcessingException" not in java
    assert "JacksonJsonSerializer" in java
    assert "DateTimeFeature.WRITE_DATES_AS_TIMESTAMPS" in java
    assert "tools.jackson.databind" in java
    assert ("json-schema-validator" in pom) == bool(metadata.router_routes)
    if metadata.router_routes:
        assert "<version>3.0.6</version>" in pom
        assert "SchemaRegistry.withDefaultDialect" in java
        assert ".typeLoose(false).formatAssertionsEnabled(true)" in java
        assert "SchemaLoader.builder().build()" in java
        assert "fetchRemoteResources" not in java


@pytest.mark.parametrize("base", BASES)
def test_cli_and_mcp_admit_preview(tmp_path, monkeypatch, base):
    fixture = tmp_path / "fixture"
    shutil.copytree("tests/fixtures/kafka-router-contract", fixture)
    manifest = fixture / "manifest.yaml"
    data = yaml.safe_load(manifest.read_text())
    data["target_profile"] = base
    manifest.write_text(yaml.safe_dump(data))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "appbuilder.cli",
            "generate",
            "--manifest",
            str(manifest),
            "--output",
            str(tmp_path / "cli"),
            "--validate-schema",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))
    response = generate_app(str(manifest), str(tmp_path / "mcp"))
    assert response.success, response.errors


def test_proof_input_is_schema_valid(tmp_path):
    fixture = prepare_input(tmp_path)
    definition = load_project_definition(fixture / "manifest.yaml")
    metadata = translate_kafka_project(definition, fixture)
    assert len(metadata.routes) == 4
    assert len(metadata.router_routes[0].targets) == 2


def _wire():
    return [
        {
            "case": "router-reply",
            "topic": "reply",
            "key": "roundtrip",
            "headers_base64": {"X-Correlation-ID": ["cm91bmR0cmlw"]},
            "payload": {
                "amount": 12.34,
                "approved": True,
                "status": "APPROVED",
                "errorCode": "NONE",
            },
        }
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("topic", "wrong"),
        ("key", "wrong"),
        ("correlation", "d3Jvbmc="),
        ("amount", "12.34"),
        ("approved", 1),
        ("errorCode", "WRONG"),
    ],
)
def test_wire_comparator_rejects_contract_mutations(field, value):
    control = _wire()
    changed = copy.deepcopy(control)
    if field == "correlation":
        changed[0]["headers_base64"]["X-Correlation-ID"] = [value]
    elif field in {"topic", "key"}:
        changed[0][field] = value
    else:
        changed[0]["payload"][field] = value
    with pytest.raises(AssertionError, match="contract mismatch"):
        compare_wire(control, changed)


def test_wire_comparator_preserves_all_other_fields_and_member_order():
    control = _wire()
    assert compare_wire(control, copy.deepcopy(control)) == []
    changed = copy.deepcopy(control)
    changed[0]["payload"]["extra"] = None
    with pytest.raises(AssertionError):
        compare_wire(control, changed)


def test_only_exact_reported_diagnostic_difference_is_allowed():
    schema, old, new = DIAGNOSTICS["v1"]
    prefix = f"V1 validation failed for schema router/schemas/{schema}.json: "
    control = [
        {
            "case": "v1",
            "payload": {
                "errorReason": prefix + "[" + old + "]",
                "timestamp": "2026-09-30T20:00:00Z",
            },
        }
    ]
    preview = copy.deepcopy(control)
    preview[0]["payload"]["errorReason"] = prefix + "[" + new + "]"
    assert len(compare_wire(control, preview)) == 1
    preview[0]["payload"]["errorReason"] = "unexpected loss of detail"
    with pytest.raises(AssertionError, match="diagnostic"):
        compare_wire(control, preview)


@pytest.mark.parametrize("tests,skipped,failures", [(0, 0, 0), (1, 1, 0), (1, 0, 1)])
def test_proof_rejects_missing_skipped_and_failed_tests(tmp_path, tests, skipped, failures):
    reports = tmp_path / "target/surefire-reports"
    reports.mkdir(parents=True)
    (reports / "TEST-proof.xml").write_text(
        f'<testsuite tests="{tests}" skipped="{skipped}" failures="{failures}" errors="0"/>'
    )
    with pytest.raises(AssertionError, match="Incomplete"):
        _counts(tmp_path, 1)
