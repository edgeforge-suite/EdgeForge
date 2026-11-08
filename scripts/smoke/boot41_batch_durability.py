"""Bounded PostgreSQL process/ownership probes for synthetic Batch preview apps."""

# ruff: noqa: E402 -- the optimization refusal intentionally precedes imports.

from scripts.smoke.boot41_batch_guard import require_unoptimized_python

require_unoptimized_python()

import base64
import hashlib
import json
import os
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from scripts.smoke.boot41_preview_proof import _http, _json, _unused_port


@contextmanager
def runtime(jar, home, env, root):
    port = _unused_port()
    log_path = root / ("process-" + uuid.uuid4().hex + ".log")
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                str(home / "bin/java"),
                "-jar",
                str(jar),
                f"--server.port={port}",
                "--server.address=127.0.0.1",
                "--app.eod.chunk-size=1",
            ],
            cwd=jar.parent.parent,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            end = time.monotonic() + 75
            while time.monotonic() < end:
                if process.poll() is not None:
                    raise AssertionError(
                        "Runtime exited: " + "\n".join(log_path.read_text().splitlines()[-50:])
                    )
                try:
                    if _http(port, "GET", "/actuator/health")[0] == 200:
                        break
                except URLError:
                    pass
                time.sleep(0.25)
            else:
                raise AssertionError("Runtime health timed out")
            yield port, process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
            process.wait(timeout=5)


def run(port, identity, date="2026-09-27"):
    status, _headers, body = _json(
        port, "POST", "/batch/run/widgetEodJob", {"runId": identity, "businessDate": date}
    )
    return status, json.loads(body)


def require_complete(response):
    assert response[0] == 200 and response[1]["status"] == "COMPLETED", response


def database_snapshot(pg, database):
    """All relevant records, not just counts; order-independent row hashing."""
    tables = pg._psql(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
        database=database,
    ).splitlines()
    digest = hashlib.sha256()
    for table in tables:
        rows = pg._psql(
            f'SELECT row_to_json(t)::text FROM "{table}" t ORDER BY row_to_json(t)::text',
            database=database,
        )
        digest.update((table + "\n" + rows + "\n").encode())
    return digest.hexdigest()


def _wait(predicate, description):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for " + description)


def _context_decoder(home, root):
    """Decode only this synthetic fixture's committed Batch context, outside the app."""
    classes = root / "proof-context"
    classes.mkdir(exist_ok=True)
    source = Path(__file__).resolve().parents[2] / "tests/fixtures/boot41-batch/ReadBatchContext.java"
    subprocess.run(
        [str(home / "bin/javac"), "-d", str(classes), str(source)],
        check=True, capture_output=True, timeout=20,
    )

    def decode(serialized):
        result = subprocess.run(
            [str(home / "bin/java"), "-cp", str(classes), "ReadBatchContext"],
            input=serialized, text=True, capture_output=True, check=True, timeout=5,
        )
        values = result.stdout.splitlines()
        assert len(values) == 2, "Invalid context inspection output"
        return {
            key: None if value == "-" else base64.b64decode(value, validate=True).decode()
            for key, value in zip(("runId", "frozenBusinessDate"), values, strict=True)
        }

    return decode


def _execution_snapshot(sql, identity, decode):
    rows = json.loads(sql(
        "SELECT COALESCE(json_agg(state),'[]'::json) FROM ("
        "SELECT json_build_object('job',row_to_json(e),'parameters',"
        "(SELECT json_object_agg(parameter_name,parameter_value) FROM batch_job_execution_params p "
        "WHERE p.job_execution_id=e.job_execution_id),'steps',"
        "(SELECT COALESCE(json_agg(s ORDER BY step_execution_id),'[]'::json) FROM batch_step_execution s "
        "WHERE s.job_execution_id=e.job_execution_id),'serialized_context',"
        "COALESCE(c.serialized_context,c.short_context)) AS state "
        "FROM batch_job_execution e LEFT JOIN batch_job_execution_context c USING(job_execution_id) "
        "WHERE e.job_execution_id IN (SELECT job_execution_id FROM batch_job_execution_params "
        f"WHERE parameter_name='runId' AND parameter_value='{identity}') ORDER BY e.job_execution_id) observations"
    ))
    assert isinstance(rows, list), "Invalid database execution inspection"
    if not rows:
        return None
    assert len(rows) == 1, "Crash fixture must have exactly one execution before recovery"
    state = rows[0]
    serialized = state["serialized_context"]
    state["context"] = decode(serialized) if serialized else {}
    return state


