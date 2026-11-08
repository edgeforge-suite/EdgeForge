# Ordinary Boot Launch: Default LZ4 Proof

EF-V5-M2-ENGINE-IMAGE-PROOF-S1 revision 1. **Functional proof passed on the two
recorded images; no image vulnerability clearance, M2 completion or release acceptance.**

Actual clean generating/proof source:
`fe125b2d6c84aadacb2605f21d7bd146087afbab`. Later collection, publication and
evidence commits are not that tested source. Reference platform `linux/amd64`,
emulated on Darwin/ARM64 with Docker 29.6.1 (daemon architecture `aarch64`).

| Java / profile | Actual image | UID / exit | UTC runtime observations |
| --- | --- | --- | --- |
| 17.0.18 / springboot-legacy-compatible | `sha256:e0f6805efc077d1cd6bdb4d249de1e3a658348474cc6a460b2e0b4f77637ed64` | 999 / 0 | 2026-10-14T22:39:57.926Z to 22:40:22.759Z |
| 21.0.10 / springboot-standard-enterprise | `sha256:eab7ac963cacb94825f49bd285e37e6567db421e6e6d04e06583124f9bd55390` | 999 / 0 | 2026-10-14T22:41:18.457Z to 22:41:39.249Z |

Both use ordinary `java -jar /app/app.jar`, the generated main/entrypoint, no JVM
arguments or forced native/factory override, and Boot's nested classloader.
The labelled proof-only observer is the sole source addition; production source,
configuration, POM and Docker recipe hashes are unchanged. See [receipt.json](receipt.json)
and the per-Java source inventories.

## Observed Behavior And Boundaries

Both report `LZ4Factory:JavaSafe`, `XXHashFactory:JavaUnsafe`,
`LZ4JavaSafeCompressor` and `XXHash32JavaUnsafe`. Native-loaded state is false
after real traffic and after observation. This Java fallback is valid default
behavior, not a failed JNI result. The observer reads Kafka's default level from
`CompressionType.LZ4.defaultLevel()` (9), not a constructor sentinel.

Real Kafka LZ4 input passes through the generated listener/transformer/producer.
The proof checks nonce correlation, exact payload fields and numeric/string
types, broker positions and the fixture's declared null round-robin output key.
Outbound compression is the unchanged generated default, **not claimed as LZ4**.
Numeric equality does not prove decimal lexical formatting. Factory/stream
observations occur after the roundtrip, not inside in-flight producer internals.

Results apply to the exact images above, not every later rebuild from floating
tags, every JDK patch or the separate assessment campaign's image identities.
The [earlier explicit-native proof](../../maven-policy-2026-10-05/README.md)
is separate evidence; its forced-loading result is not default-mode credit.

## Preserved Failed Observations

- [First attempt](prior-failure-01/receipt.json), source
  `743b5d4b0cd991238ce29dd16ac48daf5dc5feab`: observer incorrectly demanded
  inbound-key preservation instead of the declared null round-robin key.
- [Second attempt](prior-failure-02/receipt.json), source
  `64927c87a772ab21f56a9b28e01d836337bc7a79`: observer incorrectly used level -1
  for its comparison stream, selecting a different compressor from Kafka's
  default level 9.

Both remain failed/incomplete, with no Java 21 attempt. Their sanitized logs
retain actual timestamps and the original-byte hashes; no earlier failure was
rewritten as a successful observation or a product/native-loading defect.

## Reproduction And Retention

The [assessment guide](../../generated-image-assessment.md) gives the explicit
clean-source proof command. Publish a new reduced directory with:

```bash
python scripts/publish_default_lz4_evidence.py \
  --proof-directory "$SUCCESSFUL_RAW_PROOF_DIRECTORY" \
  --prior-failure "$FIRST_FAILED_PROOF_DIRECTORY" \
  --prior-failure "$SECOND_FAILED_PROOF_DIRECTORY" \
  --output "$NEW_DEFAULT_PROOF_EVIDENCE_DIRECTORY"
```

[publication.json](publication.json) distinguishes original private-byte hashes
from sanitized uncompressed/gzip hashes. Log timestamps are preserved; gzip
`mtime=0` is compression metadata, not a fabricated scan time. Host Docker
configuration/environment and hostnames are not exported. Originals remain
private and unchanged. The publisher validates receipts, container observations,
source inventories and saved source bytes; it does not build, scan, fetch or
establish security acceptance.
