# OBIE Payment Initiation Wire Transfer Smoke

Date: 2026-04-01

## Final Status Update

Updated: 2026-04-02

The original 2026-04-01 smoke was a red-state discovery run. After the merged Engine fixes in PRs `#57` through `#60`, the same `obie-wire-transfer` package is now green for the agreed Phase 2 scope.

Phase 2 closure decision:

- route contract preservation: PASS
- required server-set lifecycle fields on create: PASS
- generated app build/startup/runtime control flow: PASS
- documented remaining gap: real nested OBIE request envelopes (`Data` / `Data.Initiation`) still require a gateway/adapter layer before the generated service

That remaining gap is the explicit Phase 2 `Option B` decision:

- the generated app preserves the external OBIE route shape
- the generated app accepts the contract field names directly in the request body
- full nested upstream DTO-shape preservation is deferred as a later capability

## Final Rerun Result (2026-04-02)

Generated app used:

- `/tmp/obie-smoke-post60/generated-app`

Runtime port:

- `8093`

Control request used the correct PascalCase upstream contract field names:

```json
{
  "ConsentId": "CONSENT-20260401-001",
  "InstructionIdentification": "WIRE-20260401-001",
  "EndToEndIdentification": "E2E-20260401-001",
  "CurrencyOfTransfer": "GBP",
  "InstructedAmount": "1250.00",
  "CreditorName": "ACME SUPPLIER LTD"
}
```

Observed results:

| Step | Request | Result |
|------|---------|--------|
| 1 | `POST /international-payments` | `201 Created` |
| 2 | `GET /international-payments/{InternationalPaymentId}` | `200 OK` |
| 3 | `GET /international-payments` | `200 OK` |

Create response:

```http
HTTP/1.1 201
```

```json
{
  "InternationalPaymentId": "6a504e6b-2311-4a04-855b-6d0a632f8d44",
  "ConsentId": "CONSENT-20260401-001",
  "Status": "AcceptedSettlementInProcess",
  "StatusUpdateDateTime": "2026-04-02T14:25:28.124712",
  "CurrencyOfTransfer": "GBP",
  "InstructedAmount": "1250.00"
}
```

GET by ID response:

```http
HTTP/1.1 200
```

```json
{
  "internationalPaymentId": "6a504e6b-2311-4a04-855b-6d0a632f8d44",
  "consentId": "CONSENT-20260401-001",
  "instructionIdentification": "WIRE-20260401-001",
  "endToEndIdentification": "E2E-20260401-001",
  "currencyOfTransfer": "GBP",
  "instructedAmount": "1250.00",
  "creditorName": "ACME SUPPLIER LTD",
  "status": "AcceptedSettlementInProcess",
  "statusUpdateDateTime": "2026-04-02T14:25:28.124712"
}
```

GET list response:

```http
HTTP/1.1 200
```

```json
[
  {
    "internationalPaymentId": "6a504e6b-2311-4a04-855b-6d0a632f8d44",
    "consentId": "CONSENT-20260401-001",
    "instructionIdentification": "WIRE-20260401-001",
    "endToEndIdentification": "E2E-20260401-001",
    "currencyOfTransfer": "GBP",
    "instructedAmount": "1250.00",
    "creditorName": "ACME SUPPLIER LTD",
    "status": "AcceptedSettlementInProcess",
    "statusUpdateDateTime": "2026-04-02T14:25:28.124712"
  }
]
```

Conclusion:

- The `obie-wire-transfer` proof is green for Phase 2 scope.
- A generated app now builds, starts, preserves the spec route shape, accepts the OBIE contract field names used in the flat control request, persists successfully, and returns the created payment on both detail and list endpoints.
- The remaining known limitation is nested upstream envelope preservation. Real OBIE clients sending the full `Data` / `Data.Initiation` request body still require an adapter or gateway normalization layer before reaching the generated service.

## Goal

