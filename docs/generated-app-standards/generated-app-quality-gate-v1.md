# Generated App Quality Gate v1

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

> **Status:** Suite-level design standard. Gap register A/B items annotated
> with post-v3.0.0 implementation status (Engine PRs `#141`–`#153`).
>
> **Created:** 2026-05-05. **Updated:** 2026-07-26.
>
> **Source:** Consolidated Claude Suite and Codex Suite review of generated
> CRUD and Kafka router apps, plus the current EdgeForge `v3.0.0`
> generated-app baseline.
>
> **Owner repo:** EdgeForge Engine / Suite docs.

Primary app-specific source material came from generated CRUD and Kafka router
app reviews of the reference proof apps (external-application / a small CRUD app) and a
customer-account Kafka router proof flow. Those remain app-specific records;
this document promotes the reusable findings into suite-level standards.

## Purpose

This document defines the minimum quality gate for a production-grade
EdgeForge-generated Spring Boot application before it can be called a
production-candidate generated app.

The immediate reason for this gate is the generated-app review stream after the
`v3.0.0` baseline. The reviews found real generated-app correctness risks:
transaction/event identity, response-wrapper persistence, CRUD type drift,
fixed-width handoff formatting, DTO/list contract fidelity, Kafka router
publish/correlation ordering, and runtime schema validation fidelity. Those
findings should not remain as one-off app notes. They should become suite-level
generated-app standards so that future Engine, Studio, and generated-app
reviews use the same bar.

This document is deliberately written at suite level:

- It applies to all future generated apps.
- It separates Engine-owned generator fixes from app-specific business rules.
- It gives implementation threads a clear checklist before changing code.
- It prevents a single generated app's docs from becoming the hidden source of
  truth for platform-wide behavior.

## Current Baseline Assumptions

The `v3.0.0` suite baseline generates standalone Spring Boot applications from
reviewed manifests. Generated apps are owned by the adopting organization at runtime and have no
EdgeForge, Studio, Knowledge Assist, MCP, or LegacyExtractor runtime dependency.

Current generated-app strengths include:

- hexagonal package structure
- REST/controller, DTO, service, domain, repository, batch, exception layers
- Flyway migrations with Hibernate validate mode
- `BigDecimal` for money and `java.time.*` for time values
- Bean Validation and generated business-rule hooks
- Spring Batch scaffolding for EOD handoffs
- staging-table and fixed-width file writer scaffolding
- Kafka router V1/V2/V3/V4 validation, transform, NACK, retry/DLQ, and
  correlation scaffolding
- Dockerfile and application config generation
- basic actuator health endpoint
- CRUD, passthrough-router, and `kafka-integration` lanes

The quality gate below does not reduce those strengths. It defines the next
minimum bar for production candidacy.

## Standalone Independence Acceptance

For this standard, **standalone** means that the generated repository can be
extracted from its authoring package and independently built, tested, packaged,
and run. The generated application must not require the EdgeForge Engine,
Studio, Knowledge Assist/Server, MCP, TestBench, or any generation-source
package file at build time or runtime.

The per-generation-change acceptance gate uses one shared Engine verifier from
the generated source boundary through the packaged executable boundary:

1. Generate normally, then copy only the generated repository beneath a fresh
   isolated parent directory.
2. Reject authoring-only package paths such as the manifest, contract/mapping/
   rule directories, Studio project state, and assessment reports.
3. Parse `pom.xml` structurally and reject generator-owned dependencies or
   plugins, local modules, system-path dependencies, and parent-filesystem
   lookup.
4. Require every `db/schema-baseline.json.generated_source_files` entry to
   exist and carry generated ownership; developer-owned service subclasses must
   not appear in that inventory.
5. Run `mvn clean verify`, inspect the executable JAR's `BOOT-INF/lib`
   boundary, start the JAR from the isolated repository, and require an
   `{"status":"UP"}` actuator response.
6. Build the container with the isolated repository as its only Docker context
   and require both a configured non-root user and a nonzero effective UID from
   a one-off container execution.

Generated provenance text, ownership markers, logical source-contract
references, package-relative Evidence Trail metadata, and the current
application's own `com.appbuilder.<context>` Java namespace or declared Maven
project coordinate are **not** runtime dependencies. The namespace is derived
from the generated application's own source tree, so a valid context remains
valid even when its name overlaps a suite-related word. Absolute author-machine
paths and copied authoring-package files are prohibited, but informational
references such as `Source manifest: app-definition.yaml` are allowed. Git
administrative metadata is outside the generated-artifact content scan.

