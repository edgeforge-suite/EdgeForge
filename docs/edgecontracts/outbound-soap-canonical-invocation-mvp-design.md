# Outbound SOAP Canonical Invocation MVP Design

> **Status:** Design proposal.
>
> **Created:** 2026-06-02.
>
> **Scope:** Generated CRUD-app runtime invocation for downstream
> `soap-wsdl` contracts using explicit canonical-to-SOAP mappings.
>
> **Non-goals:** No Engine implementation, no Studio implementation, no
> manifest schema JSON implementation, no KS/KA/TestBench changes, no generated
> app runtime change in this PR, and no generated app dependency on EdgeForge
> runtime services.
>
> **Strategic anchor:** [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md).
>
> **Builds on:**
> - [SOAP/WSDL Contract Support Design](soap-wsdl-contract-support-design.md)
> - [SOAP Canonical Operation Mapping MVP Design](soap-canonical-operation-mapping-mvp-design.md)
> - [XML/XSD Contract Support Design](xml-xsd-contract-support-design.md)
> - [Manifest Schema](../manifest-schema.md)
> - [Evidence Trail Design](../evidence-trail-design.md)

## 1. Purpose

Engine can parse downstream SOAP/WSDL contracts, package WSDL/XSD resources,
generate standalone Spring WS client scaffolding, validate request/response
root QNames, and externalize the target URI. That is necessary but not yet a
runnable outbound business action.

The current generated app has no controller, job, or action that:

1. receives a request for a canonical row;
2. loads the canonical entity from the generated repository;
3. maps reviewed canonical fields into the SOAP request payload;
4. invokes the generated SOAP client; and
5. returns a deterministic mapped SOAP response summary.

This design closes that scaffold-to-runtime gap for the first safe outbound
SOAP canonical invocation MVP. It mirrors the successful edge-contract runtime
pattern from file output and XML output, while recognizing that outbound SOAP
can trigger external side effects and therefore needs tighter operation scope.

## 2. Current State

Implemented Engine SOAP/WSDL capabilities on `origin/main`:

- WSDL 1.1 document/literal-wrapped parsing and validation.
- Embedded/included XSD handling through the XML/XSD v1 boundary.
- Inbound SOAP endpoint generation for supported upstream contracts.
- Outbound SOAP client class generation for supported downstream contracts.
- WSDL/XSD resource packaging for generated apps.
- Operation-specific request/response root QName validation.
- Configurable SOAP endpoint URI using generated app configuration.
- Inbound SOAP canonical `read_by_id` for CRUD apps, proven end to end.

Remaining outbound gap:

- The generated outbound SOAP client is callable only from code.
- No generated REST action, batch action, or UI/action trigger invokes it.
- No generated component maps canonical entity fields into a SOAP request.
- No generated component maps SOAP response fields into a safe response body.

This design is docs-only. It does not change the current implementation.

## 3. Design Principles

- **Existing contract arrays:** SOAP contracts stay under
  `upstream_interfaces[]` / `downstream_interfaces[]`. Do not use
  `data_handoffs[]` and do not add `upstream_contracts[]` /
  `downstream_contracts[]`.
- **Explicit mappings only:** Engine must not infer behavior from SOAP
  operation names, XML element names, canonical entity names, or field-name
  similarity.
- **Side-effect aware naming:** Outbound SOAP invocation must not reuse
  inbound `read_by_id`. Even if the generated app looks up a row by ID, the
  remote SOAP operation may mutate external state.
- **Standalone generated apps:** Generated runtime code may use normal
  Spring/Java libraries but must not depend on EdgeForge, Studio, KS, KA, MCP,
  or TestBench services.
- **Fail fast over plausible no-op:** If a mapping says canonical invocation
  but the selected operation, entity, request mapping, or response behavior is
  unsupported, generation must fail clearly.
- **No response persistence by default:** MVP returns the mapped SOAP response
  to the caller. It does not update canonical data, write an audit/result table,
  implement retry, or claim idempotency.

## 4. MVP Trigger Choice

Recommended MVP trigger:

```http
POST /soap/outbound/{contractName}/{operationName}
Content-Type: application/json

{ "id": "<canonical-id>" }
```

### Why REST Action Endpoint

A REST action endpoint is the MVP trigger because it is:

- easy to prove with generated-app runtime smoke tests;
- operator-friendly without requiring a scheduler or batch topology;
- aligned with the generated app's existing controller style;
- precise for one canonical row and one selected SOAP operation;
- safer than hiding a network side effect inside a list/export action.

