# Generated-App Event Delivery — Architecture Review & Design

> **Status:** DESIGN **rev-5 — APPROVE-FOR-GATE** (Codex, `7ef45d3` + this one-line row-9 fix). Closes
> the final residual P2 (§3 row 9 categorical-identity wording) from the rev-4 review, on top of rev-4
> (1 P1 + 2 P2 from rev-3), rev-3 (3 P1 + 3 P2 from rev-2), and rev-2 (7 P1 + 11 P2 from rev-1) — see
> §0. **Four adversarial review rounds; the outbox direction held throughout, mechanics converged.**
> Load-bearing mechanics as gated: durable sequence allocator (profile-appropriate atomic upsert —
> PostgreSQL `ON CONFLICT … RETURNING`, no exception-driven control flow — with a unique-constraint
> fail-closed backstop, profile-pinned by a blocking Slice-2b spike); claim-token-fenced lease
> lifecycle; carried-forward `internal_schema` baseline entry; absent-feature byte-identity scoped by
> package history (never-enabled AC1 vs previously-disabled AC1b) and branched by the open §13.1
> transaction-policy decision.
> **This design selects the Phase-A mechanism, answers its open question Q1, and unblocks
> implementation** — it does not itself deliver Phase A ([`cross-service-integration-design.md`](cross-service-integration-design.md)
> §5). Design/research only — no Engine, Studio, or generated-app implementation until gated.
> **Grounding:** Engine `origin/main` @ **`57820f8`** (committed source only). The DDA rebuild packet
> (external `06-domain-events/` + `04-implementation/edgeforge-generation-scope.md`) is a **concrete
> scenario only**, and its shape is **not independently repo-verifiable** — DDA-derived statements are
> marked as packet-sourced, never as source-verified. Everything not cited is **PROPOSED**.
> **Prior art this design is bound by:**
> - Edge-contract roadmap **decision 12**: outbox/CDC belongs to the **cross-service track**
>   (`docs/edge-contract-expansion-roadmap.md:637-638`) — not a new edge-contract family.
> - Cross-service **Phase A** (`cross-service-integration-design.md:163-196`) decided the **reliability
>   properties** — publish only after confirmed commit, broker-ack before dispatch-marking, idempotent
>   retry — via *"transactional outbox **or equivalent**"*. **Prior art did not select outbox
>   specifically; this ADR does**, over the permitted equivalents (§3, §4). Q1 (`:291-304`) records
>   three open manifest options; §5 chooses one.
> - Quality gate **E5** requires the local-transaction-vs-outbox boundary be **explicit**
>   (`generated-app-quality-gate-v1.md:297`) — it does **not** prescribe unconditional service
>   transactions (rev-1 over-claimed this; §0 #4). **E8** keeps event sourcing a separate architecture
>   profile (`:300`).
> - `idempotency_key` is advisory, **Phase-4 design-first** (`identity-role-engine-behavior-design.md:52`).
> - Hook additions must follow the **regenerate-maintain protocol**: safe default in the generated
>   base + hooks-available notification + regen-summary logging (`regenerate-maintain-model-design.md:184-190`).
> **Redlines honored:** nothing DDA-specific hard-coded · Kafka not assumed the only future broker
> (§4.6 — honestly scoped, not fake-abstracted) · **no exactly-once business-processing claim** ·
> consistency and ordering trade-offs stated, incl. the ones that hurt (§4.2, §8) · existing manifests
> + generated apps preserved (one-way compatibility stated precisely, §5.3) · developer extension
> points explicit + regeneration-safe **per the repo's own protocol** (§7.3) · no mandatory EdgeForge
> runtime dependency · contract generation separated from runtime behavior.

---

## 0. Correction log (rev-1 → rev-2 → rev-3 → rev-4 → rev-5)

### 0.0 rev-1 → rev-2 (the rev-1 REWORK review: 7 P1 + 11 P2)

That review **confirmed**: decision-12 framing, E5/E8/idempotency gates, no CRUD service-level
transaction, AsyncAPI zero-references, `downstream_interfaces` closed to `message_schema`, kafka
idioms reusable-as-patterns, entity⇒public-REST (no per-entity suppression exists —
`java_emitter.py:518-545,:682-710`), profiles/ownership/Flyway rows, and that both §13 maintainer
decisions were framed genuinely open. It **refuted or qualified** the following; all accepted.

| # | rev-1 claim/mechanic | Verified fact | Fixed in |
|---|---|---|---|
| 1 | Per-aggregate ordering via row-level `SKIP LOCKED` + row-id order, **and** "one bad row never blocks the queue" | **Self-contradictory.** Row-level `SKIP LOCKED` lets a second worker claim aggregate A's row 2 while row 1 is in flight; DB id allocation can differ from commit visibility; and a `PARKED` row 1 forces a choice rev-1 refused to make: publish row 2 (ordering broken) or block (the "never blocks" claim false). | §4.2 — **aggregate-granularity claims + `aggregate_seq`**; a parked row **blocks its own aggregate only**, stated as the accepted cost |
| 2 | `PENDING/DISPATCHED/PARKED` with no claim lifecycle; "H2 single-instance" as the whole overlap story | **Undefined mechanics.** Nothing said whether the DB TX spans the broker send (long locks) or commits first (double-claim without a lease); H2 "single instance" doesn't prevent overlapping scheduler runs in one instance. | §4.4 — **`IN_FLIGHT` + owner/lease lifecycle**, crash windows enumerated, fixed-delay single-flight scheduling, per-mode behavior |
| 3 | Recorder as a ServiceBase constructor parameter; no-op `enrichEvent` default in the **developer** file | **Breaks the repo's own seam.** The base constructor is deliberately kept stable so preserved subclasses don't go stale (`java_emitter.py:3601-3607`, explicit comment; subclass scaffold passes only the repository, `:4450-4488`); and the regen protocol requires new hooks to ship a **safe default in the generated base** + notification (`regenerate-maintain-model-design.md:184-190`) — a default in the developer file never reaches existing apps. | §7.3 — setter/provider injection, hook default in ServiceBase, protocol-compliant notification, regenerate-existing-package compile AC |
| 4 | "`afterCreate`/`afterUpdate` keep their current meaning" under the new outer transaction; E5 "compels" unconditional `@Transactional` | **False and over-claimed.** Today `afterCreate(saved)` runs after the save TX returns (`:3946-3947`); under an outer service TX it runs **before commit**, its exception now rolls back the aggregate, and its external side effects fire pre-commit. E5 requires the boundary be *explicit*, not *unconditional*. | §7.1/§7.2 — semantic change documented + tested; §13.1 re-framed with this evidence, recommendation softened to a genuinely open decision |
| 5 | Delete lifecycle bindings may map aggregate/request fields | **Not constructible.** Generated delete never loads the entity: `existsById → beforeDelete(id) → deleteById` (`:3879-3885`). | §5.2/§7.4 — v1 delete payloads = **id/system values only**; optional `snapshot: true` opt-in loads-before-delete with stated cost |
| 6 | Outbox migration "immutable once emitted", table "survives removal" | **Desired outcomes stated as mechanics.** The schema baseline/Change-Plan model covers entity SQL, not this internal infra table; numbering, idempotency, and removal behavior were unspecified. | §6.1 — baseline + Change-Plan integration, V-next numbering, greenfield/regen/cross-branch Flyway ACs |
| 7 | "Guarded replay/park endpoint" | **Not a control.** Secured profiles authenticate it incidentally; unsecured/local would expose an endpoint that deliberately re-duplicates delivery. | §4.5 — disabled by default, management-class surface, role/CSRF/audit posture, both-profile ACs |
| 8 | "The only generated transaction boundaries are the 3 annotated controllers" | **Too narrow** — generated Spring Batch jobs carry `PlatformTransactionManager` chunk/tasklet machinery (`java_emitter.py:11953-12074,:12525-12654`). | §1 row corrected: *no CRUD service-level transaction; ingest + batch lanes already have transaction machinery* |
| 9 | "`async_routes`+`kafka_config` schema-bound together" | **Wrong mechanism, right conclusion** — the schema requires both only **when** `app_archetype: kafka-integration` (root `if/then`, `manifest-v1.schema.json:155-167`); nothing forbids them on CRUD — they are *operationally ignored* by CRUD translation/dispatch (`metadata/translation.py:227-250`; `generation/engine.py:60-81`). | §1 + §5.1 wording corrected |
| 10 | "pom has no micrometer", "7 dependencies" | Actuator (emitted) brings micrometer-core **transitively**; the pom is conditional (SOAP, OAuth resource-server, PostgreSQL, Flyway-Postgres). What's absent is an explicit **metrics registry/instrumentation**. | §1 row corrected |
| 11 | "Resolves Phase A"; "the suite already decided outbox" | A design resolves the *question*, not the capability; prior art decided the *reliability properties* and the *track*, not outbox specifically. | Header + §2 + final decision re-worded |
| 12 | Byte-identity claims un-qualified per slice; "after Slice 2" stale; retention both generated and deferred; correlation described as existing; veto semantics singular; SOAP "inherits bindings"; Kafka-shaped contract called broker-neutral; `operation_id` binding key ambiguous | All accepted. | AC1 formally defined + slice-qualified (§9.1); §10 labels fixed; retention default-disabled (§4.5); correlation specified as **new work** with UUIDv4 (§7.5); per-event `Optional`-style veto contract (§7.3); non-CRUD entry points enumerated honestly — SOAP inbound is read-only today, **no SOAP mutation events in v1** (§7.4); Kafka-shaped fields kept **with the honest statement** that non-Kafka transports need additive evolution (§4.6); binding key = **`{interface, operation_id}`** or validated project-wide uniqueness (§5.2) |
| 13 | No sequencing note vs other approved-but-unbuilt designs | Real merge/proof risk: OpenAPI **O0a/O0b** hoists shared CRUD endpoint/schema construction around the same emitter (`generated-app-openapi-artifact-design.md:419-454`); M4 **B2b** adds the artifact registry + agent-context facts (`generated-app-agent-guardrails-design.md:470-474`). | §10.1 — explicit cross-design build order |

---

### 0.1 rev-2 → rev-3 (the rev-2 re-review: 3 P1 + 3 P2)

Rev-2 was confirmed on prior-art framing, the constructor-stable seam, generated-base hook default,
per-event veto scope, parked-blocks-own-aggregate, replay posture, retention default, non-CRUD scope,
compatibility wording, cross-design sequencing, and both §13 decisions staying open. Three rev-2
*fixes* were themselves only partial, and are now closed:

| # | rev-2 mechanic | Verified defect | Fixed in |
|---|---|---|---|
| 14 | `aggregate_seq = max(seq)+1`, "serialized by the aggregate row's own write lock", cross-aggregate bindings *warned* | **Unsafe twice.** No generated code takes any lock — repo-wide there is no `@Lock`, `LockModeType`, `PESSIMISTIC_*`, `saveAndFlush`, or `FOR UPDATE` in `appbuilder/**`; update is a plain `findById → save` (`java_emitter.py:3761-3823`), so reading the aggregate acquires **nothing** and two concurrent mutations can read the same max. Independently, retention pruning (§4.5) can lower or erase the max ⇒ **sequence reuse**. And warning on a binding that cannot serialize contradicts a *strict* ordering guarantee. | §4.2 — **`outbox_aggregate_sequence` cursor** (conditional `UPDATE` = the serialization point, independent of the aggregate table), `UNIQUE (aggregate_type, aggregate_id, aggregate_seq)` fail-closed backstop, cursor **survives pruning**; the cross-aggregate edge **dissolves** (nothing warned-and-allowed). AC3 extended to same-aggregate concurrency, multi-event, retention-then-next, cross-aggregate |
| 15 | `owner_id` + `lease_expires_at`, outcome transitions unconditional | **Stale-owner state corruption**, not merely a duplicate: A outlives its lease → B reclaims → A's late ack/failure overwrites B's state (`DISPATCHED`→`PENDING`, attempts, park). | §4.4 — unique **`claim_token`** per claim; **every** outcome is a CAS on `(id, status=IN_FLIGHT, claim_token, owner_id)`; zero rows ⇒ stale owner abandons silently; **database clock** for lease predicates. New AC4b |
| 16 | "table survives removal" + additive apply + code removal | **Impossible together.** `build_schema_baseline` is a pure function of current metadata emitting only `entities`/`staging_tables` (`schema_baseline.py:84-123`); disappearance ⇒ `removed`/`destructive` (`change_plan.py`); `apply` raises on destructive **before** regeneration (`apply.py:53-81`) ⇒ the plan aborts before any code is removed. Rev-2 also conflated package-inventory conflict with live-DB conflict. | §6.1 — **`internal_schema` baseline section carried forward from the committed baseline** even when the section is absent ⇒ no drop delta, code removal proceeds, explicit drop still blocked; plan-time vs Flyway-time conflicts separated; AC6 now five cases |
| 17 | `null` vetoes an event | For a reliability feature, an accidental missing return would **silently suppress a required event**. | §7.3 — `Optional<EventDraft>`; `Optional.empty()` is the only veto; **`null` throws and rolls back** (fail-closed) |
| 18 | AC1 "holds through Slices 1, 2b, 3, 4, 5" while 2a annotates every app | Under option §7.1(a) nothing is byte-identical to the *pre-feature* Engine after 2a, so the claim is unsatisfiable as written. | §9 — two explicit branches: (a) exact identity through Slice 1, 2a = annotation-only delta, later slices diffed vs the **post-2a** baseline; (b) exact AC1 throughout |
| 19 | "(a) also makes multi-write flows (cross-entity rule checks + save) atomic"; §7.2 covered rollback + side-effect timing only | Those checks are **reads** — a transaction boundary alone does not make a read-then-write race safe. And the outer TX has a third observable effect rev-2 missed: a hook mutating the managed entity is now **dirty-checked and persisted**, where today it is silently lost. | §7.1 rationale narrowed (withdrawn claim stated); §7.2 now lists **three** changes with the persisted-mutation case tested both ways (AC5b) |


### 0.2 rev-3 → rev-4 (the rev-3 re-review: 1 P1 + 2 P2)

Rev-3 was confirmed on the durable allocator as the right replacement for `max(seq)+1`, the unique
constraint + retained cursor making ordering fail-closed and retention-safe, claim-token CAS + database
clock closing stale-owner corruption, `internal_schema` carry-forward resolving the removal trilemma,
and the hook/veto/AC1-branch corrections. Three residual defects, all accepted:

| # | rev-3 mechanic | Verified defect | Fixed in |
|---|---|---|---|
| 20 | First-cursor allocation: `UPDATE` → if zero rows `INSERT` → **on unique violation retry as `UPDATE`**, inside the recording transaction | **Not buildable on PostgreSQL.** A uniqueness violation aborts the transaction until rollback unless the insert sits behind an explicit savepoint, so catch-and-continue in the same Spring transaction fails; opening a new transaction would break atomicity with the aggregate and outbox row. | §4.2 — **profile-appropriate atomic upsert, no exception-driven control flow**: PG `INSERT … ON CONFLICT … DO UPDATE … RETURNING`; H2 ensure-row → increment → same-transaction read under the row lock; savepoints only with proof. Column renamed **`last_allocated_seq`** (off-by-one ambiguity removed). **Blocking Slice-2b spike** pins exact syntax and proves concurrent first-allocation on **both** H2 (`MODE=PostgreSQL`, `catalog.py:40`) and real PostgreSQL |
| 21 | AC1 / matrix row 9 / final decision: "apps without `event_publications` are byte-identical / zero-cost" | **False for one of two package histories.** After the §6.1 carry-forward, a package that *previously enabled* events keeps its outbox tables, migrations, allocator, and baseline entry by design — it is not byte-identical to a never-enabled package. | §9 — AC1 scoped to **History A (never enabled)**; new **AC1b** states the *disable* invariant for History B (no event runtime, scheduling, Kafka dependency, or new migrations; committed DB artifacts and baseline entry intentionally retained). §3 row 9 and the final decision qualified to match |
| 22 | Future cursor cleanup "may restart at 1 once no local outbox rows remain — safe because no older row exists" | **Unsound:** external consumers may still hold the prior sequence long after local pruning; restarting misorders against *their* state, which this app cannot observe. | §4.2 — assertion **withdrawn**; v1 rule is simply **cursors are never pruned**; any future cleanup/id-reuse needs its own aggregate-incarnation contract |
| 23 | AC5b: hook mutation "persists under (a), not under (b)" | **Half the matrix.** Under option (b) an **event-enabled** app also gets the outer transaction, so the mutation persists there too. | §7.2 + §9 — the real four cells: event-enabled ⇒ persists under both; event-absent ⇒ persists under (a), today's behavior under (b) |


### 0.3 rev-4 → rev-5 (the rev-4 focused re-review: APPROVE-FOR-GATE with one residual P2)

Codex confirmed the allocator redesign, AC1/AC1b histories, the four-cell hook matrix, and the
withdrawn cursor-restart claim as gate-sound, and gave **APPROVE-FOR-GATE** contingent on one wording
fix I had reintroduced: §3 row 9 still asserted never-enabled apps "generate identically" *categorically*,
dropping the §13.1 exception that Slice 2a (option a) makes those apps non-identical to the pre-feature
Engine. Fixed to route through AC1's §13.1-dependent contract. Rode-along polish: §12 no longer calls
the aggregate-incarnation contract "the only condition" for safe cursor cleanup — §4.2 states it as a
prerequisite, not a sufficient condition.


## 1. Current-state capability inventory (deliverable 1 — cited @ `57820f8`)

| Capability | State | Evidence |
|---|---|---|
| **Manifest: async/Kafka** | `async_routes`+`kafka_config` required **only for `app_archetype: kafka-integration`** (root `if/then`); not forbidden on CRUD, but CRUD translation/generation dispatch **ignores** them — operationally unusable for a CRUD producer | `manifest-v2.schema.json`; `metadata/translation.py:227-250`; `generation/engine.py:60-81` |
| **Manifest: domain-event producer** | Absent — `downstream_interfaces` is closed (`interfaceDefinition`, no `message_schema`); recorded as `gap: producer-manifest-pending` | `manifest-v2.schema.json`; `cross-service-integration-design.md:89-92` |
| **Manifest: domain-handler consumer** | Absent (`gap: consumer-domain-handler-pending`) | cross-service §3.1 `:66-77` |
| **AsyncAPI** | Zero references in `appbuilder/**` — packaged, never consumed | repo-wide search |
| **CRUD transaction boundaries** | **No CRUD service-level transaction** — create is hooks/rules → `repository.save` (`java_emitter.py:3936-3947`), delete is `existsById → beforeDelete(id) → deleteById` (`:3879-3885`), no annotation, no `TransactionTemplate`. **Ingest + batch lanes DO have transaction machinery**: the three annotated controllers (`:10308,:10877,:11230`) and generated Spring Batch jobs with `PlatformTransactionManager` chunk/tasklet transactions (`:11953-12074,:12525-12654`) | as cited |
| **Kafka runtime idioms (archetype)** | Producer factories, `DeadLetterPublishingRecoverer`/DLQ template, retry/backoff — reusable **as generation patterns, not shared code** (outputs stay standalone) | `kafka_emitter.py:287-302,:313-344,:380-424` |
| **Idempotency** | None generated; `idempotency_key` advisory, Phase-4 gated | `identity-role-engine-behavior-design.md:52,:167-177` |
| **Correlation** | Kafka archetype: correlation policy/store (router runtime). **CRUD: none** — no request-correlation context, no fallback generation; cross-service names it a *target* invariant | `cross-service-integration-design.md:51-56` |
| **Audit** | `audit_emitter.py` = JPA auditing stamps, flag-gated (default off) | `audit_emitter.py:1-14` |
| **Observability** | Actuator emitted (micrometer-core arrives **transitively**); exposure is **health-only**; no explicit metrics registry or generated instrumentation; tracing bootstrap is a separate planned brief | `build_emitter.py:194-221,:970-978` |
| **pom (CRUD)** | Conditional: web/validation/jpa/actuator/batch/flyway/h2/test **plus** conditional SOAP, OAuth resource-server, PostgreSQL, Flyway-Postgres | `build_emitter.py:194-221` |
| **Migrations** | Flyway per entity; immutable once emitted; additive generated; destructive fails closed at apply | `apply.py:67-81`; regeneration machinery |
| **Ownership / regeneration** | generated vs developer lanes; ServiceBase generated / `{Entity}Service` developer; **base constructor deliberately stable** so preserved subclasses don't go stale; **new hooks must ship safe defaults in the base + notification** | `file_writer.py:22-45`; `regeneration.py:101-120,:154-177`; `java_emitter.py:3601-3607,:4450-4488`; `regenerate-maintain-model-design.md:184-190` |
| **Developer extension points** | Per-entity hooks in the developer subclass (`beforeCreate/afterCreate/…/initializeDefaults`) — `afterCreate(saved)` currently runs **after** the save transaction returns | `java_emitter.py:3946-3947` + hook renders |
| **Profiles / DBs** | 3 profiles, Spring Boot 3.3.5; H2 local default, PostgreSQL proven in L5 | `target_profiles/catalog.py:34,:50,:66` |
| **SOAP inbound** | **Read-only** handlers, calling repositories directly (not the CRUD service) | `java_emitter.py:8647-8745` |
| **Outbox today** | Expressible only as a plain manifest entity ⇒ **public CRUD REST endpoints for the outbox** (no per-entity REST suppression exists, `:518-545,:682-710`) with no atomic wiring and no publisher — evidence it must be an **internal generated component** | as cited |
| **DDA trigger** *(packet-sourced, not repo-verifiable)* | 11 operations→events, each `implementation: transactional-outbox-custom`; domain-neutral envelope (`event_id … partition_key, data`); declares at-least-once / `partition_key: aggregate_id` / dedupe `event_id` | external `06-domain-events/*` |

**Load-bearing findings:** (1) there is **no CRUD service transaction for an outbox row to join** —
establishing one is a prerequisite with real compatibility consequences (§7.1-7.2, §13.1); (2) prior
art fixed the **reliability properties and the track** — the *mechanism* choice is this ADR's to make
and defend (§3).

## 2. Problem statement

Generated apps mutate aggregates but cannot reliably announce it; event contracts are packaged cargo
(AsyncAPI/JSON Schemas/matrices) with nothing binding them to mutations. Every adopter needing events
hand-builds the same plumbing inside generated apps — and hand-built "publish after save" is exactly
the shape Phase A's blocking constraint exists to forbid. The mechanics (atomic capture, ordered
delivery, retry, replay) are domain-independent → generation-owned; the content (which operations,
which payloads) is contract data → manifest/Studio-owned; business judgment → developer hooks. Same
three-layer split as every other Engine capability.

