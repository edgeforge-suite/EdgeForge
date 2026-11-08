# Selected REST write contract

Maintainer decision: EF-V5-ENGINE-WRITE-CONTRACT-P2 revision 1, with the
2026-10-13 payment mapping amendment. This is bounded transport support-or-refuse,
not arbitrary action generation or full OpenAPI enforcement. The
[read contract](read-operation-contract.md) remains in force.

## Supported Boundary

| Selected contract | Generated behavior |
| --- | --- |
| CRUD collection POST | Complete common collection path, required JSON-object body and compatible 201 object response. |
| CRUD item PUT | One typed own-persistence-ID path value, required JSON-object body and compatible 200 object response. |
| CRUD item DELETE | One typed own-ID path value and compatible 204 response without a body. |
| Ordinary scalar header/query inputs | Requiredness and actual values reach controller, base service and preserved developer override. Optional absence remains null. |
| Existing direct-canonical state transition | Retain its bounded own-ID/static-action route; not arbitrary OpenAPI action support. |
| Passthrough write | Body-only POST with exactly one declared 200 or 202 success: preserve its JSON-object body, or emit no body when no content/response fields are declared. Path/header/query inputs without a forwarding/developer seam are refused. |
| Sample-only input without a source HTTP contract | Existing Engine route behavior, labelled sample-only rather than remote-contract proof. |

Selected source operations are retained before classification, entity attribution,
deduplication or first-context selection can erase them. Emission does not fetch
the source again. Unselected operations are not blockers. Generate, plan and apply
share preflight before creating directories or changing bytes, permissions or
timestamps. Relevant direct emission entry points use the same guard. Diagnostics
identify interface, operation and unsupported element; unsupported input cannot
produce an approvable plan.

Refusals include unsupported methods (including PATCH), unresolved selections or
references, omitted additional primary writes, fieldless/unmapped-body entity
associations, mixed bases requiring fallback, collection PUT, trailing slashes,
dropped suffixes/variables, foreign/business-key/additional selectors, unsafe
Java literals and unsupported path syntax. Method/path collisions cover selected
operation controllers, undeclared fallback CRUD and fixed demo/batch mappings
when their controllers are actually emitted. Equivalent placeholder names do not
avoid a collision. Different HTTP methods on the same path are not themselves
a collision; absent controllers do not reserve a namespace.

Cookie inputs, unsupported types/serialization, ambiguous bindings and unenforced
standard conditional-write headers are refused. Optional bodies cannot silently
become required. Success checks validate the handler's status/body, not the first
arbitrary 2xx response. Unresolved responses and bodies with 204 are not permission
to proceed. Complete response/header/error/schema conformance is not established.
Passthrough does not choose among multiple success responses or discard canonical
response fields to satisfy an empty response. Status 202 is transport fidelity,
not a promise of an asynchronous queue or durable acceptance.

The fixed demo GETs `/api/demo/entities` and
`/api/demo/entities/{entityName}` count whenever DemoController is emitted,
including when its runtime enabled flag is false. Full CRUD generation emits
it only with the applicable profile console setting and demo-input conditions;
passthrough does not emit it. The fixed POST `/batch/run/{jobName}` counts when
the profile and entity artifact plans emit jobs and BatchTriggerController.
Direct emitters validate the surface they actually emit, not unrelated absent
controllers. Generate, plan and apply validate the full applicable surface before
output mutation.

