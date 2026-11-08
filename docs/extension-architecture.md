# EdgeForge Extension Architecture

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

> **Living document.** Updated 2026-04-18. This is the cross-repo architecture
> source of truth for EdgeForge Engine, EdgeForgeStudio, and the planned MCP
> phases.

## Purpose

This document defines the extension points, companion tools, and integration interfaces beyond the core EdgeForge generator.

Rule:

- define interfaces first
- keep Engine deterministic
- compose adjacent capabilities through MCP

## Current State

| Component | Status | Repo |
|-----------|--------|------|
| EdgeForge Engine | `origin/main` includes the merged Kafka archetype proof baseline in addition to the closed Phase 2/3 work | `santosh-sh/EdgeForge` |
| EdgeForgeStudio | 8-step wizard, S1A save/open, step registry, Kafka authoring, and Engine MCP `generate_app` integration are already on `main` | `santosh-sh/EdgeForgeStudio` |
| Phase 3 | Production quality hardening for EdgeForge v2 | complete |
| Phase 4 | Engine MCP local stdio server | implemented |
| Kafka Engine track | additive async archetype implementation | complete on Engine and Studio side; runtime smoke and TestBench follow-ups remain |
| Phase 5 | Knowledge Server MCP | backend complete in separate repo; Studio integration next |
| Phase 6 | LegacyExtractor MCP | design-first; architecture doc still required before implementation |

## Shared Architecture Baseline

The frozen v1 baseline now includes:

- CRUD generation as a proven lane
- passthrough-router generation as a proven lane
- Studio-led OBIE rerun green end to end
- Studio-led 3-entity external application expanded proof green end to end

The next exposed Engine boundary was **generation quality hardening**, especially:

- `A2` type propagation correctness
- `A3` preserved custom / non-CRUD operation support

That is why the sequence inserted Phase 3 hardening before the MCP phases. Phase 3 is now complete, and Phase 4 wraps the deterministic Engine as a local stdio MCP server.

## Locked Scope Notes

- staged downstream (`Entity -> staging -> downstream`) remains explicitly deferred
- the active baseline remains canonical-as-hub
- The coordinated manifest cut is complete: V2-E establishes the single-dialect `2.0` Engine
  contract, V2-S makes Studio export `2.0`, and paired-branch plus post-merge V2-X passed. New
  concepts remain additive within that active dialect; any further breaking revision requires a
  separate maintainer decision.

## Current Integration Pattern

Studio currently keeps EdgeForge Engine access behind the `appbuilder_integration.py` boundary.

For Phase 4, Studio routes `generate_app` through Engine MCP with subprocess fallback. Assess, validation, and local generated-app Build/Run remain on their existing Studio paths unless a later design explicitly expands the Engine MCP contract.

## Phase Map

### Phase 3 — Production Quality Hardening

This phase happened inside the Engine before new service boundary work.

Completed stack:

1. `A2` date/type propagation hardening
2. `A3` first-class preserved custom / non-CRUD operation support
3. `B4` audit baseline decision and validation
4. `B5` ISO-4217 real code emission
5. `B6` fixed-width padding/truncation using layout spec
6. `C8` production Postgres datasource profile
7. `B7` pagination baseline decision
8. `A1` transaction/event identity semantics via `identity_overrides`
9. `C9` numeric/sequence ID strategy via `id_generation_overrides`

Acceptance target:

- generate a clean privately retained external-application v4 baseline
- pass the privately retained external-application v4 baseline verification checklist

### Phase 4 — EdgeForge Engine MCP Server

Phase 4 wraps the deterministic Engine as a local stdio MCP server.

Use `docs/engine-mcp-design.md` as the Phase 4 design anchor. Approved tools:

- `validate_manifest`
- `translate_project`
- `generate_app`
- `list_target_profiles`
- `describe_target_profile`
- `list_archetypes`
- `get_manifest_schema`

### Phase 5 — Knowledge Server MCP

This is the domain-scoped legacy-document access layer.

Directionally approved capabilities:

- deterministic document readers
- document cataloging
- BM25/full-text project-scoped search
- structured inputs for draft rule and mapping suggestions in Studio

Backend implementation is now complete enough to treat Studio integration as
the active next suite slice.

### Phase 6 — LegacyExtractor MCP

This is the source-code extraction companion.

Planned capabilities:

- copybook extraction
- PL/SQL and DDL extraction
- Java legacy extraction
- draft manifest, rule, and mapping generation for Studio review

Status notes:

- LegacyExtractor remains design phase only; no code baseline exists yet
- the next required step is
  `docs/legacy-extractor-phase6-architecture.md`
- PL/SQL extraction is the intended first-value slice

