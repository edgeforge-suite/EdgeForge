# Edge-Contract Evidence Trail Metadata Design

> **Status:** Design implemented for the v1 file/XML/SOAP evidence export
> scope.
>
> **Created:** 2026-06-08.
>
> **Scope:** Additive Evidence Trail metadata for file, XML/XSD, and SOAP/WSDL
> edge-contract provenance. The design is implemented in Studio export for the
> v1 file/XML/SOAP evidence scope.
>
> **Non-goals:** No Engine runtime dependency, no manifest schema change, no
> generated-app runtime change, no KS/KA change, no TestBench change, and no
> new Evidence Trail evidence type unless a future version proves existing
> types cannot express the contract decision.
>
> **Builds on:**
> - [Evidence Trail Design](../evidence-trail-design.md)
> - [Edge-Contract Expansion Roadmap](../edge-contract-expansion-roadmap.md)
> - [CSV/Delimited and Fixed-Width File Contract Design](csv-fixed-width-file-contract-design.md)
> - [XML/XSD Contract Support Design](xml-xsd-contract-support-design.md)
> - [SOAP/WSDL Contract Support Design](soap-wsdl-contract-support-design.md)
> - [SOAP Canonical Operation Mapping MVP Design](soap-canonical-operation-mapping-mvp-design.md)
> - [Outbound SOAP Canonical Invocation MVP Design](outbound-soap-canonical-invocation-mvp-design.md)

## 1. Purpose

Engine now implements the first production-useful edge-contract family set:

- fixed-width and CSV file ingest/output, including inbound trailer
  record-count and sum reconciliation;
- XML/XSD canonical ingest/output for explicitly mapped CRUD contracts;
- SOAP/WSDL inbound `read_by_id` and outbound `invoke_by_id` canonical runtime
  paths.

At the time this design landed, the next gap was not another runtime adapter
first. The suite needed a consistent Evidence Trail metadata contract so Studio
export could explain where file, XML/XSD, and SOAP/WSDL generated-artifact
decisions came from.

This design defines additive metadata carried on existing Evidence Trail
records. It keeps Engine and generated apps standalone: the evidence sidecar is
for Studio, future governance review, and compliance tooling. It is not a
runtime dependency.

## 1.1 Implementation Status

This design is implemented for the v1 edge-contract evidence scope:

- Engine PR `#210` merged this design.
- Studio PR `#190` exports file fixed-width/CSV Evidence Trail metadata.
- Studio PR `#191` exports XML/XSD Evidence Trail metadata.
- Studio PR `#192` exports SOAP/WSDL Evidence Trail metadata.
- Studio PR `#193` proves the combined file + XML/XSD + SOAP/WSDL
  `evidence-trail.json` package.
- The final integrated v1 smoke confirmed file, XML/XSD, and SOAP/WSDL
  metadata are present, use package-relative paths, contain no absolute local
  filesystem paths, and preserve Evidence Trail v1.1 shape.

No new evidence types were added. In particular, the final proof contains no
`file_contract`, `xml_xsd`, `soap_wsdl`, or `identity_role` evidence types.
Identity roles remain excluded from Evidence Trail v1.1 generated-manifest
evidence unless a future explicit Evidence Trail version changes that rule.

## 2. Ownership Boundaries

### Studio owns evidence export

Studio owns `evidence-trail.json` export. It records human-reviewed decisions
and expands accepted or edited suggestions into evidence links at package
export time.

Studio may use imported contract artifacts, reviewed mapping files, samples,
and KA/KS citations to populate metadata. The exported manifest package remains
deterministic and Engine-facing; evidence stays in the sidecar.

### Engine consumes contracts, not evidence

Engine consumes manifest/package contract artifacts and generates apps. Engine
must not require `evidence-trail.json` to validate or generate an application.
Missing evidence metadata should not break Engine generation.

