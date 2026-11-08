# EdgeForge Target State Features v1

> **Historical / non-authoritative.** This target-state planning snapshot is
> archived for reference. Current status and sequencing live in
> [`../enterprise-readiness-roadmap.md`](../enterprise-readiness-roadmap.md),
> [`../README.md`](../README.md), and the live tracker.
>
> **Living backlog.** Updated 2026-05-18.
>
> Source of truth for pending and planned features across the full EdgeForge
> suite.
>
> For architecture direction see:
> [target-state-architecture-roadmap-v1.md](target-state-architecture-roadmap-v1.md)
>
> For implementation order and gates see:
> [target-state-sequencing-v1.md](target-state-sequencing-v1.md)
>
> Feature-specific deep design lives in the linked per-feature docs.

## Suite Baseline (May 2026)

### Engine

The Engine baseline on `main` includes:

- CRUD archetype
- `passthrough-router` archetype
- `kafka-integration` archetype:
  - fire-and-forget
  - request/reply
  - retry / DLQ
  - observability
  - four-route PaymentMediationHub E2E generation proof
  - router/orchestrator request and response path inside the existing Kafka lane
- all seven approved Engine MCP tools
- downstream fixed-width file-order harness alignment through Engine PR `#135`
- target-state design gates B1-B4:
  - Studio archetype step registry
  - Studio / KS orchestration
  - evidence trail design
  - project workspace / decision ledger design

### Studio

The Studio baseline on `main` includes:

- governed 8-step wizard
- CRUD authoring flow
- `passthrough-router` authoring flow
- Kafka authoring flow for topic/schema, route, and transform steps
- S1A file-based save/open project
- archetype step registry foundation
- Engine MCP `generate_app` integration
- Studio UX v3 Knowledge Assist capability model, default OFF
- compact KA badges/drawers and full-width Step 3 KA Review
- Step 3 field/validation review with no-op classification and batch staging
- Step 6 KA rule and cross-entity rule review with ownership/removal semantics
- Step 7 Decision History grouped into generated artifact decisions, advisory
  reviews, and current Step 6 rules
- Evidence Trail v1.1 export for accepted/edited generated-artifact decisions
- Docker Studio runtime and generated-app proxy support

### Knowledge Server

The Knowledge Server baseline includes:

- deterministic suggestion scopes for `fields`, `validations`, `rules`,
  `cross_entity_rules`, `mappings`, `transforms`, `conflict_resolution`, and
  `portfolio_reuse`
- separate MCP server boundary preserved
- wire protocol verified through real stdio subprocess smoke tests
- Kafka router transform suggestions
- Oracle DDL ingest and evidence-summary cleanup
- conflict-resolution field-level structured deltas
- deterministic SQLite FTS5/BM25 retrieval; optional AI remains future/off by default

### LegacyExtractor

LegacyExtractor remains design-first:

- no implementation on `main`
- Phase 6 architecture doc exists, but needs a Studio UX v3 / KA broader-scope refresh before coding begins
- PL/SQL extraction is the planned first-value slice

### TestBench

The TestBench baseline includes:

- v0.1 scaffold in a separate repo
- passthrough and Kafka validation focus
- simulated and real-app-connected execution modes
- Redpanda / Docker Compose local runtime setup
- Kafka router runtime closeout smoke through TestBench PR `#25`

## Implemented Post-v3.0.0 (On main)

| Feature | Implemented via | Notes |
|---|---|---|
| Generated app quality gate hardening | Engine PRs `#141`–`#153` | CRUD fixed-width/temporal, Kafka router publish/correlation, DTO/list fidelity, schema validation, QG fixtures, EOD/batch, UUID DDL, CRUD UI routes, staging run identity, duplicate-ID guard. Roadmap PRs 1–8 complete. |
| Studio / KA identity role review (slices 1–5) | Studio PRs `#154`–`#159`, KS PRs `#25`–`#28`, Engine PRs `#154`–`#160` | All seven identity roles defined. KS `identity_role` suggestion scope live. Full identity KA smoke passed May 2026. Phase 2a (`parent_reference` active mode) in-flight on feature branch. |

