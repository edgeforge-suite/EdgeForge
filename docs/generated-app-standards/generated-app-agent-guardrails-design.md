# M4 — Generated-App Enterprise Agent Guardrails: Design

> **Status:** DESIGN **rev-5** — closes the sole remaining redline from Codex's rev-4 re-review @
> `72ee6ce` (verdict APPROVE-WITH-ONE-REDLINE, *"after that correction: APPROVE-FOR-GATE"*): the tool
> stub's **self-attested hash** (§5.5), removed in favour of comparison against an independently rendered
> canonical template. rev-4's guard/registry fixes, rev-3's maintainer scope clarification, and rev-1's
> four source errors all remain closed and are not reopened (§0). Awaiting maintainer gate; build follows
> as its own PRs.
> **Tracker:** `docs/enterprise-readiness-roadmap.md:138` (must-have **M4**, effort `M`); order
> `M1 → M5a → M2/M6 → M3 → M4 → M5b` (`:172`); tracker `M4-generated-app-agent-guardrails`
> `depends_on: ["done-C1-agent-context"]` (`docs/tracker/suite-tracker.json`). Ties to **M5b** (`:139`).
> **Goal:** make "compatible with adopter-approved coding-assistant workflows" enterprise-safe. Keep
> `agent-context.md` factual/deterministic; add the guardrails an org needs before letting a repo-aware
> assistant loose on a generated app. **Prose advising an agent is the weakest layer — prefer
> machine-enforced guardrails.** Rev-2's lesson: *claiming* machine enforcement is easy; **earning** it
> means a guard on every write, prune, and rollback path. Rev-3's lesson: **scope the carry-through to
> what Studio actually authors** — a generic artifact transport was never the ask. Rev-4's lesson: a
> guardrail's **mechanics** decide whether it holds — resolving a path before checking it forfeits the
> check, and recording what was *written* forfeits what was *preserved*. Both were one word wide.
> Rev-5's lesson generalizes all three: **a guardrail must not source its evidence from the side it guards
> against** — the *evidence rule* (§0.4). A file cannot vouch for itself; compare against something the
> untrusted side cannot reach.
> **Grounding:** Engine `origin/main` @ **`4660acb` (2026-07-14)**; Studio cites marked. Everything not
> cited is **PROPOSED**.
> **Redlines honored:** no manifest-v2 semantic change · no LLM/provider involvement · nothing fabricates an
> enterprise's rules · tool-specific agent files stay opt-in.

---

## 0. Correction log

