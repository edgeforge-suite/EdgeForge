# M5a-S2 abrupt-restart feasibility — 2026-08-17

## Result

**Confirmed design correction required.** PostgreSQL durably retained Spring Batch state after an
abrupt JVM death, but Spring Batch did not treat that state as immediately restartable. The latest
`JobExecution` remained `STARTED`, and both direct relaunch attempts failed with
`JobExecutionAlreadyRunningException` before the run-identity tasklet could execute.

This is disposable design-feasibility evidence, not a generated-app acceptance result and not a
production recovery procedure.

## Pinned setup

- Engine source baseline: `bd401cb`
- Java: `17.0.18`
- Spring Batch: `org.springframework.batch:spring-batch-core:5.1.2`
- H2 length probe: `com.h2database:h2:2.2.224`
- PostgreSQL JDBC driver: `42.7.3`
- PostgreSQL server: `16.4 (Debian 16.4-1.pgdg120+2)`
- Container image (pullable digest):
  `postgres@sha256:e62fbf9d3e2b49816a32c400ed2dba83e3b361e6833e624024309c35d334b412`
- Reproducible Maven fixture coordinates: `proof:m5a-s2-abrupt-restart:1.0.0`
- Committed source SHA-256:
  - `pom.xml`:
    `cbd158c5e8c8b834e4286dbf3f1e86b05184b21c9cfaa6a3a817188935f6d4b0`
  - `AbruptRestartProof.java`:
    `4ae065ca64367580e039e685fca3f3e7fa844d4f49ca2e31d40e67422c7bf89c`

The exact small source fixture and bounded runner are committed under
[`fixtures/m5a-s2-abrupt-restart/`](fixtures/m5a-s2-abrupt-restart/). Maven output, logs, the
PostgreSQL container/database, and the copied working tree are created under `/tmp` and removed by the
runner after success or failure.

## Reproduce

Prerequisites are Java 17, Maven, Docker, and access to pull the pinned PostgreSQL digest. From the
repository root, run:

```bash
docs/test-results/fixtures/m5a-s2-abrupt-restart/run-proof.sh
```

The runner builds the committed Maven fixture, creates a disposable PostgreSQL container on an
automatically allocated loopback port, and waits boundedly until a JDBC `SELECT 1` succeeds through
that exact mapped host, port, database, user, and password. The final post-loop assertion repeats the
same JDBC predicate; it does not rely on PostgreSQL's temporary initialization Unix socket. Each probe
sets pgJDBC `connectTimeout=2` and `socketTimeout=2` and applies a two-second JDBC statement timeout to
the readiness query, so the 60-attempt loop cannot enter an unbounded driver call. The runner then
initializes the Spring Batch `5.1.2` schema, hard-kills the blocked Java process, asserts the persisted
rows, and exercises both direct refusals. It performs the explicitly labelled test-only operator
classification, proves the changed-date tasklet mismatch, prints a stable summary, and removes all
disposable resources. The runner itself contains the exact commands and SQL; no hand-reconstructed
step is required.

The committed runner was rerun twice consecutively from the PR branch and returned the same stable
summary on both runs:

```text
M5A_S2_FEASIBILITY=PASS
POSTGRES_JDBC_ENDPOINT_READY=PROVEN
POSTGRES_JDBC_TIMEOUTS_SECONDS=2
POSTGRES_BATCH_PARAMETER_VALUE_MAX=2500
H2_BATCH_PARAMETER_VALUE_MAX=2500
H2_UTF16_VARCHAR1_SUPPLEMENTARY=REJECTED
H2_UTF16_VARCHAR2_SUPPLEMENTARY=ACCEPTED
POSTGRES_CHAR_TRAILING_SPACE_COLLISION=PROVEN
ABRUPT_JOB_STATUS=STARTED
IDENTITY_STEP_STATUS=COMPLETED
DATA_STEP_STATUS=STARTED
SAME_DATE_RELAUNCH=JobExecutionAlreadyRunningException
CHANGED_DATE_RELAUNCH=JobExecutionAlreadyRunningException
POST_CLASSIFICATION_RELAUNCH=FAILED_DATE_MISMATCH
FINAL_JOB_INSTANCES=1
FINAL_JOB_EXECUTIONS=2
FINAL_STEP_EXECUTIONS=3
```

## Physical run-ID equality boundary

The same runner creates a disposable table with `run_id CHAR(8)`, `dedup_key INTEGER`, and
`UNIQUE(run_id, dedup_key)`. After inserting `('RUN-1', 1)`, PostgreSQL rejects
`('RUN-1 ', 1)` as a duplicate key. Java/Spring Batch would otherwise treat those two caller strings
as different identifying parameters. This proves why S2 must reject boundary whitespace before
`JobLauncher.run` and use the exact accepted value unchanged for Batch identity and staging. Silent
trimming is not selected.

## Effective storage-length boundary

The runner also initializes the pinned Spring Batch `5.1.2` schema on PostgreSQL and H2 and reads
`BATCH_JOB_EXECUTION_PARAMS.PARAMETER_VALUE` as `VARCHAR(2500)` on each. A separate pinned H2
`2.2.224` probe attempts to insert one supplementary Unicode character into `VARCHAR(1)` using an
ASCII `STRINGDECODE` escape. H2 rejects it as length 2; the same value is accepted by `VARCHAR(2)`.

