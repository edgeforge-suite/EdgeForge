# SOAP Canonical Operation Mapping MVP Design

> **Status:** Design proposal.
>
> **Created:** 2026-05-31.
>
> **Scope:** Inbound SOAP/WSDL operation mappings from reviewed SOAP request
> payloads to deterministic canonical generated behavior in CRUD generated apps.
>
> **Non-goals:** No Engine implementation, no Studio implementation, no
> manifest schema implementation, no KS/KA/TestBench change, no outbound SOAP
> client invocation behavior in this inbound design, no generated app runtime
> dependency on EdgeForge.
>
> **Strategic anchor:** [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md).
>
> **Builds on:**
> - [SOAP/WSDL Contract Support Design](soap-wsdl-contract-support-design.md)
> - [XML/XSD Contract Support Design](xml-xsd-contract-support-design.md)
> - [Manifest Schema](../manifest-schema.md)
> - [Evidence Trail Design](../evidence-trail-design.md)
>
> **See also:** [Outbound SOAP Canonical Invocation MVP Design](outbound-soap-canonical-invocation-mvp-design.md)

## 1. Purpose

Engine can now parse supported WSDL contracts, generate inbound SOAP endpoints,
generate outbound SOAP clients, validate SOAP XML against WSDL/XSD resources,
and return deterministic SOAP diagnostics for adapter-only or malformed
requests. The remaining gap is business/canonical behavior: generated inbound
SOAP endpoints still delegate to a user-provided handler bean unless a future
mapping slice teaches Engine how to generate a supported canonical handler.

This design defines the first safe contract for that bridge. It keeps current
adapter-only behavior valid, adds an explicit `mode` concept, and scopes the
first canonical operation kind to `read_by_id`.

The principle is simple: if a mapping says `mode: canonical`, Engine must either
generate the declared canonical behavior or fail fast. It must never silently
fall back to adapter-only behavior or generate a plausible no-op.

## 2. Current State

Implemented Engine SOAP/WSDL foundation:

- WSDL 1.1 document/literal-wrapped parsing and validation.
- Embedded/included XSD parsing through the XML/XSD boundary.
- Inbound Spring WS endpoint generation for supported upstream SOAP contracts.
- Outbound Spring WS client generation for supported downstream SOAP contracts.
- Packaged WSDL/XSD resources and request/response root QName validation.
- Adapter-only handler interfaces for inbound operations.
- Explicit adapter-only diagnostics when no handler bean exists.
- Deterministic SOAP Fault fallback for unknown operations, malformed SOAP/XML,
  schema validation failures, and adapter-only missing handlers.

Current operation mapping files only select the SOAP operation and handler
method:

```yaml
operation_mappings:
  - operation: getCustomer
    handler_method: handleGetCustomer
```

That form is adapter-only. It is useful for hand-written generated-app extension
beans, demos, and phased migrations, but it is not enough for deterministic
generated canonical behavior.

## 3. Design Principles

- **Explicit mode:** Every new mapping should say whether it is adapter-only or
  canonical.
- **Backward compatible:** Existing mappings without `mode` should default to
  `adapter_only` for compatibility.
- **No silent no-op:** `mode: canonical` must generate supported behavior or
  fail clearly.
- **No inference from operation names:** `getCustomer` does not imply a
  `Customer` lookup unless the mapping says so.
- **Reviewed mappings only:** Request lookup and response mappings come from
  reviewed YAML, not generated name matching.
- **Contract-preserving:** SOAP action, namespace, body root, XSD validation,
  and declared fault semantics remain owned by WSDL/XSD metadata.
- **Entity-safe:** Public SOAP payloads map through XML/SOAP DTOs and generated
  handler behavior. JPA entities must not become public SOAP payload types.
- **Runtime independence:** Generated apps use normal Spring/Java libraries, not
  EdgeForge runtime services.

## 4. Proposed Mapping Model

Extend the existing SOAP operation mapping YAML additively:

`operation_mappings[]` lives inside the YAML file referenced by the SOAP
interface's existing `mapping:` field. This design does not add a top-level
manifest array or a parallel contract array.

```yaml
upstream_interfaces:
  - name: customer-soap-service
    type: soap-wsdl
    wsdl_path: contracts/customer-service.wsdl
    mapping: mappings/customer-soap-operation-mapping.yaml
```

The referenced mapping file contains entries like:

```yaml
operation_mappings:
  - operation: getCustomer
    mode: adapter_only
    handler_method: handleGetCustomer
```

For canonical behavior:

```yaml
operation_mappings:
  - operation: getCustomer
    mode: canonical
    canonical_operation:
      kind: read_by_id
      entity: Customer
      lookup:
        request_path: /GetCustomerRequest/customerId
        field: customerId
      response_mappings:
        - source: Customer.customerId
          target_path: /GetCustomerResponse/customerId
        - source: Customer.name
          target_path: /GetCustomerResponse/name
      not_found_fault:
        fault: CustomerNotFoundFault
        message: Customer not found
```

### Field Meaning

| Field | Required | Meaning |
|---|---:|---|
| `operation` | yes | WSDL operation name after Engine WSDL parsing. |
| `mode` | recommended for new mappings | `adapter_only` or `canonical`. Missing means `adapter_only` for backward compatibility. |
| `handler_method` | adapter-only | Handler method name for the generated adapter-only interface. If omitted in adapter-only mode, Engine may preserve the current default. |
| `canonical_operation.kind` | canonical | Supported generated behavior kind. MVP supports only `read_by_id`. |
| `canonical_operation.entity` | canonical | Canonical entity to query. |
| `lookup.request_path` | canonical | SOAP body path to the lookup value in the request XML model. |
| `lookup.field` | canonical | Canonical entity field used for lookup. |
| `response_mappings` | canonical | Reviewed canonical-to-SOAP response field mappings. |
| `not_found_fault` | canonical | Declared or generated fault behavior for missing rows. |

`mode: canonical` without `canonical_operation` is invalid. A mapping with
`mode: adapter_only` and `canonical_operation` is also invalid because it is
ambiguous.

## 5. MVP Operation Kind: `read_by_id`

The first canonical operation kind should be `read_by_id`.

Example behavior:

1. SOAP request arrives for WSDL operation `getCustomer`.
2. Spring WS endpoint validates SOAP envelope, body root QName, SOAP action, and
   XSD payload.
3. Generated canonical handler extracts `/GetCustomerRequest/customerId`.
4. Handler queries canonical `Customer` by its persistence ID, `customerId`.
5. If found, handler maps reviewed `Customer.*` fields into
   `GetCustomerResponse`.
6. If not found, handler returns a deterministic SOAP Fault.

Why `read_by_id` first:

- It is side-effect free.
- It has a single entity boundary.
- It avoids create/update/idempotency semantics.
- It is easy to prove with generated-output and runtime fixtures.
- It exercises the full request-lookup, repository, response-mapping, and fault
  path without inventing business behavior.

### Lookup Field Scope

MVP should require lookup by the canonical entity persistence ID. Current Engine
identity-role behavior treats `business_key` as metadata-only; it does not yet
generate uniqueness constraints, repository finders, or duplicate-row handling.
Therefore a metadata-only `business_key` is not enough proof for generated SOAP
lookup behavior in this MVP.

Future non-ID lookup support can be designed after Engine has an explicit,
reviewed uniqueness/finder policy for the field. That future policy must define
how the generated app proves uniqueness, what finder is emitted, and how it
fails deterministically if duplicate rows exist. Until then, if `lookup.field`
is not the persistence ID, Engine must fail with a clear message rather than
generating a non-deterministic query.

## 6. Validation Rules

Translation or generation must fail clearly for:

- unknown SOAP operation;
- duplicate operation mappings;
- invalid `mode`;
- `mode: canonical` without `canonical_operation`;
- unsupported `canonical_operation.kind`;
- unknown canonical entity;
- unknown canonical lookup field;
- missing `lookup.request_path` for `read_by_id`;
- request path not present in the SOAP request XML model;
- lookup field type incompatible with the request path XML type;
- `lookup.field` is not the canonical entity persistence ID;
- missing `response_mappings`;
- any XSD-required response element or attribute without a `response_mapping`;
- response mapping source entity/field not found;
- response mapping target path not present in the SOAP response XML model;
- response mapping target path requires nested complex XML beyond the current
  XML/XSD v1 scalar-child scope;
- response mapping type incompatibility;
- `mode: adapter_only` combined with canonical operation configuration;
- `mode: canonical` where the selected archetype cannot generate canonical
  handler behavior.

Existing mappings without `mode` should default to `adapter_only`. This is the
least surprising path for current fixtures and generated apps. Engine should
emit a warning or quality-note in a later implementation slice encouraging new
mapping files to declare `mode` explicitly.

## 7. Generated App Behavior

For `mode: adapter_only`, generated behavior remains current:

- generate SOAP endpoint method;
- validate request root/action/XSD;
- call a handler bean if present;
- return an explicit SOAP Fault when the handler bean is absent.

For `mode: canonical` and `kind: read_by_id`, generated behavior should:

- generate a deterministic canonical handler implementation;
- preserve generated SOAP endpoint annotations and validation;
- deserialize or inspect the validated SOAP request model;
- convert the lookup value to the canonical field type;
- query the generated repository or service using the entity persistence ID;
- map canonical values into the generated SOAP response model;
- require every XSD-required response element or attribute to be populated by an
  explicit mapping at generation time; optional response fields may be omitted;
- serialize and validate the SOAP response payload;
- map not-found to the configured SOAP fault behavior;
- keep technical failures as deterministic technical SOAP Faults.

Generated code must not expose JPA entities as public SOAP payload types. Entity
objects may be internal to service/repository layers, consistent with existing
generated CRUD safety rules.

## 8. Fault Mapping

MVP not-found behavior should prefer a declared WSDL fault when the mapping
names one:

```yaml
not_found_fault:
  fault: CustomerNotFoundFault
  message: Customer not found
```

`not_found_fault` is the canonical-mode, operation-scoped inline instruction for
this MVP. It complements interface-level `fault_samples` and any future
`fault_mapping` file references from the broader SOAP/WSDL design; it does not
replace sample/evidence artifacts. The `fault` value must resolve to a
WSDL-declared fault for the selected operation.

Validation rules:

- If `fault` is provided, it must match a WSDL fault known for the operation.
- If a declared fault has a generated XML model, Engine should populate only
  reviewed fields.
- If no declared fault is configured, Engine may use a generated client fault
  with a deterministic not-found message, but the design preference is to
  require declared faults for contract-preserving SOAP APIs.

Known business faults are contract objects. Unknown runtime exceptions remain
technical errors and should use the existing safe SOAP diagnostic path.

## 9. Evidence Trail

Canonical SOAP operation mapping should reuse existing evidence types wherever
possible:

- `mapping` for request lookup and response field mappings;
- `field` for canonical field selection;
- `validation` for WSDL/XSD/root/action checks;
- `transform` for type conversion or formatting between XML and canonical
  fields.

Canonical SOAP mappings are generated-artifact evidence, not advisory evidence,
unless a KS/KA suggestion was explicitly reviewed and applied. Evidence entries
should keep the existing `manifest_path` addressing as the anchor and store
SOAP-specific values as descriptive metadata on that entry.

Example generated-artifact evidence entry:

```json
{
  "type": "mapping",
  "manifest_path": "upstream_interfaces.customer-soap-service.operations.getCustomer.mappings.customerId",
  "source": "generated-artifact",
  "metadata": {
    "wsdl_operation": "getCustomer",
    "soap_action": "urn:getCustomer",
    "soap_body_path": "/GetCustomerRequest/customerId",
    "soap_fault": "CustomerNotFoundFault",
    "canonical_entity": "Customer",
    "canonical_field": "customerId"
  }
}
```

