# Kafka Integration Archetype Design

> Drafted 2026-04-13 by Codex. Reviewed and updated 2026-04-14 by Claude.
>
> **Status (April 2026):** Engine implementation is complete (PRs 2-7 merged).
> Studio authoring is complete (Studio PRs `#61-63` merged).
> This document is now a design reference, not an active roadmap.
>
> Use the target-state planning docs and the master backlog for remaining
> follow-on work:
> [docs/archive/target-state-architecture-roadmap-v1.md](archive/target-state-architecture-roadmap-v1.md),
> [docs/archive/target-state-sequencing-v1.md](archive/target-state-sequencing-v1.md),
> and [docs/archive/target-state-features-v1.md](archive/target-state-features-v1.md).

## Review Status

- Codex: drafted baseline, scoped first slice to fire-and-forget only ✅
- Claude: reviewed, agreed on separate archetype, Kafka-first, boring first
  slice; resolved open questions; added strategic context ✅
- Engine follow-through: complete through the merged multi-route and MCP
  dispatch proof baseline ✅
- Recommended next step: Studio Kafka authoring only after the Studio
  target-state design gates are approved

---

## Purpose

The v1.5.0 EdgeForge baseline proves two application lanes:

- `crud` for persistence-first bounded-context applications
- `passthrough-router` for constrained REST-oriented routing / adapter flows

The next immediate integration requirement is Kafka-based async mediation, driven
directly by a senior-leader demo signal. The target pattern is:

```text
upstream Kafka topic
  -> generated adapter consumes the event
  -> deterministic transform
  -> generated adapter publishes a downstream event
```

Some future routes also require request/reply mediation:

```text
upstream request topic
  -> transform to downstream request topic
  -> consume downstream response topic
  -> correlate response
  -> transform to upstream response topic
```

This document recommends a new `kafka-integration` archetype instead of
overloading the existing REST `passthrough-router` archetype.

---

## Strategic Context and Roadmap Relationship

### Why Kafka now

The senior-leader demo surfaced an immediate and concrete requirement: an
enterprise integration team needs Kafka-based async mediation, not REST-first
passthrough. This is a direct business pull, not speculative roadmap work.

### This is a parallel Engine archetype track, not a Phase 5/6 item

Kafka integration is a new **archetype** (a new kind of generated application).
Phase 5 is a new **MCP server** (Knowledge Server, for manifest authoring
assistance). These are independent tracks:

- Kafka work touches: `archetypes.py`, `manifest-v1.schema.json`, new
  `kafka_emitter.py`, new `kafka_translation.py`, `engine.py`
- Phase 5 KS work touches: a new `knowledge_server/` MCP implementation, Studio
  chat UI, document ingestion

They do not share files, do not block each other, and can run in parallel.
However, bandwidth is finite. The historical Engine sequence is now complete.
The next relevant sequencing rule is:

1. keep Knowledge Server backend work independent
2. treat Engine Kafka as stable enough for Studio planning
3. do not begin Kafka Studio authoring until the Studio step-registry and
   review-state design gates are approved

### Does Kafka deviate from core EdgeForge strategy?

No. Every core principle holds:

| Core principle | Kafka archetype compliance |
|---|---|
| Contract-preserving | ✅ Preserves upstream Kafka event schema and downstream Kafka event schema exactly |
| Manifest-driven | ✅ `async_routes` in manifest; no implicit contract inference |
| Canonical internal model | ✅ Transform mapping is the canonical bridge between upstream and downstream schemas |
| Deterministic generation | ✅ Same manifest always produces the same generated Spring Boot app |
| Profile-driven | ✅ `target_profile` still controls Java version and Spring Boot baseline |
| External adapters separate from business logic | ✅ Consumer / transformer / producer are the adapter layer; business logic belongs in the downstream service, not the generated adapter |
| Generated app independently deployable | ✅ Standard Spring Boot + spring-kafka, no EdgeForge runtime dependency |
| No breaking manifest changes | ✅ All new fields are optional; schema_version stays "1.0" |

The positioning risk to watch: do not let Kafka scope-creep EdgeForge into a
general integration platform (Boomi/MuleSoft territory). The guardrail is the
manifest — EdgeForge generates Kafka adapters **from contracts**, not from
arbitrary integration logic. The story stays "we generate a Kafka adapter that
preserves your upstream and downstream Kafka contracts, exactly as we generate a
CRUD app that preserves your upstream API contract."