### 0.1 rev-1 → rev-2 (source errors — closed, not reopened)
| rev-1 claim | Corrected fact |
|---|---|
| "`referenced_paths()` consumed **only by tests**" | **REFUTED.** `_validate_local_paths` (`contracts/manifest.py:1199-1210`) iterates it and raises `FileNotFoundError`; called from `load_project_definition:1195`, entered via `metadata/translation.py:219-224`. *(rev-1's grep excluded `contracts/manifest.py` — the file holding the consumer.)* Missing-reference fail-fast is therefore **redundant and removed**. |
| "Emitters receive `source_manifest` ⇒ no metadata-layer change" | **REFUTED.** `source_manifest: str` (`build_emitter.py:35,:110,:449`); `cli.py:198,:226` pass `str(manifest_path)`. → prerequisite **B0**. |
| "Policy seam is machine-enforced **by construction**" | **REFUTED.** `_restore_package_snapshot` (`apply.py:395-417`) is ownership-blind; `_skip_apply_rollback_path:420` skips only build/VCS dirs; `file_writer.py:1-10` documents deferred sinks. → §4 **earns** it via a guard. |
| "`service/**` = developer-owned" | **REFUTED.** `{Entity}ServiceBase.java` generated (`java_emitter.py:700`) vs `{Entity}Service.java` developer (`:713,:731`). → §5.1 facts registry. |

### 0.2 rev-2 → rev-3 (scope + design contracts)
| rev-2 position | rev-3 correction |
|---|---|
| "Copy **each** `legacy_references` entry" | **OVER-SCOPED — corrected by maintainer.** The manifest contract accepts *any* relative path (`manifest-v1.schema.json` `legacy_references.items → $ref relativePath`) and the canonical example carries a **binary**: `docs/repo-blueprint.md:504-507` lists `legacy/xyz-notes.md` **and** `legacy/field-mapping.xlsx`. An XLSX can take neither an XML/Markdown header nor UTF-8 round-tripping. **M4 is not a generic artifact transport** — it carries the **Studio Step-6 Legacy Notes** only (§3). Binary/media-type/sidecar-inventory requirements are **removed**, not solved. |
| Destination "preserving the reference's relative subpath" | **AMBIGUOUS** (`legacy/foo.md` → `docs/legacy/foo.md` or `docs/legacy/legacy/foo.md`?). Fixed: **`docs/legacy/<same filename>`** (§3.3). |
| "`RESERVED_ADOPTER_PATHS` guard" (named constant) | **UNDER-SPECIFIED.** Both guard entrypoints take only a path — `write_generated_file(path, content, *, ownership)` (`file_writer.py:22`) and `_skip_apply_rollback_path(path)` (`apply.py:420-422`, matching on `path.parts`). rev-3 defines the **root-relative guard contract** (§4.1). |
| "P1a-2 sink coverage is a **tracked** dependency" | **FALSE.** Roadmap M4 (`:138`) is effort `M` with no such prereq; tracker M4 `depends_on: ["done-C1-agent-context"]` only. rev-3 **absorbs a complete mutation-sink inventory + guard retrofit into B2a** and flags the effort implication (§8, §10.4). |
| §5.1 renders from "the planned output inventory" | **DOES NOT EXIST.** `engine.py:168-177` emits build files (incl. agent-context) **before** `emit_java_sources` (`:178+`); emitters write directly, with no artifact plan. rev-3 **picks the lifecycle** (§5.1). |
| B4 "semantics to be designed" | **DECIDED NOW** (§5.5) — the build PR implements a decision, it does not make one. |
| §3.8 "no provider/network egress — the Engine sends nothing anywhere" | **TOO BROAD.** Engine fetches remote specs: `ingestion/openapi_fetcher.py` `fetch_openapi_spec(url)` → `urlopen`. Narrowed to a carry-through-scoped claim (§3.8). |
| "byte-verbatim" (§3.2/E10) | **IMPRECISE.** Only the **body** is preserved; the emitted **file** is header+body (§3.4). |

### 0.3 rev-3 → rev-4 (guardrail mechanics — both were self-defeating as written)
| rev-3 position | rev-4 correction |
|---|---|
| §4.1 "**Canonicalize** both … (`resolve()`) … compute the **root-relative** path … then **match**" | **SELF-DEFEATING ORDER.** `resolve()` follows the *final* component. If root `AGENT-POLICY.md` is a symlink to `root/other-file`, resolving first yields root-relative `other-file`, the reserved-name comparison **no longer matches**, and the write proceeds *through the reserved pathname* — mutating what the policy file reads as. The out-of-root check does not catch this: the alias never leaves the root. rev-4 splits it into **two independent checks** — lexical reservation (before following the final link) + resolved containment (§4.1). |
| §5.1 "emitters **record** each artifact they **write**" / §11 renders "the **actual emitted inventory**" | **OMITS PRESERVED FILES.** `write_generated_file(..., ownership="developer")` **returns without writing** when the file exists (`file_writer.py:43-44`), and that path is **live in production** — `_write_java_file` is a thin passthrough to the sink (`java_emitter.py:823-824`) and `:731` passes `ownership="developer"` for `{Entity}Service.java`. So a write-keyed registry lists the developer seam on greenfield and **drops it on regenerate** — an inventory that depends on disk state, breaking both the map and "same manifest ⇒ same set." rev-4 redefines it as the **declared artifact contract** (§5.1). |
| §4.2 "the **five** direct-writing emitters" (from `file_writer.py:1-10`) | **INCOMPLETE LIST.** Verified further unrouted sinks: `shutil.copyfile` (`java_emitter.py:9266,:9311,:9354,:9390`), `write_bytes` (`:9303,:9317`), backup-write + `unlink` (`:843-844`), `migration_path.unlink()` (`sql_emitter.py:99`). A prose list regresses; rev-4 grounds B2a in a **repo-wide audit + an enforced no-new-unguarded-sink test** (§4.2, AC1). |
| §5.5 "content hash" (undefined) | **UNDER-SPECIFIED** — a hash whose domain is unstated can't classify. Defined in §5.5: canonical body **excluding** header/hash metadata, **recomputed** never trusted, absent/unparseable ⇒ treated as edited. |
| §3.6 prune "acts on generated-marked files under **`docs/legacy/**`**" | **OVER-BROAD.** The prune's domain exceeded the lane's own selection domain, so a *future* generated artifact placed under `docs/legacy/` would be swept by a lane that never created it. Narrowed to `docs/legacy/*-notes.md` at depth 0 (§3.6). |
| AC3 "`legacy/field-mapping.xlsx`-style entries **ignored** (no copy, **no error**)" | **AMBIGUOUS** — read as "inert in the manifest contract," it contradicts production. "No error" means **M4 adds none**; existing referenced-path existence validation (`contracts/manifest.py:1195,:1199-1210`) still applies to **every** entry (§7 AC3). |

### 0.4 rev-4 → rev-5 (the stub hash — self-defeating in a sentence that named the attack)
| rev-4 position | rev-5 correction |
|---|---|
| §5.5 "the hash … is **recomputed from the bytes on disk at read time and compared** to the recorded value — **never trusted as read**, or an agent that edits the stub *and* rewrites the recorded hash silently gets 'unchanged.'" | **THE STATED MITIGATION DOES NOT STOP THE STATED ATTACK.** Recompute-vs-recorded detects only an **inconsistent** edit. Edit the body *and* rewrite the digest — self-consistent — and recompute matches the record: classified `unchanged` ⇒ **refreshed over, or deleted on opt-out**. rev-4 named the exact threat one clause earlier and then specified a check that trivially fails it. **A file cannot be a witness about itself.** Hash removed; classification now compares against an **independently rendered canonical template** (§5.5). |
| §0.3's row calling the rev-3 hash merely "**under-specified**" | **SUPERSEDED — the diagnosis was wrong, not just incomplete.** The defect was never that the hash's domain was unstated; it is that *any* in-file integrity metadata is unauthenticated. Defining it more precisely made it more confidently wrong. Left in place, not rewritten — that row is the record of a misdiagnosis. |
| §5.5's five-state table | **THE HOLE WAS INSIDE A ROW,** not a missing row — so enumeration couldn't reveal it. Replaced by one invariant: **exactly one classification permits overwrite or delete**; every other state, anticipated or not, defaults to preserve+warn. |

> ### The evidence rule
> **A guardrail must not source its evidence from the side it guards against.** Every correction in §0.3 and
> §0.4 is this one error in a different costume:
>
> | Mechanic | Took its evidence from | Result |
> |---|---|---|
> | §4.1 guard | the **filesystem** it was policing — `resolve()` let an in-root alias rename the reserved file out of the check | reserved path writable |
> | §5.1 registry | the **mutation outcome** it was describing — a preserved file writes nothing | developer seam vanished from the map on regen |
> | §5.5 stub hash | the **editable file** it was classifying — an editor rewrites body and digest together | adopter content classified pristine, then destroyed |
>
> The correct move was identical each time: **compare against something the untrusted side cannot reach** — a
> lexically-reserved name, a declared contract, a freshly rendered canonical template. Each fix was also
> *cheaper* than the mechanic it replaced. **B0–B4 implementers: apply this rule before adding any check;
> three of three failures here were caught in review, not by tests, because each mechanic passes the naive
> test that only exercises the honest case.**
>
> **Where the rule cannot be satisfied, say so.** The §3.6 Legacy-Notes prune trusts the ownership marker,
> because a note's body **is adopter data by construction** — no canonical render exists to compare against,
> and for the prune case (the source note is gone from the manifest) not even the source survives. That is
> the **absence of a trusted side**, not a choice to consult the untrusted one. It is bounded by fail-closed
> unmarked destinations + a depth-0 `*-notes.md` domain, and it is the trust model the existing Java prune
> already uses (`regeneration.py:101-121,:154-177`) — M4 does not unilaterally fork it. The distinction is
> the point: where a canonical render **is** available (stubs), the marker alone is not enough.

---

## 1. Current-state inventory (cited @ `4660acb`)

### 1.1 Agent-facing docs
| Artifact | CRUD | passthrough | kafka-integration | Evidence |
|---|---|---|---|---|
| `agent-context.md` | ✅ | ✅ | ❌ **absent** | `build_emitter.py:77-85`, `:152-160`; Kafka dispatch `engine.py:85-127` never calls it; `kafka_build_emitter.py:14-45` emits pom/config/Dockerfile/README only |
| `README.md` | ✅ | ✅ | ✅ (sole archetype guidance) | `kafka_build_emitter.py:38,:278` |
| Tool stubs (`CLAUDE.md`/`AGENTS.md`/copilot) | opt-in, **dormant** | opt-in, **dormant** | ❌ | tuple `:438-440`; default-off `:37,:112`; only caller `tests/unit/test_agent_context_emitter.py:402`; **no ownership header** (`:482-503`), direct `write_text` (`:457-477`) |

`agent-context.md` renders from `MetadataProject` (`build_emitter.py:579`), §1–§10. Determinism also
depends on the **generation run ID** (`:579-582`; test pins it, `test_agent_context_emitter.py:360-377`).

### 1.2 Machine layer
| Guardrail | Reality | Evidence |
|---|---|---|
| Ownership markers/lanes | Real; first-8-line read, comment-agnostic | `regeneration.py:38-49,:79-85,:154-177`; `apply.py:176-180` |
| Developer lane preserved | **Only while the entity remains**; removal archives + removes original | `regeneration.py:79-85,:212-218` |
| Central sink | **Not universal** — build/sql/ui/audit/security deferred to P1a-2; generated always overwrites | `file_writer.py:1-10,:22+` |
| Plan-hash gate · destructive fail-closed | Real — **apply path only**; raw generate bypasses | `apply.py:38-60,:67-81`; `change_plan.py:29`; bypass `cli.py:216-228`, `engine.py:155-176` |
| Unknown-ownership files | **Skipped**, not surfaced | `change_plan.py:743-769`, esp. `:752-755` |
| Failed-apply rollback | Root sweep; ownership-blind; skips only build/VCS dirs | `apply.py:395-417,:420-422` |
| Stale-generated prune | **Java-only** | `regeneration.py:101-121` |
| CRUD extension seam | Six hooks | `java_emitter.py:3797-4065,:4292-4316,:4491-4516` |
| Referenced-path existence | **Validated in production** | `contracts/manifest.py:1195,:1199-1210` |
| Path safety | Lexical only | `contracts/manifest.py:1273-1296` |
| Emission order | build files (incl. agent-context) **first**, Java/SQL/etc. after | `engine.py:168-177` → `:178+` |
| Network | Engine **does** fetch remote OpenAPI specs | `ingestion/openapi_fetcher.py` |

### 1.3 Studio Legacy Notes — the exact contract M4 consumes
Studio Step 6 renders **"Legacy Notes"** — *"Optional: paste context about the legacy system to help
developers. Saved as `legacy/<slug>-notes.md`"* (`step6_rules.html:182-194`, Markdown-supported, plus a
**Notes Slug** input). Export writes exactly that text to `legacy/{legacy_slug}-notes.md`
(`package_writer.py:499-503`); manifest generation records exactly that one path in `legacy_references`
(`manifest_generator.py:84-86`). Engine parses + existence-validates it (§1.2) — but **generation never
reads the content** (0 `legacy` hits in `build_emitter.py`; `metadata/models.py:126`'s "legacy" is an
unrelated C9 comment). *That single content hop is the whole of M4's carry-through.*

