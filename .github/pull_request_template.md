<!--
EdgeForge Engine pull request. See CONTRIBUTING.md for the authoritative rules
and docs/suite-architecture.md for orientation.
-->

## What

<!-- What does this PR change? -->

## Why

<!-- Why is this change needed? Link the roadmap item / issue if any. -->

## Validation

<!-- Commands run and their results (e.g. pytest, generated-output tests,
     mvn build / runtime smoke). Paste real output where it matters. -->

## Contract-compatibility risk

<!-- Does this affect upstream API or downstream handoff (file/table/message)
     contracts, the canonical model, or manifest schema? Call out any backward-
     compatibility risk explicitly, or state "none". -->

## Checklist

- [ ] PR-only — not pushed or merged directly to `main`
- [ ] Branch follows `<agent>/{feature|fix|docs|chore}/<short-desc>`
- [ ] PR title uses a prefix: `[FEATURE]` / `[FIX]` / `[DOCS]` / `[CHORE]` / `[GENERATED]`
- [ ] No backward-compatibility / contract break (or explicitly called out above)
- [ ] Canonical-model approach preserved (no direct API-to-entity generation)
- [ ] Generated apps remain standalone (no runtime dependency on EdgeForge/Studio/KS/MCP)
- [ ] Tests added/updated and the suite is green
- [ ] Docs updated in the same PR if behavior changed (no "design says X but code does Y" drift)
- [ ] No secrets, real/production data, or domain-specific/third-party names in committed content
