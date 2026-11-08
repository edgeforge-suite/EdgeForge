# SOAP Outbound Canonical `invoke_by_id` — Proof Plan

Date: 2026-06-02

Branch: `claude/proof/soap-outbound-canonical-invoke-by-id`

Fixture:

`tests/fixtures/edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/`

Design:

`docs/edgecontracts/outbound-soap-canonical-invocation-mvp-design.md` (PR #192)

---

## Scope

This document records:

1. What was proven in this branch (pre-implementation, June 2026).
2. The residual unproven surface keyed to design slices.
3. Explicit coverage gaps and handoffs to the build thread.

It does not contain a completed runtime proof.  The runtime proof (Section F)
cannot be executed until Slices 2-5 of the outbound canonical implementation
exist in the Engine.

---

## What Was Proven

### A — WSDL fixture integrity (6 tests, all pass)

The `customer-sync-service.wsdl` fixture parses correctly via the existing
`load_soap_contract_spec` path:

- `syncCustomer` operation is present with `soapAction: urn:syncCustomer`.
- `SyncCustomerRequest` has `customerId` (required, xs:string) and `status`
  (required, xs:string) in XSD sequence order.
- `SyncCustomerResponse` has `resultCode` (required) and `message` (optional,
  `minOccurs="0"`).
- No WSDL faults declared in the MVP operation (intentional — fault shape is
  deferred to Slice 4 design).
- `wsdl_paths` is relative to the package root, no cross-boundary path leakage.

### B — Translation-layer canonical mapping support (10 tests, all pass)

The Engine translation layer now accepts the Slice 1 downstream canonical
`invoke_by_id` shape and still enforces structural guards:

| Guard | Test | Error message |
|---|---|---|
| `mode: canonical` + `kind: invoke_by_id` on downstream SOAP → accepted into metadata | B-1 | (metadata shape assertion) |
| Canonical mapping YAML has the design-spec `invoke_by_id` shape | B-2 | (YAML cross-check, no translation layer) |
| Mapping `request_mappings` paths match WSDL input fields | B-3 | (WSDL cross-check, no translation layer) |
| Mapping `response_mappings` paths match WSDL output fields | B-4 | (WSDL cross-check, no translation layer) |
| `mode: canonical` without `canonical_operation` block → rejected | B-5 | "requires canonical_operation" |
| `mode: adapter_only` + `canonical_operation` block → rejected | B-6 | "cannot declare canonical_operation when mode is adapter_only" |
| Duplicate operation in mapping → rejected | B-7 | "declares operation ... more than once" |
| Unknown operation in mapping → rejected | B-8 | "mapping references unknown operation" |
| Missing operation in mapping → rejected | B-9 | "must declare a non-empty operation_mappings list" |
| Unrecognised mapping mode → rejected | B-10 | "unsupported operation mapping mode" |

### C — Adapter-only regression (5 tests, all pass)

The existing adapter-only outbound SOAP client scaffold generates correctly
against the new fixture's WSDL:

- Translation succeeds and sets `direction: downstream`, `mode: adapter_only`.
- `CustomerSyncClientSoapClient.java` is generated with `@Component`,
  `WebServiceTemplate`, `syncCustomer` method, correct namespace, SOAPAction.
- WSDL resource is packaged under
  `src/main/resources/soap-contracts/customer-sync-client/`.
- `application.yaml` contains `app.soap.clients.customer-sync-client.uri`.
- No `OutboundSoapActionController` is generated for adapter-only manifests.

### D — Canonical `invoke_by_id` negative translation tests (21 tests, all pass)

- D-1: unsupported downstream canonical kinds are rejected at translation.
- D-2: `handler_method` + `mode: canonical` is always rejected (regardless of
  direction).
- D-3 through D-21: unknown entity/lookup/source/path errors, non-persistence-ID
  lookup, missing `lookup.request_field`, missing required request fields,
  missing required response fields, missing/unsupported response blocks,
  duplicate request/response mappings, incompatible canonical-to-SOAP request
  types, malformed response target names, and omitted-mode canonical blocks all
  fail deterministically.

---

## Residual Unproven Surface

### Slice 1 — Mapping parser/schema extension

Implemented in Engine metadata translation:

- `_load_soap_operation_mappings` (translation.py, ~line 1151) accepts
  `mode: canonical` for `direction="downstream"`.
- `_parse_soap_canonical_operation_mapping` (or a new downstream-specific
  variant) accepts `kind: invoke_by_id` with the outbound mapping fields
  (`request_field`, `request_mappings`, `response.mode`,
  `response.response_mappings`).
- **E-1** is now active and B/D coverage verifies valid metadata plus Slice 1
  fail-fast behavior.

### Slice 2 — Controller generation and invoke_by_id vertical

Implemented as a generated REST controller with the full MVP invocation path:

- `OutboundSoapActionController` is generated for downstream canonical
  `invoke_by_id` manifests only.
- **E-2** is active and verifies `@RestController`, route shape, request/response
  records, operation registry, unknown contract/operation diagnostics,
  missing-ID diagnostics, canonical repository lookup, SOAP client invocation,
  and absence of any runtime 501 scaffold branch.
- **E-3** is active and verifies the request builder renders SOAP XML in XSD
  `xs:sequence` order (`customerId` before `status`) and uses DOM/`Source`
  payloads instead of raw SOAP strings.
- **E-4** is active and verifies the success DTO nests mapped return-only fields
  under `response`, while missing rows and remote SOAP Faults have deterministic
  safe failure envelopes.
- The generated controller uses the existing outbound SOAP client bean and
  `app.soap.clients.<contract>.uri` configuration; it does not persist SOAP
  responses or mutate canonical rows.

### Slice 3 — Runtime mock proof

Un-skip **F-1, F-2, F-3** when the generated app smoke uses a local mock SOAP
service to prove happy path, missing-row, server-unavailable, and SOAP Fault
diagnostics end to end.


---

## Coverage Gaps (hand to build thread)

1. **No test for WSDL-address-as-default-URI** (design doc §10 rule 1).
   Current generator emits `http://localhost:8080/ws` for all SOAP clients
   regardless of `soap:address` in the WSDL.  The `customer-sync-service.wsdl`
   fixture has `soap:address location="https://example.invalid/customer-sync"`.
   Test C-4 currently accepts either value.  Once the design's rule 1 is
   implemented, C-4 should assert `example.invalid/customer-sync` specifically.
   → **Build thread action:** implement WSDL-address-as-default in the SOAP
   client generator, then tighten C-4.

2. **Closed by Slice 1:** response object shape at translation is now asserted
   by the active metadata tests.

3. **Closed by Slice 1:** unsupported outbound canonical kinds are now rejected
   at translation time.

4. **Closed by Slice 1:** `response.mode` values other than `return_only` are
   rejected by translation.

5. **Closed by Slice 1 follow-up:** request type-compatibility failures,
   duplicate request/response mappings, and missing required response mappings
   now have active negative coverage.

6. **No regression test for a legacy (no `mapping:` key) downstream SOAP
   manifest** alongside an invoke_by_id manifest in the same project.  The
   `basic-outbound-customer-client` fixture has no `mapping:` field; a combined
   fixture would verify mixed downstream contracts coexist.

7. **TestBench not warranted yet.**  One-off smoke is sufficient for the MVP
   runtime proof (F-1 stub).  TestBench productisation should wait until the
   outbound invoke_by_id path is stable and the remote mock-service harness is
   worth reusing.

---

## Commands (to be executed when Slices 1-5 land)

Generate:

```bash
python3 -m appbuilder.cli generate \
  --manifest tests/fixtures/edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/app-definition.yaml \
  --output /tmp/edgeforge-soap-outbound-invoke-by-id \
  --validate-schema
```

Build:

```bash
cd /tmp/edgeforge-soap-outbound-invoke-by-id
mvn -q -DskipTests package
```

Start local mock SOAP service (WireMock example):

```bash
# SyncCustomer stub — returns ACCEPTED for any ID
cat > /tmp/syncCustomer-stub.json << 'EOF'
{
  "request": {
    "method": "POST",
    "url": "/customer-sync",
    "bodyPatterns": [{"contains": "SyncCustomerRequest"}]
  },
  "response": {
    "status": 200,
    "headers": {"Content-Type": "text/xml; charset=UTF-8"},
    "body": "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" xmlns:tns=\"urn:edgeforge:examples:customer-sync:v1\"><soapenv:Body><tns:SyncCustomerResponse><tns:resultCode>ACCEPTED</tns:resultCode><tns:message>Customer synchronized</tns:message></tns:SyncCustomerResponse></soapenv:Body></soapenv:Envelope>"
  }
}
EOF
java -jar wiremock-standalone.jar --port 18200 --root-dir /tmp/wiremock &
curl -X POST http://localhost:18200/__admin/mappings -d @/tmp/syncCustomer-stub.json
```

Run generated app (pointing at the mock):

```bash
CUSTOMER_SYNC_CLIENT_URI=http://localhost:18200/customer-sync \
SERVER_PORT=18201 \
java -jar /tmp/edgeforge-soap-outbound-invoke-by-id/target/*.jar
```

Seed a canonical Customer:

```bash
curl -s -X POST http://localhost:18201/customers \
  -H 'Content-Type: application/json' \
  -d '{"customerName":"Ada Lovelace","status":"ACTIVE"}'
# Note the returned customerId UUID.
```

Call the outbound canonical action endpoint:

```bash
curl -s -X POST http://localhost:18201/soap/outbound/customer-sync-client/syncCustomer \
  -H 'Content-Type: application/json' \
  -d '{"id":"<UUID from seed step>"}'
```

Expected response:

```json
{
  "contractName": "customer-sync-client",
  "operationName": "syncCustomer",
  "entity": "Customer",
  "id": "<UUID>",
  "response": {
    "resultCode": "ACCEPTED",
    "message": "Customer synchronized"
  }
}
```

Verify mock SOAP service received the request:

```bash
curl -s http://localhost:18200/__admin/requests | \
  python3 -c "import sys,json; reqs=json.load(sys.stdin)['requests']; print(reqs[-1]['body'])"
```

Expected SOAP body to contain `<customerId>...</customerId>` and
`<status>ACTIVE</status>` in XSD sequence order.

Missing-row diagnostic:

```bash
curl -s -X POST http://localhost:18201/soap/outbound/customer-sync-client/syncCustomer \
  -H 'Content-Type: application/json' \
  -d '{"id":"00000000-0000-0000-0000-000000000000"}'
# Expected: HTTP 404-style, body names entity and ID, no stack trace.
```

Server unavailable diagnostic (stop the mock and retry):

```bash
# Kill the WireMock process first.
curl -s -X POST http://localhost:18201/soap/outbound/customer-sync-client/syncCustomer \
  -H 'Content-Type: application/json' \
  -d '{"id":"<UUID>"}'
# Expected: HTTP 502 or 503, safe message, no paths, no SOAP payload.
```
