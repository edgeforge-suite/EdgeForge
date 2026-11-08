# Generated-App Security Posture — Design (P1-5)

> **Status:** DESIGN **FROZEN** — decision and contracts resolved; **Slices 1–4 implemented.**
> Slice 1 delivers the shipped-profile posture matrix, generated README and
> agent-context authorization envelope and rate-limit delegation, and Kafka's health-only actuator
> default. Slice 2 rejects generated CRUD pagination above the approved page-size and offset bounds.
> Slice 3 validates representable canonical passthrough inbound fields before routing,
> transformation, or downstream calls. PR #304 delivered the top-level boundary; the post-#304
> reader-first residual now resolves supported single-level nested properties, fails closed for
> unrepresentable effective required input, and surfaces compatibility diagnostics (§6).
> Slice 4 emits the universal TLS-independent response-header baseline for CRUD, passthrough, and
> Kafka applications (§7).
> Pre-existing controls this document *describes* (e.g. CRUD's own request validation, or the existing 400 on
> `page<0`/`size<1`) were already shipped beforehand and are unaffected by that statement.
> [`docs/suite-security-review-backlog.md`](../suite-security-review-backlog.md) P1-5 records the
> implemented Option A posture and completed slice sequence (§12).
>
> **Grounded against:** Engine `origin/main @ c533686` (post PR #299 — the completed Studio
> web-security-baseline reconciliation); Studio `origin/main @ 2dbdec7`; KS `origin/main @ 51bbff0`
> (Studio/KS grounding covers only the specific claims cited in §2 — profile-list hardcoding and the
> absence of any target-profile-consuming surface — not a general audit of either repo. The Studio claim
> was re-verified at `2dbdec7`: `app/routes/project.py` is byte-identical to the earlier `c555313`
> checkpoint, so the profile-picker claim is unaffected by the intervening Studio commits).
> **Slice 1 merge baseline:** Engine `origin/main @ 58c079f` via PR #301.
> **Slice 2 merge baseline:** Engine `origin/main @ 4aa09ae` via PR #303.
> **Slice 3 merge baseline:** Engine `origin/main @ 85c9902` via PR #304.
> **Post-#304 reader-first merge baseline:** Engine `origin/main @ c021c59` via PR #305.
> **Slice 4 implementation:** delivered by this change; no pre-merge SHA is represented as a merge
> baseline.
> **Source design/decision:** resolves P1-5 (`docs/suite-security-review-backlog.md:216-238`), the
> generated-app security posture decision the roadmap's M2 entry names as Engine-owned and separate from
> the suite-wide vulnerability-assessment track.
>
> **Suite scope:** Engine, Studio, KS. TestBench excluded.

## 0. Why this document exists

P1-5 asked one question: does EdgeForge ship in-application authentication/authorization in generated
apps, or does it delegate to the adopter's gateway? The audit found a dormant OAuth2 skeleton
(`emit_security`, default `False`, enabled by zero shipped profiles) and several suite documents that
described it as if it shipped. This design resolves that question for v5 and sweeps the active suite
documents that overstated the skeleton's reach — while also **specifying remediation for** four smaller,
independently real gaps found while verifying the posture: unbounded pagination, unvalidated passthrough
request bodies, no generated security-header baseline, and unauthenticated-by-default Kafka actuator
metrics/Prometheus exposure. This document is the decision and the contract; §12's slices are what
actually close those four gaps in code.

## 1. Design-baseline facts, verified at `c533686`

| # | Fact | Verified |
|---|---|---|
| 1 | `appbuilder/target_profiles/catalog.py:18` — `emit_security: bool = False`. Executed the catalog: **3 shipped profiles, zero with `emit_security=True`.** | ✅ |
| 2 | `appbuilder/generation/security_emitter.py:13-22` — `emit_security_sources` returns `[]` unless `target_profile.emit_security`. | ✅ |
| 3 | The skeleton (`security_emitter.py:21-83`) permits `/actuator/health`, authenticates every other request via `oauth2ResourceServer(jwt)`, and defines **no authority, object-level, tenant-level, or row-level authorization**. | ✅ |
| 4 | At the design baseline, `appbuilder/generation/build_emitter.py:605-625` (`_deployment_security_note_lines`) was correctly conditional on `emit_security` but its non-security branch said *"before exposing it outside a trusted local network"*. Slice 1 removes that weakened alternative and emits the complete §8/§9 boundary. | ✅ corrected by Slice 1 |
| 5 | Multiple active suite documents describe the skeleton as shipping, or present the auth default as an open adopter decision. **False for every shipped profile.** An initial pass identified 4 sites; the completed sweep found **11** across 6 files — see §11 for the full corrected list. `security-boundary-map.md`'s §4 body was *conditional* but never stated that zero shipped profiles enable it, so it was rewritten rather than left as-is. | ✅ corrected in this PR |
| 6 | No test asserts the security/console posture of every shipped profile as a matrix; `emit_security` appears only as an inline field on ad-hoc test profiles. | ✅ |
| 7 | `java_emitter.py:2241,2349,2387` — `Pageable pageable = PageRequest.of(page, size)`, no upper bound. **Correction to the original finding:** `page<0`/`size<1` already return `400` via the unconditional `@ExceptionHandler(IllegalArgumentException.class)` at `:1086` — verified by generating on all three profiles. The real gap is the missing **maximum**, not missing input handling. | ✅ (corrected) |
| 8 | `passthrough_emitter.py:337` emits `@RequestBody InboundRequestDto` with no `@Valid`. **Correction:** `@Valid` alone would **not** produce a 500 (Spring MVC maps `MethodArgumentNotValidException` → 400 by default) — but the generated POM (`build_emitter.py:1291-1294`, ships `web`/`actuator`/`test` only) carries **no Jakarta Validation implementation**, so `@Valid`/`@NotNull` **fail to compile**, not silently no-op. Independently reproduced: generated `country-router`, confirmed both Jakarta Validation API and Hibernate Validator absent from its dependency tree, added `@NotNull`, compilation failed on missing `jakarta.validation.constraints`. | ✅ (corrected twice) |
| 9 | No security-header emission, no rate limiting, anywhere in generation. | ✅ — zero hits across all emitters |
| 10 | Generated apps carry no EdgeForge runtime/build dependency; `groupId` is `com.appbuilder`. | ✅ |

