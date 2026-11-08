# Edge-Contract Expansion Roadmap

> **Status:** Suite-level roadmap / design anchor.
>
> **Created:** 2026-05-19.
>
> **Scope:** Upstream/downstream edge-contract preservation roadmap for the
> EdgeForge suite after the `v3.0.0` baseline and post-baseline generated-app
> hardening.
>
> **Non-goal:** This is not an implementation spec. Specific contract-type
> design docs (XSD, SOAP/WSDL, Avro, handoff topology) will land as their own
> PRs and reference this roadmap as their strategic anchor.
>
> **Related docs:**
> - [Generated App Engine Roadmap](generated-app-standards/generated-app-engine-roadmap.md)
> - [Generated-App Test Console UX Standard](generated-app-standards/generated-app-test-console-ux-design.md) — new edge-contract families must render into the test console via its contract-family-agnostic card model
> - [Downstream Handoff Execution Topology Design](edgecontracts/downstream-handoff-execution-topology-design.md)
> - [XML/XSD Contract Support Design](edgecontracts/xml-xsd-contract-support-design.md)
> - [SOAP/WSDL Contract Support Design](edgecontracts/soap-wsdl-contract-support-design.md)
> - [SOAP Canonical Operation Mapping MVP Design](edgecontracts/soap-canonical-operation-mapping-mvp-design.md)
> - [Outbound SOAP Canonical Invocation MVP Design](edgecontracts/outbound-soap-canonical-invocation-mvp-design.md)
> - [Generated-App SOAP Operator Dashboard Actions Design](edgecontracts/generated-soap-operator-actions-design.md)
> - [CSV/Delimited and Fixed-Width File Contract Design](edgecontracts/csv-fixed-width-file-contract-design.md)
> - [Edge-Contract Evidence Trail Metadata Design](edgecontracts/edge-contract-evidence-trail-metadata-design.md)
> - `docs/generated-app-standards/high-tps-entity-profile-design-v1.md` (planned, sibling track)
> - [Identity Role Engine Behavior Design](generated-app-standards/identity-role-engine-behavior-design.md)
> - [Kafka Router Archetype Design](kafka-router-archetype-design.md)
> - [Evidence Trail Design](evidence-trail-design.md)
> - [Manifest Schema](manifest-schema.md)
> - [LegacyExtractor Phase 6 Architecture](legacy-extractor-phase6-architecture.md)

## 1. Purpose

EdgeForge's strategic moat is **deterministic, evidence-backed, contract-preserving
generation of governed Spring Boot services from enterprise edge
contracts**. The platform exists to absorb upstream API, message, and file
contracts, derive a stable canonical internal model, and generate replacement
applications that honor those contracts at the edges.

This roadmap restates that moat and aligns next-design priorities accordingly.

Concretely:

- EdgeForge is **not** a generic AI code generator.
- EdgeForge is **not** only a CRUD scaffolding tool.
- EdgeForge is **not** primarily an app-specific business-logic generator.
- Business-logic support remains explicit, reviewed, and governed — never a
  default inference path.
- **Edge contracts are the suite's strategic center.** Expanding the breadth of
  upstream/downstream contracts EdgeForge can ingest, model, generate, and
  validate is the platform's highest-leverage investment.

## 2. Why This Roadmap Exists Now

- The `v3.0.0` suite baseline is cut.
- Engine post-v3.0.0 generated-app quality hardening (PRs `#141`–`#153`) closed
  the majority of correctness gaps surfaced in the Claude/Codex generated-app
  reviews: CRUD fixed-width/temporal, Kafka router publish/correlation, CRUD
  DTO/list contract fidelity, Kafka schema validation, regression fixtures,
  EOD/batch topology, UUID DDL consistency, staging run identity.
- The identity role foundation (Engine PRs `#154`–`#160`, Studio PRs
  `#154`–`#159`, KS PRs `#25`–`#28`) is in place and the advisory-track decision
  for all seven roles is documented.
- The next strategic risk is **roadmap drift back into app internals** —
  deeper business-logic generation, more identity-role active modes, more
  generated-app correctness polish — instead of broadening the edge-contract
  surface area where the suite's moat actually lives.

This roadmap redirects the next strategic design slot toward **upstream/downstream
contract type expansion** and **handoff topology**.

## 3. Current Baseline

### Implemented (on `origin/main`)

- CRUD REST/OpenAPI-style generation (`app_archetype: crud`)
- Passthrough router (`app_archetype: passthrough-router`)
- Kafka request/reply router (`app_archetype: kafka-integration`, `async_routes[].pattern: router`)
- Kafka JSON Schema runtime validation (cached compiles, draft honored)
- Fixed-width downstream files with minor-unit / temporal correctness
- Fixed-width and CSV/delimited file-contract parser/writer generation plus
  file-only ingest/output runtime paths
