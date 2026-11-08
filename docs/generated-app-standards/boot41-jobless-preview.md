# Boot 4.1 Fresh Application Defaults

The existing three ordinary `target_profile` IDs now select Spring Boot
**4.1.1** for fresh CRUD (jobless or supported Batch), inbound/outbound bounded
SOAP, passthrough, plain/request-reply/retry-DLQ Kafka, routers and mixed routes.
The three former `-boot41-preview` aliases are retired and receive the normal
unsupported-profile diagnostic. Manifest stays 2.0; no public Boot 3 IDs are supplied.

| Supported ordinary profile | Runtime setting | Generated-app Java release |
| --- | --- | --- |
| `springboot-legacy-compatible` | H2, legacy test-console intent | 17 |
| `springboot-enterprise-postgres-java17` | PostgreSQL, no test console | 17 |
| `springboot-standard-enterprise` | PostgreSQL, no test console | 21 |

The baseline admits fresh CRUD M5a staging jobs and ordinary file/staging
jobs, including inferred file mappings and separate ordinary/M5a jobs in one
application. A single M5a job cannot also emit files. Jobless output contains
neither Batch dependencies nor dormant Batch configuration. SOAP
and CRUD use their existing Flyway migrations and Hibernate validation. A
passthrough router has no datasource: its PostgreSQL-named profile inherits
other profile intentions, **not** a PostgreSQL runtime dependency.

## Dependency Policy

New provenance records identify `ef-v5-maven-1`. Its immutable checked-in
definition is [dependency_policy.py](../../appbuilder/generation/dependency_policy.py):
Boot 4.1.1, aligned Tomcat 11.0.26, Jackson 3.1.7, Jackson 2.21.7 (applicable
test graphs only), annotations 2.21, Batch 6.0.5 (jobs only), router validator
3.0.6 (routers only), and explicitly managed Kafka-only LZ4 1.11.4. Boot does
not manage LZ4. The policy ID identifies emission, not external database state.
Manifest 2.0, provenance 1.0 and schema-baseline 1.0 remain separate contracts.
Profile/run/source identities remain in the surrounding generated artifacts.

v5 is the first supported generated-app baseline. Pre-v5 output and Batch
history migration are unsupported: regenerate into fresh output and provision
a separate fresh database, without deleting or resetting existing resources.
Future v5+ updates must support their applicable predecessor; that transition
is not designed by this correction. Same-policy generate/plan/apply preserve
existing migration bytes; the merged POM/durable-evidence guards remain.

The generated-app CI adds one actual LZ4-compressed Kafka roundtrip on Java
17 and 21, linux/amd64, in the unchanged generated non-root Dockerfile. Its
receipt records JNI LZ4/XXHash implementations, native mappings, the initially
empty task-created extraction directory, file UID/inode/link count and bundled
resource digest. Java fallback fails. This is functional proof, not image
security clearance; other architectures/operating systems remain unassessed.
The probe explicitly invokes the library's native loader before Kafka selects
its fastest implementations: Boot's nested-JAR loader can otherwise select
Java implementations. This proves the native scenario, not that ordinary
deployment defaults force JNI; no Java fallback receives native proof credit.

```bash
python -m scripts.smoke.boot41_kafka_lz4_container_proof --work-dir "$NEW_LZ4_PROOF"
```

## Kafka Baseline

Kafka uses the Boot Kafka/web/Jackson starters, managed Spring Kafka **4.1.1**,
Kafka clients/broker **4.2.1** and Jackson **3.1.7**. Router applications alone add
NetworkNT **3.0.6**; its declared Jackson 3.1.4 is resolved to policy's 3.1.7.
Jackson annotations **2.21** is a compatibility artifact, not a Jackson 2 mapper.
The embedded-broker test graph also has Jackson 2.21.7 test-only modules;
they are absent from the packaged runtime.
The producer uses the supported Jackson 3 serializer and injected mapper, with
date arrays retained for the existing plain DTO wire contract. No database or
Batch is introduced, including on PostgreSQL-named profiles.

Router dialect selection remains explicit draft-07/2020-12, defaulting to
draft-07. Strict types, asserted formats, cached packaged schema resources and
local references remain; no new remote schema fetching is enabled. V1-V4 NACK
codes, structure, boundaries and reply/correlation rules are unchanged. The new
validator's observable diagnostics use JSON pointers and different required/enum
wording; the bounded proof retains the individual old/new reasons. Technical
DLQ stack traces reflect the new framework/parser, while original payload, key,
correlation and error routing remain. The individual observed diagnostic changes
are recorded in the [dated Kafka proof](../test-results/boot41-kafka-preview-2026-09-30.md).

At-least-once delivery and in-memory correlation/restart limitations remain.
There is no exactly-once or durable correlation claim. Evaluate fresh standalone
packages; this is not an existing-application migration or security clearance.

