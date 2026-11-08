"""Derived-publication controls; never execute a runtime or change originals."""

import copy
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import project_generated_image_proof_evidence as projection
from scripts.project_generated_image_proof_evidence import main, project


def fixture():
    cases = []
    for java in ("17", "21"):
        nonce = "default-lz4-synthetic-j" + java
        cases.append(
            {
                "java_target": java,
                "roundtrip": {
                    "key": nonce,
                    "input_partition_key": nonce,
                    "input": {"paymentId": nonce, "amount": 12.34},
                    "output": {"entryId": nonce, "amountMinorUnits": 1234},
                    "output_partition_key": None,
                },
            }
        )
    return {
        "schema_version": 1,
        "status": "validated-with-explicit-evidence-limits",
        "release_acceptance": False,
        "goal_complete": False,
        "input_sha256": {"synthetic/DatasourceCredentialConfig.java": "a" * 64},
        "runtime_default": {"cases": cases},
        "unavailable_preimages_or_bindings": [],
    }


def test_original_unchanged_and_hash_inventory_lossless():
    value = fixture()
    before = copy.deepcopy(value)
    result = project(value, "b" * 64)
    assert value == before
    assert {r["path"]: r["sha256"] for r in result["input_files"]} == value["input_sha256"]
    for row in result["runtime_default"]["cases"]:
        wire = row["roundtrip"]
        assert (
            wire["key"]
            == wire["input_partition_key"]
            == wire["input"]["paymentId"]
            == wire["output"]["entryId"]
        )
        assert wire["key"].startswith("<synthetic-correlation-")
        assert wire["input"]["amount"] == 12.34 and wire["output"]["amountMinorUnits"] == 1234
        assert wire["output_partition_key"] is None
    assert result["publication_projection"]["secret_scan_exceptions_added"] is False
    assert result["publication_projection"]["raw_runtime_receipt"] is False


@pytest.mark.parametrize(
    "field", ["key", "input_partition_key", "input.paymentId", "output.entryId"]
)
def test_projection_cannot_hide_a_failed_correlation(field):
    value = fixture()
    wire = value["runtime_default"]["cases"][0]["roundtrip"]
    if "." in field:
        parent, child = field.split(".")
        wire[parent][child] = "different"
    else:
        wire[field] = "different"
    with pytest.raises(ValueError):
        project(value, "b" * 64)


