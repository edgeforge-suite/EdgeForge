"""Dated reconciliation keeps every identity/branch and refuses unsupported proof."""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.reconcile_generated_maven_findings import (
    baseline_inventory,
    bind_images,
    in_range,
    main,
    read,
    reconcile,
    verify_sources,
)

HISTORICAL_POLICY = Path("docs/handover-evidence/maven-policy-2026-10-05")
BASELINE = Path("docs/handover-evidence/generated-maven/2026-10-05")


@pytest.fixture
def policy(tmp_path):
    """Invented advisories/ranges only: never abbreviations of retained bodies."""
    target = tmp_path / "synthetic-policy"
    sources = target / "vendor-sources"
    sources.mkdir(parents=True)
    (target / "published-source").mkdir()
    (target / "published-source/index.json").write_text("[]")
    index = []

    def source(name, value, status=200):
        raw = json.dumps(value, sort_keys=True).encode()
        (sources / name).write_bytes(gzip.compress(raw, mtime=0))
        index.append({"artifact": name, "sha256_uncompressed": hashlib.sha256(raw).hexdigest(),
                      "bytes_uncompressed": len(raw), "http_status": status,
                      "retrieved_at_utc": "2000-01-01T00:00:00Z",
                      "url": "https://example.invalid/synthetic/" + name})

    source("lz4-advisories.json.gz", [{"ghsa_id": "SYNTH-FEED-GAP", "vulnerabilities": [
        {"package": {"ecosystem": "maven", "name": "org.example.synthetic:absent"},
         "vulnerable_version_range": "< 1.0.0", "patched_versions": "1.0.0"}]}])
    source("jackson-core-advisories.json.gz", [{"ghsa_id": "SYNTH-NOT-AFFECTED", "vulnerabilities": [
        {"package": {"ecosystem": "maven", "name": "tools.jackson.core:jackson-core"},
         "vulnerable_version_range": "< 1.0.0", "patched_versions": "1.0.0"}]}])
    source("jackson-databind-advisories.json.gz", [{"ghsa_id": "SYNTH-CONTRADICTION", "vulnerabilities": [
        {"package": {"ecosystem": "maven", "name": "com.fasterxml.jackson.core:jackson-databind"},
         "vulnerable_version_range": ">= 1.0.0, <= 9.0.0", "patched_versions": "1.0.0"}]}])
    for suffix in ("global", "osv"):
        source(f"SYNTH-FEED-GAP-{suffix}.json.gz", {"synthetic": "not found"}, 404)
    (sources / "retrieval-index.json").write_text(json.dumps(index))
    vendor = {"advisories": [{"id": name} for name in
              ("SYNTH-FEED-GAP", "SYNTH-NOT-AFFECTED", "SYNTH-CONTRADICTION")],
              "feed_gap": {"ids": ["SYNTH-FEED-GAP"]}}
    (target / "vendor-dispositions.json").write_text(json.dumps(vendor))
    history = {"historical_matches": 1, "mapped_matches": 1, "mappings": [
        {"historical_id": "SYNTH-NOT-AFFECTED", "historical_coordinate": "tools.jackson.core:jackson-core",
         "historical_version": "0.5.0"}]}
    (target / "historical-18-dispositions.json").write_text(json.dumps(history))
    return target


def fixture_images():
    # Mock image identities: these unit inputs are never committed as live evidence.
    _, cases = baseline_inventory(BASELINE)
    return {"generator_sha": "b" * 40, "cases": [
        {"case": name, "packaged_libraries": row["packaged_libraries"],
         "image_id": "sha256:" + "a" * 64, "jar_sha256": "c" * 64}
        for name, row in cases.items()]}


@pytest.mark.skipif(not os.environ.get("EDGEFORGE_HISTORICAL_MAVEN_POLICY"),
                    reason="opt-in full historical replay requires original private source inputs; not executed proof")
