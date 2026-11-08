# CSV/Delimited and Fixed-Width File Contract Design v1

> **Status:** Design proposal; implementation status current through Engine PR
> `#209`.
>
> **Created:** 2026-05-19.
>
> **Scope:** Deterministic inbound and outbound file-contract support for
> CSV/delimited and fixed-width file formats across the EdgeForge suite:
> manifest model, parser/emitter behavior, control/trailer/reconciliation
> records, field layout, Studio import/review, Evidence Trail metadata, and
> generated-app file I/O.
>
> **Original design PR non-goals:** No Engine implementation, no manifest
> schema JSON implementation, no Studio implementation, no Knowledge Server
> implementation, no TestBench implementation, no generated-app runtime change
> in that PR. Current implementation progress is tracked in Section 17.
>
> **Strategic anchor:** [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md).
>
> **Related docs:**
> - [Edge-Contract Design Docs](README.md)
> - [Downstream Handoff Execution Topology Design](downstream-handoff-execution-topology-design.md)
> - [XML/XSD Contract Support Design](xml-xsd-contract-support-design.md)
> - [Manifest Schema](../manifest-schema.md)
> - [Evidence Trail Design](../evidence-trail-design.md)
> - [Edge-Contract Evidence Trail Metadata Design](edge-contract-evidence-trail-metadata-design.md)
> - [Generated App Quality Gate v1](../generated-app-standards/generated-app-quality-gate-v1.md)

## 1. Purpose

File-based contracts are the most common edge-contract format in traditional
enterprise operations. EOD batch files, reconciliation extracts, GL posting files, MIS
reports, partner feeds, and regulatory extracts are overwhelmingly delivered as
delimited (CSV, pipe-separated, tab-separated) or fixed-width flat files.

EdgeForge already supports **downstream fixed-width file generation** (Engine
PRs `#141`--`#153`), using `type: file-fixed-width` on `downstream_interfaces[]`
with a YAML layout spec and mapping. This design extends file-contract support
to cover:

- **CSV/delimited inbound and outbound** — new contract type
- **Fixed-width inbound** — symmetrical to existing outbound
- **Fixed-width outbound completeness** — control records, trailer records,
  reconciliation files
- **Shared layout and mapping model** across both families

This is the first **implementation-ready** Wave 1b design. The roadmap
sequencing table (Section 8) puts CSV/delimited as Row 4 and fixed-width
completeness/inbound as Rows 2--3 because they are low-risk, high-coverage,
and prove the one-family-at-a-time pipeline end-to-end.

## 2. Problem Statement

Today's gaps:

- **No inbound file parsing.** EdgeForge cannot ingest a fixed-width or CSV
  file and map it to canonical entities. Enterprises receive hundreds of inbound
  batch files daily — reconciliation, reference data, counterparty feeds,
  nostro/vostro extracts.
- **No CSV/delimited support at all.** CSV and pipe-delimited files are the
  most common non-fixed-width format in enterprise operations.
- **No control/trailer records.** Production batch files almost always include
  header/control records (date, run ID, record count) and trailer records
  (checksums, totals, record count). The quality gate flags this gap.
- **No reconciliation file generation.** EOD handoff is incomplete without a
  reconciliation/summary file that downstream systems can validate.

Without these, EdgeForge's file-contract story is outbound-only,
fixed-width-only, and data-records-only — insufficient for any real enterprise
batch interface.

## 3. Existing Foundation

The current implementation provides a solid base to build on.

### Current `file-fixed-width` support

- `downstream_interfaces[]` accepts `type: file-fixed-width`
- Layout spec is a YAML file with a `fields[]` array:
  - `name` — field identifier
  - `length` — fixed character width
  - `required` — boolean
- Mapping spec maps canonical entity fields to layout fields with optional
  `type_coercion` (e.g., `major_to_minor_units` for money)
- Engine generates a `FileWriter` service that serializes entity data to
  fixed-width records
- Generated apps include file-write capability with no EdgeForge runtime
  dependency

### What this design adds

- Inbound parsing for both fixed-width and CSV/delimited
- CSV/delimited type for both directions
- Control, header, trailer, and reconciliation record support
- Richer layout metadata (delimiter, quoting, encoding, date/number formats)
- Shared design patterns across both families

## 4. Design Principles

- **Build on what exists.** Extend the current `file-fixed-width` layout/mapping
  model rather than replacing it.
