# XML/XSD Contract Support Design v1

> **Status:** Design proposal.
>
> **Created:** 2026-05-19.
>
> **Scope:** Deterministic XML/XSD edge-contract import, review, canonical
> translation, XML output, validation, and evidence behavior for the EdgeForge
> suite.
>
> **Non-goals:** No Engine implementation, no Studio implementation, no
> Knowledge Server implementation, no TestBench implementation, no generated-app
> runtime change, and no manifest schema artifact change in this PR.
>
> **Strategic anchor:** [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md).
>
> **Related docs:**
> - [Edge-Contract Design Docs](README.md)
> - [Downstream Handoff Execution Topology Design](downstream-handoff-execution-topology-design.md)
> - [Manifest Schema](../manifest-schema.md)
> - [Evidence Trail Design](../evidence-trail-design.md)

## 1. Purpose

XML/XSD support is the foundational Wave 1a substrate for a large class of
enterprise edge contracts:

- standalone XML payloads
- XML file contracts
- SOAP/WSDL message bodies
- ISO 20022 and SWIFT MX profiles
- MQ/JMS XML payloads

The purpose of this design is to define how EdgeForge should ingest and emit
XML/XSD contracts deterministically while preserving the suite's governed
authoring model:

- explicit contract type selection before parsing
- reviewed mappings before generation
- additive manifest evolution
- no hidden AI inference
- generated apps with no EdgeForge, Studio, KA, or KS runtime dependency

SOAP/WSDL layers on this XML/XSD foundation but gets its own design doc. This
document intentionally stops at XML schema and XML payload behavior.

## 2. Problem Statement

Today EdgeForge is strong on REST/OpenAPI, Kafka JSON Schema, fixed-width
downstream files, and staging-table output. It does not yet have a first-class
way to ingest an XSD, review its root elements and schema-derived fields, map
those fields to canonical metadata, or emit XML payloads that preserve a
contracted schema.

Without XML/XSD support, the suite cannot credibly cover:

- SOAP contracts used by legacy enterprise systems
- XML batch files and configuration feeds
- ISO 20022-style message schemas
- XML payloads delivered over MQ/JMS
- XML downstream handoff artifacts

The risk is not just missing parser support. The deeper risk is silent contract
drift: generated Java fields, DTOs, files, or mappings might look plausible but
lose namespace, optionality, cardinality, attribute, enum, or nullability
semantics from the source XSD.

## 3. Role In The Edge-Contract Roadmap

This design is the second Wave 1a edge-contract design doc after downstream
handoff topology.

Wave 1a design sequence:

1. Edge-Contract Expansion Roadmap
2. Downstream Handoff Execution Topology Design
3. XML/XSD Contract Support Design
4. SOAP/WSDL Contract Support Design

XML/XSD is Wave 1a because it is the shared substrate for several later tracks.
It is not the only important contract family: Avro/Protobuf, fixed-width/CSV,
DB-mediated contracts, and SWIFT MT have different substrates. XML/XSD should
therefore be implemented as one contract family, not as a universal parser for
all non-REST formats.

## 4. Design Principles

- **Deterministic first:** XSD parsing and XML sample validation must use
  deterministic parsers and schema validators, not LLM inference.
- **Author reviewed:** Studio users review root selection, fields, mappings,
  and warnings before export.
- **KA OFF is clean:** importing an XSD must not call KS, start background
  suggestion work, or show KA suggestion noise unless KA is explicitly enabled.
- **Additive manifest evolution:** prefer new `type` values and optional
  per-type fields on current manifest arrays. Do not introduce parallel
  `upstream_contracts[]` or `downstream_contracts[]` arrays.
- **One family, all archetypes where applicable:** XML/XSD support is not a
  CRUD-only feature. CRUD, passthrough-router, kafka-integration, and future
  handoff-app archetypes can opt into the same XML/XSD contract model where it
  makes sense.
- **Fail clearly outside v1 scope:** unsupported XSD constructs should produce
  deterministic diagnostics, not best-effort generated code.
- **Runtime independence:** generated apps may use normal XML libraries, but
  never depend on EdgeForge, Studio, KS, KA, or MCP at runtime.

