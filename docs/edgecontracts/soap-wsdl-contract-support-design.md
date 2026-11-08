# SOAP/WSDL Contract Support Design v1

> **Status:** Design proposal.
>
> **Created:** 2026-05-19.
>
> **Scope:** Deterministic SOAP/WSDL edge-contract import, review, inbound
> endpoint generation, outbound client generation, SOAP fault mapping, Evidence
> Trail metadata, and generated-app validation behavior for the EdgeForge suite.
>
> **Non-goals:** No Engine implementation, no manifest schema JSON
> implementation, no Studio implementation, no Knowledge Server implementation,
> no TestBench implementation, no generated-app runtime change, and no
> domain-specific behavior in this PR.
>
> **Strategic anchor:** [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md).
>
> **Layered dependency:** [XML/XSD Contract Support Design](xml-xsd-contract-support-design.md).
>
> **Related docs:**
> - [Edge-Contract Design Docs](README.md)
> - [Downstream Handoff Execution Topology Design](downstream-handoff-execution-topology-design.md)
> - [XML/XSD Contract Support Design](xml-xsd-contract-support-design.md)
> - [Outbound SOAP Canonical Invocation MVP Design](outbound-soap-canonical-invocation-mvp-design.md)
> - [Manifest Schema](../manifest-schema.md)
> - [Evidence Trail Design](../evidence-trail-design.md)

## 1. Purpose

SOAP/WSDL is the largest unaddressed enterprise upstream contract
family in the current EdgeForge roadmap. It is not just XML with an envelope.
SOAP/WSDL adds service, port, binding, operation, header, body, and fault
semantics on top of XML/XSD schemas.

The purpose of this design is to define how EdgeForge should ingest WSDL
contracts, review operation surfaces, map SOAP request/response/fault shapes,
and generate Spring Boot services or clients while preserving the governed
authoring model:

- deterministic WSDL/XSD parsing;
- explicit service/port/binding/operation selection;
- reviewed mappings before generation;
- clear unsupported-binding diagnostics;
- Evidence Trail links back to WSDL, XSD, SOAP body/header/fault paths, and
  samples;
- generated apps with no EdgeForge, Studio, KA, KS, or MCP runtime dependency.

## 2. Problem Statement

Many enterprise modernization efforts need to preserve existing SOAP contracts
while replacing or mediating the application behind them. A generated
replacement app must not casually drift from the WSDL:

- wrong operation name or SOAPAction breaks clients;
- wrong namespace breaks payload parsing;
- treating SOAP headers as normal body fields loses contract meaning;
- ignoring SOAP faults turns business failures into generic exceptions;
- unsupported WSDL bindings can produce plausible but unusable code.

EdgeForge must model SOAP/WSDL as a governed edge contract, not as best-effort
XML parsing or generic app scaffolding.

## 3. Relationship To XML/XSD

SOAP/WSDL layers on the XML/XSD design and must not redefine it.

XML/XSD owns:

- XSD artifact handling;
- XML root/type selection;
- namespaces, elements, attributes, optionality, cardinality, and nillable
  semantics;
- XML validation;
- XML evidence metadata such as `xsd_path`, `xpath`, `namespace`, and
  `root_element`.

SOAP/WSDL owns:

- WSDL service, port, binding, and operation modeling;
- SOAP body, header, and fault mapping;
- SOAPAction preservation;
- inbound SOAP endpoint behavior;
- outbound SOAP client behavior;
- SOAP fault and error semantics;
- operation-level Studio review.

SOAP implementation must reuse XML/XSD parsing and validation for message
schemas. If the underlying XSD construct is outside XML/XSD v1 scope, SOAP/WSDL
v1 must fail clearly rather than trying to bypass the XML/XSD boundary.

## 4. SOAP/WSDL v1 Scope

### In Scope

SOAP/WSDL v1 should support:

- WSDL 1.1;
- document/literal-wrapped binding only;
- HTTP transport;
- one selected service/port/binding per interface entry;
- synchronous request/response operations;
- operation request body elements;
- operation response body elements;
- basic SOAP headers declared in WSDL;
- SOAP faults declared in WSDL;
- local WSDL with local XSD imports/includes inside the package;
- sample SOAP request, response, and fault payloads for validation/evidence;
- deterministic diagnostics for unsupported bindings or policy constructs.

