# Edge-Contract Handoff Readiness Matrix

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

> **What this is.** A single, honest, point-in-time status of the edge-contract
> families an adopting organization can rely on today — per family: what is
> proven, with which **re-runnable in-repo evidence**, the caveats, and what is
> explicitly future. It is for an adopter / compliance reviewer who needs to see
> a polished but truthful supported surface, not a mix of done / in-flight /
> design-only presented as ready.
>
> **Snapshot date:** 2026-06-09.
>
> **Anchored on:** the **edge-contract v1 closeout** (PR #220) and the final
> integrated Studio → Engine v1 runtime smoke
> ([edge-contract integrated v1 smoke, 2026-06-09](../test-results/edge-contract-integrated-v1-smoke-2026-06-09.md);
> Engine SHA `61583fc`; `origin/main` additionally includes PR `#215` fixing
> duplicate REST operation DTO overwrite).
>
> **Framing — read this.** Edge-contract **v1 core is closed and proven**; the
> **future families are planned**. This doc neither overclaims "everything is
> done" nor reopens v1 as unfinished. Where a claim can't be backed by the
> closeout evidence or a real in-repo fixture, it is marked lower, not higher.

## Status legend

| Status | Meaning |
|---|---|
| `implemented · proven` | Runtime works and is backed by the v1 closeout smoke and/or a re-runnable in-repo fixture. |
| `needs-UX-proof` | Runtime works, but the generated test-console / operator-UX surface is not yet separately proven. |
| `design-only` | A design (or explicit future-scope boundary) exists; no implementation yet. |
| `parked` | Out of the current waves; not started. Re-propose only with concrete demand. |

## Readiness matrix

> Edge contracts live under `upstream_interfaces[]` / `downstream_interfaces[]`;
> staging/table handoffs under `data_handoffs[]`. KA/KS do **not** auto-infer
> edge contracts. (See [§ Boundaries](#boundaries).)

| Family | Direction | Runtime status | Console-surfacing | Caveats |
|---|---|---|---|---|
| **REST / JSON (OpenAPI)** | inbound (upstream API) | `implemented · proven` | `implemented · proven` — CRUD cards | — |
| **Fixed-width files** | inbound + downstream | `implemented · proven` | `implemented · proven` — file cards | trailer record-count/sum reconciliation proven |
| **CSV / delimited files** | inbound + downstream | `implemented · proven` | `implemented · proven` — file cards | delimiter preservation + trailer reconciliation proven |
| **XML / XSD** | inbound + downstream | `implemented · proven` | `implemented · proven` — XML ingest/output cards | namespace/root preserved; negative diagnostics (malformed XML, missing required mapped field) proven |
| **SOAP / WSDL** *(bounded)* | inbound + outbound | `implemented · proven (bounded: read_by_id / invoke_by_id)` | `implemented · proven` — SOAP inbound/outbound cards | **bounded to two operation kinds only**; broader SOAP ops are `design-only` ([§ Future families](#future-families)) |
| **Staging / table handoffs** (`data_handoffs[]`) | downstream / handoff | `implemented · proven` to **generate + compile**; **not production-hardened** | via batch / EOD action cards (no dedicated interactive handoff card) | run identity / restart / idempotency semantics still pending ([caveat 3](#honest-caveats)) |
| **Evidence Trail** (edge-contract metadata) | export artifact | `implemented · proven` — Studio export | n/a — export artifact, not a console card | v1.1 shape preserved; no new evidence types; no identity-role evidence; no absolute local paths |

**Console-surfacing source of truth:** the generated test console renders cards
for CRUD, batch, file (CSV + fixed-width), XML, and SOAP actions
(`appbuilder/generation/ui_emitter.py`; asserted in
`tests/unit/test_operator_dashboard.py`). Staging handoffs are exercised through
the generated batch/EOD jobs (which are carded) rather than a dedicated
interactive handoff card.

## Golden smoke packages (re-runnable in-repo evidence)

Each proven family above is re-provable from a real in-repo manifest. Regenerate
from one (`python -m appbuilder.cli generate --manifest <path> --output /tmp/…`)
and exercise per [`docs/quickstart.md`](../quickstart.md). All paths verified to
exist at this snapshot.

| Family | In-repo golden package(s) |
|---|---|
| REST / JSON | `examples/input-projects/workspace-items/app-definition.yaml` (independent replacement; its new proof is recorded separately in [publication preparation](../public-content-preparation.md), not substituted for the historical smoke) |
| Fixed-width | `tests/fixtures/file-contracts/fixed-width-inbound-parser/`, `…/fixed-width-inbound-trailer-reconciliation/`, `…/fixed-width-downstream-record-types/` |
| CSV / delimited | `tests/fixtures/file-contracts/csv-inbound/`, `…/csv-inbound-trailer-reconciliation/`, `…/csv-downstream/` |
| XML / XSD | `tests/fixtures/edgecontracts/xml-xsd/account-roundtrip-runtime/` (+ negative: `…/xml-xsd/unsupported-choice/`) |
| SOAP / WSDL (bounded) | inbound: `tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/`; outbound: `tests/fixtures/edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/` |
| Staging handoffs | `tests/fixtures/file-contracts/fixed-width-downstream-record-types/`; `examples/input-projects/{loans-modernization,obie-wire-transfer,xyz-accounts-modernization}/` |

> **Honest note on the integrated smoke.** The final integrated v1 runtime smoke
> (the all-families-together proof, with positive + negative HTTP checks) ran
> against a temporary export package, not an in-repo fixture — its exact paths,
> SHAs, and results are recorded in the
> [smoke results doc](../test-results/edge-contract-integrated-v1-smoke-2026-06-09.md).
> The in-repo golden packages above re-prove each family individually.

## Honest caveats

These are carried up front, not buried:

1. **Batch metadata runtime config.** The generated app needs
   `--spring.batch.jdbc.initialize-schema=always` at start today; first-class
   generated batch-schema-init config is a known non-blocking follow-up (v1.1
   polish), not a v1 blocker.
2. **Console "Fill sample" is typed-empty.** The generated test console's "Fill
   sample" produces deterministic **typed-empty placeholders**, not real package
   sample payloads. Real package-sample loading is future polish (after artifact
   packaging/serving is designed).
3. **Staging-handoff production semantics pending.** Staging/table handoffs
   generate and compile with the app, but full production **run identity /
   restart / idempotency** semantics are not yet proven — a follow-up.
4. **SOAP is bounded.** SOAP runtime is proven **only** for canonical
   `read_by_id` (inbound) and `invoke_by_id` (outbound). All other SOAP
   operation kinds are future ([§ Future families](#future-families)).

## Future families

Clearly **not** part of proven v1 — listed so the supported surface stays
honest. None of these are implemented.

| Capability / family | Status |
|---|---|
| Avro / Schema Registry (Kafka serde) | `parked` (deferred until file/XML/SOAP stable; design doc not yet written — see the [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md) and issue #167) |
| MQ / JMS transport | `parked` |
| SFTP / object-store delivery | `parked` |
| Inbound DB interface tables | `parked` |
| Broader SOAP operation kinds (create / update / delete / search) beyond `read_by_id` / `invoke_by_id` | `design-only` (explicit future scope in the SOAP design docs) |
| Non-ID SOAP finder / uniqueness policies | `design-only` |
| SOAP response persistence / audit | `design-only` |
| File header semantic validation / checksums / partial-accept | `design-only` |
| Strict governance mode | `design-only` |

## Boundaries

- Edge contracts live under `upstream_interfaces[]` / `downstream_interfaces[]`;
  staging / table handoffs under `data_handoffs[]` only.
- KA / KS do **not** auto-infer edge contracts — they suggest; a human reviews;
  the Engine generates deterministically.
- The Evidence Trail carries **no** identity-role evidence.
- TestBench stays Kafka / router-focused; the file / XML / SOAP runtime proofs
  are Engine-side (generated-app + harness), not TestBench-bound.

## How to re-verify

1. Pick a golden package from the table above.
2. Regenerate and exercise it following [`docs/quickstart.md`](../quickstart.md)
   (clone → setup → `generate` → build & run → exercise the test console).
3. For the all-families-together evidence, see the
   [integrated v1 smoke results](../test-results/edge-contract-integrated-v1-smoke-2026-06-09.md).

> The G10 handover-evidence index will link this matrix (forward reference; the
> index is a separate item and is not created here).
