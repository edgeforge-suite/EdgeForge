# Manifest 2.0 Coordinated Cut — V2-X Result

**Result:** PASS — paired-branch and post-merge checkpoints complete

**Recorded:** 2026-08-16

**Scope:** Engine V2-E + Studio V2-S compatibility, cutover, and provenance proof

This is the durable repository record for the coordinated manifest `2.0` cut. It records the exact
revisions and outcomes already proven in the Engine #290 and Studio #287 review threads; it does not
rerun or reinterpret historical acceptance evidence.

## Pinned revisions

| Checkpoint | Engine | Studio | Pinned pre-cut Engine |
|---|---|---|---|
| Paired branch | `d6a82130a71432c6f299194879e589d56448cfae` | `c088e434ecbdb9f81b21829d57a91845a4334f5f` | `838784a01cb44d116bf18f58bc6af5e62131b1cc` |
| Post-merge | `b2c75ffa65363225a34bfb1fd885b1d2754dbe93` | `882dbf989f4db53d86258a486d3d70564a467709` | `838784a01cb44d116bf18f58bc6af5e62131b1cc` |

The post-merge revisions were the actual repository `main` revisions used by the final proof. The
Engine and Studio merges were 28 seconds apart, and both revisions remained unchanged throughout the
post-merge run.

## Required outcomes

- Post-cut Engine accepted manifest `2.0` and rejected retained `1.0` through package and raw-schema
  paths with version-specific diagnostics.
- The pinned pre-cut Engine rejected ordinary manifest `2.0` through both paths with a
  `schema_version` diagnostic.
- Package and raw-schema validation rejected the same unknown nested field consistently.
- Studio surfaced actionable mismatch diagnostics in both producer/consumer directions.
- Studio project snapshots `1.0` through `1.4` reopened and exported manifest `2.0` packages.
- Actual CRUD, passthrough-router, and Kafka packages exported by merged Studio generated through
  merged Engine with raw-schema validation enabled.
- Manifest-version provenance matched the approved archetype matrix: CRUD emitted headers, README,
  agent context, and baseline; passthrough emitted headers, README, and agent context without a
  baseline; Kafka emitted headers and README without agent context or baseline.
- Existing Flyway migrations and ordinary-regeneration baselines retained their ownership and
  immutability guarantees.
- CRUD, passthrough-router, and Kafka generated applications passed `mvn clean verify` under their
  supported Java targets.

## Executed results

| Check | Paired branch | Post-merge |
|---|---:|---:|
| Engine focused V2-X suite | 286 passed | 286 passed |
| Package/raw unknown-field parity and schema artifact checks | 4 passed | 4 passed |
| Studio paired V2-S suite against pinned Engine | 215 passed | 215 passed |
| Engine full suite | 1,165 passed, 8 skipped | 1,165 passed, 8 skipped |
| Studio broad/full suite | 1,926 passed, 36 skipped, 1 known unrelated failure | 1,926 passed, 36 skipped, 1 known unrelated failure |

Source review records: Engine PR #290 comments `5302880967` and `5305658307`; Studio PR #287
comments `5302880971` and `5305658308`.

## Residuals

- Studio's `harmless-dtd` XSD expectation remains out of sync with Engine #281's intentional DTD
  rejection. It reproduced against the pinned pre-cut Engine and is not caused by the manifest cut;
  it remains a narrow Studio test-alignment follow-up.
- Studio's mismatch assertion necessarily observes Engine diagnostic wording. The current paired and
  merged revisions pass, but future wording changes should preserve the actionable
  `schema_version` signal.

## Conclusion

V2-E, V2-S, paired-branch V2-X, and post-merge V2-X are complete. The coordinated manifest `2.0`
cut is complete, and M5a-S1 is eligible to begin under its separately approved four-slice sequence.