### Out Of Scope For v1

SOAP/WSDL v1 should reject or mark unsupported:

- RPC/encoded;
- RPC/literal;
- document/literal-bare unless explicitly approved in a later v1.1 design;
- WS-Security;
- WS-Policy and WS-SecurityPolicy;
- MTOM and SwA attachments;
- WS-Addressing;
- WS-ReliableMessaging;
- asynchronous SOAP callbacks;
- one-way callback flows;
- multiple-port automatic generation;
- cross-namespace import chains beyond the XML/XSD v1 supported subset;
- automatic business logic extraction from SOAP operation names.

Unsupported constructs must produce diagnostics that name the WSDL artifact,
service, port, binding, operation, and unsupported construct where possible.

## 5. Proposed Manifest Model

Everything in this section is **proposed and not implemented**. The current
manifest schema remains `schema_version: "1.0"` and does not yet accept these
fields.

### Type Name Decision

Preferred proposed type value:

- `soap-wsdl`

Rationale:

- the contract source is WSDL, not arbitrary SOAP payloads;
- WSDL selection drives service, port, binding, operation, body, header, and
  fault modeling;
- the name avoids confusion with future raw SOAP envelope routing or
  SOAP-over-non-WSDL scenarios;
- it aligns with the edge-contract roadmap's "SOAP/WSDL" label.

Do not introduce a parallel `upstream_contracts[]` or `downstream_contracts[]`
array. Use existing `upstream_interfaces[]` and `downstream_interfaces[]` with
type-specific fields.

### Upstream SOAP/WSDL Interface

Proposed inbound SOAP interface:

```yaml
upstream_interfaces:
  - name: account-service-soap
    system: legacy-core
    type: soap-wsdl
    version: "1.0"
    wsdl_path: contracts/account-service.wsdl
    service: AccountService
    port: AccountServiceSoap11Port
    binding: AccountServiceSoap11Binding
    operations:
      - name: GetAccount
        soap_action: "urn:accounts:GetAccount"
        request_element: acct:GetAccountRequest
        response_element: acct:GetAccountResponse
        request_sample: samples/get-account-request.xml
        response_sample: samples/get-account-response.xml
        fault_samples:
          - samples/get-account-not-found-fault.xml
        mapping: mappings/get-account-soap-to-canonical.yaml
        fault_mapping: mappings/get-account-faults.yaml
```

Expected future behavior:

- generated app exposes an inbound SOAP endpoint for selected operations;
- body fields map to reviewed canonical request/response DTOs;
- headers map only when explicitly reviewed;
- declared faults map to reviewed error/fault behavior.

### Downstream SOAP/WSDL Interface

Proposed outbound SOAP client:

```yaml
downstream_interfaces:
  - name: account-core-soap-client
    system: account-core
    type: soap-wsdl
    version: "1.0"
    wsdl_path: contracts/account-core.wsdl
    service: AccountCoreService
    port: AccountCoreSoap11Port
    binding: AccountCoreSoap11Binding
    operations:
      - name: UpdateAccountStatus
        soap_action: "urn:accounts:UpdateAccountStatus"
        request_element: acct:UpdateAccountStatusRequest
        response_element: acct:UpdateAccountStatusResponse
        request_sample: samples/update-account-status-request.xml
        response_sample: samples/update-account-status-response.xml
        fault_samples:
          - samples/update-account-status-fault.xml
        mapping: mappings/canonical-to-update-account-status-soap.yaml
        fault_mapping: mappings/update-account-status-faults.yaml
```

Expected future behavior:

- generated app creates an outbound SOAP client for selected operations;
- canonical/domain data maps to SOAP request body and reviewed headers;
- SOAP response maps back to canonical response/error paths;
- SOAP faults preserve fault evidence and are classified deterministically.

### Version Posture

