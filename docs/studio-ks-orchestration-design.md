# Studio KS Orchestration Design

> Design gate B2 for Studio Knowledge Server integration and future multi-MCP
> orchestration. This document defines Studio's MCP adapter responsibilities,
> async suggestion fetch behavior, review-state ownership, and save/open
> reconnect protocol. The bounded field-suggestion-only KS Studio MVP is now
> implemented on Studio main; this document remains the design anchor for the
> delivered slice and the still-pending broader scope.
>
> Related design gates:
> - [Studio Archetype Step Registry](./studio-archetype-step-registry.md)
> - [Evidence Trail Design](./evidence-trail-design.md)
> - [Project Workspace / Decision Ledger Design](./project-workspace-decision-ledger-design.md)
> - [Studio UX v3 Multi-Type Suggestion Drawer Pattern](./studio-ux-v3-suggestion-drawer-pattern.md)

## Purpose

Studio already orchestrates Engine MCP. The next integration wave will add
Knowledge Server MCP and later LegacyExtractor MCP. Suggestion review will then
span three layers:

- Studio session state
- Knowledge Server persistence
- Studio save/open project state

This document defines the orchestration model that anchored the shipped Step 1 /
Step 3 / Step 7 / Step 8 KS slice and still guides broader follow-on work.

## Problem Statement

Without this design:

- KS Studio document-workspace PRs and suggestion-review PRs could invent
  different subprocess and state-management patterns
- suggestion state could be split between Studio and KS with no clear owner
- Studio save/open would have no reliable way to reconnect to the correct KS
  workspace and resume review state

The result would be ad hoc per-route logic, inconsistent reconnect behavior,
and a fragile user experience whenever KS is slow or temporarily unavailable.

## Design Goal

Studio should treat each MCP-backed service as an integration adapter with a
clear ownership boundary:

- Studio owns user session behavior and active review state
- Knowledge Server owns persisted suggestion records and citation storage
- the Studio save file stores just enough linkage to reconnect and resume

This keeps review state comprehensible during an active session while still
making it recoverable on save/open.

## Subprocess Lifecycle Model

Knowledge Server should follow the same local stdio-first pattern established by
Engine MCP, but with one important difference: there is no CLI fallback mode.

### KS lifecycle rules

- Studio auto-starts Knowledge Server as a subprocess on first use within a
  session
- Studio is responsible for KS process startup, readiness check, and teardown
- if KS crashes mid-session, Studio surfaces a visible
  "Knowledge Server unavailable" warning
- KS unavailability must not crash the wizard or discard current manual edits
- on project reopen, Studio attempts to reconnect using the stored
  `ks_project_id`
- there is no KS CLI fallback; KS is a service-only dependency

This differs from Engine MCP, where the Studio adapter intentionally preserves a
subprocess CLI fallback for `generate_app`.

## Async Suggestion Fetch Model

Suggestion fetches should be non-blocking. For Studio UX v3, this orchestration
model is applied through compact badge and drawer view models rather than
always-visible panels. The exact multi-scope UX contract is defined in
[Studio UX v3 Multi-Type Suggestion Drawer Pattern](./studio-ux-v3-suggestion-drawer-pattern.md).

When a user navigates to a step whose registry entry has a non-`none`
`suggestion_scope`, the v3 behaviour is:

1. Studio renders the step immediately
2. `AssistService` may perform a quiet badge/count probe for eligible scopes
3. if the probe returns `count > 0`, Studio renders a compact badge
4. clicking the badge opens a drawer and fetches the full suggestion list
5. the user may continue authoring manually while any fetch is in flight

If the probe or drawer fetch fails in a wizard step, the badge or drawer content
quietly disappears or shows a small empty state. Degraded warnings are reserved
for the Knowledge Workspace page.

### Session caching

Suggestions fetched for a step should be cached in the Studio session until:

- the user navigates away from the step, or
- the user explicitly refreshes suggestions

This avoids repeated identical calls during minor in-step edits while still
allowing the user to request a fresh suggestion pass when needed.

The step attachment model that determines where suggestions are relevant is
defined in [Studio Archetype Step Registry](./studio-archetype-step-registry.md).

## Review-State Ownership Model

Studio owns suggestion review state during an active session.

The minimum in-session state should include:

- `pending_suggestion_ids`
  - suggestions fetched but not yet reviewed
- `accepted_suggestion_ids`
  - suggestions accepted as-is