```bash
python -m scripts.smoke.boot41_kafka_preservation --work-dir "$PROOF_OUTPUT/new-default-proof"
python -m scripts.smoke.boot41_kafka_preview_proof \
  --java17-home "$JAVA17_HOME" --java21-home "$JAVA21_HOME" \
  --work-dir "$PROOF_OUTPUT/new-kafka-proof"
```

The proof uses disposable actual embedded brokers and isolated generated apps,
executes ordinary profiles and independent repeated runs, and inspects resolved dependency
graphs and source/JAR independence. It is not a full L5 or advisory assessment.
Kafka decimal comparisons check parsed **numeric values and JSON types**, not lexical number
formatting: `42.5` versus `42.50` is not distinguished. This is not proof of trailing-zero,
textual-scale or byte-for-byte decimal preservation.

## Fresh JDBC Batch Applications

All supported Boot 4.1 jobs use `spring-boot-starter-batch-jdbc`, the Boot **4.1.1** managed
Batch **6.0.5** JDBC repository/operator and default context serializer. No
`@EnableBatchProcessing` or custom Batch configuration disables Boot's JDBC
auto-configuration. The legacy chunk model is deliberately retained (deprecated
but available throughout Batch 6), not rewritten. Flyway alone owns metadata;
`spring.batch.jdbc.initialize-schema=never` prevents competing initialization.
The profile-specific internal record pins Batch 6.0.5 SQL, including
`BATCH_JOB_INSTANCE_SEQ`; Batch 5.1.2 SQL, fingerprints and migrations on Boot 3
are unchanged. The proof checks the SQL against the actual packaged artifact
(ignoring comments, whitespace and case of unquoted SQL keywords/identifiers).

M5a retains its closed HTTP request, sole identifying `runId`, non-identifying
`businessDate` authoritative from original durable parameters, exact UTF-16/physical storage bound, immutable
source precondition, unique upsert keys and non-destructive staging. Jackson 3
handles the actual MVC request. Completed/running runs return 409; running
diagnostics expose the actual repository state and require ownership review.
There is no automatic failure classification, recovery endpoint or abandonment.
See the [M5a contract](generated-app-staging-handoff-run-semantics-design.md).
Ordinary jobs remain bodyless and use their existing legacy run parameters;
they do not acquire M5a request/restart guarantees.

