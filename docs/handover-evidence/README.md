# Handover Evidence — Start here if you're evaluating the import

> **Import-gate G10 — the front-door for a compliance / security reviewer.** This
> is the **one place** to land when you're deciding whether to import EdgeForge.
> Each import-review concern below is mapped to a **linked, authoritative
> artifact** plus an **honest one-line status**. This index **links** evidence —
> it does **not** restate or re-derive it, so there is no drift: the linked doc is
> always the source of truth.
>
> **Honest by design.** Where an underlying doc says *pending / adopter-decides /
> parked / skeleton*, this index says the **same** — nothing is upgraded to
> "done." The consolidated open / adopter-decides / post-import list is
> [below](#open--adopter-decides--post-import-nothing-hidden).
>
> **Last updated:** 2026-11-02 for the bounded joserfc reference-lock correction; the Python 3.11 floor, October 20 image assessment and decision packet remain unchanged. Master tracker:
> [`enterprise-readiness-roadmap.md`](../enterprise-readiness-roadmap.md).
> Orientation: [`suite-architecture.md`](../suite-architecture.md). Run it:
> [`quickstart.md`](../quickstart.md).

## What this pack is

For evidence maintenance, use the [maintainer tool map](generated-image-maintainer-tools.md).
It separates ordinary product use and contributions from release-evidence work;
none of these records by itself establishes release acceptance.

For remaining Engine M2 decisions, use the [closeout packet](engine-m2-closeout-decisions.md)
and its hash-bound [identity index](engine-m2-dispositions.json). These preserve
historical findings and identify OPEN owner actions; they do not accept risk or
declare M2 complete. #334 is merged; #333 is closed as superseded.

The subsequent [clean-plugin Plexus overlay](clean-plugin-plexus-2026-10-24/README.md)
records the owning-realm 4.0.3 correction, four clean/verify executions (28 tests:
two Engine-emitted, 26 proof-supplied), and four findings-bearing builder-stage
assessments. It preserves the October 20 OPEN ledger and distinguishes executed
artifact proof from configuration coverage. It is not M2 or release clearance.

This pack supports contributors, independent evaluators and enterprise adopters.
Named-tool scans, a machine-readable SBOM, a compliance answer-sheet, a security
boundary map and a capability matrix link claims to their dated evidence.
The open items below distinguish project-maintainer work from self-managed
adoption responsibilities. They do not promise an organization-specific handoff,
implementation service or transfer of project development.

## Concern → evidence

| Import-review concern | Evidence (authoritative — click through) | Honest status |
|---|---|---|
| **Generated Docker build/runtime assessment** | [Assessment contract](generated-image-assessment.md) · [Noble correction and current findings](generated-images/2026-10-20-noble/README.md) · [Current storage/verification](generated-images/2026-10-20-noble-storage.md) · [Historical October 17 record](generated-images/2026-10-17/README.md) | Reviewed index pins and scoped plugin corrections; 30 cases/60 stages on `linux/amd64`, Java 17/21, three actual production startups and separate compatibility/default/native proof. Historical identities and OPEN residuals remain explicit. No risk acceptance or M2/release clearance. |
| **Fresh Boot 4 generated Maven assessment** | [Current assessment guide](generated-maven-assessment.md) · [2026-10-03 finalized pack](generated-maven/2026-10-03/README.md) · [Runtime and 110 historical finding dispositions](../test-results/boot41-defaults-promotion-2026-10-03.md) | **Complete, findings open.** 30 executions/60 passes/14 validated graphs, 18 findings (11 production/build, seven test-only). No suppression, risk acceptance, migration or release/M2 clearance. Dated earlier evidence remains historical. |
| **License & dependencies** | [`dependencies.md`](dependencies.md) (cover) · [`python-dependency-policy.md`](python-dependency-policy.md) (reference and audit gate) · [`python-current/`](python-current/) (fresh Python SBOM/audit/licenses) · [`pip-audit.md`](pip-audit.md) (historical Python result) · [`generated-app-dependencies.md`](generated-app-dependencies.md) | **Fresh Python correction and blocking audit.** The November2 reference scan covers 76 packages with zero matches after the bounded joserfc 1.7.6 correction; Engine v5 still requires Python 3.11+. September23, October20, October25 and October29 snapshots remain under `python-current/history/`. `certifi` remains flagged for MPL-2.0 review. Historical findings are not erased. Maven, images and overall M2 remain separate. **Apache-2.0 is selected; maintainer publication authority remains pending** (G1). |
| **Secrets & real data** | [`secret-and-data-scan.md`](secret-and-data-scan.md) · [`secret-scan` workflow](../../.github/workflows/secret-scan.yml) (G3) | **Correctly scoped.** Pinned **gitleaks `8.30.1`** runs on every PR + push to `main` and mechanically enforces the configured secret-pattern control; the committed tree scans clean. Synthetic-only committed data is contributor policy checked through human review. No automated PII/real-data detector is claimed. `secret-and-data-scan.md` is the authoritative evidence and scope statement. |
| **Compliance & portability** | [`compliance-and-portability.md`](../compliance-and-portability.md) (G7) | **Answered + verified.** No telemetry / phone-home; the **only** outbound call is a **user/manifest-directed** OpenAPI fetch; generated apps are standalone; air-gap guidance given. Transitive dependency disposition remains separate; Apache-2.0 is selected, while maintainer publication authority is pending. |
| **Security boundaries & attack surface** | [`security-boundary-map.md`](../security-boundary-map.md) (G8) | **Mapped + verified.** Design-time vs runtime boundary (toolchain not in the production blast radius). **Inbound XML payload validators and the first SOAP/SAAJ envelope parse are verified-hardened**; SOAP envelopes are byte-bounded and preserve transport headers. Honest residuals remain in [G8 §5](../security-boundary-map.md#5-honest-open-items--recommendations). |
| **Data governance / data-protection** | [`../data-governance-posture.md`](../data-governance-posture.md) | **Documented (data-steward / DPO view).** Design-time-vs-runtime data map; classification (repo synthetic-only by contributor policy and human review **vs** operator-supplied inputs = operator-governed); AI / data-egress boundary (no LLM or provider integration exists in the suite today; KS-B5 gates any future provider layer); multi-session isolation; regeneration data-integrity; secrets; audit; retention. Honest caveats carried (no automated PII detector, operator-input governance, KS-B5). |
| **Edge-contract capability honesty** | [`edge-contract-handoff-readiness-matrix.md`](../edgecontracts/edge-contract-handoff-readiness-matrix.md) (C4) | **Truthful per-family status**, each backed by re-runnable in-repo evidence. REST / fixed-width / CSV / XML-XSD: `implemented · proven`. **SOAP is _bounded_** (`read_by_id` / `invoke_by_id` only; broader ops `design-only`). **Staging handoffs** generate + compile but are **not production-hardened**. Future families `parked`. |
| **Governance files** | [`CONTRIBUTING.md`](../../CONTRIBUTING.md) (authoritative rules) · [`SECURITY.md`](../../SECURITY.md) · [`.github/CODEOWNERS`](../../.github/CODEOWNERS) · [`pull_request_template.md`](../../.github/pull_request_template.md) (G2) | **Present.** CONTRIBUTING is the live authoritative rules home. **CODEOWNERS is a _template_** (every line commented, `@<org>/<team>` placeholders — adopter sets owners on import); **SECURITY.md** names the accountable maintainer and selected private reporting routes, whose activation/verification remains pending. No response SLA is promised; adopter-internal support is separate. |
| **CI evidence** | [`secret-scan.yml`](../../.github/workflows/secret-scan.yml) · [`appbuilder-tests.yml`](../../.github/workflows/appbuilder-tests.yml) · [`generated-app-compile.yml`](../../.github/workflows/generated-app-compile.yml) | **Required checks.** Secret scan, Engine pytest plus the Python reference dependency audit, and generated-app `mvn` compile (with **no suite on the classpath**) run in applicable CI. A live audit failure blocks the Python test job. |
| **Enterprise-readiness acceptance (end-to-end)** | [`l5-acceptance-run.md`](l5-acceptance-run.md) | **GREEN (hermetic).** Cross-repo L5 — generate→compile→run a **non-root container vs real Postgres**, multi-session isolation, regeneration data-integrity, KS isolation; **all 8 §8 hard-fail checks clear**. SHA-pin engine `b11dd04` / studio `0e58f9e` / ks `11aed44`; **pinned KS, provenance-verified**. Manual / pre-baseline (not a per-PR CI gate). |

## Open / adopter-decides / post-import (nothing hidden)

Every caveat from the underlying docs, carried forward verbatim-in-spirit and
**linked to where it's authoritative**. Tagged with the roadmap's ownership
legend — `[now-ours]` (EdgeForge, now) · `[adopter-decides]` (external gate the
adopter's legal/security owns — *visible and required, not optional*) ·
`[post-import]` (deferred to the in-house pipeline) · `[design-now / wire-later]`.

| Open item | Tag | Where it's authoritative |
|---|---|---|
| **Publication authority** — Apache-2.0/NOTICE/DCO selected; maintainer publication authorization pending before public exposure, not private preparation. | Maintainer | [Source-release policy](../v5-release-readiness.md) · roadmap **G1** |
| **G5 example classification and active-reference cleanup** — pending. PR #291's canonical-fixture shape guard is a completed bounded control, not a repository-wide semantic-neutrality scan. | `[now-ours]` | [Roadmap G5](../enterprise-readiness-roadmap.md#parallel-import-gate-lane) · [execution status](../enterprise-readiness-roadmap.md#appendix--execution-checklist-ordered) |
| **Dependency findings disposition** — the prior Python `pytest` advisory is historical; the fresh Python reference scan reports zero known advisories. `certifi` MPL-2.0 and generated-app Maven findings still need their separate decisions. | `[now-ours]` / `[post-import]` | [G4 scope note](dependencies.md#scope-read-this) · [Python reference](python-dependency-policy.md) · [historical audit](pip-audit.md) · [generated-app Maven evidence](generated-app-dependencies.md) |
| **A6 — generated-app credential fallback** — resolved in Engine `v4.1.1`: enterprise PostgreSQL profiles require datasource username/password env vars with no `postgres` fallback. | `done` | [G7 §4](../compliance-and-portability.md#4-generated-app-standalone-and-no-runtime-coupling) · [G8 §4](../security-boundary-map.md#4-controls--boundaries) |
| **Generated-app authentication posture** — **no shipped target profile emits in-application authentication or authorization.** P1-5 resolved this as gateway-delegated (Option A) for v5. Slices 1–4 and PR #305's reader-first closure are delivered: all archetypes document the authorization envelope and gateway-owned rate limiting; Kafka actuator exposure defaults to health with a protected metrics/Prometheus opt-in; CRUD pagination is bounded; passthrough request validation covers representable top-level and supported nested metadata while unrepresentable effective required input fails closed; and every generated CRUD, passthrough, and Kafka response carries the four TLS-independent baseline headers exactly once. Plain-HTTP HSTS remains gateway-owned. The internal OAuth2 emitter remains dormant and unsupported. | `done` | [P1-5 design](../generated-app-standards/generated-app-security-posture-design.md) · [G8 §4](../security-boundary-map.md#4-controls--boundaries) |
| **Generated-app gateway deployment** — the Option A posture above is only sound if the adopter deploys an authenticated, TLS-terminating gateway and makes the application port unreachable except through it; the application itself performs no authentication or authorization. This is deployment/operations ownership, distinct from the posture decision above. | `[post-import]` | [P1-5 design §8](../generated-app-standards/generated-app-security-posture-design.md#8-authorization-envelope) |
| **SOAP `/ws` envelope parser hardening** — resolved: the generated named SAAJ factory performs a byte-bounded secure parse before SAAJ, preserves transport MIME headers, and returns deterministic HTTP 400 faults for malicious/oversized envelopes. Deployment ingress and concurrency limits remain adopter-owned defense in depth. | `done` | [G8 §3b / §5](../security-boundary-map.md#5-honest-open-items--recommendations) |
| **Design-time XSD/WSDL parser hardening is resolved:** DTDs are rejected; per-document size/depth and per-load aggregate byte/document bounds apply across includes; generation revalidates bytes before parsing or copying. `defusedxml` was not adopted for the dependency and resource-cap reasons recorded in G8. **OpenAPI-fetch SSRF hardening is resolved:** HTTP(S)-only, vetted-address-pinned connections, no ambient proxies, bounded/revalidated redirects and bodies, and non-bypassable metadata denial. | `parser done`; `SSRF done` | [G8 §3a / §5](../security-boundary-map.md#5-honest-open-items--recommendations) |
| **Operator test console** — resolved: shipped enterprise profiles omit the console and `DemoController`; the legacy-compatible profile retains the local-only console, custom secured profiles require authentication, and demo/live-data endpoints remain **off by default**. | `done` | [G8 §3b / §5](../security-boundary-map.md#5-honest-open-items--recommendations) |
| **Studio / KS SSO + RBAC** — not in this release; design-now / wire-to-IdP-later. (Studio/KS are separate repos.) | `[design-now / wire-later]` (P5 / D2) | roadmap **D2** · [G8 §4](../security-boundary-map.md#4-controls--boundaries) |
| **Optional AI (KA/KS)** — **no LLM or provider integration exists in the suite today**; there is no AI capability to enable. KS-B5 gates any future provider layer. If an adopter connects KS to a model-backed MCP host, that is a separate adopter-controlled data boundary and the sanitization gap applies there. | `[adopter-decides]` / posture-now | [G7 §5](../compliance-and-portability.md#5-data-handling-posture) · roadmap **G9** |
| **SOAP bounded scope + parked future families** — broader SOAP ops, and other future edge-contract families, are `design-only` / `parked` until real demand. | `[post-import]` / planned | [C4 future families](../edgecontracts/edge-contract-handoff-readiness-matrix.md#future-families) · [C4 honest caveats](../edgecontracts/edge-contract-handoff-readiness-matrix.md#honest-caveats) |
| **Full threat model + supply-chain provenance maturity** (signed tags, attestation, branch protection, enterprise scanners) | `[post-import]` | roadmap — Compliance Hardening |

> **Reading the tags:** `[adopter-decides]` items are **real gates, not optional**
> — they're owned by the adopter's legal/security, who decide; EdgeForge only
> prepares the inputs. `[post-import]` items are deliberately deferred to the
> in-house pipeline. `[now-ours]` items are EdgeForge follow-ups tracked in the
> linked docs.

## Reproduce the evidence yourself

- **Python-only SBOM + dependency evidence (G4):** `make sbom` (wraps
  [`scripts/generate-python-dependency-evidence.sh`](../../scripts/generate-python-dependency-evidence.sh))
  refreshes only the Python reference SBOM/license/audit evidence after approval
  for the live advisory query. It does not refresh the lock or Maven evidence.
- **Resolved Python reference lock:** `make lock` re-resolves the Linux reference
  lock; review the resulting diff and rerun Python proof before selecting it.
- **Secret scan (G3):** runs automatically in CI
  ([`secret-scan.yml`](../../.github/workflows/secret-scan.yml)); locally,
  `gitleaks dir . --redact --exit-code 1` with pinned `8.30.1`.
- **Tests / standalone compile:** `make test`; the generated-app compile gate runs
  in CI ([`generated-app-compile.yml`](../../.github/workflows/generated-app-compile.yml)).

## Where to go next

- **Master tracker (status of every gate):**
  [`enterprise-readiness-roadmap.md`](../enterprise-readiness-roadmap.md)
- **Orientation / suite map (START HERE):**
  [`suite-architecture.md`](../suite-architecture.md)
- **Run it in ~10 min:** [`quickstart.md`](../quickstart.md)
- **Full docs index:** [`docs/README.md`](../README.md)