Known deferred limitation: affected integer transport parameters bind as `Long`,
so `format: int32` does not enforce signed 32-bit bounds. The
[2026-10-14 maintainer decision](enterprise-readiness-roadmap.md#endpoint-boundary-maintainer-decision)
defers Engine's range-enforcement correction until post-v5. Adopters requiring
those bounds must validate before business, persistence or downstream effects.

OpenAPI Authorization, Accept and Content-Type Parameter declarations follow
the established special-header handling. Source security/media declarations
remain intact; no authentication is inferred. Gateway authentication, protected
application ports and adopter object/tenant authorization remain required.
Input delivery is not proof of developer business semantics.

An entity-name or generic ID alias cannot contradict a separate canonical field
or its input mapping; matching a customary name does not override the selected
persistence identity. Explicit direct-canonical HTTP actions also require one
typed own-ID selector even without a source path. Genuine no-HTTP samples retain
their legacy boundary. Body wire literals and generated-local argument collisions
are refused before generation rather than renamed. Boolean transport controls
provide omitted/true/false choices; required absence blocks console submission.

## Payment And Developer Responsibilities

Required `x-idempotency-key` and `x-jws-signature`, plus optional inputs, reach
the preserved developer method. Missing required headers reject before
persistence. Console descriptors construct headers/query inputs rather than
putting them in the body. **Presence is not replay protection or signature
verification.** Those remain developer-owned; read metadata roles must not
relabel write obligations.

Write-input arguments change developer-service signatures. Pre-v5 overrides and
call sites require explicit updates after regeneration; existing developer files
remain preserved.

**Adopted v5 endpoint policy (2026-10-14): retain existing generic CRUD.** Selected
OpenAPI operations do not define the entire emitted API. Review the actual emitted
HTTP method/path surface and expose only explicitly approved operations through
the authenticated TLS gateway. Unapproved CRUD, demo and batch endpoints must be
inaccessible through it; the application port must be inaccessible except through
it. Authentication alone is not endpoint exposure approval or business/object/
tenant/row authorization. Engine does not enforce gateway configuration or supply
an endpoint allowlist. This supersedes the prior open generic-CRUD policy decision,
not the requirement for deployment-specific approval. Collision checks are not
exposure approval.

Retained source contracts now participate in CRUD `manifest_hash`, so schema
baseline hashes change even when emitted business fields do not. Together with
the payment mapping change, this uses the pre-v5 fresh-regeneration policy;
existing generated output is not a database-migration promise.

The payment input-layer correction explicitly points existing flat aliases and
downstream/handoff mappings to sampled canonical properties. It preserves
`InternationalPaymentId`, wire names, string amount, date/time types and
downstream columns. There is no emitter case-folding: `Amount`/`instructedAmount`,
`Currency`/`CurrencyOfTransfer` and `Name`/`creditorName` remain distinct. The
[historical Option B decision](test-results/obie-payment-initiation-wire-transfer-smoke-2026-04-01.md)
still applies: full nested envelopes require gateway/adapter normalization to
the flat body. Original samples and historical failures remain unchanged.

Mapped DTO properties bind their field, getter and setter to the same wire name
when JavaBean inference could differ. This prevents unintended case aliases
without merging canonical fields or expanding nested envelopes. Auto-included
response fields outside these explicit mappings remain a separate limitation.

## Proof Boundary

Focused tests cover source ingestion, three profiles, bindings, responses,
references, collisions, literals, preservation and read protections. Run:

```sh
python -m scripts.smoke.write_contract_proof \
  --output <new-evidence-directory> --java17-home <jdk17>
```

`tests/unit/test_studio_sample_write_contracts.py` also generates all three
pinned production-export Studio pack contracts on every shipped profile without
remote fetching. The claims POST's empty 202 and JSON 200/202 controls are
distinct; ambiguous/unsupported responses still refuse before output mutation.

The bounded helper builds synthetic CRUD and the shipped payment package using
cached Maven dependencies, normal H2/Flyway startup and source/packaged
independence. Test-owned developer overrides observe transport, not business
or security certification. Repeat generation and developer preservation are
checked. Payment uses the documented flat contract, not nested-wire support.
The helper also checks exact mapped response keys and isolated Jackson
serialization/deserialization, including distinct acronym fields and scalar types.
This is not Suite L5, PostgreSQL runtime proof, a dependency/image assessment,
production certification, M2 completion or release acceptance.

For fixed-controller applicability, refusal/preservation and generated guidance,
run `tests/unit/test_endpoint_boundary.py`. The separate bounded runtime helper is:

```sh
python -m scripts.smoke.endpoint_boundary_proof \
  --output <new-evidence-directory> --java17-home <jdk17>
```

It generates the four present/absent demo/batch combinations using existing
fixtures, executes generated tests, starts each app with normal H2/Flyway schema
initialization, and calls generic CRUD plus applicable demo/batch routes. It
checks deterministic regeneration and unchanged generated source/configuration.
Runtime demo disabled/enabled behavior is observed without suppressing controllers.
This local development proof neither deploys nor certifies the required gateway
exposure policy, authorization, PostgreSQL durability or full OpenAPI conformance.
