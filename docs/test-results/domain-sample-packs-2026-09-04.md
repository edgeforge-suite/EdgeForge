# Domain Sample Packs — S1 Closeout Evidence

**Result:** PASS — A1–A16 complete at the pinned Engine and Studio revisions

**Executed:** 2026-09-04

**Scope:** Studio sample-pack open/export proof, one representative browser open, and Engine validation/generation/build/independence proof

## Pinned Revisions

| Repository | Revision |
|---|---|
| Engine | `8b1fa80a1ff7c2d063fcd315ebeb22e816f026e0` |
| Studio | `d23d99f480e242291750724d192875e53b37e85f` |

Both revisions were checked out in clean worktrees before proof began. The Engine acceptance driver
confirmed that both HEADs and working trees remained unchanged and that all exported packages and
generated applications were removed with the temporary proof root.

## Environment

- macOS 26.5 (`arm64`)
- Engine Python 3.11.15
- Studio Python 3.11.15
- Apache Maven 3.9.12
- OpenJDK 21.0.12.1 for `springboot-standard-enterprise`
- OpenJDK 17.0.18 for `springboot-legacy-compatible`
- Codex in-app browser for the manual A9 open

The Studio interpreter and Java homes were supplied through the driver's documented environment
variables. No local checkout path, temporary path, or generated output is retained by this record.

## Studio Proof

From the pinned Studio worktree:

```bash
python -m pytest tests/test_domain_sample_packs.py -q
```

Result: `27 passed in 0.83s`.

This focused suite covered A1–A8 and A9b for all three packs: production-path open and restore,
authored-state round trip, archetype/readiness state, production package export, exact exported trees,
manifest `2.0`, empty export-warning contracts, Knowledge Assist off with process spawning guarded,
filesystem-path hygiene, absent committed export paths, public open/save/export behavior, and exact
derived-review-copy alignment with the canonical Studio project JSON.

### Manual Browser A9

The pinned Studio checkout was started in default local mode and the FS Account Servicing project was
opened through the real **Open Project** browser control. The project loaded without an error as
**Synthetic Account Servicing**, bounded context `account-servicing`, archetype `crud`, and target
profile `springboot-standard-enterprise`. Knowledge Assist remained visibly **Off**.

The Studio Review page exposed the authored state for review: one `Account` entity, one upstream REST
interface, one staging-table handoff, one fixed-width downstream contract, and one rule file. Its trace
showed the Account source, canonical entity, staging handoff, and fixed-width output; the review summary
showed three ready items, zero warnings, and zero contract blockers. This was an open/review check only;
no browser export or generated-app runtime claim is made.

## A1–A16 Matrix

| Check | FS Account Servicing | HC Authorization Status | INS Claims Intake Router |
|---|---|---|---|
| A1–A8 | PASS | PASS | PASS |
| A9 | PASS — representative browser open | Not applicable — one representative open required | Not applicable — one representative open required |
| A9b | PASS | PASS | PASS |
| A10 | PASS — manifest `2.0` | PASS — manifest `2.0` | PASS — manifest `2.0` |
| A11 | PASS — 32 files, zero warnings | PASS — 36 files, zero warnings | PASS — 21 files, zero warnings |
| A12 | PASS — harness, zero warnings | PASS — harness, zero warnings | Not applicable — passthrough emits no harness report |
| A13 | PASS — Java 21 package | PASS — Java 17 verify | PASS — Java 17 verify |
| A14 | PASS — source and packaged JAR | PASS — source and packaged JAR | PASS — source and packaged JAR |
| A15 | PASS — clean pinned repos; temporary output removed | PASS — clean pinned repos; temporary output removed | PASS — clean pinned repos; temporary output removed |
| A16 | PASS — 12 byte-identical; 2 narrowly normalized | PASS — 12 byte-identical; 2 narrowly normalized | PASS — 8 byte-identical; 2 narrowly normalized |

The two A16 normalization exceptions were exactly `evidence-trail.json` and `studio-project.json`, using
the field allowlists frozen in the design. No other exported file differed between the two fresh runs.

## Engine Proof

From the pinned Engine worktree, with an explicit absolute clean Studio worktree supplied only at
runtime:

```bash
python scripts/smoke/domain_sample_packs.py \
  --studio-checkout <absolute-clean-studio-worktree>
```

Overall result: `Domain sample-pack acceptance: PASSED`.

| Pack | Archetype | Profile | Build proof |
|---|---|---|---|
| `fs-account-servicing` | `crud` | `springboot-standard-enterprise` | Java 21; `mvn -q clean package -DskipTests` passed |
| `hc-authorization-status` | `crud` | `springboot-legacy-compatible` | Java 17; `mvn -q clean verify` passed |
| `ins-claims-intake-router` | `passthrough-router` | `springboot-legacy-compatible` | Java 17; `mvn -q clean verify` passed |

Every export warning list and generation warning list was empty. Both applicable CRUD harness reports
passed with empty warning lists; INS-CLAIM correctly returned no harness report. Source and packaged-JAR
independence checks passed for every generated application, including repository-boundary, Java import,
Maven boundary, schema-baseline applicability, repository hygiene, author-path, and packaged-JAR checks.
No Engine, Studio, Knowledge Server/Assist, MCP, or generator-owned runtime dependency was found.

The driver's one top-level warning was the expected bootstrap notice:
`Slice 3 pinned domain-sample-pack evidence is not recorded yet`. It reports evidence staleness only and
is distinct from the empty export, generation, and applicable-harness warning contracts. This evidence
record resolves that bootstrap condition for the pinned SHA pair.

## Engine Focused Tests

```bash
python -m pytest tests/unit/test_domain_sample_packs_driver.py -q
```

Result: `41 passed in 0.29s`.

The focused suite includes the existing fail-closed controls for checkout/proof validation, exact pack
inventory, warning and artifact drift, independent export roots, narrow normalization, CLI-only failure,
Maven/JDK mismatch, repository dirtiness or HEAD movement, output confinement, subprocess failures, and
cleanup after success or failure.

## Residual Limits

- S1 proves Studio open/export plus Engine validate/generate/build/independence; it does not claim
  generated-app runtime E2E or database/container operation.
- A9 is one intentional manual representative browser open. S1 adds no automated browser harness.
- Suite-tracker reconciliation and S8 adopter-onboarding assembly remain separately serialized follow-up
  work.

## Conclusion

The three canonical Studio sample packs satisfy the frozen A1–A16 contract at the pinned revisions.
Domain Sample Packs S1 and its three implementation slices are verified complete.
