# Studio Save/Open Project Design

> Design-first alignment document for future EdgeForge Studio save/open project support.
> This document is an Engine/Studio coordination anchor only. It does not start implementation by itself.

## Summary Recommendation

Studio should add a native save/open project capability before the wizard grows much further with manifest-v1.1 authoring fields.

The recommended first implementation is intentionally smaller than a full enterprise project-management system:

- **S1A: Studio-native save/open project**
- **S1B: optional server-backed project catalog and locking**
- **S2: SSO**
- **S3: LOB-scoped access**
- **S4: RBAC**

The design should reserve auth-ready metadata in S1A where it is cheap and harmless, but SSO, LOB filtering, and role enforcement should stay out of S1A.

## Problem

Studio authoring is a multi-step workflow. Users need to resume work later without re-entering all wizard inputs.

Current Studio already has a temporary single-session persistence file, so the problem is not simply "browser closed means all progress is always lost." The gap is that Studio does not yet have a first-class, named, portable project save/open workflow.

The product goal is:

- save in-progress Studio authoring work
- reopen it later
- modify only the required sections
- export a fresh Engine manifest package

## Current Studio Wizard Shape

Current Studio is an 8-step wizard:

| Step | Current Studio meaning |
|---|---|
| 1 | Project setup: app name, bounded context, archetype, target profile, output path, Engine repo path |
| 2 | Upstream OpenAPI/sample ingest and classification |
| 3 | CRUD entity/operation selection, or passthrough-router setup |
| 4 | Data handoffs |
| 5 | Downstream interfaces |
| 6 | Rules and legacy notes |
| 7 | Review and manifest preview |
| 8 | Export, validate, generate, Build & Run |

The save/open design should be based on Studio's current `ProjectSession` authoring state rather than an alternate step model.

Important current Studio state includes:

- `app_name`
- `bounded_context`
- `app_archetype`
- `target_profile`
- `output_path`
- `appbuilder_repo_path`
- `raw_spec_content`
- `raw_spec_url`
- `raw_spec_filename`
- `classified_entities`
- `classified_operations`
- `selected_entity_names`
- `selected_operation_names`
- `upstream_interfaces`
- `downstream_interfaces`
- `data_handoffs`
- `entity_rules`
- `legacy_notes`
- `legacy_slug`
- `passthrough_flow`

Step 8 runtime/build state should be treated separately as transient state.

### Spec Content Persistence

S1A should preserve both spec source metadata and the actual spec content Studio ingested.

For URL-backed specs, Studio currently stores:

- `raw_spec_url`
- `raw_spec_content`

For uploaded specs, Studio currently stores:

- `raw_spec_filename`
- `raw_spec_content`

Recommended S1A behavior:

- save `raw_spec_content` in the Studio project snapshot when Studio has already ingested it
- also save `raw_spec_url` or `raw_spec_filename` as source metadata
- restore from the saved content on open so the project remains reproducible if the remote URL changes or is unavailable
- offer a later explicit "refresh from source URL" action if users want to re-ingest upstream changes

This makes save/open reliable while preserving source traceability.

## Product Boundary

Studio project save/open and Engine manifest export are different artifacts:

| Artifact | Owner | Purpose | Recommended S1A shape |
|---|---|---|---|
| Studio project | Studio | Editable authoring workspace | Studio-native project JSON |
| Manifest package | Engine contract, produced by Studio | Deterministic generation input | `app-definition.yaml` plus referenced files |
| Generated app | Engine output | Runtime/build artifact | Generated source tree |

The Studio project is the editable source for resume. The exported manifest package remains the Engine input contract.

Package re-import from `app-definition.yaml` can be considered later as a separate best-effort feature. It should not block S1A.

## Phase Plan

### S1A: Studio-Native Save/Open Project

S1A should focus on the narrow user value:

- save current Studio authoring state to a Studio-native project file
- open that project later
- restore the wizard through Steps 1-6
- keep Step 7/8 recomputable
- clear or recompute transient Build & Run state on load

