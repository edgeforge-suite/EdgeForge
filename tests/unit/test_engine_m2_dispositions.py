"""Offline identity/coverage controls for the compact retained decision record."""
import copy
import json
import sys

import pytest

from scripts import build_engine_m2_dispositions as index


def test_real_index_is_complete_and_reproducible():
    actual = index.build(index.ROOT)
    assert actual == index.build(index.ROOT)
    assert json.loads((index.ROOT / index.OUTPUT).read_bytes()) == actual
    assert actual["current_record_count"] == 622
    assert actual["current_observation_count"] == 22740
    assert actual["historical_counts"]["records"] == 2186
    assert actual["historical_counts"]["observations"] == 64720
    groups = actual["groups"].values()
    assert len({key for group in groups for key in group["component_copy_ids"]}) == 3990
    assert sum(group["current_observations"] for group in groups) == 22740
    assert len(actual["maven"]["historical_mappings"]) == 18
    assert len(actual["maven"]["vendor_observations"]) == 33
    assert sum(row["adopted"] for row in actual["later_vendor_adoptions"]) == 5
    assert len(actual["coverage"]) == 60
    assert actual["risk_accepted"] is actual["m2_complete"] is False


@pytest.mark.parametrize("mutation", [
    "missing-current", "changed-current", "omitted-copy", "extra-copy", "unknown-family",
    "wrong-family-count", "closed-status", "missing-maven", "changed-vendor",
    "missing-adoption", "accepted-risk", "missing-stage",
])
def test_contradictory_or_incomplete_sources_refuse(monkeypatch, mutation):
    sources = {name: copy.deepcopy(index.load(index.ROOT, name)) for name in index.SOURCES}
    accounting = sources["residual-accounting.json.gz"]
    maven = sources["maven-reconciliation.json"]
    if mutation == "missing-current":
        sources["open-findings.json.gz"].pop()
    elif mutation == "changed-current":
        sources["open-findings.json.gz"][0]["finding"]["version"] = "different"
    elif mutation == "omitted-copy":
        accounting["records"][0]["component_copy_keys"].append("COPY-missing")
    elif mutation == "extra-copy":
        accounting["component_copies"]["COPY-extra"] = {}
    elif mutation == "unknown-family":
        accounting["records"][0]["family"] = "NEW_UNASSESSED"
    elif mutation == "wrong-family-count":
        accounting["historical_counts"]["families"]["BUILD_OS"]["records"] += 1
    elif mutation == "closed-status":
        accounting["current_findings"][0]["status"] = "CLOSED"
    elif mutation == "missing-maven":
        maven["historical_mappings"].pop()
    elif mutation == "changed-vendor":
        next(r for r in maven["vendor_observations"] if r["status"] == "OPEN")["id"] = "GHSA-other"
    elif mutation == "missing-adoption":
        sources["residual-applicability-adoption.json.gz"]["rows"].pop()
    elif mutation == "accepted-risk":
        accounting["risk_accepted"] = True
    else:
        accounting["stages"].pop(next(iter(accounting["stages"])))
    monkeypatch.setattr(index, "load", lambda root, name: sources[name])
    with pytest.raises((ValueError, KeyError)):
        index.build(index.ROOT)


def test_missing_inputs_exit_two_not_findings_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["index", "--root", str(tmp_path), "--check"])
    assert index.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "incomplete"


def test_check_does_not_modify_output(monkeypatch):
    path = index.ROOT / index.OUTPUT
    before = path.read_bytes(), path.stat().st_mtime_ns
    monkeypatch.setattr(sys, "argv", ["index", "--check"])
    assert index.main() == 0
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
