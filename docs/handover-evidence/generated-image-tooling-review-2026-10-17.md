# Generated Image Tooling: October 17 Review Notes

This is a tooling/documentation addendum to the unchanged
[October 17 assessment](generated-images/2026-10-17/README.md), not regenerated
evidence, an advisory refresh, independent approval or release clearance.
The initial independent review examined `814d369c780275eaf8f7f8dd748a6ad7a60d61eb`.
It confirmed the retained 20-plus-10 assembly, counts and startup bindings while
requesting fail-closed CLI handling and a residual publication-path guard.

## Historical Replay Tool Identities

These exact source bytes are identical at tooling revision
`39de47e8128d4d17ed4a7399b717565f3217a041`, evidence revision
`d64181a97d485e7078eb234852bc18dd4ccc4369`, and reviewed revision `814d369`:

| Tool | SHA-256 |
| --- | --- |
| `scripts/assemble_generated_image_campaign.py` | `b1a3c7acbf84e10e3dc0248a729dccd56a1256adbbcc91f56dddd47a4023653e` |
| `scripts/publish_generated_image_evidence.py` | `d11f8068563cba6e8dc01e0b403c005fb7c22f70f38dfe16bf0f571aaa6613e7` |

The composition records the assembler hash. Later CLI/privacy repairs are not
the tool bytes that created it. Current validation permits the one pinned old
assembler identity alongside its own identity, while retaining the fixed
composition kind, original fragment/failure hashes, exact coverage and all
copy/source/time/inventory checks. Unknown tool hashes remain refused.
Use the pinned old revision and original redaction-root configuration for
byte-identical historical replay. It predates the new privacy guard: inspect its
output using the repaired guard before treating any republication as sanitized.
No historical evidence or hash index is rewritten by this addendum.

## Secret-Scan Boundaries

The builder's recorded Gitleaks 8.30.1 archive-depth-2 scan covered only
`docs/handover-evidence/generated-images/2026-10-17`, about 1.11 GB expanded,
and found no matches. It did not include the historical default-LZ4 log archives.

Independent review at `814d369` ran the whole-tree scan with archive depth 3,
about 1.17 GB expanded. It found four `generic-api-key` matches in exactly
`kafka-lz4-default/2026-10-14/runtime-j17.log.gz` and `runtime-j21.log.gz`, all
the already identified synthetic correlation values, not credentials. The normal
whole-tree scan and PR-range history scan passed. These are separate scopes;
neither is a claim that the required CI scan traverses compressed members.

CI's current `gitleaks dir .` and home-path `git grep` do not inspect gzip.
The approved value-and-file-bound exception remains unchanged. If archive
inspection is later added to CI, the two exact log paths need the same
extracted-value-bound `AND` treatment, not a directory exemption or broader rule.
See [Secret and Data Scan](secret-and-data-scan.md) for the required gate.

## Unchanged Proof And Optional Follow-Ups

The reviewer reported two offline default-LZ4 contract-test passes on JDK
17.0.18 and 21.0.12.1, each observing compression level 9. This is attributed
reviewer proof, not a fresh builder run or Kafka/image startup. The opt-in tests
remain skipped in ordinary CI; no workflow is changed in this repair.

The accurate October 14 Jackson wording correction remains labelled within the
October 5 policy record; its raw vendor receipts remain unchanged. A separately
sealed erratum is an optional future documentation decision, not a new evidence
rewrite here. OPEN findings, mutable-base policy, platform limitations and M2
acceptance retain their existing dispositions.
