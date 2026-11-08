# Generated Docker Image Assessment

EF-V5-M2-ENGINE-IMAGE-PROOF-S1 revision 1 assesses actual generated **build-stage
and final runtime images**. It is not remediation, vulnerability-risk acceptance,
overall M2 completion or release clearance. Merged #330 supplies the endpoint
collision/exposure prerequisite, not image vulnerability evidence.

## Coverage And Identity

Declare the case-to-artifact map before collecting. Reuse the ten shapes and
three shipped profiles (30 cases) in the [existing Maven collector](../../scripts/collect_generated_maven_baseline.py).
Map every case to both stages, Java 17/21, recipe/input/profile, actual resolved
and packaged inventory, and relevant configuration. Reference platform:
`linux/amd64`. An ARM64 host running those images uses emulation, not ARM64 proof.
Other platforms remain unassessed.

Current recipes use the versioned [reviewed Noble index mapping](../generated-build-reference-policy.md)
for both Java targets. The dated October 17 evidence used floating
`maven:3.9.9-eclipse-temurin-17` / `-21` and `eclipse-temurin:17-jre` / `:21-jre`;
its explicit historical replay contract remains unchanged. Do not silently
substitute either policy's references. Record resolved base digests, exact recipe hash, image
ID/platform/rootfs and actual tested image. A saved image does not prove a later
rebuild from mutable tags or live Maven repositories.

Deduplicate only after actual recipe/platform, resolved and packaged inventory,
and relevant configuration justify equivalence. A historical Maven graph alone
is insufficient. Keep every applicable case receipt/mapping; one convenient app
is not universal coverage. Representative final images must start as intended
non-root, with normal schema initialization and bounded application checks.
Functional success is not vulnerability clearance.

The scanner's `image_id` identifies the assessed configuration blob. A local
Docker image store may instead address the loaded image by an OCI manifest
digest. Runtime proof must retain these distinct identities: verify the loaded
local reference against the saved export's manifest, configuration, layers,
platform, launch settings and application JAR; prohibit implicit pulls; then
verify the created container uses that inspected image. An unverified mutable
tag is not a substitute for the assessed image.

A bounded continuation may reuse completed scans only after revalidating their
original reports, inputs, inventories and exact exports. Preserve the failed
attempt separately. Record the previous campaign hash, each case's actual
generator/collector SHA, the set of actual generator SHAs, and each runtime
proof's actual helper SHA. A later helper does not become the generator of an
earlier image or the executor of an earlier successful runtime proof.
New generation/assessment still requires its own clean exact-source freeze;
continuation does not exempt it or turn partial coverage into a complete scan.

Private image retention is deliberately narrower than scan coverage. Keep the
three representative final-image exports used for startup proof, with verified
lossless compression. After complete scan/inventory validation, other task-owned
exports may be removed with explicit original-export digest, image identity,
validation and cleanup receipts. The reduced completed campaign does not retain
those exports for replay or rescan; a later rebuild has a new identity and is
not a replay. Any retained failed-campaign archives are separate; consult the
dated record for their actual availability. Do not infer a general replay
guarantee or permission to discard failed observations.
Keep every case's original scanner/SBOM output, inventory, findings, native-member
records, source/configuration receipts and hashes. This does not deduplicate or
reduce the 30-case/two-stage assessment.

## Collection Contract

[Collection](../../scripts/collect_generated_images.py) and
[assessment](../../scripts/assess_generated_images.py) supply local provenance,
normalization and integrity checks. Tool versions and official archive hashes
are [pinned separately](../../scripts/image_assessment_tools.json) from generated
runtime dependencies. Verify archives before execution and check actual versions.
The archive/checksum share a release trust boundary, not independent signing.

Retain tool/binary hashes, database identity/date/hash, actual generator SHA,
input/generation/profile, recipe/base/image identities, SBOM/inventory and
findings. Cover OS packages, JDK/JRE, packaged Maven libraries and identifiable
native/archive members. Register unsupported embedded code, JDK/feed attribution,
bootstrap/plugin paths and native extraction explicitly, not as scanned clean.