- Fixed-width downstream header/data/trailer generation plus fixed-width and
  CSV inbound trailer record-count/sum reconciliation
- XML/XSD parser/serializer generation and CRUD canonical ingest/output runtime
  paths for explicitly mapped XML contracts
- SOAP/WSDL parsing, inbound endpoint generation, outbound client generation,
  adapter-only SOAP runtime diagnostics, inbound canonical `read_by_id`, and
  outbound canonical `invoke_by_id` for supported WSDL contracts
- Edge-contract Evidence Trail metadata design plus Studio export for file,
  XML/XSD, and SOAP/WSDL provenance, preserving Evidence Trail v1.1 types
- Generated-app test console descriptor model, Tier-3 look-and-feel, family
  grouping, SOAP cards, coverage/provenance, and input hints/sample fill
- Staging / interface table output via `data_handoffs[]`
- Field-level mappings and Kafka transform mappings
- Evidence Trail v1.1 for `field`, `validation`, `rule`, `cross_entity_rule`,
  `mapping`, `transform`
- Knowledge Assist deterministic suggestion scopes including `identity_role`
- Identity roles metadata-only foundation for all seven roles
- Generated-app quality regression fixtures (Engine PR `#145`)
- Final integrated file + XML/XSD + SOAP/WSDL v1 runtime smoke passed on
  2026-06-09; see
  [edge-contract integrated v1 smoke results](test-results/edge-contract-integrated-v1-smoke-2026-06-09.md)

### Partial / pending

- TestBench runtime proof is mainly Kafka/router; CRUD/file proof is outside
  the current TestBench scope
- Source-contract conflict surfacing (roadmap PR 10) is design-pending
- Downstream handoff execution topology is design-complete for the four-mode
  model, but only embedded generated-app file output is implemented today
- File control/trailer support is partial: fixed-width outbound trailer
  generation plus fixed-width and CSV inbound trailer reconciliation are
  implemented; header semantic validation, checksums, broader reconciliation
  files, partial-accept mode, and SFTP/object-store delivery remain future
- Strict governance mode for missing optional edge-contract evidence remains
  future; current Studio export preserves Evidence Trail v1.1 shape and does
  not add `file_contract`, `xml_xsd`, `soap_wsdl`, or `identity_role` evidence
  types
- SOAP canonical operation mapping supports the CRUD inbound `read_by_id` MVP
  and downstream `invoke_by_id` MVP; broader operation kinds, non-ID finder
  policies, response persistence/audit, and richer fault/detail mapping remain
  future work
- Generated-app test console Slice 3b packaged-artifact viewer remains blocked
  on artifact packaging/serving design; Slice 5 workflow and Slice 6 sweep
  remain backlog
- High-TPS entity profile is design-pending
- Active `parent_reference` Phase 2a is in-flight on a feature branch only;
  not on `origin/main`
- Liveness/readiness K8s probe split, CRUD-lane MDC, CI pipeline descriptor,
  full server-owned timestamp protection — partial; tracked in the quality
  gate gap register

### Missing edge-contract breadth

- SOAP canonical operation mapping beyond the implemented CRUD inbound
  `read_by_id` and downstream `invoke_by_id` MVPs: broader operation kinds,
  non-ID finder policies, response persistence/audit, retries, and richer
  fault/detail mapping
- Inbound DB interface tables (current support is outbound staging only)
- Kafka Avro / Schema Registry
- IBM MQ / JMS
- PL/SQL package specs / stored procedure signatures
- COBOL copybooks (via LegacyExtractor)
- ISO 20022 / SWIFT MX / SWIFT MT message profiles

## 4. Contract Type Families

The earlier informal "XML-shaped" grouping conflated distinct contract substrates.
The correct taxonomy:

| Family | Members | Shared substrate |
|---|---|---|
| **XML/XSD-shaped** | SOAP, XSD, ISO 20022, SWIFT MX, MQ XML payloads | XSD parser + XML serialization |
| **Schema-governed message contracts (non-XML)** | Kafka JSON Schema, Avro, Protobuf | Schema-registry / schema-file resolution + JSON or binary serde |
| **Positional/text record contracts** | Fixed-width files, CSV/delimited, SWIFT MT | Custom per-format parser; no shared substrate |
| **REST/JSON contracts** | OpenAPI, JSON Schema | Already implemented baseline |
| **DB-mediated contracts** | Staging tables, interface tables, stored procedure signatures | JDBC / DDL / procedure-signature modeling |
| **Transport/delivery contracts** | SFTP, MQ/JMS transport, object-store delivery | Adapter configuration + payload contract |

Important notes:

