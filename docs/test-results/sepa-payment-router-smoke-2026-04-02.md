# SEPA Payment Router Passthrough-Router Smoke

Date: 2026-04-02

## Final Status

Green for Phase 2 scope.

This proof closes the passthrough-router archetype as generation-ready for Phase 2:

- manifest translation: PASS
- generation: PASS
- Maven build: PASS
- app startup + health: PASS
- routing decision at runtime: PASS
- documented remaining gap: live downstream connectivity requires deployed or mocked downstream systems

This is the passthrough-router equivalent of the agreed Phase 2 Option B framing:

- the generated app preserves the inbound route and routing decision behavior
- the generated app reaches the correct downstream client based on the routing rule
- live downstream success still depends on external systems or mocks being available at the configured `baseUrl`

## Smoke Table

| Step | Test | Result |
|------|------|--------|
| 1 | Package validation | PASS |
| 2 | Translation | PASS |
| 3 | Generation (15 files) | PASS |
| 4 | Maven build | PASS |
| 5 | App startup + health | PASS |
| 6 | INSTANT route — routing decision | PASS (`SctInstClient` selected) |
| 6 | INSTANT route — downstream call | FAIL (`404` — no mock downstream) |

## Translation Details

Routing rules recognized:

- `paymentType` -> `SCT_INST`
- `paymentType` -> `SCT`
- default -> `SDD`

Transforms recognized:

1. `amount -> settlementAmount`
2. `currency -> settlementCurrency`
3. `debtorIban -> debtorAccount`
4. `creditorIban -> creditorAccount`
5. `creditorName -> creditorFullName`
6. `remittanceInfo -> paymentReference`

Operations recognized:

- `routeSepaPayment`
- `submitInstantPayment`
- `submitCreditTransfer`
- `submitDirectDebit`

## Generated App

Generated output root used for the smoke:

- `/tmp/sepa-router-smoke/generated-app`

Key generated files:

- `InboundController` — `POST /payments/sepa`
- `TransformService` — upstream-to-outbound field mapping
- `RoutingService` — paymentType-based routing decision
- `SctInstClient`
- `SctClient`
- `SddClient`

Generation completed with:

- 15 files created
- no generation warnings

## Build And Runtime

Build:

- `mvn -q -DskipTests clean package` -> PASS

Jar name observation:

- bounded context is `payments`
- built jar is `payments-0.0.1-SNAPSHOT.jar`

This is correct for current Engine naming convention and should be noted by operators launching the jar manually.

Health:

- `GET /actuator/health` -> `200 OK`

```json
{"status":"UP","components":{"diskSpace":{"status":"UP","details":{"total":494384795648,"free":46828212224,"threshold":10485760,"path":"/private/tmp/sepa-router-smoke/generated-app/.","exists":true}},"ping":{"status":"UP"}}}
```

## Runtime Route Probe

Request:

```json
{
  "paymentType": "INSTANT",
  "amount": "500.00",
  "currency": "EUR",
  "debtorIban": "DE89370400440532013000",
  "creditorIban": "FR7630006000011234567890189",
  "creditorName": "ACME GMBH",
  "remittanceInfo": "Invoice 12345"
}
```

Observed behavior:

- inbound route matched: `POST /payments/sepa`
- routing decision selected `SCT_INST`
- generated client invoked downstream path `/instant-payments`
- runtime returned `500 Internal Server Error` because the downstream endpoint was not available as a real mock/service for the smoke

Observed response:

```json
{"timestamp":"2026-04-03T02:22:14.742+00:00","status":500,"error":"Internal Server Error","path":"/payments/sepa"}
```

Relevant runtime log:

- `HttpClientErrorException$NotFound: 404`
- downstream path: `/instant-payments`

## Documented Gap

Live downstream connectivity requires a deployed or mocked downstream system.

The generated clients use configured `baseUrl` values from `application.yaml`:

- `downstream.sct-inst.base-url`
- `downstream.sct.base-url`
- `downstream.sdd.base-url`

In smoke conditions, the `SCT_INST` base URL resolved to a localhost endpoint without a matching mock handler, producing the downstream `404`. This is a deployment/runtime concern, not an Engine generation gap.

## Conclusion

The passthrough-router archetype is proven for Phase 2 scope.

A realistic enterprise-domain package for SEPA routing by payment type across three downstream systems:

- translates cleanly
- generates cleanly
- builds successfully
- starts successfully
- exposes the correct inbound route
- executes the correct routing decision at runtime

The remaining documented limitation is external downstream connectivity, which is expected until deployed or mocked target systems are provided.
