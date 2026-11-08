# Studio Shared-Mode Security Baseline — Integrated Smoke Result

**Result:** PASS — Studio web-security baseline (P1-3/P1-7 and the Studio portion of P1-8) complete
through PR #293

**Recorded:** 2026-08-21

**Scope:** Studio PRs #284–#293, integrated shared-mode security smoke plus the PR #293 XML-discovery
closure smoke

This is the durable repository record for the completed Studio web-security baseline. It records the
exact revisions and outcomes already proven in the Studio build/review threads; it does not rerun or
reinterpret that evidence, and it does not claim proof beyond what each phase actually exercised.

## Pinned revisions

| Phase | Studio | Paired Engine evidence |
|---|---|---|
| Integrated smoke (after PR #292) | `1ebce2f` (PR #292 merge) | not applicable — Engine not launched by this harness |
| Closure smoke (after PR #293) | `e6884dda13b3545a2cf0c9b3c6aaf69d64a6906f` | `adfdf434ba1fe5a43fb5b4cac505a967055fbb5d` — real-loader parity proof only |

The Engine SHA above is an evidence pin for the specific real-loader parity check PR #293 ran against —
Studio pinned one exact Engine commit for the parity check, not the moving Engine `main` branch, so this
record cites that commit rather than "Engine main" as the paired evidence. It is not a claim that Studio
depends on that Engine revision at runtime. `adfdf434` is itself an Engine PR #297 (M5a-S3) commit; PR #297
merged to Engine `main` (as `2925fec`) at 2026-08-22T01:31:15Z, before Studio PR #293 merged at
2026-08-22T01:42:22Z, so by the time this reconciliation was written `adfdf434` was already an ancestor of
Engine `origin/main`.

## Controls verified by the shared-mode harness

- **Dependency vulnerability gate is blocking.** `pip-audit -r constraints.txt --strict` runs with no
  advisory wrapper; the repository's only remaining non-blocking CI step is Ruff lint, named
  "non-blocking" in its own job title.
- **Address-pinned, bounded OpenAPI fetch.** Connections resolve to numeric addresses and verify the
  connected peer matches the validated address (anti-DNS-rebinding). Link-local, multicast, reserved,
  and metadata addresses (AWS/GCP metadata IPs) are **permanently blocked with no override**. RFC1918
  and IPv6 ULA private-service ranges are blocked **unless the exact host is on the operator-configured
  allowlist** (`EDGEFORGE_STUDIO_OPENAPI_FETCH_ALLOWED_HOSTS`) — intentional, so an operator can point at
  an internal OpenAPI service. Response size is capped
  (`EDGEFORGE_STUDIO_OPENAPI_FETCH_MAX_BYTES`, default 5 MiB).
- **API docs routes are conditional, not unconditionally exposed.** `/docs`, `/redoc`, and
  `/openapi.json` are wired through `settings.enable_api_docs` rather than always-on.
- **Durable shared-mode audit.** The audit sink setting now accepts `{"noop", "sqlite"}` and defaults to
  `sqlite` when `shared_mode` is set (previously `noop` was the only accepted value in shared mode).
- **Request/resource bounds.** `app/middleware/resource_limits.py` and
  `app/services/request_resource_limits.py` add pre-materialization request bounds and
  rate/concurrency controls; `app/middleware/upload_request_policy.py` adds upload MIME/content-type
  policy.
- **Regeneration XML discovery aligned to Engine's fail-closed DTD policy** (PR #293) — this is the
  control the paired Engine evidence pin above proves.

## Integrated smoke (after PR #292)

- Focused security suite: **244 passed**
- L2 two-session smoke: **1 passed**
- Non-smoke suite: **2135 passed, 1 failed, 1 skipped, 29 deselected**
- The sole failure was the stale `harmless-dtd` Studio/Engine parity expectation (pre-existing on Studio
  `main` independent of this work — see the note below).
- The shared-mode security harness itself passed.
- Engine and KS were not launched by that harness.

## Closure smoke (after PR #293)

- Focused XML/regen/security suite: **112 passed**
- Full non-smoke suite: **2137 passed, 1 skipped, 29 deselected**
- L2 two-session smoke: **1 passed**
- `git diff --check`: clean
- Active DTD-bearing XSD/WSDL inputs were rejected consistently.
- Safe UTF-8 comment/CDATA and UTF-16BE cases remained accepted.
- The prior integrated security result (above) is therefore reclassified `pass` — the one failure it
  carried is resolved.

**No repository source files were changed by either smoke run.** Both are test-execution records only.

## What this does not prove

- **This is not a fresh L5 suite acceptance run.** The layered cross-repo smoke harness
  ([`suite-smoke-harness-design.md`](../suite-smoke-harness-design.md)) was not re-executed end to end.
- **It does not complete M2** — the suite vulnerability-assessment program still has generated-Maven CVE
  scanning, image scanning/signing/provenance, and per-app SBOM outstanding.
- **It does not complete M3/P1-6** continuous cross-repo verification — no workflow re-runs this evidence
  on a schedule or SHA trigger yet.
- **It does not close the standalone KS portion of P1-8.** Direct KS ingest still needs an
  operator-visible sensitive-data/no-sanitization notice and regression proof.
- **It does not close A11y-01** — at the time of this run, that remained a separate Studio
  spoken-announcement pre-release evidence gate. This historical classification is preserved as
  executed. The later revised policy is tracked by [Studio PR #299](https://github.com/santosh-sh/EdgeForgeStudio/pull/299)
  and [Studio issue #302](https://github.com/santosh-sh/EdgeForgeStudio/issues/302); it remains proposed
  until the Studio and Engine/Suite amendments receive independent review and merge.
- **It does not prove Engine or KS runtime behavior** beyond the explicitly invoked PR #293 real-loader
  parity check. Engine and KS were not launched as services by this harness.
- **It is not an enterprise-user authentication claim.** Shared-mode identity remains the existing
  anonymous per-session/per-principal model; this baseline hardens the web surface around it and does not
  add SSO/RBAC or multi-replica readiness.

## Source references

- Studio `CHANGELOG.md` — PR #284–#293 entries
- Studio `docs/security-boundary-map.md`, `docs/deployment-model.md` — updated control descriptions
- Studio `.github/workflows/pytest-ci.yml` — blocking dependency-audit step
- [`docs/suite-security-review-backlog.md`](../suite-security-review-backlog.md) §P1-3/P1-7/P1-8 — the
  Studio findings and P1-8 portion this baseline resolves