def test_cli_fresh_output_and_original_byte_digest(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    raw = json.dumps(fixture()).encode()
    source.write_bytes(raw)
    assert main(["--input", str(source), "--output", str(output)]) == 0
    result = json.loads(output.read_bytes())
    assert (
        result["publication_projection"]["private_summary_sha256"]
        == hashlib.sha256(raw).hexdigest()
    )
    assert source.read_bytes() == raw
    assert main(["--input", str(source), "--output", str(output)]) == 2


def test_unvalidated_record_is_not_published(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text("{}")
    assert main(["--input", str(source), "--output", str(output)]) == 2
    assert not output.exists()


DATE = "2026-10-19T03:43:29+00:00"
PROSE = "SYNTHETIC full advisory prose and PoC, never public."


def compressed(value):
    return gzip.compress(json.dumps(value, sort_keys=True).encode(), mtime=0)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_hash(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode())


def vendor_fixture():
    rows = []
    for identifier in (*projection.LZ4, projection.JACKSON):
        jackson = identifier == projection.JACKSON
        coordinate = "tools.jackson.core:jackson-databind" if jackson else "at.yawk.lz4:lz4-java"
        affected_range, fix = (">= 3.0.0, < 3.1.5", "3.1.5") if jackson else projection.LZ4[identifier]
        branches = []
        for index in range(5 if jackson else 2):
            name = coordinate if index == 0 else ("other.group:component" + str(index))
            branches.append({"package": {"ecosystem": "maven", "name": name, "description": PROSE},
                             "vulnerable_version_range": affected_range,
                             "first_patched_version": fix, "description": PROSE})
        global_body = {
            "ghsa_id": identifier, "cve_id": "CVE-2026-12345", "published_at": DATE,
            "updated_at": DATE, "html_url": "https://example.invalid/advisory/" + identifier,
            "url": "https://example.invalid/api/" + identifier,
            "identifiers": [{"type": "GHSA", "value": identifier}, {"type": "CVE", "value": "CVE-2026-12345"}],
            "vulnerabilities": branches, "description": PROSE, "summary": PROSE,
            "credits": [{"type": "finder", "user": {"login": "synthetic-user", "type": "User",
                         "html_url": "https://example.invalid/synthetic-user", "bio": PROSE}}],
            "unrestricted": {"details": PROSE},
        }
        repository = copy.deepcopy(global_body)
        repository["credits"] = [{"login": "synthetic-user", "type": "finder", "description": PROSE}]
        for branch in repository["vulnerabilities"]:
            branch["patched_versions"] = branch.pop("first_patched_version")
        if jackson:
            repository["vulnerabilities"][0]["vulnerable_version_range"] = ">= 3.0.0, <= 3.2.0"
        else:
            repository["vulnerabilities"][1]["patched_versions"] = ""
        osv = {"id": identifier, "published": DATE, "modified": DATE,
               "aliases": ["CVE-2026-12345"], "details": PROSE, "summary": PROSE,
               "references": [{"type": "WEB", "url": "https://example.invalid/" + identifier,
                               "description": PROSE}],
               "affected": [{"package": {"ecosystem": "Maven", "name": branch["package"]["name"]},
                             "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": fix}],
                                         "description": PROSE}],
                             "database_specific": {"source": "https://example.invalid/source", "details": PROSE}}
                            for branch in branches]}
        labels = ("repository", "new-global", "new-osv") if jackson else ("old-global", "old-osv", "new-global", "new-osv")
        evidence = [{"label": label, "http_status": 404 if label.startswith("old-") else 200,
                     "content_sha256": "b" * 64, "retrieved_at_utc": DATE,
                     "evidence": {"root": "plan", "member": identifier + "/" + label + ".body", "sha256": "c" * 64}}
                    for label in labels]
        historical = {"id": identifier, "status": "OPEN", "risk_accepted": False,
                      "source_sha256": "d" * 64, "source_retrieved_at_utc": DATE, "source": "historical.json.gz",
                      "next_decision": "Retain OPEN", "owner": "Engine maintainer", "open_reasons": ["OPEN_FEED_COVERAGE_GAP"],
                      "branches": [{"coordinate": coordinate, "affected_range": affected_range,
                                    "final_runtime": "NOT_AFFECTED_VERSION", "reported_fixed": fix,
                                    "scope_observations": [], "statuses": ["NOT_AFFECTED_VERSION"]}]}
        observations = []
        for index in range(30 if jackson else 9):
            for stage in sorted(projection.STAGES):
                case = "synthetic-" + str(index) + "-j17"
                refs = {name: {"root": "current", "member": case + "/" + stage + "/" + name + ".json.gz",
                               "sha256": "e" * 64} for name in ("assessment", "packaged", "syft", "provenance")}
                version = "3.1.7" if jackson else "1.11.4"
                artifact = {"name": coordinate.split(":")[1], "type": "java-archive", "version": version,
                            "purl": "pkg:maven/" + coordinate.replace(":", "/") + "@" + version,
                            "physical_hashes": [{"member": "component.jar", "sha256": "f" * 64}],
                            "locations": [{"path": "/workspace/target/app.jar:BOOT-INF/lib/component.jar"}]}
                observation = {"case": case, "stage": stage, "evidence": refs}
                if jackson:
                    observation["artifacts"] = [artifact]
                else:
                    observation.update({"image_id": "sha256:" + "a" * 64, "jar_sha256": "b" * 64,
                                        "packaged": [{"group": "at.yawk.lz4", "artifact": "lz4-java", "version": "1.11.4",
                                                      "filename": "lz4-java-1.11.4.jar", "classifier": "", "origin": "resolved-runtime",
                                                      "sha256": "f" * 64}],
                                        "physical_artifacts": [artifact], "org_lz4_observations": [], "org_lz4_absence_checked": True,
                                        "behavior_proofs_passed": True, "behavior_claims_are_production_image_proof": False,
                                        "behavior_to_campaign_jar_hash_link": "not-inferred-from-version-or-origin",
                                        "proof_claims": ["lz4-default", "lz4-jni"]})
                observations.append(observation)
        row = {"id": identifier, "status": "OPEN", "risk_accepted": False, "adopted": False, "native_clearance": False,
               "owner": "Engine maintainer", "next_action": "Retain OPEN limits", "historical_open_record": historical,
               "source_evidence": evidence, "global_advisory": global_body, "repository_advisory": repository,
               "osv_advisory": osv, "current_observations": observations}
        if jackson:
            row.update({"contradiction": "Synthetic inclusive repository range differs from global.",
                        "historical_scopes": {"runtime": "synthetic runtime", "test_only": "synthetic test-only"}})
        else:
            row.update({"coordinate": coordinate, "affected_range": affected_range, "fix_floor": fix, "gaps": [],
                        "source_range_evaluation": projection.CONCLUSION, "current_applicability_conclusion": projection.CONCLUSION,
                        "current_disposition": "supported-candidate/OPEN", "behavior_proof_gaps": [],
                        "behavior_hash_link_limitations": [{"claim": "lz4-default", "status": "OPEN_BEHAVIOR_JAR_HASH_NOT_RETAINED"}],
                        "source_observation": None})
        rows.append(row)
    return {"schema_version": "residual-vendor-current-v1", "status": "complete-assessed-with-OPEN",
            "release_clearance": False, "risk_accepted": False, "rows": rows}


