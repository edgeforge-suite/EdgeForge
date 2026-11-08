# Cross-Service Integration Design v1

> **Status:** Draft — directional design anchor, not final.
> **Scope:** How EdgeForge-generated microservices integrate with each other and with external systems.
> **Last updated:** 2026-05-14
> **Revision:** v1.1

## 1. Context and Problem

EdgeForge generates one standalone Spring Boot application per `app-definition.yaml`
manifest. Each generated app is independently buildable, deployable, and testable
with no EdgeForge runtime dependency.

When a decomposition workbench (or manual authoring) produces multiple manifests
that represent a decomposed system, those generated services must integrate with
each other. Today the Engine has no cross-manifest awareness — it processes one
manifest at a time.

This document defines the integration patterns EdgeForge-generated services should
support, the contract artifacts that govern those integrations, and the Engine
capabilities needed to generate them.

## 2. Design Principles

1. **Contract-first integration** — Services integrate through declared contracts
   (event schemas, API specs, file layouts), never through shared code, shared
   databases, or runtime coupling. If a contract is not declared in the manifest,
   the integration does not exist from the Engine's perspective.

2. **Schema is the contract** — The integration boundary between two services is a
   versioned schema (Avro, JSON Schema, OpenAPI). If both sides validate against
   the same schema version, they are compatible. Schema evolution rules (backward
   compatibility, forward compatibility) are enforced at the schema level, not in
   application code.

3. **No cross-service database access** — A generated service never reads from or
   writes to another service's database. All data sharing is through published
   interfaces. This ensures each service can evolve its persistence layer
   independently without breaking consumers.

4. **Event-driven by default, synchronous by exception** — Async event flows
   (Kafka) are the primary integration pattern. Synchronous REST calls are used
   only for point-in-time queries where eventual consistency is insufficient. This
   preference reduces temporal coupling and improves resilience.

5. **Each service owns its truth** — A service is the single source of truth for
   its domain entities. Other services receive projections via events, not direct
   entity access. This eliminates distributed ownership conflicts and keeps the
   canonical model principle intact within each service boundary.

6. **Correlation flows through the chain** *(target invariant — not yet
   implemented)* — Once Phase D of this roadmap and Phase 5 of
   [identity-role-engine-behavior-design.md](identity-role-engine-behavior-design.md)
   are delivered, every cross-service interaction will carry a correlation
   identifier so the full transaction flow is traceable end-to-end. Today
   `correlation_id` has no manifest export and no Engine behavior.

## 3. Integration Patterns

### 3.1 Event-Driven Async (Kafka)

This is the primary pattern. Service A publishes a domain event to a Kafka topic.
Service B consumes it and either routes it onward or handles it locally to update
its own domain state.

**Important distinction — two consumer shapes, only one modeled today:**

| Consumer shape | Description | Current manifest support |
|---|---|---|
| **Route / adapter** | Consume from topic A, transform, publish to topic B | `async_routes` (fire-and-forget, request-reply, router) — fully modeled |
| **Domain handler** | Consume from topic A, handle locally (update entity state, trigger batch work, write staging table) — no downstream topic | **Not yet modeled** — requires schema extension |

`async_routes` is an adapter/router pattern. Non-router `async_routes` entries
require `upstream_topic`, `downstream_topic`, and `transform_mapping`. A
terminal domain subscriber that handles an event locally and has no downstream
Kafka topic cannot be expressed as a valid `async_route` today — adding one
without a `downstream_topic` would fail schema validation.

**Current manifest mapping:**

- **Adapter/router consumers:** `async_routes` with `fire-and-forget`,
  `request-reply`, or `router` pattern. `message_schema` is carried on topic
  objects inside `async_routes`. This is the only current location for
  `message_schema`.
- **Domain handler consumers:** Not yet modeled. Services that consume an event
  and update local state (e.g., a reporting service updating analytics, a
  posting service updating entry status) have no valid manifest target today.
  Track as `gap: consumer-domain-handler-pending`.
