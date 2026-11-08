# Studio UX v3 — Multi-Type Suggestion Drawer Pattern

**Status:** Implemented / validated through Studio UX v3 KA drawer and review work; final polish through Studio PR #143
**Version:** 1.0
**Date:** April 2026
**Author:** Codex Studio
**Related designs:**
- [Studio UX v3 Assistive Features](./studio-ux-v3-assistive-features-design.md)
- [Knowledge Server Broader Suggestion Scopes](./ks-broader-suggestion-scopes-design.md)
- [Studio KS Orchestration Design](./studio-ks-orchestration-design.md)
- [Project Workspace / Decision Ledger Design](./project-workspace-decision-ledger-design.md)
- [Evidence Trail Design](./evidence-trail-design.md)
- [CRUD Cross-Entity Business Logic Rules](./crud-cross-entity-rules-design.md)

---

> **Implementation note — May 2026:** This remains the design reference for
> compact Knowledge Assist badges, drawers, advisory reviews, and full review
> surfaces. The pattern is implemented in Studio through the UX v3 / broader KA
> arc, with visual taxonomy polish through PR #143.

## 1. Purpose

This document resolves Studio UX v3 open question OQ6: **how should Studio render
compact badges and drawers when a step has multiple Knowledge Assist suggestion
scopes?**

It is the UX contract for future KS-B2 / KS-B3 Studio implementation PRs. It
does not implement any new Knowledge Server tools, Studio routes, or Engine
contracts.

The design keeps the v3 product promise:

- Knowledge Assist is **OFF by default**.
- When OFF, Knowledge Assist is invisible in wizard steps.
- When ON, suggestions remain compact until the user asks to inspect them.
- Every suggestion is human-reviewed before it can enter the manifest.
- Evidence is available on demand, not pre-expanded into the wizard.

---

## 2. Core Principle

Knowledge Assist is an assistive layer, not a parallel workflow.

The wizard remains the primary authoring surface. Suggestion UI must appear only
when there is something actionable and only in the local step context where the
suggestion can be reviewed.

### 2.1 Non-Negotiable Rules

- **No always-visible KS panels.** A wizard step must not reserve space for
  Knowledge Assist when there are no suggestions.
- **No degraded banners in wizard steps.** If Knowledge Assist cannot fetch
  suggestions, badge methods return no badge. Manual authoring continues.
- **No empty suggestion panels.** Zero suggestions means zero badge and zero
  drawer entry point.
- **No transport language.** User-facing text must not expose `KS`, `MCP`,
  tool names, subprocess state, or adapter internals.
- **No auto-accept.** Suggestions stay pending until the user accepts, edits, or
  rejects them.
- **No fake evidence.** Human-authored items can be shown in review surfaces,
  but they are not labeled as evidence-backed Knowledge Assist suggestions.

---

## 3. Badge Pattern

Badges are the only wizard-step entry point for suggestion review.

### 3.1 Rendering Rules

A badge appears only when all of these are true:

1. `ProjectCapabilities.knowledge_assist_enabled == true`
2. the current route/step supports the suggestion scope
3. the relevant scope returns `count > 0`
4. the `AssistService` badge method did not fail

If any condition is false, the route view model returns `None` for that badge
and the template renders nothing.

### 3.2 Badge Labels

Badge labels must be short, user-facing, and scope-specific:

| Scope | Badge label |
|---|---|
| Field suggestions | `N field suggestions` |
| Validation hints | `N validation hints` |
| Rule suggestions | `N rule suggestions` |
| Conflict hints | `N conflicts` |
| Mapping suggestions | `N mapping suggestions` |
| Transform suggestions | `N transform suggestions` |
| Review evidence | `Evidence used` |

Counted badges use the concrete count. Singular/plural grammar should be
handled by the template or view model.

### 3.3 Badge Semantics

- A badge is a **button**, not a status label.
- Clicking a badge opens a drawer with that scope selected.
- The badge itself is never an accept/reject/edit control.
- A step can show multiple badges side-by-side.
- Badge placement should be near the relevant step header, entity header, route
  section header, or rules section header.

### 3.4 Badge Examples

```text
Step 3 · Entity Model                                      [3 field suggestions] [2 validation hints]
```

```text
Step 6 · Rules & Legacy Notes                              [4 rule suggestions] [2 conflicts]
```

```text
Kafka Transform Mappings · target d1_us_core               [5 transform suggestions]
```

---

## 4. Drawer Pattern

Studio uses one reusable suggestion drawer pattern. The drawer can be rendered
in the existing right-side shell rail or in the bottom drawer depending on the
step and available layout space, but the interaction contract is the same.

