# Knowledge Server — Broader Suggestion Scopes and Optional AI Assistance

**Status:** Implemented through KS PR #23 (May 2026); design remains the broader-scope contract
**Version:** 1.4  
**Date:** April 2026  
**Author:** Claude Code (architecture review)  
**Branch:** `claude/docs/ks-broader-suggestion-scopes`  
**Updated by:** `claude/docs/sync-ks-broader-scope-with-ux-v3` — aligned with Studio UX v3 (PR #132)

---

## Executive Summary

The shipped KS + Studio MVP delivers deterministic field suggestions with evidence-backed citations for CRUD entity authoring. This design extends that foundation in three directions:

1. **Broader suggestion scopes** — rule suggestions, mapping/transform suggestions, validation hints, state-transition hints, cross-entity rules, conflict resolution, and portfolio reuse — all delivered as new `scope` values on a generic `suggest_manifest_candidates` tool rather than a proliferation of typed tools.

2. **Evidence model extension** — the existing citation and evidence-chain model is generalized from field-only to any suggestion type, with a new `get_suggestion_evidence_chain` tool that replaces the field-specific one.

3. **Optional AI provider layer** — a strictly optional, provider-pluggable AI adapter lives entirely inside KS. Studio never calls an AI provider directly. Deterministic retrieval remains the enterprise-safe default; AI is an opt-in enhancement enabled by environment config.

**Key constraint preserved throughout:** KS suggests only. Studio owns human review. Engine consumes only approved manifests. AI is optional and provider-neutral.

**Implementation sequencing note:** The Kafka router PRs 1–8 are merged, Studio
Phase S readiness is complete, and KS-B0 through KS-B4 are implemented as of the
May 2026 baseline. Historical wave gates in §10 are preserved as implementation
record; they are no longer active blockers for the shipped scopes.

**UX gate note:** The S8 / OQ6 multi-type badge and drawer pattern is defined in
[Studio UX v3 Multi-Type Suggestion Drawer Pattern](./studio-ux-v3-suggestion-drawer-pattern.md)
and is the Studio UX contract for KS-B2 / KS-B3 suggestion surfaces.

**Implementation note — May 2026:** KS-B0 through KS-B4 are implemented through
KS PR #23. Deterministic retrieval remains SQLite FTS5/BM25. No LLM/provider
integration exists; KS-B5 gates any future provider/model layer.

---

## Table of Contents

1. [Current State Assessment](#1-current-state-assessment)
2. [Suggestion Type Taxonomy](#2-suggestion-type-taxonomy)
3. [Tool Contract Design](#3-tool-contract-design)
4. [Suggestion Payload Schema](#4-suggestion-payload-schema)
5. [Evidence and Provenance Model](#5-evidence-and-provenance-model)
6. [Decision Write-Back](#6-decision-write-back)
7. [Optional AI Provider Layer](#7-optional-ai-provider-layer)
8. [Studio UX v3 Integration](#8-studio-ux-v3-integration)
9. [Archetype Coverage](#9-archetype-coverage)
10. [Implementation Sequencing](#10-implementation-sequencing)
11. [Non-Goals](#11-non-goals)
12. [Open Questions](#12-open-questions)
13. [Recommendation](#13-recommendation)

---

## 1. Current State Assessment

### 1.1 What Is Actually Shipped

The following is the May 2026 baseline after KS PR #23 and Studio PR #143.

| Scope | KS status / PR | Studio surface |
|-------|----------------|----------------|
| `fields` | Implemented; original MVP plus generic `suggest_manifest_candidates` path | Step 3 field review / full-width KA Review |
| `validations` | Implemented through broader-scope waves | Step 3 validation hints; can materialize Step 6 validation rules |
| `rules` | Implemented through broader-scope waves | Step 6 rule suggestion drawer |
| `cross_entity_rules` | Implemented through broader-scope waves | Step 6 cross-entity rule suggestion drawer |
| `mappings` | Implemented through broader-scope waves | Mapping review / evidence surfaces where seed data supports it |
| `transforms` | Implemented; Kafka router transform suggestions via KS PR #21 | Kafka router transform suggestion review |
| `conflict_resolution` | Implemented; field-level structured deltas via KS PR #23 | Step 7 advisory review; advisory only, no generated-app change implied |
| `portfolio_reuse` | Implemented through KS-B3 | Step 7 advisory review; advisory only, no generated-app change implied |

Current constraints:

- deterministic SQLite FTS5/BM25 retrieval is the shipped default
- no LLM/provider integration exists; KS-B5 gates any future provider/model layer
- `suggest_fields` and `get_field_evidence_chain` remain backward-compatible aliases
- Studio owns human review and manifest authoring; KS never writes the manifest

### 1.2 What the Current Design Docs Planned (Partially Stale)

> This section is preserved as implementation context. The current shipped
> baseline is in §1.1 above.

The `knowledge-server-mcp-design.md` describes a 12-tool set that includes `suggest_rules`, `suggest_mappings`, `compare_requirements`, `detect_conflicts`, `prefill_manifest_section`, and `search_portfolio`. These are planned intentions, not shipped implementations. This design supersedes that older tool list for the broader-scope work.

### 1.3 The Stable Foundation to Build On

These are solid and should not be redesigned:
- `suggestion_id` stability via `stable_field_suggestion_id()` hash
- `status` lifecycle: `pending → accepted | edited | rejected`
- `submit_suggestion_decisions()` write-back contract
- Citation model (`Citation`, `EvidenceChunk`) — reuse as-is
- BM25/FTS5 search + field catalog — extend, not replace
- Subprocess lifecycle and MCP stdio protocol in Studio

---

## 2. Suggestion Type Taxonomy

### 2.1 All Suggestion Types

| Type | Source Artifacts | Target Studio Step | Manifest Path Convention | Deterministic-Only Feasible? | AI Improves? | Engine Contract Awareness Required? | First Wave? |
|---|---|---|---|---|---|---|---|
| `field` (shipped) | DDL, Excel, BRD, CSV | Step 3 (CRUD) | `entities.{E}.fields.{F}` | ✓ | Semantic matching, synonym resolution | No | Shipped |
| `rule` | BRD, markdown, DDL constraints | Step 6 | `rules.{E}.{rule-id}` | Partial — pattern/constraint rules yes; semantic business rules weak | Yes — reasoning over natural-language rules | No | **Wave 1** |
| `cross_entity_rule` | BRD, entity catalog, relationships | Step 6 | `rules.cross.{rule-id}` | Partial — foreign-key style rules yes | Yes | No (design already in `crud-cross-entity-rules-design.md`) | **Wave 1** |
| `validation` | DDL constraints, BRD specs, field catalog | Step 3 | `entities.{E}.fields.{F}.validation` | ✓ — type/length/null/regex from DDL | Minor | No | **Wave 1** |
| `mapping` | DDL, OpenAPI, BRD field lists | Step 4 (passthrough) | `upstream_interfaces.{I}.operations.{O}.mappings.{F}` | Partial — name-match and type-compatible fields yes; semantic match weak | Yes | Yes — upstream/downstream schema shapes | **Wave 2** |
| `transform` (passthrough) | Transform examples, DDL, BRD | Step 4 | `async_routes.{name}.transform_mapping` | Partial | Yes | Yes — passthrough contract | **Wave 2** |
| `transform` (Kafka router) | Kafka schemas, BRD | Kafka step 3 | `async_routes.{name}.router_config.targets.{T}.request_transform` | Partial | Yes | Yes — router contract is stable for the May 2026 baseline | **Wave 3** |
| `state_transition` | BRD workflow docs, entity fields | Step 6 | `entities.{E}.state_transitions.{T}` | Weak — needs explicit workflow section in docs | Yes | Moderate — depends on entity model | Future |
| `conflict_resolution` | Any conflicting documents | Step 7 | N/A — surfaces existing conflict, not manifest path | ✓ — existing `find_conflicts` tool | AI can rank/explain options | No | **Wave 2** |
| `portfolio_reuse` | Cross-project KS DB | Any step | Depends on matched pattern | ✓ — existing `search_across_projects` | AI can match semantic patterns | No | **Wave 2** |
| `le_candidate` | LegacyExtractor output | Any step | Depends on artifact type | ✓ — pass-through provenance | N/A — LE does extraction | No | **Wave 4 / Future** |

### 2.2 Wave Definitions

- **Wave 1** (first safe implementation slice): `rule`, `cross_entity_rule`, `validation` — all CRUD-native, no new Engine contract dependencies, deterministic-feasible
- **Wave 2**: `mapping`, `transform` (passthrough), `conflict_resolution`, `portfolio_reuse` — requires passthrough contract awareness; passthrough is stable
- **Wave 3**: `transform` (Kafka router) — Kafka router PRs 1–8 are merged; **blocked on `router_config` schema and `RouterConfig` Pydantic model stability confirmation** before KS can index or suggest against those manifest paths
- **Wave 4 / Future**: `state_transition`, `le_candidate` — depends on LegacyExtractor MVP

---

## 3. Tool Contract Design

### 3.1 Option A vs Option B Assessment

**Option A — Separate typed tools** (`suggest_rules`, `suggest_mappings`, `suggest_transforms`, etc.):
- Pros: maximum type clarity per tool, each callable independently
- Cons: tool count explodes (13 → 20+), MCP tool surface becomes harder to navigate, each new suggestion type requires a new tool registration

**Option B — Generic typed tool with `scope` parameter** (`suggest_manifest_candidates(scope=...)`):
- Pros: single tool entry point, scope can grow without new tool registration, consistent payload envelope, one `submit_suggestion_decisions` works for all types
- Cons: payload `data` field varies by scope — callers must know the typed shape per scope

**Recommendation: Option B.** The 13-tool KS surface is already at a comfortable limit. Adding a `suggest_manifest_candidates` tool (replacing `suggest_fields`), a generic `get_suggestion_evidence_chain` (replacing `get_field_evidence_chain`), and keeping `submit_suggestion_decisions` unchanged gives a **target total of 14 active tools** — adding only 1 net new tool while covering all future suggestion types.

**Transitional tool count:** During the Studio migration window (between KS-B1 deploying and Studio switching its call sites to the new tool names), the MCP-registered surface is **16 tools** — the 14 target tools plus the two deprecated aliases (`suggest_fields`, `get_field_evidence_chain`). The aliases are removed in a single coordinated KS+Studio release once all Studio call sites have migrated. If the KS-B1 KS changes and the Studio `ks_integration.py` update land in the same PR set, the surface goes directly to 14 with no transitional period.

### 3.2 Recommended Tool Set (Post-Broader-Scopes)

| Tool | Status | Notes |
|---|---|---|
| `ingest_document` | Shipped — keep | No change |
| `list_documents` | Shipped — keep | No change |
| `search_documents` | Shipped — keep | No change |
| `read_document` | Shipped — keep | No change |
| `read_field_catalog` | Shipped — keep | No change |
| `get_evidence` | Shipped — keep | No change |
| `find_conflicts` | Shipped — keep | No change |
| `delete_document` | Shipped — keep | No change |
| `search_across_projects` | Shipped — keep | No change |
| `suggest_manifest_candidates` | **New — replaces `suggest_fields`** | Typed by `scope`; field scope is backward-compatible |
| `get_suggestion_evidence_chain` | **New — replaces `get_field_evidence_chain`** | Generic across all suggestion types |
| `submit_suggestion_decisions` | Shipped — **extend payload** | Typed `edited_payload` per suggestion_type; backward-compatible |
| `compare_field_definitions` | Shipped — keep | No change |
| `ask_document` | **New — optional AI mode only** | Disabled unless AI provider configured; returns evidence-backed answer |

Target total: 14 tools (16 transitional while deprecated aliases remain registered — see §3.1 above). `suggest_fields` and `get_field_evidence_chain` are deprecated aliases that delegate to the new tools; they must remain registered as MCP tools until Studio migrates all call sites, then removed in a coordinated KS+Studio release.

### 3.3 `suggest_manifest_candidates` Contract

```python
suggest_manifest_candidates(
    project_id: str,
    scope: str,                      # "fields" | "rules" | "cross_entity_rules" |
                                     # "validations" | "mappings" | "transforms" |
                                     # "conflict_resolutions" | "portfolio_reuse"
    entity: Optional[str] = None,    # required for entity-scoped scopes
    route_name: Optional[str] = None,# required for mapping/transform scopes
    source_entity: Optional[str] = None,  # for cross-entity and mapping scopes
    target_entity: Optional[str] = None,
    field_name_pattern: Optional[str] = None,  # for field/validation scopes
    min_source_count: int = 1,
    max_suggestions: int = 20,
    ai_mode: Optional[str] = None,   # None | "retrieval" | "generation"; overrides config
) -> SuggestManifestCandidatesResult
```

**Response:**

```python
class SuggestManifestCandidatesResult(BaseModel):
    project_id: str
    scope: str
    entity: Optional[str]
    suggestions: list[ManifestSuggestion]
    source_document_count: int
    warnings: list[str]
    ai_used: bool           # true if AI provider contributed
    provider_name: Optional[str]   # only if ai_used
```

### 3.4 `get_suggestion_evidence_chain` Contract

```python
get_suggestion_evidence_chain(
    project_id: str,
    suggestion_id: str,
) -> SuggestionEvidenceChain
```

Works for any `suggestion_type`. Internally branches to type-specific evidence aggregation.

### 3.5 `ask_document` Contract (AI-only, disabled by default)

```python
ask_document(
    project_id: str,
    question: str,
    doc_ids: Optional[list[str]] = None,   # scope to specific docs; None = all project docs
    max_chunks: int = 10,
) -> AskDocumentResult
```

```python
class AskDocumentResult(BaseModel):
    question: str
    answer: str
    citations: list[Citation]   # mandatory even if AI-generated answer
    confidence: float
    ai_used: bool
    provider_name: str
    warnings: list[str]
```

Returns error if AI provider not configured — never returns an uncited answer.

---

## 4. Suggestion Payload Schema

### 4.1 Generic Envelope

All suggestion types share this envelope. The `payload` field is typed per `suggestion_type`.

```python
class ManifestSuggestion(BaseModel):
    suggestion_id: str             # stable hash: SHA256(scope:project_id:key)[:24]
    suggestion_type: str           # "field" | "rule" | "cross_entity_rule" |
                                   # "validation" | "mapping" | "transform" |
                                   # "conflict_resolution" | "portfolio_reuse"
    project_id: str
    status: str                    # "pending" | "accepted" | "edited" | "rejected"
    confidence: float              # 0.0–1.0; flagged in UI if < 0.5
    confidence_basis: str          # "deterministic" | "ai" | "heuristic"
    title: str                     # short human-readable label
    summary: str                   # 1–2 sentence description
    rationale: str                 # why this suggestion was produced
    target_step: str               # Studio step ID: "step3" | "step4" | "step6" | "step7"
    manifest_path: str             # dot-notation path in manifest
    payload: dict                  # typed per suggestion_type — see §4.2
    citations: list[Citation]      # mandatory; empty list means low-confidence warning
    source_document_ids: list[str]
    created_at: str                # ISO-8601
    updated_at: str
    edited_payload: Optional[dict] = None   # set when status=edited
    provider_metadata: Optional[dict] = None  # only set if AI provider contributed
```

### 4.2 Typed Payload Shapes

#### `field` (backward-compatible with shipped MVP)

```python
{
    "entity": "Account",
    "field_name": "amountMinorUnits",
    "suggested_type": "BIGINT",
    "suggested_length": None,
    "nullable": False,
    "description": "Amount in minor currency units (pence/cents)",
    "consistency_score": 0.92,
    "conflict_hint": None
}
```

#### `rule`

```python
{
    "entity": "Account",
    "rule_id": "account-status-allowed-values",
    "rule_type": "allowed_values",    # "allowed_values" | "range" | "not_null" |
                                       # "pattern" | "business_constraint"
    "field": "status",
    "constraint": {
        "values": ["ACTIVE", "SUSPENDED", "CLOSED"]
    },
    "source_excerpt": "Account status must be one of: ACTIVE, SUSPENDED, CLOSED"
}
```

#### `cross_entity_rule`

```python
{
    "rule_id": "payment-account-foreign-key",
    "rule_type": "cross_entity",
    "source_entity": "Payment",
    "source_field": "accountId",
    "target_entity": "Account",
    "target_field": "id",
    "operator": "references",     # from named operator set in cross-entity rules design
    "description": "Payment.accountId must reference a valid Account.id"
}
```

#### `validation`

```python
{
    "entity": "Account",
    "field": "sortCode",
    "validation_type": "pattern",
    "pattern": "^\\d{2}-\\d{2}-\\d{2}$",
    "error_message": "Sort code must be in format NN-NN-NN",
    "source_excerpt": "Sort code format: XX-XX-XX (6 digits with dashes)"
}
```

#### `mapping` (passthrough-router / Kafka)

```python
{
    "route_name": "loan_router",
    "direction": "request",          # "request" | "response"
    "source_entity": "RORequest",
    "target_entity": "D1Request",
    "source_field": "loanAmount",
    "target_field": "amount",
    "mapping_type": "copy",          # "copy" | "value_map" | "constant" | "transform"
    "confidence_basis": "name_match_and_type_compatible",
    "value_map": None
}
```

#### `transform` (Kafka router — Wave 3, router contract must be stable)

```python
{
    "route_name": "loan_router",
    "target_id": "d1_processor",
    "direction": "request",
    "transform_file_suggestion": "transforms/ro-to-d1-request.yaml",
    "mappings": [
        {
            "source": "$.loanAmount",
            "target": "$.amount",
            "type": "copy"
        },
        {
            "source": "$.country",
            "target": "$.region",
            "type": "value_map",
            "value_map": { "UK": "EMEA", "US": "AMER", "default": null }
        }
    ],
    "missing_required_fields": [],
    "coverage_warnings": []
}
```

#### `state_transition` (Future / Wave 4)

```python
{
    "entity": "Loan",
    "from_state": "PENDING",
    "to_state": "APPROVED",
    "trigger": "approval_decision == APPROVED",
    "guard": "amount <= credit_limit",
    "source_excerpt": "Loan moves to APPROVED when credit check passes"
}
```

---

## 5. Evidence and Provenance Model

### 5.1 Stable Citation Model — No Change

The existing `Citation` model is sufficient. It is reused as-is for all suggestion types:

```python
Citation(
    document_id, document_name, chunk_id, content_hash, parser_version,
    page, section, heading, char_offset, snippet
)
```

### 5.2 Confidence Model

| `confidence_basis` | How computed | Deterministic? |
|---|---|---|
| `deterministic` | Source count, consistency score, absence of conflicts | ✓ |
| `heuristic` | Name match, type compatibility, pattern match | ✓ |
| `ai` | Model confidence score + citation grounding | Requires AI provider |

Rule: every suggestion must carry at least one citation when `confidence_basis` is `deterministic` or `heuristic`. If citation list is empty, `confidence` is capped at 0.3 and a warning is added to `warnings[]`.

AI-generated suggestions without grounded citations must not be returned. If the AI provider cannot produce citations, fall back to deterministic mode.

### 5.3 Generic `SuggestionEvidenceChain`

```python
class SuggestionEvidenceChain(BaseModel):
    suggestion: ManifestSuggestion
    evidence_chunks: list[EvidenceChunk]   # full-text supporting evidence
    related_suggestions: list[str]         # suggestion_ids of related items
    conflict_summary: Optional[str]
    source_document_count: int
    ai_used: bool
```

The existing `FieldEvidenceChain` is a special case of this. `get_field_evidence_chain` becomes a deprecated alias.

### 5.4 Evidence Scoping — Avoiding Entity Bleed

Evidence retrieval for a suggestion must be scoped to relevant documents:

- Field/validation/rule/cross-entity suggestions: scope search to documents that contain the entity name
- Mapping suggestions: scope to documents that contain both source and target entity names
- Transform suggestions: scope to schema files and BRD sections referencing the route name
- Portfolio reuse suggestions: explicitly cross-project — surfaced separately, labeled `portfolio-pattern` provenance

This prevents an Account-entity suggestion from pulling in citations about a Payment entity that happens to share field names.

### 5.5 `evidence-trail.json` Extension

The existing v1.0 schema is extended with a `suggestion_type` field per evidence link and a `by_type` breakdown object in the `provenance_summary` (replaces the implied field-only count with a per-type map):

```json
{
  "schema_version": "1.1",
  "evidence_links": [
    {
      "manifest_path": "rules.Account.account-status-allowed-values",
      "suggestion_type": "rule",
      "provenance": "ai-accepted",
      "suggestion_id": "s-...",
      "confidence": 0.81,
      "citations": [...]
    }
  ],
  "provenance_summary": {
    "human_authored": 14,
    "ai_accepted": 8,
    "ai_edited": 3,
    "no_evidence": 5,
    "by_type": {
      "field": 12,
      "rule": 6,
      "validation": 3,
      "mapping": 2,
      "cross_entity_rule": 4
    }
  }
}
```

### 5.6 Step 7 Provenance — Non-Field Suggestions

Step 7 must display non-field suggestion provenance using the same annotation model (human-authored, ai-accepted, ai-edited, no-evidence) but grouped by suggestion type. Per the UX v3 pattern, Step 7 shows a `📋 Evidence used` link (only when ≥1 suggestion was accepted/edited). Clicking it opens a provenance drawer grouped by suggestion type: fields → rules → validations → mappings → transforms, each section with its own provenance badges.

---

## 6. Decision Write-Back

### 6.1 Recommendation: Extend Existing Tool

**Do not introduce a new write-back tool.** The existing `submit_suggestion_decisions` contract is already type-agnostic at the wire level — it takes `suggestion_id` + `status` + `edited_payload`. The only gap is that `edited_payload` is currently free-form.

The fix is to validate `edited_payload` against the typed payload shape for the suggestion's `suggestion_type` on the KS side — not to introduce a new tool.

### 6.2 Updated `submit_suggestion_decisions` Contract

```python
submit_suggestion_decisions(
    project_id: str,
    decisions: list[SuggestionDecision],
) -> SubmitSuggestionDecisionsResult

class SuggestionDecision(BaseModel):
    suggestion_id: str
    status: str                           # "accepted" | "edited" | "rejected"
    edited_payload: Optional[dict] = None # typed per suggestion_type; validated server-side
```

KS validates `edited_payload` shape against the suggestion's `suggestion_type` before persisting. If validation fails, the decision outcome is `error` with a structured reason.

### 6.3 Typed Edited Payload Validation

KS maintains a validator map:

```python
EDITED_PAYLOAD_VALIDATORS = {
    "field": validate_field_payload,
    "rule": validate_rule_payload,
    "validation": validate_validation_payload,
    "mapping": validate_mapping_payload,
    "transform": validate_transform_payload,
    "cross_entity_rule": validate_cross_entity_rule_payload,
}
```

Unknown `suggestion_type` values in `edited_payload`: accepted with a warning (forward compatibility).

### 6.4 KS Storage Changes

The existing `field_suggestions` table is renamed to `manifest_suggestions` (backward-compatible migration — no column-level constraint changes required, since `suggestion_type` is already `NOT NULL` with no `DEFAULT`). New indexes are added for the broader-scope access patterns:

```sql
-- Migration: rename table; suggestion_type is already NOT NULL with no default to remove
ALTER TABLE field_suggestions RENAME TO manifest_suggestions;

-- Add indexes for new access patterns (safe to run after rename)
CREATE INDEX IF NOT EXISTS idx_manifest_suggestions_type
    ON manifest_suggestions(suggestion_type);
CREATE INDEX IF NOT EXISTS idx_manifest_suggestions_scope
    ON manifest_suggestions(project_id, suggestion_type, entity_name);

-- No column-level constraint changes required.
-- If a typed CHECK constraint is desired in future, use a table-rebuild migration at that point.
```

### 6.5 Studio Local Review History

Studio records each decision locally in the project save file under `review_history[]`:

```json
{
  "suggestion_id": "s-abc",
  "suggestion_type": "rule",
  "status": "accepted",
  "manifest_path": "rules.Account.account-status-allowed-values",
  "reviewed_at": "2026-04-24T...",
  "edited_payload": null
}
```

Studio batch-submits decisions at step exit or project save — same pattern as field suggestions today.

---

## 7. Optional AI Provider Layer

### 7.1 Three Modes

| Mode | Model required? | Studio calls | KS does | What is sent to model | What is never sent |
|---|---|---|---|---|---|
| **Deterministic retrieval** (default) | No | `suggest_manifest_candidates`, `get_evidence` | BM25 search + field catalog aggregation | N/A | N/A |
| **AI-assisted answer** | Yes | `ask_document` | Retrieves relevant chunks, constructs prompt, calls provider, returns answer + citations | Relevant document chunk text (up to `EDGEFORGE_KS_AI_MAX_CHUNKS` chunks), user question | Project file paths, API keys, credentials, full document text |
| **AI-assisted generation** | Yes | `suggest_manifest_candidates(ai_mode="generation")` | Retrieves candidates, constructs prompt, calls provider for enriched suggestions, validates citations | Relevant document chunk text, entity/field names, suggestion context | Full document text beyond selected chunks, project structure, credentials |

**The enterprise-safe default is deterministic retrieval only.** AI modes are opt-in and require explicit environment configuration.

> **⚠️ AI data handling — KS-B5 implementation requirement:** The table above describes the intended data boundary. The specific mechanisms for chunk selection, content sanitization, and any pre-send redaction or PII-detection gate are **not yet designed** — these are implementation requirements to be specified and built as part of KS-B5, not guarantees of the current system. Until KS-B5 ships with a verified pre-send sanitization implementation, treat the AI provider layer as suitable for non-production or sandboxed environments only. Enterprise production use of AI modes requires a separate data-handling design review before enabling.

### 7.2 Provider Adapter Boundary

All AI interaction is encapsulated in a `providers/` module inside KS. Studio never imports or calls an AI provider.

```python
# knowledge_server/providers/base.py

class AIProvider(Protocol):
    provider_name: str

    def answer_with_citations(
        self,
        question: str,
        context_chunks: list[str],
        citations: list[Citation],
        max_tokens: int = 1000,
    ) -> tuple[str, float]:
        """Returns (answer_text, confidence_score)."""
        ...

    def generate_suggestions(
        self,
        scope: str,
        context_chunks: list[str],
        citations: list[Citation],
        entity_context: dict,
        max_suggestions: int = 10,
    ) -> list[dict]:
        """Returns list of raw suggestion payloads to be wrapped and validated."""
        ...
```

**Concrete implementations:**

```
knowledge_server/providers/
  base.py              # AIProvider protocol
  openai_provider.py   # OpenAI / GPT-4 adapter
  anthropic_provider.py# Anthropic / Claude adapter
  gemini_provider.py   # Google Gemini adapter
  local_provider.py    # Local model adapter (Ollama or similar)
  factory.py           # resolve_provider(config) → AIProvider | None
```

### 7.3 Config Expectations

| Setting | Source | Default |
|---|---|---|
| `EDGEFORGE_KS_AI_PROVIDER` | Environment variable | `none` (disabled) |
| `OPENAI_API_KEY` | Environment variable | Not set |
| `ANTHROPIC_API_KEY` | Environment variable | Not set |
| `GEMINI_API_KEY` | Environment variable | Not set |
| `EDGEFORGE_KS_AI_MODEL` | Environment variable | Provider default |
| `EDGEFORGE_KS_AI_MAX_CHUNKS` | Environment variable | `10` |
| `EDGEFORGE_KS_AI_MAX_TOKENS` | Environment variable | `1000` |

Rules:
- `EDGEFORGE_KS_AI_PROVIDER=none` (or unset) → AI entirely disabled; `ask_document` returns a clear error
- No API key stored in Studio project files, workspace files, or KS SQLite database
- Model selection is advisory — KS may override for cost or capability reasons
- Chunk limit enforced before any API call — controls cost

### 7.4 Graceful Degradation

If AI provider is configured but call fails (network, rate limit, quota):
- Log the error with provider name and error code
- Retry once with exponential backoff
- Return deterministic-mode result with `ai_used: false` and a warning in `warnings[]`
- Never surface provider error details or partial AI output to Studio

If AI provider is configured and returns a suggestion with no supporting citations:
- Discard the suggestion
- Log a warning
- Fall back to deterministic candidates for that scope

---

## 8. Studio UX v3 Integration

> **Design alignment note:** Section 8 was updated in v1.2 to align with the
> Studio UX v3 / Assistive Features design (PR #132,
> `docs/studio-ux-v3-assistive-features-design.md`). The v2 integration model
> (always-visible right-rail panels, unconditional degraded-mode banners) is
> superseded. The canonical Studio integration reference is now PR #132.

### 8.1 Core Integration Constraints from Studio UX v3

The Studio UX v3 design establishes constraints that all KS-B1/B2/B3 Studio work
must respect. These are not optional refinements — they are the design baseline:

1. **Knowledge Assist is OFF by default.** Studio behaves as if KS does not exist
   when `ProjectCapabilities.knowledge_assist_enabled` is `False`. No KS HTML,
   no KS subprocess, no adapter calls.

2. **`ks_active` is runtime/process state, not user intent.** User intent is
   `knowledge_assist_enabled`. Routes and templates must not reason about raw
   `ks_active`.

3. **All KS adapter calls go through `AssistService`.**
   - *Wizard badge methods* (`get_field_suggestion_badge`, etc.) fail silently —
     return `None` on any error or KS unavailability. No degraded state surfaces
     to routes or templates.
   - *Workspace status methods* return structured `WorkspaceStatus` with
     `degraded=True` on failure — surfaced only inside the Knowledge Workspace.
   - `KSClient` remains transport-only and session-agnostic.

4. **Compact badge + drawer pattern. No always-visible panels.**
   - A `💡 N suggestions` badge is rendered only when `count > 0`.
   - Zero suggestions = zero KS HTML in the step.
   - Badges are compact, right-aligned in step headers; click opens a drawer.
   - The exact multi-scope drawer layout is defined by
     [Studio UX v3 Multi-Type Suggestion Drawer Pattern](./studio-ux-v3-suggestion-drawer-pattern.md).

5. **No degraded-mode warnings in wizard steps.** KS unavailability is silent in
   all wizard step routes. Degraded warnings appear only inside the Knowledge
   Workspace (`/knowledge` route). Broader-scope suggestion panels follow the
   same rule.

6. **KS unavailable in a wizard step = badge simply absent.** If `AssistService`
   fails to fetch rule/validation/mapping suggestions, the badge for that scope
   is `None` and the template renders nothing. Authoring continues uninterrupted.

### 8.2 Step Behaviour for Broader Suggestion Scopes

The table below extends the PR #132 step table for the Wave 1–3 scopes introduced
by this design. "KA OFF" means `knowledge_assist_enabled=False`; "KA ON, 0" means
enabled but no suggestions returned; "KA ON, N>0" means suggestions available.

| Step | Scope(s) | KA OFF | KA ON, 0 suggestions | KA ON, N>0 |
|---|---|---|---|---|
| Step 1 | Knowledge Workspace | No KS panel, no workspace link | KA toggle + `[Open ↗]` link; doc count shown | Same; live doc count from workspace |
| Step 3 | `fields`, `validations` | No KS UI | No badge | `💡 N field suggestions` + (Wave 1) `💡 N validation hints` — separate compact badges |
| Step 4 | `mappings`, `transforms` | No KS UI | No badge | (Wave 2/3) `💡 N mapping suggestions` per route section — compact badge; Kafka router transforms Wave 3 only |
| Step 6 | `rules`, `cross_entity_rules` | No KS UI. No advisory signals. | No badge | `💡 N rule suggestions` badge + (if non-zero) `⚠️ N conflicts` badge — separate, each opens its own drawer |
| Step 7 | `conflict_resolution` | Clean review | Clean review | `📋 Evidence used` link (only if ≥1 suggestion accepted/edited this session) |
| Step 8 | — | Normal export | Normal export | `☑ Include evidence sidecar` option only when ≥1 suggestion accepted/edited |

### 8.3 Broader-Scope UI Surfaces (UX v3 Pattern)

All broader-scope suggestion surfaces follow the same drawer pattern as the
existing field-suggestion flow. The pattern is defined in PR #132 §9.1 and is
non-negotiable for all KS-B2/B3 Studio work.

**Step 6 — Rule + Conflict badges (Wave 1 priority, KS-B2):**
- `💡 N rule suggestions` compact badge in the Step 6 rules header
- Click → drawer showing `rule` and `cross_entity_rule` suggestions for the active entity
- Each row: rule type badge, title, confidence indicator, citation count, accept/edit/reject
- Accepted rules prefill the rule authoring form (Studio-side prefill only)
- `⚠️ N conflicts` badge separate and only when non-zero — opens conflict drawer
- **Prerequisite:** Studio UX design spike (OQ6) must be approved before this PR opens;
  see [Studio UX v3 Multi-Type Suggestion Drawer Pattern](./studio-ux-v3-suggestion-drawer-pattern.md)

**Step 3 additions — Validation hints (Wave 1, KS-B2):**
- `💡 N validation hints` compact badge added alongside the existing field suggestions badge
- Click → separate drawer showing `validation` type suggestions
- Zero validation hints = badge absent (same pattern as field suggestions)

**Step 4 — Mapping badges (Wave 2, KS-B3):**
- `💡 N mapping suggestions` compact badge per route/interface section
- Click → drawer grouping `mapping` and `transform` (passthrough/fire-and-forget) suggestions
- Router `transform` scope (Wave 3) only appears after Kafka router PRs merge

**Async fetch and session cache:**
- All suggestion types use the same background-fetch model from `AssistService`
- `Fetching suggestions…` spinner only; no persistent panel while count is zero
- Refresh on new document ingest; session-cached until step navigation

**Degraded mode (Knowledge Workspace only):**
- If KS unavailable while user is inside `/knowledge`: show `WorkspaceStatus`
  `degraded=True` banner there — never in wizard steps
- All wizard badge methods return `None` silently; no banner

### 8.4 LegacyExtractor Integration Pattern (UX v3 Constraint)

LE must not create a second parallel suggestion rail in Studio. PR #132 §11
establishes the canonical pattern: LE output is ingested into KS as
provenance-tagged evidence (`"le-extraction"`) and surfaces through the same
`ManifestSuggestion` envelope and the same wizard badges/drawers as document-backed
suggestions. No separate "LE panel" or "LE badge" exists.

A second capability flag `legacy_assist_enabled: bool = False` (future, in
`ProjectCapabilities`) gates LE-sourced suggestions. It is greyed out when
`knowledge_assist_enabled` is `False`. This flag is not added to Studio until
KS-B6 (LE feed interface) is designed.

### 8.5 Optional AI Surface (UX v3 Constraint)

If AI is eventually enabled (`EDGEFORGE_KS_AI_PROVIDER` set), Studio may expose
an optional `ask_document` chat input inside the Step 1 Knowledge Workspace.
This surface:
- Is hidden unless `knowledge_assist_enabled=True` AND KS confirms AI is available
- Routes through the KS `ask_document` tool — no direct AI provider calls from Studio
- Is not added to Studio until KS-B5 ships verified pre-send sanitisation (see §7.1 ⚠️)
- Requires a separate Studio UX design spike; deferred from Wave 1 and Wave 2

---

## 9. Archetype Coverage

### 9.1 CRUD Archetype

| Suggestion type | Studio step | Manifest path | Depends on pending Engine changes? | Wave |
|---|---|---|---|---|
| `field` | Step 3 | `entities.{E}.fields.{F}` | No | Shipped |
| `validation` | Step 3 | `entities.{E}.fields.{F}.validation` | No | Wave 1 |
| `rule` | Step 6 | `rules.{E}.{rule-id}` | No (rules design doc complete) | Wave 1 |
| `cross_entity_rule` | Step 6 | `rules.cross.{rule-id}` | No (cross-entity rules design doc complete) | Wave 1 |
| `conflict_resolution` | Step 7 | N/A — surfaces evidence conflicts | No | Wave 2 |
| `portfolio_reuse` | Any | Depends on matched type | No | Wave 2 |

### 9.2 Passthrough-Router Archetype

| Suggestion type | Studio step | Manifest path | Depends on pending Engine changes? | Wave |
|---|---|---|---|---|
| `mapping` | Step 4 | `upstream_interfaces.{I}.operations.{O}.mappings.{F}` | No — passthrough contract is stable | Wave 2 |
| `transform` | Step 4 | `async_routes.{name}.transform_mapping` | No — passthrough contract is stable | Wave 2 |

### 9.3 Kafka-Integration Archetype

| Suggestion type | Studio step | Manifest path | Depends on pending Engine changes? | Wave |
|---|---|---|---|---|
| `mapping` (fire-and-forget / request-reply) | Kafka Step 3 | `async_routes.{name}.transform_mapping` | No — existing patterns are stable | Wave 2 |
| `transform` (router pattern — `router_config.targets.{T}.request_transform`) | Kafka Step 3 | `async_routes.{name}.router_config.targets.{T}.request_transform` | No — router contract is stable for the May 2026 baseline | **Wave 3** |
| `transform` (router pattern — `router_config.targets.{T}.response_transform`) | Kafka Step 3 | `async_routes.{name}.router_config.targets.{T}.response_transform` | No — router contract is stable for the May 2026 baseline | **Wave 3** |

**Wave 3 status:** The previous wait condition is satisfied for the May 2026
baseline. Kafka router request/response transform suggestions are implemented
against the stable `router_config` target transform paths.

---

## 10. Implementation Sequencing

### 10.1 Pre-Implementation Gate: Design Approval

This section is retained as implementation record. The design was reviewed and
approved before the KS-B0 through KS-B4 implementation arc.

**Kafka dependency:** Satisfied for the May 2026 baseline. KS-B4 router
transform suggestions are implemented via KS PR #21.

**Studio readiness gate (added in v1.2, from PR #132):** Satisfied for the May
2026 baseline. The historical gate was:

- **KS-B0** (schema-only in `EdgeForgeKnowledgeServer`): may proceed
  independently — no Studio surface, no Phase S dependency.
- **KS-B1 Studio** (`ks_integration.py` update, `AssistService` extension):
  requires Phase S S1–S6 + S-save-1 complete. S1–S6 puts the `AssistService`
  capability guard layer in place; S-save-1 wires `project_revision` into
  `save_project()`, which KS-B1 Studio needs because suggestion decisions
  submitted to KS reference the revision anchor (`project_id + project_revision`)
  as part of their metadata.
- **KS-B2 Studio UX** (rule/validation badge + drawer surfaces): requires Phase S
  S1–S6 complete AND the Studio UX design spike (S8 / OQ6) approved. Do not add
  new suggestion surfaces to Studio before the default-OFF capability layer and
  the no-assist regression test suite (`test_studio_ka_off.py`) exist.

This was not a governance preference — it was a design constraint. The
capability gate is now in place in Studio.

### 10.2 Phases

**KS-B0 — Database Schema Migration** (Repo: `EdgeForgeKnowledgeServer`)
- Rename `field_suggestions` → `manifest_suggestions`
- `suggestion_type` is already `NOT NULL` with no `DEFAULT` — no constraint change needed; preserve all existing `'field'` values
- Add indexes for `suggestion_type` and `(project_id, suggestion_type, entity_name)`
- Backward-compatible migration (existing field suggestions remain, status preserved)
- No tool changes — purely schema

**KS-B1 — Tool Contract Update** (Repos: `EdgeForgeKnowledgeServer` + `EdgeForgeStudio`)
- Add `suggest_manifest_candidates` tool (field scope first — backward-compatible)
- Add `get_suggestion_evidence_chain` generic tool (delegates to field chain for `scope=fields`)
- Keep `suggest_fields` and `get_field_evidence_chain` as deprecated aliases
- Update `submit_suggestion_decisions` with typed payload validation (field type only initially)
- Update Studio `ks_integration.py` with new tool wrappers; wire through `AssistService`
  (not directly from routes)
- Tests: field scope behavior unchanged; test that KA OFF → no adapter call
- **Studio side requires Phase S S1–S6 + S-save-1 complete before opening** (see §10.1)

**KS-B2 — Rule + Validation Suggestions** (Repos: `EdgeForgeKnowledgeServer` + `EdgeForgeStudio`)
- Implement `suggest_manifest_candidates(scope="rules")` — BRD/DDL constraint mining
- Implement `suggest_manifest_candidates(scope="cross_entity_rules")` — foreign-key / referential hints
- Implement `suggest_manifest_candidates(scope="validations")` — type/length/pattern from DDL
- Studio Step 6 rule/conflict compact badge + drawer (UX v3 pattern — see §8.3)
- Studio Step 3 validation hints compact badge (separate from field suggestions badge)
- Typed payload validation in `submit_suggestion_decisions` for rule and validation types
- Evidence chain for rule/validation suggestions
- Evidence trail sidecar v1.1 (adds `suggestion_type` per link)
- **First safe implementation slice — Business MVP for broader scopes**
- **Studio UX work requires Phase S S1–S6 complete AND OQ6 UX spike approved** (see §10.1)
- **Recommended split into separate PRs:** KS backend suggestion logic (KS-only),
  Studio UX consumption (Studio-only, after Phase S gate), evidence sidecar/export
  integration (can follow independently)

**KS-B3 — Mapping + Conflict Suggestions** (Repos: `EdgeForgeKnowledgeServer` + `EdgeForgeStudio`)
- Implement `suggest_manifest_candidates(scope="mappings")` — field catalog name/type matching
- Studio Step 4 mapping suggestions panel (passthrough and Kafka fire-and-forget/request-reply only)
- Implement `suggest_manifest_candidates(scope="conflict_resolutions")` — surfacing find_conflicts output as actionable suggestions
- Studio Step 7 conflicts sub-tab
- Portfolio reuse: `suggest_manifest_candidates(scope="portfolio_reuse")` — wraps `search_across_projects`

**KS-B4 — Wave 3: Kafka Router Transforms** (Implemented through KS PR #21 and Studio follow-through — Repos: `EdgeForgeKnowledgeServer` + `EdgeForgeStudio`)
- Implement `suggest_manifest_candidates(scope="transforms")` for router pattern
- Studio Kafka Step 3 transform suggestions panel
- Value-map coverage suggestions from field catalog
- Typed payload validation for transform type

**KS-B5 — Optional AI Provider Layer** (Repos: `EdgeForgeKnowledgeServer` + `EdgeForgeStudio`)
- Implement `providers/` module with `AIProvider` protocol
- `openai_provider.py` first concrete implementation
- `ask_document` tool enabled when provider configured
- `suggest_manifest_candidates` AI mode for rule/mapping/transform scopes
- Studio optional chat input in Step 1 (behind feature flag, separate UX design spike)

**KS-B6 — LegacyExtractor Feed Interface** (Repo: `EdgeForgeKnowledgeServer` — depends on LE MVP)
- Define `le_candidate` suggestion type schema
- Design KS ingestion endpoint for LE-produced artifacts
- Provenance: `le-extraction` label in evidence trail
- Implementation deferred until LegacyExtractor Phase 6 MVP complete

### 10.3 Summary Table

> **Repo key:** "KS" = `EdgeForgeKnowledgeServer`; "Studio" = `EdgeForgeStudio`. "Governance gate" = serialized by project decision (no technical dependency); "Technical blocker" = cannot implement without the dependency.

| Phase | Repo(s) | Blocked on | Wave | Business value |
|---|---|---|---|---|
| KS-B0 | KS only | Design approval — **may proceed independently** (schema-only, no Studio surface) | — | Schema foundation |
| KS-B1 KS side | KS only | KS-B0 | — | Tool contract (KS backend) |
| KS-B1 Studio | Studio | KS-B0 + **Phase S S1–S6 + S-save-1 complete** (PR #132) | — | Tool contract (Studio adapter via AssistService; revision anchor needs S-save-1) |
| KS-B2 KS side | KS only | KS-B1 KS side | Wave 1 | Rule/validation suggestion logic |
| KS-B2 Studio UX | Studio | KS-B1 Studio + **Phase S S8 / OQ6 spike approved** | Wave 1 | First broader-scope MVP in UI |
| KS-B3 | KS + Studio | KS-B2 | Wave 2 | Mapping + conflict resolution |
| KS-B4 | KS + Studio | KS-B3 + **`router_config` schema + `RouterConfig` Pydantic model stability confirmed** (Kafka PRs merged) | Wave 3 | Router transform suggestions |
| KS-B5 | KS + Studio | KS-B2 stable + KS-B5 sanitisation design | Wave 2/3 | Optional AI enhancement |
| KS-B6 | KS | LE Phase 6 MVP | Wave 4 | LE-sourced candidates |

---

## 11. Non-Goals

The following are explicitly out of scope for this design and all implementation phases derived from it:

- **No Engine LLM behavior.** Engine remains deterministic. No model calls during manifest validation or code generation.
- **No direct manifest writes from KS.** KS produces suggestions. Studio controls what enters the manifest after human review.
- **No Studio direct model calls.** All AI interaction routes through KS tool calls. Studio never imports an AI provider SDK.
- **No replacement for human review.** Suggestions are always pending until a human accepts, edits, or rejects them. Auto-accept is not supported.
- **No LegacyExtractor implementation.** KS-B6 defines an interface for LE output; it does not implement LE.
- **No chat-first redesign of Studio.** The optional `ask_document` surface is an enhancement, not a new paradigm.
- **No network/SSE deployment.** KS remains local stdio-only. SSE transport is a future option that requires a separate approved design.
- **No mandatory hosted AI dependency.** Deterministic mode must remain fully functional with zero AI provider configuration.
- **No vector search in Wave 1–2.** BM25/FTS5 is sufficient for deterministic suggestion retrieval. Vector search is a future hardening option.
- **No JIRA/Confluence live ingestion.** Manual export → file upload remains the ingestion model.

---

## 12. Open Questions

| # | Question | Impact | Recommendation |
|---|---|---|---|
| OQ1 | Should `suggest_fields` be formally deprecated and removed, or kept as a permanent alias? | Studio backward compat | Keep as alias for one full release cycle; remove in KS v2.0 |
| OQ2 | Can rule suggestions safely reference only document-derived rules, or should they also cross-check the current manifest to avoid duplicates? | Suggestion quality | Yes — add manifest-awareness check; suppress suggestions for rules already authored |
| OQ3 | How should `portfolio_reuse` suggestions be flagged in the evidence trail? Currently only local-project evidence is tracked | Provenance model | Add `portfolio-pattern` as a `provenance` value in evidence trail schema |
| OQ4 | For Kafka router transform suggestions, does KS need access to the generated JSON Schema files (from the manifest `schemas/` directory) to do field-existence validation, or is the field catalog from uploaded DDL/BRD sufficient? | Transform suggestion quality | KS should be able to ingest schema files as documents (JSON Schema is text); no special handling needed |
| OQ5 | Should `ask_document` be a named MCP tool in the 14-tool set, or an internal helper only used by suggestion generation? | Tool surface clarity | Named tool — it is a legitimate user-facing Studio feature when AI is enabled |
| OQ6 | Studio UX v3 multi-type suggestion drawer spec: per UX v3 (PR #132 §8), each step uses compact badges + drawers. The exact drawer layout for steps with multiple scopes is now defined in [Studio UX v3 Multi-Type Suggestion Drawer Pattern](./studio-ux-v3-suggestion-drawer-pattern.md). | Studio UX design | Approve Phase S S8 before KS-B2 Studio work begins |

---

## 13. Recommendation

**May 2026 status:** KS-B0 through KS-B4 are implemented and the Studio UX v3
readiness gates have been satisfied. The historical recommendation below is
retained as sequencing context for why the work landed in gated waves.

Current recommendations:

1. Treat deterministic FTS5/BM25 retrieval as the default enterprise posture.
2. Keep any future provider/model work behind the `KS-B5` design and data-handling gates; no
   LLM/provider integration exists today.
3. Treat LegacyExtractor-sourced `le_candidate` support (`KS-B6`) as a future
   interface that depends on the refreshed LegacyExtractor Phase 6 design.
4. Preserve the Studio UX v3 rule: KS suggests, Studio reviews, Engine consumes
   only approved manifest artifacts.

---

*EdgeForge Suite · Knowledge Server Broader Suggestion Scopes and Optional AI Assistance · v1.4 · April 2026*

---

## Appendix: Stable ID Conventions for New Suggestion Types

| Suggestion type | Key components for SHA256 hash |
|---|---|
| `field` (existing) | `"field:{project_id}:{normalized_entity}:{normalized_field_name}"` |
| `rule` | `"rule:{project_id}:{normalized_entity}:{rule_type}:{normalized_field_or_rule_id}"` |
| `cross_entity_rule` | `"cross_entity_rule:{project_id}:{normalized_source_entity}:{normalized_target_entity}:{normalized_source_field}"` |
| `validation` | `"validation:{project_id}:{normalized_entity}:{normalized_field_name}:{validation_type}"` |
| `mapping` | `"mapping:{project_id}:{normalized_route}:{direction}:{normalized_source_field}:{normalized_target_field}"` |
| `transform` | `"transform:{project_id}:{normalized_route}:{normalized_target_id}:{direction}"` |
| `conflict_resolution` | `"conflict:{project_id}:{sorted_document_ids_joined}:{normalized_field_or_rule_path}"` |
| `portfolio_reuse` | `"portfolio:{project_id}:{matched_project_id}:{normalized_manifest_path}"` |

All IDs use the same `SHA256(key)[:24]` truncation as the existing field suggestion IDs.
