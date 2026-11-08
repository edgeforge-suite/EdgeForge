# SOAP Canonical `read_by_id` Runtime Proof

Date: 2026-05-31

Branch: `codex/proof/soap-canonical-read-by-id-runtime`

Fixture:

`tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml`

## Scope

This proof validates the Engine-generated runtime path for inbound SOAP/WSDL
canonical operation mapping:

- `mode: canonical`
- `canonical_operation.kind: read_by_id`
- lookup by canonical persistence ID `Customer.customerId`
- mapped SOAP response fields `customerId` and `status`
- deterministic not-found SOAP Fault behavior

It does not cover outbound SOAP canonical invocation, non-ID finder policies, or
create/update/search SOAP operations.

## Commands

Generate:

```bash
.venv/bin/python -m appbuilder.cli generate \
  --manifest tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml \
  --output /tmp/edgeforge-soap-canonical-read-by-id \
  --validate-schema
```

Build:

```bash
cd /tmp/edgeforge-soap-canonical-read-by-id
mvn -q -DskipTests package
```

Run:

```bash
SERVER_PORT=18120 java -jar target/*.jar
```

Note: starting the server inside the local sandbox failed with macOS socket bind
`Operation not permitted`; rerunning with local bind permission succeeded.

Seed canonical Customer:

```bash
curl -s -X POST http://127.0.0.1:18120/customers \
  -H 'Content-Type: application/json' \
  -d '{"customerName":"Ada Lovelace","status":"ACTIVE"}'
```

Observed:

```json
{"customerId":"22ded0bb-0139-4f82-a3e4-b9459d8e850f","customerName":"Ada Lovelace","status":"ACTIVE"}
```

SOAP happy path:

```bash
curl -s -X POST http://127.0.0.1:18120/ws \
  -H 'Content-Type: text/xml; charset=UTF-8' \
  -H 'SOAPAction: "urn:getCustomer"' \
  -d '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="urn:edgeforge:examples:customer-soap:v1"><soapenv:Header/><soapenv:Body><tns:GetCustomerRequest><tns:customerId>22ded0bb-0139-4f82-a3e4-b9459d8e850f</tns:customerId></tns:GetCustomerRequest></soapenv:Body></soapenv:Envelope>'
```

Observed:

```xml
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"><SOAP-ENV:Header/><SOAP-ENV:Body><GetCustomerResponse xmlns="urn:edgeforge:examples:customer-soap:v1"><customerId>22ded0bb-0139-4f82-a3e4-b9459d8e850f</customerId><status>ACTIVE</status></GetCustomerResponse></SOAP-ENV:Body></SOAP-ENV:Envelope>
```

SOAP missing-ID path:

```bash
curl -s -w '\n%{http_code}\n' -X POST http://127.0.0.1:18120/ws \
  -H 'Content-Type: text/xml; charset=UTF-8' \
  -H 'SOAPAction: "urn:getCustomer"' \
  -d '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="urn:edgeforge:examples:customer-soap:v1"><soapenv:Header/><soapenv:Body><tns:GetCustomerRequest><tns:customerId>00000000-0000-0000-0000-000000000000</tns:customerId></tns:GetCustomerRequest></soapenv:Body></soapenv:Envelope>'
```

Observed:

```xml
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"><SOAP-ENV:Header/><SOAP-ENV:Body><SOAP-ENV:Fault><faultcode>SOAP-ENV:Client</faultcode><faultstring xml:lang="en">customerFault: Customer not found for id: 00000000-0000-0000-0000-000000000000</faultstring></SOAP-ENV:Fault></SOAP-ENV:Body></SOAP-ENV:Envelope>
500
```

## Result

Passed.

The generated app:

- validates and generates successfully;
- builds successfully with Maven;
- starts as a standalone Spring Boot app;
- accepts a real SOAP request on `/ws`;
- looks up the canonical `Customer` row by persistence ID;
- returns mapped SOAP response fields in the WSDL/XSD response shape;
- returns a deterministic not-found SOAP Fault;
- does not return the adapter-only missing-handler diagnostic;
- does not expose a stack trace, local filesystem path, or EdgeForge runtime dependency in the SOAP response.

## Focused Validation

```bash
git diff --check
.venv/bin/python -m pytest tests/unit/test_generation.py -q
.venv/bin/python -m pytest tests/unit/test_soap_contracts.py -q
.venv/bin/python -m pytest tests/unit/test_manifest.py -q
.venv/bin/python -m pytest tests/unit/test_validate_package.py -q
.venv/bin/python -m pytest tests/unit/test_build_emitter.py -q
.venv/bin/python -m appbuilder.cli generate \
  --manifest tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml \
  --output /tmp/edgeforge-soap-canonical-read-by-id-validation \
  --validate-schema
cd /tmp/edgeforge-soap-canonical-read-by-id-validation && mvn -q -DskipTests package
```

Observed:

- `git diff --check` passed.
- `tests/unit/test_generation.py`: 157 passed.
- `tests/unit/test_soap_contracts.py`: 16 passed.
- `tests/unit/test_manifest.py`: 47 passed.
- `tests/unit/test_validate_package.py`: 44 passed.
- `tests/unit/test_build_emitter.py`: 12 passed.
- Fresh proof generation created 30 files and reported `Harness: PASSED (static compatibility checks)`.
- Fresh proof Maven package completed successfully.

## Skipped / Out Of Scope

- No outbound SOAP canonical client invocation proof; this branch is inbound `read_by_id` only.
- No Studio, KS/KA, TestBench, shared-specs, upstream-producer, or demo worktree changes.
- No create/update/delete/search SOAP behavior proof.
- No new generated app dependency on EdgeForge runtime services was introduced.