Engine-generated apps remain standalone. They must not depend on Studio, KS,
KA, MCP, TestBench, or EdgeForge runtime services to parse files, process XML,
or invoke SOAP.

### KS/KA may suggest, humans decide

Knowledge Server and Knowledge Assist may provide citations or suggestions, but
human-reviewed Studio decisions decide what is exported. Rejected suggestions
are excluded from generated-manifest evidence. Advisory-only scopes are also
excluded from generated-manifest evidence.

### Test console provenance stays separate

The generated-app test console has local descriptor provenance for operator
display. That metadata is generated into the app and is separate from
`evidence-trail.json`. A future slice may link console cards to Evidence Trail
record IDs, but this design does not require that.

## 3. Evidence Type Reuse

Evidence Trail v1.1 already covers the generated-artifact decision classes
needed for edge contracts. Edge-contract metadata should reuse these types:

| Existing evidence type | Edge-contract use |
|---|---|
| `field` | Canonical field selection, file layout field review, XML element/attribute review, SOAP operation field selection. |
| `mapping` | File/XML/SOAP source-to-target mappings and canonical request/response mappings. |
| `validation` | Layout, XSD, WSDL, root QName, trailer/control total, required-field, and sample validation decisions. |
| `transform` | Type coercion, decimal formatting, XML/canonical conversion, SOAP request/response value conversion. |
| `rule` | Existing rule evidence behavior, unchanged. |
| `cross_entity_rule` | Existing cross-entity rule evidence behavior, unchanged. |

Do not add `identity_role` evidence in this design. Identity roles remain
excluded from generated-manifest evidence unless a future explicit Evidence
Trail version changes that rule.

## 4. Common Metadata Fields

Edge-contract evidence records should keep `manifest_path` as the stable anchor
and put edge-contract details under a `metadata` object. All metadata fields are
additive and optional unless a future strict-governance mode says otherwise.

Common fields:

| Field | Meaning |
|---|---|
| `source_artifact` | Package-relative source artifact path that justified the decision. |
| `artifact_type` | Artifact family, for example `file_layout`, `csv_layout`, `fixed_width_layout`, `xsd`, `wsdl`, `mapping`, `sample`. |
| `contract_name` | Interface or contract name from the manifest. |
| `contract_type` | Manifest type, for example `file-fixed-width`, `file-csv`, `xml-xsd`, `soap-wsdl`. |
| `interface_name` | Name of the upstream or downstream interface row. |
| `interface_direction` | `upstream` or `downstream`. |
| `mapping_scope` | Mapping role, for example `inbound`, `outbound`, `request`, `response`, `fault`, `trailer_validation`. |
| `source_path` | Source-side path inside the contract or mapping. |
| `target_path` | Target-side path inside the contract, mapping, or canonical entity. |
| `sample_artifact` | Package-relative sample file path, when evidence came from a sample. |
| `sample_path` | Path within the sample, such as XPath, SOAP body path, or layout field name. |
| `sample_line` | 1-based sample line number for file/text samples, when known. |
| `namespace` | XML/XSD/SOAP namespace relevant to the decision. |
| `operation_name` | Operation name for SOAP/WSDL or future operation-scoped contracts. |
| `generated_artifact` | Package-relative generated artifact path or class/resource name, when useful for review. |

Path rules:

- All paths must be package-relative.
- Absolute local filesystem paths are invalid in exported evidence metadata.
- Remote URLs should be represented only when the source artifact itself is a
  reviewed, trusted remote reference in a future design. v1 file/XML/SOAP
  evidence should use package-local artifacts.
- Missing optional fields do not block export by default.

## 5. File-Contract Metadata

File-contract evidence covers fixed-width and CSV/delimited layouts, mappings,
sample rows, generated parsers/writers, and trailer/control reconciliation.

Additional metadata fields:

