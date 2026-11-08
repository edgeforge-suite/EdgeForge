# EdgeForge Repo Blueprint

> **Reference document.** Describes EdgeForge's foundational architecture and module structure. For current state, see `docs/appbuilder-context.md`. For current execution priorities, see `docs/enterprise-readiness-roadmap.md` and `docs/tracker/README.md`; `docs/current-implementation-sequence.md` is retained as history.
>
> **See also → [`suite-architecture.md`](suite-architecture.md)** is the front-door "START HERE" orientation (suite map, repo structure, routing table). This doc carries the deeper foundational architecture and module detail.

## Purpose

EdgeForge is a metadata-driven platform that generates enterprise applications for legacy-heavy domains. Its primary goal is to replace existing legacy applications with minimal or no impact to upstream API contracts and downstream handoff contracts such as APIs, files, messages, and batch interfaces.

The generated application must:

- Preserve existing external contracts wherever possible.
- Build a stable internal domain model from those contracts.
- Add and evolve business logic around that internal model.
- Support migration of existing legacy features in controlled phases.
- Generate applications that can target older enterprise runtime stacks as well as more modern profiles.

EdgeForge itself should act as a builder/control plane. It should not be tightly coupled to one generated runtime stack.

## Repository Governance

### Pull request policy

Changes in this repository should always be made through pull requests.

Rules:

- do not push directly to `main`
- do not merge directly to `main` without review
- every meaningful change should be done on its own branch and proposed through a PR
- reviews may be performed by different AI agents or tools before merge
- parallel PRs from different agents should be expected and handled cleanly

This repository should be treated as review-driven by default.

### Branch naming convention

Use structured branch names so human and AI-agent work stays easy to review.

Recommended patterns:

- `<agent>/feature/<short-description>` for new builder capabilities
- `<agent>/fix/<short-description>` for bug fixes
- `<agent>/docs/<short-description>` for documentation changes
- `<agent>/chore/<short-description>` for maintenance work
- `generated/<app-name>` for adding or updating a generated application folder
- `review/<agent>-<topic>` for review-agent branches

Where `<agent>` is one of: `claude`, `codex`, `devin`, or a human contributor name. These prefixes make authorship and review context immediately clear in GitHub while preserving work-type granularity.

Examples for AI tools:

- Claude Code: `claude/feature/<short-description>`
- Devin: `devin/feature/<short-description>`
- Codex: `codex/feature/<short-description>`

### Pull request convention

Recommended PR title prefixes:

- `[FEATURE]`
- `[FIX]`
- `[DOCS]`
- `[CHORE]`
- `[GENERATED]`

PR descriptions should include:

- what changed
- why it changed
- how it was validated
- open questions or follow-up items

### Generated application folder convention

Committed generated application snapshots should not live in this repository.
Regenerate representative apps from committed input packages under
`examples/input-projects/` or focused fixtures under `tests/fixtures/`.

`GeneratedApps/` is kept only as a documented placeholder for local generated
outputs; do not commit generated app source snapshots there unless a future
handover decision explicitly creates a tagged reference snapshot lane.

## Product Principles

### 1. Contract-first modernization

The first job is not to redesign the external interface. The first job is to preserve the interface and replace the inside.

### 2. Canonical internal model

External contracts may be old, inconsistent, or technology-specific. Generated applications should map those contracts into a normalized internal domain model that remains stable over time.

### 3. Adapters at the edge

Format-specific logic belongs at the boundary:

- REST/JSON
- SOAP/XML
- XSD/DTD-based XML
- XSLT-style mappings
- CSV
- fixed-width files
- batch file exchanges
- event/message payloads

The core business logic must remain independent from these transport and format concerns.

### 4. Compatibility by profile

Generated applications should not assume the newest Java version or framework ecosystem. Instead, generation must be driven by a target compatibility profile such as:

- legacy-compatible profile
- standard enterprise profile
- modern profile

Each profile controls runtime version constraints, library choices, packaging style, and code-generation patterns.

### 5. Migration as a first-class concern

EdgeForge must support coexistence and phased migration:

- preserve behavior while replacing internals
- migrate modules and features incrementally
- compare legacy vs generated outputs
- allow toggles or compatibility modes where required

### 6. Auditability and traceability

For enterprise use cases, generated applications need field lineage, transformation traceability, and regression evidence.

### 7. Explicit project inputs

EdgeForge should not guess system roles from arbitrary files alone. Each modernization effort should be provided as a structured input project with a manifest that explicitly declares:

- what the upstream interfaces are
- what the downstream interfaces are
- what staging-table or datastore handoffs exist
- what business-rule sources apply
- what target compatibility profile should be used

