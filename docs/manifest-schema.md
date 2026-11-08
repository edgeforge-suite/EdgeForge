# Manifest Schema

This document captures the current manifest contract for EdgeForge input
projects as of 2026-08-17.

For the ranked suite backlog and future additive follow-ons, see
[docs/archive/target-state-features-v1.md](archive/target-state-features-v1.md).

## Stability Policy

Phase 2 is closed as EdgeForge v1. The current manifest contract is therefore a stable baseline, not an experimental setup.

Rules:

- `manifest-v2` is the stable Engine contract for the proven CRUD + passthrough-router +
  `kafka-integration` baseline
- `schema_version: "2.0"` is the only active version marker
- new concepts must be added only as optional, additive extensions
- any later breaking revision requires a separate maintainer-approved paradigm change

The approved coordinated cut is complete with no `1.0` compatibility bridge: V2-E delivers the
Engine contract, V2-S makes Studio export `2.0`, and paired-branch plus post-merge V2-X passed.
M5a-S1 delivers the bounded `run_semantics` contract and fail-closed validation described below;
M5a-S2 and M5a-S3 deliver the runtime identity and idempotent staging behavior; and M5a-S4 makes a
failed run-identity harness check blocking for an opted-in handoff while preserving legacy warnings.
The four-slice M5a implementation is complete; see the
[durable V2-X result](test-results/manifest-v2-cut-v2-x-2026-08-16.md) for the completed prerequisite.

## Current Stable Concepts

The current v2 manifest baseline makes both the contract version and the generation lane explicit:

- `schema_version: "2.0"` is required on every manifest package
- `app_archetype` defaults to `crud`
- supported archetypes today:
  - `crud`
  - `passthrough-router`
  - `kafka-integration`

The authoritative JSON Schema artifact lives at `appbuilder/schema/manifest-v2.schema.json`.

## File Name

Each modernization input package must include:

- `app-definition.yaml`

The manifest is resolved relative to the input project root.

## Top-Level Shape

The manifest must contain a YAML mapping with these top-level fields:

```yaml
app_name: string
bounded_context: string
schema_version: "2.0"
app_archetype: crud | passthrough-router | kafka-integration  # optional, defaults to crud
upstream_interfaces: []
downstream_interfaces: []
data_handoffs: []
identity_overrides: []
identity_roles: []
id_generation_overrides: []
kafka_config: {}
async_routes: []
rules: []
legacy_references: []
target_profile: string
```

## Required Fields

- `app_name`
- `bounded_context`
- `schema_version`
- `target_profile`

These values must be non-empty strings.

## Schema Version

- `schema_version` is required on every manifest package
- the only supported value is `"2.0"`
- the Engine rejects unknown versions before generation starts

## App Archetype

- `app_archetype` is optional and defaults to `crud`
- supported values:
  - `crud`
  - `passthrough-router`
  - `kafka-integration`

These three lanes are all part of the active additive `manifest-v2` baseline.

## Supported Target Profiles

Current supported profiles:

- `springboot-legacy-compatible`
- `springboot-enterprise-postgres-java17`
- `springboot-standard-enterprise`

Profile intent:

- `springboot-legacy-compatible` keeps the Java 17 + H2 compatibility baseline
- `springboot-enterprise-postgres-java17` provides the enterprise PostgreSQL baseline on Java 17
- `springboot-standard-enterprise` provides the enterprise PostgreSQL baseline on Java 21

The three ordinary IDs select **Spring Boot 4.1.1** for fresh applications
(jobless CRUD/SOAP, supported JDBC Batch/M5a/file/staging jobs, passthrough,
plain Kafka and routers). The former `-boot41-preview` aliases are retired;
only the ordinary profile IDs are supported. Manifest stays
`2.0`. No public Boot 3 profile is added.