This acceptance definition does not claim complete contract-conformance test
depth for every generated application. Per-app contract tests, SBOM generation,
and deeper dependency/license evidence remain separately tracked quality and
handover work.

Current per-PR coverage runs the full isolated build, test, executable-JAR
health, and Docker proof for a representative CRUD app. Passthrough-router and
Kafka-integration outputs receive the same isolated source/dependency/JAR
inspection plus `mvn clean verify`. Kafka runtime parity remains in the
broker-backed L5 acceptance path; this gate does not invent or silently skip a
broker to make an isolated Kafka runtime appear healthy.

## Non-Goals

This document does not:

- require generated apps to use EdgeForge at runtime
- require Talend, Ab Initio, or any external ETL product
- require event sourcing as the default persistence model
- require one generated app to combine CRUD, REST passthrough, Kafka, files, and
  every batch topology
- turn every app-specific business rule into an Engine feature
- replace app-level domain implementation plans
- implement the Engine fixes described here

## Horizon Definitions

Use these horizons consistently in reviews and implementation prompts.

| Horizon | Meaning |
|---|---|
| `NOW` | P0/P1 correctness blocker for a generated app that will handle real data. |
| `BEFORE PROD` | Required before production cutover, but can be phased after initial proof. |
| `BEFORE SCALE` | Required before high TPS, high volume, or large batch windows. |
| `ENGINE ROADMAP` | Generic generator improvement that should benefit all future apps. |
| `FUTURE / OPTIONAL` | Valuable hardening or architecture evolution, not required for initial production candidacy. |

## Ownership Definitions

| Category | Owner | Meaning |
|---|---|---|
| Engine generic | EdgeForge Engine | Generator behavior that applies to all apps. |
| Studio + Engine | EdgeForgeStudio + Engine | Manifest authoring or UX setting plus generation behavior. |
| Generated app business logic | App team / generated-app repo | DDA or domain-specific business rules that the Engine cannot infer. |
| Runtime / deployment | The adopting organization's platform team | Kubernetes, secrets, gateways, observability backends, enterprise deployment choices. |
| Design-first | Suite docs first | Needs a design doc before implementation. |

## Executive Quality Gate

A generated app is production-candidate only when the following are
true.

### Contract And Persistence Integrity

- [ ] Every persisted entity has a correct persistence identity.
- [ ] Event/transaction rows do not use a parent foreign key as their primary
      key unless the manifest explicitly models a true one-to-one relationship.
- [ ] Business IDs such as `transaction_id` are unique where idempotency or
      duplicate detection requires uniqueness.
- [ ] API request/response wrapper fields are not persisted as domain columns.
- [ ] Generated database columns represent domain state, not pagination
      envelopes or transport-only wrappers.
- [ ] Server-owned fields are not caller-controlled on create/update.
- [ ] Staging/export tables have a primary key or equivalent run/row identity.
- [ ] Downstream handoff fields come from the explicit handoff contract, not
      from all required entity fields by inference.
- [ ] Temporal fields are represented consistently across source contract,
      Java entity/DTO types, Flyway DDL, staging writers, and downstream
      handoffs. `format: date` / SQL `DATE` should not drift to `String` /
      `VARCHAR` without an explicit contract decision.
- [ ] Generated DDL column sizes align with known generated ID strategies when
      the Engine owns both sides of the contract, for example UUID string IDs
      using a 36-character column instead of an arbitrary 255-character width.

### API And DTO Correctness

- [ ] REST routes, methods, path variables, query parameters, and request bodies
      match the upstream contract.
- [ ] Create/update/state-transition operations use the correct service
      semantics and do not silently fall back to generic CRUD behavior when a
      specific operation was declared.
- [ ] List operations are pageable when the contract marks them pageable.
- [ ] Filtered list operations do not return all rows when the route declares a
      filter such as `accountId`.
- [ ] Computed reads either have real derived-read semantics or are explicitly
      blocked/TODO-marked from production use.
- [ ] Controllers do not expose JPA entities as public API request/response
      bodies when explicit request/response DTOs exist.
- [ ] Update operations accept validated request DTOs instead of persistence
      entities.
