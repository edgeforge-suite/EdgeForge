# Downstream Handoff Execution Topology Design v1

> **Status:** Design proposal.
>
> **Created:** 2026-05-19.
>
> **Scope:** Downstream handoff execution topology for the EdgeForge suite.
> This document defines how generated applications and packages should model
> embedded file generation, externally staged handoffs, separate generated
> handoff applications, and external tool contract packs.
>
> **Non-goals:** This document does not implement Engine, Studio, Knowledge
> Server, TestBench, manifest schema, or generated-app code changes. All
> manifest snippets are proposed and not implemented unless explicitly stated.
>
> **Strategic anchor:** [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md)

## 1. Purpose

EdgeForge already supports downstream fixed-width file generation and staging
table DDL/writer scaffolding for CRUD generated apps. That current behavior is
valuable, but it is only one handoff topology: the generated business service
owns the handoff job and writes the downstream artifact directly.

Real enterprise modernization uses more than one topology:

- small bounded EOD outputs can be embedded in the generated service;
- high-volume handoffs often need a separate batch app;
- existing ETL estates may own the final file generation;
- some teams need only a governed contract pack for an external tool.

Without an explicit topology model, EdgeForge risks overloading
`downstream_interfaces[]` and `data_handoffs[]` with ambiguous meaning. A
staging table can become both a canonical projection and a downstream file
transform. A generated CRUD service can accidentally become responsible for
heavy operational batch work. Studio users also have no governed place to say
"generate the app, but the external ETL tool owns this handoff."

This design introduces a topology vocabulary and proposed manifest direction
for downstream handoff execution while preserving the current embedded default.

## 2. Design Principles

- **Contract preservation first:** downstream artifacts are edge contracts, not
  incidental implementation details.
- **Backward compatible by default:** existing manifests without topology
  metadata keep today's embedded behavior.
- **Topology belongs to the downstream interface:** topology describes how a
  downstream contract is fulfilled.
- **Staging remains a contract in its own right:** `data_handoffs[]` should
  model staging/interface tables, not become an implicit file-generation mode.
- **Explicit transforms only:** canonical-to-staging and downstream artifact
  transforms must be authored/reviewed evidence-backed mappings.
- **Archetype-aware, not CRUD-only:** CRUD is one consumer of this model. Future
  passthrough-router, kafka-router, and handoff-app archetypes should opt in
  where applicable.
- **No cross-service leakage:** CDC/outbox and generated service-to-service
  event integration remain in the cross-service integration track.

## 3. Current State

Today, EdgeForge's generated CRUD lane supports:

- `downstream_interfaces[]` entries such as `type: file-fixed-width`;
- `data_handoffs[]` entries such as `type: staging-table`;
- generated Flyway DDL for staging tables;
- generated staging writer support;
- generated fixed-width EOD writer/job behavior for supported file handoffs;
- chunked EOD, rerun, temp-file, atomic move, and staging run identity
  hardening from the post-v3.0.0 generated-app quality work.

This current behavior is best described as **embedded** topology:

```text
Generated business app
  -> reads canonical entity/repository data
  -> optionally writes staging/interface table
  -> writes downstream file artifact directly
```

That remains the default for existing manifests.

Current limitations:

- no explicit topology selector;
- no first-class "external ETL owns the file" mode;
- no generated separate handoff application archetype;
- no external tool contract pack output;
- no explicit inbound/outbound direction on `data_handoffs[]`;
- no Studio Step 5 topology choice.

## 4. Topology Modes

### 4.1 `embedded`

The generated application owns downstream artifact creation directly.

Typical shape:

```text
Generated app -> downstream file / table / artifact
```

Use when:

- handoff volume is bounded;
- schedule is simple;
- operational ownership belongs to the generated service team;
- file/job rerun behavior is simple enough for the generated app;
- demos or early modernization slices need one deployable artifact.

Tradeoffs:

