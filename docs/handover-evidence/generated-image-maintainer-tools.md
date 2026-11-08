# Generated Image Evidence: Maintainer Tool Map

## Choose The Right Workflow

**Product use:** author/review a manifest and use Engine's normal generation
commands. Generated applications do not depend on these evidence-maintenance
tools or the private archive at runtime. Start with [quickstart](../quickstart.md).

**Normal contributions:** run the normal Python tests and applicable CI. Private
archives and sibling repositories are not required for ordinary unit tests;
explicit opt-in/runtime gates are not passing proof when skipped. Follow
[CONTRIBUTING](../../CONTRIBUTING.md). Do not launch a release campaign merely
because an evidence or documentation file changed.

**Release-evidence maintenance:** use the following tools only for an explicitly
scoped assessment, retained-evidence replay or packaging change. A new build or
scan has new source/image/database identities; it is not a replay of historical
proof. Collection can execute applications and retrieve public artifacts, so
its authorization is distinct from offline verification.

## Tool Map

Paths below are repository-relative. All outputs go to explicit fresh locations.

| Tool | Purpose And Inputs | Outputs / When Used |
| --- | --- | --- |
| [assess_generated_images.py](../../scripts/assess_generated_images.py) | Qualify pinned tools and assess an explicitly identified saved image; reconcile inventories and extraction. | SBOMs, inventories, findings and identity/coverage receipts. New authorized assessments, not packaging replay. |
| [collect_generated_images.py](../../scripts/collect_generated_images.py) | Consume the declared case map, source freeze, qualified bases and assessment tools. | Generated build/final-image evidence and bounded runtime receipts. Actual campaign execution only. |
| [assemble_generated_image_campaign.py](../../scripts/assemble_generated_image_campaign.py) | Validate retained fragment coverage, identity and copy bindings. | Complete assembled campaign and copy manifest. Offline composition; does not turn partial fragments into original successful runs. |
| [publish_generated_image_evidence.py](../../scripts/publish_generated_image_evidence.py) | Validate a complete retained campaign and declaration, then sanitize indexed records. | Full local sanitized layout and publication index. Offline replay; not an upload or release. Recorded prefixes matter for byte-identical replay. |
| [summarize_generated_image_proofs.py](../../scripts/summarize_generated_image_proofs.py) | Read actual compatibility, default/native and startup receipts with their source/artifact bindings. | Derived proof summary. Summarizes existing execution; does not supply new runtime proof. |
| [prepare_generated_image_residual_manifest.py](../../scripts/prepare_generated_image_residual_manifest.py) | Bind retained historical, current, vendor and proof inputs. | Hash-bound reconciliation input manifest. Offline preparation, not findings disposition. |
| [reconcile_generated_image_residuals.py](../../scripts/reconcile_generated_image_residuals.py) | Consume that manifest and explicit root aliases. | Lossless historical/current/vendor maps and receipt; exit 1 retains complete OPEN findings, exit 2 means incomplete/error. No risk acceptance. |
| [project_generated_image_proof_evidence.py](../../scripts/project_generated_image_proof_evidence.py) | Minimize validated proof, vendor or replay records while binding unchanged originals. | Explicit derived public projections, not lossless source records. Vendor prose remains archive-only; metadata/ranges/identities remain reviewable. |
| [package_generated_image_evidence.py](../../scripts/package_generated_image_evidence.py) | Validate a complete indexed sanitized filesystem and declared source. | Deterministic compact core, manifest and private PAX archive. Packaging only; original inputs are unchanged. |
| [verify_generated_image_evidence_split.py](../../scripts/verify_generated_image_evidence_split.py) | Read a core manifest and optionally its exact private archive. | Exit 0 for the requested consistency/integrity checks; every error exits 2. No network or application execution. |

Repository mode checks **internal consistency**, not independent provenance.
`public_retention.reviewed_source_sha` and `original_archive_sha256` are recorded
labels: the verifier shape-checks them, not their Git identity or agreement with
the duplicate retention record. The reviewed Git commit/PR is the external
identity anchor. Archive mode verifies content hashes, original-publication
binding and source reconstruction; it does not authenticate those two labels.
Coordinated edits of an unindexed document and its manifest can remain
self-consistent. Label cross-checking is a separate small tooling recommendation,
not implemented or required as a verifier redesign in this documentation update.

## Replay Tiers And Scope

The [approved public-import exclusions](../v5-release-readiness.md#public-import-exclusions-and-historical-replay)
leave three full October 5 repository-advisory responses private. Normal public
CI uses synthetic reconciliation tests, not those originals. Full historical
Maven/vendor replay needs the original private policy directory; missing sources
produce an incomplete/error result. The retained factual indexes/checksums and
dispositions are not rewritten, nor is public-clone internal consistency full replay.

See the [current storage contract](generated-images/2026-10-20-noble-storage.md)
for clean-clone, sanitized-archive, private-original and non-replayable-image
boundaries. The original reconciliation wrapper pre-verified twenty additional
inputs; the public CLI alone does not reproduce its 767-member receipt. The
wrapper's name, verified hash and exact input difference are recorded there.
The original replay receipt's private-original fingerprint is retained in the
archive-only reviewed publication index; its exact member, entry and hash are
now explicitly located in that storage contract. It is not the public replay
projection's gzip hash.

The [assessment guide](generated-image-assessment.md) defines coverage and exit
semantics. Neither a consistent core nor a complete findings-bearing scan is
M2 closure, risk acceptance or release clearance. Full third-party content and
old PR references still need publication review; keeping bodies archive-only
does not authorize archive distribution or erase earlier GitHub uploads.

## Known Synthetic History Matches

Gitleaks 8.30.1 history scan over `dac4a9d..b372ac5` returned exactly two
`generic-api-key` matches in preserved tooling commit
`e269fb002cfa3e228f83078b25bfede046199a30`:

- `tests/unit/test_generated_image_proofs.py:159`: a synthetic Kafka correlation fixture.
- `scripts/reconcile_generated_image_residuals.py:1202`: an ordinary validation expression.

Their fingerprints are that full commit ID, file, `generic-api-key`, and line,
joined by colons. Both were corrected without changing values in `b372ac5`;
neither is a credential. No allowlist, history rewrite or suppression is added.
This is distinct from the four previously recorded archive-depth matches in
the October 14 `runtime-j17.log.gz` / `runtime-j21.log.gz` synthetic proof logs.
Future history audits must assess exact scope and identities, not ignore a rule
or assume a passing current-tree scan examined historical/gzip contents.