- **Deterministic parsing.** File parsing uses layout specs, not LLM inference.
- **Author reviewed.** Field layouts, mappings, and record-type classification
  are reviewed in Studio before generation.
- **KA OFF is clean.** Importing a file layout must not call KS, start
  background suggestions, or show KA noise.
- **Additive manifest evolution.** New `type` values on existing arrays. No
  parallel contract arrays.
- **One family, all applicable archetypes.** File contracts apply to CRUD
  (batch ingest/extract), kafka-integration (file-triggered Kafka publish),
  passthrough-router (file transform), and future handoff-app.
- **Fail clearly.** Malformed layouts, missing fields, and type mismatches
  produce deterministic diagnostics.

## 5. Contract Type Values

### Proposed type values

| Type | Format | Directions |
|---|---|---|
| `file-fixed-width` | Fixed-width positional fields | Upstream (new) + downstream (existing) |
| `file-csv` | CSV/delimited with configurable delimiter | Upstream (new) + downstream (new) |

### Type name rationale

- `file-fixed-width` already exists in the codebase. Keep it unchanged.
- `file-csv` covers CSV, pipe-delimited, tab-delimited, and other single-character
  delimiters. The delimiter is configured in the layout spec, not the type name.
  Do not introduce `file-pipe`, `file-tsv`, etc. — delimiter belongs in metadata,
  not type identity. Studio should display this contract type as
  **"CSV / Delimited"** in the contract type selector so users understand that
  pipe-delimited and tab-delimited files are covered by this type.
- Both types belong on `upstream_interfaces[]` and `downstream_interfaces[]`.
  `data_handoffs[]` remains reserved for table-based contracts (staging tables,
  interface tables). Do not place file contracts on `data_handoffs[]`.

### Direction

The roadmap proposes `direction: inbound | outbound` on `data_handoffs[]`.
For `upstream_interfaces[]` and `downstream_interfaces[]`, direction is
implicit:

- `upstream_interfaces[]` — inbound (file is received/parsed)
- `downstream_interfaces[]` — outbound (file is generated/emitted)

No explicit `direction` field is needed on interface entries.

## 6. Proposed Manifest Model

Everything in this section is **proposed and not implemented**. The current
schema remains `schema_version: "1.0"`.

### Upstream File Interface (Inbound)

Example inbound fixed-width:

```yaml
upstream_interfaces:
  - name: nostro-reconciliation-feed
    system: core-enterprise
    type: file-fixed-width
    version: "1.0"
    spec: upstream/nostro-recon-layout.yaml
    mapping: upstream/nostro-recon-to-canonical.yaml
    samples:
      - upstream/sample-nostro-recon.txt
```

Example inbound CSV:

```yaml
upstream_interfaces:
  - name: counterparty-reference-feed
    system: counterparty-system
    type: file-csv
    version: "1.0"
    spec: upstream/counterparty-ref-layout.yaml
    mapping: upstream/counterparty-ref-to-canonical.yaml
    samples:
      - upstream/sample-counterparty-ref.csv
```

### Downstream File Interface (Outbound)

Example outbound fixed-width (extends current model):

```yaml
downstream_interfaces:
  - name: account-eod-file
    system: downstream-etl
    type: file-fixed-width
    version: "1.0"
    spec: downstream/account-eod-layout.yaml
    mapping: downstream/account-eod-mapping.yaml
    samples:
      - downstream/sample-account-eod.txt
```

Example outbound CSV:

```yaml
downstream_interfaces:
  - name: daily-gl-extract
    system: general-ledger
    type: file-csv
    version: "1.0"
    spec: downstream/gl-extract-layout.yaml
    mapping: downstream/gl-extract-mapping.yaml
    samples:
      - downstream/sample-gl-extract.csv
```

### Handoff Topology Pairing

Downstream file interfaces can pair with the handoff topology design:

```yaml
downstream_interfaces:
  - name: eod-recon-file
    system: enterprise-etl
    type: file-csv
    version: "1.0"
    spec: downstream/eod-recon-layout.yaml
    mapping: downstream/eod-recon-mapping.yaml
    handoff_topology:
      mode: staged_external
```

The `handoff_topology` field is proposed by the topology design. File contracts
should use it rather than inventing file-specific topology fields.

### Path Resolution

File contracts use the existing generic `spec` field for layout file paths:

- `spec` is the layout YAML path relative to the manifest package root.
- `mapping` is the field mapping path relative to the manifest package root.
- `samples` is an optional list of sample file paths.
- No new path fields are needed. Unlike XML/XSD (which introduced `xsd_path`
  for XSD-specific artifact handling), file layouts are simple YAML specs that
  fit the existing `spec` convention.

## 7. Layout Spec Model

### Fixed-Width Layout

Extend the current layout YAML to support richer metadata:

```yaml
format: fixed-width
encoding: UTF-8

record_types:
  header:
    indicator:
      position: 1
      length: 1
      value: "H"
    fields:
      - name: file_date
        position: 2
        length: 10
        type: date
        format: "yyyy-MM-dd"
      - name: run_id
        position: 12
        length: 8
        type: string

  data:
    indicator:
      position: 1
      length: 1
      value: "D"
    fields:
      - name: account_number
        length: 12
        type: string
        required: true
      - name: available_balance
        length: 14
        type: decimal
        required: true
        decimal_format: minor_units
      - name: opened_date
        length: 10
        type: date
        format: "yyyy-MM-dd"
        required: true

  trailer:
    indicator:
      position: 1
      length: 1
      value: "T"
    fields:
      - name: record_count
        position: 2
        length: 8
        type: integer
      - name: total_balance
        position: 10
        length: 14
        type: decimal
        decimal_format: minor_units
```

Key additions over the current model:

- `format` top-level field identifies fixed-width vs CSV.
- `encoding` — file character encoding (default UTF-8).
- `record_types` — named record type sections (header, data, trailer) with
  optional record-type indicator fields.
- `position` — explicit 1-based character position. When omitted, fields are
  laid out sequentially: the first field starts at character position 1 (or
  immediately after the record-type indicator when one is defined), and each
  subsequent field starts at the end of the previous field. Explicit and
  implicit positioning must not be mixed within the same record type. Engine
  must reject layouts with overlapping or gapped positions unless a future
  design explicitly allows filler/padding fields.
- `type` — field data type for parsing/validation (string, integer, decimal,
  date, datetime, boolean).
- `format` on date/datetime fields — parse/emit format string.
- `decimal_format` — decimal handling (e.g., `minor_units`, `explicit_decimal`,
  `implied_decimal`).
- `required` — whether the field must be present and non-empty.

**Backward compatibility:** existing `file-fixed-width` layouts that use the
current flat `fields[]` model (no `record_types`, no `format` top-level) must
continue to work. The Engine should treat a flat `fields[]` layout as a
data-record-only layout with no header/trailer.

### CSV/Delimited Layout

```yaml
format: csv
encoding: UTF-8
delimiter: ","
quote_char: "\""
escape_char: "\\"
has_header_row: true
line_separator: "\n"

record_types:
  data:
    fields:
      - name: counterparty_id
        column: 1
        type: string
        required: true
      - name: counterparty_name
        column: 2
        type: string
        required: true
      - name: effective_date
        column: 3
        type: date
        format: "yyyy-MM-dd"
        required: true
      - name: credit_limit
        column: 4
        type: decimal
        required: false
```

CSV-specific metadata:

- `delimiter` — field separator (default `,`). Supports `|`, `\t`, `;`, or
  any single character.
- `quote_char` — quoting character (default `"`). Use `null` or omit for
  no quoting.
- `escape_char` — escape character within quoted fields.
- `has_header_row` — whether the first row is a column header row (not a
  data record).
- `line_separator` — line ending convention.
- `column` — 1-based column index (alternative to sequential field ordering).

### Control/Trailer Records For CSV

CSV files may also have header/trailer records. When present, the layout uses
the same `record_types` structure as fixed-width. The record-type indicator
for CSV can be:

- a dedicated first column value (e.g., `H`, `D`, `T`)
- position-based (first row = header, last row = trailer)

Design recommendation: prefer explicit indicator-column values when the
file format uses them. Position-based detection (first/last row) is fragile
for streaming and should only be used when the file format genuinely has no
indicator.

## 8. Mapping Model

### Inbound Mapping (File to Canonical)

Inbound mappings map file fields to canonical entity fields:

```yaml
entity: NostroReconciliation
direction: inbound
field_mappings:
  - source: account_number
    target: NostroReconciliation.accountNumber
  - source: available_balance
    target: NostroReconciliation.availableBalance
    type_coercion: minor_to_major_units
  - source: opened_date
    target: NostroReconciliation.openedDate
```

