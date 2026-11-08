# EdgeForge Suite Website: Origin, Messaging, and Maintenance Guide

## Purpose of this guide

This document preserves the intent, content architecture, claim boundaries,
and maintenance process for the EdgeForge Suite adopter website:

- [`EdgeForge_Suite_Website.html`](EdgeForge_Suite_Website.html)

The website is a communication artifact, not a product source of truth. It
must remain aligned with the suite's implementation, acceptance evidence, and
living architecture documents. Future website work should update the site from
those sources rather than treating existing website copy as proof that a
capability exists.

This guide exists so that a future maintainer can extend the website without
losing its core message, flattening the Business and Technical views into one
dense page, or accidentally upgrading bounded or roadmap capabilities into
shipped claims.

## Current artifact record

| Item | Current record |
|---|---|
| Website artifact | `docs/marketing/EdgeForge_Suite_Website.html` |
| Intended use | Private adopter onboarding and suite capability review |
| Evidence baseline named by the site | Suite v4.1.0 documented acceptance run |
| Format | Self-contained, JavaScript-powered standalone HTML with embedded assets |
| Initial checked-in HTML SHA-256 | `e75cde0fab572163a8f43e2b8efe33b952fb0351d93ba172ae3688fb3782ca1e` |
| Default audience view | Business & Product |
| Detailed audience view | Technical |
| Domain lenses | Financial Services, Healthcare / Payer Operations, Insurance |
| Publication status | Private adopter preview; public-site packaging is a separate step |

The version displayed by the website identifies the acceptance evidence behind
its proof claims. Do not bump that version merely because one repository has a
newer tag. Update it only after the website claims have been reconciled to a new
coordinated suite baseline and the relevant acceptance evidence has been run and
published.

## Origin and design history

The website began as a suite-level adopter-onboarding concept, not as an Engine
feature or a general public marketing site. It was produced in an external
visual-design workspace and refined through multiple independent review passes:

1. Establish the suite story from current code and architecture documents.
2. Correct stale or overstated capability language.
3. Make upstream and downstream contract preservation the central
   differentiator.
4. Elevate generated-app independence, developer handoff, regeneration, and
   shared multi-session posture.
5. Separate a plain-language Business & Product view from a detailed Technical
   view.
6. Add domain lenses to demonstrate domain independence using illustrative
   bounded contexts.
7. Reconcile accessibility, responsive behavior, contrast, interaction state,
   and shipped-versus-roadmap wording.
8. Export a self-contained HTML artifact for private review.

The current committed file is the reviewed artifact. The external design source
is not stored in this repository.

### Post-export changes that must not be lost

Four changes were applied to the exported artifact after the last visual-design
export:

1. The outer HTML title was changed from `Bundled Page` to
   `EdgeForge Suite — Contract-Preserving Modernization`.
2. The large Technical contract-direction matrix was replaced with the compact
   `The supported edge, at a glance` coverage summary.
3. Two unused external font-host `preconnect` hints were removed. The required
   font bytes remain embedded in the bundle, so this removes external connection
   attempts without changing the typography.
4. A current-main truth refresh was applied directly to the bundle
   (see "Direct content patch — current-main truth refresh" below).

Before any future re-export replaces the checked-in file, carry all four changes
back into the external design source. Until that synchronization is confirmed,
the checked-in HTML is the visual baseline for those details.

Direct edits to the bundled HTML should be exceptional. Normal maintenance
should be source-first, followed by a fresh export and a reviewed diff. If an
emergency export patch is unavoidable, record it in this section and backport it
to the design source before the next export.

### Direct content patch — current-main truth refresh

This patch was applied directly to the bundled HTML because the external design
source is not available in this repository (see above) and the page carried
claims that were false rather than merely dated. It is an exceptional patch under
the rule above and **must be backported** before the next export.

Claims corrected:

1. **Staging handoffs.** The page said production restart/idempotency "remains
   open" in both the contract-coverage summary and the roadmap list. M5a is
   complete (`docs/enterprise-readiness-roadmap.md`, M5a row). Now described as
   opt-in caller-supplied run identity and resume-only restart. The profile
   distinction is load-bearing and must not be flattened: PostgreSQL is durable
   across process replacement, while H2 generates `jdbc:h2:mem:` and therefore
   proves same-process restart only
   (`docs/generated-app-standards/generated-app-staging-handoff-run-semantics-design.md`,
   sec. 7.4). Unsupported recovery paths still fail closed.

   The claim appears in **four** places, not one: the honesty-tier card, the
   contract-family summary line, the Technical contract-family data string, and
   the animated acceptance-gate list. The last two are JS data strings inside the
   embedded template and were missed on the first pass because they read
   "semantics remain open" while the sweep searched for "remains open". Any future
   M5a wording change must sweep all four. The acceptance-gate entry stays
   historically scoped -- the v4.1.0 run generated and compiled staging handoffs,
   and run semantics shipped after that run.
2. **Generated-app security posture.** Absent entirely. Security posture Slices
   1-4 are merged. Added as one consolidated claim: response security headers
   across all three archetypes, bounded CRUD page size and offset, and Kafka
   actuator health-only by default. The authenticated-TLS-gateway requirement is
   deliberately **not** filed here: it is an adopter obligation rather than
   shipped behavior, and belongs in the boundaries card.
3. **Passthrough request validation — scope-critical.** Generated passthrough
   apps enforce **only** required-field presence and maximum string length
   (`appbuilder/generation/passthrough_helpers.py`,
   `_passthrough_field_validation_annotations`). Pattern, enum, minimum length
   and numeric ranges are deliberately not emitted. The page must never say
   "request validation" unqualified.
4. **Studio posture.** Added as its own bullet: durable audit storage in shared
   mode with anonymous session-level attribution, bounded contract fetch, and
   request/upload and resource controls
   (`EdgeForgeStudio/docs/studio-context.md`, Security Baseline). The durability
   and the attribution scope are separate facts and must stay separate -- audit
   is durable, attribution is still anonymous and session-level. Present-tense
   Studio posture lines and headings elsewhere on the page were updated to match;
   the only remaining "session-level audit events" phrase is the v4.1.0 historical
   evidence sentence, which is retained deliberately. Also added
   the two deployment boundaries that affect enterprise review: shared mode is
   single-replica, and signed anonymous sessions provide isolation, not
   authentication.
