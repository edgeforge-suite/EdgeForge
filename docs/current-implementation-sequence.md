# EdgeForge — Implementation Sequence History

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

> **Historical snapshot.** The last full sequence snapshot is 2026-06-09; a bounded
> 2026-08-11 correction removed one delivered Studio B3 item. This file is retained
> for prior-phase and parked-work provenance, not as the current execution plan.
> Current priorities live in the
> [Enterprise-Readiness & Handoff Roadmap](enterprise-readiness-roadmap.md) and the
> generated [Suite Task Tracker](tracker/README.md). References to "current" below
> describe the 2026-06-09 snapshot unless a later date is stated explicitly.

## Snapshot State Summary (2026-06-09)

| Component | State |
|-----------|-------|
| EdgeForge Engine | `origin/main` is green through generated-app test-console Slice 3c, SOAP canonical inbound/outbound MVPs, XML/XSD canonical runtime, fixed-width/CSV inbound trailer reconciliation, and PR `#215` duplicate REST operation DTO collision hardening |
| Proven Engine lanes | CRUD + passthrough-router + `kafka-integration` all belong to the active Engine baseline |
| EdgeForgeStudio | Studio edge-contract export/evidence track verified through PR `#193`; Step 3/Step 6 batching and KA-off performance/docs closeouts are current through Studio PRs `#181`--`#189`; `v3.0.0` is tagged |
| Knowledge Server | `origin/main` verified current through KS PR `#28`; `v1.0.0` is tagged; `identity_role` scope on main |
| TestBench | Current through PR `#26`; `v1.1.0` is tagged; Kafka router runtime proof complete |
| Staged downstream | Explicitly deferred |
| Phase 3 | Production quality hardening complete |
| Phase 4 | Engine MCP local stdio server implemented; Studio uses `generate_app` with subprocess fallback |
| Kafka archetype track | Engine, Studio, KS transform suggestions, and TestBench runtime proof are complete for the current router scope |
| Edge-contract runtime track | File contracts, XML/XSD runtime, SOAP/WSDL foundation/runtime, inbound SOAP canonical `read_by_id`, outbound SOAP canonical `invoke_by_id`, fixed-width/CSV inbound trailer reconciliation, and cross-family Evidence Trail metadata export are implemented/proven for the v1 scope |
| Generated-app test console | ActionCardDescriptor refactor, Tier-3 look-and-feel, family grouping, SOAP cards, coverage/provenance, and input hints + deterministic sample fill are implemented through PRs `#197`--`#203`; packaged-artifact viewer and workflow slices remain backlog |
| Phase 5 | Knowledge Server + Studio UX v3 / broader KA scopes implemented; `v3.0.0` baseline tagged |
| Identity role foundation | All seven roles defined; Studio review slices 1–5 + KS PRs #25–#28 on main; Phase 2a in-flight |
| Design Gates B1–B4 | written, reviewed, and merged on Engine `main` |
| Phase 6 | LegacyExtractor MCP remains design-first; UX v3 Studio attachment refresh needed before coding |

## Shared Baseline

The v1 freeze point locked these merged Engine fixes:

- PR `#68` shared spec-route support logic
- PR `#70` nested upstream response DTO coverage fix
- PR `#71` PascalCase JSON property preservation fix
- PR `#72` stale generated migration cleanup / Flyway duplicate-version fix

Since that freeze, Engine main completed the Phase 3 hardening stack and the bounded Phase 4 Engine MCP server:

- `A2` date/type propagation
- `A3` preserved custom / non-CRUD operations
- `B4` audit baseline + collision guard
- `B5` ISO-4217 validation / SQL / JPA type alignment
- `B6` fixed-width padding/truncation
- `C8` PostgreSQL production datasource profiles and runtime fixes
- `B7` per-operation opt-in offset/limit pagination
- `A1` `identity_overrides`
- `C9` `id_generation_overrides`
- Phase 4 Engine MCP local stdio server with the approved seven-tool surface
- PR `#102` Engine MCP setup, allowed-root, Python 3.10+, and validation-semantics docs

The paired Studio baseline now includes:

- PR `#41` Build & Run UI
- PR `#42` Step 2 upload hardening
- PR `#46` minimal passthrough-router MVP
- PR `#47` Build & Run port/url/status follow-up polish
- PR `#56` Engine MCP `generate_app` adapter with subprocess fallback
- PR `#57` fallback hardening and Engine Python command selection
- PR `#58` reusable MCP proof runner and docs closure
- PR `#61` archetype step registry foundation
- PR `#62` Kafka Studio authoring steps
- PR `#63` Kafka reply-timeout alignment follow-up
- PR `#67` Step 1 Knowledge Workspace foundation
- PR `#68` durable save/open KS linkage and workspace state
- PR `#69` CRUD Step 3 field suggestion review with batched write-back
- PR `#70` Step 7 provenance review, Step 8 `evidence-trail.json` export, and manifest revision tracking
- Studio UX v3 / KA broader-scope implementation through PR `#143`, including:
  - default-OFF Knowledge Assist capability model
  - compact badges, drawers, and full-width Step 3 KA review
  - field, validation, rule, cross-entity rule, mapping, transform, conflict,
    and portfolio review surfaces where deterministic evidence exists
  - KA-applied rule provenance and explicit removal semantics
  - Step 7 Decision History grouping, filtering, and advisory/generated-artifact separation

## What v1 Now Means

EdgeForge v1 is no longer a proof-only checkpoint. The frozen baseline now includes:

- CRUD lane proven and part of the supported baseline
- passthrough-router Engine lane proven and part of the supported baseline
- Studio-led OBIE rerun green end to end
- Studio-led 3-entity external application expanded proof green end to end
- broad external-application scaffold green through export, generate, build, startup, and health

The broad external-application run also exposed the Phase 3 `A3` boundary:

- a state-transition write
- a read-only history lookup
- a derived-value read

Those three operations were the concrete evidence for Phase 3 `A3`.

## Completed v3 Baseline Sequence

The following steps from the previous sequence are **complete**:

1. ~~complete Studio repo docs PR B and KS README PR C~~ — done; Studio PR `#159` merged
2. ~~cut the `v3.0.0` suite baseline tag~~ — done; all four repos tagged
3. ~~treat Engine Kafka router, Studio router authoring, KS router transform suggestions,
   and TestBench runtime proof as complete~~ — complete; TestBench `v1.1.0` tagged
4. ~~treat Studio UX v3 / broader KA scopes as implemented through Studio PR `#143`~~ — done;
   extended through Studio PR `#159` with identity role review slices

Post-v3.0.0 hardening is also complete on `origin/main` (Engine PRs `#141`–`#153`,
identity role Engine/Studio/KS work through PR `#160` / Studio `#159` / KS `#28`,
and the Step-6 cross-entity KA apply-feedback fix in Studio PR `#160`).

## Near-Term Sequence at the 2026-06-09 Snapshot

### Independent decision track

1. **Phase 2a decision** — review `claude/feature/active-parent-reference-phase-2a`;
   decide merge vs hold; do not start Phase 2b without this decision. This
   track is independent of the edge-contract roadmap below and predates the
   strategic pivot.
2. **Phase 2b** — proof fixtures for active `parent_reference` (after Phase 2a merge)
3. **Phase 2c** — Studio authoring surface for active identity roles
4. **Phase 2d** — KS suggestion improvements for active identity roles

### Edge-Contract Expansion (implemented v1 track and future candidates)

This remains the strategic edge-contract track for the suite. See
[Edge-Contract Expansion Roadmap](edge-contract-expansion-roadmap.md) for the
wave model, contract type families, and full rationale.

**Wave 1a — design baseline:**

1. `[DOCS] Edge-Contract Expansion Roadmap` — the strategic anchor
2. `[DOCS] Downstream Handoff Execution Topology Design v1` —
   `docs/edgecontracts/downstream-handoff-execution-topology-design.md`
3. [XML/XSD Contract Support Design v1](edgecontracts/xml-xsd-contract-support-design.md)
   — done
4. [SOAP/WSDL Contract Support Design v1](edgecontracts/soap-wsdl-contract-support-design.md)
   — done

**Wave 1b / implementation family completed on Engine main:**

5. [CSV/Delimited and Fixed-Width File Contract Design](edgecontracts/csv-fixed-width-file-contract-design.md)
   — done; file-contract implementation and runtime ingest/output slices are on main,
   including fixed-width and CSV inbound trailer record-count/sum validation
6. XML/XSD runtime and canonical CRUD runtime — done for explicitly mapped
   supported XML/XSD contracts
7. SOAP/WSDL foundation, inbound endpoint generation, outbound client generation,
   and adapter-only diagnostics — done
8. Inbound SOAP canonical `read_by_id` generation and generated-runtime proof —
   done for CRUD persistence-ID lookup

9. Outbound SOAP canonical `invoke_by_id` generated action/runtime proof —
   done; `POST /soap/outbound/{contractName}/{operationName}` resolves a
   canonical row by persistence ID, renders the SOAP request, invokes the
   generated client, and returns mapped response fields
