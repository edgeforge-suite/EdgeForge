# Workspace Items

Independently authored for EdgeForge from these teaching requirements: two
separate entities, explicit bidirectional field mappings, generated identities,
bounded text/numeric inputs, an allowed-value rule and an existence relationship.
This is not a translation, renamed copy or reduced export of an external API.
The contract deliberately declares only two create operations, not an entire API.

Generate from the repository root with `make generate-sample`, or use the CLI
with this manifest and `--validate-schema`. Build/run the resulting standalone
Java 17/H2 app using the quickstart. Create a workspace first, then use its
returned identity in an item request; do not submit the illustrative response IDs
as new persistence identities. The generated app also emits generic CRUD routes.

Local testing must bind to loopback. Production requires the documented
authenticated TLS gateway, explicit method/path exposure approval and blocked
direct port; this example implements neither authentication nor tenant/object
authorization. Its checks are not production certification or Suite acceptance.
