"""Executed, fresh-database Batch preview proof. Never connects to adopter data."""

# ruff: noqa: E402 -- the optimization refusal intentionally precedes imports.

from __future__ import annotations

from scripts.smoke.boot41_batch_guard import require_unoptimized_python

require_unoptimized_python()

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from contextlib import nullcontext
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from appbuilder.generation import generate_application
from scripts.smoke.boot41_batch_cases import (
    CASES,
    FILE_FIXTURE,
    M5A_FIXTURE,
    ORDINARY_FIXTURE,
    case_metadata,
)
from scripts.smoke.boot41_batch_durability import old_schema_refusal, postgres_durability
from scripts.smoke.boot41_batch_early_crash import postgres_early_crash, prepare_fixture
from appbuilder.target_profiles.catalog import TARGET_PROFILES

from scripts.smoke.boot41_preview_proof import (
    _application,
    _close_postgres,
    _content_type,
    _created_id,
    _database_env,
    _dependency_identity,
    _jdk_env,
    _json,
    _Postgres,
    _run,
    _source_digest,
    _verify_java_home,
)
from scripts.smoke.generated_app_independence import verify_generated_app_independence

PROFILES = (
    ("springboot-legacy-compatible", "17"),
    ("springboot-enterprise-postgres-java17", "17"),
    ("springboot-standard-enterprise", "21"),
)


