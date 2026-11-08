# Evidence Trail Design

> **Status:** Evidence Trail v1.1 implemented in the May 2026 suite baseline.
> Exported generated-artifact evidence covers `field`, `validation`, `rule`,
> `cross_entity_rule`, `mapping`, and `transform` accepted/edited decisions
> when evidence exists. Rejected suggestions are excluded. Advisory scopes
> (`conflict_resolution`, `portfolio_reuse`) are excluded from generated-manifest
> evidence by design.
>
> Design gate B3 for provenance-aware Studio review and export. This document
> defines how accepted suggestions retain citation-backed evidence from Studio
> authoring through manifest export and future evolution.
>
> Related design gates:
> - [Studio Archetype Step Registry](./studio-archetype-step-registry.md)
> - [Studio KS Orchestration Design](./studio-ks-orchestration-design.md)
> - [Project Workspace / Decision Ledger Design](./project-workspace-decision-ledger-design.md)

## Purpose

Knowledge Server suggestions carry citations back to source document chunks.
Once a user accepts or edits a suggestion into the manifest authoring flow,
that provenance must survive beyond the live panel interaction.

The exported manifest package should remain a clean deterministic Engine input,
but Studio still needs a durable answer to questions like:

- why does this field exist?
- which BRD paragraph justified this rule?
- which accepted suggestion introduced this mapping?

This document defines the evidence sidecar and the conventions Studio should use
to generate and consume it.

## Problem Statement

The manifest package consists of Engine-facing YAML inputs such as
`app-definition.yaml`, mapping YAMLs, and rule YAMLs. Those files do not carry
evidence metadata, and they should not. The Engine contract must remain
deterministic and free of authoring-only provenance fields.

Without a sidecar:

- provenance disappears after suggestion acceptance
- there is no durable answer to "why does this field exist?" months later
- Step 7 manifest diff cannot show evidence-backed provenance classes
- future evolution work has no stable bridge from accepted manifest fields back
  to the source documents that justified them

## Evidence Sidecar File

The evidence artifact should be:

- file name: `evidence-trail.json`
- location: exported alongside `app-definition.yaml` in the manifest package
- ignored by Engine
- consumed by Studio, future evolution tooling, and compliance exports

### Schema

```json
{
  "schema_version": "1.0",
  "project_id": "...",
  "manifest_revision_id": "...",
  "exported_at": "ISO-8601 timestamp",
  "evidence_links": [
    {
      "manifest_path": "entities.Account.fields.amountMinorUnits",
      "provenance": "ai-accepted",
      "suggestion_id": "s-abc123",
      "confidence": 0.87,
      "citations": [
        {
          "document_id": "doc-xyz",
          "document_name": "Payment BRD v3.2.pdf",
          "chunk_id": "c-abc",
          "content_hash": "sha256:...",
          "parser_version": "1.0",
          "section": "Section 4.1 Amount Handling",
          "snippet": "All monetary amounts must be stored in minor currency units..."
        }
      ]
    }
  ],
  "provenance_summary": {
    "human_authored": 14,
    "ai_accepted": 8,
    "ai_edited": 3,
    "no_evidence": 5
  }
}
```

### Provenance values

Each evidence link should use one of these provenance values:

- `human-authored`
  - user entered the value directly without accepting a suggestion
- `ai-accepted`
  - user accepted a Knowledge Server suggestion as-is
- `ai-edited`
  - user accepted a Knowledge Server suggestion after editing it
- `portfolio-pattern`
  - value came from a portfolio search result or prior approved pattern
- `le-extraction`
  - value came from a LegacyExtractor-derived artifact

These values let review and audit tooling distinguish between manually authored
content and AI-assisted or reuse-assisted content.

## Manifest Path Conventions

Evidence links rely on stable, parseable `manifest_path` values. Paths should
use dot notation into the manifest authoring structure.

### Examples

- `entities.Account.fields.amountMinorUnits`
- `entities.Account.operations.createAccount`
- `data_handoffs.account-staging-table.fields.acct_bal`
- `rules.Account.allowed-values.currency`
- `upstream_interfaces.crm-api.operations.getAccount.mappings.accountId`

### Section conventions

The path conventions should remain stable across exports:

- entity fields:
  - `entities.<EntityName>.fields.<fieldName>`
- entity operations:
  - `entities.<EntityName>.operations.<operationName>`
- upstream interface mappings:
  - `upstream_interfaces.<interfaceName>.operations.<operationName>.mappings.<fieldName>`
- downstream interface mappings:
  - `downstream_interfaces.<interfaceName>.operations.<operationName>.mappings.<fieldName>`
- data handoffs:
  - `data_handoffs.<handoffName>.fields.<fieldName>`
- rules:
  - `rules.<scope>.<ruleType>.<ruleName>`
- route configuration:
  - `routes.<routeName>.<propertyName>`
- transform mappings:
  - `transforms.<transformName>.mappings.<fieldName>`

Studio should generate these paths consistently so evidence links are portable
between in-session review, exported sidecars, and future evolution workflows.

## How Studio Generates the Sidecar

Studio should track lightweight evidence links in the active `ProjectSession`
during authoring.

### Authoring-time capture

When a suggestion is accepted:

- Studio records the `manifest_path`
- Studio records the `suggestion_id`
- Studio records whether the acceptance was as-is or edited

When the user manually authors a field without accepting a suggestion:

- no suggestion-backed evidence link is created
- that field is considered `human-authored` for provenance display purposes

The in-session capture model depends on review-state ownership described in
[Studio KS Orchestration Design](./studio-ks-orchestration-design.md).

### Export-time expansion

At Step 8 export:

1. Studio gathers the accepted and edited suggestion IDs from session/workspace
   state
2. Studio queries Knowledge Server for the citation details associated with
   those suggestions
3. Studio writes the expanded `evidence-trail.json` sidecar alongside the
   manifest package

The full citation payload belongs in the sidecar export. The lightweight link
belongs in the live Studio workspace state.

## How Step 7 Uses the Evidence Model

Step 7 should read current in-session evidence state, not the exported sidecar.

The review view should render provenance annotations such as:

- human-authored
- ai-accepted
- ai-edited

Fields that currently have no evidence trail should surface a visible
`no evidence` indicator.

The intent is to let users see provenance while they are still reviewing and
editing the manifest preview, rather than only after export.

Pending suggestion summaries and unresolved conflict summaries should also come
from current session/workspace state rather than from the exported sidecar.

## Compliance and Audit Use

The sidecar enables a reviewer or auditor to trace any manifest field back to
its source evidence.

Together, the sidecar and Knowledge Server citation storage provide the chain:

- manifest field
- accepted or edited suggestion decision
- citation record
- source document chunk

That traceability matters in regulated environments, especially programs where design decisions must be justified after the original delivery
team has moved on.

## Relationship to Other Design Gates

- [Studio KS Orchestration Design](./studio-ks-orchestration-design.md)
  defines how suggestion decisions are fetched, reviewed, and persisted.
- [Project Workspace / Decision Ledger Design](./project-workspace-decision-ledger-design.md)
  defines the lightweight `evidence_links` structure that Studio should keep
  live in the save file and workspace state.
- [Studio Archetype Step Registry](./studio-archetype-step-registry.md)
  defines where provenance-aware panels attach across archetypes.

## What This Document Is NOT

- Not a replacement for Engine validation; Engine reads the manifest, not the
  sidecar
- Not a diff format; the sidecar records provenance, not change history
- Not a Git blame equivalent
