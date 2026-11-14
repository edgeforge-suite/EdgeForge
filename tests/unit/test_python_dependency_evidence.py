from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import generate_python_dependency_evidence as evidence
from scripts import python_dependency_audit as audit
from scripts.python_dependency_audit import AuditError

ROOT = Path(__file__).resolve().parents[2]


def assert_committed_reference_evidence(root: Path, evidence_dir: Path | None = None) -> None:
    if evidence_dir is None:
        evidence_dir = root / "docs/handover-evidence/python-current"
    requirements_path = root / "requirements.txt"
    lock_path = root / "requirements-lock.txt"
    provenance = json.loads((evidence_dir / "provenance.json").read_text(encoding="utf-8"))
    lock = audit.parse_lock(lock_path.read_text(encoding="utf-8"))
    direct = evidence.direct_dependencies(requirements_path)

    assert provenance["schema_version"] == "1.0"
    assert provenance["requirements_sha256"] == evidence.digest(requirements_path)
    assert provenance["lock_sha256"] == evidence.digest(lock_path)
    assert provenance["dependency_count"] == len(lock)

    sbom = evidence.validate_sbom(evidence_dir / "sbom.cdx.json", lock)
    assert provenance["sbom_component_count"] == len(sbom["components"])

    with (evidence_dir / "dependency-licenses.csv").open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ["Name", "Version", "License", "Scope"]
        licenses = list(reader)
    assert audit.inventory([
        {"name": row["Name"], "version": row["Version"]} for row in licenses
    ]) == lock
    assert provenance["license_row_count"] == len(licenses)
    for row in licenses:
        assert row["License"]
        assert row["Scope"] == ("direct" if audit.normalize(row["Name"]) in direct else "transitive")

    report = json.loads((evidence_dir / "pip-audit.json").read_text(encoding="utf-8"))
    assert audit.inventory(report["dependencies"], report=True) == lock
    assert provenance["audit_dependency_count"] == len(report["dependencies"])
    installed = [{"name": name, "version": version} for name, version in lock.items()]
    assert provenance["finding_count"] == audit.validate(
        installed, lock, report, provenance["audit_exit_code"]
    )


def test_committed_reference_evidence_matches_lock_and_provenance() -> None:
    assert_committed_reference_evidence(ROOT)


@pytest.mark.parametrize(
    "snapshot",
    sorted((ROOT / "docs/handover-evidence/python-current/history").glob("????-??-??")),
    ids=lambda snapshot: snapshot.name,
)
def test_dated_reference_evidence_matches_its_original_declarations(snapshot: Path) -> None:
    assert_committed_reference_evidence(snapshot, snapshot)


def test_correction_receipt_matches_dated_and_historical_evidence() -> None:
    directory = ROOT / "docs/handover-evidence"
    receipt = json.loads((directory / "python-audit-correction-2026-10-20.json").read_text())
    history = directory / "python-current/history"
    corrected = history / "2026-10-20"
    provenance = json.loads((corrected / "provenance.json").read_text())
    historical = json.loads((history / "2026-09-23/provenance.json").read_text())
    assert receipt["corrected_source_sha"] == provenance["engine_source_sha"]
    assert receipt["before"]["lock_sha256"] == historical["lock_sha256"]
    assert receipt["after"]["detailed_report_sha256"] == evidence.digest(corrected / "pip-audit.json")
    for field in (
        "assessment_time_utc", "requirements_sha256", "lock_sha256",
        "audit_dependency_count", "sbom_component_count", "license_row_count",
        "finding_count", "audit_exit_code",
    ):
        assert receipt["after"][field] == provenance[field]
    old_lock = audit.parse_lock((history / "2026-09-23/requirements-lock.txt").read_text())
    new_lock = audit.parse_lock((corrected / "requirements-lock.txt").read_text())
    correction = receipt["correction"]
    assert old_lock[correction["package"]] == correction["previous_version"]
    assert new_lock[correction["package"]] == correction["selected_version"]