---

## 2. Gap analysis
| Goal | Today | → |
|---|---|---|
| Adopter policy seam | Nothing; no reserved-path guard on any mutation path | §4 |
| Agent-readable ownership rules | Markers exist; agent-context has no map; lanes not path-uniform; **no artifact inventory exists** | §5.1 |
| Verification commands | README `mvn clean package` (`:368`), `docker build` (`:380`); no canonical sequence; no in-repo CI gate (M5b) | §5.2 |
| Precedence statement | Absent | §5.3 |
| **Studio Legacy Notes** content reaches the app | Dead end (§1.3) | §3 |
| Kafka parity | No agent-context; renderer not archetype-neutral | §5.4 |
| Usable stub opt-in | Dormant; semantics undefined | §5.5 |

---

## 3. **Studio Legacy Notes carry-through** — ADOPT (narrow scope)

**What this is:** carry the text an author typed into **Studio Step 6 → Legacy Notes** into the generated
app. `agent-context.md` explains *what* the app is; the Legacy Notes are the *why it behaves this way* —
system-of-record quirks a modernizer most lacks on day one.

**What this is NOT (explicit):** M4 does **not** copy arbitrary legacy inputs, source documents,
spreadsheets/binaries, or KS/KA indexed evidence. Other `legacy_references` entries are **left untouched
and unconsumed** by M4. A generic referenced-artifact transport is out of scope (§0.2).

