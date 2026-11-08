# Generated Maven Assessment Baseline

**Assessment tooling/proof complete for the declared matrix; findings open; M2 not complete.**
This record is dependency matching, not exploitability analysis, release clearance, or a
claim that generated applications are safe to ship.

Candidate: `EF-V5-M2-ENGINE-BOOT41-S4`, revision **1**.
Generating Engine: `109f6385345047013836f1e32b2d4230b9e8ad2b`.
Actual scan timestamps span **2026-10-03T23:44:42.769748+00:00** through **2026-10-03T23:52:37.835927+00:00**; no timestamp was rewritten.

## Coverage

Execution coverage: **30 case executions**, each built and assessed twice.
Persisted graph coverage: **14 unique dependency graphs** with complete reports.
Every case retains its own receipt, provenance/generation input, input/source inventories,
build log, and source/packaged-independence evidence. No repeat archive is retained.

| Case | Profile | Java | Build | Representative | Distinct findings | First / repeat raw findings |
|---|---|---|---|---|---:|---:|
| crud-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | crud-h2-j17 | 10 | 10 / 10 |
| crud-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean package -DskipTests` | crud-pg-j17 | 10 | 10 / 10 |
| crud-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean package -DskipTests` | crud-pg-j17 | 10 | 10 / 10 |
| crud-soap-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | crud-soap-h2-j17 | 10 | 10 / 10 |
| crud-soap-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean package -DskipTests` | crud-soap-pg-j17 | 10 | 10 / 10 |
| crud-soap-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean package -DskipTests` | crud-soap-pg-j17 | 10 | 10 / 10 |
| passthrough-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | passthrough-h2-j17 | 10 | 10 / 10 |
| passthrough-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean verify` | passthrough-h2-j17 | 10 | 10 / 10 |
| passthrough-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean verify` | passthrough-h2-j17 | 10 | 10 / 10 |
| kafka-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | kafka-h2-j17 | 18 | 18 / 18 |
| kafka-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean verify` | kafka-h2-j17 | 18 | 18 / 18 |
| kafka-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean verify` | kafka-h2-j17 | 18 | 18 / 18 |
| kafka-router-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | kafka-router-h2-j17 | 18 | 18 / 18 |
| kafka-router-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean verify` | kafka-router-h2-j17 | 18 | 18 / 18 |
| kafka-router-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean verify` | kafka-router-h2-j17 | 18 | 18 / 18 |
| ordinary-batch-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | ordinary-batch-h2-j17 | 10 | 10 / 10 |
| ordinary-batch-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean package -DskipTests` | ordinary-batch-pg-j17 | 10 | 10 / 10 |
| ordinary-batch-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean package -DskipTests` | ordinary-batch-pg-j17 | 10 | 10 / 10 |
| file-batch-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | file-batch-h2-j17 | 10 | 10 / 10 |
| file-batch-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean package -DskipTests` | file-batch-pg-j17 | 10 | 10 / 10 |
| file-batch-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean package -DskipTests` | file-batch-pg-j17 | 10 | 10 / 10 |
| m5a-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | m5a-h2-j17 | 10 | 10 / 10 |
| m5a-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean package -DskipTests` | m5a-pg-j17 | 10 | 10 / 10 |
| m5a-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean package -DskipTests` | m5a-pg-j17 | 10 | 10 / 10 |
| mixed-batch-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | m5a-h2-j17 | 10 | 10 / 10 |
| mixed-batch-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean package -DskipTests` | m5a-pg-j17 | 10 | 10 / 10 |
| mixed-batch-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean package -DskipTests` | m5a-pg-j17 | 10 | 10 / 10 |
| kafka-mixed-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | kafka-mixed-h2-j17 | 18 | 18 / 18 |
| kafka-mixed-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean verify` | kafka-mixed-h2-j17 | 18 | 18 / 18 |
| kafka-mixed-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean verify` | kafka-mixed-h2-j17 | 18 | 18 / 18 |

## Graph Equivalence

The versioned graph digest covers the normalized Maven tree, CycloneDX root/components/edges,
and full normalized inventory. It excludes the volatile CycloneDX SBOM timestamp; descriptive
SBOM metadata, tools, annotations and component hashes are outside graph identity. Each case
and repeat was validated before class assignment; a mismatch fails finalization.

