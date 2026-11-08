# Maven Policy Correction: 2026-10-05

Candidate **EF-V5-M2-ENGINE-MAVEN-FIX-S1**, revision **1**. This is the maintainer-approved bounded correction, not a release clearance, residual-risk acceptance, M2 completion or independent review report.

Assessment generator: `38862862a0f4e90eb4f809a0150c6d2702de2423` (tree `7fc6bc309f2f86ee7d20245231a259c24a6fbdd3`). The evidence-only commit and final PR head are distinct identities. Final-head CI and the external independent review remain required; their actual results belong to the PR checks and outside-commit review handoff, not a self-referential approval in this record.

## Approved Selection And Proof

`ef-v5-maven-1` retains Boot 4.1.1, Java 17/21, applicable Batch 6.0.5, annotations 2.21 and router validator 3.0.6. Tomcat core/EL/WebSocket are 11.0.26; Jackson 3 modules are 3.1.7; applicable Jackson 2 core/databind are 2.21.7 and test-only. Explicit dependency management selects `at.yawk.lz4:lz4-java:1.11.4` only for Kafka. Boot does not manage that dependency through an `lz4.version` property. The immutable mapping is `appbuilder/generation/dependency_policy.py`; generated provenance records its ID independently of manifest 2.0.

The [finalized campaign](../generated-maven/2026-10-05/README.md) retains all **30 ordinary cases / 60 assessments**, actual query dates, case-to-graph mapping, pinned tools, build logs and integrity receipts. Every case carries `dependency-policy.json`, recomputed against its packaged libraries and both resolved inventories during finalization. Jackson 2 mapper/core are absent from packaged apps. External PostgreSQL tests skipped by the collector are not runtime credit; actual generated-app CI runs the existing PostgreSQL Batch history/early-crash and ordinary runtime/security proofs.

The three public preview aliases are retired; the collector never contained alias cases, so there is no halved coverage. [Historical case mapping](historical-case-mapping.json) preserves all 30 identities. The obsolete captured-preview byte gate is replaced with 36 current generation/contract/same-policy-regeneration cases. Existing merged confinement/integrity guards and ordinary runtime/security assertions remain. Pre-v5 local test/demo migrations are unsupported; fresh generation/fresh separately provisioned databases do not authorize deletion/reset. Future v5+ update compatibility is deferred, not implemented here. Old internal emitter branches remain.

## Findings And Vendor Reconciliation

[All 18 historical identities](historical-18-dispositions.json) remain explicitly **OPEN** with their actual current resolved coordinates and advisory matches. The October 3 assessment and its generator `109f6385345047013836f1e32b2d4230b9e8ad2b` are untouched. Current scanner observations are separately retained in [current dispositions](current-finding-dispositions.json). Non-report means a dated source observation, never universal safety or exploitability clearance.

[Vendor dispositions](vendor-dispositions.json) and [dated public HTTP receipts](vendor-sources/retrieval-index.json) cross-check yawkat/lz4-java, FasterXML/jackson-core, FasterXML/jackson-databind and Apache Tomcat. Refreshed source bytes match the approved R2 receipts; compressed raw sources are retained, with uncompressed hashes. Reconciliation is supplementary to the campaign's own actual query interval, not a rewritten cutoff.

The five LZ4 vendor IDs GHSA-6cx8-rjf8-pr8g, GHSA-4v53-57pg-c464, GHSA-gm45-99xc-r7wv, GHSA-343h-94h5-c4wr and GHSA-mcr4-qmvw-px4g still return 404 from both direct global GitHub and OSV lookups. Their reported 1.11.2/1.11.4 fix floors are met by 1.11.4; the feed-coverage gap remains **OPEN**. The original GHSA-xx22-p4ch-683r reports a 1.11.1 floor. Upstream prefers 1.12.0, whereas this maintainer selection is intentionally 1.11.4; no alternative version was tried or silently selected.

Jackson core GHSA-649p-m576-vr99 is outside the original 18 and reports fixes 3.1.6/2.21.6, below the selected versions. GHSA-5gvw-p9qm-jgwh's published 2.x affected range `>= 2.21.0, <= 2.22.0` conflicts with its stated 2.21.5 fix floor. The published 2.21.7 source contains the `visibleInView` guard; 3.1.7 exceeds its reported **3.1.5** floor. **Wording correction, 2026-10-14:** the original prose incorrectly said 3.1.4; the retained raw vendor bytes report 3.1.5. The inclusive upper bound is preserved, not weakened to `< 2.22.0`. Source bytes and original scan timestamps are unchanged. That source evidence does not erase the **OPEN** range contradiction or assert blanket clearance. [Published source members and source-JAR receipts](published-source/index.json) retain the exact evidence. Apache's retained page documents the 11.0.25 HTTP/2 regression fixed in 11.0.26.

