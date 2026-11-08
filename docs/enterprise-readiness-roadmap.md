# EdgeForge Suite — Enterprise-Readiness & Handoff Roadmap

> **Status:** Living suite roadmap. The coordinated `v4.1.0` enterprise-readiness
> baseline is L5-proven; Engine `v4.1.1` carries the post-baseline credential
> hardening. Current unstarted work is re-prioritized below.
>
> **Created:** 2026-06-07. **Revised:** 2026-10-06 — adopted the bounded v5/public-launch
> reconciliation and parallel work plan below; earlier revisions remain context.
> v2 incorporated the Codex review;
> v3 converged the debate (onboarding stays front-loaded; import gates become a **visible
> owner-tagged parallel lane**, not a blocking pre-phase; license is an explicit **external
> adopter gate**; a lightweight **security boundary map** is a now-item while the full threat
> model defers; support/ownership is a **recommended** split); v4 added the **G10
> handover-evidence pack + README front-door**; v5 added the **ordered execution-checklist
> appendix**; this refresh adds the post-`v4.1.1` must/should/nice execution order.
>
> **Scope:** Suite-level master tracker for a usable, documented source release
> and optional self-managed enterprise adoption. Engine (`appbuilder`) items
> are directly actionable in this repo; cross-repo items (Studio, KS/KA, TestBench,
> shared-specs) are flagged for their own threads but tracked here.

## Context

The current delivery objective is a coordinated v5 baseline and public source/tag
launch of Engine, Studio and Knowledge Server, plus the separately controlled
website launch. Enterprise import remains a supported audience, not the only
purpose of this roadmap or its evidence. The adopted plan below controls current
release scope; older enterprise-import and strategic sections retain their
history and do not make every listed improvement a v5 blocker.

EdgeForge is independently maintained, with community contributions focused on
correctness, stability and usability. Individuals and enterprises in any domain
may adopt it under Apache-2.0. An adopter may maintain its own deployment or fork;
that does not transfer project governance or commit the maintainer to services.

For an optional enterprise adoption, the following are evaluation goals:
1. **Import-ready** — the adopting organization can approve the import (ownership/license/usage rights
   confirmed by the adopting organization's legal; governance; security posture with evidence; no secrets/
   real-data; no external-repo or non-EdgeForge/domain-specific references in committed
   content; dependency/license hygiene).
2. **Well-rounded & self-explanatory** — a new dev or AI agent can clone the suite in a
   new environment and *seamlessly* continue development: understand the architecture,
   set up in minutes, and start adding business logic immediately — including inside each
   *generated* app.

The suite spans **3 core repos** — Engine (`appbuilder`, this repo), Studio, and
Knowledge Server/Assist (KS/KA) — plus **2 optional** repos (TestBench and
shared-specs, **not required to import**; see
[`docs/suite-architecture.md`](suite-architecture.md) §2 for the canonical
core/optional split) and the generated apps the Engine produces. This is the
**suite-level master tracker**. Cross-repo tasks below (governance stubs, SBOM /
license inventory, reference scrub, etc.) apply to the repos an adopting
organization actually **imports** — the 3 core repos always, the optional repos
only if imported.

**Current posture (evidence-backed):** the three core repos carry governance and
import-gate evidence, but the composite lane remains partial because G5 reference
classification and active-reference cleanup are not complete. The coordinated
`v4.1.0` baseline is proven by the hermetic L5 acceptance run; Engine `v4.1.1`
adds the datasource-credential fail-fast fix. Remaining EdgeForge-owned work is
the explicit security, verification, generated-app, authoring, and documentation
backlog below. Adopter-owned gates remain open for each adopter to close;
maintainer publication authorization (G1) is a separate project gate.

For detailed public v5 source-and-tags release mechanics, see the
[Engine-owned M2 and release-readiness record](v5-release-readiness.md). It
separates confirmed distribution/hosting choices from recommended completion
rules and still-pending owner decisions; it is not a release approval.

**Historical planning decisions** (license posture superseded by approved revision 3 below): suite-wide scope; **onboarding front-loaded**
(import gates run in a parallel lane, not ahead of it); license, ownership, and the
internal/proprietary-vs-OSS posture remain an external adopter/legal decision (no
project-side license recommendation); naming = document-only (keep `appbuilder`
module/CLI; prominent "product = EdgeForge, module = appbuilder" note; no risky
pre-handoff rename).

---

## Prioritization & ownership

**Ownership / timing legend:**
- `[now-ours]` — EdgeForge work to do now.
- `[cheap-now]` — small EdgeForge task; do now.
- `[adopter-decides]` — an external gate or decision the adopter's legal owns (we *prepare*; they
  *decide*). Visible and required — **not optional**.
- `[post-import]` — deferred to in-house / the adopting organization's own pipeline.
- `[adoption]` — not import-gating; improves adoption; schedule flexibly (pre- or
  post-import). Used for Studio polish (D1) and the SSO design (D2).
