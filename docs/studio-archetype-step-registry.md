# Studio Archetype Step Registry

> Design gate B1 for Studio Kafka authoring and Studio Knowledge Server
> integration. This document defines the structural model Studio should adopt
> before adding Kafka-specific authoring or cross-cutting suggestion panels.
>
> Related design gates:
> - [Studio KS Orchestration Design](./studio-ks-orchestration-design.md)
> - [Evidence Trail Design](./evidence-trail-design.md)
> - [Project Workspace / Decision Ledger Design](./project-workspace-decision-ledger-design.md)

## Purpose

Studio's current 8-step wizard grew around CRUD authoring. Passthrough-router
support already introduced a second shape of authoring flow, and Kafka will
introduce a third. Knowledge Server suggestion panels, evidence views, and
future chat/conflict surfaces must work consistently across all archetypes.

This document defines an archetype step registry that separates shared wizard
steps from archetype-specific steps and lets cross-cutting panels attach once,
instead of being duplicated per archetype.

## Problem Statement

The current wizard structure is too CRUD-centric to cleanly absorb a third
archetype plus future Knowledge Server panels without duplication.

Today the pressure points are already visible:

- CRUD has entity, operation, handoff, and downstream interface steps
- passthrough-router compresses route and transform authoring into a different
  middle sequence
- Kafka will require topic/schema ingest, async route modeling, and transform
  mapping that do not fit the CRUD middle steps

Without a formal registry, Studio is pushed toward three separate mini-wizards:

- a CRUD wizard
- a passthrough wizard
- a Kafka wizard

That would create duplicated navigation, duplicated route wiring, duplicated
review/export entry points, and duplicated attachment points for Knowledge
Server suggestion panels. Once that happens, every new cross-cutting feature
would have to be re-threaded into three flows separately.

## Design Goal

Studio should have one wizard shell with:

- a small set of shared steps that all archetypes inherit
- a registry of archetype-specific steps inserted into the middle of the flow
- one attachment model for Knowledge Server suggestions, evidence, chat, and
  conflicts driven by step metadata rather than by archetype-specific UI code

## Step Registry Concept

Steps are classified as either shared or archetype-specific.

### Shared steps

These steps exist for every archetype:

1. project setup plus document ingest kickoff
2. rules, mappings, and conflict resolution
3. review, manifest diff, and approval
4. export, validate, generate, build, and run

The shared steps are the long-lived Studio surfaces where cross-cutting
capabilities should attach.

### Archetype-specific steps

Each archetype contributes only the domain-specific authoring steps it needs.

#### CRUD

- upstream OpenAPI ingest
- entity and operation model authoring
- data handoff / staging authoring
- downstream interface authoring

#### Passthrough-router

- upstream contract ingest
- route and transform model authoring

#### Kafka-integration

- topic and message-schema ingest
- async route model authoring, including route name, pattern, topic pairs,
  correlation config, and reply paths
- transform mapping authoring

## Conceptual Registration Shape

The registry is a conceptual design, not a finalized API.

```python
STEP_REGISTRY = {
    "crud": [
        SharedStep("project-setup"),
        CrudStep("upstream-ingest"),
        CrudStep("entity-model"),
        CrudStep("data-handoffs"),
        CrudStep("downstream-interfaces"),
        SharedStep("rules-mappings"),
        SharedStep("review"),
        SharedStep("export-build-run"),
    ],
    "kafka-integration": [
        SharedStep("project-setup"),
        KafkaStep("topic-schema-ingest"),
        KafkaStep("route-model"),
        KafkaStep("transform-mappings"),
        SharedStep("rules-mappings"),
        SharedStep("review"),
        SharedStep("export-build-run"),
    ],
    "passthrough-router": [
        SharedStep("project-setup"),
        PassthroughStep("upstream-ingest"),
        PassthroughStep("route-transform"),
        SharedStep("rules-mappings"),
        SharedStep("review"),
        SharedStep("export-build-run"),
    ],
}
```

The important idea is not the exact syntax. The important idea is that the
active archetype selects its own ordered step list from a registry, while the
shared shell remains the same.

## Step Registration Fields

Each step registration should define at least:

- `step_id`
  - Stable identifier used for navigation, save/open restore, and panel
    attachment.
- `archetype`
  - `shared` or a specific archetype such as `crud`,
    `passthrough-router`, or `kafka-integration`.
