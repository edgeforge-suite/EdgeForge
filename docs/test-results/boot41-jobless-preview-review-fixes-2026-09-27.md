# Boot 4.1 Jobless Preview: Review-Fix Proof (2026-09-27)

**Candidate:** EF-V5-M2-ENGINE-BOOT41-S1, revision 1. **Tested Engine source:**
`6011646c1261f8ea2397219ca2b3163d3ac5a5c6`. This later evidence
commit is not itself the source SHA under test. The generator and generated
configuration did not change from the [first proof](boot41-jobless-preview-2026-09-27.md);
the comparator, preview profile descriptions, tests and guide did. This record
supersedes the first proof's wire-comparator claim, not its historical results.

## Executed Proof

The full `scripts.smoke.boot41_preview_proof --mode full` command exited **0**
at the source SHA above. It used Java **17.0.18** and **21.0.12.1**, Maven
**3.9.12**, and task-owned loopback PostgreSQL **16.13**. The command is in
the [preview guide](../generated-app-standards/boot41-jobless-preview.md#reproduce-the-scoped-proof);
no host-specific path or credential is needed in this record.

| Scope | Result |
| --- | --- |
| Preview generation/build | 12/12 builds passed across four fixtures and H2/Java 17, PostgreSQL/Java 17, PostgreSQL/Java 21; each ran one generated `@SpringBootTest contextLoads()` test, zero failed/skipped. Repeated preview generation matched; source and packaged-JAR independence checks passed. |
| Boot 3 H2 controls | Four builds passed; CRUD and both SOAP controls ran one generated test each, while passthrough ran zero generated tests. |
| Live H2 wire comparisons | CRUD, inbound SOAP, outbound SOAP and passthrough all passed under the corrected comparator. These are functional HTTP/SOAP/downstream assertions, separate from context-start tests. |
| Live PostgreSQL | Fresh CRUD and inbound SOAP starts passed on Java 17 and 21; Flyway histories were `1,2` and `1`, Hibernate initialized, REST write/read worked, and no Batch tables appeared. SOAP outbound and passthrough PostgreSQL-labelled builds were not counted as database-runtime proof. |
| Engine regressions | Full Python suite: **1,673 passed, 23 skipped**. Focused preview tests: **48 passed**. Generated CRUD pagination, passthrough validation and security runtime tests: **14 passed** with the runtime flag enabled. Changed-file Ruff and diff whitespace checks passed. |

The proof created and dropped only its randomly named databases. A query found
no remaining `boot41_%` databases, and the disposable service was stopped.
The first sandboxed Python run had one packaging-install network failure and
the first sandboxed Maven run hit a Mockito agent-attach restriction; both
passed when rerun with the required local permissions. Neither was counted as
a product failure or waived check.

## Corrected Comparison Policy

Created fixture IDs must be canonical UUIDv4 strings. CRUD read/list, SOAP
REST read, inbound SOAP response, outbound SOAP request and its JSON
acknowledgement must identify the resource created by that run. Only those
identified fields are substituted. Negative controls reject numeric, object,
malformed and wrong-resource IDs. Top-level error timestamps must be
ISO-8601 UTC strings; non-error/nested `timestamp` values are preserved.

XML comparison retains meaningful text and child tails, distinguishes missing
fields and resolved QName-valued SOAP fault-code namespaces, and ignores only
namespace-prefix spelling and whitespace-only element indentation. Selected
content-type parameters, including XML charset, are compared. Negative
controls cover altered text/tails, missing fields, changed namespace bindings
and charset, while harmless prefix/indentation differences compare equal.

JSON object member order is deliberately **not** compared; the selected
contracts do not require it. Values and JSON types remain compared. The
reviewers observed different Jackson 3 key order, but order alone is not a
demonstrated contract violation. The preview retains Jackson 3 defaults and
does not emit a Jackson 2 compatibility setting or module. The live malformed
JSON probes establish the narrower, intentional input-hardening difference:

| Selected path; valid object followed by another object | Boot 3 | Boot 4.1 preview |
| --- | --- | --- |
| CRUD and both SOAP REST ingress | HTTP 201 | HTTP 400 |
| Passthrough ingress | HTTP 200 | HTTP 400 |
| Passthrough malformed downstream reply via its independent `RestTemplate` converters | HTTP 200 | HTTP 500 |

The selected valid passthrough outbound body and downstream reply still match
semantically. Malformed legacy payloads are **not** claimed compatible; an
adopter depending on them needs a separate correction/compatibility decision.
These fixtures do not exercise every Jackson 3 default, such as null-to-primitive
or enum `toString()` handling. No universal Jackson compatibility conclusion
is inferred from this bounded proof.

## Boundary

This is fresh, jobless preview proof, not persistent H2/PostgreSQL or Batch
history migration, Batch/M5a, Kafka, container operation, Maven vulnerability
assessment, Suite L5, M2 completion, residual-risk acceptance or release
approval. The new PR head's CI and independent review remain separate gates.
