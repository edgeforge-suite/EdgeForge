# Clean-Plugin Plexus Overlay: 2026-10-24

**Scoped build-tool correction; historical findings are not retroactively closed.**
Task-start date is October 24; the actual scan dates are 2026-10-25 UTC.
Generator: `b7c48b58341f823c3a87ab02456cd1c10743a32e`. No M2/security/release clearance or risk acceptance.

## Scope And Proof

Only the inherited Maven Clean Plugin's Plexus Utils dependency changes to 4.0.3.
Other plugin realms, Maven-distribution 3.6.1, application dependencies, Boot,
schema and base references are unchanged. [Summary](summary.json) binds four
`linux/amd64` builder-stage artifacts on Java 17/21; 30 cases are POM/configuration
coverage, not a new full 30-case/60-stage manual assessment campaign.

The unchanged emitted image recipe runs `mvn -q -DskipTests clean package`.
**That image build earns zero executed-test credit.** Separate exact-toolchain
`clean verify` proof executed 28 tests: two Engine-emitted and 26 proof-supplied.
Those runs removed clean markers and observed Clean Plugin 3.5.0 loading Plexus
4.0.3. Frozen disabled Boot 3 renderer controls do not establish shipped Boot 3 support.

## Findings And Copies

| Builder-stage case | Normalized finding records | Exit |
| --- | ---: | ---: |
| `crud-h2-j17` | 642 | 1 |
| `crud-pg-j21` | 642 | 1 |
| `kafka-pg-j17` | 642 | 1 |
| `kafka-pg-j21` | 642 | 1 |

Exit 1 means completed with findings, not clean. These per-image normalized
scanner observations are **not unique vulnerability counts**; all remaining
findings stay OPEN in the private raw evidence. No blanket disposition follows.

The October 20 target is two scanner identities (`GHSA-6fmv-xxpf-w3cw` and
`CVE-2025-67030`) recorded across 30 builders, totaling 60 case observations,
not 60 distinct vulnerabilities. The original identity index and ledgers remain
byte-hash-bound and unchanged; scanner fix claims remain distinct.

[Targeted copy ledger](targeted-copy-ledger.json) separates current physical
cache/distribution copies from actual debug-realm proof. The recorded current
Plexus inventories contain cache 3.6.1, cache 4.0.3 and distribution 3.6.1;
4.0.2 is absent from those recorded copies in these four images only.
This is scoped replacement/absence evidence, not historical closure or
family-wide remediation. Realm inclusion is not vulnerable-function use.

Primary POM evidence binds Clean Plugin 3.5.0 to `maven-plugins:44`, then
`maven-parent:44`, which managed the unversioned Plexus dependency at 4.0.2.
The current plugin-owned override and actual loaded realm are separate evidence.
Central HTTPS/checksums are not signature verification; no full source/advisory bodies are published here.

## Retention And Limits

Use the [verified private-archive descriptor](archive-bindings.json) and
[core manifest](core-manifest.json). The archive has not been uploaded.
Verified private archive: 1,790,494,720 bytes,
1,332 files;
SHA256 `b03bf4b270ecf304cd1a8795ed396f93d59267cf610e42d5e193db4f62519ac5`.
All `archive_member` references in the JSON are relative private-archive members,
not public files or host paths. The compact repository core supports hash and
identity consistency checks, not raw-report replay without the archive. Scanner
binaries and database payloads remain separately retained with hash-bound
descriptors; the archive alone cannot perform a fresh scan.
Fresh Grype DB built `2026-10-24T17:45:29Z` retains default 120-hour age validation;
old snapshots, failed attempts and passed compatibility proof remain preserved.
No final-image runtime, native/JNI or Kafka/LZ4 campaign, Suite L5, exploitability
or source-release acceptance is established. Feed/native/coordinate gaps remain explicit.

## Reproduction Boundary

A clean clone can run the normal Python policy tests and compare each file in
`core-manifest.json` to its recorded SHA-256 and size. With the private archive,
verify its descriptor hash first, then compare regular-member hashes against
its `FILES.json`; do not extract untrusted absolute, traversal, link or device
members. Every retained member was independently rehashed during packaging.
Actual scan re-execution additionally requires the separately retained pinned
tools and database payloads; database freshness is not bypassed to replay an
expired snapshot. This overlay is not a new general-purpose campaign harness.

Failed or interrupted observations remain separate from the passed proof. The
first builder image was reused without rebuilding. One missing exact pinned
Docker reference was restored before an affected-only infrastructure retry.
Scanner scratch-cache links were excluded from the archive; their database
payloads are separately retained. Original evidence and archives were not
modified. Automatic hosted CI and independent exact-head review are reported
with the PR, separately from these local generator-bound executions.