Image catalogers can infer incorrect Maven package URLs from JAR manifests. Keep
their original reports/findings unchanged and record those coordinate gaps.
For actual packaged application dependencies, derive a separate CycloneDX input
from retained Maven components only after comparing the current JAR SHA-256s.
The separately identified packaging bootstrap uses its embedded identity and
generated POM evidence, not a guessed name. The pinned local Grype scanner must
extract that complete authoritative coordinate/version/hash set; missing or
contradictory extraction is incomplete even if every scanner exits zero.
This supplemental local scan does not run Maven resolution, submit an inventory
to an external service or replace the original per-app SBOM command.

Build-stage coverage also includes declared test-classifier artifacts. The two
Kafka `test` JARs are not final application dependencies, but their physical
cache bytes and exact classifier-qualified coordinates must be accounted for.
Where the image cataloger cannot extract them, use a separate local authoritative
SBOM bound to the retained resolved inventory, BOM hashes and actual image/cache
identities. Require the pinned scanner to extract the exact coordinates,
including classifiers. Retain its findings as build/test observations; they
affect assessment status. Missing or contradictory extraction is incomplete,
not permission to call these JARs optional plugin gaps or scanned clean.
The qualified classifier supplement is bounded to Kafka clients/server-common
4.2.1 with classifier `test`. Other classifier identities or versions require
qualification, not a name-based inference or silent widening of coverage.

Native-member hashes cover packaged application JAR contents, not exhaustive
native provenance or advisory identification for every OS/JDK/plugin binary.
Build-cache JAR extraction/hashes and inferred-coordinate/feed gaps are retained
separately; neither execution of every plugin nor complete bootstrap/native feed
coverage is claimed. Unknown identities and unsupported scope stay explicit,
not silently vulnerability-free.

Reuse the [existing per-app Maven SBOM path](generated-maven-assessment.md).
The dated October 5 campaign is reusable only with applicability and actual
packaged-inventory equality checks; do not relabel it as a fresh advisory run.
Image SBOMs add container inventory, not a replacement Maven resolver or silent
handoff-format change. Do not patch generated source/POM/configuration/recipes.

| Exit | Meaning |
| --- | --- |
| 0 | Complete required coverage, no reported matches at the recorded database state; not security clearance. |
| 1 | Complete assessment with findings retained OPEN for disposition. |
| 2 | Missing/malformed/incomplete evidence, inventory/identity mismatch, failed tooling/network/inspection or timeout. |

A zero scanner exit is insufficient: verify inventory, extraction and identities.
Do not suppress findings, mask errors, silently skip cases or expand into upgrades.
All four image-tool CLI entry points map unexpected ordinary exceptions to exit 2;
an uncaught inspection error must never masquerade as findings-bearing exit 1.
Explicit CLI exits and operator interrupts are not converted to successful proof.

## Network, Reproduction And Refresh

Routine public tool/database/base downloads are allowed. Scan only local Docker
images/exports and local SBOMs, with implicit advisory/update calls disabled after
controlled database retrieval. Do not upload source, private identifiers, whole
images or SBOMs to a new service. Existing Maven/OSV restrictions remain; no new
full 30-case/two-pass Maven query campaign is authorized here.

Use trusted synthetic fixtures, local Docker, unique task-owned resources and
bounded timeouts. Do not prune other resources, change global Docker settings or
use a remote/offload builder. Preserve failures; stop if required coverage remains
unavailable after diagnosis and one justified corrective attempt.

The bounded reference collector budgets 3 GiB for persistent private evidence
and reserves an estimated 6 GiB working space, subject to a hard 20 GiB free-space
floor. It requires at least 26 GiB free before starting each case. These are
limits, not a guarantee that a host can complete the campaign.
Only its uniquely owned builder/cache is recreated between cases; within each
case the build/final pair shares that builder. A capacity breach is incomplete
coverage, never a clean assessment or permission to prune unrelated work.
Exclude ephemeral scanner scratch before directory traversal for persistent
accounting; the actual free-space check still includes its disk usage. Retained
evidence inspection errors remain failures, not ignored missing files. On a
failed inspection or scanner execution, stop and wait for the owned scanner
before capturing output hashes or compression receipts. A failed command's
partial output is not a completed assessment.

### October 20 Noble Correction And Evidence

The [Noble record](generated-images/2026-10-20-noble/README.md) assesses generator
`c8798275065a8a0b619046707fad053f8a9b9ad1`, not the later tooling/evidence PR
head. All 30 cases/60 stages use the reviewed index policy. Its completed
publication contains 622 normalized finding records and 22,740 scanner
observations; these are overlapping scanner/package records, not that many
distinct vulnerabilities. The [findings record](generated-images/2026-10-20-noble/findings.md)
separately reconciles historical copies, current observations and vendor sources.
No scanner silence, build-only scope or functional success accepts risk.

