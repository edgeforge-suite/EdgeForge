# Generated-App OpenAPI Artifact — Design

> **Status:** DESIGN **rev-6** — closes §10's four maintainer decisions. **Not another review round:**
> the design was source-verified stable at rev-5 (two consecutive APPROVE-WITH-REDLINES closing on
> mechanics, not architecture). rev-6 applies the sequencing/scope decisions Claude and Codex each made
> **independently** and then compared (2026-07-19) — all four aligned: O0 ships before O1 as its own
> reviewable refactor; O3 (HTTP serving) is deferred out of v1 entirely; `info.version` is confirmed as
> the shared Maven-version constant; and O0 itself splits into **O0a**/**O0b** (§8). Implementing (d)'s
> precise boundary also corrected one placement: **page-envelope schemas are O1-synthesized, not
> O0-extracted** — there is no Java class to extract them from (§0). Earlier corrections stand.
> **Grounding:** Engine `origin/main` @ **`663164a`** (committed source only). Everything not cited is
> **PROPOSED**.
> **Roadmap:** a generated-app standard artifact alongside DDL/migrations (shipped) and agent-context
> (M4). Belongs on [`generated-app-engine-roadmap.md`](generated-app-engine-roadmap.md).
> **Redlines honored:** **manifest-derived** (no runtime introspection) · **deterministic** (byte-stable
> body; the provenance header carries a run ID) · **no new runtime dependency** · **no egress** · no
> manifest-v2 semantic change · entity-CRUD first (§5).

---

## 0. Correction log (rev-1 → rev-2)

The audit **confirmed** the gap, the emit seam, the hash-comment header, enum availability as structured
rule data, the existence of generated exception→status mappings, and the Kafka N/A call. It **refuted or
qualified** the following, all verified at source and corrected here.

| # | rev-1 claim | Verified fact | Fixed in |
|---|---|---|---|
| 1 | "`op_contexts` is the single source of truth; drift is **structurally impossible**" | **REFUTED as a mechanism.** `op_contexts` (`java_emitter.py:547-592`) is *input*, not the final endpoint plan — the served surface is decided by controller-only branching (`:2218-2340,:2519-2670`), including generic fallbacks, explicit-read mode, pageable params, and a **literal** `@PutMapping("/{id}")` / delete route emitted even when a spec route uses a differently-named path parameter (`:2306-2335`). Two renderers reading `op_contexts` would *re-interpret* it, not share it. | §3.1 — extract a shared **`GeneratedCrudApiModel`** descriptor (new slice **O0**); extended in rev-3 to the schema half and all three renderers (#9) |
| 2 | "the **generated app's own endpoints**" | **OVER-SCOPED.** CRUD generation also emits real HTTP controllers beyond entity CRUD — e.g. `OutboundSoapActionController` (`@RequestMapping("/soap/outbound")`, `:7957+`), `FileIngestController` (`@RequestMapping("/files")`, `:10295+`), plus XML ingest/output, batch triggers and the config-gated demo UI. rev-1's AC3 checked entity controllers only. | §5 — v1 is the **entity-CRUD REST contract**; excluded surfaces named explicitly |
| 3 | "`info.version` from manifest app/engine version metadata" | **REFUTED — no such field.** `MetadataProject` carries `app_name` + `schema_version` (the *manifest* schema version), not an app version; the generated Maven version is **hard-coded `0.0.1-SNAPSHOT`** (`build_emitter.py:238`). Engine version is separate (`appbuilder/__init__.py:3` = `4.1.1`). | §3.5 — one named, existing, deterministic source |
| 4 | "status codes **read from** the generated handler mapping" | **REFUTED as stated.** The mappings are real (404/409/400, conditional 422 at `:1046-1163`; 201/200/204 at `:2211-2339`) but exist **only as rendered Java strings** — there is no structured catalog for a second emitter to read. | §3.4 — a structured response/error catalog in the descriptor |
| 5 | "field schemas are reachable" | **CONFIRMED WITH GAPS.** Types/formats/required exist (`metadata/models.py:96-122,:233-256`), but source **`nullable` is not retained** by OpenAPI ingestion (`ingestion/openapi_classifier.py:621-639` builds `CanonicalField` with `required=` and no nullable), and response DTOs carry no request-validation annotations. | §3.4 — define *generated-code* semantics, not source fidelity |
| 6 | Domain-specific fixture/framing + "legacy contract" | **VIOLATES `CONTRIBUTING.md:46`** ("keep committed content domain-agnostic"). rev-1 named a domain-specific generated app and framed the value around one industry. Upstream interfaces are also not necessarily *legacy* — they are **reviewed upstream contracts** (`contracts/manifest.py:39-47`). | throughout — neutral wording; in-repo citations only |
| 7 | springdoc "forfeits standalone / determinism / no-drift" | **OVERSTATED.** *Standalone* means no **EdgeForge** runtime dependency — springdoc would not break it. | §2 — narrower, still-sufficient rationale |
| 8 | O3 "a one-line static mapping" | **REFUTED.** `src/main/resources/` is **not** a Spring default static location, and secured profiles permit only `/actuator/health`, `/`, `/index.html` then `anyRequest().authenticated()` with JWT (`security_emitter.py:53-62`) — so `/openapi.yaml` would be **authenticated** unless `SecurityConfig` changes. | §6 — O3 is a real runtime/security change |

### rev-2 → rev-3 (the schema half + the zero-entity case)
The re-review confirmed all seven fixes above landed. Two residuals remained — the first is the *same*
class of error as #1, caught one layer down.

| # | rev-2 gap | Verified fact | Fixed in |
|---|---|---|---|
| 9 | Descriptor consumed by the **controller** and **OpenAPI** renderers only | **The DTO/entity renderer is a third independent producer**, so the spec could equal the descriptor while the descriptor disagreed with the emitted Java. Field membership + `@JsonProperty` aliases live at `java_emitter.py:1893-1924`; fallback DTO membership at `:1848-1889` (emitted `:634-679`); an update op with no response mappings returns the **domain entity** (`_operation_response_type`, `:2300-2313`), whose Jackson shape adds target-profile audit fields while relationships are `@JsonIgnore` (`:1559-1569`). | §3.1 — descriptor carries the **Java schema/field plan** (`java_type`, `origin`, `excluded`, `included_extras`); **three** renderers consume it; new **AC8** ties every `$ref` to a real emitted Java type |
| 10 | Where the descriptor is built was unspecified | **`emit_build_files` runs BEFORE `emit_java_sources`** (`generation/engine.py:170`, `:179`) — a descriptor built in the Java lane would not exist when the spec is emitted. | §3.1a — built **once before both lanes**, same immutable instance passed to each (**AC9**) |
| 11 | "every generated CRUD app contains `openapi.yaml`" | **FALSE for a real case.** The CRUD lane proceeds with **zero usable entities** when XML or SOAP contracts exist (`generation/engine.py:146-150`) — such an app has generated HTTP controllers but none in scope. | §5.0 — emit **only** when `endpoints` is non-empty; empty `paths: {}` rejected as misreadable; AC1 conditional + tested |
| 12 | "pinned, vendored OAS 3.0.3 schema" | Under-specified for a vendored third-party artifact. | §3.6 — record immutable upstream revision + **checksum** + **license/attribution** |

### rev-3 → rev-4 (response containers + the stale artifact)
| # | rev-3 gap | Verified fact | Fixed in |
|---|---|---|---|
| 13 | `response_schema_ref` modeled only DTO/entity **items** | Generated controllers return **containers** and a generated **error** type that are not DTO/entity schemas: `ResponseEntity<List<T>>` (`java_emitter.py:2290-2292,:2402-2404`), `ResponseEntity<Page<T>>` (`:2280,:2388`), and `ErrorResponse` — a **real emitted class** (`exception/ErrorResponse.java`, `:203`, rendered `:985-995`) with fields `timestamp · status · error · message · path`. | §3.4a — `response_body_shape` (`item`/`list`/`page`/`none`), a modeled `Page` wrapper, `ErrorResponse` registered in `schemas[]`; **AC8 extended to shapes** |
| 14 | "skip emission when there are no endpoints" (§5.0, mine) | **Left a stale artifact.** The prune is **Java-only** — `prune_stale_generated_java_sources` scopes to `src/main/java` and `rglob("*.java")` (`regeneration.py:108-113`); nothing under `src/main/resources` is pruned. An app that *loses* its CRUD surface would keep an `openapi.yaml` describing endpoints that no longer exist — the drift this artifact exists to prevent, reintroduced by my own rule. | §5.1 — bounded removal of a **`generated`-marked** `openapi.yaml` only; unmarked/edited file preserved+warned (**AC11**) |
| 15 | Slice ownership drifted from the ACs; a prose promise had no test | AC8 was unowned, AC9 unassigned, and "the README/agent-context carries the note" was an untested claim. | §8 — **O0 owns AC9**, **O1 owns AC10/AC11**, **O2 owns AC3+AC8**; the README statement becomes **AC10** |

### rev-4 → rev-5 (the Page model + fail-closed reserved path)
| # | rev-4 gap | Verified fact | Fixed in |
|---|---|---|---|
| 16 | "One reusable `Page` wrapper schema, modeled once, reused for every `page` response" | **Not buildable as OpenAPI, and not proven.** OAS 3.0.3 schema objects are **concrete**: an array's `items` must name one item schema, so one component cannot represent `Page<AccountResponse>` **and** `Page<TransactionResponse>`. Separately, the app has **no page-envelope DTO** — it serializes `PageImpl` directly, Spring Boot is pinned `3.3.5` (`target_profiles/catalog.py:34,:50,:66`), and there is **zero** `PageSerializationMode`/`EnableSpringDataWebSupport` configuration anywhere in the repo — confirmed absent by search. Spring Data's own docs state direct `PageImpl` serialization is **not guaranteed stable** outside `VIA_DTO`/`PagedModel`. AC8's "resolves to a real emitted Java type" also cannot hold for a schema with no backing class. | §3.4a — **concrete per-item envelope schemas** (e.g. `AccountResponsePage`), not one generic component; AC8 **narrowed** to item + `ErrorResponse` refs; a **new AC12** runtime test proves the envelope against the pinned baseline's actual JSON, with an explicit "re-verify on Spring Boot bump" rule; true stabilization named as later work (**O5**), out of scope here |
| 17 | "unmarked/adopter-edited file preserved and **warned**" | **Not fail-closed** — a warning still lets the run succeed with a stale or foreign file at the reserved path, in both directions (zero-endpoints removal case and non-empty overwrite case). And **"adopter-edited" is not a detectable state**: `read_edgeforge_ownership` (`regeneration.py:154-163`) reads only the marker line; a hand-edit that retains `EdgeForge-ownership: generated` is byte-indistinguishable from untouched output. `package_state_hash` (`change_plan.py:50`) is an apply-path plan/apply diff, not a stored per-file hash available to this cleanup. | §5.1 — reserved-path **preflight before any other mutation**; `generated`-marked ⇒ may write/remove; **anything else ⇒ hard-fail**, tested both directions; the undetectable "edited-but-marked" claim **dropped**, not fixed |
| 18 | *(P2)* Schema `origin` pseudocode (§3.1) listed only `mapped-dto \| fallback-dto \| domain-entity` | §3.4a already added `origin: generated-error`, and rev-5 adds the new `page-envelope` origin — neither was reflected in §3.1's own enum. | §3.1 — `origin` enum now lists all five; `java_type` marked `NULL` for `page-envelope` (no backing class) |

### rev-5 → rev-6 (§10 decisions closed; one placement corrected while implementing them)
Not review findings — the design was stable at rev-5. These are the outcomes of Claude and Codex each
independently recommending on §10's four maintainer decisions, then comparing: **all four aligned**
(full recommendations on PR #271). Implementing decision (d)'s precise O0a/O0b boundary surfaced one
genuine placement fix, logged the same as any other correction.

| # | What | Why | Fixed in |
|---|---|---|---|
| 19 | rev-5 put `page-envelope` in the descriptor's `schemas[]` as a fifth `origin`, alongside the Java-backed ones | **Wrong layer.** O0's whole point is "the Java type plan" — extracting facts about code that already exists. A page envelope has **no backing Java class** (`java_type: NULL`, as rev-5 itself already said) — there is nothing to *extract*. It is new OpenAPI-only content, synthesized at **render time** from `response_body_shape == page` + the item's own schema ref, using a fixed envelope template whose properties are what **AC12** proves against the pinned runtime. Putting it in O0's output implied a false symmetry with the four Java-backed origins. | §3.1 — `origin` enum reverts to the **four** Java-backed values; §3.4a states the envelope is **O1-synthesized, not O0-extracted**; §8 — envelope construction moves to **O1**, not O0b |

---

## 1. Current-state inventory (cited @ `663164a`)

- **Generated apps ship no API spec.** `emit_build_files` writes pom / Dockerfile / README / agent-context
  / `application.yaml` only (`build_emitter.py:30-103`); the generated pom's dependency block
  (`:194-221`) contains **no springdoc**.
- **Upstream specs are manifest input, not app output.** Upstream interfaces are manifest-declared
  (`contracts/manifest.py:39-47,:983-984`) and translation consumes their `spec`/`spec_url`
  (`metadata/translation.py:268-270`). They are **reviewed upstream contracts** — not necessarily legacy,
  and never emitted into the app.
- **Endpoint facts are split across two layers.** `op_contexts` carries DTO class names, spec path,
  mappings, method, shape, pageable flag and parameters (`java_emitter.py:547-592`) — but the **final
  served route/shape** is settled inside the controller renderer (`:2218-2340,:2519-2670`), which owns
  fallbacks, explicit-read mode, pageable parameters and the literal `/{id}` update/delete routes
  (`:2306-2335`). Shared route helpers exist (`generation/utils.py:94-170`) but stop short of a final
  endpoint plan.
- **Schema facts exist as data.** `CanonicalField` types/formats/required (`metadata/models.py:96-122`),
  operation parameters (`:233-256`), DTO membership + JSON names incl. `@JsonProperty` aliases
  (`java_emitter.py:1893-1924`), and enum allow-lists as structured `CanonicalRule.values`
  (`rules/models.py:28-42`, filtered/used at `java_emitter.py:3567-3589,:4341-4348`). **Not** retained:
  source `nullable` (`ingestion/openapi_classifier.py:621-639`).
- **Status mappings exist only as rendered Java** — handler 404/409/400 + conditional 422 (`:1046-1163`),
  controller 201/200/204 (`:2211-2339`).
- **Emit seam + header are ready.** `emit_build_files` (`build_emitter.py:30-103`);
  `render_generated_file_header(comment_style="hash")` (`audit.py:17-61`); ownership scanning is
  comment-style agnostic (`regeneration.py:154-177`).
- **Other generated HTTP surfaces exist** (§0 #2): `/soap/outbound`, `/files`, XML ingest/output, batch
  triggers, config-gated demo UI.

## 2. Why a build-time artifact (rationale, narrowed)

Enterprise **API-governance and gateway-onboarding** teams need the machine-readable contract to register
an endpoint, generate clients, and diff a change under review. Without it every adopter hand-authors one
per app, and across a multi-app estate those hand-authored specs drift.

Choosing **build-time generation over springdoc** is defensible on three honest grounds: the artifact is
**reviewable before boot** (it exists in the diff, not only in a running process), it adds **no new
runtime dependency or reflection**, and it can be made **byte-stable** and parity-tested in CI.
*(Correction, §0 #7: springdoc would **not** break generated-app "standalone" — that term means no
**EdgeForge** runtime dependency. The build-time choice stands on the three grounds above, not on an
absolute claim.)*

## 3. Design — PROPOSED

### 3.1 The mechanism: one extracted descriptor, consumed by all three renderers (§0 #1, #9)
rev-1 claimed drift was impossible because both renderers read the same metadata. That was wrong: today
the controller renderer *decides* the final surface internally, so an OpenAPI renderer reading
`op_contexts` would **independently reconstruct** it — the definition of drift risk.

**rev-2 made the *route* half real; rev-3 closes the *schema* half (§0 #9).** rev-2 had the controller and
OpenAPI renderers share the descriptor, but the **DTO/entity renderer remained a third, independent
producer** — so the spec could match the descriptor while the descriptor disagreed with the emitted Java.
The descriptor therefore carries the **exact Java schema/field plan** too:

```
GeneratedCrudApiModel                     # built ONCE per run (§3.1a), consumed by all three renderers
  endpoints[]:
    final_path            # after fallbacks/overrides — incl. the literal /{id} update/delete cases
    http_method
    parameters[]          # path · query · header · implicit pageable (page/size)
    request_schema_ref    # -> schemas[]
    response_schema_ref   # -> schemas[]; the ITEM type (entity-vs-DTO)
    response_body_shape   # item | list | page | none  -- the CONTAINER (§3.4a), not the item
    responses[]           # success + error statuses, each with its own body shape (§3.4a)
  schemas[]:                              # the Java TYPE PLAN — only schemas with a real backing class.
                                          # Page envelopes are NOT here (§3.4a): no Java class exists to
                                          # extract them from; O1 synthesizes them at render time (§0 #19).
    java_type             # the class actually emitted — always present for every entry here
    origin                # mapped-dto | fallback-dto | domain-entity | generated-error
    properties[]          # contract JSON name (incl. @JsonProperty alias), type/format,
                          # required, enum values (from the same filtered rule data)
    excluded[]            # Jackson-invisible members, e.g. @JsonIgnore relationships
    included_extras[]     # target-profile audit fields visible on a domain-entity response
```

**Three renderers, one plan:** the Spring **controller** renderer, the **DTO/entity** renderer, and the
**OpenAPI** renderer all consume it. Drift is prevented by *construction plus tests*, stated honestly:
- **machine:** the OpenAPI output equals the descriptor (AC3);
- **machine:** controller-codegen tests assert each endpoint entry yields the expected Spring
  annotation/signature;
- **machine:** **schema-codegen tests** assert each `schemas[]` entry yields a real emitted Java class whose
  Jackson-visible fields match exactly — JSON name/alias, type/format, required/validation, enum, and the
  `excluded`/`included_extras` behavior (AC8). This is what ties the spec to the Java, rather than to a
  second interpretation of it.

**Why the schema half needed this.** Field membership and `@JsonProperty` aliases are decided in the DTO
renderer (`java_emitter.py:1893-1924`), fallback DTO membership separately (`:1848-1889`, emitted
`:634-679`), and an update operation with no response mappings can return the **domain entity**
(`_operation_response_type`, `:2300-2313`) — whose Jackson shape includes target-profile audit fields while
relationships are `@JsonIgnore` (`_render_relationship_field`, `:1559-1569`). None of that is derivable
from the endpoint plan alone.

### 3.1a Where the descriptor is built (orchestration — §0 #10)
`emit_build_files` runs **before** `emit_java_sources` (`generation/engine.py:170` then `:179`). A
descriptor built inside the Java lane would therefore **not exist** when the spec is emitted. So the
descriptor is **built once, before both lanes**, and the *same immutable instance* is passed to
`emit_build_files` (spec) and `emit_java_sources` (controllers + DTOs). No lane rebuilds or re-derives it.

**The extraction is two behavior-preserving slices, not one** (§8, decided §10): **O0a** lifts the
endpoint plan out of the controller renderer; **O0b** lifts the schema/field plan out of the DTO renderer
and hoists the combined descriptor's construction ahead of both emit lanes. Both are proven by existing
generated-app tests, *with no output change*. Only then does O1 render from the result.

### 3.2 Source of truth, not passthrough
The spec describes the **generated app's entity-CRUD surface** as the descriptor defines it — it is **not**
a copy of an upstream spec, which may differ from what is generated. Upstream specs remain design-time
provenance in the manifest package.

### 3.3 Emission, header, location
Emitted from `emit_build_files`, ownership **`generated`**, header via
`render_generated_file_header(comment_style="hash")`, at **`src/main/resources/openapi.yaml`** — packaged
with the app and versioned with it. **Packaging ≠ serving**: that path is *not* a Spring default static
location, so serving is a separate, real change (§6, O3). Format: OpenAPI **3.0.3** YAML.

### 3.4 Schema, parameter and status fidelity (§0 #4, #5)
- **Requiredness / nullability — generated-code semantics, not source fidelity.** Source `nullable` is not
  retained by ingestion, so the spec states what the **generated code enforces**: `required` from
  `CanonicalField.required` / validation annotations on request DTOs; response properties are **not**
  marked required unless the generated code guarantees them. The design says this explicitly rather than
  implying round-trip fidelity.
- **Property names** use the contract JSON name, honoring `@JsonProperty` aliases
  (`java_emitter.py:1893-1924`).
- **Parameters** include path, query, header **and the implicit pageable `page`/`size`** where the
  descriptor marks an endpoint pageable.
- **Enums** are rendered from the **same filtered `CanonicalRule.values`** the ServiceBase renderer uses
  (`:3567-3589,:4341-4348`) — same filter, same ignore rules; never inferred from Java text.
- **Responses** come from a **structured response/error catalog** in the descriptor (success 201/200/204 +
  handler-mapped 404/409/400 and conditional 422), authored once and consumed by both the handler/controller
  renderers and the spec. Where a status is policy rather than per-endpoint fact, it is declared as a fixed
  policy and parity-tested — **not** "read from" rendered Java.

### 3.4a Response **body shapes** — containers and the error body (§0 #13)
A `response_schema_ref` names the **item** type. Real generated controllers return that item inside a
**container**, or return a generated **error** type — neither of which is a DTO/entity schema. All three
are modeled explicitly:

| `response_body_shape` | Generated Java | OpenAPI rendering |
|---|---|---|
| `item` | `ResponseEntity<T>` | `$ref` to the item schema |
| `list` | `ResponseEntity<List<T>>` (`java_emitter.py:2290-2292,:2402-2404`) | `type: array`, `items: $ref` |
| `page` | `ResponseEntity<Page<T>>` (`:2280,:2388`) | see below — **no single generic wrapper** |
| `none` | `ResponseEntity<Void>` / 204 | no response body |

- **The error body is a real generated schema.** `ErrorResponse` is emitted as
  `exception/ErrorResponse.java` (`java_emitter.py:203`, rendered `:985-995`) with the exact field set
  `timestamp: string · status: integer · error: string · message: string · path: string`. It is registered
  in `schemas[]` **once, globally** (`origin: generated-error`) — unlike per-entity item schemas, it is not
  *derived from* the descriptor per endpoint; the descriptor references a fixed Java class that already
  exists, and the DTO/entity renderer does not consult the descriptor to produce it. A dedicated parity
  test (below) ties the reference to that real file. It is referenced by **every** declared error status
  (404/409/400, conditional 422) — not described inline, and not invented.

**The `page` shape needed correction (§0 #16).** OpenAPI 3.0.3 schema objects are **concrete, not
generic** — `content: {type: array, items: $ref}` must name **one** item schema, so a single reusable
`Page` component cannot represent `Page<AccountResponse>` **and** `Page<TransactionResponse>`. rev-4's
"one wrapper, reused" was unbuildable as an OpenAPI artifact. Fixed:
- **A concrete envelope schema per item type**, generated deterministically from the item schema name
  (e.g. `AccountResponsePage`), each `{content: array of $ref-to-item, …page metadata}` — not one shared
  component, not an inline-per-operation schema (which would duplicate the envelope shape across every
  paginated endpoint).
- **Synthesized by O1 at render time, not carried in the O0 descriptor (§0 #19).** `GeneratedCrudApiModel.schemas[]`
  is the **Java type plan** — it exists to describe classes that are actually emitted. There is no Java
  class here to extract a plan *from*; O1 derives the envelope name and shape purely from a `page`-marked
  endpoint's `response_body_shape` + `response_schema_ref` (both of which **are** in the O0 descriptor)
  and a fixed, documented envelope template. O0's job stops at marking `response_body_shape: page`; O1
  owns turning that marker into a concrete schema.
- **The envelope's own properties are NOT a Java-DTO parity claim.** There is no `AccountResponsePage.java`
  — Spring serializes `PageImpl` directly, and **Spring Data's own docs state this representation is not
  guaranteed stable** unless `PageSerializationMode.VIA_DTO`/`PagedModel` is configured — which this repo
  does **not** configure (`target_profiles/catalog.py` pins Spring Boot `3.3.5`; no
  `EnableSpringDataWebSupport`/`PageSerializationMode` anywhere in the emitters). So **AC8's "resolves to a
  real emitted Java type" is narrowed to item DTO/entity refs + `ErrorResponse`** — the page envelope's
  shape is a claim about the **pinned framework's runtime behavior**, not about EdgeForge-emitted code, and
  is proven differently:
  - a **generated-app runtime serialization test** asserts the actual JSON a live paginated endpoint
    returns, on the pinned Spring Boot baseline, matches the envelope schema's properties exactly;
  - this is an **explicit, pinned assumption, not an eternal guarantee** — the design states plainly that
    bumping the Spring Boot baseline requires re-running this test before the envelope schema can be
    trusted, and a failure there is a signal to revisit page serialization (§9, O5), not silently ignored.
  - **This stays behavior-preserving** (no runtime-output change, no new dependency) — it adds a *test*
    that locks in what the pinned framework already does, rather than *changing* what it does. Actually
    configuring `PageSerializationMode` for a stable envelope is a **separate, later, runtime-behavior
    change** to every generated app's paginated JSON shape — out of scope here (§9, O5).
- **Parity (AC8) covers shapes, not just items:** a `list` response must render as an array; a `page`
  response must `$ref` its **concrete per-item envelope schema**, whose modeled properties are asserted
  against real runtime JSON by the serialization test above; and each error status must `$ref` the
  generated `ErrorResponse` whose emitted Java fields match. A shape mismatch fails the build exactly like
  a route mismatch.

### 3.5 `info` block — one named, existing source (§0 #3)
There is no manifest app version. v1 therefore uses:
- **`info.title`** = `metadata.app_name`;
- **`info.version`** = the **generated Maven project version** — today the hard-coded `0.0.1-SNAPSHOT`
  (`build_emitter.py:238`), promoted to a **single shared constant** so pom and spec cannot disagree;
- **Engine generator version** (`appbuilder/__init__.py:__version__`) recorded as an OpenAPI extension
  (e.g. `x-edgeforge-engine-version`), not as `info.version`.

**Confirmed at the maintainer decision** (§10.4c) — including the explicit non-goal: no adopter-reviewed
application-version concept is introduced here; that would be a separate, later, additive design.

### 3.6 Determinism + validation (§0, redline 4)
- **Canonical ordering is specified, never left to defaults:** paths sorted; HTTP methods in a fixed
  order; schemas and properties sorted; `required` lists sorted; enum values in the rule's declared order.
  No reliance on dict/set iteration or YAML emitter defaults.
- **Byte-stability is body-only** — the provenance header carries a run ID, exactly as for every other
  generated file.
- **Validation is named and offline:** a **pinned, vendored OAS 3.0.3 JSON Schema** checked with the
  repo's existing pinned `jsonschema` dependency, run as a **test-only** gate. *(Maven compile does not
  validate OpenAPI; rev-1 implied it might.)* No network, no new runtime dependency.
  **The vendored artifact carries its own provenance (§0 #12):** the immutable upstream revision/commit it
  was taken from, a recorded **checksum**, and its **license/attribution** — the same supply-chain hygiene
  the repo applies to pinned scan tools. Refreshing it is a reviewed change, not a silent copy.

## 4. Invariants held
No new runtime dependency · no reflection · no egress · no manifest-v2 semantic change · `generated` ownership so
the regenerate/refresh + prune lanes behave as for any other generated file.

## 5. Scope — v1 is the entity-CRUD REST contract (§0 #2)

### 5.0 Zero entity-CRUD endpoints ⇒ emit nothing (§0 #11)
The CRUD lane legitimately proceeds with **zero usable entities** when XML or SOAP contracts exist
(`generation/engine.py:146-150` fails only when there are *no* entities **and** no XML **and** no SOAP).
Such an app has generated HTTP controllers but **none in this artifact's scope**.

**Rule: emit `openapi.yaml` only when `GeneratedCrudApiModel.endpoints` is non-empty.** The alternative —
a valid but empty `paths: {}` document — was considered and **rejected**: an empty entity-only spec sitting
beside real, excluded SOAP/XML HTTP routes is easy for a gateway reviewer to misread as *"this app exposes
nothing."* Absence is the less misleading signal. The rule is explicit and tested (AC1), never incidental.

**The generated README states which case applies** — either the spec's path, or that this app has no
entity-CRUD REST surface. That is a **testable requirement** (AC10), not a promise in prose.

### 5.1 Skipping is not enough — the stale spec must be removed (§0 #14)
"Skip emission" alone leaves a **stale artifact**: regeneration prunes the **Java tree only** —
`prune_stale_generated_java_sources` scopes to `output_dir/src/main/java` and `rglob("*.java")`
(`regeneration.py:108-113`). Nothing under `src/main/resources` is ever pruned. So an app that **loses**
its entity-CRUD surface on regeneration would keep serving up an `openapi.yaml` describing endpoints that
no longer exist — the exact drift this artifact exists to prevent, reintroduced by my own §5.0 rule.

**Preserve-and-warn was not fail-closed, and the design over-claimed what is detectable (§0 #17).** rev-4
said an unmarked file would be "preserved and warned" — but a *warning* still lets the run **succeed**
with a stale or foreign file sitting at the reserved path, which is exactly the misleading-artifact
outcome this section exists to prevent. Worse, rev-4 implied "adopter-edited" is a distinguishable state:
it is not. `read_edgeforge_ownership` (`regeneration.py:154-163`) reads **only the marker line** — nothing
else — so a hand-edited file that retains `EdgeForge-ownership: generated` is byte-indistinguishable from
untouched generated output. `package_state_hash` (`change_plan.py:50`) detects plan-vs-apply drift on the
**apply path**; it is not a stored per-file content hash available to this cleanup, and adding one is out
of scope here. The design cannot claim a detection capability that does not exist.

**Rule — one reserved-path preflight, before either emit lane mutates output** (the same preflight-then-
mutate discipline M4 uses for Legacy Notes, `generated-app-agent-guardrails-design.md` §3.5):
1. Before generation touches `src/main/resources/openapi.yaml`, read whatever exists at that path today
   (if anything) and classify it — **not** "generated vs. edited" (undetectable), but the only distinction
   the marker actually supports: **`generated`-marked**, or **anything else** (unmarked, `developer`-marked,
   or absent).
2. **`generated`-marked** ⇒ EdgeForge **may** write, overwrite, or remove it this run, per §5.0's
   endpoints-empty/non-empty rule.
3. **Anything else present and non-empty** ⇒ **preserve it and hard-fail the run** with remediation
   guidance (move or remove the conflicting file) — in **both** directions of the collision: a
   zero-endpoints run that would otherwise remove a stale spec, and a non-empty run that would otherwise
   overwrite with fresh output. Neither may proceed past this file silently.
4. **The preflight runs before any other mutation in the run** — before README/build-file writes — so a
   failure leaves the package in its **prior** state, never partially refreshed.

This is **new work** (the existing prune cannot be reused as-is) and belongs to the emitting slice (O1).
**AC11** now asserts: the `generated`-marked write/remove path; the **hard failure** (not a warning) on any
non-`generated` file, tested in **both** the zero-endpoints and non-empty cases; and that the failure
precedes every other mutation in the run.
**In:** the generated **entity-CRUD** REST endpoints (create/get/update/delete/list, incl. pageable
variants and explicit-read/additional operations that the descriptor covers).

**Explicitly out of v1, and named as such in the emitted spec's own description** so no reader mistakes it
for the app's complete HTTP surface: `/soap/outbound` outbound-SOAP actions · `/files` file ingest · XML
ingest/output · batch triggers · the config-gated demo UI. Adding these is a **later, per-surface slice**,
not a v1 gap.

**Archetypes:** CRUD only in v1. **Kafka-router = N/A** (no generated business REST controller).
**REST-passthrough is deferred** — it *does* have a compact structured REST surface
(`passthrough_emitter.py:41-113,:277-368`), so this is a scheduling choice, **not** a metadata-maturity
blocker.

**Deployment-auth semantics:** v1 **omits** security schemes and therefore is **not, by itself, a complete
gateway-registration contract** for secured target profiles (which authenticate all non-permitted routes
with JWT — `security_emitter.py:53-62`). Emitting a target-profile-derived bearer/JWT security scheme is a
named follow-on (§7, O4).

## 6. Serving is a real change, not a mapping (§0 #8)
`src/main/resources/openapi.yaml` is **packaged but not served** by default. If serving is adopted (O3):
- it needs an explicit resource handler or controller — not a one-line static mapping;
- under **secured** profiles the route is authenticated unless `SecurityConfig` explicitly permits it —
  a **security decision**, not a convenience;
- it requires tests for the chosen access policy **and** non-regression of `/` and `/index.html` (the
  currently-permitted routes).
O3 stays **independent** of O1/O2; the artifact is useful as a packaged, diffable file with no serving at
all.

## 7. Acceptance criteria
1. **Emitted + valid, and only when in scope:** every generated CRUD app **with a non-empty entity-CRUD
   surface** contains `src/main/resources/openapi.yaml`, valid against the **pinned vendored OAS 3.0.3
   schema** (offline, test-only). A CRUD-lane app with **zero** entity-CRUD endpoints (XML/SOAP-only,
   §5.0) emits **no** `openapi.yaml` — asserted by a test, not left incidental.
2. **Determinism:** two generations from the same manifest produce **byte-identical bodies** (provenance
   header excepted), with the §3.6 canonical ordering asserted.
3. **Parity against the descriptor (the load-bearing AC):** the emitted spec's `{path × method}` set,
   parameters, schema refs and declared responses **equal the `GeneratedCrudApiModel`**; and separate
   controller-codegen tests assert each descriptor entry yields the expected Spring annotation/signature —
   including the literal `/{id}` update/delete cases and pageable parameters. Mismatch fails the build.
4. **Scope honesty:** the spec's description names the excluded HTTP surfaces (§5); AC3's route set is the
   entity-CRUD set **only**, and no excluded surface silently appears.
5. **Fidelity:** enum values match the ServiceBase-filtered rule data; property names honor
   `@JsonProperty` aliases; required/nullable follow §3.4's generated-code semantics.
6. **Invariants:** no new runtime dependency; `docker build` + boot unchanged; provenance header present
   and the file behaves as `generated` through regenerate.
7. **Serving (only if O3):** the chosen access policy is tested, and `/` + `/index.html` still resolve
   under both open and secured profiles.
8. **Schema parity to the emitted Java (§0 #9) — the second load-bearing AC, scope corrected (§0 #16):**
   every **item** `$ref` (mapped DTO, fallback DTO, domain entity) and the `ErrorResponse` `$ref` resolve
   **both** to `components.schemas` **and** to a **real emitted Java type**, with schema-codegen tests
   asserting that type's Jackson-visible fields match the descriptor **exactly** — JSON name/alias,
   type/format, required/validation, enum values, `excluded` (`@JsonIgnore` relationships), and
   `included_extras` (audit fields on a domain-entity response). **`page`-shaped responses are NOT claimed
   as a Java-type match** — there is no `{Item}Page.java`; a `page` response `$ref`s its **concrete
   per-item envelope schema** (§3.4a), and that envelope's modeled properties are instead asserted against
   the **pinned Spring Boot baseline's actual serialized JSON** by a dedicated runtime test (§3.4a, AC12).
   `list` still renders as a plain array.
9. **One descriptor, one build:** the model is constructed **once before** both emit lanes and the same
   instance reaches `emit_build_files` and `emit_java_sources` (§3.1a) — asserted so no lane can silently
   re-derive it.
10. **README states the case:** the generated README names either the emitted spec's path or the fact that
    the app has no entity-CRUD REST surface (§5.0) — a test, not a prose promise.
11. **No stale spec, fail-closed (§5.1) — corrected from "preserve and warn":** the reserved-path preflight
    runs **before any other mutation** in the run. A `generated`-marked `openapi.yaml` may be
    written/overwritten/removed per §5.0. **Any other file present at that path — unmarked or
    `developer`-marked — causes the run to hard-fail** with remediation guidance, tested in **both**
    directions: zero-endpoints (would-be removal) and non-empty (would-be overwrite). The design does
    **not** claim to detect an edit that retains the `generated` marker — `read_edgeforge_ownership` reads
    only the marker line, and no prior-content hash is added here.
12. **Page-envelope runtime parity (§0 #16, new):** for each `page`-shaped response, a generated-app
    runtime test asserts the live endpoint's actual serialized JSON matches the envelope schema's declared
    properties, on the **pinned** Spring Boot baseline (`3.3.5`). A Spring Boot baseline bump requires
    re-running this test before the envelope schema may be trusted; a failure is a signal to revisit page
    serialization (§9, O5), never silently ignored or auto-adjusted.

## 8. Build slicing

**O0 splits into O0a/O0b** — decided in §10 (Claude + Codex independently aligned): O0 grew across
rev-1→rev-5 from "extract the endpoint plan" to also cover the Java schema/field plan, the orchestration
hoist, and response shapes. One PR touching that much of `java_emitter.py` — the Engine's largest,
most-drift-prone file — is a worse safety property than two, each independently provable
behavior-preserving against the existing test suite.

- **O0a** `[CHORE]` **Endpoint/response-plan extraction.** Final routes (incl. the literal `/{id}`
  update/delete cases), parameters (path/query/header/implicit pageable), `response_body_shape`
  (item/list/page/none), and the status-response catalog — from the **controller/handler** renderer only.
  **Behavior-preserving, zero output change**, proven by existing controller-output tests.
- **O0b** `[CHORE]` **Java schema/field-plan extraction + the orchestration hoist.** Mapped-DTO,
  fallback-DTO, domain-entity, and `generated-error` schema plans (§3.1) — from the **DTO/entity**
  renderer — **then** constructs the single immutable `GeneratedCrudApiModel` (O0a's plan + O0b's plan)
  **once, before** `emit_build_files` and `emit_java_sources` both run (§3.1a). **Behavior-preserving,
  zero output change**, proven by existing DTO/entity-output tests. **Owns AC 9** — the hoisting proof is
  what closes O0b. **Page-envelope schemas are explicitly NOT built here** (§0 #19) — there is no Java
  class to extract them from; that is O1's job.
- **O1** `[FEATURE]` Render + emit `openapi.yaml` from the descriptor in `emit_build_files`: the §3.5
  `info` sources, §3.6 ordering, the §3.4a response body shapes (**incl. synthesizing the concrete
  per-item page-envelope schemas** — new work at this layer, not carried over from O0b), the §5.0
  emit-only-when-in-scope rule, the §5.1 **fail-closed reserved-path preflight**, and the README statement
  — **ACs 1, 2, 4, 5, 6, 10, 11**.
- **O2** `[FEATURE]` Parity + codegen + runtime tests — **route parity (AC 3), schema/shape parity (AC 8),
  and the page-envelope runtime serialization test (AC 12)** — the three legs of the guarantee that make it
  real. **AC12 is a real generated-app boot-and-call test**, not a unit test — sized accordingly.
- **O3** `[FEATURE]` *(deferred out of v1 entirely — §10)* Serving + access policy + non-regression tests
  (AC 7). Ships the packaged file only in v1; if built later, **defaults to no HTTP serving** rather than
  widening `SecurityConfig` for every secured-profile app.
- **O4** `[FEATURE]` *(later)* Target-profile-derived security scheme, for a complete gateway contract.
- **O5** `[FEATURE]` *(later, separate design)* **Stabilize page serialization at the runtime level** —
  e.g. configure `PageSerializationMode.VIA_DTO`/`PagedModel` — so the envelope is a documented Spring
  contract instead of a pinned-baseline assumption. **This changes every generated app's paginated JSON
  shape**; it needs its own gated design (a real runtime-behavior change, redlined out of O0's
  behavior-preserving scope), not a line item here.

**Order (§10, decided): O0a → O0b → O1 → O2.** O3 deferred out of v1 entirely; O4/O5 remain later,
separately-gated tracks. **Sizing, revised for the split:** O0a **small-to-medium**, O0b **medium**
(carries the schema plan + the hoist — the harder half of what was one "O0+O1 medium" line before), O1
**medium** (now also owns page-envelope synthesis), O2 **medium** (AC12's runtime test is real weight).
Covering every generated HTTP surface would make this **large** — hence the §5 scope decision.

## 9. Out of scope
springdoc / Swagger-UI / any runtime spec generation · the excluded HTTP surfaces (§5, later per-surface
slices) · passthrough and Kafka specs · a generated-vs-upstream conformance note · client-SDK generation ·
the estate descriptor + tracing bootstrap (separate briefs) · any manifest-v2 semantic change · **configuring
`PageSerializationMode`/`PagedModel` or any other change to generated apps' actual paginated JSON shape**
(§8, O5 — a runtime-behavior change needing its own gated design).

## 10. Decisions
1. **Build-time render, not springdoc** — reviewable-before-boot, no new runtime dependency, testable
   byte-stability (§2, without the rev-1 overstatement).
2. **Drift prevention = extracted shared descriptor + parity tests**, not "one parent metadata."
3. **v1 = entity-CRUD contract**, excluded surfaces named in the artifact itself.
4. **Sequencing/scope — DECIDED 2026-07-19.** Claude and Codex each recommended independently, then
   compared; all four aligned (no maintainer tie-break needed):
   - **(a) O0 ships before O1, as its own reviewable refactor** — never folded into the emission PR. It
     changes the structural source of generation inside the Engine's largest, most drift-prone emitter
     while promising zero output change; that guarantee needs its own provable, revertible PR, or a
     regression in extraction becomes indistinguishable from a change in spec rendering.
   - **(b) O3 (HTTP serving) is deferred out of v1 entirely.** The packaged file already delivers the
     stated value (review, CI diff, gateway onboarding, client-gen) with zero runtime-behavior change.
     Serving adds a new endpoint and an access-policy decision under secured profiles that deserves its
     own opt-in design — not a decision improvised inside a documentation artifact. If built later, it
     **defaults to no HTTP serving**, never to widening `SecurityConfig` globally.
   - **(c) `info.version` = the shared generated-Maven-version constant — confirmed.** It is the only
     value that versions the generated *application artifact itself* (`schema_version` versions the
     manifest *format*; the Engine version identifies the *generator*). Promoting the current hard-coded
     `0.0.1-SNAPSHOT` to one named constant, read by both `pom.xml` and `info.version`, is truthful and
     prevents drift. **Explicit non-goal:** if EdgeForge later introduces an adopter-reviewed application
     version, that supersedes the constant through its own additive design — inventing that concept now
     is unnecessary for v1.
   - **(d) O0 splits into O0a/O0b** (§8) — endpoint/response-plan extraction, then schema/field-plan
     extraction + the orchestration hoist. O0 had grown across five rounds to cover both; splitting
     isolates the riskiest edits without fragmenting the work into artificial micro-PRs, and gives AC9's
     hoisting proof a clear, single slice to close.
   - **Execution order: O0a → O0b → O1 → O2.** O3 deferred; O4/O5 remain later, separately-gated tracks.

**Full independent recommendations:** Engine PR #271 — [Claude](https://github.com/santosh-sh/EdgeForge/pull/271#issuecomment-5017999936) · [Codex](https://github.com/santosh-sh/EdgeForge/pull/271#issuecomment-5017972451).
