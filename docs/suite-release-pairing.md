# Suite Release-Candidate Pairing

This document defines the bounded release-pairing foundation for the three core EdgeForge Suite
repositories. The sole active candidate-selection record is
[`suite-release-candidate.json`](suite-release-candidate.json). It selects revisions for coordinated
release preparation; it does not recommend installation and does not establish integration,
security, or release acceptance.

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

The preserved pre-cutover preparation snapshot has candidate ID `public-v5-preparation`, targets `v5.0.0`, and
keeps `acceptance_status` set to `pending`. It selects manifest schema `2.0` and these exact commits:

| Role | Repository | Selected commit |
|---|---|---|
| Engine | `santosh-sh/EdgeForge` | `e39d415c3f3401247894ca38b7961db769fe637b` |
| Studio | `santosh-sh/EdgeForgeStudio` | `d23d99f480e242291750724d192875e53b37e85f` |
| KS | `santosh-sh/EdgeForgeKnowledgeServer` | `51bbff05f36c85c65a37694006e46e8eb3c21bf9` |

The record contains no branch names, version ranges, credentials, or checkout paths. Studio
dependency remediation and the other public-v5 release gates remain pending independently.

## Preflight Usage

Prepare three separate clean worktrees at the selected commits, then run:

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
replaces the old E/P/R/M archive-repository procedure. Frozen reviewed trees
will be imported into new private repositories; these new commits have new
identities. After release source checks, select actual new Engine/Studio/KS
source commits E/S/K. Pairing/evidence records P/R come later and are not
themselves the product commits exercised by L5. Run L5 from E, with explicit
S/K paths and strict required-service flags; its recorded SHAs must match E/S/K.

The verifier accepts exactly one complete repository cohort:
`santosh-sh/EdgeForge{,Studio,KnowledgeServer}` for historical selections, or
`edgeforge-suite/EdgeForge{,Studio,KnowledgeServer}` for new selections.
Mixed cohorts, wrong role/name/host, incomplete SHAs and dirty checkouts fail.
An archive descriptor never verifies a fresh-import checkout merely because
its files match; remote identity and full commit must match too.

The existing descriptor remains unchanged and pending. Only separately
authorized release selection can replace it with actual new-repository SHAs.
The accepted-release decision is a separate record, not a new descriptor
status. The eventual Release body or later record identifies P/R by full SHA;
R cannot identify itself. Tagged README guidance must direct readers to the
later accepted record, not imply that an embedded older descriptor is current.
This preparation does not authorize import, pin refresh, tags or publication.

## Updating the Selection

Change the active record only through a separate, explicit review after maintainers select a new
three-repository set. Do not substitute a newer branch head automatically and do not infer
compatibility from equal version strings.

For a pin refresh:

1. Record full commits for exactly Engine, Studio, and KS.
2. Keep the candidate and acceptance status pending until the required proof completes.
3. Run the focused verifier tests and a real preflight against separate clean worktrees.
4. Preserve prior evidence and the historical Suite baseline rather than rewriting them.
5. Record the actual run revisions in the eventual acceptance evidence.

Future M3 work should consume this selection record rather than create another active pin list. A
short Studio README pointer to this Engine-owned operator contract remains a separate Studio PR.
