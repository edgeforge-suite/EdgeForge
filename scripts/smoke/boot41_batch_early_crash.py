"""Disposable pre-identity-commit seam and database-observed crash proof."""

# ruff: noqa: E402 -- the optimization refusal intentionally precedes imports.

from scripts.smoke.boot41_batch_guard import require_unoptimized_python

require_unoptimized_python()

import difflib
import hashlib
import json
import shutil
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.error import URLError
from urllib.request import Request, urlopen

from scripts.smoke.boot41_batch_durability import (
    _context_decoder,
    _wait,
    database_snapshot,
    require_complete,
    run,
    runtime,
)
from scripts.smoke.boot41_preview_proof import _run, _source_digest

SEAM_ANCHOR = "                var execution = contribution.getStepExecution().getJobExecution();\n"
SEAM = '''                String proofMarker = System.getenv("EDGEFORGE_PROOF_EARLY_MARKER");
                if (proofMarker != null && execution.getJobParameters().getString("runId")
                        .equals(System.getenv("EDGEFORGE_PROOF_EARLY_RUNID"))) {
                    var proofPath = java.nio.file.Path.of(proofMarker);
                    var pendingPath = java.nio.file.Path.of(proofMarker + ".pending");
                    java.nio.file.Files.writeString(pendingPath, String.valueOf(execution.getId()));
                    java.nio.file.Files.move(pendingPath, proofPath, java.nio.file.StandardCopyOption.ATOMIC_MOVE);
                    if (!new java.util.concurrent.CountDownLatch(1).await(60, java.util.concurrent.TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Disposable proof coordination timed out");
                    }
                }
'''


def prepare_fixture(jar, home, env, root, maven_repo):
    """Copy and compile a disposable fixture; never modify the shipped product JAR."""
    project = root / ("early-" + jar.parent.parent.name)
    shutil.copytree(jar.parent.parent, project, ignore=shutil.ignore_patterns("target"))
    source = next(project.rglob("WidgetEodBatchJob.java"))
    before = source.read_text()
    assert before.count(SEAM_ANCHOR) == 1
    source.write_text(before.replace(SEAM_ANCHOR, SEAM_ANCHOR + SEAM, 1))
    after = source.read_text()
    assert after.replace(SEAM, "", 1) == before, "Proof seam altered identity decision code"
    patch = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="product", tofile="disposable-proof"))
    (root / (project.name + "-source-diff.log")).write_text(patch)
    identity = {
        "product_job_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "fixture_job_sha256": hashlib.sha256(after.encode()).hexdigest(),
        "seam_diff_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        "fixture_source_digest": _source_digest(project),
    }
    command = ["mvn", "-B", "-ntp"]
    if maven_repo:
        command.append(f"-Dmaven.repo.local={maven_repo}")
    output = _run(command + ["clean", "verify"], cwd=project, env=env, timeout=360)
    (root / (project.name + "-build.log")).write_text(output)
    counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for report in (project / "target/surefire-reports").glob("TEST-*.xml"):
        suite = ET.parse(report).getroot()
        for key in counts:
            counts[key] += int(suite.get(key, "0"))
    assert counts["tests"] > 0 and not any(counts[k] for k in ("failures", "errors", "skipped")), counts
    assert identity["fixture_source_digest"] == _source_digest(project)
    fixture_jar = next(p for p in (project / "target").glob("*.jar") if not p.name.endswith(".original"))
    identity.update(maven=counts, fixture_jar_sha256=hashlib.sha256(fixture_jar.read_bytes()).hexdigest())
    return fixture_jar, identity


def execution_history(sql, identity, decode):
    states = json.loads(sql(
        "SELECT COALESCE(json_agg(state),'[]'::json) FROM ("
        "SELECT json_build_object('job',row_to_json(e),'parameter_records',"
        "(SELECT json_agg(p ORDER BY parameter_name) FROM batch_job_execution_params p WHERE p.job_execution_id=e.job_execution_id),"
        "'steps',(SELECT COALESCE(json_agg(s ORDER BY step_execution_id),'[]'::json) FROM batch_step_execution s WHERE s.job_execution_id=e.job_execution_id),"
        "'serialized_context',COALESCE(c.serialized_context,c.short_context)) state FROM batch_job_execution e "
        "LEFT JOIN batch_job_execution_context c USING(job_execution_id) WHERE e.job_instance_id IN "
        "(SELECT e2.job_instance_id FROM batch_job_execution e2 JOIN batch_job_execution_params p USING(job_execution_id) "
        f"WHERE p.parameter_name='runId' AND p.parameter_value='{identity}') ORDER BY e.job_execution_id) observations"
    ))
    for state in states:
        serialized = state["serialized_context"]
        state["context"] = decode(serialized) if serialized else {}
    return states


def early_ready(state, execution_id, identity):
    if not state or not state.get("parameter_records"):
        return False
    params = {p["parameter_name"]: p for p in state["parameter_records"]}
    if not {"runId", "businessDate"} <= params.keys():
        return False
    steps = state["steps"]
    return (
        state["job"]["job_execution_id"] == execution_id and state["job"]["status"] == "STARTED"
        and params["runId"]["parameter_value"] == identity
        and params["runId"]["parameter_type"] == "java.lang.String" and params["runId"]["identifying"] == "Y"
        and params["businessDate"]["parameter_value"] == "2026-09-27"
        and params["businessDate"]["parameter_type"] == "java.time.LocalDate" and params["businessDate"]["identifying"] == "N"
        and state["context"].get("frozenBusinessDate") is None and state["context"].get("runId") is None
        and len(steps) == 1 and steps[0]["step_name"] == "widgetRunIdentityStep"
        and steps[0]["status"] == "STARTED" and steps[0]["job_execution_id"] == execution_id
    )


