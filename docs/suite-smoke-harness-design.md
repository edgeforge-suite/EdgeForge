# Suite Smoke Harness — Design (enterprise-readiness acceptance)

> **Status:** Design / docs only — no code, no Compose, no fixtures, no scripts in this PR. Defines a
> *layered* suite smoke harness for the EdgeForge enterprise-readiness MVP. Scope = the 3 mandatory
> repos: **Engine** (`appbuilder`), **Studio**, **KS/KA**. TestBench stays separate (§2, §9).
>
> This is the harness the [enterprise-readiness roadmap](enterprise-readiness-roadmap.md) gates the
> "enterprise-ready MVP" claim on. It is **acceptance smoke** — not a regression suite, not a
> replacement for per-repo unit tests, and not a replacement for TestBench's product role.
>
> **Last updated:** 2026-06-14.

---

## 1. Purpose

EdgeForge is doing large, **parallel cross-repo** enterprise-readiness work — Engine
regenerate/maintain (ownership-aware writer, service generation-gap, `db/schema-baseline.json`,
regeneration-mode detection, upcoming Change Plan dry-run / plan hash / additive migrations /
destructive fail-closed) and Studio multi-session / shared deployment (SessionStore, route re-keying,
CSRF/request-session context, upcoming shared-mode security gates, per-session workspace roots,
per-session KS DB, Engine output isolation).

Per-repo **unit tests remain primary** for local correctness — they are fast, they run on every PR,
and they are where a behavior is proven first. What unit tests *cannot* catch is **cross-repo
integration drift**: a Studio session-isolation change that breaks the path Engine generates into; a
KS per-session change that lets one session see another's documents; a regeneration change that
silently clobbers a developer file; an Engine output-layout change that breaks the generated app's
standalone runtime. That class of failure only shows up when the real components run together.

This harness exists to give **staged confidence** at exactly those seams, without becoming one giant
brittle "run everything always" suite. It is **enterprise-readiness acceptance smoke**: the evidence
that the suite behaves correctly *together* before a coordinated baseline tag / enterprise handoff.

It is explicitly **not** a replacement for TestBench. TestBench is specific to the **Kafka-router
archetype** product role; this harness covers the CRUD / REST-passthrough / edge-contract /
multi-session / regeneration surfaces that TestBench does not (and reuses the per-app
[Test Console](generated-app-standards/generated-app-test-console-ux-design.md) for per-app functional
proof rather than duplicating it).

## 2. Non-goals

- **Not** a full, exhaustive regression suite — it samples the high-risk seams, not every code path.
- **Not** a Kubernetes / production deployment platform — it proves behavior, not scale or ops.
- **Not** a replacement for per-repo unit tests (L0 stays primary).
- **Not** a replacement for TestBench's Kafka/router product role.
- **Not** intended to run full suite smoke on every PR (see §11) — full acceptance is staged/manual.
- **Not** a path to add any runtime dependency from a generated app back to EdgeForge, Studio, KS,
  KA, or TestBench. Generated apps stay standalone; the harness only *builds and exercises* them.

## 3. Layered smoke model (L0–L5)

The harness is layered so each stage runs the *cheapest test that can catch its class of failure*.
Higher levels assume lower levels pass; they do not re-prove them.

**L0 — Per-repo unit / focused tests**
- **Owner:** each repo (Engine, Studio, KS).
- **Trigger:** every PR + local dev (existing CI).
- **Runtime target:** seconds to a few minutes.
- **Proves:** local unit correctness within a repo.
- **Does NOT prove:** any cross-repo integration; runtime behavior of a generated app.

**L1 — Engine generated-app compile smoke**
- **Owner:** Engine.
- **Trigger:** every Engine generate/regenerate PR.
- **Runtime target:** a few minutes (`mvn -q -DskipTests package` of a small fixture).
- **Proves:** a generated package compiles and is structurally standalone (no EdgeForge/Studio/KS
  runtime imports).
- **Does NOT prove:** runtime behavior, multi-session, regeneration safety, cross-repo paths.

**L2 — Studio shared-mode session smoke**
- **Owner:** Studio.
- **Trigger:** every Studio multi-session PR.
- **Runtime target:** a few minutes.
- **Proves:** two-session isolation, CSRF enforcement, shared-mode security gates, server-owned
  per-session paths, rejection of user-supplied filesystem paths.
- **Does NOT prove:** regeneration, generated-app runtime, deep KS isolation, Engine invocation paths.

**L3 — Engine regeneration dry-run / apply smoke**
- **Owner:** Engine.
- **Trigger:** after each Change Plan dry-run / apply PR (and regenerate PRs touching preservation).
- **Runtime target:** a few minutes.
- **Proves:** developer-owned `{Entity}Service` preservation, generated-base refresh, migration
  byte-stability, baseline update, dry-run plan stability, `plan_hash` sensitivity, additive vs
  destructive fail-closed.
