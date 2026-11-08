# EdgeForge Knowledge Server MCP — Architecture & Design

> **Living design baseline.** Drafted 2026-04-14 and carried forward on
> 2026-04-20. The separate-repo KS backend is now implemented; this
> document remains the architecture baseline for KS scope, shipped Studio
> integration boundaries, and future follow-on work.
>
> This document supersedes the earlier KS tool sketch in `docs/extension-architecture.md` (which listed `read_copybook` and `read_table_ddl` as KS tools). Those tools belong to Phase 6 LegacyExtractor. The canonical tool vocabulary is defined here.

> **Status (April 2026):** All 12 tools are now implemented and tested.
> Wire protocol is verified via real stdio subprocess smoke tests (PR `#9`).
> The bounded field-suggestion-only Studio KS MVP is now implemented on Studio
> main through PRs `#67`-`#70`; broader Studio coverage remains future work. See
> [docs/archive/target-state-features-v1.md](archive/target-state-features-v1.md).

## Review Status

| Reviewer | Status | Date |
|----------|--------|------|
| Santosh | pending | |
| Codex | approved direction | 2026-04-14 |
| Claude | detailed target-state review aligned with this direction; Studio/workspace gaps called out separately | 2026-04-15 |

## Status Note

This document still describes the intended KS architecture and tool surface.
What has changed since the original draft is execution state:

- KS implementation is now progressing in a separate repo
- KS remains a separate MCP server and does not expand Engine MCP
- the bounded Studio field-review / provenance / export slice is now delivered
- broader Studio/workspace scope remains the next design and UX follow-on

## Problem

EdgeForge generates correct, contract-preserving applications from structured manifest packages. But the human work _before_ the manifest is the bottleneck: teams spend weeks reading legacy COBOL copybooks, PDF requirement documents, Excel data dictionaries, and Confluence pages to decide what fields map where, which business rules apply, and what the target entity model should look like.

Today that tribal knowledge lives in people's heads, SharePoint folders, and disconnected spreadsheets. There is no queryable, project-scoped knowledge layer that an AI assistant can use to _suggest_ manifest content with citations back to source material.

The Knowledge Server MCP fills that gap: it becomes the **enterprise memory** around EdgeForge, indexing legacy documentation and producing evidence-backed suggestions that flow through Studio for human review.

## Strategic Context

### Why now

- The Kafka archetype (parallel Engine track) proves EdgeForge handles async patterns. Knowledge Server is the next capability multiplier.
- Senior-leader demo feedback confirmed that AI-assisted manifest authoring from legacy docs is the highest-value differentiator.
- Phase 4 Engine MCP established the MCP pattern; Phase 5 reuses the same transport and protocol conventions.

### Relationship to existing phases

- Phase 5 is a **separate MCP server** — it does NOT expand Phase 4 Engine MCP's seven-tool surface.
- Knowledge Server touches different files and repos than the Kafka archetype track; they can run in parallel at the Engine and KS repo level (see caveat in Parallel Execution section below for Studio).
- Phase 6 LegacyExtractor MCP depends on Knowledge Server for document storage but is a separate design-first effort.

### Core architecture compliance

| Principle | How KS preserves it |
|-----------|---------------------|
| Manifest is the single source of truth | KS produces _suggestions_ that must be reviewed and accepted in Studio before they enter the manifest |
| Engine remains deterministic | KS never calls Engine directly; Studio mediates |
| Human review is mandatory | Every KS suggestion flows through accept/edit/reject in Studio |
| Contract-first | KS does not generate code; it helps populate the manifest that Engine uses to generate code |
| No vendor lock-in | KS uses a vendor-neutral agent adapter; LLM providers are swappable |

## Target-State Capabilities

The Knowledge Server MCP delivers ten capabilities across three tiers:

### Tier 1 — Foundation (PRs 2-5)

| # | Capability | Description |
|---|-----------|-------------|
| 1 | **Data dictionary ingestion** | Ingest Excel, CSV, and DDL files as structured field catalogs with type, length, nullability, and description metadata |
| 2 | **Document Q&A with citations** | Answer natural-language questions against ingested PDF, DOC, Markdown, and BRD documents; every answer includes section citations |
| 3 | **Search and retrieval** | BM25/full-text search across all project-scoped documents with ranked results |

### Tier 2 — Intelligence (PRs 6-8)

| # | Capability | Description |
|---|-----------|-------------|
| 4 | **Requirement timeline comparison** | Compare old vs. new requirements from JIRA, Confluence, or SharePoint exports; surface what changed, what was added, what was removed |
| 5 | **Rule suggestion** | Suggest business rules (validation, derivation, transformation) from ingested BRDs and copybook comments, with confidence scores and source citations |
| 6 | **Mapping suggestion** | Suggest field-level source-to-target mappings by cross-referencing data dictionaries, copybooks, and requirement documents |

### Tier 3 — Workflow & Reuse (PRs 9-11)

| # | Capability | Description |
|---|-----------|-------------|
| 7 | **Evidence traceability** | Link every manifest field, rule, and mapping back to the source document, section, and paragraph that justifies it |
| 8 | **Conflict detection** | Detect contradictions between documents (e.g., two BRDs defining different field lengths for the same entity) and surface them for resolution |
| 9 | **Manifest prefill** | Generate a draft manifest section from accepted suggestions, ready for human review in Studio |
| 10 | **Portfolio reuse** | Search across completed projects in the same domain (payments, lending, trade finance) to find reusable entity/mapping patterns |

### Cross-cutting: Review workflow

Every suggestion from capabilities 5-10 flows through a Studio **accept / edit / reject** review workflow. Nothing enters the manifest without explicit human approval.

## Architecture