def replay_fixture():
    return {"schema_version": 1, "status": "complete-publication-replay",
            "command": ["<host-5>/Documents/GitHub/synthetic/python/bin/python", "-B", "<host-1>/scripts/publish.py"],
            "started_at_utc": DATE, "ended_at_utc": DATE, "cases": 30, "stage_assessments": 60,
            "summary": {"cases": 30, "stage_observations": 60, "disposition": "OPEN"},
            "generator_sha": "a" * 40, "publication_tooling_sha": "b" * 40, "publication_sha256": "c" * 64,
            "execution_kind": "retained-assessment publication replay", "scans_repeated": 0,
            "goal": "synthetic bounded projection", "exit_code": 0, "cli_exit_code": 0, "input_files_unchanged": True,
            "amendment_revision": 3, "last_consumed_execution_ordinal": 36, "repair_cycle": 8, "repair_ceiling": 8,
            "runtime_proofs_repeated": 0, "arbitrary_original": {"counts": [622, 22740]}}


def project_fixture(kind, value=None):
    value = value if value is not None else (vendor_fixture() if kind == "vendor" else replay_fixture())
    raw = compressed(value)
    projector = getattr(projection, "project_" + kind)
    member = projection.VENDOR_MEMBER if kind == "vendor" else projection.REPLAY_MEMBER
    return projector(raw, sha(raw), member), raw


def rehash_projection(value):
    """Let negative controls bypass self-hashes so shape/source checks must do the work."""
    metadata = value["publication_projection"]
    if "rows" in metadata:
        for row, binding in zip(value["rows"], metadata["rows"], strict=True):
            for role in projection.BODIES:
                binding["bodies"][role]["projected_sha256"] = canonical_hash(row[role])
            binding["projected_sha256"] = canonical_hash(row)
    metadata["projected_payload_sha256"] = canonical_hash({k: v for k, v in value.items() if k != "publication_projection"})


def test_vendor_projection_is_deterministic_lossless_outside_bodies_and_reconstructable():
    source = vendor_fixture()
    before = copy.deepcopy(source)
    value, raw = project_fixture("vendor", source)
    assert source == before
    assert value == projection.project_vendor(raw, sha(raw), projection.VENDOR_MEMBER)
    projection.validate_vendor_projection(value)
    projection.validate_vendor_projection(value, raw)
    metadata = value["publication_projection"]
    assert metadata["source"] == {"archive_member": projection.VENDOR_MEMBER, "gzip_sha256": sha(raw),
                                  "json_sha256": sha(gzip.decompress(raw))}
    assert metadata["source_canonical_sha256"] == canonical_hash(source)
    assert PROSE not in json.dumps(value)
    for original, row, binding in zip(source["rows"], value["rows"], metadata["rows"], strict=True):
        assert {k: v for k, v in row.items() if k not in projection.BODIES} == {
            k: v for k, v in original.items() if k not in projection.BODIES}
        assert binding["canonical_sha256"] == canonical_hash(original)
        for role in projection.BODIES:
            body_binding = binding["bodies"][role]
            assert body_binding["canonical_sha256"] == canonical_hash(original[role])
            parts = body_binding["json_pointer"].split("/")
            assert source[parts[1]][int(parts[2])][parts[3]] == original[role]
            assert row["source_evidence"][0]["content_sha256"] != body_binding["canonical_sha256"]
    assert value["rows"][-1]["contradiction"] == source["rows"][-1]["contradiction"]


def test_replay_only_interpreter_representation_changes():
    original = replay_fixture()
    value, raw = project_fixture("replay", original)
    expected = copy.deepcopy(original)
    expected["command"][0] = "python3"
    assert {k: v for k, v in value.items() if k != "publication_projection"} == expected
    assert original["command"][0].startswith("<host-5>/")
    assert value["publication_projection"]["original_command"]["canonical_sha256"] == canonical_hash(original["command"])
    assert value["publication_projection"]["interpreter"]["historical_version"] == "not-recorded"
    projection.validate_replay_projection(value, raw)
    with pytest.raises(ValueError, match="not supported"):
        projection.project_replay(raw, sha(raw), projection.REPLAY_MEMBER, {"version": "today"})


@pytest.mark.parametrize("kind", ["vendor", "replay"])
def test_wrong_source_and_fingerprints_cannot_reconstruct(kind):
    value, raw = project_fixture(kind)
    validate = getattr(projection, "validate_" + kind + "_projection")
    original = json.loads(gzip.decompress(raw))
    if kind == "vendor":
        original["rows"][0]["owner"] = "different owner"
    else:
        original["arbitrary_original"]["counts"][0] = 623
    wrong = compressed(original)
    with pytest.raises(ValueError):
        validate(value, wrong)
    value["publication_projection"]["source"]["gzip_sha256"] = sha(wrong)
    with pytest.raises(ValueError):
        validate(value, wrong)
    # Even a coordinated, shape-valid projected edit cannot conceal the retained source.
    value, raw = project_fixture(kind)
    if kind == "vendor":
        value["rows"][0]["owner"] = "different owner"
    else:
        value["arbitrary_original"]["counts"][0] = 623
    rehash_projection(value)
    validate(value)
    with pytest.raises(ValueError, match="reconstruction"):
        validate(value, raw)