## 3. Decision matrix (deliverable 2 — unchanged verdicts from rev-1, wording tightened)

| # | Alternative | Verdict | Core reason |
|---|---|---|---|
| 1 | Direct write + sync publish | **REJECT** as reliability mechanism | loses events (commit-then-publish) or emits phantoms (publish-then-commit) — the anti-pattern Phase A names |
| 2 | **Outbox + in-app polling publisher** | **SELECT — generate** | atomic with the local TX; at-least-once honestly; works on H2 with no broker; no new ops deps |
| 3 | Outbox + CDC/Debezium | **Optional later adapter (Slice 6, gated)** | Connect+Debezium ops weight; Postgres-specific; H2-impossible; never default |
| 4 | Table-CDC without outbox | **REJECT** | persistence schema becomes the public contract; intent lost |
| 5 | Kafka transactions / EOS | **REJECT as consistency mechanism** | broker-side atomicity only — does not span the DB; producer idempotence kept as hygiene |
| 6 | XA/2PC | **REJECT** | Kafka has no XA; the pairing doesn't exist in this stack |
| 7 | Event sourcing | **REJECT for generation** (answers Q5: out of scope) | E8: separate architecture profile; abandons the CRUD legacy-compatible mission |
| 8 | Hooks + developer publisher | **PARTIAL — subsumed** | recorder+hooks are the seam; capture-only (Slice 2b) passes through this state; leaving the publisher app-owned re-creates N hand-builds |
| 9 | No capability | **REJECT as end state; PRESERVED as default** | apps that **never enabled** events follow AC1's §13.1-dependent identity contract; previously-enabled packages satisfy AC1b (§9); the DDA packet shows the gap concretely |

