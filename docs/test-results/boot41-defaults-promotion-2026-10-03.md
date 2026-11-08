# Boot 4.1 Defaults Promotion: Builder Evidence

Candidate **EF-V5-M2-ENGINE-BOOT41-S4 revision 1**. This is builder evidence,
not independent approval, M2 completion, release clearance or migration support.

This dated campaign keeps its original 109f638 source identities and scan times.
Subsequent review repairs strengthen only retained-evidence refusal; they do not
relabel this record as a new scan or runtime execution. Repaired-head tests,
output applicability and actual CI belong to the outside-Git repair handoff for
independent re-review.

## Retained Campaign Identities and Safety

- Actual merged pre-promotion base: `76f7ab9ef1220e2bf5c94a78ce4e107cc965a5c2`.
- Frozen final generator/assessor/finalizer and all fresh local runtime execution: `109f6385345047013836f1e32b2d4230b9e8ad2b`, tree `9e5372386652d28c8e490cee2a1ba5eca2f270a4`.
- Exact generator subtree `649cb4622fb352b904352ea07175b1fe1d1fe1b4`. Actual per-build source, POM/resolved-tree, packaged-library and JAR identities remain in the [runtime supplement](boot41-defaults-promotion-2026-10-03/runtime-proof.json). No historical preview runtime receipt is credited as new execution. Earlier 52d9620/e8f5cec campaigns and green CI are superseded, retained in history and outside Git, not relabelled.

The ordinary three IDs now select the proven Boot 4.1.1 API/starter path;
preview IDs remain aliases. The [captured fixtures](../../tests/fixtures/boot41-promotion/)
were collected from the actual base before implementation: jobless, ordinary
Batch and M5a packages on each ordinary profile, plus 36 preview source cases.
Ordinary Batch with incomplete legacy provenance, missing/conflicting framework
evidence, Boot 3 POMs and Batch 5 schemas fail GENERATE/PLAN/APPLY before writes.
Same-line generation/regeneration and alias transitions preserve migration bytes
and retained schema provenance. No ordinary test requires historical Git objects.
An additional synthetic retained 4.1.2 POM/provenance exposed silent downgrade
with false provenance. The corrected guard requires the selected proven 4.1.1
parent before writes. Eighteen controls cover all ordinary profiles through
GENERATE/PLAN/APPLY with matching or absent provenance; byte inventories remain
unchanged. No new Maven version was selected, built or queried.
Existing external installations/history remain unknown; use separate fresh
packages/databases, never force, reset or classify adopter history.

## Actual Proof

The frozen generator passed **2,031 Python tests**, with 25 ordinary opt-in skips.
Its focused preservation/assessment/health/supplement suite passed **397 tests** in both a
depth-one checkout and a source-only checkout without `.git`. The supplemental
audit tests are no-network/no-Git; final-head CI is recorded separately
in the builder delivery rather than inferred from the generator run.

Local runtime receipts contain 16 jobless builds/tests and eight endpoint cases
(CRUD/REST, SOAP inbound/outbound and passthrough); 12 ordinary-profile Batch
builds with **219 Java tests**; and 12 plain/router/mixed Kafka builds with
**90 actual embedded-broker tests**. PostgreSQL M5a executes pre- and post-identity
commit crash/date-authority proof on Java 17 and 21. H2 remains same-process only.
Ordinary staging, file and mixed jobs execute separately from jobless cases.
SOAP inbound/outbound have identical resolved dependency children/edges and
packaged libraries on all tested ordinary profiles and the H2 alias.
Numeric/type Kafka comparison does not claim lexical decimal-scale preservation.

## Complete Maven Assessment

The [direct finalized layout](../handover-evidence/generated-maven/2026-10-03/README.md)
was emitted by the committed collector and finalizer without an external
redaction/deletion/JSON-preprocessing step. It binds frozen `109f638`, 30 case
executions, 60 passes and **14 validated graphs**. Query times are
**2026-10-03 23:44:42.769748 to 23:52:37.835927 UTC**. Findings exit **1** means
complete with decisions open; pre-query/incomplete exit **2** is never credited.