@pytest.mark.parametrize("kind", ["vendor", "replay"])
@pytest.mark.parametrize("member", ["../original.gz", "/original.gz", "reconciliation/./original.gz", "bad\\original.gz",
                                    "x:original.gz", "bad\x00.gz", "residual-vendor-current.json.gz", projection.REPLAY_MEMBER])
def test_unsafe_or_wrong_role_sources_rejected(kind, member):
    if kind == "replay" and member == projection.REPLAY_MEMBER:
        member = projection.VENDOR_MEMBER
    raw = compressed(vendor_fixture() if kind == "vendor" else replay_fixture())
    with pytest.raises(ValueError):
        getattr(projection, "project_" + kind)(raw, sha(raw), member)


@pytest.mark.parametrize("kind", ["vendor", "replay"])
@pytest.mark.parametrize("raw", [b"{}", gzip.compress(b'{"x":1,"x":2}'), gzip.compress(b'{"x":NaN}'), gzip.compress(b"[]")])
def test_malformed_sources_rejected(kind, raw):
    member = projection.VENDOR_MEMBER if kind == "vendor" else projection.REPLAY_MEMBER
    with pytest.raises((ValueError, OSError)):
        getattr(projection, "project_" + kind)(raw, sha(raw), member)


@pytest.mark.parametrize("kind", ["vendor", "replay"])
def test_source_hash_and_bounded_decompression(kind, monkeypatch):
    raw = compressed(vendor_fixture() if kind == "vendor" else replay_fixture())
    member = projection.VENDOR_MEMBER if kind == "vendor" else projection.REPLAY_MEMBER
    projector = getattr(projection, "project_" + kind)
    for digest in (None, "wrong", "0" * 64):
        with pytest.raises(ValueError):
            projector(raw, digest, member)
    monkeypatch.setattr(projection, "MAX_SOURCE_BYTES", len(raw) + 10)
    with pytest.raises(ValueError, match="decompressed"):
        projector(raw, sha(raw), member)


@pytest.mark.parametrize("field", ["id", "source_evidence", "current_observations", "historical_open_record", "fix_floor", "global_advisory"])
def test_missing_vendor_required_fields(field):
    value = vendor_fixture()
    del value["rows"][0][field]
    with pytest.raises(ValueError):
        project_fixture("vendor", value)


@pytest.mark.parametrize("mutation", ["row-set", "duplicate-row", "identity", "range", "fix", "events", "observations",
                                      "evidence", "physical", "status", "risk", "conclusion", "http", "source-hash", "alias"])
def test_vendor_contradictions_fail_closed(mutation):
    value = vendor_fixture()
    row = value["rows"][0]
    if mutation == "row-set":
        value["rows"].pop()
    elif mutation == "duplicate-row":
        value["rows"][-1] = copy.deepcopy(row)
    elif mutation == "identity":
        row["global_advisory"]["ghsa_id"] = projection.JACKSON
    elif mutation == "range":
        del row["global_advisory"]["vulnerabilities"][0]["vulnerable_version_range"]
    elif mutation == "fix":
        row["global_advisory"]["vulnerabilities"][0]["first_patched_version"] = "9.9.9"
    elif mutation == "events":
        row["osv_advisory"]["affected"][0]["ranges"][0]["events"] = []
    elif mutation == "observations":
        row["current_observations"].pop()
    elif mutation == "evidence":
        row["current_observations"][0]["evidence"]["syft"]["member"] = "other/stage/syft.json.gz"
    elif mutation == "physical":
        row["current_observations"][0]["physical_artifacts"][0]["physical_hashes"][0]["sha256"] = "a" * 64
    elif mutation == "status":
        row["status"] = "CLOSED"
    elif mutation == "risk":
        row["risk_accepted"] = True
    elif mutation == "conclusion":
        row["current_applicability_conclusion"] = "NOT_INSTALLED"
    elif mutation == "http":
        row["source_evidence"][0]["http_status"] = True
    elif mutation == "source-hash":
        row["source_evidence"][0]["content_sha256"] = "invalid"
    elif mutation == "alias":
        row["osv_advisory"]["aliases"] = ["CVE-2026-99999"]
    with pytest.raises(ValueError):
        project_fixture("vendor", value)


@pytest.mark.parametrize("mutation", ["body-leak", "nested-leak", "body-identity", "range", "branch", "body-hash", "row-hash",
                                      "source-role", "metadata-role", "body-pointer", "row-pointer", "missing-source", "private-path"])