## 4. Selected architecture (ADR-EV1) — corrected mechanics

**Consistency:** the event row commits/rolls back with the aggregate in one local DB transaction
(§7.1 establishes it). **Delivery: at-least-once** — duplicates possible by design, `event_id` is the
dedupe key. **Never claimed:** exactly-once business processing; cross-aggregate or cross-topic
ordering; synchronous delivery semantics for HTTP callers.

### 4.1 Components
`DomainEventRecorder` (generated; the single write path — §7.3 injection) · outbox table/entity/
migration **+ the `outbox_aggregate_sequence` allocator** (generated, **internal**, no REST — §4.2, §6.1) · `OutboxPublisher` (generated poller — §4.3/4.4)
· Kafka producer adapter (`enable.idempotence=true`, `acks=all`; archetype idioms as patterns) ·
operator surface (§4.5). `spring-kafka` enters the pom **only when `event_publications` is declared**.

### 4.2 Ordering — durable allocator, fail-closed (§0 #14, #20, #22)
`aggregate_seq`, not the row id, is the **ordering authority** (id-allocation vs commit-visibility
inversion is out of the contract). Rev-2 allocated it as `max(seq)+1`, which was **unsafe twice
over** — no generated code takes any row lock (repo-wide: no `@Lock`, `LockModeType`,
`PESSIMISTIC_*`, `saveAndFlush`, or `FOR UPDATE` anywhere in `appbuilder/**`; update is a plain
`findById → save`, `java_emitter.py:3761-3823`), so "reading the aggregate into the transaction"
acquires nothing and two concurrent mutations can read the same max; and pruning dispatched rows
(§4.5) can lower or erase the max, letting a later event reuse a sequence. Both are fixed by moving
the authority out of the event rows entirely:

