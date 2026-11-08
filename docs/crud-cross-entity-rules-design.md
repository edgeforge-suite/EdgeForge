# EdgeForge CRUD Cross-Entity Business Logic Rules — Design Doc

> **Status:** Implemented design anchor / current contract reference as of the
> May 2026 suite baseline. Engine and Studio support the cross-entity field rule
> family `cross-entity-field-check`, `cross-entity-field-compare`, and
> `cross-entity-field-in`. Written 2026-04-21.
>
> Companion to:
> - [`docs/archive/target-state-features-v1.md`](archive/target-state-features-v1.md) — P3 backlog entry
> - [`appbuilder/rules/models.py`](../appbuilder/rules/models.py) — current rule model
> - [`appbuilder/generation/java_emitter.py`](../appbuilder/generation/java_emitter.py) — current generation site

---

## Problem Statement

The Engine currently supports one cross-entity rule: `cross-entity-exists`.

```yaml
# Current: can only ask "does this referenced entity exist?"
entity: Account
rules:
  - field: customerId
    type: cross-entity-exists
    target-entity: Customer
```

This is sufficient for referential integrity, but enterprise domains need
**conditional state-based rules** that span entity boundaries. Examples the current
engine cannot express:

- An Account with `status: BLOCKED` must reject any new Transaction debit
- A Transaction cannot be created if the source Account's `availableBalance < amount`
- A Payment cannot be initiated if the Counterparty's `sanctionsStatus != CLEARED`
- A Transfer between accounts in different currencies requires an FX record to exist first

These rules share a pattern: **the validity of an operation on Entity A depends on the
current state of a field in Entity B**, where B is referenced by A.

---

## Current Rule System Baseline

### Rule types in `RuleType` enum

| Rule type | Scope | What it checks |
|-----------|-------|----------------|
| `allowed-values` | Field | Value is in a fixed set |
| `default` | Field | Default value when not supplied |
| `format` | Field | ISO date, email, etc. |
| `max-length` / `min-length` | Field | String length bounds |
| `pattern` | Field | Regex match |
| `range` | Field | Numeric min/max |
| `not-null` | Field | Field must be present |
| `cross-entity-exists` | Cross-entity | Referenced entity row exists (`existsById`) |
| `field-comparison` | Cross-field | `field_a <operator> field_b` within same entity |

### What `cross-entity-exists` generates

```java
// Generated in create/update methods:
if (!customerRepository.existsById(account.getCustomerId())) {
    throw new ResourceNotFoundException("Customer not found with id: " + account.getCustomerId());
}
```

### Gap

`cross-entity-exists` only confirms the referenced row **exists**. It has no way to
inspect any field on the referenced row or express a conditional predicate.

---

## Proposed New Rule Types

### Rule 1: `cross-entity-field-check`

Checks a specific field on the referenced entity against a predicate.

```yaml
entity: Transaction
rules:
  - field: accountId
    type: cross-entity-field-check
    target-entity: Account
    target-field: status
    operator: eq
    expected-value: ACTIVE
    error-message: "Account is not active and cannot accept transactions"
```

**Generated Java (create/update):**

```java
Account account = accountRepository.findById(transaction.getAccountId())
    .orElseThrow(() -> new ResourceNotFoundException("Account not found with id: " + transaction.getAccountId()));
if (!"ACTIVE".equals(account.getStatus())) {
    throw new BusinessRuleException("Account is not active and cannot accept transactions");
}
```

**Supported operators:**

| Operator | Meaning |
|----------|---------|
| `eq` | `==` |
| `neq` | `!=` |
| `lt` | `<` |
| `lte` | `<=` |
| `gt` | `>` |
| `gte` | `>=` |

---

### Rule 2: `cross-entity-field-compare`

Compares a field on the **source entity** against a field on the **referenced entity**.

```yaml
entity: Transaction
rules:
  - field: accountId
    type: cross-entity-field-compare
    target-entity: Account
    target-field: availableBalance
    source-field: amount
    operator: lte
    error-message: "Transaction amount exceeds available balance"
```

This means: `transaction.amount <= account.availableBalance` — reject if false.

**Generated Java:**