### 4.1 Drawer Anatomy

```text
┌──────────────────────────────────────────────────────────────┐
│ Rule Suggestions · Step 6                              [Close]│
│ Scope: [Rules] [Cross-Entity Rules] [Conflicts]              │
│                                                              │
│  Suggested rule: Account status must be ACTIVE               │
│  rule · rules.Account.accountId.cross-entity-field-check     │
│  Confidence 0.82 · 3 citations                               │
│  Rationale: BRD states blocked accounts cannot transact.     │
│  [View evidence] [Accept] [Edit] [Reject]                    │
│                                                              │
│  Suggested rule: Counterparty sanctions status in CLEARED    │
│  cross-entity rule · rules.Payment.counterpartyId...         │
│  Confidence 0.77 · 2 citations · Warning: requires FK rule   │
│  [View evidence] [Accept] [Edit] [Reject]                    │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Required Drawer Elements

- Title: user-facing scope name and step context.
- Scope selector or section tabs when more than one scope exists.
- Suggestion list with common row fields.
- Evidence affordance per row.
- Accept, edit, and reject controls per row.
- Save decisions / apply staged changes control when the step batches decisions.
- Close control.

### 4.3 Loading and Failure States

- Full suggestion lists are fetched only after an explicit badge click or user
  refresh from within the drawer.
- The drawer may show a short loading state after the badge is clicked.
- If fetch fails before the drawer opens, the badge should not appear.
- If fetch fails after the drawer has already opened, show a quiet empty state
  inside the drawer such as `Suggestions are unavailable right now. Manual
  authoring remains available.`
- Do not show degraded-mode banners in wizard steps.

### 4.4 Accessibility Expectations

- Badges are keyboard-focusable buttons.
- Opening the drawer moves focus to the drawer title or first actionable item.
- Escape closes the drawer.
- Close returns focus to the triggering badge.
- Drawer content has a clear accessible name.
- Tabs or scope selectors expose selected state.
- Action buttons have explicit labels; icon-only controls need `aria-label`.

---

## 5. Multi-Scope Behaviour by Step

### 5.1 Step 3 — Fields and Validation Hints

Step 3 can host two distinct Knowledge Assist scopes:

- existing field suggestions
- future validation hints

Badges:

- `N field suggestions`
- `N validation hints`

Drawer behaviour:

- Either badge can open the same drawer with the requested scope active.
- Field suggestions and validation hints must use separate sections/tabs.
- Validation hints must not appear inside the field acceptance editor.
- Field suggestions can edit field name, type, nullability, and description.
- Validation hints can propose constraints such as `not-null`, `max-length`,
  `pattern`, or `range`, but they must not silently mutate field definitions.

Example:

```text
Entity: Account                                   [4 field suggestions] [2 validation hints]

Drawer tabs: [Fields] [Validation]
```

### 5.2 Step 6 — Rules, Cross-Entity Rules, and Conflicts

Step 6 is the first multi-scope drawer target for KS-B2.

Scopes:

- `rules`
- `cross_entity_rules`
- `conflict_resolution` / conflict hints

Badges:

- `N rule suggestions`
- `N conflicts`

Drawer sections:

- Rule suggestions
- Cross-entity rule suggestions
- Conflict hints / conflict resolutions

Rules:

- Rule suggestions can prefill Step 6 authoring rows only after human accept or
  edit.
- Cross-entity rule suggestions must respect the existing Step 6 prerequisite:
  the FK field must already have or be paired with a valid
  `cross-entity-exists` rule.
- Suggested cross-entity rules must target the Engine-supported rule types:
  `cross-entity-field-check`, `cross-entity-field-compare`, and
  `cross-entity-field-in`.
- Type mismatch and invalid authoring state remain form-validation errors, not
  conflict cards.
- Conflicts remain advisory and non-blocking.

Example:

```text
Rules & Legacy Notes                              [5 rule suggestions] [2 conflicts]

Drawer tabs: [Rules] [Cross-Entity Rules] [Conflicts]
```

### 5.3 Step 4 / Passthrough / Kafka Future

Mapping and transform suggestions are future KS-B3 / KS-B4 work.

Rules:

- Badges attach to the route, interface, operation, or target section where the
  suggestion applies.
- Passthrough mapping suggestions can attach to the relevant inbound operation
  or downstream target section.
- Kafka fire-and-forget and request-reply mapping suggestions may attach to the
  route section.
- Kafka router transform suggestions are Wave 3 only and attach per router
  target in the Kafka Transform Mappings page.
- No schema, NACK, source-system extraction, reply-destination extraction, or
  routing-rule suggestions are introduced by this pattern.

Example:

```text
Kafka Transform Mappings
  Target d1_us_core                                  [3 transform suggestions]
  Target d2_eu_core                                  [4 transform suggestions]
