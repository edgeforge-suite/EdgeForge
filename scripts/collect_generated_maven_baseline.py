#!/usr/bin/env python3
"""Build and assess the shipped-profile dependency branches using synthetic fixtures."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from appbuilder.generation import generate_application  # noqa: E402
from appbuilder.generation.dependency_policy import DEPENDENCY_POLICY_ID  # noqa: E402
from appbuilder.metadata.translation import build_metadata_project  # noqa: E402
from appbuilder.target_profiles import TARGET_PROFILES  # noqa: E402
from scripts.assess_generated_maven import (  # noqa: E402
    AssessmentError,
    assess,
    inventory_digest,
    read_json,
    require,
    run_tool,
    sanitize,
    source_inventory,
    write_json,
)
from scripts.smoke.generated_app_independence import (  # noqa: E402
    verify_generated_app_independence,
)
from scripts.generated_maven_policy import validate_inventory, validate_package  # noqa: E402

FIXTURES = {
    "crud": "examples/input-projects/generated-app-ci-smoke/app-definition.yaml",
    "crud-soap": "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml",
    "passthrough": "examples/input-projects/country-router/app-definition.yaml",
    "kafka": "tests/fixtures/kafka-integration/manifest.yaml",
    "kafka-router": "tests/fixtures/kafka-router-contract/manifest.yaml",
    "ordinary-batch": "tests/fixtures/boot41-batch/ordinary-app-definition.yaml",
    "file-batch": "tests/fixtures/file-contracts/csv-downstream/app-definition.yaml",
    "m5a": "tests/fixtures/manifest-v2-cut/v2-run-semantics-app-definition.yaml",
    "mixed-batch": "tests/fixtures/manifest-v2-cut/v2-run-semantics-app-definition.yaml",
    "kafka-mixed": "tests/fixtures/kafka-multi-route/manifest.yaml",
}
PROFILES = {
    "h2-j17": "springboot-legacy-compatible",
    "pg-j17": "springboot-enterprise-postgres-java17",
    "pg-j21": "springboot-standard-enterprise",
}

# Public third-party namespaces from reviewed synthetic fixture graphs. An unexpected
# namespace stops before the query, even if the local Maven/SBOM reconciliation passes.
PUBLIC_MAVEN_GROUPS = frozenset("""
at.yawk.lz4 ch.qos.logback com.dynatrace.hash4j com.ethlo.time com.fasterxml com.fasterxml.jackson.core
com.fasterxml.jackson.dataformat com.fasterxml.jackson.datatype com.fasterxml.jackson.module
com.github.ben-manes.caffeine com.github.luben com.google.code.gson com.google.errorprone com.google.re2j
com.h2database com.jayway.jsonpath com.networknt com.sun.istack com.sun.xml.messaging.saaj
com.thoughtworks.paranamer com.typesafe.scala-logging com.vaadin.external.google
com.yammer.metrics com.zaxxer commons-beanutils commons-cli commons-collections
commons-digester commons-io commons-logging commons-validator io.dropwizard.metrics io.micrometer
io.netty io.prometheus io.smallrye jakarta.activation jakarta.annotation jakarta.inject
jakarta.persistence jakarta.transaction jakarta.validation jakarta.xml.bind jakarta.xml.soap
jakarta.xml.ws net.bytebuddy net.minidev net.sf.jopt-simple net.sourceforge.argparse4j
org.antlr org.apache.kafka org.apache.logging.log4j org.apache.tomcat.embed org.apache.yetus
org.apache.zookeeper org.apiguardian org.aspectj org.assertj org.awaitility org.bitbucket.b_c
org.checkerframework org.eclipse.angus org.flywaydb org.glassfish.jaxb org.hamcrest
org.hdrhistogram org.hibernate.common org.hibernate.models org.hibernate.orm org.hibernate.validator
org.jboss.logging org.jspecify org.junit.jupiter org.junit.platform org.jvnet.staxex
org.latencyutils org.lz4 org.mockito org.objenesis org.opentest4j org.ow2.asm org.pcollections
org.postgresql org.rocksdb org.scala-lang org.scala-lang.modules org.skyscreamer org.slf4j org.snakeyaml
org.springframework org.springframework.batch org.springframework.boot org.springframework.data
org.springframework.kafka org.springframework.retry org.springframework.security org.springframework.ws
org.xerial.snappy org.xmlunit org.yaml tools.jackson.core tools.jackson.dataformat
tools.jackson.datatype tools.jackson.module
""".split())


def validate_public_query_inventory(records, repository=None):
    require(records and all(r["group"] in PUBLIC_MAVEN_GROUPS for r in records),
            "unreviewed Maven namespace: query not authorized; inspect retained inventory before retry")
    require(repository is not None, "public Maven POM inspection required before query")
    for record in records:
        group, artifact, version = (record[key] for key in ("group", "artifact", "version"))
        directory = repository / group.replace(".", "/") / artifact / version
        filename = f"{artifact}-{version}.pom"
        pom = directory / filename
        origin = directory / "_remote.repositories"
        require(pom.is_file() and origin.is_file()
                and f"{filename}>central=" in origin.read_text(),
                "public Central POM origin absent: query not authorized")
        try:
            root = ET.fromstring(pom.read_bytes())
        except ET.ParseError as exc:
            raise AssessmentError("malformed public POM: query not authorized") from exc
        namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
        actual_artifact = root.findtext("m:artifactId", namespaces=namespace) or root.findtext("artifactId")
        require(actual_artifact == artifact, "public POM coordinate mismatch: query not authorized")


def build_command(archetype, profile):
    if archetype == "crud" and TARGET_PROFILES[profile].runtime_database_dependency == "postgresql":
        return ["mvn", "-B", "-ntp", "clean", "package", "-DskipTests"]
    return ["mvn", "-B", "-ntp", "clean", "verify"]


def write_file_inventory(path, inventory):
    # Explicit digest fields avoid misclassifying API-named file hashes as credentials.
    write_json(
        path, [{"path": name, "sha256": digest} for name, digest in sorted(inventory.items())]
    )


def aggregate_findings(output, cases):
    """Union both live passes without losing their case/run-specific observations."""
    findings = {}
    for case in cases:
        case_keys = set()
        for run in ("assessment", "repeat"):
            observed = read_json(output / case["id"] / run / "findings.json")
            inventory = read_json(output / case["id"] / run / "inventory.json")
            require(isinstance(observed, list), "malformed collected findings")
            require(isinstance(inventory, list) and inventory, "malformed collected inventory")
            require(
                case[f"{run}_exit_code"] == (1 if observed else 0),
                "collected findings and assessment exit disagree",
            )
            classifications = {}
            for item in inventory:
                key = (f"{item['group']}:{item['artifact']}", item["version"])
                classifications.setdefault(key, set()).add((item["scope"], item["usage"]))
            case[f"{run}_findings"] = len(observed)
            for finding in observed:
                key = (finding["coordinate"], finding["version"], finding["id"])
                matched = classifications.get((finding["coordinate"], finding["version"]))
                require(matched, "finding is absent from the resolved inventory")
                classified = [{"scope": scope, "usage": usage} for scope, usage in sorted(matched)]
                case_keys.add(key)
                row = findings.setdefault(key, {**finding, "cases": [], "observations": []})
                if case["id"] not in row["cases"]:
                    row["cases"].append(case["id"])
                row["observations"].append(
                    {
                        "case": case["id"],
                        "run": run,
                        "classifications": classified,
                        "finding": finding,
                    }
                )
        case["findings"] = len(case_keys)
    result = []
    for key in sorted(findings):
        row = findings[key]
        classifications = {
            (classification["scope"], classification["usage"])
            for observation in row["observations"]
            for classification in observation["classifications"]
        }
        row["scopes"] = sorted({scope for scope, _ in classifications})
        row["usages"] = sorted({usage for _, usage in classifications})
        row["impact"] = "production-or-build" if "production" in row["usages"] else "test-only"
        result.append(row)
    return result


def prepare_case_input(temp, shape, fixture):
    source_manifest = ROOT / fixture
    if shape == "kafka-mixed":
        from scripts.smoke.boot41_kafka_preview_proof import prepare_input
        return prepare_input(temp) / "manifest.yaml"
    package = temp / "input"
    shutil.copytree(source_manifest.parent, package)
    manifest = package / source_manifest.name
    if shape == "mixed-batch":
        file_source = ROOT / FIXTURES["file-batch"]
        shutil.copytree(file_source.parent, package / "file-lane")
        raw = yaml.safe_load(manifest.read_text())
        lane = yaml.safe_load(file_source.read_text())
        for key in ("upstream_interfaces", "downstream_interfaces", "data_handoffs"):
            entries = lane.get(key, [])
            for entry in entries:
                for field in ("spec", "mapping", "request_sample", "response_sample"):
                    if field in entry:
                        entry[field] = "file-lane/" + entry[field]
                for operation in entry.get("operations", []):
                    for field in ("request_sample", "response_sample"):
                        if field in operation:
                            operation[field] = "file-lane/" + operation[field]
                if "samples" in entry:
                    entry["samples"] = ["file-lane/" + name for name in entry["samples"]]
            raw.setdefault(key, []).extend(entries)
        manifest.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return manifest


def collect(output, scanner, *, cases=None):
    require(not output.exists(), "baseline output already exists")
    output.mkdir(parents=True)
    sha = run_tool(["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=10).stdout.strip()
    require(not run_tool(["git", "status", "--porcelain"], cwd=ROOT, timeout=10).stdout.strip(),
            "final campaign requires a clean frozen committed generator")
    summary = {
        "engine_sha": sha,
        "coverage_version": "2.0",
        "dependency_policy": DEPENDENCY_POLICY_ID,
        "status": "incomplete",
        "exit_code": 2,
        "cases": [],
        "release_acceptance": "not established",
        "m2_complete": False,
    }
    original_java = os.environ.get("JAVA_HOME")
    original_path = os.environ.get("PATH", "")
    try:
        for shape, fixture in FIXTURES.items():
            for suffix, profile in PROFILES.items():
                case = f"{shape}-{suffix}"
                if cases and case not in cases:
                    continue
                print(f"Assessing {case}", flush=True)
                destination = output / case
                destination.mkdir()
                jdk = TARGET_PROFILES[profile].java_baseline
                java_home = os.environ.get(f"JAVA{jdk}_HOME")
                require(
                    java_home and (Path(java_home) / "bin/java").is_file(),
                    "required JDK home unavailable",
                )
                os.environ["JAVA_HOME"] = java_home
                os.environ["PATH"] = str(Path(java_home) / "bin") + os.pathsep + original_path
                with tempfile.TemporaryDirectory(prefix="generated-maven-baseline-") as temp:
                    temp = Path(temp)
                    manifest = prepare_case_input(temp, shape, fixture)
                    package = manifest.parent
                    raw = yaml.safe_load(manifest.read_text())
                    raw["target_profile"] = profile
                    manifest.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
                    input_hashes = source_inventory(package)
                    write_file_inventory(destination / "input-files.json", input_hashes)
                    metadata = build_metadata_project(manifest)
                    run_id = f"maven-assessment-{case}"
                    authoring = temp / "authoring/app"
                    generated = generate_application(
                        metadata, authoring, source_manifest=str(manifest), generation_run_id=run_id
                    )
                    write_json(
                        destination / "generation.json",
                        {
                            "generation_run_id": run_id,
                            "warnings": generated.warnings,
                            "harness": "passed"
                            if generated.harness_report is not None
                            and generated.harness_report.passed
                            else "not applicable",
                        },
                    )
                    if generated.harness_report is not None:
                        require(generated.harness_report.passed, "generation harness failed")
                    # Build only the generated repository, not its authoring package.
                    app = temp / "isolated/app"
                    shutil.copytree(authoring, app)
                    before = source_inventory(app)
                    write_file_inventory(destination / "source-files.json", before)
                    source = verify_generated_app_independence(app).to_dict()
                    source["package"] = case
                    write_json(destination / "source-independence.json", source)
                    command = build_command(metadata.app_archetype.value, profile)
                    result = run_tool(command, cwd=app, timeout=600, allowed=(0, 1))
                    (destination / "build.log").write_text(
                        sanitize(
                            result.stdout + result.stderr,
                            [(temp, "<temporary>"), (Path.home(), "<home>")],
                        ),
                        encoding="utf-8",
                    )
                    require(result.returncode == 0, f"{case}: Maven build failed; see build.log")
                    packaged = verify_generated_app_independence(
                        app, require_packaged_jar=True
                    ).to_dict()
                    packaged["package"] = case
                    write_json(destination / "packaged-independence.json", packaged)
                    applicability = {"kafka": shape.startswith("kafka"),
                                     "batch": shape in {"ordinary-batch", "file-batch", "m5a", "mixed-batch"},
                                     "router": shape in {"kafka-router", "kafka-mixed"}}
                    policy = validate_package(app, **applicability)
                    write_json(destination / "dependency-policy.json", policy)
                    require(source_inventory(app) == before, "build changed generated source")
                    provenance = {
                        "engine_sha": sha,
                        "input_package_sha256": inventory_digest(input_hashes),
                        "input_manifest": fixture,
                        "generation_run_id": run_id,
                        "target_profile": profile,
                        "archetype": metadata.app_archetype.value,
                        "generation_input": raw,
                    }
                    provenance_path = destination / "provenance.json"
                    write_json(provenance_path, provenance)
                    repository = Path(run_tool(
                        ["mvn", "-q", "help:evaluate", "-Dexpression=settings.localRepository",
                         "-DforceStdout"], cwd=app, timeout=120
                    ).stdout.strip())
                    def public_query_guard(records, repository=repository):
                        validate_public_query_inventory(records, repository)

                    first = assess(app, destination / "assessment", scanner, provenance_path,
                                   query_guard=public_query_guard)
                    require(
                        first["exit_code"] != 2,
                        f"{case}: {first.get('error', 'incomplete assessment')}",
                    )
                    second = assess(app, destination / "repeat", scanner, provenance_path,
                                    query_guard=public_query_guard)
                    require(second["exit_code"] != 2, f"{case}: repeat assessment incomplete")
                    for pass_name in ("assessment", "repeat"):
                        policy.update(validate_inventory(read_json(destination / pass_name / "inventory.json"),
                                                         **applicability))
                    write_json(destination / "dependency-policy.json", policy)
                    require(
                        first["inventory_sha256"] == second["inventory_sha256"],
                        "resolved inventory changed",
                    )
                    require(source_inventory(app) == before, "assessment changed generated source")
                    summary["cases"].append(
                        {
                            "id": case,
                            "archetype": metadata.app_archetype.value,
                            "profile": profile,
                            "jdk": jdk,
                            "maven": " ".join(command),
                            "generated_test_execution": "not run: external PostgreSQL required"
                            if "-DskipTests" in command
                            else "passed",
                            "maven_exit_code": 0,
                            "source_independence": "passed",
                            "packaged_independence": "passed",
                            "source_unchanged": True,
                            "repeat_inventory": "equivalent",
                            "assessment_exit_code": first["exit_code"],
                            "repeat_exit_code": second["exit_code"],
                            "assessment_findings": first["findings"],
                            "repeat_findings": second["findings"],
                            "resolved_artifacts": first["resolved_artifacts"],
                        }
                    )
                summary["cases"][-1]["temporary_app_removed"] = not temp.exists()
                write_json(output / "baseline.json", summary)
        require(summary["cases"], "no cases selected")
        require(
            run_tool(["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=10).stdout.strip() == sha,
            "Engine HEAD changed during baseline",
        )
        require(not run_tool(["git", "status", "--porcelain"], cwd=ROOT, timeout=10).stdout.strip(),
                "generator changed during final campaign")
        findings = aggregate_findings(output, summary["cases"])
        write_json(output / "findings.json", findings)
        summary.update(
            status="complete", exit_code=1 if findings else 0, distinct_findings=len(findings)
        )
    except (AssessmentError, OSError, ValueError, AssertionError) as exc:
        summary["error"] = (
            str(exc) if isinstance(exc, AssessmentError) else "generation/build/proof failed"
        )
    finally:
        os.environ["PATH"] = original_path
        if original_java is None:
            os.environ.pop("JAVA_HOME", None)
        else:
            os.environ["JAVA_HOME"] = original_java
        write_json(output / "baseline.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scanner", required=True, type=Path)
    parser.add_argument(
        "--case", action="append", choices=[f"{s}-{p}" for s in FIXTURES for p in PROFILES]
    )
    args = parser.parse_args()
    try:
        report = collect(args.output.resolve(), args.scanner.resolve(), cases=args.case)
    except (AssessmentError, OSError) as exc:
        print(
            str(exc) if isinstance(exc, AssessmentError) else "unavailable output", file=sys.stderr
        )
        return 2
    print(json.dumps(report, sort_keys=True))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