def _crash_boundary_ready(state, execution_id, identity, date):
    if not state:
        return False
    job, params, context = state["job"], state["parameters"], state["context"]
    steps = state["steps"]
    return (
        job["job_execution_id"] == execution_id
        and job["status"] == "STARTED"
        and params.get("runId") == identity
        and params.get("businessDate") == date
        and context.get("runId") == identity
        and context.get("frozenBusinessDate") == date
        and len(steps) == 2
        and all(s["job_execution_id"] == execution_id for s in steps)
        and any(s["step_name"] == "widgetRunIdentityStep" and s["status"] == "COMPLETED" for s in steps)
        and any(s["step_name"] == "widgetEodStep" and s["status"] == "STARTED" for s in steps)
    )


def _wait_for_crash_boundary(observe, identity, date, *, timeout=15):
    end = time.monotonic() + timeout
    execution_id = None
    last = None
    while time.monotonic() < end:
        last = observe()
        if last and execution_id is None:
            execution_id = last["job"]["job_execution_id"]
        if _crash_boundary_ready(last, execution_id, identity, date):
            return last
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for committed crash boundary: " + json.dumps(last, sort_keys=True))


def _classify_dead_execution(sql, observe, owner, before):
    assert owner.poll() is not None, "Cannot classify a live test-owned JVM"
    assert observe() == before, "Stale execution changed before test-owned classification"
    execution_id = before["job"]["job_execution_id"]
    data = next(s for s in before["steps"] if s["step_name"] == "widgetEodStep")
    assert _crash_boundary_ready(
        before, execution_id, before["parameters"]["runId"], before["context"]["frozenBusinessDate"]
    )
    # Exact dead owner's running records only; the committed identity step is immutable.
    sql(
        "BEGIN; UPDATE batch_step_execution SET status='FAILED',exit_code='FAILED',end_time=CURRENT_TIMESTAMP "
        f"WHERE job_execution_id={execution_id} AND step_execution_id={data['step_execution_id']} AND status='STARTED'; "
        "UPDATE batch_job_execution SET status='FAILED',exit_code='FAILED',end_time=CURRENT_TIMESTAMP "
        f"WHERE job_execution_id={execution_id} AND status='STARTED'; COMMIT;"
    )
    after = observe()
    assert after["job"]["job_execution_id"] == execution_id and after["job"]["status"] == "FAILED"
    assert after["serialized_context"] == before["serialized_context"]
    identity_before = next(s for s in before["steps"] if s["step_name"] == "widgetRunIdentityStep")
    assert next(s for s in after["steps"] if s["step_name"] == "widgetRunIdentityStep") == identity_before
    assert next(s for s in after["steps"] if s["step_name"] == "widgetEodStep")["status"] == "FAILED"
    return after