## 2. Decision: Option A — Gateway-Delegated Security

**Adopted for v5.** No shipped profile emits in-application authentication or authorization. Generated
apps require an **authenticated, TLS-terminating gateway** before exposure, with the application port
unreachable except through it (§8). A merely "trusted" internal network is **not** an accepted substitute
inside the supported envelope: without an authenticating hop, every caller that can route to the port is
unauthenticated, which is the bypass §8 exists to prevent. Unauthenticated local operation remains
legitimate for **development only** — the `springboot-legacy-compatible` profile and its test console are
explicitly non-production — and sits outside this envelope.

**Why not Option B:** the manifest carries no identity-claim vocabulary, tenant discriminator, or
ownership field — `CanonicalField` has `is_id`/`server_generated_id` but nothing expressing row
ownership. Object/tenant-level authorization semantics **cannot be derived from approved source**, and
building them would require a new manifest capability during the `2.0` freeze. Enabling the skeleton
without resource-level authorization would be **actively worse** than the honest current posture — any
valid token from the issuer would read every row of every tenant.

**Cross-repo impact:** none forced. Studio's profile picker (`EdgeForgeStudio/app/routes/project.py:25-32`)
hardcodes exactly the three shipped profile IDs; Option A adds no profile, so no Studio change is
required. KS has no target-profile-consuming surface — verified, no reference found.

## 3. Dormant-skeleton status

`appbuilder/generation/security_emitter.py` is retained as an **internal dormant emitter** — not removed,
not deprecated, and **not a supported extension API**. It carries no compatibility promise.

**Reachability, corrected:** constructing a `TargetProfile` object alone does not activate it. Both
generation paths resolve the target profile **by name** from the shipped catalog —
`appbuilder/generation/engine.py:178` (inside `_generate_crud_application` — CRUD dispatch only) and
`:430` (inside `_generate_passthrough_application` — passthrough dispatch only) each independently
execute `TARGET_PROFILES[metadata.target_profile]` — and `appbuilder/contracts/manifest.py:1089` rejects
any profile name not already a key in that dict. **Normal generation cannot reach the skeleton; reaching
it requires registering a new profile in `TARGET_PROFILES` itself**, which is the same act as shipping a
fourth profile and is out of scope for this design.

## 4. Support and ownership matrix

| Control | Engine-emitted | Adopter gateway | Status |
|---|---|---|---|
| TLS termination | ❌ | ✅ | Delegated |
| Authentication | ❌ | ✅ | Delegated — v5 supported posture |
| HTTP method/path exposure approval | ❌ | ✅ | Adopted 2026-10-14: review the emitted surface and expose only explicitly approved operations; selected OpenAPI operations are not the whole API |
| Authorization (object/tenant/row) | ❌ | ⚠️ partial (gateway cannot do row-level) | **Unsupported** — see §8 |
| HSTS | ❌ (the new universal header filter, §7, never emits it) | ✅ | Delegated — meaningless without knowing the TLS terminus. **The dormant Spring Security path is a separate, independent exception**: its default `HeaderWriterFilter` may emit conditional HSTS on HTTPS requests if that skeleton is ever active — that default is Spring Security's, not suppressed, and not something this design controls. |
| `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` / scoped CSP | ✅ | optional | **Slice 4** |
| Rate limiting | ❌ | ✅ | Delegated — per-instance limits are unsound under horizontal scaling and would manufacture a false guarantee |
| Pagination bounds | ✅ | ❌ (cannot safely clamp a query param) | **Slice 2 (implemented)** |
| CRUD request-payload validation | ✅ (existing) | — | Already shipped |
| Passthrough request-payload validation | ✅ | — | **Slice 3 (implemented)** |
| Kafka actuator `metrics`/`prometheus` exposure | ✅ opt-in via env var | ✅ must sit behind the gateway when enabled | **Slice 1** |

### Endpoint exposure amendment (2026-10-14)

