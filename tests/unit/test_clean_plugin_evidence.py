"""Offline consistency checks; raw archive and external truth are separate proof."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "docs/handover-evidence/clean-plugin-plexus-2026-10-24"


def load(name):
    return json.loads((CORE / name).read_text())


def test_compact_core_has_exact_members_and_hashes():
    manifest = load("core-manifest.json")
    rows = manifest["files"]
    assert len({row["path"] for row in rows}) == len(rows)
    assert {path.name for path in CORE.iterdir()} == {
        "core-manifest.json", *(row["path"] for row in rows)
    }
    for row in rows:
        assert Path(row["path"]).name == row["path"]
        raw = (CORE / row["path"]).read_bytes()
        assert len(raw) == row["bytes"]
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]


def test_overlay_counts_and_test_origins_reconcile():
    summary = load("summary.json")
    cases = summary["cases"]
    proof = summary["separate_manual_compatibility"]
    assert summary["scope"]["artifact_assessments"] == len(cases)
    assert proof["cases"] == len(cases)
    assert proof["executed_tests"] == sum(
        row["separate_clean_verify"]["executed_tests"] for row in cases
    )
    for origin, key in (("engine-emitted", "engine_emitted_tests"),
                        ("proof-supplied", "proof_supplied_tests")):
        assert proof[key] == sum(row["separate_clean_verify"]["executed_tests"]
                                 for row in cases
                                 if row["separate_clean_verify"]["test_origin"] == origin)
    assert summary["image_build"]["executed_test_credit"] == 0
    assert summary["findings_accounting"]["summed_image_observations"] == sum(
        row["normalized_finding_observations"] for row in cases
    )
    assert all(row["assessment_exit_code"] == 1
               and row["assessment_status"] == "complete-with-findings" for row in cases)


def test_archive_binding_and_historical_sources_are_explicit():
    summary = load("summary.json")
    archive = load("archive-bindings.json")
    assert summary["archive"]["private_archive"] == archive["archive"]
    assert hashlib.sha256((CORE / "archive-bindings.json").read_bytes()).hexdigest() == (
        summary["archive"]["descriptor_sha256"]
    )
    assert archive["generator_sha"] == summary["generator_sha"]
    for path, expected in summary["historical_target"]["source_ledger_sha256_unchanged"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert summary["risk_accepted"] is False
    assert summary["m2_complete"] is False
    assert summary["release_clearance"] is False
    assert summary["findings_accounting"]["all_non_target_findings_retained_open"] is True