```java
Account account = accountRepository.findById(transaction.getAccountId())
    .orElseThrow(() -> new ResourceNotFoundException("Account not found with id: " + transaction.getAccountId()));
if (!(transaction.getAmount().compareTo(account.getAvailableBalance()) <= 0)) {
    throw new BusinessRuleException("Transaction amount exceeds available balance");
}
```

**Type constraints:** both `source-field` and `target-field` must be numeric types
(`BigDecimal`, `Long`, `Integer`). The Engine must validate this at generation time.

---

### Rule 3: `cross-entity-field-in`

Checks that a field on the referenced entity is one of a set of allowed values.

```yaml
entity: Payment
rules:
  - field: counterpartyId
    type: cross-entity-field-in
    target-entity: Counterparty
    target-field: sanctionsStatus
    allowed-values:
      - CLEARED
      - PENDING_REVIEW
    error-message: "Counterparty sanctions status does not permit payment"
```

**Generated Java:**

```java
Counterparty counterparty = counterpartyRepository.findById(payment.getCounterpartyId())
    .orElseThrow(() -> new ResourceNotFoundException("Counterparty not found with id: " + payment.getCounterpartyId()));
if (!List.of("CLEARED", "PENDING_REVIEW").contains(counterparty.getSanctionsStatus())) {
    throw new BusinessRuleException("Counterparty sanctions status does not permit payment");
}
```

---

## YAML Schema Extensions

All three new rule types extend the existing external rule YAML format. The
`type` field is the discriminator; all new fields are additive.

```yaml
# Full schema for new rule fields:

entity: <string>                        # entity the rule applies to
rules:
  - field: <string>                     # FK field on this entity
    type: cross-entity-field-check      # or cross-entity-field-compare / cross-entity-field-in
    target-entity: <string>             # referenced entity name
    target-field: <string>              # field to inspect on target entity
    source-field: <string>              # (cross-entity-field-compare only) field on source entity
    operator: <eq|neq|lt|lte|gt|gte>   # (check and compare only)
    expected-value: <string>            # (check only) literal value to compare against
    allowed-values: [<string>, ...]     # (field-in only)
    error-message: <string>             # custom exception message (optional; default generated if omitted)
```

---

## `CanonicalRule` Model Changes

Three new `RuleType` enum values:

```python
CROSS_ENTITY_FIELD_CHECK = "cross-entity-field-check"
CROSS_ENTITY_FIELD_COMPARE = "cross-entity-field-compare"
CROSS_ENTITY_FIELD_IN = "cross-entity-field-in"
```

New optional fields on `CanonicalRule`:

```python
# Already present and reused:
target_entity: Optional[str] = None
operator: Optional[str] = None

# New:
target_field: Optional[str] = None        # field to inspect on target entity
source_field: Optional[str] = None        # field on source entity (field-compare only)
expected_value: Optional[str] = None      # literal expected value (field-check only)
error_message: Optional[str] = None       # custom error message
```

---

## Validation at Generation Time

The Engine must validate each new rule before emitting Java:

| Check | Rule types | Error |
|-------|-----------|-------|
| `target-entity` exists in metadata | all three | ValueError listing known entities |
| `target-field` exists on target entity | all three | ValueError with field name |
| `source-field` exists on source entity | field-compare only | ValueError |
| `source-field` and `target-field` are both numeric | field-compare only | ValueError (type mismatch) |
| `target-field` type is compatible with `expected-value` | field-check only | ValueError |
| `operator` is one of supported set | field-check, field-compare | ValueError |
| `allowed-values` is non-empty list | field-in only | ValueError |
| FK field type matches target entity ID type | inherited from cross-entity-exists | ValueError |

---

## Repository Lookup Deduplication

The emitter already maintains two separate collections for `cross-entity-exists`
(see `java_emitter.py` lines 1988–1024):

- `cross_entity_repos` — deduplicated by `target_entity`; drives one repository field
  and one constructor parameter per unique referenced entity type
- `cross_entity_checks` — all qualifying rules without dedup; drives one `existsById`
  check per FK field

