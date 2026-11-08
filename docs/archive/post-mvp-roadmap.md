# EdgeForge Post-MVP Roadmap and Design Decisions

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

> **Historical document.** Captures the design decisions made during the post-MVP phase (PRs #11–#15). For current execution priorities, see `docs/enterprise-readiness-roadmap.md` and `docs/tracker/README.md`. For current architecture, see `docs/extension-architecture.md`.

## Status: MVP Complete

All original MVP phases have been delivered and merged (PRs #1–#10):

| Phase | PR(s) | Status |
|-------|-------|--------|
| Foundation | #1 | ✅ |
| Manifest & Input Package | #2 | ✅ |
| Contract Ingestion & Metadata | #3 | ✅ |
| Mapping & Rules Engine | #4 | ✅ |
| Spring Boot Skeleton Generator | #5 | ✅ |
| Compatibility Harness | #6, #8 | ✅ |
| Developer Experience (CLI) | #7 | ✅ |
| CI Bootstrap | #10 | ✅ |
| Generality Proof (BuiltApp2 — Loans) | #9 | ✅ |

EdgeForge has been proven on two independent enterprise domains:

- **BuiltApp1** — XYZ Accounts Modernization (accounts bounded context)
- **BuiltApp2** — Loans Modernization (loans bounded context)

Both pass the full compatibility harness (38 tests, 2 integration happy-path tests).

---

## Design Decisions Finalized Post-MVP

The following decisions were reached through Claude–Santosh discussion and are now considered settled for all future implementation work.

### Decision 1: EdgeForge works with or without legacy source code

EdgeForge is **contract-first by design**. It does NOT require access to legacy application source code.

**Black box scenario (primary):**
- Observe the legacy system's external contracts (APIs, files, staging tables)
- Create an input package from those observations
- EdgeForge generates a replacement that preserves all external contracts
- Business logic is added incrementally via PRs after generation

**Source code available scenario (future enhancement):**
- A separate companion tool ("LegacyExtractor") would parse legacy source code
- LegacyExtractor outputs a DRAFT EdgeForge input package (manifest, rules, mappings)
- A human reviews and refines the draft
- The refined package feeds into EdgeForge as normal
- EdgeForge's contract-first pipeline and harness verification remain unchanged

**Key rule:** Legacy source code extraction is NEVER a replacement for contract-first generation. It is an additional input source that feeds INTO the manifest-driven pipeline. EdgeForge itself does not parse legacy code.

**Status:** LegacyExtractor is documented as a future companion tool. Not in current MVP or post-MVP scope. If built, it should be a separate repository.

### Decision 2: Inter-app integration is infrastructure, not an EdgeForge feature

EdgeForge generates each application independently with correct contracts at the edges. Connecting applications to each other (REST calls, Kafka topics, message queues) is standard infrastructure work performed on the generated apps.

**Example enterprise ecosystem:**
- FX Deal Booking → sends postings to DDA Core → sends entries to Finance Reporting
- CRM → sends CRUD to DDA Core → publishes changes to downstream apps

If each generated app correctly preserves its upstream/downstream API contracts, they integrate naturally through standard Kafka/REST/MQ wiring. EdgeForge does NOT need to:
- Generate inter-service REST clients
- Generate Kafka producers/consumers as part of the core pipeline
- Manage an ecosystem-level manifest or topology
- Perform cross-app contract governance

**Status:** Ecosystem-level features (cross-app contract checker, ecosystem manifest) are explicitly OUT of MVP and post-MVP scope. They are interesting future ideas but not required. Standard DevOps/infrastructure connects the generated apps.

### Decision 3: SSO integration and audit tracking are generated cross-cutting features

Every generated enterprise application should integrate with the enterprise's existing SSO (Single Sign-On) infrastructure and include audit tracking.

**SSO integration (security layer):**
- EdgeForge generates Spring Security OAuth2 resource server configuration
- The enterprise's existing SSO provider issues tokens
- Every generated app validates tokens and extracts user_id from JWT claims
- SSO provider URL is a configurable placeholder in `application.yaml`
- EdgeForge does NOT build the SSO server — it generates the client-side integration

**Audit tracking:**
- Every generated entity gets four audit columns: `created_by`, `created_at`, `modified_by`, `modified_at`
- JPA Auditing (`@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate`) auto-populates from the security context
- Flyway migrations include audit columns
- An optional `audit_log` table captures entity, action, user_id, timestamp, and changes

**Profile flags:**
- `emit_audit=True` — adds audit columns + JPA auditing configuration
- `emit_security=True` — adds Spring Security OAuth2 resource server configuration

**Status:** ✅ Delivered. Security layer in PR #12 (merged). Audit tracking in PR #13 (merged).

### Decision 4: Demo UI is a generated feature for stakeholder presentation

Each generated app should include a simple demo page served from `src/main/resources/static/index.html` that allows non-technical stakeholders to interact with the API without needing Postman or curl.

**The demo UI should be generated by EdgeForge (not handcrafted) so it stays in sync with the canonical model.** It should show:
- App name, bounded context, and preserved contracts
- A form with fields from the upstream API operation
- Allowed values rendered as dropdowns (from rules)
- Optional fields clearly labelled
- Submit button calling the actual API
- Response display
- Business rule validation error display

**Implementation:** Static HTML + vanilla JavaScript. No React/Vue/Angular. Spring Boot serves static files automatically from `src/main/resources/static/`.

**Status:** ✅ Delivered in PR #11 (merged). Both BuiltApp1 and BuiltApp2 regenerated with demo UI.

### Decision 5: Docker Compose for local multi-app testing

A `docker-compose.yml` at the repo root should wire up all generated BuiltApps for local integration testing on a developer's laptop.

- Each app runs on a different port (8081, 8082, 8083, etc.)
- Shared Docker network for inter-container communication
- Each app uses its own H2 in-memory database
- Health checks via `/actuator/health`

**Status:** To be implemented as a post-MVP PR. This is an infrastructure convenience, not an EdgeForge core feature.

### Decision 6: Third sample domain proves scalability

A third input project should be created to further validate EdgeForge's generality.

**Original candidates (single-entity):** FX/FT Deal Booking, Payment Initiation, Customer Onboarding.

**Updated direction (2026-03-14):** After reviewing the external application swagger spec and the Claude + Codex merged design review, the third app was redefined as **CRMApp** — a **multi-entity** proof-of-concept with Customer + Account entities derived from the external application upstream API. CRMApp lives in `CRMApp/` rather than `BuiltApp3/` to reflect its role as the first named application generated from a real swagger source with multiple entities. This requires engine changes (PRs #14 and #15) before generation, unlike the original plan which assumed no engine changes.

See `docs/archive/openapi-intake-and-multi-entity-design-note.md` for full design rationale.

**Status:** Planned as PR #17. Depends on PR #14 (OpenAPI ingestion) + PR #15 (multi-entity support).

---

## Post-MVP PR Sequence

### Delivered (PRs #11–#13)

| PR | Branch | Status | What |
|----|--------|--------|------|
| **#11** | `codex/feature/demo-ui-generator` | ✅ Merged | Demo UI generation (`ui_emitter.py`, `index.html` per app) |
| **#12** | `codex/feature/sso-security-layer` | ✅ Merged | SSO Security Layer (`emit_security` flag, `SecurityConfig.java`, OAuth2 resource server) |
| **#13** | `codex/feature/audit-tracking` | ✅ Merged | Audit Tracking (`emit_audit` flag, `AuditConfig.java`, audit columns on entities + Flyway) |

### Next: Core Generator Enhancements (PRs #14–#16)

Based on merged Claude + Codex design review. See `docs/archive/openapi-intake-and-multi-entity-design-note.md` for full design rationale.

#### PR #14 — OpenAPI / Swagger Ingestion

**Branch:** `*/feature/openapi-ingestion` (claude or codex)

Connect the `spec_url` wire in `translation.py`:
- Fetch OpenAPI 3.x JSON/YAML from `spec_url` via `httpx` or `urllib`
- Parse `components/schemas` → derive `CanonicalEntity` fields using existing `_openapi_type_to_canonical_type()`
- Parse `paths` → derive `CanonicalOperation` entries (POST=create, GET=read, PUT=update, DELETE=delete)
- Filter out infrastructure schemas (pagination wrappers, sort objects, error objects)
- Remove the stub warning ("spec_url is declared but sample-based ingestion is used...")
- Preserve backward compatibility: sample-based ingestion continues to work when `spec` is used instead of `spec_url`

**Parallelizable with PR #15.**

#### PR #15 — Multi-Entity Bounded Context Support

**Branch:** `*/feature/multi-entity` (claude or codex)

Make translation produce N entities and all emitters loop over them:
- `translation.py` — build separate `CanonicalEntity` per upstream interface (not one merged entity)
- `utils.py` — add `all_entities()` iterator; keep `primary_entity()` for batch job only
- `java_emitter.py` — loop: N Entities + N Controllers + N Services + N Repositories + N DTO sets
- `sql_emitter.py` — loop: N Flyway migrations (`V1__create_X.sql`, `V2__create_Y.sql`, ...)
- `ui_emitter.py` — demo UI with tabs per entity
- `CanonicalEntity` model — add optional FK reference support (simple `@Column` FK, not `@ManyToOne` for v1)
- No changes needed in: `build_emitter.py`, `audit_emitter.py`, `security_emitter.py`

**Parallelizable with PR #14.**

#### PR #16 — Assessment Mode (`appbuilder assess`)

**Branch:** `*/feature/assess-command` (claude or codex)

Add `appbuilder assess --swagger <url>` CLI command:
- Fetches and parses the OpenAPI spec
- Inventories all operations and schemas
- Classifies schemas as: domain entity candidate, DTO, infrastructure/skip
- Reports what EdgeForge can fully generate vs what needs manual work
- Flags missing downstream/rules inputs
- Does NOT create any files

**Depends on PR #14.**

### Then: Proof-of-Concept (PRs #17–#18)

#### PR #17 — CRMApp (Multi-Entity Proof)

**Branch:** `generated/crm-app`

Create CRMApp input package with Customer + Account entities (from external application swagger or manual YAML). Generate CRMApp using multi-entity support. Add `test_happy_path_crm_app` to integration tests. All happy-path tests must pass.

**Depends on PR #14 + PR #15.**

#### PR #18 — Docker Compose for Local Integration

**Branch:** `*/feature/docker-compose`

Add `docker-compose.yml` at the repo root that runs BuiltApp1, BuiltApp2, and CRMApp on ports 8081, 8082, 8083 with a shared Docker network. Health checks via `/actuator/health`.

**Depends on PR #17.**

### Future: Intake Tooling (Separate Conversation)

#### PR #19 — CLI Intake Command (`appbuilder init`)

**Branch:** `*/feature/init-command`

`appbuilder init --swagger <url> --output <dir>` — fetches spec, guides entity selection, generates draft input package + completeness report.

**Depends on PR #14 + PR #15. To be started in a separate conversation.**

#### Future — EdgeForge Studio (UI)

Lightweight web UI over `appbuilder init`. Separate repo. Deferred until CLI intake is proven.

---

## What EdgeForge Is NOT Building

To keep scope clear, the following are explicitly out of scope:

- **SSO server** — the enterprise provides this; EdgeForge generates client-side integration only
- **Kafka infrastructure** — standard DevOps; connect generated apps externally
- **Inter-service REST clients** — generated apps are standalone; calling between them is standard development
- **Ecosystem manifest / cross-app contract governance** — not needed if each app preserves its own contracts
- **LegacyExtractor / source code parser** — future companion tool in a separate repo
- **Production database support** — generated apps use H2 for dev; switching to PostgreSQL/Oracle is a profile change done outside EdgeForge
- **Full business logic recreation** — EdgeForge generates the structure; business logic is added incrementally via PRs on the generated app
- **Selective regeneration** — re-generating only contract edges (DTOs/controllers) without overwriting service layer; deferred until CRMApp demo proves multi-entity
- **JPA `@ManyToOne` relationships** — v1 uses simple `@Column` FK fields; full JPA relationship mapping deferred
- **EdgeForge Studio UI** — deferred to separate conversation/repo after CLI intake is proven

---

## Enterprise Scalability Confirmation

EdgeForge is confirmed scalable to large enterprise ecosystems (hundreds of applications) because:

1. **Each app is independently generated** — no coupling between generated apps
2. **Contract-first approach** — each app knows its external contracts; integration is just infrastructure
3. **Spring Boot 3 + Java 21** — handles 5000+ TPS per pod with virtual threads
4. **Profile-driven** — same engine generates for different runtime targets
5. **Standardized tech stack** — all generated apps share the same architecture pattern, making support and upgrades uniform
6. **Incremental modernization** — replace one legacy app at a time, run in shadow mode alongside legacy, cut over when ready

The enterprise modernization pattern is:
1. Create EdgeForge input package from legacy system observation
2. Run EdgeForge → generate replacement app
3. Deploy alongside legacy in shadow mode
4. Compare outputs, add missing business logic as PRs
5. Cut over when outputs match within acceptable tolerance
6. Repeat for next legacy system
