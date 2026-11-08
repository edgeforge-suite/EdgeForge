"""Pinned production-export contracts run without Studio or network access."""
import hashlib
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from appbuilder.generation import generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.change_plan import build_change_plan
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.models import CanonicalField, CanonicalFieldType
from tests.unit.test_write_contract import SHIPPED_PROFILES, snapshot

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/studio-domain-sample-contracts"
PACKS = ("fs-account-servicing", "hc-authorization-status", "ins-claims-intake-router")


def test_pinned_studio_export_files_match_inventory():
    listed = set()
    for line in (FIXTURES / "source-files.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        listed.add(name.removeprefix("./"))
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest
    assert listed == {str(path.relative_to(FIXTURES)) for pack in PACKS
                      for path in (FIXTURES / pack).rglob("*") if path.is_file()}


def claims_input(tmp_path):
    root = tmp_path / "input"
    shutil.copytree(FIXTURES / PACKS[2], root)
    return root / "app-definition.yaml", root / "upstream/claim-intake-api-spec.yaml"


@pytest.mark.parametrize("pack", PACKS)
@pytest.mark.parametrize("profile", SHIPPED_PROFILES)
def test_three_studio_pack_contracts_generate_without_remote_fetch(tmp_path, pack, profile):
    with patch("socket.socket.connect", side_effect=AssertionError("remote fetching forbidden")):
        metadata = build_metadata_project(FIXTURES / pack / "app-definition.yaml")
        metadata.target_profile = profile
        output = tmp_path / "app"
        report = generate_application(metadata, output, generation_run_id="studio-contract-control")
        assert report.warnings == []
        before = {name: value[0] for name, value in snapshot(output).items()}
        generate_application(metadata, output, generation_run_id="studio-contract-control")
        assert {name: value[0] for name, value in snapshot(output).items()} == before
        if pack == PACKS[2]:
            contract = metadata.selected_rest_contracts[0]
            assert contract["responses"] == {"202": {"description": "Synthetic claim accepted for routing"}}
            assert not metadata.operations[0].response_fields
            controller = next(output.rglob("InboundController.java")).read_text()
            assert '@PostMapping("/claims")' in controller
            assert "return ResponseEntity.status(202).build();" in controller
            assert "return ResponseEntity.ok(response);" not in controller


@pytest.mark.parametrize("status", ["200", "202"])
def test_passthrough_single_json_success_is_emitted(tmp_path, status):
    manifest, path = claims_input(tmp_path)
    spec = yaml.safe_load(path.read_text())
    spec["paths"]["/claims"]["post"]["responses"] = {status: {"description": "Result", "content": {
        "application/json": {"schema": {"type": "object", "properties": {"receipt": {"type": "string"}}}}}}}
    path.write_text(yaml.safe_dump(spec))
    metadata = build_metadata_project(manifest)
    output = tmp_path / "app"
    generate_application(metadata, output)
    source = next(output.rglob("InboundController.java")).read_text()
    expected = "ResponseEntity.ok(response)" if status == "200" else "ResponseEntity.status(202).body(response)"
    assert expected in source


def test_passthrough_empty_200_is_emitted_without_invented_body(tmp_path):
    manifest, path = claims_input(tmp_path)
    spec = yaml.safe_load(path.read_text())
    responses = spec["paths"]["/claims"]["post"]["responses"]
    responses["200"] = responses.pop("202")
    path.write_text(yaml.safe_dump(spec))
    output = tmp_path / "app"
    generate_application(build_metadata_project(manifest), output)
    assert "return ResponseEntity.status(200).build();" in next(output.rglob("InboundController.java")).read_text()


@pytest.mark.parametrize("responses", [
    {"201": {"description": "Created"}}, {"204": {"description": "Empty"}},
    {"200": {"description": "First"}, "202": {"description": "Second"}},
    {"202": {"$ref": "#/components/responses/Missing"}},
    {"202": {"description": "Array", "content": {"application/json": {"schema": {"type": "array"}}}}},
])
@pytest.mark.parametrize("entry", ["generate", "plan", "apply"])
def test_passthrough_unsupported_success_preserves_output(tmp_path, responses, entry):
    manifest, path = claims_input(tmp_path)
    spec = yaml.safe_load(path.read_text())
    spec["paths"]["/claims"]["post"]["responses"] = responses
    path.write_text(yaml.safe_dump(spec))
    metadata = build_metadata_project(manifest)
    output = tmp_path / "app"
    output.mkdir()
    sentinel = output / "developer.txt"
    sentinel.write_text("unchanged")
    sentinel.chmod(0o444)
    before, mtime = snapshot(output), output.stat().st_mtime_ns
    try:
        with pytest.raises(ValueError, match="Write operation.*unsupported"):
            if entry == "generate":
                generate_application(metadata, output)
            elif entry == "plan":
                build_change_plan(metadata=metadata, package_dir=output)
            else:
                apply_change_plan(metadata=metadata, package_dir=output, approved_plan_hash="unused")
        assert snapshot(output) == before
        assert output.stat().st_mtime_ns == mtime
        absent = tmp_path / "absent" / "app"
        with pytest.raises(ValueError, match="Write operation.*unsupported"):
            if entry == "generate":
                generate_application(metadata, absent)
            elif entry == "plan":
                build_change_plan(metadata=metadata, package_dir=absent)
            else:
                apply_change_plan(metadata=metadata, package_dir=absent, approved_plan_hash="unused")
        assert not absent.parent.exists()
    finally:
        sentinel.chmod(0o644)


def test_empty_success_cannot_discard_canonical_response_fields(tmp_path):
    manifest, _ = claims_input(tmp_path)
    metadata = build_metadata_project(manifest)
    metadata.operations[0].response_fields.append(CanonicalField(name="receipt", type=CanonicalFieldType.STRING))
    with pytest.raises(ValueError, match="response fields.*no response content"):
        generate_application(metadata, tmp_path / "absent")
    assert not (tmp_path / "absent").exists()