The maintainer [retains existing generic CRUD endpoints](../enterprise-readiness-roadmap.md#endpoint-boundary-maintainer-decision).
Selected OpenAPI operations do not define the entire emitted API. A supported
deployment must review the actual HTTP method/path surface and expose only
explicitly approved operations through the authenticated TLS gateway. Unapproved
CRUD, demo and batch endpoints must remain inaccessible through that gateway;
the application port remains inaccessible except through it. Authentication alone
does not limit available routes or methods. Gateway exposure approval is separate
from adopter-owned business/object/tenant/row authorization (§8).

Engine does not enforce this policy through an endpoint allowlist or automatic
gateway configuration. Collision preflight includes fixed demo/batch mappings
only when those controllers are emitted, including runtime-disabled demo handlers;
it is not exposure approval and changes no controller enablement behavior.
The [selected-write contract](../write-operation-contract.md) defines that guard.

Affected integer transport parameters currently bind as Java `Long`, so declared
`format: int32` does not enforce signed 32-bit bounds. This Engine-owned validation
limitation is explicitly deferred post-v5, with the bounded completion criterion
in the roadmap decision. Adopters requiring those bounds must validate before
business, persistence or downstream effects. No integer/database type changes,
full OpenAPI validation, vulnerability-risk acceptance or other gate waiver follow.

### 4.1 Archetype × posture matrix

`emit_security_sources` is called at **exactly one site** — `engine.py:221`, inside
`_generate_crud_application` (`:153`→). `_generate_kafka_application` (`:99-152`) and
`_generate_passthrough_application` (`:437`→) never call it: **`emit_security` is silently ignored by two
of three archetypes.** A custom profile that sets `emit_security=True` gets a `SecurityConfig` in CRUD
output only.

| | CRUD | Passthrough-router | Kafka |
|---|---|---|---|
| Generation path | `_generate_crud_application` | `_generate_passthrough_application` | `_generate_kafka_application` |
| POM builder | `_render_pom_xml:333` | `_render_passthrough_pom_xml:1277` | `kafka_build_emitter.py:61` |
| `spring-boot-starter-web` | ✅ | ✅ | ✅ |
| `spring-boot-starter-validation` | ✅ `:334` | ✅ **Slice 3** | ❌ n/a — no request bodies |
| Honors `emit_security` | ✅ only caller | ❌ ignored | ❌ ignored |
| `GlobalExceptionHandler` | ✅ | ✅ validation-only advice from **Slice 3** | ❌ none |
| HTTP surface | `@RestController` + optional test console | `@RestController` | actuator only |
| Pageable paths | ✅ 3 sites | ❌ | ❌ |
| Header filter (Slice 4) | wire | wire | wire |
| Actuator exposure | n/a | n/a | **health-only default; metrics/Prometheus explicit env opt-in (Slice 1)** |

## 5. Pagination contract

**Reject, not clamp.** Clamping `size=5000` to `200` silently truncates a caller's request with no
signal of data loss — the worst outcome for a security-motivated change. Reject matches the behavior
already shipped for `page<0`/`size<1`.

Two bounds, both required, as **explicit v5 policy defaults**:

| Bound | Constant | Default | Violation |
|---|---|---|---|
| Page size | `MAX_PAGE_SIZE` | `200` | `400` |
| Total offset | `MAX_PAGE_OFFSET` | `50_000` | `400` |

The offset bound is the one that protects the database: `size=200` with `page=10_000_000` passes the
size cap and still produces a catastrophic `OFFSET`.

**Ordering, corrected — construct `PageRequest` first:**

```java
private static final int MAX_PAGE_SIZE = 200;
private static final long MAX_PAGE_OFFSET = 50_000L;
```

```java
Pageable pageable = PageRequest.of(page, size);              // unchanged — still 400s page<0 / size<1
if (size > MAX_PAGE_SIZE) {
    throw new IllegalArgumentException("size must not exceed " + MAX_PAGE_SIZE);
}
if (pageable.getOffset() > MAX_PAGE_OFFSET) {
    throw new IllegalArgumentException("page offset must not exceed " + MAX_PAGE_OFFSET);
}
return ResponseEntity.ok(service.findAll(pageable));
```

An earlier draft checked `(long) page * (long) size > MAX_PAGE_OFFSET` **before** `PageRequest.of` — for
`page=-1, size=-100000` that product is `+100000`, so the new offset guard could fire ahead of
`PageRequest`'s own negative-input rejection with the wrong message. Constructing `PageRequest` first and
reading `getOffset()` off the already-validated object removes the sign-flip path entirely: `getOffset()`
is computed by `AbstractPageRequest` and is only reachable once `page`/`size` have already passed Spring
Data's own non-negative checks.

Constants declared **once, only in controller classes containing at least one pageable method** —
never emitted into a controller with no pageable path; guards inserted at all three pageable branches
(`java_emitter.py:2230` list-all, `:2340`, `:2374` preserved non-CRUD list reads).

**Runtime proof:** MockMvc with a mocked **service** (the controller's immediate collaborator, not the
repository) — assert `status().isBadRequest()` **and** `verifyNoInteractions(service)`. Repository-only
verification would pass even if the service was entered and only the repository call was skipped.

## 6. Passthrough validation contract

**Compilation, corrected.** Without `spring-boot-starter-validation`, `@Valid`/`@NotNull` do not compile
— `jakarta.validation.constraints` is absent from the classpath (Spring Boot 3 does not pull validation
transitively via `starter-web`). This was independently reproduced against a generated `country-router`
app. The starter is a **hard prerequisite** for this slice, not an optional hardening add-on, and
compilation is itself part of the negative control: a source-assertion test alone would give a false pass
if the starter were omitted.

**Scope — `InboundRequestDto` only.** `_render_dto` (`passthrough_helpers.py:73`) is called four times
(`InboundRequestDto`, `InboundResponseDto`, `OutboundRequestDto`, `OutboundResponseDto`,
`passthrough_emitter.py:70-99`). Constraints apply **only** to `InboundRequestDto` — the request-bound
input. The other three are not request inputs and must stay unannotated.

**Derivation scope, stated explicitly.** `InboundRequestDto` is built from `upstream_operations[0]`
alone (`passthrough_emitter.py:48-49`, `first_upstream_operation = upstream_operations[0]`). Multiple
upstream operations may share that DTO only when their effective required/string-maximum validation
contracts are identical. Translation fails closed before generation when those contracts differ, naming
the interface and conflicting operations. Operation-specific DTO support remains outside this slice.

**Enforceable constraint set — verified against the actual populator.** `extract_entity_fields`
(`appbuilder/ingestion/openapi_classifier.py:600-640`) is the only source of passthrough
`request_fields`. It sets exactly `required`, `max_length`, `format`, `allowed_values`, `type`, including
those supported scalar constraints carried through cycle-safe local component `$ref` chains. OpenAPI
3.1 sibling constraints are composed conjunctively for those supported fields; OpenAPI 3.0 reference
siblings retain their dialect-defined ignored behavior. Unresolvable, cyclic, incompatible, or unsupported
3.1 sibling contracts fail closed on the strict supported-scalar path instead of silently dropping effective
constraints.

| Constraint | Metadata populated? | Enforceable this slice? |
|---|---|---|
| `@NotNull` ← `required` | ✅ | **Yes**, representable canonical fields only |
| `@CodePointLength(max=)` ← `max_length` | ✅ | **Yes**, representable STRING fields only |
| `@CodePointLength(min=)` ← `min_length` | ❌ never set | No |
| `@Pattern` ← `pattern` | ❌ never set on entity fields (only on operation *parameters*, `:305`) | No |
| `@DecimalMin`/`@DecimalMax` ← `range_min`/`range_max` | ❌ never set | No |
| enum ← `allowed_values` | ✅ captured, but `_field_validation_annotations` (`java_emitter.py:2817`) emits nothing for it | No |

**Only `@NotNull` and `@CodePointLength(max=)` are enforceable.** `CodePointLength` is supplied by the
already-pinned Hibernate Validator runtime and counts Unicode code points, matching OpenAPI/JSON Schema
`maxLength` semantics for supplementary characters. Do not claim pattern, range, or enum enforcement —
the translation path does not supply the metadata (pattern/range) or the emitter does not act on it that
already has it (enum). CRUD uses the same code-point-aware string-length annotation and enforces enums
separately through the rules engine
(`RuleType.ALLOWED_VALUES`, `:3338`), which passthrough has no equivalent of.

**At PR #304's merge, Slice 3 had a closed, positive top-level structural boundary.** Its strict path
covers **top-level** upstream request properties that operation extraction represents as canonical
scalars, including the supported local-reference chains, `allOf` compositions, and dialect-specific
reference-sibling handling described above. That resolution is applied by
`_resolve_property_schema_for_extraction`, which operation extraction calls **only for top-level
properties**.

**At that merge, properties nested inside a single-level-flattened object were read literally and were
outside the boundary.** The flatten branch took `type`, `format`, and `maxLength` directly off the nested property
and never calls the resolver, so:

- a nested `$ref` trips the deeper-nesting test and the **whole parent object is skipped**, and
- a nested `allOf` loses its composed constraints — the field is emitted with `@NotNull` but no
  `@CodePointLength`, so an over-long value reaches transform, routing, and the downstream call.

Slice 3 claims neither validation nor fail-closed behavior for either case. **Required-nullable
detection is the one analysis that does recurse**: `required_nullable_request_fields` walks nested
properties and still fails closed on a required-nullable scalar inside a required object.

Every other required upstream request shape likewise remains a Phase 1a exclusion. Operation extraction
can skip such shapes, and its current call sites do not propagate the collected warnings into
`GenerationReport.warnings`; Slice 3 therefore makes no validation, fail-closed, or surfaced-diagnostic
claim outside that positive boundary.

**The follow-up requirement started from an inventory of readers, not of shapes.** Enumerating unsupported shapes
is what produced this gap: the top-level resolver was corrected repeatedly while its nested-property
sibling kept reading schemas raw. The follow-up must therefore (1) inventory **every** site that reads
`type`, `format`, `maxLength`, `$ref`, or `allOf` off a property schema, (2) add nested `$ref`/`allOf`
resolution so nested properties go through the same path as top-level ones, and (3) either fail closed
with interface/operation/field context or surface an explicit generation diagnostic for whatever remains
unrepresentable — without changing optional, response, downstream, or CRUD compatibility by accident.

### 6.1 Property-schema reader inventory

This inventory is the implementation authority for the post-#304 reader-first residual. It distinguishes
OpenAPI property readers from adjacent schema consumers so no raw property reader remains accidental.

| Path / symbol | Property context and values read | Baseline behavior | Final disposition | Covering proof |
|---|---|---|---|---|
| `ingestion/openapi_classifier.py`: `_collect_properties_and_required`, `_merge_conjunctive_property_schema`, `_resolve_property_schema_for_extraction`, and the top-level branch of `extract_entity_fields` | Canonical operation/entity properties; `type`, `format`, `maxLength`, `$ref`, `allOf`, requiredness, and supported conjunction metadata | Dialect-aware local-reference and supported-`allOf` resolution | Retain as the single shared resolver path; nested passthrough properties must call it rather than duplicate it | `test_extract_entity_fields_resolves_nested_property_references_and_all_of`; existing top-level reference/composition tests |
| `ingestion/openapi_classifier.py`: `extract_entity_fields` dispatcher and `_flatten_single_level_object_fields` | Nested upstream passthrough request properties; resolved `type`, `format`, `maxLength`, `$ref`, `allOf`, and effective requiredness | Raw read before the post-#304 residual | Opt into the shared resolver with dotted context and required fail/non-strict warn behavior only for upstream passthrough requests | `test_extract_entity_fields_resolves_nested_property_references_and_all_of`; required-shape and required-parent controls |
| `ingestion/openapi_classifier.py`: `_extract_entity_fields_legacy_compatible` | Nested upstream-response, downstream request/response, and CRUD properties; raw `type`, `format`, `maxLength`, and `$ref`/object detection | Raw read; nested `$ref` can skip the parent and nested `allOf` can lose constraints | Deliberately retain approved raw nested fields and diagnostics because resolving them would change generated DTO or persistence/API contracts. Compatibility-permitted operation roles run a diagnostic-only reference check so missing/cyclic refs warn without changing valid legacy fields | `test_non_strict_nested_reference_failures_warn_for_every_operation_role`; `test_response_and_downstream_nested_resolution_preserves_legacy_metadata`; CRUD and generated-DTO compatibility controls |
| `ingestion/openapi_classifier.py`: `_required_nullable_field_paths` and `_schema_allows_null` | Required request-property presence/nullability; `type`, `$ref`, `allOf`, `oneOf`, `anyOf`, boolean schemas, and dialect-specific reference siblings | Specialized recursive satisfiability analysis | Retain unchanged as the authoritative required-nullable check; nested extraction must not bypass it | existing required-nullable tests plus `test_passthrough_preserves_nested_required_nullable_fail_closed` |
| `metadata/translation.py`: `_schema_field_hints` via `_load_upstream_field_hints` | Sample-mapped CRUD request/response hints; raw `type`, `format`, and `maxLength` | Deliberately shallow/raw and separate from passthrough operation metadata | Retain raw for CRUD sample-inference byte compatibility; it does not authorize or emit passthrough validation. A regression pins that referenced/composed hints remain outside this residual | `test_schema_field_hints_remains_raw_for_crud_sample_compatibility`; shipped-example byte comparison |

**Classified exclusions:** `_extract_path_parameters` and `_extract_operation_parameters` read parameter
schemas, not body-property schemas. `_derive_response_shape`, `_schemas_from_schema`, and
`_entity_schemas_from_response_schema` perform operation/response traversal rather than canonical
property reads. XML/XSD, Kafka, file-contract, UI, and Java emitter readers consume other schema families
or canonical metadata and are outside this OpenAPI-property inventory.

**Post-#304 outcome:** upstream passthrough request flattening now reuses the shared resolver for local
chained references, supported scalar/object `allOf`, and OpenAPI 3.0/3.1 reference-sibling semantics.
Effective required arrays, field-level `oneOf`/`anyOf`, deeper object graphs, boolean/malformed schemas,
and missing required property definitions fail before output creation with interface, operation, and full
dotted-field context. A required parent object whose children are all optional also fails closed because
flattening cannot preserve the parent's presence; the corresponding optional parent remains supported.
Non-strict missing/cyclic nested references become stable dotted-field warnings rather than exceptions.
Upstream responses, downstream contracts, and CRUD retain approved-base canonical fields, diagnostics,
and generated bytes; response/downstream warnings still propagate through `MetadataProject.warnings`,
`GenerationReport.warnings`, and the CLI. The specialized required-nullable recursion and PR #304's
top-level validation/error contract remain unchanged.

**Passthrough authoring consequence:** a flattened nested upstream request field may be selected as a
routing field or transform source. The legacy-compatible downstream request reader does not expose a
structurally equivalent nested downstream property as a flattened transform target. When a transform
must write that value, the downstream OpenAPI contract must declare the flattened target name as a
top-level property; nesting that target is not supported by this boundary.

**Required-nullable fields fail closed for v5.** Canonical request metadata does not distinguish
property presence from a present JSON `null`. A passthrough upstream request property that is both
required and nullable would therefore be narrowed incorrectly by `@NotNull`. Translation
rejects that combination before generation for OpenAPI 3.0 `nullable: true` and OpenAPI 3.1 null unions,
including composed and referenced schemas where `null` satisfies every `allOf` branch. Boolean schema
nodes are evaluated with JSON Schema semantics (`true` accepts and `false` rejects) throughout `allOf`,
`anyOf`, `oneOf`, and references. The refusal identifies the interface, operation, and field. Optional
nullable fields remain supported. Full required-nullable presence tracking is not introduced by Slice 3.

**Advice ships**, for a stable, sanitized, cross-archetype-consistent error body — Spring's own default
(`include-message=never`) is already sanitized, so this is a consistency decision, not a security
requirement. **The contract, precisely, so two builders cannot satisfy "stable" with different
artifacts:**

- **Reuse CRUD's existing five-field `ErrorResponse` shape** (`timestamp`/`status`/`error`/`message`/`path`,
  `java_emitter.py:945-960`) — do not invent a second shape for passthrough.