- [ ] Error responses use a stable schema with error code, message, details,
      timestamp, correlation ID, and retryability where appropriate.

### Transactional Consistency

- [ ] Related database mutations for one business operation occur inside one
      local transaction where the app owns the same database boundary.
- [ ] Account balance updates and transaction-row inserts cannot commit
      independently.
- [ ] Cross-system side effects use outbox, idempotent retry, or compensation;
      generated apps do not claim XA/2PC support unless explicitly designed.
- [ ] Retry semantics distinguish business validation failures from technical
      failures.
- [ ] Kafka/router producers confirm broker send completion before source
      messages are acknowledged or correlations are completed.
- [ ] Kafka/router correlation records are cancelled or rolled back on publish
      failure so retries do not become false duplicate-correlation failures.

### Idempotency And Duplicate Protection

- [ ] Transaction posting has an idempotency key or business transaction ID.
- [ ] Customer/account creation retries have business-key uniqueness or a
      declared idempotency strategy when required by the domain.
- [ ] Duplicate API calls return a deterministic response instead of creating
      duplicate state.
- [ ] Batch/EOD reruns do not duplicate downstream rows or file records without
      explicit run identity.

### Batch, File, And Handoff Readiness

- [ ] EOD jobs have a clear source of truth: canonical tables, staging/export
      tables, or an external ETL contract.
- [ ] File layouts are generated from explicit downstream contracts.
- [ ] Fixed-width fields that explicitly represent minor-unit amounts are
      formatted as integer minor units with contract-defined padding, not as
      raw decimal strings.
- [ ] File generation includes control totals or a documented follow-up when
      files are business-critical.
- [ ] Batch jobs have run identity, restart semantics, and failure handling
      before production cutover.
- [ ] Spring Batch metadata schema initialization is explicit for the target
      runtime profile. The final edge-contract v1 smoke required
      `--spring.batch.jdbc.initialize-schema=always`; treat first-class config
      polish as a v1.1 hardening item.
      For fresh Boot 4.1 previews, Flyway instead owns Batch 6 metadata and
      competing Batch initialization is disabled; never set `always` there.
      See the [preview boundary](boot41-jobless-preview.md). The preceding
      smoke observation remains historical, not preview startup guidance.
- [ ] Staging tables are suitable for downstream ETL consumption: primary key,
      business date/run ID where needed, and status/reconciliation metadata
      where needed.

### Audit, Retention, And Data Governance

- [ ] Created/updated metadata is server-owned.
- [ ] Audit metadata captures who/what/when for mutable business records.
- [ ] Records are not physically deleted unless the domain explicitly
      permits it; soft delete or retention policy is defined.
- [ ] PII and sensitive data are not written to logs by default.
- [ ] Data archival/partitioning is planned for high-volume transaction tables.

### Observability And Operations

- [ ] Liveness and readiness signals are distinct enough for deployment probes.
- [ ] Metrics hooks are available or explicitly deferred.
- [ ] Structured logs include correlation ID and exclude sensitive fields.
- [ ] Build/test/compile gates are present for generated-app delivery.
- [ ] Generated proof packages include `evidence-trail.json` by default. When
      KA decisions contributed to generated artifacts, accepted/edited evidence
      links are populated; empty evidence trails are explicitly explained.
- [ ] Runtime configuration is externalizable by environment.
- [ ] Runtime JSON Schema validators cache compiled schemas and honor the
      schema draft declared by generated schema files.
- [ ] Kafka router default-target routing, NACKs, DLQs, and correlation
      lifecycle events are visible through logs, metrics, or trace output.

### Security And Secrets

- [ ] Datasource credentials and API secrets are not hard-coded.
- [ ] Security/authentication hooks are generated or explicitly owned by the
      deployment platform.
- [ ] TLS/mTLS, gateway, or platform ingress ownership is documented.
- [ ] Vault or secret-manager integration is supported through config hooks or
      deployment convention, even if not generated as a product dependency.

### High-TPS Readiness

- [ ] Hot accumulator fields such as account balance are not protected only by
      optimistic locking under high contention.
- [ ] Optimistic locking is limited to low-contention metadata or status fields.
- [ ] Atomic SQL update patterns are used for accumulator fields when a single
      row may receive high write volume.
- [ ] Connection pool, indexes, rate limits, and query plans are reviewed before
      scale.