The actual graph map covers CRUD H2/PG (2), SOAP H2/PG (2), passthrough (1),
plain/router/mixed Kafka (3), ordinary Batch H2/PG (2), file Batch H2/PG (2),
and M5a/mixed Batch H2/PG (2). All original five shapes across three ordinary
profiles remain present. Full per-case identities and equivalent dependency
edges are in `baseline.json`; no seven-class assumption or copied findings.
PostgreSQL CRUD `package -DskipTests` assessment is compile-only, not runtime proof.

Pinned tools remain OSV 2.3.8, CycloneDX plugin 2.9.1/schema 1.6 and dependency
plugin 3.8.1; Maven 3.9.12 and Homebrew Java 17.0.18/21 are recorded per case.
Scanner SHA-256 matches checked-in and official checksums. Before every query,
components reconcile to resolved records, exclude root/nested extras and pass
actual public Central POM identity/origin inspection (213 public coordinates).
Namespace membership alone is not authorization. The exact pinned extractor
enumerates Components, not root Metadata.Component/Tools; the matcher sends only
Maven ecosystem/name/version, then retrieves advisories by ID. No private/root
IDs, source, manifests, caches or whole SBOM are uploaded. See the [boundary and
reproduction guide](../handover-evidence/generated-maven-assessment.md).

All **18 findings are OPEN**: 11 production/build and seven test-only, across
six coordinates. Tomcat 11.0.24, Jackson 3.1.5, test Jackson 2.21.5 and LZ4 1.10.1
retain exact advisories, reported fix ranges, aliases, scopes and conflicts in
the [owner decisions](boot41-defaults-promotion-2026-10-03/finding-dispositions.json).
No compatible version candidate was attempted or selected; no unmanaged override,
suppression or risk acceptance. The [110 historical mappings](boot41-defaults-promotion-2026-10-03/historical-110-dispositions.json)
retain four current advisory/alias matches, 91 current non-reports and 15 absent
coordinates. Non-report/absence is dated evidence, not universal fixed status.
Each row has an Engine owner, explicit decision, evidence and review trigger.
Plugin/build-stage, OS/JDK and image findings remain excluded; no image slice or L5.

## Reproduce and Boundaries

From a clean checkout of the frozen generator, run the existing collector with
`JAVA17_HOME`, `JAVA21_HOME`, the pinned scanner and a new external output directory;
then run the committed finalizer directly with the candidate ID/revision.
The guide includes exact commands. A live rerun has new scan dates, not the same
advisory snapshot. Earlier failed/superseded campaigns remain outside Git.
Every finalizer-produced file, including its build/Maven/scanner logs, is included
in the committed layout despite the repository's generic log ignore rule. A
second direct finalizer output reproduces the committed layout byte-for-byte;
no external pruning/redaction script defines what is committed.

The separate supplement is reproducible with
`python -m scripts.smoke.boot41_evidence_supplement --evidence <finalized-layout> --historical docs/handover-evidence/generated-maven/2026-09-13/findings.json --jobless <jobless-receipt> --batch <batch-receipt> --kafka <kafka-receipt> --output <new-supplement-directory>`.
It audits finalized inventories/equivalence, both-pass aliases and actual clean
runtime generator identities. It performs no queries, generation, sanitization
or mutation of the finalized scanner layout. Owner decisions remain explicitly open.

The initial CI health failure and later console/API-test failures are retained
separately. Local health reproduced `UP` plus liveness/readiness group metadata;
the corrected check still rejects unhealthy aggregates/components. Console proof
now uses an actual jobless fixture; Batch provenance refusal is not weakened.
Ordinary profiles use Boot 4 test APIs without dropping validation assertions.
The finalizer first refused public advisory PoC/cache paths; committed sanitation
preserves raw-output hashes and advisory IDs/aliases/ranges/severity/references.
Original raw receipts were not rewritten. No blanket path or secret exemptions.

The [Engine-owned Studio #309 backlog](../suite-security-review-backlog.md)
retains the exact draft-head/review observation and nested-input limitation.
Entrypoint-root checks are not universal confinement; no sibling fix/merge claim.
The M2/release proposal remains proposed, and #315/tracker work remains deferred.
