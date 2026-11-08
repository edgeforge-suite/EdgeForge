# L5 Acceptance Run — Enterprise-Readiness Gate

> **Import-gate evidence — the runtime / integration capstone.** Where the static
> gates answer "is the code clean?" (G3 secrets, G4 SBOM, G7 compliance, G8
> security, C4 edge-contract honesty), the **L5 acceptance run** answers the
> holistic question: **does the whole suite — Engine + Studio + Knowledge Server —
> actually stand up together and uphold the enterprise-readiness safety bar,
> against real infrastructure?** This page records one **hermetic** run so a
> reviewer can **verify it was exercised, not asserted**: the exact command,
> topology, SHA-pin, the §8 must-never-happen checklist, per-leaf results, and the
> KS-pin provenance.
>
> **Status: GREEN (hermetic).** Run 2026-07-02. L5 is a **manual / pre-baseline**
> acceptance gate (not a per-PR CI check); the per-PR CI gates are G3 + the Engine
> test suite + the generated-app compile (see the [G10 index](README.md)).

## What it proves

In a single end-to-end run, on one host, with all three repos live:

- **The product output runs.** The Engine **generated** a combined edge-contract
  app, **compiled** it (`mvn`), and **ran it as a non-root Docker container** against
  a **real PostgreSQL** — exercising REST + inbound/outbound SOAP + file + XML/XSD —
  with **zero** Engine/Studio/KS/MCP/TestBench imports in the output app.
- **Multi-tenant safety holds.** Two concurrent Studio sessions could not see or
  overwrite each other's work; the Engine fail-closed contract rejected
  out-of-root / traversal / symlink / sibling-session writes; KS kept per-session
  stores isolated.
- **Maintain-over-time is data-safe.** Regeneration preserved developer code, applied
  **additive-only** migrations to real Postgres, kept prior Flyway migrations
  immutable, and **refused** destructive apply + plan-hash drift.
- **The §8 "must never happen" list is all-clear** (below).

## The run

- **Command (acceptance form):**
  `python scripts/smoke/l5_orchestrator.py --require-sibling-repos --require-services`
  — driven from the Engine repo; the orchestrator runs Studio + KS as subprocesses.
  `--allow-skipped-success` is **deliberately not used** for the gate.
- **Topology:** PostgreSQL `postgres:16-alpine` (container) · in-process mock SOAP
  (`scripts.smoke.engine_l5_smoke._MockSoapServer`, `in-process-v1`) · the generated
  app built to `edgeforge-suite-smoke-l5-generated-app:local` and run as a **non-root**
  container.