Key points:

- `direction: inbound` — file field is `source`, canonical field is `target`.
- `type_coercion` — reuses the existing coercion model (e.g.,
  `minor_to_major_units` is the inverse of `major_to_minor_units`).
- Inbound mapping is the reverse direction of the existing outbound mapping.

### Outbound Mapping (Canonical to File)

Existing model, extended with direction clarity:

```yaml
entity: Account
direction: outbound
field_mappings:
  - source: Account.accountNumber
    target: account_number
  - source: Account.availableBalance
    target: available_balance_minor
    type_coercion: major_to_minor_units
  - source: Account.openedDate
    target: opened_date
```

**Backward compatibility:** existing outbound mappings that omit `direction`
should continue to work. Engine treats omitted direction as `outbound` for
`downstream_interfaces[]` mappings.

### Control/Trailer Mapping

Header and trailer records map to file-level metadata, not entity fields:

```yaml
control_mappings:
  header:
    - source: run_date
      value_source: system_date
    - source: run_id
      value_source: batch_run_id
  trailer:
    - source: record_count
      value_source: data_record_count
    - source: total_balance
      value_source: sum(Account.availableBalance)
      type_coercion: major_to_minor_units
```

Value sources for control/trailer fields:

- `system_date` — current processing date
- `batch_run_id` — batch/job identifier
- `data_record_count` — count of data records written/read
- `sum(<entity>.<field>)` — aggregate of a data field
- `literal:<value>` — hardcoded literal value
- `file_name` — source/target file name

These are **generated-app runtime values**, not manifest-time constants.

### Reconciliation File

A reconciliation file is a separate downstream file interface that summarizes
or cross-checks the primary data file. It gets its own layout, mapping, and
interface entry:

```yaml
downstream_interfaces:
  - name: account-eod-file
    system: downstream-etl
    type: file-fixed-width
    spec: downstream/account-eod-layout.yaml
    mapping: downstream/account-eod-mapping.yaml
  - name: account-eod-recon
    system: downstream-etl
    type: file-csv
    spec: downstream/account-recon-layout.yaml
    mapping: downstream/account-recon-mapping.yaml
```

Reconciliation files are not a special type. They are normal file interfaces
with aggregate/summary mappings.

The relationship between a data file and its reconciliation file should be
machine-readable when it exists. Proposed optional field:

```yaml
downstream_interfaces:
  - name: account-eod-recon
    type: file-csv
    reconciles: account-eod-file
    spec: downstream/account-recon-layout.yaml
    mapping: downstream/account-recon-mapping.yaml
```

`reconciles` is an optional string referencing the `name` of another interface
in the same manifest. When present, Engine and Studio can validate that the
reconciliation file's aggregate fields (record count, totals) are consistent
with the referenced data file's layout. When absent, the reconciliation file
is treated as an independent interface.

If implementing `reconciles` proves premature in the first slice, defer it to
v1.1 with a tracking note — but do not fall back to manifest comments as the
relationship mechanism.

## 9. Inbound File Parsing Behavior

### Parse Flow

```text
Receive file
-> detect/validate encoding
-> identify record types (indicator field or position)
-> parse header record (validate file date, run ID)
-> parse data records (apply layout, validate required fields)
-> parse trailer record (validate record count, totals)
-> map parsed fields to canonical entities
-> persist/forward canonical entities
-> emit parse evidence
```

### Validation

Inbound parsing should validate:

- file encoding matches layout spec
- record-type indicators match expected values
- required fields are present and non-empty
- field lengths match (fixed-width) or column counts match (CSV)
- data types parse correctly (dates, decimals, integers)
- trailer record count matches actual data record count
- trailer totals match computed data field sums where specified
- no unexpected record types

Validation failures should produce deterministic diagnostics with:

- file name
- line number
- record type
- field name
- expected vs actual value
- layout spec path

### Partial File Handling

Design recommendation: inbound file parsing should be all-or-nothing by
default. A file with validation errors should not partially persist records
unless the mapping explicitly configures partial-accept behavior. This is
critical for reconciliation — a partial load can corrupt balances.

## 10. Outbound File Generation Behavior

### Generation Flow