**Original durable date authority on Boot 3 and Boot 4.** The identity tasklet selects the lowest
positive persisted execution ID from complete retained Batch 5/6 history, validates typed parameters
and corroborating contexts, then compares the attempted date before staging. Missing frozen context
after an early crash is recovered only from valid original parameters; malformed/conflicting history
fails closed. Valid retained rejected dates cannot become authoritative or poison original-date
retries. Current M5a contract and durable restart behavior remain required;
historical Boot 3 byte preservation is not an acceptance gate.
The [new result](../test-results/m5a-early-crash-date-integrity-2026-10-02.md) records actual four-case
early-crash execution for [#321](https://github.com/santosh-sh/EdgeForge/issues/321); the original
failed CI and dated post-commit evidence remain historical. This relies on retained, untampered
history, not a recovery endpoint, automatic repair, abandonment or migration policy.

H2 history exists only within one JVM. PostgreSQL preserves completed history
and FAILED/STOPPED restart state across replacement within the same established
policy. Same-profile regeneration retains migration bytes and schema records.
A pre-v5 package/history transition is unsupported; use a separate fresh
package and database. A disposable old-schema fixture also refuses current
startup with unchanged business/Batch/Flyway records. This is not universal
existing-database detection, nor approval to attach, reset or migrate adopter data.

## Evaluation Boundary

Use **new, disposable databases** for this baseline. This work does not prove
or provide a Boot 3-to-4 upgrade, a migration of existing PostgreSQL/H2 data or
Batch history, or a procedure for changing a persistent application's profile.
Do not reset, abandon or attach an adopter database. Generated applications
remain standalone, but production deployment still requires the authenticated
gateway and protected application port described in each generated README.
This baseline is not release acceptance or a vulnerability-risk disposition.

### Batch Proof

```bash
python -m pytest tests/unit/test_boot41_batch_preview.py \
  tests/unit/test_m5a_s2_batch_identity.py tests/unit/test_m5a_s3_staging_idempotency.py \
  tests/unit/test_boot41_batch_guard.py tests/unit/test_boot41_batch_early_crash.py -q
python -m scripts.smoke.boot41_batch_preview_proof --mode h2 --java17-home "$JAVA17_HOME"
# Use the explicit disposable PostgreSQL variables below for the full proof:
python -m scripts.smoke.boot41_batch_preview_proof --mode full \
  --java17-home "$JAVA17_HOME" --java21-home "$JAVA21_HOME" \
  --work-dir "$PROOF_OUTPUT/new-batch-proof"
```

The full Batch mode builds/tests M5a, ordinary staging, CSV file and mixed apps
on all three ordinary IDs. It checks repository rows, Flyway repeat startup,
FAILED restart, concurrency and abrupt JVM death/replacement both **before**
and **after** identity commit on PostgreSQL Java 17/21. A disposable coordination
seam precedes the unchanged decision; exact source/diff/product/JAR hashes are
retained, and no seam is emitted into product apps. No historical Boot 3
full matrix is repeated for promotion.
The early barrier requires original typed durable parameters, absent frozen context, exactly the
STARTED identity step and no data work. Each case retains two crashes, four rejected changed dates,
and final original-date completion in the same instance; missing/malformed/conflicting and shuffled
history controls execute as actual Java tests. H2 checks the promoted line within one JVM only. STOPPED is an
explicit **test-only classification** of an inactive failed execution after
its owner JVM is confirmed gone; abrupt running state remains blocked until
separate test-only classification after owner verification. No such operation
is emitted into applications. Old-output refusal is established by bounded committed prepromotion fixtures,
not by relabeling current ordinary-ID builds as historical Boot 3. Missing services/tests fail, not skip.
`--case` permits bounded iteration; omit it for the complete proof. Public Maven
resolution is needed, but no advisory inventory is submitted. The optional new
work directory retains local applications/logs; its JSON receipt has no host paths.

Ordinary comparison substitutes only positive integer instance IDs and validated
ISO-local start times in successful trigger responses. Other response values,
types, errors and content-type parameters remain exact. CSV bytes differ only
at the validated resource UUID, checked exactly once. Actual staging values
(source UUID, payload, business date, status, row UUID and run/instance binding) are
asserted against JDBC on the promoted line. Legacy jobs have no M5a restart claim.
Generated-app CI executes this full proof on a disposable PostgreSQL service,
alongside the S1 H2 and existing generated security/runtime checks.
The [domain-name review correction](../test-results/boot41-batch-name-review-fix-2026-09-29.md)
records explicit framework selection and Boot 3/4 compilation controls for valid
`JobLauncher`/`JobExplorer` domain entities. The original
[dated Batch proof](../test-results/boot41-batch-preview-2026-09-28.md)
identifies the exact generator/proof revisions and retained machine receipt.
Current compiled controls also cover valid runnable `HashSet`, `JobExecution`,
`JobParameters` and `RuntimeException` domain entities against the new M5a history helper types, using
conditional exact qualification rather than rewriting domain names.

### Proof Safeguard And Upgrade Follow-ups

The Batch proof entry points and imported helpers explicitly refuse effective Python optimization
before generation/evidence/services/database work ([#322](https://github.com/santosh-sh/EdgeForge/issues/322)).
Do not use `-O`, `-OO` or an effective nonzero `PYTHONOPTIMIZE`; negative subprocess controls cover
both flags and levels 1/2/7. Unset, empty and `0` remain valid. Existing historical receipts used
unoptimized Python and remain unchanged.

The current router's generated `RoutingService` string extraction uses the deprecated Jackson
3.1.7 `JsonNode.isTextual()` and `JsonNode.asText()` compatibility aliases. These are the identified
API calls behind the router deprecation warning, not a Kafka contract failure. Review their
supported replacements and string/value behavior before the next dependency upgrade; no API or
runtime change is made here.

## Reproduce The Scoped Proof

From the Engine root, with dependencies installed and a Java 17 JDK:

```bash
python -m pytest tests/unit/test_boot41_preview.py -q
python -m scripts.smoke.boot41_preview_proof --mode h2 --java17-home "$JAVA17_HOME"
```

The H2 mode generates, repeats, builds and executes tests for jobless CRUD,
inbound SOAP, outbound SOAP and passthrough outputs. It packages each app,
checks source/JAR independence and compares live HTTP/SOAP/passthrough behavior
with separately generated ordinary-profile repeat controls. The output is a JSON receipt on
stdout; failures exit nonzero. Public Maven dependency resolution is required.

For the full local proof, provide Java 17 and 21 homes and an **explicit
disposable loopback PostgreSQL service** with permission to create/drop its own
databases:

```bash
export EDGEFORGE_BOOT41_PGHOST=127.0.0.1
export EDGEFORGE_BOOT41_PGPORT=5432
export EDGEFORGE_BOOT41_PGUSER=preview_user
export EDGEFORGE_BOOT41_PGPASSWORD='<disposable-test-password>'
python -m scripts.smoke.boot41_preview_proof --mode full \
  --java17-home "$JAVA17_HOME" --java21-home "$JAVA21_HOME"
```

The full mode covers all four fixtures across all three ordinary profiles,
including Java 17/21 PostgreSQL Maven tests. It runs fresh CRUD and inbound
SOAP services against real PostgreSQL on both JDKs, checking Flyway history,
Hibernate startup and REST write/read. The script creates randomly named
databases and drops only those it created; a missing service is a failure, not
a skip. Passthrough remains a datasource-free proof in every profile.

The comparison keeps route/method, status, security/content headers including
media-type parameters, JSON field types/values, validation errors, SOAP
namespace/envelope/action/fault and outbound-request structure. JSON object
member order is deliberately ignored: the selected contract does not require
it, and well-formed object values and types remain checked. The fixture's
created IDs must be canonical UUIDv4 strings. Only identified record/customer
ID fields, and the outbound SOAP acknowledgement's `id`, are substituted after
checking that reads, lists and acknowledgements refer to the resource created
in that run. Only top-level ISO-8601 UTC timestamps on error responses are
substituted; a field named `timestamp` elsewhere is preserved. XML namespace
prefix spelling and whitespace-only element indentation are ignored, while
meaningful text, child tails, missing fields and resolved SOAP fault-code
namespaces are compared. XML charset and other content-type parameters remain
checked. The selected passthrough fixture exercises a decimal amount; these
fixtures do not assert unrelated date/null contracts.

The promoted path deliberately retains Jackson 3 defaults rather than enabling
Jackson 2 compatibility defaults. On the selected H2 fixtures, valid MVC JSON
and passthrough outbound serialization/downstream deserialization preserve the
selected semantic contracts, although JSON key order can differ. A valid JSON
object followed by another object is malformed input: the historical Boot 3 result accepted it,
whereas ordinary Boot 4.1 return HTTP 400 on CRUD, SOAP REST and passthrough ingress.
The passthrough `RestTemplate` uses its own converters, not the MVC mapper;
with the same malformed downstream response the historical Boot 3 result returned 200, whereas ordinary Boot 4.1
return 500. This stricter rejection is an explicit Boot 4 input-hardening
choice, not evidence that malformed legacy payloads are compatible. Adopters
with such payloads must correct them or complete a separate compatibility
decision before use. Null-to-primitive and enum `toString()` differences are
documented upstream Jackson defaults but were not exercised by these selected
DTOs; no universal impact or clearance is claimed.
Existing pagination, request-validation and security-header runtime assertions
also run for ordinary profiles in generated-app CI. This proof separately checks
the inherited test-console status and absence of packaged console files for
enterprise profiles; the existing console transition test remains.

This scoped proof does not run Suite L5, the Maven vulnerability collector,
container operation or an existing-database migration. PostgreSQL Maven
package/test checks alone are not claimed as database runtime proof; only the
explicit fresh PostgreSQL runtime probes establish that narrower result.

## Retained Package Safety

Generation, plan and apply reconcile an existing explicit Boot parent POM,
optional `db/generation-provenance.json`, and retained internal Batch schema
before writes. Boot 3/Batch 5, missing/ambiguous POMs and conflicting durable
records refuse the transition. Catalog lookup of an old profile name is not
framework provenance. Existing generated Boot 3 apps remain standalone and are
not regenerated or migrated by this slice.

The retained Boot parent must exactly match the selected proven 4.1.1 baseline.
An unvalidated 4.1 patch is refused before writes, even when its provenance agrees
or is absent; regeneration must not silently downgrade its POM or retain false
framework provenance. No automatic patch migration is supplied.

Retained POM evidence must be a Maven project with single, nonempty scalar
project/parent identity declarations. Duplicate, missing, foreign or conflicting
identity declarations refuse before writes. Durable framework provenance and
schema-baseline JSON reject duplicate object keys at every nesting level rather
than keeping a last value. Apply rechecks this evidence even after a prior plan
was approved; contradictory mutations do not authorize regeneration.

Same-policy regeneration preserves migration bytes and original profile
labels/fingerprints in the schema baseline. New packages receive a minimal
framework provenance record with `dependency_policy: ef-v5-maven-1`. No tool can infer universal freshness of an external
database; use a separate fresh package and database, never reset or attach adopter
history. Captured prepromotion receipts are committed under
`tests/fixtures/boot41-promotion/`; normal regression tests need no Git history.
Source equivalence alone does not authorize reuse of runtime evidence: resolved
dependency identity and ordinary-ID applicability are also required. Promotion
uses fresh runtime execution rather than crediting source-only hashes.

The [review-fix proof](../test-results/boot41-jobless-preview-review-fixes-2026-09-27.md)
identifies the corrected comparator's tested Engine source commit. The
[first local proof](../test-results/boot41-jobless-preview-2026-09-27.md)
remains historical with its comparator limitations disclosed. Hosted CI status
belongs to the PR's checks on its reported head, not to either local record.