This two-level split must carry forward for the new rule types, with one refinement:
the new rules use `findById` (to fetch the object for field inspection) rather than
`existsById`. The dedup key for `findById` calls is the **`(source_field, target_entity)`
pair**, not target entity alone.

### Why the dedup key is `(source_field, target_entity)`, not `target_entity`

Consider two FK fields on the same entity both pointing to `Account`:

```yaml
entity: Transfer
rules:
  - field: sourceAccountId
    type: cross-entity-field-check
    target-entity: Account
    target-field: status
    operator: eq
    expected-value: ACTIVE
  - field: destinationAccountId
    type: cross-entity-field-check
    target-entity: Account
    target-field: status
    operator: eq
    expected-value: ACTIVE
```

These need **two** `findById` calls because the lookup keys differ:

```java
// Two separate lookups — different FK source fields:
Account sourceAccount = accountRepository.findById(transfer.getSourceAccountId())
    .orElseThrow(...);
Account destinationAccount = accountRepository.findById(transfer.getDestinationAccountId())
    .orElseThrow(...);

if (!"ACTIVE".equals(sourceAccount.getStatus())) { ... }
if (!"ACTIVE".equals(destinationAccount.getStatus())) { ... }
```

But multiple rules on the **same** FK field share one `findById`:

```yaml
  - field: accountId
    type: cross-entity-field-check
    target-entity: Account
    target-field: status
    operator: eq
    expected-value: ACTIVE
  - field: accountId
    type: cross-entity-field-compare
    target-entity: Account
    target-field: availableBalance
    source-field: amount
    operator: lte
```

```java
// One lookup shared — same FK source field:
Account account = accountRepository.findById(transaction.getAccountId())
    .orElseThrow(...);

if (!"ACTIVE".equals(account.getStatus())) { ... }
if (!(transaction.getAmount().compareTo(account.getAvailableBalance()) <= 0)) { ... }
```

### Summary

| Dedup level | Key | What it controls |
|-------------|-----|-----------------|
| Repository field + constructor param | `target_entity` | One injected repo per referenced entity type |
| `findById` call per method | `(source_field, target_entity)` | One row fetch per unique FK lookup key |
| Per-rule checks | none — all rules emit | One predicate check per rule |

---

## Write-Path Coverage and Execution Order

### Write paths that receive cross-entity checks

The current emitter injects `cross-entity-exists` checks into four write paths
(confirmed in `java_emitter.py`):

| Write path | Location in emitter | Notes |
|------------|--------------------|----|
| `update` with DTO mappings | lines 2151–2158 | mapped field path |
| `update` generic | lines 2174–2182 | generic save path |
| `create` with op_context | lines 2229–2236 | DTO create path |
| `state_transition` | lines 2309–2316 | preserved custom operations |

The new `cross-entity-field-*` checks must be injected into **all four of these same
write paths** — not just create and update. `state_transition` operations are
first-class write paths in the generator and omitting them would silently skip
business-rule enforcement on custom operations like `releaseEarmark` or
`initiateTransfer`.

`computed_read` and `delete` are excluded from the new checks (read path and
delete path respectively; see "What This Does NOT Cover" for delete opt-in).

### Insertion point within each write path

The current emitter inserts `cross-entity-exists` checks **before**
`applyBusinessRules()`, not inside it. The new state-based checks follow the same
pattern — they are inline code emitted **after** field mapping and **before** the
`applyBusinessRules()` call:

```java
// 1. Field mappings (setters from request)
entity.setAccountId(request.getAccountId());

// 2. cross-entity-exists check (existsById — row must exist)
if (entity.getAccountId() != null && !accountRepository.existsById(entity.getAccountId())) {
    throw new ResourceNotFoundException("Account not found with id: " + entity.getAccountId());
}

// 3. NEW: cross-entity-field-* checks (findById — state-based)
Account account = accountRepository.findById(entity.getAccountId())
    .orElseThrow(() -> new ResourceNotFoundException("Account not found with id: " + entity.getAccountId()));
if (!"ACTIVE".equals(account.getStatus())) {
    throw new BusinessRuleException("Account is not active and cannot accept transactions");
}

// 4. applyBusinessRules (field-level rules: allowed-values, range, pattern, etc.)
applyBusinessRules(entity);
```

