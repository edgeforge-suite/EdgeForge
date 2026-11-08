# Build prompt — M5a-S2 durable Batch identity and bounded restart

**Repo:** EdgeForge Engine only

**Base:** current `origin/main` after the M5a rev-14 design PR merges; fetch and record the exact SHA

**Branch:** `<agent>/feature/m5a-s2-batch-identity`

**PR:** `[FEATURE] Add M5a-S2 durable Batch identity and bounded restart`

Open as a draft PR.

## Authority and scope

Implement only **M5a-S2** from
[`generated-app-staging-handoff-run-semantics-design.md`](generated-app-staging-handoff-run-semantics-design.md),
especially §6.1, §7.1–§7.4, §9 AC3/AC4/AC5/AC5b/AC7, and §10.1. Ground abrupt-death behavior in
[`m5a-s2-abrupt-restart-feasibility-2026-08-17.md`](../test-results/m5a-s2-abrupt-restart-feasibility-2026-08-17.md).

M5a-S1 is delivered. Do not reopen its manifest/schema contract or DDL/mapping validation. This slice
adds Batch metadata, parameter identity, the run-identity tasklet, and bounded conflict/recovery
diagnostics. It does **not** yet make opted-in generation safe for public use because S3 still owns the
per-handoff unique constraint, upsert, and destructive-clear removal.

## Required implementation

### 1. Package-scoped Batch metadata

- Add the fixed, package-scoped `internal_schema` singleton id **`pkg-batch-metadata`** when at least
  one CRUD staging handoff has validated `run_semantics`.
- It is not per-handoff, receives no ordinal, and is retained for the life of a managed package once
  established.
- Record `schema_contract_version: 1`, `target_profile`, and deterministic `content_sha256` exactly as
  §6.1 specifies. The canonical hash payload includes the contract version, target profile, pinned
  Spring Batch metadata schema version, and ordered normalized emitted SQL. Exclude Engine version,
  migration ordinal/path, generation id, timestamps, and local paths.
- Same id/version/fingerprint is retained byte-for-byte. Fingerprint drift without a version bump is
  an Engine integrity error. Unknown versions or version/fingerprint transitions fail closed without
  changing baseline or migrations.
- Emit exactly one additive, immutable Flyway migration for the profile-appropriate Batch metadata
  schema. Existing migrations remain byte-identical; deterministic migration allocation uses the
  existing high-water inventory. Pin Spring Batch `5.1.2` schema content and disable any initializer
  that could double-create PostgreSQL tables.
- PostgreSQL and H2 both use profile-appropriate Flyway-owned Batch schema SQL through the singleton;
  pin Boot initialization off so it cannot double-create. PostgreSQL is the durable cross-process
  profile. H2 re-creates its in-memory database per JVM and remains same-process only.
- Do not implement the S3 per-handoff `m5a-staging-*` entries in this slice.

### 2. Job parameters and trigger

For opted-in generated staging jobs only:

- Keep `POST /batch/run/{jobName}` and require exactly this closed JSON body:
  `{"runId":"RUN-001","businessDate":"2026-08-17"}`. Reject a missing body,
  missing/blank member, malformed ISO local date, or unknown member before launch.
- Add `runId` as the **sole identifying** JobParameter.
- Add `businessDate` as explicitly **non-identifying**.
- Remove the uniqueness-only `run.at` parameter from the opted-in path.
- Carry the selected physical run-ID column's `ValidatedStagingDdl.max_length` into generation-only
  metadata. Before width validation, reject a runId unless it is non-blank and equals Java
  `String.strip()`; do not trim or otherwise rewrite it. Apply this canonicality rule to `CHAR`,
  `VARCHAR`, and `TEXT` on H2 and PostgreSQL.
- Compute `effectiveRunIdMax = min(physicalMax, 2500)`, treating `TEXT`/missing physical max as
  infinity. The 2500 ceiling is Spring Batch `5.1.2`'s
  `BATCH_JOB_EXECUTION_PARAMS.PARAMETER_VALUE VARCHAR(2500)` on both profiles. Validate Java UTF-16
  `String.length()` before `JobLauncher.run`; accept the exact effective bound and reject over-bound
  input before any Batch row exists. This metric is safe for H2 and conservative for PostgreSQL.
- Use the exact accepted runId unchanged for the identifying JobParameter, execution
  context/diagnostics, and staging writer. The generated console submits the entered text unchanged;
  the server-side canonicality check is authoritative.
- Emit test-console descriptors per job. Opted-in cards use `FORM`/`JSON_BODY` with required `runId`
  text and `businessDate` date fields; include `effectiveRunIdMax` as the run-ID field hint. Legacy
  cards remain `NONE`/`NONE` and send no body. The server remains authoritative.
