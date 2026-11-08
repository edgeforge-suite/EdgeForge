# Noble Evidence Storage: Retention Revision 2

This is a clean packaging replacement for #333, not a new assessment or a
transfer of its exact-head approval. The [dated assessment](2026-10-20-noble/README.md)
still identifies assessed generator `c8798275065a8a0b619046707fad053f8a9b9ad1`.
Production-generation files match reviewed #333 head
`c512e4754fe2bf1f00e18968566bbb5e1802693d`; later cleanup, CI and independent
review identities are separate in the PR handoff.

## Original And Replacement Records

The original archive `2026-10-20-noble-sanitized.tar` remains unchanged:
98,908,160 bytes, 2,001 files / 95 directories, SHA-256
`771dd6afc1596a35489ba00f233fcb86c44d2286a5de850fa1aa7e022dd61cf1`.
Its original manifest hash remains
`aa72dec214b884e5f796ed2ff196c05a05246d3c75277d40859cb0791cf8e56c`.
Those are original #333 identities, not the replacement descriptor.

The new private archive is **`2026-10-20-noble-retention-r2-sanitized.tar`**.
Its exact byte count, SHA-256, full filesystem tree, core blobs and member counts
are recorded in the [replacement manifest](2026-10-20-noble-core-manifest.json).
Archive bytes: 99,409,920; SHA-256:
`cc26d48d75539646e545d8f70f83026cf929a5d1cfe63838c9e170d48c60683d`.
Replacement manifest SHA-256:
`01d1af012d1701bcd952a6b313a8af29af8628a44c72291738d91b255291a973`.
The revised split is 166 core files / 2,007 full files; 1,841 files archive-only,
with 2,001 indexed gzip records. Counts are derived from actual membership.
Two fresh packaging runs produced byte-identical archives and manifests; the
retained receipt records both. Actual scan and retrieval timestamps are unchanged.

Complete advisory records are **archive-only**, not relocated into another core
file. The public [vendor projection](2026-10-20-noble/residual-vendor-current.json.gz)
retains all six advisory/component identities, scopes, ranges/fixes, source URLs,
attribution/retrieval dates, source-body hashes, installed observations and the
Jackson contradiction. Per-row/body canonical hashes and archive JSON pointers
bind the unchanged full records. The projection is not a lossless replacement.

Archive-only originals include:

- `reconciliation/residual-vendor-current.original.json.gz`: byte-identical reviewed sanitized vendor record, including all full advisory objects.
- `reconciliation/residual-vendor-current.private-original.json.gz`: byte-identical private reconciler output bound by the unchanged adoption ledger's `source_output`; its gzip SHA is `25464a99c2cec1ac2079e67bc9e0cd5a8fa222167fd5663f280e311ebf564ef5`. Values equal the reviewed sanitized vendor record, but serialization differs.
- `reconciliation/publication-replay.original.json.gz`: unchanged reviewed replay receipt, including its sanitized original command.
- `reconciliation/reviewed-publication.original.json.gz`: exact original publication JSON bytes inside deterministic gzip.
- `reconciliation/residual-history-map.json.gz`: unchanged lossless historical/current map. Its gzip SHA remains `df436bcf10010d0ef164ed051f4559c599140aac8e40f0a5ac6917febedbfc0b`.

The top-level replay projection uses portable `python3`. Historical interpreter
version/executable hash were not recorded in that receipt and remain explicitly
`not-recorded`; current tooling observations cannot supply historical provenance.
All other replay fields and original proof/source identities remain unchanged.

The **private-original replay receipt** SHA-256 is
`ec0aeeb86c722d00b9d1f13bda2bb37e11558df08879e7298c2d7ae29a0d64dd`.
Its retained location is archive-only
`reconciliation/reviewed-publication.original.json.gz`, inside the `files` entry
whose `file` is `publication-replay.json.gz`, field `private_original_sha256`.
This was recovered from the checksum-verified retention-r2 archive without
changing its bytes. The public projected entry has null for this field; this
documentation makes the original fingerprint discoverable, not the original
receipt itself available in a clean clone. It differs from reviewed sanitized
gzip hash `26d9346d4b1bc1405ad3d879f737b7d8ace7c0364f7a27566bda8fec35ec2dba`.

## Replay Receipt Difference

The verified private wrapper is `prepare_rev3_reconciliation.py`, retained under
`rev3-private-reporting-helpers/rev3-reconciliation-prep/` in the private evidence
root. SHA-256:
`ded0f52de0040c9a63279ee98b2c34d0d188db683373e756b553fa6d20e7c7c0`.
Before calling the public `reconcile()` function it uses the same Evidence reader
to pre-verify prepared context and the pre-final publication. Consequently the
original receipt records 767 inputs; the public CLI records 747. The twenty
extras are seventeen Kafka packaged inventories, the declaration, qualification
and pre-final publication. One other packaged inventory was already read for a
runtime claim. [Replay context](2026-10-20-noble/reconciliation-replay-context.json.gz)
enumerates their exact root/member/hash identities.

