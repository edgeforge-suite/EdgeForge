# ADR-0003 — Family-agnostic descriptor model

**Status:** Accepted (records an existing, implemented decision).

## Context

EdgeForge supports a growing set of edge-contract families (REST/JSON,
fixed-width, CSV, XML/XSD, SOAP/WSDL, …), and each must be **operable and
visible** in the generated app's test console. Building a bespoke renderer per
family would multiply work, drift across families, and make each new family
expensive to add.

The family-agnostic card model is specified in
[`generated-app-standards/generated-app-test-console-ux-design.md`](../generated-app-standards/generated-app-test-console-ux-design.md)
(the renderer is family-agnostic; only the descriptor varies) and is the
integration requirement every new family must meet in
[`edge-contract-expansion-roadmap.md`](../edge-contract-expansion-roadmap.md).

## Decision

Every contract family emits one or more **`ActionCardDescriptor`s** derived
deterministically from its contract metadata. The console **renderer is
family-agnostic** — it consumes descriptors uniformly, and only the descriptor
content varies per family. Adding a new family means emitting descriptors from its
metadata, not writing new rendering code.

## Consequences

- New edge-contract families integrate by emitting descriptors; the renderer is
  not touched, so families don't drift apart in look or behavior.
- The console surface stays uniform across families (grouping, headers, actions).
- Descriptors are emitted from metadata and are deterministic — the same manifest
  yields the same cards (consistent with [ADR-0004](ADR-0004-deterministic-generation.md)).