10. [Generated-App SOAP Operator Dashboard Actions Design](edgecontracts/generated-soap-operator-actions-design.md)
    — implemented via SOAP inbound/outbound action-card descriptors in the
    generated test console
11. [Generated-App Test Console UX Standard](generated-app-standards/generated-app-test-console-ux-design.md)
    — implemented through Slice 3c; Slice 3b packaged-artifact viewer remains
    blocked on artifact packaging/serving design, and Slice 5 workflow + Slice 6
    sweep remain backlog
12. [Edge-Contract Evidence Trail Metadata Design](edgecontracts/edge-contract-evidence-trail-metadata-design.md)
    — design merged in Engine PR `#210` and implemented in Studio export for
    file, XML/XSD, and SOAP/WSDL metadata through Studio PRs `#190`--`#193`,
    preserving Evidence Trail v1.1 shape and avoiding new evidence types

**Current next Engine edge-contract candidates:**

1. Final docs/status closeout after the integrated Studio -> Engine runtime smoke.
2. Optional generated-app console polish, especially sample-fill wording or
   future real package-sample loading.
3. Optional Spring Batch schema-init runtime config polish; the final smoke
   required `--spring.batch.jdbc.initialize-schema=always`.
4. Optional Studio cleanup to prevent or remove empty duplicate REST interface
   export; Engine PR `#215` now prevents duplicate operation DTO overwrite.
5. Future contract family/design tracks: Avro/Schema Registry, MQ/JMS,
   SFTP/object-store delivery, and inbound DB interface tables.

**Final integrated v1 edge-contract smoke:** passed on 2026-06-09 with Studio
SHA `0871844` and Engine SHA `61583fc` (Engine `origin/main` is newer and
includes PR `#215` plus governance/security/docs chores). See
[edge-contract integrated v1 smoke results](test-results/edge-contract-integrated-v1-smoke-2026-06-09.md).
The generated app compiled, ran standalone, and proved REST/OpenAPI coexistence,
fixed-width ingest/output, pipe-delimited CSV ingest/output, XML/XSD
ingest/output, SOAP inbound `read_by_id`, SOAP outbound `invoke_by_id`, staging
handoff generation, batch/output jobs, and file/XML/SOAP Evidence Trail
metadata. Runtime required the non-blocking Spring Batch configuration note
`--spring.batch.jdbc.initialize-schema=always`.

**Wave 1b through Wave 3** and parked scope are detailed in the roadmap doc.

### Other design-first pending (no implementation without explicit design doc approval)

- `docs/generated-app-standards/high-tps-entity-profile-design-v1.md` —
  sibling pending track, independent of edge-contract expansion; required
  before any accumulator-field work
