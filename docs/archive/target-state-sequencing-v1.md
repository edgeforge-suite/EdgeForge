# EdgeForge Target-State Sequencing v1

> **Historical / non-authoritative.** This target-state planning snapshot is
> archived for reference. Current status and sequencing live in
> [`../enterprise-readiness-roadmap.md`](../enterprise-readiness-roadmap.md),
> [`../README.md`](../README.md), and the live tracker.
>
> **Living sequencing guide.** Updated 2026-04-15.
>
> This document synthesizes Claude's detailed sequencing review with Codex
> follow-up adjustments. It is the operational companion to
> [target-state-architecture-roadmap-v1.md](target-state-architecture-roadmap-v1.md).
> For the ranked pending-features backlog, see
> [target-state-features-v1.md](target-state-features-v1.md).

## Purpose

The architecture target state is sound, but the suite should not move into
major Studio v2 work without first clearing a small set of design gates.

This sequencing guide answers:

- what can continue in parallel right now
- what must be designed before Studio integration starts
- what should be implemented next
- what can wait until later

## Current Baseline

As of 2026-05-18 (updated from original 2026-04-15):

- Engine `origin/main` is green through PR `#160`, which includes the full
  post-v3.0.0 generated-app hardening stack (PRs `#141`–`#153`)
- Studio `origin/main` is current through PR `#159`; v3.0.0 is tagged
- Knowledge Server is current through KS PR `#28`; v1.0.0 is tagged
- Engine MCP remains bounded and stable at the approved seven-tool surface
- Studio step registry, KS orchestration, Evidence Trail, and project
  workspace / decision ledger (Gates 1–4) are all designed and implemented
- LegacyExtractor design doc exists (`docs/legacy-extractor-phase6-architecture.md`)
  but requires a Studio UX v3 attachment refresh before implementation begins

## Core Sequencing Principle

There are design gates that must be cleared **before** serious Studio Kafka work
or Studio Knowledge Server integration starts.

The most important rule is:

> Do not start Kafka Studio PR 6 or KS Studio integration work until Studio step
> generalization and review-state ownership are designed and approved.

## Design Gates

### Required gates before Studio integration work

| Gate | Design topic | Why it matters | Blocks |
|------|--------------|----------------|--------|
| Gate 1 | Studio archetype step registry | Prevents separate mini-wizards for CRUD, passthrough, and Kafka | Kafka Studio PR 6 and KS Studio PR 5 |
| Gate 2 | Suggestion state model + Studio orchestration | Defines async fetching, subprocess lifecycle, review-state ownership, reconnect behavior, and decision write-back | KS Studio integration and suggestion review work |
| Gate 3 | Evidence trail / sidecar format | Prevents bolted-on provenance after the fact | Step 7 diff/provenance and Step 8 evidence export |
| Gate 4 | Project workspace / decision ledger | Makes save/open, manifest lineage, evidence links, and future evolution mode explicit | durable Studio v2 review workflow |

### Codex refinement

Claude framed the roadmap around three core gates. Codex agrees with those
three and elevates the **project workspace / decision ledger** to an explicit
fourth gate unless it is fully and explicitly folded into Gate 2.

If the team wants only three design docs, Gate 4 may be merged into Gate 2, but
the content itself cannot be skipped.

## What Can Continue In Parallel Right Now

These tracks are safe to keep moving:

1. **Knowledge Server backend-only implementation**
   - ingestion
   - search
   - field catalog
   - suggestions
   - conflict detection
   - internal hardening

2. **Engine living-doc refresh**
   - current state/status docs
   - manifest documentation
   - roadmap alignment docs

3. **LegacyExtractor design preparation**
   - initial design drafting can begin now even if implementation comes later

## What Should Not Start Yet

Do not start these before the gates above are approved:

- Kafka Studio PR 6 on top of the current wizard shape
- KS Studio suggestion review flow
- provenance/diff UI without an evidence model
- any Studio implementation that invents its own ad hoc suggestion-state model

## Recommended Full Sequence

### Phase A — Close and stabilize in-flight tracks

#### Goals

- treat Engine Kafka as feature-complete on the Engine side
- continue KS repo work where it does not require Studio integration
- refresh stale living docs so the suite status is current

#### Deliverables

- Engine Kafka baseline treated as stable for Studio planning
- KS backend track continues independently
- refreshed status docs in EdgeForge

#### Suggested duration

- **1-2 focused days**

This replaces the older "several weeks" style framing. With agent help, this is
mostly closure and alignment work, not a long schedule item.

### Phase B — Design gate sprint

This is the most important architecture investment in the roadmap.

#### B1 — Studio archetype step registry

Recommended doc:

- `docs/studio-archetype-step-registry.md`

Defines:

- shared vs archetype-specific steps
- how CRUD, passthrough-router, and Kafka register steps
- how KS/LE panels attach consistently across step types
- template routing and URL expectations

#### B2 — Studio orchestration + suggestion state model

Recommended doc:

- `docs/studio-ks-orchestration-design.md`

Defines:

- Studio ownership during active sessions
- KS subprocess lifecycle
- async suggestion fetch model
- reconnect behavior
- save/open linkage to KS workspace
- batch decision write-back API shape

#### B3 — Evidence trail / sidecar format

Recommended doc:

- `docs/evidence-trail-design.md`

Defines:

- evidence sidecar schema
- field-path -> decision -> citation linkage
- Step 7 provenance view expectations
- Step 8 export expectations

#### B4 — Project workspace / decision ledger

Recommended doc:

- `docs/project-workspace-decision-ledger-design.md`

Defines:

- project identity
- manifest revision lineage
- review history
- accepted/rejected/edited states
- evidence links
- rationale and conflict resolution storage
- relationship to Studio save/open

