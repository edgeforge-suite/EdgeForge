# EdgeForge

Product: EdgeForge. Python module/CLI: `appbuilder`.

EdgeForge is a Python-based contract-preserving modernization engine. It translates reviewed manifest packages into generated Spring Boot applications while keeping upstream and downstream integration contracts stable.

> **Start here / architecture:** new to the suite (human or AI agent)? Read
> [`docs/suite-architecture.md`](docs/suite-architecture.md) — the front-door
> map of the 5 repos, core theses, this repo's structure, and where to go for a
> given task. The canonical docs index is [`docs/README.md`](docs/README.md).

## Project intent and community

EdgeForge is an independently maintained open-source project, shared freely under
[Apache-2.0](LICENSE). Contributions and feedback are welcome. Individuals and
enterprises may use, modify and redistribute it, including commercially, under
those terms. The maintainer does not seek sponsorship or offer paid services,
consulting, custom implementation or managed deployments through this project.
No response deadlines, fixes, delivery dates or ongoing operational support are
promised. Community contributions that improve correctness, stability and
usability are especially welcome. Enterprise adoption is welcome under the
same license; it does not establish affiliation, endorsement or maintainer
service commitments.

Start with the [documentation](docs/README.md). Use
[project issues](https://github.com/edgeforge-suite/EdgeForge/issues) for ordinary
questions, bugs and suggestions once the public destination is activated; its
availability is not asserted here. See [CONTRIBUTING](CONTRIBUTING.md) for
contributions and [SECURITY](SECURITY.md) for private vulnerability reporting.
Share only synthetic examples and redacted diagnostics.

## Quickstart

The 10-minute golden path — clone → set up → generate the sample app → build,
run, and exercise its test console — is [`docs/quickstart.md`](docs/quickstart.md).

## Import & handover readiness

> **Evaluating EdgeForge for import (compliance / security reviewer)?** Start at
> the **[handover-evidence index](docs/handover-evidence/README.md)** — one page
> mapping every import-review concern (license & dependencies, secrets/real-data,
> compliance & portability, security boundaries, edge-contract capability,
> governance, CI) to its **linked, authoritative evidence**, with an **honest**
> consolidated status (what's proven, what's *adopter-decides*, what's
> *post-import* — nothing greenwashed).

Key entry points behind that index: the
[compliance & portability checklist](docs/compliance-and-portability.md) (G7), the
[security boundary map](docs/security-boundary-map.md) (G8), the
[edge-contract readiness matrix](docs/edgecontracts/edge-contract-handoff-readiness-matrix.md)
(C4), and the [SBOM + license inventory](docs/handover-evidence/dependencies.md)
(G4). The suite-level master tracker is the
[enterprise-readiness roadmap](docs/enterprise-readiness-roadmap.md).

## Suite status

**v5.0.0 source preparation:** [approved release scope and cutover](docs/v5-release-readiness.md)
select source repositories and tags under Apache-2.0, not official binaries/images
or production certification. Maintainer publication authorization
and verified reporting routes remain public-exposure gates. This is the private
v5 release-preparation repository under
[edgeforge-suite/EdgeForge](https://github.com/edgeforge-suite/EdgeForge).
The private import is complete; public launch remains gated. The historical
baseline below is not v5 acceptance. Docker recipes support
self-managed builds, not official published images or a maintainer-operated service.

EdgeForge claims no ownership of your generated applications; Apache-2.0 covers EdgeForge itself, while third-party components and any incorporated licensed material retain their applicable terms.

References to pre-v5 commits, pull requests, issues and workflow runs point to the private development archive and may be inaccessible to public readers.

See [NOTICE](NOTICE), [third-party attribution](docs/third-party-attribution.md)
and [SECURITY](SECURITY.md). The candidate descriptor embedded in release source
or an eventual tag may predate final selection. After acceptance and separately
authorized publication, the v5.0.0 Release record will identify the accepted
Engine/Studio/KS revisions, validation and limitations. That record does not yet
exist; no embedded historical descriptor establishes the accepted v5 pairing.
The [three documented import exclusions](docs/v5-release-readiness.md#public-import-exclusions-and-historical-replay)
retain their originals privately. Public readers cannot fully replay that
historical Maven/vendor assessment from the public repository alone; normal
tests and product use do not require the excluded inputs.

Current generated build changes select reviewed Noble multi-platform index pins
and targeted build-plugin realms without changing the application dependency
policy. See [generated build references](docs/generated-build-reference-policy.md).
The [Noble assessment](docs/handover-evidence/generated-images/2026-10-20-noble/README.md)
records 30 cases/60 stages, three representative production startups and separate
compatibility/default/native proof. Findings and coverage limitations remain
explicit; this does not establish M2 or release clearance.

Ordinary generation and contributions do not require the release-evidence
campaign. Maintainers replaying or retaining assessment evidence should use the
[tool map and workflow boundaries](docs/handover-evidence/generated-image-maintainer-tools.md).

The **historical `v4.1.0` suite baseline** (Engine + Studio `v4.1.0`, KS `v4.0.0` — the
feature-flagged regen-preview UX increment on the `v4.0.0` enterprise-readiness MVP / handoff
baseline) has its Engine handover-evidence pack and reviewer front-door in place. That baseline
is **proven GREEN by the hermetic
L5 acceptance gate** (cross-repo runtime + multi-session isolation + regenerate/maintain
data-integrity), so the available evidence is ready for adopter review. The Engine-owned
import-gate lane remains **partial**: G2, G3, G4, G7, G8, and G10 are delivered, while G5
still requires example classification and active-reference cleanup. PR #291's canonical-fixture
shape guard is intentionally bounded and is not a repository-wide semantic-neutrality scan.
Adopter-decided and post-import work also remains — IdP wiring and any future
optional-AI production gate. Maintainer publication authorization (G1) is separately
pending, as listed under "still open" below and tracked in the
[enterprise-readiness roadmap](docs/enterprise-readiness-roadmap.md). This summary
is intentionally high-level so it stays current; the authoritative, living detail
lives in the sources below (follow them rather than a PR-by-PR list here, which
would re-stale).

**Where the living detail is:**

- **Import / handover readiness** → the
  [handover-evidence index](docs/handover-evidence/README.md): SBOM + dependency
  licenses, secret-pattern scan plus synthetic-data policy/review evidence, the compliance &
  portability checklist, the
  security boundary map, the edge-contract readiness matrix, governance files, and
  CI — each mapped to its evidence with an honest per-concern status.
- **Plan & what's in flight** → the
  [enterprise-readiness roadmap](docs/enterprise-readiness-roadmap.md) (suite-level
  master tracker); the full doc set is indexed in [`docs/README.md`](docs/README.md).
- **Release history** → [`CHANGELOG.md`](CHANGELOG.md) — **`[5.0.0]` source preparation**,
  with acceptance and publication pending; dated `[1.0.0]` through `[4.1.1]` entries remain intact.
  Future changes accrue under `[Unreleased]`.

**Established functional coverage (historical proof):** the CRUD, passthrough-router, and Kafka-integration
Engine lanes are proven end to end, and **edge-contract v1 is closed and proven** —
REST / JSON, fixed-width, CSV, XML / XSD, and *bounded* SOAP. See the
[edge-contract readiness matrix](docs/edgecontracts/edge-contract-handoff-readiness-matrix.md)
for the honest per-family status; further edge-contract families are **parked**
until there is real demand (neither reopened nor overclaimed). **No LLM or
provider integration exists in the suite today** — there is no Knowledge Assist
AI capability to enable.

**Honestly still open** — the Engine-owned, adopter-decided, cross-repo, and post-import remainder:

- **Engine G5 reference hygiene** — classify the retained examples and clean active references;
  PR #291 proves the exact canonical CI fixture shape only, not repository-wide semantic neutrality.

- **Publication authority** — Apache-2.0 is selected; maintainer publication
  authorization is pending before public exposure (G1).
- **Per-repo import-gate governance** — this **Engine** repo has delivered its governance,
  secret-pattern scan, and SBOM gates, but its composite import-gate lane remains partial while
  G5 is open; each sibling repo (Studio, KS) carries its **own** equivalent governance in its own
  thread. The `v4.1.0` *functional* suite baseline (Engine +
  Studio + KS) is **L5-proven**; **TestBench and shared-specs are optional and outside
  this coordinated baseline**.
- **Generated-app authentication/authorization** — **no shipped target profile emits
  in-application authentication or authorization.** Generated apps are designed for
  deployment behind an authenticated, TLS-terminating gateway (Option A,
  [P1-5 design](docs/generated-app-standards/generated-app-security-posture-design.md)).
  An OAuth2 resource-server skeleton exists in Engine as an **internal dormant
  emitter**, inactive in every shipped profile; it is not a supported extension
  surface. (Studio / KS SSO + RBAC is a separate, later track.)
- **Optional-AI production gate** — no LLM or provider integration exists in the
  suite today; the **KS-B5** data-handling design (PII / sanitization /
  redaction) gates any future provider layer.

## Current Phase Map

- Phase 2 = EdgeForge v1 closed baseline
- Phase 3 = production quality hardening
- Phase 4 = Engine MCP server
- Phase 5 = Knowledge Server MCP
- Phase 6 = LegacyExtractor MCP

Current planning is tracked in the
[enterprise-readiness roadmap](docs/enterprise-readiness-roadmap.md) (suite-level
master tracker) and the
[edge-contract expansion roadmap](docs/edge-contract-expansion-roadmap.md).

## Named Target Profiles

- `springboot-legacy-compatible` — Java 17 + H2 compatibility-first baseline
- `springboot-enterprise-postgres-java17` — Java 17 + PostgreSQL enterprise baseline for environments standardized on Java 17
- `springboot-standard-enterprise` — Java 21 + PostgreSQL enterprise baseline

All three ordinary IDs now select **Spring Boot 4.1.1** for fresh CRUD/REST,
bounded SOAP, passthrough, JDBC Batch/M5a and Kafka/router applications. Their
former `-boot41-preview` aliases are retired and are unsupported profile IDs. Java, database,
audit and console intentions are unchanged. Jobless output stays Batch-free.
Existing Boot 3 or ambiguous packages refuse generate/plan/apply before writes;
no application, database or Batch-history migration is supplied. External
database freshness remains a deployment precondition, not universal detection.
See the [Boot 4.1 guide](docs/generated-app-standards/boot41-jobless-preview.md)
for supported cases, exclusions and proof commands.

## Completed Phase 3 Hardening

Phase 3 was the EdgeForge v2 hardening pass. The completed implementation stack is:

1. `A2` — date/type propagation hardening in `translation.py`
2. `A3` — first-class preserved custom / non-CRUD operation support
3. `B4` — audit baseline decision and validation
4. `B5` — ISO-4217 real code emission
5. `B6` — fixed-width padding/truncation from layout spec
6. `C8` — production Postgres datasource profile
7. `B7` — pagination baseline decision
8. `A1` — transaction/event identity semantics via `identity_overrides`
9. `C9` — numeric/sequence ID strategy via `id_generation_overrides`

Two architecture conclusions were explicitly design-first and are now represented as additive manifest extensions:

- `A1` transaction/event identity semantics via `identity_overrides`
- `C9` numeric / sequence generated-ID strategy via `id_generation_overrides`

## Manifest Policy

The coordinated manifest cut is complete: V2-E makes Engine single-dialect `manifest-v2` /
`schema_version: "2.0"`, V2-S makes Studio export `2.0`, and both paired-branch and post-merge
V2-X proofs passed. No `1.0` compatibility bridge is retained. See the
[durable V2-X result](docs/test-results/manifest-v2-cut-v2-x-2026-08-16.md).

Subsequent candidate extensions remain optional and additive within the active `2.0` dialect unless
a separate maintainer-approved paradigm change explicitly reopens compatibility policy. The
coordinated 2.0 cut is the sole approved exception to the former no-breaking-change rule.

## Golden Contract Policy

Each future generator behavior fix PR should update the relevant golden contract assertions in the same PR. Regression signals are part of the feature/fix itself, not a follow-up chore.

Example:

- a date/type propagation fix should assert `TIMESTAMP` instead of `VARCHAR`

## Phase 3 Acceptance Target

The historical downstream acceptance target was a **privately retained external-application v4 baseline**:

- reference downstream design and review remain in the private development archive
- Phase 3 acceptance was anchored by generating that baseline and its downstream v4 verification checklist, not the new Workspace/Item example

## Baseline Tags

The Phase 2 completion baseline is:

```bash
git tag -a v1.0.0 -m "EdgeForge v1 — Phase 2 complete baseline"
git push origin v1.0.0
```

The second cross-repo baseline is:

```bash
git tag -a v1.5.0 -m "EdgeForge v1.5.0 - Phase 3 hardening and Phase 4 MCP baseline"
git push origin v1.5.0
```

`v1.5.0` marks the April 12, 2026 Engine baseline after Phase 3 production hardening, Phase 4 local Engine MCP, and the paired Studio `generate_app` MCP integration through Studio PR `#58`.

The previous documented v2.0.0 suite state was the April 21, 2026 Engine-side
suite state after the bounded field-suggestion-only KS Studio MVP landed on
`main`, the Studio smoke/proof passed, and the post-MVP docs/proof cleanup was
merged.

The `v3.0.0` suite baseline tag is cut:

```bash
git tag -a v3.0.0 -m "EdgeForge v3.0.0 - Studio UX v3 + KA broader scopes + Docker Studio baseline"
```

`v3.0.0` marks the May 2026 suite baseline with Studio UX v3, broader
Knowledge Assist scopes, Evidence Trail v1.1, Docker Studio runtime, Kafka
router Studio support, KS field-level conflict deltas, and the privately retained external-application CRUD/Knowledge Assist
manual smoke / downstream EOD verification.

That historical smoke refers to privately retained original evidence, not the
new independent [Workspace/Item example](examples/input-projects/workspace-items/README.md).
Its separate proof and content treatment are recorded in
[publication preparation](docs/public-content-preparation.md).

The current suite baseline is **`v4.1.0`** — the feature-flagged regen-preview UX increment on
the `v4.0.0` enterprise-readiness baseline. Suite pin: engine `v4.1.0` `8f758f4` / studio
`v4.1.0` `6537a75` / ks `v4.0.0` `11aed44` (**KS unchanged — not retagged**). Engine and Studio
are re-verified GREEN by the hermetic **L5 acceptance** gate, including the regen-apply addendum.

The prior **`v4.0.0`** enterprise-readiness MVP / handoff baseline (edge-contract v1,
regenerate / maintain-over-time, multi-session / shared deployment, G10 handover-evidence pack):
engine `077bc01` / studio `0e58f9e` / ks `11aed44`
([acceptance evidence](docs/handover-evidence/l5-acceptance-run.md)).

Tags are cut per repo:

```bash
git tag -a vX.Y.Z <pinned-sha> -m "EdgeForge vX.Y.Z — <summary>"
git push origin vX.Y.Z
```

For a future coordinated v5 release, a tagged Engine source checkout may
contain an earlier **candidate** descriptor, not the final accepted Suite
selection. Consult the eventual GitHub Release body (or its linked later
acceptance record) for the full-SHA candidate-descriptor commit and evidence
record, then compare their selected Engine/Studio/KS commits with the tested
run SHAs. See the [release-pairing guide](docs/suite-release-pairing.md) and
[proposed v5 release sequence](docs/v5-release-readiness.md). This guidance is
not a claim that v5 has been accepted or released.

Post-baseline work continues on `origin/main`. For the current state and the
detailed history, see the
[enterprise-readiness roadmap](docs/enterprise-readiness-roadmap.md) and
[`CHANGELOG.md`](CHANGELOG.md) (being brought current — roadmap **A3**) rather than
a PR list here.

## Working Rules

- all changes go through PRs
- do not push or merge directly to `main`
- review-first GitHub workflow only
- generated applications are regenerated from committed input packages/fixtures;
  do not commit generated output snapshots under `GeneratedApps/`
- generated applications emitted by EdgeForge Engine remain standalone artifacts;
  the adopter decides their licensing and ownership terms for the target
  deployment context
- no generated-app repo changes during docs/planning-only phases

## Local Run

Install dependencies:

```bash
python3.11 -m venv --copies .venv
.venv/bin/python -m pip install -c requirements-lock.txt -r requirements.txt
.venv/bin/python -m pip check
```

Run tests:

```bash
.venv/bin/python -m pytest -v
```

Generate the sample application:

```bash
.venv/bin/python -m appbuilder.cli generate \
  --manifest examples/input-projects/workspace-items/app-definition.yaml \
  --output /tmp/edgeforge-workspace-items
```

Build the generated Spring Boot app:

```bash
cd /tmp/edgeforge-workspace-items
mvn clean compile
```

## Local Engine MCP

Phase 4 exposes EdgeForge Engine as a local stdio MCP server. It is a thin
adapter over the existing deterministic Engine functions and requires Python
3.11+ (the Engine v5 minimum, including FastMCP):

```bash
.venv/bin/python -m appbuilder.mcp_server
```

Example MCP client config:

```json
{
  "mcpServers": {
    "edgeforge-engine": {
      "command": "/path/to/EdgeForge/.venv/bin/python",
      "args": ["-m", "appbuilder.mcp_server"],
      "cwd": "/path/to/EdgeForge",
      "env": {
        "EDGEFORGE_MCP_ALLOWED_ROOTS": "/path/to/EdgeForge:/tmp"
      }
    }
  }
}
```

`EDGEFORGE_MCP_ALLOWED_ROOTS` is required for MCP generation tools. It is an OS
path-list (`:` on macOS/Linux) of per-session roots that `manifest_path` and
`output_dir` must resolve under; the process current working directory and
Engine repository are never implicit roots. The CLI remains unconstrained for
local development when this variable is unset, but setting `EDGEFORGE_SHARED_MODE`
requires the same per-session roots for CLI path-taking commands.

For validation transport details, see `docs/engine-mcp-design.md`, especially
the distinction between MCP `validate_manifest` / `validate_package()` semantics
and Studio flows that require full `load_project_definition()` package loading.

Phase 4 stdio does not expose an HTTP health endpoint or `--port`. Clients
should treat MCP initialization, `list_tools`, or a lightweight
`get_manifest_schema` call as the local liveness check.