- `template`
  - The Jinja2 template responsible for rendering the step.
- `route`
  - The FastAPI route that handles GET and POST behavior for the step.
- `suggestion_scope`
  - The Knowledge Server suggestion category relevant to the step.
  - Expected values include `entity-fields`, `route-config`,
    `transform-mappings`, `rules`, and `none`.
- `nav_position`
  - The rendered position in the wizard navigation bar for the active
    archetype.

Additional optional metadata may be added later, but these are the minimum
fields needed to make routing, navigation, save/open restore, and cross-cutting
panel attachment deterministic.

## Cross-Cutting Panel Attachment

The step registry is the enabling layer for Knowledge Server panels.

The intended model is:

- Knowledge Server suggestion panel attaches according to `suggestion_scope`
- Evidence panel is available on all steps where `suggestion_scope != "none"`
- Chat panel is available on all steps where `suggestion_scope != "none"`
- Conflicts panel is available on all steps where `suggestion_scope != "none"`

This means Studio writes the Knowledge Server panel integration once and lets
step metadata decide when and how it appears. The logic is driven by scope, not
by special-case branching for CRUD versus Kafka versus passthrough.

The actual suggestion fetch and review-state behavior is defined separately in
[Studio KS Orchestration Design](./studio-ks-orchestration-design.md). The
step registry simply provides the stable attachment points.

## URL and Navigation Conventions

### Shared-step URLs

Shared steps should use the same URL regardless of archetype. For example:

- `/project`
- `/rules`
- `/review`
- `/export`

This keeps shared routes stable and lets review/export/build behavior remain
independent from archetype-specific authoring.

### Archetype-specific URLs

Archetype-specific steps should use archetype-prefixed URLs. Examples:

- `/crud/upstream-ingest`
- `/crud/entity-model`
- `/passthrough/upstream-ingest`
- `/passthrough/route-transform`
- `/kafka/topic-ingest`
- `/kafka/route-model`
- `/kafka/transform-mappings`

This makes route ownership explicit and prevents collisions between steps that
mean different things for different archetypes.

### Navigation rendering

The wizard navigation bar should render the ordered steps from the registry for
the active archetype. The nav should not infer step order from hard-coded
integers or CRUD-specific assumptions. On reopen, Studio should restore the
correct navigation model by reading the project's stored archetype.

## What This Enables

This design unblocks three important outcomes:

1. Kafka Studio authoring can be added by registering Kafka-specific steps
   while inheriting shared review/export/build behavior unchanged.
2. Knowledge Server panel integration can be written once and attached
   consistently by `suggestion_scope`.
3. Future archetypes can register their own step sequences without modifying
   the shared wizard shell.

In practical sequence terms:

- the first implementation PR should refactor CRUD and passthrough-router into
  the new registry without adding new user-facing features
- a later Kafka Studio PR can then add only Kafka-specific step registrations
- a later Knowledge Server Studio PR can attach suggestion/evidence/chat panels
  once, reusing the registry metadata

## Implementation Guidance

This is a refactor-first design, not a feature pile-on.

The first Studio PR implementing this document should:

- introduce the registry structure
- register CRUD through it
- register passthrough-router through it
- preserve current review and export behavior
- keep existing user-facing behavior as stable as possible

Kafka-specific steps should not be added until the registry exists and shared
step behavior is already proven with the current archetypes.

The Studio save/open project format should continue to store the selected
archetype so the correct registry can be loaded when a project is reopened. The
workspace/evolution details for that are described further in
[Project Workspace / Decision Ledger Design](./project-workspace-decision-ledger-design.md).

## Relationship to Other Design Gates

- This registry defines where cross-cutting panels can attach.
- [Studio KS Orchestration Design](./studio-ks-orchestration-design.md)
  defines how those panels fetch and persist suggestion state.
- [Evidence Trail Design](./evidence-trail-design.md) defines the provenance
  model those panels should expose in review flows.
- [Project Workspace / Decision Ledger Design](./project-workspace-decision-ledger-design.md)
  defines how archetype, review state, evidence links, and manifest lineage
  persist across save/open and future evolution.

## What This Document Is NOT

- Not a full implementation spec or working code
- Not a mandate to rewrite the entire wizard in one PR
- Not a UI framework replacement