#### Additional early outlines

These should start early as design drafts even if implementation comes later:

- `docs/legacyextractor-mcp-design.md`
- `docs/post-generation-evolution-design.md`

#### Suggested duration

- **1 focused design day per doc**
- **1-3 calendar days total** if Claude and Codex are used in parallel

This is the place where AI-agent assistance should compress the schedule the
most.

### Phase C — Studio foundation refactors

Once the design gates are approved, the Studio foundation work can begin.

#### C1 — Save/open schema evolution with KS linkage

Because S1A already exists on Studio `main`, this should be treated as **schema
evolution**, not first-time save/open implementation.

Scope:

- add KS project/workspace linkage
- add review-state placeholders
- add evidence-link placeholders
- bump `studio_project_schema_version`
- define migration behavior

#### C2 — Studio archetype step registry refactor

This should be a structural refactor first, not a feature pile-on.

Scope:

- register CRUD and passthrough through the new model
- prepare Kafka step insertion cleanly
- preserve existing review/build/export behavior

#### Suggested duration

- **10-12 working days**

### Phase D — Parallel Studio enablement

After Phase C, two feature tracks can move in parallel safely.

#### D1 — Kafka Studio authoring

Scope:

- Kafka-specific step content
- topic/schema ingest
- route authoring
- transform mapping authoring

Depends on:

- Gate 1
- Phase C step registry refactor

#### D2 — Knowledge Server Studio foundation

Scope:

- document upload panel
- Q&A panel
- field catalog browser
- `ks_integration.py` adapter

Depends on:

- Gate 1
- Gate 2
- Studio save/open schema evolution
- step registry refactor

#### Suggested duration

- **10-12 working days total per major feature track**

If staffed with Codex/Claude support, these can overlap as long as ownership
boundaries stay clean.

### Phase E — Studio intelligence layer

This is the highest-risk UX implementation phase and should stay tightly scoped.

#### E1 — Suggestion review and conflict handling

Scope:

- suggestion panel
- accept/edit/reject workflow
- conflict cards
- decision write-back to KS

#### E2 — Manifest diff and provenance view

Scope:

- Step 7 diff/provenance view
- unresolved conflict summary
- evidence-backed completeness view

#### E3 — Evidence trail export

Scope:

- Step 8 sidecar export
- workspace checkpoint
- manifest revision checkpoint

#### Suggested duration

- **10-12 working days**

### Phase F — LegacyExtractor MCP

#### Sequence

1. finish the LegacyExtractor design doc
2. implement the first extractor slice
3. wire extractor outputs into the shared Studio review pipeline

#### Suggested duration

- **1 focused design day**
- **10-12 working days for the first implementation slice**

### Phase G — Post-generation evolution mode

#### Sequence

1. finish the post-generation evolution design doc
2. implement project reopen + updated requirement ingest + safe enhancement flow

#### Suggested duration

- **1 focused design day**
- **10-12 working days for the first implementation slice**

## Suggested Timeline Model For Agent-Assisted Delivery

Claude's original sequencing used week-scale placeholders. With active
Claude/Codex design and development support, a more realistic planning model is:

| Phase | Recommended planning assumption |
|-------|--------------------------------|
| design docs / design gates | about **1 focused day each** |
| major implementation phases | about **12 working days each** |
| doc/status refresh / merge stabilization | about **1-2 days** |

This is still a planning model, not a promise, but it is a better fit for the
current agent-assisted working style than defaulting to long multi-week ranges.

## Concrete Implementation Order

1. refresh current-state docs in EdgeForge
2. continue KS backend-only work in parallel
3. write and approve the design gates
4. evolve Studio save/open schema
5. land the Studio step registry refactor
6. add Kafka Studio authoring
7. add KS Studio document/Q&A integration
8. add suggestion review + conflict resolution
9. add provenance/diff + evidence export
10. implement LegacyExtractor
11. implement post-generation evolution mode

## Sequencing Scorecard

| Area | Current status | Action |
|------|----------------|--------|
| Engine | green through PR `#160` + post-baseline hardening `#141`–`#153` | no structural change needed |
| Engine MCP | aligned | keep bounded at approved seven-tool surface |
| Kafka Engine | complete baseline | treat as stable; post-baseline hardening on main |
| Knowledge Server backend | complete through KS PR `#28` | identity_role suggestions and stale-invalidation on main |
| Studio step model | delivered — Gate 1 | archetype step registry implemented; Studio through PR `#159` |
| Suggestion state | delivered — Gate 2 | Studio/KS orchestration design implemented |
| Evidence model | delivered — Gate 3 | Evidence Trail v1.1 implemented; exported by default |
| Workspace / decision ledger | delivered — Gate 4 | project workspace / decision ledger implemented |
| LegacyExtractor design | design exists; needs UX v3 refresh | `docs/legacy-extractor-phase6-architecture.md` written; UX v3 attachment refresh needed before coding |
| Post-generation evolution design | missing | start as design work before implementation |

## The One Thing Not To Skip

Do not skip the design gate sprint.

That small upfront investment prevents three expensive retrofits:

1. Kafka Studio inventing its own wizard path
2. KS Studio integration inventing its own review-state model
3. provenance getting bolted on after save/open and export behavior already harden

## Final Recommendation

The right sequencing answer is **not**:

> finish every active implementation track first, then think about the target
> state

The right answer is:

1. finish and merge the current Engine Kafka work
2. keep KS backend work moving in parallel
3. immediately lock the Studio/workspace design gates
4. only then start major Studio Kafka and KS integration implementation

That sequencing preserves momentum while protecting the suite from the biggest
architectural risk: ad hoc Studio growth without a durable review/workspace
model.
