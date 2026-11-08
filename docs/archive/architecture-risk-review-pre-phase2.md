> Archived April 2026. Superseded by docs/archive/target-state-features-v1.md.

# EdgeForge — Architecture Risk Review Before Phase 2
*Reviewer: Claude · Date: 2026-03-26 · Status: Baseline completed on 2026-03-27; Engine setup PRs `#45–#46` merged on `main`*

> **How to use this document:**
> This review is now committed as the explicit pre-Phase-2 gate checklist.
> Phase 1b is complete; use this document to lock the remaining setup decisions before
> multi-archetype (passthrough-router) expansion begins.
> The setup gate has now landed on `main`; use this document as the locked record of those boundary decisions while Phase 2 work proceeds.

---

## Context

- **Platform:** EdgeForge — contract-preserving modernization platform for enterprise
- **Current state:** Phase 1b complete on `main`; rename baseline merged; Phase 2 setup PRs `#45–#46` merged
- **Next major step:** Phase 2 follow-through — stronger package validation, first real CRUD proof via Studio, and then the passthrough-router Engine MVP
- **Scope of this review:** Platform architecture, pre-multi-archetype expansion. Not a code review.

---

## 1. Canonical Model Neutrality

### Current State

The canonical model (`MetadataProject`, `CanonicalEntity`, `CanonicalField`, `CanonicalOperation`) is
**implicitly CRUD-shaped but not fatally so**.

| Structure | CRUD Assumption | Severity |
|-----------|----------------|----------|
| `CanonicalEntity` with `is_id`, `server_generated_id` | Assumes a persistable entity with a primary key | 🟡 Medium |
| `CanonicalOperation` binds `request_entity` ↔ `response_entity` | Assumes operations map to entity CRUD, not transformation flows | 🟡 Medium |
| `MetadataProject.staging_table_ddls` | Persistence-specific, irrelevant to passthrough | 🟢 Low (nullable, ignorable) |
| `MetadataProject.entities` as the primary generation unit | Engine loops over entities — passthrough has no entities in the traditional sense | 🔴 High |
| `CanonicalFieldType` enum (STRING, INTEGER, DECIMAL, etc.) | Type-neutral — equally valid for DTOs, transforms, and entities | 🟢 Low |
| `ContractMetadata.type` (upstream/downstream/staging-table/file) | Already multi-contract-type aware | 🟢 Low |
| `TargetProfile` with `emit_flyway`, `emit_spring_batch` flags | Profile-gated features — can be set to False for passthrough | 🟢 Low |

**Verdict:** ~60% neutral, ~40% CRUD-coupled. The coupling is concentrated in:

1. **`CanonicalEntity` as the primary generation unit** — Engine iterates `metadata.entities` and
   generates one entity/repo/service/controller per entity. A passthrough app has no "entities" —
   it has inbound shapes, outbound shapes, and transformation mappings.

2. **`CanonicalOperation` bound to entity CRUD** — `request_entity` and `response_entity` assume
   the operation reads/writes a persistence entity. A passthrough operation transforms one shape
   into another and routes it.

### Recommendations

**R1. Do NOT refactor `CanonicalEntity` or `CanonicalOperation` to be archetype-neutral.**
Instead, add parallel structures for passthrough:

```
MetadataProject
├── entities          ← CRUD archetype (existing, unchanged)
├── operations        ← CRUD archetype (existing, unchanged)
└── flows             ← Passthrough archetype (NEW in Phase 2A)
    ├── inbound_shape   (like CanonicalEntity but explicitly transient)
    ├── outbound_shapes (one per downstream target)
    ├── transform_rules
    └── routing_rules
```

**R2. Add `app_archetype` to `MetadataProject` now, before Phase 2 begins.**
Even before passthrough is implemented, having the field present with a default of `"crud"` makes
the archetype boundary explicit from day one. This is a one-line model change with zero risk.

---

## 2. Archetype Boundary Definition

### Recommended Boundary

