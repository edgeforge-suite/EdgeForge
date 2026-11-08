# Generated‑App SOAP Operator Dashboard Actions — Design

> **Status:** Design proposal.
>
> **Created:** 2026‑06‑04.
>
> **Scope:** How a generated standalone Spring Boot app should expose **inbound**
> and **outbound** SOAP runtime paths as first‑class operator‑dashboard actions,
> matching the existing CRUD / batch / file / XML action cards — without any
> dependency on TestBench, Studio, KS, or the EdgeForge runtime.
>
> **Non‑goals:** No Engine implementation, no Studio change, no KS/KA change, no
> TestBench change, no manifest shape change, no generated‑app *runtime* change.
> This designs only the **operator UI surface** over runtime endpoints that
> already exist.
>
> **Builds on:**
> - [SOAP/WSDL Contract Support Design](soap-wsdl-contract-support-design.md)
> - [SOAP Canonical Operation Mapping MVP Design](soap-canonical-operation-mapping-mvp-design.md)
> - [Outbound SOAP Canonical Invocation MVP Design](outbound-soap-canonical-invocation-mvp-design.md)

## 1. Why this belongs in the generated‑app dashboard, not TestBench

The generated app already ships a **self‑contained operator dashboard** (a single
generated static HTML page with vanilla JS, served by the app itself) that lets a
developer or operator exercise the app's runtime paths locally. File ingest, XML
ingest/output, batch/EOD jobs, and CRUD all have action cards there today. SOAP is
the only proven runtime family **without** a card.

Putting SOAP actions in that same dashboard is the right home because:

- **Proof co‑located with the artifact.** The dashboard is part of the standalone
  deliverable. An operator who has the app running can prove SOAP behavior without
  installing or launching any second tool.
- **No runtime coupling.** The dashboard calls the app's *own* endpoints
  (`/ws`, `/soap/outbound/...`). It introduces no dependency on EdgeForge, Studio,
  KS, or TestBench — preserving the generated‑app standalone guarantee.
- **TestBench stays focused.** TestBench is intentionally Kafka/passthrough /
  route‑and‑broker oriented (scenario runner, correlation, NACK/DLQ). SOAP
  request/response and `invoke_by_id` are not broker‑shaped; forcing them into
  TestBench would duplicate the dashboard's per‑app action model and blur the
  TestBench product boundary. (See the TestBench feasibility review.)
- **Consistency.** A SOAP card next to the file/XML/batch cards keeps the operator
  mental model uniform: *one dashboard, one card per declared contract path.*

Reusable, repeatable, asserted, CI‑gated SOAP proof (mock orchestration, golden
comparison, suite pass/fail) is explicitly a **later, separate** concern and is
**not** in scope here.

## 2. Current generated dashboard capabilities (baseline)

The operator dashboard (`appbuilder/generation/ui_emitter.py`, operator‑dashboard
renderer) already renders action cards using a shared card pattern (`batch-action`
styling, a per‑card request control, a **Run** button, and a JSON response panel
showing status/body/latency):

| Path | Endpoint | Operator card today |
|---|---|---|
| CRUD | `/api/...` (controllers) | Create / Get‑by‑id / List / Update / Delete panels + live data viewer (`/api/demo/entities`, config‑gated by `appbuilder.demo.enabled`) |
| Batch / EOD | `POST /batch/run/{jobName}` | Batch action cards with output hints |
| File ingest | `POST /files/ingest/{contractName}` | Server‑side path input + invoke (under `app.file-ingest.base-dir`) |
| XML ingest | `POST /xml/ingest/{contractName}` | Server‑side path input + invoke (under `app.xml-ingest.base-dir`) |
| XML output | `POST /xml/output/{contractName}` | Invoke + output hint (under `app.xml-output.base-dir`) |

These cards render **only when the corresponding contracts exist** in the metadata.
The SOAP cards in this design follow the same conditional, same card pattern, same
response‑panel shape, and the same vanilla‑JS fetch approach.

## 3. The SOAP gap

Both SOAP runtime paths exist and are proven end‑to‑end, but neither is reachable
from the dashboard:

- **Inbound `/ws`** — the generated Spring‑WS endpoint (`@Endpoint` +
  `@PayloadRoot(namespace, localPart)`, dispatched at `/ws`, WSDL at
  `/ws/<service>.wsdl`) currently requires the operator to **hand‑craft a SOAP
  envelope** and POST it with an external tool (curl/SoapUI). There is no in‑app
  request builder.
- **Outbound `POST /soap/outbound/{contractName}/{operationName}`** — the generated
  outbound action controller exists and accepts `{ "id": "<value>" }`, but the
  dashboard exposes **no operator action** to call it; the operator must construct
  the POST by hand.

## 4. Inbound SOAP action design

**Trigger:** render an *Inbound SOAP* card group when the metadata contains one or
more inbound (`upstream`) `soap-wsdl` contracts. One card per **operation**.

**Each inbound SOAP card shows:**