def test_public_vendor_validation_is_strict_even_after_rehash(mutation):
    value, _ = project_fixture("vendor")
    row = value["rows"][0]
    metadata = value["publication_projection"]
    if mutation == "body-leak":
        row["global_advisory"]["details"] = PROSE
    elif mutation == "nested-leak":
        row["osv_advisory"]["affected"][0]["database_specific"]["details"] = PROSE
    elif mutation == "body-identity":
        del row["global_advisory"]["ghsa_id"]
    elif mutation == "range":
        del row["global_advisory"]["vulnerabilities"][0]["vulnerable_version_range"]
    elif mutation == "branch":
        row["global_advisory"]["vulnerabilities"].pop()
    elif mutation == "body-hash":
        metadata["rows"][0]["bodies"]["global_advisory"]["canonical_sha256"] = None
    elif mutation == "row-hash":
        metadata["rows"][0]["canonical_sha256"] = None
    elif mutation == "source-role":
        metadata["source"]["archive_member"] = projection.REPLAY_MEMBER
    elif mutation == "metadata-role":
        metadata["role"] = "ORIGINAL"
    elif mutation == "body-pointer":
        metadata["rows"][0]["bodies"]["global_advisory"]["json_pointer"] = "/rows/1/global_advisory"
    elif mutation == "row-pointer":
        metadata["rows"][0]["json_pointer"] = "/rows/1"
    elif mutation == "missing-source":
        del metadata["source"]["json_sha256"]
    elif mutation == "private-path":
        row["owner"] = "/" + "Users/synthetic/private"
    rehash_projection(value)
    with pytest.raises(ValueError):
        projection.validate_vendor_projection(value)


@pytest.mark.parametrize("mutation", ["missing-command", "missing-date", "cases", "summary", "interpreter", "invented-version", "original-command"])
def test_replay_negative_controls(mutation):
    value, _ = project_fixture("replay")
    if mutation == "missing-command":
        del value["command"]
    elif mutation == "missing-date":
        del value["ended_at_utc"]
    elif mutation == "cases":
        value["cases"] = True
    elif mutation == "summary":
        value["summary"]["stage_observations"] = 1
    elif mutation == "interpreter":
        value["command"][0] = "<host-5>/Documents/GitHub/private/python"
    elif mutation == "invented-version":
        value["publication_projection"]["interpreter"]["historical_version"] = "3.11.15"
    elif mutation == "original-command":
        value["publication_projection"]["original_command"]["canonical_sha256"] = "invalid"
    rehash_projection(value)
    with pytest.raises(ValueError):
        projection.validate_replay_projection(value)


@pytest.mark.parametrize("field", ["rows", "source_evidence", "current_observations", "historical_open_record", "global_advisory"])
@pytest.mark.parametrize("bad", [None, 7, "not-an-object", True])
def test_malformed_vendor_container_types(field, bad):
    value = vendor_fixture()
    if field == "rows":
        value[field] = bad
    else:
        value["rows"][0][field] = bad
    with pytest.raises(ValueError):
        project_fixture("vendor", value)


@pytest.mark.parametrize("field", ["exit_code", "cli_exit_code", "input_files_unchanged", "scans_repeated", "runtime_proofs_repeated",
                                    "generator_sha", "publication_tooling_sha", "started_at_utc", "repair_cycle", "goal"])
def test_replay_required_receipt_fields(field):
    value = replay_fixture()
    del value[field]
    with pytest.raises(ValueError):
        project_fixture("replay", value)


@pytest.mark.parametrize("kind", ["vendor", "replay"])
def test_cli_validation_failure_never_creates_output_or_exposes_paths(kind, tmp_path, capsys):
    source, output = tmp_path / "malformed.json.gz", tmp_path / "unwritten.json.gz"
    raw = gzip.compress(b'{"schema_version":1,"schema_version":2}')
    source.write_bytes(raw)
    member = projection.VENDOR_MEMBER if kind == "vendor" else projection.REPLAY_MEMBER
    assert main(["--mode", kind, "--input", str(source), "--output", str(output),
                 "--expected-sha256", sha(raw), "--source-member", member]) == 2
    assert not output.exists() and source.read_bytes() == raw
    error = capsys.readouterr().err
    assert "ValueError" in error and "Traceback" not in error and str(tmp_path) not in error


def test_source_body_hash_is_not_replaced_by_embedded_canonical_hash():
    value, raw = project_fixture("vendor")
    binding = value["publication_projection"]["rows"][0]["bodies"]["global_advisory"]
    binding["canonical_sha256"] = value["rows"][0]["source_evidence"][0]["content_sha256"]
    projection.validate_vendor_projection(value)
    with pytest.raises(ValueError, match="reconstruction"):
        projection.validate_vendor_projection(value, raw)


@pytest.mark.parametrize("kind", ["vendor", "replay"])
def test_explicit_cli_modes_require_binding_and_write_fresh_deterministic_outputs(kind, tmp_path):
    _, raw = project_fixture(kind)
    source = tmp_path / "original.json.gz"
    source.write_bytes(raw)
    output, second = tmp_path / "projected.json.gz", tmp_path / "second.json.gz"
    member = projection.VENDOR_MEMBER if kind == "vendor" else projection.REPLAY_MEMBER
    base = ["--mode", kind, "--input", str(source)]
    assert main(base + ["--output", str(output)]) == 2
    assert not output.exists()
    args = base + ["--expected-sha256", sha(raw), "--source-member", member]
    assert main(args + ["--output", str(output)]) == 0
    assert main(args + ["--output", str(second)]) == 0
    assert output.read_bytes() == second.read_bytes()
    assert main(args + ["--output", str(output)]) == 2
    assert source.read_bytes() == raw
    getattr(projection, "validate_" + kind + "_projection")(json.loads(gzip.decompress(output.read_bytes())), raw)