`type: soap-wsdl` is an additive proposed type under the manifest v1 family.
The preferred implementation path is to keep it compatible with
`schema_version: "1.0"`. A soft `schema_version: "1.1"` marker is acceptable if
Engine validation needs to distinguish SOAP-aware manifests from legacy
manifests for clarity or routing. A breaking manifest v2 is not justified.

### Path Resolution And Precedence

The current manifest interface model already has generic `spec` fields.
SOAP/WSDL introduces the proposed type-specific `wsdl_path`, so path resolution
must avoid ambiguous competing sources.

Recommended precedence:

1. Future `wsdl_ref` references a named WSDL artifact in `contract_artifacts[]`.
   When present, direct path fields such as `spec` and `wsdl_path` must be
   absent.
2. `wsdl_path` is the proposed SOAP/WSDL v1 direct WSDL path.
3. `spec` is not preferred for new `type: soap-wsdl` entries. If an
   implementation temporarily accepts `spec` for compatibility, it must treat
   it as an alias for `wsdl_path`; accepting both as independent fields is
   invalid.

Do not let `spec`, `wsdl_path`, and future `wsdl_ref` silently compete.
Ambiguous path configuration should fail before generation.

## 6. WSDL Artifact Handling

### Direct `wsdl_path` First

SOAP/WSDL v1 should start with direct local `wsdl_path` references:

- WSDL path is relative to the manifest package root.
- WSDL imports/includes must resolve within the package.
- Referenced XSD files are parsed through XML/XSD support.
- Remote WSDL resolution is out of scope for v1 unless a later trusted cache
  policy is designed.

### Relationship To `contract_artifacts[]`

The XML/XSD design recommends starting with direct `xsd_path` and adding
`contract_artifacts[]` when shared bundles need it. SOAP/WSDL should follow the
same rule:

- first SOAP slice uses direct `wsdl_path`;
- shared WSDL/XSD bundles can introduce `contract_artifacts[]` later if needed;
- do not block SOAP/WSDL v1 design on shared artifact indirection.

Future `wsdl_ref` should be introduced only when `contract_artifacts[]` exists
and can model WSDL/XSD bundles cleanly.

### Namespace Ownership

Namespace ownership follows the WSDL and referenced XSD artifacts:

- WSDL target namespace owns service, port, binding, and operation names;
- referenced XSD target namespaces own body/fault/header element structures;
- manifest-level namespace assertions, if added later, must match parsed
  artifacts or fail validation;
- generated code must not invent operation or namespace names.

## 7. Inbound SOAP Endpoint Design

Inbound SOAP support turns selected WSDL operations into generated endpoint
methods.

Design direction:

- WSDL operation maps to a generated endpoint method.
- SOAP request body maps to a reviewed request DTO or command input.
- SOAP response body maps to a reviewed response DTO.
- SOAP headers map to explicit reviewed fields only.
- SOAP faults map to generated fault/error responses.
- Generated endpoints must not expose JPA entities.
- Endpoint generation must preserve WSDL operation name, namespace,
  SOAPAction, and request/response elements.

Unsupported or unselected WSDL operations must not accidentally generate
partial endpoint methods.

## 8. Outbound SOAP Client Design

Outbound SOAP support turns a downstream SOAP interface into a generated client.

Design direction:

- canonical/domain inputs map to SOAP request body and reviewed headers;
- SOAP response maps to canonical response or service result;
- declared SOAP faults map to reviewed business errors or generated fault
  handling;
- unknown SOAP faults map to technical errors;
- timeout/retry configuration is deferred out of SOAP/WSDL v1 runtime
  generation unless a dedicated implementation design defines it;
- generated clients must not depend on EdgeForge runtime libraries.

Do not silently inherit generic REST/Kafka retry semantics for SOAP. Until a
SOAP-specific timeout/retry policy is designed, generated SOAP clients should
use safe framework defaults and clearly generated configuration placeholders
only when an implementation PR deliberately adds outbound client behavior.

## 9. Operation And Mapping Review

Studio must treat SOAP review as a first-class contract review surface.

Required review concepts:

- WSDL service list;
- WSDL port list;
- binding list and support status;
- operation list;
- SOAPAction;
- request body element;
- response body element;
- declared headers;
- declared faults;
- request/response/fault samples;
- mapping files and mapping status.