- **Avro and Protobuf are not XML-shaped.** They are schema-governed message
  contracts with their own serde and registry mechanics.
- **SWIFT MT is not XML/XSD.** It needs its own parser and profile model.
  SWIFT MX is XML/XSD-shaped and layers on the XSD foundation.
- **Oracle Forms / legacy screens are evidence only**, not a generation
  contract. They are KS-ingestible as documents but do not produce manifest
  entries and EdgeForge does not generate UI from them.
- **Regulatory / XBRL is parked.** Regulatory reporting tools are their own
  ecosystem and out of EdgeForge's lane.
- **GraphQL is parked** unless a concrete enterprise modernization need appears.

## 5. Upstream Contract Roadmap

| Contract type | Family | Current status | Wave | Complexity | Notes |
|---|---|---|---|---|---|
| XSD / XML | XML/XSD | Implemented for explicit mapped CRUD ingest/output | **1a** | M-L | Foundation for SOAP, ISO 20022, SWIFT MX, MQ XML; v1 parser/runtime in place |
| SOAP / WSDL | XML/XSD | Implemented for WSDL foundation, inbound endpoint, outbound client, inbound `read_by_id`, and outbound `invoke_by_id` MVPs | **1a** | M-L | Layers on XSD; v1 scoped to document/literal-wrapped |
| CSV / delimited inbound | Positional/text | Implemented, including indicator-column trailer record-count/sum validation | 1b | S-M | Parser/runtime ingest implemented for explicit mapped CRUD contracts |
| Fixed-width inbound | Positional/text | Implemented, including trailer record-count/sum validation | 1b | S | Symmetrical parser/runtime ingest plus PR #205 trailer reconciliation |
| DB interface tables (inbound) | DB-mediated | Missing | 1b | S-M | Adds `direction: inbound` to `data_handoffs[]` |
| Kafka Avro / Schema Registry | Schema-governed (non-XML) | Missing | 1b | M | Enterprise Kafka default; SR client adds optional runtime dep |
| IBM MQ / JMS | Transport (payloads often XML) | Missing | 2 | M | Most MQ payloads are XML; sequence after XSD |
| PL/SQL package specs / SP signatures | DB-mediated | Missing | 2 | M | **Signatures only** — lightweight ingester possible without full LE |
| PL/SQL bodies / rule extraction | Legacy code | Parked | 2 (via LE) | L | Requires LegacyExtractor revival |
| COBOL copybook | Positional/text (via LE) | Parked | 2 (via LE) | L | Route through LE |
| ISO 20022 profiles | XML/XSD | Missing | 2 | M (after XSD) | Profile-scoped (e.g., `pain.001`, `camt.053`) |
| SFTP file drops + control files | Transport | Missing | 2 | M | Pairs with downstream control-file support |
| Kafka Protobuf | Schema-governed (non-XML) | Missing | 3 | M | Less common than Avro |
| SWIFT MT | Positional/text (custom parser) | Missing | 3 | L | **Not XML/XSD** — own parser/profile model |
| SWIFT MX | XML/XSD | Missing | 3 | L | XSD-layered but narrow |
| gRPC / Protobuf | Schema-governed (non-XML) | Missing | 3 | M | Low enterprise relevance |
| Object-store inbound | Transport | Missing | 3 | M | After SFTP |
| Stored procedure adapter (beyond signatures) | DB-mediated | Missing | 3 | M | After SP signature support |
| GraphQL | — | Missing | **Parked** | M | Cut unless a concrete enterprise ask appears |
| Oracle Forms | Evidence only | — | **Parked** | — | KS-ingestible as document; no manifest entry, no UI generation |
| Regulatory / XBRL | — | Missing | **Parked** | XL | Out of lane |
| CDC / outbox | — | Missing | **Cross-service track** | M-L | See section 10 |

## 6. Downstream Contract Roadmap

