from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import assess_generated_maven as assessment
from scripts import finalize_generated_maven_evidence as finalizer


def node(group="org.example", artifact="library", version="1.0", scope="compile", **extra):
    return {
        "groupId": group,
        "artifactId": artifact,
        "version": version,
        "type": "jar",
        "classifier": "",
        "scope": scope,
        **extra,
    }


def component(n):
    purl = f"pkg:maven/{n['groupId']}/{n['artifactId']}@{n['version']}?type=jar"
    return {
        "type": "library",
        "group": n["groupId"],
        "name": n["artifactId"],
        "version": n["version"],
        "purl": purl,
        "bom-ref": purl,
    }


@pytest.fixture
def evidence():
    library = node(children=[node(artifact="test-library", scope="test")])
    tree = node("com.appbuilder", "sample", "0.0.1-SNAPSHOT", "", children=[library])
    root = component(tree)
    components = [component(library), component(library["children"][0])]
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": root,
            "tools": {
                "components": [
                    {
                        "type": "library",
                        "group": "org.cyclonedx",
                        "name": "cyclonedx-maven-plugin",
                        "version": "2.9.1",
                    }
                ]
            },
        },
        "components": components,
        "dependencies": [
            {"ref": root["bom-ref"], "dependsOn": [components[0]["bom-ref"]]},
            {"ref": components[0]["bom-ref"], "dependsOn": [components[1]["bom-ref"]]},
            {"ref": components[1]["bom-ref"], "dependsOn": []},
        ],
    }
    report = {
        "results": [
            {
                "source": {"type": "sbom", "path": "/synthetic/bom.json"},
                "packages": [
                    {
                        "package": {
                            "name": "org.example:" + c["name"],
                            "version": c["version"],
                            "ecosystem": "Maven",
                        }
                    }
                    for c in components
                ],
            }
        ]
    }
    return tree, bom, report


def add_finding(report):
    report["results"][0]["packages"][0]["vulnerabilities"] = [
        {
            "id": "SYNTHETIC-1",
            "affected": [
                {
                    "package": {"name": "org.example:library", "ecosystem": "Maven"},
                    "ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.0"}]}],
                }
            ],
        }
    ]


def test_inventory_production_test_and_relationships(evidence):
    tree, bom, report = evidence
    records = assessment.compare_sbom(tree, bom, assessment.read_json(assessment.PINS_PATH))
    assert len(records) == 2
    assert {r["usage"] for r in records.values()} == {"production", "test"}
    assert [r["direct"] for r in records.values()] == [True, False]
    assert assessment.check_scanner(report, records, 0) == []


def test_findings_unknown_severity_and_reported_fixed_versions(evidence):
    tree, bom, report = evidence
    add_finding(report)
    records = assessment.compare_sbom(tree, bom, assessment.read_json(assessment.PINS_PATH))
    findings = assessment.check_scanner(report, records, 1)
    assert findings[0]["severity"] == "unknown"
    assert findings[0]["fixed_versions"] == ["2.0"]
    assert findings[0]["disposition"] == "remediation decision pending"
    report["results"][0]["packages"][0]["vulnerabilities"][0]["affected"][0].pop("ranges")
    assert assessment.check_scanner(report, records, 1)[0]["fixed_versions"] is None


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b.update(components=[]),
        lambda b: b["components"].pop(),
        lambda b: b["components"][0].pop("purl"),
        lambda b: b["components"][0].update(purl="pkg:npm/library@1.0"),
        lambda b: b["components"][0].update(group="different"),
        lambda b: b["metadata"]["tools"]["components"][0].update(version="latest"),
        lambda b: b.update(specVersion="9"),
        lambda b: b.pop("dependencies"),
        lambda b: b["dependencies"].pop(),
        lambda b: b["dependencies"][0].update(dependsOn=[]),
        lambda b: b["dependencies"][0].update(dependsOn=["not-a-ref"]),
        lambda b: b["components"].append(copy.deepcopy(b["components"][0])),
        lambda b: b["components"][0].update(components=[copy.deepcopy(b["metadata"]["component"])]),
    ],
)
def test_incomplete_sbom_is_never_clean(evidence, mutation):
    tree, bom, _ = evidence
    mutation(bom)
    with pytest.raises(assessment.AssessmentError):
        assessment.compare_sbom(tree, bom, assessment.read_json(assessment.PINS_PATH))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(results=[]),
        lambda r: r["results"][0].update(packages=[]),
        lambda r: r["results"][0]["packages"].pop(),
        lambda r: r["results"][0]["packages"][0]["package"].update(name="library"),
        lambda r: r["results"][0]["packages"][0]["package"].update(ecosystem="unknown"),
        lambda r: r["results"][0]["packages"][0].update(vulnerabilities={}),
        lambda r: r["results"][0]["packages"][0].update(vulnerabilities=[{}]),
        lambda r: r["results"][0]["source"].update(type="directory"),
    ],
)
def test_bad_scanner_extraction_is_never_clean(evidence, mutation):
    tree, bom, report = evidence
    records = assessment.compare_sbom(tree, bom, assessment.read_json(assessment.PINS_PATH))
    mutation(report)
    with pytest.raises(assessment.AssessmentError):
        assessment.check_scanner(report, records, 0)


@pytest.mark.parametrize("findings,code", [(False, 1), (True, 0), (False, 128)])
def test_exit_report_disagreement(evidence, findings, code):
    tree, bom, report = evidence
    if findings:
        add_finding(report)
    records = assessment.compare_sbom(tree, bom, assessment.read_json(assessment.PINS_PATH))
    with pytest.raises(assessment.AssessmentError, match="disagreement"):
        assessment.check_scanner(report, records, code)


