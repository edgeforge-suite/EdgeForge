# Engine M2 Closeout Decisions: 2026-10-20

**Decision packet, not M2 completion or accepted residual risk.** This consolidates
retained technical evidence and names the remaining Engine-owned decisions. The
Python audit correction in this PR is fresh evidence, reported separately in
[Python policy](python-dependency-policy.md). No new Maven/image/runtime campaign
is claimed. Studio and KS are independently owned; no companion edits are needed.

Base: `ca53afb40ac9ba67d74f9d27c2d52e63b909970c` (merged #334). #333 is closed
as superseded. Actual assessed generator remains
`c8798275065a8a0b619046707fad053f8a9b9ad1`; publication repair `5a96193`,
executed reconciliation `e269fb0`, later retention tooling `0015c6a` and reviewed
head `b9b59a4` are different identities, not substitute generators. See the
[dated image record](generated-images/2026-10-20-noble/README.md).

## Subsequent Clean-Plugin Overlay

The [October 24 clean-plugin overlay](clean-plugin-plexus-2026-10-24/README.md)
records the subsequent clean-plugin-owned Plexus Utils 4.0.3 correction and
four new builder artifacts on Java 17/21. The dated October 20 evidence and
identity index below remain unchanged, including their OPEN statuses. This
overlay is not a new 30-case/60-stage campaign, final-image runtime proof,
historical-image clearance, residual-risk acceptance or M2 completion.

## Exact Accounting And Replay

[Machine index](engine-m2-dispositions.json) binds immutable source hashes and
JSON indices/pointers. Every one of 622 current normalized image records and
22,740 observations is assigned; every historical IMG ID and all 3,990 COPY IDs
remain enumerable across 2,186 records / 64,720 observations. Current build and
runtime group record memberships overlap; their observations do not. These are
not unique vulnerability counts. Each COPY resolves to its retained case, stage,
physical path, image config, candidate/status/gap entry; a changed/absent copy is
not automatic remediation of the historical artifact.

The index also maps every one of the **18 dated Maven remediation mappings**
(coordinate/version/advisory identity, not merely advisory ID), **33 vendor
observations**, and **six later applicability rows**. Its source-row hashes and
pointers preserve branches, ranges, scope observations, installed versions and
source evidence without duplicating full advisory bodies. The later five LZ4
conclusions are additive; the earlier six OPEN vendor results are not rewritten.

```bash
python scripts/build_engine_m2_dispositions.py --check
```

This clean-clone check is offline: core hashes, identities, observation joins,
counts and deterministic decision membership only. Rebuild the index without
`--check` after an explicitly authorized source/decision update; review the diff.
The [existing split verifier](generated-images/2026-10-20-noble-storage.md#verification-and-reproduction)
provides additional archive integrity/source reconstruction. Full physical-edge
replay needs private archive member `reconciliation/residual-history-map.json.gz`
(gzip SHA `df436bcf10010d0ef164ed051f4559c599140aac8e40f0a5ac6917febedbfc0b`).
No private archive, source bodies or private originals are required by normal CI.

## Supported Technical Dispositions

| Group | Exact membership and evidence | Outcome and boundary | Owner / trigger / next action |
| --- | --- | --- | --- |
| Dated Maven 18 | Index `maven.historical_mappings`; immutable source `maven-reconciliation.json#/historical_mappings`, all 18 indices and row hashes | Retain `REMEDIATED_VERSION` for the recorded new versions/scopes and packaged bindings. Not a fresh advisory result or historical image closure. | Engine maintainer; dependency, scope or advisory change; refresh only affected proof at release selection. |
| Dated vendor 27 | Index vendor rows retaining `SUPPORTED_VERSION_DISPOSITION`; source branches distinguish NOT_INSTALLED / NOT_AFFECTED_VERSION | Supported, dated technical version/scope conclusions only; no exploitability or all-surface claim. | Engine maintainer; source/range/version/scope change; revisit affected branches. |
| Later LZ4 five | Index `later_vendor_adoptions` with `adopted: true`; adoption ledger binds five IDs, 18 case/stage observations each and packaged JAR hash | Installed `at.yawk.lz4:lz4-java:1.11.4` outside the five positively retrieved affected ranges. Earlier October 5 404 observations remain historical. Not native clearance or an LZ4 upgrade. | Engine maintainer; advisory range, packaged bytes or coordinate change; re-evaluate exact five identities. |
| Jackson | `GHSA-5gvw-p9qm-jgwh`, both vendor and later rows | **OPEN_CONFLICTING_SOURCE**: inclusive Jackson 2 range `>= 2.21.0, <= 2.22.0` conflicts with stated 2.21.5 fix. Test-only 2.21.7 differs from packaged Jackson 3.1.7. Neither test-only scope nor scanner silence accepts it. | Engine maintainer; authoritative corrected range or targeted applicability proof; request source reconciliation, then propose a bounded test-scope disposition. |

## Current Image Decisions

### Current Build OS

Index `CURRENT_BUILD_OS`: all build-stage deb/ubuntu observations (18,060),
including records also observed in final images. **OPEN_MISSING_VENDOR_PROOF**.
Installed Noble package versions and scanner fix/backport claims are retained;
Grype/Trivy differences are not collapsed into universal applicability. Owner:
Engine maintainer. Trigger: relevant Ubuntu USN/backport or selected base change.
Smallest next action: approve a bounded per-source-package Ubuntu applicability
triage, prioritizing runtime-shared packages, before choosing a base refresh.
This record does not select a new base or accept build-only exposure.

### Current Final OS

Index `CURRENT_FINAL_OS`: all final deb/ubuntu observations (4,620).
**OPEN_MISSING_VENDOR_PROOF** for the exact qualified final-image identities.
Owner: Engine maintainer. Trigger: distro advisory/backport or image selection
change. Next: reconcile affected installed versions with Ubuntu package-source
status; separately authorize any base change and affected runtime reassessment.
Do not equate missing fixes, low severity or a healthy non-root startup with
acceptance. These are still the October 20 images, not today's rebuilds.

### Current Clean Plugin Plexus

Index `CURRENT_CLEAN_PLUGIN_PLEXUS`: two normalized scanner identities / 60
observations over 30 builders. `org.codehaus.plexus:plexus-utils:4.0.2` is in the
clean-plugin cache/realm, not the packaged application or Maven distribution.
Grype `GHSA-6fmv-xxpf-w3cw` and Trivy `CVE-2025-67030` retain their separate fix
claims (4.0.3 / 3.6.1). **OPEN_PROPOSED_CORRECTION**: qualify a clean-plugin-owned
4.0.3 correction against its actual effective realm; do not apply a global POM
override, delete caches or infer compiler/distribution remediation covers it.
Owner: Engine maintainer. Trigger: approved plugin slice or changed realm/feed.
Next: separately authorize that narrow graph correction and clean/verify proof.

## Historical Image Decisions

The five groups below preserve historical OPEN statuses. New images with absent
copies or matches do not change the original vulnerable artifact's status.
The index enumerates every member and COPY ID, resolving original observations
through the immutable accounting projection and private lossless map.

### History Build Maven

24 records / 780 observations / 240 copies. **OPEN_MIXED_COPY_EVIDENCE**.
Maven distribution (3.9.16/Plexus 3.6.1), compiler/resources/Boot realms and the
remaining clean realm are distinct. Package/distribution/plugin corrections in
#334 are supported scoped replacement evidence, not clearance for every cache
copy or the historical builder. Engine maintainer owns per-copy reconciliation;
trigger: realm/base/package change. Next: retain the exact-current-copy mappings,
resolve the clean realm separately, and specify any claimed historical closure
per introducing edge rather than a family-wide version claim.

### History Build JDK

61 records / 910 observations / 30 copies. **OPEN_MISSING_APPLICABILITY_PROOF**.
Actual new Temurin inventories are recorded, but missing JDK feed matches do not
establish per-advisory applicability. Engine maintainer; trigger: Temurin advisory
or JDK selection change; next: targeted vendor-version/backport mapping for these
61 IDs, with a separately approved correction if required.

### History Build OS

1,886 records / 56,580 observations / 2,520 copies. **OPEN_REPLACEMENT_NOT_CLOSURE**.
The Noble refresh changes physical contents; retained unmatched and exact-copy
states remain distinct. Engine maintainer; trigger: distro/package/source change;
next: classify each copy through the existing map and current OS triage, without
turning a missing old copy or scanner match into a historical waiver.

### History Final OS

189 records / 5,670 observations / 1,170 copies. **OPEN_REPLACEMENT_NOT_CLOSURE**.
Runtime-base inventories are bound; new OS observations remain open separately.
Engine maintainer; trigger: runtime base or vendor applicability change; next:
same per-copy vendor triage as current final OS, preserving old observations.

### History Final Go Pebble

26 records / 780 observations / 30 copies. **OPEN_UNVERIFIED_APPLICABILITY**.
No final Go-type matches occur in the new ledger; that alone does not resolve
old embedded/native copies. Engine maintainer; trigger: verified physical removal
or authoritative component/advisory applicability; next: use the retained exact
copy/path/image mapping to propose removal/not-installed conclusions only where
supported. Do not invent a Go runtime dependency or silently clear this family.

## Coverage And Owner Decisions

| Decision | Existing control / demonstrated limit | Owner, trigger and smallest next action |
| --- | --- | --- |
| Python closure | Required fail-closed Python job, exact lock coverage, isolated pinned audit tooling and fresh Python evidence; no suppression | Engine maintainer; new advisory/lock change; apply the supported correction in this PR and refresh again before release selection. Reference graph is not all-platform coverage. |
| Per-app SBOM delivery | Existing `assess_generated_maven.py` provides resolved SBOM, inventory coverage, provenance and reports; no new scanner needed. It is explicitly invoked, not automatically attached to every generation or copied into standalone apps. | Engine maintainer; release/handoff; invoke/document the existing command for the selected app. Decide whether future automated attachment is needed; no runtime dependency or new gate is adopted here. |
| Base identity/refresh | `container_policy.py` pins explicit Noble tags plus multi-platform index digests; AMD64 children/configs and actual images are separately recorded | Engine maintainer; before release selection or material security change; review exact selected bases and authorize affected-only refresh. Existing policy is retained, no periodic watcher/SLA. No ARM64 execution claim. |
| Workflow references | Actions checkout@v4, setup-python@v5, setup-java@v4 and upload-artifact@v4 float; PostgreSQL service `postgres:16` also floats. This is separate from pinned generated bases. | Engine maintainer; before release selection; choose reviewed SHA/digest pinning or an explicit justified source-release deferral with owner/review trigger. **Recommendation, pending adoption**: pin third-party Actions and the service identity in a dedicated bounded workflow change; do not claim this PR settled them. |
| Native/embedded/feed limits | Cache/bootstrap unsupported-coordinate records, inferred AspectJ coordinates, JDK classifier limits and native `.so`/runtime-JAR linkage remain recorded. Runtime LZ4 JAR hash was not retained; instrumented images are not production-image proof. | Engine maintainer; selected dependency/native/platform change or acceptance claim; define targeted evidence or a named residual-decision candidate. No blanket exclusion, severity exemption or no-fix acceptance. |
| Public content / source labels | Full Noble advisory bodies archive-only; prior Git/PR refs and older historical advisory prose remain | Engine maintainer; publication; perform content/attribution/history review separately. Hash integrity and recorded source labels are not licence approval or independently verified Git identity. |

## Completion Boundary

This PR restores the Python audit and supplies decision-ready Engine accounting.
It does **not** close image OS findings, Plexus, Jackson, historical/native/feed
gaps, workflow-reference decisions, Studio image disposition or final selected-pair
proof. Any residual acceptance must enumerate identities, artifacts, rationale,
mitigation, accountable owner and review trigger through a separate explicit
maintainer decision. OPEN entries do not block delivery of this bounded packet;
they block claiming M2 or release clearance. No new signing, scheduling, supply
chain service, sibling edits or Suite L5 is authorized or performed here.
