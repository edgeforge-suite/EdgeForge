#!/usr/bin/env python3
"""Audit finalized promotion facts and emit separate, open owner-decision records.

No generation, Maven execution, network query, sanitizer or final-layout mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def identities(finding):
    return {finding["id"], *finding.get("aliases", [])} | {
        alias for observation in finding.get("observations", [])
        for alias in observation["finding"].get("aliases", [])
    }


def current_dispositions(findings):
    decisions = []
    for finding in findings:
        observations = finding["observations"]
        conflicts = {}
        for field in ("aliases", "advisory_modified", "severity", "severity_vectors", "fixed_versions"):
            values = {json.dumps(o["finding"].get(field), sort_keys=True) for o in observations}
            if len(values) > 1:
                conflicts[field] = [json.loads(value) for value in sorted(values)]
        fixed = sorted({version for o in observations for version in (o["finding"].get("fixed_versions") or [])})
        decisions.append({
            **{key: finding[key] for key in ("coordinate", "version", "id", "scopes", "usages", "impact", "cases")},
            "aliases": sorted({alias for o in observations for alias in o["finding"].get("aliases", [])}),
            "status": "OPEN", "owner": "Engine maintainer", "metadata_conflicts": conflicts,
            "reported_fixed_versions": fixed or None, "version_candidate_attempts": 0,
            "decision": "Retain the proven Boot 4.1.1 managed baseline for this bounded promotion. No compatible remediation candidate was validated; no suppression, unmanaged override, automatic latest patch or risk acceptance.",
            "review_trigger": "Next owner-reviewed same-line Boot BOM patch or upstream advisory change. Require Java 17/21, API, resolved graph, Batch DDL and affected runtime proof. Unknown/no-fix or major-only fixes remain open for an explicit owner decision.",
            "evidence": "Finalized findings.json observations, case assessment-receipt.json and representative assessment/osv.json.gz; actual query dates in baseline.json.",
        })
    return decisions


def historical_dispositions(historical, findings, inventory):
    rows = []
    for old in historical:
        coordinate = old["coordinate"]
        candidates = {coordinate}
        if coordinate in {"com.fasterxml.jackson.core:jackson-core", "com.fasterxml.jackson.core:jackson-databind"}:
            candidates.add(coordinate.replace("com.fasterxml.jackson.core:", "tools.jackson.core:"))
        if coordinate == "org.lz4:lz4-java":
            candidates.add("at.yawk.lz4:lz4-java")
        matches = [f for f in findings if f["coordinate"] in candidates and identities(f) & identities(old)]
        current = [{"coordinate": c, "version": version, "cases": sorted(cases)}
                   for c in sorted(candidates) for version, cases in sorted(inventory.get(c, {}).items())]
        disposition = (
            "OPEN: same advisory or alias reported on current coordinates" if matches else
            "Not reported by current two-pass assessment at listed coordinates; historical old-baseline finding retained" if current else
            "Coordinate absent from current declared graphs; historical old-baseline finding retained"
        )
        rows.append({
            "historical_coordinate": coordinate, "historical_version": old["version"],
            "historical_id": old["id"], "historical_aliases": old.get("aliases", []),
            "historical_scopes": old["scopes"], "historical_cases": old["cases"],
            "current_resolved_coordinates": current,
            "current_advisory_matches": [{"coordinate": f["coordinate"], "version": f["version"], "id": f["id"], "aliases": f.get("aliases", []), "status": "OPEN"} for f in matches],
            "disposition": disposition, "owner": "Engine maintainer",
            "decision": "No old-installation migration or risk acceptance. Absence/non-report is a dated scanner observation, not exploitability or universal fixed status. Cross-namespace family correspondence does not prove advisory-range equivalence.",
            "review_trigger": "A retained old application/coordinate is proposed for use, a current advisory/alias changes, or a compatible managed BOM patch is proposed.",
            "evidence": "Dated 2026-09-13 findings.json plus current finalized baseline.json/findings.json, inventories and validated case-to-graph equivalence.",
        })
    return rows


def resolved_inventory(evidence, baseline):
    inventory = {}
    for graph in baseline["graph_equivalence"]["classes"]:
        records = read(evidence / graph["representative_case"] / "assessment/inventory.json")
        for record in records:
            cases = inventory.setdefault(record["group"]+":"+record["artifact"], {}).setdefault(record["version"], set())
            cases.update(graph["equivalent_cases"])
    return inventory


def runtime_evidence(paths, generator_sha):
    root = Path(__file__).resolve().parents[2]
    generator_tree = subprocess.check_output(["git", "rev-parse", generator_sha+":appbuilder"], cwd=root, text=True).strip()
    result = {}
    for lane, path in paths.items():
        receipt = read(path)
        if receipt["source_dirty"] is not False:
            raise ValueError("runtime receipt has uncommitted sources")
        source_sha = receipt["source_sha"]
        runtime_tree = subprocess.check_output(["git", "rev-parse", source_sha+":appbuilder"], cwd=root, text=True).strip()
        if runtime_tree != generator_tree:
            raise ValueError("runtime generator subtree differs")
        if subprocess.check_output(["git", "diff", source_sha, generator_sha, "--", "scripts/smoke/boot41*"], cwd=root):
            raise ValueError("runtime proof helper changed")
        receipt["raw_receipt_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        for build in receipt["builds"]:
            identity = build.get("dependency_identity")
            if identity and "resolved_tree" in identity:
                tree = identity.pop("resolved_tree")
                records = {}
                def visit(node, records=records):
                    for child in node.get("children", []):
                        key = (child["groupId"], child["artifactId"], child["version"], child.get("scope", ""))
                        records[key] = dict(zip(("group", "artifact", "version", "scope"), key, strict=True))
                        visit(child)
                visit(tree)
                identity["resolved_records"] = [records[key] for key in sorted(records)]
        result[lane] = receipt
    return {"assessment_generator_sha": generator_sha, "appbuilder_tree_at_all_receipt_shas": generator_tree,
            "applicability": "Exact unchanged generator subtree and Boot proof helpers; per-build source/POM/resolved dependency and packaged-library identities retained. Receipt source SHAs remain their actual executed identities.",
            "reused_historical_preview_runtime": False, "runtime": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--historical", required=True, type=Path)
    parser.add_argument("--jobless", required=True, type=Path)
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--kafka", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    evidence, output = args.evidence.resolve(), args.output.resolve()
    if output.exists() or output == evidence or evidence in output.parents:
        raise ValueError("supplement output must be new and outside finalized evidence")
    baseline = read(evidence / "baseline.json")
    if baseline["status"] != "complete" or baseline["coverage_version"] != "2.0":
        raise ValueError("complete promoted baseline required")
    findings = read(evidence / "findings.json")
    old = read(args.historical)
    if len(old) != 110:
        raise ValueError("expected the retained historical 110 matches")
    sha = baseline["engine_sha"]
    mapped = historical_dispositions(old, findings, resolved_inventory(evidence, baseline))
    runtime = runtime_evidence({"jobless": args.jobless, "batch": args.batch, "kafka": args.kafka}, sha)
    output.mkdir(parents=True)
    documents = {
        "finding-dispositions.json": {"generator_sha": sha, "status": "complete assessment; findings open", "findings": current_dispositions(findings)},
        "historical-110-dispositions.json": {"historical_matches": 110, "mapped_matches": len(mapped), "current_generator_sha": sha, "mappings": mapped},
        "runtime-proof.json": runtime,
    }
    for name, value in documents.items():
        (output / name).write_text(json.dumps(value, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"current_decisions": len(findings), "historical_mapped": len(mapped), "runtime_receipts": list(runtime["runtime"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