def test_all_retained_identities_reconciled_without_blanket_clearance():
    policy = Path(os.environ["EDGEFORGE_HISTORICAL_MAVEN_POLICY"])
    result = reconcile(policy, BASELINE, fixture_images())
    assert len(result["historical_mappings"]) == 18
    assert len(result["vendor_observations"]) == 33
    assert result["counts"]["historical"] == {"REMEDIATED_VERSION": 18}
    assert result["counts"]["vendor"] == {"SUPPORTED_VERSION_DISPOSITION": 27, "OPEN": 6}
    assert result["exit_code"] == 1 and not result["risk_accepted"]
    assert not result["m2_complete"] and not result["release_clearance"]
    contradiction = next(r for r in result["vendor_observations"] if r["id"] == "GHSA-5gvw-p9qm-jgwh")
    assert contradiction["open_reasons"] == ["OPEN_RANGE_CONTRADICTION"]
    branch = next(r for r in contradiction["branches"] if r["reported_fixed"] == "2.21.5")
    assert branch["affected_range"] == ">= 2.21.0, <= 2.22.0"
    assert branch["final_runtime"] == "NOT_INSTALLED"
    assert all(r["scope"] == "test" and not r["packaged"] for r in branch["scope_observations"])
    corrected = next(r for r in contradiction["branches"] if r["coordinate"].startswith("tools.") and "3.0.0" in r["affected_range"])
    assert corrected["reported_fixed"] == "3.1.5"
    assert corrected["statuses"] == ["NOT_AFFECTED_VERSION"]


def test_synthetic_reconciliation_keeps_findings_and_scope(policy):
    result = reconcile(policy, BASELINE, fixture_images())
    assert result["counts"]["historical"] == {"REMEDIATED_VERSION": 1}
    assert result["counts"]["vendor"] == {"SUPPORTED_VERSION_DISPOSITION": 1, "OPEN": 2}
    assert result["exit_code"] == 1 and not result["risk_accepted"]
    assert not result["m2_complete"] and not result["release_clearance"]
    rows = {row["id"]: row for row in result["vendor_observations"]}
    assert rows["SYNTH-FEED-GAP"]["open_reasons"] == ["OPEN_FEED_COVERAGE_GAP"]
    contradiction = rows["SYNTH-CONTRADICTION"]
    assert contradiction["open_reasons"] == ["OPEN_RANGE_CONTRADICTION"]
    assert contradiction["branches"][0]["final_runtime"] == "NOT_INSTALLED"
    assert all(r["scope"] == "test" and not r["packaged"]
               for r in contradiction["branches"][0]["scope_observations"])


@pytest.mark.parametrize("release,expression,expected", [
    ("2.22.0", ">= 2.21.0, <= 2.22.0", True),
    ("2.22.1", ">= 2.21.0, <= 2.22.0", False),
    ("3.1.5", ">= 3.0.0, <= 3.1.4", False),
    ("1.11.4", "<= 1.11.3", False),
    ("2.18.7", "2.10.0 - 2.18.7", True),
    ("2.18.8", "2.10.0 - 2.18.7", False),
    ("3.0.0", "3.0.0", True),
])
def test_retained_numeric_ranges_preserve_inclusive_bounds(release, expression, expected):
    assert in_range(release, expression) is expected


@pytest.mark.parametrize("expression", ["", "all versions", "2.x", ">= 3.0.0 || <2.0.0"])
def test_unknown_range_is_not_a_clean_result(expression):
    with pytest.raises(ValueError):
        in_range("3.1.7", expression)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "library", "version", "image", "jar"])
def test_missing_or_mismatched_image_proof_fails(mutation):
    report = copy.deepcopy(fixture_images())
    if mutation == "missing":
        report["cases"].pop()
    elif mutation == "duplicate":
        report["cases"][-1] = report["cases"][0]
    elif mutation == "library":
        report["cases"][0]["packaged_libraries"] = []
    elif mutation == "version":
        report["cases"][0]["packaged_libraries"][0] = "incorrect-version.jar"
    elif mutation == "image":
        report["cases"][0]["image_id"] = "floating:tag"
    else:
        report["cases"][0]["jar_sha256"] = "unknown"
    with pytest.raises(ValueError):
        bind_images(baseline_inventory(BASELINE)[1], report)


def test_retained_source_checksum_is_required(policy):
    path = policy / "vendor-sources/jackson-databind-advisories.json.gz"
    path.write_bytes(gzip.compress(b"[]"))
    with pytest.raises(ValueError, match="checksum"):
        verify_sources(policy)


def test_vendor_identity_cannot_be_omitted(policy):
    path = policy / "vendor-dispositions.json"
    ledger = json.loads(path.read_text())
    ledger["advisories"].pop()
    path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match="identity omitted"):
        reconcile(policy, BASELINE, fixture_images())