Build a realistic EdgeForge input package for an OBIE wire-transfer style app, run it through the Engine end-to-end, and capture what generates cleanly versus what breaks without fixing anything.

## Source Spec

- Source repo: `OpenBankingUK/read-write-api-specs`
- Repo commit pinned locally for this smoke: `2011fb5ec95e90df2e23143e8c6db643f03a1c2a`
- Local spec snapshot used in the package:
  - `examples/input-projects/obie-wire-transfer/contracts/payment-initiation-openapi.yaml`
- API title/version from the artifact:
  - `Payment Initiation API`
  - `info.version: 4.0.1`
- OpenAPI document version in the artifact:
  - `openapi: 3.0.0`

## Package Built

Input package root:

- `examples/input-projects/obie-wire-transfer/`

Package contents:

- `app-definition.yaml`
- OBIE local spec snapshot
- request/response samples for:
  - `CreateInternationalPayments`
  - `GetInternationalPaymentsInternationalPaymentId`
- upstream mapping file targeting real wire-transfer business fields
- staging-table handoff for settlement
- fixed-width confirmation file handoff
- simple rules for status allowed-values and currency format

## Commands Run

Manifest + translation inspection:

```bash
python3 - <<'PY'
from pathlib import Path
from appbuilder.contracts import load_project_definition
from appbuilder.metadata import translate_project
manifest = Path('examples/input-projects/obie-wire-transfer/app-definition.yaml')
project = load_project_definition(manifest)
metadata = translate_project(project, project_root=manifest.parent)
...
PY
```

Generation:

```bash
python3 - <<'PY'
from pathlib import Path
from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project
manifest = Path('examples/input-projects/obie-wire-transfer/app-definition.yaml')
metadata = build_metadata_project(manifest)
report = generate_application(
    metadata,
    Path('/tmp/obie-payment-smoke/generated-app'),
    source_manifest=str(manifest),
    generation_run_id='obie-wire-smoke',
)
...
PY
```

Generated app build:

```bash
mvn -q -DskipTests clean package
```

Generated app runtime:

```bash
java -jar target/wire_transfer-0.0.1-SNAPSHOT.jar --server.port=8091
curl -s http://127.0.0.1:8091/actuator/health
curl -s http://127.0.0.1:8091/international_payments
curl -s -X POST http://127.0.0.1:8091/international_payments ...
```

## What Passed Cleanly

### 1. Manifest package shape

- `load_project_definition()` succeeded
- The package shape is valid under the current manifest contract

### 2. Translation completed

- `translate_project()` completed
- One canonical entity was produced:
  - `InternationalPayment`
- Operations were recognized:
  - `CreateInternationalPayments`
  - `GetInternationalPaymentsInternationalPaymentId`
  - downstream file operation
  - staging handoff operation

### 3. Engine generation completed

- `generate_application()` succeeded
- Generated app output contained:
  - domain entity
  - repository
  - service
  - controller
  - request/response DTOs
  - Flyway migrations
  - staging writer
  - fixed-width handoff writer
  - batch job
  - demo UI
- Engine compatibility harness reported `passed=True`

### 4. Maven build completed

- `mvn -q -DskipTests clean package` succeeded
- Built artifact:
  - `target/wire_transfer-0.0.1-SNAPSHOT.jar`

### 5. Runtime startup completed

- Generated app started on `localhost:8091`
- Health check passed:

```json
{"status":"UP","components":{"db":{"status":"UP"},"diskSpace":{"status":"UP"},"ping":{"status":"UP"}}}
```

- List endpoint returned successfully:

```json
[]
```

## What Broke Or Drifted

### 1. Upstream mapping against real OBIE leaf fields is not honored from nested samples

The smoke package intentionally mapped the real business fields a wire-transfer app needs:

- `ConsentId`
- `InstructionIdentification`
- `EndToEndIdentification`
- `CurrencyOfTransfer`
- `InstructedAmount`
- `CreditorName`
- `InternationalPaymentId`
- `Status`
- `StatusUpdateDateTime`