## 5. XSD v1 Scope

XSD is a large language. v1 must be intentionally scoped so the first
implementation is useful, testable, and honest.

### In Scope

XSD v1 should support:

- simple XML Schema scalar types:
  - `xs:string`
  - `xs:int`, `xs:integer`, `xs:long`
  - `xs:decimal`
  - `xs:boolean`
  - `xs:date`
  - `xs:dateTime`
- single-level complex types using `xs:sequence`
- elements and attributes
- `minOccurs` and `maxOccurs`
- basic enumerations
- `nillable`
- same-namespace `xs:include`
- XML sample files for evidence and validation
- namespace-qualified element names mapped through explicit namespace aliases

Single-level complex type support means the selected root element can contain
scalar child elements, attributes, and repeated scalar children. A repeated
complex child can be represented only when the design review maps it to a clear
canonical child collection or handoff record. Deep automatic object graph
generation is out of scope for v1.

### Out Of Scope For v1

XSD v1 should fail fast or mark advisory-only for:

- `xs:choice`
- `xs:all`
- deeply nested complex types beyond the v1 nesting limit
- cross-namespace `xs:import` chains
- substitution groups
- abstract types
- mixed content
- `xs:any`
- `xs:anyAttribute`
- recursive type definitions
- advanced facet combinations
- list/union simple types
- type derivation chains that require inheritance-style model generation

Unsupported constructs should include the source artifact path, schema path,
construct type, and a concrete suggestion such as "split into an explicitly
reviewed mapping" or "defer to the SOAP/WSDL or profile-specific design when
available."

### XSD v1 Complete Means

XSD v1 is complete when a manifest package using only the supported subset can:

1. reference one or more XSD artifacts;
2. select a root element;
3. preserve namespace, optionality, cardinality, attributes, enum, and
   nullability metadata through canonical translation;
4. generate XML parse/serialize behavior where the target archetype supports
   runtime XML behavior;
5. validate at least one sample XML payload against the referenced XSD; and
6. expose evidence links back to XSD element paths using existing Evidence
   Trail types.

## 6. Proposed Manifest Model

Everything in this section is **proposed and not implemented**. The current
schema remains `schema_version: "1.0"` and does not yet accept these fields.

### Type Values

Preferred v1 type value:

- `xml-xsd` - an XML payload or file contract governed by one or more XSD
  artifacts.

Potential future type value:

- `file-xml` - only if delivery-specific file semantics become hard to express
  with `type: xml-xsd` plus handoff/delivery metadata.

Recommendation: start with `type: xml-xsd` and keep file-vs-message delivery
outside the type name when possible. Avoid type proliferation until a concrete
design proves it is needed.

SOAP type values are intentionally not finalized here. The SOAP/WSDL design
will define its own interface type and will reuse this XML/XSD contract model
for message body schemas.

### Shared Contract Artifacts

The roadmap proposes a top-level `contract_artifacts[]` section for shared
schema files. This is useful when the same XSD bundle is referenced by multiple
upstream and downstream interfaces, especially once SOAP/WSDL introduces shared
message schemas and include bundles.

Implementation recommendation for the first XML/XSD slice:

- Start with one direct XSD path on each interface: `xsd_path`.
- Treat `xsd_path` as the proposed XML/XSD-specific path field for new
  `type: xml-xsd` entries.
- Keep the current generic `spec` field for existing contract types unless a
  later manifest/schema PR deliberately aliases it for XML/XSD migration.
- Add `contract_artifacts[]` later, when SOAP/WSDL or another shared-bundle
  use case needs one artifact to be referenced by multiple interfaces.
- Do not block XML/XSD v1 on `contract_artifacts[]`.

Example:

```yaml
schema_version: "1.0"
app_name: account-xml-adapter
bounded_context: accounts
target_profile: springboot-standard-enterprise

contract_artifacts:
  - name: account-status-xsd
    type: xsd
    path: contracts/account-status.xsd
    namespace: "urn:edgeforge:examples:account-status:v1"
    namespace_alias: acct
    includes:
      - contracts/common-types.xsd
```

