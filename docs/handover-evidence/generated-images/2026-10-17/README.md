# Generated Image Assessment: 2026-10-17

EF-V5-M2-ENGINE-IMAGE-PROOF-S1 revision 1: **complete assessment coverage,
findings OPEN**. This is not remediation, risk acceptance, overall M2 completion
or release clearance. Recipes, dependencies, profiles and application behavior
are unchanged. Merged #330 is a prerequisite consumed here, not vulnerability proof.

## Coverage And Source Identity

All generated applications, image builds, scans and startup helpers used Engine
`cc7721682f21009c6ad918ad021631213ff327a1`, based on main
`ba56abd1e0ff946260e96f3a3b715564fc0b740d`. No `appbuilder/` changes occur between
that base and the assessed generator. Later tooling/evidence commits are not
the generator. The full Python suite tested tooling revision
`39de47e8128d4d17ed4a7399b717565f3217a041`: **4,072 passed, 23 skipped**.
Final-head CI and independent-review identities belong to the PR handoff.

The [declaration](coverage-declared.json.gz) maps all ten shapes to all three
shipped profiles, with no image-equivalence claim or deduplicated assessment:

| Shapes | Profiles for every shape | Actual assessed surfaces |
| --- | --- | --- |
| CRUD, SOAP CRUD, passthrough, Kafka, Kafka router, ordinary batch, file batch, M5a, mixed batch, Kafka mixed | `springboot-legacy-h2` / Java 17; `springboot-enterprise-postgres-java17`; `springboot-standard-enterprise` / PostgreSQL / Java 21 | 30 applications, each build stage and final image: 60 assessments |

Reference platform is **linux/amd64**, executed on an ARM64 Mac with Docker
emulation. Other platforms are unassessed. Each stage retains its actual recipe,
resolved base digest, exported image/config/rootfs identity, input/source hashes,
packaged Boot-JAR identity, BOM/inventory bindings and original UTC times.
Container manifest references and assessed configuration IDs are explicitly
distinct, with their binding verified before runtime use.

Three actual final images started with their generated default user/entrypoint
and normal schema settings: `crud-h2-j17`, `passthrough-pg-j21` and
`kafka-router-h2-j17`. All reported health UP and UID 999. CRUD additionally
returned a JSON list from `GET /api/v1/records`; Kafka used an isolated broker.
This is not startup proof for all 30 applications, PostgreSQL database-runtime
proof, business certification or vulnerability clearance. Docker recipes package
with `-DskipTests`; those builds are not counted as executed generated tests.
Applicable generated-app tests run separately in CI.

## Findings And Inventory

[Summary](summary.json) and [full OPEN ledger](open-findings.json.gz): **2,186 exact
normalized finding records, 64,720 repeated observations** (38,320 Grype; 26,400
Trivy). These are not unique CVEs or exploitable paths. Cross-scanner aliases,
severity/fix disagreements, installed versions and case/stage observations remain
intact. See the [actionable family report](findings.md) for scope, owners and
next decisions. No suppression or residual-risk acceptance was made.

OS, JDK, build-tool/cache, Go and identifiable native/archive members are retained.
Per-app Maven coordinates are hash-bound to the actual packaged JARs and retained
resolved BOM, not merely inferred from filenames. All nine Kafka-family builds
include explicit extraction proof for both Kafka 4.2.1 test-classifier JARs.
There were zero final-image Java matches and zero supplemental packaged/classifier
Grype matches at these DB snapshots. That does not clear historical findings or
prove exhaustive Java/native/JDK/plugin advisory coverage.

The [local Maven reconciliation](maven-reconciliation.json) accounts for every
one of the 18 historical mappings and 33 retained vendor observations:
18 `REMEDIATED_VERSION`, 27 `SUPPORTED_VERSION_DISPOSITION`, six `OPEN`.
It checks retained source hashes and all 30 actual packaged inventories. This
uses dated October 5 vendor evidence, not a fresh Maven/OSV query campaign.

## Tools, Databases And Mutable References

Pinned, official-checksum-verified tools: **Syft 1.52.0, Grype 0.119.0,
Trivy 0.74.0**. All 60 assessments used the same recorded snapshots:

| Database | SHA-256 | Recorded source/update UTC |
| --- | --- | --- |
| Grype | `0a5db78fa73e2ab47d1203e9cedcab50d0f9bed3176dbb3997d86ea92d88d8fe` | 2026-10-17T00:29:33Z |
| Trivy OS | `bf1f1b29d76cae9ff085d418cb4bfdb3906b6069f837abdef06558b8102dd1db` | 2026-10-16T01:13:54.947090392Z |
| Trivy Java | `0e1cd4fbe85e36963327143ceb9a3b6653c54690937688ad650eafa4e40974a4` | 2026-10-17T01:07:50.102177499Z |

Trivy OS was downloaded October 17 at 18:28:40Z, after its mirror metadata's
NextUpdate. This older snapshot is disclosed, not called the latest feed.
Database dates/feed omissions remain limitations. Scans were local with updates
disabled; no source, image, SBOM or private inventory was uploaded to a new service.

The unchanged recipes still float `maven:3.9.9-eclipse-temurin-17` / `-21` and
`eclipse-temurin:17-jre` / `:21-jre`. Every observed resolution is retained in each
stage's `base-images.json.gz`; later pulls are not those images. **Recommended,
not adopted:** choose digest-bound builder/runtime release inputs with an owned
refresh procedure after the OPEN base/tooling findings are assessed. Continuing
to float instead needs an explicit reproducibility/freshness decision. Neither
policy nor risk acceptance is silently established here. Actions pinning remains
the separately recorded policy work; this slice changes no workflow.

## Retention, Failure History And Reproduction

Host temporary-directory loss removed the earlier private 23 scans, two startups,
databases and failed-image archives. None receives credit here. Committed
[October 14 default-LZ4 proof](../../kafka-lz4-default/2026-10-14/README.md) survived
and was hash-checked: Java 17/21 ordinary Boot launches, JavaSafe LZ4 and JavaUnsafe
XXHash, no forced native load, real Kafka input/output. Its actual generator is
`fe125b2d6c84aadacb2605f21d7bd146087afbab`; it was not rerun on these new images.
Its former private preimages are unavailable, while the committed failures and
sanitized receipts/logs remain historical evidence. Application/helper applicability
was checked; this is not new JNI/native vulnerability clearance.

Fresh scans ran 18:34:12Z to 20:02:30Z on October 17. The first fragment completed
40 assessments and all startups, then failed before exporting case 21 on a public
Docker registry TLS timeout. Its root remains incomplete/exit 2. A subsequent
empty attempt found a missing local base; it has no assessment credit. After
explicit restoration authorization, only the missing ten cases were executed.
That collector root remains partial-affected-scope/exit 2, scope exit 1.

[Composition](composition.json.gz) preserves both original receipts, the failed
command/streams and copied-file hashes, deriving complete aggregate coverage
only after validating all 60 assessments. No successful scan/startup was repeated.
The failed command's text streams are exported as sanitized JSON text wrappers;
their private-original hashes still identify the original bytes.
An initial publication refusal (archive source misclassified as dependency name)
and an initial test-scratch placement failure remain private failed observations;
the bounded fixes did not change scans or weaken assertions.

The private assembled layout retains three verified compressed final exports;
57 other exports were removed only after validated scans, with retention receipts.
Original reports/inventories and source/input records remain private in persistent
storage. The [publication index](publication.json) distinguishes original-private
hashes from sanitized JSON/gzip hashes. The repository deliberately excludes image,
source/input archives, binaries and database contents. It cannot replay removed
exports. Rebuilds or later databases create new evidence, not the old identities.

Use the [assessment/reproduction guide](../../generated-image-assessment.md#october-17-recovery-and-reproduction)
and committed assembler/publisher commands; no manual JSON, gzip, pruning or
receipt editing is a reproduction step. Refresh at final release selection and
after relevant generator, dependency, recipe, platform or advisory changes.
Native identification gaps, Maven bootstrap/plugin coverage and the six retained
vendor issues remain explicit in [findings](findings.md). Full Suite L5, image/base
remediation, dependency upgrades, signing and release operations were not performed.