### Alternatives Considered

| Trigger | MVP decision | Reason |
|---|---|---|
| REST action endpoint | **Chosen** | Direct, testable, and explicit about one requested call. |
| Batch/action endpoint like file/XML output | Future | Useful for bulk send, but batch semantics, retries, partial failure, and idempotency need a separate design. |
| Service method only | Rejected for MVP | Leaves generated apps scaffold-only and gives Studio/TestBench no callable runtime surface. |
| Scheduled/job trigger | Future | Requires scheduling, replay, backoff, idempotency, and operational controls. |

## 5. Endpoint Shape Decision

Use:

```http
POST /soap/outbound/{contractName}/{operationName}
```

Do not restrict v1 to one selected operation per downstream SOAP interface.
WSDL interfaces commonly expose multiple related operations, and the existing
SOAP metadata model already carries operation-level mappings. Including
`operationName` avoids ambiguity, gives deterministic diagnostics for unknown
operations, and keeps future multi-operation interfaces additive.

An implementation may still reject unsupported operations within the same
interface. That rejection should say the contract is known but the requested
operation has no supported canonical invocation mapping.

Future `POST /soap/outbound/{contractName}` convenience aliases, if ever
allowed for single-operation interfaces, must be additive only. The explicit
`operationName` segment remains the MVP source of truth.

## 6. Proposed Mapping Shape

Use the existing `downstream_interfaces[]` entry and its existing `mapping:`
path. Do not introduce a new top-level manifest array.

Manifest example:

```yaml
downstream_interfaces:
  - name: customer-soap-client
    system: CUSTOMER_CORE
    type: soap-wsdl
    wsdl_path: contracts/customer-service.wsdl
    service: CustomerService
    port: CustomerServicePort
    binding: CustomerSoapBinding
    mapping: mappings/customer-soap-outbound-mapping.yaml
```

Referenced mapping file:

```yaml
operation_mappings:
  - operation: syncCustomer
    mode: canonical
    canonical_operation:
      kind: invoke_by_id
      entity: Customer
      lookup:
        request_field: id
        field: customerId
      request_mappings:
        - source: Customer.customerId
          target_path: /SyncCustomerRequest/customerId
        - source: Customer.status
          target_path: /SyncCustomerRequest/status
      response:
        mode: return_only
        response_mappings:
          - source_path: /SyncCustomerResponse/resultCode
            target: resultCode
          - source_path: /SyncCustomerResponse/message
            target: message
```

### Operation Kind Decision

Use `invoke_by_id`.

Why:

- `read_by_id` already means inbound SOAP lookup and is intentionally
  side-effect free.
- `call_by_id` and `send_by_id` are understandable but less explicit about
  generated behavior.
- `invoke_by_id` clearly says the generated app loads one canonical row by ID
  and invokes an external operation.

`invoke_by_id` does not claim idempotency, retry safety, or business
side-effect semantics. Those require future policy fields.

Studio-facing copy may describe the action as "call by ID" or "send by ID",
but the manifest contract kind remains `invoke_by_id` for the MVP.

### Field Meaning

| Field | Required | Meaning |
|---|---:|---|
| `operation` | yes | WSDL operation name after Engine WSDL parsing. |
| `mode` | yes for new outbound canonical mappings | `adapter_only` or `canonical`; outbound canonical requires `canonical_operation`. |
| `canonical_operation.kind` | yes | MVP supports `invoke_by_id`. |
| `canonical_operation.entity` | yes | Canonical entity to load before rendering the SOAP request. |
| `lookup.request_field` | yes | JSON request field accepted by the outbound action endpoint. MVP value is `id`. |
| `lookup.field` | yes | Canonical entity lookup field. MVP requires the persistence ID. |
| `request_mappings` | yes | Canonical entity field to SOAP request body path mappings. |
| `response.mode` | yes | MVP supports `return_only`. |
| `response.response_mappings` | yes | SOAP response body paths to generated response fields. |

`mode: canonical` without `canonical_operation` is invalid. A canonical mapping
with `handler_method` is invalid because outbound canonical invocation is
generated behavior, not adapter-only delegation.