Design recommendation:

- Use direct `xsd_path` references first for simple one-interface manifests.
- Add `contract_artifacts[]` for shared XSD bundles in the later shared-bundle
  slice, likely alongside SOAP/WSDL.
- Do not require `contract_artifacts[]` for the first XML/XSD implementation.
- Keep artifact paths relative to the manifest package root.
- Keep remote schema resolution out of v1 unless a later design adds an
  explicit trusted URL/cache policy.

### Path Resolution And Precedence

The current manifest interface model already uses `spec` as the generic local
artifact path for existing contract types. XML/XSD introduces a proposed
type-specific `xsd_path`, so the design must be explicit about coexistence.

Recommended precedence:

1. `xsd_ref` references a named item in `contract_artifacts[]`. When present,
   it is the source of truth and direct path fields (`spec` or `xsd_path`) must
   be absent.
2. `xsd_path` is the proposed XML/XSD v1 direct schema path.
3. `spec` is not preferred for new `type: xml-xsd` entries. If an
   implementation temporarily accepts `spec` for XML/XSD compatibility, it must
   treat it as an alias for `xsd_path`; accepting both as independent fields is
   invalid.

Do not let `spec`, `xsd_path`, and `xsd_ref` silently compete. Ambiguous path
configuration should fail before generation.

### Namespace Ownership

Namespace ownership follows the XSD artifact, not the interface row.

Rules:

- For direct path mode, the interface's `xsd_path` points to the XSD artifact.
  The artifact's `targetNamespace` is authoritative.
- For shared artifact mode, `contract_artifacts[].namespace` declares the
  artifact namespace and must match the parsed XSD `targetNamespace`.
- An interface using `xsd_ref` inherits `namespace` and `namespace_alias` from
  the referenced artifact.
- An interface using `xsd_ref` should not repeat `namespace`. If it does, the
  value must match the referenced artifact or Engine must fail validation.
- An interface using direct path mode may include `namespace` as an expected
  namespace assertion. If supplied, it must match the parsed XSD
  `targetNamespace`.

This avoids a subtle class of drift where a reviewer sees one namespace at the
interface level while the artifact actually defines another.

### Upstream XML/XSD Interface

Example upstream XML interface:

```yaml
upstream_interfaces:
  - name: account-status-feed
    system: core-accounting
    type: xml-xsd
    version: "1.0"
    xsd_path: contracts/account-status.xsd
    root_element: AccountStatusMessage
    namespace: "urn:edgeforge:examples:account-status:v1"
    sample: samples/account-status.xml
    mapping: mappings/account-status-to-canonical.yaml
```

Required fields for `type: xml-xsd` should include:

- `name`
- `type: xml-xsd`
- direct path via `xsd_path`
- `root_element`
- `namespace` when using direct path mode and the XSD defines a target namespace

Recommended optional fields:

- `namespace_alias`
- `sample` or `samples`
- `mapping`

Deferred optional fields:

- `validation_policy`
- `compatibility_policy`

These policy fields are intentionally not defined in XML/XSD v1. They need a
separate policy design before implementation.

### Downstream XML/XSD Interface

Example downstream XML output:

```yaml
downstream_interfaces:
  - name: account-confirmation-xml
    system: downstream-servicing
    type: xml-xsd
    version: "1.0"
    xsd_path: contracts/account-confirmation.xsd
    root_element: AccountConfirmation
    namespace: "urn:edgeforge:examples:account-confirmation:v1"
    sample: samples/account-confirmation-example.xml
    mapping: mappings/canonical-to-account-confirmation.yaml
```

Downstream XML interfaces use the same schema metadata as upstream interfaces,
but the mapping direction is canonical -> XML rather than XML -> canonical.

### Shared XSD Used By Multiple Interfaces

Example shared artifact used by inbound and outbound contracts:

```yaml
contract_artifacts:
  - name: common-account-xsd
    type: xsd
    path: contracts/common-account.xsd
    namespace: "urn:edgeforge:examples:account-common:v1"
    namespace_alias: acct

upstream_interfaces:
  - name: account-status-input
    type: xml-xsd
    xsd_ref: common-account-xsd
    root_element: AccountStatusMessage
    mapping: mappings/account-status-input.yaml

downstream_interfaces:
  - name: account-status-output
    type: xml-xsd
    xsd_ref: common-account-xsd
    root_element: AccountStatusResponse
    mapping: mappings/account-status-output.yaml
```

### XML/XSD With Handoff Topology

XML output can pair with the downstream handoff topology design when XML is a
handoff artifact.

Example:

```yaml
downstream_interfaces:
  - name: account-eod-xml
    system: enterprise-etl
    type: xml-xsd
    xsd_path: contracts/account-eod.xsd
    root_element: AccountEodBatch
    namespace: "urn:edgeforge:examples:account-eod:v1"
    mapping: mappings/account-eod-xml.yaml
    handoff_topology:
      mode: external_tool_pack
```

The `handoff_topology` field is proposed by the topology design and is not
implemented today. XML/XSD should use that field rather than inventing a
separate XML-specific topology mechanism.

## 7. XML/XSD To Canonical Translation

The deterministic importer should convert reviewed XSD structures into
canonical metadata without losing XML-specific facts.

### Elements

XSD elements become candidate canonical fields when they are scalar children of
the selected root or reviewed child collection.

Recommended metadata to preserve:

- XML local name
- namespace URI
- namespace alias
- XSD type
- schema path, such as `/AccountStatusMessage/accountId`
- optionality from `minOccurs`
- cardinality from `maxOccurs`
- enum values when present
- nillable flag
- sample XPath when an XML sample is supplied

### Attributes

Attributes become fields with explicit XML-kind metadata.

Example:

```yaml
fields:
  - name: sourceSystem
    type: string
    xml:
      kind: attribute
      xsd_path: /AccountStatusMessage/@sourceSystem
```

Attribute fields must stay distinguishable from element fields so XML output
can serialize them back to attributes.

### Optionality

Recommended mapping:

| XSD signal | Canonical implication |
|---|---|
| `minOccurs="0"` | optional field |
| `minOccurs="1"` or omitted | required field |
| optional attribute | optional field |
| required attribute | required field |

Required/optional metadata should inform validation suggestions, DTO
validation, and generated runtime validation only when the relevant archetype
generates runtime XML behavior.

### Cardinality

Recommended mapping:

| XSD signal | Canonical implication |
|---|---|
| `maxOccurs="1"` or omitted | scalar field |
| `maxOccurs` greater than `1` | repeated field with bounded cardinality |
| `maxOccurs="unbounded"` | repeated field |

Repeated scalar fields can map to list/collection metadata. Repeated complex
fields require explicit review: they may become child entities, handoff record
collections, DTO-only nested structures, or unsupported constructs depending on
the target archetype and mapping.

### Enumerations

Basic `xs:restriction` enumerations should be preserved as allowed values. The
canonical model should carry both:

- the generated Java-safe enum name/value representation; and
- the original XML lexical value.

The original lexical value must be used for XML serialization.

### Nillable And Null Behavior

`nillable="true"` means the XML payload may express null with `xsi:nil="true"`.
It does not automatically mean the canonical database field should be nullable
in every archetype.

Recommended distinction:

- XSD nillable: XML representation can contain explicit nil.
- Canonical nullable: generated app domain or DTO permits null.
- Database nullable: persistence column permits null.

These should be reviewed separately when the generated app persists the value.

### Type Mapping

Recommended initial mapping:

| XSD type | Canonical type | Java direction |
|---|---|---|
| `xs:string` | string | `String` |
| `xs:int`, `xs:integer` | integer | `Integer` / `Long` by range |
| `xs:long` | long | `Long` |
| `xs:decimal` | decimal | `BigDecimal` |
| `xs:boolean` | boolean | `Boolean` |
| `xs:date` | date | `LocalDate` |
| `xs:dateTime` | datetime | `OffsetDateTime` when timezone is present; otherwise reviewed default |

Do not silently coerce ambiguous date/time formats from samples. Use XSD type
as the primary source and surface sample conflicts as warnings.

