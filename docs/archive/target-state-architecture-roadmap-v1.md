# EdgeForge Target-State Architecture Roadmap v1

> **Historical / non-authoritative.** This target-state planning snapshot is
> archived for reference. Current status and sequencing live in
> [`../enterprise-readiness-roadmap.md`](../enterprise-readiness-roadmap.md),
> [`../README.md`](../README.md), and the live tracker.
>
> **Living roadmap.** Updated 2026-04-15.
>
> This document is the synthesized target-state architecture review for the full
> EdgeForge suite. It intentionally preserves the detailed Claude design review
> points, incorporates the Codex follow-up review adjustments, and is meant to
> become the baseline architecture reference before broader Studio v2, Knowledge
> Server, and LegacyExtractor implementation proceeds.
>
> For the ranked pending-features backlog, see
> [target-state-features-v1.md](target-state-features-v1.md).

## Purpose

EdgeForge is no longer only an Engine generator with an adjacent Studio. The
suite is evolving toward a governed modernization platform for the
enterprise:

```text
legacy docs / copybooks / DDL / BRDs / tickets / OpenAPI / legacy source
    ->
Knowledge Server MCP + LegacyExtractor MCP
    ->
AI-assisted, evidence-backed draft suggestions
    ->
Studio review and pre-populated authoring
    ->
human accept / edit / reject
    ->
approved manifest package
    ->
Engine validation + deterministic generation + compatibility checks
    ->
generated app
    ->
future project evolution support
```

This roadmap defines how to reach that target state **without** breaking the
core EdgeForge principles:

- the manifest remains the single source of truth for generation
- human review remains mandatory
- Engine remains deterministic
- MCP services remain additive and bounded
- `schema_version: "1.0"` stays stable unless future additive evolution truly
  requires a versioned extension

## Current Baseline Assumptions

This roadmap assumes the following current suite baseline:

- EdgeForge Engine and Studio already have a deterministic manifest-driven flow
- Studio currently uses an 8-step governed authoring workflow
- Engine MCP Phase 4 is implemented as a bounded local stdio MCP server
- Knowledge Server MCP Phase 5 is underway in a separate repo and should remain
  separate from Engine MCP
- LegacyExtractor MCP Phase 6 is planned but not yet formally designed
- Engine Kafka archetype work is complete on the Engine side through the merged
  multi-route proof baseline

## A. Executive Conclusion

### Is the target state sound?

Yes. The target state is architecturally coherent and correctly preserves the
non-negotiable EdgeForge properties:

- contract-first modernization
- governed authoring and review
- deterministic generation
- additive manifest evolution
- explicit trust boundaries between suggestion systems and generation

### Is the current roadmap enough?

No. The current roadmap is directionally right but incomplete. Engine, Kafka,
and the Knowledge Server direction are mostly aligned. The real gaps are now in:

- Studio v2 orchestration
- suggestion review and persistence
- evidence traceability after export
- LegacyExtractor design
- post-generation project evolution support

### Biggest architectural risk

The biggest risk is **Studio becoming a second-system effect**: a partially
chat-first, partially wizard-based, partially archetype-specific shell with
different review rules per feature. If that happens, EdgeForge loses the
structured review surface that makes it trustworthy for enterprise modernization.

### Biggest product opportunity

The biggest opportunity is **one project-scoped intelligence workspace per
modernization target**. If EdgeForge can preserve accepted decisions, evidence,
mapping rationale, and requirement history across the project lifecycle, it
becomes institutional memory for modernization programs rather than only a
generator.

## Non-Negotiable Principles

These principles stay locked:

1. **Manifest remains the generation truth**
   - reviewed manifest in, deterministic app out
2. **Studio remains the governed review boundary**
   - AI suggestions can prepare drafts, not publish truth
3. **Knowledge Server and LegacyExtractor remain draft-producing services**
   - separate responsibilities, separate trust boundaries
4. **Engine remains deterministic**
   - no LLM-driven code generation path