```text
Query/receive canonical entities
-> apply outbound mapping
-> emit header record (system date, run ID, etc.)
-> emit data records (field-by-field serialization)
-> compute and emit trailer record (record count, totals)
-> validate generated file against layout spec
-> write to configured output path
-> emit generation evidence
```

### Existing Fixed-Width Behavior

The current `FileWriter` generation model (PRs `#141`--`#153`) handles
data-record emission. This design extends it with:

- header/control record generation
- trailer record generation with computed aggregates
- reconciliation file generation as a separate interface
- CSV/delimited output support

### Date/Number Formatting

Outbound files must format values according to the layout spec:

- dates use the `format` string from the layout field
- decimals use the `decimal_format` convention (minor units, explicit decimal,
  implied decimal)
- money fields use `BigDecimal` and the coercion model
- booleans use layout-specified representations (e.g., `Y`/`N`, `1`/`0`,
  `true`/`false`)

Do not silently coerce formats. If the layout says `yyyy-MM-dd` and the
canonical field is a `LocalDate`, emit that format exactly. If the canonical
field has no value and the layout field is required, fail before writing.

## 11. Validation Boundaries

### Import-Time Validation

Studio or the importer should validate:

- layout YAML is well formed
- required layout metadata is present (`format`, `fields` or `record_types`)
- field names are unique within each record type
- field lengths are positive (fixed-width)
- delimiter is a single character (CSV)
- date/number format strings are valid
- sample files, when supplied, parse against the layout
- mapping references valid layout field names and canonical entity/field names

### Studio Review-Time Warnings

Studio should surface warnings for:

- unmapped layout fields (file has fields not mapped to canonical)
- unmapped canonical fields (canonical has fields not in the file layout)
- type coercion mismatches (e.g., money field mapped without unit coercion)
- missing control/trailer record definitions for production files
- date format ambiguity across layouts in the same package
- encoding differences between files in the same package

### Engine Generation-Time Validation

Engine should validate before generation:

- `spec` path resolves inside the package
- layout YAML parses correctly
- `mapping` path resolves
- mapping entity/field references match canonical metadata
- type coercions are valid for the source/target types
- archetype supports file I/O for the requested direction
- control/trailer value sources are resolvable at generation time

### Generated-App Runtime Validation

- inbound: validate parsed records against layout before canonical mapping
- outbound: validate serialized output against layout before write
- trailer validation: record count and totals match
- file-level: encoding check, empty-file detection

## 12. Studio Import And Review UX

### Import Flow

```text
Select contract type: Fixed-Width File or CSV/Delimited File
-> choose direction: inbound or outbound
-> upload/select layout spec and optional sample files
-> deterministic parse of layout
-> review field definitions, types, required flags
-> review record types (header, data, trailer) if present
-> review mappings to/from canonical entities
-> save/export manifest
```

### UX Requirements

- user selects contract type before loading/parsing
- direction (inbound/outbound) is clear from the interface array context
  (upstream = inbound, downstream = outbound)
- layout fields show name, type, length/column, required status
- record-type classification is visible and editable
- control/trailer fields show their value source
- mappings show direction and type coercion
- sample file parse results are shown (pass/fail per record)
- KA OFF remains clean:
  - no hidden KS calls
  - no suggestion drawers opened by import
  - no background inference
  - no stale KA state from deterministic import

### Assisted Import From Sample File

When a user provides a sample file without a layout spec, Studio may offer to
**infer** a candidate layout from the sample. This is explicitly an assisted
authoring action, not hidden inference:

- user must confirm the inferred layout before it becomes the spec
- inferred field types are suggestions, not facts
- the generated layout spec is a normal YAML file that the user reviews
- inference from sample must be clearly labeled as "suggested from sample"
- KA OFF must still work — sample-based inference is a Studio deterministic
  heuristic, not a KS/KA call

## 13. KA / KS Future Behavior

Knowledge Assist can later help with file contract review:

- field naming suggestions from sample column headers
- type inference hints from sample data values
- mapping suggestions from canonical entity field names
- identity role hints from file field names
- validation suggestions from field types and domain conventions

Rules:

- file layout parsing is deterministic and does not require KS
- KA suggestions must never silently apply field mappings
- every KA suggestion requires user accept/edit/reject
- KA OFF must not perform live KS calls
- evidence should cite layout spec path, field name, sample file path, and
  line number

## 14. Generated App Implications By Archetype

### CRUD

Primary file-contract archetype:

- inbound file parsing creates/updates canonical entities via batch import
- outbound file generation extracts canonical entities to EOD/batch files
- control/trailer records provide batch integrity
- reconciliation files verify batch completeness
- Spring Batch scaffolding for large-volume file processing

CRUD + file is the most common enterprise batch pattern.

### Passthrough Router

Potential use:

- file format transform (fixed-width to CSV, CSV to fixed-width)
- file validation and forwarding
- file content extraction to Kafka or REST

Passthrough-router file support should be a later slice after CRUD file is
stable.

### Kafka Integration

Potential use:

- file-triggered Kafka publish (parse file, publish records to topic)
- Kafka-consumed records written to outbound file

This bridges batch and real-time patterns. Defer until CRUD file and Kafka
router are both stable.

### Future Handoff App

The `separate_handoff_app` topology mode is purpose-built for heavy file
handoff. File contracts are the primary payload type for this archetype.
Until the handoff-app archetype exists, file contracts use the CRUD archetype
with Spring Batch scaffolding.

## 15. Evidence Trail Behavior

Reuse Evidence Trail v1.1 evidence types:

- `field`
- `mapping`
- `validation`
- `transform`

Do not add new evidence types. Use richer metadata for file sources.

Proposed metadata:

```yaml
evidence:
  - type: field
    entity: Account
    field: accountNumber
    source_artifact: downstream/account-eod-layout.yaml
    artifact_type: file-layout
    layout_field: account_number
    record_type: data
    field_position: 1
    field_length: 12
    file_format: fixed-width

  - type: mapping
    entity: Account
    field: availableBalance
    source_artifact: downstream/account-eod-mapping.yaml
    artifact_type: file-mapping
    layout_field: available_balance_minor
    type_coercion: major_to_minor_units
    direction: outbound
```

Metadata fields:

- `source_artifact` — layout or mapping spec path
- `artifact_type` — `file-layout` or `file-mapping`
- `layout_field` — field name in the layout
- `record_type` — `header`, `data`, or `trailer`
- `field_position` — 1-based character start position (fixed-width)
- `field_length` — field width in characters (fixed-width only)
- `csv_column_index` — 1-based column index (CSV only)
- `file_format` — `fixed-width` or `csv`
- `delimiter` — delimiter character (CSV only; e.g., `,`, `|`, `\t`)
- `padding` — padding character and alignment when applicable (fixed-width)
- `decimal_format` — decimal representation (e.g., `minor_units`,
  `explicit_decimal`, `implied_decimal`)
- `date_format` — date/datetime format string when the field is temporal
- `type_coercion` — coercion applied in the mapping
- `direction` — `inbound` or `outbound`
- `sample_file` — sample file path when evidence was validated against a sample
- `sample_line` — 1-based line number in the sample file for this evidence

## 16. Test And Fixture Expectations

### Engine Unit Tests

Future implementation should include tests for:

- fixed-width data-record parse with simple types
- fixed-width header/data/trailer parse
- CSV parse with comma, pipe, tab delimiters
- CSV with quoting and escaping
- inbound required-field validation
- inbound type validation (date, decimal, integer)
- outbound fixed-width serialization with minor-units coercion
- outbound CSV serialization with delimiter and quoting
- header/trailer generation with computed aggregates
- trailer record-count and total validation
- sample file validation against layout
- encoding detection/validation
- backward compatibility with existing flat `fields[]` layouts
- missing/malformed layout diagnostic

### Golden Generated-Output Fixtures

Golden fixtures should prove:

- generated app includes `FileReader` or equivalent for inbound files
- generated app includes `FileWriter` for outbound files (existing)
- header/trailer records are generated/parsed correctly
- field formatting matches layout spec exactly
- type coercions round-trip correctly
- reconciliation file is generated independently
- generated app builds successfully
- at least one fixture includes both file and REST contracts in one package
  to prove mixed contract types

### TestBench Runtime Proof

TestBench proof is required when file I/O runtime behavior is generated:

- inbound: drop a sample file, verify canonical entities are created
- outbound: trigger generation, verify output file matches layout
- header/trailer: verify control records contain correct metadata
- reconciliation: verify recon file aggregates match data file

## 17. Implementation Slices

This section tracks the original implementation slices and their current status
after Engine PR `#209` and the final integrated edge-contract v1 smoke.