- **Pros:** simplest deployment, easiest demo path, no additional artifact or
  external tool required.
- **Cons:** business service and batch/handoff concerns share the same runtime;
  large reruns can compete with API workloads; scaling knobs are coupled.

Compatibility rule:

- existing downstream file behavior defaults to `embedded` when
  `handoff_topology` is absent.

### 4.2 `staged_external`

The generated application writes a governed staging/interface table, and an
external ETL/batch owner creates the downstream artifact.

Typical shape:

```text
Generated app -> staging/interface table -> external ETL -> downstream artifact
```

Use when:

- the organization already owns file generation in an external ETL platform;
- downstream teams require table-based handoff;
- the generated app should not own final file scheduling or delivery;
- file generation logic must stay outside the generated service boundary.

Tradeoffs:

- **Pros:** clear ownership split; generated app remains focused on canonical
  model and staging contract; external ETL can scale independently.
- **Cons:** EdgeForge cannot prove final artifact generation at runtime unless
  the external ETL is represented by a contract pack or separate proof.

Important boundary:

- EdgeForge can generate staging DDL/writer and package the downstream file
  layout/mapping as contract artifacts, but it does not generate the external
  ETL runtime in this mode.

### 4.3 `separate_handoff_app`

EdgeForge generates a separate handoff application that reads canonical or
staging data and produces the downstream artifact.

Typical shape:

```text
Generated business app -> canonical/staging store
Generated handoff app  -> reads canonical/staging store -> downstream artifact
```

Use when:

- handoff volume is large;
- batch windows and reruns require independent scaling;
- operational ownership differs from the online/API service;
- handoff scheduling, reconciliation, and failure recovery are substantial;
- the handoff must be deployed or released separately.

Tradeoffs:

- **Pros:** isolates heavy batch workloads; allows independent scaling and
  deployment; creates a clean place for handoff-specific observability.
- **Cons:** requires a new generated artifact/archetype, more packaging,
  lifecycle coordination, and stronger integration testing.

Design implication:

- this mode likely requires a future `app_archetype: file-handoff` or similar
  generated artifact. This document does not introduce that archetype.

### 4.4 `external_tool_pack`

EdgeForge emits a sealed contract pack for an external tool. No runnable
handoff code is generated.

Typical shape:

```text
EdgeForge package -> DDL + layout + mapping + samples + control spec
External tool     -> implements runtime handoff
```

Use when:

- an external ETL/file platform is mandated;
- EdgeForge should govern and preserve the contract but not own execution;
- the modernization program needs deterministic specs, samples, and evidence;
- runtime proof happens outside EdgeForge.

Tradeoffs:

- **Pros:** high value with low runtime footprint; fits established ETL estates;
  avoids pretending EdgeForge owns execution it does not control.
- **Cons:** no generated-app runtime behavior to test; success depends on the
  external tool correctly implementing the pack.

## 5. Selection Matrix

| Decision factor | `embedded` | `staged_external` | `separate_handoff_app` | `external_tool_pack` |
|---|---|---|---|---|
| Data volume | Low to medium | Medium to high | High | Any |
| Rerun complexity | Simple | External owner | Complex / isolated | External owner |
| Deployment ownership | Business app team | App + ETL teams | Separate handoff team/app | External tool team |
| Final artifact generation | Generated app | External ETL | Generated handoff app | External tool |
| Reconciliation | Basic generated records/logs | Staging contract + external reconciliation | First-class handoff app concern | Contract-pack-defined |
| Scheduling | App/job scheduler | External scheduler | Independent scheduler | External scheduler |
| Runtime isolation | Low | Medium | High | N/A |
| Studio topology owner | Step 5 | Step 5 | Step 5 | Step 5 |
| Staging spec owner | Step 4 if used | Step 4 | Step 4 if used | Step 4 if table pack exists |
| TestBench value | Medium | Low to medium | High | Low |

## 6. Manifest Placement Recommendation

