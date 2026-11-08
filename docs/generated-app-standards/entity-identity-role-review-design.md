# Entity Identity Role Review — Studio / Knowledge Assist Design

> **Status:** Design draft — post-v3.0.0 generated-app standards track.
>
> **Owner:** EdgeForge Suite / Studio / Knowledge Assist design.
>
> **Date:** May 2026.
>
> **Related docs:**
> - [A1 Identity Semantics Design](../a1-identity-semantics-design.md)
> - [C9 ID Generation Strategy Design](../c9-id-generation-strategy-design.md)
> - [Generated App Quality Gate v1](generated-app-quality-gate-v1.md)
> - [Generated App Engine Roadmap](generated-app-engine-roadmap.md)
> - [Studio UX v3 Assistive Features](../studio-ux-v3-assistive-features-design.md)
> - [Studio UX v3 Suggestion Drawer Pattern](../studio-ux-v3-suggestion-drawer-pattern.md)
> - [Knowledge Server Broader Suggestion Scopes](../ks-broader-suggestion-scopes-design.md)
> - [Evidence Trail Design](../evidence-trail-design.md)
> - [Project Workspace / Decision Ledger](../project-workspace-decision-ledger-design.md)
> - [CRUD Cross-Entity Rules](../crud-cross-entity-rules-design.md)
> - [Manifest Schema](../manifest-schema.md)

---

## 1. Purpose

Engine PR #138 made generated-app identity selection safer by failing fast when
an event/transaction-like entity would infer a parent-reference field as its
persistence primary key. That fix prevents incorrect generated output, but it
does not help authors choose the right identity intent before generation fails.

This document closes that gap. It defines how Studio and Knowledge Assist
should make identity intent visible, reviewable, and exportable so that:

- authors can review and approve which field is the persistence row identity
- parent/FK references are visually separated from persistence identity
- business keys, event IDs, idempotency keys, and correlation IDs are
  classified rather than left ambiguous
- the reviewed persistence identity decision exports to the Engine through the
  existing `identity_overrides` manifest contract
- generated apps remain standalone and runtime-independent of Studio, Knowledge
  Assist, Knowledge Server, or any MCP dependency

The target audience is any enterprise modernization project where entities have
multiple identifier-shaped fields. Transaction/event entities are the
most common trigger, but the design applies equally to e-commerce order events,
logistics shipment records, insurance claim entries, and any domain where parent
references, business keys, and persistence row identity are distinct concepts.

---

## 2. Problem

Event, transaction, history, and log-style entities routinely contain several
fields that look like identifiers but mean different things:

- a parent reference such as `accountId` or `customerId`
- a business/event identifier such as `transactionId` or `orderId`
- a persistence row identity such as `postingId` or a surrogate `id`
- an idempotency guard such as `idempotencyKey` or `requestId`
- a correlation/trace identifier such as `correlationId`
- an external/provider reference such as `providerReference`

When the Engine must select one field as the JPA `@Id` without explicit
guidance, the heuristic may choose the wrong one. The consequences are severe:

- selecting a parent reference as `@Id` collapses multiple event rows for the
  same parent into one physical row
- selecting a business/event ID as `@Id` may be correct, but also may not be
  desirable if idempotency or duplicate detection is the intended semantic
- response-wrapper fields such as `transactions`, `currentPage`, `pageSize`,
  `totalElements`, and `totalPages` are transport envelope metadata, not domain
  state, and must not become persistence columns

Engine PR #138 addresses safety by failing fast when the inferred identity looks
like a parent reference on an event/transaction-like entity. It also strips
response-wrapper fields from persistence and downstream mappings. But:

- the author receives a generation error instead of a guided review surface
- there is no Studio UI to classify identity roles before generation
- there is no Knowledge Assist evidence path to suggest identity roles
- non-event entities with ambiguous identity intent are not covered by the
  fail-fast heuristic

This design gives Studio and Knowledge Assist the tools to resolve identity
intent before the Engine has to fail.

---

## 3. Non-Goals

This document does not:

- implement Engine behavior changes — Engine PR #138 is the current safety net
  and remains unchanged by this design
- implement Studio UI — this is the design that gates later Studio
  implementation
- implement Knowledge Server tools or suggestion types — this defines the
  contract that gates later KS implementation