| Field | Meaning |
|---|---|
| `file_format` | `fixed-width` or `csv`. |
| `layout_field` | Layout field name. |
| `record_type` | `header`, `data`, `trailer`, or another reviewed record type. |
| `field_position` | 1-based fixed-width character position. |
| `field_length` | Fixed-width character length. |
| `csv_column_index` | 1-based CSV/delimited column index. |
| `delimiter` | CSV/delimited delimiter when relevant. |
| `decimal_format` | Layout decimal handling such as `minor_units`. |
| `type_coercion` | Mapping or validation coercion such as `major_to_minor_units` or reviewed aliases supported by Engine. |
| `value_source` | Control/trailer source expression such as `data_record_count` or `sum(Account.availableBalance)`. |
| `direction` | File data flow direction, `inbound` or `outbound`. |
| `sample_line` | 1-based sample line number. |

### Trailer/control evidence

Trailer and control validations should be represented as existing
`validation` evidence records, with optional `transform` records when a
coercion is involved.

Supported v1 examples:

- record count: `value_source: data_record_count` or the reviewed alias
  `record_count`;
- sum total: `value_source: sum(Entity.field)`;
- minor-unit comparison: `type_coercion` or `decimal_format` metadata explains
  how canonical decimal values compare to file trailer totals.

Broader reconciliation files, checksums, header semantic validation, SFTP or
object-store delivery, and partial-accept modes remain future scope.

## 6. XML/XSD Metadata

XML/XSD evidence covers XSD artifacts, selected roots, XML fields/attributes,
canonical mappings, sample XML paths, and generated parser/serializer artifacts.

Additional metadata fields:

| Field | Meaning |
|---|---|
| `artifact_type` | Use `xsd` for schema files and `xml_sample` for samples. |
| `xml_root` | Selected root element local name or QName. |
| `namespace` | XML namespace for the root, field, or attribute. |
| `xsd_path` | Package-relative XSD path. |
| `xpath` | XPath-like path to the selected XML element or attribute. |
| `xml_field_kind` | `element`, `attribute`, `root`, or `text`. |
| `sample_artifact` | Package-relative XML sample path. |
| `sample_xpath` | XPath-like path inside the sample payload. |

XML evidence must preserve namespace and root context. A field mapping from an
XML attribute to a canonical field should be distinguishable from a mapping
from an XML child element.

Unsupported XML/XSD v1 constructs may produce validation evidence if they were
reviewed and intentionally excluded from generation, but they should not appear
as generated-artifact mappings.

## 7. SOAP/WSDL Metadata

SOAP/WSDL evidence layers operation metadata on top of XML/XSD metadata.
Evidence records should identify the selected service/port/binding/operation
and the SOAP body/header/fault path that justified the mapping or validation.

Additional metadata fields:

| Field | Meaning |
|---|---|
| `artifact_type` | Use `wsdl` for WSDL files, `xsd` for referenced schemas, and `soap_sample` for samples. |
| `wsdl_service` | Selected WSDL service. |
| `wsdl_port` | Selected WSDL port. |
| `wsdl_binding` | Selected WSDL binding. |
| `wsdl_operation` | WSDL operation name. |
| `soap_action` | SOAPAction value when declared or selected. |
| `soap_body_path` | SOAP body path, for example `/GetCustomerRequest/customerId`. |
| `soap_header_path` | SOAP header path when headers are supported and reviewed. |
| `soap_fault` | Declared SOAP fault name or generated fault category. |
| `xsd_path` | Package-relative referenced XSD path for the message element. |
| `namespace` | SOAP/WSDL/XSD namespace relevant to the path. |

### Inbound canonical `read_by_id`

Inbound SOAP `read_by_id` evidence should use:

- `mapping` for request lookup and response field mappings;
- `validation` for WSDL operation, SOAPAction, root QName, XSD, and not-found
  fault checks;
- `field` for the canonical entity persistence ID selected as the lookup
  field;
- `transform` for type conversions between SOAP XML values and canonical field
  types.

### Outbound canonical `invoke_by_id`

