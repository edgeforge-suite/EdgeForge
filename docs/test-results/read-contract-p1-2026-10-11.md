# Selected read contract P1 proof, 2026-10-11

Candidate: **EF-V5-ENGINE-READ-CONTRACT-P1 revision 2**. Starting source:
`30d25d055c48001e6478493c8993d1e029d4df8f` (merged XR-1). The
[read contract](../read-operation-contract.md) records the maintainer's input
classification decision and supported/refused behavior. This record is not
release acceptance or a dependency/security assessment.

## Before And After

The two refusal regressions failed against the starting implementation: both
unsupported contracts generated successfully instead of raising. A separate
application generated from an archive of that exact starting source reproduced
the actual results on H2/Java 17, using overlapping persistence/owner IDs:

- `/customers/CUST-1` selected the record with persistence ID `CUST-1`, owned by
  `CUST-9`, rather than honoring the requested customer selector.
- A declared `ownerId=CUST-1` query returned records owned by both `CUST-1` and
  `CUST-9`.

That historical control ran three Maven tests (including the context test),
with no skips. Its tests deliberately asserted the unsafe observations; their
success is reproduction, not acceptance of that behavior. The original logs
and control receipt remain outside the repository.

The correction refuses these contracts before output mutation. The supported
synthetic application has two records: `ACC-7` owned by `CUST-1` and `CUST-1`
owned by `CUST-9`. HTTP tests establish the intended own-ID results, missing-ID
404 rather than a first-record fallback, honest unfiltered collection results,
pagination bounds where enabled, and absence of the refused foreign route.

| Active profile | Database / Java | Surface | Maven result |
| --- | --- | --- | --- |
| `springboot-legacy-compatible` | H2 / 17 | Read-only, unpaged | 5 tests, 0 failures/errors/skips |
| `springboot-enterprise-postgres-java17` | PostgreSQL / 17 | Mixed CRUD, paged | 5 tests, 0 failures/errors/skips |
| `springboot-standard-enterprise` | PostgreSQL / 21 | Read-only, paged | 5 tests, 0 failures/errors/skips |

These are actual HTTP/database tests, not just generated compilation. All three
builds passed repeat-generation source comparison and source/packaged runtime
independence checks. Maven did not change generated source. Tools used locally:
CPython 3.11.15, Maven 3.9.12, Java 17.0.18 and 21.0.12.1, PostgreSQL 16.
The initial 12-test proof and its clean `9b31ce7` rerun are retained. Initial implementation proof was explicitly a dirty working tree based on the
starting SHA, not proof of that commit. Clean committed-head rerun receipts and
the exact CI/review head belong in the PR handoff; no record claims its own
future commit SHA.

## Repeatable Checks

Install the declared Python dependencies with `requirements-lock.txt` constraints
in an isolated Python environment. The reference lock's Linux-only platform
packages are not installed on macOS. `pip check` passed locally.

```sh
python -m pytest -q tests/unit/test_read_contract.py tests/unit/test_generation.py tests/unit/test_operation_parameters.py tests/unit/test_metadata_translation.py tests/unit/test_generated_app_quality_gate.py tests/unit/test_operator_dashboard.py
python -m pytest -q
python docs/tracker/build.py
git diff --check
```

The initial settled focused run passed **957 tests**; the full Engine suite passed
**3,026 tests, 21 skipped**. Changed-file Ruff and diff hygiene passed; all 68
local links in the affected guidance/index/backlog resolve. Tracker views are
byte-identical after repeated regeneration. Focused coverage includes inline/referenced roles,
case handling, special OpenAPI headers, malformed/cyclic/missing refs, retained
canonical errors, unsupported selectors, selected-operation scope, dispatch/name
changes, shipped selected GET, route fidelity and existing computed-read guards.
The preservation matrix covers all three profiles, read-only/mixed generation,
five unsupported contract shapes and generation/plan/apply. Existing output's
bytes, modes and timestamps are preserved, including developer-owned files;
failed new output is not published. Tracker regeneration validates 157 tasks.