## Enriched Gap Register

### A. Engine Bugs With Temporary App Workaround Option

| ID | Gap | Category | Horizon | Complexity | Rationale | Post-v3.0.0 Status |
|---|---|---|---|---|---|---|
| A1 | Transaction/event entity may use parent `accountId` as primary key when no explicit identity override is supplied | Engine generic / app workaround | `NOW` if app used; `ENGINE ROADMAP` as root fix | Medium | One account can physically have only one transaction row; `findById` and update semantics become inverted. | **Implemented** — Engine PR `#138` (root fix); Studio/KS identity-role review/export follow-up through Studio `#154`–`#159` and KS `#25`–`#28` |
| A2 | Response-wrapper fields such as `transactions`, `currentPage`, `pageSize`, `totalElements`, `totalPages` may be persisted as entity columns | Engine generic / app workaround | `NOW` if app used; `ENGINE ROADMAP` as root fix | Medium-High | Transport/page envelope fields corrupt the domain model and downstream handoffs. | **Implemented** — Engine PR `#138` |
| A3 | Kafka router response publish, producer send confirmation, and correlation cleanup are not yet proven as durable generated-output invariants | Engine generic | `NOW` for router apps | Medium | A router can acknowledge input or complete/carry correlation state before broker publish succeeds, causing message loss or false duplicate handling. | **Implemented** — Engine PR `#142` |
| A4 | CRUD temporal fields can drift between source schema, Java types, Flyway DDL, and staging DDL | Engine generic | `NOW` if app uses date handoffs | Medium | A field such as `openedDate` can be generated as `String`/`VARCHAR` while staging requires `DATE`, creating runtime JDBC fragility. | **Implemented** — Engine PR `#141` |
| A5 | Fixed-width minor-unit amount fields can emit decimal strings instead of integer minor units | Engine generic / contract transform | `NOW` if app emits files | Medium | Downstream files often expect zero-padded minor-unit integers; raw `BigDecimal.toString()` breaks the handoff contract. | **Implemented** — Engine PR `#141` |

### B. Engine Improvements Required Before Production

| ID | Gap | Category | Horizon | Complexity | Rationale | Post-v3.0.0 Status |
|---|---|---|---|---|---|---|
| B1 | Staging tables lack generated row identity when the contract DDL omits it | Engine generic | `BEFORE PROD` | Low | EOD reruns and ETL consumers need row identity for restart, reconciliation, and duplicate control. | **Implemented** — Engine PRs `#148`–`#153` (staging run identity when the DDL contains the expected columns). Tiny smoke staging tables may still lack full production restart/idempotency semantics; treat as v1.1 hardening, not a v1 blocker. |
| B2 | Server-owned timestamp fields can remain caller-settable | Engine generic | `BEFORE PROD` | Low | `creation_date` and similar fields should be owned by the server or persistence lifecycle. | **Partial** — `@CreationTimestamp`/`@UpdateTimestamp` present; caller-settable protection uncertain |
| B3 | Some list endpoints remain unbounded or predicate-unaware | Engine generic | `BEFORE PROD` | Medium | `findAll()` is unsafe for production tables; filtered routes must use predicate-aware queries. | **Partial** — DTO/list fidelity improved via `#143`/`#150`; predicate-aware filtered query generation remains pending (see D10) |
| B4 | Stable error contract is not yet a named quality gate | Engine generic | `BEFORE PROD` | Low | Consumers need stable error code, message, details, correlation ID, timestamp, and retryability. | **Partial** — baseline `ErrorResponse.java` generated; full error contract (stable error code, details, correlation ID, retryability) still pending |
| B5 | Liveness/readiness split is not a first-class generated-app standard | Engine generic | `BEFORE PROD` | Low | Kubernetes and enterprise deployment gates need separate probe semantics. | **Partial** — `/actuator/health` HEALTHCHECK present; separate liveness/readiness endpoints not yet split |
| B6 | Structured logging/MDC is not yet generated as a standard hook | Engine generic | `BEFORE PROD` | Low | Operational support needs correlation across APIs, batch runs, and downstream handoffs. | **Partial** — MDC present in Kafka lane only; absent in CRUD lane |
| B7 | Secrets/config externalization is not yet a named generation standard | Engine generic | `BEFORE PROD` | Low | Datasource credentials and secrets must be environment/platform supplied. | **Implemented** — enterprise PostgreSQL profiles require `SPRING_DATASOURCE_USERNAME` / `SPRING_DATASOURCE_PASSWORD` with no `postgres` fallback; legacy H2 dev profile unchanged |
| B8 | CI/build pipeline descriptor is optional | Engine generic | `BEFORE PROD` | Low | Production-candidate generated apps should include an obvious build gate. | **Missing** — no CI config generated |
| B9 | Audit metadata baseline needs stronger production semantics | Engine generic | `BEFORE PROD` | Medium | Created/updated/deleted metadata and correlation trail should be explicit. | Partial — `emit_audit` flag and timestamps present; fuller audit semantics not confirmed |
| B10 | CRUD controllers can bypass generated DTO services and expose persistence entities for GET/LIST/PUT | Engine generic | `BEFORE PROD` | Medium | Public API shape drifts from the manifest and validation can be skipped on update paths. | **Implemented** — Engine PR `#143` |
| B11 | Runtime JSON Schema validation can ignore generated schema draft and recompile schemas per message | Engine generic / Kafka router | `BEFORE PROD` | Medium | Draft mismatch is a contract fidelity gap; recompilation is avoidable hot-path CPU. | **Implemented** — Engine PR `#144` |
| B12 | Kafka router error taxonomy can misclassify validation/transform failures as duplicate or technical failures | Engine generic / Kafka router | `BEFORE PROD` | Low-Medium | Misleading NACK codes and retry/DLQ behavior slow operations and can create unnecessary retries. | **Implemented** — Engine PR `#144` |