| Representative | Equivalent cases | Artifacts | Dependency-bearing distinctions |
|---|---|---:|---|
| passthrough-h2-j17 | passthrough-h2-j17, passthrough-pg-j17, passthrough-pg-j21 | 91 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| crud-soap-pg-j17 | crud-soap-pg-j17, crud-soap-pg-j21 | 143 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| kafka-router-h2-j17 | kafka-router-h2-j17, kafka-router-pg-j17, kafka-router-pg-j21 | 143 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| m5a-pg-j17 | m5a-pg-j17, m5a-pg-j21, mixed-batch-pg-j17, mixed-batch-pg-j21 | 136 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| ordinary-batch-pg-j17 | ordinary-batch-pg-j17, ordinary-batch-pg-j21 | 136 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| crud-pg-j17 | crud-pg-j17, crud-pg-j21 | 129 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| file-batch-pg-j17 | file-batch-pg-j17, file-batch-pg-j21 | 136 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| crud-h2-j17 | crud-h2-j17 | 127 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| ordinary-batch-h2-j17 | ordinary-batch-h2-j17 | 134 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| kafka-h2-j17 | kafka-h2-j17, kafka-pg-j17, kafka-pg-j21 | 139 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| file-batch-h2-j17 | file-batch-h2-j17 | 134 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| m5a-h2-j17 | m5a-h2-j17, mixed-batch-h2-j17 | 134 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| crud-soap-h2-j17 | crud-soap-h2-j17 | 141 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |
| kafka-mixed-h2-j17 | kafka-mixed-h2-j17, kafka-mixed-pg-j17, kafka-mixed-pg-j21 | 143 | basis=validated resolved components and normalized dependency edges; no assumed profile/shape equivalence |

## Findings

The aggregate contains **18 distinct advisory matches**: **11 production/build-impacting** and **7 test-only**, across **6 coordinates**.
A production/build classification means at least one matching inventory record is compile,
runtime, provided, or system scope. `provided` and `system` do not necessarily mean packaged
runtime reachability. Each aggregate observation carries sorted Maven scope/usage records.
Missing severity/fix data remains unknown; all remediation decisions remain pending.

## Repeat and Normalization Proof

Each `assessment-receipt.json` preserves real assessment/SBOM timestamps, both exits and counts,
inventory/finding-identity/machine-evidence digests, and whether first/repeat values match.
The machine-evidence digest includes the six documented JSON reports and excludes only
`assessment_time_utc` and CycloneDX `metadata.timestamp`. Finding identity is separately
defined as coordinate/version/advisory ID. Findings from either pass feed the aggregate and
therefore prevent overall exit 0; repeat-only metadata remains in aggregate observations.

## Reproducible Layout

The collector writes raw case reports. The committed companion command validates and emits the
reduced layout from a fresh output directory, including deterministic JSON, log whitespace
normalization, OSV gzip compression (`mtime=0`), pruning, receipts, graph mapping and summary:

```bash
python scripts/finalize_generated_maven_evidence.py \
  --source "$RAW_EVIDENCE_DIRECTORY" \
  --output "$NEW_REDUCED_EVIDENCE_DIRECTORY" \
  --candidate-id EF-V5-M2-ENGINE-BOOT41-S4 \
  --candidate-revision 1
```

For each representative, `assessment/` contains the full first SBOM, Maven tree, inventory,
findings, readable summary and tool logs; `osv.json.gz` is the sanitized full scanner report.
Aggregate `findings.json` retains both passes' case/run observations. The committed finalizer
does not fetch, build, scan, alter generated source, or replace actual timestamps.

## Limitations

PostgreSQL CRUD cases package with tests compiled but not run because no database service is
provided. Maven plugin dependencies, OS/JDK/container layers, runtime reachability, custom
profiles, browser/database/full-L5/runtime-E2E proof, dependency remediation, signing and CI
enforcement remain outside this baseline. Existing build/scan inputs remain unchanged.

Machine summary: [baseline.json](baseline.json). Aggregate findings: [findings.json](findings.json).