### Deployment Model

```text
┌──────────────────────────────────────────────────────────┐
│                    EdgeForgeStudio                        │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Manifest     │  │ Document     │  │ Suggestion     │  │
│  │ Authoring UI │  │ Workspace    │  │ Review Panel   │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                 │                   │           │
│  ┌──────┴─────────────────┴───────────────────┴────────┐ │
│  │              ks_integration.py                       │ │
│  │   (MCP client — auto-starts KS as subprocess)        │ │
│  └──────────────────────┬──────────────────────────────┘ │
└─────────────────────────┼────────────────────────────────┘
                          │ stdio (Phase 5)
                          │ SSE/network (future)
┌─────────────────────────┼────────────────────────────────┐
│         Knowledge Server MCP (Phase 5)                   │
│                         │                                │
│  ┌──────────────────────┴──────────────────────────────┐ │
│  │                  MCP Tool Router                     │ │
│  └──┬────┬──────┬──────┬──────┬──────┬──────┬──────┬──┘  │
│     │    │      │      │      │      │      │      │      │
│  ingest read  search  ask  suggest suggest detect prefill │
│  _doc  _doc  _docs   _doc  _rules  _maps  _confl _mfst   │
│   + list + catalog + compare + portfolio                  │
│     │    │      │      │      │      │      │      │      │
│  ┌──┴────┴──────┴──────┴──────┴──────┴──────┴──────┴────┐│
│  │              Document Store                           ││
│  │  ┌─────────┐  ┌──────────┐  ┌───────────────────┐    ││
│  │  │ SQLite  │  │ BM25     │  │ Structured Field  │    ││
│  │  │ Catalog │  │ Index    │  │ Catalog (DDL/CSV) │    ││
│  │  └─────────┘  └──────────┘  └───────────────────┘    ││
│  └──────────────────────────────────────────────────────┘│
│                         │                                │
│  ┌──────────────────────┴──────────────────────────────┐ │
│  │           Vendor-Neutral Agent Adapter               │ │
│  │  (reasoning for suggestions, Q&A, conflict detect)   │ │
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

### Transport: stdio first, SSE later

Phase 5 uses **local stdio transport only**, identical to Engine MCP Phase 4. Studio auto-starts the KS process as a subprocess and communicates via stdio. There is no meaningful CLI fallback for KS (unlike Engine, which had a pre-existing CLI). SSE/network transport is deferred to a future phase if KS needs to be shared across machines or run as a team-level service.

### Key architecture decisions

**1. Separate process, separate repo (recommended)**

The Knowledge Server runs as its own Python process with its own MCP server, similar to how Engine MCP runs. This keeps the Engine deterministic and the KS independently deployable.

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| A. Separate repo (`EdgeForgeKnowledgeServer`) | Clean boundary, independent CI, independent versioning | One more repo to manage | **Recommended** |
| B. Co-located in Engine repo (`appbuilder/knowledge/`) | Shared CI, shared deps | Blurs the Engine determinism boundary | Acceptable fallback |
| C. Co-located in Studio repo | Close to UI consumer | Wrong responsibility placement | Not recommended |

**2. Storage: SQLite + BM25, not vector DB**

Consistent with the earlier architecture decision in `extension-architecture.md`:

- **SQLite** for the document catalog (metadata, project scoping, ingestion state)
- **BM25 full-text index** (via SQLite FTS5 or Tantivy) for unstructured document search
- **Structured field catalog** tables for parsed DDL, Excel, and CSV data dictionaries
- Vector search deferred as a later enhancement, not a Phase 5 prerequisite

Rationale: BM25 is deterministic, requires no external infrastructure, works offline, and produces reproducible results. This matches EdgeForge's philosophy of no external runtime dependencies.

**3. Agent adapter for reasoning tasks**

Suggestion, Q&A, and conflict detection require LLM reasoning. KS uses the same vendor-neutral agent adapter pattern established in the extension architecture:

- Adapter interface defined in KS
- Provider implementations are swappable (Anthropic, OpenAI, local models)
- All LLM outputs are tagged with confidence scores
- No vendor-specific dependency leaks into tool responses

**4. Project-scoped isolation**

Every KS operation is scoped to a **project**. Studio owns the `project_id` and passes it to KS as an opaque namespace key on every call. KS treats it as a namespace only — it does not create, validate, or track project lifecycles beyond using the ID as a storage partition key. Documents, indexes, suggestions, and field catalogs are project-isolated. Portfolio reuse (capability 10) is an explicit cross-project search that requires opt-in.

**5. Allowed-root and document safety**

File paths passed to `ingest_document` must resolve under a configured allowed root (set at KS startup, similar to Engine MCP). Additional guards:

- Maximum file size enforced before parsing (reject oversized files early)
- DOCX/XLSX are ZIP-based formats; enforce ZIP bomb protection (max uncompressed size)
- No implicit web fetching — KS only reads local files under the allowed root
- Embedded macros and scripts in Office files are ignored; only text and table content is extracted

## Phase 5 Tool Vocabulary

This design defines **12 MCP tools**. The tool `read_document` is included to align with the expected interface sketched in `extension-architecture.md` and to give Studio a way to retrieve a full document's text by ID without triggering a search.

### Tier 1 — Foundation Tools

```python
@tool
def ingest_document(
    project_id: str,
    file_path: str,
    doc_type: str,  # "pdf", "docx", "markdown", "excel", "csv", "sql"
                    # Note: "copybook" is NOT a supported doc_type in Phase 5.
                    # Copybook text produced by LegacyExtractor may be passed
                    # as "markdown" after extraction. Structural copybook
                    # parsing belongs to Phase 6 LegacyExtractor.
                    # Note: "jira_export" and "confluence_export" are deferred
                    # beyond the shipped Phase 5 KS contract. `ddl` is not a
                    # valid Phase 5 value; use "sql".
    tags: list[str] | None = None,
    description: str | None = None,
) -> IngestResult:
    """Ingest a document into the project knowledge base.

    Parses the document, extracts text and structure, indexes for search,
    and (for DDL/Excel/CSV) populates the structured field catalog.
    File path must resolve under the KS allowed root.
    Returns document ID, extracted section count, and field count if applicable.
    """