- Phase 2a–2d identity role work (active parent_reference and follow-ups) —
  **parked until edge-contract design + implementation work completes** (see
  issue #167); branch and closed PR #161 remain reference material
- Phase 3 identity role design (business_key / external_reference active mode)
  — **parked until edge-contract work completes**; remains valid production
  correctness work
- Phase 4 identity role design (idempotency_key active mode) — **parked until
  edge-contract work completes**
- LegacyExtractor UX v3 refresh before LE coding begins — gated on a committed
  implementation owner

### General

- Keep Phase 4 Engine MCP bounded; no surface expansion without explicit design revision
- Use the target-state planning docs as the suite-level architecture anchor:
  - [docs/archive/target-state-architecture-roadmap-v1.md](archive/target-state-architecture-roadmap-v1.md)
  - [docs/archive/target-state-sequencing-v1.md](archive/target-state-sequencing-v1.md)
  - [docs/archive/target-state-features-v1.md](archive/target-state-features-v1.md)
  - [docs/edge-contract-expansion-roadmap.md](edge-contract-expansion-roadmap.md)

### Kafka Archetype Sequencing

The Kafka `kafka-integration` archetype was a parallel Engine track,
independent of Phase 5 and Phase 6. That Engine-side sequence is now complete.
It did not expand Engine MCP and did not require Knowledge Server or
LegacyExtractor.

Completed Engine Kafka sequence:

- PR 1: design doc
- PR 2: manifest schema + metadata models
- PR 3: topic-to-topic fire-and-forget generation and proof
- PR 4: request/reply correlation and response transform
- PR 5: retry / DLQ / observability hardening
- PR 7: E2E multi-route scale fixture and MCP dispatch proof
- Studio PR 6 equivalent follow-through on the Studio side:
  - Studio PR `#61` step registry foundation
  - Studio PR `#62` Kafka authoring steps
  - Studio PR `#63` reply-timeout alignment follow-up

Current Kafka follow-up:

- optional formal TestBench `v1.1.0` tag if router runtime proof is promoted as a named TestBench baseline
- later broadening only if new router targets or runtime behaviors are added

See `docs/kafka-integration-archetype-design.md` for the design baseline and
the target-state backlog for the remaining ranked follow-ons.

## Phase Map

### Phase 2 — EdgeForge v1

Phase 2 is closed. The v1 baseline is frozen and should now be treated as the stable CRUD + passthrough-router contract-preserving baseline.

### Phase 3 — Production Quality Hardening

This EdgeForge v2 hardening roadmap is now complete. The completed stack was:

#### P0 Correctness

1. `A2` — date/type propagation hardening in `appbuilder/metadata/translation.py`
2. `A3` — first-class preserved custom / non-CRUD operation support

#### P1 Baseline Hardening

3. `B4` — audit baseline decision and validation
4. `B5` — ISO-4217 real code emission instead of TODO behavior
5. `B6` — fixed-width padding/truncation from layout spec
6. `C8` — production Postgres datasource profile
7. `B7` — pagination baseline decision

#### Design-First Before Code

8. `A1` — transaction/event identity semantics
9. `C9` — numeric/sequence ID strategy

### Phase 4 — Engine MCP Server

Implemented after Phase 3 hardening stabilized the Engine baseline.

Use `docs/engine-mcp-design.md` as the Phase 4 design anchor. Approved tools:

- `validate_manifest`
- `translate_project`
- `generate_app`
- `list_target_profiles`
- `describe_target_profile`
- `list_archetypes`
- `get_manifest_schema`

### Kafka Integration Archetype (Parallel Engine Track)

New archetype `kafka-integration` for Kafka-based async mediation. This is a
parallel Engine code track, separate from Phase 5/6 MCP server work. See
`docs/kafka-integration-archetype-design.md` for detail.

The transform model built for Kafka also provides the foundation for REST
passthrough transformation rules, which reuses the same `TransformMapping`
infrastructure.

### Phase 4 — Kafka Studio Authoring

Studio-side Kafka authoring is also now complete on `main` via PRs `#61`,
`#62`, and `#63`.

The current next step is not more foundational Kafka UI work. It is runtime
validation and adjacent tool hardening.

### Phase 5 — Knowledge Server MCP and Studio UX v3

Separate MCP server, in a separate repo. The current shipped baseline now
includes:

- KS backend implementation through PR `#12`
  - stable `suggestion_id`
  - persisted suggestion `status`
  - `submit_suggestion_decisions(...)`
- Studio PR `#67`
  - Step 1 Knowledge Workspace foundation
- Studio PR `#68`
  - durable save/open KS linkage (`studio_project_schema_version: "1.1"`)
- Studio PR `#69`
  - CRUD Step 3 field suggestion review with batched write-back
- Studio PR `#70`
  - Step 7 provenance review
  - Step 8 `evidence-trail.json` export
  - manifest revision tracking
- KS broader scopes through PR `#23`
  - `fields`
  - `validations`
  - `rules`
  - `cross_entity_rules`
  - `mappings`
  - `transforms`
  - `conflict_resolution`
  - `portfolio_reuse`
- Studio UX v3 / KA broader-scope integration through Studio PR `#143`
  - default-OFF Knowledge Assist
  - Step 3 full-width KA review
  - Step 6 KA-applied rule provenance/removal semantics
  - Step 7 Decision History grouping and filters
  - Evidence Trail v1.1 generated-artifact evidence
- Identity role review integration through Studio PRs `#154`–`#159`
  - identity role KA suggestions consumed from KS `identity_role` scope
  - Step 3 and Step 6 identity role review surfaces
  - `persistence_id` exported as `identity_overrides`; other roles exported as
    `identity_roles` with `mode: metadata_only`
  - full identity KA smoke passed: KS suggests → Studio reviews → exports → Engine generates/builds
- KS post-v1.0.0 identity role hardening through KS PRs `#25`–`#28`

privately retained external-application CRUD/Knowledge Assist manual smoke passed end to end: KA review, export, generate,
build, run, and EOD downstream file output were verified in May 2026.

Post-baseline Phase 5 follow-ons:

- Phase 2a (active parent_reference) — in-flight branch
- KA persistence/reopen hardening
- first-draft / pre-populate Studio authoring from KS suggestions
- no current LLM/provider integration; KS-B5 gates any future provider/model layer

The longer Phase 5 target-state backlog still includes:

- deterministic document readers
- BM25/full-text search for project-scoped legacy docs
- agent-assisted draft rule and mapping suggestions through Studio
- evidence-backed workspace support for future Studio review flows

See [docs/archive/target-state-features-v1.md](archive/target-state-features-v1.md)
for the ranked suite backlog.

### Phase 6 — LegacyExtractor MCP

Planned as a separate MCP server. The next required step is an explicit design
doc before implementation begins:

- COBOL copybook parsing
- PL/SQL and Oracle DDL extraction
- Java legacy code extraction
- draft manifest/rule/mapping generation for Studio review

## Architecture Conclusions That Stay Locked

The following conclusions are preserved from the shared review baseline:

- `A1` was a real modeling/design gap tied to `_select_entity_id_field_name()` and is now represented through additive `identity_overrides`
- `A2` is a real correctness bug in metadata type propagation; the loss occurs in `translation.py`, not `sql_emitter.py`
- `A3` is about preserved custom / non-CRUD operations broadly, not just update/release semantics
- `B4` is mechanically small in `catalog.py`, but still a product baseline decision
- `C9` was larger design work because UUID was the only first-class automatic ID strategy; it is now represented through additive `id_generation_overrides`

## Golden Contract Policy

Relevant golden contract tests should be updated in the same PR as each future generator behavior fix. They are the regression signal, not a deferred cleanup item.

Example:

- a date/type propagation fix should update the affected golden contract to assert `TIMESTAMP` rather than `VARCHAR`

## Manifest Evolution Policy

Engine V2-E is delivered as single-dialect `manifest-v2` / `schema_version: "2.0"` for the CRUD,
passthrough-router, and `kafka-integration` lanes. Studio V2-S and the paired/post-merge V2-X proof
are complete, so the coordinated cut is complete. M5a-S1 now delivers bounded CRUD staging
`run_semantics` recognition and fail-closed validation; M5a-S2 is next.

Rules:

- add new concepts only as optional extensions within the active Engine dialect `2.0`
- continue with M5a-S2 under the approved four-slice sequence; S1 deliberately emits no runtime
  semantics and refuses opted-in generate/plan/apply until S2/S3 are delivered
- the selected cut has no post-cut `1.0` bridge; a further breaking revision needs a separate
  maintainer decision

## Deferred Scope That Remains Deferred

- staged downstream (`Entity -> staging -> downstream`)
- broader semantic manifest redesign beyond the selected 2.0 version cut
- expanding Phase 4 Engine MCP with assess, HTTP transport, auth, streaming, MCP resources/prompts, Knowledge Server tools, or LegacyExtractor tools

## v1 Freeze Marker

The Phase 3 kickoff includes permanently tagging the current Engine baseline:

```bash
git tag -a v1.0.0 -m "EdgeForge v1 — Phase 2 complete baseline"
git push origin v1.0.0
```

## Named Baseline Progression

The second named baseline captured the post-hardening / Phase 4 Engine MCP state:

```bash
git tag -a v1.5.0 -m "EdgeForge v1.5.0 - Phase 3 hardening and Phase 4 MCP baseline"
git push origin v1.5.0
```

The previous documented v2.0.0 suite state was the post-PR-70 suite state where
the bounded field-suggestion-only KS Studio MVP was implemented on `main`, the
manual smoke/proof passed, and the baseline docs/proof cleanup was merged.
TestBench remained on its separate `v1.0.0` baseline.

The `v3.0.0` suite baseline tag is cut:

```bash
git tag -a v3.0.0 -m "EdgeForge v3.0.0 - Studio UX v3 + KA broader scopes + Docker Studio baseline"
```

`v3.0.0` marks the May 2026 suite baseline after Studio UX v3, broader
Knowledge Assist scopes, Evidence Trail v1.1, Docker Studio runtime, Kafka
router Studio/KS/TestBench completion, KS conflict field-level deltas, and the
privately retained external-application CRUD/Knowledge Assist smoke / downstream EOD verification.

Post-v3.0.0 work on `origin/main` (all four repos):

- Engine identity role behavior design and advisory track (PRs `#154`–`#160`)
- Post-baseline generated-app hardening (Engine PRs `#141`–`#153`)
- KS post-v1.0.0 identity role hardening (KS PRs `#25`–`#28`)
- Studio identity role review slices 1–5 (Studio PRs `#154`–`#159`)
- TestBench `v1.1.0` tagged at TestBench PR `#26`

## Phase 3 Acceptance Signal

The historical downstream design and architecture review for this reference use
case remain in the private development archive.

Phase 3 acceptance was anchored by:

1. EdgeForge generates a clean privately retained external-application v4 baseline from the improved Engine
2. privately retained external-application v4 baseline passes its verification checklist
3. the Phase 3 hardening items above are closed without breaking the v1 manifest baseline
