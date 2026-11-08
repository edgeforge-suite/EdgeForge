# Generated Image Assessment: 2026-10-20 Noble

**Public-retention revision 2; unchanged assessed inputs and findings.** The
original reviewed #333 head is `c512e4754fe2bf1f00e18968566bbb5e1802693d`.
This clean replacement preserves its production implementation and existing
assessment/runtime proof; it does not introduce a new scan or runtime campaign.
The assessed generator remains c879827 below, not the later packaging/CI head.
Complete vendor advisory bodies are now archive-only; the public
[vendor projection](residual-vendor-current.json.gz) retains the six identities,
source attribution/URLs/dates, ranges, contradictions and installed bindings.
Its source fingerprints bind unchanged full records. No third-party licence or
public archive distribution decision is made here.

**30 cases / 60 stages complete; findings OPEN.** The assessment contains 622
normalized records and 22,740 repeated observations: 16,590 Grype and 6,150 Trivy.
These are not unique CVEs. No risk acceptance, M2 or release clearance follows.
Reconciliation completed with expected OPEN outcome (exit 1). All 622 scan records remain OPEN.
The dated Maven API report separately retains 18 `REMEDIATED_VERSION` mappings,
27 `SUPPORTED_VERSION_DISPOSITION` vendor rows and 6 OPEN vendor rows. Five new
technical LZ4 adoptions do not rewrite that dated six-OPEN result.

## Source And Qualification

Assessed generator: `c8798275065a8a0b619046707fad053f8a9b9ad1`, based on
`dac4a9d7178dd024ac7581f32777e1dfd861b657`. Assessment UTC:
2026-10-20T04:30:55.017678Z through 05:46:06.228403Z. Ordinal 11 supplied five
completed pairs; missing-only invocations 12..36 supplied 25 cases. Original
exit-2 fragments remain partial; validation completed only the assembled 30/60.

Publication replay ran 14:10:12.279528Z through 14:20:57.728602Z on October 20
using tooling `5a96193d5e2bf582a087b8bc6532e7e608f9612b`; input files unchanged,
zero repeated scans/runtime proofs. That later tooling is not the generator.
Repository validation at `e269fb002cfa3e228f83078b25bfede046199a30` passed 4,317
tests with 25 skips and 18 subtests; it is not final-head CI or independent review.

Noble qualification used Ubuntu 24.04, linux/amd64 on an ARM64 host under
emulation, Maven 3.9.16 and actual Java 17.0.20.1 / 21.0.12.1. The selected pins
are multi-platform indexes, not child manifests:

| Selection | Index Digest (SHA-256) |
| --- | --- |
| Maven 3.9.16 Java 17 Noble | `1a352420f7aba21f5ad08df31bab55f74c013fb491f1ae8ab1dd7ff9ed698584` |
| Maven 3.9.16 Java 21 Noble | `99e61abcff91a9b1333463bd8451fb18495d6eba9250ac66a338b518f8278320` |
| Temurin 17.0.20.1_1 JRE Noble | `07fa0356cf354c5252947575f42ed42aa6fd921f36438b7bc77ad81c31c537dd` |
| Temurin 21.0.12.1_1 JRE Noble | `35501d3f93173b420ac9001658eb68157e813316b865087e345c187fca422c4c` |

The retained PRIVATE-ORIGINAL qualification record binds actual amd64 child/config/
rootfs and inventories; its SHA-256 is
`e294312ffb60f8cd99670a141e1c80cf080d712ee0bdb81a2e6910b65c6a40ac`.
The redacted core qualification record has separate published hashes recorded in
the publication index; the private-original hash is not its published payload hash.
It qualified candidates from base dac4a9d, before c879 generation; it claims no
application startup, zero vulnerabilities or qualification of other platforms.

## Exact Runtime Identities

All three representative production startups passed health UP, UID 999, generated
default entrypoint/user and schema settings. CRUD additionally passed the bounded
read-only list request. Assessed configuration ID and loaded Docker ID are distinct:

| Production Case | Assessed Image ID (`sha256:`) | Loaded Docker Image ID (`sha256:`) |
| --- | --- | --- |
| crud-h2-j17 | `7f524bc2f6255e3647c7fefde46c4d4076110074b8706ab6f5df105abf34773d` | `9727393672275914bbb3966bc1f86a7a4fc38f3c881dc66faaf238c79112c284` |
| passthrough-pg-j21 | `b0256a462db48a8c0b0757f8371c1a203e3f8e7265b594ee53d6014265de8c77` | `84f34def6ef245dcfe8d8febff89baa92cad1b8ca29b863bae23e2aca31b7a92` |
| kafka-router-h2-j17 | `0b4fe99c056a4d7b9c5c2ba9a5746738416015ca78f46591111f7fdff4fe9721` | `f734dd91dff4c7016b9e9ea1ccda852c5cce9d95597580e85f8e145476fb3f1f` |

