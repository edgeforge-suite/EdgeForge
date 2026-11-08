# Knowledge Assist Persistence & Reopen Hardening — Design

> **Status:** Design / docs only — no code in this PR. Defines the product
> architecture and a phased implementation plan for making a saved Studio project
> that used **Knowledge Assist (KA)** remain *understandable and exportable* when
> it is reopened later and the live **Knowledge Server (KS)** workspace is missing,
> stale, reindexed, snapshot-only, or unavailable.
>
> **Decision (given):** a **hybrid** architecture — Studio project JSON stores
> durable review/evidence **snapshots** needed for reopen readability; KS SQLite
> stores the full searchable/indexed live evidence. Reopen must work in degraded
> mode without silently losing or confusing prior human decisions.
>
> **Last updated:** 2026-06-13.
>
> **Builds on (does not contradict):**
> [`project-workspace-decision-ledger-design.md`](project-workspace-decision-ledger-design.md)
> (durable workspace model) ·
> [`evidence-trail-design.md`](evidence-trail-design.md) (the `evidence-trail.json`
> sidecar) · [`studio-ks-orchestration-design.md`](studio-ks-orchestration-design.md)
> (reconnect protocol, degraded-mode rules) ·
> [`studio-ux-v3-assistive-features-design.md`](studio-ux-v3-assistive-features-design.md)
> (capability model, `ks_active` vs `knowledge_assist_enabled`, Addendum A
> save/open hardening, the stable `project_id + project_revision + saved_at`
> anchor) · [`ks-broader-suggestion-scopes-design.md`](ks-broader-suggestion-scopes-design.md)
> (KS suggestion envelope + citation model).
>
> **KS baseline this design assumes (already shipped):** `purge_document(confirm_purge=True)`
> hard-purge (KS PR #31) and optional-parser resource guards (KS PR #32) are
> **done** and treated as the current baseline. KS remains local-stdio,
> deterministic SQLite FTS5/BM25, no LLM/AI, suggestion-only, with a 16-tool
> vocabulary.
>
> **Status update — PARKED pending the multi-session track (2026-06-13).** The
> workspace **location and identity** this design depends on are now **owned by the
> finalized multi-session / multi-user design** (Studio PR #200, merged 2026-06-14) —
> see the next section. This design is in a **logical pause**: reviewed and aligned,
> but implementation resumes only **after** multi-session phases **P2** (SQLite
> session/project catalog + server-owned `workspace_root`) and **P4** (per-session KS
> DB + re-keyed workspace identity) land. Tracker bookkeeping for this item lives in
> the tracker-refresh PR (#234), not here.

---

## Relationship to the multi-session track (PR #200) — read first

The suite's **multi-session / multi-user architecture** is finalized and **merged**
(Studio `docs/multi-session-architecture-design.md`, PR #200). It **owns the
foundation this design was going to build**, so KA-reopen now *builds on it* rather
than duplicating it:

- **Workspace location & identity (was KA-reopen "PR 1").** Multi-session **P2** adds a
  `SessionStore` + **SQLite session/project catalog** with a **server-owned
  `workspace_root`**; **P4** relocates the KS DB under `workspace_root` and **re-keys the
  workspace identity by principal/session** (today it is keyed by `project_id` under
  `tempfile.gettempdir()`). So KA-reopen does **not** invent a persistent-location
  scheme: in **shared mode** the durable per-session location comes from P2/P4; in
  **local mode** (unchanged by multi-session) the **snapshots** are the durability
  mechanism. **KA-reopen "PR 1" is dropped** (subsumed).
- **Sequencing.** KA-reopen implementation lands **after multi-session P2 + P4** —
  building it first would code against the `ks_workspace.py` temp/`project_id` scheme
  that P4 replaces.
- **Shared seams.** Purge→snapshot redaction emits an `AuditEvent` via multi-session
  **P5**; snapshot at-rest text + retention ride multi-session **P6**; the G7/G8
  governance updates **fold into multi-session P8** (which also unblocks the held suite
  assembly).
- **Repo impact (revised).** With per-session KS + ephemeral Engine (locked decisions
  a/b/c in the multi-session design), **Engine and KS need no change**; KA-reopen is
  **Studio-only**.

The §12/§13 plan below is **re-sequenced accordingly**.

---

## 1. Problem — the reopen gap

KA produces **two kinds of state today**, with very different durability:

| State | Where it lives | Survives reopen? |
|---|---|---|
| Human decisions (accept/edit/reject), evidence **links**, conflict resolutions, manifest-revision lineage | Studio project JSON (`StudioProject` → `KSWorkspaceState`: `review_history[]`, `evidence_links[]`, `suggestion_review_state`, `conflict_resolutions[]`, `manifest_revisions[]`) | **Yes** — durable in the save file. |
| The searchable corpus, full citations, live suggestions | KS SQLite workspace at **`tempfile.gettempdir()/edgeforge-studio-ks/{workspace_id}/knowledge.sqlite3`** (`app/services/ks_workspace.py`) | **No** — it is in a **temp directory**: lost on reboot, temp-clear, or a different machine. |

Three concrete failure modes follow directly from the code:

1. **The live workspace is ephemeral.** `ks_workspace.py` roots every workspace at
   `tempfile.gettempdir()`. A project saved today and reopened next week will very
   often find its KS workspace **gone**, even though the project JSON is intact.

2. **Evidence-trail export hard-fails without live KS.** `build_evidence_trail()`
   (`app/services/evidence_trail.py`) expands KA citations by calling
   `get_suggestion_evidence_chain` against the live workspace; if KS is
   unavailable it raises **`EvidenceTrailError`** ("Knowledge Server unavailable
   while expanding evidence-trail citations"). So a reopened project whose
   workspace vanished **cannot export its evidence trail at all** — even though the
   human decisions are saved, and even though the deterministic file/XML/SOAP
   edge-contract evidence in the same sidecar needs no KS.

3. **Evidence links carry no readable citation.** `KSEvidenceLink` stores only
   `manifest_path`, `suggestion_id`, `provenance`. The actual citation (document
   name, snippet, content hash) lives **only in KS**. So Step 7 can label a
   decision "Evidence-backed" but cannot *show* the evidence once KS is gone.

What already works and must be preserved: `build_review_provenance()` (Step 7)
reads **session state, not live KS**, so the *decision list* already renders on
reopen; and `AssistService` already degrades quietly (`KSUnavailableError` /
`KSCallError` → `None`/empty). The gap is **readable evidence** and **exportable
provenance** when the live workspace is absent.

> **Trust principle (load-bearing):** *a saved project means a saved review
> context.* Reopening with KS missing must never silently drop, alter, or
> "forget" a prior human decision.

---

## 2. Architecture — hybrid persistence

```
                          STUDIO PROJECT JSON (durable, travels with the file)
   ┌───────────────────────────────────────────────────────────────────────┐
   │ decisions      review_history[]  · suggestion_review_state               │
   │ evidence links evidence_links[]  (manifest_path, suggestion_id, prov.)   │
   │ NEW snapshots  citation_snapshots[]  (frozen citation subset)            │  ← readable + exportable
   │ NEW doc hints  ks_document_hints[]   (what was ingested)                 │     without live KS
   │ NEW health     ks_workspace_health   (last-known fingerprint/count)      │
   │ anchors        project_id + project_revision + saved_at                  │
   └───────────────────────────────────────────────────────────────────────┘
                          │  reconnect by ks_project_id (when KA on)
                          ▼
                          KS SQLite WORKSPACE (live, searchable — may be absent)
   ┌───────────────────────────────────────────────────────────────────────┐
   │ full document text + chunks · FTS5/BM25 index · full ManifestSuggestion  │  ← fresh suggestions,
   │ + Citation/EvidenceChunk records · cross-project portfolio reuse         │     live citation expansion
   └───────────────────────────────────────────────────────────────────────┘
```

- **Studio JSON is the source of truth for *what a human decided and why*** and now
  also for **enough frozen evidence to read and export those decisions offline**.
- **KS is the source of truth for the *live, searchable corpus*** — fresh
  suggestions, full citation chains, conflict detection, portfolio reuse.
- The two are linked by `ks_project_id`; KS is **recoverable, not required**, for
  reading prior decisions. Live KS is required only for *new* suggestions and
  *live* citation expansion.

This is an **extension** of the already-decided split (decision-ledger doc:
"the workspace stores only the lightweight link… full citation details remain in
Knowledge Server and are expanded into `evidence-trail.json` at export time"). The
one change of principle: we additionally **freeze a bounded citation snapshot at
decision/export time** so readability and export no longer *depend* on live KS.

---

## 3. Data ownership

`[durable]` = persisted in Studio project JSON · `[live]` = KS SQLite only ·
`[new]` = added by this design.

| State | Owner | Notes |
|---|---|---|
| Studio project manifest (Steps 1–6 authoring) | `[durable]` | `StudioProject`, schema `1.3` today. |
| `ProjectCapabilities` / KA-enabled flag | `[durable]` | `capabilities.knowledge_assist_enabled` — the persisted product decision. |
| `ks_project_id` / workspace ID | `[durable]` | Studio-owned; equals `project_id` unless diverged. Reconnect key. |
| `ks_active` | `[durable]` (runtime intent) | Subprocess-activation flag; only ever `True` when `knowledge_assist_enabled`. Not evidence of user intent on migration. |
| Uploaded **document hints** (manifest of ingested docs) | `[durable] [new]` | `ks_document_hints[]` — `document_id`, `document_name`, `doc_type`, `content_hash`, `ingested_at`. **Hints/metadata only — never full document text.** |
| Suggestion **review state** | `[durable]` | `suggestion_review_state` (`accepted_ids`/`rejected_ids`/`edited_ids`). |
| **Review history** (decision ledger) | `[durable]` | `review_history[]` — `suggestion_id`, `type`, `status`, `manifest_path`, `reviewed_at`, `edited_payload`, `review_context`. |
| Evidence **links** | `[durable]` | `evidence_links[]` — `manifest_path`, `suggestion_id`, `provenance`. Lightweight pointer. |
| **Frozen citation snapshots** | `[durable] [new]` | `citation_snapshots[]` — bounded citation subset for accepted/edited links (see §6). The fix for offline readability/export. |
| `manifest_suggestions` (full live suggestion records) | `[live]` | KS table; stable `suggestion_id` + persisted `status`. |
| Full **documents / chunks / FTS index** | `[live]` | KS SQLite; the searchable corpus. Never copied wholesale into Studio JSON. |
| Full **Citation / EvidenceChunk** chains | `[live]` | KS; richer than the frozen subset. Live expansion when connected. |
| `manifest_revisions[]` lineage | `[durable]` | Append-only export lineage (`revision_id`, `manifest_hash`, …). |
| Conflict resolutions | `[durable]` | `conflict_resolutions[]` with rationale. |
| Exported **evidence-trail sidecar** (`evidence-trail.json`) | derived artifact | Built at export; now sources citations live→snapshot→unresolved (see §7). |
| Workspace **health hint** | `[durable] [new]` | `ks_workspace_health` — last-known `document_count`, `workspace_fingerprint`, `last_connected_at`, `db_location_kind`. Enables stale detection. |

**Q1 (portable in Studio JSON):** everything marked `[durable]` above — existing
fields **plus** `ks_document_hints[]`, `citation_snapshots[]`, `ks_workspace_health`.
**Q2 (external in KS):** everything marked `[live]` — full document text, chunk
corpus, FTS index, full `ManifestSuggestion`/`Citation` records, and live
re-suggestion/search/conflict/portfolio capability.

---

## 4. Workspace health model

A reopened project resolves into exactly one **`KSWorkspaceHealth`** state. This
extends the orchestration doc's single "missing workspace" branch and reuses the
existing `WorkspaceStatus{available, degraded, warning, document_count}` view model
and `KSUnavailableError`.

| State | Meaning | Live suggestions? | Prior decisions readable? |
|---|---|---|---|
| **`connected`** | KS started; `list_documents(ks_project_id)` returns; live fingerprint **matches** the saved `ks_workspace_health` fingerprint. | Yes | Yes (live or snapshot) |
| **`missing`** | KA was enabled and `ks_project_id` present, but the workspace does not exist (temp cleared / different machine / never recreated). | No | Yes — **from snapshots** |
| **`stale`** | Workspace exists but its document set / fingerprint **diverges** from the saved hint (re-ingested / reindexed / changed since last save). | Yes, but may differ from decisions on record | Yes — snapshots remain authoritative for prior decisions |
| **`snapshot_only`** | KA history/snapshots exist but live KS is **deliberately not connected** — KA toggled OFF with history, air-gapped, or the user chose "continue with snapshots only." | No | Yes — from snapshots |
| **`unresolved`** | Inconsistent/unclassifiable: `ks_project_id` present but state contradictory (e.g. KA flag/identity mismatch), or KS errored on probe in a way we cannot classify. | No | Yes — never drop; prompt repair |

**Per-state behavior — document list · evidence drill-down · export** (defined here
*before* it drives any Studio prompt, so the implementation does not have to infer it):

| State | Document-list display | Evidence drill-down | Evidence-Trail export |
|---|---|---|---|
| `connected` | Live `list_documents(ks_project_id)` rows | Live chain (`get_suggestion_evidence_chain`); snapshot as per-link fallback | `live` citations (per-link `snapshot` fallback) |
| `missing` | Saved `ks_document_hints[]` only, labelled *"live workspace unavailable"* | **Snapshot only** (frozen citations); *"live chain unavailable"* | `snapshot` → `unresolved` per link; **never fails** |
| `stale` | Live rows **+ divergence banner** (live fingerprint ≠ saved hint) | Live chain available but flagged *"may differ from the decision on record"*; snapshots stay authoritative for prior decisions | `live` for current; `snapshot` where the live chain no longer matches the recorded decision |
| `snapshot_only` | Saved `ks_document_hints[]` only (read-only) | Snapshot only; no live calls | `snapshot` → `unresolved`; no live calls |
| `unresolved` | Hints if present, else none, + repair banner | Snapshot if present, else none | `snapshot` where present, else `unresolved`; **never fails** |

> **Absence ≠ erasure.** A live document/workspace being absent (the `missing` /
> `snapshot_only` / `stale` reality — temp cleared, KS offline, opened on another
> machine, re-indexed) only marks **live** features unavailable. It **never** deletes
> or redacts saved snapshots; doing so would defeat the whole design. The single case
> that redacts snapshot content is a *confirmed hard purge* (§9), never absence.

**Probe algorithm on reopen (design):**

```
if not capabilities.knowledge_assist_enabled:
    health = snapshot_only if (review_history or evidence_links or citation_snapshots) else <no-KA>
elif not ks_project_id:
    health = unresolved
else:
    try start KS; docs = list_documents(ks_project_id)
        if workspace absent / docs empty-and-no-record -> missing
        elif fingerprint(docs) == ks_workspace_health.workspace_fingerprint -> connected
        else -> stale
    except KSUnavailableError -> missing      # cannot start / not present
    except (KSCallError, unexpected)          -> unresolved
```

`fingerprint(docs)` = deterministic hash over the sorted `(document_id, content_hash)`
set (compared against `ks_document_hints` / `ks_workspace_health.workspace_fingerprint`).
The probe is **non-blocking and quiet** in wizard steps (badges simply absent on
failure); the explicit health banner lives on the Knowledge Workspace page and the
reopen surface, per the orchestration doc's degraded-mode rules.

---

## 5. Reopen behavior

On open, after `restore_session()` rebuilds `ks_workspace_state` from the durable
fields, Studio runs the §4 probe. §4 already defines the per-state document-list,
drill-down, and export behavior; the rules here add the reopen affordances:

- **Always show prior decisions from Studio JSON**, in every state including
  `missing`/`unresolved`. Step 7 provenance already reads session state; it must
  additionally render the **frozen citation snapshot** where present.
- **Do not fetch live suggestions** when `missing` or `snapshot_only`. No KS calls
  while KA OFF (invariant preserved).
- **Surface clear, non-blocking repair actions** keyed to state — never block
  authoring:

| State | Repair actions offered |
|---|---|
| `connected` | none (full live features). |
| `missing` | **Reconnect** (locate/repoint workspace) · **Re-upload documents** (re-ingest to rebuild live evidence) · **Continue with snapshots only**. |
| `stale` | **Re-index / reconcile** (re-run suggestions against the changed corpus; prior decisions stay authoritative from snapshots) · **Continue with snapshots only**. |
| `snapshot_only` | **Re-enable / connect live KS** (if KA OFF or user-chosen) · otherwise read-only snapshot view. |
| `unresolved` | **Repair** prompt explaining the inconsistency; offer re-enable or open read-only. Decisions retained regardless. |

- **Preserve user trust:** a visible, plain banner states what is and is not
  available, e.g. *"Knowledge Assist is showing saved decisions only — the live
  Knowledge Server workspace for this project is unavailable. Reconnect or
  re-upload documents to resume live suggestions."* No cryptic failures.

---

## 6. Evidence snapshots — what to freeze, and the governance bound

**Q4 (what can be frozen without a privacy/governance problem):**

Freeze **only the minimum needed for readability + provenance integrity**, never
the corpus. Per accepted/edited evidence link, `citation_snapshots[]` stores the
**same bounded citation subset** the sidecar already emits
(`evidence_trail.py::_extract_citations`):

```
KSCitationSnapshot:
  suggestion_id, manifest_path, suggestion_type, provenance        # join keys
  confidence
  captured_at, source_revision (project_revision at capture)       # anchor to the stable triple
  citations[]:                                                     # bounded subset, NOT the corpus
    document_id, document_name, chunk_id, content_hash,
    parser_version, page, section, heading, char_offset,
    snippet            # length-capped; the text already surfaced to the reviewer
  source_purged_at     # set ONLY on a confirmed hard purge of the source doc; clears
                       # citations[] content -> exports as unresolved/source-purged (§9)
```

**Do NOT snapshot:** full document text, the full chunk corpus, rejected-suggestion
evidence (rejected decisions carry no evidence link by design), or anything KA did
not already surface as a citation to the reviewer.

**Governance guardrails (must be reflected in the suite data-governance posture
doc — tracker `data-governance-posture`):**

- The snapshot persists *source-derived text* (the snippet) into the **portable**
  project file. Studio project JSON is unencrypted at rest (same posture as the KS
  index) — rely on host filesystem encryption for sensitive content; keep the
  synthetic-only-data policy for committed fixtures.
- Snapshotting is gated by `knowledge_assist_enabled` and bounded in length; it
  performs **no inference/redaction** (deterministic). An **opt-out** is offered
  for adopters that do not want source snippets embedded in the project file
  (then export degrades to `unresolved` rather than `snapshot` when KS is absent).
- Because snapshots can outlive the KS corpus, they interact with right-to-erasure
  (see §9, Q7).

---

## 7. Evidence Trail export — fallback semantics

**Q6.** Replace today's all-or-nothing behavior (raise `EvidenceTrailError` when KS
is unavailable) with **per-link degradation**. For each accepted/edited KA evidence
link, resolve citations in this order and **tag the source**:

1. **`live`** — if health is `connected`, call `get_suggestion_evidence_chain`
   (current behavior). On a per-link failure, fall through.
2. **`snapshot`** — else if a `citation_snapshots[]` entry exists for
   `(suggestion_id, manifest_path)`, emit the frozen citation.
3. **`unresolved`** — else emit the link with empty `citations` + an explicit
   warning. **Never raise; never fail the whole export** solely because KS is down.

- Deterministic **edge-contract evidence** (file / XML / SOAP) is unchanged — it
  never needed KS and must always export.
- Each `evidence_links[]` entry gains **`citation_source: live | snapshot | unresolved`**
  — exactly these three values; no other source value is ever emitted.
- An `unresolved` entry may carry an optional **`unresolved_reason`** annotation
  (`ks-unavailable` | `no-snapshot` | `source-purged`) — honest metadata only, **not**
  a fourth `citation_source` value and **not** part of the source counts.
- `provenance_summary` gains `citations_live`, `citations_snapshot`,
  `citations_unresolved` counts (optionally with a `citations_unresolved_by_reason`
  breakdown). The sidecar **`schema_version` bumps `1.1` → `1.2`** (additive).
- `EvidenceTrailError` is retained only for genuinely malformed inputs, not for a
  down/absent KS.

This makes the exported sidecar **honest about which citations are frozen vs live**,
and guarantees an export is always producible from a saved project.

---

## 8. Studio project schema proposal

Additive bump **`STUDIO_PROJECT_SCHEMA_VERSION` `1.3` → `1.4`** (and add `"1.4"` to
the supported set in `deserialize_project()`).

New fields on `StudioProject` (mirrored on `ProjectSession.ks_workspace_state`,
following the existing mirror pattern, and wired through `snapshot_session()` /
`restore_session()`):

```
# document manifest / hints  (+ purge tombstone)
ks_document_hints: list[KSDocumentHint]      # document_id, document_name, doc_type,
                                             # content_hash, ingested_at (metadata only);
                                             # purged_at = tombstone, set ONLY on a confirmed hard purge
# frozen evidence/citation snapshots
citation_snapshots: list[KSCitationSnapshot] # §6 shape; citation content cleared and
                                             # source_purged_at set when the source doc is hard-purged
# workspace health hint (last-known)
ks_workspace_health: KSWorkspaceHealthHint   # last_connected_at, last_known_document_count,
                                             # workspace_fingerprint, db_location_kind
```

**Enriched review-history fields:** `KSReviewHistoryEntry` already carries
`review_context: dict`; no breaking change is required — snapshot linkage is keyed
by `(suggestion_id, manifest_path)`. (Optional additive `evidence_status` on the
in-session provenance view is derived, not stored.)

**Migration approach** (`_migrate_v1_3_to_v1_4`, mirrors the existing
`_migrate_*` helpers):

- Initialize `ks_document_hints = []`, `citation_snapshots = []`,
  `ks_workspace_health = {db_location_kind: "ephemeral-legacy", …empty}`.
- **Do not auto-promote** `ks_active`/history to `knowledge_assist_enabled`
  (keep the conservative rule from the UX-v3 migration). The future opt-in to
  restore KA from non-empty history remains a separate, explicit migration.
- Migrate in memory only; **do not auto-save** — surface the existing
  "saved with an older Studio version… Save to update" banner (Addendum A.7).
- Older saves (≤1.3) simply have no snapshots → on reopen they classify as
  `missing`/`snapshot_only` with the honest "citation requires live Knowledge
  Server" label; snapshots populate as the user re-reviews/re-exports.

All snapshots/hints anchor to the existing stable triple **`project_id +
project_revision + saved_at`** (Addendum A.8) so external tooling can tell which
file revision a snapshot was frozen at.

---

## 9. KS workspace behavior & baseline

- **KS stays the source of truth for live, searchable evidence.** It is not asked
  to change its persistence model; it remains local-stdio, deterministic, no-LLM,
  suggestion-only, 16 tools. No new KS tool is required for MVP — reopen uses the
  existing `list_documents`, `get_suggestion_evidence_chain`, and re-ingest path.
- **Parser limits and hard-purge are the current baseline** (KS PR #32 / #31) —
  treated as done, not re-opened here.
- **`purge_document` vs Studio snapshots (Q7) — the one real policy decision:**
  a hard purge (`purge_document(confirm_purge=True)`) physically removes KS
  metadata, chunks, field-catalog rows, **and dependent suggestions**. Studio's
  durable `citation_snapshots[]` are **independent of KS** and would *survive* a
  purge — meaning a frozen snippet could retain content a user purged from KS for
  right-to-erasure. **Recommendation:** let a *confirmed hard purge* — and **only**
  a confirmed hard purge — invalidate the derived snapshot content:
  - **The redaction trigger is a purge *event*, never absence.** Redaction fires
    (a) when the user hard-purges a document **via Studio**, and (b) on reopen
    *only* for documents carrying an explicit **purge tombstone** in the project
    file — a `ks_document_hints[]` entry marked `purged_at` (§8), recording the
    purged `document_id` + `content_hash`. The tombstone reconciles a purge whose
    snapshot-redaction did not complete (e.g. a crash mid-operation).
  - **Passive absence MUST NOT redact.** A document simply missing from the live KS
    workspace — the ordinary `missing` / `snapshot_only` / `stale` reality (temp
    cleared, KS offline, opened on another machine, re-indexed) — **never** triggers
    redaction. Those states retain every snapshot and mark only the *live* workspace
    / live citation-expansion as unavailable (§4 behavior table). Treating absence as
    a redaction trigger would destroy the snapshots that are the whole point of the
    design.
  - **What redaction does:** strip the `snippet` / citation content from the matching
    `citation_snapshots[]` entries and set `source_purged_at`; **retain the decision
    record** (`suggestion_id`, `status`, `manifest_path`, `provenance`). This
    preserves *that a decision was made* while honoring erasure of the *source
    content*. At export, a redacted snapshot resolves to **`citation_source:
    unresolved`** with **`unresolved_reason: source-purged`** (§7) — it does **not**
    introduce a new sidecar source value.
  - This is a **product/data-governance decision** (audit-immutability vs
    right-to-erasure). Default recommended **ON**; surface as adopter-configurable
    and document it in the data-governance posture doc.
- **Stale/reindexed (Q3, `stale`):** KS has no "reindex" verb — reindexing happens
  by re-ingesting documents. The saved `workspace_fingerprint` vs live
  `list_documents` is how Studio detects divergence; reconciliation re-runs
  suggestions but never overwrites prior human decisions.

---

## 10. Decision rendering on reopen, and KA OFF

**Q5 (rendering when KS unavailable):**

- **accepted / edited:** show decision + `manifest_path` + provenance class
  (`ai-accepted` / `ai-edited` / `human-authored`) + the **frozen citation
  snapshot**. If no snapshot exists (legacy save), show the honest label
  *"Evidence-backed — citation requires live Knowledge Server."*
- **rejected:** show as rejected with rationale/context (rejected decisions matter
  for "why was this dismissed"); no evidence link by design.
- No live badges/suggestions are fetched in `missing`/`snapshot_only`. A decision
  is **never** dropped or altered because KS is gone.

**Q8 (KA OFF vs saved KA history):**

- Migration **never auto-promotes** KA from a legacy save (UX-v3 invariant).
- A project saved with KA OFF but **non-empty history/snapshots** reopens as
  `snapshot_only`: the saved decision record renders **read-only**, with a clear
  *"This project has saved Knowledge Assist decisions. Re-enable Knowledge Assist
  to resume live suggestions."* (the UX-v3 future-opt-in hook, now realized as a
  reopen affordance). No live KS calls while OFF.
- **Export with KA OFF:** today KA links are skipped (`project_id = None`). With
  snapshots, the "Include evidence sidecar" option *can* still emit the **frozen**
  KA evidence (the decisions were genuinely made), marked `citation_source:
  snapshot`. Recommended default: keep the current "include sidecar only if ≥1
  accepted/edited" trigger; when included with KA OFF, use snapshots. Flagged as a
  bounded product decision since it extends current KA-OFF export behavior.

---

## 11. The ten design questions — index

| # | Question | Answered in |
|---|---|---|
| 1 | What KA state must be portable in Studio JSON? | §3 (`[durable]` rows) |
| 2 | What must remain external in KS SQLite? | §3 (`[live]` rows) |
| 3 | Connected / missing / stale / snapshot-only / unresolved? | §4 |
| 4 | What evidence can be frozen without a governance problem? | §6 |
| 5 | How do accepted/edited/rejected render if KS is unavailable? | §10 |
| 6 | How should Evidence Trail export behave w/o live citations? | §7 |
| 7 | How does `purge_document` affect saved references/snapshots? | §9 |
| 8 | How does KA OFF interact with saved KA history? | §10 |
| 9 | MVP vs long-term? | §12 |
| 10 | What phases / PRs follow? | §13 |

---

## 12. MVP vs long-term

**MVP — the must-haves for reopen trust:**

1. **(Owned by multi-session — not built here.)** The durable, per-session workspace
   location comes from multi-session **P2** (`workspace_root`) + **P4** (KS relocation +
   re-keyed identity). In local mode, snapshots cover durability. KA-reopen consumes it.
2. **Schema `1.4`** — `ks_document_hints[]` (+`purged_at`), `citation_snapshots[]`
   (+`source_purged_at`), `ks_workspace_health` + migration. *(Round-trips through both
   the file save and the multi-session catalog `state_json`.)*
3. **Populate snapshots** at decision/export time, from the **per-session** KS.
4. **Workspace health probe on reopen** + honest banners + repair actions, integrated
   with the per-session KS lifecycle.
5. **Evidence Trail fallback** (live → snapshot → unresolved; never fail the whole
   export when KS is down).
6. **Purge → snapshot invalidation** policy (right-to-erasure correctness, §9; audit via
   multi-session P5).

**Long-term / later:**

- Deeper **stale/reindexed reconciliation** — re-anchor live suggestions to prior
  decisions after re-ingest (`stable_*_suggestion_id` matching).
- **Graph / GraphRAG / vector** evidence architecture — explicitly **not** MVP;
  KS stays BM25/FTS5.

---

## 13. PR phasing plan

**Re-sequenced after the multi-session track (PR #200, merged).** Studio-only; Engine
and KS need no change. The former "PR 1" (persistent workspace location) is **dropped** —
owned by multi-session P2/P4. KA-reopen implementation lands **after** multi-session P2
(catalog + `workspace_root`) and P4 (per-session KS + re-keyed identity).

| PR | Scope | Repo | Complexity | Depends on (multi-session) |
|---|---|---|---|---|
| ~~Persistent workspace location~~ | **Dropped** — owned by multi-session **P2** (`workspace_root`) + **P4** (KS relocate + re-key) | — | — | — |
| **KA-1: Snapshot schema + population** | Schema `1.4` (`ks_document_hints`/`citation_snapshots`/`ks_workspace_health`, +`purged_at`/`source_purged_at`); populate from the **per-session** KS; compute `workspace_fingerprint`; round-trips through file save **and** catalog `state_json` | Studio | M | **P2** + **P4** |
| **KA-2: Workspace-health probe + degraded reopen** | 5-state probe wired to the per-session KS lifecycle + re-keyed identity; per-state doc-list / drill-down (§4); banners + repair actions | Studio | M–L | **P4** + KA-1 |
| **KA-3: Evidence Trail fallback + purge policy** | per-link live → snapshot → unresolved; `citation_source` / `unresolved_reason` / counts; sidecar `1.1→1.2`; purge → snapshot redaction emitting an `AuditEvent` via the **P5** seam | Studio | M–L | KA-1; purge-audit via **P5**, retention via **P6** |
| **KA-4** *(later/optional)* | deeper stale/reindexed suggestion matching/reconcile (re-anchor suggestions after re-ingest) | KS / Studio | L | after KA-2/3 |
| ~~docs (G7/G8 governance)~~ | **Folded into multi-session P8** (snapshot at-rest + purge governance; unblocks the held suite assembly) | — | — | **P8** |
| ~~Graph / GraphRAG / vector~~ | **Future only — not MVP** | — | — | — |

> **Sequencing note.** ~3 core Studio PRs (KA-1→KA-3), down from the original 5, all
> gated behind multi-session P2/P4. The one piece that fixes a *today* bug independent
> of multi-session is KA-3's export fallback (export hard-fails when the temp workspace
> is gone); it may be pulled forward **only** if written against an identity abstraction,
> not the soon-to-change `project_id`/temp keying.

---

## 14. What this design is NOT

- **Not** a change to KS's persistence model, tool vocabulary, or its
  local-stdio / deterministic / no-LLM / suggestion-only posture.
- **Not** a server-backed project catalog or multi-user store (that is
  `studio-s1b-catalog` / the multi-session track).
- **Not** a corpus copy — snapshots are a **bounded** citation subset, never the
  full document text or chunk store.
- **Not** a new audit-immutability guarantee — `review_history`/snapshots remain a
  practical decision record, not a tamper-evident log.
- **Not** a Graph/GraphRAG/vector initiative — that is explicitly future-only.

---

## 15. Cross-references

- Durable workspace model & migration rule —
  [`project-workspace-decision-ledger-design.md`](project-workspace-decision-ledger-design.md)
- Evidence sidecar schema & live-vs-stored split —
  [`evidence-trail-design.md`](evidence-trail-design.md)
- Reconnect protocol, degraded-mode, `WorkspaceStatus` —
  [`studio-ks-orchestration-design.md`](studio-ks-orchestration-design.md)
- Capability model, `ks_active` vs `knowledge_assist_enabled`, Addendum A
  save/open hardening & the stable anchor triple —
  [`studio-ux-v3-assistive-features-design.md`](studio-ux-v3-assistive-features-design.md)
- KS suggestion envelope, citation model, `submit_suggestion_decisions` —
  [`ks-broader-suggestion-scopes-design.md`](ks-broader-suggestion-scopes-design.md)
- Data-governance posture (snapshot at-rest + purge policy) — tracker
  `data-governance-posture`
- **Multi-session / multi-user track — owns the workspace location/identity this design
  builds on; supplies the P2/P4/P5/P6/P8 dependencies** — Studio
  `docs/multi-session-architecture-design.md` (PR #200, **merged**)
