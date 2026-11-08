# Python Vulnerability Audit — EdgeForge Engine

> **Import-gate G4 evidence.** Vulnerability scan of the resolved Python
> dependency lock (`requirements-lock.txt`) using **pip-audit 2.9.0**.
>
> **Generated:** 2026-06-28. Historical snapshot; the former mixed evidence
> script is disabled, and `make sbom` writes the separate `python-current/`
> assessment.
> Raw machine-readable output: [`pip-audit.json`](pip-audit.json).

## Honest status

**Findings present: 1 vulnerability record(s).** Disposition: recorded for adopter/security review or a future dependency-update PR; this P1 evidence PR does not change runtime behavior beyond pin reconciliation.

Tool exit code: `1`.

## Findings

| Package | Version | Advisory | Fix versions | Summary |
|---|---|---|---|---|
| `pytest` | 8.4.2 | GHSA-6w46-j5rx-g56g | 9.0.3 | pytest through 9.0.2 on UNIX relies on directories with the `/tmp/pytest-of-{user}` name pattern, which allows local users to cause a denial of service or possibly gain privileges. |

## Scope note

This audit covers the Python dependency lock generated from `requirements.txt`.
It does not audit generated-app Maven dependencies; see
[`generated-app-dependencies.md`](generated-app-dependencies.md) for that
standalone app surface.