@pytest.fixture
def tool_environment(tmp_path, monkeypatch, evidence):
    project = tmp_path / "app with spaces"
    project.mkdir()
    pom = """<!-- Generated by EdgeForge -->
<!-- Target profile: springboot-legacy-compatible -->
<!-- Generation run: synthetic -->
<project xmlns="http://maven.apache.org/POM/4.0.0"><properties><java.version>17</java.version></properties></project>
"""
    (project / "pom.xml").write_text(pom)
    (project / "source.java").write_text("synthetic source")
    provenance = tmp_path / "provenance.json"
    assessment.write_json(
        provenance,
        {
            "engine_sha": "a" * 40,
            "input_package_sha256": "b" * 64,
            "generation_run_id": "synthetic",
            "target_profile": "springboot-legacy-compatible",
            "archetype": "crud",
            "input_manifest": "fixture/manifest.yaml",
            "generation_input": {"target_profile": "springboot-legacy-compatible"},
        },
    )
    scanner = tmp_path / "tools" / "scanner"
    scanner.parent.mkdir()
    scanner.write_bytes(b"not an executable; mocked tools only")
    pins = assessment.read_json(assessment.PINS_PATH)
    pins["scanner_sha256"] = {"test-only": assessment.sha256(scanner)}
    pins_path = tmp_path / "pins.json"
    assessment.write_json(pins_path, pins)
    monkeypatch.setattr(assessment, "PINS_PATH", pins_path)
    calls = []
    state = {"mode": "clean"}

    def fake_run(args, **kwargs):
        calls.append(args)
        if state["mode"] == "timeout":
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        if state["mode"] == "missing-tool":
            raise FileNotFoundError("private path deliberately not propagated")
        code, stdout, stderr = 0, "", ""
        if args[-1] == "--version":
            if args[0] == "mvn":
                stdout = "Apache Maven 3.9.12\nJava version: 17.0.18, vendor: Test, runtime: /private/home\n"
            else:
                stdout = "osv-scanner version: 2.3.8\n"
                if state["mode"] == "wrong-version":
                    stdout = "osv-scanner version: 2.5.1\n"
        elif args[0] == "mvn":
            out = Path(next(a.split("=", 1)[1] for a in args if a.startswith("-DoutputDirectory=")))
            assessment.write_json(out / "maven-tree.json", evidence[0])
            assessment.write_json(out / "bom.json", evidence[1])
            if state["mode"] == "maven-error":
                code = 1
        else:
            report = copy.deepcopy(evidence[2])
            if state["mode"] == "findings":
                add_finding(report)
                code = 1
            if state["mode"] in {"paths-clean", "paths-incomplete"}:
                evidence_dir = Path(args[args.index("--lockfile") + 1]).parent
                report["experimental_config"] = {
                    "generated_app": str(project),
                    "evidence": str(evidence_dir),
                    "scanner_directory": str(scanner.parent),
                    "home": str(Path.home()),
                }
            if state["mode"] in {"windows-paths-clean", "windows-paths-incomplete"}:
                evidence_dir = Path(args[args.index("--lockfile") + 1]).parent
                report["experimental_config"] = {
                    "home": r"C:\Users\alice\private-assessment",
                    "nested": [
                        {"generated_app": str(project)},
                        {"evidence": str(evidence_dir)},
                        {"scanner_directory": str(scanner.parent)},
                        {"unc": r"\\server\share\private-assessment"},
                    ],
                }
            if state["mode"] in {"paths-incomplete", "windows-paths-incomplete"}:
                report["results"][0]["packages"].pop()
            if state["mode"] == "scanner-failure":
                code = 128
            if state["mode"] == "scanner-warning":
                stderr = "Failed to query advisory service"
            if state["mode"] == "empty":
                report["results"] = []
            if state["mode"] == "missing-package":
                report["results"][0]["packages"].pop()
            if state["mode"] == "mutation":
                (project / "source.java").write_text("changed")
            stdout = "not-json" if state["mode"] == "malformed" else json.dumps(report)
        return subprocess.CompletedProcess(args, code, stdout, stderr)

    monkeypatch.setattr(assessment.subprocess, "run", fake_run)
    return project, scanner, provenance, calls, state


@pytest.mark.parametrize(
    "mode,code",
    [
        ("clean", 0),
        ("findings", 1),
        ("timeout", 2),
        ("missing-tool", 2),
        ("wrong-version", 2),
        ("maven-error", 2),
        ("scanner-failure", 2),
        ("scanner-warning", 2),
        ("empty", 2),
        ("missing-package", 2),
        ("mutation", 2),
        ("malformed", 2),
    ],
)
def test_command_semantics_and_reports(tool_environment, tmp_path, mode, code):
    project, scanner, provenance, calls, state = tool_environment
    state["mode"] = mode
    output = tmp_path / "evidence"
    result = assessment.assess(project, output, scanner, provenance)
    assert result["exit_code"] == code
    assert result["release_acceptance"] == "not established"
    assert (output / "assessment.json").exists()
    assert (output / "summary.md").exists()
    assert str(tmp_path) not in (output / "assessment.json").read_text()
    assert all("-r" not in args and "install" not in args for args in calls)
    if code in (0, 1):
        assert result["source_unchanged"]
        assert (output / "osv.json").exists()
        assert str(tmp_path) not in (output / "osv.json").read_text()
        assert result["findings"] == (1 if code == 1 else 0)