- **HTTP `400`**, via `@ExceptionHandler(MethodArgumentNotValidException.class)`.
- **No rejected-value echo.** The `message` field names the violated field and constraint, never
  `FieldError.getRejectedValue()` — the passthrough request body is upstream-caller-controlled input, and
  echoing it back is exactly the class of thing PR #289's sanitized-diagnostics work removed elsewhere in
  the suite.
- **Runtime proof, both enforceable constraints, plus controls:** omitted and explicit-null required
  fields test `@NotNull`; ASCII and supplementary-Unicode strings test exact `maxLength` and
  max-plus-one code-point boundaries; every invalid request proves zero transform, route, downstream,
  or CRUD service interactions.

**Renderer remains passthrough-local; length semantics are coordinated.** The passthrough renderer stays
restricted to its two enforceable constraints rather than extracting a shared abstraction. The bounded
`java_emitter.py` correction replaces CRUD's string-length annotation with the same Hibernate
`CodePointLength` constraint so the two archetypes do not disagree on Unicode length. A cross-check unit
test keeps their shared required/max-length rendering aligned.

## 7. Header contract

Universal filter (new module, Slice 4 in §12) emits, on every response, every archetype:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Content-Security-Policy: frame-ancestors 'none'
```

All four are **TLS-independent** — safe without assuming termination. **No `Strict-Transport-Security`
from this filter, ever** — HSTS asserted over plain HTTP is meaningless and actively misleading; it
belongs at the TLS terminator.

**Duplication is a tested invariant, not a structural guarantee.** `response.setHeader()` replaces
whatever is present *at the moment it runs* — it does not prevent a filter that runs **later** in the
chain from overwriting or appending. The control that actually holds this is the runtime test: assert
`response.getHeaders(name).size() == 1` for every header, on every archetype, including the custom-profile
case where the dormant Spring Security skeleton is active.

**Interaction with the dormant skeleton.** Spring Security's default `HeaderWriterFilter` independently
sets `X-Frame-Options` and `X-Content-Type-Options` (not `Referrer-Policy`, not CSP), and conditionally
adds `Strict-Transport-Security` on HTTPS requests. That default is Spring Security's own and is not
suppressed by this design — it only matters if a custom profile activates the dormant skeleton (§3), which
no shipped profile does. The single-value test is what proves the two writers don't produce duplicate
headers when both are present.

## 8. Authorization envelope

Replaces any "owned by nobody / accepted risk" framing with an explicit, positive, supported boundary.

> **Supported v5 posture:** a single trusted authorization domain behind an authenticated,
> TLS-terminating gateway. Every authenticated caller is trusted equally for all data the application
> exposes. **The application's port must be unreachable except through that gateway** — a caller that
> reaches the application directly bypasses this entire posture, because the application itself performs
> no authentication or authorization.
>
> **Not supported until adopter-owned application authorization is implemented and adversarially
> tested:** multi-tenant isolation, per-user scoping, object-level authorization, row-level policy.

This wording is **mandatory in generated README output, CRUD/passthrough `agent-context.md`, the static
deployment-operations runbook, and the static generated-app-operations-note** — not confined to
internal suite documents. The README directs humans and agents to `agent-context.md`, so both artifacts
must carry one shared, non-contradictory boundary.

## 9. Rate limiting

**Explicitly gateway-delegated**, closed decision. Engine-emitted per-instance rate limiting would be
unsound under horizontal scaling (each replica enforces its own independent budget) and would create a
false guarantee stronger than what the mechanism actually provides. Document the delegation in the
generated README/runbook rather than leave it unaddressed.

## 10. Kafka actuator exposure — the final resolved item

**Pre-Slice 1 state:** `kafka_build_emitter.py:232` emitted an unconditional
`include: health,metrics,prometheus`. `tests/unit/test_kafka_build_emitter.py:135-138`
(`test_kafka_build_emitter_always_includes_prometheus_endpoint`) asserted `"prometheus" in yaml_content`
unconditionally. Slice 1 replaces both with the contract below and proves the default and opt-in at
runtime without a broker.

**Decision: default to `health` only; `metrics`/`prometheus` become explicit operator opt-in.**
"Operators need it" does not justify unauthenticated default exposure of topic names, consumer-group lag,
and throughput — this matches Spring Boot Actuator's own health-only default and its guidance to secure
any additionally exposed endpoint.

**Contract:**

```yaml
management:
  endpoints:
    web:
      exposure:
        include: ${MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE:health}
