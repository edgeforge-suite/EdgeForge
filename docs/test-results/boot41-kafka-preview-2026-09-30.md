# Boot 4.1 Kafka Preview Proof, 2026-09-30

Candidate: **EF-V5-M2-ENGINE-BOOT41-S3**, revision **1**.
Base: `584e4bf635ac12821496a52d20c3a03a6e73a92c` (#319 merged).
Locally tested generator/broker code: `80aa40ace3dd773acdb9474e27df4aee937c3d36`, clean worktree.
The later evidence/documentation/default-corpus-helper commit is not the generator
commit; it adds the combined plain/router preservation case without changing emitters.
Final local broker receipt time: `2026-09-30T21:23:38.319765+00:00`.

## Executed Proof

| Proof | Result |
| --- | --- |
| Focused Kafka/profile/security Python tests | 178 passed |
| Full Engine Python suite | 1,756 passed, 25 skipped (environment-gated proof; not passed by skipping) |
| Clean base/head default corpus | 27 byte-identical outputs: eight existing fixtures plus the combined plain/router proof input on all three existing profiles |
| Mixed Boot 3 controls and previews | Six builds, 14 executed tests each; zero failures/errors/skips |
| Separate plain and router preview packages | Six builds, one actual broker roundtrip each; zero failures/errors/skips |
| Total Maven proof | 12 builds, 90 executed tests; zero failures/errors/skips |
| Determinism/independence | Repeated mixed generation matched; all packages passed source/JAR boundary checks; build source hashes unchanged |
| Changed-file Ruff and diff hygiene | Passed |

The two Java 17 profiles used Temurin 17.0.18. The Java 21 profile used
OpenJDK 21.0.12.1. Maven was 3.9.12. Each generated test application started an
actual disposable KRaft broker and its own Spring application, without Engine,
Studio or KS on its runtime classpath. Packaged HTTP actuator/security proof and
unchanged S1/S2 matrices are executed by generated-app CI, not claimed from the
local broker run. CI must pass on the reported final PR head before handoff.

Mixed proof includes all four plain routes, two request/reply adapters and a
router with two downstream targets and header/body extraction. It compares 19
actual Kafka observations per profile pair: topic, key, all headers, correlation,
JSON values/types, decimal conversion, date arrays, explicit null, transformations,
NACK structure/codes/boundaries and original technical DLQ payload. Missing source
and invalid reply destination fail before downstream publication. V1-V4 reject
invalid payloads; successful roundtrips traverse all four boundaries. Duplicate
correlation and timeout retain their distinct codes. Technical malformed JSON
traverses the configured retry/DLQ path, not the business NACK path. DLQ original
topic, partition, offset and timestamp are checked against actual producer metadata.

The broker schemas exercise explicit draft-07, explicit 2020-12 and missing-dialect
fallback. Additional generated-validator tests exercise valid/invalid date formats,
strict number types and packaged in-document references under each dialect. They
are service-level checks, not additional Kafka observations or cross-file-reference
coverage. No new remote schema fetching is enabled.

## Resolved Dependency Boundary

Effective POMs and dependency trees were inspected for all nine preview packages.
Boot is **4.1.1**; Spring Kafka is **4.1.1**; Kafka client and test broker are
**4.2.1**. Router packages alone include NetworkNT **3.0.6**. Boot management
resolves its declared Jackson 3.1.4 to **3.1.5** for core, databind and YAML.
No family override or Jackson 2 bridge was added.

The packaged compatibility annotation artifact is Jackson annotations **2.21**
(the Jackson 2.21.5 BOM independently pins annotations to 2.21). The broker-test
graph also contains Jackson 2 **2.21.5** core/databind/dataformat modules at **test**
scope. Packaged JAR inspection excludes Jackson 2 core/databind, Batch, H2 and
PostgreSQL, and application startup asserts no datasource or Batch repository.
Plain packages have no unused router validator. The Boot 3 controls retain
Spring Kafka **3.2.4**, Kafka **3.7.1**, Jackson **2.17.2**, and router validator
**1.0.87**. The unchanged defaults are not a current security-clearance claim.

Public primary-source inspection used the exact Boot 4.1.1 and NetworkNT 3.0.6
POMs and released source artifacts, plus Jackson's 3.1.5 release record. Its
recorded CVE-2026-59889 fix applies to the selected Jackson patch, not blanket
vulnerability clearance for this graph. No private inventory/advisory submission
or full Maven assessment was performed.

## Observable Diagnostic Differences

Every NACK field remains compared except the narrowly validated timestamp.
The comparator accepts only these exact fixture-specific V1-V4 old/new reason
pairs; an unexpected reason fails. Complete raw reasons and stack traces remain
in the receipt, rather than being removed from evidence.

| Case | Boot 3 diagnostic detail | Preview diagnostic detail |
| --- | --- | --- |
| V1, missing status | `$.status: is missing but it is required` | `: required property 'status' not found` |
| V2, minimum amount | `$.amount: must have a minimum value of 1` | `/amount: must have a minimum value of 1` |
| V3, processor status enum | `$.processorStatus` with unquoted enum members | `/processorStatus` with quoted enum members |
| V4, outbound status pattern | `$.status: does not match the regex pattern ^(APPROVED\|DECLINED)$` | `/status: does not match the regex pattern ^(APPROVED\|DECLINED)$` |

The schema path/boundary prefix is retained for every reason. The technical DLQ
stack changes framework frames and parser cause from Jackson 2
`JsonParseException` to Jackson 3 `StreamReadException`, including source-location
wording. Both retain the wrapper/cause identity and malformed-token diagnostic;
exception message, original payload, topic/key/correlation and remaining headers
are still compared. Full stack differences are retained individually in each
pair's diagnostic ledger.

Only validated NACK instants and the DLQ's validated, propagation-checked original
broker timestamp are normalized. JSON object order is ignored; no payload fields,
arbitrary headers, correlation IDs or error codes are dropped. Negative controls
reject changed destination, key, correlation, value/type, boolean-to-number,
error code, extra payload fields and unexpected reason text. Missing/all-skipped/
failed test receipts fail proof.

## Reproduction and Receipt Identities

From the Engine checkout, with explicit installed JDK homes and a fresh output
directory for each invocation:

```bash
python -m pytest tests/unit/test_boot41_kafka_preview.py \
  tests/unit/test_boot41_preview.py tests/unit/test_kafka_emitter.py \
  tests/unit/test_kafka_build_emitter.py tests/unit/test_kafka_router_components.py \
  tests/unit/test_security_headers_emitter.py -q
python -m pytest -q
python -m scripts.smoke.boot41_kafka_preservation --work-dir "$PROOF_OUTPUT/default-proof"
python -m scripts.smoke.boot41_kafka_preview_proof \
  --java17-home "$JAVA17_HOME" --java21-home "$JAVA21_HOME" \
  --work-dir "$PROOF_OUTPUT/kafka-proof" --maven-repo "$TASK_MAVEN_CACHE"
```

Local raw broker receipt SHA-256:
`ec5800799c3ba5120b91c2915a38fae2ae56a5a3e14f2d1279fd22036afc2056`.
Default corpus receipt SHA-256:
`88b8377d3f4470425e57197428abd17fa7ee9e3c9f13e91ab23cd64c0b3d56a5`.
Large generated apps, Maven logs, dependency trees and broker observations stay
outside Git. The CI `boot41-kafka-proof` artifact retains its own receipts/logs;
volatile timestamps/stacks mean a later run need not reproduce the raw receipt hash.

## Limits

The first exact-head generated-app run failed in the unchanged S2 crash helper
before a committed identity boundary had been observed, so its later Kafka/default
steps were skipped. The authorized proof-only amendment and separately preserved
failed observation are recorded in
[Batch crash-boundary correction](boot41-batch-crash-boundary-2026-10-01.md).
That correction does not approve behavior before the identity commit or change
generated Batch behavior. Final handoff requires actual successful amended-head
CI execution, not the earlier skipped steps.

This supplies opt-in fresh-application Kafka compatibility only. Boot 3 remains
the default. At-least-once and in-memory correlation/restart limitations remain;
no exactly-once or durable correlation is claimed. Deployment still requires the
authenticated gateway/protected port. No adopter application/database migration,
default switch, full L5, image assessment, full Maven advisory matrix, risk
acceptance, tag or release is established. Maven remediation and M2 remain open.
Docs impact: updated.