These results ground the rev-14 pre-launch rule: compute the lesser of the physical staging width and
2500, treating `TEXT` as physically unbounded, and measure Java UTF-16 `String.length()`. The metric
matches H2's stricter behavior and is conservative for PostgreSQL. The generated server must reject a
value beyond that effective maximum before `JobLauncher.run`; the console hint mirrors the same bound
but is not the authority.

## Proof topology

The disposable job used one `JobInstance` named `m5aS2AbruptRestart` and two steps:

1. `runIdentity`, a tasklet with `allowStartIfComplete(true)`, stored
   `frozenBusinessDate=2026-08-17` in the `JobExecution` context and explicitly persisted it.
2. `dataStep` printed a readiness sentinel and then blocked without committing.

The launch parameters were:

| Parameter | Value | Identifying |
|---|---|---|
| `runId` | `RUN-001` | yes |
| `businessDate` | `2026-08-17` | no |

The first process emitted:

```text
IDENTITY_STEP_ACCEPTED=2026-08-17
DATA_STEP_WAITING
```

The JVM was then terminated with `SIGKILL`. No Batch-table mutation occurred before either direct
relaunch attempt.

## Persisted state after abrupt death

The `JobExecution` context survived and decoded to include:

```text
frozenBusinessDate
2026-08-17
batch.version
5.1.2
```

`BATCH_JOB_EXECUTION`:

| `JOB_EXECUTION_ID` | `JOB_INSTANCE_ID` | `STATUS` | `EXIT_CODE` | `END_TIME` |
|---:|---:|---|---|---|
| 1 | 1 | `STARTED` | `UNKNOWN` | null |

`BATCH_STEP_EXECUTION`:

| `STEP_EXECUTION_ID` | `JOB_EXECUTION_ID` | `STEP_NAME` | `STATUS` | `EXIT_CODE` | `COMMIT_COUNT` |
|---:|---:|---|---|---|---:|
| 1 | 1 | `runIdentity` | `COMPLETED` | `COMPLETED` | 1 |
| 2 | 1 | `dataStep` | `STARTED` | `EXECUTING` | 0 |

This proves durable metadata and frozen-date persistence. It does not prove automatic crash recovery.

## Direct relaunch results

Relaunch 1 used the same `runId` and the same date. Relaunch 2 used the same `runId` and
`businessDate=2026-08-18`. Both exited with the same result:

```text
LAUNCH_EXCEPTION=org.springframework.batch.core.repository.JobExecutionAlreadyRunningException
LAUNCH_MESSAGE=A job execution for this job is already running: JobExecution: id=1, ...
status=STARTED, exitStatus=exitCode=UNKNOWN;...
```

After both refusals:

| Inventory | Count |
|---|---:|
| Job instances | 1 |
| Job executions | 1 |
| Step executions | 2 |

The non-identifying date did not create another `JobInstance`, and its mismatch could not be checked:
the launcher rejected the stale/running execution before any step ran.

## Separately evidenced operator classification

After confirming the proof JVM no longer existed, the disposable database was explicitly updated in
one transaction to classify execution 1 and its still-`STARTED` data step as `FAILED`. This manual SQL
was an operator-action simulation only; it was not run before the direct relaunches, is not proposed as
generated runtime code, and is not an automatic startup action.

```sql
BEGIN;
UPDATE batch_step_execution
SET status = 'FAILED', exit_code = 'FAILED',
    exit_message = 'operator classified stale after owner confirmation',
    end_time = CURRENT_TIMESTAMP, last_updated = CURRENT_TIMESTAMP,
    version = version + 1
WHERE step_execution_id = 2 AND status = 'STARTED';
UPDATE batch_job_execution
SET status = 'FAILED', exit_code = 'FAILED',
    exit_message = 'operator classified stale after owner confirmation',
    end_time = CURRENT_TIMESTAMP, last_updated = CURRENT_TIMESTAMP,
    version = version + 1
WHERE job_execution_id = 1 AND status = 'STARTED';
COMMIT;
```

Relaunch with `runId=RUN-001` and `businessDate=2026-08-18` then legally created job execution 2 for
the existing job instance. The `runIdentity` tasklet ran and failed with:

```text
java.lang.IllegalStateException:
businessDate mismatch: frozen=2026-08-17, supplied=2026-08-18
```

Final persisted state:

| Execution | Job status | Step | Step status |
|---:|---|---|---|
| 1 | `FAILED` | `runIdentity` | `COMPLETED` |
| 1 | `FAILED` | `dataStep` | `FAILED` |
| 2 | `FAILED` | `runIdentity` | `FAILED` |

There was still exactly one `JobInstance`; there were two `JobExecution` rows and three
`StepExecution` rows. No `dataStep` row existed for execution 2, proving the date mismatch failed
before data/staging work.

## Design consequence

- PostgreSQL durability and automatic crash recovery are different properties.
- Native restart is directly available from an authoritative restartable state such as `FAILED` or
  `STOPPED`.
- Abrupt death may leave a running status such as `STARTED`; direct relaunch must fail closed and
  surface the execution id plus the actual repository status for ownership review.
- Automatically marking `STARTED` failed during startup is unsafe in a multi-replica deployment: a
  different replica may still own the execution.
- M5a v1 therefore uses explicit operator classification after ownership confirmation. Automatic
  multi-instance recovery remains deferred until lease/heartbeat or equivalent fencing exists.

## Residual risk

The proof does not select or validate an adopter's authorization, audit, ownership-confirmation, or
Batch-row classification procedure. It demonstrates the Spring Batch state boundary that such a
procedure must respect. H2 was not used because its generated in-memory profile is intentionally
same-process only.