| Slice | Scope | Repo(s) | Current status |
|---|---|---|---|
| 0 | Design doc only | EdgeForge docs | Done |
| 1 | Extended layout spec model (record_types, format, encoding, etc.) | EdgeForge | Done |
| 2 | Additive manifest contract for `file-csv` type | EdgeForge | Done |
| 3 | Fixed-width inbound parser (symmetrical to outbound) | EdgeForge | Done |
| 4 | CSV/delimited parser and emitter | EdgeForge | Done for inbound parser, downstream writer, and generated-app runtime data-record paths |
| 5 | Control/trailer record support (fixed-width and CSV) | EdgeForge | Partial: fixed-width downstream header/data/trailer generation done; fixed-width inbound trailer record-count/sum validation done; CSV inbound indicator-column trailer record-count/sum validation done; broader reconciliation files, header semantic validation, checksums, partial-accept mode, and SFTP/object-store delivery remain future |
| 6 | Studio import/review for file layouts | EdgeForgeStudio | Pending |
| 7 | Inbound mapping model and canonical entity creation | EdgeForge | Done for generated CRUD file ingest with explicit mappings |
| 8 | Evidence Trail metadata | EdgeForge + Studio as needed | Done for v1 file-contract metadata: design added, Studio PR `#190` exports file fixed-width/CSV evidence metadata, and Studio PR `#193` proves the combined evidence package |
| 9 | Golden generated-output fixtures | EdgeForge | Partial: generated-output/runtime coverage exists for file ingest/output and trailer reconciliation; final integrated smoke covers file runtime + evidence metadata, but broader TestBench/productized proof remains future |
| 10 | TestBench runtime proof for file I/O | EdgeForgeTestBench | Pending / partial generated-app proof outside TestBench |
| 11 | KA/KS advisory suggestions for file layout review | EdgeForgeKnowledgeServer + EdgeForgeStudio | Pending |

As of PR `#209`, Engine supports fixed-width inbound parsing, CSV inbound
parsing, CSV downstream writing, fixed-width downstream header/data/trailer
writing, file-only downstream output jobs, file-ingest runtime, explicit
file-to-ID mappings, fixed-width inbound trailer record-count/sum validation,
and CSV inbound indicator-column trailer record-count/sum validation.
Unsupported broader file-control metadata fails generation rather than being
silently ignored.

Recommended sequencing after the v1 runtime/evidence closeout:

1. Build Studio review surface for richer file-layout authoring/review
   (Slice 6) if file-layout editing becomes a near-term UX priority.
2. Add TestBench proof after a reusable file/XML/SOAP runtime fixture strategy
   is explicitly chosen (Slice 10).
3. Add KA/KS advisory suggestions for file layout review last (Slice 11).
4. Keep broader reconciliation files, header semantic validation, checksums,
   partial-accept mode, and SFTP/object-store delivery as v1.1+ work.

## 18. Open Questions

1. Should the layout spec support multiple data record types within a single
   file (e.g., detail + sub-detail records), or should multi-record-type files
   be a v1.1 follow-up?
2. Should fixed-width layouts transition from `length`-only fields to
   `position` + `length`, or keep both modes with position being optional?
3. What is the generated Spring Batch job structure for large-volume inbound
   file processing — single-step reader/processor/writer, or multi-step with
   validation/transform separation?
4. Should inbound file parsing support streaming (line-by-line) for very large
   files, or is batch-load sufficient for v1?
5. How should file encoding detection work when the layout says UTF-8 but the
   actual file is ISO-8859-1?
6. Should the proposed `reconciles` field be implemented in the first file
   contract slice (v1), or deferred to v1.1? If v1, what validation should
   Engine perform on the referenced interface (layout field consistency,
   aggregate type matching)?
7. Should `file-csv` and `file-fixed-width` share a common layout YAML
   structure with format-specific sections, or use completely separate layout
   schemas?
8. What is the generated-app file naming convention for outbound files
   (timestamp-based, run-ID-based, configurable template)?

## 19. Design Verdict

Extend EdgeForge file-contract support to cover CSV/delimited and fixed-width
files in both directions with control/trailer records. Build on the existing
`file-fixed-width` downstream foundation. Keep the layout spec model simple,
YAML-based, and deterministically parseable.

This is the highest-coverage, lowest-risk implementation step after Wave 1a
designs are locked. It proves the one-family-at-a-time implementation pipeline
end-to-end and addresses the most common edge-contract format in traditional
enterprise operations.