- `[design-now / wire-later]` — design/scaffold now; final wiring (e.g. to the adopting organization's IdP)
  is `[post-import]`. Used on D2.

> The open-decisions list (E2) labels items by **decision owner** — `[adopter-decides]`,
> `[EdgeForge-decides]`, or `[EdgeForge-recommends]` (the adopting organization finalizes) — a separate axis
> from the task tags above.

**Highest value now (lead with these — only EdgeForge can produce them):**
1. Suite onboarding context + multi-tool agent files (B1, B2).
2. Generated-app `agent-context.md` emitter (C1).
3. Edge-contract handoff readiness matrix (C4).

**Cheap, do-now, ours:** reference scrub · pinned secret scanner plus reviewed
synthetic-only committed-data policy · governance stubs · SBOM + dependency-license
inventory · handoff security boundary map · portability checklist · quickstart ·
glossary/ADRs · pyproject · cross-repo table · data-governance posture · generated-app
secrets-fallback cleanup · handover-evidence index + README front-door.

**adopter-decides (external gates — visible, not optional):** shared-specs
consumption model · deploying/operating the authenticated gateway the P1-5 posture requires (the
generated-app auth **default** is Engine-decided — Option A, gateway-delegated) · whether scanners/CI
run in-house vs offline.

**Post-import / org-side:** full threat model · supply-chain provenance maturity (signed
tags, attestation, branch protection, enterprise scanners) · release/version-matrix
maturity · support/ownership finalization.

---

## Phasing overview

| Track | Theme | Timing |
|---|---|---|
| **Onboarding (front-loaded)** | B1–B6: suite context, multi-tool agent files, setup, quickstart, glossary/ADRs | Active now — highest value, EdgeForge-only |
| **Parallel Import-Gate Lane** | Visible, owner-tagged checklist of real import gates (governance, scans, SBOM, reference scrub, boundary map, license/ownership) | Runs **alongside** onboarding — does not block it |
| **Generated-App Strength** | C1 agent-context, C2 finish UX track, C3 quality residuals, C4 readiness matrix | With / after onboarding |
| **Compliance Hardening** | data-governance + boundary map `[now]`; threat model + supply-chain maturity `[post-import]` | Mixed |
| **Authoring & Auth Polish** | D1 Studio UX, D2 SSO architecture (design now, wire to the adopting organization's IdP later) | Not import-gating |
| **Docs & Decision Hygiene (ongoing)** | consolidation, support/ownership recommended split, open decisions | Ongoing |

> The import gate is a **visible parallel lane**, not a hidden backlog and not a pre-phase
> that delays onboarding. Adopter/legal-owned items are still **real gates** — they're tagged
> `[adopter-decides]` so they can't be confused with normal product work or skipped.

---

## Adopted v5 release and public-launch plan

**Supersession (2026-10-25): EF-V5-RELEASE-SCOPE-RESET revision 3 is approved.**
The [current source-release policy](v5-release-readiness.md) replaces the older
M2-before-publication deadline and old-repository E/P/R/M procedure. Retain
required CI, fresh audits, final exact-new-repository L5 (no skipped-success),
newcomer journey, selected Studio-image build/run, focused security QA and final
independent release review. New Ubuntu/Jackson investigations, exhaustive M2
closure, signing infrastructure and new evidence tooling are not source-release
prerequisites. OPEN findings and historical evidence remain unchanged.

Apache-2.0, NOTICE and DCO 1.1 without a CLA are selected; Santosh Hommaradi is
copyright holder/accountable maintainer. Maintainer publication authorization
is pending: it blocks public exposure, not private preparation. The secured `edgeforge-suite` organization
will host fresh private Engine/Studio/KS and `website` repositories using the
existing names. One public core, no separate enterprise edition; existing
`santosh-sh` repositories become private pre-v5 archives without history import,
rename, deletion or scrubbing.

The three preparation lanes may run and human-merge independently (KS starts
first); Engine owns this roadmap/tracker. Later lanes import frozen reviewed
trees, configure controls, select new release commits/pairing, run acceptance,
verify tags and perform human-directed public flip/PVR/site launch. No imports,
settings, tags or publication are authorized by preparation.

**Maintainer adoption: 2026-10-06.** The [reconciled external-review backlog](external-review-backlog.md)
records exact observation SHAs, completion criteria, XR-1–XR-11 dispositions,
ownership and the [parallel-work/merge plan](external-review-backlog.md#parallel-work-and-merge-order).
This is the priority order for the selected **single public-ready v5 tag**; the
tracker release row includes E1, G1, S8 and XR-5 preparation before its freeze.
Common acceptance proof still applies to a separately requested private baseline;
public-launch dependencies do not automatically become private-tag gates. Adoption
is not implementation, residual-risk acceptance or permission to merge/tag/publish.

| Priority | Work | Timing |
|---|---|---|
| 1 — DONE | Engine #325 merged 2026-10-07 as `eb30749` | Delivered correction; remaining review follow-ups belong to M2 closeout |
| 2 — DONE | Engine #327/#328 reads, #329 selected writes and #330 fixed demo/batch collisions merged | Bounded correctness prerequisites delivered; endpoint policy below remains adopted. No full D10 implementation. |
| 3 | Retain Engine #335/#336 and Studio #318/#319 known limitations with owner Santosh Hommaradi and upstream/dependency/recipe/next-selection/pilot review triggers | Continuing M2, not exhaustive source-publication closure; required checks and actual supported-behavior blockers still hold |
| 4 | E1/release preparation including XR-2 and RP-EVIDENCE-PURPOSE; license/contact, notices, content/history and CI readiness | Tagged claims before tag; public terms before publication; prepare source changes before freeze |
| 5 | S8/XR-4: one proven newcomer journey and task-based Studio guide | Before public launch, prepared alongside remediation |
| 6 | XR-5: contributor templates/guidance and bounded issue drafts | Before public launch; no recruitment gate |
| 7 | Fresh audits, exact new-repository pins, required repo/build/security checks, full L5, newcomer/selected-image/security QA and independent review, then human-directed verified tags | After reviewed tree imports and controls; distinguish tested source from later pairing/evidence commits |
| 8 | Public publication plus M6 website controls and authorized deployment | Before public exposure / hosting; no product-service hosting implied |

After v5, XR-3 is the first small CI improvement. Preserve **M3 → M4 → M5b**:
XR-6 refines the existing app-local testing requirement, XR-7 reuses M5b, and
XR-9 proceeds through bounded emitter refactors. XR-8a/8b are prerequisites for
pilots with concurrent updates/large data; XR-10 gates the corresponding hosted
Studio team service; XR-11 needs a concrete pilot. Newly confirmed defects still
require triage before deferral. Full generated-contract-test/event work retains
the [existing later prerequisites](suite-security-review-backlog.md#order).

Public project CI, release pairing and supported tool-file policy are project
responsibilities. Enterprise gateway, IdP, scanner and local tool-file policy
remain deployer responsibilities. Shared-specs/TestBench are outside this shipped
release. Pre-v5 test/demo output needs fresh regeneration, not a migration
programme; post-public-v5 updates must support v5+ apps under a defined policy.
No source, evidence, license or hosting decisions are silently marked complete.

## Endpoint boundary maintainer decision

**Adopted 2026-10-14: EF-V5-ENGINE-ENDPOINT-BOUNDARY-CLOSEOUT revision 1.**
Engine #329 is merged at `891705e20f150ef421f518a8a0fecac62246da8d`;
the [selected-write contract](write-operation-contract.md) records its bounded
transport support, DTO wire-name correction and shipped sample-pack protections.
The fixed demo/batch-controller collision correction is delivered by merged #330
at `ba56abd1e0ff946260e96f3a3b715564fc0b740d`. It does not change generic CRUD
availability, demo enablement or Batch semantics. Subsequent image evidence must
identify the actual generator containing these corrections; #330 alone is not
image vulnerability proof or M2 clearance. The [October 17 assessment](handover-evidence/generated-images/2026-10-17/README.md)
now records its actual generator, 30 cases/60 stage assessments and three
representative startups. OPEN image findings, six unresolved retained vendor
observations and pin-versus-float decisions remain distinct from completed
assessment coverage; this does not close M2 or authorize a release.

**Retain existing generic CRUD endpoints.** Selected OpenAPI operations do not
define the entire emitted API. Supported deployments must review the actual
emitted HTTP method/path surface and expose **only explicitly approved operations**
through the authenticated, TLS-terminating gateway. Unapproved CRUD, demo and
batch endpoints must remain inaccessible through that gateway, and the application
port must remain inaccessible except through it. Authentication alone does not
limit available methods/routes. Exposure approval is separate from adopter-owned
business/object/tenant/row authorization. Engine does not implement this gateway
policy, an endpoint allowlist or automatic gateway configuration. A demo runtime
disabled flag does not unregister its mappings. See the
[security posture](generated-app-standards/generated-app-security-posture-design.md)
and [operator checklist](generated-app-standards/deployment-operations-runbook.md).
This supersedes the prior open, unadopted generic-CRUD policy decision; it is not
approval to expose every generated endpoint.

**Engine-owned post-v5 limitation: `int32` transport range enforcement.** Affected
integer transport parameters currently bind as Java `Long`; declared
`format: int32` does not enforce signed 32-bit bounds. Adopters requiring those
bounds must validate before business, persistence or downstream effects. Completion
requires rejecting out-of-range values at affected supported transport boundaries,
with boundary regressions and preservation of valid values, `int64`, persistence
identity and database types. This task changes no integer binding or database type.
The maintainer defers this validation correction until after v5; no vulnerability
risk acceptance, full OpenAPI conformance, M2 completion or release acceptance is
established, and no other requirement is waived.

## Current prioritized backlog (post-v4.1.1)

The 2026-08-11 programme order below is retained with current status corrections.
The adopted v5/public-launch plan above now determines release timing; in
particular, the programme's M3/M4/M5b "must" tier is **post-v5**, not a tag gate.
The programme supersedes the older wave ordering, while the detailed roadmap
sections below remain the design/history source. The derived tracker mirrors these
rows; it does not replace them. The phased Studio UX refresh is **complete**: Studio
PR #280 made the refreshed presentation the default and retired the rollout flags,
and PR #281 added presentation-only visual polish. It is deliberately excluded from
the unstarted ranking. **A11y-01 remains open as a Studio-owned accessibility
follow-up**, tracked independently from the completed Action-5 build. A controlled
native desktop successful-save observation against Studio `d23d99f` failed because
VoiceOver announced button guidance but not the save outcome; the other three required
desktop/narrow success/failure observations were not run.

The revised coordinated policy recorded in
[Studio PR #299](https://github.com/santosh-sh/EdgeForgeStudio/pull/299) and
[Engine PR #313](https://github.com/santosh-sh/EdgeForge/pull/313) is active
after both amendments merged. A11y-01 alone no longer blocks source
publication, internal baselines or tags, public releases, or promoted demos.
It remains a Studio-owned
[open known limitation](https://github.com/santosh-sh/EdgeForgeStudio/issues/302), and all
four native observations must pass before A11y-01 can be closed or spoken save outcomes can
be described as verified. Studio issue #302 records the impact and reproduction and is
publication-ready, but Studio is currently private. Any otherwise authorized public release
or promoted demo while Studio remains private must carry an audience-accessible notice of
this known limitation, including its impact and reproduction summary. Link #302 as a public
contribution path only once it is publicly accessible. Disclosure does not require A11y-01
completion. This narrow exception is not a pass, waiver, accessibility certification,
release authorization, or exception to any other acceptance gate.

**Tier meaning:** `must` protects a current security boundary, acceptance claim, or
hosted/adopter exposure; `should` is the next adopter-value product work; `nice` is
demand- or evidence-driven follow-on work.

> **Security remediation (2026-07 suite review):** the reconciled cross-track execution order —
> including pairs that are unsafe to run concurrently — lives in
> [`docs/suite-security-review-backlog.md`](suite-security-review-backlog.md) §8.

### Must-have sequence

| Order | ID | Item | Repo / effort | Timing and dependency |
|---|---|---|---|---|
| 1 | **M1 — COMPLETE** | Known security follow-ups: hardened SAAJ factory, design-time XSD/WSDL parser bounds, Engine OpenAPI-fetch SSRF posture, and operator-console exposure guidance | Engine + generated apps / S-M | Completed by Engine PRs #276/#277/#278/#281; retained as the closed guardrail anchor |
| 2 | **M5a — COMPLETE** | Staging handoff production semantics: durable run identity, restart, and idempotency | Engine + generated apps / M-L | M5a-S1 through M5a-S4 are delivered after complete V2-X. Valid opted-in packages may generate/plan/apply, and their failed run-identity harness checks are blocking without changing legacy warning behavior. M3 owns later registration of the reserved scenarios. |
| 3 | **M2 — IN PROGRESS** | Continuing vulnerability assessment, coverage and disposition programme | all core + generated apps / M-L | Engine #335/#336 deliver the latest bounded Python/plugin corrections and decision records. Historical image/Maven identities and OPEN statuses remain. Under approved scope-reset revision 3, exhaustive closure and new Ubuntu/Jackson investigations are not source-release prerequisites. Use [known limitations and retained gates](v5-release-readiness.md#source-release-known-limitations-and-m2); required audits/checks and actual shipped defects still block. No broad M2 or production clearance. |
| 4 | **M6** | Informational website and reporting-route cutover | suite / S decision; M wiring | Canonical edgeforgesuite.com, www/edgeforgesuite.app/edgeforgecontracts.com redirects, Cloudflare protected previews, accountable maintainer Santosh Hommaradi selected. Email/PVR activation, provider logs/retention, telemetry, TLS, artifact, deployment and rollback proof remain pending under [M6](v5-release-readiness.md#m6-hosting-and-contact-gates). No live product service; no public exposure before maintainer publication authorization. |
| 5 | **M3** | Change-aware Suite Verification Pack built **on** L0-L5: scenario registry, reusable synthetic inputs/expected outputs, affected-test selection, bounded deterministic replay, a SHA-moved-triggered full run + weekly heartbeat (the gated design replaced unconditional nightly), and sanitized evidence bundles | all core / M-L | Retain PR-24's completed checklist as repeatable default-on regression/evidence coverage; do not create a second harness. A narrow post-PR-24 amendment must replace the design's removed rollout-flag assumptions before VS0/VS1/V-ACT build |
| 6 | **M4** | Generated-app enterprise agent guardrails: retain factual `agent-context.md`, add an adopter-owned policy seam, explicit ownership/contract rules, required verification commands, and human/enterprise-policy precedence | Engine + generated apps / M | Design first; tool-specific agent files remain opt-in; no manifest-v2 semantic change |
| 7 | **M5b** | Remaining generated-app operational baseline: separate probes, CRUD structured logging, and CI descriptor | Engine + generated apps / M | After the risk-critical slices above; may run Engine-parallel when ownership is clear |

### Should-have sequence

| Order | ID | Item | Repo / effort | Timing and dependency |
|---|---|---|---|---|
| 1 | **S1 — COMPLETE** | Loadable synthetic Domain Sample Packs aligned to the website's Financial Services, Healthcare/Payer Operations, and Insurance lenses | Studio + Engine fixtures / S-M | [Pinned 2026-09-04 acceptance](test-results/domain-sample-packs-2026-09-04.md) completed open/export/generate/build/independence proof. Not generated-app runtime or database/container proof; reuse in S8, without claiming current-pin acceptance. |
| 2 | **S9** | Bounded docs-staleness sweep across Engine, Studio, and KS | all core / S | May start now as one controlled chore batch; use the confirmed checklist below |
| 3 | **S8** | Curated onboarding bundle plus XR-4's task-based Studio guide and one automatic newcomer journey | Studio-led / M | Before public launch; S1 is delivered. [XR-4 criteria](external-review-backlog.md#xr-4-one-newcomer-journey): one clean reference setup, real generated-app responses, supported change/regeneration and troubleshooting. Reuse proof helpers; no exhaustive manual/platform matrix. |
| 4 | **S2** | Workbook-driven bulk pre-population, absorbing D1 layout-template upload into the deterministic reviewable seed-patch model | Studio / M-L | PR-13 and PR-15 are merged and the UX refresh is now default; take a fresh capture/design pass against the shipped UX before defining a build contract. Do not start a competing UI path |
| 5 | **S3** | Printable Review Dossier for contracts, mappings, rules, provenance, readiness, and decisions | Studio / M | PR-24 is complete; define the render model when this item reaches its ordered slot. Design it to slot into, not duplicate, the handover-evidence structure |
| 6 | **S4** | Minimal source-conflict vocabulary for authored state vs re-inspected evidence | Studio + KS / M | Design now; keep it bounded to the semantics S5/S6 need, not a suite ontology |
| 7 | **S5** | Semantic Manifest Change Summary between approved exports | Studio / M | PR-24 is complete; requires a durable prior approved export and reuses S4 vocabulary |
| 8 | **S6** | Contract Drift Watch: re-upload a newer contract, re-run existing inspectors, and report deterministic drift against authored state | Studio / M | PR-24 is complete; depends on S4 and shares the S5 renderer/model rather than adding a third diff engine |
| 9 | **S7** | Kafka/passthrough UX follow-ons and KA review hardening | Studio + KS / L | PR-24 is complete, but this remains ninth in the Should queue; KA build remains gated by its production data-handling decision |

**S9 historical sweep checklist (2026-08-11; recheck remaining items):** update Studio `docs/studio-context.md` from its
stale `v3.0.0` / pre-multi-session posture; remove the obsolete "enforce when
#200 lands" wording from Studio `docs/studio-ux-refresh/implementation-design.md`
§1.3; correct the already-fixed passthrough navigation status in Studio
`docs/studio-ux-v2-design.md` and `docs/studio-implementation-plan.md`; and reconcile
KS `README.md` / `docs/security-boundary-map.md` wording that still describes a
provider-backed AI capability as merely off or future-gated. This refresh removes
the already-merged Step-6 B3 fix from Engine `docs/current-implementation-sequence.md`,
classifies that file as a historical snapshot, and routes current-plan pointers to
this roadmap and the generated tracker. Studio `CLAUDE.md` / `CONTRIBUTING.md`
already state the current two-mode posture and need no S9 change. KS's `v4.0.0` tag remains historical while
current `main` carries a `4.1.0` package posture plus post-tag runtime hardening;
the coordinated release pass must reconcile that version/tag state explicitly.

**2026-10-06 correction:** KS #41/#43 delivered the KS-owned boundary/evidence
documentation corrections; do not schedule them again from this dated checklist.
The current E1 release slice is XR-2 and the public-source preparation above;
verify remaining Studio/current-release facts against the selected revisions.

### Nice-to-have / demand-driven

| ID | Item | Repo / effort | Trigger |
|---|---|---|---|
| **N1** | Kafka-router performance polish | Engine / S-M | Benchmark or adopter scale need |
| **N2** | Remaining test-console artifact/workflow/sweep slices | Engine / M | Artifact-serving mini-design and demonstrated operator need |
| **N3** | New edge families, high-TPS/identity expansions, and LegacyExtractor | cross-repo / L-XL | Concrete adopter demand plus approved family-specific design |

**Execution guardrail:** `M1 (complete) -> V2-E/V2-S/V2-X -> M5a (complete) -> M2/M6 decisions -> M3 -> M4 -> M5b`.
`S1` and `S9` may run without contending with the completed Studio refresh. `S2` is technically
unblocked but requires a fresh capture/design pass against the shipped UX. PR-24 no longer blocks
`S3`, `S5`, `S6`, or `S7`; they still follow the Should-tier order above and must not displace the
v5 security/release floor. The KA portion of `S7` remains production-data-handling gated.

**Manifest 2.0 decision gate — complete:** M5a §13.2 is resolved; V2-E makes Engine
`2.0`-only with no `1.0` compatibility bridge; V2-S makes Studio emit `2.0`; and
both paired-branch and post-merge V2-X checkpoints passed. M5a-S1 delivers contract recognition and
fail-closed validation, M5a-S2 delivers the bounded Batch identity/restart layer, M5a-S3 delivers
the per-handoff uniqueness/upsert boundary, and M5a-S4 delivers per-handoff opt-in blocking in the
existing compatibility harness. M5a implementation is complete; M3 registration remains deferred.

---

## Parallel Import-Gate Lane

Project publication prerequisites and adopter-owned import checks are distinct.
The latter apply when an adopter chooses an internal deployment or fork. Both
are owner-tagged and run alongside onboarding.

- **G1. Publication authority — maintainer gate.** Apache-2.0,
  NOTICE, DCO 1.1 without a CLA and copyright Santosh Hommaradi are selected.
  Maintainer publication authorization remains pending
  before any public exposure, not private preparation. Keep correspondence
  private. This supersedes the earlier unselected/proprietary license wording.
  Adopters still separately review their usage and operating obligations;
  they do not choose the project's license. See the approved [release policy](v5-release-readiness.md).
- **G2. Governance stubs — `[cheap-now]`.** `SECURITY.md`, `CONTRIBUTING.md` (promote the
  rules from `CLAUDE.md`), `CODEOWNERS`, `.github/pull_request_template.md`. [all repos]
- **G3. Secret scanning + synthetic-data policy evidence — `[cheap-now]`.** Run a
  pinned named secret scanner in CI, plus a synthetic-only committed-data policy
  checked through human review. No automated PII or real-data detector is claimed.
  Record auditable evidence for both scopes. [all repos]
- **G4. SBOM + dependency-license inventory — `[now-ours]`.** Engine (Python) + Studio +
  KS + the generated-app Maven output (plus TestBench / shared-specs only if imported).
  Enterprises ask for this.
- **G5. Reference scrub (committed content) — `[now-ours]`.** Remove from committed
  content any references to **external (non-enterprise) repositories** and any
  **non-EdgeForge/domain-specific or third-party product/customer names**; replace
  external-spec references with project-neutral ones (each adopter chooses its own
  shared-specs consumption, G6); verify semantic/reference compliance through review.
  Bounded mechanical guards may
  verify exact fixture structure or explicitly named identifiers, but no scan is
  claimed to prove repository-wide semantic neutrality. PR #291 supplies the
  completed exact-shape guard for the canonical generated-app CI fixture only;
  example classification and active-reference cleanup remain pending. Local
  scratch/demo artifacts stay untracked or git-ignored, never committed. (This
  roadmap is written without enumerating such names/URLs, so the committed doc
  stays domain-neutral.) [all repos]
- **G6. shared-specs distribution & version-pin policy — `[adopter-decides]`.** Adopters
  choose how to consume optional shared specs (vendored copy / submodule / published
  package / pinned tag) and pin their chosen version. Project support for a mode
  follows ordinary contribution and review; no implementation is promised. Review
  applicable external references under G5.
- **G7. Portability checklist — `[now-ours]`** → `docs/compliance-and-portability.md`.
  Network assumptions, local-only MCP behavior, any external URLs, the generated-app
  standalone boundary, and **no runtime dependency on EdgeForge/Studio/KS/MCP**.
- **G8. Handoff security boundary map — `[now-ours]`** (a lightweight now-doc; **not** a
  full threat model, which defers — see Compliance Hardening). Captures the trust/data-flow
  posture an import reviewer needs up front:
  - Engine = CLI / MCP / control-plane (no network service, no login).
  - Studio stores/imports project artifacts (workspace storage + cleanup posture).
  - KS indexes documents **locally and deterministically**.
  - Generated apps are **standalone**.
  - KS has **no LLM or provider integration today**; any future model-backed connection is a separate
    adopter-controlled data boundary.
  - **No generated-app runtime dependency** on EdgeForge / Studio / KS.
- **G9. KA/AI production data-handling decision — `[adopter-decides]` / posture-now.**
  Deterministic KS scopes are allowed. KS has no LLM or provider integration today; KS-B5
  (PII/sanitization/redaction) gates any future provider layer or adopter-controlled model-backed
  MCP connection.
- **Import-critical CI subset — `[cheap-now]`.** Secret scanning, dependency/license
  inventory, basic green CI. Deeper CI maturity is in Compliance Hardening.
- **G10. Handover-evidence pack + README front-door — `[now-ours]` — ✅ done.** A consolidated
  index ([`docs/handover-evidence/README.md`](handover-evidence/README.md)) links the
  portability/compliance checklist (G7), SBOM + dependency-license inventory (G4),
  secret-scan and synthetic-data policy evidence (G3), the security boundary map (G8), the edge-contract
  readiness matrix (C4), governance files (G2), CI evidence, and the publication/usage summary
  (G1, maintainer gate; adopters review their own use). An **"Import & handover
  readiness"** section in the **root `README.md`** links that index + the suite
  architecture doc (B1) — so an import reviewer
  (or their scanning) can **start at the README and reach every evidence artifact in one
  hop**, verify, and return comments without digging. (The same front-door also serves the
  AI/dev onboarding goal.) G10 provides the Engine evidence front-door; it does
  not close G5 or the composite Engine-owned import-gate lane. See the
  execution-checklist appendix for per-item, cross-repo, and adopter-gate status.

---

## Onboarding (front-loaded)

Goal: any human or AI agent (Claude / Devin / Copilot / Codex) can land in the imported
repo and become productive without tribal knowledge.

- **B1. Suite architecture & repo-structure "START HERE" doc** `[now-ours]` [Engine;
  suite-level] — map the whole suite (3 core repos + optional tooling + generated apps), how they relate (Engine
  generates; Studio authors; KS/KA suggests; TestBench exercises; the Engine owns the
  manifest contract that producers conform to), the core theses (canonical internal
  model, dual-edge contract preservation,
  manifest-driven, deterministic output, mode semantics), the build/review workflow, and
  the invariants. Consolidate `docs/appbuilder-context.md` + `docs/repo-blueprint.md` →
  `docs/suite-architecture.md`; link from `docs/README.md` + root `README.md`.
- **B2. Multi-tool agent onboarding files** `[cheap-now]` [each repo] — keep `CLAUDE.md`;
  add `AGENTS.md` (Codex/Devin) and `.github/copilot-instructions.md` (Copilot), thin and
  pointing to B1.
- **B3. Reproducible setup** `[cheap-now]` [Engine; pattern for all] — `pyproject.toml`
  (`requires-python = ">=3.11"`, deps) + a `Makefile` / `.devcontainer/` with
  `setup`/`test`/`generate-sample`/`mcp` one-liners; explicit prerequisites in README.
- **B4. End-to-end quickstart ("golden path")** `[cheap-now]` [Engine; suite-level] —
  10-minute clone → setup → generate the independent Workspace/Item sample → run → exercise the test console. →
  `docs/quickstart.md`.
- **B5. Glossary + ADRs** `[cheap-now]` [Engine; suite-level] — `docs/glossary.md` + a few
  `docs/decisions/ADR-*.md` capturing *why* (canonical model, dual-edge contracts,
  family-agnostic descriptor model, determinism, generated-app standalone).
- **B6. Naming note (document-only)** `[cheap-now]` [Engine] — "product = EdgeForge;
  module/CLI = `appbuilder`"; no rename. Optional CLI alias considered later, in-house.

---

## Generated-App Strength

- **C1. Generated-app `agent-context.md` emitter** `[now-ours]` [Engine] — *(highest-value
  new feature)*
  - **Default emission:** a deterministic `agent-context.md` **+ enriched `README.md`** in
    each generated app, surfacing what's lost at generation today: purpose + archetype +
    bounded context; preserved edge contracts + families; identity roles with **mode**
    (active vs metadata-only); rules applied vs selected-but-metadata-only; ingestion notes
    + translation warnings; downstream handoff topology + staging DDL refs; secrets/env-var
    config expectations; and a clear **"where to add business logic"** section.
  - **Tool-specific stubs are OPT-IN:** `CLAUDE.md` / `AGENTS.md` /
    `.github/copilot-instructions.md` inside *generated* apps can conflict with the adopting organization's
    policy/tooling — emit only via a target-profile/generation option or documented
    enterprise policy. Deterministic `agent-context.md` + README are the always-on default.
  - Strictly typed-empty / no-business-inference. Where: `_render_agent_context()` beside
    `_render_readme()` in `appbuilder/generation/build_emitter.py`; wire into
    `appbuilder/generation/engine.py`. Reuse `MetadataProject` (`identity_roles` +
    `IdentityRoleMode`, `contracts[].ingestion_notes`, `rules[]`, `warnings`,
    `staging_table_ddls`, `systems`, `app_archetype`, `target_profile`).
- **C2. Finish the test-console UX track** `[now-ours]` [Engine — Engine design thread] —
  3c (merged, #203) → 3b (artifact viewer; needs packaging mini-design) → Slice 5 (workflow
  tools) → Slice 6 (cross-family test + build-proof sweep). Tracked by
  `docs/generated-app-standards/generated-app-test-console-ux-design.md` §12.
- **C3. Quality-gate residual triage** `[now-ours]` [Engine] — from
  `docs/generated-app-standards/generated-app-engine-roadmap.md`: B5 (split K8s liveness/
  readiness), B6 (MDC/structured logging in the CRUD lane), B8 (CI descriptor *into*
  generated apps), PR9 (Kafka router perf), PR10 (source-contract conflict surfacing).
- **C4. Edge-Contract Handoff Readiness Matrix** `[now-ours]` [Engine; suite-level] —
  *(main Track-B addition)* an honest, status-tagged matrix so the adopting organization sees a polished,
  truthful supported surface — not a mix of implemented / in-flight / design-only presented
  as ready:
  - **Family matrix by status:** `implemented/proven` · `implemented/needs-UX-proof` ·
    `design-only` · `parked`.
  - **File contracts:** fixed-width + CSV ingest/output, explicit ID behavior, trailer/
    reconciliation status, durable demo pack.
  - **XML/XSD:** ingest/output runtime proven; track malformed-XML + missing-mapped-field
    diagnostics as a demonstration-readiness gap.
  - **SOAP/WSDL:** inbound `read_by_id`, outbound invocation, adapter diagnostics, and the
    generated-app operator/test-console cards — represented honestly at **MVP scope**; do
    not imply broad SOAP operation semantics beyond the current MVP.
  - **Test console / action-card standard:** required so file/XML/SOAP runtime paths are
    visible and usable by import reviewers (ties to C2).
  - **Golden smoke packages:** one file-contract app, one XML/XSD app, one SOAP app — each
    with generate/build/runtime proof commands.
  - Scope note: Wave 2/3 contracts need **not** all be done before handoff; the matrix just
    prevents presenting a half-built vertical as fully handoff-ready.
  - **Delivered:** [Edge-Contract Handoff Readiness Matrix](edgecontracts/edge-contract-handoff-readiness-matrix.md)
    (anchored on the PR #220 v1 closeout + the 2026-06-09 integrated smoke).

---

## Compliance Hardening

- **Data governance / PII posture** `[now-ours]` [suite-level] — Studio upload/workspace
  storage + cleanup; KS index storage, retention, delete/reingest; no current LLM/provider integration;
  future integration is KS-B5-gated;
  **synthetic-only** sample/demo data policy; generated-app log PII-redaction posture (+
  remaining B6/MDC work); **Evidence Trail as an audit artifact** — what it proves, what it
  does not, and how it's preserved after Studio export.
- **Deeper CI maturity** `[post-import]` [Engine; pattern for all] — type-check (`mypy`),
  coverage targets, broader security gates (CodeQL), full lint maturity. (Import-critical CI
  is in the gate lane.)
- **Full threat model** `[post-import]` [org-side] — adopting organizations threat-model on import against
  *their* controls; the now-equivalent is the G8 boundary map.
- **Supply-chain provenance maturity** `[post-import]` [adopter pipeline] — signed/attested
  tags, branch protection, enterprise scanners, release infrastructure. (SBOM + dependency-
  license inventory remain in the gate lane as `[now-ours]`.) For the confirmed
  source/tag-only v5 launch, the [proposed minimum](v5-release-readiness.md#recommended-narrow-m2-completion-contract)
  is exact source/tag identities, hashes and repeatable evidence, not a claim
  that annotated tags are cryptographically signed. Published packages/images
  would require a new artifact-specific integrity contract.

**Public-project ownership amendment (2026-10-06):** the three maturity items
above are also project-owned post-v5 improvements, not work reserved solely for
an enterprise importer. XR-3 is the bounded first lint slice of deeper CI;
incremental types, broader analysis, threat modelling and signing remain later.
The adopter still performs its local threat assessment and operates its own
scanners/infrastructure. Current branch protection, audits and release pairing
are existing release controls, not deferred by this maturity label. Current
declared transitive dependency/SBOM coverage belongs to M2; custom/adopter
dependencies need their own audit, not a duplicate Suite release task.

---

## Authoring & Auth Polish (adoption; not import-gating)

- **D1. Studio UX improvements** `[adoption]` [Studio repo] — upload downstream
  file-layout definitions in a popup (not a long step-5 page); a pre-defined xlsx/csv
  **layout template** so users don't hand-key every field; explore the same upload-template
  pattern for other upstream/downstream contracts to keep authoring in sync and pages simple.
- **D2. SSO / auth architecture** `[design-now / wire-later]` [Studio + (conditionally) KS;
  generated-app config] — Engine = **no login** (local CLI/MCP tool). Generated apps stay
  **standalone**. P1-5 resolved the generated-app posture as gateway-delegated (Option A) for v5: no
  shipped profile emits in-application authentication; `appbuilder/generation/security_emitter.py` is an
  **internal dormant emitter**, not active in any shipped profile and not a supported extension surface —
  see the [P1-5 design](generated-app-standards/generated-app-security-posture-design.md). **Studio is the
  primary SSO surface.** **KS needs direct auth only if deployed as a network service**; if
  KS stays local/subprocess under Studio control, Studio auth governs access. Design
  pluggable OIDC/SAML now; wire to the adopting organization's real IdP after import.

  **XR-10 ownership split:** D2 retains deployer-owned IdP wiring/configuration.
  Separately, a project-supported Studio team-service offering requires
  real identity/access/audit proof before that offering. The project owns its
  supported integration, the operator its IdP/configuration. Website hosting and
  public source distribution do not alone trigger that service scope; local
  stdio KS needs no new network authentication.

---

## Docs & Decision Hygiene (ongoing)

- **E1. Docs consolidation + suite sync + archive sweep** `[cheap-now]` [all repos] —
  consolidate overlapping roadmaps under the `docs/README.md` front-door, refresh dates,
  sweep superseded docs to `docs/archive/`, prune stale git worktrees, align the docs/ shape
  across the imported repos (the 3 core repos always; TestBench / shared-specs if imported).
  For v5, use the bounded [XR-2/release preparation criteria](external-review-backlog.md#xr-2-release-claims-and-evidence-purpose),
  including RP-EVIDENCE-PURPOSE. Broad archive/worktree cleanup is not a release
  prerequisite. Contributor basics (XR-5) are a separate small launch deliverable.
- **E2. Pending-work triage + open decisions** [Engine; suite-level] — triage the
  categorized backlog (~60 items) under the approved **pre-v5 / post-v5 scope**,
  and record open **project and adopter-local decisions** in `docs/decisions/`:
  1. Active `parent_reference` (Phase 2a) — merge vs defer. `[EdgeForge-decides]`
  2. KA-AI production data-handling gate (KS-B5) — decide the controls required before any future KS
     provider or model integration. `[adopter-decides]`
  3. Generated-app ownership/licensing for the adopter's deployment. `[adopter-decides]`
  4. shared-specs distribution model — vendored / submodule / package / pinned tag (G6). `[adopter-decides]`
  5. Whether AI/tool-specific repo files are allowed in imported repos and generated
     apps (drives C1's opt-in stubs). `[adopter-decides]`
  6. ~~Generated-app auth default~~ — **RESOLVED (Engine-decided, not adopter-decides):** P1-5
     adopted gateway-delegated security (Option A) for v5. No shipped profile emits in-application
     authentication; the OAuth2 skeleton is retained as an internal dormant emitter, not a supported
     extension surface. See the
     [P1-5 design](generated-app-standards/generated-app-security-posture-design.md). The remaining
     adopter-owned piece is operating the required TLS-terminating authenticated gateway — see item 6a.
  6a. Deploy and operate the authenticated gateway the P1-5 posture requires (the application port must
      be unreachable except through it). `[adopter-decides]` (deployment/operations, not a posture
      choice)
  7. Release/version matrix for the shipped Engine/Studio/KS tuple is project-owned
     and required for v5; use the release record and observed acceptance SHAs.
     Adopter release policy and optional TestBench/shared-specs distribution remain
     separate. `[project-owned + adopter-local policy]`
  8. Edge-contract readiness gate — which families need runtime proof for adopter
     evaluation (ties to C4). `[EdgeForge-recommends]`
  9. Whether GitHub Actions/scanners run in-house or need offline/internal
     equivalents. `[adopter-decides]`
- **E3. This roadmap as the master tracker** — `docs/enterprise-readiness-roadmap.md`,
  cross-referenced from `docs/README.md`.
- A derived, filterable task-level view across the suite lives at [`docs/tracker/`](tracker/README.md) (this roadmap stays the narrative source of truth).

---

## Support / ownership model — **recommended split** (`[adopter-decides]`; EdgeForge recommends)

An adopter assigns its own internal maintenance responsibilities for a deployment
or fork; this does not change public-project governance. Recommended component split:
- **Engine** owns the generation contract and the **authoritative manifest schema**
  (`appbuilder/schema/manifest-v2.schema.json`; manifest → generated artifacts;
  V2-E, V2-S, and both V2-X checkpoints are complete);
  producers conform to it.
- **Studio** owns authoring / export UX.
- **KS / KA** owns deterministic suggestions / indexing.
- **TestBench** owns runtime proof.
- **shared-specs** (if adopted) owns only an optional published/distributed **copy** and the
  versioning of the Engine's manifest schema — not the schema itself.
- **Generated apps** are owned by the **consuming app teams** after generation.

Also record: what is **supported** vs **experimental** vs **parked**, and how shared-specs
versions are promoted and consumed.

---

## Cross-repo responsibility (gate-lane + onboarding)

| Repo | Responsibilities |
|---|---|
| **Engine** | manifest/generation; generated-app context (C1); SBOM for Python + generated Maven output; target profiles; contract runtime-proof packs (C4) |
| **Studio** | SSO design; workspace/storage/retention posture; edge-contract import UX; export/package proof; KA-OFF cleanliness |
| **KS / KA** | deterministic scopes; policy gate for any future provider/model integration; index storage/retention/delete behavior; KS-B5 data-handling gate |
| **TestBench** | what runtime behavior it proves today vs not; whether file/XML/SOAP proof is Engine-only or TestBench-bound |
| **shared-specs** | optional published/distributed **copy** of the Engine-owned manifest schema: version pinning + compatibility rules and release notes; adopters choose their consumption mode (G6) |

---

## Source ideas — how they map (reviewed / challenged / placed)

| Source idea | Disposition | Where |
|---|---|---|
| 1. EF context / repo-structure for AI onboarding | Kept + expanded to suite-level + multi-tool agent files | B1, B2 |
| 2. SSO / does EF need login | Challenged: Engine = no login; apps standalone; Studio = primary SSO; KS only if networked; design now, wire later | D2 |
| 3. Generated-app improvements + UX final | Kept; UX track + quality residuals + readiness matrix | C2, C3, C4 |
| 4. Generated-app README / agent-context.md | Kept — strongest new feature; default emit + opt-in tool stubs | C1 |
| 5. Studio UX (layout popup, templates) | Kept; adoption polish | D1 |
| 6. Sync /docs + archive | Kept; tighten + suite-sync + prune worktrees | E1 |
| 7. Review pending/planned work | Done by the sweep; now triage + decisions | E2 |
| 8. Added ideas | governance/license-gate, pyproject, CHANGELOG, CI (gate vs maturity), quickstart, glossary, ADRs, devcontainer/Makefile, portability checklist, secrets-fallback cleanup, naming note, KA-AI gate | gate lane, onboarding |
| + Debate w/ Codex | visible owner-tagged import-gate lane; license as external adopter gate; G8 security boundary map now (full threat model deferred); SBOM-now / supply-chain-maturity-later; recommended (not final) support/ownership split; C4 readiness matrix; data governance + Evidence Trail; cross-repo table; generic domain-neutral wording | gate lane, C4, Compliance Hardening, support/ownership |

---

## Verification (per-initiative "done")

- **Import-gate lane:** every imported repo has governance stubs; a pinned named
  secret scanner provides clean configured-pattern evidence; synthetic-only
  committed data is a contributor policy checked through human review, with no
  automated PII/real-data detector claimed; SBOM + license inventory is generated
  (all imported repos + generated Maven); G5 semantic/reference compliance is
  reviewed, with bounded guards only where explicitly stated; the G8 boundary map
  exists; `docs/compliance-and-portability.md` answers each import question.
  **An adopter assesses its own usage and operating obligations. Project
  publication authorization (G1) is a separate maintainer prerequisite.**
- **Onboarding:** fresh clone + `make setup` runs tests green and generates the Workspace/Item sample
  per `docs/quickstart.md`; an agent reading `docs/suite-architecture.md` + the per-tool
  files can describe the suite and locate the right repo for a task.
- **Generated-app:** regenerate a sample → it contains `agent-context.md` + enriched README
  with correct identity-role modes / preserved contracts / warnings; tool stubs only when
  opted-in; `mvn -q -DskipTests package` succeeds; the C4 matrix reflects real status; the
  three golden smoke packages build and run; determinism holds (byte-identical regen).
- **Compliance hardening:** data-governance posture documented; deeper CI / threat model /
  supply-chain maturity tracked as post-import.
- **Polish:** Studio layout-upload + template reduce field-entry effort; auth architecture +
  generated-app SSO wiring documented.
- **Hygiene:** `docs/README.md` is the single front-door; all handoff decisions recorded in
  `docs/decisions/`.
- **Enterprise-ready MVP (cross-repo acceptance):** the suite-level integration risks (multi-session
  isolation, Studio→Engine/KS per-session paths, regeneration safety, generated-app runtime, KA-OFF
  cleanliness, shared-mode security) are proven by the layered smoke harness —
  [`docs/suite-smoke-harness-design.md`](suite-smoke-harness-design.md). Its **L5 full acceptance
  smoke is the gate** before a coordinated suite baseline / tag / enterprise handoff; per-repo unit
  tests (L0) stay primary for local correctness.

## Execution note
Most onboarding / generated-app / cheap-gate items are Engine-repo and proceed via the
established build→review loop (Codex builds on a branch, Claude reviews, PR-only, never push
to main). Cross-repo items (Studio/KS/TestBench/shared-specs) need their own threads but
follow the same patterns and reference this master roadmap.

---

## Appendix — Execution checklist (ordered)

> Single ordered view for tracking. `Cx` = complexity; `~PRs` are estimates (cross-repo
> items multiply). Parallelism: tasks 14–16 can run alongside Wave 1; the only hard deps
> are **G10 needs G3/G4/G7/G8** and **B4 wants B3**. C2 is already in motion (3c merged).
>
> "`all 5`" below is an upper bound — cross-repo items apply to the repos an
> adopting organization actually imports: the 3 core repos (Engine/Studio/KS-KA)
> always, and TestBench / shared-specs only if imported.

**Wave 1 — Onboarding + cheap import-gate foundation**
- [ ] 0. Ratify this roadmap (#204) — Low — Engine (docs) — 1 (this PR)
- [ ] 1. **B1** Suite "START HERE" doc — consolidate context into one suite map — Low‑Med — Engine — ~1
- [ ] 2. **B2** Multi-tool agent files (`AGENTS.md`/copilot) → point to B1 — Low — all 5 — 1–5
- [ ] 3. **B3** Reproducible setup (`pyproject.toml` + Makefile) — Low‑Med — Engine — 1
- [ ] 4. **B4** Quickstart (golden path) — Low — Engine — 1
- [ ] 5. **B5** Glossary + ADRs — Low — Engine — 1
- [ ] 6. **B6** Naming note (doc-only) — Low — Engine — 0–1 (fold into B1)
- [ ] 7. **G2** Governance stubs (SECURITY/CONTRIBUTING/CODEOWNERS/PR template) — Low — all 5 — 1–5
- [ ] 8. **G3** Pinned secret scanner + reviewed synthetic-only-data policy evidence — Low‑Med — all 5 — 2–5
- [ ] 9. **G4** SBOM + dependency-license inventory — Low‑Med — all 5 + gen Maven — 2–5
- [ ] 10. **G5** Reviewed reference scrub (bounded guards do not prove repository-wide neutrality) — Low‑Med — all 5 — 1–5
- [x] 11. **G7** Portability checklist ([`compliance-and-portability.md`](compliance-and-portability.md)) — Low — Engine — 1 — done
- [x] 12. **G8** Security boundary map — Low — Engine — 1 — done ([`security-boundary-map.md`](security-boundary-map.md), PR #224)
- [x] 13. **G10** Handover-evidence index + README front-door — Low — Engine — 1 — done ([`handover-evidence/README.md`](handover-evidence/README.md))

> **Import-gate lane status (2026-08-16): the Engine-owned composite lane is
> partial.** G2, corrected G3, G4, G7, G8, and G10 are delivered for Engine and
> reachable from
> [`docs/handover-evidence/README.md`](handover-evidence/README.md). G3 means the
> pinned gitleaks configured-secret-pattern gate plus a synthetic-only committed-data
> policy checked through human review; it does not claim automated PII detection.
> G5 remains pending while example classification and active-reference cleanup
> establish and apply the policy boundary. PR #291's canonical-fixture shape guard
> is a completed bounded control, not a repository-wide semantic-neutrality scan.
> Cross-repo state remains represented separately. The **adopter gates** (G1
> license/ownership, G6 shared-specs model, deploying/operating the P1-5-required
> authenticated gateway, scanners
> in-house vs offline) remain `[adopter-decides]`; the **post-import** items (full
> threat model, supply-chain provenance maturity, deeper CI) stay `[post-import]`.
> G3/G5 checklist boxes above remain unticked because their stated scope is
> cross-repo and this Engine-only correction does not independently prove it.
> The G1 classification in this dated note is superseded by the current
> maintainer publication gate above.

**Wave 2 — Generated-app strength** (parallelizable with Wave 1)
- [ ] 14. **C1** Generated-app `agent-context.md` emitter (+ opt-in tool stubs) — Med — Engine — 1–2
- [x] 15. **C4** Edge-contract readiness matrix + golden smoke packs — Med — Engine — 1–2 — done ([matrix](edgecontracts/edge-contract-handoff-readiness-matrix.md))
- [ ] 16. **C2** Finish test-console UX track (3b → 5 → 6) — Med — Engine — ~3 (in motion)
- [ ] 17. **C3** Quality-gate residual fixes (B5/B6/B8/PR9/PR10) — Med — Engine — 2–5

**Wave 3 — Compliance hardening + polish**
- [ ] 18. Data-governance / PII posture (+ Evidence-Trail-as-audit) — Med — Engine+Studio+KS — 1–2
- [ ] 19. **D1** Studio UX (layout-upload popup + xlsx/csv templates) — Med — Studio — 2–3
- [ ] 20. **D2** SSO/auth architecture (design now, wire later) — Med — Studio+KS — 1–2
- [ ] 21. **E1** Docs consolidation + archive sweep + prune worktrees — Low — all 5 — 1–5
- [ ] 22. **E2** Decisions record (`docs/decisions/`) — Low‑Med — Engine — 1

**Publication and adopter gates — distinct owners**
- [ ] **G1** Publication authorization — the maintainer verifies applicable rights
      and permissions before public exposure. Adopters separately assess their use.
- [ ] **G6** shared-specs consumption model — adopters choose their mode; project
      support follows ordinary contribution and review, without an implementation commitment
- [ ] Deploy/operate the P1-5-required authenticated gateway (generated-app auth **default** is
      Engine-decided — Option A, gateway-delegated, not an adopter choice) · scanners in-house vs
      offline — the adopting organization decides

**Deferred — post-import / org-side**
- Full threat model · supply-chain provenance maturity (signed tags, attestation, branch
  protection, enterprise scanners) · deeper CI maturity (mypy/coverage/CodeQL) · release/
  version-matrix maturity · support/ownership *finalization* (recommended split shipped now).

**PR-count estimate:** Engine-focused core (1–17) ≈ **22–28 PRs**; with cross-repo
replication (B2/G2/G3/G4/G5/E1 across the other imported repos — Studio + KS/KA always, TestBench/shared-specs only if imported) + Studio (D1/D2) ≈ **40–55 PRs**
suite-wide. Biggest swing: batching (one combined governance PR vs one per repo) and how
much cross-repo work happens now vs in-house.