This keeps the MVP deterministic and reviewable.

The manifest may reference either local specification files or remote specification URLs where appropriate, such as a Swagger/OpenAPI endpoint for an upstream REST API.

## Recommended Technology Direction

### EdgeForge runtime

Use Python for EdgeForge itself.

Why:

- strong ecosystem for metadata ingestion, parsing, transformation, code generation, and orchestration
- faster iteration for generators and schema tooling
- easier support for XML, JSON, files, and mixed-format processing
- good fit for DSL/rules parsing and template-driven generation

Suggested builder stack:

- Python
- FastAPI for builder APIs
- Pydantic for metadata validation
- SQLAlchemy + Alembic for metadata persistence
- Jinja2 or equivalent templating for code generation
- PostgreSQL for metadata/config storage

The builder repository should use pinned dependency versions for reproducible development and generation behavior. When scaffolding begins, the repo should include explicit dependency management such as `requirements.txt` or equivalent lock-oriented Python project configuration.

### Generated application default

Use Spring Boot as the default generated target for enterprise applications, but drive generation through target profiles so older enterprise constraints can still be supported.

This means EdgeForge should generate for a declared compatibility target, not for a single fixed runtime stack.

## Proposed Repository Layout

```text
AppBuilder/
  GeneratedApps/
    README.md
  docs/
    repo-blueprint.md
    appbuilder-context.md
    # architecture/          (proposed, not yet created)
    # decisions/             (proposed, not yet created)
  appbuilder/
    api/
    core/
    contracts/
    metadata/
    mapping/
    rules/
    generation/
    target_profiles/
    testing/
  templates/
    springboot/
      legacy_compatible/
      standard_enterprise/
      modern_enterprise/
    python/
      service_profile/
  examples/
    input-projects/
    sample-domain/
      sample_api_specs/
      sample_xml/
      sample_files/
      sample_mappings/
  tests/
    unit/
    integration/
    golden_contracts/
  scripts/
  README.md
```

Committed generated application snapshots should not be kept in this repository.
Generate representative apps from `examples/input-projects/` or focused fixtures
under `tests/fixtures/`; keep local generated outputs outside tracked source.

## Generated Application Standards

Every generated application should be independently buildable and auditable.

### Non-negotiables

- each generated app must build independently
- each generated app must include its own `README.md`
- each generated app must include its own `Dockerfile`
- generated apps must not depend on EdgeForge at runtime
- compatibility tests must be generated alongside application code

### Enterprise generation rules

- monetary values should use `BigDecimal` in generated Java code
- date/time values should use `java.time.*`
- generated persistence changes should use versioned database migrations such as Flyway scripts
- EOD and batch-oriented enterprise flows should use generated Spring Batch scaffolding when the selected input package requires it

### Generated file traceability

Generated files should include a concise header comment describing:

- that the file was generated by EdgeForge
- the generation date or run identifier
- the source project or manifest reference
- the target compatibility profile

This improves auditability and makes generated vs hand-edited code easier to reason about.

## Core Modules

### `contracts`

Responsible for ingesting and validating external contract definitions.

In EdgeForge, a contract means any external interface definition that surrounding systems depend on and that must remain compatible during replacement.

Inputs may include:

- OpenAPI/Swagger
- WSDL
- XSD
- DTD
- XML samples
- JSON schemas
- CSV/fixed-width layout definitions
- mapping specs and transformation definitions
- staging table schemas used as integration handoffs
- validation/code-value/defaulting rules attached to external interfaces

Outputs:

- normalized contract metadata
- versioned contract registry entries

### `metadata`

Stores project, application, feature, compatibility profile, and generation settings.

Metadata is the normalized internal description EdgeForge creates after reading the input project package.

Key entities:

- project
- source contract
- downstream contract
- canonical entity
- field mapping
- business rule
- feature module
- target profile
- generation run
- integration system
- interface operation
- field definition
- sample payload/file reference
- staging table definition
- compatibility expectation

### `core`

Defines the canonical internal model and shared abstractions used by the builder.

Responsibilities:

- canonical entity representation
- field typing abstractions
- relationship modeling
- versioning metadata
- compatibility flags

### `mapping`

Contains transformation logic between external contracts and canonical domain models.

Responsibilities:

- external-to-canonical mapping specs
- canonical-to-external mapping specs
- transformation steps
- defaults and null handling
- validation and conversion rules

### `rules`

Captures business logic in declarative or semi-declarative form rather than hardcoding it into templates.

Possible rule types:

- field validations
- derived field logic
- workflow conditions
- enrichment rules
- routing rules
- compatibility-mode behavior

### `generation`

