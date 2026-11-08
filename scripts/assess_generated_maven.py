#!/usr/bin/env python3
"""Assess one trusted generated Maven app, never the Engine or a cache tree.

Exit 0: complete/no findings; 1: complete/findings; 2: incomplete/error.
This is dependency matching, not exploitability analysis or release acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

PINS_PATH = Path(__file__).with_name("maven_assessment_tools.json")
SCOPES = {"compile", "runtime", "provided", "system", "test"}
SCHEMA_DIR = Path(__file__).parent / "schemas/cyclonedx-1.6"
WINDOWS_HOME_PATH = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/]+Users[\\/]+[^\r\n]*")
WINDOWS_UNC_PATH = re.compile(r"(?<![A-Za-z0-9_\\])\\{2}[^\\/\s]+\\[^\\/\s]+(?:\\[^\\/\s]+)*")
UNIX_LOCAL_PATH = re.compile(r"/(?:Users|home|tmp|private/(?:tmp|var))/[^\s\"'`<>\\]+", re.IGNORECASE)


class AssessmentError(ValueError):
    """A bounded, path-free diagnostic safe to include in evidence."""


def require(condition, message):
    if not condition:
        raise AssessmentError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssessmentError("missing or malformed JSON evidence") from exc


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_inventory(root):
    """Hash all source/config files, excluding only Maven output and Git metadata."""
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        if parent == root:
            dirs[:] = [name for name in dirs if name not in {"target", ".git"}]
            files = [name for name in files if name != ".git"]
        for name in dirs + files:
            require(not (parent / name).is_symlink(), "source symlinks are unsupported")
        for name in sorted(files):
            path = parent / name
            require(path.is_file(), "non-regular source file")
            result[path.relative_to(root).as_posix()] = sha256(path)
    require(result, "empty source tree")
    return dict(sorted(result.items()))


def inventory_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def run_tool(args, *, cwd, timeout, allowed=(0,)):
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise AssessmentError("tool timed out; assessment incomplete") from exc
    except (OSError, UnicodeError) as exc:
        raise AssessmentError("tool unavailable or unreadable output") from exc
    require(result.returncode in allowed, "tool failed; assessment incomplete")
    return result


def coordinate(node):
    require(isinstance(node, dict), "malformed Maven node")
    fields = [node.get(key) for key in ("groupId", "artifactId", "version", "type")]
    require(
        all(isinstance(v, str) and v and not re.search(r"[\s/:@?]", v) for v in fields),
        "unsupported Maven coordinate",
    )
    classifier = node.get("classifier", "")
    require(
        isinstance(classifier, str) and not re.search(r"[\s/:@?]", classifier),
        "unsupported Maven classifier",
    )
    return (*fields, classifier)


def purl_coordinate(component):
    require(isinstance(component, dict), "malformed SBOM component")
    purl = component.get("purl", "")
    require(
        isinstance(purl, str) and purl.startswith("pkg:maven/"),
        "missing or unsupported component PURL",
    )
    parsed = urlsplit(purl)
    require(not parsed.fragment, "PURL subpaths are unsupported")
    match = re.fullmatch(r"maven/([^/]+)/([^/@]+)@([^/]+)", parsed.path)
    require(match is not None, "malformed Maven PURL")
    qualifiers = unique_object(parse_qsl(parsed.query, strict_parsing=True))
    require(set(qualifiers) <= {"type", "classifier"}, "unsupported PURL qualifier")
    group, name, version = (unquote(part) for part in match.groups())
    require(
        (component.get("group"), component.get("name"), component.get("version"))
        == (group, name, version),
        "PURL/component identity mismatch",
    )
    return coordinate(
        {
            "groupId": group,
            "artifactId": name,
            "version": version,
            "type": qualifiers.get("type", "jar"),
            "classifier": qualifiers.get("classifier", ""),
        }
    )


def maven_inventory(tree):
    root = coordinate(tree)
    records = {}

    def walk(node, depth):
        key = coordinate(node)
        if depth:
            scope = node.get("scope")
            require(scope in SCOPES, "missing or unsupported Maven scope")
            require(key not in records, "duplicate resolved Maven coordinate")
            records[key] = {
                "group": key[0],
                "artifact": key[1],
                "version": key[2],
                "type": key[3],
                "classifier": key[4],
                "scope": scope,
                "usage": "test" if scope == "test" else "production",
                "direct": depth == 1,
            }
        children = node.get("children", [])
        require(isinstance(children, list), "malformed Maven dependency relationships")
        for child in children:
            walk(child, depth + 1)

    walk(tree, 0)
    require(records and root not in records, "empty or malformed resolved inventory")
    return root, records


def compare_sbom(tree, bom, pins):
    validate_cyclonedx(bom)
    root, records = maven_inventory(tree)
    require(
        isinstance(bom, dict)
        and bom.get("bomFormat") == "CycloneDX"
        and bom.get("specVersion") == pins["cyclonedx_schema"],
        "invalid SBOM format/version",
    )
    metadata = bom.get("metadata", {})
    tools = metadata.get("tools", {}).get("components", [])
    require(
        any(
            t.get("group") == "org.cyclonedx"
            and t.get("name") == "cyclonedx-maven-plugin"
            and t.get("version") == pins["cyclonedx_maven_plugin"]
            for t in tools
        ),
        "SBOM producer version mismatch",
    )
    root_component = metadata.get("component", {})
    require(purl_coordinate(root_component) == root, "SBOM root does not match Maven project")
    components = bom.get("components")
    require(isinstance(components, list) and components, "empty SBOM inventory")
    indexed = {}
    refs = {root_component.get("bom-ref")}
    for component in components:
        require(not component.get("components"), "nested SBOM components are outside the reconciled query inventory")
        key = purl_coordinate(component)
        ref = component.get("bom-ref")
        require(
            isinstance(ref, str) and ref and ref not in refs and key not in indexed,
            "duplicate/missing SBOM identity",
        )
        refs.add(ref)
        indexed[key] = component
    require(set(records) == set(indexed), "SBOM and resolved Maven inventories differ")
    graph = bom.get("dependencies")
    require(isinstance(graph, list), "missing SBOM dependency graph")
    edges = {}
    for node in graph:
        ref, children = node.get("ref"), node.get("dependsOn")
        require(
            ref in refs
            and ref not in edges
            and isinstance(children, list)
            and all(child in refs for child in children),
            "invalid SBOM graph reference",
        )
        edges[ref] = children
    require(set(edges) == refs, "incomplete SBOM dependency relationships")
    reached, pending = set(), [root_component["bom-ref"]]
    while pending:
        ref = pending.pop()
        if ref not in reached:
            reached.add(ref)
            pending.extend(edges[ref])
    require(reached == refs, "disconnected SBOM dependency inventory")
    for key, record in records.items():
        record["purl"] = indexed[key]["purl"]
    return records


def validate_cyclonedx(bom):
    # Existing Engine validation dependencies; all references resolve locally.
    try:
        from jsonschema import Draft7Validator, ValidationError
        from referencing import Registry, Resource
        from referencing.exceptions import Unresolvable
        from referencing.jsonschema import DRAFT7
    except ImportError as exc:
        raise AssessmentError("SBOM schema validation tooling unavailable") from exc
    schemas = [
        read_json(SCHEMA_DIR / name)
        for name in ("bom-1.6.schema.json", "spdx.schema.json", "jsf-0.82.schema.json")
    ]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT7))
        for schema in schemas
    )
    try:
        Draft7Validator(schemas[0], registry=registry).validate(bom)
    except (ValidationError, Unresolvable) as exc:
        raise AssessmentError("SBOM fails local CycloneDX schema validation") from exc


def check_scanner(report, records, exit_code):
    require(isinstance(report, dict), "malformed scanner report")
    require(set(report) <= {"results", "experimental_config"}, "unexpected scanner report fields")
    sources = report.get("results")
    require(isinstance(sources, list) and len(sources) == 1, "empty/unexpected scanner sources")
    source = sources[0]
    require(source.get("source", {}).get("type") == "sbom", "scanner did not assess the SBOM")
    packages = source.get("packages")
    require(isinstance(packages, list) and packages, "empty scanner extraction")
    expected = Counter((f"{key[0]}:{key[1]}", key[2]) for key in records)
    actual = Counter()
    findings = []
    for entry in packages:
        package = entry.get("package", {})
        name, version = package.get("name"), package.get("version")
        require(
            package.get("ecosystem") == "Maven"
            and isinstance(name, str)
            and isinstance(version, str),
            "unsupported scanner coordinate",
        )
        actual[(name, version)] += 1
        vulns = entry.get("vulnerabilities", [])
        require(isinstance(vulns, list), "malformed scanner vulnerabilities")
        for vuln in vulns:
            require(
                isinstance(vuln, dict)
                and isinstance(vuln.get("id"), str)
                and vuln["id"]
                and isinstance(vuln.get("affected"), list),
                "malformed advisory",
            )
            affected = [
                a
                for a in vuln["affected"]
                if a.get("package", {}).get("name") == name
                and a.get("package", {}).get("ecosystem") == "Maven"
            ]
            require(affected, "advisory/package identity mismatch")
            fixed = sorted(
                {
                    event["fixed"]
                    for a in affected
                    for r in a.get("ranges", [])
                    for event in r.get("events", [])
                    if "fixed" in event
                }
            )
            findings.append(
                {
                    "coordinate": name,
                    "version": version,
                    "id": vuln["id"],
                    "aliases": vuln.get("aliases", []),
                    "severity": vuln.get("database_specific", {}).get("severity", "unknown"),
                    "severity_vectors": vuln.get("severity", []),
                    "fixed_versions": fixed or None,
                    "advisory_modified": vuln.get("modified"),
                    "disposition": "remediation decision pending",
                }
            )
    # OSV's Maven queries use group:artifact + version, not classifier/type.
    # It may coalesce classifier variants; the full artifact inventory stays in the SBOM.
    require(
        set(actual) == set(expected) and all(1 <= n <= expected[k] for k, n in actual.items()),
        "scanner extraction does not cover resolved coordinates",
    )
    require(exit_code == (1 if findings else 0), "scanner exit/report disagreement")
    source["source"]["path"] = "bom.json"
    return sorted(findings, key=lambda f: (f["coordinate"], f["version"], f["id"]))


def validate_provenance(value, pom_text):
    fields = {
        "engine_sha",
        "input_package_sha256",
        "input_manifest",
        "generation_run_id",
        "target_profile",
        "archetype",
        "generation_input",
    }
    require(isinstance(value, dict) and set(value) == fields, "invalid provenance fields")
    for field, size in (("engine_sha", 40), ("input_package_sha256", 64)):
        require(
            isinstance(value[field], str) and re.fullmatch(rf"[0-9a-f]{{{size}}}", value[field]),
            "invalid provenance digest",
        )
    require(
        value["archetype"] in {"crud", "passthrough-router", "kafka-integration"},
        "unsupported archetype",
    )
    for field in ("input_manifest", "generation_run_id", "target_profile"):
        require(
            isinstance(value[field], str)
            and re.fullmatch(r"[A-Za-z0-9_.\-/]+", value[field])
            and not value[field].startswith("/")
            and ".." not in value[field].split("/"),
            "invalid provenance label",
        )
    require(isinstance(value["generation_input"], dict), "missing generation-run input")
    require(
        value["generation_input"].get("target_profile") == value["target_profile"]
        and value["generation_input"].get("app_archetype", "crud") == value["archetype"],
        "generation input/provenance mismatch",
    )
    serialized = json.dumps(value)
    require(
        not re.search(
            r"(?:/" r"Users/|/home/|/private/(?:tmp|var)/|/tmp/|[A-Za-z]:\\\\Users\\\\)", serialized
        )
        and not re.search(r"https?://[^\s/\"]+@", serialized),
        "provenance contains a host path or URL credentials",
    )
    for label, field in (
        ("Target profile", "target_profile"),
        ("Generation run", "generation_run_id"),
    ):
        require(f"<!-- {label}: {value[field]} -->" in pom_text, "provenance/POM header mismatch")
    return value


def sanitize(text, paths):
    for path, label in sorted(paths, key=lambda p: len(str(p[0])), reverse=True):
        text = text.replace(str(path), label)
    text = UNIX_LOCAL_PATH.sub("<local-path>", text)
    return "\n".join(line.rstrip() for line in text.splitlines()).rstrip() + (
        "\n" if text.endswith("\n") else ""
    )


def sanitize_json(value, paths):
    """Recursively redact paths after JSON parsing so escaping cannot bypass replacement."""
    if isinstance(value, str):
        for path, label in sorted(paths, key=lambda item: len(str(item[0])), reverse=True):
            value = value.replace(str(path), label)
        value = WINDOWS_HOME_PATH.sub("<home>", value)
        value = WINDOWS_UNC_PATH.sub("<unc-path>", value)
        return UNIX_LOCAL_PATH.sub("<local-path>", value)
    if isinstance(value, list):
        return [sanitize_json(item, paths) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            sanitized_key = sanitize_json(key, paths)
            require(sanitized_key not in result, "path sanitization produced duplicate JSON key")
            result[sanitized_key] = sanitize_json(item, paths)
        return result
    return value


def assess(project, output, scanner, provenance, *, timeout=300, maven="mvn", query_guard=None):
    project, output, scanner = project.resolve(), output.resolve(), scanner.resolve()
    require(project.is_dir() and (project / "pom.xml").is_file(), "missing Maven project")
    require(
        output != project and project not in output.parents and output not in project.parents,
        "evidence must be outside the generated project",
    )
    require(not output.exists(), "evidence directory already exists; use a new run directory")
    output.mkdir(parents=True)
    report = {
        "status": "incomplete",
        "exit_code": 2,
        "release_acceptance": "not established",
        "assessment_time_utc": datetime.now(timezone.utc).isoformat(),
        "advisory_service": "https://api.osv.dev",
        "advisory_database_snapshot": "not supplied",
    }
    paths = [
        (project, "<generated-app>"),
        (output, "<evidence>"),
        (scanner.parent, "<scanner-directory>"),
        (Path.home(), "<home>"),
    ]
    before = None
    try:
        pins = read_json(PINS_PATH)
        pom_text = (project / "pom.xml").read_text(encoding="utf-8")
        pom = ET.fromstring(pom_text)
        ns = {"m": "http://maven.apache.org/POM/4.0.0"}
        require(pom.find("m:modules", ns) is None, "multi-module projects are unsupported")
        require(
            "<!-- Generated by EdgeForge -->" in pom_text, "not an identified generated project"
        )
        report["provenance"] = validate_provenance(read_json(provenance), pom_text)
        before = source_inventory(project)
        report["source_before_sha256"] = inventory_digest(before)
        report["pom_sha256"] = sha256(project / "pom.xml")
        checksum = sha256(scanner)
        require(checksum in pins["scanner_sha256"].values(), "scanner official checksum mismatch")
        version = run_tool([str(scanner), "--version"], cwd=project, timeout=timeout).stdout
        require(
            f"osv-scanner version: {pins['osv_scanner']}\n" in version, "scanner version mismatch"
        )
        mvn_version = run_tool([maven, "--version"], cwd=project, timeout=timeout).stdout
        java = re.search(r"^Java version: ([^,]+), vendor: ([^,]+)", mvn_version, re.M)
        maven_match = re.search(r"^Apache Maven ([^\s]+)", mvn_version, re.M)
        require(java and maven_match, "unrecognized Maven/Java version output")
        expected_java = pom.findtext("m:properties/m:java.version", namespaces=ns)
        require(java[1].split(".")[0] == expected_java, "Maven JDK does not match generated target")
        report["tools"] = {
            "maven": maven_match[1],
            "java": java[1],
            "java_vendor": java[2],
            "scanner": version.strip().splitlines(),
            "scanner_sha256": checksum,
            "cyclonedx_maven_plugin": pins["cyclonedx_maven_plugin"],
            "maven_dependency_plugin": pins["maven_dependency_plugin"],
        }
        result = run_tool(
            [
                maven,
                "-B",
                "-ntp",
                f"org.apache.maven.plugins:maven-dependency-plugin:{pins['maven_dependency_plugin']}:tree",
                "-DoutputType=json",
                f"-DoutputFile={output / 'maven-tree.json'}",
                f"org.cyclonedx:cyclonedx-maven-plugin:{pins['cyclonedx_maven_plugin']}:makeBom",
                "-DincludeCompileScope=true",
                "-DincludeRuntimeScope=true",
                "-DincludeProvidedScope=true",
                "-DincludeSystemScope=true",
                "-DincludeTestScope=true",
                "-DoutputFormat=json",
                f"-DschemaVersion={pins['cyclonedx_schema']}",
                f"-DoutputDirectory={output}",
                "-DoutputName=bom",
                "-Dcyclonedx.skipAttach=true",
            ],
            cwd=project,
            timeout=timeout,
        )
        (output / "maven.log").write_text(
            sanitize(result.stdout + result.stderr, paths), encoding="utf-8"
        )
        report["maven_warnings"] = [
            sanitize(line, paths) for line in result.stdout.splitlines() if "[WARNING]" in line
        ]
        tree, bom = read_json(output / "maven-tree.json"), read_json(output / "bom.json")
        records = compare_sbom(tree, bom, pins)
        normalized = sorted(records.values(), key=lambda r: r["purl"])
        write_json(output / "inventory.json", normalized)
        report["inventory_sha256"] = inventory_digest(normalized)
        if query_guard is not None:
            query_guard(normalized)
        with tempfile.TemporaryDirectory(prefix="maven-osv-config-") as temp:
            config = Path(temp) / "osv-scanner.toml"
            config.write_text("# No suppressions or package overrides.\n", encoding="utf-8")
            result = run_tool(
                [
                    str(scanner),
                    "scan",
                    "source",
                    "--lockfile",
                    str(output / "bom.json"),
                    "--format",
                    "json",
                    "--all-packages",
                    "--all-vulns",
                    "--no-call-analysis=go",
                    "--no-resolve",
                    "--config",
                    str(config),
                ],
                cwd=Path(temp),
                timeout=timeout,
                allowed=(0, 1),
            )
        (output / "scanner.log").write_text(sanitize(result.stderr, paths), encoding="utf-8")
        require(
            not re.search(r"(?im)\b(warn(?:ing)?|error|failed)\b", result.stderr),
            "scanner diagnostic indicates incomplete assessment",
        )
        try:
            raw = json.loads(result.stdout, object_pairs_hook=unique_object)
        except json.JSONDecodeError as exc:
            raise AssessmentError("malformed scanner JSON") from exc
        report["raw_scanner_stdout_sha256"] = hashlib.sha256(result.stdout.encode()).hexdigest()
        # Preserve only a sanitized machine report, including when coverage fails.
        sanitized_raw = sanitize_json(raw, paths)
        write_json(output / "osv.json", sanitized_raw)
        findings = check_scanner(raw, records, result.returncode)
        # check_scanner normalizes the successful source label; sanitize that copy too.
        sanitized_raw = sanitize_json(raw, paths)
        write_json(output / "osv.json", sanitized_raw)
        write_json(output / "findings.json", findings)
        report.update(
            status="complete",
            exit_code=1 if findings else 0,
            scanner_exit_code=result.returncode,
            resolved_artifacts=len(records),
            scanned_maven_packages=len({(k[0], k[1], k[2]) for k in records}),
            findings=len(findings),
            affected_packages=len({f["coordinate"] for f in findings}),
            inventory_coverage="complete",
            scopes=sorted(SCOPES),
        )
    except (
        AssessmentError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        ET.ParseError,
    ) as exc:
        report["error"] = (
            str(exc) if isinstance(exc, AssessmentError) else "invalid input or tool evidence"
        )
    finally:
        if before is not None:
            try:
                after = source_inventory(project)
                report["source_after_sha256"] = inventory_digest(after)
                report["source_unchanged"] = before == after
                require(before == after, "generated source changed during assessment")
            except (AssessmentError, OSError):
                report.update(
                    status="incomplete", exit_code=2, error="generated source changed or unreadable"
                )
        if "error" in report:
            report.update(status="incomplete", exit_code=2)
        write_json(output / "assessment.json", report)
        rows = [
            "# Generated Maven Assessment",
            "",
            f"Status: **{report['status']}**; exit `{report['exit_code']}`.",
            "",
            "Dependency matches are not exploitability or release acceptance.",
            "",
        ]
        if report["status"] == "complete":
            rows += [
                f"Inventory: {report['resolved_artifacts']} resolved artifacts; complete scanner coverage.",
                f"Findings: {report['findings']}; remediation decisions pending.",
                "",
                "| Coordinate | Version | Advisory | Severity | Fixed versions (reported, not recommended) |",
                "|---|---|---|---|---|",
            ]
            for finding in read_json(output / "findings.json"):
                rows.append(
                    f"| {finding['coordinate']} | {finding['version']} | {finding['id']} | "
                    f"{finding['severity']} | {', '.join(finding['fixed_versions'] or ['unknown'])} |"
                )
        else:
            rows.append(
                f"Error: {report.get('error', 'assessment incomplete')}. No clean result is established."
            )
        (output / "summary.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scanner", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        require(1 <= args.timeout <= 3600, "timeout must be between 1 and 3600 seconds")
        report = assess(
            args.project, args.output, args.scanner, args.provenance, timeout=args.timeout
        )
    except (AssessmentError, OSError) as exc:
        report = {
            "status": "incomplete",
            "exit_code": 2,
            "error": str(exc) if isinstance(exc, AssessmentError) else "unavailable input/output",
        }
    print(json.dumps(report, sort_keys=True))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