### C. Studio + Engine Design-First Work

| ID | Gap | Category | Horizon | Complexity | Rationale |
|---|---|---|---|---|---|
| C1 | Optimistic locking is not manifest-selectable by entity/field role | Studio + Engine | `BEFORE PROD` for metadata entities | Low-Medium | Prevents lost updates for low-contention metadata, but must not be applied to accumulator fields. |
| C2 | Atomic SQL accumulator pattern is absent | Studio + Engine design-first | `BEFORE SCALE` | Medium | Required for high-TPS account balance posting without optimistic-lock retry storms. |
| C3 | Spring Security/auth skeleton is not manifest-selectable | Studio + Engine | `BEFORE PROD` | Medium | Enterprise apps need a clear auth integration surface without EdgeForge runtime dependency. |
| C4 | H2/PostgreSQL/profile selection should be explicit in Studio for production apps | Studio + Engine | `BEFORE PROD` | Low-Medium | Authors should choose runtime profile deliberately; Engine emits matching config. |
| C5 | HikariCP/high-TPS runtime tuning is not modeled | Studio + Engine / runtime | `BEFORE SCALE` | Low-Medium | Defaults are not enough for 1000 TPS hot-row scenarios. |
| C6 | Hot-query indexes are not a generated standard | Studio + Engine | `BEFORE SCALE` | Low | Transaction IDs, account IDs, business dates, and staging run columns need indexes. |
| C7 | Evidence trail population is not yet enforced as default proof coverage | Studio + KS + Engine proof | `BEFORE PROD` for governed demos | Medium | A generated app can appear governed while `evidence_links` is empty; proof packages should either carry accepted/edited generated-artifact evidence or explain why no evidence applies. |

### D. Generated App / Domain-Specific Work

| ID | Gap | Category | Horizon | Complexity | Rationale |
|---|---|---|---|---|---|
| D1 | Balance update and transaction insert must share one transaction boundary | Generated app business logic | `NOW` for transaction apps | Medium | Partial commit creates inconsistent balances. |
| D2 | Idempotency beyond transaction posting may be needed | Generated app business logic | `BEFORE PROD` | Medium | Customer/account creation retries may need business-key uniqueness or request idempotency. |
| D3 | Soft delete/retention policy is undefined | Generated app business logic | `BEFORE PROD` | Low | Records are rarely hard-deleted. |
| D4 | Request validation may need domain-specific precision/range/state checks | Generated app business logic | `BEFORE PROD` | Low-Medium | Amount precision, currency-account compatibility, earmark format, and debit/credit status gates are domain-specific. |
| D5 | Batch production behavior needs app-level policy | Generated app business logic | `BEFORE PROD` | Medium | Restartability, skip limits, duplicate prevention, and reconciliation depend on business policy. |
| D6 | DDA-specific KYC and account status gates are not Engine-generic | Generated app business logic | `BEFORE PROD` | Low | These rules belong in app/domain work or evidence-backed authoring, not a generic generator assumption. |
| D7 | Business ID sequences/composite IDs may be domain-specific | Generated app business logic / Studio + Engine where generic | `BEFORE PROD` | Medium | Customer/account numbering strategy should be explicit rather than inferred. |
| D8 | Source-contract enum or length conflicts need human resolution | Studio + KS advisory / generated-app business logic | `BEFORE PROD` | Medium | OpenAPI, rules, staging DDL, and EOD layouts can disagree; Engine should not silently choose one source of truth without reviewed intent. |