**PROPOSED design:**
1. **Prerequisite B0 — typed source context.** `source_manifest` is a `str`; the emitter needs the parsed
   definition + package root. (Sized only for what this lane needs.)
2. **Selection — the Studio-owned note convention only.** Consume a `legacy_references` entry **iff**
   its normalized relative path matches **`legacy/*-notes.md`** *and* it reads as **valid UTF-8**. Any
   other entry (e.g. `legacy/field-mapping.xlsx`, `docs/repo-blueprint.md:504-507`) is ignored — no copy,
   no error, no inventory. Non-UTF-8 content at a `*-notes.md` path is a **generation error** (the Studio
   contract guarantees text; a binary there means the package is malformed).
3. **Destination — unambiguous.** `docs/legacy/<same filename>` (e.g. `legacy/dda-notes.md` →
   `docs/legacy/dda-notes.md`). No subpath reconstruction. Two selected notes resolving to the same
   filename ⇒ **generation error** (Studio emits one note per project today; this fails closed rather
   than silently overwriting).
4. **Emitted file = header + body.** Header: `render_generated_file_header(..., comment_style="xml")`
   (`build_emitter.py:191,:339,:588`) — the same HTML-comment header README/agent-context carry, read by
   `read_edgeforge_ownership` (`regeneration.py:154-177`). Body: **the note's bytes, unaltered** (UTF-8;
   BOM if present preserved inside the body; no trailing-newline normalization); exactly one `\n` between
   header and body. **Only the body is preserved verbatim — the file is not.**
5. **Copy safety — preflight, then mutate.** Resolve-then-contain under the package root (the lexical
   check at `contracts/manifest.py:1273-1296` is insufficient — reject symlink escape); require a
   **regular, readable** file; validate UTF-8; detect destination collision; **preflight all selected
   notes before writing any**. Do **not** re-check existence — already enforced (`:1199-1210`).