Lookup key names are direction-specific. Inbound SOAP canonical `read_by_id`
uses `lookup.request_path` because the lookup value comes from the SOAP XML
body. Outbound SOAP canonical `invoke_by_id` uses `lookup.request_field`
because the lookup value comes from the generated REST action JSON body. The
Engine mapping parser must branch by interface direction and reject the wrong
lookup key for that direction instead of trying to reuse the inbound
`request_path` parser path.

## 7. Canonical Row Lookup Rules

MVP lookup rules:

- Request body field is exactly `id`.
- Lookup field must be the canonical entity persistence ID.
- One request invokes one SOAP operation for one canonical row.
- No all-rows mode.
- No query/filter mode.
- No batch mode.
- Missing row returns a deterministic generated app error.

Example request:

```json
{ "id": "c4e2a57b-517b-4b8f-87ab-97017c9d6f6f" }
```

Do not allow metadata-only `business_key` or `external_reference` roles as
lookup proof in the MVP. Current Engine identity-role behavior treats those as
metadata-only; it does not generate uniqueness constraints, repository finders,
or duplicate-row deterministic failure behavior. Future non-ID lookup requires
an explicit reviewed uniqueness/finder policy.

## 8. SOAP Request Mapping

Request mappings are canonical-to-SOAP:

```yaml
request_mappings:
  - source: Customer.customerId
    target_path: /SyncCustomerRequest/customerId
  - source: Customer.status
    target_path: /SyncCustomerRequest/status
```

Rules:

- Mapping `source`/`target` names follow data-flow direction. In
  `request_mappings`, data originates in canonical state and targets the SOAP
  request. In `response.response_mappings`, data originates in the SOAP
  response and targets the generated JSON response body.
- `source` must resolve to the configured canonical entity and a known field.
- `target_path` must resolve to a supported SOAP input XML field.
- XSD-required request fields must be mapped.
- Optional request fields may be omitted.
- Mapping order must not determine XML output order; generated request XML
  must follow WSDL/XSD `xs:sequence` order.
- Type conversion must be conservative and compatibility-checked at
  generation time.
- Missing required canonical values at runtime return deterministic errors
  before the outbound SOAP call.
- SOAP headers are out of scope for MVP unless a later design explicitly adds
  header mapping.
- No business transformation inference from field names.

The supported path scope should mirror current SOAP canonical v1 scalar-child
rules unless implementation explicitly broadens XML/XSD support. Nested
complex request paths remain fail-fast until designed.

## 9. SOAP Response Behavior

MVP response behavior is `return_only`.

The generated action should return a parsed, mapped response body, for example:

```json
{
  "contractName": "customer-soap-client",
  "operationName": "syncCustomer",
  "entity": "Customer",
  "id": "c4e2a57b-517b-4b8f-87ab-97017c9d6f6f",
  "response": {
    "resultCode": "ACCEPTED",
    "message": "Customer synchronized"
  }
}
```

Rules:

- SOAP response must validate against the operation output QName and XSD.
- `response_mappings[].source_path` must resolve to supported SOAP output
  fields.
- `response_mappings[].target` defines the generated JSON response field name.
- The MVP should not return raw SOAP by default.
- Raw SOAP response capture, if ever needed, should be a future explicit
  diagnostic/audit option.
- The MVP does not update canonical entities from SOAP response values.
- The MVP does not write an audit/result table.
- The MVP does not implement retry, replay, or idempotency.

Explicitly deferred:

- response-to-canonical update;
- result/audit table persistence;
- outbox/retry/replay state;
- idempotency policy;
- remote fault classification beyond deterministic generated app response.

## 10. Endpoint URL Configuration

Current generated SOAP clients use:

```properties
app.soap.clients.<contract-slug>.uri
```

MVP should keep that property for compatibility with existing client
scaffolding. For a contract named `customer-soap-client`, generated config
should use:

```yaml
app:
  soap:
    clients:
      customer-soap-client:
        uri: ${CUSTOMER_SOAP_CLIENT_URI:https://example.invalid/customer}
```

Resolution rules:

1. Use the WSDL `soap:address` as the generated default only when present.
2. Allow `application.yaml` override.
3. Allow environment override through an explicit generated placeholder such as
   `CUSTOMER_SOAP_CLIENT_URI`, avoiding ambiguous relaxed-binding behavior for
   hyphenated contract keys.
4. Never hard-code vendor- or deployment-specific URLs outside the manifest/WSDL-derived
   default.
5. If no WSDL address or config default exists, fail startup or generation with
   a clear diagnostic rather than invoking an empty endpoint.

