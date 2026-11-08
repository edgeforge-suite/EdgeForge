# M3 — Change-Aware Suite Verification Pack: Design

> **Status:** DESIGN **rev-8** — absorbs **Engine PR #280** (generated-app standalone independence in CI,
> merged 2026-07-27), which landed after rev-7 and was never swept back in. Corrects two now-false
> current-state statements in §1.4, adds the sixth named-result producer to §1.2, adds **two-stage AC10** (reuse
> proven on `engine.runtime` by sentinel substitution against an exact declared invocation count, with
> no-duplication left honestly **review**-graded per §10), and records **two maintainer decisions taken**:
> registration granularity **G-A coarse** (§14.5) and archetype coverage **H-A representative CRUD**
> (§14.6). **V1a is unblocked** and enumerates exactly one #280 entry. **No new allowlisted unit or
> `unit_type` is required** — `engine.runtime` and `engine.regenerate` both already consume the verifier,
> though only `engine.runtime` binds #280 coverage in v1; V1a adds typed `reuse_probes` metadata to the
> existing unit (§0.8). rev-7's V-ACT gating and rev-6/rev-5 structure stand.
> **Tracker:** `M3-change-aware-verification-pack` (`docs/tracker/suite-tracker.json`, `depends_on:
> ["suite-smoke-harness"]`); roadmap must-have **M3** (`docs/enterprise-readiness-roadmap.md:137`),
> order `M1 → M5a → M2/M6 → M3 → M4 → M5b` (`:172`).
> **Hard rule (from the tracker):** extend the delivered **L0–L5 harness** — do **NOT** create a second
> harness. rev-4 enforces this at **two honest grades** (§3.5, §10): (a) *machine* — every
> scenario's **`execution_unit` must be an allowlisted invocation adapter/root** (§3.5a), and non-runner
> ops a **closed predicate set**; a new unit/root requires an explicit design-gate change to the allowlist;
> (b) *review* — that the referenced runner/validator code contains **no product assertions** is a
> code-review property the registry cannot inspect. rev-3's flat "structural / no schema slot" claim was
> an over-grade (§0.4 #2).
> **First milestone (post-flip):** retain the checklist used by Studio PR #280 as a repeatable
> default-on regression/evidence profile (§9). PR #280 completed the flip and removed the runtime
> rollout flags; §0.9 records the narrow amendment required before VS0/VS1/V-ACT can build.
> **Grounding (all three repos):** Engine `origin/main` @ **`663164a`** · Studio @ **`42cea31`**
> (refreshed from `553c7b0`; the L5/CI files are unchanged — provenance update, not a factual change) ·
> **KS @ `fb3a5e9`**. Everything not cited is **PROPOSED**.
> **Redlines honored:** no second harness · deterministic + synthetic fixtures only, no scenario network
> dependence · a skipped scenario is never a pass · additive tooling — no Engine/Studio/KS runtime or
> manifest change.

> **Bounded prerequisite delivered (2026-09-12):**
> [`suite-release-candidate.json`](suite-release-candidate.json) is the sole active
> Engine/Studio/KS candidate-selection record, and
> [`verify_suite_pairing.py`](../scripts/verify_suite_pairing.py) provides a separate read-only
> clean-pin preflight. This selects candidate revisions only. It does not implement M3's registry,
> affected-set runner, resolved-run identity, evidence, scheduling, or acceptance decision, and the
> candidate remains pending until coordinated proof is recorded.

---

## 0. Correction log

*(§0.1–0.2 = rev-1 → rev-2; §0.3 = rev-2 → rev-3. Kept in full so each rev's errors stay on the record.)*

Codex's first audit **confirmed** the current-state spine — runner counts/fixtures/helper lines, Studio L2
per-PR with two non-empty collection guards, Engine workflows carrying no smoke execution, the
path-filtered compile workflow, the skip fold + discovery-only skip-success, and the hand-authored L5
evidence page. It **refuted four interpretive claims and found ten unimplementable/untruthful mechanics**.
All are accepted; none are reopened.

### 0.1 Refuted claims (my errors)
| rev-1 claim | Corrected fact |
|---|---|
| Studio driver emits a **`name`** field | **WRONG.** `_scenario(...)` returns `{"scenario": name, "ok", "detail"}` (`l5_driver.py:400`); KS emits `{"checks":[…]}` (`run_ks_l5_isolation.py:64-67`). The JSON keys are `scenario` / `checks`, not `name`. |
| The expected-sets are **"an exact registry"** | **WRONG.** `_validate_studio_payload` computes `missing = EXPECTED_STUDIO_SCENARIOS - names` and errors only on **missing** (`l5_orchestrator.py:522-533`). **Extra and duplicate results are not rejected.** It is a presence check, not an exact contract. |
| The expected-sets are **the only place names are validated** | **WRONG.** Names are also hardcoded in `STUDIO_REQUIRED_ARTIFACT_ROOTS` (`:87`), `_build_hard_fail_checklist` (`:901` — `"multi-session isolation"`, `"per_session_db_isolation"`, engine step-substrings like `"apply out-of-root manifest rejected"`), `STUDIO_NO_LEAK_SCENARIOS` (`:65`), and the regen-apply validators. V1 must route **all** of these. |
| Three-repo grounding is **complete** | **WRONG — KS was never pinned.** rev-2 pins KS @ `fb3a5e9` and grounds against `scripts/run_ks_l5_isolation.py`. |

### 0.2 Unimplementable / untruthful mechanics (all fixed)
| # | rev-1 mechanic | Why it failed | Fixed in |
|---|---|---|---|
| 1 | `entry_point.ref = "l5_driver:multi-session isolation"` as a callable | It is a **result label**, not an entry point. Studio runs **all 8** scenarios in one `run_studio_l5_acceptance` call (`:44-103`); KS runs **all 6** in one script (`:35-63`). Execution granularity ≠ scenario granularity. | §3.2 (`runner_ref`/`execution_unit`/`verdict_selector` + fan-out) |
| 2 | "The registry becomes the single source of truth" | Only if **every** name consumer (§0.1 row 3) routes through it, rejecting missing **+ extra + duplicate**. rev-1's V1 touched only two constants. | §3, §4, V1 |
| 3 | "Cross-repo drift caught **per PR**" | **False.** A repo can rename a scenario **and** update its own manifest in one PR; its CI passes green while the central registry stays stale. Only a co-checkout run catches it. | §4 (intra vs cross, honestly) |
| 4 | Commit the raw report + pin manifest "unchanged" | They embed absolute paths (`"root": root.as_posix()` `:239`; `REPO_ROOT.as_posix()` `:852+`) — which **harness §8:240 makes a hard fail** in any committed artifact, and which the orchestrator already **scans for** (`_scan_studio_artifacts_for_absolute_paths:337`, `LOCAL_PATH_LEAK_MARKERS:102`). rev-1 proposed committing exactly what the harness rejects. | §8 (raw-retained + sanitized-committable, gated by that scanner) |
| 5 | Scheduler compares to "the last run's pin manifest"; "catches strictly more"; "can produce no new information" | Persistence location **undefined**; no `last_attempted` vs `last_successful`, so a failing unchanged SHA may never rerun. And "no new information" **contradicts** rev-1's own admission of mutable image tags + Maven drift. | §6 |
| 6 | Affected-set selection by changed paths | No **rename** handling (only new path seen), no glob semantics, and "empty selection = error" collides with legitimate **doc-only** changes. | §5 |
| 7 | "Inherit the `:235` status fold" | The fold knows `passed/skipped/failed` only. `missing` (registered-but-unreported), and **attestation completeness**, are new verdicts it cannot express. | §3.6, §7 |
| 8 | Item 1 "green checks API"; item 4 "driven through the refreshed UX" | A green checks response ≠ PR-01–23 **merged** (needs merge-ancestry + required-check conclusions at the pin). Studio helpers use FastAPI **`TestClient`**, proving the **backend** flow — **not** the rendered UX. | §9 |
| 9 | A generic `meta-check` entry kind | Arbitrary code hides behind it → a second harness by the back door (rev-1 flagged the risk; Codex confirmed it is real). | §3.5 (closed declarative ops) |
| 10 | Replay + slicing | **No slice implements replay** (V3 listed only `full`/`flip-set`; V5 is scheduler). "Expected outputs" home undocumented; roadmap/tracker cadence edit unaddressed. | §7, §12, §14 |

### 0.3 rev-2 → rev-3 (modeling + buildability — the six residuals)
Codex's second re-review **confirmed 8 rev-2 fixes** and found six that survived:
| # | rev-2 mechanic | Why it failed | Fixed in |
|---|---|---|---|
| 1 | `runner_ref: "…l5_driver.py::run"` + "V1 lint rejects unresolvable `runner_ref`" | **Wrong callable** — it is `run_studio_l5_acceptance` (`l5_driver.py:44`); KS is `run_ks_l5_isolation` (`:35`). And **V1 is Engine-only**, so it cannot resolve/validate a Studio/KS callable that isn't checked out. | §3.1 (real names), §4 (V1 validates *form*; existence checked where the repo is present) |
| 2 | One `result_selector` represents every consumer | **Five structurally different contract kinds** cannot be one selector: emission-presence (`EXPECTED_*`), **structural** artifact-root keys (`_validate_studio_artifact_root_contract` → `_json_path_get(detail, path)`), **derived** composite validation (`_validate_studio_regen_apply_contract:569`), **aggregating** hard-fail controls (`_build_hard_fail_checklist` via `_all_known:972`, three-valued over scenario+KS+step sources), and reused aliases. | §3.1/§3.4 (layered model: `verdict_selector` + referenced `contracts[]` + a separate `hard_fail_controls[]`) |
| 3 | Per-repo lint asserts "driver emission == manifest" | **Unbuildable in isolated CI** — `l5_driver` imports `_post_generate`/`run_engine_fail_closed_isolation` from `l4_driver`, which invoke the real Engine; Studio CI cannot stand up siblings to *observe* emissions. Needs a **static declaration table** both the driver and the lint read. | §4 (static `scenario_manifest.py`; lint is static, not observational) |
| 4 | The Studio scanner is a general commit gate | **Overstated.** `LOCAL_PATH_LEAK_MARKERS` (`:102`) is **three macOS markers** (the `"/" + "Users/"` home root, `private/tmp/`, `var/folders/`) over **generated-app artifact trees** — it misses Linux (`/home/`, `/tmp/`, `/root/`) and Windows entirely. On a Linux runner those markers catch nothing. | §8 (bundle is path-free **by construction** + M3's own general verifier; the Studio scanner is a complementary macOS-artifact check, not the gate) |
| 5 | "Identical SHAs/registry/profile ⇒ identical verdicts" | **Contradicts its own `determinism_bounds`** (mutable tags, Maven) and **omits inputs** — affected-selection input and the declarative-predicate GitHub state also determine verdicts. | §7 (bounded replay + full key incl. snapshotted predicate results) |
| 6 | V3 delivers the flip milestone | V3 is the **Engine** runner; `studio.flip-e2e-flag-on` is **new Studio code** that V3 can only *consume*. No Studio slice, no landing order. | §9/§12 (explicit Studio flip-scenario slice + order) |

### 0.4 rev-3 → rev-4 (honesty + internal consistency — five blockers + polish)
Codex's third re-review **confirmed rev-3's five fixes stuck** and found the design still not gate-ready.
None are direction resets; all are truth-in-the-design.
| # | rev-3 flaw | Corrected fact | Fixed in |
|---|---|---|---|
| 1 | The branch **fails its own CI** | The doc contained the contiguous macOS home literal at 3 sites; `repo-hygiene.yml:17-24` greps `"/" + "Users/"` and **both jobs were red**. A path-leak design that trips the path-leak gate is self-refuting. | rev-4 writes the marker split, as the source does; §8 makes the irony the point |
| 2 | "No second harness = **structural**" | **Over-graded.** `runner_ref` is arbitrary `repo:path::callable`; V1 checks only form; no allowlist; the registry cannot inspect code semantics. | §3.5/§10: a **machine allowlist** of runner roots (unit identity, machine-enforced) **+** honest **review**-grade for "no product assertions" |
| 3 | Reconcile full registry ⟺ per-repo manifest, exactly, both directions | **Set-boundary mismatch.** The registry spans L0–L5 (incl. `pytest-outcome`, engine steps); a repo's declaration is only its L5 emitted labels. And Studio/KS **still hardcode** the labels in tests (`test_l5_acceptance_smoke.py:61-77`; `test_l5_isolation_helpers.py:15-22`) — the declaration isn't yet the source. | §4: **contract-typed declaration sections**, reconciled **scoped by (type, owner_repo)**; V2 makes the existing tests **consume** the declaration |
| 4 | VS1 order | **Self-contradiction** — §9 said `VS1→V1→V2→V3`, §12 said `V1→V2→(VS1∥V3)`; and VS1 can't declare before V2 builds the seam, nor can V1 register a scenario Studio hasn't emitted. | §9/§12: one sequence **V1 → V2 → VS1 → V-ACT (registry activation) → V3**, identical in both |
| 5 | Replay key called "**complete**" | **Still omits** topology (image digests), toolchain (Python/JDK/Maven), run config (invocation flags), and predicate provenance (PR/merge SHA, check-run identity/time). The pin manifest already records topology by **tag** (`:852-881`). | §7: bind+publish the **resolved run manifest**; a differing rerun is an explicit **`replay_drift` non-pass**; drop "complete" for "the resolved manifest" |

**Smaller fixes folded in:** flag-state OFF/ON traceability (§9); re-key the derived validator by stable id + decide the no-leak aliases (§3.4); define `full` = `run_modes ∋ full` + reject trigger/no-impact glob overlap + RFC-3339/enum/resolvable attestation formats (§5, §9); and truth-drift cleanup (duplicate Level-2 paragraph; `l5_driver.run()`→`run_studio_l5_acceptance` in §0.2; drop "rev-2 reuses this as the commit gate"; stop citing smoke-design §14 as *proof of delivery* — that section labels the slices proposed, the **scripts' existence** is the proof; platform stated as **§14-undecided**, which is *why* the verifier must be general).

### 0.5 rev-4 → rev-5 (owning-repo alignment — six contract-semantics gaps)
Engine/Studio/KS each reviewed rev-4 from their own repo and returned **Aligned-with-concerns** — no
misalignment, no concept objection ("the architecture is sound" — Engine). rev-5 closes the six concrete
gaps they raised; all verified at source.
| # | Gap (repo) | Corrected fact | Fixed in |
|---|---|---|---|
| 1 | **`runner_ref` bypasses the Engine adapters** (Engine) | A raw `repo:path::callable` skips `_run_studio_l5` (`:285` — sets `EDGEFORGE_SHARED_MODE=1`, `_pinned_ks_python`, `_engine_mcp_python`, provenance env) and `_run_ks_l5` (`:375` — pinned `EDGEFORGE_KS_PYTHON`). Those adapters **are** the pinned-interpreter / shared-mode / provenance enforcement. | §3.1 + §3.5a: `execution_unit` resolves **through the adapter**; `approved_execution_units` = the adapters, not leaf callables |
| 2 | **No `not_selected` state** (Engine) | affected/flip-set runs intentionally omit scenarios; rev-4 had only `passed/failed/missing/skipped`, so an omitted scenario risks reading as `missing` (⇒ fail). | §3.6: a distinct **`not_selected`** state — neither pass nor fail, and **never** an input to a `hard_fail_controls` category |
| 3 | **Set equality can't catch duplicates** (KS) | `test_l5_isolation_helpers.py:15` compares `{names} == {names}` — a **set**, which silently accepts a duplicate emitted name; "exact incl. duplicate" needs **multiset** equality. | §4: reconciliation + the routed tests use **ordered/multiset** comparison |
| 4 | **No-leak aliases vs exact reconciliation** (Engine) | `STUDIO_NO_LEAK_SCENARIOS` (`:65-69`) is **3 accepted labels for one signal**, not 3 scenarios. | §3.4: **one** `no-leak` contract with an explicit `accepted_aliases` set (exact-but-alias-aware) |
| 5 | **Regen re-key slice was ambiguous** (Engine) | rev-4 implied both V1 and V2 re-key `_validate_studio_regen_apply_contract`. | §3.4/§12: **assigned to V2**, stated once |
| 6 | **VS1 CI env + incomplete id list** (Studio) | VS1's author→generate→export→compile needs the **co-checked-out L5 env** (Engine+JDK+Maven), *not* isolated Studio CI; and rev-4 showed only **3** Studio ids by example. | §9/§12: VS1 = an **L5-env** slice; V1a enumerates all **8** Studio + **6** KS ids |

**Clarifications tightened** (Engine): byte-identical L5 report is an explicit **AC1 test**, not a
promise; image/toolchain **identity** = digests resolved at run, not tags (§7); manual-attest
`decision` enum = `approved|rejected|waived` (§9); `validator_ref` resolution = registry-internal at
V1, owner-repo existence at V2/reconciliation (§4). **Slice splits adopted** (§12): V1→V1a/V1b,
V3→V3a/V3b/V3c; **V5's recommended initial home is an operator host** (pending the §14.3a maintainer
decision) unless enterprise CI has private sibling creds + Docker + durable state + ~1h budget.

### 0.6 rev-5 → rev-6 (APPROVE-WITH-REDLINES completions — precision, no architecture)
Codex's pre-gate confirmation approved the direction; KS was fully satisfied; Engine/Studio concerns had
**partially** landed. rev-6 completes them. All verified at source.
| # | Redline | Completion |
|---|---|---|
| 1 | **`not_selected` didn't define the partly-selected hard-fail case** | §3.6: **dependency closure** — selecting a scenario pulls its `hard_fail_controls` co-members into the set, so a category is never partly-selected; a category wholly out of scope resolves **`not_applicable`** (not `unknown`, not pass). `not_selected` added to the publishable verdict list (§8). |
| 2 | **No-leak bound to the wrong control** | §3.4: the contract binds to **`_scan_studio_artifacts_for_absolute_paths`** (`:337` — the normalized alias-then-scan control), aliases optional. Cardinality: **0 aliases = scan fallback (today's normal path) · exactly 1 = accepted alias · multiple/conflicting = fail**. Reconciliation permits only the closed alias set, rejects any other extra label. |
| 3 | **Report parity misstated** as byte-identical live | AC1: pins don't stabilize `root`/raw paths (`:237-246`). Restated as the Engine review's real test — feed **identical captured `OrchestratorResult` fixtures** to the legacy and registry evaluators, compare a **normalized projection** (overall status · validation outcomes · checklist category order/names/statuses). |
| 4 | **Run-identity types imprecise** ("Python" singular) | §7/AC5: Postgres = **image ID + RepoDigest when available**; locally-built app = image ID (may lack RepoDigest); **Engine, Studio, KS Python executable/version separately** (adapters can select different interpreters); host JDK + Maven. |
| 5 | **Attestation outcomes undefined** | §9: a `rejected` record **fails** the gate; **`waived` is non-pass for MVP** unless an authorized-waiver policy (actor authority · reason · scope · expiry) is defined. Structural completeness ≠ approval. |
| 6 | **`validator_ref` type-ambiguous** (a code symbol ≠ a scenario id) | §4/AC1: a **typed approved-validator mapping** — validator id → owning adapter + code symbol. V1a validates id/mapping *form*; V2 owner-symbol existence; V3a reconciliation the complete mapping. Only `hard_fail_controls[].requires` resolves directly to scenario/step ids. |
| 7 | **OFF/ON L0 nodes had no owning slice** | §9/§12: a named **VS0 (Studio)** slice creates the separately-addressable OFF/ON pytest nodes (round-trip / parity / security / old-project-compat) — net-new, since Studio CI has no flag matrix today (`pytest-ci.yml:49-81`); `test_l5_acceptance_smoke.py` parametrizes **scenario names, not flag states**. VS1 stays the L5-env E2E. |
| 8 | **Coherence cleanup** | Stale live `runner_ref` (header, §10) → `execution_unit`; §3.5a allowlist **typed** (`orchestrator-adapter` vs `pytest-root`, with pytest-node dispatch under an approved root, and "new node under an approved root ≠ design gate; new root = design gate"); §4/§9/§10 slice names → V1a/V1b/V3a/V3b/V3c; **V5 depends on V3b** (its failure-signal + retained bundles need V3b's evidence work); Studio pin → `42cea31`. |
| 9 | **Two maintainer choices read as decided** | §14: scheduler home is a **recommended initial home pending §14.3a**, not "defaults"; VS1↔Action-5 **timing** added as an explicit open choice (start VS1 now for early backend proof, or align with the remaining Action-5/flag-node work — technical deps fixed either way). |

### 0.7 rev-6 → rev-7 (V-ACT must activate VS0's entries too — APPROVE-WITH-ONE-REDLINE)
Codex's post-rev-6 re-review confirmed every rev-6 fix landed and found **one** new coherence gap I
introduced when adding VS0: **VS0 declares new OFF/ON `pytest_nodes`, but V-ACT activated only VS1's L5
scenario.** Under scoped multiset reconciliation (§4), any entry a repo declares that the central registry
lacks turns the run **red** — so VS0's nodes, unactivated, would fail every full/flip-set run. Fix
(§9/§12): **V-ACT activates *both* VS0's OFF/ON pytest-node entries and VS1's flip scenario**, and the
gated-together group is **VS0 + VS1 + V-ACT** (not VS1 + V-ACT). Precision only; no architecture change.

### 0.8 rev-7 → rev-8 (absorbing Engine #280 — currency, AC10, two decisions taken)

Engine PR #280 merged **2026-07-27**, eight days after this design (#270, 2026-07-19). Nothing swept it
back. `docs/suite-security-review-backlog.md:416` requires M3 to **consume** its checks rather than
reimplement them.

| # | rev-7 text | Verified defect | Fixed in |
|---|---|---|---|
| 1 | §1.4 — *"Engine's four workflows carry **zero** smoke execution"* | **False since #280.** `generated-app-compile.yml` references `scripts/smoke/generated_app_independence.py` at **six** sites (invocations `:87`, `:97`, `:193`, `:199`), plus JAR-health and container checks (`:85-173`). | §1.4 — corrected; L1 row names the verifier |
| 2 | §1.2 enumerated **five** hardcoded name consumers, all in `l5_orchestrator.py` | **Incomplete.** #280 added a sixth named-result producer reached from *inside* two engine leaves. A registry enumerated from §1.2 as written omits it. | §1.2 — sixth bullet |
| 3 | §11 acceptance criteria | **No AC proves reuse.** AC1 (`:663-674`) validates the five existing name consumers and normalized parity; nothing requires a registered scenario to exercise `verify_generated_app_independence`. M3 could satisfy every AC while silently reimplementing independence assertions — what `:416` forbids. | §11 — **AC10a** adapter proof + **AC10b** registry-verdict proof added |
| 4 | §12 V1a — *"enumerates the full current id set … + engine leaves"* | **Under-specified for #280.** Resolved by the §14.5/§14.6 decisions rather than left open. | §12 V1a — one `engine.runtime` entry + `reuse_probes` schema |

**No new allowlisted unit or `unit_type` is required.** Both consuming paths are already approved
`orchestrator-adapter` entries: `engine.runtime` calls the verifier at `engine_l5_smoke.py:175`, and
`engine.regenerate` reuses the L1/L3 runner — `run_engine_l5_regen` invokes `l1_l3.main(args)` (`:223`),
which verifies at `engine_l1_l3_smoke.py:111-117`. `engine.change_plan` and `engine.apply_isolation` use
only `l1_l3`'s plan/snapshot helpers and never reach it (`:241-453`). Both consuming paths pass
`require_packaged_jar=True` and `require_schema_baseline=True`. V1a **does** extend the initial registry
schema with optional typed `reuse_probes` metadata on the existing unit (§12) — no new runner and no new
`verdict_selector.kind`.

**Three facts that shaped the decisions.**
1. **The verifier is fail-fast.** `_require` raises `IndependenceVerificationError` on the first failed
   condition (`generated_app_independence.py:586-588`), so the seven named checks accumulate in the report
   **only on full success**. `package-root` is a **precondition** evaluated at `:116`, *before* the report
   object exists at `:122` — its failure yields no report at all.
2. **Success discards the names.** `_assert_standalone_generated_app` (`engine_l5_smoke.py:1529`) is
   `-> None`; `EngineL5ScenarioResult` has no check-results field (`:67-111`); the leaf appends one coarse
   step string (`:176`), immediately after the verifier call and before the only passed return (`:193`).
3. **Failure text survives only through `engine.runtime`.** `IndependenceVerificationError` formats
   `f"[{check}] {message}"` (`:75-78`), preserved via `str(exc)` at `engine_l5_smoke.py:205`. Through
   `engine.regenerate` it does not: `engine_l1_l3_smoke.main()` catches everything, prints to stderr and
   returns `1` (`:196-199`), and `run_engine_l5_regen` emits a generic exit-code message (`:224-227`).

**Decisions taken: §14.5 (granularity = G-A coarse) and §14.6 (coverage = H-A representative CRUD).**
Under G-A the verdict semantics are total and need no new machinery: any failure — one of the seven **or**
the `package-root` precondition — raises, so `run_engine_l5_runtime` returns a **failed**
`EngineL5ScenarioResult` (`:205`), and `_result_steps_contain` short-circuits `if not result.ok(): return
False` (`l5_orchestrator.py:1016`). The scenario reads **`failed`**, never `missing`, and the concrete
`[check]` name is retained in the error evidence. If a required service is unavailable the adapter is
`skipped` (`:507`) and the selector returns `None` (`:1013-1014`) — non-pass under §3.6, never green.
`missing` remains reserved for its §3.6 meaning (*unit ran, selector found nothing*), which G-A cannot
produce here.

**Two implementation obligations.**
1. **§5 trigger treatment.** The new independence scenario needs ≥1 reviewed trigger or must be
   `"full-run-only"` — V4's standing lint enforces exactly that (`:465-470`).
2. **V3b sanitization — error payload included.** Failure messages leak host paths independently of
   `IndependenceReport.package` (`:116`, `:122`): `_reject_author_path_bytes` renders the matched absolute
   author path into the message (`:517-525`), the Maven check can surface a local `file:` URL (`:318`),
   and the `package-root` message embeds the resolved path (`:116-121`). Under G-A the error text **is**
   the evidence, so this is load-bearing. §8 already requires projecting every raw path (`:541`); this
   narrows an existing obligation rather than adding one.

**Direct-CI residual.** `generated-app-compile.yml`'s direct invocations remain **owner-repo per-PR
enforcement**. M3 consumes the *same verifier* through the existing adapter; it must **not** claim the
workflow itself is registry-selected or reconciled — the typed allowlist admits only orchestrator adapters
and pytest roots (§3.5a), §13 excludes CI-gating L5 on PRs, and §6 keeps per-PR cost L0-cheap (`:508-509`).

### 0.9 Post-rev-8 currency note — Studio PR #280 completed the flip

Studio PR #280 merged on 2026-08-10 after its recorded manual checklist passed. It made the refreshed
presentation unconditional and removed runtime consumption of `EDGEFORGE_STUDIO_UX_REFRESH` and
`EDGEFORGE_STUDIO_UX_SPLIT`; Studio's `test_pr24_flag_flip.py` now proves retired setting values cannot
restore a legacy presentation. PR #281 then added presentation-only visual polish.

This **resolves** §14.3e's VS1↔Action-5 timing decision by history, but it also makes the literal
VS0/VS1/V-ACT contract below stale: OFF/ON presentation nodes and a flag-ON E2E are no longer truthful
runtime distinctions. Before those three slices build, a narrow design amendment must:

1. replace OFF/ON presentation coverage with the shipped default-on flow plus retired-setting
   invariance;
2. bind the default-on author→generate→export→compile scenario to current Studio code and the existing
   PR-24 evidence rather than a removed flag;
3. revise the V-ACT declaration ids/selectors accordingly; and
4. keep A11y-01's spoken-announcement observation manual and separately representable without making
   it part of a required release profile. Under the revised coordinated policy proposed in
   [Studio PR #299](https://github.com/santosh-sh/EdgeForgeStudio/pull/299), A11y-01 alone no longer
   blocks source publication, internal baselines or tags, public releases, or promoted demos after
   both repository amendments receive independent review and merge. It remains a Studio-owned
   [open known limitation](https://github.com/santosh-sh/EdgeForgeStudio/issues/302), and all four
   native observations remain required for A11y-01 completion. The issue is recorded and
   publication-ready, but Studio is currently private. Any otherwise authorized public release or
   promoted demo while it remains private needs an audience-accessible known-limitation notice with
   impact and reproduction summary; #302 becomes a public contribution link only when accessible.
   This disclosure does not require completing A11y-01 before release.

The registry, selection, evidence, replay, and Engine #280 reuse mechanics remain approved. **Do not
implement VS0, VS1, or V-ACT literally from the pre-flip wording; amendment first.**

---

## 1. Current-state inventory (cited)

### 1.1 What the harness ladder delivered
- **Design:** `docs/suite-smoke-harness-design.md` — L0–L5 ladder (`:51-108`), §7 required scenarios,
  §8 pass/fail + *"a warning is never silently upgraded into passed"* (`:230-248`), **§8:240 absolute
  path leak = hard fail** + §12 *"No absolute local paths in committed artifacts"* (`:284`) + *logs
  redacted* (`:286`), §11 CI strategy (`:269-277`), §14 slices (**labeled *proposed* there** — the proof
  they landed is the **scripts' existence** below, not §14), §15 open questions.
- **Engine runners:** `scripts/smoke/engine_l1_l3_smoke.py` (801 lines; assertion-phase based) ·
  `engine_l5_smoke.py` (1,335) · `l5_orchestrator.py` (1,108).
- **Engine fixtures:** `scripts/smoke/fixtures/engine-l1-l3/{initial,additive,evolved}/` (synthetic).
- **Studio runners:** `tests/smoke/` — `test_l2_two_session_smoke.py`, `l4_driver.py`, `l5_driver.py`,
  `regen_smoke.py`, **`_shared.py` (670 lines)** of reusable builders (`make_exportable_smoke_session:136`,
  `make_combined_edge_contract_session:217`, security helpers `:433-534`).
- **KS runner:** `scripts/run_ks_l5_isolation.py` (@ `fb3a5e9`) — one script, six `_run_check(...)`
  calls (`:41-63`), emitting `{"checks":[…]}` (`:64-67`); invoked by the orchestrator over
  pinned-interpreter stdio (`l5_orchestrator.py:375` `_run_ks_l5`).

### 1.2 The registry already exists — hardcoded, and spread across MORE than one place
The suite's scenario inventory + validation lives as **Python constants and inline strings** in the L5
orchestrator — and, per §0.1, in **five** consumers, not one:
- `EXPECTED_STUDIO_SCENARIOS` (`:37-46`, 8) and `EXPECTED_KS_CHECKS` (`:57-64`, 6) — **presence** checks
  (`_validate_studio_payload:522`, `_validate_ks_payload:491`): missing fails, **extra/duplicate do not**.
- `STUDIO_REQUIRED_ARTIFACT_ROOTS` (`:87`) — keys are scenario names.
- `STUDIO_NO_LEAK_SCENARIOS` (`:65`), `STUDIO_REGEN_APPLY_SCENARIO` (`:36`).
- `_build_hard_fail_checklist` (`:901`) — the §8 checklist, threading **hardcoded** scenario names and
  engine **step-substrings** into each hard-fail line.
- **`verify_generated_app_independence` (`scripts/smoke/generated_app_independence.py`) — a sixth
  producer, added by Engine #280, reached from *inside* two engine leaves rather than from orchestrator
  constants (§0.8).** Seven named checks — `repository-boundary` · `java-imports` · `maven-boundary` ·
  `author-paths` · `schema-baseline` · `repository-hygiene` · `packaged-jar` — plus a `package-root`
  **precondition** (`:116`, outside the seven, evaluated before the report exists at `:122`). **Consumed
  through two already-approved adapters:** `engine.runtime` (`engine_l5_smoke.py:175`) and
  `engine.regenerate`, which reuses the L1/L3 runner (`:223` → `engine_l1_l3_smoke.py:111-117`); both pass
  `require_packaged_jar=True` and `require_schema_baseline=True`. The verifier is **fail-fast**
  (`:586-588`), so the seven names exist only on full success; on success they are discarded (`:1529` is
  `-> None`), and on failure the `[check]` name survives only through `engine.runtime`. Both paths cover
  **CRUD only**. Per **§14.5 (G-A)** the registry consumes this coarsely, and per **§14.6 (H-A)** against
  representative CRUD output; **AC10a/AC10b** prove the reuse across their owning slices.

This is the real current-state fact M3 builds on: **a working, fail-closed scenario contract exists —
but as scattered code, presence-only, visible only at L5.** M3 consolidates it (versioned registry),
makes it **exact** (missing/extra/duplicate), and extends its reach to L0–L4. Crucially, **execution is
coarser than the contract**: one Studio driver run and one KS script run each produce *many* named
results (§3.2).

### 1.3 Discipline already enforced in code (extend, don't reinvent)
- **Skip is not pass:** `status = "failed" if hard_failures else "skipped" if skipped else "passed"`
  (`:235`); `--allow-skipped-success` is discovery-only, *"Acceptance gates should not use this"* (`:161`).
- **Empty selection is a failure:** Studio CI guards every pytest filter with a collection-non-empty
  check (`.github/workflows/pytest-ci.yml`).
- **Reproducibility pinning:** `_sha_pin_manifest` (`:852+`) records `schema_version "1.0"`, per-repo
  `{path, sha}`, topology (Postgres image/container, in-process mock SOAP version, generated-app image);
  written per run — **but with absolute `path`/`root` values (§0.2 #4).**
- **Path-leak detection already exists — but macOS-only:** `LOCAL_PATH_LEAK_MARKERS` (`:102`),
  `_scan_studio_artifacts_for_absolute_paths` (`:337`). It is a **complementary** check, **not** M3's
  commit gate — M3 needs a general (POSIX+Windows) verifier (§8, §0.4 #1).

### 1.4 What runs where today (the gap M3 fills)
| Level | Exists as | Cadence today |
|---|---|---|
| L0 | three per-repo CI suites | per-PR, per repo |
| L1 | Engine `generated-app-compile.yml` (**path-filtered**) — compile **plus** the #280 independence verifier across CRUD, passthrough and Kafka — + `engine_l1_l3_smoke.py` | compile **and independence** per-PR; smoke script **manual** |
| L2 | Studio `test_l2_two_session_smoke.py` | **per-PR in Studio CI** |
| L3 | `engine_l1_l3_smoke.py` (plan/apply) | **manual** |
| L4 | Studio `l4_driver.py` | **manual** (sibling repos) |
| L5 | `l5_orchestrator.py` + three leaves | **manual / pre-baseline** (2026-07-02 GREEN) |

Engine still has **four** workflows, but they no longer carry **zero** smoke execution: since #280,
`generated-app-compile.yml` runs `scripts/smoke/generated_app_independence.py` per-PR (six references;
invocations at `:87`, `:97`, `:193`, `:199`), plus JAR-health and container checks. What remains true —
and is the gap M3 fills — is that **nothing routinely tests the three repos together**; cross-repo drift
is invisible between manual L5 runs.
`generated-app-compile.yml` being **path-filtered** shows the suite already practices changed-paths →
selected verification; §5 generalizes an in-house pattern, not a foreign one.

## 2. Gap analysis

| # | Gap | M3 answer |
|---|---|---|
| G1 | Scenario contract is scattered across ≥5 code sites, presence-only, L5-only | One versioned registry, **exact** (missing/extra/duplicate), all consumers routed (§3, §4) |
| G2 | Cross-repo naming is discovered only when a full run fails | Two-level contract: intra-repo per-PR lint + cross-repo reconciliation (§4) — stated honestly (§0.2 #3) |
| G3 | No change→scenario mapping; only "nothing" or "everything, manually" | Auditable affected-set with rename + doc-only handling, fail-closed (§5) |
| G4 | No scheduled cross-repo run | SHA-moved trigger (with real persistence) + weekly heartbeat (§6) |
| G5 | Evidence hand-authored; scheduled runs have no home; **raw bundles leak paths** | Sanitized path-free bundle gated by M3's own general verifier (§8) |
| G6 | Completed PR-24 evidence is point-in-time and mostly manual | Post-flip `flip-set` regression/evidence profile: closed-op checks + registrations + honest manual tail (§9) |

## 3. Scenario-registry schema — PROPOSED

**Home:** `scripts/smoke/registry/scenario-registry.json` (Engine repo, per harness §10). **JSON, not
YAML** — every current suite-state consumer parses stdlib JSON; no new dependency. A companion
`scenario-registry.schema.json` validates it in Engine L0 CI. `registry_version` (monotonic int) bumps
on any change; the **registry content digest** (sha256 of canonical-serialized JSON) is the replay key
(§7).

### 3.1 The core correction — three refs, because execution ≠ scenario
rev-1 conflated "a scenario" with "a callable." They are different granularities. Each entry carries:

```jsonc
{
  "id": "studio.multi-session-isolation",   // stable, namespaced, never reused (replaces the alias constants)
  "title": "Two Studio sessions cannot see each other's state, uploads, or outputs",
  "proves": "multi-session isolation",       // harness §7 capability (traceability)
  "level": "L5",
  "owner_repo": "studio",                    // engine | studio | ks | suite

  "execution_unit": "studio-l5-adapter",      // an ALLOWLISTED adapter (§3.5a); MANY scenarios share one
  "emits": "multi-session isolation",         // the label the runner outputs (mirrors the static manifest, §4)
  "verdict_selector": {                       // ONLY the pass/fail read (§3.3) — not every contract
    "kind": "list-key-match",
    "list": "scenarios", "key": "scenario", "value": "multi-session isolation", "verdict": "ok"
  },
  "contracts": [],                            // referenced structural/derived validators (§3.6); [] here

  "fixtures": ["studio:tests/smoke/_shared.py#make_exportable_smoke_session"],
  "run_modes": ["full", "affected", "flip-set"],
  "triggers": [{"repo": "studio", "paths": ["app/services/session*", "app/routes/**"]}],
  "determinism": "deterministic given pins; no network",
  "evidence": "scenario verdict in run report"
}
```

**`execution_unit` names an adapter, NOT a leaf callable (§0.5 #1).** rev-4 pointed a `runner_ref`
straight at `run_studio_l5_acceptance` — which would **bypass** the orchestrator's invocation adapters
that set `EDGEFORGE_SHARED_MODE=1`, pin the KS/engine interpreters (`_pinned_ks_python`,
`_engine_mcp_python`), and stamp repo provenance (`_run_studio_l5:285`; `_run_ks_l5:375` uses the pinned
`EDGEFORGE_KS_PYTHON`). So the unit resolves **through the existing adapter**: `studio-l5-adapter` →
`l5_orchestrator._run_studio_l5`, `ks-l5-adapter` → `_run_ks_l5`, `engine.<leaf>` → the four
`_run_engine_*`. The adapter *is* the pinned-interpreter/shared-mode/provenance gate; the registry never
invokes a driver callable directly. The alias constants (`STUDIO_REGEN_APPLY_SCENARIO:36`) collapse into
stable `id`s — one name, not a constant reused across five sites.

### 3.2 Coarse-run fan-out (the behavior rev-1 lacked)
- An **execution_unit** runs **once** and yields results for **every** registry scenario that shares it
  (`studio-l5-adapter` → 8; `ks-l5-adapter` → 6; each Engine leaf → its steps; a Studio pytest node →
  1). Selection (§5) selects **scenarios**; the runner executes the **union of their execution_units**;
  results **fan back out** to per-scenario verdicts via each entry's `verdict_selector`.
- **This is why the registry cannot be a list of callables.** It is a list of *verdicts to extract*,
  mapped to the *units that produce them*. The N-scenarios-to-1-unit relation is first-class.
- A unit that runs but whose `verdict_selector` finds nothing ⇒ that scenario is **`missing`** (§7) — a
  distinct not-pass, closing the "extra/duplicate/absent not caught" gap (§0.1).

### 3.3 `verdict_selector.kind` — the pass/fail read ONLY (a closed enum)
This layer answers just one question — *did this scenario pass?* — and only by **reading** an existing
runner's output. It is **not** the whole contract (§3.6 handles the rest).
| kind | Extracts from | Grounded in |
|---|---|---|
| `list-key-match` | a labeled entry in a results list (`list`/`key`/`verdict` **parameterized per entry**) | Studio `{"scenarios":[{"scenario","ok"}]}` `:103,:400`; KS `{"checks":[{"name","success"}]}` `:64-73` |
| `step-substring` | presence of an asserted step string in a leaf result | engine leaves + `_result_steps_contain` `:1013` |
| `pytest-outcome` | a pytest node's pass/fail | Studio L2/L4 nodes |

The Studio/KS divergence is exactly **why** the selector is parameterized: Studio keys entries on
`scenario`/`ok`; KS on `name`/`success` (`_validate_ks_payload:491+`). One `kind`, two configs. No
`kind` executes anything. Adding a `kind` is a reviewed schema change — not a per-entry escape hatch.

### 3.4 `contracts[]` and `hard_fail_controls[]` — the four contract kinds a selector CAN'T be (§0.3 #2)
A single `verdict_selector` cannot represent the five things the current code does (§0.3 #2). rev-3
**layers** them, and — critically — the registry **references existing validator code by name; it never
re-expresses that logic** (re-implementing a derived validation in registry JSON would be a second
harness by another name):

- **`contracts[]` on a scenario** — named structural/derived validators the runner already owns,
  attached to the scenario they qualify. Two kinds today:
  | contract kind | What it asserts | Referenced validator |
  |---|---|---|
  | `artifact-roots` | required **detail keys present** (structural, `_json_path_get(detail, path)`) | `_validate_studio_artifact_root_contract` (keys in `STUDIO_REQUIRED_ARTIFACT_ROOTS:87`) |
  | `derived` | composite logic over a scenario's detail payload | `_validate_studio_regen_apply_contract:569` (+ `_session:604`) |

  A `contract` fails its scenario independently of the `verdict_selector`; both must pass. The registry
  entry carries `{kind, validator_ref}` — a pointer, not the logic. **The validator resolves the scenario
  by its stable registry `id`, not by a global label:** today `_validate_studio_regen_apply_contract`
  searches `_studio_scenario(scenarios, STUDIO_REGEN_APPLY_SCENARIO)` (`:569-575`); **V2 (once, not V1 —
  §0.5 #5)** re-keys it to the `emits` label declared for `studio.regen-preview-approve-apply`, deleting
  the alias constant (`:36`) rather than leaving a parallel name.
- **The three `STUDIO_NO_LEAK_SCENARIOS` labels (`:65-69`) are ONE signal, not three scenarios (§0.5 #4,
  §0.6 #2).** The normalized control is **`_scan_studio_artifacts_for_absolute_paths` (`:337`)**, which
  *first* accepts an explicit alias if present and *otherwise* runs the artifact scan — and current
  Studio emits **none** of the aliases, so the **scan fallback is the normal path today**. So the
  contract binds to that **scan result**, with the three labels as **optional `accepted_aliases`
  compatibility inputs**, and a defined cardinality:
  | aliases present | meaning |
  |---|---|
  | **0** | scan fallback (the normal path) — verdict from the artifact scan |
  | **exactly 1** | accepted alias input |
  | **≥2 / conflicting** | **fail** (ambiguous no-leak signal) |
  Reconciliation is exact but **alias-aware for this one contract only**: it permits **only** the closed
  three-label set and rejects any other extra label. No label lives only in a set literal.
- **`hard_fail_controls[]` — a separate top-level section**, because the §8 "must never happen"
  categories are an **aggregation**, not a per-scenario read: each category is
  `_all_known(scenario_ok(…), ks_check_ok(…), steps_contain(…))` (`_build_hard_fail_checklist:901`),
  mixing scenario verdicts, KS checks, and engine step-substrings under **three-valued** logic
  (`_all_known:972` — any `None` ⇒ `None`, never silently `True`). Modeled as:
  ```jsonc
  { "category": "session bleed",
    "requires": ["studio.multi-session-isolation", "ks.per-session-db-isolation",
                 "ks.project-scoped-search-no-bleed", "ks.cross-project-filter-no-bleed"],
    "semantics": "all-known-ok" }   // any unknown ⇒ category unknown ⇒ NOT pass (maps to §3.6 missing/skipped)
  ```
  `requires` holds stable scenario/step ids — so the §8 checklist, today a wall of hardcoded strings, is
  data pointing at the same registry ids everything else uses. This is the fifth consumer, routed.

### 3.5 Non-runner operations are a **closed declarative set** (kills `meta-check`)
Some flip-set items (§9) aren't scenarios over product code — they assert **git/CI metadata**. rev-1's
generic `meta-check` could hide arbitrary assertions. rev-2 removes it and defines a **fixed enum** of
declarative predicates with **no embedded code**:

| op | Asserts | Inputs |
|---|---|---|
| `merge-ancestry` | each named PR's merge commit is an ancestor of the pinned SHA | repo, PR list, pinned SHA |
| `required-check-conclusion` | named required checks concluded `success` at the pinned SHA | repo, check names, pinned SHA |

### 3.5a Runner allowlist — the machine half of "no second harness" (§0.4 #2)
rev-3 called "no second harness" *structural*. It isn't: without an allowlist an `execution_unit` could
name any callable and V1a would check only its **form**, so a future entry could introduce a brand-new
parallel runner and pass. rev-4 adds the missing machine
control and grades the rest honestly:

- **`approved_execution_units` — a TYPED allowlist of invocation roots, not leaf callables (§0.5 #1,
  §0.6 #8).** Each entry carries a `unit_type`:
  | `unit_type` | entries | dispatch |
  |---|---|---|
  | `orchestrator-adapter` | `studio-l5-adapter`→`_run_studio_l5` (`:285`), `ks-l5-adapter`→`_run_ks_l5` (`:375`), the four `engine.*`→`_run_engine_*` | the runner invokes **only through the adapter** — the pinned-interpreter / shared-mode / provenance setup can never be bypassed |
  | `pytest-root` | the L2/L4 roots (`test_l2_two_session_smoke.py`, `test_l4_cross_repo_smoke.py`) | a scenario's `verdict_selector` (kind `pytest-outcome`) names a **node id under an approved root**; the runner dispatches that node |
  Every scenario's `execution_unit` **must** be on this list. **Friction is typed:** a **new node under an
  already-approved `pytest-root` is NOT a design-gate change** (it's ordinary owner-repo test work,
  caught by reconciliation); **a new root or a new `orchestrator-adapter` IS** — that's the boundary the
  Engine review asked to preserve. V1a rejects any `execution_unit` not on the list.
- **What this does and does not buy (honest grades):**
  - *Machine-enforced:* a scenario cannot silently introduce a new runner — unit **identity** is bounded
    by the allowlist, predicate ops by the closed set (§3.5), `contracts[]` targets by `validator_ref`
    resolution.
  - *Review-enforced (the registry cannot inspect semantics):* that an approved runner/validator's code
    contains **no product assertions of its own** stays a code-review property. rev-4 states this as
    review-grade in §10 rather than claiming the schema prevents it.

The enforceable rule (§10): **execution units are only allowlisted existing runners; `contracts[]` only
*reference* owner-repo validators (resolved, not inlined); the only non-runner operations are the closed
predicate set** — machine-checked. "**Referenced code carries no product assertions**" — review-checked.
A new predicate or unit is a reviewed schema/allowlist change, never inline code.

### 3.6 Verdict model (the fold cannot be inherited — §0.2 #7)
Per scenario: `passed` · `failed` · `missing` (unit ran, selector/contract found nothing — a defect) ·
`skipped` (unit could not run) · **`not_selected`** (not in this profile's set — §0.5 #2). Gate fold:
**`failed | missing → failed`**; **`skipped → non-pass`** (blocks the gate, per `:161`); a failing
`contract` → `failed`; a `hard_fail_controls` category resolving to `unknown` (any input `None`, per
`_all_known`) → **non-pass**; a `manual-attest` missing any required field (§9) → **`incomplete → failed
gate`**. `not_selected` is neither pass nor fail — an `affected`/`flip-set` run intentionally omits
scenarios, and an omitted scenario must not read as `missing` (which would wrongly fail the run).
`missing` = "this profile *asked* and the unit didn't produce it"; `not_selected` = "this profile never
asked."

**`not_selected` × `hard_fail_controls` — resolved by dependency closure (§0.6 #1).** A category must
never be *partly* selected (dropping omitted `requires` would vacuously weaken `all-known-ok`; treating
them `unknown` would defeat affected runs). Two rules make that impossible:
- **Closure on selection:** selecting any scenario that appears in a `hard_fail_controls[].requires`
  **pulls the category's *other* members into the selected set** — a safety property (§8 categories are
  gate-critical) can't be evaluated on a subset.
- **Whole-category omission ⇒ `not_applicable`:** if *no* member of a category is selected, the category
  resolves **`not_applicable`** — recorded, non-pass-non-fail, and **excluded from the gate fold** (not
  `unknown`, which is non-pass). A `not_selected` scenario is therefore **never** an `all-known-ok`
  input: either closure has pulled it back to a real verdict, or its whole category is `not_applicable`.
The existing `:235` fold is *extended*, not replaced.

## 4. The contract levels — buildable in isolated CI (§0.3 #1, #3)

Constraint: **Studio and KS CIs check out only their own repo** — and, sharper than rev-2 admitted,
they **cannot execute the L5 driver at all** (`l5_driver` imports `_post_generate` /
`run_engine_fail_closed_isolation` from `l4_driver`, which invoke the real Engine — §0.3 #3). So the
per-repo lint cannot *observe* emissions; it must read a **static declaration**.

- **Level 0 — static declaration, in contract-typed sections (§0.4 #3).** The registry spans L0–L5
  (`pytest-outcome` nodes, engine steps, L5 emitted labels); a repo's declaration is only *its* slice.
  So a flat "labels the driver emits" cannot reconcile 1:1 with the full registry. Each owner module —
  Studio `tests/smoke/scenario_manifest.py`, KS alongside `run_ks_l5_isolation.py` — declares **typed
  sections**:
  | section | holds | reconciles against registry entries where |
  |---|---|---|
  | `emitted_results` | L5 driver/KS labels the runner outputs | `owner_repo == repo` **and** `verdict_selector.kind == list-key-match` |
  | `pytest_nodes` | node ids the repo owns | `owner_repo == repo` **and** `kind == pytest-outcome` |
  | `execution_units` | the repo's runner roots | in `approved_execution_units` (§3.5a) with `owner_repo == repo` |

  **Both the driver and the lint read `emitted_results`:** the driver names each `_scenario(...)` /
  `_run_check(...)` result **from** it (a small refactor so the label has one source), and a static **L0
  lint** asserts every call site uses a declared label (AST/string scan — **no execution, no siblings**).
- **Level 1 — intra-repo drift, per PR.** The L0 lint catches a driver emitting an **undeclared** label,
  or a declaration entry no call site emits, in isolated CI. **V2 also makes the existing hardcoded
  name-contract tests consume the declaration** — Studio `test_l5_acceptance_smoke.py:61-77` (the 8-name
  `parametrize`) and KS `test_l5_isolation_helpers.py:15-22` (the 6-name set) **import** their
  `emitted_results` section instead of re-listing it; otherwise the declaration is a *third* copy, not
  the source of truth (§0.4 #3). **The routed KS test must switch from set-equality to multiset (§0.5 #3):**
  today `{names} == {names}` (`:15`) is a **set**, which silently accepts a duplicate; consuming the
  declaration must compare the emitted list as an ordered/multiset so a duplicate emitted name fails. It
  does **NOT** catch cross-repo drift (§0.2 #3).
- **Level 2 — scoped reconciliation (cross-repo, full runs).** Whenever repos are co-checked-out (every
  full/affected/flip-set run — already requires siblings, `:190+`), the runner reconciles **per (section,
  owner_repo)**: each typed declaration section ⟺ the registry entries of the *matching contract type and
  owner* — **exact, both directions, within that scope**, as a **multiset** (duplicate ≠ silently-equal,
  §0.5 #3). Not "the whole registry ⟺ each manifest" (which can never be equal). This is where
  **cross-repo drift is caught**.

**What V1a can and cannot validate (§0.3 #1).** V1a is **Engine-only**, so it cannot confirm a Studio/KS
callable *exists* — those files aren't checked out. V1a validates the registry's **form**: schema-valid;
`execution_unit` ∈ `approved_execution_units` (§3.5a); `owner_repo` consistent. **`validator_ref` is a
TYPED mapping, not a scenario id (§0.6 #6):** a `contracts[].validator_ref` names a **validator id** that
resolves through an `approved_validators` map `{validator_id → owning execution adapter + code symbol}`.
Only `hard_fail_controls[].requires` resolves **directly** to scenario/step ids. Resolution is layered by
who holds the repo: **V1a** validates the ids + the *form* of the mapping (registry-internal); **V2**
confirms the **owner code symbol exists**; **V3a** co-checkout reconciliation validates the **complete**
mapping. Engine-only V1a can't see Studio/KS source — rev-2's "V1 rejects unresolvable ref" overclaimed.

**Sequencing (§0.2 #2/#3; slice ids per §12):** **V1a/V1b** rewire the **five legacy** name consumers
(§1.2) to registry IDs; V1a separately binds the sixth #280 producer through `reuse_probes` and AC10a.
For the legacy names, presence → **exact/multiset**, form-validated. **V2** = the **typed declaration sections +
L0 lints + the driver refactor + routing the existing hardcoded tests through the declaration** (owner-repo
work, not just a JSON file — §0.3 #3). **V3a** = the runner, which owns scoped reconciliation. Honest
capability by slice: V1a/V1b = one source of truth in the orchestrator (+ form); V2 = intra-repo drift per
PR; V3a = cross-repo drift at reconciliation.

**Optional stronger guarantee (maintainer decision, §14):** to catch cross-repo drift *per PR*, publish
the registry digest to a location each repo's CI can fetch (a pinned raw URL or a vendored digest file);
each per-repo lint then also asserts its manifest reconciles against that digest. Default keeps
reconciliation at full-run time (no cross-repo CI coupling); the stronger option trades that coupling
for earlier detection.

## 5. Affected-set selection — table + rename + doc-only, fail-closed

Input: `(repo, changed_paths)` from `git diff --name-status` against the merge base (local) or the PR
file list (CI) — the mechanism `generated-app-compile.yml` already uses (§1.4). Resolution:

1. **Renames evaluate BOTH sides (§0.2 #6).** `--name-status` yields `R old → new`; feed **old and
   new** paths through the globs. A move out of a triggered dir must still select that dir's scenarios.
2. **Glob semantics — stated exactly:** gitignore-style, repo-root-relative POSIX paths, `**` spans
   directories, `*` does not cross `/`, evaluated case-sensitively. (No regex, no inference.)
3. **Three path classes, explicitly:**
   - matches a scenario `trigger` → select that scenario;
   - matches a reviewed **`no-scenario-impact`** list (maintained in the registry — e.g. `docs/**`,
     `**/*.md`, `LICENSE`) → contributes nothing;
   - matches **neither** → **fail-closed escalation to the full set** for that repo's levels + all
     cross-repo scenarios. "Unclassified" means "we don't know what this touches," never "nothing."
4. **Doc-only run is an auditable `no_run`, not an error (§0.2 #6).** If **every** changed path is
   `no-scenario-impact`, the result is a recorded `no_run` (reason listed) — distinct from
   `selection_empty` (which remains a **non-zero error**: paths existed but a selection bug produced an
   empty set).
5. The full selection record — mode, per-path classification, matched globs, escalations — is written
   to the bundle (§8): auditable after the fact.

**`full` defined precisely (§0.4 smaller-fixes):** the `full` profile = **every registry entry whose
`run_modes` contains `full`** — a declared set, not "everything that happens to exist." An entry omitted
from `full` (e.g. an `"optional": true` S1 pack scenario, §7) is thereby documented as out of the full
run, not silently dropped.

Standing lints (V4): every trigger glob matches ≥1 path or carries `"dormant": "<reason>"`; every
scenario has ≥1 trigger or is `"full-run-only"`; every `no-scenario-impact` glob matches ≥1 path; and
**no path may match both a trigger and a `no-scenario-impact` glob** — an overlap is a lint error, since
a path cannot be both selecting-a-scenario and impact-free (§0.4 smaller-fixes). **Not** dependency-graph
or coverage inference — a hand table with fail-closed escalation, auditable in review, right-sized for
≈20–30 scenarios (§11).

## 6. Run modes + cadence — justified, with real persistence

**Modes:** `full` · `affected` (§5) · `flip-set` (§9) · `replay` (§7) — four selection profiles over
one registry, one runner. Not four harnesses.

**Cadence.** The tracker's "nightly full run" is treated as a proposal:

| Candidate | Catches | Costs / misses |
|---|---|---|
| Per-PR full cross-repo | drift at the PR | sibling checkouts + tens of minutes/PR — harness §11 forbids it |
| Nightly unconditional | drift ≤24 h | runs identically on no-merge days — waste for a non-CD suite |
| Weekly unconditional | eventually all | up to 7-day window when it matters most |
| On-demand + pre-baseline | gate truth | status quo; weeks-long blindness |
| **SHA-moved + weekly heartbeat (recommended)** | SHA-correlated drift promptly **and** environment/dependency drift | needs durable last-run state (below) |

**Recommended — with the persistence rev-1 omitted (§0.2 #5):**
1. **SHA-moved full run.** A scheduled tick reads the three `origin/main` SHAs and compares them to
   **durable scheduler state**. **State location is specified, not assumed:** a single
   `scheduler-state.json` — **path-relative, no absolute paths** — persisted in the run environment's
   durable store (**CI cache/artifact if run in Engine CI; an operator-host state file if operator-run**;
   the choice is §14's execution decision, but *that a durable store exists* is required, not optional).
   It tracks, separately:
   - `last_attempted`: `{engine_sha, studio_sha, ks_sha, timestamp, status}`
   - `last_successful`: the same, for the most recent **passing** run.
   **Launch rule:** launch if **any SHA differs from `last_attempted`** *or* **`last_attempted.status`
   was not `passed`** — so an unchanged **failing** SHA **re-runs** until it passes or the SHA moves
   (rev-1's bug: comparing only SHAs would strand a failing SHA forever). A tick that declines to launch
   records `no_run: pins unchanged and last run passed` — a **scheduler decision**, never a skipped run.
2. **Weekly unconditional heartbeat.** Determinism is honestly **bounded**: the topology pins images by
   **mutable tag** (`postgres:16-alpine`, `:852+`) and generated-app compile resolves Maven from the
   ecosystem. A weekly run with unchanged SHAs therefore **can** surface environment/dependency drift
   that SHA-gating cannot — the honest justification (rev-1's "catches strictly more" / "no new
   information" are **struck**: they contradicted this very bound). Ties to **M2**; if V6 digest-pins the
   images, the heartbeat's value shrinks and is revisited.
3. **Pre-baseline / on-demand** — unchanged from today's L5 posture; the registry adds the bundle (§8).

Per-PR, the only new cost is L0-cheap: the per-repo manifest lint (§4) + an optional `affected` advisory
(which scenarios this PR *would* select, without running them).

## 7. Determinism & replay — **bounded**, with the full input set (§0.3 #5)

rev-3 still called its key the *"complete outcome-determining input set"* while omitting topology,
toolchain, and run config (§0.4 #5). rev-4 stops calling it "complete" and binds **the resolved run
manifest** — everything known to move a verdict:

- **The resolved run manifest (bound in the report, replay compares against it):**
  | group | fields | source |
  |---|---|---|
  | code | `engine_sha` · `studio_sha` · `ks_sha` | git |
  | contract | `registry_digest` · required-attestation digest | registry |
  | selection | `selection_profile` · resolved `selection_input` (changed-path set) · invocation flags (`--require-services`, …) | run |
  | topology | **Postgres = image ID + RepoDigest when available**; **locally-built generated app = image ID** (may have no RepoDigest); `mock_soap` version. Not the mutable tag alone (`:852+`). | resolved at run, **new work** — today only tags are recorded |
  | toolchain | **Engine, Studio, KS Python executable + version *separately*** (the adapters can select different interpreters — §3.5a), plus host **JDK** + **Maven** versions | resolved at run, **new work** — not recorded today |
  | predicate provenance | per predicate: PR/merge SHA · check-run **id + conclusion + time** — not just the boolean | GitHub, **snapshotted** (not reconstructable later) |

- **The guarantee is bounded, and a difference is a verdict, not a shrug.** Replay reproduces the same
  verdicts **within the declared `determinism_bounds`** (mutable tags until V6 digest-pinning; Maven
  resolution). A rerun whose verdict differs is an explicit **`replay_drift` — a non-pass**, carrying the
  manifest field that moved. "Identical verdicts" as an unconditional claim is **struck** (rev-1's
  scheduler over-reach, repeated). Predicate verdicts are **recorded, not re-derived** — GitHub state at
  evaluation time is gone by replay.
- **Replay is a first-class mode delivered in V3;** topology-digest + toolchain capture is new work it
  carries (today's manifest records neither — §1.3).
- **"Expected outputs" home, documented:** the in-repo fixtures' asserted expectations (Engine fixture
  expected-values; Studio `_shared.py` assertions; KS check predicates). The repo SHA *is* their version.
  The registry references them by path (`fixtures: [...]`); it does not copy them.
- **S1 Domain Sample Packs** (`:145`) may later register as `"optional": true` scenarios; they never
  join the fail-closed escalation set, and the registry core stays domain-neutral.

## 8. Evidence bundle — path-free by construction + M3's own verifier (§0.3 #4)

Per run the runner emits **two** artifacts, because the raw one **cannot be committed**:

- **Raw bundle** — full detail incl. absolute paths; written under the temp root, **retained on failure
  for triage, pruned on clean pass** (harness §12). **Never committed.**
- **Sanitized bundle** — the committable artifact, **absolute-path-free by construction**: the runner
  builds it carrying **only SHAs and repo-relative paths**, projecting every raw path through a
  relativizer. Redaction is the primary guarantee; a verifier is the backstop.

**The verifier is M3's own — not the Studio scanner (rev-2's overstatement, §0.3 #4).**
`_scan_studio_artifacts_for_absolute_paths:337` matches only three **macOS** markers
(`LOCAL_PATH_LEAK_MARKERS:102` — the `"/" + "Users/"` home root, `private/tmp/`, `var/folders/`) over
**generated-app artifact trees**. On a Linux runner, temp roots are `/tmp/…` and `/home/runner/…` — which
those markers **entirely miss**; on an operator host they could be macOS or Windows. **The run platform
is a §14-undecided choice — which is *precisely why* the verifier must be platform-general**, not lean on
any one OS's markers. M3 defines a general absolute-path verifier over the bundle's JSON+Markdown text:
- POSIX absolute roots — `/home/`, `/root/`, `/tmp/`, the `"/" + "Users/"` macOS home, `/private/`,
  `/var/`, and a general leading-`/` path-segment heuristic;
- Windows — `[A-Za-z]:\` drive paths and `\\` UNC paths.

Run as the **commit gate**, fail-closed (a match refuses the commit). It is a **heuristic** over free
text — a legitimate string can resemble a path — so the gate errs toward refusal and the by-construction
relativization, not the scanner, is what makes leaks unlikely in the first place. The Studio scanner
stays as a **complementary** macOS-artifact check, explicitly **not** the bundle gate. *(This design doc
itself writes the macOS home marker split, for the same reason the source does — else it would trip
`repo-hygiene.yml:17-24`, §0.4 #1.)*

```
sanitized-bundle/
  run-report.json      # status · registry_version · registry_digest · selection record (§5.5) ·
                       #   per-scenario verdicts (passed/failed/missing/skipped/not_selected/replay_drift —
                       #     none upgraded) + hard_fail_controls categories (…/not_applicable) ·
                       #   the resolved run manifest (§7: SHAs · image DIGESTS · toolchain versions ·
                       #     invocation flags · predicate provenance · attestation digest) — all PATH-RELATIVE ·
                       #   enumerated warnings · determinism_bounds · manual-attest records
  summary.md           # human page in the l5-acceptance-run.md format, generated
```

**Filing:** gate runs (pre-baseline, flip-set, handoff) commit the **sanitized** bundle under
`docs/handover-evidence/verification-runs/<yyyy-mm-dd>-<profile>/`, G10 index links the newest (the
2026-07-02 `l5-acceptance-run.md` stays as the historical record; its format is the template). Scheduled
runs (SHA-moved, heartbeat) are **CI artifacts / operator-retained, never auto-committed**; a **failure**
raises a visible signal (§14) carrying the sanitized bundle.

## 9. First milestone — retain the completed PR-24 checklist as regression evidence

> **Post-PR-24 build guard (§0.9):** the table preserves the checklist taxonomy and manual-vs-machine
> boundary, but its OFF/ON flag mechanics are superseded. PR #280 removed runtime flag consumption.
> VS0/VS1/V-ACT require the narrow default-on/retired-setting amendment before implementation.

Studio `implementation-design.md` §4.2, item by item — with the two precision fixes from §0.2 #8:

| §4.2 item | Disposition | Registry mechanism |
|---|---|---|
| 1. PR-01…23 merged; pre-flip rollout-state CI green | **historical closed declarative ops** — `merge-ancestry` (each PR's merge commit is an ancestor of the PR-24 flip SHA) **+** `required-check-conclusion` at that pin. **NOT** "is the checks API green now." The post-flip profile does not recreate retired runtime states. | §3.5 ops |
| 2. Default-on round-trip + parity + security suites green; retired rollout settings cannot restore the legacy UI | **register existing** Studio L0 suites as separately addressable outcomes. The §0.9 amendment binds the exact current node ids and the retired-setting-invariance coverage shipped by PR #280. | `pytest-outcome` selectors, one registry entry per current outcome |
| 3. PR-24a a11y checklist + recorded walkthrough; A11y-01 spoken announcements remain an open known limitation but are not a release/baseline/publication blocker after coordinated activation | **separate future manual-attest, outside required release profiles** — human judgment; one desktop success case failed and three cases remain unrun, so this item is non-pass and cannot support a verified-speech claim | attestation + walkthrough + [recorded Studio issue](https://github.com/santosh-sh/EdgeForgeStudio/issues/302) |
| 4. Manual E2E: sample → refreshed UX → export → `mvn package` | **split, honestly.** The scripted leg proves the **author→generate→export→compile _backend/functional_ flow via FastAPI `TestClient`** (the machinery `_shared.py`/L4/L1 already provide) — it does **NOT** prove "driven through the refreshed UX" (TestClient renders no browser). The rendered-UX proof is items 3 + 6. | replacement default-on scenario (**built in the Studio slice VS1, §12 — not V3**) + manual-attest for the visual half |
| 5. Old-project fixture loads/exports identically under the shipped UI | **register existing** legacy-compat and retired-setting-invariance tests selected by the §0.9 amendment | `pytest-outcome` selectors |
| 6. Maintainer demo sign-off | **manual-attest** — irreducible | attestation |
| 7. `v4.1.x` baseline tag reproducible | **manual-attest**, promotable to a scripted checkout→boot→health-probe later | attestation now |

**Output after the §0.9 amendment:** the completed PR-24 checklist becomes a repeatable
`run --profile flip-set` regression/evidence profile (items 1 as closed ops, 2/4-backend/5 scripted)
**+ a baseline manual tail** (4-visual, 6, 7). Item 3 remains separately representable as an
in-registry `manual-attest`, but after the coordinated Studio/Engine amendments activate it is outside
required source-publication, baseline/tag, public-release, and promoted-demo profiles. Its non-pass
state remains visible in the recorded Studio issue and, for any authorized public release or promoted
demo while Studio is private, in an audience-accessible known-limitation notice. It cannot support a
verified-speech or complete-accessibility claim. Every selected tail item retains the **binding
fields** below, so nothing manual is dressed as automated or silently dropped.

This policy became active when Studio PR #299 and its Engine/Suite companion #313 merged on
2026-09-23; the earlier classification in Engine #312 is superseded. The one failed native
observation and three unrun cases remain open. Activation does not convert them into a pass,
narrow the four-case native contract, waive another gate, or claim accessibility certification.

**Retired-setting traceability + who owns the nodes (§0.9).** PR #280 removed runtime consumption of
the rollout settings, so OFF/ON are no longer valid execution variants. The replacement invariant is:
the default-on suites remain separately addressable and setting either retired environment variable
cannot restore the removed legacy presentation. **Slice VS0 (Studio, §12)** declares the current
round-trip / parity / security / old-project-compat outcomes plus that retired-setting-invariance
outcome; the narrow amendment records the exact node ids from current Studio source. VS0 remains
isolated-CI owner work; VS1 remains the co-checked-out L5-environment E2E.

**Attestation — completeness is not approval (§0.6 #5).** Binding schema: `actor` (non-empty) ·
`timestamp` (**RFC-3339**) · `decision` (**enum** `approved|rejected|waived`) · `evidence_ref` (**a
resolvable URL or `repo@sha:path` — not free text**) · `scenario_id` + `run_id` · `registry_digest` ·
`repo_pins` (all three SHAs). **Outcome semantics, not just structure:** `approved` ⇒ pass;
**`rejected` ⇒ the gate fails**; **`waived` ⇒ non-pass for MVP** — a waiver counts only under a defined
authorized-waiver policy (actor authority · reason · scope · expiry), otherwise it blocks. Missing or
mal-typed any field ⇒ `incomplete` ⇒ no gate pass. A structurally-complete `rejected`/`waived` record is
**not** a pass.

**The post-flip milestone spans two repos, in ONE order that matches the §12 DAG (§0.4 #4, §0.6 #8).** V1a
seeds only *current* truth, so a scenario Studio hasn't emitted yet cannot be in the registry without
turning exact reconciliation red — hence the explicit **registry-activation** step:

> **V1a** (registry from current inventory — **no replacement PR-24 evidence entries yet**) → **V2**
> (declaration sections + L0 lints + route existing tests) → **VS0/VS1 (Studio)** declare the default-on
> L0/retired-setting outcomes and emit the default-on E2E result → **V-ACT** (Engine registry activation:
> add the revised VS0 pytest-node entries and VS1 scenario id + `verdict_selector` to the central
> registry) → **V3a** `flip-set` executes them. The V3a *runner
> code* may be built in parallel, but the **flip profile is complete only when the VS0+VS1 declarations
> and the V-ACT registry entries agree** (scoped reconciliation, §4). Any declared entry the registry
> lacks — or vice versa — turns reconciliation red, so **VS0, VS1 and V-ACT are gated to land together**.

**Timing + environment (post-PR-24):** the replacement VS1 still belongs in the co-checked-out L5
environment (Engine + JDK + Maven), not Studio's isolated pytest CI, because its
author→generate→compile leg needs the real Engine and Maven. The old OFF/ON plumbing is withdrawn;
the §0.9 amendment must bind current default-on behavior and retired-setting invariance. M3 no longer
closes the already-completed PR-24 gate; it makes that evidence repeatable.

## 10. Enforcement mapping (corrected)

| Rule | Mechanism | Grade |
|---|---|---|
| No second harness — **unit identity** | `execution_unit` ∈ the typed `approved_execution_units` allowlist (adapter or approved pytest-root); predicate ops ∈ closed set; `contracts[].validator_ref` resolves through the approved-validator map — V1a-lint-enforced (§3.5a) | **machine** |
| No second harness — **referenced code has no product assertions** | a property of the approved runner/validator source the registry cannot inspect | **review** (honest; rev-3 mis-graded this *structural* — §0.4 #2) |
| One source of truth | V1a/V1b route the **five legacy name consumers** (§1.2) through registry IDs, **exact/multiset** (missing/extra/duplicate) + **form-validated** (§4); the sixth #280 producer is bound coarsely through typed `reuse_probes`, with adapter reuse proven by AC10a and registry verdict propagation by AC10b; callable existence checked where the repo is present | **machine** |
| Skip ≠ pass; missing ≠ pass; unknown ≠ pass | extended `:235` fold (§3.6): `failed\|missing→failed`, `skipped→non-pass`, hard-fail `unknown`→non-pass | **machine** |
| Intra-repo drift per PR | static-declaration L0 lint (§4 L0/L1) — buildable in isolated CI | **machine, per repo** |
| Cross-repo drift | reconciliation at full runs (§4 L2) — **not** per-PR unless the §4 optional digest-publish is adopted | **machine, per full run** (honest) |
| Selection auditable; rename-safe; doc-only = `no_run` | §5 record + `--name-status` both-sides + `no-scenario-impact` list | **machine-recorded** |
| Scheduler reruns a failing SHA | `last_attempted` vs `last_successful` (§6) | **machine** |
| Committed evidence carries no path leak | path-free **by construction** + M3's **own** general verifier as commit gate (§8) — *not* the macOS-only Studio scanner | **machine** |
| Manual items never dressed up | `manual-attest` binding fields (§9); no machine pass | **structural** |
| Warning never upgraded | enumerated in `run-report.json` (harness §8) | **machine-recorded, human-reviewed** |

## 11. Acceptance criteria (for the build slices)

1. **Legacy name consumers routed + form-validated:** the five legacy sites in §1.2 (incl. `_build_hard_fail_checklist`
   as `hard_fail_controls`, `STUDIO_REQUIRED_ARTIFACT_ROOTS` as an `artifact-roots` contract,
   `STUDIO_REGEN_APPLY_SCENARIO` collapsed to an id, the **three no-leak labels as one `no-leak` contract
   with `accepted_aliases`**) load from the registry; validation is **exact/multiset** (absent-from-registry,
   **duplicate**, missing-expected each fail — a set comparison would miss the duplicate, §0.5 #3); V1a
   rejects any `execution_unit` not in the typed `approved_execution_units`, resolves `requires` to
   scenario/step ids, and resolves each `validator_ref` through the **approved-validator map** (id → adapter
   + code symbol, §0.6 #6). **Report parity is proven the way the Engine review specified (§0.6 #3): feed
   identical captured `OrchestratorResult` fixtures to the legacy and registry evaluators and assert an
   equal *normalized projection* (overall status · validation outcomes · checklist category
   order/names/statuses) — NOT two live reports byte-for-byte** (pins don't stabilize `root`/raw paths,
   `l5_orchestrator.py:237-246`).

10. **#280 reuse is proven on `engine.runtime` in two slice-owned stages (§0.8 #3, §14.5).**

    **AC10a — V1a proves the registry binding and direct adapter path.**
    - Run `engine.runtime` in a **controlled, focused adapter test whose prerequisites are arranged so
      execution actually reaches the verifier call** (`engine_l5_smoke.py:175`). A **skipped run, or any
      failure before the verifier is reached, does NOT satisfy AC10a** — the observed count is 0, not 1.
    - **Cardinality is per-adapter, exact, and declared on the execution unit — not on the scenario**
      (execution ≠ scenario, §3.1; many scenarios may share one unit, §3.2). AC10a resolves the scenario's
      `execution_unit`, reads `reuse_probes["generated-app-independence"].expected_invocations`, invokes
      the adapter **once**, and asserts the observed count **equals** the declared value — **1** for
      `engine.runtime` today. A whole-run count is **not** 1 and must never be asserted:
      `engine.regenerate` also reaches the verifier (`:223`). Declaring on the unit stays single-source if
      H-B later makes one adapter perform several archetype checks.
    - **Patch the symbol that adapter actually calls**, not the source-module export. Both consumers bind
      the name via `from … import verify_generated_app_independence` (`engine_l5_smoke.py:32`/`:35-37`;
      `engine_l1_l3_smoke.py:24`/`:26-28`) under a dual `try/except ImportError` path, so patching
      `generated_app_independence.…` alone leaves the bound reference untouched and the test passes
      vacuously.
    - Assert the invocation carries `require_packaged_jar=True` **and** `require_schema_baseline=True`.
    - Assert the direct adapter result is non-ok and its error retains `[m3-reuse-sentinel]`. This is
      **adapter-level propagation**, not a registry scenario verdict; V1a does not own fan-out or the
      verdict engine.
    - **Non-circularity guards.** The declared count must be used **only as a post-execution assertion**:
      it must never drive a loop that invokes the verifier; the adapter is invoked exactly once; the
      sentinel spy records the actual calls and arguments; and the final error must independently retain
      the sentinel token. A coordinated adapter-plus-count change remains visible in review, as with any
      contract test.

    **AC10b — V3a proves the registry scenario verdict.** Feed the failed `engine.runtime` adapter result
    carrying `[m3-reuse-sentinel]` through V3a's registry fan-out and verdict engine. Resolve
    `engine.runtime.generated-app-independence` through its declared `execution_unit` and
    `step-substring` selector; assert the final scenario verdict is **`failed`** and its error/detail still
    contains the sentinel. A skipped adapter or a failure lacking the sentinel does not satisfy AC10b.
    **The verdict alone proves nothing:** `_result_steps_contain` returns `False` for any non-ok result
    without inspecting its error (`l5_orchestrator.py:1016`), so every failure otherwise looks identical
    through the selector.

    **Binding restriction (v1).** Only `engine.runtime` binds #280 independence coverage.
    `engine.regenerate` **may remain registered for regeneration behaviour** but **must not claim #280
    check coverage**, because no unique token survives its error path (`engine_l1_l3_smoke.py:196-199`;
    `engine_l5_smoke.py:224-227`). Binding it later requires structured regeneration-error propagation
    **and** equivalent adapter-path and registry-verdict ACs — named prerequisites, not incremental edits.

    **Why not induced package failure.** Planting a forbidden import or Maven coordinate proves only that
    *something* rejected the defect — duplicated runner logic could reject it **before** the shared
    verifier runs and still turn the scenario red. Only call-and-propagation evidence distinguishes
    consuming the shared verifier from reimplementing it.

    **"No duplicated independence assertions" stays review-graded**, consistent with §10's grading of
    *"referenced code has no product assertions"* as a property the registry cannot inspect (`:649-650`).
    AC10a proves the shared verifier **is** on the adapter path; AC10b proves the registered scenario
    preserves its failure. Neither can prove nothing else also asserts.
2. **Fan-out + layered contract + `not_selected`:** one `studio-l5-adapter` execution (through
   `_run_studio_l5`, never the raw callable) yields all 8 Studio verdicts and one `ks-l5-adapter`
   execution all 6 KS verdicts, each via its `verdict_selector`; a scenario's `contracts[]` fail it
   independently; a `hard_fail_controls` category with any `unknown` input resolves non-pass; a selector
   matching nothing ⇒ `missing` ⇒ fail; **a scenario absent from an `affected`/`flip-set` set resolves
   `not_selected` — never `missing`, never a hard-fail input**; and a **mis-resolved/absent pinned KS
   interpreter stays `skipped` (non-pass) — never green from the declaration** (§0.5 #1, KS review).
3. **Buildable intra vs cross drift, one source:** the Studio L0 lint runs **without siblings** (reads
   the typed `emitted_results` section, not a live emission), and the existing hardcoded tests
   (`test_l5_acceptance_smoke.py:61-77`, `test_l5_isolation_helpers.py:15-22`) **import that section** —
   no third copy. A driver emitting an undeclared label fails Studio L0; renaming label **and**
   declaration together stays green in Studio CI and fails the next **scoped reconciliation** (matching
   `(section, owner_repo)`). The doc claims exactly this, no more.
4. **Selection:** a rename across a trigger boundary selects the dir's scenarios (**both** path sides);
   an all-`no-scenario-impact` change yields a recorded `no_run`; an unclassified path escalates to full;
   a genuine empty selection exits non-zero.
5. **Bounded replay:** two runs at an identical **resolved run manifest** (3 SHAs, registry_digest,
   profile, selection_input, invocation flags; **image ID+RepoDigest / built-app image ID**; **Engine +
   Studio + KS Python exe/version *separately*, host JDK + Maven**; predicate provenance; attestation
   digest — §7, §0.6 #4) produce identical verdicts **within `determinism_bounds`**; a difference is an
   explicit **`replay_drift` non-pass** carrying the field that moved; predicate verdicts are replayed
   from the snapshot, not re-queried.
6. **Scheduler:** a moved SHA launches; an unmoved-**passing** SHA records `no_run`; an
   unmoved-**failing** SHA **re-launches**; no unlaunched tick is recorded as passed/skipped.
7. **Evidence:** the **sanitized** bundle is path-free **by construction** and **passes M3's own general
   (POSIX+Windows) verifier** — demonstrated to catch a `/home/runner/…` and a `C:\…` path the macOS
   Studio scanner misses; the raw bundle is never committed; scheduled-run failure raises a signal.
8. **Post-flip milestone spans two repos, one order:** current default-on and retired-setting-invariance
   L0 nodes are declared in **VS0**, the default-on E2E result in **VS1**, and **V-ACT activates both
   sets of entries** in the central registry; only then does **V3a** report the repeatable PR-24
   regression/evidence milestone. **VS0, VS1 and V-ACT are gated to land together** — any declared entry
   the registry lacks (or vice versa) turns scoped reconciliation red. Item 1 preserves historical
   `merge-ancestry` + `required-check-conclusion` evidence at the flip pin; items 2/5 bind current node
   ids selected by the §0.9 amendment; item 4's scripted leg is labeled backend/functional; every
   `manual-attest` lacking a binding field blocks pass.
9. **No-second-harness grades honestly:** a registry entry with an `execution_unit` not in
   `approved_execution_units` fails V1 (machine); the doc states "referenced code has no product
   assertions" as **review**-graded, not structural.

## 12. Build slicing (each independently mergeable)

Engine's review recommended splitting the two big slices; adopted (§0.5). Each row stays independently
mergeable.
- **V1a** `[FEATURE]` Registry schema + `scenario-registry.json` + JSON Schema + Engine form-lint +
  the **typed `approved_execution_units`** (adapters + pytest-roots, §3.5a) + the **approved-validator
  map** (§4) + **exactness/multiset**. **Enumerates the full current id set** — all **8** Studio + **6**
  KS + engine leaves (rev-4 showed only 3 by example, §0.5 #6). *Engine-only.* (AC 1, 9, **10a**)
  **#280 independence — one entry, per §14.5/§14.6.** V1a enumerates a single engine-leaf scenario
  `engine.runtime.generated-app-independence`, `verdict_selector.kind: step-substring` against
  *"confirmed generated app has no Engine/Studio/KS/MCP/TestBench imports"* (`engine_l5_smoke.py:176`),
  satisfying `suite-security-review-backlog.md:416` by **consuming** the shared verifier. It carries a §5
  trigger or `"full-run-only"` and is bound by **AC10a**. `engine.regenerate` is **not** given a #280 entry
  in v1 (AC10a/AC10b binding restriction). V1a's `scenario-registry.schema.json` additionally defines **optional
  typed `reuse_probes` metadata on `orchestrator-adapter` units**: a closed probe identifier (initially
  `generated-app-independence`) mapping to a **positive integer** `expected_invocations`; **rejected on
  `pytest-root` units and on unknown fields**. This adds no allowlisted unit and no `unit_type` — it is
  typed metadata on an existing unit. **No new `verdict_selector.kind` and no Engine declaration
  surface** — G-A requires none.
- **V1b** `[FEATURE]` **Hard-fail migration** — route `_build_hard_fail_checklist:901` to
  `hard_fail_controls[]` data (+ the closure/`not_applicable` semantics, §3.6) + the
  `STUDIO_REQUIRED_ARTIFACT_ROOTS` / **one no-leak `contracts[]` bound to the scan** (§3.4). The most
  invasive orchestrator surgery; must keep the AC1 **fixture-projection** parity green. *Engine-only.*
- **V2** `[FEATURE]` **Typed declaration sections** (`scenario_manifest.py` in Studio + KS, §4) + driver
  refactor to source labels from them + **routing the existing hardcoded tests through the declaration
  with multiset equality** (`test_l5_acceptance_smoke.py:61-77`; KS `:15` set→multiset, §0.5 #3) +
  **re-key `_validate_studio_regen_apply_contract` by id** (§3.4) + L0 lints. Isolated CI (AC 3).
  *Sibling-repo PRs.*
- **VS0** `[FEATURE]` *(Studio repo)* **AMEND BEFORE BUILD (§0.9).** Replace the obsolete OFF/ON
  presentation nodes with separately addressable default-on parity/security/old-project checks plus
  retired-setting invariance, reusing shipped PR-24 tests where possible. Isolated Studio CI.
- **VS1** `[FEATURE]` *(Studio repo)* **AMEND BEFORE BUILD (§0.9).** Build a default-on
  author→generate→export→compile scenario with no rollout-flag claim. It runs in the co-checked-out L5
  environment (Engine+JDK+Maven), not isolated Studio CI.
- **V-ACT** `[FEATURE]` *(Engine registry)* **AMEND BEFORE BUILD (§0.9).** Activate the revised VS0
  nodes and VS1 scenario. It remains gated to land with VS0 + VS1 so partial declarations cannot
  reconcile green.
- **V3a** `[FEATURE]` **Runner core** (`scripts/smoke/run_registry.py`): coarse-run **fan-out** (§3.2),
  verdict/contract/hard-fail engines (incl. `not_selected` + category `not_applicable`/closure, §3.6),
  **scoped multiset reconciliation** (§4), profiles `full`/`flip-set`, invoking **only through the
  allowlisted adapters/roots** (§3.5a). Owns AC10b's final registry scenario verdict and sentinel-error
  propagation; V1a owns only AC10a's schema/binding and direct-adapter proof. (AC 2, **10b**)
- **V3b** `[FEATURE]` **Evidence + environment capture**: sanitized+raw bundles, the own POSIX+Windows
  path verifier (§8), and the **image-ID+RepoDigest + per-repo-interpreter + JDK/Maven capture**
  (net-new; §0.6 #4). (AC 7)
- **V3c** `[FEATURE]` **Replay + attestation**: the resolved-manifest `replay` mode + `replay_drift`
  (§7), closed declarative ops (§3.5), manual-attest binding + **outcome semantics** (`rejected` fails,
  `waived` non-pass, §9, §0.6 #5). (ACs 5, 8)
- **V4** `[FEATURE]` Affected-set selection: triggers + `--name-status` renames + glob semantics +
  `no-scenario-impact` + fail-closed escalation + glob/overlap lints (AC 4).
- **V5** `[CHORE]` Scheduled wiring: durable `scheduler-state.json` + SHA-moved launch + weekly heartbeat
  + **failure signal + retained sanitized bundles** (AC 6). **Depends on V3b** (§0.6 #8 — its signal +
  retained bundles need V3b's evidence work), not merely V3a. **Recommended initial home = operator host**
  (pending §14.3a) unless enterprise CI has private sibling creds + Docker + durable state + ~1h budget.
- **V6** `[CHORE]` *(optional)* digest-pin topology images; shrink the heartbeat justification (§6.2).

Order after the §0.9 amendment: **V1a → V1b → V2 → (VS0 ∥ VS1) → V-ACT → V3a → V3b → V3c
(milestone)** (V3a–c runner code parallels VS0/VS1/V-ACT); V4 parallel after V3a; **V5 after V3b**;
V6 anytime. **VS0 + VS1 + V-ACT remain the cross-repo group gated to land together** (§9); the
amendment changes their current ids/semantics, not the reconciliation rule.

## 13. Out of scope
A second harness / any new assertion engine (redline) · dependency-graph or coverage-based test-impact
inference (§5) · per-PR full cross-repo runs (harness §11) · per-PR cross-repo drift **unless** the §4
optional digest-publish is adopted · TestBench integration (Kafka-router role stays separate) · S1 pack
scenarios (optional, later) · CI-gating L5 on PRs (harness §15 Q3) · any Engine/Studio/KS runtime or
manifest change.

## 14. Decisions

1. **Registry home = Engine `scripts/smoke/registry/`**; **JSON over YAML** — no new dependency.
2. **Nightly-as-proposed replaced** by SHA-moved (with durable `last_attempted`/`last_successful`) +
   weekly heartbeat + pre-baseline (§6). The tick may *run* nightly; it *launches* on moved-or-failing
   pins.
3. **For the maintainer, at the gate — open unless explicitly marked resolved:**
   a. **Where scheduled runs + `scheduler-state.json` live** — Engine CI (cache/artifact state, sibling
      read token, ~1 h budget) vs an operator host (state file, human-owned). rev-5/§12 name the **operator
      host as the *recommended initial* home**, but this decision is open; V5 is written either way, and
      a durable store is required regardless (§6).
   b. **Cross-repo drift timing** — accept reconciliation-at-full-run (default), or adopt the §4 registry
      digest-publish for per-PR detection (adds cross-repo CI coupling).
   c. **Failure-signal channel** (repo issue vs other).
   d. **Evidence filing** (§8): gate runs commit the sanitized bundle; scheduled runs stay artifacts.
   e. **VS1 ↔ Action-5 timing — RESOLVED by Studio PR #280 (§0.9).** Action-5 and the manual flip
      checklist completed before M3 build. The remaining decision is no longer timing: VS0/VS1/V-ACT
      require the narrow post-flip semantic amendment before implementation.
   f. **Canonical-backlog edit, at the gate, not before (M4 §10.4 discipline):** if nightly is replaced,
      update roadmap `:137` (cadence note) + the tracker M3 row, then `python3 docs/tracker/build.py`
      committing JSON + `README.md` + `index.html`. This design does not touch the backlog itself.
4. **Naming:** the M3 deliverable is the **verification pack** (registry + runner + bundles); the
   **harness** stays the L0–L5 machinery it runs on — the tracker's "not a second harness" distinction,
   in the vocabulary.
5. **#280 registration granularity — DECIDED: G-A (coarse).** One coarse scenario per adapter
   **explicitly bound to #280**; **v1 binds only `engine.runtime`** (AC10a/AC10b binding restriction). Zero
   product-code change; satisfies `:416`; verdict semantics are total (§0.8).
   **Considered and rejected: G-B (per-check scenarios).** G-B would have required (i) a
   failure-projection choice among three options — preserve fail-fast with the other six reading
   `missing`; attach a structured partial report to `IndependenceVerificationError` (`:72-78`) retaining
   completed checks; or collect-all-then-raise, which alters the verifier's per-PR CI behaviour and would
   need Engine owner sign-off — (ii) a new Engine declaration surface, since §4 defines `emitted_results`
   for Studio and KS only (`:385-395`) and V2 is sibling-repo scoped (`:725`), **consumed by the producer
   and the exact-name test as well as the lint and reconciliation** (§4: *"Both the driver and the lint
   read `emitted_results`"*, `:396`), (iii) an explicit **`package-root` precondition / unit-failure
   projection**, since it fails before the report object exists (`:116` vs `:122`), and (iv) a
   prerequisite slice for producer exposure, with registry-result projection remaining V3a's (`:740`).
   **Seven `step-substring` entries were never a valid substitute:** `_result_steps_contain` is
   `any(text in str(step) for step in steps)` (`l5_orchestrator.py:1013-1019`) and cannot reject a
   duplicate step, an extra unregistered check, or a future eighth check. Rejected as disproportionate to
   a stability release; revisitable in v5.1 if per-check diagnostics are wanted, at which point (i)–(iv)
   all reopen.
6. **#280 archetype coverage — DECIDED: H-A (representative CRUD).** M3 selects the shared verifier
   through the CRUD output both approved adapters already produce (`_combined_manifest()` `:659-663`;
   L1/L3 fixture `:4`). **Boundary, stated so it cannot be misread:** owner CI remains **authoritative**
   for the full CRUD + passthrough + Kafka matrix (`generated-app-compile.yml:184-196`;
   `docs/generated-app-standards/generated-app-quality-gate-v1.md:109-114`), and **M3 does not claim
   full-matrix independence coverage.** This satisfies `:416`, which requires consuming the checks, not
   reproducing every #280 archetype execution. **Considered and rejected: H-B (full matrix)** — it needs
   no §3.5a gate change (an existing adapter could be expanded) but is real runner work, must land before
   or atomically with the entries selecting it, and would change AC10a's declared per-adapter counts.