def build(case, profile, java_home, root, maven_repo, postgres=None):
    from appbuilder.generation.utils import base_package

    metadata = case_metadata(case, profile)
    project = root / f"{case}-{profile}"
    for output in (project, root / ("repeat-" + project.name)):
        result = generate_application(
            metadata,
            output,
            source_manifest=f"batch-preview/{case}",
            generation_run_id="boot41-batch-proof",
        )
        if not result.harness_report.passed:
            raise AssertionError(f"Compatibility harness failed: {case}/{profile}")
    if _source_digest(project) != _source_digest(root / ("repeat-" + project.name)):
        raise AssertionError("Preview generation is nondeterministic")
    before = _source_digest(project)
    generate_application(
        metadata,
        project,
        source_manifest=f"batch-preview/{case}",
        generation_run_id="boot41-batch-proof",
    )
    if _source_digest(project) != before:
        raise AssertionError("Same-profile regeneration changed the package")
    if case in {"m5a", "mixed"}:
        test = (
            project
            / "src/test/java"
            / base_package(metadata).replace(".", "/")
            / "BatchPreviewRuntimeTest.java"
        )
        test.write_text(
            Path("tests/fixtures/boot41-batch/BatchPreviewRuntimeTest.java")
            .read_text()
            .replace("@PACKAGE@", base_package(metadata))
            .replace("@INSTANCE_SEQUENCE@", "BATCH_JOB_INSTANCE_SEQ" if TARGET_PROFILES[profile].experimental_boot41 else "BATCH_JOB_SEQ")
            .replace("@ABSENT_SEQUENCE@", "BATCH_JOB_SEQ" if TARGET_PROFILES[profile].experimental_boot41 else "BATCH_JOB_INSTANCE_SEQ")
            .replace("@HISTORY_TYPE@", "org.springframework.batch.core.repository.JobRepository" if TARGET_PROFILES[profile].experimental_boot41 else "org.springframework.batch.core.explore.JobExplorer"),
            encoding="utf-8",
        )
        preview = TARGET_PROFILES[profile].experimental_boot41
        batch = "org.springframework.batch.core.job" if preview else "org.springframework.batch.core"
        replacements = {
            "@PACKAGE@": base_package(metadata), "@BATCH@": batch,
            "@PARAMS@": batch + ".parameters" if preview else batch,
            "@EXECUTION_CTOR@": "new JobExecution(id, instance, params)" if preview else "new JobExecution(instance, id, params)",
            "@OTHER_EXECUTION_CTOR@": "new JobExecution(11L, new JobInstance(8L, \"widgetEodJob\"), origin.getJobParameters())" if preview else "new JobExecution(new JobInstance(8L, \"widgetEodJob\"), 11L, origin.getJobParameters())",
            "@HISTORY_IMPORT@": "org.springframework.batch.core.repository.JobRepository" if preview else "org.springframework.batch.core.explore.JobExplorer",
            "@HISTORY_MOCK@": "repo" if preview else "mock(JobExplorer.class)",
            "@STEP_ARGUMENTS@": "repo" if preview else "repo, history",
            "@TASKLET_STEP@": "org.springframework.batch.core.step.tasklet.TaskletStep",
            "@CONTRIBUTION@": "org.springframework.batch.core.step.StepContribution" if preview else "org.springframework.batch.core.StepContribution",
            "@STEP_EXECUTION@": "org.springframework.batch.core.step.StepExecution" if preview else "org.springframework.batch.core.StepExecution",
        }
        content = Path("tests/fixtures/boot41-batch/M5aHistoryIntegrityTest.java").read_text()
        for token, value in replacements.items():
            content = content.replace(token, value)
        test.with_name("M5aHistoryIntegrityTest.java").write_text(content, encoding="utf-8")
    if case == "ordinary":
        test = (
            project
            / "src/test/java"
            / base_package(metadata).replace(".", "/")
            / "OrdinaryStagingRuntimeTest.java"
        )
        port_import = "org.springframework.boot.test.web.server.LocalServerPort"
        test.write_text(
            Path("tests/fixtures/boot41-batch/OrdinaryStagingRuntimeTest.java")
            .read_text()
            .replace("@PACKAGE@", base_package(metadata))
            .replace("@PORT_IMPORT@", port_import),
            encoding="utf-8",
        )
    verify_generated_app_independence(project, require_schema_baseline=True)
    source_digest = _source_digest(project)
    database = postgres.create("s2" + case + profile) if postgres else None
    env = _database_env(_jdk_env(java_home), postgres, database)
    command = ["mvn", "-B", "-ntp"]
    if maven_repo:
        command.append(f"-Dmaven.repo.local={maven_repo}")
    command.extend(["clean", "verify"])
    output = _run(command, cwd=project, env=env, timeout=360)
    (root / (project.name + "-build.log")).write_text(output, encoding="utf-8")
    counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for report in (project / "target/surefire-reports").glob("TEST-*.xml"):
        suite = ET.parse(report).getroot()
        for key in counts:
            counts[key] += int(suite.get(key, "0"))
    if not counts["tests"] or any(counts[key] for key in ("failures", "errors", "skipped")):
        raise AssertionError(f"Tests missing, failed or skipped: {counts}")
    if _source_digest(project) != source_digest:
        raise AssertionError("Build mutated generated source")
    verify_generated_app_independence(
        project, require_schema_baseline=True, require_packaged_jar=True
    )
    jars = [
        path for path in (project / "target").glob("*.jar") if not path.name.endswith(".original")
    ]
    if len(jars) != 1:
        raise AssertionError("Expected exactly one standalone JAR")
    if TARGET_PROFILES[profile].experimental_boot41:
        verify_batch_artifacts(jars[0], profile)
    return (
        jars[0],
        env,
        database,
        {
            "case": case,
            "profile": profile,
            "maven": counts,
            "generation_and_regeneration_deterministic": True,
            "source_and_jar_independent": True,
            "source_digest": source_digest,
            "jar_sha256": hashlib.sha256(jars[0].read_bytes()).hexdigest(),
            "dependency_identity": _dependency_identity(project, java_home, maven_repo),
            "input_tree_sha256": _source_digest(Path(FILE_FIXTURE if case == "file" else ORDINARY_FIXTURE if case == "ordinary" else M5A_FIXTURE).parent),
            "runtime_test_fixture_sha256": {
                name: hashlib.sha256(Path("tests/fixtures/boot41-batch", name).read_bytes()).hexdigest()
                for name in ("BatchPreviewRuntimeTest.java", "M5aHistoryIntegrityTest.java")
            } if case in {"m5a", "mixed"} else {},
        },
    )


