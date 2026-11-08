> Archived April 2026. Superseded by docs/archive/target-state-features-v1.md.

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

# EdgeForge Generation Quality Roadmap

> **Anchor planning document.** Updated 2026-04-12.

## Purpose

This document records the EdgeForge v2 hardening roadmap that started immediately after the EdgeForge v1 freeze and is now complete.

It is the source of truth for:

- the completed Phase 3 implementation order
- the hardening scope that was closed before Phase 4 MCP
- the design-first items that required architecture docs
- the acceptance signal for closing the phase

## Freeze Point

Phase 2 is now closed and frozen as **EdgeForge v1**.

The v1 Engine freeze point was `origin/main` through PR `#72`, including:

- PR `#68` shared spec-route support logic
- PR `#70` nested upstream response DTO coverage fix
- PR `#71` PascalCase JSON property preservation fix
- PR `#72` stale generated migration cleanup / Flyway duplicate-version fix

The Studio v1-era baseline was green through PR `#47`, including:

- PR `#41` Build & Run UI
- PR `#42` Step 2 upload hardening
- PR `#46` minimal passthrough-router MVP
- PR `#47` Build & Run port/url/status follow-up polish

## What v1 Covers

The frozen v1 baseline now includes:

- CRUD lane proven end to end
- passthrough-router Engine lane proven end to end
- Studio-led OBIE rerun green end to end
- Studio-led 3-entity external application expanded proof green end to end
- broad external-application scaffold green through export, generate, build, startup, and health

## Why Phase 3 Started

The external-application scaffold exposed the next real Engine boundary even though the v1 baseline was green:

- a state-transition write
- a read-only history lookup
- a derived-value read

These were not v1 regressions. They were the evidence that the next work was **generation quality hardening**, especially preserved custom / non-CRUD operations as first-class behavior.

## Current Phase Map

- Phase 2 = EdgeForge v1 closed baseline
- Phase 3 = production quality hardening complete
- Phase 4 = Engine MCP server implemented
- Phase 5 = Knowledge Server MCP
- Phase 6 = LegacyExtractor MCP

## Architecture Review Conclusions To Preserve

### BUG-A1

Transaction/event identity semantics are a real Engine/modeling gap rooted in `_select_entity_id_field_name()` in `appbuilder/metadata/translation.py`.

Decision:

- do not treat this as a quick patch
- use the architecture design doc as the durable record for the implementation
- use `docs/a1-identity-semantics-design.md` as the review anchor for the A1 design-first pass
- keep A1 separate from `C9`: A1 decides which field is the persistence identity; C9 decides how that identity value is generated

### BUG-A2

Date/type loss is a real correctness bug in metadata type propagation.

Decision:

- root cause is in `translation.py`
- focus on `_infer_canonical_type()` and `_load_upstream_field_hints()`
- do not frame this as a `sql_emitter.py` problem because the SQL map is already correct

### BUG-A3

This was framed as first-class support for preserved custom / non-CRUD operations, not as a narrow update/release special case.

The three concrete A3 targets from the broad external-application scaffold are **not the same behavioral type** and require distinct implementation patterns:

| Operation | Category | Required behavior |
|-----------|----------|-------------------|
| Historical state-transition write | state-transition | load-then-mutate semantics, non-CRUD HTTP path and method |
| Historical read-only history lookup | pure read | dedicated controller route, read-only service method, no mutation path |
| Historical derived-value read | computed read | dedicated controller route, derived-value service method, no mutation path |

A3 was not closed until all three categories generated correct controller routes, correct service methods, and correct HTTP path/method assignments.

### GAP-B4

Audit emitter support already exists and enabling it is mechanically small in `appbuilder/target_profiles/catalog.py`.

Decision:

- closed for the current named Spring Boot baselines
- `springboot-standard-enterprise` enables audit emission by default
- `springboot-legacy-compatible` keeps audit emission off by default

Rationale:

- `springboot-standard-enterprise` targets Engine-owned greenfield enterprise schemas where audit columns are part of the expected baseline
- `springboot-legacy-compatible` must preserve compatibility with pre-existing schemas and should not add unrequested audit columns by default
- `B4a` collision hardening is the prerequisite guard that makes the enterprise default safe when business fields already occupy audit column names