def test_repeat_inventory_and_unchanged_files(tool_environment, tmp_path):
    project, scanner, provenance, _, _ = tool_environment
    before = assessment.source_inventory(project)
    first = assessment.assess(project, tmp_path / "one", scanner, provenance)
    second = assessment.assess(project, tmp_path / "two", scanner, provenance)
    assert first["exit_code"] == second["exit_code"] == 0
    assert (tmp_path / "one/inventory.json").read_bytes() == (
        tmp_path / "two/inventory.json"
    ).read_bytes()
    assert assessment.source_inventory(project) == before


@pytest.mark.parametrize("mode,expected_exit", [("paths-clean", 0), ("paths-incomplete", 2)])
def test_osv_report_paths_are_sanitized_on_complete_and_incomplete_results(
    tool_environment, tmp_path, mode, expected_exit
):
    project, scanner, provenance, _, state = tool_environment
    state["mode"] = mode
    output = tmp_path / "evidence"
    result = assessment.assess(project, output, scanner, provenance)
    assert result["exit_code"] == expected_exit
    persisted = (output / "osv.json").read_text()
    assert all(
        placeholder in persisted
        for placeholder in ("<generated-app>", "<evidence>", "<scanner-directory>", "<home>")
    )
    assert all(
        raw not in persisted
        for raw in (str(project), str(output), str(scanner.parent), str(Path.home()))
    )


@pytest.mark.parametrize(
    "mode,expected_exit",
    [("windows-paths-clean", 0), ("windows-paths-incomplete", 2)],
)
def test_osv_report_windows_paths_are_sanitized_after_json_parsing(
    tool_environment, tmp_path, mode, expected_exit
):
    project, scanner, provenance, _, state = tool_environment
    state["mode"] = mode
    output = tmp_path / "evidence"
    result = assessment.assess(project, output, scanner, provenance)
    assert result["exit_code"] == expected_exit
    persisted = assessment.read_json(output / "osv.json")
    serialized = json.dumps(persisted, sort_keys=True)
    assert all(
        placeholder in serialized
        for placeholder in (
            "<generated-app>",
            "<evidence>",
            "<scanner-directory>",
            "<home>",
            "<unc-path>",
        )
    )
    assert all(
        token not in serialized
        for token in (str(project), str(output), str(scanner.parent), "C:", "server", "share")
    )


def test_json_sanitizer_uses_named_placeholders_for_windows_tool_paths():
    value = {
        "generated_app": r"D:\generated-app\source",
        "evidence": r"E:\evidence\assessment",
        "scanner_directory": r"F:\tools\scanner",
    }
    paths = [
        (r"D:\generated-app\source", "<generated-app>"),
        (r"E:\evidence\assessment", "<evidence>"),
        (r"F:\tools\scanner", "<scanner-directory>"),
    ]
    assert assessment.sanitize_json(value, paths) == {
        "generated_app": "<generated-app>",
        "evidence": "<evidence>",
        "scanner_directory": "<scanner-directory>",
    }


@pytest.mark.parametrize(
    "value",
    [r"literal\\d+ tail", r"regex \\w+ remains", r"escaped\\value"],
)
def test_json_sanitizer_preserves_doubled_backslashes_that_are_not_unc_paths(value):
    assert assessment.sanitize_json({"details": value}, []) == {"details": value}


def test_json_sanitizer_redacts_only_the_unc_host_share_path():
    value = r"prefix \\server\share\private-assessment tail"
    assert assessment.sanitize_json({"details": value}, []) == {"details": "prefix <unc-path> tail"}


def test_public_advisory_poc_paths_are_redacted_without_losing_advisory_identity():
    value = {
        "id": "SYNTHETIC-ADVISORY", "aliases": ["SYNTHETIC-ALIAS"],
        "details": 'PoC {"workdir":"jar:file:/tmp/public-poc.zip!/x"}; see `/private/var/tmp/poc`.',
        "affected": [{"package": {"ecosystem": "Maven", "name": "org.example:library"},
                      "ranges": [{"events": [{"introduced": "0"}, {"fixed": "1.1"}]}]}],
    }
    sanitized = assessment.sanitize_json(value, [])
    finalizer.ensure_sanitized(sanitized)
    assert sanitized["id"] == value["id"] and sanitized["aliases"] == value["aliases"]
    assert sanitized["affected"] == value["affected"]
    assert sanitized["details"] == 'PoC {"workdir":"jar:file:<local-path>"}; see `<local-path>`.'
    assert assessment.sanitize("agent (/private/tmp/task-cache/byte-buddy.jar)\n", []) == "agent (<local-path>\n"


@pytest.mark.parametrize(
    "value",
    [
        r"C:\Users\alice\private-assessment",
        r"\\server\share\private-assessment",
        r"C:\\Users\\alice\\private-assessment",
    ],
)
def test_finalizer_rejects_unsanitized_windows_paths(value):
    with pytest.raises(assessment.AssessmentError, match="machine-specific path"):
        finalizer.ensure_sanitized({"nested": [{"path": value}]})


def test_wrong_checksum_never_executes_scanner(tool_environment, tmp_path):
    project, scanner, provenance, calls, _ = tool_environment
    scanner.write_bytes(b"corrupted")
    result = assessment.assess(project, tmp_path / "evidence", scanner, provenance)
    assert result["exit_code"] == 2
    assert "checksum" in result["error"]
    assert calls == []


def test_no_overwrite_or_in_project_evidence(tool_environment, tmp_path):
    project, scanner, provenance, calls, _ = tool_environment
    for output in (project / "evidence", tmp_path, project):
        with pytest.raises(assessment.AssessmentError):
            assessment.assess(project, output, scanner, provenance)
    assert calls == []