```
SHARED CORE (archetype-agnostic)
├── Manifest parsing (YAML → ProjectDefinition)
├── Contract ingestion (OpenAPI, samples, mapping files)
├── CanonicalFieldType (type system)
├── ContractMetadata (source tracking)
├── SystemParticipant (upstream/downstream)
├── TargetProfile (build/runtime profile)
├── Compatibility harness framework
├── Build file emission (pom.xml, Dockerfile, application.yml)
├── Package naming / path utilities
├── Validation rules (NOT_NULL, RANGE, PATTERN, FIELD_COMPARISON, etc.)
└── Generation orchestration skeleton (engine.py dispatch)

CRUD LANE (entity-centric, existing)
├── CanonicalEntity / CanonicalField
├── CanonicalOperation (entity-bound CRUD ops)
├── CanonicalRule (cross-entity, validation)
├── Field accumulator / translation pipeline
├── JPA entity renderer
├── JpaRepository renderer
├── CRUD controller renderer
├── CRUD service renderer (with business rules)
├── Flyway migration emitter
├── Staging table / file writer renderers
├── Spring Batch job renderer
├── Demo UI for CRUD apps
└── Golden contract tests for CRUD

PASSTHROUGH-ROUTER LANE (flow-centric, Phase 2)
├── CanonicalFlow / FlowStep (NEW)
├── TransformRule / RoutingRule (NEW — do NOT share with CanonicalRule)
├── Inbound controller renderer (NEW)
├── Transform service renderer (NEW)
├── Routing service renderer (NEW)
├── Downstream REST client renderer (NEW)
└── Golden contract tests for passthrough
```

### Common Cross-Contamination Mistakes to Avoid

| Mistake | How It Happens | Prevention |
|---------|---------------|------------|
| Shared utility assumes entity existence | Helper like `entity_id_field()` called from shared code | Gate entity-dependent helpers behind archetype check |
| Engine hardcodes emitter sequence | `engine.py` calls `emit_java_sources()` which renders entities/repos/services | Engine should dispatch to `CrudEmitter.emit()` or `PassthroughEmitter.emit()` based on archetype |
| TargetProfile gains archetype-specific flags | Adding `emit_routing` to TargetProfile pollutes CRUD concerns | TargetProfile for cross-cutting only; archetype-specific config belongs in archetype lane |
| Translation pipeline forces entity accumulation | `translate_project()` always builds entities via `_FieldAccumulator` | Passthrough needs its own translation path building flows, not entities |

### The Critical Design Decision

**`engine.py` is the fork point.** It needs to become:

```python
def generate_application(metadata, ...):
    archetype = metadata.app_archetype or "crud"
    if archetype == "crud":
        return _generate_crud_application(metadata, ...)
    elif archetype == "passthrough-router":
        return _generate_passthrough_application(metadata, ...)
    else:
        raise ValueError(f"Unknown archetype: {archetype}")
```

Move the current `generate_application()` body into `_generate_crud_application()` as part of
Phase 2A setup — before passthrough generation is implemented.

---

## 3. CRUD vs Passthrough Separation Strategy

### Verdict: Separate archetypes is the correct direction ✅

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **A. Separate archetypes** (current plan) | Clean boundaries, independent evolution, no CRUD regression risk, easier to test | Some code duplication in shared utilities | **✅ Recommended** |
| **B. Unified model with optional behaviors** | Single code path | Entity-assumption leaks everywhere; every emitter needs `if archetype ==` guards; high CRUD regression risk | ❌ Rejected |
| **C. Hybrid (shared primitives + archetype emitters)** | Less duplication | "Shared primitives" tends to grow until it becomes Option B in disguise | ⚠️ Only if discipline maintained |

**Why A is correct:**

1. **Generation topology is fundamentally different.** CRUD: Entity→Repo→Service→Controller→Migration.
   Passthrough: Controller→TransformService→RoutingService→RestClient. These are different
   application architectures, not variations of one.

2. **Risk profile is asymmetric.** CRUD is the revenue-critical path (enterprise apps). Passthrough
   is new and experimental. Mixing them means passthrough development risks breaking CRUD.

3. **Manifest sections are mostly disjoint.** CRUD needs entities, fields, operations, rules,
   staging tables. Passthrough needs inbound contract, outbound targets, transform mappings,
   routing predicates. The overlap is small.