- add automatic surrogate ID generation — the Engine does not create new fields;
  if no existing field is suitable, the author must add one to the manifest
- introduce generated-app runtime dependency on Studio, Knowledge Assist,
  Knowledge Server, or MCP — generated apps remain owned by the adopting organization at runtime
- implement LegacyExtractor evidence — LE is Phase 6 design-first and feeds
  into this design through future KS-B6
- implement high-TPS accumulator design — that is a separate design doc
  (`high-tps-entity-profile-design-v1.md`)
- implement C9 ID generation strategy — C9 defines how identity values are
  produced; this design defines which field is the identity and why
- define composite key support — composite keys are a future design extension

---

## 4. Current Baseline and PR #138 Interaction

### What PR #138 does

Engine PR #138 added conservative safety guards to `translation.py`:

- **Explicit `identity_overrides` still wins.** When a manifest declares
  `identity_overrides` for an entity, the declared `persistence_id` is used
  with no heuristic involved.
- **Event/transaction entity detection.** Entities whose names or operations
  contain terms such as `transaction`, `posting`, `event`, `history`, `ledger`,
  `activity`, or `movement` are classified as event/transaction-like.
- **Parent-reference field detection.** Fields ending in `Id` whose stem
  matches a parent entity term (e.g., `accountId`, `customerId`, `loanId`) or
  that appear as path parameters on GET/list operations are classified as
  parent-reference-like.
- **Fail-fast on risky inference.** If the inferred persistence ID for an
  event/transaction-like entity looks like a parent reference, translation
  raises a `ValueError` with a clear message and suggested `identity_overrides`
  syntax.
- **Response-wrapper field exclusion.** Fields matching transport envelope names
  (`transactions`, `currentPage`, `pageSize`, `totalElements`, `totalPages`,
  `totalItems`, `links`, `meta`) that originate from response mappings are
  stripped from entity persistence and downstream handoff mappings.

### What PR #138 does not do

- It does not provide a Studio review surface for identity decisions.
- It does not auto-generate surrogate row IDs.
- It does not classify business keys, idempotency keys, or correlation IDs.
- It does not cover non-event entities with ambiguous identity.
- It does not suggest which field should be the persistence ID — it only rejects
  unsafe inferences.

### Interaction model

Studio export should satisfy Engine by emitting reviewed `identity_overrides`
for entities where the author has made an explicit persistence identity
decision. When Studio exports a manifest with correct `identity_overrides`, the
Engine PR #138 fail-fast path is not triggered because explicit overrides bypass
the heuristic entirely.

The Engine remains the deterministic safety net. Even if Studio does not export
identity overrides for a given entity, the Engine heuristic and fail-fast guard
continue to operate. Studio review reduces the frequency of fail-fast errors but
does not replace the guard.

---

## 5. Vocabulary

### Identity Role Vocabulary

These are the approved identity-role terms for use in Studio, Knowledge Assist,
documentation, and future manifest metadata. They are listed in order of
generation impact.