- **DB proof (once apply exists):** include at least one **real Postgres + Flyway DB-regeneration
  proof** — apply the additive migration to a live schema — not only the dry-run plan. Dry-run-only
  L3 runs need no DB (see §5).
- **Does NOT prove:** multi-session, full generated-app runtime, edge-contract runtime coexistence.

**L4 — Cross-repo Studio → Engine → KS smoke**
- **Owner:** Suite (top-level driver) with Studio / Engine / KS helpers.
- **Trigger:** after Studio per-session runtime-isolation lands and the Studio↔Engine↔KS integration
  points exist.
- **Runtime target:** tens of minutes.
- **Proves:** Studio invokes Engine per-session into server-owned paths with no output collision;
  Studio↔KS per-session isolation (no cross-session document/search bleed); the end-to-end author →
  generate flow under shared mode.
- **Does NOT prove:** the full edge-contract runtime matrix; baseline-tag acceptance.

**L5 — Full enterprise-readiness acceptance smoke**
- **Owner:** Suite docs repo (acceptance checklist), executed across all three repos.
- **Trigger:** before a coordinated suite baseline / tag / enterprise handoff (manual / pre-baseline).
- **Runtime target:** the longest — tens of minutes up to ~an hour.
- **Proves:** everything together — multi-session isolation + shared-mode security + regeneration
  safety + Change Plan behavior + edge-contract coexistence + generated-app runtime (REST / file /
  XML / bounded SOAP) + KA-OFF cleanliness.
- **Does NOT prove:** production-scale performance/load (out of scope); exhaustive regression.

## 4. Stage gates

The smoke levels map onto the current roadmap stages so each landing runs the smoke that protects it:

| Roadmap stage | Smoke to run |
|---|---|
| After each Engine **regenerate** PR | **L1** (+ **L3** once dry-run/apply exist) |
| After each Studio **multi-session** PR | **L2** |
| After Engine **Change Plan dry-run** | **L3** dry-run scenarios |
| After Studio **per-session runtime isolation** | **L4** cross-repo |
| After Engine **apply** + Studio **preview/apply** | **L3** apply + **L4** |
| Before **suite baseline tag / enterprise handoff** | **L5** full acceptance |

Lower levels are a precondition for higher ones: an L4 run assumes the relevant L1/L2/L3 are green.

## 5. Container / process topology

The harness must mirror the **real product architecture**, not a convenient fiction:

- **Smoke runner** — a Python process/script that orchestrates a scenario, asserts outcomes, and
  tears down. It is the only "driver"; it is not a service.
- **Studio** — launched in **shared mode**, single replica, with its server-owned per-session
  workspace roots and SessionStore. This is the entry point for L2/L4/L5.
- **Engine** — invoked **by Studio as a subprocess / MCP**, exactly as in production. The harness must
  **not** stand Engine up as a long-lived HTTP service.
- **KS** — invoked **by Studio per session over local stdio when suggestions are enabled**, exactly as
  in production (deterministic, suggestion-only; **KA/KS OFF by default — not called in the background**).
  The harness must **not** fake KS as a long-lived service.
- **Postgres** — a container used for generated-app runtime + DB-regeneration scenarios (L4/L5, and
  **L3 once additive-migration / apply exists** — at least one real Flyway apply against a live
  schema). Not required for L1/L2, nor for L3 dry-run-only scenarios.
- **Mock SOAP / external service** — a stub endpoint stood up **only** for the bounded-SOAP-outbound
  runtime scenario, so the generated app's outbound SOAP call has a deterministic target to invoke and
  assert against. It is a test double, not a product component, and is never a runtime dependency of
  the generated app.
- **Generated app** — built only in L1 (compile) and built+run only in the specific L4/L5 runtime
  scenarios; it runs **standalone** against Postgres with no link back to the suite.

> **Explicit rule:** do not model Engine or KS as long-lived services unless the product architecture
> itself changes. They are a subprocess and a per-session stdio process respectively; the harness must
> exercise those exact invocation paths so it catches real integration drift.

## 6. Test fixtures and golden packages

All fixtures are **generic and domain-free** (no customer/vendor names, no domain entities). Fixture
classes:

- **Minimal CRUD REST fixture** — one or two generic entities; proves REST/OpenAPI coexistence and the
  smallest viable generate→compile→run loop.
- **Combined edge-contract fixture** — a single manifest that exercises **REST + fixed-width file +
  CSV/delimited + XML/XSD + bounded SOAP inbound/outbound + a staging handoff + Evidence-Trail
  metadata** *together*, to prove coexistence (the protective net over closed edge-contract v1). The
  **outbound-SOAP** leg pairs with the mock SOAP / external service in the topology (§5) so the call
  has a deterministic target to invoke and assert against.