@pytest.mark.parametrize("kind", ["vendor", "replay"])
def test_retained_real_record_structural_check(kind):
    directory = os.environ.get("EDGEFORGE_PROJECTION_SOURCE_DIR")
    if not directory:
        pytest.skip("opt-in retained source directory not supplied")
    filename = "residual-vendor-current.json.gz" if kind == "vendor" else "publication-replay.json.gz"
    raw = (Path(directory) / filename).read_bytes()
    member = projection.VENDOR_MEMBER if kind == "vendor" else projection.REPLAY_MEMBER
    value = getattr(projection, "project_" + kind)(raw, sha(raw), member)
    getattr(projection, "validate_" + kind + "_projection")(value, raw)
    assert_retained_public_bytes(value, filename)


def assert_retained_public_bytes(value, filename):
    root = Path(projection.__file__).resolve().parents[1]
    public_raw = (root / "docs/handover-evidence/generated-images/2026-10-20-noble" / filename).read_bytes()
    encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    assert encoded == gzip.decompress(public_raw)
    stream = io.BytesIO()
    # Retained packaging uses the portable GzipFile header, not compress()'s OS byte.
    with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as zipped:
        zipped.write(encoded)
    assert stream.getvalue() == public_raw


def lz4_osv_branch(value):
    row = next(row for row in value["rows"] if row["id"] == "GHSA-343h-94h5-c4wr")
    return next(branch for branch in row["osv_advisory"]["affected"]
                if branch["package"]["name"] == "at.yawk.lz4:lz4-java")


OSV_REVIEW_COUNTEREXAMPLES = {
    "inverted": [{"introduced": "99.0.0"}, {"fixed": "1.11.4"}],
    "includes-installed": [{"introduced": "1.11.4"}, {"last_affected": "9.9.9"},
                           {"introduced": "0"}, {"fixed": "1.11.4"}],
}


def bind_mutated_vendor_source(value, source):
    """Reseal every source/public hash so semantic rejection cannot rely on stale hashes."""
    raw = compressed(source)
    metadata = value["publication_projection"]
    metadata["source"].update(gzip_sha256=sha(raw), json_sha256=sha(gzip.decompress(raw)))
    metadata["source_canonical_sha256"] = canonical_hash(source)
    for row, binding in zip(source["rows"], metadata["rows"], strict=True):
        binding["canonical_sha256"] = canonical_hash(row)
        for role in projection.BODIES:
            binding["bodies"][role]["canonical_sha256"] = canonical_hash(row[role])
    rehash_projection(value)
    return raw


def assert_vendor_cli_rejects(raw, directory):
    directory.mkdir()
    source, output = directory / "source.json.gz", directory / "never-written.json.gz"
    source.write_bytes(raw)
    result = subprocess.run(
        [sys.executable, "-B", str(Path(projection.__file__)), "--mode", "vendor",
         "--input", str(source), "--output", str(output), "--expected-sha256", sha(raw),
         "--source-member", projection.VENDOR_MEMBER], capture_output=True, check=False,
    )
    (directory / "cli.stdout").write_bytes(result.stdout)
    (directory / "cli.stderr").write_bytes(result.stderr)
    assert result.returncode == 2, result.stdout + result.stderr
    assert not output.exists() and source.read_bytes() == raw
    assert b"Traceback" not in result.stderr and str(directory).encode() not in result.stderr


@pytest.mark.parametrize("counterexample", OSV_REVIEW_COUNTEREXAMPLES)
def test_review_osv_counterexamples_reject_cli_and_resealed_source(counterexample, tmp_path):
    source = vendor_fixture()
    value, _ = project_fixture("vendor", source)
    for record in (source, value):
        lz4_osv_branch(record)["ranges"][0]["events"] = copy.deepcopy(OSV_REVIEW_COUNTEREXAMPLES[counterexample])
    raw = bind_mutated_vendor_source(value, source)
    assert_vendor_cli_rejects(raw, tmp_path / "projection-cli")
    with pytest.raises(ValueError):
        projection.project_vendor(raw, sha(raw), projection.VENDOR_MEMBER)
    for source_raw in (None, raw):
        with pytest.raises(ValueError):
            projection.validate_vendor_projection(value, source_raw=source_raw)


