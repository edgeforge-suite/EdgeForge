#!/usr/bin/env python3
"""Derive the compact Engine M2 decision index from unchanged retained ledgers.

Offline only. This neither rescans nor accepts risk. Exit 2 means invalid input
or a stale output; exit 0 means the projection matches its declared sources.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .verify_generated_image_evidence_split import verify
except ImportError:
    from verify_generated_image_evidence_split import verify

ROOT = Path(__file__).resolve().parents[1]
D = "docs/handover-evidence/generated-images/2026-10-20-noble"
OUTPUT = "docs/handover-evidence/engine-m2-dispositions.json"
SOURCES = ("open-findings.json.gz", "residual-accounting.json.gz",
           "maven-reconciliation.json", "residual-applicability-adoption.json.gz", "summary.json")


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def load(root, name):
    raw = (root / D / name).read_bytes()
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)


def build(root):
    ledgers = {name: load(root, name) for name in SOURCES}
    current, accounting, maven, adoption = (ledgers[name] for name in SOURCES[:4])
    require(isinstance(current, list) and current, "missing current findings")
    require(len(current) == ledgers["summary.json"]["distinct_finding_records"], "normalized record count differs")
    require(accounting["risk_accepted"] is False and maven["risk_accepted"] is False
            and adoption["risk_accepted"] is False, "source risk acceptance changed")
    groups = defaultdict(lambda: {"historical_record_ids": [], "component_copy_ids": set(),
                                  "current_ledger_indices": [], "current_observations": 0})
    historical_ids = set()
    for row in accounting["records"]:
        family = row["family"]
        require(family in {"BUILD_MAVEN", "BUILD_JDK", "BUILD_OS", "FINAL_OS", "FINAL_GO_PEBBLE"},
                "unknown historical family")
        require(row["id"] not in historical_ids and row["status"] == "OPEN", "historical identity/status changed")
        historical_ids.add(row["id"])
        group = groups["HISTORY_" + family]
        group["historical_record_ids"].append(row["id"])
        group["component_copy_ids"].update(row["component_copy_keys"])
    copies = set().union(*(row["component_copy_ids"] for row in groups.values()))
    require(copies == set(accounting["component_copies"]), "unmapped physical copies")
    for group in groups.values():
        require(all(key in accounting["component_copies"] for key in group["component_copy_ids"]), "unknown copy")
    counts = accounting["historical_counts"]
    require(len(historical_ids) == counts["records"] and len(copies) == counts["copies"]
            and sum(row["observations"] for row in accounting["records"]) == counts["observations"],
            "historical totals disagree")
    observed_families = {family: {"records": sum(r["family"] == family for r in accounting["records"]),
        "observations": sum(r["observations"] for r in accounting["records"] if r["family"] == family)}
        for family in counts["families"]}
    require(observed_families == counts["families"], "historical family totals disagree")
    current_members = []
    expected_observations = Counter()
    for index, row in enumerate(current):
        require(row["disposition"].startswith("OPEN;"), "current disposition changed")
        finding = row["finding"]
        require(finding["scanner"] in {"grype", "trivy"}, "unsupported scanner")
        fingerprint = sha(canonical(finding))
        assignment = Counter()
        for observation in row["observations"]:
            stage, case = observation["stage"], observation["case"]
            require(stage in {"generated-build-stage", "generated-final-image"}, "unknown image stage")
            if finding["type"] in {"deb", "ubuntu"}:
                group_id = "CURRENT_BUILD_OS" if stage == "generated-build-stage" else "CURRENT_FINAL_OS"
            else:
                require(stage == "generated-build-stage" and finding["name"] in {
                            "plexus-utils", "org.codehaus.plexus:plexus-utils"}
                        and finding["version"] == "4.0.2" and finding["type"] in {"jar", "java-archive"},
                        "new non-OS family requires an explicit decision")
                group_id = "CURRENT_CLEAN_PLUGIN_PLEXUS"
            assignment[group_id] += 1
            expected_observations[case, stage, fingerprint] += 1
        require(assignment, "empty finding observations")
        for group_id, count in sorted(assignment.items()):
            groups[group_id]["current_ledger_indices"].append(index)
            groups[group_id]["current_observations"] += count
        current_members.append({"ledger_index": index, "finding_sha256": fingerprint,
                                "decisions": dict(sorted(assignment.items()))})
    actual = Counter((row["case"], row["stage"], row["finding_sha256_canonical"])
                     for row in accounting["current_findings"])
    require(actual == expected_observations, "current observation identities disagree")
    require(all(row["status"] == "OPEN" for row in accounting["current_findings"]), "current observation status changed")
    require(sum(expected_observations.values()) == accounting["current_counts"]["findings"], "current totals disagree")
    normalized_groups = {}
    for key, value in sorted(groups.items()):
        normalized_groups[key] = {**value,
            "historical_record_ids": sorted(value["historical_record_ids"]),
            "component_copy_ids": sorted(value["component_copy_ids"]),
            "decision_ref": "engine-m2-closeout-decisions.md#" + key.lower().replace("_", "-")}
    maven_members = {}
    for name in ("historical_mappings", "vendor_observations"):
        rows = []
        for index, row in enumerate(maven[name]):
            require(row["risk_accepted"] is False and row["status"] in {
                "REMEDIATED_VERSION", "SUPPORTED_VERSION_DISPOSITION", "OPEN"}, "invalid Maven disposition")
            rows.append({"source_index": index, "id": row["id"], "source_row_sha256": sha(canonical(row)),
                         "retained_status": row["status"],
                         "decision": "SUPPORTED_DATED_TECHNICAL_DISPOSITION" if row["status"] != "OPEN" else "OPEN_VENDOR",
                         "source_pointer": "/" + name + "/" + str(index)})
        maven_members[name] = rows
    require(Counter(r["status"] for r in maven["historical_mappings"]) == maven["counts"]["historical"]
            and Counter(r["status"] for r in maven["vendor_observations"]) == maven["counts"]["vendor"],
            "Maven totals disagree")
    adoptions = [{"id": row["id"], "source_index": i, "adopted": row["adopted"],
                  "source_row_sha256": sha(canonical(row)),
                  "decision": "SUPPORTED_LZ4_VERSION_APPLICABILITY" if row["adopted"] else "OPEN_JACKSON_CONFLICT"}
                 for i, row in enumerate(adoption["rows"])]
    require(sum(row["adopted"] for row in adoptions) == adoption["technical_adoptions"], "adoption totals disagree")
    require({r["id"] for r in adoptions} == {r["id"] for r in maven["vendor_observations"] if r["status"] == "OPEN"},
            "vendor follow-up identity set differs")
    coverage = [{"stage_key": key, "classifier_inventory_required": row["classifier_inventory_required"],
        "image_identity": {name: row["image"][name] for name in (
            "image_id", "config_sha256", "configuration_sha256", "jar_sha256", "platform")},
        "full_image_binding_sha256": sha(canonical(row["image"])),
        "native_evidence": row["evidence"]["native-members"],
        "gap_sets": {name: {"sha256": sha(canonical(gap)), "status": gap["status"],
                            "record_count": len(gap["records"])}
                     for name, gap in sorted(row["assessment_gaps"].items())},
        "decision_ref": "engine-m2-closeout-decisions.md#coverage-and-owner-decisions"}
        for key, row in sorted(accounting["stages"].items())]
    require(len(coverage) == accounting["current_counts"]["stages"], "stage coverage missing")
    return {"schema_version": "engine-m2-decision-index-1", "source_base_sha": "ca53afb40ac9ba67d74f9d27c2d52e63b909970c",
            "assessed_generator_sha": accounting["source_sha"], "risk_accepted": False, "m2_complete": False,
            "sources": {D + "/" + name: {"sha256": sha((root / D / name).read_bytes())} for name in SOURCES},
            "source_resolution": "Indices and JSON pointers resolve only against the hash-bound unchanged source; not fresh advisories.",
            "groups": normalized_groups, "current_records": current_members,
            "historical_counts": counts, "current_record_count": len(current),
            "current_observation_count": sum(expected_observations.values()),
            "maven": maven_members, "later_vendor_adoptions": adoptions,
            "coverage": coverage,
            "copy_detail": "Every COPY ID resolves to the same retained accounting component_copies entry, including case/stage/path/config/candidate IDs/status/gaps. Full introducing-edge detail needs the private archive.",
            "group_counting": "Current OS records may belong to build and runtime groups; observation assignments are disjoint. Do not sum overlapping group record counts."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        verify(args.root, args.root / (D + "-core-manifest.json"), evidence_dir=D)
        raw = json.dumps(build(args.root), indent=2, sort_keys=True).encode() + b"\n"
        path = args.root / OUTPUT
        if args.check:
            require(path.read_bytes() == raw, "decision index differs from retained sources")
        else:
            path.write_bytes(raw)
        print(json.dumps({"status": "verified" if args.check else "written", "risk_accepted": False, "m2_complete": False}))
        return 0
    except Exception:
        print(json.dumps({"status": "incomplete", "reason": "invalid source, missing identity or stale index"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