5. **Manifest stability is preserved**
   - new concepts should be additive optional extensions where possible
6. **Evidence and rationale stay explicit**
   - not buried inside chat logs or implicit model memory

## B. What Already Aligns Today

These areas already support the target state well.

### Engine and Engine MCP

- [docs/appbuilder-context.md](../appbuilder-context.md)
  anchors Engine as a deterministic generator
- [docs/engine-mcp-design.md](../engine-mcp-design.md)
  keeps the Engine MCP surface bounded to deterministic validation and
  generation
- Engine Kafka work proved additive archetype growth without breaking the
  manifest stability policy

### Manifest policy

- [docs/manifest-schema.md](../manifest-schema.md)
  preserves `schema_version: "1.0"` as the stable contract marker
- additive evolution is already the working policy for pagination, identity
  overrides, ID generation, and Kafka concepts

### Knowledge Server direction

- [docs/knowledge-server-mcp-design.md](../knowledge-server-mcp-design.md)
  already captures the correct foundation:
  - project-scoped document ingest
  - BM25/full-text search
  - Q&A with citations
  - suggestions as drafts only
  - portfolio reuse
  - evidence traceability as a later capability
- the 12-tool vocabulary already covers the intended Phase 5 knowledge scope

### Extension boundaries

- [docs/extension-architecture.md](../extension-architecture.md)
  already keeps the separation between:
  - Engine MCP
  - Knowledge Server MCP
  - LegacyExtractor MCP
- the vendor-neutral agent adapter principle is already aligned with the future
  target state

### Studio review posture

The Studio direction remains fundamentally correct:

- wizard-based structured authoring
- human approval before generation
- manifest preview/review before export
- save/open project support already established as a Studio-owned concept

## C. Gap Analysis

The roadmap gaps are now mostly above the Engine layer.

### Gap 1 — Studio v2 orchestration layer is missing

There is no fully defined architecture for how Studio should orchestrate:

- Engine MCP
- Knowledge Server MCP
- LegacyExtractor MCP
- asynchronous suggestion fetches
- subprocess lifecycle and reconnect behavior

If this stays implicit, separate Studio PRs will invent different integration
patterns for Kafka, Knowledge Server, and later LegacyExtractor work.

### Gap 2 — Suggestion state lifecycle is under-specified

The KS design already includes persisted suggestions with status. What is still
under-designed is:

- who owns suggestion review state during a live Studio session
- how accept/edit/reject writes back durably
- how reopen/reconnect works across Studio save/open cycles
- how accepted, rejected, and edited decisions participate in portfolio reuse

Claude correctly called out the missing decision write-back API. Codex agrees
with the need, but recommends locking the ownership model first and then likely
adding a **batch-oriented decision tool** such as:

- `record_suggestion_decisions(...)`
- or `update_suggestion_statuses(...)`

before hard-coding a single-item `update_suggestion_status(...)` contract.

### Gap 3 — Evidence attachment beyond suggestion time is missing

Knowledge Server citations alone are not enough. EdgeForge still needs a durable
way to answer:

- why this field exists
- which document justified this mapping
- which evidence backed an accepted rule after manifest export

The manifest should **not** absorb evidence metadata. Instead, the suite needs
an explicit sidecar/ledger model that survives:

- suggestion review
- manifest editing
- export
- later project reopen

### Gap 4 — Project workspace / decision ledger is not explicitly designed

This is the biggest Codex addition to Claude's review.

The suite now needs an explicit model for the project workspace that spans:

- Studio project state
- Knowledge Server `project_id`
- accepted/rejected/edited suggestion history
- evidence links
- conflict resolutions
- manifest revision lineage
- rationale notes
- future enhancement workflows

This can be folded into the orchestration design, but it cannot remain implicit.

### Gap 5 — Post-generation evolution mode is absent

The roadmap still reads too much like a pre-generation assistant flow. For real
enterprise modernization, EdgeForge must also support:

- reopening a project months later
- ingesting updated BRDs and requirements
- comparing new evidence against approved manifest history
- impact analysis against downstream contracts and compatibility checks
- explaining prior accepted and rejected decisions

Without this, the suite risks becoming a "fire once" generator instead of a
long-lived modernization workspace.

### Gap 6 — Studio wizard semantics are under-generalized

Studio is still too CRUD- and OpenAPI-centered in the current documentation.
Kafka has already exposed the need for broader step semantics:

- Step 2 must become **upstream contract ingest**, not only OpenAPI ingest
- Step 3 must become **domain-or-route model authoring**
- Step 5 must support REST/file/Kafka downstream contract variants

If Kafka Studio work lands before this generalization, the suite will accumulate
separate mini-wizards.

### Gap 7 — LegacyExtractor is still a bare sketch

LegacyExtractor needs its own real design before implementation begins. The
current sketch is not enough for:

- output contract design
- provenance rules
- confidence model
- error handling for partially parseable legacy sources
- integration with KS and Studio

### Gap 8 — Conflict resolution UX and manifest diff UX are still under-designed

The roadmap needs explicit definitions for:

- how conflicts are presented
- how resolutions are recorded
- whether unresolved conflicts block export or warn only
- how Step 7 shows human-authored vs AI-accepted vs AI-edited content

## D. Studio v2 UX Design

### Design principle: augment, do not replace

The 8-step Studio wizard should remain the governed authoring backbone.
EdgeForge should **not** become a freeform prompt-only or chat-only tool.

Recommended cross-cutting Studio v2 frame:

- **main pane:** step-specific structured authoring form
- **persistent right rail:** `Suggestions`, `Evidence`, `Chat`, `Conflicts`
- **bottom drawer:** `Manifest Diff`, `Decision History`, `Completeness`

That gives the user AI assistance **around** the governed authoring flow rather
than **instead of** it.

### Cross-cutting panels and review mechanics

#### Suggestion panel

Used primarily on Steps 2-6. Every suggestion should show:

- target manifest section/path
- confidence
- origin (`knowledge-server`, `legacy-extractor`, `portfolio-pattern`, etc.)
- citations / provenance
- actions: `Accept`, `Edit`, `Reject`

#### Evidence panel

Shows the supporting citation trail for the currently selected suggestion or
approved field:

- source document
- section / heading / chunk
- snippet
- extraction source if it came from LegacyExtractor output

#### Chat panel

This is for lookup and question-answering, not for primary authoring. It should
help the user ask things like:

- "What did the BRD say about amount handling?"
- "What fields were in the old account verification copybook?"
- "What changed between the two requirement documents?"

#### Conflicts panel

Shows contradictions and unresolved tensions:

- source A vs source B
- recommendation
- user resolution choice
- whether the conflict remains blocking or advisory

#### Manifest diff and decision history

Step 7 and Step 8 should surface:

- approved manifest diff against prior baseline
- provenance class:
  - human-authored
  - AI-suggested and accepted
  - AI-suggested and edited
- unresolved conflicts
- pending suggestions
- low-confidence accepted items

### Page-by-page recommendation for Steps 1-8

#### Step 1 — Project setup / archetype selection / ingest kickoff

Keep:

- app name
- bounded context
- archetype
- target profile
- workspace/output settings

Add:

- "Describe the system" natural-language kickoff
- document upload / ingest kickoff
- Knowledge Server workspace status
- LegacyExtractor source-ingest kickoff for structural artifacts

Output of Step 1 should be:

- Studio project initialized
- project-scoped workspace linked
- initial ingest jobs started
- initial suggestion queue seeded

#### Step 2 — Upstream interface ingest

This step must be generalized now.

- **CRUD:** OpenAPI/sample ingest and upstream operation review
- **passthrough-router:** upstream REST contract ingest
- **kafka-integration:** topic + message schema ingest

Additions:

- suggestions sourced from KS and later LE
- evidence panel showing contract-supporting documents
- confidence markers for inferred upstream operations or fields