@pytest.mark.parametrize("counterexample", OSV_REVIEW_COUNTEREXAMPLES)
def test_real_review_osv_counterexamples_reject_cli_and_repository(counterexample, tmp_path):
    directory = os.environ.get("EDGEFORGE_PROJECTION_SOURCE_DIR")
    if not directory:
        pytest.skip("opt-in retained source directory not supplied")
    from scripts import verify_generated_image_evidence_split as verifier

    source_path = Path(directory) / "residual-vendor-current.json.gz"
    original = source_path.read_bytes()
    source = json.loads(gzip.decompress(original))
    value = projection.project_vendor(original, sha(original), projection.VENDOR_MEMBER)
    for record in (source, value):
        lz4_osv_branch(record)["ranges"][0]["events"] = copy.deepcopy(OSV_REVIEW_COUNTEREXAMPLES[counterexample])
    mutated_raw = bind_mutated_vendor_source(value, source)
    assert_vendor_cli_rejects(mutated_raw, tmp_path / "real-projection-cli")
    for source_raw in (None, mutated_raw):
        with pytest.raises(ValueError):
            projection.validate_vendor_projection(value, source_raw=source_raw)

    bundle = "docs/handover-evidence/generated-images/2026-10-20-noble"
    manifest_name = bundle + "-core-manifest.json"
    root = tmp_path / "resealed-core"
    shutil.copytree(verifier.ROOT / bundle, root / bundle)
    manifest = json.loads((verifier.ROOT / manifest_name).read_bytes())
    publication = json.loads((root / bundle / "publication.json").read_bytes())
    name = "residual-vendor-current.json.gz"
    data = compressed(value)
    entry = next(entry for entry in publication["files"] if entry["file"] == name)
    entry.update(sanitized_gzip_sha256=sha(data), sanitized_json_sha256=sha(gzip.decompress(data)))
    source_name = value["publication_projection"]["source"]["archive_member"]
    entry = next(entry for entry in publication["files"] if entry["file"] == source_name)
    entry.update(sanitized_gzip_sha256=sha(mutated_raw), sanitized_json_sha256=sha(gzip.decompress(mutated_raw)))
    for filename, content in ((name, data), ("publication.json", json.dumps(publication, sort_keys=True).encode())):
        (root / bundle / filename).write_bytes(content)
        entry = next(entry for entry in manifest["core"] if entry["path"] == bundle + "/" + filename)
        entry.update(bytes=len(content), sha256=sha(content), git_blob=verifier.git_blob(content))
    (root / manifest_name).write_text(json.dumps(manifest, sort_keys=True))
    result = subprocess.run(
        [sys.executable, "-B", str(Path(verifier.__file__)), "--root", str(root),
         "--manifest", str(root / manifest_name), "--evidence-dir", bundle],
        capture_output=True, check=False,
    )
    (tmp_path / "repository-cli.stdout").write_bytes(result.stdout)
    (tmp_path / "repository-cli.stderr").write_bytes(result.stderr)
    assert result.returncode == 2, result.stdout + result.stderr
    assert source_path.read_bytes() == original


@pytest.mark.parametrize("events", [
    [{"introduced": "0"}, {"fixed": "1.10.0"}, {"introduced": "1.11.0"}, {"fixed": "1.11.4"}],
    [{"introduced": "0"}, {"fixed": "1.11.4"}],
    [{"introduced": "1.11.0"}, {"last_affected": "1.11.0"},
     {"introduced": "1.11.1"}, {"fixed": "1.11.4"}],
    [{"introduced": "0"}, {"limit": "1.11.0"}, {"introduced": "1.11.0"}, {"fixed": "1.11.4"}],
    [{"introduced": "0"}, {"last_affected": "1.11.3"}, {"introduced": "1.11.5"}, {"fixed": "1.11.6"}],
])
def test_numeric_osv_valid_interval_topology(events):
    intervals = projection._osv_intervals(events)
    assert len(intervals) == len(events) // 2


@pytest.mark.parametrize("events", [
    [{"introduced": "2"}, {"fixed": "1"}],
    [{"introduced": "1"}, {"fixed": "1.0.0"}],
    [{"introduced": "1"}, {"limit": "1"}],
    [{"introduced": "2"}, {"last_affected": "1"}],
    [{"introduced": "0"}, {"fixed": "2"}, {"introduced": "1"}, {"fixed": "3"}],
    [{"introduced": "0"}, {"last_affected": "1"}, {"introduced": "1"}, {"fixed": "2"}],
    [{"introduced": "2"}, {"fixed": "3"}, {"introduced": "0"}, {"fixed": "1"}],
    [{"introduced": "0"}],
    [{"fixed": "0"}, {"introduced": "1"}],
    [{"introduced": "0"}, {"fixed": "1"}, {"introduced": "2"}],
])
def test_numeric_osv_invalid_interval_topology(events):
    with pytest.raises(ValueError):
        projection._osv_intervals(events)


@pytest.mark.parametrize("version", ["1.11.4-rc1", "1.11.4-SNAPSHOT", "1.11.4+build", "01.11.4",
                                     "1.2.3.4.5.6.7.8.9", "1000000000.0.0", "9" * 100, True, None])
