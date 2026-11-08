"""Translation from manifest-driven input projects into normalized metadata."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from appbuilder.contracts import ProjectDefinition, load_project_definition
from appbuilder.contracts.manifest import (
    SOAP_WSDL_CONTRACT_TYPE,
    XML_XSD_CONTRACT_TYPE,
    DataHandoffDefinition,
    IdGenerationOverride,
    InterfaceDefinition,
)
from appbuilder.contracts.soap_contracts import load_soap_contract_spec
from appbuilder.contracts.xml_contracts import load_xml_contract_spec
from appbuilder.core import AppArchetype
from appbuilder.core.sql_safety import ValidatedStagingDdl, validate_staging_ddl
from appbuilder.generation.utils import (
    entity_id_field,
    staging_operational_column_role,
    to_pascal_case,
    to_snake_case,
)
from appbuilder.generation.utils import (
    xml_field_type_label as _xml_field_type_label,
)
from appbuilder.generation.utils import (
    xml_mapping_types_compatible as _xml_mapping_types_compatible,
)
from appbuilder.ingestion.openapi_classifier import (
    ingest_openapi_entities,
    ingest_openapi_operations,
    openapi_type_to_canonical_type,
    required_nullable_request_fields,
)
from appbuilder.ingestion.openapi_fetcher import (
    OpenAPIFetchPolicyError,
    fetch_openapi_spec,
)
from appbuilder.mapping import (
    FieldMapping,
    MappingCompletenessReport,
    MappingDirection,
    MappingIssue,
    MappingSeverity,
    build_output_mapping_artifacts,
    build_upstream_mapping_artifacts,
)
from appbuilder.rules import CanonicalRule, RuleType, load_rule_definitions
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

from .file_contracts import FILE_CONTRACT_TYPES, FileLayoutSpec, load_file_layout_spec
from .kafka_models import KafkaMetadata
from .kafka_translation import translate_kafka_project
from .models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    CanonicalRelationship,
    ContractMetadata,
    HttpMethod,
    IdentityRole,
    IdentityRoleMetadata,
    IdentityRoleMode,
    IdGenerationStrategy,
    MetadataProject,
    RelationshipType,
    ResponseShape,
    RouteEntry,
    RoutingRule,
    RunSemanticsMetadata,
    SystemParticipant,
    TransformMapping,
)

_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ISO_DATETIME_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)

_SERVER_GENERATED_ID_INCOMPATIBLE_RULE_TYPES = frozenset(
    {
        RuleType.ALLOWED_VALUES,
        RuleType.DEFAULT,
        RuleType.MAX_LENGTH,
        RuleType.MIN_LENGTH,
        RuleType.PATTERN,
        RuleType.RANGE,
    }
)
_EVENT_OR_TRANSACTION_ENTITY_TERMS = frozenset(
    {
        "transaction",
        "posting",
        "event",
        "history",
        "ledgerentry",
        "ledger",
        "activity",
        "movement",
    }
)
_PARENT_REFERENCE_ID_STEMS = frozenset(
    {
        "account",
        "customer",
        "loan",
        "parent",
        "client",
        "borrower",
        "user",
        "party",
        "counterparty",
    }
)
_TRANSPORT_WRAPPER_FIELD_NAMES = frozenset(
    {
        "transactions",
        "currentpage",
        "pagesize",
        "totalelements",
        "totalpages",
        "totalitems",
        "links",
        "meta",
    }
)
_SOAP_RESPONSE_TARGET_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class _UpstreamFieldHint:
    type: CanonicalFieldType
    required: bool = False
    format: str | None = None
    max_length: int | None = None
    allowed_values: tuple[str, ...] = ()


@dataclass
class _FieldAccumulator:
    name: str
    type: CanonicalFieldType = CanonicalFieldType.STRING
    required: bool = False
    not_null: bool = False
    max_length: int | None = None
    min_length: int | None = None
    pattern: str | None = None
    range_min: float | None = None
    range_max: float | None = None
    format: str | None = None
    default_value: str | None = None
    allowed_values: list[str] = field(default_factory=list)
    source_paths: list[str] = field(default_factory=list)
    # True when the id field appears in the create request body — client supplies the id.
    # server_generated_id on the emitted CanonicalField will be False in that case.
    client_supplied_id: bool = False

    def merge_length(self, length: int | None) -> None:
        """Keep the tightest length constraint so generated code satisfies all contracts."""
        if length is None:
            return
        if self.max_length is None:
            self.max_length = length
        else:
            self.max_length = min(self.max_length, length)

    def merge_min_length(self, length: int | None) -> None:
        """Keep the strongest minimum length constraint."""
        if length is None:
            return
        if self.min_length is None:
            self.min_length = length
        else:
            self.min_length = max(self.min_length, length)

    def merge_pattern(self, pattern: str | None) -> None:
        if pattern and self.pattern is None:
            self.pattern = pattern

    def merge_range_min(self, value: float | None) -> None:
        if value is None:
            return
        if self.range_min is None:
            self.range_min = value
        else:
            self.range_min = max(self.range_min, value)

    def merge_range_max(self, value: float | None) -> None:
        if value is None:
            return
        if self.range_max is None:
            self.range_max = value
        else:
            self.range_max = min(self.range_max, value)

    def add_source(self, source_path: str) -> None:
        if source_path not in self.source_paths:
            self.source_paths.append(source_path)

    def add_allowed_values(self, values: Iterable[str]) -> None:
        for value in values:
            if value not in self.allowed_values:
                self.allowed_values.append(value)


def build_metadata_project(manifest_path: str | Path) -> MetadataProject:
    """Build normalized metadata from a manifest-driven input project."""

    manifest_file = Path(manifest_path)
    definition = load_project_definition(manifest_file)
    return translate_project(definition, project_root=manifest_file.parent)


def translate_project(
    definition: ProjectDefinition,
    *,
    project_root: str | Path | None = None,
) -> MetadataProject | KafkaMetadata:
    """Translate a loaded project definition into normalized metadata."""

    resolved_project_root = (
        Path(project_root) if project_root is not None else definition.manifest_path.parent
    )
    target_profile = TARGET_PROFILES[definition.target_profile]
    _validate_file_contract_runtime_boundaries(definition, project_root=resolved_project_root)
    _validate_xml_xsd_contracts(definition, project_root=resolved_project_root)
    _validate_soap_wsdl_contracts(definition, project_root=resolved_project_root)
    if definition.app_archetype == AppArchetype.KAFKA_INTEGRATION:
        return translate_kafka_project(
            definition,
            project_root=resolved_project_root,
        )
    if definition.app_archetype == AppArchetype.PASSTHROUGH_ROUTER:
        return _translate_passthrough_project(
            definition,
            project_root=resolved_project_root,
        )

    identity_override_lookup = {
        override.entity: override.persistence_id for override in definition.identity_overrides
    }
    id_generation_override_lookup = {
        override.entity: override for override in definition.id_generation_overrides
    }
    field_accumulators: OrderedDict[str, _FieldAccumulator] = OrderedDict()
    operations: list[CanonicalOperation] = []
    rest_contracts: list[dict] = []
    contracts: list[ContractMetadata] = []
    systems = OrderedDict[str, SystemParticipant]()
    entity_names: OrderedDict[str, None] = OrderedDict()
    openapi_entities: OrderedDict[str, CanonicalEntity] = OrderedDict()
    mappings: list[FieldMapping] = []
    mapping_reports: list[MappingCompletenessReport] = []
    rules: list[CanonicalRule] = []
    default_entity_name = _derive_primary_entity_name(definition, entity_names=())

    for interface in definition.upstream_interfaces:
        source = interface.spec if interface.spec is not None else interface.spec_url or ""
        notes: list[str] = []
        if interface.type == XML_XSD_CONTRACT_TYPE:
            xsd_path = _xml_xsd_interface_path(interface)
            xml_spec = load_xml_contract_spec(
                resolved_project_root / xsd_path,
                interface_name=interface.name,
                root_element=interface.root_element or "",
                namespace=interface.namespace,
                namespace_alias=interface.namespace_alias,
                source_xsd_path=xsd_path,
                package_root=resolved_project_root,
            )
            notes.append("xml-contract: xsd v1 parsed")
            contracts.append(
                ContractMetadata(
                    name=interface.name,
                    type=interface.type,
                    version=interface.version,
                    source=xsd_path,
                    physical_name=None,
                    sample_paths=_collect_interface_sample_paths(interface),
                    mapping_path=interface.mapping,
                    ingestion_notes=notes,
                    xml_contract=xml_spec.to_metadata(),
                )
            )
            system_name = _resolve_system_name(interface.system, interface.name, fallback="UPSTREAM")
            systems[system_name] = SystemParticipant(name=system_name, role="upstream")
            if interface.mapping:
                (
                    interface_operations,
                    interface_mappings,
                    interface_report,
                    interface_entity_name,
                ) = _ingest_upstream_xml_interface(
                    resolved_project_root,
                    interface,
                    xml_contract=xml_spec.to_metadata(),
                    field_accumulators=field_accumulators,
                    default_entity_name=default_entity_name,
                )
                operations.extend(interface_operations)
                mappings.extend(interface_mappings)
                mapping_reports.append(interface_report)
                entity_names[interface_entity_name] = None
            continue
        if interface.type == SOAP_WSDL_CONTRACT_TYPE:
            wsdl_path = _soap_wsdl_interface_path(interface)
            soap_spec = load_soap_contract_spec(
                resolved_project_root / wsdl_path,
                interface_name=interface.name,
                service=interface.service,
                port=interface.port,
                binding=interface.binding,
                operation_names=_interface_operation_names(interface),
                source_wsdl_path=wsdl_path,
                package_root=resolved_project_root,
            )
            notes.append("soap-contract: wsdl v1 parsed")
            soap_contract_metadata = soap_spec.to_metadata()
            soap_contract_metadata["direction"] = "upstream"
            if interface.mapping:
                soap_contract_metadata["operation_mappings"] = _load_soap_operation_mappings(
                    resolved_project_root / interface.mapping,
                    interface_name=interface.name,
                    operations=soap_contract_metadata["operations"],
                    direction="upstream",
                )
            contracts.append(
                ContractMetadata(
                    name=interface.name,
                    type=interface.type,
                    version=interface.version,
                    source=wsdl_path,
                    physical_name=None,
                    sample_paths=_collect_interface_sample_paths(interface),
                    mapping_path=interface.mapping,
                    ingestion_notes=notes,
                    soap_contract=soap_contract_metadata,
                )
            )
            system_name = _resolve_system_name(interface.system, interface.name, fallback="UPSTREAM")
            systems[system_name] = SystemParticipant(name=system_name, role="upstream")
            continue
        if interface.type in {"file-fixed-width", "file-csv"} and interface.spec:
            layout_spec = load_file_layout_spec(
                resolved_project_root / interface.spec,
                contract_type=interface.type,
            )
            contracts.append(
                ContractMetadata(
                    name=interface.name,
                    type=interface.type,
                    version=interface.version,
                    source=source,
                    physical_name=None,
                    sample_paths=_collect_interface_sample_paths(interface),
                    mapping_path=interface.mapping,
                    ingestion_notes=notes,
                    file_layout=layout_spec.to_metadata(),
                )
            )
            system_name = _resolve_system_name(interface.system, interface.name, fallback="UPSTREAM")
            systems[system_name] = SystemParticipant(name=system_name, role="upstream")
            (
                interface_operations,
                interface_mappings,
                interface_report,
                interface_entity_name,
            ) = _ingest_upstream_file_interface(
                resolved_project_root,
                interface,
                layout_spec=layout_spec,
                field_accumulators=field_accumulators,
                default_entity_name=default_entity_name,
            )
            operations.extend(interface_operations)
            mappings.extend(interface_mappings)
            mapping_reports.append(interface_report)
            entity_names[interface_entity_name] = None
            continue
        ingested_openapi_entities: list[CanonicalEntity] = []
        collect_sample_fields = True
        openapi_spec_for_interface: dict | None = None
        if interface.spec_url:
            try:
                openapi_spec_for_interface = fetch_openapi_spec(interface.spec_url)
                ingested_openapi_entities = ingest_openapi_entities(
                    openapi_spec_for_interface,
                    interface.name,
                )
                if ingested_openapi_entities:
                    notes.append(
                        f"OpenAPI spec ingested from {interface.spec_url}: "
                        f"{len(ingested_openapi_entities)} domain "
                        f"{'entity classified' if len(ingested_openapi_entities) == 1 else 'entities classified'}."
                    )
                    collect_sample_fields = False
                else:
                    notes.append(
                        f"OpenAPI spec ingested from {interface.spec_url}: 0 domain entities classified. "
                        "Falling back to sample ingestion."
                    )
            except OpenAPIFetchPolicyError:
                raise
            except ValueError as exc:
                notes.append(f"spec_url fetch failed: {exc}. Falling back to sample ingestion.")
        elif interface.spec:
            local_spec = _load_yaml(resolved_project_root / interface.spec)
            if isinstance(local_spec.get("paths"), dict):
                openapi_spec_for_interface = local_spec
        if openapi_spec_for_interface is not None:
            from appbuilder.ingestion.rest_contract import selected_rest_contracts
            selection = [op.name for op in interface.operations] or list(_load_upstream_samples(resolved_project_root, interface)) or None
            rest_contracts.extend(selected_rest_contracts(openapi_spec_for_interface, interface.name, selection))
        contracts.append(
            ContractMetadata(
                name=interface.name,
                type=interface.type,
                version=interface.version,
                source=source,
                physical_name=None,
                sample_paths=_collect_interface_sample_paths(interface),
                mapping_path=interface.mapping,
                ingestion_notes=notes,
            )
        )
        system_name = _resolve_system_name(interface.system, interface.name, fallback="UPSTREAM")
        systems[system_name] = SystemParticipant(name=system_name, role="upstream")
        (
            interface_operations,
            interface_mappings,
            interface_report,
            interface_entity_name,
        ) = _ingest_upstream_interface(
            resolved_project_root,
            interface,
            field_accumulators,
            default_entity_name=default_entity_name,
            collect_sample_fields=collect_sample_fields,
            openapi_spec=openapi_spec_for_interface,
            notes=notes,
        )
        # If the interface has explicit sample-based operations, enrich them from
        # OpenAPI metadata by matching operationId. Otherwise use the OpenAPI
        # operations directly when available.
        has_sample_ops = bool(interface.operations) or bool(interface.samples)
        if openapi_spec_for_interface is not None and not has_sample_ops:
            openapi_ops = ingest_openapi_operations(openapi_spec_for_interface, interface.name)
            if openapi_ops:
                # Use OpenAPI-derived operations with rich REST metadata (HTTP method, path, params)
                operations.extend(openapi_ops)
            else:
                operations.extend(interface_operations)
        elif openapi_spec_for_interface is not None:
            openapi_ops = ingest_openapi_operations(openapi_spec_for_interface, interface.name)
            operations.extend(_enrich_operations_with_openapi(interface_operations, openapi_ops))
        else:
            operations.extend(interface_operations)
        mappings.extend(interface_mappings)
        mapping_reports.append(interface_report)
        entity_names[interface_entity_name] = None
        for entity in ingested_openapi_entities:
            entity_names[entity.name] = None
            if entity.name not in openapi_entities:
                openapi_entities[entity.name] = entity

    for interface in definition.downstream_interfaces:
        source = interface.spec if interface.spec is not None else interface.spec_url or ""
        notes: list[str] = []
        file_layout_metadata: dict[str, Any] | None = None
        xml_contract_metadata: dict[str, Any] | None = None
        soap_contract_metadata: dict[str, Any] | None = None
        if interface.type == XML_XSD_CONTRACT_TYPE:
            xsd_path = _xml_xsd_interface_path(interface)
            xml_spec = load_xml_contract_spec(
                resolved_project_root / xsd_path,
                interface_name=interface.name,
                root_element=interface.root_element or "",
                namespace=interface.namespace,
                namespace_alias=interface.namespace_alias,
                source_xsd_path=xsd_path,
                package_root=resolved_project_root,
            )
            notes.append("xml-contract: xsd v1 parsed")
            xml_contract_metadata = xml_spec.to_metadata()
            source = xsd_path
        if interface.type == SOAP_WSDL_CONTRACT_TYPE:
            wsdl_path = _soap_wsdl_interface_path(interface)
            soap_spec = load_soap_contract_spec(
                resolved_project_root / wsdl_path,
                interface_name=interface.name,
                service=interface.service,
                port=interface.port,
                binding=interface.binding,
                operation_names=_interface_operation_names(interface),
                source_wsdl_path=wsdl_path,
                package_root=resolved_project_root,
            )
            notes.append("soap-contract: wsdl v1 parsed")
            soap_contract_metadata = soap_spec.to_metadata()
            soap_contract_metadata["direction"] = "downstream"
            if interface.mapping:
                soap_contract_metadata["operation_mappings"] = _load_soap_operation_mappings(
                    resolved_project_root / interface.mapping,
                    interface_name=interface.name,
                    operations=soap_contract_metadata["operations"],
                    direction="downstream",
                )
            source = wsdl_path
        if interface.spec_url:
            notes.append(
                "spec_url is declared on a downstream interface, but remote downstream contract "
                "fetching is not implemented."
            )
        if interface.spec and interface.type in FILE_CONTRACT_TYPES:
            layout_spec = load_file_layout_spec(
                resolved_project_root / interface.spec,
                contract_type=interface.type,
            )
            layout_note = _file_layout_note(interface.type, layout_spec)
            if layout_note is not None:
                notes.append(layout_note)
            file_layout_metadata = layout_spec.to_metadata()
        contracts.append(
            ContractMetadata(
                name=interface.name,
                type=interface.type,
                version=interface.version,
                source=source,
                physical_name=None,
                sample_paths=_collect_interface_sample_paths(interface),
                mapping_path=interface.mapping,
                ingestion_notes=notes,
                file_layout=file_layout_metadata,
                xml_contract=xml_contract_metadata,
                soap_contract=soap_contract_metadata,
            )
        )
        system_name = _resolve_system_name(
            interface.system, interface.name, fallback="DOWNSTREAM"
        )
        systems[system_name] = SystemParticipant(name=system_name, role="downstream")
        if interface.type == XML_XSD_CONTRACT_TYPE:
            if interface.mapping and xml_contract_metadata is not None:
                (
                    interface_operations,
                    interface_mappings,
                    interface_report,
                    interface_entity_name,
                ) = _ingest_downstream_xml_interface(
                    resolved_project_root,
                    interface,
                    xml_contract=xml_contract_metadata,
                    field_accumulators=field_accumulators,
                    default_entity_name=default_entity_name,
                )
                operations.extend(interface_operations)
                mappings.extend(interface_mappings)
                mapping_reports.append(interface_report)
                entity_names[interface_entity_name] = None
            continue
        if interface.type == SOAP_WSDL_CONTRACT_TYPE:
            continue
        (
            interface_operations,
            interface_mappings,
            interface_report,
            interface_entity_name,
        ) = _ingest_downstream_interface(
            resolved_project_root,
            interface,
            field_accumulators,
            default_entity_name=default_entity_name,
        )
        operations.extend(interface_operations)
        mappings.extend(interface_mappings)
        mapping_reports.append(interface_report)
        entity_names[interface_entity_name] = None

    # accumulate staging DDL content so sql_emitter can generate Flyway migrations
    staging_ddls: dict[str, str] = {}
    staging_ddl_owners: dict[str, str] = {}
    canonical_types_before_handoffs = {
        field_key: accumulator.type
        for field_key, accumulator in field_accumulators.items()
    }
    staging_column_types_by_contract: dict[
        str, dict[str, CanonicalFieldType]
    ] = {}
    for handoff in definition.data_handoffs:
        ddl_content = (resolved_project_root / handoff.spec).read_text(encoding="utf-8")
        validated_ddl = validate_staging_ddl(
            ddl_content,
            handoff_name=handoff.name,
            database=target_profile.runtime_database_dependency,
            declared_table=_declared_handoff_table_name(
                resolved_project_root / handoff.mapping if handoff.mapping else None
            ),
        )
        physical_name = validated_ddl.table_name
        staging_column_types_by_contract[handoff.name] = {
            column.name.lower(): _sql_type_to_canonical_type(column.raw_type)
            for column in validated_ddl.columns
        }
        physical_key = physical_name.lower()
        if physical_key in staging_ddl_owners:
            raise ValueError(
                f"Staging DDL for handoff '{handoff.name}' targets table '{physical_name}', "
                f"which is already declared by handoff '{staging_ddl_owners[physical_key]}'. "
                "Each staging handoff must declare a unique physical table."
            )
        staging_ddl_owners[physical_key] = handoff.name
        # Preserve the exact decoded SQL text consumed by validation; unsupported SQL
        # is rejected, never silently rewritten.
        staging_ddls[physical_name] = ddl_content
        contract_metadata = ContractMetadata(
            name=handoff.name,
            type=handoff.type,
            version=handoff.version,
            source=handoff.spec,
            physical_name=physical_name,
            mapping_path=handoff.mapping,
        )
        contracts.append(contract_metadata)
        system_name = _resolve_system_name(handoff.system, handoff.name, fallback="HANDOFF")
        systems[system_name] = SystemParticipant(name=system_name, role="handoff")
        (
            handoff_operations,
            handoff_mappings,
            handoff_report,
            handoff_entity_name,
            handoff_run_semantics,
        ) = _ingest_data_handoff(
            resolved_project_root,
            handoff,
            field_accumulators,
            default_entity_name=default_entity_name,
            validated_ddl=validated_ddl,
        )
        contract_metadata.run_semantics = handoff_run_semantics
        operations.extend(handoff_operations)
        mappings.extend(handoff_mappings)
        mapping_reports.append(handoff_report)
        entity_names[handoff_entity_name] = None

    _validate_run_semantics_type_compatibility(
        contracts=contracts,
        mappings=mappings,
        canonical_types_before_handoffs=canonical_types_before_handoffs,
        staging_column_types_by_contract=staging_column_types_by_contract,
    )
    _validate_run_semantics_file_output_jobs(
        contracts=contracts,
        mappings=mappings,
    )

    for rule_path in definition.rules:
        rule_entity_name, loaded_rules = load_rule_definitions(resolved_project_root / rule_path)
        rules.extend(loaded_rules)
        _apply_canonical_rules(loaded_rules, field_accumulators)
        if rule_entity_name:
            entity_names[rule_entity_name] = None

    # Group field accumulators by entity prefix (keys are stored as "EntityName.fieldName")
    default_entity_name = _derive_primary_entity_name(definition, entity_names=entity_names.keys())
    entity_field_groups: OrderedDict[str, list[_FieldAccumulator]] = OrderedDict()
    for field_key, acc in field_accumulators.items():
        if "." in field_key:
            entity_prefix = field_key.split(".", 1)[0]
        else:
            entity_prefix = default_entity_name
        entity_field_groups.setdefault(entity_prefix, []).append(acc)

    built_entities: list[CanonicalEntity] = []
    for entity_group_name, accs in entity_field_groups.items():
        id_field_name, id_warning = _select_entity_id_field_name(
            entity_group_name,
            accs,
            operations=operations,
            mappings=mappings,
            identity_override=identity_override_lookup.get(entity_group_name),
        )
        built_entities.append(
            CanonicalEntity(
                name=entity_group_name,
                fields=[
                    CanonicalField(
                        name=acc.name,
                        type=acc.type,
                        is_id=acc.name == id_field_name,
                        required=acc.required,
                        not_null=acc.not_null,
                        max_length=acc.max_length,
                        min_length=acc.min_length,
                        pattern=acc.pattern,
                        range_min=acc.range_min,
                        range_max=acc.range_max,
                        format=acc.format,
                        default_value=acc.default_value,
                        allowed_values=list(acc.allowed_values),
                        source_paths=list(acc.source_paths),
                        server_generated_id=(
                            not _is_client_supplied_id_field(
                                entity_group_name,
                                acc.name,
                                mappings=mappings,
                            )
                            if acc.name == id_field_name
                            else not acc.client_supplied_id
                        ),
                    )
                    for acc in accs
                ],
                warnings=[id_warning] if id_warning is not None else [],
            )
        )

    entities = list(openapi_entities.values())
    for built_entity in built_entities:
        if not built_entity.fields:
            continue
        if built_entity.name in openapi_entities:
            # Merge normalized constraint enrichment into the existing OpenAPI entity
            # instead of silently discarding it.
            openapi_entity = openapi_entities[built_entity.name]
            existing_field_map = {f.name: f for f in openapi_entity.fields}
            for warning in built_entity.warnings:
                if warning not in openapi_entity.warnings:
                    openapi_entity.warnings.append(warning)
            for built_field in built_entity.fields:
                if built_field.name in existing_field_map:
                    _merge_canonical_field(existing_field_map[built_field.name], built_field)
                else:
                    # Pure rule-only field not present in the OpenAPI entity — append it
                    openapi_entity.fields.append(built_field)
        else:
            entities.append(built_entity)
    has_xml_contract = any(
        interface.type == XML_XSD_CONTRACT_TYPE
        for interface in [*definition.upstream_interfaces, *definition.downstream_interfaces]
    )
    has_soap_contract = any(
        interface.type == SOAP_WSDL_CONTRACT_TYPE
        for interface in [*definition.upstream_interfaces, *definition.downstream_interfaces]
    )
    if not entities:
        entities = (
            []
            if has_xml_contract or has_soap_contract
            else built_entities or [CanonicalEntity(name=default_entity_name, fields=[])]
        )

    _validate_staging_table_targets(
        staging_ddls=staging_ddls,
        staging_ddl_owners=staging_ddl_owners,
        entities=entities,
    )

    _normalize_entity_id_fields(
        entities,
        operations=operations,
        mappings=mappings,
        identity_overrides=identity_override_lookup,
    )
    mappings = _drop_transport_wrapper_persistence_fields(
        entities=entities,
        mappings=mappings,
    )
    for entity in entities:
        override = id_generation_override_lookup.get(entity.name)
        if override is None:
            continue
        for warning in _apply_id_generation_override(
            entity=entity,
            override=override,
            target_profile=target_profile,
        ):
            _append_entity_warning(entity, warning)

    _warn_on_server_generated_id_rules(entities, rules)
    relationships = _infer_relationships(entities, rules)
    _propagate_relationship_constraints(entities, relationships)
    identity_roles = _translate_identity_roles(definition, entities=entities)
    _validate_downstream_soap_canonical_operation_mappings(
        contracts=contracts,
        entities=entities,
    )

    # Collect project-level translation warnings from all entities
    project_warnings: list[str] = []
    for entity in entities:
        for warning in entity.warnings:
            project_warnings.append(f"{entity.name}: {warning}")

    return MetadataProject(
        app_name=definition.app_name,
        bounded_context=definition.bounded_context,
        schema_version=definition.schema_version,
        app_archetype=definition.app_archetype,
        target_profile=definition.target_profile,
        systems=list(systems.values()),
        contracts=contracts,
        operations=operations,
        selected_rest_contracts=rest_contracts,
        entities=entities,
        mappings=mappings,
        mapping_reports=mapping_reports,
        rules=rules,
        relationships=relationships,
        identity_roles=identity_roles,
        warnings=project_warnings,
        staging_table_ddls=staging_ddls,
    )


def _translate_passthrough_project(
    definition: ProjectDefinition,
    *,
    project_root: Path,
) -> MetadataProject:
    contracts: list[ContractMetadata] = []
    systems = OrderedDict[str, SystemParticipant]()
    operations: list[CanonicalOperation] = []
    rest_contracts: list[dict] = []
    routing_rules: list[RoutingRule] = []
    transform_mappings: list[TransformMapping] = []
    translation_warnings: list[str] = []

    upstream_interface_names = {interface.name for interface in definition.upstream_interfaces}
    downstream_interface_names = {interface.name for interface in definition.downstream_interfaces}

    for interface in definition.upstream_interfaces:
        notes: list[str] = []
        if interface.type == XML_XSD_CONTRACT_TYPE:
            xsd_path = _xml_xsd_interface_path(interface)
            xml_spec = load_xml_contract_spec(
                project_root / xsd_path,
                interface_name=interface.name,
                root_element=interface.root_element or "",
                namespace=interface.namespace,
                namespace_alias=interface.namespace_alias,
                source_xsd_path=xsd_path,
                package_root=project_root,
            )
            notes.append("xml-contract: xsd v1 parsed")
            contracts.append(
                ContractMetadata(
                    name=interface.name,
                    type=interface.type,
                    version=interface.version,
                    source=xsd_path,
                    sample_paths=_collect_interface_sample_paths(interface),
                    mapping_path=interface.mapping,
                    ingestion_notes=notes,
                    xml_contract=xml_spec.to_metadata(),
                )
            )
            system_name = _resolve_system_name(interface.system, interface.name, fallback="UPSTREAM")
            systems[system_name] = SystemParticipant(name=system_name, role="upstream")
            continue
        if interface.type == SOAP_WSDL_CONTRACT_TYPE:
            wsdl_path = _soap_wsdl_interface_path(interface)
            soap_spec = load_soap_contract_spec(
                project_root / wsdl_path,
                interface_name=interface.name,
                service=interface.service,
                port=interface.port,
                binding=interface.binding,
                operation_names=_interface_operation_names(interface),
                source_wsdl_path=wsdl_path,
                package_root=project_root,
            )
            notes.append("soap-contract: wsdl v1 parsed")
            soap_contract_metadata = soap_spec.to_metadata()
            soap_contract_metadata["direction"] = "upstream"
            if interface.mapping:
                soap_contract_metadata["operation_mappings"] = _load_soap_operation_mappings(
                    project_root / interface.mapping,
                    interface_name=interface.name,
                    operations=soap_contract_metadata["operations"],
                    direction="upstream",
                )
            contracts.append(
                ContractMetadata(
                    name=interface.name,
                    type=interface.type,
                    version=interface.version,
                    source=wsdl_path,
                    sample_paths=_collect_interface_sample_paths(interface),
                    mapping_path=interface.mapping,
                    ingestion_notes=notes,
                    soap_contract=soap_contract_metadata,
                )
            )
            system_name = _resolve_system_name(interface.system, interface.name, fallback="UPSTREAM")
            systems[system_name] = SystemParticipant(name=system_name, role="upstream")
            continue
        spec = _load_interface_openapi_spec(project_root, interface, notes=notes)
        source = interface.spec if interface.spec is not None else interface.spec_url or ""
        contracts.append(
            ContractMetadata(
                name=interface.name,
                type=interface.type,
                version=interface.version,
                source=source,
                sample_paths=_collect_interface_sample_paths(interface),
                mapping_path=interface.mapping,
                ingestion_notes=notes,
            )
        )
        system_name = _resolve_system_name(interface.system, interface.name, fallback="UPSTREAM")
        systems[system_name] = SystemParticipant(name=system_name, role="upstream")
        if spec is not None:
            from appbuilder.ingestion.rest_contract import selected_rest_contracts
            selection = [op.name for op in interface.operations] or None
            rest_contracts.extend(selected_rest_contracts(spec, interface.name, selection))
            _validate_passthrough_required_request_nullability(
                spec,
                interface_name=interface.name,
            )
            interface_operations = ingest_openapi_operations(
                spec,
                interface.name,
                fail_on_unrepresentable_required_request_fields=True,
                resolve_nested_request_properties=True,
                diagnose_nested_reference_failures=True,
                warnings_out=translation_warnings,
            )
            _validate_passthrough_operation_request_validation_contracts(
                interface_operations,
                interface_name=interface.name,
            )
            operations.extend(op for op in interface_operations if selection is None or op.name in selection)

    for interface in definition.downstream_interfaces:
        notes: list[str] = []
        if interface.type == XML_XSD_CONTRACT_TYPE:
            xsd_path = _xml_xsd_interface_path(interface)
            xml_spec = load_xml_contract_spec(
                project_root / xsd_path,
                interface_name=interface.name,
                root_element=interface.root_element or "",
                namespace=interface.namespace,
                namespace_alias=interface.namespace_alias,
                source_xsd_path=xsd_path,
                package_root=project_root,
            )
            notes.append("xml-contract: xsd v1 parsed")
            contracts.append(
                ContractMetadata(
                    name=interface.name,
                    type=interface.type,
                    version=interface.version,
                    source=xsd_path,
                    sample_paths=_collect_interface_sample_paths(interface),
                    mapping_path=interface.mapping,
                    ingestion_notes=notes,
                    xml_contract=xml_spec.to_metadata(),
                )
            )
            system_name = _resolve_system_name(interface.system, interface.name, fallback="DOWNSTREAM")
            systems[system_name] = SystemParticipant(name=system_name, role="downstream")
            continue
        if interface.type == SOAP_WSDL_CONTRACT_TYPE:
            wsdl_path = _soap_wsdl_interface_path(interface)
            soap_spec = load_soap_contract_spec(
                project_root / wsdl_path,
                interface_name=interface.name,
                service=interface.service,
                port=interface.port,
                binding=interface.binding,
                operation_names=_interface_operation_names(interface),
                source_wsdl_path=wsdl_path,
                package_root=project_root,
            )
            notes.append("soap-contract: wsdl v1 parsed")
            soap_contract_metadata = soap_spec.to_metadata()
            soap_contract_metadata["direction"] = "downstream"
            if interface.mapping:
                soap_contract_metadata["operation_mappings"] = _load_soap_operation_mappings(
                    project_root / interface.mapping,
                    interface_name=interface.name,
                    operations=soap_contract_metadata["operations"],
                    direction="downstream",
                )
            contracts.append(
                ContractMetadata(
                    name=interface.name,
                    type=interface.type,
                    version=interface.version,
                    source=wsdl_path,
                    sample_paths=_collect_interface_sample_paths(interface),
                    mapping_path=interface.mapping,
                    ingestion_notes=notes,
                    soap_contract=soap_contract_metadata,
                )
            )
            system_name = _resolve_system_name(interface.system, interface.name, fallback="DOWNSTREAM")
            systems[system_name] = SystemParticipant(name=system_name, role="downstream")
            continue
        spec = _load_interface_openapi_spec(project_root, interface, notes=notes)
        source = interface.spec if interface.spec is not None else interface.spec_url or ""
        contracts.append(
            ContractMetadata(
                name=interface.name,
                type=interface.type,
                version=interface.version,
                source=source,
                sample_paths=_collect_interface_sample_paths(interface),
                mapping_path=interface.mapping,
                ingestion_notes=notes,
            )
        )
        system_name = _resolve_system_name(interface.system, interface.name, fallback="DOWNSTREAM")
        systems[system_name] = SystemParticipant(name=system_name, role="downstream")
        if spec is not None:
            operations.extend(
                ingest_openapi_operations(
                    spec,
                    interface.name,
                    diagnose_nested_reference_failures=True,
                    warnings_out=translation_warnings,
                )
            )

    for rule_path in definition.rules:
        loaded_routing_rules, loaded_transform_mappings = _load_passthrough_rule_config(
            project_root / rule_path
        )
        routing_rules.extend(loaded_routing_rules)
        transform_mappings.extend(loaded_transform_mappings)

    _validate_passthrough_configuration(
        routing_rules=routing_rules,
        transform_mappings=transform_mappings,
        upstream_request_fields={
            field.name
            for operation in operations
            if operation.interface_name in upstream_interface_names
            for field in operation.request_fields
        },
        downstream_request_fields={
            field.name
            for operation in operations
            if operation.interface_name in downstream_interface_names
            for field in operation.request_fields
        },
        downstream_targets={
            participant.name
            for participant in systems.values()
            if participant.role == "downstream"
        },
    )

    return MetadataProject(
        app_name=definition.app_name,
        bounded_context=definition.bounded_context,
        schema_version=definition.schema_version,
        app_archetype=definition.app_archetype,
        target_profile=definition.target_profile,
        systems=list(systems.values()),
        contracts=contracts,
        operations=operations,
        selected_rest_contracts=rest_contracts,
        entities=[],
        mappings=[],
        mapping_reports=[],
        rules=[],
        relationships=[],
        routing_rules=routing_rules,
        transform_mappings=transform_mappings,
        warnings=translation_warnings,
        staging_table_ddls={},
    )


def _validate_file_contract_runtime_boundaries(
    definition: ProjectDefinition,
    *,
    project_root: Path,
) -> None:
    for interface in definition.upstream_interfaces:
        if interface.type not in FILE_CONTRACT_TYPES:
            continue
        if interface.spec:
            load_file_layout_spec(project_root / interface.spec, contract_type=interface.type)
        if interface.type in {"file-fixed-width", "file-csv"}:
            if definition.app_archetype != AppArchetype.CRUD:
                raise ValueError(
                    f"Inbound {interface.type} parser generation is currently implemented only for "
                    f"app_archetype: crud. Interface '{interface.name}' uses "
                    f"app_archetype: {definition.app_archetype.value}."
                )
            continue
        raise ValueError(
            "Inbound file contract generation is not implemented yet for upstream "
            f"interface '{interface.name}' ({interface.type})."
        )

    for interface in definition.downstream_interfaces:
        if interface.type not in FILE_CONTRACT_TYPES:
            continue
        if interface.spec:
            load_file_layout_spec(project_root / interface.spec, contract_type=interface.type)
        if definition.app_archetype != AppArchetype.CRUD:
            raise ValueError(
                f"Downstream {interface.type} generation is currently implemented only for "
                f"app_archetype: crud. Interface '{interface.name}' uses "
                f"app_archetype: {definition.app_archetype.value}."
            )


def _validate_xml_xsd_contracts(
    definition: ProjectDefinition,
    *,
    project_root: Path,
) -> None:
    has_xml_contract = False
    for interface in [*definition.upstream_interfaces, *definition.downstream_interfaces]:
        if interface.type != XML_XSD_CONTRACT_TYPE:
            continue
        has_xml_contract = True
        xsd_path = _xml_xsd_interface_path(interface)
        load_xml_contract_spec(
            project_root / xsd_path,
            interface_name=interface.name,
            root_element=interface.root_element or "",
            namespace=interface.namespace,
            namespace_alias=interface.namespace_alias,
            source_xsd_path=xsd_path,
            package_root=project_root,
        )
    if has_xml_contract and definition.app_archetype == AppArchetype.KAFKA_INTEGRATION:
        raise ValueError(
            "XML/XSD runtime generation is not implemented yet for "
            "app_archetype: kafka-integration."
        )


def _validate_soap_wsdl_contracts(
    definition: ProjectDefinition,
    *,
    project_root: Path,
) -> None:
    has_soap_contract = False
    for interface in [*definition.upstream_interfaces, *definition.downstream_interfaces]:
        if interface.type != SOAP_WSDL_CONTRACT_TYPE:
            continue
        has_soap_contract = True
        wsdl_path = _soap_wsdl_interface_path(interface)
        load_soap_contract_spec(
            project_root / wsdl_path,
            interface_name=interface.name,
            service=interface.service,
            port=interface.port,
            binding=interface.binding,
            operation_names=_interface_operation_names(interface),
            source_wsdl_path=wsdl_path,
            package_root=project_root,
        )
    if has_soap_contract and definition.app_archetype == AppArchetype.KAFKA_INTEGRATION:
        raise ValueError(
            "SOAP/WSDL runtime generation is not implemented yet for "
            "app_archetype: kafka-integration."
        )


def _xml_xsd_interface_path(interface: InterfaceDefinition) -> str:
    return interface.xsd_path or interface.spec or ""


def _soap_wsdl_interface_path(interface: InterfaceDefinition) -> str:
    return interface.wsdl_path or interface.spec or ""


def _interface_operation_names(interface: InterfaceDefinition) -> tuple[str, ...] | None:
    if not interface.operations:
        return None
    return tuple(operation.name for operation in interface.operations)


def _load_soap_operation_mappings(
    mapping_path: Path,
    *,
    interface_name: str,
    operations: Iterable[dict[str, Any]],
    direction: str,
) -> dict[str, dict[str, Any]]:
    raw = _load_yaml(mapping_path)
    operation_mappings = raw.get("operation_mappings")
    if not isinstance(operation_mappings, list) or not operation_mappings:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' mapping '{mapping_path}' must declare "
            "a non-empty operation_mappings list."
        )
    operation_lookup = {str(operation["name"]): operation for operation in operations}
    operation_names = set(operation_lookup)
    parsed: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(operation_mappings):
        if not isinstance(entry, dict):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation_mappings[{index}] must be a mapping."
            )
        operation = str(entry.get("operation") or "").strip()
        if not operation:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation_mappings[{index}] requires operation."
            )
        if operation not in operation_names:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' mapping references unknown operation "
                f"'{operation}'."
            )
        if operation in parsed:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' mapping declares operation "
                f"'{operation}' more than once."
            )
        mode = str(entry.get("mode") or "adapter_only").strip()
        if mode not in {"adapter_only", "canonical"}:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation}' uses unsupported "
                f"operation mapping mode '{mode}'. Supported modes are adapter_only and canonical."
            )
        allowed_keys = {"operation", "mode"}
        if mode == "adapter_only":
            allowed_keys.add("handler_method")
            if "canonical_operation" in entry:
                raise ValueError(
                    f"SOAP/WSDL interface '{interface_name}' operation '{operation}' cannot declare "
                    "canonical_operation when mode is adapter_only."
                )
        else:
            allowed_keys.add("canonical_operation")
            if "handler_method" in entry:
                raise ValueError(
                    f"SOAP/WSDL interface '{interface_name}' operation '{operation}' cannot combine "
                    "handler_method with mode canonical."
                )
        unknown_keys = sorted(set(entry) - allowed_keys)
        if unknown_keys:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation}' declares unsupported "
                f"operation mapping key(s): {', '.join(unknown_keys)}."
            )
        handler_method = str(entry.get("handler_method") or f"handle{to_pascal_case(operation)}").strip()
        if not handler_method:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation}' requires handler_method."
            )
        if mode == "canonical":
            canonical_operation = _parse_soap_canonical_operation_mapping(
                entry.get("canonical_operation"),
                interface_name=interface_name,
                operation_name=operation,
                operation_metadata=operation_lookup[operation],
                direction=direction,
            )
        else:
            canonical_operation = None
        parsed[operation] = {
            "operation": operation,
            "mode": mode,
            "handler_method": handler_method,
        }
        if canonical_operation is not None:
            parsed[operation]["canonical_operation"] = canonical_operation
    missing = sorted(operation_names - set(parsed))
    if missing:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' mapping '{mapping_path}' is missing "
            f"operation_mappings for: {', '.join(missing)}."
        )
    return parsed


def _parse_soap_canonical_operation_mapping(
    raw: Any,
    *,
    interface_name: str,
    operation_name: str,
    operation_metadata: dict[str, Any],
    direction: str,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' with mode "
            "canonical requires canonical_operation."
        )
    if direction == "upstream":
        return _parse_inbound_soap_canonical_operation_mapping(
            raw,
            interface_name=interface_name,
            operation_name=operation_name,
            operation_metadata=operation_metadata,
        )
    if direction == "downstream":
        return _parse_downstream_soap_canonical_operation_mapping(
            raw,
            interface_name=interface_name,
            operation_name=operation_name,
            operation_metadata=operation_metadata,
        )
    raise ValueError(
        f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' uses unsupported "
        f"SOAP mapping direction '{direction}'."
    )


def _parse_inbound_soap_canonical_operation_mapping(
    raw: dict[str, Any],
    *,
    interface_name: str,
    operation_name: str,
    operation_metadata: dict[str, Any],
) -> dict[str, Any]:
    allowed_keys = {"kind", "entity", "lookup", "response_mappings", "not_found_fault"}
    unknown_keys = sorted(set(raw) - allowed_keys)
    if unknown_keys:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' declares unsupported "
            f"canonical_operation key(s): {', '.join(unknown_keys)}."
        )
    kind = str(raw.get("kind") or "").strip()
    if kind != "read_by_id":
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' uses unsupported "
            f"canonical_operation.kind '{kind or '<missing>'}'. Only read_by_id is supported."
        )
    entity = str(raw.get("entity") or "").strip()
    if not entity:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' read_by_id "
            "requires canonical_operation.entity."
        )
    lookup = raw.get("lookup")
    if not isinstance(lookup, dict):
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' read_by_id "
            "requires canonical_operation.lookup."
        )
    lookup_allowed = {"field", "request_path"}
    lookup_unknown = sorted(set(lookup) - lookup_allowed)
    if lookup_unknown:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' read_by_id lookup "
            f"declares unsupported key(s): {', '.join(lookup_unknown)}."
        )
    lookup_field = str(lookup.get("field") or "").strip()
    request_path = str(lookup.get("request_path") or "").strip()
    if not lookup_field or not request_path:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' read_by_id lookup "
            "requires field and request_path."
        )
    input_fields = _soap_fields_by_path(operation_metadata.get("input_fields") or [])
    if request_path not in input_fields:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' read_by_id lookup "
            f"references unknown request_path '{request_path}'."
        )
    if not _is_supported_soap_canonical_path(request_path):
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' read_by_id lookup "
            f"request_path '{request_path}' is out of scope. SOAP canonical read_by_id currently "
            "supports flat scalar child or attribute paths like /Root/id or /Root/@id; root text "
            "and nested complex paths are fail-fast."
        )
    response_mappings = raw.get("response_mappings")
    if not isinstance(response_mappings, list) or not response_mappings:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' read_by_id "
            "requires a non-empty response_mappings list."
        )
    output_fields = _soap_fields_by_path(operation_metadata.get("output_fields") or [])
    parsed_response_mappings: list[dict[str, str]] = []
    seen_targets: set[str] = set()
    for index, mapping in enumerate(response_mappings):
        if not isinstance(mapping, dict):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] must be a mapping."
            )
        mapping_allowed = {"source", "target_path"}
        mapping_unknown = sorted(set(mapping) - mapping_allowed)
        if mapping_unknown:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] declares unsupported key(s): {', '.join(mapping_unknown)}."
            )
        source = str(mapping.get("source") or "").strip()
        target_path = str(mapping.get("target_path") or "").strip()
        if not source or not target_path:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] requires source and target_path."
            )
        if target_path not in output_fields:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] references unknown target_path '{target_path}'."
            )
        if not _is_supported_soap_canonical_path(target_path):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] target_path '{target_path}' is out of scope. SOAP "
                "canonical read_by_id currently supports flat scalar child or attribute paths like "
                "/Root/id or /Root/@id; root text and nested complex paths are fail-fast."
            )
        if target_path in seen_targets:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' maps "
                f"response target_path '{target_path}' more than once."
            )
        seen_targets.add(target_path)
        parsed_response_mappings.append({"source": source, "target_path": target_path})
    missing_required = sorted(
        path
        for path, field in output_fields.items()
        if bool(field.get("required")) and path not in seen_targets
    )
    if missing_required:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' read_by_id "
            f"is missing response mappings for required SOAP field(s): {', '.join(missing_required)}."
        )
    not_found_fault = raw.get("not_found_fault")
    parsed_fault: dict[str, str] | None = None
    if not_found_fault is not None:
        if not isinstance(not_found_fault, dict):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' not_found_fault "
                "must be a mapping."
            )
        fault_allowed = {"fault", "message"}
        fault_unknown = sorted(set(not_found_fault) - fault_allowed)
        if fault_unknown:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' not_found_fault "
                f"declares unsupported key(s): {', '.join(fault_unknown)}."
            )
        fault_name = str(not_found_fault.get("fault") or "").strip()
        if not fault_name:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' not_found_fault "
                "requires fault."
            )
        available_faults = {str(fault.get("name")) for fault in operation_metadata.get("faults") or []}
        if fault_name not in available_faults:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' references "
                f"unknown SOAP fault '{fault_name}'."
            )
        parsed_fault = {"fault": fault_name}
        message = str(not_found_fault.get("message") or "").strip()
        if message:
            parsed_fault["message"] = message
    return {
        "kind": "read_by_id",
        "entity": entity,
        "lookup": {"field": lookup_field, "request_path": request_path},
        "response_mappings": parsed_response_mappings,
        **({"not_found_fault": parsed_fault} if parsed_fault else {}),
    }


def _parse_downstream_soap_canonical_operation_mapping(
    raw: dict[str, Any],
    *,
    interface_name: str,
    operation_name: str,
    operation_metadata: dict[str, Any],
) -> dict[str, Any]:
    allowed_keys = {"kind", "entity", "lookup", "request_mappings", "response"}
    unknown_keys = sorted(set(raw) - allowed_keys)
    if unknown_keys:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' declares unsupported "
            f"canonical_operation key(s): {', '.join(unknown_keys)}."
        )
    kind = str(raw.get("kind") or "").strip()
    if kind != "invoke_by_id":
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' uses unsupported "
            f"canonical_operation.kind '{kind or '<missing>'}'. Only invoke_by_id is supported "
            "for downstream SOAP interfaces."
        )
    entity = str(raw.get("entity") or "").strip()
    if not entity:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' invoke_by_id "
            "requires canonical_operation.entity."
        )
    lookup = raw.get("lookup")
    if not isinstance(lookup, dict):
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' invoke_by_id "
            "requires canonical_operation.lookup."
        )
    lookup_allowed = {"field", "request_field"}
    lookup_unknown = sorted(set(lookup) - lookup_allowed)
    if lookup_unknown:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' invoke_by_id lookup "
            f"declares unsupported key(s): {', '.join(lookup_unknown)}."
        )
    lookup_field = str(lookup.get("field") or "").strip()
    request_field = str(lookup.get("request_field") or "").strip()
    if not lookup_field or not request_field:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' invoke_by_id lookup "
            "requires field and request_field."
        )
    if request_field != "id":
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' invoke_by_id lookup "
            f"request_field '{request_field}' is unsupported. The MVP supports only request_field 'id'."
        )

    input_fields = _soap_fields_by_path(operation_metadata.get("input_fields") or [])
    request_mappings = raw.get("request_mappings")
    if not isinstance(request_mappings, list) or not request_mappings:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' invoke_by_id "
            "requires a non-empty request_mappings list."
        )
    parsed_request_mappings: list[dict[str, str]] = []
    seen_request_sources: set[str] = set()
    seen_request_targets: set[str] = set()
    for index, mapping in enumerate(request_mappings):
        if not isinstance(mapping, dict):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"request_mappings[{index}] must be a mapping."
            )
        mapping_allowed = {"source", "target_path"}
        mapping_unknown = sorted(set(mapping) - mapping_allowed)
        if mapping_unknown:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"request_mappings[{index}] declares unsupported key(s): {', '.join(mapping_unknown)}."
            )
        source = str(mapping.get("source") or "").strip()
        target_path = str(mapping.get("target_path") or "").strip()
        if not source or not target_path:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"request_mappings[{index}] requires source and target_path."
            )
        input_field = input_fields.get(target_path)
        if input_field is None:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"request_mappings[{index}] references unknown target_path '{target_path}'."
            )
        if not _is_supported_soap_canonical_path(target_path):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"request_mappings[{index}] target_path '{target_path}' is out of scope. SOAP "
                "canonical invoke_by_id currently supports flat scalar child or attribute paths "
                "like /Root/id or /Root/@id; root text and nested complex paths are fail-fast."
            )
        if input_field.get("repeated"):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"request target_path '{target_path}' is repeated; invoke_by_id supports flat scalar "
                "SOAP request fields only."
            )
        if source in seen_request_sources:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' maps "
                f"request source '{source}' more than once."
            )
        if target_path in seen_request_targets:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' maps "
                f"request target_path '{target_path}' more than once."
            )
        seen_request_sources.add(source)
        seen_request_targets.add(target_path)
        parsed_request_mappings.append({"source": source, "target_path": target_path})
    missing_required_request = sorted(
        path
        for path, field in input_fields.items()
        if bool(field.get("required")) and path not in seen_request_targets
    )
    if missing_required_request:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' invoke_by_id "
            f"is missing request mappings for required SOAP field(s): {', '.join(missing_required_request)}."
        )

    response = raw.get("response")
    if not isinstance(response, dict):
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' invoke_by_id "
            "requires canonical_operation.response."
        )
    response_allowed = {"mode", "response_mappings"}
    response_unknown = sorted(set(response) - response_allowed)
    if response_unknown:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' response "
            f"declares unsupported key(s): {', '.join(response_unknown)}."
        )
    response_mode = str(response.get("mode") or "").strip()
    if response_mode != "return_only":
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' uses unsupported "
            f"response.mode '{response_mode or '<missing>'}'. Only return_only is supported."
        )
    output_fields = _soap_fields_by_path(operation_metadata.get("output_fields") or [])
    response_mappings = response.get("response_mappings")
    if not isinstance(response_mappings, list) or not response_mappings:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' return_only "
            "requires a non-empty response_mappings list."
        )
    parsed_response_mappings: list[dict[str, str]] = []
    seen_response_sources: set[str] = set()
    seen_response_targets: set[str] = set()
    for index, mapping in enumerate(response_mappings):
        if not isinstance(mapping, dict):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] must be a mapping."
            )
        mapping_allowed = {"source_path", "target"}
        mapping_unknown = sorted(set(mapping) - mapping_allowed)
        if mapping_unknown:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] declares unsupported key(s): {', '.join(mapping_unknown)}."
            )
        source_path = str(mapping.get("source_path") or "").strip()
        target = str(mapping.get("target") or "").strip()
        if not source_path or not target:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] requires source_path and target."
            )
        output_field = output_fields.get(source_path)
        if output_field is None:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] references unknown source_path '{source_path}'."
            )
        if not _is_supported_soap_canonical_path(source_path):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] source_path '{source_path}' is out of scope. SOAP "
                "canonical invoke_by_id currently supports flat scalar child or attribute paths "
                "like /Root/id or /Root/@id; root text and nested complex paths are fail-fast."
            )
        if output_field.get("repeated"):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response source_path '{source_path}' is repeated; invoke_by_id supports flat scalar "
                "SOAP response fields only."
            )
        if not _SOAP_RESPONSE_TARGET_RE.match(target):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
                f"response_mappings[{index}] target '{target}' is not a supported response field name."
            )
        if source_path in seen_response_sources:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' maps "
                f"response source_path '{source_path}' more than once."
            )
        if target in seen_response_targets:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' maps "
                f"response target '{target}' more than once."
            )
        seen_response_sources.add(source_path)
        seen_response_targets.add(target)
        parsed_response_mappings.append({"source_path": source_path, "target": target})
    missing_required_response = sorted(
        path
        for path, field in output_fields.items()
        if bool(field.get("required")) and path not in seen_response_sources
    )
    if missing_required_response:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' return_only "
            f"is missing response mappings for required SOAP field(s): {', '.join(missing_required_response)}."
        )
    return {
        "kind": "invoke_by_id",
        "entity": entity,
        "lookup": {"field": lookup_field, "request_field": request_field},
        "request_mappings": parsed_request_mappings,
        "response": {
            "mode": "return_only",
            "response_mappings": parsed_response_mappings,
        },
    }


def _validate_downstream_soap_canonical_operation_mappings(
    *,
    contracts: Iterable[ContractMetadata],
    entities: list[CanonicalEntity],
) -> None:
    entities_by_name = {entity.name: entity for entity in entities}
    for contract in contracts:
        soap_contract = contract.soap_contract
        if contract.type != SOAP_WSDL_CONTRACT_TYPE or not soap_contract:
            continue
        if soap_contract.get("direction") != "downstream":
            continue
        canonical_mappings = {
            operation_name: mapping
            for operation_name, mapping in (soap_contract.get("operation_mappings") or {}).items()
            if (mapping.get("canonical_operation") or {}).get("kind") == "invoke_by_id"
        }
        if not canonical_mappings:
            continue
        operations_by_name = {
            str(operation["name"]): operation for operation in soap_contract.get("operations") or []
        }
        for operation_name, mapping in canonical_mappings.items():
            canonical_operation = mapping.get("canonical_operation") or {}
            entity_name = str(canonical_operation.get("entity") or "")
            entity = entities_by_name.get(entity_name)
            if entity is None:
                raise ValueError(
                    f"Downstream SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                    f"references unknown canonical entity '{entity_name}'."
                )
            fields_by_name = {field.name: field for field in entity.fields}
            id_field = entity_id_field(entity)
            lookup = canonical_operation.get("lookup") or {}
            lookup_field_name = str(lookup.get("field") or "")
            if lookup_field_name not in fields_by_name:
                raise ValueError(
                    f"Downstream SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                    f"references unknown lookup field '{entity.name}.{lookup_field_name}'."
                )
            if lookup_field_name != id_field.name:
                raise ValueError(
                    f"Downstream SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                    f"invoke_by_id lookup field '{lookup_field_name}' must be the persistence ID "
                    f"'{entity.name}.{id_field.name}'. Business-key SOAP lookup requires a future "
                    "explicit uniqueness/finder policy."
                )
            operation = operations_by_name.get(operation_name) or {}
            input_fields = _soap_fields_by_path(operation.get("input_fields") or [])
            for request_mapping in canonical_operation.get("request_mappings") or []:
                source = str(request_mapping.get("source") or "")
                if "." not in source:
                    raise ValueError(
                        f"Downstream SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                        f"request source '{source}' must be an Entity.field path."
                    )
                source_entity_name, source_field_name = source.split(".", 1)
                if source_entity_name != entity.name:
                    raise ValueError(
                        f"Downstream SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                        f"request source '{source}' must reference canonical entity '{entity.name}'."
                    )
                canonical_field = fields_by_name.get(source_field_name)
                if canonical_field is None:
                    raise ValueError(
                        f"Downstream SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                        f"request source references unknown field '{source}'."
                    )
                target_path = str(request_mapping.get("target_path") or "")
                input_field = input_fields.get(target_path)
                if input_field is None:
                    raise ValueError(
                        f"Downstream SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                        f"request target_path '{target_path}' is not declared by the SOAP input element."
                    )
                if not _xml_mapping_types_compatible(
                    direction="downstream",
                    xml_field=input_field,
                    canonical_field=canonical_field,
                ):
                    raise ValueError(
                        f"Downstream SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                        f"cannot map canonical field '{source}' ({canonical_field.type.value}) to SOAP "
                        f"request field '{target_path}' ({_xml_field_type_label(input_field)})."
                    )


def _soap_fields_by_path(fields: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(field.get("path") or ""): dict(field) for field in fields}


def _is_supported_soap_canonical_path(path: str) -> bool:
    parts = path.split("/")
    return len(parts) == 3 and parts[0] == "" and bool(parts[1]) and bool(parts[2])


def _file_layout_note(contract_type: str, layout_spec: FileLayoutSpec) -> str | None:
    if contract_type == "file-fixed-width":
        if layout_spec.is_flat_fixed_width:
            return None
        model = "flat" if layout_spec.is_flat_fixed_width else "enhanced"
        return f"file-layout: fixed-width {model}"
    return f"file-layout: {layout_spec.format}"


def _translate_identity_roles(
    definition: ProjectDefinition,
    *,
    entities: list[CanonicalEntity],
) -> list[IdentityRoleMetadata]:
    if not definition.identity_roles:
        return []

    entity_fields = {
        entity.name: {field.name for field in entity.fields}
        for entity in entities
    }
    translated: list[IdentityRoleMetadata] = []
    for role in definition.identity_roles:
        if role.entity not in entity_fields:
            raise ValueError(
                "identity_roles references unknown entity "
                f"'{role.entity}' for field '{role.field}' ({role.role}). "
                f"Known entities: {sorted(entity_fields)}."
            )
        if role.field not in entity_fields[role.entity]:
            raise ValueError(
                "identity_roles references unknown field "
                f"'{role.entity}.{role.field}' for role '{role.role}'. "
                f"Known fields on {role.entity}: {sorted(entity_fields[role.entity])}."
            )
        translated.append(
            IdentityRoleMetadata(
                entity=role.entity,
                field=role.field,
                role=IdentityRole(role.role),
                mode=IdentityRoleMode(role.mode),
                policy=role.policy,
            )
        )
    return translated


def _load_interface_openapi_spec(
    project_root: Path,
    interface: InterfaceDefinition,
    *,
    notes: list[str],
) -> dict[str, Any] | None:
    if interface.spec_url:
        try:
            spec = fetch_openapi_spec(interface.spec_url)
        except ValueError as exc:
            raise ValueError(
                f"Failed to fetch spec_url for interface '{interface.name}': {exc}"
            ) from exc
        notes.append(f"OpenAPI spec ingested from {interface.spec_url}.")
        return spec
    if interface.spec:
        return _load_yaml(project_root / interface.spec)
    return None


def _load_passthrough_rule_config(
    rule_path: Path,
) -> tuple[list[RoutingRule], list[TransformMapping]]:
    payload = _load_yaml(rule_path)

    routing_payload = payload.get("routing_rules")
    routing_entries: list[dict[str, Any]]
    if routing_payload is None:
        routing_entries = []
    elif isinstance(routing_payload, dict):
        routing_entries = [routing_payload]
    elif isinstance(routing_payload, list):
        routing_entries = routing_payload
    else:
        raise ValueError(f"'routing_rules' in '{rule_path}' must be a mapping or list.")

    routing_rules = [
        RoutingRule(
            route_field=str(entry["route_field"]),
            routes=[
                RouteEntry(match=str(route["match"]), target=str(route["target"]))
                for route in entry.get("routes", [])
            ],
            default_target=str(entry["default_target"]),
        )
        for entry in routing_entries
    ]

    transforms_payload = payload.get("transforms", [])
    if transforms_payload is None:
        transforms_payload = []
    if not isinstance(transforms_payload, list):
        raise ValueError(f"'transforms' in '{rule_path}' must be a list.")

    transform_mappings = [
        TransformMapping(
            source=str(entry["source"]),
            target=str(entry["target"]),
            default=None if entry.get("default") is None else str(entry["default"]),
        )
        for entry in transforms_payload
    ]

    return routing_rules, transform_mappings


def _validate_passthrough_required_request_nullability(
    spec: dict[str, Any],
    *,
    interface_name: str,
) -> None:
    findings = required_nullable_request_fields(spec)
    if not findings:
        return
    operation_name, field_name = findings[0]
    raise ValueError(
        f"Passthrough interface '{interface_name}', operation '{operation_name}', required "
        f"request field '{field_name}' allows null. Required-nullable presence "
        "semantics are not currently representable; remove nullability or make the field optional."
    )


def _validate_passthrough_operation_request_validation_contracts(
    operations: list[CanonicalOperation],
    *,
    interface_name: str,
) -> None:
    if len(operations) < 2:
        return

    baseline_operation = operations[0]
    baseline_contract = _passthrough_request_validation_contract(baseline_operation)
    for operation in operations[1:]:
        if _passthrough_request_validation_contract(operation) == baseline_contract:
            continue
        raise ValueError(
            f"Passthrough interface '{interface_name}' operations "
            f"'{baseline_operation.name}' and '{operation.name}' have different request-validation "
            "contracts. A shared InboundRequestDto cannot enforce both safely; use one validated "
            "request contract per interface."
        )


def _passthrough_request_validation_contract(
    operation: CanonicalOperation,
) -> tuple[tuple[str, str, bool, int | None], ...]:
    constraints: list[tuple[str, str, bool, int | None]] = []
    for request_field in operation.request_fields:
        required = request_field.required or request_field.not_null
        max_length = (
            request_field.max_length
            if request_field.type == CanonicalFieldType.STRING
            else None
        )
        if required or max_length is not None:
            constraints.append(
                (request_field.name, request_field.type.value, required, max_length)
            )
    return tuple(sorted(constraints))


def _validate_passthrough_configuration(
    *,
    routing_rules: list[RoutingRule],
    transform_mappings: list[TransformMapping],
    upstream_request_fields: set[str],
    downstream_request_fields: set[str],
    downstream_targets: set[str],
) -> None:
    if not routing_rules:
        raise ValueError(
            "Passthrough-router manifests require at least one 'routing_rules' section."
        )
    if not transform_mappings:
        raise ValueError(
            "Passthrough-router manifests require at least one entry in 'transforms'."
        )

    for routing_rule in routing_rules:
        if routing_rule.route_field not in upstream_request_fields:
            raise ValueError(
                f"Routing field '{routing_rule.route_field}' is not present in the passthrough "
                "upstream request contract."
            )
        if routing_rule.default_target not in downstream_targets:
            raise ValueError(
                f"Default routing target '{routing_rule.default_target}' does not match any "
                "downstream interface system."
            )
        for route in routing_rule.routes:
            if route.target not in downstream_targets:
                raise ValueError(
                    f"Routing target '{route.target}' does not match any downstream interface system."
                )

    for mapping in transform_mappings:
        if mapping.source not in upstream_request_fields:
            raise ValueError(
                f"Transform source '{mapping.source}' is not present in the passthrough "
                "upstream request contract."
            )
        if mapping.target not in downstream_request_fields:
            raise ValueError(
                f"Transform target '{mapping.target}' is not present in the passthrough "
                "downstream request contracts."
            )


def _enrich_operations_with_openapi(
    operations: list[CanonicalOperation],
    openapi_operations: list[CanonicalOperation],
) -> list[CanonicalOperation]:
    openapi_by_name = {operation.name: operation for operation in openapi_operations}
    enriched: list[CanonicalOperation] = []
    for operation in operations:
        openapi_operation = openapi_by_name.get(operation.name)
        if openapi_operation is None:
            enriched.append(operation)
            continue
        enriched.append(
            operation.model_copy(
                update={
                    "http_method": openapi_operation.http_method or operation.http_method,
                    "path": openapi_operation.path or operation.path,
                    "path_parameters": list(openapi_operation.path_parameters),
                    "operation_parameters": list(openapi_operation.operation_parameters),
                    "read_input_errors": list(openapi_operation.read_input_errors),
                    "has_request_body": openapi_operation.has_request_body,
                    "response_shape": openapi_operation.response_shape or operation.response_shape,
                    "pageable": operation.pageable,
                }
            )
        )
    return enriched


def _infer_relationships(
    entities: list[CanonicalEntity],
    rules: list[CanonicalRule],
) -> list[CanonicalRelationship]:
    """Infer canonical entity relationships from cross-entity existence rules."""

    entity_lookup = {entity.name: entity for entity in entities}
    relationships: list[CanonicalRelationship] = []

    for rule in rules:
        if rule.type != RuleType.CROSS_ENTITY_EXISTS or not rule.target_entity:
            continue

        source_entity = entity_lookup.get(rule.entity_name)
        if source_entity is None:
            continue

        source_field = next(
            (field for field in source_entity.fields if field.name == rule.field_name),
            None,
        )
        if source_field is None:
            source_entity.warnings.append(
                f"Relationship inference skipped: cross-entity-exists rule references "
                f"unknown field '{rule.field_name}'."
            )
            continue

        target_entity = entity_lookup.get(rule.target_entity)
        if target_entity is None:
            source_entity.warnings.append(
                f"Relationship inference skipped: cross-entity-exists rule references "
                f"unknown target entity '{rule.target_entity}'."
            )
            continue

        target_id_field = entity_id_field(target_entity)
        if source_field.type != target_id_field.type:
            source_entity.warnings.append(
                f"Relationship inference skipped: '{source_entity.name}.{source_field.name}' "
                f"(type: {source_field.type.value}) does not match "
                f"'{target_entity.name}.{target_id_field.name}' "
                f"(type: {target_id_field.type.value})."
            )
            continue

        relationships.append(
            CanonicalRelationship(
                source_entity=source_entity.name,
                source_field=source_field.name,
                target_entity=target_entity.name,
                target_field=target_id_field.name,
                relationship_type=RelationshipType.MANY_TO_ONE,
                association_name=_relationship_association_name(source_field.name),
            )
        )

    return relationships


def _propagate_relationship_constraints(
    entities: list[CanonicalEntity],
    relationships: list[CanonicalRelationship],
) -> None:
    """Propagate target ID constraints onto referencing FK fields when absent."""

    entity_lookup = {entity.name: entity for entity in entities}
    for relationship in relationships:
        source_entity = entity_lookup.get(relationship.source_entity)
        target_entity = entity_lookup.get(relationship.target_entity)
        if source_entity is None or target_entity is None:
            continue

        source_field = next(
            (field for field in source_entity.fields if field.name == relationship.source_field),
            None,
        )
        target_field = next(
            (field for field in target_entity.fields if field.name == relationship.target_field),
            None,
        )
        if source_field is None or target_field is None:
            continue

        if target_field.server_generated_id:
            if any(
                (
                    target_field.max_length is not None,
                    target_field.min_length is not None,
                    target_field.pattern is not None,
                )
            ):
                _append_entity_warning(
                    source_entity,
                    (
                        f"{source_field.name}: cross-entity-exists target "
                        f"'{target_entity.name}.{target_field.name}' is server-generated, "
                        "so ID shape constraints were not propagated."
                    ),
                )
            continue

        if source_field.max_length is None:
            source_field.max_length = target_field.max_length
        if source_field.min_length is None:
            source_field.min_length = target_field.min_length
        if source_field.pattern is None:
            source_field.pattern = target_field.pattern


def _warn_on_server_generated_id_rules(
    entities: list[CanonicalEntity],
    rules: list[CanonicalRule],
) -> None:
    entity_lookup = {entity.name: entity for entity in entities}
    for rule in rules:
        if rule.type not in _SERVER_GENERATED_ID_INCOMPATIBLE_RULE_TYPES:
            continue

        entity = entity_lookup.get(rule.entity_name)
        if entity is None:
            continue
        field = next((candidate for candidate in entity.fields if candidate.name == rule.field_name), None)
        if field is None or not field.is_id or not field.server_generated_id:
            continue

        _append_entity_warning(
            entity,
            (
                f"{field.name}: rule '{rule.type.value}' targets a server-generated ID "
                "and was ignored for input/FK constraint generation."
            ),
        )


def _normalize_entity_id_fields(
    entities: list[CanonicalEntity],
    *,
    operations: list[CanonicalOperation],
    mappings: list[FieldMapping],
    identity_overrides: dict[str, str],
) -> None:
    for entity in entities:
        identity_override = identity_overrides.get(entity.name)
        if identity_override is not None:
            candidate_fields = list(entity.fields)
        else:
            candidate_fields = [
                field
                for field in entity.fields
                if field.is_id or field.name.lower().endswith("id")
            ]
        if not candidate_fields:
            continue

        selected_id_field_name, id_warning = _select_entity_id_field_name(
            entity.name,
            candidate_fields,
            operations=operations,
            mappings=mappings,
            identity_override=identity_override,
        )
        if selected_id_field_name is None:
            continue

        # Do not prove a read's identity by inferring it from that same read.
        read_operations = {
            (op.interface_name, op.name) for op in operations if op.http_method == HttpMethod.GET
        }
        independent_id, independent_warning = _select_entity_id_field_name(
            entity.name, candidate_fields,
            operations=[op for op in operations if op.http_method != HttpMethod.GET],
            mappings=[mapping for mapping in mappings if (
                mapping.contract_name, mapping.operation_name
            ) not in read_operations],
            identity_override=identity_override,
        )
        entity.read_identity_verified = (
            independent_id == selected_id_field_name and independent_warning is None
        )

        for entity_field in entity.fields:
            if entity_field.is_id or entity_field.name.lower().endswith("id"):
                entity_field.is_id = entity_field.name == selected_id_field_name

        if id_warning is not None and id_warning not in entity.warnings:
            entity.warnings.append(id_warning)


def _drop_transport_wrapper_persistence_fields(
    *,
    entities: list[CanonicalEntity],
    mappings: list[FieldMapping],
) -> list[FieldMapping]:
    """Remove response-envelope fields from persistence and output surfaces.

    Upstream response mappings are left intact because they are transport/API
    context. The canonical persistent entity and generated handoff/file writers
    should not persist or emit those envelope/page fields as domain state.
    """

    wrapper_targets = {
        mapping.target_path
        for mapping in mappings
        if _is_transport_wrapper_mapping(mapping)
    }
    wrapper_targets.update(
        f"{entity.name}.{field.name}"
        for entity in entities
        for field in entity.fields
        if _is_transport_wrapper_entity_field(field)
    )
    if not wrapper_targets:
        return mappings

    for entity in entities:
        entity.fields = [
            field
            for field in entity.fields
            if f"{entity.name}.{field.name}" not in wrapper_targets
        ]

    return [
        mapping
        for mapping in mappings
        if not (
            mapping.direction
            in {
                MappingDirection.CANONICAL_TO_DOWNSTREAM,
                MappingDirection.CANONICAL_TO_HANDOFF,
            }
            and mapping.source_path in wrapper_targets
        )
    ]


def _is_transport_wrapper_mapping(mapping: FieldMapping) -> bool:
    if mapping.direction != MappingDirection.UPSTREAM_TO_CANONICAL:
        return False
    if ".response." not in mapping.source_path:
        return False
    source_field = mapping.source_path.rsplit(".", 1)[-1]
    target_field = mapping.target_path.rsplit(".", 1)[-1]
    return _is_transport_wrapper_field_name(source_field) and _is_transport_wrapper_field_name(
        target_field
    )


def _is_transport_wrapper_entity_field(field: CanonicalField) -> bool:
    if not _is_transport_wrapper_field_name(field.name):
        return False
    return any(".response." in source_path for source_path in field.source_paths)


def _is_transport_wrapper_field_name(field_name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", field_name.lower())
    return normalized in _TRANSPORT_WRAPPER_FIELD_NAMES


def _apply_id_generation_override(
    *,
    entity: CanonicalEntity,
    override: IdGenerationOverride,
    target_profile: TargetProfile,
) -> list[str]:
    """Apply C9 ID generation metadata after persistence ID selection."""

    warnings: list[str] = []
    id_field = next((field for field in entity.fields if field.is_id), None)
    if id_field is None:
        raise ValueError(
            f"id_generation_overrides: entity '{entity.name}' has no selected "
            "persistence identity field. Run A1 identity selection first or add "
            "an identity_overrides entry."
        )

    if override.field is not None and override.field != id_field.name:
        raise ValueError(
            f"id_generation_overrides: entity '{entity.name}' declares "
            f"field '{override.field}' as the ID guard, but A1/heuristic "
            f"selected '{id_field.name}' as the persistence identity. "
            "Either remove the field guard or update it to match."
        )

    strategy = IdGenerationStrategy(override.strategy)
    is_numeric = id_field.type == CanonicalFieldType.INTEGER
    is_string = id_field.type == CanonicalFieldType.STRING

    if strategy == IdGenerationStrategy.UUID and not is_string:
        raise ValueError(
            f"id_generation_overrides: entity '{entity.name}' declares "
            f"strategy 'uuid' but the persistence ID field '{id_field.name}' "
            f"is type '{id_field.type.value}'. Strategy 'uuid' requires a string ID."
        )

    if strategy in {IdGenerationStrategy.DB_IDENTITY, IdGenerationStrategy.DB_SEQUENCE}:
        if not is_numeric:
            raise ValueError(
                f"id_generation_overrides: entity '{entity.name}' declares "
                f"strategy '{strategy.value}' but the persistence ID field "
                f"'{id_field.name}' is type '{id_field.type.value}'. "
                "Strategies 'db_identity' and 'db_sequence' require a numeric ID "
                "(canonical type 'integer', Java type Long)."
            )
        if not id_field.server_generated_id:
            raise ValueError(
                f"id_generation_overrides: entity '{entity.name}' declares "
                f"strategy '{strategy.value}' (database-generated), but the "
                f"persistence ID field '{id_field.name}' appears in a create "
                "request mapping (caller-supplied). A database-generated ID "
                "must not be required from the caller."
            )
        if target_profile.runtime_database_dependency not in {"h2", "postgresql"}:
            raise ValueError(
                f"id_generation_overrides: strategy '{strategy.value}' is not supported "
                f"for database '{target_profile.runtime_database_dependency}'."
            )

    if strategy == IdGenerationStrategy.UUID and not id_field.server_generated_id:
        warnings.append(
            f"id_generation_overrides: entity '{entity.name}' declares strategy "
            f"'uuid' but the persistence ID field '{id_field.name}' appears in a "
            "create request mapping. The server will generate the UUID; the "
            "caller-provided value will be ignored."
        )

    # C9: explicit id_generation_strategy wins over server_generated_id inference.
    id_field.id_generation_strategy = strategy
    id_field.id_sequence_name = (
        override.sequence_name if strategy == IdGenerationStrategy.DB_SEQUENCE else None
    )
    id_field.server_generated_id = strategy != IdGenerationStrategy.CALLER_SUPPLIED

    return warnings


def _append_entity_warning(entity: CanonicalEntity, warning: str) -> None:
    if warning not in entity.warnings:
        entity.warnings.append(warning)


def _relationship_association_name(source_field_name: str) -> str:
    if source_field_name.endswith("Id") and len(source_field_name) > 2:
        return source_field_name[:-2]
    if source_field_name.lower().endswith("id") and len(source_field_name) > 2:
        return source_field_name[:-2]
    return source_field_name


def _ingest_upstream_interface(
    project_root: Path,
    interface: InterfaceDefinition,
    field_accumulators: OrderedDict[str, _FieldAccumulator],
    *,
    default_entity_name: str,
    collect_sample_fields: bool = True,
    openapi_spec: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> tuple[
    list[CanonicalOperation],
    list[FieldMapping],
    MappingCompletenessReport,
    str,
]:
    samples = _load_upstream_samples(project_root, interface)
    field_hints = _load_upstream_field_hints(
        project_root,
        interface,
        openapi_spec=openapi_spec,
        notes=notes,
    )
    mapping_location = str(project_root / interface.mapping) if interface.mapping else None
    declared_operations = {
        operation_name: {
            sample_kind: sorted(_flatten_sample_field_names(payload))
            for sample_kind, payload in payloads.items()
        }
        for operation_name, payloads in samples.items()
    }

    if interface.mapping:
        mappings, report, lookup, entity_name = build_upstream_mapping_artifacts(
            mapping_path=project_root / interface.mapping,
            interface_name=interface.name,
            declared_operations=declared_operations,
        )
    else:
        mappings, report, lookup, entity_name = _build_inferred_upstream_mappings(
            interface_name=interface.name,
            samples=samples,
            default_entity_name=default_entity_name,
        )
    required_lookup = _build_upstream_required_lookup(mappings)

    operations: list[CanonicalOperation] = []
    for operation_name, payloads in samples.items():
        request_entity: str | None = None
        response_entity: str | None = None
        for sample_kind, payload in payloads.items():
            if collect_sample_fields and sample_kind == "response":
                _auto_include_unmapped_response_sample_fields(
                    interface_name=interface.name,
                    operation_name=operation_name,
                    payload=payload,
                    lookup=lookup,
                    mappings=mappings,
                    report=report,
                    entity_name=entity_name,
                    source_location=mapping_location,
                )
            mapped_entity = _apply_upstream_sample_payload(
                interface_name=interface.name,
                operation_name=operation_name,
                sample_kind=sample_kind,
                payload=payload,
                lookup=lookup,
                field_hints=field_hints,
                source_required_lookup=required_lookup,
                field_accumulators=field_accumulators,
                default_entity_name=entity_name,
                collect_fields=collect_sample_fields,
            )
            if sample_kind == "request":
                request_entity = mapped_entity
                if response_entity is None:
                    response_entity = mapped_entity
            else:
                response_entity = mapped_entity
                if request_entity is None:
                    request_entity = mapped_entity

        _refresh_report_status(report)
        operations.append(
            CanonicalOperation(
                name=operation_name,
                interface_name=interface.name,
                request_entity=request_entity,
                response_entity=response_entity,
                http_method=_infer_http_method_from_name(operation_name),
                pageable=_interface_operation_pageable(interface, operation_name),
            )
        )

    return operations, mappings, report, entity_name


def _ingest_upstream_file_interface(
    project_root: Path,
    interface: InterfaceDefinition,
    *,
    layout_spec: FileLayoutSpec,
    field_accumulators: OrderedDict[str, _FieldAccumulator],
    default_entity_name: str,
) -> tuple[list[CanonicalOperation], list[FieldMapping], MappingCompletenessReport, str]:
    layout_fields = {field.name: field for field in layout_spec.fields}
    issues: list[MappingIssue] = []
    mappings: list[FieldMapping] = []
    entity_name = default_entity_name

    if interface.mapping:
        mapping_payload = _load_yaml(project_root / interface.mapping)
        if mapping_payload.get("direction", "inbound") != "inbound":
            issues.append(
                MappingIssue(
                    contract_name=interface.name,
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    severity=MappingSeverity.ERROR,
                    message="File upstream mapping direction must be inbound.",
                    location=str(project_root / interface.mapping),
                )
            )
        entity_name = str(mapping_payload.get("entity") or entity_name)
        mapped_source_fields: set[str] = set()
        for mapping_payload_entry in mapping_payload.get("field_mappings", []):
            source_field = str(mapping_payload_entry["source"])
            target_path = str(mapping_payload_entry["target"])
            mapped_source_fields.add(source_field)
            if source_field not in layout_fields:
                issues.append(
                    MappingIssue(
                        contract_name=interface.name,
                        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                        severity=MappingSeverity.ERROR,
                        message=f"Mapping source '{source_field}' is not present in file layout.",
                        location=str(project_root / interface.mapping),
                    )
                )
                continue
            mappings.append(
                FieldMapping(
                    contract_name=interface.name,
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    source_path=f"{interface.name}.file.{source_field}",
                    target_path=target_path,
                    source_required=layout_fields[source_field].required,
                    source_location=str(project_root / interface.mapping),
                )
            )
        for field in layout_spec.fields:
            if field.required and field.name not in mapped_source_fields:
                issues.append(
                    MappingIssue(
                        contract_name=interface.name,
                        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                        severity=MappingSeverity.WARNING,
                        message=f"Required layout field '{field.name}' is not mapped to canonical metadata.",
                        location=str(project_root / interface.mapping),
                    )
                )
    else:
        for field in layout_spec.fields:
            target_field_name = _snake_to_camel(field.name)
            target_path = f"{entity_name}.{target_field_name}"
            mappings.append(
                FieldMapping(
                    contract_name=interface.name,
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    source_path=f"{interface.name}.file.{field.name}",
                    target_path=target_path,
                    source_required=field.required,
                    notes=["Inferred inbound file mapping because no explicit mapping file was declared."],
                )
            )
        issues.append(
            MappingIssue(
                contract_name=interface.name,
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                severity=MappingSeverity.WARNING,
                message="No explicit upstream file mapping file declared; inferred field mappings were used.",
            )
        )

    for mapping in mappings:
        layout_field_name = mapping.source_path.rsplit(".", 1)[1]
        layout_field = layout_fields.get(layout_field_name)
        if layout_field is None:
            continue
        mapped_entity_name, canonical_field_name = _split_canonical_path(mapping.target_path)
        accumulator = _ensure_field(
            field_accumulators,
            f"{mapped_entity_name}.{canonical_field_name}",
            field_name=canonical_field_name,
        )
        accumulator.type = _file_layout_canonical_type(layout_field)
        accumulator.required = accumulator.required or layout_field.required
        accumulator.add_source(f"{interface.name}.layout.{layout_field.name}")
        entity_name = mapped_entity_name

    report = MappingCompletenessReport(
        contract_name=interface.name,
        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
        status="complete",
        issues=issues,
    )
    _refresh_report_status(report)
    return [], mappings, report, entity_name


def _ingest_upstream_xml_interface(
    project_root: Path,
    interface: InterfaceDefinition,
    *,
    xml_contract: dict[str, Any],
    field_accumulators: OrderedDict[str, _FieldAccumulator],
    default_entity_name: str,
) -> tuple[list[CanonicalOperation], list[FieldMapping], MappingCompletenessReport, str]:
    xml_fields = _xml_contract_fields_by_name(xml_contract)
    issues: list[MappingIssue] = []
    mappings: list[FieldMapping] = []
    entity_name = default_entity_name

    if not interface.mapping:
        raise ValueError(
            f"XML/XSD upstream interface '{interface.name}' requires an explicit mapping file "
            "before canonical ingest runtime generation."
        )

    mapping_path = project_root / interface.mapping
    mapping_payload = _load_yaml(mapping_path)
    if mapping_payload.get("direction", "inbound") != "inbound":
        issues.append(
            MappingIssue(
                contract_name=interface.name,
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                severity=MappingSeverity.ERROR,
                message="XML/XSD upstream mapping direction must be inbound.",
                location=str(mapping_path),
            )
        )
    entity_name = str(mapping_payload.get("entity") or entity_name)
    mapped_source_fields: set[str] = set()
    for mapping_payload_entry in mapping_payload.get("field_mappings", []):
        source_field = str(mapping_payload_entry["source"])
        target_path = str(mapping_payload_entry["target"])
        mapped_source_fields.add(source_field)
        xml_field = xml_fields.get(source_field)
        if xml_field is None:
            issues.append(
                MappingIssue(
                    contract_name=interface.name,
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    severity=MappingSeverity.ERROR,
                    message=f"Mapping source '{source_field}' is not present in XML/XSD contract.",
                    location=str(mapping_path),
                )
            )
            continue
        mappings.append(
            FieldMapping(
                contract_name=interface.name,
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                source_path=f"{interface.name}.xml.{source_field}",
                target_path=target_path,
                source_required=bool(xml_field.get("required")),
                source_location=str(mapping_path),
            )
        )
    for field_name, xml_field in xml_fields.items():
        if bool(xml_field.get("required")) and field_name not in mapped_source_fields:
            issues.append(
                MappingIssue(
                    contract_name=interface.name,
                    direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                    severity=MappingSeverity.ERROR,
                    message=f"Required XML/XSD field '{field_name}' is not mapped to canonical metadata.",
                    location=str(mapping_path),
                )
            )

    for mapping in mappings:
        xml_field_name = mapping.source_path.rsplit(".", 1)[1]
        xml_field = xml_fields.get(xml_field_name)
        if xml_field is None:
            continue
        mapped_entity_name, canonical_field_name = _split_canonical_path(mapping.target_path)
        accumulator = _ensure_field(
            field_accumulators,
            f"{mapped_entity_name}.{canonical_field_name}",
            field_name=canonical_field_name,
        )
        accumulator.type = _xml_contract_canonical_type(xml_field)
        accumulator.required = accumulator.required or bool(xml_field.get("required"))
        accumulator.add_allowed_values(tuple(str(value) for value in xml_field.get("enum_values") or ()))
        accumulator.add_source(f"{interface.name}.xml.{xml_field_name}")
        entity_name = mapped_entity_name

    report = MappingCompletenessReport(
        contract_name=interface.name,
        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
        status="complete",
        issues=issues,
    )
    _refresh_report_status(report)
    return [], mappings, report, entity_name


def _ingest_downstream_xml_interface(
    project_root: Path,
    interface: InterfaceDefinition,
    *,
    xml_contract: dict[str, Any],
    field_accumulators: OrderedDict[str, _FieldAccumulator],
    default_entity_name: str,
) -> tuple[list[CanonicalOperation], list[FieldMapping], MappingCompletenessReport, str]:
    xml_fields = _xml_contract_fields_by_name(xml_contract)
    available_targets = {
        field_name: bool(field.get("required"))
        for field_name, field in xml_fields.items()
    }

    if not interface.mapping:
        raise ValueError(
            f"XML/XSD downstream interface '{interface.name}' requires an explicit mapping file "
            "before canonical output runtime generation."
        )

    mapping_path = project_root / interface.mapping
    mappings, report, lookup, entity_name = build_output_mapping_artifacts(
        mapping_path=mapping_path,
        contract_name=interface.name,
        direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
        available_targets=available_targets,
    )
    mapping_payload = _load_yaml(mapping_path)
    if mapping_payload.get("direction", "outbound") != "outbound":
        report.issues.append(
            MappingIssue(
                contract_name=interface.name,
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                severity=MappingSeverity.ERROR,
                message="XML/XSD downstream mapping direction must be outbound.",
                location=str(mapping_path),
            )
        )
        _refresh_report_status(report)

    for target_name, source_path in lookup.items():
        xml_field = xml_fields.get(target_name)
        if xml_field is None:
            continue
        entity_name_from_path, canonical_field_name = _split_canonical_path(source_path)
        accumulator = _ensure_field(
            field_accumulators,
            f"{entity_name_from_path}.{canonical_field_name}",
            field_name=canonical_field_name,
        )
        accumulator.type = _xml_contract_canonical_type(xml_field)
        if bool(xml_field.get("required")) and accumulator.default_value is None:
            accumulator.required = True
        accumulator.add_allowed_values(tuple(str(value) for value in xml_field.get("enum_values") or ()))
        accumulator.add_source(f"{interface.name}.xml.{target_name}")

    return [], mappings, report, entity_name or default_entity_name


def _xml_contract_fields_by_name(xml_contract: dict[str, Any]) -> OrderedDict[str, dict[str, Any]]:
    fields: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for xml_field in [*(xml_contract.get("attributes") or []), *(xml_contract.get("fields") or [])]:
        field_name = str(xml_field.get("name") or "")
        if field_name:
            fields[field_name] = dict(xml_field)
    return fields


def _xml_contract_canonical_type(field: dict[str, Any]) -> CanonicalFieldType:
    raw_type = str(field.get("type") or "string").lower()
    if raw_type in {"string", "char", "text"}:
        return CanonicalFieldType.STRING
    if raw_type in {"integer", "int", "long"}:
        return CanonicalFieldType.INTEGER
    if raw_type in {"decimal", "number", "bigdecimal"}:
        return CanonicalFieldType.DECIMAL
    if raw_type in {"date", "localdate"}:
        return CanonicalFieldType.DATE
    if raw_type in {"datetime", "date-time", "timestamp", "localdatetime"}:
        return CanonicalFieldType.DATETIME
    if raw_type in {"boolean", "bool"}:
        return CanonicalFieldType.BOOLEAN
    raise ValueError(
        f"Unsupported XML/XSD field type '{field.get('type')}' for field '{field.get('name')}'."
    )


def _file_layout_canonical_type(field: Any) -> CanonicalFieldType:
    raw_type = (field.type or "string").lower()
    if raw_type in {"string", "char", "text"}:
        return CanonicalFieldType.STRING
    if raw_type in {"integer", "int", "long"}:
        return CanonicalFieldType.INTEGER
    if raw_type in {"decimal", "number", "bigdecimal"}:
        return CanonicalFieldType.DECIMAL
    if raw_type in {"date", "localdate"}:
        return CanonicalFieldType.DATE
    if raw_type in {"datetime", "date-time", "timestamp", "localdatetime"}:
        return CanonicalFieldType.DATETIME
    if raw_type in {"boolean", "bool"}:
        return CanonicalFieldType.BOOLEAN
    raise ValueError(
        f"Unsupported file layout field type '{field.type}' for field '{field.name}'."
    )


def _interface_operation_pageable(interface: InterfaceDefinition, operation_name: str) -> bool:
    for operation in interface.operations:
        if operation.name == operation_name:
            return operation.pageable
    return False


def _auto_include_unmapped_response_sample_fields(
    *,
    interface_name: str,
    operation_name: str,
    payload: dict[str, Any],
    lookup: dict[tuple[str, str, str], str],
    mappings: list[FieldMapping],
    report: MappingCompletenessReport,
    entity_name: str,
    source_location: str | None,
) -> None:
    for field_name, _field_value in _iter_sample_scalar_fields(payload):
        if field_name.startswith("Links.") or field_name.startswith("Meta."):
            continue
        lookup_key = (operation_name, "response", field_name)
        if lookup_key in lookup:
            continue

        canonical_field_name = field_name.rsplit(".", 1)[-1]
        lookup[lookup_key] = f"{entity_name}.{canonical_field_name}"
        mappings.append(
            FieldMapping(
                contract_name=interface_name,
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name=operation_name,
                source_path=f"{interface_name}.{operation_name}.response.{field_name}",
                target_path=f"{entity_name}.{canonical_field_name}",
                source_required=False,
                source_location=source_location,
                notes=[
                    "Auto-included from response sample because no explicit upstream "
                    "mapping was declared for this response field."
                ],
            )
        )
        _replace_unmapped_response_warning(
            report=report,
            interface_name=interface_name,
            operation_name=operation_name,
            field_name=field_name,
            source_location=source_location,
        )


def _flatten_sample_field_names(payload: dict[str, Any]) -> set[str]:
    return {field_name for field_name, _value in _iter_sample_scalar_fields(payload)}


def _iter_sample_scalar_fields(
    payload: dict[str, Any],
    *,
    prefix: str = "",
) -> Iterable[tuple[str, Any]]:
    for field_name, field_value in payload.items():
        if not isinstance(field_name, str):
            continue
        qualified_name = f"{prefix}.{field_name}" if prefix else field_name
        if isinstance(field_value, dict):
            yield from _iter_sample_scalar_fields(field_value, prefix=qualified_name)
            continue
        if isinstance(field_value, list):
            continue
        yield qualified_name, field_value


def _replace_unmapped_response_warning(
    *,
    report: MappingCompletenessReport,
    interface_name: str,
    operation_name: str,
    field_name: str,
    source_location: str | None,
) -> None:
    original_message = (
        f"Sample field '{field_name}' in operation '{operation_name}' response "
        "is not explicitly mapped."
    )
    report.issues = [
        issue for issue in report.issues if issue.message != original_message
    ]
    report.issues.append(
        MappingIssue(
            contract_name=interface_name,
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            severity=MappingSeverity.WARNING,
            message=(
                f"Sample field '{field_name}' in operation '{operation_name}' response "
                "auto-included in canonical model; add an explicit mapping to silence "
                "this warning."
            ),
            location=source_location,
        )
    )


def _ingest_downstream_interface(
    project_root: Path,
    interface: InterfaceDefinition,
    field_accumulators: OrderedDict[str, _FieldAccumulator],
    *,
    default_entity_name: str,
) -> tuple[list[CanonicalOperation], list[FieldMapping], MappingCompletenessReport, str]:
    if interface.spec and interface.type in FILE_CONTRACT_TYPES:
        layout_spec = load_file_layout_spec(project_root / interface.spec, contract_type=interface.type)
        layout_fields = [
            {
                "name": field.name,
                "required": field.required,
                **({"length": field.length} if field.length is not None else {}),
            }
            for field in layout_spec.fields
        ]
    else:
        spec = _load_yaml(project_root / interface.spec) if interface.spec else {}
        layout_fields = spec.get("fields", [])
    available_targets = {
        field_definition["name"]: bool(field_definition.get("required", True))
        for field_definition in layout_fields
    }

    if interface.mapping:
        mappings, report, lookup, entity_name = build_output_mapping_artifacts(
            mapping_path=project_root / interface.mapping,
            contract_name=interface.name,
            direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
            available_targets=available_targets,
        )
    else:
        mappings, report, lookup, entity_name = _build_inferred_output_mappings(
            contract_name=interface.name,
            direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
            target_names=list(available_targets),
            required_targets=available_targets,
            default_entity_name=default_entity_name,
        )

    # B6: keep fixed-width layout widths on output mappings so the generated
    # file writer can apply contract-driven padding and truncation without
    # leaking presentation widths into canonical schema constraints.
    width_by_field: dict[str, int] = {
        field_definition["name"]: int(field_definition["length"])
        for field_definition in layout_fields
        if "length" in field_definition
    }
    for mapping in mappings:
        target_field_name = mapping.target_path.rsplit(".", 1)[1]
        if target_field_name in width_by_field:
            mapping.layout_width = width_by_field[target_field_name]

    for field_definition in layout_fields:
        target_name = field_definition["name"]
        source_path = lookup.get(target_name)
        if source_path is None:
            continue
        entity_name_from_path, canonical_field_name = _split_canonical_path(source_path)
        accumulator = _ensure_field(
            field_accumulators,
            f"{entity_name_from_path}.{canonical_field_name}",
            field_name=canonical_field_name,
        )
        # fixed-width layout "length" is a file-format presentation constraint
        # (padding/truncation width in the output file). It must NOT set canonical max_length,
        # which drives DB column width (VARCHAR) and UI form maxlength. These are separate concerns.
        # The layout length is used only in AccountEodHandoffFileWriter for byte-level formatting.
        # accumulator.merge_length(field_definition.get("length"))  — intentionally removed
        # Promote required=True from the downstream layout only when no default exists;
        # a default makes the field effectively optional at the API boundary.
        if field_definition.get("required") and accumulator.default_value is None:
            accumulator.required = True
        accumulator.add_source(f"{interface.name}.layout.{target_name}")

    entity_name = entity_name or default_entity_name
    operations = [
        CanonicalOperation(
            name=f"emit{entity_name}EodHandoff",
            interface_name=interface.name,
            request_entity=entity_name,
            response_entity=None,
        )
    ]
    return operations, mappings, report, entity_name


def _ingest_data_handoff(
    project_root: Path,
    handoff: DataHandoffDefinition,
    field_accumulators: OrderedDict[str, _FieldAccumulator],
    *,
    default_entity_name: str,
    validated_ddl: ValidatedStagingDdl,
) -> tuple[
    list[CanonicalOperation],
    list[FieldMapping],
    MappingCompletenessReport,
    str,
    RunSemanticsMetadata | None,
]:
    table_columns = _validated_sql_table_schema(validated_ddl)
    available_targets = {
        column_name: bool(column["required"]) for column_name, column in table_columns.items()
    }
    mappable_targets = {
        column_name: required
        for column_name, required in available_targets.items()
        if staging_operational_column_role(column_name) is None
    }

    if handoff.mapping:
        mappings, report, lookup, entity_name = build_output_mapping_artifacts(
            mapping_path=project_root / handoff.mapping,
            contract_name=handoff.name,
            direction=MappingDirection.CANONICAL_TO_HANDOFF,
            available_targets=mappable_targets,
        )
    else:
        mappings, report, lookup, entity_name = _build_inferred_output_mappings(
            contract_name=handoff.name,
            direction=MappingDirection.CANONICAL_TO_HANDOFF,
            target_names=list(mappable_targets),
            required_targets=mappable_targets,
            default_entity_name=default_entity_name,
        )

    for target_name, source_path in lookup.items():
        column = table_columns.get(target_name)
        if column is None:
            continue
        entity_name_from_path, canonical_field_name = _split_canonical_path(source_path)
        field_key = f"{entity_name_from_path}.{canonical_field_name}"
        field_already_exists = field_key in field_accumulators
        accumulator = _ensure_field(field_accumulators, field_key, field_name=canonical_field_name)
        column_type = column["type"]
        if field_already_exists and accumulator.type != column_type:
            if _can_promote_string_to_temporal_contract_type(
                field_name=canonical_field_name,
                existing_type=accumulator.type,
                contract_type=column_type,
            ):
                accumulator.type = column_type
                _apply_temporal_format_from_contract(accumulator, column_type)
            else:
                report.issues.append(
                    MappingIssue(
                        contract_name=handoff.name,
                        direction=MappingDirection.CANONICAL_TO_HANDOFF,
                        severity=MappingSeverity.ERROR,
                        message=(
                            f"Type conflict for field '{canonical_field_name}': upstream declares "
                            f"'{accumulator.type.value}' but staging table '{handoff.name}' declares "
                            f"'{column_type.value}'."
                        ),
                        location=str(project_root / handoff.mapping) if handoff.mapping else str(project_root / handoff.spec),
                    )
                )
        else:
            accumulator.type = column_type
            _apply_temporal_format_from_contract(accumulator, column_type)
        if column["required"] and accumulator.default_value is None:
            accumulator.required = True
        # Staging-table VARCHAR widths are downstream storage constraints, not
        # upstream input limits. In particular, identifier references such as
        # borrowerId/customerId are often UUIDs in the generated app even when
        # the staging contract is narrower (for example VARCHAR(20)); we keep
        # the warning below but do not let the staging width truncate the
        # canonical/UI constraint for *Id fields.
        if not canonical_field_name.endswith("Id"):
            accumulator.merge_length(column["max_length"])
        accumulator.add_source(f"{handoff.name}.{target_name}")

        # warn when a UUID ID field maps to a VARCHAR column too narrow to
        # hold a 36-char UUID. The DDL is emitted verbatim (contract fidelity); this warning
        # surfaces the mismatch so the contract owner can widen the column in the DDL spec.
        if (
            column_type == CanonicalFieldType.STRING
            and column["max_length"] is not None
            and column["max_length"] < 36
            and canonical_field_name.endswith("Id")
        ):
            report.issues.append(
                MappingIssue(
                    contract_name=handoff.name,
                    direction=MappingDirection.CANONICAL_TO_HANDOFF,
                    severity=MappingSeverity.WARNING,
                    message=(
                        f"Staging column '{target_name}' in table '{handoff.name}' is "
                        f"VARCHAR({column['max_length']}), which may be too narrow for a "
                        f"36-char UUID value mapped from '{source_path}'. "
                        f"Consider widening to VARCHAR(36) in the DDL spec."
                    ),
                    location=str(project_root / handoff.spec),
                )
            )

    _refresh_report_status(report)
    entity_name = entity_name or default_entity_name
    run_semantics = _translate_run_semantics(
        handoff=handoff,
        validated_ddl=validated_ddl,
        mapping_lookup=lookup,
        entity_name=entity_name,
    )
    operations = [
        CanonicalOperation(
            name=f"stage{entity_name}ForEod",
            interface_name=handoff.name,
            request_entity=entity_name,
            response_entity=None,
        )
    ]
    return operations, mappings, report, entity_name, run_semantics


def _translate_run_semantics(
    *,
    handoff: DataHandoffDefinition,
    validated_ddl: ValidatedStagingDdl,
    mapping_lookup: dict[str, str],
    entity_name: str,
) -> RunSemanticsMetadata | None:
    definition = handoff.run_semantics
    if definition is None:
        return None

    columns_by_key = {column.name.lower(): column for column in validated_ddl.columns}
    run_id_columns = [
        column
        for column in validated_ddl.columns
        if staging_operational_column_role(column.name) == "run_id"
    ]
    errors: list[str] = []
    if len(run_id_columns) != 1:
        names = ", ".join(column.name for column in run_id_columns) or "none"
        errors.append(
            "exactly one recognized physical run-ID column is required "
            f"(run_id or eod_run_id); found {names}"
        )
    elif not run_id_columns[0].required:
        errors.append(
            f"run-ID column '{run_id_columns[0].name}' must be NOT NULL"
        )
    elif run_id_columns[0].raw_type not in {"CHAR", "TEXT", "VARCHAR"}:
        errors.append(
            f"run-ID column '{run_id_columns[0].name}' must use a string-compatible SQL "
            f"type (CHAR, TEXT, or VARCHAR); found {run_id_columns[0].raw_type}"
        )

    mapped_targets = {name.lower() for name in mapping_lookup}
    normalized_dedup_key: list[str] = []
    for declared_name in definition.dedup_key:
        column = columns_by_key.get(declared_name.lower())
        if column is None:
            errors.append(f"dedup column '{declared_name}' does not exist in the staging DDL")
            continue
        normalized_dedup_key.append(column.name)
        role = staging_operational_column_role(column.name)
        if role is not None:
            errors.append(
                f"dedup column '{column.name}' is operational ({role}) and cannot identify "
                "canonical rows"
            )
        if not column.required:
            errors.append(f"dedup column '{column.name}' must be NOT NULL")
        if column.name.lower() not in mapped_targets:
            errors.append(f"dedup column '{column.name}' must have a canonical-to-handoff mapping")
    if errors:
        raise ValueError(
            f"Invalid run_semantics for staging handoff '{handoff.name}': "
            + "; ".join(errors)
        )

    return RunSemanticsMetadata(
        run_id=definition.run_id,
        restart=definition.restart,
        dedup_key=normalized_dedup_key,
        internal_schema_id=definition.internal_schema_id,
        physical_run_id_column=run_id_columns[0].name,
        physical_run_id_max_length=run_id_columns[0].max_length,
        entity_name=entity_name,
    )


def _validate_run_semantics_type_compatibility(
    *,
    contracts: list[ContractMetadata],
    mappings: list[FieldMapping],
    canonical_types_before_handoffs: dict[str, CanonicalFieldType],
    staging_column_types_by_contract: dict[str, dict[str, CanonicalFieldType]],
) -> None:
    observations_by_source: dict[
        str, list[tuple[str, str, CanonicalFieldType]]
    ] = {}
    mappings_by_contract_target: dict[tuple[str, str], FieldMapping] = {}
    for mapping in mappings:
        if mapping.direction != MappingDirection.CANONICAL_TO_HANDOFF:
            continue
        contract_columns = staging_column_types_by_contract.get(mapping.contract_name)
        if contract_columns is None:
            continue
        target_name = mapping.target_path.rsplit(".", 1)[-1]
        target_key = target_name.lower()
        column_type = contract_columns.get(target_key)
        if column_type is None:
            continue
        mappings_by_contract_target[(mapping.contract_name, target_key)] = mapping
        observations_by_source.setdefault(mapping.source_path, []).append(
            (mapping.contract_name, target_name, column_type)
        )

    for contract in contracts:
        run_semantics = contract.run_semantics
        if run_semantics is None:
            continue
        errors: list[str] = []
        for dedup_column in run_semantics.dedup_key:
            mapping = mappings_by_contract_target.get(
                (contract.name, dedup_column.lower())
            )
            if mapping is None:
                # The local S1 validation already reports unmapped dedup columns.
                continue
            observations = observations_by_source.get(mapping.source_path, [])
            staging_types = {observation[2] for observation in observations}
            canonical_type = canonical_types_before_handoffs.get(mapping.source_path)
            _, field_name = _split_canonical_path(mapping.source_path)
            compatible_with_canonical = (
                canonical_type is None
                or len(staging_types) != 1
                or canonical_type in staging_types
                or _can_promote_string_to_temporal_contract_type(
                    field_name=field_name,
                    existing_type=canonical_type,
                    contract_type=next(iter(staging_types)),
                )
            )
            if len(staging_types) <= 1 and compatible_with_canonical:
                continue
            details = [
                f"{handoff_name}.{target_name}={field_type.value}"
                for handoff_name, target_name, field_type in sorted(
                    observations,
                    key=lambda item: (item[0], item[1], item[2].value),
                )
            ]
            if canonical_type is not None:
                details.insert(0, f"canonical-before-handoffs={canonical_type.value}")
            errors.append(
                f"dedup column '{dedup_column}' maps to '{mapping.source_path}' with an "
                "order-independent canonical/staging type compatibility error "
                f"({', '.join(details)})"
            )
        if errors:
            raise ValueError(
                f"Invalid run_semantics for staging handoff '{contract.name}': "
                + "; ".join(errors)
            )


def _validate_run_semantics_file_output_jobs(
    *,
    contracts: list[ContractMetadata],
    mappings: list[FieldMapping],
) -> None:
    downstream_file_contracts = {
        contract.name
        for contract in contracts
        if contract.type in FILE_CONTRACT_TYPES
    }
    for contract in contracts:
        run_semantics = contract.run_semantics
        if run_semantics is None:
            continue
        entity_prefix = f"{run_semantics.entity_name}."
        conflicting_files = sorted(
            {
                mapping.contract_name
                for mapping in mappings
                if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
                and mapping.contract_name in downstream_file_contracts
                and mapping.source_path.startswith(entity_prefix)
            }
        )
        if conflicting_files:
            raise ValueError(
                f"Invalid run_semantics for staging handoff '{contract.name}': entity "
                f"'{run_semantics.entity_name}' shares its EOD job with downstream file "
                f"output(s) {', '.join(conflicting_files)}. M5a v1 requires staging-only jobs; "
                "file output for a different entity remains supported."
            )


def _can_promote_string_to_temporal_contract_type(
    *,
    field_name: str,
    existing_type: CanonicalFieldType,
    contract_type: CanonicalFieldType,
) -> bool:
    if existing_type != CanonicalFieldType.STRING:
        return False
    if contract_type == CanonicalFieldType.DATE:
        return _looks_like_date_field_name(field_name)
    if contract_type == CanonicalFieldType.DATETIME:
        return _looks_like_datetime_field_name(field_name)
    return False


def _apply_temporal_format_from_contract(
    accumulator: _FieldAccumulator,
    contract_type: CanonicalFieldType,
) -> None:
    if contract_type == CanonicalFieldType.DATE:
        accumulator.format = accumulator.format or "date"
    elif contract_type == CanonicalFieldType.DATETIME:
        accumulator.format = accumulator.format or "date-time"


def _looks_like_date_field_name(field_name: str) -> bool:
    normalized = field_name.lower().replace("_", "")
    return normalized.endswith("date") and not normalized.endswith("datetime")


def _looks_like_datetime_field_name(field_name: str) -> bool:
    normalized = field_name.lower().replace("_", "")
    return normalized.endswith("datetime") or normalized.endswith("timestamp")


def _apply_canonical_rules(
    rules: list[CanonicalRule],
    field_accumulators: OrderedDict[str, _FieldAccumulator],
) -> None:
    for rule in rules:
        accumulator = _ensure_field(
            field_accumulators,
            f"{rule.entity_name}.{rule.field_name}",
            field_name=rule.field_name,
        )
        accumulator.add_source(rule.source_path)
        if rule.type == RuleType.ALLOWED_VALUES:
            accumulator.add_allowed_values(rule.values)
        elif rule.type == RuleType.DEFAULT:
            accumulator.default_value = rule.value
            accumulator.required = False
        elif rule.type == RuleType.MAX_LENGTH:
            accumulator.merge_length(rule.max_length)
        elif rule.type == RuleType.MIN_LENGTH:
            accumulator.merge_min_length(rule.min_length)
        elif rule.type == RuleType.PATTERN:
            accumulator.merge_pattern(rule.pattern)
        elif rule.type == RuleType.RANGE:
            accumulator.merge_range_min(rule.range_min)
            accumulator.merge_range_max(rule.range_max)
        elif rule.type == RuleType.NOT_NULL:
            accumulator.not_null = True
            if accumulator.default_value is None:
                accumulator.required = True
        elif rule.type == RuleType.FORMAT:
            accumulator.format = rule.format
            if rule.format == "iso-4217":
                accumulator.merge_length(3)


def _ensure_field(
    field_accumulators: OrderedDict[str, _FieldAccumulator],
    field_key: str,
    *,
    field_name: str | None = None,
) -> _FieldAccumulator:
    if field_key not in field_accumulators:
        field_accumulators[field_key] = _FieldAccumulator(
            name=field_name if field_name is not None else field_key
        )
    return field_accumulators[field_key]


def _merge_canonical_field(existing: CanonicalField, incoming: CanonicalField) -> None:
    for value in incoming.allowed_values:
        if value not in existing.allowed_values:
            existing.allowed_values.append(value)

    if incoming.not_null:
        existing.not_null = True

    if (
        incoming.required
        and incoming.default_value is None
        and existing.default_value is None
    ):
        existing.required = True

    if incoming.default_value is not None and existing.default_value is None:
        existing.default_value = incoming.default_value
        existing.required = False

    if incoming.max_length is not None:
        if existing.max_length is None:
            existing.max_length = incoming.max_length
        else:
            existing.max_length = min(existing.max_length, incoming.max_length)

    if incoming.min_length is not None:
        if existing.min_length is None:
            existing.min_length = incoming.min_length
        else:
            existing.min_length = max(existing.min_length, incoming.min_length)

    if incoming.pattern is not None and existing.pattern is None:
        existing.pattern = incoming.pattern

    if incoming.range_min is not None:
        if existing.range_min is None:
            existing.range_min = incoming.range_min
        else:
            existing.range_min = max(existing.range_min, incoming.range_min)

    if incoming.range_max is not None:
        if existing.range_max is None:
            existing.range_max = incoming.range_max
        else:
            existing.range_max = min(existing.range_max, incoming.range_max)

    if incoming.format is not None and existing.format is None:
        existing.format = incoming.format

    for source_path in incoming.source_paths:
        if source_path not in existing.source_paths:
            existing.source_paths.append(source_path)


def _apply_upstream_sample_payload(
    *,
    interface_name: str,
    operation_name: str,
    sample_kind: str,
    payload: dict[str, Any],
    lookup: dict[tuple[str, str, str], str],
    field_hints: dict[str, dict[str, dict[str, _UpstreamFieldHint]]],
    source_required_lookup: dict[tuple[str, str, str], bool],
    field_accumulators: OrderedDict[str, _FieldAccumulator],
    default_entity_name: str,
    collect_fields: bool,
) -> str:
    entity_name = default_entity_name
    for field_name, value in _iter_sample_scalar_fields(payload):
        canonical_path = lookup.get((operation_name, sample_kind, field_name))
        if canonical_path is None:
            continue
        entity_name, canonical_field_name = _split_canonical_path(canonical_path)
        if not collect_fields:
            continue
        accumulator = _ensure_field(
            field_accumulators,
            f"{entity_name}.{canonical_field_name}",
            field_name=canonical_field_name,
        )
        field_hint = field_hints.get(operation_name, {}).get(sample_kind, {}).get(field_name)
        if field_hint is not None:
            accumulator.type = field_hint.type
            accumulator.format = field_hint.format
            accumulator.merge_length(field_hint.max_length)
            accumulator.add_allowed_values(field_hint.allowed_values)
        else:
            accumulator.type = _infer_canonical_type(value)
        accumulator.add_source(f"{interface_name}.{sample_kind}.{field_name}")
        if field_hint is not None:
            if field_hint.required:
                accumulator.required = True
        elif source_required_lookup.get((operation_name, sample_kind, field_name), False):
            accumulator.required = True
        # ID ownership inference (Phase 1a): if the id field appears in the CREATE
        # request body the client is supplying the id — mark accordingly so the
        # emitter omits @GeneratedValue.  Restricted to create-style operation
        # names so that update request samples (which always carry the id) do not
        # incorrectly flag the id as client-supplied on create.
        if (
            sample_kind == "request"
            and _is_entity_id_field(entity_name, canonical_field_name)
            and _is_create_operation_name(operation_name)
        ):
            accumulator.client_supplied_id = True
    return entity_name


def _load_upstream_samples(
    project_root: Path,
    interface: InterfaceDefinition,
) -> OrderedDict[str, OrderedDict[str, dict[str, Any]]]:
    samples: OrderedDict[str, OrderedDict[str, dict[str, Any]]] = OrderedDict()

    if interface.operations:
        for operation in interface.operations:
            payloads: OrderedDict[str, dict[str, Any]] = OrderedDict()
            if operation.request_sample:
                payloads["request"] = _load_json(project_root / operation.request_sample)
            if operation.response_sample:
                payloads["response"] = _load_json(project_root / operation.response_sample)
            samples[operation.name] = payloads
        return samples

    for sample_path in interface.samples:
        path = project_root / sample_path
        operation_name, sample_kind = _infer_sample_operation(path, "Record")
        payloads = samples.setdefault(operation_name, OrderedDict())
        payloads[sample_kind] = _load_json(path)
    return samples


def _build_inferred_upstream_mappings(
    *,
    interface_name: str,
    samples: OrderedDict[str, OrderedDict[str, dict[str, Any]]],
    default_entity_name: str,
) -> tuple[list[FieldMapping], MappingCompletenessReport, dict[tuple[str, str, str], str], str]:
    mappings: list[FieldMapping] = []
    lookup: dict[tuple[str, str, str], str] = {}
    for operation_name, payloads in samples.items():
        for sample_kind, payload in payloads.items():
            for field_name in payload:
                target_path = f"{default_entity_name}.{field_name}"
                lookup[(operation_name, sample_kind, field_name)] = target_path
                mappings.append(
                    FieldMapping(
                        contract_name=interface_name,
                        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                        operation_name=operation_name,
                        source_path=f"{interface_name}.{operation_name}.{sample_kind}.{field_name}",
                        target_path=target_path,
                        source_required=False,
                        notes=["Inferred mapping because no explicit interface mapping file was declared."],
                    )
                )

    report = MappingCompletenessReport(
        contract_name=interface_name,
        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
        status="warning",
        issues=[
            MappingIssue(
                contract_name=interface_name,
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                severity=MappingSeverity.WARNING,
                message="No explicit upstream mapping file declared; inferred field mappings were used.",
            )
        ],
    )
    return mappings, report, lookup, default_entity_name


def _build_inferred_output_mappings(
    *,
    contract_name: str,
    direction: MappingDirection,
    target_names: list[str],
    required_targets: dict[str, bool],
    default_entity_name: str,
) -> tuple[list[FieldMapping], MappingCompletenessReport, dict[str, str], str]:
    mappings: list[FieldMapping] = []
    lookup: dict[str, str] = {}
    for target_name in target_names:
        source_path = f"{default_entity_name}.{_snake_to_camel(target_name)}"
        lookup[target_name] = source_path
        mappings.append(
            FieldMapping(
                contract_name=contract_name,
                direction=direction,
                source_path=source_path,
                target_path=f"{contract_name}.{target_name}",
                notes=["Inferred mapping because no explicit contract mapping file was declared."],
            )
        )

    report = MappingCompletenessReport(
        contract_name=contract_name,
        direction=direction,
        status="warning",
        issues=[
            MappingIssue(
                contract_name=contract_name,
                direction=direction,
                severity=MappingSeverity.WARNING,
                message="No explicit contract mapping file declared; inferred field mappings were used.",
            )
        ],
    )
    return mappings, report, lookup, default_entity_name


def _collect_interface_sample_paths(interface: InterfaceDefinition) -> list[str]:
    sample_paths: list[str] = []
    if interface.sample:
        sample_paths.append(interface.sample)
    for operation in interface.operations:
        if operation.request_sample and operation.request_sample not in sample_paths:
            sample_paths.append(operation.request_sample)
        if operation.response_sample and operation.response_sample not in sample_paths:
            sample_paths.append(operation.response_sample)

    for sample in interface.samples:
        if sample not in sample_paths:
            sample_paths.append(sample)

    return sample_paths


def _infer_sample_operation(path: Path, default_entity_name: str) -> tuple[str, str]:
    match = re.match(r"sample-(?P<name>.+)-(?P<kind>request|response)\.json", path.name)
    if not match:
        return f"process{default_entity_name}", "request"

    raw_name = match.group("name")
    kind = match.group("kind")
    operation = _hyphen_to_camel(raw_name)
    return operation, kind


def _infer_canonical_type(value: Any) -> CanonicalFieldType:
    if isinstance(value, bool):
        return CanonicalFieldType.BOOLEAN
    if isinstance(value, int):
        return CanonicalFieldType.INTEGER
    if isinstance(value, float):
        return CanonicalFieldType.DECIMAL
    if isinstance(value, str):
        if _ISO_DATE_RE.fullmatch(value):
            return CanonicalFieldType.DATE
        if _ISO_DATETIME_RE.fullmatch(value):
            return CanonicalFieldType.DATETIME
    return CanonicalFieldType.STRING


def _load_upstream_field_hints(
    project_root: Path,
    interface: InterfaceDefinition,
    *,
    openapi_spec: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> dict[str, dict[str, dict[str, _UpstreamFieldHint]]]:
    spec = openapi_spec
    if spec is None and interface.spec is not None:
        spec = _load_yaml(project_root / interface.spec)

    if spec is None:
        if interface.spec_url and notes is not None:
            warning = (
                f"OpenAPI field hints unavailable for interface '{interface.name}'; "
                "falling back to sample type inference."
            )
            if (
                warning not in notes
                and not any(note.startswith("spec_url fetch failed:") for note in notes)
            ):
                notes.append(warning)
        return {}
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return {}

    hints: dict[str, dict[str, dict[str, _UpstreamFieldHint]]] = {}
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for operation_item in path_item.values():
            if not isinstance(operation_item, dict):
                continue
            operation_name = operation_item.get("operationId")
            if not isinstance(operation_name, str) or not operation_name:
                continue
            operation_hints = hints.setdefault(operation_name, {})

            request_schema = (
                operation_item.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            if isinstance(request_schema, dict):
                operation_hints["request"] = _schema_field_hints(request_schema)

            responses = operation_item.get("responses", {})
            if not isinstance(responses, dict):
                continue
            for response in responses.values():
                if not isinstance(response, dict):
                    continue
                response_schema = (
                    response.get("content", {})
                    .get("application/json", {})
                    .get("schema", {})
                )
                if isinstance(response_schema, dict):
                    operation_hints["response"] = _schema_field_hints(response_schema)
                    break

    return hints


def _schema_field_hints(schema: dict[str, Any]) -> dict[str, _UpstreamFieldHint]:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return {}

    required_fields = set(schema.get("required", []))
    hints: dict[str, _UpstreamFieldHint] = {}
    for field_name, property_schema in properties.items():
        if not isinstance(property_schema, dict):
            continue
        hints[field_name] = _UpstreamFieldHint(
            type=openapi_type_to_canonical_type(
                property_schema.get("type"),
                property_schema.get("format"),
            ),
            required=field_name in required_fields,
            format=property_schema.get("format"),
            max_length=property_schema.get("maxLength"),
            allowed_values=tuple(property_schema.get("enum", [])),
        )
    return hints


def _build_upstream_required_lookup(
    mappings: list[FieldMapping],
) -> dict[tuple[str, str, str], bool]:
    lookup: dict[tuple[str, str, str], bool] = {}
    for mapping in mappings:
        if mapping.operation_name is None:
            continue
        _, _, sample_kind, field_name = mapping.source_path.split(".", 3)
        lookup[(mapping.operation_name, sample_kind, field_name)] = mapping.source_required
    return lookup


def _resolve_system_name(
    explicit_system: str | None,
    interface_name: str,
    *,
    fallback: str,
) -> str:
    if explicit_system:
        return explicit_system
    return _derive_system_name(interface_name, fallback=fallback)


def _derive_system_name(interface_name: str, *, fallback: str) -> str:
    prefix = interface_name.split("-", 1)[0].strip()
    if not prefix:
        return fallback
    return prefix.upper()


def _derive_primary_entity_name(
    definition: ProjectDefinition,
    *,
    entity_names: Iterable[str],
) -> str:
    for entity_name in entity_names:
        if entity_name:
            return entity_name
    singular = (
        definition.bounded_context[:-1]
        if definition.bounded_context.endswith("s")
        else definition.bounded_context
    )
    return singular[:1].upper() + singular[1:]


def _is_entity_id_field(entity_name: str, field_name: str) -> bool:
    entity_lower = entity_name.lower()
    field_lower = field_name.lower()
    return field_lower.endswith("id") and entity_lower in field_lower


def _select_entity_id_field_name(
    entity_name: str,
    field_accumulators: list[_FieldAccumulator | CanonicalField],
    *,
    operations: list[CanonicalOperation],
    mappings: list[FieldMapping],
    identity_override: str | None = None,
) -> tuple[str | None, str | None]:
    if identity_override is not None:
        field_names = {acc.name for acc in field_accumulators}
        if identity_override not in field_names:
            raise ValueError(
                f"identity_overrides: entity '{entity_name}' declares "
                f"persistence_id '{identity_override}' but no such field exists. "
                f"Available fields: {sorted(field_names)}"
            )
        return identity_override, None

    candidates = [
        acc.name
        for acc in field_accumulators
        if acc.name.lower().endswith("id") or getattr(acc, "is_id", False)
    ]
    if not candidates:
        return None, None
    if len(candidates) == 1:
        _validate_event_identity_selection(
            entity_name=entity_name,
            selected_id_field_name=candidates[0],
            operations=[
                operation
                for operation in operations
                if operation.request_entity == entity_name or operation.response_entity == entity_name
            ],
            mappings=mappings,
        )
        return candidates[0], None

    operation_methods = {
        (operation.interface_name, operation.name): operation.http_method
        for operation in operations
    }
    relevant_operations = [
        operation
        for operation in operations
        if operation.request_entity == entity_name or operation.response_entity == entity_name
    ]
    last_entity_token = _camel_tokens(entity_name)[-1].lower()
    entity_lower = entity_name.lower()

    def score(field_name: str) -> tuple[int, int, int, int, int, int, int, int]:
        field_stem = field_name[:-2].lower()
        normalized_field_name = field_name.lower()
        has_get_request_mapping = False
        matches_terminal_path_param_exactly = False
        matches_terminal_resource_id_hint = False
        appears_in_create_response = False
        appears_in_create_request = False
        for operation in relevant_operations:
            terminal_path_param = _terminal_path_parameter_name(operation)
            if terminal_path_param is None:
                continue
            terminal_path_param_stem = (
                terminal_path_param[:-2] if terminal_path_param.endswith("id") else terminal_path_param
            )
            if terminal_path_param == normalized_field_name:
                matches_terminal_path_param_exactly = True
            if (
                normalized_field_name == "id"
                and terminal_path_param.endswith("id")
                and (
                    terminal_path_param_stem == entity_lower
                    or terminal_path_param_stem == last_entity_token
                )
            ):
                matches_terminal_resource_id_hint = True
            if (
                field_stem
                and terminal_path_param.endswith("id")
                and field_stem == terminal_path_param_stem
            ):
                matches_terminal_resource_id_hint = True
        for mapping in mappings:
            if mapping.target_path != f"{entity_name}.{field_name}" or mapping.operation_name is None:
                continue
            if ".request." in mapping.source_path:
                if operation_methods.get((mapping.contract_name, mapping.operation_name)) == HttpMethod.GET:
                    has_get_request_mapping = True
                if _is_create_operation_name(mapping.operation_name):
                    appears_in_create_request = True
            if ".response." in mapping.source_path and _is_create_operation_name(mapping.operation_name):
                appears_in_create_response = True

        return (
            1 if matches_terminal_path_param_exactly else 0,
            1 if matches_terminal_resource_id_hint else 0,
            1 if has_get_request_mapping else 0,
            1 if normalized_field_name == "id" else 0,
            1 if field_stem == entity_lower else 0,
            1 if field_stem == last_entity_token else 0,
            1 if appears_in_create_response and not appears_in_create_request else 0,
            1 if appears_in_create_response else 0,
        )

    ranked = sorted(candidates, key=score, reverse=True)
    selected = ranked[0]
    _validate_event_identity_selection(
        entity_name=entity_name,
        selected_id_field_name=selected,
        operations=relevant_operations,
        mappings=mappings,
    )
    if len(ranked) > 1 and score(ranked[0]) == score(ranked[1]):
        return (
            selected,
            (
                f"Ambiguous id-field inference among candidates {ranked[0]!r} and "
                f"{ranked[1]!r}; selected {selected!r} by source order."
            ),
        )
    return selected, None


def _validate_event_identity_selection(
    *,
    entity_name: str,
    selected_id_field_name: str,
    operations: list[CanonicalOperation],
    mappings: list[FieldMapping],
) -> None:
    if not _looks_like_event_or_transaction_entity(entity_name, operations):
        return
    if not _looks_like_parent_reference_id(
        entity_name=entity_name,
        field_name=selected_id_field_name,
        operations=operations,
        mappings=mappings,
    ):
        return
    example_identity = _example_safe_identity_field(entity_name)
    raise ValueError(
        f"Entity '{entity_name}' appears to be event/transaction-like, but inferred "
        f"persistence ID '{selected_id_field_name}' looks like a parent/reference field. "
        "Using a parent reference as the row identity would collapse multiple event rows "
        "for the same parent. Add identity_overrides with a real row identity field, "
        f"for example identity_overrides: [{{entity: {entity_name}, "
        f"persistence_id: {example_identity}}}]."
    )


def _looks_like_event_or_transaction_entity(
    entity_name: str,
    operations: list[CanonicalOperation],
) -> bool:
    entity_normalized = "".join(token.lower() for token in _camel_tokens(entity_name))
    if any(term in entity_normalized for term in _EVENT_OR_TRANSACTION_ENTITY_TERMS):
        return True

    for operation in operations:
        operation_name = operation.name.lower()
        if any(term in operation_name for term in _EVENT_OR_TRANSACTION_ENTITY_TERMS):
            return True
        if operation.path:
            normalized_path = operation.path.lower()
            if any(term in normalized_path for term in _EVENT_OR_TRANSACTION_ENTITY_TERMS):
                return True
    return False


def _looks_like_parent_reference_id(
    *,
    entity_name: str,
    field_name: str,
    operations: list[CanonicalOperation],
    mappings: list[FieldMapping],
) -> bool:
    normalized_field_name = field_name.lower()
    if normalized_field_name == "id" or not normalized_field_name.endswith("id"):
        return False

    field_stem = normalized_field_name[:-2]
    entity_tokens = [token.lower() for token in _camel_tokens(entity_name)]
    entity_normalized = "".join(token.lower() for token in _camel_tokens(entity_name))
    if (
        field_stem == entity_normalized
        or (entity_tokens and field_stem == entity_tokens[-1])
        or field_stem in _EVENT_OR_TRANSACTION_ENTITY_TERMS
    ):
        return False

    if field_stem in _PARENT_REFERENCE_ID_STEMS:
        return True

    for operation in operations:
        path_param_names = {parameter.name.lower() for parameter in operation.path_parameters}
        if normalized_field_name in path_param_names:
            return True

    target_path = f"{entity_name}.{field_name}"
    for mapping in mappings:
        if mapping.target_path != target_path or mapping.operation_name is None:
            continue
        if ".request." not in mapping.source_path:
            continue
        operation = next(
            (
                op
                for op in operations
                if op.interface_name == mapping.contract_name and op.name == mapping.operation_name
            ),
            None,
        )
        if operation is not None and operation.http_method == HttpMethod.GET:
            return True
        if operation is not None and operation.response_shape == ResponseShape.LIST:
            return True

    return False


def _example_safe_identity_field(entity_name: str) -> str:
    if "history" in entity_name.lower():
        return "transactionRowId"
    if "posting" in entity_name.lower():
        return "postingId"
    return f"{entity_name[:1].lower()}{entity_name[1:]}Id"


def _is_client_supplied_id_field(
    entity_name: str,
    field_name: str,
    *,
    mappings: list[FieldMapping],
) -> bool:
    target_path = f"{entity_name}.{field_name}"
    return any(
        mapping.target_path == target_path
        and mapping.operation_name is not None
        and ".request." in mapping.source_path
        and _is_create_operation_name(mapping.operation_name)
        for mapping in mappings
    )


def _terminal_path_parameter_name(operation: CanonicalOperation) -> str | None:
    if not operation.path or not operation.path_parameters:
        return None
    path = operation.path.rstrip("/")
    for parameter in reversed(operation.path_parameters):
        placeholder = "{" + parameter.name + "}"
        if path.endswith(placeholder):
            return parameter.name.lower()
    return None


_CREATE_OP_KEYWORDS = frozenset({
    "create", "add", "open", "register", "new", "initiate", "submit", "post",
})
_UPDATE_OP_KEYWORDS = frozenset({
    "update", "modify", "patch", "edit", "change", "amend", "replace", "put",
})
_GET_OP_PREFIXES = frozenset({"get", "fetch", "find", "read", "retrieve", "list"})
_DELETE_OP_PREFIXES = frozenset({"delete", "remove", "cancel", "close"})


def _infer_http_method_from_name(name: str) -> HttpMethod | None:
    """Infer HTTP method from operation name prefix when no OpenAPI spec is available."""
    lower = name.lower()
    if any(lower.startswith(p) for p in _GET_OP_PREFIXES):
        return HttpMethod.GET
    if any(kw in lower for kw in _CREATE_OP_KEYWORDS) and not any(kw in lower for kw in _UPDATE_OP_KEYWORDS):
        return HttpMethod.POST
    if any(kw in lower for kw in _UPDATE_OP_KEYWORDS):
        return HttpMethod.PUT
    if any(lower.startswith(p) for p in _DELETE_OP_PREFIXES):
        return HttpMethod.DELETE
    return None


def _is_create_operation_name(name: str) -> bool:
    """Return True when the operation name suggests create semantics.

    Explicitly rejects names that look like update/modify operations because
    update request samples also carry the id field — but that doesn't mean
    the id is client-supplied on create.
    """
    lower = name.lower()
    if any(kw in lower for kw in _UPDATE_OP_KEYWORDS):
        return False
    return any(kw in lower for kw in _CREATE_OP_KEYWORDS)


def _camel_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z]|$)", value) or [value]


def _validated_sql_table_schema(
    validated_ddl: ValidatedStagingDdl,
) -> dict[str, dict[str, Any]]:
    return {
        column.name: {
            "raw_type": column.raw_type,
            "type": _sql_type_to_canonical_type(column.raw_type),
            "max_length": column.max_length,
            "required": column.required,
        }
        for column in validated_ddl.columns
    }


def _declared_handoff_table_name(mapping_path: Path | None) -> str | None:
    if mapping_path is None:
        return None
    payload = _load_yaml(mapping_path)
    table_name = payload.get("table")
    if table_name is None:
        return None
    if not isinstance(table_name, str) or not table_name.strip():
        raise ValueError(f"Handoff mapping '{mapping_path}' field 'table' must be non-empty text")
    return table_name.strip()


_ENGINE_MANAGED_TABLES = {
    "batch_job_execution",
    "batch_job_execution_context",
    "batch_job_execution_params",
    "batch_job_instance",
    "batch_step_execution",
    "batch_step_execution_context",
    "flyway_schema_history",
}


def _protected_generated_table_owner(
    physical_name: str,
    *,
    entity_names: Iterable[str],
) -> str | None:
    normalized = physical_name.lower()
    if normalized in _ENGINE_MANAGED_TABLES:
        return "Engine/Flyway/Spring Batch infrastructure"
    for entity_name in entity_names:
        if normalized == to_snake_case(entity_name):
            return f"generated entity '{entity_name}'"
    return None


def _validate_staging_table_targets(
    *,
    staging_ddls: dict[str, str],
    staging_ddl_owners: dict[str, str],
    entities: list[CanonicalEntity],
) -> None:
    entity_names = [entity.name for entity in entities]
    for physical_name in staging_ddls:
        protected_table = _protected_generated_table_owner(
            physical_name,
            entity_names=entity_names,
        )
        if protected_table is None:
            continue
        handoff_name = staging_ddl_owners[physical_name.lower()]
        raise ValueError(
            f"Staging DDL for handoff '{handoff_name}' targets protected table "
            f"'{physical_name}' ({protected_table}). Declare a dedicated staging table."
        )


def _sql_type_to_canonical_type(raw_type: str) -> CanonicalFieldType:
    normalized = raw_type.upper()
    if normalized in {"INT", "INTEGER", "BIGINT"}:
        return CanonicalFieldType.INTEGER
    if normalized in {"DECIMAL", "NUMERIC", "NUMBER"}:
        return CanonicalFieldType.DECIMAL
    if normalized in {"DATE"}:
        return CanonicalFieldType.DATE
    if normalized in {"TIMESTAMP", "DATETIME"}:
        return CanonicalFieldType.DATETIME
    if normalized in {"BLOB", "BINARY", "VARBINARY", "BYTEA"}:
        return CanonicalFieldType.BINARY
    return CanonicalFieldType.STRING


def _split_canonical_path(path: str) -> tuple[str, str]:
    entity_name, field_name = path.split(".", 1)
    return entity_name, field_name


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _hyphen_to_camel(value: str) -> str:
    parts = value.split("-")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in '{path}'")
    return payload


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping in '{path}'")
    return payload


def _refresh_report_status(report: MappingCompletenessReport) -> None:
    if any(issue.severity == MappingSeverity.ERROR for issue in report.issues):
        report.status = "error"
    elif report.issues:
        report.status = "warning"
    else:
        report.status = "complete"