- Preserve byte-identical legacy controller, `run.at`, and card behavior when `run_semantics` is
  absent. Prove a mixed app emits and executes both contracts without cross-applying either one.

### 3. Run-identity tasklet

- Add a generated tasklet step before the data/chunk step.
- Configure it with `allowStartIfComplete(true)` so it runs on every legally created execution,
  including restarts.
- On the first execution, persist the supplied business date in the JobExecution context in a
  committed transaction before any data work.
- On every later execution, read the inherited frozen date and compare it with the non-identifying
  supplied date. A mismatch fails before the staging writer/data step runs and names the runId,
  frozen date, and supplied date without leaking unrelated state.
- Do not infer the frozen date from current time or reconstruct it from Engine/package hashes.

### 4. Completed/running/stale conflict handling

- `JobInstanceAlreadyCompleteException` returns HTTP 409 for the existing completed instance.
- After `JobExecutionAlreadyRunningException`, use `JobExplorer`/repository state to identify the
  matching job name + identifying runId. Do not parse the exception message.
- For an observed running status (`STARTING`, `STARTED`, or `STOPPING`), return HTTP 409 with
  `code=batch_execution_running`, caller `runId`, `jobExecutionId`, the **actual** `batchStatus`, and
  `ownerVerificationRequired=true`. Do not label a live execution stale.
- If the execution becomes terminal between launcher rejection and lookup, return HTTP 409 with
  `code=batch_execution_state_changed`, actual status/id, and `requeryRequired=true`; do not relaunch
  inside the same request. If no authoritative matching row is found, return
  `code=batch_execution_state_unavailable`, `batchStatus=UNKNOWN`, and `requeryRequired=true`, with
  no fabricated execution id.
- Do **not** auto-mark any running execution failed at startup or launch time.
- Do **not** add a generated recovery REST endpoint, authenticated or otherwise, in S2.
- Do **not** assume a single replica.
- Document that an authorized operator may classify an execution only after independently confirming
  no owner remains. The adopter-owned operational mechanism is outside this slice.
- Defer automatic multi-instance recovery until lease/heartbeat or equivalent fencing is designed.

### 5. Reader boundary

- Do not add a generic keyset/frozen-upper-bound reader. Generated entity ids have no universal
  insertion-stable ordering contract.
- Retain the immutable-source-during-run precondition.
- Leave AC2/AC2b implementation to S3; AC2b must continue to show source mutation as outside the v1
  guarantee.

### 6. Keep the public execution gate

The S1 fail-closed gate on public `generate`, `plan`, and `apply` remains active after S2. Those entry
points must still refuse opted-in packages until S3 delivers the unique constraint, profile-pinned
upsert, and clear-on-start removal. Test S2 through focused emitter/internal integration fixtures or a
test-only assembled app; do not add a production bypass flag or expose unsafe S2-only output.

## Required proof

### Determinism and ownership

- Block absent: generated output remains byte-identical to the exact pinned pre-S2 baseline.
- Block present in internal tests: Batch metadata SQL, singleton baseline entry, Java tasklet/trigger,
  request/card descriptors, and diagnostics are deterministic for fixed inputs.
- Existing Flyway migrations and preserved baselines remain byte-identical outside their approved
  greenfield/adoption/apply ownership transitions.
- Same singleton content emits no duplicate migration; collisions and fingerprint/version drift fail
  before mutation.

### AC3 — completed conflict

Run a job to `COMPLETED`, re-submit the same runId, and prove:

- HTTP 409 / `JobInstanceAlreadyCompleteException` mapping;
- no new JobInstance or staging write; and
- the response does not imply the completed run was retried.

### AC4 — concurrent conflict

Launch the same runId concurrently and prove one execution owns the instance while the other receives
HTTP 409. Prove exactly one JobInstance and no application-level check-then-act race. Cover repository
observations of `STARTING`, `STARTED`, and `STOPPING`, plus the terminal-transition and missing-lookup
races; every response reports actual state or explicit unavailability, never fabricated `STARTED`.

### AC5 — state matrix for a changed business date

- Authoritative `FAILED`/`STOPPED`: a new execution for the same JobInstance is legally created; the
  run-identity tasklet rejects the changed date before the data/staging step.
- Latest execution `STARTING`/`STARTED`/`STOPPING`: launcher returns
  `JobExecutionAlreadyRunningException`; generated response is the running-state 409 with the actual
  status and execution id; tasklet does not run.
- Terminal transition after launcher rejection: response is the state-changed 409; missing lookup is
  state-unavailable. Neither path relaunches or invents an execution status/id.
- `COMPLETED`: launcher returns `JobInstanceAlreadyCompleteException`; response is 409; tasklet does
  not run.
- Exactly one JobInstance exists in every case.

### AC5b — abrupt-death boundary and explicit classification