## Design Decision: Knowledge Server over RAG

The planned Knowledge Server still follows the earlier architecture choice:

- deterministic readers for structured content
- BM25/full-text search for unstructured docs
- agent reasoning on top of retrieved source material

Vector search remains a possible later enhancement, not a Phase 5 prerequisite.

## Trust Boundary

The trust boundary does not change across the upcoming phases:

- Knowledge Server and LegacyExtractor produce drafts only
- Studio remains the human review boundary
- the manifest remains the single source of truth
- the Engine remains deterministic: reviewed manifest in, generated app out

## System Composition

```text
LegacyExtractor MCP (Phase 6) ----\
                                   \
Knowledge Server MCP (Phase 5) ----- > EdgeForgeStudio -> reviewed manifest/package
                                     /
EdgeForge Engine MCP (Phase 4) <----/
           ^
           |
   EdgeForge Engine core
   quality-hardened in Phase 3
```

## Vendor-Neutral Agent Adapter

The vendor-neutral adapter decision remains in force for the future agent-assisted phases:

- Studio, Knowledge Server, and LegacyExtractor should call a stable adapter interface
- providers remain swappable
- outputs must validate against explicit schemas
- no vendor-specific runtime dependency should leak into EdgeForge or generated apps

## MCP Interface Direction

### Engine MCP

The Engine MCP should expose deterministic generation and validation tools only.

Expected interface shape:

- `validate_manifest({ manifest_path })`
- `translate_project({ manifest_path })`
- `generate_app({ manifest_path, output_dir })`
- `list_target_profiles({})`
- `describe_target_profile({ profile_name })`
- `list_archetypes({})`
- `get_manifest_schema({ schema_version? })`

### Knowledge Server MCP

The canonical Phase 5 tool vocabulary is defined in `docs/knowledge-server-mcp-design.md`.
That document supersedes the earlier sketch below.

The approved 12-tool surface for Phase 5:

- `ingest_document`
- `list_documents`
- `read_document`
- `search_documents`
- `ask_document`
- `read_field_catalog`
- `suggest_rules`
- `suggest_mappings`
- `compare_requirements`
- `detect_conflicts`
- `prefill_manifest_section`
- `search_portfolio`

Earlier sketch entries that are retired:

- `read_copybook` → belongs to Phase 6 LegacyExtractor (`extract_copybook_fields`)
- `read_table_ddl` → covered by `ingest_document` (`doc_type: "ddl"`) + `read_field_catalog`

### LegacyExtractor MCP

Expected initial tools:

- `extract_rules`
- `extract_fields`
- `extract_copybook`
- `generate_draft_manifest`

## Build Sequence

| Phase | What | Depends On | Delivers |
|-------|------|-----------|----------|
| v1 closed baseline | CRUD + passthrough-router proof closure | merged Phase 2 fixes | EdgeForge v1 freeze |
| Phase 3 | production quality hardening | v1 freeze | stable v2-quality Engine baseline |
| Phase 4 | Engine MCP server | stable Phase 3 baseline | MCP transport for Studio and CI |
| Kafka Engine track | additive async archetype | stable manifest policy + Engine emitter work | proven `kafka-integration` baseline |
| Phase 5 | Knowledge Server MCP | Engine MCP pattern + stable manifest policy | project-scoped doc intelligence |
| Phase 6 | LegacyExtractor MCP | stable manifest policy + review workflow | draft extraction pipeline |

The next suite-level planning anchors are:

- [docs/archive/target-state-architecture-roadmap-v1.md](archive/target-state-architecture-roadmap-v1.md)
- [docs/archive/target-state-sequencing-v1.md](archive/target-state-sequencing-v1.md)
- [docs/archive/target-state-features-v1.md](archive/target-state-features-v1.md)

## What This Architecture Does Not Change

- EdgeForge remains contract-first
- generated apps remain standalone Spring Boot applications
- the manifest remains the single source of truth
- human review remains mandatory for AI-drafted content
- staged downstream remains deferred from the active baseline

## Repository Layout Direction

```text
EdgeForge/
  appbuilder/
    mcp/          # Engine MCP adapter implemented in Phase 4
    knowledge/    # possible Phase 5 implementation area if co-located

EdgeForgeStudio/
  app/
  app/integrations/

LegacyExtractor/
  extractors/
  mcp/
```

## Open Questions

These remain open for later phases, not for the current docs/status PR:

1. Engine MCP network transport beyond local stdio, if ever needed
2. Knowledge Server DB connectivity: direct legacy DB access or exported artifacts only?
3. LegacyExtractor confidence handling in Studio review flows
4. Retrieval upgrades beyond BM25 if later scale demands them
