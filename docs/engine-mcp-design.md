# Engine MCP Server Design — Phase 4

> Design-first document for Phase 4 Engine MCP server.
> No implementation is approved by this document alone.
> Phases 5 (Knowledge Server MCP) and 6 (LegacyExtractor MCP) are referenced
> for architecture alignment but not designed here.

## Problem

EdgeForge Engine today is invoked only as a CLI subprocess:

```
Studio → subprocess call → python -m appbuilder ... → files on disk
Claude Code → manual shell → python -m appbuilder ... → files on disk
Codex → manual shell → python -m appbuilder ... → files on disk
```

This is brittle:
- callers must manage process lifecycle and parse stdout/stderr
- no structured result — callers scrape files from disk
- no discovery — callers must know every CLI flag
- no composability — cannot chain Engine capabilities as tool calls
- AI agents cannot call Engine mid-conversation without manual shell commands

**MCP solves this.** The Engine exposes its capabilities as callable tools via the
Model Context Protocol (MCP) — an open, platform-agnostic standard. Any
MCP-compatible client (Studio, Claude Code, Codex, future CI/CD) can discover
and call Engine tools without shell scripting.

## Design Decisions

### MCP Standard

Use the **Model Context Protocol (MCP)** open standard:
- platform-agnostic: works with Claude, Codex, GPT, and any MCP-compatible client
- no vendor lock-in
- no per-call licensing or plugin fees when self-hosted
- token overhead is minimal — tool responses are structured JSON, not large text blobs

### Framework

Use **FastMCP** (Python MCP server framework):
- matches Engine's Python stack (no new language)
- minimal boilerplate: `@mcp.tool()` decorator pattern
- supports local (stdio) and network (SSE/HTTP) transport
- open source, no licensing cost

### Deployment Model

**Phase 4 target: local deployment first.**

The MCP server runs on the same machine as Studio or Claude Code. Phase 4
transport is `stdio` (standard input/output) for local clients.

Local deployment means:
- no HTTP port, endpoint, or network auth surface in Phase 4
- no auth required in Phase 4
- Studio and Claude Code both connect via their MCP client config
- zero additional infrastructure cost

Network deployment (shared team server) is a Phase 4+ consideration, not part of
the first implementation.

### Authentication

No auth in Phase 4 (local stdio transport). Add token-based auth in Phase 4+ when
network deployment is needed.

### Local Setup

The server entry point is:

```bash
python -m appbuilder.mcp_server
```

Engine v5 requires Python 3.11+, including its FastMCP entry point. FastMCP is
an unconditional declared dependency; older interpreter installs are not a
supported non-MCP subset. This supersedes the earlier version-marker guidance.

Example Studio / Claude Code / Codex client config:

```json
{
  "mcpServers": {
    "edgeforge-engine": {
      "command": "/path/to/EdgeForge/.venv/bin/python",
      "args": ["-m", "appbuilder.mcp_server"],
      "cwd": "/path/to/EdgeForge",
      "env": {
        "EDGEFORGE_MCP_ALLOWED_ROOTS": "/path/to/EdgeForge:/tmp"
      }
    }
  }
}
```

`EDGEFORGE_MCP_ALLOWED_ROOTS` is required for MCP generation tools. It is an OS
path-list (`:` on macOS/Linux) of per-session roots that `manifest_path` and
`output_dir` must resolve under; the process current working directory and
Engine repository are never implicit roots. The CLI remains unconstrained for
local development when this variable is unset, but setting `EDGEFORGE_SHARED_MODE`
requires the same per-session roots for CLI path-taking commands.

Known limitation: allowed-root checks resolve and reject traversal/symlink
escapes before file access, but they do not defend against a privileged local
process swapping a symlink after resolution; shared deployments must still
provide server-owned per-session workspace isolation.

For local stdio, the health check is the MCP handshake plus tool discovery:
initialize the server, call `list_tools`, or call a lightweight tool such as
`get_manifest_schema`. Phase 4 intentionally does not add an HTTP `/_health`
endpoint or `--port`.

### Filesystem and Side-Effect Safety

Local stdio removes the network boundary, but MCP tools can still read manifests
and write generated applications on the local filesystem. Phase 4 must keep that
surface explicit and bounded:

- `validate_manifest` and `translate_project` are read-only tools
- `generate_app` is the only Phase 4 tool that writes files
- tool implementations must resolve `manifest_path` and `output_dir` to absolute
  paths before use
