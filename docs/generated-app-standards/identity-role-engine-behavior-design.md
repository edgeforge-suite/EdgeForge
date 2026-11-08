# Identity Role Engine Behavior Design

> **Status:** Design draft — future Engine behavior roadmap for non-persistence
> identity roles. Phase 2 active `parent_reference` policy contract added May 2026.
>
> **Owner:** EdgeForge Engine / Studio / Knowledge Server design.
>
> **Date:** May 2026.
>
> **Related docs:**
> - [Entity Identity Role Review Design](entity-identity-role-review-design.md)
>   -- the Studio/KA review UX for role classification (current baseline)
> - [A1 Identity Semantics Design](../a1-identity-semantics-design.md)
> - [C9 ID Generation Strategy Design](../c9-id-generation-strategy-design.md)
> - [Generated App Quality Gate v1](generated-app-quality-gate-v1.md)
> - [Generated App Engine Roadmap](generated-app-engine-roadmap.md)
> - [Manifest Schema](../manifest-schema.md)
> - [CRUD Cross-Entity Rules](../crud-cross-entity-rules-design.md)

---

## 1. Purpose

Studio and Knowledge Assist can review and classify seven identity roles on
entity fields:

| Role | Current status |
|---|---|
| `persistence_id` | Reaches Layer 3 via `identity_overrides`. Engine generates `@Id`, repository, route identity. |
| `parent_reference` | Reaches Layer 2 as an `identity_roles` entry with `mode: metadata_only` (after Studio PRs #148 / #153 / #155). Generates zero Engine artifacts in `metadata_only` mode. Phase 2 active policy design is the subject of this document. |
| `business_key` | Layer 2 export as `identity_roles` with `mode: metadata_only` (after Studio PR #155). Generates no Engine artifacts. Phase 3 planned. |
| `event_id` | Layer 2 export as `identity_roles` with `mode: metadata_only` (after Studio PR #155). Generates no Engine artifacts. Phase 5 planned. |
| `idempotency_key` | Layer 2 export as `identity_roles` with `mode: metadata_only` (after Studio PR #155). Generates no Engine artifacts. Phase 4 planned. |
| `correlation_id` | Layer 2 export as `identity_roles` with `mode: metadata_only` (after Studio PR #155). Generates no Engine artifacts. Phase 5 planned. |
| `external_reference` | Layer 2 export as `identity_roles` with `mode: metadata_only` (after Studio PR #155). Generates no Engine artifacts. Phase 5 planned. |

### Engine-generated track vs advisory track

A strategic decision applies to each role before any implementation begins.
This table is the authoritative record of that decision and must be updated
before any phase is implemented.

| Role | Track | Rationale |
|---|---|---|
| `persistence_id` | **Engine** (implemented) | Fully generated via `identity_overrides`. |
| `parent_reference` — cross_entity_exists | **Engine** — Phase 2a | Identical in every service, reuses existing `CanonicalRule` path, zero variation. |
| `parent_reference` — `@ManyToOne` / FK | **Advisory** — Phase 2e optional | Architectural preference; `existsById` check (Phase 2a) captures the correctness value. JPA relationship shape is a developer decision. |
| `business_key` — single-field | **Engine** — Phase 3 | Mechanical DDL boilerplate; DB constraint handles concurrency correctly. Policy must be explicit: unique scope, constraint name, nullable semantics, and 409 mapping. |
| `business_key` — composite (multi-field) | **Advisory** — defer | No manifest syntax designed. Composite keys use a future `business_key_policies` section, not multiple independent `business_key` role entries (see Section 4.2). Design the escape hatch before single-field implementation hardens assumptions. |
| `external_reference` — index + finder | **Engine** — Phase 3 (folds into business_key) | Purely mechanical: Flyway index + Spring Data method. Not unique by default — external refs are often provider-scoped. |
| `event_id` — unique constraint | **Engine** — Phase 5 (cross-service Phase A dependency) | Same template as `business_key`; requires cross-service integration Phase A before full event deduplication value is realised. |
| `idempotency_key` | **Advisory** — Phase 4 design first | Replay mode, retention, storage backend, and concurrent-duplicate handling are too contextual for a generic template. `mode: active` is **not valid** for `idempotency_key` until a complete interceptor + replay + retention design is settled. A DDL-only scaffold would not satisfy the `active` contract. If scaffold-only behavior is later desired, a `mode: scaffold_only` concept requires a separate design document before any implementation. |
| `correlation_id` | **Advisory** | Spring Boot 3.x + Micrometer Tracing already handles trace/correlation ID propagation. A custom generated MDC filter risks conflicting with Micrometer's infrastructure. Cross-thread propagation in async contexts is where hand-rolled solutions break silently. Kafka propagation depends on cross-service integration Phase D. |

**`active` contract rule:** `mode: active` means the Engine generates fully-supported,
real artifacts — or rejects the manifest with a clear error. There is no valid
middle ground: partial generation, scaffold stubs, or TODO placeholders do not
satisfy `active`. A role that cannot yet generate complete artifacts must stay
`mode: metadata_only`.

### Current baseline: what `metadata_only` means today

An `identity_roles` entry with `mode: metadata_only` is accepted by the Engine
and produces **zero** generated artifacts. Specifically, it generates:

- no Java code of any kind
- no DDL, Flyway migration, or database constraint
- no validation rule, business rule, or `applyBusinessRules()` hook
- no foreign key, index, or relationship annotation
- no idempotency logic, finder method, or logger hook
- no additional runtime behavior of any kind

The entry is structurally valid in the manifest but the Engine treats it as
read-only metadata. Studio can display it as "reviewed, not yet active."

**Important:** If Studio PR #155 has not yet merged, non-`persistence_id` roles
are still Studio-only project state and do not appear in exported manifests at
all. The row above ("Reaches Layer 2 ... after Studio PR #155") describes the
state after that PR merges. Until then, the `entity-identity-role-review-design.md`
Section 9 table ("No current manifest field — Recorded in Studio project state")
accurately describes the pre-#155 state.

### What this document adds

Today, `persistence_id` is the only role that flows through all three layers:
Studio project state, exported manifest/package, and Engine-generated app
behavior. This document defines how `parent_reference` can safely reach Layer 3
in Phase 2, and documents the phased roadmap for the remaining five roles,
**without magical inference, silent database constraints, or implicit runtime
coupling**.

---

## 2. The Three-Layer Model

Every identity role passes through three layers before it becomes generated-app
behavior. A role that exists only in Layer 1 is safe metadata. A role that
reaches Layer 3 produces real artifacts with real correctness consequences.

```
 Layer 1: Studio project state
 ─────────────────────────────
 What the author sees and reviews in Studio.
 Roles are classified. Review citations and decision history are recorded in
 Studio project state. No external effect.
 Note: Evidence Trail v1.1 does not include identity_role entries.
 Studio decision history is separate from evidence-trail.json.

          │  export
          ▼

 Layer 2: Manifest / input package
 ─────────────────────────────────
 What the manifest carries. The Engine reads this.
 Only exported roles produce Engine behavior. All others are invisible.

          │  generation
          ▼

 Layer 3: Engine-generated app behavior
 ────────────────────────────────────────
 What appears in the generated Spring Boot application.
 Code, annotations, DDL, configuration. Real artifacts. Real consequences.
```

**Current state:** Only `persistence_id` reaches Layer 3. After Studio PR #155
lands, non-`persistence_id` roles reach Layer 2 as `identity_roles` entries
with `mode: metadata_only`, which generates no artifacts. The existing identity
smoke proves the full loop for `persistence_id`. This document plans the path
for the remaining six roles, starting with `parent_reference` in Phase 2.

---

## 3. Safety Principles

These principles are non-negotiable. Every role-to-behavior proposal in this
document must satisfy all of them.

### 3.1 Role selection captures intent, not behavior

Classifying a field as `business_key` in Studio captures the author's intent
that this field is a domain-meaningful natural key. It does **not** automatically
generate a unique constraint, a finder method, or a duplicate validation rule.
The role is descriptive metadata until the author explicitly approves a behavior
policy.

### 3.2 Generated behavior requires reviewed policy/scope

Moving a role from Layer 1 to Layer 3 requires:
- an explicit policy declaration in the manifest (Layer 2)
- a reviewed scope (which entity, which operations, what enforcement mode)
- human approval in Studio before export

The Engine never infers behavior from role classification alone.

### 3.3 No silent database constraints

The Engine must not add unique constraints, indexes, foreign keys, or check
constraints to DDL based solely on a role classification. Every database
artifact requires:
- an explicit manifest directive
- a reviewed migration (Flyway) entry
- visibility in the generated `CREATE TABLE` or `ALTER TABLE` statement

Authors must see exactly what will be generated before it is generated.

### 3.4 No idempotency behavior without operation/retention/replay policy

An `idempotency_key` classification does not produce idempotency logic.
Idempotency requires:
- which operation(s) are guarded
- what the retention window is
- what the replay response is (return cached result, return 409, return 200
  with original)
- where the idempotency state is stored (DB table, Redis, in-memory)

Without all four answered, the Engine emits nothing.

### 3.5 No database FK assumption for cross-service references

A `parent_reference` classification does not produce a `FOREIGN KEY` constraint.
In a decomposed microservice architecture, the parent entity may live in a
different service and database.
Parent-reference behavior is:
- default: no FK, no constraint, regular field
- explicit opt-in: FK only when the parent is a same-service entity and the
  author enables it in the policy
- cross-service: runtime exists-check via API call, never a DB FK

### 3.6 Generated apps remain standalone

No generated behavior may introduce a runtime dependency on Studio, Knowledge
Assist, Knowledge Server, or any MCP tool. Generated apps are owned by the adopting organization and
runtime-independent. All identity behavior is resolved at generation time and
baked into the application.

---

## 4. Role-by-Role Future Behavior

Each subsection below defines the **proposed** generated behavior for one
identity role. None of these behaviors exist today. Each requires its own
implementation, manifest contract extension, and review.

### 4.1 `parent_reference`

**Current state (Engine):** Engine PR #138 fails fast if a parent-reference
field is inferred as `persistence_id` on event/transaction entities. The
manifest already supports `cross-entity-exists` rules, and those rules are
generated through an established path in `java_emitter.py` (the
`cross_entity_checks` / `cross_entity_repos` / `cross_entity_state_rules`
collections). A reviewed `parent_reference` role classification in Studio does
not automatically produce a rule. Authoring a `cross-entity-exists` rule in
the manifest is today a manual Step 6 action entirely separate from the role
classification.

**Current state (manifest model):** After Studio PR #155, `parent_reference`
reaches Layer 2 as an `identity_roles` entry with `mode: metadata_only`. The
Engine accepts this entry and generates nothing from it. The
`IdentityRoleDefinition` model in `appbuilder/contracts/manifest.py` validates
the role and mode values and enforces that `mode: active` is rejected with a
clear validation error (line 267-272) until Engine support is implemented.

---

#### Phase 2 active `parent_reference` policy contract

Phase 2 defines how an `active` mode `parent_reference` entry in
`identity_roles` translates into generated Engine behavior.

##### Policy shape

```yaml
identity_roles:
  - entity: Transaction
    field: accountId
    role: parent_reference
    mode: active
    policy:
      target_entity: Account         # required
      reference_type: local          # required: local | remote
      validation:
        cross_entity_exists: true    # optional, default false
      relationship_metadata:
        enabled: false               # optional, default false — deferred to Phase 2b
      db_foreign_key:
        enabled: false               # optional, default false — deferred to Phase 2b
```

##### Required vs optional policy fields

| Field | Required | Reasoning |
|---|---|---|
| `target_entity` | **Required** | The Engine cannot know which entity to look up without an explicit target. Inference from field name is rejected — see Safety Principle 3.2. |
| `reference_type` | **Required** | The `local` vs `remote` distinction has fundamentally different safety boundaries (DB FK eligibility, generation path). Inference from entity list membership would be brittle and unreviewed. |
| `validation.cross_entity_exists` | Optional, default `false` | Explicit opt-in to the exists check. Omitting it leaves the field as a regular column with no constraint. |
| `relationship_metadata.enabled` | Optional, default `false` | Deferred to Phase 2b. Present in schema for forward compatibility; Engine rejects `true` in Phase 2a with a clear error. |
| `db_foreign_key.enabled` | Optional, default `false` | Deferred to Phase 2b. Present in schema for forward compatibility; Engine rejects `true` in Phase 2a with a clear error. |

##### `reference_type: local` behavior

A `local` reference means the `target_entity` is present in the same
manifest's entity set — i.e., it will be generated in the same application.

| Policy flag | Phase 2a behavior | Future phase |
|---|---|---|
| `validation.cross_entity_exists: true` | Engine translates the active entry into an internal `CanonicalRule` with `type: CROSS_ENTITY_EXISTS` for the same `entity.field → target_entity` pair. Uses existing generation path unchanged. | Already available (Phase 2a). |
| `relationship_metadata.enabled: true` | Engine rejects with validation error: "relationship_metadata is not yet supported in Phase 2a; set enabled: false" | Phase 2b |
| `db_foreign_key.enabled: true` | Engine rejects with validation error: "db_foreign_key is not yet supported in Phase 2a; set enabled: false" | Phase 2b |

**Duplicate-rule guard:** If the manifest also contains an explicit
`cross-entity-exists` rule YAML file for the same `(entity, field,
target_entity)` triple, the Engine must detect the conflict and reject with a
validation error naming both sources. The active identity role and an explicit
rule must not both generate an `existsById` check for the same lookup.

##### `reference_type: remote` behavior

A `remote` reference means the `target_entity` does not live in the same
application. It may be in a separate service with its own database.

| Policy flag | Phase 2a behavior |
|---|---|
| `validation.cross_entity_exists: true` | Engine rejects with validation error: "cross_entity_exists is not valid for reference_type: remote — a remote existsById requires a service client, which is out of scope. Use mode: metadata_only to record this reference without generating behavior." |
| `relationship_metadata.enabled: true` | Engine rejects with validation error: "relationship_metadata is not valid for reference_type: remote — JPA relationships require a local entity" |
| `db_foreign_key.enabled: true` | Engine rejects with validation error: "db_foreign_key is not valid for reference_type: remote — DB FK requires a local co-located entity" |

`mode: active` is **always rejected** for `reference_type: remote`, regardless
of policy flag values. There is no Engine behavior that can fulfil an active
remote parent reference today — not even a no-op acceptance. The contract is
strict: `active` must produce supported behavior or fail fast, and "accepted
with zero artifacts" is not a valid active outcome.

To document a remote parent reference, use `mode: metadata_only`. That is the
only valid mode for remote references until a future phase (not Phase 2)
introduces remote exists-check client generation.

**Important:** `reference_type: remote` never produces a DB FK or JPA
relationship annotation, even in future phases. Cross-service references use
runtime API clients, which are a separate design concern outside this document.

---

#### Mapping to existing cross-entity rule generation — Option A

**Design decision: Option A is selected.**

The Engine translates an `active parent_reference` entry with
`cross_entity_exists: true` into the same internal `CanonicalRule` model as an
explicit `cross-entity-exists` rule YAML entry. The existing generation path
in `java_emitter.py` is used without modification.

**Justification based on the code:**

Reading `appbuilder/rules/ingestion.py` and `appbuilder/generation/java_emitter.py`:

1. The `cross-entity-exists` generation path in `java_emitter.py` is already
   battle-tested. It populates `cross_entity_checks` (all rules, drives
   `existsById` per field) and `cross_entity_repos` (deduplicated by
   `target_entity`, drives one repository injection per target). This
   deduplication logic handles the case where multiple FK fields on the same
   entity reference the same target — exactly the pattern that
   `active parent_reference` would produce.

2. `CanonicalRule` already has all the fields needed: `entity_name`,
   `field_name`, `type: RuleType.CROSS_ENTITY_EXISTS`, `target_entity`. No new
   model fields are required for Phase 2a.

3. The Engine validates that `target_entity` exists in the metadata's known
   entity set (line 2841-2847) and that the field type matches the target
   entity's ID field type (line 2851-2859). These validations apply equally to
   rules synthesized from `identity_roles`.

4. Option B (Studio exports an explicit `cross_entity_rules` entry) would work
   but introduces a redundancy: the `identity_roles` section would carry the
   policy declaration while a separate rule YAML file carries the generated
   rule. This splits the intent across two manifest artifacts for what is
   logically one policy decision. Option A keeps the single-source-of-truth
   principle: the `identity_roles` policy entry is the canonical declaration.

**Implementation path (PR 2a):**

In `appbuilder/contracts/manifest.py`, the `_validate_identity_roles_contract`
function currently rejects all `mode: active` entries (line 1175-1179). PR 2a
replaces that blanket rejection with role-specific validation:

- `role: parent_reference` + `reference_type: local` + `cross_entity_exists: true`
  → accepted; the Engine synthesizes a `CanonicalRule(type=CROSS_ENTITY_EXISTS)`
  for the entry during ingestion
- `role: parent_reference` + `reference_type: remote` → accepted; generates
  nothing; remote FK and relationship are rejected as described above
- `role: parent_reference` + `relationship_metadata.enabled: true` → rejected
  in Phase 2a with clear error
- `role: parent_reference` + `db_foreign_key.enabled: true` → rejected in
  Phase 2a with clear error
- Any other role with `mode: active` → continues to be rejected with "not yet
  supported"

The synthesized `CanonicalRule` is inserted into the rule list during manifest
ingestion, before the emitter runs. The emitter code is **not modified** — it
processes the synthesized rule through the same path as an explicit rule YAML
entry.

---

#### Relationship metadata — deferred to Phase 2b

`@ManyToOne` / `@JoinColumn` / fetch type generation requires verifying that
`java_emitter.py` has safe, tested support for JPA relationship annotations.
Reading the emitter, no such support exists today. Implementing it would
require new generation paths for:

- `@ManyToOne` annotation on the field
- `@JoinColumn(name = "...")` referencing the FK column name
- fetch type selection (LAZY vs EAGER) and the associated N+1 risk discussion
- DTO impact: the related entity's fields would need to be included or excluded
  from request/response shapes

This is a meaningful design surface that must not be bundled into the first
Phase 2 PR. It is deferred to Phase 2b.

---

#### DB FK policy — deferred to Phase 2b

DB FK generation requires all five conditions to be true simultaneously:

1. `mode: active`
2. `role: parent_reference`
3. `reference_type: local`
4. `target_entity` is present in the same manifest's entity set
5. `db_foreign_key.enabled: true`

Reading `java_emitter.py`, the Flyway migration emitter does not currently
have support for `FOREIGN KEY` constraint emission. Implementing FK DDL
involves deciding:

- whether the FK is deferrable or non-deferrable
- the `ON DELETE` and `ON UPDATE` behavior
- how the FK interacts with Flyway migration ordering (parent table must exist
  before FK is applied)
- whether cascade behavior is in scope

This is deferred to Phase 2b. PR 2a rejects `db_foreign_key.enabled: true`
with a clear validation error pointing to the Phase 2b roadmap.

---

#### KA OFF behavior and Studio/KS boundaries

- Studio owns authoring and export of the active `parent_reference` policy
  (Phase 2b Studio PR).
- With KA OFF, the author manually sets `mode: active` and writes the policy
  block in the manifest. The Engine accepts or rejects based on the policy
  content alone.
- Knowledge Server can suggest `parent_reference → cross-entity-exists` policy
  candidates (Phase 2c KS PR), but does not auto-approve active behavior.
- Neither KA suggestions nor KS candidates move a role from `metadata_only` to
  `active` without human review in Studio.
- Evidence Trail and the project decision ledger are unchanged by Phase 2a.
  The active policy is in the manifest; no new evidence-trail type is needed.

---

**Proposed future behaviors (updated):**

| Behavior | Phase | Trigger | Generated artifact |
|---|---|---|---|
| Cross-entity-exists validation | Phase 2a | `mode: active`, `reference_type: local`, `cross_entity_exists: true` | `existsById` check in create/update/state_transition via existing rule generation path |
| Remote reference metadata | Phase 2a | `mode: metadata_only`, `reference_type: remote` | Nothing; accepted as reviewed metadata — `mode: active` is always rejected for remote references |
| Relationship metadata | Phase 2b | `relationship_metadata.enabled: true` | `@ManyToOne` / `@JoinColumn` JPA annotations (deferred) |
| Optional DB FK | Phase 2b | `db_foreign_key.enabled: true` AND `reference_type: local` | `FOREIGN KEY` constraint in Flyway migration (deferred) |

**Constraints (unchanged from original):**
- DB FK is never generated for `reference_type: remote`
- `db_foreign_key: true` is an explicit opt-in, never a default
- Without any active policy, a `parent_reference` field remains a regular
  column with no constraints

### 4.2 `business_key`

**Current state:** Layer 2 export as `identity_roles` with `mode: metadata_only`
(after Studio PR #155). No Engine artifacts.

**Track: Engine — Phase 3 (single-field only).**

**Proposed future behaviors (single-field):**

| Behavior | Trigger | Generated artifact |
|---|---|---|
| Unique constraint | Author enables `unique_scope: entity` or `unique_scope: bounded_context` | `UNIQUE` constraint in Flyway migration, `@Column(unique=true)` |
| Finder method | Author enables `generate_finder: true` | `findByBusinessKey()` repository method + service lookup |
| Duplicate validation | Author enables `duplicate_check: pre_persist` | Service-layer check before insert, 409 Conflict on duplicate |

**Engine generation requirements (all must be explicit in policy):**
- `unique_scope` is required — `entity`, `bounded_context`, `tenant`, or `global`.
  The Engine rejects `business_key` active entries without an explicit scope.
- Constraint names are deterministic and derived from entity + field names
  (e.g., `uq_transaction_transaction_ref`). Authors may override.
- Nullable semantics must be documented: a nullable `business_key` field is
  unusual and the Engine will warn. A `UNIQUE` constraint on a nullable column
  allows multiple NULLs in most databases — this must be an explicit choice.
- Duplicate violation maps to `409 Conflict` with a structured error body.
  The Engine does not generate custom error shapes; override via the standard
  exception handler if a different shape is needed.

**Composite business key — design the escape hatch before single-field implementation:**

Composite keys (unique across multiple fields) must NOT be expressed as multiple
independent `business_key` role entries on the same entity — that would imply
separate unique constraints on each field individually, not a compound constraint.

The reserved future shape uses a separate manifest section:

```yaml
# Single-field: identity_roles entry (Phase 3, implemented)
identity_roles:
  - entity: Account
    field: accountNumber
    role: business_key
    mode: active
    policy:
      unique_scope: entity

# Composite key: separate grouped policy (future — NOT YET IMPLEMENTED)
# Do not use multiple identity_roles entries to express a composite key.
business_key_policies:
  - entity: Account
    fields: [sortCode, accountNumber]
    unique_scope: entity
    # Not valid until manifest schema extension is designed and merged.
```

This reservation prevents manifest assumptions hardened by single-field
implementation from blocking composite key design later.

**Constraints:**
- Without any policy, a `business_key` field is a regular column
- Composite key support is deferred — do not attempt to express composite
  keys using multiple `identity_roles` entries

### 4.3 `idempotency_key`

**Current state:** Layer 2 export as `identity_roles` with `mode: metadata_only`
(after Studio PR #155). No Engine artifacts. `mode: active` is not valid for
this role — see Track note below.

**Track: Advisory — `mode: active` is NOT valid for this role today.**

`mode: active` requires the Engine to generate fully-supported, real artifacts.
`idempotency_key` cannot satisfy that contract because the replay mode, retention
TTL, storage backend, and concurrent-duplicate handling are all business and
infrastructure decisions that a generic template cannot make safely:

- **Replay mode** (`cached_response` vs `conflict_409` vs `success_200_original`)
  is a business decision — a payment API and a reference-data API have different
  correct behaviors on duplicate.
- **Concurrent-duplicate correctness** requires an INSERT-first pattern (INSERT
  the idempotency record using a DB-level UNIQUE constraint, then execute). A
  check-then-act implementation has a race condition under concurrent load. This
  is a correctness property the Engine template must prove, not assume.
- **Storage backend** (DB table vs Redis vs in-memory) is an infrastructure
  decision outside the manifest.

A DDL-only partial scaffold would not satisfy `active` — it would generate a
table with no guard, giving a false sense of protection. **That is worse than
no generation.**

If scaffold-only behavior is ever desired, a `mode: scaffold_only` concept
requires a separate design document defining its contract before any implementation.

**Phase 4 scope: design document first, implementation TBD.**
Phase 4 settles the full policy semantics via a design PR before any Engine
code is written. Until that design is agreed and the Engine can generate a
complete, concurrency-correct implementation, all `idempotency_key` entries
must use `mode: metadata_only`.

**Future design requirements (not yet Engine-generatable):**

| Behavior | Required policy field | Design question |
|---|---|---|
| Per-operation guard | `operations: [create, update]` | Which operations require idempotency? |
| Replay behavior | `replay_mode: cached_response \| conflict_409 \| success_200_original` | Business decision — no safe default |
| Retention / TTL | `retention_days: N` | Compliance / storage budget decision |
| Storage backend | `storage: db_table \| redis \| in_memory` | Infrastructure decision |

**Constraints:**
- All four policy fields are required before Engine generation is valid
- The idempotency table (if DB-backed) requires a Flyway migration with
  a UNIQUE constraint on the key column — the DB enforces the race condition
  boundary, not application code
- No default retention — the author must choose explicitly

### 4.4 `correlation_id`

**Current state:** Layer 2 export as `identity_roles` with `mode: metadata_only`
(after Studio PR #155). No Engine artifacts. Advisory track — no active
generation planned.

**Track: Advisory — use Micrometer Tracing; `mode: active` not planned for this role.**

Spring Boot 3.x with Micrometer Tracing handles trace/correlation ID propagation
built-in. A custom generated MDC filter risks conflicting with or duplicating
Micrometer's trace context infrastructure. The correct implementation path is:

1. Ensure the generated app includes `micrometer-tracing` and the appropriate
   bridge (e.g., Brave, OpenTelemetry).
2. The `correlation_id` manifest metadata records which field carries the
   correlation identifier — Studio displays it; developers use it as the field
   to extract when logging structured events.
3. No Engine generation is planned for the propagation layer.

**Kafka header propagation** depends on cross-service integration Phase D
(see [cross-service-integration-design.md](cross-service-integration-design.md)
Section 5). Until Phase D is implemented, Kafka propagation is not available
regardless of manifest flags.

**Cross-thread propagation note:** MDC context does not propagate automatically
across thread boundaries (`@Async`, virtual threads, parallel streams). Any
generated or hand-written propagation solution must handle this explicitly.
Micrometer's context propagation API handles this; custom MDC filters do not.

**Proposed advisory documentation (not Engine-generated):**

| Behavior | Implementation path | Dependency |
|---|---|---|
| MDC / logging propagation | Micrometer Tracing (built-in Spring Boot 3.x) | None |
| API header propagation | Micrometer Tracing observation API | None |
| Kafka header propagation | Micrometer Tracing + Kafka binder | Cross-service Phase D |

**Constraints:**
- Header name is configurable via Micrometer (default: `traceparent` for
  W3C Trace Context, or `X-B3-TraceId` for Brave)
- Without Micrometer, a `correlation_id` field is a regular column —
  propagation must be wired manually

### 4.5 `external_reference`

**Current state:** Layer 2 export as `identity_roles` with `mode: metadata_only`
(after Studio PR #155). No Engine artifacts.

**Track: Engine — Phase 3 (folds into business_key generation pass).**

Index and finder generation use the same mechanical template as `business_key`.
No uniqueness assumption — external references are often provider-scoped and are
not globally unique. Do not generate a UNIQUE constraint by default.

**Proposed future behaviors:**

| Behavior | Trigger | Generated artifact |
|---|---|---|
| Lookup index | Author enables `generate_index: true` | DB index in Flyway migration |
| Finder method | Author enables `generate_finder: true` | `findByExternalReference()` repository method |
| Provider/system scope | Author sets `provider_scope: "SWIFT"` or similar | Compound index on `(provider, external_ref)` if multi-provider |

**Constraints:**
- **No uniqueness by default** — external refs from upstream systems (SWIFT
  references, correspondent enterprise IDs, clearing house codes) are often
  provider-scoped and may be reused across contexts. A UNIQUE constraint is
  never generated unless explicitly opted in via a separate `unique_scope` policy.
- Provider scope is optional metadata, not a constraint by default
- Without any policy, an `external_reference` field is a regular column

### 4.6 `event_id`

**Current state:** Layer 2 export as `identity_roles` with `mode: metadata_only`
(after Studio PR #155). No Engine artifacts.

**Track: Engine — Phase 5, with cross-service Phase A dependency.**

`event_id` unique constraint generation uses the same DDL template as
`business_key`. However, full event deduplication value is only realised when
the event producer side also has a manifest representation.

**Cross-service Phase A dependency:** Until cross-service integration Phase A
(outbound publisher manifest — see [cross-service-integration-design.md](cross-service-integration-design.md)
Section 5, Phase A) lands, the producer side has no manifest schema. Consumer-side
deduplication by `event_id` can be generated independently, but without the
producer schema there is no contract counterpart to validate the scope against.
Keep `mode: metadata_only` until Phase A is available in the authoring environment.

`source_scope` is required when event IDs originate from upstream systems —
the same event_id value from two different source systems is not a duplicate.
The Engine rejects `event_id` active entries without an explicit scope.

**Proposed future behaviors:**

| Behavior | Trigger | Generated artifact |
|---|---|---|
| Scoped uniqueness | Author enables `unique_scope: entity` + `source_scope` | `UNIQUE` constraint in Flyway migration, optionally compound on `(source_system, event_id)` |
| Duplicate detection | Author enables `duplicate_check: pre_persist` | Service-layer check, 409 on duplicate |
| Source-system scoping | Author sets `source_scope: "<upstream-system>"` | Compound index and uniqueness on `(source_system, event_id)` |

**Constraints:**
- Event IDs from upstream systems are not globally unique — `source_scope` is
  required, not optional
- An `event_id` is never the `persistence_id` (PR #138 enforces this)
- Without any policy, an `event_id` field is a regular column
- Active policy implementation deferred until cross-service Phase A lands

---

## 5. Proposed Phased Roadmap

Each phase builds on the previous. No phase can ship without the safety
principles in Section 3 satisfied.

### Phase 1 — UX clarity, no behavior change

**Status: Complete**

| PR | Delivered |
|---|---|
| Studio PR #148 | Export-impact copy added to identity-role review flow |
| Studio PR #153 | Step 7 wording updated to reflect metadata-only state for non-`persistence_id` roles |
| Studio PR #154 | Engine behavior indicators added per role in Step 3; compact seven-role vocabulary / three-layer model help panel; KA impact copy updated |
| Studio PR #155 | Non-persistence roles export as `identity_roles` entries with `mode: metadata_only` in the manifest |

All Phase 1 items are delivered. The three-layer model is documented in this
design document and surfaced as structured UI in Studio.

**Scope:** Studio and documentation only. No Engine changes. No
Engine-generated artifact behavior changes. Phase 1 includes UX clarity plus
metadata-only manifest export (Studio PR #155); `metadata_only` entries remain
zero-artifact at the Engine layer.

**Why first:** Establishes the vocabulary and sets expectations before any
behavior ships. Prevents authors from assuming that classifying a field as
`business_key` produces a unique constraint today.

### Phase 2 — `parent_reference` active policy

**Scope:** Engine ingestion + Studio authoring + KS suggestions + proof.
Design contract defined in Section 4.1 of this document.

#### Phase 2a — Engine: active parent_reference cross_entity_exists (first PR)

**Deliverables:**
- Engine accepts `mode: active` for `role: parent_reference` (previously
  rejected for all roles)
- Engine validates the policy block: `target_entity` and `reference_type` are
  required; unsupported flags (`relationship_metadata.enabled: true`,
  `db_foreign_key.enabled: true`) are rejected with clear errors
- Engine synthesizes a `CanonicalRule(type=CROSS_ENTITY_EXISTS)` from an
  `active parent_reference` entry with `cross_entity_exists: true` and
  `reference_type: local`; inserts it into the rule list; existing generation
  path unchanged
- Engine detects and rejects duplicate rule conflicts (explicit rule YAML and
  active identity role both targeting the same `entity.field → target_entity`)
- `mode: active` is **always rejected** for `reference_type: remote`,
  regardless of policy flag values. There is no Engine behavior that can fulfil
  an active remote parent reference in Phase 2a — including the zero-flag case.
  Accepting a no-op `active` remote silently would weaken the
  `active`/`metadata_only` contract. Remote parent references must use
  `mode: metadata_only`.
- No emitter changes; no schema version bump

**Why first:** Unblocks all downstream phases. Uses the existing rule generation
path exactly as designed. No new emitter paths. The manifest model change in
`_validate_identity_roles_contract` is the only code change.

#### Phase 2b — Proof fixture (implements before Studio)

**Rationale for ordering:** The proof validates Engine-generated output before
Studio or KS builds on top of it. Discovering a Phase 2a bug after Studio
authoring exists requires fixes in both Engine and Studio simultaneously.
Finding it in proof before Studio exists is cheaper and cleaner.

**Deliverables:**
- New golden contract test fixture (in Engine repo) demonstrating the full
  Phase 2a loop: `identity_roles` active `parent_reference` entry →
  synthesized `CanonicalRule` → `existsById` check in generated service Java
- Fixture asserts no duplicate rule conflict detection false-positives
- Fixture asserts that `mode: active` + `reference_type: remote` produces a
  validation error, not generated code
- Fixture asserts `mode: metadata_only` produces no artifacts

**Proof lives in Engine, not TestBench.** This is generated-output contract
proof — static assertion against the emitted Java/Flyway artifacts.
TestBench (runtime) validation is a separate concern.

**Why before Studio:** Studio and KS must build on a proven Engine contract.

#### Phase 2c — Studio: authoring and export for active parent_reference

**Scope:** Studio authoring only. No Engine changes. No relationship_metadata
or db_foreign_key controls — those are hidden/disabled in the UI until Phase 2e
Engine support lands.

**Deliverables:**
- Studio Step 6 exposes a policy form for active `parent_reference` export
- Author can set `reference_type: local | remote` and enable
  `cross_entity_exists: true`
- `relationship_metadata` and `db_foreign_key` controls are explicitly hidden
  or greyed out in the Phase 2c UI — they are not configurable until Phase 2e
- Exported manifests satisfy Phase 2a Engine validation (no deferred flags)

**Why after Phase 2b:** Studio authoring requires a proven Engine contract.
Phase 2b proof confirms that contract before Studio depends on it.

#### Phase 2d — KS: parent_reference policy candidate suggestions

**Deliverables:**
- Knowledge Server suggests `parent_reference → cross-entity-exists` policy
  candidates based on DDL FK evidence, OpenAPI path parameters, and field
  catalog entries
- Suggestions appear as candidates; human review in Studio required before
  any `mode: active` export
- KA OFF: Studio manual authoring remains fully functional without KS

**Why after Phase 2c:** KS suggestions feed into Studio's active policy
authoring surface. Studio must have the authoring form before KS can populate
it with candidates.

#### Phase 2e (optional convenience) — Relationship metadata and DB FK

**Track: Advisory by default; optional Engine generation for teams that opt in.**

Phase 2a `existsById` check captures the business-correctness value of
`parent_reference`. JPA relationship annotations (`@ManyToOne`, `@JoinColumn`)
and Flyway FK constraints are architectural preferences that teams have strong
opinions about. Some teams explicitly avoid JPA relationships to sidestep
Hibernate lazy-loading complexity. Phase 2e is optional — not required
completion of the parent_reference story.

**Scope:** Both Engine generation and Studio UI controls ship in the same phase.
Phase 2e is the earliest point where `relationship_metadata.enabled: true` or
`db_foreign_key.enabled: true` is valid in a manifest.

**Engine deliverables:**
- Engine generates `@ManyToOne` / `@JoinColumn` when
  `relationship_metadata.enabled: true` and `reference_type: local`
- Engine generates Flyway `FOREIGN KEY` constraint when
  `db_foreign_key.enabled: true`, `reference_type: local`, and `target_entity`
  is confirmed to exist in the same generated application
- New emitter paths; the full DB FK precondition list in Section 4.1 applies

**Studio deliverables:**
- `relationship_metadata` and `db_foreign_key` controls are unlocked in the
  policy form (were hidden/disabled in Phase 2c)

**Why separate from 2c:** Phase 2c Studio authoring ships only what Phase 2a
Engine supports. Relationship metadata and DB FK require new emitter paths that
are not built in Phase 2a. Exposing those controls in Studio before Engine
support exists would allow authors to set `enabled: true` and receive a
validation error — a confusing failure mode. The controls stay hidden until
the Engine is ready.

See Section 4.1 for the full DB FK preconditions list.

### Phase 3 — `business_key` + `external_reference` Engine generation

**Scope:** Design doc update + manifest extension + Engine generation.
`external_reference` folds into this phase — it uses the same DDL template
as `business_key` and there is no value in a separate phase for two lines
of generation.

**Sequence within Phase 3:**
1. Design PR: settle single-field policy semantics, constraint naming
   convention, nullable behaviour, 409 mapping, and the composite key
   escape-hatch reservation (see Section 4.2)
2. Engine PR: unique constraint + finder + duplicate check generation for
   single-field `business_key`; index + finder for `external_reference`
3. Studio + KS PR: authoring surfaces for both roles

**Engine generation requirements (must be in design PR before Engine PR):**
- `unique_scope` must be explicit in the policy — no default scope
- Constraint names are deterministic and derived from entity + field names;
  author override allowed
- Nullable `business_key` fields emit a warning; authors must opt in explicitly
- Duplicate violation → `409 Conflict` with structured error body
- `external_reference` index is never UNIQUE by default

**Why third:** Well-understood DDL patterns with bounded design surface.
Uses the same generation path as `business_key`; no new emitter paths.

### Phase 4 — `idempotency_key` design (advisory track)

**Track: Advisory — `mode: active` is NOT valid for `idempotency_key`.**
See Section 4.3 for the full rationale.

**Phase 4 scope: design document only. No Engine generation in this phase.**

The purpose of Phase 4 is to settle all policy semantics through a design PR
before any implementation is written. Until a complete, concurrency-correct
implementation is designed and proven, all `idempotency_key` manifest entries
remain `mode: metadata_only`.

**Design PR deliverables:**
- Full policy field specification: `operations`, `replay_mode`, `retention_days`,
  `storage` — all required, no defaults
- Concurrent-duplicate correctness requirement documented: INSERT-first pattern,
  DB UNIQUE constraint as the race-condition boundary, not application code
- Decision on whether to introduce `mode: scaffold_only` for teams that want
  generated DDL + implementation stub (requires its own design if chosen)
- TestBench validation approach: concurrent replay test (two identical requests
  in-flight simultaneously) must be a required proof case before any Engine
  implementation ships

**Engine implementation:** TBD pending design PR approval. Will be a separate
phase once the design is settled and the active contract can be fully satisfied.

**Why fourth:** Idempotency has the largest design surface and the highest
correctness risk of any identity role. Settling the design before writing
Engine code avoids a subtly-wrong implementation in every generated app.

### Phase 5 — `event_id` unique constraint + `correlation_id` advisory docs

**Track split within Phase 5:**
- `event_id` unique constraint → **Engine** (same template as `business_key`)
- `correlation_id` → **Advisory** (Micrometer Tracing guidance, no generation)
- `external_reference` → already delivered in Phase 3

**Cross-service dependencies (must be resolved before Engine implementation):**
- `event_id` active unique policy depends on **cross-service integration Phase A**
  (outbound publisher manifest). Until Phase A lands, keep `mode: metadata_only`.
  See [cross-service-integration-design.md](cross-service-integration-design.md).
- `correlation_id` Kafka header propagation depends on **cross-service
  integration Phase D**. Advisory path (Micrometer Tracing) has no such dependency.

**Deliverables:**
- `event_id`: scoped unique constraint + pre-persist duplicate check
  (generation contingent on cross-service Phase A availability)
- `correlation_id`: advisory documentation PR pointing to Micrometer Tracing
  setup for the generated app; records which field carries the correlation
  identifier so developers can reference it in structured logging
- Studio metadata display for both roles

**Why last:** `event_id` Engine work is blocked on cross-service Phase A.
`correlation_id` advisory docs can ship at any point after Phase 3 stabilises.

---

## 6. Manifest Contract Considerations

### Where to store non-persistence roles

Today the manifest has `identity_overrides` (array of `{entity, persistence_id}`)
and `id_generation_overrides` (array of `{entity, strategy, ...}`). These cover
`persistence_id` only.

**Current state:** The `identity_roles` top-level section already exists in the
manifest schema (`manifest-v2.schema.json`) and in `appbuilder/contracts/manifest.py`
as `IdentityRoleDefinition`. The manifest schema has `additionalProperties: true`
on the `policy` object, so Phase 2a policy sub-fields do not require a schema
version bump. The Pydantic model stores `policy` as `Optional[dict[str, Any]]`.

The `identity_roles` section reached the manifest baseline as an additive
optional field. Future Phase 2a policy fields remain additive within the active
single-dialect manifest `2.0` contract and do not require another version cut.

**Phase 2a illustrative manifest entries:**

```yaml
identity_roles:
  # Phase 2a — local parent reference with exists validation
  - entity: Transaction
    field: accountId
    role: parent_reference
    mode: active
    policy:
      target_entity: Account
      reference_type: local
      validation:
        cross_entity_exists: true
      relationship_metadata:
        enabled: false      # deferred — Phase 2e (optional)
      db_foreign_key:
        enabled: false      # deferred — Phase 2e (optional)

  # Remote parent reference — always metadata_only; mode: active rejected for remote
  - entity: Transaction
    field: externalOrgId
    role: parent_reference
    mode: metadata_only   # active is always rejected for remote references
    policy:
      target_entity: ExternalOrg   # lives in a different service
      reference_type: remote
      # No validation/relationship/FK flags — none are supported for remote today

  # Phase 5 — event_id, metadata_only until Phase 5 ships
  - entity: Transaction
    field: transactionId
    role: event_id
    mode: metadata_only   # no artifacts generated

  # Phase 4 — idempotency_key, metadata_only until Phase 4 ships
  - entity: Payment
    field: idempotencyKey
    role: idempotency_key
    mode: metadata_only   # no artifacts generated
```

The existing `identity_overrides` section remains unchanged and continues to
be the primary mechanism for `persistence_id` export. `identity_roles` is
additive — it does not replace or modify `identity_overrides`.

### Backward compatibility

- `identity_roles` is optional. Manifests without it remain valid and
  generate the same output as today.
- Every role entry must declare a `mode` field. This prevents silent no-op
  generation when a role is not yet supported by the Engine:

  | `mode` value | Engine behaviour |
  |---|---|
  | `metadata_only` | Always accepted. Engine records the classification but generates no artifacts. Studio can display this as "reviewed, not yet active". |
  | `active` | Engine validates that it can fulfil the role + policy combination. If the role or policy is not yet supported, the Engine rejects the manifest with a clear validation error naming the unsupported role. |

  A role entry that omits `mode` is a schema validation error. There is no
  default: authors must choose explicitly. This ensures that Studio exporting
  a Phase 3+ role before the Engine implements it is safe — the author sets
  `mode: metadata_only`, the Engine accepts it without generating artifacts,
  and there is no ambiguity about what happened.

- **`policy` block rules** (tied to `mode`):
  - `mode: metadata_only` — `policy` is optional. If present it is recorded
    as metadata but the Engine generates no artifacts from it.
  - `mode: active` — `policy` is required. The Engine validates that the
    role + policy combination is supported and rejects the manifest with a
    clear error if it is not.

### Schema versioning

`identity_roles` is already present in `manifest-v2` as an optional array
with `additionalProperties: true` on the `policy` object. The Phase 2a policy
sub-fields (`target_entity`, `reference_type`, `validation`,
`relationship_metadata`, `db_foreign_key`) are stored in that open `policy`
object, so no JSON Schema change is required for Phase 2a. Pydantic-level
validation of the policy contents is added to `_validate_identity_roles_contract`
in `manifest.py`. Per the stability policy in [Manifest Schema](../manifest-schema.md),
this is a non-breaking additive change within the single-dialect `2.0`
contract and requires no further version cut.

---

## 7. Ownership

| Component | Responsibility |
|---|---|
| **Studio** | Owns the review UX for all seven roles. Owns manifest export logic. Owns the policy configuration surfaces for each role. |
| **Knowledge Server / Knowledge Assist** | Suggests role classifications and policy recommendations based on upstream spec analysis. Does not auto-approve. |
| **Engine** | Generates deterministic behavior from explicit manifest contract only. Does not infer behavior from role classification. Does not reach back to Studio or KS at generation time. |
| **Generated apps** | Remain standalone, owned by the adopting organization, and runtime-independent of Studio, KS, KA, or any MCP dependency. |
| **Manifest authors / tooling** | Any tool that emits `app-definition.yaml` must include `identity_roles` entries when role policies have been reviewed. The Engine applies the same contract regardless of what produced the manifest. |

---

## 8. Open Questions

These questions must be resolved before implementation of each phase. They do
not block Phase 1 (UX clarity only).

### Q1. Manifest section name and location

Should `identity_roles` be a top-level manifest section (as proposed above),
or should each role's policy attach inline to entity field definitions? Both
approaches have tradeoffs:

- Top-level: clear separation of concerns, easy to review, but requires
  entity+field cross-referencing
- Inline: collocated with field definitions, but makes manifest field
  definitions more complex

**Recommendation:** Top-level, matching the existing `identity_overrides`
pattern.

### Q2. Uniqueness scope model

Business keys and event IDs need a scope for uniqueness. The proposed scopes
are `entity`, `bounded_context`, `tenant`, and `global`. Questions:

- Is `bounded_context` scope well-defined enough when a generated app spans
  multiple aggregate roots?
- Is `tenant` scope relevant for single-tenant deployments?
- Should scope be extensible or a closed enum?

### Q3. Idempotency replay response shape

The `replay_mode` enum proposes `cached_response`, `conflict_409`, and
`success_200_original`. Questions:

- Should `cached_response` return the exact original response body, or is a
  minimal acknowledgment sufficient?
- Should the response include a header indicating it is a replay?
- How does the replay response interact with the evidence trail?

### Q4. FK vs runtime validation vs cross-service reference — RESOLVED

**Resolution (Phase 2 design):**

- The manifest must explicitly declare `reference_type: local | remote`.
  Inference from the entity list is rejected — it is brittle and unreviewed.
  An entity that is present in the manifest today may be moved to a separate
  service later; that structural change should not silently change runtime
  behavior.
- `reference_type: local` → the parent entity is in the same generated app and
  the same database. `cross_entity_exists`, relationship metadata, and DB FK
  are all candidates (subject to individual enablement flags).
- `reference_type: remote` → the parent entity is in a different service. DB FK
  and JPA relationship annotations are rejected with validation errors. Runtime
  exists-check via API client is out of scope for Phase 2 and is explicitly
  noted as a future design concern.
- The Engine does not generate REST client stubs for remote reference validation.
  That is a service orchestration concern, not a manifest-driven generation
  concern.

### Q5. Composite key support — RESOLVED (escape hatch reserved)

**Resolution:** Composite key support is deferred past Phase 3, but the
manifest escape hatch is reserved before single-field implementation begins.

Single-field `business_key` uses an `identity_roles` entry. Composite keys
(unique across multiple fields) must NOT be expressed as multiple independent
`identity_roles` entries — that implies separate per-field constraints, not
a compound constraint.

The future shape is a separate `business_key_policies` section:

```yaml
# Single-field (Phase 3, implemented via identity_roles)
identity_roles:
  - entity: Account
    field: accountNumber
    role: business_key
    mode: active
    policy:
      unique_scope: entity

# Composite key (future — separate section, NOT via multiple identity_roles entries)
business_key_policies:
  - entity: Account
    fields: [sortCode, accountNumber]
    unique_scope: entity
    # Not valid until manifest schema extension is designed and merged.
```

This reservation prevents assumptions hardened by Phase 3 single-field
implementation from blocking composite key manifest design later.
The `business_key_policies` section does not exist yet in
`appbuilder/schema/manifest-v2.schema.json` (the Engine repo's manifest schema).
Any addition requires a schema change to that file. If the project later adopts
a shared published schema contract as an upstream source, the change must be
coordinated there first; until then, `appbuilder/schema/manifest-v2.schema.json`
is the single source of truth for manifest schema in this repo.

---

## Appendix A. Role Vocabulary Reference

Reproduced from
[Entity Identity Role Review Design](entity-identity-role-review-design.md)
Section 5 for convenience. The canonical definition lives in that document.

| Role | Meaning | Current Engine behavior | Phase 2 behavior | Future behavior |
|---|---|---|---|---|
| `persistence_id` | JPA `@Id`, repository identity, route path parameter | Full generation via `identity_overrides` | No change | No change needed |
| `parent_reference` | FK / relationship reference to another entity | PR #138 fail-fast if inferred as persistence_id; `cross-entity-exists` rules require explicit manual authoring — role classification alone does not generate them; `metadata_only` mode accepted, zero artifacts | Phase 2a: `active` + `reference_type: local` + `cross_entity_exists: true` → synthesized `CanonicalRule(CROSS_ENTITY_EXISTS)`, existing generation path. Phase 2b: relationship metadata and DB FK deferred. | Phase 2e: optional `@ManyToOne` / `@JoinColumn`, optional DB FK (explicit opt-in only) |
| `business_key` | Domain-meaningful natural key | `metadata_only` accepted, zero artifacts | No change in Phase 2 | Unique constraint, finder, duplicate check (Phase 3) |
| `event_id` | Upstream event/transaction identifier | `metadata_only` accepted, zero artifacts | No change in Phase 2 | Scoped uniqueness, duplicate detection (Phase 5) |
| `idempotency_key` | Replay/duplicate protection key | `metadata_only` accepted, zero artifacts | No change in Phase 2 | Idempotency guard with full policy (Phase 4) |
| `correlation_id` | Request/workflow tracing identifier | `metadata_only` accepted, zero artifacts | No change in Phase 2 | MDC/header propagation (Phase 5) |
| `external_reference` | External provider identifier | `metadata_only` accepted, zero artifacts | No change in Phase 2 | Index, finder, provider scope (Phase 5) |
