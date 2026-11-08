# Edge-Contract Integrated v1 Runtime Smoke

Date: 2026-06-09

Result: pass with one runtime configuration note.

## Scope

This smoke validates the final integrated Studio -> Engine edge-contract v1
package after file fixed-width/CSV, XML/XSD, SOAP/WSDL, generated-app test
console, and edge-contract Evidence Trail metadata implementation.

It proves the supported v1 runtime lanes together in one generated CRUD app.
It does not claim broader enterprise contract-family completion, strict
governance mode, production-complete staging idempotency, TestBench
generalization, or generated-app dependency on Studio/KS/KA/MCP/TestBench.

## Inputs

- Studio SHA: `0871844`
- Engine SHA used in smoke: `61583fc`
- Engine `origin/main`: newer than the smoke SHA; includes PR `#215`
  (`[FIX] Prevent duplicate REST operation DTO overwrite`) plus governance,
  security, and docs chores.
- Temp project:
  `/tmp/edgeforge-final-integrated-edge-contract-smoke/edge-contract-all-runtime-integrated-smoke.project.json`
- Export package:
  `/tmp/edgeforge-final-integrated-edge-contract-smoke/export/edge-contract-integrated-v1-smoke`
- Generated app:
  `/tmp/edgeforge-final-integrated-edge-contract-smoke/generated-app`
- Runtime port: `18199`

## Studio Validation

- Targeted evidence test: `47 passed`
- Package/project/KA-off tests: `123 passed`
- Full Studio suite: `1075 passed, 1 skipped`
- Studio export: passed
- Studio export warnings: `[]`

Studio-side edge-contract evidence implementation included:

- Studio PR `#190`: file fixed-width/CSV Evidence Trail metadata export.
- Studio PR `#191`: XML/XSD Evidence Trail metadata export.
- Studio PR `#192`: SOAP/WSDL Evidence Trail metadata export.
- Studio PR `#193`: combined file + XML/XSD + SOAP/WSDL Evidence Trail
  metadata proof.

Related Studio performance/governance closeouts included:

- Studio PR `#181`: Step 3 render performance, externalized large Step 3 JS.
- Studio PR `#182`: Step 6 GET purity, no no-op session writes.
- Studio PR `#186`: Step 3 full-review batching.
- Studio PR `#187`: Step 3 page badge batching.
- Studio PR `#188`: Step 6 rule badge batching.
- Studio PR `#189`: KA-ON batching docs closeout.

## Engine Validation

- `generate --validate-schema`: passed
- Harness: passed
- Maven package: passed
- Runtime: passed after starting the generated app with:

```bash
--spring.batch.jdbc.initialize-schema=always
```

The Spring Batch metadata initialization flag is a non-blocking runtime
configuration note and a v1.1 polish candidate, not a v1 blocker.

## Positive Runtime Checks

### REST/OpenAPI coexistence

- OpenAPI included as a JSON artifact.
- `customer-api` exported as `rest-json`.
- `POST /customers` worked.
- `GET /customers` worked.

### Fixed-width

- Inbound ingest persisted Account
  `11111111-1111-1111-1111-111111111111`.
- Downstream fixed-width output worked.

### CSV/delimited

- Pipe-delimited inbound ingest persisted Account
  `22222222-2222-2222-2222-222222222222`.
- Pipe-delimited downstream output worked.
- Delimiter `|` was preserved.

### XML/XSD

- XML ingest persisted Account
  `33333333-3333-3333-3333-333333333333`.
- XML output worked.
- XML root and namespace were preserved.

### SOAP/WSDL

- Inbound SOAP `getCustomer` canonical `read_by_id` returned HTTP 200.
- Outbound SOAP `syncCustomer` canonical `invoke_by_id` returned HTTP 200
  against a mock SOAP service.

### Staging handoffs

- `account-staging-handoff` exported under `data_handoffs[]`.
- `customer-staging-handoff` exported under `data_handoffs[]`.
- Both generated and compiled with the app.

Generated staging support can use run identity when the DDL contains the
expected columns. The tiny smoke staging tables still do not prove full
production restart/idempotency semantics.

### Batch/output

- `accountEodJob` completed.
- `customerEodJob` completed.
- Fixed-width and CSV output files were written.
- XML output files were written.

### Evidence Trail

- File metadata present.
- XML/XSD metadata present.
- SOAP/WSDL metadata present.
- No absolute local paths.
- No new evidence types such as `file_contract`, `xml_xsd`, `soap_wsdl`, or
  `identity_role`.
- Evidence Trail v1.1 shape preserved.
- KA OFF produced no KS/evidence noise.

## Negative Runtime Checks

- Unknown file contract: HTTP 404.
- Comma CSV against pipe contract: HTTP 400.
- Malformed XML: HTTP 400.
- Missing XML required mapped field: HTTP 400.
- Inbound SOAP unknown customer: SOAP fault / HTTP 500.
- Outbound SOAP missing ID: HTTP 400.
- Outbound SOAP unknown customer: HTTP 404.
- Outbound SOAP mock fault: HTTP 502.
- Outbound SOAP mock unavailable: HTTP 503.

## Non-blocking Follow-ups

- Spring Batch schema initialization should get first-class generated runtime
  config polish; this smoke used
  `--spring.batch.jdbc.initialize-schema=always`.
- Studio should still clean up or prevent empty duplicate REST interface export
  as package hygiene. Engine PR `#215` makes generation robust against duplicate
  REST operation DTO overwrite.
- Generated-app test console **Fill sample** currently produces deterministic
  typed-empty placeholders, not real package sample payloads. Future polish may
  rename/hide blank placeholder fills or add real package-sample loading after
  artifact packaging/serving is designed.
- TestBench remains scoped mainly to Kafka/router proof unless a future
  file/XML/SOAP runtime-proof trigger is explicitly chosen.

## Result

Passed.

The final integrated v1 package proved the current supported file, XML/XSD, and
SOAP/WSDL edge-contract runtime lanes together with Evidence Trail metadata
export, while preserving generated-app standalone operation.