| Contract type | Family | Current status | Wave | Complexity | Notes |
|---|---|---|---|---|---|
| XML/XSD output | XML/XSD | Implemented for explicit mapped CRUD output | **1a** | M | Same XSD pipeline as upstream |
| SOAP outbound client | XML/XSD | Implemented, including downstream canonical `invoke_by_id` action MVP | **1a** | M | Paired with upstream SOAP; same WSDL/XSD pipeline |
| Downstream handoff topology | Topology | Design-pending | **1a (design)** | L | Defines `embedded` / `staged_external` / `separate_handoff_app` / `external_tool_pack` modes |
| Outbound REST client (OpenAPI) | REST/JSON | Missing | 1b | M | No client emitter today |
| Fixed-width inbound/outbound symmetry | Positional/text | Implemented for data records and fixed-width trailer/control paths | 1b | S | Reuses outbound spec |
| CSV / delimited output | Positional/text | Implemented for data records | 1b | S-M | Pairs with inbound |
| Control/trailer/reconciliation files | Positional/text | Partial | 1b | M | Fixed-width outbound trailer generation plus fixed-width and CSV inbound trailer reconciliation are done; broader reconciliation files, checksums, header semantic validation, partial-accept mode, and SFTP/object-store delivery remain future |
| Kafka Avro/SR producer | Schema-governed (non-XML) | Missing | 1b | M | Paired with Avro ingest |
| IBM MQ / JMS outbound | Transport | Missing | 2 | M | Paired with MQ ingest |
| SFTP delivery | Transport | Missing | 2 | M | Needed for nearly all real EOD handoffs |
| External tool contract pack | Topology mode | Missing | 2 | M | Sealed spec export for Talend/Ab Initio/Spring Batch; no generated runnable code |
| ISO 20022 output | XML/XSD | Missing | 2 | M (after XSD) | Profile-scoped |
| PL/SQL / stored procedure call (outbound) | DB-mediated | Missing | 2 | M | If SP signature support lands in upstream |
| Kafka Protobuf producer | Schema-governed (non-XML) | Missing | 3 | M | Paired with Protobuf ingest |
| SWIFT MT output | Positional/text (custom parser) | Missing | 3 | L | Own parser |
| SWIFT MX output | XML/XSD | Missing | 3 | L | After XSD; narrow |
| Object-store delivery | Transport | Missing | 3 | M | After SFTP |
| Data warehouse / analytics feed pack | Analytics | Missing | 3 | M | Often better via external tool pack |
| Audit / event log handoff | Logging | Partial | 2 | S-M | Depends on B6 (MDC) and B9 (audit metadata) hardening |
| Regulatory / XBRL output | — | Missing | **Parked** | XL | Out of lane |
| GraphQL output | — | Missing | **Parked** | M | Cut unless a concrete enterprise ask appears |
| Outbox / CDC publishing | — | Missing | **Cross-service track** | L | See section 10 |

## 7. Recommended Waves

### Wave 1a — Roadmap + Topology + XML Foundation

- Edge-Contract Expansion Roadmap (this doc)
- Downstream Handoff Execution Topology Design v1
- XML/XSD Contract Support Design v1
- SOAP/WSDL Contract Support Design v1

**Why Wave 1a:** XSD foundation unblocks the entire XML universe (SOAP, ISO
20022, SWIFT MX, MQ XML payloads). SOAP is the single largest unaddressed
enterprise upstream type. Handoff topology choice is the most-requested
operational gap. The roadmap doc anchors all of the above and prevents drift.

### Wave 1b — Edge Symmetry + Avro

- CSV / delimited inbound and outbound, including indicator-column inbound
  trailer record-count/sum reconciliation
- Fixed-width inbound (implemented, including trailer record-count/sum
  reconciliation)
- Inbound DB interface tables (add `direction: inbound` to `data_handoffs[]`)
- Kafka Avro / Schema Registry ingest and producer (non-default serde; opt-in dependency)
- Outbound REST client emission from OpenAPI
- Control / trailer / reconciliation files (partially complete: fixed-width
  outbound trailer generation plus fixed-width and CSV inbound reconciliation
  are done; broader reconciliation files, checksums, header semantic
  validation, partial-accept mode, and SFTP/object-store delivery remain)

**Why Wave 1b:** Closes the current v1 inbound/outbound asymmetry across
positional contracts; adds the most common enterprise Kafka serde (Avro) as a
future schema-governed lane; and leaves broader reconciliation files, transport
delivery, checksums, and partial-accept behavior as explicit follow-ons.

### Wave 2 — Legacy + Layered Standards

- PL/SQL package spec ingester (signatures only — lightweight wedge ahead of full LE)
- LegacyExtractor UX v3 refresh + Phase 6 first implementation slice
  (PL/SQL bodies, COBOL copybook)
- COBOL copybook ingest through LE
- IBM MQ / JMS inbound and outbound
- SFTP delivery + control-file linkage
- ISO 20022 specific message profiles (layered on XSD)
- External tool contract pack export
- Audit / event log handoff (after B6 / B9 hardening)

**Why Wave 2:** Adds the legacy/layered enterprise standards that depend on
foundational Wave 1a/1b work. Gates the LegacyExtractor revival behind explicit
implementation ownership.

### Wave 3 — Specialized / Defer

- SWIFT MT (own parser) and SWIFT MX (XSD-layered)
- Kafka Protobuf
- gRPC / Protobuf
- Object-store delivery (inbound and outbound)
- Stored procedure outbound adapter beyond signatures
- Data warehouse / analytics feed packs

**Why Wave 3:** Narrow, specialized, or driven by specific customer demand.
Defer until at least one Wave 1/2 implementation slice is in production.