def test_numeric_osv_comparison_refuses_unsupported_releases(version):
    with pytest.raises(ValueError, match="unsupported OSV release comparison"):
        projection._numeric_release(version)


@pytest.mark.parametrize("terminal,endpoint,accepted", [
    ("fixed", "1.11.4", True), ("limit", "1.11.4", True),
    ("last_affected", "1.11.3", True), ("last_affected", "1.11.4", False),
    ("last_affected", "1.11.4.0", False), ("fixed", "1.11.5", False),
    ("limit", "1.11.5", False),
])
def test_every_selected_osv_range_checks_installed_version(terminal, endpoint, accepted):
    source = vendor_fixture()
    value, _ = project_fixture("vendor", source)
    for record in (source, value):
        branch = lz4_osv_branch(record)
        # Keep the expected fixed event in another range: it cannot mask this interval.
        branch["ranges"].append({"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {terminal: endpoint}]})
    raw = bind_mutated_vendor_source(value, source)
    if accepted:
        assert projection.project_vendor(raw, sha(raw), projection.VENDOR_MEMBER) == value
        projection.validate_vendor_projection(value, source_raw=raw)
    else:
        with pytest.raises(ValueError, match="includes installed"):
            projection.project_vendor(raw, sha(raw), projection.VENDOR_MEMBER)
        for source_raw in (None, raw):
            with pytest.raises(ValueError, match="includes installed"):
                projection.validate_vendor_projection(value, source_raw=source_raw)


@pytest.mark.parametrize("version", ["1.11.4", "1.11.4.0", "1.11.4-rc1"])
def test_selected_osv_explicit_versions_cannot_contradict_installed_conclusion(version):
    source = vendor_fixture()
    value, _ = project_fixture("vendor", source)
    for record in (source, value):
        lz4_osv_branch(record)["versions"] = [version]
    raw = bind_mutated_vendor_source(value, source)
    with pytest.raises(ValueError):
        projection.project_vendor(raw, sha(raw), projection.VENDOR_MEMBER)
    for source_raw in (None, raw):
        with pytest.raises(ValueError):
            projection.validate_vendor_projection(value, source_raw=source_raw)


def test_valid_multi_interval_source_reconstructs_without_changing_facts():
    source = vendor_fixture()
    branch = lz4_osv_branch(source)
    branch["ranges"][0]["events"] = [
        {"introduced": "0"}, {"last_affected": "1.10.0"},
        {"introduced": "1.11.0"}, {"fixed": "1.11.4"},
        {"introduced": "1.11.5"}, {"limit": "1.11.6"},
    ]
    branch["versions"] = ["1.0", "1.10.0", "1.11.3", "1.11.5"]
    before = copy.deepcopy(source)
    value, raw = project_fixture("vendor", source)
    assert source == before
    public_branch = lz4_osv_branch(value)
    assert public_branch["versions"] == branch["versions"]
    assert public_branch["ranges"] == [{"type": "ECOSYSTEM", "events": branch["ranges"][0]["events"]}]
    projection.validate_vendor_projection(value)
    projection.validate_vendor_projection(value, source_raw=raw)


def test_ordered_later_interval_cannot_reaffect_installed_version():
    source = vendor_fixture()
    value, _ = project_fixture("vendor", source)
    for record in (source, value):
        lz4_osv_branch(record)["ranges"][0]["events"] = [
            {"introduced": "0"}, {"fixed": "1.11.4"},
            {"introduced": "1.11.4"}, {"last_affected": "1.11.4"},
        ]
    raw = bind_mutated_vendor_source(value, source)
    with pytest.raises(ValueError, match="includes installed"):
        projection.project_vendor(raw, sha(raw), projection.VENDOR_MEMBER)
    for source_raw in (None, raw):
        with pytest.raises(ValueError, match="includes installed"):
            projection.validate_vendor_projection(value, source_raw=source_raw)


def test_real_retained_projection_values_and_source_bytes_unchanged():
    directory = os.environ.get("EDGEFORGE_PROJECTION_SOURCE_DIR")
    if not directory:
        pytest.skip("opt-in retained source directory not supplied")
    path = Path(directory) / "residual-vendor-current.json.gz"
    raw = path.read_bytes()
    assert sha(raw) == "921e361dc7d246ae344029f728e2425a6a5d1f34bb6136c2ffa3b25eb6d58ca9"
    assert sha(gzip.decompress(raw)) == "68292deade915bab63fa9767032dab8552655dfb54807594bbb7db32bcda876a"
    value = projection.project_vendor(raw, sha(raw), projection.VENDOR_MEMBER)
    assert_retained_public_bytes(value, "residual-vendor-current.json.gz")
    projection.validate_vendor_projection(value, source_raw=raw)
    assert path.read_bytes() == raw
    jackson = next(row for row in value["rows"] if row["id"] == projection.JACKSON)
    assert jackson["status"] == "OPEN" and jackson["contradiction"]
    assert all(row["current_applicability_conclusion"] == projection.CONCLUSION
               for row in value["rows"] if row["id"] != projection.JACKSON)
