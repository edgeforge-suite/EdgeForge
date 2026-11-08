#!/usr/bin/env python3
"""Validate raw generated-Maven evidence and write its reduced durable layout."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.assess_generated_maven import (  # noqa: E402
    PINS_PATH,
    SCOPES,
    AssessmentError,
    check_scanner,
    compare_sbom,
    inventory_digest,
    read_json,
    require,
)
from scripts.collect_generated_maven_baseline import aggregate_findings  # noqa: E402

NORMALIZATION = {
    "version": "1.0",
    "canonical_json": "UTF-8 JSON with sorted keys and compact separators",
    "graph_includes": [
        "complete normalized Maven dependency tree",
        "CycloneDX format/version/serial number and root/component PURLs",
        "CycloneDX dependency relationships",
        "complete normalized inventory records",
    ],
    "graph_excludes": ["CycloneDX metadata.timestamp"],
    "graph_non_identity_fields_not_included": [
        "CycloneDX metadata tools and annotations",
        "CycloneDX component hashes and descriptive annotations",
    ],
    "machine_evidence_includes": [
        "assessment.json",
        "bom.json",
        "maven-tree.json",
        "inventory.json",
        "findings.json",
        "osv.json",
    ],
    "machine_evidence_excludes": [
        "assessment.json assessment_time_utc",
        "bom.json metadata.timestamp",
    ],
    "finding_identity_fields": ["coordinate", "version", "id"],
}

GRAPH_CLASSES = (
    {
        "representative_case": "crud-h2-j17",
        "equivalent_cases": ("crud-h2-j17",),
        "dependency_distinctions": {
            "archetype": "crud",
            "database_driver": "h2",
            "soap_dependencies": False,
            "kafka_router_dependencies": False,
        },
    },
    {
        "representative_case": "crud-pg-j17",
        "equivalent_cases": ("crud-pg-j17", "crud-pg-j21"),
        "dependency_distinctions": {
            "archetype": "crud",
            "database_driver": "postgresql",
            "soap_dependencies": False,
            "kafka_router_dependencies": False,
        },
    },
    {
        "representative_case": "crud-soap-h2-j17",
        "equivalent_cases": ("crud-soap-h2-j17",),
        "dependency_distinctions": {
            "archetype": "crud",
            "database_driver": "h2",
            "soap_dependencies": True,
            "kafka_router_dependencies": False,
        },
    },
    {
        "representative_case": "crud-soap-pg-j17",
        "equivalent_cases": ("crud-soap-pg-j17", "crud-soap-pg-j21"),
        "dependency_distinctions": {
            "archetype": "crud",
            "database_driver": "postgresql",
            "soap_dependencies": True,
            "kafka_router_dependencies": False,
        },
    },
    {
        "representative_case": "kafka-h2-j17",
        "equivalent_cases": ("kafka-h2-j17", "kafka-pg-j17", "kafka-pg-j21"),
        "dependency_distinctions": {
            "archetype": "kafka-integration",
            "database_driver": "none",
            "soap_dependencies": False,
            "kafka_router_dependencies": False,
        },
    },
    {
        "representative_case": "kafka-router-h2-j17",
        "equivalent_cases": (
            "kafka-router-h2-j17",
            "kafka-router-pg-j17",
            "kafka-router-pg-j21",
        ),
        "dependency_distinctions": {
            "archetype": "kafka-integration",
            "database_driver": "none",
            "soap_dependencies": False,
            "kafka_router_dependencies": True,
        },
    },
    {
        "representative_case": "passthrough-h2-j17",
        "equivalent_cases": (
            "passthrough-h2-j17",
            "passthrough-pg-j17",
            "passthrough-pg-j21",
        ),
        "dependency_distinctions": {
            "archetype": "passthrough-router",
            "database_driver": "none",
            "soap_dependencies": False,
            "kafka_router_dependencies": False,
        },
    },
)

CASE_FILES = (
    "build.log",
    "generation.json",
    "input-files.json",
    "packaged-independence.json",
    "provenance.json",
    "source-files.json",
    "source-independence.json",
)
FULL_ASSESSMENT_FILES = (
    "assessment.json",
    "bom.json",
    "findings.json",
    "inventory.json",
    "maven-tree.json",
    "maven.log",
    "scanner.log",
    "summary.md",
)
PROVENANCE_FIELDS = {
    "engine_sha",
    "input_package_sha256",
    "input_manifest",
    "generation_run_id",
    "target_profile",
    "archetype",
    "generation_input",
}
INDEPENDENCE_FIELDS = {
    "status",
    "package",
    "checks",
    "baseline_generated_source_count",
    "packaged_jar",
}
INDEPENDENCE_CHECKS = {
    "repository-boundary",
    "java-imports",
    "maven-boundary",
    "schema-baseline",
    "repository-hygiene",
    "author-paths",
    "packaged-jar",
}
GENERATION_RECEIPT_FIELDS = {"generation_run_id", "warnings", "harness"}
PATH_PATTERN = re.compile(
    r"(?:/"
    r"Users/|/home/|/private/(?:tmp|var)/|/tmp/|(?<![A-Za-z0-9])[A-Z]:[\\/]+Users[\\/]+|\\{2,}[^\\/\s]+[\\/]+[^\\/\s]+)",
    re.IGNORECASE,
)


def canonical_digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def finding_identities(findings):
    require(isinstance(findings, list), "malformed findings")
    identities = [
        {field: finding[field] for field in NORMALIZATION["finding_identity_fields"]}
        for finding in findings
    ]
    return sorted(
        identities,
        key=lambda row: tuple(row[field] for field in NORMALIZATION["finding_identity_fields"]),
    )


def normalized_maven_node(node):
    require(isinstance(node, dict), "malformed Maven dependency tree")
    normalized = {
        key: node[key]
        for key in ("groupId", "artifactId", "version", "type", "classifier", "scope", "optional")
        if key in node
    }
    children = [normalized_maven_node(child) for child in node.get("children", [])]
    normalized["children"] = sorted(children, key=lambda child: json.dumps(child, sort_keys=True))
    return normalized


def normalized_graph(tree, bom, inventory):
    component_refs = sorted(component["purl"] for component in bom.get("components", []))
    dependencies = sorted(
        (
            {"ref": item["ref"], "dependsOn": sorted(item.get("dependsOn", []))}
            for item in bom.get("dependencies", [])
        ),
        key=lambda item: item["ref"],
    )
    return {
        "normalization_version": NORMALIZATION["version"],
        "maven_tree": normalized_maven_node(tree),
        "cyclonedx_graph": {
            "bom_format": bom["bomFormat"],
            "spec_version": bom["specVersion"],
            "serial_number": bom.get("serialNumber"),
            "root_purl": bom["metadata"]["component"]["purl"],
            "component_purls": component_refs,
            "dependencies": dependencies,
        },
        "inventory": sorted(inventory, key=lambda item: item["purl"]),
    }


def normalized_machine_evidence(report, tree, bom, inventory, findings, osv):
    report = copy.deepcopy(report)
    bom = copy.deepcopy(bom)
    report.pop("assessment_time_utc", None)
    bom.get("metadata", {}).pop("timestamp", None)
    return {
        "normalization_version": NORMALIZATION["version"],
        "assessment": report,
        "bom": bom,
        "maven_tree": tree,
        "inventory": inventory,
        "findings": findings,
        "osv": osv,
    }


def validate_run(run_dir, pins):
    report = read_json(run_dir / "assessment.json")
    tree = read_json(run_dir / "maven-tree.json")
    bom = read_json(run_dir / "bom.json")
    inventory = read_json(run_dir / "inventory.json")
    findings = read_json(run_dir / "findings.json")
    osv = read_json(run_dir / "osv.json")
    require(report.get("status") == "complete", "incomplete assessment cannot be finalized")
    require(report.get("exit_code") in (0, 1), "invalid assessment exit")
    records = compare_sbom(tree, bom, pins)
    normalized_inventory = sorted(records.values(), key=lambda item: item["purl"])
    require(normalized_inventory == inventory, "retained normalized inventory differs")
    require(
        inventory_digest(inventory) == report.get("inventory_sha256"),
        "retained inventory digest differs",
    )
    normalized_findings = check_scanner(osv, records, report.get("scanner_exit_code"))
    require(normalized_findings == findings, "retained normalized findings differ")
    require(len(findings) == report.get("findings"), "retained finding count differs")
    require(
        report.get("exit_code") == (1 if findings else 0),
        "assessment exit and findings disagree",
    )
    require(report.get("inventory_coverage") == "complete", "assessment coverage is incomplete")
    require(report.get("resolved_artifacts") == len(records), "resolved artifact count differs")
    scanned_packages = len({(key[0], key[1], key[2]) for key in records})
    require(
        report.get("scanned_maven_packages") == scanned_packages,
        "scanned package count differs",
    )
    require(
        report.get("affected_packages") == len({item["coordinate"] for item in findings}),
        "affected package count differs",
    )
    require(report.get("scopes") == sorted(SCOPES), "assessment scopes are incomplete")
    before = report.get("source_before_sha256")
    after = report.get("source_after_sha256")
    require(
        report.get("source_unchanged") is True
        and isinstance(before, str)
        and re.fullmatch(r"[0-9a-f]{64}", before) is not None
        and before == after,
        "assessment source hashes do not prove unchanged source",
    )
    require(
        report.get("release_acceptance") == "not established",
        "assessment must not claim release acceptance",
    )
    graph = normalized_graph(tree, bom, inventory)
    identities = finding_identities(findings)
    machine = normalized_machine_evidence(report, tree, bom, inventory, findings, osv)
    return {
        "report": report,
        "bom_timestamp_utc": bom.get("metadata", {}).get("timestamp"),
        "graph_sha256": canonical_digest(graph),
        "inventory_sha256": canonical_digest(inventory),
        "finding_identities_sha256": canonical_digest(identities),
        "normalized_machine_evidence_sha256": canonical_digest(machine),
        "findings": findings,
    }


def retained_file_hashes(path, label):
    rows = read_json(path)
    require(isinstance(rows, list) and rows, f"{label} inventory is empty")
    inventory = {}
    for row in rows:
        require(
            isinstance(row, dict)
            and set(row) == {"path", "sha256"}
            and isinstance(row["path"], str)
            and row["path"]
            and not row["path"].startswith("/")
            and ".." not in row["path"].split("/")
            and isinstance(row["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is not None,
            f"malformed {label} inventory",
        )
        require(row["path"] not in inventory, f"duplicate {label} inventory path")
        inventory[row["path"]] = row["sha256"]
    return inventory


def retained_source_hashes(path):
    inventory = retained_file_hashes(path, "case source")
    require("pom.xml" in inventory, "case source inventory has no POM")
    return inventory_digest(inventory), inventory["pom.xml"]


def validate_case_finding_counts(raw_case, case, validated, *, legacy_counts):
    first_count = validated["assessment"]["report"]["findings"]
    repeat_count = validated["repeat"]["report"]["findings"]
    if legacy_counts:
        require(
            raw_case.get("findings") == first_count,
            "legacy raw case and first assessment finding counts differ",
        )
        return
    require(
        raw_case.get("assessment_findings") == first_count,
        "raw case and first assessment finding counts differ",
    )
    require(
        raw_case.get("repeat_findings") == repeat_count,
        "raw case and repeat assessment finding counts differ",
    )
    require(
        raw_case.get("findings") == case["findings"],
        "raw case distinct finding union differs",
    )


def validate_generation_receipt(path, case, provenance):
    value = read_json(path)
    require(
        isinstance(value, dict) and set(value) == GENERATION_RECEIPT_FIELDS,
        "malformed generation receipt",
    )
    require(
        value.get("generation_run_id") == provenance.get("generation_run_id"),
        "retained generation receipt differs from provenance",
    )
    warnings = value.get("warnings")
    require(
        isinstance(warnings, list) and all(isinstance(item, str) for item in warnings),
        "malformed generation warnings",
    )
    expected_harness = "passed" if case.get("archetype") == "crud" else "not applicable"
    require(value.get("harness") == expected_harness, "generation harness receipt differs")


def validate_retained_provenance(case_dir, case, validated, engine_sha):
    path = case_dir / "provenance.json"
    value = read_json(path)
    require(isinstance(value, dict) and set(value) == PROVENANCE_FIELDS, "malformed provenance")
    require(
        value == validated["assessment"]["report"].get("provenance")
        and value == validated["repeat"]["report"].get("provenance"),
        "retained provenance differs from assessment reports",
    )
    require(
        value.get("engine_sha") == engine_sha
        and value.get("archetype") == case.get("archetype")
        and value.get("target_profile") == case.get("profile"),
        "retained provenance differs from baseline case",
    )
    require(
        isinstance(value.get("input_package_sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", value["input_package_sha256"]) is not None,
        "retained provenance has an invalid input digest",
    )
    input_hashes = retained_file_hashes(case_dir / "input-files.json", "case input")
    require(
        inventory_digest(input_hashes) == value["input_package_sha256"],
        "retained input inventory digest differs from provenance",
    )
    require(
        value.get("generation_run_id") == f"maven-assessment-{case['id']}",
        "retained provenance has an unexpected generation run",
    )
    generation_input = value.get("generation_input")
    require(
        isinstance(generation_input, dict)
        and generation_input.get("target_profile") == case.get("profile")
        and generation_input.get("app_archetype", "crud") == case.get("archetype"),
        "retained provenance generation input differs",
    )
    validate_generation_receipt(case_dir / "generation.json", case, value)


def validate_independence_report(path, case, *, packaged):
    value = read_json(path)
    label = "packaged" if packaged else "source"
    require(
        isinstance(value, dict) and set(value) == INDEPENDENCE_FIELDS,
        f"malformed {label} independence report",
    )
    require(
        value.get("status") == "passed" and case.get(f"{label}_independence") == value["status"],
        f"{label} independence proof did not pass",
    )
    require(value.get("package") == case.get("id"), f"{label} independence package differs")
    count = value.get("baseline_generated_source_count")
    require(
        isinstance(count, int) and not isinstance(count, bool) and count >= 0,
        f"{label} independence source count is invalid",
    )
    checks = value.get("checks")
    require(isinstance(checks, list), f"malformed {label} independence checks")
    names = []
    for check in checks:
        require(
            isinstance(check, dict)
            and set(check) == {"name", "detail"}
            and isinstance(check["name"], str)
            and isinstance(check["detail"], str)
            and check["detail"],
            f"malformed {label} independence check",
        )
        names.append(check["name"])
    require(
        len(names) == len(set(names)) and set(names) == INDEPENDENCE_CHECKS,
        f"{label} independence checks are incomplete",
    )
    jar = value.get("packaged_jar")
    if packaged:
        require(
            isinstance(jar, str)
            and jar.startswith("target/")
            and jar.endswith(".jar")
            and ".." not in jar.split("/"),
            "packaged independence JAR is invalid",
        )
    else:
        require(jar is None, "source independence unexpectedly records a packaged JAR")
    return value


def validate_retained_case_proofs(case_dir, case, validated, engine_sha):
    validate_retained_provenance(case_dir, case, validated, engine_sha)
    source = validate_independence_report(
        case_dir / "source-independence.json", case, packaged=False
    )
    packaged = validate_independence_report(
        case_dir / "packaged-independence.json", case, packaged=True
    )
    require(
        source["baseline_generated_source_count"] == packaged["baseline_generated_source_count"],
        "source and packaged independence counts differ",
    )


def validate_case_summary(case, validated, engine_sha, source_digest, pom_digest):
    first = validated["assessment"]
    repeat = validated["repeat"]
    first_report, repeat_report = first["report"], repeat["report"]
    require(
        case.get("assessment_exit_code") == first_report["exit_code"], "case first exit differs"
    )
    require(case.get("repeat_exit_code") == repeat_report["exit_code"], "case repeat exit differs")
    require(
        case.get("resolved_artifacts")
        == first_report["resolved_artifacts"]
        == repeat_report["resolved_artifacts"],
        "case resolved artifact count differs",
    )
    require(
        case.get("source_unchanged") is True
        and first_report["source_unchanged"] is True
        and repeat_report["source_unchanged"] is True,
        "case source status differs",
    )
    require(
        case.get("repeat_inventory") == "equivalent"
        and first["inventory_sha256"] == repeat["inventory_sha256"],
        "case repeat inventory differs",
    )
    require(
        first_report["source_before_sha256"]
        == first_report["source_after_sha256"]
        == repeat_report["source_before_sha256"]
        == repeat_report["source_after_sha256"]
        == source_digest,
        "case source hashes differ from retained source inventory",
    )
    require(
        first_report["pom_sha256"] == repeat_report["pom_sha256"] == pom_digest,
        "case POM hashes differ from retained source inventory",
    )
    require(case.get("maven_exit_code") == 0, "case Maven build did not pass")
    require(
        case.get("source_independence") == "passed"
        and case.get("packaged_independence") == "passed",
        "case independence proof did not pass",
    )
    require(case.get("temporary_app_removed") is True, "case temporary app was not removed")
    for run, report in (("assessment", first_report), ("repeat", repeat_report)):
        require(
            report.get("provenance", {}).get("engine_sha") == engine_sha,
            f"case {run} Engine SHA differs",
        )
        require(
            report.get("provenance", {}).get("archetype") == case.get("archetype")
            and report.get("provenance", {}).get("target_profile") == case.get("profile"),
            f"case {run} provenance differs",
        )
    if "assessment_findings" in case:
        require(
            case["assessment_findings"] == first_report["findings"],
            "case first finding count differs",
        )
    if "repeat_findings" in case:
        require(
            case["repeat_findings"] == repeat_report["findings"],
            "case repeat finding count differs",
        )


def validate_receipt_summary(case, case_receipt):
    require(
        case_receipt["assessment"]["exit_code"] == case["assessment_exit_code"]
        and case_receipt["repeat"]["exit_code"] == case["repeat_exit_code"],
        "case and receipt exits differ",
    )
    require(
        case_receipt["assessment"]["findings"] == case["assessment_findings"]
        and case_receipt["repeat"]["findings"] == case["repeat_findings"],
        "case and receipt finding counts differ",
    )
    require(
        case_receipt["assessment"]["resolved_artifacts"]
        == case_receipt["repeat"]["resolved_artifacts"]
        == case["resolved_artifacts"],
        "case and receipt artifact counts differ",
    )
    require(
        case_receipt["assessment"]["status"] == case_receipt["repeat"]["status"] == "complete",
        "case receipt contains an incomplete assessment",
    )
    require(
        case_receipt["assessment"]["inventory_coverage"]
        == case_receipt["repeat"]["inventory_coverage"]
        == "complete",
        "case receipt contains incomplete coverage",
    )
    require(
        case_receipt["assessment"]["source_before_sha256"]
        == case_receipt["assessment"]["source_after_sha256"]
        == case_receipt["repeat"]["source_before_sha256"]
        == case_receipt["repeat"]["source_after_sha256"],
        "case receipt source hashes differ",
    )
    require(case_receipt.get("repeat_completed") is True, "case repeat did not complete")
    require(
        case_receipt.get("repeat_inventory_matched")
        is (
            case_receipt["assessment"]["normalized_inventory_sha256"]
            == case_receipt["repeat"]["normalized_inventory_sha256"]
        ),
        "case receipt repeat inventory status differs",
    )
    require(
        case_receipt.get("repeat_findings_identity_matched")
        is (
            case_receipt["assessment"]["findings_identity_sha256"]
            == case_receipt["repeat"]["findings_identity_sha256"]
        ),
        "case receipt finding identity status differs",
    )
    require(
        case_receipt.get("repeat_normalized_machine_evidence_matched")
        is (
            case_receipt["assessment"]["normalized_machine_evidence_sha256"]
            == case_receipt["repeat"]["normalized_machine_evidence_sha256"]
        ),
        "case receipt normalized evidence status differs",
    )


def build_graph_equivalence(validated, case_ids, graph_classes=GRAPH_CLASSES):
    known = {case for item in graph_classes for case in item["equivalent_cases"]}
    require(set(case_ids) <= known, "case has no declared graph-equivalence class")
    classes = []
    assigned = set()
    for item in graph_classes:
        selected = [case for case in item["equivalent_cases"] if case in case_ids]
        if not selected:
            continue
        representative = (
            item["representative_case"] if item["representative_case"] in selected else selected[0]
        )
        expected = validated[representative]["assessment"]["graph_sha256"]
        for case in selected:
            require(
                validated[case]["assessment"]["graph_sha256"] == expected,
                f"{case}: graph differs from declared representative {representative}",
            )
            require(
                validated[case]["repeat"]["graph_sha256"] == expected,
                f"{case}: repeat graph differs from declared representative {representative}",
            )
        resolved = validated[representative]["assessment"]["report"]["resolved_artifacts"]
        classes.append(
            {
                "graph_sha256": expected,
                "representative_case": representative,
                "equivalent_cases": selected,
                "resolved_artifacts": resolved,
                "dependency_distinctions": item["dependency_distinctions"],
            }
        )
        assigned.update(selected)
    require(assigned == set(case_ids), "not every case was assigned to a graph class")
    require(
        len({item["graph_sha256"] for item in classes}) == len(classes),
        "declared graph representatives are not unique",
    )
    return {
        "normalization": NORMALIZATION,
        "classes": classes,
    }


def observed_graph_classes(validated, case_ids):
    grouped = {}
    for case in sorted(case_ids):
        digest = validated[case]["assessment"]["graph_sha256"]
        grouped.setdefault(digest, []).append(case)
    return tuple({
        "representative_case": cases[0],
        "equivalent_cases": cases,
        "dependency_distinctions": {"basis": "validated resolved components and normalized dependency edges; no assumed profile/shape equivalence"},
    } for _, cases in sorted(grouped.items()))


def require_complete_case_matrix(case_ids, graph_classes=GRAPH_CLASSES):
    expected = {case for item in graph_classes for case in item["equivalent_cases"]}
    require(
        set(case_ids) == expected, "raw baseline must contain the complete declared case matrix"
    )


def receipt(case, validated, representative):
    runs = {}
    for run in ("assessment", "repeat"):
        value = validated[run]
        report = value["report"]
        runs[run] = {
            "status": report["status"],
            "exit_code": report["exit_code"],
            "scanner_exit_code": report["scanner_exit_code"],
            "assessment_time_utc": report["assessment_time_utc"],
            "sbom_timestamp_utc": value["bom_timestamp_utc"],
            "advisory_service": report["advisory_service"],
            "advisory_database_snapshot": report["advisory_database_snapshot"],
            "tools": report["tools"],
            "resolved_artifacts": report["resolved_artifacts"],
            "scanned_maven_packages": report["scanned_maven_packages"],
            "findings": report["findings"],
            "inventory_coverage": report["inventory_coverage"],
            "assessment_inventory_sha256": report["inventory_sha256"],
            "normalized_inventory_sha256": value["inventory_sha256"],
            "findings_identity_sha256": value["finding_identities_sha256"],
            "normalized_machine_evidence_sha256": value["normalized_machine_evidence_sha256"],
            "source_before_sha256": report["source_before_sha256"],
            "source_after_sha256": report["source_after_sha256"],
            "pom_sha256": report["pom_sha256"],
        }
        if "raw_scanner_stdout_sha256" in report:
            runs[run]["raw_scanner_stdout_sha256"] = report["raw_scanner_stdout_sha256"]
    return {
        "schema_version": "1.0",
        "case": case,
        "normalization_version": NORMALIZATION["version"],
        "graph_sha256": validated["assessment"]["graph_sha256"],
        "representative_case": representative,
        "full_graph_evidence_retained": case == representative,
        "assessment": runs["assessment"],
        "repeat": runs["repeat"],
        "repeat_completed": True,
        "repeat_inventory_matched": (
            runs["assessment"]["normalized_inventory_sha256"]
            == runs["repeat"]["normalized_inventory_sha256"]
        ),
        "repeat_findings_identity_matched": (
            runs["assessment"]["findings_identity_sha256"]
            == runs["repeat"]["findings_identity_sha256"]
        ),
        "repeat_normalized_machine_evidence_matched": (
            runs["assessment"]["normalized_machine_evidence_sha256"]
            == runs["repeat"]["normalized_machine_evidence_sha256"]
        ),
    }


def ensure_sanitized(value):
    if isinstance(value, str):
        require(
            not PATH_PATTERN.search(value), "retained evidence contains a machine-specific path"
        )
        require(
            not re.search(r"https?://[^\s/\"]+@", value),
            "retained evidence contains URL credentials",
        )
        return
    if isinstance(value, list):
        for item in value:
            ensure_sanitized(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            ensure_sanitized(key)
            ensure_sanitized(item)


def normalized_text(text):
    return "\n".join(line.rstrip() for line in text.splitlines()).rstrip() + "\n"


def copy_evidence_file(source, destination):
    require(source.is_file() and not source.is_symlink(), "missing or unsafe evidence file")
    if source.suffix == ".json":
        value = read_json(source)
        ensure_sanitized(value)
        serialized = json.dumps(value, indent=2, sort_keys=True) + "\n"
    else:
        serialized = normalized_text(source.read_text(encoding="utf-8"))
        ensure_sanitized(serialized)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialized, encoding="utf-8")


def write_sanitized_json(destination, value):
    serialized = json.dumps(value, indent=2, sort_keys=True) + "\n"
    ensure_sanitized(value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialized, encoding="utf-8")


def write_deterministic_gzip_json(source, destination):
    value = read_json(source)
    serialized = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    ensure_sanitized(value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
            compressed.write(serialized)


def render_summary(summary, findings):
    cases = summary["cases"]
    classes = summary["graph_equivalence"]["classes"]
    split = summary["finding_summary"]
    times = [
        case[run]["assessment_time_utc"]
        for case in summary["case_receipts"]
        for run in ("assessment", "repeat")
    ]
    rows = [
        "# Generated Maven Assessment Baseline",
        "",
        "**Assessment tooling/proof complete for the declared matrix; findings open; M2 not complete.**",
        "This record is dependency matching, not exploitability analysis, release clearance, or a",
        "claim that generated applications are safe to ship.",
        "",
        f"Candidate: `{summary['candidate']['id']}`, revision **{summary['candidate']['revision']}**.",
        f"Generating Engine: `{summary['engine_sha']}`.",
        f"Actual scan timestamps span **{min(times)}** through **{max(times)}**; no timestamp was rewritten.",
        "",
        "## Coverage",
        "",
        f"Execution coverage: **{len(cases)} case executions**, each built and assessed twice.",
        f"Persisted graph coverage: **{len(classes)} unique dependency graphs** with complete reports.",
        "Every case retains its own receipt, provenance/generation input, input/source inventories,",
        "build log, and source/packaged-independence evidence. No repeat archive is retained.",
        "",
        "| Case | Profile | Java | Build | Representative | Distinct findings | First / repeat raw findings |",
        "|---|---|---|---|---|---:|---:|",
    ]
    receipts = {item["case"]: item for item in summary["case_receipts"]}
    for case in cases:
        item = receipts[case["id"]]
        rows.append(
            f"| {case['id']} | {case['profile']} | {case['jdk']} | `{case['maven']}` | "
            f"{item['representative_case']} | {case['findings']} | "
            f"{item['assessment']['findings']} / {item['repeat']['findings']} |"
        )
    rows += [
        "",
        "## Graph Equivalence",
        "",
        "The versioned graph digest covers the normalized Maven tree, CycloneDX root/components/edges,",
        "and full normalized inventory. It excludes the volatile CycloneDX SBOM timestamp; descriptive",
        "SBOM metadata, tools, annotations and component hashes are outside graph identity. Each case",
        "and repeat was validated before class assignment; a mismatch fails finalization.",
        "",
        "| Representative | Equivalent cases | Artifacts | Dependency-bearing distinctions |",
        "|---|---|---:|---|",
    ]
    for item in classes:
        distinctions = ", ".join(
            f"{key}={str(value).lower()}" for key, value in item["dependency_distinctions"].items()
        )
        rows.append(
            f"| {item['representative_case']} | {', '.join(item['equivalent_cases'])} | "
            f"{item['resolved_artifacts']} | {distinctions} |"
        )
    rows += [
        "",
        "## Findings",
        "",
        f"The aggregate contains **{split['distinct']} distinct advisory matches**: "
        f"**{split['production_or_build']} production/build-impacting** and "
        f"**{split['test_only']} test-only**, across **{split['affected_coordinates']} coordinates**.",
        "A production/build classification means at least one matching inventory record is compile,",
        "runtime, provided, or system scope. `provided` and `system` do not necessarily mean packaged",
        "runtime reachability. Each aggregate observation carries sorted Maven scope/usage records.",
        "Missing severity/fix data remains unknown; all remediation decisions remain pending.",
        "",
        "## Repeat and Normalization Proof",
        "",
        "Each `assessment-receipt.json` preserves real assessment/SBOM timestamps, both exits and counts,",
        "inventory/finding-identity/machine-evidence digests, and whether first/repeat values match.",
        "The machine-evidence digest includes the six documented JSON reports and excludes only",
        "`assessment_time_utc` and CycloneDX `metadata.timestamp`. Finding identity is separately",
        "defined as coordinate/version/advisory ID. Findings from either pass feed the aggregate and",
        "therefore prevent overall exit 0; repeat-only metadata remains in aggregate observations.",
        "",
        "## Reproducible Layout",
        "",
        "The collector writes raw case reports. The committed companion command validates and emits the",
        "reduced layout from a fresh output directory, including deterministic JSON, log whitespace",
        "normalization, OSV gzip compression (`mtime=0`), pruning, receipts, graph mapping and summary:",
        "",
        "```bash",
        "python scripts/finalize_generated_maven_evidence.py \\",
        '  --source "$RAW_EVIDENCE_DIRECTORY" \\',
        '  --output "$NEW_REDUCED_EVIDENCE_DIRECTORY" \\',
        f"  --candidate-id {summary['candidate']['id']} \\",
        f"  --candidate-revision {summary['candidate']['revision']}",
        "```",
        "",
        "For each representative, `assessment/` contains the full first SBOM, Maven tree, inventory,",
        "findings, readable summary and tool logs; `osv.json.gz` is the sanitized full scanner report.",
        "Aggregate `findings.json` retains both passes' case/run observations. The committed finalizer",
        "does not fetch, build, scan, alter generated source, or replace actual timestamps.",
        "",
        "## Limitations",
        "",
        "PostgreSQL CRUD cases package with tests compiled but not run because no database service is",
        "provided. Maven plugin dependencies, OS/JDK/container layers, runtime reachability, custom",
        "profiles, browser/database/full-L5/runtime-E2E proof, dependency remediation, signing and CI",
        "enforcement remain outside this baseline. Existing build/scan inputs remain unchanged.",
        "",
        "Machine summary: [baseline.json](baseline.json). Aggregate findings: [findings.json](findings.json).",
        "",
    ]
    return "\n".join(rows)


def finalize(source, output, candidate_id, candidate_revision, graph_classes=GRAPH_CLASSES):
    source = source.resolve()
    output = output.resolve()
    require(source.is_dir(), "raw evidence directory is missing")
    require(not output.exists(), "reduced evidence output already exists")
    require(
        source != output and source not in output.parents, "output must be outside raw evidence"
    )
    baseline = read_json(source / "baseline.json")
    require(baseline.get("status") == "complete", "raw baseline is incomplete")
    require(
        baseline.get("release_acceptance") == "not established",
        "raw baseline must not claim release acceptance",
    )
    require(baseline.get("m2_complete") is False, "raw baseline must not claim M2 completion")
    engine_sha = baseline.get("engine_sha")
    require(
        isinstance(engine_sha, str) and re.fullmatch(r"[0-9a-f]{40}", engine_sha) is not None,
        "raw baseline has an invalid Engine SHA",
    )
    cases = baseline.get("cases")
    require(isinstance(cases, list) and cases, "raw baseline has no cases")
    raw_cases = copy.deepcopy(cases)
    raw_exit_code = baseline.get("exit_code")
    raw_distinct_findings = baseline.get("distinct_findings")
    case_ids = [case["id"] for case in cases]
    require(len(case_ids) == len(set(case_ids)), "duplicate baseline case")
    count_fields = [
        ("assessment_findings" in case, "repeat_findings" in case) for case in raw_cases
    ]
    require(
        all(first == repeat for first, repeat in count_fields),
        "raw case has partial per-run finding counts",
    )
    require(
        len({first for first, _ in count_fields}) == 1,
        "raw baseline mixes finding-count semantics",
    )
    legacy_counts = not count_fields[0][0]
    coverage = baseline.get("coverage_version", "1.0")
    dependency_policy = baseline.get("dependency_policy")
    if dependency_policy is not None:
        from appbuilder.generation.dependency_policy import DEPENDENCY_POLICY_ID
        require(dependency_policy == DEPENDENCY_POLICY_ID, "unknown dependency policy")
    require(coverage in {"1.0", "2.0"}, "unknown case coverage version")
    if coverage == "2.0":
        from scripts.collect_generated_maven_baseline import FIXTURES, PROFILES
        require(set(case_ids) == {f"{shape}-{profile}" for shape in FIXTURES for profile in PROFILES},
                "raw baseline must contain the complete promoted case matrix")
    else:
        require_complete_case_matrix(case_ids, graph_classes)
    pins = read_json(PINS_PATH)
    validated = {}
    for case in case_ids:
        validated[case] = {
            run: validate_run(source / case / run, pins) for run in ("assessment", "repeat")
        }
        require(
            validated[case]["assessment"]["graph_sha256"]
            == validated[case]["repeat"]["graph_sha256"],
            f"{case}: repeated normalized graph differs",
        )
    if coverage == "2.0":
        graph_classes = observed_graph_classes(validated, case_ids)
    graph_equivalence = build_graph_equivalence(validated, case_ids, graph_classes)
    representative_by_case = {
        case: item["representative_case"]
        for item in graph_equivalence["classes"]
        for case in item["equivalent_cases"]
    }
    findings = aggregate_findings(source, cases)
    for raw_case, case in zip(raw_cases, cases, strict=True):
        validate_case_finding_counts(
            raw_case,
            case,
            validated[case["id"]],
            legacy_counts=legacy_counts,
        )
        validate_retained_case_proofs(source / case["id"], case, validated[case["id"]], engine_sha)
        if dependency_policy is not None:
            from scripts.generated_maven_policy import validate_inventory, validate_libraries
            shape = case["id"].rsplit("-", 2)[0]
            applicability = {"kafka": shape.startswith("kafka"),
                             "batch": shape in {"ordinary-batch", "file-batch", "m5a", "mixed-batch"},
                             "router": shape in {"kafka-router", "kafka-mixed"}}
            policy = read_json(source / case["id"] / "dependency-policy.json")
            require(isinstance(policy, dict), "malformed retained dependency policy proof")
            expected_policy = validate_libraries(policy.get("packaged_libraries"), **applicability)
            for pass_name in ("assessment", "repeat"):
                expected_policy.update(validate_inventory(
                    read_json(source / case["id"] / pass_name / "inventory.json"), **applicability))
            require(policy == expected_policy, "retained dependency policy proof differs")
        source_digest, pom_digest = retained_source_hashes(
            source / case["id"] / "source-files.json"
        )
        validate_case_summary(
            case,
            validated[case["id"]],
            engine_sha,
            source_digest,
            pom_digest,
        )
    require(
        raw_exit_code == (1 if findings else 0),
        "raw baseline exit and aggregate findings disagree",
    )
    require(
        raw_distinct_findings == len(findings),
        "raw baseline distinct finding count differs",
    )
    split = Counter(finding["impact"] for finding in findings)
    require(set(split) <= {"production-or-build", "test-only"}, "unknown finding impact")
    receipts = [receipt(case, validated[case], representative_by_case[case]) for case in case_ids]
    for case, case_receipt in zip(cases, receipts, strict=True):
        validate_receipt_summary(case, case_receipt)
    output.mkdir(parents=True)
    for case in cases:
        case_id = case["id"]
        case_output = output / case_id
        case_output.mkdir()
        for name in CASE_FILES:
            copy_evidence_file(source / case_id / name, case_output / name)
        if dependency_policy is not None:
            copy_evidence_file(source / case_id / "dependency-policy.json", case_output / "dependency-policy.json")
        write_sanitized_json(
            case_output / "assessment-receipt.json", receipts[case_ids.index(case_id)]
        )
        if representative_by_case[case_id] == case_id:
            assessment_output = case_output / "assessment"
            assessment_output.mkdir()
            for name in FULL_ASSESSMENT_FILES:
                copy_evidence_file(source / case_id / "assessment" / name, assessment_output / name)
            write_deterministic_gzip_json(
                source / case_id / "assessment/osv.json", assessment_output / "osv.json.gz"
            )
    diagnostics = source / "diagnostics"
    if diagnostics.exists():
        require(
            diagnostics.is_dir() and not diagnostics.is_symlink(), "unsafe diagnostics directory"
        )
        for path in sorted(diagnostics.rglob("*")):
            if path.is_file():
                copy_evidence_file(path, output / "diagnostics" / path.relative_to(diagnostics))
    baseline.update(
        candidate={"id": candidate_id, "revision": candidate_revision},
        execution_coverage={"case_executions": len(cases), "assessment_runs": len(cases) * 2},
        persisted_graph_coverage={
            "unique_graphs": len(graph_equivalence["classes"]),
            "representative_cases": [
                item["representative_case"] for item in graph_equivalence["classes"]
            ],
        },
        graph_equivalence=graph_equivalence,
        case_receipts=receipts,
        finding_summary={
            "distinct": len(findings),
            "production_or_build": split["production-or-build"],
            "test_only": split["test-only"],
            "affected_coordinates": len(
                {(finding["coordinate"], finding["version"]) for finding in findings}
            ),
        },
        exit_code=1 if findings else 0,
        distinct_findings=len(findings),
        final_layout="reduced-v1",
    )
    write_sanitized_json(output / "baseline.json", baseline)
    write_sanitized_json(output / "findings.json", findings)
    summary = render_summary(baseline, findings)
    ensure_sanitized(summary)
    (output / "README.md").write_text(summary, encoding="utf-8")
    return baseline


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--candidate-revision", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        require(
            re.fullmatch(r"[A-Z0-9-]+", args.candidate_id) is not None,
            "invalid candidate ID",
        )
        require(args.candidate_revision > 0, "invalid candidate revision")
        report = finalize(args.source, args.output, args.candidate_id, args.candidate_revision)
    except (AssessmentError, OSError, ValueError, KeyError, TypeError) as exc:
        print(
            str(exc) if isinstance(exc, AssessmentError) else "evidence finalization failed",
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "candidate": report["candidate"],
                "execution_coverage": report["execution_coverage"],
                "persisted_graph_coverage": report["persisted_graph_coverage"],
                "finding_summary": report["finding_summary"],
                "exit_code": report["exit_code"],
                "release_acceptance": report["release_acceptance"],
            },
            sort_keys=True,
        )
    )
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
