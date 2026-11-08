# EdgeForge Engine — Agents (Codex / Devin / general)

EdgeForge **Engine** (product = EdgeForge; Python module/CLI = `appbuilder`) —
deterministically generates standalone Spring Boot apps from reviewed manifests
while preserving upstream and downstream edge contracts.

## Start here

- **Authoritative rules — read before changing anything:**
  [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Orientation + "Where do I go for X?":**
  [`docs/suite-architecture.md`](docs/suite-architecture.md)
- **Branch / PR conventions:** see [`CONTRIBUTING.md`](CONTRIBUTING.md)
  (`<agent>/{feature|fix|docs|chore}/<short-desc>`; PR title prefix
  `[FEATURE]` / `[FIX]` / `[DOCS]` / `[CHORE]` / `[GENERATED]`).

## Common tasks

- **Refresh the suite task tracker:** edit `docs/tracker/suite-tracker.json`,
  run `python3 docs/tracker/build.py`, commit all three changed files
  (JSON + `README.md` + `index.html`). See
  [`docs/tracker/HOWTO-update.md`](docs/tracker/HOWTO-update.md) for schema
  and rules.

---

*This file is a thin, tool-specific pointer. The canonical rules live in
[`CONTRIBUTING.md`](CONTRIBUTING.md) and orientation in
[`docs/suite-architecture.md`](docs/suite-architecture.md) — keep it in sync,
don't fork it.*
