# OpenAPI Intake and Multi-Entity Design Note

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

> **Historical document.** Design notes from the OpenAPI intake and multi-entity design discussion. For current architecture, see `docs/extension-architecture.md`.

## Purpose

This note consolidates the design discussion around:

- ingesting Swagger/OpenAPI directly into EdgeForge
- supporting multiple entities and operations within one bounded context
- introducing a separate intake/pre-processing experience to prepare correct EdgeForge input packages

It is based on:

- direct review of the privately retained external-application OpenAPI specification
- the EdgeForge architecture as it exists today
- independent analysis by both Codex and Claude, followed by cross-review
- merged conclusions approved by the repository owner

This note is the **single aligned design reference** for all implementation PRs on ingestion, multi-entity, and intake tooling.

**Last updated:** 2026-03-14 (merged review integration)

---

## Current Reality

EdgeForge already has a strong foundation:

- manifest-driven input package model
- contract ingestion and canonical metadata translation
- explicit mappings and rules
- generated Spring Boot skeleton applications
- compatibility harness
- generated demo UI
- generated security scaffolding (`emit_security` flag, PR #12)
- generated audit tracking (`emit_audit` flag, PR #13)

However, the current generator has two structural limitations:

1. **Single-entity oriented** — `primary_entity()` returns `metadata.entities[0]`; all emitters consume only that one entity
2. **No remote spec fetching** — `spec_url` field exists in the manifest model but translation.py emits a warning and falls back to sample-based ingestion

These limitations prevent EdgeForge from handling real-world bounded contexts with multiple entities (e.g., Customer + Account) and from auto-parsing upstream APIs from live Swagger endpoints.

---

## Privately retained external-application review

The March 14 review examined a multi-entity external application. Its
operation/schema inventory, payloads and application-specific intake mockup
are withheld. The useful conclusion was to select a small related-entity
slice, exclude response wrappers, and keep domain logic developer-owned.

---

## Agreed Design Points

### 1. Keep the existing manifest/input-package path

This remains the correct baseline for legacy modernization.

Reasons:

- many legacy apps will not have OpenAPI
- downstream files and staging contracts still need explicit representation
- business rules and migration notes still need structured input

### 2. Add `spec_url` / OpenAPI ingestion

EdgeForge should support:

- `spec: local-file.yaml` (already works)
- `spec_url: http://.../v3/api-docs` (fetch not yet implemented)

This is an **additional upstream ingestion source**, not a replacement for the manifest model.

Implementation path:

- The `spec_url` field already exists in `InterfaceDefinition` (manifest model)
- The `_openapi_type_to_canonical_type()` mapper already exists in `translation.py`
- The missing piece is: HTTP fetch → parse OpenAPI JSON/YAML → walk `components/schemas` and `paths` → populate `CanonicalEntity` fields and `CanonicalOperation` entries

### 3. Entity count is not the same as business complexity

| Domain | Entities | Generated % | Business Logic Complexity |
|--------|----------|------------|--------------------------|
| CRM (Customer + Account) | 2 | ~90% | Low — CRUD only |
| Loan Origination | 4 | ~50% | Medium — interest, amortization |
| FX/MM Deal Booking | 5 | ~40% | High — rates, netting, settlement |
| Instant Payments | 4 | ~30% | Very High — routing, clearing, volume |
| Liquidity Management | 3 | ~35% | High — sweep rules, thresholds |

EdgeForge generates the structural skeleton. Business logic is added incrementally via PRs on the generated app.

### 4. Do not map OpenAPI schemas directly to canonical entities

This is a critical design correction.

In a real OpenAPI spec, many `components/schemas` entries are NOT domain entities:

- request DTOs (CreateCustomerRequest)
- response DTOs (CustomerResponse)
- page wrappers (PageCustomerResponse)
- infrastructure objects (PageableObject, SortObject)
- balance snapshots (BalanceResponse)
- error objects

The correct ingestion sequence is:

1. OpenAPI ingestion builds a **contract model** (all schemas and operations)
2. EdgeForge derives **candidate entities** by identifying response schemas linked to CRUD operations
3. The intake layer or manifest **selects** which candidates belong to the bounded context
4. Canonical entities are built from that reviewed selection

**Rule:** Do not assume `components/schemas/*` maps 1:1 to `CanonicalEntity`.

### 5. Multi-entity support is more than "loop over all entities"

Proper multi-entity support requires changes in:

| Component | Change Required |
|-----------|----------------|
| `translation.py` | Build separate `CanonicalEntity` per upstream interface/schema (not one merged entity) |
| `utils.py` | Add `all_entities()` iterator; keep `primary_entity()` for batch job only |
| `java_emitter.py` | Loop: N Entities + N Controllers + N Services + N Repositories + N DTO sets |
| `sql_emitter.py` | Loop: N Flyway migrations (`V1__create_X.sql`, `V2__create_Y.sql`, ...) |
| `ui_emitter.py` | Demo UI with tabs per entity |
| `CanonicalEntity` model | Add optional FK reference support (simple `@Column` FK, not `@ManyToOne` for v1) |
| Downstream writers | One writer per downstream interface |
| Batch job | One EOD job that processes all entities |

No changes needed in: `build_emitter.py`, `audit_emitter.py`, `security_emitter.py`.

Estimated scope: ~200-250 lines across 4-5 files.

### 6. Generated apps are starting points, not continuously regenerated

After generation, the app is maintained like any normal application. Whole-app regeneration after heavy manual edits is risky and not promised. EdgeForge's value is in the initial skeleton + contract correctness.

Two paths for adding entities after initial generation:

1. **Re-generate with updated manifest** — adds new entity scaffolding but overwrites everything
2. **Manually add** following the patterns EdgeForge established

Path 2 is what real teams will do. Path 1 is only useful for greenfield apps.

### 7. A pre-app / intake tool reduces friction

A companion tool that prepares EdgeForge input packages would:

- guide the user through input collection
- validate minimum required information
- avoid overloading EdgeForge with irrelevant raw data
- generate the manifest and folder structure EdgeForge expects
- produce a completeness report showing gaps

**Naming:** "EdgeForge Studio" for the future UI version.

**Rollout:** CLI first (`appbuilder init`), UI later (separate conversation/repo).

---

## Ingestion Source Priority

| Priority | Source | Format | EdgeForge Status |
|----------|--------|--------|-------------------|
| **P1** | OpenAPI 3.x / Swagger 2.0 | JSON/YAML at URL or file | `spec_url` field exists, fetch not implemented → next PR |
| **P1** | Sample JSON request/response | JSON files | ✅ Already works |
| **P1** | DDL (CREATE TABLE) | `.sql` files | ✅ Already works for staging tables |
| **P1** | Fixed-width file layouts | YAML spec + sample files | ✅ Already works for downstream handoffs |
| **P2** | WSDL (SOAP) | XML at URL or `.wsdl` file | Not implemented |
| **P2** | XSD (standalone) | `.xsd` schema files | Not implemented |
| **P2** | DTD | `.dtd` files | Not implemented |
| **P3** | Postman Collection | `.postman_collection.json` | Not implemented |
| **P3** | COBOL copybooks | `.cpy` record layouts | Not implemented |
| **P4** | Protobuf / gRPC | `.proto` schema files | Not implemented |
| **P4** | Avro / JSON Schema | `.avsc` / `.json` schema files | Not implemented |

### Enterprise prevalence (for prioritization context)

- OpenAPI/Swagger: ★★★★★ — common in apps built in last 10 years
- Sample JSON/XML: ★★★★★ — universal fallback
- WSDL/SOAP: ★★★★☆ — very common in enterprises (COBOL/Java bridges, ESB)
- DDL/staging tables: ★★★★☆ — DBA exports, Flyway migrations
- Fixed-width files: ★★★★☆ — EOD batch, SWIFT messages, regulatory reports
- XSD (standalone): ★★★☆☆ — often appears without WSDL wrapper in real enterprise
- DTD: ★★☆☆☆ — older XML contract definitions, mostly replaced by XSD
- COBOL copybooks: ★★★☆☆ — mainframe-fed systems
- Postman: ★★★☆☆ — dev teams without formal API docs
- Protobuf: ★★☆☆☆ — newer payment rails
- Avro: ★★☆☆☆ — event-driven / Kafka architectures

---

## Assessment Mode (`appbuilder assess`)

Before generating anything, EdgeForge should support a standalone assessment command:

```bash
appbuilder assess --swagger http://localhost:8080/v3/api-docs
```

This command:

1. Fetches and parses the OpenAPI spec
2. Inventories all operations and schemas
3. Classifies schemas as: domain entity candidate, DTO, infrastructure/skip
4. Reports what EdgeForge can fully generate vs what needs manual work
5. Flags missing downstream/rules inputs needed for full generation
6. Does NOT create any files

The original application-specific output mockup is retained privately.
This public summary describes the assessment behavior, not that API.

---

## Intake Tool Strategy

### Stage 1: CLI intake command (`appbuilder init`)

```bash
appbuilder init --swagger http://localhost:8080/v3/api-docs --output examples/input-projects/crm-app/
```

This CLI:

- fetches the spec
- inventories operations and schemas
- lets the user choose tags/entities/operations in scope
- generates a draft EdgeForge input package (manifest + folders)
- emits a completeness report

### Stage 2: EdgeForge Studio (UI)

After CLI is proven, add a lightweight web form that:

- accepts Swagger URL or file upload
- accepts pasted sample JSON/XML payloads
- accepts DDL for staging tables
- helps user review inferred entities/operations
- generates the manifest/package
- shows completeness report with gaps

**Decision:** EdgeForge Studio is deferred to a separate conversation and repo. Not in current scope.

### Min/Max data boundaries for intake

**Minimum required:**
- At least 1 upstream interface (swagger URL or sample JSON pair)
- At least 1 field on at least 1 entity
- A target profile selection

**Maximum supported (current):**
- Entity fields: all scalar types EdgeForge maps (string, integer, decimal, boolean, date, datetime)
- Operations: CRUD (create, read, update, delete, list)
- Downstream: fixed-width file layouts

**What intake should filter out / warn about:**
- Nested object schemas → flatten or skip with warning
- Pagination wrappers (Page<T>) → extract inner schema only
- Infrastructure schemas (SortObject, PageableObject) → skip
- Operations with complex body patterns (multi-leg posting) → flag as "manual implementation needed"

---

## Gaps Identified During Cross-Review

### 1. Entity relationships (FK support)

For CRMApp, Account has a FK to Customer (`customerId`). `CanonicalEntity` today has no concept of foreign keys or relationships.

**Resolution:** Add an optional `relationships` or `references` field to `CanonicalEntity`. Minimum viable: FK reference with target entity name and field. Generated JPA entity uses a simple `@Column` FK field, NOT a `@ManyToOne` JPA relationship — keep it simple for v1.

### 2. Re-generation safety for contract edge changes

Once developers add business logic to a generated app, upstream contract changes require selective regeneration (just DTOs/controllers) without overwriting the service layer.

**Resolution:** Deferred. For now, contract changes are handled as manual PRs on the generated app. Future "selective regeneration" is out of scope for current sequence.

### 3. Integration logs as ingestion source

In real legacy modernization, sometimes the only documentation of a contract is a captured production message.

**Resolution:** Already covered by existing sample JSON/XML ingestion path. The future intake tool should have an explicit "paste a captured message" UX label.

---

## What EdgeForge Generates vs What Stays Manual

### EdgeForge generates (structural skeleton)

```
Controller → Service (thin) → Repository
    ↕              ↕              ↕
  DTOs        [extension     Entity + JPA
               point for       annotations
               business
               logic]
```

Plus: Flyway DDL, batch scaffolding, downstream file writers, demo UI, security config, audit config, Dockerfile, README, pom.xml.

### Teams add manually (domain logic)

- Complex business rules
- Pricing and fee engines
- Overdraft / interest accrual logic
- Payment routing / orchestration
- Liquidity sweep decisioning
- Settlement workflows
- Concurrency / recovery behavior
- Inter-entity validation (FK checks)

---

## Aligned PR Sequence

### Phase 1: Core Generator Enhancements

| PR | Branch | What | Depends On | Parallelizable |
|----|--------|------|------------|----------------|
| **PR 14** | `*/feature/openapi-ingestion` | Fetch `spec_url`, parse OpenAPI schemas/paths into CanonicalEntity + CanonicalOperation. Remove stub warning. | Nothing | Yes — parallel with PR 15 |
| **PR 15** | `*/feature/multi-entity` | Translation builds N entities. All emitters loop. Add FK reference to CanonicalEntity. | Nothing | Yes — parallel with PR 14 |
| **PR 16** | `*/feature/assess-command` | `appbuilder assess --swagger <url>` CLI. Inventory + classification + gap report. No file generation. | PR 14 | No |

### Phase 2: Proof-of-Concept

| PR | Branch | What | Depends On |
|----|--------|------|------------|
| **PR 17** | `generated/crm-app` | CRMApp input package (Customer + Account). Generate CRMApp. Integration test. | PR 14 + PR 15 |
| **PR 18** | `*/feature/docker-compose` | `docker-compose.yml` for BuiltApp1 + BuiltApp2 + CRMApp on ports 8081-8083. | PR 17 |

### Phase 3: Intake Tooling (Separate Conversation)

| PR | Branch | What | Depends On |
|----|--------|------|------------|
| **PR 19** | `*/feature/init-command` | `appbuilder init --swagger <url>` CLI. Entity selection + draft package + completeness report. | PR 14 + PR 15 |
| **Future** | Separate repo | EdgeForge Studio (UI wizard). | PR 19 proven |

Note: PR numbers are indicative. Actual numbers assigned by GitHub at creation time.

---

## Decisions Deferred

| Topic | Decision | Revisit When |
|-------|----------|-------------|
| Re-generation safety (selective regeneration) | Out of scope. Manual PRs on generated app. | After CRMApp demo |
| JPA `@ManyToOne` relationships | Simple `@Column` FK for v1. | After CRMApp demo |
| WSDL/XSD ingestion | P2 priority. Not in current sequence. | After OpenAPI + multi-entity merged |
| EdgeForge Studio (UI) | Separate conversation and repo. | After `appbuilder init` CLI proven |
| Whole-enterprise ecosystem manifest | Out of scope per post-mvp-roadmap.md Decision 2. | Not planned |

---

## Practical Conclusion

No effort so far has been wasted. The current EdgeForge foundation remains correct:

- manifest-first
- contract-first
- normalized metadata
- generated app scaffolding
- compatibility verification

What changes now is the next enhancement direction:

- connect the `spec_url` wire (OpenAPI ingestion)
- unlock multi-entity bounded contexts
- add assessment and intake tooling

This is the correct path to make EdgeForge useful for real CRM-style and enterprise modernization use cases.