- **Regeneration fixture** — a set:
  - an initial generated package (with `db/schema-baseline.json` + ownership headers),
  - an evolved manifest (add field / remove field / type change),
  - a developer-owned `{Entity}Service` edit (the hand-written business logic that must survive),
  - the **expected Change Plan**, and
  - the **expected outcome**: an additive migration for safe changes, or a destructive fail-closed for
    unsafe ones.
- **Multi-session fixture** — two independent sessions/projects with **distinct** uploaded
  docs/artifacts and **distinct** output packages, used to prove no cross-session bleed.

Golden packages stay small and deterministic; large generated output is produced under temp roots
(§10, §12), not committed.

## 7. Required MVP smoke scenarios

At minimum, the harness must cover:

**Multi-session isolation**
- Session A and Session B cannot see each other's project state, uploads, KS documents, or output
  packages.

**Shared-mode security**
- CSRF is enforced.
- Build & Run is rejected **server-side** in shared mode.
- User-supplied filesystem paths are ignored/rejected (server owns paths).
- The OpenAPI URL policy is obeyed (no out-of-policy fetches).

**Studio → Engine**
- Generation uses server-owned **per-session** paths.
- No shared output-directory collision between concurrent sessions.

**KS/KA explicitly enabled — per-session isolation (positive *and* negative)**
- This scenario applies **only when KS/KA suggestions are explicitly turned on** (the default is the
  strict KA-OFF scenario below). Once enabled, KS must be per-session isolated:
- Per-session KS DB / path.
- **Positive:** KS serves the *current* session correctly — a `search` / `search_across_projects` in
  session A returns session A's own indexed documents.
- **Negative:** the same search in session A does **not** surface session B's documents (no
  cross-session bleed).

**Engine regenerate**
- A developer-owned `{Entity}Service` **survives** regeneration.
- The generated `{Entity}ServiceBase` refreshes.
- Existing Flyway migrations remain **byte-stable** (immutable).
- `db/schema-baseline.json` updates correctly.

**Change Plan**
- The dry-run plan is **stable** for fixed inputs.
- `plan_hash` changes if the manifest, baseline, **package state**, a developer file, or the Flyway
  inventory changes.
- Destructive / unsafe changes **fail closed**.
- Edge-contract impact is surfaced in the plan.

**Generated-app runtime**
- The generated app compiles.
- REST create/get works.
- File ingest/output works.
- XML ingest/output works.
- Bounded SOAP inbound/outbound works where relevant.

**KA OFF — strict default (no hidden/live KS *or* KA activity)**
- With KA OFF (the default), the entire suggestion machinery is **quiet**: **no hidden or live KS
  calls, no KA/LLM calls, and no suggestion/evidence noise.** KS/KA is opt-in — nothing queries it in
  the background. This matches the suite's standing "KA OFF by default" posture; live KS calls appear
  **only** in the explicitly-enabled isolation scenario above, never as a side effect of normal use.

## 8. Pass / fail criteria

**Hard fail** (the run fails; no handoff):
- Build / compile failure of a generated app.
- Session bleed (any cross-session visibility of state, uploads, KS docs, or outputs).
- Any file written or read **outside** the server-owned workspace root.
- Any hidden/live **KS or KA/AI (LLM)** call when KA is OFF (the default) — the suggestion machinery must be silent unless explicitly enabled.
- A **stale `plan_hash` accepted** at apply (drift not detected).
- A destructive/unsafe migration **silently emitted** (not failed-closed).
- Generated-app **runtime** failure on a required scenario.
- An **absolute local path leak** in Evidence Trail or any committed/emitted artifact.

**Warning** (recorded, does not fail the run by itself):
- Known optional advisory output when a mode is explicitly enabled.
- Non-blocking performance observations (full perf/load is out of scope).
- Optional/edge scenarios marked non-required for the current MVP gate.

Every warning must be explicitly enumerated in the acceptance checklist so a warning is never silently
upgraded into "passed."

## 9. Ownership model

- **Engine** owns the generated-app **compile/regenerate** smoke pieces (L1, L3 helpers + fixtures).
- **Studio** owns the **shared-mode / session** smoke driver (L2, and the L4 orchestration entry).
- **KS** owns the **KS isolation / reliability** smoke helpers (per-session DB/path, no-bleed checks).
- **Suite docs repo** (this repo) owns the **top-level smoke harness design** and the **L5 acceptance
  checklist** — the cross-repo coordination layer.
- **TestBench** remains **separate** (Kafka-router product role) unless a later, explicit decision
  expands its charter.

## 10. Where scripts should eventually live (proposed — not implemented here)

- Top-level suite-smoke orchestration: **`scripts/smoke/`** in the Engine repo to start, or a future
  dedicated **`suite-smoke/`** folder/repo if the harness outgrows Engine.