6. **Lane — `generated`/refreshed + a bounded prune (new work).** No prune covers `docs/legacy/`
   (`regeneration.py:101` is Java-only). The new prune matches **`docs/legacy/*-notes.md` at depth 0**
   (this lane's own selection domain, §3.2 — *not* all of `docs/legacy/**`), acts **only** on files
   carrying the **generated** marker, removes those not in the current selected-note set, and **never
   touches unmarked files** there (fail closed on a pre-existing unowned destination). **A prune's domain
   must equal its lane's domain:** the broader `docs/legacy/**` sweep would let this lane delete a *future*
   generated artifact it never created, and `docs/legacy/` is not claimed as exclusively M4-owned.
7. **Archetype coverage.** CRUD + passthrough: copy + agent-context §2.1 pointer. Kafka: copy + a README
   "Legacy system context" section now; §2.1 once Kafka gains agent-context (§5.4).
8. **Data handling — honest, scoped.** This is **deliberate data replication**: the note moves from the
   manifest package into the generated repository, changing its distribution/access surface even though
   both are adopter-controlled. Adopters should apply their own classification/secret review to
   `docs/legacy/**`. Supportable claim: **the legacy carry-through performs no network call and sends no
   legacy-note content externally.** *(Not claimable: "the Engine sends nothing anywhere" — Engine fetches
   remote OpenAPI specs, `ingestion/openapi_fetcher.py`.)*

---

## 4. Adopter-owned policy seam — earn the machine guarantee

**Reserved object:** the **repo-root** `AGENT-POLICY.md` — adopter-owned or absent. The Engine never emits
it, not even a placeholder (a template is the first step toward fabricating an enterprise's rules).

### 4.1 The guard contract (two independent checks — PROPOSED)
Neither entrypoint knows the root today: `write_generated_file(path, content, *, ownership)`
(`file_writer.py:22`) and `_skip_apply_rollback_path(path)` (`apply.py:420-422`, matching `path.parts`).
The guard therefore requires an **explicit output/package root** at every call site.

**Why two checks, not one.** rev-3 said *resolve, then match* — which forfeits the match. `resolve()`
follows the **final** component, so an in-root alias (`root/AGENT-POLICY.md` → `root/other-file`) resolves
to `other-file`, the reserved name stops matching, and the write lands **through the reserved pathname**,
changing what the policy file reads as. Containment can't catch it — the alias never leaves the root. The
two properties are **orthogonal and must be checked separately**:

- **Check 1 — Reservation (lexical; does NOT follow the final symlink).** Normalize the candidate against
  the declared root *textually* (`os.path.normpath`-style `..`/`.` collapse — **never** `resolve()`) and
  compare the root-relative result against `RESERVED_ADOPTER_PATHS` as **exact paths at depth 0**
  (`AGENT-POLICY.md` only). **The root pathname is reserved regardless of its target** — a regular file,
  a dangling link, or an alias to anything. Match ⇒ refuse.
- **Check 2 — Containment (resolved).** Independently `resolve()` the root and the candidate — for a
  not-yet-created file, resolve its **nearest existing ancestor** and re-append the remaining components
  (`resolve()` on a missing leaf resolves ancestors and leaves the tail lexical, which is precisely the
  case Check 2 exists to police). Require the result to sit **inside** the resolved root. Outside ⇒ refuse.

Both must pass; a refusal from **either** is fail-closed (raise). A generator targeting a reserved or
escaping path is a bug, not a warning. Check 1 alone would miss escapes through an aliased mid-path
directory (`link/../x` collapses lexically but not physically); Check 2 alone is the rev-3 bypass. Neither
is redundant.

- **Nested `docs/AGENT-POLICY.md` is deliberately NOT reserved** — the seam is the repo-root file; a
  nested same-named file is ordinary content. (Stated so the rule is unambiguous, not accidental.)
- **One shared helper, three call sites:** **writer** (refuse), **failed-apply rollback** (extend
  `_skip_apply_rollback_path` so the sweep neither deletes nor reverts it — *the exact hole that killed
  rev-1's claim, and the cheapest fix*), and **every prune** (incl. §3.6). Duplicating the two-check logic
  per call site is how the halves drift apart; the helper is the unit that gets tested.

### 4.2 Universality is a real cost, not a footnote
The guard is only universal once **every mutation sink** routes through it. `file_writer.py:1-10` defers
`build_emitter`, `sql_emitter`, `ui_emitter`, `audit_emitter`, `security_emitter` (P1a-2), and **that work
is not in the canonical backlog** (roadmap `:138` effort `M`, no prereq; tracker M4 `depends_on:
["done-C1-agent-context"]`). **B2a therefore absorbs a complete mutation-sink inventory + guard retrofit.**
**E4 becomes machine-enforced only when that inventory is complete.** See §10.4 for the effort implication.

**The inventory is grounded by a repo-wide audit — not by `file_writer.py`'s docstring.** That list names
five *modules*; it was never an inventory of *sinks*, and taking it as one under-counts. Verified direct
mutations outside it, @ `4660acb`:

| Sink | Site |
|---|---|
| `shutil.copyfile` (contract/sample copies) | `java_emitter.py:9266,:9311,:9354,:9390` |
| `write_bytes` (WSDL/schema) | `java_emitter.py:9303,:9317` |
| backup `write_text` + `path.unlink()` | `java_emitter.py:843-844` |
| `migration_path.unlink()` | `sql_emitter.py:99` |

Note two of these **delete** and four **copy** — a guard that only wraps *content writes* would pass its
own tests and still leave the seam mutable. B2a's audit must cover **write · copy · delete · move**.

**Coverage is made testable, not promised.** B2a ships a **no-new-unguarded-sink test**: an AST scan over
the generation packages for direct mutation calls (`open(...)` in a write mode, `write_text`, `write_bytes`,
`shutil.copy*`/`move`, `unlink`, `rmtree`, `rename`, `replace`) asserting each site either routes through
the guarded helper or sits on an **explicit allowlist with a justification**. A new sink then fails CI until
it is routed or consciously exempted. Without this, "every mutation sink" decays back into exactly the
stale list above — the failure mode this section exists to end.

**Resulting claim:** machine-enforced at writer/rollback/prune, **regression-tested across greenfield
generate · regenerate · successful apply · failed-apply rollback**, with sink coverage **enforced by test**.
By **guard + inventory + tests** — never "by construction."

---

## 5. `agent-context.md` additions — PROPOSED (deterministic, facts-only)

### 5.1 §11 Ownership map — from a **declared-artifact registry** (lifecycle decided)
A hand table is impossible (lanes split *inside* `service/`: `ServiceBase` generated `java_emitter.py:700`
vs `Service` developer `:713,:731`), and rev-2's "planned output inventory" **does not exist** — agent
-context is emitted **first** (`engine.py:168-177`), before Java/SQL/security/audit (`:178+`), and emitters
write directly with no plan.

**Why "what we wrote" is the wrong key.** `write_generated_file` **returns without writing** when a
developer-owned file already exists (`file_writer.py:43-44`), and that branch is **live**: `_write_java_file`
is a thin passthrough to the sink (`java_emitter.py:823-824`) and `:731` scaffolds `{Entity}Service.java` as
`ownership="developer"`. A write-keyed registry therefore lists the developer seam on a **greenfield** run and
**drops it on regenerate** — inverted exactly where it matters, since a regenerated app is the one an
assistant is *most* likely to be reading, and `{Entity}Service.java` is the one file §11 most needs to name
as off-limits. It also makes the inventory a function of disk state, so "same manifest ⇒ same set" fails.

**Decision — the registry is the run's *declared artifact contract*, not its write log.** Record every
artifact the run **considers**, keyed by what the manifest determines rather than what the filesystem
allowed:

| Field | Value |
|---|---|
| `path` | package-relative destination |
| `ownership` | `generated` \| `developer` |
| `disposition` | `written` · `refreshed` · `scaffolded` · `preserved` |

- **Recorded at the sink, on entry** — after ownership validation, **before** the write/preserve branch.
  `write_generated_file` returns `path` on **both** branches (`:44`, `:46`), so the sink already sees every
  considered artifact; only a hook placed *inside* the write branch could miss one. **This makes B2b one
  hook, not a per-emitter retrofit** — a *simplification* over rev-3's "emitters record."
- **Disposition costs one `stat`.** The sink does not distinguish first-write from refresh today
  (`generated` always writes, `:45`); classifying needs an `exists()` check at entry. Cheap, and it is what
  turns the registry into a diagnostic as well as a map.
- **§11 renders `path` + `ownership` ONLY — never `disposition`.** Disposition is outcome-dependent
  (greenfield vs regenerate); rendering it would make `agent-context.md` bytes differ between runs of the
  *same manifest*, breaking AC2. It stays available to tests and diagnostics. **The lane contract is
  deterministic precisely because it is declared** — this is what rev-3's collect-what-was-written could
  not offer.
- **Agent-context pre-registers itself** at its declared position (`generated`), so the map is complete and
  an assistant reading the file sees the file itself described as generated. It renders after collection;
  without pre-registration it would be the one artifact missing from its own inventory. Opt-in stubs
  (§5.5) register on the same rule when enabled. Pruned/removed paths are **not** entries — the map
  describes the app, not the run's removals.
- **Completeness is bounded by B2a, and honestly so.** Artifacts written by sinks that don't route through
  the guarded helper (§4.2's copies/deletes) are invisible to the registry until B2a routes them. §11's
  exceptions list is therefore not hand-waving — it is **exactly B2a's remaining allowlist**, and shrinks
  as that lands. Never scrape prose back against markers.

**Emission still moves to the end** of the run (the reorder is unchanged from rev-3 and still required).
**Option A** (a full pre-write `GeneratedArtifact(path, ownership, content)` plan) remains the longer-term
ideal and converges with P1a-2 sink completion — the declared registry is its first half.

### 5.2 §12 Verification sequence
One canonical **`mvn clean verify`** (rev-2's `package` → `test` was redundant — `package` already runs
tests), plus `docker build .` where Docker applies. When **M5b/QG-B8** emits a CI descriptor, §12 cites it
— but **mandatory-ness still depends on the adopter's CI/branch policy**; M4 must not imply otherwise.

### 5.3 §13 Organization policy & precedence
**1)** repo-root `AGENT-POLICY.md` if present · **2)** human review · **3)** this file's factual
constraints · **4)** assistant inference. Item 2 is labelled an **EdgeForge recommendation/default**, not
fabricated enterprise policy. Invariants: preserved edge contracts are behavioral guarantees; destructive
schema changes fail closed **in the plan/apply path** — with the honest caveat that **raw generate bypasses
that gate** (`cli.py:216-228`), never stated as a universal generation property.