Five cases/ten assessments completed before the unchanged storage guard stopped
the first invocation. Missing-only invocations supplied the other 25 cases/50
assessments. Their original partial root receipts remain exit 2. A new full
aggregate binds all 60 completed assessments, shared databases, copied input
hashes and original timestamps; only its separately validated full coverage
is complete. This is not the October 17 assembler's fixed 20-plus-10 partition.
Its private fragment/copy receipts are necessary for original-collection replay.

Publication revalidates the retained reports without rebuilding or rescanning.
The plan retains validated `build_base`, `runtime_base` and
`base_reference_policy`; invalid, partial or mixed pairs still refuse. Historical
declarations keep their original policy. Later plan repair and publication do
not change the generator, scan bytes, database dates or runtime-proof identities.

The [proof summarizer](../../scripts/summarize_generated_image_proofs.py) validates
retained compatibility and separate default/native receipts. The Kafka tests
are [proof-supplied sources](../../tests/fixtures/residual-base-proof/README.md),
not Engine-emitted tests: 26 of the 32 compatibility tests, with six emitted tests.
The [publication projection](../../scripts/project_generated_image_proof_evidence.py)
keeps private hashes, uses lossless path/hash arrays, and replaces only validated
synthetic correlation identifiers consistently in proof mode. Retention revision
2 separately projects vendor source facts without full advisory bodies and
replaces the sanitized home-relative interpreter path with a portable identifier.
Unrecorded historical interpreter version/hash values remain explicitly unknown;
today's executable is not substituted as historical provenance. Complete source
records remain unchanged in the private archive. These are derived records, not a
new runtime execution or a scanner exception. Runtime version/origin observations
do not supply a missing runtime LZ4 JAR hash or establish production-image byte
equality; the forced-native baseline also has its separately disclosed limit.

The [manifest adapter](../../scripts/prepare_generated_image_residual_manifest.py)
and [residual reconciler](../../scripts/reconcile_generated_image_residuals.py)
use explicit local roots and member hashes. Retained proposal/vendor/private
proof inputs are required, in addition to the full sanitized layout. The adapter
returns 0 only for manifest preparation; the reconciler returns 1 for complete
findings-bearing reconciliation and 2 for incomplete input. Neither runs a
scanner, selects a replacement dependency or accepts residual risk. The existing
Maven reconciler remains the dated 18/33 accounting path, not a fresh advisory run.

The publisher writes the full sanitized layout. After derived ledgers and final
README/findings are prepared, the
[filesystem packager](../../scripts/package_generated_image_evidence.py) creates
the compact core, manifest and private archive directly:

```bash
python scripts/package_generated_image_evidence.py \
  --input-root "$FINAL_SANITIZED_LAYOUT_ROOT" --output-root "$NEW_CORE_ROOT" \
  --evidence-dir docs/handover-evidence/generated-images/2026-10-20-noble \
  --archive-dir "$NEW_PRIVATE_ARCHIVE_DIRECTORY" \
  --archive-name 2026-10-20-noble-retention-r2-sanitized.tar \
  --source-commit c8798275065a8a0b619046707fad053f8a9b9ad1 \
  --expected-publication-sha256 "$FINAL_PUBLICATION_SHA256"
```

