# Domain Sample Packs — Design (S1)

> **Editorial publication summary (2026-11-01):** external-application names and
> contract-specific details have been withheld. Historical dates, results and
> limitations below refer to privately retained original evidence, not the
> new Workspace/Item example. Complete originals remain at private source
> `8a94e5697c2ccd02f917ee7f94385f02d6a22398`; this is not fresh acceptance.

> **Status:** DESIGN **FROZEN — rev-6; S1 VERIFIED** — no open decisions (§13). Studio Slice 1 and its bounded source
> correction are merged through PR #298 at `d23d99f`; Generated-App Security Slices 1–4 and the
> passthrough reader-first closure are merged through Engine PR #306 at `9e2e7ac`. Engine Slice 2 is
> merged through PR #307 at `8b1fa80`. Slice 3 verified the frozen A1–A16 contract on 2026-09-04 against
> Engine `8b1fa80a1ff7c2d063fcd315ebeb22e816f026e0` and Studio
> `d23d99f480e242291750724d192875e53b37e85f`, including the manual A9 browser open; durable evidence is
> recorded in [`docs/test-results/domain-sample-packs-2026-09-04.md`](test-results/domain-sample-packs-2026-09-04.md).
> No exported package or generated application is committed, and the Suite tracker remains untouched.
>
> **rev-2 corrections** (bounded revision, no architectural change; Studio JSON remains canonical):
> **(1)** `contracts/`/`samples/` reclassified as **derived review copies** with a CI byte-compare —
> Studio's export reads content embedded in the project JSON and never opens a sibling file, so
> hand-maintained siblings would have been a silent second source (§5.4). **(2)** Verified SHAs removed
> from `expected-proof.json` and kept only in the Engine closeout evidence — recording a Studio SHA
> inside a Studio file is circular and would have forced a fourth slice (§9). **(3)** The browser check
> moved out of Studio CI to a **manual** closeout step — Studio deliberately has no jsdom/Playwright
> harness and S1 does not introduce one (§7.1). **(4)** Pack contents specified concretely — fields,
> IDs, operations, DDL columns, layout offsets, XML structure, routing values (§6.1-§6.4). **(5)** Engine
> acceptance now requires the harness to pass **with zero warnings**, because staging run-identity is only
> `ERROR` under an M5a opt-in Studio cannot author (§7.2). **(6)** Path hygiene scoped to enumerated
> filesystem path fields — the earlier blanket leading-`/` rule would have rejected every valid OpenAPI
> route (§7.1).
>
> **rev-3 corrections** (bounded revision, no architectural change; Studio JSON remains canonical):
> **(1)** INS-CLAIM rewritten as an actually-buildable pack — Studio only writes passthrough rules when
> `default_target` **and** `transforms` are both non-empty, and Engine rejects an empty routing/transform
> list outright; both shipped passthrough examples confirm the fail-closed posture is "route the
> unmatched case somewhere," not "reject it" (§6.3). **(2)** Canonical-source language de-contradicted —
> D1, §8's "checked-in derivatives," the risk table, and the header rule all now agree with §5.4's actual
> mechanism, and the header rule no longer requires an in-file comment on JSON, which cannot carry one
> (§5.2, §6, §8). **(3)** HC-AUTH's XML namespace and INS-CLAIM's downstream operation IDs/transforms
> specified; each pack's exact exported-artifact allowlist added (§6.2, §6.3, §9). **(4)** Rebased onto
> current Engine `main`; Security Slice 1 recorded as implemented (Engine PR #301), with final S1
> acceptance still gated on Slices 2–4 (§8). **(5)** Stop conditions clarified to forbid only *committed*
> absolute/adjacent-repo paths — the Engine driver's required runtime Studio-checkout argument was never
> the target of that redline (§11).
>
> **rev-4 corrections** (bounded revision, no architectural change; Studio JSON remains canonical):
> **(1)** The exported-artifact allowlist is now **derived rather than described** — a session was built
> per §6 and Studio's real `write_package_result` executed at the grounding SHA, and §9.1 records the
> complete literal tree each pack produces. The earlier list was neither complete nor exact: it named two
> common files where the writer unconditionally writes **five**, and omitted the rule files, the operation
> samples, the `data-handoffs/` staging paths and the `contracts/` spec path. **A6** now asserts exact
> tree equality, and the incorrect "A9b/A6" cross-reference is gone — A9b is the source-derivative
> byte-compare and always was (§9.1, §10.2). **(2)** `expected-proof.json` is described as what it is:
> pack-local proof metadata consumed by **both** the Studio acceptance tests and the Engine driver (§9).
> **(3)** Ownership de-contradicted — the adopter-facing pack index is **Studio's**; Engine owns the
> design home only (§5.2) — and the obsolete "Security Slice 1 owns the tracker lane" clause is removed
> while the serialization rule stays (§11). **(4)** Four facts found by *executing* the writer and the
> generator rather than reading them: the passthrough lane exports no operation samples and receives **no
> harness report at all**, so A12 binds the two CRUD packs only (§7.2); a zero-generation-warning build
> needs two authoring rules — complete response mappings and `VARCHAR(36)` staging id columns (§6.1,
> §6.2, §7.2); exactly two exported files are volatile (§9, A16); and a project saved *after* an export
> commits an absolute machine path, which would trip this design's own stop condition (§7.1 item 9).
> **(5)** Committed review copies re-specified as one file per embedded JSON field under a fixed per-pack
> extraction map, with every authored OpenAPI document in JSON (§6). **(6)** Rebased onto current Engine
> `main`; Security Slice 2 recorded as merged (§8).
>
> **rev-5 correction** (bounded revision, no architectural change; Studio JSON remains canonical):
> **(1)** The rev-4 claim that the derivation run left **every** package-path field unset was false for
> one pair per CRUD pack. `package_writer.py:300-305` never defaults the two operation-sample paths — no
> other writer-derived path works that way. In real Studio use they are assigned earlier, by the
> operation-selection authoring route (`app/routes/entities.py:2746-2762`), as
> `upstream/sample-{slug(operationId)}-{request,response}.json`, where the slugger does not split
> camelCase. The rev-4 fixture set these two fields to that exact convention before calling the writer —
> so the derivation was faithful to real Studio behavior — but the filenames it produced,
> `sample-create-account-*` / `sample-create-authorization-*`, were **not** what that convention actually
> emits: `createAccount`/`createAuthorization` have no non-alphanumeric boundary for the slugger to find,
> so the real paths are `sample-createaccount-*` / `sample-createauthorization-*`. Corrected throughout
> §6.1, §6.2, and §9.1, and re-verified against a fresh writer + generator run: same 14/14/10 counts, same
> zero warnings, only the two filenames changed. §9.1 now states the exception explicitly instead of
> asserting a blanket rule that had one unstated carve-out, and its maintenance rule now names the
> authoring route as a second thing that can move the CRUD sample paths, alongside the writer.
>
> **rev-6 correction** (bounded source reconciliation after the stopped first Slice 2 run; external
> contracts unchanged): **(1)** The first real Engine acceptance run exposed two pack-source defects:
> integer-shaped FS-ACCT `balance` examples caused sample inference to conflict with the declared decimal
> staging field, and HC-AUTH's canonical `Authorization` entity generated the H2-reserved unquoted table
> name `authorization`. Studio PR #298 made every FS `balance` and HC `serviceUnits` example
> decimal-shaped, aliased the HC canonical entity to `AuthorizationRecord`, and consequently changed its
> rule artifact to `rules/authorizationrecord-business-rules.yaml`. **(2)** The external HC OpenAPI and
> XML vocabulary remains `Authorization`, including routes, schema/root names, and interface filenames;
> only the generated canonical entity/table identity changed. **(3)** A13 is profile-aware: PostgreSQL
> profiles use `mvn -q clean package -DskipTests` with their declared Java baseline because this slice
> provisions no database, while H2 profiles use `mvn -q clean verify`. **(4)** Generic reserved-identifier
> protection and broader OpenAPI sample/schema-reader precedence remain separate residual work; the pack
> correction does not claim either platform-wide issue resolved.
>
> **Grounded against (rev-5):** Engine `origin/main @ 4aa09ae067632ea5f0f7fd41bf8d33248e579440`
> (includes merged PR #301, Security Slice 1, and merged PR #303, Security Slice 2) · Studio
> `origin/main @ ac51a4674b0e1206f12719bbee9eacd7a64c8222` (unchanged since rev-1). Both re-verified
> immediately before this revision, and the §9.1 trees were produced by executing Studio's package writer
> and Engine's generator at that Studio/Engine SHA pair. Original grounding: Engine
> `dfc2b00997b7d27a743fbf053af34e4101eff9ca`.
>
> **Current implementation and proof grounding:** Engine
> `origin/main @ 8b1fa80a1ff7c2d063fcd315ebeb22e816f026e0` (includes PR #307, its A10–A16
> driver, PR #306, and all four generated-app security slices) · Studio
> `origin/main @ d23d99f480e242291750724d192875e53b37e85f` (includes PR #297, correction PR
> #298, and all three maintained packs). The same exact SHA pair passed the 2026-09-04 Slice 3 closeout
> recorded in [`docs/test-results/domain-sample-packs-2026-09-04.md`](test-results/domain-sample-packs-2026-09-04.md).
> The rev-1 through rev-5 grounding above remains the historical design record.
>
> **Source:** roadmap **S1** (`docs/enterprise-readiness-roadmap.md:157`) — *"Loadable synthetic Domain
> Sample Packs aligned to the website's Financial Services, Healthcare/Payer Operations, and Insurance
> lenses… each must open, export, generate, and compile."* Classified **parallel-safe** in
> [`docs/suite-security-review-backlog.md:479`](suite-security-review-backlog.md).
>
> **Suite scope:** Engine + Studio. KS/KA not required and not used. TestBench excluded.

## 1. Decision summary

| # | Decision | Choice |
|---|---|---|
| D1 | Canonical authoring source | **The Studio project JSON alone is canonical.** Everything else — `contracts/`, `samples/`, and the Engine package produced during proof — is derived. Engine packages are **never committed**; `contracts/`/`samples/` **are** committed, but only as CI-verified derived copies extracted from the JSON (§5.4). |
| D2 | Engine-side committed derivative | **None.** No checked-in manifest package, so no cross-repo parity guard is needed and none is built. |
| D3 | Pack count and shape | Three packs, one per website lens, each **deliberately narrow** — not three "everything demos." |
| D4 | Archetype coverage | CRUD ×2, passthrough-router ×1. **Kafka deliberately excluded** — see §3.1. |
| D5 | Contract-family coverage | REST/OpenAPI ×3, fixed-width file ×1, staging handoff ×2, XML/XSD ×1. **SOAP/WSDL excluded** — see §3.1. |
| D6 | Target profiles | Two of the three shipped profiles exercised; the third is covered by existing Engine examples. |
| D7 | Studio proof depth | Service/route-level proof for all three packs in Studio CI. **No browser check in CI** — Studio has no browser harness and S1 does not introduce one; one manual browser open is a Slice-3 closeout step (§7.1). |
| D8 | Engine proof depth | Validate + generate + compile for all three. **No runtime E2E** — §7.3 states why. |
| D9 | Acceptance ownership | Studio owns open/save/export; Engine owns validate/generate/compile; final evidence is a pinned manual cross-repo run, **not** cross-repo CI. |
| D10 | Security sequencing | Authoring runs in parallel with Security Slices 1–4; **final acceptance runs after all four merge**, pinned to post-security SHAs. |
| D11 | Slice count | **3 PRs** — one Studio, one Engine, one closeout. Verified SHAs live only in the Engine closeout evidence, so no fourth PR is needed to record them (§9). |
| D12 | Contract artifacts on disk | Committed as **derived review copies** extracted from the project JSON, guarded by a Studio-CI byte-comparison. The project JSON stays the only source Studio reads (§5.4). |
| D13 | Staging run identity | Both staging DDLs declare a recognized `RUN_ID` column and a primary key, and acceptance asserts **zero harness warnings** — because Studio cannot author M5a `run_semantics` (§7.2). The harness runs only on the CRUD lane, so this bar binds FS-ACCT and HC-AUTH; INS-CLAIM gets no harness report at all (§7.2). |

## 2. Source-evidence table

Every fact this design depends on, verified at the grounding SHAs.

| Claim | Evidence | Verified |
|---|---|---|
| Three shipped target profiles, all `emit_security=False` | `appbuilder/target_profiles/catalog.py:18,32,49,66` — executed the catalog | ✅ |
| Three shipped archetypes | `appbuilder/metadata/models.py` `AppArchetype` — executed: `['crud','passthrough-router','kafka-integration']` | ✅ |
| Studio project schema `1.4` | `EdgeForgeStudio/app/models/project.py:16` — `STUDIO_PROJECT_SCHEMA_VERSION = "1.4"` | ✅ |
| Studio exports manifest `2.0` only | `EdgeForgeStudio/app/services/manifest_contract.py:7` — `STUDIO_MANIFEST_SCHEMA_VERSION = "2.0"`; consumed at `manifest_generator.py:38` | ✅ |
| Project files and manifest packages are distinct artifacts | `project_file_service.py:277` `save_project` (project JSON) vs `package_writer.py:154` (manifest package tree) — different writers, different shapes | ✅ |
| Studio auto-migrates older project files on open | `project_file_service.py:330` calls `_migrate_project_to_current_schema`; chain `_migrate_v1_0_to_v1_1` … `_migrate_v1_3_to_v1_4` at `:341-408`; loop at `:413-431` | ✅ |
| Unsupported project versions fail closed | `project_file_service.py:320-328` — raises `ValueError` listing supported versions | ✅ |
| Studio open/save routes | `EdgeForgeStudio/app/routes/project_file.py:42` prefix `/project`, `:101` `POST /open`, `:74` `POST /save` | ✅ |
| Package writer enforces package-relative artifact paths | `package_writer.py:154` writes to `root/<project-slug>/`; `:222` rejects colliding paths with *"Choose unique package-relative paths…"* | ✅ |
| KA default OFF | `EdgeForgeStudio/app/models/project_capabilities.py:15` — `knowledge_assist_enabled: bool = False` | ✅ |
| **No committed Studio sample project exists today** | `git grep -l studio_project_schema_version -- '*.json'` → empty. Only project-shaped JSON is `tests/fixtures/security/hostile_saved_project.json`, an XSS fixture. Tests build via `snapshot_session`/`deserialize_project` | ✅ |
| Engine examples are manifest-first, not Studio projects | `examples/input-projects/` — 7 packages, each rooted at `app-definition.yaml`; none contains a Studio project JSON | ✅ |
| Engine CLI surface | `python -m appbuilder.cli --help` → `{generate,plan,apply,assess}`; `--validate-schema` documented at `examples/input-projects/README.md` | ✅ |
| Compatibility harness exists | `appbuilder/harness/` — `checks.py`, `models.py`, `runner.py` | ✅ |
| Layered smoke L0–L5 exists; L4 is cross-repo | `docs/suite-smoke-harness-design.md:51-101` — L4 *"Cross-repo Studio → Engine → KS smoke"* | ✅ |
| Website lens vocabulary | `docs/marketing/EdgeForge_Suite_Website.html` — `key:'financial'` (`Account`, `ACCOUNT_STG.ddl`, `ACCT_EOD.layout`), `key:'healthcare'` (`Authorization`, `AUTHORIZATION_STG`), `key:'insurance'` (`Claim`, `CLAIM_STG`) | ✅ |
| S1 is parallel-safe | `docs/suite-security-review-backlog.md:479` — *"Parallel-safe throughout: S1 domain packs, S9 documentation cleanup."* | ✅ |
| Security slices change generated output across archetypes | `docs/generated-app-standards/generated-app-security-posture-design.md:345-348` — Slice 1 README/Kafka actuator, Slice 2 CRUD pagination, Slice 3 passthrough validation, Slice 4 headers (all archetypes) | ✅ |
| **Export writes from content EMBEDDED in the project JSON** | `package_writer.py:281-305,318-326,376-378` — writes `iface.spec_content`, `iface.xsd_content`, `iface.wsdl_content`, `iface.sample_content`, `op.request_sample_content`, `handoff.ddl_content`. It never reads a sibling file from disk | ✅ drives D12 |
| **Studio has no browser test harness, by choice** | `EdgeForgeStudio/tests/test_step3_render_snapshots.py:4-6` — *"Studio intentionally has no Node/jsdom or Playwright harness"*; same note repeated in `test_step7_trace_lens.py:505`, `test_step5_tab_badge_focus.py:9,204`, `test_step2_seed_patch.py:5` | ✅ drives D7 |
| **Harness `passed` ignores WARNING-severity checks** | `appbuilder/harness/models.py:35-40` — `passed` filters to `severity == ERROR` only | ✅ drives D13 |
| **Staging run-identity is ERROR only when opted into `run_semantics`** | `appbuilder/harness/checks.py:236-240` — `ERROR if opted_in else WARNING`; non-opt-in branch at `:230-234` passes when a recognized run-ID column exists | ✅ drives D13 |
| **Studio cannot author `run_semantics`** | `grep -rn run_semantics EdgeForgeStudio/app --include='*.py'` → **zero hits**. A Studio-authored pack cannot opt in | ✅ drives D13 |
| Recognized staging operational column names | `appbuilder/generation/utils.py:181-189` — run-ID role matches normalized `runid` / `eodrunid`; PK detected via `parse_sql_table_columns` | ✅ |
| Existing shipped example lacks run identity | `examples/input-projects/loans-modernization/contracts/loan-staging-table.sql` — no primary key, no run-ID column, so it emits the WARNING today | ✅ confirms D13 is live, not theoretical |
| Real fixed-width layout format | `examples/input-projects/xyz-accounts-modernization/downstream/eod-handoff-layout.yaml` — `name:` + `fields: [{name,start,length}]` | ✅ |
| **Five files are written unconditionally on every export** | `package_writer.py:531` (`app-definition.yaml`), `:537` (`completeness-report.md`), `:552` (`assessment-report.json`), `:559` (`evidence-trail.json`), `:576` (`studio-project.json`) | ✅ drives §9.1 |
| **Package paths are derived from slugified names when the author sets none** | `package_writer.py:284,309,321-322,347,354,362,376,381,511,517`; `edge_contracts.py:313-321` (`default_artifact_path`) | ✅ drives §9.1 |
| **The two CRUD operation-sample paths are the one exception — the writer never defaults them** | `package_writer.py:300-305` writes a sample only when its path AND content are both already set, with no `default_...path()` call; real paths come from `app/routes/entities.py:2746-2762` at operation selection, as `upstream/sample-{slug(operationId)}-{request,response}.json` (`entities.py:220-221` for `slug`, which does not split camelCase) | ✅ drives §6.1, §6.2, §9.1 |
| **The passthrough lane exports no operation samples and no upstream mapping** | `package_writer.py:262-270` — the branch `continue`s before the sample block (`:300-305`) and the upstream-mapping block (`:308-311`) | ✅ drives §6, §9.1 |
| **The three exported trees in §9.1** | Executed Studio's `write_package_result` at the grounding Studio SHA against a session built to §6 for each pack: 14 / 14 / 10 files, **zero export warnings** for all three | ✅ derived, not sketched |
| **Only two exported files are volatile** | Two exports of the same session, compared file by file: `evidence-trail.json` and `studio-project.json` differ; every other file is byte-identical | ✅ drives A16 |
| **The compatibility harness runs on the CRUD lane only** | `generation/engine.py:330` (CRUD) vs `:145-150` (Kafka) and `:457-462` (passthrough), both returning `harness_report=None`; `cli.py:252-253` prints `Harness: NOT RUN`. Generating all three packs confirms it: CRUD `passed=True, errors=0, warnings=0`; INS-CLAIM no harness report | ✅ drives A12 |
| **All three packs generate with zero generation warnings** | `python -m appbuilder.cli generate --validate-schema` against each exported package, after the two §7.2 authoring rules are applied | ✅ drives A11 |
| **An unmapped response-sample field warns** | `appbuilder/metadata/translation.py:2791-2801` — *"auto-included in canonical model; add an explicit mapping to silence this warning"* | ✅ drives §7.2 |
| **A staging `*Id` column below `VARCHAR(36)` warns** | `appbuilder/metadata/translation.py:2980-3003`; the canonical width is protected at `:2970-2977` | ✅ drives §6.1, §6.2 |
| **A saved project can carry an absolute export path** | `project_file_service.py:117` copies `last_export_path`; every export appends `KSManifestRevision.export_path` (`models/project.py:453-459`, `package_writer.py:564-574`) | ✅ drives §7.1 item 9 |
| S1 tracker row is `pending` | `docs/tracker/suite-tracker.json` row `S1-domain-sample-packs`, `status: pending`, `last_updated: 2026-07-13` | ✅ (not modified by this PR) |

## 3. Portfolio matrix

The website already fixes each lens's vocabulary. The packs adopt it so the samples and the marketing
narrative cannot drift apart.

| | **FS-ACCT** | **HC-AUTH** | **INS-CLAIM** |
|---|---|---|---|
| Display name | Account Servicing | Authorization Status | Claims Intake Router |
| Lens | Financial Services | Healthcare / Payer Operations | Insurance |
| Business problem | Account servicing API replacing a legacy core, owing an EOD file and a staging handoff | Authorization status service owing a staging handoff, with a mapped XML obligation | Broker claim submissions routed to the correct downstream claims rail |
| Canonical entities | `Account` | `AuthorizationRecord` | *(none — router carries messages, not entities)* |
| Upstream | REST/OpenAPI account API | REST/OpenAPI authorization API | REST/OpenAPI claim-intake API |
| Downstream | `ACCOUNT_STG` staging handoff + `ACCT_EOD` fixed-width file | `AUTHORIZATION_STG` staging handoff + `authorization-schema.xsd` XML output | 3 downstream REST claims rails, rule-routed |
| Archetype | `crud` | `crud` | `passthrough-router` |
| Target profile | `springboot-standard-enterprise` | `springboot-legacy-compatible` | `springboot-legacy-compatible` |
| Contract families | REST/OpenAPI · fixed-width file · staging DDL | REST/OpenAPI · XML/XSD · staging DDL | REST/OpenAPI ×4 |
| Rules | 1 allowed-values rule on `status` | 1 allowed-values rule on `status` | 3 routing rules (one per rail) |
| Staging handoff | Yes | Yes | No |
| Evidence Trail | Decisions recorded for every accepted field/rule | Same | Same |
| **Deliberately NOT shown** | XML, SOAP, Kafka, passthrough, regeneration | Fixed-width, SOAP, Kafka, passthrough, regeneration | Entities, staging, files, XML, SOAP, Kafka |

### 3.1 Why this coverage, and why not more

**Kafka is excluded.** The `kafka-integration` archetype is generated by a wholly separate path
(`_generate_kafka_application`) with its own POM builder and no entity/mapping/staging model. A Kafka
pack would share almost nothing with the other two and would double the maintenance surface to
demonstrate a fourth thing. It is also the archetype most disturbed by Security Slice 1 (the actuator
exposure default changes). **Deferred to a demand-driven follow-up**, not to S8.

**SOAP/WSDL is excluded.** The website shows a SOAP edge in all three lenses, but the readiness matrix
records SOAP at **MVP scope**. A sample pack is an adopter's first impression; leading with the
narrowest-scoped family invites expectations the family does not yet meet. REST/OpenAPI, file, XML and
staging are the families with runtime proof today.

**One pack per archetype-shape, not per family.** FS-ACCT and HC-AUTH are both CRUD but differ in the
axis that matters — file obligation vs XML obligation, enterprise PostgreSQL profile vs legacy H2
profile. INS-CLAIM covers the router shape, which has no entities at all and therefore exercises a
genuinely different Studio authoring path.

**Profile coverage is intentionally 2 of 3.** `springboot-enterprise-postgres-java17` is already covered
by existing Engine examples; adding a third pack solely to cover it would violate the
"smallest maintainable system" objective for zero adopter value.

## 4. Synthetic-data contract

Binding on every committed artifact in every pack. Violation is a review-blocking defect, not a nit.

1. **Synthetic only.** No real customer, patient, policyholder, member, provider, or broker data.
2. **No real identifiers.** Account/claim/authorization numbers, member IDs, policy IDs, IBANs, NPIs, tax
   IDs and similar are fabricated and obviously so — the website's own `ACCT-0001` / `MBR-4471` /
   `CLM-0001` / `POL-9204` shape is the reference style.
3. **No real endpoints or domains.** Hosts use `example.com` / `example.org` only. No internal hostnames,
   no reachable URLs.
4. **No credentials of any kind**, including placeholders that resemble real tokens. Secrets are declared
   as env-var *names* only.
5. **No third-party product, vendor, or company branding**, and no customer names.
6. **No copied production schemas.** Every OpenAPI/XSD/DDL/layout is authored for the pack. A schema that
   looks like a real institution's is a defect even if the data in it is fake.
7. **No regulatory-compliance claims.** No statement that a pack is HIPAA/PCI/SOX/GDPR compliant, aligned,
   or ready. Domain vocabulary is illustrative only — the website already says exactly this
   (*"Illustrative healthcare vocabulary — the same generic contract families and archetypes apply in
   every domain"*).
8. **Deterministic values.** No timestamps-at-authoring-time, no random IDs, no environment-derived
   content in committed source. Dates are fixed literals.
9. **Small.** Each contract artifact stays reviewable in a diff — target ≤200 lines per file, ≤10 sample
   rows per data file. A sample pack nobody can review is not evidence.

**Enforcement:** the existing `gitleaks` secret-scan gate covers rule 4 mechanically. Rules 1–3 and 5–7
are **review-enforced**, consistent with how G5 semantic neutrality is handled — this design claims no
scanner that does not exist.

## 5. Canonical source and repository ownership

### 5.1 The decision

**Studio project JSON is the single canonical source. Engine holds no committed derivative.**

Three models were considered:

| Model | Verdict |
|---|---|
| Studio canonical, Engine package generated during proof | **SELECTED** |
| Studio canonical + committed Engine derivative behind a parity guard | Rejected — see below |
| Engine manifest canonical, Studio project derived | Rejected — Studio cannot import an exported package (V2-S explicitly does not claim exported-package import), so this direction has no supported mechanism |

**Why not the parity-guard model.** It is the more conventional choice and deserves the argument.
Committing an Engine derivative would let Engine CI validate/generate/compile the packs without Studio
present. But the guard has to prove the derivative still matches what Studio *would* export — and the
only honest way to do that is to run Studio, which reintroduces the cross-repo dependency the guard was
meant to remove. A guard that cannot run Studio can only check the derivative is self-consistent, which
is exactly the **evidence-source failure** §4 of the security backlog names as a standing anti-pattern:
the check would draw its evidence from the artifact it exists to constrain. Committing nothing is
strictly more honest than committing a derivative whose freshness is unprovable in CI.

**What this costs, stated plainly.** Engine CI cannot exercise these packs. That is accepted: Engine
already has seven manifest-first examples under `examples/input-projects/` and a domain-neutral CI
fixture (`generated-app-ci-smoke`) that *is* CI-exercised. S1's job is adopter-facing credibility, not
additional CI coverage — and duplicating CI coverage is what would create the second verification
framework §9 forbids.

**What de-risks it.** Studio auto-migrates project files across schema versions on open
(`project_file_service.py:330`, chain at `:341-408`), so a committed `1.4` project keeps opening after
Studio moves to `1.5`+ without an S1 edit. Unsupported versions fail closed with a clear error
(`:320-328`) rather than corrupting state. This is the mechanism that makes a committed project file a
maintainable asset rather than a permanent migration debt.

### 5.2 Ownership by artifact class

| Artifact | Repo | Committed? | Owner |
|---|---|---|---|
| Studio project JSON (`.edgeforge-project.json`) | **Studio** | ✅ | Studio — **the only artifact Studio reads** |
| OpenAPI / XSD / layout / DDL contracts under `contracts/` | **Studio** | ✅ **as derived review copies** | Studio — extracted from the JSON, byte-compared in CI (§5.4). Never read by Studio at runtime |
| Sample data rows under `samples/` | **Studio** | ✅ **as derived review copies** | Same |
| Per-pack `README.md` | **Studio** | ✅ | Studio |
| `expected-proof.json` (static expectations only — **no SHAs**) | **Studio** | ✅ | Studio |
| Exported Engine manifest package | — | ❌ **never** | produced to a temp dir during proof |
| Generated Spring Boot application | — | ❌ **never** | temp proof root only |
| Engine acceptance script | **Engine** | ✅ | Engine |
| Pinned final evidence record | **Engine** | ✅ | Engine (`docs/test-results/`) |
| Design home (this document) | **Engine** | ✅ | Engine (`docs/`) — the suite-level design narrative lives in Engine |
| Adopter-facing pack index / catalogue | **Studio** | ✅ | Studio (`docs/sample-packs/README.md`) — beside the packs, so a Studio user finds it without cross-repo navigation (§5.3) |

### 5.3 Proposed directories

**Studio** — new:
```
docs/sample-packs/
  README.md                      ← index: the 3 packs, what each shows, how to open one
  fs-account-servicing/
  hc-authorization-status/
  ins-claims-intake-router/
```

**Engine** — new:
```
scripts/smoke/domain_sample_packs.py     ← acceptance driver (§10.1)
docs/test-results/
  domain-sample-packs-<YYYY-MM-DD>.md    ← pinned final evidence (closeout slice only)
```

Engine's `docs/domain-sample-packs-design.md` (this file) is the design home; the adopter-facing pack
index lives in **Studio**, beside the packs, so a Studio user finds it without cross-repo navigation.

### 5.4 Why `contracts/` and `samples/` are derived, not canonical

**The problem this resolves.** Studio's package writer builds the exported package from content
**embedded in the project JSON** — `iface.spec_content`, `iface.xsd_content`, `iface.wsdl_content`,
`iface.sample_content`, `op.request_sample_content` (`package_writer.py:281-305,318-326,376-378`). It never opens a
sibling file. So committing a hand-maintained `contracts/account-api-spec.json` **beside** the project
JSON would create a second source that Studio silently ignores: edit the sibling file, export, and the
export still carries the stale embedded copy. That is a second canonical source in all but name, and it
contradicts D1.

**The resolution.** `contracts/**` and `samples/**` are committed **only as derived review copies**, and
the project JSON remains the sole authority:

- A Studio dev helper extracts every embedded content field to its committed pack path, following the
  fixed per-pack map in §6 — one committed file per JSON field, nothing computed.
- A Studio-CI test re-runs that extraction into a temp dir and **byte-compares** it against the committed
  copies. Mismatch fails CI.
- Every pack `README.md` states that `contracts/`/`samples/` are generated and that edits belong in the
  project JSON. **Comment-capable formats** carry the same notice as a file-header comment — under the §6
  map that is the `.sql` staging DDLs and the `.xsd` schema. **JSON cannot carry a comment and stays
  valid**, so the authored OpenAPI documents and the `samples/*.json` payloads carry **no in-file
  header**; the README notice is the only marker for those files, which is sufficient since every one of
  them lives inside a pack whose README already states the rule.

**Why this guard is legitimate where the Engine parity guard was not (§5.1).** The rejected Engine guard
would have had to prove a committed manifest still matched *what Studio would export* — provable only by
running Studio's export pipeline, which is why it collapsed into an evidence-source failure. This guard
proves only that a committed file equals a **JSON field in the same repository**. The extraction is a
dictionary read, needs no Studio runtime, no Engine, and no cross-repo checkout, and it runs in Studio CI
where the source of truth actually lives. Different problem, different cost, different verdict.

**Why not commit the JSON alone.** An OpenAPI document embedded as an escaped JSON string is unreviewable
in a pull-request diff, and these packs exist to be read by adopters and reviewers. Losing diff
reviewability to avoid a guard that costs one test is the wrong trade.

## 6. Pack directory schema

Identical shape for all three; the committed file set differs only where the pack's own content differs.
Every path is **package-relative**; no absolute path, no `../`, no adjacent-repo reference appears in any
committed file.

```
docs/sample-packs/<pack-id>/
  README.md                            # story, what it shows/does not, open steps
  expected-proof.json                  # static expectations, no SHAs (§9)
  project/
    <pack-id>.edgeforge-project.json   # CANONICAL — the only artifact Studio reads
  contracts/                           # DERIVED review copies (§5.4) — byte-compared in CI
  samples/                             # DERIVED review copies — CRUD packs only
```

**The committed review copies are exactly the embedded-content fields — one file per field**, so the
extraction that A9b byte-compares stays the dictionary read §5.4 argues for. Each pack's map is fixed:

| Pack | Committed review copy | Extracted from |
|---|---|---|
| FS-ACCT | `contracts/account-api-spec.json` | `upstream_interfaces[0].spec_content` |
| FS-ACCT | `contracts/account-staging-table.sql` | `data_handoffs[0].ddl_content` |
| FS-ACCT | `samples/sample-createaccount-request.json` | `upstream_interfaces[0].operations[0].request_sample_content` |
| FS-ACCT | `samples/sample-createaccount-response.json` | `upstream_interfaces[0].operations[0].response_sample_content` |
| HC-AUTH | `contracts/authorization-api-spec.json` | `upstream_interfaces[0].spec_content` |
| HC-AUTH | `contracts/authorization-schema.xsd` | `downstream_interfaces[0].xsd_content` |
| HC-AUTH | `contracts/authorization-staging-table.sql` | `data_handoffs[0].ddl_content` |
| HC-AUTH | `samples/sample-createauthorization-request.json` | `upstream_interfaces[0].operations[0].request_sample_content` |
| HC-AUTH | `samples/sample-createauthorization-response.json` | `upstream_interfaces[0].operations[0].response_sample_content` |
| INS-CLAIM | `contracts/claim-intake-api-spec.json` | `upstream_interfaces[0].spec_content` |
| INS-CLAIM | `contracts/auto-claims-api-spec.json` | `downstream_interfaces[0].spec_content` |
| INS-CLAIM | `contracts/property-claims-api-spec.json` | `downstream_interfaces[1].spec_content` |
| INS-CLAIM | `contracts/specialty-claims-api-spec.json` | `downstream_interfaces[2].spec_content` |

**Three consequences, all of them writer behaviour rather than preference:**

- **`samples/` exists only for the two CRUD packs.** The passthrough lane never reaches the
  operation-sample block (§9.1), so a committed INS-CLAIM sample would be a file the export ignores —
  exactly the silent-second-source failure §5.4 exists to prevent. INS-CLAIM's synthetic identifiers live
  in its OpenAPI `example` payloads instead.
- **Every authored OpenAPI document in every pack is JSON.** The CRUD export path names an uploaded spec
  `contracts/<slug>-spec.json` unconditionally (`package_writer.py:284`), so YAML content would ship
  under a `.json` name. Engine already reads JSON specifications: its
  [`fetch_openapi_spec` parser](../appbuilder/ingestion/openapi_fetcher.py)
  tries JSON before YAML, while local specification loading uses the
  [translation loader](../appbuilder/metadata/translation.py), whose YAML parser
  also accepts JSON. This Engine-reading capability is separate from the
  Studio writer's filename behavior; the YAML Workspace/Item example is not
  evidence of JSON input.
- **A committed review copy is not always what the export writes.** For FS-ACCT and HC-AUTH the writer
  copies these fields verbatim, so committed copy and exported file are byte-identical. For INS-CLAIM the
  writer *filters* each spec to its selected operation and re-dumps it as YAML, so the exported
  `upstream/claim-intake-api-spec.yaml` and the three `downstream/*-openapi.yaml` are derivatives of the
  committed JSON, not copies of it. A9b compares the committed copy against the project JSON — never
  against the export — so this distinction costs the guard nothing.

**Layout, mapping, rule and report artifacts are deliberately not committed.** The writer *generates*
them from structured fields (`layout_fields`, `field_mappings`, `entity_rules`) rather than copying an
embedded string, so there is no field to extract and no dictionary read to compare. They are reviewable
as structured data inside the project JSON, and they appear in the exported tree, which A6 asserts
exactly (§9.1).

Downstream layout uses the shipped YAML shape (`name:` + `fields: [{name,start,length}]`,
per `examples/input-projects/xyz-accounts-modernization/downstream/eod-handoff-layout.yaml`), not a
bespoke `.layout` format.

**Not present, by design:** no exported manifest package, no `app-definition.yaml`, no generated Java, no
`pom.xml`, no `target/`. If any appears in a pack directory, the pack is malformed.

### 6.1 FS-ACCT — Account Servicing (`crud`, `springboot-standard-enterprise`, Java 21 / PostgreSQL)

**Identity — load-bearing.** §9.1's exported tree is derived from these names: bounded context
`account-servicing` (which becomes the exported package directory) · entity `Account` · upstream
interface `account-api` · downstream interface `account-eod` · data handoff `account-staging-table` ·
upstream operation `createAccount`, whose sample paths are assigned by Studio's authoring route, not the
writer (§9.1).

**Entity `Account`** — `accountId` (STRING, id, required, max 12, client-supplied) · `customerId`
(STRING, required, max 12) · `status` (STRING, required, allowed `OPEN`/`CLOSED`/`FROZEN`) · `balance`
(DECIMAL, required) · `currencyCode` (STRING, max 3, format `iso-4217`) · `openedAt` (DATE, required).

**Upstream OpenAPI** (authored as JSON, §6) — `getAccount` `GET /accounts/{accountId}` ·
`createAccount` `POST /accounts` · `listAccounts` `GET /accounts?status=`.

**Committed samples** — `createAccount` request and response only, at the paths Studio's
operation-selection route assigns (`upstream/sample-createaccount-{request,response}.json`, §9.1).
**Every field in the response sample carries an explicit response mapping**, because an unmapped sample
field is auto-included in the canonical model and warns (§7.2).

**Downstream fixed-width** `account-eod-layout.yaml` — `account_id` start 1 len 12 · `customer_id` start
13 len 12 · `status` start 25 len 10 · `balance` start 35 len 15 · `opened_at` start 50 len 8.

**Staging** — exported as `data-handoffs/account-staging-table.sql`:

```sql
CREATE TABLE account_staging (
    staging_row_id  VARCHAR(36)   NOT NULL PRIMARY KEY,
    run_id          VARCHAR(64)   NOT NULL,
    business_date   DATE          NOT NULL,
    staging_status  VARCHAR(16)   NOT NULL,
    created_at      TIMESTAMP     NOT NULL,
    account_id      VARCHAR(36)   NOT NULL,
    customer_id     VARCHAR(36)   NOT NULL,
    balance         DECIMAL(15,2) NOT NULL
);
```

`account_id`/`customer_id` are `VARCHAR(36)`, not the entity's `max 12`: a staging column mapped from a
canonical `*Id` field warns at anything narrower (§7.2). The canonical constraint is unaffected — the
translator deliberately refuses to let a staging width narrow a `*Id` field.

**Rule:** one allowed-values rule on `status`. **Sample IDs:** `ACCT-0001`…`ACCT-0005`, `CUST-0001`…

### 6.2 HC-AUTH — Authorization Status (`crud`, `springboot-legacy-compatible`, Java 17 / H2)

**Identity — load-bearing.** Bounded context `authorization-status` · canonical entity
`AuthorizationRecord` · upstream interface `authorization-api` · downstream XML interface
`authorization` (which is why the exported XSD is `downstream/authorization-schema.xsd`, §9.1) · data
handoff `authorization-staging-table`. The external OpenAPI schema and XML root remain `Authorization`;
the canonical alias avoids generating the H2-reserved table name `authorization`.

**Entity `AuthorizationRecord`** — `authorizationId` (STRING, id, required, max 12, client-supplied) ·
`memberId` (STRING, required, max 12) · `status` (STRING, required, allowed
`APPROVED`/`PENDED`/`DENIED`) · `serviceUnits` (DECIMAL, required) · `submittedAt` (DATE, required).

**Upstream OpenAPI** (authored as JSON, §6) — `getAuthorization`
`GET /authorizations/{authorizationId}` · `createAuthorization` `POST /authorizations` ·
`listAuthorizations` `GET /authorizations?status=`.

**Committed samples** — `createAuthorization` request and response only, at the paths Studio's
operation-selection route assigns (`upstream/sample-createauthorization-{request,response}.json`, §9.1),
with every response-sample field explicitly mapped (§7.2).

**Downstream XML** — exported as `downstream/authorization-schema.xsd`;
`targetNamespace="urn:edgeforge:samples:authorization:v1"`,
`elementFormDefault="qualified"`, following the proven fixture convention
(`tests/fixtures/edgecontracts/xml-xsd/order-with-attributes/contracts/order.xsd`). Root element
`Authorization` (type `tns:AuthorizationType`), sequence of `authorizationId` (`xs:string`), `status`
(`xs:string`), `serviceUnits` (`xs:decimal`). Mapped field-by-field from the entity; no nesting, no choice
groups, no substitution, no `xs:include`.

**Staging** — exported as `data-handoffs/authorization-staging-table.sql`:

```sql
CREATE TABLE authorization_staging (
    staging_row_id   VARCHAR(36)   NOT NULL PRIMARY KEY,
    run_id           VARCHAR(64)   NOT NULL,
    business_date    DATE          NOT NULL,
    staging_status   VARCHAR(16)   NOT NULL,
    created_at       TIMESTAMP     NOT NULL,
    authorization_id VARCHAR(36)   NOT NULL,
    member_id        VARCHAR(36)   NOT NULL,
    service_units    DECIMAL(13,2) NOT NULL
);
```

Same `VARCHAR(36)` reason as §6.1.

**Rule:** one allowed-values rule on `status`. **Sample IDs:** `AUTH-0001`…`AUTH-0005`, `MBR-0001`…

### 6.3 INS-CLAIM — Claims Intake Router (`passthrough-router`, `springboot-legacy-compatible`)

**Identity — load-bearing.** Bounded context `claims-intake-router` · upstream interface
`claim-intake-api` · downstream interfaces `auto-claims-api`, `property-claims-api`,
`specialty-claims-api`. The routing-rules filename is derived from the **bounded context**, not the
route, so this pack exports `rules/claims-intake-router-passthrough-routing.yaml` (§9.1).

**No entities** — the router carries messages.

**Corrected from rev-2.** rev-2 specified "no default route" as a fail-closed posture. That is not
buildable: Studio only writes the passthrough rules file when `flow.default_target` **and**
`flow.transforms` are both non-empty (`EdgeForgeStudio/app/services/package_writer.py:508-513`), Engine's
`RoutingRule.default_target` is `Field(min_length=1)` (`appbuilder/metadata/models.py:214`), the loader
reads `entry["default_target"]` directly with no fallback (`appbuilder/metadata/translation.py:1861`),
and `_validate_passthrough_configuration` rejects an empty `routing_rules` or an empty `transforms` list
outright (`translation.py:1892-1899`). A default target and at least one transform are **mandatory**, not
optional — confirmed by the two shipped passthrough examples, both of which route an unmatched value to
a designated system rather than rejecting it
(`examples/input-projects/sepa-payment-router/rules/sepa-routing.yaml`:
`default_target: SDD`; `country-router/rules/payment-routing.yaml`: `default_target: APP_C`). INS-CLAIM
now follows the same proven shape.

**Upstream OpenAPI** (authored as JSON, §6; exported as a YAML derivative filtered to `submitClaim`,
§9.1) — `submitClaim` `POST /claims`. Request fields:
`claimId` (string, required, max 12) · `policyId` (string, required, max 12) · `amount` (number,
required) · `lineOfBusiness` (string, required, enum `AUTO`/`PROP`/`SPEC`) · `reportedAt` (string,
`date`, required).

**Three downstream systems**, each a minimal OpenAPI declaring one `POST /claims` operation with an
**identical request shape** (`claimId`, `policyId`, `claimAmount`, `reportedDate`, `lineOfBusiness`) —
required because passthrough routing shares one `OutboundRequestDto` Java type across every target
(`passthrough_emitter.py:70-99`), so all three downstream contracts must accept the same transformed
shape:

| Interface name | System code | Operation ID | Path |
|---|---|---|---|
| `auto-claims-api` | `AUTO_CLAIMS` | `submitAutoClaim` | `POST /claims` |
| `property-claims-api` | `PROP_CLAIMS` | `submitPropertyClaim` | `POST /claims` |
| `specialty-claims-api` | `SPEC_CLAIMS` | `submitSpecialtyClaim` | `POST /claims` |

**Routing rules** (exported as `rules/claims-intake-router-passthrough-routing.yaml`) —
`route_field: lineOfBusiness`; `AUTO` → `AUTO_CLAIMS`, `PROP` →
`PROP_CLAIMS`; **`default_target: SPEC_CLAIMS`**. An unmatched or unusual line of business routes to the
specialty desk for manual handling — a realistic claims-intake posture, and the mandatory default the
archetype requires.

**Transforms** (5, covering every upstream field — none invented beyond what routing/DTO construction
needs):

```yaml
transforms:
  - source: claimId
    target: claimId
  - source: policyId
    target: policyId
  - source: amount
    target: claimAmount
  - source: reportedAt
    target: reportedDate
  - source: lineOfBusiness
    target: lineOfBusiness
    default: "UNSPECIFIED"
```

The last entry demonstrates the `default` mechanism (`passthrough_emitter.py:200-203`), mirroring
`country-router`'s `senderName → originatorName default: "UNKNOWN"` and SEPA's `remittanceInfo →
paymentReference default: "UNSTRUCTURED"`.

**Sample IDs:** `CLM-0001`…`CLM-0005`, `POL-0001`… — carried in the OpenAPI `example` payloads, because
this pack commits **no** `samples/` files: the passthrough lane never writes operation samples (§6, §9.1).
**Deliberately absent:** entities, staging, files, XML, SOAP, Kafka.

### 6.4 What "synthetic" means concretely here

Every identifier above follows a fixed `PREFIX-NNNN` shape with a small ordinal, so no value can
resemble a real account, member, policy, or claim number. Dates are fixed literals in 2026. Hosts in
every OpenAPI `servers` block are `https://api.example.com`. No value is drawn from a real institution's
format.

## 7. Lifecycle contracts

### 7.1 Studio lifecycle — required proof per pack

1. **Open** the committed project JSON through `deserialize_project` + `restore_session`
   (`project_file_service.py:303,164`) — the same path `POST /project/open`
   (`app/routes/project_file.py:101`) uses.
2. **Round-trip**: `snapshot_session_for_save` → serialize → deserialize → assert the reloaded project
   equals the original on all authored fields.
3. **Render state**: assert the session reports the expected archetype and a readiness state consistent
   with `expected-proof.json`.
4. **Export** through the package writer with **no hand-editing of the exported tree**.
5. **Assert the export tree exactly**: the sorted list of written paths must **equal**
   `expected_exported_artifacts` (§9.1) — not merely contain it — and the exported manifest must declare
   `schema_version: "2.0"`. "Expected artifacts present" is not the bar; an unexpected extra file is a
   failure too, because it means the writer or the pack changed without anyone noticing.
6. **No unexpected warnings** — the export warning list must match `expected-proof.json` exactly
   (empty for all three packs at the grounding SHA). A pack that exports "with a couple of warnings" is
   not export-clean.
7. **KA OFF**: assert `capabilities.knowledge_assist_enabled is False` and that no KS process is spawned.
8. **Path hygiene — scoped to filesystem path fields only.** Assert that no *filesystem path field*
   carries a POSIX home-directory prefix, a Windows drive-letter prefix, or a `..` segment. The fields
   are enumerable and finite: `spec`, `mapping_path`, `xsd_path`, `wsdl_path`, `sample_path`,
   `request_sample_path`, `response_sample_path`, and the staging-DDL path — the same fields
   `package_writer` treats as package-relative (`package_writer.py:222`).
   **Do not scan arbitrary contract content, and do not reject a leading `/`.** Every OpenAPI route in
   these packs legitimately starts with `/` (`/accounts/{accountId}`, `/claims`), so a blanket
   leading-slash rule would reject valid contracts. When implementing, reuse the needle the repo-hygiene
   `absolute-path-guard` ([`.github/workflows/repo-hygiene.yml`](../.github/workflows/repo-hygiene.yml))
   builds rather than writing the literal marker into a committed file — that guard greps the whole
   repository and a literal example in documentation trips it.
9. **The committed project JSON carries no export path.** `snapshot_session_for_save` copies
   `last_export_path` into the saved project (`project_file_service.py:117`), and every export appends a
   `KSManifestRevision` whose `export_path` is a required absolute path (`models/project.py:453-459`,
   `package_writer.py:564-574`). A pack saved *after* an export would therefore commit the author's
   machine path and trip §11's own stop condition. Assert both are absent from the committed JSON: save
   the pack before exporting it, or clear the two fields before committing. (This is about the
   **committed** file only — the exported `studio-project.json` legitimately records the temp proof root,
   which is why §9 lists it as volatile.)

**Browser proof (D7) — not in CI.** Studio **intentionally has no jsdom or Playwright harness**; the
choice is documented in at least four test modules (`tests/test_step3_render_snapshots.py:4-6`,
`test_step7_trace_lens.py:505`, `test_step5_tab_badge_focus.py:9,204`, `test_step2_seed_patch.py:5`),
which verify client behavior by static source inspection instead. An earlier draft of this design
required a browser check in Studio CI; that was **unbuildable without introducing a browser-testing
foundation**, which is far outside S1's scope and would be a Studio architecture decision, not a
sample-pack one.

**Resolution:** all CI-level Studio proof is service/route-level (A1–A8). **One manual browser open of
FS-ACCT is a Slice-3 closeout step** (A9), recorded in the evidence document alongside the pinned SHAs.
It is a human check, performed once, at the post-security baseline. S1 introduces no browser tooling.

### 7.2 Engine lifecycle — required proof per pack

Run against the package Studio just exported into a temp root:

1. **Schema validation** — package rejected if not manifest `2.0`.
2. **Generate — with ZERO generation warnings.** `python -m appbuilder.cli generate --manifest
   <tmp>/app-definition.yaml --output <tmp-out> --validate-schema`, and `GenerationReport.warnings` must
   be empty.

   Two authoring rules make that reachable, and both were found by generating these packs rather than by
   reading the emitter:

   - **Every field present in a committed response sample carries an explicit response mapping.** A
     sample field with no mapping is auto-included in the canonical model and warns
     (`metadata/translation.py:2791-2801`). FS-ACCT and HC-AUTH map all five/six response fields, not
     just the id.
   - **Staging columns mapped from a canonical `*Id` field are `VARCHAR(36)`.** Anything narrower warns
     that it may truncate a 36-char UUID (`metadata/translation.py:2980-3003`), even though these packs
     use client-supplied 12-character ids. The staging DDLs in §6.1/§6.2 are widened accordingly; the
     entity-side `max 12` constraint is unaffected, because staging widths are downstream storage
     constraints and the translator deliberately does not let them narrow a canonical `*Id` field
     (`translation.py:2970-2977`).
3. **Harness — pass with ZERO warnings, on the two CRUD packs.** `appbuilder/harness/runner.py` must
   report `HarnessReport.passed` **and** an empty warning list for FS-ACCT and HC-AUTH.

   **The harness does not run for INS-CLAIM, and A12 does not claim it does.** The compatibility harness
   is invoked only from the CRUD lane (`generation/engine.py:330`); the passthrough lane
   (`_generate_passthrough_application`, `:419`) and the Kafka lane (`:99`) both return
   `harness_report=None` (`:457-462`, `:145-150`), which the CLI prints as `Harness: NOT RUN`
   (`cli.py:252-253`). This was confirmed by generating all three packs: two report
   `passed=True, errors=0, warnings=0`; INS-CLAIM reports no harness at all. The staging run-identity
   argument below is CRUD-and-staging-specific anyway — INS-CLAIM has no staging handoff.

   **Why the stricter bar is required.** `HarnessReport.passed` filters to `severity == ERROR`
   (`harness/models.py:35-40`), and the staging run-identity check is `ERROR` **only when the contract
   opts into M5a `run_semantics`** (`harness/checks.py:236-240`). **Studio cannot author `run_semantics`
   at all** — `grep -rn run_semantics EdgeForgeStudio/app --include='*.py'` returns zero hits — so a
   Studio-authored pack can never opt in, the check is always `WARNING`, and `passed` ignores it. A
   staging pack with no run identity would therefore be recorded green.

   This is live, not theoretical: the shipped `loans-modernization` staging DDL has neither a primary key
   nor a run-ID column and emits exactly this warning today.

   **The fix is in the DDL, not the opt-in.** Both staging DDLs (§6.1, §6.2) declare a primary key and a
   `run_id` column — recognized because `staging_operational_column_role` normalizes to `runid`
   (`generation/utils.py:181-189`) — so the non-opt-in branch (`checks.py:230-234`) finds run identity and
   raises no issue at all. Asserting zero warnings then makes that guarantee load-bearing rather than
   advisory. When Studio later gains `run_semantics` authoring, these packs can opt in and the same check
   becomes `ERROR` with no pack redesign.
4. **Compile/package using the resolved profile.** PostgreSQL runtime profiles use
   `mvn -q clean package -DskipTests` with the profile's declared JDK; this manual slice does not
   provision PostgreSQL. H2 runtime profiles use `mvn -q clean verify`, also with the profile's declared
   JDK. The driver records the exact command and toolchain for every pack.
   Java 21 for `springboot-standard-enterprise`, Java 17 for `springboot-legacy-compatible`.
5. **Independence** — assert no `edgeforge`/`appbuilder`/Studio/KS coordinate in the generated dependency
   tree, reusing `scripts/smoke/generated_app_independence.py`.
6. **No manual edits** — generated source is compiled exactly as emitted.
7. **Temp-root only** — every byte of generated output lands under a temp proof root and is deleted;
   nothing is written into either repository.

### 7.3 Why no runtime E2E

Generation + compile proves the contract-preservation claim S1 exists to demonstrate. Runtime proof
requires a database, container runtime, and per-archetype harness — which is the L4/L5 acceptance
program's job, already built. Adding runtime to S1 would rebuild a slice of L5 under a different name,
which §9 forbids. **The one justified exception is already covered elsewhere:** `generated-app-ci-smoke`
carries runtime-health and container proof in CI, domain-neutrally. S1 does not need to repeat it.

## 8. Security-slice sequencing

Recorded, not reopened. The generated-app security design is frozen and this document does not amend it.

| Rule | Statement |
|---|---|
| S1 | Engine P1-5 Security Slices 1–4 and the reader-first closure are merged: Slice 1 via PR #301 (`58c079f`), Slice 2 via PR #303 (`4aa09ae`), Slice 3 via PR #304 (`85c9902`), reader closure via PR #305 (`c021c59`), and Slice 4 via PR #306 (`9e2e7ac`). |
| S2 | **S1 design and source authoring may run in parallel**, because manifest `2.0` is unchanged by any security slice and pack authoring touches no Engine emitter. |
| S3 | **Final S1 acceptance runs only after Security Slices 1–4 all merge.** |
| S4 | Final evidence **pins exact Studio and Engine SHAs**. |
| S5 | Post-security baseline is what gets proven: generated README wording (Slice 1), Kafka actuator defaults (Slice 1), CRUD pagination bounds (Slice 2), passthrough request validation (Slice 3), universal security headers (Slice 4). |
| S6 | **Stop condition.** If security implementation changes a target-profile or manifest assumption contrary to the frozen design, S1 halts for reconciliation rather than adapting silently. |

**Concrete exposure.** Slice 1 changes generated README wording → affects all three. Slice 2 changes
CRUD pagination → affects FS-ACCT and HC-AUTH. Slice 3 changes passthrough validation and adds a POM
dependency → affects INS-CLAIM. Slice 4 adds headers → affects all three. **Every pack is touched by at
least two slices**, which is precisely why acceptance waits rather than proving a baseline that is about
to move. All four slices and the reader-first closure are in the Engine baseline. The Slice 2 driver
proved the intended post-security output, and Slice 3 pinned that proof and completed the manual browser
check in [`docs/test-results/domain-sample-packs-2026-09-04.md`](test-results/domain-sample-packs-2026-09-04.md).

## 9. Determinism and drift control

**Byte-identical across repeated exports, same Studio SHA + same project JSON — verified, not assumed.**
Each pack was exported twice from the same session at the grounding SHA and compared file by file.
**Exactly two files differ:** `evidence-trail.json` (`manifest_revision_id`, `exported_at`) and
`studio-project.json` (`updated_at`/`saved_at`, the appended `ks_workspace_state.manifest_revisions`
entry, and the absolute `export_path`/`last_export_path` of the temp proof root). **Every other exported
file is byte-identical**, including `app-definition.yaml`, every contract artifact, every mapping
artifact, `completeness-report.md` and `assessment-report.json`.

**Legitimately volatile, normalized before comparison:** the two files named above, plus generation-run
IDs and any absolute temp-root path in a log. The acceptance driver normalizes those fields before
diffing (A16); it does not assert on them. Nothing else needs normalizing — that is the point of naming
them exactly.

**Checked-in derivatives:** `contracts/**` and `samples/**` are checked-in derivatives of the project
JSON (§5.4) — the *Engine* package is what has none, and that remains the simplification: no cross-repo
regeneration-and-compare, because there is nothing on the Engine side to compare against. The
`contracts/`/`samples/` guard is single-repo (extract-and-byte-compare inside Studio CI) and is
maintained as part of Slice 1, not as an ongoing burden — it runs on every Studio CI run, same as any
other test.

**Schema upgrades:** a Studio project-schema bump needs **no S1 change** — the migration chain handles
`1.4` forward automatically (`project_file_service.py:413-431`). A *manifest* schema bump beyond `2.0`
would be a coordinated suite cut (the V2-E/V2-S/V2-X pattern), and S1 packs would be migrated as part of
that cut, not independently.

**Pack version/compatibility metadata — no new manifest or project fields.** `expected-proof.json` is
**pack-local proof metadata**, consumed by **both** the Studio acceptance tests (A1–A8, A9b) and the
Engine acceptance driver (A10–A16). It never enters the manifest, the project schema, or any Engine
contract:

```json
{
  "pack_id": "fs-account-servicing",
  "archetype": "crud",
  "target_profile": "springboot-standard-enterprise",
  "expected_entities": ["Account"],
  "expected_manifest_schema_version": "2.0",
  "expected_export_warnings": [],
  "expected_generation_warnings": [],
  "expected_harness_warnings": [],
  "harness_applies": true,
  "min_studio_project_schema_version": "1.4",
  "expected_export_dir": "account-servicing",
  "expected_exported_artifacts": [
    "app-definition.yaml",
    "assessment-report.json",
    "completeness-report.md",
    "contracts/account-api-spec.json",
    "data-handoffs/account-staging-table-mapping.yaml",
    "data-handoffs/account-staging-table.sql",
    "downstream/account-eod-layout.yaml",
    "downstream/account-eod-mapping.yaml",
    "evidence-trail.json",
    "rules/account-business-rules.yaml",
    "studio-project.json",
    "upstream/account-api-mapping.yaml",
    "upstream/sample-createaccount-request.json",
    "upstream/sample-createaccount-response.json"
  ]
}
```

Two fields carry pack-specific truth rather than a constant: `harness_applies` is `false` for INS-CLAIM,
because the passthrough lane produces no harness report (§7.2), and `expected_export_dir` is the package
directory the writer derives from the bounded context (§9.1). `expected_exported_artifacts` is sorted, and
A6 compares it against the sorted export tree.

**No SHAs live in `expected-proof.json`.** An earlier draft carried a `last_verified` block holding the
Studio and Engine SHAs the pack was last proven against. That is unmaintainable: recording Studio's own
merge SHA inside a Studio file is circular — the SHA does not exist until the commit that would contain
it is created — so the value is stale the moment it lands, and refreshing it needs an extra Studio PR,
turning the claimed three slices into four.

**Verified SHAs live only in the Engine closeout evidence** (`docs/test-results/domain-sample-packs-<date>.md`),
which is written *after* both repositories are at known, already-merged SHAs. That file can state both
pins truthfully because it is authored downstream of both. `expected-proof.json` holds only static,
repo-independent expectations, which never go stale on a merge.

**Staleness** is therefore judged from the evidence document, not from a field inside the pack: a pack
whose most recent evidence record predates the current Engine or Studio baseline is stale. The acceptance
driver reports that as a warning, not a CI failure, because these packs are deliberately outside CI
(§5.1).

### 9.1 The exported tree, per pack — derived from the writer, not sketched

**`expected_exported_artifacts` is an exact allowlist, not a minimum.** A6 (§10.2) asserts the sorted
exported package tree **equals** this list — no extra file, no missing file.

**How these lists were produced.** A `ProjectSession` was built for each pack exactly as §6 specifies.
**Every writer-derived package-path field was left unset** — spec, mapping, XSD, DDL and rule paths all
came from the writer's own defaulting, not from the fixture. Studio's real `write_package_result` was
then executed at the grounding Studio SHA, and the lists below are that output: derived, reproducible
facts about the current writer, not a content sketch — which is what makes "exact" a contract Slice 1 can
satisfy rather than a promise it would have to renegotiate.

**One pair of paths per CRUD pack is the one exception, and it is not the writer's.** The two operation
sample fields — `OperationSample.request_sample_path` / `.response_sample_path` — are the single
package-path pair the writer never defaults: `package_writer.py:300-305` writes a sample only when its
path **and** its content are already populated, with no `default_...path()` fallback if the path is
absent (contrast the spec/mapping/XSD/DDL paths at `:284,309,321-322,347,354,362,376,381,511,517`, which
all do have one). In real Studio use these two fields are assigned earlier, by the operation-selection
authoring route (`app/routes/entities.py:2746-2762`) — **not** by the package writer — as
`upstream/sample-{slug(operationId)}-request.json` / `...-response.json`, where `slug` lowercases and
collapses non-alphanumeric runs to `-` without splitting camelCase (`entities.py:220-221`). That is why
FS-ACCT's files below are `sample-createaccount-*`, not `sample-create-account-*`: `createAccount` has no
non-alphanumeric boundary for the slugger to find. The fixture set these two fields to exactly that
authoring-route convention before calling the writer, so the derivation is faithful to what a Studio
author would actually produce — but it is a documented exception to "every path is unset," not an
instance of it. Every other listed path — spec, mapping, XSD, DDL, rule — came from the writer's own
defaulting with the fixture leaving the field unset, exactly as claimed.

INS-CLAIM has no equivalent exception: the passthrough lane never reaches the operation-sample block at
all (§9.1 below), so it has no sample paths to assign, populated or otherwise.

**Five files are common to every pack** — written unconditionally at the end of every export:
`app-definition.yaml` (`package_writer.py:531`), `completeness-report.md` (`:537`),
`assessment-report.json` (`:552`), `evidence-trail.json` (`:559`), `studio-project.json` (`:576`).

**FS-ACCT — `account-servicing/` (14 files)**

```
app-definition.yaml
assessment-report.json
completeness-report.md
contracts/account-api-spec.json
data-handoffs/account-staging-table-mapping.yaml
data-handoffs/account-staging-table.sql
downstream/account-eod-layout.yaml
downstream/account-eod-mapping.yaml
evidence-trail.json
rules/account-business-rules.yaml
studio-project.json
upstream/account-api-mapping.yaml
upstream/sample-createaccount-request.json
upstream/sample-createaccount-response.json
```

**HC-AUTH — `authorization-status/` (14 files)**

```
app-definition.yaml
assessment-report.json
completeness-report.md
contracts/authorization-api-spec.json
data-handoffs/authorization-staging-table-mapping.yaml
data-handoffs/authorization-staging-table.sql
downstream/authorization-mapping.yaml
downstream/authorization-schema.xsd
evidence-trail.json
rules/authorizationrecord-business-rules.yaml
studio-project.json
upstream/authorization-api-mapping.yaml
upstream/sample-createauthorization-request.json
upstream/sample-createauthorization-response.json
```

**INS-CLAIM — `claims-intake-router/` (10 files)**

```
app-definition.yaml
assessment-report.json
completeness-report.md
downstream/auto-claims-api-openapi.yaml
downstream/property-claims-api-openapi.yaml
downstream/specialty-claims-api-openapi.yaml
evidence-trail.json
rules/claims-intake-router-passthrough-routing.yaml
studio-project.json
upstream/claim-intake-api-spec.yaml
```

**Why the three trees differ in shape** — each difference is a writer branch, not a pack preference:

| Observation | Mechanism |
|---|---|
| CRUD upstream specs land under `contracts/<slug>-spec.json`, not `upstream/` | uploaded spec content is written to `contracts/{slug}-spec.json` (`package_writer.py:284`); the `.json` extension is unconditional, which is why **every authored OpenAPI document in all three packs is JSON** |
| Staging artifacts land under `data-handoffs/`, not `staging/` | `package_writer.py:376,381` |
| CRUD packs export operation samples; **INS-CLAIM exports none** | samples are written at `:300-305`, *after* the passthrough branch at `:262-270` has already `continue`d — the passthrough lane never reaches the sample or upstream-mapping blocks |
| Sample filenames are `upstream/sample-<slug(op)>-request.json` | the path Studio assigns when a sample is captured (`app/routes/entities.py:2759-2760`) |
| HC-AUTH's XSD is `downstream/authorization-schema.xsd`, not `authorization.xsd` | `default_artifact_path` appends `-schema.xsd` (`edge_contracts.py:313-321`) |
| INS-CLAIM's routing rules file is named from the **bounded context**, not the route | `rules/{slug(bounded_context)}-passthrough-routing.yaml` (`package_writer.py:511`); CRUD rule files are named from the entity — `rules/{slug(entity)}-business-rules.yaml` (`:517`) |
| INS-CLAIM's exported specs are **not** copies of the authored content | the passthrough branch filters each spec to the selected operation and re-dumps it as YAML (`:262-270`, `:343-350`) |

**Maintenance rule.** These lists are derived, so they move when their source moves — the package
writer for every path except the two CRUD sample paths, and the operation-selection authoring route
(`entities.py:2746-2762`) for those. A Studio change to the writer's path derivation, its unconditional-
file set, **or that authoring route's sample-path convention** **updates every affected
`expected_exported_artifacts` and this section in the same change** — that is the whole cost of the exact
contract, and it is paid by whoever changes the source, in the PR that changes it. Slice 1 **asserts**
these lists; it does not discover them. If Slice 1's first real export disagrees with any line here, that
is a design defect to reconcile in a design revision — not a list to quietly edit.

## 10. Acceptance matrix and harness ownership

### 10.1 Ownership

| Proof | Owner | Mechanism | CI? |
|---|---|---|---|
| Project open / round-trip / render state | **Studio** | `pytest` beside `tests/test_project_file_service.py` | ✅ Studio CI |
| Export cleanliness, manifest 2.0, KA OFF, path hygiene | **Studio** | `pytest` beside `tests/test_package_writer.py` | ✅ Studio CI |
| Derived `contracts/`+`samples/` match the project JSON | **Studio** | extraction + byte-compare test (§5.4) | ✅ Studio CI |
| One representative browser open | **Studio** | **manual**, once, at closeout — Studio has no browser harness | ❌ manual (Slice 3) |
| Validate / generate / harness / compile / independence | **Engine** | `scripts/smoke/domain_sample_packs.py` | ❌ **manual** — needs a Studio checkout |
| Final pinned cross-repo evidence | **Engine** | one manual run, recorded in `docs/test-results/` | ❌ manual |

**No circular CI dependency.** Studio CI tests only Studio artifacts. Engine CI is untouched by S1 — the
Engine driver is explicitly a manual, developer-invoked script that takes a Studio checkout path as an
argument and **fails with a clear message when not given one**. Engine CI never depends on a developer's
Studio checkout, which is the redline this satisfies.

**Reuses, does not rebuild:** `appbuilder/harness/runner.py`,
`scripts/smoke/generated_app_independence.py`, the `docs/test-results/` evidence convention, and the L0–L5
vocabulary. **Creates no second verification framework and does not absorb M3** — if M3 later wants these
packs as optional scenarios, it registers them; S1 does not build a registry.

### 10.2 Per-pack acceptance checklist

| # | Check | Owner |
|---|---|---|
| A1 | Opens via `deserialize_project` at schema `1.4` | Studio |
| A2 | Save/open round-trip preserves all authored fields | Studio |
| A3 | Reported archetype matches `expected-proof.json` | Studio |
| A4 | Exports with **zero** unexpected warnings | Studio |
| A5 | Exported manifest is `schema_version: "2.0"` | Studio |
| A6 | Sorted exported tree **equals** `expected_exported_artifacts` — no extra file, no missing file (§9.1) | Studio |
| A7 | `knowledge_assist_enabled is False`; no KS spawn | Studio |
| A8 | No absolute/machine-specific path in the enumerated **filesystem path fields**, and none in the committed project JSON's `last_export_path` / `ks_workspace_state.manifest_revisions[].export_path` (§7.1 items 8–9) | Studio |
| A9 | One representative pack opens in a real browser | **Manual, Slice 3** |
| A9b | Derived `contracts/`/`samples/` byte-match extraction from the project JSON | Studio |
| A10 | Engine schema validation passes | Engine |
| A11 | `generate --validate-schema` succeeds **with zero generation warnings** (§7.2) | Engine |
| A12 | Harness reports pass **with zero warnings** — **FS-ACCT and HC-AUTH only**; the passthrough lane emits no harness report at all, so A12 is not applicable to INS-CLAIM (§7.2) | Engine |
| A13 | Profile-selected Maven succeeds on the declared JDK: PostgreSQL uses `mvn -q clean package -DskipTests`; H2 uses `mvn -q clean verify` | Engine |
| A14 | No EdgeForge/Studio/KS coordinate in the dependency tree | Engine |
| A15 | Generated output confined to a temp root; repos unmodified | Engine |
| A16 | Repeated export is byte-identical except `evidence-trail.json` and `studio-project.json`, which are normalized before comparison (§9) | Engine |

## 11. Implementation slices

| # | Slice | Repo | Branch / PR title | Depends on | Changes | Proof | Review |
|---|---|---|---|---|---|---|---|
| **1 — IMPLEMENTED** | Author the three packs + Studio acceptance tests | **Studio** | PR #297 (`a87d1a05`) plus correction PR #298 (`d23d99f`)<br>`[FEATURE] Add synthetic domain sample packs` | This design merged | `docs/sample-packs/**` (3 packs + index), focused tests, extraction helper + byte-compare test (§5.4) | A1–A8 + A9b for all three packs; rev-6 source corrections preserve external HC vocabulary while making Engine generation/build proof reachable. **No browser test** | Independently reviewed and merged |
| **2 — IMPLEMENTED BY PR #307** | Engine acceptance driver | **Engine** | `codex/feature/domain-sample-pack-acceptance`<br>`[FEATURE] Add domain sample-pack acceptance driver` | Slice 1 and Security Slices 1–4 merged | `scripts/smoke/domain_sample_packs.py`, focused unit tests, `examples/input-projects/README.md` pointer | Driver runs A10–A16 against a supplied Studio checkout, reading each pack's `expected-proof.json` for its frozen expectations; exact export-tree/warning contracts, JDK builds, independence, confinement, and narrow determinism checks fail closed. **Engine CI unchanged** | Independent Engine review in PR #307 |
| **3 — IMPLEMENTED BY THIS PR** | Pinned closeout evidence + docs | **Engine** | `codex/docs/domain-sample-packs-evidence`<br>`[DOCS] Record domain sample-pack acceptance evidence` | Slice 2 merged | `docs/test-results/domain-sample-packs-2026-09-04.md` holds **both** pinned SHAs; this design's status is verified | One manual cross-repo run at pinned SHAs passed A1–A16 for all three — A12 on the two CRUD packs only (§7.2) — **including the manual A9 browser open**. No Studio PR needed — no SHA is written back into the packs (§9) | Independent Engine review required before merge |

**Merge order: 1 → 2 → 3, strictly.** Slice 2 cannot be written before the packs exist; Slice 3 cannot run
before the post-security Engine baseline exists (§8 S3).

**Why three, and why it stays three.** Slices 1 and 2 are in different repositories and cannot be one PR.
Slice 3 is separated from Slice 2 by an external dependency — the security slices — that may take weeks;
folding it into Slice 2 would block a finished, reviewable Engine driver behind unrelated work. **No
fourth slice is needed**: because no verified SHA is written back into a pack file (§9), the closeout
requires no follow-up Studio PR.

**Stop conditions (any slice):** security implementation contradicts the frozen design (§8 S6) · a pack
cannot export without hand-editing (invalidates the §5.1 canonical-source decision and requires a design
revision, not a workaround) · a pack requires KA · any **committed** file contains an absolute or
adjacent-repo path · generated output would need committing · scope grows to a fourth pack or the
Kafka/SOAP families.

**Clarification, not a new rule:** the redline above is about what gets *committed*, not about the Engine
driver's own invocation. The driver **requires** a runtime-supplied, validated Studio-checkout argument
(§10.1) to do its job — that argument is a local developer/CI input, never written into any tracked file,
and is exactly the "developer's own Studio checkout" pattern §5.1 already accepts for the same reason
Engine CI stays untouched. A driver invocation such as
`python scripts/smoke/domain_sample_packs.py --studio-checkout /path/to/EdgeForgeStudio` is expected and
correct; a **committed** config file or default pointing at a specific machine's checkout would trip the
stop condition.

**Tracker:** untouched by all three slices. Tracker edits are serialized one-editor-at-a-time
([`docs/tracker/HOWTO-update.md`](tracker/HOWTO-update.md)), and S1 has no reason to take that lane: the
`S1-domain-sample-packs` row is re-statused **after** Slice 3, in whatever tracker-sync PR the maintainer
sequences — not by S1 itself.

## 12. S8 handoff

S8 (adopter onboarding bundle) assembles immediately after S1 and reuses, without re-authoring:

- **Per-pack `README.md`** → the "try a realistic example" section of the bundle.
- **`docs/sample-packs/README.md`** → the pack chooser, already written as adopter-facing prose.
- **The open → export → generate → compile command sequence** (§7.1, §7.2) → the bundle's reproducible
  walkthrough; every command is already pinned and copy-pasteable.
- **`docs/test-results/domain-sample-packs-<date>.md`** → the evidence pointer S8 requires, with the SHAs
  already pinned.
- **`expected-proof.json`** → the fit-checklist input: what each pack does and does not demonstrate is
  already machine-readable.

**S8 does not start now.** No bundle file, no Compose asset, and no quickstart edit belongs in any S1
slice. The handoff is designed so S8 is assembly rather than authoring.

## 13. Risks, non-goals, open decisions

### Risks

| Risk | Mitigation |
|---|---|
| Packs go stale against Engine/Studio drift, outside CI | Evidence-document-dated staleness reporting (§9); packs are small and few by construction |
| Studio project schema bump orphans committed projects | Auto-migration chain verified at `project_file_service.py:413-431`; unsupported versions fail closed, not silently |
| Domain vocabulary reads as a compliance claim | §4 rule 7 forbids it; website's own "illustrative vocabulary" wording is adopted |
| A pack quietly becomes an "everything demo" | §3's per-pack *"deliberately NOT shown"* row is normative, and a stop condition |
| Security slices move the baseline mid-flight | Acceptance deliberately sequenced after all four (§8) |
| A Studio writer change silently invalidates §9.1's exact trees | A6 compares the whole tree, so drift fails Studio CI on the next run rather than degrading quietly; §9.1's maintenance rule puts the update in the same PR that changes the writer |

### Non-goals

No generated-app product/runtime implementation · no new manifest or Studio project fields · no Engine generation features ·
no Studio UX change · no KA requirement · no S2 workbook work · no S3 dossier work · no website change ·
no generated-app security implementation · no runtime production-readiness claim · no committed generated
application · **no tracker status change**.

### Open decisions

**None.** Every choice in §1 is resolved with its rationale recorded. The design remains frozen at
rev-6. Studio Slice 1 and Engine Slice 2 are merged; Slice 3 completed the pinned closeout proof and
manual A9 browser check recorded in
[`docs/test-results/domain-sample-packs-2026-09-04.md`](test-results/domain-sample-packs-2026-09-04.md).
S1 is verified; tracker reconciliation and the S8 handoff remain separately sequenced follow-up work.