- **Durable allocator table (generated, internal):** `outbox_aggregate_sequence` keyed by
  `(aggregate_type, aggregate_id)` holding **`last_allocated_seq`** — the most recently *issued*
  value, so the first allocation for an aggregate yields `1` (rev-3's `next_seq` left an off-by-one
  ambiguity; the name now states which it is).
- **Allocation is a conditional write, never exception-driven control flow (§0 #20).** Rev-3
  specified "`UPDATE`; if zero rows `INSERT`; on unique violation retry as `UPDATE`" — **not
  buildable on PostgreSQL**, where a constraint violation aborts the transaction until rollback, so
  catching it and continuing in the same Spring transaction fails, and opening a new transaction
  would break atomicity with the aggregate and the outbox row. The generated allocator therefore
  uses a **profile-appropriate atomic upsert with no catch-and-continue path on any profile**:
  - **PostgreSQL** — one statement:
    `INSERT INTO outbox_aggregate_sequence(aggregate_type, aggregate_id, last_allocated_seq) VALUES (?,?,1)
    ON CONFLICT (aggregate_type, aggregate_id) DO UPDATE SET last_allocated_seq =
    outbox_aggregate_sequence.last_allocated_seq + 1 RETURNING last_allocated_seq`.
  - **H2** — the same effect without relying on `RETURNING`: ensure-row (idempotent insert) →
    `UPDATE … SET last_allocated_seq = last_allocated_seq + 1` → read the value **in the same
    transaction under the update's row lock**. *(The H2 profile already runs `MODE=PostgreSQL`,
    `target_profiles/catalog.py:40`, which narrows the dialect gap — but the exact accepted syntax
    is **not verifiable from this repository**, so it is pinned by a Slice-2b spike (below) rather
    than asserted here.)*
  - Savepoint-backed alternatives are permitted only with proof that the outer mutation transaction
    remains usable afterward; the default design avoids savepoints entirely.
  **Slice-2b spike (blocking):** pin the exact statement per profile and prove concurrent
  first-allocation on **both H2 (MODE=PostgreSQL) and real PostgreSQL** before the recorder lands.