### 5.4 Kafka parity — do it now, sized honestly
Not a wire-up: the renderer consumes `MetadataProject` (`build_emitter.py:572-853`); Kafka carries
`KafkaMetadata` routes/router-routes (`metadata/kafka_models.py:221-235`). **Design:** a normalized
**`AgentContextFacts`** contract (or archetype-specific renderer) covering routes/topics, processing
semantics, retry, observability, ownership, verification. Kafka lacks the CRUD regeneration/baseline path —
its agent-context must **not** inherit CRUD-only guarantees (no six-hook seam, no CRUD regenerate story).

### 5.5 Tool-stub semantics — **decided here** (not deferred to the build PR)
Stubs today carry **no ownership header** (`build_emitter.py:482-503`) and use direct `write_text`
(`:457-477`). B4 must add the header and implement exactly this state machine.

**No stored content hash — the file cannot vouch for itself.** rev-4 specified a digest recorded *inside*
the stub and recomputed at read time. That catches only an **inconsistent** edit (body changed, digest
stale). An editor that changes the body **and** rewrites the digest — routine for a coding assistant, and
automatic in many tooling chains — produces a self-consistent file that classifies as *unchanged* and is
then **refreshed over or deleted**: precisely the adopter-content loss the table exists to prevent. Integrity
metadata inside an editable artifact is not evidence about that artifact (see the **evidence rule**, §0.4).
The field is **removed**, not hardened.

**Classification compares against an independently rendered canonical template.** The Engine knows exactly
what it would emit, and — decisively — **it is already holding it**: `_render_agent_tool_stub(*, metadata,
link_prefix)` (`build_emitter.py:482-503`) is a **pure function** of `metadata.app_name`,
`metadata.app_archetype.value`, and `link_prefix`, and `:473-474` already calls it and passes the result
straight to `write_text`. The comparison therefore costs **one string equality on a value already in hand**.
rev-4's digest was not merely unauthenticated — it was **redundant machinery** (a stored field, a parse
step, a recompute step, and an absent/unparseable fallback rule) bought to answer a question the render
answers for free. Its removal makes B4 *smaller*.

**The rule — one state, and only one, permits a destructive action:**

> A stub is **`pristine`** iff the file on disk is **byte-identical** to
> `render_generated_file_header(…) + "\n" + _render_agent_tool_stub(…)` **rendered from this run's inputs**,
> with the header's `Generation run:` value taken from the file. **Every other state is `unknown` and is
> preserved with a warning.**

- **Why the run-ID label is read from the file, and why that is not the same mistake.** The header carries
  `Generation run: {generation_run_id}` (`audit.py:17+`), which differs on every run, so a whole-file
  equality needs it neutralized. It is a **label with no authority**: substituting it cannot make a
  non-matching file match, because every other byte must still equal our render. The evidence rule forbids
  taking *evidence* from the untrusted side — this reads a placeholder precisely **because** it is not
  trusted. The stub **body** needs no such carve-out: unlike `agent-context.md` (`:457-464`, which takes
  `generation_run_id`), the stub render takes no run ID and is stable across runs for the same manifest.
- **Whole-file, not body-only.** Body-only equality leaves the header region unchecked, so adopter content
  parked in leading comment lines would classify `pristine` and be deleted on opt-out. Whole-file equality
  closes that without a special case.
