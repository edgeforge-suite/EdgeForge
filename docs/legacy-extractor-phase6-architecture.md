# EdgeForge LegacyExtractor — Phase 6 Architecture Design

> **Design-first doc.** Written 2026-04-21.
>
> This doc is the **source of truth** for all future LegacyExtractor (LE)
> implementation. No LE code should be written without referring back to this
> design. Implementation slices must cite this doc as their contract.
>
> Companion docs:
> - [`docs/engine-mcp-design.md`](engine-mcp-design.md) — Engine MCP pattern to follow
> - [`docs/knowledge-server-mcp-design.md`](knowledge-server-mcp-design.md) — KS MCP boundary
> - [`docs/archive/target-state-architecture-roadmap-v1.md`](archive/target-state-architecture-roadmap-v1.md) — Phase 6 summary
> - [`docs/studio-ux-v3-assistive-features-design.md`](../../EdgeForgeStudio/docs/studio-ux-v3-assistive-features-design.md) — LE Studio attachment points (UX v3; replaces the stale `studio-ux-v2-design.md` reference)
>
> Cross-repo note: LE lives in its own repo (`EdgeForgeLegacyExtractor`, TBD),
> parallel to `EdgeForgeKnowledgeServer`. It is not a module inside Engine or KS.

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Suite Positioning](#2-suite-positioning)
3. [Non-Goals — What LE Will NOT Own](#3-non-goals--what-le-will-not-own)
4. [Full Original Scope (Target State)](#4-full-original-scope-target-state)
5. [MVP Scope (First-Value Slice)](#5-mvp-scope-first-value-slice)
6. [MCP Tool Contracts](#6-mcp-tool-contracts)
7. [Output Artifact Model](#7-output-artifact-model)
8. [Provenance and Confidence Model](#8-provenance-and-confidence-model)
9. [Parser Boundary Discipline](#9-parser-boundary-discipline)
10. [Error Handling and Partial Extraction](#10-error-handling-and-partial-extraction)
11. [Integration with EdgeForge Components](#11-integration-with-edgeforge-components)
12. [Security, Sandboxing, and Resource Limits](#12-security-sandboxing-and-resource-limits)
13. [Implementation Phasing](#13-implementation-phasing)
14. [Open Questions](#14-open-questions)
15. [Appendix: Example Payloads](#15-appendix-example-payloads)

---

## 1. Purpose and Scope

### 1.1 Problem Statement

Enterprise modernization projects start with legacy source-like
artifacts: COBOL copybooks, PL/SQL packages, Oracle DDL, legacy Java
classes, EBCDIC record layouts, and similar structural assets. Today the only
way to get their content into EdgeForge is manual transcription into
OpenAPI/sample JSON or by uploading raw text to the Knowledge Server and
relying on BM25 retrieval.

That loses structure. A copybook is **deterministic**: positions, lengths,
types, signs, and packed-decimal formats are all exact. A PL/SQL procedure is
**deterministic**: parameter types, branches, table touches, and return
shapes are all parseable. Both deserve first-class extraction — not keyword
search.

### 1.2 What LegacyExtractor Is

LegacyExtractor (LE) is a **separate MCP server** that performs
**deterministic structural extraction** from legacy source artifacts and
produces **typed, provenanced outputs** consumable by KS, Studio, and
(indirectly, via Studio authoring) the Engine manifest pipeline.

LE is to **structural legacy assets** what KS is to **prose legacy
documents**:

| Concern | Knowledge Server | LegacyExtractor |
|---------|------------------|-----------------|
| Input | Markdown, PDF, DOCX, CSV, SQL dumps, Excel | COBOL copybooks, PL/SQL packages, Oracle DDL, EBCDIC layouts, legacy Java source |
| Output | Searchable chunks, field catalog rows, evidence chains | Typed schemas, extracted fields, rule candidates, mapping candidates, structural provenance |
| Primary op | BM25 search, field aggregation | Parser-driven structural extraction |
| Consumers | Studio (suggestions, evidence), author Q&A | Studio (suggestions, evidence, conflicts), KS (as reuse push target) |

### 1.3 What This Doc Delivers

A complete, implementation-ready design covering:

- Full original scope and MVP boundary
- Tool contracts (all planned + MVP subset)
- Typed output artifact schemas
- Provenance and confidence model
- Parser isolation and language-plugin discipline
- Integration contracts with KS, Studio, Engine, and Engine MCP
- Security, sandboxing, and partial-extraction error model
- Implementation phasing

---

## 2. Suite Positioning

### 2.1 Component Map

```
                    ┌────────────────────────────────┐
                    │            Studio              │
                    │  (main pane + right rail +     │
                    │   bottom drawer shell, v2)     │
                    └──┬───────────┬──────────┬──────┘
          suggestions  │           │ Engine   │ KS tool
          + evidence   │           │ MCP      │ calls
          + conflicts  │           │ calls    │
                       ▼           ▼          ▼
         ┌─────────────────┐ ┌──────────┐ ┌────────────┐
         │   LegacyExtract │ │  Engine  │ │ Knowledge  │
         │       (LE)      │ │   MCP    │ │  Server    │
         │                 │ │          │ │    (KS)    │
         │  parsers +      │ │ 7 bounded│ │ 13 tools   │
         │  extractors +   │ │ tools    │ │ BM25 +     │
         │  provenance     │ │ (stdio)  │ │ field      │
         │  (stdio)        │ │          │ │ catalog    │
         └────────┬────────┘ └──────────┘ └─────▲──────┘
                  │                              │
                  └──────────────────────────────┘
                     LE → KS push (optional)
```

### 2.2 Boundaries

- LE does **not** call Engine MCP. It does not generate code.
- LE does **not** call KS directly for search or Q&A. LE pushes artifacts
  into KS via a narrow push API, but LE is never a KS client.
- LE does **not** own Studio workflow state. Studio owns what happens to LE
  outputs (accept / edit / reject) via the same review pattern it already
  uses for KS field suggestions.
- LE does **not** own manifest publication. Studio composes the final
  manifest and calls Engine MCP `generate_app`. LE outputs flow through
  Studio as candidate inputs.

---

## 3. Non-Goals — What LE Will NOT Own

This list is the **hard boundary** for LE. If a future proposal asks LE to
take on any of these, it needs an explicit design-doc revision.

1. **Project document search and Q&A** — that is Knowledge Server's job.
2. **Studio workflow state, save/open, review bucket persistence** — Studio owns that.
3. **Final manifest publication** — Studio + Engine MCP compose and generate.
4. **Code generation** — Engine owns that, via Engine MCP.
5. **General-purpose "AI modernization brain"** — LE is a parser, not a reasoner.
6. **LLM-based extraction as primary path** — extractors must be deterministic first; LLM assistance is a future-optional, explicitly-flagged mode.
7. **Direct integration with the generated application at runtime** — zero runtime coupling.
8. **Multi-tenancy, RBAC, audit logging** — stays local-stdio for Phase 6, same posture as Engine MCP and KS.
9. **Live database connections** — LE reads files on disk, not live Oracle/DB2 instances.
10. **Manifest mutation** — LE emits candidates; Studio decides what lands in the manifest.

---

## 4. Full Original Scope (Target State)

This section documents everything LE was originally envisioned to support.
**Not all of this is in MVP** — MVP is called out separately in Section 5.
This section is the long-term target the suite should keep converging toward.

### 4.1 Supported Input Types

| Input type | Description | Target extractor |
|------------|-------------|------------------|
| COBOL copybooks | Record layouts with PIC clauses, OCCURS, REDEFINES, packed-decimal, COMP, COMP-3, SIGN LEADING/TRAILING | `cobol-copybook` |
| PL/SQL packages | Oracle packages, procedures, functions, cursors, exception handlers, table touches | `plsql` |
| Oracle DDL | `CREATE TABLE`, `CREATE INDEX`, `CREATE VIEW`, constraints, sequences, triggers (structural parts only) | `oracle-ddl` |
| EBCDIC record layouts | Fixed-position records with field definitions and type encoding | `ebcdic-layout` |
| Legacy Java | Pre-Spring-era Java DTOs, service classes, utility classes; extract types, method signatures, and persistence annotations if present | `legacy-java` |
| JCL job definitions | Batch job steps, DD statements, program invocations, dataset references | `jcl` |
| IMS / DB2 DCLGEN | DB2 structure definitions | `db2-dclgen` |
| Fixed-width file layouts | Spec documents describing positional record formats (may overlap with copybooks) | `fixed-width-layout` |

Each input type is a **separate parser plugin** — not a shared monolith. See
Section 9 for boundary discipline.

### 4.2 Target Output Artifacts

LE extractors produce one or more of the following typed artifacts per
ingested source. All artifacts are JSON with strict schemas (see
[Section 7](#7-output-artifact-model)).

| Artifact type | Produced by | Used by |
|--------------|-------------|---------|
| `extracted_schema` | copybook, DDL, DCLGEN, EBCDIC | Studio Step 3 entity suggestions; KS field catalog push |
| `extracted_field` | all extractors | Studio right-rail field suggestions; KS field catalog push |
| `extracted_rule_candidate` | PL/SQL, legacy-Java | Studio Step 6 rule suggestions (future scope) |
| `extracted_mapping_candidate` | PL/SQL, JCL | Studio Step 4/5 mapping suggestions |
| `extracted_operation_candidate` | PL/SQL procedures, legacy-Java service methods | Studio Step 3 operation suggestions |
| `extraction_warning` | all extractors | Studio conflict panel + bottom drawer |
| `provenance_record` | all extractors | Studio Evidence panel; KS evidence push |

### 4.3 Planned Tool Surface (13 tools at target state)

Following the Engine MCP pattern (7 bounded tools) and KS pattern (13 tools),
LE's target-state tool surface is:

**Ingestion and catalog**
1. `ingest_source` — parse a single source file and persist extraction to project-scoped LE store
2. `list_sources` — list ingested sources in a project
3. `get_source` — return parsed structural summary for one source
4. `delete_source` — soft-delete an ingested source

**Typed extraction queries**
5. `list_extracted_schemas` — all schemas extracted for a project
6. `list_extracted_fields` — all fields, optionally filtered by schema or source
7. `list_extracted_rule_candidates` — all rule candidates
8. `list_extracted_mapping_candidates` — all mapping candidates
9. `list_extracted_operation_candidates` — all operation candidates

**Studio-facing suggestion tools**
10. `suggest_entities_from_extraction` — aggregate extracted schemas into entity-suggestion candidates (parallel to KS `suggest_fields`)
11. `suggest_rules_from_extraction` — aggregate extracted rule candidates into rule-suggestion candidates

**Cross-component integration**
12. `push_to_knowledge_server` — push extracted artifacts into KS for search/reuse
13. `submit_extraction_decisions` — persist batched Studio accept/edit/reject decisions on LE suggestions (parallel to KS `submit_suggestion_decisions`)

### 4.4 Project Scoping

LE state is **project-scoped** using the same `project_id` convention as KS.
A project in Studio maps 1:1 to a project namespace in KS and a project
namespace in LE. All LE tools require a `project_id` argument.

Projects are isolated — one project cannot read another's extractions
without explicit cross-project tooling (not in Phase 6 scope).

### 4.5 Reuse Across Projects

LE artifacts may represent common domain structures (a `TransactionRecord`
copybook, a standard `Customer` DCLGEN). Cross-project reuse is handled by
**pushing accepted artifacts into KS** via `push_to_knowledge_server` — KS
already has `search_across_projects`. LE does not maintain its own
cross-project search surface.

---

## 5. MVP Scope (First-Value Slice)

This is what the **first LE implementation PR** should deliver. Everything
else in Section 4 is deferred until MVP lands and produces value in Studio.

### 5.1 MVP Extractors

**PL/SQL only.** Per the target-state roadmap, PL/SQL is the first-value
slice because:

- Enterprises have the largest volumes of business logic trapped in PL/SQL
- PL/SQL extraction produces the highest-leverage artifact: **rule
  candidates** that can feed the new Engine cross-entity rule types
- Deterministic PL/SQL parsers (ANTLR grammars) are mature and available
- Output is directly consumable by Studio Step 6 (Rules workbench)

COBOL copybook support is the intended **second slice**, not MVP.

### 5.2 MVP Artifact Types

The MVP produces three artifact types only:

1. `extracted_rule_candidate` — conditions and predicates extracted from PL/SQL procedures
2. `extracted_operation_candidate` — procedure/function signatures as operation candidates
3. `provenance_record` — source file, procedure name, line range, extraction timestamp

Not in MVP:
- Schema extraction (DDL parsing)
- Field catalog extraction
- Mapping candidates
- Cross-file rule correlation
- PL/SQL-to-Java translation

### 5.3 MVP Tool Surface (5 tools)

MVP ships a minimal tool surface. The remaining 8 tools from Section 4.3
land in subsequent slices.

| Tool | MVP? | Notes |
|------|------|-------|
| `ingest_source` | Yes | PL/SQL files only |
| `list_sources` | Yes | |
| `get_source` | Yes | |
| `list_extracted_rule_candidates` | Yes | |
| `list_extracted_operation_candidates` | Yes | |
| `delete_source` | No | Can be manual file delete in MVP |
| `list_extracted_schemas` | No | No schema extractor in MVP |
| `list_extracted_fields` | No | No field extractor in MVP |
| `list_extracted_mapping_candidates` | No | No mapping extractor in MVP |
| `suggest_entities_from_extraction` | No | No entity aggregation in MVP |
| `suggest_rules_from_extraction` | No | Replaced by direct `list_extracted_rule_candidates` in MVP; Studio aggregates client-side |
| `push_to_knowledge_server` | No | Manual copy to KS if needed; MVP establishes LE baseline first |
| `submit_extraction_decisions` | No | Studio stores decisions in its own review-state model for MVP |

### 5.4 MVP Studio Integration

Studio integration in MVP is bounded:

- Step 1 Knowledge Workspace gains a **"Structural Sources"** subsection for
  uploading `.sql`/`.pls`/`.pks`/`.pkb` files
- Step 6 right-rail Suggestions panel gets an **`origin: legacy-extractor`**
  badge on rule candidate cards — one new card type, reusing the existing
  accept / edit / reject pattern from KS field suggestions
- No conflict workbench integration in MVP — LE warnings surface as plain
  text entries in the advisory Conflicts panel
- No Step 7 provenance column for LE — that comes in a later slice

### 5.5 MVP Success Criteria

- A developer can upload a representative PL/SQL package in Studio Step 1
- LE extracts at least one rule candidate per IF/ELSIF condition in the package
- Extracted candidates appear in Step 6 right-rail Suggestions
- Accepting a candidate writes a `cross-entity-field-check` or similar rule
  into the manifest rules YAML (leveraging PR #121 cross-entity rules)
- Provenance records link each candidate back to its source file + line range
- The generated app builds and runs with the accepted rule

---

## 6. MCP Tool Contracts

All LE tools follow the Engine MCP pattern: **stdio transport, small
structured responses, no source-file contents in payload, relative paths
only**.

### 6.1 Shared Conventions

Every tool:
- Takes `project_id: str` as first argument
- Returns JSON with a `status: "ok" | "error"` envelope
- On error, returns `{ status: "error", code: str, message: str, details?: object }`
- Paths in responses are **relative** to the project root configured in
  `LEGACYEXTRACTOR_ALLOWED_ROOTS` (mirroring Engine MCP's `EDGEFORGE_MCP_ALLOWED_ROOTS`)
- Engine v5 and its MCP entry point now require Python 3.11+; this supersedes
  the original Python 3.10 baseline assumed by this deferred extractor design.

### 6.2 Tool Schema Summary

| Tool | Args | Returns |
|------|------|---------|
| `ingest_source` | `project_id`, `file_path` (relative to `LEGACYEXTRACTOR_ALLOWED_ROOTS`), `source_type` (enum: `plsql`, `cobol-copybook`, …) | `IngestResult { source_id, warnings[] }` |
| `list_sources` | `project_id`, optional `source_type` filter | `SourceListResult { sources: [{ source_id, source_type, file_name, ingested_at }] }` |
| `get_source` | `project_id`, `source_id` | `SourceSummary { source_id, extractor_version, summary, warnings[] }` |
| `delete_source` | `project_id`, `source_id` | `{ status }` |
| `list_extracted_rule_candidates` | `project_id`, optional `source_id` filter | `RuleCandidateListResult { candidates: [RuleCandidate] }` |
| `list_extracted_operation_candidates` | `project_id`, optional `source_id` filter | `OperationCandidateListResult { candidates: [OperationCandidate] }` |
| `list_extracted_schemas` (post-MVP) | `project_id`, optional `source_id` | `SchemaListResult { schemas: [ExtractedSchema] }` |
| `list_extracted_fields` (post-MVP) | `project_id`, optional `schema_id`, `source_id` | `FieldListResult { fields: [ExtractedField] }` |
| `list_extracted_mapping_candidates` (post-MVP) | `project_id`, optional `source_id` | `MappingCandidateListResult { candidates: [MappingCandidate] }` |
| `suggest_entities_from_extraction` (post-MVP) | `project_id` | `EntitySuggestionResult { suggestions: [EntitySuggestion], suggestion_ids[] }` |
| `suggest_rules_from_extraction` (post-MVP) | `project_id` | `RuleSuggestionResult { suggestions: [RuleSuggestion], suggestion_ids[] }` |
| `push_to_knowledge_server` (post-MVP) | `project_id`, `artifact_ids[]`, `ks_project_id` | `PushResult { pushed_count, ks_evidence_ids[] }` |
| `submit_extraction_decisions` (post-MVP) | `project_id`, `decisions: [{ suggestion_id, status }]` | `{ persisted_count }` |

### 6.3 Size Discipline

Like Engine MCP and KS, LE tool responses must fit comfortably in an LLM
context window. Hard rules:

- No raw source file contents in any response — only structured extracts
- Rule candidate and operation candidate payloads capped at 50 per response;
  pagination via `cursor` token if needed
- `get_source` returns a **summary**, not the full AST — requesting the full
  AST is a separate post-MVP tool if ever needed
- Evidence snippets capped at 500 characters per candidate

---

## 7. Output Artifact Model

### 7.1 Common Fields

Every artifact includes:

```json
{
  "artifact_id": "le-rc-20260421-00042",
  "project_id": "proj-abc123",
  "source_id": "src-20260421-00007",
  "extractor": "plsql",
  "extractor_version": "0.1.0",
  "extracted_at": "2026-04-21T14:22:33Z",
  "provenance": { ... },
  "confidence": 0.92,
  "warnings": []
}
```

### 7.2 `extracted_rule_candidate`

```json
{
  "artifact_id": "le-rc-...",
  "kind": "cross-entity-field-check",
  "proposed_rule": {
    "entity": "Transaction",
    "field": "accountId",
    "type": "cross-entity-field-check",
    "target-entity": "Account",
    "target-field": "status",
    "operator": "eq",
    "expected-value": "ACTIVE"
  },
  "source_expression": "IF v_account.status <> 'ACTIVE' THEN RAISE ...",
  "source_procedure": "PKG_TRANSACTION.POST_DEBIT",
  "source_line_range": [142, 148],
  "confidence": 0.92,
  "provenance": { ... }
}
```

The `proposed_rule` payload conforms to the cross-entity rules YAML shape
defined in [`docs/crud-cross-entity-rules-design.md`](crud-cross-entity-rules-design.md).
LE emits rule candidates that Studio can directly accept into the manifest
rules YAML without transformation.

### 7.3 `extracted_operation_candidate`

```json
{
  "artifact_id": "le-op-...",
  "proposed_operation": {
    "name": "postDebit",
    "http_method": "POST",
    "path": "/transactions/{transactionId}/debit",
    "request_shape_hint": { "amount": "BigDecimal", "accountId": "String" },
    "response_shape_hint": { "transactionId": "String", "status": "String" }
  },
  "source_procedure": "PKG_TRANSACTION.POST_DEBIT",
  "source_signature": "PROCEDURE post_debit(p_tx_id IN VARCHAR2, p_amount IN NUMBER, p_account_id IN VARCHAR2)",
  "source_line_range": [101, 180],
  "confidence": 0.78,
  "provenance": { ... }
}
```

Operation candidates are **hints**, not directly-injectable operations. The
Engine requires OpenAPI/sample JSON for operation definition — LE operation
candidates prompt Studio authors to draft the corresponding OpenAPI entry
rather than auto-generating it.

### 7.4 `extracted_schema` (post-MVP)

```json
{
  "artifact_id": "le-sch-...",
  "proposed_entity": {
    "name": "CustomerRecord",
    "fields": [
      { "name": "customerId", "type": "String", "max_length": 10, "nullable": false },
      { "name": "balance", "type": "BigDecimal", "precision": 15, "scale": 2 },
      { "name": "status", "type": "String", "max_length": 1, "allowed_values": ["A", "I", "C"] }
    ]
  },
  "source_layout": "COPYBOOK CUST-REC",
  "source_line_range": [1, 42],
  "confidence": 0.95
}
```

### 7.5 `extracted_field` (post-MVP)

One row per field. Aggregated across schemas for Studio right-rail field
suggestion panels. Shape parallels KS `read_field_catalog` output, enabling
seamless LE-to-KS push.

### 7.6 `extracted_mapping_candidate` (post-MVP)

Represents a structural mapping from one form to another (e.g., JCL step
copying dataset A to dataset B, or PL/SQL procedure copying rows from table
A to table B).

### 7.7 Artifact Evolution and Versioning

Each extractor has its own `extractor_version` field on every emitted
artifact. If an extractor's output schema changes (say from `v0.1` to
`v0.2`), Studio can detect the version mismatch and either migrate,
re-run, or surface a warning. Extractor versions follow semver.

---

## 8. Provenance and Confidence Model

### 8.1 Provenance

Every artifact carries a `provenance` block:

```json
{
  "source_file": "specs/plsql/pkg_transaction.pkb",
  "source_type": "plsql",
  "source_hash": "sha256:ab12cd34...",
  "extractor": "plsql",
  "extractor_version": "0.1.0",
  "extracted_at": "2026-04-21T14:22:33Z",
  "source_location": {
    "procedure": "PKG_TRANSACTION.POST_DEBIT",
    "line_range": [142, 148]
  },
  "upstream_evidence_ids": []
}
```

Fields:

- `source_file` — relative path under the LE project root
- `source_hash` — SHA-256 of the file bytes at ingest time; lets Studio
  detect when a source has changed since extraction
- `source_location` — structured pointer (procedure/line/column as
  applicable to the source type) used by the Studio Evidence panel to
  display a citation
- `upstream_evidence_ids` — optional list of KS evidence IDs this artifact
  was informed by (if the same file was also ingested into KS for search)

### 8.2 Confidence Score

Every artifact has a `confidence: float` in `[0.0, 1.0]`. Confidence
reflects **extractor certainty**, not semantic correctness. Heuristics:

| Extractor | 1.0 | 0.7-0.9 | 0.4-0.7 | <0.4 |
|-----------|-----|---------|---------|------|
| copybook | Fully parsed, all clauses resolved | OCCURS/REDEFINES partially resolved | Ambiguous REDEFINES | Parse errors partially recovered |
| PL/SQL | Direct IF/ELSIF with string/number literals | IF branches with variable references | Dynamic SQL or heuristic pattern | LLM-assisted (future) |
| DDL | CREATE TABLE with declared types | Types inferred from domain | Fallback defaults | |

Studio uses confidence to:
- Sort candidate lists (highest first)
- Show a badge: `High`, `Medium`, `Low`
- Warn when accepting `Low` confidence items (`< 0.5`)

### 8.3 Conflict Detection (post-MVP)

When two sources produce artifacts that disagree (e.g., copybook says field
is PIC X(10), DDL says VARCHAR2(20)), LE emits an `extraction_warning` of
kind `cross_source_conflict`. These warnings feed the Studio Conflicts
panel. MVP does not include cross-source correlation — it ships per-source
extraction only.

---

## 9. Parser Boundary Discipline

### 9.1 One Plugin Per Language

LE is organized as a **parser plugin registry**. Each extractor:

- Lives in its own Python module (`le_plugins.plsql`, `le_plugins.cobol`, …)
- Declares the source types it handles
- Implements a common interface: `parse(file_bytes) -> ParseResult`
- Has its own test fixture suite
- Can be independently versioned and released

A parser plugin **cannot call another plugin**. Cross-source correlation
(e.g., joining copybook field definitions with DDL table definitions) lives
in a separate correlation layer that consumes artifacts from both plugins
as normalized JSON — not by having the copybook parser invoke the DDL parser.

### 9.2 Why This Matters

- Parser bugs stay contained
- New languages can be added without touching existing ones
- Language-specific grammar libraries (ANTLR for PL/SQL, a hand-rolled
  recursive-descent for copybook, tree-sitter for Java) can coexist without
  forcing a single framework

### 9.3 MVP Plugin

MVP ships exactly one plugin: **`plsql`**. It uses a deterministic grammar
(ANTLR-generated or hand-rolled — implementation choice during the slice).
LLM-assisted extraction is **not** in the MVP plugin.

### 9.4 LLM-Assisted Extraction (Future, Explicit)

Post-MVP, a plugin may offer an optional LLM-assisted extraction mode for
paths the deterministic parser cannot resolve (e.g., dynamic SQL strings
built at runtime). Such artifacts:

- Carry `confidence < 0.5`
- Include a `llm_assisted: true` flag on the provenance
- Must be reviewed by a human before acceptance — the flag is surfaced in
  the Studio UI

LLM assistance is **never** the primary path. A plugin without a
deterministic mode is rejected at the LE boundary.

---

## 10. Error Handling and Partial Extraction

### 10.1 Partial Extraction Is a First-Class Outcome

Legacy sources are often malformed, vendor-specific, or missing context.
LE must handle this gracefully:

- **Never fail the whole file** because of one unparseable section
- Emit whatever artifacts could be extracted
- Emit an `extraction_warning` for each unparseable section with:
  - line range
  - reason code (e.g., `UNKNOWN_PIC_CLAUSE`, `DYNAMIC_SQL_UNRESOLVED`)
  - human-readable message

### 10.2 Error Categories

| Category | Example | LE behavior |
|----------|---------|-------------|
| Unsupported construct | COBOL `CICS` macro embedded in copybook | Skip + warning |
| Vendor-specific extension | Oracle hint `/*+ INDEX(...) */` inside PL/SQL | Strip + continue |
| Genuinely malformed | Unclosed BEGIN block | Skip procedure, continue file |
| File encoding issue | EBCDIC bytes in presumed ASCII file | Ingest error, no artifacts |
| Oversized file | 50MB single PL/SQL file | Ingest error with size limit message |

### 10.3 Warnings Surface in Studio

`extraction_warning` records flow into:
- The ingestion result returned from `ingest_source`
- Studio Step 1 Knowledge Workspace (shown on the uploaded file card)
- Studio Step 6 right-rail Conflicts panel (advisory tier, amber)

---

## 11. Integration with EdgeForge Components

This is the section that answers: **"How does LE interact with every other
piece of EdgeForge?"**

### 11.1 Integration with Engine

**Direct integration: none.**

LE never calls Engine code directly. LE outputs flow through Studio, which
composes the manifest and invokes Engine MCP `generate_app`. Engine remains
unaware of LE's existence.

However, **LE output shapes are designed to conform to Engine input
contracts**:

- `extracted_rule_candidate.proposed_rule` matches the rules YAML shape
  consumed by the Engine rule ingestion (`appbuilder/rules/ingestion.py`)
- `extracted_schema.proposed_entity` matches the entity shape the Engine
  expects after metadata translation
- Operation candidates match the OpenAPI/sample JSON shape the Engine
  consumes during translation

This conformance is a **contract**. When Engine adds a new rule type (like
the cross-entity business rules in PR #121), LE rule candidate kinds must
extend to match. The mapping table is maintained in this doc, updated when
Engine rule contract changes.

### 11.2 Integration with Engine MCP

**None.**

LE does not call Engine MCP tools. LE does not appear in the Engine MCP
allowed-tools list. The two MCP servers are fully separate processes with
no runtime coupling. Studio is the only orchestrator that talks to both.

### 11.3 Integration with Knowledge Server

LE and KS are **peer MCP servers**. They do not share state or storage.
They interact through two narrow, intentional surfaces.

#### 11.3.1 LE → KS push (optional, post-MVP)

`push_to_knowledge_server(project_id, artifact_ids[], ks_project_id)` takes
accepted LE artifacts and writes them into KS via the KS ingestion tools.
Pushed artifacts appear in KS as:

- Field catalog rows (for `extracted_field` and `extracted_schema` fields)
- Documents with full extracted text (for `extracted_rule_candidate` source
  snippets, enabling BM25 search against LE-sourced content)
- Evidence chains tagged with `extraction-source: <file>` so KS
  `get_field_evidence_chain` shows the LE origin

KS does not need to be LE-aware. LE formats its pushes to conform to KS's
existing ingestion tools.

#### 11.3.2 Shared `project_id` namespace

Studio uses the same `project_id` across Engine MCP, KS, and LE. A project
in Studio maps 1:1:1 across all three MCP servers. Namespace collisions are
impossible because each server owns its own storage.

### 11.4 Integration with Studio

Studio is LE's primary consumer. Integration is scoped through the existing
Studio UX v2 frame:

#### 11.4.1 Step 1 — Knowledge Workspace

A new **"Structural Sources"** subsection appears under the existing
Knowledge Workspace surface. Authors upload copybooks, PL/SQL, DDL, etc.
Each uploaded file is sent to LE via `ingest_source` and appears as a card
showing:

- source type (with icon)
- ingestion status (`parsed`, `partial`, `failed`)
- extraction summary (e.g., "12 rule candidates, 3 warnings")
- warnings count with click-to-expand

MVP: PL/SQL upload only. Other source types show "Coming in a later release."

#### 11.4.2 Step 3 — Right-rail Suggestions

LE-sourced entity suggestions appear alongside KS field suggestions in the
right-rail Suggestions panel. Cards carry an
**`origin: legacy-extractor`** badge to distinguish them from KS
suggestions. The same accept / edit / reject action model applies.

MVP: not included — no entity extraction in MVP.

#### 11.4.3 Step 6 — Right-rail Suggestions (Rules)

LE-sourced rule candidates appear in the Step 6 Suggestions panel. This is
the **primary MVP surface**. Card shape:

```
┌─────────────────────────────────────────────┐
│ [legacy-extractor] [High confidence]        │
│ cross-entity-field-check                    │
│                                             │
│ Transaction.accountId  →  Account.status    │
│ must be: ACTIVE                             │
│                                             │
│ Source: PKG_TRANSACTION.POST_DEBIT L142-148 │
│                                             │
│ [ Accept ]  [ Edit ]  [ Reject ]            │
└─────────────────────────────────────────────┘
```

Accepting writes a rule entry into the appropriate rules YAML file using
the cross-entity rules design from PR #121.

#### 11.4.4 Right-rail Evidence Panel

When a user clicks a rule candidate card, the Evidence panel shows:

- source file name + line range
- the source expression verbatim (capped at 500 chars)
- extractor name + version
- link to open the file in a modal viewer (future)

The Evidence panel remains **read-only**, consistent with the Studio UX v2
spec — LE evidence is displayed, not authored.

#### 11.4.5 Right-rail Conflicts Panel

`extraction_warning` records surface here as advisory entries. `cross_source_conflict`
warnings (post-MVP) become structured conflict cards in the main pane at Step 6.

#### 11.4.6 Step 7 — Provenance and Decision History

Accepted LE artifacts appear in Step 7 decision history with:

- origin column: `legacy-extractor`
- source file + line range
- extractor version

The `extraction-source` pointer carries through to Step 8
`evidence-trail.json` export, giving downstream tooling full provenance
back to the original legacy source.

MVP: Not included; Studio stores LE acceptance in the same review-state
buckets as KS suggestions, but provenance column is a later slice.

#### 11.4.7 Studio save/open (project workspace)

Studio workspace state gains an `le_project_id` field alongside the existing
`ks_project_id`. This requires a version bump to `studio_project_schema_version: "1.2"`.
The current shipped baseline is `"1.1"` (KS linkage, evidence_links, manifest_revisions).
LE linkage is the `"1.2"` addition — implemented in Phase 6.2 Step 6, not before.
This links a Studio project to its LE namespace, enabling project reopen to rehydrate
uploaded sources and extraction status.

### 11.5 Summary Matrix

| Component | LE calls it? | It calls LE? | Shared data |
|-----------|:------------:|:------------:|-------------|
| Engine | No | No | Output shape conforms to Engine rule/entity contract |
| Engine MCP | No | No | None |
| Knowledge Server | No (except push) | No | `project_id` namespace convention |
| Studio | No | Yes — via LE MCP stdio | Project workspace linkage + suggestion review buckets |
| Generated application | No | No | None — no runtime coupling |
| TestBench | No | No | None |

---

## 12. Security, Sandboxing, and Resource Limits

### 12.1 Local stdio only for Phase 6

Like Engine MCP and KS, LE ships as a **local stdio subprocess**. No HTTP,
no network listeners, no auth. Deployed models (shared server, HTTP
transport, multi-tenant) are explicitly out of Phase 6 scope.

### 12.2 Path Validation

`LEGACYEXTRACTOR_ALLOWED_ROOTS` env var mirrors the Engine MCP pattern. All
file paths in tool arguments must resolve under a configured root. Path
traversal is rejected before any file read.

### 12.3 Parser Sandboxing

Parsers must not:
- Spawn subprocesses
- Open network sockets
- Write to disk outside the LE project store
- Execute any content from the parsed source (no eval, no dynamic loading)

Parsers **may**:
- Read from disk under the project root
- Write parsed artifacts to the project store under a configured path

### 12.4 Resource Limits

| Limit | MVP default | Rationale |
|-------|-------------|-----------|
| Max single-file size | 10 MB | Larger files indicate concatenated exports; request splitting |
| Max parse wall time per file | 60 seconds | Catches runaway grammars |
| Max artifacts per file | 500 | Sanity upper bound; most PL/SQL packages produce <50 |
| Max project artifact store size | 500 MB | Can be raised via config if needed |

Exceeding a limit produces an ingestion error with a clear reason code.

### 12.5 PII and Data Handling

Legacy sources may contain test data, hard-coded credentials, or PII. LE
responsibilities:

- Do **not** emit literal string values into `extracted_rule_candidate`
  expected-value fields if the value looks credential-like (regex matches
  for common patterns)
- Flag credential-pattern matches as `extraction_warning` with kind
  `possible_credential_in_source` — the author should strip these upstream
- Leave full raw source text on disk unmodified — LE is not a redaction tool

---

## 13. Implementation Phasing

### Phase 6.0 — Design (this doc)

1 focused design day. This doc is the deliverable.

### Phase 6.1 — MVP: PL/SQL extractor (first-value slice)

| Step | Scope | Size |
|------|-------|------|
| 1 | Scaffold LE repo (`EdgeForgeLegacyExtractor`), FastMCP server shell, allowed-roots config, stdio entry point | S |
| 2 | `ingest_source`, `list_sources`, `get_source` tools with project-scoped storage | M |
| 3 | PL/SQL parser plugin (ANTLR grammar + visitor) producing AST | L |
| 4 | Rule candidate extractor (IF/ELSIF conditions → `cross-entity-field-check` / `cross-entity-field-compare` / `cross-entity-field-in` candidates) | M |
| 5 | Operation candidate extractor (procedure signatures) | S |
| 6 | `list_extracted_rule_candidates`, `list_extracted_operation_candidates` tools | S |
| 7 | Provenance records with SHA-256 source hash and line-range citations | S |
| 8 | Tests: fixture packages covering common PL/SQL patterns; golden contract on extraction output | M |

Estimated duration: **10-12 working days** per the sequencing doc.

### Phase 6.2 — Studio MVP integration

| Step | Scope | Size |
|------|-------|------|
| 1 | Studio `le_integration.py` adapter (subprocess launch, tool invocation), mirroring `ks_integration.py` | S |
| 2 | Step 1 Knowledge Workspace "Structural Sources" subsection for PL/SQL upload | M |
| 3 | Step 6 right-rail Suggestions — `origin: legacy-extractor` badge and rule candidate cards | M |
| 4 | Accept path: write accepted candidates into rules YAML via Studio save/open | M |
| 5 | Evidence panel shows LE provenance for selected rule candidate | S |
| 6 | `studio_project_schema_version` bump to `"1.2"` adding `le_project_id` | S |

Estimated duration: 1 focused slice, parallel to later Studio UX v2 slices.

### Phase 6.3 — Copybook slice

Second extractor: COBOL copybooks. Adds `list_extracted_schemas` and
`list_extracted_fields` tools. Adds Step 3 right-rail integration.

### Phase 6.4 — DDL slice

Third extractor: Oracle DDL. Enables cross-source correlation (copybook vs
DDL).

### Phase 6.5 — Cross-source correlation + conflict model

Adds the correlation layer and `cross_source_conflict` warnings. Surfaces
structured conflict cards in Studio Step 6 main pane.

### Phase 6.6 — LE → KS push

`push_to_knowledge_server` tool. Enables cross-project reuse of accepted
LE artifacts via KS.

### Phase 6.7 — Additional extractors

Legacy Java, JCL, DCLGEN, EBCDIC layouts. Each is its own slice, added as
demand justifies.

---

## 14. Open Questions

Resolve before Phase 6.1 implementation starts:

1. **Grammar library choice for PL/SQL**: ANTLR (mature, large grammar
   available) vs hand-rolled (full control, more work). Recommendation:
   ANTLR, using an existing open-source Oracle PL/SQL grammar as starting
   point.

2. **Artifact storage format**: SQLite (like KS) vs flat JSON files vs
   JSONL. Recommendation: SQLite — same pattern as KS, supports efficient
   filtered queries, atomic writes.

3. **`extracted_rule_candidate` kind coverage in MVP**: does MVP emit only
   `cross-entity-field-check`, or also `cross-entity-field-compare` and
   `cross-entity-field-in`?
   Recommendation: all three, since the Engine already supports them via
   PR #121.

4. **How to represent IF/ELSIF branches that produce multiple rules**: one
   rule candidate per branch, or a grouped candidate? Recommendation: one
   per branch, each with its own line range — cleaner provenance.

5. **Handling PL/SQL calls to external procedures**: recursively parse or
   treat as opaque? Recommendation: treat as opaque in MVP; emit an
   `extraction_warning` noting the external call; correlation is a later
   slice.

6. **Studio upload mechanism**: does Studio pass file contents inline, or a
   file path?
   **Resolved: file path.** `ingest_source` takes `file_path` — a path
   relative to `LEGACYEXTRACTOR_ALLOWED_ROOTS`, not inline file bytes.
   Studio places uploaded source files into the LE project root (a
   Studio-managed directory under the allowed root) and passes the relative
   path to `ingest_source`. This is consistent with Engine MCP's path-based
   model, keeps MCP payloads small, and gives LE full control over file
   reading within its sandbox. This closes the question — tool schema in
   Section 6.2 and the appendix example both use `file_path` and are now
   consistent.

7. **Versioning strategy across extractors**: one LE version vs per-plugin
   versioning. Recommendation: LE server has its own semver; each plugin
   has its own semver; artifacts carry both.

---

## 15. Appendix: Example Payloads

### 15.1 `ingest_source` request/response

**Request:**
```json
{
  "project_id": "proj-abc123",
  "file_path": "specs/plsql/pkg_transaction.pkb",
  "source_type": "plsql"
}
```

**Response:**
```json
{
  "status": "ok",
  "result": {
    "source_id": "src-20260421-00007",
    "source_type": "plsql",
    "file_name": "pkg_transaction.pkb",
    "ingested_at": "2026-04-21T14:22:33Z",
    "summary": {
      "procedures_parsed": 8,
      "rule_candidates": 12,
      "operation_candidates": 8
    },
    "warnings": [
      {
        "kind": "dynamic_sql_unresolved",
        "line_range": [215, 220],
        "message": "Dynamic SQL construction could not be resolved statically"
      }
    ]
  }
}
```

### 15.2 `list_extracted_rule_candidates` response

```json
{
  "status": "ok",
  "result": {
    "candidates": [
      {
        "artifact_id": "le-rc-20260421-00042",
        "kind": "cross-entity-field-check",
        "proposed_rule": {
          "entity": "Transaction",
          "field": "accountId",
          "type": "cross-entity-field-check",
          "target-entity": "Account",
          "target-field": "status",
          "operator": "eq",
          "expected-value": "ACTIVE"
        },
        "source_expression": "IF v_account.status <> 'ACTIVE' THEN RAISE account_not_active; END IF;",
        "source_procedure": "PKG_TRANSACTION.POST_DEBIT",
        "source_line_range": [142, 148],
        "confidence": 0.92,
        "provenance": {
          "source_file": "specs/plsql/pkg_transaction.pkb",
          "source_hash": "sha256:ab12cd34...",
          "extractor": "plsql",
          "extractor_version": "0.1.0",
          "extracted_at": "2026-04-21T14:22:33Z"
        }
      }
    ],
    "total": 12,
    "cursor": null
  }
}
```

### 15.3 Minimal MCP client config

```json
{
  "mcpServers": {
    "legacy-extractor": {
      "command": "python",
      "args": ["-m", "legacyextractor.mcp_server"],
      "cwd": "/path/to/EdgeForgeLegacyExtractor",
      "env": {
        "LEGACYEXTRACTOR_ALLOWED_ROOTS": "/path/to/studio-projects"
      }
    }
  }
}
```

---

## Change Log

| Date | Change |
|------|--------|
| 2026-04-21 | Initial design — full scope + MVP + integration with all EdgeForge components |