### Parked indefinitely

- GraphQL
- XBRL / regulatory reporting output
- Oracle Forms UI generation (Oracle Forms can still be KS-ingested as
  evidence; no manifest contract type)
- CDC / outbox as an edge-contract concern (it belongs to the cross-service
  integration track — see section 10)

## 8. Implementation Approach and Sequencing

### Mixed contract types are intentional

EdgeForge must support multiple upstream and downstream contract types in a
single generated app/package. The canonical model remains the hub. Example of
a realistic enterprise replacement app:

- **Upstream:** REST/OpenAPI (channel API) + SOAP/WSDL (core back-end service) +
  XSD/XML (configuration feed) + Kafka JSON/Avro (real-time events) +
  fixed-width inbound (batch file feed)
- **Downstream:** fixed-width EOD file + CSV reconciliation file + staging table +
  SOAP client (downstream core) + Kafka event (notification publish)

Each `upstream_interfaces[]`, `downstream_interfaces[]`, and `data_handoffs[]`
entry carries its own `type` and type-specific metadata. The manifest is not
"one app = one contract type" — it is "one app = one canonical model fed by N
upstream contract types and producing M downstream contract types."

Edge-contract capabilities are suite-level design tracks, not CRUD-only
features. Each contract family defines common manifest shape, deterministic
parsing, evidence mapping, and Studio review behavior once. Engine emitters then
opt in by archetype where the behavior makes sense. CRUD is one consumer of the
contract model, not the boundary of the capability. Passthrough-router,
Kafka-router, and future handoff-app archetypes should reuse the same contract
family definitions where applicable.

### One contract family at a time

Implementation of each new contract family should follow the complete pipeline
before the next family starts:

1. Design the contract family (design doc in `docs/edgecontracts/`)
2. Add/extend manifest shape additively within the active `2.0` dialect
3. Add deterministic parser/importer (no AI inference by default)
4. Add Studio import/review surface (explicit contract type selection)
5. Add Engine translation to canonical metadata
6. Add emitter/runtime support where applicable
7. Add Evidence Trail source mapping (reuse existing types + richer metadata)
8. Add generated-output tests
9. Add TestBench/runtime proof (only when the contract type has meaningful
   runtime behavior — e.g., Kafka router needs runtime proof; SFTP delivery
   does not)

Partial "parser only" or "emitter only" implementations are not acceptable as
shipped contract family support. Each family must be end-to-end testable before
the next begins.

### Studio import UX principle

Studio should ask for the contract type before loading/parsing whenever
possible. Preferred UX direction:

```
Select contract type -> choose source (upload / file path / URL /
  registry / DB connection later) -> deterministic parse ->
  review fields/operations/mappings -> export manifest
```

This keeps KA OFF clean and preserves deterministic behavior. KA/KS suggestions
should run only after the explicit import/review flow, not as hidden background
inference during import.

### Design waves vs implementation sequence

The Wave model (section 7) defines **design priority**. The sequencing table
below defines the likely **implementation order**. These are related but not
identical:

- **XML/XSD and SOAP/WSDL stay Wave 1a design priorities** because they are
  strategic foundations that unblock the largest family of enterprise contract types.
- **Fixed-width inbound, CSV/delimited, and DB interface tables (inbound) may
  still be earlier implementation slices** after their design lands, because they
  are lower-risk and can prove the one-family-at-a-time pipeline cheaply.
- **Avro/SR remains Wave 1b design priority**, but implementation may follow
  file/table symmetry because it introduces an optional Schema Registry runtime
  dependency that needs careful opt-in design.

### Implementation sequencing