- tool implementations must reject path traversal or paths outside configured
  allowed roots
- `generate_app` must return relative `files_written` paths only, never full
  source contents
- destructive cleanup of an existing output directory is not implicit; any
  overwrite/clean behavior must be explicit in the tool contract before code
  implements it

### Validation Semantics

`validate_manifest` intentionally matches `validate_package()` schema/package
validation. It validates the manifest YAML content and does not load referenced
package files. Studio flows that need full package loading semantics should keep
using their current `load_project_definition()` path or call `translate_project`
when they intentionally want translation-level validation and warnings.

---

## Open Architecture Question for Codex Review

> **Separate MCP servers vs. Unified Engine MCP — which architecture fits EdgeForge's
> Phase 4, 5, and 6 roadmap better?**

The roadmap has three MCP phases:

| Phase | Server | Capabilities |
|---|---|---|
| Phase 4 | Engine MCP | validate, translate, generate, list profiles |
| Phase 5 | Knowledge Server MCP | search domain patterns, rules, entity definitions, Confluence, JIRA, BRD docs |
| Phase 6 | LegacyExtractor MCP | parse COBOL, PL/SQL, Java, mainframe, Basic; extract schemas, data flows, business rules |

**Option A: Separate MCP Servers**

```
Engine MCP Server          (port/stdio: engine)
Knowledge Server MCP       (port/stdio: knowledge)
LegacyExtractor MCP        (port/stdio: extractor)
```

Each server is independent. Clients configure three separate MCP connections.

Pros:
- Clean separation of concerns
- Independent deployment and versioning
- Teams can own and update each server independently
- Engine changes never require KB or LE redeployment
- Each server has its own dependency set (no bloat)

Cons:
- Client config requires three connection entries
- Three servers to run locally (three processes)
- Discovery friction: clients must know which tools live on which server

**Option B: Unified Engine MCP**

```
Engine MCP Server
  ├── generation tools (translate, generate, validate)
  ├── knowledge search tools (patterns, rules, KB search)
  └── legacy extraction tools (COBOL parse, schema extract)
```

Single server, single connection, all tools in one place.

Pros:
- Single client connection and config
- Simpler local setup (one process)
- Tools can share internal utilities and models

Cons:
- Monolithic: changing KB search requires Engine redeployment
- Dependency bloat: COBOL parsers live in the same Python env as code generation
- KB and LE concerns leak into the Engine codebase
- Harder to independently scale or swap components

**Option C: Federated Gateway (Phase 4+)**

```
EdgeForge MCP Gateway       (single client connection)
  ├── → Engine MCP Server
  ├── → Knowledge Server MCP
  └── → LegacyExtractor MCP
```

Clients connect to one gateway. Gateway routes tool calls to the correct server.
Clients only see one endpoint.

Pros:
- Single connection for clients (like Option B)
- Clean separation for teams (like Option A)
- Gateway can add auth, rate limiting, logging in one place

Cons:
- Gateway is extra infrastructure (builds, deploys, routes)
- Overkill for Phase 4 local deployment

**Recommendation for Codex review:**

The recommended default is **Option A (Separate MCP Servers)** for Phases 4, 5, 6,
with **Option C (Federated Gateway)** considered only when team/shared deployment
is needed. Rationale:

- Engine should stay focused on generation. KB search and COBOL parsing have
  different dependencies, update cycles, and ownership.
- Local stdio deployment makes three processes trivial.
- If a gateway becomes necessary (team deployment, auth, single endpoint), it
  can be added as a thin wrapper over the three existing servers without
  changing the servers themselves.

**Codex Studio and Codex Engine are asked to review this recommendation and
confirm or challenge it before implementation begins.**

---

## Phase 4 Tool Vocabulary

The first Engine MCP implementation should expose these tools only.
KB and LE tools belong to Phases 5 and 6 respectively.

### Core Generation Tools