- **The header parse is not security-critical** — a mis-parse can only fail the equality, and every failure
  lands on `unknown` ⇒ preserve. There is no parse bug that yields a false `pristine`.

| Destination state | Classification | Behavior |
|---|---|---|
| **Absent** | — | Scaffold: header + canonical body |
| **Byte-identical to this run's render** (run-ID label aside) | **`pristine`** | Refresh — rewrites the header's run ID; the body is unchanged **by definition** |
| **Anything else present** — edited body · absent/forged marker · adopter's own file · extra header content · canonical template drifted across Engine versions | **`unknown`** | **Preserve + warn** |
| **Opt-in disabled** | — | Delete **only** a `pristine` stub; **preserve + warn** every `unknown` |

**Invariant:** exactly one classification permits overwrite or delete. A state nobody anticipated defaults
to `preserve` — the fail-closed direction is **structural**, not enumerated. (rev-4's table failed on this:
it enumerated four states and the hole was *inside* one of them.)

**Accepted cost, stated honestly:** if the canonical stub template changes in a later Engine version, an
untouched stub from an earlier version compares unequal and is classified `unknown` — preserved and warned
rather than refreshed. Stubs then stop auto-refreshing across Engine upgrades until a human looks. That is a
**false positive in the safe direction**, and the alternative (trusting an in-file version marker to select
a historical template) reintroduces exactly the trust problem this section removes.

*Alternative considered and rejected:* leave the opt-in unexposed and drop B4 from M4 — rejected because
the website's claim rests on adopters actually being able to turn stubs on safely.

---

## 6. Enforcement mapping

| # | Guardrail | Verdict | Note |
|---|---|---|---|
| E1 | Developer lane survives regeneration | **PARTIAL machine** | Survives while the entity remains; removal archives/moves it (`regeneration.py:79-85,:212-218`) |
| E2 | Destructive change blocked | **MACHINE — apply path only** | Raw generate bypasses (`cli.py:216-228`) |
| E3 | Stale/unapproved plan can't apply | **MACHINE** ✅ | `apply.py:38-60` |
| E4 | Policy seam untouched | **NOT machine today** → machine **only after B2a's full sink inventory + guard**, and only with §4.1's **two checks** (resolve-first alone is a bypass) | §4.1, §4.2 |
| E5 | agent-context / note determinism | **Deterministic algorithm + regression test** | Inputs incl. **run ID** (`:579-582`) + package bytes |
| E6 | Verification actually run | **Prose** → M5b executes; mandatory-ness needs adopter CI/branch policy | one `mvn clean verify` |
| E7 | Generated-lane drift visible | **Rescoped** | Truth: *post-approval package-state drift invalidates apply for tracked owned files*. Unknown files are **skipped** (`change_plan.py:752-755`). Path-level drift reporting = later work |
| E8 | Precedence | **Governance prose** | Human-review = EdgeForge recommendation |
| E9 | Stubs opt-in | Default-off machine-real; **semantics decided** (§5.5) — destructive action gated on **byte-equality with an independently rendered canonical template**, never on the file's own claim about itself | B4 implements the invariant |
| E10 | Legacy note carried safely | **Proposed algorithm + tests** | Missing-reference failure **already exists** (M4 adds none, and relaxes none); **body**-verbatim copy + a prune bounded to **this lane's own domain** (`docs/legacy/*-notes.md`, generated-marked) + byte semantics are the new work |

---

## 7. Acceptance criteria

1. **Policy seam:** survives greenfield generate · regenerate · successful apply · **failed-apply rollback**
   (sentinel bytes written post-snapshot, forced failure ⇒ byte-identical); writer/rollback/pruner
   **reject/skip** reserved paths; **nested `docs/AGENT-POLICY.md` is not reserved**. The reserved pathname
   is refused in **all four destination states** — **regular file · absent · in-root symlink · out-of-root
   symlink** (the middle two are the rev-3 bypasses: an absent leaf and an in-root alias both survive a
   resolve-first guard). Escape via an **aliased mid-path directory** is refused by containment. The
   two-check helper is tested **as a unit**, and each of the three call sites is asserted to use it.
2. **Determinism:** byte-identical `agent-context.md` + `docs/legacy/*` across two runs with **all inputs
   pinned** — same package bytes **and** run ID.
3. **Legacy notes:** only `legacy/*-notes.md` + valid UTF-8 selected; **`legacy/field-mapping.xlsx`-style
   entries are not selected** — **M4 adds no error for them**, which is *not* the same as inert: the
   existing referenced-path existence validation (`contracts/manifest.py:1195,:1199-1210`) still applies to
   **every** `legacy_references` entry, so a *missing* XLSX still fails load exactly as it does today. M4
   neither extends nor relaxes that. Destination `docs/legacy/<same filename>`; header + **body-verbatim**
   per §3.4; symlink-escape / non-regular / unreadable / non-UTF-8-at-a-notes-path / filename collision →
   rejected in **preflight before any write**; note removed ⇒ bounded prune removes only generated-marked
   `docs/legacy/*-notes.md`, and **leaves a generated non-note artifact under `docs/legacy/` untouched**;
   **pre-existing unmarked file at the destination ⇒ fail closed**.
4. **Ownership map:** §11 renders from the **declared-artifact registry** and matches actual lanes
   **including the `ServiceBase`/`Service` split** — asserted on a **regenerate over an existing app**,
   where `{Entity}Service.java` is `preserved` (unwritten) yet **must still appear as developer-owned**;
   §11 bytes are **identical between greenfield and regenerate** for the same manifest (disposition never
   renders); exceptions explicit and matching B2a's allowlist.