### 6.1 Put `handoff_topology` on `downstream_interfaces[]`

Recommended proposed shape:

```yaml
downstream_interfaces:
  - name: account-eod-file
    type: file-fixed-width
    spec: downstream/account-eod-layout.yaml
    mapping: downstream/account-eod-mapping.yaml
    handoff_topology:
      mode: embedded
```

Why:

- topology describes how the downstream interface/artifact is fulfilled;
- one downstream file may be generated directly while another is external;
- topology choice belongs next to downstream interface review in Studio Step 5;
- this avoids making staging tables carry file-generation execution semantics.

Validation direction:

- `handoff_topology` is optional;
- missing topology defaults to `embedded` only for current-compatible downstream
  file generation;
- unsupported topology for an archetype should fail clearly rather than
  silently downgrade.

Version posture:

- `handoff_topology` is additive and optional, so the preferred implementation
  path is to keep it compatible with `schema_version: "1.0"`;
- if Engine validation needs to distinguish topology-aware manifests from
  legacy manifests for clarity or routing, a soft `schema_version: "1.1"`
  marker is acceptable under the manifest evolution principles;
- a breaking manifest v2 is not justified by this topology model.

### 6.2 Keep `data_handoffs[]` focused on table/interface contracts

`data_handoffs[]` should continue to model staging/interface table contracts:

```yaml
data_handoffs:
  - name: account-staging-table
    type: staging-table
    spec: data-handoffs/account-staging-table.sql
    mapping: data-handoffs/account-staging-mapping.yaml
```

Future direction:

```yaml
data_handoffs:
  - name: account-staging-table
    type: staging-table
    direction: outbound
    spec: data-handoffs/account-staging-table.sql
    mapping: data-handoffs/account-staging-mapping.yaml
```

`direction: inbound | outbound` is likely needed for future inbound DB
interface tables, but it is not required for the first topology implementation.

### 6.3 Reference staging contracts from topology where needed

For `staged_external` and `separate_handoff_app`, topology may need to identify
which staging/interface contract is the source.

Proposed:

```yaml
downstream_interfaces:
  - name: account-eod-file
    type: file-fixed-width
    spec: downstream/account-eod-layout.yaml
    mapping: downstream/account-eod-mapping.yaml
    handoff_topology:
      mode: staged_external
      data_handoff: account-staging-table
```

Rules:

- `data_handoff` must reference an existing `data_handoffs[].name`;
- external ETL ownership must be explicit in docs/export behavior;
- generated app must not also generate the final file writer unless topology
  says it owns the artifact.

### 6.4 Do not create parallel arrays yet

Do not add `downstream_contracts[]` or `handoff_contracts[]` unless a future
design proves current arrays cannot express the contract. The current
`type` discriminator and optional sub-blocks remain sufficient for this design.

## 7. Proposed Manifest Examples

All examples in this section are **proposed and not implemented**.

### 7.1 Current-compatible embedded fixed-width file

```yaml
downstream_interfaces:
  - name: account-eod-file
    system: downstream-ledger
    type: file-fixed-width
    version: v1
    spec: downstream/account-eod-layout.yaml
    mapping: downstream/account-eod-mapping.yaml
    samples:
      - downstream/account-eod-sample.txt
    handoff_topology:
      mode: embedded

data_handoffs:
  - name: account-staging-table
    system: downstream-ledger
    type: staging-table
    version: v1
    spec: data-handoffs/account-staging-table.sql
    mapping: data-handoffs/account-staging-mapping.yaml
```

Expected future behavior:

- generated app owns the fixed-width writer/job;
- staging table support remains available if declared;
- omission of `handoff_topology` keeps current behavior.

### 7.2 Staged external handoff