`applyBusinessRules()` remains unchanged — it contains field-level rule logic only.

---

## Exception Model

### Scope: new cross-entity business-rule checks only

The new `BusinessRuleException` applies **only to the three new rule types** in this
design. Existing rule violations are **not migrated**:

| Violation type | Exception | HTTP status | Changed? |
|----------------|-----------|-------------|---------|
| Referenced row not found (`cross-entity-exists`) | `ResourceNotFoundException` | 404 | No |
| Field-level rules (`allowed-values`, `range`, `pattern`, etc.) | `IllegalArgumentException` | 400 | No |
| New cross-entity state checks (`field-check`, `field-compare`, `field-in`) | `BusinessRuleException` (new) | 422 | **New** |

`IllegalArgumentException` → HTTP 400 is the current contract (see `java_emitter.py`
line 528). That mapping is preserved as-is. Migrating all field-level rules to 422
would be a breaking contract change and is explicitly out of scope for this PR.

### New exception class

```java
// Generated once per app when any cross-entity-field-* rule is present:
public class BusinessRuleException extends RuntimeException {
    public BusinessRuleException(String message) {
        super(message);
    }
}
```

### Global handler addition

A new `@ExceptionHandler` for `BusinessRuleException` is added to the existing
global handler class alongside the current `IllegalArgumentException` handler:

```java
@ExceptionHandler(BusinessRuleException.class)
@ResponseStatus(HttpStatus.UNPROCESSABLE_ENTITY)
public ErrorResponse handleCrossEntityBusinessRule(
        BusinessRuleException ex,
        HttpServletRequest request) {
    return new ErrorResponse(
        java.time.Instant.now().toString(),
        HttpStatus.UNPROCESSABLE_ENTITY.value(),
        "Unprocessable Entity",
        ex.getMessage(),
        request.getRequestURI()
    );
}
```

The `BusinessRuleException` class and handler are **only emitted** if the app's
manifest includes at least one `cross-entity-field-*` rule. Apps with no such rules
are unchanged.

---

## Manifest Contract Stability

These rules live in **external rule YAML files**, referenced from the manifest via the
existing `rules` array. The manifest schema (`manifest-v1.schema.json`) and
`schema_version: "1.0"` are **unchanged**.

No new manifest fields. No version bump. Additive rule YAML only.

---

## What This Does NOT Cover

These scenarios are explicitly out of scope for this design:

- **Multi-hop rules**: A depends on B which depends on C — only one level of reference is supported
- **Aggregation rules**: "sum of all Transaction amounts for this Account" — requires query-level logic, not field-level lookup
- **Mutation triggers**: rules that modify the referenced entity (e.g., decrement balance) — these are service orchestration, not rule validation
- **Async / eventual consistency**: all checks are synchronous within the service method transaction boundary
- **Engine MCP expansion**: no new MCP tools are added for this feature

---

## Implementation Sequence

| Step | Scope | Size |
|------|-------|------|
| 1 | Add three new `RuleType` values and new `CanonicalRule` fields | XS |
| 2 | Extend `ingestion.py` to parse the new rule YAML fields | S |
| 3 | Add generation-time validation checks in `java_emitter.py` | S |
| 4 | Add `BusinessRuleException` class generation and global handler wiring | S |
| 5 | Emit `findById` + field-check / field-compare / field-in logic in all four write paths: `update` (DTO), `update` (generic), `create` (op_context), `state_transition` | M |
| 6 | Implement `(source_field, target_entity)` dedup for `findById` calls across all four write paths | S |
| 7 | Add golden contract test fixture and unit tests | M |

Total estimated size: **one focused PR**, medium complexity.

---

## Golden Contract Requirement

A new fixture directory must be added covering at least:

- `cross-entity-field-check` on a status field
- `cross-entity-field-compare` on a numeric balance field
- `cross-entity-field-in` on an enum/status field

The golden contract must assert the generated service Java contains the correct
`findById` call, the predicate check, and the `BusinessRuleException` throw.

---

## Open Questions (Resolve Before Implementation)