### First Review Repair

Independent review of `9b31ce7143fa7edc43d91b204aa0f9639320ec53` found five
blocking cases despite the initial green tests. The correction shares the
computed-header rule between preflight and rendering, validates all raw request
mappings before target-field deduplication, preserves mixed-CRUD list suffixes,
refuses unsafe Java argument bindings, and resolves active local security-scheme
references before classification checks. Multiple distinct primary mixed-CRUD
reads are refused, while equivalent duplicates still deduplicate.

The expanded runtime proof above adds classified computed-read headers and a
static list subroute on all three profiles, totaling **15 tests**. Its first run
incorrectly expected root GET to return 404 on mixed CRUD; the actual 405 is
correct because POST remains declared there. That failed observation is retained
separately. The corrected proof asserts 405 for mixed CRUD and 404 for read-only,
alongside actual selected-route results; no product assertion was relaxed.
All 22 applicable independent reproduction/control tests pass after the repair;
the two original compile probes now receive the intended early refusal and are
covered by explicit binding-preservation regressions instead. The final repair
head, full test count, CI and re-review outcome are reported in the PR handoff.

### Second Review Repair

Re-review of `846bc1902edcefbab5b16e0f95f7d71a2f6a25ff` verified the first
repairs but found a dotted-header mapping bypass and a console list-endpoint
disagreement. The second bounded repair compares the full input name in the
selected request context, never only its final dotted token, and aligns console
read descriptors with the compatible selected controller path. Both mapping
orders, dotted and wrapped sources, all public-entry preservation boundaries,
and paged/unpaged read-only/mixed console-controller parity are tested. The
runtime helper additionally verifies descriptor routing before HTTP proof where
the profile emits a bundled console (H2); it explicitly reports not applicable
for the two PostgreSQL profiles, whose no-console default is preserved. The
initial helper attempt incorrectly assumed all profiles bundled the console;
its missing-file failure is retained separately and did not establish runtime
success. Profile-aware positive and missing/wrong-console controls cover the
correction. No browser journey is claimed. Final exact-head proof, CI and the last
authorized independent re-review remain completion gates in the PR handoff.

### Additional Authorized Context Repair

The final second-round review of
`875108a2d52a4c8d3e5469d8b30184ff236cdacf` found a supported-case regression:
response mappings with a nested property named `request` were treated as request
selectors. Both own-ID and computed reads failed; their `result` controls passed.
That failure and the earlier review receipts are preserved, not replaced by later
success. The maintainer authorized one additional narrow repair/re-review round.

The collector now classifies mappings by the selected interface/operation's
transport prefix. Only genuine selected response mappings bypass request-selector
checks; unknown, malformed and wrong-context sources remain subject to refusal.
The response collector uses the same boundary, so nested `response` request data
cannot become response mappings. Full dotted-header identity, raw-before-dedup
validation and cross-entity checks remain intact.

The static DTO harness shared the same substring ambiguity; the first new runtime
attempt failed its static check before Maven. Its log is retained separately.
Generation and the DTO harness now share the exact-prefix classifier. Unknown
contexts remain subject to request checking, and missing response DTOs still fail
the harness; no check is disabled or reclassified as not applicable.

Committed regressions exercise schema-valid own-ID/computed response `request`
and `result` properties, exact path-ID mappings, nested/malformed/wrong-context
sources and output preservation. The existing three-profile runtime harness now
uses those nested response names for both own-ID and computed reads. Earlier
runtime receipts did not exercise that new case and are reused only as historical
evidence. Newly executed counts, exact-head CI and the one additional independent
review outcome belong in the PR handoff; no prior approval transfers.

The shared-boundary repair's focused run, including harness tests, passed
**1,116 tests**; **53 applicable prior independent controls passed**, with the same two obsolete compile-success
expectations excluded in favor of the committed early-refusal checks. An initial
full-suite attempt reached 3,157 passes but failed its packaging test because the
sandbox could not resolve the package service for build dependencies. That log
remains preserved; an unsandboxed exact-head run and hosted CI, not a skipped
packaging test, are required to resolve the infrastructure failure.