**Risk to manage:** Gratuitous divergence between archetypes — improvements to one never flowing to
the other. Mitigation: shared core (build files, health checks, type catalog, target profile,
harness framework) must be actively maintained as shared during code review.

---

## 4. Studio ↔ Engine Contract Risk

### Current State

Studio exports manifest YAML. Engine consumes via `build_metadata_project(manifest_path)`.
There is **no formal schema contract** — the contract is implicit in the Python YAML parser.

### Risk Level: 🟡 Medium (manageable now, dangerous at scale)

| Risk | Likelihood | Impact |
|------|------------|--------|
| Studio emits a field Engine doesn't expect | Medium | Silent data loss (Pydantic drops unknown fields) |
| Engine requires a field Studio doesn't emit | High | Engine crash with unhelpful error |
| Enum value mismatch (e.g., `staging-table` vs `staging_table`) | Medium | Silent misparse or crash |
| New archetype adds manifest sections Studio doesn't know about yet | High (Phase 2) | Engine rejects package, user confused |

### Recommended Safeguards

**S1. JSON Schema for the manifest package (Phase 2A prerequisite).**

```
appbuilder/
└── schema/
    ├── manifest-v1.schema.json    ← CRUD archetype
    ├── manifest-v2.schema.json    ← adds passthrough-router fields
    └── validate.py                ← shared validator used by both Studio and Engine
```

**S2. Golden input packages as contract artifacts.**
Add golden manifest YAML files as test fixtures. If Engine changes its parser, the golden input
test breaks. If Studio changes its export format, the golden input test breaks.

**S3. `schema_version` field in every manifest.**

```yaml
schema_version: "1.0"
app_archetype: crud
app_name: LoanLite
```

Engine rejects unknown versions with a clear error. Prevents silent drift.

**S4. `validate_package()` function in Engine (Phase 2+).**
A validation-only entry point Studio can call without triggering generation. Returns
errors/warnings. Cheaper than "generate and see if it crashes."

---

## 5. Phase Sequencing Review

### Current Sequence

```
Docs baseline  →  Fresh workspaces  →  Architecture gate  →  Phase 2 setup  →  Phase 2-CRUD / Phase 2-PT  →  Phase 3 (Engine MCP)  →  Phase 4 (Knowledge Server)  →  Phase 5 (LegacyExtractor)
```

### Transition Risk Assessment

| Transition | Risk | Notes |
|------------|------|-------|
| 1b → 2 (real apps + passthrough) | 🟡 Low-Medium | Safe if archetypes are separate. CRUD golden tests must pass on every passthrough PR. |
| 2 → 3 (Engine MCP) | 🟡 Medium | MCP must be an adapter, not a host. Engine remains callable as a library. |
| 3 → 4 (Knowledge Server) | 🟢 Low | Knowledge Server produces manifest content; doesn't depend on Engine internals. |
| 4 → 5 (LegacyExtractor) | 🟢 Low | Same pattern — produces manifest content, consumes manifest schema. |

### Recommended Change: Split Phase 2 Into Parallel Tracks

```
Phase 1b  ──→  Phase 2-CRUD (real enterprise apps via Studio)
                     ∥ (parallel, not sequential)
               Phase 2-PT   (passthrough-router archetype)
                     ↓
               Phase 3 (Engine MCP — wraps both archetypes)
```

Do not gate passthrough on completing all real enterprise apps. Do not gate real enterprise apps on
passthrough. MCP wrapping (Phase 3) should happen after both archetypes are stable.

**One hard dependency:** If Knowledge Server (Phase 4) will ever produce passthrough-router
manifests, the passthrough manifest schema must be stable before Phase 4 starts. Naturally
satisfied if Phase 2-PT completes before Phase 4.

---

## 6. Rule Engine Evolution Risk

### Current Rule Types
`ALLOWED_VALUES`, `DEFAULT`, `FORMAT`, `MAX_LENGTH`, `MIN_LENGTH`, `PATTERN`, `RANGE`,
`NOT_NULL`, `CROSS_ENTITY_EXISTS`, `FIELD_COMPARISON`

### Archetype Scoping of Rule Types

