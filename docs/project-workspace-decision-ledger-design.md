# Project Workspace / Decision Ledger Design

> Design gate B4 for durable Studio save/open evolution, review history, and
> future post-generation enhancement flows. This document defines the
> workspace-level persistence model that ties together Studio state, Knowledge
> Server linkage, evidence links, and manifest revision lineage.
>
> Related design gates:
> - [Studio Archetype Step Registry](./studio-archetype-step-registry.md)
> - [Studio KS Orchestration Design](./studio-ks-orchestration-design.md)
> - [Evidence Trail Design](./evidence-trail-design.md)

## Purpose

Studio save/open S1A already preserves local authoring state. Knowledge Server
will preserve suggestions and citations. What still needs an explicit design is
the workspace that spans both systems over time.

This workspace model is the durable bridge across:

- Studio authoring state
- Knowledge Server document and suggestion linkage
- evidence links
- conflict resolution history
- manifest revision lineage
- future post-generation evolution flows

## Problem Statement

Today the persistence model is incomplete:

- Studio save/open is scoped to authoring state only
- Knowledge Server stores suggestions and citations but does not know Studio's
  manifest lifecycle
- there is no design for how save/open, review history, and reconnect behavior
  survive across sessions
- there is no durable answer to questions such as:
  - why does this rule exist?
  - what did the user reject?
  - what changed between one export and the next?

Without a workspace model, save/open, suggestion review, and future enhancement
flows will evolve independently toward incompatible persistence shapes.

## Workspace Identity

The workspace is the durable artifact that ties together all project state.

Recommended identity fields:

- `project_id`
  - globally unique ID for the modernization project
  - owned by Studio
- `project_name`
  - human-readable name derived from `app_name`
- `bounded_context`
  - copied from the manifest authoring context
- `ks_project_id`
  - the Knowledge Server namespace for this project
- `studio_project_schema_version`
  - version marker for the Studio project file format
- `created_at`
  - ISO-8601 timestamp
- `last_saved_at`
  - ISO-8601 timestamp

### Recommendation

Use the same value for `project_id` and `ks_project_id` unless there is a
specific reason to diverge. Matching values remove an avoidable mapping lookup
and make reconnect behavior unambiguous.

## Manifest Revision Lineage

Each time the user exports a manifest package, Studio should append a lightweight
revision record:

```yaml
manifest_revisions:
  - revision_id: rev-001
    exported_at: "..."
    manifest_hash: "sha256:..."
    archetype: crud
    target_profile: springboot-standard-enterprise
    export_path: /path/to/exported/package
```

This is intentionally lightweight and append-only. It is not Git history.

The purpose is to preserve:

- when the project was exported
- which archetype and target profile were active
- which manifest hash was produced
- where the package was written

This is enough to support reopen and future evolution without introducing a
full revision-control system.

## Review History

The workspace should store the complete suggestion review history:

```yaml
review_history:
  - suggestion_id: s-abc
    type: rule
    status: accepted
    manifest_path: rules.Account.allowed-values.currency
    reviewed_at: "..."
    edited_payload: null
```

This history should preserve:

- accepted suggestions
- edited suggestions
- rejected suggestions

Rejected decisions matter because users will later ask why a suggestion was
dismissed, especially after updated source documents are ingested.

This history becomes the durable source of truth for provenance classification
used by the evidence sidecar described in
[Evidence Trail Design](./evidence-trail-design.md).

## Evidence Links

The workspace should store a lightweight evidence link structure for live
session and reopen use:

```yaml
evidence_links:
  - manifest_path: entities.Account.fields.amountMinorUnits
    suggestion_id: s-abc123
    provenance: ai-accepted
```

The workspace stores only the lightweight link. Full citation details remain in
Knowledge Server and are expanded into `evidence-trail.json` at export time.

That split keeps the Studio save file compact while preserving enough data to
annotate review surfaces and reconnect provenance on reopen.

## Conflict Resolutions

Conflict resolutions should be preserved alongside review history:

```yaml
conflict_resolutions:
  - conflict_id: c-123
    resolution: use-source-a
    rationale: BRD v3.2 is more recent than data-dict-2024.xlsx
    resolved_at: "..."
```

This lets the workspace retain the user's reasoning, not just the final chosen
value. That matters when the user later revisits the project with new source
documents or a new reviewer.

## Relationship to the Studio Save File

The workspace is embedded in the Studio save file rather than stored as a
separate artifact.

Recommended shape:

```json
{
  "studio_project_schema_version": "1.1",
  "project_id": "...",
  "ks_project_id": "...",
  "ks_active": true,
  "suggestion_review_state": {
    "accepted_ids": [],
    "rejected_ids": [],
    "edited_ids": []
  },
  "evidence_links": [],
  "manifest_revisions": [],
  "conflict_resolutions": [],
  "review_history": []
}
```

Existing S1A fields remain unchanged. These fields are additive.

### Migration rule

Studio must migrate S1A save files that lack these new fields.

If `ks_project_id` is absent:

- `ks_active` should default to `false`
- `suggestion_review_state` should initialize empty
- `evidence_links` should initialize empty
- `manifest_revisions` should initialize empty
- `conflict_resolutions` should initialize empty
- `review_history` should initialize empty

This keeps older local project files loadable while allowing the workspace
model to grow forward.

## Post-Generation Evolution Mode

This workspace design is also the forward reference for future enhancement
flows after generation.

Expected flow:

1. user reopens a Studio project weeks after generation
2. Studio reconnects to Knowledge Server using `ks_project_id`
3. user ingests updated BRD or policy documents
4. Knowledge Server compares the new requirements against the prior indexed set
5. new conflicts and suggestions are surfaced in the same accept/edit/reject
   workflow
6. the updated manifest is exported with a new `revision_id`
7. new evidence links and review history entries are appended

This does not require a separate Studio UX. It should reuse the same wizard
steps and panels, with the workspace supplying the continuity across time.

## Relationship to Other Design Gates

- [Studio Archetype Step Registry](./studio-archetype-step-registry.md)
  determines which step sequence is active when the project is reopened.
- [Studio KS Orchestration Design](./studio-ks-orchestration-design.md)
  defines reconnect behavior, in-session ownership, and decision write-back.
- [Evidence Trail Design](./evidence-trail-design.md) defines how lightweight
  workspace evidence links expand into the exported sidecar.

## What This Design Is NOT

- Not a database or server-backed catalog; S1A remains file-based
- Not a Git replacement; there are no branch or merge semantics
- Not a full audit log with immutability guarantees
- Not a multi-user shared workspace; this remains a single-user local model
