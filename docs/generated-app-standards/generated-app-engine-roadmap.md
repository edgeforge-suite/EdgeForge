# Generated App Engine Roadmap

> **Status:** Roadmap companion to
> [Generated App Quality Gate v1](generated-app-quality-gate-v1.md).
>
> **Created:** 2026-05-05.
>
> **Updated:** 2026-05-18. PRs 1–8 delivered via Engine PRs `#141`–`#153` on
> `origin/main` post-v3.0.0. PR 9 (Kafka router performance polish) remains a
> true residual. PR 10 (Studio/KS source-contract conflict) is design-pending.
>
> **Scope:** Design-to-implementation bridge. This file does not implement
> Engine changes; it ranks the follow-up PRs implied by the quality gate.

## Purpose

The generated app quality gate names the bar. This roadmap turns that
bar into implementation-ready work packages for the Engine, Studio, and
generated-app/domain layers.

## Completed Baseline Capabilities

The `v3.0.0` baseline and the post-baseline identity work closed the first
identity loop. These items are complete capabilities, not planned roadmap work:

1. Engine accepts explicit `identity_overrides` and fails fast on unsafe
   event/transaction identity inference.
2. Studio lets authors review manual identity roles and exports
   `persistence_id` as `identity_overrides`.
3. Knowledge Server suggests deterministic `identity_role` candidates.
4. Studio consumes those suggestions and the full identity KA smoke passed:
   KS suggests -> Studio reviews -> Studio exports -> Engine generates/builds.

## Delivered — Post-v3.0.0 Generated-App Hardening

The following roadmap PRs are **delivered** via Engine PRs `#141`–`#153` on
`origin/main`. Two generated apps drove the reviews: a small CRUD app with
staging/EOD files, and a Kafka router proof app with request/response transforms.

| Roadmap PR | Capability | Engine PR(s) | Status |
|---|---|---|---|
| PR 1 | CRUD fixed-width minor-unit and temporal correctness | `#141` | Delivered |
| PR 2 | Kafka router response publish and correlation correctness | `#142` | Delivered |
| PR 3 | CRUD API DTO and list contract fidelity | `#143` | Delivered |
| PR 4 | Kafka router schema validation and business error taxonomy | `#144` | Delivered |
| PR 5 | Generated-app quality gate regression fixtures | `#145` | Delivered |
| PR 6 | CRUD EOD rerun and batch topology | `#146` | Delivered |
| PR 7 | Kafka router operational semantics | `#147` | Delivered |
| PR 8 + quality closeouts | UUID and persistence DDL consistency, CRUD UI routes, duplicate-ID conflict guard, staging run identity | `#148`–`#153` | Delivered |

### True Residuals

The following items from the original roadmap are **not yet implemented**:

- **PR 9 — Kafka Router Performance Polish (P3):** routing rule rebuild per message
  and double JSON parse on the happy path remain unoptimized. See [PR 9](#pr-9--engine-kafka-router-performance-polish) below.
- **PR 10 — Studio / KS Source-Contract Conflict Surfacing (P3):** enum and
  field-length mismatches across OpenAPI, rules, and staging DDL need a design
  doc before implementation. See [PR 10](#pr-10--studio--ks-source-contract-conflict-surfacing) below.

### Additional Confirmed Residuals (from post-v3.0.0 code review)

These items from the quality gate gap register are partially implemented or still absent:

- **B5** Liveness/readiness K8s probe split — `/actuator/health` HEALTHCHECK present; separate liveness/readiness endpoints not yet split
- **B6** MDC/structured logging — present in Kafka lane (`MDC.put("sourceTopic", ...)`); absent in CRUD lane
- **B8** CI/build pipeline descriptor — no CI config file generated
- **B7/C4** Secrets/config defaults — enterprise PostgreSQL datasource credentials are env-var-required with no `postgres` fallback; remaining work is broader secrets/config standardization as needed

## Remaining Hardening Work

## Priority Legend

| Priority | Meaning |
|---|---|
| `P0` | Correctness blocker for demo/proof confidence or real-data use. |
| `P1` | Contract fidelity or operational correctness needed before production candidacy. |
| `P2` | Production hardening that can follow the correctness slices. |
| `P3` | Useful polish, scale, or observability refinement. |

## Full PR Catalogue (for reference — PRs 1–8 delivered)

### PR 1 — Engine: CRUD Fixed-Width Minor-Unit And Temporal Correctness

**Status: Delivered — Engine PR `#141`.**

**Owner repo:** EdgeForge Engine.

**Priority:** P0.

**Complexity:** Medium.

**Task type:** implementation + generated-output regression.

**Why first:** the reviewed CRUD app produced demonstrably wrong downstream
handoff output and has a runtime-prone date/staging mismatch. These are direct
contract correctness issues in generated files.

**Required behavior:**

- When a downstream fixed-width field is explicitly mapped as a minor-unit
  amount, or when the contract has an unambiguous `_minor` naming convention,
  convert `BigDecimal` major units to integer minor units and left-zero-pad to
  the declared field width.
- Propagate OpenAPI `string` + `format: date`, JSON Schema `format: date`, and
  staging DDL `DATE` into Java `LocalDate`, request/response DTOs, entity
  fields, Flyway DDL, and staging writers.
- Keep `date-time` mapped to an appropriate Java temporal type such as
  `OffsetDateTime` where already supported.
- Avoid silent semantic conversion when the mapping is ambiguous; prefer a
  validation warning or explicit transform requirement.

**Done means:**

- `available_balance_minor`-style fields emit `00000000125000`, not
  `100.0000`, when the source amount is 1250.00 and the file contract requires
  minor units.
- `openedDate`-style fields do not drift between `String`/`VARCHAR` and
  `DATE`.
- Generated staging writer and EOD file tests cover these cases.

**Likely areas:**

- `appbuilder/metadata/translation.py`
- `appbuilder/generation/java_emitter.py`
- `appbuilder/generation/sql_emitter.py`
- downstream file writer generation
- generated-output tests

### PR 2 — Engine: Kafka Router Response Publish And Correlation Correctness

**Status: Delivered — Engine PR `#142`.**

**Owner repo:** EdgeForge Engine.

**Priority:** P0.

**Complexity:** Medium.

**Task type:** implementation + generated-output regression.

**Why second:** the Kafka router is structurally strong, but publish/ack and
correlation ordering are message-loss risks. The generated response path must
prove that downstream replies are actually published upstream before the
listener acknowledges and before the correlation is completed.

**Required behavior:**

- Verify current Engine source/output for the response-publish path. If
  `kafkaTemplate.send(record)` is confirmed where `record` is a
  `RoutingCorrelationRecord` rather than the intended upstream
  `ProducerRecord`, fix it to send the upstream response record.
- Confirm Kafka producer sends before acknowledging consumed messages or
  completing correlations. `kafkaTemplate.send(...)` is asynchronous; generated
  code must not treat an enqueued send as a confirmed broker publish.
- If downstream publish fails, cancel or roll back the correlation state so a
  retry of the input does not become a false duplicate-correlation NACK.
- If upstream reply or NACK publish fails, surface a technical failure path that
  can retry/DLQ according to the generated listener/error-handler contract.
- Ensure optional source fields are not emitted as `null` target fields when
  the target JSON Schema declares an optional but non-nullable string/number.
  Omit the property or require an explicit nullable/default transform.

**Done means:**

- A generated router app can complete U1 -> router -> D1 -> router -> U1 reply
  roundtrip with confirmed send semantics.
- Publish failure tests do not leave stale in-memory correlation records that
  poison retries.
- Optional absent fields do not create false V2 schema failures.
- Existing Kafka fire-and-forget and request-reply generation remain green.

**Likely areas:**

- `appbuilder/generation/kafka_emitter.py`
- generated router `RoutingService.java`
- generated router listeners and error handler templates
- generated router tests/golden output

### PR 3 — Engine: CRUD API DTO And List Contract Fidelity

**Status: Delivered — Engine PR `#143`.**

**Owner repo:** EdgeForge Engine.

**Priority:** P1.

**Complexity:** Medium-Large.

**Task type:** implementation + generated-output regression.

**Why third:** controllers and service methods should reflect the manifest's
API contract, not generic CRUD shortcuts. The reviewed app generated DTOs, but
GET/LIST/PUT paths still exposed or accepted JPA entities.

**Required behavior:**

- Controllers return response DTOs for read/list operations when the manifest
  declares response mappings.
- Update operations accept request DTOs plus `@Valid`, not JPA domain entities.
- List operations that return arrays/lists generate list response DTOs or
  `List<ResponseDto>` and do not generate fake request DTO IDs when the
  upstream route has no request identifier.
- Operation-specific service methods should be reachable from controllers or
  not emitted.
- Domain entities should not be serialized as public API response bodies when a
  contract DTO exists.

**Done means:**

- `GET /customers` and `GET /accounts` style operations return the declared
  array/list contract.
- Generated dead list methods that perform `findById` for list routes are gone.
- Existing CRUD scaffolds still support simple generic read/list routes when
  no explicit operation mapping exists.

### PR 4 — Engine: Kafka Router Schema Validation And Business Error Taxonomy

**Status: Delivered — Engine PR `#144`.**

**Owner repo:** EdgeForge Engine.

**Priority:** P1.

**Complexity:** Medium.

**Task type:** implementation.

**Required behavior:**

- Cache compiled JSON Schemas by schema path instead of recompiling from the
  classpath on every message.
- Use JSON Schema Draft 2020-12 or automatic `$schema` detection when generated
  schemas declare 2020-12.
- Wrap numeric/type coercion failures in `TransformMappingException` so invalid
  transform data produces business NACK rather than technical retry/DLQ.
- Treat missing/blank correlation ID as a validation/business failure, not a
  duplicate-correlation failure.

**Done means:**

- Runtime schema validation honors the schema draft emitted in generated
  resources.
- Transform coercion and missing correlation diagnostics route to the right
  NACK/error taxonomy.
- The generated app avoids avoidable schema-compile CPU pressure.

### PR 5 — Engine: Generated-App Quality Gate Regression Fixtures

**Status: Delivered — Engine PR `#145`.**

**Owner repo:** EdgeForge Engine.

**Priority:** P1.

**Complexity:** Medium-Large.

**Task type:** tests/proof.

**Why fifth:** compile-only proof is not enough. The reviewed issues would be
caught by generated-output or runtime fixture checks.

**Required behavior:**

- Add a CRUD generated-app fixture that includes:
  - date field used by API, entity, and staging DDL
  - downstream fixed-width minor-unit amount field
  - list operations returning arrays/lists
  - update operation with request validation
  - staging/EOD handoff
- Add a Kafka router fixture that includes:
  - full downstream response -> upstream reply path
  - optional source field omitted from target output
  - publish failure/correlation cleanup behavior where testable
  - schema validation boundary checks
- Add evidence-trail coverage for generated-app proofs: when KA decisions are
  part of the proof package, accepted/edited generated-artifact decisions should
  populate `evidence-trail.json` by default; empty `evidence_links` should be
  explicitly intentional, not silent.
- Assert generated output would fail on the known Claude/Codex findings and
  passes after PRs 1-4.

**Done means:**

- Future generated-app reviews start from living regression signals, not only
  manual source inspection.
- Proof packages no longer look governed while carrying an unexplained empty
  evidence trail.

### PR 6 — Engine: CRUD EOD Rerun And Batch Topology

**Status: Delivered — Engine PR `#146`.**

**Owner repo:** EdgeForge Engine.

**Priority:** P2.

**Complexity:** Medium-Large.

**Task type:** design may be needed before implementation if behavior changes
external contracts.

**Required behavior:**

- Define rerun semantics for generated EOD jobs: truncate, upsert, run ID, or
  explicit validation failure when the handoff contract cannot support rerun.
- Avoid duplicate primary-key failures on a second batch run over the same
  canonical records.
- Move high-volume EOD paths away from `findAll()` materialization toward
  chunked Spring Batch readers/writers.
- Use temp-file + atomic move or equivalent status handling for file outputs.
- Return or log output file path, record count, created/skipped status, and
  skip reason where appropriate.

### PR 7 — Engine: Kafka Router Operational Semantics

**Status: Delivered — Engine PR `#147`.**

**Owner repo:** EdgeForge Engine.

**Priority:** P2.

**Complexity:** Medium.

**Required behavior:**

- Validate reply destinations against configured source-system allowlists,
  topic mappings, or safe topic-prefix policies.
- Make default-target routing observable through structured logs, metrics, or
  trace output. Default routing is valid when configured, but it must not be
  invisible.
- Externalize duplicate-correlation policy from manifest-generated config
  instead of hardcoding a string literal.
- Rename correlation record fields currently described as schema versions if
  they store schema file paths.
- Remove vestigial null `app.kafka.topics` config from generated YAML.

### PR 8 — Engine: UUID And Persistence DDL Consistency

**Status: Delivered — Engine PRs `#148`–`#153`.**

**Owner repo:** EdgeForge Engine.

**Priority:** P2.

**Complexity:** Small-Medium.

**Required behavior:**

- For server-generated UUID string persistence IDs, emit consistent column
  width such as `VARCHAR(36)` when the Engine owns the DDL.
- Preserve compatibility for caller-supplied arbitrary string IDs where a
  larger length is intentional.
- Keep staging DDL and entity DDL aligned where the same identifier crosses
  canonical/staging boundaries.

### PR 9 — Engine: Kafka Router Performance Polish

**Status: Residual — not yet implemented.**

**Owner repo:** EdgeForge Engine.

**Priority:** P3.

**Complexity:** Small-Medium.

**Required behavior:**

- Avoid rebuilding immutable routing rule lists per message.
- Avoid parsing the same JSON payload multiple times on the happy path.
- Consider per-target or per-topic consumer group naming for better lag
  observability; if this changes deployment semantics, design it first.

### PR 10 — Studio / KS: Source-Contract Conflict Surfacing

**Status: Residual — design pending before implementation.**

**Owner repos:** EdgeForgeStudio + EdgeForgeKnowledgeServer.

**Priority:** P3.

**Complexity:** Medium.

**Task type:** design/UX first.

**Why later:** enum and length mismatches are not always Engine bugs. They
often represent conflicting source evidence that the author must resolve.

**Examples:**

- OpenAPI allows `REJECTED`, but business rules reject it.
- OpenAPI allows `ACTIVE/CLOSED`, while rules include `DORMANT`.
- API max length is 25 while downstream file/staging has length 80.

**Done means:**

- Studio/KA presents these as source-alignment or advisory conflicts with clear
  downstream impact rather than silently choosing one source.

## Items Not In The Immediate Engine Fix Line

The following are real but intentionally not part of PRs 1-5:

- persistent/distributed Kafka correlation store for multi-pod routers
- event-sourced generated app profile
- high-TPS accumulator profile
- full downstream handoff execution topology
- Graph/GraphRAG lineage
- LegacyExtractor Phase 6 integration

These need separate design tracks before implementation.

## Temporary Generated-App Workaround Decision

For reviewed generated apps specifically:

- If an app must be demoed or tested before Engine fixes land, temporary
  generated-app patches are acceptable.
- If the app can wait, prefer Engine fix + regeneration.
- Do not treat app-specific workaround patches as the platform source of truth.

Suggested decision label:

```text
pre-generated-app-quality-gate-v1
```

Use that label for generated app snapshots that predate this hardening
standard.

## Implementation Guardrails

- Keep generator changes generic.
- Do not encode DDA-only rules into the Engine.
- Preserve generated-app runtime independence.
- Keep manifest changes additive within the active dialect. V2-E establishes Engine's
  single-dialect `schema_version: "2.0"`; additions remain optional and additive within `2.0`.
  Studio V2-S and paired-branch plus post-merge V2-X are complete.
  Any further breaking revision requires a separate maintainer-approved paradigm change.
- Add generated-output or runtime fixture tests in the same PR as generator
  behavior changes.
- Use Studio changes only when author intent must be captured; do not add
  Studio UI just to compensate for unsafe Engine inference.

## Future Tracks — Edge-Contract Expansion

The generated-app quality gate roadmap above is **separate from** the
suite-level edge-contract expansion roadmap. Quality-gate residuals (PR 9,
PR 10, partial B-series items) remain tracked in this doc; the edge-contract
expansion roadmap covers broadening the upstream/downstream contract surface.

The strategic anchor for edge-contract expansion is:

- [docs/edge-contract-expansion-roadmap.md](../edge-contract-expansion-roadmap.md)

The Wave 1a design PRs implied by that roadmap (all done):

1. [Downstream Handoff Execution Topology Design](../edgecontracts/downstream-handoff-execution-topology-design.md)
   — defines `embedded` / `staged_external` / `separate_handoff_app` /
   `external_tool_pack` modes.
2. [XML/XSD Contract Support Design](../edgecontracts/xml-xsd-contract-support-design.md)
   — foundational schema substrate for SOAP, ISO 20022, SWIFT MX, MQ XML
   payloads.
3. [SOAP/WSDL Contract Support Design](../edgecontracts/soap-wsdl-contract-support-design.md)
   — done; layered on XSD and scoped to document/literal-wrapped binding.

Current edge-contract status after the v1 closeout smoke:

4. [CSV/Delimited and Fixed-Width File Contract Design](../edgecontracts/csv-fixed-width-file-contract-design.md)
   — implemented for generated CRUD file ingest/output, fixed-width outbound
   trailer generation, and fixed-width/CSV inbound trailer reconciliation.
5. XML/XSD and SOAP/WSDL implementation — implemented for explicit mapped
   XML/XSD ingest/output, SOAP inbound `read_by_id`, and SOAP outbound
   `invoke_by_id`.
6. [Edge-Contract Evidence Trail Metadata Design](../edgecontracts/edge-contract-evidence-trail-metadata-design.md)
   — implemented in Studio export for file, XML/XSD, and SOAP/WSDL metadata;
   final integrated smoke proved the combined package.
7. Avro/Schema Registry design + implementation — still deferred until after
   the v1 docs/status closeout and any chosen file/XML/SOAP hardening polish.

These edge-contract design tracks should not be conflated with the generated-app
quality residuals listed earlier in this doc. Quality residuals are
production-correctness work on existing contract types; edge-contract expansion
adds new contract surface area.