### Relationship to planned passthrough-router transformation

The `TransformMapping` model extension for Kafka (adding `value_map`,
`type_coercion`, `constant`, and header extraction) is the same infrastructure
needed for REST passthrough transformation. Kafka work here builds the
foundation that REST passthrough transformation later reuses. This is a positive
side effect, not a conflict.

---

## Current State

The existing `passthrough-router` archetype already provides useful patterns:

- explicit archetype dispatch in `appbuilder/generation/engine.py`
- separate translation path in `appbuilder/metadata/translation.py`
- separate passthrough Java emitter in `appbuilder/generation/passthrough_emitter.py`
- separate passthrough build output in `appbuilder/generation/build_emitter.py`
- reusable `RoutingRule` and `TransformMapping` metadata concepts in
  `appbuilder/metadata/models.py`

The current passthrough lane is still intentionally narrow:

- REST JSON in / REST JSON out
- synchronous request/response
- one effective inbound DTO family
- one effective outbound DTO family
- global routing rules
- global flat field transforms
- no Kafka, MQ, event bus, request/reply correlation, retry policy, DLQ policy,
  or schema registry support

This means Kafka should be implemented as a parallel archetype lane, not as a
special mode hidden inside REST passthrough generation.

---

## Recommendation

Add a new additive archetype:

```yaml
app_archetype: kafka-integration
```

Start with the smallest boring Kafka proof:

```text
Kafka topic-to-topic fire-and-forget transform
```

Then grow in explicit slices:

1. design doc ← current PR
2. manifest schema + metadata model
3. topic-to-topic generation and proof
4. request/reply correlation and response transform
5. retry / DLQ / observability hardening
6. Studio authoring
7. multi-route scale proof

---

## Non-Goals For The First Slice

The first implementation slice should not include:

- request/reply correlation
- REST-to-Kafka hybrid generation
- multi-downstream fan-out aggregation
- Avro / Protobuf / schema registry integration
- arbitrary scripting, SpEL, MVEL, Groovy, or JavaScript transforms
- nested JSONPath transform evaluation
- DB-backed idempotency or correlation
- Kafka security UI beyond environment-variable-ready placeholders
- Knowledge Server MCP tools
- LegacyExtractor MCP tools
- Engine MCP HTTP transport or broader Phase 4 MCP expansion
- Studio UI before the Engine contract is proven
- exactly-once end-to-end semantics claims

---

## Generated Application Shape

For a Kafka topic-to-topic route, the generated Spring Boot application should
look like:

```text
src/main/java/com/appbuilder/{bounded_context}/
  {AppName}Application.java
  config/
    KafkaConsumerConfig.java
    KafkaProducerConfig.java
  dto/
    inbound/
      {UpstreamMessage}.java      (one DTO per upstream message schema)
    outbound/
      {DownstreamMessage}.java    (one DTO per downstream message schema)
  consumer/
    {RouteName}Consumer.java      (one @KafkaListener per upstream topic)
  producer/
    {RouteName}Producer.java      (one KafkaTemplate wrapper per downstream topic)
  transform/
    {RouteName}Transformer.java   (one transformer per async_route)

src/main/resources/
  application.yaml
```

Request/reply routes may later add:

```text
correlation/
  CorrelationStore.java
  InMemoryCorrelationStore.java
consumer/
  {RouteName}ResponseConsumer.java
producer/
  {RouteName}ResponseProducer.java
transform/
  {RouteName}ResponseTransformer.java
```

Retry / DLQ hardening may later add:

```text
dto/dlq/
  FailedMessageEnvelope.java
error/
  DlqPublisher.java
  KafkaErrorHandler.java
```

---

## Generated Runtime Defaults

For the first Kafka slice:

- JSON message payloads only
- `spring-kafka` and Spring Boot standard dependencies
- `enable-auto-commit=false`
- manual ack after transform and successful downstream publish
- producer `acks=all`
- topic names externalized through environment variables
- consumer group externalized through configuration
- partition key optional; default to broker strategy when omitted
- **at-least-once processing semantics only**

