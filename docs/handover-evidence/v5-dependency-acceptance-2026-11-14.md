# v5 dependency-correction acceptance — 2026-11-14

**Required execution passed; independent exact-head review pending.** This
successor record qualifies the sources below after two transitive dependency
corrections. It preserves the [November 10 acceptance](v5-acceptance-2026-11-10.md)
and its later independent approval as dated evidence for their original inputs.
Applicable final records-head CI and independent review are recorded externally
after this results commit. All three repair PRs remain draft and unmerged.

## Selection and bounded change

| Role | Repository | Selected source | Selected tree |
|---|---|---|---|
| E | `edgeforge-suite/EdgeForge` | `57a59759e968887177e51043a2620ba08bb6858e` | `659a963863af76e022be1c0e0b07aedb39683638` |
| S | `edgeforge-suite/EdgeForgeStudio` | `1c19275d2960640105ca28f9a7e17e247833cc61` | `6aef34334159916a588c0112b8ddb679f8178443` |
| K | `edgeforge-suite/EdgeForgeKnowledgeServer` | `4a6cfae77cb88567f9538f7db09a092ba2f0f47b` | `e1a11c04fce780e7a3ff65c1119416593a28899e` |

Candidate P is `a33a403db2ffcff08c82e4e49a8b779741e840be`, tree
`c3ea0877c4bb8e702e546bc86206ca47ea9b397f`. Its sole
[`suite-release-candidate.json`](../suite-release-candidate.json) has SHA-256
`cea281121a360f577772c04a67b2cf31a29e86295f06cfd3678bd6342cd37dcf`.
The supported descriptor schema remains `1.0`, manifest schema `2.0`, candidate
ID `public-v5-preparation`, target `v5.0.0`, `status: candidate` and
`acceptance_status: pending`. The historical baseline is unchanged.

All three reference graphs change only dnspython `2.9.0` to `2.9.2` and
OpenTelemetry API `1.45.1` to `1.45.2`. Direct dependencies, FastMCP/MCP pins,
product behavior, generators, workflows, package versions and licensing terms
are unchanged. Existing dependency evidence was regenerated with the existing
generators. Engine's November 2 evidence and declarations are preserved in a
fixed historical snapshot, and its one historical correction test reads that
snapshot with every assertion preserved. Studio updates the two literal pin
expectations in its existing audit-policy test. KS changes no test assertions.
Current generated licence metadata and bootstrap/project entries retain their
documented platform and tool-environment qualifications.

Initial Engine and KS source CI exposed stale evidence assertions. The explicitly
authorized evidence correction resolved them; the original failures remain
retained. Successor E/S/K also include the merged contributor and current-guidance
documents. The earlier accepted E/S/K, P `1f90850fac48f119fe39a79b894cabf4ffab9af9`
and R `92d0de224d127525b3b3db1365cf931188ccfffb` retain their original scope.

E is the tested product source; later P and this results commit R are records,
not replacement source or tag targets. R cannot name its own full commit SHA;
the external handoff and review bind its actual identity after committing.

## Executed proof and justified reuse