def test_october25_correction_receipt_matches_its_preserved_snapshot() -> None:
    directory = ROOT / "docs/handover-evidence"
    receipt = json.loads((directory / "python-audit-correction-2026-10-25.json").read_text())
    current = directory / "python-current/history/2026-10-25"
    provenance = json.loads((current / "provenance.json").read_text())
    assert receipt["corrected_source_sha"] == provenance["engine_source_sha"]
    for field, value in provenance.items():
        assert receipt["after"][field] == value
    for name, expected in receipt["current_evidence_sha256"].items():
        assert evidence.digest(current / name) == expected
    for name, expected in receipt["historical_snapshot_sha256"].items():
        assert evidence.digest(current.parent / "2026-10-20" / name) == expected
    old = audit.parse_lock((current.parent / "2026-10-20/requirements-lock.txt").read_text())
    selected = audit.parse_lock((current / "requirements-lock.txt").read_text())
    for correction in receipt["corrections"]:
        assert old[correction["package"]] == correction["previous_version"]
        assert selected[correction["package"]] == correction["selected_version"]
    assert receipt["before"]["audit_dependency_count"] == len(old)
    assert receipt["after"]["audit_dependency_count"] == len(selected)
    assert receipt["proof_carryforward"]["before_sha256"] == receipt["proof_carryforward"]["after_sha256"]
    assert receipt["risk_accepted"] is False
    assert receipt["m2_complete"] is False


def test_october29_correction_preserves_two_pin_scope_and_evidence_bindings() -> None:
    directory = ROOT / "docs/handover-evidence"
    current = directory / "python-current/history/2026-10-29"
    history = current.parent / "2026-10-25"
    receipt = json.loads((directory / "python-audit-correction-2026-10-29.json").read_text())
    provenance = json.loads((current / "provenance.json").read_text())
    assert receipt["after"] == provenance
    assert receipt["corrected_source_sha"] == provenance["engine_source_sha"]
    for name, expected in receipt["current_evidence_sha256"].items():
        assert evidence.digest(current / name) == expected
    for name, expected in receipt["historical_snapshot_sha256"].items():
        assert evidence.digest(history / name) == expected
    old = audit.parse_lock((history / "requirements-lock.txt").read_text())
    selected = audit.parse_lock((current / "requirements-lock.txt").read_text())
    assert old.keys() == selected.keys()
    assert {name for name in old if old[name] != selected[name]} == {"authlib", "dnspython"}
    for correction in receipt["corrections"]:
        assert old[correction["package"]] == correction["previous_version"]
        assert selected[correction["package"]] == correction["selected_version"]
    assert {row["id"] for row in receipt["advisories"]} == {
        "GHSA-6v38-4h7w-rj9h", "GHSA-7vr2-2fgp-9w7p", "GHSA-8m4g-j4wp-wgcg",
        "GHSA-c5mf-xmp2-59rc", "GHSA-fch4-3c6x-j4gc", "GHSA-x4rv-c3wx-4cr8",
        "GHSA-45c3-73f7-pv4m",
    }
    assert receipt["support"]["requires_python"] == ">=3.11"
    assert receipt["baseline"]["findings"] == 7
    assert provenance["finding_count"] == 0
    assert provenance["audit_exit_code"] == 0
    assert receipt["risk_accepted"] is receipt["m2_complete"] is False


def test_november02_joserfc_correction_preserves_single_pin_and_evidence() -> None:
    directory = ROOT / "docs/handover-evidence"
    current = directory / "python-current/history/2026-11-02"
    previous = current.parent / "2026-10-29"
    receipt = json.loads((directory / "python-audit-correction-2026-11-02.json").read_text())
    provenance = json.loads((current / "provenance.json").read_text())
    assert receipt["after"] == provenance
    assert receipt["corrected_source_sha"] == provenance["engine_source_sha"]
    old = audit.parse_lock((previous / "requirements-lock.txt").read_text())
    selected = audit.parse_lock((current / "requirements-lock.txt").read_text())
    assert old.keys() == selected.keys()
    assert {name for name in old if old[name] != selected[name]} == {"joserfc"}
    assert old["joserfc"] == "1.7.5" and selected["joserfc"] == "1.7.6"
    assert (previous / "requirements.txt").read_bytes() == (current / "requirements.txt").read_bytes()
    for name, expected in receipt["current_evidence_sha256"].items():
        assert evidence.digest(current / name) == expected
    for name, expected in receipt["historical_snapshot_sha256"].items():
        assert evidence.digest(previous / name) == expected
    assert receipt["advisory"]["id"] == "GHSA-9pg5-8c7x-5hfx"
    assert receipt["advisory"]["reviewed_range"] == "< 1.7.6"
    assert receipt["advisory"]["repository_patch_claim"] == "1.7.5"
    assert receipt["qualification"]["candidates_evaluated"] == ["1.7.6"]
    assert provenance["finding_count"] == 0 and provenance["audit_exit_code"] == 0
    assert receipt["proof_carryforward"]["product_and_example_bytes_unchanged"]
    assert receipt["risk_accepted"] is receipt["m2_complete"] is False