Existing Boot 3/Batch 5 or ambiguous output refuses generate, plan and apply
before writes, using POM and durable internal evidence rather than reinterpreting
its old profile ID. Boot 4 same-line regeneration retains migration bytes and
original schema provenance; profile selection does not imply a migration.
See [the Boot 4.1 guide](generated-app-standards/boot41-jobless-preview.md).
A fresh external database is a deployment precondition, not a detected fact.

Future runtime/profile concepts remain additive within the active `2.0` dialect. The selected
V2-E/V2-S/V2-X cut is the sole approved exception to preserving the prior dialect; Engine retains no
post-V2-E v1 bridge.

## Kafka Integration Concepts

`kafka-integration` is an additive archetype under the same
`schema_version: "2.0"` contract. It introduces two top-level optional fields
that become required only when `app_archetype: kafka-integration`:

- `kafka_config`
- `async_routes`

### Kafka Config

`kafka_config` must contain:

- `consumer_group`: non-empty string
- `concurrency`: optional integer, defaults to `1`
- `retry`: optional additive retry policy
- `dlq`: optional additive dead-letter policy

Retry policy shape:

- `max_attempts`: integer `0..10`
- `backoff_ms`: integer `100..60000`
- `backoff_multiplier`: number `>= 1.0`

DLQ policy shape:

- `enabled`: boolean, defaults to `true`
- `topic_suffix`: string beginning with `.`, defaults to `.dlq`

### Async Routes

Each entry in `async_routes` must contain:

- `name`: non-empty string
- `pattern`: `fire-and-forget` or `request-reply`
- `upstream_topic`
- `downstream_topic`
- `transform_mapping`

`upstream_topic` and `downstream_topic` contain:

- `name`
- `system`
- `message_schema`
- optional `sample`

For `request-reply`, the following additive fields are required:

- `upstream_reply_topic`
- `downstream_reply_topic`
- `response_transform_mapping`

Optional additive request/reply route fields:

- `correlation_id`
- `partition_key`
- `reply_timeout_ms`

### Kafka validation rules

- `kafka-integration` manifests require `kafka_config`
- `kafka-integration` manifests require at least one `async_routes` entry
- non-Kafka archetypes do not require or consume Kafka route fields
- all Kafka additions remain additive under `schema_version: "2.0"`

## Interface Definitions

Each entry in `upstream_interfaces` or `downstream_interfaces` must contain:

- `name`: non-empty string
- `system`: optional non-empty string
- `type`: non-empty string
- `version`: optional string
- exactly one of:
  - `spec`: relative path inside the input project
  - `spec_url`: remote HTTP(S) URL
- `mapping`: optional relative path inside the input project
- `sample`: optional single relative sample path for XML/XSD contracts
- `samples`: optional list of relative paths inside the input project
- `operations`: optional list of explicit operation definitions

File contracts belong in `upstream_interfaces[]` or `downstream_interfaces[]`.
`file-fixed-width` remains the supported downstream fixed-width writer contract
for flat `fields[]` layouts and enhanced header/data/trailer layouts.
`file-csv` is recognized as a file contract type with inbound parser and
downstream writer support.

XML/XSD contracts use `type: xml-xsd` in `upstream_interfaces[]` or
`downstream_interfaces[]`. New XML/XSD entries should use `xsd_path` plus
`root_element`; `spec` is accepted as a compatibility alias for `xsd_path`, but
`spec_url` is not supported for XML/XSD. Optional `namespace` asserts the XSD
`targetNamespace`, and `namespace_alias` may carry a reviewed prefix for
generated runtime adapters. Supported CRUD XML/XSD contracts generate standalone
Java XML model, parser, serializer, and XSD-validation adapters. XML runtime
support for Kafka, passthrough routing, and unsupported XSD features remains
fail-fast until those slices are implemented.

