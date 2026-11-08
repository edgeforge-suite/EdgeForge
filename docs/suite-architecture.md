# EdgeForge Suite Architecture — START HERE

> **What this is:** the single front-door for anyone — a new human dev or an AI
> agent (Claude / Devin / Copilot / Codex) — landing in this repo cold. Read this
> first to understand the suite, find the right repo/dir for your task, and start
> working without tribal knowledge.
>
> **Last updated:** 2026-06-08. This is the canonical orientation doc; the
> per-tool agent files are thin pointers to it.
>
> **You are in:** the **Engine** repo (product = **EdgeForge**; Python
> module/CLI = `appbuilder`). The other four repos are separate — described here
> by role.
>
> **See also:** [`docs/appbuilder-context.md`](appbuilder-context.md) (current
> suite state) and [`docs/repo-blueprint.md`](repo-blueprint.md) (deeper
> foundational architecture) go deeper than this front-door. Authoritative rules
> and invariants live in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

---

## 1. What EdgeForge is

EdgeForge is a **contract-preserving modernization platform** for
legacy-heavy enterprise domains. It takes the contracts a legacy system
must keep honoring — upstream APIs and downstream files/tables/messages — and
generates a replacement application that stays **backward-compatible at the
edges** while modernizing everything inside. It is deterministic, governed, and
evidence-backed; it is **not** generic AI code generation. Business logic stays
explicit, reviewed, and traceable.

## 2. The suite map (3 core repos + optional tooling + generated apps)

```
                 suggests (deterministic; no LLM integration exists)
   KS / KA  ───────────────────────────────┐
                                            ▼
   Studio  ──authors──►  manifest  ──►  Engine (appbuilder)  ──generates──►  Generated app
  (review UX)         (app-definition)     [THIS REPO]                    (standalone Spring Boot)
        │                                  owns the manifest contract:             │
        └─ conforms to the Engine's ─────► appbuilder/schema/                      ▼
           authoritative schema            manifest-v2.schema.json   (optional) TestBench ──exercises──┘
```

The **Engine owns the manifest contract** — `appbuilder/schema/manifest-v2.schema.json`
is the authoritative runtime validator. Studio (and any other upstream producer)
**conforms to** that schema; the Engine does not depend on them. (See
[`docs/upstream-integration-boundary.md`](upstream-integration-boundary.md).)

**Core suite** — the author → generate flow an adopting organization imports:

| Component | Repo? | One-line role |
|---|---|---|
| **Engine** (`appbuilder`) | **this repo (core)** | Deterministically generates the standalone app from a reviewed manifest. Owns the generation contract. |
| **Studio** | separate (core) | Authoring/review UX: produces the app-definition manifest a human has reviewed; conforms to the Engine's manifest schema. |
| **Knowledge Server / Assist (KS/KA)** | separate (core) | Deterministic, evidence-backed **suggestions** during authoring. **No LLM or provider integration exists in the suite today**; KS-B5 gates any future provider layer. |
| **Generated apps** | output | Standalone Spring Boot apps the Engine emits. **No runtime dependency** on any suite component. |

**Optional / not required to import** — the Engine has no dependency on either:

| Component | Repo? | Why optional |
|---|---|---|
| **TestBench** | separate (optional) | A local runtime/scenario proof harness (e.g. Kafka-router testing). The Engine validates via its own [`appbuilder/harness/`](../appbuilder/harness/) plus the generated apps' own tests, so an adopting organization with its own test infrastructure need not import it. |
| **shared-specs** | external (optional) | A design-time contract document. The Engine owns the authoritative schema (`appbuilder/schema/manifest-v2.schema.json`); producers conform to it (see [`docs/upstream-integration-boundary.md`](upstream-integration-boundary.md)). Not required to import. |

> **This core/optional split is the canonical reference for the suite.** The
> three core repos (Engine, Studio, KS/KA) carry the author → generate flow;
> TestBench and shared-specs are real but **optional** — an adopting
> organization need not import them.

**Flow in one line:** KS/KA suggests → a human reviews in Studio → Studio exports
a manifest → **Engine generates deterministically** → *(optionally)* TestBench
proves it runs.

## 3. Core architecture theses

- **Canonical internal model.** External contracts are mapped into a stable,
  normalized internal domain model. Never bind business logic directly to raw
  external shapes; never do API-to-entity generation.
- **Dual-edge contract preservation.** Both edges are first-class contracts:
  **upstream** APIs (REST/JSON, SOAP/XML, XML/XSD) and **downstream** handoffs
  (files, staging tables, messages). Edge contracts live under
  `upstream_interfaces[]` / `downstream_interfaces[]`.