- Per-repo helper scripts live **near each repo** (Studio session driver in Studio, KS isolation
  helpers in KS, compile/regenerate helpers in Engine).
- Generated output is written under a deterministic temp root: **`/tmp/edgeforge-suite-smoke-*`**.
- **No committed generated output** — except small, deliberate golden fixtures (§6).

## 11. CI strategy

- Initially, focused smoke (L1/L2/L3) runs **manually or nightly**, not on every PR.
- **L5** full acceptance is **manual / pre-baseline** at first.
- Do **not** block every PR on full smoke — keep the per-PR loop fast (L0 + the relevant focused
  level).
- Later, promote **L1/L2** into CI as time and runtime budget allow.
- Keep the runtime budget realistic per level (§3); a smoke level that grows too slow stops being run.

## 12. Data governance / cleanup

- All smoke output lives under deterministic temp roots (`/tmp/edgeforge-suite-smoke-*`).
- A clear **cleanup policy**: each run removes its temp root on success; failures retain it for triage
  under a known path, pruned on the next run.
- **No real data** — generic, synthetic fixtures only.
- **No absolute local paths** in committed artifacts (golden fixtures must be path-relative).
- **No secrets** in fixtures, logs, or committed files.
- Logs are **redacted** where they could contain paths or environment specifics.

## 13. Relationship to existing docs

- [Regenerate / Maintain — Engine-internal design](regenerate-maintain-model-design.md) — the
  ownership model, baseline, additive/destructive rules the L3 scenarios assert.
- [Regenerate / Maintain — Suite design](regenerate-maintain-suite-design.md) — the Change Plan
  contract, `plan_hash` / `package_state_hash`, and plan-hash binding the L3 Change Plan scenarios
  assert.
- **Studio `docs/multi-session-architecture-design.md`** (Studio repo) — the SessionStore / shared-mode
  / per-session model the L2/L4 scenarios assert. *(Cross-repo; referenced textually, not linked.)*
- [Edge-Contract Handoff Readiness Matrix](edgecontracts/edge-contract-handoff-readiness-matrix.md) +
  [Edge-Contract Expansion Roadmap](edge-contract-expansion-roadmap.md) — the closed edge-contract v1
  surfaces the combined-edge-contract fixture protects.
- [Generated-App Test Console UX](generated-app-standards/generated-app-test-console-ux-design.md) —
  the per-app functional surface the runtime scenarios reuse rather than duplicate.
- [Enterprise-Readiness & Handoff Roadmap](enterprise-readiness-roadmap.md) — the roadmap whose
  "enterprise-ready MVP" gate this harness backs.
- [Suite Task Tracker](tracker/README.md) — see §14 for the tracker-row note.
- **TestBench docs** (TestBench repo) — this harness does **not** replace TestBench's Kafka-router
  product role; the two are complementary. *(Cross-repo; referenced textually.)*

## 14. Implementation slices (proposed future PRs)

- **Slice 0 — design doc only** *(this PR)*.
- **Slice 1 — Engine generated-app compile/regenerate smoke runner** (L1 + L3 fixtures/helpers).
- **Slice 2 — Studio shared-mode two-session smoke runner** (L2).
- **Slice 3 — Studio → Engine → KS cross-repo smoke** (L4 driver + per-repo helpers).
- **Slice 4 — Regeneration Change Plan smoke** (L3 Change Plan scenarios on the regeneration fixture).
- **Slice 5 — Full enterprise-readiness acceptance smoke** (L5 + the acceptance checklist).
- **Slice 6 — Optional CI / nightly wiring** (promote L1/L2; schedule nightly focused smoke).

> **Tracker note:** when **Slice 1** starts, a tracker row (e.g. `suite-smoke-harness`,
> in-progress, Slices 0–6, owner = suite) should be added to `docs/tracker/suite-tracker.json`. This
> PR is **design-only** and deliberately does **not** modify the tracker.

## 15. Open questions

- **Top-level harness home** — should it live in the Engine repo (`scripts/smoke/`) or a future
  dedicated `suite-smoke/` folder/repo?
- **Runtime proof boundary** — how much generated-app runtime proof belongs here vs in TestBench (for
  any archetype overlap)?
- **L5 CI gating** — when should L5 become CI-gated rather than manual/pre-baseline?
- **Postgres scope** — should Postgres be mandatory for *all* full smoke runs, or only the
  DB-regeneration / runtime scenarios that need a live schema?
- **Reproducible evidence** — how should cross-repo SHAs be pinned (a manifest of Engine/Studio/KS
  commit SHAs per smoke run) so an acceptance run is reproducible and auditable?

---

*This harness backs the enterprise-readiness MVP gate. It is layered acceptance smoke over the 3
mandatory repos — complementary to per-repo unit tests (L0, primary for local correctness) and to
TestBench (separate, Kafka-router product role).*
