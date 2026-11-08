# External Review Reconciliation — v5 and Public Launch

**Status: scope and priority order adopted by the maintainer on 2026-10-06.**
This reconciles the external adopter/contributor/engineering review with the
[canonical roadmap](enterprise-readiness-roadmap.md). It is the completion and
parallel-work detail for that roadmap, not a second implementation queue.
Adoption does not complete any pending item, accept vulnerability risk, authorize
implementation goals, or authorize merges, tags, publication, or deployment.

**Current supersession (2026-10-25): maintainer-approved
EF-V5-RELEASE-SCOPE-RESET revision 3.** The [source-release policy](v5-release-readiness.md)
supersedes the old exhaustive-M2-before-publication gate and archive-repository
E/P/R/M procedure. Engine #335/#336 and Studio #318/#319 remain referenced
source-release known limitations with owner Santosh Hommaradi and review on
relevant upstream/advisory, dependency/recipe, next selection or production-pilot
change. Historical OPEN findings, observations and pins are not cleared.
New Ubuntu/Jackson research, new evidence tooling and signing infrastructure
are not pre-source-release work. Retain fresh strict audits, required checks,
new-pair L5 without skipped-success, newcomer journey, selected Studio-image
build/run, focused security QA and independent release review.

## Grounding and delivered work

The review proposal was dated 2026-10-05; this reconciliation checked fetched
`origin/main`, open PRs and main CI on 2026-10-06. The review's test/lint counts
remain attributed historical observations, not newly executed acceptance proof.

| Repository | Observed main on 2026-10-06 | Delivery boundary at that observation |
|---|---|---|
| Engine | `ab41a02fc854f89681e0473d9914e9e16528c3c2` | Boot 4.1.1 default delivered by #324. Maven correction #325 is draft/unmerged at `b90adfc84a83641905cee4c4e6c8553fdc629a90`; its assessment does not establish M2 closure. |
| Studio | `e17eeaa317fb23147ff27dba553e7ee9c7ed867f` | #309 delivered bounded adversarial caller defenses/proof; #310 delivered a dated image refresh and Expat dispositions. Residual image findings and final-pair applicability remain open. No open PR. |
| Knowledge Server | `543a9785752ac0c0c285913fffdd6d82c1b6328b` | #39 ingest notice, #41 publication documentation, #42 dependency closure and #43 evidence/documentation corrections delivered. `Blocking dependency audit` is a required main check, verified from protection settings. No open PR. |

**Current correction (2026-10-07):** Engine #325 merged as
`eb3074940790e64478da76746b6da9e3bad19394`. Studio and KS main remain at the
revisions above. The October 6 observations are preserved as history. Current
Maven evidence is the [October 5 campaign](handover-evidence/generated-maven/2026-10-05/README.md)
and [policy/disposition record](handover-evidence/maven-policy-2026-10-05/README.md).
The merge delivers the correction, not M2 closure or residual-risk acceptance.

Main CI was green at the October 6 revisions. No new runtime test, live dependency scan,
image build or L5 acceptance was performed for this documentation reconciliation.
These are observation pins, not release selections. Preserve the active candidate
descriptor and historical baseline/evidence until the authorized selection task.

[Domain sample packs](test-results/domain-sample-packs-2026-09-04.md) are delivered
at their recorded revisions; export/build/independence proof is not app runtime
or database/container proof. Engine Python closure and Boot migration slices,
Studio dependency controls and caller defenses, and KS controls must be reused,
not reimplemented because an older tracker row says pending. Engine #315 is
status reconciliation for the delivered KS notice, not another KS code task.

## Release boundaries

- Initial public distribution is the three source repositories and tags; no
  official package, binary or image publication. Website hosting is included.
  TestBench and shared-specs remain outside this shipped-Suite scope.
- Engine owns/consumes manifest 2.0 and generates standalone applications;
  Studio authors/exports it. Studio Knowledge Assist is a feature; the optional
  local Knowledge Server supplies evidence and neither produces nor consumes
  the manifest. Do not renumber independently versioned snapshots.
- Broad M2 continues, but exhaustive residual closure is not a prerequisite
  for this source release. The [release record](v5-release-readiness.md) defines
  retained checks, limitation ownership and fresh-repository ordering.
- Apache-2.0/NOTICE/DCO 1.1 (no CLA), one public core, fresh repositories under
  secured `edgeforge-suite`, and selected security/contact email/PVR routes are
  adopted. Maintainer publication authorization and route verification
  remain later public-exposure gates; preparation stays private.
- Pre-v5 generated apps are local test/demo output. Fresh regeneration replaces
  pre-v5 migration/backward-compatibility work; no automatic destructive reset is
  authorized. Updates after public v5 must support v5+ apps within an explicit
  supported transition policy; this is not indefinite support for every release.