- **Host prereqs:** all three repos checked out at the SHA-pin commits below (each
  sibling repo's GitHub `main` at run time); Python 3.11 available to the
  orchestrator; Docker + Maven + JDK 17.

## SHA-pin (what passed)

| Repo | Commit | Notes |
|---|---|---|
| Engine (`appbuilder`) | `dabac1fbdfb8f3e1777992cec84aba147c7ba406` | A6 generated-output commit; includes generated-app credential fallback hardening |
| Studio | `7fcb28bf1dabd365ac88d213e3e35a6f0ee76079` | GitHub `main` at run time |
| Knowledge Server | `fb3a5e9e2508a82d20146f4bdbcfe027b1a14478` | GitHub `main` at run time |

`schema_version: 1.0`.

## §8 must-never-happen checklist — all clear

The eight §8 hard-fail conditions ([`suite-smoke-harness-design.md` §8](../suite-smoke-harness-design.md)), each **not** triggered:

| # | Hard-fail condition | Result |
|---|---|---|
| 1 | Build / compile failure of a generated app | **PASS** |
| 2 | Session bleed | **PASS** |
| 3 | Read/write outside the server-owned workspace root | **PASS** |
| 4 | Hidden / live KS or KA/AI (LLM) call when KA is OFF | **PASS** |
| 5 | Stale `plan_hash` accepted at apply | **PASS** |
| 6 | Destructive/unsafe migration silently emitted | **PASS** |
| 7 | Generated-app runtime failure on a required scenario | **PASS** |
| 8 | Absolute local path leak in Evidence Trail / any emitted artifact | **PASS** |

Condition **1** (build/compile failure) is evidenced by the `engine.runtime` leaf's
successful `mvn package`; the orchestrator's printed §8 block covers conditions **2–8**.
All eight: clear.

## Per-leaf results — all passed

| Leaf | What it exercised |
|---|---|
| `engine.runtime` | generate → `mvn package` → run as a **non-root** Docker container vs real Postgres; REST + inbound/outbound SOAP + file + XML/XSD; **no** Engine/Studio/KS/MCP/TestBench imports in the output app. |
| `engine.regenerate` | developer-owned service preserved; generated `ServiceBase` refreshed; prior Flyway migrations immutable; **additive** migration applied to real Postgres; **destructive apply + plan-hash drift refused**. |
| `engine.change_plan` | dry-run stable + read-only; `plan_hash` sensitive to manifest / baseline / package-state / developer-file / Flyway drift; destructive/unsafe classified; edge-contract impact surfaced. |
| `engine.apply_isolation` | `appbuilder apply` rejected shared-mode with no allowed roots; rejected out-of-root manifest/package paths; proved apply writes stayed under the resolved package path. |
| `studio.l5` | multi-session isolation · per-session outputs · shared-mode security · Engine fail-closed out-of-root (engine-tree / traversal / symlink / sibling-session rejected) · KA-OFF strict · combined edge-contract author→generate · **regen-preview approve-apply** with two isolated sessions. Orchestrator artifact scan: **no absolute-path leaks**. |
| `ks.l5` | per-session DB isolation · project-scoped + explicit cross-project-filter search no-bleed · allowed-root read-reject · shared-mode-requires-DB-path · no absolute-path leak. |

## KS-pin provenance — hermetic (pinned KS, not ambient)

The #253 orchestrator hardening makes the Studio→KS leaf launch the **pinned** KS
deterministically (it sets `EDGEFORGE_STUDIO_KS_REPO` + `EDGEFORGE_STUDIO_KS_COMMAND`
from the pinned KS repo and asserts the resolution). In this run:

- `orchestrator_pinned_ks`: `command = <python3.11>`,
  `command_from_edgeforge_ks_python: true`, `command_under_ks_repo: false`,
  `valid: true`.
- `studio_resolved_ks.repo` matches the pinned KS checkout and
  `studio_resolved_ks.command` matches the orchestrator-pinned Python command —
  the orchestrator's `_validate_studio_ks_resolution` gate passed.

So the Studio→KS isolation scenario used the **pinned** KS (`fb3a5e9`), not any
ambient / globally-installed copy.

> **Reproduction note (does not affect the proof above).** This recorded run used
> fresh GitHub-main Studio / KS checkouts and an explicit Python 3.11 command via
> `EDGEFORGE_STUDIO_PYTHON` / `EDGEFORGE_KS_PYTHON`. In that shape,
> `command_under_ks_repo` is **`false`** because the interpreter is intentionally a
> shared Python 3.11 binary, while `studio_resolved_ks.repo` still pins the KS code
> path to the recorded KS checkout. A reproducer using a repo-local KS venv may see
> `command_under_ks_repo: true`; either shape is accepted only when the command and
> repo match the orchestrator pin.

## Reproduce

1. Check out the **exact commits in the SHA-pin table above** — Engine `dabac1f`,
   Studio `7fcb28b`, KS `fb3a5e9` (full SHAs in the table) — **not `main`** (which
   moves on; pinning is what makes *this* recorded run reproducible). The run is driven
   from the Engine repo.
2. Use Python 3.11. Either a Python 3.11 venv per repo or a shared Python 3.11
   interpreter with the repos on `PYTHONPATH` is acceptable. Install as needed:
   Engine `pip install -e .`, Studio `pip install -r requirements.txt`, KS
   `pip install -e .`.
3. Export `EDGEFORGE_STUDIO_REPO`, `EDGEFORGE_KS_REPO`, `EDGEFORGE_STUDIO_PYTHON`,
   `EDGEFORGE_KS_PYTHON` (point the `*_PYTHON` vars at the Python 3.11
   interpreter or repo-local venv you installed with). The orchestrator sets
   `EDGEFORGE_STUDIO_KS_REPO` / `_KS_COMMAND` / `_ENGINE_MCP_COMMAND` +
   `EDGEFORGE_SHARED_MODE=1` itself.
4. From the Engine repo: `python scripts/smoke/l5_orchestrator.py
   --require-sibling-repos --require-services`. Needs Docker + Maven + JDK 17.
5. A genuine pass is `status: "passed"` with **no skips**; never accept `skipped` as a
   pass (don't use `--allow-skipped-success` for the gate).

## Honest notes

- **Manual / pre-baseline gate** — L5 is run on demand (here, a local host with
  Docker + Maven + JDK), not on every PR. The per-PR CI gates remain G3 + Engine
  tests + the generated-app compile.
- **Mock SOAP is in-process** (`in-process-v1`) — it exercises the generated app's
  SOAP in/out path without standing up an external SOAP server.
- **Historical scope:** at this recorded run, SOAP-envelope SAAJ hardening was
  still an inherited caveat. The generated-app acceptance leg now also gates
  byte-bounded first-parse rejection, transport-header preservation, exact HTTP
  400 faults, post-attack health, and valid-envelope recovery; a new full
  cross-repo L5 evidence run remains separate. Current caveats include own
  license, transitive-dependency disposition, and KS-B5 (gates any future
  provider layer; no LLM integration exists today) — see
  [G7](../compliance-and-portability.md) / [G8](../security-boundary-map.md) /
  [G10 open items](README.md#open--adopter-decides--post-import-nothing-hidden).

## See also

- [Handover-Evidence Index (G10)](README.md) — the front-door this artifact plugs into.
- [Compliance & Portability (G7)](../compliance-and-portability.md) ·
  [Security Boundary Map (G8)](../security-boundary-map.md) ·
  [Data-Governance Posture](../data-governance-posture.md).
- [Suite Smoke Harness — Design](../suite-smoke-harness-design.md) — the L0–L5 model
  this run is the top rung of.