SOAP/WSDL contracts use `type: soap-wsdl` in `upstream_interfaces[]` or
`downstream_interfaces[]`. New SOAP/WSDL entries should use `wsdl_path`; `spec`
is accepted as a compatibility alias for `wsdl_path`, but `spec_url` is not
supported for SOAP/WSDL. Optional `service`, `port`, and `binding` fields select
the WSDL service surface when the WSDL contains multiple choices. The Engine
validates the supported WSDL 1.1 document/literal-wrapped foundation. Supported
CRUD upstream SOAP contracts generate inbound Spring WS endpoint artifacts when
explicit operation mappings are present. Supported CRUD downstream SOAP
contracts generate configurable Spring WS client artifacts under
`app.soap.clients.<interface>.uri`. Unsupported archetypes and unsupported
WSDL/SOAP features remain fail-fast.

Inbound SOAP operation mapping files support adapter-only operation delegation
through `operation_mappings[].operation` and `handler_method`. Missing `mode`
defaults to `adapter_only`. For CRUD apps, operation mappings may also use
`mode: canonical` with `canonical_operation.kind: read_by_id` to generate a
handler that looks up the canonical entity by its persistence ID and maps flat
scalar SOAP response fields. Non-ID lookups, nested complex response paths, and
other canonical operation kinds remain fail-fast until explicitly supported.

Outbound SOAP canonical invocation has metadata-parser and generated runtime
support for the MVP mapping shape in configured CRUD downstream
`invoke_by_id` operations. The MVP keeps mappings under the existing
`downstream_interfaces[].mapping` file and uses
`operation_mappings[].mode: canonical` with
`canonical_operation.kind: invoke_by_id` to load one canonical row by
persistence ID, render a SOAP request from explicit canonical-to-SOAP mappings,
invoke the generated outbound SOAP client, and return mapped SOAP response
fields nested under a `response` object. Missing rows, missing required
canonical values, SOAP Faults, transport failures, and invalid SOAP responses
return deterministic safe error envelopes instead of stack traces or raw SOAP
payloads.

### Operation Rules

If `operations` are present, each operation must contain:

- `name`: non-empty string
- at least one of `request_sample` or `response_sample`
- `pageable`: optional boolean, defaults to `false`

Operation sample paths follow the same local path rules as `samples`.

Selected CRUD GET contracts use the
[support-or-refuse read contract](read-operation-contract.md), independent of
operation-name classification. Single-record reads require an independently
established persistence ID, one correctly typed ID path input and own-resource
binding. Foreign-resource IDs, business keys and ignored nested selectors are
refused. Generic `id` or matching a field name alone is not proof of binding.
Use the existing `identity_overrides.persistence_id` when GET-independent
identity selection is ambiguous. The shipped hyphenated payment route remains supported.

Computed reads retain XR-1's narrower exact ID-name/type and
`/<snake_case_entity>s/{<id_field>}` layout, optional static prefix/suffix and
mapped response fields. Collection reads must be unfiltered or use the existing
explicit pagination mechanism. Declared unsupported query/cookie/body inputs
cannot disappear before validation. Unclassified ordinary headers are refused;
`x-edgeforge-read-input-role: metadata` or `gateway-rate-limit` on the actual
OpenAPI header Parameter Object declares non-record-selection context. This is
canonical metadata, not a new manifest field or version. Classification does
not implement correlation echo, rate limiting, authentication or authorization.
The special `Authorization`, `Accept` and `Content-Type` header declarations
follow OpenAPI handling; source security/media declarations remain separate.

