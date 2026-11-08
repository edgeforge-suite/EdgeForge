# Generated‑App Test Console UX Standard — Design

> **Status:** Design standard; implementation current through Slice 3c /
> Engine PR `#203`. Production-exposure policy is also enforced: shipped
> enterprise profiles omit the console, while the legacy-compatible profile
> retains it for local development.
>
> **Created:** 2026‑06‑06.
>
> **Scope:** The UX standard for the **operator/test console** when a target
> profile enables that generated static dashboard and the app has eligible
> actions. The shipped legacy-compatible profile enables it for local
> development; shipped enterprise profiles do not emit it. A custom profile
> that enables both the console and generated OAuth2 security requires
> authentication for the console root. This document defines a
> **contract‑family‑agnostic action‑card model** so that every current *and
> future* edge‑contract family renders into the same console with no bespoke UI,
> plus the contract‑awareness, workflow, and look‑and‑feel standards the console
> should meet when enabled.
>
> **Original design PR non‑goals:** No Engine/UI implementation, no
> Studio/KS/TestBench change, no manifest shape change, no generated‑app
> *runtime* (endpoint/controller) change. Current implementation progress is
> tracked in Section 12.
>
> **Builds on:**
> - [Generated App Quality Gate v1](generated-app-quality-gate-v1.md)
> - [Generated App Engine Roadmap](generated-app-engine-roadmap.md)
> - [Generated‑App SOAP Operator Dashboard Actions Design](../edgecontracts/generated-soap-operator-actions-design.md)
>   (the SOAP inbound/outbound cards are the **first concrete instance** of the
>   card model defined here)

## 1. Purpose and audience

The test console is the **runtime face of contract preservation** — the one
EdgeForge surface the adopting organization's own employees touch inside a generated app. It is a
**quick‑test / operator** surface, **not** the generated app's end‑user UI.

Target users when an organization adopts EdgeForge:
- **Onboarding / integration engineers** — "what does this service accept and
  emit, and does it match the spec?"
- **QA / UAT reviewers** — exercise each declared path, confirm behavior, attach
  evidence to a test record.
- **SRE / release** — fast pre‑deploy smoke of every contract path.
- **Developers** extending the generated app — fast repro, re‑run, copy‑as‑curl.

