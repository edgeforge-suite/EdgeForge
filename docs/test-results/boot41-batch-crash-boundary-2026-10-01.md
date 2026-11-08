# Batch Crash-Proof Boundary Correction, 2026-10-01

Candidate: **EF-V5-M2-ENGINE-BOOT41-S3**, revision **1**, PR #320.
This is the maintainer-authorized proof-only amendment, not a Batch product fix.
Clean locally tested helper commit: `7575098c9f3f5472d8fe3be03b412fcfad6758ac`.
The generator remains the previously tested S3 implementation at
`80aa40ace3dd773acdb9474e27df4aee937c3d36`; subsequent commits did not alter
generated Batch behavior, schema, businessDate semantics or recovery policy.

## Original Failed Observation: Preserved, Not Reclassified as Passing

[Generated-app run 36779765648](https://github.com/santosh-sh/EdgeForge/actions/runs/36779765648)
failed at head `9144d363f0e693ff41038f6027ff9de998c0082a`. Its Java 21 synthetic
run `durable-fd642f03-abrupt` requested `businessDate=2026-09-27`. The old helper
killed the JVM after observing only job `STARTED`; its process log last showed
`widgetRunIdentityStep` executing, without observing the committed frozen context
or completed identity step. After test-owned classification, a replacement
accepted `2026-09-28` and returned HTTP 200 / `COMPLETED`, jobId 6. That failure
and the original process/build logs remain separately retained in the run's
`boot41-batch-proof` artifact and the local failure bundle.

The corrected test does **not** establish or approve behavior before the identity
commit. No generated recovery mechanism, adopter-data operation or risk acceptance
is supplied. The original run's Kafka/default-preservation steps were skipped,
not passed; they must actually execute successfully on the amended PR head.

## Corrected Barrier and Classification

The helper polls database state for at most 15 seconds, with bounded inspection
subprocesses. A single database query collects the exact execution's parameters,
job, step rows and committed serialized job context. A test-only, size-bounded
JDK reader outside the generated application decodes that synthetic string-valued
context with an explicit type allow-list. JVM termination requires all of:

- The original runId and `frozenBusinessDate=2026-09-27` in committed context,
  with matching original parameters.
- The same execution's `widgetRunIdentityStep` is `COMPLETED`.
- Its `widgetEodStep` and job are both `STARTED`.

The synthetic sink lock stays in a task-owned session until bounded proof cleanup;
there is no timed sleep used to infer the crash boundary. Pre/post-crash snapshots
must match. Classification verifies the original JVM is dead and that its exact
snapshot is unchanged, then updates only that execution's `STARTED` job and exact
`STARTED` data-step row. The completed identity-step row and serialized context
must remain byte-for-byte unchanged. The existing FAILED-to-STOPPED synthetic
fixture also now preserves its completed identity-step row and selects only its
exact execution's failed records; it is not deployment/recovery guidance.

All changed-date rejection, no-staging-write, single-instance, concurrent duplicate,
owner-verification, immutable source, Flyway history and old-schema refusal checks
remain. The crash case additionally records the HTTP response and staging counts
before asserting, preserving useful failure evidence if it regresses.

## Executed Local Results

Receipt time: `2026-10-01T02:27:34.282055+00:00`; worktree clean.
PostgreSQL 16.13, Maven 3.9.12, Temurin 17.0.18 and OpenJDK 21.0.12.1.

| PostgreSQL case | Exact execution / steps | Frozen date before/after crash | Classification | Changed-date result |
| --- | --- | --- | --- | --- |
| Java 17, `durable-e423f660-abrupt` | execution 12; identity 20; data 21 | `2026-09-27` / `2026-09-27` | job/data FAILED; identity remains COMPLETED | HTTP 200 / FAILED; staging 0 -> 0 |
| Java 21, `durable-c74ab278-abrupt` | execution 12; identity 20; data 21 | `2026-09-27` / `2026-09-27` | job/data FAILED; identity remains COMPLETED | HTTP 200 / FAILED; staging 0 -> 0 |

The targeted `--mode full --case m5a` matrix executed **five Maven builds / 14
tests**, zero failures/errors/skips: three preview profiles and two Boot 3
PostgreSQL old-schema controls. Both PostgreSQL original-date restarts completed
with three staging rows in one instance; old Batch 5 startup was refused without
database mutation. H2 remains a same-process restart boundary, not durability proof.
Source/JAR independence and deterministic generation/regeneration checks passed.

Focused preview/helper tests: **146 passed**, including **15 crash-helper
regressions**. The negative STARTED-only case times out rather than allowing
termination. Other controls reject incomplete identity/context, wrong date/owner/
execution, non-running data/job states, live-owner classification, changed
snapshots and corruption of the completed identity record.
Full Engine suite: **1,771 passed, 25 skipped** (environment-gated tests, not
skipped-success). Changed-file Ruff and diff hygiene passed.

One earlier local proof attempt failed on multiline PostgreSQL JSON parsing,
before the crash/restart assertions; its logs remain separate. Structural parsing
and a multiline-response regression repaired that reader. A sandbox-only packaging
download failure was resolved by the authorized task-cache/network run above.
Neither attempt was a changed-date product failure at the proven boundary.

Raw successful receipt SHA-256:
`02639f65845dbd902dd2e66bc517c467d37581dba88e4e4e220354b4b0da4293`.
It includes complete pre-crash, post-crash and post-classification database rows,
serialized/decoded contexts, original JVM exit code, changed-date response and
staging counts. Incremental `*-crash-evidence.log` files contain JSON and are
retained by the existing CI artifact glob even if the final aggregate receipt is
not produced. Large generated applications/logs remain outside Git.

## Reproduction and Handoff Boundary

Use a fresh task-owned loopback PostgreSQL service, synthetic credentials and an
explicit psql executable; never use an adopter database:

```bash
python -m pytest tests/unit/test_boot41_batch_durability.py \
  tests/unit/test_boot41_batch_preview.py tests/unit/test_boot41_kafka_preview.py \
  tests/unit/test_boot41_preview.py -q
python -m scripts.smoke.boot41_batch_preview_proof --mode full --case m5a \
  --java17-home "$JAVA17_HOME" --java21-home "$JAVA21_HOME" \
  --maven-repo "$TASK_MAVEN_CACHE" --work-dir "$PROOF_OUTPUT"
```

Set the existing `EDGEFORGE_BOOT41_PGHOST`, `EDGEFORGE_BOOT41_PGPORT`,
`EDGEFORGE_BOOT41_PGUSER`, `EDGEFORGE_BOOT41_PGPASSWORD` and
`EDGEFORGE_BOOT41_PSQL` variables. The runner creates/removes only its synthetic
databases; retain its output directory for inspection.

The final PR handoff must cite successful applicable exact-head CI, including
actual full S2, Kafka and default-preservation execution; this local targeted run
alone is insufficient. Independent review and human merge remain separate.
No pre-identity-commit behavior, database migration, default switch, full L5,
Maven security clearance or overall M2 completion is claimed. Docs impact: updated.