This step should no longer be thought of as "the OpenAPI step." It is the
**upstream contract step**.

#### Step 3 — Entities / operations or route model authoring

This step should become **domain-or-route model authoring**:

- **CRUD:** entities, fields, operations
- **passthrough-router:** route model and transform families
- **kafka-integration:** async routes, patterns, correlation config, reply paths

AI role:

- suggest candidate fields
- suggest missing operations or route shapes
- cite why each candidate exists

Human role:

- accept/edit/reject route and model decisions before they become approved draft

#### Step 4 — Handoffs / staging / integration contract authoring

This step remains archetype-aware:

- **CRUD:** staging tables / data handoffs
- **passthrough-router:** handoff or integration contract details
- **kafka-integration:** transform mapping and integration-specific contract data

AI role:

- field catalog prefill
- contract mismatch detection
- staging/mapping suggestions

#### Step 5 — Downstream interface authoring

This step must support multiple transport types under one conceptual frame:

- **CRUD:** downstream file or service handoffs
- **passthrough-router:** downstream REST targets
- **kafka-integration:** downstream topics and reply topics

The right abstraction is **downstream contract authoring**, not a single
transport-specific form.

#### Step 6 — Rules / mappings / legacy notes / conflict resolution

This becomes the richest decision workbench in Studio v2.

It should host:

- rule suggestions
- mapping suggestions
- legacy-extracted candidate rules
- conflict cards
- rationale capture
- accept/edit/reject decisions

Important:

- "legacy notes" should remain possible
- but rationale and decision history should move into a structured decision model

#### Step 7 — Review / completeness / manifest diff / approval

This step needs a real expansion:

- completeness by step and archetype
- unresolved conflict summary
- pending suggestion summary
- evidence coverage summary
- diff against prior approved manifest revision
- manifest provenance view

Step 7 should be the place where the user approves the **manifest snapshot**,
not the place where the system improvises final content.

#### Step 8 — Export / validate / generate / build / run / verify

Keep the current generation flow:

- export reviewed manifest package
- validate via Engine
- generate via Engine
- build / run / verify

Add:

- evidence trail sidecar export
- manifest revision checkpoint
- workspace checkpoint
- compatibility check summary
- "open next revision from this approved baseline" handoff into future project
  evolution

### Archetype-aware step matrix

| Step | CRUD | passthrough-router | kafka-integration |
|------|------|--------------------|-------------------|
| 1 | shared setup + ingest kickoff | shared setup + ingest kickoff | shared setup + ingest kickoff |
| 2 | upstream API ingest | upstream contract ingest | topic + schema ingest |
| 3 | entity + operation model | route model | async route model |
| 4 | data handoffs / staging | integration contract details | transform mapping / contract authoring |
| 5 | downstream interface authoring | downstream target authoring | downstream + reply topic authoring |
| 6 | rules / mappings / conflicts | rules / mappings / conflicts | rules / mappings / conflicts |
| 7 | shared review / diff / approval | shared review / diff / approval | shared review / diff / approval |
| 8 | shared export / build / verify | shared export / build / verify | shared export / build / verify |

## E. Independent MCP Architecture

### Knowledge Server MCP — owns

Knowledge Server should own:

- document ingest and parsing
- structured field catalog creation
- search and retrieval
- Q&A with citations
- rule suggestions
- mapping suggestions
- requirement comparison
- conflict detection
- manifest-shaped draft fragments
- portfolio reuse / domain pattern search

Its current 12-tool vocabulary remains directionally correct.

### Knowledge Server MCP — must not own

Knowledge Server must not own:

- structural source code parsing of copybooks / PL-SQL / legacy Java
- final manifest approval
- code generation
- Engine validation
- Studio workflow authority

### LegacyExtractor MCP — owns

LegacyExtractor should own deterministic structural extraction from legacy
source-like artifacts, especially:

- COBOL copybooks
- PL/SQL
- DDL where deeper structural extraction is needed
- legacy Java and similar source assets

