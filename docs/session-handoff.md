# Session Handoff

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

> **SUPERSEDED — April 14, 2026 snapshot.** Preserved as a historical
> implementation record. Current baseline context lives in
> [../README.md](../README.md) and
> [docs/appbuilder-context.md](appbuilder-context.md).

**Last updated:** 2026-04-14

## Current State

### Repository

- **Branch baseline:** `origin/main`
- **Main status:** EdgeForge `origin/main` is green through PR `#104`; `v1.5.0` tag was cut at the PR `#103` baseline and documented by PR `#104`
- **Repo:** `santosh-sh/EdgeForge`
- **Studio pair:** EdgeForgeStudio `main` is green through PR `#58`
- **Phase state:** Phase 2 is closed and frozen as EdgeForge v1; Phase 3 hardening is complete; Phase 4 local Engine MCP is implemented
- **Current work type:** Kafka integration archetype design (PR `#105` in review); Phase 5 KS design doc to open in parallel
- **Workflow:** review-first GitHub PR workflow only

### Current Engine Baseline

The v1 freeze point included:

- PR `#68` shared spec-route support logic
- PR `#70` nested upstream response DTO coverage fix
- PR `#71` PascalCase JSON property preservation fix
- PR `#72` stale generated migration cleanup / Flyway duplicate-version fix

Since the v1 freeze, Engine main has completed:

- Phase 3 hardening: `A2`, `A3`, `B4`, `B5`, `B6`, `C8`, `B7`, `A1`, and `C9`
- Phase 4 Engine MCP: local stdio server with exactly seven approved tools
- generated dashboard/test-console improvements for EOD batch actions and CRUD route consistency
- PR `#102` Engine MCP stdio setup and smoke-test documentation

The current Studio baseline includes:

- PR `#41` Build & Run UI
- PR `#42` Step 2 upload hardening
- PR `#46` minimal passthrough-router MVP
- PR `#47` Build & Run port/url/status follow-up polish
- PR `#56` Engine MCP `generate_app` adapter with subprocess fallback
- PR `#57` fallback hardening, Engine Python command selection, and dependency fixes
- PR `#58` reusable MCP proof runner and docs closure

### Proven Outcomes on the Frozen Baseline

- CRUD lane is proven and belongs to EdgeForge v1
- passthrough-router Engine lane is proven and belongs to EdgeForge v1
- Studio-led OBIE rerun is green end to end
- Studio-led 3-entity external application expanded proof is green end to end
- broad external-application scaffold is green through export, generate, build, startup, and health

### Phase 3 Boundary Closed

The broad external-application run exposed the Phase 3 `A3` targets:

- a state-transition write
- a read-only history lookup
- a derived-value read

These drove the preserved custom / non-CRUD operation hardening work and are no longer the next starting point for new implementation threads.

## Current Phase Map

- Phase 2 = EdgeForge v1 closed baseline
- Phase 3 = production quality hardening
- Phase 4 = Engine MCP server
- Phase 5 = Knowledge Server MCP
- Phase 6 = LegacyExtractor MCP

## Completed Phase 3 Order

### P0 Correctness

1. `A2` — date/type propagation hardening in `translation.py`
2. `A3` — first-class preserved custom / non-CRUD operation support

### P1 Baseline Hardening

3. `B4` — audit baseline decision and validation
4. `B5` — ISO-4217 real code emission
5. `B6` — fixed-width padding/truncation using layout spec
6. `C8` — production Postgres datasource profile
7. `B7` — pagination baseline decision

### Design-First Before Code

8. `A1` — transaction/event identity semantics
9. `C9` — numeric/sequence ID strategy

## Architecture Conclusions To Preserve

- `A1` is a real modeling/design gap rooted in `_select_entity_id_field_name()` and needs a design doc first
- `A2` is a metadata type propagation bug in `translation.py`, not a SQL emitter bug
- `A3` is broader than release/update semantics; it is about preserved custom / non-CRUD operations as first-class generated behavior
- `B4` is mechanically small in `catalog.py` but still a baseline decision
- `C9` was larger design work because UUID was the only first-class automatic ID strategy; it is now represented through additive `id_generation_overrides`

## Policies Still Locked

- staged downstream remains deferred
- `manifest-v1` stays stable
- new manifest concepts must be additive optional extensions only
- relevant golden contract tests should be updated in the same PR as each future generator behavior fix

Example:

- when `A2` lands, the affected golden contract should assert `TIMESTAMP` instead of `VARCHAR`

## Downstream Acceptance Target

The historical downstream design and architecture review for this reference use
case remain in the private development archive.

Phase 3 remains accepted against the privately retained external-application v4 baseline generation and verification narrative.

## Version Baseline

The permanent v1 freeze marker remains `v1.0.0` for the Phase 2 completion point.

The second cross-repo baseline is now tagged as `v1.5.0` on both Engine and Studio after the living-doc sync landed and both repos were verified green from their current `main` branches:

- Engine: `422 passed, 1 skipped`
- Studio: `292 passed`

This tag marks the Phase 3 production-hardening + Phase 4 Engine MCP baseline.

## Key Files

| File | Purpose |
|------|---------|
| `README.md` | top-level baseline summary and v1 freeze marker |
| `docs/generation-quality-roadmap.md` | Phase 3 closure record and future hardening notes |
| `docs/a1-identity-semantics-design.md` | A1 design-first proposal for transaction/event identity semantics |
| `docs/c9-id-generation-strategy-design.md` | C9 design-first proposal for numeric/sequence ID generation strategy |
| `docs/current-implementation-sequence.md` | historical execution order across Phases 3-6 |
| `docs/appbuilder-context.md` | current Engine and Studio baseline context |
| `docs/extension-architecture.md` | cross-repo architecture and MCP phase direction |
| `docs/manifest-schema.md` | current manifest-v1 contract and additive evolution policy |
| `appbuilder/metadata/translation.py` | `A1` / `A2` root-cause context |
| `appbuilder/generation/java_emitter.py` | `A3` current generation behavior context |
| `appbuilder/target_profiles/catalog.py` | `B4` audit baseline decision point |
| `tests/golden_contracts/` | golden regression signal location for generator behavior fixes |

## Active Work: Kafka Integration Archetype

PR `#105` (draft): `docs/kafka-integration-archetype-design.md`

- New `kafka-integration` archetype — parallel Engine track, not a Phase 5/6 item
- Kafka PR 2 (manifest schema) starts after PR `#105` merges
- Studio Kafka UI (Kafka PR 6) starts after Engine Kafka PR 3 is stable
- See `docs/kafka-integration-archetype-design.md` for full PR roadmap
- The `TransformMapping` model extension for Kafka also provides the foundation
  for future REST passthrough transformation rules

## Notes for the Next Contributor

- treat Phase 2 and Phase 3 as closed; do not reopen them with new scope
- keep Engine MCP Phase 4 bounded to the approved seven tools unless the design is explicitly revised
- do not add assess, HTTP transport, auth, streaming, resources/prompts, Knowledge Server tools, or LegacyExtractor tools to Phase 4
- Kafka archetype does not expand Phase 4 MCP tools — it is a new archetype, not a new MCP tool
- Phase 5 Knowledge Server MCP design doc should be opened in parallel with Kafka PR 2/3, not after
- keep the roadmap language aligned across Engine and Studio repos
- use design docs first for Phase 5 Knowledge Server MCP and Phase 6 LegacyExtractor MCP before implementation