| Field | Source | Notes |
|---|---|---|
| Contract / interface name | contract `name` | card heading group |
| Operation name | operation `name` | card title |
| Endpoint | `/ws` (read‑only) | the app's SOAP dispatch path; WSDL hint `/ws/<service>.wsdl` |
| SOAPAction | operation `soap_action` if present | shown as a read‑only hint; omitted/blank when the WSDL declares none |
| Request body | **textarea** | the SOAP envelope to send; pre‑filled with a deterministic sample when safe (see §6), else empty with helper copy |
| Submit | **Send SOAP Request** button | POSTs the textarea body to `/ws` with `Content-Type: text/xml; charset=utf-8` and the `SOAPAction` header when known |
| Response | JSON/text response panel | shows HTTP status, latency, and the **raw SOAP response or SOAP Fault body** |

**Behavior:**
- The card POSTs the operator‑supplied envelope verbatim to `/ws`. It does **not**
  transform, re‑order, or "fix" the envelope — what the operator sends is what the
  endpoint receives (honest runtime proof).
- The response panel renders the response body as returned (SOAP success envelope
  or `soap:Fault`). Fault vs success is distinguished by HTTP status and/or the
  presence of a `Fault` element (display treatment is an open question — see §11).
- This reuses the existing card + response‑panel pattern; only the request control
  differs (a textarea instead of a path input / id input).

## 5. Outbound SOAP action design

**Trigger:** render an *Outbound SOAP* card group when the metadata contains one or
more outbound canonical `invoke_by_id` action operations (the same set the
`OutboundSoapActionController` is generated from). One card per **operation**.

**Each outbound SOAP card shows:**

| Field | Source | Notes |
|---|---|---|
| Contract name | `OperationConfig` contract key | card heading group |
| Operation name | `OperationConfig` operation key | card title |
| Canonical entity | `OperationConfig.entity` | read‑only context |
| Lookup field | `OperationConfig.lookupField` | read‑only context (persistence‑ID field) |
| ID input | **text input** | the canonical row id to look up and invoke with |
| Submit | **Invoke Outbound SOAP** button | `POST /soap/outbound/{contractName}/{operationName}` with body `{ "id": "<value>" }` |
| Response | JSON response panel | status + the controller's structured response |

**Behavior (mirrors the generated `OutboundSoapActionController` contract):**
- **Success → HTTP 200**, body = `OutboundSoapActionSuccessResponse`
  (`contractName`, `operationName`, `entity`, `id`, response summary/body). Render
  in the standard response panel.
- **Deterministic error display**, mapped from the controller's
  `OutboundSoapActionFailureResponse` (`contractName`, `operationName`, `entity`,
  `id`, `status`, `error`, `message`):
  - **400** — missing/blank `id` (request body absent or `id` empty).
  - **404** — unknown contract/operation, **or** no canonical row for the id
    (missing‑row case).
  - **502 Bad Gateway** — a **remote `soap:Fault`** returned by the downstream
    service (`SoapFaultClientException`), or a generic SOAP client failure.
  - **503 Service Unavailable** — the **SOAP target is unavailable** (transport /
    connection failure, `WebServiceIOException`).
  - **504 Gateway Timeout** — the downstream SOAP call **timed out**
    (`SocketTimeoutException`).
- The card shows the `error`/`message` text from the failure response verbatim so
  the operator sees *which* deterministic failure occurred. (Whether to visually
  distinguish a remote SOAP Fault from a transport failure is an open question —
  §11.) The dashboard does **not** invent retries, fallbacks, or persistence.

## 6. Sample envelope strategy (inbound only)

The outbound card needs no sample (it is a structured `{id}` action). The **inbound**
card may pre‑fill the request textarea with a **deterministic skeleton envelope**,
under strict rules:

- **Deterministic generation is safe** when the inbound contract metadata provides
  the request element QName (namespace + local part) and a **flat, scalar** request
  field set (the same flat‑scalar scope the inbound canonical `read_by_id` mapping
  already supports). The skeleton is built purely from the schema:
  `soap:Envelope` → `soap:Body` → `<ns:RequestElement>` → one child element per
  declared scalar field, with **typed‑empty placeholders** (empty string, `0`,
  `0.00`, a schema‑shaped date), in **XSD sequence order**.
- **Show an empty textarea + helper copy** (the request element QName and a pointer
  to the packaged WSDL at `/ws/<service>.wsdl`) when: the request structure is
  nested/complex beyond the flat‑scalar scope, the XSD detail needed to build a
  faithful skeleton is unavailable, or generation would otherwise have to guess
  structure.
- **No business inference from operation names.** Placeholder values are
  type‑shaped only — never guessed business values, never derived from the
  operation or field name's apparent meaning. A `getCustomer` skeleton does not
  invent a customer id; it emits a typed‑empty `customerId` placeholder.
- The sample is a **starting point the operator edits**, clearly labelled as a
  skeleton, not a valid business request.

