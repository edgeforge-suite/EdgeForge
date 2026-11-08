# Studio UX v3 — Assistive Features and Knowledge Assist Simplification

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

**Status:** Implemented — merged through Studio PR #143 (May 2026). Privately retained external-application CRUD/Knowledge Assist smoke passed.
**Version:** 1.8  
**Date:** April 2026  
**Author:** Claude Code (architecture review)  
**Branch:** `claude/docs/studio-ux-v3-assistive-features`  
**Related PRs:** PR #129 (`docs/ks-broader-suggestion-scopes-design.md`)
**Related design spikes:** [Studio UX v3 Multi-Type Suggestion Drawer Pattern](./studio-ux-v3-suggestion-drawer-pattern.md)

> **Implementation note — May 2026:** The core UX v3 capability model,
> Knowledge Assist default-OFF behavior, compact badge/drawer pattern, Step 3
> full-width KA review, Step 6 KA-applied rule ownership/removal semantics, and
> Step 7 Decision History grouping are implemented through Studio PR #143.
> Acceptance was verified through the focused privately retained external-application CRUD/Knowledge Assist manual smoke
> covering review, export, generation, build, runtime, and EOD downstream
> output. Save/open hardening is partially implemented; KA persistence/reopen
> hardening remains post-baseline design work.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Current-State Diagnosis (Post-Kafka Studio)](#3-current-state-diagnosis-post-kafka-studio)
4. [Target UX Principles](#4-target-ux-principles)
5. [Knowledge Assist Toggle Design](#5-knowledge-assist-toggle-design)
6. [Capability Model](#6-capability-model)
7. [Workspace Identity Behaviour](#7-workspace-identity-behaviour)
8. [Knowledge Workspace v3 Layout](#8-knowledge-workspace-v3-layout)
9. [Step-by-Step OFF/ON Behaviour](#9-step-by-step-offon-behaviour)
10. [Kafka Awareness](#10-kafka-awareness)
11. [LegacyExtractor Integration Pattern](#11-legacyextractor-integration-pattern)
12. [Optional AI Fit](#12-optional-ai-fit)
13. [Architecture Boundaries](#13-architecture-boundaries)
14. [Repo Impact Table](#14-repo-impact-table)
15. [Risk Table](#15-risk-table)
16. [Recommended Implementation PR Sequence](#16-recommended-implementation-pr-sequence)
17. [Acceptance Criteria for Build PRs](#17-acceptance-criteria-for-build-prs)
18. [Follow-up Doc Updates Needed](#18-follow-up-doc-updates-needed)
19. [Non-Goals](#19-non-goals)
20. [Addendum A — Save/Open Project Hardening](#addendum-a--saveopen-project-hardening)

---

## 1. Executive Summary

The post-Kafka EdgeForge Studio is functionally correct and architecturally
sound for its current scope. It cleanly separates the three build archetypes
(CRUD, passthrough-router, kafka-integration), and the Kafka authoring flow is
a genuine new capability delivered without breaking the earlier flows.

However, the current Knowledge Server integration is **conditionally correct
but architecturally leaky for a broader rollout:**

- There is no user-controlled toggle. `ks_active` is an activation flag, not a
  product capability choice. It can be set implicitly when workspace identity is
  minted, before the user has asked for KS help at all.
- Step 1 always renders the Knowledge Workspace panel and "KS Status" indicator,
  even for users who have never touched the Knowledge Workspace.
- The `build_workspace_summary` service is called unconditionally on every Step 1
  render, coupling the project-setup screen to KS state regardless of user intent.
- `ks_review_enabled` in Step 3 is gated on archetype + entity selection, but
  not on whether the user explicitly enabled Knowledge Assist.
- Degraded-mode and advisory conflict signals appear in Steps 7 and 6 for CRUD
  projects without any user opt-in.
- KS subprocess lifecycle is managed in a service layer, which is correct, but
  routes still carry archetype-and-flag checks that should live in a central
  capability guard.

Expanding KS to cover broader suggestion scopes (PR #129 waves 1–3) and adding
LegacyExtractor into the mix will make these leaks significantly worse unless a
clean capability model is established first.

**The fix is not a redesign.** It is:
1. A central `ProjectCapabilities` model with `knowledge_assist_enabled: bool = False`
2. A user-facing "Knowledge Assist" toggle in Step 1 (default OFF)
3. All KS adapter calls and KS-related template surfaces gated behind that flag
4. A "compact badge, drill-down on demand" suggestion pattern — no always-open panels
5. A scalable two-panel Knowledge Workspace v3 layout

This document defines that model for Studio UX v3 and serves as the
implementation contract for the build PRs that follow.

**Product principle throughout:** *Studio is clean and manual by default.
Assistive intelligence appears only when the user asks for help.*

---

## 2. Problem Statement

### 2.1 The KS Leakage Pattern

Without a user-controlled capability flag:

- Users who never want KS see a "KS Status" panel and "Open Knowledge
  Workspace" button on every Step 1 visit.
- Users who accidentally visit `/knowledge` implicitly activate `ks_active`,
  which changes downstream step behaviour.
- When the KS subprocess is not running (common when KS is not configured),
  Studio surfaces degraded-mode warnings that are confusing to users who did
  not ask for KS at all.
- Adding broader suggestion scopes (rules, mappings, transforms) without a
  capability gate will add more panels, more badges, and more degraded warnings
  to more steps — for all users, not just those who opted in.

### 2.2 The Scaling Problem

The current Knowledge Workspace is a single-page scroll: upload form at top,
document list below, field catalog further below. This worked for the MVP with
2–5 documents. It will break visually and functionally at 20+ documents — the
typical real-world BRD + DDL + mapping + rules document set for a single
modernization project.

### 2.3 The LegacyExtractor Gap

There is no design for how LegacyExtractor output enters Studio. Without a
pattern, ad hoc implementation risks adding a second parallel suggestion rail,
raw LE complexity surfaced directly in Studio, or another leaky always-visible
panel in the wizard.

### 2.4 Kafka Flow Completeness

The Kafka authoring flow (3 Kafka-specific steps: topic ingest, route config,
transforms) is now complete. Future KS mapping and transform suggestions for
Kafka routes need to fit the step structure without cluttering the transform
authoring screen that is already information-dense.

---

## 3. Current-State Diagnosis (Post-Kafka Studio)

### 3.1 Route and Template Inventory

| Route | Template | Archetype | KS Surface Present? | KS Gate |
|---|---|---|---|---|
| `GET /` | `step1_project.html` | All | **Always** — `workspace_summary` panel unconditional | `build_workspace_summary()` called regardless of `ks_active` |
| `GET /upstream` | `step2_upstream.html` | CRUD / Passthrough | No | — |
| `GET /entities` | `step3_entities.html` | CRUD only | `ks_review_enabled` right-rail panel | `archetype == "crud" and bool(selected_entities)` — no capability flag check |
| `GET /passthrough` | `step3_passthrough.html` | Passthrough | No | — |
| `GET /kafka/topics` | `kafka_step1_topics.html` | Kafka | No | — |
| `GET /kafka/routes` | `kafka_step2_routes.html` | Kafka | No | — |
| `GET /kafka/transforms` | `kafka_step3_transforms.html` | Kafka | No | — |
| `GET /downstream` | `step4_downstream.html` | CRUD | No | — |
| `GET /handoffs` | `step5_handoffs.html` | CRUD | No | — |
| `GET /rules` | `step6_rules.html` | All | Advisory conflict signals for CRUD | `not session.ks_active` guard in route |
| `GET /review` | `step7_review.html` | All | `advisory_conflicts` card | `not session.ks_active or archetype != "crud"` |
| `GET /export` | `step8_export.html` | All | Evidence sidecar option | Conditional on review/export flow |
| `GET /knowledge` | `knowledge_workspace.html` | All | Full workspace | `ks_available` flag set from subprocess check |

### 3.2 KS Session State

```python
# app/models/project.py — current
class ProjectSession(BaseModel):
    ks_project_id: Optional[str] = None   # workspace identity
    ks_active: bool = False                # activation flag (NOT a user toggle)
    ks_workspace_state: KSWorkspaceState   # suggestion/evidence state

class StudioProject(BaseModel):           # save file
    ks_project_id: Optional[str] = None
    ks_active: bool = False
```

`ks_active` is set to `True` in two places:
1. `ensure_workspace_identity()` — when minting a new workspace ID (before user
   has asked for KS help)
2. `mark_workspace_active()` — when user visits `/knowledge`

**Problem:** `ensure_workspace_identity` can be triggered by workspace ID
resolution, not user action. This means `ks_active` can become `True` before
the user opts in to Knowledge Assist.

### 3.3 `build_workspace_summary` Call Pattern

`build_workspace_summary(session)` is called unconditionally on every `GET /`
request in `project.py`. The result drives the "Knowledge Workspace" panel and
"KS Status" indicator rendered in `step1_project.html`. These surfaces are
visible to all users regardless of whether they have ever touched the workspace
or want KS.

### 3.4 Scattered KS Checks

```
app/routes/entities.py  line 446: ks_review_enabled = archetype=="crud" and bool(entities)
app/routes/rules.py     line 306: not session.ks_active
app/routes/review.py    line 57:  not workspace_id or not canonical_entities or not session.ks_active
app/services/ks_workspace.py line 35: session.ks_active = True  (side-effect in ID minting)
```

No single authoritative capability gate. Each site carries its own partial
condition. Adding new KS surfaces (rule suggestions, mapping suggestions) will
add more scattered checks unless a central guard is established.

### 3.5 Post-Kafka Model Additions

The Kafka authoring flow adds the following to `ProjectSession`:
- `kafka_config: KafkaConfig` — consumer group, topic pairs
- `kafka_route_models: list[KafkaRouteModel]` — routes with patterns,
  upstream/downstream topics, schemas, routing rules (router pattern)
- `kafka_route_transforms: list[KafkaRouteTransform]` — fixed-route transform
  rows and router-target transform rows

The Kafka `kafka_step3_transforms.html` template is information-dense: it shows
all routes, each with request/response transform rows or per-target transform
rows for the router pattern. There is currently no KS surface in any Kafka
step, which is correct — router transform suggestions are Wave 3 in PR #129 and
are technically blocked on the router manifest contract stabilising.

---

## 4. Target UX Principles

1. **Off by default.** No KS UI is rendered until the user explicitly enables
   Knowledge Assist. No KS subprocess is started. No KS adapter is called.

2. **One toggle, one place.** The Knowledge Assist toggle lives in Step 1, inside
   the project setup section. Not on a welcome banner, not in a separate settings
   page, not duplicated across steps.

3. **User-facing label is "Knowledge Assist."** Never expose "Knowledge Server,"
   "MCP," "KS," or subprocess language to the user.

4. **Compact suggestion affordance.** Suggestions appear as a small badge
   (`💡 N suggestions`) in the relevant step, only when suggestions actually
   exist. Zero suggestions = zero KS pixels in that step.

5. **No empty KS states.** If KS returns nothing, show nothing. No "KS checked
   but found nothing" messaging in the main wizard flow.

6. **No degraded-mode warnings in the wizard flow.** KS unavailability is silent
   in all wizard steps. The only place a degraded-mode warning ever appears is
   inside the Knowledge Workspace itself (where the user deliberately opened a
   KS surface).

7. **Evidence is drill-down.** Citations and provenance are accessible on demand
   from within a suggestion drawer. They are never pre-expanded in the wizard
   flow.

8. **Provenance persists quietly.** When a suggestion is accepted, a small badge
   (`✓ from BRD Q2`) appears on the affected form field. This is the only
   persistent KS mark in the main flow.

9. **Engine never changes.** Engine is deterministic. It does not know KS,
   LegacyExtractor, or AI exist. It receives only the final approved manifest.

10. **LegacyExtractor and AI follow the same pattern.** They are future,
    optional, and gated by the same capability model. They do not get separate
    parallel suggestion rails in Studio.

---

## 5. Knowledge Assist Toggle Design

### 5.1 Placement

The toggle lives in Step 1 inside the project setup form, below the archetype
selector and above the "Save and continue" button. It is rendered as a named
feature panel, not a checkbox buried in a form.

```
Step 1 — Project Setup
───────────────────────────────────────────────────────────────────
  App name        [________________________]
  Archetype       [CRUD ▼]
  Target profile  [Spring Boot Legacy Compatible ▼]

  ┌──────────────────────────────────────────────────────────────┐
  │  ✦ Knowledge Assist                            [OFF ●]       │
  │  Upload documents and get field, rule, and mapping           │
  │  suggestions as you build. Off by default.                   │
  │                                                              │
  │  [Learn more ↗]                                              │
  └──────────────────────────────────────────────────────────────┘

  [Save and continue →]
───────────────────────────────────────────────────────────────────
```

When the user flips the toggle to ON, the panel expands:

```
  ┌──────────────────────────────────────────────────────────────┐
  │  ✦ Knowledge Assist                            [ON ●]        │
  │  Documents: 0 ingested · Not yet opened        [Open ↗]     │
  │                                                              │
  │  Upload BRDs, DDLs, field mappings, and rule specs to        │
  │  get evidence-backed suggestions at each authoring step.     │
  └──────────────────────────────────────────────────────────────┘
```

The `[Open ↗]` link leads to `/knowledge` (Knowledge Workspace). This link is
**only visible when Knowledge Assist is ON.**

### 5.2 Toggle Behaviour

| Action | Effect |
|---|---|
| Toggle OFF (default) | No KS subprocess started. No workspace summary fetched. No KS panel rendered. |
| Toggle ON (first time) | Workspace identity minted (lazily on first actual KS tool call, not on toggle flip). KS subprocess not yet started — waits for first use. |
| Toggle ON → navigate to Step 3 | KS subprocess starts lazily when Step 3 fetches suggestions. |
| Toggle ON → open `/knowledge` | KS subprocess starts on first tool call from workspace page. |
| Toggle OFF after being ON | KS UI hidden immediately. KS subprocess stops (or is allowed to die). `knowledge_assist_enabled` set to `False`. Workspace identity and ingested data are preserved so re-enabling later is seamless. |
| New project (reset) | Toggle defaults to OFF. `knowledge_assist_enabled = False`. |
| Save project with toggle ON | `knowledge_assist_enabled = True` persisted in save file. |
| Open saved project with toggle ON | Toggle restored as ON; KS subprocess starts lazily on first actual use. |

### 5.3 Toggle Interaction with `ks_active`

`ks_active` in the current session model is a low-level activation flag. After
introducing `knowledge_assist_enabled`, the relationship is:

- `knowledge_assist_enabled` = user's product-level decision (persisted in save
  file, controls all UI and adapter calls)
- `ks_active` = subprocess-level activation (set when the subprocess actually
  starts; can be True only if `knowledge_assist_enabled` is True)

`ks_active` must never become True when `knowledge_assist_enabled` is False.
The `ensure_workspace_identity()` function must not set `ks_active = True` as a
side effect of minting a workspace ID.

---

## 6. Capability Model

### 6.1 `ProjectCapabilities` Model

Introduce a new model in `app/models/project_capabilities.py`:

```python
# app/models/project_capabilities.py  (new file)

from __future__ import annotations
from pydantic import BaseModel


class ProjectCapabilities(BaseModel):
    """
    Project-level capability flags for optional assistive features.

    All assistive features default to OFF. Studio behaviour is identical to
    the non-KS flow when all flags are False.
    """
    knowledge_assist_enabled: bool = False
    # Future extensions:
    # legacy_assist_enabled: bool = False    # requires knowledge_assist_enabled=True
    # ai_assist_enabled: bool = False        # requires knowledge_assist_enabled=True

    @property
    def any_assist_active(self) -> bool:
        return self.knowledge_assist_enabled
        # Future: return any([self.knowledge_assist_enabled,
        #                     self.legacy_assist_enabled])
```

### 6.2 Where the Model Lives

`ProjectCapabilities` is embedded in `ProjectSession` and `StudioProject`:

```python
# app/models/project.py

class ProjectSession(BaseModel):
    # ... existing fields ...
    capabilities: ProjectCapabilities = Field(default_factory=ProjectCapabilities)
    ks_project_id: Optional[str] = None
    ks_active: bool = False          # subprocess-level flag; never True if capabilities.knowledge_assist_enabled is False
    ks_workspace_state: KSWorkspaceState = Field(default_factory=KSWorkspaceState)
    is_brand_new: bool = False       # transient; True only for new projects created in this session
                                     # open_project() always sets this to False (including migrated files)
                                     # save_project() clears it after first save; never persisted to the save file

class StudioProject(BaseModel):
    # ... existing fields ...
    capabilities: ProjectCapabilities = Field(default_factory=ProjectCapabilities)
    ks_project_id: Optional[str] = None
    ks_active: bool = False
```

### 6.3 Save/Load Migration

`project_file_service.py` must include a migration path for existing save files
that have no `capabilities` key:

```python
# project_file_service.py — migration guard (existing pattern)
migrated.setdefault("capabilities", {"knowledge_assist_enabled": False})
```

**Conservative migration for existing saves:** Do NOT promote `ks_active: true`
to `knowledge_assist_enabled: true`. The problem statement (§3.2) established
that `ks_active` can become `True` as an accidental side-effect of workspace ID
minting — not from an explicit user choice. Promoting it would silently enable
Knowledge Assist for every user who happened to visit `/knowledge` or trigger
identity minting, which is precisely the leaky behaviour this design is
removing.

Instead, default `knowledge_assist_enabled` to `False` for all existing saves,
and preserve `ks_project_id` dormant so users who genuinely used KS can
re-enable Knowledge Assist and reconnect to their existing workspace:

```python
# project_file_service.py — conservative migration
# Always default knowledge_assist_enabled to False for existing saves.
# ks_project_id is preserved so the user can re-enable and reconnect.
migrated.setdefault("capabilities", {"knowledge_assist_enabled": False})
# Do NOT promote ks_active → knowledge_assist_enabled.
# ks_active=True in a legacy save is not reliable evidence of deliberate user choice.
```

Future consideration: if a stronger signal is available — such as non-empty
`ks_workspace_state.review_history` or accepted `ks_workspace_state.evidence_links`
— a future migration pass could offer to restore KA. That opt-in promotion
requires a dedicated migration design. Do not implement it in the S1 PR.

### 6.4 Central Capability Guard in the Assist Service Layer

All KS adapter calls go through a new `AssistService` layer:

```python
# app/services/assist_service.py  (new file)

from app.models.project import ProjectSession
from app.integrations.ks_integration import KSClient, KSUnavailableError

class AssistService:
    """
    Studio-facing assistant service layer.

    Two method categories with different failure contracts:

    WIZARD BADGE METHODS (get_*_badge, get_*_suggestions):
      - Fail silently — return None/empty on any error or KS unavailability.
      - No degraded-mode information surfaced to routes or templates.
      - Used by wizard step routes; templates render nothing when result is None.

    WORKSPACE STATUS METHODS (get_workspace_status, get_document_list, etc.):
      - Return structured status/degraded view models.
      - Failures are surfaced as degraded state inside the Knowledge Workspace only.
      - Used by the /knowledge route exclusively.

    The raw KSClient transport remains session-agnostic and is not capability-aware.
    """

    def __init__(self, ks_client: KSClient):
        self._ks = ks_client

    # ── WIZARD BADGE METHODS ──────────────────────────────────────────────────

    def get_field_suggestion_badge(
        self, session: ProjectSession, entity: str
    ) -> FieldSuggestionBadge | None:
        """
        Returns a badge view model when suggestions exist, None otherwise.

        This is the lazy-start entry point for the KS subprocess: if KA is
        enabled but the subprocess has not started yet (ks_active=False),
        attempt to start it now. On success, set ks_active=True and proceed
        with the suggestion fetch. On any failure, return None silently.

        Do NOT add `if not session.ks_active: return None` — that would prevent
        Step 3 (or any wizard step) from ever being the first call that wakes
        up the subprocess.
        """
        if not session.capabilities.knowledge_assist_enabled:
            return None
        try:
            # Lazy subprocess start: AssistService resolves workspace config
            # from session and passes only primitives to the transport layer.
            # KSClient must NOT receive ProjectSession — it is transport-only.
            if not session.ks_active:
                workspace_id = ensure_workspace_identity(session)
                db_path = workspace_db_path_for_id(workspace_id)
                allowed_roots = workspace_allowed_roots_for_id(workspace_id)
                self._ks.ensure_started(
                    db_path=db_path,
                    allowed_roots=allowed_roots,
                )   # raises KSUnavailableError if it cannot start
                session.ks_active = True
                save_session(session)
            result = self._ks.suggest_fields(session.ks_project_id, entity)
            if not result.suggestions:
                return None
            return FieldSuggestionBadge(count=len(result.suggestions), entity=entity)
        except (KSUnavailableError, Exception):
            return None   # Fail silently — no degraded warning in wizard flow

    # Future: get_rule_suggestion_badge, get_mapping_suggestion_badge, etc.
    # All follow the same pattern: capability check → resolve config → lazy start
    # (primitives only to KSClient) → call → None on any failure.

    # ── WORKSPACE STATUS METHODS ──────────────────────────────────────────────

    def get_workspace_status(self, session: ProjectSession) -> WorkspaceStatus:
        """
        Returns a structured status view model for the Knowledge Workspace page.

        Unlike badge methods, this surfaces degraded/unavailable state so the
        workspace can show a meaningful banner. Only used by GET /knowledge.
        Still gated on knowledge_assist_enabled — redirects handle the OFF case
        before this method is ever called.
        """
        if not session.capabilities.knowledge_assist_enabled:
            # Should not be reached: /knowledge redirects when KA is OFF.
            return WorkspaceStatus(available=False, degraded=True,
                                   warning="Knowledge Assist is off.")
        try:
            if not session.ks_active:
                workspace_id = ensure_workspace_identity(session)
                db_path = workspace_db_path_for_id(workspace_id)
                allowed_roots = workspace_allowed_roots_for_id(workspace_id)
                self._ks.ensure_started(
                    db_path=db_path,
                    allowed_roots=allowed_roots,
                )   # KSClient stays session-agnostic; primitives only
                session.ks_active = True
                save_session(session)
            doc_list = self._ks.list_documents(session.ks_project_id)
            return WorkspaceStatus(available=True, degraded=False,
                                   document_count=len(doc_list.documents))
        except KSUnavailableError as e:
            return WorkspaceStatus(available=False, degraded=True,
                                   warning=str(e))

    # Future: get_document_list, search_documents, get_field_catalog — all
    # return structured results with degraded state rather than None.
```

Routes consume badge/panel view models only:

```python
# app/routes/entities.py — after refactor
ks_badge = assist_service.get_field_suggestion_badge(session, entity=canonical_entity)
context["ks_field_badge"] = ks_badge   # None when KA is OFF or 0 suggestions
```

Templates render based on the view model only:

```html
{# step3_entities.html — after refactor #}
{% if ks_field_badge %}
  <button class="ks-badge" hx-get="/entities/ks/panel?entity={{ entity }}">
    💡 {{ ks_field_badge.count }} field suggestions
  </button>
{% endif %}
```

No template ever checks `ks_available`, `ks_active`, or `app_archetype == "crud"` for KS purposes. Capability logic lives in `AssistService` only.

---

## 7. Workspace Identity Behaviour

### 7.1 Problems with Current `ensure_workspace_identity`

```python
# ks_workspace.py — current (problematic)
def ensure_workspace_identity(session: ProjectSession) -> str:
    ...
    else:
        workspace_id = f"studio-ks-{uuid4()}"
        session.project_id = workspace_id
        session.ks_project_id = workspace_id
        session.ks_active = True        # ← side-effect: sets ks_active unconditionally
        changed = True
```

Setting `ks_active = True` as a side effect of minting a workspace ID is the
root cause of the leakage pattern. A workspace ID can be minted without the
user ever choosing to use Knowledge Assist.

### 7.2 Target Behaviour

| Condition | Current | Target |
|---|---|---|
| New project, KA OFF | Workspace ID minted on first `/knowledge` visit; `ks_active=True` | Workspace ID NOT minted; `ks_active` stays `False` |
| New project, KA OFF, user visits `/knowledge` | `ks_active=True`, workspace active | Redirect to Step 1 with prompt to enable KA first, or enable KA implicitly via deliberate workspace open |
| New project, KA ON (user toggles) | n/a (no toggle exists) | Workspace ID minted lazily on first KS tool call; `ks_active` stays `False` until subprocess actually starts |
| KA ON, user navigates to Step 3 | n/a | Subprocess starts lazily; `ks_active=True` set by `AssistService` on first successful call |
| KA OFF after being ON | n/a | `ks_active=False`; subprocess stopped; workspace ID and data preserved in session |

### 7.3 `ensure_workspace_identity` Refactoring

Remove the `session.ks_active = True` side-effect from identity minting:

```python
# ks_workspace.py — target
def ensure_workspace_identity(session: ProjectSession) -> str:
    """
    Return the durable workspace ID. Mints a new ID if needed.
    Does NOT set ks_active — that is the AssistService's responsibility.
    Caller must ensure session.capabilities.knowledge_assist_enabled is True
    before calling this function.
    """
    changed = False
    if session.project_id:
        if session.ks_project_id != session.project_id:
            session.ks_project_id = session.project_id
            changed = True
    elif session.ks_project_id:
        session.project_id = session.ks_project_id
        changed = True
    else:
        workspace_id = f"studio-ks-{uuid4()}"
        session.project_id = workspace_id
        session.ks_project_id = workspace_id
        changed = True
    # NOTE: ks_active is NOT set here. AssistService sets it on first subprocess start.
    if changed:
        save_session(session)
    return session.project_id or session.ks_project_id or ""
```

### 7.4 Visiting `/knowledge` with KA OFF

If a user navigates directly to `/knowledge` while `knowledge_assist_enabled` is
False, the route should redirect to Step 1 with a flash message:

```
"Knowledge Assist is off. Enable it in Step 1 to use the Knowledge Workspace."
```

This prevents workspace access from implicitly activating KS.

---

## 8. Knowledge Workspace v3 Layout

### 8.1 Current Limitations

- Single scroll page: upload form → document list → field catalog
- No grouping, no pagination, no filtering by type/entity/status
- No split-pane or detail view for individual documents or fields
- Evidence and citation drill-down not available from this page
- Upload form dominates the page even after documents are ingested
- "Load more" / pagination not present

### 8.2 Target: Two-Panel, Search-First Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Knowledge Workspace  ·  project: acme-loans        [+ Add Documents ▼] │
├────────────────────────────┬────────────────────────────────────────────┤
│  LIBRARY                   │  DETAIL                                    │
│  ─────────────────────    │                                              │
│  [🔍 Search…           ]  │  ← Select a document or field to view       │
│  [Type: All ▼] [Entity ▼] │                                              │
│                            │                                              │
│  ▶ DDL / Schema   (3) ─── │                                              │
│    ● acct_v2.sql           │                                              │
│    ● loans.sql             │                                              │
│    ○ payments.sql  ···     │  (○ = indexing in progress)                 │
│                            │                                              │
│  ▶ BRD / Business  (2) ── │                                              │
│    ● brd_q2_2026.pdf       │                                              │
│    ✗ brd_draft.docx  [!]  │  (✗ = parse failed)                         │
│                            │                                              │
│  ▶ Field Mappings  (1) ── │                                              │
│    ● field_map_v3.xlsx     │                                              │
│                            │                                              │
│  ──────────────────────── │                                              │
│  FIELD CATALOG             │                                              │
│  [Entity: All ▼]           │                                              │
│    Account    (14 fields) ▶│                                              │
│    Payment    (9 fields)  ▶│                                              │
│    Loan       (6 fields)  ▶│                                              │
│                            │                                              │
│  [Load more]               │                                              │
└────────────────────────────┴────────────────────────────────────────────┘
```

### 8.3 Left Panel Rules

- Documents grouped by type: DDL / Schema, BRD / Business Rules, Field
  Mappings, Kafka Schemas, Other — collapsible sections
- Status indicators per document:
  - `●` — indexed and ready
  - `○` + spinner — indexing in progress (auto-refresh every 5s)
  - `✗` — parse failed; click shows error detail in right panel
- Field catalog as a collapsible section below documents, entity-grouped with
  field counts
- Search: full-text across document names, entity names, and field names
  simultaneously; results highlight matching items across all sections
- Type and Entity filters refine both document list and catalog
- Pagination: show 20 documents per group; "Load more" link per group
- No endless scroll of extracted field values in the left panel

### 8.4 Right Panel Rules

| Left panel selection | Right panel shows |
|---|---|
| Nothing selected | "Select a document or field" hint |
| Document row | Document title, type, ingested date, chunk count, sections; [Delete] action |
| Failed document | Error detail: file type, parse error message, suggested fix |
| Entity in field catalog | Field list for that entity; each field shows: name, type, source document, confidence |
| Field in catalog | Evidence detail: all citations for that field (doc name, section, snippet, confidence); conflict hint if applicable |

Evidence drill-down is on-demand — never pre-expanded. The right panel is the
only place evidence/citation detail appears; it does not appear in the main
wizard flow.

### 8.5 Upload Flow

`[+ Add Documents ▼]` opens a modal overlay with:
- Drag-and-drop zone
- "Choose file" button
- Supported types displayed: `.md .pdf .docx .xlsx .sql .csv`
- Optional description field
- [Upload] button

The modal closes on successful upload and the left panel refreshes to show the
new document (status: indexing). The upload form does not dominate the
workspace page.

---

## 9. Step-by-Step OFF/ON Behaviour

The table below defines exactly what is shown and what is called at each Studio
step for all three archetypes, in both Knowledge Assist states.

> Interpretation note: "Kafka steps" refers to the three Kafka-specific wizard
> steps (Topic Ingest, Route Config, Transforms), not the shared steps that
> Kafka projects also traverse (Step 1, Step 7, Step 8).

| Step | Route | Knowledge Assist OFF | Knowledge Assist ON (0 suggestions) | Knowledge Assist ON (suggestions available) |
|---|---|---|---|---|
| **Step 1** Project Setup | `GET /` | No KS panel. No "Open Knowledge Workspace" link. No KS subprocess. `build_workspace_summary` not called. | KA toggle shown as ON. KS subprocess not yet started. Document count: 0. `[Open ↗]` link visible. | KA toggle ON. Brief doc count + status in toggle panel. `[Open ↗]` link visible. |
| **Step 2** Upstream Contract | `GET /upstream` | No KS UI | No KS UI | No KS UI — upstream contract is user-provided |
| **Step 3** Entity / Fields (CRUD) | `GET /entities` | No KS UI anywhere in step | No KS badge — nothing shown | `💡 N field suggestions` compact button (right-aligned in entity header). Click → drawer opens. Zero accepted = no provenance badges. |
| **Step 3b** Route / Transform (Passthrough) | `GET /passthrough` | No KS UI | No KS UI | No KS UI (mapping suggestions are Wave 2, post KS-B3) |
| **Kafka Step 1** Topic Ingest | `GET /kafka/topics` | No KS UI | No KS UI | No KS UI |
| **Kafka Step 2** Route Config | `GET /kafka/routes` | No KS UI | No KS UI | No KS UI in MVP. Future (KS-B3 Wave 2): `💡 N mapping suggestions` compact badge per route section for fire-and-forget / request-reply patterns only |
| **Kafka Step 3** Transforms | `GET /kafka/transforms` | No KS UI | No KS UI | No KS UI (router transform suggestions are Wave 3, technically blocked — see §10) |
| **Step 4** Downstream Interfaces | `GET /downstream` | No KS UI | No KS UI | No KS UI in MVP; future: `💡 N mapping suggestions` for passthrough (post KS-B3) |
| **Step 5** Data Handoffs | `GET /handoffs` | No KS UI | No KS UI | No KS UI |
| **Step 6** Rules | `GET /rules` | No KS UI. No advisory signals. No conflict hints. | Nothing — if KS returns 0 rule/conflict suggestions, show nothing | `💡 N rule suggestions` badge + `⚠️ N conflicts` badge (separate, only when non-zero). Click each → separate drawers. |
| **Step 7** Review | `GET /review` | Clean review. No advisory signals card. No KS-related copy. | Clean review | Clean review + `📋 Evidence used` link (only if ≥1 suggestion was accepted/edited during this session) |
| **Step 8** Export | `GET /export` | Normal export. No evidence sidecar option. | Normal export. No evidence sidecar option (no accepted suggestions). | `☑ Include evidence sidecar (evidence-trail.json)` checkbox appears only if ≥1 suggestion was accepted or edited |

### 9.1 Suggestion Drawer Pattern

All suggestion surfaces follow a single drawer pattern. The canonical
multi-scope badge and drawer contract for KS-B2 / KS-B3 Studio work is now
defined in
[Studio UX v3 Multi-Type Suggestion Drawer Pattern](./studio-ux-v3-suggestion-drawer-pattern.md).
The sketch below remains the single-scope field-suggestion baseline.

```
[Main step content]                              [💡 4 field suggestions]
                                                          ↓ click
                                ┌─────────────────────────────────────────┐
                                │ Field Suggestions  ·  Account      [✕]  │
                                │ ─────────────────────────────────────── │
                                │ amountMinorUnits  BIGINT  [✓ Accept]    │
                                │   📄 acct_v2.sql, line 34               │
                                │                                          │
                                │ accountStatus  VARCHAR(20)  [✓ Accept]  │
                                │   📄 brd_q2.pdf §3.1                    │
                                │                           [✎ Edit] [✗]  │
                                │                                          │
                                │ sortCode  CHAR(8)  [✓ Accept]           │
                                │   📄 acct_v2.sql + brd_q2.pdf           │
                                │                                          │
                                │ [Save decisions]                         │
                                └─────────────────────────────────────────┘
```

Rules:
- Drawer slides over the main content; does not push or reflow layout
- Closes on `[✕]`, Escape, or click-outside
- Per-session state: close state remembered within the session
- Evidence citation is inline (doc name + location) — click opens full evidence
  detail in a nested panel or the Knowledge Workspace detail view
- "Save decisions" writes accepted/edited/rejected to KS via
  `submit_suggestion_decisions`
- After save, accepted fields receive a small inline provenance badge on the
  entity form field: `✓ acct_v2.sql`

---

## 10. Kafka Awareness

### 10.1 Current Kafka Step Structure

The post-Kafka Studio adds three archetype-specific steps to the wizard:

| Kafka Step | Route | Template | Purpose |
|---|---|---|---|
| Topic Ingest | `/kafka/topics` | `kafka_step1_topics.html` | Consumer groups, topic pairs, schema references |
| Route Config | `/kafka/routes` | `kafka_step2_routes.html` | Route patterns (fire-and-forget, request-reply, router), upstream/downstream topics, routing rules, NACK config |
| Transforms | `/kafka/transforms` | `kafka_step3_transforms.html` | Fixed-route transform rows and router per-target transform rows |

The Kafka Transforms template is already information-dense (254 lines; per-route
sections with request/response transform grids and per-target router transform
grids). Adding suggestion surfaces here must not increase visual complexity.

### 10.2 Future KS Mapping Suggestions for Kafka (Wave 2)

When KS-B3 mapping suggestions are ready, standard Kafka routes
(fire-and-forget, request-reply) are eligible for mapping suggestions because
their `transform_mapping` paths are stable.

Placement: a compact `💡 N mapping suggestions` badge in the **Route Config
step** (Step 2 / `/kafka/routes`) header per route section. Not in the
Transforms step — that step is for authoring transform rows, not for suggestion
review.

### 10.3 Kafka Router Transform Suggestions (Wave 3 — Blocked)

Router-pattern transform suggestions (`scope=transforms`,
`router_config.targets.{T}.request_transform`) are **technically blocked** until:

- Kafka router Engine and Studio PRs 1–8 are merged
- `manifest-v1.schema.json` `routerConfig` definition is stable
- `RouterConfig` Pydantic model is in its final form

When unblocked, placement would be inside the Transforms step (`/kafka/transforms`),
as a per-target compact badge within the router target transform grid. This
surface must not expand until the contract is frozen.

### 10.4 What the Kafka Steps Do NOT Need

- No KS workspace integration in topic or route config steps
- No suggestion badges for schema references or NACK config (not suggestion-eligible)
- No changes to the existing Kafka authoring forms
- No routing-logic suggestions (routing rules are user-defined business logic)

---

## 11. LegacyExtractor Integration Pattern

### 11.1 Guiding Constraint

LE must not create a second parallel suggestion rail in Studio. Studio users
see one unified suggestion surface per step, with provenance distinguishing the
source. LE does not get its own panels.

### 11.2 Recommended Architecture

LE output is ingested into KS as provenance-tagged evidence. Studio surfaces it
through the same `ManifestSuggestion` envelope as document-backed suggestions.

```
LE artifacts  (entity/field/rule candidates)
      ↓  ingest with provenance tag: "le-extraction"
EdgeForgeKnowledgeServer  (unified suggestion service)
      ↓  ManifestSuggestion with source_type: "le" | "document"
EdgeForgeStudio  (single drawer per step)
```

### 11.3 Second Toggle: "Legacy Analysis"

A second capability flag `legacy_assist_enabled: bool = False` (future) sits
beneath Knowledge Assist in Step 1:

```
  ┌──────────────────────────────────────────────────────────────┐
  │  ✦ Knowledge Assist                            [ON ●]        │
  │  Documents: 5 ingested · Workspace ready       [Open ↗]     │
  │                                                              │
  │  Legacy Analysis                               [OFF ●]       │
  │  Surface candidates from legacy code analysis.              │
  │  (Requires Knowledge Assist ON)                              │
  └──────────────────────────────────────────────────────────────┘
```

Rules:
- "Legacy Analysis" toggle is greyed out when Knowledge Assist is OFF
- Enabling Legacy Analysis does NOT automatically enable Knowledge Assist
- If KA is turned OFF while Legacy Analysis is ON, Legacy Analysis is implicitly
  paused (its UI disappears with all other KS surfaces)

### 11.4 Studio UX for LE-sourced Suggestions

Inside the suggestion drawer, LE-sourced candidates appear alongside
document-sourced ones, differentiated by provenance icon:

```
  amountMinorUnits  BIGINT  [✓ Accept]
    📄 acct_v2.sql, line 34       ← document evidence

  accountType  VARCHAR(20)  [✓ Accept]
    🏛 Legacy Analysis — AccountService.java, line 112  ← LE evidence

  currencyCode  CHAR(3)  [✓ Accept]
    📄 brd_q2.pdf §3.1  +  🏛 Legacy Analysis  ← both sources
```

The accept/edit/reject lifecycle is identical regardless of evidence source.

### 11.5 What LE Must NOT Do

- Write directly to the Studio manifest
- Create a separate right-rail or panel section alongside the KS suggestion panel
- Surface raw complexity (class hierarchies, intermediate parse artifacts, byte offsets)
- Produce suggestions without the user enabling Legacy Analysis first
- Operate when Knowledge Assist is OFF

---

## 12. Optional AI Fit

### 12.1 Position

AI assistance is future only. No AI surfaces exist in Studio today, and none
should be introduced until:

1. KS-B5 AI provider layer is designed and reviewed (post PR #129 KS-B2+B3)
2. A separate data-handling / redaction design is approved (see PR #129 §7.1 ⚠️)
3. Enterprise production suitability is confirmed

### 12.2 Capability Flag

`ai_assist_enabled: bool = False` (future) would be the third capability flag,
below Legacy Analysis in Step 1. It requires Knowledge Assist ON and must be
explicitly enabled.

### 12.3 Design Constraints

- If a future provider/model layer is implemented, Studio must not call providers
  directly; the provider boundary must remain within KS.
- A future provider-backed suggestion mode may use `ai_mode="generation"` on
  `suggest_manifest_candidates` — same tool, same drawer, same lifecycle.
- `ask_document` AI chat surface, if ever exposed, appears in the Knowledge
  Workspace only, not in the main wizard flow
- No chat-first redesign of Studio
- Deterministic retrieval must remain fully functional without a provider/model layer.
- No provider-backed mode is implemented today; KS-B5 requires a verified pre-send
  sanitization design and implementation before one can be added.

---

## 13. Architecture Boundaries

### 13.1 Layering Model

```
Templates
  └── render badge/drawer view models only
  └── no ks_active / ks_available / archetype checks for KS purposes

Routes
  └── call AssistService for badge/panel view models
  └── no direct KS adapter calls
  └── no subprocess lifecycle management

AssistService  (new)
  └── capability check first (returns None/empty if KA disabled)
  └── calls KSClient via ks_integration.py
  └── fails silently (never propagates KS errors to routes)
  └── sets ks_active on first successful subprocess contact

KSClient / ks_integration.py
  └── subprocess transport only (session-agnostic)
  └── no capability logic
  └── no knowledge of knowledge_assist_enabled

ks_workspace.py
  └── workspace identity management
  └── does NOT set ks_active as a side-effect
  └── does NOT call any KS tool

ProjectCapabilities  (new model)
  └── single source of truth for all assist feature flags
  └── persisted in save file
  └── default: all False
```

### 13.2 Invariants

1. `capabilities.knowledge_assist_enabled == False` → no KS subprocess, no KS
   HTML, no KS adapter call, no KS subprocess error surfaced anywhere in the wizard
2. `ks_active == True` can only be reached when `knowledge_assist_enabled == True`
3. All template KS surfaces in wizard steps guarded by `{% if ks_badge %}` (view
   model) — never by `{% if ks_active %}` or `{% if ks_available %}`
4. **Wizard badge methods** in `AssistService` return `None` or empty on any
   exception — no errors or degraded state reach wizard step routes or templates
5. **Workspace status methods** in `AssistService` return structured
   `WorkspaceStatus` (with `degraded=True` + warning) on KS failure — used only
   by `GET /knowledge`, never by wizard step routes
6. `ensure_workspace_identity()` does not set `ks_active = True`
7. Visiting `/knowledge` with KA OFF redirects to Step 1 with an informational
   message — workspace access cannot bypass the capability flag
8. `ks_active` is never promoted from a legacy save file as evidence of KA
   user intent; `knowledge_assist_enabled` defaults to `False` in all migrations

### 13.3 Test Requirements

```python
# tests/test_studio_ka_off.py  (new — required before KS-B1 Studio / KS-B2 UX work begins)

def test_step1_no_ks_html_when_ka_off():
    # KA off → no KS panel, no workspace link, no workspace_summary call

def test_step3_no_ks_badge_when_ka_off():
    # KA off → no ks_field_badge in context, no badge in HTML

def test_step6_no_advisory_when_ka_off():
    # KA off → no advisory conflicts card in HTML

def test_step7_no_evidence_link_when_ka_off():
    # KA off → no "Evidence used" link in HTML

def test_knowledge_workspace_redirects_when_ka_off():
    # GET /knowledge with KA off → redirect to / with flash

def test_ks_subprocess_not_started_when_ka_off():
    # Navigate through all steps with KA off → assert subprocess never started
```

---

## 14. Repo Impact Table

| Repo | Changes | Priority | Notes |
|---|---|---|---|
| **`EdgeForge`** | This design doc; possible updates to `docs/ks-broader-suggestion-scopes-design.md` §10 and `docs/studio-ks-orchestration-design.md` | Medium | Design-only in this PR |
| **`EdgeForgeStudio`** | **(1)** New `app/models/project_capabilities.py`; **(2)** `ProjectCapabilities` embedded in `ProjectSession` and `StudioProject`; **(3)** KA toggle in `step1_project.html` + route; **(4)** `app/services/assist_service.py` capability guard; **(5)** Remove `ks_active = True` side-effect from `ks_workspace.py`; **(6)** Migrate `build_workspace_summary` to be KA-conditional; **(7)** Replace scattered `ks_active`/`ks_available`/archetype checks with `AssistService` badge calls; **(8)** Compact badge/drawer pattern in Steps 3, 6, 7, 8; **(9)** Knowledge Workspace v3 two-panel layout; **(10)** `GET /knowledge` guard redirect when KA OFF; **(11)** `tests/test_studio_ka_off.py` | **High** | No KS code changed; Studio-only |
| **`EdgeForgeKnowledgeServer`** | No changes in this design PR. When KS-B0/B1/B2 begin: schema migration, broader tool contracts per PR #129. | Medium | KS-B0 (schema-only) may proceed independently; Studio-facing KS-B1/KS-B2 work requires S1–S6 complete |
| **`LegacyExtractor`** | No changes now. Future: define LE output format compatible with `ManifestSuggestion` envelope; KS ingestion interface (KS-B6 per PR #129). | Low / Future | Deferred until LE Phase 6 MVP |

---

## 15. Risk Table

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Residual `ks_active` / `ks_available` checks missed in templates after refactor → KS UI leaks when KA is OFF | Medium | High | Grep for `ks_active` and `ks_available` in templates as part of PR checklist; `test_studio_ka_off.py` suite enforces zero-KS-HTML invariant |
| `ensure_workspace_identity` called from an unexpected path and sets `ks_active=True` implicitly | Medium | Medium | Remove `ks_active = True` from identity minting; add assertion in test suite that `ks_active` is never set when `knowledge_assist_enabled=False` |
| KS subprocess crash propagates to route and causes 500 | Low (already handled) | Medium | `AssistService` wraps all calls in `try/except`; returns `None` on any exception; no exception reaches route handler |
| KA toggle state not persisted correctly on save/open → user's KA preference lost | Low | Medium | `capabilities` embedded in both `ProjectSession` and `StudioProject`; migration guard for legacy saves without `capabilities` key |
| Compact badge pattern regresses to always-visible empty states as more scopes are added | Medium | Medium | Badge generated by `AssistService` returns `None` when count is 0; template renders nothing when badge is None; enforced by pattern contract |
| Studio UX design spike (OQ6) for multi-type suggestion drawers delayed → KS-B2 Studio work starts without resolved UI pattern | Medium | Medium | OQ6 spike must be a named deliverable before KS-B2 Studio PR opens; gate KS-B2 Studio PR on UX spike doc approval |
| LE toggle added before KS-B5 is stable → LE suggestions surface through an unverified data path | Low (governance) | High | Legacy Analysis toggle is UI-only (greyed out) until KS-B6 LE interface is designed and implemented |
| AI mode enabled before pre-send redaction is designed | Low (governance) | High | AI toggle not added to UI until KS-B5 ships verified sanitisation; follows PR #129 §7.1 ⚠️ gate |
| `/knowledge` accessible without KA ON → implicit KS activation back-door | Medium | Medium | `GET /knowledge` route checks `capabilities.knowledge_assist_enabled`; redirects to Step 1 if OFF |

---

## 16. Recommended Implementation PR Sequence

### Phase S (Studio Readiness) — Required Before KS-B1 Studio Work and KS-B2 UX

| Order | PR Slice | Repo | Complexity | Gate |
|---|---|---|---|---|
| S1 | `ProjectCapabilities` model + session/save wiring + migration guard | `EdgeForgeStudio` | Low | This design approved |
| S2 | KA toggle in Step 1 (OFF by default) + `knowledge_assist_enabled` persisted in save file | `EdgeForgeStudio` | Low-Medium | S1 |
| S3 | `AssistService` capability guard + remove `ks_active=True` side-effect from `ks_workspace.py` | `EdgeForgeStudio` | Medium | S1 |
| S4 | Replace scattered `ks_active`/archetype KS checks → `AssistService` badge calls in routes + templates | `EdgeForgeStudio` | Medium | S2 + S3 |
| S5 | `GET /knowledge` redirect when KA OFF; `build_workspace_summary` KA-conditional | `EdgeForgeStudio` | Low | S2 |
| S6 | `tests/test_studio_ka_off.py` — prove all steps work with KA OFF, no subprocess started | `EdgeForgeStudio` | Medium | S4 + S5 |
| S7 | Knowledge Workspace v3 two-panel layout | `EdgeForgeStudio` | High | S2 (can run parallel to S3–S6) |
| S8 | Studio UX design spike doc (OQ6): multi-type suggestion drawer and badge pattern spec | `EdgeForge` docs | Medium | S6 (must complete before KS-B2 Studio); see [Studio UX v3 Multi-Type Suggestion Drawer Pattern](./studio-ux-v3-suggestion-drawer-pattern.md) |

### Phase KS (KS Broader Scopes)

KS-B0 through KS-B4 per PR #129 §10 sequence (15 PRs). KS-B4 (router
transforms) remains technically blocked on Kafka router PRs 1–8 independently
of the Studio readiness work.

**Gate clarification:** Phase S S1–S6 must complete before KS-B1 Studio
adapter work and KS-B2 UX work begin. KS-B0 is a schema-only change entirely
inside `EdgeForgeKnowledgeServer` (table rename + indexes, no Studio surface)
and may proceed independently or in parallel with Phase S once governance
approves. Do not block a pure DB migration PR on Studio readiness.

| Phase | Blocked on | Notes |
|---|---|---|
| KS-B0 DB migration | Governance gate (Kafka router Studio PRs complete) — **does not require Phase S** | Schema-only; `EdgeForgeKnowledgeServer` only; no Studio changes |
| KS-B1 tool contracts | KS-B0 + **S1–S6 complete** | KS side: new tools. Studio side: `AssistService` extension requires Phase S guard layer in place |
| KS-B2 rule/validation | KS-B1 + **S8 spike** | First broader-scope MVP |
| KS-B3 mapping/conflict | KS-B2 | Passthrough and Kafka fire-and-forget/request-reply only |
| KS-B4 router transforms | **Kafka router PRs 1–8 merged** | Technical blocker independent of all other sequencing |

---

## 17. Acceptance Criteria for Build PRs

These criteria apply to each Studio build PR in Phase S and each KS-B Studio-
side PR:

### S1 Acceptance Criteria

- [ ] `ProjectCapabilities` model exists in `app/models/project_capabilities.py`
- [ ] `ProjectSession.capabilities` field exists with `default_factory=ProjectCapabilities`
- [ ] `StudioProject.capabilities` field exists
- [ ] Migration guard in `project_file_service.py` handles saves without `capabilities` key: defaults `knowledge_assist_enabled` to `False`
- [ ] Legacy saves with `ks_active: true` are NOT promoted to `knowledge_assist_enabled: true` — `ks_project_id` is preserved dormant for later opt-in
- [ ] `ks_active` is never read as a migration signal for `knowledge_assist_enabled`

### S2 Acceptance Criteria

- [ ] KA toggle renders in Step 1 with default state OFF
- [ ] Toggle state persists on save and restores on open
- [ ] When OFF: no KS panel, no workspace link, no `build_workspace_summary` call
- [ ] When ON: KS toggle panel shows, workspace link visible
- [ ] Toggle flip does not cause page reload (HTMX or form POST)

### S3+S4 Acceptance Criteria

- [ ] `AssistService` exists with wizard badge methods (`get_*_badge`) returning `None` silently on any failure
- [ ] `AssistService` workspace status methods (`get_workspace_status`, etc.) return structured `WorkspaceStatus` with `degraded=True` on KS failure — used only by `GET /knowledge`
- [ ] `get_field_suggestion_badge()` does NOT guard on `ks_active`; it triggers lazy subprocess start if KA is enabled
- [ ] After a successful lazy KS start, `session.ks_active` is set to `True` by `AssistService`
- [ ] `ensure_workspace_identity()` does NOT set `ks_active = True`
- [ ] No `ks_active`, `ks_available`, or `app_archetype == "crud"` KS checks in templates
- [ ] All template KS surfaces in wizard steps gated by `{% if ks_badge %}` only

### S6 Acceptance Criteria

- [ ] All wizard steps render without error when `knowledge_assist_enabled=False`
- [ ] No KS subprocess is started during a full wizard run with KA OFF
- [ ] No KS-related HTML is present in any step response when KA OFF
- [ ] All existing CRUD/Kafka/Passthrough wizard behaviour unchanged when KA ON

### S7 (Workspace v3) Acceptance Criteria

- [ ] Two-panel layout renders for both empty and populated workspaces
- [ ] Document grouping by type with collapsible sections
- [ ] Document status indicators: indexed, indexing, failed
- [ ] Right panel shows document detail when a document is selected
- [ ] Right panel shows field evidence when a field is selected
- [ ] Field catalog is entity-grouped with counts
- [ ] Upload via modal overlay (not inline form)
- [ ] No endless scroll of raw extracted field values
- [ ] Accessible when KA ON; redirects to Step 1 when KA OFF

---

## 18. Follow-up Doc Updates Needed

### 18.1 PR #129 (`docs/ks-broader-suggestion-scopes-design.md`)

The following additions should be made to PR #129 before KS-B1 and KS-B2
implementation prompts are generated:

1. **New §: "Pre-implementation Studio Readiness Gate"** — list Phase S (S1–S6
   from this document) as prerequisites before **KS-B1 Studio adapter work and
   KS-B2 UX work** begin. KS-B0 (schema-only in `EdgeForgeKnowledgeServer`) may
   proceed independently and does not require Phase S. The current PR #129 §10.1
   assumes Studio is ready to receive broader suggestion surfaces; the
   `AssistService` capability guard layer (Phase S S1–S4) must be in place before
   any KS-B1 Studio PR opens.

2. **§10.2 KS-B1** — add note: *"The Studio `ks_integration.py` / `AssistService`
   extension for new tool wrappers may land as a separate Studio PR immediately
   after the KS tool changes merge. The `AssistService` capability guard pattern
   (from Studio UX v3 design) must be in place before this Studio PR opens."*

3. **§10.2 KS-B2** — split into three sub-PRs matching the Codex 15-PR sequence
   (KS backend / Studio UX / evidence sidecar) and correct the evidence sidecar
   repo label to `EdgeForgeKnowledgeServer` + `EdgeForgeStudio`.

### 18.2 `docs/studio-ks-orchestration-design.md`

Add a forward reference: *"Studio UX v3 assistive features design
(`studio-ux-v3-assistive-features-design.md`) introduces `ProjectCapabilities`
and `AssistService` as the authoritative capability gate layer. The subprocess
lifecycle rules in this document remain valid; the `AssistService` calls
`KSClient` only after confirming `knowledge_assist_enabled=True`."*

### 18.3 `docs/project-workspace-decision-ledger-design.md`

No structural changes needed. Forward reference to `ProjectCapabilities` as the
source of truth for whether workspace identity should be activated.

---

## 19. Non-Goals

The following are explicitly out of scope for this design and the build PRs that
derive from it:

- **No chat-first Studio redesign.** The optional `ask_document` surface, if
  ever added, lives in the Knowledge Workspace only.
- **No Engine changes.** Engine remains deterministic and does not know KS,
  LE, KA, or provider integrations exist.
- **No KS mandatory behaviour.** KS off by default; Studio functions identically
  without it.
- **No LegacyExtractor mandatory behaviour.** LE off by default; deferred to LE
  Phase 6 MVP.
- **No LLM/provider behaviour.** No LLM or provider integration exists today;
  KS-B5 and a separate data-handling design gate any future provider/model layer.
- **No KS/LE/KA auto-write to manifest.** All suggestions are pending until a
  human accepts, edits, or rejects them.
- **No changes to Kafka authoring flow.** Kafka steps are not modified; future
  KS mapping/transform suggestion surfaces are additive and Wave 2/3 only.
- **No vector search in Wave 1–2.** BM25/FTS5 is sufficient.
- **No network/SSE KS deployment.** KS remains local stdio-only.
- **No global welcome-banner toggle.** The KA toggle lives in Step 1, not on a
  splash screen.

---

## Addendum A — Save/Open Project Hardening

> **Status:** Design addendum — future Studio hardening PR (not S1).
> The S1 PR must include only the minimal `ProjectCapabilities` persistence and
> migration described in §6.2–§6.3. The hardening items below belong in a
> separate Studio PR after Phase S stabilises.

### A.1 Schema Version vs Save Revision

Two fields with distinct purposes currently share ambiguous naming:

| Field | Purpose | When it changes |
|---|---|---|
| `studio_project_schema_version` | Identifies the **save-file format** for migration logic | Only when the `StudioProject` model shape changes (new required fields, renamed keys, removed fields). Rarely — not on every save. |
| `project_revision` *(new)* | Monotonic counter tracking **how many times the project has been saved** | Increments on every successful save (Save, Save As both increment independently per file). Starts at `1`. |

**Current state:** `StudioProject` carries `studio_project_schema_version` but no save counter. The `capabilities` migration in S1 will increment `studio_project_schema_version` once. After that it should not change again until the next schema change.

**Target:** Add `project_revision: int = 1` to `StudioProject`. Increment on every successful `save_project()` call. Never reset except on "New project."

### A.2 Timestamps and User Identity

#### A.2a Timestamps

Add three ISO-8601 timestamps and two user identity fields to `StudioProject`:

```python
class StudioProject(BaseModel):
    # ... existing fields ...
    project_revision: int = 1
    created_at: Optional[str] = None     # set on first save (new project or Save As); never auto-populated
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    saved_at: Optional[str] = None       # set at write time by save_project()
    created_by: Optional[str] = None     # identity of first saver; never overwritten (except Save As)
    modified_by: Optional[str] = None    # identity of most recent saver; updated every save
```

| Field | Set when | Updated when |
|---|---|---|
| `created_at` | New project first saved | Never changed after initial save |
| `updated_at` | Any state mutation in the session (entity added, rule edited, etc.) | Updated in-memory by session mutations; written to file on save |
| `saved_at` | Written to the file by `save_project()` at the exact moment of write | Every successful save |
| `created_by` | New project first saved — value from `_current_user_hint()` | Never changed after initial save |
| `modified_by` | Every save — value from `_current_user_hint()` | Updated on every successful `save_project()` call |

External tooling (KS evidence links, LE output, audit logs) should anchor a
specific file snapshot using the stable triple: `project_id + project_revision
+ saved_at`. `modified_by` alongside it is optional audit display metadata —
useful for showing who saved a revision, but not part of the snapshot's unique
identity (see §A.8).

#### A.2b User Identity: Local Hint Without SSO

Studio is a local single-user tool today. SSO/auth is a future concern. For
now, user identity is a **best-effort hint** resolved from the environment:

```python
# app/services/project_file_service.py  (new helper)

import os

def _current_user_hint() -> Optional[str]:
    """
    Resolve a best-effort user identity string without requiring auth.

    Resolution order:
    1. EDGEFORGE_USER env var — explicit override (CI, scripts, future SSO injection).
       If set to the empty string (""), identity recording is suppressed (returns None).
    2. USER (Unix/macOS system username)
    3. USERNAME (Windows system username)
    4. None — unknown; field stored as null in save file

    When SSO lands, this function is replaced or wrapped by an auth-aware
    resolver that returns the authenticated principal. No schema change needed.
    """
    edgeforge_user = os.environ.get("EDGEFORGE_USER")
    if edgeforge_user is not None:
        # Env var is explicitly set (possibly empty). An empty string means
        # "suppress identity recording" — do not fall through to USER/USERNAME.
        return edgeforge_user or None

    return (
        os.environ.get("USER")
        or os.environ.get("USERNAME")
        or None
    )
```

`save_project()` calls `_current_user_hint()` at write time:

```python
def save_project(session: ProjectSession, path: str, *, save_as: bool = False) -> None:
    project = _session_to_project(session)
    now = datetime.utcnow().isoformat()
    user = _current_user_hint()

    project.saved_at = now
    project.modified_by = user

    if save_as:
        # Save As: diverging copy gets a fresh creator stamp and revision reset.
        # Always set unconditionally — the copy's lineage starts here regardless
        # of what the parent file had in created_at / created_by.
        project.project_revision = 1
        project.created_at = now
        project.created_by = user
    else:
        # Normal save path. Set created metadata ONLY for genuinely new projects.
        # Detection uses session.is_brand_new — an explicit flag set to True only
        # when the new-project wizard creates the session in memory. open_project()
        # always sets is_brand_new=False, including for migrated legacy files.
        # Do NOT use revision number alone: migrated files are initialised to
        # project_revision=1, so revision <= 1 cannot distinguish new from migrated.
        if session.is_brand_new and project.created_by is None:
            project.created_by = user
        if session.is_brand_new and project.created_at is None:
            project.created_at = now
        # Clear the flag after first save so subsequent saves don't re-trigger.
        session.is_brand_new = False

    # ... backup-before-overwrite, write to .tmp, atomic rename ...
```

**Semantics and privacy contract:**
- `created_by` and `modified_by` are **non-authoritative audit/display hints
  only**. They must never be used as authorization inputs, access control
  decisions, or identity verification.
- The fields are opt-out: set `EDGEFORGE_USER=""` to explicitly suppress
  identity recording. When `EDGEFORGE_USER` is present but empty, the function
  returns `None` immediately without falling through to `USER`/`USERNAME`.
  Users who want no identity stored should set `EDGEFORGE_USER=""` in their
  environment or launch script.
- Values from `USER`/`USERNAME` are mutable OS-level display names. They are
  not stable identifiers — they can change if the user renames their account.
  Treat stored values as "who the machine said it was at save time," not as a
  verified identity.

**Future SSO integration path:** When Studio adds an auth layer (OIDC, SAML,
or a lightweight hosted identity), `_current_user_hint()` is replaced or
wrapped by an auth-aware resolver. SSO should store a **stable principal
identifier** (e.g. the `sub` claim from an OIDC token) rather than a mutable
display name. The `created_by` / `modified_by` schema fields accept any string
— no migration is needed for the transition. Display-name resolution from the
stable principal is a UI concern, not a storage concern.

### A.3 Stable `project_id`

`project_id` is the durable Studio-owned workspace identity. It must survive:

- Save and re-open
- "Save As" to a new filename (the copy gets the **same** `project_id` as its
  parent — it is a branch of the same project lineage, not a new project)
- Schema migration on open
- `capabilities` flag changes

`project_id` must NOT be re-minted on:
- Normal save
- Schema migration
- Toggle changes
- Opening a saved file on a different machine (the `project_id` travels in the
  save file)

The `_reset_flow_state()` function in `project.py` correctly sets
`session.project_id = None` for "New project." This is the only intended reset
path. Migration code must explicitly preserve any existing `project_id` rather
than defaulting to `None`.

### A.4 Save vs Save As Behaviour

| Action | `project_id` | `project_revision` | `created_at` / `created_by` | `modified_by` | File path |
|---|---|---|---|---|---|
| First save (new project) | Minted now; stored in file | Set to `1` | Set to now / current user hint | Set to current user hint | User-chosen path |
| Save (overwrite) | Unchanged | Incremented | Unchanged | Updated to current user hint | Same path |
| Save As (new file) | **Copied from parent** — same lineage | Starts at `1` in the new copy | Set to now / current user hint in the new copy | Set to current user hint | New user-chosen path |
| Open then save | Unchanged | Incremented from loaded value | Unchanged | Updated to current user hint | Same or new path |

"Save As" does not create a new identity — it creates a diverging copy that
shares the same project lineage. If KS evidence links or LE outputs reference
`project_id`, they remain valid across "Save As" copies of the same project.

The Save As path is implemented as the `save_as=True` branch of `save_project()`
(see §A.2b). The branch resets `project_revision=1` and unconditionally sets
`created_at`/`created_by` to now/current user — regardless of what the parent
file had. This is distinct from the `is_brand_new` path, which only fills `None`
slots and is gated on the session flag set by the new-project wizard.

### A.5 Backup Before Overwrite

When saving to an existing file path (Save, not Save As), Studio should:

1. Write the new content to `<filename>.tmp` first
2. If the write succeeds, atomically rename `.tmp` → target path
3. Before rename, optionally copy the existing file to `<filename>.bak` (one
   backup only; no rotation needed for a local design tool)
4. If the `.tmp` write fails, leave the original file untouched and surface an
   error

This prevents a failed save from leaving the project file in a corrupt state.
The `.bak` file is a convenience for accidental overwrites, not a full history.

### A.6 Dirty State in Studio UI

Studio should track a dirty flag (`session_is_dirty: bool`) that is:
- Set to `True` on any mutation (entity change, rule edit, KA toggle, etc.)
- Set to `False` after a successful save
- Used by the UI to show an unsaved-changes indicator (e.g. `●` in the title
  bar, or a "Unsaved changes" badge near the project name)
- Checked before navigation away or browser close (warn if dirty)

The dirty flag is session-only and is not persisted to the save file.

### A.7 Schema Migration Reporting on Open

When `open_project()` detects `studio_project_schema_version` is older than the
current version:

1. Run the migration chain silently in memory
2. Do NOT auto-save the migrated result — the user must explicitly save to
   commit the migration to disk
3. Surface a non-blocking banner: *"This project was saved with an older Studio
   version. Save to update the file format."*
4. Show the current and previous schema versions in the banner for diagnostics

If migration fails (corrupt field, unknown key):
- Surface a blocking error with the specific field/key that failed
- Do not open the project in a partially-migrated state
- Offer to open in read-only mode for inspection

### A.8 Revision-Anchored References from KS, LE, and Future Tools

KS evidence links, suggestion decisions, manifest revisions, and LE output
reference a Studio project snapshot using a **stable triple** as the unique
anchor, plus optional audit metadata alongside it:

```json
{
  "project_id": "studio-ks-abc123",
  "project_revision": 7,
  "saved_at": "2026-04-25T14:32:00Z",
  "_audit": {
    "modified_by": "jsmith"
  }
}
```

**The stable anchor is the triple: `project_id + project_revision + saved_at`.**
This triple uniquely identifies a project file snapshot without requiring a
content hash and without depending on the reliability of the user identity hint.

`modified_by` is carried as **optional audit metadata** beside the anchor —
useful for display and filtering but not part of the unique identity. Because
`modified_by` is a best-effort local hint that may be `None`, mutable (OS
username changes), or later replaced by an SSO principal, it must not be
treated as part of the snapshot's stable identity.

The triple allows:
- KS to record which revision of the manifest a suggestion was made against
- LE output to be anchored to the project state at time of analysis
- Evidence trail export to carry a traceable snapshot reference

`modified_by` alongside the triple additionally allows:
- Audit display: "revision 7 was saved by jsmith"
- Future audit queries: "show all revisions saved by user X" (best-effort,
  not authoritative)

A content hash is not required in Phase S or KS-B0/B1. When SSO lands,
`modified_by` in the audit field carries the stable principal instead of the
OS username hint — no anchor schema change needed.

### A.9 Implementation Sequencing for This Addendum

| PR | Scope | Dependency |
|---|---|---|
| **S1** (existing) | `ProjectCapabilities` model + `knowledge_assist_enabled: bool = False` + migration guard (`setdefault("capabilities", …)`). No new timestamp or user fields. No `save_project()` wiring beyond what capabilities migration requires. | This design approved |
| **S-save-1** (new hardening PR) | Add `project_revision`, `created_at`, `updated_at`, `saved_at`, `created_by`, `modified_by` to `StudioProject` (all `Optional`/defaulted). Add `is_brand_new: bool = False` to `ProjectSession`. Add `_current_user_hint()`. Wire full `save_project()` logic: `is_brand_new`/`save_as` branches, `created_by`/`modified_by` population, `project_revision` increment, `saved_at` write. Backup-before-overwrite (`tmp` + atomic rename + `.bak`). Dirty-flag tracking. | S1 merged |
| **S-save-2** (new hardening PR) | Schema migration banner on open. Read-only mode for corrupt saves. Save As UI flow (dialog + file picker wired to `save_project(save_as=True)`). | S-save-1 merged |
| **KS-B1 Studio** | `AssistService` extension references `project_id` + `project_revision` in suggestion decisions submitted to KS. | S1 + S-save-1 merged |

The hardening PRs (S-save-1, S-save-2) are separate from the Knowledge Assist
toggle work and can be scheduled independently. They must complete before KS-B1
Studio work begins, because KS suggestion decisions need a stable revision
anchor.

---

*EdgeForge Suite · Studio UX v3 Assistive Features Design · v1.8 · April 2026*
