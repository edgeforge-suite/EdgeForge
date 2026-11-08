# Example Input Projects

These are manifest input packages for exercising EdgeForge Engine. They are
source fixtures, not generated apps. Generated output should be written to a
temporary directory or a downstream app repo, not committed here.

| Example | Archetype | Profile | What it covers |
|---|---|---|---|
| [`generated-app-ci-smoke`](generated-app-ci-smoke/app-definition.yaml) | `crud` | `springboot-legacy-compatible` | **CI scaffolding:** canonical domain-neutral generate, compile, package, runtime-health, container, and Maven-evidence proof. Not the developer walkthrough sample. |
| [`workspace-items`](workspace-items/app-definition.yaml) | `crud` | `springboot-legacy-compatible` | Two REST/OpenAPI upstream interfaces mapped to independently authored Workspace and Item entities, generated identities, constraints/defaults and an existence rule. |
| [`loans-modernization`](loans-modernization/app-definition.yaml) | `crud` | `springboot-standard-enterprise` | REST/OpenAPI upstream, fixed-width downstream report, staging-table handoff, enterprise profile. |
| [`obie-wire-transfer`](obie-wire-transfer/app-definition.yaml) | `crud` | `springboot-legacy-compatible` | REST/OpenAPI upstream operations, fixed-width downstream confirmation file, staging-table handoff. |
| [`xyz-accounts-modernization`](xyz-accounts-modernization/app-definition.yaml) | `crud` | `springboot-legacy-compatible` | REST/OpenAPI upstream, downstream fixed-width EOD file, staging-table handoff, legacy reference notes. |
| [`country-router`](country-router/app-definition.yaml) | `passthrough-router` | `springboot-legacy-compatible` | REST passthrough router with one upstream API and three downstream REST systems. |
| [`sepa-payment-router`](sepa-payment-router/app-definition.yaml) | `passthrough-router` | `springboot-legacy-compatible` | REST passthrough router with rules-based routing to three downstream payment rails. |

Representative generation command:

```bash
.venv/bin/python -m appbuilder.cli generate \
  --manifest examples/input-projects/workspace-items/app-definition.yaml \
  --output /tmp/edgeforge-workspace-items \
  --validate-schema
```

## Studio Domain Sample Packs

Studio maintains three canonical domain sample packs for Financial Services,
Healthcare/Payer Operations, and Insurance. Engine's manual acceptance driver
exports those projects through Studio's production package writer, then validates,
generates, builds, and checks the resulting applications without modifying either
repository:

```bash
python scripts/smoke/domain_sample_packs.py \
  --studio-checkout /absolute/path/to/EdgeForgeStudio
```

The checkout argument is required and is never inferred or written to the
repository. Exported packages and generated applications remain temporary.
