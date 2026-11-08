# EdgeForge Suite Glossary

> **What this is.** The shared vocabulary a new human or AI agent needs to read
> the suite without tribal knowledge. Each entry is distilled from the
> authoritative doc and carries a **See:** link there — this glossary defines
> terms, it does **not** redefine or supersede the source. Terms are
> alphabetical.
>
> **See also:** [`suite-architecture.md`](suite-architecture.md) (START HERE
> orientation) · [`appbuilder-context.md`](appbuilder-context.md) (current-state
> detail) · [Decision Records (ADRs)](decisions/README.md) (the *why* behind the
> core terms below).

---

**Allowed roots / shared-mode isolation** — The fail-closed contract that confines
each session's file access in a shared, multi-user deployment. Under MCP, generation
requires `EDGEFORGE_MCP_ALLOWED_ROOTS` (per-session, server-owned roots) and is
rejected when unset; the CLI enforces roots when set and hard-fails under
`EDGEFORGE_SHARED_MODE`. The Engine install tree and process cwd are never implicit
roots; out-of-root, `..`-traversal, symlink-escape, and sibling-session paths are
rejected. See: [`engine-mcp-design.md`](engine-mcp-design.md),
[`data-governance-posture.md`](data-governance-posture.md).

**App archetype** — The generation shape the Engine dispatches on, declared as
`app_archetype` in the manifest (`crud`, `passthrough-router`,
`kafka-integration`). Dispatch is explicit, never inferred.
See: [`suite-architecture.md`](suite-architecture.md),
[`appbuilder-context.md`](appbuilder-context.md).

**App regeneration / maintain-over-time** — Re-running the Engine over an
already-generated, deployed app to evolve it safely: developer code is preserved (see
**Ownership headers**), database changes are **additive-only** with immutable prior
migrations, destructive changes fail closed, and apply is **plan-hash**-bound.
Implemented on `origin/main` and L5-verified. See:
[`regenerate-maintain-model-design.md`](regenerate-maintain-model-design.md),
[`regenerate-maintain-suite-design.md`](regenerate-maintain-suite-design.md).

**appbuilder** — The Python module and CLI that implements the Engine. The
**product** is EdgeForge; **`appbuilder`** is the module/CLI name used in code and
commands. See: [`suite-architecture.md`](suite-architecture.md).

**Canonical (internal) model** — The stable, normalized internal domain model that
external contracts are mapped into. Business logic binds to this model, never to
raw external shapes, and the Engine never does API-to-entity generation.
See: [`suite-architecture.md`](suite-architecture.md),
[ADR-0001](decisions/ADR-0001-canonical-internal-model.md).

**Change Plan / plan-hash** — The dry-run preview of a regeneration: a read-only plan
of additions/changes/migrations, plus a **plan-hash** computed over the manifest,
committed baseline, and output-package state. Apply is refused on any preview→apply
drift; destructive/unsafe evolution is classified and fails closed. See:
[`regenerate-maintain-suite-design.md`](regenerate-maintain-suite-design.md),
[`regenerate-maintain-model-design.md`](regenerate-maintain-model-design.md).

**Contract family** — A kind of upstream/downstream edge contract — e.g. REST/JSON,
fixed-width files, CSV/delimited, XML/XSD, SOAP/WSDL, staging handoffs. Each
family defines a common manifest shape and is implemented end-to-end as one
family (not via a universal parser).
See: [`edge-contract-expansion-roadmap.md`](edge-contract-expansion-roadmap.md),
[`edgecontracts/edge-contract-handoff-readiness-matrix.md`](edgecontracts/edge-contract-handoff-readiness-matrix.md).

**Descriptor / descriptor model (`ActionCardDescriptor`)** — The family-agnostic
contract the Engine derives from contract metadata so every edge-contract family
renders into the generated test console through one renderer; the renderer is
family-agnostic and only the descriptor varies. It is deterministic — the same
manifest yields the same card.
See: [`generated-app-standards/generated-app-test-console-ux-design.md`](generated-app-standards/generated-app-test-console-ux-design.md),
[ADR-0003](decisions/ADR-0003-family-agnostic-descriptor-model.md).

**Determinism** — The same manifest produces the same generated app
(byte-identical regeneration); no AI inference in the generation path, no silent
auto-apply, no name inference.
See: [`suite-architecture.md`](suite-architecture.md),
[ADR-0004](decisions/ADR-0004-deterministic-generation.md).

**Edge contract (upstream / downstream)** — A first-class integration contract the
generated app must keep honoring: **upstream** APIs (REST/JSON, SOAP/XML, XML/XSD)
and **downstream** handoffs (files, staging tables, messages). They live under
`upstream_interfaces[]` / `downstream_interfaces[]` in the manifest.
See: [`suite-architecture.md`](suite-architecture.md),
[ADR-0002](decisions/ADR-0002-dual-edge-contract-preservation.md).

**EdgeForge** — The **product**: a contract-preserving modernization platform for
legacy-heavy enterprise domains. It takes the upstream APIs and downstream
files/tables/messages a legacy system must keep honoring and generates a
replacement application that stays backward-compatible at the edges. (Module/CLI =
`appbuilder`.) See: [`suite-architecture.md`](suite-architecture.md),
[`appbuilder-context.md`](appbuilder-context.md).

**Engine** — This repo: the deterministic generator that turns a reviewed manifest
into a standalone Spring Boot app, and the **owner of the manifest/generation
contract**. See: [`suite-architecture.md`](suite-architecture.md).

**Evidence Trail** — The Studio export (v1.1) recording generated-artifact
provenance for accepted/edited decisions (`field`, `validation`, `rule`,
`cross_entity_rule`, `mapping`, `transform`). It preserves its v1.1 shape and adds
no new evidence types. See: [`appbuilder-context.md`](appbuilder-context.md),
[`evidence-trail-design.md`](evidence-trail-design.md).

