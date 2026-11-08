# EdgeForge Suite — Security Review Backlog (consolidated)

> **Status:** ACTIVE — prioritized remediation backlog from a suite-wide adversarial security review.
> **P0 is complete** (Studio PRs #276/#277/#278 + #279 follow-up). Sequencing below is reconciled across
> two independent reviewers and a third pass covering the generated-app handoff track.
> **Remediation note (2026-08-21; superseded for KS P1-8 below):** KS PR #37 plus Studio PRs #282/#283 completed P1-1;
> continuous cross-repo evidence refresh remains separate under P1-6. Engine PR #288 completed P1-4.
> Studio PRs #284–#293 completed P1-3, P1-7, and the **Studio portion** of P1-8 — dependency findings
> are zero **and** the CI gate is blocking. The standalone KS ingest notice under P1-8
> remained open on this date. See §2 below for the full control list and
> [the durable smoke evidence](test-results/studio-shared-mode-security-baseline-2026-08-21.md).
> **Current update (2026-09-24):** the standalone KS ingest notice under P1-8
> shipped in [KS #39](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/39).
> **Audit pins (historical — the SHAs the findings were measured against):** Engine `43fdc68` ·
> Studio `2d23c33` · KS `fb3a5e9`. **Remediation state is tracked separately** in
> `docs/tracker/suite-tracker.json` (`meta.snapshots`), which moves as fixes land — do not read these
> pins as current state. **TestBench excluded** (local tool;
> hardening tracked separately, not part of the enterprise-readiness verdict).
> **Provenance:** two independent adversarial reviews (Claude suite thread; Codex), each against full
> source for all three repos, followed by **two rounds of reconciliation**. Every finding below is
> either agreed by both reviews or confirmed by one at source. Severities are the reconciled position.
> **Deliberate omission:** findings are recorded at the altitude needed to **fix** them. Reproduction
> steps, proof-of-concept chains, and exploit mechanics are **excluded by design** and are not
> committed to any repository.
> **Audience:** internal remediation tracking, private repository. **Not adopter-facing** — see §6.

## Engine Nested-Input Confinement Follow-Up

**OPEN, Engine owner; documentation/ownership only (2026-10-03).**
Studio [#309 retained review observation](https://github.com/santosh-sh/EdgeForgeStudio/pull/309#issuecomment-5973217351),
draft head `01ef8600deb378f7ba7fe8da115921888a2cd5be`, retains frozen Engine
`5793cb2` accepting a nested local-spec symlink. Retained sibling evidence:
`docs/handover-evidence/studio-adversarial-handoff.md` and its JSON companion.
The review reports Studio preflight coverage for validate/assess/generate, but a
planted nested symlink gap at opt-in regeneration preview/apply. Entry-point root
checks are **not universal nested-input confinement**. This record does not
claim Studio merged/finally fixed the observation or that Engine confines every
nested input. No sibling implementation, new risk acceptance or broad sweep is
included. Owner decision: Engine must separately review nested input resolution
across relevant regeneration entry points before broadening confinement claims;
trigger: a scoped boundary change or next corresponding Engine security review.
#315/tracker reconciliation remains separate.

## Finding schema

**Release-policy supersession (2026-10-25):** approved
EF-V5-RELEASE-SCOPE-RESET revision 3 replaces older complete-M2-before-source-
publication instructions. [Current policy](v5-release-readiness.md) retains
required checks/audits, final exact-pair L5, newcomer/selected-Studio-image/
focused-security QA and independent release review. Existing Engine #335/#336
and Studio #318/#319 findings remain OPEN known limitations with accountable
owner Santosh Hommaradi; revisit on upstream/advisory, affected dependency/recipe,
next selection or production-pilot changes. No new Ubuntu/Jackson investigation,
exhaustive residual closure, signing infrastructure or new evidence tooling is
a source-release prerequisite. No factual finding, vulnerability acceptance,
supported-deployment obligation or historical evidence is changed.

Every finding carries seven fields, so that configuration risk is never presented as a current
exploit, and genuine live failures stay unmistakable:

**Exposure** · **Severity** · **Repo** · **Evidence** · **Remediation** · **Regression proof** ·
**Invalidates** (the existing security claim the finding falsifies — blank if none) ·
**Tracker mapping** (existing row to update, or `NEW` — existing work is mapped, never duplicated).

**Exposure types** — kept strictly separate; they warrant different responses *and* different
disclosure treatment:
- **LIVE** — exploitable now in a shipped or documented configuration.
- **LATENT** — safe only because a flag is set, a default holds, or a deployment assumption is honored.
- **DELEGATED** — genuinely the adopter's responsibility; the test is whether the delegation is stated
  where an **operator** reads it, not only where a **security architect** does.

**Documentation corrections ship with their finding**, not as a deferred cleanup pass. Each is captured
in the *Invalidates* field of the item that falsifies it.

---

## 1. P0 — one urgent security release, separate focused PRs

### P0-1 · Studio cross-session path containment
- **Exposure:** LIVE — **Severity:** CRITICAL — **Repo:** Studio
- **Evidence:** Imported project files restore server-side runtime path fields into live session state
  (`app/services/project_file_service.py:243`). The designated reader `session_export_dir()`
  (`app/services/path_resolver.py:40-51`) home-expands but applies **no session-workspace containment**;
  a second independent reader shares the gap (`app/routes/review.py:176-194`). Engine allowed-roots are
  then derived from those same untrusted paths (`app/integrations/appbuilder_integration.py:713-732`),
  so the Engine's fail-closed check validates the untrusted path against a root derived from it.
  Confirmed: cross-session read of another session's authoring state; cross-session write; build
  executes with an attacker-chosen working directory. **Code execution follows from the write and
  build-directory primitives but was not demonstrated end to end.**
- **Remediation:** Stop restoring server runtime paths from uploaded projects — rebind to the current
  session on import. Enforce containment inside `session_export_dir()` against the server-owned
  session workspace root. Derive Engine roots **only** from that trusted root, never from a request- or
  file-supplied path.
- **Regression proof:** Route-level tests that import a **hostile project file** through `/project/open`
  and assert cross-session read, cross-session write, and build-directory selection are all refused.
  Must exercise **Studio's own HTTP surface**, not the Engine CLI.
- **Invalidates:** the shared-mode isolation contract as documented; and the boundary-map statement that
  Studio sets a per-session **server-owned** Engine root.
- **Tracker mapping:** `sec-studio-session-path-containment` — **status `done`** (Studio PR #276). See §3.1 for why these rows carry no `sequence_rank`.
- **Note:** correct term is **cross-session** (shared multi-session authoring), not multi-tenant. This
  does not reduce severity.

### P0-2 · Shipped container and compose defaults
- **Exposure:** LIVE — **Severity:** CRITICAL (as launched from the shipped artifact) — **Repo:** Studio
- **Evidence:** The hazard is the **combination**: unrestricted **host port publication**
  (`docker-compose.yml`), shared mode unset — which disables CSRF, falls back to a reusable development
  session secret, and force-enables Build & Run — plus `--reload` and root execution (`Dockerfile` has
  no `USER`). *(The container's internal `0.0.0.0` bind is normal and not itself the flaw.)*
- **Remediation:** Publish to loopback only by default; remove `--reload`; add a non-root `USER`;
  provide explicit **local** and **shared** deployment profiles; **reject unsafe shared configuration at
  startup** instead of silently degrading. Make the Build & Run disable flag honored in every mode.
- **Regression proof:** Startup tests asserting refusal of unsafe shared configuration; a container test
  asserting non-root, no reload, and loopback publication.
- **Invalidates:** the deployment runbook's "keep it bound to localhost; do not expose the port" — the
  shipped runtime does the opposite.
- **Tracker mapping:** `sec-studio-container-defaults` — **status `done`** (Studio PR #278 + #279).

### P0-3 · Stored DOM XSS
- **Exposure:** LIVE — **Severity:** HIGH (CRITICAL where P0-2 exposure applies) — **Repo:** Studio
- **Evidence:** Persisted and imported contract/project values reach `innerHTML` and HTML attributes
  without output encoding — confirmed in passthrough and Kafka authoring templates, with further
  unescaped sinks identified and several divergent escape helpers, three of them incomplete. Studio's
  purpose is ingesting third-party contracts, so the source is attacker-influenced by design.
  Compounded by absent CSRF in local mode (P0-2) and the absence of any CSP (P2-1).
- **Remediation:** Replace string-built markup with safe DOM APIs or a single audited escaping helper;
  consolidate the divergent helpers. **Run a complete source-to-DOM-sink sweep — not only the confirmed
  templates.**
- **Regression proof:** Hostile-spec and hostile-saved-project tests asserting no script execution and
  correct encoding at each sink class.
- **Invalidates:** —
- **Tracker mapping:** `sec-studio-stored-xss` — **status `done`** (Studio PR #277).

**Sequencing:** P0-1 and P0-2 compound and belong in the same release, as **separate PRs** with
independent tests and rollback boundaries. P0-3 is independent and may land in parallel.

---

## 2. P1 — before any hosted/shared exposure or adopter handover

### P1-1 · KS runtime hardening — **resolved by KS #37 + Studio #282/#283**
- **Exposure:** LATENT (becomes CRITICAL if exposed) — **Severity:** HIGH — **Repo:** KS (+ Studio)
- **Evidence at the audit pin:** The entry point called `mcp.run()` without pinning transport
  (`knowledge_server/server.py:419-421`); FastMCP resolves transport/host/port from `FASTMCP_*`
  environment variables **and a CWD-relative `.env` file**, and no auth is configured on the server
  object. A single working-directory `.env` could select HTTP transport, an all-interface host, and a
  port; no separate process-environment host override or proxy was required. The `.env` vector is the
  sharp edge: KS's defaults made the working directory triple-purpose (default store, default ingest
  root, **and** config source), and `.env` was not gitignored. Separately: the standalone startup path
  could perform FastMCP's PyPI **version check**
  (cached; suppressed when Studio launches KS, which sets the banner variable — but **not** for
  standalone launches, the documented usage); only version/IP/timing metadata leaves, **not operator
  data**. Error-detail masking is off, so a rejected ingest returns the configured allow-roots. Studio
  passed roots and store path to the KS child but **not shared mode**
  (`app/integrations/ks_integration.py`), so KS's fail-closed guard never engages; KS allow-roots
  default to the process working directory when unset, with no test on that branch.
- **KS remediation shipped:** KS PR #37 pins the supported FastMCP runtime, forces local stdio despite
  hostile transport settings, disables the banner/update lookup, masks filesystem details in errors,
  requires explicit roots and DB path in shared mode, and ignores repository `.env` files. Its
  adversarial regression suite covers those KS-owned guarantees.
- **Studio remediation shipped:** Studio PRs #282/#283 propagate shared mode to the KS child while
  retaining per-session roots/DB paths, preserving solo/local behavior, and proving KA-OFF
  zero-spawn behavior.
- **Regression proof:** KS PR #37 owns hostile-environment, no-listener, no-update-call,
  path-redaction, and unset-root tests; Studio PRs #282/#283 own shared-mode propagation,
  fail-closed startup, local-mode compatibility, and KA-OFF zero-spawn tests.
- **Invalidates:** The broad historical transport/egress claims were narrowed by KS PR #37. P1-1 is
  complete; refreshing continuous cross-repo adversarial evidence remains separate under P1-6.
- **Tracker mapping:** `sec-ks-runtime-hardening` — **status `done`**.

### P1-2 · Engine design-time parser hardening — **resolved by Engine PR #281**
- **Exposure at audit baseline:** LATENT — **Severity:** HIGH — **Repo:** Engine
- **Relationship to existing work:** this was **not a new backlog item**. The review expanded and
  sharpened the existing M1 follow-on `sec-defusedxml` ("Design-time parser defense-in-depth") by
  identifying missing bounds, an under-counted parser inventory, and the absence of a usable
  platform-parser guarantee.
- **Historical evidence at the audit pins:** The Engine's own design-time parsers applied no complete
  size/depth bounds across contract-loader and generation-time XSD/WSDL reads. Entity-expansion
  protection was not effectively inherited from the platform XML library: on CPython 3.11.15 with
  expat 2.7.4, the classic payload expanded to 30,000 characters, and `XMLParser` exposed no `.parser`
  attribute for the usual `defusedxml` hook.
- **Remediation shipped:** Engine PR #281 validates the exact bytes consumed by contract loaders and
  generation-time resource reads, rejects DTDs, and enforces per-document size/depth plus aggregate
  byte/document bounds across include graphs. The implementation deliberately did not add
  `defusedxml`, because that dependency alone does not provide the required resource caps.
- **Regression proof:** focused contract-loader, generation-resource, include-graph, encoding, and
  Engine-parity tests cover oversize input, deep nesting, DTDs, aggregate limits, and exact-byte
  validation. Merged tracker row `sec-defusedxml` is `done`.
- **Invalidated historical claim:** the boundary-map argument that design-time parsing risk was
  acceptable because inputs were author-supplied to their own build tool; shared-mode authoring
  contradicted that premise. The corrected boundary and completed remediation now supersede it.
- **Tracker mapping:** **`sec-defusedxml` — status `done`**. Do not create a second row.

### P1-3 · Studio web-security baseline — **resolved by Studio PRs #284–#293**
- **Exposure at audit baseline:** LIVE / LATENT — **Severity:** HIGH — **Repo:** Studio
- **Evidence at audit baseline:** Dependency scan recorded **19 findings** while CI emitted a warning
  rather than failing.
  URL fetching lets an allowlisted hostname short-circuit private-address verification and reads the
  response body with no size cap. Default API documentation routes (`/docs`, `/redoc`,
  `/openapi.json`) are exposed. Raw subprocess output — including tracebacks with absolute server
  paths — is returned to clients on validate/assess paths. Upload validation is extension-based with no
  content-type check, and body size is enforced after the request is materialized. No rate limiting.
- **Remediation shipped:** Studio PRs #284/#285 reduced dependency findings to zero and #286 made the
  `pip-audit --strict` CI gate blocking, with no advisory wrapper. #288 adopted the Engine's
  address-pinned, peer-verified, size-bounded fetch policy (§5) for OpenAPI URL fetching. #289 gates
  `/docs`/`/redoc`/`/openapi.json` behind an explicit setting (off by default) and centralizes sanitized
  diagnostics instead of raw subprocess output. #290 makes shared-mode audit durable — the sink setting
  now accepts `{"noop", "sqlite"}` and defaults to `sqlite` under `shared_mode`, where it previously
  accepted only `noop`. #291 adds pre-materialization request bounds and upload MIME/content-type
  policy. #292 adds shared-mode per-principal/process rate and concurrency controls. #293 aligns
  Studio's regeneration XML discovery with the Engine's fail-closed DTD policy.
- **Regression proof:** Studio's own suites — `tests/test_openapi_fetch_guard.py` (687 new lines),
  `tests/test_request_resource_limits.py` (711 new lines), `tests/test_upload_request_policy.py` (476
  new lines), `tests/test_audit_persistence.py` (671 new lines), `tests/test_browser_security.py`,
  `tests/test_diagnostics.py`. Independently corroborated at source for this reconciliation (settings,
  fetch-guard connection path, audit-sink allowed values); full integrated-smoke and closure-smoke
  results are recorded in
  [the durable evidence record](test-results/studio-shared-mode-security-baseline-2026-08-21.md).
- **Invalidates:** the "CI gate non-blocking" and "web controls open" language in the prior remediation
  note above and in `M2-suite-vulnerability-assessment`'s prior summary.
- **Tracker mapping:** `sec-studio-web-baseline` — **status `done`** (Studio PRs #284–#293).
  `M2-suite-vulnerability-assessment` stays **in-progress** — Studio's web surface is resolved;
  the [current source-release record](v5-release-readiness.md#source-release-known-limitations-and-m2)
  enumerates the remaining M2 coverage and disposition work.

### P1-4 · Engine staging-DDL executable-input boundary — **resolved by Engine #288**
- **Exposure at audit baseline:** LATENT — **Severity:** HIGH — **Repo:** Engine
- **Remediation shipped:** Engine PR #288 treats staging DDL as executable contract input.
  Translation accepts only
  one table-scoped `CREATE TABLE` with portable ASCII identifiers, target-compatible scalar columns,
  target-specific length/precision caps, one primary key, and optional unique constraints/indexes on
  that table. Oversized modifier tokens fail before integer conversion. `IF NOT EXISTS` is rejected;
  the declared table must be unique across handoffs and is checked against the finalized generated
  entity set plus infrastructure tables. Table-level PK fields are required mapping targets. The
  mapping-declared table name is enforced when present; all other or unrecognised forms fail closed.
  The exact decoded SQL text consumed by translation remains authoritative and is copied unchanged —
  no silent SQL rewriting.
- **Regression proof:** Translation-level tests reject `DROP`, `ALTER`, `GRANT`, DML, procedural,
  malformed/unrecognised, invalid identifier/type-modifier, target-incompatible type, multiple-PK,
  `IF NOT EXISTS`, duplicate/finalized-entity/infrastructure-table, multiple/cross-table, and
  mapping-table mismatch inputs. A table-level-PK regression proves required mapping semantics; a
  one-line valid DDL regression proves the shared validated model emits all runtime writer columns;
  target maximum and max-plus-one cases cover H2/PostgreSQL length and numeric precision, plus a
  5,000-digit fail-closed diagnostic. The negative control removes the ingest gate and proves the
  refusal test fails rather than passing vacuously.
- **Invalidates:** the implicit assumption that contract packages are inert data.
- **Tracker mapping:** `sec-engine-ddl-trust-boundary` — **status `done`** (Engine PR #288).

### P1-5 · Generated-app security posture decision — **resolved; Slices 1–4 delivered**
- **Exposure:** **DELEGATED** — **Severity at audit baseline:** HIGH — **Repo:** Engine
- **Decision and remediation shipped:** Option A is the supported v5 posture. No shipped target profile
  emits in-application authentication or authorization. Production requires an authenticated,
  TLS-terminating gateway, and the application port must be unreachable except through it. All
  authenticated callers share one authorization domain; multi-tenant, per-user, object-level, and
  row-level authorization remain unsupported. Rate limiting is gateway-owned. Generated READMEs for
  CRUD, passthrough, and Kafka now state this complete boundary without treating a trusted network as
  an alternative; CRUD/passthrough `agent-context.md` uses the same shared guidance.
- **Kafka hardening shipped:** actuator exposure defaults to health only. Metrics and Prometheus require
  `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,metrics,prometheus` and the non-bypassable gateway
  boundary. The Prometheus registry remains packaged for operator opt-in.
- **Regression proof:** An exact-key profile matrix covers all three shipped profile IDs and their
  `emit_security`/test-console posture. Generated README tests cover all archetypes. A deterministic,
  broker-independent generated-JAR test proves health-only default exposure and the explicit opt-in.
  Slice 2 source and generated MockMvc tests prove page-size and database-offset rejection before any
  service call, plus exact-bound acceptance and deterministic generation.
  Slice 3 source and generated MockMvc tests prove passthrough supported-required/code-point-length
  validation returns a sanitized 400 before transform, routing, or downstream collaborators.
  Required-nullable OpenAPI 3.0/3.1 inputs fail closed before generation; omitted/explicit-null required
  values and ASCII plus supplementary-Unicode exact/max-plus-one boundaries are covered alongside
  dependency inventory, standalone-app independence, and deterministic generation.
- **Post-#304 required-shape closure:** the reader-first follow-up inventories OpenAPI property readers,
  routes supported nested upstream-request `$ref`/`allOf` properties through the shared dialect-aware resolver, fails
  before generation for unrepresentable effective required upstream fields, and propagates deterministic
  contextual diagnostics for compatibility-permitted skips. PR #304's top-level-only statement remains
  its historical merge boundary rather than the current Engine boundary.
- **Universal header baseline shipped:** every generated CRUD, passthrough, and Kafka application emits
  the four TLS-independent P2-1 headers exactly once. Plain-HTTP HSTS is deliberately absent and remains
  gateway-owned. The dormant OAuth2 emitter remains internal, inactive, and unsupported.
- **Tracker mapping:** `gate-genapp-auth-default` is **done**; `post-oauth2-idp-wiring` now records the
  adopter-owned authenticated-gateway deployment obligation rather than nonexistent skeleton wiring.

### P1-6 · Repair security evidence, then make it continuous
- **Exposure:** LATENT — **Severity:** HIGH — **Repo:** all three
- **Historical review evidence (2026-07; superseded in part below):** The cross-repo isolation acceptance run proves a pinned baseline; **no workflow in any
  repo re-runs it**, and there is no cross-repo version-compatibility enforcement. The isolation suite
  asserts **separation** (sessions get different paths) but never **access attempts** (one session
  reaching another's data). The cross-repo negatives invoke the Engine directly **with the correct root
  supplied**, so they never test whether Studio supplies the right one — the actual failure (P0-1).
- **Remediation:** Convert the isolation suite to adversarial cases covering the complete Studio→Engine
  trust handoff, KS error payloads, and hostile environment settings; add it to CI; refresh the
  acceptance run against current pins; build the approved **M3** change-aware verification pack; define
  a compatibility/pin mechanism across the three repos.
- **Bounded pin prerequisite (2026-09-12):** `docs/suite-release-candidate.json` now supplies one
  explicit Engine/Studio/KS candidate selection and `scripts/verify_suite_pairing.py` provides its
  read-only clean-checkout preflight. Matching pins do not prove compatibility, security, or release
  acceptance. The adversarial evidence refresh, continuous execution, and full M3 work remain open,
  so P1-6 stayed pending at that checkpoint.
- **Current bounded delivery (2026-10-06):** Studio #309 delivered adversarial
  caller defenses and actual Engine/KS proof, including the independently found
  regeneration preflight gap. Its [evidence](https://github.com/santosh-sh/EdgeForgeStudio/blob/e17eeaa317fb23147ff27dba553e7ee9c7ed867f/docs/handover-evidence/studio-adversarial-handoff.md)
  records original and repaired proof separately, optional live-case boundaries
  and Engine/host-filesystem limitations. The old claim that no access attempts
  are tested is no longer current. Reuse the suite; do not reimplement #309.
  Current selected-pair acceptance remains required. Continuous cross-repo
  enforcement belongs to post-v5 M3; remaining direct-Engine/nested-input
  limitations need scoped disposition, not an implied universal sandbox.
- **Regression proof:** the suite itself, gated per-PR.
- **Invalidates:** the isolation acceptance evidence as a *current* guarantee — it is historical.
- **Tracker mapping:** `sec-suite-evidence-repair` — **status `in-progress`**, with continuous execution folded into
  **`M3-change-aware-verification-pack`** rather than reimplementing M3.

### P1-7 · Studio audit durability decision — **resolved by Studio PR #290**
- **Exposure at audit baseline:** DELEGATED + documentation defect — **Severity:** MEDIUM-HIGH —
  **Repo:** Studio
- **Evidence at audit baseline:** Audit terminates in a no-op sink; configuration permits no other
  value, so no operator can enable durable audit; failures are swallowed. Consequence: none of P0-1's
  cross-session activity would leave a forensic trace.
- **Remediation shipped:** Studio PR #290 provides a durable SQLite audit sink. `audit_sink` now accepts
  `{"noop", "sqlite"}` (previously `{"noop"}` only) and defaults to `sqlite` when `shared_mode` is set,
  with degradation visibility rather than silent swallowing.
- **Regression proof:** `tests/test_audit_persistence.py` (671 new lines).
- **Invalidates:** —
- **Tracker mapping:** fold into `sec-studio-web-baseline` — **status `done`**.

### P1-8 · Real-data handling surfaced at point of use — **Studio and standalone KS resolved**
- **Exposure at audit baseline:** DELEGATED — **Severity:** MEDIUM-HIGH — **Repo:** Studio (+ KS)
- **Evidence at audit baseline:** The position that operator inputs may contain real or sensitive data
  and are **not sanitized** exists only in compliance documents. At that baseline, Studio's README and
  actual upload surfaces carried no such notice; standalone KS ingest still carries no point-of-use
  notice for direct KS operators.
- **Studio remediation shipped:** Studio PR #290 (`88b996e`) — the same commit that shipped the durable audit
  sink also added the point-of-use notice ("Use synthetic or approved content only. Studio does not
  sanitize uploaded or pasted content...") to `base.html`, `knowledge_workspace.html`, and
  `step2_upstream.html`.
- **Studio regression proof:** `tests/test_audit_persistence.py` asserts the exact notice text.
- **KS remediation shipped:** [KS #39](https://github.com/santosh-sh/EdgeForgeKnowledgeServer/pull/39)
  added the standalone `ingest_document` point-of-use notice to MCP tool metadata and operator
  guidance, with in-process and real-stdio `tools/list` regressions. It did not add sanitization or
  change ingest behavior. The historical no-notice observation above remains dated to the audit pins.
- **Invalidates:** —
- **Tracker mapping:** the Studio portion is `sec-studio-web-baseline`; the KS row is
  `sec-ks-ingest-data-notice`, now reconciled to **done** with the 2026-10-06
  snapshot and regenerated views. This closes Engine #315's status drift, not
  the remaining M2 or public-release gates.

---

## 3. P2 — hardening and coherence

| ID | Repo | Finding | Exposure | Sev | Invalidates |
|---|---|---|---|---|---|
| P2-1 | Studio + generated | **RESOLVED by Studio #289/#292 and generated-app security posture Slice 4.** Studio and generated CRUD/passthrough/Kafka responses carry `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a `frame-ancestors` CSP. Generated runtime proof covers all three archetypes and the dormant-security compatibility case with exactly one value per header. HSTS remains at the TLS-terminating proxy; generated-app rate limiting remains explicitly gateway-owned under Option A rather than app-local. | RESOLVED + DELEGATED | Med | — |
| P2-2 | Engine | **RESOLVED by generated-app security posture Slice 2.** Pageable CRUD controllers reject page sizes above `200` and database offsets above `50_000` with HTTP 400 before calling the service. Requests exactly at either bound retain existing behavior. | RESOLVED | Med | — |
| P2-3 | Engine | **RESOLVED by generated-app security posture Slice 3 plus its reader-first closure.** Passthrough inbound DTOs enforce representable canonical required and Unicode-code-point `maxLength` metadata with sanitized HTTP 400 responses before transform, routing, or downstream invocation. Required-nullable OpenAPI 3.0/3.1 request properties fail closed. Supported nested upstream-request local references and `allOf` constraints use the shared dialect-aware resolver; arrays, field-level polymorphism, deeper object graphs, boolean/malformed schemas, and missing required property definitions fail before generation when effectively required upstream. Optional request failures become contextual diagnostics, while upstream responses and downstream contracts retain approved-base fields and emit compatibility diagnostics without changing generated DTOs. | RESOLVED | Med | — |
| P2-4 | Engine | **RESOLVED by generated-app security posture Slice 1.** Kafka exposes health only by default; metrics/Prometheus require explicit environment opt-in and the documented non-bypassable authenticated-gateway boundary. | RESOLVED | Med | — |
| P2-5 | Suite | Supply chain: no generated-Maven CVE scanning, no image scanning/signing/provenance, mutable action and image tags, Spring Boot baseline ~21 months old | LATENT | Med | "green gates" framing in handover evidence |
| P2-6a | Engine | **RESOLVED by Engine PR #281.** An earlier revision said entity-expansion protection was *inherited* from the platform XML library. **Measured false:** on CPython 3.11.15 with expat **2.7.4**, stdlib `ElementTree` expanded the classic payload. PR #281 now rejects DTDs and enforces per-document plus aggregate resource bounds across contract-loader and generation-time XSD/WSDL reads. KS parser-resource residuals remain separate under P2-8. | LIVE | Med | "mitigated on the modern expat" |
| P2-6 | KS | Retention: soft delete retains indexed content; **standalone** KS lacks project-level/bulk purge and a clear retention + encryption-at-rest policy. *(Corrected: individual hard purge exists, and Studio-managed KS is cleaned up — Studio removes the per-session workspace and store on explicit deletion and retention sweep.)* | LATENT + DELEGATED | Med | — |
| P2-7 | KS | Cross-project evidence lookup can override caller project scope from a stored payload value — a second cross-project path | LATENT | Med | "one explicit cross-project read" |
| P2-8 | KS | Parser resource bounds incomplete — archive limits trust declared metadata; no CPU/wall-clock bound; regex-heavy parsers over supplied input unaudited | LATENT | Med | — |
| P2-9 | Suite | **Resource-exhaustion review is fragmented.** Generated CRUD pagination is bounded by Engine Slice 2, but KS parser bounds plus remaining request-rate and execution-time posture still need one coherent cross-repo pass rather than isolated patches. | LATENT | Med | — |
| P2-10 | Studio | Session identifier used unvalidated as a filesystem path segment; safe only while the signing secret is confidential (P0-2) | LATENT | Med | — |
| P2-11 | Suite | `SECURITY.md` ships an unfilled contact placeholder — no channel exists to report a vulnerability | DELEGATED | Low-Med | the existence of a disclosure process |
| P2-12 | Suite | Dependabot alerts disabled on all three repos (available and free for private repos) | LATENT | Low-Med | — |
| P2-13 | Suite | **Stale AI documentation.** References to "optional AI is OFF by default until KS-B5 lands" conflated the implemented, switchable deterministic KA experience with a nonexistent provider-backed capability. Corrected to: **no LLM/provider integration or provider enable flag exists anywhere in the suite**; a model-backed MCP client would create a **separate adopter-controlled data boundary**, and the sanitization gap applies there | RESOLVED (doc) — Engine PR #286 | Med | "optional AI off by default until KS-B5" |

**Active M2 assessment note (2026-09-13):** the
[per-application Maven assessment lane](handover-evidence/generated-maven-assessment.md)
adds resolved CycloneDX SBOMs, checked scanner extraction, live advisory reports,
and pending findings for a bounded generated-app matrix. This supersedes the
"no generated-Maven CVE scanning" portion of the historical P2-5 description,
not its open supply-chain status. The
[proposed completion record](v5-release-readiness.md#recommended-narrow-m2-completion-contract)
enumerates the remaining coverage, disposition and provenance boundaries.
M2 is **not complete**; no tracker or historical correction log is changed by
this slice.

**Historical proposed v5 completion boundary (2026-09-24):** the
[M2/release-readiness record](v5-release-readiness.md) distinguishes selected
source-and-tag provenance from later cryptographic signing/attestation maturity;
it does not waive image assessment or any open finding. Its coverage and
disposition rules are recommendations until adopted. The existing KS audit job
is not a required main-protection check (the currently required contexts are
`KS test suite` and `gitleaks secret scan`); requiring that existing context is
a separate KS-owned admin follow-up. No new scanner is prescribed here.

**Current correction (2026-10-06):** KS main protection now requires
`Blocking dependency audit` alongside the two contexts above; the setting was
read directly during this reconciliation. Engine #316/#324, Studio #303–#310
and KS #42/#43 delivered later dependency/image/proof work, with open dispositions
and exclusions preserved. The [adopted phase plan](external-review-backlog.md)
supersedes the older scheduling statements, not their dated observations. M2
and final acceptance remain incomplete; no additional KS audit tool is needed.

### 3.1 Tracker mapping — as shipped

**Created (9 rows, all under wave "Security remediation (2026-07 suite review)"):**
`sec-studio-session-path-containment` · `sec-studio-container-defaults` · `sec-studio-stored-xss`
(the three P0s, **status `done`**) · `sec-ks-runtime-hardening` (**done** via KS #37 and Studio
#282/#283) ·
`sec-engine-ddl-trust-boundary` · `sec-studio-web-baseline` (P1-3/P1-7 plus Studio P1-8) ·
`sec-ks-ingest-data-notice` (remaining KS P1-8) ·
`sec-suite-evidence-repair` (P1-6) · `genapp-handoff-residual` (the three remaining handoff outcomes).

**`sequence_rank` is deliberately absent on all nine.** The field encodes the roadmap guardrail
`M1 → M5a → M2/M6 → M3 → M4 → M5b`; security remediation is not a stage within it, and borrowing M1's
rank would misstate both. Ordering comes from `priority` (`now`/`next`/`later`) instead. For the same
reason these rows carry **no `design_status`** — they are findings with a remediation, not approved
designs.

**Updated existing rows:**

| Finding | Tracker row | Current treatment |
|---|---|---|
| P1-2 design-time parsers | `sec-defusedxml` | **done** — Engine PR #281 closed the design-time parser gap; M1 is complete |
| P1-3 dependency triage + P2-5 supply chain | `M2-suite-vulnerability-assessment` | **in-progress** — Studio's dependency gate is blocking (#284–#286); Engine's generated-Maven assessment is delivered with open findings. The [proposed completion record](v5-release-readiness.md#recommended-narrow-m2-completion-contract) owns the full remaining-work list; cryptographic signing/attestation remains later maturity for source/tag-only distribution. |
| P1-6 evidence repair + continuous verification | `M3-change-aware-verification-pack` | execution vehicle for `sec-suite-evidence-repair`; register/select rather than reimplement |
| P1-5 generated-app auth posture | `gate-genapp-auth-default` | precise gateway-delegation versus generated authorization decision |

**Published and discoverable:** this canonical backlog is linked from both
`docs/README.md` and `docs/enterprise-readiness-roadmap.md`. The generated-app standards index remains
the home for generated-app design contracts; this suite-level remediation backlog belongs at the docs
front door and in the enterprise roadmap.

---

## 4. Cross-cutting: evidence integrity

Four shipped controls **pass while the property they assert does not hold**. Two are **evidence-source**
failures (the check draws evidence from the side it guards); two are **evidence-scope** failures (the
check covers a subset that excludes the failing case):

| Control | Failure |
|---|---|
| Studio → Engine path confinement | **Source** — the Engine's allowed root is derived from the untrusted path it exists to constrain (P0-1) |
| Cross-repo isolation negatives | **Source** — invoke the Engine *with the correct root supplied*; never test whether Studio supplies it (P1-6) |
| KS "no network egress" claim | **Historical scope failure** — the documented method grepped first-party code only; KS PR #37 closes the dependency-default defect, while P1-6 still owes continuous cross-repo evidence |
| KS path-leak proof | **Historical scope failure** — it inspected successful results from three of sixteen tools; KS PR #37 adds rejection-path coverage, while P1-6 still owes the refreshed suite proof |

**Standing rule to adopt:** every security check must state *what evidence it consumes* and *which side
produced it*. A check must not source evidence from the side it guards, and its scope must include the
failure mode it claims to exclude. Add to the review checklist.

---

## 5. Confirmed sound — protect from regression

Verified by adversarial probing, not assumed:

- **Engine OpenAPI fetch policy** — scheme allowlist, DNS-pinned connections defeating rebinding,
  metadata/private-address denial, redirect revalidation, size cap, timeout, fully tested.
  **Reference implementation for P1-3.**
- **Studio → Engine subprocess invocation** — argument-list execution, no shell, quoted interpolation
  with the injection risk named in-comment, timeout enforced.
- **SQL — runtime application DML is parameterized** across Studio, KS, and generated apps; KS
  full-text queries normalized (survived hostile probing). Operator-supplied staging **DDL** remains
  executable input, but Engine now enforces the P1-4 fail-closed statement/table boundary before
  carrying the accepted decoded SQL text into generation unchanged.
- **Studio session identity and project ownership** — signed server-minted identifiers, principal-scoped
  catalog queries, cross-principal project access rejected. *(Sound layer; P0-1 is a different layer.)*
- **Shared-mode CSRF** — fail-closed; resisted three bypass attempts.
- **KS ingest ordering and path containment** — resolve-then-contain guard (symlink-safe), extension
  controls, and safety checks that run **before** any parse. **Qualified:** archive and parser
  *resource* bounds remain incomplete — declared-metadata trust, and no CPU/wall-clock bound — tracked
  as **P2-8**. Only the ordering and containment properties are sound.
- **Generated-app server-side validation** (CRUD archetype) and **generated README security guidance**.
- **Secret hygiene** — no committed credentials; secret scanning gates every PR.
- **Design-time / runtime boundary** — no generated-app runtime dependency on Engine, Studio, or KS.
- **No LLM/provider integration or provider enable flag exists anywhere in the suite.** Deterministic
  KA remains an implemented, switchable authoring experience. MCP becomes a data
  boundary **only if** an adopter connects KS to a model-backed host — an adopter-controlled,
  conditional boundary, not current egress.

---

## 6. Handling and disclosure

- Internal remediation artifact, private repository. **Exploit mechanics excluded by design.**
- **Disclosure is not to be delayed categorically.** The obligations, in order:
  1. **Stop hosting, adopter handover, and any new acceptance baseline** for the affected baseline until
     the P0 items land and the adversarial isolation proof is rerun.
  2. **If any party has already received the affected baseline, coordinate notification** with the
     maintainer, security owner, and counsel — do not defer on the reasoning that a fix is coming.
  3. **Never continue asserting a control this review invalidated.** Every claim in an *Invalidates*
     field must be corrected or withdrawn at the time the finding is accepted, not when it is fixed.
  4. Where no party holds the affected baseline, the adopter-facing summary is best written **after**
     P0 remediation, framed as *self-assessment conducted, findings remediated, residual accepted risks
     are X/Y/Z* — found-and-fixed evidences a mature posture. This is a sequencing preference, **not**
     a licence to withhold.
- **Git history is permanent** — anything landed persists through clones, forks, and handover.
- **Cheap now, independent of the above:** enable **Dependabot alerts** on all three repos (P2-12) and
  fill the **`SECURITY.md`** contact (P2-11).

## 7. Out of scope

- **TestBench** — local development tool; hardening tracked separately, excluded from the suite
  enterprise-readiness verdict and this backlog.
- **Penetration testing** — this was a source and configuration audit. Confirmed findings were verified
  at source and several exercised against a locally-run instance; it is **not** a substitute for an
  independent penetration test before production exposure.


---

## 8. Reconciled execution order (2026-07-27)

Agreed across the suite thread and Codex after three reconciliation passes, covering the
security backlog, the enterprise roadmap, and the generated-app handoff track. **Follow this
order rather than picking by whichever item surfaced most recently** — several pairs below are
unsafe to run concurrently, not merely out of sequence.

### Unsafe-to-parallelise pairs (verified)

| Pair | Why | Rule |
|---|---|---|
| Tracker refresh ↔ any PR carrying tracker edits | `HOWTO-update.md` requires the JSON to stay the single source with **both** views regenerated together | One editor at a time. *(Cleared correctly: PR #281's tracker update landed first; PR #282 then rebased on it and regenerated both tracker views.)* |
| M5a ↔ event-delivery `internal_schema` | **Both** designs independently introduce prior-baseline carry-forward; the baseline is currently derived from current metadata only | **M5a lands one generic foundation; event delivery consumes it.** Do not implement twice |
| OpenAPI O0a/O0b ↔ M4 B2b ↔ event Slices 2a/2b | All restructure or instrument `java_emitter.py` / ServiceBase emission | **One active structural-emitter PR at a time**, then rebase the next |
| Security-doc corrections ↔ PR #281 | #281 already edits `security-boundary-map.md`; a parallel consolidated correction is textually mergeable but semantically unsafe | Corrections follow #281 |

### The four artifact/plan models — roles, not a redesign

A **narrow** design amendment is required before O0a/O0b or M4 B2b. Roles:

- **`GeneratedCrudApiModel`** — plan-time API semantics.
- **`_EntityJavaArtifactPlan`** — plan-time artifact/path decisions; **references** the API model
  rather than duplicating operation derivation.
- **`schema_baseline.generated_source_files`** — a **persisted projection** of the plan, not
  another source of truth.
- **M4 registry** — **write-time** observation across all emitters, reconciled against the plans.

**Do not build the registry first and derive the plans from it** — a write-time registry cannot
drive dry-run or pre-emission planning. M4's "no artifact plan exists" statements are now stale
and need narrowing before B2a/B2b.

### Order

**2026-10-06 release reconciliation:** the maintainer adopted the
[bounded v5/public-launch plan](external-review-backlog.md#combined-execution-order)
and its [parallel work rules](external-review-backlog.md#parallel-work-and-merge-order).
It adds XR-1's fail-fast correctness slice before the planned public tag, folds
claims into release preparation and keeps M3/M4/M5b post-v5. The programme
dependencies below remain; tracker rank is not permission to expand release scope.

1. **M1 parser hardening — DONE via Engine #281.** Contract loaders and generation-time resource reads
   now reject DTDs with per-document and aggregate size/depth bounds. **M1 is complete.**
2. **Reconcile tracker/current docs after cross-repo merges — DONE in the rev-10 decision sync**
   through Engine #288, Studio #285, and KS #37; snapshot SHAs remain one merge stale by
   construction.
3. **P1 tranche, parallel** — P1-1, P1-3, P1-4, P1-7, and the Studio portion of P1-8 are complete.
   The standalone KS ingest notice for P1-8 shipped in KS #39. Keep A11y-01 open:
   the Studio #299 and Engine #313 amendments are merged and the revised policy is active.
   A11y-01 alone does not block source publication, internal baselines or tags,
   public releases, or promoted demos; it remains the Studio-owned
   [open known limitation](https://github.com/santosh-sh/EdgeForgeStudio/issues/302), and all four
   native cases remain required for completion. While Studio is private, any otherwise authorized
   public release or promoted demo needs an audience-accessible notice of the limitation's impact
   and reproduction; disclosure does not require A11y-01 completion. This exception does not alter
   any other release, security, correctness, or acceptance gate. Treat generated-app security posture
   Slices 1–4 and the
   passthrough reader-first closure as complete:
   they deliver the Option A boundary, profile matrix, Kafka health-only default, CRUD pagination
   bounds, request validation/diagnostics boundary, and universal response headers (P1-5);
   continue M2 under the [proposed bounded contract](v5-release-readiness.md#recommended-narrow-m2-completion-contract).
   P1-6
   remains the separate continuous cross-repo evidence lane.
4. **M5a is complete under the approved sequence:** V2-E, V2-S, paired-branch V2-X, the coordinated
   merge,
   and post-merge V2-X are complete. M5a-S1 contract recognition and fail-closed validation are
   delivered; M5a-S2 delivers the package Batch-metadata singleton and bounded identity/restart
   layer; M5a-S3 delivers the per-handoff `internal_schema` idempotency foundation before event
   delivery consumes it; and M5a-S4 makes opted-in run-identity harness failures blocking while
   retaining advisory legacy findings. The four-slice M5a implementation is complete.
5. **Apply the approved source-release boundary, not exhaustive M2 closure.**
   Keep existing findings/coverage gaps OPEN under the owner/trigger above.
   Retain required audits, checks and final acceptance. New-repository
   [cutover ordering](v5-release-readiness.md#replacement-cutover-and-release-sequence)
   replaces E/P/R/M. Complete M6 before hosting; protect previews and retain
   maintainer publication authorization as a public-exposure gate.
6. **Build M3 in guardrail order** — **consuming** the Engine #280 standalone-independence checks
   rather than reimplementing them. Studio PR #280 already completed the UX flip against the recorded
   manual gates; M3 is no longer a prerequisite for that historical event. Before VS0/VS1/V-ACT, amend
   their removed rollout-flag assumptions and retain the checklist as default-on regression/evidence.
7. **Apply the narrow model amendment**, then build M4.
8. **M5b.**
9. **Then** groupId design → OpenAPI O0a→O0b→O1→O2 → generated contract tests → event delivery.
   Per-app SBOM sits under **M2**.

**Parallel-safe throughout:** S1 domain packs, S9 documentation cleanup.

**Deliberately blocked:** event delivery remains pending §13.1. M5a's §13.2 prerequisite and S1
contract-validation, M5a-S2 Batch identity/restart, M5a-S3 staging idempotency, and M5a-S4 blocking
harness slices are complete. M3 owns later registration of the reserved M5a scenarios.
The former PR-24↔M3 timing decision is closed by Studio PR #280 and replaced by the narrow M3
post-flip amendment described in step 6.

### Generated-app handoff track — where it lands

Seven of ten outcomes are **done** (PR #279 + #280). Three remain, and **none is a new track**:
project-owned Maven `groupId` (still `com.appbuilder` for every app) → step 9 · app-local
executable contract tests → **M3** · per-app SBOM → **M2** *(G4's representative Maven evidence
is **not** a per-app SBOM — different artifact, different consumer)*.

**2026-10-06 reconciliation:** generated context-start tests and the per-app
Maven SBOM/assessment command now exist; do not repeat the historical claim that
no `src/test/java` is emitted. Useful app-local behavior/contract tests remain
open, refined by [XR-6](external-review-backlog.md#xr-6-generated-app-local-tests)
under the existing M3/handoff requirement. M2 verifies delivery and closes only
demonstrated SBOM gaps; it does not build another assessment tool. Broader
generated-contract-test work retains step 9 prerequisites. This is not a claim
that all handoff outcomes, M2 or M3 are complete.