Suggested file name/format:

- `edgeforge-studio-project.json`

S1A may include auth-ready metadata fields, but should not enforce auth or access control.

Those fields should be treated as reserved/nullable compatibility fields. If Studio is running in a local unauthenticated mode, it may leave them empty or use local placeholders without implying any SSO provider, organization model, or LOB authorization policy.

Recommended S1A project envelope:

```yaml
studio_project_schema_version: "1.0"
project_id: string
name: string
description: string?
created_at: timestamp?
updated_at: timestamp?

# Auth-ready, not enforced in S1A.
org_id: string?
lob_id: string?
owner_user_id: string?
last_edited_by: string?

snapshot:
  # Studio-owned authoring state, shaped around current ProjectSession.
  app_name: string
  bounded_context: string
  app_archetype: string
  target_profile: string
  output_path: string?
  appbuilder_repo_path: string?
  raw_spec_content: string?
  raw_spec_url: string?
  raw_spec_filename: string?
  classified_entities: []
  classified_operations: []
  selected_entity_names: []
  selected_operation_names: []
  upstream_interfaces: []
  downstream_interfaces: []
  data_handoffs: []
  entity_rules: []
  legacy_notes: string?
  legacy_slug: string?
  passthrough_flow: {}

last_known:
  last_export_path: string?
  last_exported_at: timestamp?

step_progress:
  current_step: integer?
  completed_steps: integer[]
  warnings: []
```

This is intentionally Studio-owned. Engine should not consume this file.

### S1B: Optional Server-Backed Project Catalog

The richer project catalog can follow once S1A proves useful:

- project list UI
- create/list/open/delete APIs
- database-backed project rows
- optional soft delete/archive
- optional pessimistic lock/heartbeat

This is where the stronger server-side model from earlier design discussion fits naturally:

- `Project` row
- `snapshot` JSONB
- `lock_holder_user_id`
- `lock_expires_at`
- lock heartbeat
- conflict/read-only UI

S1B can reuse the S1A project envelope and store the `snapshot` in PostgreSQL JSONB if the product direction requires server-backed project management.

Recommended timing:

- do not start S1B immediately after S1A by default
- revisit after the Engine MCP phase clarifies the service boundary and deployment model
- prioritize S1B only when Studio needs multi-project catalog behavior, multi-user access, shared team workflows, or enterprise deployment support

Until those needs are concrete, S1A's file-based save/open path is the preferred scope.

### S2: SSO

SSO should remain a later phase.

Reason:

- the target enterprise SSO mechanism is not settled
- WorkOS or any other provider may have licensing/cost implications
- auth effort should not block the basic save/open product value

When S2 arrives, it can populate and enforce already-reserved fields like:

- `owner_user_id`
- `org_id`
- `last_edited_by`

### S3: LOB-Scoped Access

LOB-specific access should remain later than S1A.

When S3 arrives, it can use fields like:

- `lob_id`
- `org_id`

S1A can preserve these fields without enforcing them.

### S4: RBAC

RBAC should remain later than S1A and S1B.

When S4 arrives, it can add permission checks on top of the project catalog and user/LOB membership model. It should not be required for the first save/open feature.

## Save vs. Do Not Save

### Save As Durable Authoring State

- Project setup fields
- Raw spec source metadata and content where Studio already has it
- Classified entities and operations
- Selected entities and operations
- Upstream interfaces and mappings
- Data handoffs
- Downstream interfaces and mappings
- Rules and legacy notes
- Passthrough-router flow state
- Step progress and non-blocking warnings where useful

### Do Not Save As Durable Runtime State

- running process IDs
- local port bindings
- health URL/status
- build logs
- run logs
- generated app runtime status
- active subprocess state

### Optional Last-Known Convenience State

- last export path
- last export timestamp
- last generated app path

These can help UX, but must not be treated as authoritative after reopen.

## Engine Impact

Expected Engine impact for S1A: **none**.

Engine should continue to own:

- manifest schema
- manifest loading/validation
- metadata translation
- generation behavior

Studio should own:

- Studio project save/open format
- snapshot schema
- project file read/write
- wizard resume behavior

The Engine should see only the exported manifest package.

## Manifest Compatibility

When Studio exports a saved project, it should continue to produce the normal Engine manifest package.

For the current baseline:

- `schema_version: "1.0"` should be used unless Studio has manifest-v1.1 authoring fields ready
- optional manifest-v1.1 fields such as `identity_overrides` and `id_generation_overrides` should not be invented by Studio before the corresponding UI/authoring decisions exist
- when Studio later adds entity type, identity, or ID strategy controls, export can move to the appropriate additive manifest-v1.1 fields

The Studio project file's `studio_project_schema_version` is separate from the Engine manifest `schema_version`.

## Authentication-Ready Fields

It is reasonable to reserve auth-aware fields in S1A:

- `org_id`
- `lob_id`
- `owner_user_id`
- `last_edited_by`

Guardrails:

- fields may be nullable in S1A
- local placeholders are acceptable in S1A when no authenticated user context exists
- no SSO enforcement in S1A
- no LOB filtering in S1A
- no RBAC in S1A
- no provider-specific assumptions in S1A

This lets future S2/S3/S4 work attach to the project record without forcing premature auth decisions.

## API Shape Recommendation

For S1A, API needs can stay minimal and Studio-owned. If implemented as local file save/open, Studio may only need routes/actions like:

```text
POST /projects/save
POST /projects/open
POST /projects/save-as
```

For S1B, the richer API shape can be introduced:

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/:id
PUT    /api/projects/:id
DELETE /api/projects/:id
POST   /api/projects/:id/acquire-lock
POST   /api/projects/:id/release-lock
POST   /api/projects/:id/heartbeat
```

The richer API should not be required for the first Studio-native save/open implementation.

## Storage Recommendation

S1A should choose the smallest durable storage approach that satisfies local save/open:

- Studio-native JSON project file is preferred for the first implementation
- local temp-session persistence should not be treated as the user-facing project artifact

PostgreSQL + JSONB is a good fit for S1B if/when Studio needs a server-backed project catalog, multi-user access, locking, or enterprise deployment.

SQLite, S3, DynamoDB, and provider-specific auth stores should not be necessary for S1A.

## Testing Strategy

S1A tests should focus on lossless Studio resume behavior:

| Scenario | How to Test |
|---|---|
| Save/open after Step 1 | Project setup fields restore exactly |
| Save/open after Step 2 | raw spec metadata/content and classification restore |
| Save/open after Step 3 CRUD | selected entities/operations and upstream interfaces restore |
| Save/open after Step 3 passthrough | passthrough flow restores |
| Save/open after Step 4/5/6 | handoffs, downstreams, rules, and legacy notes restore |
| Export after reopen | regenerated `app-definition.yaml` matches expected manifest |
| Step 8 transient state | build/run PID, ports, logs, and runtime status are cleared or recomputed |

S1B tests can add:

- project list CRUD
- locking conflict
- lock expiry
- heartbeat renewal
- archived project behavior

## Open Questions For Implementation

- Should large specs require size limits or external file storage instead of embedding directly in the project snapshot?
- Should the first implementation expose a file picker or save to a configured workspace path?
- Should opening a project restore the last active step or always start at Step 1 with all state loaded?
- Should autosave be part of S1A or a follow-up after explicit save/open?
- Should S1B live in Studio only, or should any project catalog concerns move to a future service boundary?

## Codex Studio Review Position

High-level design direction: aligned.

Recommended adjustment:

- keep auth-ready fields in the project format
- move SSO, LOB enforcement, RBAC, server-backed locking, and PostgreSQL JSONB project catalog out of the first save/open MVP
- align the snapshot around current Studio `ProjectSession` rather than a separate invented Step 1-6 model
- keep Engine ownership limited to exported manifest contracts

This keeps the feature useful now while leaving a clean path to enterprise auth and access control later.