```

### 5.4 Step 7 — Evidence Used

Step 7 is a review checkpoint, not a suggestion authoring step.

The `Evidence used` link appears only when at least one suggestion has been
accepted or edited in the current project state.

Drawer grouping:

- fields
- rules
- validations
- mappings
- transforms

Rules:

- The drawer groups provenance by suggestion type.
- Human-authored rules remain visible in Decision History separately.
- Human-authored rules must not be mislabeled as evidence-backed suggestions.
- Rejected suggestions may appear in Decision History, but not in `Evidence
  used` unless the review design explicitly includes rejected decision audit.

Example:

```text
Review Checkpoint                                      [Evidence used]

Drawer sections: [Fields] [Rules] [Validations] [Mappings] [Transforms]
```

---

## 6. Common Suggestion Row Contract

Every suggestion row in a drawer should be renderable from a common view model.

### 6.1 Required Row Fields

| Field | Purpose |
|---|---|
| `suggestion_id` | Stable identifier for decision write-back |
| `title` | Short row title |
| `summary` | Human-readable summary |
| `suggestion_type` | Field, validation, rule, mapping, transform, conflict |
| `target_manifest_path` | Stable dot-path target |
| `confidence` | Numeric confidence or bounded label |
| `citation_count` | Number of available citations |
| `rationale` | Short explanation of why the suggestion exists |
| `warnings` | Optional authoring or prerequisite warnings |
| `payload` | Type-specific proposed manifest payload |
| `status` | Pending, accepted, edited, rejected |

### 6.2 Required Row Actions

- Accept
- Edit
- Reject
- View evidence

Accepting or editing a row creates a reviewed Studio decision. Rejected rows
remain out of the manifest.

### 6.3 Edited Payload Behaviour

- Edit opens an inline detail editor or subordinate panel inside the drawer.
- Edited payloads must preserve the original `suggestion_id`.
- Edited payloads are submitted as `status=edited` with `edited_payload`.
- Accepted and edited suggestions can create evidence links when citations
  exist.
- Rejected suggestions do not create manifest entries or evidence links.

---

## 7. Evidence Behaviour

Evidence is on demand.

Rules:

- Citation detail is never pre-expanded in wizard steps.
- Each row exposes `View evidence`.
- Evidence detail can open in a nested drawer panel, bottom drawer tab, or
  Knowledge Workspace detail view.
- Evidence trail sidecar expansion happens later during export.
- No fake evidence is created for human-authored items.
- Future provenance labels such as `portfolio-pattern`, `le-extraction`, and
  optional AI-assisted classes remain compatible with the row contract.

Evidence labels:

| Source | User-facing label |
|---|---|
| Document-backed KS suggestion | Document evidence |
| Portfolio reuse | Portfolio pattern |
| LegacyExtractor future source | Legacy analysis |
| Human-authored item | Manual authoring |

`Manual authoring` is not evidence-backed unless a future explicit evidence
attachment feature is designed.

---

## 8. AssistService View Model Contract

This section defines expected future view models, not implementation code.

### 8.1 Badge Methods

Badge methods return `None` when:

- Knowledge Assist is OFF
- count is zero
- KS is unavailable
- fetch fails
- the current archetype/step does not support the scope

Example future methods:

```python
get_field_suggestion_badge(session, entity) -> SuggestionBadge | None
get_validation_hint_badge(session, entity) -> SuggestionBadge | None
get_rule_suggestion_badge(session, entity) -> SuggestionBadge | None
get_conflict_badge(session, entity) -> SuggestionBadge | None
get_mapping_suggestion_badge(session, route_name) -> SuggestionBadge | None
get_transform_suggestion_badge(session, route_name, target_id) -> SuggestionBadge | None
get_evidence_used_badge(session) -> SuggestionBadge | None
```

### 8.2 Drawer Fetch Methods

Drawer fetch methods return structured suggestion lists only after badge click
or explicit refresh.

Example future methods:

```python
fetch_suggestion_drawer(session, scope, context) -> SuggestionDrawerViewModel
fetch_suggestion_evidence(session, suggestion_id) -> SuggestionEvidenceViewModel
```

### 8.3 Route and Template Responsibilities

- Routes consume `AssistService` view models.
- Templates render badges and drawers from view models.
- Templates do not inspect raw `ks_active`, `ks_available`, subprocess status,
  or adapter warning state.
- Templates do not infer Knowledge Assist visibility from archetype alone.

---

## 9. UX Examples

### 9.1 Step 3 Badges and Validation Drawer

```text
Step 3: Entity Model