| Seq | Contract / capability | Why this implementation order | Complexity | Confidence | Primary repo impact |
|---|---|---|---|---|---|
| 1 | Downstream handoff topology | Most-requested operational gap; design-only; unblocks all downstream work | L (design) | High | Engine + Studio |
| 2 | Fixed-width outbound completeness: control/trailer/reconciliation files | Implemented for header/data/trailer generation; broader reconciliation files remain future | S-M | High | Engine |
| 3 | Fixed-width inbound | Implemented, including generated parser/runtime ingest and trailer record-count/sum reconciliation | S | High | Engine + Studio |
| 4 | CSV / delimited inbound + outbound | Implemented for parser/writer/runtime data-record paths and indicator-column inbound trailer validation | S-M | High | Engine + Studio |
| 5 | DB interface tables (inbound) | Adds `direction: inbound`; reuses existing staging pipeline | S-M | High | Engine + Studio |
| 6 | XML/XSD foundation | Unblocks SOAP, ISO 20022, SWIFT MX, MQ XML; highest-leverage new parser | M-L | Medium | Engine + Studio + KS |
| 7 | SOAP/WSDL inbound + outbound | Layers on XSD; single largest unaddressed enterprise upstream type | M-L | Medium | Engine + Studio |
| 8 | IBM MQ / JMS | Most MQ payloads are XML; sequence after XSD | M | Medium | Engine |
| 9 | SFTP delivery package | Needed for nearly all real EOD handoffs in production | M | Medium | Engine |
| 10 | External tool contract pack | Sealed spec export; no generated runnable code; covers non-generated ETL | M | Medium | Engine |
| 11 | PL/SQL package specs / SP signatures | Lightweight ingester; useful wedge ahead of full LE | M | Medium | Engine (+ LE if bodies) |
| 12 | Avro / Schema Registry | Enterprise Kafka serde; opt-in SR runtime dependency | M | Medium | Engine + Studio |
| 13 | ISO 20022 profiles | Profile-scoped XSD work (e.g., `pain.001`, `camt.053`) | M | Medium | Engine |
| 14 | COBOL copybook (via LE) | Requires LegacyExtractor revival; gated on LE owner | L | Low | LE + Engine |
| 15 | SWIFT MX | XSD-layered; narrow scope | L | Low | Engine |
| 16 | SWIFT MT | Own parser; not XML/XSD | L | Low | Engine |
| 17 | Protobuf / gRPC | Low enterprise relevance today | M | Low | Engine |
| 18 | Object-store delivery | After SFTP; cloud-native variant | M | Low | Engine |
| — | CDC / outbox | Cross-service track, not edge-contract (section 10) | M-L | — | Separate design |
| — | GraphQL / XBRL / Oracle Forms UI | Parked indefinitely | — | — | — |

See the "Design waves vs implementation sequence" subsection above for the
rationale behind design priority and implementation order being separated.

## 9. Manifest Evolution Principles

- **Current code is manifest v2.** The coordinated pre-adopter V2-E/V2-S/V2-X cut replaced the
  active contract with single-dialect `2.0`, with no `1.0` compatibility bridge. The cut is an
  anti-downgrade boundary, not the parked broader semantic redesign.
- **Prefer additive, backward-compatible evolution within the active dialect.** Candidate `type`
  values and optional sub-blocks target `2.0` and remain backward-compatible within that dialect.
- **Do not create another breaking manifest revision** unless a separately approved paradigm shift
  requires it (for example, first-class contract identity, lineage, or compatibility policy that
  demands a different top-level shape).
- **Do not introduce parallel `upstream_contracts[]` / `downstream_contracts[]`
  arrays** unless a concrete design proves the current model cannot represent
  the use case.

### Candidate additive concepts (proposed, not implemented)

- `contract_artifacts[]` at top level — shared XSD/WSDL imports referenced by
  multiple interfaces; XML/XSD v1 should start with direct interface `xsd_path`
  references and add shared artifacts when SOAP/WSDL or another shared-bundle
  use case needs them
- `handoff_topology` on `downstream_interfaces[]` — enum of `embedded` /
  `staged_external` / `separate_handoff_app` / `external_tool_pack`
- Per-`type` required sub-blocks (e.g., `wsdl_path` for `type: soap-wsdl`,
  `avro_schema_path` + optional `schema_registry_url` for `type: kafka-avro`,
  `xsd_path` for `type: xml-xsd`)
- `direction: inbound | outbound` on `data_handoffs[]` (currently implicit outbound)
- `compatibility_policy` optional per interface; deferred policy concept, not
  part of XML/XSD v1
- Richer evidence metadata on existing Evidence Trail types (see section 12)

## 10. Cross-Service vs Edge-Contract Ownership

The two roadmaps overlap on Kafka but address different product problems.

| Lens | Scope | Examples |
|---|---|---|
| **Edge-contract roadmap** | External system contracts and adapter/handoff preservation across organizational boundaries | SOAP service to an upstream core; Avro topic from a partner system; EOD file to an external ETL team |
| **Cross-service integration design** | Generated microservice-to-microservice integration within the same modernization estate | Outbound event publishers, consumer domain handlers, outbox/correlation, saga-like patterns between EdgeForge-generated apps |

Where they meet (Kafka):

- If the topic crosses an **organizational/contract boundary** → edge-contract
  roadmap owns the contract type and serde.
- If the topic is between two **EdgeForge-generated apps in the same estate** →
  cross-service integration design owns the publisher/consumer pattern.

CDC / outbox is a cross-service concern, not an edge-contract one. Keep it in
the cross-service track and do not re-scope it into this roadmap.

## 11. Downstream Handoff Topology

This roadmap does not design the topology in detail. That belongs in
[Downstream Handoff Execution Topology Design](edgecontracts/downstream-handoff-execution-topology-design.md).

Summary of the four modes to be designed:

| Mode | When |
|---|---|
| `embedded` | Small/bounded EOD; SoR golden-data dumps; demos; today's de-facto default |
| `staged_external` | Existing external ETL owns the file generation |
| `separate_handoff_app` | Heavy EOD, reruns, reconciliation, large-volume operations; requires a new `app_archetype: file-handoff` (or similar) |
| `external_tool_pack` | External ETL is mandated; emit a sealed contract pack (DDL + mapping spec + sample + control-file spec) — no generated runnable code |

Studio ownership direction:

- **Studio Step 5 (Downstream Interfaces) should own the topology choice.**
- **Step 4 remains staging-table spec authoring.** Topology is a handoff-time
  decision, not a staging-time one.

Transformation placement (to be detailed in the topology design):

- **Canonical → staging projection** mapping is allowed and welcome **when the
  staging table is itself a downstream contract**. These transforms must be
  explicit, evidence-backed, and authored in Studio Step 4 — not implicit in code.
- **Staging/canonical → downstream artifact transform** belongs to the
  downstream handoff lane and varies by topology.
- **Core rule:** do not let staging tables become an ambiguous mix of canonical
  model and downstream file logic.

## 12. Evidence Trail Direction

Reuse existing Evidence Trail v1.1 evidence types first:

- `field`
- `mapping`
- `validation`
- `transform`

Prefer adding **richer metadata fields** on existing evidence types when the
source is a contract artifact. Proposed additive metadata:

- `source_artifact` — relative path to the source artifact (e.g.,
  `upstream/customer-service.wsdl`)
- `artifact_type` — `xsd` | `wsdl` | `avro` | `copybook` | `openapi` |
  `fixed-width-layout` | `swift-mt` | etc.
- `xsd_path` — XSD element/type path when applicable
- `xpath` — XPath into a sample payload when applicable
- `wsdl_operation` — operation name for SOAP-sourced evidence
- `schema_type` — Avro / Protobuf type name when applicable
- `namespace` — XML namespace when applicable

**Decision rule:** propose a new evidence type **only** if a future design
proves the existing types enriched with these metadata fields cannot represent
contract-artifact provenance cleanly. So far, every contract type in the
matrices fits.

## 13. Identity Role Priority Note

Active modes for `business_key`, `external_reference`, and `idempotency_key`
remain valid **production correctness work**. They are not low-value, and they
are not business-logic drift.

- They are **paused behind Wave 1a edge-contract design**, not canceled.
- They remain on the design-first roadmap as production correctness items.
- They should **not consume the next strategic design slot** unless EdgeForge
  explicitly decides to prioritize generated-app production semantics over
  edge-contract expansion.
- Phase 2a `parent_reference` remains a separate in-flight decision track,
  independent of this roadmap.

This roadmap is a **priority call, not a value judgment.**

## 14. Implementation Rule

**No implementation work begins on a new contract type, topology mode, manifest
extension, or generated-app archetype until the relevant design doc lands and
is reviewed.**

This is the rule that prevents the suite from drifting back into app-specific
hardening or speculative implementation.

The only exception is the in-flight Phase 2a (`parent_reference`) feature branch,
which predates this strategic pivot and is being handled on its own
merge-decision track.

## 15. Current Edge-Contract Follow-Up Sequence

1. [Downstream Handoff Execution Topology Design](edgecontracts/downstream-handoff-execution-topology-design.md)
   — done as the four-mode topology design; implementation remains limited to
   embedded generated-app output.
2. [XML/XSD Contract Support Design](edgecontracts/xml-xsd-contract-support-design.md)
   — done; explicit mapped CRUD XML ingest/output runtime is implemented.
3. [SOAP/WSDL Contract Support Design](edgecontracts/soap-wsdl-contract-support-design.md)
   — done; layered on XSD, defines inbound SOAP endpoint and outbound
   SOAP client generation, and is scoped to document/literal-wrapped binding
   in v1.
4. [SOAP Canonical Operation Mapping MVP Design](edgecontracts/soap-canonical-operation-mapping-mvp-design.md)
   — implemented for explicit CRUD inbound SOAP `read_by_id` mappings to the
   canonical persistence ID while preserving adapter-only mode.
5. [Outbound SOAP Canonical Invocation MVP Design](edgecontracts/outbound-soap-canonical-invocation-mvp-design.md)
   — implemented for downstream SOAP `invoke_by_id` canonical invocation.
6. [Edge-Contract Evidence Trail Metadata Design](edgecontracts/edge-contract-evidence-trail-metadata-design.md)
   — design merged in Engine PR `#210` and implemented in Studio export for
   file, XML/XSD, and SOAP/WSDL metadata through Studio PRs `#190`--`#193`;
   combined proof and final integrated runtime smoke passed.
