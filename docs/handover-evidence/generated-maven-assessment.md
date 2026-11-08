# Per-Application Maven Dependency Assessment

This M2 prerequisite assesses **one trusted synthetic/generated Maven project**.
It does not upgrade dependencies, establish exploitability, waive findings, or
approve an application or Suite release. M2 remains incomplete.

Historical baseline (not the current Boot 4 default): [2026-09-13 assessment and machine-readable evidence](generated-maven/2026-09-13/README.md).

## Historical October 3 Promotion Campaign

Delivered [2026-10-03 reduced baseline](generated-maven/2026-10-03/README.md):
30 executions, 60 passes, 14 validated resolved graphs and 18 OPEN findings
(11 production/build, seven test-only), frozen generator `109f638`.
[Runtime/disposition supplement](../test-results/boot41-defaults-promotion-2026-10-03.md)
maps all 110 historical matches and retains actual source/dependency applicability.
This is not M2 completion, release clearance or independent approval.

## Corrected Dependency Policy Campaign

Delivered [2026-10-05 reduced baseline](generated-maven/2026-10-05/README.md):
30 executions, 60 passes, 14 validated graphs, zero scanner matches at the
retained query dates, and all resolved/packaged policy checks passed. Generator
`38862862a0f4e90eb4f809a0150c6d2702de2423` is distinct from the evidence commit.
The [dated decision and proof package](maven-policy-2026-10-05/README.md) maps all
18 October 3 findings and retains vendor-only sources, feed gaps and range
contradictions OPEN. Zero scanner matches are not security or M2 clearance.