It should produce typed outputs such as:

- extracted schemas
- extracted fields
- extracted rule candidates
- extracted mapping candidates
- provenance and extraction warnings

### LegacyExtractor MCP — must not own

LegacyExtractor must not own:

- project document search and Q&A
- Studio workflow state
- final manifest publication
- code generation
- becoming a vague all-purpose "AI modernization brain"

### Studio — owns orchestration and review

Studio should own:

- user workflow orchestration
- project workspace state
- accept/edit/reject review behavior
- approval checkpoints
- manifest authoring and export

Codex refinement to Claude's wording:

- Studio should remain the **workflow orchestrator and approval boundary**
- direct LE -> KS artifact publishing is acceptable **if** it is explicit,
  typed, provenance-preserving, and still surfaced through Studio review
- Studio should not be reduced to a dumb transport bus, but it should remain the
  governance point

### Engine — owns deterministic generation

Engine continues to own:

- manifest validation
- metadata translation
- deterministic generation
- compatibility checks

### Conceptual data flow

```text
user uploads documents and legacy artifacts in Studio
    ->
Studio routes:
  documents / BRDs / DDL / exports -> Knowledge Server MCP
  copybooks / PL-SQL / legacy Java -> LegacyExtractor MCP
    ->
LegacyExtractor returns typed extraction outputs
    ->
Studio may:
  - present LE outputs directly for review
  - publish selected derived artifacts into Knowledge Server explicitly
    for search / Q&A / portfolio-aware reasoning
    ->
Knowledge Server returns cited suggestions and evidence-backed answers
    ->
Studio review:
  accept / edit / reject
    ->
approved manifest package
    ->
Engine validate + generate
```

## F. "Little LLM per App" Recommendation

### Reframe the concept

The right mental model is **not** "one LLM per app." The right mental model is:

> one project-scoped intelligence workspace per modernization target

The base model remains swappable and shared. The durable asset is the reviewed,
project-specific workspace.

### Recommended memory layers

1. **Base model**
   - general language and reasoning ability
2. **EdgeForge platform knowledge**
   - manifest rules, archetypes, generation constraints
3. **Domain patterns**
   - domain patterns, portfolio patterns, cross-project reuse
4. **Project-specific workspace**
   - documents, extracted artifacts, approved evidence, accepted decisions
5. **Generated app / current implementation state**
   - codebase status and drift from prior approved manifest revisions

### Truth order must be explicit

When sources conflict, the suite should prefer:

1. approved manifest revision
2. accepted decision / evidence ledger
3. generated app code and current implementation
4. extracted artifacts and indexed documents
5. model prior knowledge

This truth ordering is critical. EdgeForge should never blur approved manifest
truth together with vague model memory or stale code drift.

### Examples of future questions this workspace should answer

- "Why does this rule exist?"
- "Which BRD or copybook justified this field?"
- "What changed between the old and new requirements?"
- "Which downstream contracts are affected if I change this field?"
- "Which mappings were accepted versus rejected?"
- "Which tests or compatibility checks should rerun?"
- "How should the next enhancement safely update the manifest?"

## G. MVP-to-Scale Rollout

### Anchor scenario

Use a **payment mediation** scenario as the architecture stress test,
because it exercises:

- contract preservation
- rule and mapping suggestions
- async Kafka patterns
- legacy artifact knowledge
- downstream impact analysis

Early UI proof points can still be validated first on a simpler CRUD flow.

### Recommended rollout

#### MVP 1 — Knowledge foundation

- KS ingest, search, Q&A, citations, field catalog
- Studio uses it as lookup assistance
- no automatic prefill yet

#### MVP 2 — Suggestion cards + governed review

- suggestion cards in Studio
- accept/edit/reject workflow
- no silent manifest mutation

#### MVP 3 — Prefill + manifest diff + evidence traceability

- target manifest sections can be prefilled from approved suggestions
- manifest diff and provenance view added
- evidence sidecar/ledger exported with the manifest package