## Edge-Contract Expansion

> See [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md)
> for full strategic context, contract type families, and waves.

The next strategic design track. Wave 1a is docs-only design work; no
implementation begins until the relevant design doc lands and is reviewed.

| Wave | Item | Type | Priority | Status |
|---|---|---|---|---|
| **1a** | [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md) | design (anchor) | P0 | Done |
| **1a** | [Downstream Handoff Execution Topology Design v1](../edgecontracts/downstream-handoff-execution-topology-design.md) | design | P0 | Done |
| **1a** | [XML/XSD Contract Support Design v1](../edgecontracts/xml-xsd-contract-support-design.md) | design | P0 | Done |
| **1a** | [SOAP/WSDL Contract Support Design v1](../edgecontracts/soap-wsdl-contract-support-design.md) | design | P0 | Done |
| 1b | [CSV/Delimited and Fixed-Width File Contract Design](../edgecontracts/csv-fixed-width-file-contract-design.md) | design | P1 | In review |
| 1b | Fixed-width inbound (symmetrical) | implementation (after design) | P1 | Pending |
| 1b | Inbound DB interface tables | implementation | P1 | Pending |
| 1b | Kafka Avro / Schema Registry in + out | design + implementation | P1 | Deferred (after file contracts + XML/SOAP impl) |
| 1b | Outbound REST client + control/trailer files | implementation | P1 | Pending |
| 2 | PL/SQL package spec ingester (signatures only) | design + implementation | P2 | Pending |
| 2 | LegacyExtractor UX v3 refresh + Phase 6 first slice | design (gated on owner commitment) | P2 | Pending |
| 2 | COBOL copybook ingest (via LE) | implementation | P2 | Pending |
| 2 | IBM MQ / JMS in + out | design + implementation | P2 | Pending |
| 2 | SFTP delivery + control-file linkage | design + implementation | P2 | Pending |
| 2 | ISO 20022 profiles (layered on XSD) | design + implementation | P2 | Pending |
| 2 | External tool contract pack export | design + implementation | P2 | Pending |
| 3 | SWIFT MT (own parser) and SWIFT MX | future | P3 | Deferred |
| 3 | Kafka Protobuf in + out | future | P3 | Deferred |
| 3 | gRPC / Protobuf | future | P3 | Deferred |
| 3 | Object-store delivery (in + out) | future | P3 | Deferred |
| 3 | Stored procedure outbound adapter | future | P3 | Deferred |
| 3 | Data warehouse / analytics feed packs | future | P3 | Deferred |
| **Parked** | GraphQL | — | — | Parked indefinitely; enterprise modernization is rarely GraphQL |
| **Parked** | XBRL / regulatory reporting output | — | — | Parked; out of EdgeForge's lane |
| **Parked** | Oracle Forms UI generation | — | — | Parked; Oracle Forms KS-ingestible as evidence only |
| **Parked** | CDC / outbox as edge-contract work | — | — | Belongs to cross-service integration track |

### Sibling pending tracks (independent of edge-contract expansion)

- **High-TPS entity profile design** — required before any accumulator-field
  or high-TPS generation work begins. Sibling track, not part of edge-contract
  expansion. Design doc:
  `docs/generated-app-standards/high-tps-entity-profile-design-v1.md` (pending).
- **Downstream handoff topology** is listed under Wave 1a above; it is the
  first substantive edge-contract design PR.

## Pending Features

