# Suite Release-Candidate Pairing

This document defines the bounded release-pairing foundation for the three core EdgeForge Suite
repositories. The sole candidate-selection descriptor is
[`suite-release-candidate.json`](suite-release-candidate.json). It records the frozen v5
sources selected after the three release-preparation PRs merged. Acceptance
results are recorded separately. The historical baseline retains its original
scope.

## Candidate, Run, Evidence, and Release

These records answer different questions and must not be substituted for one another:

| Record | What it establishes | What it does not establish |
|---|---|---|
| Candidate selection | The exact Engine, Studio, and KS revisions selected for a future proof run | That the revisions work together |
| Observed run SHAs | The revisions and environment an individual smoke run actually exercised | A reusable candidate selection or future compatibility |
| Scoped historical evidence | The result and limits of one completed proof at its recorded pins | Acceptance of a newer candidate |
| Accepted release | A coordinated release decision supported by the required current evidence | Established by matching Git revisions alone |

The historical [`suite-baseline.json`](suite-baseline.json), L5 run manifests, and committed test
evidence keep their existing scopes. They are not competing active candidate lists and are not
promoted by this foundation.

## Active Selection

The active selection has candidate ID `public-v5-preparation`, targets `v5.0.0`, and
keeps `acceptance_status` set to `pending`. It selects manifest schema `2.0` and these exact commits:

| Role | Repository | Selected commit |
|---|---|---|
| Engine | `edgeforge-suite/EdgeForge` | `c52dd93b5c33b74f6ead06e15490415740874716` |
| Studio | `edgeforge-suite/EdgeForgeStudio` | `b412050531f18813354df0406e41d4fed0ce9f86` |
| KS | `edgeforge-suite/EdgeForgeKnowledgeServer` | `6fb5be6efd82e93ca735595e9e7b37dfb5f36418` |

The record contains no branch names, version ranges, credentials, or checkout paths.
The pins identify the tested PR #1 merge commits. The PR #2 documentation
successors remain separate from this selection. The canonical
[release sequence](v5-release-readiness.md#replacement-cutover-and-release-sequence)
defines the acceptance and public-launch gates.

## Preflight Usage

Prepare three separate clean checkouts at the selected E/S/K and run the
verifier from a clean checkout of the committed candidate record P:

```bash
python scripts/verify_suite_pairing.py \
  --candidate docs/suite-release-candidate.json \
  --engine-checkout "$ENGINE_CHECKOUT" \
  --studio-checkout "$STUDIO_CHECKOUT" \
  --ks-checkout "$KS_CHECKOUT"
```

All four arguments are required. The checkout running the verifier may differ from the selected
Engine checkout; this permits a future Engine commit to verify a separately pinned Engine worktree
without exempting Engine from the same checks.

The verifier validates the descriptor before inspecting Git. For each role, it requires the supplied
directory to be the intended repository's exact worktree root, at the declared full commit, with no
tracked changes or non-ignored untracked files. It rejects index flags that could hide tracked-file
changes and disables Git replacement-object interpretation while inspecting the selected commit.
Detached worktrees are supported. The verifier does not fetch, switch, reset, clean, install, launch
KS, or run any product process.

The path-free JSON report is deterministic for identical inputs and always states that release
acceptance is not established. Its result is `pins-match` only when all three clean revisions match;
all other outcomes are `pins-mismatch` and fail closed.

| Exit | Meaning |
|---:|---|
| `0` | All three intended repositories are clean and match the selected commits |
| `1` | Checkout verification completed and at least one checkout mismatched |
| `2` | Input was invalid or Git inspection tooling was unavailable or failed |

## Operating Boundary

Run this preflight separately and immediately before the existing smoke command selected for the
release proof. A successful preflight does not lock the worktrees or prevent a later change, so the
proof must use a controlled checkout set and must continue to record the revisions that actually ran.

This foundation does not implement the M3 scenario registry, affected-set scheduler, resolved-run
identity, environment provenance, evidence bundle, runtime negotiation, or acceptance decision. It
also does not replace the remaining security closure or final coordinated public-v5 acceptance.

The approved [fresh-repository sequence](v5-release-readiness.md#replacement-cutover-and-release-sequence)
replaces the old E/P/R/M archive-repository procedure. The approved parentless
private imports now exist; their new identities do not inherit old acceptance.
Prepare and independently review the three version/documentation PRs, obtain the
coordinated pre-merge review, and human-merge them before later selecting actual
tested new Engine/Studio/KS source commits E/S/K. Engine E must carry the
`pyproject.toml` version bump that triggers generated-app CI; this workflow has
no manual trigger. Capture actual generated compile/standalone results at E
or a verified identical tested merge tree, never another docs-only head.

Candidate record P names the full E/S/K hashes and keeps acceptance pending.
Execute one coordinated acceptance on those clean sources, then record actual
outcomes at R and obtain independent final release review. Pairing/evidence
commits P/R are not the product commits exercised by L5. Run L5 from E, with
explicit S/K paths, separate constrained copied environments and strict
required-service flags; its recorded SHAs must match E/S/K. Use the dated
[current-release environment and MCP launch guidance](v5-release-readiness.md#v5-environment-and-mcp-launch).
Only subsequent authorization permits tags on tested E/S/K, followed by public
cutover and separately authorized website launch.

The verifier accepts exactly one complete repository cohort:
`santosh-sh/EdgeForge{,Studio,KnowledgeServer}` for historical selections, or
`edgeforge-suite/EdgeForge{,Studio,KnowledgeServer}` for new selections.
Mixed cohorts, wrong role/name/host, incomplete SHAs and dirty checkouts fail.
An archive descriptor never verifies a fresh-import checkout merely because
its files match; remote identity and full commit must match too.

The descriptor uses `status: candidate` and `acceptance_status: pending`.
Record the acceptance decision separately using the existing evidence convention. The eventual Release body or later record identifies P/R by full SHA;
R cannot identify itself. The candidate descriptor embedded in release source
or an eventual tag may predate final selection. After separately authorized
publication, the v5.0.0 Release record will name accepted E/S/K, P/R, validation
and limitations; that record and its URL do not yet exist. Refer to the release record only after publication is separately authorized
and completed.

## Updating the Selection

Change the active record only through a separate, explicit review after maintainers select a new
three-repository set. Do not substitute a newer branch head automatically and do not infer
compatibility from equal version strings.

For a pin refresh:

1. Record full commits for exactly Engine, Studio, and KS.
2. Keep `status: candidate` and `acceptance_status: pending`; record any eventual
   acceptance decision separately rather than changing descriptor status.
3. Run the focused verifier tests and a real preflight against separate clean worktrees.
4. Preserve prior evidence and the historical Suite baseline rather than rewriting them.
5. Record the actual run revisions in the eventual acceptance evidence.

Future M3 work should consume this selection record rather than create another active pin list. A
short Studio README pointer to this Engine-owned operator contract remains a separate Studio PR.
