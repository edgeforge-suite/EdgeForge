"""Bounded preview selection and default-output preservation checks."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from email.message import Message
from pathlib import Path

import pytest
import yaml

from appbuilder.generation import generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.engine import require_supported_preview_input
from appbuilder.mapping import MappingDirection
from appbuilder.mcp.tools.catalog import list_target_profiles
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.models import ContractMetadata
from appbuilder.target_profiles.catalog import TARGET_PROFILES
from scripts.smoke.boot41_preview_proof import (
    _capture,
    _close_postgres,
    _content_type,
    _created_id,
    _normalize_json,
    _parse_xml,
    _Postgres,
    _require_resource_id,
    _require_xml_resource_id,
    _response_headers,
    _xml_value,
)

_PAIRS = (
    ("springboot-legacy-compatible", "springboot-legacy-compatible", "17", "h2"),
    (
        "springboot-enterprise-postgres-java17",
        "springboot-enterprise-postgres-java17",
        "17",
        "postgresql",
    ),
    (
        "springboot-standard-enterprise",
        "springboot-standard-enterprise",
        "21",
        "postgresql",
    ),
)
_FIXTURES = {
    "crud": "examples/input-projects/generated-app-ci-smoke/app-definition.yaml",
    "soap": "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml",
    "passthrough": "examples/input-projects/country-router/app-definition.yaml",
    "batch": "examples/input-projects/obie-wire-transfer/app-definition.yaml",
    "kafka": "tests/fixtures/kafka-integration/manifest.yaml",
    "kafka-router": "tests/fixtures/kafka-router-contract/manifest.yaml",
}


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.mark.parametrize("base,preview,java,database", _PAIRS)
def test_ordinary_profiles_have_current_runtime_settings(
    base: str, preview: str, java: str, database: str
) -> None:
    shipped = TARGET_PROFILES[base]
    selected = TARGET_PROFILES[preview]
    assert shipped.spring_boot_baseline == "4.1.1"
    assert shipped.experimental_boot41
    assert selected.spring_boot_baseline == "4.1.1"
    assert selected.experimental_boot41
    assert selected.emit_spring_batch
    assert selected.java_baseline == java
    assert selected.runtime_database_dependency == database
    assert selected.emit_flyway
    assert not selected.emit_security
    assert selected.emit_audit == (database == "postgresql")
    assert selected.emit_test_console == (database == "h2")


@pytest.mark.parametrize("profile", tuple(TARGET_PROFILES))
@pytest.mark.parametrize("shape", ("crud", "soap", "soap-out", "passthrough", "batch", "ordinary", "file", "m5a", "mixed", "kafka", "kafka-router", "kafka-mixed"))
def test_current_policy_generation_is_deterministic(tmp_path, shape, profile):
    from scripts.smoke.boot41_kafka_preservation import equivalence_case

    assert equivalence_case(tmp_path, shape, profile)["deterministic"]


@pytest.mark.parametrize("kind", ["crud", "soap", "passthrough"])
@pytest.mark.parametrize("_base,preview,_java,_database", _PAIRS)
def test_preview_generation_is_jobless_and_deterministic(
    tmp_path: Path, kind: str, _base: str, preview: str, _java: str, _database: str
) -> None:
    fixture = _FIXTURES[kind]
    metadata = build_metadata_project(fixture)
    metadata.target_profile = preview
    first = tmp_path / "first"
    second = tmp_path / "second"
    for output in (first, second):
        generate_application(
            metadata, output, source_manifest=fixture, generation_run_id="current-policy"
        )
    assert _tree_digest(first) == _tree_digest(second)
    pom = (first / "pom.xml").read_text(encoding="utf-8")
    assert "<version>4.1.1</version>" in pom
    assert "spring-boot-starter-webmvc" in pom
    assert "spring-boot-starter-jackson" in pom
    assert "spring-boot-starter-batch" not in pom
    assert "spring-boot-starter-jackson2" not in pom
    assert not list(first.rglob("*BatchJob.java"))
    assert not any(
        "org.springframework.batch" in path.read_text(encoding="utf-8")
        for path in first.rglob("*.java")
    )
    assert "Spring Boot 4.1 Fresh Applications" in (first / "README.md").read_text()
    if kind == "passthrough":
        assert "spring-boot-starter-restclient" in pom
    else:
        assert "spring-boot-starter-flyway" in pom
        assert "spring-boot-starter-data-jpa" in pom
        assert "  batch:" not in (first / "src/main/resources/application.yaml").read_text()
        if kind == "soap":
            assert "spring-boot-starter-webservices" in pom
    if "postgres" in preview and kind != "passthrough":
        assert "flyway-database-postgresql" in pom


@pytest.mark.parametrize(
    "fixture",
    [
        _FIXTURES["kafka"],
        _FIXTURES["kafka-router"],
    ],
)
def test_preview_admits_supported_kafka_without_overwriting_unrelated_output(
    tmp_path: Path, fixture: str
) -> None:
    metadata = build_metadata_project(fixture)
    if hasattr(metadata, "target_profile_name"):
        metadata.target_profile_name = _PAIRS[0][1]
    else:
        metadata.target_profile = _PAIRS[0][1]
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "adopter.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    generate_application(metadata, output)
    assert (output / "pom.xml").exists()
    assert sentinel.read_text(encoding="utf-8") == "untouched"


@pytest.mark.parametrize("handoff", ["staging", "file"])
def test_preview_admits_non_m5a_job_bearing_handoff(
    tmp_path: Path, handoff: str
) -> None:
    metadata = build_metadata_project(_FIXTURES["batch"])
    metadata.target_profile = _PAIRS[0][1]
    retained_direction = (
        MappingDirection.CANONICAL_TO_HANDOFF
        if handoff == "staging"
        else MappingDirection.CANONICAL_TO_DOWNSTREAM
    )
    metadata.mappings = [
        mapping for mapping in metadata.mappings
        if mapping.direction != MappingDirection.CANONICAL_TO_HANDOFF
        and mapping.direction != MappingDirection.CANONICAL_TO_DOWNSTREAM
        or mapping.direction == retained_direction
    ]
    output = tmp_path / "not-created"
    generate_application(metadata, output)
    assert "spring-boot-starter-batch-jdbc" in (output / "pom.xml").read_text()
    assert list(output.rglob("*BatchJob.java"))


def test_metadata_only_file_declaration_does_not_trigger_job_refusal() -> None:
    metadata = build_metadata_project(_FIXTURES["crud"])
    metadata.target_profile = _PAIRS[0][1]
    metadata.contracts.append(
        ContractMetadata(name="not-mapped", type="file-csv", source="metadata-only")
    )
    require_supported_preview_input(metadata)


def test_cli_admits_inferred_file_job(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    shutil.copytree(Path(_FIXTURES["crud"]).parent, fixture)
    manifest = fixture / "app-definition.yaml"
    contents = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    contents["target_profile"] = _PAIRS[0][1]
    (fixture / "downstream").mkdir()
    (fixture / "downstream/record-csv-layout.yaml").write_text(yaml.safe_dump({
        "format": "csv", "record_types": {"data": {"fields": [
            {"name": "record_id", "column": 1, "type": "string", "required": True},
        ]}},
    }), encoding="utf-8")
    contents["downstream_interfaces"] = [{
        "name": "record-file-note", "system": "CiSmokeSink", "type": "file-csv",
        "spec": "downstream/record-csv-layout.yaml",
    }]
    manifest.write_text(yaml.safe_dump(contents, sort_keys=False), encoding="utf-8")
    output = tmp_path / "output"
    result = subprocess.run(
        [sys.executable, "-m", "appbuilder.cli", "generate", "--manifest", str(manifest),
         "--output", str(output), "--validate-schema"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert list(output.rglob("*BatchJob.java"))


def test_cli_accepts_metadata_only_identity_declaration_end_to_end(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    shutil.copytree(Path(_FIXTURES["crud"]).parent, fixture)
    manifest = fixture / "app-definition.yaml"
    contents = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    contents["target_profile"] = _PAIRS[0][1]
    contents["identity_roles"] = [{
        "entity": "Record", "field": "recordId", "role": "business_key",
        "mode": "metadata_only",
    }]
    manifest.write_text(yaml.safe_dump(contents, sort_keys=False), encoding="utf-8")
    output = tmp_path / "output"
    result = subprocess.run(
        [sys.executable, "-m", "appbuilder.cli", "generate", "--manifest", str(manifest),
         "--output", str(output), "--validate-schema"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "<version>4.1.1</version>" in (output / "pom.xml").read_text()
    assert not list(output.rglob("*BatchJob.java"))


def test_apply_rejects_unsupported_preview_before_existing_package_changes(
    tmp_path: Path,
) -> None:
    from scripts.smoke.boot41_batch_cases import case_metadata

    metadata = case_metadata("mixed", _PAIRS[0][1])
    for mapping in metadata.mappings:
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM:
            mapping.source_path = "Widget.payloadKey"
    package = tmp_path / "package"
    package.mkdir()
    (package / "adopter.txt").write_text("unchanged", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot share an EOD file job"):
        apply_change_plan(
            metadata=metadata, package_dir=package, approved_plan_hash="irrelevant"
        )
    assert [path.name for path in package.iterdir()] == ["adopter.txt"]


def test_cli_selects_preview_profile_without_new_manifest_field(tmp_path: Path) -> None:
    source = Path(_FIXTURES["crud"]).parent
    fixture = tmp_path / "fixture"
    shutil.copytree(source, fixture)
    manifest = fixture / "app-definition.yaml"
    contents = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    contents["target_profile"] = _PAIRS[0][1]
    manifest.write_text(yaml.safe_dump(contents, sort_keys=False), encoding="utf-8")
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable, "-m", "appbuilder.cli", "generate",
            "--manifest", str(manifest), "--output", str(output), "--validate-schema",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "<version>4.1.1</version>" in (output / "pom.xml").read_text()


def test_cli_admits_preview_kafka(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    shutil.copytree(Path(_FIXTURES["kafka"]).parent, fixture)
    manifest = fixture / "manifest.yaml"
    contents = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    contents["target_profile"] = _PAIRS[0][1]
    manifest.write_text(yaml.safe_dump(contents, sort_keys=False), encoding="utf-8")
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable, "-m", "appbuilder.cli", "generate",
            "--manifest", str(manifest), "--output", str(output), "--validate-schema",
        ],
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "<version>4.1.1</version>" in (output / "pom.xml").read_text()


def test_wire_normalization_only_discards_declared_volatility() -> None:
    value = {
        "customerId": "generated-value",
        "id": "keep-this-other-id",
        "timestamp": "2026-09-27T05:00:00Z",
        "amount": 42.5,
        "optional": None,
    }
    normalized = _normalize_json(
        value, generated_id="generated-value", id_field="customerId", error_timestamp=True
    )
    assert normalized == {
        "customerId": "<generated-id>",
        "id": ("str", "keep-this-other-id"),
        "timestamp": "<request-timestamp:iso-utc>",
        "amount": ("float", 42.5),
        "optional": ("NoneType", None),
    }
    with pytest.raises(AssertionError, match="timestamp"):
        _normalize_json({"timestamp": "not-a-timestamp"}, error_timestamp=True)
    assert _normalize_json({"timestamp": "not-a-timestamp"}) == {
        "timestamp": ("str", "not-a-timestamp")
    }


def test_wire_ids_reject_wrong_type_format_and_resource() -> None:
    generated = "fc256fae-142f-48c8-9b0c-bf56d24696c4"
    other = "c5b15a51-100f-4cbe-bc4d-83e449ddcbce"
    response = (201, {}, json.dumps({"recordId": generated}).encode())
    assert _created_id(response, "recordId") == generated
    for value in (17, {"value": generated}, "not-a-uuid", other.upper()):
        with pytest.raises(AssertionError, match="UUIDv4"):
            _created_id((201, {}, json.dumps({"recordId": value}).encode()), "recordId")
    _require_resource_id(json.dumps({"recordId": generated}).encode(), "recordId", generated)
    _require_resource_id(json.dumps([{"recordId": generated}]).encode(), "recordId", generated, listed=True)
    for value in (17, other, {"value": generated}):
        with pytest.raises(AssertionError, match="created recordId"):
            _require_resource_id(json.dumps({"recordId": value}).encode(), "recordId", generated)
    for value in (17, other, {"value": generated}):
        assert _normalize_json(
            {"recordId": value}, generated_id=generated, id_field="recordId"
        ) != {"recordId": "<generated-id>"}


def test_wire_json_policy_is_order_insensitive_but_preserves_values() -> None:
    left = {"recordId": "same", "label": "Ada", "state": "NEW"}
    right = {"state": "NEW", "recordId": "same", "label": "Ada"}
    assert _normalize_json(left) == _normalize_json(right)
    assert _normalize_json(left) != _normalize_json({**right, "state": "CLOSED"})


def test_error_timestamp_only_normalizes_top_level_error_field() -> None:
    headers = {"content-type": "application/json", **{
        "x-content-type-options": "nosniff", "x-frame-options": "DENY",
        "referrer-policy": "no-referrer", "content-security-policy": "frame-ancestors 'none'",
    }}
    good = {"timestamp": "2026-09-27T05:00:00Z", "detail": {"timestamp": "important"}}
    captured = _capture((400, headers, json.dumps(good).encode()), error_timestamp=True)
    assert captured[2]["timestamp"] == "<request-timestamp:iso-utc>"
    assert captured[2]["detail"]["timestamp"] == ("str", "important")
    for value in (17, "2026-09-27 05:00:00Z", "2026-09-27T05:00:00+00:00"):
        with pytest.raises(AssertionError, match="timestamp"):
            _capture((400, headers, json.dumps({"timestamp": value}).encode()), error_timestamp=True)
    assert _capture((200, headers, json.dumps(good).encode()), error_timestamp=True)[2]["timestamp"] == (
        "str", "2026-09-27T05:00:00Z"
    )


def test_wire_xml_normalization_retains_namespace_and_other_values() -> None:
    value = ET.fromstring(
        '<x:Root xmlns:x="urn:one"><x:Id>generated</x:Id>'
        '<x:Amount>42.50</x:Amount></x:Root>'
    )
    assert _xml_value(value, generated_id="generated") == (
        "{urn:one}Root", (), "",
        (
            ("{urn:one}Id", (), "generated", (), ""),
            ("{urn:one}Amount", (), "42.50", (), ""),
        ), "",
    )


def test_wire_xml_preserves_meaningful_text_tails_and_fields() -> None:
    original = _parse_xml(b"<r><n>Ada</n>after<n>Grace</n></r>")
    assert original != _parse_xml(b"<r><n> Ada </n>after<n>Grace</n></r>")
    assert original != _parse_xml(b"<r><n>Ada</n>changed<n>Grace</n></r>")
    assert original != _parse_xml(b"<r><n>Ada</n>after</r>")
    assert _parse_xml(b"<r>\n  <n>Ada</n>\n</r>") == _parse_xml(b"<r><n>Ada</n></r>")


def test_wire_soap_resource_id_must_match_created_resource() -> None:
    expected = "fc256fae-142f-48c8-9b0c-bf56d24696c4"
    correct = f"<r><customerId>{expected}</customerId></r>".encode()
    _require_xml_resource_id(correct, "customerId", expected)
    for body in (
        b"<r/>", b"<r><customerId>wrong</customerId></r>",
        correct.replace(b"</r>", f"<customerId>{expected}</customerId></r>".encode()),
    ):
        with pytest.raises(AssertionError, match="created customerId"):
            _require_xml_resource_id(body, "customerId", expected)


def test_wire_soap_fault_qname_resolves_namespace_not_prefix() -> None:
    left = b'<s:Fault xmlns:s="urn:soap"><faultcode>s:Server</faultcode></s:Fault>'
    same = b'<x:Fault xmlns:x="urn:soap"><faultcode>x:Server</faultcode></x:Fault>'
    rebound = b'<s:Fault xmlns:s="urn:soap"><faultcode xmlns:s="urn:wrong">s:Server</faultcode></s:Fault>'
    changed = b'<s:Fault xmlns:s="urn:soap"><faultcode>s:Client</faultcode></s:Fault>'
    assert _parse_xml(left) == _parse_xml(same)
    assert _parse_xml(left) != _parse_xml(rebound)
    assert _parse_xml(left) != _parse_xml(changed)
    with pytest.raises(AssertionError, match="namespace"):
        _parse_xml(b"<Fault><faultcode>s:Server</faultcode></Fault>")


def test_content_type_keeps_parameters_with_lexical_normalization() -> None:
    assert _content_type("text/XML; Charset=UTF-8") == _content_type("text/xml;charset=utf-8")
    assert _content_type("text/xml;charset=utf-8") != _content_type("text/xml;charset=iso-8859-1")
    assert _content_type("application/json") != _content_type("application/json;charset=utf-8")


def test_postgres_cleanup_attempts_every_owned_database(monkeypatch: pytest.MonkeyPatch) -> None:
    postgres = _Postgres.__new__(_Postgres)
    postgres.databases = ["boot41_one", "boot41_two", "boot41_three"]
    attempted = []

    def fail_two(sql: str, *, database: str) -> str:
        attempted.append(sql)
        if "two" in sql or "three" in sql:
            raise RuntimeError("drop failed")
        return ""

    monkeypatch.setattr(postgres, "_psql", fail_two)
    with pytest.raises(AssertionError, match="boot41_two"):
        postgres.close()
    assert attempted == [
        "DROP DATABASE boot41_three", "DROP DATABASE boot41_two", "DROP DATABASE boot41_one"
    ]


def test_postgres_cleanup_does_not_replace_primary_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    postgres = _Postgres.__new__(_Postgres)

    def failed_close() -> None:
        raise AssertionError("owned database drop failed")

    monkeypatch.setattr(postgres, "close", failed_close)
    with pytest.raises(RuntimeError, match="original proof failure"):
        try:
            raise RuntimeError("original proof failure")
        finally:
            _close_postgres(postgres)
    assert "owned database drop failed" in capsys.readouterr().err


def test_ordinary_profiles_describe_fresh_baseline() -> None:
    summaries = {item.name: item.description for item in list_target_profiles()}
    for _base, preview, _java, _database in _PAIRS:
        assert "Spring Boot 4.1.1" in summaries[preview]
        assert "fresh" in summaries[preview]


def test_wire_headers_reject_duplicate_security_values() -> None:
    headers = Message()
    for name, value in (
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Content-Security-Policy", "frame-ancestors 'none'"),
    ):
        headers.add_header(name, value)
    assert _response_headers(headers)["x-frame-options"] == "DENY"
    headers.add_header("X-Frame-Options", "DENY")
    with pytest.raises(AssertionError, match="duplicate"):
        _response_headers(headers)