```yaml
downstream_interfaces:
  - name: account-eod-file
    system: downstream-ledger
    type: file-fixed-width
    version: v1
    spec: downstream/account-eod-layout.yaml
    mapping: downstream/account-eod-from-staging-mapping.yaml
    handoff_topology:
      mode: staged_external
      data_handoff: account-staging-table
      external_owner: downstream-etl  # tentative - see open question #2

data_handoffs:
  - name: account-staging-table
    system: downstream-ledger
    type: staging-table
    version: v1
    spec: data-handoffs/account-staging-table.sql
    mapping: data-handoffs/canonical-to-staging-mapping.yaml
```

Expected future behavior:

- generated app writes the staging/interface table;
- generated app does not write the final fixed-width file;
- package includes downstream file layout/mapping evidence for the external
  ETL owner.

### 7.3 Separate generated handoff app

```yaml
downstream_interfaces:
  - name: account-eod-file
    system: downstream-ledger
    type: file-fixed-width
    version: v1
    spec: downstream/account-eod-layout.yaml
    mapping: downstream/account-eod-mapping.yaml
    handoff_topology:
      mode: separate_handoff_app
      data_handoff: account-staging-table
      handoff_app:
        app_name: account-eod-handoff
        source: staging_table

data_handoffs:
  - name: account-staging-table
    system: downstream-ledger
    type: staging-table
    version: v1
    spec: data-handoffs/account-staging-table.sql
    mapping: data-handoffs/canonical-to-staging-mapping.yaml
```

Expected future behavior:

- business app and handoff app are separate generated artifacts;
- generated handoff app owns file creation, rerun, reconciliation, and
  handoff-specific observability;
- scheduling is a runtime/deployment concern, not part of the v1 contract
  shape;
- requires a future archetype/design before implementation.

### 7.4 External tool contract pack

```yaml
downstream_interfaces:
  - name: account-eod-file
    system: downstream-ledger
    type: file-fixed-width
    version: v1
    spec: downstream/account-eod-layout.yaml
    mapping: downstream/account-eod-mapping.yaml
    samples:
      - downstream/account-eod-sample.txt
    handoff_topology:
      mode: external_tool_pack
      pack:
        include_ddl: true
        include_mapping_spec: true
        include_samples: true
        include_control_file_spec: true

data_handoffs:
  - name: account-staging-table
    system: downstream-ledger
    type: staging-table
    version: v1
    spec: data-handoffs/account-staging-table.sql
    mapping: data-handoffs/canonical-to-staging-mapping.yaml
```

Expected future behavior:

- EdgeForge emits a sealed package of contract artifacts;
- no runnable file writer or handoff app is generated;
- external tool/runtime owns execution.

## 8. Transform Boundaries

### 8.1 Canonical-to-staging projection

Canonical-to-staging projection maps canonical entity fields into a
staging/interface table contract.

This belongs with `data_handoffs[]` and Studio Step 4.

Rules:

- explicit mapping required;
- evidence-backed field provenance required;
- staging columns must not silently inherit downstream file-only logic;
- staging run identity and reconciliation columns remain staging concerns.

### 8.2 Staging/canonical-to-downstream artifact transform

Downstream artifact transform maps either canonical data or staging data into a
file/message/table artifact declared under `downstream_interfaces[]`.

This belongs with the downstream interface and Studio Step 5.

Rules:

- topology decides whether this transform is implemented by generated code,
  an external ETL owner, a separate generated handoff app, or a contract pack;
- transform ownership must be visible in Studio and in generated/package docs;
- the same mapping syntax may be reused, but mapping scope must be explicit.

### 8.3 Avoid ambiguous staging tables

Staging tables must not become an implicit mix of:

- canonical persistence fields;
- downstream file layout fields;
- ETL scratch columns;
- handoff control/trailer fields.

If the staging table itself is the downstream contract, model it as a
`data_handoffs[]` contract. If a file is the downstream contract, keep the file
under `downstream_interfaces[]` and link it to staging only through explicit
topology metadata.

## 9. Studio Ownership

Studio should keep topology authoring aligned with the existing wizard model:

- **Step 4:** staging/interface table spec and canonical-to-staging mapping.
- **Step 5:** downstream interface contract and handoff topology choice.

Recommended Step 5 UX:

- show topology as a required or defaulted choice for each downstream interface;
- default current fixed-width file behavior to `embedded`;
- show concise mode descriptions and operational tradeoffs;
- warn when a selected topology requires a staging table but none is declared;
- warn when a topology has no generated runtime behavior
  (`staged_external`, `external_tool_pack`);
- preserve KA OFF cleanliness; no hidden inference or background KS calls.

The full UX should be designed in Studio when implementation begins. This doc
only assigns ownership and vocabulary.

Step 7 Decision History may summarize topology choices as manual authoring
decisions alongside other reviewed project decisions. Topology choices should
not be treated as Evidence Trail entries unless a future Evidence Trail design
adds that capability explicitly.

Future KA/KS support may suggest topology choices, for example through a
future `topology` suggestion scope. Such suggestions must never infer, apply,
or change topology silently. They must be reviewed by the author in Studio
before changing project state or manifest export.

## 10. Generated App Implications By Archetype

### 10.1 CRUD

CRUD is the first and current consumer of downstream handoff topology.

Supported future direction:

- `embedded`: current EOD/file writer behavior;
- `staged_external`: generated app writes staging/interface table only;
- `separate_handoff_app`: CRUD app emits/maintains source data while a generated
  handoff app owns artifact generation;
- `external_tool_pack`: CRUD package includes downstream contract pack but no
  handoff runtime code.

### 10.2 Passthrough Router

Passthrough-router may opt in where routing/enrichment flows produce a
downstream artifact or staging projection.

Supported future direction:

- do not assume CRUD persistence;
- topology support should require explicit downstream interface contracts;
- embedded file generation may be less common than external tool packs or
  staged external handoffs.

### 10.3 Kafka Integration / Router

Kafka-router apps already model async request/reply contracts. Downstream
handoff topology is not the same as Kafka topic routing.

Supported future direction:

- use topology only when the router also emits or prepares a downstream handoff
  artifact/table;
- do not conflate Kafka DLQ/retry topics with downstream handoff topology;
- Kafka Avro/SR remains a separate edge-contract family.

### 10.4 Future Handoff App

`separate_handoff_app` likely requires a future generated artifact/archetype,
for example `file-handoff`.

That future design must cover:

- generated app boundary and packaging;
- source data access;
- scheduling;
- rerun and reconciliation;
- deployment ownership;
- TestBench/runtime proof.

This document does not implement or finalize the archetype name.

## 11. Evidence Trail Behavior

Reuse Evidence Trail v1.1 types first:

- `field`
- `mapping`
- `validation`
- `transform`

Proposed richer metadata for contract-derived evidence:

```yaml
evidence:
  type: mapping
  source_artifact: downstream/account-eod-layout.yaml
  artifact_type: fixed-width-layout
  mapping_scope: downstream_artifact
  handoff_topology: embedded
  downstream_interface: account-eod-file
  data_handoff: account-staging-table
```

Guidance:

- topology choice itself is project/manifest metadata, not necessarily a new
  evidence type;
- mapping and transform decisions should carry topology context where useful;
- `external_tool_pack` packages should preserve evidence links even though no
  runnable code is generated;
- propose a new evidence type only if future implementation proves enriched
  existing types cannot represent handoff provenance.

## 12. Golden Fixtures And TestBench Expectations

### 12.1 Golden/generated-output fixtures

Future Engine implementation should add generated-output fixtures for:

- missing topology defaults to current `embedded` behavior;
- explicit `embedded` produces equivalent file writer/job output;
- `staged_external` does not generate final file writer code but does preserve
  staging writer/package artifacts;
- invalid topology for an archetype fails clearly;
- topology references to missing `data_handoffs[]` entries fail clearly;
- Evidence Trail/package metadata includes topology context where implemented.