5. **Roadmap accuracy.** Studio UX refresh moved off the roadmap (it is now
   Studio's sole presentation). Knowledge Assist review hardening remains on the
   roadmap, gated on the production data-handling decision — this is a distinct
   item from the completed Knowledge Server runtime hardening and must not be
   collapsed into it.
6. **Release tiering — restructured.** An interim revision added a fourth
   category, "IMPLEMENTED ON CURRENT MAIN · v5 CANDIDATE", beside the existing
   three. That was reverted after review: four tiers turned the section into an
   evidence register, which is not what this page is for. The section is now
   three cards on a different axis — `AVAILABLE ON CURRENT MAIN · v5 CANDIDATE`,
   `VERIFIED EVIDENCE`, `BOUNDARIES & NEXT`. Measured against the committed base
   `3476633`, that is **19 bullets / 270 words to 16 bullets / 322 words**. The
   earlier "25 bullets" figure was measured against an uncommitted interim and
   must not be repeated. The section carries roughly 77 words of claims absent
   from base entirely — Studio security baseline, staging profile boundary,
   gateway ownership, sample packs — so pre-existing content is shorter than base
   while total words are higher. Any further compaction has to come out of one of
   those four claims or out of the contract-family naming; it is a content
   decision, not a wording one.
   The known trade-off: evidence strength is no longer bound per claim, so the
   `VERIFIED EVIDENCE` card must always state plainly that current-main additions
   still await the coordinated v5 acceptance run. The `v4.1.0` acceptance badges
   are deliberately unchanged: they identify a specific acceptance run, and the
   rule at the top of this guide prohibits bumping them before a coordinated
   baseline and evidence run.
7. **Smaller corrections.** Exported artifact renamed `manifest.yaml` ->
   `app-definition.yaml`; REST direction qualified (CRUD inbound, passthrough
   invokes declared downstream operations); TestBench removed from the
   runtime-independence list; the exception-handling boundary narrowed to
   domain-specific behavior beyond the generated baseline.

No card, grid, palette or type styles were changed. The section keeps its
original `minmax(320px,1fr)` track, its three accent colors, and the same card
pattern; only the card contents changed. Note that the container caps at 1200px,
so this grid resolves to three 388px columns at every desktop width — it cannot
lay out four cards on one row, which is one reason the interim fourth card was
reverted. A separate visual pass is sequenced after this content freeze.

Sample packs: the three Studio packs are acceptance-backed as of Engine PR #308
(`docs/test-results/domain-sample-packs-2026-09-04.md`, A1-A16 PASS at pinned
Engine `8b1fa80` / Studio `d23d99f`, including the manual A9 browser open). The
page must keep that proof's own boundary visible — generated-app runtime E2E is
outside it — and must not quote the A-number contract or pinned SHAs, which are
proof mechanics that belong in this repository, not on the page.

## What the website is for

The website should help an adopting organization answer four questions:

1. What modernization problem does EdgeForge solve?
2. What does EdgeForge generate, preserve, and deliberately leave to engineers?
3. Is the suite's authoring, generation, and handoff posture suitable for
   enterprise review?
4. Which claims are shipped and acceptance-backed, and which remain bounded,
   adopter-wired, or roadmap?

The website is not:

- a replacement for the handover-evidence pack;
- a legal opinion, security certification, or production certification;
- a promise that EdgeForge discovers undocumented business logic;
- a claim that every contract family works in every direction;
- a claim that generated applications contain completed domain behavior;
- a substitute for current README files, roadmaps, or release notes.

## Core message

The durable story is:

> Modernize the application at the center while preserving the reviewed
> obligations at its edges.

The supporting message is:

- Upstream is what enters or calls the application.
- Downstream is what the application produces, invokes, or must continue
  honoring.
- Both sides become explicit, reviewed inputs.
- Studio authors and reviews the manifest package.
- EdgeForge Engine generates deterministically or fails fast.
- The generated Spring Boot application is standalone and adopter-owned.
- Engineers implement product-specific workflows, policies, authorization,
  domain-specific exception behavior beyond the generated baseline validation
  and error responses, and unsupported integration behavior.
- CRUD applications can be regenerated while preserving developer-owned service
  logic and failing closed on destructive or drifted database changes.
- Evidence and acceptance artifacts support claims; they do not remove the need
  for adopter review and release controls.

This message should remain recognizable even if the visual design changes.

## Audience model

The site deliberately uses two views. Legal, security, compliance, and data
governance are horizontal concerns that must remain discoverable in both views;
they are not a third mode.

### Business & Product view

Business & Product is the default view. It is for sponsors, product and domain
owners, architecture leaders, adoption teams, and reviewers who first need to
understand the problem and organizational fit.

Its job is to explain:

- why API-only modernization can leave the surrounding ecosystem broken;
- where EdgeForge fits and where it does not;
- how reviewed obligations become a runnable engineering starting point;
- what the adopting engineering team receives and owns;
- why standalone output reduces runtime lock-in;
- how a bounded legacy application can be replaced while surrounding systems
  remain connected through preserved obligations;
- what is shipped today versus roadmap or in-organization wiring;
- the high-level governance, data, identity, and evidence posture.

Business copy should minimize internal names, schema paths, method names, and
framework detail. It must still carry material qualifiers. Simplicity must not
erase the CRUD-only regeneration boundary, bounded SOAP scope, anonymous-session
identity posture, human-review boundary, or roadmap status of SSO/RBAC.

### Technical view

Technical view is for architects, engineers, platform teams, and technical
reviewers evaluating whether the suite fits an actual contract ecosystem.

Its job is to make the following inspectable:

- supported contract families and exact directions;
- the reviewed canonical model and manifest package;
- CRUD, Kafka integration, and passthrough-router application shapes;
- Studio authoring and optional Knowledge Assist behavior;
- deterministic Engine generation and fail-fast validation;
- generated repository anatomy and developer extension seams;
- what engineers still implement;
- CRUD regeneration and additive database evolution;
- shared multi-session deployment and identity boundaries;
- validation evidence, limitations, and technical fit questions.

Technical detail must remain concise enough to scan. Prefer one accurate
coverage summary plus deeper examples over repeating the same family descriptions
in several tables and cards.

### View behavior

The following interaction contract should be preserved:

- Business & Product is the default view.
- Switching views takes the reader to the selected view's hero.
- The selected domain remains unchanged when switching views.
- The mobile menu closes after a view change or navigation choice.
- Direct URLs may select `view=business` or `view=technical`.
- Direct URLs may select `domain=financial`, `domain=healthcare`, or
  `domain=insurance`.
- Explicit section hashes should still work on initial load.
- Mode changes and selected controls must be announced accessibly.
- Reduced-motion preferences must disable nonessential movement.

## Domain-lens model

The domain lenses demonstrate that the generation model is driven by contract
families, not by one industry's semantics. They are illustrative and must never
become implied native protocol support.

### Business domain lens

Business view uses an ecosystem model:

`upstream applications -> bounded legacy application -> downstream applications`

The center then changes to an EdgeForge-generated standalone application while
the surrounding obligations remain visible. This communicates replacement of a
bounded application or service slice, not automatic replacement of an entire
enterprise core.

Each domain should keep at least three plausible upstream roles and three
plausible downstream roles, using generic system-role names rather than real
products or customers.

| Domain | Center example | Example surrounding roles |
|---|---|---|
| Financial Services | Account-servicing application | Customer-servicing portal, operations platform, partner feed, reconciliation platform, data platform, notification consumers |
| Healthcare / Payer Operations | Authorization-status application | Provider portal, care-management platform, partner feed, claims/operations platform, reporting platform, notification consumers |
| Insurance | Claims-servicing application | Broker/agent portal, claims-intake platform, partner file, policy/claims platform, reporting platform, notification consumers |

### Technical domain lens

Technical view keeps the detailed contract-oriented model:

`reviewed upstream contracts -> generated standalone app -> reviewed downstream obligations`

The vocabulary changes by domain, but the supported family set and directional
boundaries do not.

### Domain-example guardrails

Domain examples must:

- use synthetic names and data;
- use only implemented generic contract families and shipped archetypes;
- keep the generated application at bounded-context scale;
- include the visible statement that mappings are illustrative;
- leave governance, identity, evidence, and shipped-versus-roadmap claims
  unchanged across domains.

Domain examples must not imply native support for unimplemented industry
semantics or protocols, including FHIR, HL7 v2, X12/EDI, ACORD semantics, or
full core-platform replacement.

## Current claim boundaries

The table below records the website's current truth discipline. Implementation
and evidence sources remain authoritative.

| Topic | Safe current claim | Boundary that must remain visible |
|---|---|---|
| REST / OpenAPI | Reviewed inbound REST contracts generate controllers | No generated outbound REST client is implied |
| Fixed-width | Reviewed layouts support inbound parsing and downstream writing | Broader file controls such as checksums and partial acceptance remain future work |
| CSV / delimited | Reviewed layouts support inbound reading and downstream writing | Preserve the declared delimiter; do not imply arbitrary spreadsheet semantics |
| XML / XSD | Explicit mappings support inbound parsing and downstream serialization | Do not imply every advanced XSD construct is supported |
| SOAP / WSDL | Supported document/literal-wrapped contracts generate inbound endpoints and outbound clients | Turnkey canonical runtime is bounded to inbound lookup by ID and outbound call by ID; broader operations and advanced WS-* policies remain future work |
| Staging / table handoffs | Downstream handoffs are modeled separately and generated | Production restart, run identity, and idempotency hardening remain open |
| Kafka integration | A shipped generated-application archetype | It is not an additional direction for every contract family |
| Passthrough router | A shipped synchronous mediation archetype | It does not imply arbitrary protocol or orchestration support |
| Determinism | Greenfield generation is deterministic for the reviewed package and Engine version | Regeneration also depends on committed baseline/package state and preserved developer-owned files |
| Regeneration | CRUD generated base code refreshes, developer-owned services are preserved, additive Flyway changes are supported, destructive/drifted changes fail closed | Do not generalize identical maintain-over-time behavior to Kafka or passthrough outputs |
| Generated app independence | Generated applications build and run without EdgeForge suite runtime dependencies | Adopter-specific domain logic and production hardening remain engineering work |
| Generated context | CRUD and passthrough outputs include deterministic `agent-context.md`; all archetypes include README guidance | Kafka currently relies on archetype-specific README guidance; tool-specific stubs are opt-in |
| Developer hooks | CRUD generated service bases expose `beforeCreate`, `afterCreate`, `beforeUpdate`, `afterUpdate`, `beforeDelete`, and `afterGeneratedBusinessRules` | These are extension seams, not inferred business behavior |
| Health endpoint | Generated application packaging uses `/actuator/health` | Separate liveness/readiness probe standards remain follow-up work |
| Knowledge Assist | Optional, off-by-default local evidence retrieval with cited suggestions and explicit human review | It is not an LLM integration and does not write decisions automatically |
| Shared authoring | Studio supports shared multi-session isolation, CSRF protection, session-level audit events, and server-owned paths | Identity today is signed anonymous browser sessions; OIDC/proxy SSO, RBAC, and named-user audit attribution remain adopter wiring or roadmap |
| Acceptance evidence | The documented v4.1.0 suite acceptance run covers named scenarios | It is not production certification or continuous assurance |
| Test utility | An optional local utility can exercise generated apps | Do not position it as a required runtime suite component |

## Claims the website must not make

Do not state or imply that:

- SSO, RBAC, or named-user audit attribution ships today;
- shared multi-session means full authenticated multi-user tenancy;
- every SOAP operation or WS-* policy is supported;
- every contract family is bidirectional;
- EdgeForge infers undocumented business logic;
- generated applications contain finished product behavior;
- coding assistants can modify generated applications autonomously or safely;
- EdgeForge connects to an external LLM provider;
- illustrative domains add native industry semantics;
- the documented acceptance run is production certification;
- CRUD regeneration guarantees apply unchanged to all archetypes;
- generated applications require Studio, Engine, Knowledge Assist, MCP, or the
  test utility at runtime.

## Authoritative sources for future updates

### Engine and suite sources in this repository

- [Suite architecture](../suite-architecture.md)
- [Edge-contract handoff-readiness matrix](../edgecontracts/edge-contract-handoff-readiness-matrix.md)
- [Edge-contract expansion roadmap](../edge-contract-expansion-roadmap.md)
- [Regenerate/maintain model design](../regenerate-maintain-model-design.md)
- [Regenerate/maintain suite design](../regenerate-maintain-suite-design.md)
- [Suite smoke-harness design](../suite-smoke-harness-design.md)
- [L5 acceptance-run evidence](../handover-evidence/l5-acceptance-run.md)
- [Data-governance posture](../data-governance-posture.md)
- [Compliance and portability](../compliance-and-portability.md)
- [Security boundary map](../security-boundary-map.md)
- [Generated-app quality gate](../generated-app-standards/generated-app-quality-gate-v1.md)
- [`CHANGELOG.md`](../../CHANGELOG.md)

### Cross-repository sources

Read the corresponding current documents in the sibling repositories before
changing Studio or Knowledge Assist claims:

- Studio: `docs/multi-session-architecture-design.md`
- Studio: `docs/deployment-model.md`
- Studio: `docs/security-boundary-map.md`
- Studio: `docs/handover-evidence/README.md`
- Knowledge Server: `README.md`
- Knowledge Server: `docs/security-boundary-map.md`
- Knowledge Server: `docs/handover-evidence/README.md`

Do not infer cross-repository status from an Engine-only roadmap entry.

## Website update workflow

### 1. Define the update

Classify the proposed change as one of:

- wording or visual polish with no claim change;
- a changed shipped capability;
- a newly acceptance-proven capability;
- a changed limitation or roadmap boundary;
- a new coordinated suite baseline;
- a hosting or packaging change.

### 2. Establish current truth

For every changed claim, record:

- repository and implementation location;
- test or acceptance evidence;
- whether it is shipped, bounded/partial, adopter-decided, or roadmap;
- which archetypes and directions it applies to;
- any cross-repository dependency.

Never promote a design document alone into a shipped website claim.

### 3. Update the external design source first

Preserve:

- the two-view audience model;
- the upstream/downstream core story;
- generated-app independence;
- the domain-lens invariants;
- the governance content in both views;
- the visible shipped-versus-roadmap split;
- current URL parameters and anchor IDs where practical.

Set the page title in the design source as well as the exported artifact. Ensure
the compact Technical contract-coverage summary is also present in the source
before replacing the checked-in export.

### 4. Export into a temporary location

Do not overwrite the checked-in artifact first. Compare the new export with the
current HTML and identify:

- copy changes;
- capability/status changes;
- removed qualifiers;
- interaction changes;
- unexpected asset or network dependencies;
- reintroduced post-export defects.

### 5. Validate the exported website

At minimum, verify:

- Business & Product and Technical views;
- all three domain lenses in both views;
- direct query-parameter loading;
- view switching returns to the correct hero and preserves the domain;
- mobile menu closure after mode or navigation selection;
- every header and in-page anchor;
- keyboard operation and visible focus for all controls;
- semantic tabs, radios, buttons, and the Knowledge Assist switch;
- desktop, tablet, and narrow mobile layouts;
- no global horizontal overflow;
- readable contrast for text, badges, code, and status chips;
- `prefers-reduced-motion` behavior;
- no browser-console errors;
- no external runtime/CDN dependency unless deliberately approved;
- no absolute local paths, secrets, real data, customer names, or product names;
- outer and rendered page titles;
- domain disclaimers and synthetic-data labels;
- the documented baseline version and evidence pointer.

### 6. Re-verify high-risk claims

Always re-check these claims against code and evidence:

- generated-app runtime independence;
- `agent-context.md` archetype coverage;
- generated hook names;
- health and packaging claims;
- SOAP directions and operation bounds;
- regeneration archetype scope;
- Studio identity and audit posture;
- Knowledge Assist and external-LLM wording;
- acceptance-run version and scope.

### 7. Commit through a focused PR

The PR should state:

- the prior and new website baseline;
- whether the external design source was updated;
- changed claims and their evidence;
- visual/interaction changes;
- verification performed;
- any deliberate post-export patch;
- whether hosting behavior changed.

Avoid combining website refreshes with Engine runtime changes.

## Hosting and publication boundary

The checked-in HTML is suitable as a self-contained private-preview artifact,
but repository check-in does not itself create a secure private website.

Private hosting must provide access control outside the HTML, such as an
approved identity-aware proxy or authenticated hosting layer. A private URL or
unlisted path is not access control.

Before hosting, decide and document:

- who may access the site;
- authentication and authorization method;
- hosting owner and support contact;
- custom-domain and TLS ownership;
- logging and retention posture;
- whether analytics or telemetry are prohibited or approved;
- deployment and rollback process;
- content-update approval process.

Before any future public launch, convert or rebuild the current bundled export
as maintainable site source and add normal public-site concerns such as metadata,
social previews, canonical URLs, accessibility/indexing fallback, content
security policy, and security headers. Public launch is a separate decision from
merging this documentation artifact.

## Ownership and durability rules

**Current launch decision (2026-10-25):** [approved scope-reset revision 3](../v5-release-readiness.md)
selects edgeforgesuite.com, redirects from www and the other two registered
domains, a fresh private `edgeforge-suite/website` repository and protected
Cloudflare previews. Maintainer publication authorization remains pending before any public
exposure; production follows acceptance and explicit authorization. Reporting
email/PVR, hosting logs/retention/TLS and rollback still require verification.
This supersedes unselected hosting/provider/domain wording above, not the
historical origin evidence or outstanding website corrections.

- The suite implementation and evidence remain authoritative; this guide owns
  only website intent and maintenance discipline.
- The website should communicate current truth, not mirror every tracker row.
- Avoid PR-number histories and volatile implementation detail in primary copy.
- Keep technical specifics only when they help an evaluator understand support
  or a material boundary.
- Keep legal, compliance, identity, AI, and data qualifiers visible in both
  audience views.
- Preserve the standalone-generated-app invariant.
- Preserve domain neutrality and synthetic examples.
- Keep non-public correspondence, private planning material and obsolete
  presentation exports outside the repository.
- Keep website changes PR-only; never update the checked-in artifact directly on
  the default branch.

## Freeze checklist

The website is ready for a new frozen baseline only when all answers are yes:

- [ ] Every changed capability claim has current code or acceptance evidence.
- [ ] Shipped, bounded, adopter-wired, and roadmap statements remain distinct.
- [ ] Business copy is understandable without hiding material limits.
- [ ] Technical copy states directions and archetype scope precisely.
- [ ] Domain examples change vocabulary, not capability claims.
- [ ] Business and Technical views remain purposeful and non-duplicative.
- [ ] Governance and evidence remain reachable from both views.
- [ ] The design source includes all post-export fixes.
- [ ] The exported title and rendered title are correct.
- [ ] Responsive, keyboard, contrast, reduced-motion, and anchor checks pass.
- [ ] No secrets, real data, local paths, or external runtime dependencies were
      introduced.
- [ ] The checked-in artifact matches the reviewed export byte-for-byte.
- [ ] Hosting or publication status is stated honestly.
