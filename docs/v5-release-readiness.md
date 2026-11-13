# v5 Source-Release Readiness

**Authority: EF-V5-RELEASE-SCOPE-RESET revision 3, approved by Santosh Hommaradi
on 2026-10-25.** This supersedes conflicting October 6 release gates and the
old E/P/R/M procedure. It authorizes private preparation, not release execution.
**Current release guidance:** the approved private cutover is complete.
Selected-source technical acceptance was independently approved; executed results
are in [the November 10 record](handover-evidence/v5-acceptance-2026-11-10.md).
The earlier EF-V5-RELEASE-PREP-ENGINE-S1 revision 2 authorized version/documentation
preparation. Tags, public exposure and website launch require separate human
authorization; documentation-only successors do not replace accepted E/S/K or P/R.
Broad M2 remains incomplete; historical findings and acceptance pins are unchanged.
The approved **EF-V5-SOURCE-PREP-ENGINE-S1 revision 2** content amendment below
documents three advisory-source future-public-import exclusions, not findings clearance.
The approved EF-V5-PUBLIC-CONTENT-ENGINE-S1 cleanup additionally replaces external
example/fixture content and publishes neutral historical summaries; see the
[content and coverage record](public-content-preparation.md). These tracked-tree
edits are distinct from import-time exclusions and do not publish old history.

## Decisions and lanes

v5 distributes tested Engine, Studio and Knowledge Server **source repositories
and tags**, with an informational website. No official binary/package/container
distribution, hosted product service or production certification is selected.
One public core is maintained; adopters may keep private configuration,
extensions and downstream modifications. No duplicate enterprise edition is
required. Manifest 2.0 and standalone generated-app contracts are unchanged.