@tool
def list_documents(
    project_id: str,
    doc_type: str | None = None,
    tags: list[str] | None = None,
) -> DocumentList:
    """List all documents in the project knowledge base, optionally filtered."""

@tool
def read_document(
    project_id: str,
    document_id: str,
    section: str | None = None,  # optional: return only a named section
) -> DocumentContent:
    """Return the full extracted text of an ingested document, or a named section.

    Citations reference document_id + section (for DOCX/Markdown) or
    document_id + page (for PDF). DOCX citations use heading/paragraph
    anchors, not page numbers, because DOCX page numbers are render-dependent.
    """

@tool
def search_documents(
    project_id: str,
    query: str,
    doc_types: list[str] | None = None,
    max_results: int = 20,
) -> SearchResults:
    """Full-text BM25 search across project documents.

    Returns ranked results with document ID, section/heading, chunk_id,
    relevance score, and a text snippet around each match.
    """

@tool
def ask_document(
    project_id: str,
    question: str,
    doc_ids: list[str] | None = None,
) -> AnswerWithCitations:
    """Answer a natural-language question using project documents.

    Uses BM25 retrieval + agent reasoning. Every claim in the answer
    includes a citation: {document_id, section, heading, chunk_id, snippet}.
    DOCX citations reference heading/paragraph, not page number.
    """

@tool
def read_field_catalog(
    project_id: str,
    source: str | None = None,  # filter by source document
    entity: str | None = None,  # filter by entity/table name
) -> FieldCatalog:
    """Read the structured field catalog built from ingested DDL, Excel, and CSV files.

    Returns fields with: name, type, length, precision, scale, nullability,
    description, source_document, source_location.
    """
```

### Tier 2 — Intelligence Tools

```python
@tool
def suggest_rules(
    project_id: str,
    entity: str | None = None,
    max_suggestions: int = 10,
) -> RuleSuggestions:
    """Suggest business rules from ingested documents.

    Cross-references BRDs, data dictionaries, and requirement documents.
    Each suggestion includes: rule_type (validation/derivation/transformation),
    description, confidence (0.0-1.0), and source citations.
    """

@tool
def suggest_mappings(
    project_id: str,
    source_entity: str | None = None,
    target_entity: str | None = None,
    max_suggestions: int = 20,
) -> MappingSuggestions:
    """Suggest field-level source-to-target mappings.

    Cross-references data dictionaries and requirement documents.
    Each suggestion includes: source_field, target_field, transform (if any),
    confidence (0.0-1.0), and source citations.
    """

@tool
def compare_requirements(
    project_id: str,
    baseline_doc_id: str,
    current_doc_id: str,
) -> RequirementDiff:
    """Compare two requirement documents and surface changes.

    Returns: added requirements, removed requirements, modified requirements,
    each with citations to both documents.
    """

@tool
def detect_conflicts(
    project_id: str,
    scope: str | None = None,  # "fields", "rules", "all"
) -> ConflictReport:
    """Detect contradictions across ingested documents.

    Examples: two BRDs defining different field lengths, a DDL type
    conflicting with a data dictionary type, overlapping rule definitions.
    Each conflict includes the two sources and a suggested resolution.
    """
```

### Tier 3 — Workflow Tools

```python
@tool
def prefill_manifest_section(
    project_id: str,
    section: str,  # "entities", "routes", "mappings", "rules"
    accepted_suggestion_ids: list[str],
) -> ManifestDraft:
    """Generate a draft manifest section from accepted suggestions.

    Takes suggestion IDs that were accepted in the Studio review workflow.
    Returns a manifest-shaped YAML/JSON fragment validated against the
    manifest schema where possible. This is a starting point for human
    review and editing in Studio — not a final valid manifest. Engine MCP
    validate_manifest remains the final contract gate.
    """

@tool
def search_portfolio(
    query: str,
    domain: str | None = None,  # "payments", "lending", "trade-finance", "treasury"
    max_results: int = 10,
) -> PortfolioResults:
    """Search across completed projects for reusable patterns.

    Returns matching entities, mappings, and rules from other projects
    in the same domain, with usage frequency and origin project.
    Requires explicit opt-in per project to be included in portfolio search.
    Cross-project search returns patterns only — not raw document content.
    """
```

### LegacyExtractor boundary (NOT Phase 5 tools)

```python
# The following tools belong to Phase 6 LegacyExtractor MCP, not Knowledge Server.
# Listed here for boundary clarity.
#
# extract_copybook_fields(file_path) -> FieldCatalog
#   Structural COBOL copybook parsing: field names, picture clauses, levels.
#
# extract_plsql_rules(file_path) -> RuleSuggestions
# extract_java_entities(file_path) -> EntitySuggestions
# generate_draft_manifest(project_id) -> ManifestDraft
#
# LegacyExtractor feeds into KS via: extractor calls ingest_document()
# with the extracted text as a structured artifact.
# KS stores and indexes it; Studio reviews.
```

### Earlier tool sketch superseded

`extension-architecture.md` previously sketched `read_copybook` and `read_table_ddl` as KS tools. Those names are retired:

- `read_copybook` → belongs to Phase 6 LegacyExtractor (`extract_copybook_fields`)
- `read_table_ddl` → covered by `ingest_document` with `doc_type: "sql"` + `read_field_catalog`

## Tool Response Shape Contract

All tool responses follow a consistent envelope:

```python
from pydantic import BaseModel