| Pending Feature | Planned Phase or PR# | Current Priority | Recommended Priority | Complexity | Change Repo | Brief description |
|---|---|---:|---:|---|---|---|
| Phase 2a — active parent_reference | `claude/feature/active-parent-reference-phase-2a` | **Parked** | Parked | S-M | Engine | Active `parent_reference` with `cross_entity_exists` synthesis. Intentionally parked until edge-contract design + implementation work completes (see issue #167). Branch and closed PR #161 remain reference material. |
| Phase 2b — parent_reference proof fixtures | After Phase 2a | **Parked** | Parked | S | Engine + Studio | Proof fixtures for active `parent_reference`. Parked behind Phase 2a. |
| Phase 2c — Studio active identity role authoring | After Phase 2b | **Parked** | Parked | M | Studio | Studio authoring surface for active identity role modes. Parked behind Phase 2a. |
| Phase 2d — KS identity role suggestion improvements | After Phase 2c | **Parked** | Parked | M | KS | KS suggestions for active identity role modes. Parked behind Phase 2a. |
| Phase 3 identity role design — business_key / external_reference active | Design-first; **parked until edge-contract work completes** | Parked | Parked | M | Engine + Studio | Active mode for `business_key` and `external_reference`. Valid production correctness work; parked, not low-value. Needs design doc before implementation. |
| Phase 4 identity role design — idempotency_key active | Design-first; **parked until edge-contract work completes** | Parked | Parked | M | Engine + Studio | Active mode for `idempotency_key`. Valid production correctness work; parked, not low-value. Needs design doc before implementation. |
| KA persistence/reopen hardening | Post-v3 baseline | P1 follow-up | P1 | M | Studio + KS | Hybrid Studio JSON snapshots plus live KS workspace recovery, workspace health probe, citation snapshots, and evidence fallback modes. |
| KS pre-populate Studio first-draft authoring | Phase 5 post-baseline | P2 | P2 | M | Studio + KS | Use approved suggestions to prefill manifest-shaped sections and accelerate first-pass Studio authoring. |
| CRUD cross-entity / business-logic rule engine | `docs/crud-cross-entity-rules-design.md` | Shipped/current contract reference | P2 hardening | M | Engine + Studio | Cross-entity field rules are implemented for `cross-entity-field-check`, `cross-entity-field-compare`, and `cross-entity-field-in`; future work is hardening and broader rule expansion. |
| D10 derived read models / computed-read semantics | `review-feedback-future-notes.md` (#75/#77) | P3 future | P3 | L | Engine | Add real derived-read/query semantics for computed reads instead of placeholder or repository-backed fallbacks. |
| D10 predicate-aware filtered query generation | `review-feedback-future-notes.md` (#87) | P3 future | P3 | M-L | Engine | Support filtered list/query generation for `listTransactionsByAccount(accountId)` instead of `findAll`. |
| LegacyExtractor Phase 6 UX v3 refresh | `docs/legacy-extractor-phase6-architecture.md` | P3 design refresh | P3 | M | Engine docs | Refresh the existing LE design for Studio UX v3, KA broader scopes, decision ledger, and future KS-B6/`le_candidate` integration before LE implementation. |
| LegacyExtractor PL/SQL extraction | Phase 6 first-value slice | P3 future | P3 | L | LegacyExtractor | Parse PL/SQL procedures/functions/packages/table access and turn them into structured rule/service-logic candidates. |
| High-TPS entity profile options | No dedicated design doc yet | P3 future | P3 | L | Engine | Add optional generation modes for high-write entities: atomic SQL update or append/event-oriented persistence strategies. Needs new design doc: `docs/high-tps-entity-profile-design.md`. |
| Java emitter maintainability refactor for query expansion | `review-feedback-future-notes.md` (#77) | P4 prep | P3 prep | S | Engine | Refactor duplicated read/list emitter logic before D10 query/read-model work. Do this before items 9-10. |
| Studio entity-type selector | Manifest-v1.1-style wizard addition | P4 | P4 | S-M | Studio | Surface master record vs transaction/event authoring once Engine A1 semantics are exposed in Studio. |
| Studio ID strategy panel | Manifest-v1.1-style wizard addition | P4 | P4 | M | Studio | Let authors choose UUID / sequence / composite style once Engine C9 is exposed cleanly. |
| Studio unique / idempotency key toggle | Future manifest-v1.1-style addition | P4 | P4 | S | Studio + Engine | Add field-level unique/idempotency controls after the Engine unique-constraint contract exists. |
| REST passthrough transform rules using Kafka transform model | Passthrough follow-up | P4 | P4 | M | Engine | Reuse the richer Kafka `TransformMapping` model for REST passthrough transform/enrich scenarios. |
| Engine MCP helper tool adoption in Studio | Phase 4 optional follow-up | P4 | P4 | S-M | Studio + Engine | Consume `list_target_profiles`, `describe_target_profile`, `get_manifest_schema`, and `translate_project` in bounded Studio flows. |
| LegacyExtractor additional extractors | Phase 6 later slices | P4 | P4 | L | LegacyExtractor | COBOL copybook, legacy Java, and other extractor types after PL/SQL-first is stable. |
| LE to KS push integration | Phase 6 cross-repo follow-up | P4 | P4 | S | LE + KS | Push extracted artifacts into KS for search/Q&A/reuse while preserving provenance. |
| Package re-import from `app-definition.yaml` | Save/open later follow-up | P5 | P5 | M | Studio | Best-effort reconstruction from exported manifest packages. |
| Autosave / dirty-state UX | Save/open later follow-up | P5 | P5 | S | Studio | Better editing ergonomics after durable workspace model is stable. |
| Staged downstream pipeline | `staged-downstream-future-design-review.md` | P5 deferred | P5 | XL | Engine + Studio | `Entity -> staging -> downstream` optional topology for enterprise batch / EOD flows. |
| S1B server-backed catalog + locking | Save/open later phase | P5 deferred | P5 | L | Studio | Multi-project server-backed storage only when real multi-user need appears. |
| SSO / LOB access / RBAC | Save/open auth track | P5 deferred | P5 | L | Studio | Enterprise deployment concerns, intentionally later than local-first Studio. |
| Engine MCP HTTP/SSE transport or federated gateway | Extension architecture future | P5 out | P5 | L-XL | Cross-repo | Add shared/server deployment only if local stdio is no longer enough. |
| Generation-quality cleanup bundle | `review-feedback-future-notes.md` (#78/#82/#83/#86/#90/#92) | P5 | P5 | S | Engine | Small deferred correctness/maintainability cleanup items. |
| Breaking manifest redesign (v2) | Explicitly deferred | P5 deferred | P5 | XL | Cross-repo | Stay additive on `schema_version: "1.0"` unless a deliberate future redesign is justified. |

## Design Gaps And Implementation Follow-Through

Post-baseline P3 items either still need design-first docs or now need
implementation follow-through from a new design anchor:

- `docs/high-tps-entity-profile-design.md` — high-TPS atomic / event-sourced entity profiles
- `docs/legacy-extractor-phase6-architecture.md` — refresh for Studio UX v3 and unified KA suggestion flow
- `docs/generated-app-standards/generated-app-quality-gate-v1.md` — generated-app quality gate exists; next work is implementation follow-through
- `docs/generated-app-standards/generated-app-engine-roadmap.md` — generated-app Engine roadmap exists; next work is implementation follow-through

`docs/crud-cross-entity-rules-design.md` and
`docs/legacy-extractor-phase6-architecture.md` already exist. Do not describe
them as missing; track current gaps as implementation hardening or refresh
work, not absent design anchors.

## Archived Docs

The following older planning docs were archived in April 2026 after their
remaining useful content was folded into the target-state roadmap, sequencing,
or this master backlog:

- `docs/archive/generation-quality-roadmap.md` — Phase 3 hardening record; superseded as a live roadmap by this backlog and the target-state docs
- `docs/archive/architecture-risk-review-pre-phase2.md` — historical pre-Phase-2 risk review; valuable as context, no longer active roadmap guidance
- `docs/archive/passthrough-router-mini-roadmap.md` — passthrough lane is now part of the baseline and remaining follow-ons are tracked here

## Usage Notes

- Treat this file as the ranked suite backlog source of truth.
- Use the target-state architecture and sequencing docs for rationale and gate
  ordering.
- Keep feature-specific design in dedicated docs instead of overloading this
  backlog file with implementation detail.