| Rule Category | CRUD | Passthrough | Shared? |
|--------------|------|-------------|---------|
| Validation (NOT_NULL, RANGE, PATTERN, etc.) | ✅ | ✅ (on inbound shape) | Yes |
| Cross-entity (CROSS_ENTITY_EXISTS) | ✅ | ❌ (no entities) | No — CRUD only |
| Field comparison | ✅ | Maybe (on inbound shape) | Partially |
| Transform rules (rename, default, type-convert) | ❌ | ✅ | No — Passthrough only |
| Routing rules (predicate → target) | ❌ | ✅ | No — Passthrough only |
| Enrichment rules (external lookup) | ❌ | ✅ (Phase 2+) | No — Passthrough only |

### Design Constraints

**C1. Rules must be archetype-scoped, not universal.**

```python
# BAD: One god-object CanonicalRule for everything
class CanonicalRule(BaseModel):
    type: RuleType  # 15+ types, most fields irrelevant to most
    transform_function: Optional[str]  # passthrough only
    routing_target: Optional[str]      # passthrough only

# GOOD: Archetype-specific rule models
class ValidationRule(BaseModel): ...     # Shared (NOT_NULL, RANGE, PATTERN)
class FieldComparisonRule(BaseModel): ...# Shared
class CrossEntityRule(BaseModel): ...    # CRUD-only
class TransformRule(BaseModel): ...      # Passthrough-only
class RoutingRule(BaseModel): ...        # Passthrough-only
```

**C2. Routing rules must be archetype-specific — never added to `CanonicalRule`.**
Routing is a passthrough-only concept. It belongs in a `PassthroughFlow` or `RoutingConfig`.

**C3. Transform rules are NOT validation rules.**
Transform rules mutate data. Validation rules reject data. They must never share a model or
a code path, even if both are YAML-defined.

**C4. Cap rule types per archetype at 10–12.**
If any archetype exceeds 12 rule types, that is a signal that rules are being used for things
that should be configuration (e.g., "retry 3 times" is config, not a rule).

---

## 7. MCP Migration Risk (Secondary)

### Protective Pattern

```python
# appbuilder/mcp/server.py (Phase 3 — NEW)
class EdgeForgeMCPServer:
    def handle_generate(self, mcp_input: dict) -> dict:
        metadata = MetadataProject(**mcp_input["metadata"])  # adapter
        report = generate_application(metadata, ...)          # Engine unchanged
        return {"status": "ok", "files": report.files_created}

# Engine never imports from mcp/. MCP imports from Engine. One-way dependency.
```

| Risk | Mitigation |
|------|------------|
| Engine depending on MCP message format | Engine `generate_application()` signature never changes for MCP |
| Session state leaking into Engine | Engine must remain stateless per invocation |
| MCP error handling replacing Engine error handling | Engine throws Python exceptions; MCP adapter catches and formats |

---

## 8. Real-World Spec Handling (Secondary)

### Recommended Spec Complexity Gate

Add a validation step in `translation.py` before entity accumulation:

```python
def _validate_spec_complexity(spec: dict) -> list[str]:
    """Returns rejection reasons. Empty = supported."""
    rejections = []
    if _has_polymorphism(spec):       # oneOf / anyOf
        rejections.append("oneOf/anyOf polymorphism not yet supported")
    if _max_nesting_depth(spec) > 3:
        rejections.append(f"Nesting depth {depth} exceeds maximum of 3")
    if _has_circular_refs(spec):
        rejections.append("Circular $ref detected")
    return rejections
```

**Fail loudly before generation, not silently during emission.**

| Construct | Recommended Handling |
|-----------|---------------------|
| `oneOf` / `anyOf` polymorphism | Reject with clear error naming field and construct |
| Deeply nested objects (3+ levels) | Flatten with dot-path naming; warn if depth > 3 |
| `$ref` cycles | Detect during spec parsing; reject with cycle path |
| `additionalProperties: true` | Emit `Map<String, Object>` with generation warning |
| Array-of-arrays | Reject |
| `allOf` composition | Support simple flat merge; reject on conflict |

---

## Design Boundary Recommendations