All open dispositions are owned by the Engine maintainer for an explicit follow-up decision; no suppression or implied acceptance. A demonstrated unmet targeted fix or compatibility defect requires a pause, not another upgrade loop. New unrelated observations are retained without expanding this goal.

## Native LZ4 Scenario And Reproduction

The new probe uses each generated application's unchanged non-root Dockerfile and unchanged POM on **linux/amd64**, Java **17 and 21**, with an injected proof entrypoint. It explicitly calls `Native.load` before factory selection because Boot's nested-JAR loader is not the system loader. It does **not** claim ordinary deployment defaults force JNI. Actual LZ4/XXHash factories and Kafka compression/checksum fields must be JNI; Java fallback fails the proof. An actual `compression.type=lz4` send is transformed through the generated listener and consumed from the output topic, including the numeric money contract.

Before extraction, the non-root entrypoint exclusively creates a fresh directory and passes `java.io.tmpdir` at JVM startup. The probe observes initial emptiness, exactly one new regular non-symlink SO, nlink 1, matching non-root ownership, inode/mode/size, a hash equal to the bundled 1.11.4 native resource, and actual `/proc/self/maps` loading. [Local receipts](native-local/source-applicability.json) retain the actual precommit `source_dirty=true` identity, not a relabelled final-head claim. Their helper/Java hashes match the frozen sources. Actual final-head CI independently supplies clean checkout receipts.

Finite local history is retained under `native-local/`: initial Java 17 producer validation failed because delivery timeout was below request timeout plus linger; material repair 1 set request timeout/linger and passed Java 17, then exposed Java 21's cached startup temp-directory behavior; material repair 2 moved directory selection before JVM startup and both versions passed. These are two distinct material repairs, now exhausted, not unavailable infrastructure. CI does not reset the limits. Both native SO hashes were `9e3f9a3deae369dc15788f07f68b84b0b6ea933356f59a0d43bc383bd17cb629`, uid 999. Local Docker hosted arm64 with amd64 emulation; the scenario still ran amd64, not an arm64 qualification.

From a clean checkout of the generator commit, install the pinned Python requirements and pinned/checksummed OSV scanner described in `scripts/maven_assessment_tools.json`, and set `JAVA17_HOME` / `JAVA21_HOME`. Use new task-owned directories:

```bash
python -m pip install -c requirements-lock.txt -r requirements.txt
python -m pytest -q
python scripts/collect_generated_maven_baseline.py \
  --scanner "$PINNED_OSV_SCANNER" --output "$NEW_RAW_EVIDENCE_DIRECTORY"
python scripts/finalize_generated_maven_evidence.py \
  --source "$NEW_RAW_EVIDENCE_DIRECTORY" --output "$NEW_REDUCED_EVIDENCE_DIRECTORY" \
  --candidate-id EF-V5-M2-ENGINE-MAVEN-FIX-S1 --candidate-revision 1
python -m scripts.smoke.boot41_kafka_lz4_container_proof \
  --work-dir "$NEW_NATIVE_PROOF_DIRECTORY"
```

Collector exit 1 means complete with findings; exit 2 blocks acceptance. Queries retain the existing fail-closed inventory/SBOM reconciliation and Central-origin guards, submitting only authorized public third-party Maven coordinates to OSV querybatch/vulns. No private/root coordinates, manifests, sources or whole SBOMs are uploaded. The finalizer validates and writes the reduced layout without manual pruning. Native commands require Docker and create uniquely named task resources, cleaned only if their creation succeeded.

Existing generated-app CI additionally executes ordinary H2/SOAP/passthrough, PostgreSQL Batch Java 17/21 early-crash/history, Kafka broker contracts and security regression proofs, plus one Java-serialization header/Map assertion for Batch's default context serializer. No second full local runtime campaign is credited. Numeric/type equality does not establish decimal lexical-scale preservation. Functional native/container proof is not image vulnerability clearance. macOS arm64, Linux arm64, Windows and riscv64 remain unassessed; image/SBOM follow-up, full Suite L5, release publication and remaining M2 decisions are excluded.