The console's job: let any of these users **exercise every declared contract path
of this app, see the result, and build pre‑cutover confidence — with no external
client or test tools** (no SoapUI, curl, or DB client required for exercising the
app's contract paths). The generated app itself may still have legitimate runtime
dependencies (database, message broker, etc.) — "no external tools" refers to the
operator's workflow, not the app's runtime stack.

## 2. Product boundary (what this is and is not)

| Is | Is not |
|---|---|
| A per‑app, local, single‑operator **test/operator console** | The generated app's **end‑user/product UI** |
| Generated **static HTML + vanilla JS**, served by the app | A framework/SPA with a build step |
| **Standalone** — calls only the app's own endpoints | Dependent on EdgeForge / Studio / KS / TestBench / MCP |
| **Deterministic** — rendered from the manifest/metadata | Hand‑authored or run‑dependent |
| **Manual** exercise + visual aids (history, pin/diff) | An assertion/pass‑fail/recipe/mock engine — that is **TestBench** |

These boundaries are hard constraints for every feature in this document.

## 3. Core principle — the contract‑family‑agnostic action‑card model

**The future‑proofing requirement:** adding a new edge‑contract family later (MQ/JMS,
Avro, gRPC, additional SOAP operation kinds, …) must slot into this console **with
no new dashboard code** — it should get a card, a coverage entry, a provenance
panel, input hints, history, and copy‑as‑curl *for free*.

This is achieved by making the console render from a small, uniform **action‑card
descriptor** that the Engine derives from contract metadata. The renderer is
**family‑agnostic**; only the descriptor varies.

### 3.1 Action‑card descriptor (the contract every family emits)

```
ActionCardDescriptor {
  family        : string   // "rest-crud" | "file" | "xml" | "soap-inbound" | "soap-outbound" | "batch" | <future>
  group         : enum     // UPSTREAM | DOWNSTREAM | HANDOFF | BATCH   (section placement)
  title         : string   // operation/contract/job name shown on the card
  actions       : Action[] // one or more invocations the card exposes
  responseShape : enum     // JSON | XML | SOAP | TEXT | FILE_RESULT
  provenance    : Provenance
  coverageKey   : string   // stable id for the coverage map
  hints?        : FieldHint[]   // required/type/min/max/pattern from manifest rules
  samplePrefill?: string|object // deterministic, typed-empty sample (optional)
}

Action {
  verb        : enum     // GET | POST | PUT | DELETE
  endpoint    : string   // e.g. "/files/ingest/{contractName}"
  inputControl: enum     // NONE | ID | PATH | TEXTAREA | FORM
  inputBinding: enum     // PATH_PARAM | JSON_BODY | RAW_BODY | QUERY | NONE
  headers?    : map      // e.g. SOAPAction
}

Provenance {
  contractName  : string
  direction     : enum   // UPSTREAM | DOWNSTREAM | HANDOFF
  sourceArtifact: string // packaged spec/WSDL/XSD/DDL/layout/sample path
  mappingRef?   : string // mapping file, if any
}
```

### 3.2 Input‑binding semantics

`inputBinding` tells the renderer **where** the user's input value goes in the
HTTP request — without this the renderer would need family‑specific submit logic
for each action (CRUD ID as a path segment vs SOAP outbound `{id}` as a JSON
body vs inbound SOAP raw XML body), which breaks the family‑agnostic promise.

| `inputBinding` | Renderer behavior |
|---|---|
| `PATH_PARAM` | Substitute the input value into the `endpoint` template placeholder (e.g. `GET /accounts/{id}` → `GET /accounts/42`). |
| `JSON_BODY` | Send the input value as a JSON request body (e.g. `{"id": "…"}` or `{"path": "…"}`). Content‑Type: `application/json`. |
| `RAW_BODY` | Send the input value as the raw request body verbatim (e.g. a full SOAP XML envelope). Content‑Type from `headers` (e.g. `text/xml`). |
| `QUERY` | Append the input value as a query parameter (reserved for future families; no current family uses it). |
| `NONE` | No input value — fire the request as‑is (e.g. `GET /accounts` list, or a legacy `POST /batch/run/{jobName}` with no body). |

**Endpoint template resolution is universal.** Before applying `inputBinding`,
the renderer resolves any `{placeholder}` segments in `endpoint` from the input
data (for FORM: extract the matching field; for ID: substitute the single value).
This is orthogonal to `inputBinding` — e.g. CRUD update (`PUT /…/{id}` FORM
JSON_BODY) resolves `{id}` from the form, *and* sends the full form as JSON body.

The renderer's submit function is a **single code path**: resolve endpoint
template, apply `inputBinding`, attach `headers`, fire `verb` + `endpoint`.
No `if (family === 'soap-outbound')` branches.

### 3.3 What the renderer does, uniformly, for every descriptor
- Places the card in its **group** section.
- Renders the **input control(s)** (NONE / ID / PATH / TEXTAREA / FORM) — a small,
  fixed control vocabulary that covers all current families.
- Renders **field hints** and an optional **"fill sample"** next to inputs.
- Wires **submit → fetch → response panel** by `responseShape` (JSON/XML/SOAP/TEXT/
  FILE_RESULT), with status badge + latency + timestamp.
- Adds the card to the **coverage map** (`coverageKey`) and a **provenance panel**.
- Wires **history**, **copy‑as‑curl**, and **export** generically (they operate on
  `Action` + last request/response, not on family‑specific logic).

**Family‑specific surface is intentionally tiny:** the `inputControl`,
`inputBinding`, and `responseShape` enums. A new family reuses existing values
where possible; a genuinely new shape adds **one renderer branch**, not a new
dashboard.

## 4. Current families expressed as descriptors (model validation)

The model must describe what already ships. It does:

| Family | group | actions (verb · endpoint · inputControl · inputBinding) | responseShape |
|---|---|---|---|
| `rest-crud` | UPSTREAM | create `POST /…` FORM JSON_BODY · get `GET /…/{id}` ID PATH_PARAM · list `GET /…` NONE NONE · update `PUT /…/{id}` FORM JSON_BODY · delete `DELETE /…/{id}` ID PATH_PARAM | JSON |
| `batch` | BATCH | run `POST /batch/run/{jobName}` NONE NONE | JSON |
| `file` | UPSTREAM/HANDOFF | ingest `POST /files/ingest/{contractName}` PATH JSON_BODY | JSON |
| `xml` | UPSTREAM/DOWNSTREAM | ingest `POST /xml/ingest/{contractName}` PATH JSON_BODY · output `POST /xml/output/{contractName}` NONE NONE | JSON |
| `soap-inbound` | UPSTREAM | send `POST /ws` TEXTAREA RAW_BODY (+ `SOAPAction` header) | SOAP |
| `soap-outbound` | DOWNSTREAM | invoke `POST /soap/outbound/{contractName}/{operationName}` ID JSON_BODY | JSON |

(SOAP rows are the design from the merged SOAP operator‑actions doc, now expressed
as two descriptors — confirming the model fits the newest family cleanly.)

### 4.1 Selected M5a-S2 extension (not yet emitted)

| Family | group | action | responseShape |
|---|---|---|---|
| `batch` (M5a opt-in) | BATCH | run `POST /batch/run/{jobName}` FORM JSON_BODY with required `runId` text + `businessDate` date fields | JSON |

M5a-S2 owns the controller body and card together: only an opted-in job receives the closed JSON
request shape and `FORM`/`JSON_BODY` card. Its run-ID hint uses the lesser of the physical staging
width and Spring Batch's 2500-unit parameter bound; `TEXT` therefore receives 2500. A legacy job keeps
the no-body `NONE`/`NONE` card. A mixed generated app therefore emits both descriptor shapes per job;
the renderer needs no new input-control or binding enum. This row is the selected S2 contract, not a
current-runtime claim. The renderer submits the run-ID text unchanged. It does not trim or
canonicalize identity: the generated S2 controller is authoritative and rejects boundary whitespace
or a Java UTF-16 length beyond the effective maximum before launch.

## 5. Tier 1 — contract‑aware features (uniquely EdgeForge; highest enterprise value)

These exploit that the app was **generated from declared contracts** — they're
free once descriptors exist:

1. **Contract coverage map** (top of dashboard) — every declared contract listed
   with a chip: *exercised this session / not yet tried / last status*. The runtime
   complement to the static compatibility harness (harness proves the code matches
   contracts; this tracks operator exercise). Drives pre‑cutover checklists.
2. **Per‑card provenance panel** — "preserves `POST /accounts` from `openapi.yaml`",
   "writes `ACCOUNT_STG` per `account.sql`", "SOAP `getCustomer` from
   `account-service.wsdl`". Instant traceability; reinforces contract preservation
   at runtime. Sourced from `Provenance`.
3. **Packaged‑artifact viewer** — render the packaged WSDL/XSD/OpenAPI/DDL/
   layout/sample files inline (read‑only). The console becomes self‑contained
   reference documentation; no hunting for the spec.
4. **Contract‑driven input hints + deterministic sample prefill** — show
   required/type/min‑max/pattern from manifest rules next to inputs, and a "fill
   sample" button that emits a valid‑*shaped* request (typed‑empty/sample, **no
   business inference**, same discipline as the SOAP envelope strategy).