- **Why this serializes:** the write itself takes the cursor row's lock, so **the allocator
  serializes same-aggregate mutations on its own row** — no dependency on the aggregate table being
  locked, and therefore no dependency on the mutation even touching that aggregate. Rev-2's
  "cross-aggregate binding" edge case **dissolves**: a binding whose mutation never writes the target
  aggregate serializes on the cursor exactly like any other. Nothing is warned-and-allowed.
- **Fail-closed backstop:** `UNIQUE (aggregate_type, aggregate_id, aggregate_seq)` on the outbox
  table. If any allocation path is ever wrong, the transaction fails and the mutation rolls back —
  a duplicate sequence can never commit. Strict ordering fails closed rather than degrading silently.
- **Retention-safe:** the allocator is the durable high-water mark and **survives event-row pruning**.
  **Cursor rows are never pruned — that is the v1 rule, full stop.** *(Growth is bounded by distinct
  aggregate ids, one narrow row each. Rev-3 speculated that a future cleanup could safely restart an
  aggregate at 1 once no local outbox rows remain — **withdrawn** (§0 #22): external consumers may
  still retain the prior sequence long after local pruning, so restarting would misorder against
  *their* state, which this app cannot observe. Any future cursor cleanup or id-reuse needs its own
  aggregate-incarnation contract, designed separately.)*
- **Publish order:** per aggregate, strictly ascending `aggregate_seq`. Achieved by **claiming at
  aggregate granularity** (§4.3-4.4), never row-granularity `SKIP LOCKED` across the whole table.
- **A `PARKED` row blocks its own aggregate — and only its own aggregate.** This is the deliberate
  resolution of the rev-1 contradiction: strict per-aggregate ordering is kept; the cost is
  head-of-line blocking *within a poisoned aggregate*, which is surfaced (health shows parked
  aggregates + oldest-blocked age) rather than silently bypassed. Other aggregates flow freely. If an
  adopter prefers bypass-over-blocking for some event type, that is a **later, explicit, per-binding
  relaxation** — not a v1 default.

### 4.3 Publisher algorithm (aggregate-granularity claims, fenced)
Each cycle: select aggregates having dispatchable work (earliest non-terminal row is `PENDING` and
due) → for each, **claim the aggregate** by marking that earliest row `IN_FLIGHT` with a fresh
`claim_token`, `owner_id`, and `lease_expires_at` (§4.4) → publish → **compare-and-set** the outcome
on that token → continue to the aggregate's next row. One in-flight row per aggregate ⇒ ordering by
construction across any number of publisher instances; competing claims collide on the row update and
lose cleanly.

### 4.4 Claim lifecycle with ownership fencing (§0 #2, #15)
States: `PENDING → IN_FLIGHT → DISPATCHED | PENDING(retry) | PARKED`, in three **separate short
transactions** — claim (commit; no DB lock held during network I/O), broker send **outside any DB
transaction**, outcome transition (commit).

**Fencing (the rev-2 gap).** A lease alone prevents an ordinary double-claim but not a *stale owner*:
owner A outlives its lease, owner B legitimately reclaims, then A's late ack or failure overwrites B's
newer state — corrupting `DISPATCHED` back to `PENDING`, inflating `attempts`, or parking a row B
owns. Therefore:
- Every claim assigns a **unique `claim_token`** (fresh per claim, not per owner).
- **Every** outcome transition is a compare-and-set:
  `UPDATE outbox_event SET … WHERE id=? AND status='IN_FLIGHT' AND claim_token=? AND owner_id=?`.
- **Zero rows updated ⇒ the owner is stale ⇒ it abandons the row silently** (warn-log + metric), never
  retries the transition, and never touches the aggregate's later rows in that cycle.
- **Lease timestamps come from the database clock** (`CURRENT_TIMESTAMP` in the claim/expiry
  predicates), not from application clocks — no cross-instance skew assumption is required. Lease
  duration is configured above the worst-case send timeout; expiry is the only path that un-claims.

**Crash windows** (each lands on at-least-once, never on corruption): crash after claim ⇒ lease
expires ⇒ reclaim ⇒ possible re-send ⇒ **duplicate**; crash after broker ack before `DISPATCHED` ⇒
same; slow owner overtaken mid-send ⇒ duplicate **plus** a fenced no-op transition by the stale owner.

**Scheduling:** fixed-**delay** (never fixed-rate) + an in-process single-flight guard ⇒ no
same-instance overlap; multi-instance correctness rests on the fenced CAS above, not on deployment
assumptions (H2 deployments remain documented single-instance for other reasons). **Modes:**
`disabled` (no broker — capture only, rows visible via the operator surface, health reports
accumulation) · `log` (dev) · `kafka`.

### 4.5 Retry, park, replay, retention (§0 #7, #12; allocator interaction §0 #14)
Capped attempts with exponential backoff per row; exhaustion ⇒ `PARKED` (the outbox **is** the
producer-side dead-letter surface). **Replay is disabled by default.** When enabled: a
management-class endpoint (actuator-style, not an ordinary public controller), **role-gated under the
secured profile** (never in the permit-list — `security_emitter.py:53-62` already authenticates
non-permitted routes), **explicitly opt-in via configuration on unsecured/local profiles**, POST-only
with the app's CSRF posture, every invocation audit-logged (actor, row ids, outcome), and idempotent
(`PARKED → PENDING` only; replaying a non-parked row is a no-op error). **Retention pruning of
`DISPATCHED` rows defaults to DISABLED** — deleting rows is adopter data-retention policy (rev-1
contradicted its own gap table here); the generated job exists but activates only when the operator
sets an explicit retention window. **Pruning never touches the allocator cursor** (§4.2) — the ordering high-water mark must outlive the rows.

### 4.6 Broker portability — honest, not abstracted (§0 #12)
The manifest fields stay Kafka-shaped (`topic`, `partition_key`): inventing transport-neutral
vocabulary for brokers the Engine does not support would be speculative abstraction. **Stated
plainly:** a future JMS/MQ adapter (parked `EC-mq-jms`) will require **additive** manifest evolution
(destination/ordering semantics differ); the publisher/adapter seam isolates the runtime, not the
contract.

## 5. Manifest proposal (deliverables 5–6) — answers Q1

### 5.1 Shape: new optional top-level `event_publications`
Rejected: extending `downstream_interfaces` (closed edge-contract families; decision 12 fences events
out of that model) and reusing `async_routes` (archetype-conditional and **operationally ignored** by
CRUD dispatch — §1; forcing CRUD through it couples lanes). Selected: a new optional top-level
section, per the `manifest-additive-candidates` discipline.

### 5.2 Shape (PROPOSED; names final at Slice-1 review)
```yaml
event_publications:                    # optional; absent = feature entirely off (AC1)
  defaults:
    delivery: at-least-once            # the only valid value in v1
    partition_key: aggregate_id
  events:
    - event_type: ACCOUNT_OPENED
      topic: account-events
      aggregate: Account
      payload_schema: schemas/account-event-payload.schema.json
      bindings:
        - interface: account-api       # binding key = {interface, operation_id} (§0 #12)
          operation_id: openAccount
        - lifecycle: create
      payload_mapping:                 # explicit allowlist — nothing unmapped is ever emitted
        account_id: { source: aggregate, field: accountId }
        status:     { source: aggregate, field: accountStatus }
        opened_by:  { source: system,   value: correlation_id }
```
Three corrections from rev-1: **bindings key on `{interface, operation_id}`**
(or Slice-1 validation enforces project-wide `operation_id` uniqueness — `operation_id` alone can
repeat across upstream interface documents); **delete/lifecycle-delete bindings may map only
id/system sources in v1** — an optional `snapshot: true` loads the aggregate before deletion inside
the transaction (stated cost: one extra read + the row lock) and unlocks aggregate-field mapping;
**multi-event bindings define veto per event** (§7.3).

### 5.3 Compatibility — one-way, stated precisely (§0 #12)
Additive-optional means: the **new** Engine accepts all **old** manifests unchanged, and absence of
the section ⇒ behavior per AC1. It does **not** mean old Engines accept new manifests — a manifest
carrying `event_publications` is rejected by earlier v2 Engines (root schema is closed,
`manifest-v2.schema.json`; the committed schema itself changes). Slice 1 also adds: the Pydantic
model, `payload_schema` participation in `referenced_paths()`/package-existence validation, and Studio
packaging tests.

## 6. Ownership map + migration integration

### 6.1 Retained internal schema — resolving the removal trilemma (§0 #16)
Rev-2 asserted three things that **cannot hold together** against the current machinery:
`build_schema_baseline` is a pure function of *current* metadata emitting only `entities` +
`staging_tables` (`schema_baseline.py:84-123`); a table that disappears from the new baseline is
classified `removed`/`destructive` (`change_plan.py`, *"dropping tables is destructive"*); and
`apply_change_plan` raises on any `unsafe`/`destructive` delta **before** regeneration runs
(`apply.py:53-81`). So on removal of the last binding, rev-2 could not simultaneously remove the
generated code, keep the table, and complete an additive apply — the plan would abort first. The fix
is a real, statable machinery change, not a wish:

- **Baseline gains an `internal_schema` section** recording infrastructure tables enabled for the
  package (the outbox + its allocator), alongside `entities`/`staging_tables`.
- **Carry-forward rule:** `build_schema_baseline` takes the **committed prior baseline** as an
  additional input and copies existing `internal_schema` entries forward **even when
  `event_publications` is absent**. (This is precisely where it stops being a pure function of current
  metadata — called out as a design consequence for the Slice-1 review, not smuggled in.)
- **Therefore, removing the last binding** produces **no table-drop delta**: the generated recorder,
  publisher, adapter, and config disappear (generated lane), the tables remain in the baseline, and
  apply completes additively. An **explicit** drop request stays destructive and blocked — the safe
  posture is preserved, not bypassed.
- **Re-enabling** finds the entry already present ⇒ no duplicate migration, no renumbering.
- **Two distinct conflict surfaces, correctly separated** (rev-2 conflated them): a package/migration
  **inventory** collision — the table is already in the baseline or a migration file already claims
  it, e.g. after a cross-branch merge — is detected **at plan time**; an **arbitrary live-database**
  table the package never recorded is undetectable from static package state and surfaces **at Flyway
  apply**, which is the correct owner of live-DB conflict.
- **AC6 (extended):** enable · disable-with-table-retained (plan additive, code removed, baseline keeps
  the entry) · re-enable (no duplicate migration) · cross-branch inventory collision at plan time ·
  explicit-drop refusal — each with a real Flyway run (§9).

Ownership rows otherwise as rev-1 (recorder/publisher/entity/migration generated; `enrichEvent`
**override** developer-owned; hand-written flows developer-owned) with one correction: the no-op
`enrichEvent` **default lives in generated ServiceBase** (§7.3).

## 7. Runtime semantics — corrected

### 7.1 The transaction boundary — a real decision, honestly framed (§0 #4, #19)
Mutating CRUD service methods need a service-level transaction for atomic capture. Two honest options:
- **(a) Unconditional** `@Transactional` on mutating ServiceBase methods for all apps: one ServiceBase
  shape, and the selected repository operations plus the outbox write share one transaction; **but it
  is a behavior change for every regenerated app** — hook semantics change (§7.2) and any developer
  code relying on post-commit hooks breaks. *(Rev-2 also claimed it makes "multi-write flows
  (cross-entity rule checks + save) atomic" — withdrawn: those checks are **reads**, and a transaction
  boundary alone does not make a read-then-write race safe. That needs locking or a stricter isolation
  level, neither of which is generated (§4.2) nor proposed here.)*
- **(b) Only-when-events:** zero change for non-event apps; **two ServiceBase shapes** to maintain and
  test, and the drift hazard that implies.
E5 requires the boundary be **explicit**; it does not choose between these. **§13.1 puts the choice to
the maintainer with the §7.2 evidence attached** — rev-1's "unconditional, recommended, E5 compels it"
is withdrawn as over-claimed.

### 7.2 What the outer transaction changes about existing hooks (§0 #4, #19)
Today `afterCreate(saved)`/`afterUpdate(saved)` run **after** the repository proxy's transaction
returns — their exceptions cannot roll back the save, and their side effects happen post-commit. Under
an outer service transaction they run **inside** it. Three observable changes, all documented and
tested, listed in the regen summary, none claimed as a no-op:
1. an exception now rolls back the aggregate (and the event row);
2. external side effects fire **pre**-commit;
3. **a hook that mutates the managed entity now persists it** — the entity is still managed, so the
   mutation is dirty-checked and flushed at commit, where today the save transaction has already
   returned and such a mutation is silently lost. This is the change most likely to alter existing
   behavior *without any error surfacing*, so it gets its own test across the full matrix — **an
   event-enabled app persists the mutation under either §13.1 option** (option (b) adds the outer
   transaction precisely when events are declared); an **event-absent** app persists it under (a) and
   keeps today's non-persisting behavior under (b). (Rev-3 stated only the second row — §0 #23.)

**Hook order with events:** `beforeX → rules → save → afterX (existing, unchanged position) → build
envelope → enrichEvent (§7.3) → record`. The recorder runs **last**, so enrichment sees the final
entity state including `afterX` mutations.

### 7.3 The developer seam — protocol-compliant (§0 #3)
- **Injection:** `DomainEventRecorder` reaches ServiceBase via **setter/provider injection into the
  generated base** (e.g. an `@Autowired ObjectProvider<DomainEventRecorder>` field) — the constructor
  signature **does not change**, preserving the documented stability contract
  (`java_emitter.py:3601-3607`). Preserved subclasses recompile untouched (AC, §9).
- **Hook:** `enrichEvent` ships as a **no-op default in generated ServiceBase**; developer subclasses
  *optionally* override — per the regen protocol (`regenerate-maintain-model-design.md:184-190`),
  with agent-context "hooks available" refresh + regen-summary logging of the new hook.
- **Veto contract (per event, explicit and fail-closed — §0 #17):** for each event a binding produces
  the hook is invoked once —
  `Optional<EventDraft> enrichEvent(EventDraft draft, T entity)`. Returning a present draft (mutated or
  not) emits it; **`Optional.empty()` is the only way to veto**, and vetoes exactly that one event —
  other events of the same binding proceed. **A `null` return is a programming error, not a veto**: it
  throws and rolls back the mutation, so an accidental missing return can never silently suppress a
  required event (rev-2's `null`-vetoes contract could). A **thrown exception rolls back the whole
  mutation** — aggregate and all pending event rows — and is the documented way to make an event
  mandatory.
- **Hand-written flows:** inject the recorder into developer-owned `@Transactional` methods — no
  generated file edited.

### 7.4 Non-CRUD entry points — enumerated honestly (§0 #12)
| Path | v1 status |
|---|---|
| REST CRUD operations (create/update/delete incl. explicit-read variants) | **In scope** — bindings |
| File / XML ingest | **In scope, explicit work** — recorder inserted into the already-transactional ingest paths (`:10308,:10877`); a Slice-3 AC, not "inherited" |
| Spring Batch jobs | **In scope, explicit work** — recorder participates in chunk transactions (`:11953+`); per-job wiring in the slice |
| SOAP inbound | **Out of scope v1** — current handlers are **read-only and bypass the CRUD service** (`:8647-8745`); no mutation exists to bind |
| Scheduled/system flows | Developer-owned via the recorder; a declarative `system` binding source is deferred |

### 7.5 Correlation — new work, not an existing facility (§0 #12)
v1 generates a minimal correlation filter for event purposes only: read `X-Correlation-Id` if present,
else generate a **UUIDv4** (Java 17 has no built-in UUIDv7; monotonic ordering is `aggregate_seq`'s
job, not the id's), normalize (length/charset cap), hold request-scoped, stamp into envelopes.
Full propagation remains cross-service **Phase D** — not delivered here, and said so.

### 7.6 Schema evolution · PII · observability
As rev-1: `schema_version` per envelope, packaged diffable schemas, additive-only guidance (Q3/
registry stays open); payload = explicit allowlist by construction, masking deferred (E4);
Slice 4 adds outbox health (lag, parked aggregates, oldest-blocked age) + counters via an explicit
metrics registry dependency **added only with events** — full tracing stays in the tracing brief.

## 8. Failure-mode analysis (rev-1 coverage; poison/ordering, fencing, and allocator behaviors corrected since)
DB rollback ⇒ aggregate + event rows + seq allocation all roll back · broker outage ⇒ accumulate +
visible degradation, writes unaffected · crash windows per §4.4 (each named, each lands on
at-least-once) · **poison row ⇒ parks its own aggregate; other aggregates unaffected; health names the
blocked aggregate** (was: "never blocks the queue") · duplicate HTTP retry ⇒ two events, correct,
idempotency-key enforcement is Phase-4-gated · multi-instance ⇒ safe via fenced CAS claims (not via
`SKIP LOCKED` scanning); **stale owner after lease expiry ⇒ its late outcome updates zero rows** ·
**concurrent same-aggregate mutations ⇒ serialized on the allocator cursor; a wrong sequence can never
commit (unique constraint)** · schema drift ⇒ contract-level detection, cross-service Phase B.

## 9. Proof plan + acceptance criteria

**AC1 — absent-feature output stability. Scoped by *package history* first (§0 #21), then branched by
the §13.1 choice (§0 #18).** The §6.1 carry-forward means "no `event_publications`" describes **two
different packages**, and only one of them can claim byte-identity:
- **History A — never enabled** (greenfield, or a managed package with no committed event
  `internal_schema` entry): **AC1 applies.**
- **History B — previously enabled, now disabled:** AC1 **does not apply** and never could. Its
  invariant is different and is asserted separately as **AC1b**: no event runtime code, no publisher
  scheduling, no Kafka dependency, and no new migrations are emitted, while the previously committed
  outbox table, allocator, migrations, and `internal_schema` entry **intentionally remain**. Deleting
  them is the destructive path that stays blocked (§6.1).

Within History A, rev-2's "AC1 holds through Slices 1, 2b, 3, 4, 5" was still unsatisfiable under
option (a), because after 2a no output matches the *pre-feature* Engine. Two coherent branches:
- **Under §7.1(a):** exact pre-feature identity is required through **Slice 1 only**. Slice 2a is a
  single approved, global, golden-updating delta — **its own AC: the diff contains nothing but the
  transaction annotation** — and from 2b onward every slice is diffed against the **post-2a baseline**,
  where absent-feature output must again be byte-identical.
- **Under §7.1(b):** exact pre-feature AC1 holds through **every** slice, with no exemption.

**AC2** rollback ⇒ no event row, and **no sequence residue** (the allocator increment rolls back with
it). **AC3 — ordering, extended (§0 #14):** (i) concurrent mutations across ≥2 aggregates publish
per-aggregate in `aggregate_seq` order; (ii) **concurrent mutations of the *same* aggregate** produce
distinct, gap-free sequences under load; (iii) a **multi-event** mutation orders its own events
deterministically; (iv) **retention-then-next-event** — prune dispatched rows, emit again, assert the
new sequence still exceeds every pruned one; (v) a **cross-aggregate binding** (mutation that never
writes the target aggregate) serializes correctly on the cursor. **AC4** crash-window duplicates carry
identical `event_id`. **AC4b — fencing (§0 #15):** owner A's lease expires mid-send, B reclaims, A's
late success *and* late failure each update **zero** rows and cannot alter B's state. **AC5**
preserved-subclass compatibility: regenerate a package whose developer subclass predates events ⇒
compiles, tests green, untouched. **AC5b** the §7.2 hook-semantics triple, with **mutate-in-`afterUpdate`** asserted across the real
four-cell matrix (§0 #23): **event-enabled ⇒ persists under both (a) and (b)** — option (b) also adds
the outer transaction once events are declared; **event-absent ⇒ persists under (a), retains today's
non-persisting behavior under (b)**. **AC6** the §6.1 five-case migration set. **AC7**
replay disabled-by-default, role-gated, audited, idempotent. **AC8** H2/no-broker boot, capture,
operator visibility. Fixture = widget (domain-neutral); DDA packet = external replay validation;
scenarios register in M3's registry once built.

## 10. Roadmap (amended) + cross-design sequencing

Slices as rev-1 — **1 → 2a → 2b → 3 → 4; 5 parallel after 1; 6 unscheduled** — with: 2a contingent on
§13.1; 2b = capture-only (honest labeling); file/XML/batch recorder insertion ACs live in **3**;
replay/retention/health in **4**; matrix row-8 "after Slice 2" corrected to **2b**.

### 10.1 Order against the other approved-but-unbuilt designs (§0 #13)
OpenAPI **O0a/O0b** restructures the same emitter surface (shared endpoint/schema plan hoisted ahead
of both emit lanes); M4 **B2b** introduces the declared-artifact registry + agent-context facts; event
Slices 2a/2b alter ServiceBase and per-entity orchestration. No conceptual conflict, real rebase/proof
risk. **Recorded order:** complete **O0a → O0b before** event 2a/2b (the descriptor extraction touches
every line 2a/2b would edit); land **M4 B2b first or** require event artifacts/hooks to register
through B2b's sink when it lands; **M3** remains the scenario-registration vehicle after it exists.
This note belongs in the other two designs' sequencing sections as well — flagged for their next
touch, not silently edited here.

## 11. Broader gap review — as rev-1 (ranking unchanged)
Optimistic locking = next separate design gate (quality-gate High-TPS record exists) · idempotency-key
enforcement = existing Phase-4 gate reaffirmed · observability = extend the tracing brief · audit
consolidation later · resilience → `EC-rest-outbound-client` · auth → identity track/D2 · pagination/
error → OpenAPI-artifact work · migrations/secrets/retention/tests → covered or folded as before.

## 12. Deferred / rejected — as rev-1, plus
Per-binding parked-row **bypass relaxation** (v1 blocks the aggregate, §4.2) · UUIDv7 ids · SOAP
mutation events (no mutation path exists) · declarative `system` bindings · transport-neutral manifest
vocabulary (explicitly additive-evolution-later, §4.6) · **allocator-cursor cleanup** (cursors are
never pruned in v1; §4.2 makes any future cleanup/id-reuse conditional on a separately designed
aggregate-incarnation contract — a prerequisite, not by itself a sufficient condition) ·
per-binding ordering relaxation.

## 13. Maintainer decisions (both genuinely open)
1. **Transaction boundary — §7.1(a) unconditional vs §7.1(b) only-when-events.** Now presented with
   the full evidence: (a) changes hook semantics for every regenerated app (§7.2) and breaks
   post-commit assumptions in existing developer code; (b) preserves today's behavior everywhere
   events are absent but maintains two ServiceBase shapes. No recommendation is pre-decided; the
   §7.2 tests and AC5/AC5b apply to whichever is chosen, and **AC1 branches by it** (§9). *(rev-1's "unconditional, E5 compels it" is
   withdrawn — E5 requires explicitness, not universality.)*
2. **Build timing.** Sequenced by the canonical roadmap guardrail (M1 → M5a → … ) **and** §10.1's
   cross-design order (O0a/O0b before 2a/2b; M4 B2b registry interaction; M3 for scenario
   registration). Gating this design commits no build capacity.
3. Manifest field names final at Slice-1 review. 4. Q2 (consumers) deliberately open. 5. At-least-once
   is the only delivery contract v1 will ever state.

---

## Final decision

**Add the capability: transactional outbox + generated in-app polling publisher — the ADR selects this
mechanism from Phase A's permitted "outbox or equivalent" space** — opt-in via an additive
`event_publications` section (Q1 answered), at-least-once delivery with strict per-aggregate ordering
via a **durable sequence allocator** (unique-constraint fail-closed, retention-proof) plus
aggregate-granularity claims (parked rows block their own aggregate only), a **claim-token-fenced**
lease lifecycle with enumerated crash windows, a regeneration-safe recorder/hook seam that follows the
repo's own protocol, migrations integrated via a **carried-forward `internal_schema` baseline entry**
so disabling events removes code without ever proposing a table drop, and a disabled-by-default,
role-gated replay surface. CDC remains an optional gated adapter; event sourcing and XA stay rejected.
Zero cost and byte-identical output for apps that **never enabled** events (AC1); a package that
enabled and later disabled them keeps its committed outbox schema by design while emitting no event
runtime, dependency, or new migrations (AC1b). The one genuinely open exception, the §13.1
transaction-boundary decision, is put to the maintainer with its full
compatibility evidence rather than a recommendation that outran it.