```python
@mcp.tool()
def validate_manifest(manifest_path: str) -> ValidationResult:
    """
    Validate a manifest YAML file against the Engine schema.
    Returns: { valid: bool, errors: list[str], warnings: list[str] }
    """

@mcp.tool()
def translate_project(manifest_path: str) -> TranslationResult:
    """
    Run A1/translation on a manifest package.
    Returns: canonical metadata summary (entities, operations, warnings)
    Does NOT write files. Safe to call for preview/validation.
    """

@mcp.tool()
def generate_app(manifest_path: str, output_dir: str) -> GenerationResult:
    """
    Full generation: translate + emit all files.
    Returns: { output_dir: str, files_written: list[str], warnings: list[str] }
    """

@mcp.tool()
def list_target_profiles() -> list[ProfileSummary]:
    """
    List all available target profiles with name, description, and key properties.
    Returns: [ { name, description, java_version, database, audit } ]
    """

@mcp.tool()
def describe_target_profile(profile_name: str) -> ProfileDetail:
    """
    Return non-sensitive generation detail for a target profile.
    Returns: ProfileDetail fields, excluding datasource passwords or secrets.
    """

@mcp.tool()
def list_archetypes() -> list[ArchetypeSummary]:
    """
    List supported app archetypes (crud, passthrough-router).
    Returns: [ { name, description } ]
    """

@mcp.tool()
def get_manifest_schema(schema_version: str = "2.0") -> dict:
    """
    Return the JSON Schema for a manifest version.
    Useful for Studio or author tooling to validate before submitting.
    """
```

### Deferred (Phase 5 — Knowledge Server MCP)

```python
# @mcp.tool()
# def search_domain_patterns(query: str, domain: str) -> list[Pattern]: ...
# def search_entity_definitions(entity_type: str) -> list[EntityDef]: ...
# def search_rules(entity_type: str) -> list[Rule]: ...
# def search_historical_mappings(source: str, target: str) -> list[Mapping]: ...
# def search_confluence(query: str) -> list[WikiPage]: ...
# def search_sharepoint(query: str, site: str) -> list[Document]: ...
# def search_jira_epics(project: str, keyword: str) -> list[Epic]: ...
# def search_brd_docs(query: str) -> list[BrdSection]: ...
```

### Deferred (Phase 6 — LegacyExtractor MCP)

```python
# @mcp.tool()
# def extract_from_cobol(source_code: str, dialect: str) -> ExtractedMetadata: ...
# def extract_from_plsql(sql_content: str) -> SchemaMetadata: ...
# def extract_from_java(project_path: str) -> CodeMetadata: ...
# def extract_from_mainframe(jcl_or_copybook: str) -> MainframeMetadata: ...
# def extract_from_basic(source_code: str) -> CodeMetadata: ...
# def parse_data_dictionary(content: str, format: str) -> DataDictionary: ...
# def infer_business_rules(code_analysis: CodeMetadata) -> list[BusinessRule]: ...
```

---

## Tool Response Shape Contract

Tool responses should follow a consistent shape. Callers depend on this contract.

```python
class ValidationResult(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]

class TranslationResult(BaseModel):
    app_name: str
    app_archetype: str
    entity_count: int
    operation_count: int
    warnings: list[str]
    # NOT the full MetadataProject — that is too large for LLM context windows.
    # Full metadata stays on disk or is returned via a file path.

class GenerationResult(BaseModel):
    success: bool
    output_dir: str
    files_written: list[str]   # relative paths only
    warnings: list[str]
    errors: list[str]

class ProfileSummary(BaseModel):
    name: str
    description: str
    java_version: str
    database: str
    emit_audit: bool

class ProfileDetail(ProfileSummary):
    language: str
    framework: str
    spring_boot_version: str
    emit_flyway: bool
    emit_spring_batch: bool
    emit_security: bool
    supports_xml: bool
    datasource_url_template: str | None
    datasource_driver_class_name: str | None

class ArchetypeSummary(BaseModel):
    name: str
    description: str
```

**Key constraint:** Tool responses must be small enough to fit in LLM context windows
without bloat. Return summaries and file paths, not full generated source code or
full canonical metadata trees.

---

## Integration Points

### Studio (MCP Client)

Studio replaces its current subprocess call with an MCP tool call:

```python
# Before (subprocess):
result = subprocess.run(["python", "-m", "appbuilder", ...], capture_output=True)

# After (MCP tool call):
result = await mcp_client.call_tool("generate_app", {
    "manifest_path": str(manifest_path),
    "output_dir": str(output_dir)
})
```