## 6. Tier 2 — workflow / productivity (cheap, broadly useful)

5. **Session request/response history** (client‑side `localStorage`) per card —
   re‑run, inspect, compare last N.
6. **"Copy as curl"** on every action (verb, endpoint, headers, body) — reproduce
   outside the console; paste into a ticket/runbook (audit‑friendly).
7. **Export session log** (JSON/CSV, client‑side) to attach to a UAT/test record.
8. **Save / load named inputs** (`localStorage`) — *inputs only*, not recipes
   (recipe engine = TestBench).
9. **Manual "pin & diff"** a response — pin a baseline, visually diff the next.
   **Visual aid only — no automated verdict** (keeps it out of TestBench territory).
10. **Read‑only / safe‑mode toggle** — restrict the console to GET/read paths
    (hide create/update/delete/ingest/outbound‑invoke). "Explore without risk of
    mutating" — a strong fit for cautious enterprise environments.

## 7. Tier 3 — look & feel (high perceived value, low cost; CSS/JS only)

11. **Group cards within entity panels** by Upstream · Downstream · Handoffs ·
    Batch using descriptor `group`, with headers, icons, collapsible sections,
    and clean empty states.
12. **Status‑colored response badges** — 2xx green, 4xx amber, 5xx/502/503/504 red,
    **SOAP Fault visually distinct**; latency + timestamp + in‑flight spinner.
