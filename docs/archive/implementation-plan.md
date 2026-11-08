# EdgeForge Implementation Plan

> **Historical document.** Preserved as the record of how EdgeForge's MVP was designed and built. For current execution plans, see:
> - `docs/enterprise-readiness-roadmap.md` — canonical current priorities
> - `docs/tracker/README.md` — generated current tracker view
> - `docs/current-implementation-sequence.md` — historical phase sequence
> - `docs/extension-architecture.md` — current architecture
> - `docs/appbuilder-context.md` — current state

## Status: MVP Delivered — Post-MVP In Progress

All six MVP phases below have been delivered and merged (PRs #1–#10). Post-MVP features (PRs #11–#13) are also delivered. The plan below is preserved as historical record of how EdgeForge was designed and built. For the current roadmap, see `docs/enterprise-readiness-roadmap.md`.

| Phase | PR(s) | Status |
|-------|-------|--------|
| Phase 1: Foundation | #1, #2 | ✅ Delivered |
| Phase 2: Contract Ingestion & Metadata | #3 | ✅ Delivered |
| Phase 3: Mapping & Rules Engine | #4 | ✅ Delivered |
| Phase 4: Spring Boot Generator | #5 | ✅ Delivered |
| Phase 5: Compatibility Harness | #6, #8 | ✅ Delivered |
| Phase 6: Developer Experience | #7, #10 | ✅ Delivered |
| Generality Proof (BuiltApp2) | #9 | ✅ Delivered |
| Demo UI | #11 | ✅ Delivered |
| SSO Security Layer | #12 | ✅ Delivered |
| Audit Tracking | #13 | ✅ Delivered |

---

## Purpose

This document is the authoritative execution plan for EdgeForge.

It exists to keep the project on one implementation path while still allowing multiple AI tools and human reviewers to contribute in parallel.

## Planning Approach

EdgeForge should have one primary plan, reviewed by multiple agents, not multiple independent plans competing with each other.

Recommended model:

- Codex owns the primary implementation plan and repo execution flow
- Claude reviews the plan and PRs, challenges assumptions, and suggests missing risks
- Devin can take bounded implementation tickets once interfaces and acceptance criteria are stable
- Santosh remains the final approver for plan changes and merges

## Product Guardrails

The implementation plan must preserve the existing source-of-truth decisions:

- manifest-driven structured input projects
- canonical internal model instead of contract-shaped internals
- contract-preserving modernization at system boundaries
- compatibility-profile-driven generation
- generated applications isolated under `BuiltAppN/`
- PR-only repository workflow

## MVP Goal

Deliver the first credible AppBuilder slice that can:

- load one manifest-driven input project
- validate referenced input files
- normalize that project into internal metadata
- select a target compatibility profile
- generate the first Spring Boot enterprise-oriented project skeleton
- emit compatibility-oriented test scaffolding

The first example remains `xyz-accounts-modernization`.

## Phase Plan

### Phase 1. Foundation and validation

Goal:

- stabilize the repo scaffold and the core input contract for AppBuilder itself

Deliverables:

- manifest schema and loader
- example input project package
- target profile catalog
- pinned builder dependencies
- initial unit tests

Definition of done:

- example manifest loads successfully
- missing referenced files fail validation clearly
- target profile selection is represented in code

### Phase 2. Contract ingestion and canonical model derivation

Goal:

- ingest real contracts and derive normalized internal metadata from them together

Deliverables:

- OpenAPI/Swagger ingestion from `spec` or `spec_url`
- downstream file layout ingestion from YAML definitions
- staging-table contract ingestion from SQL plus mapping YAML
- rule ingestion from YAML
- canonical entity model
- controlled canonical field type vocabulary
- field model with typing, length, format, defaults, and allowed values
- participating systems model
- contract metadata model with version support
- operation metadata model
- project metadata translation from the example package

Definition of done:

- the example project can ingest upstream, downstream, and data-handoff inputs into one metadata graph
- the example project can be translated into normalized metadata objects
- metadata is independent of raw JSON/XML/file layout shapes

### Phase 3. Mapping and rules engine

Goal:

- make contract-to-canonical and canonical-to-output transformations explicit and testable

Deliverables:

- upstream field to canonical field mappings
- canonical field to staging-table column mappings
- canonical field to downstream file field or position mappings
- mapping completeness policy
- rules engine for defaults, allowed values, and validations
- `mapping/` module implementation
- `rules/` module implementation

Definition of done:

- the example project has explicit mapping metadata rather than implicit field-name coupling
- the example project rules can be represented in normalized form

### Phase 4. Spring Boot enterprise profile generator

Goal:

- generate the first independently buildable application skeleton from normalized metadata

Deliverables:

- project structure generator
- package naming conventions
- generated domain entity classes
- generated service layer stubs
- generated REST adapter stubs
- generated persistence and repository stubs
- generated staging-table writer scaffolding
- generated README and Dockerfile
- generated file header comments
- Flyway migration scaffolding
- Spring Batch scaffolding when the input package requires EOD flows

Definition of done:

- AppBuilder can generate a non-empty enterprise-oriented Spring Boot skeleton into `BuiltApp1/`
- output includes audit headers and profile information

### Phase 5. Compatibility harness

Goal:

- prove the generator is preserving contract intent instead of only emitting code

Deliverables:

- manifest validation tests
- negative manifest test coverage
- golden metadata fixtures
- golden sample comparisons
- contract regression scaffolding
- staging-table mapping validation
- explicit mapping completeness assertions
- one end-to-end happy-path generation test around `XYZ Accounts`

Definition of done:

- the example project has runnable builder-side tests for manifest loading and generated output expectations

### Phase 6. Builder developer experience

Goal:

- make AppBuilder usable repeatedly by humans and AI agents

Deliverables:

- CLI entry point
- clearer error messages
- generation run identifiers
- reproducible local setup instructions
- CI for builder tests

Definition of done:

- a developer can run the builder locally with one documented command path

## AI Tool Division of Work

### Codex

Use Codex for:

- authoritative implementation plan maintenance
- repo structure and code scaffolding
- manifest/model/profile implementation
- integration of review feedback
- shipping the main MVP path in reviewable increments

### Claude

Use Claude for:

- plan review
- PR review
- architecture critique
- documentation refinement
- edge-case and risk identification

Claude should be treated as a reviewer and challenger by default, not as the owner of a second full project plan.

### Devin

Use Devin for:

- bounded follow-on implementation tasks
- repetitive code generation support work
- CI and environment automation tasks
- large but well-specified tickets after interfaces are frozen

## PR Workflow Recommendation

Use this pattern for steady execution:

1. Codex creates or updates the plan.
2. Claude reviews the plan or the PR.
3. Approved plan items are converted into small branch-sized tickets.
4. Codex or Devin implements the ticket.
5. Claude reviews the resulting PR.
6. Santosh approves merge.

## Immediate Next Branches

The current open branch predates the new branch rule. Future branches should follow the new naming convention.

Recommended next implementation branches:

1. `codex/feature/manifest-loader-hardening`
2. `codex/feature/contract-ingestion-and-metadata`
3. `codex/feature/mapping-and-rules-engine`
4. `codex/feature/springboot-skeleton-generator`

Recommended review branches:

- `claude/docs/plan-review`
- `claude/review/pr-1`
- `devin/feature/builder-ci-bootstrap`

## MVP Acceptance Criteria

The MVP is successful when all of the following are true:

- one manifest-driven example project can be loaded without ambiguity
- contract version metadata exists in the manifest and internal models
- upstream, downstream, and staging-table inputs are represented as first-class contracts
- normalized metadata is produced from the example project
- explicit mapping metadata exists between contracts and canonical entities
- one target profile can generate a Spring Boot enterprise-oriented app skeleton
- generated output is isolated under a `BuiltAppN/` folder
- generation includes audit headers, Dockerfile scaffolding, and README scaffolding
- compatibility-oriented tests exist for the example project
- the codebase remains reviewable across Codex, Claude, and Devin workflows

## What Not To Do

- do not let multiple AI tools create separate competing master plans
- do not skip the manifest-driven input model
- do not generate internal domain models directly from raw external API payload shapes
- do not rely on implicit field-name matching where explicit mappings are required
- do not over-expand format support before the first end-to-end path works
- do not optimize for UI or orchestration before the builder core is credible