1. **`error-message` default format**: if `error-message` is omitted, what is the
   generated default? Recommended: `"{TargetEntity} {targetField} does not satisfy rule for {sourceEntity}.{field}"`

2. **Delete method coverage**: should these checks also run on delete? For most
   enterprise scenarios, no — deletion is rare and existence-gated. Recommend delete
   coverage is opt-in via an `apply-on-delete: true` flag (default false), but
   this can be deferred to a follow-up.

3. **`field-compare` with nullable fields**: if `target-field` is nullable in the
   target entity, the emitted Java must null-check before compare. Recommend
   treating null as a rule violation (conservative default).

---

## Notes for Alignment (Non-Blocking)

### Operator dialect vs `field-comparison`

The existing `field-comparison` rule type uses **symbolic** operators
(`<=`, `<`, `>=`, `>`, `==`) — see `appbuilder/rules/ingestion.py` line 12:

```python
_FIELD_COMPARISON_OPERATORS = {"<=", "<", ">=", ">", "=="}
```

The new `cross-entity-field-check` and `cross-entity-field-compare` rules use
**named** operators (`lt`, `lte`, `gt`, `gte`, `eq`, `neq`). These are two different
dialects. The implementation PR must make an explicit choice between three options:

| Option | Description | Recommendation |
|--------|-------------|----------------|
| A — Named only (new style) | New rules use `lt`/`lte`/etc.; `field-comparison` keeps symbolic | **Preferred.** Named operators are more readable in YAML and safer to extend. |
| B — Symbolic only (old style) | Align new rules to `<=`/`<`/etc. to match `field-comparison` | Consistent but less readable for non-technical manifest authors. |
| C — Accept both dialects | Ingestion normalizes both to a canonical internal form | Most flexible but adds parsing complexity. |

Option A is recommended. If chosen, document that `field-comparison` uses symbolic
operators and the new cross-entity rules use named operators — both are valid but
they are distinct YAML conventions. A future cleanup pass can migrate
`field-comparison` to named operators without breaking existing manifests (additive
alias first, deprecate symbolic later).

### Nullable FK field handling

When the FK source field (`field:` in the rule YAML) is nullable, the current
`cross-entity-exists` emitter wraps the check in `if (value != null && ...)`. The
same null-guard applies to `findById` calls for the new rules:

```java
if (transaction.getAccountId() != null) {
    Account account = accountRepository.findById(transaction.getAccountId())
        .orElseThrow(...);
    // predicate checks follow
}
```

If the FK field is declared `not-null` in the manifest, the null-guard can be omitted.
The emitter should inspect the field's `not_null` metadata to make this decision.

### Studio authoring surface (future)

When Studio exposes rule authoring for the new types, the operator set and field-type
constraints defined here are the contract. Studio must not invent a different operator
vocabulary. See the full Studio authoring design in the appendix below.

---

## Appendix: Studio UX Impact

> This section defines what the cross-entity business logic rules mean for
> the Studio UI, framed within the **Studio UX v2 redesign**
> (`EdgeForgeStudio/docs/studio-ux-v2-design.md`). All Studio changes should
> be imagined against the new shell + right rail + bottom drawer frame, not
> the current wizard.

### Which step owns cross-entity rule authoring

**Step 6 — Rules, Mappings, and Conflict Workbench** is the correct home.

This is already the rules authoring step in the current wizard and is called out
in the UX v2 design as "the richest decision workbench in Studio v2." The three
new rule types are additive entries in the Step 6 rules form. No new step is needed.

### Step 6 main pane — rule form changes

The current Step 6 rules form has a `type` selector and a small set of fields that
vary by type. The three new types need new form shapes:

#### `cross-entity-field-check`

