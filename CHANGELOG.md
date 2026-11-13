# Changelog

All notable changes to the **EdgeForge Engine** (`appbuilder`) are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the repo tags **suite baselines** ([SemVer](https://semver.org/)). This is the
**Engine-local** changelog; Studio, Knowledge Server / Assist, and TestBench keep
their own.

> **Honest scope.** The current manifest dialect is `schema_version: "2.0"`;
> new concepts are optional, backward-compatible extensions within that dialect.
> Historical entries retain their then-current schema and evidence scope.
> Edge-contract **v1 is closed and proven** per the
> [readiness matrix](docs/edgecontracts/edge-contract-handoff-readiness-matrix.md);
> **SOAP is bounded** (`read_by_id` / `invoke_by_id`) and broader SOAP operations
> plus further families are **parked**. Entries are reconstructed from git tags +
> commit ranges; design-only items are labelled as such. Maintainer publication
> authorization (G1), IdP / SSO wiring, and the optional-AI production gate (KS-B5)
> are **not** resolved here.

## [Unreleased]

## [5.0.0] — source preparation

This section collects the v5 source changes. Selected-source technical acceptance
is recorded in the [November 10 results](docs/handover-evidence/v5-acceptance-2026-11-10.md),
separately from tag creation and publication. No public release date is assigned
by this section; consult verified tags and Release records for publication status.

- Set the Engine package/runtime version to 5.0.0 in the completed private
  `edgeforge-suite/EdgeForge` import. Align constrained local setup and the later
  source-selection, pairing and acceptance sequence; preserve the pending
  candidate descriptor, historical baseline and public-launch gates.

- Clarify independent community maintenance and optional self-managed enterprise
  adoption; use neutral publication-authorization wording in preparation
  guidance. Publication prerequisites, license terms and dated proof results
  remain unchanged.

- Correct the reference-only joserfc pin from 1.7.5 to qualified 1.7.6 for
  GHSA-9pg5-8c7x-5hfx; preserve the advisory-range discrepancy and prior evidence.
  Other 75 pins, direct requirements, Python 3.11 floor and generated applications
  are unchanged. Refresh coherent current audit/SBOM/license/provenance records.

- Emit SQL column defaults before NOT NULL/CHECK constraints in fresh CREATE TABLE
  and newly generated additive ADD COLUMN migrations, preserving values, escaping,
  ranges, nullability and identity/primary-key behavior. Fresh Workspace/Item
  Java 17/H2 proof and direct additive H2 checks cover defaults and constraints;
  existing generated migrations and real databases are not automatically repaired.

- Replace the external developer sample and related tracked fixture with an
  independently authored Workspace/Item package; preserve read/write, identity,
  constraint, relationship and independence regression coverage. Publish neutral
  editorial historical summaries, complete Open Banking attribution and review
  three retained technical designs before removing stale confidentiality labels.
  Existing private evidence/advisory exclusions and publication gates remain;
  no generator behavior, dependency or broad M2/acceptance change.

- Correct the reference lock to Authlib 1.9.1 and dnspython 2.9.0 and adopt the
  approved Python 3.11+ minimum for Engine v5. FastMCP is no longer conditional
  on an older interpreter. Preserve dated Python 3.10 evidence; generated Java
  applications do not require migration. Current audit evidence is refreshed
  separately from unchanged Maven/image proof; no M2 or publication clearance.

- Adopt approved v5 source-release policy: Apache-2.0/NOTICE/DCO, fresh private
  repository cutover and disclosed M2 limitations with retained release checks.
  Pairing supports strict archive/new cohorts; the no-tag bootstrap is scoped
  to the new Engine repository. Public exposure requires maintainer authorization
  and reporting-route verification; no generated behavior or historical evidence changes.

- Correct the Python reference audit with FastMCP 3.4.10 and OpenTelemetry API
  1.45.1, preserving the then-supported Python 3.10 and all other selected versions. Retain coherent
  current evidence and the immutable October20 snapshot. Audit failures now
  identify package/version/advisory IDs without changing coverage or exit rules.
  Offline generation comparisons justify reusing the dated clean-plugin proof;
  no manual image/Maven campaign or M2/risk clearance is implied.

- Scope Plexus Utils 4.0.3 to the inherited Maven Clean Plugin through the shared
  build-only policy; preserve application dependencies and base references.
  Include `requirements-lock.txt` in both generated-app workflow path filters.
  Retain a dated, four-builder correction overlay without rewriting historical
  OPEN evidence or claiming M2/security clearance.

- Correct the reference Python audit finding with a supported constrained
  dependency refresh and coherent fresh Python evidence. Add an identity-complete
  Engine M2 decision index and precise OPEN owner actions; clarify retained
  source-label and replay-fingerprint boundaries without rerunning image/Maven
  campaigns or accepting residual risk. M2 and release clearance remain open.

- Keep complete Noble advisory bodies archive-only in a clean replacement
  history; retain reviewable range/source/applicability projections, portable
  interpreter provenance, verified replay boundaries and a maintainer tool map.
  Original evidence and findings remain unchanged; no publication or clearance.

- Pin generated Noble builder/runtime multi-platform indexes through one versioned
  reference map; scope build-only dependency corrections to proven compiler,
  resources and packaging realms without changing Boot or application policy.
  Retain historical evidence acceptance and the separate clean-plugin Plexus
  residual. Retain the new 30-case/60-stage assessment as a compact core and
  verified private archive, with historical/current/vendor reconciliation and
  separate emitted versus proof-supplied test accounting. Remaining findings
  stay explicit; no M2, security or release clearance is implied.

- Retain the byte-identical October 17 generated-image evidence core in Git with a checksummed private full archive, storage guidance and a read-only split verifier; findings remain OPEN.

### Assessment

- Add bounded generated build/runtime image collection and integrity checks,
  declared Java 17/21 `linux/amd64` coverage and local scanner provenance. Keep
  findings and extraction/feed limitations separate from completed proof.
  Add ordinary Boot-launch Kafka/LZ4 default evidence, distinct from forced-native
  proof, and explicit historical/vendor Maven reconciliation. Correct the Jackson
  3.1.5 fix-floor and inclusive affected-range wording without rewriting raw
  source receipts. No dependency/base-image change, risk acceptance or M2 clearance.
  Fail closed with exit 2 on unexpected image-tool CLI errors; reject publication
  with residual recorded host paths, including after moving retained proof.
  Existing dated image evidence remains unchanged.

### Corrected

- Include actually emitted fixed demo/batch controller mappings in REST collision
  preflight, including runtime-disabled demo mappings and equivalent placeholder
  names. Refuse conflicts before generate/plan/apply output mutation, without
  reserving absent controllers or changing generic CRUD or Batch behavior.
  Record the adopted v5 gateway-exposure policy: selected operations are not the
  entire API; expose only explicitly approved methods/paths and block unapproved
  CRUD/demo/batch endpoints and direct-port bypass. Document the Engine-owned
  post-v5 `int32` transport range-enforcement limitation; integer bindings remain
  unchanged and adopters needing those bounds must validate before effects.

- Refuse unsupported selected REST writes before output mutation: preserve
  faithful routes, scalar inputs and compatible success status/body; detect
  emitted-route collisions including fallbacks. Headers/query values reach
  preserved developer methods and console requests. Required payment headers
  are transport support, not replay protection or signature verification.
  Explicit payment mappings avoid duplicate canonical/DTO accessors while
  retaining its flat adapter contract and persistence identity.
  Mapped DTO fields/getters/setters share explicit wire names without unintended
  JavaBean case aliases; canonical distinctions and scalar types are preserved.
  Preserve a passthrough POST's single declared 200/202 success and JSON/empty
  response shape, including the shipped insurance sample's empty 202. Retained
  contracts also change CRUD baseline manifest hashes under fresh regeneration.

- Validate selected CRUD GET contracts across get-by-ID, computed and collection
  dispatch paths before output mutation. Refuse foreign/business-key/nested
  lookups, ignored selectors and unfaithful read routes; preserve own-ID,
  unfiltered and bounded pageable reads. Ordinary OpenAPI headers require
  explicit `x-edgeforge-read-input-role` metadata/rate-limit classification;
  special security/media headers follow OpenAPI handling without generated auth.
  Bind selected GETs to their returned entity even with an unmapped request
  sample, closing the preflight bypass before generate/plan/apply can touch output.
  Classified optional read headers are passed through generated service methods;
  the shipped wire-transfer `findById` signature now includes its five optional
  headers, so pre-v5 developer calls must supply those arguments.

- Refuse CRUD operations classified by Engine as `computed_read` without a
  supported path-parameter ID lookup
  before creating or updating application output, replacing the arbitrary
  first-record/TODO fallback with an operation-specific diagnostic. Require one
  same-name, same-type parameter bound to the resolved entity ID directly after
  its Engine collection route (including generic `id` fields); refuse owner,
  nested, wildcard/matrix-route and ignored query/header-filter lookups instead
  of selecting the last parameter. Planning blocks the same unsupported input.
  These refusals and the removal of first-record/last-parameter fallbacks apply
  only to that branch. Supported computed-ID reads retain their implementation;
  unchecked contract-path `get_by_id`, list filtering and route preservation
  remain [open adjacent limitations](docs/external-review-backlog.md#xr-1-adjacent-operation-audit).
  Full derived-query semantics are not supplied.
- Retained Boot 4.1.1 with generated dependency policy `ef-v5-maven-1`:
  Tomcat 11.0.26, Jackson 3.1.7/2.21.7 and explicit Kafka-only LZ4 1.11.4.
  Retired the three preview aliases, replacing captured old-byte gates with
  current-policy determinism and same-policy regeneration. Existing runtime,
  security, Batch date/history and public-query integrity checks remain.
  Added native LZ4 container roundtrip proof for Java 17/21 linux/amd64 and a
  default Java Batch context-serialization assertion. Pre-v5 migration is
  unsupported; no vulnerability-risk acceptance or M2 completion is implied.

### Added

- Extended the opt-in Boot 4.1.1 profiles to plain/request-reply/retry-DLQ Kafka,
  routers and mixed routes using Jackson 3 and a compatible router validator.
  Added actual broker contract checks and clean-base default-output proof.
  Boot 3 defaults, at-least-once and in-memory correlation limits remain;
  this does not switch defaults, provide migration or complete M2.
- Added experimental, explicitly selected Spring Boot 4.1.1 profiles for fresh,
  jobless CRUD/SOAP and passthrough applications on H2/Java 17 and PostgreSQL/
  Java 17 or 21. Existing Spring Boot 3 defaults remain unchanged; Batch/M5a,
  job-bearing file/staging and Kafka preview inputs fail closed. This does not
  complete Maven remediation or M2, or authorize existing-database migration.
- Added a Python 3.11 Linux reference dependency lock, complete-inventory SBOM/
  license/audit evidence, and a fail-closed Python dependency audit in the
  existing CI test job. This closes the Engine Python slice only; generated-app
  Maven, images and overall M2 remain separate.
- Added per-generated-app Maven SBOM and live vulnerability assessment tooling,
  resolved-inventory coverage checks, and a bounded baseline with open findings.
  This does not upgrade dependencies, add a live CI gate, or complete M2.
- Added one explicit, machine-readable Engine/Studio/KS release-candidate pin set and a standalone
  read-only preflight that validates the descriptor, intended repository roots, exact commits, and
  clean worktrees. A matching report is revision selection only; it does not establish integration,
  security, or release acceptance.
- Added the manual domain sample-pack acceptance driver. Given an explicit Studio
  checkout, it exports the three maintained packs twice through Studio's production
  restore/export path and proves manifest validation, warning-free generation,
  applicable harness results, profile-pinned Maven builds, standalone generated-app
  independence, repository confinement, and narrowly normalized export determinism.

### Changed

- Promoted the three ordinary profiles to the delivered Spring Boot 4.1.1 path
  for fresh applications; preview IDs remain compatible aliases. Known Boot 3,
  Batch 5, unvalidated Boot patches or ambiguous packages refuse generate/plan/apply
  before writes using retained POM/schema evidence. Same-line regeneration preserves immutable SQL
  and original internal-schema provenance. No application/database/history
  migration, risk acceptance, release clearance or M2 completion is supplied.
- Expanded generated-Maven collection to current jobless, JDBC Batch/M5a,
  ordinary/file/mixed and Kafka/router graphs. New coverage derives validated
  graph classes rather than assuming the historical seven; historical evidence
  validation remains unchanged. Scanner/plugin pins remain unchanged.


- Extended the opt-in Boot 4.1.1 previews to fresh CRUD Batch applications:
  Flyway-owned Batch 6.0.5 JDBC metadata, ordinary file/staging jobs and M5a
  run identity/restart/idempotency. Jobless previews stay Batch-free and Boot 3
  defaults remain byte-identical. H2 history is same-process only; PostgreSQL
  durability is scoped to fresh Batch 6 applications. No Batch 5 migration,
  Kafka, default switch or overall Maven/M2 completion is supplied.
- Tightened the Boot 4.1 preview proof to validate created-resource identity,
  XML mixed content and SOAP fault namespaces, error timestamps and media-type
  parameters. The preview deliberately keeps Jackson 3 strict parsing for
  malformed JSON; valid selected wire contracts and default Boot 3 output
  remain covered, with the prior comparator record retained as history.
- Generated CRUD, passthrough, and Kafka applications now emit the same
  deterministic response-header baseline: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and
  `Content-Security-Policy: frame-ancestors 'none'`. The universal filter is
  profile-independent and deliberately emits no HSTS; HSTS remains owned by
  the TLS-terminating gateway. Generated README and agent-context guidance now
  identify the filter as a security control and make that HSTS responsibility
  explicit for adopters and coding agents.
- Passthrough upstream-request ingestion now resolves nested local `$ref` chains
  and supported `allOf` constraints through the same dialect-aware path as
  top-level properties. Unsupported effective required request fields fail before
  generation with interface, operation, and dotted-field context; non-strict
  missing/cyclic references become deterministic generation and CLI warnings.
  Required parent objects whose presence cannot survive flattening also fail
  closed, while upstream responses, downstream contracts, and CRUD retain their
  established nested fields, diagnostics, and generated output.
- PR #304 established that generated CRUD and passthrough request DTOs enforce OpenAPI string
  maximum lengths by Unicode code point, including constraints defined through
  reusable and chained scalar schema references, including supported OpenAPI
  3.1 reference siblings. Passthrough controllers validate supported canonical
  required fields before routing, transformation, or downstream calls, return a
  sanitized five-field HTTP 400 response without rejected values, and fail closed
  when required-nullable OpenAPI presence semantics cannot be represented safely
  or multiple upstream operations declare incompatible request-validation
  contracts for the shared inbound DTO. At the #304 merge, that coverage was
  **top-level only**:
  properties nested inside a flattened object are read literally, so a nested
  `$ref` skips the whole parent and a nested `allOf` loses its constraints.
  those nested cases and other unrepresentable required shapes were explicitly
  deferred to the reader-first follow-up recorded above.
- Generated pageable CRUD controllers now reject page sizes above `200` and
  database offsets above `50,000` with HTTP 400 before invoking the service.
- Generated CRUD, passthrough, and Kafka READMEs, plus CRUD/passthrough
  `agent-context.md`, now state the supported gateway-delegated authorization
  envelope and make rate limiting an explicit gateway responsibility.
- Generated Kafka apps expose only actuator health by default. Operators can
  opt into metrics and Prometheus with
  `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,metrics,prometheus` when the
  application port is protected by the required authenticated gateway.

### Fixed

- Refuse effectively optimized Python before any Batch proof side effects, including
  module entry points and imported helpers; subprocess controls cover `-O`, `-OO`
  and effective `PYTHONOPTIMIZE` levels (#322).
- Keep opted-in M5a retries bound to the original typed durable execution parameters
  on Batch 5 and 6, including crashes before frozen context commits (#321). Validate
  complete history and corroborating context fail-closed; rejected attempts cannot
  rebind or poison original-date retries. This intentionally changes only affected
  M5a job Java, not ordinary defaults, migrations, dependencies or recovery policy.
  Added four-case PostgreSQL early-crash proof and both-line H2/corruption controls.
  Select the platform history-read exception explicitly for a valid
  `RuntimeException` domain entity; both Boot lines compile and execute the
  expanded name controls without rewriting domain references.

- Boot 4.1 Batch preview templates now select framework types explicitly rather
  than rewriting rendered bodies, preserving valid domain names such as
  `JobLauncher` and `JobExplorer`. Schema-valid ordinary/M5a compilation
  regressions run on Boot 3 and Boot 4; existing defaults remain unchanged.

## [4.1.1] - 2026-07-02

Security hardening hotfix for generated enterprise PostgreSQL apps.

### Changed

- **A6 generated-app credential fallback hardening** — enterprise PostgreSQL
  target profiles now emit `SPRING_DATASOURCE_USERNAME` and
  `SPRING_DATASOURCE_PASSWORD` placeholders with no `postgres` fallback. A
  misconfigured deployment fails fast instead of silently using
  `postgres` / `postgres`. The legacy-compatible H2 development profile is
  unchanged.
- Updated generated-app operations and handover evidence docs to mark A6
  resolved and to keep datasource credentials platform/env supplied.

## [4.1.0] - 2026-06-26

The **regen-preview UX increment** on the `v4.0.0` enterprise-readiness baseline — feature-flagged
and off by default. Suite pin: engine `8f758f4` / studio `6537a75` / ks `11aed44` (unchanged).
Re-verified GREEN by the hermetic **L5 acceptance** gate, including the regen-apply addendum.

### Added

- **Regenerate/maintain apply surface (Engine)** — `appbuilder apply --manifest --package
  --approved-plan-hash`, with per-session allowed-roots fail-closed isolation; additive-only and
  drift-refusing (prior Flyway migrations immutable).
- **Regen-preview UX (Studio)** — preview → approve → apply of the Engine Change Plan, per-session
  isolated, feature-flagged (`EDGEFORGE_STUDIO_REGEN_PREVIEW_ENABLED`, off by default).
- **L5 acceptance — regen-apply addendum** — the two-session `regen-preview approve-apply` scenario
  added to the hermetic L5 gate (Engine orchestrator + Studio leaf).
- **Apply contract pinned (§11)** — `docs/regenerate-maintain-suite-design.md` §11 fixes the apply
  CLI surface and the L5 regen-apply scenario detail shape as the cross-repo contract.

### Changed

- Synced the suite-baseline pointers (glossary, READMEs, this changelog) and the suite tracker to
  `v4.1.0`; carried forward the prior `v4.0.0` docs-sync.

## [4.0.0] - 2026-06-20

The **enterprise-readiness MVP / handoff suite baseline**: edge-contract v1,
regenerate / maintain-over-time, and multi-session / shared deployment — proven GREEN by
the hermetic **L5 acceptance** gate and packaged with the G10 handover-evidence pack.
Suite pin: engine `077bc01` / studio `0e58f9e` / ks `11aed44`. (Reconstructed from
`git log v3.0.0..v4.0.0`.)

### Added

- **Edge-contract v1 — upstream/downstream contract families** (additive, under
  `upstream_interfaces[]` / `downstream_interfaces[]`):
  - **XML / XSD** — contract foundation, canonical runtime + generated runtime
    adapters, XSD include/metadata validation.
  - **SOAP / WSDL (bounded)** — WSDL contract foundation, inbound endpoint
    generation, outbound canonical mapping + generated clients; **bounded to
    `read_by_id` / `invoke_by_id`** (broader operations remain design-only per the
    readiness matrix).
  - **CSV / delimited files** — inbound parsers, downstream writers, trailer
    reconciliation, separator/encoding validation.
  - **Fixed-width files** — inbound parsers, enhanced handoff records, trailer
    reconciliation, minor-unit output, record-indicator validation.
  - **File-contract layout foundation**; support for multiple downstream file
    contracts per entity.
  - **Staging / table handoffs** — generated to **generate + compile** (run-identity
    handoffs); **not production-hardened** per the readiness matrix.
- **Identity roles (additive, advisory)** — `identity_roles` manifest contract in
  `mode: metadata_only`; an Engine-vs-Advisory track decision recorded for all seven
  roles. Active modes (e.g. `parent_reference`) remain design / in-flight.
- **Generated-app `agent-context.md` emitter (C1)** — a deterministic per-app agent
  onboarding context file.
- **Generated-app test console UX (C2 track)** — cards grouped by edge-contract
  family, SOAP cards, input hints + sample fill, a coverage map + provenance, and a
  Tier-3 look and feel.
- **Enterprise-readiness / import-gate pack** — onboarding (suite "START HERE"
  architecture B1, multi-tool agent files B2, reproducible setup `pyproject` +
  `Makefile` B3, quickstart B4); governance stubs (G2); and the handover-evidence
  pack: secret-scan CI (G3), SBOM + dependency-license inventory (G4), compliance &
  portability checklist (G7), security boundary map (G8), edge-contract readiness
  matrix (C4), and the handover-evidence index + README front-door (G10).

### Changed

- **Generated-app hardening** — quality-gate regression fixtures and checkpoint
  fixes; Kafka router operational semantics, publish/correlation lifecycle, and
  schema-validation taxonomy; CRUD EOD rerun batch topology; mixed path-filtered
  route roots; downstream output dashboard hints.
- **XML runtime safety** — hardened generated XML adapters, output-rollback scoped
  to the publish phase, and sanitized scalar parse diagnostics.
- **Domain-neutral framing (reference scrub, G5)** — neutralized
  customer/product-specific wording (e.g. renamed the generated-app quality gate;
  corrected shared-specs ownership) so committed content is domain-agnostic.

### Fixed

- Identity-role design-review findings, including closing a silent no-op:
  `mode: active` is now always **rejected** for remote `parent_reference`.
- Edge-contract design-review fixes across CSV / fixed-width, XML/XSD, SOAP, and
  downstream topology; a SOAP servlet bean-name collision; SOAP canonical response
  ordering; and non-SOAP XML fault handling.

### Docs & design (design-only)

- Design docs: XML/XSD, SOAP/WSDL, CSV + fixed-width file contracts, downstream
  handoff execution topology, the edge-contract expansion roadmap, and the
  enterprise-readiness & handoff roadmap (iterated v2–v6).

## [3.0.0] - 2026-05-04

Suite baseline (tag subject: *Studio UX v3, KA broader scopes, Kafka router, Docker
Studio*). Reconstructed from `git log v1.5.0..v3.0.0`; Engine-side content below.
Studio UX v3 and Docker Studio are suite / Studio-side (designed and coordinated
here, implemented in their repos). Consolidates the interim, **untagged v2.0.0**
documented baseline (the bounded KS ↔ Studio MVP).

### Added

- **`kafka-integration` archetype / Kafka router** — `kafka-integration` manifest
  contract; generated topic-to-topic and request-reply apps; raw-JSON Kafka
  consumers; router core component renderers; router request/response path
  generation; retry / DLQ observability hardening; and a multi-route scale fixture
  proof.
- **Cross-entity business rules** — a cross-entity rules contract + validation, a
  cross-entity-exists prerequisite, cross-entity state rules, and offset-datetime
  rule literals.

### Changed

- Strict Kafka router schema policy; tightened Kafka manifest and router contract
  validation; repeated downstream file source-field handling and downstream
  file-order harness alignment.

### Docs & design (design-only)

- Studio UX v3 assistive-features design + suggestion-drawer pattern; broader
  Knowledge Server suggestion-scopes design (Engine-side design for the Studio / KS
  suite work); target-state roadmap + sequencing docs; a KS Phase 5 tool review.
- A `[RELEASE]` commit recorded the interim Engine **v2.0.0** baseline within this
  range.

### CI

- Keep the Python check green for docs-only PRs; reduce redundant workflow runs.

## [1.5.0] - 2026-04-12

Phase 3 production-quality hardening + Phase 4 Engine MCP baseline. Reconstructed
from `git log v1.0.0..v1.5.0`.

### Added

- **Phase 4 — local stdio Engine MCP server** — a thin adapter over the
  deterministic Engine functions (Python 3.10+ / FastMCP), with stdio setup and
  allowed-root handling.
- **`springboot-enterprise-postgres-java17` target profile (C8)** — a Java 17 +
  PostgreSQL datasource baseline.
- **Additive manifest extensions** — transaction/event identity semantics via
  `identity_overrides` (A1) and a numeric/sequence generated-ID strategy via
  `id_generation_overrides` (C9).

### Changed

- **Phase 3 hardening** — first-class preserved custom / non-CRUD operations (A3);
  date/type propagation hardening in `translation.py` (A2); real ISO-4217 validation
  emission (B5); fixed-width padding/truncation from the layout spec (B6); an opt-in
  pagination baseline (B7); an audit baseline for the standard enterprise profile
  (B4); and a more honest preserved read-only entity surface.

### Fixed

- Guard create flows from response-only required fields; avoid synthetic create
  methods for explicit read-only operations; align ISO-4217 Hibernate validation
  with CHAR columns and PostgreSQL Flyway / JPA emission; an audit-emission
  business-field collision guard; generated dashboard read-route/path alignment and
  batch test actions; and a pydantic pin aligned for FastMCP.

### Docs & design (design-only)

- A1 identity-semantics design, C9 ID-generation-strategy design, the Phase 4 Engine
  MCP design, and the Studio save/load Phase S1 design.

## [1.0.0] - 2026-04-07

EdgeForge v1 freeze point. Phase 2 is closed and the current baseline is now the permanent v1 reference for the Engine.

### Included in the v1 freeze

- CRUD lane proven end to end
- passthrough-router Engine lane proven end to end
- Studio-led OBIE rerun green end to end
- Studio-led 3-entity privately retained external application expanded proof green end to end
- broad external-application scaffold green through export, generate, build, startup, and health

### Final merged fixes included at the freeze point

- PR `#68` shared spec-route support logic
- PR `#70` nested upstream response DTO coverage fix
- PR `#71` PascalCase JSON property preservation fix
- PR `#72` stale generated migration cleanup / Flyway duplicate-version fix

### Next phase after v1

Phase 3 becomes the EdgeForge v2 production quality hardening pass. The full P0/P1/design-first priority stack is documented in [docs/archive/generation-quality-roadmap.md](docs/archive/generation-quality-roadmap.md).
