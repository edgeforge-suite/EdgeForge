> Archived April 2026. Superseded by docs/archive/target-state-features-v1.md.

# Passthrough-Router Mini-Roadmap

> **Planning note.** Drafted 2026-03-26 to map a second generated-app archetype into the EdgeForge roadmap. This complements the existing entity-centric CRUD generator and does not replace it.

## Why This Exists

Today EdgeForge generates a **persistence-first bounded-context application**:

- canonical entities
- JPA repositories
- Flyway migrations
- service/controller CRUD flows
- optional downstream file and staging-table writers

That is the right archetype for DDA, loans, and other stateful enterprise systems.

Some modernization targets are different. They behave more like **adapters / mediators**:

- accept an inbound API request or message
- apply deterministic field transformations
- optionally enrich values from static rules or defaults
- route the transformed payload to one of several downstream systems
- return an adapted response
- do **not** require durable JPA persistence for the core flow

This document defines the smallest useful EdgeForge path for that second archetype.

## Current Truth

The current generator is not yet suited to this pattern as a first-class mode:

- repositories and entity persistence are assumed
- Flyway-backed tables are assumed for canonical entities
- downstream support today is strongest for fixed-width files and staging-table handoffs
- outbound REST routing/orchestration is not yet a generated capability

So this is **not** a Phase 1b tweak. It is a **Phase 2 archetype expansion**.

## Proposed Archetype

Suggested name:

- `passthrough-router`

Suggested manifest-level selector:

```yaml
app_archetype: passthrough-router
```

The existing archetype remains the default:

```yaml
app_archetype: crud
```

## Phase Mapping

### Phase 1b — Finish current entity-centric hardening

Keep the current focus on:

- entity relationships
- query/header parameter support
- closing any remaining smoke-driven gaps

The passthrough/router work should not interrupt those near-term hardening items.

### Phase 2A — Docs + Engine MVP

Add the first deterministic passthrough/router slice to the Engine only.

#### Inputs to add

- inbound REST contract
- one or more downstream REST target contracts
- deterministic transformation mappings
- deterministic routing rules

#### Engine behavior

- skip JPA entity/repository/Flyway generation for this archetype
- generate inbound controller + request/response DTOs
- generate transform service
- generate routing service
- generate outbound REST clients

#### Routing scope for v1

- simple field-based predicates only
- example: `countryCode == "US" -> AppA`, `countryCode == "GB" -> AppB`, else `AppC`

### Phase 2B — Prove one real passthrough app

Generate one real app that:

- receives one inbound JSON request
- transforms/enriches it deterministically
- routes to App-A / App-B / App-C based on a simple rule
- returns a contract-correct downstream-adapted response

This becomes the proof that EdgeForge can generate both:

- stateful bounded-context CRUD apps
- stateless or low-state transform/router apps

### Phase 2C — Studio Support

Once the Engine contract is stable:

- add Studio authoring/export support for `passthrough-router`
- collect downstream targets
- collect transform mappings
- collect routing rules
- export a valid passthrough-router package without manual YAML editing

## Smallest Useful MVP

The first MVP should support only this narrow lane:

- REST in
- REST out
- synchronous request/response
- same-request deterministic transformation
- static/default enrichment only
- simple routing predicates on one field
- no durable canonical persistence required

## Manifest Additions For MVP

Suggested new areas:

- `app_archetype`
- downstream REST targets
- transformation mappings
- routing rules

Illustrative shape:

```yaml
app_name: Country Router
bounded_context: payments
app_archetype: passthrough-router

upstream_interfaces:
  - name: inbound-payments-api
    type: rest-json
    spec: upstream/payments-openapi.yaml

downstream_interfaces:
  - name: app-a-api
    system: APP_A
    type: rest-json
    spec: downstream/app-a-openapi.yaml
  - name: app-b-api
    system: APP_B
    type: rest-json
    spec: downstream/app-b-openapi.yaml
  - name: app-c-api
    system: APP_C
    type: rest-json
    spec: downstream/app-c-openapi.yaml

rules:
  - rules/payment-routing.yaml
  - rules/payment-transforms.yaml
```

## Generated Components For MVP

The Engine should emit something closer to:

- `InboundController`
- `TransformService`
- `RoutingService`
- `AppAClient`
- `AppBClient`
- `AppCClient`
- shared DTOs / mapper helpers

and **not** emit by default:

- JPA `@Entity`
- `JpaRepository`
- Flyway migrations

for the passthrough-router archetype.

## Explicitly Out Of MVP

Keep v1 narrow. Do not attempt all transport styles at once.

Out of scope for the first slice:

- Kafka / MQ / event-bus routing
- file-based passthrough flows
- long-running workflow orchestration
- dynamic expression languages
- database-backed enrichment lookups
- retry/circuit-breaker policy design
- per-operation mixed persistence modes inside one app
- Studio visual rule builders beyond basic form support

## Why This Fits EdgeForge

This is still aligned with the suite's core principles:

- manifest-in, code-out
- deterministic generation
- contract preservation at both edges
- canonical internal representation
- profile/archetype-driven output

It is a **second generator lane**, not a departure from EdgeForge's architecture.