Account                                           [3 field suggestions] [2 validation hints]
──────────────────────────────────────────────────────────────────────────────
Field grid and operation selection remain visible here.

Drawer: Validation Hints
  [Fields] [Validation]

  amount
  validation · entities.Account.fields.amount.validation
  Suggest range min=0 from DDL constraint
  Confidence 0.86 · 2 citations
  [View evidence] [Accept] [Edit] [Reject]
```

### 9.2 Step 6 Rule and Conflict Badges

```text
Step 6: Rules & Legacy Notes                       [4 rule suggestions] [1 conflict]
──────────────────────────────────────────────────────────────────────────────
Business Rules form remains the main surface.

Drawer: Rules
  [Rule Suggestions] [Cross-Entity Rules] [Conflicts]
```

### 9.3 Step 6 Cross-Entity Rule Section

```text
Cross-Entity Rule Suggestions

Account must be ACTIVE for Payment.accountId
cross-entity-field-check · rules.Payment.accountId.cross-entity-field-check
Confidence 0.78 · 3 citations
Warning: requires cross-entity-exists prerequisite on Payment.accountId
[View evidence] [Accept] [Edit] [Reject]
```

### 9.4 Step 7 Evidence Used Drawer

```text
Review Checkpoint                                  [Evidence used]

Drawer: Evidence Used
  [Fields] [Rules] [Validations] [Mappings] [Transforms]

  Fields
    Account.status · ai-accepted · 2 citations
    Account.amountMinorUnits · ai-edited · 3 citations

  Human-authored rules
    Listed in Decision History, not counted as evidence-backed suggestions.
```

### 9.5 Empty / Zero-Suggestion State

Zero suggestions produce no badge:

```text
Step 6: Rules & Legacy Notes
──────────────────────────────────────────────────────────────────────────────
Business Rules form
```

No placeholder panel, no empty drawer, no degraded banner.

---

## 10. Out of Scope

This design spike does not implement:

- KS-B2 backend suggestion logic
- new KS tools
- Studio code changes
- Engine changes
- LegacyExtractor implementation
- optional AI runtime
- chat-first UI
- auto-accept suggestions
- always-visible suggestion panels
- schema/NACK/routing suggestions for Kafka router
- evidence-trail schema changes

---

## 11. Implementation Sequencing

This pattern becomes the UX prerequisite for broader Knowledge Assist work.

Recommended follow-on sequence:

1. **KS-B0 — KnowledgeServer schema migration**
   - Rename/generalize suggestion persistence for non-field scopes.
   - No Studio UI.

2. **KS-B1 KS — generic tool contracts**
   - Add `suggest_manifest_candidates`.
   - Add generic `get_suggestion_evidence_chain`.
   - Keep field-scope behaviour backward-compatible.

3. **KS-B1 Studio — integration wrappers**
   - Update `ks_integration.py` and `AssistService` wrappers for generic field
     scope first.
   - Keep existing field suggestion UX stable.

4. **KS-B2 KS — rules, cross-entity rules, validations backend**
   - Implement deterministic Wave 1 scopes.
   - Preserve human review and decision write-back.

5. **KS-B2 Studio — Step 6 and Step 3 badges/drawers**
   - Use this S8 pattern for rule, cross-entity rule, conflict, and validation
     badges.
   - Respect Step 6 cross-entity prerequisite semantics.

6. **KS-B2 Evidence — evidence-trail v1.1**
   - Extend evidence links with non-field suggestion types.
   - Do not mix human-authored rule rows with evidence-backed suggestions.

7. **KS-B3 — mapping and conflict suggestions**
   - Add mapping badges for passthrough and eligible Kafka route sections.
   - Add conflict-resolution suggestion handling where evidence exists.

8. **KS-B4 — Kafka router transform suggestions**
   - Add per-target transform badges only after router manifest paths remain
     stable.
   - No schema/NACK/routing suggestion surface in this design.

---

## 12. Approval Checklist

Before opening KS-B2 Studio UX PRs:

- [ ] This S8 design is reviewed and approved.
- [ ] Badge methods return `None` for OFF, zero, unavailable, and failed states.
- [ ] Templates render no suggestion UI when badge view models are `None`.
- [ ] Step 6 implementation keeps rule suggestions, cross-entity rule
      suggestions, and conflict hints separated.
- [ ] Step 7 keeps human-authored rules separate from evidence-backed
      Knowledge Assist suggestions.
- [ ] No wizard route exposes degraded Knowledge Assist warnings.
