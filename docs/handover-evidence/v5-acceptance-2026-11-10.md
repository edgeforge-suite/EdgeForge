# Coordinated v5 technical acceptance — 2026-11-10

**Execution passed; independent final release review pending.** This record covers
the selected sources below. It establishes neither publication authorization nor
broad M2 completion. Engine and Studio PR #3 remain draft and unmerged.

## Selection and lineage

| Role | Repository | Selected commit | Selected tree |
|---|---|---|---|
| E | `edgeforge-suite/EdgeForge` | `fe0aa4dc565bae3be3b003bfcc3f473d251cd7fd` | `8e6a0643e45ac8a238bc3ff7ca3234c3629a4ca5` |
| S | `edgeforge-suite/EdgeForgeStudio` | `854d51c8dea36ecb9d8e130e7161b8b7615d2435` | `ecd9f2d7a1c5a4e4c892e60f1dd41321243322e6` |
| K | `edgeforge-suite/EdgeForgeKnowledgeServer` | `6fb5be6efd82e93ca735595e9e7b37dfb5f36418` | `0d66a85dde92682f748eac26f979a02c692ea9a9` |

The active candidate P is `1f90850fac48f119fe39a79b894cabf4ffab9af9`. Its
[`suite-release-candidate.json`](../suite-release-candidate.json) SHA-256 is
`222d8b7a7135dde63ef84cffc41ca9b47719ebc2b944470ace74a67cdbe4fe39`. It keeps candidate ID `public-v5-preparation`,
target `v5.0.0`, manifest schema `2.0`, `status: candidate` and
`acceptance_status: pending`. The historical baseline is unchanged.

The original frozen E/S were `c52dd93b5c33b74f6ead06e15490415740874716` and
`b412050531f18813354df0406e41d4fed0ce9f86`; K is unchanged. Initial candidate
`0ea1df6c0c720e9473a049e8d98188bda48edc40` and successor `1f151a6b84cdb5a214aae708a8c8ae1762ea091d` are preserved. The latter
selected Studio's required-request-body fixture correction at
`c224af844bcc6a5dbfc347d3bfe520ec54f2fbae`.

The maintainer authorized a fourth bounded repair cycle and exactly one full L5
rerun. E now aligns the regeneration harness's Flyway Maven plugin with the
generated application's resolved Flyway version, failing closed on unresolved
output. Its workflow path filter covers that harness, allowing actual generated-app
CI at E. S also removes local generated-export provenance paths from portable
snapshots and isolates smoke-scenario rate-limit history. Limits remain enforced
within each scenario. No dependency pins or Engine generator behavior changed.
Both selections include the previously reviewed contributor documentation.

E is an earlier, separately tested commit on Engine PR #3. P and this later
results commit R remain distinct from E and from future tag targets. R's actual
commit identity and final records-head CI are recorded externally after commit;
this document cannot name its own commit SHA. Current main and PR #2 merge commits
are documentation successors, not automatic source replacements.

## Execution and evidence

All required execution items passed or have explicitly scoped reuse. The initial
failed L5, diagnoses, earlier browser driver failure and all prior records are
retained. Passing evidence was not rewritten as a fresh run.