def postgres_early_crash(jar, home, env, root, pg, database, source_identity):
    def sql(query):
        return pg._psql(query, database=database)
    decode = _context_decoder(home, root)
    identity = "early-" + uuid.uuid4().hex[:12]
    evidence = {"run_id": identity, "original_business_date": "2026-09-27", "source_identity": source_identity, "crashes": [], "rejections": []}
    path = root / (identity + "-early-crash-evidence.log")

    def retain():
        path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")

    def observe():
        return execution_history(sql, identity, decode)

    def no_staging():
        assert sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{identity}'") == "0"

    source = sql("SELECT row_to_json(w)::text FROM widget w ORDER BY widget_id")
    flyway = pg.history(database)
    for cycle in range(2):
        marker = root / f"{identity}-{cycle}.marker"
        crash_env = dict(env, EDGEFORGE_PROOF_EARLY_MARKER=str(marker), EDGEFORGE_PROOF_EARLY_RUNID=identity)
        with runtime(jar, home, crash_env, root) as (port, owner):
            def request():
                req = Request(f"http://127.0.0.1:{port}/batch/run/widgetEodJob", data=json.dumps({"runId": identity, "businessDate": "2026-09-27"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
                try:
                    with urlopen(req, timeout=75) as response:
                        return response.status
                except (OSError, URLError):
                    return "owner-connection-ended"
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(request)
                _wait(marker.exists, "pre-identity tasklet coordination marker")
                execution_id = int(marker.read_text())
                _wait(lambda execution_id=execution_id: early_ready(observe()[-1], execution_id, identity), "durable pre-identity boundary")
                before = observe()
                no_staging()
                snapshot = database_snapshot(pg, database)
                for date in ("2026-09-27", "2026-09-28"):
                    conflict = run(port, identity, date)
                    assert conflict[0] == 409 and conflict[1]["code"] == "batch_execution_running", conflict
                    assert conflict[1]["jobExecutionId"] == execution_id and conflict[1]["ownerVerificationRequired"] is True
                assert database_snapshot(pg, database) == snapshot
                owner.kill()
                owner.wait(timeout=5)
                assert pending.result(timeout=5) == "owner-connection-ended"
                assert owner.poll() is not None and observe() == before
                crash = {"pre_crash_history": before, "dead_owner_return_code": owner.returncode, "post_crash_history": observe()}
                evidence["crashes"].append(crash)
                retain()
        with runtime(jar, home, env, root) as (port, replacement):
            snapshot = database_snapshot(pg, database)
            crash["unclassified_responses"] = [run(port, identity, date) for date in ("2026-09-27", "2026-09-28")]
            for conflict in crash["unclassified_responses"]:
                assert conflict[0] == 409 and conflict[1]["batchStatus"] == "STARTED" and conflict[1]["jobExecutionId"] == execution_id
            assert database_snapshot(pg, database) == snapshot
        assert replacement.poll() is not None and owner.poll() is not None and observe() == before
        step_id = before[-1]["steps"][0]["step_execution_id"]
        sql("BEGIN; UPDATE batch_step_execution SET status='FAILED',exit_code='FAILED',end_time=CURRENT_TIMESTAMP "
            f"WHERE job_execution_id={execution_id} AND step_execution_id={step_id} AND status='STARTED'; "
            "UPDATE batch_job_execution SET status='FAILED',exit_code='FAILED',end_time=CURRENT_TIMESTAMP "
            f"WHERE job_execution_id={execution_id} AND status='STARTED'; COMMIT;")
        after = observe()
        assert after[:-1] == before[:-1]
        assert after[-1]["job"]["status"] == "FAILED" and after[-1]["steps"][0]["status"] == "FAILED"
        assert after[-1]["serialized_context"] == before[-1]["serialized_context"]
        assert after[-1]["parameter_records"] == before[-1]["parameter_records"]
        crash["post_classification_history"] = after
        with runtime(jar, home, env, root) as (port, _replacement):
            for date in ("2026-09-28", "2026-09-29"):
                rejected = run(port, identity, date)
                evidence["rejections"].append({"requested_date": date, "response": rejected, "history": observe()})
                retain()
                assert rejected[0] == 200 and rejected[1]["status"] == "FAILED", rejected
                assert "businessDate mismatch" in observe()[-1]["job"]["exit_message"]
                no_staging()
        retain()
    retained_history = observe()
    with runtime(jar, home, env, root) as (port, _replacement):
        completed = run(port, identity)
        evidence["original_date_response"] = completed
        evidence["final_history"] = observe()
        retain()
        require_complete(completed)
        assert observe()[:-1] == retained_history
        assert len({s["job"]["job_instance_id"] for s in observe()}) == 1
        assert observe()[0]["context"]["frozenBusinessDate"] is None
        assert observe()[-1]["context"]["frozenBusinessDate"] == "2026-09-27"
        assert sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{identity}'") == sql("SELECT count(*) FROM widget")
        assert sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{identity}' AND business_date <> '2026-09-27'") == "0"
        assert run(port, identity, "2026-09-28")[0] == 409
        assert sql("SELECT row_to_json(w)::text FROM widget w ORDER BY widget_id") == source
        assert pg.history(database) == flyway
    return evidence
