# Boot 4.1 Jobless Preview: Local Proof (2026-09-27)

> **Historical comparator limitation.** This first receipt predates the
> [review-fix proof](boot41-jobless-preview-review-fixes-2026-09-27.md).
> Its comparator replaced truthy ID fields without checking resource identity,
> stripped XML text, omitted child tails and QName namespace bindings, ignored
> content-type parameters, and compared JSON objects without member order.
> Its successful comparisons therefore do not establish those properties.
> The later proof reruns the matrix with explicit checks.

**Candidate:** EF-V5-M2-ENGINE-BOOT41-S1, revision 1. **Starting Engine main:**
`fad1e1a5cb8baaeb7719c1d9c4dbc4cda77d90f9`. **Tested source commit:**
`6c347dfe4c13bb97ece4d6aecdce873a26203a5f`. This record is a later,
documentation-only evidence commit; its own SHA was **not** the source under
test. The tested source selected the published OSS Boot 4.1.1 BOM; that BOM
manages Batch 6.0.5, but no Batch dependency was included in a preview app.

## Scope and Result

The existing committed fixtures were jobless and unmodified: CI-smoke CRUD,
canonical inbound SOAP customer service, canonical outbound SOAP client and
country-router passthrough. For each of the four, the full proof generated and
repeated output on all three preview profiles, ran `mvn clean verify`, required
at least one executed test, and checked standalone source and packaged JAR
independence. Result: **12 of 12 preview builds passed; 12 executed generated
`@SpringBootTest contextLoads()` tests (one per preview build), zero failures
or skips**. These context starts are distinct from the live functional wire
assertions below. Boot 3 controls were independently generated
and built on H2/Java 17: three generated tests executed across CRUD and SOAP;
the existing passthrough control emits no generated test and is recorded as
zero, not as a test pass.

| Preview profile | Java | CRUD | SOAP inbound | SOAP outbound | Passthrough |
| --- | --- | --- | --- | --- | --- |
| `springboot-legacy-compatible-boot41-preview` | 17 | H2 build/test + live write/read | H2 build/test + live write/read | H2 build/test + live call | No DB; build/test + live route |
| `springboot-enterprise-postgres-java17-boot41-preview` | 17 | PostgreSQL build/test + live write/read | PostgreSQL build/test + live write/read | PostgreSQL build/test | No DB; build/test |
| `springboot-standard-enterprise-boot41-preview` | 21 | PostgreSQL build/test + live write/read | PostgreSQL build/test + live write/read | PostgreSQL build/test | No DB; build/test |

The local full command returned **0**. It used OpenJDK **17.0.18** and
**21.0.12.1**, Maven **3.9.12**, and a task-owned, loopback PostgreSQL
**16.13** service with disposable databases. The reusable command and
required database environment are in the [preview guide](../generated-app-standards/boot41-jobless-preview.md#reproduce-the-scoped-proof).
The generated-app proof itself requires the service; it has no skip-success
path for an unavailable PostgreSQL server.

Four H2 wire comparisons against separately running Boot 3 controls passed:
CRUD, inbound SOAP, outbound SOAP and passthrough. The comparisons covered
routes/methods, statuses, selected security/content headers, payload field
types/values, validation errors, SOAP namespaces/actions/envelope/fault and
outbound bodies. The selected passthrough contract exercised a decimal amount
(`42.5`); these selected fixtures do not establish unrelated date/null
contracts. The comparator's actual normalization limitations are noted above.
The local downstream accepted
both content-length and chunked requests. Existing pagination,
passthrough-validation and security-header runtime tests passed on original
and preview lines (**14 passed**); the existing default-line console-transition
runtime test passed (**1 passed**). Preview enterprise JARs contained no demo
controller/static console and their live console route returned 404.

Four fresh PostgreSQL runtimes passed: CRUD and inbound SOAP on Java 17 and
Java 21. They showed Flyway history (`1,2` for CRUD; `1` for inbound SOAP),
Hibernate EntityManager initialization, and REST write/read. No Batch tables
appeared. H2 CRUD/SOAP startup logs also showed Flyway and Hibernate. A
PostgreSQL-labelled passthrough build was **not** counted as PostgreSQL runtime
proof because that archetype has no datasource. The local proof created and
dropped only its own randomly named databases.

The full Engine Python suite at the tested source commit reported **1,661
passed, 23 skipped**. The focused preview/security unit set reported **59
passed**. Before/after generation checked **12** pre-change tree digests from
the clean starting main, including default CRUD/SOAP/passthrough profiles plus
Batch and Kafka controls; nine default application trees were also compared
byte-for-byte against that main. Unsupported preview M5a, job-bearing file
and staging, plain/router Kafka, and CLI Kafka requests failed before output.
Changed-file Ruff, staged secret scan and diff whitespace checks passed.

## Boundaries

This is fresh-app, jobless preview proof only. It does not establish an
existing H2/PostgreSQL or Batch-history migration, Batch/M5a behavior,
Kafka/validator compatibility, a default-profile switch, vulnerability
remediation or risk acceptance, container operation, full Suite L5, M2
completion or release acceptance. Hosted CI results and independent review
must be evaluated against the PR's **final exact head**, separately from this
local source-commit record.
