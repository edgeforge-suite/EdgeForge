# Remaining Findings And Decisions

All image findings are **OPEN**, owned by Engine. Assessment completion does not
accept risk or establish M2/release clearance. The [full ledger](open-findings.json.gz)
enumerates every exact advisory/package/version/severity/fix record and affected
case/stage observation. There are 2,186 normalized records and 64,720 observations,
not that many unique vulnerabilities. The rows below account for all observations;
scope means physical residence, not proven invocation, reachability or exploitability.

| Family | Affected surfaces and actual evidence | Engine-owned next decision |
| --- | --- | --- |
| Build OS: 56,580 observations | All 30 builders, Ubuntu 24.04. Includes binutils 2.42, curl 8.5.0, OpenSSL 3.0.13, Git 2.43.0, GnuPG 2.4.4, OpenSSH 9.6p1 with recorded distro revisions. | Build-image owner: reconcile vendor patch/backport status and build-time exposure, then propose a bounded compatible builder-base change. No automatic change here. |
| Build JDK: 910 | Grype CPE/binary matches: 20 J17 images at `17.0.15+6`; ten J21 at `21.0.7+6-LTS`. 61 exact records across the two branches. | Build-platform owner: verify vendor-specific affectedness and reported fix branches. Trivy's missing matches do not clear Grype's findings. |
| Build Maven/tooling/cache: 780 | Both scanners find older Plexus Utils (3.5.1/3.6.0/4.0.2), Commons IO 2.11.0, Commons Lang3 3.16.0 and Jackson 3.1.5. Distribution and cache copies are retained separately; these are not those versions in the final app. | Build-tooling owner: identify the introducing distribution/plugin edges and select a separately authorized compatible correction. Cache presence does not prove plugin execution or test-only usage. |
| Final OS: 5,670 | All 30 finals, Ubuntu 26.04. Includes rust-coreutils `0.10.0-1ubuntu2~26.04.1`, libc6 `2.43-2ubuntu2.4`, PCRE2 `10.46-1build1`, Perl, GnuTLS, Expat and util-linux. Binary packages can share source advisories. | Runtime-base owner: reconcile vendor status and base freshness before proposing remediation. Empty fixes or wont-fix statuses are not acceptance. |
| Final Go/Pebble: 780 | All 30 finals contain `/usr/bin/pebble`, Go 1.27.1. Thirteen explicit GO/CVE alias pairs per scanner; this is base-image code, not an Engine Go dependency. | Runtime-base owner: establish vendor build/applicability and compatible patch options. Do not infer vulnerable-function use from health success or discard the binary as unrelated to Java. |
| Per-app Maven/test-classifier paths: zero reported matches | All hash-bound packaged dependencies and represented per-app scopes, including both Kafka 4.2.1 test-classifier JARs in nine Kafka-family builders. | Dependency owner: retain dated no-match limits and the separate historical/vendor dispositions below. No universal Java/native clearance. |

The two Grype Critical Go records are **GO-2026-6604 / CVE-2026-56857** and
**GO-2026-6612 / CVE-2026-78663**. Their 60 repeated Critical observations are
not 60 different Critical issues. Trivy reports Low and Medium respectively.
Both severities remain visible. Trivy lists 1.26.9/1.27.2 fix branches; Grype's
listed branches differ for some Go records. No branch downgrade or severity
preference is selected. Unknown severity (for example CVE-2026-97030) stays unknown.

Twenty-four explicitly alias-matched package/version pairs have differing fix
sets: 19 build and five final Go pairs. Some are alternate branches, not a true
contradiction. OpenSSH CVE-2026-106552 illustrates fix-availability disagreement:
Trivy lists distro fix `1:9.6p1-3ubuntu13.20`, while Grype lists no fixed version.
Plexus reports branch-specific 3.6.1 / 4.0.3 fixes; Commons IO and Lang3 report
2.14.0 / 3.18.0. These are scanner observations, not approved upgrade instructions.

## Maven And Vendor Ledger

[Reconciliation](maven-reconciliation.json) enumerates all 18 historical mappings
and all 33 retained vendor identities/branches against current resolved scope and
30 actual packaged inventories. Eighteen have supported version-remediation
evidence; 27 vendor records have supported version/scope dispositions. They are
not closed merely because the newer image scan has zero Java matches.

Six vendor identities remain OPEN, each with an Engine maintainer and next decision:

| Identity | Unresolved evidence | Required next decision |
| --- | --- | --- |
| GHSA-5gvw-p9qm-jgwh | Inclusive `<= 2.22.0` affected range conflicts with the 2.22.0 fix floor; represented Jackson 2 scope is test-only, not final runtime. Jackson 3's retained fix floor is 3.1.5, not 3.1.4. | Seek corrected source/range evidence or bounded applicability proof. Test-only classification is not a waiver. |
| GHSA-343h-94h5-c4wr, GHSA-4v53-57pg-c464, GHSA-6cx8-rjf8-pr8g, GHSA-gm45-99xc-r7wv, GHSA-mcr4-qmvw-px4g | Five enumerated retained vendor/feed gaps; the dated global/OSV lookups returned 404. | Obtain corrected upstream/feed evidence or commission bounded applicability proof. Missing feed entries do not clear the vendor observations. |

The original vendor payloads, timestamps and historical evidence remain unchanged.
This reconciliation is local analysis of dated bytes, not a fresh Maven advisory
campaign, current upstream assertion, exploitability conclusion or risk acceptance.

## Coverage Limits And Policy Decisions

Three explicitly recorded non-per-app cache-coordinate gaps remain: two
`javax.inject-1.jar` copies (Maven distribution/cache) and cached
`surefire-shared-utils-3.5.6.jar`. Their bytes/hashes and original inferred-coordinate
gaps remain retained. A missing required per-app or Kafka test-classifier component
cannot be relabelled as one of these exclusions.

Nine Kafka-family cases each enumerate 52 native members in both stages, including
lz4-java 1.11.4, snappy-java 1.1.10.7 and zstd-jni 1.5.6-10 assets. Hashes prove
physical bundled bytes, not exhaustive native advisory identification or loading.
Unlabelled embedded code, dynamically fetched plugins, exact plugin execution,
vendor JDK mappings and reachability remain limited. Final J17/J21 versions are
17.0.20.1 / 21.0.12.1; absence of final JDK matches is not exhaustive feed coverage.

Maintainer decisions remain: separately scope any builder/runtime base or tooling
remediation, resolve the six vendor issues, and choose digest pinning versus an
explicitly owned floating-reference/refresh policy. All resolved base digests and
actual image identities are already recorded. No policy change, suppression,
blanket clearance or follow-on implementation is authorized by this record.