Offline CLI replay reproduced the lossless history map byte-identically and all
vendor values exactly, with complete-findings exit 1. The CLI alone does **not**
reproduce the wrapper's receipt. Full replay also needs the private wrapper and
its original inputs, not merely the composition script or a clean clone.
The original composition script hash remains
`aa1162ed9b7ca732a855b71c7953e418a4070b91ef7a6a08694153d064c123e0`.
The separate retention-revision composition script hash is
`51183e84c8bd473d229a8c0e5953a589a3d2b147d5f558a35579332589845b9c`;
it prepares only derived local data and never executes product/runtime proof.

## Verification And Reproduction

```bash
python scripts/verify_generated_image_evidence_split.py \
  --root . \
  --manifest docs/handover-evidence/generated-images/2026-10-20-noble-core-manifest.json \
  --evidence-dir docs/handover-evidence/generated-images/2026-10-20-noble
# Additional full sanitized archive/source verification, not a new assessment:
python scripts/verify_generated_image_evidence_split.py \
  --root . \
  --manifest docs/handover-evidence/generated-images/2026-10-20-noble-core-manifest.json \
  --evidence-dir docs/handover-evidence/generated-images/2026-10-20-noble \
  --archive "$PRIVATE_RETENTION_R2_ARCHIVE"
```

Repository mode checks **internal consistency**, not independent provenance.
The recorded reviewed-source and original-archive identity labels are only
shape-checked, not independently authenticated or cross-checked against duplicate
labels. The reviewed Git commit/PR supplies that external identity anchor.
A coordinated edit of an unindexed document and its manifest may remain
self-consistent. Archive mode additionally reconstructs vendor/replay projections
from exact unchanged originals and checks their original reviewed index bindings;
these content checks do not authenticate the two labels above. This clarifies
the earlier dated README's "additional assurance" phrase without changing its
historical evidence or introducing a verifier redesign.
Neither mode is security acceptance; exit 2 is incomplete/error, never findings.

The filesystem packager writes sorted PAX members with uid/gid/mtime zero,
files 0644 / directories 0755 and a private 0600 archive. PAX `comment` and legacy
`reviewed_commit` identify the assessed source only, not approval or a full-bundle
Git commit. Existing member/decompression/archive limits, safe extraction and
hash checks remain in force. Default verifier arguments still select October 17.
Replacement packaging/verification tooling is committed at
`0015c6a04d1d85c8393b9bc48260f6addf57c200`; it is not the assessed generator.
The retained layout uses Python 3.11.15 and the existing canonical JSON/gzip
writer. Public projection CLI modes reproduce the factual values; exact layout
serialization and full receipt composition also require the recorded private
composition inputs/script. Do not mistake value equality for byte equality.

1. **Clean clone:** verify the compact core, factual projections, accounting and declared source/archive fingerprints; cannot inspect full source bodies or the lossless map.
2. **Private sanitized archive:** additionally verify every indexed record, exact core equality and source-assisted projection reconstruction. Full structured advisories are present; this does not authorize distribution.
3. **Private originals:** replay reconciliation/publication and final composition using hash-identified wrappers, frozen inputs and recorded tooling. Raw HTTP response bytes are private-original inputs; embedded-object canonical hashes are not their raw-body hashes.
4. **Images:** no universal replay. Fifty-seven exports were removed with receipts; three production exports remain private. Instrumented default/native proof images are distinct, and runtime LZ4 JAR hashes were not retained. New builds/scans require separate authorization and identities.

See the [maintainer tool map](../generated-image-maintainer-tools.md) for tool
purpose, inputs/outputs and separation from ordinary product/contributor work.
Routine CI does not inspect gzip member contents. Decompressed privacy/integrity
checks and archive-depth secret scans are separate scoped proof, with known
synthetic history matches recorded rather than suppressed.

## Public-History Boundary

The replacement starts before `79cdbb6`, the first full-advisory core commit,
and preserves generator/tooling ancestors plus the reviewed later fixes.
**Use a history-preserving merge commit, not squash/rebase**, so recorded source
identities remain reachable. #334 was merged with a merge commit as `ca53afb`;
#333 was closed as superseded. Neither closure nor this status note erases refs.
#333, its branch and GitHub PR refs remain reachable and may become
public; keeping its advisory bodies out of replacement-main ancestry does not
erase earlier uploads. Third-party-content review applies to anything published
in Git, archives or historical refs. No licence determination, public archive
upload, retention SLA, risk acceptance, M2 completion or release clearance is made.