The [project-intent statement](../README.md#project-intent-and-community) applies
across the Suite. The maintainer's choice not to monetize adds no restriction to
Apache-2.0 or commercial use by adopters. Enterprise adoption guidance describes
the adopter's own implementation, confidential-data handling, deployment and
internal support responsibilities; it does not offer those services from the
maintainer. Docker recipes are for self-managed builds. Sharing without charge
does not satisfy ownership, confidentiality or other applicable obligations.

Apache-2.0, a short [NOTICE](../NOTICE), DCO 1.1 sign-off without a CLA, and
copyright Santosh Hommaradi are selected.
**Maintainer publication authorization is required before
all public exposure, including previews; private preparation is separately authorized.** Keep
non-public correspondence and planning material private.
The choice of license does not itself prove authority to publish. The maintainer
must verify the applicable rights and permissions before authorizing exposure;
supporting non-public records remain private.

**Wording clarification (2026-11-05):** public preparation documents use
maintainer publication authorization for G1. This editorial change does not
satisfy or waive any prerequisite, accept risk or authorize publication.
Enterprise adoption remains optional and self-managed; the project continues
to be independently maintained with community contributions welcome.

The three product repositories are: `edgeforge-suite/EdgeForge`,
`edgeforge-suite/EdgeForgeStudio` and `edgeforge-suite/EdgeForgeKnowledgeServer`.
Their approved parentless initial imports and repository controls were verified
and independently approved. Release preparation now belongs in these repositories.
The original `santosh-sh` repositories remain private pre-v5 archives.
`edgeforge-suite/website` is a separate lane; product-import completion asserts
no website creation, deployment or launch.
Do not import their history, PRs, issues, Actions logs or private working files;
do not rename, delete, scrub or expose those repositories.

| Lane | Required outcome |
|---|---|
| Private preparation | Complete version/release-documentation PRs in the three new private repositories, with ordinary required checks and independent review, then human merge. Maintainer publication authorization and reporting-route verification are required for public exposure, not private preparation. The three lanes may proceed in parallel. Engine alone owns the canonical Suite roadmap/tracker. |
| Coordinated release selection | Actual new-repository source commits, strict clean pairing, required repo/build checks, fresh strict audits, selected Studio-image build/run, full L5 with required services and no skipped-success, newcomer journey, focused security QA and one independent final release review. Green CI or matching pins is not acceptance. |
| Public exposure | Maintainer publication authorization, reviewed intended trees and attribution, verified email route, verified tags/targets and human authorization. Enable/verify PVR immediately on public cutover before announcing launch. |
| Website hosting | Protected Cloudflare previews before launch; production only after acceptance and human authorization. Verify the bounded hosting controls below. No live Studio/KS/Engine/demo/generated-app service is authorized. |

<a id="recommended-narrow-m2-completion-contract"></a>

## Source-release known limitations and M2

The prior requirement to complete every M2 investigation before external
baseline/publication is **superseded for this source release**. No new Ubuntu
or Jackson investigation, exhaustive residual closure, signing infrastructure,
evidence generator, ledger or archive campaign is a prerequisite. This changes
release gating, not vulnerability facts, technical dispositions or production
risk acceptance. Source/tag identities, hashes and repeatable existing evidence
remain required; annotated tags are not cryptographic signatures. Expanded
binary/image distribution needs a new artifact-specific contract.

The maintainer approves the existing Engine #335/#336 and Studio #318/#319
findings as **referenced source-release known limitations**, not fixed or safe
components. Accountable owner: **Santosh Hommaradi**, with the relevant repository
maintainers. Review triggers: relevant upstream fixes/advisories, affected
dependency/recipe changes, next release selection, or a proposed production pilot.
New findings require triage; they do not automatically inherit this disposition.

| Retained record | What remains and where to find exact identities |
|---|---|
| Engine #335 | [Closeout decision record](handover-evidence/engine-m2-closeout-decisions.md) and [identity mapping](handover-evidence/engine-m2-dispositions.json): 622 October 20 image records / 22,740 observations, 2,186 historical records / 64,720 observations / 3,990 copies, dated Maven/vendor mappings, Jackson conflict, OS/build/runtime/native/feed gaps. Counts are not unique exploitable-vulnerability counts. |
| Engine #336 | [Clean-plugin overlay](handover-evidence/clean-plugin-plexus-2026-10-24/README.md) proves four new builders and clean-plugin-owned 4.0.3, not a rebuild of thirty historical images. [Python correction](handover-evidence/python-audit-correction-2026-10-25.json) records the fresh 76-package audit. Neither clears other image findings. |
| Studio #318/#319 | [#318](https://github.com/santosh-sh/EdgeForgeStudio/pull/318) and [#319](https://github.com/santosh-sh/EdgeForgeStudio/pull/319) retain Studio-owned image/pip-private/OS/native/JDK/stage findings and coverage limits. Preserve their actual evidence identities; final selected-pair image proof remains required. These archive links are not a claim of public access or current acceptance. |

Keep historical OPEN statuses, source disagreements and physical-copy scope.
“No fix,” severity, build-only scope and scanner silence are not non-applicability
or acceptance. Continue M2 under the existing accountable records after v5;
do not claim broad M2 completion. Existing Python audits, per-app Maven SBOM
delivery, pinned base/refresh controls and strict assessment error handling are
reused, not replaced. Preserve the distinction between complete-with-findings
and incomplete/error. Do not change historical ledgers to implement this policy.

A remaining finding blocks when it establishes a defect in shipped code/recipes,
a failed required check, unsafe/private/untrue public content or claims, or a
missing necessary release decision. Disclosure never repairs such a blocker.

A11y-01 stays **open and Studio-owned**: one failed native save observation and
three untested cases; all four exact-spoken-outcome native observations are still
required for closeout. Carry an audience-accessible notice, including impact and
reproduction summary, while [Studio issue #302](https://github.com/santosh-sh/EdgeForgeStudio/issues/302)
is private. It is not a universal tag/publication/demo blocker and is not passed.
Gateway method/path exposure approval and adopter-owned business/object/tenant/row
authorization remain mandatory supported-deployment boundaries.

<a id="proposed-release-sequence-and-record-identity"></a>

## Replacement cutover and release sequence

**Completed private prerequisite:** the approved tracked-tree projections were
imported as one parentless initial commit per product repository. Exactly the
three Engine advisory files below were omitted. Private source/tree/import
correspondence and independent verification remain in the sealed cutover record;
old history was not imported. Branch protection, required checks, gitleaks and
read-only default Actions permissions were verified. Private controls must remain
supported by the selected organization plan. Email receipt and replies must be
tested before public exposure. Enable and verify PVR at public cutover, including
its reporter-facing route, before Release publication or announcement.
No re-import or repository-settings change is part of release preparation.

Steps 1–5 describe the completed v5 preparation/acceptance ordering; reuse the
recorded proof. Documentation-only main successors do not repeat those steps or
become tag targets. Later operators still verify drift and required approvals.

1. **Prepare and human-merge the three release PRs.** Set versions, changelogs
   and active release/setup guidance in the new private repositories. Complete
   ordinary applicable CI and independent lane reviews, then the coordinated
   pre-merge review and human merge decisions. Keep the three product lanes
   parallel. No acceptance, tags or public exposure is authorized by preparation.
2. **Select tested source commits E/S/K.** Select actual new-repository
   source commits after the preparation merges. Capture exact-source required
   checks, including Engine **generated-app compile/standalone proof**. Engine E
   must carry the `pyproject.toml` version bump: both generated-app path filters
   include it, and the workflow has no manual trigger. Do not nominate a later
   docs-only head and reuse another head's run. A merge commit qualifies only
   with checks at that source or a verified identical tested tree. Version inputs
   also ensure the Python suite and strict audit execute rather than docs-only skip.
3. **Record candidate P.** In a separate candidate-record commit, select
   full E/S/K hashes and the complete `edgeforge-suite` repository cohort.
   Keep `status: candidate` and `acceptance_status: pending`. Descriptor updates
   belong at authorized P; preserve the historical v4 baseline.
   P names prior source commits; it cannot select itself as Engine E.
4. **Execute one coordinated acceptance on E/S/K.** Run the [pairing verifier](suite-release-pairing.md)
   from a recorded tool checkout against clean E/S/K. Run L5 **from E**, with
   `EDGEFORGE_STUDIO_REPO` and `EDGEFORGE_KS_REPO` selecting S/K and the pinned,
   copied, constrained interpreters described in the current-release note below.
   Use `python scripts/smoke/l5_orchestrator.py --require-sibling-repos --require-services`;
   never `--allow-skipped-success`. Recorded Engine/Studio/KS manifest SHAs must
   match E/S/K. Complete the newcomer journey, fresh strict audits, selected
   Studio-image build/run and existing focused security QA. Keep the five agreed
   release-QA clarifications within their existing tasks, not new workstreams.
   Retain the bounded Studio-to-Engine adversarial proof and its nested-input/
   concurrent-writer limitations; full M3 automation remains separate.
5. **Record results R and obtain independent release review.** Commit
   sanitized acceptance records with actual outcomes and limitations. Review all E-to-P/R changes;
   behavior-affecting changes require reselection and affected proof. An R record
   cannot contain its own full SHA: the later Release body or subsequent record
   names P/R. The independent final release review covers actual tested identities,
   later evidence and limitations. An older descriptor embedded in E is not the
   accepted selection. The candidate descriptor embedded in release source or
   a tag may predate final selection. Any separately authorized v5.0.0 Release
   must identify accepted E/S/K, P/R, validation and limitations. Use verified
   publication records for actual Release URLs.
6. **Verify tags under subsequent human authorization.** Immediately before tagging,
   check current advisories for the unchanged selected inventories; reuse qualifying
   same-input results rather than duplicate campaigns. Triage new findings;
   required audits must pass. Create/verify annotated v5 tags only on the
   actual accepted source commits E/S/K, never P/R, and verify package/version
   agreement. No historical/fake tags to silence CI, no automatic tag moves/deletions.
   The no-tag bootstrap applies **only** to `edgeforge-suite/EdgeForge`; package
   agreement is always checked. Once any tags exist, the normal newest-tag check
   applies (main push mismatch fails; PR mismatch warns). The original archive
   repository does not receive a no-tag exemption.
7. **Human-directed public flip and launch.** Only after maintainer publication authorization,
   email verification, full intended-tree approval, final review/acceptance and
   exact-target checks, make the new repositories public; enable/verify PVR
   before launch announcement. Deploy the accepted informational website only
   under separate authorization. Original private repositories remain archives;
   no old PR/history publication.

Tested source commits, later pairing/evidence commits, import commits and merge
commits are different identities. No later record SHA substitutes for a tested
source SHA. This preparation authorizes none of the later release operations above.

<a id="v5-environment-and-mcp-launch"></a>

### Current-release environment and Engine MCP launch verification — 2026-11-07

This dated procedure explains the retained acceptance provenance. Actual executed
results are in the [November 10 record](handover-evidence/v5-acceptance-2026-11-10.md);
this documentation refresh does not rerun or relabel them.

The July [L5 record](handover-evidence/l5-acceptance-run.md#reproduce) remains
historical proof at its recorded pins. Later v5 acceptance uses separate clean
E/S/K checkouts, each with its own constrained Python 3.11 `.venv` created using
`python3.11 -m venv --copies .venv`. Do not overwrite active environments or
combine the three dependency graphs. From E, install with
`.venv/bin/python -m pip install -c requirements-lock.txt -r requirements.txt`,
then `.venv/bin/python -m pip check`; S/K use their own selected constraints.
No system-site packages, inherited `PYTHONHOME`, uncontrolled `PYTHONPATH` or
global dependency fallback qualifies.

Before that acceptance run, resolve `E/.venv/bin/python` exactly as
`_engine_mcp_python()` in `scripts/smoke/l5_orchestrator.py` does. Probe that
exact executable: it must remain inside E's `.venv`, with `sys.prefix` equal to
that environment and different from `sys.base_prefix`. Record requested/resolved
paths, executable hash/version, `pyvenv.cfg`, lock identity, installed inventory
and pip-check results for each environment. Setting `ENGINE_PYTHON` alone does
not control the Studio-to-Engine MCP child.

During later acceptance, use the approved private acceptance plan's unchanged,
invocation-scoped parent-spawn observer outside the checkouts. Before L5, require
startup parity with and without observation for the actual installed environments
and base interpreter, including loaded `sitecustomize` file/spec origin and path/
prefix fields. Require copied-path success and base/symlink, async, cached-module
and unrelated-launch controls. Missing or indistinguishable evidence stops before
L5. On macOS, a process-list sample alone cannot distinguish framework re-execs.

Bind Studio-parent Engine MCP spawn requests to the L5 PID/time window; each
requested executable and argv0 must match the preflighted copied Engine path.
Observe wrong paths too, rather than filtering them out. Prefix probes are
preflight, parent audit events establish requested launches, and successful MCP/
L5 results establish completion; correlate all three. Missing records, a base
interpreter request, startup mismatch or observer failure leaves acceptance
incomplete. This preparation neither implements, changes nor executes that
observer, harness or acceptance plan, and does not relabel earlier L5 results.

## Public-import exclusions and historical replay

**Approved 2026-10-25, source-preparation revision 2.** Exclude only the three
full repository-advisory responses below because their redistribution basis
remains unresolved. This is not a conclusion that redistribution is unlawful,
vulnerability clearance or accepted risk. Do not copy their prose into replacement
records. Preserve all 33 vendor identities, 18 historical mappings, conclusions,
OPEN limitations, historical indexes/checksums and original evidence unchanged.

These exclusions remove three source files, not all overlapping advisory text.
Some of the same text remains in GitHub Advisory Database-derived OSV records
under the source-specific CC-BY-4.0 basis documented in
[third-party attribution](third-party-attribution.md#github-advisory-database).
The maintainer explicitly approved retention of the identified permitted copies
on 2026-11-06. The completed private import preserved them and the dated ownership
note/protective ignore patterns unchanged. This is not blanket permission for
other feeds, vulnerability acceptance or full intended-tree publication approval.

All three originals were introduced at private source revision
`d7f8379374c3757a9cc1aa7fd2febe22ac7fa2e9` and are byte-identical at preparation
base `d148ca50722a676359ec7c7296561f79f99e2b69`. Hashes below are the existing
original compressed/uncompressed SHA-256 values, **not hashes of abbreviated
content**. The unchanged historical `SHA256SUMS` and
`vendor-sources/retrieval-index.json` under the October 5 policy directory
describe the original inputs.

| Exact excluded repository path | Original gzip SHA-256 / decompressed SHA-256 | Original upstream reference |
|---|---|---|
| `docs/handover-evidence/maven-policy-2026-10-05/vendor-sources/lz4-advisories.json.gz` | `6060d838eff8dc392fd6fc8d0b009cc3dd5e2668deca845998ff58281a7fe3f0` / `f48d5c1919e297200f8a2e220d7a54af7d0d3288a45973a3d7ba542f2d91a457` | [yawkat/lz4-java repository advisories](https://api.github.com/repos/yawkat/lz4-java/security-advisories?per_page=100), 7 retained responses |
| `docs/handover-evidence/maven-policy-2026-10-05/vendor-sources/jackson-core-advisories.json.gz` | `52614644a0287673531a6614d4038bfdb748960f6a9a86f901a71b481dbbefff` / `8f623346378d9418970fb085ecf12fbac44268fbb09da0804a96cb333a4c9e0f` | [FasterXML/jackson-core repository advisories](https://api.github.com/repos/FasterXML/jackson-core/security-advisories?per_page=100), 9 retained responses |
| `docs/handover-evidence/maven-policy-2026-10-05/vendor-sources/jackson-databind-advisories.json.gz` | `495ad6e742baf2d39a329d50d2de0618f8a606f9ac8d5144287cf055f81f2575` / `f1775652c8b34967a0a4e65527acb48392692877716cfe98244b5495f408b3fe` | [FasterXML/jackson-databind repository advisories](https://api.github.com/repos/FasterXML/jackson-databind/security-advisories?per_page=100), 17 retained responses |

**Private retention:** originals remain in the private development repository
and its existing evidence retention, unchanged and not uploaded/repackaged.
Historical indexes still describe complete private evidence, not public file
availability. Public readers **cannot fully replay this historical assessment
from the public repository alone**. Public CI uses explicitly synthetic sources
for reconciliation logic/negative tests and existing compact records for internal
consistency; that is not full historical replay.

With the complete original private policy directory, an explicitly authorized
offline historical replay is:

```bash
EDGEFORGE_HISTORICAL_MAVEN_POLICY="$ORIGINAL_PRIVATE_POLICY_DIRECTORY" \
  python -m pytest -q tests/unit/test_maven_finding_reconciliation.py
```

Unset means that one opt-in historical test is visibly skipped, never credited
as proof. If requested with missing originals, it fails. The existing
`scripts/reconcile_generated_maven_findings.py` CLI also requires complete
original inputs: a missing source returns `status: incomplete`, exit **2** and
the missing artifact, not clean/success or complete-with-findings. No fallback
to summaries, network download or historical-hash rewrite is performed.
Original sources are not needed for normal product generation/use.

<a id="m6-decision-sheet-pending"></a>

## M6 hosting and contact gates

Canonical website: **https://edgeforgesuite.com**. Redirect
`www.edgeforgesuite.com`, `edgeforgesuite.app` and `edgeforgecontracts.com`
to it. Use the private `edgeforge-suite/website` repository and Cloudflare
Pages, with **Cloudflare Access-protected previews**, including the default
`pages.dev` address; a private repository alone does not protect previews.
Production waits for acceptance/authorization. Hosting is informational only,
not permission to expose product services.

Santosh Hommaradi is the accountable maintainer. Selected routes
`security@edgeforgesuite.com` and `contact@edgeforgesuite.com` require tested
receipt/replies through Cloudflare Email Routing before public flip. PVR is
primary at cutover. No route is claimed operational here; no invented SLA.
Use public documentation and repository issues for ordinary project questions
after activation. The contact mailbox is for project administration, not sales,
custom implementation or managed onboarding; security reports follow the private
route in [SECURITY](../SECURITY.md).
Before hosting, record operator/access, provider logs/retention, telemetry,
TLS/redirect checks, exact website source/artifact, deployment authorization and
tested rollback. No DNS/email/provider configuration is performed by this PR.

## Release QA coverage within existing work

**Adopted clarification, 2026-10-14; retained by scope-reset revision 3.**
Keep these five checks within the existing owners/tasks, not separate goals
or a whole-codebase investigation. Map applicable completed proof first.

| Check | Existing owner/task | Required bounded outcome |
|---|---|---|
| Understandable security responsibilities | Engine endpoint closeout; all-core E1/XR-2 | Gateway TLS, blocked direct port and explicit method/path approval are prominent; authentication and route approval are not object/tenant/row authorization. |
| Visible limitations and accurate claims | E1/XR-2 and website before hosting | Match claims/examples to behavior; retain int32, A11y-01, image/font and pilot boundaries. Disclosure does not replace required fixes. |
| Release and evidence agreement | M2 records, S8/XR-4, final Suite selection | Bind newcomer, generation/image/security proof to actual source/configuration/image identities; label historical reuse. Green CI is not L5 acceptance. |
| Focused adversarial coverage | Existing security regressions, final bounded QA | Cover relevant imported-input, session, generated read/write, regeneration and KS-deletion boundaries. Add checks only for concrete gaps; broader research needs separate scope. |
| Observable quality and claim accuracy | S8/XR-4 and implementation review | Check expected results and failures, false-success paths, swallowed errors, ineffective assertions, broken controls, confusing guidance and stale examples. Size/style/AI authorship alone is not a release blocker. |

The later acceptance record keeps one concise entry per check: source/configuration,
method/commands, results, evidence, reuse applicability and remaining gaps/disposition.
All five entries must be accounted for; prove required fixes and resolve necessary
release decisions alongside required checks and L5, then stop. Preserve dated records.

## Post-v5 work

Keep optional work in the existing [post-v5 backlog](external-review-backlog.md):
M2 residual research/assurance, M3/M4/M5b, XR-3 and bounded refactors remain
separate. No optional improvement automatically starts a new task.