- A11y-01 remains open under the active limited exception: disclose the failed
  native save observation and three untested cases through an audience-accessible
  notice. Four exact-speech native observations are still required for closeout.
  Automated checks do not replace them; no accessibility certification is implied.

## Combined execution order

The [five agreed release-QA checks](v5-release-readiness.md#release-qa-coverage-within-existing-work)
remain within E1/XR-2, S8/XR-4, existing security regressions and final acceptance.
No new task IDs, separate assurance programme or broad investigation is added.

Numbers express priority and convergence, not a serial schedule. The selected
path is **one public-ready v5 tag**: complete the source content and bounded
preparation/proof in rows 4–6 before row 7's freeze. Publishing prepared issues
and deploying the website remain launch operations, not prerequisites to the tag. Rows 3–6 and M6 preparation
can overlap under the [ownership rules below](#parallel-work-and-merge-order).
XR-1 and the two adjacent read P1s are delivered by #327/#328; #329 delivers the
bounded selected-write correction. The fixed demo/batch collision closeout is
delivered by #330. The [2026-10-14 endpoint decision](#endpoint-boundary-maintainer-decision)
dispositions generic CRUD exposure and defers `int32` validation, without a
vulnerability-risk waiver. XR-2 folds into existing preparation; no blanket
deferral follows from this execution order.

| Order | Existing owner / task | Gate | Completion criteria |
|---|---|---|---|
| 1 — DONE | Engine: Maven correction #325 | Delivered prerequisite | Merged 2026-10-07 as `eb30749`, following exact-head review and applicable CI. Remaining proof/documentation/disposition follow-ups are in row 3, not another merge task. |
| 2 | Engine: #327/#328 reads, #329 selected writes and #330 fixed demo/batch collisions merged | Delivered bounded pre-tag corrections | Image proof now consumes the merged corrections, not the earlier generator. Generic CRUD is retained under the adopted gateway-exposure boundary; `int32` range enforcement remains Engine-owned post-v5 work. Full D10 remains deferred. |
| 3 | Engine + Studio; KS verification: continuing M2 | Source-release known limitations, not exhaustive closure | Reuse #335/#336 and Studio #318/#319 records with owner/trigger; preserve OPEN identities, uncertainty, exclusions and existing per-app SBOM/base controls. No new Ubuntu/Jackson investigation, blanket clearance or production risk acceptance. |
| 4 | All three: release preparation / E1 / XR-2 | Tagged claims before tag; publication gates before public release | Versions/changelogs/current scope and security claims, known limitations, selected terms/contact/metadata, notices, applicable G5 public-safe content/history review and public-compatible CI checked. Include RP-EVIDENCE-PURPOSE below. No broad archive cleanup is required to finish this slice. |
| 5 | Studio-led, Engine support: S8 / XR-4 | Before public launch | One clean reference environment completes install, sample open/review, generate, build/run, change and regenerate; bounded automation proves real responses and supported developer-owned preservation. Short task-based Studio guide and troubleshooting; KS/Knowledge Assist remains optional. |
| 6 | Each core repo: XR-5 / governance | Before public launch | Usable issue templates, contribution/review guidance, private security-report routing and a small set of bounded starter-issue drafts ready. Reuse existing issues; publish appropriate drafts and public links at launch. Recruiting a second person is not a gate. |
| 7 | Suite coordination; separate repo release PRs | Selected single public-ready v5 tag; common proof applies to any coordinated baseline | Fresh applicable audits, exact frozen E/S/K selection, clean pairing, required repo/build/security proof and full L5 with required services and no skipped-success. Independently review actual run SHAs, limitations and later evidence commits. Human-authorized annotated tags target the tested commits; preserve v4 evidence. |
| 8 | Maintainer + website owner: publication / M6 | Public exposure and website hosting | Verify terms, content, disclosures and exact release targets. Set audience/access, operator, domain/TLS, logs/retention, telemetry, support, artifact and rollback; verify the separately authorized deployment. Website hosting does not authorize product-service hosting. |

Scope authority: [M2/M6](enterprise-readiness-roadmap.md#must-have-sequence),
[L5 acceptance](enterprise-readiness-roadmap.md#verification-per-initiative-done),
[P1-6](suite-security-review-backlog.md#p1-6--repair-security-evidence-then-make-it-continuous),
and the maintainer's adopted additions below. Green path-filtered or docs-skipped
CI is not fresh acceptance. New correctness/security defects must be triaged
before deferral; no-fix, feed gaps or unsupported upgrades do not accept risk.

A separately requested private internal baseline still needs the common exact-pin
acceptance, required checks and relevant correctness/claims proof. It does not
inherit G1/S8/XR-5 public-launch prerequisites merely from this selected public
release row. The old exhaustive M2 publication deadline is superseded by revision 3.
No separate private-tag milestone is introduced by this plan.

### M2 follow-ups from #325

Carry the [independent review's nonblocking follow-ups](https://github.com/santosh-sh/EdgeForge/pull/325#issuecomment-6008668712)
into the existing Engine proof/disposition work; do not reopen the merged bundle:

**Current bounded work:** the assessment landed through #332; its October 17
record remains historical. EF-V5-M2-ENGINE-RESIDUAL-FIX-S1 supplies the
[Noble/plugin correction and new assessment](handover-evidence/generated-images/2026-10-20-noble/README.md),
with 30 cases/60 stages, separate compatibility/default/native proof, and explicit
historical/current/vendor accounting. OPEN residuals and coverage limitations
remain; neither delivery establishes M2 or release clearance. Suite release-QA
documentation is separate, not an implementation prerequisite.

EF-V5-M2-ENGINE-RESIDUAL-PACKAGING-S2 revision 2 replaces #333's proposed
landing history, not its dated approval or assessment identities. Retention
keeps complete advisory bodies archive-only and publishes bounded factual
projections with unchanged ranges, contradictions, source fingerprints and
dispositions. The [storage contract](handover-evidence/generated-images/2026-10-20-noble-storage.md)
and [maintainer tool map](handover-evidence/generated-image-maintainer-tools.md)
record replay/privacy limits. #333 and prior GitHub references remain reachable;
no public-content licence, archive publication or residual-risk decision follows.

**Current delivery (2026-10-20):** #334 merged as `ca53afb`; #333 is closed as
superseded. The [Engine M2 decision packet](handover-evidence/engine-m2-closeout-decisions.md)
consolidates the unchanged historical/current/vendor identities and remaining
owners/actions. It does not turn the merged assessment into M2 clearance.
The Python audit's new live finding and correction are separate fresh evidence;
retained image/Maven reports keep their actual generator and observation dates.

The [October 17 image record](handover-evidence/generated-images/2026-10-17/README.md)
records 30 cases/60 stage assessments and three representative non-root startups
from generator `cc7721682f21009c6ad918ad021631213ff327a1`, including the merged
#330 correction. It retains the original failed fragment and affected-only
continuation separately. Image findings stay OPEN. Reconciliation gives explicit
version-remediation evidence for all 18 historical Maven mappings and supported
version/scope dispositions for 27 of 33 vendor observations; six vendor identities
remain OPEN (one range contradiction, five feed gaps). These are dated source and
packaged-inventory conclusions, not fresh Maven queries or exploitability clearance.

- **Default LZ4 path:** the [October 14 default-launch proof](handover-evidence/kafka-lz4-default/2026-10-14/README.md)
  records passing Java 17/21 roundtrips through the ordinary Boot `java -jar`
  loader without forced `Native.load`, at its exact recorded source and image
  identities. Java fallback and the two prior helper failures remain explicit.
  Existing forced-native proof is separate, not default-mode credit; this
  functional result does not complete the generated-image campaign or M2.
- **Advisory wording:** the 2026-10-14 correction verifies the GHSA-5gvw Jackson
  3 fix floor **3.1.5** (not 3.1.4) and inclusive `<= 2.22.0` range against retained
  source bytes. The evidence text/ledger labels the correction; original source
  bytes and scan timestamps remain unchanged. The 2.x range contradiction stays OPEN.
- **Owner dispositions:** reconcile all 18 historical mappings and 33 vendor
  observations against resolved/packaged scope and retained fix evidence. Close
  supported identities explicitly as remediated/not affected; isolate the
  test-only Jackson 2 range contradiction and feed-coverage limitations rather
  than issuing blanket clearance. Evidence-backed remediation is not residual
  risk acceptance; unresolved cases still require evidence or a maintainer decision.
- **Optional wording:** a clearer refusal message for pre-policy Boot 4.1.1
  packages may accompany relevant documentation work; no new migration capability
  or separate release blocker is introduced.

## Parallel work and merge order

| Lane / owning repository | Can proceed alongside | Convergence / ownership boundary |
|---|---|---|
| Engine image/SBOM proof consumes merged #325/#327/#328/#329/#330 | Studio image triage; Studio S8 documentation/preparation; KS publication prep; maintainer decisions | One structural-emitter PR at a time. The dated image assessment identifies the actual generator containing those corrections; default LZ4 and historical Maven/vendor reconciliation remain separately scoped evidence. OPEN findings still need disposition. |
| Studio image: residual-family triage and coverage decisions | Engine work; KS prep; S8 in a separate worktree with distinct files | #310's rebuild is delivered, not a new task. Final assessment must represent the final Studio/Engine pairing and actual image digest; a prebuilt-image test does not prove a fresh Dockerfile build. |
| Studio onboarding: S8 guide and one automated journey | Image work if Dockerfile/dependency/workflow ownership is assigned; Engine fixes; KS prep | Reuse existing sample packs and proof helpers. Default ownership: image lane owns Dockerfile, dependency locks, image workflows and image evidence; S8 owns its guide and new journey-test files. A shared general workflow edit goes through one nominated lane after coordination, never simultaneous edits. Final journey proof uses selected compatible revisions before freeze; no new full-suite harness. |
| KS publication preparation | Both product repositories; maintainer decisions | No companion runtime/image work without a demonstrated gap. Draft independent corrections now; chosen terms/contact must arrive before completion. Preserve advisory-feed limitations and perform the final audit at selection. |
| Suite documentation / tracker | All repo product work | One tracker editor. Canonical docs plus JSON/README/HTML travel together. #325 is merged; this docs branch incorporates its main merge and the updated snapshot. Refresh again if relevant repository state changes before merge. |
| Maintainer license/contact + website/M6 preparation | All lanes above | Terms, ownership, security route, concrete residual risks and hosting choices remain maintainer decisions. Content/operations preparation can proceed; publication/deployment require separate authorization. |
| Final M2 closeout → release freeze → coordinated acceptance | Preparation can overlap; final selection is a shared convergence point | Finish material product/image changes first. Studio/KS release prep can merge independently; use actual selected post-merge commits. Engine version/tag/evidence timing follows the release record, not an automatic merge. |

Repo build → applicable CI → independent exact-head review → bounded fixes and
re-review → human merge remains the workflow. One successful final L5 is the
planned convergence proof; do not repeat it for each documentation/family task.
A changed selected tuple or relevant defect requires appropriate re-proof,
including a new L5 for changed release pins. No repeated scan merely to seek a
clean result. Retain proportionate, sanitized evidence and explicit stop points.

## XR disposition and completion criteria

### XR-1 Refuse unsupported computed reads

The following describes the merged XR-1 scope; current selected-read behavior
is governed by the later [Read P1 Maintainer Decision](#read-p1-maintainer-decision).

**Merged in PR #327; Engine; Small; before v5 tag.** The starting revision
`64f51d0bac92b4c70f26c8f5f067888717df7b14` emitted
`findAll().stream().findFirst()` for a computed read without path parameters,
and its unit test expected the TODO placeholder. The XR-1 correction uses
operation-specific generation-time refusal before any application-output
mutation, including regeneration of existing output. The 2026-10-09 review
also found owner/nested IDs were incorrectly treated as entity IDs by selecting
the last path parameter. The corrected computed-read lookup requires exactly
one resolved entity ID and one same-name, same-Java-type path parameter, bound once directly
after the Engine entity collection in any explicit contract path, with no
ignored query/header parameters. Equal names alone were still unsafe for generic
`id`: the additional maintainer-authorized repair refuses
`/owners/{id}/records/summary` for `Record.id`, while retaining the Engine resource
layout `/records/{id}/summary`. Static API prefixes are retained only when the
entity's operations have a compatible common route base; this binding check is
not proof of emitted route preservation (see the open route P2 below). No custom
resource alias, description inference or URL normalization/decoding supplies a binding.
The static prefix/suffix allowlist also refuses wildcard route patterns,
malformed braces and semicolon matrix syntax rather than broadening the mapping
or emitting an unusable route.
Legacy contexts without an explicit path retain the Engine entity-resource route.
Ambiguous or unbound lookups in the `computed_read` branch fail rather than
guessing aliases or discarding scope. The resolved `is_id` field can be inferred,
including from the route being checked; an explicit identity override is not
required. Supported computed-ID reads retain their existing implementation.
Planning runs the same preflight and cannot emit an approvable plan for unsupported input.
No developer override or
derived-query implementation is introduced. Full derived-read semantics stay
in D10; XR-1 does not depend on an emitter refactor or pre-v5 package migration.
The [regression tests](../tests/unit/test_generation.py) cover the direct
renderer, early whole-application/Java preflight, all three profiles, existing
user/generated output preservation, schema-valid CLI failure/success, and
additive apply refusal before its migration/baseline/rollback boundary (including
read-only developer files and unchanged file bytes, timestamps and modes),
owner/nested lookup refusals, explicit custom IDs and CLI planning refusal.
Generic-ID binding regressions exercise service rendering, Java emission,
generation into absent/existing output, planning and additive apply across the
three shipped profiles, preserving read-only developer files and package state.
Wildcard/malformed/matrix-route regressions cover those same entry points and
schema-valid CLI generation, planning and apply.

**Historical scope correction (2026-10-10, superseded for selected reads by
the 2026-10-11 amendment below):** `_operation_category` first applies its
create/update/delete rules. It then classifies a single-object GET as `get_by_id`
when it has path parameters, a name starting (case-insensitively) with `get`,
`fetch`, `find`, `read` or `retrieve`, and either an explicit path ending in a
placeholder or no explicit path. Other single-object GETs reaching that branch
are `computed_read`. Only the latter receive XR-1's binding/refusal preflight.
Contract-path get-by-ID still selects its last path parameter unchecked. The
prior unqualified refusal wording is superseded by this branch-specific scope,
not by a fix or acceptance of the adjacent defects below.

#### Read P1 Maintainer Decision

**2026-10-11: adopted; delivered by merged PR #328 at
`47135eacdd3e884d2a1448a96d9ebf07bc24fdcd`.** Both the
unchecked get-by-ID binding and ignored collection-selector P1s must be fixed
before v5; neither is deferred or risk-accepted. EF-V5-ENGINE-READ-CONTRACT-P1
revision 2 authorizes bounded support-or-refuse validation, GET-independent
identity checks, faithful scoped routes and explicit ordinary-header roles.
The [selected-read contract](read-operation-contract.md) records that decision,
supported/refused cases, the shipped selected GET and gateway responsibilities.
The correction also addresses dropped parameter refs, cookies and GET bodies
within these reads. General non-read route safety, arbitrary filtering and
object/tenant authorization remain separate. Completion requires passing proof,
applicable CI and independent exact-head review; this record alone closes no P1.

#### Selected Write Maintainer Decision

**2026-10-13: adopted; delivered by merged #329 at
`891705e20f150ef421f518a8a0fecac62246da8d`.**
EF-V5-ENGINE-WRITE-CONTRACT-P2 authorizes the bounded
[selected-write contract](write-operation-contract.md). Selected non-read
contracts must be faithfully generated or refused before output mutation.
Retained source inventory prevents unsupported methods/actions/inputs from
disappearing during attribution or dispatch. The payment mapping amendment
repairs explicit canonical bindings, not the deferred nested-wire capability.
Historical observations below remain history; #328 already corrected the
scoped reads. The merged correction includes scoped proof, applicable CI and
exact-head review; none establishes business/security semantics or release acceptance.

#### Endpoint Boundary Maintainer Decision

**Adopted 2026-10-14: EF-V5-ENGINE-ENDPOINT-BOUNDARY-CLOSEOUT revision 1.** The
[canonical roadmap decision](enterprise-readiness-roadmap.md#endpoint-boundary-maintainer-decision)
supersedes the prior open, unadopted generic-CRUD policy: retain existing generic
CRUD, review the emitted HTTP method/path surface and expose only explicitly
approved operations at the authenticated TLS gateway. Unapproved CRUD/demo/batch
routes must remain inaccessible through it, with no direct application-port bypass.
Authentication is not exposure approval or business/object/tenant/row authorization.
There is no generated endpoint allowlist or automatic gateway configuration.

Fixed demo/batch-controller collision coverage is delivered by merged #330 at
`ba56abd1e0ff946260e96f3a3b715564fc0b740d`. It includes actual emitted mappings,
even for runtime-disabled demo handlers, without reserving absent controllers.
`int32` range enforcement is deferred post-v5 and remains **Engine-owned**:
affected transport inputs bind as `Long`, not 32-bit bounded values. Adopters
requiring those bounds validate before effects. Closeout requires boundary
rejection tests and preservation of in-range values, `int64`, persistence identity
and database types. No other requirement or vulnerability disposition is waived.

#### XR-1 Adjacent Operation Audit

**Additional nonblocking review findings (2026-10-14):** review of #329 identified
missing collision checks for emitted demo routes and `/batch/run/{jobName}`.
That pre-merge observation is superseded by merged #330's delivery above; it is
not a remaining image-campaign prerequisite. The same review identified integer
parameters binding as `Long` despite `format: int32`; 32-bit range fidelity remains
unimplemented under the explicit Engine-owned post-v5 deferral above. The shipped
insurance pack's declared empty 202 preservation regression was addressed in #329.
These dispositions do not rewrite the dated observations or imply release acceptance.

**Historical record, 2026-10-09/10.** The observations and pending-disposition
wording below describe the reviewed XR-1 scope, not current authorization.
The 2026-10-11 maintainer decision above supersedes both P1 disposition choices
and authorizes scoped read-route/input corrections. Preserve the original
findings and their evidence; do not treat current refusal as a query engine or
rewrite the historical proof as if it tested the subsequent correction.

Bounded source inspection on 2026-10-08 covered `_operation_category`, the
controller's operation dispatch and `_render_service`'s CRUD/non-CRUD dispatch
in [`java_emitter.py`](../appbuilder/generation/java_emitter.py), rather than a
repository-wide emitter redesign. The historical inspection is supplemented by
the [2026-10-10 independent review](https://github.com/santosh-sh/EdgeForge/pull/327#issuecomment-6094505457)
at `924bdae56483beb0b13dc29b39d4bacac702f720`; its adjacent findings below are
pre-existing on base `64f51d0bac92b4c70f26c8f5f067888717df7b14`, not introduced
by XR-1. The computed-read TODO/first-record fallback
is removed. Generic create fallbacks map and persist declared fields, and
state transitions retrieve by ID; they are not additional first-record TODOs.

**P1 distinct correctness follow-up, Engine-owned and still open:** `read_list`
and list methods accept path/query arguments but use unfiltered `findAll()`
or `findAll(pageable)` in `_render_service`. For example,
`GET /accounts/{accountId}/records` can return every record rather than only
that account's records. This is a false-success filtering boundary, not a
list-size/pagination fix. The relevant source anchors are
`_operation_path_variable_service_signatures`, `_service_parameter_signature`,
and the `list`/`read_list` branches of `_render_service` (both explicit-read and
mixed CRUD surfaces). A follow-up must explicitly implement or refuse unsupported
filtering, with two-owner fixtures proving no cross-owner rows are returned.
This audit records the defect, not its resolution or permission to infer
filtering from arbitrary query/header names. Do not advertise those arguments
as enforced filters. XR-1's narrow single-record refusal does not fix it.

**Release disposition pending (2026-10-09):** the maintainer must choose a separate
bounded pre-tag implement-or-refuse slice, or explicit D10 deferral with mandatory
release-note known-limitation disclosure. The former is recommended; neither is
authorized by this audit. The execution plan and Suite tracker must record that
decision before treating this defect as deferred. Tracker changes are outside
XR-1's authorized scope and remain a Suite coordination handoff.

**P1 unchecked get-by-ID binding (recorded 2026-10-10), Engine-owned and open:**
changing an operation name from `accountForCustomer` to `getAccountForCustomer`
can bypass XR-1's computed-read guard. Contract-path `get_by_id` uses
`_primary_operation_id_argument_name` (the last path parameter) in both the
read-only `_render_service` branch and the CRUD `getById` controller/service
path. For `Account` with resolved persistence ID `id`, this emits
`findById(customerId)` for `/customers/{customerId}`, uses a business key as the
ID for `/accounts/by-number/{accountNumber}`, and ignores the owner in
`/customers/{customerId}/accounts/{id}`. A generic foreign `/customers/{id}` is
also unchecked. The independent reviewer reproduced these on base and head;
with `ACC-7` owned by `CUST-1` and account `CUST-1` owned by `CUST-9`,
`GET /customers/CUST-1` returned HTTP 200 with the CUST-9 account.

**Release disposition pending:** a separately authorized bounded pre-tag
implement-or-refuse slice is recommended alongside the list-filtering P1.
No deferral, risk acceptance or runtime design is selected here. Reusing XR-1's
snake-case collection allowlist blindly would reject the shipped route
`/international-payments/{InternationalPaymentId}`. Follow-up proof must cover
name flips, generic foreign IDs, business-key/nested reads, overlapping-key
runtime data and preservation of shipped get-by-ID contracts. The execution
plan/tracker disposition remains a Suite coordination handoff outside this PR.

**P2 distinct route correctness follow-up, Engine-owned and still open:**
the 2026-10-10 review widens the earlier multi-parameter legacy-route observation.
`_common_spec_route_base` returns no base when eligible operations imply multiple
bases, so controller routes fall back to Engine's entity layout rather than the
declared paths. The reviewer observed contract `POST /api/v2/accounts` plus
XR-1-supported `GET /api/v1/accounts/{id}/summary` return 404 while the app served
`POST /accounts` and `GET /accounts/{id}/accountSummary`. Single-parameter
get-by-ID can also emit `/{id}` with `@PathVariable("accountNumber")`, producing
HTTP 500 (`MissingPathVariableException`). `_non_crud_route_suffix` can emit only
the first parameter while `_operation_path_variable_controller_signatures`
requires every parameter, causing the same missing-variable failure.
These defects predate XR-1; refusing multi-parameter computed reads does not
resolve them. Triage before v5 must choose separately scoped refusal of
unpreservable routes/missing variables, implementation, or explicit
known-limitation disclosure. That disposition is pending, not authorized here;
tracker coordination remains outside this amendment. Follow-up proof must call
the declared routes, check every variable and verify startup, not merely pass
the static harness.

**Additional known boundaries (2026-10-10; not fixed by this PR):** cookie
parameters and GET request-body filters can be silently dropped; XR-1 checks
only the modeled path/query/header inputs. Resolved IDs may be inferred from
the route itself, so matching `is_id` is not independent proof of intended
identity; review explicit `identity_overrides` where needed. Accepted static
prefixes/suffixes impose no ownership, tenancy or authorization. Routes are
embedded unescaped by `_mapping_annotation`; quotes/newlines can break Java
compilation and annotation-shaped input can alter emitted annotations. A
computed read on an existing CRUD item route can also cause ambiguous-mapping
startup failure. These are retained limitations, not permission to advertise
arbitrary route/input support or treat a static harness pass as compile/runtime
proof. Follow-up triage/proof must include ignored inputs, identity inference,
route escaping and mapping collisions; no runtime change or waiver is made here.

### XR-2 Release claims and evidence purpose

**Adopted within E1/release preparation; all-core; Small.** Tagged README,
quickstart and SECURITY claims must reflect supported behavior; website claims
must match before hosting. Add a named **“What EdgeForge does and doesn’t do”**
section: one manifest produces one standalone app; cross-service calls are
limited to the supported contract paths, not arbitrary orchestration. Explain
supported interfaces, mappings, declared
rules and handoffs without promising complete business logic, automatic legacy
data migration/cutover or full OpenAPI constraint enforcement. Regeneration
preserves designated developer-owned seams, not arbitrary edits. State the
authenticated TLS gateway and inaccessible application-port requirement, plus
adopter business/object/tenant/row authorization responsibilities. Distinguish
Studio anonymous shared sessions from real identity and KS local evidence from
provider-backed AI. Keep the current Boot default/profile and pre-v5 regeneration
policy truthful; no production certification or universal compatibility claim.
Preserve the Studio image's disclosed Java font-rendering limitation; restoring
fonts would be a separate compatibility change with an updated image assessment.

**RP-EVIDENCE-PURPOSE:** release preparation in all three repositories explains
that handover evidence serves maintainers, contributors, users and enterprise
adopters. State what each record proves, source/tool/date identity, limitations,
reproduction and material-change refresh triggers. Keep historical paths and
dated results; distinguish current acceptance from older snapshots. Publish the
necessary sanitized evidence, not private raw logs/source archives. No separate
renaming project or repeated audit campaign is required. In particular, Studio
#310's decision/delta projection used a task-local `build_evidence.py` and retained
raw inputs: its committed summaries alone do not provide exact replay. The
[source record](https://github.com/santosh-sh/EdgeForgeStudio/blob/e17eeaa317fb23147ff27dba553e7ee9c7ed867f/docs/handover-evidence/studio-image-refresh-2026-10-04.md)
states that availability boundary. Publication guidance must preserve it and make
the necessary sanitized reproduction material available or state what cannot be
re-derived; do not call the projection reproducible from a clean clone alone.

**G5 mapping:** applicable example classification and active-reference/content
corrections needed for public-safe source belong to row 4/E1 before publication
and the selected public-ready source freeze. Existing content rules remain in
force. Broader adopter-specific import/branding cleanup and optional-repository
work are not additional v5 tag gates. The two import-gate tracker rows are scope
summaries, not two new implementation programmes.

### XR-3 Blocking lint after v5

**Adopted first small post-v5 CI improvement; all-core; Small.** First slice of
`post-deeper-ci`: pin the current checker/rules, clean the baseline, demonstrate
that a deliberate violation fails the enforced merge check. Repository-setting
changes remain explicitly authorized operations. Incremental typing is later;
do not introduce broader rule/style migrations before the release.

### XR-4 One newcomer journey

**Adopted in S8; before public launch; Studio-led/all-core; Medium.** Row 5 is
the finish line: one supported reference environment and one representative
sample, real app requests, supported regeneration and a task-based guide.
Reuse delivered sample packs, L2/L5 and Engine helpers where applicable. No
fixed file-count/timing claims, mandatory KS install, exhaustive manual,
all-platform matrix, new browser framework or full M3 prerequisite.

### XR-5 Contributor basics

**Adopted launch slice; all-core; Small plus ongoing people work.** Row 6 is
the documentation finish line. Templates must route private security reports
away from public issues. Starter tasks need ownership, prerequisites and testable
completion criteria; reuse the public canonical backlog. Second-person
reproduction/recruitment is ongoing with its own evidence, never a dependency
of the tag or launch. Do not treat a currently private issue as a public channel.

### XR-6 Generated app-local tests

**Post-v5; Engine/generated apps; Medium–Large; existing handoff/M3 requirement.**
Design the bounded coverage before implementation: supported operations,
mappings, invalid inputs and declared rules get independently specified expected
results; tests must detect relevant wrong behavior and execute in CI beyond a
context-start test. Amend M3's consumption/selection design as needed, retaining
app ownership of executable tests. This is not another verification framework.
Preserve M3 → M4 → M5b and the later groupId/OpenAPI prerequisites for the broader
generated-contract-test programme in [security order §8](suite-security-review-backlog.md#order).

### XR-7 Operational baseline

**Post-v5; existing M5b.** Reuse QG-B5/B6/B8: separate probes, CRUD structured
logging and generated CI, under their existing completion criteria. No duplicate
XR-7 implementation row or new pre-tag gate.

The [generated-app quality gate](generated-app-standards/generated-app-quality-gate-v1.md)
remains the authority for these and the C1/C2/B3 pilot criteria below; neither
the XR mappings nor a single slice closes its broader quality requirements.

### XR-8a Concurrent updates

**Pilot-triggered; Engine + Studio; Medium–Large; QG-C1.** Before a pilot needs
concurrent updates, prove conflicting edits to ordinary low-contention records
are detected instead of silently overwritten. Design the manifest/authoring and
error contract first. Balance/hot-accumulator fields remain excluded and require
the separate C2 atomic-update design. This does not close every concurrency gate.

### XR-8b Bounded list responses

**Pilot-triggered; Engine; Medium; B3 list-size slice.** Before large-data pilots,
including read-only pilots, each applicable route has contract-compatible
paging/limits or explicit contract-required unbounded behavior with proven
operating safeguards. No silent truncation or response-shape change. Delivered
page/offset bounds remain delivered. Filtering correctness is separate D10 work;
a newly confirmed wrong-result defect must be triaged before deferral. Neither
this slice nor disclosure alone closes all B3 or approves a production pilot.

### XR-9 Incremental emitter refactoring

**Post-v5; Engine; Large overall, bounded extractions.** Extend the existing
`emitter-refactor` item; start with a useful responsibility/read-list extraction.
For each slice compare supported examples/fixtures/profiles using identical
inputs and fixed run metadata; require byte-identical output and relevant
build/runtime proof. Keep the pre-D10 dependency. No full-module rewrite or
template conversion is a v5 prerequisite.

### XR-10 Hosted Studio identity

**Conditional project team-service requirement; Studio; Large.** Before offering that
service, prove projects/access/audit records attach to real identities through
the selected IdP. The project owns supported reference integration and boundaries;
the operator owns its identity configuration and access policy. Anonymous session
isolation is not authentication. Website hosting does not trigger this service
scope; local stdio KS needs no companion network-auth change. D2 continues to
track the separate deployer-owned IdP wiring. The project-supported integration
above is conditional pending work, not a transfer of the deployer's ownership.

### XR-11 Pilot integration and migration

**Concrete-pilot-driven; relevant product/adopter owners; Very large overall.**
Scope service calls, business events, old/new output comparisons, migration and
cutover/rollback against an actual pilot's contracts and operating needs. Link
the [cross-service integration draft](generated-app-standards/cross-service-integration-design.md)
and [event-delivery design](generated-app-standards/generated-app-event-delivery-design.md),
including their unresolved decisions and prerequisites, rather than adding
a duplicate strategic implementation umbrella. Completion requires the scoped
contract/runtime and migration/reconciliation proof, not generic enterprise
certification. `park-cdc-outbox` carries a searchable XR-11 cross-reference to
these designs; it covers event delivery, not the whole pilot/migration scope.
This does not reopen migration of pre-v5 test/demo output.

## Ownership and tracker mapping

| Review material | Canonical/tracker action |
|---|---|
| XR-1 | New bounded `XR-1`; related to D10, but no dependency on implementing D10. |
| XR-2 | Extend E1/release preparation; retain M6 for website publication. |
| XR-3 | New bounded child `XR-3` of the existing post-deeper-ci programme; keep later typing/security/coverage maturity separate. |
| XR-4 | Extend S8; mark S1 delivered only from its pinned acceptance, not as current runtime proof. |
| XR-5 | New bounded contributor-basics row; reuse existing governance files/issues. |
| XR-6 | Extend genapp-handoff-residual and M3; no duplicate XR-6 programme. |
| XR-7 | Existing QG-B5/B6/B8. |
| XR-8a / XR-8b | QG-C1 and a bounded B3 list-limit row; preserve separate C2/filtering scope. |
| XR-9 / XR-10 / XR-11 | Existing emitter-refactor / D2 deployer wiring plus conditional project XR-10 scope / XR-11 design links and park-cdc-outbox cross-reference; no new broad XR-11 implementation row. |

Public project CI, release pairing and supported source/tool-file policy are
project responsibilities. Full threat modelling, deeper CI and signing/attestation
are later project maturity work, alongside each adopter's local assessment,
enterprise scanners, gateway, IdP and tool-file policies. M2 owns current declared
dependency/SBOM coverage and dispositions; do not create a duplicate transitive
audit because an old importer-oriented row remains. G6/shared-specs is optional
and outside this release. No repository merger, forced identical dependency
versions or generator template rewrite is adopted.

The tracker remains a derived reference: canonical sections supply status and
timing; no new guardrail sequence ranks are invented for XR items. Preserve
historical records and distinguish implemented, tested, accepted, released and
published. This reconciliation changes the plan, not the status of its pending
product, publication or pilot deliverables.