v1 may ship with **no** sample generation at all (empty textarea + QName/WSDL
helper) and add deterministic skeletons in a later slice — see §10 and §11.

## 7. UX constraints

- **Generated app standalone.** Cards call only the app's own endpoints; no call to
  EdgeForge, Studio, KS, KA, MCP, or TestBench.
- **No EdgeForge / TestBench runtime dependency** introduced in the generated app.
- **No new frontend framework.** Reuse the existing generated dashboard: vanilla
  HTML + JS, the `batch-action` card styling, the shared response‑panel renderer,
  and the existing fetch helper pattern (`runBatchAction`‑style). SOAP cards add a
  textarea (inbound) and a text input (outbound) — no new libraries, no build step.
- **Preserve existing dashboard patterns.** Same card layout, same status/body/
  latency response panel, same conditional rendering ("card only when contract
  exists"), same navy/white/light‑gray palette.
- **Config‑gating** consistent with current behavior: SOAP action cards follow the
  same enablement model as the other runtime action cards (the live data viewer's
  `appbuilder.demo.enabled` gate is unchanged).

## 8. Out of scope

- Mock SOAP service orchestration (standing up a downstream SOAP target to invoke
  against) — that is a TestBench‑shaped concern and is **not** added anywhere here.
- Any TestBench expansion.
- Response persistence, audit tables, retry/replay, or batch/all‑rows invocation.
- SOAP **headers** (WS‑Security, WS‑Addressing, custom headers) beyond what the
  generated runtime already supports — the cards expose only the currently
  supported request/response surface.
- Studio authoring/export changes (the mappings already exist and are exported).
- Any change to the generated **runtime** (endpoints, controller, client, faults).
- Formatted‑XML pretty‑printing libraries (raw display in v1; see §11).

## 9. Tests / future implementation expectations

When implemented (separate PRs), generated‑output expectations:

- A fixture with an **inbound** `soap-wsdl` contract → generated dashboard contains
  an **inbound SOAP card** per operation (endpoint `/ws`, operation name, SOAPAction
  hint when present, request textarea, submit, response panel).
- A fixture with an **outbound** canonical `invoke_by_id` action → generated
  dashboard contains an **outbound SOAP card** per operation (entity + lookup field
  context, id input, submit, response panel).
- A fixture with **no** SOAP contracts → **no** SOAP cards rendered (parity with the
  conditional file/XML card behavior).
- **Regression:** existing CRUD, batch/EOD, file ingest, and XML ingest/output
  dashboard cards and behavior are unchanged.
- Build proof: the generated app still builds (`mvn package`) with the added static
  cards (cards are static HTML/JS — no new server endpoints, no new deps).

## 10. Implementation slices

| Slice | Scope |
|---|---|
| **Slice 0** | This design doc + living‑doc references (this PR). |
| **Slice 1** | Inbound SOAP dashboard card: per‑operation card, `/ws` endpoint, SOAPAction hint, request textarea (empty + QName/WSDL helper), submit, response panel. Generated‑output test. |
| **Slice 2** | Outbound SOAP dashboard card: per‑operation card, entity/lookup‑field context, id input, `POST /soap/outbound/{contract}/{operation}` with `{id}`, deterministic 200/400/404/502/503/504 display. Generated‑output test. |
| **Slice 3** | Optional deterministic inbound sample‑envelope generation for flat‑scalar request shapes (typed‑empty placeholders, XSD sequence order); empty‑textarea fallback otherwise. |
| **Slice 4** | Generated‑output / build proof fixture(s) covering inbound‑only, outbound‑only, and no‑SOAP cases; assert regression of file/XML/batch/CRUD cards. |
| **Slice 5** | Manual runtime smoke: run a generated SOAP app, send an inbound request from the card, invoke an outbound action from the card, observe deterministic success/fault. |

Slices 1 and 2 are independent and can land in either order. Slice 3 depends on
Slice 1. Slices 4–5 follow.

## 11. Open questions

1. **Raw vs formatted response.** Should the response panel show the **raw** SOAP
   XML, or pretty‑print it? v1 leans raw (no formatting dependency, honest bytes);
   formatting could be a later, dependency‑free enhancement.
2. **How much sample generation is safe in v1.** Ship Slice 1 with **no** sample
   (empty textarea + QName/WSDL helper) and add deterministic skeletons in Slice 3,
   or include the flat‑scalar skeleton in Slice 1 from the start?
3. **Outbound endpoint override hints.** Should the outbound card surface the
   configured downstream SOAP target (e.g. the `app.soap.clients.<interface>.uri`
   config key and its current value/override) as a read‑only hint, so the operator
   knows *where* the invocation goes? Leaning yes, read‑only, no edit control.
4. **SOAP Fault visual distinction.** Should a remote `soap:Fault` (business/contract
   failure, **502**) be rendered visually distinct from a target‑unavailable
   transport failure (**503**), a timeout (**504**), and a local request error
   (**400/404**)? All arrive deterministically; a small status‑colored badge keyed
   on the controller's `error`/`status` could help without adding logic.
