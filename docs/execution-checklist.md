# EdgeForge Execution Checklist

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

> **SUPERSEDED — April 12, 2026 snapshot.** Phase 5 KS Studio work listed as
> future here is complete through Studio PR #143. Current execution priorities
> live in the
> [Enterprise-Readiness & Handoff Roadmap](enterprise-readiness-roadmap.md) and
> generated [Suite Task Tracker](tracker/README.md). The broader
> [Implementation Sequence History](current-implementation-sequence.md) is also
> historical, not a live plan.

## Current Focus

**Shared baseline as of 2026-04-12:** EdgeForge `main` is green through PR `#102`, EdgeForgeStudio `main` is green through PR `#58`, Phase 3 Engine hardening is complete, Phase 4 local Engine MCP is implemented, and Studio uses Engine MCP `generate_app` with subprocess fallback through its existing integration boundary.

---

## Completed (all merged to main)

### MVP (PRs #1–#10)

- [x] Foundation: scaffold, manifest schema, normalized metadata model
- [x] Manifest and input package: hardened validation, negative tests, path normalization
- [x] Contract ingestion: OpenAPI, downstream file layout, staging-table metadata, canonical field types
- [x] Mapping and rules engine: upstream/downstream/staging mappings, defaults, allowed-values
- [x] Generation skeleton: domain entities, services, controllers, repositories, Flyway, Spring Batch, Dockerfile, README
- [x] Compatibility harness: golden samples, mapping completeness, happy-path tests
- [x] Developer experience: CLI entry point, CI, review guidance

### Post-MVP Features (PRs #11–#23)

