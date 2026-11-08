# Engine Public-Content Preparation

Approved scope: EF-V5-PUBLIC-CONTENT-ENGINE-S1 revision 4. Preparation base:
`8a94e5697c2ccd02f917ee7f94385f02d6a22398`. No import, public exposure, original
history cleanup or ownership clearance is performed. Existing repositories and
their histories remain private. This is not broad M2 or final Suite acceptance.

## Independent Replacement And Coverage

[Workspace/Item](../examples/input-projects/workspace-items/README.md) is newly
authored from the behavior below, not a renamed/exported external contract.
It deliberately has only two POST operations. The old external specification,
empty twin, samples, mappings and rules are removed from the working tree; the
old tracked relationship fixture is replaced conservatively as well. Complete
originals, exact original-path/blob correspondence and the prior publication
reviews remain private and recoverable from the recorded base. No large new
archive or historical hash rewrite is needed.

| Before: affected coverage/content | After: treatment and retained assertion |
|---|---|
| External-derived developer example and tracked two-entity roundtrip package | Independent Workspace/Item contracts/mappings/samples/rules; separate domains/controllers/services/repositories, two migrations, explicit field delivery and relationship check remain asserted. |
| CLI and MCP example consumers, E2E and generated-app independence | Point to the new manifest; preserve allowed-root/refusal tests, CLI/MCP output equality, static harness and 16-source independence checks. The warning test injects its own unmapped annotation rather than depending on old external fields. |
| FK/relationship and exists-rule tracked fixture | New `workspace-cross-entity` package; retains own target profile and source/target IDs, association and repository-existence assertions. Other scalar relationship negatives and multi-FK controls remain unchanged. |
| Assertion-built inline constraint and generated-ID packages | Generic minimal sample-only scalar packages remain, with neutral system labels. Preserve request-supplied versus response-only generated IDs, max-length propagation, explicit-source override and guard failures. They contain no copied external spec/export. |
| Canonical operation-context fixtures and wrapper classifier | Hand-built generic canonical metadata/wrapper shapes remain; neutral interface/system labels only. Preserve read/computed-read support-or-refuse, exact context/mapping protections, wrappers excluded from entities and every existing write protection. |
| Build identifier tests | Neutral labels; retain space/special-character sanitization, Docker JAR naming and all existing build-policy assertions. |
| March ingestion design/review and later historical summaries | Editorial public summaries with original dates, conclusions and limitations; external inventory/mockup omitted. Original source revision remains recorded; no claim the replacement produced older results. |

The replacement's bounds/defaults are explicit rules as well as illustrative
OpenAPI declarations. This does not imply complete OpenAPI constraint enforcement.
All existing generic banking fixtures outside the affected boundary remain; no
test is deleted, skipped, or changed from a refusal into a success for cleanup.

## Three Retained Designs

Complete content review covered every section, table, code block, appendix and
reference in the Kafka router design (1,354 original lines), broader KS suggestion
design (966 lines), and Studio assistive-features design (1,482 lines). The Kafka
and KS examples are generic technical designs; references describe public
technologies, project source and hypothetical future integrations, not private
deployments or actual credentials. The Studio document's old acceptance references
are now explicitly neutral summaries of privately retained historical proof.
No external API inventory/payload or actual private correspondence was found in
those three designs. Stale confidentiality footers are removed after this review,
not treated as permission to ignore private content. Original dates, technical
content, implementation notes and future-feature/privacy boundaries remain.

## Open Banking