Parameter references resolve locally with bounded cycle/error detection.
Unsupported references, unsafe/unpreservable scoped routes and colliding reads
fail before output mutation. Selected-operation validation precedes context
deduplication, generation, planning and apply, including additive apply's
migration/baseline/rollback boundary. Existing output remains untouched on refusal.
General query semantics, non-read route hardening and object/tenant authorization
are not supplied by this correction. See the linked contract for exact limitations
and the [dated historical audit](external-review-backlog.md#xr-1-adjacent-operation-audit).

`pageable: true` is an additive Phase 3 B7 CRUD option for list-style read
operations. It emits offset/limit pagination using Spring Data `Page<T>`,
`PageRequest`, and `Pageable`. When omitted or set to `false`, generated output
remains unchanged. The option is ignored by the passthrough-router archetype.

## Data Handoff Definitions

Each entry in `data_handoffs` must contain:

- `name`: non-empty string
- `system`: optional non-empty string
- `type`: non-empty string
- `version`: optional string
- `spec`: relative path inside the input project
- `mapping`: optional relative path inside the input project
- `run_semantics`: optional closed M5a-S1 object, only for CRUD `staging-table` handoffs

`data_handoffs[]` is reserved for table/interface-table contracts such as
`staging-table`. File contracts (`file-fixed-width`, `file-csv`) and XML/XSD
contracts (`xml-xsd`) and SOAP/WSDL contracts (`soap-wsdl`) must not be declared
under `data_handoffs[]`; use `upstream_interfaces[]` or
`downstream_interfaces[]` instead.

### Staging run semantics (M5a-S1)

The optional `run_semantics` object recognizes exactly this v1 bundle:

```yaml
run_semantics:
  run_id: caller_supplied
  restart: resume
  dedup_key: [physical_key]
  # internal_schema_id: m5a-staging-001
```

The object is closed: all three required members must be present, `dedup_key` must be non-empty,
and unknown members or unsupported enum combinations fail validation. It is currently supported
only when `app_archetype: crud` and the enclosing handoff has `type: staging-table`;
passthrough-router and Kafka manifests are rejected rather than accepted with the block discarded.

Translation validates the operator DDL and mapping as one contract:

- exactly one recognized physical run-ID column (`run_id` or `eod_run_id`) must exist;
- that column must be `NOT NULL` and use `CHAR`, `VARCHAR`, or `TEXT`, matching the selected
  caller-supplied string run-ID contract;
- every dedup entry must be a unique, simple physical identifier naming a non-operational,
  mapped, `NOT NULL` staging column;
- dedup compatibility is checked against the complete canonical and staging mapping set, independent
  of `data_handoffs[]` order;
- optional `internal_schema_id` values use the positive `m5a-staging-001` ordinal form and must not
  be claimed by more than one handoff. Baseline existence and rename reconciliation begin in S3.

M5a-S1 recognizes and validates this safety contract. M5a-S2/S3 deliver restart and idempotent staging
behavior, so valid opted-in packages may generate, plan, and apply. M5a-S4 grades run-identity harness
findings per handoff: opted-in failures are blocking `ERROR` results while legacy findings remain
advisory `WARNING` results. Omitting `run_semantics` preserves legacy output and harness posture.

## Identity Overrides

`identity_overrides` is an optional additive Phase 3 A1 field. When omitted,
the Engine keeps the existing heuristic `@Id` selection behavior unchanged.

Each entry must contain:

- `entity`: non-empty string matching the canonical entity name
- `persistence_id`: non-empty string matching a field name on that entity

Example:

```yaml
identity_overrides:
  - entity: TransactionPosting
    persistence_id: postingId
```

When present, the declared `persistence_id` wins over the heuristic in
`_select_entity_id_field_name()` and becomes the field with `is_id: true`.
Duplicate entries for the same entity are rejected during manifest validation
before translation. The field is optional and does not change
`schema_version: "2.0"` compatibility.

## Identity Roles

`identity_roles` is an optional additive manifest field for reviewed
non-persistence identity-role metadata. It is currently supported only for
`app_archetype: crud`, because CRUD translation has canonical entity and field
metadata available for reference validation. Passthrough-router and
`kafka-integration` manifests that include `identity_roles` are rejected rather
than accepted and silently ignored.

Each entry must contain:

- `entity`: non-empty string matching a canonical CRUD entity name
- `field`: non-empty string matching a field on that entity
- `role`: one of:
  - `parent_reference`
  - `business_key`
  - `event_id`
  - `idempotency_key`
  - `correlation_id`
  - `external_reference`
- `mode`: either `metadata_only` or `active`
- `policy`: optional object for `metadata_only`; required for `active`

`persistence_id` is intentionally not a valid `identity_roles.role`. Use
top-level `identity_overrides` to select persistence identity.

Mode behavior today:

- `metadata_only`: accepted for CRUD manifests, carried as metadata, and emits
  no Java, DDL, indexes, constraints, finders, logging, idempotency, downstream,
  handoff, or Kafka behavior
- `active`: rejected with a clear unsupported-behavior validation error until a
  future PR implements explicit role/policy behavior

Example:

```yaml
identity_roles:
  - entity: Posting
    field: accountId
    role: parent_reference
    mode: metadata_only

  - entity: Payment
    field: idempotencyKey
    role: idempotency_key
    mode: metadata_only
    policy:
      operations: [createPayment]
      replay_mode: cached_response
      retention_days: 30
      storage: db_table
```

The field is optional and does not change `schema_version: "2.0"`
compatibility.

## ID Generation Overrides

`id_generation_overrides` is an optional additive Phase 3 C9 field. When
omitted, the Engine keeps the existing ID generation behavior unchanged.

Each entry must contain:

- `entity`: non-empty string matching the canonical entity name
- `strategy`: one of `uuid`, `caller_supplied`, `db_identity`, or `db_sequence`
- `field`: optional non-empty string used as a validation guard; if present, it
  must match the selected persistence ID from A1 or the fallback heuristic
- `sequence_name`: required for `db_sequence`; invalid for all other strategies

Strategy meanings:

- `uuid`: server-generated UUID for a string persistence ID
- `caller_supplied`: caller provides the persistence ID in the create request
- `db_identity`: database-generated numeric ID using identity semantics
- `db_sequence`: database-generated numeric ID using a named sequence

Example:

```yaml
identity_overrides:
  - entity: Loan
    persistence_id: loanId
  - entity: LedgerEntry
    persistence_id: entryId

id_generation_overrides:
  - entity: Loan
    field: loanId
    strategy: db_identity
  - entity: LedgerEntry
    field: entryId
    strategy: db_sequence
    sequence_name: ledger_entry_seq
```

Duplicate entries for the same entity are rejected during manifest validation.
The field is optional and does not change `schema_version: "2.0"` compatibility.

## Project Path Fields

These fields must contain relative paths inside the input project:

- interface `spec`
- interface `mapping`
- interface `samples`
- interface operation `request_sample`
- interface operation `response_sample`
- data handoff `spec`
- data handoff `mapping`
- `rules`
- `legacy_references`

Path normalization rules:

- leading `./` is normalized away
- internal `.` segments are removed
- `..` is allowed only when it stays inside the project root after normalization
- absolute paths are rejected

## Future Additive Extensions Under Review

These extensions are **proposed, not implemented**. They are listed here so
future contributors are aware of the direction and do not invent alternative
shapes. The strategic anchor for these extensions is
[docs/edge-contract-expansion-roadmap.md](edge-contract-expansion-roadmap.md);
the XML/XSD-specific proposal is
[docs/edgecontracts/xml-xsd-contract-support-design.md](edgecontracts/xml-xsd-contract-support-design.md).

Versioning principles:

- V2-E makes Engine single-dialect `2.0`, with no post-cut `1.0` bridge. Saved Studio projects will
  reopen/re-export through V2-S; a standalone v1 package follows the reviewed copy-and-version
  conversion defined by the M5a design.
- Proposed extensions target the active `2.0` dialect and remain additive/backward-compatible there.
- Do **not** create another breaking manifest revision unless a separately approved paradigm shift
  requires it. The parked broader semantic redesign is not delivered by the narrow 2.0 cut.
- Do **not** introduce parallel `upstream_contracts[]` /
  `downstream_contracts[]` arrays unless a concrete design proves the
  current `upstream_interfaces[]` / `downstream_interfaces[]` / `data_handoffs[]`
  arrays cannot represent the use case. The existing `type` discriminator is
  the primary extension surface.

Proposed additive concepts (each pending its own design PR):

- **`contract_artifacts[]`** at top level — shared schema artifacts (XSD
  imports, WSDL bundles, Avro schema files) referenced by multiple interfaces.
  XML/XSD v1 should start with direct interface `xsd_path` references; add
  shared artifacts when SOAP/WSDL or another shared-bundle use case needs them.
- **`handoff_topology`** on `downstream_interfaces[]` — enum of `embedded` /
  `staged_external` / `separate_handoff_app` / `external_tool_pack`. Pending
  design in
  [docs/edgecontracts/downstream-handoff-execution-topology-design.md](edgecontracts/downstream-handoff-execution-topology-design.md).
- **Per-`type` required sub-blocks** on `upstream_interfaces[]` /
  `downstream_interfaces[]`:
  - `wsdl_path` when `type: soap-wsdl` (preferred proposed SOAP/WSDL type)
  - `xsd_path` when `type: xml-xsd`; current generic `spec` remains the
    existing field for current non-XML types unless a later schema PR
    deliberately aliases it
  - `avro_schema_path` and optional `schema_registry_url` when `type: kafka-avro`
  - `copybook_path` when `type: file-copybook`
  - other per-type fields as new contract types are added
- **`direction: inbound | outbound`** on `data_handoffs[]` — current support is
  implicit outbound; explicit `direction` is required to model inbound DB
  interface tables.
- **`compatibility_policy`** optional per interface — deferred policy concept
  for declaring contract-change strictness (e.g., `strict` /
  `additive_only` / `advisory`); not part of XML/XSD v1.
- **Richer evidence metadata** on existing Evidence Trail v1.1 evidence types
  (`field` / `mapping` / `validation` / `transform`): `source_artifact`,
  `artifact_type`, `xsd_path`, `xpath`, `wsdl_operation`, `schema_type`,
  `namespace`. A new evidence type will be proposed only if existing types
  enriched with these metadata fields cannot represent contract-artifact
  provenance cleanly.

## Deferred Scope That Must Not Be Assumed Into the Active Dialect

These were not part of the pre-cut v1 contract and remain excluded from the active `2.0` contract
unless introduced later as optional, additive extensions:

- staged downstream topology as a required pattern
- breaking changes to current CRUD semantics
- mandatory pagination wrapper concepts
- mandatory numeric/sequence ID strategy concepts

## Example Manifest

```yaml
app_name: XYZ Accounts Replacement
bounded_context: accounts
schema_version: "2.0"
app_archetype: crud

upstream_interfaces:
  - name: crm-account-api
    system: CRM
    type: rest-json
    version: v1
    spec_url: https://internal.example.com/xyz/swagger.json
    mapping: upstream/crm-account-mapping.yaml
    operations:
      - name: createAccount
        request_sample: upstream/sample-create-account-request.json
        response_sample: upstream/sample-create-account-response.json

downstream_interfaces:
  - name: eod-handoff-file
    system: DOWNSTREAM_APPS
    type: file-fixed-width
    version: v1
    spec: downstream/eod-handoff-layout.yaml
    mapping: downstream/eod-handoff-mapping.yaml
    samples:
      - downstream/sample-output-file.txt

data_handoffs:
  - name: account-staging-table
    system: ETL
    type: staging-table
    version: v1
    spec: data-handoffs/account-staging-table.sql
    mapping: data-handoffs/staging-table-mapping.yaml

rules:
  - rules/account-business-rules.yaml

legacy_references:
  - legacy/xyz-notes.md

target_profile: springboot-legacy-compatible
```