class Citation(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str          # stable chunk identifier for traceability
    content_hash: str      # hash of chunk content at ingestion time
    parser_version: str    # parser version used, for reindex detection
    page: int | None = None        # PDF only; None for DOCX/Markdown
    section: str | None = None     # heading or section name
    heading: str | None = None     # nearest enclosing heading (DOCX/Markdown)
    char_offset: int | None = None # character offset within the chunk
    snippet: str           # the source text that supports this claim

class Suggestion(BaseModel):
    suggestion_id: str
    type: str  # "rule", "mapping", "field", "entity"
    description: str
    confidence: float  # 0.0 to 1.0
    citations: list[Citation]
    status: str = "pending"  # "pending", "accepted", "edited", "rejected"

class KSToolResult(BaseModel):
    success: bool
    tool_name: str
    project_id: str | None = None
    data: dict | list  # tool-specific payload
    citations: list[Citation] = []
    warnings: list[str] = []
```

Key constraints:

- Every suggestion MUST include at least one citation
- Confidence scores MUST be between 0.0 and 1.0
- Suggestions with confidence below 0.5 MUST be flagged as "low confidence" in the response
- No tool response may include generated code — only manifest-compatible data structures
- DOCX citations use `section`/`heading` anchors — never `page`, which is render-dependent

## Document Ingestion Pipeline

### Supported formats and parsers

| Format | Parser | Extracts | Citation anchor |
|--------|--------|----------|-----------------|
| PDF | `pdfplumber` or `PyMuPDF` | Text by page, tables, section headings | Page number |
| DOCX | `python-docx` | Text by paragraph, tables, headings | Heading / paragraph anchor |
| Markdown | `markdown-it-py` | Text by section, code blocks | H2/H3 section heading |
| Excel (`.xlsx`) | `openpyxl` | Structured field rows → field catalog | Sheet name + row index |
| CSV | `csv` stdlib | Structured field rows → field catalog | Row index |
| SQL DDL (`.sql`) | Custom stdlib `re` parser | Tables, columns, types, constraints → field catalog | Table name + column |
| COBOL copybook | **Not supported in Phase 5** — deferred to Phase 6 LegacyExtractor | — | — |
| JIRA export (JSON/CSV) | **Not supported in Phase 5** — deferred beyond the shipped KS baseline | — | — |
| Confluence export (HTML) | **Not supported in Phase 5** — deferred beyond the shipped KS baseline | — | — |

**DOCX citation note:** DOCX does not expose stable page numbers without rendering. All DOCX citations use the nearest enclosing heading and paragraph index as the anchor. This makes citations reproducible across re-ingestion.

### Ingestion flow

```text
file_path + doc_type
       │
       ▼
  ┌──────────┐   ┌────────────┐   ┌──────────────┐   ┌───────────────┐
  │ Safety   │──▶│ Format     │──▶│ Text/Table   │──▶│ SQLite        │
  │ Check    │   │ Detector   │   │ Extractor    │   │ Catalog       │
  │(size/zip)│   └────────────┘   └──────┬───────┘   └───────────────┘
  └──────────┘                           │
                                         ▼
                                  ┌──────────────┐   ┌───────────────┐
                                  │ Section/Page │──▶│ BM25 FTS5     │
                                  │ Chunker      │   │ Index         │
                                  │ (chunk_id,   │   └───────────────┘
                                  │  hash, ver)  │
                                  └──────┬───────┘
                                         │
                                         ▼ (if DDL/Excel/CSV)
                                  ┌──────────────┐   ┌───────────────┐
                                  │ Field        │──▶│ Structured    │
                                  │ Parser       │   │ Field Catalog │
                                  └──────────────┘   └───────────────┘
```

### Chunking strategy

- **Page-level** for PDF: each page is a chunk
- **Heading-level** for DOCX/Confluence: each H2/H3 block is a chunk; citation anchor is heading text + paragraph index
- **Section-level** for Markdown: each H2/H3 section is a chunk
- **Row-level** for Excel/CSV/DDL: each field/column row is a catalog entry
- **Requirement-level** for JIRA: each issue is a searchable unit
- Every chunk is assigned a stable `chunk_id` (hash of document_id + position), a `content_hash`, and the parser version — enabling citation integrity checks and selective reindexing

## Storage Schema Direction

```sql
-- Document catalog
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    file_path TEXT,
    ingested_at TEXT NOT NULL,
    page_count INTEGER,
    section_count INTEGER,
    tags TEXT,  -- JSON array
    description TEXT,
    deleted_at TEXT  -- soft delete; NULL = active
);

-- Full-text search via FTS5
CREATE VIRTUAL TABLE document_chunks USING fts5(
    chunk_id,               -- stable: hash(document_id + position)
    document_id,
    project_id UNINDEXED,
    page INTEGER UNINDEXED,         -- PDF only
    section TEXT UNINDEXED,         -- heading/section name
    heading TEXT UNINDEXED,         -- nearest enclosing heading
    char_offset INTEGER UNINDEXED,
    content_hash TEXT UNINDEXED,    -- hash of chunk content at ingest
    parser_version TEXT UNINDEXED,
    content,
    tokenize = 'porter unicode61'
);

-- Structured field catalog (from DDL, Excel, CSV)
CREATE TABLE field_catalog (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    entity_name TEXT,
    field_name TEXT NOT NULL,
    field_type TEXT,
    length INTEGER,
    precision INTEGER,
    scale INTEGER,
    nullable INTEGER,
    description TEXT,
    source_location TEXT  -- sheet+row, table+column, or line number
);

