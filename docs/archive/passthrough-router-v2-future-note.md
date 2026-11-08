# Passthrough-Router v2 Future Note

> Saved 2026-04-09 for future reference. This is not part of the active Phase 3 hardening scope.

## Current Baseline

The current `passthrough-router` archetype is a proven Phase 2 / v1 lane, but it is intentionally narrow:

- stateless Spring Boot router generation
- REST JSON in
- REST JSON out
- synchronous request/response
- flat deterministic field transforms
- simple field-based routing
- no JPA / Flyway / repository generation

This lane is suitable for a **single inbound request shape routed across downstream REST targets**.

## Current Practical Limits

The current Engine can ingest multiple upstream and downstream interfaces in translation, but the emitter still collapses the generated app into one effective flow:

- one shared `InboundRequestDto`
- one shared `InboundResponseDto`
- one shared `OutboundRequestDto`
- one shared `OutboundResponseDto`
- one shared `TransformService`
- one shared `RoutingService`

Key implementation constraints today:

- `InboundRequestDto` / `InboundResponseDto` are generated from the **first upstream operation**
- `OutboundRequestDto` / `OutboundResponseDto` are generated from the **first downstream operation**
- all downstream clients reuse that single outbound DTO family
- routing is global, not flow-specific
- transforms are global, not target- or operation-specific

Studio support is still narrower than the Engine:

- passthrough generation exists in Engine
- full Studio authoring/export support for passthrough packages is still not complete
- the current checklist still treats passthrough Studio support as an open item

## What Is Not Supported Yet

These are not first-class passthrough-router capabilities today:

- multiple independent upstream API flows in one generated passthrough app
- target-specific outbound DTO families
- per-target or per-operation transform sets
- multiple routing rule sets scoped to different inbound flows
- file-based passthrough flows
- event/message passthrough
- database-backed enrichment
- retry/circuit-breaker policy generation
- long-running orchestration

## Future Requirement Shape: Multi-Flow Router

Example target use case:

- 5 upstream APIs
- deterministic field transformations per flow
- route/send to 5 downstream APIs

This should **not** be forced into the current MVP shape.

The correct future direction is a `passthrough-router v2` expansion that introduces first-class **flow definitions**, for example:

- flow-specific inbound contract
- flow-specific downstream targets
- flow-specific transform mappings
- flow-specific routing rules
- target-specific outbound request/response shapes

## Likely Manifest Direction

This would need an additive future manifest extension, not a mutation of the current v1 passthrough shape.

Likely concepts:

- `flows`
- per-flow inbound operation binding
- per-flow target set
- per-flow transforms
- per-flow routing
- target-specific request/response mapping groups

This should be additive in a `manifest-v1.1` style only.

## Recommended Phase Placement

This is **not** a Phase 3 item.

Recommended placement:

- finish Phase 3 hardening first
- finish currently planned MCP phases or explicitly approve a post-Phase-3 archetype expansion track
- then treat this as a separate Engine-first design/implementation effort:
  - `passthrough-router v2`
  - or `multi-flow passthrough-router`

## Design Constraints To Preserve

Any future passthrough expansion must preserve these architecture rules:

- deterministic generation only
- passthrough-router remains stateless
- CRUD must not be mutated to simulate router/orchestration behavior
- new topology means new archetype lane or an explicitly expanded passthrough lane
- no hidden runtime inference from ambiguous metadata
- Studio support should follow an Engine-first proof

## Short Recommendation

Use the current `passthrough-router` archetype for:

- one inbound contract
- one outbound DTO family
- simple deterministic routing across downstream REST targets

Do **not** use it yet for:

- multi-upstream / multi-downstream integration hub patterns

That pattern should be handled later as a deliberate `passthrough-router v2` design item.