## 8. Canonical To XML Output

XML output support should preserve schema intent instead of treating XML as
plain string concatenation.

### Serialization Expectations

Generated XML output should:

- select the reviewed `root_element`
- emit the configured namespace and namespace prefix/alias
- emit attributes as attributes and elements as elements
- serialize enum lexical values exactly as defined by the XSD
- format dates, datetimes, decimals, and booleans according to XML Schema
  lexical rules
- validate generated samples against the referenced XSD in tests

Implementation can choose JAXB, Jackson XML, or another maintained Java XML
library by target profile, but the generated output must not depend on
EdgeForge runtime libraries.

### Namespace Handling

The manifest should preserve:

- namespace URI
- optional namespace alias/prefix
- root element namespace
- included XSD namespace assumptions

The generated app should not invent prefixes that make review or evidence
harder. Prefixes may differ in XML semantics, but stable generated prefixes are
important for fixture comparison and reviewer trust.

### Omitted, Empty, And Nil Fields

The mapper must distinguish:

| Situation | XML output behavior |
|---|---|
| optional value absent | omit element/attribute unless mapping says otherwise |
| present empty string | emit empty text value |
| nillable null | emit `xsi:nil="true"` only when reviewed mapping requires explicit nil |
| required value absent | validation error before output |

Silent conversion between omitted, empty, and nil values is contract drift.

## 9. Validation Boundaries

### Import-Time Validation

Studio or the importer should validate:

- XSD is well-formed XML
- referenced `xs:include` files are present
- selected root element exists
- `spec`, `xsd_path`, and `xsd_ref` do not conflict
- asserted interface namespace matches the parsed XSD namespace
- unsupported constructs are reported deterministically
- sample XML files, when supplied, are well formed and validate against the XSD

Import-time validation should not require KA/KS.

### Studio Review-Time Warnings

Studio should surface warnings for:

- unsupported XSD constructs
- repeated complex children requiring modeling decisions
- ambiguous namespace aliasing
- sample payload fields not represented in the selected root schema
- XSD-required fields missing from samples
- possible canonical field naming conflicts
- conflicting field semantics across multiple contract artifacts

Warnings should be reviewable. They should not silently disappear during export.

### Engine Generation-Time Validation

Engine should validate manifest/package references before generation:

- `xsd_path` or `xsd_ref` resolves inside the package
- `root_element` exists
- `namespace` matches the referenced artifact when required
- `xsd_ref` inheritance does not conflict with interface-level namespace values
- mapping paths exist
- unsupported constructs did not bypass Studio
- archetype-specific XML runtime support exists before emitting XML runtime code

If a manifest asks an archetype to generate XML behavior it does not support
yet, Engine should fail with a clear diagnostic.

### Generated-App Runtime Validation

Generated-app runtime XML validation is applicable only when the generated app
parses or emits XML at runtime.

Recommended policy:

- inbound XML parsing should validate against the XSD by default when an XSD is
  packaged with the generated app;
- outbound XML generation should validate in tests and optionally at runtime
  based on a profile/config flag;
- high-volume paths may disable runtime validation only through explicit
  generated-app configuration, not by silently skipping validation;
- validation failures should map to the generated app's standard error contract
  or router NACK taxonomy, depending on archetype.

## 10. Studio Import And Review UX

Studio should make XML/XSD import deterministic and explicit.

Preferred flow:

```text
Select contract type: XML/XSD
-> choose source: upload / file path / trusted package path
-> choose XSD file and optional XML samples
-> deterministic parse
-> select root element/type
-> review derived fields, attributes, enums, optionality, cardinality
-> review mappings to canonical entities/fields
-> save/export manifest
```

UX requirements:

- User selects contract type before loading/parsing.
- Upload/select XSD files and optional samples before parse.
- Root element/type selection is explicit.
- If the XSD has exactly one global element, Studio may preselect it but should
  still show the selection and require normal review before export.
- If the XSD has multiple global elements, Studio must require the user to pick
  one root element.
- If the XSD has no global element but has named complex types, Studio must ask
  for an explicit root/wrapper decision instead of guessing.