#### MVP 4 — Studio archetype generalization + Kafka authoring

- step registry and archetype-aware wizard baseline landed
- Kafka Studio authoring added on top of that generalized frame

#### MVP 5 — LegacyExtractor structured drafts

- deterministic extraction outputs flow into the same Studio review pipeline

#### MVP 6 — Post-generation evolution mode

- reopen project workspace
- ingest updated requirements
- compare against existing manifest and evidence history
- propose safe enhancement changes

#### MVP 7 — Portfolio/domain reuse

- search accepted patterns across completed projects
- reuse with citations and provenance, not blind copy

### What to prove first

The first hard proof should be:

- suggestions with citations help users move faster
- accepted vs edited vs rejected decisions persist cleanly
- evidence remains traceable through manifest approval and export

### What to defer

Defer these until the core review/workspace model is proven:

- vector search as a dependency
- fully automated authoring
- generic integration-platform expansion
- LLM-driven code generation
- broad networked MCP deployment

## H. Additional PRs / Design Docs To Add

### Must-add design docs

1. **Studio Archetype Step Registry**
   - shared vs archetype-specific steps
   - how KS/LE panels attach to steps
2. **Studio Orchestration + Suggestion State Model**
   - subprocess lifecycle
   - async fetching
   - review-state ownership
   - reconnection model
   - batch decision write-back API
3. **Project Workspace / Decision Ledger**
   - project identity
   - manifest revision lineage
   - accepted/rejected/edited history
   - rationale and evidence links
4. **Evidence Trail / Sidecar Format**
   - field-path -> decision -> citation linkage
   - export format and audit role
5. **LegacyExtractor MCP Architecture**
   - tool vocabulary
   - output contracts
   - provenance and confidence model
6. **Conflict Resolution UX**
   - resolution choices
   - blocking vs advisory behavior
7. **Post-Generation Evolution Mode**
   - reopen workflow
   - updated requirement ingest
   - safe enhancement proposal model

### Recommended implementation PR themes

1. Studio save/open schema evolution for KS/LE linkage
2. Studio archetype step registry refactor
3. Knowledge Server decision write-back API
4. Studio document/Q&A integration
5. Studio suggestion review experience
6. Step 7 manifest diff + provenance view
7. Step 8 evidence trail sidecar export
8. LegacyExtractor first implementation slice
9. Post-generation workspace reopen / enhancement flow

## I. Redesign Advice Now, Before Kafka + Studio Changes Go Too Far

### What should be generalized now

1. **Generalize Studio step semantics now**
   - Step 2 -> upstream contract ingest
   - Step 3 -> domain-or-route modeling
   - Step 5 -> downstream contract authoring

2. **Define suggestion targeting now**
   - suggestions must target explicit manifest paths/sections
   - not only ad hoc page widgets

3. **Define review-state ownership now**
   - who owns in-session truth
   - who persists decisions
   - how save/open reconnects

4. **Define workspace / decision ledger now**
   - do not leave this as an accidental byproduct of save/open files

5. **Keep evidence out of the manifest**
   - evidence belongs in a sidecar / decision ledger
   - not in the deterministic Engine contract

### What should be explicitly avoided

- letting AI write directly to the final manifest without review
- collapsing KS and LegacyExtractor into one muddy service
- turning Studio into a chat-only interface
- carelessly expanding Engine MCP with non-deterministic tools
- breaking manifest-v1 casually
- turning EdgeForge into a generic integration platform with weak contract
  discipline

## Final Recommendation

The target state is not overreaching. The bigger risk is actually
**under-designing the workspace and review-state layer** while moving quickly on
separate Engine, Kafka, and Knowledge Server tracks.

If the suite locks down:

- Studio step generalization
- suggestion/state ownership
- workspace / decision ledger
- evidence sidecar design
- LegacyExtractor boundaries

then the roadmap can evolve cleanly without betraying the core EdgeForge model.