User decisions:

- select service/port/binding when multiple exist;
- select included operations;
- review request mappings;
- review response mappings;
- review fault mappings;
- review headers separately from body fields.

Headers must never be silently flattened into body fields.

### Multi-Operation Canonical Mapping

A single WSDL often contains multiple operations that reference the same
business concept, such as `GetAccount`, `UpdateAccount`, and `CloseAccount`.
EdgeForge should not infer a new canonical entity per operation by default.

Design direction:

- operations in the same WSDL may map to shared canonical entities and fields;
- each operation owns its own request, response, header, and fault mapping;
- shared canonical fields should preserve per-operation evidence links so
  reviewers can see which WSDL operation contributed each mapping;
- conflicting operation shapes for the same canonical field should surface as
  source-contract conflicts, not silent last-writer-wins metadata;
- operation-specific DTOs may exist even when canonical entities are shared.

This keeps WSDL operation review explicit while avoiding duplicated canonical
models for every SOAP operation.

## 10. Fault And Error Semantics

SOAP faults are contract objects, not generic exceptions.

Design direction:

- declared WSDL faults become reviewed fault mappings;
- known business faults map to generated business errors or SOAP fault
  responses depending on direction;
- unknown SOAP faults become technical errors;
- fault code, fault string/reason, detail element, namespace, and sample XPath
  should be preserved as evidence;
- inbound generated endpoints should emit reviewed SOAP faults for known
  business failures where the WSDL declares them;
- outbound generated clients should map known SOAP faults into generated
  service-layer errors without losing fault evidence.

Fault behavior must be deterministic. Do not infer business meaning from fault
names without reviewed mapping.

## 11. Validation Boundaries

### Import-Time Validation

Importer/Studio should validate:

- WSDL is well formed;
- WSDL 1.1 structure is present;
- selected service/port/binding exists;
- selected binding is document/literal-wrapped;
- HTTP transport is used;
- selected operations exist;
- request/response/fault elements resolve to XML/XSD-supported schemas;
- local imports/includes resolve within the package;
- samples are well formed SOAP envelopes;
- samples match selected operation body/fault elements where supplied.

### Studio Review-Time Warnings

Studio should surface warnings for:

- unsupported bindings;
- multiple services/ports needing selection;
- missing SOAPAction;
- declared headers without reviewed mapping;
- declared faults without reviewed classification;
- sample payloads that do not match selected operation;
- XSD constructs outside XML/XSD v1 scope.

### Engine Generation-Time Validation

Engine should validate before generation:

- `wsdl_path` resolves inside the package;
- selected service/port/binding/operation exists;
- binding support is in v1 scope;
- mapping paths exist;
- request/response/fault elements are resolvable;
- selected archetype supports requested SOAP behavior;
- unsupported constructs fail clearly.

### Runtime Validation

Runtime validation applies only when generated SOAP behavior exists:

- inbound SOAP request validation should be enabled by default when WSDL/XSD is
  packaged;
- outbound SOAP response/fault validation should be test-backed and optionally
  runtime-configurable;
- high-volume paths may tune validation only through explicit generated-app
  configuration;
- failures must map to the generated app's standard error/fault semantics.

## 12. Studio UX

Preferred import/review flow:

```text
Select contract type: SOAP/WSDL
-> choose WSDL and optional samples
-> deterministic parse
-> select service / port / binding
-> review supported and unsupported operations
-> select included operations
-> review body, header, and fault mappings
-> save/export manifest
```

UX requirements:

- user selects contract type before loading/parsing;
- upload/select WSDL and sample payloads;
- show service/port/binding choices explicitly;
- show binding support status;
- show operation list with include/exclude decisions;
- show headers separately from body fields;
- show faults separately from generic errors;
- show request/response/fault mapping status;
- preserve KA OFF cleanliness:
  - no hidden KS calls;
  - no suggestion drawers opened by import;
  - no background inference;
  - no stale KA state created by deterministic import.

SOAP review UX is sensitive because existing SOAP contracts are often treated
as immutable. Studio must make it obvious when EdgeForge is preserving a WSDL
contract versus proposing a mapping decision.