- Derived fields show whether they came from element or attribute.
- Optional/repeated/nillable/enum markers are visible.
- XML namespace and root element are visible.
- Unsupported constructs are shown as clear warnings/errors.
- Mappings are reviewed before export.
- KA OFF remains clean:
  - no hidden KS calls
  - no suggestion drawers opened by import
  - no background inference
  - no stale KA state created by deterministic import

KA-enabled suggestions can be layered later, but the base import/review path
must work fully with KA OFF.

## 11. KA / KS Future Behavior

Knowledge Assist can later help with XML/XSD review, but only as advisory,
reviewed suggestions.

Potential future KS suggestion scopes:

- canonical field naming from XSD element names and annotations
- mapping suggestions from XSD element paths to canonical fields
- identity role suggestions from XSD names plus DDL/OpenAPI evidence
- validation suggestions from XSD required/enumerated fields
- conflict warnings when XSD, OpenAPI, DDL, or file layouts disagree

Rules:

- XSD parsing itself is deterministic and does not require KS.
- KA suggestions must never silently apply schema mappings.
- Every KA suggestion requires user accept/edit/reject.
- KA OFF must not perform live KS calls.
- Evidence should cite XSD paths, XML sample XPaths, and source artifacts.

## 12. Generated App Implications By Archetype

XML/XSD is a suite-level contract family. Each archetype should opt in only
where the behavior is meaningful.

### CRUD

Potential CRUD uses:

- XML request/response DTOs for declared XML endpoints in future interface
  designs
- XML downstream handoff output
- XML file ingestion feeding canonical entities in future inbound-file work
- XSD-derived validation metadata

CRUD persistence should not automatically mirror XML nesting. Entity modeling
still goes through reviewed canonical metadata.

### Passthrough Router

Potential passthrough-router uses:

- validate inbound XML payloads against XSD
- transform XML source payloads to downstream XML or JSON payloads
- preserve namespace/root/attribute semantics
- return validation failures through the router error contract

Passthrough XML behavior should not require persistence.

### Kafka Integration

Kafka routes may carry XML payloads over string or byte topics. XML/XSD support
could enable:

- XSD validation of XML message payloads
- XML-to-JSON or XML-to-XML transform mappings
- downstream XML message generation
- schema evidence for transform mappings

This is distinct from Avro/Schema Registry support. XML-over-Kafka uses XML/XSD
validation and serialization; Avro uses schema-registry serde.

### Future Handoff App

The future `file-handoff` or batch-handoff archetype can use XML/XSD for:

- reading staging/canonical data
- emitting XML handoff files
- producing external tool packs with XSD, mapping specs, and samples
- validating generated XML files before delivery

The topology mode should come from the downstream handoff topology design, not
from XML-specific fields.

## 13. Relationship To SOAP/WSDL And Future Profiles

SOAP/WSDL is out of scope for this document.

This design owns:

- XSD artifact handling
- XML root/type selection
- XML field/attribute/cardinality translation
- XML parse/serialize expectations
- XML evidence metadata

The SOAP/WSDL design owns:

- WSDL import
- service, port, binding, and operation modeling
- SOAP body/header/fault mapping
- inbound SOAP endpoint generation
- outbound SOAP client generation
- SOAP-specific error/fault behavior
- SOAP transport and binding scope

Future ISO 20022 and SWIFT MX profile designs should layer on the XML/XSD
foundation. They should add profile-specific naming, message selection,
validation, and evidence rules without weakening the base XML/XSD semantics.

## 14. Evidence Trail Behavior

Evidence Trail v1.1 already supports the main evidence categories needed for
XML/XSD:

- `field`
- `mapping`
- `validation`
- `transform`

Do not add a new evidence type by default. Reuse existing evidence types and
add richer metadata when the source is an XML/XSD artifact.

Proposed additive metadata:

```yaml
evidence:
  - type: field
    entity: AccountStatus
    field: accountId
    source_artifact: contracts/account-status.xsd
    artifact_type: xsd
    xsd_path: /AccountStatusMessage/accountId
    xpath: /acct:AccountStatusMessage/acct:accountId
    namespace: "urn:edgeforge:examples:account-status:v1"
    root_element: AccountStatusMessage
```