The input is the finalized layout, not the unextended publisher index. All three
roots must be separate and outputs fresh. No raw evidence Git commit is created.
See the [new storage note](generated-images/2026-10-20-noble-storage.md) for actual
counts, reproducible archive metadata, explicit verifier commands and the limits
of clean-clone versus private-original reproduction. Integrity is not security
acceptance. Repository-only verification establishes internal consistency;
the reviewed-source label is recorded, not independently verified by the tool.
The reviewed Git commit/PR anchors identity; archive verification additionally
checks content hashes and source reconstruction, not authentication of the
recorded reviewed-source/original-archive labels. See the
[current storage clarification](generated-images/2026-10-20-noble-storage.md#verification-and-reproduction).
The private reconciliation wrapper pre-verifies twenty more inputs than the
public CLI; its hash and exact receipt difference are recorded in the storage
note. Use the [maintainer tool map](generated-image-maintainer-tools.md) to
distinguish offline replay from campaign execution. The original #333 source and
GitHub references remain reachable; this replacement does not erase them or
authorize distribution of the archive. The unchanged historical record remains
available below.

### October 17 Recovery And Reproduction

The publisher writes the full sanitized layout. The repository retains only the
declared 161-file reviewed core; the complete unchanged bundle is held in a
checksummed private archive. Consult the
[storage and verification note](generated-images/2026-10-17-storage.md) for the
exact split, archive-only references in the dated README, verification commands
and four reproducibility tiers. No evidence bytes or historical results changed.

The [October 17 record](generated-images/2026-10-17/README.md) replaces unavailable
private image proof, not historical committed evidence. A host temporary-directory
loss removed the earlier 23 private assessments, two startup records, databases
and failed-image archives. None receives reuse credit. The committed October 14
default-LZ4 logs/receipts and dated Maven/vendor sources survived and were checked;
their former private preimages are unavailable. Keep retained proof in persistent
storage outside disposable test scratch and cache-cleanup targets.

The fresh October 17 collection completed 40 assessments and all three startups,
then stopped on a public-registry TLS timeout before exporting the next image.
Following explicit authorization and base restoration, `campaign --cases`
executed only the remaining ten cases/twenty assessments. Its root deliberately
remains `partial-affected-scope` with exit 2; `affected_scope_exit_code` reports
the completed selected scope. Neither original fragment becomes a successful
full campaign.

The [bounded offline assembler](../../scripts/assemble_generated_image_campaign.py)
accepts only this recorded 20-plus-10 partition, exact generator/declaration and
original failure identity. It verifies all 60 stages, three startups, shared
tool/database snapshots, copied bytes and original UTC spans. It derives a new
complete aggregate, preserving both input receipts and the failed command. The
publisher revalidates that composition and retains sanitized lineage. This is
not a scheduler, arbitrary resume registry, retry authorization or M3 automation.

Given the retained private fragments, reproduce the full sanitized publication
layout directly; the repository's core/archive split is separately verified by
the storage note's manifest and verifier, not produced by the publisher:

The October 17 record binds the exact original replay tools listed in the
[tooling review note](generated-image-tooling-review-2026-10-17.md). Use that
revision for byte-identical historical replay; current repaired validation also
recognizes that one pinned assembler identity for the unchanged composition.
This is not permission to accept an arbitrary source hash.

Publication redaction uses positional `<host-N>` placeholders, so it is not
location-independent. Byte-identical republication requires the original
redaction roots and ordering, or explicit `--host-prefix` values for the recorded
roots when replaying moved storage. These arguments refer to the original path
spellings in the receipts, not their resolution on the current host. They may be
repeated; never use `/` as a prefix. Verify output hashes rather than assuming a
different prefix set produces the original bytes. The repaired publisher rejects
residual home paths, recorded command/cwd roots and home-only replacements that
still expose the original private layout. An incomplete attempt has no
`publication.json`; preserve it separately, then correct prefixes and use a new
destination. Do not edit recorded inputs or the dated committed evidence.

```bash
python scripts/assemble_generated_image_campaign.py \
  --first "$FIRST_FRAGMENT" --remaining "$REMAINING_FRAGMENT" \
  --declaration "$DECLARED_COVERAGE" --output "$NEW_ASSEMBLED_DIRECTORY"
# Exit 1 is expected for complete findings-bearing coverage; 2 is incomplete.
python scripts/publish_generated_image_evidence.py \
  --campaign "$NEW_ASSEMBLED_DIRECTORY" --declaration "$DECLARED_COVERAGE" \
  --output "$NEW_PUBLICATION_DIRECTORY" --host-prefix "$RECORDED_PROOF_ROOT"
python scripts/reconcile_generated_maven_findings.py \
  --policy docs/handover-evidence/maven-policy-2026-10-05 \
  --baseline docs/handover-evidence/generated-maven/2026-10-05 \
  --packaged-inventories "$NEW_ASSEMBLED_DIRECTORY/packaged-inventories.json" \
  --output "$NEW_RECONCILIATION_JSON"
```

For a fresh assessment, declare the actual selected source and obtain a new
clean-freeze approval; never reuse the old approval or imply a rebuild is the
old image. With persistent, newly selected output paths, use:

```bash
python scripts/assess_generated_images.py plan \
  --declaration "$DECLARED_COVERAGE" --output "$NEW_COVERAGE_PLAN"
python scripts/collect_generated_images.py setup --output "$NEW_TOOL_DIRECTORY"
python scripts/collect_generated_images.py campaign \
  --declaration "$DECLARED_COVERAGE" --approval "$CLEAN_FREEZE_APPROVAL" \
  --tool-setup "$NEW_TOOL_DIRECTORY" \
  --baseline docs/handover-evidence/generated-maven/2026-10-05 \
  --output "$NEW_CAMPAIGN_DIRECTORY"
```

The following earlier continuation commands describe historical authorized
boundaries. Their missing pre-reboot private inputs cannot now be reconstructed
from conversation hashes or substituted with the new fragments.

For the specifically authorized first-case runtime-reference continuation, use
a new output directory and retain the original failed campaign unchanged:

```bash
python scripts/collect_generated_images.py continue-campaign \
  --declaration "$DECLARED_COVERAGE" --approval "$CLEAN_FREEZE_APPROVAL" \
  --tool-setup "$VERIFIED_TOOL_DIRECTORY" --baseline "$RETAINED_MAVEN_BASELINE" \
  --prior-campaign "$PRESERVED_FAILED_CAMPAIGN" --output "$NEW_CAMPAIGN_DIRECTORY"
```

The continuation approval explicitly binds the prior campaign digest,
`crud-h2-j17`'s original generator/collector SHA, and the new frozen helper SHA.
This narrow continuation revalidates and reuses those two completed scans,
retains the failed runtime observation, and runs the affected exact-image startup
before collecting the remaining 29 cases. It is not a general resume registry,
permission to reuse arbitrary partial scans, or a fresh 60-scan claim. All 60
validated assessments still must be present for publication; provenance records
which two were reused and which 58 were newly collected.

If that first case has already passed runtime validation and was finalized
before a capacity stop, a separately approved capacity-only continuation instead
preserves the completed case. Bind the exact capacity-stop receipt and original
successful helper identity in addition to the original scan lineage. Revalidate
both retained stages, compressed exports/reports, runtime evidence, and unchanged
tool/database identities before copying. Do not rescan, rebuild or rerun that
case's successful startup. Preserve both earlier campaign receipts, the original
failed runtime, and all original source identities and UTC spans. The remaining
29 cases use the new clean freeze; their two representative runtime proofs name
their own actual helper. Neither path may reuse arbitrary partial cases or call
incomplete coverage a complete campaign.

Use `continue-capacity` with the same explicit arguments shown above and the
capacity-stop campaign as `--prior-campaign`. Its separate approval uses
`capacity_continuation_approved: true`, the exact `prior_campaign_sha256`,
`reuse_case`, `reuse_generator_sha`, `reuse_collector_sha` and
`reuse_runtime_helper_sha`, plus the new campaign's ordinary clean-freeze fields.
Do not set `continuation_approved` for this path: that approval authorizes a
failed-runtime retry, not reuse of an already successful runtime observation.

The separately authorized Kafka-coverage continuation binds the exact earlier
campaign receipt and its nine finalized cases. Revalidate all 18 assessments,
both successful runtime observations, retention and unchanged tool/database
identities before copying. Preserve their original files and source/helper/UTC
identities, the earlier lineage, and the failed Kafka observation separately.
Only the affected Kafka case and the remaining 20 cases are newly generated and
assessed: 21 builds, 42 assessments and one remaining representative startup.
Do not repeat the completed 18 assessments or two startups. All 30 cases and 60
complete observations are still required for final publication; reused proof
is not newly executed proof. This bounded cohort continuation is not a general
resume registry or change-aware verification implementation.

Use `continue-kafka` with the same explicit path arguments and the preserved
Kafka-stop campaign as `--prior-campaign`. Its approval sets
`kafka_continuation_approved: true`, the exact `prior_campaign_sha256`, and
`reuse_cases` from `kafka_reuse_bindings()` (case and original generator,
collector and nullable runtime-helper identities), alongside the new ordinary
clean-freeze fields. Do not set either earlier continuation approval. A missing
case, altered copied file, different tool/database identity or contradictory
source/time lineage is incomplete; it cannot silently trigger a replacement run.

The separately authorized storage-helper continuation preserves the next exact
boundary: 11 complete case pairs and one complete Java 21 Kafka build assessment
(23 assessments), plus both earlier startups. Validate their original source,
tool/database, hash and timestamp identities before reuse. Preserve the failed
final-image observation separately, including any historical raw/receipt
contradiction; never rewrite it into a pass. Reassess only that existing final
export, without rebuilding the app or repeating its build assessment, then
generate and assess the remaining 18 cases. This executes 37 new assessments
and one remaining representative startup. The reused image retains its original
generator/build identity; record the new assessment helper independently. All
60 complete assessments remain required before publication. Existing scripted
lossless-retention checks apply to finalizing the partially completed case;
original proof and the approved reuse boundary must remain auditable.

Use `continue-storage` with the same explicit path arguments and additionally
`--prior-manifest "$ORIGINAL_POST_STOP_FILE_MANIFEST"`. Its approval binds
`storage_continuation_approved: true`, `prior_campaign_sha256`,
`prior_manifest_sha256`, and `reuse_stages` from `storage_reuse_bindings()`, plus
the new clean-freeze identities. Do not set earlier continuation approvals.
The partial case's new final assessment records `assessment_helper_sha` while
retaining the saved image's original generation/collection provenance; the
campaign records helpers per stage. Copied proof and the scripted partial-case
retention transformation are independently checked before publication. A single
successful diagnostic command is never substituted for the required complete
assessment.

The dated evidence supplies exact commands, map, identities, findings, exclusions
and pending pin-versus-float decisions. Refresh for relevant generator/dependency/
recipe/profile/platform changes, new advisory/database evidence or changed
deployment artifacts. Final release-entry refresh remains separate.

[Publication](../../scripts/publish_generated_image_evidence.py) validates the
complete 30-by-two-stage campaign before writing a new sanitized evidence directory.
It retains inventories, findings and scanner JSON with deterministic gzip, records
private-original versus sanitized hashes separately, and excludes source/image
archives, binaries and database contents from the repository layout. Originals
of scanner/SBOM/source records remain private, losslessly compressed as applicable;
image-export retention follows the explicit policy above. No manual JSON editing,
compression or pruning is a reproduction step.

## Bounded Maven Follow-Ups

The ordinary Boot `java -jar` default-LZ4 proof is separate from the retained
explicit-native probe. Record actual default LZ4/XXHash behavior on Java 17/21
and real Kafka LZ4 input through the generated listener to output. Java fallback
is valid. No forced native load/factory override is default-mode credit. A labelled
additive observer is proof instrumentation, not generated business behavior; all
preexisting generated source/configuration/POM/recipe bytes remain unchanged.
Numeric/type equality is not decimal lexical-format proof.

Run the default proof from an explicitly selected clean source, keeping its
evidence directory outside that checkout:

```bash
python -m scripts.smoke.boot41_kafka_lz4_default_proof \
  --work-dir "$NEW_DEFAULT_PROOF_DIRECTORY" \
  --approved-source-sha "$CLEAN_PROOF_COMMIT"
```

The post-roundtrip observer obtains the compression level from Kafka's
`CompressionType.LZ4.defaultLevel()`; a constructor value of `-1` is not the
default-level contract. It records actual factory/compressor/checksum classes,
unchanged native-loaded state, correlated values/types, actual broker positions
and the fixture's declared null round-robin output key. It does not require the
inbound correlation key to become an undeclared output partition key. Preserve
failed observations separately; changing a helper does not turn its earlier
failed receipt into a pass.

[Default-proof publication](../../scripts/publish_default_lz4_evidence.py) validates
the retained observation/source receipts and emits compact sanitized receipts,
source inventories and losslessly compressed runtime logs. Earlier failed
attempts remain labelled failures with their actual source identities. It does
not copy host Docker configuration or turn this functional proof into an image
assessment; original receipts/logs remain private and unchanged.
The [October 14 default-launch record](kafka-lz4-default/2026-10-14/README.md)
contains both successful Java cases and the two separately preserved failures.

[Reconciliation](../../scripts/reconcile_generated_maven_findings.py) hash-checks
retained vendor/published-source receipts, enumerates all 18 historical mappings
and 33 vendor observations, and binds them to actual current image packaged
inventories. Unknown/contradictory ranges and feed gaps stay OPEN with owner/next
decision; zero-match scans do not clear historical evidence automatically. The
Jackson correction preserves inclusive `<= 2.22.0` and the 3.1.5 fix floor; original
source bytes remain unchanged.

No sibling changes, dependency/framework/base migration, signing, endpoint
suppression, integer-range implementation, Suite L5 or release operation follows.