### 12.2 TestBench/runtime proof

TestBench proof is meaningful only when runtime behavior exists.

Recommended:

- `embedded`: runtime proof can execute generated EOD/file job and verify file
  output.
- `staged_external`: runtime proof may verify staging rows, but final file is
  external and should not be claimed as EdgeForge-generated runtime behavior.
- `separate_handoff_app`: runtime proof is required once the future handoff app
  archetype exists.
- `external_tool_pack`: no runtime proof by default; package inspection is the
  right validation signal.

Do not expand TestBench product behavior until a topology implementation PR
creates meaningful runtime behavior to prove.

## 13. Implementation Slices

### Slice 0 — Design doc only

This PR. No code.

### Slice 1 — Manifest contract

Additive manifest/schema support for:

- optional `downstream_interfaces[].handoff_topology`;
- `mode` enum:
  - `embedded`
  - `staged_external`
  - `separate_handoff_app`
  - `external_tool_pack`
- references to `data_handoffs[]` where required;
- defaulting rules for existing fixed-width downstream behavior.

### Slice 2 — Preserve current embedded behavior

Make current embedded file generation explicit and regression-tested.

Requirements:

- manifests without topology still generate today;
- explicit `mode: embedded` matches current behavior;
- unsupported topology combinations fail clearly.

### Slice 3 — `staged_external`

Generate staging/interface contract output without final file writer runtime.

Requirements:

- staging DDL/writer remains generated where declared;
- package includes downstream file layout/mapping artifacts;
- generated docs explain external ETL ownership.

### Slice 4 — `external_tool_pack`

Emit a sealed contract pack without runnable handoff code.

Requirements:

- include DDL, mapping spec, layout, samples, and control-file spec where
  declared;
- package validation verifies referenced artifacts exist;
- no generated runtime code is implied.

### Slice 5 — `separate_handoff_app`

Design and implement a future handoff app artifact/archetype.

Requirements:

- separate design PR before code;
- generated artifact boundary and deployment model;
- scheduling, rerun, reconciliation, observability;
- runtime proof.

### Slice 6 — Studio Step 5 topology selector

Studio should expose topology in Step 5 after the manifest contract is stable.

Requirements:

- clear defaulting;
- mode-specific warnings;
- no hidden KS calls;
- preserve Step 4/Step 5 ownership boundary.

### Slice 7 — Fixtures and runtime proof

Add golden fixtures in the same implementation PRs as behavior changes.
Add TestBench proof only where runtime behavior exists.

## 14. Open Questions

1. Should `handoff_topology` be required for all future downstream interfaces,
   or remain optional with defaults for current-compatible types?
2. Should `external_owner` be free-form text, a controlled enum, or omitted
   until Studio has a project/team model?
3. Should `separate_handoff_app` share one manifest with the business app, or
   should EdgeForge export a multi-package bundle?
4. Should `external_tool_pack` include generated control/trailer specs in v1,
   or wait for the control/trailer file design?
5. Should `direction` on `data_handoffs[]` land with topology support or wait
   for inbound DB interface tables?
6. How much topology metadata belongs in Evidence Trail versus package docs?
7. Should `staged_external` require a `data_handoff` reference, or allow pure
   package-only file specs with no generated staging output?
8. What is the minimum Studio UX needed to prevent users from misreading
   `external_tool_pack` as generated runtime behavior?

## 15. Design Verdict

Add `handoff_topology` as an optional proposed sub-block on
`downstream_interfaces[]`. Keep `data_handoffs[]` focused on staging/interface
table contracts. Preserve current embedded behavior as the default. Treat
`staged_external` and `external_tool_pack` as contract-preserving modes that do
not imply EdgeForge owns runtime file generation. Treat `separate_handoff_app`
as a future archetype/design track, not a small extension of CRUD.

This gives EdgeForge a clean downstream handoff vocabulary without breaking the
current manifest or drifting into speculative runtime implementation.
