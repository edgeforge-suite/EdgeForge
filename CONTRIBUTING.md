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
- keep examples synthetic and exclude secrets and private employer/customer
  material. Necessary public dependency names, upstream references and attribution
  are permitted for accurate documentation and supported examples. Preserve the
  applicable source/distribution permissions, notices and modification disclosures;
  public attribution does not authorize private material.
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

## PR lifecycle and ownership

GitHub Issues are authoritative for task ownership and progress. The Engine-owned
Suite roadmap sets direction; the tracker is a dated documentation view, not an
assignment board. A Project board is optional and does not replace issue ownership.

1. Before substantial work, comment on the owning issue with the proposed scope
   and obtain maintainer confirmation of ownership.
2. Open a focused draft PR linked to that issue. Explain the problem, resulting
   change, relevant validation and compatibility risks.
3. Mark the PR ready when implementation and relevant checks are complete.
   **Ready for review does not mean approved.**
4. Record review findings and their resolution in the PR. Identify the reviewed
   revision and review subsequent changes; an earlier approval does not
   automatically cover a new revision.
5. Maintainers retain merge control. Before merging, confirm applicable checks
   passed, required findings are resolved and the latest changes have been reviewed.
6. After merging, check applicable main-branch results and update the linked issue
   with the outcome; close it only when its work is complete. Delete completed
   branches only when they are no longer needed.

Recorded Claude/Codex review reports are review evidence, not formal GitHub
approvals. Identify the actual reviewer and reviewed revision. When the maintainer
also authored the PR, record their merge decision as a maintainer decision, not an
independent human approval. Preserve the existing independent-review approach and
any task-specific repair/re-review limits; this process adds no universal second
review, new release gate or reset of an existing allowance.

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

Current repository: `https://github.com/edgeforge-suite/EdgeForge`.
The approved private import is complete; the original `santosh-sh` repository
remains the private pre-v5 archive. Public exposure requires maintainer
authorization under the [release policy](docs/v5-release-readiness.md).
Private security reports follow [SECURITY.md](SECURITY.md), never public issues.

EdgeForge claims no ownership of your generated applications; Apache-2.0 covers EdgeForge itself, while third-party components and any incorporated licensed material retain their applicable terms.

References to pre-v5 commits, pull requests, issues and workflow runs point to the private development archive and may be inaccessible to public readers.

## Release Procedure

For v5, the approved [fresh-repository cutover sequence](docs/v5-release-readiness.md#replacement-cutover-and-release-sequence)
supersedes the old archive-repository E/P/R/M ordering. The selected v5 sources
and completed technical acceptance are recorded in the
[acceptance results](docs/handover-evidence/v5-acceptance-2026-11-10.md).
Documentation-only successors do not change those sources or restart acceptance.
The procedure below describes release ordering; tag creation, settings and
publication require separate human authorization.

Before cutting a coordinated Engine release tag:

1. Update `pyproject.toml` `[project].version`.
2. Update `appbuilder/__init__.py` `__version__`.
3. Promote `CHANGELOG.md` `[Unreleased]` content into the release section.
4. Refresh active `README.md` release guidance; preserve the historical Suite
   baseline and change the candidate descriptor only at separately authorized P.
5. Human-merge the three preparation PRs, then select tested source commits E/S/K.
   Record the candidate at P, execute coordinated acceptance and record results
   at R; obtain independent release review as the canonical sequence requires.
6. Confirm required tests and generated-app compile/standalone checks actually
   executed at the selected Engine source. A later docs-only head does not
   inherit proof from an earlier head. Confirm package/version agreement.
7. Only under subsequent human authorization, after the last advisory check,
   create and push an annotated tag on the tested source commit, never P/R.
   The following is a future operator template, not a preparation command:

   ```bash
   git tag -a vX.Y.Z <tested-source-sha> -m "EdgeForge vX.Y.Z — <summary>"
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