Studio MCP client configuration (local stdio):
```json
{
  "mcpServers": {
    "edgeforge-engine": {
      "command": "python",
      "args": ["-m", "appbuilder.mcp_server"],
      "cwd": "/path/to/EdgeForge"
    }
  }
}
```

### Claude Code (MCP Client)

Claude Code connects to Engine MCP and can call tools mid-conversation:
```json
{
  "mcpServers": {
    "edgeforge-engine": {
      "command": "python",
      "args": ["-m", "appbuilder.mcp_server"],
      "cwd": "/path/to/EdgeForge"
    }
  }
}
```

This allows Claude Code to call `validate_manifest` or `list_target_profiles`
directly during a review or implementation session.

### Codex (MCP Client)

Same config as Claude Code. Codex can validate its own generated manifests
before opening a PR.

---

## Implementation Location

New module in Engine:

```
appbuilder/
  mcp_server.py          ← Entry point: FastMCP server, tool registrations
  mcp/
    __init__.py
    tools/
      generation.py      ← validate_manifest, translate_project, generate_app
      catalog.py         ← list_target_profiles, describe_target_profile, list_archetypes
      schema.py          ← get_manifest_schema
    models/
      results.py         ← ValidationResult, TranslationResult, GenerationResult, etc.
```

No changes to existing Engine modules (`contracts/`, `metadata/`, `generation/`).
The MCP server is a thin adapter layer over existing Engine functions.

---

## Acceptance Criteria

The Phase 4 implementation is complete when:

1. `validate_manifest` returns correct errors for an invalid manifest and empty
   errors for a valid one. Matches current `validate_package()` behavior.
2. `translate_project` returns entity count, operation count, and warnings
   for the in-repo independently authored Workspace/Item fixture
   (`examples/input-projects/workspace-items/app-definition.yaml`) without writing files.
3. `generate_app` produces the same output as the current CLI `--generate` path
   for the in-repo independently authored Workspace/Item fixture
   (`examples/input-projects/workspace-items/app-definition.yaml`).
4. `list_target_profiles` returns all three current profiles with correct metadata.
5. `get_manifest_schema` returns valid JSON Schema for `schema_version: "2.0"` and rejects `1.0`.
6. Studio can call `generate_app` via MCP and replace its current subprocess call.
7. Claude Code can call `validate_manifest` via MCP with a local manifest path.
8. All existing Engine tests pass unchanged (MCP is additive, not a refactor).
9. No new external dependencies beyond FastMCP.
10. Server starts cleanly with `python -m appbuilder.mcp_server` and registers
    all tools.
11. Path handling tests cover allowed-root validation for `manifest_path` and
    `output_dir`, and prove `translate_project` performs no file writes.

---

## Explicitly Out of Scope (Phase 4)

- Knowledge base search tools (Phase 5)
- Legacy extractor tools (Phase 6)
- Authentication or token-based access control
- Network/HTTP deployment (local stdio only for Phase 4)
- Federated MCP gateway
- Streaming tool responses
- MCP resource or prompt registrations (tools only in Phase 4)
- Studio UI changes beyond wiring the MCP client
- Any changes to Engine core modules (`contracts/`, `metadata/`, `generation/`)

---

## Phase 5 and Phase 6 Design Notes

These are not designed in this document. The following notes exist only to inform
the architecture question above and to flag what each phase needs to answer.

### Phase 5 — Knowledge Server MCP

Key questions to resolve in Phase 5 design doc:
- What is the knowledge base storage technology? (vector DB, full-text search, PostgreSQL?)
- How is knowledge populated initially? (manual curation, auto-import from Confluence/JIRA, or both?)
- Confluence and SharePoint integration: push-based (sync job) or pull-based (live API call)?
- How are historical mappings stored and updated after each modernization project?
- Does the KB server live in the Engine repo, a new repo, or as a Studio plugin?

### Phase 6 — LegacyExtractor MCP

Key questions to resolve in Phase 6 design doc:
- COBOL dialect support: IBM COBOL only, or also MicroFocus, GnuCOBOL?
- Java extraction: AST-based (JavaParser) or LLM-assisted analysis?
- PL/SQL: Oracle dialect first, or multi-vendor?
- Output contract: does the extractor produce partial manifest fragments, or
  full canonical metadata, or something in between?
- How does extracted metadata feed into the Engine? Direct file drop, or
  Studio-mediated review before export?
- Does the LegacyExtractor need human-in-the-loop review at any extraction step?
