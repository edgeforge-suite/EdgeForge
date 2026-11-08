# ADR-0004 — Deterministic generation (byte-identical regeneration)

**Status:** Accepted (records an existing, implemented decision).

## Context

EdgeForge is a **governed, evidence-backed** platform, not generic AI code
generation. Auditability, reviewability, and reproducibility require that
generation be a pure function of its input — otherwise the same manifest could
yield different apps, breaking golden-contract regression signals and traceability.

This is a core thesis in [`suite-architecture.md`](../suite-architecture.md)
("Deterministic output", "Mode semantics") and an invariant in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Decision

The same manifest produces the **same generated app — byte-identical
regeneration**. There is **no AI inference in the generation path**, no silent
auto-apply, and no name inference. Where a feature carries a `mode`,
`metadata_only` emits zero artifacts while `active` must **generate the declared
behavior or fail fast** — never a silent no-op or a plausible scaffold passed off
as complete.

## Consequences

- Regeneration is reproducible; golden-contract tests are a reliable regression
  signal (each generator behavior change updates its goldens in the same PR).
- Generation is traceable and reviewable — output is explained entirely by the
  manifest plus the target profile.
- It deliberately excludes generative-AI-in-the-loop generation; optional AI
  (Knowledge Assist) stays in the **authoring/suggestion** phase, never in the
  deterministic generation path.
- "Generate or fail fast" prevents misleading partial output for `active` features.