@pytest.mark.parametrize("mutation", ["lock_hash", "requirements_hash", "sbom", "audit", "licenses"])
def test_committed_reference_evidence_rejects_drift(tmp_path: Path, mutation: str) -> None:
    source = ROOT / "docs/handover-evidence/python-current"
    target = tmp_path / "docs/handover-evidence/python-current"
    target.parent.mkdir(parents=True)
    shutil.copytree(source, target)
    shutil.copyfile(ROOT / "requirements.txt", tmp_path / "requirements.txt")
    shutil.copyfile(ROOT / "requirements-lock.txt", tmp_path / "requirements-lock.txt")

    if mutation in {"lock_hash", "requirements_hash"}:
        path = target / "provenance.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data[f"{mutation.removesuffix('_hash')}_sha256"] = "0" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
    elif mutation in {"sbom", "audit"}:
        path = target / ("sbom.cdx.json" if mutation == "sbom" else "pip-audit.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["components"] if mutation == "sbom" else data["dependencies"]
        rows[0]["version"] = "0"
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        path = target / "dependency-licenses.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fieldnames = reader.fieldnames
            rows = list(reader)
        rows[0]["Version"] = "0"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    with pytest.raises((AssertionError, AuditError)):
        assert_committed_reference_evidence(tmp_path)


def test_legacy_evidence_command_refuses_without_writing(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    legacy = scripts / "generate-dependency-evidence.sh"
    shutil.copyfile(ROOT / "scripts/generate-dependency-evidence.sh", legacy)
    lock = tmp_path / "requirements-lock.txt"
    lock.write_text("unchanged\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(legacy)], cwd=tmp_path, capture_output=True, text=True, timeout=5
    )

    assert result.returncode == 2
    assert "disabled" in result.stderr
    assert lock.read_text(encoding="utf-8") == "unchanged\n"


def test_license_inventory_covers_lock() -> None:
    payload = json.dumps([
        {"Name": "One", "Version": "1.0", "License": "MIT"},
        {"Name": "Two", "Version": "2.0", "License": "UNKNOWN"},
    ])
    csv_data, table, flagged = evidence.validate_licenses(
        payload, {"one": "1.0", "two": "2.0"}, {"one"}
    )
    assert "One,1.0,MIT,direct" in csv_data
    assert "Two,2.0,UNKNOWN,transitive" in csv_data
    assert "`Two`" in table
    assert flagged == 1


@pytest.mark.parametrize(
    "rows",
    [
        [{"Name": "One", "Version": "1.0", "License": "MIT"}],
        [{"Name": "One", "Version": "9.0", "License": "MIT"}, {"Name": "Two", "Version": "2.0", "License": "MIT"}],
        [{"Name": "One", "Version": "1.0", "License": "MIT"}, {"Name": "One", "Version": "1.0", "License": "MIT"}],
        [{"Name": "One", "Version": "1.0", "License": "MIT"}, {"Name": "Two", "Version": "2.0"}],
    ],
)
def test_license_inventory_rejects_incomplete_rows(rows: list[dict[str, str]]) -> None:
    with pytest.raises(AuditError):
        evidence.validate_licenses(json.dumps(rows), {"one": "1.0", "two": "2.0"}, set())


def test_sbom_inventory_rejects_missing_component(tmp_path: Path) -> None:
    sbom = {"bomFormat": "CycloneDX", "components": [
        {"name": "one", "version": "1.0", "purl": "pkg:pypi/one@1.0"}
    ]}
    path = tmp_path / "sbom.json"
    path.write_text(json.dumps(sbom), encoding="utf-8")
    with pytest.raises(AuditError, match="coverage"):
        evidence.validate_sbom(path, {"one": "1.0", "two": "2.0"})


def test_reference_direct_requirements_are_exact(tmp_path: Path) -> None:
    path = tmp_path / "requirements.txt"
    path.write_text("One==1.0\nTwo>=2.0\n", encoding="utf-8")
    with pytest.raises(AuditError, match="not exactly pinned"):
        evidence.direct_dependencies(path)
