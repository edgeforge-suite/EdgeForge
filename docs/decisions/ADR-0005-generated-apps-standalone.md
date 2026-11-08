# ADR-0005 — Generated apps are standalone (no runtime suite dependency)

**Status:** Accepted (records an existing, implemented decision).

## Context

A generated app is meant to run in the **adopting organization's own
infrastructure**, long after generation. If it retained a runtime dependency on
the design-time toolchain (EdgeForge/Studio/KS/KA/MCP), production would be coupled
to developer/build tooling — an operational and security liability.

The standalone requirement is an invariant in
[`suite-architecture.md`](../suite-architecture.md) ("Generated apps are
standalone") and [`CONTRIBUTING.md`](../../CONTRIBUTING.md); the design-time vs.
runtime boundary it creates is the spine of
[`security-boundary-map.md`](../security-boundary-map.md) and is answered in
[`compliance-and-portability.md`](../compliance-and-portability.md) (§4).

## Decision

Generated apps have **no runtime dependency** on EdgeForge, Studio, the Knowledge
Server/Assist (KS/KA), or MCP. Each is an independently buildable, standard Spring
Boot project shipping its own `README.md` and `Dockerfile`, configured via standard
mechanisms (e.g. environment variables), and making only the outbound calls its
manifest declares.

## Consequences

- The design-time toolchain is **not in the production blast radius** — a generated
  app builds and runs with no suite component on the classpath (enforced by the
  generated-app compile check in CI).
- Generated apps are portable into an ordinary enterprise JVM environment with no
  proprietary runtime.
- The Engine and the rest of the suite are positioned as **design-time** tools;
  this boundary is what the compliance and security-boundary docs rely on.
- Generated-app outputs are regenerated from committed input packages/fixtures;
  generated source snapshots are not committed under `GeneratedApps/`.