### GAP-B5 / GAP-B6 / GAP-C8

These are real baseline-hardening items, but not all are correctness blockers.

Decision:

- these were addressed in the Phase 3 `P1` pass after `A2` and `A3`

### GAP-B7

Pagination is a baseline decision, not just a hardening item.

Decision:

- closed for Phase 3 with pagination **off by default**
- support additive per-operation opt-in via `pageable: true`
- first supported mode is offset/limit pagination using Spring Data `Pageable`
- cursor pagination, sort-key declaration, filtering, and total-count suppression remain future design items
- passthrough-router remains unaffected because it is stateless and repository-free

### GAP-C9

Numeric/sequence ID strategy is larger design work than originally estimated.

Decision:

- the original Engine had no first-class automatic numeric ID strategy beyond UUID
- use `docs/c9-id-generation-strategy-design.md` as the review anchor for the C9 design-first pass
- keep C9 separate from `A1`: A1 decides which field is the persistence identity; C9 decides how that identity value is generated
- C9 is now represented through additive `id_generation_overrides`

## Completed Phase 3 Priority Stack

### P0 Correctness

1. `A2` — date/type propagation hardening in `translation.py`
2. `A3` — first-class preserved custom / non-CRUD operation support

### P1 Baseline Hardening

3. `B4` — audit baseline decision and validation
4. `B5` — ISO-4217 real code emission instead of TODO behavior
5. `B6` — fixed-width padding/truncation using layout spec
6. `C8` — production Postgres datasource profile
7. `B7` — pagination baseline decision

### Design-First Before Code

8. `A1` — transaction/event identity semantics
9. `C9` — numeric/sequence ID strategy

## Historical Phase 3 PR Order

Phase 3 used small reviewable PRs in this order:

1. `A2` fix PR with matching golden contract updates
2. `A3` fix PR with focused regression coverage for preserved operations
3. `B4` decision and collision-guard PRs
4. `B5`, `B6`, `C8`, and `B7` as focused hardening PRs
5. `A1` design and `identity_overrides` implementation
6. `C9` design and `id_generation_overrides` implementation

## Golden Contract Test Policy

Relevant golden contract tests should be updated in the **same PR** as each future generator behavior fix.

This is the required regression signal.

Example:

- when `A2` lands, the relevant golden contract must assert `TIMESTAMP` instead of `VARCHAR`

Do not treat golden-contract updates as a later cleanup PR.

The original A2 note about adding a date/timestamp golden-contract signal is closed with the A2 implementation.

## Manifest Evolution Policy

`manifest-v1` remains stable for the current CRUD + passthrough-router baseline.

Rules:

- no breaking changes to existing `schema_version: "1.0"` packages
- new concepts must be optional and additive
- evolve future concepts in a `manifest-v1.1` style only

## Deferred Scope That Remains Deferred

- staged downstream as an active baseline requirement
- breaking manifest redesign
- implementation work on `A1` before the design doc
- implementation work on `C9` before the design doc

## v1 Freeze Marker

The permanent marker for the EdgeForge v1 freeze point is:

```bash
git tag -a v1.0.0 -m "EdgeForge v1 — Phase 2 complete baseline"
git push origin v1.0.0
```

**Sequencing:** the tag must be applied to the `main` merge commit of the Phase 3 kickoff docs PR. No Phase 3 implementation PRs should open before the tag is applied. If the tag is delayed, it must still target the same merge commit — not a later commit on `main`.

## Phase 3 Acceptance Target

The downstream reference use case is:

- the historical downstream design and architecture review retained in the private development archive

Phase 3 acceptance is anchored by EdgeForge generating a clean **privately retained external-application v4 baseline** and that downstream repo passing its v4 verification checklist.

## What This Roadmap Does Not Authorize

This roadmap is a closure record and future-reference document.

It does not itself authorize:

- generated-app repo changes
- breaking manifest changes
- expanding Phase 4 Engine MCP beyond the approved seven local stdio tools