Outbound SOAP `invoke_by_id` evidence should use:

- `mapping` for canonical-to-SOAP request mappings and SOAP response-to-JSON
  response mappings;
- `validation` for configured operation selection, request/response root QName,
  XSD validation, and safe fault diagnostics;
- `field` for the canonical entity persistence ID lookup field;
- `transform` for conservative value formatting or parsing.

Response persistence, audit/result-table persistence, retry/replay, and
idempotency evidence are out of scope until those runtime features are designed.

## 8. Evidence Rules

Studio export should apply these rules:

1. Accepted generated-artifact decisions may produce evidence.
2. Edited generated-artifact decisions may produce evidence and should preserve
   both the final reviewed value and the suggestion/citation link where
   available.
3. Rejected suggestions are excluded from generated-manifest evidence.
4. Advisory-only scopes are excluded from generated-manifest evidence unless a
   future design explicitly promotes them into generated artifacts.
5. Metadata-only identity roles remain excluded.
6. Evidence records must be deterministic and stable across export when inputs
   do not change.
7. Missing optional edge-contract evidence must not block package export unless
   the user explicitly enables a future strict governance mode.
8. Evidence metadata must not contain local absolute paths, stack traces,
   secrets, raw credentials, or machine-specific temporary directories.

## 9. Examples

### Fixed-width field evidence

```json
{
  "manifest_path": "upstream_interfaces.account-fixed-inbound.layout.account_id",
  "type": "field",
  "provenance": "human-authored",
  "metadata": {
    "source_artifact": "upstream/account-fixed-layout.yaml",
    "artifact_type": "fixed_width_layout",
    "contract_name": "account-fixed-inbound",
    "contract_type": "file-fixed-width",
    "interface_name": "account-fixed-inbound",
    "interface_direction": "upstream",
    "file_format": "fixed-width",
    "record_type": "data",
    "layout_field": "account_id",
    "field_position": 2,
    "field_length": 36,
    "source_path": "record_types.data.fields.account_id",
    "target_path": "Account.accountId",
    "sample_artifact": "upstream/sample-account-fixed.dat",
    "sample_line": 2
  }
}
```

### CSV trailer record-count evidence

```json
{
  "manifest_path": "upstream_interfaces.account-csv-inbound.trailer.record_count",
  "type": "validation",
  "provenance": "human-authored",
  "metadata": {
    "source_artifact": "upstream/account-csv-layout.yaml",
    "artifact_type": "csv_layout",
    "contract_name": "account-csv-inbound",
    "contract_type": "file-csv",
    "interface_direction": "upstream",
    "mapping_scope": "trailer_validation",
    "file_format": "csv",
    "record_type": "trailer",
    "layout_field": "record_count",
    "csv_column_index": 2,
    "delimiter": "|",
    "value_source": "data_record_count",
    "sample_artifact": "upstream/sample-account-inbound.csv",
    "sample_line": 4
  }
}
```

### XML field mapping evidence

```json
{
  "manifest_path": "upstream_interfaces.account-xml-inbound.mappings.accountId",
  "type": "mapping",
  "provenance": "ai-edited",
  "suggestion_id": "s-xml-account-id",
  "metadata": {
    "source_artifact": "contracts/account.xsd",
    "artifact_type": "xsd",
    "contract_name": "account-xml-inbound",
    "contract_type": "xml-xsd",
    "interface_name": "account-xml-inbound",
    "interface_direction": "upstream",
    "xml_root": "Account",
    "namespace": "urn:edgeforge:account:v1",
    "xsd_path": "contracts/account.xsd",
    "xpath": "/Account/@accountId",
    "xml_field_kind": "attribute",
    "source_path": "/Account/@accountId",
    "target_path": "Account.accountId",
    "sample_artifact": "samples/account.xml",
    "sample_xpath": "/Account/@accountId"
  }
}
```

### SOAP operation/body mapping evidence

