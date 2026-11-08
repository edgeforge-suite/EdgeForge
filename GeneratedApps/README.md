# Generated App Snapshots

Committed generated-app source snapshots are intentionally not kept in this
repository.

Historical generated outputs (`BuiltApp1`, `BuiltApp2`, `DDAApp`, and
`bankingcore`) were removed from tracked source during the enterprise handover
cleanup so stale generated code does not look like maintained product source.
Representative apps should be regenerated from committed input packages under
`examples/input-projects/` or focused fixtures under `tests/fixtures/`.

The generated-app compile workflow now regenerates a representative app into a
temporary directory and builds that output instead of compiling a committed
snapshot.
