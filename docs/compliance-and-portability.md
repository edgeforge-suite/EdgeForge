# Compliance & Portability Checklist

> **Import-gate G7.** A reviewer's answer-sheet: the questions an import /
> compliance review asks, each **pre-answered and linked to real evidence** —
> with honest caveats where something is pending or nuanced. Claims about code
> were **verified against the source** (the method is stated where it matters),
> not asserted.
>
> **Last updated:** 2026-06-10. This checklist **links** the evidence pack (G3
> secret scan, G4 SBOM/licenses) as the single source of truth; it does not
> re-derive it. The G10 handover-evidence index will link this doc (forward
> reference; the index is a separate item).

## At a glance

| # | Question | Short answer | Evidence |
|---|---|---|---|
| 1 | License posture | Apache-2.0 selected for Engine; third-party terms remain separate; maintainer publication authorization pending | [§1](#1-license-posture) |
| 2 | Secrets / real data | No secrets; named scan enforced in CI; all data synthetic | [§2](#2-secrets-and-real-data) |
| 3 | Telemetry / phone-home | **None** (verified); one **user-directed** spec fetch disclosed | [§3](#3-telemetry-and-phone-home) |
| 4 | Generated-app standalone | No runtime dependency on the suite; one credential caveat disclosed | [§4](#4-generated-app-standalone-and-no-runtime-coupling) |
| 5 | Data-handling posture | Deterministic; **no LLM or provider integration exists today**; no PII in Evidence Trail | [§5](#5-data-handling-posture) |
| 6 | Dependency hygiene | Pinned + reproducible SBOM | [§6](#6-dependency-hygiene) |
| 7 | Portability | Python 3.11+ + standard Spring Boot/Maven; air-gap-friendly | [§7](#7-portability) |

---

## 1. License posture

**Third-party dependencies:** all six **directly declared** Python dependencies
are permissive (Apache-2.0 / BSD / MIT) — no copyleft. Inventory + machine-readable
SBOM:
[`dependency-licenses.md`](handover-evidence/dependency-licenses.md) ·
[`sbom.cdx.json`](handover-evidence/sbom.cdx.json) ·
[`dependencies.md`](handover-evidence/dependencies.md) (G4).

**EdgeForge's own license:** Apache-2.0, short NOTICE and DCO 1.1 without a CLA
are selected by the maintainer under [scope-reset revision 3](v5-release-readiness.md).
Maintainer publication authorization remains pending before
public exposure; adopters separately review their own usage/operating policies.
Historical dependency tables are dated evidence, not a new all-permissive claim.
The current Python inventory retains `certifi` MPL-2.0 for review.

> **Caveat (carried from G4):** the inventory covers the *declared* surface. A
> full **transitive** license audit is a deeper artifact and **should not be
> skipped** — at the G4 snapshot the tool reports at least one *transitive*
> package's license as `UNKNOWN`.

## 2. Secrets and real data

**No secrets in the repository, enforced on every change.** A named secret
scanner (**gitleaks**, pinned) runs in CI on every PR and push to `main`; the
committed tree scans clean.

**All fixtures/examples are synthetic** — no real customer data or PII is
committed (synthetic-only-data policy).

Evidence: [`secret-and-data-scan.md`](handover-evidence/secret-and-data-scan.md)
and the [`secret-scan` workflow](../.github/workflows/secret-scan.yml) (G3).

## 3. Telemetry and phone-home

**Verified result: EdgeForge has no telemetry, analytics, or phone-home.**

**Verification method (reproducible):** grep of the Engine source for network and
telemetry libraries —
`(requests|httpx|aiohttp|urllib|http.client|socket|smtplib|ftplib)` imports and
`sentry|posthog|segment|mixpanel|amplitude|analytics|telemetry` —
across `appbuilder/**/*.py`, and the same over `templates/**`. The **only**
network capability in the Engine is the policy-bound OpenAPI fetcher described
below; templates contain no telemetry/analytics SDKs.

**The one outbound capability, disclosed honestly — it is user-directed, not
telemetry:**

- [`appbuilder/ingestion/openapi_fetcher.py`](../appbuilder/ingestion/openapi_fetcher.py)
  — `fetch_openapi_spec(url)` fetches an **OpenAPI/Swagger spec the user/manifest
  points it at** under one Engine-wide SSRF policy. There is **no fixed endpoint**
  and **no automatic/background call** — the URL always comes from the user, so
  it is categorically different from telemetry. The fetcher accepts HTTP(S)
  only, resolves and classifies every target, pins the connection to the vetted
  numeric addresses while retaining the original HTTP `Host` and TLS
  SNI/certificate checks, disables ambient proxies, revalidates bounded redirects,
  and caps the response at 5 MiB. An exact host in
  `EDGEFORGE_OPENAPI_FETCH_ALLOWED_HOSTS` may resolve to RFC1918/IPv6-ULA private
  service addresses; cloud metadata, loopback, link-local, reserved, multicast,
  and unspecified destinations remain non-bypassable denials. It is reached from
  two user/manifest-directed entry points:
  - the CLI `assess --swagger <URL>` command (the user supplies the URL); and
  - **during `generate`** — when a manifest **upstream interface declares a remote
    `spec_url`**, the translation step fetches it to ingest the contract (see
    [`appbuilder/metadata/translation.py`](../appbuilder/metadata/translation.py)
    around the `interface.spec_url` fetch). If interfaces use a **local `spec`
    file** instead of `spec_url`, `generate` makes **no** network call. (A remote
    `spec_url` on a *downstream* interface is rejected, not fetched.)
  - An SSRF policy rejection fails generation. DNS or transport unavailability
    is treated separately: a CRUD interface with reviewed samples retains the
    existing sample-ingestion fallback and records the fetch failure.

**Local MCP server = no network egress.**
[`appbuilder/mcp_server.py`](../appbuilder/mcp_server.py) is a **local stdio**
server (`mcp.run()` over stdio — no host/port, no HTTP listener).

**Generated apps = standalone, no phone-home.** A generated app makes only the
outbound calls its **manifest declares** (e.g. a downstream REST target or a
Kafka broker for the router/passthrough archetypes), all **env-configured**;
there is no call back to EdgeForge or to any vendor analytics.

## 4. Generated-app standalone and no runtime coupling

**Generated apps have no runtime dependency on EdgeForge, Studio, the Knowledge
Server/Assist (KS/KA), MCP, or TestBench.** Each is an independently buildable
standard Spring Boot app.

How it's enforced / proven:

- **Invariant:** [`CONTRIBUTING.md`](../CONTRIBUTING.md) (and
  [`suite-architecture.md`](suite-architecture.md)) make "generated apps are
  standalone — no runtime dependency on EdgeForge/Studio/KS/KA/MCP" a
  non-negotiable rule.
- **CI proof:** the [Generated App Compile Check](../.github/workflows/generated-app-compile.yml)
  builds a representative generated app (`mvn clean compile`) with no suite on the
  classpath.
- **Runtime proof:** the [quickstart](quickstart.md) regenerates and runs the
  sample app end to end; each generated app also ships its own `agent-context.md`
  + `README.md` describing its standalone operation.

> **Generated-app credential posture (A6 resolved):** generated apps
> externalize datasource credentials via Spring env-var injection
> (`${SPRING_DATASOURCE_URL/USERNAME/PASSWORD}`). The enterprise PostgreSQL target
> profiles now require `SPRING_DATASOURCE_USERNAME` and
> `SPRING_DATASOURCE_PASSWORD` with **no** generated `postgres` fallback, so a
> misconfigured deployment fails fast. The dev/H2 profile continues to use `sa`
> with an empty password for in-memory local runs only.

## 5. Data-handling posture

- **No LLM or provider integration exists in the suite today** — there is no AI
  capability to enable. KA/KS run deterministically
  ([`suite-architecture.md`](suite-architecture.md)). The KS-B5 data-handling
  design (PII / sanitization / redaction) gates any future provider layer — a
  separate KS thread, not resolved here. If an adopter connects KS to a
  model-backed MCP host, that is a separate adopter-controlled data boundary and
  the sanitization gap applies there.
- **Deterministic Engine, no AI inference in generation.** The same manifest
  produces the same app (byte-identical regeneration); generation does no AI
  inference, name inference, or silent auto-apply (a core invariant in
  [`CONTRIBUTING.md`](../CONTRIBUTING.md)).
- **Evidence Trail carries no identity-role / PII evidence** — it preserves the
  v1.1 shape and adds no new evidence types (see the edge-contract Evidence Trail
  scope).

## 6. Dependency hygiene

- **Pinned dependencies:** [`requirements.txt`](../requirements.txt) and
  [`pyproject.toml`](../pyproject.toml) align their exact direct versions. The
  selected Python 3.11 Linux reference closure is in
  [`requirements-lock.txt`](../requirements-lock.txt); other supported platforms
  may resolve different conditional transitives.
- **Python SBOM, license inventory and audit:** `make sbom` runs the pinned,
  isolated [Python-only evidence command](handover-evidence/python-dependency-policy.md)
  against the reference lock. Inventories are checked for complete coverage;
  actual scan timestamps and live advisory results are not byte-stable. Generated
  Maven evidence remains separate (G4/M2).

## 7. Portability

- **Engine:** Python **3.11+**; standard library + the small permissive
  dependency set (§1). No proprietary SaaS or vendor runtime is required to run
  the Engine.
- **Generated apps:** standard **Spring Boot / Maven** projects with their own
  `Dockerfile` — buildable and runnable in an ordinary enterprise JVM environment;
  no proprietary SaaS dependency.
- **Air-gapped / restricted networks:** the Engine performs no background network
  I/O. The only outbound call is the **user/manifest-directed** OpenAPI spec fetch
  (§3), triggered either by `assess <URL>` **or by `generate` when a manifest
  upstream interface declares a remote `spec_url`**. For an air-gapped run, point
  interfaces at **local `spec` files** (not `spec_url`) and skip `assess` — then
  `generate` and the local MCP server need no network. Dependency install (pip /
  Maven) needs registry access or an internal mirror (noted in the
  [quickstart](quickstart.md)). A generated app's own runtime calls only the
  downstream targets its manifest declares.

---

## Caveats summary (not buried)

- **Maintainer publication authority pending** — G1; Apache-2.0 selected (§1).
- **Transitive license UNKNOWN** — ≥1 transitive dep is UNKNOWN; a transitive
  audit should not be skipped (§1).
- **Generated-app datasource credentials** — enterprise PostgreSQL profiles are
  env-var-required / fail-fast with no `postgres` fallback; dev/H2 remains local-only (§4).
- **Optional AI** — no LLM or provider integration exists today; KS-B5
  PII/sanitization design gates any future provider layer (§5).
