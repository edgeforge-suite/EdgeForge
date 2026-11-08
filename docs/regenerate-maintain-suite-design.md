# Regenerate / Maintain — Suite Cross-Repo Design (Change Plan contract, Studio & KA)

> **Status:** Design / docs only — no code in this PR. Suite-level (Engine + Studio + KS/KA)
> companion to the Engine-internal [`docs/regenerate-maintain-model-design.md`](regenerate-maintain-model-design.md).
> Reconciles the Codex-Suite cross-repo design debate (2026-06-14).
>
> **Scope.** The 3 mandatory repos — **Engine** (`appbuilder`), **Studio**, **KS/KA**.
> Generated apps are covered as Engine output. TestBench and shared-specs are out of scope here.
>
> **What this adds.** The Engine-internal doc defines *how the Engine regenerates safely*
> (developer-owned layer §4, additive DB §5, legacy adoption §4.6, destructive flagging §5.5).
> It does **not** define the **user-facing workflow** — load an existing project → detect it is
> an older project → see what changed (added / removed / modified) → approve → regenerate —
> which spans **Studio** (authoring/UX) and **KS/KA** (advisory). This doc specifies that
> cross-repo layer: the **Change Plan contract**, who owns what, the failure modes, and the
> sequencing against Studio's in-flight multi-session work.
>
> **Last updated:** 2026-06-14.

---

## 1. The two principles

**P1 — Single source of truth = the Engine.** Only the Engine knows what it will actually emit:
ownership headers, generated-vs-developer file policy, Flyway migration numbering, baseline diff,
destructive fail-closed rules, and edge-contract emitter behavior. Studio and KA **consume** the
Engine's authoritative output; they must **never re-derive** the diff (it would drift immediately).
Studio may compute lightweight UI hints, but they must be labeled non-authoritative — the gate is
always an Engine-produced plan. KA/KS is advisory only: it explains impact and cites source
artifacts, but it never decides migration safety.

**P2 — Plan-hash binding (non-negotiable safety rail).** The core risk is not the split; it is
**preview/apply drift** — Studio previews one thing, then the manifest / baseline / package changes,
and the Engine regenerates something else. The rail:

1. Studio asks the Engine for a **dry-run Change Plan** → receives a `plan_hash`.
2. The user reviews and approves *that* plan.
3. Studio calls regenerate with the `approved_plan_hash`.
4. The Engine **recomputes the plan and refuses to apply if the hash changed** — including any
   change to the **output-package state** (a hand-edited generated file, a new/edited
   developer-owned file, generated-file divergence, or a Flyway migration added on another
   branch), not just the manifest or baseline.

No regenerate/apply path may run without a still-valid approved plan hash. The `plan_hash` binds
the inputs **and** the current output-package state (see `package_state_hash`, §3).

## 2. Roles

| Capability | Owner | Notes |
|---|---|---|
| Compute the authoritative delta + migration safety + edge-contract impact | **Engine** | The only component that can act on the diff |
| Produce + publish the versioned **Change Plan** (dry-run) | **Engine** | The cross-repo contract |
| Regenerate safely (preserve developer files, additive migrations, fail-closed) | **Engine** | Per the Engine-internal doc §4–§5 |
| Emit + read the in-package `db/schema-baseline.json` | **Engine** | Authoritative previous state |
| Store a durable, hashed, **managed copy** of the generated package/baseline | **Studio** | A Studio-owned artifact, never an external path — see §4 |
| Render the Change Plan; gate destructive/manual items; require explicit consent | **Studio** | The "highlight" UX |
| Bind an existing generated package to a Studio project | **Studio** | Import / relink |
| Enforce plan-hash binding at apply | **Engine + Studio** | Studio sends `approved_plan_hash`; Engine validates |
| Advisory explanation of impact (cite docs/contracts/mappings) | **KS/KA** | Optional deterministic advisory only; may be enabled or disabled, but never decides safety or mutates the plan. No LLM/provider integration exists; KS-B5 gates any future provider/model layer. |

## 3. The Change Plan contract

The Engine publishes a **versioned** Change Plan — not an informal JSON blob. Minimum fields:

- `change_plan_schema_version` (semver; consumers reject unknown **major**, tolerate additive **minor**)
- `engine_version` (commit / build id)
- `manifest_hash`, `baseline_hash`, `target_profile`
- `generated_app_id` / bounded-context / package identity
- `package_state_hash` — binds the **current output-package state** the plan was computed
  against: the developer-owned file inventory + contents, ownership headers, any generated-file
  divergence (hand-edits to `generated`-owned files), and the Flyway migration inventory
  (high-water mark). This is what makes drift detection complete.
- `plan_id` / `plan_hash` — `plan_hash` is computed over `manifest_hash` + `baseline_hash` +
  `package_state_hash` + the deltas/classification, so it transitively binds the inputs **and**
  the output-package state
