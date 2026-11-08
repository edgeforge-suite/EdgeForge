# Noble Findings: 2026-10-20

**Assessment/reconciliation complete; all 622 scan records OPEN.** Actual ledger:
622 normalized records / 22,740 repeated observations (Grype 16,590; Trivy 6,150),
not unique CVEs. Counts below are recomputed from the completed published ledger,
not inferred from the old assessment. All findings remain visible.

| Physical Surface / Catalog Type | Observations | Engine-Owned Next Decision |
| --- | ---: | --- |
| Build OS (`deb` / `ubuntu`) | 18,060 (13,410 / 4,650) | Reconcile actual package/vendor backports, fix evidence and build-time exposure before separately scoped action. |
| Build Java cache (`java-archive` / `jar`) | 60 (30 / 30) | Clean-plugin Plexus Utils 4.0.2 remains OPEN; confirm owning-realm action and compatible proof separately. Compiler correction is not family-wide remediation. |
| Final OS (`deb` / `ubuntu`) | 4,620 (3,150 / 1,470) | Reconcile runtime-base vendor status/freshness; missing fixes are not acceptance. |

Plexus observations retain Grype `GHSA-6fmv-xxpf-w3cw` (High, fix 4.0.3) and
Trivy `CVE-2025-67030` (HIGH, fixes 4.0.3 / 3.6.1), each across 30 builders.
These are retained scanner identities/fix observations, not an approved override
or proof of vulnerable-function use. Cache deletion cannot dispose of the finding.
No final Java or Go-type matches occur in this ledger; this is dated scanner
coverage, not universal Java/native/JDK/plugin clearance or historical closure.

## Completed Reconciliation

The reconciler completed with expected exit 1 (OPEN), not incomplete exit 2.
The separate dated Maven API report also completed with exit 1:

| Dated Maven Ledger | Disposition | Rows |
| --- | --- | ---: |
| Historical mappings | REMEDIATED_VERSION | 18 |
| Vendor observations | SUPPORTED_VERSION_DISPOSITION | 27 |
| Vendor observations | OPEN | 6 |

That dated six-OPEN result is preserved separately from the five new
technical adoptions below. Neither report overwrites the other.

All 2,186 historical records, 64,720 observations and 3,990 COPY entries remain
accounted for without rewriting original dispositions or receipt bytes.

| Historical Family | Records | Observations |
| --- | ---: | ---: |
| BUILD_JDK | 61 | 910 |
| BUILD_MAVEN | 24 | 780 |
| BUILD_OS | 1,886 | 56,580 |
| FINAL_GO_PEBBLE | 26 | 780 |
| FINAL_OS | 189 | 5,670 |

| Current Copy Disposition | Entries |
| --- | ---: |
| OPEN | 3,780 |
| current-copy-observed | 210 |

A current observed copy is not historical closure or permission to delete evidence.
The [core accounting projection](residual-accounting.json.gz) enumerates all
2,186 record IDs / 3,990 COPY IDs / 22,740 current observations through
IDs, hashes, coverage and status; it is explicitly not the full lossless map.
Full archive-only member: `reconciliation/residual-history-map.json.gz`
(143,718,022 raw bytes / 16,327,562 gzip bytes;
gzip SHA-256 `df436bcf10010d0ef164ed051f4559c599140aac8e40f0a5ac6917febedbfc0b`). No repository link is implied.

### Six Vendor Rows

| Advisory | Affected Range | Fix Floor | Installed | Technical Result |
| --- | --- | --- | --- | --- |
| GHSA-343h-94h5-c4wr | `<= 1.11.3` | 1.11.4 | 1.11.4 | Verified outside affected range |
| GHSA-4v53-57pg-c464 | `<= 1.11.1` | 1.11.2 | 1.11.4 | Verified outside affected range |
| GHSA-6cx8-rjf8-pr8g | `<= 1.11.1` | 1.11.2 | 1.11.4 | Verified outside affected range |
| GHSA-gm45-99xc-r7wv | `<= 1.11.3` | 1.11.4 | 1.11.4 | Verified outside affected range |
| GHSA-mcr4-qmvw-px4g | `<= 1.11.3` | 1.11.4 | 1.11.4 | Verified outside affected range |
| GHSA-5gvw-p9qm-jgwh | Inclusive Jackson range contradiction | Unresolved | Runtime 3.1.7 / test-only 2.21.7 distinct | OPEN; no adoption/waiver |

Five separate technical adoptions bind each advisory to 18 actual case/stage
observations (9 Kafka-family cases, both stages), coordinate
`at.yawk.lz4:lz4-java:1.11.4` and packaged-JAR SHA-256
`58c8e0b813960d2a248e050c353baea73139b48a2ffc55382d42c69707e17325`.
The original tool rows remain `supported-candidate/OPEN`; their statuses and
all historical dispositions are unchanged. The technical decision is recorded
separately in the [adoption ledger](residual-applicability-adoption.json.gz),
not inferred from feed lookup absence, runtime behavior or a version alone.
Jackson remains OPEN for authoritative inclusive-range resolution; test-only
scope is no waiver. Native and broader feed coverage remain OPEN, as do default/
JNI behavior-to-JAR hash limitations. These adoptions do not imply native
clearance, risk acceptance, an upgrade or runtime-to-production byte identity.

## Proof And Disclosure Limits

Three exact production-image startups, separate default/native Java 17/21
instrumented proof images and 32 compatibility tests (6 emitted/26 proof-supplied)
are functional evidence. Exact image identities and private-original receipt
hashes are recorded in the dated README, not inferred from health checks.
Runtime JAR hash linkage is unavailable; a native `.so` hash is not its LZ4 JAR
hash. Native's pre-build baseline is instrumented, weaker than Default's separate
observer-only comparison. No runtime-to-production byte-identity claim follows.

New proof-summary publication is DERIVED. Original-private hashes and lossless
path/hash arrays remain distinct from sanitized outputs; synthetic-correlation
placeholders are disclosed, without scan exceptions or finding suppression.
Zero matches or supported version applicability is not risk acceptance, M2,
independent approval or release clearance. Only actual OPEN residuals need owner
decisions; no new pin-versus-float decision or fortnightly refresh SLA is created.