The original Payment Initiation copy at private source
`a15e1ff8359176bdf86f7f398643bf07aa621492` is byte-identical to official v4.0.1,
SHA-256 `01d3ec5eb7034d270b1f67085b0e870e10604b3e642383f5635f71062f0ce718`.
The current unchanged contract has SHA-256
`254accd60ab92551fc9802dfd77d1f3d19be22463d8c6f8338df87dad8fd1f3b`.
Removing exactly the five declared header-role annotations from parsed content
reproduces upstream; no other structural difference exists. Focused upstream
retrieval and comparison: 2026-11-01. See [attribution](third-party-attribution.md#open-banking-specification)
and its linked complete MIT/copyright notice. Engine Apache-2.0 does not replace
those terms. Studio owns its separate fixture provenance/notice check.

## Intended Tree And Historical Evidence

Tracked-tree replacements/removals above happen in this preparation PR. The
subsequent frozen tree still has exactly the three separately approved
[advisory-source import exclusions](v5-release-readiness.md#public-import-exclusions-and-historical-replay).
Their private originals, hashes, indexes, findings and historical mappings remain
byte-identical. Overlapping database-derived records still need the existing
source-specific retention confirmation at final intended-tree review.

The local intended-import projection must equal the reviewed tracked tree minus
those three files, byte/mode for every included file, with no untracked local
assets. No whole-history scan or zero-keyword guarantee is claimed. Immutable
dated evidence may still refer to the old input identity; it is not a runnable
replacement command or fresh proof. Specific legacy ignore globs remain defensive
rules, not publication content or approval; no blanket document-format ignore is
introduced. Current ownership, reporting activation and final acceptance gates
remain pending under the [release policy](v5-release-readiness.md).

## Validation And Review

At checkpoint `be4335400e5785bc4f3880daf351fe6a3e3aa085`, the local Python
suite passed 4,582 tests with 32 skips and 29 subtests, but the generated context
test failed during normal H2 initialization: a range/default combination emitted
`CHECK (...) DEFAULT 3`. That original failure remains private and is not
rewritten as a passing observation.

Revision 2 authorizes the narrow product correction: emit DEFAULT before NOT NULL
and CHECK. Defaults, checks, nullability, primary keys and identity logic are
preserved; no generated output is patched. Nine new ordering cases fail against
the old emitter and pass after correction, covering all three profiles and
nullable, required and explicitly non-null fields. Existing PostgreSQL/identity
generation controls remain. Direct H2 2.4.240 execution proves the default value,
range rejection, nullability and primary-key enforcement on the emitted SQL.

Fresh `make generate-sample` output passes Java 17/H2 `mvn clean verify`, including
its one Engine-emitted context test. Loopback startup/health, 15 JSON HTTP
observations and the console check prove generated identities, mapped values,
defaults, create/read/list, invalid length/range/required/reference rejection and
no persistence from rejected requests. This is bounded sample proof, not full
Suite acceptance. Existing generated migrations are preserved on regeneration.
The correction affects fresh CREATE TABLE and newly generated additive ADD COLUMN
migrations; previously generated migrations and real databases are not
automatically repaired.

Revision 3 corrects the subsequently observed joserfc audit finding through a
single transitive lock change, 1.7.5 to qualified 1.7.6. Python >=3.11, the other
75 pins and all generator/example bytes are unchanged. See the
[dated correction](handover-evidence/python-audit-correction-2026-11-02.json)
and [reference policy](handover-evidence/python-dependency-policy.md#bounded-correction-on-2026-11-02).
Earlier failed CI and clean point-in-time records are retained, not rewritten.
The existing manual Java/H2/HTTP and content proof is reused, not repeated or
relabeled as execution at the later dependency/evidence commit.

Revision 4 addresses Claude's first independent review at
`4b52d3ed14690ed8df335ef233d5bb81e8ce27cc` (REQUEST CHANGES). Remaining historical
repository identifiers and operation-name lists are replaced with neutral,
dated descriptions; no earlier acceptance is attributed to Workspace/Item.
Defensive filename globs are retained by explicit maintainer decision, with a
narrow root slides-directory ignore after verifying no tracked slide content.
The sample-pack note now cites Engine's JSON parsers rather than a YAML example.
The dependency receipt's added direct server-extra edge is an explanatory
clarification from retained metadata, not a new audit.

The same clause-order correction now covers additive apply. Six new actual
plan/apply regressions (two field shapes across the three shipped profiles) fail
against the original renderer and pass after correction, retaining old migration
and developer-file bytes, permissions and timestamps. Direct H2 2.4.240 in
PostgreSQL mode executes the actual generated additive migrations: 14 checks
cover existing-row backfill, later insert defaults, escaped string values,
inclusive bounds, length/range/nullability rejection, primary keys and preserved
prior row values. The original renderer produces two syntax rejections in the
same engine. The retained H2 JAR SHA-256 is
`29b70e427cc1c40cdc376283adbb0cc62853073797bb5fe5761f81fe73d57ce0`.
No PostgreSQL deployment or application/Maven/runtime campaign was repeated.

Earlier CREATE TABLE, Java/H2/HTTP, Open Banking, complete-design and joserfc
qualification/audit/SBOM/license evidence remain at their original identities.
The only later product delta is additive SQL clause ordering; it does not change
fresh-generation inputs, application dependencies or Docker recipes. New additive
proof and final-head automatic CI cover that delta, not a relabeling of old proof.

The prior projection receipt's 367 relative links counted **changed Markdown
documents only**, not the whole tree, and its stale-link scan excluded the
handover-evidence directory. Claude separately checked the full tree (1,285 links;
no newly broken links; one pre-existing sibling-repository reference). The repair
packet labels changed-document and full-tree check scopes separately and includes
handover evidence in the refreshed stale-link check. Sealed earlier receipts are
preserved unchanged.

Final intended-tree checks, exact-head CI and external Claude review arranged
through Suite are recorded in the
draft PR and private packet. The older full-suite result applies to its recorded
checkpoint, not automatically to amended code. Claude is the required independent
reviewer; Codex/Astra cannot substitute. Publication gates remain pending.