def test_cli_incomplete_is_error_not_findings(tmp_path, monkeypatch, policy):
    image = tmp_path / "images.json"
    image.write_text(json.dumps({"generator_sha": "b" * 40, "cases": []}))
    output = tmp_path / "result.json"
    monkeypatch.setattr("sys.argv", ["reconcile", "--policy", str(policy),
                                    "--baseline", str(BASELINE), "--packaged-inventories",
                                    str(image), "--output", str(output)])
    assert main() == 2
    assert json.loads(output.read_text())["status"] == "incomplete"


def test_cli_complete_findings_stay_visible(tmp_path, monkeypatch, policy):
    image = tmp_path / "images.json"
    image.write_text(json.dumps(fixture_images()))
    output = tmp_path / "result.json"
    monkeypatch.setattr("sys.argv", ["reconcile", "--policy", str(policy),
                                    "--baseline", str(BASELINE), "--packaged-inventories",
                                    str(image), "--output", str(output)])
    assert main() == 1
    assert json.loads(output.read_text())["status"] == "complete"


def test_synthetic_clean_is_complete_not_release_clearance(policy):
    vendor_path = policy / "vendor-dispositions.json"
    vendor = json.loads(vendor_path.read_text())
    vendor["feed_gap"]["ids"] = []
    vendor_path.write_text(json.dumps(vendor))
    source_path = policy / "vendor-sources/jackson-databind-advisories.json.gz"
    advisory = json.loads(gzip.decompress(source_path.read_bytes()))
    advisory[0]["vulnerabilities"][0]["vulnerable_version_range"] = "< 1.0.0"
    raw = json.dumps(advisory, sort_keys=True).encode()
    source_path.write_bytes(gzip.compress(raw, mtime=0))
    index_path = policy / "vendor-sources/retrieval-index.json"
    index = json.loads(index_path.read_text())
    for item in index:
        if item["artifact"] == source_path.name:
            item.update(sha256_uncompressed=hashlib.sha256(raw).hexdigest(), bytes_uncompressed=len(raw))
    index_path.write_text(json.dumps(index))
    result = reconcile(policy, BASELINE, fixture_images())
    assert result["status"] == "complete" and result["exit_code"] == 0
    assert not result["release_clearance"] and not result["risk_accepted"]


def test_duplicate_json_keys_are_not_silently_overwritten(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"cases": [], "cases": [1]}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        read(path)


def test_continued_images_keep_actual_per_case_source_identity(policy):
    report = fixture_images()
    report["cases"][0]["generator_sha"] = "a" * 40
    report["generator_shas"] = ["a" * 40, "b" * 40]
    result = reconcile(policy, BASELINE, report)
    assert result["generator_shas"] == report["generator_shas"]
    bound = {row["case"]: row for row in result["image_bindings"]}
    assert bound[report["cases"][0]["case"]]["generator_sha"] == "a" * 40
    assert len(bound) == 30


@pytest.mark.parametrize("name", ["lz4", "jackson-core", "jackson-databind"])
def test_requested_replay_missing_original_is_explicit_error(tmp_path, monkeypatch, policy, name):
    missing = f"{name}-advisories.json.gz"
    (policy / "vendor-sources" / missing).unlink()
    image = tmp_path / "images.json"
    image.write_text(json.dumps(fixture_images()))
    output = tmp_path / "incomplete.json"
    monkeypatch.setattr("sys.argv", ["reconcile", "--policy", str(policy),
                                    "--baseline", str(BASELINE), "--packaged-inventories",
                                    str(image), "--output", str(output)])
    assert main() == 2
    result = json.loads(output.read_text())
    assert result["status"] == "incomplete" and result["exit_code"] == 2
    assert result["missing_source"] == missing
    assert "original private source inputs" in result["error"]
    assert not result["release_clearance"]


@pytest.mark.parametrize("mutation", ["omitted", "extra", "invalid", "unsorted", "duplicate"])
def test_continued_images_reject_false_source_sets(mutation):
    report = fixture_images()
    report["cases"][0]["generator_sha"] = "a" * 40
    report["generator_shas"] = ["a" * 40, "b" * 40]
    if mutation == "omitted":
        del report["generator_shas"]
    elif mutation == "extra":
        report["generator_shas"].append("c" * 40)
    elif mutation == "invalid":
        report["cases"][0]["generator_sha"] = "main"
    elif mutation == "unsorted":
        report["generator_shas"].reverse()
    else:
        report["generator_shas"].append("b" * 40)
    with pytest.raises(ValueError, match="generator"):
        bind_images(baseline_inventory(BASELINE)[1], report)
