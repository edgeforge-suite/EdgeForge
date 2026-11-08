# Proof-Supplied Kafka Contract Tests

This test source is not emitted by Engine. The Noble-base compatibility proof
adds it only under `src/test/java/proof/` in pristine applications generated from
`tests/fixtures/kafka-integration`, using the PostgreSQL Java 17 and Java 21
profiles. It uses the applications' existing test dependencies without changing
production sources, configuration, POMs, dependency versions or Docker recipes.

The tests exercise real generated consumers, transformers, producers and Kafka
configuration with mocked transport: mapped values/types, topics and keys,
acknowledgement order, invalid messages, send failures, correlation context and
configuration. They do not run a broker, certify business behavior or establish
LZ4/native behavior. The separate ordinary-launch and explicit-native proofs do
that bounded runtime work.

Record this file's SHA-256, the pristine and instrumented inventories, actual
Surefire class/method results, Java/Maven/base identities and unchanged production
bytes. Report these as **proof-supplied tests executed against generated apps**,
not Engine-emitted tests. Consult the dated assessment for executed coverage,
source identities, retained evidence and limitations.
