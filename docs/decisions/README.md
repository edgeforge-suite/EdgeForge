# Architecture Decision Records (ADRs)

> **The "why" layer.** These records capture the core architecture decisions that
> are **already made and reflected in the EdgeForge codebase** — they document
> rationale, they do **not** reopen or change anything. Each distills reasoning
> that already lives in the design docs (cited in each record's *Context*). For
> term definitions, see the [Glossary](../glossary.md); for the authoritative
> rules and invariants, see [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Format

Lightweight [MADR](https://adr.github.io/madr/)-style. Each ADR has:
**Status · Context · Decision · Consequences**. Records are numbered
`ADR-NNNN-<slug>.md`, append-only; a superseded decision keeps its file and is
marked superseded by a later ADR rather than edited away.

## Index

| ADR | Decision | Status |
|---|---|---|
| [ADR-0001](ADR-0001-canonical-internal-model.md) | Canonical internal model over API-to-entity mapping | Accepted |
| [ADR-0002](ADR-0002-dual-edge-contract-preservation.md) | Dual-edge contract preservation (upstream + downstream) | Accepted |
| [ADR-0003](ADR-0003-family-agnostic-descriptor-model.md) | Family-agnostic descriptor model | Accepted |
| [ADR-0004](ADR-0004-deterministic-generation.md) | Deterministic generation (byte-identical regeneration) | Accepted |
| [ADR-0005](ADR-0005-generated-apps-standalone.md) | Generated apps are standalone (no runtime suite dependency) | Accepted |
