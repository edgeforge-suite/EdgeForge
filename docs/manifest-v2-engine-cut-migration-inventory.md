# Manifest V2-E Engine Cut Migration Inventory

**Status:** V2-E implementation inventory, grounded at pre-cut Engine `838784a`.

This inventory records the deliberate Engine-only transition from the single supported manifest
dialect `1.0` to `2.0`. It is not a compatibility bridge and does not implement M5a
`run_semantics`. Studio V2-S and the paired/post-merge V2-X proof subsequently completed; see the
[durable V2-X result](test-results/manifest-v2-cut-v2-x-2026-08-16.md). This inventory remains the
V2-E migration record rather than an M5a implementation record.

## Contract Delta

The pre-cut `manifest-v1.schema.json` and active `manifest-v2.schema.json` are identical after
normalizing exactly these three version-identity locations:

- root `$id`;
- root `title`; and
- `properties.schema_version.enum`.

The canonical JSON SHA-256 for both normalized schemas is
`8186a762628dbb9e834473a439f9178e1c9dd39d8f7d0783a3a3fe16966c3c04`.
No manifest field, constraint, archetype, or nested object shape changes in V2-E.

## Migrated Engine Surfaces

- Current/supported manifest constants now contain only `2.0` and name
  `manifest-v2.schema.json`.
- Public package loading runs the bundled closed JSON Schema before Pydantic model construction.
- Raw-schema, CLI, and MCP entry points use the same schema and version set.
- Active package data includes manifest v2 and Change Plan v1, and excludes manifest v1.
- Metadata defaults for CRUD/passthrough and Kafka carry `2.0`.
- All six example packages, 28 active v2 fixture manifests, three L1/L3 smoke manifests, dynamic
  test manifests, and golden metadata were migrated deliberately.
- One clearly labelled `1.0` package remains under `tests/fixtures/manifest-v2-cut/` solely to prove
  version-specific rejection and reviewed copy-and-version conversion.
- Standard generated headers and README files carry manifest-version provenance for all three
  archetypes; CRUD/passthrough agent context, conditional CRUD audit configuration, and CRUD schema
  baseline follow the existing artifact topology.
- Existing Flyway migrations remain immutable. Only newly emitted migrations carry the current
  manifest version. Existing managed baselines remain byte-identical during ordinary regeneration;
  greenfield/adoption and successful approved apply own baseline establishment or transition.

## Deliberately Unchanged Contracts

- `BASELINE_SCHEMA_VERSION = "1.0"` and the schema-baseline format identity;
- `CHANGE_PLAN_SCHEMA_VERSION = "1.0"` and `change-plan-v1.schema.json`;
- Evidence Trail `1.1`;
- Studio snapshot `1.4` and Studio's Change Plan v1 reader;
- L5 report/run and suite-baseline schemas;
- XML declarations and OpenAPI document versions; and
- historical design and acceptance evidence.

## Conversion Boundary

There is no automatic v1 conversion. A standalone pre-cut package must be copied and reviewed, then
only its root `/schema_version` scalar may be changed from `1.0` to `2.0`. The V2-E regression proof
asserts that referenced artifacts remain byte-identical and that both package and raw-schema paths
accept the reviewed copy. Any other required change fails closed for human review.