### E. Optional / Runtime Hardening Backlog

| ID | Gap | Category | Horizon | Complexity | Rationale |
|---|---|---|---|---|---|
| E1 | Service interfaces are not emitted | Engine optional | `FUTURE / OPTIONAL` | Low | Useful architecture polish, not a production blocker. |
| E2 | OpenAPI/springdoc output is not standard | Engine optional | `BEFORE PROD` or `FUTURE / OPTIONAL` | Low-Medium | Useful for consumers and demos, but correctness comes first. |
| E3 | Rate limiting/throttling hooks are absent | Runtime hardening | `BEFORE SCALE` | Medium | Protects hot accounts and downstream systems. |
| E4 | PII log redaction needs explicit policy | Runtime hardening | `BEFORE PROD` | Low | Structured logging must not leak customer/account data. |
| E5 | Distributed boundary guidance is not yet encoded in generated docs | Architecture guidance | `BEFORE PROD` | Low | Local transaction vs outbox/compensation boundary must be explicit. |
| E6 | Data archival/partitioning is not modeled | Runtime hardening | `BEFORE SCALE` | Medium | Transaction tables grow without bound. |
| E7 | Kubernetes/Grafana/ELK/Jaeger deployment hooks are optional | Runtime hardening | `FUTURE / OPTIONAL` | Low-Medium | Valuable enterprise integrations, but deployer-owned. |
| E8 | Event sourcing is not a generation profile | Engine roadmap | `FUTURE / OPTIONAL` | High | It is a separate architecture profile, not a checkbox on CRUD. |

## High-TPS Decision Record

The review evaluated three patterns for a 1000 TPS transaction-posting scenario
against a single account.

### Optimistic Locking

Good for:

- low-contention metadata
- customer profile updates
- account status changes

Bad for:

- account balance accumulator fields under heavy contention

Decision:

- Use optimistic locking for metadata/status entities only when selected.
- Never rely on `@Version` alone for a hot accumulator field.

### Atomic SQL Accumulator

Pattern:

```sql
UPDATE account
SET balance = balance + :delta
WHERE account_id = :id
  AND status IN (...)
```

Required service rule:

- The atomic update and transaction row insert must run inside the same local
  `@Transactional` boundary.
- If either fails, both must roll back.

Decision:

- This is the preferred future high-TPS CRUD pattern.
- It needs a dedicated high-TPS entity profile design before implementation.

### Event Sourcing

Good for:

- append-only ledgers
- replayable projections
- event-driven core accounting designs

Decision:

- Treat event sourcing as a future separate generation profile.
- Do not add it as a simple field/entity checkbox on the current CRUD generator.

## Current-State Interpretation Of The external-application Findings

The external-application generated app was a manual test output, not a suite baseline app.
The cleanest path is to fix the Engine/generation behavior and regenerate rather
than hand-patch that generated app unless a demo urgently requires it.

Use this interpretation:

- If the generated app will handle real data before Engine fixes land, apply
  temporary app workarounds.
- If not, fix the Engine and regenerate.
- Keep DDA-specific rules in the generated-app domain plan.
- Promote only generic generator behavior into Engine.

## Recommended Minimum Implementation Order

1. Fix CRUD fixed-width minor-unit formatting and temporal type propagation.
2. Verify/fix Kafka router response publish, producer confirmation,
   correlation cleanup, and optional-null transform behavior.
3. Fix CRUD DTO/list/controller contract fidelity.
4. Harden Kafka router schema validation and business error taxonomy.
5. Add generated-app quality-gate regression fixtures and evidence-trail
   coverage for both CRUD and Kafka router outputs.