| Role | Meaning | Current Engine generation consequence |
|---|---|---|
| `persistence_id` | The field that becomes the generated app's JPA `@Id`, repository `findById` identity, and route path parameter for single-resource operations. | Drives `CanonicalField.is_id`, `@Id`, route ID, `findById`. Maps to `identity_overrides` on export. |
| `parent_reference` | A field that references another entity's identity, such as `accountId` on a transaction entity. It is a foreign key or relationship reference, not this entity's row identity. | Currently handled through `cross-entity-exists` rules. Must not become `@Id` for event/transaction entities (PR #138 fail-fast). |
| `business_key` | A domain-meaningful natural key, such as `accountNumber`, `invoiceNumber`, or `orderReference`. It identifies a business concept and may need uniqueness enforcement but is not automatically the persistence row identity. | No current generation consequence. Future candidate for unique constraint or lookup index. |
| `event_id` | An upstream event or transaction identifier, such as `transactionId` or `eventId`. It identifies the business event and may need idempotency or duplicate detection but is not automatically the JPA `@Id`. | Regular field. Should not become `@Id` solely by naming unless explicitly approved. |
| `idempotency_key` | A replay/duplicate protection key. It ensures that retried operations do not create duplicate state. | Regular field. Future candidate for unique constraint or idempotency service logic. |
| `correlation_id` | A request-level, workflow-level, or cross-system tracing identifier, such as `correlationId` or `traceId`. | Regular field. Useful for logging and debugging but not persistence identity. |
| `external_reference` | An identifier assigned by an external provider or integration partner, such as `providerReference` or `gatewayTransactionId`. | Regular field. May overlap with business key in specific domains. |

### Entity Kind Vocabulary

Entity kind is a design-level taxonomy that helps Studio and Knowledge Assist
reason about which identity roles are likely and which generation patterns
apply. It is advisory unless later implemented as a manifest field.

| Kind | Meaning | Typical identity pattern |
|---|---|---|
| `master` | System-of-record entity that is created, read, updated, and may be soft-deleted. Examples: Customer, Account, Product. | Usually has a natural or surrogate persistence ID. Business keys are common. |
| `reference` | Stable reference/code-table entity that rarely mutates. Examples: Currency, Country, BranchCode. | Usually has a short code or natural key as persistence ID. |
| `event` | Append-only or append-mostly entity representing a business event. Examples: TransactionPosting, PaymentEvent. | Needs a dedicated row identity separate from parent reference. Business event ID is common. |
| `transaction` | Financial or business transaction entity, similar to `event` but with domain-specific accounting semantics. Examples: Transaction, LedgerEntry. | Same as event. Parent account/customer reference is always a FK, never a PK. |
| `log` | Audit, activity, or history trail entity. Examples: AuditLog, LoginHistory. | Needs a surrogate or sequence-based row identity. Often append-only. |
| `read_model` | A derived or computed view entity. Examples: AccountBalance, DailySummary. | May use a composite or natural key. Often read-only in the generated app. |

Identity role and entity kind are related but separate concerns:

- entity kind describes what the entity represents in the domain
- identity role describes what a specific field means for that entity
- knowing the entity kind narrows which identity roles are expected, but does
  not determine them

Entity kind is not a current manifest field. It is a design taxonomy used by
Studio and Knowledge Assist to guide suggestions and review. If later
implementation requires a manifest representation, it should be introduced as an
additive optional field with a separate design review.

---

## 6. Studio UX v3 Placement

### Alignment with Studio UX v3

This design aligns with the implemented Studio UX v3 baseline:

- Knowledge Assist is OFF by default. The identity role review surface must
  work fully with KA OFF through manual authoring.
- Step 3 (entity + field modeling) is the primary home for identity role review.
  Step 3 already hosts compact triage and full-width Knowledge Assist Review
  for field suggestions.
- Step 6 (rules) consumes reviewed identity roles for rule suggestions. It is
  not the primary identity authoring surface.
- Step 7 (Decision History) records accepted, edited, and rejected identity
  decisions alongside other review decisions.
- Compact badges and drawers are the only wizard-step entry points for
  suggestion review. No always-visible panels are introduced.

### Recommended Step 3 placement

Identity role review lives inside Step 3's entity/field modeling surface:

1. **Field table identity role column.** The existing field table for each
   entity gains an identity role indicator. Each field that has been classified
   shows a compact chip: `🔑 persistence_id`, `🔗 parent_reference`,
   `🏷️ business_key`, `📌 event_id`, `🔒 idempotency_key`, or similar
   compact labels. Unclassified fields show no chip.

2. **Identity review section.** Below or alongside the field table, a compact
   identity review section groups the reviewed decisions for the current entity:
   - **Selected persistence identity** — the field that will become `@Id`
   - **Parent references** — fields classified as FK/relationship references
   - **Business / idempotency keys** — fields that may need uniqueness or
     duplicate protection
   - **Event / correlation / external references** — remaining classified
     identifiers

3. **KA ON: identity suggestion badge.** When Knowledge Assist is enabled and
   KS returns identity-role suggestions for the current entity, a compact
   badge such as `💡 N identity suggestions` appears in the Step 3 entity
   section. Clicking opens a drawer showing KA-suggested identity roles with
   evidence links. The author accepts, edits, or rejects each suggestion.

4. **KA OFF: manual identity classification.** When Knowledge Assist is off,
   the author can manually assign identity roles through the field table or
   identity review section. No KA badges, drawers, or evidence links appear.

### Step 6 consumption

Step 6 can use reviewed identity roles to improve rule suggestions:

- a field classified as `parent_reference` is a candidate for
  `cross-entity-exists`, `cross-entity-field-check`, or
  `cross-entity-field-compare` rules
- a field classified as `business_key` is a candidate for uniqueness or
  duplicate detection rules
- a field classified as `idempotency_key` is a candidate for replay protection
  rules
- a field classified as `persistence_id` is usually not a business rule
  candidate — it is infrastructure

Step 6 surfaces these candidates through its existing KA rule suggestion
mechanism. It does not re-author identity classifications.

### Step 7 recording

Step 7 records identity role decisions in the Decision History alongside other
reviewed decisions. Each accepted or edited identity classification appears
with:

- the entity and field name
- the assigned role
- the provenance (human-authored, suggestion-accepted, or suggestion-edited)
- the evidence summary if KA was used

Rejected identity suggestions also appear in the decision history so that
reviewers can see what was considered and dismissed.

---

## 7. Human Review Model

### Core flow

1. Studio loads the entity model from ingested upstream contracts.
2. If Knowledge Assist is enabled, KS provides identity-role suggestions with
   evidence citations.
3. Studio displays suggestions as pending draft decisions in the Step 3
   identity review section.
4. The author reviews each suggestion and accepts, edits, or rejects it.
5. Accepted or edited `persistence_id` decisions map to `identity_overrides`
   in the exported manifest.
6. Rejected suggestions do not affect the manifest.
7. If the author skips identity review entirely, the Engine heuristic and
   PR #138 fail-fast guard remain the safety net.

### Decision types

| Action | Meaning | Manifest effect |
|---|---|---|
| Accept | Author approves the suggested identity role as-is. | `persistence_id` acceptance maps to `identity_overrides`. Other roles export as `identity_roles` entries with `mode: metadata_only` (after Studio PR #155). Engine generates zero artifacts in `metadata_only` mode. |
| Edit | Author changes the suggested role (e.g., changes `event_id` to `persistence_id`). | Edited decision maps to the manifest according to the final role chosen. |
| Reject | Author dismisses the suggestion. | No manifest effect. Recorded in review history for audit. |
| Manual entry | Author assigns an identity role without KA suggestion. | Same manifest mapping as accepted suggestion. Provenance is `human-authored`. |

### KA OFF behavior

When Knowledge Assist is off:

- No KA badges, drawers, or evidence links appear anywhere in Step 3.
- The identity review section still appears, allowing manual identity
  classification.
- Manual classification is fully functional without KA.
- The author can assign `persistence_id` to any existing eligible entity
  field, which exports as `identity_overrides`.

### Suggestion card design

KA identity suggestions should follow the established suggestion card pattern:

- **Title:** short label, e.g., "accountId is a parent reference"
- **Confidence indicator:** deterministic confidence score
- **Evidence summary:** one or two citation references
- **Why suggested:** compact rationale, e.g., "accountId appears as a path
  parameter in GET /accounts/{accountId}/transactions"
- **Action buttons:** Accept / Edit / Reject

Cards should be decision-first. The evidence is available on demand through
the existing evidence chain mechanism but is not pre-expanded in the
suggestion list.

### Visual taxonomy alignment

Identity role suggestions use the existing KA visual taxonomy:

| Category | When used |
|---|---|
| Applies generated change | `persistence_id` accepted — affects `identity_overrides` export |
| Already satisfied | Field already has a matching explicit `identity_overrides` entry |
| Exported as metadata | `parent_reference`, `business_key`, `event_id`, etc. — exported as `identity_roles` entry with `mode: metadata_only` (after Studio PR #155); Engine generates no artifacts |
| Evidence-backed | Suggestion has one or more KS citations |
| Review needed | Conflicting evidence or low confidence |

---

## 8. Knowledge Assist / KS Evidence Model

### Deterministic evidence sources

Knowledge Server uses deterministic retrieval to suggest identity roles. The
following evidence sources are ranked from strongest to weakest:

| Rank | Evidence source | Signal type | Example |
|---|---|---|---|
| 1 | Explicit manifest/project decision | Human decision | Author previously classified `postingId` as `persistence_id` |
| 2 | DDL primary key constraint | Structural | `PRIMARY KEY (posting_id)` in DDL |
| 3 | DDL foreign key constraint | Structural | `FOREIGN KEY (account_id) REFERENCES account(account_id)` |
| 4 | DDL unique constraint | Structural | `UNIQUE (transaction_id)` — suggests business key or idempotency key |
| 5 | OpenAPI path parameters | Structural | `/accounts/{accountId}/transactions` — `accountId` is parent reference |
| 6 | OpenAPI request/response body structure | Structural | Create request includes `transactionId` but not `accountId` in body — suggests `transactionId` is caller-supplied event ID |
| 7 | Field catalog definitions | Documentary | Field catalog describes `accountId` as "Foreign key to the owning account" |
| 8 | BRD / business policy text | Documentary | BRD states "Each transaction must have a unique transaction reference number" |
| 9 | Naming conventions | Heuristic | Field ends in `Id` and stem matches a known parent entity name |
| 10 | Existing cross-entity rules | Contextual | A `cross-entity-exists` rule on `accountId` targeting `Account` confirms FK intent |
| 11 | Sample payloads | Contextual | Sample data shows multiple transaction rows with the same `accountId` value |
| 12 | LegacyExtractor evidence | Future | LE-extracted DDL, stored procedure analysis, or legacy mapping artifacts |

### Evidence ranking principles

- **Explicit decisions always win.** A prior human decision recorded in the
  project is not overridden by KA evidence.
- **Structural evidence outranks documentary evidence.** DDL constraints and
  OpenAPI path structure are more reliable than BRD text or field catalog
  descriptions.
- **Documentary evidence outranks naming heuristics.** BRD statements about
  field purpose are more reliable than field-name pattern matching.
- **Conflicting evidence triggers review-needed.** When evidence sources
  disagree (e.g., DDL says PK but OpenAPI path says parent reference), the
  suggestion is flagged as `review-needed` with both evidence sources cited.

### Key evidence patterns

| Pattern | Suggested role | Confidence basis |
|---|---|---|
| Path parameter `/parents/{parentId}/children` — `parentId` used in child entity | `parent_reference` | Structural — OpenAPI path parameter on a nested resource |
| DDL `PRIMARY KEY (transaction_id)` on a transaction table | `persistence_id` | Structural — explicit DDL PK declaration |
| DDL `FOREIGN KEY (account_id) REFERENCES account(account_id)` | `parent_reference` | Structural — explicit DDL FK declaration |
| DDL `UNIQUE (transaction_id)` without DDL PK | `business_key` or `idempotency_key` | Structural — uniqueness without PK suggests business key |
| Field named `transactionId` on entity named `Transaction` | `event_id` (not `persistence_id`) | Heuristic — field stem matches entity name, but event entities often need a separate row identity |
| BRD says "transaction reference must be unique for duplicate detection" | `idempotency_key` | Documentary — explicit business policy |
| Field named `correlationId` or `traceId` | `correlation_id` | Heuristic — established naming convention |
| Field named `providerReference` or `gatewayTransactionId` | `external_reference` | Heuristic — established naming convention |

### AI provider position

- KS deterministic retrieval (SQLite FTS5/BM25) is the primary evidence source.
- No LLM/provider integration exists; the broader-scopes design keeps any future
  provider/model layer behind KS-B5.
- No LLM-only inference is required for the identity role suggestion design.
- If a provider/model layer is implemented later, it may improve BRD text interpretation, but
  structural evidence still outranks AI-derived suggestions.

---

## 9. Manifest / Export Contract

### Current mapping

The only identity role that maps to a current manifest field is
`persistence_id`:

| Reviewed role | Current manifest mapping | Export behavior |
|---|---|---|
| `persistence_id` | `identity_overrides[].persistence_id` | Accepted `persistence_id` decision exports as an `identity_overrides` entry for the entity. Reaches Layer 3 (Engine-generated `@Id`, repository, route). |
| `parent_reference` | `identity_roles[].role: parent_reference` with `mode: metadata_only` (after Studio PR #155) | Exported as an `identity_roles` entry. Engine accepts the entry and generates zero artifacts in `metadata_only` mode. After Phase 2a, `mode: active` with an explicit policy can drive `cross_entity_exists` validation via the existing rule generation path. Before Studio PR #155, still Studio project state only. |
| `business_key` | `identity_roles[].role: business_key` with `mode: metadata_only` (after Studio PR #155) | Exported as an `identity_roles` entry. Engine generates zero artifacts. Phase 3 planned for active policy. Before Studio PR #155, Studio project state only. |
| `event_id` | `identity_roles[].role: event_id` with `mode: metadata_only` (after Studio PR #155) | Exported as an `identity_roles` entry. Engine generates zero artifacts. Phase 5 planned. Before Studio PR #155, Studio project state only. |
| `idempotency_key` | `identity_roles[].role: idempotency_key` with `mode: metadata_only` (after Studio PR #155) | Exported as an `identity_roles` entry. Engine generates zero artifacts. Phase 4 planned. Before Studio PR #155, Studio project state only. |
| `correlation_id` | `identity_roles[].role: correlation_id` with `mode: metadata_only` (after Studio PR #155) | Exported as an `identity_roles` entry. Engine generates zero artifacts. Phase 5 planned. Before Studio PR #155, Studio project state only. |
| `external_reference` | `identity_roles[].role: external_reference` with `mode: metadata_only` (after Studio PR #155) | Exported as an `identity_roles` entry. Engine generates zero artifacts. Phase 5 planned. Before Studio PR #155, Studio project state only. |

### C9 interaction

A1 identity role review and C9 ID generation strategy are separate concerns
that compose:

- A1 / identity role review answers: **which field is the persistence
  identity?**
- C9 answers: **how is that identity value generated?** (UUID, database
  identity, sequence, caller-supplied)

Identity role review happens first. Once the author has selected the
`persistence_id` field, C9 generation strategy selection can follow. The two
decisions should not be conflated in a single UI panel.

### Future manifest metadata

Future manifest extensions may add metadata for non-persistence roles:

- `entity_kind` — advisory classification (master, reference, event, etc.)
- `business_keys` — list of fields declared as business keys per entity
- `idempotency_keys` — list of fields declared as idempotency keys per entity

These are design-only placeholders in this document. They should not be
implemented as manifest fields until a separate additive manifest extension
design is approved. The design intent is:

- additive and optional under `schema_version: "1.0"`
- no breaking change to existing manifests
- no Engine behavior change without explicit implementation PR

---

## 10. Engine Interaction

### Safety net preservation

Engine PR #138 fail-fast guard remains the safety net regardless of Studio
identity review:

- if Studio exports `identity_overrides`, the Engine uses the explicit
  override and bypasses the heuristic entirely
- if Studio does not export `identity_overrides` for an entity, the Engine
  heuristic runs and the PR #138 fail-fast guard applies
- Engine behavior is deterministic and does not depend on whether Studio or KA
  was used during authoring

### Generated app independence

Generated applications remain standalone Spring Boot applications with no
runtime dependency on Studio, Knowledge Assist, Knowledge Server, MCP, or
EdgeForge:

- identity role decisions are baked into the manifest at export time
- `identity_overrides` are consumed by the Engine during generation
- the generated `@Id`, routes, repositories, and DDL reflect the reviewed
  identity — no runtime lookup or callback is needed
- if the manifest has no `identity_overrides`, the Engine heuristic applies as
  it always has

### No automatic surrogate identity

The Engine does not currently auto-generate surrogate row identity fields. If
an entity has no suitable persistence identity field, the author must add one to
the upstream contract or manifest. This design does not change that behavior.

A future design may consider whether Studio should offer to suggest creating a
new surrogate field (e.g., an auto-generated `id` column), but that is an open
question, not a current feature.

---

## 11. Cross-Entity / Rules Interaction

Reviewed identity roles create candidates for downstream rule suggestions in
Step 6. The dependency table below defines how identity roles map to rule
suggestion candidates:

| Identity role | Rule suggestion candidate | Example |
|---|---|---|
| `parent_reference` | `cross-entity-exists` — referenced entity row must exist | `accountId` on Transaction → Account must exist |
| `parent_reference` | `cross-entity-field-check` — field on referenced entity must satisfy a predicate | `accountId` → Account.status must be Active |
| `parent_reference` | `cross-entity-field-compare` — field comparison across entities | Transaction.currency must match Account.currency |
| `business_key` | Uniqueness rule — field or field combination must be unique | `accountNumber` must be unique per entity |
| `idempotency_key` | Duplicate/replay protection rule — ensure idempotent create behavior | `transactionId` must not produce duplicate rows on retry |
| `persistence_id` | Generated row identity — usually not a business rule | `id` is infrastructure, not a domain constraint |
| `event_id` | Possible duplicate detection input — not JPA `@Id` by default | `transactionId` may need uniqueness but is not automatically the row PK |
| `correlation_id` | Tracing/integration metadata — not a persistence or business rule target by default | `correlationId` is for logging and debugging |
| `external_reference` | External integration metadata — may need format validation | `providerReference` format may need pattern rule |

The key insight: **identity role classification informs rule suggestions, but
identity roles are not rules themselves.** A `parent_reference` classification
creates a candidate for a `cross-entity-exists` rule, but the rule must still
be authored, reviewed, and accepted separately in Step 6.

---

## 12. Save / Open / Project Schema Implications

### Persistence of identity decisions

Reviewed identity role decisions must survive save/open cycles:

- accepted and edited identity roles are stored in the Studio project file
- the project file already supports `suggestion_review_state`, `review_history`,
  and `evidence_links` per the project workspace / decision ledger design
- identity role decisions use the same review history mechanism as other
  suggestion types

### Schema migration

Adding identity role review to the Studio project file may require a schema
version bump:

- the project file needs to store per-entity, per-field identity role
  classifications
- older project files that lack identity role data must open cleanly with
  identity roles unclassified
- the schema version bump should happen during implementation, not in this
  design doc

### Rejected suggestions

Rejected identity suggestions are stored in the review history, not in the
manifest or evidence trail. They are visible in Step 7 Decision History for
audit purposes but do not affect generation.

### Evidence Trail interaction

The current Evidence Trail v1.1 supports these evidence types: `field`,
`validation`, `rule`, `cross_entity_rule`, `mapping`, `transform`.

An `identity_role` evidence type is not part of the current baseline. Later
implementation must decide whether identity decisions are represented through:

- enriching existing `field` evidence links with identity role metadata
- adding a new `identity_role` evidence type in a future Evidence Trail v1.2
- recording identity decisions only in the project decision ledger without
  an evidence trail entry

The recommended approach is to start with the project decision ledger (which
already stores `review_history` entries) and add Evidence Trail support only if
compliance/audit requirements demand it. This avoids expanding the evidence
sidecar schema before the identity review feature is proven in use.

---

## 13. Implementation Slices

The following later PRs are recommended. This design document gates all of
them. No implementation should begin before this design is reviewed and
approved.

### Slice 1 — Studio model and save/open support

- Add per-entity, per-field identity role storage to the Studio project model
- Migrate older project files that lack identity role data
- Ensure save/open round-trips preserve identity role classifications
- No UI changes in this slice

### Slice 2 — Studio Step 3 identity role review UI

- Add identity role column/chips to the Step 3 field table
- Add identity review section for the current entity
- Manual identity classification works with KA OFF
- No KA suggestion integration in this slice

### Slice 3 — KS/KA deterministic identity-role suggestion support

- Add `identity_role` as a suggestion scope in KS
  `suggest_manifest_candidates`
- Implement deterministic evidence retrieval for identity role signals:
  DDL PK/FK/unique, OpenAPI path parameters, field catalog, BRD text, naming
  conventions
- KS evidence (BRDs, field catalogs, DDL keys, OpenAPI paths, legacy evidence)
  drives the identity-role suggestion quality; wire KS signals first before
  adding heuristic fallbacks
- Add `identity_role` typed payload to the suggestion envelope
- Badge and drawer in Step 3 for identity suggestions

### Slice 4 — Studio export to current Engine `identity_overrides`

- Accepted `persistence_id` decisions export as `identity_overrides` entries
- Verify that exported manifests satisfy Engine PR #138 without fail-fast
  errors
- Other reviewed roles are stored in the project but do not export to current
  manifest fields

### Slice 5 — Engine/Studio proof using PR #138 invalid fixture

- Use the `transaction-identity-wrapper-invalid` test fixture from PR #138
- Demonstrate that Studio-authored identity review + export satisfies the
  Engine without triggering the fail-fast guard
- The `transaction-identity-wrapper-valid` fixture already passes; the proof
  shows Studio can produce a valid manifest for the previously-invalid case

### Slice 6 — Future business/idempotency key rule generation design

- Design how `business_key` and `idempotency_key` classifications feed into
  uniqueness and duplicate protection rule suggestions in Step 6
- May require additive manifest metadata for unique constraints
- Separate design review required

### Slice 7 — Future Evidence Trail handling for identity decisions

- Decide whether identity decisions need their own Evidence Trail type
- If yes, add `identity_role` to Evidence Trail v1.2
- If no, document that identity decisions live in the project decision ledger
  only

---

## 14. Acceptance Criteria

The following criteria define when the later implementation slices are complete.
They are not acceptance criteria for this design document itself.

### Functional criteria

- [ ] KA OFF manual identity review and export works end-to-end
- [ ] KA ON shows deterministic evidence-backed identity suggestions
- [ ] User can review an event/transaction entity and see:
  - persistence row ID
  - parent reference / FK
  - business key
  - event / transaction ID
  - idempotency key where applicable
- [ ] Accepted `persistence_id` decision exports as `identity_overrides`
- [ ] Rejected suggestions do not affect the manifest
- [ ] Engine PR #138 fail-fast fixture can be satisfied by Studio-authored
  identity review
- [ ] Step 6 can consume parent/business/idempotency roles for rule
  suggestions
- [ ] Step 7 records identity decision history
- [ ] Generated app has no runtime dependency on Studio, KA, KS, or MCP

### Non-functional criteria

- [ ] Older Studio project files without identity role data open cleanly
- [ ] Identity review section does not appear when entity has zero
  identifier-shaped fields
- [ ] KA badge is absent when KA is OFF or when zero identity suggestions
  exist
- [ ] Manual classification is fully functional without KA enabled
- [ ] Entity kind is advisory only and does not affect Engine generation
  unless a future design explicitly adds it

---

## 15. Open Questions

| # | Question | Impact | Recommendation |
|---|---|---|---|
| OQ1 | Exact future manifest field for non-persistence identity roles | Manifest schema evolution | Resolved: `identity_roles` top-level section now exists in the manifest schema and the Pydantic model. Non-persistence roles export as `identity_roles` entries with `mode: metadata_only` (after Studio PR #155). Active policy for `parent_reference` is defined in the identity-role-engine-behavior-design.md Phase 2 section. |
| OQ2 | Whether business/idempotency uniqueness belongs in rules, entity metadata, or operation metadata | Manifest and Engine design | Lean toward rules (the current rule system already supports `allowed-values`, `pattern`, etc.); evaluate after Slice 6 design. |
| OQ3 | Whether first implementation supports multiple business keys per entity | Studio data model | Yes — store as a list. A single entity can have both `accountNumber` (business key) and `idempotencyKey` (idempotency key). |
| OQ4 | Whether `identity_role` gets its own Evidence Trail v1.2 type | Evidence Trail schema | Defer to Slice 7. Start with project decision ledger only. |
| OQ5 | How LegacyExtractor evidence participates once Phase 6 is active | KS-B6 integration | LE-extracted DDL, stored procedure analysis, and legacy mapping artifacts feed into KS as provenance-tagged evidence (`le-extraction`). Identity role suggestions can use LE evidence through the same KS retrieval path. |
| OQ6 | Whether Studio should ever suggest creating a new surrogate ID field | Author experience | Defer. The current design requires authors to map an existing field. Creating new fields is a manifest authoring concern, not an identity review concern. |
| OQ7 | How to represent composite keys / composite business keys in the first implementation | Studio data model | Defer composite key support. First implementation covers single-field identity roles only. Document the limitation explicitly. |
| OQ8 | Whether entity kind should eventually be a manifest field or remain Studio-only advisory | Manifest schema | Lean toward Studio-only advisory in first implementation. If Engine behavior per entity kind is later needed (e.g., append-only generation for event entities), revisit as an additive manifest extension. |

---

*EdgeForge Suite · Entity Identity Role Review Design · May 2026 · Post-v3.0.0 generated-app standards track*