## 13. KA / KS Future Behavior

Knowledge Assist may later suggest SOAP/WSDL review decisions, but only as
advisory reviewed suggestions.

Potential future suggestion scopes:

- operation grouping;
- canonical field mapping from SOAP body paths;
- header classification;
- identity role hints from WSDL/XSD names plus other evidence;
- fault classification;
- validation hints from XSD-required fields and WSDL faults.

Rules:

- WSDL parsing is deterministic and does not require KS.
- KA must not silently infer or apply operation mappings.
- KA must not silently classify faults.
- KA OFF must not perform live KS calls.
- Evidence should cite WSDL service, port, binding, operation, SOAPAction,
  SOAP body/header/fault path, XSD path, XPath, namespace, and samples.

## 14. Generated App Implications By Archetype

### CRUD

Potential CRUD use:

- generated SOAP inbound facade around reviewed canonical operations;
- generated SOAP outbound client from downstream interface;
- SOAP request/response DTOs mapped to canonical metadata;
- SOAP faults mapped to generated error/fault behavior.

CRUD persistence identity and entity design still flow through canonical
metadata. SOAP names do not automatically define persistence identity or
business logic.

### Passthrough Router

Potential passthrough-router use:

- SOAP passthrough route with validation;
- SOAP-to-SOAP transform route;
- SOAP-to-REST or REST-to-SOAP mediation where mappings are explicit;
- SOAP fault preservation across the route.

This should be a later implementation slice after base SOAP import/review is
stable.

### Kafka Integration

Kafka-router integration with SOAP should be deferred.

Possible future use:

- synchronous SOAP outbound enrichment/callout from a Kafka route;
- SOAP response mapped back to Kafka response path.

This is operationally risky because it introduces blocking downstream calls
inside async routing. It requires a separate design before implementation.

### Future Handoff App

SOAP is usually not central to handoff-app topology, but a future handoff app
could call a SOAP endpoint as delivery or reconciliation step. Treat this as
deferred until the handoff-app archetype exists.

### Relationship To Handoff Topology

Downstream SOAP clients usually model service calls rather than file/table
handoff artifacts. The `handoff_topology` modes from the downstream handoff
topology design should not be required for ordinary `type: soap-wsdl`
downstream interfaces.

If a future handoff app uses SOAP as a delivery or reconciliation step, the
handoff topology belongs on the downstream handoff artifact/interface that owns
the execution mode. SOAP operation metadata remains on the `soap-wsdl`
interface. Do not introduce SOAP-specific topology fields.

## 15. Evidence Trail Behavior

Reuse Evidence Trail v1.1 evidence types first:

- `field`
- `mapping`
- `validation`
- `transform`

Do not add a new evidence type by default. Use richer metadata for SOAP/WSDL
sources.

Proposed metadata:

```yaml
evidence:
  - type: mapping
    entity: Account
    field: accountId
    source_artifact: contracts/account-service.wsdl
    artifact_type: wsdl
    wsdl_service: AccountService
    wsdl_port: AccountServiceSoap11Port
    wsdl_binding: AccountServiceSoap11Binding
    wsdl_operation: GetAccount
    soap_action: "urn:accounts:GetAccount"
    soap_body_path: /soap:Envelope/soap:Body/acct:GetAccountRequest/acct:accountId
    soap_header_path: null
    soap_fault: null
    xsd_path: /GetAccountRequest/accountId
    xpath: /acct:GetAccountRequest/acct:accountId
    namespace: "urn:edgeforge:examples:accounts:v1"
```

Fault evidence should preserve:

- `soap_fault`;
- fault code;
- fault string or reason;
- detail element path;
- sample fault XPath;
- operation and SOAPAction.

Introduce a new evidence type only if a future implementation proves existing
types plus SOAP metadata cannot represent provenance cleanly.

## 16. Test And Fixture Expectations

Future implementation should include tests for:

- valid WSDL 1.1 parse;
- document/literal-wrapped binding support;
- unsupported RPC/encoded diagnostic;
- unsupported WS-Security/WS-Policy diagnostic;
- service/port/binding selection;
- operation selection;
- SOAPAction preservation;
- header detection and mapping;
- declared fault detection and mapping;
- local XSD import/include resolution through XML/XSD support;
- sample request validation;
- sample response validation;
- sample fault validation;
- namespace preservation;
- generated app build for endpoint/client fixtures.

Golden generated-output fixtures should prove:

- generated endpoint method names map to selected operations;
- request/response DTOs are generated, not JPA entities;
- SOAPAction and namespaces are preserved;
- declared faults produce generated fault/error mapping;
- unsupported bindings fail before generation.

## 17. TestBench Runtime Proof

TestBench proof is needed only when generated SOAP runtime behavior exists.

Inbound endpoint proof:

- start generated app;
- send SOAP request;
- assert SOAP response;
- send failure request;
- assert declared SOAP fault.

Outbound client proof:

- start generated app;
- run mock SOAP service;
- assert generated client sends correct SOAP request;
- assert generated app handles SOAP response;
- assert declared SOAP fault mapping.

No TestBench proof is needed for parser-only design or manifest validation
alone.

## 18. Implementation Slices

No implementation happens in this PR. Proposed future slices:

| Slice | Scope | Repo(s) |
|---|---|---|
| 0 | Design doc only | EdgeForge docs |
| 1 | Additive manifest/schema contract for SOAP/WSDL references | EdgeForge |
| 2 | Deterministic WSDL parser/importer | EdgeForge |
| 3 | Studio SOAP import/review surface | EdgeForgeStudio |
| 4 | Engine translation to canonical operation metadata | EdgeForge |
| 5 | Inbound SOAP endpoint emitter | EdgeForge |
| 6 | Outbound SOAP client emitter | EdgeForge |
| 7 | SOAP fault/error mapping | EdgeForge |
| 8 | Evidence Trail metadata | EdgeForge + Studio as needed |
| 9 | Golden generated-output fixtures | EdgeForge |
| 10 | TestBench runtime proof where generated runtime behavior exists | EdgeForgeTestBench |
| 11 | KA/KS advisory suggestions after deterministic import/review works | EdgeForgeKnowledgeServer + EdgeForgeStudio |

Recommended sequencing:

1. Lock this design.
2. Decide SOAP library and minimal manifest shape.
3. Implement parser/importer before endpoint/client emitters.
4. Build Studio review surface before exposing broad generation.
5. Add inbound endpoint and outbound client emitters separately.
6. Add runtime proof only once generated SOAP runtime behavior exists.

## 19. Open Questions

1. Is `soap-wsdl` the final manifest type name, or should a shorter `soap`
   alias exist later?
2. Should `contract_artifacts[]` land with SOAP/WSDL or wait for a later
   shared-bundle implementation?
3. Which generated-app SOAP library should be preferred: Spring-WS, Apache CXF,
   or profile-specific selection?
4. How much SOAP header support belongs in v1?
5. Should document/literal-bare be a v1.1 follow-up?
6. Should runtime request/response/fault validation be on by default?
7. What is the exact generated fault mapping shape?
8. Should a future SOAP-specific timeout/retry policy live in SOAP operation
   metadata or generated app runtime config?
9. How should WSDL compatibility/versioning be tracked across project reopen
   and later enhancement flows?
10. Should SOAP inbound endpoints be allowed for passthrough-router in the
    first implementation slice, or wait until CRUD SOAP is stable?

## 20. Design Verdict

Introduce SOAP/WSDL as a deterministic edge-contract family layered on
XML/XSD. Prefer proposed manifest type `soap-wsdl`. Scope v1 to WSDL 1.1,
document/literal-wrapped, HTTP transport, one selected service/port/binding,
synchronous request/response operations, basic headers, and declared faults.

Fail fast for unsupported SOAP binding and policy constructs. Keep KA
advisory, reviewed, and off by default. Keep generated apps independent of
EdgeForge runtime. Reuse existing Evidence Trail types with richer SOAP/WSDL
metadata.

This gives EdgeForge a credible SOAP preservation path without weakening the
XML/XSD foundation or drifting into speculative SOAP policy/runtime complexity.
