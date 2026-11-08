# ADR-0002 — Dual-edge contract preservation (upstream + downstream)

**Status:** Accepted (records an existing, implemented decision).

## Context

A legacy system must keep honoring contracts on **both** edges: the **upstream**
APIs callers depend on (REST/JSON, SOAP/XML, XML/XSD) and the **downstream**
handoffs it produces (files, staging tables, messages). Modernization efforts that
preserve only one edge — typically the API — silently break the other and fail
integration.

Both edges are stated as first-class contracts in
[`suite-architecture.md`](../suite-architecture.md) ("Dual-edge contract
preservation"), and broadening the breadth of upstream/downstream contracts is
named the platform's highest-leverage investment in
[`edge-contract-expansion-roadmap.md`](../edge-contract-expansion-roadmap.md).

## Decision

Treat **both** edges as first-class, preserved contracts. Edge contracts live in
their dedicated manifest arrays — `upstream_interfaces[]` and
`downstream_interfaces[]` — and table/datastore staging lives in `data_handoffs[]`.
New edge-contract concepts are added within these arrays; the system never routes
file/XML/SOAP edge contracts through `data_handoffs[]`, and never adds parallel
`*_contracts[]` arrays.

## Consequences

- Upstream and downstream are both modeled, generated, and validated — the
  generated app stays backward-compatible at both edges.
- A single, consistent home for each contract kind keeps the manifest coherent and
  avoids drift across parallel structures.
- Edge-contract breadth (more families) is the primary growth axis, expanded one
  family at a time within the established arrays
  (see [`edge-contract-expansion-roadmap.md`](../edge-contract-expansion-roadmap.md)).
