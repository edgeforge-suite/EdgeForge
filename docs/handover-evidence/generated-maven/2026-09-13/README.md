# Generated Maven Assessment Baseline

**Assessment tooling/proof complete for the declared matrix; findings open; M2 not complete.**
This record is dependency matching, not exploitability analysis, release clearance, or a
claim that generated applications are safe to ship.

Candidate: `ENGINE-M2-GENERATED-MAVEN-ASSESSMENT`, revision **1**.
Generating Engine: `582c853f2566ac5cdf45ad239c1827a5aa47f12e`.
Actual scan timestamps span **2026-09-13T22:50:22.591906+00:00** through **2026-09-13T22:53:50.551762+00:00**; no timestamp was rewritten.

## Coverage

Execution coverage: **15 case executions**, each built and assessed twice.
Persisted graph coverage: **7 unique dependency graphs** with complete reports.
Every case retains its own receipt, provenance/generation input, input/source inventories,
build log, and source/packaged-independence evidence. No repeat archive is retained.

| Case | Profile | Java | Build | Representative | Distinct findings | First / repeat raw findings |
|---|---|---|---|---|---:|---:|
| crud-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | crud-h2-j17 | 77 | 77 / 77 |
| crud-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean package -DskipTests` | crud-pg-j17 | 80 | 80 / 80 |
| crud-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean package -DskipTests` | crud-pg-j17 | 80 | 80 / 80 |
| crud-soap-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | crud-soap-h2-j17 | 79 | 79 / 79 |
| crud-soap-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean package -DskipTests` | crud-soap-pg-j17 | 82 | 82 / 82 |
| crud-soap-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean package -DskipTests` | crud-soap-pg-j17 | 82 | 82 / 82 |
| passthrough-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | passthrough-h2-j17 | 73 | 73 / 73 |
| passthrough-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean verify` | passthrough-h2-j17 | 73 | 73 / 73 |
| passthrough-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean verify` | passthrough-h2-j17 | 73 | 73 / 73 |
| kafka-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | kafka-h2-j17 | 102 | 107 / 107 |
| kafka-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean verify` | kafka-h2-j17 | 102 | 107 / 107 |
| kafka-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean verify` | kafka-h2-j17 | 102 | 107 / 107 |
| kafka-router-h2-j17 | springboot-legacy-compatible | 17 | `mvn -B -ntp clean verify` | kafka-router-h2-j17 | 102 | 107 / 107 |
| kafka-router-pg-j17 | springboot-enterprise-postgres-java17 | 17 | `mvn -B -ntp clean verify` | kafka-router-h2-j17 | 102 | 107 / 107 |
| kafka-router-pg-j21 | springboot-standard-enterprise | 21 | `mvn -B -ntp clean verify` | kafka-router-h2-j17 | 102 | 107 / 107 |

## Graph Equivalence

The versioned graph digest covers the normalized Maven tree, CycloneDX root/components/edges,
and full normalized inventory. It excludes the volatile CycloneDX SBOM timestamp; descriptive
SBOM metadata, tools, annotations and component hashes are outside graph identity. Each case
and repeat was validated before class assignment; a mismatch fails finalization.

| Representative | Equivalent cases | Artifacts | Dependency-bearing distinctions |
|---|---|---:|---|
| crud-h2-j17 | crud-h2-j17 | 106 | archetype=crud, database_driver=h2, soap_dependencies=false, kafka_router_dependencies=false |
| crud-pg-j17 | crud-pg-j17, crud-pg-j21 | 108 | archetype=crud, database_driver=postgresql, soap_dependencies=false, kafka_router_dependencies=false |
| crud-soap-h2-j17 | crud-soap-h2-j17 | 114 | archetype=crud, database_driver=h2, soap_dependencies=true, kafka_router_dependencies=false |
| crud-soap-pg-j17 | crud-soap-pg-j17, crud-soap-pg-j21 | 116 | archetype=crud, database_driver=postgresql, soap_dependencies=true, kafka_router_dependencies=false |
| kafka-h2-j17 | kafka-h2-j17, kafka-pg-j17, kafka-pg-j21 | 137 | archetype=kafka-integration, database_driver=none, soap_dependencies=false, kafka_router_dependencies=false |
| kafka-router-h2-j17 | kafka-router-h2-j17, kafka-router-pg-j17, kafka-router-pg-j21 | 140 | archetype=kafka-integration, database_driver=none, soap_dependencies=false, kafka_router_dependencies=true |
| passthrough-h2-j17 | passthrough-h2-j17, passthrough-pg-j17, passthrough-pg-j21 | 75 | archetype=passthrough-router, database_driver=none, soap_dependencies=false, kafka_router_dependencies=false |

## Findings

The aggregate contains **110 distinct advisory matches**: **88 production/build-impacting** and **22 test-only**, across **34 coordinates**.
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
  --candidate-id ENGINE-M2-GENERATED-MAVEN-ASSESSMENT \
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
