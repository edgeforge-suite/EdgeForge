# Generated App CI Smoke

The canonical fixture for EdgeForge's generated-app CI proof. It exists to exercise the
generate → compile → package → run → containerise chain, not to demonstrate a product scenario.

## What this fixture proves

`.github/workflows/generated-app-compile.yml` generates this app, isolates it, and runs:
source-boundary independence, `mvn -q clean verify`, packaged-boundary independence, an executable
JAR start with an `/actuator/health` check, and a Docker build asserting a non-root user.

It is also the source for the generated-app Maven dependency evidence in `docs/handover-evidence/`.

## Scope — deliberately minimal

| Included | Why |
|---|---|
| Two independent entities (`Record`, `Entry`) | Preserves multi-entity compilation |
| One REST operation each | Matches what the gate exercises |
| Flyway persistence | The gate compiles and starts the app |
| One rule file, exactly two entries | `allowed-values` and `default` emit separate compiled Java paths |

| Excluded | Why |
|---|---|
| Staging handoffs / DDL | Covered by `scripts/smoke/fixtures/engine-l1-l3/` |
| SOAP, XML, file, Kafka, trailer | Covered by focused fixtures |
| `spec_url` | The spec is local and synthetic by design |
| Business logic beyond the two rule entries | Not generation proof |

## Rules for changing this fixture

1. **Additions require a demonstrated shared-gate need.** "It would be useful to also test X" is not one —
   add a focused fixture instead.
2. **No domain vocabulary.** No customer, product, vendor, or industry-specific names. `system:
   CiSmokeSource` names this fixture, not an external system.
3. **The file set is fixed.** A shape guard asserts the exact file list and manifest values; adding a
   file fails CI by design.
4. **Editing the OpenAPI schemas will not change the generated entity.** This fixture uses a local
   `spec:`, so canonical fields come from the sample payloads and mappings. The OpenAPI document
   enriches the manifest-declared operations with HTTP method, path, parameters, request-body presence,
   and response shape; it does not define the entity's fields.

## Not the product sample

This is CI scaffolding. The developer-facing walkthrough sample is separate and lives elsewhere — do not
repoint quickstart documentation here.
