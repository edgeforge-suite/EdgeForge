# ADR-0001 — Canonical internal model over API-to-entity mapping

**Status:** Accepted (records an existing, implemented decision).

## Context

Many enterprise replacement efforts fail because teams **redesign the external
contracts** instead of preserving them, or they bind business logic directly to
raw external API/file shapes (API-to-entity generation). Either path couples the
new system's internals to volatile external shapes, so contract churn ripples into
core logic and modernization stalls.

This is called out as the suite's core problem and a non-negotiable requirement in
[`appbuilder-context.md`](../appbuilder-context.md) ("Core Problem",
"Non-Negotiable Requirements") and as a core thesis in
[`suite-architecture.md`](../suite-architecture.md) ("Canonical internal model").

## Decision

External contracts are mapped into a **stable, normalized canonical internal
domain model**. Business logic binds to the canonical model — never to raw
external shapes — and the Engine **never** does API-to-entity generation. The
mapping between external and canonical models is **explicit and reviewed**, and
external adapters are kept separate from core logic.

## Consequences

- External adapters are isolated from core logic; the canonical model absorbs
  upstream/downstream contract changes without rewriting business logic.
- Mappings are first-class, explicit artifacts (and reviewable), not implicit.
- A modest upfront modeling cost is accepted in exchange for resilience to
  external-contract churn and clean separation of concerns.
- It rules out "shape-in, shape-out" generation — the platform is contract-first,
  not a raw API scaffolder.