-- Suggestions (rules, mappings, fields)
CREATE TABLE suggestions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'rule', 'mapping', 'field', 'entity'
    description TEXT NOT NULL,
    confidence REAL NOT NULL,
    payload TEXT NOT NULL,  -- JSON: the actual suggestion content
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'accepted', 'edited', 'rejected'
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL
);

-- Suggestion citations (many-to-many)
CREATE TABLE suggestion_citations (
    suggestion_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    page INTEGER,           -- PDF only
    section TEXT,           -- heading/section for DOCX/Markdown
    heading TEXT,
    snippet TEXT NOT NULL,
    FOREIGN KEY (suggestion_id) REFERENCES suggestions(id),
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

-- Portfolio index (opt-in cross-project search)
CREATE TABLE portfolio_entries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    domain TEXT,  -- 'payments', 'lending', 'trade-finance', 'treasury'
    entry_type TEXT NOT NULL,  -- 'entity', 'mapping', 'rule'
    name TEXT NOT NULL,
    payload TEXT NOT NULL,  -- JSON
    usage_count INTEGER DEFAULT 1
);
```

## Document Lifecycle

KS must support removing documents cleanly. Such source documents are sensitive; a BRD ingested by mistake should be removable without leaving orphaned index entries.

Document deletion is a roadmap item (see KS PR 11 / follow-up). The schema above includes `deleted_at` for soft-delete. The implementation requirement:

- `delete_document(project_id, document_id)` sets `deleted_at`
- All FTS5 chunks for that document are removed from the search index
- All field catalog entries for that document are removed
- Suggestions that cited only that document are marked `status = "retracted"`
- Portfolio entries derived from that document are removed
- Portfolio opt-in status is preserved at the project level

Full `delete_document` tool design is deferred; the schema is designed to support it.

## Integration Points

### Studio Integration

Studio is the primary consumer. Integration follows the same pattern as Engine MCP (`appbuilder_integration.py` → `ks_integration.py`):

**1. KS Startup and Transport**

Studio auto-starts KS as a subprocess via `ks_integration.py`, using stdio transport:

```python
# EdgeForgeStudio/app/integrations/ks_integration.py
#
# Phase 5 transport: stdio only.
# Studio spawns the KS process as a subprocess on first use.
# There is no separate KS CLI fallback — KS is a service, not a CLI tool.
# SSE/network transport is a future option if KS becomes a shared team service.
#
# Studio owns project_id. It is passed on every KS call as an opaque namespace.
# KS does not create or validate project IDs — it uses them as storage partition keys.
```

**2. Studio UI Components (target state)**

Current shipped Studio coverage is a bounded subset of this table: document
upload / browse / search / read / field catalog, CRUD Step 3 field suggestion
review, Step 7 provenance review, and Step 8 `evidence-trail.json` export.

| Component | Purpose | KS Tools Used |
|-----------|---------|---------------|
| **Document Upload Panel** | Upload and ingest legacy docs into project KB | `ingest_document` |
| **Document Browser** | List and search ingested documents | `list_documents`, `search_documents` |
| **Document Viewer** | Read a full document or section | `read_document` |
| **Q&A Chat Panel** | Ask questions about legacy docs | `ask_document` |
| **Suggestion Review Panel** | Accept/edit/reject rule and mapping suggestions | `suggest_rules`, `suggest_mappings` |
| **Requirement Diff View** | Side-by-side requirement comparison | `compare_requirements` |
| **Conflict Resolution Panel** | Review and resolve detected conflicts | `detect_conflicts` |
| **Manifest Prefill Action** | Generate manifest fragment from accepted suggestions | `prefill_manifest_section` |
| **Field Catalog Browser** | Browse structured fields from DDL/Excel | `read_field_catalog` |

**3. Studio workflow integration**

The suggestion review workflow fits into Studio's existing step model:

```text
Step 1: Upload spec/contracts     (existing)
Step 2: Author manifest           (existing — now with KS suggestions)
Step 3: Generate & build           (existing)
Step 4: Test & validate            (existing)

New KS-assisted sub-steps in Step 2:
  2a. Upload legacy docs to KS          → ingest_document
  2b. Browse / search / ask             → list_documents, search_documents, ask_document
  2c. Review suggested rules            → suggest_rules → accept/edit/reject
  2d. Review suggested mappings         → suggest_mappings → accept/edit/reject
  2e. Detect and resolve conflicts      → detect_conflicts
  2f. Prefill manifest from accepted    → prefill_manifest_section → Studio editor
  2g. Continue manual authoring         → existing manifest editor
  2h. Final gate                        → Engine MCP validate_manifest
