# Contributing to EdgeForge

Product: EdgeForge. Python module/CLI: `appbuilder`.

> **This is the authoritative rules home for the EdgeForge Engine repository.**
> The tool-specific entry files — [`CLAUDE.md`](CLAUDE.md), [`AGENTS.md`](AGENTS.md),
> and [`.github/copilot-instructions.md`](.github/copilot-instructions.md) — are
> thin pointers to this file and favor no single tool. For suite orientation and
> the "Where do I go for X?" routing table, see
> [`docs/suite-architecture.md`](docs/suite-architecture.md).

Read these files before making meaningful changes:

- `docs/suite-architecture.md` — suite orientation and the routing table
- `docs/appbuilder-context.md`
- `docs/repo-blueprint.md`

## Project Purpose

EdgeForge is a contract-preserving modernization platform for legacy-heavy enterprise domains.

The builder should:

- preserve upstream API contracts
- preserve downstream handoff contracts such as files, tables, and messages
- build a canonical internal model from those contracts
- generate replacement applications that remain backward compatible at the edges

## Non-Negotiable Architecture Rules

- prefer a canonical internal model instead of reusing raw external contract shapes as the internal domain model
- use manifest-driven structured input packages rather than guessing from arbitrary files
- treat staging tables and downstream handoffs as first-class contracts
- keep generated applications profile-driven for compatibility, not hardcoded to one runtime stack
- keep external adapters separate from core business logic
- keep Engine output deterministic — the same manifest produces the same generated app; no generic AI inference, no silent auto-apply, and no name inference; every `active`/explicit mapping must generate a supported artifact or fail fast with a clear message
- keep edge contracts in their arrays — declare upstream/downstream edge contracts under `upstream_interfaces[]` / `downstream_interfaces[]` only; never add parallel `*_contracts[]` arrays, and never route file/XML/SOAP edge contracts through `data_handoffs[]` (that stays table/datastore-handoff oriented)
- evolve the manifest additively only — V2-E makes Engine single-dialect
  `schema_version: "2.0"`; add concepts as optional, backward-compatible extensions within that
  active dialect. The maintainer-approved V2-E/V2-S/V2-X cut is the sole exception to preserving
  the prior `1.0` dialect, and the coordinated cut remains incomplete until V2-S and both V2-X
  proofs pass

## Repository Workflow Rules

- do not push directly to `main`
- do not merge directly to `main`
- all changes should go through pull requests
- expect parallel review branches from multiple AI agents
- keep examples synthetic and exclude customer/private organization material;
  public upstream references, dependency names and source-specific attribution
  are permitted when needed for accurate documentation and supported samples
- treat `.claude/session-notes.md` as Claude-local continuity context; do not commit it and do not edit it unless explicitly asked
- adopter-defined review automation should be configured through `CODEOWNERS`,
  branch protection, and required checks; this repo does not carry a
  personal-agent review workflow

Recommended branch naming:

- `<agent>/feature/<short-description>` for new builder capabilities
- `<agent>/fix/<short-description>` for bug fixes
- `<agent>/docs/<short-description>` for documentation changes
- `<agent>/chore/<short-description>` for maintenance work
- `generated/<app-name>` for adding or updating a generated application folder
- `review/<agent>-<topic>` for review-agent branches

Where `<agent>` is one of: `claude`, `codex`, `devin`, or a human contributor name.

Examples for AI tools:

- Claude Code: `claude/feature/<short-description>`
- Devin: `devin/feature/<short-description>`
- Codex: `codex/feature/<short-description>`

Recommended PR title prefixes:

- `[FEATURE]`
- `[FIX]`
- `[DOCS]`
- `[CHORE]`
- `[GENERATED]`

## Generated Application Rules

- each generated app lives in its own top-level folder (for example under `GeneratedApps/`), is independently buildable, and ships its own `README.md` and `Dockerfile`
- generated applications must not depend on EdgeForge, Studio, Knowledge Server/Assist (KS/KA), or MCP at runtime

For enterprise Spring profiles:

- use `BigDecimal` for money
- use `java.time.*` for date/time values
- emit versioned database migrations such as Flyway scaffolding
- emit Spring Batch scaffolding when EOD or batch handoffs are part of the input package

The detailed, authoritative generated-app standards live in
[`docs/generated-app-standards/`](docs/generated-app-standards/README.md) — the
generated-app quality gate, the Generated App Engine Roadmap, the Test Console UX
Standard, the Identity-Role Engine Behavior design, and the Cross-Service
Integration design. Reference those for specifics rather than restating them here.

## Guidance For Reviews And Changes

- preserve the manifest-driven MVP scope
- prefer small, reviewable changes
- call out risks to contract compatibility clearly
- if a change weakens backward compatibility, surface that explicitly
- do not replace the canonical-model approach with direct API-to-entity generation

## Contributions and licensing

See [project intent and community](README.md#project-intent-and-community) for
ordinary questions, feedback and the maintainer's service boundaries.

EdgeForge uses [Apache-2.0](LICENSE). Sign off every contribution under the
[Developer Certificate of Origin 1.1](https://developercertificate.org/), using
`git commit -s` to add `Signed-off-by: Your Name <your-email>` with an identity
you are authorized to use. The sign-off certifies your right to submit the
contribution on those terms; it is not a CLA. Do not sign for someone else or
submit private employer/customer material. No CLA is required. Maintainers
review contributions and retain merge control.

Current destination: `https://github.com/edgeforge-suite/EdgeForge` (planned
fresh repository; availability is not asserted). The existing private repository
receives preparation changes before becoming the pre-v5 archive. See the
[release policy](docs/v5-release-readiness.md) for pending publication authority.
Private security reports follow [SECURITY.md](SECURITY.md), never public issues.

EdgeForge claims no ownership of your generated applications; Apache-2.0 covers EdgeForge itself, while third-party components and any incorporated licensed material retain their applicable terms.

References to pre-v5 commits, pull requests, issues and workflow runs point to the private development archive and may be inaccessible to public readers.

## Release Procedure

For v5, the approved [fresh-repository cutover sequence](docs/v5-release-readiness.md#replacement-cutover-and-release-sequence)
supersedes the old archive-repository E/P/R/M ordering. Preparation does not
authorize versions, tags, imports, settings or publication. The commands below
are later human-directed operations, not instructions to run in a preparation PR.

Before cutting a coordinated Engine release tag:

1. Update `pyproject.toml` `[project].version`.
2. Update `appbuilder/__init__.py` `__version__`.
3. Promote `CHANGELOG.md` `[Unreleased]` content into the release section.
4. Refresh the root `README.md` baseline/status and any suite-baseline notes.
5. Confirm the version matches the intended `vX.Y.Z` tag.
6. Run the required tests and generated-app compile checks.
7. Create and push an annotated tag:

   ```bash
   git tag -a vX.Y.Z -m "EdgeForge vX.Y.Z — <summary>"
   git push origin vX.Y.Z
   ```

## Pre-Import Activation Checklist

Before an adopting organization imports this repository into its enterprise
GitHub/GitLab organization:

- Replace placeholder owners in `.github/CODEOWNERS` with real teams.
- Verify the selected project reporting routes at cutover; adopters separately
  configure internal reporting and support without inventing a project SLA.
- Configure branch protection and required checks for `main`.
- Decide whether the non-blocking Ruff signal should become blocking.
- Configure the adopter-defined review process; do not rely on personal-agent
  workflow files.
- Preserve Apache-2.0 and third-party notices. Adopters separately review their
  own usage and operating policies; these are not additional project license terms.