| Item | Method and actual result |
|---|---|
| Pairing | Clean P verifier against separate E/S/K, `pins-match`, exit 0 before and after acceptance; 44 focused pairing tests passed. Archive/Org positives and mixed-cohort/dirty fail-closed cases remain. |
| Exact-source CI | E: all 6 checks passed, 4,605 Python tests passed, 32 skipped, 29 subtests passed. [Generated-app run](https://github.com/edgeforge-suite/EdgeForge/actions/runs/42924847729/job/130208602338): checkout E itself, same selected tree, 41/41 successful steps and 14 runtime tests; six source/job-bound receipts retained. S: 3/3 checks, 2,523 passed, 45 skipped, 32 deselected, separate L2 passed. K: reused unchanged exact-source 5/5 CI, 342 passed, core-only install passed. All source runs succeeded on attempt 1. Ordinary unit skips receive no required acceptance credit. |
| Fresh strict audits | Engine existing lock procedure: 76 packages, 0 findings. Studio pinned strict audit: full selected constraints, no known vulnerabilities found. KS pinned strict audit: 84 packages, 0 findings; selected installed inventory independently verified in Linux. Audit queries were fresh on 2026-11-10 UTC; inputs and timestamps retained. Native macOS omits Linux-only packages, so the Linux inventory proof is separately identified. |
| Environment and observer | Separate constrained Python 3.11.15 `--copies` environments, explicit E interpreter, inventories and `pip check` passed. Actual resolved executable/prefix/lock/configuration hashes retained. Six startup-parity contexts preserved vendor startup file/spec identity. Copied, base, resolved-symlink, async, cached-module and unrelated launch controls passed; old observer retained as negative control. Five matching Studio-parent Engine spawn requests were bound to the successful L5 PID/time window and MCP results. These are observed requests plus runtime completion, not process-list claims. |
| Full L5 | From E with explicit selected siblings/interpreters and `--require-sibling-repos --require-services --keep`: exit 0; all 6 leaves passed, all 7 printed hard checks passed, all 8 Studio scenarios passed, no warnings or skipped-success. Manifest SHAs match E/S/K. Engine runtime, regeneration, change plan, apply isolation, Studio and KS all executed. |
| Newcomer browser | Actual headless native Chrome, KA OFF, explicit `springboot-legacy-compatible`, maintained synthetic Account. Earlier initial/hook/additive browser proof retains its original source bindings: author/open, validate, generate, build/run, create/read/missing-ID, developer hook, additive preview/approve/apply and preservation passed. Each initial/hook/post-apply `mvn -B -ntp clean verify` executed 1 test, no failures/errors/skips. Supplied nickname and omitted-field `UNNAMED` default survived rebuilt runtime. Exact generator, UI, integration and guide objects are unchanged and justify this reuse. Fresh selected E/S browser export/validate/download verified cleared generated-export paths, retained revision identities and unchanged ordinary Save Project semantics. |
| Selected Studio/Engine image | New exact-source `linux/amd64` image `sha256:f2962951efcd455c48ecee333fdfaf814edb3b09dcd030a5a1444226a90c4cee`; ARM64 host emulation disclosed. Packaged E/S source hashes match. Prebuilt-image launch test: 1 passed, no skips. Same image's strict local-MCP generation/build/run proof: non-root `appuser`, no host source mounts, generated Maven verify 1 test, no failures/errors/skips; create 201, read 200, missing ID 404 with persisted supplied fields. The helper's packaging command skips tests; the separate retained verify command actually ran them. No registry upload. |
| Focused repairs/security | Engine focused unit checks 13 passed and real PostgreSQL additive regeneration passed. Studio focused unit checks 128 passed; all 8 focused smoke scenarios passed. The limiter test proves six exports succeed and the seventh is refused in each separate scenario. Selected-source live adversarial handoff: 42 passed, Engine/KS cases executed. Wider regressions reuse source CI and strict L5. |

The acceptance L5 command, from E, was:

```bash
EDGEFORGE_STUDIO_REPO="$STUDIO_CHECKOUT" EDGEFORGE_KS_REPO="$KS_CHECKOUT" \
EDGEFORGE_STUDIO_PYTHON="$STUDIO_PYTHON" EDGEFORGE_KS_PYTHON="$KS_PYTHON" \
"$ENGINE_PYTHON" scripts/smoke/l5_orchestrator.py \
  --require-sibling-repos --require-services --keep
```

The unchanged approved observer was scoped to that invocation. Its SHA-256 is
`6e01d12456673aba33c03054e9b6e23a05d461ef317e3de3f430806aea128141`.
Raw manifests, logs, screenshots, project snapshots, inventories, image identities,
commands and reports remain in maintainer-retained private evidence, not Git.
The compact execution receipt SHA-256 is `a5d9622fe8a0a4f0882e3d6e15fbb6a643a60786f99a46ece617c00d9fd961ef`. Its evidence hashes bind
the specific proof and justified reuse above; it does not contain R's later identity.

## Five existing release-QA entries

| Entry | Evidence and disposition |
|---|---|
| Security responsibilities | Selected security guidance and generated README retain gateway TLS, blocked direct ports and approved methods/routes. Authentication/route approval is not object/tenant/row authorization. Loopback proofs do not operate adopter infrastructure. |
| Visible boundaries | Newcomer guide, current README and readiness guidance retain support/refusal, generic CRUD, int32, pre-v5 app, pilot, A11y-01 and font/image limits. Generation is distinct from business logic. Website review remains separate. |
| Source/image/evidence agreement | Exact source trees, candidate hash, L5 manifest, installed environments, image packaged-source hashes and browser reuse comparison agree. P/R and PR #2 documents are distinguished from tested product sources. |
| Focused adversarial coverage | Live handoff checks, selected CI and all required L5 isolation/refusal leaves passed. Nested input, concurrent writer, KS deletion/atomic retry and wider security limits retain their existing scope; this is no broad security audit. |
| Observable success/failure | Browser and runtime receipts record validation, stale/destructive refusal, approved additive apply, developer-file preservation and actual supplied/default responses. No optional cosmetic or quality campaign was added. |

## Limits, counters and remaining gates

Repair cycles: **4/4 used**, including the two explicitly authorized additional
cycles; no allowance reset. Full L5 executions: **2** (initial failed run plus
one authorized successful rerun). Transient retries: **0**. Final Claude reviews:
**0**, with one initial review and at most two focused re-review rounds available.
Historical lane repair counters remain Engine 1/2, Studio 0/2, KS 0/2, with
affected-job CI retries 0/1 each; these are distinct from this acceptance goal.

Independent final review and applicable final records-head CI must be confirmed
externally before maintainer merge review. Recorded AI review evidence is not a
formal GitHub approval or the maintainer's merge decision.

Known M2 image/native/JDK/pip limitations remain open; Python audit success is not
whole-image clearance. A11y-01 remains open (one failed native observation and
three untested cases); fonts remain deferred. Headless Chrome does not establish
manual keyboard, screen-reader or printing clearance. No native ARM64 support,
production database upgrade, business authorization or broader production pilot
is proved. Local authoring snapshots and uploaded/authored content retain their
documented privacy limits; only generated export-provenance paths were corrected.
The three advisory exclusions and source-specific attribution are preserved.

The [approved release sequence](../v5-release-readiness.md#replacement-cutover-and-release-sequence)
still requires independent release review, maintainer merge/publication decisions,
tested reporting/contact/security routes and replies, full intended-tree approval,
and PVR verification at public cutover. The last applicable advisory check remains
immediately before separately authorized tags on tested E/S/K. No tags, Releases,
package/image uploads, visibility/settings changes, website deployment or public
announcement is authorized or performed here.