def verify_batch_artifacts(jar, profile):
    from appbuilder.generation.batch_metadata import normalized_batch_metadata_sql_statements
    from appbuilder.target_profiles.catalog import TARGET_PROFILES

    with ZipFile(jar) as app:
        libs = app.namelist()
        assert "BOOT-INF/lib/spring-batch-core-6.0.5.jar" in libs
        assert "BOOT-INF/lib/spring-boot-4.1.1.jar" in libs
        with ZipFile(BytesIO(app.read("BOOT-INF/lib/spring-batch-core-6.0.5.jar"))) as batch:
            database = TARGET_PROFILES[profile].runtime_database_dependency
            schema = batch.read(f"org/springframework/batch/core/schema-{database}.sql").decode()
    schema = re.sub(r"/\*.*?\*/|--[^\n]*", "", schema, flags=re.DOTALL)
    actual = [re.sub(r"\s+", " ", s).strip() for s in schema.split(";") if s.strip()]
    # These pinned scripts contain only unquoted identifiers/keywords, no literals.
    assert "'" not in schema and '"' not in schema
    assert [s.upper() for s in actual] == [
        s.upper() for s in normalized_batch_metadata_sql_statements(TARGET_PROFILES[profile])
    ], "Packaged Batch schema differs"


def trigger_value(response):
    status, headers, body = response
    value = json.loads(body)
    if status == 200:
        if set(value) != {"jobName", "jobId", "status", "startTime", "exitCode"}:
            raise AssertionError(f"Changed trigger response shape: {value}")
        if type(value["jobId"]) is not int or value["jobId"] < 1:
            raise AssertionError("Trigger identity must be a positive integer")
        if not isinstance(value["startTime"], str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T[0-9:.]+", value["startTime"]
        ):
            raise AssertionError("Trigger startTime must remain a local ISO timestamp")
        try:
            datetime.fromisoformat(value["startTime"])
        except ValueError as exc:
            raise AssertionError("Trigger startTime must be a valid calendar timestamp") from exc
        value = {**value, "jobId": "<validated-instance-id>", "startTime": "<validated-start-time>"}
    return status, _content_type(headers["content-type"]), value


def ordinary_wire(jar, java_home, env, root, case):
    output = root / (jar.parent.parent.name + "-files")
    output.mkdir()
    with _application(
        jar, java_home=java_home, env=env, root=root, properties={"app.eod.output-dir": str(output)}
    ) as (port, _log):
        if case == "ordinary":
            created = _json(port, "POST", "/widgets", {"payloadKey": "bounded-proof"})
            resource_id = _created_id(created, "widgetId")
            job = "widgetEodJob"
        else:
            request = json.loads(
                Path(
                    "tests/fixtures/file-contracts/csv-downstream/upstream/create-account-request.json"
                ).read_text()
            )
            created = _json(port, "POST", "/accounts", request)
            resource_id = _created_id(created, "accountId")
            job = "accountEodJob"
        first = _json(port, "POST", "/batch/run/" + job)
        first_value = trigger_value(first)
        if first_value[0] != 200 or first_value[2]["status"] != "COMPLETED":
            raise AssertionError(f"Ordinary job did not complete: {first_value}")
        unknown = trigger_value(_json(port, "POST", "/batch/run/notAJob"))
        if unknown[0] != 404:
            raise AssertionError("Unknown ordinary job did not retain 404")
        files = list(output.rglob("*.csv"))
        content = None
        if case == "file":
            if len(files) != 1:
                raise AssertionError(f"Expected one CSV, found {len(files)}")
            raw = files[0].read_bytes()
            if raw.count(resource_id.encode()) != 1:
                raise AssertionError("CSV must identify the created account exactly once")
            content = raw.replace(resource_id.encode(), b"<validated-created-id>").hex()
        second = trigger_value(_json(port, "POST", "/batch/run/" + job))
        if second[0] != 200 or second[2]["status"] != "COMPLETED":
            raise AssertionError("Legacy bodyless rerun did not complete")
        return {"trigger": first_value, "unknown": unknown, "rerun": second, "file_bytes": content}