```

### Engine Integration

The Knowledge Server does **not** call Engine directly. The integration is indirect:

1. KS `prefill_manifest_section` produces manifest-shaped fragments
2. Studio edits and inserts accepted fragments into the manifest
3. Studio calls Engine MCP `validate_manifest` — this is the final contract gate
4. Studio calls Engine MCP `generate_app` as usual

KS references Engine's manifest schema at startup (via Engine MCP `get_manifest_schema` or a local copy) to validate suggestion payloads where possible. This is best-effort validation — KS cannot guarantee all fragments are valid for every future manifest evolution. Engine MCP `validate_manifest` remains the authoritative check.

### LegacyExtractor Integration (Phase 6)

Phase 6 LegacyExtractor will feed into Knowledge Server using a push model:

- LegacyExtractor parses COBOL copybooks, PL/SQL, and legacy Java
- Extractor calls `ingest_document()` with the extracted text artifact (as `doc_type: "markdown"` or `"sql"`)
- KS stores, chunks, and indexes it
- Studio reviews the resulting field catalog and suggestions

The push model (extractor → KS) is recommended over pull, so KS does not need to know about LegacyExtractor's internals. This dependency is forward-looking and does not block Phase 5 implementation.

## Implementation Roadmap

### Repository Setup

**Recommended:** New repo `EdgeForgeKnowledgeServer` with its own CI.

```text
EdgeForgeKnowledgeServer/
├── knowledge_server/
│   ├── __init__.py
│   ├── server.py              # MCP server entry point (stdio)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── ingest.py          # ingest_document
│   │   ├── read.py            # read_document
│   │   ├── search.py          # list_documents, search_documents
│   │   ├── ask.py             # ask_document
│   │   ├── field_catalog.py   # read_field_catalog
│   │   ├── suggest.py         # suggest_rules, suggest_mappings
│   │   ├── compare.py         # compare_requirements
│   │   ├── conflicts.py       # detect_conflicts
│   │   ├── prefill.py         # prefill_manifest_section
│   │   └── portfolio.py       # search_portfolio
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py
│   │   ├── docx_parser.py     # cites by heading/paragraph, not page
│   │   ├── markdown_parser.py
│   │   ├── excel_parser.py
│   │   ├── csv_parser.py
│   │   ├── ddl_parser.py
│   │   ├── jira_parser.py
│   │   └── confluence_parser.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── catalog.py         # SQLite document catalog
│   │   ├── search_index.py    # FTS5 BM25 index
│   │   └── field_store.py     # Structured field catalog
│   ├── reasoning/
│   │   ├── __init__.py
│   │   ├── adapter.py         # Vendor-neutral agent adapter interface
│   │   ├── qa_engine.py       # Q&A with citation extraction
│   │   ├── rule_engine.py     # Rule suggestion reasoning
│   │   ├── mapping_engine.py  # Mapping suggestion reasoning
│   │   └── conflict_engine.py # Conflict detection reasoning
│   └── models/
│       ├── __init__.py
│       ├── documents.py       # Pydantic models for documents
│       ├── suggestions.py     # Pydantic models for suggestions
│       ├── citations.py       # Citation model with chunk_id + content_hash
│       └── responses.py       # Tool response envelope
├── tests/
│   ├── fixtures/
│   │   ├── sample.pdf
│   │   ├── data-dictionary.xlsx
│   │   ├── sample-ddl.sql
│   │   └── sample-brd.md
│   ├── test_parsers/
│   ├── test_storage/
│   ├── test_tools/
│   └── test_reasoning/
├── pyproject.toml
├── README.md
└── .github/
    └── workflows/
        └── ks-tests.yml