def test_duplicate_json_fails_closed(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"results": [], "results": []}')
    with pytest.raises(assessment.AssessmentError, match="duplicate"):
        assessment.read_json(path)


def test_missing_command_arguments():
    with pytest.raises(SystemExit) as exc:
        assessment.main([])
    assert exc.value.code == 2


def test_source_symlink_rejected(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "escape").symlink_to(tmp_path)
    with pytest.raises(assessment.AssessmentError, match="symlinks"):
        assessment.source_inventory(root)


@pytest.mark.parametrize("archetype", ["crud", "passthrough-router", "kafka-integration"])
@pytest.mark.parametrize(
    "profile",
    [
        "springboot-legacy-compatible",
        "springboot-enterprise-postgres-java17",
        "springboot-standard-enterprise",
    ],
)
def test_database_free_profile_build_boundary(archetype, profile):
    from scripts.collect_generated_maven_baseline import build_command

    command = build_command(archetype, profile)
    skip = archetype == "crud" and profile != "springboot-legacy-compatible"
    assert ("-DskipTests" in command) == skip
    assert ("verify" in command) != skip


def test_schema_rejects_invalid_component_type(evidence):
    _, bom, _ = evidence
    bom["components"][0]["type"] = "invalid-component-type"
    with pytest.raises(assessment.AssessmentError, match="schema validation"):
        assessment.validate_cyclonedx(bom)


def test_scanner_error_field_cannot_be_ignored(evidence):
    tree, bom, report = evidence
    records = assessment.compare_sbom(tree, bom, assessment.read_json(assessment.PINS_PATH))
    report["error"] = "network failure"
    with pytest.raises(assessment.AssessmentError):
        assessment.check_scanner(report, records, 0)


@pytest.mark.parametrize(
    "url", ["/tmp/private-input", "https://user:password@example.invalid/manifest"]
)
def test_machine_specific_provenance_rejected(tool_environment, tmp_path, url):
    project, scanner, provenance, calls, _ = tool_environment
    value = assessment.read_json(provenance)
    value["generation_input"]["source"] = url
    assessment.write_json(provenance, value)
    result = assessment.assess(project, tmp_path / "evidence", scanner, provenance)
    assert result["exit_code"] == 2
    assert calls == []
    assert url not in (tmp_path / "evidence/assessment.json").read_text()