- [x] Demo UI generation (PR #11)
- [x] SSO Security Layer — `emit_security` flag (PR #12)
- [x] Audit Tracking — `emit_audit` flag (PR #13)
- [x] Docs sync (PR #14)
- [x] OpenAPI ingestion + classification + `appbuilder assess` CLI (PR #15)
- [x] Multi-entity bounded context generation (PR #16)
- [x] Privately retained external-application multi-entity PoC (PR #17)
- [x] Phase A rule constraints: max_length, min_length, pattern, range, not_null (PR #18)
- [x] Full CRUD endpoints + path param binding + error handling (PR #20)
- [x] Operator dashboard with entity-centric panels + demo endpoints (PR #21/22)
- [x] Cross-entity FK existence validation (`cross-entity-exists` rule) (PR #23)

### Phase 1a: Generator Blockers — ✅ All resolved

- [x] Full CRUD endpoint generation (GET/{id}, GET list, POST, PUT/{id}, DELETE/{id})
- [x] Path parameter binding (`@PathVariable`, service/repository methods)
- [x] Basic error handling (`@ControllerAdvice`, 404/400 standard error DTO)
- [x] Basic nested object/array handling (`List<T>`, flattened embedded objects)
- [x] Unsupported entity-ingestion construct warnings (oneOf/anyOf, scalar arrays — warning + skip)
- [x] ID ownership inference (server-generated vs client-supplied)
- [x] Cross-entity FK validation (`cross-entity-exists` rule type, PR #23)
- [x] Empty/degenerate manifest surfaced as clear generation error (PR #29)

---

## Recently Completed

### Phase 1-smoke + Smoke-Fix Follow-Up — ✅ Completed / merged

- [x] LoanLite: full Studio -> export -> generate -> compile -> run path proven
- [x] Privately retained external-application input package through Studio -> export -> generate -> compile -> run
- [x] Real OBIE spec through Studio -> classify -> failure inventory captured
- [x] LoanLite smoke blockers fixed and merged (PR #25)
- [x] Staging-width ID truncation and repayment runtime issues fixed and merged (PR #26)
- [x] Vendor-neutral agent-adapter architecture docs merged (PR #27)
- [x] Phase 1-smoke report captured and used to drive fix PRs (PR #28, later closed without merge)
- [x] Empty-manifest generation error hardened and merged (PR #29)

---

## Phase 1-smoke: Studio ↔ Engine E2E

- [x] LoanLite: full Studio → generate → compile → run
- [x] Privately retained external-application input package through Studio → export → generate → compile → run
- [x] Real OBIE spec through Studio → classify → generate → document failures

## Phase 1b: Second-Tier Gaps

- [x] Entity relationships (`@ManyToOne`, FK columns, migration ordering)
- [x] DTO validation annotations (`@NotNull`, code-point-aware `@CodePointLength`, and `@Pattern` from canonical model)
- [x] External-application smoke P2: response-sample fields absent from explicit mappings were silently omitted; restore response-field completeness for that contract path
- [x] Query/header parameter support (`@RequestParam`, `@RequestHeader`)
- [x] Same-entity `field-comparison` rule type (`<=`, `<`, `>=`, `>`, `==`) with generated service-layer `400 Bad Request` validation
- [x] FK/reference constraint propagation + generated ID-input constraint rendering
- [x] Generated-ID guardrail for server-generated IDs vs business-key constraints
- [ ] Passthrough operation extraction: inventory every site that reads `type`/`format`/`maxLength`/
  `$ref`/`allOf` off a property schema, add nested `$ref`/`allOf` resolution so nested properties use the
  same path as top-level ones, then fail closed or surface diagnostics for what remains unrepresentable
- [x] Maven/package naming sanitization for spaced app names
- [x] Phase 1b smoke-driven P1/P2 follow-ups closed on `main`

## Phase 2 Setup / Gate

- [x] Docs baseline refresh merged
- [x] Fresh workspaces opened on `EdgeForge` / `EdgeForgeStudio`
- [x] Architecture review gate completed from `docs/architecture-risk-review-pre-phase2.md`
- [x] `app_archetype` field added
- [x] `schema_version` added
- [x] `engine.py` refactored to explicit archetype dispatch
- [x] `manifest-schema.json` v1 drafted for CRUD packages
- [x] `validate_package()` / stronger package contract checks (PR #47)
- [x] Passthrough-router Engine MVP (translation + emitters) (PRs #49–#50)
- [x] Studio manifest-v1 export alignment merged in `EdgeForgeStudio` (PR #14)
- [x] Java identifier sanitization (PR #51)
- [x] OAS 3.1 nullable type normalization (PR #52)
- [x] Duplicate DTO field deduplication (PR #53)
- [x] Terminal path param ID field alignment (PR #54)
- [x] Paginated wrapper field exclusion (PR #55)
- [x] Integration tests + docs sync (PR #56)

## Phase 2: Real Apps via Studio

- [x] Wire Transfer App (OBIE Payment Initiation spec) — **proof closed green 2026-04-02** (PRs #57–#61)
  - nested sample field extraction (PR #57)
  - `@PrePersist` lifecycle init — string fields (PR #58)
  - route contract preservation (PR #59)
  - `@PrePersist` lifecycle init — datetime fields (PR #60)
  - smoke report updated green (PR #61)
  - documented gap: nested OBIE `Data`/`Data.Initiation` envelope requires gateway adapter (Option B)
- [x] Prove one real passthrough-router app — **SEPA Payment Router proof closed green 2026-04-02** (PR #64)
  - translation: PASS
  - generation: PASS
  - Maven build: PASS
  - app startup + health: PASS
  - runtime routing decision: PASS
  - documented gap: downstream connectivity requires deployed or mocked target systems
- [x] Close the spec-route seam-review stack (PRs #66–#68)
  - cross-emitter spec-route regression gate
  - shared `spec_route_base_path()`
  - shared `supports_spec_route()`
- [x] Studio-led OBIE rerun green end to end after Studio PR #36
- [x] Studio-led external application expanded 3-entity proof green end to end
- [x] Studio manual-testing fixes merged for:
  - Step 4/5 reload serialization regressions (Studio PR #37)
  - Step 6 pasted regex normalization / blank-pattern handling (Studio PR #39)
- [x] Studio docs sync merged to the April 5 baseline (Studio PR #40)
- [x] Studio Build & Run support after generation
- [x] Studio export/authoring support for passthrough-router packages
- [x] Broad external-application scaffold runtime gaps moved into Phase 3 `A3` hardening
  - state-transition write behavior
  - read-only history lookup behavior
  - derived-value read behavior

## Earlier Decisions Locked

### Architecture

- Canonical-as-hub topology confirmed: `canonical → downstream`, `canonical → handoff`
- Staging-to-downstream chaining: **deferred out of Phase 2 scope**
- If staged downstream is revisited later, treat it as an optional extension and start with an Engine-only proof first (see EdgeForgeStudio PR #38 / `docs/staged-downstream-future-design-review.md`)
- All new Engine features require a real proof to justify them (proof-driven, not speculative)

### Pending Chore Backlog (non-blocking)

- [ ] Move `_is_create_operation_name` from `translation.py` to `generation/utils.py`
- [ ] Remove/correct service comment on update path (`// Server-set fields...`)
- [ ] Move Codat-specific envelope keys out of global `_RESPONSE_ENVELOPE_METADATA_KEYS`

### Engine-First Features (deferred until a proof proves the need)

- Delimited downstream file format (CSV/pipe) — no proven blocker yet
- Additional generated-ID strategy picker UX beyond current overrides — no proven blocker yet
- Nested upstream request DTO shape preservation (Option A) — future design if a proof demands it

### Studio (parallel, no Engine gate)

- [x] Step 5 staging mapping target validation against actual parsed DDL column names
- [x] Step 4/5 reorder (wizard flow only)
- [x] Proof-runner consolidation
- [x] Export error surfacing (traceback summary in UI)
- [x] Step 3 paginated-wrapper guidance
- [x] `field-comparison` rule authoring UI
- [x] Build & Run UI after generation
- [x] Minimal passthrough wizard path within current Engine limits

## Phase 3 / Phase 4 Closure

- [x] `A2` date/type propagation hardening
- [x] `A3` preserved custom / non-CRUD operation support
- [x] `B4` audit baseline + collision guard
- [x] `B5` ISO-4217 validation / SQL / JPA type alignment
- [x] `B6` fixed-width padding/truncation
- [x] `C8` PostgreSQL production datasource profiles and runtime fixes
- [x] `B7` per-operation opt-in offset/limit pagination
- [x] `A1` `identity_overrides`
- [x] `C9` `id_generation_overrides`
- [x] Engine MCP server (Phase 4 local stdio; seven approved tools)
- [x] Studio MCP `generate_app` adapter with subprocess fallback
- [x] Studio MCP proof runner and docs closure

## Phase 5+ Extensions

- [ ] Knowledge Server MCP design doc before implementation
- [ ] Passthrough-router multi-upstream/multi-downstream transformation-rules design
- [ ] LegacyExtractor MCP design doc before implementation

---

## Review Guidance

When asking Claude to review a PR, prefer prompts like:

`Review this PR for contract-preserving design risks, canonical-model drift, missing tests, and migration compatibility issues. Findings first.`

When asking Codex to review or implement follow-up work, prefer prompts like:

`Review this PR for implementation risks and then update the code to resolve the highest-signal issues while preserving the manifest-driven MVP path.`

---

## Decision Rule

If Codex and Claude disagree:

1. preserve the source-of-truth docs
2. prefer the design that keeps contracts stable at the edges
3. prefer the design that keeps the canonical model clean internally
4. prefer the smaller, more testable implementation slice
5. if the plan contradicts source-of-truth docs, update the plan to match