- entity / field / contract **deltas** (added / removed / modified)
- **migration classification** per change: `additive` | `unsafe` | `destructive`
- **edge-contract impact** (see §5)
- **required manual actions**
- **warnings**

**Consumer compatibility.** Studio and KS reject unknown major versions and tolerate additive minor
fields (e.g. Studio supports `1.x`, rejects `2.0`).

**Surfaces.** The Engine exposes the dry-run as a CLI / API / MCP shape (the same way the Engine is
already invoked); the apply/regenerate surface requires `approved_plan_hash`. The concrete signatures
are now **fixed and L5-proven** — the dry-run is `appbuilder plan` and the apply is
`appbuilder apply --approved-plan-hash` (pinned in §11) — invocable from Studio's server-owned,
per-session Engine-invocation path.

## 4. Older-project detection (three distinct version concepts)

Keep these three separate — conflating them is a known pitfall:

1. **Studio project schema version** — the shape of Studio's saved authoring state (Studio's own migration chain).
2. **Generated-app schema baseline** — the emitted DB/code state of a previously-generated app (`db/schema-baseline.json`, Engine-authoritative).
3. **Manifest schema version** — the package contract the Engine accepts.

**Engine-side detection** (already in the Engine doc's unified flow §6): a target package with
`schema-baseline.json` + ownership headers → *regenerate* mode; without them → *greenfield*; legacy
(EdgeForge-generated but headers/baseline absent) → *adopt* per §4.6.

**Studio-side reference must be durable.** A bare path pointer is too weak — paths move, exports get
copied, multi-session workspaces are cleaned up. Studio stores, in project state:

- `last_generated_package_ref`
- `generation_run_id`
- `manifest_hash`, `baseline_hash`
- a **managed copy** of the generated package + baseline, stored as a durable Studio-owned
  project artifact under the SessionStore / workspace (never just an external path pointer —
  paths are fragile under export/move and multi-session workspace TTL)

The in-package `db/schema-baseline.json` remains authoritative. If Studio has only a manifest revision
but no generated package/baseline, the Engine can show a **manifest-diff preview** but **cannot** safely
produce DB migration deltas.

## 5. Destructive & edge-contract impact (Engine-owned)

The Engine-internal doc §5.5 already flags destructive **DB** changes. This doc makes **edge-contract
impact a first-class part of the Change Plan** — it affects generation safety, so the Engine owns the
deterministic check; KA only explains it. The Engine must detect:

- a removed canonical field used by an **upstream ingestion mapping**
- a removed canonical field used by a **downstream layout / XML / SOAP mapping**
- type / length / nullable changes that break file layouts or XML/XSD serialization
- a **field rename** read as drop+add unless explicit rename metadata exists (§9)
- a staging-DDL checksum change
- SOAP / XML root / namespace / path impact
- Evidence-Trail metadata path changes

**Resolved disagreement:** KA must **not** be the only place contract breakage is detected. The Engine
owns the deterministic safety classification; KA adds advisory narrative ("this fixed-width column will
no longer be populated", "this SOAP response mapping will break"). A change can be **DB-additive but
contract-destructive** — the Change Plan classifies the two axes independently.

## 6. Failure modes & required handling

| Failure mode | Handling |
|---|---|
| **Plan/apply race** (manifest/baseline changed after preview) | Plan-hash binding (§1, P2) — Engine refuses on hash mismatch |
| **Branch migration collision** (two branches both author `V3__…`) | Flyway migration inventory is in `package_state_hash`; the plan-hash recompute detects the next-version mismatch and requires rebase/regenerate |
| **Rename ambiguity** (no stable field IDs → rename looks like drop+add) | Treat as destructive unless explicit rename metadata exists |
| **Package relocation** (Studio path pointer breaks after export/import) | Store `baseline_hash` + a managed artifact copy, not only a local path |
| **Edited generated-owned file** | `package_state_hash` covers generated-file divergence, so the plan-hash recompute catches it; warn / fail before overwrite (Engine doc §4.6 protect-hand-edited rule) |
| **Deleted developer file** | Policy (§9): re-scaffold if absent (P1b default), or warn that a developer-owned file was removed |
| **Target-profile drift** (baseline under profile A, regen under profile B) | Plan flags the profile change as unsafe |
| **Edge-contract-only break** | Engine classifies DB + contract axes independently (§5) |
| **Multi-session workspace TTL** deletes the package baseline | Studio stores the baseline as a **managed project artifact**, not a TTL'd workspace temp |
| **Stale KA advisory** (advice computed against an old plan hash) | KA advice is invalidated when the plan hash changes |

## 7. Sequencing vs Studio multi-session

The boundary that keeps the two tracks stable: **multi-session infrastructure is independent and
proceeds now; the regeneration *preview* is the coupled feature and waits for the Change Plan contract.**
Reconciled order (both Codex threads + this thread agree):

1. **Engine P1a** ✅ merged (ownership-aware sink, PR #238) → **Engine P1b** (service generation-gap) — in flight; contract-free, independent.
2. **Engine Change Plan contract design** (this doc) — design only, no implementation.
3. **Engine P2** — `db/schema-baseline.json` emission + regen detection (Engine doc §5.2, §9). **Must precede the full dry-run**, because the DB-delta Change Plan is diffed against the baseline.
4. **Engine dry-run implementation** — produces the full Change Plan (DB deltas + migration classification + edge-contract impact), no apply yet. Requires the baseline from step 3. *(A manifest-only preview can exist earlier, but per §4 it cannot produce DB migration deltas — so the full dry-run is sequenced after baseline emission, not before.)*
5. **Studio multi-session** — SessionStore / workspace roots / server-owned package paths (Studio P2-2b router re-key + global-backdoor removal → P2-2c/2d server-owned paths). **Independent of the regenerate work; proceed in parallel.**
6. **Studio regeneration binding** — project stores the durable managed package/baseline copy (§4).
7. **Studio preview UI** — feature-flagged; calls the Engine full dry-run; **no duplicated diff logic**.
8. **Engine P3** — additive migrations + destructive fail-closed + **apply-with-approved-plan-hash**.
9. **Studio apply flow** — approve plan hash, call regenerate, show output summary.
10. **KS/KA advisory** — optional plan explanation + impact citations, **after the schema stabilizes**.

**Hard rule:** the Studio preview (step 7) needs **both** Studio SessionStore/workspace (step 5) **and**
the Engine full dry-run (step 4) — parallel prerequisites; neither blocks the other until they meet.
Studio must **not** add baseline-pointer / Change-Plan / regen-preview / Engine-dry-run code during the
multi-session infrastructure slices.

## 8. Per-repo build responsibilities

**Engine**
- Ownership headers + developer-file preservation (P1a ✅ / P1b).
- Emit + read `db/schema-baseline.json`; diff baseline → manifest-derived schema.
- Produce the versioned Change Plan; dry-run command / API / MCP.
- Detect destructive/unsafe DB changes **and** edge-contract impact (§5).
- Detect developer edits to generated-owned files; handle legacy packages (§4.6).
- Regenerate/apply requiring an approved `plan_hash`; fail closed on baseline mismatch or changed hash.

**Studio**
- Store the durable generated-package/baseline reference in project state (§4); import/bind an existing package.
- Call the Engine dry-run; render the Change Plan with clear additive/destructive labels; require explicit acknowledgement for destructive/manual items.
- Prevent apply if the plan hash changed; preserve KA-OFF cleanliness.
- Make all of the above **per-session and workspace-root aware** (depends on the multi-session foundation).

**KS/KA**
- Optional ingestion / indexing of Change Plan artifacts; deterministic advisory over impacted docs/contracts/mappings.
- No plan mutation, no migration generation, no cross-session leakage. Deterministic KS/KA remains
  optional and advisory; no LLM/provider integration exists, and KS-B5 gates any future
  provider/model layer.

## 9. Open decisions

- **Rename metadata.** Without stable field IDs, a rename is indistinguishable from drop+add (destructive).
  Decide whether to add explicit rename hints to the manifest / Studio authoring (recommended) so renames
  can be classified as safe.
- **Deleted developer file policy.** P1b's scaffold-once re-scaffolds an absent developer file by default.
  Ratify: re-scaffold silently vs warn-on-removed. (Recommendation: re-scaffold **and** emit a Change-Plan warning.)
- **Change Plan surface shape — RESOLVED.** The dry-run and apply are **CLI** (`appbuilder plan` /
  `appbuilder apply --approved-plan-hash`), invoked from Studio's server-owned, per-session path; both
  `--manifest` and `--package` resolve through the per-session allowed-roots fail-closed contract. Pinned in §11.

## 10. Verification

- A Change Plan produced by the dry-run validates against the published schema; consumers reject a bumped
  major version and tolerate an added minor field.
- Apply refuses when `approved_plan_hash` ≠ a freshly recomputed plan hash (drift test) — including
  drift in the **output-package state**: a hand-edited generated file, a new developer file, or a
  Flyway migration added on another branch all invalidate the approved hash.
- A destructive field change and an edge-contract-only break are both classified correctly and gated.
- An older project is detected via `schema-baseline.json`; a project with only a manifest revision yields
  a manifest-diff preview but no DB migration deltas.
- Studio renders the plan without re-deriving the diff; two sessions never share regeneration state.

## 11. Apply contract (fixed) — CLI surface + L5 regen-apply scenario shape

> **Pinned 2026-06-21**, after the v4.1.0 regen-preview UX landed. Both shapes below were previously
> deferred (§3 "Surfaces", §9). Leaving them unpinned cost **three cross-repo L5 mismatches** during the
> v4.1.0 cycle — the scenario *name*, the per-session *detail shape*, then the *artifact-root key path*.
> Changing either shape now requires updating the **Studio leaf and the Engine orchestrator in lockstep**.

### 11.1 Apply CLI surface
Apply is a CLI command, invoked from Studio's server-owned, per-session Engine path:

```
appbuilder apply --manifest <app-definition.yaml> --package <generated-app-dir> \
                 --approved-plan-hash <hash> [--generation-run-id <id>]
```

- Both `--manifest` and `--package` resolve through the per-session **allowed-roots fail-closed**
  contract (`EDGEFORGE_MCP_ALLOWED_ROOTS` per session; hard-fail under `EDGEFORGE_SHARED_MODE` with no
  roots). Apply writes **only** under the resolved package dir.
- Apply **refuses** when `approved_plan_hash` ≠ a freshly recomputed plan hash (drift; §10).
- Changes are **additive-only**; prior Flyway migrations are immutable; destructive changes fail closed
  (Engine-internal mechanics in [`regenerate-maintain-model-design.md`](regenerate-maintain-model-design.md)).

### 11.2 L5 regen-apply acceptance scenario shape
The suite L5 gate exercises apply end-to-end as the Studio scenario **`regen-preview approve-apply`**,
run as a **two-session** (alpha/beta) isolation test. The Engine orchestrator validates this exact
detail shape, so the Studio leaf and the orchestrator must agree on it:

- **Top-level:** `ok`, `ka_off_silent`, `ks_calls`, `distinct_workspaces`, `distinct_generated_outputs`,
  `distinct_managed_packages`, `alpha_under_workspace`, `beta_under_workspace`, `alpha_cross_bleed`,
  `beta_cross_bleed`, `alpha` (object), `beta` (object).
- **Per session (`alpha`, `beta`):** `applied`, `workspace_root`, `export_package`, `generated_output`,
  `initial_managed_package`, `refreshed_package`, `plan_hash`, `new_migration_count`, `new_migrations`,
  `migration_contains_field`, `migration_needle`, and `apply_summary` — the Studio apply-service summary
  sub-object holding **apply metadata only**: `generation_run_id`, `managed_package_ref`, `manifest_hash`,
  `baseline_hash`, `baseline_present`, `status`. On a **successful apply** `apply_summary.status` is
  **`"none"`** (the post-apply regen state — nothing pending once the baseline is refreshed); apply success
  itself is signalled by the sibling **`applied: true`**, not by `apply_summary.status`. It **carries no
  artifact paths** — the per-session paths above are top-level siblings of `apply_summary`, not nested inside it.
- **Orchestrator asserts:** KA-off silence; distinct workspaces / outputs / packages; per session —
  apply succeeded (sibling `applied: true`, with `apply_summary.status == "none"`), ≥1 new migration,
  the migration carries the new field, and `refreshed_package` /
  `generated_output` resolve under that session's `workspace_root`; and no cross-session bleed. The §8
  checklist additionally rejects an apply whose `--manifest` / `--package` resolves outside an allowed root.
- **Artifact-leak scan** keys off the **session-level** paths (`alpha.export_package`,
  `alpha.refreshed_package`, `alpha.workspace_root`, `alpha.generated_output`, `alpha.initial_managed_package`,
  + `beta.*`) — all guaranteed present. Because `apply_summary` is metadata with **no paths**, it is **not**
  an artifact-root source: never require or path-scan `apply_summary.*`. Validate its metadata fields
  (`status`, `generation_run_id`, `managed_package_ref`, the hashes, `baseline_present`) separately.
- **Fixture fidelity (lesson).** Unit-test fixtures for this payload **must mirror the real Studio emitter**.
  In the v4.1.0 cycle a hand-written orchestrator fixture invented a path-rich `apply_summary`, so the change
  passed 27 unit tests yet failed the real hermetic run — green-but-lying. Derive the fixture from (or assert
  it against) `regen_preview.py`'s real `summary` shape.

Engine orchestrator: `scripts/smoke/l5_orchestrator.py` (regen-apply validation + artifact scan).
Studio leaf: `tests/smoke/l5_driver.py::_regen_apply_isolation`. Feature-flagged
(`EDGEFORGE_STUDIO_REGEN_PREVIEW_ENABLED`), off by default.

---

*This is the suite/cross-repo half of the regenerate/maintain model. The Engine-internal mechanics
(developer-owned layer, additive DB evolution, legacy adoption, destructive flagging) live in
[`docs/regenerate-maintain-model-design.md`](regenerate-maintain-model-design.md); the determinism
contract is [`docs/decisions/ADR-0004-deterministic-generation.md`](decisions/ADR-0004-deterministic-generation.md).*
