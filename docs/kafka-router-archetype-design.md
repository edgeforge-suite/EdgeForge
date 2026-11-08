# Kafka Router/Orchestrator Archetype Design

**Status:** Merged — PR #126 (2026-04-24). Design baseline for the `kafka-integration` router pattern.
**Branch:** `claude/docs/kafka-router-archetype-design`  
**Version:** 2.3 (design-doc correction pass — all blockers resolved, ground-truth aligned)  
**Date:** April 2026  
**Author:** Claude Code (architecture review)

---

## Finalized Requirement (Plain English — Confirm Before Implementation)

EdgeForge should be able to generate a reusable Kafka routing/orchestration application — call the generated app **RO** — that sits between one or more upstream systems (U1, U2, …) and one or more downstream processors (D1, D2, …).

When an upstream system publishes a JSON request, RO must:

1. Consume the request and identify the upstream source system and reply destination from headers or configured body fields.
2. Validate the reply destination early — fail fast with NACK before any downstream publish if the reply destination is invalid or unsupported.
3. Validate the inbound request against the RO/common request JSON Schema (V1).
4. Evaluate manifest/config-driven routing rules against routing fields (country, app version, partner, message type, etc.) to select the correct downstream target (D1 or D2) at runtime.
5. Register a correlation record capturing: correlationId, source system, reply destination, business flow, selected target, timestamps, and schema/route metadata.
6. Transform the validated request into the target-specific downstream JSON contract.
7. Validate the transformed request against the downstream request JSON Schema (V2).
8. Publish the transformed request to the selected downstream topic.
9. Consume the downstream response, correlate it back to the original request record, and validate it (V3).
10. Transform the downstream response into the RO/common response contract.
11. Validate the transformed response against the RO/common response JSON Schema (V4).
12. Publish the final response to the upstream-specific reply topic retrieved from the correlation record.
13. Produce a NACK/error response for **all** business/contract failures — including response-side validation failures (V3, V4) — and use retry/DLQ only for genuine technical failures such as Kafka publish failure, processing exception, or transient infrastructure fault.

**RO is not a one-off.** Topic names, schema files, routing rules, transform mappings, target metadata, NACK policy, retry policy, and timeout behavior all come from the manifest. The same Engine generates a different router app from a different manifest — no code change required.

**Initial scope:** JSON-to-JSON only. No XML. No fan-out/aggregation. No Saga/BPM. No event sourcing. One-of-N target selection only. Routing rules are deterministic and bounded — no scripting engine.

**Business MVP** = the phase combination that delivers the full U1→RO→D1/D2→RO→U1 roundtrip, including inbound NACK on bad requests and retry/DLQ on technical failures. A request-only technical slice is **not** the Business MVP.

---

## Architecture: Additive to Existing `kafka-integration` Model

The router pattern is **not** a separate archetype and **not** a parallel manifest lane. It is a new `pattern` value added to the existing `async_routes[]` model inside `app_archetype: kafka-integration`.

**Current pattern values** (from `appbuilder/contracts/manifest.py` and `manifest-v1.schema.json`):
- `fire-and-forget`
- `request-reply`

**New pattern value added by this design:**
- `router`

A single generated app can contain a mix of route patterns. For example:

```yaml
app_archetype: kafka-integration
async_routes:
  - name: audit_events
    pattern: fire-and-forget
    # ... existing fire-and-forget fields ...

  - name: loan_status
    pattern: request-reply
    # ... existing request-reply fields ...

  - name: loan_router
    pattern: router
    router_config:
      # ... router-only config (see §2) ...
```

**Anchor files for implementation:**

| File | Role |
|---|---|
| `appbuilder/contracts/manifest.py` | `AsyncRouteDefinition` — add `router_config: Optional[RouterConfig]` field + pattern validator update |
| `appbuilder/schema/manifest-v1.schema.json` | Add `router` to pattern enum + `routerConfig` definition |
| `appbuilder/metadata/kafka_translation.py` | Extend with router route translation + gen-time transform validation |
| `appbuilder/generation/kafka_emitter.py` | Extend with router pattern code emission (within existing kafka generation path) |

