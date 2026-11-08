# Handoff Security Boundary Map

> **Import-gate G8.** The trust-boundary / data-flow / attack-surface view a
> **security architect** reads at import — the architecture companion to the G7
> [Compliance & Portability Checklist](compliance-and-portability.md). It maps
> where the trust boundaries are, what data crosses each, where untrusted input
> enters, where the controls sit, and what the honest open items are.
>
> **Scope:** a *lightweight* now-doc, **not** a full threat model (that defers —
> see the roadmap's Compliance Hardening track). Every security claim below was
> **verified against the actual source** (the file/symbol is cited), not asserted.
>
> **Last updated:** 2026-07-24. This doc **references** the evidence pack as the
> single source of truth — G3 (secret/real-data scan), G4 (SBOM + licenses), G7
> (compliance/portability) — and does not re-derive it. The G10
> handover-evidence index will link this doc (forward reference).

## At a glance

| # | Question a reviewer asks | Short answer | Where |
|---|---|---|---|
| 1 | What is the central boundary? | **Design-time toolchain** (Engine/Studio/KS/KA/TestBench) vs **runtime generated apps**. Only the generated apps run in production with real data, and they have **zero runtime dependency** on the toolchain — so the toolchain is **not in the production blast radius**. | [§1](#1-the-central-boundary--design-time-vs-runtime) |
| 2 | Show me the trust boundaries | Diagram: untrusted contract inputs → Engine (design-time) → generated source → **[boundary]** → generated app in the enterprise (runtime). | [§2](#2-trust-boundary-diagram) |
| 3 | Where does untrusted input enter, per component? | Design-time: contract-file parsing (stdlib `xml.etree`) + user-directed OpenAPI fetch. Runtime: upstream REST/SOAP/XML endpoints, file ingestion, the operator test console, DB/downstream credentials. | [§3](#3-attack-surfaces-per-component) |
| 4 | Where are the controls? | Generated **payload/XSD validators and the first SOAP/SAAJ envelope parse** are hardened and runtime-verified; SOAP envelopes have a configurable byte cap and retain transport headers. **Design-time XSD/WSDL parsing rejects DTDs and is size/depth-bounded.** Engine OpenAPI fetching is SSRF-guarded. **No shipped profile emits OAuth2** — it exists only as a dormant internal skeleton, inactive by default in every shipped profile ([P1-5 design](generated-app-standards/generated-app-security-posture-design.md)); the supported v5 posture is gateway-delegated authentication. No secrets in repo (G3), env-var-required datasource credentials; **no production data to any LLM**; no phone-home. | [§4](#4-controls--boundaries) |
| 5 | What's still open? | Multi-tenant/per-user/object/row-level authorization (unsupported until adopter-owned, adversarially tested); SSO/RBAC (parked); transitive dep audit; adopter-owned ingress/concurrency limits for bounded SOAP buffering. | [§5](#5-honest-open-items--recommendations) |

---

## 1. The central boundary — design-time vs. runtime

This is the spine of the whole map. EdgeForge has **two populations of software**
on opposite sides of one boundary:

- **Design-time toolchain** — the **Engine** (`appbuilder`), **Studio**, the
  **Knowledge Server / Assist (KS/KA)**, and **TestBench**. These are
  **developer / build-time** tools. They run on a developer's machine or in a
  build pipeline, they process *contract definitions and sample data a developer
  supplies*, and they do **not** handle production traffic or live customer data.
- **Runtime generated apps** — the standalone Spring Boot applications the Engine
  emits. These are the **only** EdgeForge artifacts that run in production,
  terminate real upstream traffic, and touch real data.

**The load-bearing fact:** a generated app has **zero runtime dependency** on the
Engine, Studio, KS/KA, MCP, or TestBench (a non-negotiable suite invariant —
[`CONTRIBUTING.md`](../CONTRIBUTING.md), [`suite-architecture.md`](suite-architecture.md);
proven by the [Generated App Compile Check](../.github/workflows/generated-app-compile.yml)
building it with no suite on the classpath, and re-stated in G7
[§4](compliance-and-portability.md#4-generated-app-standalone-and-no-runtime-coupling)).

Therefore **the design-time toolchain is not in the production blast radius.** A
vulnerability in the Engine's XSD parser, for example, is a *build-host* concern
(an author feeding a malicious contract to their own tool), **not** a
production-runtime concern. The two surfaces have different threat models and
this doc keeps them separate everywhere.

## 2. Trust-boundary diagram

```
  DESIGN-TIME  (developer / build host — no production data)
  ─────────────────────────────────────────────────────────────────────────
   author-supplied contract inputs                  ┌────────────────────┐
   (XSD / WSDL / OpenAPI / sample files)  ──────────►│  Engine            │
        ▲  trust boundary: author input              │  (appbuilder)      │
        │  (stdlib xml.etree parse; package-         │  [THIS REPO]       │
        │   boundary guard on xs:include)            │  deterministic,    │
                                                     │  no AI in gen path │
   remote OpenAPI spec_url  ──user-directed fetch───►│                    │
        ▲  egress: policy-enforced pinned HTTP(S)    │  MCP = local stdio │
        │  fetch — ONLY outbound call (see G7 §3)    │  (no network)      │
                                                     └─────────┬──────────┘
                                                generated source │ (deterministic)
  ══════════════════════════════════════════════════════════════▼══════════
  ║  TRUST BOUNDARY — design-time  ⇢  runtime                                ║
  ║  generated app carries NO runtime dependency back across this line       ║
  ══════════════════════════════════════════════════════════════▼══════════
  RUNTIME  (enterprise environment — real data)
  ─────────────────────────────────────────────────────────────────────────
   upstream callers                  ┌──────────────────────┐
   REST/JSON · SOAP /ws · XML  ──────►│  Generated app       │──► downstream
        ▲  trust boundary:            │  (standalone Spring  │    handoffs
        │  untrusted network input.   │   Boot)              │    (files / staging
        │  payload + first SOAP/SAAJ  │                      │     tables / Kafka)
        │  envelope parse hardened    │  NO in-app auth in   │──► database
        │  + bounded (VERIFIED, §3b)  │  any shipped profile │    (env-required
   operator test console ────────────►│  (gateway-delegated, │     credentials)
   (NON-PROD, local-only, demo        │   P1-5)              │
    endpoints OFF by default)         └──────────────────────┘
```

Read it as: **untrusted input crosses two boundaries** — author-supplied
contracts into the design-time Engine, and untrusted network traffic into the
runtime generated app — and the **design-time → runtime boundary is one-way**:
generated source flows down; nothing the generated app does reaches back up.

## 3. Attack surfaces, per component

### 3a. Engine (design-time) — author-input trust context

**Contract-file parsing (XSD / WSDL).** The Engine validates XSD and WSDL bytes
with its bounded `appbuilder/core/xml_safety.py` pre-pass, then builds trees from
those validated bytes with Python **standard-library `xml.etree.ElementTree`**
([`appbuilder/contracts/xml_contracts.py`](../appbuilder/contracts/xml_contracts.py)
and [`soap_contracts.py`](../appbuilder/contracts/soap_contracts.py)).
Generation revalidates the exact source bytes before parsing, copying, or
performing its deterministic endpoint rewrite. Characterized **honestly, in its
trust context** (the input is a contract package an author supplies to their own
build tool — *not* untrusted network input):

- **External-entity resolution (XXE):** `xml.etree.ElementTree` does **not**
  resolve or fetch external general/parameter entities and does **not** retrieve
  external DTDs. So the classic XXE file-read / SSRF-via-entity vector is **not**
  reachable through this parser.
- **Entity-expansion DoS ("billion laughs" / quadratic blowup):** **hardened —
  the contract parsers reject DTDs outright.** An earlier revision of this map
  said the risk was "mitigated by modern `expat`"; that was **measured and found
  wrong** — on CPython 3.11 stock `ElementTree` expands the classic payload in
  full, because expat's amplification guard only trips well above these sizes.
  `appbuilder/core/xml_safety.py` now runs an `expat` pre-pass that refuses any
  document type declaration *at the declaration*, before a single entity is
  expanded, which forecloses entity declarations entirely. Documents are also
  bounded by size (`EDGEFORGE_XML_MAX_BYTES`, 10 MiB per document), nesting
  depth (`EDGEFORGE_XML_MAX_DEPTH`, 200), aggregate bytes per contract load
  (`EDGEFORGE_XML_MAX_TOTAL_BYTES`, 20 MiB), and distinct document count
  (`EDGEFORGE_XML_MAX_DOCUMENTS`, 100). `defusedxml` is **not** used. It can
  harden ElementTree by selecting its pure-Python parser, but it provides no
  size or depth bounds; adopting it would also add and maintain another runtime
  dependency across the declared requirements, lock, SBOM, and handover
  inventory while leaving the explicit resource caps necessary.
- **Real controls that *are* present (verified):** `xs:include` targets are
  constrained to **stay within the manifest package** — a path-traversal guard
  that rejects includes escaping the package boundary
  (`xml_contracts.py`, `_resolve_include_path`). `xs:import` and other
  out-of-scope constructs (`choice`/`any`/`union`/…) are **rejected**, not
  silently followed (`UNSUPPORTED_XSD_ELEMENTS` in both parsers).

> **No false "XXE-safe" blanket claim, no fearmongering:** ElementTree does not
> fetch external entities/DTDs (the dangerous part), and the input is
> author-trusted design-time data. Internal-entity DoS and unbounded include
> graphs are closed by DTD rejection plus per-document and aggregate bounds.
> **Scope, stated plainly:** the policy covers the parsers that ingest a
> manifest package and every generation-time XSD/WSDL re-read or byte copy.
> Translation and generation each validate the bytes they actually consume, so
> an on-disk contract mutation between those phases fails closed.

**Operator-supplied staging DDL (executable input).** Contract packages are not
uniformly inert data: a `data_handoffs[]` staging-table spec becomes an executable
Flyway migration in the generated app. Translation therefore validates the decoded
DDL text before it enters metadata or generation. The approved v1 boundary is
exactly one `CREATE TABLE` for a dedicated handoff physical table, using simple
portable ASCII unquoted identifiers, scalar types allowed by the selected H2 or
PostgreSQL target, and one inline or table-level `PRIMARY KEY` plus optional `UNIQUE`
constraints, followed only by optional simple `CREATE [UNIQUE] INDEX` statements on
that same table. Length and numeric precision modifiers are capped at the selected
database's declared maxima; oversized numeric tokens are rejected before conversion.
`IF NOT EXISTS` is rejected so the migration cannot silently attach a writer to a
pre-existing table. The table name is matched against `mapping.table` when declared,
must be unique across handoffs, and is checked against the finalized set of generated
entity tables plus Flyway and Spring Batch tables.

`DROP`, `ALTER`, `GRANT`, DML, defaults or expressions, procedural blocks,
foreign-key/check constraints, additional tables, cross-table indexes, invalid type
modifiers, target-incompatible types, reserved/non-ASCII identifiers, multiple
primary-key definitions, and every unrecognised construct fail translation with the
handoff name and permitted forms. Table-level primary-key columns are required mapping
targets, matching the database constraint. The exact decoded SQL text consumed by
translation is carried into generation unchanged; Engine neither repairs nor sanitises
it. Translation, metadata, and writer generation share the validated structured
table/column model, so accepted one-line and multiline DDL cannot diverge between the
trust-boundary decision and runtime writer emission.

**User-directed OpenAPI fetch (SSRF angle).**
[`appbuilder/ingestion/openapi_fetcher.py`](../appbuilder/ingestion/openapi_fetcher.py)
fetches the URL the **user/manifest supplies** (the CLI
`assess --swagger <URL>`, or a remote `spec_url` on an **upstream** interface
during `generate` — see G7
[§3](compliance-and-portability.md#3-telemetry-and-phone-home)) under a single
Engine-wide policy:

- only `http` and `https` are accepted;
- targets are resolved once and every connection is pinned to that vetted
  numeric address set while retaining the original HTTP `Host` and TLS
  SNI/certificate checks; ambient proxies are disabled;
- loopback, link-local, reserved, multicast, unspecified, and cloud metadata
  targets are always rejected; RFC1918/IPv6-ULA private service targets are
  denied by default;
- every redirect target is independently resolved, validated, and pinned;
  redirects are bounded and response bodies are capped at 5 MiB;
- an exact private/internal host may be deliberately enabled with
  `EDGEFORGE_OPENAPI_FETCH_ALLOWED_HOSTS` (comma-separated), but that exception
  relaxes only RFC1918/IPv6-ULA private-service denial and cannot enable metadata
  or the other special destinations. This is an operator-owned trust decision;
  the default remains fail-closed for internal targets.
- policy violations fail generation rather than falling back. Ordinary DNS or
  transport unavailability remains distinct: where an upstream interface has
  reviewed request/response samples, translation records the fetch failure and
  preserves the existing sample-ingestion fallback.

This remains a *design-time* capability: no credentials or production data are
attached to the fetch.
- It is **not** telemetry/phone-home: there is no fixed endpoint and no
  background call (verified in G7 §3).

**MCP server.** [`appbuilder/mcp_server.py`](../appbuilder/mcp_server.py) is a
**local stdio** server (`mcp.run()` over stdio — no host/port, no HTTP listener,
no network egress). It is a thin adapter over the same deterministic Engine
functions; architecturally a local pipe, not a network service (G7 §3).

### 3b. Generated app (runtime) — untrusted-network trust context

This is the surface that **matters most**, because it terminates untrusted
traffic and touches real data.

- **Upstream REST/SOAP/XML endpoints.** A generated app exposes the upstream
  interfaces its manifest declares (REST controllers, a SOAP `/ws` endpoint for
  WSDL-bounded contracts, XML ingestion for XSD contracts).
- **Inbound XML _payload_ parsing — VERIFIED hardened.** Every XML reader the
  Engine emits to read and XSD-validate a request **payload** builds its
  `DocumentBuilderFactory` with the **full OWASP XXE-prevention recipe** —
  confirmed by reading the emitted Java in
  [`appbuilder/generation/java_emitter.py`](../appbuilder/generation/java_emitter.py)
  (consistent across **every emitted payload/XSD validator**):

  ```java
  factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
  factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
  factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
  factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
  factory.setXIncludeAware(false);
  factory.setExpandEntityReferences(false);
  ```

  XSD validation (`SchemaFactory`) sets `ACCESS_EXTERNAL_DTD=""` and
  `ACCESS_EXTERNAL_SCHEMA="file,jar"`, and XML output (`TransformerFactory`)
  sets `ACCESS_EXTERNAL_DTD=""` / `ACCESS_EXTERNAL_STYLESHEET=""`. **DOCTYPE is
  rejected outright**, so XXE, external-entity SSRF, and external-DTD retrieval
  are all closed on these **payload / XSD validators**. **This is a strength, not
  a gap.** (Scope note: this is the DOM/XSD validation of the request *payload* —
  for SOAP it is **not** the first parse of the inbound envelope; see the next
  bullet.)
- **SOAP `/ws` envelope parse — VERIFIED hardened before SAAJ.** For an inbound
  SOAP endpoint, generated `SoapEndpointConfig`
  ([`java_emitter.py`](../appbuilder/generation/java_emitter.py)) supplies the
  named `SaajSoapMessageFactory` used by the Spring-WS servlet. Before SAAJ sees
  the envelope, that factory reads through a hard byte limit, rejects an
  oversized request, and performs a secure SAX pass with secure processing,
  DOCTYPE disabled, external general/parameter entities disabled, external DTD
  loading disabled, external DTD/schema access empty, and a bounded entity
  expansion limit. The replay remains a Spring-WS `TransportInputStream` and
  delegates the original MIME-header enumeration, so `Content-Type`,
  `SOAPAction`, and other transport headers still reach SAAJ. The default cap is
  1 MiB and is configurable with `APP_SOAP_MAX_ENVELOPE_BYTES`
  (`app.soap.max-envelope-bytes`). Unsafe or over-limit envelopes return the
  generated HTTP 400 SOAP-client fault before endpoint dispatch. Runtime
  acceptance covers external-entity, nested-expansion, and oversized envelopes,
  then confirms health and a valid SOAP request. **Residual boundary:** the app
  can buffer up to the configured cap during the validation/SAAJ passes; the
  ingress/container must also enforce request/concurrency limits appropriate to
  the deployment.
- **Operator test console.** Console emission is an explicit target-profile
  policy plus an eligibility check for actions the console can exercise. The
  shipped `springboot-legacy-compatible` profile retains the HTML **"Initial
  Test Console"** for local development; the shipped enterprise PostgreSQL
  profiles omit both `static/index.html` and its `DemoController`. A custom
  profile that emits both the console and the OAuth2 security skeleton requires
  authentication for `/` and `/index.html`; only `/actuator/health` is
  anonymously permitted. When emitted, the console remains banner-labeled
  **"NON-PRODUCTION TEST CONSOLE · local only"** and exercises the app's
  **real** endpoints, including write/command operations, so it **can mutate
  data**. Its demo/live-data endpoints are independently gated OFF by default
  behind `appbuilder.demo.enabled=false`.
- **DB / downstream credentials.** Datasource and downstream credentials are
  **env-var-injected** at runtime; enterprise PostgreSQL credentials are
  env-var-required / fail-fast — see the credential posture in
  [§4](#4-controls--boundaries).

## 4. Controls + boundaries

**Authentication / authorization — gateway-delegated for v5 (P1-5, Option A).**
**No shipped target profile emits in-application authentication or authorization.**
`appbuilder/generation/security_emitter.py`, gated on `target_profile.emit_security`, is an **internal
dormant emitter** — not a supported extension surface — and `emit_security` defaults `False` with zero of
the three shipped profiles setting it `True`. If a *custom* profile were registered with it enabled, the
Engine would emit a `SecurityConfig` wiring a stateless **OAuth2 JWT resource server**
(`oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))`), CSRF disabled, only
`/actuator/health` `permitAll`, and everything else `.authenticated()` — with no authority, object-level,
tenant-level, or row-level authorization defined, which is why it is not shipped active. See the
[P1-5 design](generated-app-standards/generated-app-security-posture-design.md) for the full decision and
the authorization envelope every generated app is supported under instead. Studio/KS SSO + RBAC are
**parked (P5)**, not in this release.

**Secrets — none in the repo; runtime via env-var injection.** No secrets are
committed (enforced every PR by the gitleaks scan — G3,
[`secret-and-data-scan.md`](handover-evidence/secret-and-data-scan.md)). At
runtime, datasource credentials are env-var-injected
([`target_profiles/catalog.py`](../appbuilder/target_profiles/catalog.py),
`${SPRING_DATASOURCE_USERNAME/PASSWORD}`).

> **A6 resolved:** enterprise PostgreSQL profiles require
> `SPRING_DATASOURCE_USERNAME` and `SPRING_DATASOURCE_PASSWORD` with no generated
> `postgres` fallback. Missing credentials fail fast during startup; the legacy
> H2 profile remains dev-only.

**AI / data-egress boundary — no production data to any LLM.** This is a top
reviewer question, stated clearly:

- The **Engine is deterministic** — there is **no AI/LLM inference in the
  generation path** (a core invariant in [`CONTRIBUTING.md`](../CONTRIBUTING.md);
  same manifest → byte-identical app).
- **No LLM or provider integration exists in the suite today** — there is no AI
  capability to enable. **KS-B5** gates any future provider layer (PII /
  sanitization / redaction) — a separate KS thread (G7
  [§5](compliance-and-portability.md#5-data-handling-posture), roadmap G9). If an
  adopter connects KS to a model-backed MCP host, that is a separate
  adopter-controlled data boundary and the sanitization gap applies there.
- Consequently **no production / customer data is sent to any LLM or external
  service** by EdgeForge.

**Network egress — only the user-directed OpenAPI fetch; no phone-home.** The
single outbound capability is the OpenAPI fetch in §3a (URL always supplied by
the user/manifest). No telemetry, analytics, or background calls anywhere in the
Engine or templates (method + result in G7 §3). Generated apps make only the
outbound calls their **manifest declares** (a downstream target, a Kafka broker),
all env-configured — never a call back to EdgeForge or to a vendor.

## 5. Honest open items / recommendations

Nothing security-relevant is hidden. A6 is recorded as resolved in §4; the table
below lists the remaining open items and recommendations, while retaining the
resolved OpenAPI-fetch row for implementation traceability.

| # | Item | Surface | Posture / recommendation |
|---|---|---|---|
| 1 | **Design-time parser defense-in-depth** | Engine XSD/WSDL (`xml.etree`) | **Resolved:** `appbuilder/core/xml_safety.py` rejects DTDs (and therefore entity declarations) via an `expat` pre-pass and enforces per-document size/depth plus aggregate bytes/document-count bounds across include graphs. Contract loaders and generation-time resource reads validate the exact bytes they consume, closing the translation-to-generation mutation window. External entities/DTDs were already not fetched. `defusedxml` was not adopted because it adds dependency/inventory maintenance and does not provide the size/depth/aggregate caps required here. |
| 2 | **Runtime XML parsers** | Generated app | **Payload/XSD validators and the first SOAP/SAAJ envelope parse are VERIFIED hardened** (§3b). SOAP envelopes have a generated 1 MiB default cap (`APP_SOAP_MAX_ENVELOPE_BYTES` override), preserve transport MIME headers during bounded replay, and fail with HTTP 400 before dispatch. Deployment ingress/container request and concurrency limits remain adopter-owned defense in depth. |
| 3 | **OpenAPI-fetch SSRF** | Engine (`openapi_fetcher.py`) | **Resolved:** HTTP(S)-only; DNS results are bound to pinned sockets with original Host/SNI/certificate checks; ambient proxies are disabled; special/private targets are denied by default; redirects are independently revalidated/pinned; responses are bounded. Exact internal hosts may allow RFC1918/IPv6-ULA addresses through `EDGEFORGE_OPENAPI_FETCH_ALLOWED_HOSTS`, but metadata and other special destinations remain denied. For air-gap, use **local `spec` files** (G7 §7). |
| 4 | **Operator test-console exposure** | Generated app | **Resolved:** shipped enterprise profiles omit the console and `DemoController`; the legacy-compatible profile retains the local-only console. Custom profiles that emit both the console and security require authentication for `/` and `/index.html`. Demo/live-data endpoints remain independently disabled by default. |
| 5 | **In-application authentication/authorization** | Generated app | **RESOLVED (design):** Option A — gateway-delegated for v5. No shipped profile emits in-application auth; the dormant OAuth2 skeleton is internal-only and not a supported extension surface. Object/tenant/row-level authorization is unsupported until adopter-owned application authorization is implemented and adversarially tested. See the [P1-5 design](generated-app-standards/generated-app-security-posture-design.md). |
| 6 | **SSO / RBAC** | Studio / KS | **Parked (P5)** — not in this release. |
| 7 | **Full transitive dependency audit** | Supply chain | The G4 inventory covers the **declared** surface; ≥1 transitive package reports `UNKNOWN`. A transitive audit **should not be skipped** (G4 / G7 §1 caveat). |

---

## Caveats summary (not buried)

- **Design-time XSD/WSDL parsing is bounded** — external entities were never
  fetched; DTDs (hence entity expansion) are now rejected outright and documents
  are bounded per file and cumulatively across include graphs. Generation-time
  contract resource reads revalidate the exact bytes they consume. `defusedxml`
  is deliberately not used for the dependency and resource-cap reasons in §3a.
- **Runtime XML/SOAP — VERIFIED hardened with a bounded envelope** — generated
  payload/XSD validators and the first inbound SOAP/SAAJ envelope parse reject
  DTDs/external entities; SOAP buffering is capped at 1 MiB by default and keeps
  transport headers intact. Tune the cap and enforce ingress/container limits
  for deployment concurrency (§3b, §5.2).
- **OpenAPI fetch is SSRF-guarded** — user/manifest-directed and design-time;
  connections are pinned to vetted DNS results, ambient proxies are disabled,
  and special/private targets are denied unless an exact host is explicitly
  allowlisted for RFC1918/IPv6-ULA service access. Metadata and other special
  destinations cannot be allowlisted (§3a, §5.3).
- **No shipped profile emits in-application auth** — gateway-delegated for v5 (Option A). The OAuth2
  skeleton is an internal dormant emitter, not active in any shipped profile (§4, §5.5, P1-5).
- **Generated-app datasource credentials** — enterprise PostgreSQL credentials are
  env-var-required / fail-fast (§4).
- **Operator console can mutate data when emitted** — shipped enterprise
  profiles omit it; the local profile keeps it non-prod/local-only with demo
  endpoints off by default (§3b).
- **Transitive dep audit pending** — G4 caveat (§5.7).

## See also

- [Compliance & Portability Checklist](compliance-and-portability.md) (G7) — the
  compliance companion to this architecture map.
- [Handover evidence](handover-evidence/dependencies.md) — SBOM + license
  inventory (G4); [`secret-and-data-scan.md`](handover-evidence/secret-and-data-scan.md)
  (G3).
- [Suite Architecture — START HERE](suite-architecture.md) — the suite map and
  the standalone-generated-app invariant.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — the authoritative invariants
  (deterministic, no-AI-in-gen-path, standalone generated apps).