```

- **Retain** the `micrometer-registry-prometheus` Maven dependency (`test_kafka_build_emitter.py:125`,
  unaffected by this change — it checks `pom.xml`, not the exposure line) so operators can opt in without
  a rebuild.
- **Document** `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,metrics,prometheus` in the generated
  README/runbook as the opt-in value.
- **Require** the gateway/non-bypassable network boundary (§8) as a precondition of opting in — the
  generated documentation must state this, not merely mention the env var.
- **This is a generated-runtime-configuration change**, not a documentation-only correction — it changes
  what `application.yaml` renders by default. It belongs in Slice 1 alongside the posture decision because
  it is part of *stating* the posture accurately, but it requires the same class of proof as any other
  generation-behavior change: focused generation assertion, Kafka `mvn` compile, and **runtime proof in
  both directions** — health reachable by default while metrics/Prometheus are not, and the explicit
  env-var opt-in exposes them. **Slice 1 is not a no-Maven, no-runtime slice** once this item is included.

## 11. Documentation corrections (this PR)

| File | Current defect | Correction |
|---|---|---|
| `README.md:90-91` | *"generated apps ship an OAuth2 resource-server **skeleton**"* | States no shipped profile emits it; points to this design doc |
| `docs/security-boundary-map.md` quick-answer row 4 (~`:25`) | *"OAuth2 remains a resource-server **skeleton** (IdP wired post-import)"* — implies shipped | Corrected to dormant/inactive in every shipped profile |
| `docs/security-boundary-map.md` §2 ASCII diagram (~`:84`) | The runtime-app box was labelled `OAuth2 resource-server SKELETON (IdP wired post-import)` unconditionally | Relabelled `NO in-app auth in any shipped profile (gateway-delegated, P1-5)` |
| `docs/security-boundary-map.md` §4 body (`:279-289`) | *Conditional* ("when a target profile enables it") but never stated that **zero** shipped profiles do — a reader would reasonably infer some profile does | Rewritten to lead with "No shipped target profile emits…", keeping the custom-profile behavior as explicitly hypothetical |
| `docs/security-boundary-map.md` §5 open-items row 5 (`:338`) | *"OAuth2-skeleton completion … (adopter action)"* — implied the adopter receives a skeleton to finish | Replaced with the resolved Option A decision and the unsupported-authorization boundary |
| `docs/security-boundary-map.md` caveats summary (`:361`) | *"OAuth2 is a skeleton — completed at the enterprise IdP post-import"* | Replaced with "No shipped profile emits in-application auth" |
| `docs/enterprise-readiness-roadmap.md:379-380` (D2 item) | *"Generated apps stay standalone with the existing OAuth2 resource-server skeleton … ready for the adopting organization's IdP"* — implies active/ready | Corrected to "dormant, internal-only, not active in any shipped profile" and points to this design |
| `docs/enterprise-readiness-roadmap.md` E2 item 6, external-gates list, `[adopter-decides]` summary, and import-gate status note | Four places presented the generated-app auth **default** as an open adopter decision, contradicting the Engine-owned Option A resolution | All four now record the default as Engine-decided; the genuinely adopter-owned obligation is restated as **deploying/operating the required authenticated gateway** |
| `docs/handover-evidence/README.md:58` | *"generated app **is** an OAuth2 resource server"* — flatly false, and this is adopter-facing handover evidence | Corrected — highest-priority fix, since this is the document an import reviewer reads. Split into an Engine-hardening row (`[now-ours]`) and a gateway-deployment row (`[post-import]`) so one tag does not cover two ownership scopes |
| `docs/generated-app-standards/deployment-operations-runbook.md:24-27` + OAuth2 env-var bullet (`:61`) | Retained "unless a security profile is enabled", and listed OAuth2/JWT config as ordinary secrets to provision, beside new wording saying the app performs no authentication | Removed the conditional; qualified the env-var bullet as custom-profile-only; added the §8 envelope wording; removed the "or trusted internal network" alternative |
| `docs/generated-app-standards/generated-app-operations-note.md:66-69` + OAuth2 env-var bullet (`:55`) | Same pair of defects | Same corrections |

**Preserved, not touched:** archived documents, `docs/handover-evidence/*.json`/dated evidence artifacts
other than the one `README.md` table row above, and any pinned historical acceptance evidence — none of
those assert current OAuth2 posture and none are in scope.

## 12. Slices — ordered, with acceptance criteria

| # | Slice | Files | Acceptance criteria | Merge-safety |
|---|---|---|---|---|
| **1 — IMPLEMENTED** | Posture decision, profile matrix, doc corrections (§11), rate-limit delegation, authorization envelope (§8) in generated README + CRUD/passthrough agent context + static runbook + operations-note, Kafka actuator env-var default (§10), **P1-5 backlog status update** | `build_emitter.py` (shared CRUD/passthrough README/agent-context wording), `kafka_build_emitter.py` (README + exposure line), docs, `docs/suite-security-review-backlog.md` (P1-5 resolved/implemented), exact profile-matrix and Kafka runtime tests | Delivered: exact three-profile `emit_security`/console matrix; shared generated-guidance assertions across CRUD and passthrough plus Kafka README coverage; no trusted-network alternative; broker-independent Kafka `mvn clean verify` plus runtime proof that health is reachable by default while metrics/Prometheus are not, and that the explicit env-var opt-in exposes all three; Prometheus registry retained; deterministic repeated generation. Tracker rows are reconciled per §12.1. | ✅ First in the slice sequence |
| **2 — IMPLEMENTED** | Pagination bounds, 3 CRUD branches | `java_emitter.py` | Delivered: constants are emitted once per pageable controller; all three pageable branches construct `PageRequest` first, then reject size above `200` or offset above `50_000` before service invocation. Source regressions cover default `listAll`, preserved `read_list`, preserved pageable `list`, non-pageable absence, exact messages/defaults, and ordering. A deterministic generated-app MockMvc proof runs `mvn -q clean verify`, uses `verifyNoInteractions(service)` for **exactly `MAX_PAGE_SIZE+1`** and **exactly `MAX_PAGE_OFFSET+1`**, and proves requests exactly at both bounds and below still reach the service. CRUD only — no other archetype has a pageable path. | ✅ Structural-emitter lane serialized for this change |
| **3 — IMPLEMENTED** | Passthrough `@Valid` + validation starter + advice, `InboundRequestDto`-only scope | `passthrough_emitter.py`, `passthrough_helpers.py`, `build_emitter.py`, bounded `java_emitter.py` annotation correction | Delivered by PR #304: the real OpenAPI translation path retains representable required and string `maxLength` metadata and fails closed when an explicitly nullable required property cannot be represented or multiple operations declare incompatible validation contracts for the shared DTO; only `InboundRequestDto` emits passthrough `@NotNull`/`@CodePointLength(max=)`; controllers use `@Valid`; passthrough POMs include the validation starter; and validation-only advice returns the five-field sanitized 400 shape using field and constraint codes without rejected values. CRUD and passthrough use the same Unicode code-point semantics. Deterministic generated MockMvc and Maven proof covers OpenAPI 3.0/3.1 nullable rejection, a safe later operation sharing the same contract, omitted/explicit-null required values, ASCII and supplementary-Unicode max-plus-one/exact-bound behavior, zero collaborator calls for invalid input, dependency inventory, and standalone-app independence. At the #304 merge, coverage was top-level only; the reader-first residual closing nested resolution, unsupported-required fail-closed behavior, and diagnostic propagation is recorded in §6 without rewriting #304's historical boundary. | ✅ Coordinated annotation correction; no shared abstraction |
| **4 — IMPLEMENTED** | Security-header filter | `security_headers_emitter.py`, `engine.py` (3 call sites) | Delivered: one provenance-marked `OncePerRequestFilter` is emitted for every shipped profile and all three archetypes. Generated CRUD, passthrough, and Kafka JARs return exactly one value for each §7 header over real HTTP and no plain-HTTP HSTS. A test-only `emit_security=True` CRUD profile proves the same single-value contract alongside Spring Security without an IdP. Repeated generation is byte-identical for all three archetypes. | ✅ New bounded emitter and three call sites; no dependency or profile change |

**Proof is risk-scaled, not uniform.** Slice 1's doc/matrix portions need no Maven; its Kafka portion
does. Slice 2 needs CRUD-only generation + runtime, not all three archetypes. Slice 3 needs passthrough-
only. Slice 4 is the one slice that genuinely needs all three, because header wiring is per-archetype by
construction. No slice's acceptance criteria cite a historical test count.

### 12.1 Maintainer-facing tracker rows Slice 1 must reconcile

This design PR is deliberately **tracker-free** — the tracker is a derived, maintainer-facing status view,
not implementation authority, and tracker edits are serialised one-editor-at-a-time
([`docs/tracker/HOWTO-update.md`](../tracker/HOWTO-update.md)). But Option A invalidates two rows that
currently assert the opposite, and leaving them is a maintainer-visible falsehood.

| Row | What it says now | Why it is now wrong |
|---|---|---|
| `gate-genapp-auth-default` | `status: adopter-decides`, `priority: adopter-gate`, `wave: External gate`; summary ends *"The suite boundary map implies a shipping skeleton and must be corrected."* | Two defects. The posture is **no longer adopter-decided** — P1-5 resolved it as Engine-decided Option A. And the boundary-map correction it calls for **is done** (§11). The row should be repurposed to the residual adopter obligation (deploy/operate the required authenticated gateway) or closed with a pointer to this design, not left as an open gate. |
| `post-oauth2-idp-wiring` | *"The generated skeleton **ships unwired**; issuer/JWKS/audience/authority mapping are configured against the enterprise IdP post-import."* | **Flatly false** — the skeleton does not ship at all; no shipped profile emits it (§1 facts 1-3). There is no post-import IdP wiring task for a generated app under Option A. |

**Not stale, deliberately untouched:** `D2` (SSO / auth architecture) scopes Studio and KS SSO, not
generated-app auth, and is unaffected by this decision. A sweep of every tracker row mentioning
auth/OAuth2/security/pagination/passthrough/headers/rate-limiting/actuator found no third row invalidated
by Option A.

**Required of Slice 1 — choose one, and say which in the PR body:**

1. **Preferred:** update both rows in `docs/tracker/suite-tracker.json`, run `python3 docs/tracker/build.py`,
   and commit all three artifacts (JSON + generated `README.md` + `index.html`) **within Slice 1**. This
   is what `HOWTO-update.md` prescribes — Slice 1 is already editing the canonical source
   (`suite-security-review-backlog.md`), and the derived view should move alongside it rather than drift.
   Slice 1 then holds the tracker-edit lock: it must not land concurrently with any other tracker-touching
   PR.
2. **Alternative:** a named, immediately-following, tracker-only PR, serialised after Slice 1 merges.
   Acceptable if a tracker refresh is already in flight and would collide.

Either way the two rows must not survive Slice 1's merge window unreconciled.

## 13. Preserved invariants

Manifest `2.0`, deterministic generation, and regeneration behavior are unaffected — every slice changes
emission logic, not the manifest contract, and each carries its own determinism proof. Standalone-app
independence (§1 fact 10) is unaffected — Slice 3 adds a Spring Boot starter, not an EdgeForge component.

## 14. Open maintainer decisions

**No original posture decisions remain.** `MAX_PAGE_SIZE=200`/`MAX_PAGE_OFFSET=50_000`, shipping the
passthrough advice, the passthrough-local renderer, the Kafka health-only default, and the mandatory
authorization-envelope wording are all accepted decisions recorded above. Design is frozen and all
four original slices are implemented. The required-shape diagnostics follow-up recorded in §6 merged
via PR #305 and did not reopen the posture decision.
