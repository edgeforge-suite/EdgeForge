# EdgeForge Docs Index

> **Product:** EdgeForge. **Python module/CLI:** `appbuilder`.
>
> **Suite baseline:** `v4.1.0` — June 2026: feature-flagged regen-preview UX
> increment on the `v4.0.0` enterprise-readiness baseline. Suite pin: engine
> `v4.1.0` `8f758f4` / studio `v4.1.0` `6537a75` / ks `v4.0.0` `11aed44`.

This is the navigation index for the Engine repo docs. Prefer the links below
over older planning notes; archived documents are preserved under
[`archive/`](archive/README.md) and are explicitly non-authoritative.

## Start Here

- [Suite Architecture — START HERE](suite-architecture.md) — front-door
  orientation for humans and agents: suite map, repo structure, routing table,
  and invariants.
- [Root README](../README.md) — high-level baseline, quickstart, working rules,
  and tag information.
- [Contributing](../CONTRIBUTING.md) — authoritative workflow and review rules.
- [Quickstart](quickstart.md) — clone, set up, generate, build, and run the
  representative app.
- [Glossary](glossary.md) — shared suite vocabulary.

## Current Baseline

- [Enterprise-Readiness & Handoff Roadmap](enterprise-readiness-roadmap.md) —
  suite-level master tracker for import-readiness and handoff.
- [Adopted v5 / External Review Reconciliation](external-review-backlog.md) —
  release versus launch/pilot scope, completion criteria, XR item mapping and
  parallel repository work/merge order (maintainer adoption: 2026-10-06).
- [Suite Security Review Backlog](suite-security-review-backlog.md) —
  canonical remediation backlog and reconciled cross-track execution order from
  the 2026-07 adversarial review.
- [Suite Task Tracker](tracker/README.md) — generated current view over the
  canonical roadmap and backlog sources.
- [Implementation Sequence History](current-implementation-sequence.md) —
  historical phase sequence and parked-work provenance; not the current plan.
- [Appbuilder Context](appbuilder-context.md) — compact agent context for the
  current suite baseline.
- [Historical Suite Baseline (v4.1.0)](suite-baseline.json) — preserved cross-repo
  baseline metadata, including its then-current license status; not current v5
  release policy.
- [Suite Release-Candidate Pairing](suite-release-pairing.md) — active
  three-repository candidate selection, read-only preflight usage, and evidence
  boundaries; the machine-readable pins live in
  [`suite-release-candidate.json`](suite-release-candidate.json).
- [v5 Source-Release Readiness](v5-release-readiness.md) — approved scope-reset
  revision 3, disclosed M2 limitations, fresh-repository cutover and retained
  acceptance checks; maintainer publication authorization and reporting prerequisites.
- [Public-Content Preparation](public-content-preparation.md) — independent
  Workspace/Item example, before/after coverage, retained design review,
  Open Banking attribution and intended-tree boundaries.
- [Decisions](decisions/README.md) — ADRs for canonical model, dual-edge
  preservation, descriptor model, deterministic generation, and standalone apps.

## Reference

- [Manifest Schema](manifest-schema.md) — manifest contract notes; schema source
  lives under `appbuilder/schema/`.
- [Selected REST Read Contract](read-operation-contract.md) — supported ID/list
  reads, fail-fast selectors and explicit OpenAPI metadata-header classification.
- [Selected REST Write Contract](write-operation-contract.md) — faithful selected
  write routes, inputs, responses and developer-owned semantics.
- [Upstream Integration Boundary](upstream-integration-boundary.md) — how other
  producers conform to the Engine-owned manifest contract.
- [Edge-Contract Docs](edgecontracts/README.md) — file, XML/XSD, SOAP/WSDL, and
  Evidence Trail metadata design/status.
- [Generated App Standards](generated-app-standards/README.md) — generated-app
  quality gate, roadmap, test-console UX, identity roles, and integration
  standards.
- [Generated-App Operations Note](generated-app-standards/generated-app-operations-note.md)
  — deployment guidance for generated-app file/XML directories, secrets, and
  gateway/TLS posture.
- [Experimental Boot 4.1 Preview](generated-app-standards/boot41-jobless-preview.md)
  — opt-in fresh CRUD/SOAP, JDBC Batch and passthrough scope; unchanged Boot 3
  defaults, proof commands and no Batch 5 history migration.
- [Regenerate / Maintain Model](regenerate-maintain-model-design.md) and
  [Suite Regenerate / Maintain Contract](regenerate-maintain-suite-design.md) —
  ownership, baseline, Change Plan, and apply model.
- [Security Boundary Map](security-boundary-map.md) — trust boundaries, attack
  surfaces, and controls.
- [Compliance & Portability](compliance-and-portability.md) — import-review
  answer sheet.
- [Data-Governance Posture](data-governance-posture.md) — data map,
  classification, retention, and AI/data-egress posture.
- [Project Workspace / Decision Ledger](project-workspace-decision-ledger-design.md)
  — project-state and decision-history model.
- [Extension Architecture](extension-architecture.md) — planned extension
  surfaces.

## Test & Evidence

- [Handover-Evidence Index](handover-evidence/README.md) — start here for import
  review: secrets/data scan, dependency evidence, compliance, security, CI, and
  L5 acceptance.
- [Dependency Evidence](handover-evidence/dependencies.md) — Python SBOM,
  `pip-audit`, transitive licenses, and representative generated-app Maven
  evidence.
- [Generated Docker Image Assessment](handover-evidence/generated-image-assessment.md)
  — actual build/runtime coverage, inventories, findings and bounded Maven follow-ups.
- [Generated Build References](generated-build-reference-policy.md) — reviewed Noble
  index pins, build-plugin realm boundaries, historical replay and pending proof.
- [L5 Acceptance Run](handover-evidence/l5-acceptance-run.md) — hermetic
  cross-repo acceptance evidence.
- [Suite Smoke Harness Design](suite-smoke-harness-design.md) — L0-L5 smoke
  harness contract.
- [Test Results](test-results/) — focused proof notes and smoke results.
- [Task Tracker](tracker/README.md) — generated tracker; update
  `tracker/suite-tracker.json` and run `python3 docs/tracker/build.py` when
  editing tracker data.

## Deferred / Historical

- [Archive](archive/README.md) — historical, non-authoritative planning and
  review documents.
- [Archived Target-State Features](archive/target-state-features-v1.md)
- [Archived Target-State Architecture Roadmap](archive/target-state-architecture-roadmap-v1.md)
- [Archived Target-State Sequencing](archive/target-state-sequencing-v1.md)
- [LegacyExtractor Phase 6 Architecture](legacy-extractor-phase6-architecture.md)
  — design exists, but implementation is parked until there is a committed owner.
- Future design docs should be added here only after they become active or
  explicitly parked.
