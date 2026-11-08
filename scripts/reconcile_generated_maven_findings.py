"""Reconcile retained Maven/vendor evidence locally; never query or accept risk."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


class HistoricalSourceUnavailable(ValueError):
    """A full replay needs original retained bytes, not a public projection."""

    def __init__(self, artifact):
        self.artifact = artifact
        super().__init__(f"historical source unavailable: {artifact}")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def version(text):
    require(isinstance(text, str) and re.fullmatch(r"\d+(?:\.\d+){0,3}", text),
            "unsupported version; applicability remains untested")
    parts = tuple(map(int, text.split(".")))
    return parts + (0,) * (4 - len(parts))


def in_range(installed, expression):
    """Only numeric release ranges present in these retained vendor receipts."""
    actual = version(installed)
    require(isinstance(expression, str) and expression.strip(), "missing advisory range")
    interval = re.fullmatch(r"\s*(\d+(?:\.\d+){0,3})\s+-\s+(\d+(?:\.\d+){0,3})\s*", expression)
    if interval:
        return version(interval[1]) <= actual <= version(interval[2])
    comparisons = []
    for fragment in expression.split(","):
        part = re.fullmatch(r"\s*(<=|>=|<|>|=)?\s*(\d+(?:\.\d+){0,3})\s*", fragment)
        require(part is not None, "unsupported advisory range; applicability remains untested")
        expected = version(part[2])
        comparisons.append({"<": actual < expected, "<=": actual <= expected,
                            ">": actual > expected, ">=": actual >= expected,
                            "=": actual == expected}[part[1] or "="])
    return all(comparisons)


def branch_result(installed, expression, fixed):
    affected = in_range(installed, expression)
    if affected:
        if fixed and version(installed) >= version(fixed):
            return "OPEN_RANGE_CONTRADICTION"
        return "OPEN_AFFECTED_OR_UNTESTED"
    return "NOT_AFFECTED_VERSION"


def verify_sources(policy):
    index = read(policy / "vendor-sources/retrieval-index.json")
    sources = {}
    for entry in index:
        name = entry["artifact"]
        require(Path(name).name == name and name not in sources, "invalid/duplicate source artifact")
        try:
            compressed = (policy / "vendor-sources" / name).read_bytes()
        except FileNotFoundError:
            raise HistoricalSourceUnavailable(name) from None
        raw = gzip.decompress(compressed)
        require(digest(raw) == entry["sha256_uncompressed"]
                and len(raw) == entry["bytes_uncompressed"], "retained source checksum mismatch")
        sources[name] = {"bytes": raw, "sha256": digest(raw), "http_status": entry["http_status"],
                         "retrieved_at_utc": entry["retrieved_at_utc"], "url": entry["url"]}
    for entry in read(policy / "published-source/index.json"):
        require(digest((policy / "published-source" / entry["file"]).read_bytes()) == entry["sha256"],
                "published source member checksum mismatch")
    return sources


def baseline_inventory(baseline):
    root = read(baseline / "baseline.json")
    require(root["status"] == "complete", "incomplete retained Maven campaign")
    cases = {}
    for receipt in root["case_receipts"]:
        case, representative = receipt["case"], receipt["representative_case"]
        require(case not in cases, "duplicate retained case")
        inventory = read(baseline / representative / "assessment/inventory.json")
        libraries = read(baseline / case / "dependency-policy.json")["packaged_libraries"]
        require(libraries == sorted(set(libraries)) and inventory, "invalid retained inventory")
        cases[case] = {"inventory": inventory, "packaged_libraries": libraries}
    return root, cases


def bind_images(cases, image_report):
    require(re.fullmatch(r"[0-9a-f]{40}", image_report["generator_sha"]), "invalid image generator SHA")
    rows = image_report["cases"]
    require(isinstance(rows, list) and len(rows) == len(cases), "missing image case coverage")
    seen, generators = set(), set()
    for row in rows:
        case = row["case"]
        require(case in cases and case not in seen, "unknown/duplicate image case")
        seen.add(case)
        require(row["packaged_libraries"] == cases[case]["packaged_libraries"],
                "image/Maven packaged inventory mismatch")
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", row["image_id"])
                and re.fullmatch(r"[0-9a-f]{64}", row["jar_sha256"]), "invalid image/JAR identity")
        generator = row.get("generator_sha", image_report["generator_sha"])
        require(isinstance(generator, str) and re.fullmatch(r"[0-9a-f]{40}", generator),
                "invalid per-case image generator SHA")
        generators.add(generator)
    require(seen == set(cases), "missing image cases")
    require(image_report.get("generator_shas", [image_report["generator_sha"]]) == sorted(generators),
            "image generator set differs from actual case identities")


def observations(cases, coordinate):
    group, artifact = coordinate.split(":")
    result = []
    for case, evidence in sorted(cases.items()):
        for record in evidence["inventory"]:
            if record["group"] == group and record["artifact"] == artifact:
                filename = f"{artifact}-{record['version']}.jar"
                result.append({"case": case, "coordinate": coordinate, "version": record["version"],
                               "scope": record["scope"], "usage": record["usage"],
                               "packaged": filename in evidence["packaged_libraries"]})
    return result


def reconcile(policy, baseline, image_report):
    sources = verify_sources(policy)
    previous, cases = baseline_inventory(baseline)
    bind_images(cases, image_report)
    vendor = read(policy / "vendor-dispositions.json")
    historical = read(policy / "historical-18-dispositions.json")
    ids = {r["id"] for r in vendor["advisories"]}
    require(len(ids) == len(vendor["advisories"]), "duplicate vendor identity")
    raw_advisories = {}
    for name in ("lz4", "jackson-core", "jackson-databind"):
        artifact = f"{name}-advisories.json.gz"
        for advisory in json.loads(sources[artifact]["bytes"]):
            key = advisory["ghsa_id"]
            require(key not in raw_advisories, "duplicate raw vendor identity")
            raw_advisories[key] = (artifact, advisory)
    require(ids == set(raw_advisories), "vendor identity omitted or added")
    rows = []
    for identity in sorted(ids):
        source, advisory = raw_advisories[identity]
        branches = []
        unresolved = []
        for item in advisory["vulnerabilities"]:
            package = item["package"]
            require(package["ecosystem"].lower() == "maven", "unsupported vendor ecosystem")
            coordinate = package["name"]
            installed = observations(cases, coordinate)
            statuses = set()
            for observed in installed:
                try:
                    status = branch_result(observed["version"], item["vulnerable_version_range"],
                                           item.get("patched_versions", ""))
                except ValueError:
                    status = "OPEN_UNTESTED_APPLICABILITY"
                statuses.add(status)
            if not installed:
                statuses.add("NOT_INSTALLED")
            open_statuses = sorted(s for s in statuses if s.startswith("OPEN"))
            unresolved.extend(open_statuses)
            branches.append({"coordinate": coordinate, "affected_range": item["vulnerable_version_range"],
                             "reported_fixed": item.get("patched_versions", ""),
                             "scope_observations": installed, "statuses": sorted(statuses),
                             "final_runtime": "NOT_INSTALLED" if not any(r["packaged"] for r in installed)
                             else "OPEN" if open_statuses else "NOT_AFFECTED_VERSION"})
        feed_gap = identity in vendor["feed_gap"]["ids"]
        if feed_gap:
            for suffix in ("global", "osv"):
                require(sources[f"{identity}-{suffix}.json.gz"]["http_status"] == 404,
                        "retained feed-gap observation changed")
            unresolved.append("OPEN_FEED_COVERAGE_GAP")
        rows.append({"id": identity, "source": source, "source_sha256": sources[source]["sha256"],
                     "source_retrieved_at_utc": sources[source]["retrieved_at_utc"],
                     "branches": branches, "status": "OPEN" if unresolved else "SUPPORTED_VERSION_DISPOSITION",
                     "open_reasons": sorted(set(unresolved)), "owner": "Engine maintainer",
                     "next_decision": "Seek corrected upstream/feed evidence or commission bounded applicability proof; no suppression or risk acceptance"
                     if unresolved else "Reopen if coordinates, packaged scope or advisory ranges change",
                     "risk_accepted": False})
    historical_rows = []
    unique = set()
    for old in historical["mappings"]:
        identity, coordinate = old["historical_id"], old["historical_coordinate"]
        require((identity, coordinate) not in unique, "duplicate historical mapping")
        unique.add((identity, coordinate))
        if identity in raw_advisories:
            row = next(r for r in rows if r["id"] == identity)
            disposition = "REMEDIATED_VERSION" if row["status"] == "SUPPORTED_VERSION_DISPOSITION" else "OPEN"
            evidence = {"vendor_id": identity, "branches": row["branches"], "source_sha256": row["source_sha256"]}
        else:
            require(coordinate == "org.apache.tomcat.embed:tomcat-embed-core", "unmapped historical advisory")
            current = observations(cases, coordinate)
            require(current and all(r["version"] == "11.0.26" for r in current), "unexpected Tomcat inventory")
            raw = sources["tomcat-security-11.html.gz"]["bytes"].decode()
            cves = [c for c in old["historical_aliases"] if c.startswith("CVE-")]
            for cve in cves:
                pos = raw.find(cve)
                require(pos >= 0 and "Affects: 11.0.0-M1 to 11.0.24" in re.sub(r"<[^>]+>", "", raw[pos:pos+2200]),
                        "Tomcat affected-range evidence absent")
            evidence = {"source": "tomcat-security-11.html.gz", "source_sha256": sources["tomcat-security-11.html.gz"]["sha256"],
                        "cves": cves, "affected_through": "11.0.24", "scope_observations": current}
            disposition = "REMEDIATED_VERSION"
        historical_rows.append({"id": identity, "historical_coordinate": coordinate,
                                "historical_version": old["historical_version"],
                                "status": disposition, "evidence": evidence,
                                "owner": "Engine", "risk_accepted": False,
                                "review_trigger": "Dependency, packaged scope or advisory change"})
    require(len(unique) == historical["historical_matches"] == historical["mapped_matches"],
            "historical mapping omitted or added")
    return {"format_version": "1.0", "status": "complete",
            "exit_code": 1 if any(r["status"] == "OPEN" for r in rows + historical_rows) else 0,
            "generator_sha": image_report["generator_sha"],
            "generator_sha_semantics": image_report.get(
                "generator_sha_semantics", "campaign identity; actual image generators are recorded per case"),
            "generator_shas": image_report.get("generator_shas", [image_report["generator_sha"]]),
            "image_bindings": [{"case": row["case"],
                                "generator_sha": row.get("generator_sha", image_report["generator_sha"]),
                                "image_id": row["image_id"], "jar_sha256": row["jar_sha256"]}
                               for row in sorted(image_report["cases"], key=lambda item: item["case"])],
            "historical_maven_generator_sha": previous["engine_sha"],
            "image_case_count": len(cases), "historical_mappings": historical_rows,
            "vendor_observations": rows, "counts": {
                "historical": dict(Counter(r["status"] for r in historical_rows)),
                "vendor": dict(Counter(r["status"] for r in rows))},
            "normalization": "Numeric release ranges only; unknown formats remain OPEN, no network query. Every retained source branch is included.",
            "evidence_boundary": "Dated retained vendor bytes, independently hash-checked, reconciled to retained resolved scopes and actual current image packaged inventories. Not a fresh Maven/OSV campaign or exploitability proof.",
            "m2_complete": False, "release_clearance": False, "risk_accepted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--packaged-inventories", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    try:
        result = reconcile(args.policy, args.baseline, read(args.packaged_inventories))
    except HistoricalSourceUnavailable as exc:
        result = {"status": "incomplete", "exit_code": 2,
                  "error": "full historical replay requires original private source inputs",
                  "missing_source": exc.artifact, "release_clearance": False}
    except (OSError, ValueError, KeyError, TypeError):
        result = {"status": "incomplete", "exit_code": 2,
                  "error": "retained evidence reconciliation failed", "release_clearance": False}
    try:
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except OSError:
        return 2
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