@pytest.fixture
def collector_environment(tmp_path, monkeypatch):
    from scripts import collect_generated_maven_baseline as collector

    root = tmp_path / "engine"
    package = root / "fixture"
    package.mkdir(parents=True)
    (package / "manifest.yaml").write_text("app_archetype: crud\n")
    java = tmp_path / "jdk"
    (java / "bin").mkdir(parents=True)
    (java / "bin/java").write_text("not executable; all tools mocked")
    monkeypatch.setenv("JAVA17_HOME", str(java))
    monkeypatch.setattr(collector, "ROOT", root)
    monkeypatch.setattr(collector, "FIXTURES", {"crud": "fixture/manifest.yaml"})
    monkeypatch.setattr(collector, "PROFILES", {"h2-j17": "springboot-legacy-compatible"})
    monkeypatch.setattr(
        collector,
        "build_metadata_project",
        lambda _: SimpleNamespace(app_archetype=SimpleNamespace(value="crud")),
    )

    def generate(_metadata, output, **_kwargs):
        output.mkdir(parents=True)
        (output / "pom.xml").write_text("synthetic generated POM")
        return SimpleNamespace(warnings=[], harness_report=None)

    monkeypatch.setattr(collector, "generate_application", generate)
    monkeypatch.setattr(
        collector,
        "verify_generated_app_independence",
        lambda *_args, **_kwargs: SimpleNamespace(to_dict=lambda: {"passed": True}),
    )
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        if args == ["mvn", "-q", "help:evaluate", "-Dexpression=settings.localRepository", "-DforceStdout"]:
            return subprocess.CompletedProcess(args, 0, str(tmp_path / "m2"), "")
        assert args in (["git", "rev-parse", "HEAD"], ["git", "status", "--porcelain"]) or args == [
            "mvn",
            "-B",
            "-ntp",
            "clean",
            "verify",
        ]
        return subprocess.CompletedProcess(args, 0, "a" * 40 if args[:2] == ["git", "rev-parse"] else "", "")

    monkeypatch.setattr(collector, "run_tool", run)
    passes = {}

    def assess(_app, output, _scanner, _provenance, **_kwargs):
        output.mkdir()
        value = passes[output.name]
        report = {"status": "incomplete", "exit_code": 2}
        if value is not None:
            report = {
                "status": "complete",
                "exit_code": 1 if value else 0,
                "findings": len(value),
                "inventory_sha256": "same-resolved-inputs",
                "resolved_artifacts": 1,
            }
            assessment.write_json(output / "findings.json", value)
            assessment.write_json(
                output / "inventory.json",
                [
                    {
                        "group": "org.example",
                        "artifact": "library",
                        "version": "1.0",
                        "scope": "compile",
                        "usage": "production",
                        "type": "jar",
                        "classifier": "",
                        "direct": True,
                        "purl": "pkg:maven/org.example/library@1.0?type=jar",
                    }
                ],
            )
        assessment.write_json(output / "assessment.json", report)
        return report

    monkeypatch.setattr(collector, "assess", assess)
    # These tests isolate pass union/integrity, not Maven build policy selection.
    monkeypatch.setattr(collector, "validate_package", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(collector, "validate_inventory", lambda *_args, **_kwargs: {})
    return collector, passes, calls


def synthetic_finding(advisory):
    return {
        "coordinate": "org.example:library",
        "version": "1.0",
        "id": advisory,
        "severity": "unknown",
        "fixed_versions": None,
        "disposition": "remediation decision pending",
    }


@pytest.mark.parametrize(
    "first,repeat",
    [
        ([], []),
        ([], ["SYNTHETIC-2"]),
        (["SYNTHETIC-1"], []),
        (["SYNTHETIC-1"], ["SYNTHETIC-2"]),
        (["SYNTHETIC-1"], ["SYNTHETIC-1"]),
        (["SYNTHETIC-1", "SYNTHETIC-1"], ["SYNTHETIC-1"]),
    ],
)
def test_collector_unions_both_assessment_passes(collector_environment, tmp_path, first, repeat):
    collector, passes, calls = collector_environment
    passes.update(
        assessment=list(map(synthetic_finding, first)), repeat=list(map(synthetic_finding, repeat))
    )
    output = tmp_path / "evidence"
    result = collector.collect(output, tmp_path / "scanner")
    expected = set(first + repeat)
    assert result["status"] == "complete"
    assert result["exit_code"] == (1 if expected else 0)
    assert result["distinct_findings"] == len(expected)
    case = result["cases"][0]
    assert case["findings"] == len(expected)
    assert case["assessment_findings"] == len(first)
    assert case["repeat_findings"] == len(repeat)
    combined = assessment.read_json(output / "findings.json")
    assert {row["id"] for row in combined} == expected
    for row in combined:
        assert row["cases"] == ["crud-h2-j17"]
        assert row["scopes"] == ["compile"]
        assert row["usages"] == ["production"]
        assert row["impact"] == "production-or-build"
        assert row["observations"] == [
            {
                "case": "crud-h2-j17",
                "run": run,
                "classifications": [{"scope": "compile", "usage": "production"}],
                "finding": synthetic_finding(row["id"]),
            }
            for run, ids in (("assessment", first), ("repeat", repeat))
            for advisory in ids
            if row["id"] == advisory
        ]
    assert collector.aggregate_findings(output, copy.deepcopy(result["cases"])) == combined
    assert case["source_unchanged"] and case["temporary_app_removed"]
    assert len(calls) == 6  # HEAD/cleanliness, build and repository lookup; no real tool.
    assert str(tmp_path) not in (output / "baseline.json").read_text()
    assert str(tmp_path) not in (output / "findings.json").read_text()


@pytest.mark.parametrize("first", [[], ["SYNTHETIC-1"]])
def test_collector_incomplete_repeat_never_completes(collector_environment, tmp_path, first):
    collector, passes, _ = collector_environment
    passes.update(assessment=list(map(synthetic_finding, first)), repeat=None)
    output = tmp_path / "evidence"
    result = collector.collect(output, tmp_path / "scanner")
    assert result["status"] == "incomplete"
    assert result["exit_code"] == 2
    assert "repeat assessment incomplete" in result["error"]
    assert not (output / "findings.json").exists()
    assert (
        assessment.read_json(output / "crud-h2-j17/assessment/findings.json")
        == passes["assessment"]
    )
    assert assessment.read_json(output / "crud-h2-j17/repeat/assessment.json")["exit_code"] == 2


def test_collector_preserves_case_run_and_changed_advisory_metadata(
    collector_environment, tmp_path
):
    collector, passes, _ = collector_environment
    collector.FIXTURES["crud-soap"] = "fixture/manifest.yaml"
    first = synthetic_finding("SYNTHETIC-1")
    repeat = {**first, "severity": "HIGH", "fixed_versions": ["2.0"]}
    passes.update(assessment=[first], repeat=[repeat])
    output = tmp_path / "evidence"
    result = collector.collect(output, tmp_path / "scanner")
    assert result["exit_code"] == 1
    assert result["distinct_findings"] == 1
    (row,) = assessment.read_json(output / "findings.json")
    assert row["cases"] == ["crud-h2-j17", "crud-soap-h2-j17"]
    assert row["observations"] == [
        {
            "case": case,
            "run": run,
            "classifications": [{"scope": "compile", "usage": "production"}],
            "finding": finding,
        }
        for case in row["cases"]
        for run, finding in (("assessment", first), ("repeat", repeat))
    ]


def test_aggregate_findings_classifies_production_and_test_only(tmp_path):
    from scripts.collect_generated_maven_baseline import aggregate_findings

    cases = []
    for case_id, scope, usage, advisory in (
        ("production", "provided", "production", "SYNTHETIC-PROD"),
        ("test-only", "test", "test", "SYNTHETIC-TEST"),
    ):
        case = {"id": case_id, "assessment_exit_code": 1, "repeat_exit_code": 0}
        cases.append(case)
        inventory = [
            {
                "group": "org.example",
                "artifact": "library",
                "version": "1.0",
                "scope": scope,
                "usage": usage,
            }
        ]
        for run, findings in (
            ("assessment", [synthetic_finding(advisory)]),
            ("repeat", []),
        ):
            run_dir = tmp_path / case_id / run
            run_dir.mkdir(parents=True)
            assessment.write_json(run_dir / "inventory.json", inventory)
            assessment.write_json(run_dir / "findings.json", findings)

    results = {row["id"]: row for row in aggregate_findings(tmp_path, cases)}
    assert results["SYNTHETIC-PROD"]["impact"] == "production-or-build"
    assert results["SYNTHETIC-PROD"]["scopes"] == ["provided"]
    assert results["SYNTHETIC-TEST"]["impact"] == "test-only"
    assert results["SYNTHETIC-TEST"]["usages"] == ["test"]


def test_false_graph_equivalence_fails_closed():
    from scripts.finalize_generated_maven_evidence import (
        build_graph_equivalence,
        require_complete_case_matrix,
    )

    validated = {
        case: {
            run: {
                "graph_sha256": digest,
                "report": {"resolved_artifacts": 1},
            }
            for run in ("assessment", "repeat")
        }
        for case, digest in (("case-a", "a" * 64), ("case-b", "b" * 64))
    }
    graph_classes = (
        {
            "representative_case": "case-a",
            "equivalent_cases": ("case-a", "case-b"),
            "dependency_distinctions": {"archetype": "synthetic"},
        },
    )
    with pytest.raises(assessment.AssessmentError, match="differs from declared representative"):
        build_graph_equivalence(validated, ["case-a", "case-b"], graph_classes)
    with pytest.raises(assessment.AssessmentError, match="complete declared case matrix"):
        require_complete_case_matrix(["case-a"], graph_classes)


def test_normalized_digests_exclude_documented_timestamps_only(evidence):
    from scripts.finalize_generated_maven_evidence import (
        canonical_digest,
        normalized_graph,
        normalized_machine_evidence,
    )

    tree, bom, osv = evidence
    records = assessment.compare_sbom(tree, bom, assessment.read_json(assessment.PINS_PATH))
    inventory = sorted(records.values(), key=lambda item: item["purl"])
    first_bom, repeat_bom = copy.deepcopy(bom), copy.deepcopy(bom)
    first_bom["metadata"]["timestamp"] = "2026-09-13T01:00:00Z"
    repeat_bom["metadata"]["timestamp"] = "2026-09-13T02:00:00Z"
    first_report = {"assessment_time_utc": "2026-09-13T01:00:00Z", "stable": "value"}
    repeat_report = {"assessment_time_utc": "2026-09-13T02:00:00Z", "stable": "value"}

    assert canonical_digest(normalized_graph(tree, first_bom, inventory)) == canonical_digest(
        normalized_graph(tree, repeat_bom, inventory)
    )
    assert canonical_digest(
        normalized_machine_evidence(first_report, tree, first_bom, inventory, [], osv)
    ) == canonical_digest(
        normalized_machine_evidence(repeat_report, tree, repeat_bom, inventory, [], osv)
    )
    repeat_report["stable"] = "changed"
    assert canonical_digest(
        normalized_machine_evidence(first_report, tree, first_bom, inventory, [], osv)
    ) != canonical_digest(
        normalized_machine_evidence(repeat_report, tree, repeat_bom, inventory, [], osv)
    )


def finalizer_fixture(
    tmp_path,
    evidence,
    *,
    with_findings=False,
    finding_runs=None,
    current_collector=False,
):
    source = tmp_path / "raw"
    output = tmp_path / "reduced"
    case_id = "synthetic-case"
    case_dir = source / case_id
    case_dir.mkdir(parents=True)
    engine_sha = "b" * 40
    profile = "springboot-legacy-compatible"
    source_inventory = {"pom.xml": "c" * 64, "src/main/java/App.java": "d" * 64}
    source_digest = assessment.inventory_digest(source_inventory)
    input_inventory = {"app-definition.yaml": "e" * 64}
    pins = assessment.read_json(assessment.PINS_PATH)
    if finding_runs is None:
        finding_runs = {"assessment", "repeat"} if with_findings else set()
    run_counts = {}
    provenance = {
        "engine_sha": engine_sha,
        "input_package_sha256": assessment.inventory_digest(input_inventory),
        "input_manifest": "fixture/app-definition.yaml",
        "generation_run_id": f"maven-assessment-{case_id}",
        "target_profile": profile,
        "archetype": "crud",
        "generation_input": {"target_profile": profile, "app_archetype": "crud"},
    }

    for index, run in enumerate(("assessment", "repeat"), start=1):
        run_dir = case_dir / run
        run_dir.mkdir()
        tree, bom, osv = copy.deepcopy(evidence)
        bom["metadata"]["timestamp"] = f"2026-09-13T0{index}:00:00Z"
        if run in finding_runs:
            add_finding(osv)
        records = assessment.compare_sbom(tree, bom, pins)
        inventory = sorted(records.values(), key=lambda item: item["purl"])
        scanner_exit = 1 if run in finding_runs else 0
        findings = assessment.check_scanner(osv, records, scanner_exit)
        run_counts[run] = len(findings)
        report = {
            "status": "complete",
            "exit_code": scanner_exit,
            "scanner_exit_code": scanner_exit,
            "release_acceptance": "not established",
            "inventory_coverage": "complete",
            "inventory_sha256": assessment.inventory_digest(inventory),
            "resolved_artifacts": len(records),
            "scanned_maven_packages": len({(key[0], key[1], key[2]) for key in records}),
            "findings": len(findings),
            "affected_packages": len({item["coordinate"] for item in findings}),
            "scopes": sorted(assessment.SCOPES),
            "source_before_sha256": source_digest,
            "source_after_sha256": source_digest,
            "source_unchanged": True,
            "pom_sha256": source_inventory["pom.xml"],
            "assessment_time_utc": f"2026-09-13T0{index}:00:01Z",
            "advisory_service": "https://api.osv.dev",
            "advisory_database_snapshot": "not supplied",
            "tools": {"scanner": "synthetic"},
            "provenance": provenance,
        }
        for name, value in (
            ("assessment.json", report),
            ("maven-tree.json", tree),
            ("bom.json", bom),
            ("inventory.json", inventory),
            ("findings.json", findings),
            ("osv.json", osv),
        ):
            assessment.write_json(run_dir / name, value)
        for name in ("maven.log", "scanner.log", "summary.md"):
            (run_dir / name).write_text("synthetic\n", encoding="utf-8")

    case = {
        "id": case_id,
        "archetype": "crud",
        "profile": profile,
        "jdk": "17",
        "maven": "mvn -B -ntp clean verify",
        "maven_exit_code": 0,
        "assessment_exit_code": 1 if run_counts["assessment"] else 0,
        "repeat_exit_code": 1 if run_counts["repeat"] else 0,
        "resolved_artifacts": 2,
        "findings": run_counts["assessment"],
        "generated_test_execution": "passed",
        "source_independence": "passed",
        "packaged_independence": "passed",
        "source_unchanged": True,
        "repeat_inventory": "equivalent",
        "temporary_app_removed": True,
    }
    distinct_findings = 1 if any(run_counts.values()) else 0
    if current_collector:
        case.update(
            assessment_findings=run_counts["assessment"],
            repeat_findings=run_counts["repeat"],
            findings=distinct_findings,
        )
    assessment.write_json(
        source / "baseline.json",
        {
            "engine_sha": engine_sha,
            "status": "complete",
            "exit_code": 1 if distinct_findings else 0,
            "distinct_findings": distinct_findings,
            "release_acceptance": "not established",
            "m2_complete": False,
            "cases": [case],
        },
    )
    check_names = sorted(finalizer.INDEPENDENCE_CHECKS)
    source_independence = {
        "status": "passed",
        "package": case_id,
        "checks": [{"name": name, "detail": f"synthetic {name}"} for name in check_names],
        "baseline_generated_source_count": 2,
        "packaged_jar": None,
    }
    packaged_independence = {
        **source_independence,
        "checks": copy.deepcopy(source_independence["checks"]),
        "packaged_jar": "target/synthetic.jar",
    }
    root_files = {
        "generation.json": {
            "generation_run_id": f"maven-assessment-{case_id}",
            "warnings": [],
            "harness": "passed",
        },
        "input-files.json": [
            {"path": path, "sha256": digest} for path, digest in input_inventory.items()
        ],
        "packaged-independence.json": packaged_independence,
        "provenance.json": provenance,
        "source-files.json": [
            {"path": path, "sha256": digest} for path, digest in source_inventory.items()
        ],
        "source-independence.json": source_independence,
    }
    for name, value in root_files.items():
        assessment.write_json(case_dir / name, value)
    (case_dir / "build.log").write_text("synthetic\n", encoding="utf-8")
    graph_classes = (
        {
            "representative_case": case_id,
            "equivalent_cases": (case_id,),
            "dependency_distinctions": {"archetype": "synthetic"},
        },
    )
    return source, output, graph_classes


def test_finalizer_accepts_internally_consistent_receipts(tmp_path, evidence):
    source, output, graph_classes = finalizer_fixture(tmp_path, evidence)
    result = finalizer.finalize(source, output, "SYNTHETIC-CANDIDATE", 1, graph_classes)
    assert result["exit_code"] == 0
    assert result["distinct_findings"] == 0
    assert (output / "synthetic-case/assessment-receipt.json").is_file()


def test_finalizer_refuses_unknown_dependency_policy_before_output(tmp_path, evidence):
    source, output, graph_classes = finalizer_fixture(tmp_path, evidence)
    baseline = assessment.read_json(source / "baseline.json")
    baseline["dependency_policy"] = "unreviewed-policy"
    assessment.write_json(source / "baseline.json", baseline)
    with pytest.raises(assessment.AssessmentError, match="unknown dependency policy"):
        finalizer.finalize(source, output, "SYNTHETIC-CANDIDATE", 1, graph_classes)
    assert not output.exists()


def test_finalizer_refuses_missing_declared_dependency_policy_proof(tmp_path, evidence):
    source, output, graph_classes = finalizer_fixture(tmp_path, evidence)
    baseline = assessment.read_json(source / "baseline.json")
    baseline["dependency_policy"] = "ef-v5-maven-1"
    assessment.write_json(source / "baseline.json", baseline)
    with pytest.raises(assessment.AssessmentError, match="missing|unreadable|invalid"):
        finalizer.finalize(source, output, "SYNTHETIC-CANDIDATE", 1, graph_classes)
    assert not output.exists()


def test_finalizer_accepts_current_collector_clean_first_finding_repeat(tmp_path, evidence):
    source, output, graph_classes = finalizer_fixture(
        tmp_path,
        evidence,
        finding_runs={"repeat"},
        current_collector=True,
    )
    result = finalizer.finalize(source, output, "SYNTHETIC-CANDIDATE", 1, graph_classes)
    assert result["exit_code"] == 1
    assert result["cases"][0]["findings"] == 1
    assert result["cases"][0]["assessment_findings"] == 0
    assert result["cases"][0]["repeat_findings"] == 1


def test_current_collector_counts_validate_distinct_union_and_each_run():
    raw_case = {"findings": 102, "assessment_findings": 107, "repeat_findings": 107}
    recomputed_case = {"findings": 102}
    validated = {
        "assessment": {"report": {"findings": 107}},
        "repeat": {"report": {"findings": 107}},
    }
    finalizer.validate_case_finding_counts(
        raw_case, recomputed_case, validated, legacy_counts=False
    )
    raw_case["repeat_findings"] = 106
    with pytest.raises(assessment.AssessmentError, match="repeat assessment finding counts differ"):
        finalizer.validate_case_finding_counts(
            raw_case, recomputed_case, validated, legacy_counts=False
        )
    raw_case.update(repeat_findings=107, findings=103)
    with pytest.raises(assessment.AssessmentError, match="distinct finding union differs"):
        finalizer.validate_case_finding_counts(
            raw_case, recomputed_case, validated, legacy_counts=False
        )


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("exit-with-findings", "assessment exit and findings disagree"),
        ("partial-coverage", "coverage is incomplete"),
        ("artifact-count", "resolved artifact count differs"),
        ("package-count", "scanned package count differs"),
        ("affected-count", "affected package count differs"),
        ("source-hash", "source hashes do not prove unchanged source"),
        ("case-artifact-count", "case resolved artifact count differs"),
        ("case-finding-count", "legacy raw case and first assessment finding counts differ"),
        ("baseline-exit", "raw baseline exit and aggregate findings disagree"),
        ("baseline-finding-count", "distinct finding count differs"),
        ("retained-source-hash", "source hashes differ from retained source inventory"),
        ("provenance-engine", "retained provenance differs from assessment reports"),
        ("input-digest", "retained input inventory digest differs from provenance"),
        ("input-inventory", "retained input inventory digest differs from provenance"),
        ("generation-run", "retained generation receipt differs from provenance"),
        ("source-independence", "source independence proof did not pass"),
        ("packaged-independence", "packaged independence proof did not pass"),
    ],
)
def test_finalizer_rejects_contradictory_assessment_and_baseline_receipts(
    tmp_path, evidence, mutation, match
):
    with_findings = mutation == "exit-with-findings"
    source, output, graph_classes = finalizer_fixture(
        tmp_path, evidence, with_findings=with_findings
    )
    baseline = assessment.read_json(source / "baseline.json")
    report_path = source / "synthetic-case/assessment/assessment.json"
    report = assessment.read_json(report_path)
    if mutation == "exit-with-findings":
        report["exit_code"] = 0
    elif mutation == "partial-coverage":
        report["inventory_coverage"] = "partial"
    elif mutation == "artifact-count":
        report["resolved_artifacts"] += 1
    elif mutation == "package-count":
        report["scanned_maven_packages"] += 1
    elif mutation == "affected-count":
        report["affected_packages"] += 1
    elif mutation == "source-hash":
        report["source_after_sha256"] = "f" * 64
    elif mutation == "case-artifact-count":
        baseline["cases"][0]["resolved_artifacts"] += 1
    elif mutation == "case-finding-count":
        baseline["cases"][0]["findings"] += 1
    elif mutation == "baseline-exit":
        baseline["exit_code"] = 1
    elif mutation == "baseline-finding-count":
        baseline["distinct_findings"] += 1
    elif mutation == "retained-source-hash":
        source_files = assessment.read_json(source / "synthetic-case/source-files.json")
        source_files[1]["sha256"] = "f" * 64
        assessment.write_json(source / "synthetic-case/source-files.json", source_files)
    elif mutation == "provenance-engine":
        provenance_path = source / "synthetic-case/provenance.json"
        provenance = assessment.read_json(provenance_path)
        provenance["engine_sha"] = "f" * 40
        assessment.write_json(provenance_path, provenance)
    elif mutation == "input-digest":
        provenance_path = source / "synthetic-case/provenance.json"
        provenance = assessment.read_json(provenance_path)
        provenance["input_package_sha256"] = "f" * 64
        assessment.write_json(provenance_path, provenance)
        report["provenance"]["input_package_sha256"] = "f" * 64
        repeat_path = source / "synthetic-case/repeat/assessment.json"
        repeat = assessment.read_json(repeat_path)
        repeat["provenance"]["input_package_sha256"] = "f" * 64
        assessment.write_json(repeat_path, repeat)
    elif mutation == "input-inventory":
        input_path = source / "synthetic-case/input-files.json"
        input_files = assessment.read_json(input_path)
        input_files[0]["sha256"] = "f" * 64
        assessment.write_json(input_path, input_files)
    elif mutation == "generation-run":
        generation_path = source / "synthetic-case/generation.json"
        generation = assessment.read_json(generation_path)
        generation["generation_run_id"] = "maven-assessment-conflicting-case"
        assessment.write_json(generation_path, generation)
    elif mutation in {"source-independence", "packaged-independence"}:
        independence_path = source / f"synthetic-case/{mutation}.json"
        independence = assessment.read_json(independence_path)
        independence["status"] = "failed"
        assessment.write_json(independence_path, independence)
    assessment.write_json(report_path, report)
    assessment.write_json(source / "baseline.json", baseline)
    with pytest.raises(assessment.AssessmentError, match=match):
        finalizer.finalize(source, output, "SYNTHETIC-CANDIDATE", 1, graph_classes)


def test_receipt_consistency_check_rejects_contradictory_counts(tmp_path, evidence):
    source, output, graph_classes = finalizer_fixture(tmp_path, evidence)
    result = finalizer.finalize(source, output, "SYNTHETIC-CANDIDATE", 1, graph_classes)
    case = result["cases"][0]
    receipt = copy.deepcopy(result["case_receipts"][0])
    receipt["assessment"]["findings"] += 1
    with pytest.raises(assessment.AssessmentError, match="receipt finding counts differ"):
        finalizer.validate_receipt_summary(case, receipt)