**Generated app (standalone)** — A standard Spring Boot app the Engine emits, with
its own `README.md` and `Dockerfile`, independently buildable and carrying **no
runtime dependency** on EdgeForge, Studio, KS/KA, or MCP.
See: [`suite-architecture.md`](suite-architecture.md),
[ADR-0005](decisions/ADR-0005-generated-apps-standalone.md).

**Harness** — The Engine's generated-app validation gates / quality checks
(`appbuilder/harness/`). See: [`suite-architecture.md`](suite-architecture.md).

**Identity role + mode** — A manifest concept (`identity_roles`) classifying an
entity's persistence/identity semantics (e.g. `parent_reference`). Each carries a
`mode`: `metadata_only` (recorded, zero generated artifacts) or `active` (generate
or fail fast). On `origin/main`, `active` is **blanket-rejected for all identity
roles**; the `active` `parent_reference` mode is a **separate, in-flight track**
(Phase 2a, on a feature branch — not on `main`).
See: [`appbuilder-context.md`](appbuilder-context.md),
[`generated-app-standards/identity-role-engine-behavior-design.md`](generated-app-standards/identity-role-engine-behavior-design.md).

**Knowledge Assist (KA)** — The implemented, optional deterministic authoring
review and suggestion experience layered on KS. Studio can enable or disable KA;
its default-off posture leaves authoring functional without KS/KA. **No LLM or
provider integration exists in the suite today, and there is no provider enable
flag**; KS-B5 gates any future provider/model layer. See:
[`suite-architecture.md`](suite-architecture.md),
[`appbuilder-context.md`](appbuilder-context.md).

**Knowledge Server (KS)** — The separate repo providing **deterministic,
evidence-backed suggestions** during authoring (local-first; SQLite FTS5/BM25
retrieval). No LLM or provider integration exists in the suite today.
See: [`suite-architecture.md`](suite-architecture.md),
[`appbuilder-context.md`](appbuilder-context.md).

**Manifest (`app-definition.yaml`)** — The explicit, reviewed app-definition
package the Engine generates from (`manifest-v2`, `schema_version: "2.0"`).
Generation reads this manifest, not guesses from arbitrary files.
See: [`suite-architecture.md`](suite-architecture.md),
[`manifest-schema.md`](manifest-schema.md).

**Manifest schema** — The authoritative JSON Schema the Engine **owns**
(`appbuilder/schema/manifest-v2.schema.json`) and validates against at runtime.
Studio and any other upstream producer conform to it.
See: [`manifest-schema.md`](manifest-schema.md),
[`suite-architecture.md`](suite-architecture.md).

**Mode semantics** — Where a feature carries a `mode`: `metadata_only` = accepted
and recorded but emits **zero** generated artifacts; `active` = the Engine must
**generate the declared behavior or fail fast** — never a silent no-op or a
plausible scaffold passed off as complete.
See: [`suite-architecture.md`](suite-architecture.md).

**Ownership headers** — The per-file markers the Engine emits to distinguish
regenerated **generated**-owned code from scaffold-once **developer**-owned code, so
regeneration refreshes the former and never overwrites the latter. See:
[`regenerate-maintain-model-design.md`](regenerate-maintain-model-design.md).

**Plan-hash binding** — The safety rail binding a regeneration **apply** to the exact
previewed **Change Plan**, via a hash over manifest + committed baseline +
output-package state; if anything drifted between preview and apply, the apply is
refused. See: [`regenerate-maintain-suite-design.md`](regenerate-maintain-suite-design.md).

**Schema baseline** — The committed `db/schema-baseline.json` snapshot the Engine
compares against to compute **additive-only** delta migrations during regeneration,
keeping prior Flyway migrations immutable. See:
[`regenerate-maintain-model-design.md`](regenerate-maintain-model-design.md).

**Session** — In a shared, multi-user Studio deployment, an isolated unit of work with
its own server-owned workspace, KS database, and generated outputs; cross-session
read/write is rejected (see **Allowed roots / shared-mode isolation**). See:
[`data-governance-posture.md`](data-governance-posture.md),
[`engine-mcp-design.md`](engine-mcp-design.md).

**shared-specs** — An optional, **external** design-time contract document; not
required to import. The Engine owns the authoritative schema and producers conform
to it. See: [`suite-architecture.md`](suite-architecture.md),
[`upstream-integration-boundary.md`](upstream-integration-boundary.md).

**Studio** — The separate authoring/review UX repo that produces a human-reviewed
app-definition manifest conforming to the Engine's schema.
See: [`suite-architecture.md`](suite-architecture.md),
[`appbuilder-context.md`](appbuilder-context.md).

**Suite baseline** — A tagged cross-repo state of the suite (current: `v4.1.0` — the
feature-flagged regen-preview UX increment on the `v4.0.0` enterprise-readiness baseline;
Engine + Studio at `v4.1.0`, KS unchanged at `v4.0.0`), the reference point the living docs build from.
See: [`appbuilder-context.md`](appbuilder-context.md), [`../CHANGELOG.md`](../CHANGELOG.md).

**Target profile** — The runtime compatibility profile that drives generation
(`appbuilder/target_profiles/catalog.py`) — e.g. `springboot-legacy-compatible`,
`springboot-enterprise-postgres-java17`, `springboot-standard-enterprise`.
See: [`suite-architecture.md`](suite-architecture.md), [`../README.md`](../README.md).

**TestBench** — An optional, separate runtime/scenario proof harness (e.g.
Kafka-router runtime proof). The Engine has no dependency on it.
See: [`suite-architecture.md`](suite-architecture.md).