Do not promise exactly-once end-to-end semantics in the first slice. Kafka
producer idempotence can be enabled later, but end-to-end exactly-once behavior
requires stricter broker, transaction, idempotency, and state-store decisions
than this first archetype proof should carry. Document this explicitly in the
generated app README.

---

## Manifest Extension Direction

Keep `schema_version: "1.0"` stable. Add optional fields and a new
`app_archetype` enum value.

Illustrative manifest shape:

```yaml
app_name: payment-mediation-adapter
bounded_context: payment_mediation
schema_version: "1.0"
app_archetype: kafka-integration
target_profile: springboot-legacy-compatible

kafka_config:
  consumer_group: payment-mediation-group
  concurrency: 1

async_routes:
  - name: payment-initiated
    pattern: fire-and-forget
    upstream_topic:
      name: abc.payments.initiated.v1
      system: ABC_CORE
      message_schema: schemas/upstream/payment-initiated.json
      sample: samples/payment-initiated.json
    downstream_topic:
      name: xyz.settlement.request.v1
      system: XYZ_SETTLEMENT
      message_schema: schemas/downstream/settlement-request.json
      sample: samples/settlement-request.json
    transform_mapping: mappings/payment-to-settlement.yaml
    partition_key:
      strategy: field_value
      source: accountId
```

Future request/reply fields (PR 4 scope, not first slice):

```yaml
  - name: account-status-check
    pattern: request-reply
    upstream_topic:
      name: abc.account.status.request.v1
      system: ABC_CORE
      message_schema: schemas/upstream/account-status-request.json
    downstream_topic:
      name: xyz.account.lookup.request.v1
      system: XYZ_ACCOUNTS
      message_schema: schemas/downstream/account-lookup-request.json
    downstream_reply_topic:
      name: xyz.account.lookup.response.v1
      message_schema: schemas/downstream/account-lookup-response.json
    upstream_reply_topic:
      name: abc.account.status.response.v1
      message_schema: schemas/upstream/account-status-response.json
    transform_mapping: mappings/status-request-transform.yaml
    response_transform_mapping: mappings/status-response-transform.yaml
    correlation_id:
      source: header
      field_name: x-correlation-id
    reply_timeout_ms: 15000
```

---

## Transform Model

Reuse the spirit of the existing flat passthrough transform model, but extend it
additively for Kafka. The same `TransformMapping` model in
`appbuilder/metadata/models.py` is extended with optional new fields — existing
REST passthrough transforms that only use `source`, `target`, and `default` are
unaffected.

First-slice operations:

| Operation | Manifest syntax | Generated Java |
|-----------|---------|---|
| copy / rename | `source: amount`, `target: settlementAmount` | `out.setSettlementAmount(in.getAmount())` |
| default fallback | `source: currency`, `default: EUR` | `out.setCurrency(in.getCurrency() != null ? in.getCurrency() : "EUR")` |
| constant injection | `target: channel`, `constant: KAFKA_BRIDGE` | `out.setChannel("KAFKA_BRIDGE")` |
| header extraction | `source: "@header.x-source-system"` | `out.setOrigin(headers.get("x-source-system", String.class))` |
| value mapping | `value_map: { INSTANT: SCT_INST }` | Generated `switch` expression |
| major/minor units | `type_coercion: major_to_minor_units` | `in.getAmount().multiply(BigDecimal.valueOf(100)).longValue()` |

Example mapping file:

```yaml
transforms:
  - source: amount
    target: settlementAmount

  - source: currency
    target: settlementCurrency
    default: EUR

  - source: paymentType
    target: scheme
    value_map:
      INSTANT: SCT_INST
      CREDIT: SCT

  - source: amount
    target: amountMinorUnits
    type_coercion: major_to_minor_units

  - target: channel
    constant: KAFKA_BRIDGE

  - source: "@header.x-source-system"
    target: originatingSystem
```

The first slice stays flat. Nested object and array transform support comes
later when a real fixture proves the need.

**Explicitly deferred from first slice:** nested JSONPath, SpEL/MVEL/Groovy
expression evaluation, conditional transforms, multi-field aggregation. These
break the deterministic generation model and are not needed for the first proof.

---

## Message Schema Handling

Use JSON Schema for the first slice:

```text
schemas/
  upstream/
    payment-initiated.json
  downstream/
    settlement-request.json
```