Converts metadata plus target profile into a generated application skeleton and feature modules.

Responsibilities:

- template selection
- code generation
- config generation
- packaging
- generation manifests
- generated file audit headers

### `target_profiles`

Defines runtime compatibility profiles.

Each profile should describe:

- target language and framework
- runtime/version baseline
- dependency set
- project structure
- code-generation conventions
- supported feature set

For example, an enterprise Spring Boot profile may specify:

- Java baseline
- Spring Boot baseline
- whether Flyway migrations are emitted
- whether Spring Batch scaffolding is emitted
- XML/SOAP support options

### `testing`

Produces and runs compatibility-oriented tests.

Must include:

- schema validation tests
- contract regression tests
- golden input/output comparisons
- legacy parity checks
- mapping validation tests
- end-to-end happy-path generation tests

## Generation Flow

### Phase 0. Input project load

Read the project manifest and validate that all referenced files exist and are supported.

### Phase 1. Contract ingestion

Read upstream API specs, downstream file/message specs, and relevant legacy definitions.

### Phase 2. Canonical model derivation

Create normalized domain entities and field relationships from the contract metadata.

### Phase 3. Mapping design

Generate explicit mappings from external formats into the canonical model and back out again.

### Phase 4. Business logic assembly

Attach rules, workflows, validations, and feature-specific behavior around the canonical model.

### Phase 5. Target profile generation

Generate the application according to the selected compatibility profile.

### Phase 6. Compatibility verification

Generate tests proving that external contracts and expected outputs remain intact.

## Compatibility Strategy

Backward compatibility and future-proofing should be handled through versioned profiles and versioned contracts, not informal conventions.

### Required mechanisms

- contract version registry
- target runtime profiles
- explicit support matrices
- template versioning
- generation manifests
- feature flags for migration
- golden-file regression suites

### Important rule

Never bind business logic directly to raw external schemas. Always map into the canonical model first.

That keeps old interfaces stable while allowing the internal application to evolve.

## Standard Input Project Model

For the MVP, each modernization effort should be supplied as a structured input package rather than as loose files.

### Example structure

```text
input-projects/
  xyz-accounts-modernization/
    app-definition.yaml
    upstream/
      crm-account-openapi.yaml
      sample-create-account-request.json
      sample-create-account-response.json
    downstream/
      eod-handoff-layout.yaml
      sample-output-file.txt
    data-handoffs/
      account-staging-table.sql
      staging-table-mapping.yaml
    rules/
      account-business-rules.yaml
    legacy/
      xyz-notes.md
      field-mapping.xlsx
```

### Purpose of the manifest

The manifest tells EdgeForge what each input means. The tool should not infer upstream vs downstream vs staging-table role only from file location or naming.

For supported interface types, the manifest should allow either:

- `spec`: a local file path inside the input project
- `spec_url`: a remote source such as a Swagger/OpenAPI URL

### Example manifest

```yaml
app_name: XYZ Accounts Replacement
bounded_context: accounts

upstream_interfaces:
  - name: crm-account-api
    type: rest-json
    spec_url: https://internal.example.com/xyz/swagger.json
    samples:
      - upstream/sample-create-account-request.json
      - upstream/sample-create-account-response.json

downstream_interfaces:
  - name: eod-handoff-file
    type: file-fixed-width
    spec: downstream/eod-handoff-layout.yaml
    samples:
      - downstream/sample-output-file.txt

data_handoffs:
  - name: account-staging-table
    type: staging-table
    spec: data-handoffs/account-staging-table.sql
    mapping: data-handoffs/staging-table-mapping.yaml

rules:
  - rules/account-business-rules.yaml

legacy_references:
  - legacy/xyz-notes.md
  - legacy/field-mapping.xlsx

target_profile: springboot-legacy-compatible
```

### Manifest responsibilities

The MVP manifest should declare:

- project/application identity
- bounded context
- upstream interfaces
- downstream interfaces
- staging-table or integration datastore handoffs
- rules sources
- optional legacy reference artifacts
- target compatibility profile

### Guidance on remote specs

Remote specs such as Swagger/OpenAPI URLs are useful for upstream API discovery, but they are not sufficient on their own for full application generation. The rest of the project package is still needed for downstream contracts, staging-table handoffs, rules, and legacy references.

## Metadata Built From Inputs

After loading the input package, EdgeForge should build metadata that is independent of any one raw source format.

### Example metadata categories

