# Edge-Contract Design Docs

This folder owns upstream/downstream edge-contract design docs for the
EdgeForge suite.

The strategic anchor for this folder is:

- [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md) —
  suite-level roadmap; contract type families, waves, manifest evolution
  principles, and implementation rules.

## v1 Implemented Status

The v1 edge-contract runtime lane is implemented and smoke-proven for the
current Engine/Studio scope:

- file fixed-width and CSV/delimited ingest/output, including fixed-width
  outbound trailer generation and fixed-width/CSV inbound trailer
  record-count/sum reconciliation;
- XML/XSD explicit mapped CRUD ingest/output runtime;
- SOAP/WSDL inbound canonical `read_by_id` and outbound canonical
  `invoke_by_id` runtime;
- generated-app test-console cards for CRUD, batch, file, XML, and SOAP
  actions through the Slice 3c input-hints/sample-fill work;
- Studio Evidence Trail metadata export for file, XML/XSD, and SOAP/WSDL
  provenance through Studio PRs `#190`--`#193`, reusing Evidence Trail v1.1
  types and excluding identity-role evidence.

The final integrated Studio -> Engine v1 runtime smoke passed on 2026-06-09.
See [edge-contract integrated v1 smoke results](../test-results/edge-contract-integrated-v1-smoke-2026-06-09.md)
for the exact package paths, SHAs, positive paths, negative paths, and the
non-blocking Spring Batch schema-init runtime note.

For the per-family supported-surface status — what is proven vs future, with
re-runnable in-repo evidence and the honest caveats — see the
[Edge-Contract Handoff Readiness Matrix](edge-contract-handoff-readiness-matrix.md).

## Wave 1a Design Docs

- [Downstream Handoff Execution Topology Design](downstream-handoff-execution-topology-design.md)
  — defines the four handoff topology modes: `embedded` / `staged_external` /
  `separate_handoff_app` / `external_tool_pack`. First substantive design PR
  after the roadmap anchor.
- [XML/XSD Contract Support Design](xml-xsd-contract-support-design.md) —
  foundational XSD/XML ingest and emit; unblocks SOAP, ISO 20022, SWIFT MX, and
  MQ XML payloads.
- [SOAP/WSDL Contract Support Design](soap-wsdl-contract-support-design.md) —
  layered on XSD; v1 scoped to document/literal-wrapped binding only.
- [SOAP Canonical Operation Mapping MVP Design](soap-canonical-operation-mapping-mvp-design.md) —
  explicit inbound SOAP operation mapping from reviewed WSDL request/response
  shapes to generated canonical `read_by_id` behavior; keeps adapter-only mode
  valid.
- [Outbound SOAP Canonical Invocation MVP Design](outbound-soap-canonical-invocation-mvp-design.md) —
  explicit downstream SOAP action mapping from canonical rows to generated
  outbound SOAP client invocation using `invoke_by_id`; keeps outbound SOAP
  scaffold/runtime invocation sequencing honest.
- [Generated-App SOAP Operator Dashboard Actions Design](generated-soap-operator-actions-design.md) —
  generated-app UX design: exposes inbound `/ws` and outbound
  `/soap/outbound/{contractName}/{operationName}` runtime paths as
  operator-dashboard action cards (matching the existing CRUD/batch/file/XML
  cards), with no TestBench or EdgeForge runtime dependency. Implemented as
  generated test-console SOAP cards via PR `#201`.

## Wave 1b Design Docs

- [CSV/Delimited and Fixed-Width File Contract Design](csv-fixed-width-file-contract-design.md) —
  inbound and outbound file contracts for CSV/delimited and fixed-width formats;
  extends existing `file-fixed-width` downstream support with inbound parsing,
  CSV support, and control/trailer/reconciliation records. Engine
  implementation is current through fixed-width and CSV inbound trailer
  reconciliation.
- [Edge-Contract Evidence Trail Metadata Design](edge-contract-evidence-trail-metadata-design.md) —
  additive Evidence Trail metadata contract for file, XML/XSD, and SOAP/WSDL
  provenance; implemented in Studio export for the v1 file, XML/XSD, and
  SOAP/WSDL scope while keeping `evidence-trail.json` separate from Engine
  runtime and generated apps.

## Deferred Design Docs

- `avro-schema-registry-contract-support-design.md` — Kafka Avro / Schema
  Registry ingest and producer; opt-in runtime dependency. Deferred until file
  contracts and XML/SOAP implementation are stable (see issue #167).

## Not In This Folder

- `docs/generated-app-standards/high-tps-entity-profile-design-v1.md` —
  generated-app runtime/scale design; not an edge-contract concern.
- `docs/generated-app-standards/identity-role-engine-behavior-design.md` —
  generated-app manifest behavior; not an edge-contract concern.
- `docs/generated-app-standards/cross-service-integration-design.md` —
  microservice-to-microservice integration within the same estate; see section 10
  of the roadmap for the cross-service vs edge-contract ownership boundary.