Separate instrumented Kafka proof images passed with actual Java 17.0.20.1 /
21.0.12.1, UID 999, linux/amd64. These are not the production images above:

| Mode / Java | Proof Image ID (`sha256:`) |
| --- | --- |
| Default / 17 | `6670979d174f75217439e3822b161aab53a23e5a059c2c0e2f0edbcf162ff889` |
| Default / 21 | `7b0399630040f3c26985fe454320e971c663889a3fcec260fea6a3eb5672ca48` |
| Forced native / 17 | `51a0b983319c111efb91edeb284af200fdf9eae035dd67f8b4b442c06b9c9925` |
| Forced native / 21 | `559c963c7b9ff6169863406a10ffcda8ef56b43235b4938c0dbf51b8242f9fbd` |

Default is ordinary `java -jar`, JavaSafe LZ4 / JavaUnsafe XXHash, default level 9,
no forced native loading, correlated Kafka mapping and null round-robin output
key. Forced Native.load/PropertiesLauncher JNI roundtrip is separate credit.
Native's retained pre-build inventory is already instrumented; Default has the
stronger observer-only pristine comparison. Runtime LZ4 JAR SHA was not retained;
version/origin and extracted `.so` hash cannot prove production JAR byte identity.

Compatibility ordinal 7 reconstructs 32 tests: 6 Engine-emitted and 26 proof-supplied
unit/contract/configuration tests, 8 cases (3 reused/5 fresh), zero failures/errors/
skips. Skipped-test image packaging is not executed-test credit. Neither three
startups nor four Kafka proof cases certify all application behavior/security.

## Disclosure And Remaining Work

New proof summaries are **DERIVED**, not raw runtime receipts. Private-original
compatibility/default/native receipt SHA-256s remain respectively:
`6cea2da88901a9b3d56b03984b6809d331c39f94f8624f7c91fb6f818e7035d2`,
`0b6c10bdb239f5e2cab1a7bf6f449c380778f38c1d0cec792f08a4825d643962`,
`e43af85b821d836d9be074a055c79d203993d750e9621ae036a6ab22770dade5`.
The retained private summary hash is `06418b47d69a3d68cf9376a6dafb2e082be6e63e2f2d354ea2cab969e3e59242`;
its derived publication projection hash is `c07cf14d42c9f1d292f911f4b78a012a5ce9dcb9e25a75aa74e0bdecd9b57cd1`.
Lossless path/hash arrays retain input identities; labelled synthetic-correlation
placeholders avoid false positives without scanner exceptions or suppressions.

See [findings](findings.md) and [storage](../2026-10-20-noble-storage.md).
Historical 2,186 records / 64,720 observations / 3,990 copies are accounted for,
not rewritten. The [core accounting projection](residual-accounting.json.gz)
enumerates all historical record/COPY IDs and 22,740 current observations by
IDs/hashes/coverage/status. It is not a lossless replacement for archive-only
`reconciliation/residual-history-map.json.gz`. Five technical LZ4 applicability
adoptions are separate from unchanged OPEN tool statuses and risk acceptance.
Final archive metadata belongs only in the external verified manifest. Three private
production exports are retained; 57 removals have receipts. Full publication
replay needs private originals AND the private archive, not a clean clone alone.
No universal image replay. Base review precedes release selection and follows
material security changes; no fortnightly service or new pin-versus-float decision.

## Retention And Replay Boundaries

The replay-command projection uses portable `python3`. The historical replay
receipt did not record an interpreter version or executable hash; those remain
unknown, not inferred from the current environment. The original sanitized
command/receipt remains unchanged in the private archive.

The original reconciliation receipt has 767 inputs; a fresh offline public-CLI
replay has 747. [Replay context](reconciliation-replay-context.json.gz) records
the verified private wrapper hash and all twenty additional pre-verified inputs.
The lossless history map reproduces byte-identically and vendor values are
unchanged, but the public CLI alone does not reproduce the wrapper receipt.

Repository-only verification checks internal consistency. Reviewed source
identity and archive verification provide additional assurance; neither is
release acceptance. See the [maintainer tool map](../../generated-image-maintainer-tools.md)
and [storage note](../2026-10-20-noble-storage.md) for exact commands, source
bindings and clean-clone/private-archive/private-original boundaries. #333 and
its GitHub refs remain reachable; avoiding its advisory-core commit in this
replacement history does not erase prior uploads or authorize publication.
