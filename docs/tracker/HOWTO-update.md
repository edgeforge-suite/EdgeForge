# Suite Task Tracker — How to Update

> The tracker is a **derived view** over the canonical roadmaps. The roadmaps
> (starting with [`docs/enterprise-readiness-roadmap.md`](../enterprise-readiness-roadmap.md))
> remain the narrative **source of truth** — when a plan changes, change the
> roadmap first (or alongside), then reflect it here.

## The update flow (one data file, one command, one PR)

1. **Edit [`suite-tracker.json`](suite-tracker.json)** — the single edit point.
   Add, modify, or re-status task records. Every record must trace to a real
   doc + heading (`source_doc`); never invent tasks, statuses, or estimates.
2. **Regenerate the views:**

   ```bash
   python3 docs/tracker/build.py
   ```

   This validates the schema (vocabularies, unique ids, `depends_on`
   referential integrity, no absolute paths), regenerates the Markdown mirror
   ([`README.md`](README.md)), and syncs the embedded data block in
   [`index.html`](index.html) so the page also works opened via `file://`.
3. **Open a PR** with all three files (JSON + the two generated views).
   Never push to `main` directly.

### Snapshot cadence

Refresh `meta.snapshot_date` and the current repo SHAs at every coordinated
baseline, roadmap-wave boundary, or intervening cross-repo merge that changes a
current tracker row. Before merging a tracker PR, compare all referenced core repos
against their current `main`. Do not rewrite historical acceptance-evidence pins;
those identify the exact state that produced the recorded evidence.

**A snapshot SHA is always slightly behind by construction.** A tracker refresh cannot record the SHA of
its own merge commit, and later non-tracker merges may land before the next refresh. This is expected, not
a defect: when auditing, compare the **represented task state** against the repos, never raw
snapshot-SHA-to-head equality.

## Record schema (columns)

| Field | Values / notes |
|---|---|
| `id` | Roadmap id where one exists (`B5`, `D1`, `KS-B5`…) else a kebab slug |
| `title`, `summary` | Short name + one line |
| `status` | `done` · `in-progress` · `pending` · `blocked` · `adopter-decides` · `parked` — **exactly as the source says** (source "deferred" → `parked`; "design-first/design-pending" → `pending`) |
| `priority` | `now` · `next` · `later` · `strategic` · `adopter-gate` · `future` · `parked` (tier, derived from roadmap wave/positioning) |
| `complexity`, `prs_estimate` | Only if the source states them, else `—` |
| `design_status` *(optional)* | Maturity of the **design artifact only** — `approved` (design doc merged/gated) · `in-review` (design PR open) · `exploratory` (mocks/options exist, **no build contract**). **Orthogonal to `status`:** any status may carry any maturity, and a design stays `approved` after its build ships. **"Designed but not built" is a compound query** (`design_status=approved` **and** `status` in `{pending, blocked}`), never a status value — this is exactly what the README's `build_pending` count and the HTML's "designed only (build not started)" filter preset compute. Only set it when a real design artifact exists — a source that says "design-deferred" or is marked **partial**, or is plain backlog, does **not** qualify (e.g. `gap-decision-ledger`'s own `source_doc` says "(partial)" — excluded, and the row says so). **This facet is a bounded, hand-audited record, not an exhaustive sweep of all tasks** — absence of the facet means "not yet checked," never "confirmed unapproved." |
| `design_ref` *(required whenever `design_status` is set)* | The design doc path or PR the maturity claim traces to. Build fails without it — no unsourced design claims. |
| `sequence_rank` *(optional, integer)* | Only for rows whose `wave` names a step in the roadmap's canonical execution guardrail `M1 → M5a → M2/M6 → M3 → M4 → M5b` (`enterprise-readiness-roadmap.md`, "Execution guardrail"). Values `1`–`6` map to that order (M1=1, M5a=2, M2/M6=3, M3=4, M4=5, M5b=6). Both the README and the HTML sort **within a priority tier** by this rank before falling back to file order, so the rendered "Now" list matches the roadmap's stated sequence instead of JSON insertion order. Do not invent a rank for a row outside that guardrail. |
| `category` | `Enterprise-readiness` · `Generation-quality` · `Edge-contract` · `Target-state` · `UX` · `Identity` · `Docs-hygiene` · `Adopter-gate` · `Parked` |
| `repo_impact` | `Engine` · `Studio` · `KS-KA` · `cross-repo` · `generated-apps` · `all-core` · `TestBench (optional)` · `shared-specs (optional)` |
| `wave` | The roadmap wave/phase the item belongs to (e.g. `EC Wave 2`, `P4`, `post-import`, `External gate`) |
| `source_doc` | Repo-relative path + the heading it came from (prefix `Studio:` / `KS:` / `TestBench:` / `shared-specs:` for other repos) |
| `depends_on` | List of other task `id`s (validated) |
| `blocked_by` | Optional free-text blocker when the blocker isn't a tracked task |
| `owner_thread`, `last_updated` | Optional owner; ISO date of the row's last edit |

**Status notes (honesty rules):**

- `adopter-decides` covers both adopter-owned **decision gates** and
  **post-import** adopter-side work — the `wave` column distinguishes
  (`External gate` vs `post-import`). Neither is optional or skippable.
- Never upgrade a status beyond what the source doc supports. If a source is
  ambiguous, pick the **lower** status and note the ambiguity in `summary`.
- `done` rows are kept sparingly as anchors for completed tracks; pending work
  is the tracker's focus.

## Viewing

- **On GitHub:** read [`README.md`](README.md) (grouped by priority tier).
- **Interactive:** open [`index.html`](index.html) — filter (status / priority /
  category / repo), search, sort any column, group by tier/category/repo/status.
  Works opened directly from disk (embedded data) and over GitHub Pages / any
  static server (fetches the JSON live).

No backend, no cron, no auto-sync: "live" means **always current with `main`**
via PR edits to the data file.