13. **Dependency‑free JSON/XML pretty‑print** with light syntax color (`<pre>` +
    CSS, no library).
14. **Money/temporal display correctness** — render `BigDecimal` money with scale
    and `java.time` values cleanly (not lossy raw JSON numbers).
15. **Non‑production banner** — persistent "NON‑PRODUCTION TEST CONSOLE · local
    only" + active profile/DB (H2 vs Postgres) + `appbuilder.demo.enabled` state.
16. **Config‑driven title + optional logo slot** (deterministic, from config) plus
    accessibility basics (labels, focus states, keyboard nav, `Ctrl+Enter` submit,
    ARIA on panels).

## 8. Future‑proofing — "adding a new edge‑contract family" walkthrough

When a future family lands (e.g. **MQ/JMS**, **Avro/Schema Registry**, **gRPC**, or
new SOAP operation kinds), the family author does **only** this:

1. Emit one or more `ActionCardDescriptor`s from the family's contract metadata
   (group, title, actions, responseShape, provenance, coverageKey, hints, sample).
2. Reuse existing `inputControl` (NONE/ID/PATH/TEXTAREA/FORM), `inputBinding`
   (PATH_PARAM/JSON_BODY/RAW_BODY/QUERY/NONE), and `responseShape`
   (JSON/XML/SOAP/TEXT/FILE_RESULT). Only add a new enum value **if** the family
   has a genuinely new input/response/binding shape — and that adds **one renderer
   branch**.

They get, for free: the card, group placement, coverage‑map entry, provenance
panel, input hints + sample, response panel, history, copy‑as‑curl, export, and
read‑only‑mode behavior. **No dashboard rewrite, no per‑family console code.**

**Family‑author checklist (normative):**
- [ ] Descriptor emitted from metadata (deterministic — same manifest → same card).
- [ ] `inputControl` / `inputBinding` / `responseShape` reuse existing values, or add exactly one.
- [ ] `provenance.sourceArtifact` points at the packaged contract artifact.
- [ ] `coverageKey` stable and unique.
- [ ] Card renders only when the family's contract exists (conditional parity).
- [ ] No new frontend dependency; no runtime/manifest change required for the card.

## 9. Constraints (hard)

- **Standalone:** cards call only the app's own endpoints; no EdgeForge/Studio/KS/
  KA/TestBench/MCP dependency in the generated app.
- **No framework / build step:** generated static HTML + vanilla JS; reuse the
  existing card/response‑panel pattern and palette.
- **Deterministic:** the UI (cards, coverage, provenance, hints) is generated from
  the manifest/metadata; same manifest → same console. Client‑side `localStorage`/
  session state is per‑browser and is **never** part of generation.
- **Config‑gated** consistent with today (`appbuilder.demo.enabled` for the data
  viewer); SOAP and other action cards follow the existing enablement model.
- **No secrets persisted**; show a security note.

## 10. Relationship to the SOAP operator‑actions design (#196)

