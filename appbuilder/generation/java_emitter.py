"""Emit Spring Boot Java sources from normalized metadata."""

from __future__ import annotations

import re
import shutil
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from appbuilder.core import AppArchetype
from appbuilder.core.xml_safety import XmlParseBudget, read_untrusted_xml_bytes
from appbuilder.mapping import MappingDirection, MappingSeverity
from appbuilder.mapping.models import FieldMapping
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalRelationship,
    ContractMetadata,
    HttpMethod,
    IdGenerationStrategy,
    MetadataProject,
    OperationParameter,
    OperationParameterLocation,
    ResponseShape,
    RunSemanticsMetadata,
)
from appbuilder.metadata.translation import _is_create_operation_name
from appbuilder.rules import CanonicalRule, RuleType
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

from .file_writer import write_generated_file
from .utils import (
    _java_file,
    all_entities,
    base_package,
    canonical_field_name,
    contract_field_name,
    entity_id_field,
    filter_mappings,
    operation_entity_name,
    operation_mapping_transport_context,
    output_field_name,
    package_path,
    parse_sql_table_columns,
    staging_operational_column_role,
    to_java_class_name,
    to_java_method_name,
    to_pascal_case,
    to_snake_case,
)
from .utils import (
    spec_entity_route_base_candidate as _spec_entity_route_base_candidate,
)
from .utils import (
    supports_spec_route as _supports_spec_route_helper,
)
from .utils import (
    xml_field_type_label as _xml_field_type_label,
)
from .utils import (
    xml_mapping_types_compatible as _xml_mapping_types_compatible,
)

CANONICAL_TO_JAVA = {
    "string": "String",
    "integer": "Long",
    "decimal": "BigDecimal",
    "boolean": "Boolean",
    "date": "LocalDate",
    "datetime": "LocalDateTime",
    "binary": "byte[]",
}

CANONICAL_TO_SQL = {
    "string": "VARCHAR({max_length})",
    "integer": "BIGINT",
    "decimal": "DECIMAL(19,4)",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "binary": "BYTEA",
}

_JAVA_INTEGER_LITERAL_PATTERN = re.compile(r"^[+-]?\d+$")
_JAVA_DECIMAL_LITERAL_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")

JAVA_IMPORTS = {
    "BigDecimal": "java.math.BigDecimal",
    "LocalDate": "java.time.LocalDate",
    "LocalDateTime": "java.time.LocalDateTime",
}

_AUDIT_FIELD_SPECS = (
    {
        "field_name": "createdBy",
        "column_name": "created_by",
        "annotation": "@CreatedBy",
    },
    {
        "field_name": "createdAt",
        "column_name": "created_at",
        "annotation": "@CreatedDate",
    },
    {
        "field_name": "modifiedBy",
        "column_name": "modified_by",
        "annotation": "@LastModifiedBy",
    },
    {
        "field_name": "modifiedAt",
        "column_name": "modified_at",
        "annotation": "@LastModifiedDate",
    },
)
_AUDIT_COLUMN_SPECS = {spec["column_name"]: spec for spec in _AUDIT_FIELD_SPECS}
_CROSS_ENTITY_FIELD_OPERATORS = {"eq", "neq", "lt", "lte", "gt", "gte"}
_CROSS_ENTITY_STATE_RULE_TYPES = {
    RuleType.CROSS_ENTITY_FIELD_CHECK,
    RuleType.CROSS_ENTITY_FIELD_COMPARE,
    RuleType.CROSS_ENTITY_FIELD_IN,
}
_NUMERIC_FIELD_TYPES = {
    CanonicalFieldType.INTEGER,
    CanonicalFieldType.DECIMAL,
}
_MINOR_UNIT_TYPE_COERCION = "major_to_minor_units"
_INBOUND_TRAILER_COUNT_VALUE_SOURCES = {"data_record_count", "record_count"}
_INBOUND_TRAILER_UNSUPPORTED_MESSAGE = (
    "Inbound trailer validation supports only record-count and sum totals in v1."
)


def emit_java_sources(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
) -> list[Path]:
    from .write_contract import validate_write_contracts
    validate_write_contracts(metadata, target_profile=target_profile, controller_scope="java")
    _validate_computed_read_runtime_support(metadata)
    _validate_file_contract_runtime_support(metadata)
    root_package = base_package(metadata)
    root_path = output_dir / "src" / "main" / "java" / package_path(root_package)
    test_root = output_dir / "src" / "test" / "java" / package_path(root_package)
    root_path.mkdir(parents=True, exist_ok=True)
    test_root.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []

    # Per-app singletons — emitted once regardless of entity count
    files.append(
        _write_java_file(
            root_path / f"{to_pascal_case(metadata.bounded_context)}Application.java",
            _render_application_class(
                metadata=metadata,
                root_package=root_package,
                target_profile=target_profile,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            ),
        )
    )
    files.append(
        _write_java_file(
            test_root / f"{to_pascal_case(metadata.bounded_context)}ApplicationTest.java",
            _render_application_test(
                metadata=metadata,
                root_package=root_package,
                target_profile=target_profile,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            ),
        )
    )

    # Error handling — shared exception classes emitted once per app
    exception_dir = root_path / "exception"
    files.append(
        _write_java_file(
            exception_dir / "ResourceNotFoundException.java",
            _render_resource_not_found_exception(
                root_package=root_package,
                source_manifest=source_manifest,
                target_profile=target_profile,
                generation_run_id=generation_run_id,
            ),
        )
    )
    files.append(
        _write_java_file(
            exception_dir / "DuplicateResourceException.java",
            _render_duplicate_resource_exception(
                root_package=root_package,
                source_manifest=source_manifest,
                target_profile=target_profile,
                generation_run_id=generation_run_id,
            ),
        )
    )
    files.append(
        _write_java_file(
            exception_dir / "ErrorResponse.java",
            _render_error_response(
                root_package=root_package,
                source_manifest=source_manifest,
                target_profile=target_profile,
                generation_run_id=generation_run_id,
            ),
        )
    )
    if _has_cross_entity_state_rules(metadata):
        files.append(
            _write_java_file(
                exception_dir / "BusinessRuleException.java",
                _render_business_rule_exception(
                    root_package=root_package,
                    source_manifest=source_manifest,
                    target_profile=target_profile,
                    generation_run_id=generation_run_id,
                ),
            )
        )
    files.append(
        _write_java_file(
            exception_dir / "GlobalExceptionHandler.java",
            _render_global_exception_handler(
                root_package=root_package,
                emit_business_rule_handler=_has_cross_entity_state_rules(metadata),
                source_manifest=source_manifest,
                target_profile=target_profile,
                generation_run_id=generation_run_id,
            ),
        )
    )
    if target_profile.runtime_database_dependency == "postgresql":
        files.append(
            _write_java_file(
                root_path / "config" / "DatasourceCredentialConfig.java",
                _render_datasource_credential_config(
                    root_package=root_package,
                    source_manifest=source_manifest,
                    target_profile=target_profile,
                    generation_run_id=generation_run_id,
                ),
            )
        )

    # Per-entity generation — one set of domain/repo/controller/service/DTOs per entity
    domain_dir = root_path / "domain"
    repository_dir = root_path / "repository"
    inbound_dir = root_path / "adapter" / "inbound"
    service_dir = root_path / "service"
    outbound_dir = root_path / "adapter" / "outbound"
    upstream_file_ingest_contexts = _upstream_file_ingest_contexts(metadata)

    for contract in _upstream_fixed_width_contracts(metadata):
        files.append(
            _write_java_file(
                inbound_dir / f"{_fixed_width_parser_class_name(contract.name)}.java",
                _render_fixed_width_inbound_parser(
                    contract=contract,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
    for contract in _upstream_csv_contracts(metadata):
        files.append(
            _write_java_file(
                inbound_dir / f"{_csv_parser_class_name(contract.name)}.java",
                _render_csv_inbound_parser(
                    contract=contract,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
    if upstream_file_ingest_contexts:
        files.append(
            _write_java_file(
                inbound_dir / "FileIngestController.java",
                _render_file_ingest_controller(
                    metadata=metadata,
                    contexts=upstream_file_ingest_contexts,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
    for contract in _xml_contracts(metadata):
        files.append(
            _write_java_file(
                root_path / "adapter" / "xml" / f"{_xml_model_class_name(contract)}.java",
                _render_xml_model(
                    contract=contract,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        files.append(
            _write_java_file(
                root_path / "adapter" / "xml" / f"{_xml_parser_class_name(contract)}.java",
                _render_xml_parser(
                    contract=contract,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        files.append(
            _write_java_file(
                root_path / "adapter" / "xml" / f"{_xml_serializer_class_name(contract)}.java",
                _render_xml_serializer(
                    contract=contract,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        files.extend(
            _copy_xml_contract_resources(
                contract=contract,
                output_dir=output_dir,
                source_manifest=source_manifest,
            )
        )
        files.extend(
            _emit_xml_contract_sample_test(
                contract=contract,
                test_root=test_root,
                root_package=root_package,
                target_profile=target_profile,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
                output_dir=output_dir,
            )
        )

    upstream_xml_ingest_contexts = _upstream_xml_ingest_contexts(metadata)
    if upstream_xml_ingest_contexts:
        files.append(
            _write_java_file(
                root_path / "adapter" / "xml" / "XmlIngestController.java",
                _render_xml_ingest_controller(
                    metadata=metadata,
                    contexts=upstream_xml_ingest_contexts,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )

    downstream_xml_output_contexts = _downstream_xml_output_contexts(metadata)
    if downstream_xml_output_contexts:
        files.append(
            _write_java_file(
                root_path / "adapter" / "xml" / "XmlOutputController.java",
                _render_xml_output_controller(
                    metadata=metadata,
                    contexts=downstream_xml_output_contexts,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )

    inbound_soap_contracts = _inbound_soap_contracts(metadata)
    outbound_soap_contracts = _outbound_soap_contracts(metadata)
    outbound_soap_action_contexts = _outbound_soap_action_contexts(metadata)
    if outbound_soap_contracts:
        files.append(
            _write_java_file(
                root_path / "adapter" / "soap" / "SoapClientConfig.java",
                _render_soap_client_config(
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        files.append(
            _write_java_file(
                exception_dir / "SoapClientException.java",
                _render_soap_client_exception(
                    root_package=root_package,
                    source_manifest=source_manifest,
                    target_profile=target_profile,
                    generation_run_id=generation_run_id,
                ),
            )
        )
    if inbound_soap_contracts:
        files.append(
            _write_java_file(
                root_path / "adapter" / "soap" / "SoapEndpointConfig.java",
                _render_soap_endpoint_config(
                    contracts=inbound_soap_contracts,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        files.append(
            _write_java_file(
                exception_dir / "SoapOperationMappingException.java",
                _render_soap_operation_mapping_exception(
                    root_package=root_package,
                    source_manifest=source_manifest,
                    target_profile=target_profile,
                    generation_run_id=generation_run_id,
                ),
            )
        )
    for contract in inbound_soap_contracts:
        files.append(
            _write_java_file(
                root_path / "adapter" / "soap" / f"{_soap_handler_interface_name(contract)}.java",
                _render_soap_handler_interface(
                    contract=contract,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        if _soap_has_canonical_operation_mappings(contract):
            files.append(
                _write_java_file(
                    root_path / "adapter" / "soap" / f"{_soap_canonical_handler_class_name(contract)}.java",
                    _render_soap_canonical_handler(
                        metadata=metadata,
                        contract=contract,
                        root_package=root_package,
                        target_profile=target_profile,
                        source_manifest=source_manifest,
                        generation_run_id=generation_run_id,
                    ),
                )
            )
        files.append(
            _write_java_file(
                root_path / "adapter" / "soap" / f"{_soap_endpoint_class_name(contract)}.java",
                _render_soap_endpoint(
                    contract=contract,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        files.extend(
            _copy_soap_contract_resources(
                contract=contract,
                output_dir=output_dir,
                source_manifest=source_manifest,
                rewrite_endpoint_address=True,
            )
        )

    for contract in outbound_soap_contracts:
        files.append(
            _write_java_file(
                root_path / "adapter" / "soap" / f"{_soap_client_class_name(contract)}.java",
                _render_soap_client(
                    contract=contract,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        files.extend(
            _copy_soap_contract_resources(
                contract=contract,
                output_dir=output_dir,
                source_manifest=source_manifest,
                rewrite_endpoint_address=False,
            )
        )
    if outbound_soap_action_contexts:
        files.append(
            _write_java_file(
                root_path / "adapter" / "soap" / "OutboundSoapActionController.java",
                _render_outbound_soap_action_controller(
                    contexts=outbound_soap_action_contexts,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )

    entity_artifact_plans: dict[str, _EntityJavaArtifactPlan] = {}
    for entity in all_entities(metadata):
        if not entity.fields:
            continue
        artifact_plan = _entity_java_artifact_plan(
            metadata=metadata,
            entity=entity,
            target_profile=target_profile,
        )
        entity_artifact_plans[entity.name] = artifact_plan
        files.append(
            _write_java_file(
                domain_dir / f"{entity.name}.java",
                _render_entity(
                    metadata=metadata,
                    entity=entity,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        files.append(
            _write_java_file(
                repository_dir / f"{entity.name}Repository.java",
                _render_repository(
                    entity=entity,
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )

        entity_path_base = f"/{to_snake_case(entity.name)}s"
        op_contexts = artifact_plan.operation_contexts
        for ctx in op_contexts:
            files.append(
                _write_java_file(
                    inbound_dir / f"{ctx['request_class_name']}.java",
                    _render_dto(
                        class_name=ctx["request_class_name"],
                        package_name=f"{root_package}.adapter.inbound",
                        entity=entity,
                        field_mappings=ctx["request_field_mappings"],
                        emit_validation_annotations=True,
                        target_profile=target_profile,
                        source_manifest=source_manifest,
                        generation_run_id=generation_run_id,
                    ),
                )
            )
            files.append(
                _write_java_file(
                    inbound_dir / f"{ctx['response_class_name']}.java",
                    _render_dto(
                        class_name=ctx["response_class_name"],
                        package_name=f"{root_package}.adapter.inbound",
                        entity=entity,
                        field_mappings=ctx["response_field_mappings"],
                        emit_validation_annotations=False,
                        target_profile=target_profile,
                        source_manifest=source_manifest,
                        generation_run_id=generation_run_id,
                    ),
                )
            )

        # Determine id type for CRUD path-param methods
        id_field = entity_id_field(entity)
        id_java_type = _java_type(id_field)
        if artifact_plan.emit_generic_fallback_dtos:
            if artifact_plan.emit_generic_create_fallback:
                files.append(
                    _write_java_file(
                        inbound_dir / f"{_fallback_create_request_class(entity)}.java",
                        _render_dto(
                            class_name=_fallback_create_request_class(entity),
                            package_name=f"{root_package}.adapter.inbound",
                            entity=entity,
                            field_mappings=_fallback_request_field_mappings(metadata, entity),
                            emit_validation_annotations=True,
                            target_profile=target_profile,
                            source_manifest=source_manifest,
                            generation_run_id=generation_run_id,
                        ),
                    )
                )
            files.append(
                _write_java_file(
                    inbound_dir / f"{_fallback_update_request_class(entity)}.java",
                    _render_dto(
                        class_name=_fallback_update_request_class(entity),
                        package_name=f"{root_package}.adapter.inbound",
                        entity=entity,
                        field_mappings=_fallback_request_field_mappings(metadata, entity),
                        emit_validation_annotations=True,
                        target_profile=target_profile,
                        source_manifest=source_manifest,
                        generation_run_id=generation_run_id,
                    ),
                )
            )
            files.append(
                _write_java_file(
                    inbound_dir / f"{_fallback_response_class(entity)}.java",
                    _render_dto(
                        class_name=_fallback_response_class(entity),
                        package_name=f"{root_package}.adapter.inbound",
                        entity=entity,
                        field_mappings=_fallback_response_field_mappings(entity),
                        emit_validation_annotations=False,
                        target_profile=target_profile,
                        source_manifest=source_manifest,
                        generation_run_id=generation_run_id,
                    ),
                )
            )

        # Emit ONE controller with full CRUD (POST + GET/{id} + GET-list + PUT/{id} + DELETE/{id})
        files.append(
            _write_java_file(
                inbound_dir / f"{entity.name}Controller.java",
                _render_controller(
                    entity=entity,
                    root_package=root_package,
                    op_contexts=op_contexts,
                    entity_path_base=entity_path_base,
                    id_java_type=id_java_type,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        files.append(
            _write_java_file(
                service_dir / f"{entity.name}ServiceBase.java",
                _render_service(
                    metadata=metadata,
                    entity=entity,
                    root_package=root_package,
                    op_contexts=op_contexts,
                    id_java_type=id_java_type,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
            )
        )
        developer_service_path = service_dir / f"{entity.name}Service.java"
        _adopt_legacy_service_for_generation_gap(
            developer_service_path,
            metadata=metadata,
            entity=entity,
        )
        files.append(
            _write_java_file(
                developer_service_path,
                _render_developer_service(
                    metadata=metadata,
                    entity=entity,
                    root_package=root_package,
                    id_java_type=id_java_type,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                ),
                ownership="developer",
            )
        )

        file_writer_contexts = artifact_plan.file_writer_contexts
        for file_writer_context in file_writer_contexts:
            files.append(
                _write_java_file(
                    outbound_dir / f"{file_writer_context.writer_class_name}.java",
                    _render_file_writer(
                        metadata=metadata,
                        entity=entity,
                        file_writer_context=file_writer_context,
                        root_package=root_package,
                        target_profile=target_profile,
                        source_manifest=source_manifest,
                        generation_run_id=generation_run_id,
                    ),
                )
            )
        if artifact_plan.emit_staging_writer:
            files.append(
                _write_java_file(
                    outbound_dir / f"{entity.name}StagingWriter.java",
                    _render_staging_writer(
                        metadata=metadata,
                        entity=entity,
                        root_package=root_package,
                        target_profile=target_profile,
                        source_manifest=source_manifest,
                        generation_run_id=generation_run_id,
                    ),
                )
            )

    # Batch job — one per entity that has staging-table handoffs or downstream file outputs.
    if any(plan.emit_batch_job for plan in entity_artifact_plans.values()):
        batch_dir = root_path / "batch"
        run_semantics_by_job: dict[str, RunSemanticsMetadata] = {}
        for entity in (item for item in all_entities(metadata) if item.fields):
            artifact_plan = entity_artifact_plans[entity.name]
            if not artifact_plan.emit_batch_job:
                continue
            run_semantics = _run_semantics_for_entity(metadata, entity.name)
            entity_var = entity.name[:1].lower() + entity.name[1:]
            if run_semantics is not None:
                run_semantics_by_job[f"{entity_var}EodJob"] = run_semantics
            files.append(
                _write_java_file(
                    batch_dir / f"{entity.name}EodBatchJob.java",
                    _render_batch_job(
                        entity=entity,
                        root_package=root_package,
                        bounded_context=metadata.bounded_context,
                        target_profile=target_profile,
                        source_manifest=source_manifest,
                        generation_run_id=generation_run_id,
                        has_staging_writer=artifact_plan.emit_staging_writer,
                        has_file_writer=artifact_plan.has_downstream_file,
                        file_writer_contexts=artifact_plan.file_writer_contexts,
                        file_extension=_file_output_extension_for_entity(
                            metadata, entity.name
                        ),
                        has_file_control_records=_has_enhanced_fixed_width_contract_for_entity(
                            metadata, entity.name
                        ),
                        staging_has_run_identity=_staging_entity_has_run_identity(
                            metadata, entity.name
                        ),
                        staging_has_business_date=_staging_entity_has_business_date(
                            metadata, entity.name
                        ),
                        run_semantics=run_semantics,
                    ),
                )
            )
        files.append(
            _write_java_file(
                inbound_dir / "BatchTriggerController.java",
                _render_batch_trigger_controller(
                    root_package=root_package,
                    target_profile=target_profile,
                    source_manifest=source_manifest,
                    generation_run_id=generation_run_id,
                    run_semantics_by_job=run_semantics_by_job,
                ),
            )
        )

    return files


def _write_java_file(path: Path, content: str, *, ownership: str = "generated") -> Path:
    return write_generated_file(path, content, ownership=ownership)


def _adopt_legacy_service_for_generation_gap(
    path: Path,
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
) -> None:
    """Move a pre-ownership generated service aside so the developer subclass can scaffold."""

    if not path.exists() or not path.is_file():
        return
    existing = path.read_text(encoding="utf-8")
    if "EdgeForge-ownership:" in existing or "Generated by EdgeForge" not in existing:
        return

    backup_path = _legacy_service_backup_path(path, existing)
    if not backup_path.exists():
        backup_path.write_text(existing, encoding="utf-8")
    path.unlink()
    _append_generation_warning(
        metadata,
        f"{entity.name}: legacy generated service adopted for regeneration ownership split; "
        f"previous content preserved as {backup_path.name}.",
    )


def _legacy_service_backup_path(path: Path, content: str) -> Path:
    backup_path = path.with_name(f"{path.name}.legacy.bak")
    if not backup_path.exists() or backup_path.read_text(encoding="utf-8") == content:
        return backup_path

    index = 1
    while True:
        candidate = path.with_name(f"{path.name}.legacy.bak.{index}")
        if not candidate.exists() or candidate.read_text(encoding="utf-8") == content:
            return candidate
        index += 1


# ---------------------------------------------------------------------------
# App-wide generated configuration and error handling singletons
# ---------------------------------------------------------------------------

def _render_datasource_credential_config(
    *,
    root_package: str,
    source_manifest: str,
    target_profile: TargetProfile,
    generation_run_id: str,
) -> str:
    body = [
        "@Configuration",
        "public class DatasourceCredentialConfig implements BeanFactoryPostProcessor, EnvironmentAware {",
        "",
        "    private Environment environment;",
        "",
        "    @Override",
        "    public void setEnvironment(Environment environment) {",
        "        this.environment = environment;",
        "    }",
        "",
        "    @Override",
        "    public void postProcessBeanFactory(ConfigurableListableBeanFactory beanFactory)",
        "            throws BeansException {",
        "        requireNonBlank(",
        "            \"SPRING_DATASOURCE_USERNAME\",",
        "            environment.getProperty(\"SPRING_DATASOURCE_USERNAME\")",
        "        );",
        "        requireNonBlank(",
        "            \"SPRING_DATASOURCE_PASSWORD\",",
        "            environment.getProperty(\"SPRING_DATASOURCE_PASSWORD\")",
        "        );",
        "    }",
        "",
        "    private void requireNonBlank(String envVar, String value) {",
        "        if (value == null || value.isBlank()) {",
        "            throw new IllegalStateException(envVar + \" must be set for enterprise PostgreSQL profiles.\");",
        "        }",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.config",
        imports=[
            "org.springframework.beans.BeansException",
            "org.springframework.beans.factory.config.BeanFactoryPostProcessor",
            "org.springframework.beans.factory.config.ConfigurableListableBeanFactory",
            "org.springframework.context.annotation.Configuration",
            "org.springframework.context.EnvironmentAware",
            "org.springframework.core.env.Environment",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_resource_not_found_exception(
    *,
    root_package: str,
    source_manifest: str,
    target_profile: TargetProfile,
    generation_run_id: str,
) -> str:
    """Generate a single ResourceNotFoundException used by all entity services."""
    body = [
        "// Generated: one shared exception class for all entity 404 cases.",
        "public class ResourceNotFoundException extends RuntimeException {",
        "",
        "    public ResourceNotFoundException(String message) {",
        "        super(message);",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.exception",
        imports=[],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_duplicate_resource_exception(
    *,
    root_package: str,
    source_manifest: str,
    target_profile: TargetProfile,
    generation_run_id: str,
) -> str:
    """Generate a shared conflict exception for create-only duplicate IDs."""
    body = [
        "// Generated: thrown when POST create would overwrite an existing resource.",
        "public class DuplicateResourceException extends RuntimeException {",
        "",
        "    public DuplicateResourceException(String message) {",
        "        super(message);",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.exception",
        imports=[],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_error_response(
    *,
    root_package: str,
    source_manifest: str,
    target_profile: TargetProfile,
    generation_run_id: str,
) -> str:
    """Generate an ErrorResponse record used by the GlobalExceptionHandler."""
    body = [
        "public class ErrorResponse {",
        "",
        "    private final String timestamp;",
        "    private final int status;",
        "    private final String error;",
        "    private final String message;",
        "    private final String path;",
        "",
        "    public ErrorResponse(String timestamp, int status, String error, String message, String path) {",
        "        this.timestamp = timestamp;",
        "        this.status = status;",
        "        this.error = error;",
        "        this.message = message;",
        "        this.path = path;",
        "    }",
        "",
        "    public String getTimestamp() { return timestamp; }",
        "    public int getStatus() { return status; }",
        "    public String getError() { return error; }",
        "    public String getMessage() { return message; }",
        "    public String getPath() { return path; }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.exception",
        imports=[],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_business_rule_exception(
    *,
    root_package: str,
    source_manifest: str,
    target_profile: TargetProfile,
    generation_run_id: str,
) -> str:
    """Generate a shared 422 business-rule exception for cross-entity state checks."""
    body = [
        "public class BusinessRuleException extends RuntimeException {",
        "",
        "    public BusinessRuleException(String message) {",
        "        super(message);",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.exception",
        imports=[],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_global_exception_handler(
    *,
    root_package: str,
    emit_business_rule_handler: bool,
    source_manifest: str,
    target_profile: TargetProfile,
    generation_run_id: str,
) -> str:
    """Generate a @RestControllerAdvice that maps exceptions to HTTP responses."""
    body = [
        "@RestControllerAdvice",
        "public class GlobalExceptionHandler {",
        "",
        "    @ExceptionHandler(ResourceNotFoundException.class)",
        "    @ResponseStatus(HttpStatus.NOT_FOUND)",
        "    public ErrorResponse handleNotFound(",
        "            ResourceNotFoundException ex,",
        "            HttpServletRequest request) {",
        "        return new ErrorResponse(",
        "            java.time.Instant.now().toString(),",
        "            HttpStatus.NOT_FOUND.value(),",
        "            \"Not Found\",",
        "            ex.getMessage(),",
        "            request.getRequestURI()",
        "        );",
        "    }",
        "",
        "    @ExceptionHandler(DuplicateResourceException.class)",
        "    @ResponseStatus(HttpStatus.CONFLICT)",
        "    public ErrorResponse handleDuplicateResource(",
        "            DuplicateResourceException ex,",
        "            HttpServletRequest request) {",
        "        return new ErrorResponse(",
        "            java.time.Instant.now().toString(),",
        "            HttpStatus.CONFLICT.value(),",
        "            \"Conflict\",",
        "            ex.getMessage(),",
        "            request.getRequestURI()",
        "        );",
        "    }",
        "",
        "    @ExceptionHandler(org.springframework.web.bind.MethodArgumentNotValidException.class)",
        "    @ResponseStatus(HttpStatus.BAD_REQUEST)",
        "    public ErrorResponse handleValidation(",
        "            org.springframework.web.bind.MethodArgumentNotValidException ex,",
        "            HttpServletRequest request) {",
        "        String message = ex.getBindingResult().getFieldErrors().stream()",
        "            .map(e -> e.getField() + \": \" + e.getDefaultMessage())",
        "            .collect(java.util.stream.Collectors.joining(\"; \"));",
        "        return new ErrorResponse(",
        "            java.time.Instant.now().toString(),",
        "            HttpStatus.BAD_REQUEST.value(),",
        "            \"Bad Request\",",
        "            message,",
        "            request.getRequestURI()",
        "        );",
        "    }",
    ]
    if emit_business_rule_handler:
        body.extend(
            [
                "",
                "    @ExceptionHandler(BusinessRuleException.class)",
                "    @ResponseStatus(HttpStatus.UNPROCESSABLE_ENTITY)",
                "    public ErrorResponse handleCrossEntityBusinessRule(",
                "            BusinessRuleException ex,",
                "            HttpServletRequest request) {",
                "        return new ErrorResponse(",
                "            java.time.Instant.now().toString(),",
                "            HttpStatus.UNPROCESSABLE_ENTITY.value(),",
                "            \"Unprocessable Entity\",",
                "            ex.getMessage(),",
                "            request.getRequestURI()",
                "        );",
                "    }",
            ]
        )
    body.extend(
        [
            "",
            "    @ExceptionHandler(IllegalArgumentException.class)",
            "    @ResponseStatus(HttpStatus.BAD_REQUEST)",
            "    public ErrorResponse handleBusinessRule(",
            "            IllegalArgumentException ex,",
            "            HttpServletRequest request) {",
            "        return new ErrorResponse(",
            "            java.time.Instant.now().toString(),",
            "            HttpStatus.BAD_REQUEST.value(),",
            "            \"Bad Request\",",
            "            ex.getMessage(),",
            "            request.getRequestURI()",
            "        );",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.exception",
        imports=[
            f"{root_package}.exception.DuplicateResourceException",
            f"{root_package}.exception.ErrorResponse",
            f"{root_package}.exception.ResourceNotFoundException",
            "jakarta.servlet.http.HttpServletRequest",
            "org.springframework.http.HttpStatus",
            "org.springframework.web.bind.annotation.ExceptionHandler",
            "org.springframework.web.bind.annotation.ResponseStatus",
            "org.springframework.web.bind.annotation.RestControllerAdvice",
        ]
        + (
            [f"{root_package}.exception.BusinessRuleException"]
            if emit_business_rule_handler
            else []
        ),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


# ---------------------------------------------------------------------------
# Application class
# ---------------------------------------------------------------------------

def _render_application_class(
    *,
    metadata: MetadataProject,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    class_name = f"{to_pascal_case(metadata.bounded_context)}Application"
    return _java_file(
        package_name=root_package,
        imports=[
            "org.springframework.boot.SpringApplication",
            "org.springframework.boot.autoconfigure.SpringBootApplication",
        ],
        body=[
            "@SpringBootApplication",
            f"public class {class_name} {{",
            "",
            "    public static void main(String[] args) {",
            f"        SpringApplication.run({class_name}.class, args);",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


# ---------------------------------------------------------------------------
# Domain entity
# ---------------------------------------------------------------------------

def _render_entity(
    *,
    metadata: MetadataProject | None = None,
    entity: CanonicalEntity,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    business_audit_annotations: dict[str, list[str]] = {}
    occupied_audit_columns: set[str] = set()
    imports = {
        "com.fasterxml.jackson.annotation.JsonIgnore",
        "jakarta.persistence.Column",
        "jakarta.persistence.Entity",
        "jakarta.persistence.FetchType",
        "jakarta.persistence.GeneratedValue",
        "jakarta.persistence.GenerationType",
        "jakarta.persistence.Id",
        "jakarta.persistence.JoinColumn",
        "jakarta.persistence.ManyToOne",
        "jakarta.persistence.SequenceGenerator",
        "jakarta.persistence.Table",
    }
    if any(field.format == "iso-4217" for field in entity.fields):
        imports.update(
            {
                "org.hibernate.annotations.JdbcTypeCode",
                "org.hibernate.type.SqlTypes",
            }
        )
    if target_profile.emit_audit:
        imports.update(
            {
                "jakarta.persistence.EntityListeners",
                "java.time.LocalDateTime",
                "org.springframework.data.annotation.CreatedBy",
                "org.springframework.data.annotation.CreatedDate",
                "org.springframework.data.annotation.LastModifiedBy",
                "org.springframework.data.annotation.LastModifiedDate",
                "org.springframework.data.jpa.domain.support.AuditingEntityListener",
            }
        )
    for field in entity.fields:
        java_type = _java_type(field)
        if java_type in JAVA_IMPORTS:
            imports.add(JAVA_IMPORTS[java_type])
    entity_relationships = _relationships_for_entity(metadata, entity.name) if metadata is not None else []
    for relationship in entity_relationships:
        if relationship.target_entity != entity.name:
            imports.add(f"{root_package}.domain.{relationship.target_entity}")
    pre_persist_initializers = (
        _server_set_field_initializers(metadata, entity) if metadata is not None else []
    )
    if pre_persist_initializers:
        imports.add("jakarta.persistence.PrePersist")
    if any(literal.startswith("LocalDateTime.now()") for _, literal in pre_persist_initializers):
        imports.add("java.time.LocalDateTime")
    if any(literal.startswith("LocalDate.now()") for _, literal in pre_persist_initializers):
        imports.add("java.time.LocalDate")
    body: list[str] = [
        "@Entity",
        f"@Table(name = \"{to_snake_case(entity.name)}\")",
    ]
    if target_profile.emit_audit:
        occupied_audit_columns, business_audit_annotations = _audit_collision_metadata(entity)
        body.append("@EntityListeners(AuditingEntityListener.class)")
    body.extend(
        [
            f"public class {entity.name} {{",
            "",
        ]
    )
    id_field = entity_id_field(entity)
    for field in entity.fields:
        body.extend(
            _render_entity_field(
                metadata=metadata,
                entity=entity,
                field=field,
                is_id=field.name == id_field.name,
                extra_annotations=business_audit_annotations.get(field.name, []),
            )
        )
        body.append("")
    for relationship in entity_relationships:
        body.extend(_render_relationship_field(relationship))
        body.append("")
    if target_profile.emit_audit:
        audit_fields = _render_audit_fields(skip_columns=occupied_audit_columns)
        if audit_fields:
            body.extend(audit_fields)
            body.append("")
    body.extend(
        [
            f"    public {entity.name}() {{",
            "    }",
            "",
        ]
    )
    if pre_persist_initializers:
        body.extend(_render_pre_persist_initializer(pre_persist_initializers))
        body.append("")
    for field in entity.fields:
        java_type = _java_type(field)
        method_suffix = to_pascal_case(field.name)
        body.extend(
            [
                f"    public {java_type} get{method_suffix}() {{",
                f"        return {field.name};",
                "    }",
                "",
                f"    public void set{method_suffix}({java_type} {field.name}) {{",
                f"        this.{field.name} = {field.name};",
                "    }",
                "",
            ]
        )
    for relationship in entity_relationships:
        method_suffix = to_pascal_case(relationship.association_name)
        body.extend(
            [
                f"    public {relationship.target_entity} get{method_suffix}() {{",
                f"        return {relationship.association_name};",
                "    }",
                "",
                f"    public void set{method_suffix}({relationship.target_entity} {relationship.association_name}) {{",
                f"        this.{relationship.association_name} = {relationship.association_name};",
                "    }",
                "",
            ]
        )
    if target_profile.emit_audit:
        body.extend(_render_audit_getters_and_setters(skip_columns=occupied_audit_columns))
    body.append("}")

    body_text = "\n".join(body)
    if "@GeneratedValue" not in body_text:
        imports.discard("jakarta.persistence.GeneratedValue")
        imports.discard("jakarta.persistence.GenerationType")
    if "@SequenceGenerator" not in body_text:
        imports.discard("jakarta.persistence.SequenceGenerator")
    if "UUID.randomUUID()" in body_text:
        imports.add("java.util.UUID")

    return _java_file(
        package_name=f"{root_package}.domain",
        imports=sorted(imports),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_entity_field(
    metadata: MetadataProject | None,
    entity: CanonicalEntity,
    field: CanonicalField,
    is_id: bool,
    *,
    extra_annotations: list[str] | None = None,
) -> list[str]:
    annotations = []
    if is_id:
        annotations.append("    @Id")
        application_assigned_ingest_id = _uses_application_assigned_ingest_id(
            metadata=metadata,
            entity=entity,
            field=field,
            is_id=is_id,
        )
        # C9: explicit id_generation_strategy wins over server_generated_id inference.
        strategy = field.id_generation_strategy
        if strategy is not None:
            if strategy == IdGenerationStrategy.UUID:
                if application_assigned_ingest_id:
                    annotations.append(
                        "    // ID ownership: application-assigned UUID (external ingestion may supply the id)."
                    )
                else:
                    annotations.append("    // ID ownership: server-generated UUID (C9 explicit).")
                    annotations.append("    @GeneratedValue(strategy = GenerationType.UUID)")
            elif strategy == IdGenerationStrategy.CALLER_SUPPLIED:
                annotations.append("    // ID ownership: caller-supplied (C9 explicit).")
            elif strategy == IdGenerationStrategy.DB_IDENTITY:
                annotations.append("    // ID ownership: database identity (C9 explicit).")
                annotations.append("    @GeneratedValue(strategy = GenerationType.IDENTITY)")
            elif strategy == IdGenerationStrategy.DB_SEQUENCE:
                seq_name = field.id_sequence_name or f"{to_snake_case(field.name)}_seq"
                generator_name = f"{seq_name}_generator"
                annotations.append(
                    f"    @SequenceGenerator(name = \"{generator_name}\", sequenceName = \"{seq_name}\", allocationSize = 1)"
                )
                annotations.append(
                    f"    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = \"{generator_name}\")"
                )
        else:
            # Legacy path: no explicit C9 strategy, fall back to server_generated_id inference.
            if field.type.value == "string" and field.server_generated_id:
                if application_assigned_ingest_id:
                    annotations.append(
                        "    // ID ownership: application-assigned UUID (external ingestion may supply the id)."
                    )
                else:
                    annotations.append(
                        "    // ID ownership: server-generated UUID (id absent from POST body schema)."
                    )
                    annotations.append("    @GeneratedValue(strategy = GenerationType.UUID)")
            elif field.type.value == "string":
                annotations.append(
                    "    // ID ownership: client-supplied (id present in POST body schema)."
                )
    annotations.extend(f"    {annotation}" for annotation in (extra_annotations or []))

    column_args = [f'name = "{to_snake_case(field.name)}"']
    if field.format == "iso-4217":
        annotations.append("    @JdbcTypeCode(SqlTypes.CHAR)")
        column_args.append('columnDefinition = "CHAR(3)"')
    uuid_column_length = _uuid_column_length(
        metadata=metadata,
        entity=entity,
        field=field,
        is_id=is_id,
    )
    if uuid_column_length is not None:
        column_args.append(f"length = {uuid_column_length}")
        if is_id:
            column_args.append("updatable = false")
    elif (
        field.max_length is not None
        and field.type.value == "string"
        and not is_id
        and field.format != "iso-4217"
    ):
        column_args.append(f"length = {field.max_length}")
    if _field_requires_persistence_constraint(
        metadata=metadata,
        entity=entity,
        field=field,
    ):
        column_args.append("nullable = false")
    annotations.append(f"    @Column({', '.join(column_args)})")

    initializer = ""
    if field.default_value is not None:
        initializer = f" = {_java_literal(field)}"
    source_paths = ", ".join(field.source_paths)
    return [
        "    /**",
        f"     * Source paths: {source_paths}",
        "     */",
        *annotations,
        f"    private {_java_type(field)} {field.name}{initializer};",
    ]


def _uuid_column_length(
    *,
    metadata: MetadataProject | None,
    entity: CanonicalEntity,
    field: CanonicalField,
    is_id: bool,
) -> int | None:
    if _is_server_generated_uuid_string_id(field, is_id=is_id):
        return 36
    if metadata is not None and _is_uuid_reference_field(
        metadata=metadata,
        entity=entity,
        field=field,
    ):
        return 36
    return None


def _is_server_generated_uuid_string_id(
    field: CanonicalField,
    *,
    is_id: bool,
) -> bool:
    if not is_id or field.type != CanonicalFieldType.STRING:
        return False
    if field.id_generation_strategy == IdGenerationStrategy.UUID:
        return True
    if field.id_generation_strategy is not None:
        return False
    return field.server_generated_id


def _uses_application_assigned_ingest_id(
    *,
    metadata: MetadataProject | None,
    entity: CanonicalEntity,
    field: CanonicalField,
    is_id: bool,
) -> bool:
    if metadata is None or not is_id or field.type != CanonicalFieldType.STRING:
        return False
    if not _has_upstream_persistence_id_mapping(
        metadata=metadata,
        entity=entity,
        id_field=field,
    ):
        return False
    if field.id_generation_strategy == IdGenerationStrategy.UUID:
        return True
    if field.id_generation_strategy is not None:
        return False
    return field.server_generated_id


def _has_upstream_persistence_id_mapping(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    id_field: CanonicalField,
) -> bool:
    upstream_ingest_contract_names = {
        contract.name
        for contract in metadata.contracts
        if (
            contract.type in {"file-fixed-width", "file-csv"}
            and contract.file_layout is not None
        )
        or (contract.type == "xml-xsd" and contract.xml_contract is not None)
    }
    target_path = f"{entity.name}.{id_field.name}"
    return any(
        mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
        and mapping.contract_name in upstream_ingest_contract_names
        and mapping.target_path == target_path
        for mapping in metadata.mappings
    )


def _is_uuid_reference_field(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    field: CanonicalField,
) -> bool:
    for relationship in _relationships_for_entity(metadata, entity.name):
        if relationship.source_field != field.name:
            continue
        target_entity = _find_entity_by_name(metadata, relationship.target_entity)
        if target_entity is None:
            continue
        target_id = entity_id_field(target_entity)
        if relationship.target_field != target_id.name:
            continue
        if _is_server_generated_uuid_string_id(target_id, is_id=True):
            return True
    return False


def _render_relationship_field(relationship: CanonicalRelationship) -> list[str]:
    return [
        "    @JsonIgnore",
        "    @ManyToOne(fetch = FetchType.LAZY)",
        (
            "    @JoinColumn("
            f'name = "{to_snake_case(relationship.source_field)}", '
            f'referencedColumnName = "{to_snake_case(relationship.target_field)}", '
            "insertable = false, updatable = false)"
        ),
        f"    private {relationship.target_entity} {relationship.association_name};",
    ]


def _server_set_field_initializers(
    metadata: MetadataProject,
    entity: CanonicalEntity,
) -> list[tuple[CanonicalField, str]]:
    create_request_fields = _create_request_fields(metadata, entity)
    rule_lookup = _entity_rule_lookup(metadata, entity)

    initializers: list[tuple[CanonicalField, str]] = []
    for field in entity.fields:
        if _uses_application_assigned_ingest_id(
            metadata=metadata,
            entity=entity,
            field=field,
            is_id=field.is_id,
        ):
            initializers.append((field, "UUID.randomUUID().toString()"))
            continue
        if field.name in create_request_fields:
            continue
        if not (field.required or field.not_null):
            continue
        literal = _server_initializer_literal(rule_lookup, field)
        if literal is None:
            continue
        initializers.append((field, literal))
    return initializers


def _create_request_fields(
    metadata: MetadataProject,
    entity: CanonicalEntity,
) -> set[str]:
    return {
        canonical_field_name(mapping)
        for mapping in metadata.mappings
        if (
            mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
            and mapping.operation_name is not None
            and _is_create_operation_name(mapping.operation_name)
            and ".request." in mapping.source_path
            and mapping.target_path.startswith(f"{entity.name}.")
        )
    }


def _entity_rule_lookup(
    metadata: MetadataProject,
    entity: CanonicalEntity,
) -> dict[tuple[RuleType, str], object]:
    rule_lookup: dict[tuple[RuleType, str], object] = {}
    for rule in metadata.rules:
        if rule.entity_name != entity.name:
            continue
        rule_lookup.setdefault((rule.type, rule.field_name), rule)
    return rule_lookup


def _server_initializer_literal(
    rule_lookup: dict[tuple[RuleType, str], object],
    field: CanonicalField,
) -> str | None:
    if field.default_value is not None:
        return _java_literal(field)

    default_rule = rule_lookup.get((RuleType.DEFAULT, field.name))
    allowed_values_rule = rule_lookup.get((RuleType.ALLOWED_VALUES, field.name))
    initial_value: str | None = None
    if default_rule is not None and getattr(default_rule, "value", None) is not None:
        initial_value = default_rule.value
    elif allowed_values_rule is not None and getattr(allowed_values_rule, "values", None):
        initial_value = allowed_values_rule.values[0]
    elif field.allowed_values:
        initial_value = field.allowed_values[0]
    if initial_value is None and _is_temporal_server_set_field(field):
        initial_value = "__NOW__"
    if initial_value is None:
        return None
    if initial_value == "__NOW__":
        return _java_now_expression(field)
    return _java_literal(field.model_copy(update={"default_value": initial_value}))


def _entity_has_create_operation(
    metadata: MetadataProject,
    entity: CanonicalEntity,
) -> bool:
    return any(
        _is_create_operation_name(operation.name)
        and (operation.request_entity == entity.name or operation.response_entity == entity.name)
        for operation in metadata.operations
    )


def _field_requires_persistence_constraint(
    *,
    metadata: MetadataProject | None,
    entity: CanonicalEntity,
    field: CanonicalField,
) -> bool:
    if not (field.required or field.not_null):
        return False
    if metadata is None:
        return True
    if not _entity_has_create_operation(metadata, entity):
        return True
    if field.name in _create_request_fields(metadata, entity):
        return True
    if field.is_id and field.server_generated_id:
        return True
    return _server_initializer_literal(_entity_rule_lookup(metadata, entity), field) is not None


def _render_pre_persist_initializer(
    initializers: list[tuple[CanonicalField, str]],
) -> list[str]:
    body = [
        "    @PrePersist",
        "    protected void initializeDefaults() {",
    ]
    for field, literal in initializers:
        body.extend(
            [
                f"        if (this.{field.name} == null) {{",
                f"            this.{field.name} = {literal};",
                "        }",
            ]
        )
    body.append("    }")
    return body


def _java_now_expression(field: CanonicalField) -> str:
    is_date_only = (
        field.type == CanonicalFieldType.DATE
        or _looks_like_date_field_name(field.name)
    )
    now_expr = "LocalDate.now()" if is_date_only else "LocalDateTime.now()"
    if field.type == CanonicalFieldType.STRING:
        return f"{now_expr}.toString()"
    return now_expr


def _is_temporal_server_set_field(field: CanonicalField) -> bool:
    return field.type in (
        CanonicalFieldType.DATETIME,
        CanonicalFieldType.DATE,
    ) or _looks_like_datetime_field_name(field.name) or _looks_like_date_field_name(field.name)


def _looks_like_datetime_field_name(field_name: str) -> bool:
    normalized = field_name.lower()
    return normalized.endswith("datetime") or normalized.endswith("timestamp")


def _looks_like_date_field_name(field_name: str) -> bool:
    normalized = field_name.lower()
    return normalized.endswith("date") and not normalized.endswith("datetime")


def _relationships_for_entity(
    metadata: MetadataProject,
    entity_name: str,
) -> list[CanonicalRelationship]:
    return [
        relationship
        for relationship in metadata.relationships
        if relationship.source_entity == entity_name
    ]


def _audit_collision_metadata(entity: CanonicalEntity) -> tuple[set[str], dict[str, list[str]]]:
    occupied_columns: set[str] = set()
    business_annotations: dict[str, list[str]] = {}
    for field in entity.fields:
        column_name = to_snake_case(field.name)
        occupied_columns.add(column_name)
        audit_spec = _AUDIT_COLUMN_SPECS.get(column_name)
        if audit_spec is not None:
            business_annotations[field.name] = [audit_spec["annotation"]]
    return occupied_columns, business_annotations


def _render_audit_fields(*, skip_columns: set[str] | None = None) -> list[str]:
    skipped = skip_columns or set()
    lines: list[str] = []
    for spec in _AUDIT_FIELD_SPECS:
        if spec["column_name"] in skipped:
            continue
        lines.extend(
            [
                f"    {spec['annotation']}",
                f'    @Column(name = "{spec["column_name"]}")',
                f'    private {"String" if spec["field_name"].endswith("By") else "LocalDateTime"} {spec["field_name"]};',
                "",
            ]
        )
    if lines:
        lines.pop()
    return lines


def _render_audit_getters_and_setters(*, skip_columns: set[str] | None = None) -> list[str]:
    skipped = skip_columns or set()
    lines: list[str] = []
    for spec in _AUDIT_FIELD_SPECS:
        if spec["column_name"] in skipped:
            continue
        java_type = "String" if spec["field_name"].endswith("By") else "LocalDateTime"
        method_suffix = to_pascal_case(spec["field_name"])
        field_name = spec["field_name"]
        lines.extend(
            [
                f"    public {java_type} get{method_suffix}() {{",
                f"        return {field_name};",
                "    }",
                "",
                f"    public void set{method_suffix}({java_type} {field_name}) {{",
                f"        this.{field_name} = {field_name};",
                "    }",
                "",
            ]
        )
    return lines


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

def _render_repository(
    *,
    entity: CanonicalEntity,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    id_type = _java_type(entity_id_field(entity))
    body = [
        f"public interface {entity.name}Repository extends JpaRepository<{entity.name}, {id_type}> {{",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.repository",
        imports=[
            f"{root_package}.domain.{entity.name}",
            "org.springframework.data.jpa.repository.JpaRepository",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------

def _should_emit_generic_fallback_dtos(op_contexts: list[dict]) -> bool:
    return not _uses_explicit_read_surface(op_contexts)


def _fallback_create_request_class(entity: CanonicalEntity) -> str:
    return f"{entity.name}CreateRequest"


def _fallback_update_request_class(entity: CanonicalEntity) -> str:
    return f"{entity.name}UpdateRequest"


def _fallback_response_class(entity: CanonicalEntity) -> str:
    return f"{entity.name}Response"


def _fallback_request_field_mappings(
    metadata: MetadataProject,
    entity: CanonicalEntity,
) -> list[FieldMapping]:
    server_set_fields = {
        field.name for field, _ in _server_set_field_initializers(metadata, entity)
    }
    request_mapped_fields = {
        canonical_field_name(mapping)
        for mapping in metadata.mappings
        if (
            mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
            and ".request." in mapping.source_path
            and mapping.target_path.startswith(f"{entity.name}.")
        )
    }
    mappings: list[FieldMapping] = []
    for field in entity.fields:
        if request_mapped_fields and field.name not in request_mapped_fields:
            continue
        if field.name in server_set_fields:
            continue
        if field.is_id and field.server_generated_id:
            continue
        mappings.append(_fallback_dto_field_mapping(entity, field))
    return mappings


def _fallback_response_field_mappings(entity: CanonicalEntity) -> list[FieldMapping]:
    return [_fallback_dto_field_mapping(entity, field) for field in entity.fields]


def _fallback_dto_field_mapping(
    entity: CanonicalEntity,
    field: CanonicalField,
) -> FieldMapping:
    return FieldMapping(
        contract_name=f"{to_snake_case(entity.name)}-fallback-api",
        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
        source_path=f"{to_snake_case(entity.name)}-fallback-api.{field.name}",
        target_path=f"{entity.name}.{field.name}",
        source_required=field.required or field.not_null,
    )


def _render_dto(
    *,
    class_name: str,
    package_name: str,
    entity: CanonicalEntity,
    field_mappings: list,
    emit_validation_annotations: bool,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    field_mappings = _dedupe_field_mappings(field_mappings)
    entity_fields = {field.name: field for field in entity.fields}
    imports: set[str] = set()
    body = [f"public class {class_name} {{", ""]
    for mapping in field_mappings:
        field_name = canonical_field_name(mapping)
        contract_name = contract_field_name(mapping)
        field = entity_fields.get(field_name) or _transport_wrapper_dto_field(mapping)
        if field is None:
            continue
        java_type = _java_type(field)
        if java_type in JAVA_IMPORTS:
            imports.add(JAVA_IMPORTS[java_type])
        validation_annotations = _field_validation_annotations(field) if emit_validation_annotations else []
        if validation_annotations:
            if any(
                not annotation.startswith("@CodePointLength(")
                for annotation in validation_annotations
            ):
                imports.add("jakarta.validation.constraints.*")
            if any(
                annotation.startswith("@CodePointLength(")
                for annotation in validation_annotations
            ):
                imports.add("org.hibernate.validator.constraints.CodePointLength")
            body.extend(f"    {annotation}" for annotation in validation_annotations)
        if _dto_needs_explicit_json_property(field_name, contract_name):
            imports.add("com.fasterxml.jackson.annotation.JsonProperty")
            body.append(f"    @JsonProperty(\"{contract_name}\")")
        body.append(f"    private {java_type} {field_name};")
        body.append("")
    body.extend(
        [
            f"    public {class_name}() {{",
            "    }",
            "",
        ]
    )
    for mapping in field_mappings:
        field_name = canonical_field_name(mapping)
        contract_name = contract_field_name(mapping)
        field = entity_fields.get(field_name) or _transport_wrapper_dto_field(mapping)
        if field is None:
            continue
        java_type = _java_type(field)
        method_suffix = to_pascal_case(field_name)
        property_annotation = (
            [f'    @JsonProperty("{contract_name}")']
            if _dto_needs_explicit_json_property(field_name, contract_name) else []
        )
        body.extend(
            property_annotation + [
                f"    public {java_type} get{method_suffix}() {{",
                f"        return {field_name};",
                "    }",
                "",
            ] + property_annotation + [
                f"    public void set{method_suffix}({java_type} {field_name}) {{",
                f"        this.{field_name} = {field_name};",
                "    }",
                "",
            ]
        )
    body.append("}")
    return _java_file(
        package_name=package_name,
        imports=sorted(imports),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _dedupe_field_mappings(field_mappings: list[FieldMapping]) -> list[FieldMapping]:
    deduped: OrderedDict[str, FieldMapping] = OrderedDict()
    for mapping in field_mappings:
        deduped.setdefault(canonical_field_name(mapping), mapping)
    return list(deduped.values())


def _dedupe_operation_contexts(entity_name: str, op_contexts: list[dict]) -> list[dict]:
    deduped: OrderedDict[tuple[str, str, str], dict] = OrderedDict()
    for ctx in op_contexts:
        key = (
            ctx["java_operation_name"],
            ctx["request_class_name"],
            ctx["response_class_name"],
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = ctx
            continue
        deduped[key] = _select_operation_context(
            entity_name=entity_name,
            key=key,
            existing=existing,
            candidate=ctx,
        )
    return list(deduped.values())


def _select_operation_context(
    *,
    entity_name: str,
    key: tuple[str, str, str],
    existing: dict,
    candidate: dict,
) -> dict:
    existing_mapped = _operation_context_has_explicit_mappings(existing)
    candidate_mapped = _operation_context_has_explicit_mappings(candidate)
    if existing_mapped and not candidate_mapped:
        return existing
    if candidate_mapped and not existing_mapped:
        return candidate

    if _operation_context_mapping_signature(existing) != _operation_context_mapping_signature(candidate):
        raise ValueError(
            "Duplicate REST operation contexts for entity "
            f"'{entity_name}' normalize to Java operation '{key[0]}' and DTOs "
            f"'{key[1]}'/'{key[2]}', but interfaces "
            f"'{existing.get('interface_name')}' and '{candidate.get('interface_name')}' "
            "declare conflicting explicit mappings."
        )
    if _operation_context_route_signature(existing) != _operation_context_route_signature(candidate):
        raise ValueError(
            "Duplicate REST operation contexts for entity "
            f"'{entity_name}' normalize to Java operation '{key[0]}' and DTOs "
            f"'{key[1]}'/'{key[2]}', but interfaces "
            f"'{existing.get('interface_name')}' and '{candidate.get('interface_name')}' "
            "declare incompatible routes."
        )
    return existing


def _operation_context_has_explicit_mappings(ctx: dict) -> bool:
    return bool(ctx.get("request_field_mappings") or ctx.get("response_field_mappings"))


def _operation_context_mapping_signature(ctx: dict) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    return (
        _field_mapping_semantic_signature(ctx.get("request_field_mappings") or []),
        _field_mapping_semantic_signature(ctx.get("response_field_mappings") or []),
    )


def _field_mapping_semantic_signature(mappings: list[FieldMapping]) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (
                _rest_operation_mapping_source_leaf(mapping.source_path),
                mapping.target_path,
            )
            for mapping in mappings
        )
    )


def _rest_operation_mapping_source_leaf(source_path: str) -> str:
    for marker in (".request.", ".response."):
        if marker in source_path:
            return source_path.split(marker, 1)[1]
    return source_path


def _operation_context_route_signature(ctx: dict) -> tuple:
    return (
        _context_value(ctx.get("http_method")),
        ctx.get("spec_path") or "",
        ctx.get("path") or "",
        _context_value(ctx.get("response_shape")),
        bool(ctx.get("pageable")),
        tuple(_operation_parameter_signature_value(param) for param in ctx.get("path_parameters", [])),
        tuple(_operation_parameter_signature_value(param) for param in ctx.get("operation_parameters", [])),
    )


def _operation_parameter_signature_value(param: object) -> tuple:
    return (
        getattr(param, "name", ""),
        _context_value(getattr(param, "location", "")),
        _context_value(getattr(param, "type", "")),
        bool(getattr(param, "required", False)),
    )


def _context_value(value: object) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


_TRANSPORT_WRAPPER_DTO_FIELD_NAMES = frozenset(
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


def _transport_wrapper_dto_field(mapping: FieldMapping) -> CanonicalField | None:
    """Create DTO-only fields for response envelope/page metadata."""

    if mapping.direction != MappingDirection.UPSTREAM_TO_CANONICAL:
        return None
    if ".response." not in mapping.source_path:
        return None
    field_name = canonical_field_name(mapping)
    normalized_name = _normalize_transport_wrapper_field_name(field_name)
    if normalized_name not in _TRANSPORT_WRAPPER_DTO_FIELD_NAMES:
        return None
    field_type = (
        CanonicalFieldType.INTEGER
        if normalized_name
        in {"currentpage", "pagesize", "totalelements", "totalpages", "totalitems"}
        else CanonicalFieldType.STRING
    )
    return CanonicalField(name=field_name, type=field_type, required=False)


def _normalize_transport_wrapper_field_name(field_name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", field_name.lower())


# ---------------------------------------------------------------------------
# Controller — full CRUD: POST, GET/{id}, GET-list, PUT/{id}, DELETE/{id}
# ---------------------------------------------------------------------------

def _render_controller(
    *,
    entity: CanonicalEntity,
    root_package: str,
    op_contexts: list[dict],
    entity_path_base: str,
    id_java_type: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    _validate_computed_read_contexts(entity, op_contexts)
    entity_var = entity.name[:1].lower() + entity.name[1:]
    service_var = f"{entity_var}Service"
    spec_route_base = _common_spec_route_base(op_contexts)
    from .write_contract import validate_write_context
    for context in op_contexts:
        validate_write_context(entity, context, spec_route_base)
    controller_route_base = spec_route_base or entity_path_base
    explicit_read_surface = _uses_explicit_read_surface(op_contexts)

    imports: set[str] = {
        f"{root_package}.domain.{entity.name}",
        f"{root_package}.exception.ResourceNotFoundException",
        f"{root_package}.service.{entity.name}Service",
        "java.util.List",
        "org.springframework.http.HttpStatus",
        "org.springframework.http.ResponseEntity",
        "org.springframework.web.bind.annotation.DeleteMapping",
        "org.springframework.web.bind.annotation.GetMapping",
        "org.springframework.web.bind.annotation.PathVariable",
        "org.springframework.web.bind.annotation.PostMapping",
        "org.springframework.web.bind.annotation.PutMapping",
        "org.springframework.web.bind.annotation.RequestBody",
        "org.springframework.web.bind.annotation.RequestMapping",
        "org.springframework.web.bind.annotation.RestController",
    }
    for ctx in op_contexts:
        imports.add(f"{root_package}.adapter.inbound.{ctx['request_class_name']}")
        imports.add(f"{root_package}.adapter.inbound.{ctx['response_class_name']}")
    if _should_emit_generic_fallback_dtos(op_contexts):
        if _should_emit_generic_create_fallback(op_contexts):
            imports.add(f"{root_package}.adapter.inbound.{_fallback_create_request_class(entity)}")
        imports.add(f"{root_package}.adapter.inbound.{_fallback_update_request_class(entity)}")
        imports.add(f"{root_package}.adapter.inbound.{_fallback_response_class(entity)}")
    get_ctx = None if explicit_read_surface else _find_get_by_id_context(op_contexts)
    list_ctx = None if explicit_read_surface else _find_list_context(op_contexts)
    additional_contexts = _additional_operation_contexts(op_contexts)
    _add_operation_parameter_controller_imports(imports, get_ctx)
    _add_operation_parameter_controller_imports(imports, list_ctx)
    for ctx in additional_contexts:
        _add_operation_parameter_controller_imports(imports, ctx)
    has_pageable_methods = any(
        _is_pageable_list_context(ctx) for ctx in [list_ctx, *additional_contexts]
    )
    if has_pageable_methods:
        imports.update(
            {
                "org.springframework.data.domain.Page",
                "org.springframework.data.domain.PageRequest",
                "org.springframework.data.domain.Pageable",
                "org.springframework.web.bind.annotation.RequestParam",
            }
        )

    body: list[str] = [
        "@RestController",
        f"@RequestMapping(\"{controller_route_base}\")",
        f"public class {entity.name}Controller {{",
    ]
    if has_pageable_methods:
        body.extend(
            [
                "",
                "    private static final int MAX_PAGE_SIZE = 200;",
                "    private static final long MAX_PAGE_OFFSET = 50_000L;",
            ]
        )
    body.extend(
        [
            "",
            f"    private final {entity.name}Service {service_var};",
            "",
            f"    public {entity.name}Controller({entity.name}Service {service_var}) {{",
            f"        this.{service_var} = {service_var};",
            "    }",
        ]
    )

    # --- POST /entities → create → 201 + created entity ---
    create_ctx = _find_create_context(op_contexts)
    update_ctx = _find_update_context(op_contexts)
    delete_ctx = next((ctx for ctx in op_contexts if _operation_category(ctx) == "delete"), None)
    for context in (create_ctx, update_ctx, delete_ctx):
        _add_operation_parameter_controller_imports(imports, context)
    if create_ctx or update_ctx or any(_operation_category(ctx) == "state_transition" for ctx in additional_contexts):
        imports.add("jakarta.validation.Valid")
    if _should_emit_generic_create_fallback(op_contexts) or (not explicit_read_surface and update_ctx is None):
        imports.add("jakarta.validation.Valid")
    if create_ctx:
        req_class = create_ctx["request_class_name"]
        resp_class = create_ctx["response_class_name"]
        method_name = create_ctx["java_operation_name"]
        create_route_suffix = _controller_method_route_suffix(
            create_ctx,
            entity_path_base=entity_path_base,
            spec_route_base=spec_route_base,
        )
        body.extend([
            "",
            "    // POST " + _join_controller_route(controller_route_base, create_route_suffix) + " — create entity, returns 201 + created resource",
            _mapping_annotation("PostMapping", create_route_suffix),
            f"    public ResponseEntity<{resp_class}> {method_name}({', '.join([*_spring_parameter_signature(create_ctx.get('operation_parameters', [])), f'@Valid @RequestBody {req_class} request'])}) {{",
            f"        {resp_class} created = {service_var}.{method_name}({', '.join([*_operation_parameter_argument_names(create_ctx), 'request'])});",
            "        return ResponseEntity.status(HttpStatus.CREATED).body(created);",
            "    }",
        ])
    elif _should_emit_generic_create_fallback(op_contexts):
        # No mapped create operation — emit a generic create stub using all entity fields
        body.extend(_render_generic_create_method(
            entity=entity,
            entity_path_base=controller_route_base,
            service_var=service_var,
        ))

    # --- GET /entities/{id} → getById → 200 or 404 ---
    if not explicit_read_surface:
        get_response_type = (
            _operation_response_type(get_ctx, entity.name)
            if _has_response_mappings(get_ctx)
            else _fallback_response_class(entity)
        )
        get_route_suffix = _controller_method_route_suffix(
            get_ctx,
            entity_path_base=entity_path_base,
            spec_route_base=spec_route_base,
            default_suffix="/{id}",
        )
        get_path_variable_name = _controller_path_variable_name(get_ctx, spec_route_base) or "id"
        get_method_params = (
            _operation_path_variable_controller_signatures(get_ctx, id_java_type=id_java_type)
            if get_ctx and _supports_spec_route(get_ctx)
            else [_controller_path_variable_signature(get_ctx, spec_route_base, id_java_type)]
        )
        if get_ctx:
            get_method_params.extend(_spring_parameter_signature(get_ctx["operation_parameters"]))
        get_service_args = [
            _verified_read_id_argument_name(entity, get_ctx) if get_ctx else get_path_variable_name,
            *_operation_parameter_argument_names(get_ctx),
        ]
        body.extend([
            "",
            "    // GET " + _join_controller_route(controller_route_base, get_route_suffix) + " — retrieve single entity by ID, 404 if missing",
            _mapping_annotation("GetMapping", get_route_suffix),
            f"    public ResponseEntity<{get_response_type}> getById({', '.join(get_method_params)}) {{",
            f"        {get_response_type} response = {service_var}.findById({', '.join(get_service_args)});",
            "        return ResponseEntity.ok(response);",
            "    }",
        ])

    # --- GET /entities → listAll → 200 + List ---
    if not explicit_read_surface:
        list_response_type = (
            _operation_response_type(list_ctx, entity.name)
            if _has_response_mappings(list_ctx)
            else _fallback_response_class(entity)
        )
        list_method_params = _spring_parameter_signature(list_ctx["operation_parameters"]) if list_ctx else []
        list_service_args = _operation_parameter_argument_names(list_ctx)
        list_route_suffix = _controller_method_route_suffix(
            list_ctx, entity_path_base=entity_path_base, spec_route_base=spec_route_base,
        )
        if _is_pageable_list_context(list_ctx):
            pageable_params = [
                '@RequestParam(defaultValue = "0") int page',
                '@RequestParam(defaultValue = "20") int size',
            ]
            method_params = [*list_method_params, *pageable_params]
            body.extend([
                "",
                "    // GET " + controller_route_base + " — list entities with offset/limit pagination",
                _mapping_annotation("GetMapping", list_route_suffix),
                f"    public ResponseEntity<Page<{list_response_type}>> listAll({', '.join(method_params)}) {{",
                "        Pageable pageable = PageRequest.of(page, size);",
                *_render_pageable_guard_lines(),
                f"        return ResponseEntity.ok({service_var}.findAll({', '.join([*list_service_args, 'pageable'])}));",
                "    }",
            ])
        else:
            body.extend([
                "",
                "    // GET " + controller_route_base + " — list all entities",
                _mapping_annotation("GetMapping", list_route_suffix),
                f"    public ResponseEntity<List<{list_response_type}>> listAll({', '.join(list_method_params)}) {{"
                if list_method_params
                else f"    public ResponseEntity<List<{list_response_type}>> listAll() {{",
                f"        return ResponseEntity.ok({service_var}.findAll({', '.join(list_service_args)}));"
                if list_service_args
                else f"        return ResponseEntity.ok({service_var}.findAll());",
                "    }",
            ])

    # --- PUT /entities/{id} → update → 200 + updated entity ---
    if update_ctx:
        update_req_class = update_ctx["request_class_name"]
        update_resp_class = _operation_response_type(update_ctx, entity.name)
        update_method_name = update_ctx["java_operation_name"]
        body.extend([
            "",
            "    // PUT " + controller_route_base + "/{id} — full update, path id takes precedence",
            "    @PutMapping(\"/{id}\")",
            f"    public ResponseEntity<{update_resp_class}> {update_method_name}(",
            f"            @PathVariable {id_java_type} id,",
            *[f"            {parameter}," for parameter in _spring_parameter_signature(update_ctx.get("operation_parameters", []))],
            f"            @Valid @RequestBody {update_req_class} request) {{",
            f"        {update_resp_class} updated = {service_var}.{update_method_name}({', '.join(['id', *_operation_parameter_argument_names(update_ctx), 'request'])});",
            "        return ResponseEntity.ok(updated);",
            "    }",
        ])
    elif not explicit_read_surface:
        fallback_response_class = _fallback_response_class(entity)
        fallback_update_class = _fallback_update_request_class(entity)
        body.extend([
            "",
            "    // PUT " + controller_route_base + "/{id} — full update, path id takes precedence",
            "    @PutMapping(\"/{id}\")",
            f"    public ResponseEntity<{fallback_response_class}> update(",
            f"            @PathVariable {id_java_type} id,",
            f"            @Valid @RequestBody {fallback_update_class} request) {{",
            f"        {fallback_response_class} updated = {service_var}.update(id, request);",
            "        return ResponseEntity.ok(updated);",
            "    }",
        ])

    # --- DELETE /entities/{id} → delete → 204 ---
    if not explicit_read_surface:
        body.extend([
            "",
            "    // DELETE " + controller_route_base + "/{id} — delete entity, returns 204 No Content",
            "    @DeleteMapping(\"/{id}\")",
            f"    public ResponseEntity<Void> delete({', '.join([f'@PathVariable {id_java_type} id', *_spring_parameter_signature(delete_ctx.get('operation_parameters', []) if delete_ctx else [])])}) {{",
            f"        {service_var}.delete({', '.join(['id', *_operation_parameter_argument_names(delete_ctx)])});",
            "        return ResponseEntity.noContent().build();",
            "    }",
        ])

    for ctx in additional_contexts:
        category = _operation_category(ctx)
        method_name = ctx["java_operation_name"]
        route_suffix = _non_crud_route_suffix(ctx, controller_route_base=controller_route_base)
        path_variable_params = _operation_path_variable_controller_signatures(
            ctx,
            id_java_type=id_java_type,
        )
        operation_params = _spring_parameter_signature(ctx.get("operation_parameters", []))
        service_args = [
            *_operation_path_variable_argument_names(ctx),
            *_operation_parameter_argument_names(ctx),
        ]

        if category == "state_transition":
            req_class = ctx["request_class_name"]
            resp_class = ctx["response_class_name"]
            method_params = [*path_variable_params, *operation_params, f"@Valid @RequestBody {req_class} request"]
            body.extend([
                "",
                "    // "
                + _non_crud_http_method(category)
                + " "
                + _join_controller_route(controller_route_base, route_suffix)
                + " — preserved state transition operation",
                _mapping_annotation("PostMapping", route_suffix),
                f"    public ResponseEntity<{resp_class}> {method_name}({', '.join(method_params)}) {{",
                f"        return ResponseEntity.ok({service_var}.{method_name}({', '.join([*service_args, 'request'])}));",
                "    }",
            ])
        elif category == "read_list":
            resp_class = ctx["response_class_name"]
            method_params = [*path_variable_params, *operation_params]
            if _is_pageable_list_context(ctx):
                pageable_params = [
                    '@RequestParam(defaultValue = "0") int page',
                    '@RequestParam(defaultValue = "20") int size',
                ]
                body.extend([
                    "",
                    "    // "
                    + _non_crud_http_method(category)
                    + " "
                    + _join_controller_route(controller_route_base, route_suffix)
                    + " — preserved non-CRUD list read with offset/limit pagination",
                    _mapping_annotation("GetMapping", route_suffix),
                    f"    public ResponseEntity<Page<{resp_class}>> {method_name}({', '.join([*method_params, *pageable_params])}) {{",
                    "        Pageable pageable = PageRequest.of(page, size);",
                    *_render_pageable_guard_lines(),
                    f"        return ResponseEntity.ok({service_var}.{method_name}({', '.join([*service_args, 'pageable'])}));",
                    "    }",
                ])
            else:
                body.extend([
                    "",
                    "    // "
                    + _non_crud_http_method(category)
                    + " "
                    + _join_controller_route(controller_route_base, route_suffix)
                    + " — preserved non-CRUD list read",
                    _mapping_annotation("GetMapping", route_suffix),
                    f"    public ResponseEntity<List<{resp_class}>> {method_name}({', '.join(method_params)}) {{"
                    if method_params
                    else f"    public ResponseEntity<List<{resp_class}>> {method_name}() {{",
                    f"        return ResponseEntity.ok({service_var}.{method_name}({', '.join(service_args)}));"
                    if service_args
                    else f"        return ResponseEntity.ok({service_var}.{method_name}());",
                    "    }",
                ])
        elif category == "list":
            resp_class = ctx["response_class_name"]
            method_params = operation_params
            if _is_pageable_list_context(ctx):
                pageable_params = [
                    '@RequestParam(defaultValue = "0") int page',
                    '@RequestParam(defaultValue = "20") int size',
                ]
                body.extend([
                    "",
                    "    // "
                    + _non_crud_http_method(category)
                    + " "
                    + _join_controller_route(controller_route_base, route_suffix)
                    + " — preserved list read operation with offset/limit pagination",
                    _mapping_annotation("GetMapping", route_suffix),
                    f"    public ResponseEntity<Page<{resp_class}>> {method_name}({', '.join([*method_params, *pageable_params])}) {{",
                    "        Pageable pageable = PageRequest.of(page, size);",
                    *_render_pageable_guard_lines(),
                    f"        return ResponseEntity.ok({service_var}.{method_name}({', '.join([*service_args, 'pageable'])}));",
                    "    }",
                ])
            else:
                body.extend([
                    "",
                    "    // "
                    + _non_crud_http_method(category)
                    + " "
                    + _join_controller_route(controller_route_base, route_suffix)
                    + " — preserved list read operation",
                    _mapping_annotation("GetMapping", route_suffix),
                    f"    public ResponseEntity<List<{resp_class}>> {method_name}({', '.join(method_params)}) {{"
                    if method_params
                    else f"    public ResponseEntity<List<{resp_class}>> {method_name}() {{",
                    f"        return ResponseEntity.ok({service_var}.{method_name}({', '.join(service_args)}));"
                    if service_args
                    else f"        return ResponseEntity.ok({service_var}.{method_name}());",
                    "    }",
                ])
        elif category == "get_by_id":
            resp_class = ctx["response_class_name"]
            method_params = [*path_variable_params, *operation_params]
            body.extend([
                "",
                "    // "
                + _non_crud_http_method(category)
                + " "
                + _join_controller_route(controller_route_base, route_suffix)
                + " — preserved single read operation",
                _mapping_annotation("GetMapping", route_suffix),
                f"    public ResponseEntity<{resp_class}> {method_name}({', '.join(method_params)}) {{"
                if method_params
                else f"    public ResponseEntity<{resp_class}> {method_name}() {{",
                f"        return ResponseEntity.ok({service_var}.{method_name}({', '.join(service_args)}));"
                if service_args
                else f"        return ResponseEntity.ok({service_var}.{method_name}());",
                "    }",
            ])
        elif category == "computed_read":
            resp_class = ctx["response_class_name"]
            method_params = [*path_variable_params, *operation_params]
            body.extend([
                "",
                "    // "
                + _non_crud_http_method(category)
                + " "
                + _join_controller_route(controller_route_base, route_suffix)
                + " — preserved computed read operation",
                _mapping_annotation("GetMapping", route_suffix),
                f"    public ResponseEntity<{resp_class}> {method_name}({', '.join(method_params)}) {{"
                if method_params
                else f"    public ResponseEntity<{resp_class}> {method_name}() {{",
                f"        return ResponseEntity.ok({service_var}.{method_name}({', '.join(service_args)}));"
                if service_args
                else f"        return ResponseEntity.ok({service_var}.{method_name}());",
                "    }",
            ])

    body.append("}")

    return _java_file(
        package_name=f"{root_package}.adapter.inbound",
        imports=sorted(imports),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_generic_create_method(
    *,
    entity: CanonicalEntity,
    entity_path_base: str,
    service_var: str,
) -> list[str]:
    """Fallback create stub when no DTO operation context was mapped."""
    request_class = _fallback_create_request_class(entity)
    response_class = _fallback_response_class(entity)
    return [
        "",
        "    // POST " + entity_path_base + " — create entity, returns 201 + created resource",
        "    @PostMapping",
        f"    public ResponseEntity<{response_class}> create(@Valid @RequestBody {request_class} request) {{",
        f"        {response_class} created = {service_var}.create(request);",
        "        return ResponseEntity.status(HttpStatus.CREATED).body(created);",
        "    }",
    ]


def _find_create_context(op_contexts: list[dict]) -> dict | None:
    """Return the first create op, or the lone opaque op for legacy generic scaffolds."""
    for ctx in op_contexts:
        if _operation_category(ctx) == "create":
            return ctx
    if op_contexts and all(_operation_category(ctx) is None for ctx in op_contexts):
        return op_contexts[0]
    return None


def _should_emit_generic_create_fallback(op_contexts: list[dict]) -> bool:
    """Emit the generic create stub only when no operation contexts exist."""
    return not op_contexts


def _find_update_context(op_contexts: list[dict]) -> dict | None:
    """Return the first PUT/update op context, if any."""
    for ctx in op_contexts:
        if _operation_category(ctx) == "update":
            return ctx
    return None


def _has_response_mappings(ctx: dict | None) -> bool:
    return bool(ctx and ctx.get("response_field_mappings"))


def _operation_response_type(ctx: dict | None, fallback_entity_name: str) -> str:
    if _has_response_mappings(ctx):
        return ctx["response_class_name"]
    return fallback_entity_name


def _find_get_by_id_context(op_contexts: list[dict]) -> dict | None:
    for ctx in op_contexts:
        if _operation_category(ctx) == "get_by_id":
            return ctx
    return None


def _has_create_operation(op_contexts: list[dict]) -> bool:
    return any(_operation_category(ctx) == "create" for ctx in op_contexts)


def _uses_explicit_read_surface(op_contexts: list[dict]) -> bool:
    if not op_contexts or _has_create_operation(op_contexts):
        return False
    categories = {_operation_category(ctx) for ctx in op_contexts}
    if categories.intersection({"update", "delete", "state_transition"}):
        return False
    return bool(categories.intersection({"get_by_id", "list", "computed_read", "read_list"}))


def _additional_operation_contexts(op_contexts: list[dict]) -> list[dict]:
    if _uses_explicit_read_surface(op_contexts):
        return [
            ctx
            for ctx in op_contexts
            if _operation_category(ctx) in {"get_by_id", "list", "computed_read", "read_list"}
        ]
    return _find_non_crud_contexts(op_contexts)


def _common_spec_route_base(op_contexts: list[dict]) -> str | None:
    if not op_contexts:
        return None
    from appbuilder.generation.utils import compatible_read_route_base

    candidate_bases = [
        (base, ctx.get("http_method") == HttpMethod.GET and ctx.get("response_shape") == ResponseShape.LIST)
        for ctx in op_contexts
        if (
            base := _spec_entity_route_base_candidate(
                path=ctx.get("spec_path"),
                http_method=ctx.get("http_method"),
                response_shape=ctx.get("response_shape"),
                path_parameter_count=len(ctx.get("path_parameters", [])),
            )
        )
    ]
    return compatible_read_route_base(candidate_bases)


def _supports_spec_route(ctx: dict | None) -> bool:
    if not ctx:
        return False
    return _supports_spec_route_helper(
        path=ctx.get("spec_path"),
        http_method=ctx.get("http_method"),
        response_shape=ctx.get("response_shape"),
        path_parameter_count=len(ctx.get("path_parameters", [])),
    )


def _controller_method_route_suffix(
    ctx: dict | None,
    *,
    entity_path_base: str,
    spec_route_base: str | None,
    default_suffix: str = "",
) -> str:
    if spec_route_base is None or not _supports_spec_route(ctx):
        return default_suffix
    spec_path = ctx.get("spec_path")
    if not spec_path:
        return default_suffix
    suffix = spec_path[len(spec_route_base):]
    if suffix in {"", "/"}:
        return ""
    return suffix


def _controller_path_variable_name(ctx: dict | None, spec_route_base: str | None) -> str | None:
    if spec_route_base is None or not _supports_spec_route(ctx):
        return None
    path_parameters = ctx.get("path_parameters", [])
    if len(path_parameters) != 1:
        return None
    return _java_parameter_name(path_parameters[0].name)


def _controller_path_variable_signature(
    ctx: dict | None,
    spec_route_base: str | None,
    id_java_type: str,
) -> str:
    if spec_route_base is None or not _supports_spec_route(ctx):
        return f"@PathVariable {id_java_type} id"
    path_parameters = ctx.get("path_parameters", [])
    if len(path_parameters) != 1:
        return f"@PathVariable {id_java_type} id"
    contract_name = path_parameters[0].name
    java_name = _java_parameter_name(contract_name)
    return f"@PathVariable(\"{contract_name}\") {id_java_type} {java_name}"


def _mapping_annotation(annotation_name: str, route_suffix: str) -> str:
    if not route_suffix:
        return f"    @{annotation_name}"
    return f"    @{annotation_name}(\"{route_suffix}\")"


def _join_controller_route(base_path: str, route_suffix: str) -> str:
    if not route_suffix:
        return base_path
    return f"{base_path}{route_suffix}"


def _find_list_context(op_contexts: list[dict]) -> dict | None:
    for ctx in op_contexts:
        if _operation_category(ctx) == "list":
            return ctx
    return None


def _find_non_crud_contexts(op_contexts: list[dict]) -> list[dict]:
    return [
        ctx for ctx in op_contexts
        if _operation_category(ctx) in {"state_transition", "computed_read", "read_list"}
    ]


def _is_pageable_list_context(ctx: dict | None) -> bool:
    if not ctx or not ctx.get("pageable"):
        return False
    return _operation_category(ctx) in {"list", "read_list"}


def _render_pageable_guard_lines() -> list[str]:
    return [
        "        if (size > MAX_PAGE_SIZE) {",
        '            throw new IllegalArgumentException("size must not exceed " + MAX_PAGE_SIZE);',
        "        }",
        "        if (pageable.getOffset() > MAX_PAGE_OFFSET) {",
        "            throw new IllegalArgumentException(",
        '                "page offset must not exceed " + MAX_PAGE_OFFSET',
        "            );",
        "        }",
    ]


def _operation_category(ctx: dict | None) -> str | None:
    if not ctx:
        return None

    http_method = ctx.get("http_method")
    response_shape = ctx.get("response_shape")
    operation_name = str(ctx.get("operation_name", ""))
    lower_name = operation_name.lower()
    path_parameters = list(ctx.get("path_parameters", []))
    spec_path = ctx.get("spec_path")

    if response_shape == ResponseShape.CREATED or _is_create_operation_name(operation_name):
        return "create"
    if http_method == HttpMethod.PUT or lower_name.startswith("update"):
        return "update"
    if http_method == HttpMethod.DELETE or lower_name.startswith(("delete", "remove")):
        return "delete"
    if http_method == HttpMethod.GET and response_shape == ResponseShape.SINGLE:
        if (
            path_parameters
            and lower_name.startswith(("get", "fetch", "find", "read", "retrieve"))
            and ((spec_path and re.fullmatch(r".*/\{[^/]+\}", spec_path)) or not spec_path)
        ):
            return "get_by_id"
        return "computed_read"
    if http_method == HttpMethod.GET and response_shape == ResponseShape.LIST:
        if not path_parameters and lower_name.startswith(
            ("list", "get", "fetch", "find", "retrieve")
        ):
            return "list"
        return "read_list"
    if http_method == HttpMethod.POST:
        return "state_transition"
    return None


def _computed_read_id_argument_name(entity: CanonicalEntity, ctx: dict) -> str:
    path_parameters = list(ctx.get("path_parameters", []))
    declared_ids = [field for field in entity.fields if field.is_id]
    spec_path = ctx.get("spec_path")
    if len(declared_ids) == 1:
        id_field = declared_ids[0]
        id_type = _java_type(id_field)
        # This is the existing Engine resource layout, not an inferred contract alias.
        entity_id_route = f"/{to_snake_case(entity.name)}s/{{{id_field.name}}}"
        static_path = (spec_path or "").replace(f"{{{id_field.name}}}", "")
        resource_bound = not spec_path or (
            spec_path.startswith("/")
            and not spec_path.startswith("//")
            and not spec_path.endswith("//")
            and re.search(re.escape(entity_id_route) + r"(?:/|$)", spec_path) is not None
            and all(segment not in {"", ".", ".."} for segment in spec_path.strip("/").split("/"))
            and not any(character in static_path for character in ("%", "\\", "?", "#", "*", "{", "}", ";"))
        )
        requirement = (
            f"exactly one path parameter named '{id_field.name}' with type '{id_type}', "
            f"bound once directly after the entity collection in '{entity_id_route}', "
            "with only static literal prefix/suffix segments and no selection parameters; "
            "custom resource aliases, route patterns and matrix parameters are unsupported"
        )
        if (
            len(path_parameters) == 1
            and path_parameters[0].name == id_field.name
            and (path_parameters[0].type or id_type) == id_type
            and all(
                parameter.location == OperationParameterLocation.HEADER
                and parameter.read_input_role in {"metadata", "gateway-rate-limit"}
                for parameter in ctx.get("operation_parameters", [])
            )
            and resource_bound
            and (not spec_path or re.findall(r"\{([^}]+)\}", spec_path) == [id_field.name])
        ):
            # Legacy contexts expose the validated identifier as the Java argument `id`.
            return _java_parameter_name(id_field.name) if spec_path else "id"
    else:
        requirement = "exactly one explicitly declared entity ID field and its sole path parameter"
    received = ", ".join(parameter.name for parameter in path_parameters) or "none"
    raise ValueError(
        f"Computed read operation '{ctx['operation_name']}' "
        f"on interface '{ctx.get('interface_name', 'unspecified')}' "
        f"for entity '{entity.name}' has no supported path-parameter ID lookup: "
        f"requires {requirement}; received path '{spec_path or '(Engine default route)'}' "
        f"with path parameters [{received}]. "
        "Owner-scoped, nested, query/header-filtered and collection-derived computed lookups "
        "are not supported. Use a supported ID-based read or remove the unsupported operation."
    )


def _validate_computed_read_contexts(entity: CanonicalEntity, op_contexts: list[dict]) -> None:
    read_routes: dict[str, str] = {}
    route_base = _common_spec_route_base(op_contexts)
    if not _uses_explicit_read_surface(op_contexts):
        for category in ("get_by_id", "list"):
            contexts = [ctx for ctx in op_contexts if _operation_category(ctx) == category]
            if len({(ctx["java_operation_name"], ctx.get("spec_path")) for ctx in contexts}) > 1:
                _refuse_read(entity, contexts[1], "multiple selected CRUD reads of the same kind cannot be emitted faithfully")
    for ctx in op_contexts:
        category = _operation_category(ctx)
        if ctx.get("http_method") != HttpMethod.GET:
            continue
        if category == "computed_read":
            _computed_read_id_argument_name(entity, ctx)
        _validate_read_inputs(entity, ctx)
        if category is None and ctx.get("response_shape") is None and not ctx.get("spec_path"):
            if ctx.get("path_parameters") or ctx.get("request_field_mappings") or ctx.get("operation_parameters"):
                _refuse_read(entity, ctx, "legacy read inputs have no supported binding")
            # Sample-only metadata does not declare a REST read route. Its
            # existing generic CRUD surface has explicit Engine ID/list inputs.
            continue
        if category not in {"get_by_id", "computed_read", "list", "read_list"}:
            _refuse_read(entity, ctx, "GET dispatch does not implement a supported read")
        if category in {"get_by_id", "computed_read"}:
            _verified_read_id_argument_name(entity, ctx)
        elif ctx.get("path_parameters") or ctx.get("request_field_mappings"):
            _refuse_read(entity, ctx, "collection selection inputs are not implemented")
        path = ctx.get("spec_path")
        if path:
            _validate_read_route(entity, ctx, route_base)
            signature = re.sub(r"\{[^}]+\}", "{}", path)
            existing = read_routes.get(signature)
            if existing and existing != ctx["java_operation_name"]:
                _refuse_read(entity, ctx, "read route collides with another selected read")
            read_routes[signature] = ctx["java_operation_name"]
            if not _uses_explicit_read_surface(op_contexts) and category in {"computed_read", "read_list"}:
                base = route_base or f"/{to_snake_case(entity.name)}s"
                if signature in {base, base + "/{}"}:
                    _refuse_read(entity, ctx, "read route collides with a generated fallback CRUD read")


def _refuse_read(entity: CanonicalEntity, ctx: dict, reason: str) -> None:
    raise ValueError(
        f"Read operation '{ctx['operation_name']}' on interface "
        f"'{ctx.get('interface_name', 'unspecified')}' for entity '{entity.name}' "
        f"is unsupported: {reason}. Use an unambiguous own-persistence-ID read, "
        "an unfiltered collection with optional Engine pagination, or remove the "
        "unsupported selector. Ordinary metadata headers require an explicit "
        "x-edgeforge-read-input-role declaration."
    )


def _validate_read_inputs(entity: CanonicalEntity, ctx: dict) -> None:
    from appbuilder.generation.utils import JAVA_RESERVED_IDENTIFIERS

    if ctx.get("read_input_errors"):
        _refuse_read(entity, ctx, "; ".join(ctx["read_input_errors"]))
    if ctx.get("has_request_body"):
        _refuse_read(entity, ctx, "declared request-body selection is not implemented")
    argument_names = {_java_parameter_name(parameter.name) for parameter in ctx.get("path_parameters", [])}
    response_class = ctx.get("response_class_name", _fallback_response_class(entity))
    entity_var = entity.name[:1].lower() + entity.name[1:]
    fallback_response = _fallback_response_class(entity)
    reserved_bindings = JAVA_RESERVED_IDENTIFIERS | {
        entity_var, entity_var + "Repository", entity_var + "Service",
        response_class[:1].lower() + response_class[1:],
        fallback_response[:1].lower() + fallback_response[1:],
        "entity", "response", "record", "records", "responses", "pageable",
    }
    if argument_names.intersection(reserved_bindings):
        _refuse_read(entity, ctx, "path input conflicts with a Java keyword or generated read local")
    if ctx.get("pageable"):
        argument_names.update({"page", "size"})
    for parameter in ctx.get("operation_parameters", []):
        if (
            parameter.location != OperationParameterLocation.HEADER
            or parameter.read_input_role not in {"metadata", "gateway-rate-limit"}
        ):
            _refuse_read(entity, ctx, f"declared {parameter.location.value} input '{parameter.name}' is not a supported selector or classified metadata header")
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", parameter.name):
            _refuse_read(entity, ctx, "header name is not a valid HTTP field-name token")
        argument_name = _java_parameter_name(parameter.name)
        if argument_name in reserved_bindings or argument_name == "id":
            _refuse_read(entity, ctx, f"header '{parameter.name}' conflicts with a Java keyword or generated read local")
        if argument_name in argument_names:
            _refuse_read(entity, ctx, "declared inputs collide as generated Java arguments")
        argument_names.add(argument_name)
        if any(
            (_read_mapping_input_name(mapping, ctx) or "").lower() == parameter.name.lower()
            for mapping in ctx.get("request_field_mappings", [])
        ):
            _refuse_read(entity, ctx, f"header '{parameter.name}' classification contradicts its canonical record mapping")


def _read_mapping_input_name(mapping: FieldMapping, ctx: dict) -> str | None:
    # Dots may be part of a literal HTTP header name. Never collapse a source
    # to its last token and thereby turn a different input into the path ID.
    prefix = f"{ctx.get('interface_name')}.{ctx['operation_name']}.request."
    return mapping.source_path[len(prefix):] if mapping.source_path.startswith(prefix) else None


def _verified_read_id_argument_name(entity: CanonicalEntity, ctx: dict) -> str:
    ids = [field for field in entity.fields if field.is_id]
    parameters = list(ctx.get("path_parameters", []))
    if len(ids) != 1 or not entity.read_identity_verified:
        _refuse_read(entity, ctx, "persistence identity is ambiguous or inferred from the read itself; declare an existing identity_overrides persistence_id")
    field = ids[0]
    if len(parameters) != 1 or parameters[0].type != _java_type(field):
        _refuse_read(entity, ctx, "exactly one correctly typed persistence-ID path input is required")
    parameter = parameters[0]
    if parameter.name.lower() not in {field.name.lower(), "id"}:
        _refuse_read(entity, ctx, f"path input '{parameter.name}' is not persistence ID '{field.name}'")
    if any(
        mapping.target_path != f"{entity.name}.{field.name}"
        or (_read_mapping_input_name(mapping, ctx) or "").lower() != parameter.name.lower()
        for mapping in ctx.get("request_field_mappings", [])
    ):
        _refuse_read(entity, ctx, "additional or contradictory record-selection mappings are not implemented")
    path = ctx.get("spec_path")
    if path:
        parts = path.strip("/").split("/")
        marker = "{" + parameter.name + "}"
        index = parts.index(marker) if marker in parts else -1
        resource = parts[index - 1].lower() if index > 0 else ""
        spellings = {entity.name.lower(), to_snake_case(entity.name), to_snake_case(entity.name).replace("_", "-")}
        collections = spellings | {spelling + "s" for spelling in spellings}
        if resource not in collections:
            _refuse_read(entity, ctx, "path input is not bound to the selected entity's own resource collection")
        return _java_parameter_name(parameter.name)
    return "id"


def _validate_read_route(entity: CanonicalEntity, ctx: dict, route_base: str | None) -> None:
    path = ctx["spec_path"]
    names = [parameter.name for parameter in ctx.get("path_parameters", [])]
    static = re.sub(r"\{[^}]+\}", "", path)
    if (
        not path.startswith("/") or path.startswith("//") or path.endswith("/")
        or any(part in {"", ".", ".."} for part in path.strip("/").split("/"))
        or any(character in static for character in ('%', '\\', '?', '#', '*', '{', '}', ';', '"', "'"))
        or any(character.isspace() or ord(character) < 32 for character in path)
        or re.findall(r"\{([^}]+)\}", path) != names
        or len(set(names)) != len(names)
        or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names)
    ):
        _refuse_read(entity, ctx, "read route has unsupported literals or mismatched path variables")
    if route_base is None or not (path == route_base or path.startswith(route_base + "/")):
        _refuse_read(entity, ctx, "read route cannot be emitted faithfully with the selected controller base")


def _validate_computed_read_runtime_support(metadata: MetadataProject) -> None:
    """Preflight every selected GET before generation can modify user output."""

    entities = {entity.name: entity for entity in all_entities(metadata)}
    selected = {
        (mapping.contract_name, mapping.operation_name)
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
    }
    for operation in metadata.operations:
        if (operation.http_method != HttpMethod.GET
                or (operation.interface_name, operation.name) not in selected):
            continue
        entity_name = operation_entity_name(operation)
        entity = entities.get(entity_name)
        if entity is None or not entity.fields:
            _refuse_read(
                entity or CanonicalEntity(name=entity_name or "unresolved"),
                {"operation_name": operation.name, "interface_name": operation.interface_name},
                "selected read has no resolved returned entity with fields",
            )
    for entity in entities.values():
        if entity.fields:
            _validate_computed_read_contexts(
                entity, _operation_contexts_for_entity(metadata, entity),
            )


def _operation_path_variable_controller_signatures(
    ctx: dict,
    *,
    id_java_type: str,
) -> list[str]:
    path_parameters = list(ctx.get("path_parameters", []))
    if not path_parameters:
        return []
    spec_path = ctx.get("spec_path")
    if not spec_path:
        return [f"@PathVariable {id_java_type} id"]
    signatures: list[str] = []
    for parameter in path_parameters:
        signatures.append(
            f"@PathVariable(\"{parameter.name}\") {parameter.type or id_java_type} {_java_parameter_name(parameter.name)}"
        )
    return signatures


def _operation_path_variable_service_signatures(
    ctx: dict,
    *,
    id_java_type: str,
) -> list[str]:
    path_parameters = list(ctx.get("path_parameters", []))
    if not path_parameters:
        return []
    spec_path = ctx.get("spec_path")
    if not spec_path:
        return [f"{id_java_type} id"]
    signatures: list[str] = []
    for parameter in path_parameters:
        signatures.append(f"{parameter.type or id_java_type} {_java_parameter_name(parameter.name)}")
    return signatures


def _operation_path_variable_argument_names(ctx: dict) -> list[str]:
    path_parameters = list(ctx.get("path_parameters", []))
    if not path_parameters:
        return []
    spec_path = ctx.get("spec_path")
    if not spec_path:
        return ["id"]
    return [_java_parameter_name(parameter.name) for parameter in path_parameters]


def _primary_operation_id_argument_name(ctx: dict) -> str:
    argument_names = _operation_path_variable_argument_names(ctx)
    if argument_names:
        return argument_names[-1]
    return "id"


def _non_crud_route_suffix(ctx: dict, *, controller_route_base: str) -> str:
    spec_path = ctx.get("spec_path")
    if spec_path and spec_path.startswith(controller_route_base):
        suffix = spec_path[len(controller_route_base):]
        if suffix in {"", "/"}:
            return ""
        return suffix
    route_segment = _non_crud_route_segment(ctx)
    path_parameters = list(ctx.get("path_parameters", []))
    if not path_parameters:
        path_prefix = ""
    elif spec_path:
        path_prefix = f"/{{{path_parameters[0].name}}}"
    else:
        path_prefix = "/{id}"
    return f"{path_prefix}/{route_segment}"


def _non_crud_route_segment(ctx: dict) -> str:
    operation_name = ctx["java_operation_name"]
    if (
        ctx.get("http_method") == HttpMethod.GET
        and operation_name.startswith("get")
        and len(operation_name) > 3
        and operation_name[3:4].isupper()
    ):
        return operation_name[3:4].lower() + operation_name[4:]
    return operation_name


def _non_crud_http_method(category: str) -> str:
    if category == "state_transition":
        return "POST"
    return "GET"


def _add_operation_parameter_controller_imports(imports: set[str], ctx: dict | None) -> None:
    if not ctx:
        return
    for parameter in ctx.get("operation_parameters", []):
        if parameter.location == OperationParameterLocation.QUERY:
            imports.add("org.springframework.web.bind.annotation.RequestParam")
        elif parameter.location == OperationParameterLocation.HEADER:
            imports.add("org.springframework.web.bind.annotation.RequestHeader")
    _add_operation_parameter_type_imports(imports, ctx)


def _add_operation_parameter_type_imports(imports: set[str], ctx: dict | None) -> None:
    if not ctx:
        return
    for parameter in ctx.get("operation_parameters", []):
        java_type = _java_type_for_parameter(parameter)
        java_import = JAVA_IMPORTS.get(java_type)
        if java_import:
            imports.add(java_import)


def _spring_parameter_signature(parameters: list[OperationParameter]) -> list[str]:
    signatures: list[str] = []
    for parameter in parameters:
        annotation = (
            "RequestParam"
            if parameter.location == OperationParameterLocation.QUERY
            else "RequestHeader"
        )
        signatures.append(
            f"@{annotation}(name = \"{parameter.name}\", required = {str(parameter.required).lower()}) "
            f"{_java_type_for_parameter(parameter)} {_java_parameter_name(parameter.name)}"
        )
    return signatures


def _operation_parameter_argument_names(ctx: dict | None) -> list[str]:
    if not ctx:
        return []
    return [
        _java_parameter_name(parameter.name)
        for parameter in ctx.get("operation_parameters", [])
    ]


def _field_validation_annotations(field: CanonicalField) -> list[str]:
    annotations: list[str] = []
    if field.not_null or field.required:
        annotations.append("@NotNull")
    if (
        (field.min_length is not None or field.max_length is not None)
        and field.type == CanonicalFieldType.STRING
    ):
        size_args: list[str] = []
        if field.min_length is not None:
            size_args.append(f"min={field.min_length}")
        if field.max_length is not None:
            size_args.append(f"max={field.max_length}")
        annotations.append(f"@CodePointLength({', '.join(size_args)})")
    if field.pattern:
        annotations.append(f"@Pattern(regexp={_java_code_string_literal(field.pattern)})")
    if field.format == "iso-4217":
        annotations.append('@Pattern(regexp="[A-Z]{3}")')
    if field.range_min is not None:
        annotations.append(f'@DecimalMin("{_java_decimal_literal(field.range_min)}")')
    if field.range_max is not None:
        annotations.append(f'@DecimalMax("{_java_decimal_literal(field.range_max)}")')
    return annotations


def _java_decimal_literal(value: float) -> str:
    rendered = format(Decimal(str(value)).normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _java_type_for_parameter(parameter: OperationParameter) -> str:
    if parameter.type in {CanonicalFieldType.DATE, CanonicalFieldType.DATETIME, CanonicalFieldType.BINARY}:
        return "String"
    return CANONICAL_TO_JAVA[parameter.type.value]


def _java_parameter_name(name: str) -> str:
    segments = [segment for segment in re.split(r"[^a-zA-Z0-9]+", name) if segment]
    if not segments:
        return "param"
    normalized = segments[0][:1].lower() + segments[0][1:]
    for segment in segments[1:]:
        normalized += segment[:1].upper() + segment[1:]
    if normalized and normalized[0].isdigit():
        normalized = f"param{normalized[:1].upper()}{normalized[1:]}"
    return normalized


def _java_bean_json_property_name(field_name: str) -> str:
    """Return the JSON property name inferred from JavaBean accessors."""
    if not field_name:
        return field_name
    if len(field_name) > 1 and field_name[0].isupper() and field_name[1].isupper():
        return field_name
    return field_name[:1].lower() + field_name[1:]


def _dto_needs_explicit_json_property(field_name: str, contract_name: str) -> bool:
    # Link fields and accessors when wire/storage names or bean naming can diverge.
    # Uppercase/acronym names are explicit across Jackson bean-naming settings.
    bean_name = _java_bean_json_property_name(to_pascal_case(field_name))
    return contract_name != bean_name or field_name != bean_name or field_name[:1].isupper()


def _service_parameter_signature(ctx: dict | None) -> list[str]:
    if not ctx:
        return []
    return [
        f"{_java_type_for_parameter(parameter)} {_java_parameter_name(parameter.name)}"
        for parameter in ctx.get("operation_parameters", [])
    ]


def _append_generation_warning(metadata: MetadataProject, warning: str) -> None:
    if warning not in metadata.warnings:
        metadata.warnings.append(warning)


def _ignore_business_key_rule_for_server_generated_id(
    field: CanonicalField,
    rule: CanonicalRule,
) -> bool:
    if not field.is_id or not field.server_generated_id:
        return False
    return rule.type in {
        RuleType.ALLOWED_VALUES,
        RuleType.DEFAULT,
        RuleType.MAX_LENGTH,
        RuleType.MIN_LENGTH,
        RuleType.PATTERN,
        RuleType.RANGE,
    }


def _field_comparison_decimal_expression(
    left_getter: str,
    right_getter: str,
    operator: str,
) -> str:
    if operator == "<=":
        return f"{left_getter}.compareTo({right_getter}) <= 0"
    if operator == "<":
        return f"{left_getter}.compareTo({right_getter}) < 0"
    if operator == ">=":
        return f"{left_getter}.compareTo({right_getter}) >= 0"
    if operator == ">":
        return f"{left_getter}.compareTo({right_getter}) > 0"
    if operator == "==":
        return f"{left_getter}.compareTo({right_getter}) == 0"
    raise ValueError(f"Unsupported field-comparison operator '{operator}'")


def _find_entity_by_name(
    metadata: MetadataProject,
    entity_name: str,
) -> CanonicalEntity | None:
    return next((candidate for candidate in metadata.entities if candidate.name == entity_name), None)


def _validate_cross_entity_rule_target_entity(
    *,
    metadata: MetadataProject,
    rule: CanonicalRule,
    source_entity: CanonicalEntity,
    source_field: CanonicalField,
) -> CanonicalEntity:
    known_entity_names = sorted(entity.name for entity in metadata.entities)
    target_entity_name = rule.target_entity or ""
    target_entity = _find_entity_by_name(metadata, target_entity_name)
    if target_entity is None:
        raise ValueError(
            f"{rule.type.value} rule on '{source_entity.name}.{rule.field_name}' "
            f"references unknown entity '{target_entity_name}'. "
            f"Known entities: {known_entity_names}. "
            f"Check the 'target-entity' value in your rules YAML."
        )

    target_id_field = entity_id_field(target_entity)
    if source_field.type != target_id_field.type:
        raise ValueError(
            f"{rule.type.value} rule on '{source_entity.name}.{rule.field_name}' "
            f"(type: {source_field.type.value}) is not compatible with the ID "
            f"field '{target_id_field.name}' of '{target_entity.name}' "
            f"(type: {target_id_field.type.value}). "
            f"Cross-entity rules require the FK field type to match the target ID type. "
            f"Align the field types in your entity definitions or rules YAML."
        )

    return target_entity


def _validate_expected_value_for_field(
    *,
    rule: CanonicalRule,
    source_entity: CanonicalEntity,
    target_field: CanonicalField,
) -> None:
    expected_value = rule.expected_value
    if expected_value is None:
        raise ValueError(
            f"{rule.type.value} rule on '{source_entity.name}.{rule.field_name}' "
            "requires an 'expected-value' before generation."
        )

    try:
        if target_field.type == CanonicalFieldType.INTEGER:
            int(str(expected_value))
        elif target_field.type == CanonicalFieldType.DECIMAL:
            Decimal(str(expected_value))
        elif target_field.type == CanonicalFieldType.BOOLEAN:
            if str(expected_value).lower() not in {"true", "false"}:
                raise ValueError("boolean")
        elif target_field.type == CanonicalFieldType.DATE:
            date.fromisoformat(str(expected_value))
        elif target_field.type == CanonicalFieldType.DATETIME:
            datetime.fromisoformat(str(expected_value).replace("Z", "+00:00"))
        elif target_field.type == CanonicalFieldType.BINARY:
            raise ValueError("binary")
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ValueError(
            f"{rule.type.value} rule on '{source_entity.name}.{rule.field_name}' "
            f"has expected-value '{expected_value}' that is not compatible with "
            f"target field '{rule.target_entity}.{target_field.name}' "
            f"(type: {target_field.type.value})."
        ) from exc


def _validate_cross_entity_field_rules(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    entity_fields: dict[str, CanonicalField],
) -> None:
    cross_entity_exists_pairs = {
        (rule.entity_name, rule.field_name, rule.target_entity)
        for rule in metadata.rules
        if rule.type == RuleType.CROSS_ENTITY_EXISTS and rule.target_entity
    }

    for rule in metadata.rules:
        if rule.entity_name != entity.name or rule.type not in {
            RuleType.CROSS_ENTITY_FIELD_CHECK,
            RuleType.CROSS_ENTITY_FIELD_COMPARE,
            RuleType.CROSS_ENTITY_FIELD_IN,
        }:
            continue

        source_fk_field = entity_fields.get(rule.field_name)
        if source_fk_field is None:
            raise ValueError(
                f"{rule.type.value} rule on '{entity.name}.{rule.field_name}' "
                "references a field that was not found on the source entity."
            )
        if (entity.name, rule.field_name, rule.target_entity) not in cross_entity_exists_pairs:
            raise ValueError(
                f"{rule.type.value} rule on '{entity.name}.{rule.field_name}' "
                f"requires a matching 'cross-entity-exists' rule for target entity "
                f"'{rule.target_entity}'. Add the prerequisite reference rule first."
            )

        target_entity = _validate_cross_entity_rule_target_entity(
            metadata=metadata,
            rule=rule,
            source_entity=entity,
            source_field=source_fk_field,
        )
        target_field_name = rule.target_field or ""
        target_field = next(
            (field for field in target_entity.fields if field.name == target_field_name),
            None,
        )
        if target_field is None:
            raise ValueError(
                f"{rule.type.value} rule on '{entity.name}.{rule.field_name}' "
                f"references unknown target field '{target_field_name}' on "
                f"entity '{target_entity.name}'."
            )

        if rule.type in {
            RuleType.CROSS_ENTITY_FIELD_CHECK,
            RuleType.CROSS_ENTITY_FIELD_COMPARE,
        } and rule.operator not in _CROSS_ENTITY_FIELD_OPERATORS:
            raise ValueError(
                f"{rule.type.value} rule on '{entity.name}.{rule.field_name}' "
                f"uses unsupported operator '{rule.operator}'. "
                f"Supported named operators: {sorted(_CROSS_ENTITY_FIELD_OPERATORS)}."
            )

        if rule.type == RuleType.CROSS_ENTITY_FIELD_CHECK:
            _validate_expected_value_for_field(
                rule=rule,
                source_entity=entity,
                target_field=target_field,
            )
            continue

        if rule.type == RuleType.CROSS_ENTITY_FIELD_IN:
            if not rule.values:
                raise ValueError(
                    f"{rule.type.value} rule on '{entity.name}.{rule.field_name}' "
                    "requires a non-empty 'allowed-values' list."
                )
            continue

        source_compare_field_name = rule.source_field or ""
        source_compare_field = entity_fields.get(source_compare_field_name)
        if source_compare_field is None:
            raise ValueError(
                f"{rule.type.value} rule on '{entity.name}.{rule.field_name}' "
                f"references unknown source field '{source_compare_field_name}'."
            )
        if source_compare_field.type not in _NUMERIC_FIELD_TYPES:
            raise ValueError(
                f"{rule.type.value} rule on '{entity.name}.{rule.field_name}' "
                f"requires numeric source-field '{source_compare_field_name}', "
                f"but found type '{source_compare_field.type.value}'."
            )
        if target_field.type not in _NUMERIC_FIELD_TYPES:
            raise ValueError(
                f"{rule.type.value} rule on '{entity.name}.{rule.field_name}' "
                f"requires numeric target-field '{target_field.name}', "
                f"but found type '{target_field.type.value}'."
            )


def _has_cross_entity_state_rules(metadata: MetadataProject) -> bool:
    return any(rule.type in _CROSS_ENTITY_STATE_RULE_TYPES for rule in metadata.rules)


def _cross_entity_repo_var(target_entity: str) -> str:
    return f"{target_entity[:1].lower() + target_entity[1:]}Repository"


def _java_code_string_literal(value: str) -> str:
    escaped_parts: list[str] = []
    for char in value:
        if char == "\\":
            escaped_parts.append("\\\\")
        elif char == '"':
            escaped_parts.append('\\"')
        elif char == "\n":
            escaped_parts.append("\\n")
        elif char == "\r":
            escaped_parts.append("\\r")
        elif char == "\t":
            escaped_parts.append("\\t")
        elif ord(char) < 0x20:
            escaped_parts.append(f"\\u{ord(char):04x}")
        else:
            escaped_parts.append(char)
    escaped = "".join(escaped_parts)
    return f'"{escaped}"'


def _cross_entity_lookup_var_name(
    *,
    field_name: str,
    target_entity: str,
) -> str:
    target_var = target_entity[:1].lower() + target_entity[1:]
    normalized = field_name
    for suffix in ("Id", "_id", "ID"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    normalized = normalized or target_var
    if "_" in normalized:
        parts = [part for part in normalized.split("_") if part]
        normalized = parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
    candidate = normalized[:1].lower() + normalized[1:]
    if candidate == target_var or candidate.lower().endswith(target_var.lower()):
        return candidate
    return f"{candidate}{target_entity}"


def _cross_entity_expected_literal(
    *,
    field: CanonicalField,
    expected_value: str,
) -> str:
    if field.type == CanonicalFieldType.STRING:
        return _java_code_string_literal(expected_value)
    if field.type == CanonicalFieldType.BOOLEAN:
        return _validated_java_boolean_literal(
            expected_value,
            context=f"cross-entity expected value for '{field.name}'",
        )
    if field.type == CanonicalFieldType.INTEGER:
        return (
            _validated_java_integer_literal(
                expected_value,
                context=f"cross-entity expected value for '{field.name}'",
            )
            + "L"
        )
    if field.type == CanonicalFieldType.DECIMAL:
        return (
            "new BigDecimal("
            + _java_code_string_literal(
                _validated_java_decimal_literal(
                    expected_value,
                    context=f"cross-entity expected value for '{field.name}'",
                )
            )
            + ")"
        )
    if field.type == CanonicalFieldType.DATE:
        _validate_java_date_literal(
            expected_value,
            context=f"cross-entity expected value for '{field.name}'",
        )
        return f"LocalDate.parse({_java_code_string_literal(expected_value)})"
    if field.type == CanonicalFieldType.DATETIME:
        _validate_java_datetime_literal(
            expected_value,
            context=f"cross-entity expected value for '{field.name}'",
        )
        if re.search(r"(Z|[+-]\d{2}:\d{2})$", expected_value):
            return (
                f"java.time.OffsetDateTime.parse({_java_code_string_literal(expected_value)})"
                ".toLocalDateTime()"
            )
        return f"LocalDateTime.parse({_java_code_string_literal(expected_value)})"
    raise ValueError(
        f"Unsupported target-field type '{field.type.value}' for expected-value emission."
    )


def _cross_entity_comparison_success_expression(
    *,
    left_expression: str,
    right_expression: str,
    operator: str,
) -> str:
    if operator == "eq":
        return f"{left_expression}.compareTo({right_expression}) == 0"
    if operator == "neq":
        return f"{left_expression}.compareTo({right_expression}) != 0"
    if operator == "lt":
        return f"{left_expression}.compareTo({right_expression}) < 0"
    if operator == "lte":
        return f"{left_expression}.compareTo({right_expression}) <= 0"
    if operator == "gt":
        return f"{left_expression}.compareTo({right_expression}) > 0"
    if operator == "gte":
        return f"{left_expression}.compareTo({right_expression}) >= 0"
    raise ValueError(f"Unsupported cross-entity operator '{operator}'")


def _cross_entity_rule_message(
    *,
    rule: CanonicalRule,
    source_entity_name: str,
) -> str:
    return rule.error_message or (
        f"{rule.target_entity} {rule.target_field} does not satisfy rule for "
        f"{source_entity_name}.{rule.field_name}"
    )


def _cross_entity_rule_target_field(
    *,
    metadata: MetadataProject,
    rule: CanonicalRule,
) -> CanonicalField:
    target_entity = _find_entity_by_name(metadata, rule.target_entity or "")
    if target_entity is None:
        raise ValueError(
            f"Unable to resolve target entity '{rule.target_entity}' for {rule.type.value} emission."
        )
    target_field = next(
        (field for field in target_entity.fields if field.name == (rule.target_field or "")),
        None,
    )
    if target_field is None:
        raise ValueError(
            f"Unable to resolve target field '{rule.target_field}' for {rule.type.value} emission."
        )
    return target_field


def _cross_entity_field_nullable(field: CanonicalField) -> bool:
    return not (field.required or field.not_null)


def _emit_cross_entity_runtime_checks(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    entity_fields: dict[str, CanonicalField],
    exists_rules: list[CanonicalRule],
    state_rules: list[CanonicalRule],
    entity_var_expression: str,
) -> list[str]:
    lines: list[str] = []
    state_pairs = {(rule.field_name, rule.target_entity) for rule in state_rules}
    for rule in exists_rules:
        if (rule.field_name, rule.target_entity) in state_pairs:
            continue
        getter = f"{entity_var_expression}.get{to_pascal_case(rule.field_name)}()"
        target_repo_var = _cross_entity_repo_var(rule.target_entity or "")
        lines.extend(
            [
                f"        if ({getter} != null && !{target_repo_var}.existsById({getter})) {{",
                f"            throw new ResourceNotFoundException(\"{rule.target_entity} not found with id: \" + {getter});",
                "        }",
            ]
        )

    rules_by_pair: OrderedDict[tuple[str, str], list[CanonicalRule]] = OrderedDict()
    for rule in state_rules:
        pair = (rule.field_name, rule.target_entity or "")
        rules_by_pair.setdefault(pair, []).append(rule)

    for (field_name, target_entity_name), pair_rules in rules_by_pair.items():
        source_field = entity_fields[field_name]
        fk_getter = f"{entity_var_expression}.get{to_pascal_case(field_name)}()"
        lookup_var = _cross_entity_lookup_var_name(
            field_name=field_name,
            target_entity=target_entity_name,
        )
        target_repo_var = _cross_entity_repo_var(target_entity_name)
        lookup_lines = [
            f"        {target_entity_name} {lookup_var} = {target_repo_var}.findById({fk_getter})",
            "            .orElseThrow(() -> new ResourceNotFoundException(",
            f'                "{target_entity_name} not found with id: " + {fk_getter}));',
        ]
        predicate_lines: list[str] = []
        for rule in pair_rules:
            target_field = _cross_entity_rule_target_field(metadata=metadata, rule=rule)
            target_getter = f"{lookup_var}.get{to_pascal_case(target_field.name)}()"
            message_literal = _java_code_string_literal(
                _cross_entity_rule_message(rule=rule, source_entity_name=entity.name)
            )
            if rule.type == RuleType.CROSS_ENTITY_FIELD_CHECK:
                expected_literal = _cross_entity_expected_literal(
                    field=target_field,
                    expected_value=rule.expected_value or "",
                )
                success_expression = _cross_entity_comparison_success_expression(
                    left_expression=target_getter,
                    right_expression=expected_literal,
                    operator=rule.operator or "",
                )
                predicate_lines.extend(
                    [
                        f"        if ({target_getter} == null || !({success_expression})) {{",
                        f"            throw new BusinessRuleException({message_literal});",
                        "        }",
                    ]
                )
            elif rule.type == RuleType.CROSS_ENTITY_FIELD_COMPARE:
                source_getter = f"{entity_var_expression}.get{to_pascal_case(rule.source_field or '')}()"
                success_expression = _cross_entity_comparison_success_expression(
                    left_expression=source_getter,
                    right_expression=target_getter,
                    operator=rule.operator or "",
                )
                predicate_lines.extend(
                    [
                        f"        if ({source_getter} == null || {target_getter} == null || !({success_expression})) {{",
                        f"            throw new BusinessRuleException({message_literal});",
                        "        }",
                    ]
                )
            elif rule.type == RuleType.CROSS_ENTITY_FIELD_IN:
                allowed_values = ", ".join(_java_code_string_literal(value) for value in rule.values)
                predicate_lines.extend(
                    [
                        f"        if ({target_getter} == null || !List.of({allowed_values}).contains({target_getter})) {{",
                        f"            throw new BusinessRuleException({message_literal});",
                        "        }",
                    ]
                )

        if _cross_entity_field_nullable(source_field):
            lines.append(f"        if ({fk_getter} != null) {{")
            lines.extend(f"    {line}" for line in lookup_lines)
            lines.extend(f"    {line}" for line in predicate_lines)
            lines.append("        }")
        else:
            lines.extend(lookup_lines)
            lines.extend(predicate_lines)

    return lines


# ---------------------------------------------------------------------------
# Service — create, findById (throws ResourceNotFoundException), findAll,
#           update, delete; plus legacy per-operation create stubs
# ---------------------------------------------------------------------------

def _append_response_mapping_setters(
    body: list[str],
    *,
    response_mappings: list[FieldMapping],
    entity_fields: dict[str, CanonicalField],
    response_var: str,
    source_var: str,
    indent: str,
) -> None:
    for mapping in response_mappings:
        canonical_name = canonical_field_name(mapping)
        if canonical_name not in entity_fields:
            continue
        method_suffix = to_pascal_case(canonical_name)
        body.append(
            f"{indent}{response_var}.set{method_suffix}({source_var}.get{method_suffix}());"
        )


def _request_mappings_set_persistence_id(
    *,
    entity: CanonicalEntity,
    id_field: CanonicalField,
    request_mappings: list[FieldMapping],
) -> bool:
    if id_field.server_generated_id:
        return False
    id_target_path = f"{entity.name}.{id_field.name}"
    return any(mapping.target_path == id_target_path for mapping in request_mappings)


def _emit_duplicate_create_guard(
    *,
    entity: CanonicalEntity,
    id_field: CanonicalField,
    request_mappings: list[FieldMapping],
    entity_var: str,
    repository_var: str,
) -> list[str]:
    if not _request_mappings_set_persistence_id(
        entity=entity,
        id_field=id_field,
        request_mappings=request_mappings,
    ):
        return []
    id_getter = f"{entity_var}.get{to_pascal_case(id_field.name)}()"
    return [
        f"        if ({id_getter} != null && {repository_var}.existsById({id_getter})) {{",
        f"            throw new DuplicateResourceException(\"{entity.name} already exists with id: \" + {id_getter});",
        "        }",
    ]


def _render_service(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    root_package: str,
    op_contexts: list[dict],
    id_java_type: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    _validate_computed_read_contexts(entity, op_contexts)
    from .write_contract import validate_write_context
    for context in op_contexts:
        validate_write_context(entity, context, _common_spec_route_base(op_contexts))
    entity_fields = {field.name: field for field in entity.fields}
    _validate_cross_entity_field_rules(
        metadata=metadata,
        entity=entity,
        entity_fields=entity_fields,
    )
    repository_var = f"{entity.name[:1].lower() + entity.name[1:]}Repository"
    entity_var = entity.name[:1].lower() + entity.name[1:]
    id_field = entity_id_field(entity)
    explicit_read_surface = _uses_explicit_read_surface(op_contexts)
    has_pre_persist_initializer = bool(_server_set_field_initializers(metadata, entity))

    # cross-entity-exists rules for this entity.
    # Fix (Codex P1): separate concerns —
    #   cross_entity_checks = ALL qualifying rules, one existsById check emitted per rule
    #   cross_entity_repos  = deduplicated by target_entity, one generated field per target
    # Fix (Codex P2): validate each target_entity against known metadata entities before generating.
    _known_entity_names: set[str] = {e.name for e in metadata.entities}
    cross_entity_checks: list[CanonicalRule] = []   # all exists rules — drives existsById checks
    cross_entity_state_rules: list[CanonicalRule] = []  # all runtime state rules — drives findById + predicates
    cross_entity_repos: list[CanonicalRule] = []    # deduplicated by target — drives repository injection
    _seen_targets: set[str] = set()
    for _rule in metadata.rules:
        if _rule.entity_name != entity.name or not _rule.target_entity:
            continue
        if entity_fields.get(_rule.field_name) is None:
            continue
        if _rule.target_entity not in _known_entity_names:
            raise ValueError(
                f"{_rule.type.value} rule on '{entity.name}.{_rule.field_name}' "
                f"references unknown entity '{_rule.target_entity}'. "
                f"Known entities: {sorted(_known_entity_names)}. "
                f"Check the 'target-entity' value in your rules YAML."
            )
        _rule_field = entity_fields[_rule.field_name]
        _target_entity_obj = next(e for e in metadata.entities if e.name == _rule.target_entity)
        _target_id_field = entity_id_field(_target_entity_obj)
        if _rule_field.type != _target_id_field.type:
            raise ValueError(
                f"{_rule.type.value} rule on '{entity.name}.{_rule.field_name}' "
                f"(type: {_rule_field.type.value}) is not compatible with the ID "
                f"field '{_target_id_field.name}' of '{_rule.target_entity}' "
                f"(type: {_target_id_field.type.value}). "
                f"existsById() and findById() require matching types. "
                f"Align the field types in your entity definitions or rules YAML."
            )
        if _rule.type == RuleType.CROSS_ENTITY_EXISTS:
            cross_entity_checks.append(_rule)
        elif _rule.type in _CROSS_ENTITY_STATE_RULE_TYPES:
            cross_entity_state_rules.append(_rule)
        if _rule.target_entity not in _seen_targets:
            cross_entity_repos.append(_rule)
            _seen_targets.add(_rule.target_entity)

    imports: set[str] = {
        f"{root_package}.domain.{entity.name}",
        f"{root_package}.exception.DuplicateResourceException",
        f"{root_package}.exception.ResourceNotFoundException",
        f"{root_package}.repository.{entity.name}Repository",
        "java.util.List",
    }
    id_java_import = JAVA_IMPORTS.get(id_java_type)
    if id_java_import:
        imports.add(id_java_import)
    if cross_entity_state_rules:
        imports.add(f"{root_package}.exception.BusinessRuleException")
    for _rule in cross_entity_state_rules:
        imports.add(f"{root_package}.domain.{_rule.target_entity}")
    for ctx in op_contexts:
        imports.add(f"{root_package}.adapter.inbound.{ctx['request_class_name']}")
        imports.add(f"{root_package}.adapter.inbound.{ctx['response_class_name']}")
    if _should_emit_generic_fallback_dtos(op_contexts):
        if _should_emit_generic_create_fallback(op_contexts):
            imports.add(f"{root_package}.adapter.inbound.{_fallback_create_request_class(entity)}")
        imports.add(f"{root_package}.adapter.inbound.{_fallback_update_request_class(entity)}")
        imports.add(f"{root_package}.adapter.inbound.{_fallback_response_class(entity)}")
    for _cr in cross_entity_repos:
        imports.add(f"{root_package}.repository.{_cr.target_entity}Repository")
    for _rule in cross_entity_state_rules:
        _target_field = _cross_entity_rule_target_field(metadata=metadata, rule=_rule)
        _java_import = JAVA_IMPORTS.get(_java_type(_target_field))
        if _java_import:
            imports.add(_java_import)
    get_ctx = None if explicit_read_surface else _find_get_by_id_context(op_contexts)
    list_ctx = None if explicit_read_surface else _find_list_context(op_contexts)
    _add_operation_parameter_type_imports(imports, get_ctx)
    _add_operation_parameter_type_imports(imports, list_ctx)
    for context in op_contexts:
        _add_operation_parameter_type_imports(imports, context)
    if any(_is_pageable_list_context(ctx) for ctx in [list_ctx, *op_contexts]):
        imports.update(
            {
                "org.springframework.data.domain.Page",
                "org.springframework.data.domain.Pageable",
            }
        )
    if cross_entity_repos:
        imports.add("org.springframework.beans.factory.annotation.Autowired")

    body: list[str] = [f"public abstract class {entity.name}ServiceBase {{", ""]

    # Allowed-values constants — scoped to this entity only to avoid duplicate
    # field declarations when multiple entities share a field name (e.g. "status")
    allowed_value_rules = [
        rule for rule in metadata.rules
        if (
            rule.type == RuleType.ALLOWED_VALUES
            and rule.entity_name == entity.name
            and (
                entity_fields.get(rule.field_name) is None
                or not _ignore_business_key_rule_for_server_generated_id(
                    entity_fields[rule.field_name],
                    rule,
                )
            )
        )
    ]
    for rule in allowed_value_rules:
        imports.add("java.util.Set")
        constant_name = f"ALLOWED_{to_snake_case(rule.field_name).upper()}_VALUES"
        allowed_values = ", ".join(_java_code_string_literal(value) for value in rule.values)
        body.append(
            f"    private static final Set<String> {constant_name} = Set.of({allowed_values});"
        )
    if allowed_value_rules:
        body.append("")

    # Primary repository field + one field per unique target entity (cross_entity_repos)
    body.append(f"    protected final {entity.name}Repository {repository_var};")
    for _cr in cross_entity_repos:
        _target_repo_var = _cross_entity_repo_var(_cr.target_entity or "")
        body.append("    @Autowired")
        body.append(f"    protected {_cr.target_entity}Repository {_target_repo_var};")
    body.append("")

    # Constructor — keep this stable across manifest evolution. Variable secondary
    # repositories are injected into the generated base so preserved developer
    # subclasses do not go stale when regenerated rules add dependencies.
    _ctor_params = [f"{entity.name}Repository {repository_var}"]
    body.append(f"    protected {entity.name}ServiceBase({', '.join(_ctor_params)}) {{")
    body.append(f"        this.{repository_var} = {repository_var};")
    body.append("    }")

    # --- findById — throws ResourceNotFoundException on miss ---
    if not explicit_read_surface:
        get_service_params = [f"{id_java_type} id", *_service_parameter_signature(get_ctx)]
        if _has_response_mappings(get_ctx):
            resp_class = get_ctx["response_class_name"]
            response_var = resp_class[:1].lower() + resp_class[1:]
            body.extend([
                "",
                f"    public {resp_class} findById({', '.join(get_service_params)}) {{",
                f"        {entity.name} {entity_var} = {repository_var}.findById(id)",
                "            .orElseThrow(() -> new ResourceNotFoundException(",
                f"                \"{entity.name} not found with id: \" + id));",
                f"        {resp_class} {response_var} = new {resp_class}();",
            ])
            _append_response_mapping_setters(
                body,
                response_mappings=get_ctx["response_field_mappings"],
                entity_fields=entity_fields,
                response_var=response_var,
                source_var=entity_var,
                indent="        ",
            )
            body.extend([
                f"        return {response_var};",
                "    }",
            ])
        else:
            resp_class = _fallback_response_class(entity)
            response_var = resp_class[:1].lower() + resp_class[1:]
            body.extend([
                "",
                f"    public {resp_class} findById({', '.join(get_service_params)}) {{",
                f"        {entity.name} {entity_var} = {repository_var}.findById(id)",
                "            .orElseThrow(() -> new ResourceNotFoundException(",
                f"                \"{entity.name} not found with id: \" + id));",
                f"        {resp_class} {response_var} = new {resp_class}();",
            ])
            _append_response_mapping_setters(
                body,
                response_mappings=_fallback_response_field_mappings(entity),
                entity_fields=entity_fields,
                response_var=response_var,
                source_var=entity_var,
                indent="        ",
            )
            body.extend([
                f"        return {response_var};",
                "    }",
            ])

    # --- findAll ---
    if not explicit_read_surface:
        list_service_params = _service_parameter_signature(list_ctx)
        if _is_pageable_list_context(list_ctx) and _has_response_mappings(list_ctx):
            resp_class = list_ctx["response_class_name"]
            response_var = resp_class[:1].lower() + resp_class[1:]
            body.extend([
                "",
                f"    public Page<{resp_class}> findAll({', '.join([*list_service_params, 'Pageable pageable'])}) {{",
                f"        return {repository_var}.findAll(pageable).map(record -> {{",
                f"            {resp_class} {response_var} = new {resp_class}();",
            ])
            _append_response_mapping_setters(
                body,
                response_mappings=list_ctx["response_field_mappings"],
                entity_fields=entity_fields,
                response_var=response_var,
                source_var="record",
                indent="            ",
            )
            body.extend([
                f"            return {response_var};",
                "        });",
                "    }",
            ])
        elif _is_pageable_list_context(list_ctx):
            resp_class = _fallback_response_class(entity)
            response_var = resp_class[:1].lower() + resp_class[1:]
            body.extend([
                "",
                f"    public Page<{resp_class}> findAll({', '.join([*list_service_params, 'Pageable pageable'])}) {{",
                f"        return {repository_var}.findAll(pageable).map(record -> {{",
                f"            {resp_class} {response_var} = new {resp_class}();",
            ])
            _append_response_mapping_setters(
                body,
                response_mappings=_fallback_response_field_mappings(entity),
                entity_fields=entity_fields,
                response_var=response_var,
                source_var="record",
                indent="            ",
            )
            body.extend([
                f"            return {response_var};",
                "        });",
                "    }",
            ])
        elif _has_response_mappings(list_ctx):
            resp_class = list_ctx["response_class_name"]
            response_var = resp_class[:1].lower() + resp_class[1:]
            body.extend([
                "",
                f"    public List<{resp_class}> findAll({', '.join(list_service_params)}) {{"
                if list_service_params
                else f"    public List<{resp_class}> findAll() {{",
                f"        List<{entity.name}> records = {repository_var}.findAll();",
                f"        List<{resp_class}> responses = new java.util.ArrayList<>();",
                f"        for ({entity.name} record : records) {{",
                f"            {resp_class} {response_var} = new {resp_class}();",
            ])
            _append_response_mapping_setters(
                body,
                response_mappings=list_ctx["response_field_mappings"],
                entity_fields=entity_fields,
                response_var=response_var,
                source_var="record",
                indent="            ",
            )
            body.extend([
                f"            responses.add({response_var});",
                "        }",
                "        return responses;",
                "    }",
            ])
        else:
            resp_class = _fallback_response_class(entity)
            response_var = resp_class[:1].lower() + resp_class[1:]
            body.extend([
                "",
                f"    public List<{resp_class}> findAll({', '.join(list_service_params)}) {{"
                if list_service_params
                else f"    public List<{resp_class}> findAll() {{",
                f"        List<{entity.name}> records = {repository_var}.findAll();",
                f"        List<{resp_class}> responses = new java.util.ArrayList<>();",
                f"        for ({entity.name} record : records) {{",
                f"            {resp_class} {response_var} = new {resp_class}();",
            ])
            _append_response_mapping_setters(
                body,
                response_mappings=_fallback_response_field_mappings(entity),
                entity_fields=entity_fields,
                response_var=response_var,
                source_var="record",
                indent="            ",
            )
            body.extend([
                f"            responses.add({response_var});",
                "        }",
                "        return responses;",
                "    }",
            ])

    # --- update (path id wins — discard any id in request body) ---
    id_setter = to_pascal_case(id_field.name)
    update_ctx = _find_update_context(op_contexts)
    if update_ctx:
        update_req_class = update_ctx["request_class_name"]
        update_mappings = update_ctx["request_field_mappings"]
        update_resp_class = _operation_response_type(update_ctx, entity.name)
        update_response_var = update_resp_class[:1].lower() + update_resp_class[1:]
        update_method_name = update_ctx["java_operation_name"]
        body.extend([
            "",
            f"    public {update_resp_class} {update_method_name}({', '.join([f'{id_java_type} id', *_service_parameter_signature(update_ctx), f'{update_req_class} request'])}) {{",
            f"        {entity.name} {entity_var} = {repository_var}.findById(id)",
            "            .orElseThrow(() -> new ResourceNotFoundException(",
            f"                \"{entity.name} not found with id: \" + id));",
        ])
        for mapping in update_mappings:
            canonical_name = canonical_field_name(mapping)
            if canonical_name == id_field.name:
                continue
            method_suffix = to_pascal_case(canonical_name)
            body.append(
                f"        {entity_var}.set{method_suffix}(request.get{method_suffix}());"
            )
        body.append(f"        {entity_var}.set{id_setter}(id);  // path id always takes precedence")
        body.extend(
            _emit_cross_entity_runtime_checks(
                metadata=metadata,
                entity=entity,
                entity_fields=entity_fields,
                exists_rules=cross_entity_checks,
                state_rules=cross_entity_state_rules,
                entity_var_expression=entity_var,
            )
        )
        body.extend([
            f"        beforeUpdate({entity_var});",
            f"        applyBusinessRules({entity_var});",
        ])
        if _has_response_mappings(update_ctx):
            body.extend([
                f"        {entity.name} saved = {repository_var}.save({entity_var});",
                "        afterUpdate(saved);",
                f"        {update_resp_class} {update_response_var} = new {update_resp_class}();",
            ])
            _append_response_mapping_setters(
                body,
                response_mappings=update_ctx["response_field_mappings"],
                entity_fields=entity_fields,
                response_var=update_response_var,
                source_var="saved",
                indent="        ",
            )
            body.extend([
                f"        return {update_response_var};",
                "    }",
            ])
        else:
            body.extend([
                f"        {entity.name} saved = {repository_var}.save({entity_var});",
                "        afterUpdate(saved);",
                "        return saved;",
                "    }",
            ])
    elif not explicit_read_surface:
        update_req_class = _fallback_update_request_class(entity)
        update_resp_class = _fallback_response_class(entity)
        update_response_var = update_resp_class[:1].lower() + update_resp_class[1:]
        body.extend([
            "",
            f"    public {update_resp_class} update({id_java_type} id, {update_req_class} request) {{",
            f"        {entity.name} {entity_var} = {repository_var}.findById(id)",
            "            .orElseThrow(() -> new ResourceNotFoundException(",
            f"                \"{entity.name} not found with id: \" + id));",
        ])
        for mapping in _fallback_request_field_mappings(metadata, entity):
            canonical_name = canonical_field_name(mapping)
            if canonical_name == id_field.name:
                continue
            method_suffix = to_pascal_case(canonical_name)
            body.append(
                f"        {entity_var}.set{method_suffix}(request.get{method_suffix}());"
            )
        body.append(f"        {entity_var}.set{id_setter}(id);  // path id always takes precedence")
        body.extend(
            _emit_cross_entity_runtime_checks(
                metadata=metadata,
                entity=entity,
                entity_fields=entity_fields,
                exists_rules=cross_entity_checks,
                state_rules=cross_entity_state_rules,
                entity_var_expression=entity_var,
            )
        )
        body.extend([
            f"        beforeUpdate({entity_var});",
            f"        applyBusinessRules({entity_var});",
            f"        {entity.name} saved = {repository_var}.save({entity_var});",
            "        afterUpdate(saved);",
            f"        {update_resp_class} {update_response_var} = new {update_resp_class}();",
        ])
        _append_response_mapping_setters(
            body,
            response_mappings=_fallback_response_field_mappings(entity),
            entity_fields=entity_fields,
            response_var=update_response_var,
            source_var="saved",
            indent="        ",
        )
        body.extend([
            f"        return {update_response_var};",
            "    }",
        ])

    # --- delete ---
    if not explicit_read_surface:
        delete_ctx = next((ctx for ctx in op_contexts if _operation_category(ctx) == "delete"), None)
        body.extend([
            "",
            f"    public void delete({', '.join([f'{id_java_type} id', *_service_parameter_signature(delete_ctx)])}) {{",
            f"        if (!{repository_var}.existsById(id)) {{",
            "            throw new ResourceNotFoundException(",
            f"                \"{entity.name} not found with id: \" + id);",
            "        }",
            "        beforeDelete(id);",
            f"        {repository_var}.deleteById(id);",
            "    }",
        ])

    # --- create (from operation context or generic) ---
    create_ctx = _find_create_context(op_contexts)
    if create_ctx:
        req_class = create_ctx["request_class_name"]
        resp_class = create_ctx["response_class_name"]
        request_mappings = create_ctx["request_field_mappings"]
        response_mappings = create_ctx["response_field_mappings"]
        response_var = resp_class[:1].lower() + resp_class[1:]
        method_name = create_ctx["java_operation_name"]

        body.extend(
            [
                "",
                f"    public {resp_class} {method_name}({', '.join([*_service_parameter_signature(create_ctx), f'{req_class} request'])}) {{",
                f"        {entity.name} {entity_var} = new {entity.name}();",
            ]
        )
        for mapping in request_mappings:
            canonical_name = canonical_field_name(mapping)
            mapped_field = entity_fields.get(canonical_name)
            if mapped_field is not None and mapped_field.is_id and mapped_field.server_generated_id:
                continue
            method_suffix = to_pascal_case(canonical_name)
            body.append(
                f"        {entity_var}.set{method_suffix}(request.get{method_suffix}());"
            )
        body.extend(
            _emit_duplicate_create_guard(
                entity=entity,
                id_field=id_field,
                request_mappings=request_mappings,
                entity_var=entity_var,
                repository_var=repository_var,
            )
        )
        body.extend(
            _emit_cross_entity_runtime_checks(
                metadata=metadata,
                entity=entity,
                entity_fields=entity_fields,
                exists_rules=cross_entity_checks,
                state_rules=cross_entity_state_rules,
                entity_var_expression=entity_var,
            )
        )
        body.extend(
            [
                f"        beforeCreate({entity_var});",
                f"        applyBusinessRules({entity_var});",
            ]
        )
        if has_pre_persist_initializer:
            body.append(
                "        // Server-set fields (status, etc.) are initialized via @PrePersist on the entity."
            )
        body.extend(
            [
                f"        {entity.name} saved = {repository_var}.save({entity_var});",
                "        afterCreate(saved);",
                f"        {resp_class} {response_var} = new {resp_class}();",
            ]
        )
        for mapping in response_mappings:
            canonical_name = canonical_field_name(mapping)
            if canonical_name not in entity_fields:
                continue
            method_suffix = to_pascal_case(canonical_name)
            body.append(
                f"        {response_var}.set{method_suffix}(saved.get{method_suffix}());"
            )
        body.extend(
            [
                f"        return {response_var};",
                "    }",
            ]
        )
    elif _should_emit_generic_create_fallback(op_contexts):
        # Generic create stub — no DTO mappings available
        create_req_class = _fallback_create_request_class(entity)
        create_resp_class = _fallback_response_class(entity)
        create_response_var = create_resp_class[:1].lower() + create_resp_class[1:]
        body.append("")
        body.append(f"    public {create_resp_class} create({create_req_class} request) {{")
        body.append(f"        {entity.name} {entity_var} = new {entity.name}();")
        fallback_request_mappings = _fallback_request_field_mappings(metadata, entity)
        for mapping in fallback_request_mappings:
            canonical_name = canonical_field_name(mapping)
            method_suffix = to_pascal_case(canonical_name)
            body.append(
                f"        {entity_var}.set{method_suffix}(request.get{method_suffix}());"
            )
        body.extend(
            _emit_duplicate_create_guard(
                entity=entity,
                id_field=id_field,
                request_mappings=fallback_request_mappings,
                entity_var=entity_var,
                repository_var=repository_var,
            )
        )
        body.extend([
            f"        beforeCreate({entity_var});",
            f"        applyBusinessRules({entity_var});",
        ])
        if has_pre_persist_initializer:
            body.append(
                "        // Server-set fields (status, etc.) are initialized via @PrePersist on the entity."
            )
        body.extend([
            f"        {entity.name} saved = {repository_var}.save({entity_var});",
            "        afterCreate(saved);",
            f"        {create_resp_class} {create_response_var} = new {create_resp_class}();",
        ])
        _append_response_mapping_setters(
            body,
            response_mappings=_fallback_response_field_mappings(entity),
            entity_fields=entity_fields,
            response_var=create_response_var,
            source_var="saved",
            indent="        ",
        )
        body.extend([
            f"        return {create_response_var};",
            "    }",
        ])

    # Additional non-create operation stubs
    for ctx in op_contexts:
        category = _operation_category(ctx)
        if category in {"create", "update", "delete"}:
            continue
        if not explicit_read_surface and category in {"get_by_id", "list"}:
            continue
        req_class = ctx["request_class_name"]
        resp_class = ctx["response_class_name"]
        request_mappings = ctx["request_field_mappings"]
        response_mappings = ctx["response_field_mappings"]
        response_var = resp_class[:1].lower() + resp_class[1:]
        method_name = ctx["java_operation_name"]
        path_variable_params = _operation_path_variable_service_signatures(ctx, id_java_type=id_java_type)
        operation_params = _service_parameter_signature(ctx)

        if category == "state_transition":
            id_arg = _primary_operation_id_argument_name(ctx)
            body.extend(
                [
                    "",
                    f"    public {resp_class} {method_name}({', '.join([*path_variable_params, *operation_params, f'{req_class} request'])}) {{",
                    f"        {entity.name} {entity_var} = {repository_var}.findById({id_arg})",
                    "            .orElseThrow(() -> new ResourceNotFoundException(",
                    f"                \"{entity.name} not found with id: \" + {id_arg}));",
                ]
            )
            for mapping in request_mappings:
                canonical_name = canonical_field_name(mapping)
                if canonical_name == id_field.name:
                    continue
                method_suffix = to_pascal_case(canonical_name)
                body.append(
                    f"        {entity_var}.set{method_suffix}(request.get{method_suffix}());"
                )
            body.extend(
                _emit_cross_entity_runtime_checks(
                    metadata=metadata,
                    entity=entity,
                    entity_fields=entity_fields,
                    exists_rules=cross_entity_checks,
                    state_rules=cross_entity_state_rules,
                    entity_var_expression=entity_var,
                )
            )
            body.extend(
                [
                    f"        beforeUpdate({entity_var});",
                    f"        applyBusinessRules({entity_var});",
                    f"        {entity.name} saved = {repository_var}.save({entity_var});",
                    "        afterUpdate(saved);",
                    f"        {resp_class} {response_var} = new {resp_class}();",
                ]
            )
            for mapping in response_mappings:
                canonical_name = canonical_field_name(mapping)
                if canonical_name not in entity_fields:
                    continue
                method_suffix = to_pascal_case(canonical_name)
                body.append(
                    f"        {response_var}.set{method_suffix}(saved.get{method_suffix}());"
                )
        elif category == "computed_read":
            id_arg = _computed_read_id_argument_name(entity, ctx)
            body.extend(
                [
                    "",
                    f"    public {resp_class} {method_name}({', '.join([*path_variable_params, *operation_params])}) {{",
                    f"        {entity.name} {entity_var} = {repository_var}.findById({id_arg})",
                    "            .orElseThrow(() -> new ResourceNotFoundException(",
                    f"                \"{entity.name} not found with id: \" + {id_arg}));",
                ]
            )
            body.append(f"        {resp_class} {response_var} = new {resp_class}();")
            for mapping in response_mappings:
                canonical_name = canonical_field_name(mapping)
                if canonical_name not in entity_fields:
                    continue
                method_suffix = to_pascal_case(canonical_name)
                body.append(
                    f"        {response_var}.set{method_suffix}({entity_var}.get{method_suffix}());"
                )
        elif explicit_read_surface and category == "get_by_id":
            id_arg = _verified_read_id_argument_name(entity, ctx)
            body.extend(
                [
                    "",
                    f"    public {resp_class} {method_name}({', '.join([*path_variable_params, *operation_params])}) {{",
                    f"        {entity.name} {entity_var} = {repository_var}.findById({id_arg})",
                    "            .orElseThrow(() -> new ResourceNotFoundException(",
                    f"                \"{entity.name} not found with id: \" + {id_arg}));",
                    f"        {resp_class} {response_var} = new {resp_class}();",
                ]
            )
            for mapping in response_mappings:
                canonical_name = canonical_field_name(mapping)
                if canonical_name not in entity_fields:
                    continue
                method_suffix = to_pascal_case(canonical_name)
                body.append(
                    f"        {response_var}.set{method_suffix}({entity_var}.get{method_suffix}());"
                )
        elif explicit_read_surface and category in {"list", "read_list"}:
            method_params = [*path_variable_params, *operation_params]
            if _is_pageable_list_context(ctx):
                body.extend(
                    [
                        "",
                        f"    public Page<{resp_class}> {method_name}({', '.join([*method_params, 'Pageable pageable'])}) {{",
                        f"        return {repository_var}.findAll(pageable).map(record -> {{",
                        f"            {resp_class} {response_var} = new {resp_class}();",
                    ]
                )
            else:
                body.extend(
                    [
                        "",
                        f"    public List<{resp_class}> {method_name}({', '.join(method_params)}) {{"
                        if method_params
                        else f"    public List<{resp_class}> {method_name}() {{",
                        f"        List<{entity.name}> records = {repository_var}.findAll();",
                        f"        List<{resp_class}> responses = new java.util.ArrayList<>();",
                        f"        for ({entity.name} record : records) {{",
                        f"            {resp_class} {response_var} = new {resp_class}();",
                    ]
                )
            for mapping in response_mappings:
                canonical_name = canonical_field_name(mapping)
                if canonical_name not in entity_fields:
                    continue
                method_suffix = to_pascal_case(canonical_name)
                body.append(
                    f"            {response_var}.set{method_suffix}(record.get{method_suffix}());"
                )
            if _is_pageable_list_context(ctx):
                body.extend(
                    [
                        f"            return {response_var};",
                        "        });",
                        "    }",
                    ]
                )
            else:
                body.extend(
                    [
                        f"            responses.add({response_var});",
                        "        }",
                        "        return responses;",
                        "    }",
                    ]
                )
            continue
        elif category == "read_list":
            method_params = [*path_variable_params, *operation_params]
            if _is_pageable_list_context(ctx):
                body.extend(
                    [
                        "",
                        f"    public Page<{resp_class}> {method_name}({', '.join([*method_params, 'Pageable pageable'])}) {{",
                        f"        return {repository_var}.findAll(pageable).map(record -> {{",
                        f"            {resp_class} {response_var} = new {resp_class}();",
                    ]
                )
            else:
                body.extend(
                    [
                        "",
                        f"    public List<{resp_class}> {method_name}({', '.join(method_params)}) {{"
                        if method_params
                        else f"    public List<{resp_class}> {method_name}() {{",
                        f"        List<{entity.name}> records = {repository_var}.findAll();",
                        f"        List<{resp_class}> responses = new java.util.ArrayList<>();",
                        f"        for ({entity.name} record : records) {{",
                        f"            {resp_class} {response_var} = new {resp_class}();",
                    ]
                )
            for mapping in response_mappings:
                canonical_name = canonical_field_name(mapping)
                if canonical_name not in entity_fields:
                    continue
                method_suffix = to_pascal_case(canonical_name)
                body.append(
                    f"            {response_var}.set{method_suffix}(record.get{method_suffix}());"
                )
            if _is_pageable_list_context(ctx):
                body.extend(
                    [
                        f"            return {response_var};",
                        "        });",
                        "    }",
                    ]
                )
            else:
                body.extend(
                    [
                        f"            responses.add({response_var});",
                        "        }",
                        "        return responses;",
                        "    }",
                    ]
                )
            continue
        elif ctx.get("http_method") == HttpMethod.GET or category == "get_by_id":
            body.extend(
                [
                    "",
                    f"    public {resp_class} {method_name}({req_class} request) {{",
                    f"        {entity.name} {entity_var} = {repository_var}.findById(request.get{to_pascal_case(id_field.name)}())",
                    "            .orElseThrow(() -> new ResourceNotFoundException(",
                    f"                \"{entity.name} not found with id: \" + request.get{to_pascal_case(id_field.name)}()));",
                    f"        {resp_class} {response_var} = new {resp_class}();",
                ]
            )
            for mapping in response_mappings:
                canonical_name = canonical_field_name(mapping)
                if canonical_name not in entity_fields:
                    continue
                method_suffix = to_pascal_case(canonical_name)
                body.append(
                    f"        {response_var}.set{method_suffix}({entity_var}.get{method_suffix}());"
                )
        else:
            body.extend(
                [
                    "",
                    f"    public {resp_class} {method_name}({req_class} request) {{",
                    f"        {entity.name} {entity_var} = new {entity.name}();",
                ]
            )
            for mapping in request_mappings:
                canonical_name = canonical_field_name(mapping)
                method_suffix = to_pascal_case(canonical_name)
                body.append(
                    f"        {entity_var}.set{method_suffix}(request.get{method_suffix}());"
                )
            body.extend(
                [
                    f"        beforeCreate({entity_var});",
                    f"        applyBusinessRules({entity_var});",
                    f"        {entity.name} saved = {repository_var}.save({entity_var});",
                    "        afterCreate(saved);",
                    f"        {resp_class} {response_var} = new {resp_class}();",
                ]
            )
            for mapping in response_mappings:
                canonical_name = canonical_field_name(mapping)
                if canonical_name not in entity_fields:
                    continue
                method_suffix = to_pascal_case(canonical_name)
                body.append(
                    f"        {response_var}.set{method_suffix}(saved.get{method_suffix}());"
                )
        body.extend(
            [
                f"        return {response_var};",
                "    }",
            ]
        )

    body.extend(
        [
            "",
            f"    protected void beforeCreate({entity.name} {entity_var}) {{",
            "    }",
            "",
            f"    protected void afterCreate({entity.name} {entity_var}) {{",
            "    }",
            "",
            f"    protected void beforeUpdate({entity.name} {entity_var}) {{",
            "    }",
            "",
            f"    protected void afterUpdate({entity.name} {entity_var}) {{",
            "    }",
            "",
            f"    protected void beforeDelete({id_java_type} id) {{",
            "    }",
            "",
            f"    protected void validateFormat({entity.name} {entity_var}, String fieldName, Object value) {{",
            "    }",
            "",
            f"    protected void compareValues({entity.name} {entity_var}, String ruleName, Object leftValue, Object rightValue, String operator) {{",
            "    }",
            "",
            f"    protected void validateComparison({entity.name} {entity_var}, String ruleName, Object leftValue, Object rightValue, String operator) {{",
            "    }",
            "",
            f"    protected void afterGeneratedBusinessRules({entity.name} {entity_var}) {{",
            "    }",
            "",
            f"    protected {entity.name} computeDerivedRead(String operationName, Object... args) {{",
            f"        throw new UnsupportedOperationException(\"Override computeDerivedRead in {entity.name}Service\");",
            "    }",
        ]
    )

    # applyBusinessRules — shared across all write operations
    body.extend(["", f"    protected final void applyBusinessRules({entity.name} {entity_var}) {{"])
    for rule in metadata.rules:
        if rule.entity_name != entity.name:
            continue
        field = entity_fields.get(rule.field_name)
        if field is None:
            if rule.type == RuleType.FIELD_COMPARISON:
                _append_generation_warning(
                    metadata,
                    f"{entity.name}: field-comparison rule on '{rule.field_name}' skipped because the field was not found on the entity."
                )
            continue
        if _ignore_business_key_rule_for_server_generated_id(field, rule):
            continue
        method_suffix = to_pascal_case(rule.field_name)
        if rule.type == RuleType.ALLOWED_VALUES:
            constant_name = f"ALLOWED_{to_snake_case(rule.field_name).upper()}_VALUES"
            body.extend(
                [
                    f"        if ({entity_var}.get{method_suffix}() != null && !{constant_name}.contains({entity_var}.get{method_suffix}())) {{",
                    f"            throw new IllegalArgumentException(\"Invalid value for {rule.field_name}: \" + {entity_var}.get{method_suffix}());",
                    "        }",
                ]
            )
        elif rule.type == RuleType.DEFAULT:
            body.extend(
                [
                    f"        if ({entity_var}.get{method_suffix}() == null) {{",
                    f"            {entity_var}.set{method_suffix}({_java_literal(field)});",
                    "        }",
                ]
            )
        elif rule.type == RuleType.FORMAT:
            if rule.format == "iso-4217":
                body.extend(
                    [
                        f'        if ({entity_var}.get{method_suffix}() != null && !{entity_var}.get{method_suffix}().matches("[A-Z]{{3}}")) {{',
                        "            throw new IllegalArgumentException(",
                        f'                "Invalid ISO-4217 currency code: " + {entity_var}.get{method_suffix}());',
                        "        }",
                    ]
                )
            else:
                body.extend(
                    [
                        f"        if ({entity_var}.get{method_suffix}() != null) {{",
                        f"            validateFormat({entity_var}, \"{rule.field_name}\", {entity_var}.get{method_suffix}());",
                        "        }",
                    ]
                )
        elif rule.type == RuleType.FIELD_COMPARISON:
            compare_to_field_name = rule.compare_to_field or ""
            if compare_to_field_name == rule.field_name:
                _append_generation_warning(
                    metadata,
                    f"{entity.name}: field-comparison rule on '{rule.field_name}' skipped because it compares the field to itself."
                )
                continue

            compare_field = entity_fields.get(compare_to_field_name)
            if compare_field is None:
                _append_generation_warning(
                    metadata,
                    f"{entity.name}: field-comparison rule on '{rule.field_name}' skipped because compare-to-field '{compare_to_field_name}' was not found on the entity."
                )
                continue

            if field.type != compare_field.type:
                _append_generation_warning(
                    metadata,
                    f"{entity.name}: field-comparison rule on '{rule.field_name}' skipped because '{rule.field_name}' ({field.type.value}) and '{compare_to_field_name}' ({compare_field.type.value}) have different canonical types."
                )
                continue

            compare_method_suffix = to_pascal_case(compare_to_field_name)
            left_getter = f"{entity_var}.get{method_suffix}()"
            right_getter = f"{entity_var}.get{compare_method_suffix}()"

            if field.type == CanonicalFieldType.DECIMAL:
                body.extend(
                    [
                        f"        if ({left_getter} != null && {right_getter} != null",
                        f"                && !({_field_comparison_decimal_expression(left_getter, right_getter, rule.operator or '')})) {{",
                        f'            throw new IllegalArgumentException("{rule.field_name} must be {rule.operator} {compare_to_field_name} but got {rule.field_name}=" + {left_getter} + ", {compare_to_field_name}=" + {right_getter});',
                        "        }",
                    ]
                )
            elif field.type == CanonicalFieldType.INTEGER:
                body.extend(
                    [
                        f"        if ({left_getter} != null && {right_getter} != null",
                        f"                && !({left_getter} {rule.operator} {right_getter})) {{",
                        f'            throw new IllegalArgumentException("{rule.field_name} must be {rule.operator} {compare_to_field_name} but got {rule.field_name}=" + {left_getter} + ", {compare_to_field_name}=" + {right_getter});',
                        "        }",
                    ]
                )
            elif field.type == CanonicalFieldType.STRING:
                _append_generation_warning(
                    metadata,
                    f"{entity.name}: field-comparison rule on '{rule.field_name}' skipped because String comparisons are not supported in v1."
                )
                body.extend(
                    [
                        f"        compareValues({entity_var}, \"{rule.field_name}\", {left_getter}, {right_getter}, \"{rule.operator or ''}\");",
                        f"        validateComparison({entity_var}, \"{rule.field_name}\", {left_getter}, {right_getter}, \"{rule.operator or ''}\");",
                    ]
                )
            else:
                _append_generation_warning(
                    metadata,
                    f"{entity.name}: field-comparison rule on '{rule.field_name}' skipped because canonical type '{field.type.value}' is not supported in v1."
                )
    body.extend([f"        afterGeneratedBusinessRules({entity_var});", "    }", "}"])

    return _java_file(
        package_name=f"{root_package}.service",
        imports=sorted(imports),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_developer_service(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    root_package: str,
    id_java_type: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    repository_var = f"{entity.name[:1].lower() + entity.name[1:]}Repository"
    entity_var = entity.name[:1].lower() + entity.name[1:]

    imports: set[str] = {
        f"{root_package}.domain.{entity.name}",
        f"{root_package}.repository.{entity.name}Repository",
        "org.springframework.stereotype.Service",
    }
    id_java_import = JAVA_IMPORTS.get(id_java_type)
    if id_java_import:
        imports.add(id_java_import)

    ctor_params = [f"{entity.name}Repository {repository_var}"]
    ctor_args = [repository_var]

    body: list[str] = [
        "@Service",
        f"public class {entity.name}Service extends {entity.name}ServiceBase {{",
        "",
        "    /*",
        "     * Developer-owned extension points.",
        "     * Add business logic in this class; EdgeForge scaffolds it once and preserves",
        "     * your edits across regeneration. Generated CRUD, mapping, and validation",
        f"     * logic lives in {entity.name}ServiceBase and is refreshed by the Engine.",
        "     */",
        "",
        f"    public {entity.name}Service({', '.join(ctor_params)}) {{",
        f"        super({', '.join(ctor_args)});",
        "    }",
        "",
        "    @Override",
        f"    protected void beforeCreate({entity.name} {entity_var}) {{",
        "        // Add pre-create business logic here.",
        "    }",
        "",
        "    @Override",
        f"    protected void afterCreate({entity.name} {entity_var}) {{",
        "        // Add post-create business logic here.",
        "    }",
        "",
        "    @Override",
        f"    protected void beforeUpdate({entity.name} {entity_var}) {{",
        "        // Add pre-update business logic here.",
        "    }",
        "",
        "    @Override",
        f"    protected void afterUpdate({entity.name} {entity_var}) {{",
        "        // Add post-update business logic here.",
        "    }",
        "",
        "    @Override",
        f"    protected void beforeDelete({id_java_type} id) {{",
        "        // Add pre-delete business logic here.",
        "    }",
        "",
        "    @Override",
        f"    protected void afterGeneratedBusinessRules({entity.name} {entity_var}) {{",
        "        // Add additional business rules here after generated checks pass.",
        "    }",
        "",
        "    @Override",
        f"    protected void validateFormat({entity.name} {entity_var}, String fieldName, Object value) {{",
        "        // Add custom format validation here.",
        "    }",
        "",
        "    @Override",
        f"    protected void compareValues({entity.name} {entity_var}, String ruleName, Object leftValue, Object rightValue, String operator) {{",
        "        // Add custom comparison preparation here.",
        "    }",
        "",
        "    @Override",
        f"    protected void validateComparison({entity.name} {entity_var}, String ruleName, Object leftValue, Object rightValue, String operator) {{",
        "        // Add custom comparison validation here.",
        "    }",
        "",
        "    @Override",
        f"    protected {entity.name} computeDerivedRead(String operationName, Object... args) {{",
        "        return super.computeDerivedRead(operationName, args);",
        "    }",
        "}",
    ]

    transport_methods = []
    for context in _operation_contexts_for_entity(metadata, entity):
        category = _operation_category(context)
        if category not in {"create", "update", "delete"} or not context.get("operation_parameters"):
            continue
        _add_operation_parameter_type_imports(imports, context)
        parameters = _service_parameter_signature(context)
        arguments = _operation_parameter_argument_names(context)
        if category != "create":
            parameters.insert(0, f"{id_java_type} id")
            arguments.insert(0, "id")
        if category == "delete":
            method_name, return_type = "delete", "void"
        else:
            request_class = context["request_class_name"]
            return_type = context["response_class_name"] if category == "create" else _operation_response_type(context, entity.name)
            imports.add(f"{root_package}.adapter.inbound.{request_class}")
            if return_type != entity.name:
                imports.add(f"{root_package}.adapter.inbound.{return_type}")
            method_name = context["java_operation_name"]
            parameters.append(f"{request_class} request")
            arguments.append("request")
        transport_methods.extend([
            "", "    // Transport inputs only: implement required business/security semantics before deployment.",
            "    // Header presence is not replay protection, signature verification or conditional-write enforcement.",
            "    @Override", f"    public {return_type} {method_name}({', '.join(parameters)}) {{",
            f"        {'return ' if return_type != 'void' else ''}super.{method_name}({', '.join(arguments)});", "    }",
        ])
    body[-1:-1] = transport_methods

    return _java_file(
        package_name=f"{root_package}.service",
        imports=sorted(imports),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
        ownership="developer",
    )


# ---------------------------------------------------------------------------
# Outbound writers (unchanged from pre-Phase-1a)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _DownstreamFileWriterContext:
    contract: ContractMetadata
    mappings: tuple[FieldMapping, ...]
    writer_class_name: str
    writer_var_name: str
    local_var_prefix: str
    file_extension: str
    output_file_name_prefix: str
    output_file_method_name: str
    temp_file_method_name: str
    output_context_key: str
    temp_context_key: str
    file_total_context_key: str
    has_control_records: bool


@dataclass(frozen=True)
class _EntityJavaArtifactPlan:
    """Deterministic per-entity decisions shared by emission and the schema baseline."""

    operation_contexts: list[dict]
    emit_generic_fallback_dtos: bool
    emit_generic_create_fallback: bool
    file_writer_contexts: list[_DownstreamFileWriterContext]
    emit_staging_writer: bool
    has_downstream_file: bool
    emit_batch_job: bool


@dataclass(frozen=True)
class _UpstreamFileIngestContext:
    contract: ContractMetadata
    entity: CanonicalEntity
    mappings: tuple[FieldMapping, ...]
    parser_class_name: str
    parser_var_name: str
    repository_var_name: str
    ingest_method_name: str


@dataclass(frozen=True)
class _UpstreamXmlIngestContext:
    contract: ContractMetadata
    entity: CanonicalEntity
    mappings: tuple[FieldMapping, ...]
    parser_class_name: str
    parser_var_name: str
    model_class_name: str
    repository_var_name: str
    ingest_method_name: str


@dataclass(frozen=True)
class _DownstreamXmlOutputContext:
    contract: ContractMetadata
    entity: CanonicalEntity
    mappings: tuple[FieldMapping, ...]
    serializer_class_name: str
    serializer_var_name: str
    model_class_name: str
    repository_var_name: str
    output_method_name: str
    contract_slug: str


@dataclass(frozen=True)
class _OutboundSoapActionContext:
    contract: ContractMetadata
    operation_name: str
    soap_contract: dict
    operation: dict
    canonical_operation: dict
    entity: CanonicalEntity
    id_field: CanonicalField
    lookup_field_name: str
    client_method_name: str


def _downstream_file_writer_contexts(
    metadata: MetadataProject,
    entity: CanonicalEntity,
) -> list[_DownstreamFileWriterContext]:
    mappings_by_contract: OrderedDict[str, list[FieldMapping]] = OrderedDict()
    for contract in metadata.contracts:
        if contract.type in {"file-fixed-width", "file-csv"}:
            mappings_by_contract[contract.name] = []
    for mapping in metadata.mappings:
        if (
            mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
            and mapping.source_path.startswith(f"{entity.name}.")
            and mapping.contract_name in mappings_by_contract
        ):
            mappings_by_contract[mapping.contract_name].append(mapping)

    contexts: list[_DownstreamFileWriterContext] = []
    active_contracts = [
        (contract, mappings_by_contract[contract.name])
        for contract in metadata.contracts
        if contract.name in mappings_by_contract and mappings_by_contract[contract.name]
    ]
    single_contract = len(active_contracts) == 1
    entity_var = entity.name[:1].lower() + entity.name[1:]
    used_writer_class_names: set[str] = set()
    used_writer_var_names: set[str] = set()
    used_local_var_prefixes: set[str] = set()
    used_output_method_names: set[str] = set()
    used_temp_method_names: set[str] = set()
    used_contract_slugs: set[str] = set()
    for contract, mappings in active_contracts:
        contract_slug_base = to_snake_case(contract.name).replace("_", "-") or contract.name.lower()
        contract_slug = contract_slug_base
        writer_class_name = f"{entity.name}EodHandoffFileWriter"
        writer_var_name = "handoffFileWriter"
        local_var_prefix = to_java_method_name(contract.name, fallback="file")
        output_file_method_name = "outputFile"
        temp_file_method_name = "tempFile"
        if not single_contract:
            contract_slug = _unique_generated_slug(contract_slug_base, used_contract_slugs)
            writer_class_name = _unique_generated_name(
                f"{entity.name}{to_pascal_case(contract.name)}FileWriter",
                used_writer_class_names,
            )
            writer_var_name = _unique_generated_name(
                to_java_method_name(
                    f"{contract.name}FileWriter",
                    fallback="handoffFileWriter",
                ),
                used_writer_var_names,
            )
            local_var_prefix = _unique_generated_name(
                to_java_method_name(contract.name, fallback="file"),
                used_local_var_prefixes,
            )
            output_file_method_name = _unique_generated_name(
                to_java_method_name(
                    f"{contract.name}OutputFile",
                    fallback="outputFile",
                ),
                used_output_method_names,
            )
            temp_file_method_name = _unique_generated_name(
                to_java_method_name(f"{contract.name}TempFile", fallback="tempFile"),
                used_temp_method_names,
            )
        output_identity = "outputFile" if single_contract else f"outputFile.{contract.name}"
        temp_identity = "tempOutputFile" if single_contract else f"tempOutputFile.{contract.name}"
        total_identity = "fileTotal" if single_contract else f"fileTotal.{contract.name}"
        contexts.append(
            _DownstreamFileWriterContext(
                contract=contract,
                mappings=tuple(mappings),
                writer_class_name=writer_class_name,
                writer_var_name=writer_var_name,
                local_var_prefix=local_var_prefix,
                file_extension=_file_output_extension_for_contract(contract),
                output_file_name_prefix=(
                    f"{entity_var}-eod-"
                    if single_contract
                    else f"{entity_var}-{contract_slug}-"
                ),
                output_file_method_name=output_file_method_name,
                temp_file_method_name=temp_file_method_name,
                output_context_key=output_identity,
                temp_context_key=temp_identity,
                file_total_context_key=total_identity,
                has_control_records=_contract_has_enhanced_fixed_width_control_records(contract),
            )
        )
    return contexts


def _unique_generated_name(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _unique_generated_slug(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _file_output_extension_for_contract(contract: ContractMetadata) -> str:
    return "csv" if contract.type == "file-csv" else "dat"


def _contract_has_enhanced_fixed_width_control_records(contract: ContractMetadata) -> bool:
    return (
        contract.type == "file-fixed-width"
        and bool(contract.file_layout)
        and not bool(contract.file_layout.get("is_flat_fixed_width"))
    )


def _render_file_writer(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    file_writer_context: _DownstreamFileWriterContext | None = None,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    if file_writer_context is None:
        contexts = _downstream_file_writer_contexts(metadata, entity)
        if not contexts:
            raise ValueError(
                f"No downstream file mappings found for entity '{entity.name}'"
            )
        file_writer_context = contexts[0]

    entity_mappings = list(file_writer_context.mappings)
    contract = file_writer_context.contract
    if not entity_mappings:
        raise ValueError(
            f"No downstream file mappings found for entity '{entity.name}' "
            f"and contract '{contract.name}'"
        )
    if contract.type == "file-csv":
        return _render_csv_file_writer(
            contract=contract,
            mappings=entity_mappings,
            entity=entity,
            writer_class_name=file_writer_context.writer_class_name,
            root_package=root_package,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    if contract.type != "file-fixed-width":
        raise ValueError(
            f"Downstream file writer generation is not implemented for contract "
            f"'{contract.name}' ({contract.type})."
        )
    if contract.file_layout and not bool(contract.file_layout.get("is_flat_fixed_width")):
        return _render_enhanced_fixed_width_file_writer(
            contract=contract,
            mappings=entity_mappings,
            entity=entity,
            writer_class_name=file_writer_context.writer_class_name,
            root_package=root_package,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    mappings = entity_mappings
    entity_fields = {field.name: field for field in entity.fields}
    entity_var = entity.name[:1].lower() + entity.name[1:]
    writer_class_name = file_writer_context.writer_class_name
    layout = contract.file_layout or {}
    encoding = str(layout.get("encoding") or "UTF-8")
    body = [
        "@Component",
        f"public class {writer_class_name} {{",
        f"    private static final Charset FILE_CHARSET = Charset.forName({_java_code_string_literal(encoding)});",
        "",
        f"    public void write({entity.name} {entity_var}, Path outputPath) throws IOException {{",
        f"        String line = renderLine({entity_var});",
        "        Files.writeString(",
        "            outputPath,",
        "            line + System.lineSeparator(),",
        "            FILE_CHARSET,",
        "            StandardOpenOption.CREATE,",
        "            StandardOpenOption.APPEND",
        "        );",
        "    }",
        "",
        f"    public String renderLine({entity.name} {entity_var}) {{",
        "        StringBuilder line = new StringBuilder();",
    ]
    has_widths = any(mapping.layout_width is not None for mapping in mappings)
    has_minor_unit_mappings = any(
        _is_minor_unit_output_mapping(mapping, entity_fields=entity_fields)
        for mapping in mappings
    )
    for mapping in mappings:
        field_name = mapping.source_path.split(".", 1)[1]
        getter = to_pascal_case(field_name)
        if _is_minor_unit_output_mapping(mapping, entity_fields=entity_fields):
            value_expression = f"minorUnitString({entity_var}.get{getter}())"
            if mapping.layout_width is not None:
                body.append(
                    f"        line.append(fixedWidthMinorUnitString({entity_var}.get{getter}(), {mapping.layout_width}));"
                )
            else:
                body.append(f"        line.append({value_expression});")
        elif mapping.layout_width is not None:
            body.append(
                f"        line.append(padRight(stringValue({entity_var}.get{getter}()), {mapping.layout_width}));"
            )
        else:
            body.append(
                f"        line.append(stringValue({entity_var}.get{getter}()));"
            )
    body.extend(
        [
            "        return line.toString();",
            "    }",
            "",
            "    private String stringValue(Object value) {",
            "        return value == null ? \"\" : value.toString();",
            "    }",
        ]
    )
    if has_minor_unit_mappings:
        body.extend(
            [
                "",
                "    private String minorUnitString(BigDecimal value) {",
                "        if (value == null) {",
                '            return "";',
                "        }",
                "        return value.movePointRight(2).toBigIntegerExact().toString();",
                "    }",
                "",
                "    private String fixedWidthMinorUnitString(BigDecimal value, int width) {",
                "        if (value == null) {",
                '            return " ".repeat(width);',
                "        }",
                "        String converted = minorUnitString(value);",
                "        if (converted.length() > width) {",
                '            throw new IllegalArgumentException("Minor-unit value exceeds fixed width " + width);',
                "        }",
                '        return "0".repeat(width - converted.length()) + converted;',
                "    }",
            ]
        )
    if has_widths:
        body.extend(
            [
                "",
                "    private String padRight(String value, int width) {",
                '        if (value == null) value = "";',
                "        if (value.length() >= width) return value.substring(0, width);",
                '        return value + " ".repeat(width - value.length());',
                "    }",
            ]
        )
    body.append("}")
    return _java_file(
        package_name=f"{root_package}.adapter.outbound",
        imports=[
            f"{root_package}.domain.{entity.name}",
            *(["java.math.BigDecimal"] if has_minor_unit_mappings else []),
            "java.io.IOException",
            "java.nio.charset.Charset",
            "java.nio.file.Files",
            "java.nio.file.Path",
            "java.nio.file.StandardOpenOption",
            "org.springframework.stereotype.Component",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_enhanced_fixed_width_file_writer(
    *,
    contract: ContractMetadata,
    mappings: list[FieldMapping],
    entity: CanonicalEntity,
    writer_class_name: str | None = None,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    layout = contract.file_layout or {}
    _validate_enhanced_fixed_width_writer_layout(contract_name=contract.name, layout=layout)
    record_types = {
        str(record_type["name"]): record_type
        for record_type in layout.get("record_types") or []
    }
    unsupported_record_types = set(record_types) - {"header", "data", "detail", "trailer"}
    if unsupported_record_types:
        raise ValueError(
            f"Enhanced fixed-width writer for contract '{contract.name}' supports only "
            f"header/data/detail/trailer record types; unsupported: "
            f"{sorted(unsupported_record_types)!r}."
        )
    data_record = record_types.get("data") or record_types.get("detail")
    if data_record is None:
        raise ValueError(
            f"Enhanced fixed-width writer for contract '{contract.name}' requires "
            "a data or detail record type."
        )
    header_record = record_types.get("header")
    trailer_record = record_types.get("trailer")
    mapping_by_target = {
        mapping.target_path.rsplit(".", 1)[1]: mapping
        for mapping in mappings
    }
    entity_fields = {field.name: field for field in entity.fields}
    entity_var = entity.name[:1].lower() + entity.name[1:]
    writer_class_name = writer_class_name or f"{entity.name}EodHandoffFileWriter"
    encoding = str(layout.get("encoding") or "UTF-8")
    sum_field_name = _enhanced_fixed_width_sum_source_field(
        contract=contract,
        trailer_record=trailer_record,
        entity=entity,
        entity_fields=entity_fields,
    )

    body = [
        "@Component",
        f"public class {writer_class_name} {{",
        f"    private static final Charset FILE_CHARSET = Charset.forName({_java_code_string_literal(encoding)});",
        "",
        "    public void startFile(Path outputPath, String runId) throws IOException {",
    ]
    if header_record is not None:
        body.extend(
            [
                "        Files.writeString(",
                "            outputPath,",
                "            renderHeader(runId) + System.lineSeparator(),",
                "            FILE_CHARSET,",
                "            StandardOpenOption.CREATE,",
                "            StandardOpenOption.APPEND",
                "        );",
            ]
        )
    body.extend(
        [
            "    }",
            "",
            f"    public void write({entity.name} {entity_var}, Path outputPath) throws IOException {{",
            f"        String line = renderLine({entity_var});",
            "        Files.writeString(",
            "            outputPath,",
            "            line + System.lineSeparator(),",
            "            FILE_CHARSET,",
            "            StandardOpenOption.CREATE,",
            "            StandardOpenOption.APPEND",
            "        );",
            "    }",
            "",
            "    public void finishFile(Path outputPath, long recordCount, BigDecimal totalValue) throws IOException {",
        ]
    )
    if trailer_record is not None:
        body.extend(
            [
                "        Files.writeString(",
                "            outputPath,",
                "            renderTrailer(recordCount, totalValue) + System.lineSeparator(),",
                "            FILE_CHARSET,",
                "            StandardOpenOption.CREATE,",
                "            StandardOpenOption.APPEND",
                "        );",
            ]
        )
    body.extend(
        [
            "    }",
            "",
            f"    public String renderLine({entity.name} {entity_var}) {{",
            f"        return renderDataLine({entity_var});",
            "    }",
            "",
        ]
    )
    if header_record is not None:
        _append_enhanced_fixed_width_record_renderer(
            body,
            method_signature="public String renderHeader(String runId)",
            record=header_record,
            value_expression=lambda field: _enhanced_fixed_width_control_expression(
                contract=contract,
                record_name="header",
                field=field,
                entity=entity,
                entity_fields=entity_fields,
                total_source_field_name=sum_field_name,
            ),
        )
    _append_enhanced_fixed_width_record_renderer(
        body,
        method_signature=f"private String renderDataLine({entity.name} {entity_var})",
        record=data_record,
        value_expression=lambda field: _enhanced_fixed_width_data_expression(
            contract=contract,
            field=field,
            mapping_by_target=mapping_by_target,
            entity_fields=entity_fields,
            entity_var=entity_var,
        ),
    )
    if trailer_record is not None:
        _append_enhanced_fixed_width_record_renderer(
            body,
            method_signature="public String renderTrailer(long recordCount, BigDecimal totalValue)",
            record=trailer_record,
            value_expression=lambda field: _enhanced_fixed_width_control_expression(
                contract=contract,
                record_name="trailer",
                field=field,
                entity=entity,
                entity_fields=entity_fields,
                total_source_field_name=sum_field_name,
            ),
        )
    body.extend(
        [
            f"    public BigDecimal dataTotal({entity.name} {entity_var}) {{",
            "        BigDecimal total = BigDecimal.ZERO;",
        ]
    )
    if sum_field_name is not None:
        sum_field = entity_fields[sum_field_name]
        getter = to_pascal_case(sum_field_name)
        if sum_field.type == CanonicalFieldType.DECIMAL:
            body.extend(
                [
                    f"        BigDecimal value = {entity_var}.get{getter}();",
                    "        if (value != null) {",
                    "            total = total.add(value);",
                    "        }",
                ]
            )
        elif sum_field.type == CanonicalFieldType.INTEGER:
            body.extend(
                [
                    f"        Long value = {entity_var}.get{getter}();",
                    "        if (value != null) {",
                    "            total = total.add(BigDecimal.valueOf(value));",
                    "        }",
                ]
            )
    body.extend(
        [
            "        return total;",
            "    }",
            "",
            "    private String formatFixedWidthField(String fieldName, Object value, boolean required, String type, String format, int width, boolean zeroPad) {",
            "        if (value == null) {",
            "            if (required) {",
            "                throw new IllegalArgumentException(\"Required fixed-width field is null: \" + fieldName);",
            "            }",
            '            return " ".repeat(width);',
            "        }",
            "        String serialized = stringValue(value, type, format);",
            "        if (required && serialized.isBlank()) {",
            "            throw new IllegalArgumentException(\"Required fixed-width field is blank: \" + fieldName);",
            "        }",
            "        if (serialized.length() > width) {",
            "            throw new IllegalArgumentException(\"Fixed-width value exceeds width for \" + fieldName + \": \" + serialized.length() + \" > \" + width);",
            "        }",
            "        String padding = (zeroPad ? \"0\" : \" \").repeat(width - serialized.length());",
            "        return zeroPad ? padding + serialized : serialized + padding;",
            "    }",
            "",
            "    private String stringValue(Object value, String type, String format) {",
            "        if (value instanceof BigDecimal decimal) {",
            "            return decimal.toPlainString();",
            "        }",
            "        if (value instanceof LocalDate date) {",
            "            return format == null ? date.toString() : date.format(DateTimeFormatter.ofPattern(format));",
            "        }",
            "        if (value instanceof LocalDateTime dateTime) {",
            "            return format == null ? dateTime.toString() : dateTime.format(DateTimeFormatter.ofPattern(format));",
            "        }",
            "        return value.toString();",
            "    }",
            "",
            "    private String minorUnitString(BigDecimal value) {",
            "        if (value == null) {",
            '            return "";',
            "        }",
            "        return value.movePointRight(2).toBigIntegerExact().toString();",
            "    }",
            "",
            "    private String requireLineLength(String recordType, String line, int expectedLength) {",
            "        if (line.length() != expectedLength) {",
            "            throw new IllegalArgumentException(\"Fixed-width \" + recordType + \" record length mismatch: expected \" + expectedLength + \", got \" + line.length());",
            "        }",
            "        return line;",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.adapter.outbound",
        imports=[
            f"{root_package}.domain.{entity.name}",
            "java.io.IOException",
            "java.math.BigDecimal",
            "java.nio.charset.Charset",
            "java.nio.file.Files",
            "java.nio.file.Path",
            "java.nio.file.StandardOpenOption",
            "java.time.LocalDate",
            "java.time.LocalDateTime",
            "java.time.format.DateTimeFormatter",
            "org.springframework.stereotype.Component",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_csv_file_writer(
    *,
    contract: ContractMetadata,
    mappings: list[FieldMapping],
    entity: CanonicalEntity,
    writer_class_name: str | None = None,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    layout = contract.file_layout or {}
    _validate_csv_writer_layout(contract_name=contract.name, layout=layout)
    layout_fields = sorted(
        list(layout.get("fields") or []),
        key=lambda field: int(field["column"]),
    )
    mapping_by_target = {
        mapping.target_path.rsplit(".", 1)[1]: mapping
        for mapping in mappings
    }
    entity_fields = {field.name: field for field in entity.fields}
    entity_var = entity.name[:1].lower() + entity.name[1:]
    writer_class_name = writer_class_name or f"{entity.name}EodHandoffFileWriter"
    delimiter = str(layout.get("delimiter") or ",")
    quote_char = layout.get("quote_char")
    escape_char = layout.get("escape_char")
    has_header_row = bool(layout.get("has_header_row"))
    line_separator = str(layout.get("line_separator") or "\n")
    encoding = str(layout.get("encoding") or "UTF-8")
    for field in layout_fields:
        field_name = str(field["name"])
        if bool(field.get("required")) and field_name not in mapping_by_target:
            raise ValueError(
                f"Required CSV target field '{field_name}' is not mapped for "
                f"downstream contract '{contract.name}'."
            )
    body = [
        "@Component",
        f"public class {writer_class_name} {{",
        f"    private static final String DELIMITER = {_java_code_string_literal(delimiter)};",
        "    private static final String QUOTE_CHAR = "
        + ("null" if quote_char is None else _java_code_string_literal(str(quote_char)))
        + ";",
        "    private static final String ESCAPE_CHAR = "
        + ("null" if escape_char is None else _java_code_string_literal(str(escape_char)))
        + ";",
        f"    private static final String LINE_SEPARATOR = {_java_code_string_literal(line_separator)};",
        f"    private static final boolean HAS_HEADER_ROW = {'true' if has_header_row else 'false'};",
        f"    private static final Charset FILE_CHARSET = Charset.forName({_java_code_string_literal(encoding)});",
        "",
        f"    public void write({entity.name} {entity_var}, Path outputPath) throws IOException {{",
        "        if (HAS_HEADER_ROW && shouldWriteHeader(outputPath)) {",
        "            Files.writeString(",
        "                outputPath,",
        "                renderHeader() + LINE_SEPARATOR,",
        "                FILE_CHARSET,",
        "                StandardOpenOption.CREATE,",
        "                StandardOpenOption.APPEND",
        "            );",
        "        }",
        f"        String line = renderLine({entity_var});",
        "        Files.writeString(",
        "            outputPath,",
        "            line + LINE_SEPARATOR,",
        "            FILE_CHARSET,",
        "            StandardOpenOption.CREATE,",
        "            StandardOpenOption.APPEND",
        "        );",
        "    }",
        "",
        "    public String renderHeader() {",
        "        return String.join(DELIMITER, List.of(",
    ]
    for index, field in enumerate(layout_fields):
        suffix = "," if index < len(layout_fields) - 1 else ""
        body.append(f"            encode({_java_code_string_literal(str(field['name']))}){suffix}")
    body.extend(
        [
            "        ));",
            "    }",
            "",
            f"    public String renderLine({entity.name} {entity_var}) {{",
            "        List<String> columns = new ArrayList<>();",
        ]
    )
    for field in layout_fields:
        field_name = str(field["name"])
        mapping = mapping_by_target.get(field_name)
        if mapping is None:
            body.append('        columns.add("");')
            continue
        canonical_name = mapping.source_path.split(".", 1)[1]
        getter = to_pascal_case(canonical_name)
        canonical_field = entity_fields.get(canonical_name)
        if canonical_field is None:
            raise ValueError(
                f"CSV downstream mapping references unknown source field "
                f"'{mapping.source_path}'."
            )
        required = "true" if bool(field.get("required")) else "false"
        field_type = str(field.get("type") or "string")
        is_minor_unit_mapping = _is_minor_unit_output_mapping(
            mapping, entity_fields=entity_fields
        )
        if is_minor_unit_mapping:
            if not _csv_minor_unit_layout_type_compatible(field_type):
                raise ValueError(
                    f"CSV downstream field '{field_name}' expects layout type "
                    f"'{field_type}', but type_coercion "
                    f"'{_MINOR_UNIT_TYPE_COERCION}' produces integer minor units."
                )
        elif not _csv_layout_type_compatible(field_type, canonical_field.type):
            raise ValueError(
                f"CSV downstream field '{field_name}' expects layout type "
                f"'{field_type}', but source field '{mapping.source_path}' is "
                f"{canonical_field.type.value}."
            )
        field_format = field.get("format")
        field_format_literal = (
            "null"
            if field_format in (None, "")
            else _java_code_string_literal(str(field_format))
        )
        value_expression = f"{entity_var}.get{getter}()"
        if is_minor_unit_mapping:
            value_expression = f"minorUnitString({value_expression})"
        body.append(
            "        columns.add(formatColumn("
            f"{_java_code_string_literal(field_name)}, "
            f"{value_expression}, "
            f"{required}, "
            f"{_java_code_string_literal(field_type)}, "
            f"{field_format_literal}"
            "));"
        )
    body.extend(
        [
            "        return String.join(DELIMITER, columns);",
            "    }",
            "",
            "    private boolean shouldWriteHeader(Path outputPath) throws IOException {",
            "        return !Files.exists(outputPath) || Files.size(outputPath) == 0L;",
            "    }",
            "",
            "    private String formatColumn(String fieldName, Object value, boolean required, String type, String format) {",
            "        if (value == null) {",
            "            if (required) {",
            "                throw new IllegalArgumentException(\"Required CSV field is null: \" + fieldName);",
            "            }",
            '            return "";',
            "        }",
            "        String serialized = stringValue(value, type, format);",
            "        if (required && serialized.isBlank()) {",
            "            throw new IllegalArgumentException(\"Required CSV field is blank: \" + fieldName);",
            "        }",
            "        return encode(serialized);",
            "    }",
            "",
            "    private String stringValue(Object value, String type, String format) {",
            "        if (value instanceof BigDecimal decimal) {",
            "            return decimal.toPlainString();",
            "        }",
            "        if (value instanceof LocalDate date) {",
            "            return format == null ? date.toString() : date.format(DateTimeFormatter.ofPattern(format));",
            "        }",
            "        if (value instanceof LocalDateTime dateTime) {",
            "            return format == null ? dateTime.toString() : dateTime.format(DateTimeFormatter.ofPattern(format));",
            "        }",
            "        return value.toString();",
            "    }",
            "",
            "    private String minorUnitString(BigDecimal value) {",
            "        if (value == null) {",
            '            return "";',
            "        }",
            "        return value.movePointRight(2).toBigIntegerExact().toString();",
            "    }",
            "",
            "    private String encode(String value) {",
            "        boolean mustQuote = value.contains(DELIMITER)",
            "                || value.contains(LINE_SEPARATOR)",
            "                || (QUOTE_CHAR != null && value.contains(QUOTE_CHAR));",
            "        if (mustQuote && QUOTE_CHAR != null) {",
            "            String encoded = value;",
            "            if (ESCAPE_CHAR != null) {",
            "                encoded = encoded.replace(ESCAPE_CHAR, ESCAPE_CHAR + ESCAPE_CHAR);",
            "                encoded = encoded.replace(QUOTE_CHAR, ESCAPE_CHAR + QUOTE_CHAR);",
            "            } else if (value.contains(QUOTE_CHAR)) {",
            "                throw new IllegalArgumentException(\"CSV value contains quote_char, but escape_char is disabled\");",
            "            }",
            "            return QUOTE_CHAR + encoded + QUOTE_CHAR;",
            "        }",
            "        if (mustQuote) {",
            "            throw new IllegalArgumentException(\"CSV value requires quoting, but quote_char is disabled\");",
            "        }",
            "        return value;",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.adapter.outbound",
        imports=[
            f"{root_package}.domain.{entity.name}",
            "java.io.IOException",
            "java.math.BigDecimal",
            "java.nio.charset.Charset",
            "java.nio.file.Files",
            "java.nio.file.Path",
            "java.nio.file.StandardOpenOption",
            "java.time.LocalDate",
            "java.time.LocalDateTime",
            "java.time.format.DateTimeFormatter",
            "java.util.ArrayList",
            "java.util.List",
            "org.springframework.stereotype.Component",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _validate_csv_writer_layout(*, contract_name: str, layout: dict) -> None:
    if not layout:
        raise ValueError(f"Missing CSV layout metadata for downstream contract '{contract_name}'.")
    if not layout.get("fields"):
        raise ValueError(f"Missing CSV data fields for downstream contract '{contract_name}'.")


def _append_enhanced_fixed_width_record_renderer(
    body: list[str],
    *,
    method_signature: str,
    record: dict,
    value_expression,
) -> None:
    record_name = str(record["name"])
    expected_length = int(record["expected_length"])
    body.extend(
        [
            f"    {method_signature} {{",
            "        StringBuilder line = new StringBuilder();",
        ]
    )
    indicator = record.get("indicator")
    if isinstance(indicator, dict):
        body.append(
            f"        line.append({_java_code_string_literal(str(indicator['value']))});"
        )
    for field in sorted(record.get("fields") or [], key=lambda item: int(item["position"])):
        field_name = str(field["name"])
        expression, zero_pad = value_expression(field)
        required = "true" if bool(field.get("required")) else "false"
        field_type = str(field.get("type") or "string")
        field_format = field.get("format")
        field_format_literal = (
            "null"
            if field_format in (None, "")
            else _java_code_string_literal(str(field_format))
        )
        body.append(
            "        line.append(formatFixedWidthField("
            f"{_java_code_string_literal(field_name)}, "
            f"{expression}, "
            f"{required}, "
            f"{_java_code_string_literal(field_type)}, "
            f"{field_format_literal}, "
            f"{int(field['length'])}, "
            f"{'true' if zero_pad else 'false'}"
            "));"
        )
    body.extend(
        [
            "        return requireLineLength("
            + _java_code_string_literal(record_name)
            + f", line.toString(), {expected_length});",
            "    }",
            "",
        ]
    )


def _validate_enhanced_fixed_width_writer_layout(*, contract_name: str, layout: dict) -> None:
    for record_type in layout.get("record_types") or []:
        indicator = record_type.get("indicator")
        if not isinstance(indicator, dict):
            continue
        if int(indicator.get("position", 1)) != 1:
            raise ValueError(
                "Enhanced fixed-width downstream writer requires leading "
                f"indicators at position 1 for contract '{contract_name}'. "
                f"Record type '{record_type.get('name')}' declares indicator.position "
                f"{indicator.get('position')}."
            )


def _enhanced_fixed_width_data_expression(
    *,
    contract: ContractMetadata,
    field: dict,
    mapping_by_target: dict[str, FieldMapping],
    entity_fields: dict[str, CanonicalField],
    entity_var: str,
) -> tuple[str, bool]:
    field_name = str(field["name"])
    if _is_filler_field(field_name):
        return _java_code_string_literal(""), False
    mapping = mapping_by_target.get(field_name)
    if mapping is None:
        if bool(field.get("required")):
            raise ValueError(
                f"Required enhanced fixed-width data field '{field_name}' is not "
                f"mapped for downstream contract '{contract.name}'."
            )
        return _java_code_string_literal(""), False
    source_field_name = mapping.source_path.split(".", 1)[1]
    source_field = entity_fields.get(source_field_name)
    if source_field is None:
        raise ValueError(
            f"Enhanced fixed-width mapping references unknown source field "
            f"'{mapping.source_path}'."
        )
    field_type = str(field.get("type") or "string")
    is_minor_unit_mapping = _is_minor_unit_output_mapping(
        mapping, entity_fields=entity_fields
    ) or str(field.get("decimal_format") or "").lower() == "minor_units"
    if is_minor_unit_mapping:
        if source_field.type != CanonicalFieldType.DECIMAL:
            raise ValueError(
                "Enhanced fixed-width minor-unit field "
                f"'{field_name}' requires DECIMAL source field "
                f"'{mapping.source_path}', got '{source_field.type.value}'."
            )
        if not _csv_minor_unit_layout_type_compatible(field_type):
            raise ValueError(
                f"Enhanced fixed-width field '{field_name}' expects layout type "
                f"'{field_type}', but minor-unit output produces integer values."
            )
        return f"minorUnitString({entity_var}.get{to_pascal_case(source_field_name)}())", True
    if not _csv_layout_type_compatible(field_type, source_field.type):
        raise ValueError(
            f"Enhanced fixed-width field '{field_name}' expects layout type "
            f"'{field_type}', but source field '{mapping.source_path}' is "
            f"{source_field.type.value}."
        )
    return f"{entity_var}.get{to_pascal_case(source_field_name)}()", _is_numeric_layout_type(field_type)


def _enhanced_fixed_width_control_expression(
    *,
    contract: ContractMetadata,
    record_name: str,
    field: dict,
    entity: CanonicalEntity,
    entity_fields: dict[str, CanonicalField],
    total_source_field_name: str | None,
) -> tuple[str, bool]:
    field_name = str(field["name"])
    if _is_filler_field(field_name):
        return _java_code_string_literal(""), False
    value_source = field.get("value_source")
    if value_source is None:
        raise ValueError(
            f"Enhanced fixed-width {record_name} field '{field_name}' in contract "
            f"'{contract.name}' requires value_source."
        )
    value_source = str(value_source)
    field_type = str(field.get("type") or "string")
    normalized_source = value_source.lower()
    if normalized_source.startswith("literal:"):
        return _java_code_string_literal(value_source.split(":", 1)[1]), False
    if normalized_source in {"system_date", "current_date"}:
        return "LocalDate.now()", False
    if normalized_source in {"system_datetime", "current_datetime"}:
        return "LocalDateTime.now()", False
    if normalized_source in {"batch_run_id", "run_id"}:
        return "runId", False
    if normalized_source in {"data_record_count", "record_count"}:
        if record_name != "trailer":
            raise ValueError(
                f"Enhanced fixed-width value_source '{value_source}' is supported "
                "only on trailer fields."
            )
        return "recordCount", True
    sum_source = _parse_enhanced_sum_value_source(value_source)
    if sum_source is not None:
        source_entity, source_field = sum_source
        if record_name != "trailer":
            raise ValueError(
                f"Enhanced fixed-width value_source '{value_source}' is supported "
                "only on trailer fields."
            )
        if source_entity != entity.name:
            raise ValueError(
                f"Enhanced fixed-width sum source '{value_source}' must reference "
                f"entity '{entity.name}'."
            )
        if total_source_field_name != source_field:
            raise ValueError(
                f"Enhanced fixed-width trailer field '{field_name}' references "
                f"'{value_source}', but generated writer is configured for "
                f"'{entity.name}.{total_source_field_name}'."
            )
        source_canonical_field = entity_fields.get(source_field)
        if source_canonical_field is None:
            raise ValueError(
                f"Enhanced fixed-width sum source '{value_source}' references "
                "an unknown canonical field."
            )
        if source_canonical_field.type not in _NUMERIC_FIELD_TYPES:
            raise ValueError(
                f"Enhanced fixed-width sum source '{value_source}' requires a "
                f"numeric canonical field, got '{source_canonical_field.type.value}'."
            )
        if _is_minor_unit_trailer_coercion(field):
            if source_canonical_field.type != CanonicalFieldType.DECIMAL:
                raise ValueError(
                    f"Enhanced fixed-width type_coercion '{_MINOR_UNIT_TYPE_COERCION}' "
                    f"requires DECIMAL source field '{value_source}'."
                )
            return "minorUnitString(totalValue)", True
        if field.get("type_coercion") is not None:
            raise ValueError(
                f"Enhanced fixed-width type_coercion '{field.get('type_coercion')}' "
                f"is unsupported for control field '{field_name}'."
            )
        return "totalValue", _is_numeric_layout_type(field_type)
    raise ValueError(
        f"Enhanced fixed-width {record_name} field '{field_name}' in contract "
        f"'{contract.name}' declares unsupported value_source '{value_source}'."
    )


def _enhanced_fixed_width_sum_source_field(
    *,
    contract: ContractMetadata,
    trailer_record: dict | None,
    entity: CanonicalEntity,
    entity_fields: dict[str, CanonicalField],
) -> str | None:
    if trailer_record is None:
        return None
    sum_sources: list[tuple[str, str]] = []
    for field in trailer_record.get("fields") or []:
        value_source = field.get("value_source")
        parsed = _parse_enhanced_sum_value_source(str(value_source)) if value_source is not None else None
        if parsed is not None:
            sum_sources.append(parsed)
    if not sum_sources:
        return None
    if len(set(sum_sources)) > 1:
        raise ValueError(
            f"Enhanced fixed-width writer for contract '{contract.name}' supports "
            "one trailer sum source in this slice."
        )
    source_entity, source_field = sum_sources[0]
    if source_entity != entity.name:
        raise ValueError(
            f"Enhanced fixed-width sum source must reference entity '{entity.name}', "
            f"got '{source_entity}'."
        )
    canonical_field = entity_fields.get(source_field)
    if canonical_field is None:
        raise ValueError(
            f"Enhanced fixed-width sum source references unknown field "
            f"'{source_entity}.{source_field}'."
        )
    if canonical_field.type not in _NUMERIC_FIELD_TYPES:
        raise ValueError(
            f"Enhanced fixed-width sum source '{source_entity}.{source_field}' "
            f"requires a numeric field, got '{canonical_field.type.value}'."
        )
    return source_field


def _parse_enhanced_sum_value_source(value_source: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"sum\(([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\)", value_source)
    if match is None:
        return None
    return match.group(1), match.group(2)


def _layout_declares_value_source(layout: dict) -> bool:
    for field in layout.get("fields") or []:
        if isinstance(field, dict) and field.get("value_source") is not None:
            return True
    for record_type in layout.get("record_types") or []:
        if not isinstance(record_type, dict):
            continue
        for field in record_type.get("fields") or []:
            if isinstance(field, dict) and field.get("value_source") is not None:
                return True
    return False


def _file_trailer_record(layout: dict) -> dict | None:
    for record_type in layout.get("record_types") or []:
        if isinstance(record_type, dict) and str(record_type.get("name") or "") == "trailer":
            return record_type
    return None


def _csv_layout_uses_indicator_record_routing(layout: dict) -> bool:
    record_types = [
        record_type
        for record_type in layout.get("record_types") or []
        if isinstance(record_type, dict)
    ]
    if not record_types:
        return False
    indicator_record_types = [
        record_type
        for record_type in record_types
        if isinstance(record_type.get("indicator"), dict)
        and record_type["indicator"].get("column") is not None
    ]
    return bool(indicator_record_types) and len(indicator_record_types) == len(record_types)


def _is_minor_unit_trailer_coercion(field: dict) -> bool:
    return str(field.get("type_coercion") or "") in {_MINOR_UNIT_TYPE_COERCION, "minor_units"}


def _inbound_trailer_validation_specs(
    contract: ContractMetadata,
) -> list[dict[str, object]]:
    if contract.type not in {"file-fixed-width", "file-csv"}:
        return []
    trailer_record = _file_trailer_record(contract.file_layout or {})
    if trailer_record is None:
        return []
    specs: list[dict[str, object]] = []
    for field in trailer_record.get("fields") or []:
        if not isinstance(field, dict):
            continue
        value_source = field.get("value_source")
        if value_source is None:
            continue
        value_source_text = str(value_source)
        normalized_source = value_source_text.lower()
        if normalized_source in _INBOUND_TRAILER_COUNT_VALUE_SOURCES:
            specs.append({"kind": "record_count", "field": field})
            continue
        sum_source = _parse_enhanced_sum_value_source(value_source_text)
        if sum_source is not None:
            source_entity, source_field = sum_source
            specs.append(
                {
                    "kind": "sum",
                    "field": field,
                    "source_entity": source_entity,
                    "source_field": source_field,
                }
            )
            continue
        raise ValueError(
            f"Inbound {contract.type} trailer field '{field.get('name') or '<unknown>'}' "
            f"on contract '{contract.name}' declares unsupported value_source "
            f"'{value_source_text}'. {_INBOUND_TRAILER_UNSUPPORTED_MESSAGE}"
        )
    return specs


def _validate_inbound_file_trailer_value_sources(
    *,
    contract: ContractMetadata,
    entity: CanonicalEntity,
    mappings: list[FieldMapping],
) -> None:
    layout = contract.file_layout or {}
    if contract.type == "file-csv":
        if _layout_declares_value_source(layout) and not _csv_layout_uses_indicator_record_routing(layout):
            raise ValueError(
                "CSV inbound trailer validation supports indicator-column routing "
                "only in this slice."
            )
    elif contract.type != "file-fixed-width":
        return

    entity_fields = {field.name: field for field in entity.fields}
    mapped_canonical_fields = {canonical_field_name(mapping) for mapping in mappings}
    family_label = "CSV" if contract.type == "file-csv" else "fixed-width"

    def validate_field(record_name: str, field: dict) -> None:
        value_source = field.get("value_source")
        if value_source is None:
            return
        value_source_text = str(value_source)
        field_name = str(field.get("name") or "<unknown>")
        if record_name != "trailer":
            raise ValueError(
                f"Inbound {family_label} field '{field_name}' in record type "
                f"'{record_name}' on contract '{contract.name}' declares "
                f"value_source '{value_source_text}', but "
                f"{_INBOUND_TRAILER_UNSUPPORTED_MESSAGE}"
            )

        normalized_source = value_source_text.lower()
        if normalized_source in _INBOUND_TRAILER_COUNT_VALUE_SOURCES:
            if field.get("type_coercion") is not None:
                raise ValueError(
                    f"Inbound {family_label} trailer field '{field_name}' on contract "
                    f"'{contract.name}' declares unsupported type_coercion "
                    f"'{field.get('type_coercion')}' for record-count validation."
                )
            return

        sum_source = _parse_enhanced_sum_value_source(value_source_text)
        if sum_source is None:
            raise ValueError(
                f"Inbound {family_label} trailer field '{field_name}' on contract "
                f"'{contract.name}' declares unsupported value_source "
                f"'{value_source_text}'. {_INBOUND_TRAILER_UNSUPPORTED_MESSAGE}"
            )

        source_entity, source_field = sum_source
        if source_entity != entity.name:
            raise ValueError(
                f"Inbound {family_label} trailer sum source '{value_source_text}' on "
                f"contract '{contract.name}' must reference entity '{entity.name}'."
            )
        canonical_field = entity_fields.get(source_field)
        if canonical_field is None:
            raise ValueError(
                f"Inbound {family_label} trailer sum source '{value_source_text}' on "
                f"contract '{contract.name}' references unknown canonical field "
                f"'{source_entity}.{source_field}'."
            )
        if source_field not in mapped_canonical_fields:
            raise ValueError(
                f"Inbound {family_label} trailer sum source '{value_source_text}' on "
                f"contract '{contract.name}' must reference a canonical field mapped "
                f"from the file into entity '{entity.name}'."
            )
        if canonical_field.type not in _NUMERIC_FIELD_TYPES:
            raise ValueError(
                f"Inbound {family_label} trailer sum source '{value_source_text}' on "
                f"contract '{contract.name}' requires a numeric canonical field, "
                f"got '{canonical_field.type.value}'."
            )
        if _is_minor_unit_trailer_coercion(field):
            if canonical_field.type != CanonicalFieldType.DECIMAL:
                raise ValueError(
                    f"Inbound {family_label} trailer type_coercion "
                    f"'{field.get('type_coercion')}' requires DECIMAL sum source "
                    f"'{value_source_text}'."
                )
            return
        if field.get("type_coercion") is not None:
            raise ValueError(
                f"Inbound {family_label} trailer field '{field_name}' on contract "
                f"'{contract.name}' declares unsupported type_coercion "
                f"'{field.get('type_coercion')}'."
            )

    record_types = [
        record_type
        for record_type in layout.get("record_types") or []
        if isinstance(record_type, dict)
    ]
    if record_types:
        for record_type in record_types:
            record_name = str(record_type.get("name") or "data")
            for field in record_type.get("fields") or []:
                if isinstance(field, dict):
                    validate_field(record_name, field)
        return

    for field in layout.get("fields") or []:
        if isinstance(field, dict):
            validate_field("data", field)


def _is_filler_field(field_name: str) -> bool:
    normalized = field_name.lower()
    return normalized.startswith("filler") or normalized.startswith("padding")


def _is_numeric_layout_type(layout_type: str) -> bool:
    return layout_type.lower() in {
        "integer",
        "int",
        "long",
        "decimal",
        "number",
        "bigdecimal",
    }


def _csv_layout_type_compatible(layout_type: str, source_type: CanonicalFieldType) -> bool:
    normalized_type = layout_type.lower()
    if normalized_type in {"string", "char", "text"}:
        return True
    if normalized_type in {"integer", "int", "long"}:
        return source_type == CanonicalFieldType.INTEGER
    if normalized_type in {"decimal", "number", "bigdecimal"}:
        return source_type in {CanonicalFieldType.DECIMAL, CanonicalFieldType.INTEGER}
    if normalized_type in {"date", "localdate"}:
        return source_type == CanonicalFieldType.DATE
    if normalized_type in {"datetime", "date-time", "timestamp", "localdatetime"}:
        return source_type == CanonicalFieldType.DATETIME
    if normalized_type in {"boolean", "bool"}:
        return source_type == CanonicalFieldType.BOOLEAN
    return False


def _csv_minor_unit_layout_type_compatible(layout_type: str) -> bool:
    return layout_type.lower() in {
        "string",
        "char",
        "text",
        "integer",
        "int",
        "long",
        "decimal",
        "number",
        "bigdecimal",
    }


def _render_fixed_width_inbound_parser(
    *,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    layout = contract.file_layout or {}
    _validate_fixed_width_parser_layout(contract_name=contract.name, layout=layout)
    record_types = list(layout.get("record_types") or [])
    parser_class_name = _fixed_width_parser_class_name(contract.name)
    encoding = str(layout.get("encoding") or "UTF-8")
    body = [
        "@Component",
        f"public class {parser_class_name} {{",
        f"    private static final Charset FILE_CHARSET = Charset.forName({_java_code_string_literal(encoding)});",
        "",
        "    public List<ParsedRecord> parse(Path inputPath) throws IOException {",
        "        List<String> lines = Files.readAllLines(inputPath, FILE_CHARSET);",
        "        List<ParsedRecord> records = new ArrayList<>();",
        "        for (int index = 0; index < lines.size(); index++) {",
        "            records.add(parseLine(inputPath.toString(), index + 1, lines.get(index)));",
        "        }",
        "        return records;",
        "    }",
        "",
        "    public ParsedRecord parseLine(String fileName, int lineNumber, String line) {",
        "        String recordType = detectRecordType(fileName, lineNumber, line);",
        "        return switch (recordType) {",
    ]
    for record_type in record_types:
        record_name = str(record_type["name"])
        method_suffix = to_pascal_case(record_name)
        body.append(
            f"            case {_java_code_string_literal(record_name)} -> parse{method_suffix}(fileName, lineNumber, line);"
        )
    body.extend(
        [
            "            default -> throw parseError(fileName, lineNumber, recordType, null, "
            + _java_code_string_literal("unsupported record type")
            + ");",
            "        };",
            "    }",
            "",
            "    private String detectRecordType(String fileName, int lineNumber, String line) {",
        ]
    )
    indicator_record_types = [
        record_type
        for record_type in record_types
        if isinstance(record_type.get("indicator"), dict)
    ]
    if indicator_record_types:
        first_indicator = indicator_record_types[0]["indicator"]
        first_position = int(first_indicator["position"])
        first_length = int(first_indicator["length"])
        first_end = first_position + first_length - 1
        body.extend(
            [
                f"        if (line.length() < {first_end}) {{",
                "            throw parseError(fileName, lineNumber, null, null, "
                + _java_code_string_literal("line too short for record indicator")
                + ");",
                "        }",
            ]
        )
        for record_type in indicator_record_types:
            indicator = record_type["indicator"]
            position = int(indicator["position"])
            length = int(indicator["length"])
            value = str(indicator["value"])
            record_name = str(record_type["name"])
            body.extend(
                [
                    f"        if (line.length() >= {position + length - 1} "
                    f"&& slice(line, {position}, {length}).equals({_java_code_string_literal(value)})) {{",
                    f"            return {_java_code_string_literal(record_name)};",
                    "        }",
                ]
            )
        body.extend(
            [
                f"        String observedIndicator = slice(line, {first_position}, {first_length});",
                "        throw parseError(fileName, lineNumber, null, null, "
                + _java_code_string_literal("unknown record indicator: ")
                + " + observedIndicator);",
            ]
        )
    else:
        body.append('        return "data";')
    body.extend(["    }", ""])

    for record_type in record_types:
        record_name = str(record_type["name"])
        method_suffix = to_pascal_case(record_name)
        expected_length = int(record_type["expected_length"])
        body.extend(
            [
                f"    private ParsedRecord parse{method_suffix}(String fileName, int lineNumber, String line) {{",
                f"        requireLineLength(fileName, lineNumber, {_java_code_string_literal(record_name)}, line, {expected_length});",
                "        Map<String, Object> fields = new LinkedHashMap<>();",
            ]
        )
        for field in record_type.get("fields") or []:
            field_name = str(field["name"])
            position = int(field["position"])
            length = int(field["length"])
            required = "true" if bool(field.get("required")) else "false"
            field_type = str(field.get("type") or "string").lower()
            field_format = field.get("format")
            body.append(
                "        fields.put("
                + _java_code_string_literal(field_name)
                + ", parseField(fileName, lineNumber, "
                + _java_code_string_literal(record_name)
                + ", "
                + _java_code_string_literal(field_name)
                + f", slice(line, {position}, {length}), {required}, "
                + _java_code_string_literal(field_type)
                + ", "
                + ("null" if field_format is None else _java_code_string_literal(str(field_format)))
                + "));"
            )
        body.extend(
            [
                f"        return new ParsedRecord({_java_code_string_literal(record_name)}, fields);",
                "    }",
                "",
            ]
        )

    body.extend(
        [
            "    private void requireLineLength(String fileName, int lineNumber, String recordType, String line, int expectedLength) {",
            "        if (line.length() != expectedLength) {",
            "            throw parseError(fileName, lineNumber, recordType, null, "
            + _java_code_string_literal("expected line length ")
            + " + expectedLength + "
            + _java_code_string_literal(", got ")
            + " + line.length());",
            "        }",
            "    }",
            "",
            "    private Object parseField(String fileName, int lineNumber, String recordType, String fieldName, String rawValue, boolean required, String type, String format) {",
            "        String value = rawValue.trim();",
            "        if (required && value.isEmpty()) {",
            "            throw parseError(fileName, lineNumber, recordType, fieldName, "
            + _java_code_string_literal("required field is blank")
            + ");",
            "        }",
            "        if (value.isEmpty()) {",
            "            return null;",
            "        }",
            "        try {",
            "            return switch (type) {",
            '                case "integer", "int", "long" -> Long.valueOf(value);',
            '                case "decimal", "number", "bigdecimal" -> new BigDecimal(value);',
            '                case "date", "localdate" -> LocalDate.parse(value, DateTimeFormatter.ofPattern(format == null ? "yyyy-MM-dd" : format));',
            '                case "datetime", "date-time", "timestamp", "localdatetime" -> LocalDateTime.parse(value, DateTimeFormatter.ofPattern(format == null ? "yyyy-MM-dd\'T\'HH:mm:ss" : format));',
            "                default -> value;",
            "            };",
            "        } catch (RuntimeException ex) {",
            "            throw parseError(fileName, lineNumber, recordType, fieldName, "
            + _java_code_string_literal("invalid ")
            + " + type + "
            + _java_code_string_literal(" value: ")
            + " + value, ex);",
            "        }",
            "    }",
            "",
            "    private String slice(String line, int position, int length) {",
            "        int start = position - 1;",
            "        return line.substring(start, start + length);",
            "    }",
            "",
            "    private IllegalArgumentException parseError(String fileName, int lineNumber, String recordType, String fieldName, String message) {",
            "        return parseError(fileName, lineNumber, recordType, fieldName, message, null);",
            "    }",
            "",
            "    private IllegalArgumentException parseError(String fileName, int lineNumber, String recordType, String fieldName, String message, Throwable cause) {",
            "        StringBuilder builder = new StringBuilder();",
            "        builder.append("
            + _java_code_string_literal(f"Fixed-width parse error for interface '{contract.name}'")
            + ");",
            "        builder.append("
            + _java_code_string_literal(" in ")
            + ").append(fileName);",
            "        builder.append("
            + _java_code_string_literal(" at line ")
            + ").append(lineNumber);",
            "        if (recordType != null) {",
            "            builder.append("
            + _java_code_string_literal(", record type ")
            + ").append(recordType);",
            "        }",
            "        if (fieldName != null) {",
            "            builder.append("
            + _java_code_string_literal(", field ")
            + ").append(fieldName);",
            "        }",
            "        builder.append("
            + _java_code_string_literal(": ")
            + ").append(message);",
            "        return cause == null ? new IllegalArgumentException(builder.toString()) : new IllegalArgumentException(builder.toString(), cause);",
            "    }",
            "",
            "    public record ParsedRecord(String recordType, Map<String, Object> fields) {",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.adapter.inbound",
        imports=[
            "java.io.IOException",
            "java.math.BigDecimal",
            "java.nio.charset.Charset",
            "java.nio.file.Files",
            "java.nio.file.Path",
            "java.time.LocalDate",
            "java.time.LocalDateTime",
            "java.time.format.DateTimeFormatter",
            "java.util.ArrayList",
            "java.util.LinkedHashMap",
            "java.util.List",
            "java.util.Map",
            "org.springframework.stereotype.Component",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _validate_fixed_width_parser_layout(*, contract_name: str, layout: dict) -> None:
    if not layout:
        raise ValueError(f"Missing fixed-width layout metadata for upstream interface '{contract_name}'.")
    for record_type in layout.get("record_types") or []:
        for field in record_type.get("fields") or []:
            field_type = str(field.get("type") or "string").lower()
            if field_type in {"boolean", "bool"}:
                raise ValueError(
                    "Fixed-width inbound parser generation requires explicit boolean "
                    f"representations before field '{field.get('name')}' on interface "
                    f"'{contract_name}' can be parsed."
                )


def _render_csv_inbound_parser(
    *,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    layout = contract.file_layout or {}
    _validate_csv_parser_layout(contract_name=contract.name, layout=layout)
    if _csv_layout_uses_indicator_record_routing(layout):
        return _render_csv_indicator_routed_inbound_parser(
            contract=contract,
            root_package=root_package,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    fields = sorted(
        list(layout.get("fields") or []),
        key=lambda field: int(field["column"]),
    )
    parser_class_name = _csv_parser_class_name(contract.name)
    expected_columns = max(int(field["column"]) for field in fields)
    delimiter = str(layout.get("delimiter") or ",")
    quote_char = layout.get("quote_char")
    escape_char = layout.get("escape_char")
    has_header_row = bool(layout.get("has_header_row"))
    encoding = str(layout.get("encoding") or "UTF-8")
    line_separator = str(layout.get("line_separator") or "\n")
    body = [
        "@Component",
        f"public class {parser_class_name} {{",
        f"    private static final String DELIMITER = {_java_code_string_literal(delimiter)};",
        "    private static final String QUOTE_CHAR = "
        + ("null" if quote_char is None else _java_code_string_literal(str(quote_char)))
        + ";",
        "    private static final String ESCAPE_CHAR = "
        + ("null" if escape_char is None else _java_code_string_literal(str(escape_char)))
        + ";",
        f"    private static final String LINE_SEPARATOR = {_java_code_string_literal(line_separator)};",
        f"    private static final boolean HAS_HEADER_ROW = {'true' if has_header_row else 'false'};",
        f"    private static final int EXPECTED_COLUMNS = {expected_columns};",
        f"    private static final Charset FILE_CHARSET = Charset.forName({_java_code_string_literal(encoding)});",
        "",
        "    public List<ParsedRecord> parse(Path inputPath) throws IOException {",
        "        List<String> lines = readConfiguredLines(inputPath);",
        "        if (lines.isEmpty()) {",
        "            throw parseError(inputPath.toString(), 1, null, "
        + _java_code_string_literal("CSV file is empty")
        + ");",
        "        }",
        "        List<ParsedRecord> records = new ArrayList<>();",
        "        int startIndex = 0;",
        "        if (HAS_HEADER_ROW) {",
        "            validateHeader(inputPath.toString(), parseCsvLine(inputPath.toString(), 1, lines.get(0)));",
        "            startIndex = 1;",
        "        }",
        "        for (int index = startIndex; index < lines.size(); index++) {",
        "            records.add(parseLine(inputPath.toString(), index + 1, lines.get(index)));",
        "        }",
        "        return records;",
        "    }",
        "",
        "    public ParsedRecord parseLine(String fileName, int lineNumber, String line) {",
        "        List<String> columns = parseCsvLine(fileName, lineNumber, line);",
        "        requireColumnCount(fileName, lineNumber, columns);",
        "        Map<String, Object> fields = new LinkedHashMap<>();",
    ]
    for field in fields:
        field_name = str(field["name"])
        column = int(field["column"])
        required = "true" if bool(field.get("required")) else "false"
        field_type = str(field.get("type") or "string").lower()
        field_format = field.get("format")
        body.append(
            "        fields.put("
            + _java_code_string_literal(field_name)
            + ", parseField(fileName, lineNumber, "
            + _java_code_string_literal(field_name)
            + f", columns.get({column - 1}), {required}, "
            + _java_code_string_literal(field_type)
            + ", "
            + ("null" if field_format is None else _java_code_string_literal(str(field_format)))
            + "));"
        )
    body.extend(
        [
            '        return new ParsedRecord("data", fields);',
            "    }",
            "",
            "    private void validateHeader(String fileName, List<String> header) {",
            "        requireColumnCount(fileName, 1, header);",
        ]
    )
    for field in fields:
        field_name = str(field["name"])
        column = int(field["column"])
        body.extend(
            [
                f"        if (!header.get({column - 1}).trim().equals({_java_code_string_literal(field_name)})) {{",
                "            throw parseError(fileName, 1, "
                + _java_code_string_literal(field_name)
                + ", "
                + _java_code_string_literal("expected header ")
                + " + "
                + _java_code_string_literal(field_name)
                + " + "
                + _java_code_string_literal(", got ")
                + f" + header.get({column - 1}));",
                "        }",
            ]
        )
    body.extend(
        [
            "    }",
            "",
            "    private List<String> readConfiguredLines(Path inputPath) throws IOException {",
            "        String content = Files.readString(inputPath, FILE_CHARSET);",
            "        List<String> lines = new ArrayList<>();",
            "        if (content.isEmpty()) {",
            "            return lines;",
            "        }",
            "        int start = 0;",
            "        int next = content.indexOf(LINE_SEPARATOR, start);",
            "        while (next >= 0) {",
            "            lines.add(content.substring(start, next));",
            "            start = next + LINE_SEPARATOR.length();",
            "            next = content.indexOf(LINE_SEPARATOR, start);",
            "        }",
            "        if (start < content.length()) {",
            "            lines.add(content.substring(start));",
            "        }",
            "        return lines;",
            "    }",
            "",
            "    private List<String> parseCsvLine(String fileName, int lineNumber, String line) {",
            "        List<String> columns = new ArrayList<>();",
            "        StringBuilder current = new StringBuilder();",
            "        boolean inQuotes = false;",
            "        for (int index = 0; index < line.length(); index++) {",
            "            String value = String.valueOf(line.charAt(index));",
            "            if (inQuotes && ESCAPE_CHAR != null && value.equals(ESCAPE_CHAR)) {",
            "                if (index + 1 >= line.length()) {",
            "                    throw parseError(fileName, lineNumber, null, "
            + _java_code_string_literal("escape character at end of line")
            + ");",
            "                }",
            "                current.append(line.charAt(index + 1));",
            "                index++;",
            "                continue;",
            "            }",
            "            if (QUOTE_CHAR != null && value.equals(QUOTE_CHAR)) {",
            "                inQuotes = !inQuotes;",
            "                continue;",
            "            }",
            "            if (!inQuotes && value.equals(DELIMITER)) {",
            "                columns.add(current.toString());",
            "                current.setLength(0);",
            "                continue;",
            "            }",
            "            current.append(value);",
            "        }",
            "        if (inQuotes) {",
            "            throw parseError(fileName, lineNumber, null, "
            + _java_code_string_literal("unterminated quoted field")
            + ");",
            "        }",
            "        columns.add(current.toString());",
            "        return columns;",
            "    }",
            "",
            "    private void requireColumnCount(String fileName, int lineNumber, List<String> columns) {",
            "        if (columns.size() != EXPECTED_COLUMNS) {",
            "            throw parseError(fileName, lineNumber, null, "
            + _java_code_string_literal("expected ")
            + " + EXPECTED_COLUMNS + "
            + _java_code_string_literal(" columns, got ")
            + " + columns.size());",
            "        }",
            "    }",
            "",
            "    private Object parseField(String fileName, int lineNumber, String fieldName, String rawValue, boolean required, String type, String format) {",
            "        String trimmedValue = rawValue.trim();",
            "        if (required && trimmedValue.isEmpty()) {",
            "            throw parseError(fileName, lineNumber, fieldName, "
            + _java_code_string_literal("required field is blank")
            + ");",
            "        }",
            "        if (trimmedValue.isEmpty()) {",
            "            return null;",
            "        }",
            "        try {",
            "            return switch (type) {",
            '                case "integer", "int", "long" -> Long.valueOf(trimmedValue);',
            '                case "decimal", "number", "bigdecimal" -> new BigDecimal(trimmedValue);',
            '                case "boolean", "bool" -> parseBoolean(fileName, lineNumber, fieldName, trimmedValue);',
            '                case "date", "localdate" -> LocalDate.parse(trimmedValue, DateTimeFormatter.ofPattern(format == null ? "yyyy-MM-dd" : format));',
            '                case "datetime", "date-time", "timestamp", "localdatetime" -> LocalDateTime.parse(trimmedValue, DateTimeFormatter.ofPattern(format == null ? "yyyy-MM-dd\'T\'HH:mm:ss" : format));',
            '                case "string", "char", "text" -> rawValue;',
            "                default -> rawValue;",
            "            };",
            "        } catch (RuntimeException ex) {",
            "            throw parseError(fileName, lineNumber, fieldName, "
            + _java_code_string_literal("invalid ")
            + " + type + "
            + _java_code_string_literal(" value: ")
            + " + trimmedValue, ex);",
            "        }",
            "    }",
            "",
            "    private Boolean parseBoolean(String fileName, int lineNumber, String fieldName, String value) {",
            "        if (value.equalsIgnoreCase(\"true\")) {",
            "            return Boolean.TRUE;",
            "        }",
            "        if (value.equalsIgnoreCase(\"false\")) {",
            "            return Boolean.FALSE;",
            "        }",
            "        throw parseError(fileName, lineNumber, fieldName, "
            + _java_code_string_literal("invalid boolean value: ")
            + " + value);",
            "    }",
            "",
            "    private IllegalArgumentException parseError(String fileName, int lineNumber, String fieldName, String message) {",
            "        return parseError(fileName, lineNumber, fieldName, message, null);",
            "    }",
            "",
            "    private IllegalArgumentException parseError(String fileName, int lineNumber, String fieldName, String message, Throwable cause) {",
            "        StringBuilder builder = new StringBuilder();",
            "        builder.append("
            + _java_code_string_literal(f"CSV parse error for interface '{contract.name}'")
            + ");",
            "        builder.append("
            + _java_code_string_literal(" in ")
            + ").append(fileName);",
            "        builder.append("
            + _java_code_string_literal(" at line ")
            + ").append(lineNumber);",
            "        if (fieldName != null) {",
            "            builder.append("
            + _java_code_string_literal(", field ")
            + ").append(fieldName);",
            "        }",
            "        builder.append("
            + _java_code_string_literal(": ")
            + ").append(message);",
            "        return cause == null ? new IllegalArgumentException(builder.toString()) : new IllegalArgumentException(builder.toString(), cause);",
            "    }",
            "",
            "    public record ParsedRecord(String recordType, Map<String, Object> fields) {",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.adapter.inbound",
        imports=[
            "java.io.IOException",
            "java.math.BigDecimal",
            "java.nio.charset.Charset",
            "java.nio.file.Files",
            "java.nio.file.Path",
            "java.time.LocalDate",
            "java.time.LocalDateTime",
            "java.time.format.DateTimeFormatter",
            "java.util.ArrayList",
            "java.util.LinkedHashMap",
            "java.util.List",
            "java.util.Map",
            "org.springframework.stereotype.Component",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_csv_indicator_routed_inbound_parser(
    *,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    layout = contract.file_layout or {}
    record_types = [
        record_type
        for record_type in layout.get("record_types") or []
        if isinstance(record_type, dict)
    ]
    parser_class_name = _csv_parser_class_name(contract.name)
    delimiter = str(layout.get("delimiter") or ",")
    quote_char = layout.get("quote_char")
    escape_char = layout.get("escape_char")
    encoding = str(layout.get("encoding") or "UTF-8")
    line_separator = str(layout.get("line_separator") or "\n")
    indicator_column = int(record_types[0]["indicator"]["column"])
    body = [
        "@Component",
        f"public class {parser_class_name} {{",
        f"    private static final String DELIMITER = {_java_code_string_literal(delimiter)};",
        "    private static final String QUOTE_CHAR = "
        + ("null" if quote_char is None else _java_code_string_literal(str(quote_char)))
        + ";",
        "    private static final String ESCAPE_CHAR = "
        + ("null" if escape_char is None else _java_code_string_literal(str(escape_char)))
        + ";",
        f"    private static final String LINE_SEPARATOR = {_java_code_string_literal(line_separator)};",
        f"    private static final int INDICATOR_COLUMN = {indicator_column};",
        f"    private static final Charset FILE_CHARSET = Charset.forName({_java_code_string_literal(encoding)});",
        "",
        "    public List<ParsedRecord> parse(Path inputPath) throws IOException {",
        "        List<String> lines = readConfiguredLines(inputPath);",
        "        if (lines.isEmpty()) {",
        "            throw parseError(inputPath.toString(), 1, null, null, "
        + _java_code_string_literal("CSV file is empty")
        + ");",
        "        }",
        "        List<ParsedRecord> records = new ArrayList<>();",
        "        for (int index = 0; index < lines.size(); index++) {",
        "            records.add(parseLine(inputPath.toString(), index + 1, lines.get(index)));",
        "        }",
        "        return records;",
        "    }",
        "",
        "    public ParsedRecord parseLine(String fileName, int lineNumber, String line) {",
        "        List<String> columns = parseCsvLine(fileName, lineNumber, line);",
        "        String recordType = detectRecordType(fileName, lineNumber, columns);",
        "        return switch (recordType) {",
    ]
    for record_type in record_types:
        record_name = str(record_type["name"])
        method_suffix = to_pascal_case(record_name)
        body.append(
            f"            case {_java_code_string_literal(record_name)} -> parse{method_suffix}(fileName, lineNumber, columns);"
        )
    body.extend(
        [
            "            default -> throw parseError(fileName, lineNumber, recordType, null, "
            + _java_code_string_literal("unsupported record type")
            + ");",
            "        };",
            "    }",
            "",
            "    private String detectRecordType(String fileName, int lineNumber, List<String> columns) {",
            "        if (columns.size() < INDICATOR_COLUMN) {",
            "            throw parseError(fileName, lineNumber, null, null, "
            + _java_code_string_literal("line too short for record indicator column")
            + ");",
            "        }",
            "        String observedIndicator = columns.get(INDICATOR_COLUMN - 1).trim();",
            "        return switch (observedIndicator) {",
        ]
    )
    for record_type in record_types:
        indicator = record_type["indicator"]
        body.append(
            "            case "
            + _java_code_string_literal(str(indicator["value"]))
            + " -> "
            + _java_code_string_literal(str(record_type["name"]))
            + ";"
        )
    body.extend(
        [
            "            default -> throw parseError(fileName, lineNumber, null, null, "
            + _java_code_string_literal("unknown record indicator: ")
            + " + observedIndicator);",
            "        };",
            "    }",
            "",
        ]
    )

    for record_type in record_types:
        record_name = str(record_type["name"])
        method_suffix = to_pascal_case(record_name)
        expected_columns = int(record_type.get("expected_length") or 0)
        fields = sorted(
            list(record_type.get("fields") or []),
            key=lambda field: int(field["column"]),
        )
        body.extend(
            [
                f"    private ParsedRecord parse{method_suffix}(String fileName, int lineNumber, List<String> columns) {{",
                f"        requireColumnCount(fileName, lineNumber, {_java_code_string_literal(record_name)}, columns, {expected_columns});",
                "        Map<String, Object> fields = new LinkedHashMap<>();",
            ]
        )
        for field in fields:
            field_name = str(field["name"])
            column = int(field["column"])
            required = "true" if bool(field.get("required")) else "false"
            field_type = str(field.get("type") or "string").lower()
            field_format = field.get("format")
            body.append(
                "        fields.put("
                + _java_code_string_literal(field_name)
                + ", parseField(fileName, lineNumber, "
                + _java_code_string_literal(record_name)
                + ", "
                + _java_code_string_literal(field_name)
                + f", columns.get({column - 1}), {required}, "
                + _java_code_string_literal(field_type)
                + ", "
                + ("null" if field_format is None else _java_code_string_literal(str(field_format)))
                + "));"
            )
        body.extend(
            [
                f"        return new ParsedRecord({_java_code_string_literal(record_name)}, fields);",
                "    }",
                "",
            ]
        )

    body.extend(
        [
            "    private List<String> readConfiguredLines(Path inputPath) throws IOException {",
            "        String content = Files.readString(inputPath, FILE_CHARSET);",
            "        List<String> lines = new ArrayList<>();",
            "        if (content.isEmpty()) {",
            "            return lines;",
            "        }",
            "        int start = 0;",
            "        int next = content.indexOf(LINE_SEPARATOR, start);",
            "        while (next >= 0) {",
            "            lines.add(content.substring(start, next));",
            "            start = next + LINE_SEPARATOR.length();",
            "            next = content.indexOf(LINE_SEPARATOR, start);",
            "        }",
            "        if (start < content.length()) {",
            "            lines.add(content.substring(start));",
            "        }",
            "        return lines;",
            "    }",
            "",
            "    private List<String> parseCsvLine(String fileName, int lineNumber, String line) {",
            "        List<String> columns = new ArrayList<>();",
            "        StringBuilder current = new StringBuilder();",
            "        boolean inQuotes = false;",
            "        for (int index = 0; index < line.length(); index++) {",
            "            String value = String.valueOf(line.charAt(index));",
            "            if (inQuotes && ESCAPE_CHAR != null && value.equals(ESCAPE_CHAR)) {",
            "                if (index + 1 >= line.length()) {",
            "                    throw parseError(fileName, lineNumber, null, null, "
            + _java_code_string_literal("escape character at end of line")
            + ");",
            "                }",
            "                current.append(line.charAt(index + 1));",
            "                index++;",
            "                continue;",
            "            }",
            "            if (QUOTE_CHAR != null && value.equals(QUOTE_CHAR)) {",
            "                inQuotes = !inQuotes;",
            "                continue;",
            "            }",
            "            if (!inQuotes && value.equals(DELIMITER)) {",
            "                columns.add(current.toString());",
            "                current.setLength(0);",
            "                continue;",
            "            }",
            "            current.append(value);",
            "        }",
            "        if (inQuotes) {",
            "            throw parseError(fileName, lineNumber, null, null, "
            + _java_code_string_literal("unterminated quoted field")
            + ");",
            "        }",
            "        columns.add(current.toString());",
            "        return columns;",
            "    }",
            "",
            "    private void requireColumnCount(String fileName, int lineNumber, String recordType, List<String> columns, int expectedColumns) {",
            "        if (columns.size() != expectedColumns) {",
            "            throw parseError(fileName, lineNumber, recordType, null, "
            + _java_code_string_literal("expected ")
            + " + expectedColumns + "
            + _java_code_string_literal(" columns, got ")
            + " + columns.size());",
            "        }",
            "    }",
            "",
            "    private Object parseField(String fileName, int lineNumber, String recordType, String fieldName, String rawValue, boolean required, String type, String format) {",
            "        String trimmedValue = rawValue.trim();",
            "        if (required && trimmedValue.isEmpty()) {",
            "            throw parseError(fileName, lineNumber, recordType, fieldName, "
            + _java_code_string_literal("required field is blank")
            + ");",
            "        }",
            "        if (trimmedValue.isEmpty()) {",
            "            return null;",
            "        }",
            "        try {",
            "            return switch (type) {",
            '                case "integer", "int", "long" -> Long.valueOf(trimmedValue);',
            '                case "decimal", "number", "bigdecimal" -> new BigDecimal(trimmedValue);',
            '                case "boolean", "bool" -> parseBoolean(fileName, lineNumber, recordType, fieldName, trimmedValue);',
            '                case "date", "localdate" -> LocalDate.parse(trimmedValue, DateTimeFormatter.ofPattern(format == null ? "yyyy-MM-dd" : format));',
            '                case "datetime", "date-time", "timestamp", "localdatetime" -> LocalDateTime.parse(trimmedValue, DateTimeFormatter.ofPattern(format == null ? "yyyy-MM-dd\'T\'HH:mm:ss" : format));',
            '                case "string", "char", "text" -> rawValue;',
            "                default -> rawValue;",
            "            };",
            "        } catch (RuntimeException ex) {",
            "            throw parseError(fileName, lineNumber, recordType, fieldName, "
            + _java_code_string_literal("invalid ")
            + " + type + "
            + _java_code_string_literal(" value: ")
            + " + trimmedValue, ex);",
            "        }",
            "    }",
            "",
            "    private Boolean parseBoolean(String fileName, int lineNumber, String recordType, String fieldName, String value) {",
            "        if (value.equalsIgnoreCase(\"true\")) {",
            "            return Boolean.TRUE;",
            "        }",
            "        if (value.equalsIgnoreCase(\"false\")) {",
            "            return Boolean.FALSE;",
            "        }",
            "        throw parseError(fileName, lineNumber, recordType, fieldName, "
            + _java_code_string_literal("invalid boolean value: ")
            + " + value);",
            "    }",
            "",
            "    private IllegalArgumentException parseError(String fileName, int lineNumber, String recordType, String fieldName, String message) {",
            "        return parseError(fileName, lineNumber, recordType, fieldName, message, null);",
            "    }",
            "",
            "    private IllegalArgumentException parseError(String fileName, int lineNumber, String recordType, String fieldName, String message, Throwable cause) {",
            "        StringBuilder builder = new StringBuilder();",
            "        builder.append("
            + _java_code_string_literal(f"CSV parse error for interface '{contract.name}'")
            + ");",
            "        builder.append("
            + _java_code_string_literal(" in ")
            + ").append(fileName);",
            "        builder.append("
            + _java_code_string_literal(" at line ")
            + ").append(lineNumber);",
            "        if (recordType != null) {",
            "            builder.append("
            + _java_code_string_literal(", record type ")
            + ").append(recordType);",
            "        }",
            "        if (fieldName != null) {",
            "            builder.append("
            + _java_code_string_literal(", field ")
            + ").append(fieldName);",
            "        }",
            "        builder.append("
            + _java_code_string_literal(": ")
            + ").append(message);",
            "        return cause == null ? new IllegalArgumentException(builder.toString()) : new IllegalArgumentException(builder.toString(), cause);",
            "    }",
            "",
            "    public record ParsedRecord(String recordType, Map<String, Object> fields) {",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.adapter.inbound",
        imports=[
            "java.io.IOException",
            "java.math.BigDecimal",
            "java.nio.charset.Charset",
            "java.nio.file.Files",
            "java.nio.file.Path",
            "java.time.LocalDate",
            "java.time.LocalDateTime",
            "java.time.format.DateTimeFormatter",
            "java.util.ArrayList",
            "java.util.LinkedHashMap",
            "java.util.List",
            "java.util.Map",
            "org.springframework.stereotype.Component",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _validate_csv_parser_layout(*, contract_name: str, layout: dict) -> None:
    if not layout:
        raise ValueError(f"Missing CSV layout metadata for upstream interface '{contract_name}'.")
    if not layout.get("fields"):
        raise ValueError(f"Missing CSV data fields for upstream interface '{contract_name}'.")
    if _csv_layout_uses_indicator_record_routing(layout) and bool(layout.get("has_header_row")):
        raise ValueError(
            "CSV indicator-column record routing uses record_types.header for "
            f"control records; has_header_row is not supported on interface '{contract_name}'."
        )


def _render_xml_model(
    *,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    xml_contract = _require_xml_contract(contract)
    attributes, elements = _xml_field_descriptors(xml_contract)
    fields = [*attributes, *elements]
    enum_fields = [field for field in fields if field.get("enum_values")]
    imports = _xml_model_imports(fields)
    body = [
        f"public class {_xml_model_class_name(contract)} {{",
        "",
    ]
    for field in enum_fields:
        enum_name = _xml_enum_class_name(field)
        body.extend(
            [
                f"    public enum {enum_name} {{",
            ]
        )
        enum_values = list(field.get("enum_values") or [])
        for index, value in enumerate(enum_values):
            suffix = "," if index < len(enum_values) - 1 else ";"
            body.append(
                f"        {_xml_enum_constant(value)}({_java_code_string_literal(str(value))}){suffix}"
            )
        body.extend(
            [
                "",
                "        private final String wireValue;",
                "",
                f"        {enum_name}(String wireValue) {{",
                "            this.wireValue = wireValue;",
                "        }",
                "",
                "        public String wireValue() {",
                "            return wireValue;",
                "        }",
                "",
                f"        public static {enum_name} fromWireValue(String value) {{",
                f"            for ({enum_name} candidate : values()) {{",
                "                if (candidate.wireValue.equals(value)) {",
                "                    return candidate;",
                "                }",
                "            }",
                "            throw new IllegalArgumentException(\"Unsupported enum value.\");",
                "        }",
                "    }",
                "",
            ]
        )
    for field in fields:
        field_name = str(field["java_name"])
        java_type = _xml_java_type(field)
        if bool(field.get("repeated")):
            body.append(f"    private List<{java_type}> {field_name} = new ArrayList<>();")
        else:
            body.append(f"    private {java_type} {field_name};")
    body.append("")
    for field in fields:
        field_name = str(field["java_name"])
        method_suffix = to_pascal_case(field_name)
        java_type = _xml_java_type(field)
        if bool(field.get("repeated")):
            body.extend(
                [
                    f"    public List<{java_type}> get{method_suffix}() {{",
                    f"        return {field_name};",
                    "    }",
                    "",
                    f"    public void set{method_suffix}(List<{java_type}> {field_name}) {{",
                    f"        this.{field_name} = {field_name} == null ? new ArrayList<>() : {field_name};",
                    "    }",
                    "",
                ]
            )
        else:
            body.extend(
                [
                    f"    public {java_type} get{method_suffix}() {{",
                    f"        return {field_name};",
                    "    }",
                    "",
                    f"    public void set{method_suffix}({java_type} {field_name}) {{",
                    f"        this.{field_name} = {field_name};",
                    "    }",
                    "",
                ]
            )
    body.append("}")
    return _java_file(
        package_name=f"{root_package}.adapter.xml",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_xml_parser(
    *,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    xml_contract = _require_xml_contract(contract)
    model_class = _xml_model_class_name(contract)
    parser_class = _xml_parser_class_name(contract)
    attributes, fields = _xml_field_descriptors(xml_contract)
    namespace = xml_contract.get("namespace")
    root_element = str(xml_contract.get("root_element") or "")
    resource_path = _xml_xsd_resource_path(contract)
    body = [
        "@Component",
        f"public class {parser_class} {{",
        f"    private static final String ROOT_ELEMENT = {_java_code_string_literal(root_element)};",
        "    private static final String NAMESPACE = "
        + ("null" if namespace is None else _java_code_string_literal(str(namespace)))
        + ";",
        f"    private static final String XSD_RESOURCE = {_java_code_string_literal(resource_path)};",
        "",
        f"    public {model_class} parse(Path inputPath) throws Exception {{",
        "        try {",
        "            Document document = documentBuilder().parse(inputPath.toFile());",
        f"            {model_class} model = parseDocument(document);",
        "            validateXml(new StreamSource(inputPath.toFile()));",
        "            return model;",
        "        } catch (SAXException ex) {",
        "            throw malformedXml(ex);",
        "        }",
        "    }",
        "",
        f"    public {model_class} parse(String xml) throws Exception {{",
        "        try {",
        "            Document document = documentBuilder().parse(new InputSource(new StringReader(xml)));",
        f"            {model_class} model = parseDocument(document);",
        "            validateXml(new StreamSource(new StringReader(xml)));",
        "            return model;",
        "        } catch (SAXException ex) {",
        "            throw malformedXml(ex);",
        "        }",
        "    }",
        "",
        f"    private {model_class} parseDocument(Document document) {{",
        "        Element root = document.getDocumentElement();",
        "        validateRoot(root);",
        f"        {model_class} model = new {model_class}();",
    ]
    for field in attributes:
        xml_field_name = str(field["name"])
        java_field_name = str(field["java_name"])
        method_suffix = to_pascal_case(java_field_name)
        has_attribute_var = f"has{method_suffix}Attribute"
        value_var = f"{java_field_name}Value"
        xml_path = _xml_runtime_field_path(root_element, field)
        body.extend(
            [
                f"        boolean {has_attribute_var} = root.hasAttribute({_java_code_string_literal(xml_field_name)});",
                f"        if (!{has_attribute_var}) {{",
            ]
        )
        if bool(field.get("required")):
            body.append(
                f"            throw missingRequiredXmlField({_java_code_string_literal(xml_path)});"
            )
        else:
            body.append("            // Optional attribute is absent.")
        body.extend(
            [
                "        }",
                f"        if ({has_attribute_var}) {{",
                f"            String {value_var} = root.getAttribute({_java_code_string_literal(xml_field_name)});",
                f"            model.set{method_suffix}({_xml_parse_expression(field, value_var, xml_path)});",
                "        }",
            ]
        )
    for field in fields:
        xml_field_name = str(field["name"])
        java_field_name = str(field["java_name"])
        method_suffix = to_pascal_case(java_field_name)
        variable = f"{java_field_name}Elements"
        xml_path = _xml_runtime_field_path(root_element, field)
        body.append(
            f"        List<Element> {variable} = childElements(root, {_java_code_string_literal(xml_field_name)});"
        )
        if bool(field.get("required")):
            body.extend(
                [
                    f"        if ({variable}.isEmpty()) {{",
                    f"            throw missingRequiredXmlField({_java_code_string_literal(xml_path)});",
                    "        }",
                ]
            )
        max_occurs = field.get("max_occurs")
        if max_occurs is not None:
            body.extend(
                [
                    f"        if ({variable}.size() > {int(max_occurs)}) {{",
                    f"            throw parseError({_java_code_string_literal(xml_path)}, "
                    + _java_code_string_literal(f"expected at most {int(max_occurs)} element(s)")
                    + ");",
                    "        }",
                ]
            )
        if bool(field.get("repeated")):
            body.append(f"        for (Element element : {variable}) {{")
            body.extend(_xml_parse_element_value_lines(field, "element", "parsedValue", xml_path))
            body.extend(
                [
                    f"            model.get{method_suffix}().add(parsedValue);",
                    "        }",
                ]
            )
        else:
            body.extend(
                [
                    f"        if (!{variable}.isEmpty()) {{",
                    f"            Element element = {variable}.get(0);",
                    *_xml_parse_element_value_lines(field, "element", "parsedValue", xml_path),
                    f"            model.set{method_suffix}(parsedValue);",
                    "        }",
                ]
            )
    body.extend(
        [
            "        return model;",
            "    }",
            "",
            "    private void validateXml(StreamSource source) throws Exception {",
            "        Schema schema = loadSchema();",
            "        schema.newValidator().validate(source);",
            "    }",
            "",
            "    private Schema loadSchema() throws Exception {",
            "        URL resource = getClass().getResource(XSD_RESOURCE);",
            "        if (resource == null) {",
            "            throw new IllegalStateException(\"Missing XML/XSD resource: \" + XSD_RESOURCE);",
            "        }",
            "        SchemaFactory schemaFactory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, \"file,jar\");",
            "        return schemaFactory.newSchema(resource);",
            "    }",
            "",
            "    private DocumentBuilder documentBuilder() throws ParserConfigurationException {",
            "        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();",
            "        factory.setNamespaceAware(true);",
            "        factory.setFeature(\"http://apache.org/xml/features/disallow-doctype-decl\", true);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-general-entities\", false);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-parameter-entities\", false);",
            "        factory.setFeature(\"http://apache.org/xml/features/nonvalidating/load-external-dtd\", false);",
            "        factory.setXIncludeAware(false);",
            "        factory.setExpandEntityReferences(false);",
            "        return factory.newDocumentBuilder();",
            "    }",
            "",
            "    private void validateRoot(Element root) {",
            "        if (!ROOT_ELEMENT.equals(localName(root))) {",
            "            throw parseError(null, \"expected root element \" + ROOT_ELEMENT + \", got \" + localName(root));",
            "        }",
            "        if (NAMESPACE != null && !NAMESPACE.equals(root.getNamespaceURI())) {",
            "            throw parseError(null, \"expected namespace \" + NAMESPACE + \", got \" + root.getNamespaceURI());",
            "        }",
            "    }",
            "",
            "    private List<Element> childElements(Element parent, String childName) {",
            "        List<Element> children = new ArrayList<>();",
            "        NodeList nodes = parent.getChildNodes();",
            "        for (int index = 0; index < nodes.getLength(); index++) {",
            "            Node node = nodes.item(index);",
            "            if (node.getNodeType() != Node.ELEMENT_NODE) {",
            "                continue;",
            "            }",
            "            Element child = (Element) node;",
            "            if (childName.equals(localName(child)) && (NAMESPACE == null || NAMESPACE.equals(child.getNamespaceURI()))) {",
            "                children.add(child);",
            "            }",
            "        }",
            "        return children;",
            "    }",
            "",
            "    private boolean isNil(Element element) {",
            "        return \"true\".equals(element.getAttributeNS(XMLConstants.W3C_XML_SCHEMA_INSTANCE_NS_URI, \"nil\"));",
            "    }",
            "",
            "    private String localName(Element element) {",
            "        return element.getLocalName() == null ? element.getNodeName() : element.getLocalName();",
            "    }",
            "",
            *_xml_parse_helper_methods(),
            "",
            "    private IllegalArgumentException missingRequiredXmlField(String xmlPath) {",
            "        return parseError(xmlPath, \"required field is missing\");",
            "    }",
            "",
            "    private IllegalArgumentException malformedXml(SAXException ex) {",
            "        return new IllegalArgumentException(",
            "                "
            + _java_code_string_literal(f"Malformed XML for contract {contract.name}: ")
            + " + safeXmlMessage(ex),",
            "                ex);",
            "    }",
            "",
            "    private String safeXmlMessage(Exception ex) {",
            "        String message = ex.getMessage();",
            "        if (message == null || message.isBlank()) {",
            "            return \"XML parser rejected the document.\";",
            "        }",
            "        String sanitized = message.replace('\\r', ' ').replace('\\n', ' ').replace('\\t', ' ').trim();",
            "        sanitized = sanitized.replaceAll(\"file:/[^\\\\s]+\", \"[path]\");",
            "        sanitized = sanitized.replaceAll(\"([A-Za-z]:)?[/\\\\\\\\][^\\\\s]+\", \"[path]\");",
            "        if (sanitized.length() > 240) {",
            "            return sanitized.substring(0, 240) + \"...\";",
            "        }",
            "        return sanitized;",
            "    }",
            "",
            "    private IllegalArgumentException parseError(String xmlPath, String message) {",
            "        StringBuilder builder = new StringBuilder();",
            "        builder.append("
            + _java_code_string_literal(f"XML parse error for interface '{contract.name}'")
            + ");",
            "        if (xmlPath != null) {",
            "            builder.append("
            + _java_code_string_literal(" at ")
            + ").append(xmlPath);",
            "        }",
            "        builder.append("
            + _java_code_string_literal(": ")
            + ").append(message);",
            "        return new IllegalArgumentException(builder.toString());",
            "    }",
            "}",
        ]
    )
    body = [line.replace(_xml_model_class_name_placeholder(), model_class) for line in body]
    return _java_file(
        package_name=f"{root_package}.adapter.xml",
        imports=[
            f"{root_package}.adapter.xml.{model_class}",
            "java.math.BigDecimal",
            "java.net.URL",
            "java.nio.file.Path",
            "java.time.LocalDate",
            "java.time.OffsetDateTime",
            "java.util.ArrayList",
            "java.util.List",
            "javax.xml.XMLConstants",
            "javax.xml.parsers.DocumentBuilder",
            "javax.xml.parsers.DocumentBuilderFactory",
            "javax.xml.parsers.ParserConfigurationException",
            "javax.xml.transform.stream.StreamSource",
            "javax.xml.validation.Schema",
            "javax.xml.validation.SchemaFactory",
            "org.springframework.stereotype.Component",
            "org.w3c.dom.Document",
            "org.w3c.dom.Element",
            "org.w3c.dom.Node",
            "org.w3c.dom.NodeList",
            "org.xml.sax.InputSource",
            "org.xml.sax.SAXException",
            "java.io.StringReader",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_xml_serializer(
    *,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    xml_contract = _require_xml_contract(contract)
    model_class = _xml_model_class_name(contract)
    serializer_class = _xml_serializer_class_name(contract)
    attributes, fields = _xml_field_descriptors(xml_contract)
    namespace = xml_contract.get("namespace")
    namespace_alias = xml_contract.get("namespace_alias")
    root_element = str(xml_contract.get("root_element") or "")
    resource_path = _xml_xsd_resource_path(contract)
    body = [
        "@Component",
        f"public class {serializer_class} {{",
        f"    private static final String ROOT_ELEMENT = {_java_code_string_literal(root_element)};",
        "    private static final String NAMESPACE = "
        + ("null" if namespace is None else _java_code_string_literal(str(namespace)))
        + ";",
        "    private static final String NAMESPACE_ALIAS = "
        + ("null" if namespace_alias is None else _java_code_string_literal(str(namespace_alias)))
        + ";",
        f"    private static final String XSD_RESOURCE = {_java_code_string_literal(resource_path)};",
        "",
        f"    public String serialize({model_class} model) throws Exception {{",
        "        Document document = documentBuilder().newDocument();",
        "        Element root = createRoot(document);",
        "        document.appendChild(root);",
    ]
    for field in attributes:
        xml_field_name = str(field["name"])
        java_field_name = str(field["java_name"])
        getter = f"model.get{to_pascal_case(java_field_name)}()"
        body.extend(
            [
                f"        if ({getter} == null) {{",
            ]
        )
        if bool(field.get("required")):
            body.append(
                f"            throw serializeError({_java_code_string_literal(xml_field_name)}, "
                + _java_code_string_literal("required attribute is null")
                + ");"
            )
        body.extend(
            [
                "        } else {",
                f"            root.setAttribute({_java_code_string_literal(xml_field_name)}, {_xml_format_expression(field, getter)});",
                "        }",
            ]
        )
    for field in fields:
        xml_field_name = str(field["name"])
        java_field_name = str(field["java_name"])
        getter = f"model.get{to_pascal_case(java_field_name)}()"
        if bool(field.get("repeated")):
            if bool(field.get("required")):
                body.extend(
                    [
                        f"        if ({getter}.isEmpty()) {{",
                        f"            throw serializeError({_java_code_string_literal(xml_field_name)}, "
                        + _java_code_string_literal("required repeated element is empty")
                        + ");",
                        "        }",
                    ]
                )
            max_occurs = field.get("max_occurs")
            if max_occurs is not None:
                body.extend(
                    [
                        f"        if ({getter}.size() > {int(max_occurs)}) {{",
                        f"            throw serializeError({_java_code_string_literal(xml_field_name)}, "
                        + _java_code_string_literal(f"expected at most {int(max_occurs)} element(s)")
                        + ");",
                        "        }",
                    ]
                )
            body.extend(
                [
                    f"        for ({_xml_external_java_type(field)} value : {getter}) {{",
                    "            if (value == null) {",
                    f"                appendElement(document, root, {_java_code_string_literal(xml_field_name)}, null, true, {'true' if bool(field.get('nillable')) else 'false'});",
                    "            } else {",
                    f"                appendElement(document, root, {_java_code_string_literal(xml_field_name)}, {_xml_format_expression(field, 'value')}, false, {'true' if bool(field.get('nillable')) else 'false'});",
                    "            }",
                    "        }",
                ]
            )
        else:
            body.extend(
                [
                    f"        if ({getter} == null) {{",
                ]
            )
            if bool(field.get("required")) and not bool(field.get("nillable")):
                body.append(
                    f"            throw serializeError({_java_code_string_literal(xml_field_name)}, "
                    + _java_code_string_literal("required element is null")
                    + ");"
                )
            elif bool(field.get("nillable")):
                body.append(
                    f"            appendElement(document, root, {_java_code_string_literal(xml_field_name)}, null, true, true);"
                )
            body.extend(
                [
                    "        } else {",
                    f"            appendElement(document, root, {_java_code_string_literal(xml_field_name)}, {_xml_format_expression(field, getter)}, false, {'true' if bool(field.get('nillable')) else 'false'});",
                    "        }",
                ]
            )
    body.extend(
        [
            "        String xml = toXml(document);",
            "        validateXml(xml);",
            "        return xml;",
            "    }",
            "",
            "    private Element createRoot(Document document) {",
            "        Element root;",
            "        if (NAMESPACE == null) {",
            "            root = document.createElement(ROOT_ELEMENT);",
            "        } else if (NAMESPACE_ALIAS == null || NAMESPACE_ALIAS.isBlank()) {",
            "            root = document.createElementNS(NAMESPACE, ROOT_ELEMENT);",
            "            root.setAttribute(\"xmlns\", NAMESPACE);",
            "        } else {",
            "            root = document.createElementNS(NAMESPACE, NAMESPACE_ALIAS + \":\" + ROOT_ELEMENT);",
            "            root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI, \"xmlns:\" + NAMESPACE_ALIAS, NAMESPACE);",
            "        }",
            "        return root;",
            "    }",
            "",
            "    private void appendElement(Document document, Element parent, String name, String value, boolean nil, boolean nillable) {",
            "        if (nil && !nillable) {",
            "            return;",
            "        }",
            "        Element child;",
            "        if (NAMESPACE == null) {",
            "            child = document.createElement(name);",
            "        } else {",
            "            child = document.createElementNS(NAMESPACE, name);",
            "        }",
            "        if (nil) {",
            "            child.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI, \"xmlns:xsi\", XMLConstants.W3C_XML_SCHEMA_INSTANCE_NS_URI);",
            "            child.setAttributeNS(XMLConstants.W3C_XML_SCHEMA_INSTANCE_NS_URI, \"xsi:nil\", \"true\");",
            "        } else {",
            "            child.setTextContent(value);",
            "        }",
            "        parent.appendChild(child);",
            "    }",
            "",
            "    private String toXml(Document document) throws TransformerException {",
            "        TransformerFactory transformerFactory = TransformerFactory.newInstance();",
            "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, \"\");",
            "        Transformer transformer = transformerFactory.newTransformer();",
            "        transformer.setOutputProperty(OutputKeys.INDENT, \"no\");",
            "        StringWriter writer = new StringWriter();",
            "        transformer.transform(new DOMSource(document), new StreamResult(writer));",
            "        return writer.toString();",
            "    }",
            "",
            "    private void validateXml(String xml) throws Exception {",
            "        Schema schema = loadSchema();",
            "        schema.newValidator().validate(new StreamSource(new StringReader(xml)));",
            "    }",
            "",
            "    private Schema loadSchema() throws Exception {",
            "        URL resource = getClass().getResource(XSD_RESOURCE);",
            "        if (resource == null) {",
            "            throw new IllegalStateException(\"Missing XML/XSD resource: \" + XSD_RESOURCE);",
            "        }",
            "        SchemaFactory schemaFactory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, \"file,jar\");",
            "        return schemaFactory.newSchema(resource);",
            "    }",
            "",
            "    private DocumentBuilder documentBuilder() throws ParserConfigurationException {",
            "        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();",
            "        factory.setNamespaceAware(true);",
            "        factory.setFeature(\"http://apache.org/xml/features/disallow-doctype-decl\", true);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-general-entities\", false);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-parameter-entities\", false);",
            "        factory.setFeature(\"http://apache.org/xml/features/nonvalidating/load-external-dtd\", false);",
            "        factory.setXIncludeAware(false);",
            "        factory.setExpandEntityReferences(false);",
            "        return factory.newDocumentBuilder();",
            "    }",
            "",
            "    private IllegalArgumentException serializeError(String fieldName, String message) {",
            "        return new IllegalArgumentException("
            + _java_code_string_literal(f"XML serialize error for interface '{contract.name}', field ")
            + " + fieldName + "
            + _java_code_string_literal(": ")
            + " + message);",
            "    }",
            "}",
        ]
    )
    body = [line.replace(_xml_model_class_name_placeholder(), model_class) for line in body]
    return _java_file(
        package_name=f"{root_package}.adapter.xml",
        imports=[
            f"{root_package}.adapter.xml.{model_class}",
            "java.net.URL",
            "java.time.format.DateTimeFormatter",
            "javax.xml.XMLConstants",
            "javax.xml.parsers.DocumentBuilder",
            "javax.xml.parsers.DocumentBuilderFactory",
            "javax.xml.parsers.ParserConfigurationException",
            "javax.xml.transform.OutputKeys",
            "javax.xml.transform.Transformer",
            "javax.xml.transform.TransformerException",
            "javax.xml.transform.TransformerFactory",
            "javax.xml.transform.dom.DOMSource",
            "javax.xml.transform.stream.StreamResult",
            "javax.xml.transform.stream.StreamSource",
            "javax.xml.validation.Schema",
            "javax.xml.validation.SchemaFactory",
            "org.springframework.stereotype.Component",
            "org.w3c.dom.Document",
            "org.w3c.dom.Element",
            "java.io.StringReader",
            "java.io.StringWriter",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_soap_endpoint_config(
    *,
    contracts: list[ContractMetadata],
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    body = [
        "@Configuration",
        "public class SoapEndpointConfig {",
        "",
        "    private static final String DISALLOW_DOCTYPE_DECL =",
        '        "http://apache.org/xml/features/disallow-doctype-decl";',
        "    private static final String EXTERNAL_GENERAL_ENTITIES =",
        '        "http://xml.org/sax/features/external-general-entities";',
        "    private static final String EXTERNAL_PARAMETER_ENTITIES =",
        '        "http://xml.org/sax/features/external-parameter-entities";',
        "    private static final String LOAD_EXTERNAL_DTD =",
        '        "http://apache.org/xml/features/nonvalidating/load-external-dtd";',
        "    private static final String ENTITY_EXPANSION_LIMIT =",
        '        "http://www.oracle.com/xml/jaxp/properties/entityExpansionLimit";',
        "",
        '    @Bean(name = "messageFactory")',
        "    public SaajSoapMessageFactory edgeForgeSoapMessageFactory(",
        '            @Value("${app.soap.max-envelope-bytes:1048576}") int maxEnvelopeBytes) {',
        "        return new HardenedSaajSoapMessageFactory(maxEnvelopeBytes);",
        "    }",
        "",
        "    @Bean(name = \"messageReceiverHandlerAdapter\")",
        "    public WebServiceMessageReceiverHandlerAdapter edgeForgeSoapMessageReceiverHandlerAdapter() {",
        "        return new EdgeForgeSoapMessageReceiverHandlerAdapter();",
        "    }",
        "",
        "    @Bean",
        "    public EndpointExceptionResolver edgeForgeSoapFaultExceptionResolver() {",
        "        return new EdgeForgeSoapFaultExceptionResolver();",
        "    }",
        "",
        "    @Bean",
        "    public PayloadEndpointAdapter edgeForgeSoapPayloadEndpointAdapter() {",
        "        return new PayloadEndpointAdapter();",
        "    }",
        "",
        "    @Bean",
        "    public EndpointMapping edgeForgeUnknownSoapOperationEndpointMapping() {",
        "        AbstractEndpointMapping mapping = new AbstractEndpointMapping() {",
        "            private final PayloadEndpoint endpoint = source -> {",
        "                throw new SoapOperationMappingException(",
        "                    \"Unknown SOAP operation for generated SOAP WSDL runtime. \"",
        "                        + \"No generated SOAP endpoint matched the request payload. \"",
        "                        + \"Verify the SOAP body root element and namespace.\"",
        "                );",
        "            };",
        "",
        "            @Override",
        "            protected Object getEndpointInternal(MessageContext messageContext) {",
        "                return endpoint;",
        "            }",
        "        };",
        "        mapping.setOrder(Ordered.LOWEST_PRECEDENCE);",
        "        return mapping;",
        "    }",
    ]
    for contract, method_name in _soap_wsdl_definition_methods(contracts):
        body.extend(
            [
                "",
                f"    @Bean(name = {_java_code_string_literal(contract.name)})",
                f"    public SimpleWsdl11Definition {method_name}() {{",
                "        return new SimpleWsdl11Definition(new ClassPathResource("
                + _java_code_string_literal(_soap_wsdl_resource_path(contract, leading_slash=False))
                + "));",
                "    }",
            ]
        )
    body.extend(
        [
            "",
            "    private static final class EdgeForgeSoapFaultExceptionResolver",
            "            extends AbstractSoapFaultDefinitionExceptionResolver {",
            "",
            "        private EdgeForgeSoapFaultExceptionResolver() {",
            "            setOrder(Ordered.HIGHEST_PRECEDENCE);",
            "        }",
            "",
            "        @Override",
            "        protected SoapFaultDefinition getFaultDefinition(Object endpoint, Exception ex) {",
            "            SoapFaultDefinition definition = new SoapFaultDefinition();",
            "            definition.setFaultCode(SoapFaultDefinition.CLIENT);",
            "            definition.setFaultStringOrReason(safeSoapDiagnostic(ex));",
            "            return definition;",
            "        }",
            "    }",
            "",
            "    private static final class HardenedSaajSoapMessageFactory extends SaajSoapMessageFactory {",
            "",
            "        private final int maxEnvelopeBytes;",
            "",
            "        private HardenedSaajSoapMessageFactory(int maxEnvelopeBytes) {",
            "            if (maxEnvelopeBytes < 1) {",
            "                throw new IllegalArgumentException(",
            '                    "app.soap.max-envelope-bytes must be greater than zero.");',
            "            }",
            "            this.maxEnvelopeBytes = maxEnvelopeBytes;",
            "        }",
            "",
            "        @Override",
            "        public SaajSoapMessage createWebServiceMessage(InputStream inputStream) throws IOException {",
            "            byte[] envelope = readBoundedEnvelope(inputStream);",
            "            validateEnvelopeBeforeSaaj(envelope);",
            "            InputStream replay = inputStream instanceof TransportInputStream transport",
            "                ? new ReplayTransportInputStream(envelope, transport)",
            "                : new ByteArrayInputStream(envelope);",
            "            return super.createWebServiceMessage(replay);",
            "        }",
            "",
            "        private byte[] readBoundedEnvelope(InputStream inputStream) throws IOException {",
            "            ByteArrayOutputStream output =",
            "                new ByteArrayOutputStream(Math.min(maxEnvelopeBytes, 8192));",
            "            byte[] buffer = new byte[8192];",
            "            int total = 0;",
            "            int read;",
            "            while ((read = inputStream.read(buffer)) != -1) {",
            "                if (read > maxEnvelopeBytes - total) {",
            "                    throw new SoapMessageCreationException(",
            '                        "SOAP envelope exceeds configured maximum of "',
            '                            + maxEnvelopeBytes + " bytes.");',
            "                }",
            "                output.write(buffer, 0, read);",
            "                total += read;",
            "            }",
            "            return output.toByteArray();",
            "        }",
            "",
            "        private void validateEnvelopeBeforeSaaj(byte[] envelope) {",
            "            try {",
            "                SAXParserFactory factory = SAXParserFactory.newInstance();",
            "                factory.setNamespaceAware(true);",
            "                factory.setXIncludeAware(false);",
            "                factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);",
            "                factory.setFeature(DISALLOW_DOCTYPE_DECL, true);",
            "                factory.setFeature(EXTERNAL_GENERAL_ENTITIES, false);",
            "                factory.setFeature(EXTERNAL_PARAMETER_ENTITIES, false);",
            "                factory.setFeature(LOAD_EXTERNAL_DTD, false);",
            "",
            "                SAXParser parser = factory.newSAXParser();",
            "                XMLReader reader = parser.getXMLReader();",
            "                reader.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "                reader.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, \"\");",
            "                reader.setProperty(ENTITY_EXPANSION_LIMIT, \"256\");",
            "                reader.setEntityResolver((publicId, systemId) -> {",
            "                    throw new SAXException(\"External entities are disabled for SOAP envelopes.\");",
            "                });",
            "                DefaultHandler handler = new DefaultHandler();",
            "                reader.setContentHandler(handler);",
            "                reader.setErrorHandler(handler);",
            "                reader.parse(new InputSource(new ByteArrayInputStream(envelope)));",
            "            } catch (ParserConfigurationException | SAXException | IOException ex) {",
            "                throw new SoapMessageCreationException(\"Rejected unsafe SOAP/XML envelope.\", ex);",
            "            }",
            "        }",
            "",
            "        private static final class ReplayTransportInputStream extends TransportInputStream {",
            "",
            "            private final byte[] envelope;",
            "            private final TransportInputStream source;",
            "",
            "            private ReplayTransportInputStream(",
            "                    byte[] envelope, TransportInputStream source) {",
            "                this.envelope = envelope;",
            "                this.source = source;",
            "            }",
            "",
            "            @Override",
            "            protected InputStream createInputStream() {",
            "                return new ByteArrayInputStream(envelope);",
            "            }",
            "",
            "            @Override",
            "            public Iterator<String> getHeaderNames() throws IOException {",
            "                return source.getHeaderNames();",
            "            }",
            "",
            "            @Override",
            "            public Iterator<String> getHeaders(String name) throws IOException {",
            "                return source.getHeaders(name);",
            "            }",
            "        }",
            "    }",
            "",
            "    private static final class EdgeForgeSoapMessageReceiverHandlerAdapter",
            "            extends WebServiceMessageReceiverHandlerAdapter {",
            "",
            "        @Override",
            "        public void afterPropertiesSet() {",
            "            // The SOAP servlet injects the message factory into this named adapter during servlet initialization.",
            "        }",
            "",
            "        @Override",
            "        public ModelAndView handle(HttpServletRequest request, HttpServletResponse response, Object handler)",
            "                throws Exception {",
            "            try {",
            "                return super.handle(request, response, handler);",
            "            } catch (SoapMessageCreationException ex) {",
            "                writeMalformedSoapFault(response, ex);",
            "                return null;",
            "            }",
            "        }",
            "",
            "        @Override",
            "        protected void handleInvalidXmlException(",
            "                HttpServletRequest request,",
            "                HttpServletResponse response,",
            "                Object handler,",
            "                InvalidXmlException ex) throws Exception {",
            "            writeMalformedSoapFault(response, ex);",
            "        }",
            "    }",
            "",
            "    private static void writeMalformedSoapFault(HttpServletResponse response, Exception ex) throws Exception {",
            "        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);",
            "        response.setContentType(\"text/xml;charset=UTF-8\");",
            "        try (PrintWriter writer = response.getWriter()) {",
            "            writer.write(soapFaultEnvelope(\"Malformed SOAP/XML request: \" + safeSoapDiagnostic(ex)));",
            "        }",
            "    }",
            "",
            "    private static String safeSoapDiagnostic(Exception ex) {",
            "        String message = ex.getMessage();",
            "        if (message == null || message.isBlank()) {",
            "            return \"SOAP request failed while processing the generated adapter.\";",
            "        }",
            "        String sanitized = message.replace('\\r', ' ').replace('\\n', ' ').replace('\\t', ' ').trim();",
            "        sanitized = sanitized.replaceAll(\"file:/[^\\\\s]+\", \"[path]\");",
            "        sanitized = sanitized.replaceAll(\"([A-Za-z]:)?[/\\\\\\\\][^\\\\s]+\", \"[path]\");",
            "        if (sanitized.length() > 300) {",
            "            return sanitized.substring(0, 300) + \"...\";",
            "        }",
            "        return sanitized;",
            "    }",
            "",
            "    private static String soapFaultEnvelope(String faultString) {",
            "        return \"<?xml version=\\\"1.0\\\" encoding=\\\"UTF-8\\\"?>\"",
            "            + \"<soapenv:Envelope xmlns:soapenv=\\\"http://schemas.xmlsoap.org/soap/envelope/\\\">\"",
            "            + \"<soapenv:Body><soapenv:Fault><faultcode>soapenv:Client</faultcode>\"",
            "            + \"<faultstring>\" + escapeXml(faultString) + \"</faultstring>\"",
            "            + \"</soapenv:Fault></soapenv:Body></soapenv:Envelope>\";",
            "    }",
            "",
            "    private static String escapeXml(String value) {",
            "        return value",
            "            .replace(\"&\", \"&amp;\")",
            "            .replace(\"<\", \"&lt;\")",
            "            .replace(\">\", \"&gt;\")",
            "            .replace(\"\\\"\", \"&quot;\")",
            "            .replace(\"'\", \"&apos;\");",
            "    }",
        ]
    )
    body.append("}")
    return _java_file(
        package_name=f"{root_package}.adapter.soap",
        imports=[
            f"{root_package}.exception.SoapOperationMappingException",
            "java.io.ByteArrayInputStream",
            "java.io.ByteArrayOutputStream",
            "java.io.IOException",
            "java.io.InputStream",
            "java.io.PrintWriter",
            "java.util.Iterator",
            "javax.xml.XMLConstants",
            "javax.xml.parsers.ParserConfigurationException",
            "javax.xml.parsers.SAXParser",
            "javax.xml.parsers.SAXParserFactory",
            "jakarta.servlet.http.HttpServletRequest",
            "jakarta.servlet.http.HttpServletResponse",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.context.annotation.Bean",
            "org.springframework.context.annotation.Configuration",
            "org.springframework.core.io.ClassPathResource",
            "org.springframework.core.Ordered",
            "org.springframework.web.servlet.ModelAndView",
            "org.springframework.ws.InvalidXmlException",
            "org.springframework.ws.context.MessageContext",
            "org.springframework.ws.server.EndpointExceptionResolver",
            "org.springframework.ws.server.EndpointMapping",
            "org.springframework.ws.server.endpoint.PayloadEndpoint",
            "org.springframework.ws.server.endpoint.adapter.PayloadEndpointAdapter",
            "org.springframework.ws.server.endpoint.mapping.AbstractEndpointMapping",
            "org.springframework.ws.soap.SoapMessageCreationException",
            "org.springframework.ws.soap.saaj.SaajSoapMessage",
            "org.springframework.ws.soap.saaj.SaajSoapMessageFactory",
            "org.springframework.ws.soap.server.endpoint.AbstractSoapFaultDefinitionExceptionResolver",
            "org.springframework.ws.soap.server.endpoint.SoapFaultDefinition",
            "org.springframework.ws.transport.TransportInputStream",
            "org.springframework.ws.transport.http.WebServiceMessageReceiverHandlerAdapter",
            "org.springframework.ws.wsdl.wsdl11.SimpleWsdl11Definition",
            "org.xml.sax.InputSource",
            "org.xml.sax.SAXException",
            "org.xml.sax.XMLReader",
            "org.xml.sax.helpers.DefaultHandler",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_soap_operation_mapping_exception(
    *,
    root_package: str,
    source_manifest: str,
    target_profile: TargetProfile,
    generation_run_id: str,
) -> str:
    body = [
        "public class SoapOperationMappingException extends RuntimeException {",
        "    public SoapOperationMappingException(String message) {",
        "        super(message);",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.exception",
        imports=[],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_soap_client_exception(
    *,
    root_package: str,
    source_manifest: str,
    target_profile: TargetProfile,
    generation_run_id: str,
) -> str:
    body = [
        "public class SoapClientException extends RuntimeException {",
        "    public SoapClientException(String message) {",
        "        super(message);",
        "    }",
        "",
        "    public SoapClientException(String message, Throwable cause) {",
        "        super(message, cause);",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.exception",
        imports=[],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_soap_client_config(
    *,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    body = [
        "@Configuration",
        "public class SoapClientConfig {",
        "",
        "    @Bean",
        "    public WebServiceTemplate webServiceTemplate() {",
        "        return new WebServiceTemplate();",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{root_package}.adapter.soap",
        imports=[
            "org.springframework.context.annotation.Bean",
            "org.springframework.context.annotation.Configuration",
            "org.springframework.ws.client.core.WebServiceTemplate",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_soap_client(
    *,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    soap_contract = _require_soap_contract(contract)
    client_name = _soap_client_class_name(contract)
    client_methods = _soap_client_java_methods(soap_contract)
    xsd_resources = _soap_xsd_resource_paths(contract, source_manifest=source_manifest)
    if not xsd_resources:
        raise ValueError(
            f"Outbound SOAP/WSDL interface '{contract.name}' has no packaged XSD resources "
            "available for request/response validation."
        )
    property_name = _soap_client_uri_property(contract)
    body = [
        "@Component",
        f"public class {client_name} {{",
        "    private static final String[] XSD_RESOURCES = new String[] {",
        *[f"        {_java_code_string_literal(resource)}," for resource in xsd_resources],
        "    };",
        "",
        "    private final WebServiceTemplate webServiceTemplate;",
        "    private final String endpointUri;",
        "",
        f"    public {client_name}(",
        "            WebServiceTemplate webServiceTemplate,",
        f"            @Value(\"${{{property_name}}}\") String endpointUri) {{",
        "        this.webServiceTemplate = webServiceTemplate;",
        "        this.endpointUri = endpointUri;",
        "    }",
        "",
    ]
    for operation in soap_contract.get("operations") or []:
        operation_name = str(operation["name"])
        method_name = client_methods[operation_name]
        soap_action = operation.get("soap_action")
        input_namespace, input_local = _soap_qname_parts(
            str(operation.get("input_element") or operation_name),
            default_namespace=str(soap_contract.get("target_namespace") or ""),
        )
        output_element = operation.get("output_element")
        output_namespace, output_local = _soap_qname_parts(
            str(output_element or operation_name),
            default_namespace=str(soap_contract.get("target_namespace") or ""),
        )
        body.extend(
            [
                f"    public Source {method_name}(Source requestPayload) {{",
                "        try {",
                "            Source validatedRequest = validatePayload(",
                "                requestPayload,",
                f"                {_java_code_string_literal(input_namespace)},",
                f"                {_java_code_string_literal(input_local)},",
                f"                {_java_code_string_literal(operation_name)},",
                "                \"request\"",
                "            );",
                "            Source response = webServiceTemplate.sendSourceAndReceive(",
                "                endpointUri,",
                "                validatedRequest,",
                "                message -> applySoapAction(message, "
                + _java_code_string_literal(str(soap_action or ""))
                + "),",
                "                source -> {",
                "                    try {",
                "                        return copySource(source);",
                "                    } catch (Exception ex) {",
                "                        throw new SoapClientException("
                + _java_code_string_literal(
                    f"SOAP operation '{operation_name}' for interface '{contract.name}' response copy failed."
                )
                + ", ex);",
                "                    }",
                "                }",
                "            );",
                "            if (response == null) {",
                "                throw new SoapClientException("
                + _java_code_string_literal(
                    f"SOAP operation '{operation_name}' for interface '{contract.name}' returned no response."
                )
                + ");",
                "            }",
                "            return validatePayload(",
                "                response,",
                f"                {_java_code_string_literal(output_namespace)},",
                f"                {_java_code_string_literal(output_local)},",
                f"                {_java_code_string_literal(operation_name)},",
                "                \"response\"",
                "            );",
                "        } catch (SoapClientException ex) {",
                "            throw ex;",
                "        } catch (Exception ex) {",
                "            throw new SoapClientException("
                + _java_code_string_literal(
                    f"SOAP operation '{operation_name}' for interface '{contract.name}' failed."
                )
                + ", ex);",
                "        }",
                "    }",
                "",
            ]
        )
    body.extend(
        [
            "    private void applySoapAction(WebServiceMessage message, String soapAction) {",
            "        if (soapAction == null || soapAction.isBlank()) {",
            "            return;",
            "        }",
            "        if (message instanceof SoapMessage) {",
            "            ((SoapMessage) message).setSoapAction(soapAction);",
            "        }",
            "    }",
            "",
            "    private Source validatePayload(",
            "            Source payload,",
            "            String expectedNamespace,",
            "            String expectedLocalName,",
            "            String operationName,",
            "            String direction) throws Exception {",
            "        Document document = documentBuilder().newDocument();",
            "        secureTransformerFactory().newTransformer().transform(payload, new DOMResult(document));",
            "        validateRootElement(document, expectedNamespace, expectedLocalName, operationName, direction);",
            "        loadSchema().newValidator().validate(new DOMSource(document));",
            "        return new DOMSource(document);",
            "    }",
            "",
            "    private void validateRootElement(",
            "            Document document,",
            "            String expectedNamespace,",
            "            String expectedLocalName,",
            "            String operationName,",
            "            String direction) {",
            "        Element root = document.getDocumentElement();",
            "        if (root == null) {",
            "            throw new SoapClientException(\"SOAP operation '\" + operationName + \"' \" + direction + \" payload is empty.\");",
            "        }",
            "        String actualNamespace = root.getNamespaceURI() == null ? \"\" : root.getNamespaceURI();",
            "        String actualLocalName = root.getLocalName() == null ? root.getNodeName() : root.getLocalName();",
            "        if (!expectedNamespace.equals(actualNamespace) || !expectedLocalName.equals(actualLocalName)) {",
            "            throw new SoapClientException(",
            "                \"SOAP operation '\" + operationName + \"' expected \" + direction + \" root {\"",
            "                    + expectedNamespace + \"}\" + expectedLocalName",
            "                    + \" but got {\" + actualNamespace + \"}\" + actualLocalName + \".\"",
            "            );",
            "        }",
            "    }",
            "",
            "    private Source copySource(Source source) throws Exception {",
            "        Document document = documentBuilder().newDocument();",
            "        secureTransformerFactory().newTransformer().transform(source, new DOMResult(document));",
            "        return new DOMSource(document);",
            "    }",
            "",
            "    private Schema loadSchema() throws Exception {",
            "        SchemaFactory schemaFactory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, \"file,jar\");",
            "        List<Source> schemas = new ArrayList<>();",
            "        for (String xsdResource : XSD_RESOURCES) {",
            "            URL resource = getClass().getResource(xsdResource);",
            "            if (resource == null) {",
            "                throw new IllegalStateException(\"Missing SOAP/WSDL XSD resource: \" + xsdResource);",
            "            }",
            "            schemas.add(new StreamSource(resource.toExternalForm()));",
            "        }",
            "        return schemaFactory.newSchema(schemas.toArray(new Source[0]));",
            "    }",
            "",
            "    private DocumentBuilder documentBuilder() throws ParserConfigurationException {",
            "        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();",
            "        factory.setNamespaceAware(true);",
            "        factory.setFeature(\"http://apache.org/xml/features/disallow-doctype-decl\", true);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-general-entities\", false);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-parameter-entities\", false);",
            "        factory.setFeature(\"http://apache.org/xml/features/nonvalidating/load-external-dtd\", false);",
            "        factory.setXIncludeAware(false);",
            "        factory.setExpandEntityReferences(false);",
            "        return factory.newDocumentBuilder();",
            "    }",
            "",
            "    private TransformerFactory secureTransformerFactory() throws Exception {",
            "        TransformerFactory transformerFactory = TransformerFactory.newInstance();",
            "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, \"\");",
            "        return transformerFactory;",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.adapter.soap",
        imports=[
            f"{root_package}.exception.SoapClientException",
            "java.net.URL",
            "java.util.ArrayList",
            "java.util.List",
            "javax.xml.XMLConstants",
            "javax.xml.parsers.DocumentBuilder",
            "javax.xml.parsers.DocumentBuilderFactory",
            "javax.xml.parsers.ParserConfigurationException",
            "javax.xml.transform.Source",
            "javax.xml.transform.TransformerFactory",
            "javax.xml.transform.dom.DOMResult",
            "javax.xml.transform.dom.DOMSource",
            "javax.xml.transform.stream.StreamSource",
            "javax.xml.validation.Schema",
            "javax.xml.validation.SchemaFactory",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.stereotype.Component",
            "org.springframework.ws.WebServiceMessage",
            "org.springframework.ws.client.core.WebServiceTemplate",
            "org.springframework.ws.soap.SoapMessage",
            "org.w3c.dom.Document",
            "org.w3c.dom.Element",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _outbound_soap_action_contexts(metadata: MetadataProject) -> list[_OutboundSoapActionContext]:
    contexts: list[_OutboundSoapActionContext] = []
    entities_by_name = {entity.name: entity for entity in all_entities(metadata)}
    for contract in _outbound_soap_contracts(metadata):
        soap_contract = _require_soap_contract(contract)
        operations_by_name = {
            str(operation["name"]): operation for operation in soap_contract.get("operations") or []
        }
        client_methods = _soap_client_java_methods(soap_contract)
        for operation_name, mapping in _soap_canonical_operation_mappings(soap_contract).items():
            canonical_operation = mapping.get("canonical_operation") or {}
            if canonical_operation.get("kind") != "invoke_by_id":
                continue
            lookup = canonical_operation.get("lookup") or {}
            entity_name = str(canonical_operation.get("entity") or "")
            entity = entities_by_name[entity_name]
            contexts.append(
                _OutboundSoapActionContext(
                    contract=contract,
                    operation_name=operation_name,
                    soap_contract=soap_contract,
                    operation=operations_by_name[operation_name],
                    canonical_operation=canonical_operation,
                    entity=entity,
                    id_field=entity_id_field(entity),
                    lookup_field_name=str(lookup.get("field") or ""),
                    client_method_name=client_methods[operation_name],
                )
            )
    return contexts


def _render_outbound_soap_action_controller(
    *,
    contexts: list[_OutboundSoapActionContext],
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    contexts_by_contract: OrderedDict[str, list[_OutboundSoapActionContext]] = OrderedDict()
    for ctx in contexts:
        contexts_by_contract.setdefault(ctx.contract.name, []).append(ctx)

    repository_entities: OrderedDict[str, CanonicalEntity] = OrderedDict()
    client_contracts: OrderedDict[str, ContractMetadata] = OrderedDict()
    for ctx in contexts:
        repository_entities[ctx.entity.name] = ctx.entity
        client_contracts[ctx.contract.name] = ctx.contract

    client_var_names: dict[str, str] = {}
    used_client_vars: set[str] = set()
    for contract in client_contracts.values():
        client_var_names[contract.name] = _unique_generated_name(
            to_java_method_name(_soap_client_class_name(contract), fallback="soapClient"),
            used_client_vars,
        )

    action_methods: dict[tuple[str, str], str] = {}
    used_action_methods: set[str] = set()
    for ctx in contexts:
        action_methods[(ctx.contract.name, ctx.operation_name)] = _unique_java_method_name(
            to_java_method_name(
                f"invoke {ctx.contract.name} {ctx.operation_name}",
                fallback="invokeOutboundSoapOperation",
            ),
            used_action_methods,
        )

    registry_lines = [
        "    private static final Map<String, Map<String, OperationConfig>> OPERATIONS = Map.ofEntries(",
    ]
    known_operation_lines = [
        "    private static final Map<String, Set<String>> KNOWN_OPERATIONS = Map.ofEntries(",
    ]
    contract_items = list(contexts_by_contract.items())
    for contract_index, (contract_name, contract_contexts) in enumerate(contract_items):
        contract_suffix = "," if contract_index < len(contract_items) - 1 else ""
        registry_lines.append(
            f"        Map.entry({_java_code_string_literal(contract_name)}, Map.ofEntries("
        )
        soap_contract = _require_soap_contract(contract_contexts[0].contract)
        known_operation_names = [
            str(operation["name"]) for operation in soap_contract.get("operations") or []
        ]
        known_operation_lines.append(
            f"        Map.entry({_java_code_string_literal(contract_name)}, Set.of("
            + ", ".join(_java_code_string_literal(name) for name in known_operation_names)
            + f")){contract_suffix}"
        )
        for operation_index, ctx in enumerate(contract_contexts):
            operation_suffix = "," if operation_index < len(contract_contexts) - 1 else ""
            registry_lines.append(
                "            Map.entry("
                + _java_code_string_literal(ctx.operation_name)
                + ", new OperationConfig("
                + _java_code_string_literal(ctx.entity.name)
                + ", "
                + _java_code_string_literal(ctx.lookup_field_name)
                + ", "
                + _java_code_string_literal(f"{ctx.contract.name}::{ctx.operation_name}")
                + f")){operation_suffix}"
            )
        registry_lines.append(f"        )){contract_suffix}")
    registry_lines.append("    );")
    known_operation_lines.append("    );")

    fields: list[str] = []
    constructor_params: list[str] = []
    assignments: list[str] = []
    for entity in repository_entities.values():
        repository_class = f"{entity.name}Repository"
        repository_var = _repository_var_name(entity)
        fields.append(f"    private final {repository_class} {repository_var};")
        constructor_params.append(f"            {repository_class} {repository_var}")
        assignments.append(f"        this.{repository_var} = {repository_var};")
    for contract in client_contracts.values():
        client_class = _soap_client_class_name(contract)
        client_var = client_var_names[contract.name]
        fields.append(f"    private final {client_class} {client_var};")
        constructor_params.append(f"            {client_class} {client_var}")
        assignments.append(f"        this.{client_var} = {client_var};")

    body = [
        "@RestController",
        "@RequestMapping(\"/soap/outbound\")",
        "public class OutboundSoapActionController {",
        "",
        *registry_lines,
        "",
        *known_operation_lines,
        "",
        *fields,
        "",
        "    public OutboundSoapActionController(",
        ",\n".join(constructor_params),
        "    ) {",
        *assignments,
        "    }",
        "",
        "    @PostMapping(\"/{contractName}/{operationName}\")",
        "    public ResponseEntity<?> invoke(",
        "            @PathVariable String contractName,",
        "            @PathVariable String operationName,",
        "            @RequestBody(required = false) OutboundSoapActionRequest request) {",
        "        Map<String, OperationConfig> operations = OPERATIONS.get(contractName);",
        "        if (operations == null) {",
        "            return failure(",
        "                    HttpStatus.NOT_FOUND,",
        "                    contractName,",
        "                    operationName,",
        "                    null,",
        "                    null,",
        "                    \"Unknown downstream SOAP canonical contract: \" + contractName);",
        "        }",
        "        OperationConfig operation = operations.get(operationName);",
        "        if (operation == null) {",
        "            Set<String> knownOperations = KNOWN_OPERATIONS.get(contractName);",
        "            if (knownOperations != null && knownOperations.contains(operationName)) {",
        "                return failure(",
        "                        HttpStatus.BAD_REQUEST,",
        "                        contractName,",
        "                        operationName,",
        "                        null,",
        "                        null,",
        "                        \"Downstream SOAP contract '\" + contractName + \"' operation '\"",
        "                                + operationName + \"' has no canonical invoke_by_id mapping.\");",
        "            }",
        "            return failure(",
        "                    HttpStatus.NOT_FOUND,",
        "                    contractName,",
        "                    operationName,",
        "                    null,",
        "                    null,",
        "                    \"Unknown downstream SOAP canonical operation: \" + contractName + \"/\" + operationName);",
        "        }",
        "        if (request == null || request.id() == null || request.id().isBlank()) {",
        "            return failure(",
        "                    HttpStatus.BAD_REQUEST,",
        "                    contractName,",
        "                    operationName,",
        "                    operation.entity(),",
        "                    null,",
        "                    \"Outbound SOAP canonical invoke_by_id request id is required.\");",
        "        }",
        "        String id = request.id().trim();",
        "        return switch (operation.actionKey()) {",
    ]
    for ctx in contexts:
        body.append(
            "            case "
            + _java_code_string_literal(f"{ctx.contract.name}::{ctx.operation_name}")
            + " -> "
            + action_methods[(ctx.contract.name, ctx.operation_name)]
            + "(id);"
        )
    body.extend(
        [
        "            default -> failure(",
        "                    HttpStatus.INTERNAL_SERVER_ERROR,",
        "                    contractName,",
        "                    operationName,",
        "                    operation.entity(),",
        "                    id,",
        "                    \"Outbound SOAP canonical operation dispatch is not generated for \"",
        "                            + contractName + \"/\" + operationName + \".\");",
        "        };",
        "    }",
        "",
        ]
    )
    for ctx in contexts:
        body.extend(
            _outbound_soap_action_method_lines(
                ctx=ctx,
                method_name=action_methods[(ctx.contract.name, ctx.operation_name)],
                client_var_name=client_var_names[ctx.contract.name],
            )
        )
    id_converter_types = _outbound_soap_action_id_converter_types(contexts)
    body.extend(_outbound_soap_action_common_method_lines(id_converter_types))
    body.extend(
        [
        "    private ResponseEntity<OutboundSoapActionSuccessResponse> success(",
        "            String contractName,",
        "            String operationName,",
        "            String entity,",
        "            String id,",
        "            Map<String, String> response) {",
        "        return ResponseEntity.ok(",
        "                new OutboundSoapActionSuccessResponse(",
        "                        contractName,",
        "                        operationName,",
        "                        entity,",
        "                        id,",
        "                        response));",
        "    }",
        "",
        "    private ResponseEntity<OutboundSoapActionFailureResponse> failure(",
        "            HttpStatus status,",
        "            String contractName,",
        "            String operationName,",
        "            String entity,",
        "            String id,",
        "            String message) {",
        "        return ResponseEntity.status(status).body(",
        "                new OutboundSoapActionFailureResponse(",
        "                        contractName,",
        "                        operationName,",
        "                        entity,",
        "                        id,",
        "                        status.value(),",
        "                        status.getReasonPhrase(),",
        "                        message));",
        "    }",
        "",
        "    public record OutboundSoapActionRequest(String id) {",
        "    }",
        "",
        "    public record OutboundSoapActionSuccessResponse(",
        "            String contractName,",
        "            String operationName,",
        "            String entity,",
        "            String id,",
        "            Map<String, String> response) {",
        "    }",
        "",
        "    public record OutboundSoapActionFailureResponse(",
        "            String contractName,",
        "            String operationName,",
        "            String entity,",
        "            String id,",
        "            int status,",
        "            String error,",
        "            String message) {",
        "    }",
        "",
        "    private record OperationConfig(String entity, String lookupField, String actionKey) {",
        "    }",
        "",
        "    private static class OutboundSoapActionException extends RuntimeException {",
        "        private final HttpStatus status;",
        "",
        "        OutboundSoapActionException(HttpStatus status, String message) {",
        "            super(message);",
        "            this.status = status;",
        "        }",
        "",
        "        HttpStatus status() {",
        "            return status;",
        "        }",
        "    }",
        "}",
    ]
    )
    imports = [
        f"{root_package}.exception.SoapClientException",
        "java.net.SocketTimeoutException",
        "java.util.LinkedHashMap",
        "java.util.Map",
        "java.util.Set",
        "javax.xml.XMLConstants",
        "javax.xml.parsers.DocumentBuilder",
        "javax.xml.parsers.DocumentBuilderFactory",
        "javax.xml.parsers.ParserConfigurationException",
        "javax.xml.transform.Source",
        "javax.xml.transform.TransformerFactory",
        "javax.xml.transform.dom.DOMResult",
        "javax.xml.transform.dom.DOMSource",
        "org.springframework.http.HttpStatus",
        "org.springframework.http.ResponseEntity",
        "org.springframework.web.bind.annotation.PathVariable",
        "org.springframework.web.bind.annotation.PostMapping",
        "org.springframework.web.bind.annotation.RequestBody",
        "org.springframework.web.bind.annotation.RequestMapping",
        "org.springframework.web.bind.annotation.RestController",
        "org.springframework.ws.client.WebServiceIOException",
        "org.springframework.ws.soap.client.SoapFaultClientException",
        "org.w3c.dom.Document",
        "org.w3c.dom.Element",
        "org.w3c.dom.Node",
        "org.w3c.dom.NodeList",
    ]
    imports.extend(_outbound_soap_action_java_type_imports(contexts))
    if (
        CanonicalFieldType.DATE in id_converter_types
        or CanonicalFieldType.DATETIME in id_converter_types
    ):
        imports.append("java.time.format.DateTimeParseException")
    for entity in repository_entities.values():
        imports.append(f"{root_package}.domain.{entity.name}")
        imports.append(f"{root_package}.repository.{entity.name}Repository")
    for contract in client_contracts.values():
        imports.append(f"{root_package}.adapter.soap.{_soap_client_class_name(contract)}")
    return _java_file(
        package_name=f"{root_package}.adapter.soap",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _outbound_soap_action_id_converter_types(
    contexts: list[_OutboundSoapActionContext],
) -> set[CanonicalFieldType]:
    return {
        ctx.id_field.type
        for ctx in contexts
        if ctx.id_field.type != CanonicalFieldType.STRING
    }


def _outbound_soap_action_java_type_imports(
    contexts: list[_OutboundSoapActionContext],
) -> list[str]:
    java_types: set[str] = set()
    for ctx in contexts:
        java_types.add(_java_type(ctx.id_field))
        fields_by_name = {field.name: field for field in ctx.entity.fields}
        for mapping in ctx.canonical_operation.get("request_mappings") or []:
            source = str(mapping.get("source") or "")
            if "." not in source:
                continue
            _entity_name, field_name = source.split(".", 1)
            field = fields_by_name.get(field_name)
            if field is not None:
                java_types.add(_java_type(field))
    return [
        JAVA_IMPORTS[java_type]
        for java_type in sorted(java_types)
        if java_type in JAVA_IMPORTS
    ]


def _outbound_soap_action_method_lines(
    *,
    ctx: _OutboundSoapActionContext,
    method_name: str,
    client_var_name: str,
) -> list[str]:
    entity = ctx.entity
    repository_var = _repository_var_name(entity)
    request_builder = f"{method_name}RequestPayload"
    response_extractor = f"{method_name}Response"
    id_java_type = _java_type(ctx.id_field)
    lookup_id_expr = _outbound_soap_id_conversion_expression(ctx.id_field, "id")
    lines = [
        f"    private ResponseEntity<?> {method_name}(String id) {{",
        "        try {",
        f"            {id_java_type} lookupId = {lookup_id_expr};",
        f"            {entity.name} record = {repository_var}.findById(lookupId).orElse(null);",
        "            if (record == null) {",
        "                return failure(",
        "                        HttpStatus.NOT_FOUND,",
        f"                        {_java_code_string_literal(ctx.contract.name)},",
        f"                        {_java_code_string_literal(ctx.operation_name)},",
        f"                        {_java_code_string_literal(entity.name)},",
        "                        id,",
        "                        "
        + _java_code_string_literal(
            f"Canonical entity '{entity.name}' was not found for outbound SOAP invoke_by_id id: "
        )
        + " + id);",
        "            }",
        f"            Source requestPayload = {request_builder}(record);",
        f"            Source responsePayload = {client_var_name}.{ctx.client_method_name}(requestPayload);",
        f"            Map<String, String> mappedResponse = {response_extractor}(responsePayload);",
        "            return success(",
        f"                    {_java_code_string_literal(ctx.contract.name)},",
        f"                    {_java_code_string_literal(ctx.operation_name)},",
        f"                    {_java_code_string_literal(entity.name)},",
        "                    id,",
        "                    mappedResponse);",
        "        } catch (OutboundSoapActionException ex) {",
        "            return failure(",
        "                    ex.status(),",
        f"                    {_java_code_string_literal(ctx.contract.name)},",
        f"                    {_java_code_string_literal(ctx.operation_name)},",
        f"                    {_java_code_string_literal(entity.name)},",
        "                    id,",
        "                    ex.getMessage());",
        "        } catch (SoapClientException ex) {",
        "            return soapClientFailure(",
        f"                    {_java_code_string_literal(ctx.contract.name)},",
        f"                    {_java_code_string_literal(ctx.operation_name)},",
        f"                    {_java_code_string_literal(entity.name)},",
        "                    id,",
        "                    ex);",
        "        } catch (Exception ex) {",
        "            return failure(",
        "                    HttpStatus.BAD_GATEWAY,",
        f"                    {_java_code_string_literal(ctx.contract.name)},",
        f"                    {_java_code_string_literal(ctx.operation_name)},",
        f"                    {_java_code_string_literal(entity.name)},",
        "                    id,",
        "                    "
        + _java_code_string_literal(
            f"Outbound SOAP canonical invocation failed for contract '{ctx.contract.name}' "
            f"operation '{ctx.operation_name}'."
        )
        + ");",
        "        }",
        "    }",
        "",
    ]
    lines.extend(
        _outbound_soap_request_builder_lines(
            ctx=ctx,
            method_name=request_builder,
        )
    )
    lines.extend(
        _outbound_soap_response_extractor_lines(
            ctx=ctx,
            method_name=response_extractor,
        )
    )
    return lines


def _outbound_soap_request_builder_lines(
    *,
    ctx: _OutboundSoapActionContext,
    method_name: str,
) -> list[str]:
    namespace = str(ctx.soap_contract.get("target_namespace") or "")
    input_root = _soap_qname_local(str(ctx.operation.get("input_element") or ctx.operation_name))
    input_fields = _soap_fields_by_path(ctx.operation.get("input_fields") or [])
    input_field_order = [str(field.get("path") or "") for field in ctx.operation.get("input_fields") or []]
    request_mappings_by_target = {
        str(mapping["target_path"]): mapping
        for mapping in ctx.canonical_operation.get("request_mappings") or []
    }
    fields_by_name = {field.name: field for field in ctx.entity.fields}
    ordered_request_mappings = [
        (target_path, request_mappings_by_target[target_path])
        for target_path in input_field_order
        if target_path in request_mappings_by_target
    ]
    lines = [
        f"    private Source {method_name}({ctx.entity.name} record) throws Exception {{",
        "        Document document = documentBuilder().newDocument();",
        f"        Element root = createElement(document, {_java_code_string_literal(namespace)}, {_java_code_string_literal(input_root)});",
        "        document.appendChild(root);",
    ]
    for index, (target_path, mapping) in enumerate(ordered_request_mappings):
        source = str(mapping["source"])
        _entity_name, field_name = source.split(".", 1)
        canonical_field = fields_by_name[field_name]
        target_field = input_fields[target_path]
        value_var = f"{to_java_method_name(field_name, fallback='field')}Value{index}"
        getter = f"record.get{to_pascal_case(canonical_field.name)}()"
        lines.append(f"        {_java_type(canonical_field)} {value_var} = {getter};")
        lines.append(f"        if ({value_var} == null) {{")
        if bool(target_field.get("required")):
            lines.append(
                "            throw new OutboundSoapActionException("
                "HttpStatus.BAD_REQUEST, "
                + _java_code_string_literal(
                    f"Canonical field '{source}' is required for SOAP request field "
                    f"'{target_path}' but is null."
                )
                + ");"
            )
        lines.append("        } else {")
        formatted = _soap_format_expression(canonical_field, value_var)
        terminal = _soap_path_terminal(target_path)
        if str(target_field.get("kind") or "element") == "attribute":
            lines.append(
                f"            root.setAttribute({_java_code_string_literal(terminal[1:])}, {formatted});"
            )
        else:
            lines.append(
                f"            appendElement(document, root, {_java_code_string_literal(namespace)}, "
                f"{_java_code_string_literal(terminal)}, {formatted});"
            )
        lines.append("        }")
    lines.extend(
        [
            "        return new DOMSource(document);",
            "    }",
            "",
        ]
    )
    return lines


def _outbound_soap_response_extractor_lines(
    *,
    ctx: _OutboundSoapActionContext,
    method_name: str,
) -> list[str]:
    output_fields = _soap_fields_by_path(ctx.operation.get("output_fields") or [])
    response_mappings = (
        (ctx.canonical_operation.get("response") or {}).get("response_mappings") or []
    )
    lines = [
        f"    private Map<String, String> {method_name}(Source responsePayload) throws Exception {{",
        "        Document document = toDocument(responsePayload);",
        "        Element root = document.getDocumentElement();",
        "        if (root == null) {",
        "            throw new SoapClientException("
        + _java_code_string_literal(
            f"SOAP operation '{ctx.operation_name}' response payload is empty."
        )
        + ");",
        "        }",
        "        Map<String, String> response = new LinkedHashMap<>();",
    ]
    for index, mapping in enumerate(response_mappings):
        source_path = str(mapping["source_path"])
        target = str(mapping["target"])
        output_field = output_fields[source_path]
        value_var = f"{to_java_method_name(target, fallback='responseValue')}Value{index}"
        lines.append(
            f"        String {value_var} = valueAt(root, {_java_code_string_literal(source_path)});"
        )
        if bool(output_field.get("required")):
            lines.extend(
                [
                    f"        if ({value_var} == null) {{",
                    "            throw new SoapClientException("
                    + _java_code_string_literal(
                        f"SOAP operation '{ctx.operation_name}' response field "
                        f"'{source_path}' is required but missing."
                    )
                    + ");",
                    "        }",
                ]
            )
        lines.append(
            f"        response.put({_java_code_string_literal(target)}, {value_var});"
        )
    lines.extend(
        [
            "        return response;",
            "    }",
            "",
        ]
    )
    return lines


def _outbound_soap_action_common_method_lines(
    id_converter_types: set[CanonicalFieldType],
) -> list[str]:
    lines = [
        "    private ResponseEntity<OutboundSoapActionFailureResponse> soapClientFailure(",
        "            String contractName,",
        "            String operationName,",
        "            String entity,",
        "            String id,",
        "            SoapClientException ex) {",
        "        SoapFaultClientException fault = findCause(ex, SoapFaultClientException.class);",
        "        if (fault != null) {",
        "            String faultCode = fault.getFaultCode() == null ? \"SOAP Fault\" : fault.getFaultCode().toString();",
        "            String faultReason = safeMessage(fault.getFaultStringOrReason());",
        "            return failure(",
        "                    HttpStatus.BAD_GATEWAY,",
        "                    contractName,",
        "                    operationName,",
        "                    entity,",
        "                    id,",
        "                    \"Remote SOAP Fault [\" + safeMessage(faultCode) + \"]: \" + faultReason);",
        "        }",
        "        if (findCause(ex, SocketTimeoutException.class) != null) {",
        "            return failure(",
        "                    HttpStatus.GATEWAY_TIMEOUT,",
        "                    contractName,",
        "                    operationName,",
        "                    entity,",
        "                    id,",
        "                    \"Outbound SOAP service timed out for contract '\" + contractName",
        "                            + \"' operation '\" + operationName + \"'.\");",
        "        }",
        "        if (findCause(ex, WebServiceIOException.class) != null) {",
        "            return failure(",
        "                    HttpStatus.SERVICE_UNAVAILABLE,",
        "                    contractName,",
        "                    operationName,",
        "                    entity,",
        "                    id,",
        "                    \"Outbound SOAP service is unavailable for contract '\" + contractName",
        "                            + \"' operation '\" + operationName + \"'.\");",
        "        }",
        "        return failure(",
        "                HttpStatus.BAD_GATEWAY,",
        "                contractName,",
        "                operationName,",
        "                entity,",
        "                id,",
        "                \"Outbound SOAP invocation failed for contract '\" + contractName",
        "                        + \"' operation '\" + operationName + \"': \" + safeMessage(ex.getMessage()));",
        "    }",
        "",
        "    private <T extends Throwable> T findCause(Throwable throwable, Class<T> type) {",
        "        Throwable current = throwable;",
        "        while (current != null) {",
        "            if (type.isInstance(current)) {",
        "                return type.cast(current);",
        "            }",
        "            current = current.getCause();",
        "        }",
        "        return null;",
        "    }",
        "",
        "    private Document toDocument(Source source) throws Exception {",
        "        Document document = documentBuilder().newDocument();",
        "        secureTransformerFactory().newTransformer().transform(source, new DOMResult(document));",
        "        return document;",
        "    }",
        "",
        "    private void appendElement(Document document, Element parent, String namespace, String name, String value) {",
        "        Element child = createElement(document, namespace, name);",
        "        child.setTextContent(value);",
        "        parent.appendChild(child);",
        "    }",
        "",
        "    private Element createElement(Document document, String namespace, String name) {",
        "        if (namespace == null || namespace.isBlank()) {",
        "            return document.createElement(name);",
        "        }",
        "        return document.createElementNS(namespace, name);",
        "    }",
        "",
        "    private String valueAt(Element root, String xmlPath) {",
        "        String[] parts = xmlPath.split(\"/\");",
        "        if (parts.length != 3 || parts[1].isBlank() || parts[2].isBlank()) {",
        "            throw new SoapClientException(\"Unsupported outbound SOAP response path: \" + xmlPath);",
        "        }",
        "        String terminal = parts[2];",
        "        if (terminal.startsWith(\"@\")) {",
        "            String attributeName = terminal.substring(1);",
        "            return root.hasAttribute(attributeName) ? root.getAttribute(attributeName) : null;",
        "        }",
        "        NodeList nodes = root.getChildNodes();",
        "        for (int index = 0; index < nodes.getLength(); index++) {",
        "            Node node = nodes.item(index);",
        "            if (node.getNodeType() != Node.ELEMENT_NODE) {",
        "                continue;",
        "            }",
        "            Element child = (Element) node;",
        "            String localName = child.getLocalName() == null ? child.getNodeName() : child.getLocalName();",
        "            if (terminal.equals(localName)) {",
        "                return child.getTextContent();",
        "            }",
        "        }",
        "        return null;",
        "    }",
        "",
        "    private DocumentBuilder documentBuilder() throws ParserConfigurationException {",
        "        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();",
        "        factory.setNamespaceAware(true);",
        "        factory.setFeature(\"http://apache.org/xml/features/disallow-doctype-decl\", true);",
        "        factory.setFeature(\"http://xml.org/sax/features/external-general-entities\", false);",
        "        factory.setFeature(\"http://xml.org/sax/features/external-parameter-entities\", false);",
        "        factory.setFeature(\"http://apache.org/xml/features/nonvalidating/load-external-dtd\", false);",
        "        factory.setXIncludeAware(false);",
        "        factory.setExpandEntityReferences(false);",
        "        return factory.newDocumentBuilder();",
        "    }",
        "",
        "    private TransformerFactory secureTransformerFactory() throws Exception {",
        "        TransformerFactory transformerFactory = TransformerFactory.newInstance();",
        "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
        "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, \"\");",
        "        return transformerFactory;",
        "    }",
        "",
    ]
    if CanonicalFieldType.INTEGER in id_converter_types:
        lines.extend(
            [
        "    private Long asLongValue(String value, String fieldName) {",
        "        try {",
        "            return Long.valueOf(value.trim());",
        "        } catch (NumberFormatException ex) {",
        "            throw new OutboundSoapActionException(",
        "                    HttpStatus.BAD_REQUEST,",
        "                    \"Outbound SOAP invoke_by_id request field '\" + fieldName + \"' is not a valid integer.\");",
        "        }",
        "    }",
        "",
            ]
        )
    if CanonicalFieldType.DECIMAL in id_converter_types:
        lines.extend(
            [
        "    private BigDecimal asBigDecimalValue(String value, String fieldName) {",
        "        try {",
        "            return new BigDecimal(value.trim());",
        "        } catch (NumberFormatException ex) {",
        "            throw new OutboundSoapActionException(",
        "                    HttpStatus.BAD_REQUEST,",
        "                    \"Outbound SOAP invoke_by_id request field '\" + fieldName + \"' is not a valid decimal.\");",
        "        }",
        "    }",
        "",
            ]
        )
    if CanonicalFieldType.BOOLEAN in id_converter_types:
        lines.extend(
            [
        "    private Boolean asBooleanValue(String value, String fieldName) {",
        "        if (\"true\".equalsIgnoreCase(value.trim()) || \"false\".equalsIgnoreCase(value.trim())) {",
        "            return Boolean.valueOf(value.trim());",
        "        }",
        "        throw new OutboundSoapActionException(",
        "                HttpStatus.BAD_REQUEST,",
        "                \"Outbound SOAP invoke_by_id request field '\" + fieldName + \"' is not a valid boolean.\");",
        "    }",
        "",
            ]
        )
    if CanonicalFieldType.DATE in id_converter_types:
        lines.extend(
            [
        "    private LocalDate asLocalDateValue(String value, String fieldName) {",
        "        try {",
        "            return LocalDate.parse(value.trim());",
        "        } catch (DateTimeParseException ex) {",
        "            throw new OutboundSoapActionException(",
        "                    HttpStatus.BAD_REQUEST,",
        "                    \"Outbound SOAP invoke_by_id request field '\" + fieldName + \"' is not a valid date.\");",
        "        }",
        "    }",
        "",
            ]
        )
    if CanonicalFieldType.DATETIME in id_converter_types:
        lines.extend(
            [
        "    private LocalDateTime asLocalDateTimeValue(String value, String fieldName) {",
        "        try {",
        "            return LocalDateTime.parse(value.trim());",
        "        } catch (DateTimeParseException ex) {",
        "            throw new OutboundSoapActionException(",
        "                    HttpStatus.BAD_REQUEST,",
        "                    \"Outbound SOAP invoke_by_id request field '\" + fieldName + \"' is not a valid dateTime.\");",
        "        }",
        "    }",
        "",
            ]
        )
    lines.extend(
        [
        "    private String safeMessage(String message) {",
        "        if (message == null || message.isBlank()) {",
        "            return \"No additional detail.\";",
        "        }",
        "        return message.replaceAll(\"[\\\\r\\\\n\\\\t]+\", \" \").trim();",
        "    }",
        "",
        ]
    )
    return lines


def _outbound_soap_id_conversion_expression(field: CanonicalField, raw_value: str) -> str:
    if field.type == CanonicalFieldType.INTEGER:
        return f"asLongValue({raw_value}, \"id\")"
    if field.type == CanonicalFieldType.DECIMAL:
        return f"asBigDecimalValue({raw_value}, \"id\")"
    if field.type == CanonicalFieldType.BOOLEAN:
        return f"asBooleanValue({raw_value}, \"id\")"
    if field.type == CanonicalFieldType.DATE:
        return f"asLocalDateValue({raw_value}, \"id\")"
    if field.type == CanonicalFieldType.DATETIME:
        return f"asLocalDateTimeValue({raw_value}, \"id\")"
    return raw_value


def _render_soap_canonical_handler(
    *,
    metadata: MetadataProject,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    soap_contract = _require_soap_contract(contract)
    handler_name = _soap_handler_interface_name(contract)
    canonical_handler_name = _soap_canonical_handler_class_name(contract)
    handler_methods = _soap_handler_java_methods(contract)
    operations_by_name = {
        str(operation["name"]): operation for operation in soap_contract.get("operations") or []
    }
    entities_by_name = {entity.name: entity for entity in all_entities(metadata)}
    canonical_mappings = _soap_canonical_operation_mappings(soap_contract)
    repository_entities: OrderedDict[str, CanonicalEntity] = OrderedDict()
    for _operation_name, mapping in canonical_mappings.items():
        canonical_operation = mapping["canonical_operation"]
        entity = entities_by_name[str(canonical_operation["entity"])]
        repository_entities[entity.name] = entity
    fields: list[str] = []
    constructor_params: list[str] = []
    assignments: list[str] = []
    for entity in repository_entities.values():
        repository_class = f"{entity.name}Repository"
        repository_var = _repository_var_name(entity)
        fields.append(f"    private final {repository_class} {repository_var};")
        constructor_params.append(f"            {repository_class} {repository_var}")
        assignments.append(f"        this.{repository_var} = {repository_var};")
    xsd_resources = _soap_xsd_resource_paths(contract, source_manifest=source_manifest)
    body = [
        "@Component",
        f"public class {canonical_handler_name} implements {handler_name} {{",
        f"    private static final String NAMESPACE = {_java_code_string_literal(str(soap_contract.get('target_namespace') or ''))};",
        "    private static final String[] XSD_RESOURCES = new String[] {",
        *[f"        {_java_code_string_literal(resource)}," for resource in xsd_resources],
        "    };",
        "",
        *fields,
        "",
    ]
    if constructor_params:
        body.extend(
            [
                f"    public {canonical_handler_name}(",
                ",\n".join(constructor_params),
                "    ) {",
                *assignments,
                "    }",
                "",
            ]
        )
    else:
        body.extend([f"    public {canonical_handler_name}() {{", "    }", ""])
    for operation in soap_contract.get("operations") or []:
        operation_name = str(operation["name"])
        handler_method = handler_methods[operation_name]
        mapping = canonical_mappings.get(operation_name)
        body.append("    @Override")
        body.append(f"    public Source {handler_method}(Source requestPayload) throws Exception {{")
        if mapping is None:
            body.extend(
                [
                    "        throw new SoapOperationMappingException("
                    + _java_code_string_literal(
                        f"SOAP operation '{operation_name}' is configured as adapter-only. "
                        f"Generated canonical handler '{canonical_handler_name}' has no canonical "
                        "operation mapping for it. Provide a custom handler bean if this operation "
                        "should execute business logic."
                    )
                    + ");",
                    "    }",
                    "",
                ]
            )
            continue
        canonical_operation = mapping["canonical_operation"]
        entity = entities_by_name[str(canonical_operation["entity"])]
        id_field = entity_id_field(entity)
        repository_var = _repository_var_name(entity)
        lookup = canonical_operation["lookup"]
        request_path = str(lookup["request_path"])
        id_var = to_java_method_name(id_field.name, fallback="recordId")
        raw_var = f"{id_var}Raw"
        body.extend(
            [
                "        Document requestDocument = toDocument(requestPayload);",
                f"        String {raw_var} = requiredText(requestDocument, {_java_code_string_literal(request_path)});",
                f"        {_java_type(id_field)} {id_var} = {_soap_lookup_conversion_expression(id_field, raw_var, request_path)};",
                f"        {entity.name} record = {repository_var}.findById({id_var})",
                "            .orElseThrow(() -> new SoapOperationMappingException("
                + _java_code_string_literal(_soap_not_found_message(operation_name, canonical_operation))
                + " + "
                + id_var
                + "));",
                f"        return build{to_pascal_case(operation_name)}Response(record);",
                "    }",
                "",
            ]
        )
        body.extend(
            _soap_response_builder_lines(
                entity=entity,
                operation=operations_by_name[operation_name],
                canonical_operation=canonical_operation,
            )
        )
    body.extend(
        [
            "    private Document toDocument(Source source) throws Exception {",
            "        Document document = documentBuilder().newDocument();",
            "        secureTransformerFactory().newTransformer().transform(source, new DOMResult(document));",
            "        return document;",
            "    }",
            "",
            "    private String requiredText(Document document, String xmlPath) {",
            "        Element root = document.getDocumentElement();",
            "        if (root == null) {",
            "            throw new SoapOperationMappingException(\"SOAP canonical request payload is empty.\");",
            "        }",
            "        String value = valueAt(root, xmlPath);",
            "        if (value == null || value.isBlank()) {",
            "            throw new SoapOperationMappingException(\"SOAP canonical request missing required value at \" + xmlPath + \".\");",
            "        }",
            "        return value;",
            "    }",
            "",
            "    private String valueAt(Element root, String xmlPath) {",
            "        String[] parts = xmlPath.split(\"/\");",
            "        if (parts.length != 3 || parts[1].isBlank() || parts[2].isBlank()) {",
            "            throw new SoapOperationMappingException(\"Unsupported SOAP canonical path: \" + xmlPath);",
            "        }",
            "        String terminal = parts[2];",
            "        if (terminal.startsWith(\"@\")) {",
            "            String attributeName = terminal.substring(1);",
            "            return root.hasAttribute(attributeName) ? root.getAttribute(attributeName) : null;",
            "        }",
            "        NodeList nodes = root.getChildNodes();",
            "        for (int index = 0; index < nodes.getLength(); index++) {",
            "            Node node = nodes.item(index);",
            "            if (node.getNodeType() != Node.ELEMENT_NODE) {",
            "                continue;",
            "            }",
            "            Element child = (Element) node;",
            "            String localName = child.getLocalName() == null ? child.getNodeName() : child.getLocalName();",
            "            if (terminal.equals(localName)) {",
            "                return child.getTextContent();",
            "            }",
            "        }",
            "        return null;",
            "    }",
            "",
            "    private void appendElement(Document document, Element parent, String name, String value) {",
            "        Element child = createElement(document, name);",
            "        child.setTextContent(value);",
            "        parent.appendChild(child);",
            "    }",
            "",
            "    private Element createElement(Document document, String name) {",
            "        if (NAMESPACE.isBlank()) {",
            "            return document.createElement(name);",
            "        }",
            "        return document.createElementNS(NAMESPACE, name);",
            "    }",
            "",
            "    private void validateResponse(Document document) throws Exception {",
            "        loadSchema().newValidator().validate(new DOMSource(document));",
            "    }",
            "",
            "    private Schema loadSchema() throws Exception {",
            "        SchemaFactory schemaFactory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, \"file,jar\");",
            "        List<Source> schemas = new ArrayList<>();",
            "        for (String xsdResource : XSD_RESOURCES) {",
            "            URL resource = getClass().getResource(xsdResource);",
            "            if (resource == null) {",
            "                throw new IllegalStateException(\"Missing SOAP/WSDL XSD resource: \" + xsdResource);",
            "            }",
            "            schemas.add(new StreamSource(resource.toExternalForm()));",
            "        }",
            "        return schemaFactory.newSchema(schemas.toArray(new Source[0]));",
            "    }",
            "",
            "    private DocumentBuilder documentBuilder() throws ParserConfigurationException {",
            "        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();",
            "        factory.setNamespaceAware(true);",
            "        factory.setFeature(\"http://apache.org/xml/features/disallow-doctype-decl\", true);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-general-entities\", false);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-parameter-entities\", false);",
            "        factory.setFeature(\"http://apache.org/xml/features/nonvalidating/load-external-dtd\", false);",
            "        factory.setXIncludeAware(false);",
            "        factory.setExpandEntityReferences(false);",
            "        return factory.newDocumentBuilder();",
            "    }",
            "",
            "    private TransformerFactory secureTransformerFactory() throws Exception {",
            "        TransformerFactory transformerFactory = TransformerFactory.newInstance();",
            "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, \"\");",
            "        return transformerFactory;",
            "    }",
            "",
            "    private Long asLongValue(String value, String xmlPath) {",
            "        try {",
            "            return Long.valueOf(value.trim());",
            "        } catch (NumberFormatException ex) {",
            "            throw new SoapOperationMappingException(\"SOAP canonical request value at \" + xmlPath + \" is not a valid integer.\");",
            "        }",
            "    }",
            "",
            "    private BigDecimal asBigDecimalValue(String value, String xmlPath) {",
            "        try {",
            "            return new BigDecimal(value.trim());",
            "        } catch (NumberFormatException ex) {",
            "            throw new SoapOperationMappingException(\"SOAP canonical request value at \" + xmlPath + \" is not a valid decimal.\");",
            "        }",
            "    }",
            "",
            "    private Boolean asBooleanValue(String value, String xmlPath) {",
            "        if (\"true\".equalsIgnoreCase(value.trim()) || \"false\".equalsIgnoreCase(value.trim())) {",
            "            return Boolean.valueOf(value.trim());",
            "        }",
            "        throw new SoapOperationMappingException(\"SOAP canonical request value at \" + xmlPath + \" is not a valid boolean.\");",
            "    }",
            "",
            "    private LocalDate asLocalDateValue(String value, String xmlPath) {",
            "        try {",
            "            return LocalDate.parse(value.trim());",
            "        } catch (DateTimeParseException ex) {",
            "            throw new SoapOperationMappingException(\"SOAP canonical request value at \" + xmlPath + \" is not a valid date.\");",
            "        }",
            "    }",
            "",
            "    private LocalDateTime asLocalDateTimeValue(String value, String xmlPath) {",
            "        try {",
            "            return LocalDateTime.parse(value.trim());",
            "        } catch (DateTimeParseException ex) {",
            "            throw new SoapOperationMappingException(\"SOAP canonical request value at \" + xmlPath + \" is not a valid dateTime.\");",
            "        }",
            "    }",
            "}",
        ]
    )
    imports = [
        f"{root_package}.exception.SoapOperationMappingException",
        f"{root_package}.adapter.soap.{handler_name}",
        "java.math.BigDecimal",
        "java.net.URL",
        "java.time.LocalDate",
        "java.time.LocalDateTime",
        "java.time.format.DateTimeParseException",
        "java.util.ArrayList",
        "java.util.List",
        "javax.xml.XMLConstants",
        "javax.xml.parsers.DocumentBuilder",
        "javax.xml.parsers.DocumentBuilderFactory",
        "javax.xml.parsers.ParserConfigurationException",
        "javax.xml.transform.Source",
        "javax.xml.transform.TransformerFactory",
        "javax.xml.transform.dom.DOMResult",
        "javax.xml.transform.dom.DOMSource",
        "javax.xml.transform.stream.StreamSource",
        "javax.xml.validation.Schema",
        "javax.xml.validation.SchemaFactory",
        "org.springframework.stereotype.Component",
        "org.w3c.dom.Document",
        "org.w3c.dom.Element",
        "org.w3c.dom.Node",
        "org.w3c.dom.NodeList",
    ]
    for entity in repository_entities.values():
        imports.append(f"{root_package}.domain.{entity.name}")
        imports.append(f"{root_package}.repository.{entity.name}Repository")
    return _java_file(
        package_name=f"{root_package}.adapter.soap",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _soap_response_builder_lines(
    *,
    entity: CanonicalEntity,
    operation: dict,
    canonical_operation: dict,
) -> list[str]:
    output_root = _soap_qname_local(str(operation.get("output_element") or operation.get("name") or "Response"))
    output_fields = _soap_fields_by_path(operation.get("output_fields") or [])
    output_field_order = [str(field.get("path") or "") for field in operation.get("output_fields") or []]
    response_mappings_by_target = {
        str(mapping["target_path"]): mapping
        for mapping in canonical_operation.get("response_mappings") or []
    }
    fields_by_name = {field.name: field for field in entity.fields}
    method_name = f"build{to_pascal_case(str(operation['name']))}Response"
    lines = [
        f"    private Source {method_name}({entity.name} record) throws Exception {{",
        "        Document document = documentBuilder().newDocument();",
        f"        Element root = createElement(document, {_java_code_string_literal(output_root)});",
        "        document.appendChild(root);",
    ]
    ordered_response_mappings = [
        (target_path, response_mappings_by_target[target_path])
        for target_path in output_field_order
        if target_path in response_mappings_by_target
    ]
    for index, (target_path, mapping) in enumerate(ordered_response_mappings):
        source = str(mapping["source"])
        _entity_name, field_name = source.split(".", 1)
        canonical_field = fields_by_name[field_name]
        target_field = output_fields[target_path]
        value_var = f"{to_java_method_name(field_name, fallback='field')}Value{index}"
        getter = f"record.get{to_pascal_case(canonical_field.name)}()"
        lines.append(f"        {_java_type(canonical_field)} {value_var} = {getter};")
        lines.append(f"        if ({value_var} == null) {{")
        if bool(target_field.get("required")):
            lines.append(
                "            throw new SoapOperationMappingException("
                + _java_code_string_literal(f"SOAP canonical response field '{target_path}' is required but null.")
                + ");"
            )
        lines.extend(["        } else {"])
        formatted = _soap_format_expression(canonical_field, value_var)
        if str(target_field.get("kind") or "element") == "attribute":
            attribute_name = _soap_path_terminal(target_path)[1:]
            lines.append(
                f"            root.setAttribute({_java_code_string_literal(attribute_name)}, {formatted});"
            )
        else:
            lines.append(
                f"            appendElement(document, root, {_java_code_string_literal(_soap_path_terminal(target_path))}, {formatted});"
            )
        lines.extend(["        }"])
    lines.extend(
        [
            "        validateResponse(document);",
            "        return new DOMSource(document);",
            "    }",
            "",
        ]
    )
    return lines


def _render_soap_handler_interface(
    *,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    soap_contract = _require_soap_contract(contract)
    handler_name = _soap_handler_interface_name(contract)
    handler_methods = _soap_handler_java_methods(contract)
    body = [
        f"public interface {handler_name} {{",
    ]
    for operation in soap_contract.get("operations") or []:
        operation_name = str(operation["name"])
        method_name = handler_methods[operation_name]
        body.extend(
            [
                f"    Source {method_name}(Source requestPayload) throws Exception;",
                "",
            ]
        )
    body.append("}")
    return _java_file(
        package_name=f"{root_package}.adapter.soap",
        imports=["javax.xml.transform.Source"],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_soap_endpoint(
    *,
    contract: ContractMetadata,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    soap_contract = _require_soap_contract(contract)
    endpoint_name = _soap_endpoint_class_name(contract)
    handler_name = _soap_handler_interface_name(contract)
    endpoint_methods = _soap_endpoint_java_methods(soap_contract)
    handler_methods = _soap_handler_java_methods(contract)
    namespace = str(soap_contract.get("target_namespace") or "")
    xsd_resources = _soap_xsd_resource_paths(contract, source_manifest=source_manifest)
    if not xsd_resources:
        raise ValueError(
            f"Inbound SOAP/WSDL interface '{contract.name}' has no packaged XSD resources "
            "available for payload validation."
        )
    body = [
        "@Endpoint",
        f"public class {endpoint_name} {{",
        f"    private static final String NAMESPACE = {_java_code_string_literal(namespace)};",
        "    private static final String[] XSD_RESOURCES = new String[] {",
        *[f"        {_java_code_string_literal(resource)}," for resource in xsd_resources],
        "    };",
        "",
        f"    private final ObjectProvider<{handler_name}> handlerProvider;",
        "",
        f"    public {endpoint_name}(ObjectProvider<{handler_name}> handlerProvider) {{",
        "        this.handlerProvider = handlerProvider;",
        "    }",
        "",
    ]
    for operation in soap_contract.get("operations") or []:
        operation_name = str(operation["name"])
        operation_method = endpoint_methods[operation_name]
        input_local = _soap_qname_local(str(operation.get("input_element") or operation_name))
        soap_action = operation.get("soap_action")
        handler_method = handler_methods[operation_name]
        body.extend(
            [
                f"    @PayloadRoot(namespace = NAMESPACE, localPart = {_java_code_string_literal(input_local)})",
            ]
        )
        if soap_action:
            body.append(f"    @SoapAction({_java_code_string_literal(str(soap_action))})")
        body.extend(
            [
                "    @ResponsePayload",
                f"    public Source {operation_method}(@RequestPayload Source requestPayload) throws Exception {{",
                "        Source validatedPayload = validatePayload(requestPayload);",
                f"        {handler_name} handler = handlerProvider.getIfAvailable();",
                "        if (handler == null) {",
                "            throw new SoapOperationMappingException("
                + _java_code_string_literal(
                    f"SOAP operation '{operation_name}' is configured as adapter-only. "
                    "No canonical handler implementation is generated yet. "
                    "Add an explicit SOAP canonical mapping or provide handler bean "
                    f"'{handler_name}'."
                )
                + ");",
                "        }",
                f"        return handler.{handler_method}(validatedPayload);",
                "    }",
                "",
            ]
        )
    body.extend(
        [
            "    private Source validatePayload(Source requestPayload) throws Exception {",
            "        Document document = documentBuilder().newDocument();",
            "        secureTransformerFactory().newTransformer().transform(requestPayload, new DOMResult(document));",
            "        loadSchema().newValidator().validate(new DOMSource(document));",
            "        return new DOMSource(document);",
            "    }",
            "",
            "    private Schema loadSchema() throws Exception {",
            "        SchemaFactory schemaFactory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "        schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, \"file,jar\");",
            "        List<Source> schemas = new ArrayList<>();",
            "        for (String xsdResource : XSD_RESOURCES) {",
            "            URL resource = getClass().getResource(xsdResource);",
            "            if (resource == null) {",
            "                throw new IllegalStateException(\"Missing SOAP/WSDL XSD resource: \" + xsdResource);",
            "            }",
            "            schemas.add(new StreamSource(resource.toExternalForm()));",
            "        }",
            "        return schemaFactory.newSchema(schemas.toArray(new Source[0]));",
            "    }",
            "",
            "    private DocumentBuilder documentBuilder() throws ParserConfigurationException {",
            "        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();",
            "        factory.setNamespaceAware(true);",
            "        factory.setFeature(\"http://apache.org/xml/features/disallow-doctype-decl\", true);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-general-entities\", false);",
            "        factory.setFeature(\"http://xml.org/sax/features/external-parameter-entities\", false);",
            "        factory.setFeature(\"http://apache.org/xml/features/nonvalidating/load-external-dtd\", false);",
            "        factory.setXIncludeAware(false);",
            "        factory.setExpandEntityReferences(false);",
            "        return factory.newDocumentBuilder();",
            "    }",
            "",
            "    private TransformerFactory secureTransformerFactory() throws Exception {",
            "        TransformerFactory transformerFactory = TransformerFactory.newInstance();",
            "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, \"\");",
            "        transformerFactory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, \"\");",
            "        return transformerFactory;",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{root_package}.adapter.soap",
        imports=[
            f"{root_package}.exception.SoapOperationMappingException",
            "java.net.URL",
            "java.util.ArrayList",
            "java.util.List",
            "javax.xml.XMLConstants",
            "javax.xml.parsers.DocumentBuilder",
            "javax.xml.parsers.DocumentBuilderFactory",
            "javax.xml.parsers.ParserConfigurationException",
            "javax.xml.transform.Source",
            "javax.xml.transform.TransformerFactory",
            "javax.xml.transform.dom.DOMResult",
            "javax.xml.transform.dom.DOMSource",
            "javax.xml.transform.stream.StreamSource",
            "javax.xml.validation.Schema",
            "javax.xml.validation.SchemaFactory",
            "org.springframework.beans.factory.ObjectProvider",
            "org.springframework.ws.server.endpoint.annotation.Endpoint",
            "org.springframework.ws.server.endpoint.annotation.PayloadRoot",
            "org.springframework.ws.server.endpoint.annotation.RequestPayload",
            "org.springframework.ws.server.endpoint.annotation.ResponsePayload",
            "org.springframework.ws.soap.server.endpoint.annotation.SoapAction",
            "org.w3c.dom.Document",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _emit_xml_contract_sample_test(
    *,
    contract: ContractMetadata,
    test_root: Path,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
    output_dir: Path,
) -> list[Path]:
    copied_samples = _copy_xml_contract_sample_resources(
        contract=contract,
        output_dir=output_dir,
        source_manifest=source_manifest,
    )
    if not copied_samples:
        return []
    sample_resource = f"/xml-contract-samples/{_xml_resource_dir_name(contract.name)}/{copied_samples[0].name}"
    test_class = f"{_xml_model_class_name(contract)}AdapterTest"
    model_class = _xml_model_class_name(contract)
    parser_class = _xml_parser_class_name(contract)
    serializer_class = _xml_serializer_class_name(contract)
    body = [
        f"class {test_class} {{",
        "",
        "    @Test",
        "    void parsesSampleAndSerializesValidXml() throws Exception {",
        f"        URL sample = getClass().getResource({_java_code_string_literal(sample_resource)});",
        "        assertNotNull(sample);",
        f"        {parser_class} parser = new {parser_class}();",
        f"        {model_class} model = parser.parse(Path.of(sample.toURI()));",
        "        assertNotNull(model);",
        f"        {serializer_class} serializer = new {serializer_class}();",
        "        String xml = serializer.serialize(model);",
        "        assertNotNull(xml);",
        "        assertFalse(xml.isBlank());",
        "    }",
        "}",
    ]
    return [
        *copied_samples,
        _write_java_file(
            test_root / "adapter" / "xml" / f"{test_class}.java",
            _java_file(
                package_name=f"{root_package}.adapter.xml",
                imports=[
                    "java.net.URL",
                    "java.nio.file.Path",
                    "org.junit.jupiter.api.Test",
                    "static org.junit.jupiter.api.Assertions.assertFalse",
                    "static org.junit.jupiter.api.Assertions.assertNotNull",
                ],
                body=body,
                source_manifest=source_manifest,
                target_profile=target_profile.name,
                generation_run_id=generation_run_id,
            ),
        )
    ]


def _copy_xml_contract_resources(
    *,
    contract: ContractMetadata,
    output_dir: Path,
    source_manifest: str,
) -> list[Path]:
    manifest_path = Path(source_manifest)
    if not manifest_path.exists():
        return []
    xml_contract = _require_xml_contract(contract)
    xsd_reference = str(xml_contract.get("xsd_path") or contract.source or "")
    if not xsd_reference:
        return []
    project_root = manifest_path.parent
    resource_dir = output_dir / "src" / "main" / "resources" / "xml-contracts" / _xml_resource_dir_name(contract.name)
    written: list[Path] = []
    parse_budget = XmlParseBudget()
    xsd_paths = list(xml_contract.get("xsd_paths") or [xsd_reference])
    for xsd_path in xsd_paths:
        relative = Path(str(xsd_path))
        if relative.is_absolute():
            continue
        source_path = project_root / relative
        if not source_path.exists():
            continue
        data, _root = _read_generation_xml(
            source_path,
            purpose=f"XML/XSD interface '{contract.name}' generation resource '{relative}'",
            budget=parse_budget,
        )
        target_path = resource_dir / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)
        written.append(target_path)
    return written


def _copy_soap_contract_resources(
    *,
    contract: ContractMetadata,
    output_dir: Path,
    source_manifest: str,
    rewrite_endpoint_address: bool,
) -> list[Path]:
    manifest_path = Path(source_manifest)
    if not manifest_path.exists():
        return []
    soap_contract = _require_soap_contract(contract)
    wsdl_reference = str(soap_contract.get("wsdl_path") or contract.source or "")
    if not wsdl_reference:
        return []
    project_root = manifest_path.parent
    wsdl_relative = Path(wsdl_reference)
    if wsdl_relative.is_absolute():
        return []
    source_wsdl = project_root / wsdl_relative
    if not source_wsdl.exists():
        return []
    parse_budget = XmlParseBudget()
    wsdl_data, root = _read_generation_xml(
        source_wsdl,
        purpose=f"SOAP/WSDL interface '{contract.name}' generation WSDL '{wsdl_relative}'",
        budget=parse_budget,
    )
    namespace_map = _soap_namespace_map(wsdl_data)

    resource_dir = output_dir / "src" / "main" / "resources" / "soap-contracts" / _xml_resource_dir_name(contract.name)
    written: list[Path] = []
    target_wsdl = resource_dir / wsdl_relative
    target_wsdl.parent.mkdir(parents=True, exist_ok=True)
    if rewrite_endpoint_address:
        target_wsdl.write_bytes(
            _soap_wsdl_bytes_with_endpoint_address(
                source_text=wsdl_data.decode("utf-8"),
                namespace_map=namespace_map,
                endpoint_url="http://localhost:8080/ws",
            )
        )
    else:
        target_wsdl.write_bytes(wsdl_data)
    written.append(target_wsdl)

    for index, schema in enumerate(_soap_embedded_schemas(root), start=1):
        target_schema = resource_dir / _soap_xsd_resource_relative_path(wsdl_relative, index)
        target_schema.parent.mkdir(parents=True, exist_ok=True)
        target_schema.write_bytes(_soap_schema_bytes(schema, namespace_map))
        written.append(target_schema)
        written.extend(
            _copy_soap_schema_includes(
                schema=schema,
                source_base=source_wsdl.parent,
                target_base=target_schema.parent,
                project_root=project_root,
                parse_budget=parse_budget,
            )
        )
    return written


def _copy_soap_schema_includes(
    *,
    schema: ET.Element,
    source_base: Path,
    target_base: Path,
    project_root: Path,
    parse_budget: XmlParseBudget,
    visited: set[Path] | None = None,
) -> list[Path]:
    written: list[Path] = []
    visited = visited or set()
    for include in schema.findall("{http://www.w3.org/2001/XMLSchema}include"):
        location = include.attrib.get("schemaLocation")
        if not location:
            continue
        source_path = (source_base / location).resolve()
        try:
            source_path.relative_to(project_root.resolve())
        except ValueError:
            continue
        if source_path in visited or not source_path.exists():
            continue
        visited.add(source_path)
        data, nested = _read_generation_xml(
            source_path,
            purpose=f"SOAP/WSDL generation included XSD '{source_path.name}'",
            budget=parse_budget,
        )
        target_path = target_base / location
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)
        written.append(target_path)
        written.extend(
            _copy_soap_schema_includes(
                schema=nested,
                source_base=source_path.parent,
                target_base=target_path.parent,
                project_root=project_root,
                parse_budget=parse_budget,
                visited=visited,
            )
        )
    return written


def _copy_xml_contract_sample_resources(
    *,
    contract: ContractMetadata,
    output_dir: Path,
    source_manifest: str,
) -> list[Path]:
    manifest_path = Path(source_manifest)
    if not manifest_path.exists():
        return []
    project_root = manifest_path.parent
    sample_dir = output_dir / "src" / "test" / "resources" / "xml-contract-samples" / _xml_resource_dir_name(contract.name)
    written: list[Path] = []
    for sample_path in contract.sample_paths:
        source_sample = project_root / sample_path
        if not source_sample.exists():
            continue
        target_path = sample_dir / source_sample.name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_sample, target_path)
        written.append(target_path)
    return written


def _xml_parse_element_value_lines(
    field: dict,
    element_var: str,
    value_var: str,
    xml_path: str,
) -> list[str]:
    java_type = _xml_external_java_type(field)
    lines = [
        f"            {java_type} {value_var};",
        f"            if (isNil({element_var})) {{",
    ]
    if bool(field.get("nillable")):
        lines.append(f"                {value_var} = null;")
    else:
        lines.append(
            f"                throw parseError({_java_code_string_literal(xml_path)}, "
            + _java_code_string_literal("xsi:nil is not allowed")
            + ");"
        )
    lines.extend(
        [
            "            } else {",
            f"                String rawValue = {element_var}.getTextContent();",
            f"                {value_var} = {_xml_parse_expression(field, 'rawValue', xml_path)};",
            "            }",
        ]
    )
    return lines


def _xml_parse_expression(field: dict, raw_value_expression: str, xml_path: str | None = None) -> str:
    field_name = str(xml_path or field["name"])
    required = "true" if bool(field.get("required")) else "false"
    if field.get("enum_values"):
        enum_name = _xml_enum_class_name(field)
        return (
            f"{_xml_model_class_name_placeholder()}.{enum_name}.fromWireValue("
            f"parseString({_java_code_string_literal(field_name)}, {raw_value_expression}, {required}))"
        )
    field_type = str(field.get("type") or "string").lower()
    if field_type == "string":
        return f"parseString({_java_code_string_literal(field_name)}, {raw_value_expression}, {required})"
    if field_type in {"integer", "int", "long"}:
        return f"parseLong({_java_code_string_literal(field_name)}, {raw_value_expression}, {required})"
    if field_type == "decimal":
        return f"parseDecimal({_java_code_string_literal(field_name)}, {raw_value_expression}, {required})"
    if field_type == "boolean":
        return f"parseBoolean({_java_code_string_literal(field_name)}, {raw_value_expression}, {required})"
    if field_type == "date":
        return f"parseDate({_java_code_string_literal(field_name)}, {raw_value_expression}, {required})"
    if field_type == "datetime":
        return f"parseDateTime({_java_code_string_literal(field_name)}, {raw_value_expression}, {required})"
    return f"parseString({_java_code_string_literal(field_name)}, {raw_value_expression}, {required})"


def _xml_runtime_field_path(root_element: str, field: dict) -> str:
    field_name = str(field["name"])
    if str(field.get("kind") or "") == "attribute":
        return f"/{root_element}/@{field_name}"
    return f"/{root_element}/{field_name}"


def _xml_parse_helper_methods() -> list[str]:
    return [
        "    private String parseString(String fieldName, String rawValue, boolean required) {",
        "        if (rawValue == null) {",
        "            if (required) {",
        "                throw parseError(fieldName, \"required value is missing\");",
        "            }",
        "            return null;",
        "        }",
        "        return rawValue;",
        "    }",
        "",
        "    private Long parseLong(String fieldName, String rawValue, boolean required) {",
        "        String value = parseString(fieldName, rawValue, required);",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        try {",
        "            return Long.valueOf(value.trim());",
        "        } catch (RuntimeException ex) {",
        "            throw parseError(fieldName, \"invalid integer value\");",
        "        }",
        "    }",
        "",
        "    private BigDecimal parseDecimal(String fieldName, String rawValue, boolean required) {",
        "        String value = parseString(fieldName, rawValue, required);",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        try {",
        "            return new BigDecimal(value.trim());",
        "        } catch (RuntimeException ex) {",
        "            throw parseError(fieldName, \"invalid decimal value\");",
        "        }",
        "    }",
        "",
        "    private Boolean parseBoolean(String fieldName, String rawValue, boolean required) {",
        "        String value = parseString(fieldName, rawValue, required);",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        String trimmed = value.trim();",
        "        if (\"true\".equals(trimmed) || \"1\".equals(trimmed)) {",
        "            return Boolean.TRUE;",
        "        }",
        "        if (\"false\".equals(trimmed) || \"0\".equals(trimmed)) {",
        "            return Boolean.FALSE;",
        "        }",
        "        throw parseError(fieldName, \"invalid boolean value\");",
        "    }",
        "",
        "    private LocalDate parseDate(String fieldName, String rawValue, boolean required) {",
        "        String value = parseString(fieldName, rawValue, required);",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        try {",
        "            return LocalDate.parse(value.trim());",
        "        } catch (RuntimeException ex) {",
        "            throw parseError(fieldName, \"invalid date value\");",
        "        }",
        "    }",
        "",
        "    private OffsetDateTime parseDateTime(String fieldName, String rawValue, boolean required) {",
        "        String value = parseString(fieldName, rawValue, required);",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        try {",
        "            return OffsetDateTime.parse(value.trim());",
        "        } catch (RuntimeException ex) {",
        "            throw parseError(fieldName, \"invalid datetime value\");",
        "        }",
        "    }",
    ]


def _xml_format_expression(field: dict, value_expression: str) -> str:
    if field.get("enum_values"):
        return f"{value_expression}.wireValue()"
    field_type = str(field.get("type") or "string").lower()
    if field_type == "decimal":
        return f"{value_expression}.toPlainString()"
    if field_type == "date":
        return f"{value_expression}.format(DateTimeFormatter.ISO_LOCAL_DATE)"
    if field_type == "datetime":
        return f"{value_expression}.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)"
    return f"String.valueOf({value_expression})"


def _xml_model_imports(fields: list[dict]) -> list[str]:
    imports: list[str] = []
    if any(_xml_java_type(field) == "BigDecimal" for field in fields):
        imports.append("java.math.BigDecimal")
    if any(_xml_java_type(field) == "LocalDate" for field in fields):
        imports.append("java.time.LocalDate")
    if any(_xml_java_type(field) == "OffsetDateTime" for field in fields):
        imports.append("java.time.OffsetDateTime")
    if any(bool(field.get("repeated")) for field in fields):
        imports.extend(["java.util.ArrayList", "java.util.List"])
    return imports


def _xml_java_type(field: dict) -> str:
    if field.get("enum_values"):
        return _xml_enum_class_name(field)
    field_type = str(field.get("type") or "string").lower()
    if field_type in {"integer", "int", "long"}:
        return "Long"
    if field_type == "decimal":
        return "BigDecimal"
    if field_type == "boolean":
        return "Boolean"
    if field_type == "date":
        return "LocalDate"
    if field_type == "datetime":
        return "OffsetDateTime"
    return "String"


def _xml_external_java_type(field: dict) -> str:
    if field.get("enum_values"):
        return f"{_xml_model_class_name_placeholder()}.{_xml_enum_class_name(field)}"
    return _xml_java_type(field)


def _xml_all_fields(xml_contract: dict) -> list[dict]:
    return [*(xml_contract.get("attributes") or []), *(xml_contract.get("fields") or [])]


def _xml_field_descriptors(xml_contract: dict) -> tuple[list[dict], list[dict]]:
    raw_attributes = [dict(field) for field in xml_contract.get("attributes") or []]
    raw_elements = [dict(field) for field in xml_contract.get("fields") or []]
    combined = [*raw_attributes, *raw_elements]
    base_counts: dict[str, int] = {}
    for field in combined:
        base_name = _xml_java_member_base_name(field)
        base_counts[base_name] = base_counts.get(base_name, 0) + 1

    used: set[str] = set()
    for field in combined:
        base_name = _xml_java_member_base_name(field)
        if base_counts[base_name] > 1:
            suffix = "Attribute" if field.get("kind") == "attribute" else "Element"
            candidate = f"{base_name}{suffix}"
        else:
            candidate = base_name
        unique_candidate = candidate
        index = 2
        while unique_candidate in used:
            unique_candidate = f"{candidate}{index}"
            index += 1
        field["java_name"] = unique_candidate
        used.add(unique_candidate)
    return raw_attributes, raw_elements


def _xml_java_member_base_name(field: dict) -> str:
    return to_java_method_name(str(field.get("name") or ""), fallback="xmlField")


def _require_xml_contract(contract: ContractMetadata) -> dict:
    if contract.type != "xml-xsd" or not contract.xml_contract:
        raise ValueError(f"Missing XML/XSD metadata for interface '{contract.name}'.")
    return contract.xml_contract


def _require_soap_contract(contract: ContractMetadata) -> dict:
    if contract.type != "soap-wsdl" or not contract.soap_contract:
        raise ValueError(f"Missing SOAP/WSDL metadata for interface '{contract.name}'.")
    return contract.soap_contract


def _xml_contracts(metadata: MetadataProject) -> list[ContractMetadata]:
    return [contract for contract in metadata.contracts if contract.type == "xml-xsd"]


def _inbound_soap_contracts(metadata: MetadataProject) -> list[ContractMetadata]:
    return [
        contract
        for contract in metadata.contracts
        if contract.type == "soap-wsdl"
        and contract.soap_contract
        and contract.soap_contract.get("direction") == "upstream"
    ]


def _outbound_soap_contracts(metadata: MetadataProject) -> list[ContractMetadata]:
    return [
        contract
        for contract in metadata.contracts
        if contract.type == "soap-wsdl"
        and contract.soap_contract
        and contract.soap_contract.get("direction") == "downstream"
    ]


def _xml_model_class_name(contract: ContractMetadata) -> str:
    return f"{to_java_class_name(contract.name, fallback='XmlContract')}XmlModel"


def _xml_parser_class_name(contract: ContractMetadata) -> str:
    return f"{to_java_class_name(contract.name, fallback='XmlContract')}XmlParser"


def _xml_serializer_class_name(contract: ContractMetadata) -> str:
    return f"{to_java_class_name(contract.name, fallback='XmlContract')}XmlSerializer"


def _xml_enum_class_name(field: dict) -> str:
    return f"{to_pascal_case(str(field.get('java_name') or field['name']))}Value"


def _xml_enum_constant(value: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]", "_", value).upper()
    if not candidate:
        candidate = "VALUE"
    if candidate[0].isdigit():
        candidate = f"_{candidate}"
    return candidate


def _xml_resource_dir_name(contract_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", contract_name).strip("-") or "xml-contract"


def _xml_xsd_resource_path(contract: ContractMetadata) -> str:
    xml_contract = _require_xml_contract(contract)
    xsd_reference = Path(str(xml_contract.get("xsd_path") or contract.source or "contract.xsd"))
    return f"/xml-contracts/{_xml_resource_dir_name(contract.name)}/{xsd_reference.as_posix()}"


def _xml_model_class_name_placeholder() -> str:
    return "__XML_MODEL_CLASS__"


def _soap_endpoint_class_name(contract: ContractMetadata) -> str:
    return f"{to_java_class_name(contract.name, fallback='SoapContract')}SoapEndpoint"


def _soap_handler_interface_name(contract: ContractMetadata) -> str:
    return f"{to_java_class_name(contract.name, fallback='SoapContract')}SoapHandler"


def _soap_canonical_handler_class_name(contract: ContractMetadata) -> str:
    return f"{to_java_class_name(contract.name, fallback='SoapContract')}CanonicalSoapHandler"


def _soap_client_class_name(contract: ContractMetadata) -> str:
    return f"{to_java_class_name(contract.name, fallback='SoapContract')}SoapClient"


def _soap_wsdl_definition_methods(
    contracts: list[ContractMetadata],
) -> list[tuple[ContractMetadata, str]]:
    used: set[str] = set()
    methods: list[tuple[ContractMetadata, str]] = []
    for contract in contracts:
        base = to_java_method_name(f"{contract.name}Wsdl", fallback="soapWsdl")
        methods.append((contract, _unique_java_method_name(base, used)))
    return methods


def _soap_endpoint_java_methods(soap_contract: dict) -> dict[str, str]:
    used: set[str] = set()
    methods: dict[str, str] = {}
    for operation in soap_contract.get("operations") or []:
        operation_name = str(operation["name"])
        base = to_java_method_name(operation_name, fallback="soapOperation")
        methods[operation_name] = _unique_java_method_name(base, used)
    return methods


def _soap_handler_java_methods(contract: ContractMetadata) -> dict[str, str]:
    soap_contract = _require_soap_contract(contract)
    operation_mappings = _soap_operation_mappings(soap_contract)
    used: dict[str, str] = {}
    methods: dict[str, str] = {}
    for operation in soap_contract.get("operations") or []:
        operation_name = str(operation["name"])
        mapping = operation_mappings[operation_name]
        configured = str(mapping["handler_method"])
        method_name = to_java_method_name(
            configured,
            fallback=f"handle{to_pascal_case(operation_name)}",
        )
        previous = used.get(method_name)
        if previous is not None:
            raise ValueError(
                f"Inbound SOAP/WSDL interface '{contract.name}' operation mappings for "
                f"'{previous}' and '{operation_name}' both normalize to Java handler method "
                f"'{method_name}'. Use distinct handler_method values."
            )
        used[method_name] = operation_name
        methods[operation_name] = method_name
    return methods


def _soap_client_java_methods(soap_contract: dict) -> dict[str, str]:
    used: set[str] = set()
    methods: dict[str, str] = {}
    for operation in soap_contract.get("operations") or []:
        operation_name = str(operation["name"])
        base = to_java_method_name(operation_name, fallback="callSoapOperation")
        methods[operation_name] = _unique_java_method_name(base, used)
    return methods


def _unique_java_method_name(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _soap_operation_mappings(soap_contract: dict) -> dict[str, dict]:
    raw = soap_contract.get("operation_mappings") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(name): dict(mapping) for name, mapping in raw.items()}


def _soap_canonical_operation_mappings(soap_contract: dict) -> dict[str, dict]:
    return {
        operation_name: mapping
        for operation_name, mapping in _soap_operation_mappings(soap_contract).items()
        if mapping.get("mode") == "canonical"
    }


def _soap_has_canonical_operation_mappings(contract: ContractMetadata) -> bool:
    return bool(_soap_canonical_operation_mappings(_require_soap_contract(contract)))


def _soap_fields_by_path(fields: list[dict]) -> dict[str, dict]:
    return {str(field.get("path") or ""): dict(field) for field in fields}


def _soap_path_terminal(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _repository_var_name(entity: CanonicalEntity) -> str:
    return f"{entity.name[:1].lower()}{entity.name[1:]}Repository"


def _soap_lookup_conversion_expression(
    field: CanonicalField,
    raw_value: str,
    xml_path: str,
) -> str:
    path_literal = _java_code_string_literal(xml_path)
    if field.type == CanonicalFieldType.INTEGER:
        return f"asLongValue({raw_value}, {path_literal})"
    if field.type == CanonicalFieldType.DECIMAL:
        return f"asBigDecimalValue({raw_value}, {path_literal})"
    if field.type == CanonicalFieldType.BOOLEAN:
        return f"asBooleanValue({raw_value}, {path_literal})"
    if field.type == CanonicalFieldType.DATE:
        return f"asLocalDateValue({raw_value}, {path_literal})"
    if field.type == CanonicalFieldType.DATETIME:
        return f"asLocalDateTimeValue({raw_value}, {path_literal})"
    return raw_value


def _soap_format_expression(field: CanonicalField, value_expr: str) -> str:
    if field.type == CanonicalFieldType.DECIMAL:
        return f"{value_expr}.toPlainString()"
    if field.type == CanonicalFieldType.STRING:
        return value_expr
    return f"String.valueOf({value_expr})"


def _soap_not_found_message(operation_name: str, canonical_operation: dict) -> str:
    fault = canonical_operation.get("not_found_fault") or {}
    message = str(fault.get("message") or "").strip()
    if not message:
        message = f"SOAP operation '{operation_name}' did not find canonical record with id: "
    elif not message.endswith(" "):
        message = f"{message} "
    fault_name = str(fault.get("fault") or "").strip()
    if fault_name and not message.startswith(f"{fault_name}:"):
        message = f"{fault_name}: {message}"
    return message


def _soap_qname_local(value: str) -> str:
    return value.split(":", 1)[1] if ":" in value else value


def _soap_qname_parts(value: str, *, default_namespace: str) -> tuple[str, str]:
    if ":" in value:
        return default_namespace, value.split(":", 1)[1]
    return default_namespace, value


def _soap_wsdl_resource_path(contract: ContractMetadata, *, leading_slash: bool = True) -> str:
    soap_contract = _require_soap_contract(contract)
    wsdl_reference = Path(str(soap_contract.get("wsdl_path") or contract.source or "contract.wsdl"))
    resource = f"soap-contracts/{_xml_resource_dir_name(contract.name)}/{wsdl_reference.as_posix()}"
    return f"/{resource}" if leading_slash else resource


def _soap_client_uri_property(contract: ContractMetadata) -> str:
    return f"app.soap.clients.{_xml_resource_dir_name(contract.name)}.uri"


def _soap_xsd_resource_paths(contract: ContractMetadata, *, source_manifest: str) -> list[str]:
    manifest_path = Path(source_manifest)
    if not manifest_path.exists():
        return []
    soap_contract = _require_soap_contract(contract)
    wsdl_reference = str(soap_contract.get("wsdl_path") or contract.source or "")
    if not wsdl_reference:
        return []
    wsdl_relative = Path(wsdl_reference)
    if wsdl_relative.is_absolute():
        return []
    source_wsdl = manifest_path.parent / wsdl_relative
    if not source_wsdl.exists():
        return []
    _data, root = _read_generation_xml(
        source_wsdl,
        purpose=f"SOAP/WSDL interface '{contract.name}' generation WSDL '{wsdl_relative}'",
        budget=XmlParseBudget(),
    )
    resources = []
    for index, _schema in enumerate(_soap_embedded_schemas(root), start=1):
        relative = _soap_xsd_resource_relative_path(wsdl_relative, index)
        resources.append(
            f"/soap-contracts/{_xml_resource_dir_name(contract.name)}/{relative.as_posix()}"
        )
    return resources


def _soap_xsd_resource_relative_path(wsdl_relative: Path, index: int) -> Path:
    return wsdl_relative.parent / f"{wsdl_relative.stem}-schema-{index}.xsd"


def _soap_embedded_schemas(root: ET.Element) -> list[ET.Element]:
    return list(root.findall(".//{http://www.w3.org/2001/XMLSchema}schema"))


def _soap_namespace_map(data: bytes) -> dict[str, str]:
    namespace_map: dict[str, str] = {}
    for _event, namespace in ET.iterparse(BytesIO(data), events=("start-ns",)):
        prefix, uri = namespace
        if prefix and prefix not in namespace_map:
            namespace_map[prefix] = uri
    return namespace_map


def _read_generation_xml(
    path: Path,
    *,
    purpose: str,
    budget: XmlParseBudget,
) -> tuple[bytes, ET.Element]:
    data = read_untrusted_xml_bytes(path, purpose=purpose, budget=budget)
    try:
        return data, ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"{purpose} could not be parsed: {exc}.") from exc


def _soap_wsdl_bytes_with_endpoint_address(
    *,
    source_text: str,
    namespace_map: dict[str, str],
    endpoint_url: str,
) -> bytes:
    updated = source_text
    soap_prefixes = [
        prefix
        for prefix, uri in namespace_map.items()
        if uri == "http://schemas.xmlsoap.org/wsdl/soap/"
    ]
    for prefix in soap_prefixes:
        address_pattern = re.compile(
            rf"(<{re.escape(prefix)}:address\b[^>]*?\blocation\s*=\s*)(?P<quote>['\"])(.*?)(?P=quote)",
            re.DOTALL,
        )
        updated = address_pattern.sub(
            lambda match: f"{match.group(1)}{match.group('quote')}{endpoint_url}{match.group('quote')}",
            updated,
        )
    return updated.encode("utf-8")


def _soap_schema_bytes(schema: ET.Element, namespace_map: dict[str, str]) -> bytes:
    schema_copy = ET.fromstring(ET.tostring(schema, encoding="utf-8"))
    for prefix, uri in namespace_map.items():
        if prefix in {"soap", "wsdl"} or uri == "http://www.w3.org/2001/XMLSchema":
            continue
        if f"xmlns:{prefix}" not in schema_copy.attrib:
            schema_copy.set(f"xmlns:{prefix}", uri)
    return ET.tostring(schema_copy, encoding="utf-8", xml_declaration=True)


def _fixed_width_parser_class_name(contract_name: str) -> str:
    return f"{to_java_class_name(contract_name, fallback='FixedWidth')}FixedWidthParser"


def _csv_parser_class_name(contract_name: str) -> str:
    return f"{to_java_class_name(contract_name, fallback='Csv')}CsvParser"


def _upstream_fixed_width_contracts(metadata: MetadataProject) -> list[ContractMetadata]:
    return _upstream_file_contracts(metadata, "file-fixed-width")


def _upstream_csv_contracts(metadata: MetadataProject) -> list[ContractMetadata]:
    return _upstream_file_contracts(metadata, "file-csv")


def _upstream_file_contracts(metadata: MetadataProject, contract_type: str) -> list[ContractMetadata]:
    upstream_contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
    }
    return [
        contract
        for contract in metadata.contracts
        if contract.type == contract_type
        and contract.name in upstream_contract_names
        and contract.file_layout is not None
    ]


def _upstream_file_ingest_contexts(
    metadata: MetadataProject,
) -> list[_UpstreamFileIngestContext]:
    contexts: list[_UpstreamFileIngestContext] = []
    entities_by_name = {entity.name: entity for entity in all_entities(metadata)}
    used_parser_vars: set[str] = set()
    used_ingest_methods: set[str] = set()
    for contract in metadata.contracts:
        if contract.type not in {"file-fixed-width", "file-csv"} or contract.file_layout is None:
            continue
        mappings = [
            mapping
            for mapping in metadata.mappings
            if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
            and mapping.contract_name == contract.name
        ]
        if not mappings:
            continue
        entity_names = {
            mapping.target_path.split(".", 1)[0]
            for mapping in mappings
            if "." in mapping.target_path
        }
        if len(entity_names) != 1:
            raise ValueError(
                f"Upstream file contract '{contract.name}' must map to exactly one "
                f"canonical entity for generated file ingestion, got {sorted(entity_names)!r}."
            )
        entity_name = next(iter(entity_names))
        entity = entities_by_name.get(entity_name)
        if entity is None:
            raise ValueError(
                f"Upstream file contract '{contract.name}' maps to unknown entity '{entity_name}'."
            )
        _validate_inbound_file_trailer_value_sources(
            contract=contract,
            entity=entity,
            mappings=mappings,
        )
        parser_class_name = (
            _csv_parser_class_name(contract.name)
            if contract.type == "file-csv"
            else _fixed_width_parser_class_name(contract.name)
        )
        parser_var_name = _unique_generated_name(
            to_java_method_name(f"{contract.name}Parser", fallback="fileParser"),
            used_parser_vars,
        )
        contexts.append(
            _UpstreamFileIngestContext(
                contract=contract,
                entity=entity,
                mappings=tuple(_dedupe_field_mappings(mappings)),
                parser_class_name=parser_class_name,
                parser_var_name=parser_var_name,
                repository_var_name=f"{entity.name[:1].lower()}{entity.name[1:]}Repository",
                ingest_method_name=_unique_generated_name(
                    to_java_method_name(f"ingest {contract.name}", fallback="ingestFile"),
                    used_ingest_methods,
                ),
            )
        )
    return contexts


def _upstream_xml_ingest_contexts(
    metadata: MetadataProject,
) -> list[_UpstreamXmlIngestContext]:
    contexts: list[_UpstreamXmlIngestContext] = []
    entities_by_name = {entity.name: entity for entity in all_entities(metadata)}
    used_parser_vars: set[str] = set()
    used_ingest_methods: set[str] = set()
    for contract in metadata.contracts:
        if contract.type != "xml-xsd" or contract.xml_contract is None:
            continue
        mappings = [
            mapping
            for mapping in metadata.mappings
            if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
            and mapping.contract_name == contract.name
        ]
        if not mappings:
            continue
        entity_names = {
            mapping.target_path.split(".", 1)[0]
            for mapping in mappings
            if "." in mapping.target_path
        }
        if len(entity_names) != 1:
            raise ValueError(
                f"Upstream XML/XSD contract '{contract.name}' must map to exactly one "
                f"canonical entity for generated XML ingestion, got {sorted(entity_names)!r}."
            )
        entity_name = next(iter(entity_names))
        entity = entities_by_name.get(entity_name)
        if entity is None:
            raise ValueError(
                f"Upstream XML/XSD contract '{contract.name}' maps to unknown entity '{entity_name}'."
            )
        _validate_xml_mappings_supported(
            contract=contract,
            mappings=mappings,
            direction="upstream",
            entity=entity,
        )
        contexts.append(
            _UpstreamXmlIngestContext(
                contract=contract,
                entity=entity,
                mappings=tuple(_dedupe_field_mappings(mappings)),
                parser_class_name=_xml_parser_class_name(contract),
                parser_var_name=_unique_generated_name(
                    to_java_method_name(f"{contract.name}XmlParser", fallback="xmlParser"),
                    used_parser_vars,
                ),
                model_class_name=_xml_model_class_name(contract),
                repository_var_name=f"{entity.name[:1].lower()}{entity.name[1:]}Repository",
                ingest_method_name=_unique_generated_name(
                    to_java_method_name(f"ingest {contract.name}", fallback="ingestXml"),
                    used_ingest_methods,
                ),
            )
        )
    return contexts


def _downstream_xml_output_contexts(metadata: MetadataProject) -> list[_DownstreamXmlOutputContext]:
    contexts: list[_DownstreamXmlOutputContext] = []
    entities_by_name = {entity.name: entity for entity in all_entities(metadata)}
    used_serializer_vars: set[str] = set()
    used_output_methods: set[str] = set()
    used_slugs: set[str] = set()
    for contract in metadata.contracts:
        if contract.type != "xml-xsd" or contract.xml_contract is None:
            continue
        mappings = [
            mapping
            for mapping in metadata.mappings
            if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
            and mapping.contract_name == contract.name
        ]
        if not mappings:
            continue
        entity_names = {
            mapping.source_path.split(".", 1)[0]
            for mapping in mappings
            if "." in mapping.source_path
        }
        if len(entity_names) != 1:
            raise ValueError(
                f"Downstream XML/XSD contract '{contract.name}' must map from exactly one "
                f"canonical entity for generated XML output, got {sorted(entity_names)!r}."
            )
        entity_name = next(iter(entity_names))
        entity = entities_by_name.get(entity_name)
        if entity is None:
            raise ValueError(
                f"Downstream XML/XSD contract '{contract.name}' maps from unknown entity '{entity_name}'."
            )
        _validate_xml_mappings_supported(
            contract=contract,
            mappings=mappings,
            direction="downstream",
            entity=entity,
        )
        contexts.append(
            _DownstreamXmlOutputContext(
                contract=contract,
                entity=entity,
                mappings=tuple(mappings),
                serializer_class_name=_xml_serializer_class_name(contract),
                serializer_var_name=_unique_generated_name(
                    to_java_method_name(f"{contract.name}XmlSerializer", fallback="xmlSerializer"),
                    used_serializer_vars,
                ),
                model_class_name=_xml_model_class_name(contract),
                repository_var_name=f"{entity.name[:1].lower()}{entity.name[1:]}Repository",
                output_method_name=_unique_generated_name(
                    to_java_method_name(f"write {contract.name}", fallback="writeXmlOutput"),
                    used_output_methods,
                ),
                contract_slug=_unique_generated_slug(
                    to_snake_case(contract.name).replace("_", "-") or "xml-output",
                    used_slugs,
                ),
            )
        )
    return contexts


def _xml_field_descriptor_lookup(contract: ContractMetadata) -> dict[str, dict]:
    xml_contract = _require_xml_contract(contract)
    attributes, fields = _xml_field_descriptors(xml_contract)
    return {
        str(field["name"]): field
        for field in [*attributes, *fields]
    }


def _validate_xml_mappings_supported(
    *,
    contract: ContractMetadata,
    mappings: list[FieldMapping],
    direction: str,
    entity: CanonicalEntity,
) -> None:
    field_lookup = _xml_field_descriptor_lookup(contract)
    entity_fields = {field.name: field for field in entity.fields}
    seen_contract_fields: set[str] = set()
    seen_canonical_fields: set[str] = set()
    for mapping in mappings:
        contract_name = (
            contract_field_name(mapping)
            if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
            else output_field_name(mapping)
        )
        field = field_lookup.get(contract_name)
        if field is None:
            raise ValueError(
                f"{direction.capitalize()} XML/XSD contract '{contract.name}' maps unknown "
                f"field '{contract_name}'."
            )
        if bool(field.get("repeated")):
            raise ValueError(
                f"{direction.capitalize()} XML/XSD contract '{contract.name}' maps repeated "
                f"field '{contract_name}', but canonical XML runtime currently supports one "
                "canonical row per XML document."
            )
        canonical_field_name_value = (
            canonical_field_name(mapping)
            if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
            else mapping.source_path.split(".", 1)[1]
        )
        canonical_field = entity_fields.get(canonical_field_name_value)
        if canonical_field is None:
            raise ValueError(
                f"{direction.capitalize()} XML/XSD contract '{contract.name}' maps unknown "
                f"canonical field '{entity.name}.{canonical_field_name_value}'."
            )
        if not _xml_mapping_types_compatible(
            direction=direction,
            xml_field=field,
            canonical_field=canonical_field,
        ):
            raise ValueError(
                f"{direction.capitalize()} XML/XSD contract '{contract.name}' cannot map XML "
                f"field '{contract_name}' ({_xml_field_type_label(field)}) to canonical field "
                f"'{entity.name}.{canonical_field.name}' ({canonical_field.type.value})."
            )
        if contract_name in seen_contract_fields:
            raise ValueError(
                f"{direction.capitalize()} XML/XSD contract '{contract.name}' maps XML field "
                f"'{contract_name}' more than once."
            )
        seen_contract_fields.add(contract_name)
        canonical_path = (
            mapping.target_path
            if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
            else mapping.source_path
        )
        if canonical_path in seen_canonical_fields:
            raise ValueError(
                f"{direction.capitalize()} XML/XSD contract '{contract.name}' maps canonical "
                f"field '{canonical_path}' more than once."
            )
        seen_canonical_fields.add(canonical_path)


def _render_file_ingest_controller(
    *,
    metadata: MetadataProject,
    contexts: list[_UpstreamFileIngestContext],
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    constructor_params: list[str] = []
    fields: list[str] = [
        "    @Value(\"${app.file-ingest.base-dir:"
        + _isolated_tmp_base_dir_default(metadata.bounded_context, "file-ingest")
        + "}\")",
        "    private String ingestBaseDir;",
        "",
    ]
    assignments: list[str] = []
    imported_entities: OrderedDict[str, CanonicalEntity] = OrderedDict()
    imported_repositories: OrderedDict[str, str] = OrderedDict()
    imported_parsers: OrderedDict[str, str] = OrderedDict()
    for ctx in contexts:
        imported_entities[ctx.entity.name] = ctx.entity
        imported_repositories[ctx.repository_var_name] = f"{ctx.entity.name}Repository"
        imported_parsers[ctx.parser_var_name] = ctx.parser_class_name
    for parser_var, parser_class in imported_parsers.items():
        fields.append(f"    private final {parser_class} {parser_var};")
        constructor_params.append(f"            {parser_class} {parser_var}")
        assignments.append(f"        this.{parser_var} = {parser_var};")
    for repository_var, repository_class in imported_repositories.items():
        fields.append(f"    private final {repository_class} {repository_var};")
        constructor_params.append(f"            {repository_class} {repository_var}")
        assignments.append(f"        this.{repository_var} = {repository_var};")

    for index in range(len(constructor_params) - 1):
        constructor_params[index] += ","

    switch_cases = []
    for ctx in contexts:
        switch_cases.append(
            "            case "
            + _java_code_string_literal(ctx.contract.name)
            + " -> ResponseEntity.ok("
            + f"{ctx.ingest_method_name}(resolveInputPath(request == null ? null : request.path())));"
        )

    ingest_methods: list[str] = []
    for ctx in contexts:
        ingest_methods.extend(_file_ingest_method_lines(ctx))

    body = [
        "@RestController",
        "@RequestMapping(\"/files\")",
        "public class FileIngestController {",
        "",
        *fields,
        "",
        "    public FileIngestController(",
        *constructor_params,
        "    ) {",
        *assignments,
        "    }",
        "",
        "    @PostMapping(\"/ingest/{contractName}\")",
        "    @Transactional",
        "    public ResponseEntity<FileIngestResponse> ingest(",
        "            @PathVariable String contractName,",
        "            @RequestBody FileIngestRequest request) {",
        "        try {",
        "            return switch (contractName) {",
        *switch_cases,
        "                default -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(",
        "                        FileIngestResponse.failure(contractName, null, \"Unknown upstream file contract: \" + contractName));",
        "            };",
        "        } catch (DuplicateIngestRecordException ex) {",
        "            return ResponseEntity.status(HttpStatus.CONFLICT).body(",
        "                    FileIngestResponse.failure(contractName, ex.entityName(), ex.getMessage()));",
        "        } catch (IllegalArgumentException ex) {",
        "            return ResponseEntity.badRequest().body(",
        "                    FileIngestResponse.failure(contractName, null, ex.getMessage()));",
        "        } catch (IOException ex) {",
        "            return ResponseEntity.badRequest().body(",
        "                    FileIngestResponse.failure(contractName, null, \"Unable to read ingest file.\"));",
        "        }",
        "    }",
        "",
        *ingest_methods,
        "    private Path resolveInputPath(String requestedPath) {",
        "        if (requestedPath == null || requestedPath.isBlank()) {",
        "            throw new IllegalArgumentException(\"File ingest path is required.\");",
        "        }",
        "        String trimmedPath = requestedPath.trim();",
        "        String lowerPath = trimmedPath.toLowerCase(Locale.ROOT);",
        "        if (lowerPath.matches(\"^[a-z][a-z0-9+.-]*://.*\") || lowerPath.startsWith(\"file:\")) {",
        "            throw new IllegalArgumentException(\"Remote URLs and URI paths are not allowed for file ingestion.\");",
        "        }",
        "        Path baseDir = Path.of(ingestBaseDir).toAbsolutePath().normalize();",
        "        Path candidate = Path.of(trimmedPath);",
        "        Path resolved = candidate.isAbsolute()",
        "                ? candidate.toAbsolutePath().normalize()",
        "                : baseDir.resolve(candidate).normalize();",
        "        if (!resolved.startsWith(baseDir)) {",
        "            throw new IllegalArgumentException(\"File ingest path must stay under the configured ingest base directory.\");",
        "        }",
        "        if (!Files.exists(resolved)) {",
        "            throw new IllegalArgumentException(\"File ingest path does not exist.\");",
        "        }",
        "        if (!Files.isRegularFile(resolved)) {",
        "            throw new IllegalArgumentException(\"File ingest path must reference a regular file.\");",
        "        }",
        "        try {",
        "            Path realBaseDir = baseDir.toRealPath();",
        "            Path realInputPath = resolved.toRealPath();",
        "            if (!realInputPath.startsWith(realBaseDir)) {",
        "                throw new IllegalArgumentException(\"File ingest path must stay under the configured ingest base directory.\");",
        "            }",
        "            return realInputPath;",
        "        } catch (IOException ex) {",
        "            throw new IllegalArgumentException(\"File ingest path could not be resolved safely.\");",
        "        }",
        "    }",
        "",
        "    private Object requiredField(Map<String, Object> fields, String fieldName, String entityFieldName) {",
        "        Object value = fields.get(fieldName);",
        "        if (value == null) {",
        "            throw new IllegalArgumentException(\"Required file field is missing for \" + entityFieldName + \": \" + fieldName);",
        "        }",
        "        return value;",
        "    }",
        "",
        "    private String asString(String fieldName, Object value) {",
        "        return value == null ? null : value.toString();",
        "    }",
        "",
        "    private Long asLong(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof Number number) {",
        "            return number.longValue();",
        "        }",
        "        try {",
        "            return Long.valueOf(value.toString().trim());",
        "        } catch (RuntimeException ex) {",
        "            throw new IllegalArgumentException(\"Invalid integer value for \" + fieldName + \".\");",
        "        }",
        "    }",
        "",
        "    private BigDecimal asBigDecimal(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof BigDecimal decimal) {",
        "            return decimal;",
        "        }",
        "        if (value instanceof Number number) {",
        "            return BigDecimal.valueOf(number.doubleValue());",
        "        }",
        "        try {",
        "            return new BigDecimal(value.toString().trim());",
        "        } catch (RuntimeException ex) {",
        "            throw new IllegalArgumentException(\"Invalid decimal value for \" + fieldName + \".\");",
        "        }",
        "    }",
        "",
        "    private BigDecimal asExactBigDecimal(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof BigDecimal decimal) {",
        "            return decimal;",
        "        }",
        "        try {",
        "            return new BigDecimal(value.toString().trim());",
        "        } catch (RuntimeException ex) {",
        "            throw new IllegalArgumentException(\"Invalid decimal value for \" + fieldName + \".\");",
        "        }",
        "    }",
        "",
        "    private IllegalArgumentException trailerValidationError(",
        "            Path inputPath,",
        "            String contractName,",
        "            String layoutSource,",
        "            String fieldName,",
        "            String expected,",
        "            String actual) {",
        "        String safeFileName = inputPath.getFileName() == null ? \"<unknown>\" : inputPath.getFileName().toString();",
        "        return new IllegalArgumentException(",
        "                \"Inbound trailer validation failed for interface '\" + contractName",
        "                        + \"' in \" + safeFileName",
        "                        + \", layout '\" + layoutSource",
        "                        + \"', record type trailer, field \" + fieldName",
        "                        + \": expected \" + expected",
        "                        + \", actual \" + actual);",
        "    }",
        "",
        "    private Boolean asBoolean(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof Boolean bool) {",
        "            return bool;",
        "        }",
        "        String text = value.toString().trim();",
        "        if (text.equalsIgnoreCase(\"true\")) {",
        "            return Boolean.TRUE;",
        "        }",
        "        if (text.equalsIgnoreCase(\"false\")) {",
        "            return Boolean.FALSE;",
        "        }",
        "        throw new IllegalArgumentException(\"Invalid boolean value for \" + fieldName + \".\");",
        "    }",
        "",
        "    private LocalDate asLocalDate(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof LocalDate date) {",
        "            return date;",
        "        }",
        "        try {",
        "            return LocalDate.parse(value.toString().trim());",
        "        } catch (RuntimeException ex) {",
        "            throw new IllegalArgumentException(\"Invalid date value for \" + fieldName + \".\");",
        "        }",
        "    }",
        "",
        "    private LocalDateTime asLocalDateTime(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof LocalDateTime dateTime) {",
        "            return dateTime;",
        "        }",
        "        try {",
        "            return LocalDateTime.parse(value.toString().trim());",
        "        } catch (RuntimeException ex) {",
        "            throw new IllegalArgumentException(\"Invalid datetime value for \" + fieldName + \".\");",
        "        }",
        "    }",
        "",
        "    public record FileIngestRequest(String path) {",
        "    }",
        "",
        "    public record FileIngestResponse(",
        "            String contractName,",
        "            String entity,",
        "            long parsedCount,",
        "            long persistedCount,",
        "            List<String> errors) {",
        "        static FileIngestResponse success(String contractName, String entity, long parsedCount, long persistedCount) {",
        "            return new FileIngestResponse(contractName, entity, parsedCount, persistedCount, List.of());",
        "        }",
        "",
        "        static FileIngestResponse failure(String contractName, String entity, String error) {",
        "            return new FileIngestResponse(contractName, entity, 0L, 0L, List.of(error));",
        "        }",
        "    }",
        "",
        "    private static class DuplicateIngestRecordException extends RuntimeException {",
        "        private final String entityName;",
        "",
        "        DuplicateIngestRecordException(String entityName, String message) {",
        "            super(message);",
        "            this.entityName = entityName;",
        "        }",
        "",
        "        String entityName() {",
        "            return entityName;",
        "        }",
        "    }",
        "}",
    ]
    imports = [
        *[f"{root_package}.adapter.inbound.{parser_class}" for parser_class in imported_parsers.values()],
        *[f"{root_package}.domain.{entity.name}" for entity in imported_entities.values()],
        *[f"{root_package}.repository.{repository_class}" for repository_class in imported_repositories.values()],
        "java.io.IOException",
        "java.math.BigDecimal",
        "java.nio.file.Files",
        "java.nio.file.Path",
        "java.time.LocalDate",
        "java.time.LocalDateTime",
        "java.util.ArrayList",
        "java.util.HashSet",
        "java.util.List",
        "java.util.Locale",
        "java.util.Map",
        "java.util.Set",
        "org.springframework.beans.factory.annotation.Value",
        "org.springframework.http.HttpStatus",
        "org.springframework.http.ResponseEntity",
        "org.springframework.transaction.annotation.Transactional",
        "org.springframework.web.bind.annotation.PathVariable",
        "org.springframework.web.bind.annotation.PostMapping",
        "org.springframework.web.bind.annotation.RequestBody",
        "org.springframework.web.bind.annotation.RequestMapping",
        "org.springframework.web.bind.annotation.RestController",
    ]
    return _java_file(
        package_name=f"{root_package}.adapter.inbound",
        imports=list(dict.fromkeys(imports)),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _file_ingest_trailer_validation_method_name(ctx: _UpstreamFileIngestContext) -> str:
    return f"validate{ctx.ingest_method_name[:1].upper()}{ctx.ingest_method_name[1:]}Trailer"


def _file_ingest_trailer_validation_method_lines(ctx: _UpstreamFileIngestContext) -> list[str]:
    specs = _inbound_trailer_validation_specs(ctx.contract)
    if not specs:
        return []

    entity = ctx.entity
    entity_var = entity.name[:1].lower() + entity.name[1:]
    entity_fields = {field.name: field for field in entity.fields}
    method_name = _file_ingest_trailer_validation_method_name(ctx)
    lines = [
        f"    private void {method_name}(Path inputPath, List<{ctx.parser_class_name}.ParsedRecord> parsedRecords, List<{entity.name}> entities) {{",
        f"        List<{ctx.parser_class_name}.ParsedRecord> trailerRecords = parsedRecords.stream()",
        "                .filter(record -> \"trailer\".equals(record.recordType()))",
        "                .toList();",
        "        if (trailerRecords.size() != 1) {",
        "            throw trailerValidationError(",
        "                    inputPath,",
        "                    "
        + _java_code_string_literal(ctx.contract.name)
        + ",",
        "                    "
        + _java_code_string_literal(ctx.contract.source)
        + ",",
        "                    \"trailer\",",
        "                    \"1\",",
        "                    String.valueOf(trailerRecords.size()));",
        "        }",
        "        Map<String, Object> trailerFields = trailerRecords.get(0).fields();",
    ]
    for spec in specs:
        field = spec["field"]
        assert isinstance(field, dict)
        field_name = str(field["name"])
        field_literal = _java_code_string_literal(field_name)
        field_suffix = to_pascal_case(field_name)
        actual_var = f"actual{field_suffix}"
        expected_var = f"expected{field_suffix}"
        if spec["kind"] == "record_count":
            lines.extend(
                [
                    f"        Long {actual_var} = asLong({field_literal}, trailerFields.get({field_literal}));",
                    f"        long {expected_var} = entities.size();",
                    f"        if ({actual_var} == null || {actual_var}.longValue() != {expected_var}) {{",
                    "            throw trailerValidationError(",
                    "                    inputPath,",
                    "                    "
                    + _java_code_string_literal(ctx.contract.name)
                    + ",",
                    "                    "
                    + _java_code_string_literal(ctx.contract.source)
                    + ",",
                    "                    "
                    + field_literal
                    + ",",
                    f"                    String.valueOf({expected_var}),",
                    f"                    {actual_var} == null ? \"null\" : {actual_var}.toString());",
                    "        }",
                ]
            )
            continue

        source_field = str(spec["source_field"])
        source_canonical_field = entity_fields[source_field]
        source_getter = f"{entity_var}.get{to_pascal_case(source_field)}()"
        value_var = f"{to_java_method_name(source_field, fallback='sumValue')}Value"
        lines.append(f"        BigDecimal {expected_var} = BigDecimal.ZERO;")
        lines.append(f"        for ({entity.name} {entity_var} : entities) {{")
        if source_canonical_field.type == CanonicalFieldType.DECIMAL:
            lines.append(f"            BigDecimal {value_var} = {source_getter};")
            value_expr = value_var
        else:
            lines.append(f"            Number {value_var} = {source_getter};")
            value_expr = f"BigDecimal.valueOf({value_var}.longValue())"
        lines.extend(
            [
                f"            if ({value_var} == null) {{",
                "                throw trailerValidationError(",
                "                        inputPath,",
                "                        "
                + _java_code_string_literal(ctx.contract.name)
                + ",",
                "                        "
                + _java_code_string_literal(ctx.contract.source)
                + ",",
                "                        "
                + field_literal
                + ",",
                "                        "
                + _java_code_string_literal(f"non-null {entity.name}.{source_field}")
                + ",",
                "                        \"null\");",
                "            }",
                f"            {expected_var} = {expected_var}.add({value_expr});",
                "        }",
            ]
        )
        if _is_minor_unit_trailer_coercion(field):
            lines.extend(
                [
                    "        try {",
                    f"            {expected_var} = {expected_var}.movePointRight(2).setScale(0);",
                    "        } catch (ArithmeticException ex) {",
                    "            throw trailerValidationError(",
                    "                    inputPath,",
                    "                    "
                    + _java_code_string_literal(ctx.contract.name)
                    + ",",
                    "                    "
                    + _java_code_string_literal(ctx.contract.source)
                    + ",",
                    "                    "
                    + field_literal
                    + ",",
                    "                    \"minor-unit total with scale 0\",",
                    f"                    {expected_var}.toPlainString());",
                    "        }",
                ]
            )
        lines.extend(
            [
                f"        BigDecimal {actual_var} = asExactBigDecimal({field_literal}, trailerFields.get({field_literal}));",
                f"        if ({actual_var} == null || {actual_var}.compareTo({expected_var}) != 0) {{",
                "            throw trailerValidationError(",
                "                    inputPath,",
                "                    "
                + _java_code_string_literal(ctx.contract.name)
                + ",",
                "                    "
                + _java_code_string_literal(ctx.contract.source)
                + ",",
                "                    "
                + field_literal
                + ",",
                f"                    {expected_var}.toPlainString(),",
                f"                    {actual_var} == null ? \"null\" : {actual_var}.toPlainString());",
                "        }",
            ]
        )
    lines.extend(["    }", ""])
    return lines


def _file_ingest_method_lines(ctx: _UpstreamFileIngestContext) -> list[str]:
    entity = ctx.entity
    entity_var = entity.name[:1].lower() + entity.name[1:]
    id_field = entity_id_field(entity)
    id_java_type = _java_type(id_field)
    trailer_validation_specs = _inbound_trailer_validation_specs(ctx.contract)
    mapped_id_fields = [
        mapping
        for mapping in ctx.mappings
        if canonical_field_name(mapping) == id_field.name
    ]
    id_is_mapped = bool(mapped_id_fields)
    lines = [
        f"    public FileIngestResponse {ctx.ingest_method_name}(Path inputPath) throws IOException {{",
        f"        List<{ctx.parser_class_name}.ParsedRecord> parsedRecords = {ctx.parser_var_name}.parse(inputPath);",
        f"        List<{entity.name}> entities = new ArrayList<>();",
    ]
    if id_is_mapped:
        lines.append(f"        Set<{id_java_type}> seenIds = new HashSet<>();")
    lines.extend(
        [
            f"        for ({ctx.parser_class_name}.ParsedRecord record : parsedRecords) {{",
            "            if (!\"data\".equals(record.recordType())) {",
            "                continue;",
            "            }",
            "            Map<String, Object> fields = record.fields();",
            f"            {entity.name} {entity_var} = new {entity.name}();",
        ]
    )
    fields_by_name = {field.name: field for field in entity.fields}
    for mapping in ctx.mappings:
        field_name = canonical_field_name(mapping)
        field = fields_by_name.get(field_name)
        if field is None:
            raise ValueError(
                f"Upstream file contract '{ctx.contract.name}' maps to unknown field "
                f"'{mapping.target_path}'."
            )
        contract_name = contract_field_name(mapping)
        value_expr = f"fields.get({_java_code_string_literal(contract_name)})"
        if field.required:
            value_expr = (
                "requiredField(fields, "
                + _java_code_string_literal(contract_name)
                + ", "
                + _java_code_string_literal(f"{entity.name}.{field.name}")
                + ")"
            )
        converter = _file_ingest_converter(field)
        lines.append(
            f"            {entity_var}.set{to_pascal_case(field.name)}("
            f"{converter}({_java_code_string_literal(field.name)}, {value_expr}));"
        )
    if id_is_mapped:
        id_getter = f"{entity_var}.get{to_pascal_case(id_field.name)}()"
        lines.extend(
            [
                f"            {id_java_type} recordId = {id_getter};",
                "            if (recordId != null && !seenIds.add(recordId)) {",
                "                throw new DuplicateIngestRecordException(",
                "                        "
                + _java_code_string_literal(entity.name)
                + ", ",
                "                        "
                + _java_code_string_literal(f"Duplicate {entity.name} ID within ingest file: ")
                + " + recordId);",
                "            }",
            ]
        )
    lines.extend(
        [
            f"            entities.add({entity_var});",
            "        }",
        ]
    )
    if trailer_validation_specs:
        lines.append(
            f"        {_file_ingest_trailer_validation_method_name(ctx)}(inputPath, parsedRecords, entities);"
        )
    if id_is_mapped:
        lines.extend(
            [
                f"        for ({id_java_type} recordId : seenIds) {{",
                f"            if ({ctx.repository_var_name}.existsById(recordId)) {{",
                "                throw new DuplicateIngestRecordException(",
                "                        "
                + _java_code_string_literal(entity.name)
                + ", ",
                "                        "
                + _java_code_string_literal(f"{entity.name} already exists with id: ")
                + " + recordId);",
                "            }",
                "        }",
            ]
        )
    lines.extend(
        [
            f"        {ctx.repository_var_name}.saveAll(entities);",
            "        return FileIngestResponse.success(",
            "                "
            + _java_code_string_literal(ctx.contract.name)
            + ",",
            "                "
            + _java_code_string_literal(entity.name)
            + ",",
            "                entities.size(),",
            "                entities.size());",
            "    }",
            "",
        ]
    )
    lines.extend(_file_ingest_trailer_validation_method_lines(ctx))
    return lines


def _render_xml_ingest_controller(
    *,
    metadata: MetadataProject,
    contexts: list[_UpstreamXmlIngestContext],
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    constructor_params: list[str] = []
    fields: list[str] = [
        "    @Value(\"${app.xml-ingest.base-dir:"
        + _isolated_tmp_base_dir_default(metadata.bounded_context, "xml-ingest")
        + "}\")",
        "    private String ingestBaseDir;",
        "",
    ]
    assignments: list[str] = []
    imported_entities: OrderedDict[str, CanonicalEntity] = OrderedDict()
    imported_repositories: OrderedDict[str, str] = OrderedDict()
    imported_parsers: OrderedDict[str, str] = OrderedDict()
    imported_models: OrderedDict[str, str] = OrderedDict()
    for ctx in contexts:
        imported_entities[ctx.entity.name] = ctx.entity
        imported_repositories[ctx.repository_var_name] = f"{ctx.entity.name}Repository"
        imported_parsers[ctx.parser_var_name] = ctx.parser_class_name
        imported_models[ctx.model_class_name] = ctx.model_class_name
    for parser_var, parser_class in imported_parsers.items():
        fields.append(f"    private final {parser_class} {parser_var};")
        constructor_params.append(f"            {parser_class} {parser_var}")
        assignments.append(f"        this.{parser_var} = {parser_var};")
    for repository_var, repository_class in imported_repositories.items():
        fields.append(f"    private final {repository_class} {repository_var};")
        constructor_params.append(f"            {repository_class} {repository_var}")
        assignments.append(f"        this.{repository_var} = {repository_var};")
    for index in range(len(constructor_params) - 1):
        constructor_params[index] += ","

    switch_cases = [
        "            case "
        + _java_code_string_literal(ctx.contract.name)
        + " -> ResponseEntity.ok("
        + f"{ctx.ingest_method_name}(resolveInputPath(request == null ? null : request.path())));"
        for ctx in contexts
    ]
    ingest_methods: list[str] = []
    for ctx in contexts:
        ingest_methods.extend(_xml_ingest_method_lines(ctx))

    body = [
        "@RestController",
        "@RequestMapping(\"/xml\")",
        "public class XmlIngestController {",
        "",
        *fields,
        "",
        "    public XmlIngestController(",
        *constructor_params,
        "    ) {",
        *assignments,
        "    }",
        "",
        "    @PostMapping(\"/ingest/{contractName}\")",
        "    @Transactional",
        "    public ResponseEntity<XmlIngestResponse> ingest(",
        "            @PathVariable String contractName,",
        "            @RequestBody XmlIngestRequest request) {",
        "        try {",
        "            return switch (contractName) {",
        *switch_cases,
        "                default -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(",
        "                        XmlIngestResponse.failure(contractName, null, \"Unknown upstream XML/XSD contract: \" + contractName));",
        "            };",
        "        } catch (DuplicateXmlIngestRecordException ex) {",
        "            return ResponseEntity.status(HttpStatus.CONFLICT).body(",
        "                    XmlIngestResponse.failure(contractName, ex.entityName(), ex.getMessage()));",
        "        } catch (IllegalArgumentException ex) {",
        "            return ResponseEntity.badRequest().body(",
        "                    XmlIngestResponse.failure(contractName, null, ex.getMessage()));",
        "        } catch (IOException ex) {",
        "            return ResponseEntity.badRequest().body(",
        "                    XmlIngestResponse.failure(contractName, null, \"Unable to read XML ingest file.\"));",
        "        } catch (Exception ex) {",
        "            return ResponseEntity.badRequest().body(",
        "                    XmlIngestResponse.failure(contractName, null, \"XML ingest failed validation or parsing.\"));",
        "        }",
        "    }",
        "",
        *ingest_methods,
        "    private Path resolveInputPath(String requestedPath) {",
        "        if (requestedPath == null || requestedPath.isBlank()) {",
        "            throw new IllegalArgumentException(\"XML ingest path is required.\");",
        "        }",
        "        String trimmedPath = requestedPath.trim();",
        "        String lowerPath = trimmedPath.toLowerCase(Locale.ROOT);",
        "        if (lowerPath.matches(\"^[a-z][a-z0-9+.-]*://.*\") || lowerPath.startsWith(\"file:\")) {",
        "            throw new IllegalArgumentException(\"Remote URLs and URI paths are not allowed for XML ingestion.\");",
        "        }",
        "        Path baseDir = Path.of(ingestBaseDir).toAbsolutePath().normalize();",
        "        Path candidate = Path.of(trimmedPath);",
        "        Path resolved = candidate.isAbsolute()",
        "                ? candidate.toAbsolutePath().normalize()",
        "                : baseDir.resolve(candidate).normalize();",
        "        if (!resolved.startsWith(baseDir)) {",
        "            throw new IllegalArgumentException(\"XML ingest path must stay under the configured ingest base directory.\");",
        "        }",
        "        if (!Files.exists(resolved)) {",
        "            throw new IllegalArgumentException(\"XML ingest path does not exist.\");",
        "        }",
        "        if (!Files.isRegularFile(resolved)) {",
        "            throw new IllegalArgumentException(\"XML ingest path must reference a regular file.\");",
        "        }",
        "        try {",
        "            Path realBaseDir = baseDir.toRealPath();",
        "            Path realInputPath = resolved.toRealPath();",
        "            if (!realInputPath.startsWith(realBaseDir)) {",
        "                throw new IllegalArgumentException(\"XML ingest path must stay under the configured ingest base directory.\");",
        "            }",
        "            return realInputPath;",
        "        } catch (IOException ex) {",
        "            throw new IllegalArgumentException(\"XML ingest path could not be resolved safely.\");",
        "        }",
        "    }",
        "",
        "    private <T> T requiredXmlValue(String xmlPath, T value, String entityFieldName) {",
        "        if (value == null) {",
        "            throw new IllegalArgumentException(\"Missing required XML field \" + xmlPath + \" mapped to \" + entityFieldName);",
        "        }",
        "        return value;",
        "    }",
        "",
        "    private String asStringValue(String fieldName, Object value) {",
        "        return value == null ? null : String.valueOf(value);",
        "    }",
        "",
        "    private Long asLongValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof Number number) {",
        "            return number.longValue();",
        "        }",
        "        try {",
        "            return Long.valueOf(value.toString().trim());",
        "        } catch (RuntimeException ex) {",
        "            throw new IllegalArgumentException(\"Invalid integer value for XML field \" + fieldName + \".\");",
        "        }",
        "    }",
        "",
        "    private BigDecimal asBigDecimalValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof BigDecimal decimal) {",
        "            return decimal;",
        "        }",
        "        if (value instanceof Number number) {",
        "            return BigDecimal.valueOf(number.doubleValue());",
        "        }",
        "        try {",
        "            return new BigDecimal(value.toString().trim());",
        "        } catch (RuntimeException ex) {",
        "            throw new IllegalArgumentException(\"Invalid decimal value for XML field \" + fieldName + \".\");",
        "        }",
        "    }",
        "",
        "    private Boolean asBooleanValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof Boolean bool) {",
        "            return bool;",
        "        }",
        "        String text = value.toString().trim();",
        "        if (text.equalsIgnoreCase(\"true\")) {",
        "            return Boolean.TRUE;",
        "        }",
        "        if (text.equalsIgnoreCase(\"false\")) {",
        "            return Boolean.FALSE;",
        "        }",
        "        throw new IllegalArgumentException(\"Invalid boolean value for XML field \" + fieldName + \".\");",
        "    }",
        "",
        "    private LocalDate asLocalDateValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof LocalDate date) {",
        "            return date;",
        "        }",
        "        try {",
        "            return LocalDate.parse(value.toString().trim());",
        "        } catch (RuntimeException ex) {",
        "            throw new IllegalArgumentException(\"Invalid date value for XML field \" + fieldName + \".\");",
        "        }",
        "    }",
        "",
        "    private LocalDateTime asLocalDateTimeValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof LocalDateTime dateTime) {",
        "            return dateTime;",
        "        }",
        "        if (value instanceof OffsetDateTime offsetDateTime) {",
        "            return offsetDateTime.toLocalDateTime();",
        "        }",
        "        try {",
        "            return LocalDateTime.parse(value.toString().trim());",
        "        } catch (RuntimeException ex) {",
        "            throw new IllegalArgumentException(\"Invalid datetime value for XML field \" + fieldName + \".\");",
        "        }",
        "    }",
        "",
        "    public record XmlIngestRequest(String path) {",
        "    }",
        "",
        "    public record XmlIngestResponse(",
        "            String contractName,",
        "            String entity,",
        "            long parsedCount,",
        "            long persistedCount,",
        "            List<String> errors) {",
        "        static XmlIngestResponse success(String contractName, String entity, long parsedCount, long persistedCount) {",
        "            return new XmlIngestResponse(contractName, entity, parsedCount, persistedCount, List.of());",
        "        }",
        "",
        "        static XmlIngestResponse failure(String contractName, String entity, String error) {",
        "            return new XmlIngestResponse(contractName, entity, 0L, 0L, List.of(error));",
        "        }",
        "    }",
        "",
        "    private static class DuplicateXmlIngestRecordException extends RuntimeException {",
        "        private final String entityName;",
        "",
        "        DuplicateXmlIngestRecordException(String entityName, String message) {",
        "            super(message);",
        "            this.entityName = entityName;",
        "        }",
        "",
        "        String entityName() {",
        "            return entityName;",
        "        }",
        "    }",
        "}",
    ]
    imports = [
        *[f"{root_package}.adapter.xml.{parser_class}" for parser_class in imported_parsers.values()],
        *[f"{root_package}.adapter.xml.{model_class}" for model_class in imported_models.values()],
        *[f"{root_package}.domain.{entity.name}" for entity in imported_entities.values()],
        *[f"{root_package}.repository.{repository_class}" for repository_class in imported_repositories.values()],
        "java.io.IOException",
        "java.math.BigDecimal",
        "java.nio.file.Files",
        "java.nio.file.Path",
        "java.time.LocalDate",
        "java.time.LocalDateTime",
        "java.time.OffsetDateTime",
        "java.util.List",
        "java.util.Locale",
        "org.springframework.beans.factory.annotation.Value",
        "org.springframework.http.HttpStatus",
        "org.springframework.http.ResponseEntity",
        "org.springframework.transaction.annotation.Transactional",
        "org.springframework.web.bind.annotation.PathVariable",
        "org.springframework.web.bind.annotation.PostMapping",
        "org.springframework.web.bind.annotation.RequestBody",
        "org.springframework.web.bind.annotation.RequestMapping",
        "org.springframework.web.bind.annotation.RestController",
    ]
    return _java_file(
        package_name=f"{root_package}.adapter.xml",
        imports=list(dict.fromkeys(imports)),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _xml_ingest_method_lines(ctx: _UpstreamXmlIngestContext) -> list[str]:
    entity = ctx.entity
    entity_var = entity.name[:1].lower() + entity.name[1:]
    model_var = "xmlRecord"
    id_field = entity_id_field(entity)
    id_java_type = _java_type(id_field)
    mapped_id_fields = [
        mapping for mapping in ctx.mappings if canonical_field_name(mapping) == id_field.name
    ]
    lines = [
        f"    private XmlIngestResponse {ctx.ingest_method_name}(Path inputPath) throws Exception {{",
        f"        {ctx.model_class_name} {model_var} = {ctx.parser_var_name}.parse(inputPath);",
        f"        {entity.name} {entity_var} = new {entity.name}();",
    ]
    fields_by_name = {field.name: field for field in entity.fields}
    xml_fields = _xml_field_descriptor_lookup(ctx.contract)
    xml_contract = _require_xml_contract(ctx.contract)
    root_element = str(xml_contract.get("root_element") or ctx.contract.name)
    for mapping in ctx.mappings:
        field_name = canonical_field_name(mapping)
        field = fields_by_name.get(field_name)
        if field is None:
            raise ValueError(
                f"Upstream XML/XSD contract '{ctx.contract.name}' maps to unknown field "
                f"'{mapping.target_path}'."
            )
        xml_field_name = contract_field_name(mapping)
        xml_field = xml_fields[xml_field_name]
        value_expr = _xml_ingest_assignment_expression(
            model_var=model_var,
            xml_field=xml_field,
            entity_field=field,
            entity_name=entity.name,
            xml_path=_xml_runtime_field_path(root_element, xml_field),
        )
        lines.append(
            f"        {entity_var}.set{to_pascal_case(field.name)}({value_expr});"
        )
    if mapped_id_fields:
        id_getter = f"{entity_var}.get{to_pascal_case(id_field.name)}()"
        lines.extend(
            [
                f"        {id_java_type} recordId = {id_getter};",
                f"        if (recordId != null && {ctx.repository_var_name}.existsById(recordId)) {{",
                "            throw new DuplicateXmlIngestRecordException(",
                "                    "
                + _java_code_string_literal(entity.name)
                + ", ",
                "                    "
                + _java_code_string_literal(f"{entity.name} already exists with id: ")
                + " + recordId);",
                "        }",
            ]
        )
    lines.extend(
        [
            f"        {ctx.repository_var_name}.save({entity_var});",
            "        return XmlIngestResponse.success(",
            "                "
            + _java_code_string_literal(ctx.contract.name)
            + ",",
            "                "
            + _java_code_string_literal(entity.name)
            + ",",
            "                1L,",
            "                1L);",
            "    }",
            "",
        ]
    )
    return lines


def _render_xml_output_controller(
    *,
    metadata: MetadataProject,
    contexts: list[_DownstreamXmlOutputContext],
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    constructor_params: list[str] = []
    fields: list[str] = [
        "    @Value(\"${app.xml-output.base-dir:"
        + _isolated_tmp_base_dir_default(metadata.bounded_context, "xml-output")
        + "}\")",
        "    private String outputBaseDir;",
        "",
    ]
    assignments: list[str] = []
    imported_entities: OrderedDict[str, CanonicalEntity] = OrderedDict()
    imported_repositories: OrderedDict[str, str] = OrderedDict()
    imported_serializers: OrderedDict[str, str] = OrderedDict()
    imported_models: OrderedDict[str, str] = OrderedDict()
    for ctx in contexts:
        imported_entities[ctx.entity.name] = ctx.entity
        imported_repositories[ctx.repository_var_name] = f"{ctx.entity.name}Repository"
        imported_serializers[ctx.serializer_var_name] = ctx.serializer_class_name
        imported_models[ctx.model_class_name] = ctx.model_class_name
    for serializer_var, serializer_class in imported_serializers.items():
        fields.append(f"    private final {serializer_class} {serializer_var};")
        constructor_params.append(f"            {serializer_class} {serializer_var}")
        assignments.append(f"        this.{serializer_var} = {serializer_var};")
    for repository_var, repository_class in imported_repositories.items():
        fields.append(f"    private final {repository_class} {repository_var};")
        constructor_params.append(f"            {repository_class} {repository_var}")
        assignments.append(f"        this.{repository_var} = {repository_var};")
    for index in range(len(constructor_params) - 1):
        constructor_params[index] += ","

    switch_cases = [
        "            case "
        + _java_code_string_literal(ctx.contract.name)
        + " -> ResponseEntity.ok("
        + f"{ctx.output_method_name}());"
        for ctx in contexts
    ]
    output_methods: list[str] = []
    for ctx in contexts:
        output_methods.extend(_xml_output_method_lines(ctx))

    body = [
        "@RestController",
        "@RequestMapping(\"/xml\")",
        "public class XmlOutputController {",
        "",
        *fields,
        "",
        "    public XmlOutputController(",
        *constructor_params,
        "    ) {",
        *assignments,
        "    }",
        "",
        "    @PostMapping(\"/output/{contractName}\")",
        "    @Transactional(readOnly = true)",
        "    public ResponseEntity<XmlOutputResponse> output(@PathVariable String contractName) {",
        "        try {",
        "            return switch (contractName) {",
        *switch_cases,
        "                default -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(",
        "                        XmlOutputResponse.failure(contractName, null, \"Unknown downstream XML/XSD contract: \" + contractName));",
        "            };",
        "        } catch (IllegalArgumentException ex) {",
        "            return ResponseEntity.badRequest().body(",
        "                    XmlOutputResponse.failure(contractName, null, ex.getMessage()));",
        "        } catch (IOException ex) {",
        "            return ResponseEntity.badRequest().body(",
        "                    XmlOutputResponse.failure(contractName, null, \"Unable to write XML output file.\"));",
        "        } catch (Exception ex) {",
        "            return ResponseEntity.badRequest().body(",
        "                    XmlOutputResponse.failure(contractName, null, \"XML output failed validation or serialization.\"));",
        "        }",
        "    }",
        "",
        *output_methods,
        "    private Path outputBaseDir() throws IOException {",
        "        Path baseDir = Path.of(outputBaseDir).toAbsolutePath().normalize();",
        "        Files.createDirectories(baseDir);",
        "        return baseDir;",
        "    }",
        "",
        "    private void writeAllOrNothing(List<XmlOutputFile> pendingFiles) throws IOException {",
        "        List<XmlOutputBackupFile> backupFiles = new ArrayList<>();",
        "        try {",
        "            for (XmlOutputFile pendingFile : pendingFiles) {",
        "                Files.writeString(pendingFile.tempPath(), pendingFile.xml(), StandardCharsets.UTF_8);",
        "            }",
        "        } catch (IOException ex) {",
        "            cleanupTempFiles(pendingFiles);",
        "            throw ex;",
        "        }",
        "        try {",
        "            for (XmlOutputFile pendingFile : pendingFiles) {",
        "                Path backupPath = tempOutputPath(pendingFile.outputPath());",
        "                if (Files.exists(pendingFile.outputPath())) {",
        "                    moveAtomically(pendingFile.outputPath(), backupPath);",
        "                    backupFiles.add(new XmlOutputBackupFile(pendingFile.outputPath(), backupPath, true));",
        "                } else {",
        "                    backupFiles.add(new XmlOutputBackupFile(pendingFile.outputPath(), backupPath, false));",
        "                }",
        "            }",
        "        } catch (IOException ex) {",
        "            restoreBackupFiles(backupFiles, ex);",
        "            cleanupTempFiles(pendingFiles);",
        "            throw ex;",
        "        }",
        "        try {",
        "            for (XmlOutputFile pendingFile : pendingFiles) {",
        "                moveAtomically(pendingFile.tempPath(), pendingFile.outputPath());",
        "            }",
        "            cleanupBackupFiles(backupFiles);",
        "        } catch (IOException ex) {",
        "            rollbackPublishedFiles(pendingFiles, backupFiles, ex);",
        "            cleanupTempFiles(pendingFiles);",
        "            throw ex;",
        "        }",
        "    }",
        "",
        "    private Path tempOutputPath(Path outputPath) {",
        "        return outputPath.resolveSibling(\".\" + outputPath.getFileName() + \".\" + UUID.randomUUID() + \".tmp\");",
        "    }",
        "",
        "    private void moveAtomically(Path tempPath, Path outputPath) throws IOException {",
        "        try {",
        "            Files.move(tempPath, outputPath, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);",
        "        } catch (AtomicMoveNotSupportedException ex) {",
        "            Files.move(tempPath, outputPath, StandardCopyOption.REPLACE_EXISTING);",
        "        }",
        "    }",
        "",
        "    private void restoreBackupFiles(List<XmlOutputBackupFile> backupFiles, IOException originalFailure) {",
        "        for (XmlOutputBackupFile backupFile : backupFiles) {",
        "            if (!backupFile.hadOriginal()) {",
        "                continue;",
        "            }",
        "            try {",
        "                if (Files.exists(backupFile.backupPath())) {",
        "                    moveAtomically(backupFile.backupPath(), backupFile.outputPath());",
        "                }",
        "            } catch (IOException rollbackFailure) {",
        "                originalFailure.addSuppressed(rollbackFailure);",
        "            }",
        "        }",
        "    }",
        "",
        "    private void rollbackPublishedFiles(",
        "            List<XmlOutputFile> pendingFiles,",
        "            List<XmlOutputBackupFile> backupFiles,",
        "            IOException originalFailure) {",
        "        for (XmlOutputFile pendingFile : pendingFiles) {",
        "            try {",
        "                Files.deleteIfExists(pendingFile.outputPath());",
        "            } catch (IOException rollbackFailure) {",
        "                originalFailure.addSuppressed(rollbackFailure);",
        "            }",
        "        }",
        "        restoreBackupFiles(backupFiles, originalFailure);",
        "    }",
        "",
        "    private void cleanupTempFiles(List<XmlOutputFile> pendingFiles) {",
        "        for (XmlOutputFile pendingFile : pendingFiles) {",
        "            try {",
        "                Files.deleteIfExists(pendingFile.tempPath());",
        "            } catch (IOException ignored) {",
        "                // Best-effort cleanup only.",
        "            }",
        "        }",
        "    }",
        "",
        "    private void cleanupBackupFiles(List<XmlOutputBackupFile> backupFiles) {",
        "        for (XmlOutputBackupFile backupFile : backupFiles) {",
        "            try {",
        "                Files.deleteIfExists(backupFile.backupPath());",
        "            } catch (IOException ignored) {",
        "                // Best-effort cleanup only.",
        "            }",
        "        }",
        "    }",
        "",
        "    private String outputFileName(String contractSlug, Object entityId, int index) {",
        "        String idToken = entityId == null ? String.format(\"%05d\", index) : String.valueOf(entityId);",
        "        String safeId = idToken.replaceAll(\"[^A-Za-z0-9._-]\", \"-\");",
        "        if (safeId.isBlank()) {",
        "            safeId = String.format(\"%05d\", index);",
        "        }",
        "        return contractSlug + \"-\" + String.format(\"%05d\", index) + \"-\" + safeId + \".xml\";",
        "    }",
        "",
        "    private String asStringValue(String fieldName, Object value) {",
        "        return value == null ? null : String.valueOf(value);",
        "    }",
        "",
        "    private Long asLongValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof Number number) {",
        "            return number.longValue();",
        "        }",
        "        return Long.valueOf(value.toString().trim());",
        "    }",
        "",
        "    private BigDecimal asBigDecimalValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof BigDecimal decimal) {",
        "            return decimal;",
        "        }",
        "        if (value instanceof Number number) {",
        "            return BigDecimal.valueOf(number.doubleValue());",
        "        }",
        "        return new BigDecimal(value.toString().trim());",
        "    }",
        "",
        "    private Boolean asBooleanValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof Boolean bool) {",
        "            return bool;",
        "        }",
        "        return Boolean.valueOf(value.toString().trim());",
        "    }",
        "",
        "    private LocalDate asLocalDateValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof LocalDate date) {",
        "            return date;",
        "        }",
        "        return LocalDate.parse(value.toString().trim());",
        "    }",
        "",
        "    private OffsetDateTime asOffsetDateTimeValue(String fieldName, Object value) {",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        if (value instanceof OffsetDateTime offsetDateTime) {",
        "            return offsetDateTime;",
        "        }",
        "        if (value instanceof LocalDateTime localDateTime) {",
        "            return localDateTime.atOffset(ZoneOffset.UTC);",
        "        }",
        "        return OffsetDateTime.parse(value.toString().trim());",
        "    }",
        "",
        "    public record XmlOutputResponse(",
        "            String contractName,",
        "            String entity,",
        "            long rowCount,",
        "            List<String> filePaths,",
        "            List<String> errors) {",
        "        static XmlOutputResponse success(String contractName, String entity, long rowCount, List<String> filePaths) {",
        "            return new XmlOutputResponse(contractName, entity, rowCount, filePaths, List.of());",
        "        }",
        "",
        "        static XmlOutputResponse failure(String contractName, String entity, String error) {",
        "            return new XmlOutputResponse(contractName, entity, 0L, List.of(), List.of(error));",
        "        }",
        "    }",
        "",
        "    private record XmlOutputFile(Path outputPath, Path tempPath, String xml) {",
        "    }",
        "",
        "    private record XmlOutputBackupFile(Path outputPath, Path backupPath, boolean hadOriginal) {",
        "    }",
        "}",
    ]
    imports = [
        *[f"{root_package}.adapter.xml.{serializer_class}" for serializer_class in imported_serializers.values()],
        *[f"{root_package}.adapter.xml.{model_class}" for model_class in imported_models.values()],
        *[f"{root_package}.domain.{entity.name}" for entity in imported_entities.values()],
        *[f"{root_package}.repository.{repository_class}" for repository_class in imported_repositories.values()],
        "java.io.IOException",
        "java.math.BigDecimal",
        "java.nio.charset.StandardCharsets",
        "java.nio.file.AtomicMoveNotSupportedException",
        "java.nio.file.Files",
        "java.nio.file.Path",
        "java.nio.file.StandardCopyOption",
        "java.time.LocalDate",
        "java.time.LocalDateTime",
        "java.time.OffsetDateTime",
        "java.time.ZoneOffset",
        "java.util.ArrayList",
        "java.util.HashSet",
        "java.util.List",
        "java.util.Set",
        "java.util.UUID",
        "org.springframework.beans.factory.annotation.Value",
        "org.springframework.http.HttpStatus",
        "org.springframework.http.ResponseEntity",
        "org.springframework.transaction.annotation.Transactional",
        "org.springframework.web.bind.annotation.PathVariable",
        "org.springframework.web.bind.annotation.PostMapping",
        "org.springframework.web.bind.annotation.RequestMapping",
        "org.springframework.web.bind.annotation.RestController",
    ]
    return _java_file(
        package_name=f"{root_package}.adapter.xml",
        imports=list(dict.fromkeys(imports)),
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _xml_output_method_lines(ctx: _DownstreamXmlOutputContext) -> list[str]:
    entity = ctx.entity
    entity_var = entity.name[:1].lower() + entity.name[1:]
    id_field = entity_id_field(entity)
    id_getter = f"get{to_pascal_case(id_field.name)}"
    model_var = "model"
    lines = [
        f"    private XmlOutputResponse {ctx.output_method_name}() throws Exception {{",
        "        Path baseDir = outputBaseDir();",
        f"        List<{entity.name}> records = {ctx.repository_var_name}.findAll();",
        "        List<XmlOutputFile> pendingFiles = new ArrayList<>();",
        "        List<String> filePaths = new ArrayList<>();",
        "        Set<String> outputFileNames = new HashSet<>();",
        "        int index = 0;",
        f"        for ({entity.name} {entity_var} : records) {{",
        f"            {ctx.model_class_name} {model_var} = new {ctx.model_class_name}();",
    ]
    fields_by_name = {field.name: field for field in entity.fields}
    xml_fields = _xml_field_descriptor_lookup(ctx.contract)
    for mapping in ctx.mappings:
        source_field_name = mapping.source_path.split(".", 1)[1]
        entity_field = fields_by_name.get(source_field_name)
        if entity_field is None:
            raise ValueError(
                f"Downstream XML/XSD contract '{ctx.contract.name}' maps from unknown field "
                f"'{mapping.source_path}'."
            )
        xml_field_name = output_field_name(mapping)
        xml_field = xml_fields[xml_field_name]
        setter_suffix = to_pascal_case(str(xml_field["java_name"]))
        value_expr = _xml_output_assignment_expression(
            entity_var=entity_var,
            entity_field=entity_field,
            xml_field=xml_field,
            model_class_name=ctx.model_class_name,
        )
        lines.append(f"            {model_var}.set{setter_suffix}({value_expr});")
    lines.extend(
        [
            f"            String xml = {ctx.serializer_var_name}.serialize({model_var});",
            "            index++;",
            "            String fileName = outputFileName(",
            "                    "
            + _java_code_string_literal(ctx.contract_slug)
            + ",",
            f"                    {entity_var}.{id_getter}(),",
            "                    index);",
            "            if (!outputFileNames.add(fileName)) {",
            "                throw new IllegalArgumentException(\"XML output filename collision for \" + fileName);",
            "            }",
            "            Path outputPath = baseDir.resolve(fileName);",
            "            pendingFiles.add(new XmlOutputFile(outputPath, tempOutputPath(outputPath), xml));",
            "        }",
            "        writeAllOrNothing(pendingFiles);",
            "        for (XmlOutputFile pendingFile : pendingFiles) {",
            "            filePaths.add(pendingFile.outputPath().getFileName().toString());",
            "        }",
            "        return XmlOutputResponse.success(",
            "                "
            + _java_code_string_literal(ctx.contract.name)
            + ",",
            "                "
            + _java_code_string_literal(entity.name)
            + ",",
            "                records.size(),",
            "                filePaths);",
            "    }",
            "",
        ]
    )
    return lines


def _xml_ingest_assignment_expression(
    *,
    model_var: str,
    xml_field: dict,
    entity_field: CanonicalField,
    entity_name: str,
    xml_path: str | None = None,
) -> str:
    getter = f"{model_var}.get{to_pascal_case(str(xml_field['java_name']))}()"
    field_name_literal = _java_code_string_literal(str(xml_field["name"]))
    xml_path_literal = _java_code_string_literal(str(xml_path or xml_field["name"]))
    if entity_field.required:
        getter = (
            "requiredXmlValue("
            + xml_path_literal
            + ", "
            + getter
            + ", "
            + _java_code_string_literal(f"{entity_name}.{entity_field.name}")
            + ")"
        )
    if xml_field.get("enum_values"):
        if entity_field.type == CanonicalFieldType.STRING:
            return f"{getter} == null ? null : {getter}.wireValue()"
        raise ValueError(
            f"XML/XSD enum field '{xml_field['name']}' can only map to STRING canonical fields."
        )
    xml_type = str(xml_field.get("type") or "string").lower()
    if entity_field.type == CanonicalFieldType.STRING:
        return getter if xml_type == "string" else f"asStringValue({field_name_literal}, {getter})"
    if entity_field.type == CanonicalFieldType.INTEGER:
        return getter if xml_type in {"integer", "int", "long"} else f"asLongValue({field_name_literal}, {getter})"
    if entity_field.type == CanonicalFieldType.DECIMAL:
        return getter if xml_type == "decimal" else f"asBigDecimalValue({field_name_literal}, {getter})"
    if entity_field.type == CanonicalFieldType.BOOLEAN:
        return getter if xml_type == "boolean" else f"asBooleanValue({field_name_literal}, {getter})"
    if entity_field.type == CanonicalFieldType.DATE:
        return getter if xml_type == "date" else f"asLocalDateValue({field_name_literal}, {getter})"
    if entity_field.type == CanonicalFieldType.DATETIME:
        if xml_type == "datetime":
            return f"{getter} == null ? null : {getter}.toLocalDateTime()"
        return f"asLocalDateTimeValue({field_name_literal}, {getter})"
    return getter


def _xml_output_assignment_expression(
    *,
    entity_var: str,
    entity_field: CanonicalField,
    xml_field: dict,
    model_class_name: str,
) -> str:
    getter = f"{entity_var}.get{to_pascal_case(entity_field.name)}()"
    if xml_field.get("enum_values"):
        enum_name = _xml_enum_class_name(xml_field)
        return (
            f"{getter} == null ? null : {model_class_name}.{enum_name}.fromWireValue("
            f"asStringValue({_java_code_string_literal(str(xml_field['name']))}, {getter}))"
        )
    xml_type = str(xml_field.get("type") or "string").lower()
    field_name_literal = _java_code_string_literal(str(xml_field["name"]))
    if xml_type == "string":
        if entity_field.type == CanonicalFieldType.STRING:
            return getter
        return f"asStringValue({field_name_literal}, {getter})"
    if xml_type in {"integer", "int", "long"}:
        return getter if entity_field.type == CanonicalFieldType.INTEGER else f"asLongValue({field_name_literal}, {getter})"
    if xml_type == "decimal":
        return getter if entity_field.type == CanonicalFieldType.DECIMAL else f"asBigDecimalValue({field_name_literal}, {getter})"
    if xml_type == "boolean":
        return getter if entity_field.type == CanonicalFieldType.BOOLEAN else f"asBooleanValue({field_name_literal}, {getter})"
    if xml_type == "date":
        return getter if entity_field.type == CanonicalFieldType.DATE else f"asLocalDateValue({field_name_literal}, {getter})"
    if xml_type == "datetime":
        return f"asOffsetDateTimeValue({field_name_literal}, {getter})"
    return getter


def _file_ingest_converter(field: CanonicalField) -> str:
    if field.type == CanonicalFieldType.INTEGER:
        return "asLong"
    if field.type == CanonicalFieldType.DECIMAL:
        return "asBigDecimal"
    if field.type == CanonicalFieldType.BOOLEAN:
        return "asBoolean"
    if field.type == CanonicalFieldType.DATE:
        return "asLocalDate"
    if field.type == CanonicalFieldType.DATETIME:
        return "asLocalDateTime"
    return "asString"


def _safe_property_segment(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return normalized or fallback


def _isolated_tmp_base_dir_default(bounded_context: str, leaf: str) -> str:
    segment = _safe_property_segment(bounded_context, "app")
    return (
        "${java.io.tmpdir}/edgeforge-"
        + segment
        + "-${APP_INSTANCE_ID:${random.uuid}}/"
        + leaf
    )


def _is_minor_unit_output_mapping(
    mapping: FieldMapping,
    *,
    entity_fields: dict[str, CanonicalField],
) -> bool:
    field_name = mapping.source_path.split(".", 1)[1]
    field = entity_fields.get(field_name)
    if mapping.type_coercion == _MINOR_UNIT_TYPE_COERCION:
        if field is None:
            raise ValueError(
                f"Mapping type_coercion '{_MINOR_UNIT_TYPE_COERCION}' references unknown "
                f"source field '{mapping.source_path}'."
            )
        if field.type != CanonicalFieldType.DECIMAL:
            raise ValueError(
                f"Mapping type_coercion '{_MINOR_UNIT_TYPE_COERCION}' requires DECIMAL "
                f"source field '{mapping.source_path}', got '{field.type.value}'."
            )
        return True
    if field is None or field.type != CanonicalFieldType.DECIMAL:
        return False
    target_name = output_field_name(mapping)
    if target_name.endswith(("_minor", "_minor_units")):
        return True
    return target_name.endswith("MinorUnits")


def _render_staging_writer(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    entity_mappings = [
        m for m in metadata.mappings
        if m.direction == MappingDirection.CANONICAL_TO_HANDOFF
        and m.source_path.startswith(f"{entity.name}.")
    ]
    contract_names = {m.contract_name for m in entity_mappings}
    if not contract_names:
        raise ValueError(
            f"No staging-table mappings found for entity '{entity.name}'"
        )
    if len(contract_names) > 1:
        raise ValueError(
            f"Entity '{entity.name}' maps to multiple staging contracts "
            f"{sorted(contract_names)!r}; each entity must map to exactly one."
        )
    handoff_contract = next(iter(contract_names))
    mappings = entity_mappings
    handoff_metadata = next(
        contract
        for contract in metadata.contracts
        if contract.name == handoff_contract and contract.type == "staging-table"
    )
    table_name = handoff_metadata.physical_name or handoff_contract.replace("-", "_")
    run_semantics = handoff_metadata.run_semantics
    if run_semantics is not None:
        mappings = sorted(
            mappings,
            key=lambda mapping: (output_field_name(mapping), mapping.source_path),
        )
    operational_columns = _staging_operational_columns(metadata, table_name)
    insert_columns = [
        *[column.name for column in operational_columns],
        *[output_field_name(mapping) for mapping in mappings],
    ]
    column_names = ", ".join(insert_columns)
    placeholders = ", ".join("?" for _ in insert_columns)
    run_id_column = _staging_run_id_column(operational_columns)
    entity_var = entity.name[:1].lower() + entity.name[1:]
    body = [
        "@Component",
        f"public class {entity.name}StagingWriter {{",
        "",
        "    private final JdbcTemplate jdbcTemplate;",
        "",
        f"    public {entity.name}StagingWriter(JdbcTemplate jdbcTemplate) {{",
        "        this.jdbcTemplate = jdbcTemplate;",
        "    }",
        "",
    ]
    if run_semantics is not None:
        pass
    elif run_id_column:
        body.extend(
            [
                "    public void clear(String runId) {",
                f"        jdbcTemplate.update(\"DELETE FROM {table_name} WHERE {run_id_column.name} = ?\", runId);",
                "    }",
                "",
            ]
        )
    else:
        body.extend(
            [
                "    public void clear() {",
                f"        jdbcTemplate.update(\"DELETE FROM {table_name}\");",
                "    }",
                "",
            ]
        )
    operational_roles = {column.role for column in operational_columns}
    write_params = [f"{entity.name} {entity_var}"]
    if "run_id" in operational_roles:
        write_params.append("String runId")
    if "business_date" in operational_roles:
        write_params.append("LocalDate businessDate")
    write_signature = f"    public void write({', '.join(write_params)}) {{"
    value_lines = [*_staging_operational_value_lines(operational_columns)]
    mapped_values: dict[str, str] = {}
    for mapping in mappings:
        field_name = mapping.source_path.split(".", 1)[1]
        getter = f"{entity_var}.get{to_pascal_case(field_name)}()"
        value_lines.append(getter)
        mapped_values[output_field_name(mapping).lower()] = getter
    insert_sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"
    h2_update_sql: str | None = None
    conflict_value_lines: list[str] = []
    mutable_value_lines: list[str] = []
    if run_semantics is not None:
        conflict_columns = [run_semantics.physical_run_id_column, *run_semantics.dedup_key]
        dedup_keys = {column.lower() for column in run_semantics.dedup_key}
        mutable_columns = [
            output_field_name(mapping)
            for mapping in mappings
            if output_field_name(mapping).lower() not in dedup_keys
        ]
        if target_profile.runtime_database_dependency == "postgresql":
            update_assignments = [
                *[f"{column} = EXCLUDED.{column}" for column in mutable_columns],
                *(
                    ["staging_status = 'READY'"]
                    if "staging_status" in operational_roles
                    else []
                ),
            ]
            if update_assignments:
                insert_sql += (
                    f" ON CONFLICT ({', '.join(conflict_columns)}) DO UPDATE SET "
                    + ", ".join(update_assignments)
                )
            else:
                insert_sql += f" ON CONFLICT ({', '.join(conflict_columns)}) DO NOTHING"
        elif target_profile.runtime_database_dependency == "h2":
            update_assignments = [
                *[f"{column} = ?" for column in mutable_columns],
                *(
                    ["staging_status = 'READY'"]
                    if "staging_status" in operational_roles
                    else []
                ),
            ]
            mutable_value_lines = [mapped_values[column.lower()] for column in mutable_columns]
            conflict_value_lines = [
                "runId",
                *[mapped_values[column.lower()] for column in run_semantics.dedup_key],
            ]
            if update_assignments:
                h2_update_sql = (
                    f"UPDATE {table_name} SET {', '.join(update_assignments)} WHERE "
                    + " AND ".join(f"{column} = ?" for column in conflict_columns)
                )
        else:
            raise ValueError(
                "M5a-S3 requires a profile-pinned staging upsert for target profile "
                f"'{target_profile.name}'."
            )
    body.append(write_signature)
    is_h2_upsert = (
        run_semantics is not None
        and target_profile.runtime_database_dependency == "h2"
    )
    if is_h2_upsert:
        body.extend(
            [
                "        try {",
                "            jdbcTemplate.update(",
                f"                \"{insert_sql}\",",
            ]
        )
        _append_java_arguments(body, value_lines, indent="                ")
        body.extend(
            [
                "            );",
                "        } catch (DuplicateKeyException alreadyPresent) {",
                "            // The existing conflict key is refreshed inside this chunk transaction.",
            ]
        )
        if h2_update_sql is not None:
            body.extend(
                [
                    "            jdbcTemplate.update(",
                    f"                \"{h2_update_sql}\",",
                ]
            )
            _append_java_arguments(
                body,
                [*mutable_value_lines, *conflict_value_lines],
                indent="                ",
            )
            body.append("            );")
        body.append("        }")
        read_sql = (
            f"SELECT COUNT(*) FROM {table_name} WHERE "
            + " AND ".join(f"{column} = ?" for column in conflict_columns)
        )
        body.extend(
            [
                "        Integer persisted = jdbcTemplate.queryForObject(",
                f"            \"{read_sql}\",",
                "            Integer.class,",
            ]
        )
        _append_java_arguments(body, conflict_value_lines, indent="            ")
        body.extend(
            [
                "        );",
                "        if (persisted == null || persisted != 1) {",
                "            throw new IllegalStateException(\"M5a staging upsert did not resolve exactly one row\");",
                "        }",
            ]
        )
    else:
        body.extend(["        jdbcTemplate.update(", f"            \"{insert_sql}\","])
        _append_java_arguments(body, value_lines, indent="            ")
        body.append("        );")
    body.extend(["    }", "}"])
    imports = [
        f"{root_package}.domain.{entity.name}",
        "org.springframework.jdbc.core.JdbcTemplate",
        "org.springframework.stereotype.Component",
    ]
    if "business_date" in operational_roles:
        imports.append("java.time.LocalDate")
    if "created_at" in operational_roles:
        imports.append("java.time.LocalDateTime")
    if "staging_row_id" in operational_roles:
        imports.append("java.util.UUID")
    if is_h2_upsert:
        imports.append("org.springframework.dao.DuplicateKeyException")
    return _java_file(
        package_name=f"{root_package}.adapter.outbound",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _append_java_arguments(body: list[str], values: list[str], *, indent: str) -> None:
    for index, value in enumerate(values):
        suffix = "," if index < len(values) - 1 else ""
        body.append(f"{indent}{value}{suffix}")


class _StagingOperationalColumn:
    def __init__(self, name: str, role: str) -> None:
        self.name = name
        self.role = role


def _staging_operational_columns(
    metadata: MetadataProject,
    table_name: str,
) -> list[_StagingOperationalColumn]:
    ddl_content = metadata.staging_table_ddls.get(table_name)
    if not ddl_content:
        return []
    columns: list[_StagingOperationalColumn] = []
    database = TARGET_PROFILES[metadata.target_profile].runtime_database_dependency
    for column_name in parse_sql_table_columns(ddl_content, database=database):
        role = staging_operational_column_role(column_name)
        if role is not None:
            columns.append(_StagingOperationalColumn(column_name, role))
    return columns


def _staging_run_id_column(
    operational_columns: list[_StagingOperationalColumn],
) -> _StagingOperationalColumn | None:
    for column in operational_columns:
        if column.role == "run_id":
            return column
    return None


def _staging_operational_value_lines(
    operational_columns: list[_StagingOperationalColumn],
) -> list[str]:
    values: list[str] = []
    for column in operational_columns:
        if column.role == "staging_row_id":
            values.append("UUID.randomUUID().toString()")
        elif column.role == "run_id":
            values.append("runId")
        elif column.role == "business_date":
            values.append("businessDate")
        elif column.role == "staging_status":
            values.append('"READY"')
        elif column.role == "created_at":
            values.append("LocalDateTime.now()")
    return values


def _staging_entity_has_run_identity(
    metadata: MetadataProject,
    entity_name: str,
) -> bool:
    table_name = _staging_entity_table_name(metadata, entity_name)
    if table_name is None:
        return False
    return _staging_run_id_column(
        _staging_operational_columns(metadata, table_name)
    ) is not None


def _staging_entity_has_business_date(
    metadata: MetadataProject,
    entity_name: str,
) -> bool:
    table_name = _staging_entity_table_name(metadata, entity_name)
    if table_name is None:
        return False
    return any(
        column.role == "business_date"
        for column in _staging_operational_columns(metadata, table_name)
    )


def _run_semantics_for_entity(
    metadata: MetadataProject,
    entity_name: str,
) -> RunSemanticsMetadata | None:
    """Return the single validated run-semantics binding for an entity."""

    bindings = [
        contract.run_semantics
        for contract in metadata.contracts
        if contract.run_semantics is not None
        and contract.run_semantics.entity_name == entity_name
    ]
    if len(bindings) > 1:
        raise ValueError(
            f"Entity '{entity_name}' has multiple run_semantics bindings; "
            "generation requires exactly one per batch job."
        )
    return bindings[0] if bindings else None


def _staging_entity_table_name(
    metadata: MetadataProject,
    entity_name: str,
) -> str | None:
    contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_HANDOFF
        and mapping.source_path.startswith(f"{entity_name}.")
    }
    if len(contract_names) != 1:
        return None
    contract_name = next(iter(contract_names))
    for contract in metadata.contracts:
        if contract.name == contract_name and contract.type == "staging-table":
            return contract.physical_name or contract.name.replace("-", "_")
    return None


# ---------------------------------------------------------------------------
# Batch job


def _batch_reader_lines(entity, entity_var, id_field, repository, target_profile):
    sort = f'Map.of("{id_field.name}", Sort.Direction.ASC)'
    if target_profile.experimental_boot41:
        return [
            f"        RepositoryItemReader<{entity.name}> reader = new RepositoryItemReader<>({repository}, {sort});",
            f'        reader.setName("{entity_var}EodReader");',
            '        reader.setMethodName("findAll");',
            "        reader.setPageSize(chunkSize);",
        ]
    return [
        f"        RepositoryItemReader<{entity.name}> reader = new RepositoryItemReader<>();",
        f"        reader.setRepository({repository});",
        '        reader.setMethodName("findAll");',
        "        reader.setPageSize(chunkSize);",
        f"        reader.setSort({sort});",
    ]


def _batch_java_file(
    *, package_name: str, imports: list[str], body: list[str],
    source_manifest: str, target_profile: str, generation_run_id: str,
) -> str:
    """Select exact framework imports without rewriting domain names or body text."""

    if TARGET_PROFILES[target_profile].experimental_boot41:
        moved = {
            "org.springframework.batch.core.Job": "org.springframework.batch.core.job.Job",
            "org.springframework.batch.core.JobExecution": "org.springframework.batch.core.job.JobExecution",
            "org.springframework.batch.core.JobInstance": "org.springframework.batch.core.job.JobInstance",
            "org.springframework.batch.core.JobParameters": "org.springframework.batch.core.job.parameters.JobParameters",
            "org.springframework.batch.core.JobParametersBuilder": "org.springframework.batch.core.job.parameters.JobParametersBuilder",
            "org.springframework.batch.core.Step": "org.springframework.batch.core.step.Step",
            "org.springframework.batch.core.StepExecution": "org.springframework.batch.core.step.StepExecution",
            "org.springframework.batch.core.StepExecutionListener": "org.springframework.batch.core.listener.StepExecutionListener",
            "org.springframework.batch.core.repository.JobExecutionAlreadyRunningException": "org.springframework.batch.core.launch.JobExecutionAlreadyRunningException",
            "org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException": "org.springframework.batch.core.launch.JobInstanceAlreadyCompleteException",
        }
        imports = [
            moved.get(value, value.replace("org.springframework.batch.item.", "org.springframework.batch.infrastructure.item.")
                      .replace("org.springframework.batch.repeat.", "org.springframework.batch.infrastructure.repeat."))
            for value in imports
        ]
    return _java_file(
        package_name=package_name, imports=imports, body=body,
        source_manifest=source_manifest, target_profile=target_profile,
        generation_run_id=generation_run_id,
    )
# ---------------------------------------------------------------------------

def _render_batch_job(
    *,
    entity: CanonicalEntity,
    root_package: str,
    bounded_context: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
    has_staging_writer: bool = True,
    has_file_writer: bool = False,
    file_writer_contexts: list[_DownstreamFileWriterContext] | None = None,
    file_extension: str = "dat",
    has_file_control_records: bool = False,
    staging_has_run_identity: bool = False,
    staging_has_business_date: bool = False,
    run_semantics: RunSemanticsMetadata | None = None,
) -> str:
    if run_semantics is not None:
        if not has_staging_writer:
            raise ValueError(
                f"M5a-S2 run_semantics for '{entity.name}' requires a staging writer."
            )
        if has_file_writer or file_writer_contexts:
            raise ValueError(
                f"M5a-S2 run_semantics for '{entity.name}' cannot share an EOD file job."
            )
        return _render_run_semantics_batch_job(
            entity=entity,
            root_package=root_package,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
            staging_has_business_date=staging_has_business_date,
        )
    entity_var = entity.name[:1].lower() + entity.name[1:]
    file_writer_contexts = list(file_writer_contexts or [])
    if len(file_writer_contexts) > 1:
        return _render_multi_file_batch_job(
            entity=entity,
            root_package=root_package,
            bounded_context=bounded_context,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
            file_writer_contexts=file_writer_contexts,
            has_staging_writer=has_staging_writer,
            staging_has_run_identity=staging_has_run_identity,
            staging_has_business_date=staging_has_business_date,
        )
    if file_writer_contexts:
        has_file_writer = True
        file_writer_class_name = file_writer_contexts[0].writer_class_name
        file_extension = file_writer_contexts[0].file_extension
        has_file_control_records = file_writer_contexts[0].has_control_records
    else:
        file_writer_class_name = f"{entity.name}EodHandoffFileWriter"
    eod_dir_default = f"./{bounded_context}-eod"
    id_field = entity_id_field(entity)
    staging_write_args = ["record"]
    if staging_has_run_identity:
        staging_write_args.append('context.getString("runId")')
    if staging_has_business_date:
        staging_write_args.append('LocalDate.parse(context.getString("businessDate"))')

    step_params = [
        "        JobRepository jobRepository,",
        "        PlatformTransactionManager transactionManager,",
        f"        RepositoryItemReader<{entity.name}> {entity_var}EodReader,",
        f"        ItemWriter<{entity.name}> {entity_var}EodWriter,",
        f"        StepExecutionListener {entity_var}EodStepListener",
    ]
    before_step_staging_lines: list[str] = []
    if has_staging_writer:
        if staging_has_run_identity:
            before_step_staging_lines.append("                String runId = resolveRunId(stepExecution);")
        if staging_has_business_date:
            before_step_staging_lines.extend(
                [
                    "                LocalDate businessDate = resolveBusinessDate(stepExecution);",
                    "                context.putString(\"businessDate\", businessDate.toString());",
                ]
            )
        if staging_has_run_identity:
            before_step_staging_lines.extend(
                [
                    "                context.putString(\"runId\", runId);",
                    "                stagingWriter.clear(runId);",
                ]
            )
            if staging_has_business_date:
                before_step_staging_lines.extend(
                    [
                        "                log.info(\"EOD job {} staging run initialized with runId={} businessDate={}\",",
                        "                        stepExecution.getJobExecution().getJobInstance().getJobName(),",
                        "                        runId,",
                        "                        businessDate);",
                    ]
                )
            else:
                before_step_staging_lines.extend(
                    [
                        "                log.info(\"EOD job {} staging run initialized with runId={}\",",
                        "                        stepExecution.getJobExecution().getJobInstance().getJobName(),",
                        "                        runId);",
                    ]
                )
        else:
            before_step_staging_lines.append("                stagingWriter.clear();")
            if staging_has_business_date:
                before_step_staging_lines.extend(
                    [
                        "                log.info(\"EOD job {} staging replace-run initialized with businessDate={}\",",
                        "                        stepExecution.getJobExecution().getJobInstance().getJobName(),",
                        "                        businessDate);",
                    ]
                )

    writer_param_lines = []
    if has_staging_writer:
        writer_param_lines.append(f"            {entity.name}StagingWriter stagingWriter")
    if has_file_writer:
        if writer_param_lines:
            writer_param_lines[-1] += ","
        writer_param_lines.append(f"            {file_writer_class_name} handoffFileWriter")

    listener_param_lines = []
    if has_staging_writer:
        listener_param_lines.append(f"            {entity.name}StagingWriter stagingWriter")
    if has_file_control_records:
        if listener_param_lines:
            listener_param_lines[-1] += ","
        listener_param_lines.append(f"            {file_writer_class_name} handoffFileWriter")

    body = [
        "@Configuration",
        f"public class {entity.name}EodBatchJob {{",
        "",
        f"    private static final Logger log = LoggerFactory.getLogger({entity.name}EodBatchJob.class);",
        "",
        f"    @Value(\"${{app.eod.output-dir:{eod_dir_default}}}\")",
        "    private String eodOutputDir;",
        "",
        "    @Value(\"${app.eod.business-date:}\")",
        "    private String configuredBusinessDate;",
        "",
        "    @Value(\"${app.eod.chunk-size:500}\")",
        "    private int chunkSize;",
        "",
        "    @Bean",
        f"    public Job {entity_var}EodJob(",
        "            JobRepository jobRepository,",
        f"            Step {entity_var}EodStep"
        + ("," if has_file_writer else ""),
        *([f"            Step {entity_var}EodFinalizeStep"] if has_file_writer else []),
        "    ) {",
        f"        return new JobBuilder(\"{entity_var}EodJob\", jobRepository)",
        f"            .start({entity_var}EodStep)",
        *([f"            .next({entity_var}EodFinalizeStep)"] if has_file_writer else []),
        "            .build();",
        "    }",
        "",
        "    @Bean",
        f"    public Step {entity_var}EodStep(",
        *step_params,
        "    ) {",
        f"        return new StepBuilder(\"{entity_var}EodStep\", jobRepository)",
        f"            .<{entity.name}, {entity.name}>chunk(chunkSize, transactionManager)",
        f"            .reader({entity_var}EodReader)",
        f"            .writer({entity_var}EodWriter)",
        f"            .listener({entity_var}EodStepListener)",
        "            .build();",
        "    }",
        "",
        *(
            [
                "    @Bean",
                f"    public Step {entity_var}EodFinalizeStep(",
                "        JobRepository jobRepository,",
                "        PlatformTransactionManager transactionManager"
                + ("," if has_file_control_records else ""),
                *(
                    [f"        {file_writer_class_name} handoffFileWriter"]
                    if has_file_control_records
                    else []
                ),
                "    ) {",
                f"        return new StepBuilder(\"{entity_var}EodFinalizeStep\", jobRepository)",
                "            .tasklet((contribution, chunkContext) -> {",
                "                StepExecution stepExecution = currentStepExecution();",
                "                var context = stepExecution.getJobExecution().getExecutionContext();",
                "                long recordCount = context.getLong(\"recordCount\", 0L);",
                "                Path outputFile = Path.of(context.getString(\"outputFile\"));",
                "                Path tempFile = Path.of(context.getString(\"tempOutputFile\"));",
                "                if (recordCount > 0) {",
                *(
                    [
                        "                    Object fileTotalValue = context.get(\"fileTotal\");",
                        "                    BigDecimal fileTotal = fileTotalValue instanceof BigDecimal decimal ? decimal : BigDecimal.ZERO;",
                        "                    handoffFileWriter.finishFile(tempFile, recordCount, fileTotal);",
                    ]
                    if has_file_control_records
                    else []
                ),
                "                    moveReplacing(tempFile, outputFile);",
                "                    context.putString(\"outputStatus\", \"CREATED\");",
                "                    log.info(\"EOD job {} finalized {} records at {}\",",
                "                            stepExecution.getJobExecution().getJobInstance().getJobName(),",
                "                            recordCount,",
                "                            outputFile);",
                "                } else {",
                "                    deleteTempQuietly(tempFile);",
                "                    context.putString(\"outputStatus\", \"SKIPPED\");",
                "                    context.putString(\"skipReason\", \"NO_RECORDS\");",
                "                    log.info(\"EOD job {} skipped output because no records were read; outputFile={}\",",
                "                            stepExecution.getJobExecution().getJobInstance().getJobName(),",
                "                            outputFile);",
                "                }",
                "                return RepeatStatus.FINISHED;",
                "            }, transactionManager)",
                "            .build();",
                "    }",
                "",
            ]
            if has_file_writer
            else []
        ),
        "",
        "    @Bean",
        f"    public RepositoryItemReader<{entity.name}> {entity_var}EodReader(",
        f"            {entity.name}Repository {entity_var}Repository) {{",
        *_batch_reader_lines(entity, entity_var, id_field, f"{entity_var}Repository", target_profile),
        "        return reader;",
        "    }",
        "",
        "    @Bean",
        f"    public ItemWriter<{entity.name}> {entity_var}EodWriter(",
        *writer_param_lines,
        "    ) {",
        "        return items -> {",
        "            StepExecution stepExecution = currentStepExecution();",
        "            var context = stepExecution.getJobExecution().getExecutionContext();",
            "            long recordCount = context.getLong(\"recordCount\", 0L);",
            "            int chunkCount = 0;",
            *(
                [
                    "            Object fileTotalValue = context.get(\"fileTotal\");",
                    "            BigDecimal fileTotal = fileTotalValue instanceof BigDecimal decimal ? decimal : BigDecimal.ZERO;",
                ]
                if has_file_control_records
                else []
            ),
            *(
            [
                "            Path tempOutputFile = Path.of(",
                "                    context.getString(\"tempOutputFile\"));",
            ]
            if has_file_writer
            else []
        ),
            f"            for ({entity.name} record : items) {{",
            *(
                [f"                stagingWriter.write({', '.join(staging_write_args)});"]
                if has_staging_writer
                else []
            ),
            *(
                ["                handoffFileWriter.write(record, tempOutputFile);"]
                if has_file_writer else []
            ),
            *(
                ["                fileTotal = fileTotal.add(handoffFileWriter.dataTotal(record));"]
                if has_file_control_records
                else []
            ),
            "                chunkCount++;",
            "            }",
            "            context.putLong(\"recordCount\", recordCount + chunkCount);",
            *(
                ["            context.put(\"fileTotal\", fileTotal);"]
                if has_file_control_records
                else []
            ),
            "        };",
        "    }",
        "",
        "    @Bean",
        f"    public StepExecutionListener {entity_var}EodStepListener(",
        *listener_param_lines,
        "    ) {",
        "        return new StepExecutionListener() {",
        "            @Override",
        "            public void beforeStep(StepExecution stepExecution) {",
        "                var context = stepExecution.getJobExecution().getExecutionContext();",
        *before_step_staging_lines,
                "                context.putLong(\"recordCount\", 0L);",
        *(
            [
                "                context.put(\"fileTotal\", BigDecimal.ZERO);",
            ]
            if has_file_control_records
            else []
        ),
                "                context.putString(\"outputStatus\", \"CREATED\");",
        *(
            [
                "                try {",
                "                    Path outputFile = outputFile();",
                "                    Files.createDirectories(outputFile.getParent());",
                "                    Path tempFile = tempFile(outputFile, stepExecution);",
                "                    Files.deleteIfExists(tempFile);",
                "                    Files.createFile(tempFile);",
                "                    context.putString(\"outputFile\", outputFile.toString());",
                "                    context.putString(\"tempOutputFile\", tempFile.toString());",
                *(
                    [
                        "                    String outputRunId = resolveOutputRunId(stepExecution);",
                        "                    context.putString(\"outputRunId\", outputRunId);",
                        "                    handoffFileWriter.startFile(tempFile, outputRunId);",
                    ]
                    if has_file_control_records
                    else []
                ),
                "                } catch (IOException ex) {",
                "                    throw new IllegalStateException(\"Failed to prepare EOD output file\", ex);",
                "                }",
            ]
            if has_file_writer
            else []
        ),
        "            }",
        "",
        "            @Override",
        "            public ExitStatus afterStep(StepExecution stepExecution) {",
        "                var context = stepExecution.getJobExecution().getExecutionContext();",
        "                long recordCount = context.getLong(\"recordCount\", 0L);",
        *(
            [
                "                if (stepExecution.getStatus() != BatchStatus.COMPLETED) {",
                "                    Path outputFile = Path.of(context.getString(\"outputFile\"));",
                "                    Path tempFile = Path.of(context.getString(\"tempOutputFile\"));",
                "                    deleteTempQuietly(tempFile);",
                "                    context.putString(\"outputStatus\", \"FAILED\");",
                "                    log.warn(\"EOD job {} failed after {} records; temp output removed; outputFile={}\",",
                "                            stepExecution.getJobExecution().getJobInstance().getJobName(),",
                "                            recordCount,",
                "                            outputFile);",
                "                }",
            ]
            if has_file_writer
            else [
                "                if (stepExecution.getStatus() == BatchStatus.COMPLETED && recordCount == 0) {",
                "                    context.putString(\"outputStatus\", \"SKIPPED\");",
                "                    context.putString(\"skipReason\", \"NO_RECORDS\");",
                "                    log.info(\"EOD job {} skipped staging output because no records were read\",",
                "                            stepExecution.getJobExecution().getJobInstance().getJobName());",
                "                } else if (stepExecution.getStatus() != BatchStatus.COMPLETED) {",
                "                    context.putString(\"outputStatus\", \"FAILED\");",
                "                    log.warn(\"EOD job {} failed after {} staging records\",",
                "                            stepExecution.getJobExecution().getJobInstance().getJobName(),",
                "                            recordCount);",
                "                } else {",
                "                    context.putString(\"outputStatus\", \"CREATED\");",
                "                    log.info(\"EOD job {} completed with {} staging records; status={}\",",
                "                            stepExecution.getJobExecution().getJobInstance().getJobName(),",
                "                            recordCount,",
                "                            context.getString(\"outputStatus\"));",
                "                }",
            ]
        ),
        "                return stepExecution.getExitStatus();",
        "            }",
        "        };",
        "    }",
        "",
        "    private StepExecution currentStepExecution() {",
        "        return StepSynchronizationManager.getContext().getStepExecution();",
        "    }",
        *(
            [
                "",
                "    private Path outputFile() {",
                "        String dateStamp = LocalDate.now()",
                "                .format(DateTimeFormatter.ofPattern(\"yyyyMMdd\"));",
                "        Path outputDir = Path.of(eodOutputDir);",
                f"        return outputDir.resolve(\"{entity_var}-eod-\" + dateStamp + \".{file_extension}\");",
                "    }",
                "",
                "    private Path tempFile(Path outputFile, StepExecution stepExecution) {",
                "        return outputFile.resolveSibling(",
                "                outputFile.getFileName() + \".tmp-\" + stepExecution.getJobExecutionId());",
                "    }",
                "",
                "    private void moveReplacing(Path tempFile, Path outputFile) throws IOException {",
                "        try {",
                "            Files.move(tempFile, outputFile, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);",
                "        } catch (AtomicMoveNotSupportedException ex) {",
                "            Files.move(tempFile, outputFile, StandardCopyOption.REPLACE_EXISTING);",
                "        }",
                "    }",
                "",
                "    private void deleteTempQuietly(Path tempFile) {",
                "        try {",
                "            Files.deleteIfExists(tempFile);",
                "        } catch (IOException ex) {",
                "            log.warn(\"Failed to delete temporary EOD output file {}\", tempFile, ex);",
                "        }",
                "    }",
            ]
            if has_file_writer
            else []
        ),
        *(
            [
                "",
                "    private String resolveOutputRunId(StepExecution stepExecution) {",
                "        String runId = stepExecution.getJobParameters().getString(\"runId\");",
                "        if (runId == null || runId.isBlank()) {",
                "            Long executionId = stepExecution.getJobExecutionId();",
                "            runId = executionId == null ? UUID.randomUUID().toString() : executionId.toString();",
                "        }",
                "        return runId;",
                "    }",
            ]
            if has_file_control_records
            else []
        ),
        *(
            [
                "",
                "    private String resolveRunId(StepExecution stepExecution) {",
                "        String runId = stepExecution.getJobParameters().getString(\"runId\");",
                "        if (runId == null || runId.isBlank()) {",
                "            Long executionId = stepExecution.getJobExecutionId();",
                "            runId = executionId == null ? UUID.randomUUID().toString() : executionId.toString();",
                "        }",
                "        return runId;",
                "    }",
            ]
            if staging_has_run_identity
            else []
        ),
        *(
            [
                "",
                "    private LocalDate resolveBusinessDate(StepExecution stepExecution) {",
                "        String businessDate = stepExecution.getJobParameters().getString(\"businessDate\");",
                "        if (businessDate != null && !businessDate.isBlank()) {",
                "            return LocalDate.parse(businessDate);",
                "        }",
                "        if (configuredBusinessDate != null && !configuredBusinessDate.isBlank()) {",
                "            return LocalDate.parse(configuredBusinessDate);",
                "        }",
                "        return LocalDate.now();",
                "    }",
            ]
            if staging_has_business_date
            else []
        ),
        "}",
    ]

    imports = [
        f"{root_package}.domain.{entity.name}",
        f"{root_package}.repository.{entity.name}Repository",
        "java.util.Map",
        "org.slf4j.Logger",
        "org.slf4j.LoggerFactory",
        "org.springframework.batch.core.BatchStatus",
        "org.springframework.batch.core.ExitStatus",
        "org.springframework.batch.core.Job",
        "org.springframework.batch.core.Step",
        "org.springframework.batch.core.StepExecution",
        "org.springframework.batch.core.StepExecutionListener",
        "org.springframework.batch.core.job.builder.JobBuilder",
        "org.springframework.batch.core.repository.JobRepository",
        "org.springframework.batch.core.scope.context.StepSynchronizationManager",
        "org.springframework.batch.core.step.builder.StepBuilder",
        "org.springframework.batch.item.ItemWriter",
        "org.springframework.batch.item.data.RepositoryItemReader",
        "org.springframework.batch.repeat.RepeatStatus",
        "org.springframework.beans.factory.annotation.Value",
        "org.springframework.context.annotation.Bean",
        "org.springframework.context.annotation.Configuration",
        "org.springframework.data.domain.Sort",
        "org.springframework.transaction.PlatformTransactionManager",
    ]
    if has_staging_writer:
        imports[1:1] = [f"{root_package}.adapter.outbound.{entity.name}StagingWriter"]
    if has_file_writer:
        imports[1:1] = [f"{root_package}.adapter.outbound.{file_writer_class_name}"]
        imports.extend(
            [
                "java.io.IOException",
                "java.nio.file.AtomicMoveNotSupportedException",
                "java.nio.file.Files",
                "java.nio.file.Path",
                "java.nio.file.StandardCopyOption",
                "java.time.LocalDate",
                "java.time.format.DateTimeFormatter",
            ]
        )
    if has_file_control_records:
        imports.extend(["java.math.BigDecimal", "java.util.UUID"])
    if staging_has_business_date:
        imports.append("java.time.LocalDate")
    if staging_has_run_identity:
        imports.append("java.util.UUID")
    imports = list(dict.fromkeys(imports))

    return _batch_java_file(
        package_name=f"{root_package}.batch",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _m5a_history_type(target_profile: TargetProfile, entity_name: str, name: str) -> str:
    if entity_name != name:
        return name
    package = "org.springframework.batch.core"
    if target_profile.experimental_boot41:
        package += ".job" if name == "JobExecution" else ".job.parameters"
    return f"{package}.{name}"


def _m5a_history_validation_lines(target_profile: TargetProfile, entity_name: str) -> list[str]:
    preview = target_profile.experimental_boot41
    execution_type = _m5a_history_type(target_profile, entity_name, "JobExecution")
    parameters_type = _m5a_history_type(target_profile, entity_name, "JobParameters")
    set_type = "java.util.Set" if entity_name == "Set" else "Set"
    hash_set_type = "java.util.HashSet" if entity_name == "HashSet" else "HashSet"
    type_method = "type()" if preview else "getType()"
    value_method = "value()" if preview else "getValue()"
    identifying_method = "identifying()" if preview else "isIdentifying()"
    return [
        f"    private static LocalDate authoritativeBusinessDate({execution_type} execution, List<{execution_type}> history) {{",
        "        Long currentId = execution.getId();",
        "        Long instanceId = execution.getJobInstance() == null ? null : execution.getJobInstance().getId();",
        "        if (currentId == null || currentId <= 0 || instanceId == null || instanceId <= 0",
        "                || history == null || history.isEmpty()) {",
        '            throw integrityFailure("missing persisted execution history");',
        "        }",
        "        var instance = execution.getJobInstance();",
        f"        {set_type}<Long> ids = new {hash_set_type}<>();",
        f"        {execution_type} origin = null;",
        f"        for ({execution_type} prior : history) {{",
        "            Long priorId = prior == null ? null : prior.getId();",
        "            if (priorId == null || priorId <= 0",
        "                    || priorId > currentId || !ids.add(priorId)",
        "                    || prior.getJobInstance() == null",
        "                    || !instanceId.equals(prior.getJobInstance().getId())",
        "                    || !instance.getJobName().equals(prior.getJobInstance().getJobName())) {",
        '                throw integrityFailure("unorderable or contradictory execution history");',
        "            }",
        "            if (origin == null || prior.getId() < origin.getId()) {",
        "                origin = prior;",
        "            }",
        "        }",
        "        if (!ids.contains(execution.getId())) {",
        '            throw integrityFailure("current durable execution missing from history");',
        "        }",
        "        String runId = requiredRunId(execution.getJobParameters());",
        "        String originalRunId = requiredRunId(origin.getJobParameters());",
        "        LocalDate originalDate = requiredBusinessDate(origin.getJobParameters());",
        "        if (!originalRunId.equals(runId)) {",
        '            throw integrityFailure("authoritative runId contradicts current instance");',
        "        }",
        f"        for ({execution_type} prior : history) {{",
        "            if (!runId.equals(requiredRunId(prior.getJobParameters()))) {",
        '                throw integrityFailure("history runId contradicts current instance");',
        "            }",
        "            requiredBusinessDate(prior.getJobParameters());",
        "            corroborateContext(prior, runId, originalDate);",
        "            // Batch 6 parameter equality compares names, not persisted values.",
        "            if (currentId.equals(prior.getId())",
        "                    && !requiredBusinessDate(prior.getJobParameters()).equals(requiredBusinessDate(execution.getJobParameters()))) {",
        '                throw integrityFailure("current parameters contradict durable history");',
        "            }",
        "        }",
        "        corroborateContext(execution, runId, originalDate);",
        "        if (!originalDate.equals(requiredBusinessDate(execution.getJobParameters()))) {",
        '            throw new IllegalStateException("businessDate mismatch with original persisted execution; use original date and inspect Batch history");',
        "        }",
        "        return originalDate;",
        "    }",
        "",
        f"    private static String requiredRunId({parameters_type} parameters) {{",
        '        var parameter = parameters == null ? null : parameters.getParameter("runId");',
        f"        if (parameter == null || parameter.{type_method} != String.class",
        f"                || !parameter.{identifying_method} || parameters.getIdentifyingParameters().size() != 1",
        f"                || !(parameter.{value_method} instanceof String value)",
        "                || value.isBlank() || !value.equals(value.strip()) || value.length() > 2500) {",
        '            throw integrityFailure("missing or invalid typed identifying runId");',
        "        }",
        "        return value;",
        "    }",
        "",
        f"    private static LocalDate requiredBusinessDate({parameters_type} parameters) {{",
        '        var parameter = parameters == null ? null : parameters.getParameter("businessDate");',
        f"        if (parameter == null || parameter.{type_method} != LocalDate.class",
        f"                || parameter.{identifying_method} || !(parameter.{value_method} instanceof LocalDate value)) {{",
        '            throw integrityFailure("missing or invalid typed non-identifying businessDate");',
        "        }",
        "        return value;",
        "    }",
        "",
        f"    private static void corroborateContext({execution_type} execution, String runId, LocalDate date) {{",
        "        var context = execution.getExecutionContext();",
        "        if (context == null) {",
        '            throw integrityFailure("execution context unavailable");',
        "        }",
        '        for (String key : List.of("runId", "frozenBusinessDate", "businessDate")) {',
        "            if (context.containsKey(key)) {",
        '                String expected = key.equals("runId") ? runId : date.toString();',
        "                if (!(context.get(key) instanceof String value) || !expected.equals(value)) {",
        '                    throw integrityFailure("malformed or conflicting frozen context: " + key);',
        "                }",
        "            }",
        "        }",
        "    }",
        "",
        "    private static IllegalStateException integrityFailure(String reason) {",
        '        return new IllegalStateException("M5a integrity: " + reason + "; inspect retained Batch metadata; no automatic repair");',
        "    }",
        "",
    ]


def _render_run_semantics_batch_job(
    *,
    entity: CanonicalEntity,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
    staging_has_business_date: bool,
) -> str:
    """Emit the M5a-S2 identity step for an opted-in staging-only EOD job."""

    entity_var = entity.name[:1].lower() + entity.name[1:]
    id_field = entity_id_field(entity)
    preview = target_profile.experimental_boot41
    execution_type = _m5a_history_type(target_profile, entity.name, "JobExecution")
    runtime_exception_type = "java.lang.RuntimeException" if entity.name == "RuntimeException" else "RuntimeException"
    business_date_context = (
        [
            '                context.putString("businessDate", frozenBusinessDate);',
            '                log.info("EOD job {} accepted runId={} businessDate={}",',
            "                        execution.getJobInstance().getJobName(),",
            "                        runId,",
            "                        frozenBusinessDate);",
        ]
        if staging_has_business_date
        else [
            '                log.info("EOD job {} accepted runId={}",',
            "                        execution.getJobInstance().getJobName(),",
            "                        runId);",
        ]
    )
    staging_write_args = ["record", 'context.getString("runId")']
    if staging_has_business_date:
        staging_write_args.append('LocalDate.parse(context.getString("businessDate"))')

    body = [
        "@Configuration",
        f"public class {entity.name}EodBatchJob {{",
        "",
        f"    private static final Logger log = LoggerFactory.getLogger({entity.name}EodBatchJob.class);",
        "",
        "    @Value(\"${app.eod.chunk-size:500}\")",
        "    private int chunkSize;",
        "",
        "    @Bean",
        f"    public Job {entity_var}EodJob(",
        "            JobRepository jobRepository,",
        f"            Step {entity_var}RunIdentityStep,",
        f"            Step {entity_var}EodStep",
        "    ) {",
        f"        return new JobBuilder(\"{entity_var}EodJob\", jobRepository)",
        f"            .start({entity_var}RunIdentityStep)",
        f"            .next({entity_var}EodStep)",
        "            .build();",
        "    }",
        "",
        "    @Bean",
        f"    public Step {entity_var}RunIdentityStep(",
        "            JobRepository jobRepository,",
        *([] if preview else ["            org.springframework.batch.core.explore.JobExplorer jobExplorer,"]),
        "            PlatformTransactionManager transactionManager",
        "    ) {",
        f"        return new StepBuilder(\"{entity_var}RunIdentityStep\", jobRepository)",
        "            .tasklet((contribution, chunkContext) -> {",
        "                var execution = contribution.getStepExecution().getJobExecution();",
        f"                List<{execution_type}> history;",
        "                try {",
        f"                    history = {'jobRepository' if preview else 'jobExplorer'}.getJobExecutions(execution.getJobInstance());",
        f"                }} catch ({runtime_exception_type} exception) {{",
        '                    throw new IllegalStateException("M5a integrity: complete execution history unavailable; inspect retained Batch metadata", exception);',
        "                }",
        "                String frozenBusinessDate = authoritativeBusinessDate(execution, history).toString();",
        '                String runId = execution.getJobParameters().getString("runId");',
        "                var context = execution.getExecutionContext();",
        '                context.putString("frozenBusinessDate", frozenBusinessDate);',
        '                context.putString("runId", runId);',
        *business_date_context,
        "                jobRepository.updateExecutionContext(execution);",
        "                return RepeatStatus.FINISHED;",
        "            }, transactionManager)",
        "            .allowStartIfComplete(true)",
        "            .build();",
        "    }",
        "",
        "    @Bean",
        f"    public Step {entity_var}EodStep(",
        "            JobRepository jobRepository,",
        "            PlatformTransactionManager transactionManager,",
        f"            RepositoryItemReader<{entity.name}> {entity_var}EodReader,",
        f"            ItemWriter<{entity.name}> {entity_var}EodWriter",
        "    ) {",
        f"        return new StepBuilder(\"{entity_var}EodStep\", jobRepository)",
        f"            .<{entity.name}, {entity.name}>chunk(chunkSize, transactionManager)",
        f"            .reader({entity_var}EodReader)",
        f"            .writer({entity_var}EodWriter)",
        "            .build();",
        "    }",
        "",
        "    @Bean",
        f"    public RepositoryItemReader<{entity.name}> {entity_var}EodReader(",
        f"            {entity.name}Repository repository",
        "    ) {",
        *_batch_reader_lines(entity, entity_var, id_field, "repository", target_profile),
        "        return reader;",
        "    }",
        "",
        "    @Bean",
        f"    public ItemWriter<{entity.name}> {entity_var}EodWriter(",
        f"            {entity.name}StagingWriter stagingWriter",
        "    ) {",
        "        return chunk -> {",
        "            var context = StepSynchronizationManager.getContext().getStepExecution()",
        "                .getJobExecution().getExecutionContext();",
        f"            for ({entity.name} record : chunk) {{",
        f"                stagingWriter.write({', '.join(staging_write_args)});",
        "            }",
        "        };",
        "    }",
        "",
        *_m5a_history_validation_lines(target_profile, entity.name),
        "}",
    ]
    return _batch_java_file(
        package_name=f"{root_package}.batch",
        imports=[
            f"{root_package}.adapter.outbound.{entity.name}StagingWriter",
            f"{root_package}.domain.{entity.name}",
            f"{root_package}.repository.{entity.name}Repository",
            "java.time.LocalDate",
            "java.util.List",
            *([] if entity.name == "Set" else ["java.util.Set"]),
            *([] if entity.name == "HashSet" else ["java.util.HashSet"]),
            "java.util.Map",
            "org.slf4j.Logger",
            "org.slf4j.LoggerFactory",
            "org.springframework.batch.core.Job",
            *([] if entity.name == "JobExecution" else ["org.springframework.batch.core.JobExecution"]),
            *([] if entity.name == "JobParameters" else ["org.springframework.batch.core.JobParameters"]),
            "org.springframework.batch.core.Step",
            "org.springframework.batch.core.job.builder.JobBuilder",
            "org.springframework.batch.core.repository.JobRepository",
            "org.springframework.batch.core.scope.context.StepSynchronizationManager",
            "org.springframework.batch.core.step.builder.StepBuilder",
            "org.springframework.batch.item.ItemWriter",
            "org.springframework.batch.item.data.RepositoryItemReader",
            "org.springframework.batch.repeat.RepeatStatus",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.context.annotation.Bean",
            "org.springframework.context.annotation.Configuration",
            "org.springframework.data.domain.Sort",
            "org.springframework.transaction.PlatformTransactionManager",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_multi_file_batch_job(
    *,
    entity: CanonicalEntity,
    root_package: str,
    bounded_context: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
    file_writer_contexts: list[_DownstreamFileWriterContext],
    has_staging_writer: bool = True,
    staging_has_run_identity: bool = False,
    staging_has_business_date: bool = False,
) -> str:
    entity_var = entity.name[:1].lower() + entity.name[1:]
    eod_dir_default = f"./{bounded_context}-eod"
    id_field = entity_id_field(entity)
    control_contexts = [ctx for ctx in file_writer_contexts if ctx.has_control_records]
    staging_write_args = ["record"]
    if staging_has_run_identity:
        staging_write_args.append('context.getString("runId")')
    if staging_has_business_date:
        staging_write_args.append('LocalDate.parse(context.getString("businessDate"))')

    def _var_prefix(ctx: _DownstreamFileWriterContext) -> str:
        return ctx.local_var_prefix

    before_step_staging_lines: list[str] = []
    if has_staging_writer:
        if staging_has_run_identity:
            before_step_staging_lines.append("                String runId = resolveRunId(stepExecution);")
        if staging_has_business_date:
            before_step_staging_lines.extend(
                [
                    "                LocalDate businessDate = resolveBusinessDate(stepExecution);",
                    "                context.putString(\"businessDate\", businessDate.toString());",
                ]
            )
        if staging_has_run_identity:
            before_step_staging_lines.extend(
                [
                    "                context.putString(\"runId\", runId);",
                    "                stagingWriter.clear(runId);",
                ]
            )
        else:
            before_step_staging_lines.append("                stagingWriter.clear();")

    file_prepare_lines = [
        "                try {",
        *(
            ["                    String outputRunId = resolveOutputRunId(stepExecution);"]
            if control_contexts
            else []
        ),
    ]
    for ctx in file_writer_contexts:
        prefix = _var_prefix(ctx)
        output_var = f"{prefix}OutputFile"
        temp_var = f"{prefix}TempFile"
        file_prepare_lines.extend(
            [
                f"                    Path {output_var} = {ctx.output_file_method_name}();",
                f"                    Files.createDirectories({output_var}.getParent());",
                f"                    Path {temp_var} = {ctx.temp_file_method_name}({output_var}, stepExecution);",
                f"                    Files.deleteIfExists({temp_var});",
                f"                    Files.createFile({temp_var});",
                f"                    context.putString(\"{ctx.output_context_key}\", {output_var}.toString());",
                f"                    context.putString(\"{ctx.temp_context_key}\", {temp_var}.toString());",
            ]
        )
        if ctx.has_control_records:
            file_prepare_lines.append(
                f"                    {ctx.writer_var_name}.startFile({temp_var}, outputRunId);"
            )
    file_prepare_lines.extend(
        [
            "                } catch (IOException ex) {",
            "                    throw new IllegalStateException(\"Failed to prepare EOD output files\", ex);",
            "                }",
        ]
    )

    writer_temp_lines = []
    for ctx in file_writer_contexts:
        writer_temp_lines.extend(
            [
                f"            Path {_var_prefix(ctx)}TempOutputFile = Path.of(",
                f"                    context.getString(\"{ctx.temp_context_key}\"));",
            ]
        )
    writer_total_load_lines = []
    writer_total_store_lines = []
    for ctx in control_contexts:
        total_var = f"{_var_prefix(ctx)}FileTotal"
        writer_total_load_lines.extend(
            [
                f"            Object {total_var}Value = context.get(\"{ctx.file_total_context_key}\");",
                f"            BigDecimal {total_var} = {total_var}Value instanceof BigDecimal decimal ? decimal : BigDecimal.ZERO;",
            ]
        )
        writer_total_store_lines.append(f"            context.put(\"{ctx.file_total_context_key}\", {total_var});")

    writer_call_lines = []
    for ctx in file_writer_contexts:
        prefix = _var_prefix(ctx)
        writer_call_lines.append(
            f"                {ctx.writer_var_name}.write(record, {prefix}TempOutputFile);"
        )
        if ctx.has_control_records:
            writer_call_lines.append(
                f"                {prefix}FileTotal = {prefix}FileTotal.add({ctx.writer_var_name}.dataTotal(record));"
            )

    finalize_param_lines = [
        "        JobRepository jobRepository,",
        "        PlatformTransactionManager transactionManager",
    ]
    for ctx in control_contexts:
        finalize_param_lines[-1] += ","
        finalize_param_lines.append(
            f"        {ctx.writer_class_name} {ctx.writer_var_name}"
        )

    finalize_record_lines = []
    finalize_skip_lines = []
    for ctx in file_writer_contexts:
        prefix = _var_prefix(ctx)
        output_var = f"{prefix}OutputFile"
        temp_var = f"{prefix}TempFile"
        finalize_record_lines.extend(
            [
                f"                    Path {output_var} = Path.of(context.getString(\"{ctx.output_context_key}\"));",
                f"                    Path {temp_var} = Path.of(context.getString(\"{ctx.temp_context_key}\"));",
            ]
        )
        if ctx.has_control_records:
            total_var = f"{prefix}FileTotal"
            finalize_record_lines.extend(
                [
                    f"                    Object {total_var}Value = context.get(\"{ctx.file_total_context_key}\");",
                    f"                    BigDecimal {total_var} = {total_var}Value instanceof BigDecimal decimal ? decimal : BigDecimal.ZERO;",
                    f"                    {ctx.writer_var_name}.finishFile({temp_var}, recordCount, {total_var});",
                ]
            )
        finalize_record_lines.append(f"                    moveReplacing({temp_var}, {output_var});")
        finalize_skip_lines.extend(
            [
                f"                    Path {temp_var} = Path.of(context.getString(\"{ctx.temp_context_key}\"));",
                f"                    deleteTempQuietly({temp_var});",
            ]
        )

    failure_cleanup_lines = []
    for ctx in file_writer_contexts:
        temp_var = f"{_var_prefix(ctx)}TempFile"
        failure_cleanup_lines.extend(
            [
                f"                    Path {temp_var} = Path.of(context.getString(\"{ctx.temp_context_key}\"));",
                f"                    deleteTempQuietly({temp_var});",
            ]
        )

    output_methods = []
    for ctx in file_writer_contexts:
        output_methods.extend(
            [
                "",
                f"    private Path {ctx.output_file_method_name}() {{",
                "        String dateStamp = LocalDate.now()",
                "                .format(DateTimeFormatter.ofPattern(\"yyyyMMdd\"));",
                "        Path outputDir = Path.of(eodOutputDir);",
                f"        return outputDir.resolve(\"{ctx.output_file_name_prefix}\" + dateStamp + \".{ctx.file_extension}\");",
                "    }",
                "",
                f"    private Path {ctx.temp_file_method_name}(Path outputFile, StepExecution stepExecution) {{",
                "        return outputFile.resolveSibling(",
                "                outputFile.getFileName() + \".tmp-\" + stepExecution.getJobExecutionId());",
                "    }",
            ]
        )

    writer_params = []
    if has_staging_writer:
        writer_params.append(f"            {entity.name}StagingWriter stagingWriter,")
    for index, ctx in enumerate(file_writer_contexts):
        suffix = "," if index < len(file_writer_contexts) - 1 else ""
        writer_params.append(f"            {ctx.writer_class_name} {ctx.writer_var_name}{suffix}")

    listener_params = []
    if has_staging_writer:
        listener_params.append(f"            {entity.name}StagingWriter stagingWriter")
    for ctx in control_contexts:
        if listener_params:
            listener_params[-1] += ","
        listener_params.append(f"            {ctx.writer_class_name} {ctx.writer_var_name}")

    body = [
        "@Configuration",
        f"public class {entity.name}EodBatchJob {{",
        "",
        f"    private static final Logger log = LoggerFactory.getLogger({entity.name}EodBatchJob.class);",
        "",
        f"    @Value(\"${{app.eod.output-dir:{eod_dir_default}}}\")",
        "    private String eodOutputDir;",
        "",
        "    @Value(\"${app.eod.business-date:}\")",
        "    private String configuredBusinessDate;",
        "",
        "    @Value(\"${app.eod.chunk-size:500}\")",
        "    private int chunkSize;",
        "",
        "    @Bean",
        f"    public Job {entity_var}EodJob(",
        "            JobRepository jobRepository,",
        f"            Step {entity_var}EodStep,",
        f"            Step {entity_var}EodFinalizeStep",
        "    ) {",
        f"        return new JobBuilder(\"{entity_var}EodJob\", jobRepository)",
        f"            .start({entity_var}EodStep)",
        f"            .next({entity_var}EodFinalizeStep)",
        "            .build();",
        "    }",
        "",
        "    @Bean",
        f"    public Step {entity_var}EodStep(",
        "        JobRepository jobRepository,",
        "        PlatformTransactionManager transactionManager,",
        f"        RepositoryItemReader<{entity.name}> {entity_var}EodReader,",
        f"        ItemWriter<{entity.name}> {entity_var}EodWriter,",
        f"        StepExecutionListener {entity_var}EodStepListener",
        "    ) {",
        f"        return new StepBuilder(\"{entity_var}EodStep\", jobRepository)",
        f"            .<{entity.name}, {entity.name}>chunk(chunkSize, transactionManager)",
        f"            .reader({entity_var}EodReader)",
        f"            .writer({entity_var}EodWriter)",
        f"            .listener({entity_var}EodStepListener)",
        "            .build();",
        "    }",
        "",
        "    @Bean",
        f"    public Step {entity_var}EodFinalizeStep(",
        *finalize_param_lines,
        "    ) {",
        f"        return new StepBuilder(\"{entity_var}EodFinalizeStep\", jobRepository)",
        "            .tasklet((contribution, chunkContext) -> {",
        "                StepExecution stepExecution = currentStepExecution();",
        "                var context = stepExecution.getJobExecution().getExecutionContext();",
        "                long recordCount = context.getLong(\"recordCount\", 0L);",
        "                if (recordCount > 0) {",
        *finalize_record_lines,
        "                    context.putString(\"outputStatus\", \"CREATED\");",
        "                    log.info(\"EOD job {} finalized {} records across downstream file contracts\",",
        "                            stepExecution.getJobExecution().getJobInstance().getJobName(),",
        "                            recordCount);",
        "                } else {",
        *finalize_skip_lines,
        "                    context.putString(\"outputStatus\", \"SKIPPED\");",
        "                    context.putString(\"skipReason\", \"NO_RECORDS\");",
        "                    log.info(\"EOD job {} skipped downstream file output because no records were read\",",
        "                            stepExecution.getJobExecution().getJobInstance().getJobName());",
        "                }",
        "                return RepeatStatus.FINISHED;",
        "            }, transactionManager)",
        "            .build();",
        "    }",
        "",
        "    @Bean",
        f"    public RepositoryItemReader<{entity.name}> {entity_var}EodReader(",
        f"            {entity.name}Repository {entity_var}Repository) {{",
        *_batch_reader_lines(entity, entity_var, id_field, f"{entity_var}Repository", target_profile),
        "        return reader;",
        "    }",
        "",
        "    @Bean",
        f"    public ItemWriter<{entity.name}> {entity_var}EodWriter(",
        *writer_params,
        "    ) {",
        "        return items -> {",
        "            StepExecution stepExecution = currentStepExecution();",
        "            var context = stepExecution.getJobExecution().getExecutionContext();",
        "            long recordCount = context.getLong(\"recordCount\", 0L);",
        "            int chunkCount = 0;",
        *writer_total_load_lines,
        *writer_temp_lines,
        f"            for ({entity.name} record : items) {{",
        *(
            [f"                stagingWriter.write({', '.join(staging_write_args)});"]
            if has_staging_writer
            else []
        ),
        *writer_call_lines,
        "                chunkCount++;",
        "            }",
        "            context.putLong(\"recordCount\", recordCount + chunkCount);",
        *writer_total_store_lines,
        "        };",
        "    }",
        "",
        "    @Bean",
        f"    public StepExecutionListener {entity_var}EodStepListener(",
        *listener_params,
        "    ) {",
        "        return new StepExecutionListener() {",
        "            @Override",
        "            public void beforeStep(StepExecution stepExecution) {",
        "                var context = stepExecution.getJobExecution().getExecutionContext();",
        *before_step_staging_lines,
        "                context.putLong(\"recordCount\", 0L);",
        *[f"                context.put(\"{ctx.file_total_context_key}\", BigDecimal.ZERO);" for ctx in control_contexts],
        "                context.putString(\"outputStatus\", \"CREATED\");",
        *file_prepare_lines,
        "            }",
        "",
        "            @Override",
        "            public ExitStatus afterStep(StepExecution stepExecution) {",
        "                var context = stepExecution.getJobExecution().getExecutionContext();",
        "                long recordCount = context.getLong(\"recordCount\", 0L);",
        "                if (stepExecution.getStatus() != BatchStatus.COMPLETED) {",
        *failure_cleanup_lines,
        "                    context.putString(\"outputStatus\", \"FAILED\");",
        "                    log.warn(\"EOD job {} failed after {} records; downstream temp outputs removed\",",
        "                            stepExecution.getJobExecution().getJobInstance().getJobName(),",
        "                            recordCount);",
        "                }",
        "                return stepExecution.getExitStatus();",
        "            }",
        "        };",
        "    }",
        "",
        "    private StepExecution currentStepExecution() {",
        "        return StepSynchronizationManager.getContext().getStepExecution();",
        "    }",
        *output_methods,
        "",
        "    private void moveReplacing(Path tempFile, Path outputFile) throws IOException {",
        "        try {",
        "            Files.move(tempFile, outputFile, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);",
        "        } catch (AtomicMoveNotSupportedException ex) {",
        "            Files.move(tempFile, outputFile, StandardCopyOption.REPLACE_EXISTING);",
        "        }",
        "    }",
        "",
        "    private void deleteTempQuietly(Path tempFile) {",
        "        try {",
        "            Files.deleteIfExists(tempFile);",
        "        } catch (IOException ex) {",
        "            log.warn(\"Failed to delete temporary EOD output file {}\", tempFile, ex);",
        "        }",
        "    }",
        *(
            [
                "",
                "    private String resolveOutputRunId(StepExecution stepExecution) {",
                "        String runId = stepExecution.getJobParameters().getString(\"runId\");",
                "        if (runId == null || runId.isBlank()) {",
                "            Long executionId = stepExecution.getJobExecutionId();",
                "            runId = executionId == null ? UUID.randomUUID().toString() : executionId.toString();",
                "        }",
                "        return runId;",
                "    }",
            ]
            if control_contexts
            else []
        ),
        *(
            [
                "",
                "    private String resolveRunId(StepExecution stepExecution) {",
                "        String runId = stepExecution.getJobParameters().getString(\"runId\");",
                "        if (runId == null || runId.isBlank()) {",
                "            Long executionId = stepExecution.getJobExecutionId();",
                "            runId = executionId == null ? UUID.randomUUID().toString() : executionId.toString();",
                "        }",
                "        return runId;",
                "    }",
            ]
            if staging_has_run_identity
            else []
        ),
        *(
            [
                "",
                "    private LocalDate resolveBusinessDate(StepExecution stepExecution) {",
                "        String businessDate = stepExecution.getJobParameters().getString(\"businessDate\");",
                "        if (businessDate != null && !businessDate.isBlank()) {",
                "            return LocalDate.parse(businessDate);",
                "        }",
                "        if (configuredBusinessDate != null && !configuredBusinessDate.isBlank()) {",
                "            return LocalDate.parse(configuredBusinessDate);",
                "        }",
                "        return LocalDate.now();",
                "    }",
            ]
            if staging_has_business_date
            else []
        ),
        "}",
    ]

    imports = [
        f"{root_package}.domain.{entity.name}",
        *[f"{root_package}.adapter.outbound.{ctx.writer_class_name}" for ctx in file_writer_contexts],
        f"{root_package}.repository.{entity.name}Repository",
        "java.io.IOException",
        *(["java.math.BigDecimal"] if control_contexts else []),
        "java.nio.file.AtomicMoveNotSupportedException",
        "java.nio.file.Files",
        "java.nio.file.Path",
        "java.nio.file.StandardCopyOption",
        "java.time.LocalDate",
        "java.time.format.DateTimeFormatter",
        "java.util.Map",
        *(["java.util.UUID"] if control_contexts or staging_has_run_identity else []),
        "org.slf4j.Logger",
        "org.slf4j.LoggerFactory",
        "org.springframework.batch.core.BatchStatus",
        "org.springframework.batch.core.ExitStatus",
        "org.springframework.batch.core.Job",
        "org.springframework.batch.core.Step",
        "org.springframework.batch.core.StepExecution",
        "org.springframework.batch.core.StepExecutionListener",
        "org.springframework.batch.core.job.builder.JobBuilder",
        "org.springframework.batch.core.repository.JobRepository",
        "org.springframework.batch.core.scope.context.StepSynchronizationManager",
        "org.springframework.batch.core.step.builder.StepBuilder",
        "org.springframework.batch.item.ItemWriter",
        "org.springframework.batch.item.data.RepositoryItemReader",
        "org.springframework.batch.repeat.RepeatStatus",
        "org.springframework.beans.factory.annotation.Value",
        "org.springframework.context.annotation.Bean",
        "org.springframework.context.annotation.Configuration",
        "org.springframework.data.domain.Sort",
        "org.springframework.transaction.PlatformTransactionManager",
    ]
    if has_staging_writer:
        imports[1:1] = [f"{root_package}.adapter.outbound.{entity.name}StagingWriter"]
    imports = list(dict.fromkeys(imports))
    return _batch_java_file(
        package_name=f"{root_package}.batch",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_batch_trigger_controller(
    *,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
    run_semantics_by_job: dict[str, RunSemanticsMetadata] | None = None,
) -> str:
    if run_semantics_by_job:
        return _render_run_semantics_batch_trigger_controller(
            root_package=root_package,
            target_profile=target_profile,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
            run_semantics_by_job=run_semantics_by_job,
        )
    launcher_type = "JobOperator" if target_profile.experimental_boot41 else "JobLauncher"
    launch_method = "start" if target_profile.experimental_boot41 else "run"
    instance_id_method = "getJobInstanceId" if target_profile.experimental_boot41 else "getJobId"
    body = [
        "@RestController",
        "@RequestMapping(\"/batch\")",
        "public class BatchTriggerController {",
        "",
        f"    private final {launcher_type} jobLauncher;",
        "    private final java.util.Map<String, Job> jobsByName;",
        "",
        f"    public BatchTriggerController({launcher_type} jobLauncher, java.util.Map<String, Job> jobsByName) {{",
        "        this.jobLauncher = jobLauncher;",
        "        this.jobsByName = jobsByName;",
        "    }",
        "",
        "    /**",
        "     * POST /batch/run/{jobName}",
        "     * Triggers a named EOD batch job. Unique run.at param ensures re-runs are distinct instances.",
        "     */",
        "    @PostMapping(\"/run/{jobName}\")",
        "    public ResponseEntity<java.util.Map<String, Object>> runJob(",
        "            @PathVariable String jobName) throws Exception {",
        "        Job job = jobsByName.get(jobName);",
        "        if (job == null) {",
        "            return ResponseEntity.status(404).body(",
        "                java.util.Map.of(\"error\", \"Job not found: \" + jobName,",
        "                                 \"available\", jobsByName.keySet()));",
        "        }",
        "        JobParameters params = new JobParametersBuilder()",
        "            .addLong(\"run.at\", System.currentTimeMillis())",
        "            .toJobParameters();",
        f"        JobExecution execution = jobLauncher.{launch_method}(job, params);",
        "        return ResponseEntity.ok(java.util.Map.of(",
        "            \"jobName\", execution.getJobInstance().getJobName(),",
        f"            \"jobId\", execution.{instance_id_method}(),",
        "            \"status\", execution.getStatus().toString(),",
        "            \"startTime\", execution.getStartTime() != null ? execution.getStartTime().toString() : \"pending\",",
        "            \"exitCode\", execution.getExitStatus().getExitCode()",
        "        ));",
        "    }",
        "}",
    ]
    imports = [
        "org.springframework.batch.core.Job",
        "org.springframework.batch.core.JobExecution",
        "org.springframework.batch.core.JobParameters",
        "org.springframework.batch.core.JobParametersBuilder",
        f"org.springframework.batch.core.launch.{launcher_type}",
        "org.springframework.http.ResponseEntity",
        "org.springframework.web.bind.annotation.PathVariable",
        "org.springframework.web.bind.annotation.PostMapping",
        "org.springframework.web.bind.annotation.RequestMapping",
        "org.springframework.web.bind.annotation.RestController",
    ]
    return _batch_java_file(
        package_name=f"{root_package}.adapter.inbound",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_run_semantics_batch_trigger_controller(
    *,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
    run_semantics_by_job: dict[str, RunSemanticsMetadata],
) -> str:
    """Emit the closed M5a-S2 request contract without changing legacy jobs."""

    preview = target_profile.experimental_boot41
    launcher_type = "JobOperator" if preview else "JobLauncher"
    explorer_type = "JobRepository" if preview else "JobExplorer"
    explorer_import = (
        "org.springframework.batch.core.repository.JobRepository"
        if preview else "org.springframework.batch.core.explore.JobExplorer"
    )
    launch_method = "start" if preview else "run"
    instance_id_method = "getJobInstanceId" if preview else "getJobId"
    text_check = "isString" if preview else "isTextual"
    text_value = "stringValue" if preview else "textValue"
    json_node_import = (
        "tools.jackson.databind.JsonNode" if preview else "com.fasterxml.jackson.databind.JsonNode"
    )
    run_id_limit_entries = []
    for job_name, run_semantics in sorted(run_semantics_by_job.items()):
        physical_max = run_semantics.physical_run_id_max_length
        effective_max = min(physical_max, 2500) if physical_max is not None else 2500
        run_id_limit_entries.append(f'        Map.entry("{job_name}", {effective_max})')

    body = [
        "@RestController",
        "@RequestMapping(\"/batch\")",
        "public class BatchTriggerController {",
        "",
        "    private static final Map<String, Integer> RUN_ID_LIMITS = Map.ofEntries(",
        ",\n".join(run_id_limit_entries),
        "    );",
        "",
        f"    private final {launcher_type} jobLauncher;",
        f"    private final {explorer_type} jobExplorer;",
        "    private final Map<String, Job> jobsByName;",
        "",
        "    public BatchTriggerController(",
        f"            {launcher_type} jobLauncher,",
        f"            {explorer_type} jobExplorer,",
        "            Map<String, Job> jobsByName",
        "    ) {",
        "        this.jobLauncher = jobLauncher;",
        "        this.jobExplorer = jobExplorer;",
        "        this.jobsByName = jobsByName;",
        "    }",
        "",
        "    @PostMapping(\"/run/{jobName}\")",
        "    public ResponseEntity<Map<String, Object>> runJob(",
        "            @PathVariable String jobName,",
        "            @RequestBody(required = false) JsonNode request",
        "    ) throws Exception {",
        "        Job job = jobsByName.get(jobName);",
        "        if (job == null) {",
        "            return ResponseEntity.status(404).body(Map.of(",
        "                \"error\", \"Job not found: \" + jobName,",
        "                \"available\", jobsByName.keySet()));",
        "        }",
        "        Integer runIdLimit = RUN_ID_LIMITS.get(jobName);",
        "        if (runIdLimit == null) {",
        "            return runLegacyJob(job);",
        "        }",
        "        if (request == null || !request.isObject()",
        "                || !request.hasNonNull(\"runId\") || !request.hasNonNull(\"businessDate\")",
        f"                || request.size() != 2 || !request.get(\"runId\").{text_check}()",
        f"                || !request.get(\"businessDate\").{text_check}()) {{",
        "            return badRequest(\"Body must contain only textual runId and businessDate members\");",
        "        }",
        f"        String runId = request.get(\"runId\").{text_value}();",
        "        if (runId.isBlank() || !runId.equals(runId.strip())) {",
        "            return badRequest(\"runId must be non-blank and must not have leading or trailing whitespace\");",
        "        }",
        "        if (runId.length() > runIdLimit) {",
        "            return badRequest(\"runId exceeds the configured UTF-16 storage bound of \" + runIdLimit);",
        "        }",
        "        LocalDate businessDate;",
        "        try {",
        f"            businessDate = LocalDate.parse(request.get(\"businessDate\").{text_value}());",
        "        } catch (DateTimeParseException exception) {",
        "            return badRequest(\"businessDate must be an ISO-8601 calendar date\");",
        "        }",
        "        JobParameters params = new JobParametersBuilder()",
        "            .addString(\"runId\", runId, true)",
        "            .addLocalDate(\"businessDate\", businessDate, false)",
        "            .toJobParameters();",
        "        try {",
        f"            JobExecution execution = jobLauncher.{launch_method}(job, params);",
        "            return accepted(execution);",
        "        } catch (JobInstanceAlreadyCompleteException exception) {",
        "            return ResponseEntity.status(409).body(Map.of(",
        "                \"code\", \"batch_instance_completed\",",
        "                \"jobName\", jobName,",
        "                \"runId\", runId,",
        "                \"message\", \"The requested runId already completed. Use a new runId.\"));",
        "        } catch (JobExecutionAlreadyRunningException exception) {",
        "            return runningConflict(jobName, params, runId);",
        "        }",
        "    }",
        "",
        "    private ResponseEntity<Map<String, Object>> runLegacyJob(Job job) throws Exception {",
        "        JobParameters params = new JobParametersBuilder()",
        "            .addLong(\"run.at\", System.currentTimeMillis())",
        "            .toJobParameters();",
        f"        return ResponseEntity.ok(result(jobLauncher.{launch_method}(job, params)));",
        "    }",
        "",
        "    private ResponseEntity<Map<String, Object>> accepted(JobExecution execution) {",
        "        return ResponseEntity.ok(result(execution));",
        "    }",
        "",
        "    private Map<String, Object> result(JobExecution execution) {",
        "        return Map.of(",
        "            \"jobName\", execution.getJobInstance().getJobName(),",
        f"            \"jobId\", execution.{instance_id_method}(),",
        "            \"status\", execution.getStatus().toString(),",
        "            \"startTime\", execution.getStartTime() != null ? execution.getStartTime().toString() : \"pending\",",
        "            \"exitCode\", execution.getExitStatus().getExitCode()",
        "        );",
        "    }",
        "",
        "    private ResponseEntity<Map<String, Object>> runningConflict(",
        "            String jobName, JobParameters params, String runId",
        "    ) {",
        "        JobInstance instance = jobExplorer.getJobInstance(jobName, params);",
        "        if (instance == null) {",
        "            return ResponseEntity.status(409).body(Map.of(",
        "                \"code\", \"batch_execution_state_unavailable\",",
        "                \"jobName\", jobName,",
        "                \"runId\", runId,",
        "                \"batchStatus\", \"UNKNOWN\",",
        "                \"requeryRequired\", true,",
        "                \"message\", \"Batch state changed during launch; retry after inspecting the job state.\"));",
        "        }",
        "        JobExecution execution = jobExplorer.getLastJobExecution(instance);",
        "        if (execution == null) {",
        "            return ResponseEntity.status(409).body(Map.of(",
        "                \"code\", \"batch_execution_state_unavailable\",",
        "                \"jobName\", jobName,",
        "                \"runId\", runId,",
        "                \"batchStatus\", \"UNKNOWN\",",
        "                \"requeryRequired\", true,",
        "                \"message\", \"Batch execution lookup changed during launch; retry after inspecting the job state.\"));",
        "        }",
        "        if (execution.getStatus().isRunning()) {",
        "            return ResponseEntity.status(409).body(Map.of(",
        "                \"code\", \"batch_execution_running\",",
        "                \"jobName\", jobName,",
        "                \"runId\", runId,",
        "                \"jobExecutionId\", execution.getId(),",
        "                \"batchStatus\", execution.getStatus().toString(),",
        "                \"ownerVerificationRequired\", true,",
        "                \"message\", \"The requested runId is already running.\"));",
        "        }",
        "        return ResponseEntity.status(409).body(Map.of(",
        "            \"code\", \"batch_execution_state_changed\",",
        "            \"jobName\", jobName,",
        "            \"runId\", runId,",
        "            \"jobExecutionId\", execution.getId(),",
        "            \"batchStatus\", execution.getStatus().toString(),",
        "            \"requeryRequired\", true,",
        "            \"message\", \"Batch state changed during launch; inspect the execution before retrying.\"));",
        "    }",
        "",
        "    private ResponseEntity<Map<String, Object>> badRequest(String message) {",
        "        return ResponseEntity.badRequest().body(Map.of(",
        "            \"code\", \"invalid_batch_request\",",
        "            \"message\", message));",
        "    }",
        "",
        "}",
    ]
    return _batch_java_file(
        package_name=f"{root_package}.adapter.inbound",
        imports=[
            json_node_import,
            "java.time.LocalDate",
            "java.time.format.DateTimeParseException",
            "java.util.Map",
            "org.springframework.batch.core.Job",
            "org.springframework.batch.core.JobExecution",
            "org.springframework.batch.core.JobInstance",
            "org.springframework.batch.core.JobParameters",
            "org.springframework.batch.core.JobParametersBuilder",
            explorer_import,
            f"org.springframework.batch.core.launch.{launcher_type}",
            "org.springframework.batch.core.repository.JobExecutionAlreadyRunningException",
            "org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException",
            "org.springframework.http.ResponseEntity",
            "org.springframework.web.bind.annotation.PathVariable",
            "org.springframework.web.bind.annotation.PostMapping",
            "org.springframework.web.bind.annotation.RequestBody",
            "org.springframework.web.bind.annotation.RequestMapping",
            "org.springframework.web.bind.annotation.RestController",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


def _render_application_test(
    *,
    metadata: MetadataProject,
    root_package: str,
    target_profile: TargetProfile,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    class_name = f"{to_pascal_case(metadata.bounded_context)}ApplicationTest"
    body = [
        "@SpringBootTest",
        f"class {class_name} {{",
        "",
        "    @Test",
        "    void contextLoads() {",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=root_package,
        imports=[
            "org.junit.jupiter.api.Test",
            "org.springframework.boot.test.context.SpringBootTest",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _java_type(field: CanonicalField) -> str:
    return CANONICAL_TO_JAVA[field.type.value]


def _java_literal(field: CanonicalField) -> str:
    if field.default_value is None:
        return "null"
    raw_default = str(field.default_value)
    if field.type.value == "string":
        return _java_code_string_literal(raw_default)
    if field.type.value == "boolean":
        return _validated_java_boolean_literal(
            raw_default,
            context=f"field '{field.name}' default",
        )
    if field.type.value == "integer":
        return (
            _validated_java_integer_literal(
                raw_default,
                context=f"field '{field.name}' default",
            )
            + "L"
        )
    if field.type.value == "decimal":
        return (
            "new BigDecimal("
            + _java_code_string_literal(
                _validated_java_decimal_literal(
                    raw_default,
                    context=f"field '{field.name}' default",
                )
            )
            + ")"
        )
    if field.type.value == "date":
        _validate_java_date_literal(raw_default, context=f"field '{field.name}' default")
        return f"LocalDate.parse({_java_code_string_literal(raw_default)})"
    if field.type.value == "datetime":
        _validate_java_datetime_literal(raw_default, context=f"field '{field.name}' default")
        if re.search(r"(Z|[+-]\d{2}:\d{2})$", raw_default):
            return (
                f"java.time.OffsetDateTime.parse({_java_code_string_literal(raw_default)})"
                ".toLocalDateTime()"
            )
        return f"LocalDateTime.parse({_java_code_string_literal(raw_default)})"
    raise ValueError(
        f"Unsupported Java default for field '{field.name}' of type '{field.type.value}'."
    )


def _validated_java_integer_literal(value: str, *, context: str) -> str:
    if not _JAVA_INTEGER_LITERAL_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid Java integer literal for {context}.")
    return value


def _validated_java_decimal_literal(value: str, *, context: str) -> str:
    if not _JAVA_DECIMAL_LITERAL_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid Java decimal literal for {context}.")
    return value


def _validated_java_boolean_literal(value: str, *, context: str) -> str:
    normalized = value.lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"Invalid Java boolean literal for {context}.")
    return normalized


def _validate_java_date_literal(value: str, *, context: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid Java date literal for {context}.") from exc


def _validate_java_datetime_literal(value: str, *, context: str) -> None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid Java datetime literal for {context}.") from exc


def _operations_for_entity(
    metadata: MetadataProject, entity_name: str
) -> list:
    """Return operations bound to this entity (returned entity for selected GETs).

    Falls back to legacy name-based lookup for manifests that predate the
    request_entity field.
    """
    upstream_op_names: set[str] = {
        mapping.operation_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
        and mapping.operation_name is not None
    }
    ops = [
        op for op in metadata.operations
        if operation_entity_name(op) == entity_name
        and op.name in upstream_op_names
    ]
    if ops:
        return ops
    if not metadata.operations or not upstream_op_names:
        return []
    # Legacy fallback
    fallback_name = _create_operation_name_for_entity(metadata, entity_name)
    for op in metadata.operations:
        if op.name == fallback_name and op.name in upstream_op_names:
            return [op]
    return []


def _operation_contexts_for_entity(
    metadata: MetadataProject,
    entity: CanonicalEntity,
) -> list[dict]:
    """Build the deduplicated operation contexts consumed by Java and inventory emission."""

    entity_ops = _operations_for_entity(metadata, entity.name)
    entity_path_base = f"/{to_snake_case(entity.name)}s"
    entity_prefix = f"{entity.name}."
    op_contexts: list[dict] = []
    for operation in entity_ops:
        all_op_mappings = filter_mappings(
            metadata,
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=operation.interface_name,
            operation_name=operation.name,
        )
        mapping_contexts = [
            (mapping, operation_mapping_transport_context(
                mapping.source_path, operation.interface_name, operation.name,
            ))
            for mapping in all_op_mappings
        ]
        # Only a genuine selected response is exempt from input validation.
        # Unknown/wrong-context sources remain visible to the fail-fast guard.
        raw_request_mappings = [
            mapping for mapping, context in mapping_contexts if context != "response"
        ]
        request_mappings = _dedupe_field_mappings([
            mapping for mapping in raw_request_mappings
            if mapping.target_path.startswith(entity_prefix)
        ])
        response_mappings = _dedupe_field_mappings(
            [
                mapping
                for mapping, context in mapping_contexts
                if context == "response"
                and mapping.target_path.startswith(entity_prefix)
            ]
        )
        operation_class = to_java_class_name(
            operation.name,
            fallback="GeneratedOperation",
        )
        op_contexts.append(
            {
                "operation_name": operation.name,
                "interface_name": operation.interface_name,
                "java_operation_name": to_java_method_name(
                    operation.name,
                    fallback="generatedOperation",
                ),
                "request_class_name": f"{operation_class}Request",
                "response_class_name": f"{operation_class}Response",
                "path": entity_path_base,
                "spec_path": operation.path,
                "request_field_mappings": request_mappings,
                "raw_request_field_mappings": raw_request_mappings,
                "response_field_mappings": response_mappings,
                "http_method": operation.http_method,
                "response_shape": operation.response_shape,
                "pageable": operation.pageable,
                "path_parameters": list(operation.path_parameters),
                "operation_parameters": list(operation.operation_parameters),
                "has_request_body": operation.has_request_body,
                "read_input_errors": list(operation.read_input_errors),
            }
        )

    # Validate every selected contract before deduplication can discard a copy.
    _validate_computed_read_contexts(entity, [
        {**context, "request_field_mappings": context["raw_request_field_mappings"]}
        for context in op_contexts
    ])
    op_contexts = _dedupe_operation_contexts(entity.name, op_contexts)
    if len(op_contexts) > 1:
        for context in op_contexts:
            context["path"] = (
                f"{entity_path_base}/{to_snake_case(context['operation_name'])}"
            )
    return op_contexts


def _entity_java_artifact_plan(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    target_profile: TargetProfile,
) -> _EntityJavaArtifactPlan:
    """Return the exact per-entity Java artifact decisions for this generation."""

    operation_contexts = _operation_contexts_for_entity(metadata, entity)
    file_writer_contexts = _downstream_file_writer_contexts(metadata, entity)
    emit_staging_writer = _has_handoffs_for_entity(metadata, entity.name)
    has_downstream_file = _has_downstream_file_contract_for_entity(
        metadata,
        entity.name,
    )
    return _EntityJavaArtifactPlan(
        operation_contexts=operation_contexts,
        emit_generic_fallback_dtos=_should_emit_generic_fallback_dtos(
            operation_contexts
        ),
        emit_generic_create_fallback=_should_emit_generic_create_fallback(
            operation_contexts
        ),
        file_writer_contexts=file_writer_contexts,
        emit_staging_writer=emit_staging_writer,
        has_downstream_file=has_downstream_file,
        emit_batch_job=target_profile.emit_spring_batch
        and (emit_staging_writer or has_downstream_file),
    )


def _create_operation_name_for_entity(metadata: MetadataProject, entity_name: str) -> str:
    for operation in metadata.operations:
        if (
            operation_entity_name(operation) == entity_name
            and operation.name.lower().startswith("create")
        ):
            return operation.name
    for operation in metadata.operations:
        if operation_entity_name(operation) == entity_name:
            return operation.name
    raise ValueError(
        f"No upstream operation found for entity '{entity_name}'. "
        "Ensure the manifest declares an upstream operation with "
        f"request_entity: {entity_name}."
    )


def _has_handoffs(metadata: MetadataProject) -> bool:
    return any(contract.type == "staging-table" for contract in metadata.contracts)


def _has_fixed_width_contract(metadata: MetadataProject) -> bool:
    return any(contract.type == "file-fixed-width" for contract in metadata.contracts)


def _has_handoffs_for_entity(metadata: MetadataProject, entity_name: str) -> bool:
    return any(
        mapping.source_path.startswith(f"{entity_name}.")
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_HANDOFF
    )


def _has_downstream_file_contract_for_entity(metadata: MetadataProject, entity_name: str) -> bool:
    downstream_file_contracts = {
        contract.name
        for contract in metadata.contracts
        if contract.type in {"file-fixed-width", "file-csv"}
    }
    return any(
        mapping.source_path.startswith(f"{entity_name}.")
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.contract_name in downstream_file_contracts
    )


def _has_downstream_file_contracts(metadata: MetadataProject) -> bool:
    downstream_file_contracts = {
        contract.name
        for contract in metadata.contracts
        if contract.type in {"file-fixed-width", "file-csv"}
    }
    return any(
        mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.contract_name in downstream_file_contracts
        for mapping in metadata.mappings
    )


def _file_output_extension_for_entity(metadata: MetadataProject, entity_name: str) -> str:
    downstream_file_contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.source_path.startswith(f"{entity_name}.")
    }
    for contract in metadata.contracts:
        if contract.name in downstream_file_contract_names and contract.type == "file-csv":
            return "csv"
    return "dat"


def _has_enhanced_fixed_width_contract_for_entity(
    metadata: MetadataProject,
    entity_name: str,
) -> bool:
    downstream_file_contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.source_path.startswith(f"{entity_name}.")
    }
    for contract in metadata.contracts:
        if (
            contract.name in downstream_file_contract_names
            and contract.type == "file-fixed-width"
            and contract.file_layout
            and not bool(contract.file_layout.get("is_flat_fixed_width"))
        ):
            return True
    return False


def _validate_file_contract_runtime_support(metadata: MetadataProject) -> None:
    xml_contract_names = {
        contract.name
        for contract in metadata.contracts
        if contract.type == "xml-xsd"
    }
    for report in metadata.mapping_reports:
        if report.contract_name not in xml_contract_names:
            continue
        errors = [
            issue.message
            for issue in report.issues
            if issue.severity == MappingSeverity.ERROR
        ]
        if errors:
            raise ValueError(
                f"XML/XSD interface '{report.contract_name}' has invalid explicit mapping: "
                + "; ".join(errors)
            )
    for contract in metadata.contracts:
        if contract.type == "xml-xsd" and metadata.app_archetype != AppArchetype.CRUD:
            raise ValueError(
                f"XML/XSD runtime generation is currently implemented only for "
                f"app_archetype: crud. Interface '{contract.name}' uses "
                f"app_archetype: {metadata.app_archetype.value}."
            )
        if contract.type == "soap-wsdl":
            if metadata.app_archetype != AppArchetype.CRUD:
                raise ValueError(
                    f"SOAP/WSDL runtime generation is currently implemented only for "
                    f"app_archetype: crud. Interface '{contract.name}' uses "
                    f"app_archetype: {metadata.app_archetype.value}."
                )
            soap_contract = _require_soap_contract(contract)
            if soap_contract.get("direction") != "upstream":
                continue
            operation_mappings = _soap_operation_mappings(soap_contract)
            if not operation_mappings:
                raise ValueError(
                    f"Inbound SOAP/WSDL interface '{contract.name}' requires an explicit "
                    "operation mapping file with operation_mappings before endpoint generation."
                )
            _soap_handler_java_methods(contract)
            missing = [
                str(operation["name"])
                for operation in soap_contract.get("operations") or []
                if str(operation["name"]) not in operation_mappings
            ]
            if missing:
                raise ValueError(
                    f"Inbound SOAP/WSDL interface '{contract.name}' is missing operation "
                    f"mappings for: {', '.join(missing)}."
                )
            _validate_soap_canonical_operation_mappings(metadata, contract)
    return None


def _validate_soap_canonical_operation_mappings(
    metadata: MetadataProject,
    contract: ContractMetadata,
) -> None:
    soap_contract = _require_soap_contract(contract)
    canonical_mappings = _soap_canonical_operation_mappings(soap_contract)
    if not canonical_mappings:
        return
    entities_by_name = {entity.name: entity for entity in all_entities(metadata)}
    operations_by_name = {
        str(operation["name"]): operation for operation in soap_contract.get("operations") or []
    }
    for operation_name, mapping in canonical_mappings.items():
        canonical_operation = mapping.get("canonical_operation") or {}
        if canonical_operation.get("kind") != "read_by_id":
            raise ValueError(
                f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                "uses unsupported canonical operation kind. Only read_by_id is supported."
            )
        entity_name = str(canonical_operation.get("entity") or "")
        entity = entities_by_name.get(entity_name)
        if entity is None:
            raise ValueError(
                f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                f"references unknown canonical entity '{entity_name}'."
            )
        id_field = entity_id_field(entity)
        lookup = canonical_operation.get("lookup") or {}
        lookup_field_name = str(lookup.get("field") or "")
        if lookup_field_name != id_field.name:
            raise ValueError(
                f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                f"read_by_id lookup field '{lookup_field_name}' must be the persistence ID "
                f"'{entity.name}.{id_field.name}'. Business-key SOAP lookup requires a future "
                "explicit uniqueness/finder policy."
            )
        operation = operations_by_name.get(operation_name) or {}
        input_fields = _soap_fields_by_path(operation.get("input_fields") or [])
        request_path = str(lookup.get("request_path") or "")
        input_field = input_fields.get(request_path)
        if input_field is None:
            raise ValueError(
                f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                f"references unknown lookup request_path '{request_path}'."
            )
        if input_field.get("repeated"):
            raise ValueError(
                f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                f"lookup request_path '{request_path}' is repeated; read_by_id requires one scalar ID."
            )
        if not _xml_mapping_types_compatible(
            direction="upstream",
            xml_field=input_field,
            canonical_field=id_field,
        ):
            raise ValueError(
                f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                f"cannot map SOAP lookup '{request_path}' ({_xml_field_type_label(input_field)}) "
                f"to canonical persistence ID '{entity.name}.{id_field.name}' ({id_field.type.value})."
            )
        output_fields = _soap_fields_by_path(operation.get("output_fields") or [])
        fields_by_name = {field.name: field for field in entity.fields}
        for response_mapping in canonical_operation.get("response_mappings") or []:
            source = str(response_mapping.get("source") or "")
            if "." not in source:
                raise ValueError(
                    f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                    f"response source '{source}' must be an Entity.field path."
                )
            source_entity_name, source_field_name = source.split(".", 1)
            if source_entity_name != entity.name:
                raise ValueError(
                    f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                    f"response source '{source}' must reference canonical entity '{entity.name}'."
                )
            canonical_field = fields_by_name.get(source_field_name)
            if canonical_field is None:
                raise ValueError(
                    f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                    f"response source references unknown field '{source}'."
                )
            target_path = str(response_mapping.get("target_path") or "")
            output_field = output_fields.get(target_path)
            if output_field is None:
                raise ValueError(
                    f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                    f"response target_path '{target_path}' is not declared by the SOAP output element."
                )
            if output_field.get("repeated"):
                raise ValueError(
                    f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                    f"response target_path '{target_path}' is repeated; read_by_id supports flat scalar "
                    "SOAP response fields only."
                )
            if not _xml_mapping_types_compatible(
                direction="downstream",
                xml_field=output_field,
                canonical_field=canonical_field,
            ):
                raise ValueError(
                    f"Inbound SOAP/WSDL interface '{contract.name}' operation '{operation_name}' "
                    f"cannot map canonical field '{source}' ({canonical_field.type.value}) to SOAP "
                    f"response field '{target_path}' ({_xml_field_type_label(output_field)})."
                )


# ---------------------------------------------------------------------------
# Demo controller — config-gated /api/demo/entities endpoints
# ---------------------------------------------------------------------------

def emit_demo_controller(
    *,
    metadata: MetadataProject,
    target_profile: TargetProfile,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
) -> Path:
    """Generate DemoController.java — config-gated demo/internal endpoint.

    Generates GET /api/demo/entities and
    GET /api/demo/entities/{entityName} endpoints for all entities.
    Disabled by default via appbuilder.demo.enabled=false.
    """
    from .write_contract import validate_write_contracts
    validate_write_contracts(metadata, target_profile=target_profile, controller_scope="demo")
    root_package = base_package(metadata)
    root_path = output_dir / "src" / "main" / "java" / package_path(root_package)
    inbound_dir = root_path / "adapter" / "inbound"

    entities = all_entities(metadata)
    content = _render_demo_controller(
        entities=entities,
        root_package=root_package,
        source_manifest=source_manifest,
        target_profile=target_profile,
        generation_run_id=generation_run_id,
    )
    demo_path = inbound_dir / "DemoController.java"
    return _write_java_file(demo_path, content)


def _render_demo_controller(
    *,
    entities: list[CanonicalEntity],
    root_package: str,
    source_manifest: str,
    target_profile: TargetProfile,
    generation_run_id: str,
) -> str:
    """Generate the DemoController class body.

    This controller is intentionally internal/demo only.
    It is config-gated and MUST NOT be exposed in production without
    explicit opt-in via appbuilder.demo.enabled=true.
    """
    # Build registry constructor parameters and map entries
    constructor_params: list[str] = []
    map_puts: list[str] = []
    repo_imports: list[str] = []

    for entity in entities:
        repo_class = f"{entity.name}Repository"
        repo_var = f"{entity.name[:1].lower()}{entity.name[1:]}Repository"
        constructor_params.append(f"            {repo_class} {repo_var}")
        map_puts.append(
            f'        this.entityRepositories.put("{entity.name}", {repo_var});'
        )
        repo_imports.append(f"{root_package}.repository.{repo_class}")

    # Format constructor params with commas
    constructor_params_str = ",\n".join(constructor_params)

    body = [
        "// INTERNAL/DEMO controller — not for production use.",
        "// Enabled only when appbuilder.demo.enabled=true in application.yaml.",
        "@RestController",
        "@RequestMapping(\"/api/demo\")",
        "public class DemoController {",
        "",
        "    @Value(\"${appbuilder.demo.enabled:false}\")",
        "    private boolean demoEnabled;",
        "",
        "    private final java.util.Map<String, org.springframework.data.jpa.repository.JpaRepository<?, ?>> entityRepositories = new java.util.LinkedHashMap<>();",
        "",
        "    public DemoController(",
        constructor_params_str + ") {",
    ]
    body.extend(map_puts)
    body.extend([
        "    }",
        "",
        "    @GetMapping(\"/entities\")",
        "    public ResponseEntity<?> listEntities() {",
        "        if (!demoEnabled) {",
        "            return ResponseEntity.status(403).body(",
        "                java.util.Map.of(\"error\", \"Demo endpoints are disabled. Set appbuilder.demo.enabled=true to enable.\"));",
        "        }",
        "        java.util.List<java.util.Map<String, Object>> result = new java.util.ArrayList<>();",
        "        for (String name : entityRepositories.keySet()) {",
        "            result.add(java.util.Map.of(\"entityName\", name));",
        "        }",
        "        return ResponseEntity.ok(result);",
        "    }",
        "",
        "    @GetMapping(\"/entities/{entityName}\")",
        "    public ResponseEntity<?> getEntityRows(@PathVariable String entityName) {",
        "        if (!demoEnabled) {",
        "            return ResponseEntity.status(403).body(",
        "                java.util.Map.of(\"error\", \"Demo endpoints are disabled. Set appbuilder.demo.enabled=true to enable.\"));",
        "        }",
        "        org.springframework.data.jpa.repository.JpaRepository<?, ?> repo = entityRepositories.get(entityName);",
        "        if (repo == null) {",
        "            return ResponseEntity.status(404).body(",
        "                java.util.Map.of(\"error\", \"Unknown entity: \" + entityName,",
        "                                 \"available\", entityRepositories.keySet()));",
        "        }",
        "        java.util.List<?> rows = repo.findAll().stream().limit(50).collect(java.util.stream.Collectors.toList());",
        "        return ResponseEntity.ok(rows);",
        "    }",
        "}",
    ])

    imports = sorted(set(repo_imports + [
        "org.springframework.beans.factory.annotation.Value",
        "org.springframework.http.ResponseEntity",
        "org.springframework.web.bind.annotation.GetMapping",
        "org.springframework.web.bind.annotation.PathVariable",
        "org.springframework.web.bind.annotation.RequestMapping",
        "org.springframework.web.bind.annotation.RestController",
    ]))

    return _java_file(
        package_name=f"{root_package}.adapter.inbound",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile.name,
        generation_run_id=generation_run_id,
    )