The Engine translates JSON Schema into generated Java DTO fields using a
controlled type mapping:

| JSON Schema type | Java type |
|------------------|-----------|
| `string` | `String` |
| `integer` | `Long` or `Integer` |
| `number` | `BigDecimal` |
| `boolean` | `Boolean` |
| `string` + `format: date` | `LocalDate` |
| `string` + `format: date-time` | `OffsetDateTime` |

Avro and Protobuf are future additions, not part of the first Kafka proof.

---

## Request/Reply Correlation Direction

Request/reply is a second implementation slice (PR 4) after fire-and-forget
generation (PR 3) proves the new archetype.

Recommended behavior:

- correlation ID from Kafka header first, body field second
- generated response consumer listens to downstream reply topic
- generated response transformer maps downstream reply to upstream reply shape
- generated producer publishes upstream reply topic
- timeout behavior configured per route
- in-memory correlation store (ConcurrentHashMap + TTL) for first implementation
- persistent correlation state, duplicate handling, restart recovery, and
  broker transaction semantics deferred to a later hardening PR

---

## Retry And DLQ Direction

Retry and DLQ are important but belong in a later hardening PR (PR 5).

Recommended direction:

- route-level retry policy
- default DLQ topic suffix (e.g., `.dlq` appended to source topic name)
- DLQ envelope with original topic, key, payload, correlation ID, error, and
  timestamp
- no secrets in generated source
- Kafka credentials only through environment-backed configuration

---

## Engine Implementation Roadmap

### PR 1 — Design Document (current)

Files:

- `docs/kafka-integration-archetype-design.md`

Acceptance:

- no code changes
- design reviewed by Claude and Codex
- open questions resolved (see below)
- roadmap accepted before schema work begins

### PR 2 — Manifest Schema, Contract Models, Metadata Models

Likely files:

- `appbuilder/core/archetypes.py`
- `appbuilder/schema/manifest-v1.schema.json`
- `appbuilder/contracts/manifest.py`
- `appbuilder/metadata/models.py` (extend `TransformMapping` with new optional fields)
- new `appbuilder/metadata/kafka_models.py`
- `tests/unit/test_manifest.py`
- `tests/unit/test_manifest_schema_artifact.py`
- `tests/unit/test_validate_package.py`

Acceptance:

- `kafka-integration` is a valid additive archetype
- `async_routes` validation is strict only when `app_archetype` is
  `kafka-integration`
- existing CRUD and REST passthrough manifests validate unchanged
- all existing 422 tests pass

### PR 3 — Kafka Translation And Topic-To-Topic Generation

Likely files:

- new `appbuilder/metadata/kafka_translation.py`
- `appbuilder/metadata/translation.py` (add dispatch branch)
- new `appbuilder/generation/kafka_emitter.py`
- new `appbuilder/generation/kafka_build_emitter.py`
- `appbuilder/generation/engine.py` (add dispatch branch)
- new fixture under `tests/fixtures/kafka-integration/`
- new unit tests for translation, emitter, and build output

Acceptance:

- generated app has Kafka consumer, producer, transformer, DTOs, config, POM,
  README, Dockerfile, and `application.yaml`
- generated app compiles (`mvn package` clean)
- fixture covers at least two fire-and-forget routes
- generated app README states at-least-once semantics explicitly
- CRUD and REST passthrough tests remain green

### PR 4 — Request/Reply Correlation And Response Transform

Likely files:

- `appbuilder/metadata/kafka_models.py`
- `appbuilder/generation/kafka_emitter.py`
- request/reply fixture
- focused unit tests for correlation and response transform generation

Acceptance:

- generated request/reply app emits response consumer, response transformer, and
  response publisher
- correlation ID propagation is generated deterministically
- timeout behavior is explicit in generated config
- in-memory correlation store is clearly documented as non-persistent

### PR 5 — Retry, DLQ, Observability

Likely files:

- `appbuilder/generation/kafka_emitter.py`
- `appbuilder/generation/kafka_build_emitter.py`
- focused tests for DLQ envelope and config rendering

Acceptance:

- generated app includes route-level retry and DLQ configuration
- structured logging with correlationId in MDC
- secrets remain environment-backed only

### PR 6 — Studio Authoring UI