def postgres_durability(jar, home, env, root, pg, database):
    def sql(query):
        return pg._psql(query, database=database)

    prefix = "durable-" + uuid.uuid4().hex[:8]
    complete, failed, stopped, abrupt = (
        prefix + "-" + s for s in ("complete", "failed", "stopped", "abrupt")
    )
    with runtime(jar, home, env, root) as (port, owner):
        history = pg.history(database)
        require_complete(run(port, complete))
        sql(
            "ALTER TABLE widget_staging ADD CONSTRAINT proof_durable_sink "
            f"CHECK(run_id NOT LIKE '{prefix}%' OR payload_key <> 'FAIL')"
        )
        sql(
            "INSERT INTO widget(widget_id,payload_key) VALUES "
            "('00000000-0000-0000-0000-000000000011','OK1'),"
            "('00000000-0000-0000-0000-000000000012','FAIL'),"
            "('00000000-0000-0000-0000-000000000013','OK3')"
        )
        source = sql("SELECT row_to_json(w)::text FROM widget w ORDER BY widget_id")
        for identity in (failed, stopped):
            response = run(port, identity)
            assert response[0] == 200 and response[1]["status"] == "FAILED", response
            assert sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{identity}'") == "1"
    assert owner.poll() is not None
    # Classification is a simulated operator action in this test-owned database
    # after its JVM is confirmed gone; it is not a generated recovery operation.
    stopped_execution = sql(
        "SELECT job_execution_id FROM batch_job_execution_params "
        f"WHERE parameter_name='runId' AND parameter_value='{stopped}'"
    )
    assert stopped_execution.isdigit()
    identity_query = (
        "SELECT row_to_json(s)::text FROM batch_step_execution s "
        f"WHERE job_execution_id={stopped_execution} AND step_name='widgetRunIdentityStep'"
    )
    stopped_identity = sql(identity_query)
    assert json.loads(stopped_identity)["status"] == "COMPLETED"
    sql(
        "BEGIN; UPDATE batch_step_execution SET status='STOPPED',exit_code='STOPPED' "
        f"WHERE status='FAILED' AND job_execution_id={stopped_execution}; "
        "UPDATE batch_job_execution SET status='STOPPED',exit_code='STOPPED' "
        f"WHERE status='FAILED' AND job_execution_id={stopped_execution}; COMMIT;"
    )
    assert sql(identity_query) == stopped_identity
    sql("ALTER TABLE widget_staging DROP CONSTRAINT proof_durable_sink")
    with runtime(jar, home, env, root) as (port, _owner):
        assert pg.history(database) == history
        completed_records = database_snapshot(pg, database)
        for date in ("2026-09-27", "2026-09-28"):
            response = run(port, complete, date)
            assert response[0] == 409 and response[1]["code"] == "batch_instance_completed", (
                response
            )
        assert database_snapshot(pg, database) == completed_records
        for identity in (failed, stopped):
            rows = sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{identity}'")
            mismatch = run(port, identity, "2026-09-28")
            assert mismatch[0] == 200 and mismatch[1]["status"] == "FAILED", mismatch
            assert sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{identity}'") == rows
            require_complete(run(port, identity))
            assert sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{identity}'") == "3"
            assert (
                sql(
                    "SELECT count(DISTINCT e.job_instance_id) FROM batch_job_execution e JOIN batch_job_execution_params p "
                    f"USING(job_execution_id) WHERE p.parameter_name='runId' AND p.parameter_value='{identity}'"
                )
                == "1"
            )
            assert run(port, identity)[0] == 409
    decode = _context_decoder(home, root)
    evidence = {"run_id": abrupt, "original_business_date": "2026-09-27"}

    def observe():
        state = _execution_snapshot(sql, abrupt, decode)
        evidence["last_database_observation"] = state
        return state
    # JSON content under .log is retained by the existing CI failure-artifact glob.
    evidence_path = root / (abrupt + "-crash-evidence.log")

    def retain():
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")

    # Hold only the synthetic sink. Kill our JVM only after the frozen identity
    # is committed and the exact execution's data step is running.
    lock_env = os.environ.copy()
    lock_env["PGPASSWORD"] = pg.password
    lock_env["PGAPPNAME"] = prefix + "-sink-lock"
    lock = subprocess.Popen(
        [
            str(pg.psql),
            "-X",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            pg.host,
            "-p",
            pg.port,
            "-U",
            pg.user,
            "-d",
            database,
        ],
        env=lock_env,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        lock.stdin.write(b"BEGIN; LOCK widget_staging IN ACCESS EXCLUSIVE MODE;\n")
        lock.stdin.flush()
        _wait(
            lambda: (
                sql(
                    "SELECT count(*) FROM pg_locks WHERE relation='widget_staging'::regclass "
                    "AND mode='AccessExclusiveLock' AND granted"
                )
                == "1"
            ),
            "synthetic sink lock",
        )
        with runtime(jar, home, env, root) as (port, owner):

            def blocked_request():
                request = Request(
                    f"http://127.0.0.1:{port}/batch/run/widgetEodJob",
                    data=json.dumps({"runId": abrupt, "businessDate": "2026-09-27"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urlopen(request, timeout=30) as response:
                        return response.status
                except (OSError, URLError):
                    return "owner-connection-ended"

            with ThreadPoolExecutor(max_workers=1) as executor:
                request = executor.submit(blocked_request)
                try:
                    evidence["pre_crash"] = _wait_for_crash_boundary(observe, abrupt, "2026-09-27")
                finally:
                    retain()
                conflict = run(port, abrupt)
                assert conflict[0] == 409 and conflict[1]["code"] == "batch_execution_running", (
                    conflict
                )
                assert conflict[1]["ownerVerificationRequired"] is True
                assert type(conflict[1]["jobExecutionId"]) is int
                assert conflict[1]["batchStatus"] == "STARTED"
                assert conflict[1]["jobExecutionId"] == evidence["pre_crash"]["job"]["job_execution_id"]
                assert (
                    sql(
                        "SELECT count(*) FROM batch_job_execution_params "
                        f"WHERE parameter_name='runId' AND parameter_value='{abrupt}'"
                    )
                    == "1"
                )
                owner.kill()
                owner.wait(timeout=5)
                crash_owner = owner
                evidence["dead_owner_return_code"] = crash_owner.returncode
                evidence["post_crash"] = observe()
                assert evidence["post_crash"] == evidence["pre_crash"]
                retain()
                assert request.result(timeout=5) == "owner-connection-ended"
        assert owner.poll() is not None
    finally:
        # Terminating psql alone can leave its backend holding the lock.
        # Select only this probe's named session in its own disposable database.
        sql(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname='{database}' AND application_name='{prefix}-sink-lock'"
        )
        if lock.poll() is None:
            lock.terminate()
        lock.stdin.close()
        lock.wait(timeout=5)
    with runtime(jar, home, env, root) as (port, owner):
        before = database_snapshot(pg, database)
        for date in ("2026-09-27", "2026-09-28"):
            conflict = run(port, abrupt, date)
            assert conflict[0] == 409 and conflict[1]["batchStatus"] == "STARTED", conflict
            assert conflict[1]["ownerVerificationRequired"] is True
            assert conflict[1]["jobExecutionId"] == evidence["pre_crash"]["job"]["job_execution_id"]
        assert database_snapshot(pg, database) == before
    assert owner.poll() is not None
    evidence["post_classification"] = _classify_dead_execution(sql, observe, crash_owner, evidence["post_crash"])
    retain()
    with runtime(jar, home, env, root) as (port, _owner):
        rows = sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{abrupt}'")
        mismatch = run(port, abrupt, "2026-09-28")
        evidence["changed_date_response"] = mismatch
        evidence["staging_rows_before_changed_date"] = int(rows)
        evidence["staging_rows_after_changed_date"] = int(sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{abrupt}'"))
        retain()
        assert mismatch[0] == 200 and mismatch[1]["status"] == "FAILED", mismatch
        assert evidence["staging_rows_after_changed_date"] == evidence["staging_rows_before_changed_date"]
        require_complete(run(port, abrupt))
        assert sql(f"SELECT count(*) FROM widget_staging WHERE run_id='{abrupt}'") == "3"
        assert (
            sql(
                "SELECT count(DISTINCT e.job_instance_id) FROM batch_job_execution e "
                "JOIN batch_job_execution_params p USING(job_execution_id) "
                f"WHERE p.parameter_name='runId' AND p.parameter_value='{abrupt}'"
            )
            == "1"
        )
        assert sql("SELECT row_to_json(w)::text FROM widget w ORDER BY widget_id") == source
        assert pg.history(database) == history
    return {
        "completed_across_replacement": True,
        "failed_and_classified_stopped_restart": True,
        "same_instance_and_frozen_date": True,
        "concurrent_duplicate_serialized": True,
        "abrupt_running_replacement_fails_closed": True,
        "classification_after_owner_gone": True,
        "source_rows_immutable": True,
        "flyway_history_preserved": True,
        "crash_boundary_evidence": evidence,
    }


def old_schema_refusal(preview_jar, legacy_jar, home, preview_env, legacy_env, root, pg, database):
    with runtime(legacy_jar, home, legacy_env, root) as (port, _owner):
        pg._psql(
            "INSERT INTO widget(widget_id,payload_key) VALUES "
            "('00000000-0000-0000-0000-000000000088','protected-legacy-row')",
            database=database,
        )
        require_complete(run(port, "legacy-protected"))
        assert (
            pg._psql(
                "SELECT count(*) FROM widget_staging WHERE run_id='legacy-protected'",
                database=database,
            )
            == "1"
        )
    before = database_snapshot(pg, database)
    try:
        with runtime(preview_jar, home, preview_env, root):
            raise AssertionError("Preview unexpectedly started against the Batch 5 fixture")
    except AssertionError as exc:
        if "Runtime exited:" not in str(exc) or "Validate failed" not in str(exc):
            raise
    assert database_snapshot(pg, database) == before
    return {
        "disposable_batch5_startup_refused": True,
        "all_business_batch_and_flyway_records_unchanged": True,
        "universal_old_database_detection": False,
    }
