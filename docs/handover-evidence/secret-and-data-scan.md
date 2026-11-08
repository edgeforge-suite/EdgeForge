# Secret & Data Scan — Evidence

> **Import-gate G3.** Replaces "we grepped" with a named, ongoing, auditable
> secret scan, and records the synthetic-only-data policy. The handover-evidence
> index (G10) links this doc.
>
> **Last updated:** 2026-06-09.

## Scanner

- **Tool:** [gitleaks](https://github.com/gitleaks/gitleaks) — a named, widely
  used secret scanner.
- **Version:** pinned to `8.30.1` in the CI workflow.
- **Ruleset:** gitleaks' full default ruleset (`[extend] useDefault = true` in
  [`.gitleaks.toml`](../../.gitleaks.toml)) plus a small, justified allowlist of
  confirmed documentation false positives (below).

## How it runs (CI)

- **Workflow:** [`.github/workflows/secret-scan.yml`](../../.github/workflows/secret-scan.yml).
- **Triggers:** every `pull_request` (all branches) and every `push` to `main`.
- **What it does:** installs the pinned gitleaks CLI and runs
  `gitleaks dir . --redact --exit-code 1` over the committed tree. Any finding
  fails the job (and blocks the PR); `--redact` keeps matches out of the logs.
- **Portability:** uses the pinned CLI (not a marketplace action), so it needs no
  org license and carries cleanly into an adopting organization's CI.

## Result — clean

Run locally with gitleaks `8.30.1` on commit baseline `4aca0a3` (2026-06-09):

| Scan | Command | Result |
|---|---|---|
| Committed tree | `gitleaks dir .` | **no leaks found** (0) |
| Full git history (one-time audit, 435 commits) | `gitleaks git .` | **no leaks found** (0) after the documented allowlist below |

The CI `Secret Scan` workflow runs the committed-tree scan on every PR/push; its
passing run is the ongoing, auditable evidence going forward.

## Allowlist (confirmed false positives only)

Defined in [`.gitleaks.toml`](../../.gitleaks.toml). Discipline: only confirmed
**non-credential** matches are allowlisted, each justified; no real or
real-looking secret is ever silenced.

| Pattern | Why it is not a secret |
|---|---|
| `unique/idempotency` | gitleaks' `generic-api-key` rule reads the markdown phrase "key \| unique/idempotency" (a `key` column header followed by the words) as an API-key value. It is documentation prose about a future "unique / idempotency key" control — currently in `docs/archive/target-state-features-v1.md`, and a historical-commit-only match in `generated-app-engine-roadmap.md` (surfaced by the one-time full-history audit, no longer in the tree) — not a credential. |

## Synthetic-only data policy

- **All committed fixtures, examples, and test data are synthetic.** No real
  customer data, production data, or PII is committed to this repository.
- Sample manifests, OpenAPI/WSDL/XSD specs, file layouts, IBANs/IDs, and
  generated-app proof outputs under `examples/` and `tests/` are illustrative,
  fabricated values only. `GeneratedApps/` is a placeholder for local generated
  outputs, not a committed snapshot source.
- Sample hostnames/URLs in examples (e.g. `*.example.com`) are placeholders, not
  real endpoints.
- Generated apps externalize all secrets (datasource credentials, OAuth2 issuer,
  etc.) via environment/config — no secret values are baked into generated
  output (see the generated `agent-context.md` §"Config & secrets").
- Any future real or PII data must **not** be committed; contributors should use
  synthetic equivalents. The secret scan above enforces the no-credentials half
  of this policy on every PR.

## Scope notes

- Compressed evidence is not traversed by the current required CI commands.
  The [October 17 image-tooling review note](generated-image-tooling-review-2026-10-17.md)
  distinguishes the image-only archive-depth-2 scan from the independent whole-tree
  archive-depth-3 scan and its four synthetic-value matches in two historical logs.
  Neither those observations nor a plain-file CI pass establishes unrestricted
  compressed-artifact coverage. The narrow approved allowlist is not broadened here.

- This is the **secret + synthetic-only-data** gate (G3). Heavier automated
  PII-detection tooling is out of scope here; the synthetic-only policy plus the
  named secret scan cover the "no real data / no secrets" import requirement.
- SBOM + dependency-license inventory is a separate gate (G4); the
  handover-evidence **index** is G10.