- **Manifest-driven.** Generation reads an explicit, reviewed manifest
  (`manifest-v2`, `schema_version: "2.0"`) — not guesses from arbitrary files.
  New concepts are **additive optional extensions only**.
- **Deterministic output.** The same manifest produces the same app
  (byte-identical regeneration). No silent inference, no auto-apply.
- **Mode semantics.** Where a feature carries a `mode`: `metadata_only` =
  accepted and recorded but emits **zero generated artifacts**; `active` =
  Engine must **generate the declared behavior or fail fast** — never a silent
  no-op or a plausible scaffold passed off as complete.

## 4. This (Engine) repo structure

**Top-level:**

| Path | What it is |
|---|---|
| `appbuilder/` | The Engine Python package (generation logic; see below). |
| `docs/` | Suite + Engine docs. Canonical index: [`docs/README.md`](README.md). |
| `tests/` | Engine test suite (pytest), including golden-contract fixtures. |
| `examples/` | Sample input projects (`examples/input-projects/<name>/app-definition.yaml`). |
| `GeneratedApps/` | Placeholder documenting that generated-output snapshots are not committed; regenerate representative apps from `examples/input-projects/` or `tests/fixtures/`. |
| `templates/` | Generation templates (`springboot/`, `python/`). |
| `.github/` | CI workflows and repo automation. |
| `CONTRIBUTING.md` · `README.md` · `CHANGELOG.md` · `requirements.txt` | Authoritative rules · baseline · changelog · pinned deps. (`CLAUDE.md` / `AGENTS.md` / `.github/copilot-instructions.md` are thin tool-specific pointers to `CONTRIBUTING.md`.) |

**`appbuilder/` subpackages:**

| Package | Responsibility |
|---|---|
| `api/` | Builder API surface (thin package placeholder today). |
| `contracts/` | Ingest + validate external contract definitions (manifest loader, SOAP/WSDL, XML/XSD). |
| `core/` | Archetype dispatch (`archetypes.py`) and manifest version handling; shared abstractions. |
| `metadata/` | Canonical metadata models + translation (incl. file and Kafka contract metadata). |
| `mapping/` | External ↔ canonical mapping ingestion and models. |
| `rules/` | Business-rule ingestion and models. |
| `generation/` | Turn canonical metadata + target profile into the generated app (Java/SQL/build/UI emitters). |
| `target_profiles/` | Runtime compatibility profile catalog (`catalog.py`). |
| `harness/` | Generated-app validation gates / quality checks. |
| `ingestion/` | OpenAPI/Swagger fetch + classify. |
| `mcp/` | Local stdio MCP server tool implementations (`tools/`: catalog, generation, schema). |
| `schema/` | The `manifest-v2.schema.json` JSON Schema plus independently versioned schemas. |
| `testing/` | Compatibility/test scaffolding helpers. |
| `cli.py` | The `appbuilder` CLI (`generate`, `assess`). |
| `mcp_server.py` | Local stdio MCP server entrypoint. |

## 5. Getting started (orientation)

> Step-by-step golden path: see **[`docs/quickstart.md`](quickstart.md)** —
> clone → setup → generate → build & run the sample app → exercise its test
> console (~10 min). The commands below are the orientation subset.
>
> **One-liners:** the root `Makefile` wraps routine tasks — `make test`,
> `make generate-sample`, `make mcp` (run `make help` to list them).

Set up for current release preparation (Python 3.11, constrained dependencies):

```bash
python3.11 -m venv --copies .venv
.venv/bin/python -m pip install -c requirements-lock.txt -r requirements.txt
.venv/bin/python -m pip check
```

Run the test suite:

```bash
.venv/bin/python -m pytest -v
```

Generate a sample app from a manifest:

```bash
.venv/bin/python -m appbuilder.cli generate \
  --manifest examples/input-projects/workspace-items/app-definition.yaml \
  --output /tmp/edgeforge-sample-app
```

Run the local Engine MCP server (stdio; thin adapter over the deterministic
Engine functions):

```bash
.venv/bin/python -m appbuilder.mcp_server
```

(The generated app is a standalone Maven Spring Boot project — `mvn clean
compile` inside the output dir builds it. See the root [`README.md`](../README.md)
for the full local-run and MCP-client config detail.)

## 6. Where do I go for X?