```

### PR Roadmap

KS PR 2 from the original draft was too large. It has been split into two focused PRs (2a and 2b) to keep changes reviewable.

---

#### KS PR 1: Design Document (this PR)

**Files:** `docs/knowledge-server-mcp-design.md` (EdgeForge Engine repo)

**Acceptance:**
- Design reviewed and approved by stakeholders
- Architecture decisions agreed (separate repo, SQLite+BM25, vendor-neutral adapter, stdio first)
- Tool vocabulary of 12 tools frozen for Phase 5
- Copybook boundary clarified: parsing belongs to Phase 6 LegacyExtractor

---

#### KS PR 2a: Repo Bootstrap + Core Storage + Markdown/CSV Ingestion

**Target:** Minimal walking skeleton — MCP server starts, Markdown and CSV ingest and search

**Files:**
- `knowledge_server/server.py` — MCP server skeleton (stdio transport)
- `knowledge_server/storage/catalog.py` — SQLite document catalog with soft-delete column
- `knowledge_server/storage/search_index.py` — FTS5 index with chunk_id, content_hash, parser_version
- `knowledge_server/parsers/markdown_parser.py` — section-level chunker
- `knowledge_server/parsers/csv_parser.py` — field row extractor
- `knowledge_server/tools/ingest.py` — `ingest_document` for markdown + csv
- `knowledge_server/tools/search.py` — `list_documents`, `search_documents`
- `knowledge_server/models/` — core Pydantic models
- `tests/test_parsers/`, `tests/test_storage/`, `tests/test_tools/`

**Acceptance:**
- MCP server starts via stdio and responds to tool calls
- Markdown and CSV documents ingest and are searchable via BM25
- CSV fields appear in field catalog
- chunk_id and content_hash are stable across identical re-ingestion
- Safety check rejects files above max size limit

---

#### KS PR 2b: PDF, DOCX, Excel, DDL Parsers

**Depends on:** KS PR 2a

**Files:**
- `knowledge_server/parsers/pdf_parser.py` — page-level chunker
- `knowledge_server/parsers/docx_parser.py` — heading/paragraph anchor (no page numbers)
- `knowledge_server/parsers/excel_parser.py` — sheet + row extractor
- `knowledge_server/parsers/ddl_parser.py` — table/column extractor
- DOCX/XLSX ZIP bomb protection in safety check
- Tests with fixture files per format

**Acceptance:**
- All four formats ingest and are searchable
- DOCX citations reference heading + paragraph index, never page number
- XLSX files with embedded macros are accepted (macros ignored; text/tables extracted)
- ZIP bomb threshold enforced on DOCX and XLSX

---

#### KS PR 3: Read Document + Q&A Tools

**Depends on:** KS PR 2a

**Files:**
- `knowledge_server/tools/read.py` — `read_document`
- `knowledge_server/tools/ask.py` — `ask_document`
- `knowledge_server/reasoning/adapter.py` — vendor-neutral agent adapter interface
- `knowledge_server/reasoning/qa_engine.py` — Q&A with citation extraction
- `knowledge_server/models/citations.py` — citation model with chunk_id + content_hash

**Acceptance:**
- `read_document` returns full document text or a named section by heading
- `ask_document` answers questions with citations (chunk_id, section, heading, snippet)
- DOCX answers cite heading/paragraph, not page
- Agent adapter is provider-swappable with at least one implementation

---

#### KS PR 4: Field Catalog + JIRA/Confluence Ingestion

> **Status: Superseded.** Field catalog (`read_field_catalog`) was implemented
> as part of the actual KS slice delivery. JIRA and Confluence ingestion are
> deferred beyond the shipped Phase 5 KS contract and are not part of the
> implemented doc_type baseline. The canonical implemented doc_type values are:
> `"markdown"`, `"csv"`, `"sql"`, `"excel"`, `"pdf"`, `"docx"`.

---

#### KS PR 5: Studio Integration — Document Workspace Foundation

**Depends on:** KS PR 3 (in EdgeForgeStudio repo)

**Files (EdgeForgeStudio):**
- `app/integrations/ks_integration.py` — stdio MCP client; Studio auto-starts KS subprocess
- `app/templates/` — Document Upload Panel, Document Browser, Document Viewer, Search Surface, Field Catalog Browser
- `app/routes/` — KS-related API routes
- Tests

**Acceptance:**
- Studio auto-starts KS process via subprocess on first use
- Studio can upload documents to KS and display ingestion status
- Studio can browse, search, and read ingested documents
- Field catalog browser shows structured fields
- No separate KS CLI fallback path

**Studio sequencing note:** KS Studio PRs (5, 8) and Kafka Studio PR (Kafka PR 6) may touch shared navigation and wizard step templates. These Studio PRs should be sequenced to avoid UI conflicts even though the underlying KS and Kafka Engine work runs in parallel.

---

#### KS PR 6: Rule and Mapping Suggestion Tools

**Depends on:** KS PR 3

**Files:**
- `knowledge_server/tools/suggest.py` — `suggest_rules`, `suggest_mappings`
- `knowledge_server/reasoning/rule_engine.py`
- `knowledge_server/reasoning/mapping_engine.py`
- `knowledge_server/models/suggestions.py`
- `knowledge_server/storage/` — suggestion persistence tables

**Acceptance:**
- `suggest_rules` returns business rules with confidence scores and citations
- `suggest_mappings` returns field-level mappings with confidence and citations
- Suggestions persisted in SQLite for later review
- Low-confidence suggestions (<0.5) are flagged
- Each suggestion has at least one citation with chunk_id

---

#### KS PR 7: Requirement Comparison and Conflict Detection

**Depends on:** KS PR 3

**Files:**
- `knowledge_server/tools/compare.py` — `compare_requirements`
- `knowledge_server/tools/conflicts.py` — `detect_conflicts`
- `knowledge_server/reasoning/conflict_engine.py`

**Acceptance:**
- `compare_requirements` produces added/removed/modified diffs with citations
- `detect_conflicts` finds field-level contradictions across documents
- Conflicts include suggested resolutions

---

#### KS PR 8: Studio Suggestion Review & Manifest Prefill

**Depends on:** KS PR 6, KS PR 5 (in EdgeForgeStudio repo)

**Files (EdgeForgeStudio):**
- `app/templates/` — Suggestion Review Panel (accept/edit/reject UI)
- `app/routes/` — suggestion review API routes
- Updated `ks_integration.py`

**Files (EdgeForgeKnowledgeServer):**
- `knowledge_server/tools/prefill.py` — `prefill_manifest_section`

**Acceptance:**
- Studio displays suggestions with confidence and citations
- User can accept, edit, or reject each suggestion
- Accepted suggestions produce manifest-shaped YAML fragments via `prefill_manifest_section`
- Prefilled content appears in Studio's manifest editor for final human review
- Studio then calls Engine MCP `validate_manifest` as the final gate
- Manifest prefill output is explicitly labeled as a draft starting point, not a valid manifest

---

#### KS PR 9: Portfolio Reuse

**Depends on:** KS PR 6

**Files:**
- `knowledge_server/tools/portfolio.py` — `search_portfolio`
- `knowledge_server/storage/` — portfolio index tables

**Acceptance:**
- Projects can opt in to portfolio indexing
- `search_portfolio` returns matching entities/mappings/rules from other projects
- Results include domain classification and usage frequency
- Raw document content is never exposed via portfolio search

---

#### KS PR 10: Evidence Traceability

**Depends on:** KS PR 8

**Files:**
- Studio traceability view or report export
- Links every manifest field back to suggestion_citations

**Acceptance:**
- For any manifest field/rule/mapping, the system traces back to source documents via chunk_id
- Traceability report is exportable for audit/compliance

---

#### KS PR 11: Document Deletion (follow-up)

**Depends on:** KS PR 2a

**Files:**
- `knowledge_server/tools/ingest.py` — add `delete_document` tool
- Cascade: remove FTS5 chunks, field catalog entries, retract orphaned suggestions, remove portfolio entries

**Acceptance:**
- `delete_document` soft-deletes catalog entry and removes all derived index data
- Retracted suggestions are marked but not hard-deleted (audit trail)

---

## Parallel Execution with Kafka Track

The Kafka archetype track and KS track touch completely different files at the Engine and KS repo level:

| Aspect | Kafka Track | KS Track |
|--------|-------------|----------|
| Engine repo | `appbuilder/contracts/`, `appbuilder/metadata/`, `appbuilder/generation/` | No changes |
| KS repo | No changes | `knowledge_server/` (new repo) |
| Engine MCP | No changes to Phase 4 tools | No changes to Phase 4 tools |
| Studio impact | Kafka PR 6 (authoring UI) | KS PRs 5, 8 (doc upload, suggestion review) |

**Caveat on Studio:** Kafka PR 6 and KS PRs 5/8 both touch Studio's navigation, wizard steps, and shared template files. These Studio PRs should be sequenced to avoid UI conflicts, even though all Engine and KS repo work runs in parallel.

## Non-Goals for Phase 5

- No real-time database connectivity to legacy systems (KS works with exported artifacts only)
- No vector search / embeddings (deferred enhancement, not a prerequisite)
- No auto-generation without human review (every suggestion goes through accept/edit/reject)
- No expansion of Phase 4 Engine MCP tools
- No structural COBOL/PL-SQL/Java source code parsing (that is Phase 6 LegacyExtractor)
- No multi-tenant / multi-user auth (single-user local-first, matching Engine MCP)
- No SSE/network transport in Phase 5 (stdio only; SSE is a future option)
- No KS CLI tool (KS is an MCP service; Studio auto-starts it as a subprocess)

## Guardrails

1. **Human-in-the-loop is non-negotiable.** Every KS suggestion flows through Studio's accept/edit/reject workflow. Nothing enters the manifest automatically.
2. **Confidence transparency.** Every suggestion includes a confidence score and source citations. Users must see _why_ something was suggested.
3. **Manifest prefill is a draft.** `prefill_manifest_section` output is manifest-shaped and validated where possible, but Engine MCP `validate_manifest` is the final contract gate.
4. **Citation integrity.** Every citation carries a stable `chunk_id`, `content_hash`, and `parser_version`. This supports verification and future reindex detection.
5. **DOCX citations use heading anchors, not page numbers.** Page numbers in DOCX are render-dependent and not reproducible without rendering.
6. **File safety.** All ingested files must resolve under the configured allowed root. DOCX/XLSX ZIP bomb protection is enforced. Max file size is enforced before parsing.
7. **Project isolation.** Documents and suggestions are strictly project-scoped. Studio owns the project_id. KS treats it as an opaque namespace.
8. **Cross-project search returns patterns only.** `search_portfolio` never exposes raw document content from other projects.
9. **No Engine MCP expansion.** KS is a separate server. Phase 4's seven tools remain unchanged.
10. **Design-first.** This design doc must be reviewed and accepted before any implementation PR.
11. **Deterministic retrieval.** BM25 search results are reproducible for the same index state. Only the reasoning layer uses non-deterministic LLM calls.

## Open Questions

| # | Question | Status |
|---|----------|--------|
| Q1 | Should KS support SharePoint document ingestion natively, or require manual export to PDF/DOCX first? | Open — recommend manual export for Phase 5, native connector deferred |
| Q2 | Should the portfolio index be local (SQLite) or a shared service for team-wide reuse? | Open — recommend local-first, shared service deferred |
| Q3 | What is the minimum confidence threshold for surfacing suggestions? | Open — recommend 0.3 with explicit "low confidence" flag below 0.5 |
| Q4 | Should KS validate suggestions against the current project manifest to avoid duplicates? | Open — recommend yes, dedup against existing manifest fields/rules |
| Q5 | LegacyExtractor → KS integration: push or pull? | Decided — push: extractor calls `ingest_document` |
| Q6 | Max file size limit for ingestion? | Open — recommend 50 MB for Phase 5; tune based on parser performance |
| Q7 | How should `delete_document` handle suggestions that cite multiple documents, only some of which are deleted? | Open — recommend partial retraction: mark affected suggestions as "evidence-weakened" rather than fully retracting |

## Summary

The Knowledge Server MCP is EdgeForge's **enterprise memory** — a project-scoped document intelligence layer that turns legacy PDFs, data dictionaries, BRDs, and requirement exports into actionable manifest suggestions with full evidence traceability.

It runs as a separate MCP server (Phase 5), independent of Engine MCP (Phase 4) and the Kafka archetype track. Studio is the primary consumer, auto-starting KS via subprocess (stdio, Phase 5 only) and currently providing document upload / browse / search / read / field catalog, CRUD Step 3 field suggestion review, Step 7 provenance review, and Step 8 `evidence-trail.json` export. Broader Studio flows such as Q&A panels, non-field suggestion review, conflict resolution UI, and manifest prefill remain future work. Every prefilled fragment goes through Studio editing and Engine MCP validation before entering the manifest.

The 12-tool vocabulary and 11-PR roadmap deliver capabilities in three tiers: foundation (ingestion, search, Q&A), intelligence (rule/mapping suggestions, requirement comparison, conflict detection), and workflow (manifest prefill, portfolio reuse, evidence traceability, document deletion). Every tier preserves EdgeForge's core principle: the manifest is the single source of truth, and human review is non-negotiable.

---

## Phase 5 Review Notes

> **Reviewed by:** Claude (KS implementation thread)
> **Dates:** 2026-04-15 through 2026-04-18
> **Status:** Implemented in the KS backend and consumed by the current Studio
> CRUD Step 3 field-review slice.

The approved direction from PR `#115`, now reflected in the shipped contract, is:

- use **`submit_suggestion_decisions`** as the batch decision write-back tool
- keep the tool **batch-oriented** for Studio step-end or save-boundary write-back
- return **`outcomes: list[DecisionOutcome]`** so Studio can see per-decision
  success, warning, or error details
- persist stable **`suggestion_id`** and suggestion **`status`** so Studio can
  reconnect review state honestly
- type `status` as
  **`Literal["accepted", "edited", "rejected"]`**
- keep a richer typed **`SuggestionPayload` union** as future cleanup once
  broader suggestion types are formalized

The still-future part is broader suggestion typing and broader Studio coverage,
not the existence of the tool itself.
