# Upstream-Producer Integration Boundary

> How EdgeForge accepts work from any upstream producer, and where the boundary
> sits. EdgeForge is domain-agnostic and **owns its input contract** — producers
> conform to EdgeForge, not the other way around.

## The contract

EdgeForge consumes an `app-definition.yaml` manifest and generates a standalone
Spring Boot application from it. Any upstream producer — another tool, a manual
author, or an automated decomposition/modernization workbench — may emit that
manifest, **provided it validates against EdgeForge's own authoritative schema**:

- `appbuilder/schema/manifest-v2.schema.json` — the authoritative **runtime**
  validator. It is the single source of truth for what a valid manifest is.

Producers **adapt to EdgeForge's contract**, not the reverse. EdgeForge has **no
runtime dependency** on any producer, and no producer code runs inside EdgeForge.

## Unknown / producer-private fields

EdgeForge's schema uses `additionalProperties: false`, so it **rejects unknown
fields**. If a producer carries its own private traceability/source metadata in
the file, that producer is responsible for **stripping such blocks before handoff**
so the manifest validates cleanly against `manifest-v2.schema.json`.

## Boundary summary

```
upstream producer  — emits app-definition.yaml (must validate against the Engine schema)
        ↓
EdgeForge (this repo)  — domain-agnostic generation engine; owns manifest-v2.schema.json
        ↓
generated app  — standalone Spring Boot; no runtime dependency on EdgeForge or any producer
```

- The Engine owns and enforces the manifest contract at runtime.
- An optional **design-time** published copy of the schema may be distributed for
  producers to develop against, but that is a distribution choice, not a runtime
  dependency, and it does not change which schema is authoritative (the Engine's).
- Generated apps carry no dependency on EdgeForge or on any upstream producer.

See [`docs/suite-architecture.md`](suite-architecture.md) for where this fits in
the overall suite, and [`docs/manifest-schema.md`](manifest-schema.md) for the
manifest contract itself.