| I want to… | Go to |
|---|---|
| Add/extend an **edge-contract family** (file, XML/XSD, SOAP/WSDL, …) | Design first: [`docs/edge-contract-expansion-roadmap.md`](edge-contract-expansion-roadmap.md) + [`docs/edgecontracts/`](edgecontracts/README.md). Then code: `appbuilder/contracts/` (parse/validate) + `appbuilder/generation/` (emit). |
| Change how the **app is generated** | `appbuilder/generation/` |
| Change the **canonical model / manifest** | `appbuilder/metadata/` + `appbuilder/schema/` (+ [`docs/manifest-schema.md`](manifest-schema.md)) |
| Add/adjust a **target profile** | `appbuilder/target_profiles/catalog.py` |
| Change **validation / quality gates** | `appbuilder/harness/` |
| Change **mapping** or **rules** ingestion | `appbuilder/mapping/` · `appbuilder/rules/` |
| Touch the **local MCP server** | `appbuilder/mcp/` + `appbuilder/mcp_server.py` (bounded surface — design revision required to expand) |
| Change **authoring / review UX** | **Studio** (separate repo) |
| Change **suggestions / indexing** | **KS / KA** (separate repo) |
| Change **runtime / scenario proof** | **TestBench** (separate repo) |
| Change the **manifest / contract schema** | `appbuilder/schema/manifest-v2.schema.json` (the Engine owns it; producers conform) |
| Understand the **handoff/enterprise-readiness plan** | [`docs/enterprise-readiness-roadmap.md`](enterprise-readiness-roadmap.md) (master tracker) |
| Answer an **import / compliance question** (license, secrets, telemetry, standalone, portability) | [`docs/compliance-and-portability.md`](compliance-and-portability.md) |
| Understand the **trust boundaries / attack surface** (security architect's view) | [`docs/security-boundary-map.md`](security-boundary-map.md) |

## 7. Build & review workflow (conventions)

Summarized from [`CONTRIBUTING.md`](../CONTRIBUTING.md) — **that file is authoritative**:

- **PR-only.** Never push or merge directly to `main`. Every change goes through
  a pull request; review-first by default.
- **Dual-agent loop.** Whoever **authors** a PR is not its primary reviewer —
  build and review are handed across agents.
- **Branch naming:** `<agent>/{feature|fix|docs|chore}/<short-desc>` where
  `<agent>` ∈ `claude | codex | devin | <human>`; plus `generated/<app-name>`
  and `review/<agent>-<topic>`.
- **PR title prefixes:** `[FEATURE]` · `[FIX]` · `[DOCS]` · `[CHORE]` ·
  `[GENERATED]`.
- **PR body** states what changed, why, how it was validated, and any risk to
  contract compatibility / backward compatibility.

## 8. Non-negotiable invariants

Summarized here; [`CONTRIBUTING.md`](../CONTRIBUTING.md) is the source of truth.

- **Public-safe committed content.** Synthetic examples and necessary public
  upstream references/attribution are permitted; private customer/organization
  material is excluded. See the current contribution and source-release policy.
- **Generated apps are standalone.** No runtime dependency on EdgeForge,
  Studio, KS/KA, or MCP. Each generated app is independently buildable with its
  own `README.md` and `Dockerfile`.
- **Canonical model, never API-to-entity.** Map external contracts into the
  canonical internal model; keep external adapters separate from core logic.
- **Deterministic Engine output.** Same manifest → same app. No generic AI
  inference, no silent auto-apply, no name inference; `active`/explicit mappings
  generate a supported artifact **or fail fast**.
- **Manifest is additive-only after the completed coordinated cut.** V2-E makes Engine
  single-dialect `schema_version: "2.0"`; V2-S makes Studio export `2.0`; paired-branch and
  post-merge V2-X passed. Optional extensions evolve within that active dialect.
- **Edge contracts stay in their arrays.** Use `upstream_interfaces[]` /
  `downstream_interfaces[]`; never add parallel `*_contracts[]` arrays and never
  route file/XML/SOAP edge contracts through `data_handoffs[]` (that stays
  table/datastore-handoff oriented).

## 9. Pointers

- [`docs/README.md`](README.md) — the canonical docs index (start there for the
  full doc set).
- [`docs/enterprise-readiness-roadmap.md`](enterprise-readiness-roadmap.md) —
  the suite-level master tracker for import-readiness and handoff.
- [`docs/edge-contract-expansion-roadmap.md`](edge-contract-expansion-roadmap.md)
  — the strategic roadmap for upstream/downstream edge-contract preservation.
- [`docs/appbuilder-context.md`](appbuilder-context.md) — current suite state.
- [`docs/repo-blueprint.md`](repo-blueprint.md) — foundational architecture and
  module detail.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — authoritative rules and invariants
  (the `CLAUDE.md` / `AGENTS.md` / Copilot files are thin pointers to it).