- **Producer side:** Not yet modeled. `downstream_interfaces` uses
  `additionalProperties: false` and rejects `message_schema`. Track as
  `gap: producer-manifest-pending` (see Phase A).

**Gap:** Both domain handler consumers and event producers require manifest
schema extensions before they can be implemented. See Q1 and Q2 in Open
Questions.

### 3.2 Staging Tables and Data Handoffs

Service A writes to an **integration-owned handoff store** (a staging table, EOD
file, or batch output). Service B or a batch process reads from it. Both sides
declare the handoff in their manifests via `data_handoffs`.

**Important boundary:** Staging tables are not a loophole around the no
cross-service database rule. A staging table used for data handoff is an
explicit integration contract owned by the handoff — it is not another service's
private schema. Ownership, retention policy, and the consuming service must all
be declared in `data_handoffs`. A service must never read directly from another
service's entity tables.

**Current support:**

- `data_handoffs` section exists in the manifest schema with types like
  `staging-table`, `eod-file`, `gl-entry`, `batch-output`.
- Engine generates staging table DDL scaffolding.

**Gap:** Consumer-side ingestion scaffolding (reading from staging tables) is not
yet generated.

### 3.3 Synchronous REST (Query Only)

Service A calls Service B's REST API to fetch data for a point-in-time decision.
This is the exception pattern — used for lookups, not for triggering business
operations across services.

**Current support:**

- `upstream_interfaces` with type `REST` and `spec`/`spec_url` reference exists
  in the manifest schema.
- Engine generates the inbound REST API (server side) but does not generate
  outbound REST client stubs.

**Gap:** Engine should optionally generate a typed REST client (e.g., Spring
WebClient wrapper) from a declared upstream REST interface. This is lower priority
than event-driven integration.

### 3.4 Request-Reply (Kafka)

Service A sends a request message and waits for a correlated reply on a reply
topic. Already modeled in `async_routes` with the `request-reply` pattern
including `reply_timeout_ms`, `upstream_reply_topic`, `downstream_reply_topic`.

**Current support:** Fully modeled in the manifest schema. Engine generation
support is in progress.

## 4. Contract Artifacts

The following table shows which artifact governs each integration point:

| Integration pattern | Contract artifact  | Declared in manifest                                                           | Format                       |
| ------------------- | ------------------ | ------------------------------------------------------------------------------ | ---------------------------- |
| Kafka adapter/router consumer | Message schema | `async_routes[].upstream_topic.message_schema` | Avro (.avsc) or JSON Schema |
| Kafka domain handler consumer | Message schema | **Not yet in manifest** — requires schema extension (Q2) | Avro (.avsc) or JSON Schema |
| Kafka event producer | Message schema | **Not yet in manifest** — requires schema extension (Q1) | Avro (.avsc) or JSON Schema |
| REST API | API specification | `upstream_interfaces[].spec` or `spec_url` | OpenAPI 3.x |
| Staging table | Table specification | `data_handoffs[].spec` | DDL or spec document |
| Batch file | File layout | `data_handoffs[].spec` | Layout specification |

Two of the six rows above are pending manifest work. The gaps are in both
manifest modeling **and** Engine generation — not generation only.

## 5. What the Engine Should Generate (Roadmap)

### Phase A — Outbound event publishing (next priority)

**Prerequisite:** The manifest schema must be extended before this phase can be
implemented. `downstream_interfaces` entries currently use `spec`/`spec_url`
with `additionalProperties: false` and do not support `message_schema` or event
triggers. A new manifest mechanism is required — the shape is an open question
(see Q1 below). This document should be updated once that schema extension is
agreed and reflected in `app-definition.schema.json`.

When the manifest extension exists, the Engine should generate:

- A domain event class matching the declared message schema.
- A publisher service that emits the event after successful persistence.
- Spring Kafka producer configuration.

**Required reliability constraint:** Any generated outbound publisher must
satisfy the existing runtime hardening rules from the
[Generated App Quality Gate](generated-app-quality-gate-v1.md)
(Section E):