The settled working-tree runtime proof passed all three builds and **15 tests**,
including both nested response names, determinism and source/packaged
independence. This is explicitly a modified working tree, not proof of the
preceding commit. A clean committed-head rerun and its exact SHA are reported in
the handoff alongside fresh CI and independent review.

### Request-Sample Association Follow-Up

Independent review of `4655b80d8a82a11aebfa7c5c2e9f691e38570733`
found that an unmapped GET request sample associated the request with the default
fieldless `Record` placeholder while response mappings selected `Account`.
Request-entity-based emission omitted that GET from read preflight. Planning
could approve it, and generation could rewrite output before a missing-DTO check
failed. The review and the failing regression log are preserved separately.

The follow-up binds selected GETs to their returned entity consistently in Java
emission, preflight and console descriptors. Raw request mapping validation is
unchanged; an unmapped sample does not hide a declared request body or selector.
Missing/fieldless selected read entities fail before artifact planning or output
mutation. Sample-only legacy metadata retains its existing entity fallback.

The initial **58 new regressions failed** against that reviewed source, including
the owner's lookup and unmapped body/query list controls. Read-only failures
included the previous unrelated missing-operation diagnostic; mixed-CRUD planning
reproduced the bypass. Schema-valid manifest fixtures cover all three profiles,
read-only/mixed surfaces and generate/plan/apply, including fresh-output absence
and unchanged existing bytes, permissions, file and directory timestamps.
Supported own-ID, computed and list reads with request samples also retain their
generated routes and pass the static harness. Missing/fieldless returned-entity
controls are included. Fresh exact-head counts, CI and independent review belong
in the PR handoff, not the earlier approval.

The three-profile runtime helper now uses a distinct `Record` request placeholder
for each synthetic GET while retaining the `Account` response and overlapping-ID,
missing-record, collection/pagination and nested-response checks. This exercises
the corrected association in compiled/running applications; real manifest
ingestion of request samples is separately covered by the unit fixtures. Previous
receipts remain historical and do not establish this new head's proof.

Settled follow-up validation passed **1,182 focused tests** and the full Engine
suite, **3,319 passed, 21 skipped**. Changed-file Ruff, six current local-document
links and diff hygiene passed. Tracker regeneration validated 157 tasks without
changing its JSON or either view. These are newly executed results for the
follow-up tree; exact committed-head runtime/CI/review receipts are reported in
the PR handoff. No historical failure or earlier approval is replaced.

For runtime proof, supply explicit disposable output and JDK locations, plus the
existing loopback PostgreSQL helper environment (`EDGEFORGE_BOOT41_PGHOST`,
`EDGEFORGE_BOOT41_PGPORT`, `EDGEFORGE_BOOT41_PGUSER`, `EDGEFORGE_BOOT41_PGPASSWORD`,
`EDGEFORGE_BOOT41_PSQL`). The helper creates/drops only its test databases.

```sh
python -m scripts.smoke.read_contract_proof \
  --output "$PROOF_OUTPUT" \
  --java17-home "$JAVA17_HOME" \
  --java21-home "$JAVA21_HOME"
```

The command uses cached Maven artifacts offline, requires a new output directory,
retains build logs and a receipt with the actual Engine SHA/dirty state, and
fails on missing/failed/skipped runtime proof. No advisory service is queried.

## Limits And Handoff

This closes neither general query support nor object/tenant authorization.
The header extension is an author declaration, not correlation echo, rate
limiting or authentication. Gateway/deployment obligations remain unchanged.
Only selected scoped REST reads are hardened; unrelated route safety remains
separate. No full Suite L5, Maven advisory matrix, image assessment or release
acceptance was run for this correctness fix. Applicable hosted generated-app
checks and required CI must pass on the reported head, followed by independent
exact-head review; local proof alone does not resolve the two P1s.