```json
{
  "manifest_path": "downstream_interfaces.customer-soap-client.operations.syncCustomer.request_mappings.customerId",
  "type": "mapping",
  "provenance": "human-authored",
  "metadata": {
    "source_artifact": "contracts/customer-service.wsdl",
    "artifact_type": "wsdl",
    "contract_name": "customer-soap-client",
    "contract_type": "soap-wsdl",
    "interface_name": "customer-soap-client",
    "interface_direction": "downstream",
    "mapping_scope": "request",
    "wsdl_service": "CustomerService",
    "wsdl_port": "CustomerServicePort",
    "wsdl_binding": "CustomerSoapBinding",
    "wsdl_operation": "syncCustomer",
    "operation_name": "syncCustomer",
    "soap_action": "urn:customer:syncCustomer",
    "soap_body_path": "/SyncCustomerRequest/customerId",
    "source_path": "Customer.customerId",
    "target_path": "/SyncCustomerRequest/customerId",
    "namespace": "urn:edgeforge:customer:v1"
  }
}
```

### SOAP fault mapping evidence

```json
{
  "manifest_path": "upstream_interfaces.customer-soap-service.operations.getCustomer.not_found_fault",
  "type": "validation",
  "provenance": "human-authored",
  "metadata": {
    "source_artifact": "contracts/customer-service.wsdl",
    "artifact_type": "wsdl",
    "contract_name": "customer-soap-service",
    "contract_type": "soap-wsdl",
    "interface_name": "customer-soap-service",
    "interface_direction": "upstream",
    "mapping_scope": "fault",
    "wsdl_service": "CustomerService",
    "wsdl_port": "CustomerServicePort",
    "wsdl_binding": "CustomerSoapBinding",
    "wsdl_operation": "getCustomer",
    "operation_name": "getCustomer",
    "soap_fault": "CustomerNotFoundFault",
    "soap_body_path": "/GetCustomerRequest/customerId",
    "target_path": "Customer.customerId"
  }
}
```

## 10. Implementation Slices

| Slice | Scope | Primary repo |
|---|---|---|
| 0 | Design doc only. Done. | EdgeForge docs |
| 1 | Studio export support for file-contract evidence metadata. Done via Studio PR `#190`. | EdgeForgeStudio |
| 2 | Studio export support for XML/XSD evidence metadata. Done via Studio PR `#191`. | EdgeForgeStudio |
| 3 | Studio export support for SOAP/WSDL evidence metadata. Done via Studio PR `#192`. | EdgeForgeStudio |
| 4 | Package/golden tests proving `evidence-trail.json` contains contract provenance. Done for the combined v1 package via Studio PR `#193`. | EdgeForgeStudio + EdgeForge |
| 5 | Cross-family proof package using file + XML + SOAP evidence. Done for v1 smoke/proof; broader productized proof pack remains optional. | EdgeForge + EdgeForgeStudio |
| 6 | Optional KS/KA citation enrichment when deterministic citations are available. | EdgeForgeKnowledgeServer + EdgeForgeStudio |

Implementation started in Studio because Studio owns the sidecar export. Engine
may later add validation helpers or golden fixture checks that assert the
sidecar shape, but generated apps must remain independent of evidence metadata.

## 11. Open Questions

1. Does additive edge-contract metadata require an Evidence Trail schema version
   bump, or is it v1.1-compatible because `metadata` is already extensible?
2. Should a JSON Schema for `evidence-trail.json` live in EdgeForge docs first,
   or move directly into shared specs once multiple repos validate it?
3. How strict should export be when source artifacts referenced by evidence are
   missing from the package?
4. Should sample-based evidence be required for strict-governance export, or
   remain optional?
5. How much operation-level SOAP evidence is enough for v1: operation only,
   operation plus body paths, or operation plus fault/header paths?
6. Should generated-app operator console provenance eventually link to evidence
   records, or remain separate local UI metadata?