Translation reported these as mapping errors because the current sample-based upstream ingestion only validates against top-level sample keys, while the OBIE payload nests those fields under `Data` and `Data.Initiation`.

Observed translation issues included:

- `Mapping source 'ConsentId' is not present in the request sample ...`
- `Mapping source 'InstructionIdentification' is not present in the request sample ...`
- `Mapping source 'InternationalPaymentId' is not present in the response sample ...`

At the same time, the nested wrapper fields were auto-included:

- `Data`
- `Links`
- `Meta`

### 2. Canonical model is polluted by OBIE wrapper fields

Generated domain entity:

- `InternationalPayment`

Generated fields included both the intended business fields and wrapper/container fields:

- `Data`
- `Links`
- `Meta`
- plus the mapped business fields

The generated entity source shows this directly:

```java
@Column(name = "data")
private String Data;

@Column(name = "links")
private String Links;

@Column(name = "meta")
private String Meta;
```

This means the app compiles, but the canonical model is not clean for a real OBIE wire-transfer shape.

### 3. Type fidelity drifted for important payment fields

Because the nested OBIE fields were not truly ingested from the upstream payload shape, type information for some business fields fell back to downstream/handoff constraints instead of real upstream semantics.

Observed type conflicts during translation:

- `instructedAmount`: upstream inferred as `string`, staging expects `decimal`
- `statusUpdateDateTime`: upstream inferred as `string`, staging expects `datetime`

The generated Flyway migration reflects that drift:

```sql
instructed_amount VARCHAR(18) NOT NULL,
status_update_date_time VARCHAR(255) NOT NULL
```

For a real payment app, these are semantically weak types.

### 4. Generated HTTP contract is CRUD-generic, not OBIE-contract-preserving

The generated controller exposes generic CRUD routes:

- `POST /international_payments`
- `GET /international_payments/{id}`
- `GET /international_payments`
- `PUT /international_payments/{id}`
- `DELETE /international_payments/{id}`

It does **not** preserve the OBIE path shapes from the source spec, such as:

- `/international-payments`
- `/international-payments/{InternationalPaymentId}`
- `/international-payments/{InternationalPaymentId}/payment-details`

So the app is runnable, but it is not yet a contract-preserving replacement for the OBIE Payment Initiation edge.

### 5. Create flow fails at runtime for the generated app

Startup and health succeeded, but create did not.

Request made:

- `POST /international_payments`

Result:

- HTTP `500`

Root cause from the generated app logs:

```text
NULL not allowed for column "STATUS"
```

The generated service does not populate required runtime fields like:

- `status`
- `statusUpdateDateTime`

before persisting the entity, even though the generated schema marks them `NOT NULL`.

So the smoke result is:

- generation/build/startup: green
- create runtime path: red

## Net Smoke Assessment

This package proved that the current Engine can:

- accept a realistic OBIE Payment Initiation package
- generate a compilable runnable Spring Boot app
- carry downstream handoff/file/staging scaffolding through generation

But it also surfaced that the current CRUD lane is **not yet sufficient for a real contract-preserving OBIE wire-transfer app**.

The biggest gaps exposed by this smoke are:

1. nested OBIE request/response field extraction for local-spec + sample-driven packages
2. canonical wrapper/container pollution (`Data`, `Links`, `Meta`)
3. semantic type drift (`decimal`/`datetime` collapsing to `string`)
4. generic CRUD route generation instead of source-contract route preservation
5. required payment lifecycle fields not being populated at runtime on create

## Conclusion

This is a useful red-state smoke, not a proof of readiness.

The package is realistic enough to show that EdgeForge can generate and run *something* from the OBIE Payment Initiation inputs, but the generated application is not yet a faithful wire-transfer replacement app. The next work should come from these specific blockers rather than from speculative feature expansion.
