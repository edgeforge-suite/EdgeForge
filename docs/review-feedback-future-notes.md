# Review Feedback Future Notes

Durable parking lot for non-blocking PR review observations that were accepted
for later follow-up. This file is intentionally not an implementation roadmap by
itself; use it as a review-audit checklist after major phases or before opening
design work.

## Status

This file remains a parking lot for generation-quality improvement items.

Items `#75`, `#77`, and `#87` (D10 derived read models and predicate-aware
query work) have been elevated into the P3 backlog in
[docs/archive/target-state-features-v1.md](archive/target-state-features-v1.md).

The Java emitter maintainability refactor from `#77` is treated as **P3-prep**
and should land before the deeper D10 derived-read and filtered-query work.

## Open Notes

| Source PR | Area | Note | Suggested Timing | Status |
|---|---|---|---|---|
| #75 | A3 computed reads | `computed_read` operations with no path parameter still use a generated `findAll().stream().findFirst()` placeholder. The generated output is TODO-marked, but domain-specific aggregate/query semantics remain unresolved. | Future query semantics / derived read design | Open |
| #76 | Read-only entity CRUD surface | Read-only/computed-read entities previously still exposed generic `PUT` and `DELETE`; PR #77 later addressed the surface-honesty part. Keep this here as resolved traceability for the blocker follow-up. | Addressed by #77 | Resolved |
| #77 | Explicit read surface data semantics | Explicit read-surface operations such as `Balance.getBalance(accountId)` can still return repository-backed 404s when the table has no data source. Correct data-source wiring, derivation, or query semantics remain design-first work. | Future derived read / read-model semantics | Open |
| #77 | Java emitter maintainability | Explicit read-surface list rendering and the generic `read_list` branch share similar `findAll()` plus DTO mapping logic. Consider extracting a helper before deeper filtered query or pagination work causes branch drift. | Refactor before major query-generation expansion | Open |
| #78 | Audit collision cleanup | `_audit_collision_metadata` tracks all business column names in `occupied_columns`, even though only audit-column collisions matter. This is correct today because audit renderers check only audit columns, but it could be tightened to store only matching audit columns. | Opportunistic emitter cleanup | Open |
| #82 | Datasource fallback consistency | `datasource_username` fallback used a falsy check while `datasource_password` used an explicit `is not None` pattern. Standardize fallback handling if datasource profile fields are revisited. | Future profile cleanup | Open |
| #82 | PostgreSQL dialect explicitness | PostgreSQL profiles rely on Hibernate dialect auto-detection. Consider emitting `spring.jpa.database-platform: org.hibernate.dialect.PostgreSQLDialect` explicitly for PostgreSQL profiles. | Future C8/profile polish | Open |
| #83 | Target profile catalog duplication | `springboot-enterprise-postgres-java17` and `springboot-standard-enterprise` are nearly identical except for Java baseline. If more Java-version variants are added, factor shared enterprise PostgreSQL defaults into a builder/base helper. | When adding a third Java/profile variant | Open |
| #86 | Source-path convention dependency | `_create_request_fields` distinguishes request-side mappings using the `".request."` segment in `FieldMapping.source_path`. This is correct for current REST JSON paths, but future non-request/response contract types should avoid depending on that convention implicitly. | Future contract-type expansion / mapping abstraction | Open |
| #87 | Filtered list pagination | List operations with path/query predicates, such as `listTransactionsByAccount(accountId)`, still use repository-wide `findAll(...)` / `findAll(pageable)` without predicate-aware query generation. This predates B7 and should be handled with filtered query semantics, not as a B7 regression. | Future filtered query / predicate-aware pagination design | Open |
| #90 | A1 identity override diagnostics | `identity_override` lookup uses entity-name key matching via `.get(entity_group_name)`. If entity naming/key normalization drifts in future C9/observability work, add explicit diagnostics so a declared override cannot be silently missed. | Future C9 / identity observability | Open |
| #92 | Java emitter import cleanup | `SequenceGenerator` is imported unconditionally for generated entities after C9. This is harmless because it is on the JPA classpath, but can be made conditional if import hygiene is revisited. | Opportunistic Java emitter cleanup | Open |

## Maintenance Rules

- Add notes here when a PR review calls out a non-blocking issue that is merged
  without being fixed.
- Keep entries concise and link them to a source PR.
- Mark notes `Resolved` rather than deleting them when a later PR intentionally
  addresses the deferred issue.
- Do not use this file for active blockers; blockers should be fixed before
  merge or tracked in the relevant implementation PR.
