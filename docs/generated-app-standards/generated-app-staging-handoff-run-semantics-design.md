# Generated-App Staging-Handoff Run Semantics — Design (M5a)

> **Rev-15 amendment, 2026-10-02:** approved slice EF-V5-ENGINE-M5A-321-322 corrects
> [#321](https://github.com/santosh-sh/EdgeForge/issues/321) on both framework lines.
> The authoritative-date rule in section 7.1a supersedes the prior missing-context
> limitation and its post-commit-only qualifications below. Historical correction
> logs and dated evidence remain unchanged. The new dated result identifies executed
> proof and its exact code revision; independent review and human merge remain separate.

> **Status:** DESIGN **rev-15** with **M5a-S1 through M5a-S4 delivered** — the Engine now combines
> the package-scoped Flyway-owned Spring Batch metadata singleton, the bounded
> run-identity tasklet, the opted-in trigger/card contract, deterministically retained per-handoff
> `UNIQUE` migrations, PostgreSQL `ON CONFLICT`, and the H2 ensure-row/update/read sequence described
> below. Destructive clear-on-start is removed for opted-in jobs and public `generate`, `plan`, and
> additive approved `apply` are enabled; legacy handoffs remain unchanged. The compatibility harness
> now grades run-identity findings per handoff: opted-in failures are blocking `ERROR` results while
> legacy findings remain advisory `WARNING` results. Rev-14 completes
> the M5a-S2 pre-launch storage bound across both persistence
> layers and target profiles. The effective run-ID maximum is the lesser of the physical staging
> width and Spring Batch's `VARCHAR(2500)` parameter limit, with `TEXT` therefore capped at 2500;
> Java UTF-16 `String.length()` is the conservative common metric (§0.12, §5, §7.1, AC5c).
> Rev-13 completed the canonical identity contract after rev-12 exposed a
> PostgreSQL `CHAR(n)` equality mismatch. Rev-13 rejects non-canonical caller run IDs with leading or
> trailing whitespace before launch and uses the exact accepted value unchanged for Batch identity and
> staging, preventing two JobInstances from collapsing onto one padded staging key (§0.11, §5, §7.1).
> Rev-12 completed the broader S2 build contract after rev-11's disposable
> Spring Batch `5.1.2` + PostgreSQL feasibility run proved that durable metadata can retain an
> execution as `STARTED` after process death, making direct relaunch fail closed before the
> run-identity tasklet. Rev-12 retains explicit operator classification after ownership confirmation
> and no automatic multi-instance recovery, while pinning the previously missing trigger/test-console
> request shape, actual running-state diagnostics, pre-launch physical run-ID width check, and
> reproducible proof fixture (§0.10, §7.1, AC5/AC5b/AC7). It also retains rev-11's rejection of a
> generic keyset/frozen-upper-bound reader for S2 v1 because arbitrary generated entity ids provide
> no universal insertion-stable watermark (§7.2).
> Rev-10 selects and specifies the coordinated, pre-adopter
> `schema_version: "2.0"` cut as the M5a anti-downgrade boundary (§0.8, §7.6, §10.2–§10.5,
> §13.2). Engine V2-E, Studio V2-S, and both paired-branch and post-merge V2-X are complete.
> M5a-S1 delivers contract recognition and fail-closed validation; M5a-S2 delivers the bounded Batch
> identity/restart layer; M5a-S3 delivers idempotent staging; and M5a-S4 delivers the opt-in blocking
> harness gate. Actual scenario registration remains deferred to M3. See the
> [durable V2-X result](../test-results/manifest-v2-cut-v2-x-2026-08-16.md).
> V2-E closes package/raw-schema unknown-field parity, defines the reviewed standalone-package
> migration path, and emits explicit deterministic manifest-version provenance; the version enum alone
> is not a sufficient anti-downgrade gate for later `2.0` features.
> Three fail-closed/determinism corrections: **(1)** M5a v1 does **not** support completing a handoff
> or staging-table rename, including by adding an out-of-band Flyway migration, because no delivered
> Engine surface can reconcile that migration into the Engine-owned baseline; **(2)** the
> package-global `BATCH_JOB_*` singleton carries a versioned deterministic content fingerprint, and
> simultaneous new per-handoff entries use a stable allocation order in a dedicated ordinal
> namespace; **(3)** AC6 proves additive lifecycle behavior and exact rename refusal with zero package
> mutation, rather than implying an executable rename migration. This remains the design authority;
> M5a-S1, the bounded M5a-S2 Batch identity/restart layer, S3 idempotent staging semantics, and the S4
> opt-in blocking harness gate are implemented. Rev-15 corrects pre-identity-commit date authority
> from retained original execution parameters on both Batch lines (§7.1a); no recovery policy changes.
> **Scope:** roadmap **M5a** (`docs/enterprise-readiness-roadmap.md:135`) — production semantics for
> generated **staging-table** downstream-handoff Spring Batch jobs, the **`embedded`** topology only
> ([`downstream-handoff-execution-topology-design.md`](../edgecontracts/downstream-handoff-execution-topology-design.md),
> itself *"Design proposal"*). The run-semantics contract is written to **carry forward** to the other
> three (design-only) modes.
> **Grounding:** the core M5a mechanics were originally source-audited at Engine `3235fe7`.
> PR #288 refreshed the staging-DDL F5 posture through Engine `68885ba`; the rev-10
> manifest-version amendment was separately verified at `68885ba`. The rev-11/rev-12 S2 restart and
> rev-13 PostgreSQL `CHAR(n)` equality and rev-14 Batch/H2 length corrections are grounded by the
> reproducible disposable proof at Engine `bd401cb`, recorded in
> [`m5a-s2-abrupt-restart-feasibility-2026-08-17.md`](../test-results/m5a-s2-abrupt-restart-feasibility-2026-08-17.md).
> M5a implementation must revalidate the mechanics after the manifest-v2 cut. Domain-neutral; no
> scenario packet.
> Everything not cited is **PROPOSED**.
> **Prior art this design reuses / is bound by:**
> - **Event-delivery/outbox design** (PR #274): the suite's idempotency + internal-schema pattern —
>   a **durable key + `UNIQUE` fail-closed backstop + profile-appropriate atomic conflict handling**
>   (PG `ON CONFLICT … DO UPDATE`; **H2 = ensure-row → update → same-transaction read under the row
>   lock**, *not* `MERGE` — `generated-app-event-delivery-design.md:199-209`), and **retained
>   `internal_schema` baseline entries carried forward on disable** (§6.1 there). M5a reuses the
>   **invariant** and the internal-schema mechanism; each concrete SQL statement is **spike-pinned
>   per profile**, not asserted (§7.3, §0 #7).
> - Quality gate: staging tables need *"a primary key or equivalent run/row identity."* M5a-S4 emits
>   deterministic per-handoff results: an opted-in failure is a blocking `ERROR`, while a legacy
>   finding retains the existing advisory `WARNING`; one handoff cannot promote another's severity.
> - `idempotency_key` identity-role is advisory / Phase-4 gated (`manifest.py:351-356`) — untouched.
> **Redlines / guardrails:** M5a remains additive and opt-in **after the coordinated v2 cut** —
> **byte-identical generation when the block is absent**
> (AC1) · profile SQL **spike-pinned, not asserted** · **no exactly-once processing claim** · no-loss
> **bounded** by the source precondition (§4.2) · staging DDL stays **operator-authored and bounded
> by the fail-closed executable-input gate**; accepted decoded SQL is copied unchanged (the Engine
> adds constraints via its own additive migration, never by editing author DDL — §6.1) ·
> pre-cut/post-V2-E and pre-cut/post-V2-S compatibility **explicit and fail-closed** (§7.6) · no
> `1.0` compatibility bridge after the coordinated cut · regeneration-aware · domain-agnostic
> (`CONTRIBUTING.md:46`) · no mandatory EdgeForge runtime dependency.

---

## 0. Correction log (rev-1 → … → rev-13 → rev-14)

### 0.0 rev-1 → rev-2 (the rev-1 REQUEST-CHANGES review: 6 P1 + 2 P2/P3)

That review **confirmed** the direction (durable run id + unique backstop + atomic upsert) and that CI
is green. It **refuted or bounded** the following; all accepted, each verified at source.
**Rows 2 and 3 were themselves superseded in rev-3 — see §0.1 #10 and #11.**

| # | rev-1 claim | Verified defect | Fixed in |
|---|---|---|---|
| 1 | The existing temp+atomic move makes the downstream file last-writer-wins per `(runId,businessDate)` | **Mixed staging+file jobs stay restart-unsafe.** Staging and file rows are written in the **same chunk** (`java_emitter.py:12255-12303`); on restart `beforeStep` resets `recordCount=0` and creates a **fresh empty temp** (`:12312-12344`) while the reader resumes **past** committed chunks (`:12244-12253`) ⇒ the finalized file holds only the post-checkpoint **tail**. And the final path uses `LocalDate.now()` only (`:12401-12410`) — **no runId/businessDate** ⇒ two runIds same day overwrite. The mixed topology is a real fixture (`tests/fixtures/file-contracts/fixed-width-downstream-record-types/app-definition.yaml`). | §4/§7.5 — **v1 is staging-only; fail-fast when an opted-in staging handoff shares a job with file output**; restart-safe file output (separate rebuild step from committed staging rows, path keyed by runId+businessDate) is a **deferred forward design**, not claimed working |
| 2 | `restart: replace` reprocesses a completed run | **Cannot execute under JobInstance identity.** Same identifying params ⇒ same JobInstance; a **completed instance cannot run again**; a *new* runId's `DELETE WHERE run_id=<new>` replaces nothing. rev-1 also self-contradicted ("completed ⇒ 409" **and** "completed reprocess ⇒ replace") and left `businessDate` identity ambiguous (`addString` is identifying by default). | §4/§7.1 — **`replace` dropped from v1**; ship **failed-run `resume`** only; **`businessDate` is frozen-identifying, mismatch on restart rejected** *(← superseded in rev-3: making the date identifying creates a NEW instance instead of rejecting; §0.1 #10)*; `replace` deferred behind a run-control-ledger sketch (§11) |
| 3 | Unqualified "no dup/loss" and "row count == source count" | **Assumes an immutable source snapshot the design never creates.** The reader is a **paged live `findAll`** (`:12244-12253`); inserts/deletes before the saved offset shift pages, updates before the checkpoint are never revisited. Upsert dedups only rows *read* — it cannot recover skipped rows. | §4.2/§7.2 — explicit **immutable-source-during-run precondition**, claim **bounded** to it; keyset-cursor + frozen upper bound recommended as the robust mechanism; **AC2 mutates the source** *(← superseded in rev-3: that contradicts the precondition; split into AC2 in-guarantee + AC2b boundary; §0.1 #11)* |
| 4 | Author declares `UNIQUE(run_id,dedup_key)`; Engine validates; "Flyway migration (or initialize-schema)" | **Not regeneration-buildable.** Editing author DDL changes its `ddl_sha256` ⇒ `_staging_table_deltas` classifies it **unsafe** and `apply` rejects (`change_plan.py:442-499`); ordinary regen **preserves** migrations and emits none (`sql_emitter.py:46-48`); the batch-metadata migration is **absent** from baseline/Change-Plan/apply; "Flyway or initializer" is not one deterministic decision. | §6.1 — **Engine-generated `UNIQUE` as a retained `internal_schema` entry** (never edits author DDL); batch metadata likewise; **exactly one additive Flyway migration on enable**, carried forward on disable; enable/disable/re-enable/collision defined; **Flyway migration chosen** (drop the "or"). Maintainer decision 1 **resolved** (§13) |
| 5 | `dedup_key: [account_id]` = "source natural keys" | **Ambiguous + nullable-unsafe + unvalidatable.** "Source natural key" vs physical staging column is ambiguous (mappings rename `accountId→account_id`); a `UNIQUE` with any NULL component permits duplicate rows; and the DDL parser **skips `CONSTRAINT` lines** (`utils.py:205-228`), so author-declared constraint validation isn't defined. | §5.2 — `dedup_key` = **physical staging output columns**, one namespace; **run_id + every component required, mapped, type-compatible, NOT NULL**; NOT-NULL **validated fail-closed** (requires a Slice-1 parser extension, flagged); the `UNIQUE` is **Engine-generated** (§6.1), removing author-constraint-grammar guesswork |
| 6 | (implicit) older Engines are simply incompatible | **They silently downgrade a *safety* block.** `DataHandoffDefinition` has no `extra=forbid` (`manifest.py:195`), schema validation is optional on CLI generate (`cli.py:216-223`), and `load_project_definition` uses Pydantic directly (`:1173-1196`) — a `run_semantics` package **model-validates with the block dropped**, silently generating legacy clear+insert. | §7.6 — presence of `run_semantics` **forces schema validation** (not optional) and **rejects unknown handoff fields**; package binds a **minimum Engine capability/version**; older Engine **rejects rather than downgrades** *(← superseded twice: the capability stamp is unenforceable (§0.1 #9) and the version bump conflicts with a suite non-negotiable (§0.2 #16); the gate is now an OPEN maintainer decision, §13.2)*; anti-downgrade regression (AC9) |
| 7 | "H2 `MERGE` — the same helper" as the outbox | **Inaccurate.** The outbox H2 shape is **ensure-row → update → same-transaction read**, not `MERGE` (`event-delivery-design.md:199-209`). | Header + §7.3 — describe the **shared invariant** (profile-pinned atomic conflict handling + unique backstop); the staging statement is its **own spike-backed** shape, not a promised single helper |
| 8 | A domain-specific end-of-day framing in the problem statement | Violates the domain-agnostic rule (`CONTRIBUTING.md:46`). | Swept to neutral enterprise wording throughout |

---

### 0.1 rev-2 → rev-3 (the rev-2 re-review: 3 P1 + 2 P2 + 1 P3)

Rev-2 was confirmed on the mixed-file fail-fast, `replace` removal, Engine-owned author-DDL fix,
dedup namespace/nullability, H2-helper accuracy, and framing corrections. Six residual defects, all
accepted and verified at source:

| # | rev-2 mechanic | Verified defect | Fixed in |
|---|---|---|---|
| 9 | Anti-downgrade via a `min_engine_capability` stamp + forcing schema validation in the new Engine | **Self-defeating.** A pre-feature Engine **drops unknown fields** at both levels — a new top-level capability field *and* nested `run_semantics` (reviewer reproduced both against `origin/main`); and tightening validation in the **new** Engine cannot change what an **old** Engine does. The discriminator must be something the old Engine *already* rejects. | §7.6 — **manifest-version boundary**: packages using `run_semantics` declare **`schema_version: "1.1"`**, which every Engine validates on the **always-run Pydantic path** (`manifest.py:1005-1014`, *"Unknown schema_version … Supported versions"*; JSON schema enums `["1.0"]`) ⇒ pre-feature Engines **fail closed at load**. Packages without the feature stay `1.0` and remain cross-compatible. **AC9 runs the package through an actual pre-feature Engine.** Decision 2 **resolved** |
| 10 | `(runId, businessDate)` both **identifying**, "different date ⇒ rejected" | **Does not reject — it creates a new run.** Spring Batch derives the JobInstance from the **complete identifying set**, so the same runId + a different identifying date is a **new JobInstance that runs**; two concurrent such requests create **two** instances. No durable runId uniqueness existed, and the run-control ledger is deferred. | §7.1 — **`runId` is the sole identifying parameter**; `businessDate` is **non-identifying**, frozen on first execution and **compared on every later execution, failing fast on mismatch** *(mechanism made executable in rev-4 — a run-identity tasklet with `allowStartIfComplete(true)`; §0.2 #17)*; race safety comes from the **JobRepository's own instance serialization** (concurrent same-runId ⇒ 409), not app logic. **AC3–AC5 realigned** |
| 11 | AC2 mutates the source, then asserts exactly-once over a "frozen input set" | **Contradicts the stated precondition.** The v1 guarantee requires an immutable source and baseline v1 **never materializes** a frozen set (keyset/frozen-bound is only an optional Slice-2 recommendation); a frozen upper bound alone would not resurrect deleted rows or revisit pre-checkpoint updates. | §9 — **AC2 (positive)** holds the source immutable and asserts the guarantee; **AC2b (boundary)** mutates and asserts the **documented out-of-guarantee behavior**, including exactly which mutation classes the optional keyset option would and would not convert |
| 12 | Enums allowing `execution_derived + resume` and `caller_supplied + none`; `run_semantics: {}` and `dedup_key` requiredness unstated | **Exposes combinations the selected v1 semantics cannot honor** (no caller-stable identity to resume to; `none` is not equivalent to today once caller params become identifying). | §5.2 — v1 requires **exactly one bundle** (`caller_supplied` + `resume` + non-empty `dedup_key`); every other combination — including `{}`, a missing member, or an empty key — is a **fail-closed validation error** naming the unsupported combination; **legacy = omit the block** |
| 13 *(§6.1 wording superseded in rev-7 and rev-8 — no executable destructive or baseline-reconciliation flow exists; §0.5 #27, §0.6 #29)* | Enable/disable/re-enable described only for an **unchanged** key | **Key/column/table changes unclassified** ⇒ carry-forward could retain the **old** `UNIQUE` while adding a new one, silently over-constraining the staging table. | §6.1 — every `internal_schema` entry carries a **stable identity + content fingerprint** (incl. the exact `dedup_key` list); changing `dedup_key`, the run-id column, the table, or handoff identity is detected as a change to an existing entry and classified **unsafe/destructive**. M5a v1 refuses it without mutating package state; a future destructive migration + baseline-reconciliation protocol is required |
| 14 | "Flyway migration for batch metadata (H2 relies on Boot init)" | **Two rules, and it overstates H2.** The generated H2 URL is **`jdbc:h2:mem:`** (`target_profiles/catalog.py:44`) — batch metadata does **not** survive a process restart there. | §7.4 — one rule per profile: **PostgreSQL = Flyway-owned durable metadata** (initializer pinned off), **H2 = same-process restart only, stated explicitly**; durable cross-restart resume is proven on PostgreSQL alone (**AC7**) |
| 15 (P3) | PR body + a §0 correction-log phrase stale | The PR body still advertised `replace`, H2 `MERGE`-as-shared-helper, author-owned `UNIQUE`, and four old maintainer decisions; §0 row 8 re-quoted the domain-specific phrase it says was swept. | **PR body rewritten** to rev-3; §0 row 8 phrase **neutralized** |


### 0.2 rev-3 → rev-4 (the rev-3 re-review: 3 P1 + 1 P2)

Rev-3 was confirmed on the exact-option bundle, the immutable-source acceptance split, the H2
durability scope, and most of the run-identity model. Four residual defects, all accepted:

| # | rev-3 mechanic | Verified defect | Fixed in |
|---|---|---|---|
| 16 | `schema_version: "1.1"` as the anti-downgrade gate, marked **RESOLVED** | **Conflicts with a suite non-negotiable.** `CONTRIBUTING.md:38` — *"keep `schema_version: \"1.0\"` stable, add new concepts as optional `manifest-v1.1`-style extensions"* — repeated in `docs/suite-architecture.md:220-221` and `docs/manifest-schema.md:17-25`. The gate works technically (`manifest.py:1005-1015`, `core/manifest_versions.py`) but **evidence that a mechanism works does not authorize changing the suite contract** — that is a maintainer call, and I marked it resolved unilaterally. No third discriminator exists: `data_handoffs[].type` is an open string with a rejection list (`manifest.py:205-225`), not a closed enum. | §7.6 rewritten — claim **retracted**, **no Engine-enforceable gate exists under the current contract**, residual risk stated plainly; **Option A** (amend the contract + define a 1.0/1.1 compatibility matrix in the same gated change) vs **Option B** (keep `"1.0"`, process-level Studio/CI check only, AC9 reduced) put to the maintainer (§13.2) and marked a **blocking prerequisite** for Slice 1 |
| 17 | "the job's first step persists the date; every later execution compares" | **Not executable.** Spring Batch **skips a completed step on restart**, so the comparison would never run; and persisting inside the chunk step doesn't guarantee a durable commit before abrupt termination. | §7.1 — a **run-identity tasklet before the chunk step** with **`allowStartIfComplete(true)`**: first execution stores and **durably commits** the date before any data work; every later execution compares the inherited value and **fails before any staging write**. **New AC5b**: fail after that step, restart with a different date, prove rejection *before* staging writes, including a **process-termination** case on PostgreSQL |
| 18 | `internal_schema` entry keyed by *(handoff identity, staging table, purpose)*, "changing the handoff or table is detected as a change to that entry" | **Self-defeating.** Changing a key component produces a **different key**, so carry-forward would keep the old `UNIQUE` and add a new entry — the exact over-constraint hazard the paragraph claimed to close. | §6.1 — **immutable logical id assigned at first enable**, independent of mutable names; the entry *records* handoff/table/run-id column/`dedup_key` and fingerprints its SQL; any recorded-value change under that id is `unsafe`/`destructive`; **an id disappearing while a new one appears is itself destructive before carry-forward**. **AC6b now proves handoff/table rename refusal and zero mutation** |
| 19 (P2) | rev-3's identity fix wasn't propagated | §4.1, §8, §10 slice 2, the final decision, and `README.md:28` still described **`(runId, businessDate)` as identifying** — able to drive an implementation straight back to the rev-2 bug. | All normative/summary occurrences normalized to **"`runId` alone identifying; `businessDate` non-identifying and frozen-compared"**, doc + README |


### 0.3 rev-4 → rev-5 (the rev-4 review: 2 P1 + 1 P2 — propagation failures, not architecture)

Both P1s were **contradictory leftovers of earlier corrections**, the third consecutive round with
this failure mode. Fixed, and swept exhaustively this time — every occurrence of *identifying*,
*schema_version*/*1.1*, and *logical id* was enumerated and individually classified as
current-normative, historical-log, or corrected (sweep recorded in the commit).

| # | Stale text | Why it mattered | Fixed in |
|---|---|---|---|
| 20 | §4.1 still read *"the caller supplies `runId` (+ `businessDate`); **both are identifying JobParameters**"* — rev-2 text untouched by rev-3's correction | §4.1 is the **normative summary of the three properties**; an implementer reading it would rebuild the exact rev-2 defect (a changed date silently creating a *new instance* instead of being rejected), even though §7.1 was correct | §4.1 — **`runId` sole identifying**; `businessDate` non-identifying, frozen, tasklet-compared, failing **before any staging write**; with the reason inlined so it cannot be "simplified" back |
| 21 | §5.2 still stated *"A package using `run_semantics` **must declare `schema_version: "1.1"`**"* — the bullet **rev-3 added and rev-4 forgot to retract** while rewriting §7.6 and §13.2 | Directly contradicted rev-4's retraction **and** the live v1 policy (`CONTRIBUTING.md:38`), i.e. the manifest section instructed exactly what the compatibility section had just withdrawn | §5.2 — the package's `schema_version` is **explicitly tied to the OPEN §13.2 decision**: `"1.0"` under the current contract (with the silent-ignore residual risk restated), `"1.1"` **only** if the maintainer picks Option A |
| 22 (P2; allocation/reconciliation refined in rev-6/rev-8 — §0.4 #23, §0.6 #30) | The immutable `internal_schema` logical id was asserted but its **creation and reconciliation were undefined** | "Immutable id" is not implementable without saying *how it is minted* and *how a candidate is matched to it* — and a **derived/hashed** id would change with its inputs, reintroducing the rev-3 defect (§0.2 #18) | §6.1 — **created** in a dedicated ordinal namespace using stable candidate order, then persisted and never recomputed/reused; reconciled by explicit annotation or exact identity, never purpose/heuristic matching; ambiguity/removal fails closed |


### 0.4 rev-5 → rev-6 (the rev-5 review: 1 P1 + 1 P2 + 1 P3, plus re-grounding)

| # | rev-5 mechanic | Verified defect | Fixed in |
|---|---|---|---|
| 23 | "reconcile by **id first**"; purpose-matching as the fallback | **Circular and non-unique.** Manifest-derived candidates carry **no id**, so nothing can be matched *by id* until a candidate declares one; and *purpose* is not unique across multiple staging handoffs. Rename handling is one of this design's stated destructive-change guarantees, so an unimplementable association blocks the whole §6.1 contract. | §6.1 — a 4-step deterministic algorithm: **(1)** author-annotated `internal_schema_id` binds a candidate to a committed entry, preserving identity for precise diagnostics (it does **not** make the rename additive or executable); **(2)** otherwise exact **(handoff name, staging table)** match; **(3)** **no match ⇒ destructive remove + add, fail closed** — the Engine will not guess "renamed" vs "replaced"; **(4)** any many-to-one binding is a **reconciliation error**, never a guess |
| 24 (P2) | "different `businessDate` ⇒ the run fails fast on the tasklet comparison" | **Missing state precedence.** The tasklet is only reachable for a **FAILED/restartable** instance; a **RUNNING** or **COMPLETED** instance is rejected by the **launcher (409) before the job — and therefore before the tasklet — runs**. | §7.1 + §8 + **AC5 scoped**: RUNNING ⇒ 409, COMPLETED ⇒ 409, FAILED/restartable ⇒ tasklet comparison fails the job **before any staging write**; in all three **no fresh JobInstance is created**, which is the property that matters |
| 25 (P3) | Standards index still said rev-4; PR body still a rev-3 summary advertising the withdrawn mandatory `schema_version: "1.1"` gate | Stale published surfaces contradict the design's own retraction — the first thing a reader sees. | README index refreshed to **rev-6**; **PR body rewritten** to the rev-6 position (staging-only, resume-only, sole-`runId`, bounded no-loss, **open §13.2 compatibility decision**) |
| — | **Re-grounding (not a review finding; found while fixing the above).** rev-5 was cited @ `9ed09e0`. The merged **M1** PRs moved `main` to `3235fe7`: #276's SOAP hardening inserted ~130 lines into `java_emitter.py`, #278 added `emit_test_console` to `target_profiles/catalog.py`, and `build_emitter.py` shifted. | **Every staging-path citation in the document had silently drifted** (e.g. the staging `INSERT`, `resolveRunId`, `beforeStep`, and trigger anchors), which would have sent a build thread to the wrong lines. | All citations recomputed **and individually re-verified against `origin/main`** (java_emitter staging anchors +130; `catalog.py:40→:44`; `build_emitter.py:919→:965`); grounding commit updated throughout |


### 0.5 rev-6 → rev-7 (the rev-6 review: 2 P1 + 1 P2)

| # | rev-6 mechanic | Verified defect | Fixed in |
|---|---|---|---|
| 26 | `BATCH_JOB_*` batch metadata modelled as an `internal_schema` entry under the **per-handoff** identity/reconciliation algorithm | **Wrong scope.** Batch metadata is **one per generated package**, shared by every job and existing whenever *any* handoff enables restart — it has no handoff name and no staging table to key on. Under the per-handoff algorithm it would appear renamed or removed whenever an unrelated handoff changed. | §6.1 — **two identity scopes**: package-scoped **singleton** entries (currently just batch metadata) take a **fixed well-known id** (`pkg-batch-metadata`), are created once on first enable, **retained for the life of the package**, have no rename case, and are **excluded from per-handoff reconciliation**; per-handoff entries (the `UNIQUE`) keep the ordinal-id model |
| 27 *(completion path tightened again in rev-8 — §0.6 #29)* | An annotated rename is "an `unsafe`/`destructive` delta **requiring an approved migration**" | **That path does not exist.** `appbuilder apply` is **additive-only**: it fails closed on any unsafe/destructive delta — *"Unsafe/destructive changes must be handled manually"* (`apply.py:50,:70-80`) — and `--approved-plan-hash` approves an **additive** plan; **no approval permits a destructive delta**. So the design implied an executable flow that isn't there. | §6.1 — stated plainly: **v1 cannot execute a staging-handoff/table rename through the tool, annotated or not.** The annotation is **diagnostic and safety-preserving**: it turns a silently wrong remove+add into an explicit fail-closed error naming the entry and changed values. rev-8 removes the remaining implication that an operator can complete the transition with SQL alone |
| 28 (P2) | Slice 1 claimed **AC5** | AC5 asserts the per-state `businessDate` rejection, which needs the **run-identity tasklet — delivered in Slice 2**. A slice cannot claim an AC whose mechanism it does not build. | §10 — **AC5 moved to Slice 2**; Slice 1 keeps AC1/AC9/AC10. *(Self-caught in the same pass: **AC2b** was defined in §9 but claimed by no slice — now claimed by Slice 3 alongside AC2.)* |

### 0.6 rev-7 → rev-8 (the rev-7 review: 1 P1 + 1 P2 + 1 P3)

| # | rev-7 mechanic/surface | Verified defect | Fixed in |
|---|---|---|---|
| 29 | "Perform the manual rename migration" after additive-only `apply` refuses | **SQL does not complete the package transition.** The committed baseline still records the old handoff/table/fingerprint, so the next Change Plan reports the same destructive delta and remains blocked. No delivered command can safely adopt the migration and advance the Engine-owned baseline. | §6.1/§9/§11 — **rename is unsupported end-to-end in M5a v1**. Annotated and unannotated renames produce precise destructive plans; apply makes **zero** package changes; the operator must revert the manifest/package or wait for a separately designed destructive-migration + baseline-reconciliation protocol. AC6b locks baseline, migration inventory, and generated files byte-unchanged |
| 30 | Fixed singleton id `pkg-batch-metadata` with no version/fingerprint; "next ordinal" with no namespace or simultaneous-candidate order | A fixed id cannot detect a future Spring Batch/profile DDL change, and several first-enabled handoffs could receive different ordinals if emitter iteration order changes. | §6.1 — singleton stores `schema_contract_version` + canonical SQL `content_sha256` and fails closed on unversioned drift; per-handoff ids use the dedicated `m5a-staging` ordinal namespace, preserve/tombstone all prior ordinals, stable-sort unmatched candidates, and allocate from `max(existing)+1` |
| 31 | PR body remained rev-6; normative heading said "non-destructive rename"; AC6 included rename in an executable "migration set" | Public and acceptance surfaces could still direct a build thread to implement a flow the Engine refuses. | Header/§6.1/§9/README/PR body — terminology is **identity-preserving attribution**, not non-destructive; AC6 is split into additive lifecycle proof and rename-refusal proof; all normative/public rev-6 executable-rename wording removed |

### 0.7 rev-8 → rev-9 (doc-truth sweep: 1 P1 + 1 P2, no architecture change)

| # | rev-8 mechanic/surface | Verified defect | Fixed in |
|---|---|---|---|
| 32 | §10.1 said Slice 3 "lands on, or just after, the outbox build so the internal-schema + upsert primitives are exercised once" | **Contradicts the reconciled execution order.** `suite-security-review-backlog.md` §8 (line 387) rules *"M5a lands one generic foundation; event delivery consumes it. Do not implement twice,"* and §8's step 4 sequences "land the shared `internal_schema` foundation; build M5a." "On, or just after, the outbox build" inverts producer and consumer, and would license building the foundation twice — the exact duplication §8 exists to prevent. | §10.1 — Slice 3 lands **first** and establishes the one generic `internal_schema` foundation the outbox build then consumes, cited to backlog §8. The same-baseline mechanism and the spike-pinned upsert invariant are unchanged and still correct |
| 33 | §10.1 instructed that the note "belongs in the event-delivery design's sequencing section too — flagged for its next touch" | **Would have propagated the wrong ordering into a document that is already right.** Verified at source: `generated-app-event-delivery-design.md` §12 "Build timing" sequences by the canonical roadmap guardrail (M1 → M5a → …) plus §10.1's cross-design order, which is the correct producer-then-consumer direction. Acting on the instruction would have introduced the §0.7 #32 defect into a second design. | §10.1 — the cross-document instruction is **withdrawn** and inverted into an explicit "needs no change; do not propagate a different ordering into it." The event-delivery design is **not** edited by this revision |

### 0.8 rev-9 → rev-10 (maintainer decision: coordinated manifest 2.0 cut)

The maintainer selected a clean, pre-adopter manifest cut rather than either rev-9 option. The
decision was selected and specified by rev-10; Engine V2-E now delivers its Engine phase:

- the next manifest contract is `schema_version: "2.0"`;
- the post-V2-E Engine supports only `2.0`, and the post-V2-S Studio exports only `2.0`;
- no temporary or permanent `1.0` compatibility bridge is selected;
- the post-V2-E Engine rejects `1.0`, while pre-cut Studio remains on `1.0` until V2-S; and
- M5a-S1 was gated on V2-S and complete post-merge V2-X; both subsequently passed, satisfying the
  prerequisite without delivering M5a itself.

This resolves the anti-downgrade decision without claiming M5a implementation. The detailed entry-point
contract is in §7.6, the controlled cutover and proof are in §10.2–§10.4, and §13.2 records the
resolution. Historical descriptions in §0.0–§0.7 remain intentionally unchanged.

The rev-10 review identified seven required consequences of that decision, all incorporated into the
active contract:

| # | Review finding | Rev-10 correction |
|---|---|---|
| 34 | A post-V2-E, pre-M5a Engine would accept the same `2.0` version and silently discard a future `run_semantics` field on the permissive Pydantic package path. | V2-E makes closed JSON Schema validation mandatory before every package-model load, giving package and raw-schema paths identical unknown-field rejection. Stage 2 pins the immediate prior `2.0` Engine and proves both paths reject `run_semantics`. |
| 35 | Studio reopens project JSON snapshots, not standalone exported manifest packages. | §7.6 splits the migration paths: Studio snapshots reopen/re-export; standalone v1 packages use a deterministic reviewed copy-and-version conversion followed by both v2 validation paths. No package re-import is claimed. |
| 36 | Active manifest-policy surfaces still prohibited the selected cut. | The root README, manifest-schema document, edge-contract roadmap, and tracker candidate row now state the one approved exception and make later additive work target the active dialect. |
| 37 | Generated apps expose no explicit manifest schema-version provenance. | V2-E adds deterministic `manifest_schema_version` provenance to the schema baseline, standard generated audit surfaces, README, and `agent-context.md`, with V2-X assertions. |
| 38 | Two active policy statements still promised unconditional v1 compatibility. | The manifest target-profile policy and extension-architecture lock now state additive evolution within the active dialect, with V2-E/V2-S/V2-X as the sole approved no-bridge cut. |
| 39 | A uniform provenance requirement ignored current archetype artifact topology and could absorb Kafka agent-context work owned by M4. | §7.6 defines a closed archetype matrix: headers and README for all three lanes, baseline for CRUD, agent context for CRUD/passthrough, and conditional CRUD `AuditConfig`; V2-X proves applicable presence and intentional absence without creating new artifact classes. |
| 40 | A blanket generated-header rule could rewrite immutable prior Flyway migrations, and broad regeneration wording could advance the Engine-owned baseline outside approved apply. | §7.6 exempts existing `V*.sql` bytes from retrofit, requires provenance on new migrations, and makes baseline provenance follow the existing greenfield/adoption/apply ownership boundary. V2-X proves migration checksums and ordinary-regenerate baseline bytes remain unchanged. |

### 0.9 rev-10 → rev-11 (M5a-S2 abrupt-restart feasibility correction)

A disposable Spring Batch `5.1.2` + PostgreSQL run at Engine `bd401cb` completed the run-identity
step, entered the data step, and then hard-killed the JVM. PostgreSQL retained the job execution as
`STARTED`, the identity step as `COMPLETED`, and the data step as `STARTED`. Both same-date and
different-date relaunches raised `JobExecutionAlreadyRunningException` before any step could run.
The exact evidence is recorded in the linked test result above.

| # | rev-10 mechanic/claim | Verified defect | Rev-11 correction |
|---|---|---|---|
| 41 | Durable PostgreSQL `BATCH_JOB_*` metadata plus the run-identity tasklet was treated as sufficient automatic process-crash recovery. | Durability preserves the authoritative state; it does not make a stale `STARTED` execution restartable. Spring Batch correctly refuses to create another execution while the prior one is recorded as running, so neither the tasklet nor its date comparison is reachable. Startup auto-failure would be unsafe with multiple replicas because the apparent stale execution may still have a live owner. | §7.1/§7.4/§8/AC5b/AC7 — native restart is claimed only after an authoritative `FAILED` or `STOPPED` state. Abrupt-death `STARTED` is surfaced as recovery-required with the execution id and fails closed. V1 requires explicit operator classification after confirming no owner; automatic recovery is deferred until ownership fencing exists. |
| 42 | A generic keyset cursor plus frozen upper bound was offered as an S2 stability option. | Generated entities have arbitrary id types and ordering semantics; no universal insertion-stable watermark exists. Selecting one without a separate source contract would replace a documented boundary with an inference. | §4.2/§7.2/§9/§10.1 — the generic reader is **not selected for S2 v1**. The immutable-source-during-run precondition remains normative, and AC2b continues to demonstrate mutation as out of guarantee. |

### 0.10 rev-11 → rev-12 (M5a-S2 build-contract closure)

Rev-11 corrected the central abrupt-restart claim but left four implementation decisions incomplete.
Rev-12 closes them without reopening S1 or adding production behavior in this design PR.

| # | rev-11 gap | Verified defect | Rev-12 correction |
|---|---|---|---|
| 43 | The existing batch trigger was told to require `runId` and `businessDate` without selecting a wire shape or test-console input contract. | The shipped controller accepts only `{jobName}`, and legacy batch cards are `NONE`/`NONE`. An implementer could invent incompatible query/body shapes or change every legacy job. | §7.1/§10.1 — S2 keeps `POST /batch/run/{jobName}`, adds one closed JSON body for opted-in jobs, emits `FORM`/`JSON_BODY` cards with two typed fields, and preserves no-body `NONE`/`NONE` behavior per legacy job. Mixed applications are explicitly proven. |
| 44 | Every `JobExecutionAlreadyRunningException` response was hard-coded as `batchStatus=STARTED`. | Spring Batch `BatchStatus.isRunning()` includes `STARTING`, `STARTED`, and `STOPPING`; repository state can also become terminal between launcher rejection and diagnostic lookup. A fixed value lies about authoritative state. | §7.1/AC4/AC5 — query `JobExplorer`/repository state, return the actual observed running status, and fail closed with a separate state-changed/unavailable response if lookup observes a terminal transition or no authoritative row. Never parse exception text or invent `STARTED`. |
| 45 | S2 validated only that the caller's run ID was non-empty. | S1 already records a finite `CHAR(n)`/`VARCHAR(n)` width in `ValidatedStagingDdl.max_length`. An over-width value could create durable Batch identity and fail only at the staging write. | §5/§7.1 — carry that bound as generation-only metadata and reject an over-width run ID before `JobLauncher.run`; the exact bound is accepted and `TEXT` remains unbounded. |
| 46 | The feasibility result recorded source hashes, but its temporary source and command sequence were removed. | A reviewer could validate the narrative but could not independently reproduce the hard-kill, persisted rows, direct refusals, and post-classification mismatch from committed material. | The linked evidence now commits the exact small Maven fixture plus a bounded runner pinned to Spring Batch `5.1.2` and a pullable PostgreSQL digest. Generated files, logs, container, and database remain disposable under `/tmp`. |

### 0.11 rev-12 → rev-13 (physical/Batch run-ID equivalence)

| # | rev-12 gap | Verified defect | Rev-13 correction |
|---|---|---|---|
| 47 | S2 accepted exact-bound `CHAR(n)` run IDs after only blankness and width checks. | PostgreSQL blank-pads `CHAR(n)` and ignores trailing spaces for equality. `RUN-1` and `RUN-1 ` are distinct Spring Batch identifying strings but collide under `UNIQUE(run_id, dedup_key)`, so a later S3 upsert could update another JobInstance's row. The generated console preserves the entered text and cannot close the server-side gap. | §5/§7.1/AC3–AC5 — for every supported physical string type and both profiles, reject a run ID unless it equals Java `String.strip()` and is non-blank. Never silently trim. Use the exact accepted value unchanged for the Batch parameter, execution context/diagnostics, and staging writer. Add a `CHAR(n)` regression proving the padded variant is rejected before launch and cannot create a second JobInstance sharing the staging key. |

### 0.12 rev-13 → rev-14 (complete pre-launch storage bound)

| # | rev-13 gap | Verified defect | Rev-14 correction |
|---|---|---|---|
| 48 | Width validation considered only finite physical `CHAR(n)`/`VARCHAR(n)`, treated `TEXT` as unbounded, and counted Unicode code points. | Spring Batch `5.1.2` stores parameters in `BATCH_JOB_EXECUTION_PARAMS.PARAMETER_VALUE VARCHAR(2500)` on PostgreSQL and H2, so `TEXT` and wider physical columns can still fail during launch. H2 `2.2.224` measures a supplementary character as two UTF-16 units for `VARCHAR(n)`, while Java code-point count reports one. | §5/§7.1/AC5c — compute `effectiveMax = min(physicalMax, 2500)`, treating `TEXT` physical max as infinity, and validate with Java `String.length()` UTF-16 units before `JobLauncher.run`. Use the effective max in the server and console hint. Prove 2500/2501 boundaries for `TEXT` and a wide `VARCHAR`, plus the H2 supplementary-character boundary, with zero Batch/staging mutation on refusal. |

## 1. Audited pre-M5a inventory (core cited @ `3235fe7`; F5 refreshed @ `68885ba`)

Generated staging-handoff = a per-entity Spring Batch job (`{Entity}EodBatchJob`) reading the source
table and writing staging rows and/or a fixed-width file, triggered by REST.

| # | Fact | Evidence |
|---|---|---|
| **F1** | **Run identity ephemeral by construction.** `resolveRunId` reads a `runId` param but the only generated trigger passes none — comment *"Unique run.at param ensures re-runs are distinct instances"*, adding only `run.at=now()` ⇒ `runId` always falls back to `getJobExecutionId()`, new each launch. | `java_emitter.py:12450-12457`, `:13014-13027` |
| **F2** | **Native restart unreachable *and* self-defeating.** Every POST is a new JobInstance; `beforeStep` clears staging every execution; `spring.batch.job.enabled:false` + no scheduler/CLI ⇒ REST is the only entry. | `:13014-13026`; `:12089-12124`; `build_emitter.py:965` |
| **F3** | **Idempotency = clear-then-insert only.** Plain `INSERT`; `staging_row_id = UUID.randomUUID()` per row; the only dedup is `clear(runId)` = `DELETE … WHERE run_id=?` or `clear()` = whole-table. No `ON CONFLICT/MERGE/UNIQUE` in the staging path. | `:11902-11917`, `:11974-11975`, `:11878-11889` |
| **F4** | **Mixed staging+file in one chunk; file restart-unsafe.** The chunk writer writes staging **and** the temp file per record (`:12255-12303`); on failure the temp is deleted (`:12358-12367`); on restart `beforeStep` makes a fresh empty temp and resets counters (`:12312-12344`) while the reader resumes past committed chunks ⇒ **tail-only file**. Final path = `LocalDate.now()` only (`:12401-12410`) ⇒ same-day runIds overwrite. | as cited |
| **F5** | **Not manifest-expressible; accepted author DDL remains authoritative.** `DataHandoffDefinition` = name/type/spec/mapping; DDL accepted by the fail-closed staging trust boundary is copied unchanged into a Flyway migration; run identity is inferred iff a `runid`/`eodrunid`-named column exists. Translation and writer generation consume the same validated table/column model, including inline and table-level primary/unique constraints. | `manifest.py`; `sql_safety.py`; `translation.py`; `sql_emitter.py`; `utils.py` |
| **F6** | **The gate only warns; older Engines silently drop the block.** The harness WARNs *"…may not be production-ready"* and `passed` ignores non-`ERROR`. `DataHandoffDefinition` has no `extra=forbid`; schema validation is optional on generate ⇒ a `run_semantics` package model-validates with the block dropped. | `checks.py:212-221`; `models.py:36-39`; `manifest.py:195`; `cli.py:216-223` |
| **F7** | **Not regeneration-buildable as rev-1 proposed.** Author-DDL edits change `ddl_sha256` ⇒ classified unsafe (`change_plan.py:442-499`); regen preserves migrations, emits none (`sql_emitter.py:46-48`); batch metadata (`BATCH_JOB_*`) is never provisioned (no `initialize-schema`/`BATCH_*` migration anywhere) ⇒ no restart metadata on Postgres. | as cited |

**Supporting.** Chunk step on the injected `PlatformTransactionManager` (`:12178-12188`); reader is a
paged live `RepositoryItemReader.findAll` sorted by id, re-reading the whole source each run
(`:12244-12253`); one runtime test POSTs once and asserts `COMPLETED` — no count/restart/rerun/dedup
(`scripts/smoke/engine_l5_smoke.py:823-831`). Accepted staging SQL is copied unchanged after the
profile-aware trust-boundary validation (F5).

**The original one-sentence problem at the audited baseline:** an enterprise scheduled / end-of-day
handoff that **fails and is retried
orphans or duplicates staging rows and emits a truncated or overwritten downstream file** — and the
Engine ships that shape behind a non-blocking warning.

## 2. Problem statement

Durable run identity, restart, and idempotency are coupled and all absent (F1–F4). These are
**domain-independent batch-integrity mechanics** → generation-owned; the *content* (table, columns,
natural key) is contract data → manifest/DDL-owned; the same three-layer split and the same
idempotency + internal-schema primitives the event-delivery design established.

## 3. Decision matrix

| # | Alternative | Verdict | Reason |
|---|---|---|---|
| 1 | Status quo (clear-on-start + random-PK insert + ephemeral id) | **REJECT as end state; PRESERVED default** | orphans/dups on retry (F1–F4); non-opted-in apps stay byte-identical (AC1) |
| 2 | Whole-run single transaction | **REJECT** | unbounded TX for a full table; abandons chunking; no cross-launch idempotency |
| 3 | Delete-by-runId then insert (durable caller id) | **PARTIAL** | fixes replace only if the id is reused, leaves the restart data-loss hazard + no per-row idempotency |
| 4 | **Staging-only: durable caller runId + Engine `UNIQUE(run_id,dedup_key)` + profile upsert + resume-safe restart, immutable-source-bounded; fail-fast on mixed file jobs** | **SELECT (§4)** | retry/restart converge after an authoritative `FAILED`/`STOPPED` state; repository-observed running executions fail closed for explicit ownership review; reuses the outbox idempotency + internal-schema primitives and **claims only what the reader + JobInstance model can deliver** |
| 5 | Also make the downstream **file** restart-safe in v1 | **DEFER (§7.5, §11)** | requires a separate rebuild-from-staging step + re-keyed final path; real work, out of v1 scope; **fail-fast until then** |
| 6 | `restart: replace` in v1 | **DEFER (§11)** | not executable under JobInstance identity without a run-control ledger (P2) |
| 7 | CDC / external ETL owns idempotency | **OUT OF SCOPE** | the non-`embedded` topologies (separate design) |

## 4. Selected architecture (ADR-M5a) — staging-only, resume-only, bounded

**Opt-in via an additive `run_semantics` block on a `data_handoffs[]` *staging* entry (§5).** Absent ⇒
byte-identical (AC1). Present ⇒ the coherent production bundle below. **If the entry's job also emits
downstream-file output, generation fails fast** (§7.5) — v1 does not silently ship the restart-unsafe
file path (F4).

### 4.1 The three properties, made concrete
- **Durable run identity.** The caller supplies `runId` (+ `businessDate`). **`runId` is the *sole*
  identifying `JobParameter`**, so the same `runId` ⇒ the same JobInstance (the precondition for
  native restart) and is the staging idempotency partition. **`businessDate` is NON-identifying**,
  with the original durably persisted date authoritative on every later execution,
  including missing frozen context after an early crash (§7.1a). A mismatch **fails the job before
  any staging write**; frozen context corroborates rather than overrides origin.
  *(Making the date identifying would create a **new
  instance** on a changed date rather than rejecting it — §0.1 #10.)*
- **Restart = resume an authoritatively *failed or stopped* run only.** The same `runId` re-POSTed
  (with the frozen `businessDate`) after the prior execution is authoritatively recorded as
  **FAILED** or **STOPPED** ⇒ Spring Batch creates another execution for the same instance; the reader
  resumes from its checkpoint; the **upsert** makes re-written rows safe; the destructive
  clear-on-start is **removed** for opted-in handoffs (§7.2). Abrupt process death can instead leave
  the prior execution recorded in a running state (commonly **STARTED**); direct relaunch then fails
  closed with the actual repository state before the tasklet runs (§7.1). A **COMPLETED** instance ⇒
  **409** (not re-run).
  Intentional reprocess ⇒ a *new* runId (or the deferred `replace`, §11).
- **Idempotency = Engine-generated `UNIQUE(run_id, dedup_key)` + profile upsert.** The staging write
  becomes a **profile-pinned atomic conflict-handling upsert** keyed by `(run_id, dedup_key)` (PG
  `ON CONFLICT … DO UPDATE`; H2 ensure-row→update→read; each **spike-pinned**, §7.3). The `UNIQUE`
  constraint — **Engine-generated as an `internal_schema` migration, never an author-DDL edit** (§6.1)
  — is the **fail-closed backstop**: a wrong upsert fails the chunk instead of duplicating.

### 4.2 What is and isn't claimed — bounded
- **Claimed, *under the immutable-source-during-run precondition* (§7.2):** *effectively-once staging
  state per `(run_id, dedup_key)`* — after any number of failed-run resumes, each logical row that is
  **read** appears once with last-write-wins content.
- **Explicitly outside the guarantee:** rows inserted into / deleted from the source **after** a run
  starts (page-shift / never-revisited-update, F-supporting); mutation of the source mid-run remains
  **out of scope**. M5a-S2 v1 does not select a generic keyset/frozen-upper-bound reader because
  arbitrary generated entity ids do not provide a universal insertion-stable watermark (§7.2).
- **Never claimed:** exactly-once *processing*; that a *completed* run re-runs transparently;
  restart-safe **file** output (deferred, §7.5); cross-run ordering.

## 5. Manifest proposal — additive, opt-in

```yaml
data_handoffs:
  - name: acct-eod-staging
    type: staging-table
    spec: data-handoffs/acct-staging.sql          # operator DDL; validated fail-closed, copied unchanged, NEVER edited by the Engine
    mapping: data-handoffs/acct-staging-mapping.yaml
    run_semantics:                                # OPTIONAL; absent ⇒ legacy behavior, byte-identical (AC1)
      run_id: caller_supplied                     # v1: MUST be caller_supplied
      dedup_key: [account_id]                     # v1: MUST be non-empty; PHYSICAL staging output columns (post-mapping)
      restart: resume                             # v1: MUST be resume  (`replace` deferred, §11)
      # internal_schema_id: m5a-staging-001       # OPTIONAL, diagnostics-only on rename: declares
                                                  # which committed entry changed (§6.1 path 1).
                                                  # It does not make a rename executable in v1.
```
- **`run_id: caller_supplied`** wires the trigger + `resolveRunId` to require the caller's id as the
  **sole** identifying JobParameter (§7.1). Slice 1 requires exactly one recognized physical
  `run_id`/`eod_run_id` column, `NOT NULL`, with a string-compatible SQL type (`CHAR`, `VARCHAR`, or
  `TEXT`); accepting numeric/temporal partition columns would contradict the selected Java `String`
  run-ID contract before S2 can bind it. S2 carries the selected column's existing
  `ValidatedStagingDdl.max_length` into generation-only metadata. Before width validation, every
  supported physical string type applies the same portable canonicality rule: the caller value must
  be non-blank and equal Java `String.strip()` (no leading/trailing Java whitespace). The Engine does
  **not** trim or rewrite it. S2 then computes one storage-safe maximum:
  `min(physicalMax, 2500)`, where finite `CHAR(n)`/`VARCHAR(n)` contributes `n`, `TEXT` contributes
  infinity, and 2500 is Spring Batch `5.1.2`'s parameter-value column width on both profiles. The
  caller value's Java UTF-16 `String.length()` must not exceed that effective maximum **before**
  `JobLauncher.run`. This matches H2's stricter supplementary-character behavior and is conservative
  for PostgreSQL. The exact bound is accepted. The exact accepted string is used unchanged for Batch
  identity, execution context/diagnostics, and the staging writer.
- **`dedup_key`** = **physical staging output column name(s)** (the columns the upsert and the
  `UNIQUE` operate on) — one unambiguous namespace (F5: mappings rename `accountId→account_id`, so a
  "source path" namespace is not safely inferable). Slice-1 validation requires: every component
  **present in the staging table, mapped, type-compatible, and NOT NULL** (a NULL component defeats
  `UNIQUE`, §0 #5); normalized-duplicate or unsupported identifiers are rejected. Slice 1 consumes
  the structured `ValidatedStagingDdl.columns` result delivered by PR #288, which already records
  required/primary-key/unique properties; it does **not** add or fork a DDL parser. Type compatibility
  is evaluated against the complete pre-handoff canonical type set and every staging mapping, so
  reordering `data_handoffs[]` cannot change acceptance.
- **v1 accepts exactly one bundle; every other combination fails generation fast (§0 #12).** rev-2's
  enums implied combinations the selected semantics cannot honor — `execution_derived + resume` (no
  caller-stable identity to resume *to*) and `caller_supplied + none` (not equivalent to today once
  the caller parameter becomes identifying). Therefore v1 requires
  **`run_id: caller_supplied` + `restart: resume` + non-empty `dedup_key`**, all three present;
  **`run_semantics: {}`**, a missing member, an empty `dedup_key`, or any other enum combination is a
  **fail-closed validation error** naming the unsupported combination. **One optional member is
  permitted alongside the bundle: `internal_schema_id`** — the identity-preserving diagnostic
  annotation (§6.1 path 1). It is **omitted in the normal case**. Slice 1 validates its syntax and
  rejects duplicate claims across handoffs; baseline-existence and rename reconciliation begin in
  Slice 3, when `internal_schema` exists. It does not change the rename's destructive classification
  or make it executable. **Legacy behavior is expressed by omitting the block entirely** — never by a
  degenerate one. The closed schema exposes only the selected v1 values; any future combination
  requires an explicit additive contract change rather than silent approximation.
- **Presence of `run_semantics` forces schema validation and rejects unknown handoff fields** (§7.6) —
  the block is a *safety* contract and must never be silently dropped.
- **Slice 1 is CRUD-only.** Passthrough-router and Kafka translation do not consume staging handoffs,
  so all raw-schema, package-model, MCP, and CLI generation paths reject an opted-in non-CRUD
  manifest instead of accepting and discarding the safety block.
- **If the same entity-scoped EOD job also emits downstream-file output ⇒ generation fails fast**
  (§7.5); file output for another entity remains valid.

- **M5a is implemented only after the coordinated manifest-v2 prerequisite (§10.2).** V2-E requires
  Engine packages to use **`schema_version: "2.0"`** and retains no Engine `1.0` bridge. V2-S and
  complete V2-X are delivered, so the prerequisite is satisfied (§7.6).

Within the pinned post-V2-E, pre-M5a baseline, an absent block ⇒ no M5a
schema/generation/dependency change and byte-identical generation (AC1). The version cut itself is a
separate prerequisite and is never included in the M5a golden comparison.

## 6. Ownership, migration & regeneration

### 6.1 Engine-owned schema as retained `internal_schema` (mirrors event-delivery §6.1)
rev-1 required the author to add `UNIQUE`/`NOT NULL` to their DDL; that is **not buildable** — it
changes `ddl_sha256` ⇒ `_staging_table_deltas` flags it unsafe and `apply` rejects (F7). rev-2 makes
the Engine own the additive schema, never touching author DDL:
- **`UNIQUE(run_id, dedup_key)`** and the **Spring Batch metadata tables** (`BATCH_JOB_*`) are emitted
  as **`internal_schema` entries** in the schema baseline (the mechanism the event-delivery design
  introduced), each as **exactly one additive Flyway migration on enable** (Flyway chosen — not "or
  initialize-schema" — for deterministic, regen-preserved ownership; Boot's `initialize-schema`
  interaction is set to not double-create, stated as a Slice task).
- **NOT-NULL** on `run_id` + `dedup_key` stays the **author's** DDL responsibility (altering author
  columns would touch their DDL/sha); the Engine **validates it fail-closed** from the existing
  structured `ValidatedStagingDdl.columns` metadata (§5.2). Adding `UNIQUE` over
  already-NOT-NULL columns is a safe additive migration.
- **Two identity scopes, because the entries are not all per-handoff (§0.5 #26).** The reconciliation
  algorithm below is **per-handoff** and keys on handoff/staging-table identity — which the
  **`BATCH_JOB_*` batch-metadata entry does not have**: it is **one per generated package**, shared by
  every job, existing whenever *any* handoff enables restart. Modelling it per-handoff would make it
  appear to be renamed or removed whenever an unrelated handoff changed. Therefore:
  - **Package-scoped singleton entries** — currently just the batch metadata — use a **fixed,
    well-known id** (`pkg-batch-metadata`), **not** an allocated ordinal and **not** derived from any
    handoff. It is created once, on the first enable of any `run_semantics` handoff; it is **retained
    for the life of the package** (never carried by, or removed with, any individual handoff); and it
    is **excluded from the per-handoff reconciliation algorithm entirely** — it matches by its fixed
    id or it is created.
    - The singleton records `schema_contract_version: 1`, `target_profile`, and `content_sha256`.
      `content_sha256` is lowercase SHA-256 over UTF-8 canonical JSON containing the contract version,
      target profile, pinned Spring Batch metadata-schema version, and the **ordered normalized SQL
      statements** the Engine emits. Object keys are sorted; the SQL array remains in execution
      order; timestamps, migration filename/ordinal, generation id, local paths, and Engine version
      are excluded. Fixed inputs therefore produce the same fingerprint.
    - The Engine must increment `schema_contract_version` whenever the meaning or required shape of
      that canonical payload changes. Same id + same version + same fingerprint is retained with no
      migration. A fingerprint change without a version increment is an Engine integrity error.
      A version or fingerprint change is an explicit `unsafe` internal-schema delta in M5a v1 and
      `appbuilder apply` refuses it; the Engine must not overwrite the old baseline or create a second
      singleton. A future reviewed metadata-upgrade migration may define that transition. Unknown
      versions fail closed.
  - **Per-handoff entries** — the `UNIQUE(run_id, dedup_key)` constraint — use the ordinal-id +
    reconciliation model below.
- **Every *per-handoff* `internal_schema` entry carries an IMMUTABLE logical id + a content fingerprint (§0 #18).**
  rev-3 keyed the entry by *(handoff identity, staging table, purpose)* and then claimed a change to
  the handoff or table would be *detected as a change to that entry* — self-defeating, because such a
  change produces a **different key**, so carry-forward would preserve the old constraint and add a
  new entry: exactly the over-constraint hazard the paragraph claimed to close. Instead:
  - each entry is assigned an **immutable logical id at first enable**, independent of any mutable
    handoff/table name, and that id is what the baseline carries forward. **How it is created and
    reconciled, deterministically (§0.3 #22):**
    - **Creation/allocation:** the id is **generated by the Engine at first enable** and **written into
      the committed schema baseline** — it is *not* a hash of mutable manifest values (which would
      change when those values change). Determinism comes from a fixed allocation algorithm plus
      persistence, never randomness:
      1. reconcile all annotated and exact-match candidates to existing entries first;
      2. reserve every ordinal ever present in the dedicated **`m5a-staging` namespace**, including
         retained/disabled/removed entries; gaps are tombstones and are never reused;
      3. stable-sort the still-unmatched new candidates by canonical allocation tuple
         `(handoff_name, staging_table, run_id_column, dedup_key[])`, comparing the UTF-8 canonical-JSON
         bytes (sorted object keys; `dedup_key` preserves declared column order);
      4. allocate consecutive ids beginning at
         `max(existing m5a-staging ordinal, 0) + 1` (`m5a-staging-001`, `-002`, ...).
      Duplicate allocation tuples, malformed ordinals, or two candidates claiming one prior entry
      fail closed. Greenfield generation uses the same sort from ordinal 1, so manifest iteration or
      emitter traversal order cannot change ids. Once persisted, an id is never recomputed or
      renumbered.
    - **Reconciliation on every regeneration (§0.4 #23).** Manifest-derived candidates carry **no
      id** — so "match by id first" is only meaningful once a candidate *declares* one, and matching
      by *purpose* is non-unique across multiple staging handoffs. The deterministic algorithm is:
      1. **Author-annotated identity-preserving attribution.** If the handoff's
         `run_semantics` declares **`internal_schema_id: <id>`**, the candidate binds to that committed
         entry. A changed handoff name or staging table is then a **recorded-value change on a known
         id**, reported precisely against that id rather than as a silent remove+add. Annotating an id
         absent from the committed baseline is an error.
         **What that does and does not buy you (§0.5 #27, §0.6 #29):** it does **not** make the rename
         executable. `appbuilder apply` is **additive-only** — it fails closed on any `unsafe`/
         `destructive` delta and says so: *"Unsafe/destructive changes must be handled manually"*
         (`apply.py:50,:70-80`); `--approved-plan-hash` approves an **additive** plan, and **no
         approval path exists that permits a destructive delta**. So in v1 **a rename of a staging
         handoff or its table is not executable through the tool at all**, annotated or not. The
         annotation's value is diagnostic and safety-preserving: it converts a *silently wrong*
         outcome (remove+add ⇒ the old `UNIQUE` retained alongside a new one ⇒ an over-constrained
         table) into an **explicit fail-closed error naming the entry and the changed values**.
         An out-of-band SQL/Flyway rename alone is **not a supported workaround**: it does not update
         the Engine-owned baseline's recorded identity/fingerprint/high-water state, so later plans
         remain blocked. The only v1 recovery is to revert the manifest/package to the committed
         baseline. Completing a rename requires a separately designed destructive-migration +
         baseline-reconciliation protocol — **out of M5a's scope** and specified as a prerequisite
         contract in §11.
      2. **Exact identity match.** Otherwise, bind a candidate to the committed entry whose recorded
         **(handoff name, staging table)** match exactly. This is the ordinary no-rename case.
      3. **No match ⇒ destructive remove + add, fail closed.** An **unannotated rename** produces an
         unmatched candidate *and* an orphaned committed entry. The Engine does **not** guess they are
         the same: it classifies this as **removal of the old entry plus addition of a new one —
         destructive** — and **fails closed**. The operator may annotate `internal_schema_id` to
         declare the identity (path 1), which still fails closed but produces a precise,
         correctly-attributed error. The operator may not complete the transition by adding an
         untracked/manual migration; v1 recovery is revert-or-wait for the deferred reconciliation
         protocol. This is the honest default: the Engine cannot distinguish "renamed" from
         "replaced" without being told, and cannot advance its own baseline without a safe adoption
         surface.
      4. **Ambiguity fails closed.** More than one candidate binding to the same committed id (e.g.
         two handoffs annotating the same id, or swapped names) is a **reconciliation error** naming
         the conflicting candidates — never a guess. It must be corrected in the manifest; a manual
         migration does not resolve the baseline association.
    - **Removal:** an id present in the committed baseline and absent from the new candidate set is
      **destructive** (§6.1 carry-forward rules) — it is retained, never dropped implicitly.
  - the entry **records** its current handoff identity, staging table, run-id column, and
    `dedup_key` list, and **fingerprints** its effective SQL;
  - a change to any recorded value under the same logical id is classified **`unsafe`/`destructive`**
    and **fails closed** — `apply` cannot execute it (§0.5 #27), and M5a v1 does not supply a manual
    migration/adoption completion path (§0.6 #29);
  - **an entry's logical id disappearing while a new one appears is itself classified destructive
    before any carry-forward**, so a rename can never masquerade as an unrelated add.
  **AC6b covers precise refusal of handoff rename and staging-table rename**, including proof that
  the baseline, migration inventory, and generated files remain byte-unchanged.
- **Enable on an existing package** ⇒ the additive migration is planned via the Change-Plan path
  (plan→approve→apply); **disable** ⇒ generated batch/config revert, the `internal_schema` entries and
  their tables are **carried forward** (dropping them is the operator's destructive action, blocked at
  apply); **re-enable** ⇒ entry already present, no duplicate migration; a pre-existing
  table/migration is a **plan-time inventory collision**, distinct from a live-DB collision surfaced at
  Flyway apply.
- **ACs:** greenfield · enable-on-managed-package · disable-with-schema-retained · re-enable
  (no dup migration) · collision · NOT-NULL-missing fails closed — each with a real Flyway run (§9).

Ownership otherwise: staging DDL = operator-authored (bounded at ingest, accepted text copied
unchanged, never edited); batch Java / writer / trigger /
`resolveRunId` = generated (refreshed); `run_semantics` = author package input.

## 7. Runtime semantics

### 7.1 Trigger & run-identity contract — `runId` is the *sole* identifying parameter (§0 #10)
rev-2 made **both** `runId` and `businessDate` identifying. That does **not** produce the promised
rejection: Spring Batch derives the JobInstance from the **complete identifying set**, so the same
`runId` with a *different* `businessDate` is simply a **new JobInstance that runs**, and two
concurrent requests with the same runId and different dates create **two** instances. rev-3:

**S2 owns one stable HTTP and console contract.** The route remains
`POST /batch/run/{jobName}`. An opted-in job requires the closed JSON body below; a missing body,
missing/blank member, malformed ISO local date, or unknown member returns a stable 4xx before launch.

```json
{
  "runId": "RUN-001",
  "businessDate": "2026-08-17"
}
```

The generated controller accepts the body conditionally by job metadata: legacy jobs keep the
existing no-body `run.at` path byte-for-byte, while opted-in jobs reject a missing body and never add
`run.at`. The generated test console likewise emits descriptors **per job**: legacy cards remain
`NONE`/`NONE`; opted-in cards use `FORM`/`JSON_BODY` with required `runId` text and `businessDate`
date fields. The run-ID hint carries the effective physical/Batch maximum defined below. S2 owns the
controller request model, descriptor/card changes, and mixed opted-in/legacy proof; S3 may not remove
the S1 execution gate until this trigger contract and the S3 staging guarantees are both delivered.

- **`runId` is the only identifying JobParameter** (`run.at=now()` dropped). Same runId ⇒ **always
  the same JobInstance** — which is what makes restart/409 mean anything. Before launch, S2 validates
  that the input is non-blank and equals `runId.strip()`; boundary whitespace is rejected with a
  stable 4xx and is never silently trimmed. This applies to `CHAR`, `VARCHAR`, and `TEXT` on both
  profiles, closing PostgreSQL `CHAR(n)` blank-padding equality before Batch identity exists. S2 then
  validates Java UTF-16 `String.length()` against
  `min(ValidatedStagingDdl.max_length, 2500)`, with a missing physical maximum (`TEXT`) treated as
  infinity. The 2500 ceiling comes from Spring Batch `5.1.2`'s PostgreSQL and H2
  `BATCH_JOB_EXECUTION_PARAMS.PARAMETER_VALUE VARCHAR(2500)`. Exact-effective-bound input is accepted;
  over-bound input is rejected before any Batch row is created. The metric is safe for H2 and
  conservative for PostgreSQL. The same unmodified accepted value is passed to the identifying
  JobParameter and staging writer, and the effective maximum is emitted as the console field hint.
- **`businessDate` is NON-identifying and the original persisted request is authoritative.**
  The **run-identity tasklet before the chunk step**, with **`allowStartIfComplete(true)`**,
  validates complete retained history and corroborating context on every execution (§7.1a).
  Missing context is recovered only from valid original parameters, never the latest retry date.
  Only after validation does it save the same existing context keys in its transaction before data work.
  The original failed observation remains in the unchanged
  [crash-boundary evidence](../test-results/boot41-batch-crash-boundary-2026-10-01.md).
  The [rev-15 result](../test-results/m5a-early-crash-date-integrity-2026-10-02.md) separately records
  compiled early-crash proof on Boot 3 and Boot 4 with PostgreSQL Java 17 and 21.
- **Race safety** comes from the JobRepository itself, not from application logic: `JobInstance`
  creation is serialized by the batch metadata's own uniqueness on (job name, identifying key), so
  concurrent same-runId launches resolve to one instance — the second raises
  `JobExecutionAlreadyRunningException` (**409**) rather than racing the date comparison.
- **Running-state diagnostics reflect repository truth (§0.10 #44).** Spring Batch defines
  `STARTING`, `STARTED`, and `STOPPING` as running. After
  `JobExecutionAlreadyRunningException`, the controller queries `JobExplorer`/repository state for
  the matching job name and identifying `runId`; it does not parse exception text. If the latest
  observed execution is still running, return HTTP 409 with
  `code=batch_execution_running`, `runId`, `jobExecutionId`, the **actual** `batchStatus`, and
  `ownerVerificationRequired=true`. This deliberately does not label a live execution stale.
- **Lookup transitions fail closed rather than fabricating state.** If the execution becomes
  terminal between launcher rejection and lookup, return HTTP 409 with
  `code=batch_execution_state_changed`, its actual status/id, and `requeryRequired=true`; do not
  relaunch within the same request. If no authoritative matching execution can be read, return
  `code=batch_execution_state_unavailable`, `batchStatus=UNKNOWN`, and `requeryRequired=true`, with
  no invented execution id. Tests pin `STARTING`, `STARTED`, `STOPPING`, terminal-transition, and
  missing-lookup behavior.
- **Durable metadata is not automatic crash recovery (§0.9 #41).** Abrupt death may leave an
  execution in a running status, commonly `STARTED`; Spring Batch refuses a new execution before the
  run-identity tasklet. The response above supplies the execution id and actual state for ownership
  review. Only after independently confirming that no process/replica owns that execution may an
  authorized operator classify it `FAILED` through adopter-controlled procedure.
- **V1 recovery decision — explicit and fail-closed.** Do not auto-mark running executions failed
  during application startup or launch, do not add a generated recovery REST endpoint, and do not
  assume a single replica. Automatic multi-instance recovery is deferred until the design includes
  lease/heartbeat or equivalent fencing; without that, startup recovery could corrupt a legitimate
  execution still owned by another replica.

Contract and retained boundaries:
- **Fresh `runId`** ⇒ new instance; its durable original parameters establish authority before freezing.
- **Same runId, prior execution authoritatively FAILED/STOPPED, same businessDate** ⇒ **restart**
  (§7.2).
- **Same runId, prior execution COMPLETED** ⇒ `JobInstanceAlreadyCompleteException` ⇒ **409**.
- **Same runId with latest status STARTING/STARTED/STOPPING** ⇒
  `JobExecutionAlreadyRunningException` ⇒ **409 `batch_execution_running`** with the execution id,
  actual status, and ownership-review requirement. The generated app does not guess whether it is
  live or stale.
- **Same runId, *different* businessDate** ⇒ the outcome depends on the instance's state, because
  **launcher-level rejections precede the job and therefore precede the tasklet (§0.4 #24)**:
  - latest execution **STARTING/STARTED/STOPPING** ⇒ the running-state **409** above
    (`JobExecutionAlreadyRunningException`) — the job never starts, so no date comparison happens;
  - instance **COMPLETED** ⇒ **409** (`JobInstanceAlreadyCompleteException`) — likewise;
  - instance **authoritatively FAILED/STOPPED and restartable**, with committed or missing frozen
    context ⇒ the tasklet compares to original durable parameters and **fails before staging**.
    Malformed/conflicting history or context fails closed, not automatic repair (§7.1a).
  In every case **no fresh JobInstance is created**, because the date is not identifying — which is
  a preserved identity property, but **not sufficient** to establish date protection.
Intentional reprocess of a completed date ⇒ a new runId (v1), or the deferred `replace` (§11).

### 7.1a Authoritative original request (rev-15)

On every reachable identity tasklet, obtain the **complete retained execution history**
for the instance: Batch 5.1.2 `JobExplorer.getJobExecutions(JobInstance)` or Batch 6.0.5
`JobRepository.getJobExecutions(JobInstance)`. The pinned JDBC DAOs query every execution
without pagination, allocate sequence execution IDs before insertion, and order by
descending `JOB_EXECUTION_ID`. Select the **lowest positive persisted execution ID**,
not timestamps, iteration order, latest retry, or first context-bearing record.
This lowest-ID origin rule relies on serialized execution creation per JobInstance
and the generated ascending PostgreSQL sequence's `CACHE 1` (default), `NO CYCLE`
ordering; multi-session `CACHE > 1`, cycling or resetting the sequence invalidates
that assumption.
Missing/empty history, failed reads, null/duplicate/unorderable identities, wrong
instance/job, absent current execution, or contradictory current durable parameters
fail the identity step with a bounded `M5a integrity` diagnostic before staging.
Batch 6 parameter equality compares names only; compare typed values explicitly.

The origin must carry canonical identifying String `runId` as the sole identifying
parameter and non-identifying `LocalDate businessDate`. Every history run identity
must match the current instance request; required parameter types/flags must be valid.
The current requested date must equal the origin date. A valid mismatched date in a
later **rejected** execution is retained but is not authoritative and does not poison
a subsequent original-date retry. The first execution establishes origin from its
own durable parameters before freezing; missing context on a later execution is
recoverable only from this valid complete history.

Every retained job context and the inherited current context corroborate that origin.
Present `runId`, `frozenBusinessDate`, and downstream `businessDate` keys must be
Strings with exactly the authoritative values. Wrong types, malformed dates, or
conflicts fail closed and are never overwritten or repaired. Absent keys are frozen
only after all history/parameter/context checks pass. Existing keys and downstream
use remain unchanged. Launch-level completed/running/state-changed/state-unavailable
responses still precede this check and retain their contract; restartable mismatches
fail the identity step, not a new HTTP refusal policy.

AC5 now includes two pre-identity-commit crashes and intervening rejected dates on
Boot 3/4 with PostgreSQL Java 17/21, in addition to the retained AC5b post-commit proof.
The disposable coordination seam executes before, but never replaces, identity
decision code; its exact source/diff/JAR hashes are retained and it is not emitted
into product packages. Stale running records remain blocked until explicit
test-owned classification after confirming the owner is dead. H2 proves only
same-process behavior on both lines. This intentionally changes only opted-in
M5a job Java output on Boot 3 as well as previews; unrelated artifacts and every
migration byte remain unchanged. It relies on retained, untampered repository
history, not protection against external SQL edits/deletion or an adopter migration.
No new schema, automatic classification, recovery endpoint, reset, abandonment,
identifying date, dependency, or recovery-policy change is supplied.

History helper and platform exception types are selected explicitly in templates
when a valid domain name collides, without rewriting rendered Java or domain
references. Both-line compiled controls include `RuntimeException`; other
non-colliding generated packages retain their tested source bytes.

### 7.2 Restart reconciled with the reader — and its boundary
For opted-in handoffs the **destructive clear-on-start is removed**; restart resumes the reader from
its checkpoint and the **upsert** re-writes partially-committed rows idempotently — eliminating the
rev-1 clear-vs-checkpoint data-loss hazard **for rows within the run's input set**. But the reader is
a **paged live `findAll`** (F-supporting): source rows inserted/deleted after start shift pages, and
updates to already-passed rows are never revisited. Therefore:
- **v1 precondition (stated, not assumed):** the source is **immutable for the duration of a run** —
  the normal posture for a cutoff/quiesced scheduled batch. The §4.2 guarantee holds **only** under it.
- **No generic keyset reader in S2 v1 (§0.9 #42).** Generated canonical entities can use arbitrary
  id types and orderings; no universal insertion-stable upper bound can be inferred safely. A future
  reader may require an explicit, contract-backed immutable sequence/watermark, but S2 must not infer
  one or silently select entity-id ordering as a snapshot boundary.
- **Acceptance is split accordingly (§9):** **AC2** proves the guarantee with the source **held
  immutable** (the stated precondition); **AC2b** mutates the source and proves the **documented
  out-of-guarantee behavior**. Neither asserts a frozen input set that v1 does not materialize
  (§0 #11); AC2b remains an S3 boundary proof and is not converted by an S2 keyset option.

### 7.3 The upsert — shared invariant, per-profile spike (not one helper)
The staging write becomes the **same invariant** the outbox uses — *profile-pinned atomic conflict
handling keyed by the unique tuple, with the `UNIQUE` constraint as the fail-closed backstop* — **not
a single shared helper and not `MERGE`-by-assertion** (§0 #7). PostgreSQL: `INSERT … ON CONFLICT
(run_id, dedup_key) DO UPDATE …`. H2: the outbox's **ensure-row → update → same-transaction read**
shape adapted to staging, **or** a `MERGE` **if a dedicated spike proves it equivalent** — the exact
statement is pinned by a **blocking Slice-3 spike on both real PostgreSQL and generated-app H2
(`MODE=PostgreSQL`)**, never asserted here. `staging_row_id` stays the physical PK; `created_at` is
insert-only; `staging_status` resets to `READY` on re-write.

### 7.4 Durable batch metadata — one deterministic rule per profile (§0 #14)
Native restart needs durable `BATCH_JOB_*` tables, never provisioned today (F7). rev-2 left this as
"Flyway migration (or Boot initialization on H2)", which is two rules and overstates H2. The rule:
- **PostgreSQL profiles: Flyway-owned.** The batch metadata schema is an **`internal_schema` Flyway
  migration** (§6.1) — deterministic, regen-preserved, Change-Plan-visible; Boot's
  `initialize-schema` is pinned so it cannot double-create.
- **H2 profile: Flyway-owned but same-process restart only, and said so.** The profile-appropriate
  H2 Batch schema is emitted through the same deterministic internal-schema/Flyway ownership lane;
  Boot initialization is pinned off so there is one owner. The generated URL is
  **`jdbc:h2:mem:…`** (`target_profiles/catalog.py:44`) — in-memory. `DB_CLOSE_DELAY=-1` keeps it
  alive for the life of the JVM, so **batch metadata does not survive a process restart on H2**. H2
  therefore proves **restart-after-failure within one process**; it does **not** prove durable
  cross-process state. Only PostgreSQL proves state durability plus restart from an authoritative
  `FAILED`/`STOPPED` state (**AC7**); neither profile claims automatic recovery from a persisted
  running execution,
  and any H2 restart AC is scoped to the same-process case. Changing this would require an H2
  file/storage URL — out of scope, noted.

PostgreSQL durability means the repository state and execution context survive process replacement;
it does **not** mean every persisted state is immediately restartable. Native restart directly creates
a later execution only from an authoritative restartable state such as `FAILED` or `STOPPED`. A stale
a running execution remains deliberately non-restartable until the explicit operator classification
in §7.1. AC7 proves both the durability and this state boundary; it does not relabel persisted metadata
as automatic crash recovery.

### 7.5 Mixed staging+file jobs — fail-fast in v1, forward design deferred
Because the current file writer is restart-unsafe and mis-keyed (F4), **v1 fails generation fast** when
a `run_semantics` staging handoff shares a job with downstream-file output, with a clear diagnostic.
The **deferred forward design** (§11): make file output a **separate step that rebuilds the complete
file from committed run-scoped staging rows** after the staging step succeeds, with the **final path
keyed by `(runId, businessDate)`** and header/trailer counts/totals recomputed from staging — so the
file inherits the staging step's idempotency instead of the chunk's fragile in-line write.

### 7.6 Anti-downgrade — **RESOLVED** by the coordinated manifest 2.0 cut

`run_semantics` is a **safety** contract, so an Engine that does not implement it must reject the
package rather than silently generate legacy clear+insert (F6). The selected mechanism is a clean,
single-dialect cut to `schema_version: "2.0"`; no temporary or permanent `1.0` bridge is selected.

Enforcement is deliberately unified at the public boundary while preserving each entry-point shape:

- **Package entry points** run the bundled closed JSON Schema validation **before**
  `ProjectDefinition.model_validate()`: `load_project_definition()` and its callers in CLI
  `generate`/`plan`/`apply` and MCP `translate`/`generate`; Studio joins through V2-S. V2-E does
  not rely on Pydantic's permissive unknown-field behavior. This closes same-version
  forward-compatibility asymmetry: a post-V2-E, pre-M5a Engine rejects a later `2.0` package that
  contains `run_semantics` instead of silently dropping it.
- **Raw-schema entry points** enforce the same bundled closed JSON Schema:
  `validate_package()`, `validate_package_or_raise()`, optional CLI `--validate-schema`, and MCP
  `validate_manifest`. `manifest-v2.schema.json` must declare exactly `"enum": ["2.0"]` and retain
  fail-closed `additionalProperties` rules for contract-bearing objects.
- **Typed internal APIs** operate only after package validation and gain no duplicate gate:
  `generate_application(MetadataProject | KafkaMetadata)`,
  `build_change_plan(MetadataProject)`, `apply_change_plan(MetadataProject)`, and
  `translate_project(ProjectDefinition)`.

Generated apps remain runtime-independent because deployed generated apps do not read manifests.
The generated repository does, however, need auditable provenance. V2-E adds deterministic source
`manifest_schema_version` to the generated README for every archetype and to **normally refreshed**
generated files that already use the standard header, then to archetype-specific artifacts only
where those artifacts already exist. V2-E does not create a schema baseline, agent context, or audit
configuration merely to satisfy provenance, and it never retrofits immutable migration bytes:

| Existing generated artifact | CRUD | Passthrough router | Kafka integration | V2-E obligation |
|---|---|---|---|---|
| Normally refreshed files using standard generated headers | emitted | emitted | emitted | Record `manifest_schema_version` when the file is newly emitted or normally refreshed. This row excludes existing immutable Flyway migrations. |
| `README.md` | emitted | emitted | emitted | Record `manifest_schema_version` explicitly and deterministically. |
| Existing `V*.sql` Flyway migrations | retained by maintained CRUD packages | not emitted | not emitted | Preserve every prior migration byte-for-byte, including a pre-provenance header. Never retrofit `manifest_schema_version` or alter its checksum. |
| Newly emitted `V*.sql` Flyway migration | conditional on an approved CRUD apply | not emitted | not emitted | Record the current `manifest_schema_version`; existing migrations remain untouched. |
| `db/schema-baseline.json` | emitted | not emitted | not emitted | Record `manifest_schema_version` on CRUD greenfield generation or successful approved legacy adoption. For an existing managed package, update it atomically only after successful approved apply; ordinary regenerate preserves the baseline byte-for-byte. Do not add baselines to passthrough/Kafka. |
| `agent-context.md` | emitted | emitted | not emitted | Record `manifest_schema_version` for CRUD and passthrough. Kafka parity remains M4-owned and is not a V2-E prerequisite. |
| `AuditConfig.java` | emitted only when the CRUD target profile enables audit | not emitted | not emitted | Record `manifest_schema_version` when the file is emitted; do not broaden audit topology. |

V2-X asserts every applicable matrix cell and also asserts that V2-E does not introduce the
currently absent artifacts, rewrite prior migrations, or advance an existing baseline during
ordinary regeneration. The source field is distinct from `baseline_schema_version`,
`change_plan_schema_version`, and the opaque `manifest_hash`. A legacy CRUD baseline without the
field is surfaced as **unknown/pre-provenance** and requires the reviewed migration record below;
V2-E must not infer `1.0` from an old Engine version or hash. Greenfield generation and successful
approved legacy adoption create a `2.0` baseline. For an existing managed package, only successful
approved apply transitions the baseline atomically to `2.0`; rejection or failure leaves the prior
baseline unchanged. Passthrough and Kafka have no baseline to migrate.

Migration into the cut has two supported source forms:

V2-E is a **version-boundary cut, not a semantic-shape redesign**: its v2 manifest schema is
structurally equivalent to the pre-cut v1 schema except for schema identity/version metadata. M5a's
`run_semantics` field arrives only in M5a-S1. V2-X compares normalized v1/v2 schemas and fails if V2-E
introduces any other manifest-field delta; this is what makes the standalone conversion below exact.

1. **Saved Studio project JSON (`1.0`–`1.4`)** is reopened by post-V2-S Studio and exported as a v2
   package. Studio's project snapshot version remains `1.4`; Studio must surface an actionable
   Engine/manifest-version mismatch rather than a generic validation failure.
2. **Standalone/CLI-authored v1 manifest packages** are not importable as Studio projects and are
   never described that way. Before post-V2-E regeneration, an operator makes a reviewed copy of the
   complete package, changes only the root `schema_version` scalar from `1.0` to `2.0`, and runs both
   post-V2-E package and raw-schema validation. V2-X records the source/target manifest hashes and a
   path-level diff proving `/schema_version` is the only manifest change and all referenced contract
   artifacts are byte-identical. Any other required change or validation error fails the conversion
   closed for explicit human review; no value is inferred or silently rewritten.

| Producer / consumer | Pre-cut Engine | Post-V2-E Engine |
|---|---|---|
| **Pre-cut Studio (`1.0`)** | accepted | rejected with a `schema_version` diagnostic; reopen its saved Studio project and re-export through post-V2-S Studio |
| **Post-V2-S Studio (`2.0`)** | rejected with a `schema_version` diagnostic | accepted |

The full contract is active: Engine V2-E, Studio V2-S, and both V2-X stages are complete (§10.2).
The post-merge proof is recorded in the
[durable V2-X result](../test-results/manifest-v2-cut-v2-x-2026-08-16.md).

## 8. Failure-mode analysis

| Failure | Pre-M5a baseline | M5a implementation / boundary |
|---|---|---|
| Job fails mid-run and is authoritatively `FAILED`/`STOPPED`, then retried | new instance, `clear(newRunId)` deletes nothing ⇒ **orphaned/duplicated** rows | same `runId` (date frozen) ⇒ **restart resumes**; upsert re-writes committed rows; **no dup/loss for the run's input set** (§4.2 bound) |
| Process dies abruptly while execution remains running | no durable restart contract | PostgreSQL retains execution parameters/context; direct relaunch **fails closed with 409, the execution id, and actual observed `STARTING`/`STARTED`/`STOPPING` status**. After an authorized operator confirms no owner and classifies it `FAILED`, restart validates the original durable date even before frozen-context commit. No startup auto-recovery or generated recovery endpoint (§7.1/§7.1a/§7.4). |
| Same completed run re-POSTed | re-runs ⇒ duplicate work/file | **409** |
| Concurrent triggers, same run | two instances ⇒ duplicates | **409** (JobInstance serialized) |
| Same runId, different businessDate | silent (LocalDate.now drift) | FAILED/STOPPED and restartable ⇒ tasklet fails before staging against original persisted parameters, including missing frozen context. Retained rejected attempts cannot rebind or poison original-date retries. Running ⇒ 409 with actual status; COMPLETED ⇒ launcher 409. A lookup race returns state-changed/unavailable rather than inventing state (§7.1a). |
| Caller runId has leading/trailing whitespace | Batch and physical equality can diverge, especially with padded PostgreSQL `CHAR(n)` | **4xx before launch** for every physical string type/profile; no trimming, Batch row, or staging write. The exact accepted canonical value is shared by Batch and staging (§7.1/AC5c). |
| Caller runId exceeds the physical or Batch parameter bound | launch or staging persistence can fail after identity work begins | **4xx before launch** using `min(physicalMax, 2500)` and Java UTF-16 length; `TEXT` is capped by Batch. Console and server expose the same effective maximum (§7.1/AC5c). |
| Source mutated mid-run | silent skip/dup | **outside the guarantee** (stated); S2 v1 selects no generic keyset/frozen-bound inference (§7.2) |
| Mixed staging+file handoff | tail-only file, same-day overwrite (F4) | **generation fails fast** (§7.5) |
| Reprocess a completed date | whole-table clear or orphan | **new runId** (v1); `replace` deferred (§11) |
| Enable on existing managed package | — | additive `internal_schema` migration via Change-Plan; disable carries schema forward (§6.1) |
| M5a package run through pre-cut Engine | silent legacy downgrade if the version is not gated (F6) | **Rejected by `schema_version`**; package and raw-schema entry points are both proven in V2-X/AC9 (§7.6) |
| M5a package run through post-V2-E, pre-M5a Engine | same accepted `2.0` version could let permissive Pydantic silently drop `run_semantics` (F6) | **Rejected by mandatory closed-schema validation before model loading**; Stage 2 pins and proves the immediate prior Engine through both paths (§7.6/§10.4) |

## 9. Proof plan + acceptance criteria
Runtime, on **both H2 and PostgreSQL** (the original gap was that nothing ran the job, §1):
- **AC1** absent `run_semantics` ⇒ generation **byte-identical to a pinned post-V2-E, pre-M5a
  baseline**. Pin the exact Engine SHA, generation-run input, manifest bytes, and package-state
  assumptions. The version cut is outside this comparison: changing `schema_version` changes
  `manifest_hash`, and `manifest_hash` is one of the eight direct `plan_hash` inputs
  (`change_plan.py:97-108`). `engine_version` is rendered in the baseline and Change Plan but is
  excluded from that direct hashed payload; a prior baseline's Engine version may still affect
  `baseline_hash`. `package_state_hash` excludes `db/schema-baseline.json`
  (`change_plan.py:743-751`).
- **AC2 (positive, in-guarantee)** fail-inject mid-job, restart the same `runId` **with the source
  held immutable** — the precondition under which the guarantee is stated (§4.2/§7.2) ⇒ assert
  exactly-once / last-write-wins per `(run_id, dedup_key)` and no loss. *(rev-2's AC2 mutated the
  source and then asserted a "frozen input set" that baseline v1 never materializes — §0 #11.)*
- **AC2b (boundary, out-of-guarantee)** the same restart **with the source mutated** between failure
  and restart (insert / delete / update) ⇒ assert the **documented boundary behavior**, demonstrating
  that such mutations are outside the guarantee rather than silently claimed safe. S2 v1 selects no
  generic keyset/frozen-bound reader, so AC2b does not promote any mutation class into guarantee.
- **AC3** re-POST a COMPLETED runId ⇒ **409**, staging unchanged.
- **AC4** two concurrent triggers, same runId ⇒ one runs, one **409** (JobRepository-serialized,
  §7.1). Prove diagnostics use the repository-observed `STARTING`, `STARTED`, or `STOPPING` status;
  a terminal transition between exception and lookup returns `batch_execution_state_changed`, and a
  missing lookup returns `batch_execution_state_unavailable`. No response fabricates `STARTED` or
  parses exception text.
- **AC5 — original durable date on every restart.** Same runId + different `businessDate`,
  **asserted per instance state** (§0.4 #24, §0.9 #41, §0.10 #44): **FAILED/STOPPED and restartable**
  must fail the job **before any staging write**; latest execution **STARTING/STARTED/STOPPING** ⇒
  the running-state **409** with its execution id and actual status; a post-exception terminal/missing lookup ⇒ the
  state-changed/unavailable **409**; **COMPLETED** ⇒ **409** from the launcher. In every state, **no
  second JobInstance is created**. Prove both pre- and post-identity-commit boundaries on Boot 3/4
  with PostgreSQL Java 17/21. Retain multiple early crashes and intervening rejected attempts, then
  complete an original-date retry in the same instance. Add malformed/missing/conflicting and
  shuffled-history controls (§7.1a); AC5b alone is insufficient.
- **AC5b — abrupt-death boundary plus explicit recovery.** On PostgreSQL, kill the process after the
  run-identity tasklet commits and while the data step is `STARTED`. Prove the frozen
  `businessDate`, `BATCH_JOB_EXECUTION=STARTED`, completed identity step, and started data step
  survive. Prove direct relaunch with both the same and a different date fails closed with
  `JobExecutionAlreadyRunningException`, before the tasklet or staging writer runs, and returns the
  execution id plus actual observed `STARTED` status and ownership-review requirement. Then, in a
  separate evidenced operator action after confirming no owner is running, classify the stale
  execution `FAILED`; restart with a different date and prove the identity tasklet rejects the
  mismatch before any staging write. Exactly one JobInstance exists throughout. The operator action
  is not an automatic startup mutation and not a generated REST endpoint. This proves only the
  **post-identity-commit boundary**, not behavior before that commit or completion of all AC5 cases.
- **AC5c — physical/Batch run-ID equivalence and storage bound.** On both PostgreSQL and generated-app
  H2, use an opted-in handoff whose physical run-ID column is `CHAR(8)`. Submit `RUN-1` and prove the
  exact value is used for both the identifying JobParameter and staging writer. Submit `RUN-1 ` and
  ` RUN-1` and prove each receives the stable pre-launch 4xx, creates no JobInstance/JobExecution,
  and performs no staging write. Repeat the canonicality guard for `VARCHAR` and `TEXT`. Then prove:
  a 2500-UTF-16-unit value is accepted and 2501 is rejected for both `TEXT` and a physical
  `VARCHAR(3000)`; a supplementary character (Java length 2) is rejected for H2 `VARCHAR(1)` and
  accepted for H2 `VARCHAR(2)`. Every refusal occurs before Batch/staging mutation. The console hint
  equals the computed effective maximum. Negative controls must fail if either the server-side
  `strip()` equality or effective-max guard is removed; the console is not the authority.
- **AC6a (additive lifecycle only)** the §6.1 migration set: greenfield · enable-on-managed ·
  disable-retained · re-enable with no duplicate migration · inventory collision ·
  **NOT-NULL-missing fails generation**. With several new handoffs, two generations with permuted
  manifest/emitter traversal produce the same `m5a-staging-*` ids, baseline bytes, and migration
  order.
- **AC6b (rename refusal, not a migration-success case)** annotated and unannotated handoff rename
  plus staging-table rename each produce the expected `unsafe`/`destructive` Change Plan and
  `appbuilder apply` refusal. Assert **no package mutation**: `db/schema-baseline.json`, the complete
  Flyway inventory (no new `V*`; all existing paths and bytes), and all generated/developer files
  are unchanged. Adding an
  out-of-band rename migration is explicitly not considered completion and does not unblock the
  plan; recovery is revert-or-deferred baseline reconciliation (§6.1/§11).
- **AC7** PostgreSQL persists `BATCH_JOB_*` state and execution context across process replacement;
  H2 remains same-process only. Prove the deterministic `pkg-batch-metadata` singleton and prove
  native restart after an authoritative `FAILED` or `STOPPED` state. Also prove that a persisted
  running state fails closed with actual repository status and ownership review rather than being
  called automatic crash recovery. The
  singleton records `schema_contract_version` and deterministic `content_sha256`; identical inputs
  retain it byte-for-byte, SQL fingerprint drift without a version bump fails as an integrity error,
  and a version/fingerprint transition fails closed without overwriting the baseline.
- **AC8** the PG `ON CONFLICT` and H2 statements are **spike-proven** against a real PG container and
  generated-app H2 — not asserted from source.
- **AC9 — version and same-version feature anti-downgrade proof.** Use three explicitly labelled
  fixtures: an ordinary v2 fixture proving a pinned pre-cut Engine rejects `2.0`; a v1 fixture proving
  the post-V2-E Engine rejects `1.0`; and a `2.0 + run_semantics` fixture proving the pinned
  post-V2-E, pre-M5a Engine rejects the unsupported block while post-M5a-S1 accepts it. Exercise both
  package and raw-schema paths for all three. Version-crossing diagnostics must identify
  `schema_version`; the same-version diagnostic must identify `run_semantics` as unsupported/unknown.
  Rejection for an unrelated field is insufficient. Run each pinned Engine from its own checkout and
  interpreter, not through another phase's environment.
- **AC10** a `run_semantics` staging handoff sharing an entity-scoped EOD job with file output for
  that same entity **fails generation fast**; file output for another entity remains valid.
The identities **`staging-restart`**, **`staging-idempotency`**, and
**`staging-mixed-reject`** remain reserved for M3. Actual scenario registration waits for the M3 pack;
M5a-S4 does not create a registry or a second harness.

## 10. Roadmap + cross-design sequencing

### 10.1 M5a slices and cross-design sequencing

| Slice | Content | Independently useful as |
|---|---|---|
| **M5a-S1 — DELIVERED** | After complete V2-X: CRUD-only `run_semantics` schema + the v2 anti-downgrade gate (§7.6) + string run-ID and order-independent `dedup_key` validation from existing `ValidatedStagingDdl` metadata + entity/job-scoped mixed-output fail-fast + an interim generate/plan/apply refusal until S2/S3 | contract validation; AC1/AC9/AC10 *(AC5 stays in M5a-S2 — it needs the run-identity tasklet, §0.5 #28)* |
| **M5a-S2 — DELIVERED** | Versioned/fingerprinted package-singleton Batch-metadata `internal_schema` migration + per-job trigger/card contract (`POST /batch/run/{jobName}` with closed JSON `runId`/`businessDate` body and `FORM`/`JSON_BODY` for opt-in; legacy remains no-body `NONE`/`NONE`) + pre-launch run-ID canonicality and effective physical/Batch UTF-16 width validation + **`runId` as the sole identifying parameter** + the **run-identity tasklet** (`allowStartIfComplete(true)`) validating original durable non-identifying `businessDate` before staging, including absent frozen context (§7.1a) + completed/actual-running-state/lookup-race diagnostics. No generic keyset reader or automatic stale-execution mutation. S3 retires the S1 public execution refusal. | native restart for authoritative `FAILED`/`STOPPED`; original durable date authority; physical/Batch identity aligned; running states fail closed without fabricated status (AC3/AC4/AC5/AC5b/AC5c/AC7) |
| **M5a-S3 — DELIVERED** | Deterministically allocated per-handoff Engine `UNIQUE` `internal_schema` migration + PostgreSQL `ON CONFLICT` and H2 ensure-row/update/read upserts (spike-pinned) + remove destructive clear-on-start; `resume`; retire the interim public execution refusal | idempotent retry/restart (AC2/**AC2b**/AC6a/AC6b/AC8) |
| **M5a-S4 — DELIVERED** | Grade the existing harness check per handoff: opted-in failures are gated `ERROR` results and legacy findings remain advisory `WARNING` results. Reserve `staging-restart`, `staging-idempotency`, and `staging-mixed-reject`; actual registration remains M3-owned. | the opt-in gate holds without a second harness |

M5a-S1 through M5a-S4 remain sequenced in order. Their V2-S and complete post-merge V2-X prerequisite
is satisfied (§10.2). M5a-S1 delivers the bounded contract-validation slice and M5a-S2 delivers the
Batch identity/restart layer; M5a-S3 delivers the staging idempotency boundary and retires the public
execution refusal for valid opted-in packages; M5a-S4 delivers the per-handoff blocking harness gate.
The four implementation slices are delivered; rev-15 adds original durable date authority and
early-crash proof (§7.1a). M3 scenario registration remains deferred. This is not automatic recovery
or protection against externally edited/deleted repository history.

M5a's `UNIQUE`/batch-metadata `internal_schema` entries and the outbox's use the **same baseline
mechanism** (event-delivery §6.1); the upsert is the **same invariant** (§7.3) with each statement
spike-pinned — **not** one prematurely shared helper. M5a-S3 lands **first**, establishing the one
generic `internal_schema` foundation that the outbox build then consumes, per
[`suite-security-review-backlog.md`](../suite-security-review-backlog.md) §8: *"M5a lands one generic
foundation; event delivery consumes it. Do not implement twice."* The event-delivery design already
sequences by the canonical roadmap guardrail and needs no change for this.

### 10.2 Manifest-v2 phases and controlled cutover

The manifest-version prerequisite is delivered as three coordinated phases before the four M5a
implementation slices:

| Phase | Required outcome |
|---|---|
| **V2-E** | Engine becomes a `2.0`-only contract: add `manifest-v2.schema.json`, remove the active v1 schema, make closed-schema validation mandatory before every package-model load, enforce package/raw-schema and MCP/CLI parity, define the reviewed standalone-v1-package conversion, emit explicit deterministic `manifest_schema_version` provenance without rewriting prior migrations or bypassing apply-owned baseline transition, migrate examples/fixtures, and prove package-data contents. |
| **V2-S** | Studio exports only `2.0`; project snapshots remain `1.4`; Engine/manifest mismatches are actionable; snapshot migration/reopen proofs cover retained Studio projects without claiming exported-package import. |
| **V2-X** | Run paired-branch proof, including both v1 source forms and package/raw-schema unknown-field parity, then rerun the full proof against the actual merged Engine and Studio SHAs. V2-X is complete only after the post-merge run passes. |
| **M5a-S1–M5a-S4** | The four M5a slices are delivered in the §10.1 sequence; M3 owns later registration of the three reserved scenario identities. |

V2-E, V2-S, and both V2-X runs are complete. The controlled merge/freeze sequence below remains the
normative procedure that was followed; the exact SHAs and results are recorded in the
[durable V2-X result](../test-results/manifest-v2-cut-v2-x-2026-08-16.md).

Controlled cutover:

1. Prepare Engine and Studio branches in parallel.
2. Run paired-branch V2-X.
3. Freeze both repositories operationally.
4. Merge Engine first.
5. Merge Studio immediately after.
6. Rerun V2-X against the actual merged SHAs.
7. Keep the freeze until that proof passes.
8. On failure, revert Studio first, then Engine, rerun paired proof, and only then reopen use.

The domain-neutral canonical CI-fixture implementation is sequenced **after complete V2-X** and must
be authored directly at manifest `2.0`; it is not a bridge fixture.

### 10.3 Migration inventory

At Engine `68885ba`, 44 test files contain `schema_version`, 68 contain the literal `"1.0"`, and 38
contain both. V2-E requires a categorised inventory and deliberate migration, never a broad string
replacement.

The delivered Engine migration is recorded in
[`manifest-v2-engine-cut-migration-inventory.md`](../manifest-v2-engine-cut-migration-inventory.md).

The Engine inventory includes the version constant, metadata default, hardcoded schema path, JSON
Schema identity/enum/closed-object rules, package-loader validation order, MCP schema tool, CLI help,
all six current examples, smoke manifests, golden/direct metadata, and package-data behavior. It also
includes generated provenance surfaces according to the §7.6 archetype matrix: normally refreshed
headers and universal README; immutable prior versus newly emitted CRUD migrations; the
greenfield/adoption/apply-owned CRUD baseline transition; CRUD/passthrough agent context; and
conditional CRUD `AuditConfig`. Kafka agent-context parity remains outside V2-E under M4. The Studio
inventory includes the exporter, two PR-template assertions, Engine-alignment test, requirements
document, proof scripts, and tests. Active Engine policy/current-state surfaces include the root README,
appbuilder context, MCP design, glossary, upstream-integration boundary, edge-contract roadmap,
generated-app roadmap, manifest-schema document, and tracker candidate wording.
Historical design/evidence references must be classified rather than rewritten indiscriminately.

The following versioned contracts remain unchanged:

- `BASELINE_SCHEMA_VERSION = "1.0"`;
- `CHANGE_PLAN_SCHEMA_VERSION = "1.0"` and `change-plan-v1.schema.json`;
- Studio project snapshot `1.4` and the Studio Change Plan v1 reader/tests;
- Evidence Trail `1.1`;
- L5 report/run schemas and suite-baseline schemas;
- XML declarations and OpenAPI document versions; and
- historical acceptance evidence.

V2-E removes `manifest-v1.schema.json` from active package data. A built-wheel assertion must prove
that the v2 schema is present, the v1 schema is absent, and Change Plan v1 remains present.

### 10.4 Two-stage proof

**Stage 1 — V2-X:**

- The post-V2-E package path accepts v2 and rejects v1, always running closed-schema validation
  before Pydantic model construction.
- The post-V2-E raw-schema/MCP path accepts v2 and rejects v1.
- Under accepted version `2.0`, the same deliberately unknown nested field is rejected through both
  package and raw-schema paths with the same field path; removing the mandatory package-schema call
  makes this proof fail.
- `get_manifest_schema()` and `get_manifest_schema("2.0")` return an enum exactly equal to
  `["2.0"]`; v1 requests fail.
- A normalized v1/v2 schema comparison proves V2-E changes only schema identity/version metadata;
  no semantic manifest field is added, removed, or modified in the cut.
- A pinned pre-cut Engine rejects an ordinary v2 package through both mechanisms with a
  version-specific diagnostic.
- All three archetypes generate from v2 packages.
- Studio project snapshots `1.0` through `1.4` reopen and export v2; no exported-package import is
  claimed.
- A standalone v1 package follows the reviewed copy-and-version conversion in §7.6. The proof records
  source/target manifest hashes, asserts `/schema_version` is the only manifest path changed, proves
  referenced artifacts byte-identical, and passes both post-V2-E validation paths.
- Both supported source forms can drive post-V2-E Change Plan/apply against a package generated from
  a v1 baseline without unsafe or destructive schema/contract deltas caused merely by the version
  cut.
- CRUD output records `manifest_schema_version: "2.0"` in normally refreshed standard headers,
  README, `agent-context.md`, and `AuditConfig` when the selected profile emits it. Existing
  migrations remain byte-identical and may retain pre-provenance headers; each newly emitted
  migration records the current manifest version.
- CRUD greenfield generation and successful approved legacy adoption create a baseline containing
  `manifest_schema_version: "2.0"`. Ordinary regeneration of an existing managed package leaves its
  baseline byte-identical. Successful approved apply updates the baseline atomically only after
  generation, harness, and migration success; rejected or failed apply leaves it unchanged.
- Passthrough output records the same value in existing standard headers, README, and
  `agent-context.md`; it continues to emit neither a schema baseline nor `AuditConfig`.
- Kafka output records the same value in existing standard headers and README; it continues to emit
  no schema baseline, `agent-context.md`, or `AuditConfig`. Kafka agent-context parity remains M4.
- Per-archetype tests distinguish `manifest_schema_version` from baseline, Change Plan, Evidence
  Trail, and Studio snapshot schema versions, prove deterministic bytes, and assert both required
  presence and intentional absence from the §7.6 matrix. CRUD tests additionally pin prior migration
  bytes/checksums, prove new migration provenance, prove ordinary regenerate cannot rewrite a legacy
  baseline, and prove only greenfield generation or successful approved apply/adoption establishes
  the `2.0` baseline state. A legacy CRUD baseline missing the field remains
  unknown/pre-provenance until that approved transition; the value is never guessed.

**Stage 2 — M5a-S1:**

- A pre-cut Engine rejects a v2 package containing `run_semantics` because of `schema_version`.
- A pinned post-V2-E, pre-M5a Engine rejects that same `2.0` package through both package and
  raw-schema paths because `run_semantics` is unknown; the diagnostic names the field.
- The post-M5a-S1 Engine accepts and translates it through both validation paths, while the interim
  S1 execution gate refuses generate/plan/apply. S3 retires that interim gate only after the S2
  identity layer, uniqueness migration, profile-specific upsert, and clear removal are all active.

### 10.5 Active-text propagation sweep

V2-E/V2-S must update active rev-9/current-state statements in the design header redlines and
guardrails, §5.2 package-version wording, §7.6, the failure-mode table, AC1 and AC9, the M5a-S1 row
and prerequisite, package/raw-schema parity, standalone-package migration guidance, generated
provenance, §13.2, and the final decision. Historical correction records in §0.0–§0.8 remain
unchanged even when they describe the decision as formerly open. Verification must exclude that
historical region; a raw repository-wide zero-match assertion would contradict deliberate history
preservation.

## 11. Deferred / rejected
- **`restart: replace`** — needs a **run-control ledger / attempt key + a dedicated replace-init step**
  (logical-run identity separate from execution identity), because a completed JobInstance cannot re-run
  (§0 #2). Deferred with that sketch; v1 uses a new runId for reprocess.
- **Restart-safe downstream file** — the §7.5 rebuild-from-staging step + re-keyed final path; v1
  fails fast on mixed jobs instead.
- **A destructive-migration + baseline-reconciliation protocol** — today `appbuilder apply` is
  additive-only (`apply.py:50,:70-80`). M5a v1 therefore treats staging-handoff/table renames as
  unsupported end-to-end, not as "manual SQL completes it." A future design must bind an explicitly
  reviewed destructive plan to the exact old baseline/package-state hashes, verify an immutable
  sequential Flyway migration and its checksum, apply or record its successful application, and
  atomically update the Engine-owned entry (recorded identity, SQL fingerprint, migration
  high-water mark, and baseline hash). Any mismatch must leave the package and baseline untouched.
  Until that protocol exists, annotation provides precise attribution only and AC6b proves refusal.
- **Automatic multi-instance stale-execution recovery** — requires an ownership mechanism such as a
  lease/heartbeat or equivalent fencing before any process may classify another execution failed.
  Startup auto-failure, a generated unauthenticated recovery endpoint, and a single-replica assumption
  are rejected for v1.
- **Keyset/high-water incremental reads** — not selected for S2 v1 because arbitrary generated entity
  ids provide no universal insertion-stable watermark. A future design must bind the cursor to an
  explicit source contract rather than infer it. This remains separate from the immutable-source
  precondition and AC2b boundary.
- **Other deferred surfaces** — non-`embedded` topologies · scheduling/orchestration entry points
  (REST stays generated; the invoker is adopter-owned, documented) · `idempotency_key` identity-role
  activation (Phase-4).

## 12. Why two designs (M5a vs the outbox), not one
Both harden generated persistence idempotency and share the **internal-schema + upsert invariant**, but
the surfaces differ: the outbox captures domain events inside the CRUD **service** transaction; M5a
hardens the **batch staging** path (chunk-oriented, restartable, scheduled). Their triggers, transaction
models (service vs chunk), and restart lifecycles differ enough that one document would blur the batch
semantics that are M5a's whole point — they **share primitives, not a spec**.

## 13. Maintainer decisions
1. **RESOLVED (was open):** the `UNIQUE` constraint is **Engine-generated as an `internal_schema`
   migration**, not author-declared — forced by the `ddl_sha256`/regen-apply model (§0 #4). NOT-NULL
   stays author-declared, validated fail-closed.
2. **RESOLVED — coordinated manifest 2.0 anti-downgrade cut.** The maintainer selected the clean,
   pre-adopter V2-E/V2-S/V2-X cut specified in §7.6 and §10.2: the post-V2-E Engine supports only
   `2.0`, the post-V2-S Studio exports only `2.0`, and no `1.0` compatibility bridge is retained.
   V2-E also makes closed-schema validation mandatory before package model loading, provides the
   reviewed standalone-package conversion path, and emits explicit manifest-version provenance;
   V2-S owns Studio snapshot reopen/re-export. V2-E, V2-S, complete post-merge V2-X, and all four M5a
   implementation slices are delivered.
3. **RESOLVED — opt-in upgrades the harness warning to a blocking error for that handoff.** M5a-S4
   selects the lean option: failed opted-in checks are `ERROR`; legacy findings remain `WARNING`; mixed
   projects retain per-handoff severity without cross-promotion.
4. **`replace` + run-control-ledger** — build in a later slice, or leave reprocess as "new runId"
   permanently? (Lean: defer, revisit on adopter demand.)
5. **Build timing — RESOLVED:** rank 2; M5a Slice 3 lands **before** event delivery and establishes
   the generic `internal_schema` foundation that the outbox consumes. Do not sequence these builds
   concurrently or reimplement that foundation; M1 security is already complete.
6. **M5a-S2 abrupt-restart posture — RESOLVED for v1:** a persisted running execution fails closed
   with its actual repository status and an ownership-review requirement. An authorized operator may
   classify it only after independently confirming no owner remains. Startup auto-failure and
   generated recovery endpoints are rejected; automatic multi-instance recovery is deferred until
   ownership fencing exists (§0.9/§0.10/§7.1).

---

## Final decision

**Add opt-in, staging-only production run-semantics to generated staging-handoff batch jobs —
durable caller-supplied **`runId` as the sole identifying JobParameter**, accepted only when
non-blank, boundary-whitespace-free, and within the lesser of its physical width and Spring Batch's
2500-UTF-16-unit parameter limit, then used unchanged for Batch and staging (with a non-identifying,
frozen-and-compared `businessDate`), **authoritatively FAILED/STOPPED-run `resume`**
made reachable and resume-safe by removing destructive clear-on-start, and idempotency via an
**Engine-generated `UNIQUE(run_id, dedup_key)` `internal_schema` migration** + a profile-pinned atomic
upsert reusing the outbox invariant (spike-pinned per profile) — bounded by an explicit
immutable-source-during-run precondition, with durable batch metadata (PostgreSQL Flyway-owned; H2 same-process
only), explicit fail-closed handling with actual repository state when abrupt death leaves an
execution running, and **fast failure on mixed staging+file jobs** (whose restart-safe
file rebuild is a deferred forward design). `replace` is deferred behind a run-control-ledger design.**
Byte-identical for handoffs that do not opt in, measured only against a pinned post-V2-E, pre-M5a
baseline (AC1); effectively-once staging state under the stated bound; exactly-once *processing*
never claimed. S2 v1 does not auto-classify stale executions, expose a generated recovery endpoint,
assume one replica, or infer a generic keyset watermark; automatic crash recovery waits for ownership
fencing. The anti-downgrade prerequisite is **resolved in design** as the coordinated,
single-dialect manifest 2.0 cut (§7.6/§13.2). Engine V2-E, Studio V2-S, and paired-branch plus
post-merge V2-X are proven, so the coordinated cut is complete; M5a-S1 contract validation, the
bounded M5a-S2 Batch identity/restart layer, M5a-S3 staging idempotency, and the M5a-S4 opt-in blocking
harness gate are delivered. The S1 public execution gate is retired for valid opted-in packages, and
the approved four implementation slices are delivered. Rev-15 establishes original durable date
authority before and after identity commit with complete retained history (§7.1a), without changing
dead-owner recovery policy or claiming protection against external history edits/deletion. The three
reserved scenario identities remain deferred to M3, which will consume the existing harness rather
than create a second one.