- `edited_suggestion_ids`
  - suggestions accepted after user modification
- `rejected_suggestion_ids`
  - suggestions dismissed by the user

Knowledge Server remains the persistence layer for suggestion status and
citations. Studio should not treat KS as the active interaction owner while the
user is reviewing a step.

### Batching rule

Studio should not write back after every single accept/reject click. Instead,
Studio should batch decisions and write them:

- at the end of each step review, and
- on explicit project save

This reduces noisy IPC chatter while preserving durable review state at the
points where the user has meaningfully concluded work.

## Decision Write-Back API

The additive Phase 5 review tool is now implemented as:

```python
submit_suggestion_decisions(
    project_id: str,
    decisions: list[SuggestionDecision],
) -> DecisionResult

class SuggestionDecision(BaseModel):
    suggestion_id: str
    status: str  # "accepted" | "edited" | "rejected"
    edited_payload: dict | None = None
```

This tool now:

- accept a batch of review decisions from Studio
- persist those decisions in Knowledge Server's suggestions table
- return success or failure per decision via per-item `outcomes`

Studio calls it:

- when the user completes step review
- when the user explicitly saves the project

Current delivered Studio coverage is intentionally narrower than the full
target-state design:

- Step 1 Knowledge Workspace foundation is implemented
- CRUD Step 3 field suggestion review is implemented
- Step 7 provenance review and Step 8 `evidence-trail.json` export are implemented
- broader non-field suggestion flows and broader step attachment by
  `suggestion_scope` remain follow-on work

## Save/Open Reconnect Protocol

The Studio save file must carry enough state to reconnect to Knowledge Server
without assuming that KS persistence always exists on the local machine.

The minimum stored fields are:

- `ks_project_id`
- `ks_active`
- `suggestion_review_state`
  - `accepted_ids`
  - `rejected_ids`
  - `edited_ids`

### Reopen flow

If `ks_active` is `true` and `ks_project_id` is present:

1. Studio starts the KS subprocess
2. Studio calls `list_documents(project_id=ks_project_id)` to confirm the
   workspace still exists
3. if the workspace exists, Studio reloads review state from both the local
   save file and Knowledge Server persistence
4. if the KS workspace is missing, Studio surfaces a visible warning and still
   opens the project without blocking manual authoring

If `ks_active` is `false`, Studio opens the project without attempting a KS
connection.

Current repo truth is partial:

- durable linkage and workspace state are already persisted in the Studio save
  file
- broader reconnect automation on reopen is still follow-on work and should not
  be overstated as fully shipped behavior

The durable save-file structure and migration behavior are described more
fully in
[Project Workspace / Decision Ledger Design](./project-workspace-decision-ledger-design.md).

## Multi-MCP Adapter Pattern

Studio should keep one adapter module per MCP-backed service under
`app/integrations/`:

- `app/integrations/appbuilder_integration.py`
- `app/integrations/ks_integration.py`
- `app/integrations/le_integration.py`

Each adapter owns:

- subprocess start and stop
- readiness or health checks
- tool-call dispatch
- transport-level error surfacing

Studio routes should call adapters directly. Routes should not manage
subprocess state themselves.

This keeps orchestration logic centralized and makes service-specific failure
handling consistent.

## Failure Handling Expectations

Studio should handle KS failures as degraded-mode events, not wizard-fatal
errors.

Examples:

- if KS is unavailable, suggestion panels show a visible warning and manual
  authoring remains available
- if a background suggestion fetch fails, Studio should surface the failure in
  the panel and allow retry
- if write-back fails on step completion or save, Studio should preserve the
  local in-session decisions and warn the user that KS persistence did not
  complete

The user should never lose local authoring work because KS is temporarily down.

## Relationship to Other Design Gates

- [Studio Archetype Step Registry](./studio-archetype-step-registry.md)
  determines which steps expose suggestion-capable panels via
  `suggestion_scope`.
- [Evidence Trail Design](./evidence-trail-design.md) depends on accepted and
  edited suggestion decisions being persisted and recoverable.
- [Project Workspace / Decision Ledger Design](./project-workspace-decision-ledger-design.md)
  defines how reconnect metadata, review history, and lightweight evidence
  links persist in the Studio save file.

## What This Document Is NOT

- Not a full KS integration implementation spec
- Not a mandate for an async/await rewrite of Studio's FastAPI routes
- Not a decision on SSE or network transport; Phase 5 remains stdio-only