The current generator uses `ef-v5-maven-1`; see the
[policy and runtime guide](../generated-app-standards/boot41-jobless-preview.md#dependency-policy).
Actual Docker build/runtime surfaces and the bounded #325 follow-ups are a
separate [image-assessment lane](generated-image-assessment.md). Reusing this
dated Maven campaign requires checked applicability and actual image packaged
inventories; it does not refresh its query timestamps or establish image clearance.
The same **10 shapes x 3 ordinary profiles = 30 cases**, with two complete
assessment passes each, remain binding. The retired aliases were never collector
cases, so retirement does not halve the campaign. Freeze a clean tested generator
commit before collecting; record it separately from the later evidence commit.

Each corrected case also retains `dependency-policy.json`: the actual packaged
JAR library inventory and applicable resolved-version checks from both passes.
The finalizer revalidates these reports when the campaign declares a policy;
legacy historical layouts remain independently supported. Query origin,
inventory reconciliation, repeat-pass union, integrity and deduplication guards
remain in force. Vendor feed gaps and contradictory ranges are separate OPEN
owner decisions, never scanner suppressions or universal clearance.

The Boot 4.1.1 promotion uses coverage version **2.0**: all original five shapes
x three ordinary profiles plus ordinary staging, file, M5a, mixed Batch and
mixed Kafka shapes. Jobless and JDBC Batch inventories are assessed separately;
classes are derived only from independently validated resolved components and
dependency edges in both passes. No seven-class assumption or copied findings.
The historical version 1.0 finalizer contract remains unchanged.

The collector requires a clean frozen committed generator SHA before and after
the declared two-pass campaign. Evidence commits are later and do not replace
that generator identity. PostgreSQL assessment builds with `-DskipTests` remain
compile-only; separate runtime proof supplies endpoint/database claims.
Finding exit **1** is complete with open decisions, not clearance; incomplete
exit **2** cannot be accepted. No suppression, risk acceptance or automatic
framework patch is supplied. The October 3 promotion's existing 110-match
September mapping remains historical evidence. This correction separately maps
all 18 October 3 identities to actual current coordinates and dispositions,
not a count-based exploitability comparison.

Before each scope query the SBOM components must equal resolved Maven records,
exclude the root, contain no nested extra components, and use reviewed public
third-party namespaces from trusted synthetic fixtures. Namespace membership
alone is not permission for arbitrary private artifacts: the collector also
checks each actual resolved artifact's POM identity and public Central origin
in the effective Maven repository before each query. Missing origins or
mismatched POMs stop before querying. The scanner reads the complete SBOM **locally**, but its pinned
CycloneDX extractor enumerates only Components (not Metadata.Component/Tools),
and its matcher sends only Maven ecosystem, package name and version through
OSV querybatch, then retrieves advisories by ID. Verified source:
`osv-scalibr` commit `9293bfa4f86f`, `extractor/filesystem/sbom/cdx/cdx.go`,
and OSV 2.3.8 `internal/clients/clientimpl/osvmatcher/osvmatcher.go`.
`--no-resolve`, explicit lockfile, no Go call analysis and temporary empty
configuration remain in force. No private/root/customer IDs, source, documents,
cache or whole-SBOM upload is authorized.

## Tools and Network Boundary

The checked-in pins in `scripts/maven_assessment_tools.json` select:

- CycloneDX Maven plugin **2.9.1**, CycloneDX JSON **1.6**.
- Maven dependency plugin **3.8.1** for the independently resolved inventory.
- OSV-Scanner **2.3.8**, using the official release binary SHA-256 checksums.

Maven and JDK versions are recorded per application rather than silently
replaced. The Maven JVM must match the generated POM's Java major version.
The Python command uses Engine's existing Python environment and JSON Schema
validation dependencies; no assessment dependency is added to generated apps.

OSV-Scanner 2.5.1 was evaluated but not selected: in the live Maven SBOM probe,
its JSON output lost group IDs, and its CycloneDX output logged invalid Maven
package names and contained no components. Version 2.3.8 retained full
`group:artifact` identities. A version change requires new coverage tests and
real proof; changing the version string alone is not sufficient.

The official references are the [CycloneDX Maven plugin documentation](https://cyclonedx.github.io/cyclonedx-maven-plugin/),
[Maven dependency-tree documentation](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html),
and [OSV SBOM scanning documentation](https://google.github.io/osv-scanner/usage/scan-source).
Local, unmodified CycloneDX schemas and their provenance/license are under
`scripts/schemas/cyclonedx-1.6/`; schema validation never downloads references.

Network access is explicit and required: the initial scanner download accesses
the official release host; Maven downloads plugins, artifact POMs and JARs from
the configured repositories (normally Maven Central). Maven executes trusted
project/plugin code, so **do not assess an unreviewed third-party POM**. The
scanner sends dependency ecosystem, group/artifact identities and versions to
the public OSV advisory service and retrieves advisory records. Do not use this
mode for confidential dependency coordinates without the appropriate approval.
No account, API secret, dashboard, source upload, product startup, KS process,
whole-cache scan, or recursive Engine scan is needed. Proxy/repository settings
remain operator-owned and must not be committed.

## Install the Pinned Scanner

Choose the official binary for the host (Darwin/Linux, arm64/amd64). For example:

```bash
mkdir -p "$TOOLS"
curl --fail --location --output "$TOOLS/osv-scanner_darwin_arm64" \
  https://github.com/google/osv-scanner/releases/download/v2.3.8/osv-scanner_darwin_arm64
curl --fail --location --output "$TOOLS/osv-scanner_SHA256SUMS" \
  https://github.com/google/osv-scanner/releases/download/v2.3.8/osv-scanner_SHA256SUMS
(cd "$TOOLS" && shasum -a 256 -c osv-scanner_SHA256SUMS --ignore-missing)
chmod u+x "$TOOLS/osv-scanner_darwin_arm64"
```

The assessment command also hashes the binary against the checked-in official
checksums **before executing it**, then verifies its reported version. It never
downloads or installs tools implicitly. The official checksum file and binary
share a release trust boundary; this is integrity checking, not a claim of
independent signature verification or scanner vulnerability clearance.

## Assess an Application

Use explicit directories outside the generated app for evidence. The output
directory must not already exist, preventing stale reports from appearing current.

```bash
python scripts/assess_generated_maven.py \
  --project "$GENERATED_APP" \
  --output "$NEW_EVIDENCE_DIRECTORY" \
  --scanner "$TOOLS/osv-scanner_darwin_arm64" \
  --provenance "$PROVENANCE_JSON" \
  --timeout 300
```

The provenance JSON has exactly these fields (the baseline collector produces
it automatically): `engine_sha` (full generating Engine commit),
`input_package_sha256`, `input_manifest` (logical repository-relative label),
`generation_run_id`, `target_profile`, `archetype`, and `generation_input`
(the effective manifest JSON object). The input package digest is SHA-256 of
the UTF-8 `json.dumps(file_hashes, sort_keys=True)` representation, where
`file_hashes` maps package-relative filenames to SHA-256 content digests.
The retained `input-files.json` and `source-files.json` serialize these as
explicit `{ "path": ..., "sha256": ... }` records; reconstruct the map for the
digest calculation. The finalizer rejects malformed or duplicate paths and
recomputes `input_package_sha256` from the retained input inventory before
copying it. It also requires the exact collector generation receipt shape and
reconciles its run ID and expected harness state with case provenance. A digest
is not an API key, even for an API-named file.
Input hashes and the effective manifest identify the actual profile override,
not just the untouched source fixture. These are supplied provenance, not a
claim that a post-generation command can reconstruct authoring history. Profile
and generation-run headers are checked against the generated POM. Use only
sanitized synthetic provenance, never credentials or host-specific paths.

The command invokes these explicit goals without changing the POM:

```text
org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
  -DoutputType=json -DoutputFile=<evidence>/maven-tree.json
org.cyclonedx:cyclonedx-maven-plugin:2.9.1:makeBom
  -DincludeCompileScope=true -DincludeRuntimeScope=true
  -DincludeProvidedScope=true -DincludeSystemScope=true -DincludeTestScope=true
  -DoutputFormat=json -DschemaVersion=1.6
  -DoutputDirectory=<evidence> -DoutputName=bom -Dcyclonedx.skipAttach=true
```

OSV receives only the explicit `bom.json` lockfile with `--all-packages`,
`--all-vulns`, `--no-call-analysis=go`, and `--no-resolve`. A temporary empty
configuration overrides inherited suppressions/package overrides. Scanning
uses a temporary working directory, not the generated source or Maven cache.

## Results and Exit Codes

| Exit | Meaning |
|---|---|
| 0 | Complete inventory coverage; no vulnerabilities reported at scan time. **Not a security approval.** |
| 1 | Complete inventory coverage; findings recorded and retained. Remediation decisions remain pending. |
| 2 | Invalid input, missing/mismatched tools, timeout, failed inspection/network, malformed report, incomplete inventory, or changed generated source. No clean assessment is established. |

Do not mask exit 1 or 2 with `|| true`. A caller collecting multiple applications
may explicitly continue on **1 only**, record it, and return 1 for the overall
baseline. An incomplete case ends the collector with exit 2.

The collector unions findings from **both** the initial `assessment` and `repeat`
passes. Any findings-bearing pass prevents an overall clean exit, even when live
advisories change between runs. Case `findings` counts the distinct union;
`assessment_findings` and `repeat_findings` retain the individual counts. Combined
findings deduplicate coordinate/version/advisory identities and list unique
affected `cases`. Their `observations` preserve every case/run and its original
finding metadata, including changes in severity or reported fixes. Top-level
finding metadata is the first observation, not a claim of the latest advisory
state. No incomplete repeat can produce a complete baseline.

Each raw complete assessment writes:

| Artifact | Purpose |
|---|---|
| `bom.json` | Schema-validated CycloneDX components, hashes, Maven PURLs and dependency graph. |
| `maven-tree.json` | Resolved Maven dependency tree, including scope and classifier. |
| `inventory.json` | Deterministically ordered full artifact identities, direct/transitive status, Maven scope and production/test classification. |
| `osv.json` | Full machine-readable OSV package/advisory report; source labels and known generated-app, evidence, scanner-directory and home paths are replaced with documented placeholders. |
| `findings.json`, `summary.md` | Coordinates, versions, advisory/alias IDs, available severity/vectors and fixed versions. Missing data stays unknown. |
| `assessment.json` | Input provenance, POM/source/inventory digests, actual tool versions, timestamp, exit status and coverage. |
| `maven.log`, `scanner.log` | Tool diagnostics with known local directories redacted. |

The scanner's `group:artifact` + version inventory must cover every resolved
Maven coordinate. Classifier/type variants remain separate artifact/PURL entries
in the SBOM and normalized inventory, but OSV can coalesce them into the same
Maven advisory query. This is explicit, not a missing-package waiver.
The root project is described in SBOM metadata, not a third-party dependency;
SBOM-producing tool metadata is likewise not a runtime dependency. Neither is
required in OSV's third-party package extraction.

Scopes come from Maven, **not** CycloneDX's required/optional component scope:
test dependencies are classified as test; compile/runtime/provided/system as
production/build contract dependencies. A `provided` or `system` classification
does not by itself establish packaged runtime reachability. Packaged independence
is separate proof. Maven plugins,
plugin dependency graphs, operating-system packages, JDK vulnerabilities,
container layers, source reachability, and deployment configuration are outside
this dependency assessment. Multi-module Maven reactors and unsupported PURLs
fail closed. Dependencies added by an adopter require a new per-app assessment.

Generated source hashes cover every file except top-level `target/` and Git
administrative metadata. Maven may write build output/cache entries; it must
not change source, POMs or configuration. The before/after check detects changes,
but is not a sandbox that prevents malicious Maven code from writing files.

## Reproduce the Baseline

From the selected Engine checkout, set `JAVA17_HOME`, `JAVA21_HOME` and `TOOLS`
to operator-selected installations, then run:

```bash
python scripts/collect_generated_maven_baseline.py \
  --scanner "$TOOLS/osv-scanner_darwin_arm64" \
  --output "$NEW_RAW_BASELINE_DIRECTORY"
```

The committed baseline uses the deterministic companion finalizer. It validates
the complete raw evidence first, then emits the final reduced layout directly to
a new directory; do not manually prune, edit, archive, recompress, or normalize
its output:

```bash
python scripts/finalize_generated_maven_evidence.py \
  --source "$NEW_RAW_BASELINE_DIRECTORY" \
  --output "$NEW_REDUCED_BASELINE_DIRECTORY" \
  --candidate-id ENGINE-M2-GENERATED-MAVEN-ASSESSMENT \
  --candidate-revision 1
```

Finalization reconstructs scanner findings and Maven/SBOM inventory coverage,
then reconciles assessment exits, artifact/package/finding counts, source and POM
hashes, case summaries, root totals, and generated receipts. Contradictory or
incomplete evidence fails closed instead of being copied into the durable record.
Current collector baselines validate the distinct first/repeat union separately
from both raw per-run counts; legacy raw baselines without per-run fields retain
their explicit compatibility check. Retained provenance must match both assessment
reports, and source/packaged independence reports must contain passing, case-bound
proof before any of those files are copied.
Scanner JSON is sanitized recursively after parsing so JSON escaping cannot retain
host paths. Windows user homes use `<home>`, UNC host paths use `<unc-path>`,
and generated-app, evidence, and scanner locations keep their named placeholders
on every operating system. Doubled backslashes without a UNC host/share shape are
preserved as advisory content.

The collector copies existing fixtures, changes only the **temporary input's**
target profile, generates with an explicit run ID, then copies only the
generated repository into an isolated build directory. H2 CRUD, passthrough and
Kafka cases run `mvn -B -ntp clean verify`. PostgreSQL CRUD uses
`mvn -B -ntp clean package -DskipTests`, matching the existing sample-pack driver's
database-free boundary: sources and tests compile, but database-backed tests do
not execute. This does not waive PostgreSQL runtime acceptance. Each case runs
existing source and packaged-JAR independence checks and two complete assessments.
Source trees and normalized dependency inventories must remain unchanged; live
advisories/timestamps need not be byte-identical. Temporary applications are
removed, evidence is retained, and the final status does not call a
findings-bearing baseline clean. `--case <id>` permits a named subset; the raw
report lists what actually ran. Current full baseline finalization expects the
declared 30-case matrix; historical coverage version 1.0 expects 15 cases.

**Historical coverage version 1.0 (2026-09-13), not the current 30-case matrix:**
five dependency shapes were tested against each of the three shipped profiles:

| Shape | Fixture | Dependency branch |
|---|---|---|
| CRUD | `examples/input-projects/generated-app-ci-smoke/app-definition.yaml` | JPA, validation, batch, Flyway, H2 or PostgreSQL/Flyway PostgreSQL. |
| CRUD SOAP | `tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml` | Same CRUD branch plus `spring-boot-starter-web-services`. |
| Passthrough | `examples/input-projects/country-router/app-definition.yaml` | Web, validation, actuator, tests; no database dependency. |
| Kafka | `tests/fixtures/kafka-integration/manifest.yaml` | Kafka, actuator, Prometheus, Kafka test libraries; no database dependency. |
| Kafka router | `tests/fixtures/kafka-router-contract/manifest.yaml` | Kafka plus `com.networknt:json-schema-validator:1.0.87`. |

Case suffixes `h2-j17`, `pg-j17`, `pg-j21` identify the legacy-compatible,
enterprise-postgres-java17, and standard-enterprise profiles, respectively.
For passthrough/Kafka the suffix identifies the selected profile, **not** an
emitted database. All retain Spring Boot 3.3.5. Every case is executed and
assessed independently. The finalizer may share persisted full evidence only
after its versioned graph comparison proves that the normalized Maven tree,
CycloneDX dependency identity/relationships, and normalized inventory match the
declared representative.

The CRUD emitter's SOAP condition is shared by inbound and outbound SOAP;
this baseline exercises it with inbound canonical SOAP, not every SOAP behavior.
All shipped profiles enable batch and Flyway; custom profiles toggling these,
or enabling the unshipped security flag, are excluded. Audit/test-console flags
do not add Maven dependencies. Request/reply and fire-and-forget Kafka routes
share the non-router POM branch; this is not runtime parity proof for every route.

The collector does not run browsers, database services, containers, full L5, or
application runtime E2E. It leaves canonical fixtures, old Python/Maven evidence,
Suite candidate pins, and the tracker unchanged. Live scanning is not a new CI
gate; normal Engine tests exercise mocked negative controls without Maven,
network access or sibling repositories.

## Reduced Durable Baseline

The dated baseline records **15 case executions and 30 assessment passes**, while
persisting complete dependency evidence for seven unique graph representatives:
`crud-h2-j17`, `crud-pg-j17`, `crud-soap-h2-j17`, `crud-soap-pg-j17`,
`kafka-h2-j17`, `kafka-router-h2-j17`, and `passthrough-h2-j17`.

Every case directory retains `assessment-receipt.json`, `provenance.json`,
`generation.json`, input/source inventories, source and packaged-independence
results, and its build log. The receipt keeps both real scan and SBOM timestamps,
assessment/scanner exits, finding and resolved-package counts, tool/advisory
provenance, source/POM digests, the assessor inventory digest, and normalized
inventory, finding-identity, and machine-evidence digests. No `repeat.tar.gz` or
full duplicate-graph assessment directory is retained.

Each representative additionally retains the complete first-pass CycloneDX
SBOM, Maven tree, inventory, findings, readable summary and tool logs. Its
sanitized OSV report is deterministic gzip (`mtime=0`, no embedded host filename).
Root `findings.json` still unions both passes, so repeat-only findings prevent an
overall clean result and changed live advisory metadata remains attributable to
its case/run observation.

`baseline.json.graph_equivalence` is the machine-readable seven-class map. Its
normalization algorithm is version **1.0**. The graph digest includes the complete
normalized Maven tree; CycloneDX format/specification/serial number, root and
dependency component PURLs and edges; and every normalized inventory record. It
excludes the volatile CycloneDX `metadata.timestamp`; non-identity descriptive
SBOM metadata, tools, annotations and component hashes are outside this graph
identity rather than silently treated as volatile. Any case or repeat that differs
from its declared representative fails finalization.

The separate normalized machine-evidence digest includes `assessment.json`,
`bom.json`, `maven-tree.json`, `inventory.json`, `findings.json`, and `osv.json`.
It excludes only `assessment.json.assessment_time_utc` and CycloneDX
`metadata.timestamp`. Actual timestamps remain in receipts and representative
reports. Finding identity is independently defined as coordinate, version and
advisory ID.

The current aggregate reconstructs from retained inventories as **110 distinct
advisory matches**: **88 production/build-impacting** and **22 test-only**, across
34 coordinates. These values are generated from evidence, not implementation
constants. Every observation exposes sorted Maven scope/usage classifications;
all 110 remediation decisions remain open, M2 remains incomplete, and no release
clearance is established.