- project metadata
- participating systems such as CRM, XYZ, ETL, downstream applications
- interface definitions and operations such as `createAccount`, `updateAccount`, `getAccount`
- external request/response/file/table schemas
- canonical entities and fields such as `Account`, `CustomerId`, `AccountStatus`
- field-level typing, nullability, lengths, formats, defaults, code values
- mappings from upstream contracts to canonical entities
- mappings from canonical entities to staging tables or downstream files
- validation rules and business rules
- compatibility profile and generation settings
- test expectations and golden samples

### Example happy-path interpretation

For the `XYZ Accounts` scenario:

- the CRM JSON API is an upstream contract
- the staging table is a downstream integration contract because ETL depends on it
- the EOD handoff file is also a downstream contract, even if generated by ETL rather than the generated app directly
- EdgeForge uses those definitions to generate a replacement app that preserves the CRM-facing behavior and the staging-table handoff behavior

## MVP Scope

The MVP should be narrow and opinionated.

### Recommended MVP capabilities

- ingest one upstream API contract format and one downstream file/message format
- support XML and JSON from the beginning
- support staging-table handoffs as explicit integration contracts
- support a canonical domain model
- support explicit field mappings
- support basic business-rule definitions
- support a manifest-driven input project structure
- generate one Spring Boot target profile first
- generate compatibility test scaffolding
- include one domain example with sample contracts and expected outputs
- emit Flyway migration scaffolding for the first Spring Boot enterprise profile
- emit Spring Batch scaffolding when the project includes EOD or batch handoff requirements

### What to defer

- broad UI work
- multi-cloud deployment generation
- too many target stacks at once
- advanced workflow engines
- generalized low-code front-end generation

## Phased Roadmap

> **Note:** All MVP phases below were delivered in PRs #1–#10. Post-MVP features (Demo UI, SSO, Audit) delivered in PRs #11–#13. This section is preserved as historical record. For the current roadmap, see `docs/archive/post-mvp-roadmap.md`.

### Phase 1. Builder foundation ✅

- [x] create Python project scaffold with pinned dependencies
- [x] define manifest schema and input project loader
- [x] define normalized metadata models
- [x] define target profile abstraction

### Phase 2. XML/JSON contract ingestion ✅

- [x] parse OpenAPI and Swagger sources from local files or `spec_url`
- [x] parse XML-related specs and examples
- [x] normalize contracts into metadata
- [x] validate project packages against the manifest schema

### Phase 3. Mapping and rule engine ✅

- [x] support field mapping definitions
- [x] support staging-table mapping definitions
- [x] support validation and business-rule definitions
- [x] support canonical-model transformations

### Phase 4. Spring Boot enterprise profile generator ✅

- [x] generate core project structure
- [x] generate domain, adapter, and persistence layers
- [x] generate Flyway migration scaffolding
- [x] generate Spring Batch scaffolding where applicable
- [x] generate Dockerfile and app-specific README

### Phase 5. Compatibility harness ✅

- [x] generate contract regression tests
- [x] generate golden-file comparisons
- [x] generate legacy parity test scaffolding
- [x] add one end-to-end happy-path example for the `XYZ Accounts` scenario

### Phase 6. Generated app packaging model ✅

- [x] generate application-specific output under `BuiltAppN/`
- [x] keep each generated app independently buildable
- [x] prepare each generated app for later extraction into its own repository and Docker image

## Open Questions

- ~~what exact manifest schema should be frozen for Phase 1?~~ **Resolved:** See `docs/manifest-schema.md` and `appbuilder/contracts/manifest.py`.
- ~~what should the initial enterprise-compatible Java and Spring baselines be for each target profile?~~ **Resolved:** Java 17 / Spring Boot 3.3.5 for legacy-compatible, Java 21 / Spring Boot 3.3.5 for standard-enterprise. See `appbuilder/target_profiles/catalog.py`.
- ~~which database baselines should be supported first for generated migrations?~~ **Resolved:** H2 in-memory for dev. Flyway DDL is database-agnostic. Production DB is a profile change outside EdgeForge.
- how much XSLT behavior should be parsed vs executed directly? *(Still open — XSLT/XSD ingestion is P2 priority, deferred until after OpenAPI and multi-entity PRs)*
- ~~what minimum review artifacts should be generated for business-rule mappings?~~ **Resolved:** Mapping completeness reports with warnings/errors. See `appbuilder/mapping/ingestion.py`.

## Risks To Design For Early

- external contract ambiguity in legacy systems
- undocumented legacy behaviors
- schema drift between environments
- differences between sample payloads and actual production behavior
- hardcoded data assumptions in old systems
- runtime constraints in self-hosted enterprise environments

## Definition Of Success

EdgeForge is successful when it can take existing upstream and downstream interface definitions, derive a stable internal model, generate a replacement application, and prove through tests that the new application preserves critical contract behavior while allowing new business features to be added safely.
