<!--
EdgeForge Engine pull request. See CONTRIBUTING.md for the authoritative rules
and docs/suite-architecture.md for orientation.
-->

## What

<!-- What does this PR change? -->

## Why

<!-- What problem does this solve? -->

Linked issue: <!-- Link the owning issue and confirmed scope, or explain if none applies. -->

## Validation

<!-- Record the tested revision, commands actually run, results, skips and untested
     limitations. Use relevant checks; prose-only edits need content/link checks,
     not new tests that merely assert wording. -->

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
- [ ] Applicable checks passed; actual results and untested limitations recorded
- [ ] Behavior changes have regression coverage; prose-only changes have content/link checks
- [ ] Contribution commits carry the contributor's DCO 1.1 Signed-off-by trailer (`git commit -s`; no CLA)
- [ ] Docs updated in the same PR if behavior changed (no "design says X but code does Y" drift)
- [ ] No secrets, private employer/customer material or real/production data; fixtures are synthetic

<!-- Necessary public dependency names, upstream references and attribution are
     permitted under CONTRIBUTING.md; preserve applicable permissions and notices. -->