def _proof(args):
    _verify_java_home(args.java17_home, "17")
    if args.mode == "full":
        if not args.java21_home:
            raise ValueError("Full proof requires Java 21")
        _verify_java_home(args.java21_home, "21")
    postgres = _Postgres() if args.mode == "full" else None
    try:
        if args.work_dir:
            args.work_dir.mkdir(parents=True, exist_ok=False)
        context = (
            nullcontext(str(args.work_dir))
            if args.work_dir
            else tempfile.TemporaryDirectory(prefix="edgeforge-s2-")
        )
        with context as temporary:
            root = Path(temporary)
            rows = []
            wires = {}
            for profile, java in PROFILES[:1] if args.mode == "h2" else PROFILES:
                home = args.java17_home if java == "17" else args.java21_home
                for case in args.case or CASES:
                    pg = postgres if "h2" not in profile and profile != PROFILES[0][0] else None
                    jar, env, database, receipt = build(
                        case, profile, home, root, args.maven_repo, pg
                    )
                    if case in {"ordinary", "file"}:
                        wire = ordinary_wire(jar, home, env, root, case)
                        if database and case == "ordinary":
                            if (
                                pg._psql(
                                    "SELECT COUNT(*) FROM widget_staging WHERE payload_key='bounded-proof'",
                                    database=database,
                                )
                                != "2"
                            ):
                                raise AssertionError(
                                    "Ordinary staging reruns did not retain distinct legacy run rows"
                                )
                        if not database:
                            wires[case] = wire
                        receipt["ordinary_wire_and_file_output"] = wire
                    if case == "mixed":
                        ordinary_wire(jar, home, env, root, "file")
                        receipt["mixed_bodyless_file_job_executed"] = True
                    if database and case == "m5a":
                        receipt["postgres_durability"] = postgres_durability(
                            jar, home, env, root, pg, database
                        )
                        seam_test_db = pg.create("seamtests" + profile)
                        seam_test_env = _database_env(_jdk_env(home), pg, seam_test_db)
                        early_jar, source_identity = prepare_fixture(jar, home, seam_test_env, root, args.maven_repo)
                        receipt["postgres_early_crash"] = postgres_early_crash(
                            early_jar, home, env, root, pg, database, source_identity
                        )
                    if database:
                        receipt["flyway_versions"] = pg.history(database)
                    rows.append(receipt)
            report = {
                "mode": args.mode,
                "profile_selection": "promoted ordinary IDs; no historical Boot 3 matrix",
                "builds": rows,
                "batch_schema": "6.0.5",
                "boot": "4.1.1",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "source_sha": _run(
                    ["git", "rev-parse", "HEAD"], cwd=Path.cwd(), env=os.environ.copy()
                ).strip(),
                "source_dirty": bool(
                    _run(
                        ["git", "status", "--porcelain"], cwd=Path.cwd(), env=os.environ.copy()
                    ).strip()
                ),
                "h2_restart_boundary": "same-process",
                "release_acceptance": "not-established",
            }
            if args.work_dir:
                (root / "receipt.json").write_text(
                    json.dumps(report, sort_keys=True, indent=2) + "\n"
                )
            return report
    finally:
        _close_postgres(postgres)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("h2", "full"), required=True)
    parser.add_argument("--java17-home", type=Path, required=True)
    parser.add_argument("--java21-home", type=Path)
    parser.add_argument("--maven-repo", type=Path)
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="New directory retaining local logs/apps and the path-free receipt",
    )
    args = parser.parse_args()
    try:
        print(json.dumps(_proof(args), sort_keys=True, indent=2))
    except (AssertionError, ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Batch preview proof failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