| Item | Actual result and coverage |
|---|---|
| Pairing | Committed clean P verifies separate clean E/S/K with `pins-match`, exit 0 before and after affected proof. The 44 existing focused pairing tests passed; archive/Org positive, mixed-cohort and dirty-checkout fail-closed coverage is preserved. |
| Exact-source CI | E: 6/6 checks, 4,606 passed, 32 skipped and 29 subtests. Its [generated-app job](https://github.com/edgeforge-suite/EdgeForge/actions/runs/43611433752/job/132497126300) checked out E itself, completed 41/41 steps and executed 14 runtime tests. S: 3/3 checks, 2,523 passed, 45 skipped, 32 deselected and separate L2 passed. K: 5/5 checks, 342 passed and core-only install passed. All final source jobs succeeded on attempt 1. Ordinary unit skips receive no required acceptance credit; Ruff remains advisory. |
| Strict dependency audits | Successful selected-source procedures cover Engine 76, Studio 95 and KS 84 reference packages, with zero findings at their recorded November 14 query times. Current evidence generations and qualifying exact-source CI are reused rather than queried again for timestamps. The selected image's separate complete installed inventory covers 94 packages with zero findings. No suppression, omitted inventory or silent pin change is used. These results are not whole-image clearance or permanent advisory currency. |
| Installed environments and provenance | Separate constrained Python 3.11.15 `--copies` environments and `pip check` passed. Interpreter, prefix, configuration, constraints, installed inventory and startup-file identities are retained and unchanged at continuation. Six startup-parity contexts, six launch controls and the old observer negative control are reused. Five actual Studio-parent Engine launch requests match the copied E interpreter and successful L5 time window/MCP results. Process-list output is not interpreter provenance. |
| Focused affected checks | 45 bounded dependency cases, 8 actual Studio-client stdio metadata cases and 42 live-sibling adversarial handoff tests passed. Engine and KS evidence-focused checks passed 23 and 42 tests respectively. No sibling skip is counted as execution. Wider regressions reuse the exact-source CI and complete L5. |
| Final full L5 | The second authorized execution ran exact E/S/K from E with required sibling/service flags: exit 0, all 6 leaves, 7 hard checks and 8 Studio scenarios passed, no required skips or warnings. The artifact-path scan checked 691 files and found no leak. The manifest agrees with P. Runtime, regeneration, change plan, apply isolation, Studio and KS all executed. |
| Clean selected Studio/Engine image | The second build uses pristine tracked-only contexts at E/S and the unchanged amd64 recipe. Image `sha256:2b616067c2153ea41936cf1528758b9fa2321f503787830d18c4c68bdeb9f57c` has exact packaged source bytes and no copied host caches. ARM64-host emulation is disclosed. Launch: 1 passed, no skips. The same image runs as UID 1000 with no host mounts; in-image generation, separate `mvn -B -ntp clean verify` (1 test, zero failures/errors/skips), packaging and runtime passed. Synthetic Account create/read/missing-ID returned 201/200/404 with persisted fields. Studio's packaging route skips tests; the separate verify result is the executed test proof. No registry upload occurred. |
| Browser and Java reuse | The previously accepted native-Chrome Account journey, developer hook, additive regeneration, preservation, supplied/default fields and Maven evidence retain their original dates and sources. Exact unchanged generator, UI, integration, sample, helper and guide Git objects establish applicability; fresh affected transport, L5 and image proof cover the corrected Python graphs. No new browser, manual keyboard, screen-reader or printing campaign is claimed. |

The final L5 invocation, from E, was:

```bash
EDGEFORGE_STUDIO_REPO="$STUDIO_CHECKOUT" EDGEFORGE_KS_REPO="$KS_CHECKOUT" \
EDGEFORGE_STUDIO_PYTHON="$STUDIO_PYTHON" EDGEFORGE_KS_PYTHON="$KS_PYTHON" \
"$ENGINE_PYTHON" scripts/smoke/l5_orchestrator.py \
  --require-sibling-repos --require-services --keep
```

The unchanged invocation-scoped observer SHA-256 is
`6e01d12456673aba33c03054e9b6e23a05d461ef317e3de3f430806aea128141`.
The final L5 report SHA-256 is
`3d23547882ea73157b5f08ff20afb2bfb66b0e69cb52b8c90a082c83c500fb36`;
the manifest SHA-256 is
`9dcf3e6d144b83f17883d7a8f273d3c83e868acb7fdef5b620eeafd9516da271`.
The compact execution receipt SHA-256 is
`97a981388c65f657fb67b776e1b08bcda4ef80d3850e7df149463fb582ce4a2f`.
Raw logs, manifests, inventories, screenshots, project exports, local paths and
private diagnosis remain in maintainer-retained private evidence, outside Git.

## Preserved unsuccessful attempts and continuation

The first selected image built and launched but was rejected by source comparison:
18 ignored host cache files had entered the build context. Some contained private
task paths. This coordinator build-context error received no clean-image acceptance
credit. The original image, exact mismatch and diagnosis remain retained.

The first L5 was interrupted incomplete after the generated app's Maven proof
and Docker build completed, while its parent remained blocked reading an exited
Docker child's output. A stuck orphan credential helper was also observed; the
precise helper/pipe mechanism remains a hypothesis. There was no final L5 report,
no Studio launch evidence and no L5 acceptance credit for that attempt.

The maintainer explicitly authorized Q2: one additional clean selected image
build, then one additional complete L5. The continuation used a task-only anonymous
Docker client configuration, the same verified engine and unchanged pinned public
base images. Its actual invocation environments and subprocess inheritance are
retained; no credentials or global settings changed. The mitigation is not claimed
as a proven root-cause repair. Previous task outputs and shared aliases were
preserved/restored. Finite limits were recorded before launch and not extended.

Current task totals are selected Studio image builds **2/2** and full L5
executions **2/2**, with one rejected/incomplete attempt and one pass for each.
Affected-job CI retries remain **0**; push-triggered runs at new commits are not
retries. Earlier acceptance (4/4 repairs, 2 L5 runs, 0 transient retries), readiness,
documentation and lane counters remain unchanged. No third attempt or automatic
source, dependency, harness, observer or workflow repair is authorized.

## Limits and remaining decisions

The five existing release-QA entries retain their scope: gateway and business
authorization responsibilities; visible support/refusal boundaries; exact source,
image and evidence agreement; focused adversarial coverage and its limits; and
observable success, refusal and developer-file preservation. This successor adds
no assurance programme or optional cleanup campaign.

All 150 retained tracked logs and the three Engine advisory exclusions are
preserved, with source-specific attribution intact. Known M2 image/native/JDK/pip
limits, A11y-01 and deferred fonts remain. The checks do not establish broad M2,
production, accessibility, whole-image or native ARM64 clearance. Local authoring
snapshots may still contain user paths; the prior export fix removes two provenance
fields, not every possible local path.

Independent exact-head Claude review and applicable final records CI remain
external completion conditions. AI review evidence is not a formal GitHub approval
or maintainer merge decision. Later human merges must preserve tested source
identities and verify resulting content and applicable main CI.

The [release sequence](../v5-release-readiness.md#replacement-cutover-and-release-sequence)
still requires the proportional Stage A amendment, actual-main Stage B approval,
maintainer publication authorization, tested reporting delivery/replies and the
actual reply identity, a final applicable advisory check immediately before
separately authorized exact-target tags, visibility/Release authorization, PVR
and organization-control verification at cutover, public links and a separately
authorized website launch. No merge, tag, Release, publication, upload, settings,
reporting-route or website operation is authorized by this record.
