# Batch Domain-Name Review Correction

Bounded P2 correction to EF-V5-M2-ENGINE-BOOT41-S2 revision 1, PR #319.
Reviewed head: `521f2dc690d0011d9cc3538b83e3d231a4907a43`.
Clean corrected generator/proof commit:
`a99ee99cfc944a56d925e5e215de4723a9bdfc10`.
Later commits carrying this record are documentation/evidence, not the tested
generator revision. Hosted results must be bound separately to the PR head.

## Correction And Controls

Batch templates now select launcher/explorer framework types and version-specific
methods explicitly at the controller sites. The import selector no longer rewrites
rendered bodies, domain type names, string literals or unrelated method calls.
Boot 3 defaults and the 24 shipped-profile corpus digests remain byte-identical.

Two schema-valid synthetic manifests each contain domain entities named
`JobLauncher` and `JobExplorer`: ordinary staging and M5a staging. Effective
generation tests cover both manifests on all six default/preview profiles.
The compilation command builds both manifests on the H2/Java 17 Boot 3 control
and Boot 4 preview, with standalone source/JAR checks and actual Maven tests.
The existing compile CI job runs this additional proof and retains its receipt
and logs; a static harness pass alone is insufficient.

The 13 new regression checks were overlaid on an archive of the reviewed head,
without copying corrected generator source. As expected, its six Boot 3 controls
passed while six Boot 4 name-preservation cases and the body-preservation control
failed (**7 failed, 6 passed**). These expected failures are negative controls,
not passing runtime evidence.

## Executed Proof

- Focused Python (Batch preview, S1 preview, M5a identity and idempotency):
  **166 passed**. Full Engine Python: **1,726 passed, 23 skipped** in default mode.
  The first sandboxed full run could not download packaging build dependencies;
  the authorized network-enabled repeat passed without changing tests.
- [Clean name-collision receipt](boot41-batch-name-review-fix-2026-09-29.json):
  **4 builds, 4 Maven tests, zero failures/errors/skips**. Actual UTC observation:
  `2026-09-29T02:34:19.529151+00:00` (September 28 locally).
- [Clean focused M5a receipt](boot41-batch-name-review-fix-m5a-2026-09-29.json):
  **1 build, 4 Maven tests, zero failures/errors/skips**. These include real HTTP
  validation and run/restart/idempotency assertions. H2 remains same-process.
  Actual UTC observation: `2026-09-29T02:34:03.766671+00:00`.
- Both clean receipts record the corrected commit above and `source_dirty: false`.
  Java 17.0.18+8 and Maven 3.9.12 were selected explicitly; no global settings
  or other tasks' resources were changed. Changed-file Ruff and diff hygiene pass.

From the Engine root with declared dependencies installed:

```bash
python -m pytest tests/unit/test_boot41_batch_preview.py \
  tests/unit/test_boot41_preview.py tests/unit/test_m5a_s2_batch_identity.py \
  tests/unit/test_m5a_s3_staging_idempotency.py -q
python -m pytest -q
python -m scripts.smoke.boot41_batch_name_collision_proof \
  --java17-home "$JAVA17_HOME" --maven-repo "$MAVEN_PROOF_CACHE" \
  --work-dir "$PROOF_OUTPUT/new-name-proof"
python -m scripts.smoke.boot41_batch_preview_proof --mode h2 --case m5a \
  --java17-home "$JAVA17_HOME" --maven-repo "$MAVEN_PROOF_CACHE" \
  --work-dir "$PROOF_OUTPUT/new-m5a-proof"
```

The full PostgreSQL matrix was not repeated locally for this correction.
The required generated-app CI reruns the established S1/runtime checks and
complete 16-build/38-test Batch matrix at the new head, plus the four new
compilation builds. Its results are reported in the PR, not inferred from the
older successful run. The earlier [Batch proof](boot41-batch-preview-2026-09-28.md)
and receipt remain unchanged as historical evidence.

No Kafka preview, Boot default switch, Batch 5 migration, dependency/advisory
assessment, full L5 or release acceptance is supplied. Maven/M2 remain incomplete.
The PR stays draft and requires new exact-head independent review. Docs impact:
updated.