The merged SOAP operator‑actions design is the **first concrete instance** of this
model: `soap-inbound` (TEXTAREA → `/ws`, SOAP responseShape) and `soap-outbound`
(ID → `/soap/outbound/{contractName}/{operationName}`, JSON responseShape with the
deterministic 400/404/502/503/504 mapping). When the SOAP cards are implemented
(its Slices 1–2), they should be built **as descriptors** under this model rather
than as one‑off cards, so the existing CRUD/file/XML cards and SOAP cards converge
on the same renderer. If implementing the model reveals a refinement to the SOAP
card spec, update that doc; this standard governs the umbrella UX.

## 11. Out of scope

- The generated app's end‑user/product UI.
- Any TestBench expansion; automated assertions, pass/fail gates, mock SOAP
  orchestration, or recipe‑as‑a‑product (history/pin/diff stay manual aids).
- Server‑side console state, authentication, or multi‑user.
- A frontend framework, bundler, or build step.
- Manifest shape changes or generated‑app runtime (endpoint/controller) changes.
- Production audit/observability (the app's concern, not the console's).

## 12. Implementation slices

| Slice | Scope |
|---|---|
| **Slice 0** | Done: this design doc + cross‑references. |
| **Slice 1** | Done: refactored the existing dashboard to render from `ActionCardDescriptor`s for the current families (CRUD, batch, file, XML) with no behavior change. |
| **Slice 2** | Done: Tier‑3 look & feel presentation: status badges, pretty‑print, non‑prod banner, money/temporal display, config title/logo slot, and a11y basics. |
| **Slice 2b** | Done: Tier‑3 grouping within entity panels: collapsible Upstream · Downstream · Handoffs · Batch sections driven by descriptor `group`, with the entity sidebar retained as primary navigation. |
| **Slice 3a** | Done: Tier‑1 contract‑awareness: coverage map + provenance panel. Coverage exercise state is client‑side `localStorage` only and never server‑side. |
| **Slice 3c** | Done: Tier‑1 input hints + deterministic sample prefill. Implemented as flat‑scalar typed‑empty client-side fill; no business inference and no SOAP envelope generation. |
| **Slice 3b** | Tier‑1 packaged‑artifact viewer. Deferred until an artifact‑packaging/serving decision lands: today only SOAP WSDLs are packaged/served by generated apps; OpenAPI, DDL, file layouts, samples, and mappings are not consistently packaged. |
| **Slice 4** | Done: SOAP descriptors (inbound + outbound) per the #196 design, on the model from Slice 1. |
| **Slice 5** | Backlog: Tier‑2 workflow: session history, copy‑as‑curl, export log, saved inputs, pin/diff, read‑only mode. |
| **Slice 6** | Backlog: generated‑output tests/sweep for descriptor coverage per family, conditional rendering, existing CRUD/file/XML/batch behavior, and build proof. |

Slice 1 was the enabling refactor. Slices 2, 2b, 3a, 3c, and 4 are implemented
on Engine main; Slice 3b remains deferred until artifact packaging/serving is
designed, and Slices 5--6 remain backlog.

Current non-blocking UX observation: the Slice 3c **Fill sample** control fills
deterministic typed-empty placeholders from descriptor hints. It does not load
real package sample payloads or infer business values. Future polish may rename
or hide the control when it would only populate blank placeholders, or add a
separate **Load package sample** path after artifact packaging/serving is
designed.

## 13. Open questions

1. **Descriptor source of truth.** Resolved for Slice 1 as an inline generated
   descriptor JSON/global in the static HTML. A later slice may move this to a
   generated `descriptors.json` if artifact packaging/serving needs it.
2. **Coverage persistence.** Resolved for Slice 3a as session‑only browser
   `localStorage`; never server‑side and never embedded into generation output.
3. **How much sample generation is safe in v1** (mirror the SOAP open question:
   flat‑scalar typed‑empty only; empty + helper otherwise).
4. **Artifact viewer rendering** — raw text vs light formatting for WSDL/XSD/DDL.
5. **Refactor‑first vs additive.** Resolved: Slice 1 refactored existing cards
   onto the model before SOAP cards landed, avoiding one-off SOAP dashboard code.
6. **Read‑only mode default** — off (full console) vs on (safe by default) for enterprise
   deployments.