Use Spring Batch `5.1.2` and a real PostgreSQL container:

1. Launch with identifying runId and non-identifying businessDate.
2. Let the identity tasklet commit its context.
3. Hold the data step and hard-kill the process.
4. Query and record `BATCH_JOB_EXECUTION=STARTED`, identity step `COMPLETED`, data step `STARTED`, and
   the frozen date in execution context.
5. Directly relaunch with the same date and a different date. Both must fail closed before any step
   with `JobExecutionAlreadyRunningException`, the same execution id, actual observed `STARTED`
   status, ownership-review requirement, and no new Batch rows.
6. After separately evidencing that the owner is gone, simulate an authorized operator classification
   to `FAILED` in test infrastructure only. This is not generated startup behavior or a runtime API.
7. Relaunch with the changed date. Prove a second JobExecution for the same single JobInstance is
   created, the identity tasklet rejects the mismatch, and no data/staging step is created.

The proof must fail if the stale-`STARTED` gate or `allowStartIfComplete(true)` is removed.

### AC5c — physical/Batch run-ID equivalence and storage bound

Against both real PostgreSQL and generated-app H2, use `CHAR(8)` as the opted-in physical run-ID
column. Prove `RUN-1` is accepted and the identical string reaches Batch identity and the staging
writer. Prove `RUN-1 ` and ` RUN-1` receive the stable pre-launch 4xx, create no
JobInstance/JobExecution, and write no staging row. Repeat the canonicality guard for `VARCHAR` and
`TEXT`. Prove a 2500-UTF-16-unit run ID is accepted and 2501 is rejected for both `TEXT` and
`VARCHAR(3000)`. On H2, prove one supplementary character (Java `String.length() == 2`) is rejected
for `VARCHAR(1)` and accepted for `VARCHAR(2)`. Assert zero Batch/staging mutation on every refusal,
the same effective maximum in the console hint, and negative controls showing the tests fail if either
the `strip()` equality or effective-max guard is removed.

### AC7 — metadata durability, singleton integrity, and bounded restart

- Real PostgreSQL/Flyway creates the pinned `BATCH_JOB_*` schema and survives process replacement.
- H2 proves same-process restart only.
- `pkg-batch-metadata` id/version/fingerprint and SQL inventory are deterministic and retained.
- Native restart succeeds from an authoritative `FAILED` or `STOPPED` state with the same date.
- A persisted running status fails closed with actual repository state and ownership review; do not
  label persistence itself automatic crash recovery.

## Focused regression tests

Add tests for:

- sole-identifying runId and non-identifying businessDate;
- absent/blank/malformed/unknown trigger-body inputs and the exact JSON wire shape;
- leading/trailing whitespace refusal with no silent trimming and no Batch/staging mutation;
- physical-width and Batch-2500 effective bounds for `CHAR`/`VARCHAR`/`TEXT`, measured by Java UTF-16
  length and checked before launch;
- H2 supplementary-character `VARCHAR(1)`/`VARCHAR(2)` boundary and 2500/2501 cases;
- opted-in `FORM`/`JSON_BODY` and legacy `NONE`/`NONE` cards in one mixed app;
- first-execution context persistence and later comparison;
- completed, concurrent `STARTING`/`STARTED`/`STOPPING`, lookup-transition/unavailable,
  FAILED/STOPPED-same-date, and changed-date paths;
- deterministic singleton fingerprint and migration bytes;
- migration inventory collision and initializer double-create prevention;
- H2 same-process scope and PostgreSQL cross-process durability;
- no generic keyset reader;
- public generate/plan/apply refusal still occurring with zero writes; and
- no S3 unique/upsert/clear-removal behavior in the diff.

Run focused tests, the full Engine suite, generated-app compilation, and the real PostgreSQL AC5b/AC7
proof. Record exact Spring Batch/PostgreSQL versions and final persisted Batch states.

## Hard boundaries

- No manifest/schema changes and no S1 reopening.
- No S3 unique constraint, upsert, clear-on-start removal, dedup execution, or AC2/AC2b claims.
- No automatic Batch-table mutation, startup recovery, recovery endpoint, or single-replica premise.
- No keyset/high-water reader inference.
- No event-delivery implementation and no tracker update.
- No public relaxation of the S1 execution refusal.
- No new EdgeForge runtime dependency in generated apps.

## PR body

Report the singleton/migration contract, exact trigger/card shape, parameter identity, canonicality,
effective physical/Batch UTF-16 width checks, actual-state conflict responses,
AC3/AC4/AC5/AC5b/AC5c/AC7 results, exact abrupt-death Batch rows, H2/PostgreSQL scope, determinism,
full-suite result, and the continued S1 public refusal. State that S3 remains required before opted-in
packages may generate or apply. Report evidence and residual risk without declaring merge-readiness.