5. **Kafka parity:** kafka-integration emits `agent-context.md` with archetype-correct facts and **no
   CRUD-only guarantees**.
6. **Stubs:** the §5.5 rule is implemented exactly — default none; **`pristine` (byte-identical to this
   run's render, run-ID label aside) is the only state that may be overwritten or deleted**; every other
   state is preserved+warned, on both the refresh path and the opt-out/delete path. Cases: absent ⇒
   scaffold · pristine ⇒ refresh · edited body ⇒ preserve · **marker absent** ⇒ preserve · **marker
   forged onto adopter content** ⇒ preserve · **adopter content added inside the header block** ⇒ preserve
   · **canonical template drift** (render a stub, mutate the template, reclassify) ⇒ preserve+warn, never
   refresh. **The test that would have caught rev-4 — make it explicit:** edit the body **and** rewrite any
   in-file integrity/metadata field to be **self-consistent**, then classify ⇒ **must be `unknown`,
   preserved on refresh and on opt-out delete**. A stub is never destroyed on the strength of a claim it
   makes about itself.
7. **Cross-cutting:** generated apps compile + test for **every affected archetype**; `manifest-v2.schema.json`
   untouched; **no absolute source paths leak in Engine-added content** — headers, links, registry/inventory
   and metadata — **explicitly excluding opaque adopter-authored note body bytes** (which may legitimately
   mention local paths).

## 8. Build slicing

- **B0** `[FEATURE]` Typed generation-source/package context (parsed definition + package root) — prereq for B1.
- **B1** `[FEATURE]` **Studio Legacy Notes** select/preflight/copy/bounded-prune + agent-context §2.1 (needs B0)
  — AC 2/3. *Markdown-note lane only; no binary/media-type/sidecar work.*
- **B2a** `[FEATURE]` **Mutation-sink inventory (repo-wide write/copy/delete/move audit) + the two-check
  `RESERVED_ADOPTER_PATHS` guard helper** across writer / rollback (`apply.py:420`) / all prunes, **+ the
  no-new-unguarded-sink AST test** — AC 1. **Larger than rev-2 implied** (§4.2); the audit and the
  coverage test are the slice's substance, not the guard itself.
- **B2b** `[FEATURE]` **Declared-artifact registry (one hook at the guarded sink) + agent-context emission
  reorder** + §11/§12/§13 rendering (needs B2a's reserved constant for §13, **and B2a's routing for the
  registry to see non-`file_writer` artifacts**) — AC 4. *Smaller than rev-3 implied* — recording at the
  sink replaces the per-emitter retrofit (§5.1).
- **B3** `[FEATURE]` Kafka `AgentContextFacts` + renderer (needs B2b) — AC 5.
- **B4** `[FEATURE]` Stub opt-in exposure implementing the §5.5 invariant (header + canonical-render
  equality; `pristine` is the only destructive-eligible state) — AC 6. *Smaller than rev-4 implied* — no
  digest to store, parse, recompute, or fall back on; `_render_agent_tool_stub` is already called on the
  write path (`build_emitter.py:472-473`).

Order: **B0 → B1** and **B2a → B2b → B3** (parallel lanes); **B4** independent.

## 9. Out of scope
Generic referenced-artifact transport / binary carry-through / media-type sidecars (**maintainer-scoped
out**) · generalized referenced-artifact validation (**already exists**, `:1199-1210`) · path-level drift
reporting (E7 later) · the CI descriptor (**M5b**) · policy-file *content* semantics · KS/KA indexed
evidence · any LLM/provider integration (never) · Studio-side changes.

## 10. Decisions
1. **Legacy scope — Studio Step-6 Notes only.** ✅ Maintainer-decided; §3 narrowed, binary/sidecar work removed.
2. **Kafka parity — now.** ✅ Agreed by both reviewers; sized as a facts/renderer slice (B3); no CRUD guarantees leak.
3. **Policy seam — earn it via the §4 guard.** ✅ Codex: *"Do not weaken it to convention."* rev-2's open
   question is **closed**.
4. **⚠️ For the maintainer — the one new cost (reviewer-recommended, not yet decided):** B2a includes a
   **complete mutation-sink inventory + guard retrofit** (the work `file_writer.py:1-10` defers as P1a-2),
   because E4's machine guarantee is worthless without it and that work is **absent from the canonical
   backlog** (roadmap `:138` effort `M`; tracker `depends_on: ["done-C1-agent-context"]`). Either accept
   **M4's effort growing beyond `M`**, or add an **explicit P1a-2 prerequisite slice**.

   **Codex's gate call @ `a23e211`:** *accept that M4 is now larger than `M`* — "hiding B2a as a medium
   implementation would recreate the exact sink-coverage problem the design is trying to eliminate."
   I agree, and §4.2's audit table is the evidence: the deferred-module list under-counts the real sinks
   by at least eight sites, four of which **copy** and two of which **delete**. Sizing M4 at `M` prices in
   the stale list.

   **This design does not edit the canonical backlog** — that lands *at* the gate, not before it. The exact
   edits, whichever way it goes: `docs/enterprise-readiness-roadmap.md:138` (effort), and
   `docs/tracker/suite-tracker.json` M4 (`depends_on`, if a P1a-2 slice is added) — then
   `python3 docs/tracker/build.py`, committing JSON + `README.md` + `index.html` together.

5. **Guard + registry mechanics — decided (rev-4).** §4.1's two-check order and §5.1's declared-artifact
   contract are design decisions, not build-time choices. Both rev-3 formulations were **self-defeating as
   written** (§0.3): each would have passed a naive test suite while leaving the guarantee it names unmet.