| Field | Control | Notes |
|-------|---------|-------|
| FK field | Dropdown | Fields on current entity with a cross-entity-exists rule already defined |
| Target entity | Read-only (derived from the FK field's existing cross-entity-exists rule) | Auto-filled once FK field is selected |
| Target field | Dropdown | Fields on the target entity (fetched from manifest metadata) |
| Operator | Dropdown | `eq`, `neq` only — for status/string checks |
| Expected value | Text input | Literal string or enum value |
| Error message | Text input (optional) | Defaults shown as placeholder |

#### `cross-entity-field-compare`

| Field | Control | Notes |
|-------|---------|-------|
| FK field | Dropdown | Same — must have an existing cross-entity-exists rule |
| Target entity | Read-only (derived) | Auto-filled |
| Target field | Dropdown | Numeric fields only on the target entity |
| Source field | Dropdown | Numeric fields only on the source entity |
| Operator | Dropdown | `lt`, `lte`, `gt`, `gte`, `eq`, `neq` |
| Error message | Text input (optional) | |

#### `cross-entity-field-in`

| Field | Control | Notes |
|-------|---------|-------|
| FK field | Dropdown | Same — must have an existing cross-entity-exists rule |
| Target entity | Read-only (derived) | Auto-filled |
| Target field | Dropdown | String/enum fields only on the target entity |
| Allowed values | Tag input (multi-value) | Comma-separated or add-one-at-a-time |
| Error message | Text input (optional) | |

### Constraint: FK field must already have a `cross-entity-exists` rule

The three new rule types are **state extensions of an existing reference**, not
standalone declarations. Studio must enforce this:

- The FK field dropdown for the new rule types shows only fields that already
  have a `cross-entity-exists` rule for the same target entity
- If no such rule exists, the UI shows an inline hint: _"Add a cross-entity-exists
  rule for this field first"_
- Target entity and target field dropdowns derive from manifest metadata — no
  freeform text entry

This constraint mirrors the Engine validation requirement and prevents
misconfigured rules from reaching generation.

### Right rail — Suggestions panel at Step 6

Per the UX v2 design, the right rail Suggestions panel at Step 6 is scoped to
**KS-sourced rule and mapping suggestions (future scope — currently empty state)**.

The cross-entity business logic rules are **manifest-authored**, not KS-suggested.
They appear in the main pane form only. The right rail Suggestions panel at Step 6
remains empty state until KS gains rule-suggestion capability (a later phase).

The right rail **Evidence panel** is read-only (per `studio-ux-v2-design.md` — the
panel shows citation chains, it does not accept author input). Cross-entity business
rules authored in Step 6 are manual authoring decisions, not KS suggestions, so
there is no evidence chain to display for them. The Evidence panel shows an empty
state for manually-authored rules.

If an author wants to capture the rationale for a cross-entity rule (e.g., "account
must be ACTIVE per rule X in the legacy business rules spec"), the appropriate
capture surface is the **error-message field** on the rule form, or the
**legacy notes textarea** that already exists in Step 6. Manual evidence linking
to the Evidence panel is out of scope for the baseline and would require a
design decision in a future slice.

### Right rail — Conflicts panel at Step 6

The Conflicts panel in the right rail surfaces `conflict_hint` signals from KS
suggestion cards and is unaffected by the new rule types. Cross-entity business
rules do not generate conflicts in the KS sense — they are author decisions.

If a rule introduced at Step 6 contradicts an entity field type set at Step 3
(e.g., `cross-entity-field-compare` selected on a non-numeric field), Studio should
surface this as an **inline validation error on the form**, not a conflict card.

### Step 7 — Provenance and Decision History

The new rule types produce YAML entries in the generated `rules/*.yaml` files.
Step 7 should include them in the manifest diff view and decision history. No new
panel or section is needed — the existing manifest diff and provenance surfaces cover this.

### Implementation slice placement

These Studio changes belong in **Slice 6 — per-step visual polish and form
hardening**, which is already scoped in the UX v2 design as the last implementation
slice. The new rule type forms are a targeted expansion of the Step 6 rules form
within that slice. No earlier slice is blocked by or requires these changes.

### Operator contract for Studio

Studio must use the **named operator dialect** (`lt`, `lte`, `gt`, `gte`, `eq`,
`neq`) for the three new rule types. The existing `field-comparison` rule type
continues to use symbolic operators (`<=`, `<`, `>=`, `>`, `==`) — these are
two separate form shapes in the Step 6 UI.

Do not merge the two rule type forms or coerce operator styles across them without
an explicit Engine ingestion migration first.