The router pattern generator is an extension of the existing kafka generation path — it does not introduce a separate `kafka_router_generator.py` archetype lane or a new top-level generator entry point.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Manifest Schema](#2-manifest-schema)
3. [Request Path](#3-request-path)
4. [Routing Decision](#4-routing-decision)
5. [Correlation Store](#5-correlation-store)
6. [Response Path](#6-response-path)
7. [Validation Boundaries](#7-validation-boundaries)
8. [NACK and Error Routing](#8-nack-and-error-routing)
9. [Business vs Technical Failure Split](#9-business-vs-technical-failure-split)
10. [Timeout Behavior](#10-timeout-behavior)
11. [Payload Logging Guardrails](#11-payload-logging-guardrails)
12. [Observability and Audit](#12-observability-and-audit)
13. [Generation-Time Transform Validation](#13-generation-time-transform-validation)
14. [Source System Extraction](#14-source-system-extraction)
15. [Generated Java/Spring Components](#15-generated-javaspring-components)
16. [Studio Authoring](#16-studio-authoring)
17. [TestBench Implications](#17-testbench-implications)
18. [Future Hardening (Non-Goals for Initial Phases)](#18-future-hardening-non-goals-for-initial-phases)
19. [Implementation Roadmap](#19-implementation-roadmap)

---

## 1. Architecture Overview

```
U1 ──► [U1-request-topic]
U2 ──► [U2-request-topic]   (or shared topic with source-system field/header)
              │
              ▼
     ┌────────────────────────────────────────────────────────┐
     │  RO  (generated kafka-integration app, pattern: router)│
     │                                                        │
     │  REQUEST PATH                                          │
     │  1.  Ingest from upstream topic(s)                     │
     │  2.  Extract source system + reply destination         │
     │  3.  Validate reply destination  ← fail-fast NACK      │
     │  4.  Parse JSON + V1 inbound validation                │
     │  5.  Evaluate routing rules → select D1 or D2          │
     │  6.  Check duplicate correlationId                     │
     │  7.  Register correlation record  ← first registration │
     │  8.  Transform request (T-req)                         │
     │  9.  Validate outbound request (V2)                    │
     │  10. Publish to selected downstream topic              │
     │                                                        │
     │  RESPONSE PATH                                         │
     │  11. Consume from downstream response topic            │
     │  12. Correlate response → retrieve record              │
     │  13. Validate downstream response (V3) [business]      │
     │  14. Transform response → RO/common format (T-resp)    │
     │  15. Validate RO/common response (V4) [business]       │
     │  16. Publish to upstream reply topic (from record)     │
     └────────────────────────────────────────────────────────┘
              │                        │
              ▼                        ▼
     [D1-request-topic]       [D2-request-topic]
              │                        │
     [D1-response-topic]      [D2-response-topic]
              └────────────────────────┘
                            │
       [U1-reply-topic] / [U2-reply-topic]
       [NACK topic(s)]  / [DLQ topic(s)]
```

**Key principles:**
- All configuration comes from the manifest. No hardcoded business values in generated code.
- V3 and V4 are business/contract validation boundaries — they produce NACK, not retry/DLQ.
- The correlation record is registered (step 7) only after routing is complete and reply-destination is validated. Steps 1–6 have no correlation record.

---

## 2. Manifest Schema

### 2.1 Route Entry Shape

The router pattern is expressed as one entry in `async_routes[]` with `pattern: router`. All router-specific config is nested under `router_config` on that route entry. Existing fields (`upstream_topic`, `downstream_topic`, `transform_mapping`) are not used for `pattern: router` — instead, intake and target config are declared inside `router_config`.

```yaml
app_archetype: kafka-integration
schema_version: "1.0"
# ... existing kafka_config, app_name, etc. ...

async_routes:
  - name: loan_router
    pattern: router

    router_config:

      # --- Upstream intake ---
      upstream_topics:
        - id: u1_intake
          name: "u1-loan-request"
          consumer_group: "ro-u1-consumer"
          source_system_extraction:
            mode: header          # header | body_field
            header_key: "X-Source-System"
          reply_destination_extraction:
            mode: header
            header_key: "X-Reply-To"
        - id: u2_intake
          name: "u2-loan-request"
          consumer_group: "ro-u2-consumer"
          source_system_extraction:
            mode: body_field
            body_field_path: "$.sourceSystem"
          reply_destination_extraction:
            mode: body_field
            body_field_path: "$.replyTopic"

      # --- Inbound schema (RO/common request contract) ---
      inbound_schema:
        file: "schemas/ro-request-v1.json"
        validation_policy: strict     # strict | lenient
        failure_behavior: nack

      # --- Routing rules (evaluated top-down; first match wins) ---
      routing_rules:
        routing_fields:
          - name: country
            json_path: "$.country"
          - name: appVersion
            json_path: "$.appVersion"
          - name: operationType
            json_path: "$.operationType"
        rules:
          - id: rule_uk_v2
            conditions:
              - field: country
                operator: eq
                value: "UK"
              - field: appVersion
                operator: eq
                value: "v2"
            target: d1_processor
          - id: rule_us_any
            conditions:
              - field: country
                operator: eq
                value: "US"
            target: d2_processor
        default_target: null    # null → NACK on no-match; set to a target id to use as fallback

      # --- Duplicate correlation policy ---
      duplicate_correlation_policy: reject-new   # reject-new (default, safe) | accept-last

      # --- Downstream targets ---
      targets:
        - id: d1_processor
          request_topic: "d1-loan-request"
          response_topic: "d1-loan-response"
          request_schema:
            file: "schemas/d1-request-v1.json"
            validation_policy: strict
            failure_behavior: nack
          response_schema:
            file: "schemas/d1-response-v1.json"
            validation_policy: strict
            failure_behavior: nack        # V3 = business failure → NACK
          request_transform:
            file: "transforms/ro-to-d1-request.yaml"
          response_transform:
            file: "transforms/d1-to-ro-response.yaml"
          retry:
            max_attempts: 3
            backoff_ms: 1000
            dlq_topic: "d1-loan-request-dlq"
          timeout_ms: 30000

        - id: d2_processor
          request_topic: "d2-loan-request"
          response_topic: "d2-loan-response"
          request_schema:
            file: "schemas/d2-request-v1.json"
            validation_policy: strict
            failure_behavior: nack
          response_schema:
            file: "schemas/d2-response-v1.json"
            validation_policy: strict
            failure_behavior: nack        # V3 = business failure → NACK
          request_transform:
            file: "transforms/ro-to-d2-request.yaml"
          response_transform:
            file: "transforms/d2-to-ro-response.yaml"
          retry:
            max_attempts: 3
            backoff_ms: 1000
            dlq_topic: "d2-loan-request-dlq"
          timeout_ms: 30000

      # --- Outbound schema (RO/common response contract) ---
      outbound_schema:
        file: "schemas/ro-response-v1.json"
        validation_policy: strict
        failure_behavior: nack    # V4 = business failure → NACK

      # --- NACK routing ---
      nack_routing:
        mode: per_source_system   # same_as_reply | per_source_system | fixed | default_error
        per_source_system:
          u1: "u1-loan-nack"
          u2: "u2-loan-nack"
        fixed_topic: null
        default_error_topic: "ro-default-error"

      # --- Timeout behavior ---
      timeout:
        behavior_with_known_reply: nack    # nack | error_topic
        behavior_without_reply: error_topic

      # --- Payload logging ---
      payload_logging:
        policy: none    # none (default, safe) | hash | redacted | capped_raw
        capped_raw_bytes: 512

      # --- Correlation store ---
      correlation_store:
        type: in_memory       # in_memory (Phase R1); persistent_jpa added in Phase R4
        timeout_ms: 30000
        eviction_interval_ms: 60000
```

### 2.2 Relationship to Existing `AsyncRouteDefinition`

The existing `AsyncRouteDefinition` model (`appbuilder/contracts/manifest.py`) currently defines:

```python
name: str
pattern: str                              # currently: "fire-and-forget" | "request-reply"
upstream_topic: KafkaTopicDefinition
downstream_topic: KafkaTopicDefinition
transform_mapping: str
upstream_reply_topic: Optional[KafkaReplyTopicDefinition]
downstream_reply_topic: Optional[KafkaReplyTopicDefinition]
response_transform_mapping: Optional[str]
correlation_id: Optional[CorrelationIdDefinition]
partition_key: Optional[PartitionKeyDefinition]
reply_timeout_ms: int = 30000
```

The `router` pattern extends this model with a **settled contract** — no ambiguity about which fields are required or forbidden per pattern:

**`manifest.py` — `AsyncRouteDefinition` changes:**

1. **Make fixed-route fields optional at the Pydantic level** so Pydantic does not reject a router route before the per-pattern validator runs. The currently-required fields become:
   ```python
   upstream_topic: Optional[KafkaTopicDefinition] = None      # was required
   downstream_topic: Optional[KafkaTopicDefinition] = None    # was required
   transform_mapping: Optional[str] = None                    # was required
   ```
   The already-optional fields (`upstream_reply_topic`, `downstream_reply_topic`, `response_transform_mapping`) need no change.

2. **Add the new router field:**
   ```python
   router_config: Optional[RouterConfig] = None
   ```

3. **Update `validate_pattern` validator** to accept `"router"` alongside the existing two values.

4. **Update `validate_pattern_fields` model validator** with a `router` branch and tighten the existing branches:
   - `router` branch: `router_config` must not be `None`; `upstream_topic`, `downstream_topic`, `transform_mapping`, `upstream_reply_topic`, `downstream_reply_topic`, `response_transform_mapping` must all be `None` (raise `ValueError` if any are set).
   - `request-reply` branch: unchanged — `upstream_topic`, `downstream_topic`, `transform_mapping` must not be `None` (add explicit checks since they are now Optional at the field level); existing reply-field checks unchanged.
   - `fire-and-forget` branch: unchanged — same explicit not-None checks for the three core fields; existing forbidden-field checks unchanged.

5. **Update referenced-path collection** (the code path that gathers file paths from a route for existence checks). It must branch on `pattern`:
   - For `router`: collect paths from `router_config` (all `file:` references inside `inbound_schema`, `outbound_schema`, `targets[].request_schema`, `targets[].response_schema`, `targets[].request_transform`, `targets[].response_transform`).
   - For `fire-and-forget` / `request-reply`: collect from the existing fields (`upstream_topic.message_schema`, `downstream_topic.message_schema`, `transform_mapping`, etc.) as today.

**`manifest-v1.schema.json` changes:**

1. **Remove `upstream_topic`, `downstream_topic`, `transform_mapping` from the unconditional `required` array** of `asyncRouteDefinition`. Currently `required: ["name", "pattern", "upstream_topic", "downstream_topic", "transform_mapping"]` — change to `required: ["name", "pattern"]`.

2. **Add `"router_config"` to `asyncRouteDefinition.properties`** referencing a new `routerConfig` `$defs` object.

3. **Add an `if/then/else` constraint** on `asyncRouteDefinition`:
   - `if pattern == "router"`: `router_config` is required; `upstream_topic`, `downstream_topic`, `transform_mapping`, `upstream_reply_topic`, `downstream_reply_topic`, `response_transform_mapping` are forbidden via `not` + `required`.
   - `else` (non-router): `upstream_topic`, `downstream_topic`, `transform_mapping` are required; `router_config` must be absent.

This means a router route entry looks like:

```yaml
- name: loan_router
  pattern: router
  router_config:
    upstream_topics: [...]
    # ...all other router config...
# upstream_topic, downstream_topic, transform_mapping are absent and forbidden
```

And a non-router route entry looks exactly as it does today — `router_config` absent, existing required fields present. No changes to existing `fire-and-forget` or `request-reply` validation.

### 2.3 Transform Mapping Format

Transform files are YAML field maps already used by the existing `kafka_translation.py` path. Extended for router-specific mapping types:

```yaml
# transforms/ro-to-d1-request.yaml
version: "1.0"
direction: request
source_schema: "schemas/ro-request-v1.json"
target_schema: "schemas/d1-request-v1.json"
mappings:
  - source: "$.loanAmount"
    target: "$.amount"
    type: copy           # copy | constant | value_map | concat | default_if_null
  - source: "$.country"
    target: "$.region"
    type: value_map
    value_map:
      UK: "EMEA"
      US: "AMER"
      default: null      # null → generation fails if source enum not fully covered
  - source: null
    target: "$.processorVersion"
    type: constant
    value: "D1-V2"
```

---

## 3. Request Path

### 3.1 Complete Request Processing Sequence

The following is the authoritative ordered sequence for request processing. Each step shows what it does, what happens on failure, and whether a correlation record exists at that point.

**Key rule: steps 1–6 have no correlation record. `cancel()` is only called from steps 8–10, after step 7 registered the record.**

```
Step 1  extractSourceSystem(record)
          # header or body_field per upstream topic config (§14)
          # if absent → sourceSystem = UNKNOWN → treat as step 2 failure

Step 2  validateSourceSystem(sourceSystem)
          # if UNKNOWN or not in configured set:
          #   publishNack(defaultErrorTopic, errorCode=UNKNOWN_SOURCE_SYSTEM)
          #   return   ← no correlation record; reply destination not yet known

Step 3  extractReplyDestination(record)
          # header or body_field per upstream topic config (§14)

Step 4  validateReplyDestination(replyDestination)
          # if null, blank, or not in supported set:
          #   publishNack(defaultErrorTopic, errorCode=INVALID_REPLY_DESTINATION)
          #   return   ← no correlation record; reply destination is the problem
          # FAIL-FAST: no schema validation, no routing, no downstream contact
          # happens here so that all subsequent NACKs have a valid reply destination

Step 5  parseJson + validate(payload, inbound_schema)   [V1]
          # strict or lenient per manifest
          # if failure (business failure):
          #   publishNack(replyDestination, errorCode=V1_VALIDATION_FAILED)
          #   return   ← no correlation record

Step 6  evaluateRoutingRules(payload, routing_rules)
          # extract routing fields; evaluate rules top-down; first match wins
          # if default_target configured and no rule matches: use default_target
          # if no match and no default_target:
          #   publishNack(replyDestination, errorCode=NO_ROUTING_RULE_MATCHED)
          #   return   ← no correlation record
          # if target not found in targets[]:
          #   publishNack(replyDestination, errorCode=UNKNOWN_TARGET)
          #   return   ← no correlation record
          # if duplicate correlationId + policy=reject-new:
          #   publishNack(replyDestination, errorCode=DUPLICATE_CORRELATION_ID)
          #   return   ← registration refused; never registered

Step 7  register(RoutingCorrelationRecord)
          # ← CORRELATION RECORD IS REGISTERED HERE
          # all subsequent failure paths must call cancel(correlationId) before NACK

Step 8  transformed = transform(payload, target.request_transform)
          # if runtime transform failure (e.g. value_map miss):
          #   cancel(correlationId)
          #   publishNack(replyDestination, errorCode=REQUEST_TRANSFORM_FAILED)
          #   return

Step 9  validate(transformed, target.request_schema)   [V2]
          # if failure (business failure):
          #   cancel(correlationId)
          #   publishNack(replyDestination, errorCode=V2_VALIDATION_FAILED)
          #   return

Step 10 publish(transformed, target.request_topic)
          # if Kafka publish fails (TECHNICAL failure):
          #   spring-kafka retry applies
          #   after max_attempts exhausted: DLQ + cancel(correlationId)
          #   return
```

**Why reply-destination validation is step 4 (before V1):** if validation fails later and RO cannot deliver the NACK to the reply destination, the error is silent. Validating the reply destination first ensures every NACK produced in steps 5–9 has a known and deliverable target.

### 3.2 Inbound Validation (V1) Detail

Schema: `router_config.inbound_schema.file`. Policy: `strict` or `lenient` per manifest. Default: `strict`.

`strict` rejects extra fields and enforces all type constraints. `lenient` permits extra fields but enforces `required` fields and declared types. V1 failure is a business failure — no retry.

### 3.3 Routing Decision Detail

Routing fields are extracted from the V1-validated payload using configured `json_path` expressions. Rules are evaluated top-down; first full-condition match wins. `default_target` (when configured) is the fallback if no rule matches. If `default_target` is `null` or absent and no rule matches, NACK is produced.

Condition operators: `eq`, `in`, `lt`, `lte`, `gt`, `gte`, `not_null`. All deterministic. No scripting, no SpEL. New operators require a manifest schema version bump.

Once a target ID is selected, all target-specific metadata is resolved from `targets[]` in the manifest: request topic, response topic, request schema, response schema, request transform, response transform, retry config, timeout. Adding a new target (D3) is a manifest-only change — no generated code change.

### 3.4 Correlation Registration Detail

The correlation record is registered at step 7 — after routing decision, duplicate check, and reply-destination validation. All fields in the record are known at registration time; no deferred update is needed.

```java
RoutingCorrelationRecord {
    String correlationId;          // from inbound header or generated UUID
    String sourceSystem;           // from step 1 extraction
    String replyDestination;       // from step 3 extraction
    String businessFlow;           // from route name or manifest field
    String selectedTargetId;       // from step 6 routing decision
    String selectedRequestTopic;   // resolved from target config
    String selectedResponseTopic;  // resolved from target config
    String requestSchemaVersion;   // from target.request_schema file reference
    String responseSchemaVersion;  // from target.response_schema file reference
    Instant capturedAt;
    Instant expiresAt;             // capturedAt + target.timeout_ms (or global fallback)
}
```

---

## 4. Routing Decision

### 4.1 Supported Condition Operators

| Operator | Description |
|---|---|
| `eq` | String or numeric equality |
| `in` | Value in configured list |
| `lt` / `lte` | Numeric less than / less-than-or-equal |
| `gt` / `gte` | Numeric greater than / greater-than-or-equal |
| `not_null` | Field present and non-null |

### 4.2 Default Target Fallback

`default_target` in `router_config.routing_rules` is optional.

- If configured with a valid target ID → used when no rule matches. This is a legitimate routing outcome, not an error.
- If `null` or absent and no rule matches → NACK (`NO_ROUTING_RULE_MATCHED`).

`default_target` must be consistent in:
- routing prose (§3.3, §4.2)
- routing YAML example (§2.1)
- NACK conditions table (§8.3)
- TestBench scenarios (§17.2): "No rule match / default target" scenario
- Roadmap acceptance criteria (§19, Phase R3 item 4)

---

## 5. Correlation Store

### 5.1 Current State (Ground Truth)

The current `kafka_emitter.py` generates a minimal CorrelationStore for `request-reply` routes:

```java
// CURRENT — what is generated today for request-reply pattern
ConcurrentHashMap<String, Instant> pending;
void register(String correlationId)   // stores correlationId → now + timeoutMs
boolean isExpired(String correlationId)
void complete(String correlationId)
@Scheduled(fixedDelay=60000) void evictExpired()
```

This is insufficient for the `router` pattern. The router requires a richer record and a `cancel()` operation.

### 5.2 Required Enriched CorrelationStore (Router Pattern)

```java
// REQUIRED for pattern: router
ConcurrentHashMap<String, RoutingCorrelationRecord> pending;

void register(RoutingCorrelationRecord record);
    // throws DuplicateCorrelationException if exists and policy=reject-new

RoutingCorrelationRecord retrieve(String correlationId);
    // returns null if not found (orphaned response case)

void complete(String correlationId);
    // called when response-path processing finishes (success or business failure)

void cancel(String correlationId);
    // called when a request-path failure occurs AFTER registration (steps 8-10)
    // prevents the eviction scheduler from firing a spurious timeout NACK

@Scheduled void evictExpired();
    // produces timeout NACK/error for entries past expiresAt
```

### 5.3 Correlation Cleanup — All Terminal Failure Paths

The cleanup action depends on whether the correlation record was registered when the failure occurs.

**Steps 1–6 (pre-registration): no correlation record exists — no cancel() needed**

| Step | Failure | Correlation action | NACK destination |
|---|---|---|---|
| 2 | Unknown/missing source system | None | `default_error_topic` (reply dest unknown) |
| 4 | Invalid/missing reply destination | None | `default_error_topic` (reply dest is the problem) |
| 5 | V1 validation failure | None | `nack_routing` per mode (reply dest known) |
| 6 | No routing rule matched, no default | None | `nack_routing` per mode |
| 6 | Unknown target ID | None | `nack_routing` per mode |
| 6 | Duplicate correlationId (reject-new) | None — registration refused | `nack_routing` per mode |

**Steps 7–10 (post-registration): record exists — cancel() required before NACK**

| Step | Failure | Correlation action | NACK destination |
|---|---|---|---|
| 8 | Request transform failure | `cancel(correlationId)` | `nack_routing` per mode |
| 9 | V2 outbound validation failure | `cancel(correlationId)` | `nack_routing` per mode |
| 10 | Kafka publish failure (technical) | Retry; on DLQ: `cancel(correlationId)` | DLQ topic |

**Response path (post-downstream): use complete(), not cancel()**

| Failure | Correlation action | NACK destination |
|---|---|---|
| V3 downstream response validation failure | `complete(correlationId)` | `nack_routing` per mode (reply dest from record) |
| Response transform failure | `complete(correlationId)` | `nack_routing` per mode |
| V4 RO response validation failure | `complete(correlationId)` | `nack_routing` per mode |
| Orphaned response (correlationId not found) | None — record already gone | `default_error_topic` |

On the response path, `complete()` (not `cancel()`) is used because the downstream interaction concluded — only the response-side processing failed.

### 5.4 Duplicate CorrelationId Policy

Default: `reject-new`. A duplicate `correlationId` arriving while one is pending → NACK to the reply destination; no processing, no overwrite.

`accept-last` is supported but must be explicitly set in the manifest (`duplicate_correlation_policy: accept-last`). It is not the default because it overwrites the `replyDestination` of the in-flight first request and can misroute its response.

### 5.5 Phase 1 In-Memory Limitation

In-memory CorrelationStore is acceptable for Phase R1 through R3. It does not survive JVM restart. Persistent correlation (DB or Redis-backed) is a future hardening phase — explicitly not out of scope. See §18.

---

## 6. Response Path

### 6.1 Downstream Response Consumption

```
KafkaListener(@downstream-response-topic)
  → extractCorrelationId(record)    # from Kafka correlation header
  → record = retrieve(correlationId)
  → if record == null:
      publishToDefaultErrorTopic(errorCode=ORPHANED_RESPONSE)
      return   # already timed out or cancelled; no reply destination known
```

### 6.2 Response Validation, Transform, and Upstream Publish

All failures on the response path call `complete(correlationId)` (the downstream interaction has concluded) and publish NACK to the reply destination from the stored record. None of these failures go to DLQ — they are all business/contract failures.

```
validate(downstreamResponse, target.response_schema)    // V3 — business/contract boundary
  → if failure:
      complete(correlationId)
      publishNack(record.replyDestination, errorCode=V3_VALIDATION_FAILED)
      return
      // reason: downstream violated its response contract
      // retrying will not fix a contract violation

transformed = transform(downstreamResponse, target.response_transform)
  → if failure:
      complete(correlationId)
      publishNack(record.replyDestination, errorCode=RESPONSE_TRANSFORM_FAILED)
      return

validate(roResponse, outbound_schema)                   // V4 — business/config boundary
  → if failure:
      complete(correlationId)
      publishNack(record.replyDestination, errorCode=V4_VALIDATION_FAILED)
      return
      // reason: response transform produced output that does not match RO response contract
      // retrying will not fix a mapping configuration error

publish(roResponse, record.replyDestination)
complete(correlationId)
```

### 6.3 Response Topic per Source System

The reply destination is **extracted** at step 3 and **validated** at step 4, but it is not stored in a correlation record until step 7 (registration). During the response path, RO retrieves the stored record and reads `record.replyDestination` — it does not re-examine response message headers. U1 and U2 can share a request topic while receiving responses on separate reply topics because each request's reply destination was captured in its own correlation record at registration time.

---

## 7. Validation Boundaries

All four boundaries produce NACK on failure. DLQ is reserved for Kafka publish failures and transient infrastructure faults only.

| Boundary | Schema source | Default policy | Failure behavior |
|---|---|---|---|
| V1 — Inbound RO request | `router_config.inbound_schema.file` | strict | **NACK** — no correlation record yet |
| V2 — Outbound downstream request | `targets[id].request_schema.file` | strict | **NACK** + `cancel(correlationId)` |
| V3 — Inbound downstream response | `targets[id].response_schema.file` | strict | **NACK** to reply dest + `complete(correlationId)` |
| V4 — Outbound RO/common response | `router_config.outbound_schema.file` | strict | **NACK** to reply dest + `complete(correlationId)` |

`strict` rejects extra fields. `lenient` allows extra fields but enforces required fields and types. Both policies are manifest-configured per boundary. `strict` is the default for all four.

Runtime JSON Schema validation using `networknt/json-schema-validator` is a **new generated-app dependency** added for the `router` pattern. It is not present in current generated `kafka-integration` apps. See §15.2.

---

## 8. NACK and Error Routing

### 8.1 Flexible NACK Routing Modes

| Mode | Behavior |
|---|---|
| `same_as_reply` | NACK published to the same topic as the normal reply destination |
| `per_source_system` | Map of source system ID → dedicated NACK topic |
| `fixed` | All NACKs go to a single configured topic |
| `default_error` | All NACKs go to `nack_routing.default_error_topic` |

A single global NACK topic is not sufficient for enterprise systems. Per-source-system NACK topics allow each upstream system to receive its own error notifications.

### 8.2 NACK Envelope

```json
{
  "correlationId": "...",
  "errorCode": "V1_VALIDATION_FAILED",
  "errorReason": "Required field 'country' is missing",
  "sourceSystem": "U1",
  "replyDestination": "u1-loan-reply",
  "businessFlow": "loan-origination",
  "selectedTarget": null,
  "validationBoundary": "V1",
  "timestamp": "2026-04-23T10:15:00Z",
  "originalPayloadRef": "<per payload_logging.policy — see §11>"
}
```

### 8.3 NACK Conditions — Full Table

| # | Condition | Step | Correlation action | NACK destination |
|---|---|---|---|---|
| 1 | Unknown/missing source system | 2 | None | `default_error_topic` |
| 2 | Invalid/missing reply destination | 4 | None | `default_error_topic` |
| 3 | V1 inbound validation failure | 5 | None | `nack_routing` per mode |
| 4 | No routing rule matched, no `default_target` | 6 | None | `nack_routing` per mode |
| 5 | Unknown target ID | 6 | None | `nack_routing` per mode |
| 6 | Duplicate correlationId (`reject-new`) | 6 | None — registration refused | `nack_routing` per mode |
| 7 | Request transform failure | 8 | `cancel(correlationId)` | `nack_routing` per mode |
| 8 | V2 outbound validation failure | 9 | `cancel(correlationId)` | `nack_routing` per mode |
| 9 | V3 downstream response validation failure | response | `complete(correlationId)` | `nack_routing` per mode |
| 10 | Response transform failure | response | `complete(correlationId)` | `nack_routing` per mode |
| 11 | V4 RO response validation failure | response | `complete(correlationId)` | `nack_routing` per mode |

**Cases 1–2 use `default_error_topic`** regardless of `nack_routing.mode` because the reply destination is not yet validated at those steps. All other cases use the `nack_routing` mode configured in the manifest.

---

## 9. Business vs Technical Failure Split

The current `kafka_emitter.py` wraps all exceptions as `IllegalStateException("Failed to process Kafka message", ex)`. There is no Business/Technical split today. The `router` pattern introduces a new exception hierarchy.

### 9.1 Exception Classes (New, Router Pattern Only)

```java
// Business/contract failures → NACK, no retry, no DLQ
RouterBusinessException extends RuntimeException
  ValidationFailedException extends RouterBusinessException
      // covers V1, V2, V3, V4 boundary failures
  RoutingRuleNotFoundException extends RouterBusinessException
  DuplicateCorrelationException extends RouterBusinessException
  InvalidReplyDestinationException extends RouterBusinessException
  TransformMappingException extends RouterBusinessException
      // runtime value_map miss, missing source field at runtime

// Technical failures → spring-kafka retry + DLQ
RouterTechnicalException extends RuntimeException
  KafkaPublishException extends RouterTechnicalException
      // Kafka broker/network failure on publish (step 10) — retry + DLQ appropriate
  UnexpectedProcessingException extends RouterTechnicalException

// NOTE: correlation/reply timeout is NOT in the exception hierarchy above.
// It is handled by the @Scheduled eviction scheduler (§10), which detects
// expired RoutingCorrelationRecords and publishes a NACK or writes to
// default_error_topic directly. It does not throw an exception and does not
// go through the spring-kafka listener retry/DLQ path.
//
// DownstreamTimeoutException is intentionally absent from this hierarchy to
// prevent implementers from routing upstream-facing timeout NACKs into DLQ.
```

### 9.2 Error Handler Routing

```java
@KafkaListener error handler:
  if (ex instanceof RouterBusinessException):
    publishNack(resolvedNackDestination, envelope)  // no retry
  else if (ex instanceof RouterTechnicalException):
    let spring-kafka DefaultErrorHandler retry/DLQ handle
  else:
    wrap as UnexpectedProcessingException → retry/DLQ
```

### 9.3 Why V3 and V4 Are Business Failures

V3 (downstream response validation) and V4 (RO/common response validation) are contract boundaries. They detect that a party violated its agreed message contract. Retrying does not fix a contract violation. These failures produce NACK to the upstream reply destination so the caller knows the operation failed. They are handled by `ValidationFailedException` (a `RouterBusinessException`), not by the DLQ path.

DLQ applies when Kafka publish itself fails (network, broker unavailable) — retrying infrastructure failure is appropriate.

---

## 10. Timeout Behavior

Timeout is detected by the eviction scheduler (`@Scheduled(fixedDelay=eviction_interval_ms)`). When a correlation record's `expiresAt` has passed:

```
evictExpired():
  for each expired record:
    if record.replyDestination is known:
      if timeout.behavior_with_known_reply == "nack":
        publishNack(record.replyDestination, errorCode=CORRELATION_TIMEOUT)
      else:
        publishToDefaultErrorTopic(errorCode=CORRELATION_TIMEOUT)
    else:
      publishToDefaultErrorTopic(errorCode=CORRELATION_TIMEOUT)
    remove record from store
```

Timeout duration per target: `targets[id].timeout_ms`. Global fallback: `correlation_store.timeout_ms`. The eviction scheduler does not go through the spring-kafka retry path — timeout is handled directly.

---

## 11. Payload Logging Guardrails

Message payloads contain PII, account numbers, and other sensitive fields. NACK/error envelopes must never default to including the raw original payload.

Configurable via `router_config.payload_logging.policy`:

| Policy | NACK/error envelope behavior |
|---|---|
| `none` **(default)** | `originalPayloadRef` field omitted entirely |
| `hash` | SHA-256 hash of serialized payload (audit correlation without exposing content) |
| `redacted` | Schema-driven field redaction — fields marked `pii: true` in schema replaced with `"***"` |
| `capped_raw` | First N bytes of raw payload; N from `capped_raw_bytes` |

**Default is `none`.** Changing to `capped_raw` requires explicit manifest opt-in. Payloads are never written to application logs regardless of this setting.

---

## 12. Observability and Audit

### 12.1 Scope: Generated-App vs Platform Integration

Items generated directly in Phase R3 (in the generated Spring Boot app) vs items left for later platform hardening:

| Item | Generated in Phase R3 | Later hardening |
|---|---|---|
| Structured log events (SLF4J + MDC) | ✓ | |
| Spring Actuator health/info/metrics | ✓ | |
| Micrometer counters | ✓ | |
| Environment-backed config (`@Value`) | ✓ | |
| Grafana dashboard templates | | ✓ |
| Elastic index templates | | ✓ |
| ServiceNow integration | | ✓ |
| Vault-specific secret binding | | ✓ |

### 12.2 MDC Fields

Current generated apps carry 3 MDC fields: `sourceTopic`, `partition`, `offset`. The router pattern adds 7 more:

| MDC Field | Source |
|---|---|
| `sourceTopic` | Kafka consumer record |
| `partition` | Kafka consumer record |
| `offset` | Kafka consumer record |
| `correlationId` | Extracted from request |
| `sourceSystem` | Step 1 extraction |
| `replyDestination` | Step 3 extraction |
| `businessFlow` | Route name / manifest field |
| `selectedTarget` | Step 6 routing decision |
| `schemaVersion` | From manifest |
| `routingRuleId` | Matched rule ID |

### 12.3 Structured Log Events

| Event | Level |
|---|---|
| `REQUEST_RECEIVED` — correlationId, sourceSystem, replyDestination | INFO |
| `VALIDATION_PASSED` / `VALIDATION_FAILED` — boundary (V1/V2/V3/V4), errorCode | INFO / WARN |
| `ROUTE_DECISION` — selectedTarget, routingRuleId, routingFields used | INFO |
| `CORRELATION_REGISTERED` / `DUPLICATE_REJECTED` | INFO / WARN |
| `TRANSFORM_COMPLETED` / `TRANSFORM_FAILED` — direction (request/response) | INFO / ERROR |
| `DOWNSTREAM_PUBLISHED` — targetTopic, correlationId | INFO |
| `DOWNSTREAM_RESPONSE_RECEIVED` — correlationId, selectedTarget | INFO |
| `UPSTREAM_RESPONSE_PUBLISHED` — replyDestination, correlationId | INFO |
| `NACK_PUBLISHED` — errorCode, validationBoundary, nackTopic | WARN |
| `DLQ_PUBLISHED` — targetDlqTopic, errorCode | ERROR |
| `CORRELATION_TIMEOUT` — correlationId, elapsedMs | WARN |

Payloads are **never** logged in any event.

### 12.4 Micrometer Counters

```
ro.request.received{sourceSystem, businessFlow}
ro.validation.failure{boundary, sourceSystem}
ro.route.decision{selectedTarget, routingRuleId}
ro.downstream.published{targetId}
ro.downstream.response.received{targetId}
ro.upstream.response.published{replyDestination}
ro.nack.published{errorCode, sourceSystem}
ro.dlq.published{targetId}
ro.correlation.timeout{targetId}
```

---

## 13. Generation-Time Transform Validation

**Current state:** `kafka_translation.py` validates file existence and loads field names + java types from the schema. It does **not** validate field-level cross-references between source schema, target schema, and the transform mapping file.

The router pattern extends `kafka_translation.py` with deterministic field-level validation at generation time.

### 13.1 Required Checks

For each transform file referenced in `router_config`:

1. **Source field existence** — each non-null `source` JSON path must resolve to a declared field in the `source_schema`.
2. **Target field existence** — each `target` JSON path must resolve to a declared field in the `target_schema`.
3. **Required target field coverage** — every `required` field in `target_schema` must be covered by a `copy`, `constant`, `value_map`, or `default_if_null` mapping entry.
4. **Type coercion legality** — source/target type mismatch must use an allowed coercion (string→string, int→string, boolean→string are allowed; string→int requires `value_map` or explicit cast).
5. **Value map coverage** — if `type: value_map` and `value_map.default` is `null`, every possible source enum value must appear as a key.

### 13.2 Failure vs Warning

| Check | Behavior |
|---|---|
| Source field not in source schema | **Generation fails** — structured error with file path, mapping index, field name |
| Target field not in target schema | **Generation fails** |
| Required target field not covered | **Generation fails** |
| Illegal type coercion | **Generation fails** |
| Value map missing coverage (default=null) | **Generation fails** |
| Value map missing coverage (default set) | Warning to stdout only |
| Extra source fields with no target mapping | Warning to stdout only |

These checks apply to both request transforms and response transforms for all targets in `router_config.targets[]`.

---

## 14. Source System Extraction

When U1 and U2 publish to the **same** request topic, source system and reply destination must be identified from message content. Two extraction modes are supported per upstream topic config:

| Mode | Description |
|---|---|
| `header` | Read from a Kafka record header key (e.g. `X-Source-System`) |
| `body_field` | Extract via JSON path from the body (e.g. `$.sourceSystem`) |

Both `source_system_extraction` and `reply_destination_extraction` use these two modes independently. Both are mandatory per `upstream_topics[]` entry.

If `mode: body_field`, extraction happens after basic JSON parse but before V1 schema validation. If the field is absent, the value defaults to `UNKNOWN`, which triggers a NACK at step 2 (`UNKNOWN_SOURCE_SYSTEM`).

---

## 15. Generated Java/Spring Components

### 15.1 New Components (Router Pattern Only)

| Component | Description |
|---|---|
| `RouterPatternListener.java` | `@KafkaListener` for upstream topics declared in `router_config.upstream_topics` |
| `DownstreamResponseListener.java` | `@KafkaListener` for downstream response topics from all targets |
| `RoutingService.java` | Orchestrates the full 16-step request + response path |
| `RoutingRuleEvaluator.java` | Evaluates `router_config.routing_rules` deterministically (no scripting) |
| `RoutingCorrelationStore.java` | In-memory `ConcurrentHashMap<String, RoutingCorrelationRecord>` |
| `RoutingCorrelationRecord.java` | 11-field correlation record (§5.2) |
| `RouterTransformService.java` | Applies router field mappings from transform YAML files |
| `RouterJsonSchemaValidator.java` | `networknt/json-schema-validator` wrapper, boundary-aware (V1/V2/V3/V4) |
| `NackPublisher.java` | Resolves NACK destination per `nack_routing.mode` and publishes NACK envelope |
| `RouterBusinessException.java` (hierarchy) | Business/contract failures — no retry |
| `RouterTechnicalException.java` (hierarchy) | Technical failures — retry/DLQ |
| `RouterErrorHandler.java` | `KafkaListenerErrorHandler`: routes to NACK vs retry/DLQ |
| `RouterObservabilityService.java` | Structured log events + Micrometer counter increments |

### 15.2 New Runtime Dependency (Router Pattern Only)

`RouterJsonSchemaValidator` requires `networknt/json-schema-validator` as a **new runtime dependency** in the generated app's `pom.xml`. This library is not currently used or present in any generated `kafka-integration` app. The dependency is added only when the manifest contains a `pattern: router` route.

```xml
<!-- Added to generated pom.xml when pattern: router is present -->
<dependency>
  <groupId>com.networknt</groupId>
  <artifactId>json-schema-validator</artifactId>
  <version>1.3.x</version>
</dependency>
```

### 15.3 Existing Components Extended (Not Replaced)

- `kafka_emitter.py` — extended with router pattern code emission (router handling is added within the existing kafka generation path, not a separate generator entry point)
- `kafka_translation.py` — extended with gen-time field/type/coverage validation for router transforms
- `manifest.py` (`AsyncRouteDefinition`) — extended with `router_config` field + `router` pattern validator
- `manifest-v1.schema.json` — extended with `router` pattern enum + `routerConfig` definition
- Spring Kafka `@KafkaListener`, `DefaultErrorHandler`, `DeadLetterPublishingRecoverer` — reused
- Spring Actuator — reused
- SLF4J MDC — reused, expanding from 3 to 10 fields

### 15.4 Configuration Properties

All topic names, schema file paths, routing rules, timeout values, retry counts, NACK mode, and payload-logging policy are externalized to generated `application.yml`. No hardcoded business values in generated Java code.

---

## 16. Studio Authoring

### 16.1 Current State

Studio has 3 Kafka authoring steps for existing patterns:
- `kafka_step1_topics.html` — consumer group + topic pairs
- `kafka_step2_routes.html` — route pattern (`fire-and-forget` / `request-reply`)
- `kafka_step3_transforms.html` — request and response field mappings

### 16.2 Router Pattern Extension

`kafka_step2_routes.html` adds `router` as a third selectable pattern. Selecting `router` activates sub-sections for `router_config` authoring within the same step (no new wizard step required):

- **Upstream topics** — list of topic name / consumer group / source-system extraction / reply-destination extraction per topic
- **Routing fields** — JSON path + name per routing dimension
- **Routing rules** — add/remove conditions, target selector per rule, first-match ordering
- **Default target** — optional dropdown (blank = NACK on no-match)
- **Duplicate correlation policy** — `reject-new` (default) / `accept-last` selector
- **NACK routing mode** — dropdown (`same_as_reply` / `per_source_system` / `fixed` / `default_error`)
- **Timeout config** — ms per target + behavior for known/unknown reply
- **Payload logging policy** — dropdown (`none` / `hash` / `redacted` / `capped_raw`)

`kafka_step3_transforms.html` extends to support per-target request + response transforms, value-map authoring, and response schema selection.

### 16.3 Wizard Registry Entry

```python
# wizard_registry.py addition
{
  "step_id": "kafka-router-rules",
  "label": "Routing Rules",
  "template": "kafka_step2_routes.html",
  "archetype": "kafka-integration",
  "condition": "kafka_pattern == 'router'"
}
```

---

## 17. TestBench Implications

The generated router app is difficult to validate by code inspection alone. TestBench must exercise the full roundtrip.

### 17.1 Current TestBench Support

- Redpanda v24.1.12 on ports 9092/19092
- `kafka_execution.py` — simulated + real scenario modes
- `adapters/kafka_integration.py` — real Kafka harness for `kafka-integration` and `passthrough-router` archetypes

The router harness extends the existing real Kafka harness — not built from scratch.

### 17.2 Required TestBench Scenarios

| Scenario | What to verify |
|---|---|
| **Happy path U1→D1** | Publish U1 request (country=UK, appVersion=v2) → verify D1 selected → simulate D1 response → verify U1 reply topic receives correct RO response |
| **Happy path U2→D2** | country=US from U2 source system → correct routing → U2 reply topic receives correct response |
| **Shared topic routing** | U1 and U2 publish to same topic with source-system body field → each receives response on correct reply topic |
| **No rule match / no `default_target`** | country=AU, no matching rule, no default → verify NACK on U1-NACK topic, nothing on D1 or D2 |
| **No rule match / `default_target` configured** | country=AU, default_target=d2_processor → verify routing to D2, full roundtrip completes |
| **Invalid reply destination** | Unknown or blank reply destination → verify NACK on `default_error_topic` (not U1-NACK, because reply dest is invalid) |
| **V1 inbound validation failure** | Missing required field → verify NACK on U1-NACK, no downstream publish, no spurious timeout later |
| **V2 outbound validation failure** | Inject malformed request transform → verify NACK on U1-NACK + correlation cancelled; wait > timeout_ms → verify no second timeout NACK |
| **V3 response validation failure** | Simulate D1 returning malformed response → verify NACK on U1 reply destination, **not** DLQ |
| **V4 RO response validation failure** | Inject malformed response transform → verify NACK on U1 reply destination, **not** DLQ |
| **Duplicate correlationId (`reject-new`)** | Publish same correlationId twice → verify second gets NACK, first proceeds normally |
| **Technical failure / DLQ** | Simulate Kafka publish failure to downstream → verify retry → DLQ after max_attempts |
| **Timeout / NACK** | Valid request, do not simulate downstream response → verify NACK on U1-NACK topic after `timeout_ms`; verify correlation record removed |
| **Correlation/routing trace** | After happy path → verify trace shows selectedTarget, routingRuleId, timing, schema version, all validation outcomes |

### 17.3 TestBench API Additions

- `POST /testbench/kafka-router/execute` — run a named scenario against live Redpanda
- `GET /testbench/kafka-router/trace/{correlationId}` — return routing trace (selectedTarget, timing, schemaVersion, validation outcomes per boundary)

---

## 18. Future Hardening (Non-Goals for Initial Phases)

Explicitly identified future work — not permanently out of scope:

| Item | Notes |
|---|---|
| **Persistent CorrelationStore** | DB or Redis-backed; required for restart recovery and multi-instance operation |
| Restart recovery | Re-register in-flight correlation records on startup |
| Multi-instance duplicate detection | DB-level unique constraint or distributed lock |
| XML transformation | Separate future phase after JSON-to-JSON is proven |
| Fan-out / aggregation | Different pattern; out of scope for `router` |
| Saga / BPM / event sourcing | Out of scope for `router` pattern |
| Full expression engine for routing rules | Add operators incrementally; no Groovy/SpEL at runtime |
| Grafana dashboard templates | Generated config files; observability hardening phase |
| Elastic index templates | Generated config files; observability hardening phase |
| Vault-specific secret binding | Spring Cloud Vault; security hardening phase |
| ServiceNow integration | Platform integration; not generated |
| mTLS / SASL Kafka auth | Target profile addition; security hardening phase |

---

## 19. Implementation Roadmap

Phases derived from actual current state of EdgeForge Engine (`v2.0.0` baseline), Studio, and TestBench.

### 19.1 Current State Baseline

| Component | Current State |
|---|---|
| Archetype model | `app_archetype: kafka-integration` + `async_routes[]` + `AsyncRouteDefinition` |
| Existing pattern values | `fire-and-forget`, `request-reply` (hyphenated) |
| CorrelationStore (current) | `ConcurrentHashMap<String, Instant>` — 2-field record, 3 methods |
| Exception handling (current) | All wrapped as `IllegalStateException` — no Business/Technical split |
| MDC fields (current) | 3: `sourceTopic`, `partition`, `offset` — no correlationId |
| Micrometer (current) | None beyond spring-kafka defaults |
| Transform validation (current) | `kafka_translation.py` — file existence + schema field loading only |
| Runtime JSON Schema validation | Not in generated apps — new dependency to add for router pattern |
| Studio Kafka authoring | 3 templates, 3 route pairs; `fire-and-forget` + `request-reply` patterns only |
| TestBench Kafka support | Redpanda v24.1.12 + real harness; `kafka-integration` + `passthrough-router` archetypes |

---

### Phase R1 — Manifest + Schema Extension + Gen-Time Validation

**Technical slice. Not Business MVP.**

**Purpose:** Extend the `kafka-integration` manifest schema with `pattern: router` and implement generation-time routing rule and transform validation. No generated Java app yet.

**Scope included:**
- Add `"router"` to `pattern` enum in `manifest-v1.schema.json` `asyncRouteDefinition`
- Add `routerConfig` definition to `manifest-v1.schema.json` with all router-only fields
- Add `router_config: Optional[RouterConfig]` to `AsyncRouteDefinition` in `manifest.py`
- Update pattern validator in `manifest.py` to accept `"router"`
- Add cross-field model validator: `router_config` required when `pattern == "router"`
- Generation-time routing rule validation: all target IDs in rules exist in `targets[]`
- Generation-time transform validation extended into `kafka_translation.py` (§13): source/target field existence, required-field coverage, type coercion, value-map coverage
- `RouterPatternGenerator` stub wired into existing kafka generation orchestration in `kafka_emitter.py` (no templates yet)
- Unit tests

**Scope excluded:** Generated Java app, Studio changes, TestBench changes.

**Engine manifest/schema changes:**
- `asyncRouteDefinition.pattern` enum extended with `"router"`
- `routerConfig` sub-object defined in `$defs`
- Existing `fire-and-forget` and `request-reply` routes unaffected

**Generator changes:**
- `kafka_translation.py`: `validate_router_transforms()` method added
- `kafka_emitter.py`: router pattern stub wired in

**Generated Java/Spring:** None.

**Studio changes:** None.

**TestBench changes:** None.

**Tests:**
- Unit: routing rule evaluator — all 5 operators, first-match semantics, `default_target` fallback
- Unit: gen-time transform validation — missing required field, wrong type coercion, value map gap
- Unit: manifest JSON Schema — valid router manifest passes, invalid router fields rejected
- Regression: existing `fire-and-forget` and `request-reply` manifests pass unchanged

**Acceptance criteria:**
- Valid router manifest (2 targets, 2 routing rules, 2 transform files, `default_target: null`) passes gen-time validation with no errors
- Manifest with missing required target field in a transform → generation fails with structured error (file path, mapping index, field name, reason)
- Manifest with `default_target` set to a valid target ID → passes validation
- Existing pattern manifests pass regression test unchanged

**Dependencies:** None (additive extension).

**Business MVP contribution:** Foundational. No user-visible app.

---

### Phase R2 — Generated Router App: Request Path

**Technical slice. Not Business MVP.**

**Purpose:** Generate the full request-side routing application through step 10 (downstream publish). No response path yet.

**Scope included:**
- `RouterApplication.java`, `RouterConfig.java`
- `RouterPatternListener.java` (MDC expanded to 10 fields)
- `RoutingService.java` — request path (steps 1–10 of §3.1)
- `RoutingRuleEvaluator.java` (Java runtime; `default_target` fallback included)
- `RouterTransformService.java` — request transform only
- `RouterJsonSchemaValidator.java` — V1 and V2 boundaries; `networknt/json-schema-validator` added to generated `pom.xml` as new dependency
- `RoutingCorrelationStore.java` — enriched 11-field record; `register`, `retrieve`, `complete`, `cancel`, `evictExpired`
- `RoutingCorrelationRecord.java`
- `RouterBusinessException.java` hierarchy
- `RouterTechnicalException.java` hierarchy
- `RouterErrorHandler.java` — business → NACK, technical → retry
- `NackPublisher.java` — all 4 NACK routing modes
- NACK envelope with `payload_logging.policy` (default: `none`)
- Duplicate correlationId handling (`reject-new` default)
- Micrometer counters for request-side events
- Structured log events for request-side stages
- Generated `application.yml` (request-side config only)
- Studio: `kafka_step2_routes.html` — `router` pattern option + upstream topics, routing fields/rules, NACK mode, timeout config, payload logging policy
- `kafka.py` routes — save/load for `router_config` block
- TestBench: request-side scenarios (see below)

**Scope excluded:**
- `DownstreamResponseListener`, V3/V4 validation, response transform, upstream response publish
- Timeout NACK on reply destination (eviction scheduler emits to `default_error_topic` only in this phase — full timeout NACK with known reply destination is R3)

**Engine manifest/schema changes:** None beyond R1.

**Generator changes:** `RouterPatternGenerator` within `kafka_emitter.py` — request-path Java + Jinja2 templates.

**Studio changes:**
- `kafka_step2_routes.html` — `router` pattern selection + `router_config` sub-form
- `kafka.py` — save/load router config
- `wizard_registry.py` — `kafka-router-rules` step entry

**TestBench changes:**
- `kafka-router` harness in `adapters/kafka_integration.py`
- Scenarios delivered in R2:
  - Happy path request-to-D1: publish U1 request → verify D1 topic receives correctly transformed message
  - V1 validation failure: missing required field → NACK on U1-NACK, nothing on D1
  - No routing rule matched (no default): → NACK on U1-NACK
  - No routing rule matched (default_target configured): → message routed to default target topic
  - Invalid reply destination: → NACK on `default_error_topic`
  - Duplicate correlationId (`reject-new`): → second gets NACK, first proceeds to D1
  - Shared topic routing (request side): U1 and U2 on same topic with body_field source system → correct D1/D2 downstream routing

**Tests:**
- Unit: `RoutingService` request path with mocked Kafka publisher
- Unit: `RoutingRuleEvaluator` — all operators, `default_target` fallback
- Unit: `RoutingCorrelationStore` — register, duplicate reject, cancel, evict
- Unit: `NackPublisher` — all 4 modes; cases 1–2 use `default_error_topic`
- Unit: `RouterJsonSchemaValidator` — strict vs lenient, V1/V2
- Integration (TestBench): publish U1 request → verify D1 topic receives transformed message

**Acceptance criteria:**
- Valid U1 request routes to D1 topic with correct transformation
- V1 failure → NACK on U1-NACK, no downstream publish
- Duplicate correlationId → NACK, no overwrite
- Invalid reply destination → NACK on `default_error_topic` (not `nack_routing` mode)
- No match + no default → NACK
- No match + default_target → correct fallback routing
- Pre-downstream failure (V2) → correlation cancelled; wait > timeout_ms → no spurious second NACK

**Dependencies:** R1.

**Business MVP contribution:** Partial (request half). Not Business MVP.

---

### Phase R3 — Generated Router App: Response Path + Full Roundtrip

**⚑ BUSINESS MVP: R1 + R2 + R3 together deliver the true Business MVP.**

**Purpose:** Complete the response path. Full U1→RO→D1/D2→RO→U1 roundtrip, NACK on all business failures (including V3/V4), retry/DLQ on technical failures, full timeout NACK behavior.

**Scope included:**
- `DownstreamResponseListener.java` — `@KafkaListener` for all downstream response topics
- `RoutingService.java` response path (steps 11–16 of §6.2, V3/V4 as NACK not DLQ)
- `RouterTransformService.java` — response transform
- `RouterJsonSchemaValidator.java` — V3 and V4 boundaries
- `RouterObservabilityService.java` — full structured event set + all Micrometer counters (§12)
- Timeout eviction — full behavior: NACK to reply destination when known (per `timeout.behavior_with_known_reply`), else `default_error_topic`
- Orphaned response handling
- Full `application.yml` (request + response config merged)
- MDC full 10-field set
- Studio: `kafka_step3_transforms.html` — per-target response transform + value-map authoring + response schema selector + outbound schema (V4) selector
- TestBench: remaining scenarios from §17.2

**Scope excluded:**
- Persistent CorrelationStore (still in-memory)
- Grafana/Elastic/Vault/ServiceNow platform wiring
- XML transforms, fan-out/aggregation

**Engine manifest/schema changes:** None beyond R1.

**Generator changes:** Response-path Jinja2 templates in `kafka_emitter.py` router extension.

**Studio changes:**
- `kafka_step3_transforms.html` — per-target response transform + value-map authoring
- Response schema file selector per target
- Outbound schema (V4) file selector

**TestBench changes:**
- Remaining scenarios from §17.2:
  - Happy path U1→D1 full roundtrip (simulate D1 response → verify U1 reply)
  - Happy path U2→D2 full roundtrip
  - Shared topic full roundtrip (each upstream receives response on correct reply topic)
  - No rule match / `default_target` → full roundtrip via default target
  - V3 failure → NACK on reply destination, **not** DLQ
  - V4 failure → NACK on reply destination, **not** DLQ
  - Timeout → NACK on U1-NACK after timeout_ms; verify correlation record removed
  - V2 pre-downstream failure → correlation cancelled; no spurious timeout NACK
  - Technical failure / DLQ → Kafka publish failure → retry → DLQ
  - Correlation/routing trace → verify all fields populated
- `POST /testbench/kafka-router/execute`
- `GET /testbench/kafka-router/trace/{correlationId}`

**Tests:**
- Unit: `DownstreamResponseListener` — V3 failure → NACK (not DLQ)
- Unit: `RoutingService` response path — V4 failure → NACK (not DLQ)
- Unit: timeout eviction — reply known → NACK, reply unknown → error topic
- Integration (TestBench): full roundtrip U1→D1→U1-reply
- Integration (TestBench): V3 failure → NACK on reply destination
- Integration (TestBench): V4 failure → NACK on reply destination
- Integration (TestBench): timeout → NACK after timeout_ms
- Integration (TestBench): DLQ → Kafka publish failure → retry → DLQ

**Acceptance criteria (Business MVP gate):**
1. U1 valid request → RO routes to D1 → simulated D1 response → U1 receives correct RO response on reply topic
2. U2 valid request → RO routes to D2 → simulated D2 response → U2 receives correct RO response on reply topic
3. Invalid request → NACK on U1-NACK topic; nothing published to D1 or D2
4. No matching rule, `default_target` configured → routing to default target; full roundtrip completes
5. No matching rule, no `default_target` → NACK on U1-NACK
6. V3 failure (bad downstream response) → NACK on reply destination, **not** DLQ
7. V4 failure (bad response transform output) → NACK on reply destination, **not** DLQ
8. Kafka publish failure → retry → DLQ after max_attempts
9. Timeout with known reply → NACK after timeout_ms; no second NACK after that
10. All Micrometer counters increment correctly per scenario
11. Routing trace visible via TestBench trace API
12. Generated app compiles, starts, passes `mvn test`, no EdgeForge runtime dependency

**Dependencies:** R1 + R2.

**Business MVP:** ✓ R1 + R2 + R3 = Business MVP.

---

### Phase R4 — Production Hardening (Post-MVP)

**Post-MVP. Not required for Business MVP.**

**Purpose:** Harden for production-like constraints.

**Scope:**
- Persistent CorrelationStore (`correlation_store.type: persistent_jpa` — Spring Data JPA + Flyway table; eviction scheduler persists timeout-NACK state across restart)
- Restart recovery (re-register in-flight records on startup)
- Multi-instance duplicate detection (DB unique constraint on correlationId)
- SASL/SSL Kafka auth profile additions
- Spring Cloud Vault secret binding
- Grafana dashboard template (generated JSON from manifest)
- Elastic index template (generated NDJSON from manifest)
- Schema-driven field redaction for `payload_logging.policy: redacted`

**Dependencies:** R3 (Business MVP complete first).

---

### Phase Summary

| Phase | Business MVP? | Delivers |
|---|---|---|
| R1 | Foundation only | `pattern: router` in schema + gen-time transform validation |
| R2 | Partial — request half | Generated request path + Studio router authoring + TestBench request scenarios |
| **R3** | **✓ YES — Business MVP** | **Full roundtrip + V3/V4 NACK + full timeout + TestBench full scenarios** |
| R4 | Post-MVP hardening | Persistent correlation, security, observability platform integration |

**R1 + R2 + R3 = true Business MVP.**  
R1 + R2 alone is a technical slice. R3 is required to complete it.

---

*EdgeForge Suite · Kafka Router/Orchestrator Archetype Design · v2.3 · April 2026*
