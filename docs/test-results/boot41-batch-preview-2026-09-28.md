# Boot 4.1 Fresh JDBC Batch Preview Proof

Candidate **EF-V5-M2-ENGINE-BOOT41-S2**, revision **1**. Local observation
completed **2026-09-28T04:38:39.127230+00:00** (September 27 locally).
This is fresh-application compatibility proof, not Maven/M2 or release clearance.

## Revisions And Artifacts

- Base: `127439a54bb9e1fc787cf981490e6c33e8a45da2`, the #318 merge.
- Generator implementation: `382d200a7b194e050e09b5000bdab57c9d46bfaf`.
- Final complete matrix: clean `c60424859d4434eae782733ad74c9738c3e22cc4`.
  This adds only portable fixture binding and a non-empty old-schema control;
  generator emitters are unchanged from `382d200`.
- The later commit carrying this record is an evidence/documentation commit,
  **not** the generator/proof revision. Hosted checks belong to the draft PR's
  reported exact head, not to this local observation.
- Java: Temurin 17.0.18+8 and Homebrew OpenJDK 21.0.12.1; Maven 3.9.12;
  local PostgreSQL 16, macOS arm64. Each Maven invocation explicitly selects
  its JDK without changing global configuration.
- Exact Boot 4.1.1 BOM selects Batch 6.0.5. BOM SHA-256:
  `1c929eeccb48f8ee12225e9fec725177170b89575754bd903f184c185db77775`.
  `org.springframework.batch:spring-batch-core:6.0.5` JAR SHA-256:
  `1ff956ee90cae2ff29268b4ec8cb259493089dfd31281a7f87ed915fc4107fbf`.
  The proof compares each packaged H2/PostgreSQL schema with emitted SQL,
  ignoring comments, whitespace and unquoted keyword/identifier case only.

## Executed Coverage

The [machine receipt](boot41-batch-preview-2026-09-28.json) records all 16
builds, source digests, executed counts and runtime results. Each has executed
Maven tests, zero failures/errors/skips, deterministic generation/regeneration
and source/packaged independence. Totals: **38 tests**.

| Case | H2 / Java 17 | PostgreSQL / Java 17 | PostgreSQL / Java 21 |
| --- | --- | --- | --- |
| M5a immutable staging | 4 tests | 4 tests + process proofs | 4 tests + process proofs |
| Ordinary staging | 2 tests + bodyless HTTP/JDBC | 2 tests + HTTP/JDBC | 2 tests + HTTP/JDBC |
| Ordinary CSV file | 1 test + HTTP/file bytes | 1 test + HTTP/file bytes | 1 test + HTTP/file bytes |
| Separate M5a + ordinary file jobs | 4 tests + bodyless file job | 4 tests + bodyless file job | 4 tests + bodyless file job |

Four Boot 3 controls add five tests: H2 ordinary staging/file (2/1) and the
PostgreSQL Batch 5 refusal applications on Java 17/21 (1 each).

M5a HTTP tests observe the real Jackson 3 MVC converter: closed textual request,
whitespace rejection, exact supplementary-character preservation and 64 UTF-16
unit storage boundary. They check non-identifying frozen date, one logical
instance, partial-commit failure/restart, unique upserts and completed conflicts.

Both PostgreSQL profiles separately prove completed duplicate protection after
JVM replacement; FAILED and classified STOPPED restart; changed-date refusal
before new staging writes; concurrent duplicate serialization; abrupt owner
death with persisted STARTED state; truthful 409 diagnostics after replacement;
and restart only after test-only classification with the owner confirmed gone.
STOPPED is **simulated test-infrastructure classification**, not an observed
native stop endpoint or a generated recovery operation. All source rows remain
immutable through these runs, and Flyway history survives replacement.

The Batch 5 control contains actual source/staging rows and completed history.
Preview startup fails Flyway validation; complete business/Batch/Flyway row
snapshots remain equal. Package regeneration and approved apply independently
reject incompatible profile transitions before output mutation. This does not
establish universal detection of arbitrary existing databases.

Ordinary Boot 3/4 H2 trigger/status/error comparisons and CSV bytes match under
the narrow validated identity/time substitutions documented in the
[preview guide](../generated-app-standards/boot41-jobless-preview.md).
JDBC tests on both lines assert actual staging values, legacy run/instance
binding and identifying `run.at`. Ordinary jobs acquire no M5a request or
restart guarantee. H2 history is strictly **same-process**.

## Commands And Regression

From the Engine root with declared dependencies installed:

```bash
python -m pytest tests/unit/test_boot41_batch_preview.py \
  tests/unit/test_boot41_preview.py tests/unit/test_m5a_s2_batch_identity.py \
  tests/unit/test_m5a_s3_staging_idempotency.py -q
python -m pytest -q
python -m scripts.smoke.boot41_preview_proof --mode h2 --java17-home "$JAVA17_HOME"
python -m scripts.smoke.boot41_batch_preview_proof --mode full \
  --java17-home "$JAVA17_HOME" --java21-home "$JAVA21_HOME" \
  --maven-repo "$MAVEN_PROOF_CACHE" --work-dir "$PROOF_OUTPUT/new-batch-proof"
EDGEFORGE_RUN_GENERATED_RUNTIME_TESTS=1 python -m pytest \
  tests/integration/test_test_console_exposure_runtime.py \
  tests/integration/test_generated_crud_pagination_runtime.py \
  tests/integration/test_generated_passthrough_validation_runtime.py \
  tests/integration/test_generated_security_headers_runtime.py -q
```

Full Batch mode requires the explicit disposable loopback PostgreSQL variables
in the guide, permission to create/drop only its own databases, and `psql`.
All local commands exited **0** after bounded fixture/API repairs. Earlier
failed iterations are not represented as successful evidence. No advisory
inventory was submitted. Only task-owned processes/databases were stopped.

- Focused Python: **153 passed**; repeated at `c604248`.
- Full Python: **1,713 passed, 23 skipped** in default suite mode at implementation
  bytes committed as `382d200`; later changes are confined to runtime proof.
- Relevant opt-in runtime/security regressions: **15 passed**, no skips.
- Required S1 H2 proof at `382d200`: all four preview builds/tests and four
  live wire comparisons passed. Boot 3 controls executed three Maven tests;
  the inherited passthrough control has no generated Maven test (not counted
  as a test pass). Its live HTTP comparison did execute.
- Twenty-four shipped-profile corpus digests match clean base output, including
  jobless/SOAP/passthrough, legacy jobs, M5a, mixed jobs and Kafka controls.
  New synthetic inputs were overlaid on the clean base, not new generator code.
- Changed-file Ruff, workflow routing/service inspection and diff hygiene pass.
  Existing generated-app CI now executes the full new Batch proof; required
  hosted results are reported separately on the final PR head.

## Limits

No Batch 5 migration, adopter history operation, Kafka preview, Boot default
switch, container runtime proof, live Maven advisory scan, full Suite L5,
license/risk acceptance or release operation was performed. These selected
CSV/staging cases do not certify every edge combination. Delivered M5a remains
intact; this extends the preview only. Maven remediation and overall M2 remain
incomplete. Docs impact: updated.