- Publish after confirmed DB commit, not before (transactional outbox or
  equivalent). With the outbox pattern, HTTP success may be returned after the
  local DB transaction — including the outbox record — commits durably. The
  broker send happens asynchronously; what matters is that it is confirmed
  before the outbox item is marked dispatched, not before the HTTP caller
  receives a response.
- Idempotent retry on broker failure — duplicate event delivery must be safe
  for consumers
- Confirmed broker send before marking the outbox event dispatched (or before
  completing correlation / acknowledging a source message in non-outbox flows)

Generating a naive "publish after save" without these properties would lose
events at DB commit / broker failure boundaries. This is a **blocking
correctness requirement** for Phase A, not a follow-up.

### Phase B — Contract test scaffolding

Generate consumer-driven contract tests (e.g., Pact or schema compatibility
tests) that verify:

- Producer's published event matches the declared schema.
- Consumer's deserialization matches the declared schema.
- Schema evolution is backward-compatible.

### Phase C — Outbound REST client generation

When a service declares an `upstream_interfaces` entry of type `REST`, optionally
generate a typed client wrapper from the OpenAPI spec. Lower priority — most
cross-service data sharing should be event-driven.

### Phase D — Correlation propagation

Generate MDC context propagation and Kafka header forwarding for `correlation_id`
fields. Ties to Phase 5 of the identity-role engine behavior roadmap.

### Phase E — Saga scaffolding (long-term)

For multi-step flows requiring compensation (e.g., a transaction that must be
reversed if a downstream step fails), generate saga orchestrator or choreography
scaffolding. This is the most complex pattern and requires significant design
work.

**Note:** Phases are directional. Ordering may change based on implementation
experience and priority shifts.

## 6. What the Engine Does NOT Own

Important boundaries for this integration design:

- **Cross-manifest schema compatibility.** The Engine does NOT validate that two
  manifests declare compatible schemas. It processes one manifest at a time.
  Schema compatibility validation is the responsibility of the tool that produces
  the manifests (e.g., a decomposition workbench or CI pipeline).

- **Integration topology.** The Engine does NOT produce an integration topology
  diagram. Topology is an upstream concern — the tool that decomposes a system
  into services owns the topology view.

- **Service mesh configuration.** The Engine does NOT generate service mesh
  configuration (Istio, Linkerd). Infrastructure concerns are outside generation
  scope.

- **Shared libraries.** The Engine does NOT generate shared libraries between
  services. Each generated app is standalone. If two services need the same event
  class, each generates its own from the shared schema artifact.

## 7. Example: Three-Service Event Flow

The following illustrates a generic three-service integration using the patterns
described above:

```
Order Service                Processing Service           Analytics Service
───────────                  ──────────────────           ─────────────────
Order placed (POST /orders)
  │
  ├──► Kafka: domain.order.created ──► Consumes event
  │                                     Processes fulfillment
  │                                       │
  │                                       ├──► Kafka: domain.order.fulfilled ──► Consumes event
  │                                       │                                      Updates analytics
  │                                       │
  │                                       └──► Staging table: settlement_entries
  │                                            (EOD batch picks up)
  │
  └──► REST: GET /orders/{id} ◄── Analytics queries order details (point-in-time)
```

Each service's manifest independently declares:

- **Order Service:** inbound REST API spec; outbound Kafka producer for
  `domain.order.created` *(producer-side manifest contract pending Phase A
  schema extension)*.
- **Processing Service:** consumes `domain.order.created` as a domain handler
  (fulfills order locally — no downstream topic) *(gap: consumer-domain-handler-pending
  — not expressible as valid `async_route` today)*; outbound producer for
  `domain.order.fulfilled` *(gap: producer-manifest-pending)*;
  `data_handoffs` entry for `settlement_entries`.
- **Analytics Service:** consumes `domain.order.fulfilled` as a domain handler
  (updates analytics state locally — no downstream topic) *(gap:
  consumer-domain-handler-pending)*; `upstream_interfaces` REST entry pointing
  to Order Service's OpenAPI spec.