7. Current Engine edge-contract candidates:
   - final docs/status closeout after the integrated runtime smoke;
   - optional generated-app console polish, especially typed-empty sample-fill
     wording or future real package-sample loading;
   - optional Spring Batch schema-init runtime config polish;
   - optional Studio cleanup for empty duplicate REST interface export, with
     Engine PR `#215` already preventing DTO overwrite.
8. Later: Avro/Schema Registry, inbound DB interface tables, MQ/JMS, SFTP
   delivery, PL/SQL package spec ingester (signatures only), and remaining
   specialized contract families.

### Scoping notes for the first four contract-specific design docs

- **XSD v1 must scope its complexity surface explicitly.** In-scope: simple
  types, single-level complex types with `sequence`, attributes/elements,
  `minOccurs`/`maxOccurs`, basic enumerations, `nillable`, same-namespace
  `xs:include`. Out-of-scope for v1: `xs:choice`/`xs:all`, deeply nested
  complex types, cross-namespace `xs:import` chains, substitution groups,
  abstract types, mixed content, `xs:any`/`xs:anyAttribute`, recursive types,
  advanced facet combinations.
- **SOAP v1 must scope its binding surface.** In-scope: document/literal-wrapped
  binding only, WSDL operations, basic SOAP headers, SOAP faults, HTTP
  transport. Out-of-scope for v1: RPC/encoded, RPC/literal, doc/literal-bare,
  WS-Security policy attachments, MTOM/SwA attachments, WS-Addressing,
  WS-ReliableMessaging, asynchronous SOAP, multi-port/multi-binding WSDLs.
- **SOAP Studio review UX is politically sensitive in enterprise modernization.** Treat WSDL
  operation and fault review as a first-class design item, not an afterthought.
- **SOAP canonical operation mapping starts narrow.** The implemented MVPs
  preserve adapter-only mappings and add only explicit CRUD inbound
  `read_by_id` and downstream `invoke_by_id` canonical behavior before any
  create/update/search, non-ID lookup, response persistence, or retry work.

## 16. Risks / Pushback

1. **Wave 1a is four design tracks.** Even with this roadmap anchor in place,
   topology + XSD + SOAP design is a real quarter of design work. Resist the
   temptation to start implementation on any of them before its relevant design
   doc lands (per section 14 — each track gates on its own design doc, not on
   all Wave 1a docs landing together).
2. **XSD/SOAP complexity is medium-large, not medium.** Underestimating the
   scoped-v1 surface is the biggest delivery risk. Honor the explicit
   in-scope/out-of-scope lists.
3. **SOAP Studio review UX is politically sensitive.** Bad WSDL review will
   burn customer trust faster than missing scope. Budget design time for it.
4. **LegacyExtractor is the bottleneck for COBOL/PL/SQL bodies.** Wave 2 value
   depends on LE being revived. Without an implementation owner, LE UX v3
   Refresh will rot a second time. Decide commitment before writing the refresh
   doc.
5. **PL/SQL package-spec ingester (signatures only) is a useful wedge** into
   Wave 2 ahead of full LE revival. Take this opportunity; it's lightweight.
6. **Avro / Schema Registry adds a runtime dependency footprint.** Confluent
   client jars + SR URL config. Keep this opt-in. Today's JSON Schema runtime
   validation is decoupled from SR — don't break that.
7. **`separate_handoff_app` is heavier than it looks.** New archetype, new
   deploy artifact, new TestBench proof. Sequence `external_tool_pack` earlier
   — it covers a large share of the value for less effort.
8. **Studio UX bandwidth is the throttle.** Phase 2a/2b/2c identity role
   authoring, B3 cross-entity KA fix, edge-contract import UX, and topology
   selector all compete for the same surface area. Define a per-quarter
   Studio surface budget.
9. **The existing manifest `type` discriminator is sufficient.** Resist the
   urge to add parallel `upstream_contracts[]` / `downstream_contracts[]`
   arrays. Per section 9, only justify if a concrete design proves the
   current shape inadequate.
10. **No AI features for contract import as default behavior.** WSDL / XSD /
    Avro parsers must be deterministic. KS suggestion scopes can grow (e.g., a
    future `xsd_field` or `wsdl_operation` scope), but inference must remain
    off by default and gated behind explicit KA.
11. **Parked and deferred items must stay in their assigned lanes unless real
    demand appears.** GraphQL, XBRL/regulatory, and Oracle Forms UI generation
    are parked indefinitely. SWIFT MT outbound is Wave 3 deferred, not parked.
    Future agents should not re-propose these items into Wave 1 or Wave 2
    without explicit strategic redirection.
12. **CDC/outbox stays in the cross-service track**, per section 10. Don't
    double-scope it into the edge-contract roadmap.
