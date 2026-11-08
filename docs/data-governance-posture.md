# Data-Governance Posture

> **What this is.** The **data-steward / data-protection** read of EdgeForge at
> import — the companion to the G7 [Compliance & Portability Checklist](compliance-and-portability.md)
> and the G8 [Security Boundary Map](security-boundary-map.md). It answers one
> question end-to-end: **what data exists in the suite, where it lives, where it
> can and cannot flow, and what protects it** — for both the design-time toolchain
> and the runtime generated apps. It **consolidates** data-handling facts otherwise
> spread across G7 §5, G8 §4, the regenerate/maintain design, and the MCP /
> shared-mode contracts; it **links** those sources and does not re-derive them.
>
> **Scope & method:** a now-doc for a data steward / DPO; **not** a full DPIA (that
> defers to the adopter, with the adopter's own data). It distinguishes **repository
> policy and controls** (what EdgeForge requires and checks for committed
> contents) from **operator input governance** (what an operator supplies into
> the tools at runtime). Every claim
> was verified against the cited source or the L5 acceptance run; caveats are
> surfaced, not buried.
>
> **Verification status — final.** The orchestrator KS-wiring hardening (#253) is
> merged, and the **hermetic L5 rerun is GREEN** at engine `b11dd04` / studio
> `0e58f9e` / ks `11aed44`, with the Studio→KS leaf launching the **pinned** KS
> (`command_under_ks_repo: true`, repo-match validated — no ambient fallback). The
> full record is the
> [L5 acceptance evidence artifact](handover-evidence/l5-acceptance-run.md) (§4, §7).
>
> **Last updated:** 2026-08-16.

## At a glance

| # | Data-governance question | Short answer | Where |
|---|---|---|---|
| 1 | What data does the suite touch, and where? | **Committed** repo fixtures are synthetic by contributor policy and human review; **operator-supplied** design-time inputs are the operator's to govern; **only the runtime generated apps handle production data** by design. | [§1](#1-data-map--design-time-vs-runtime) |
| 2 | Any PII / real customer data in the **repo**? | The committed-data policy prohibits it and current fixtures are reviewed as synthetic; no automated PII/real-data detector is claimed. Evidence Trail holds design metadata only (no record values / identity-role evidence). Operator inputs are operator-governed. | [§2](#2-data-classification) |
| 3 | Does any data go to an LLM / external service? | **No production / customer data to any LLM.** No LLM or provider integration exists in the suite today; deterministic Engine; only egress is a user-directed spec fetch. | [§3](#3-ai--data-egress-boundary) |
| 4 | How is data isolated in a shared / multi-user deployment? | Per-session server-owned roots, fail-closed when unset; per-session KS DB; cross-session access rejected — **verified at L5 (hermetic; pinned KS)**. | [§4](#4-multi-session-isolation-shared-deployment) |
| 5 | Is data integrity protected when an app is regenerated? | Developer code preserved; **additive-only** migrations (immutable priors); **destructive changes fail closed**; plan-hash-bound apply — verified at L5. | [§5](#5-data-integrity-under-regeneration) |
| 6 | How are credentials / secrets handled? | No secrets in repo (G3); env-var-required datasource credentials at runtime. | [§6](#6-secrets--credentials) |
| 7 | What is auditable / traceable? | Evidence Trail (decision provenance), Change-Plan + plan-hash (regeneration), SHA-pin (acceptance); runtime app logging is the adopter's. | [§7](#7-audit--traceability) |
| 8 | Retention / residency? | No central store; design-time artifacts live on the build host / per-session workspace; runtime residency is the adopter's deployment. | [§8](#8-retention--residency) |

---

## 1. Data map — design-time vs. runtime

This is the spine of the whole posture (the data view of G8 §1). EdgeForge has **two
populations of software** on opposite sides of one boundary:

- **Design-time toolchain** — the **Engine** (`appbuilder`), **Studio**, and the
  **Knowledge Server / Assist (KS/KA)**. These run on a developer / build host and
  **handle no production *traffic***; they process contract definitions (XSD / WSDL
  / OpenAPI / manifests) and sample data an **operator supplies**. Two distinct
  governance scopes apply here and must not be conflated:
  - **Committed repository contents** are required to be **synthetic-only** by
    contributor policy and human review. Pinned gitleaks mechanically checks
    configured secret patterns; no automated PII or real-data detector is claimed
    (G3).
  - **Operator-supplied inputs at runtime** (uploaded contracts, sample files,
    KS-ingested documents) **may contain real or sensitive data**, and EdgeForge
    does **not** enforce that they are synthetic. That data lives in the operator's
    own build host / per-session workspace / KS SQLite; classifying, minimizing,
    retaining, and redacting it is the **operator's responsibility** (§2). EdgeForge
    processes it **locally** — no egress, and no LLM or provider integration
    exists to send it to (§3).
- **Runtime generated apps** — the standalone Spring Boot applications the Engine
  emits. These are the **only** EdgeForge artifacts that run in production,
  terminate real upstream/downstream traffic, and read/write the enterprise
  database. They carry **zero runtime dependency** on the toolchain (a
  non-negotiable suite invariant — G8 §1).

→ **The production data blast radius is the generated apps, not the toolchain** —
but design-time inputs are still real-data-capable and operator-governed (above). A
generated app's data handling is governed by the **enterprise's own** controls (it
is a standard Spring Boot app); the toolchain that produced it is not in the
production data path.

Cross-links: G8 [§1–§2](security-boundary-map.md), [`suite-architecture.md`](suite-architecture.md).

## 2. Data classification

- **No real customer data / PII is permitted in the suite repositories.** All
  committed fixtures and examples are required to be **synthetic** by contributor
  policy and human review. Pinned gitleaks checks configured secret patterns, not
  semantic PII or real-data content; no automated PII/real-data detector is claimed
  (G7 [§2](compliance-and-portability.md#2-secrets-and-real-data), G3). This is a
  **repository policy** — see operator-supplied inputs below for data fed in at
  runtime.
- **The Evidence Trail records design / decision metadata only** — **no record
  values and no identity-role evidence**. It captures decision provenance
  (`field` / `validation` / `rule` / `cross_entity_rule` / `mapping` / `transform`)
  and adds no new evidence types (G7 §5,
  [`evidence-trail-design.md`](evidence-trail-design.md)).
- **Operator-supplied inputs are operator-governed.** Contracts, sample files, and
  KS-ingested documents an operator feeds the design-time tools **may contain real
  or sensitive data**; EdgeForge does **not** sanitize them or enforce
  synthetic-only. They are held in the operator's own workspace / KS store and
  processed **locally** (no egress; no LLM or provider integration exists, §3).
  Classifying,
  minimizing, retaining, and redacting these inputs is the **operator's
  responsibility**. Within the design-time trust context they are author-supplied
  build inputs, not untrusted network input
  (G8 [§3a](security-boundary-map.md#3-attack-surfaces-per-component)).
- **Runtime data classification is the adopter's.** The generated app touches
  whatever the enterprise's upstream / downstream / database carry; EdgeForge makes
  no classification claim about that data and stores none of it centrally.

## 3. AI / data-egress boundary

The top data-protection question, stated plainly (consolidates G7 §5 + G8 §4):

- **No production / customer data is sent to any LLM or external service.**
- **The Engine is deterministic** — there is **no AI/LLM inference in the
  generation path** (same manifest → byte-identical app; a core invariant in
  [`CONTRIBUTING.md`](../CONTRIBUTING.md)).
- **No LLM or provider integration exists in the suite today** — there is no AI
  capability to enable. **KS-B5** (PII / sanitization / redaction) gates any
  future provider layer — a separate KS-thread item, not resolved here.
  Operator-supplied inputs (§1) are processed **locally** and there is no
  provider to transmit them to. If an adopter connects KS to a model-backed MCP
  host, that is a separate adopter-controlled data boundary and the sanitization
  gap applies there.
- **The only outbound network call** is a **user / manifest-directed** OpenAPI spec
  fetch — no fixed endpoint, no attached credentials, no background call, no
  production data — categorically **not** telemetry. No telemetry / analytics /
  phone-home exists anywhere in the Engine or templates (verified, G7
  [§3](compliance-and-portability.md#3-telemetry-and-phone-home)).

## 4. Multi-session isolation (shared deployment)

When Studio runs as a **shared, multi-user deployment**
(`EDGEFORGE_STUDIO_SHARED_MODE=true` — Studio's operator flag; the Engine subprocess
Studio spawns and KS receive `EDGEFORGE_SHARED_MODE=1` as their **child fail-closed**
flag), each session's data is isolated by a **fail-closed** contract — the
data-governance guarantee for multi-tenant authoring:

- **Per-session, server-owned roots.** Engine generation under MCP requires
  `EDGEFORGE_MCP_ALLOWED_ROOTS` (per-session roots) and is **fail-closed when
  unset** — the Engine install tree and process cwd are never implicit roots. The
  CLI enforces roots when set and hard-fails under `EDGEFORGE_SHARED_MODE`.
  Out-of-root / `..`-traversal / symlink-escape / sibling-session paths are
  **rejected** ([`engine-mcp-design.md`](engine-mcp-design.md)).
- **Per-session KS store.** KS requires a per-session `EDGEFORGE_KS_DB_PATH`; under
  `EDGEFORGE_SHARED_MODE` a missing DB path **fails closed**. Each session's
  knowledge store is a distinct SQLite database, so retrieval does **not** bleed
  **across sessions**.
- **Per-session workspaces.** Studio confines each session's generated output and
  state to its own workspace; cross-session read/write is rejected.
- **Verified at L5 (hermetic).** The suite L5 acceptance gate ran two concurrent
  sessions and confirmed: no session bleed, no read/write outside the server-owned
  root (engine-tree / traversal / symlink / sibling-session all rejected), and
  **per-session KS DB isolation with no cross-session bleed** (SHA-pin engine
  `b11dd04` / studio `0e58f9e` / ks `11aed44`). The Studio→KS leaf launched the
  **pinned** KS deterministically (#253: `command_under_ks_repo: true`, repo-match
  validated — no ambient fallback), and the dedicated `ks.l5` leaf exercised the same
  pinned KS (per-session DB isolation, project-scoped + explicit cross-project-filter
  no-bleed). Full record:
  [L5 acceptance evidence](handover-evidence/l5-acceptance-run.md).

Cross-links: [`engine-mcp-design.md`](engine-mcp-design.md),
[`suite-smoke-harness-design.md`](suite-smoke-harness-design.md),
G8 [§3b](security-boundary-map.md#3-attack-surfaces-per-component).

## 5. Data integrity under regeneration

EdgeForge's maintain-over-time capability evolves an already-deployed,
developer-extended app **without losing developer code or corrupting the
database** — a data-integrity contract that is **implemented on `main` and
L5-verified** (the regeneration leaves are Engine-only and unaffected by the §4
KS-wiring caveat):

- **Developer code is never overwritten.** Generated logic lives in a regenerated
  abstract base; developer logic lives in a scaffold-once subclass written once and
  never re-emitted. Ownership headers mark which is which.
- **Database changes are additive-only.** Regeneration emits **additive** delta
  migrations; prior Flyway migrations are **immutable**; **destructive changes fail
  closed** and are never auto-applied.
- **Plan-hash-bound apply.** The Change Plan dry-run is read-only; a plan hash over
  manifest + committed baseline + output-package state **refuses apply on any
  preview→apply drift**.
- **Verified at L5.** The `engine.regenerate` and `engine.change_plan` leaves
  proved, against real PostgreSQL / Flyway: developer-service preservation,
  generated-`ServiceBase` refresh, prior-migration immutability, additive apply,
  and destructive / plan-hash-drift **refusal**.

Cross-links: [`regenerate-maintain-model-design.md`](regenerate-maintain-model-design.md),
[`regenerate-maintain-suite-design.md`](regenerate-maintain-suite-design.md).

## 6. Secrets & credentials

- **No secrets committed** — enforced on every PR by the pinned gitleaks scan
  (G3 / G7 §2).
- **Runtime credentials are env-var-injected** (`${SPRING_DATASOURCE_USERNAME/PASSWORD}`),
  not hardcoded.
- **A6 resolved:** enterprise PostgreSQL profiles require
  `SPRING_DATASOURCE_USERNAME` and `SPRING_DATASOURCE_PASSWORD` with no generated
  `postgres` fallback, so missing credentials fail fast. The local H2 profile is
  unchanged.

## 7. Audit & traceability

What is auditable today, honestly scoped:

- **Decision provenance** — the **Evidence Trail** records which generated
  artifacts came from accepted / edited authoring decisions; design metadata only,
  no record values ([`evidence-trail-design.md`](evidence-trail-design.md)).
- **Regeneration audit** — every apply is gated by an **approved Change Plan** plus
  a **plan-hash**; a destructive or drifted plan is refused, leaving a deterministic
  record of what was and was not applied (§5).
- **Acceptance evidence** — the L5 gate emits a **SHA-pin manifest** (the three repo
  HEADs + topology) as reproducible proof of what passed. The hermetic run (engine
  `b11dd04` / studio `0e58f9e` / ks `11aed44`) is recorded in the
  [L5 acceptance evidence artifact](handover-evidence/l5-acceptance-run.md)
  ([`suite-smoke-harness-design.md`](suite-smoke-harness-design.md)).
- **Runtime audit logging is the adopter's.** A generated app is standard Spring
  Boot; application / access audit logging is configured by the enterprise in its
  own environment. EdgeForge does not impose or centralize a runtime audit log.

> **Honest gap:** there is no built-in *central* audit-log aggregation beyond the
> artifacts above; runtime audit / observability is delegated to the adopter's
> standard Spring Boot + platform tooling.

## 8. Retention & residency

- **No central data store.** The design-time tools persist their artifacts
  (manifests, generated source, Evidence Trail, per-session KS SQLite) **on the
  developer / build host or per-session workspace** — there is no EdgeForge-operated
  server or cloud store.
- **Runtime residency is the adopter's.** Generated apps run in the enterprise's own
  environment against its own database / messaging; data residency and retention
  follow the enterprise's deployment and policies.

---

## Caveats summary (not buried)

- **Operator-supplied design-time inputs are operator-governed** — EdgeForge does
  **not** enforce-synthetic on uploaded contracts / samples / KS documents (§1, §2).
- **No LLM or provider integration exists today**; KS-B5 PII / sanitization
  design gates any future provider layer (§3) — no production data to any LLM.
- **Datasource credentials** — enterprise PostgreSQL credentials are
  env-var-required / fail-fast; local H2 remains dev-only (§6).
- **Runtime audit is the adopter's** — no central audit-log aggregation built in
  (§7).
- **Runtime data classification / residency** are the adopter's responsibility —
  EdgeForge stores no production data (§2, §8).
- Inherited from G7 / G8: **own license unresolved** and
  **transitive-dependency disposition** remains adopter-owned. SOAP-envelope SAAJ
  hardening is implemented; deployment ingress/concurrency limits remain
  adopter-owned defense in depth — see those gates.

## See also

- [Compliance & Portability Checklist](compliance-and-portability.md) (G7) — the
  import / compliance answer-sheet.
- [Security Boundary Map](security-boundary-map.md) (G8) — the trust-boundary /
  attack-surface companion.
- [Suite Architecture — START HERE](suite-architecture.md) · [Glossary](glossary.md).
- [`regenerate-maintain-model-design.md`](regenerate-maintain-model-design.md) ·
  [`regenerate-maintain-suite-design.md`](regenerate-maintain-suite-design.md) ·
  [`engine-mcp-design.md`](engine-mcp-design.md) ·
  [`suite-smoke-harness-design.md`](suite-smoke-harness-design.md).