Evidence should point back to the mapping file, WSDL operation, request/response
body paths, and canonical field metadata. It should not imply KS/KA authored the
mapping unless a reviewed suggestion was actually applied.

## 10. Studio Implications

Studio should eventually expose SOAP operation mode as a reviewed choice:

- `adapter_only`: user supplies or later wires a handler bean outside Engine.
- `canonical`: Engine generates a supported canonical handler.

This should extend the existing edge-contract mapping authoring surface for
inbound SOAP, where Studio already exports `operation_mappings[]` through the
mapping generation flow. It should stay in the upstream contract review and
mapping flow rather than creating a separate SOAP-only screen.

For canonical `read_by_id`, Studio should let users review:

- SOAP operation;
- SOAP action and body root;
- request lookup path;
- canonical entity;
- lookup field;
- response mappings;
- not-found fault selection;
- validation/type compatibility findings.

KA OFF remains clean. KS/KA may later suggest mappings, but suggestions must stay
advisory and require explicit user review before export.

## 11. Out Of Scope

- SOAP canonical create/update/delete handlers.
- Multi-entity canonical handlers.
- Predicate/search/list SOAP handlers.
- Outbound SOAP canonical client invocation; see
  [Outbound SOAP Canonical Invocation MVP Design](outbound-soap-canonical-invocation-mvp-design.md).
- WS-Security, WS-Policy, MTOM, WS-Addressing, callbacks, or async SOAP.
- Automatic business logic inference from SOAP operation names.
- Studio implementation.
- KS suggestions.
- TestBench runtime proof.
- Manifest schema/code implementation in this design PR.

## 12. Recommended Implementation Slices

1. **Slice 0: design doc only.** Land this document and status references.
2. **Slice 1: Engine contract parser/schema extension.** Accept `mode` and
   `canonical_operation`; preserve missing `mode` as `adapter_only`; reject
   unknown keys, invalid modes, and `mode: canonical` unless the new canonical
   parser shape is fully validated. Include negative fixtures before handler
   generation begins.
3. **Slice 2: Engine `read_by_id` canonical generation.** Generate canonical
   handler implementation for supported CRUD SOAP upstream contracts.
4. **Slice 3: generated-output and runtime proof.** Add fixture with
   `getCustomer`, repository lookup, response mapping, and not-found fault. This
   is a hard gate before Studio authoring/export work.
5. **Slice 4: Studio author/export UI.** Let users select mode and author
   request/response/fault mappings.
6. **Slice 5: Studio to Engine runtime smoke.** Prove exported canonical mapping
   generates and runs without hand-patching.
7. **Slice 6: optional KS advisory suggestions.** Suggest lookup and response
   mappings, with reviewed application only.
8. **Slice 7: future operation designs.** Design create/update/search and
   outbound SOAP canonical invocation separately.

Implementation note: until Slice 1 lands, no fixture or exported package should
author `mode: canonical`. The current Engine parser only understands
`operation` and `handler_method`, so Slice 1 must close that gap by making
unrecognized keys and unsupported canonical mode fail fast instead of being
silently treated as adapter-only.

## 13. Open Questions

- How long should Engine warn about un-moded mappings before requiring explicit
  `mode` in newly-authored mapping files?
- What explicit uniqueness/finder policy would be required before non-ID
  lookups, including `business_key`, can become generated behavior?
- Should not-found require a declared SOAP fault, or allow a generated default
  SOAP client fault?
- Should optional response fields have a way to declare intentional omission for
  audit clarity?
- Should canonical SOAP handlers call generated service methods, repositories,
  or a new generated operation service facade?
- How should future outbound SOAP canonical slices coordinate with the separate
  `invoke_by_id` design so shared mapping parser behavior stays consistent?