Metadata fields:

- `source_artifact`
- `artifact_type: xsd`
- `xsd_path`
- `xpath`
- `namespace`
- `root_element`

Decision rule: introduce a new evidence type only if a future XML/SOAP profile
cannot be represented by `field`, `mapping`, `validation`, or `transform` plus
metadata.

## 15. Test And Fixture Expectations

### Design-Time / Engine Unit Tests

Future Engine implementation should include focused tests for:

- valid XSD parse with simple types
- same-namespace `xs:include`
- element vs attribute mapping
- `minOccurs`/`maxOccurs`
- enum preservation
- nillable metadata
- unsupported `xs:choice` diagnostic
- unsupported cross-namespace `xs:import` diagnostic
- missing root element diagnostic
- missing XSD artifact diagnostic
- sample XML validates against XSD
- sample XML fails against XSD with clear diagnostic

### Golden Generated-Output Fixtures

Golden fixtures should prove:

- generated DTOs/models carry correct XML annotations or equivalent metadata
- XML output preserves root element and namespace
- attributes serialize as attributes
- optional omitted values stay omitted
- nillable fields serialize as `xsi:nil` only when configured
- enum lexical values round trip
- generated app build succeeds

At least one fixture should include both JSON/OpenAPI and XML/XSD contracts in
one package to prove mixed contract types remain supported.

### TestBench Runtime Proof

TestBench proof is required only when meaningful runtime behavior is generated.

Examples that justify TestBench:

- generated passthrough-router validates an XML payload and emits a downstream
  XML payload
- generated Kafka route validates XML-over-Kafka payloads
- future handoff app emits an XML file and validates it

Examples that do not require TestBench:

- parser-only import
- manifest validation only
- external tool pack export with no generated runtime behavior

## 16. Implementation Slices

No implementation happens in this PR. Proposed future slices:

| Slice | Scope | Repo(s) |
|---|---|---|
| 0 | Design doc only | EdgeForge docs |
| 1 | Additive manifest/schema contract for XML/XSD references | EdgeForge |
| 2 | Deterministic XSD parser/importer | EdgeForge |
| 3 | Studio import/review surface with explicit type selection | EdgeForgeStudio |
| 4 | Engine translation to canonical metadata | EdgeForge |
| 5 | XML output serialization and validation support | EdgeForge |
| 6 | Evidence Trail source mapping metadata | EdgeForge + Studio as needed |
| 7 | Golden generated-output fixtures | EdgeForge |
| 8 | TestBench/runtime proof only where XML runtime behavior is generated | EdgeForgeTestBench |
| 9 | KA/KS advisory suggestions for XML/XSD mappings and warnings | EdgeForgeKnowledgeServer + EdgeForgeStudio |

Recommended sequencing:

1. Lock this design.
2. Write SOAP/WSDL design using this document as its XML substrate.
3. Implement the smallest XML/XSD end-to-end slice before adding profile
   standards such as ISO 20022 or SWIFT MX.
4. Keep KA/KS suggestion work after deterministic import/review works with KA
   OFF.

## 17. Open Questions

- At which SOAP/WSDL or shared-bundle slice should `contract_artifacts[]` be
  introduced after the first direct-`xsd_path` XML/XSD implementation?
- Should the canonical XML metadata live on fields directly, or in a
  sidecar mapping structure referenced by mappings and emitters?
- Which Java XML library should each target profile use for XML serialization
  and validation?
- Should inbound runtime XSD validation be always on by default, or should high
  volume profiles default to test-time validation plus opt-in runtime
  validation?
- How should repeated complex children be represented in the canonical model
  when they are DTO-only and not persistent entities?
- Should namespace prefixes be user-selected in Studio, generated
  deterministically, or both?
- How much XML sample evidence should be exported in Evidence Trail without
  leaking sensitive sample payload values?
- Should XML/XSD support introduce a soft `schema_version: "1.1"` marker for
  validation routing, even if the manifest change is additive?