Future implementation may add an alias such as
`app.soap.clients.<contract-slug>.endpoint-url`, but the first slice should not
break the existing `.uri` client property unless it deliberately migrates the
generated client code and tests.

## 11. Runtime Diagnostics

Generated errors must be useful and safe:

- no stack traces in user-facing responses;
- no local filesystem paths;
- no raw WSDL/XSD file paths;
- no raw SOAP payload logging by default;
- no EdgeForge runtime dependency references.

Expected diagnostics:

| Condition | Expected behavior |
|---|---|
| Unknown `contractName` | 404 or 400-style generated app error naming the unknown contract. |
| Unknown `operationName` | 404 or 400-style generated app error naming the operation and contract. |
| Operation has no canonical mapping | 400-style error explaining the operation is adapter-only or unsupported. |
| Unsupported operation mode/kind | Generation-time fail-fast when possible; runtime error only if externally requested. |
| Missing request `id` | 400-style error before repository lookup. |
| Missing canonical row | 404-style error naming entity and ID, without stack trace. |
| Missing required mapped canonical field | 400 or 409-style deterministic error before SOAP invocation. |
| SOAP server unavailable | 502/503-style generated app error with safe message. |
| Timeout | 504-style generated app error if timeout configuration exists; otherwise deterministic SOAP client error. |
| SOAP Fault from remote service | Deterministic generated app error preserving safe fault code/message. |
| Malformed SOAP response | 502-style generated app error. |
| Response validation failure | 502-style generated app error naming contract and operation. |

## 12. Generated App Architecture

Expected generated components:

- `OutboundSoapActionController` or equivalent.
- Request DTO for `{ "id": "..." }`.
- Response DTO containing contract, operation, entity, ID, and mapped response
  fields.
- Canonical row lookup service or generated controller helper.
- Request mapping renderer that builds operation-specific SOAP XML in XSD
  sequence order.
- Existing generated SOAP client bean invocation.
- Response mapping reader that extracts operation-specific SOAP response paths.
- Safe exception classes and global handler integration.
- Application config binding for `app.soap.clients.<contract-slug>.uri`.

The action controller should not expose JPA entities as public request/response
bodies. Entities remain internal to repository/service layers.

## 13. Transaction And Side-Effect Boundary

Outbound SOAP invocation is a network side effect. The MVP should:

- read the canonical row;
- render the SOAP request;
- invoke the external SOAP service;
- return the mapped response;
- avoid wrapping the external call in a broad database transaction;
- avoid mutating canonical state.

The MVP should not pretend to provide delivery guarantees. Future persistence,
audit, outbox, retry, replay, compensation, and idempotency behavior should be
designed separately.

## 14. Studio Implications

Future Studio work should extend the existing edge-contract mapping flow for
downstream SOAP interfaces. Studio should let users review:

- downstream SOAP contract and selected operation;
- operation kind `invoke_by_id`;
- canonical entity;
- persistence ID lookup field;
- canonical fields mapped to SOAP request paths;
- SOAP response paths returned in the generated response body;
- endpoint URI override hint;
- validation/type compatibility findings.

KA OFF remains clean. KS/KA may later suggest canonical-to-SOAP mappings, but
suggestions must remain advisory and require explicit review before export.

## 15. Evidence Trail

Reuse existing evidence types where possible:

- `mapping` for canonical-to-SOAP request and SOAP-to-response mappings;
- `field` for canonical field selection;
- `validation` for WSDL/XSD/root/action checks;
- `transform` for explicit type conversion or formatting.

Add SOAP/canonical metadata to evidence entries rather than creating a new
evidence type unless future implementation proves a gap:

- `downstream_interface`;
- `wsdl_operation`;
- `soap_action`;
- `soap_request_path`;
- `soap_response_path`;
- `canonical_entity`;
- `canonical_field`;
- `invocation_mode`.

Example evidence metadata:

```json
{
  "type": "mapping",
  "manifest_path": "downstream_interfaces.customer-soap-client.operations.syncCustomer.mappings.status",
  "source": "generated-artifact",
  "metadata": {
    "downstream_interface": "customer-soap-client",
    "wsdl_operation": "syncCustomer",
    "soap_action": "urn:syncCustomer",
    "soap_request_path": "/SyncCustomerRequest/status",
    "canonical_entity": "Customer",
    "canonical_field": "status",
    "invocation_mode": "invoke_by_id"
  }
}
```

## 16. Test And Golden Fixture Expectations