The Engine generates each in isolation. Schema compatibility is validated before
generation by the authoring tool or CI.

## 8. Open Questions

### Q1. Outbound event publisher manifest shape (blocking for Phase A)

The current manifest has no valid location for Kafka producer contracts.
`downstream_interfaces` uses `additionalProperties: false` and rejects
`message_schema`. Phase A is blocked until this is resolved. Options:

- Extend `downstream_interfaces` with `message_schema` and `trigger` fields
  (requires a change to the manifest/contract schema,
  `appbuilder/schema/manifest-v1.schema.json`).
- Add a separate top-level `event_publishers` section.
- Reuse `async_routes` with a new `publish-on-entity-event` pattern.

**Highest-priority open question.** Needs design review and a manifest-schema
update before any Phase A implementation.

### Q2. Domain handler consumer manifest shape (blocking for Phase B/consumer)

The current `async_routes` schema requires `downstream_topic` and
`transform_mapping` for non-router patterns. A terminal domain subscriber that
consumes an event and handles it locally — updating entity state, triggering
a batch job, writing to a staging table — has no valid manifest target today.
Options:

- Add a `domain_handler` route pattern to `async_routes` that requires only
  `upstream_topic` and a handler reference (no `downstream_topic`).
- Add a separate top-level `event_subscriptions` section for domain handlers.
- Treat domain handler wiring as convention-based (entity + event type → handler
  class name) with no explicit manifest entry.

This must be resolved before any service with terminal event consumers can emit
a valid manifest.

### Q3. Schema registry integration

Should generated apps register schemas at startup (Confluent Schema Registry
pattern), or is schema validation a build-time-only concern? Runtime registry adds
operational complexity but enables schema evolution checks at publish time.

### Q4. Idempotent consumers

Should the Engine generate idempotent consumer logic by default (deduplicate by
event ID), or is this opt-in per `async_route`? Ties to `idempotency_key` Phase 4
in the identity-role engine behavior roadmap.

### Q5. Event sourcing

Is event sourcing (deriving entity state from an event log) in scope for EdgeForge
generation, or is it explicitly out of scope? If in scope, it is a separate design
effort.

### Q6. Choreography vs orchestration

When a flow spans three or more services, should EdgeForge generate choreography
(each service reacts to the previous event) or orchestration (a coordinator
service manages the flow)? Or should the Engine support both, chosen per manifest?

## 9. Relationship to Other Design Documents

- [Identity Role Engine Behavior Design](identity-role-engine-behavior-design.md)
  — Phase 5 (`correlation_id` propagation) enables end-to-end tracing across
  integrated services.
- [Generated App Quality Gate v1](generated-app-quality-gate-v1.md)
  — Section E (runtime hardening) covers Kafka reliability and retry.
- [Generated App Engine Roadmap](generated-app-engine-roadmap.md) — Cross-service
  integration adds new roadmap items to the Engine backlog.

## 10. Revision History

| Date       | Version | Change                               |
| ---------- | ------- | ------------------------------------ |
| 2026-05-13 | v1.0    | Initial draft — directional design anchor |
| 2026-05-14 | v1.1    | P1: corrected Kafka producer manifest mapping — `message_schema` only valid in `async_routes`, not `downstream_interfaces`; marked producer-side contract as pending Phase A schema extension. P2: clarified staging tables are integration-owned handoff stores, not cross-service DB access. P2: added outbox/idempotency reliability as a blocking Phase A correctness requirement. P3: marked correlation_id principle as target invariant, not current state. P1: distinguished `async_routes` as adapter/router pattern only — domain handler consumers (no downstream topic) have no valid manifest target today; marked as `gap: consumer-domain-handler-pending`. Updated contract table and Q1/Q2 accordingly. |

This document is a living artifact. It will be updated as integration patterns are
implemented, open questions are resolved, and real-world usage reveals gaps.
