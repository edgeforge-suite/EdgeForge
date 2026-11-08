"""Compile schema-valid domain names that collide with legacy Batch API types."""

# ruff: noqa: E402 -- the optimization refusal intentionally precedes imports.

from __future__ import annotations

from scripts.smoke.boot41_batch_guard import require_unoptimized_python

require_unoptimized_python()

import argparse
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import yaml

from appbuilder.contracts import validate_package
from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project
from scripts.smoke.boot41_preview_proof import (
    _jdk_env,
    _run,
    _source_digest,
    _verify_java_home,
)
from scripts.smoke.generated_app_independence import verify_generated_app_independence

PROFILES = ("springboot-legacy-compatible",)


def history_name_fixture(root: Path, left: str, right: str) -> Path:
    fixture = root / f"history-names-{left.lower()}-{right.lower()}"
    fixture.mkdir(parents=True, exist_ok=False)
    for name in ("names-m5a-app-definition.yaml", "job-launcher-staging.sql", "job-explorer-staging.sql",
                 "job-launcher-staging-mapping.yaml", "job-explorer-staging-mapping.yaml"):
        source = Path("tests/fixtures/boot41-batch") / name
        target = fixture / name
        shutil.copyfile(source, target)
        if name.endswith(".yaml"):
            # Rename only synthetic input symbols, never generated Java decision code.
            target.write_text(target.read_text().replace("JobLauncher", left).replace("JobExplorer", right))
    return fixture / "names-m5a-app-definition.yaml"


def proof(java_home: Path, root: Path, maven_repo: Path | None):
    _verify_java_home(java_home, "17")
    root.mkdir(parents=True, exist_ok=False)
    rows = []
    cases = [(case, Path(f"tests/fixtures/boot41-batch/names-{case}-app-definition.yaml"), ["JobExplorer", "JobLauncher"])
             for case in ("ordinary", "m5a")]
    for left, right in (("HashSet", "JobExecution"), ("JobParameters", "JobLauncher"),
                        ("JobLauncher", "RuntimeException")):
        cases.append((f"m5a-{left}-{right}", history_name_fixture(root, left, right), sorted((left, right))))
    for case, fixture, expected_names in cases:
        errors = validate_package(yaml.safe_load(fixture.read_text()))
        if errors:
            raise AssertionError(f"Invalid regression manifest: {errors}")
        for profile in PROFILES:
            metadata = build_metadata_project(fixture)
            names = sorted(entity.name for entity in metadata.entities)
            assert names == expected_names
            metadata.target_profile = profile
            app = root / f"{case}-{profile}"
            result = generate_application(
                metadata,
                app,
                source_manifest=f"batch-names/{case}",
                generation_run_id="batch-names-regression",
            )
            if not result.harness_report.passed:
                raise AssertionError(f"Static harness failed: {case}/{profile}")
            verify_generated_app_independence(app, require_schema_baseline=True)
            digest = _source_digest(app)
            command = ["mvn", "-B", "-ntp"]
            if maven_repo:
                command.append(f"-Dmaven.repo.local={maven_repo}")
            output = _run(
                command + ["clean", "verify"], cwd=app, env=_jdk_env(java_home), timeout=360
            )
            (root / f"{app.name}.log").write_text(output, encoding="utf-8")
            counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
            for report in (app / "target/surefire-reports").glob("TEST-*.xml"):
                suite = ET.parse(report).getroot()
                for key in counts:
                    counts[key] += int(suite.get(key, "0"))
            if not counts["tests"] or any(counts[key] for key in ("failures", "errors", "skipped")):
                raise AssertionError(f"Tests missing, failed or skipped: {counts}")
            if _source_digest(app) != digest:
                raise AssertionError("Build mutated generated source")
            verify_generated_app_independence(
                app, require_schema_baseline=True, require_packaged_jar=True
            )
            rows.append(
                {
                    "case": case,
                    "profile": profile,
                    "entities": names,
                    "maven": counts,
                    "source_digest": digest,
                    "source_and_jar_independent": True,
                }
            )
    report = {
        "builds": rows,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source_sha": _run(
            ["git", "rev-parse", "HEAD"], cwd=Path.cwd(), env=os.environ.copy()
        ).strip(),
        "source_dirty": bool(
            _run(["git", "status", "--porcelain"], cwd=Path.cwd(), env=os.environ.copy()).strip()
        ),
        "release_acceptance": "not-established",
    }
    (root / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java17-home", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--maven-repo", type=Path)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                proof(args.java17_home, args.work_dir, args.maven_repo), indent=2, sort_keys=True
            )
        )
    except (AssertionError, ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Batch domain-name compilation proof failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