| Component | Shared | CRUD-Only | Passthrough-Only |
|-----------|:------:|:---------:|:----------------:|
| Manifest YAML parsing | ✅ | | |
| `CanonicalFieldType` | ✅ | | |
| `ContractMetadata` | ✅ | | |
| `SystemParticipant` | ✅ | | |
| `TargetProfile` | ✅ | | |
| Build file emission | ✅ | | |
| Health/actuator config | ✅ | | |
| Validation rules (NOT_NULL, RANGE, etc.) | ✅ | | |
| `CanonicalEntity` / `CanonicalField` | | ✅ | |
| `CanonicalOperation` (entity-bound) | | ✅ | |
| JPA entity / repository / Flyway | | ✅ | |
| CRUD service / controller | | ✅ | |
| Staging table / file writers | | ✅ | |
| Spring Batch | | ✅ | |
| Cross-entity rules | | ✅ | |
| `CanonicalFlow` / `FlowStep` | | | ✅ |
| Transform rules | | | ✅ |
| Routing rules / config | | | ✅ |
| Downstream REST client | | | ✅ |
| Transform service | | | ✅ |
| Routing service | | | ✅ |

---

## Archetype Strategy Recommendation

**Separate archetypes. ✅** The two archetypes share a manifest format, type system, contract
metadata, and target profile — but diverge completely at the generation topology level. Attempting
to unify them into one generation path would create a tangle of `if archetype ==` branches in
every emitter method, with high regression risk on the proven CRUD path.

**Discipline required:** Actively maintain the shared core as shared. Resist duplicating shared
utilities into archetype lanes. Code review should flag any duplication that belongs in shared core.

---

## Final Risk Summary

### Top 3 Architectural Risks

| # | Risk | Severity | Mitigation |
|---|------|:--------:|------------|
| 1 | **Canonical model CRUD drift** — `CanonicalEntity` becomes the de facto generation unit for all archetypes, forcing passthrough to fake "entities" for transforms | 🔴 High | Add parallel `CanonicalFlow` structures for passthrough. Never force passthrough data through entity/field models. |
| 2 | **Studio ↔ Engine contract drift** — no formal schema; silent failures on mismatch | 🟡 Medium | Add `manifest-schema.json` + `schema_version` field before Phase 2-PT. Validate on both sides. |
| 3 | **Rule model god-object** — `CanonicalRule` absorbs transform, routing, and enrichment rules alongside validation rules | 🟡 Medium | Scope rule models per archetype. Validation rules shared; transform/routing rules passthrough-only. Cap at 10–12 types per archetype. |

### Top 3 Protective Design Rules

| # | Rule | Why |
|---|------|-----|
| 1 | **Engine must remain a stateless library callable without MCP.** MCP is an adapter only. | Prevents MCP migration from becoming an irreversible architecture change. Keeps testing simple. |
| 2 | **CRUD golden tests must pass on every passthrough PR, and vice versa.** Cross-archetype CI gate. | Prevents shared-core changes from silently breaking the other archetype. |
| 3 | **Fail loudly on unsupported constructs before generation, not during.** Spec complexity gate in translation, not silent skips in emitters. | Prevents users from getting a "generated" app that compiles but has silently missing features. |

---

## Baseline Checklist (Complete Before Phase 2 Start)

Before treating this document as the Phase 2 baseline, confirm all of the following:

- [x] Phase 1b entity relationships PR merged and smoke-validated
- [x] Phase 1b query/header parameter support PR merged
- [x] All 295 unit tests green on main
- [x] EdgeForge branding PR merged and GitHub repo rename completed
- [x] Fresh workspaces opened on the renamed repos
- [x] Stale smoke PR `#40` explicitly not treated as source of truth; use merged fix PRs or a fresh smoke artifact instead
- [x] `app_archetype: crud` field added to `MetadataProject` (default `"crud"`)
- [x] `schema_version` field added to manifest packages
- [x] `engine.py` refactored to `_generate_crud_application()` dispatch pattern
- [x] `manifest-schema.json` v1 drafted for CRUD archetype
- [x] This document reviewed and countersigned by Codex

---

*Document saved: 2026-03-26 · Baseline candidate committed: 2026-03-27 · Baseline completed: 2026-03-27 · Next review: before the first passthrough-router Engine implementation PR*