This belongs in `EdgeForgeStudio` after the Engine schema and generation
contract are stable (after PR 3 at minimum).

Likely work:

- archetype selector adds `kafka-integration`
- async route authoring view
- JSON Schema upload/paste for upstream and downstream messages
- transform mapping editor
- Kafka topic / consumer group / partition key configuration
- manifest preview/export support
- validation and error surfacing

### PR 7 — End-To-End Proof And Scale Fixture

Start with two routes:

- one fire-and-forget route (payment event example)
- one request/reply route

Then scale to a seven-route fixture once the two-route pattern is stable.

Testing options:

- prefer unit-level generated-source assertions first
- use Spring `@EmbeddedKafka` for generated-app proof (no Docker dependency)
- consider Testcontainers only when broker realism justifies the Docker overhead

---

## Studio Roadmap

Studio should not lead the schema design. The Engine manifest contract must be
stable first (PR 2 merged at minimum before Studio work begins).

Target Studio capabilities:

- select `kafka-integration` as an archetype
- define one or more async routes
- upload/paste JSON Schema for inbound and outbound messages
- configure upstream/downstream topics and systems
- define flat transform mappings
- configure partition key strategy
- preview/export the generated manifest package
- later: request/reply correlation and DLQ policy UI

---

## Guardrails

- Do not break CRUD behavior.
- Do not break current REST passthrough-router behavior.
- Do not mutate current passthrough output to simulate Kafka.
- Do not change `schema_version: "1.0"` semantics.
- Do not add unreviewed AI or runtime inference to generated apps.
- Do not add Knowledge Server or LegacyExtractor tools to Engine MCP.
- Do not add HTTP transport, auth, streaming, resources, or prompts to Phase 4
  Engine MCP as part of this work.
- Do not hardcode Kafka credentials or secrets in generated source.
- Do not claim exactly-once semantics in first slice.
- Generated apps must remain standard Spring Boot applications.
- Keep the first Kafka transform model deterministic and flat.
- All 422 existing Engine tests must pass at every PR.

---

## Open Questions — Resolved

The four questions raised during design review are resolved as follows:

**Q1: Standalone archetype or broader `integration` archetype family?**

Decision: standalone `kafka-integration` archetype now. A broader
`integration` archetype family (covering Kafka, JMS, MQ, file-based integration)
may be introduced later if the pattern repeats, but introducing a family
abstraction before a second integration type exists is premature. Revisit after
REST passthrough transformation and file-transform archetypes exist.

**Q2: `async_routes` only, or reuse `upstream_interfaces`/`downstream_interfaces`
with `type: kafka-json`?**

Decision: `async_routes` only. Reusing the REST interface fields would pollute
their semantics (they carry OpenAPI spec references, HTTP methods, URL paths).
Kafka routes carry topic names, consumer groups, and message schemas — these are
structurally different enough to warrant a separate top-level field.

**Q3: Model retry/DLQ schema before implementing the emitter?**

Decision: document future fields in this design doc (done above in Retry and DLQ
Direction). Implement schema fields for retry/DLQ in PR 5, not PR 2. Reason:
the fire-and-forget proof (PR 3) must be running before DLQ behavior can be
verified. Defining the schema fields before the emitter exists creates orphaned
schema that cannot be tested.

**Q4: Include `spring-boot-starter-web` from slice 1?**

Decision: yes, include it from slice 1. Reason: the generated app exposes
Spring Actuator health and metrics endpoints via HTTP, which enterprise
operations teams depend on. The web starter is justified by actuator/operations
requirements, not by REST passthrough behavior. Document this clearly in the
generated app README so future reviewers do not mistake it for a REST passthrough
archetype.

---

## Summary

Kafka async mediation should be a new Engine archetype lane:

```text
kafka-integration
```

The first implementation should prove deterministic topic-to-topic JSON
transformation with at-least-once semantics and flat field transforms. Request/
reply, correlation, retry, DLQ, Studio UI, and larger seven-route scale fixtures
should follow in separate reviewable PRs.

This keeps the v1.5.0 baseline stable, follows all core EdgeForge architecture
principles, and responds directly to the business demand for async integration
modernization without blocking Phase 5 Knowledge Server or Phase 6 LegacyExtractor
work.
