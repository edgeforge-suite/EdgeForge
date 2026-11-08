# M5a Original-Date Integrity And Proof Safeguard

Approved slice: EF-V5-ENGINE-M5A-321-322 revision 1. Base:
`5793cb2f8779322ce13c5e758806b54e5e9d835a`. Addresses
[#321](https://github.com/santosh-sh/EdgeForge/issues/321) and
[#322](https://github.com/santosh-sh/EdgeForge/issues/322); independent review,
human merge, default switching and M2 are separate. Historical evidence is unchanged.

## Tested Revisions

First implementation commit `9b0d168f916fc28c6cfc741304ff88aa88dacacd` added
explicit `sys.flags.optimize` refusal before Batch proof imports/side effects.
Before new product proof, Python 3.11 ran **59 passing tests**: 40 negative
subprocess combinations (four modules, module/import use, `-O`, `-OO`, effective
`PYTHONOPTIMIZE=1/2/7`), three valid unoptimized settings, one guard-source check
and 15 existing durability tests. An exact-commit reproduction also passes 59;
the current early-crash helper expands negative combinations to 50.

Product decision commit: `e2df8cbe5e9e452c95abace4a37b9b7b7550a4f2`.
Clean compiled matrix revision: `8272556d0616442cc57217a636c40e9735bb3811`.
Subsequent documentation/evidence edits do not change that tested code.
The later conditional helper-type qualification at
`777816b73678449e04aeba83e1b1407e286466f1` preserves every Widget package byte
on all six profiles, explicitly compared to the matrix revision. It fixes a new
valid-domain `HashSet` compile regression against the exact base without replacing
decision code; framework types are selected explicitly, never globally rewritten.
Full normal Python after that repair: **1846 passed, 25 skipped**
(optional integration tests; the required matrix below
executes independently). Focused generator/identity/idempotency/helper tests:
**209 passed**. Final-head CI runs the full applicable workflow, not a package-only check.
Expanded domain-name proof at clean `6b2ff90f57fc6e4c5cab871c00e6299395bbd3a1`:
**eight builds, eight executed app tests, zero failures/errors/skips**, covering
ordinary/M5a `JobLauncher`/`JobExplorer` plus the new runnable helper collisions
on both lines. Receipt SHA-256:
`80511510fad5fddc6ecd7913d6cb7e3019e570740e5ecbf05222dca63b23843d`.

Repair round 1 addresses initial independent finding R0-1: schema-valid domain
`RuntimeException` shadowed the new history-read catch on both lines. Commit
`31412f72572f6905db1eaa6f800329277cd7c0f3` selects `java.lang.RuntimeException`
only for that collision, preserving domain references and all six tested Widget
package trees. **211 focused / 1848 full Python passed, 25 optional skips**;
**10 compiled name builds / 10 executed app tests**, zero failures/errors/skips.
Name receipt SHA: `84aecb8fea61584f916e8c587cf1ac1f0bf78b7c3bb3c9ed3312db811717de40`.
Its dirty flag records only the concurrent packaging test's untracked egg-info,
retained outside Git; no tracked source differed from the named commit.
Final-head CI and fresh independent re-review remain separately required. Prior
CI Kafka total is **12 builds / 90 tests** (84 mixed + 6 standalone), not the mixed
subtotal alone. Prior artifacts and the independent finding remain unchanged.

## Compiled Execution

| Product | Database / JDK | Product tests | Disposable seam tests | Early run ID |
|---|---|---:|---:|---|
| Boot 3.3.5 / Batch 5.1.2 | PostgreSQL / 17 | 35 | 35 | `early-f3cc9504df41` |
| Boot 4.1.1 / Batch 6.0.5 | PostgreSQL / 17 | 35 | 35 | `early-6d9b9b4f833e` |
| Boot 3.3.5 / Batch 5.1.2 | PostgreSQL / 21 | 35 | 35 | `early-601be5fd9bb0` |
| Boot 4.1.1 / Batch 6.0.5 | PostgreSQL / 21 | 35 | 35 | `early-7572a93d3ad8` |
| Boot 3.3.5 / Batch 5.1.2 | H2 / 17 | 35 | - | same-process only |
| Boot 4.1.1 / Batch 6.0.5 | H2 / 17 | 35 | - | same-process only |

**10 builds, 350 executed tests, zero failures/errors/skips.** Each PostgreSQL
case observes typed original parameters, an absent frozen context, exactly its
STARTED identity step and no staging rows before killing the coordinated owner.
Owner death and unchanged history are checked before test-only classification.
Unclassified replacement refuses both dates. Each case retains **two crashes,
four changed-date failures and seven executions in one instance**, then completes
the original date `2026-09-27`. Earlier executions remain byte-identical; rejected
dates `2026-09-28/29` neither rebind authority nor poison original-date retry.
Existing post-commit crash, FAILED/STOPPED, completed/running/concurrency,
source immutability, upsert, Flyway and one-instance invariants also execute.

Each build includes 21 synthetic malformed/missing/conflicting history controls,
shuffled/tied/reversed timestamp history, read-failure and actual tasklet date
rejection tests. Six actual HTTP/JDBC corruption controls retain original
parameter/context records without repair; hydration failure may return 500,
otherwise the identity step reports FAILED before staging. Unchanged exact-base
generated decision code fails the changed-retry counterexample on **both** lines
(one expected assertion failure per line), while corrected code passes.

## Evidence And Reproduction

Retained outside Git in the task-owned proof directory; the independent-review
delivery packet supplies exact local locations and final-head CI/artifact links.
The machine receipt records input tree, product source/JAR, test fixtures,
disposable source/JAR and seam diff SHA-256 identities and full raw histories.
Receipt SHA-256: `2f169c7071ceaff61a34da49a82c61a0cd3b385f28a91c1ead317b186cbaa965`.
Input tree SHA-256: `0370aabfb24460e55ba6f98f68388e245d84ee668c432760d65f7e31323e0011`.
Exact-base old-behavior receipt SHA-256:
`dfe8ba720da3dafa4de025e762694b7ea7523d16330adba274e23a87d079897e`.
Unchanged 27-case default preservation receipt SHA-256:
`1f956149c30e8b0e27b2740a299ee6aa53e625d626da806cfdc358e3d781289a`.
Six opted-in M5a/mixed preservation cases additionally compare against the exact
base and allow only the named M5a job Java file to differ; migration bytes and all
other artifacts are exact, not a broad Java exemption.

Use Python 3.11, public Maven resolution, both JDKs and a **task-owned disposable**
PostgreSQL service with the explicit variables in the preview guide:

```bash
python -m scripts.smoke.boot41_batch_preview_proof --mode full --case m5a \
  --java17-home "$JAVA17_HOME" --java21-home "$JAVA21_HOME" \
  --work-dir "$PROOF_OUTPUT/new-m5a-proof"
python -m scripts.smoke.boot41_kafka_preservation \
  --base-revision 5793cb2f8779322ce13c5e758806b54e5e9d835a \
  --work-dir "$PROOF_OUTPUT/new-preservation-proof"
```

CI omits `--case` and executes ordinary/file/mixed cases too. The disposable seam
does not replace decision code and is never shipped. History authority relies on
retained untampered records; no schema, migration, dependency, identifying-date,
automatic recovery/repair, adopter-database or general business-data recovery
claim is introduced. Failed observations are retained: primitive-ID compilation,
Batch 6 name-only parameter equality, fixture VARCHAR cleanup and seam-build
database contamination each received one distinct repair. The approved
host-network retry resolves the sandbox-only packaging download failure.
The domain-type collision received one conditional qualification repair. Its first
expanded runtime fixture used the pre-existing physical SQL keyword `set`; that
failed observation is retained, and runtime controls use runnable domain names
`HashSet`, `JobExecution` and `JobParameters` without changing SQL guards/defaults.