Future Engine implementation should add tests proving:

- mapping parser accepts valid outbound canonical invocation mapping;
- mapping parser rejects unknown operations and duplicate mappings;
- mapping parser rejects unsupported `canonical_operation.kind`;
- mapping parser rejects unsupported `response.mode` values;
- mapping parser rejects non-persistence-ID lookup;
- mapping parser rejects missing required SOAP request mappings;
- mapping parser rejects response mappings to unknown SOAP paths;
- mapping parser rejects type-incompatible mappings;
- generated app exposes `POST /soap/outbound/{contractName}/{operationName}`;
- generated app builds;
- generated app resolves canonical row by ID;
- generated app invokes a local mock SOAP service;
- generated app returns mapped SOAP response fields;
- missing canonical row returns clear error;
- remote SOAP server unavailable returns clear error;
- remote SOAP Fault is surfaced deterministically;
- existing adapter-only outbound client scaffolding remains compatible;
- inbound SOAP canonical `read_by_id`, XML/XSD runtime, and file-contract
  runtime tests remain green.

Suggested fixture:

```text
tests/fixtures/edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/
```

## 17. TestBench / Runtime Proof Expectations

Runtime proof should come after generated runtime behavior exists:

1. Generate a supported CRUD app from the outbound SOAP canonical fixture.
2. Build the generated app.
3. Start a local mock SOAP service.
4. Start the generated app on a non-demo port.
5. Seed a canonical `Customer` or `Account` through REST.
6. Call `POST /soap/outbound/{contractName}/{operationName}` with the seeded ID.
7. Verify the mock SOAP service receives the expected SOAP request body.
8. Verify the generated app returns mapped response fields.
9. Verify missing row, server unavailable, timeout, and SOAP Fault diagnostics.

Do not treat TestBench proof as complete until both the generated app and a
local mock SOAP service participate in the runtime path.

## 18. Recommended Implementation Slices

1. **Slice 0: design doc only.** Land this document and status references.
2. **Slice 1: Engine mapping parser/schema extension.** Accept downstream
   canonical SOAP mappings with `kind: invoke_by_id`; distinguish upstream
   `lookup.request_path` from downstream `lookup.request_field` by interface
   direction; preserve existing adapter-only outbound client scaffolding;
   reject unsupported modes.
3. **Slice 2: Engine outbound SOAP action/controller generation.** Generate the
   callable REST action endpoint and DTOs.
4. **Slice 3: request mapping renderer and canonical row lookup.** Load row by
   persistence ID, render SOAP request in WSDL/XSD order, and fail before the
   remote call when required values are missing.
5. **Slice 4: response return DTO/body and fault diagnostics.** Map SOAP
   response paths into safe JSON and surface remote faults deterministically.
6. **Slice 5: generated-output and runtime proof fixture.** Prove generated app
   builds and invokes a local mock SOAP service.
7. **Slice 6: Studio author/export UI.** Author downstream SOAP canonical
   invocation mappings from the existing edge-contract mapping flow.
8. **Slice 7: Studio to Engine runtime smoke.** Export from Studio, generate in
   Engine, run the generated app, and prove the outbound action.
9. **Slice 8: future response persistence/audit/retry design.** Decide whether
   to add result tables, outbox/retry, idempotency, scheduling, and batch send.

## 19. Open Questions

- Should v1 allow multiple canonical outbound operations per downstream SOAP
  interface, or should implementation begin with one while preserving the URL
  shape?
- Should the action response include only mapped fields, or optionally include
  safe SOAP metadata such as remote fault code and SOAPAction?
- What timeout default should generated apps use before a dedicated retry
  design exists?
- Are SOAP headers completely deferred, or is there a narrow reviewed static
  header mapping needed for the first real customer proof?
- When should response persistence/audit/result table behavior be designed?
- Should outbound SOAP eventually share a generic operator-action model with
  XML/file output jobs, or remain a per-ID REST action because of side effects?

## 20. Out Of Scope

- Engine implementation.
- Studio implementation.
- Manifest schema JSON changes.
- KS/KA/TestBench changes.
- Outbound SOAP bulk/batch mode.
- SOAP headers.
- WS-Security, WS-Policy, MTOM, WS-Addressing, retries, replay, or async
  callback behavior.
- Response-to-canonical update.
- Audit/result table persistence.
- Idempotency or exactly-once claims.
- Generated app dependency on EdgeForge runtime services.