6. Add EOD rerun/batch topology hardening and staging-table run identity.
7. Design high-TPS entity profile before implementing accumulator support.
8. Design downstream handoff execution topology before expanding file/batch
   generation modes beyond the initial embedded writer model.

## What Belongs Where

### Engine Generic

Belongs in the Engine when the behavior applies to any generated app:

- entity identity selection safeguards
- response-wrapper exclusion
- staging PK defaults or validation
- server-owned timestamp lifecycle
- generated error contract
- liveness/readiness config
- structured logging hooks
- paginated and predicate-aware list generation
- generated migration/index support

### Studio + Engine

Belongs in Studio + Engine when the author must choose a generation policy:

- entity type or event/transaction classification
- optimistic locking selection
- accumulator field designation
- runtime profile selection
- auth mode/security skeleton
- idempotency/unique key declaration

### Generated App

Belongs in app-specific code/docs when it is domain knowledge:

- KYC gate
- DDA account status rules
- customer/account number formatting
- transaction idempotency semantics
- EOD business calendar and reconciliation
- consumer-specific fixed-width file content rules

### Runtime / Platform

Belongs to the adopting organization's deployment/platform layer:

- gateway/WAF/rate-limit products
- Vault/secret manager binding
- TLS/mTLS infrastructure
- Kubernetes manifests beyond generated hooks
- observability backend deployment

## Review Checklist For Future Generated Apps

Use this checklist during generated-app reviews.

### Entity Model

- [ ] Does every entity have exactly one persistence identity?
- [ ] Are event/transaction entities using a surrogate row ID plus business key?
- [ ] Are parent references modeled as foreign keys, not accidental primary keys?
- [ ] Are response envelopes excluded from persistence?
- [ ] Are generated IDs, caller-supplied IDs, identity columns, and sequences
      explicit?

### API Surface

- [ ] Are declared operations preserved with correct method/path/body semantics?
- [ ] Are read-only/computed surfaces honest about unsupported writes?
- [ ] Are list operations pageable or intentionally bounded?
- [ ] Are query/path filters actually applied?
- [ ] Do controllers use generated request/response DTOs instead of exposing
      persistence entities when a contract DTO exists?
- [ ] Do update paths use request DTOs plus validation?
- [ ] Are error responses stable and consumer-safe?

### Persistence

- [ ] Do Flyway migrations match entity fields and relationships?
- [ ] Do OpenAPI/JSON Schema date formats and staging DDL date columns map to
      Java temporal types consistently?
- [ ] Do staging tables have row identity and run metadata where needed?
- [ ] Are unique constraints generated for idempotency/business keys?
- [ ] Are indexes generated or documented for hot paths?
- [ ] Are server-owned timestamps protected from callers?

### Batch / Handoff

- [ ] Is the file layout sourced from the downstream contract?
- [ ] Are minor-unit amount fields converted and padded according to the file
      contract?
- [ ] Is the staging/export table contract explicit?
- [ ] Is the source of file generation clear: canonical table, staging table, or
      external ETL?
- [ ] Is EOD rerun behavior defined?
- [ ] Are control totals/reconciliation requirements captured?

### Kafka Router

- [ ] Does the response path publish the transformed upstream reply record to
      the captured reply destination?
- [ ] Are Kafka producer sends confirmed before listener ack or correlation
      completion?
- [ ] Are correlation records cancelled/rolled back on publish failure?
- [ ] Are optional absent fields omitted or explicitly made nullable/defaulted
      before V2/V4 validation?
- [ ] Are JSON Schemas cached and validated against the declared draft?
- [ ] Do transform coercion failures and missing correlation IDs produce
      business NACKs instead of technical retries or misleading duplicate
      errors?
- [ ] Is default-target routing observable when it is used?

### Operations

- [ ] Are health probes adequate for deployment?
- [ ] Are logs structured and PII-safe?
- [ ] Are metrics hooks present or explicitly owned by platform?
- [ ] Are secrets externalized?
- [ ] Is a build/test pipeline present?

## Open Design Follow-Ups

The following should be separate design docs or design refreshes:

- High-TPS entity profile design.
- Downstream handoff execution topology design.
- KA persistence/reopen hardening.
- LegacyExtractor UX v3 refresh.
- Event-sourced generated-app profile.
