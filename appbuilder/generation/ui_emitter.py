"""Emit a generated static demo UI for each application."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    ContractMetadata,
    HttpMethod,
    MetadataProject,
    OperationParameterLocation,
    ResponseShape,
)
from appbuilder.rules import RuleType
from appbuilder.target_profiles.catalog import TARGET_PROFILES

from .audit import render_generated_file_header
from .utils import (
    canonical_field_name,
    contract_field_name,
    entity_id_field,
    filter_mappings,
    operation_entity_name,
    to_snake_case,
)
from .utils import (
    spec_entity_route_base_candidate as _spec_entity_route_base_candidate,
)
from .utils import (
    supports_spec_route as _supports_spec_route_helper,
)

_CREATE_OP_KEYWORDS = frozenset({
    "create", "add", "open", "register", "new", "initiate", "submit", "post",
})

_READ_OPERATION_CATEGORIES = frozenset({"get_by_id", "list", "computed_read", "read_list"})
_WRITE_OPERATION_CATEGORIES = frozenset({"create", "update", "delete", "state_transition"})
_ACTION_GROUP_ORDER = ("UPSTREAM", "DOWNSTREAM", "HANDOFF", "BATCH")
_ACTION_GROUP_LABELS = {
    "UPSTREAM": "Upstream",
    "DOWNSTREAM": "Downstream",
    "HANDOFF": "Handoffs",
    "BATCH": "Batch",
}
_ACTION_GROUP_ICONS = {
    "UPSTREAM": "\u2191",
    "DOWNSTREAM": "\u2193",
    "HANDOFF": "\u2194",
    "BATCH": "\u27f3",
}
_FILLABLE_INPUT_TYPES = frozenset({
    "checkbox",
    "date",
    "datetime-local",
    "number",
    "select",
    "text",
})


@dataclass(frozen=True)
class Action:
    verb: str
    endpoint: str
    inputControl: str
    inputBinding: str
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "verb": self.verb,
            "endpoint": self.endpoint,
            "inputControl": self.inputControl,
            "inputBinding": self.inputBinding,
        }
        if self.headers:
            payload["headers"] = dict(sorted(self.headers.items()))
        return payload


@dataclass(frozen=True)
class Provenance:
    contractName: str
    direction: str
    sourceArtifact: str
    mappingRef: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contractName": self.contractName,
            "direction": self.direction,
            "sourceArtifact": self.sourceArtifact,
        }
        if self.mappingRef is not None:
            payload["mappingRef"] = self.mappingRef
        return payload


@dataclass(frozen=True)
class ActionCardDescriptor:
    family: str
    group: str
    title: str
    actions: list[Action]
    responseShape: str
    provenance: Provenance
    coverageKey: str
    hints: list[dict[str, Any]] = field(default_factory=list)
    samplePrefill: str | dict[str, Any] | None = None
    owner_entity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "family": self.family,
            "group": self.group,
            "title": self.title,
            "actions": [action.to_dict() for action in self.actions],
            "responseShape": self.responseShape,
            "provenance": self.provenance.to_dict(),
            "coverageKey": self.coverageKey,
            "hints": self.hints,
        }
        if self.samplePrefill is not None:
            payload["samplePrefill"] = self.samplePrefill
        return payload


def _is_create_operation(operation: CanonicalOperation) -> bool:
    """Return True when the operation name suggests create semantics.

    Used to pick the right panel when multiple operations share an entity —
    e.g. createCustomer should win over updateCustomer even if the update
    operation appears first in the manifest.
    """
    lower = operation.name.lower()
    return any(kw in lower for kw in _CREATE_OP_KEYWORDS)


def _ui_operation_category(operation: CanonicalOperation) -> str | None:
    lower_name = operation.name.lower()
    if operation.response_shape == ResponseShape.CREATED or _is_create_operation(operation):
        return "create"
    if operation.http_method == HttpMethod.PUT or lower_name.startswith("update"):
        return "update"
    if operation.http_method == HttpMethod.DELETE or lower_name.startswith(("delete", "remove")):
        return "delete"
    if operation.http_method == HttpMethod.GET and operation.response_shape == ResponseShape.SINGLE:
        if operation.path_parameters:
            return "get_by_id"
        return "computed_read"
    if operation.http_method == HttpMethod.GET and operation.response_shape == ResponseShape.LIST:
        if not operation.path_parameters:
            return "list"
        return "read_list"
    if operation.http_method == HttpMethod.POST:
        return "state_transition"
    return None


def generate_demo_ui(
    metadata: MetadataProject,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
) -> Path:
    """Generate src/main/resources/static/index.html from metadata.

    # upgraded to full operator dashboard with entity
    # sidebar, per-entity CRUD tabs, request/response panels, and live
    # data viewer backed by DemoController /api/demo/entities endpoints.
    """

    panels = _build_operation_panels(metadata)

    static_dir = output_dir / "src" / "main" / "resources" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    html_path = static_dir / "index.html"
    html_path.write_text(
        _render_operator_dashboard(
            metadata=metadata,
            panels=panels,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        encoding="utf-8",
    )
    return html_path


def _append_generation_warning(metadata: MetadataProject, warning: str) -> None:
    if warning not in metadata.warnings:
        metadata.warnings.append(warning)


def _build_operation_panels(metadata: MetadataProject) -> list[dict]:
    """Build one panel descriptor per entity for the create operation.

    The generated create form must submit to the same entity route base used by
    the generated controller. When the controller preserves a common upstream
    spec route base (for example ``/pet`` + ``/pet/{petId}``), the UI must use
    that preserved base too. Otherwise it falls back to the legacy
    ``/{snake_case_entity}s`` convention.

    When multiple operations share the same entity (e.g. createCustomer +
    updateCustomer) the create operation is selected explicitly — not just
    whichever appears first in the manifest.  This means the form is always
    built from the create request shape even when the manifest lists update
    or delete operations before create.
    """
    # Group all request-bearing operations by entity, preserving manifest order.
    entity_ops: dict[str, list[CanonicalOperation]] = {}
    for operation in metadata.operations:
        if not _is_ui_operation_candidate(metadata, operation):
            continue
        if operation.request_entity is None:
            continue
        try:
            request_entity = _request_entity(metadata, operation)
        except ValueError:
            continue
        entity_ops.setdefault(request_entity.name, []).append(operation)

    panels = []
    for _entity_name, ops in entity_ops.items():
        # Prefer an explicitly create-named operation; fall back to first if none found.
        create_ops = [op for op in ops if _is_create_operation(op)]
        operation = create_ops[0] if create_ops else ops[0]

        request_entity = _request_entity(metadata, operation)
        request_fields = _request_fields(metadata, operation, request_entity.name)
        if not request_fields:
            continue
        # Namespace DOM ids per operation to prevent duplicate ids across forms
        # (e.g. both Customer and Account forms may have a "customerId" field)
        field_descriptors = [
            {
                **_build_field_descriptor(metadata, request_entity.name, field, mapping),
                "id": f"{operation.name}-{field.name}",
            }
            for field, mapping in request_fields
        ]
        endpoint = _entity_route_base(metadata, request_entity.name)
        panels.append({
            "operation": operation,
            "entity_name": request_entity.name,
            "field_descriptors": field_descriptors,
            "endpoint": endpoint,
            "form_id": f"form-{operation.name}",
            "response_panel_id": f"response-{operation.name}",
        })
    if not panels:
        if any(contract.run_semantics is not None for contract in metadata.contracts):
            # Opted-in staging-only apps still need the S2 batch trigger card, but
            # have no upstream REST operation from which to build a CRUD form.
            return []
        if (
            _has_upstream_file_to_canonical_mappings(metadata)
            or _has_downstream_file_contracts(metadata)
            or _has_upstream_xml_to_canonical_mappings(metadata)
            or _has_downstream_xml_contracts(metadata)
        ):
            return []
        # Absolute fallback for manifests without request_entity declared
        operation = _primary_upstream_operation(metadata)
        request_entity = _request_entity(metadata, operation)
        request_fields = _request_fields(metadata, operation, request_entity.name)
        field_descriptors = [
            {
                **_build_field_descriptor(metadata, request_entity.name, field, mapping),
                "id": f"{operation.name}-{field.name}",
            }
            for field, mapping in request_fields
        ]
        panels.append({
            "operation": operation,
            "entity_name": request_entity.name,
            "field_descriptors": field_descriptors,
            "endpoint": f"/{metadata.bounded_context}",
            "form_id": "appbuilder-demo-form",
            "response_panel_id": "response-panel",
        })
    return panels


def _contract_for_name(metadata: MetadataProject, name: str) -> ContractMetadata | None:
    return next((contract for contract in metadata.contracts if contract.name == name), None)


def _contract_source_artifact(contract: ContractMetadata | None) -> str:
    if contract is None:
        return ""
    return contract.source or ""


def _contract_mapping_ref(contract: ContractMetadata | None) -> str | None:
    if contract is None:
        return None
    return contract.mapping_path


def _configured_datasource_label(metadata: MetadataProject) -> str:
    target_profile = TARGET_PROFILES.get(metadata.target_profile)
    dependency_value = target_profile.runtime_database_dependency if target_profile else "h2"
    dependency = (dependency_value or "h2").lower()
    if dependency == "postgresql" or "postgres" in dependency:
        return "PostgreSQL"
    if dependency == "h2":
        return "H2"
    return dependency.upper() if dependency else "Unknown"


def _descriptor_response_panel_id(descriptor: ActionCardDescriptor) -> str:
    return f"resp-panel-{_safe_dom_id(descriptor.coverageKey)}"


def _coverage_chip_id(coverage_key: str) -> str:
    return f"coverage-chip-{_safe_dom_id(coverage_key)}"


def _render_coverage_map(descriptors: list[ActionCardDescriptor]) -> str:
    if not descriptors:
        return ""

    entries: list[str] = []
    for descriptor in descriptors:
        coverage_key = descriptor.coverageKey
        coverage_key_attr = html.escape(coverage_key, quote=True)
        title = html.escape(descriptor.title)
        family = html.escape(descriptor.family)
        group = html.escape(descriptor.group)
        chip_id = _coverage_chip_id(coverage_key)
        onclick_key = html.escape(json.dumps(coverage_key), quote=True)
        entries.append(
            f"""
            <button
                class="coverage-entry"
                type="button"
                data-coverage-entry="{coverage_key_attr}"
                onclick="focusCoverageCard({onclick_key})"
            >
                <span class="coverage-title">{title}</span>
                <span class="coverage-meta">{family} · {group}</span>
                <span
                    id="{chip_id}"
                    class="status-badge coverage-chip not-tried"
                    data-coverage-status="not-tried"
                >not yet tried</span>
            </button>
            """.rstrip()
        )

    entries_html = "\n".join(entries)
    return f"""
            <section class="coverage-map" aria-labelledby="coverage-map-title">
                <div class="coverage-map-header">
                    <div>
                        <h2 id="coverage-map-title">Contract Coverage Map</h2>
                        <p>Visual exercise tracking only. Static compatibility remains in the harness and TestBench.</p>
                    </div>
                    <span class="coverage-map-count">{len(descriptors)} descriptors</span>
                </div>
                <div class="coverage-map-grid">
{entries_html}
                </div>
            </section>
    """.rstrip()


def _render_provenance_panel(descriptor: ActionCardDescriptor) -> str:
    provenance = descriptor.provenance
    contract_name = provenance.contractName or "generated operation"
    source_artifact = provenance.sourceArtifact or ""
    direction = provenance.direction or "UNKNOWN"
    mapping_ref = provenance.mappingRef or ""

    if source_artifact:
        summary = f"preserves {contract_name} from {source_artifact}"
    elif provenance.contractName == "generated-crud":
        summary = "generated CRUD operation — no source contract"
    else:
        summary = f"preserves {contract_name} from generated metadata"

    mapping_html = ""
    if mapping_ref:
        mapping_html = f"""
                    <div class="provenance-line" data-provenance-mapping="{html.escape(mapping_ref, quote=True)}">
                        <strong>Mapping</strong>
                        <span>{html.escape(mapping_ref)}</span>
                    </div>
        """.rstrip()

    return f"""
                <details
                    class="provenance-panel"
                    data-provenance-contract="{html.escape(contract_name, quote=True)}"
                    data-provenance-direction="{html.escape(direction, quote=True)}"
                    data-provenance-source="{html.escape(source_artifact, quote=True)}"
                >
                    <summary>Provenance</summary>
                    <div class="provenance-body">
                        <p>{html.escape(summary)}</p>
                        <div class="provenance-line">
                            <strong>Direction</strong>
                            <span>{html.escape(direction)}</span>
                        </div>
{mapping_html}
                    </div>
                </details>
    """.rstrip()


def _path_field_descriptor(
    *,
    input_id: str,
    label: str,
    placeholder: str,
    help_text: str | None = None,
) -> dict[str, Any]:
    descriptor = {
        "id": input_id,
        "label": label,
        "canonicalName": "path",
        "contractName": "path",
        "inputType": "text",
        "required": True,
        "maxLength": None,
        "minLength": None,
        "pattern": None,
        "minValue": None,
        "maxValue": None,
        "defaultValue": None,
        "allowedValues": [],
        "placeholder": placeholder,
        "step": None,
    }
    if help_text:
        descriptor["helpText"] = help_text
    return descriptor


def _id_json_body_field_descriptor(
    *,
    input_id: str,
    label: str,
    help_text: str,
) -> dict[str, Any]:
    return {
        "id": input_id,
        "label": label,
        "canonicalName": "id",
        "contractName": "id",
        "inputType": "text",
        "required": True,
        "maxLength": None,
        "minLength": None,
        "pattern": None,
        "minValue": None,
        "maxValue": None,
        "defaultValue": None,
        "allowedValues": [],
        "placeholder": "canonical-id",
        "step": None,
        "helpText": help_text,
    }


def _raw_body_field_descriptor(
    *,
    input_id: str,
    label: str,
    placeholder: str,
    help_text: str,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "id": input_id,
        "label": label,
        "canonicalName": "body",
        "contractName": "body",
        "inputType": "textarea",
        "required": required,
        "maxLength": None,
        "minLength": None,
        "pattern": None,
        "minValue": None,
        "maxValue": None,
        "defaultValue": "",
        "allowedValues": [],
        "placeholder": placeholder,
        "step": None,
        "helpText": help_text,
    }


def _is_fillable_scalar_hint(hint: dict[str, Any]) -> bool:
    if hint.get("outputHint") or hint.get("bodyField"):
        return False
    return str(hint.get("inputType") or "") in _FILLABLE_INPUT_TYPES


def _descriptor_should_show_sample_button(descriptor: ActionCardDescriptor) -> bool:
    fillable_hints = [
        hint for hint in descriptor.hints if _is_fillable_scalar_hint(hint)
    ]
    if not fillable_hints:
        return False

    endpoint_placeholders = {
        placeholder
        for action in descriptor.actions
        for placeholder in re.findall(r"\{([^{}]+)\}", action.endpoint)
    }
    if not endpoint_placeholders:
        return True
    return any(
        str(hint.get("contractName") or hint.get("canonicalName") or "")
        not in endpoint_placeholders
        for hint in fillable_hints
    )


def _field_type_label(field_descriptor: dict[str, object]) -> str:
    input_type = str(field_descriptor.get("inputType") or "text")
    if input_type == "checkbox":
        return "boolean"
    if input_type == "datetime-local":
        return "datetime"
    if input_type == "number" and field_descriptor.get("step"):
        return "decimal"
    if input_type == "select":
        return "enum"
    if input_type == "date":
        return "date"
    if input_type == "number":
        return "number"
    return "text"


def _range_summary(min_value: object, max_value: object) -> str | None:
    if min_value is not None and max_value is not None:
        return f"{min_value}\u2013{max_value}"
    if min_value is not None:
        return f"min {min_value}"
    if max_value is not None:
        return f"max {max_value}"
    return None


def _field_rule_summary(field_descriptor: dict[str, object]) -> str:
    parts = [
        "required" if field_descriptor.get("required") else "optional",
        _field_type_label(field_descriptor),
    ]
    min_length = field_descriptor.get("minLength")
    max_length = field_descriptor.get("maxLength")
    if min_length is not None and max_length is not None:
        parts.append(f"length {min_length}\u2013{max_length}")
    elif min_length is not None:
        parts.append(f"min length {min_length}")
    elif max_length is not None:
        parts.append(f"max length {max_length}")
    if range_text := _range_summary(
        field_descriptor.get("minValue"),
        field_descriptor.get("maxValue"),
    ):
        parts.append(str(range_text))
    if pattern := field_descriptor.get("pattern"):
        parts.append(f"pattern {pattern}")
    allowed_values = list(field_descriptor.get("allowedValues") or [])
    if allowed_values:
        parts.append("allowed " + ", ".join(str(value) for value in allowed_values))
    return " \u00b7 ".join(parts)


def _build_action_card_descriptors(
    metadata: MetadataProject,
    panels: list[dict],
) -> list[ActionCardDescriptor]:
    descriptors: list[ActionCardDescriptor] = []
    panels_by_entity = {panel["entity_name"]: panel for panel in panels}

    for entity in metadata.entities:
        entity_name = entity.name
        entity_route_base = _entity_route_base(metadata, entity_name)
        tabs = _rendered_dashboard_tabs(
            metadata,
            entity_name,
            has_create_panel=entity_name in panels_by_entity,
        )
        tab_names = {tab_name for tab_name, _label in tabs}

        if "create" in tab_names and entity_name in panels_by_entity:
            panel = panels_by_entity[entity_name]
            operation: CanonicalOperation = panel["operation"]
            contract = _contract_for_name(metadata, operation.interface_name)
            descriptors.append(
                ActionCardDescriptor(
                    family="rest-crud",
                    group="UPSTREAM",
                    title=f"Create {entity_name}",
                    actions=[
                        Action(
                            verb="POST",
                            endpoint=panel["endpoint"],
                            inputControl="FORM",
                            inputBinding="JSON_BODY",
                        )
                    ],
                    responseShape="JSON",
                    provenance=Provenance(
                        contractName=operation.interface_name,
                        direction="UPSTREAM",
                        sourceArtifact=_contract_source_artifact(contract),
                        mappingRef=_contract_mapping_ref(contract),
                    ),
                    coverageKey=f"{entity_name}-create",
                    hints=[*panel["field_descriptors"], *_build_query_parameter_descriptors(
                        entity_name=entity_name, tab_name="create", operation=operation, write=True)],
                )
            )

        if "get" in tab_names:
            operation = _entity_get_operation(metadata, entity_name)
            contract = _contract_for_name(metadata, operation.interface_name) if operation else None
            route_template = _read_route_template(
                metadata,
                entity_name,
                operation,
                tab_name="get",
            )
            hints = [
                _build_template_path_field_descriptor(
                    metadata,
                    entity,
                    input_id=f"get-id-{entity_name}",
                    route_template=route_template,
                )
            ]
            hints.extend(
                {
                    **descriptor,
                    "query": True,
                }
                for descriptor in _build_query_parameter_descriptors(
                    entity_name=entity_name,
                    tab_name="get",
                    operation=operation,
                )
            )
            descriptors.append(
                ActionCardDescriptor(
                    family="rest-crud",
                    group="UPSTREAM",
                    title=(
                        f"Get {entity_name}"
                        if _uses_explicit_read_surface(metadata, entity_name)
                        else f"Get {entity_name} by ID"
                    ),
                    actions=[
                        Action(
                            verb="GET",
                            endpoint=route_template,
                            inputControl="ID",
                            inputBinding="PATH_PARAM",
                        )
                    ],
                    responseShape="JSON",
                    provenance=Provenance(
                        contractName=operation.interface_name if operation else "generated-crud",
                        direction="UPSTREAM",
                        sourceArtifact=_contract_source_artifact(contract),
                        mappingRef=_contract_mapping_ref(contract),
                    ),
                    coverageKey=f"{entity_name}-get",
                    hints=hints,
                )
            )

        if "list" in tab_names:
            operation = _entity_list_operation(metadata, entity_name)
            contract = _contract_for_name(metadata, operation.interface_name) if operation else None
            route_template = _read_route_template(
                metadata,
                entity_name,
                operation,
                tab_name="list",
            )
            descriptors.append(
                ActionCardDescriptor(
                    family="rest-crud",
                    group="UPSTREAM",
                    title=(
                        f"List {entity_name}"
                        if _uses_explicit_read_surface(metadata, entity_name)
                        else f"List All {entity_name}s"
                    ),
                    actions=[
                        Action(
                            verb="GET",
                            endpoint=route_template,
                            inputControl="NONE",
                            inputBinding="NONE",
                        )
                    ],
                    responseShape="JSON",
                    provenance=Provenance(
                        contractName=operation.interface_name if operation else "generated-crud",
                        direction="UPSTREAM",
                        sourceArtifact=_contract_source_artifact(contract),
                        mappingRef=_contract_mapping_ref(contract),
                    ),
                    coverageKey=f"{entity_name}-list",
                    hints=[
                        {
                            **descriptor,
                            "query": True,
                        }
                        for descriptor in _build_query_parameter_descriptors(
                            entity_name=entity_name,
                            tab_name="list",
                            operation=operation,
                        )
                    ],
                )
            )

        if "update" in tab_names:
            descriptors.append(
                ActionCardDescriptor(
                    family="rest-crud",
                    group="UPSTREAM",
                    title=f"Update {entity_name}",
                    actions=[
                        Action(
                            verb="PUT",
                            endpoint=f"{entity_route_base}/{{id}}",
                            inputControl="FORM",
                            inputBinding="JSON_BODY",
                        )
                    ],
                    responseShape="JSON",
                    provenance=Provenance(
                        contractName="generated-crud",
                        direction="UPSTREAM",
                        sourceArtifact="",
                    ),
                    coverageKey=f"{entity_name}-update",
                    hints=[
                        _build_template_path_field_descriptor(
                            metadata,
                            entity,
                            input_id=f"update-id-{entity_name}",
                            route_template=f"{entity_route_base}/{{id}}",
                        ),
                        {
                            "id": f"update-body-{entity_name}",
                            "label": "Request Body (JSON)",
                            "canonicalName": "body",
                            "contractName": "body",
                            "inputType": "textarea",
                            "required": True,
                            "maxLength": None,
                            "minLength": None,
                            "pattern": None,
                            "minValue": None,
                            "maxValue": None,
                            "defaultValue": "",
                            "allowedValues": [],
                            "placeholder": '{"field": "value"}',
                            "step": None,
                            "bodyField": True,
                        },
                        *_build_query_parameter_descriptors(entity_name=entity_name, tab_name="update",
                            operation=next((op for op in _entity_operations(metadata, entity_name) if _ui_operation_category(op) == "update"), None), write=True),
                    ],
                )
            )

        if "delete" in tab_names:
            descriptors.append(
                ActionCardDescriptor(
                    family="rest-crud",
                    group="UPSTREAM",
                    title=f"Delete {entity_name}",
                    actions=[
                        Action(
                            verb="DELETE",
                            endpoint=f"{entity_route_base}/{{id}}",
                            inputControl="ID",
                            inputBinding="PATH_PARAM",
                        )
                    ],
                    responseShape="JSON",
                    provenance=Provenance(
                        contractName="generated-crud",
                        direction="UPSTREAM",
                        sourceArtifact="",
                    ),
                    coverageKey=f"{entity_name}-delete",
                    hints=[
                        _build_template_path_field_descriptor(
                            metadata,
                            entity,
                            input_id=f"delete-id-{entity_name}",
                            route_template=f"{entity_route_base}/{{id}}",
                        ),
                        *_build_query_parameter_descriptors(entity_name=entity_name, tab_name="delete",
                            operation=next((op for op in _entity_operations(metadata, entity_name) if _ui_operation_category(op) == "delete"), None), write=True),
                    ],
                )
            )

        for contract in _upstream_file_contracts_for_entity(metadata, entity_name):
            descriptors.append(
                ActionCardDescriptor(
                    family="file",
                    group="UPSTREAM",
                    title=f"Ingest {contract.name}",
                    actions=[
                        Action(
                            verb="POST",
                            endpoint="/files/ingest/{contractName}",
                            inputControl="PATH",
                            inputBinding="JSON_BODY",
                        )
                    ],
                    responseShape="JSON",
                    provenance=Provenance(
                        contractName=contract.name,
                        direction="UPSTREAM",
                        sourceArtifact=_contract_source_artifact(contract),
                        mappingRef=_contract_mapping_ref(contract),
                    ),
                    coverageKey=f"file-{entity_name}-{contract.name}",
                    hints=[
                        _path_field_descriptor(
                            input_id=_safe_dom_id(f"ingest-{entity_name}-{contract.name}-path"),
                            label="Server-side file path",
                            placeholder="relative/path/to/input.dat",
                            help_text="Resolved under app.file-ingest.base-dir.",
                        )
                    ],
                )
            )

        for contract in _upstream_xml_contracts_for_entity(metadata, entity_name):
            descriptors.append(
                ActionCardDescriptor(
                    family="xml",
                    group="UPSTREAM",
                    title=f"Ingest XML {contract.name}",
                    actions=[
                        Action(
                            verb="POST",
                            endpoint="/xml/ingest/{contractName}",
                            inputControl="PATH",
                            inputBinding="JSON_BODY",
                        )
                    ],
                    responseShape="JSON",
                    provenance=Provenance(
                        contractName=contract.name,
                        direction="UPSTREAM",
                        sourceArtifact=_contract_source_artifact(contract),
                        mappingRef=_contract_mapping_ref(contract),
                    ),
                    coverageKey=f"xml-{entity_name}-ingest-{contract.name}",
                    hints=[
                        _path_field_descriptor(
                            input_id=_safe_dom_id(f"xml-ingest-{entity_name}-{contract.name}-path"),
                            label="Server-side XML path",
                            placeholder="relative/path/to/input.xml",
                            help_text="Resolved under app.xml-ingest.base-dir.",
                        )
                    ],
                )
            )

        for contract in _downstream_xml_contracts_for_entity(metadata, entity_name):
            descriptors.append(
                ActionCardDescriptor(
                    family="xml",
                    group="DOWNSTREAM",
                    title=f"Write XML {contract.name}",
                    actions=[
                        Action(
                            verb="POST",
                            endpoint="/xml/output/{contractName}",
                            inputControl="NONE",
                            inputBinding="NONE",
                        )
                    ],
                    responseShape="JSON",
                    provenance=Provenance(
                        contractName=contract.name,
                        direction="DOWNSTREAM",
                        sourceArtifact=_contract_source_artifact(contract),
                        mappingRef=_contract_mapping_ref(contract),
                    ),
                    coverageKey=f"xml-{entity_name}-output-{contract.name}",
                    hints=[{"outputHint": "app.xml-output.base-dir"}],
                )
            )

        for context in _upstream_soap_canonical_ops_for_entity(metadata, entity_name):
            contract = context["contract"]
            operation = context["operation"]
            operation_name = str(context["operation_name"])
            soap_action = str(operation.get("soap_action") or "")
            headers = {"Content-Type": "text/xml; charset=utf-8"}
            if soap_action:
                headers["SOAPAction"] = soap_action
            input_element = str(operation.get("input_element") or "SOAP request")
            service_name = str(context["soap_contract"].get("service") or contract.name)
            wsdl_hint = f"/ws/{contract.name}.wsdl"
            helper_parts = [
                f"Request element: {input_element}.",
                f"WSDL: {wsdl_hint}.",
                f"Service: {service_name}.",
            ]
            if soap_action:
                helper_parts.append(f"SOAPAction: {soap_action}.")
            descriptors.append(
                ActionCardDescriptor(
                    family="soap-inbound",
                    group="UPSTREAM",
                    title=f"Inbound SOAP {operation_name}",
                    actions=[
                        Action(
                            verb="POST",
                            endpoint="/ws",
                            inputControl="TEXTAREA",
                            inputBinding="RAW_BODY",
                            headers=headers,
                        )
                    ],
                    responseShape="SOAP",
                    provenance=Provenance(
                        contractName=contract.name,
                        direction="UPSTREAM",
                        sourceArtifact=_contract_source_artifact(contract),
                        mappingRef=_contract_mapping_ref(contract),
                    ),
                    coverageKey=f"soap-inbound-{entity_name}-{contract.name}-{operation_name}",
                    hints=[
                        _raw_body_field_descriptor(
                            input_id=_safe_dom_id(
                                f"soap-inbound-{entity_name}-{contract.name}-{operation_name}-body"
                            ),
                            label="SOAP envelope",
                            placeholder="Paste SOAP envelope here",
                            help_text=" ".join(helper_parts),
                        )
                    ],
                )
            )

        for context in _downstream_soap_canonical_ops_for_entity(metadata, entity_name):
            contract = context["contract"]
            operation_name = str(context["operation_name"])
            canonical_operation = context["canonical_operation"]
            lookup = canonical_operation.get("lookup") or {}
            lookup_field = str(lookup.get("field") or "id")
            descriptors.append(
                ActionCardDescriptor(
                    family="soap-outbound",
                    group="DOWNSTREAM",
                    title=f"Invoke SOAP {operation_name}",
                    actions=[
                        Action(
                            verb="POST",
                            endpoint=f"/soap/outbound/{contract.name}/{operation_name}",
                            inputControl="ID",
                            inputBinding="JSON_BODY",
                        )
                    ],
                    responseShape="JSON",
                    provenance=Provenance(
                        contractName=contract.name,
                        direction="DOWNSTREAM",
                        sourceArtifact=_contract_source_artifact(contract),
                        mappingRef=_contract_mapping_ref(contract),
                    ),
                    coverageKey=f"soap-outbound-{entity_name}-{contract.name}-{operation_name}",
                    hints=[
                        _id_json_body_field_descriptor(
                            input_id=_safe_dom_id(
                                f"soap-outbound-{entity_name}-{contract.name}-{operation_name}-id"
                            ),
                            label="Canonical ID",
                            help_text=(
                                f"Looks up {entity_name}.{lookup_field} before invoking "
                                f"downstream SOAP operation {operation_name}."
                            ),
                        )
                    ],
                )
            )

    for action in _batch_actions(metadata):
        run_semantics = action.get("runSemantics")
        run_semantics_hints = (
            _batch_run_semantics_hints(
                job_name=str(action["jobName"]),
                effective_run_id_max=int(action["effectiveRunIdMax"]),
            )
            if run_semantics
            else []
        )
        descriptors.append(
            ActionCardDescriptor(
                family="batch",
                group="BATCH",
                title=action["label"],
                actions=[
                    Action(
                        verb="POST",
                        endpoint="/batch/run/{jobName}",
                        inputControl="FORM" if run_semantics else "NONE",
                        inputBinding="JSON_BODY" if run_semantics else "NONE",
                    )
                ],
                responseShape="JSON",
                provenance=Provenance(
                    contractName=action["jobName"],
                    direction="HANDOFF",
                    sourceArtifact=action["outputHint"],
                ),
                coverageKey=f"batch-{action['jobName']}",
                hints=[*run_semantics_hints, {"outputHint": action["outputHint"]}],
                owner_entity=action["entityName"],
            )
        )

    return descriptors


def _render_demo_ui(
    *,
    metadata: MetadataProject,
    panels: list[dict],
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=metadata.target_profile,
        generation_run_id=generation_run_id,
        comment_style="xml",
    )

    contracts_html = "\n".join(
        (
            "        <li class=\"contract-item\">"
            f"<span class=\"contract-check\">✅</span>"
            f"<span class=\"contract-name\">{html.escape(contract.name)}</span>"
            f"<span class=\"contract-type\">{html.escape(contract.type)}</span>"
            "</li>"
        )
        for contract in metadata.contracts
    )

    entities_html = "\n".join(
        (
            "        <li class=\"contract-item\">"
            f"<span class=\"contract-check\">🗂️</span>"
            f"<span class=\"contract-name\">{html.escape(entity.name)}</span>"
            f"<span class=\"contract-type\">{len(entity.fields)} fields</span>"
            "</li>"
        )
        for entity in metadata.entities
    )

    # One <section> per panel — one per upstream operation
    operation_sections_html = "\n\n".join(
        _render_operation_section(panel) for panel in panels
    )

    # JS config: one entry per panel so each form posts to its own entity endpoint
    forms_config = json.dumps(
        [
            {
                "formId": panel["form_id"],
                "responsePanelId": panel["response_panel_id"],
                "endpoint": panel["endpoint"],
                "fieldDescriptors": panel["field_descriptors"],
            }
            for panel in panels
        ],
        indent=2,
    )

    return f"""{header}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(metadata.app_name)} Demo UI</title>
  <style>
    :root {{
      --navy: #1a237e;
      --navy-deep: #10195c;
      --surface: #ffffff;
      --background: #f5f7fb;
      --border: #d8deea;
      --text: #1f2937;
      --muted: #6b7280;
      --success: #4caf50;
      --error: #f44336;
      --shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: var(--background);
      color: var(--text);
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      line-height: 1.5;
    }}

    .page {{
      max-width: 800px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}

    .banner {{
      background: linear-gradient(135deg, var(--navy), var(--navy-deep));
      color: #fff;
      border-radius: 18px;
      padding: 28px;
      box-shadow: var(--shadow);
      margin-bottom: 20px;
    }}

    .banner h1 {{
      margin: 0 0 8px;
      font-size: 2rem;
    }}

    .banner p {{
      margin: 4px 0;
      opacity: 0.92;
    }}

    .section {{
      background: var(--surface);
      border-radius: 18px;
      padding: 24px;
      box-shadow: var(--shadow);
      margin-bottom: 20px;
    }}

    .section h2 {{
      margin-top: 0;
      margin-bottom: 16px;
      font-size: 1.25rem;
    }}

    .contracts {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 12px;
    }}

    .contract-item {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: #fbfcff;
    }}

    .contract-check {{
      font-size: 1.2rem;
    }}

    .contract-name {{
      font-weight: 600;
      flex: 1;
    }}

    .contract-type {{
      color: var(--muted);
      font-size: 0.95rem;
      text-transform: lowercase;
    }}

    form {{
      display: grid;
      gap: 18px;
    }}

    .field {{
      display: grid;
      gap: 8px;
    }}

    .field label {{
      font-weight: 600;
    }}

    .field label .optional {{
      color: var(--muted);
      font-weight: 400;
      margin-left: 6px;
    }}

    .field .hint {{
      color: var(--muted);
      font-size: 0.9rem;
      margin-top: -2px;
    }}

    input,
    select {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 14px;
      font: inherit;
      background: #fff;
    }}

    input:focus,
    select:focus {{
      outline: 2px solid rgba(26, 35, 126, 0.18);
      border-color: var(--navy);
    }}

    .checkbox-row {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .checkbox-row input {{
      width: auto;
      margin: 0;
    }}

    button {{
      justify-self: start;
      border: none;
      border-radius: 999px;
      background: var(--navy);
      color: #fff;
      padding: 12px 18px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      box-shadow: 0 10px 20px rgba(26, 35, 126, 0.18);
    }}

    button:hover {{
      background: var(--navy-deep);
    }}

    .response-panel {{
      display: none;
      margin-top: 18px;
      border-radius: 14px;
      padding: 16px;
      border: 1px solid var(--border);
      background: #f8fafc;
    }}

    .response-panel.success {{
      display: block;
      border-color: var(--success);
      background: rgba(76, 175, 80, 0.08);
    }}

    .response-panel.error {{
      display: block;
      border-color: var(--error);
      background: rgba(244, 67, 54, 0.08);
      color: var(--error);
    }}

    pre {{
      margin: 0;
      overflow-x: auto;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      font-size: 0.92rem;
      white-space: pre-wrap;
      word-break: break-word;
    }}

    footer {{
      color: var(--muted);
      text-align: center;
      font-size: 0.92rem;
      padding: 8px 0 0;
    }}

    @media (max-width: 768px) {{
      .page {{
        padding: 16px 12px 32px;
      }}

      .banner,
      .section {{
        padding: 20px;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="banner">
      <p>{html.escape(metadata.bounded_context)} bounded context</p>
      <h1>{html.escape(metadata.app_name)}</h1>
      <p>Generated by EdgeForge — do not edit manually</p>
    </section>

    <section class="section">
      <h2>Preserved Contracts</h2>
      <ul class="contracts">
{contracts_html}
      </ul>
    </section>

{operation_sections_html}

    <section class="section">
      <h2>Generated Domain Entities</h2>
      <ul class="contracts">
{entities_html}
      </ul>
    </section>

    <footer>
      Generated by EdgeForge | Profile: {html.escape(metadata.target_profile)} | Run: {html.escape(generation_run_id)}
    </footer>
  </main>

  <script>
    const forms = {forms_config};

    function coerceValue(field, element) {{
      if (field.inputType === "checkbox") {{
        return element.checked;
      }}
      if (element.value === "") {{
        return null;
      }}
      if (field.inputType === "number") {{
        return Number(element.value);
      }}
      return element.value;
    }}

    function setupForm(config) {{
      const form = document.getElementById(config.formId);
      const responsePanel = document.getElementById(config.responsePanelId);
      const responseContent = responsePanel.querySelector("pre");

      function renderResponse(kind, payload) {{
        responsePanel.className = `response-panel ${{kind}}`;
        responseContent.textContent = typeof payload === "string"
          ? payload
          : JSON.stringify(payload, null, 2);
      }}

      form.addEventListener("submit", async (event) => {{
        event.preventDefault();

        const body = {{}};
        for (const field of config.fieldDescriptors) {{
          const element = document.getElementById(field.id);
          const value = coerceValue(field, element);
          if (value === null) {{
            if (field.required) {{
              renderResponse("error", `Missing required field: ${{field.contractName}}`);
              return;
            }}
            continue;
          }}
          body[field.contractName] = value;
        }}

        try {{
          const response = await fetch(config.endpoint, {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json",
            }},
            body: JSON.stringify(body),
          }});

          let payload;
          try {{
            payload = await response.json();
          }} catch (error) {{
            payload = {{ message: "Response did not contain JSON.", detail: String(error) }};
          }}

          if (!response.ok) {{
            renderResponse("error", {{
              status: response.status,
              statusText: response.statusText,
              body: payload,
            }});
            return;
          }}

          renderResponse("success", payload);
        }} catch (error) {{
          renderResponse("error", {{
            status: "NETWORK_ERROR",
            message: error.message,
          }});
        }}
      }});
    }}

    forms.forEach(setupForm);
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Full operator dashboard renderer
# ---------------------------------------------------------------------------

def _render_operator_dashboard(
    *,
    metadata: MetadataProject,
    panels: list[dict],
    source_manifest: str,
    generation_run_id: str,
) -> str:
    """Render the upgraded operator dashboard HTML.

    # replaces the minimal single-form UI with a full
    # operator dashboard: entity sidebar/tabs, CRUD action panels, request
    # JSON preview, response panel (status + timing), and live data viewer.
    """
    header = render_generated_file_header(
        source_manifest=source_manifest,
        target_profile=metadata.target_profile,
        generation_run_id=generation_run_id,
        comment_style="xml",
    )

    # Build per-entity dashboard data
    # Group panels by entity
    entity_panels: dict[str, list[dict]] = {}
    for panel in panels:
        entity_panels.setdefault(panel["entity_name"], []).append(panel)

    # Also gather all entities for sidebar and live viewer (even those without panels)
    all_entity_names = [e.name for e in metadata.entities]
    # Merge in any from panels not in entities list
    for name in entity_panels:
        if name not in all_entity_names:
            all_entity_names.append(name)

    # Sidebar nav items
    # entity navigation for sidebar
    nav_items_html = "\n".join(
        f'        <button class="nav-item" data-entity="{html.escape(name)}" '
        f'type="button" aria-current="false" '
        f'onclick="showEntity(\'{html.escape(name)}\')">'
        f'{html.escape(name)}</button>'
        for name in all_entity_names
    )

    descriptors = _build_action_card_descriptors(metadata, panels)
    descriptors_by_key = {
        descriptor.coverageKey: descriptor for descriptor in descriptors
    }
    coverage_map_html = _render_coverage_map(descriptors)

    # Per-entity CRUD tab panels
    entity_tab_panels_html = "\n".join(
        _render_entity_dashboard_panel(
            entity_name=name,
            panels=entity_panels.get(name, []),
            metadata=metadata,
            descriptors_by_key=descriptors_by_key,
        )
        for name in all_entity_names
    )

    # Entity names for the live viewer JS
    entity_names_json = json.dumps(all_entity_names)
    descriptors_json = json.dumps(
        [descriptor.to_dict() for descriptor in descriptors],
        indent=2,
    )
    coverage_storage_key_json = json.dumps(
        f"edgeforge.testConsole.coverage.{metadata.bounded_context}"
    )

    datasource_label = _configured_datasource_label(metadata)

    return f"""{header}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(metadata.app_name)} — Initial Test Console</title>
  <!-- operator dashboard styles — navy/white/light-gray palette -->
  <style>
    :root {{
      --navy: #1a237e;
      --navy-deep: #10195c;
      --navy-light: #283593;
      --surface: #ffffff;
      --background: #f0f2f8;
      --sidebar-bg: #1e2a5e;
      --sidebar-text: #c5cae9;
      --sidebar-active: #3949ab;
      --border: #d0d6e8;
      --text: #1f2937;
      --muted: #6b7280;
      --success: #2e7d32;
      --success-bg: rgba(46,125,50,0.08);
      --warning: #b45309;
      --warning-bg: rgba(180,83,9,0.1);
      --error: #c62828;
      --error-bg: rgba(198,40,40,0.08);
      --fault: #6d28d9;
      --fault-bg: rgba(109,40,217,0.1);
      --shadow: 0 2px 12px rgba(15,23,42,0.08);
      --tab-active: #1a237e;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--background); color: var(--text); font-family: "Segoe UI", system-ui, sans-serif; line-height: 1.5; height: 100vh; display: flex; flex-direction: column; }}

    /* Top banner */
    .non-prod-banner {{ background: #fff7ed; border-bottom: 1px solid #fed7aa; color: #7c2d12; padding: 8px 24px; display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; font-size: 0.78rem; font-weight: 600; }}
    .non-prod-banner strong {{ letter-spacing: 0.04em; }}
    .non-prod-banner span {{ white-space: nowrap; }}
    .banner {{ background: linear-gradient(135deg, var(--navy), var(--navy-deep)); color: #fff; padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; box-shadow: 0 2px 8px rgba(0,0,0,0.2); }}
    .banner-left {{ display: flex; align-items: center; gap: 12px; }}
    .console-logo-slot {{ display: none; width: 36px; height: 36px; border-radius: 8px; background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.25); }}
    .banner-left h1 {{ font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }}
    .banner-left p {{ font-size: 0.8rem; opacity: 0.75; margin-top: 1px; }}
    .banner-meta {{ font-size: 0.75rem; opacity: 0.6; text-align: right; }}

    /* Layout: sidebar + main */
    .layout {{ display: flex; flex: 1; overflow: hidden; }}

    /* Sidebar */
    .sidebar {{ width: 200px; background: var(--sidebar-bg); display: flex; flex-direction: column; flex-shrink: 0; overflow-y: auto; }}
    .sidebar-label {{ font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #7986cb; padding: 16px 16px 8px; }}
    .nav-item {{ display: block; width: 100%; text-align: left; padding: 10px 16px; font-size: 0.88rem; color: var(--sidebar-text); background: transparent; border: none; cursor: pointer; border-left: 3px solid transparent; transition: all 0.15s; }}
    .nav-item:hover {{ background: rgba(255,255,255,0.06); color: #fff; }}
    .nav-item.active {{ background: rgba(57,73,171,0.4); color: #fff; border-left-color: #7986cb; font-weight: 600; }}
    .nav-item:focus-visible, .crud-tab:focus-visible, .btn:focus-visible {{ outline: 3px solid rgba(121,134,203,0.7); outline-offset: 2px; }}

    /* Main content */
    .main {{ flex: 1; overflow-y: auto; padding: 20px 24px 32px; }}
    .test-disclaimer {{ background: #fff; border: 1px solid var(--border); border-left: 4px solid var(--navy-light); border-radius: 8px; padding: 12px 16px; margin-bottom: 18px; color: var(--text); font-size: 0.86rem; box-shadow: var(--shadow); }}
    .test-disclaimer strong {{ color: var(--navy); }}
    .coverage-map {{ background: #fff; border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow); margin-bottom: 18px; padding: 16px; }}
    .coverage-map-header {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 12px; }}
    .coverage-map h2 {{ color: var(--navy); font-size: 1rem; margin-bottom: 4px; }}
    .coverage-map p {{ color: var(--muted); font-size: 0.82rem; }}
    .coverage-map-count {{ border: 1px solid var(--border); border-radius: 999px; color: var(--muted); font-size: 0.72rem; font-weight: 700; padding: 3px 10px; white-space: nowrap; }}
    .coverage-map-grid {{ display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
    .coverage-entry {{ display: grid; gap: 3px; width: 100%; text-align: left; background: #f8faff; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; cursor: pointer; transition: border-color 0.15s, box-shadow 0.15s; }}
    .coverage-entry:hover {{ border-color: var(--navy-light); box-shadow: 0 2px 8px rgba(26,35,126,0.08); }}
    .coverage-entry:focus-visible {{ outline: 3px solid rgba(121,134,203,0.7); outline-offset: 2px; }}
    .coverage-title {{ color: var(--text); font-size: 0.84rem; font-weight: 700; }}
    .coverage-meta {{ color: var(--muted); font-size: 0.72rem; }}
    .coverage-chip {{ justify-self: start; margin-top: 3px; }}
    .coverage-chip.not-tried {{ background: #e5e7eb; color: #374151; }}
    .provenance-panel {{ border: 1px dashed var(--border); border-radius: 8px; background: #f8faff; margin: -4px 0 12px; padding: 0; }}
    .provenance-panel > summary {{ cursor: pointer; color: var(--navy); font-size: 0.76rem; font-weight: 700; padding: 8px 10px; }}
    .provenance-panel > summary:focus-visible {{ outline: 3px solid rgba(121,134,203,0.7); outline-offset: 2px; }}
    .provenance-body {{ border-top: 1px solid var(--border); color: var(--muted); display: grid; gap: 6px; font-size: 0.76rem; padding: 9px 10px 10px; }}
    .provenance-body p {{ color: var(--text); margin: 0; }}
    .provenance-line {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .provenance-line strong {{ color: var(--navy); }}

    /* Descriptor group sections */
    .group-section {{ background: #fff; border: 1px solid var(--border); border-radius: 10px; box-shadow: var(--shadow); margin-bottom: 16px; overflow: hidden; }}
    .group-section > summary {{ cursor: pointer; display: flex; align-items: center; gap: 10px; padding: 13px 16px; color: var(--navy); font-weight: 700; list-style: none; }}
    .group-section > summary::-webkit-details-marker {{ display: none; }}
    .group-section[open] > summary {{ border-bottom: 1px solid var(--border); background: #f8faff; }}
    .group-section > summary:focus-visible {{ outline: 3px solid rgba(121,134,203,0.7); outline-offset: -3px; }}
    .group-icon {{ width: 24px; height: 24px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center; background: rgba(26,35,126,0.08); color: var(--navy); font-size: 0.9rem; }}
    .group-title {{ font-size: 0.94rem; }}
    .group-count {{ margin-left: auto; color: var(--muted); font-size: 0.78rem; font-weight: 700; }}
    .group-section-body {{ padding: 16px; display: grid; gap: 12px; }}
    .group-note {{ color: var(--muted); font-size: 0.84rem; margin: 0; }}

    /* EOD / batch test actions */
    .batch-section {{ background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 18px; box-shadow: var(--shadow); margin-bottom: 20px; }}
    .batch-section h2 {{ font-size: 1rem; color: var(--navy); margin-bottom: 6px; }}
    .batch-section p {{ color: var(--muted); font-size: 0.84rem; margin-bottom: 12px; }}
    .batch-actions {{ display: grid; gap: 10px; }}
    .batch-action {{ border: 1px solid var(--border); border-radius: 8px; padding: 12px; background: #f8faff; }}
    .batch-action strong {{ color: var(--navy); }}
    .batch-action code {{ color: var(--navy); font-size: 0.78rem; }}
    .batch-output-hint {{ color: var(--muted); font-size: 0.78rem; margin-top: 4px; }}

    /* Entity panel */
    .entity-panel {{ display: none; }}
    .entity-panel.active {{ display: block; }}
    .entity-panel > h2 {{ font-size: 1.1rem; color: var(--navy); margin-bottom: 16px; font-weight: 700; }}

    /* CRUD tabs */
    .crud-tabs {{ display: flex; gap: 4px; margin-bottom: 0; flex-wrap: wrap; }}
    .crud-tab {{ padding: 7px 16px; font-size: 0.82rem; font-weight: 600; border: 1px solid var(--border); background: #fff; color: var(--muted); cursor: pointer; border-radius: 8px 8px 0 0; border-bottom: none; transition: all 0.15s; }}
    .crud-tab:hover {{ background: #f0f4ff; color: var(--navy); }}
    .crud-tab.active {{ background: var(--navy); color: #fff; border-color: var(--navy); }}

    /* CRUD panel */
    .crud-panel {{ display: none; background: #fff; border: 1px solid var(--border); border-radius: 0 8px 8px 8px; padding: 20px; box-shadow: var(--shadow); margin-bottom: 20px; }}
    .crud-panel.active {{ display: block; }}
    .crud-panel h3 {{ font-size: 0.9rem; color: var(--navy); margin-bottom: 14px; font-weight: 600; }}

    /* Forms */
    .form-grid {{ display: grid; gap: 14px; }}
    .field {{ display: grid; gap: 5px; }}
    .field label {{ font-size: 0.82rem; font-weight: 600; color: var(--text); }}
    .field label .opt {{ color: var(--muted); font-weight: 400; margin-left: 4px; font-size: 0.78rem; }}
    .field .hint {{ font-size: 0.76rem; color: var(--muted); }}
    .field .rule-summary {{ color: var(--navy); }}
    input, select, textarea {{ width: 100%; border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; font: inherit; font-size: 0.88rem; background: #fff; color: var(--text); }}
    input:focus, select:focus, textarea:focus {{ outline: 2px solid rgba(26,35,126,0.18); border-color: var(--navy); }}
    .checkbox-row {{ display: flex; align-items: center; gap: 8px; }}
    .checkbox-row input {{ width: auto; }}
    .btn {{ border: none; border-radius: 8px; background: var(--navy); color: #fff; padding: 9px 18px; font: inherit; font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: background 0.15s; margin-top: 6px; }}
    .btn:hover {{ background: var(--navy-deep); }}
    .btn:disabled {{ cursor: progress; opacity: 0.75; }}
    .btn-secondary {{ background: #fff; color: var(--navy); border: 1px solid var(--border); }}
    .btn-secondary:hover {{ background: #f0f4ff; }}
    .btn-danger {{ background: #c62828; }}
    .btn-danger:hover {{ background: #b71c1c; }}

    /* Request preview panel */
    .request-preview {{ margin-top: 14px; padding: 12px 14px; background: #f8faff; border: 1px solid var(--border); border-radius: 8px; }}
    .request-preview .label {{ font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }}
    pre.json {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.82rem; white-space: pre-wrap; word-break: break-word; color: #1a237e; margin: 0; }}

    /* Response panel */
    .response-panel {{ display: none; margin-top: 14px; border-radius: 8px; padding: 14px; border: 1px solid var(--border); background: #f8fafc; }}
    .response-panel.pending {{ display: block; border-color: var(--border); background: #f8faff; }}
    .response-panel.success {{ display: block; border-color: #4caf50; background: var(--success-bg); }}
    .response-panel.warning {{ display: block; border-color: var(--warning); background: var(--warning-bg); }}
    .response-panel.error {{ display: block; border-color: #f44336; background: var(--error-bg); }}
    .response-panel.fault {{ display: block; border-color: var(--fault); background: var(--fault-bg); }}
    .resp-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
    .status-badge {{ font-size: 0.75rem; font-weight: 700; padding: 2px 10px; border-radius: 999px; }}
    .status-badge.ok {{ background: #4caf50; color: #fff; }}
    .status-badge.warn {{ background: var(--warning); color: #fff; }}
    .status-badge.err {{ background: #f44336; color: #fff; }}
    .status-badge.fault {{ background: var(--fault); color: #fff; }}
    .timing {{ font-size: 0.75rem; color: var(--muted); }}
    .spinner {{ display: inline-block; width: 0.9em; height: 0.9em; border: 2px solid rgba(26,35,126,0.25); border-top-color: var(--navy); border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: -0.12em; margin-right: 6px; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .json-key {{ color: #7c3aed; }}
    .json-string {{ color: #166534; }}
    .json-number {{ color: #b45309; }}
    .json-literal {{ color: #0369a1; }}
    .json-empty {{ color: var(--muted); font-style: italic; }}

    /* Live data viewer */
    .live-section {{ background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 18px; box-shadow: var(--shadow); margin-bottom: 20px; }}
    .live-section h3 {{ font-size: 0.88rem; font-weight: 700; color: var(--navy); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }}
    .live-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #4caf50; animation: pulse 2s infinite; }}
    @keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.4; }} }}
    .live-empty {{ color: var(--muted); font-size: 0.85rem; padding: 16px 0; text-align: center; }}
    .live-disabled {{ color: var(--muted); font-size: 0.85rem; padding: 16px 0; font-style: italic; }}
    table.data-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
    table.data-table th {{ background: #f0f2f8; color: var(--muted); font-weight: 700; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; padding: 7px 10px; text-align: left; border-bottom: 1px solid var(--border); }}
    table.data-table td {{ padding: 6px 10px; border-bottom: 1px solid #f0f2f8; color: var(--text); font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.78rem; word-break: break-all; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    table.data-table tr:hover td {{ background: #f8faff; }}

    footer {{ color: var(--muted); text-align: center; font-size: 0.78rem; padding: 10px 0 4px; border-top: 1px solid var(--border); background: #fff; flex-shrink: 0; }}

    @media (max-width: 640px) {{
      .layout {{ flex-direction: column; }}
      .sidebar {{ width: 100%; flex-direction: row; overflow-x: auto; padding: 8px 4px; }}
      .sidebar-label {{ display: none; }}
      .nav-item {{ white-space: nowrap; border-left: none; border-bottom: 3px solid transparent; }}
      .nav-item.active {{ border-bottom-color: #7986cb; border-left: none; }}
    }}
  </style>
</head>
<body>
  <div class="non-prod-banner" role="status" aria-live="polite">
    <strong>NON-PRODUCTION TEST CONSOLE &middot; local only</strong>
    <span>profile: {html.escape(metadata.target_profile)}</span>
    <span>datasource (configured default): {html.escape(datasource_label)}</span>
    <span id="demo-state-indicator">demo data: checking</span>
  </div>
  <!-- top banner with app name, bounded context, metadata -->
  <div class="banner">
    <div class="banner-left">
      <div class="console-logo-slot" data-logo-slot="reserved" aria-hidden="true"></div>
      <div>
        <h1>{html.escape(metadata.app_name)} Initial Test Console</h1>
        <p>{html.escape(metadata.bounded_context)} bounded context &middot; Generated App Test Console</p>
      </div>
    </div>
    <div class="banner-meta">
      Generated by EdgeForge<br/>Profile: {html.escape(metadata.target_profile)}<br/>Run: {html.escape(generation_run_id)}
    </div>
  </div>

  <div class="layout">
    <!-- entity sidebar navigation -->
    <nav class="sidebar">
      <div class="sidebar-label">Entities</div>
{nav_items_html}
    </nav>

    <main class="main">
      <div class="test-disclaimer">
        <strong>Initial Test UI.</strong>
        This generated UI is intended for local validation of generated APIs, data, and batch outputs. It is not a production application UI.
      </div>
{coverage_map_html}
      <!-- per-entity dashboard panels with CRUD tabs -->
{entity_tab_panels_html}

      <footer>
        Generated by EdgeForge &mdash; Profile: {html.escape(metadata.target_profile)} &mdash; Run: {html.escape(generation_run_id)}
      </footer>
    </main>
  </div>

  <!-- dashboard JavaScript — CRUD forms, request preview, response panel, live viewer -->
  <script>
    // Entity names known at generation time
    const ENTITY_NAMES = {entity_names_json};

    // Action-card descriptors are the dashboard source of truth.
    // Slice 1 keeps them inline; a later slice can swap this for descriptors.json.
    const DESCRIPTORS = {descriptors_json};
    const DESCRIPTOR_BY_KEY = Object.fromEntries(DESCRIPTORS.map(descriptor => [descriptor.coverageKey, descriptor]));
    const COVERAGE_STORAGE_KEY = {coverage_storage_key_json};

    // ---- Navigation ----
    function showEntity(entityName) {{
      document.querySelectorAll('.entity-panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.nav-item').forEach(n => {{
        n.classList.remove('active');
        n.setAttribute('aria-current', 'false');
      }});
      const panel = document.getElementById('entity-panel-' + entityName);
      if (panel) panel.classList.add('active');
      const navBtn = document.querySelector('.nav-item[data-entity="' + entityName + '"]');
      if (navBtn) {{
        navBtn.classList.add('active');
        navBtn.setAttribute('aria-current', 'page');
      }}
      const activeTab = panel ? panel.querySelector('.crud-tab.active') : null;
      if (activeTab) showCrudTab(entityName, activeTab.dataset.tab);
      // Reset live viewer for this entity
      loadLiveData(entityName);
    }}

    // ---- CRUD tab switching ----
    function showCrudTab(entityName, tabName) {{
      const panelEl = document.getElementById('entity-panel-' + entityName);
      if (!panelEl) return;
      panelEl.querySelectorAll('.crud-tab').forEach(t => {{
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      }});
      panelEl.querySelectorAll('.crud-panel').forEach(p => p.classList.remove('active'));
      const tab = panelEl.querySelector('.crud-tab[data-tab="' + tabName + '"]');
      if (tab) {{
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
      }}
      const panel = document.getElementById('crud-' + entityName + '-' + tabName);
      if (panel) panel.classList.add('active');
      updateRequestPreview(entityName, tabName);
    }}

    // ---- Descriptor-driven request preview ----
    function descriptorKey(entityName, tabName) {{
      return entityName + '-' + tabName;
    }}

    function actionResponsePanelId(descriptor) {{
      return 'resp-panel-' + safeDomId(descriptor.coverageKey);
    }}

    function safeDomId(value) {{
      return String(value || '').replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'action';
    }}

    function descriptorEntityName(descriptor) {{
      const firstToken = String(descriptor.coverageKey || '').split('-')[0];
      return ENTITY_NAMES.includes(firstToken) ? firstToken : null;
    }}

    function updateRequestPreview(entityName, tabName) {{
      const descriptor = DESCRIPTOR_BY_KEY[descriptorKey(entityName, tabName)];
      const previewEl = document.getElementById('req-preview-' + entityName);
      if (!previewEl) return;
      if (!descriptor || !descriptor.actions || descriptor.actions.length === 0) {{
        previewEl.textContent = '';
        return;
      }}
      const action = descriptor.actions[0];
      const inputState = collectActionInputs(descriptor, action, true);
      const request = buildActionRequest(descriptor, action, inputState, true);
      const bodyPreview = request.bodyPreview === null
        ? ''
        : '\\n' + (typeof request.bodyPreview === 'string' ? request.bodyPreview : JSON.stringify(request.bodyPreview, null, 2));
      previewEl.textContent = action.verb + ' ' + request.endpoint + bodyPreview;
    }}

    // ---- Response render ----
    function responseTimestamp() {{
      return new Date().toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit', second: '2-digit' }});
    }}

    function statusBadgeClass(kind, numericStatus) {{
      if (kind === 'fault') return 'fault'; // Reserved for SOAP Fault cards in a later slice.
      if (numericStatus >= 500) return 'err';
      if (numericStatus >= 400) return 'warn';
      if (numericStatus >= 200 && numericStatus < 400) return 'ok';
      return kind === 'success' ? 'ok' : 'err';
    }}

    function responsePanelClass(kind, numericStatus) {{
      const badgeClass = statusBadgeClass(kind, numericStatus);
      if (badgeClass === 'ok') return 'success';
      if (badgeClass === 'warn') return 'warning';
      if (badgeClass === 'fault') return 'fault';
      return 'error';
    }}

    function renderBatchResponse(kind, status, rawBody, ms, responsePanelId, numericStatus, responseShape) {{
      const respEl = document.getElementById(responsePanelId || 'batch-response');
      if (!respEl) return;
      const badgeCls = statusBadgeClass(kind, numericStatus || 0);
      respEl.className = 'response-panel ' + responsePanelClass(kind, numericStatus || 0);
      respEl.innerHTML =
        '<div class="resp-header">' +
        '<span class="status-badge ' + badgeCls + '">' + status + '</span>' +
        '<span class="timing">' + ms + 'ms &middot; ' + responseTimestamp() + '</span>' +
        '</div>' +
        '<pre class="json">' + formatResponseBody(String(rawBody ?? ''), responseShape || 'JSON') + '</pre>';
    }}

    function renderInFlightResponse(responsePanelId) {{
      const respEl = document.getElementById(responsePanelId || 'batch-response');
      if (!respEl) return;
      respEl.className = 'response-panel pending';
      respEl.innerHTML =
        '<div class="resp-header">' +
        '<span class="spinner" aria-hidden="true"></span>' +
        '<span class="timing">Sending&hellip;</span>' +
        '</div>';
    }}

    function formatResponseBody(rawText, responseShape) {{
      if (rawText === '') return '<span class="json-empty">(empty response body)</span>';
      if ((responseShape || 'JSON') === 'JSON') return formatJsonLossless(rawText);
      return escapeHtml(rawText);
    }}

    function formatJsonLossless(rawText) {{
      const trimmed = rawText.trim();
      if (!(trimmed.startsWith('{{') || trimmed.startsWith('['))) return escapeHtml(rawText);
      try {{ JSON.parse(rawText); }} catch(e) {{ return escapeHtml(rawText); }}
      return colorizeJson(prettyJsonLossless(rawText));
    }}

    function prettyJsonLossless(rawText) {{
      let output = '';
      let indent = 0;
      let inString = false;
      let escaped = false;
      const unit = '  ';
      for (const ch of rawText.trim()) {{
        if (inString) {{
          output += ch;
          if (escaped) {{
            escaped = false;
          }} else if (ch === '\\\\') {{
            escaped = true;
          }} else if (ch === '"') {{
            inString = false;
          }}
          continue;
        }}
        if (ch === '"') {{
          inString = true;
          output += ch;
        }} else if (ch === '{{' || ch === '[') {{
          indent += 1;
          output += ch + '\\n' + unit.repeat(indent);
        }} else if (ch === '}}' || ch === ']') {{
          indent = Math.max(0, indent - 1);
          output = output.trimEnd() + '\\n' + unit.repeat(indent) + ch;
        }} else if (ch === ',') {{
          output += ch + '\\n' + unit.repeat(indent);
        }} else if (ch === ':') {{
          output += ': ';
        }} else if (!/\\s/.test(ch)) {{
          output += ch;
        }}
      }}
      return output;
    }}

    function colorizeJson(formatted) {{
      return formatted.replace(/("(?:\\\\.|[^"\\\\])*")(\\s*:)?|-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?|\\b(?:true|false|null)\\b/g, (match, stringToken, keySuffix) => {{
        if (stringToken && keySuffix) {{
          return '<span class="json-key">' + escapeHtml(stringToken) + '</span>' + keySuffix;
        }}
        if (stringToken) return '<span class="json-string">' + escapeHtml(match) + '</span>';
        if (/^-?\\d/.test(match)) return '<span class="json-number">' + escapeHtml(match) + '</span>';
        return '<span class="json-literal">' + escapeHtml(match) + '</span>';
      }});
    }}

    function escapeHtml(s) {{
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }}

    // ---- Contract coverage map ----
    function loadCoverageState() {{
      try {{
        const raw = localStorage.getItem(COVERAGE_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) : {{}};
        return parsed && typeof parsed === 'object' ? parsed : {{}};
      }} catch(e) {{
        return {{}};
      }}
    }}

    function saveCoverageState(state) {{
      try {{
        localStorage.setItem(COVERAGE_STORAGE_KEY, JSON.stringify(state));
      }} catch(e) {{
        // Coverage is a browser-only visual aid; storage failures must not block actions.
      }}
    }}

    function coverageRecordClass(record) {{
      if (!record || !record.exercised) return 'not-tried';
      const numericStatus = Number(record.numericStatus || 0);
      const kind = numericStatus >= 200 && numericStatus < 400 ? 'success' : 'error';
      return statusBadgeClass(kind, numericStatus);
    }}

    function coverageRecordLabel(record) {{
      if (!record || !record.exercised) return 'not yet tried';
      return record.status || 'exercised';
    }}

    function applyCoverageRecord(coverageKey, record) {{
      const chip = document.getElementById('coverage-chip-' + safeDomId(coverageKey));
      if (!chip) return;
      const cls = coverageRecordClass(record);
      chip.className = 'status-badge coverage-chip ' + cls;
      chip.dataset.coverageStatus = cls === 'not-tried' ? 'not-tried' : 'exercised';
      chip.textContent = coverageRecordLabel(record);
    }}

    function refreshCoverageMap() {{
      const state = loadCoverageState();
      DESCRIPTORS.forEach(descriptor => {{
        applyCoverageRecord(descriptor.coverageKey, state[descriptor.coverageKey]);
      }});
    }}

    function recordCoverageResult(coverageKey, numericStatus, statusText) {{
      if (!coverageKey) return;
      const state = loadCoverageState();
      state[coverageKey] = {{
        exercised: true,
        numericStatus: Number(numericStatus || 0),
        status: statusText || String(numericStatus || 'exercised')
      }};
      saveCoverageState(state);
      applyCoverageRecord(coverageKey, state[coverageKey]);
    }}

    function focusCoverageCard(coverageKey) {{
      const cards = Array.from(document.querySelectorAll('[data-coverage-key]'));
      const card = cards.find(el => el.dataset.coverageKey === coverageKey);
      if (!card) return;
      let ownerEntityName = null;
      const ownerPanel = card.closest('.entity-panel');
      if (ownerPanel && ownerPanel.id && ownerPanel.id.startsWith('entity-panel-')) {{
        ownerEntityName = ownerPanel.id.slice('entity-panel-'.length);
        showEntity(ownerEntityName);
      }}
      const crudPanel = card.closest('.crud-panel');
      const crudPrefix = ownerEntityName ? 'crud-' + ownerEntityName + '-' : null;
      if (ownerEntityName && crudPanel && crudPanel.id && crudPanel.id.startsWith(crudPrefix)) {{
        showCrudTab(ownerEntityName, crudPanel.id.slice(crudPrefix.length));
      }}
      const groupSection = card.closest('details.group-section');
      if (groupSection) groupSection.open = true;
      card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      const button = card.querySelector('[data-action-button]');
      if (button) button.focus({{ preventScroll: true }});
    }}

    // ---- Value coercion ----
    function coerceValue(fd, el) {{
      if (fd.inputType === 'checkbox') return el.checked;
      if (el.value === '') return null;
      if (fd.inputType === 'number') return Number(el.value);
      return el.value;
    }}

    function isFillableSampleHint(fd) {{
      if (!fd || fd.outputHint || fd.bodyField) return false;
      return ['checkbox', 'date', 'datetime-local', 'number', 'select', 'text'].includes(fd.inputType);
    }}

    function sampleValueForHint(fd) {{
      if (fd.allowedValues && fd.allowedValues.length > 0) {{
        return fd.required ? String(fd.allowedValues[0]) : '';
      }}
      if (fd.inputType === 'checkbox') return false;
      if (fd.inputType === 'date') return '2000-01-01';
      if (fd.inputType === 'datetime-local') return '2000-01-01T00:00';
      if (fd.inputType === 'number') return fd.step ? '0.00' : '0';
      return '';
    }}

    function refreshDescriptorPreview(descriptor) {{
      const entityName = descriptorEntityName(descriptor);
      if (!entityName) return;
      const tabName = descriptor.coverageKey.slice(entityName.length + 1);
      updateRequestPreview(entityName, tabName);
    }}

    function fillSample(coverageKey) {{
      const descriptor = DESCRIPTOR_BY_KEY[coverageKey];
      if (!descriptor) return;
      for (const fd of descriptor.hints || []) {{
        if (!isFillableSampleHint(fd)) continue;
        const el = document.getElementById(fd.id);
        if (!el) continue;
        const sampleValue = sampleValueForHint(fd);
        if (fd.inputType === 'checkbox') {{
          el.checked = Boolean(sampleValue);
        }} else {{
          el.value = sampleValue;
        }}
      }}
      refreshDescriptorPreview(descriptor);
    }}

    function collectActionInputs(descriptor, action, previewMode) {{
      const values = {{
        contractName: descriptor.provenance ? descriptor.provenance.contractName : null,
        jobName: descriptor.provenance ? descriptor.provenance.contractName : null
      }};
      const query = new URLSearchParams();
      const transportHeaders = Object.create(null);
      const bodyFields = {{}};
      const errors = [];
      let bodyValue = null;
      let rawBody = null;
      const endpointPlaceholderNames = new Set(endpointPlaceholders(action.endpoint));
      for (const fd of descriptor.hints || []) {{
        if (fd.outputHint) continue;
        const el = document.getElementById(fd.id);
        let value = null;
        if (fd.bodyField) {{
          const raw = el ? el.value.trim() : '';
          if (!raw) {{
            if (fd.required) {{
              if (previewMode) bodyValue = {{"...fields": "...values"}};
              else errors.push(fd.contractName + ' is required');
            }}
            continue;
          }}
          try {{
            bodyValue = JSON.parse(raw);
          }} catch(e) {{
            if (previewMode) bodyValue = raw;
            else errors.push('Invalid JSON: ' + e.message);
          }}
          continue;
        }}
        if (action.inputControl === 'TEXTAREA') {{
          value = el ? el.value : '';
          rawBody = value;
        }} else {{
          value = el ? (fd.writeTransport && el.type !== 'checkbox' ? el.value : coerceValue(fd, el)) : null;
        }}
        if (value === null || value === '') {{
          if (fd.required) {{
            if (previewMode) value = '<required>';
            else errors.push((fd.contractName || fd.label || 'value') + ' is required');
          }} else {{
            continue;
          }}
        }}
        if (fd.header) {{
          transportHeaders[fd.contractName] = value;
          continue;
        }}
        if (fd.query) {{
          query.append(fd.contractName, value);
          continue;
        }}
        values[fd.contractName] = value;
        values[fd.canonicalName] = value;
        const isEndpointPlaceholder =
          endpointPlaceholderNames.has(fd.contractName) || endpointPlaceholderNames.has(fd.canonicalName);
        if (action.inputBinding === 'JSON_BODY' && !isEndpointPlaceholder) {{
          bodyFields[fd.contractName] = value;
        }} else if (action.inputControl === 'FORM' && !isEndpointPlaceholder) {{
          bodyFields[fd.contractName] = value;
        }}
      }}
      for (const placeholder of endpointPlaceholders(action.endpoint)) {{
        if (values[placeholder] === undefined || values[placeholder] === null || values[placeholder] === '') {{
          if (previewMode) values[placeholder] = '<required>';
          else errors.push(placeholder + ' is required');
        }}
      }}
      return {{ values, queryString: query.toString(), transportHeaders, bodyFields, bodyValue, rawBody, errors }};
    }}

    function endpointPlaceholders(endpoint) {{
      const matches = [];
      endpoint.replace(/\\{{([^{{}}]+)\\}}/g, (_match, name) => {{
        matches.push(name);
        return _match;
      }});
      return matches;
    }}

    function resolveEndpointTemplate(endpoint, values) {{
      return endpoint.replace(/\\{{([^{{}}]+)\\}}/g, (_match, name) => encodeURIComponent(values[name] ?? ''));
    }}

    function buildActionRequest(descriptor, action, inputState, previewMode) {{
      let endpoint = resolveEndpointTemplate(action.endpoint, inputState.values);
      if (inputState.queryString) {{
        endpoint += (endpoint.includes('?') ? '&' : '?') + inputState.queryString;
      }}
      const headers = Object.assign(Object.create(null), action.headers || {{}}, inputState.transportHeaders || {{}});
      let body = null;
      if (action.inputBinding === 'JSON_BODY') {{
        body = inputState.bodyValue !== null ? inputState.bodyValue : inputState.bodyFields;
        if (!headers['Content-Type']) headers['Content-Type'] = 'application/json';
      }} else if (action.inputBinding === 'RAW_BODY') {{
        body = inputState.rawBody || '';
      }} else if (action.inputBinding === 'QUERY' && inputState.queryString) {{
        body = null;
      }}
      const fetchOptions = {{ method: action.verb, headers }};
      if (body !== null && action.inputBinding === 'JSON_BODY') fetchOptions.body = JSON.stringify(body);
      else if (body !== null && action.inputBinding === 'RAW_BODY') fetchOptions.body = body;
      if (!previewMode && Object.keys(headers).length === 0) delete fetchOptions.headers;
      return {{ endpoint, fetchOptions, bodyPreview: body }};
    }}

    function actionButtonId(coverageKey, actionIndex) {{
      return 'action-btn-' + safeDomId(coverageKey) + '-' + (actionIndex || 0);
    }}

    function setActionInFlight(coverageKey, actionIndex, inFlight) {{
      const button = document.getElementById(actionButtonId(coverageKey, actionIndex));
      if (!button) return;
      if (inFlight) {{
        if (!button.dataset.originalLabel) button.dataset.originalLabel = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="spinner" aria-hidden="true"></span> Sending&hellip;';
      }} else {{
        button.disabled = false;
        if (button.dataset.originalLabel) button.innerHTML = button.dataset.originalLabel;
      }}
    }}

    async function submitAction(coverageKey, actionIndex, responsePanelId) {{
      const descriptor = DESCRIPTOR_BY_KEY[coverageKey];
      if (!descriptor) return;
      const resolvedActionIndex = actionIndex || 0;
      const action = descriptor.actions[resolvedActionIndex];
      if (!action) return;
      const inputState = collectActionInputs(descriptor, action, false);
      if (inputState.errors.length > 0) {{
        renderActionResponse(descriptor, 'error', '400', JSON.stringify({{errors: inputState.errors}}, null, 2), 0, responsePanelId, 400);
        recordCoverageResult(coverageKey, 400, '400');
        return;
      }}
      const request = buildActionRequest(descriptor, action, inputState, false);
      const t0 = Date.now();
      setActionInFlight(coverageKey, resolvedActionIndex, true);
      renderInFlightResponse(responsePanelId || actionResponsePanelId(descriptor));
      try {{
        const resp = await fetch(request.endpoint, request.fetchOptions);
        const ms = Date.now() - t0;
        const rawText = await resp.text();
        let payload = null;
        try {{ payload = rawText ? JSON.parse(rawText) : null; }} catch(e) {{ payload = null; }}
        const kind = resp.ok ? 'success' : 'error';
        renderActionResponse(descriptor, kind, resp.status + ' ' + resp.statusText, rawText, ms, responsePanelId, resp.status);
        recordCoverageResult(coverageKey, resp.status, resp.status + ' ' + resp.statusText);
        if (resp.ok) {{
          if (payload && payload.entity) loadLiveData(payload.entity);
          const entityName = descriptorEntityName(descriptor);
          if (entityName) loadLiveData(entityName);
        }}
      }} catch(e) {{
        renderActionResponse(descriptor, 'error', 'NETWORK_ERROR', JSON.stringify({{message: e.message}}, null, 2), Date.now()-t0, responsePanelId, 0);
        recordCoverageResult(coverageKey, 0, 'NETWORK_ERROR');
      }} finally {{
        setActionInFlight(coverageKey, resolvedActionIndex, false);
      }}
    }}

    function renderActionResponse(descriptor, kind, status, rawBody, ms, responsePanelId, numericStatus) {{
      renderBatchResponse(kind, status, rawBody, ms, responsePanelId || actionResponsePanelId(descriptor), numericStatus, descriptor.responseShape);
    }}

    function setDemoState(message) {{
      const indicator = document.getElementById('demo-state-indicator');
      if (indicator) indicator.textContent = message;
    }}

    function topLevelObjectTexts(rawText) {{
      const objects = [];
      let depth = 0;
      let start = -1;
      let inString = false;
      let escaped = false;
      for (let i = 0; i < rawText.length; i++) {{
        const ch = rawText[i];
        if (inString) {{
          if (escaped) {{
            escaped = false;
          }} else if (ch === '\\\\') {{
            escaped = true;
          }} else if (ch === '"') {{
            inString = false;
          }}
          continue;
        }}
        if (ch === '"') {{
          inString = true;
        }} else if (ch === '{{') {{
          if (depth === 0) start = i;
          depth += 1;
        }} else if (ch === '}}') {{
          depth = Math.max(0, depth - 1);
          if (depth === 0 && start >= 0) {{
            objects.push(rawText.slice(start, i + 1));
            start = -1;
          }}
        }}
      }}
      return objects;
    }}

    function readJsonStringEnd(text, start) {{
      let escaped = false;
      for (let i = start + 1; i < text.length; i++) {{
        const ch = text[i];
        if (escaped) {{
          escaped = false;
        }} else if (ch === '\\\\') {{
          escaped = true;
        }} else if (ch === '"') {{
          return i;
        }}
      }}
      return -1;
    }}

    function skipCompositeJsonValue(text, start) {{
      let objectDepth = 0;
      let arrayDepth = 0;
      let inString = false;
      let escaped = false;
      for (let i = start; i < text.length; i++) {{
        const ch = text[i];
        if (inString) {{
          if (escaped) {{
            escaped = false;
          }} else if (ch === '\\\\') {{
            escaped = true;
          }} else if (ch === '"') {{
            inString = false;
          }}
          continue;
        }}
        if (ch === '"') {{
          inString = true;
        }} else if (ch === '{{') {{
          objectDepth += 1;
        }} else if (ch === '}}') {{
          objectDepth = Math.max(0, objectDepth - 1);
        }} else if (ch === '[') {{
          arrayDepth += 1;
        }} else if (ch === ']') {{
          arrayDepth = Math.max(0, arrayDepth - 1);
        }}
        if (i > start && objectDepth === 0 && arrayDepth === 0) return i + 1;
      }}
      return text.length;
    }}

    function extractTopLevelScalarTokens(objectText) {{
      const row = {{}};
      let i = 1;
      while (i < objectText.length - 1) {{
        while (/[\\s,]/.test(objectText[i] || '')) i += 1;
        if (objectText[i] !== '"') {{
          i += 1;
          continue;
        }}
        const keyEnd = readJsonStringEnd(objectText, i);
        if (keyEnd < 0) break;
        const keyToken = objectText.slice(i, keyEnd + 1);
        let key = keyToken;
        try {{ key = JSON.parse(keyToken); }} catch(e) {{}}
        i = keyEnd + 1;
        while (/\\s/.test(objectText[i] || '')) i += 1;
        if (objectText[i] !== ':') continue;
        i += 1;
        while (/\\s/.test(objectText[i] || '')) i += 1;
        if (objectText[i] === '"') {{
          const valueEnd = readJsonStringEnd(objectText, i);
          if (valueEnd < 0) break;
          row[key] = objectText.slice(i, valueEnd + 1);
          i = valueEnd + 1;
        }} else if (objectText[i] === '{{' || objectText[i] === '[') {{
          i = skipCompositeJsonValue(objectText, i);
        }} else {{
          const scalarMatch = objectText.slice(i).match(/^-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?|^true|^false|^null/);
          if (scalarMatch) {{
            row[key] = scalarMatch[0];
            i += scalarMatch[0].length;
          }} else {{
            i += 1;
          }}
        }}
      }}
      return row;
    }}

    function rawRowsMatchParsedRows(rawRows, parsedRows) {{
      if (!Array.isArray(parsedRows) || rawRows.length !== parsedRows.length) return false;
      for (let i = 0; i < parsedRows.length; i++) {{
        const parsedRow = parsedRows[i];
        if (parsedRow === null || typeof parsedRow !== 'object' || Array.isArray(parsedRow)) return false;
        const parsedKeys = Object.keys(parsedRow).sort();
        const rawKeys = Object.keys(rawRows[i]).sort();
        if (parsedKeys.length !== rawKeys.length) return false;
        for (let k = 0; k < parsedKeys.length; k++) {{
          if (parsedKeys[k] !== rawKeys[k]) return false;
        }}
      }}
      return true;
    }}

    function extractRawScalarRows(rawText, parsedRows) {{
      const rawRows = topLevelObjectTexts(rawText).map(extractTopLevelScalarTokens);
      return rawRowsMatchParsedRows(rawRows, parsedRows) ? rawRows : [];
    }}

    function rawCellDisplay(rawToken, fallbackValue) {{
      if (rawToken === undefined) return String(fallbackValue ?? '');
      if (rawToken.startsWith('"')) {{
        try {{ return JSON.parse(rawToken); }} catch(e) {{ return rawToken; }}
      }}
      return rawToken;
    }}

    // ---- Live data viewer — polls /api/demo/entities/{{name}} every 5s ----
    const liveTimers = {{}};

    async function loadLiveData(entityName) {{
      const tableContainer = document.getElementById('live-table-' + entityName);
      if (!tableContainer) return;
      try {{
        const resp = await fetch('/api/demo/entities/' + encodeURIComponent(entityName));
        if (resp.status === 403) {{
          setDemoState('demo data: disabled');
          tableContainer.innerHTML = '<div class="live-disabled">Demo data viewer not available &mdash; set <code>appbuilder.demo.enabled=true</code> to enable.</div>';
          // stop polling after first 403 — demo is disabled, no point retrying
          if (liveTimers[entityName]) {{ clearInterval(liveTimers[entityName]); liveTimers[entityName] = null; }}
          return;
        }}
        if (!resp.ok) {{
          setDemoState('demo data: unavailable');
          tableContainer.innerHTML = '<div class="live-empty">Could not load data (HTTP ' + resp.status + ')</div>';
          return;
        }}
        setDemoState('demo data: enabled');
        const rawText = await resp.text();
        const rows = JSON.parse(rawText);
        const rawRows = extractRawScalarRows(rawText, rows);
        if (!rows || rows.length === 0) {{
          tableContainer.innerHTML = '<div class="live-empty">No rows found.</div>';
          return;
        }}
        const cols = Object.keys(rows[0]);
        let html = '<table class="data-table"><thead><tr>';
        for (const c of cols) html += '<th>' + escapeHtml(c) + '</th>';
        html += '</tr></thead><tbody>';
        for (let rowIndex = 0; rowIndex < rows.length; rowIndex++) {{
          const row = rows[rowIndex];
          html += '<tr>';
          for (const c of cols) {{
            const displayValue = rawRows.length === rows.length
              ? rawCellDisplay(rawRows[rowIndex][c], row[c])
              : String(row[c] ?? '');
            html += '<td title="' + escapeHtml(displayValue) + '">' + escapeHtml(displayValue) + '</td>';
          }}
          html += '</tr>';
        }}
        html += '</tbody></table>';
        tableContainer.innerHTML = html;
      }} catch(e) {{
        setDemoState('demo data: unavailable');
        tableContainer.innerHTML = '<div class="live-empty">Error loading live data.</div>';
      }}
    }}

    function startLivePolling(entityName) {{
      if (liveTimers[entityName]) clearInterval(liveTimers[entityName]);
      loadLiveData(entityName);
      liveTimers[entityName] = setInterval(() => loadLiveData(entityName), 5000);
    }}

    // ---- Init ----
    // Wire descriptor hint inputs into the existing entity request preview panel.
    DESCRIPTORS.forEach(descriptor => {{
      const entityName = descriptorEntityName(descriptor);
      if (!entityName) return;
      const tabName = descriptor.coverageKey.slice(entityName.length + 1);
      (descriptor.hints || []).forEach(fd => {{
        const el = document.getElementById(fd.id);
        if (el) el.addEventListener('input', () => updateRequestPreview(entityName, tabName));
      }});
    }});
    document.querySelectorAll('[data-coverage-key]').forEach(card => {{
      card.addEventListener('keydown', event => {{
        if (!(event.ctrlKey && event.key === 'Enter')) return;
        const button = card.querySelector('[data-action-button]');
        if (button && !button.disabled) {{
          event.preventDefault();
          button.click();
        }}
      }});
    }});
    refreshCoverageMap();

    // Activate first entity and start polling for all entities
    if (ENTITY_NAMES.length > 0) {{
      showEntity(ENTITY_NAMES[0]);
      ENTITY_NAMES.forEach(name => startLivePolling(name));
    }} else {{
      setDemoState('demo data: unavailable');
    }}
  </script>
</body>
</html>
"""


def _batch_actions(metadata: MetadataProject) -> list[dict[str, Any]]:
    target_profile = TARGET_PROFILES.get(metadata.target_profile)
    if target_profile is None or not target_profile.emit_spring_batch:
        return []
    if not (_has_handoffs(metadata) or _has_downstream_file_contracts(metadata)):
        return []

    actions: list[dict[str, str]] = []
    for entity in metadata.entities:
        has_handoff = _has_handoffs_for_entity(metadata, entity.name)
        downstream_contracts = _downstream_file_contracts_for_entity(metadata, entity.name)
        if not has_handoff and not downstream_contracts:
            continue
        entity_var = entity.name[:1].lower() + entity.name[1:]
        run_semantics = _batch_run_semantics_for_entity(metadata, entity.name)
        output_hint = f"./{metadata.bounded_context}-eod"
        if downstream_contracts:
            output_names = _downstream_output_hint_names(entity_var, downstream_contracts)
            output_hint = f"{output_hint}/" + ", ".join(output_names)
        actions.append(
            {
                "entityName": entity.name,
                "label": (
                    f"Run {_display_entity_name(entity.name)} downstream outputs"
                    if downstream_contracts and not has_handoff
                    else f"Generate {_display_entity_name(entity.name)} EOD File"
                    if downstream_contracts
                    else f"Run {entity_var}EodJob"
                ),
                "jobName": f"{entity_var}EodJob",
                "outputHint": output_hint,
                "runSemantics": run_semantics is not None,
                "effectiveRunIdMax": (
                    min(run_semantics.physical_run_id_max_length, 2500)
                    if run_semantics is not None
                    and run_semantics.physical_run_id_max_length is not None
                    else 2500
                ),
            }
        )
    return actions


def _batch_run_semantics_for_entity(metadata: MetadataProject, entity_name: str) -> Any | None:
    bindings = [
        contract.run_semantics
        for contract in metadata.contracts
        if contract.run_semantics is not None
        and contract.run_semantics.entity_name == entity_name
    ]
    if len(bindings) > 1:
        raise ValueError(
            f"Entity '{entity_name}' has multiple run_semantics bindings; "
            "the test-console job card would be ambiguous."
        )
    return bindings[0] if bindings else None


def _batch_run_semantics_hints(
    *,
    job_name: str,
    effective_run_id_max: int,
) -> list[dict[str, Any]]:
    return [
        {
            "id": _safe_dom_id(f"batch-{job_name}-run-id"),
            "label": "Run ID",
            "canonicalName": "runId",
            "contractName": "runId",
            "inputType": "text",
            "required": True,
            "maxLength": effective_run_id_max,
            "minLength": None,
            "pattern": None,
            "minValue": None,
            "maxValue": None,
            "defaultValue": None,
            "allowedValues": [],
            "placeholder": "RUN-001",
            "step": None,
            "helpText": "Caller-supplied identity; leading or trailing whitespace is rejected.",
        },
        {
            "id": _safe_dom_id(f"batch-{job_name}-business-date"),
            "label": "Business date",
            "canonicalName": "businessDate",
            "contractName": "businessDate",
            "inputType": "date",
            "required": True,
            "maxLength": None,
            "minLength": None,
            "pattern": None,
            "minValue": None,
            "maxValue": None,
            "defaultValue": None,
            "allowedValues": [],
            "placeholder": "",
            "step": None,
            "helpText": "Frozen for the run identity after the first identity step succeeds.",
        },
    ]


def _render_batch_actions_section(
    descriptors: list[ActionCardDescriptor],
    *,
    entity_name: str,
) -> str:
    action_blocks = _render_batch_action_cards(descriptors, entity_name=entity_name)
    if not action_blocks:
        return ""
    return f"""
        <p class="group-note">Local test tooling for generated batch jobs. These actions call the generated <code>POST /batch/run/{{jobName}}</code> endpoint and do not run automatically.</p>
        <p class="group-note">Responses show <code>jobName</code>, <code>jobId</code>, <code>status</code>, <code>exitCode</code>, and <code>startTime</code> when the generated batch endpoint returns them.</p>
        <div class="batch-actions">
{action_blocks}
        </div>
"""


def _render_batch_action_cards(
    descriptors: list[ActionCardDescriptor],
    *,
    entity_name: str,
) -> str:
    return "\n".join(
        _render_action_card(
            descriptor,
            panel_id=_safe_dom_id(f"{entity_name}-{descriptor.coverageKey}"),
            panel_class="batch-action",
            button_label="Run Batch Action \u2192",
            response_panel_id=f"resp-panel-{_safe_dom_id(entity_name)}-{_safe_dom_id(descriptor.coverageKey)}",
        )
        for descriptor in descriptors
    )


def _display_entity_name(entity_name: str) -> str:
    words: list[str] = []
    current = ""
    for char in entity_name:
        if current and char.isupper():
            words.append(current)
            current = char
        else:
            current += char
    if current:
        words.append(current)
    return " ".join(words) or entity_name


def _has_handoffs(metadata: MetadataProject) -> bool:
    return any(contract.type == "staging-table" for contract in metadata.contracts)


def _has_handoffs_for_entity(metadata: MetadataProject, entity_name: str) -> bool:
    return any(
        mapping.source_path.startswith(f"{entity_name}.")
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_HANDOFF
    )


def _has_downstream_file_contracts(metadata: MetadataProject) -> bool:
    downstream_file_contract_names = {
        contract.name
        for contract in metadata.contracts
        if contract.type in {"file-fixed-width", "file-csv"}
    }
    return any(
        mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.contract_name in downstream_file_contract_names
        for mapping in metadata.mappings
    )


def _downstream_file_contracts_for_entity(
    metadata: MetadataProject,
    entity_name: str,
) -> list[ContractMetadata]:
    contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.source_path.startswith(f"{entity_name}.")
    }
    return [
        contract
        for contract in metadata.contracts
        if contract.name in contract_names and contract.type in {"file-fixed-width", "file-csv"}
    ]


def _downstream_output_hint_names(
    entity_var: str,
    contracts: list[ContractMetadata],
) -> list[str]:
    if len(contracts) == 1:
        extension = "csv" if contracts[0].type == "file-csv" else "dat"
        return [f"{entity_var}-eod-YYYYMMDD.{extension}"]
    output_names: list[str] = []
    used_slugs: set[str] = set()
    for contract in contracts:
        slug_base = to_snake_case(contract.name).replace("_", "-") or contract.name.lower()
        slug = slug_base
        suffix = 2
        while slug in used_slugs:
            slug = f"{slug_base}-{suffix}"
            suffix += 1
        used_slugs.add(slug)
        extension = "csv" if contract.type == "file-csv" else "dat"
        output_names.append(f"{entity_var}-{slug}-YYYYMMDD.{extension}")
    return output_names


def _is_ui_operation_candidate(metadata: MetadataProject, operation: CanonicalOperation) -> bool:
    if operation.http_method is not None or operation.path:
        return True
    return any(
        mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
        and mapping.contract_name == operation.interface_name
        and mapping.operation_name == operation.name
        for mapping in metadata.mappings
    )


def _has_upstream_file_to_canonical_mappings(metadata: MetadataProject) -> bool:
    upstream_file_contract_names = {
        contract.name
        for contract in metadata.contracts
        if contract.type in {"file-fixed-width", "file-csv"}
    }
    return any(
        mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
        and mapping.contract_name in upstream_file_contract_names
        for mapping in metadata.mappings
    )


def _has_upstream_xml_to_canonical_mappings(metadata: MetadataProject) -> bool:
    upstream_xml_contract_names = {
        contract.name
        for contract in metadata.contracts
        if contract.type == "xml-xsd"
    }
    return any(
        mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
        and mapping.contract_name in upstream_xml_contract_names
        for mapping in metadata.mappings
    )


def _has_downstream_xml_contracts(metadata: MetadataProject) -> bool:
    downstream_xml_contract_names = {
        contract.name
        for contract in metadata.contracts
        if contract.type == "xml-xsd"
    }
    return any(
        mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.contract_name in downstream_xml_contract_names
        for mapping in metadata.mappings
    )


def _upstream_file_contracts_for_entity(metadata: MetadataProject, entity_name: str):
    contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
        and mapping.target_path.startswith(f"{entity_name}.")
    }
    return [
        contract
        for contract in metadata.contracts
        if contract.name in contract_names and contract.type in {"file-fixed-width", "file-csv"}
    ]


def _has_upstream_file_to_canonical_mappings_for_entity(
    metadata: MetadataProject,
    entity_name: str,
) -> bool:
    return bool(_upstream_file_contracts_for_entity(metadata, entity_name))


def _append_group_block(
    group_blocks: dict[str, list[tuple[int, str]]],
    *,
    group: str,
    html_block: str,
    card_count: int,
) -> None:
    if not html_block.strip() or card_count <= 0:
        return
    group_blocks.setdefault(group, []).append((card_count, html_block))


def _render_action_group_section(group: str, blocks: list[tuple[int, str]]) -> str:
    if not blocks:
        return ""
    label = _ACTION_GROUP_LABELS.get(group, group.title())
    icon = _ACTION_GROUP_ICONS.get(group, "\u2022")
    count = sum(card_count for card_count, _html_block in blocks)
    inner_html = "\n".join(html_block for _card_count, html_block in blocks)
    open_attr = " open" if group == "UPSTREAM" else ""
    return f"""
      <details class="group-section" data-group="{html.escape(group)}"{open_attr}>
        <summary><span class="group-icon" aria-hidden="true">{html.escape(icon)}</span><span class="group-title">{html.escape(label)}</span><span class="group-count">({count})</span></summary>
        <div class="group-section-body">
{inner_html}
        </div>
      </details>"""


def _render_action_group_sections(group_blocks: dict[str, list[tuple[int, str]]]) -> str:
    return "\n".join(
        section
        for group in _ACTION_GROUP_ORDER
        if (section := _render_action_group_section(group, group_blocks.get(group, [])))
    )


def _entity_batch_descriptors(
    descriptors_by_key: dict[str, ActionCardDescriptor],
    entity_name: str,
) -> list[ActionCardDescriptor]:
    return [
        descriptor
        for descriptor in descriptors_by_key.values()
        if descriptor.group == "BATCH"
        and descriptor.owner_entity == entity_name
    ]


def _render_entity_dashboard_panel(
    *,
    entity_name: str,
    panels: list[dict],
    metadata: MetadataProject,
    descriptors_by_key: dict[str, ActionCardDescriptor],
) -> str:
    """Render the dashboard panel for one entity — CRUD tabs + live viewer.

    # generates Create/Get/List/Update/Delete tabs and live data table.
    """
    has_create = bool(panels)
    tabs = _rendered_dashboard_tabs(metadata, entity_name, has_create_panel=has_create)
    first_active_tab = tabs[0][0] if tabs else "get"

    tabs_html = "\n      ".join(
        f'<button id="crud-tab-{html.escape(entity_name)}-{t}" '
        f'class="crud-tab{" active" if t == first_active_tab else ""}" '
        f'type="button" role="tab" aria-selected="{"true" if t == first_active_tab else "false"}" '
        f'aria-controls="crud-{html.escape(entity_name)}-{t}" '
        f'data-tab="{t}" onclick="showCrudTab(\'{html.escape(entity_name)}\', \'{t}\')">'
        f'{html.escape(label)}</button>'
        for i, (t, label) in enumerate(tabs)
    )

    # Create panel content
    create_panel_html = ""
    create_descriptor = descriptors_by_key.get(f"{entity_name}-create")
    if create_descriptor is not None:
        create_panel_html = _render_action_card(
            create_descriptor,
            panel_id=f"crud-{entity_name}-create",
            panel_class="crud-panel",
            active=first_active_tab == "create",
            button_label="Send Create Request \u2192",
            include_request_preview_for=entity_name,
            labelled_by=f"crud-tab-{entity_name}-create",
        )
    else:
        # No create panel but req-preview still needed for JS
        create_panel_html = f"""
      <div style="display:none">
        <pre class="json" id="req-preview-{html.escape(entity_name)}"></pre>
      </div>"""

    # Get by ID panel
    get_panel_html = ""
    get_descriptor = descriptors_by_key.get(f"{entity_name}-get")
    if get_descriptor is not None:
        get_panel_html = _render_action_card(
            get_descriptor,
            panel_id=f"crud-{entity_name}-get",
            panel_class="crud-panel",
            active=first_active_tab == "get",
            button_label="Send Request \u2192",
            labelled_by=f"crud-tab-{entity_name}-get",
        )

    # List panel
    list_panel_html = ""
    list_descriptor = descriptors_by_key.get(f"{entity_name}-list")
    if list_descriptor is not None:
        list_panel_html = _render_action_card(
            list_descriptor,
            panel_id=f"crud-{entity_name}-list",
            panel_class="crud-panel",
            active=first_active_tab == "list",
            button_label="Fetch All \u2192",
            labelled_by=f"crud-tab-{entity_name}-list",
        )

    # Update panel
    update_panel_html = ""
    update_descriptor = descriptors_by_key.get(f"{entity_name}-update")
    if update_descriptor is not None:
        update_panel_html = _render_action_card(
            update_descriptor,
            panel_id=f"crud-{entity_name}-update",
            panel_class="crud-panel",
            button_label="Send Update \u2192",
            labelled_by=f"crud-tab-{entity_name}-update",
        )

    # Delete panel
    delete_panel_html = ""
    delete_descriptor = descriptors_by_key.get(f"{entity_name}-delete")
    if delete_descriptor is not None:
        delete_panel_html = _render_action_card(
            delete_descriptor,
            panel_id=f"crud-{entity_name}-delete",
            panel_class="crud-panel",
            button_label="Delete \u2192",
            button_class="btn btn-danger",
            labelled_by=f"crud-tab-{entity_name}-delete",
        )

    group_blocks: dict[str, list[tuple[int, str]]] = {}
    crud_descriptors = [
        descriptor
        for descriptor in [
            create_descriptor,
            get_descriptor,
            list_descriptor,
            update_descriptor,
            delete_descriptor,
        ]
        if descriptor is not None
    ]
    if crud_descriptors:
        crud_group = crud_descriptors[0].group
        tabs_container_html = ""
        if tabs_html:
            tabs_container_html = f"""
        <!-- CRUD action tabs — only rendered for generated backend operations -->
        <div class="crud-tabs" role="tablist" aria-label="{html.escape(entity_name)} actions">
          {tabs_html}
        </div>"""
        crud_panels_html = "\n".join(
            panel_html
            for panel_html in [
                create_panel_html,
                get_panel_html,
                list_panel_html,
                update_panel_html,
                delete_panel_html,
            ]
            if panel_html.strip()
        )
        _append_group_block(
            group_blocks,
            group=crud_group,
            html_block=f"{tabs_container_html}\n{crud_panels_html}",
            card_count=len(crud_descriptors),
        )

    file_ingest_cards = _render_file_ingest_card_blocks(
        metadata,
        entity_name,
        descriptors_by_key,
    )
    if file_ingest_cards:
        file_intro_html = ""
        if not tabs:
            file_intro_html = """
        <p class="group-note">
          This package is driven by file edge contracts instead of REST/OpenAPI operations.
          Enter a server-side path under the configured ingest base directory and invoke the generated parser/mapping runtime.
        </p>"""
        _append_group_block(
            group_blocks,
            group=file_ingest_cards[0][0].group,
            html_block=file_intro_html + "\n" + "\n".join(card_html for _descriptor, card_html in file_ingest_cards),
            card_count=len(file_ingest_cards),
        )

    for descriptor, card_html in _render_xml_ingest_card_blocks(
        metadata,
        entity_name,
        descriptors_by_key,
    ):
        _append_group_block(
            group_blocks,
            group=descriptor.group,
            html_block=card_html,
            card_count=1,
        )

    for descriptor, card_html in _render_xml_output_card_blocks(
        metadata,
        entity_name,
        descriptors_by_key,
    ):
        _append_group_block(
            group_blocks,
            group=descriptor.group,
            html_block=card_html,
            card_count=1,
        )

    for descriptor, card_html in _render_soap_action_card_blocks(
        metadata,
        entity_name,
        descriptors_by_key,
    ):
        _append_group_block(
            group_blocks,
            group=descriptor.group,
            html_block=card_html,
            card_count=1,
        )

    batch_descriptors = _entity_batch_descriptors(descriptors_by_key, entity_name)
    if batch_descriptors:
        _append_group_block(
            group_blocks,
            group=batch_descriptors[0].group,
            html_block=_render_batch_actions_section(batch_descriptors, entity_name=entity_name),
            card_count=len(batch_descriptors),
        )
    group_sections_html = _render_action_group_sections(group_blocks)

    # Live data viewer
    live_viewer_html = f"""
      <!-- live data viewer — auto-refreshes via /api/demo/entities/{html.escape(entity_name)} -->
      <div class="live-section">
        <h3><span class="live-dot"></span> Live Data &mdash; {html.escape(entity_name)} (auto-refresh every 5s)</h3>
        <div id="live-table-{html.escape(entity_name)}">
          <div class="live-empty">Loading&hellip;</div>
        </div>
      </div>"""

    return f"""      <div id="entity-panel-{html.escape(entity_name)}" class="entity-panel">
        <h2>{html.escape(entity_name)}</h2>
        {group_sections_html}
        {live_viewer_html}
      </div>"""


def _render_operation_section(panel: dict) -> str:
    """Render one <section> card for a single upstream operation panel."""
    operation = panel["operation"]
    form_id = panel["form_id"]
    response_panel_id = panel["response_panel_id"]
    entity_name = panel["entity_name"]
    endpoint = panel["endpoint"]
    field_descriptors = panel["field_descriptors"]

    form_fields_html = "\n".join(
        _render_field_block(fd) for fd in field_descriptors
    )
    endpoint_label = html.escape(endpoint)
    return (
        f'    <section class="section">\n'
        f'      <h2>Try it — {html.escape(operation.name)}</h2>\n'
        f'      <p style="color:var(--muted);margin-top:-8px;margin-bottom:16px;">'
        f'Entity: <strong>{html.escape(entity_name)}</strong> &nbsp;·&nbsp; '
        f'POST <code>{endpoint_label}</code></p>\n'
        f'      <form id="{html.escape(form_id)}">\n'
        f'{form_fields_html}\n'
        f'        <button type="submit">Send Request →</button>\n'
        f'      </form>\n\n'
        f'      <div id="{html.escape(response_panel_id)}" class="response-panel" aria-live="polite">\n'
        f'        <pre></pre>\n'
        f'      </div>\n'
        f'    </section>'
    )


def _entity_route_base(metadata: MetadataProject, entity_name: str) -> str:
    from appbuilder.generation.utils import compatible_read_route_base

    candidate_bases = [
        (base, operation.http_method == HttpMethod.GET and operation.response_shape == ResponseShape.LIST)
        for operation in metadata.operations
        if _operation_targets_entity(operation, entity_name)
        if (
            base := _spec_entity_route_base_candidate(
                path=operation.path,
                http_method=operation.http_method,
                response_shape=operation.response_shape,
                path_parameter_count=len(operation.path_parameters),
            )
        )
    ]
    return compatible_read_route_base(candidate_bases) or f"/{to_snake_case(entity_name)}s"


def _entity_operations(metadata: MetadataProject, entity_name: str) -> list[CanonicalOperation]:
    return [
        operation
        for operation in metadata.operations
        if _is_ui_operation_candidate(metadata, operation)
        if _operation_targets_generated_crud_controller(operation, entity_name)
    ]


def _uses_explicit_read_surface(metadata: MetadataProject, entity_name: str) -> bool:
    operations = _entity_operations(metadata, entity_name)
    if not operations:
        return False
    categories = {_ui_operation_category(operation) for operation in operations}
    if "create" in categories or categories.intersection({"update", "delete", "state_transition"}):
        return False
    return bool(categories.intersection(_READ_OPERATION_CATEGORIES))


def _rendered_dashboard_tabs(
    metadata: MetadataProject,
    entity_name: str,
    *,
    has_create_panel: bool,
) -> list[tuple[str, str]]:
    if (
        _has_upstream_file_to_canonical_mappings_for_entity(metadata, entity_name)
        and not _entity_operations(metadata, entity_name)
    ):
        return []
    if not _uses_explicit_read_surface(metadata, entity_name):
        tabs: list[tuple[str, str]] = []
        if has_create_panel:
            tabs.append(("create", "Create"))
        tabs.extend([
            ("get", "Get by ID"),
            ("list", "List"),
            ("update", "Update"),
            ("delete", "Delete"),
        ])
        return tabs

    tabs = []
    if _entity_get_operation(metadata, entity_name):
        tabs.append(("get", "Get"))
    if _entity_list_operation(metadata, entity_name):
        tabs.append(("list", "List"))
    return tabs


def _render_file_ingest_card_blocks(
    metadata: MetadataProject,
    entity_name: str,
    descriptors_by_key: dict[str, ActionCardDescriptor],
) -> list[tuple[ActionCardDescriptor, str]]:
    inbound_contracts = _upstream_file_contracts_for_entity(metadata, entity_name)
    card_blocks: list[tuple[ActionCardDescriptor, str]] = []
    for contract in inbound_contracts:
        descriptor = descriptors_by_key[f"file-{entity_name}-{contract.name}"]
        card_blocks.append(
            (
                descriptor,
                _render_action_card(
                    descriptor,
                    panel_id=_safe_dom_id(f"file-{entity_name}-{contract.name}"),
                    panel_class="batch-action",
                    button_label="Run File Ingest \u2192",
                ),
            )
        )
    return card_blocks


def _render_soap_action_card_blocks(
    metadata: MetadataProject,
    entity_name: str,
    descriptors_by_key: dict[str, ActionCardDescriptor],
) -> list[tuple[ActionCardDescriptor, str]]:
    contexts = [
        *_upstream_soap_canonical_ops_for_entity(metadata, entity_name),
        *_downstream_soap_canonical_ops_for_entity(metadata, entity_name),
    ]
    card_blocks: list[tuple[ActionCardDescriptor, str]] = []
    for context in contexts:
        contract = context["contract"]
        operation_name = str(context["operation_name"])
        direction = str(context["soap_contract"].get("direction") or "")
        prefix = "soap-inbound" if direction == "upstream" else "soap-outbound"
        descriptor = descriptors_by_key[
            f"{prefix}-{entity_name}-{contract.name}-{operation_name}"
        ]
        card_blocks.append(
            (
                descriptor,
                _render_action_card(
                    descriptor,
                    panel_id=_safe_dom_id(
                        f"{prefix}-{entity_name}-{contract.name}-{operation_name}"
                    ),
                    panel_class="batch-action",
                ),
            )
        )
    return card_blocks


def _render_action_card(
    descriptor: ActionCardDescriptor,
    *,
    panel_id: str,
    panel_class: str,
    active: bool = False,
    button_label: str | None = None,
    button_class: str = "btn",
    include_request_preview_for: str | None = None,
    response_panel_id: str | None = None,
    labelled_by: str | None = None,
) -> str:
    action = descriptor.actions[0]
    active_class = " active" if active else ""
    inputs_html = _render_action_card_inputs(descriptor)
    output_hint = _render_action_output_hint(descriptor)
    provenance_panel = _render_provenance_panel(descriptor)
    response_panel_id = response_panel_id or _descriptor_response_panel_id(descriptor)
    coverage_js = html.escape(json.dumps(descriptor.coverageKey), quote=True)
    response_js = html.escape(json.dumps(response_panel_id), quote=True)
    action_label = button_label or f"{action.verb} {descriptor.title} \u2192"
    display_endpoint = _display_action_endpoint(descriptor, action)
    action_button_id = f"action-btn-{_safe_dom_id(descriptor.coverageKey)}-0"
    sample_button_html = ""
    if _descriptor_should_show_sample_button(descriptor):
        sample_button_html = (
            f'          <button data-fill-sample="{html.escape(descriptor.coverageKey)}" '
            f'class="btn btn-secondary" type="button" title="Fill typed-empty sample values; edit before sending." '
            f'onclick="fillSample({coverage_js})">'
            "Fill sample</button>\n"
        )
    panel_accessibility = ""
    if labelled_by:
        panel_accessibility = (
            f' role="tabpanel" aria-labelledby="{html.escape(labelled_by)}"'
        )
    request_preview_html = ""
    if include_request_preview_for:
        request_preview_html = f"""
        <!-- request JSON preview panel -->
        <div class="request-preview">
          <div class="label">Request Preview</div>
          <pre class="json" id="req-preview-{html.escape(include_request_preview_for)}"></pre>
        </div>"""
    return f"""
      <div id="{html.escape(panel_id)}" class="{html.escape(panel_class)}{active_class}" data-coverage-key="{html.escape(descriptor.coverageKey)}"{panel_accessibility}>
        <h3>{html.escape(action.verb)} {html.escape(display_endpoint)} &mdash; {html.escape(descriptor.title)}</h3>
        {provenance_panel}
        {output_hint}
        <div class="form-grid">
{inputs_html}
{sample_button_html}
          <button id="{html.escape(action_button_id)}" data-action-button="{html.escape(descriptor.coverageKey)}" data-action-index="0" class="{html.escape(button_class)}" type="button" onclick="submitAction({coverage_js}, 0, {response_js})">{html.escape(action_label)}</button>
        </div>{request_preview_html}
        <div id="{html.escape(response_panel_id)}" class="response-panel" aria-live="polite"></div>
      </div>"""


def _render_action_card_inputs(descriptor: ActionCardDescriptor) -> str:
    return "\n".join(
        _render_action_hint_control(hint)
        for hint in descriptor.hints
        if not hint.get("outputHint")
    )


def _display_action_endpoint(descriptor: ActionCardDescriptor, action: Action) -> str:
    values = {
        "contractName": descriptor.provenance.contractName,
        "jobName": descriptor.provenance.contractName,
    }
    endpoint = action.endpoint
    for name, value in values.items():
        endpoint = endpoint.replace(f"{{{name}}}", value)
    return endpoint


def _render_action_hint_control(hint: dict[str, Any]) -> str:
    if hint.get("bodyField"):
        placeholder = html.escape(str(hint.get("placeholder") or '{"field": "value"}'))
        return f"""          <div class="field">
            <label for="{html.escape(str(hint["id"]))}">{html.escape(str(hint["label"]))}</label>
            <textarea id="{html.escape(str(hint["id"]))}" rows="5" style="width:100%;border:1px solid var(--border);border-radius:8px;padding:9px 12px;font-family:monospace;font-size:0.82rem;" placeholder='{placeholder}'></textarea>
          </div>"""
    if hint.get("inputType") == "textarea":
        placeholder = html.escape(str(hint.get("placeholder") or ""))
        required = " required" if hint.get("required") else ""
        help_text = ""
        if hint.get("helpText"):
            help_text = f'<div class="hint">{html.escape(str(hint["helpText"]))}</div>'
        default_value = html.escape(str(hint.get("defaultValue") or ""))
        return f"""          <div class="field">
            <label for="{html.escape(str(hint["id"]))}">{html.escape(str(hint["label"]))}</label>
            {help_text}
            <textarea id="{html.escape(str(hint["id"]))}" name="{html.escape(str(hint["id"]))}" rows="7" style="width:100%;border:1px solid var(--border);border-radius:8px;padding:9px 12px;font-family:monospace;font-size:0.82rem;" placeholder="{placeholder}"{required}>{default_value}</textarea>
          </div>"""
    return _render_field_block(hint)


def _render_action_output_hint(descriptor: ActionCardDescriptor) -> str:
    for hint in descriptor.hints:
        output_hint = hint.get("outputHint")
        if output_hint:
            return f'          <div class="batch-output-hint">Output hint: {html.escape(str(output_hint))}</div>'
    return ""


def _render_xml_ingest_card_blocks(
    metadata: MetadataProject,
    entity_name: str,
    descriptors_by_key: dict[str, ActionCardDescriptor],
) -> list[tuple[ActionCardDescriptor, str]]:
    inbound_contracts = _upstream_xml_contracts_for_entity(metadata, entity_name)
    card_blocks: list[tuple[ActionCardDescriptor, str]] = []
    for contract in inbound_contracts:
        descriptor = descriptors_by_key[f"xml-{entity_name}-ingest-{contract.name}"]
        card_blocks.append(
            (
                descriptor,
                _render_action_card(
                    descriptor,
                    panel_id=_safe_dom_id(f"xml-ingest-{entity_name}-{contract.name}"),
                    panel_class="batch-action",
                    button_label="Run XML Ingest \u2192",
                ),
            )
        )
    return card_blocks


def _render_xml_output_card_blocks(
    metadata: MetadataProject,
    entity_name: str,
    descriptors_by_key: dict[str, ActionCardDescriptor],
) -> list[tuple[ActionCardDescriptor, str]]:
    downstream_contracts = _downstream_xml_contracts_for_entity(metadata, entity_name)
    card_blocks: list[tuple[ActionCardDescriptor, str]] = []
    for contract in downstream_contracts:
        descriptor = descriptors_by_key[f"xml-{entity_name}-output-{contract.name}"]
        card_blocks.append(
            (
                descriptor,
                _render_action_card(
                    descriptor,
                    panel_id=_safe_dom_id(f"xml-output-{entity_name}-{contract.name}"),
                    panel_class="batch-action",
                    button_label="Run XML Output \u2192",
                ),
            )
        )
    return card_blocks


def _upstream_xml_contracts_for_entity(metadata: MetadataProject, entity_name: str) -> list[ContractMetadata]:
    contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
        and mapping.target_path.startswith(f"{entity_name}.")
    }
    return [
        contract
        for contract in metadata.contracts
        if contract.name in contract_names and contract.type == "xml-xsd"
    ]


def _downstream_xml_contracts_for_entity(metadata: MetadataProject, entity_name: str) -> list[ContractMetadata]:
    contract_names = {
        mapping.contract_name
        for mapping in metadata.mappings
        if mapping.direction == MappingDirection.CANONICAL_TO_DOWNSTREAM
        and mapping.source_path.startswith(f"{entity_name}.")
    }
    return [
        contract
        for contract in metadata.contracts
        if contract.name in contract_names and contract.type == "xml-xsd"
    ]


def _soap_contract_dict(contract: ContractMetadata) -> dict[str, Any] | None:
    soap_contract = getattr(contract, "soap_contract", None)
    if contract.type != "soap-wsdl" or not isinstance(soap_contract, dict):
        return None
    return soap_contract


def _soap_operation_mappings(soap_contract: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    operation_mappings = soap_contract.get("operation_mappings") or {}
    if isinstance(operation_mappings, dict):
        return [
            (str(operation_name), mapping)
            for operation_name, mapping in operation_mappings.items()
            if isinstance(mapping, dict)
        ]
    if isinstance(operation_mappings, list):
        return [
            (str(mapping.get("operation") or ""), mapping)
            for mapping in operation_mappings
            if isinstance(mapping, dict)
        ]
    return []


def _soap_operations_by_name(soap_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    operations = soap_contract.get("operations") or ()
    return {
        str(operation.get("name")): operation
        for operation in operations
        if isinstance(operation, dict) and operation.get("name")
    }


def _soap_canonical_ops_for_entity(
    metadata: MetadataProject,
    entity_name: str,
    *,
    direction: str,
    kind: str,
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for contract in metadata.contracts:
        soap_contract = _soap_contract_dict(contract)
        if soap_contract is None or soap_contract.get("direction") != direction:
            continue
        operations_by_name = _soap_operations_by_name(soap_contract)
        for operation_name, mapping in _soap_operation_mappings(soap_contract):
            if mapping.get("mode") != "canonical":
                continue
            canonical_operation = mapping.get("canonical_operation") or {}
            if canonical_operation.get("kind") != kind:
                continue
            if canonical_operation.get("entity") != entity_name:
                continue
            resolved_operation_name = str(mapping.get("operation") or operation_name)
            operation = operations_by_name.get(resolved_operation_name)
            if not operation:
                continue
            contexts.append(
                {
                    "contract": contract,
                    "soap_contract": soap_contract,
                    "operation_name": resolved_operation_name,
                    "operation": operation,
                    "mapping": mapping,
                    "canonical_operation": canonical_operation,
                }
            )
    return contexts


def _upstream_soap_canonical_ops_for_entity(
    metadata: MetadataProject,
    entity_name: str,
) -> list[dict[str, Any]]:
    return _soap_canonical_ops_for_entity(
        metadata,
        entity_name,
        direction="upstream",
        kind="read_by_id",
    )


def _downstream_soap_canonical_ops_for_entity(
    metadata: MetadataProject,
    entity_name: str,
) -> list[dict[str, Any]]:
    return _soap_canonical_ops_for_entity(
        metadata,
        entity_name,
        direction="downstream",
        kind="invoke_by_id",
    )


def _safe_dom_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "file-ingest"


def _entity_get_operation(
    metadata: MetadataProject,
    entity_name: str,
) -> CanonicalOperation | None:
    if _uses_explicit_read_surface(metadata, entity_name):
        for operation in _entity_operations(metadata, entity_name):
            if _ui_operation_category(operation) in {"get_by_id", "computed_read"}:
                return operation
        return None
    return _get_by_id_operation(metadata, entity_name)


def _entity_list_operation(
    metadata: MetadataProject,
    entity_name: str,
) -> CanonicalOperation | None:
    if _uses_explicit_read_surface(metadata, entity_name):
        for operation in _entity_operations(metadata, entity_name):
            if _ui_operation_category(operation) in {"list", "read_list"}:
                return operation
        return None
    return _list_operation(metadata, entity_name)


def _read_route_template(
    metadata: MetadataProject,
    entity_name: str,
    operation: CanonicalOperation | None,
    *,
    tab_name: str,
) -> str:
    entity_route_base = _entity_route_base(metadata, entity_name)
    if operation and operation.path:
        if _uses_explicit_read_surface(metadata, entity_name):
            return operation.path
        if (
            _supports_spec_route(operation)
            and (operation.path == entity_route_base or operation.path.startswith(entity_route_base + "/"))
        ):
            return operation.path
    if tab_name == "get":
        return f"{entity_route_base}/{{id}}"
    return entity_route_base


def _path_variable_name_from_template(template: str, *, fallback: str) -> str:
    match = re.search(r"\{([^{}]+)\}", template)
    if not match:
        return fallback
    return match.group(1)


def _operation_targets_entity(operation: CanonicalOperation, entity_name: str) -> bool:
    if operation.http_method == HttpMethod.GET:
        return operation_entity_name(operation) == entity_name
    return operation.request_entity == entity_name or operation.response_entity == entity_name


def _operation_targets_generated_crud_controller(
    operation: CanonicalOperation,
    entity_name: str,
) -> bool:
    return operation_entity_name(operation) == entity_name


def _supports_spec_route(operation: CanonicalOperation) -> bool:
    return _supports_spec_route_helper(
        path=operation.path,
        http_method=operation.http_method,
        response_shape=operation.response_shape,
        path_parameter_count=len(operation.path_parameters),
    )


def _render_field_block(field_descriptor: dict[str, object]) -> str:
    label_suffix = ""
    if not field_descriptor["required"]:
        label_suffix = '<span class="optional">(optional)</span>'

    hint = ""
    if field_descriptor["contractName"] != field_descriptor["canonicalName"]:
        hint = (
            f'<div class="hint">API field: {html.escape(str(field_descriptor["contractName"]))}</div>'
        )
    if field_descriptor.get("helpText"):
        hint += f'<div class="hint">{html.escape(str(field_descriptor["helpText"]))}</div>'
    hint += (
        f'<div class="hint rule-summary">Rules: '
        f'{html.escape(_field_rule_summary(field_descriptor))}</div>'
    )

    if field_descriptor["inputType"] == "checkbox":
        checked = " checked" if field_descriptor["defaultValue"] else ""
        return (
            "        <div class=\"field\">"
            f"<label for=\"{html.escape(str(field_descriptor['id']))}\">{html.escape(str(field_descriptor['label']))} {label_suffix}</label>"
            f"{hint}"
            "<div class=\"checkbox-row\">"
            f"<input id=\"{html.escape(str(field_descriptor['id']))}\" name=\"{html.escape(str(field_descriptor['id']))}\" type=\"checkbox\"{checked} />"
            f"<span>{html.escape(str(field_descriptor['label']))}</span>"
            "</div>"
            "</div>"
        )

    if field_descriptor["allowedValues"]:
        options = ['<option value=""></option>' if not field_descriptor["required"] or field_descriptor.get("writeTransport") else ""]
        for value in field_descriptor["allowedValues"]:
            selected = " selected" if value == field_descriptor["defaultValue"] else ""
            options.append(
                f'<option value="{html.escape(str(value))}"{selected}>{html.escape(str(value))}</option>'
            )
        control = (
            f'<select id="{html.escape(str(field_descriptor["id"]))}" '
            f'name="{html.escape(str(field_descriptor["id"]))}"'
            f'{" required" if field_descriptor["required"] else ""}>'
            + "".join(options)
            + "</select>"
        )
    else:
        attributes = [
            f'id="{html.escape(str(field_descriptor["id"]))}"',
            f'name="{html.escape(str(field_descriptor["id"]))}"',
            f'type="{html.escape(str(field_descriptor["inputType"]))}"',
        ]
        if field_descriptor["step"]:
            attributes.append(f'step="{html.escape(str(field_descriptor["step"]))}"')
        if (
            field_descriptor["maxLength"] is not None
            and field_descriptor["inputType"] != "number"
        ):
            attributes.append(f'maxlength="{field_descriptor["maxLength"]}"')
        if (
            field_descriptor["minLength"] is not None
            and field_descriptor["inputType"] not in {"number", "checkbox", "select"}
        ):
            attributes.append(f'minlength="{field_descriptor["minLength"]}"')
        if (
            field_descriptor["pattern"] is not None
            and field_descriptor["inputType"] == "text"
        ):
            attributes.append(
                f'pattern="{html.escape(str(field_descriptor["pattern"]))}"'
            )
        if (
            field_descriptor["minValue"] is not None
            and field_descriptor["inputType"] == "number"
        ):
            attributes.append(f'min="{html.escape(str(field_descriptor["minValue"]))}"')
        if (
            field_descriptor["maxValue"] is not None
            and field_descriptor["inputType"] == "number"
        ):
            attributes.append(f'max="{html.escape(str(field_descriptor["maxValue"]))}"')
        if field_descriptor["required"]:
            attributes.append("required")
        if field_descriptor["defaultValue"] not in (None, ""):
            attributes.append(
                f'value="{html.escape(str(field_descriptor["defaultValue"]))}"'
            )
        if field_descriptor.get("placeholder"):
            attributes.append(
                f'placeholder="{html.escape(str(field_descriptor["placeholder"]))}"'
            )
        control = f"<input {' '.join(attributes)} />"

    return (
        "        <div class=\"field\">"
        f"<label for=\"{html.escape(str(field_descriptor['id']))}\">{html.escape(str(field_descriptor['label']))} {label_suffix}</label>"
        f"{hint}"
        f"{control}"
        "</div>"
    )


def _primary_upstream_operation(metadata: MetadataProject) -> CanonicalOperation:
    for operation in metadata.operations:
        if any(
            mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
            and mapping.contract_name == operation.interface_name
            and mapping.operation_name == operation.name
            for mapping in metadata.mappings
        ):
            return operation
    raise ValueError("No upstream operation with explicit mappings was found.")


def _request_entity(metadata: MetadataProject, operation: CanonicalOperation):
    entity_name = operation_entity_name(operation)
    if entity_name is None:
        raise ValueError(f"Operation '{operation.name}' does not declare a request entity.")
    for entity in metadata.entities:
        if entity.name == entity_name:
            return entity
    raise ValueError(
        f"Operation entity '{entity_name}' for operation '{operation.name}' was not found."
    )


def _request_fields(
    metadata: MetadataProject,
    operation: CanonicalOperation,
    entity_name: str,
) -> list[tuple[CanonicalField, object]]:
    request_mappings = [
        mapping
        for mapping in filter_mappings(
            metadata,
            direction=MappingDirection.UPSTREAM_TO_CANONICAL,
            contract_name=operation.interface_name,
            operation_name=operation.name,
        )
        if ".request." in mapping.source_path and mapping.target_path.startswith(f"{entity_name}.")
    ]
    entity_fields = {field.name: field for entity in metadata.entities if entity.name == entity_name for field in entity.fields}

    results: list[tuple[CanonicalField, object]] = []
    for mapping in request_mappings:
        field_name = canonical_field_name(mapping)
        field = entity_fields[field_name]
        results.append((field, mapping))
    return results


def _build_field_descriptor(
    metadata: MetadataProject,
    entity_name: str,
    field: CanonicalField,
    mapping: FieldMapping,
) -> dict[str, object]:
    allowed_values = _allowed_values(
        metadata,
        entity_name,
        field,
        fallback=list(field.allowed_values),
    )

    default_value = field.default_value
    if default_value is None:
        default_value = _default_value(metadata, entity_name, field)

    input_type = _input_type(field)
    if allowed_values:
        input_type = "select"
    step = "0.01" if field.type.value == "decimal" else None
    return {
        "id": field.name,
        "label": field.name,
        "canonicalName": field.name,
        "contractName": contract_field_name(mapping),
        "inputType": input_type,
        "required": field.required,
        "maxLength": field.max_length,
        "minLength": field.min_length,
        "pattern": field.pattern,
        "minValue": _constraint_value(field.range_min),
        "maxValue": _constraint_value(field.range_max),
        "defaultValue": _coerce_default_value(default_value, field.type.value),
        "allowedValues": allowed_values,
        "placeholder": None,
        "step": step,
    }


def _build_id_field_descriptor(
    metadata: MetadataProject,
    entity: CanonicalEntity,
    *,
    input_id: str,
) -> dict[str, object]:
    id_field = entity_id_field(entity)
    suppress_constraints = id_field.server_generated_id
    if suppress_constraints and any(
        (
            id_field.max_length is not None,
            id_field.min_length is not None,
            id_field.pattern is not None,
            id_field.range_min is not None,
            id_field.range_max is not None,
            id_field.default_value is not None,
            bool(id_field.allowed_values),
        )
    ):
        _append_generation_warning(
            metadata,
            (
                f"{entity.name}.{id_field.name}: input/UI constraints were suppressed "
                "because the field is a server-generated ID."
            ),
        )
    input_type = _input_type_for_type(id_field.type)
    return {
        "id": input_id,
        "label": "ID",
        "canonicalName": id_field.name,
        "contractName": id_field.name,
        "inputType": input_type,
        "required": True,
        "maxLength": None if suppress_constraints else id_field.max_length,
        "minLength": None if suppress_constraints else id_field.min_length,
        "pattern": None if suppress_constraints else id_field.pattern,
        "minValue": None if suppress_constraints else _constraint_value(id_field.range_min),
        "maxValue": None if suppress_constraints else _constraint_value(id_field.range_max),
        "defaultValue": None,
        "allowedValues": [],
        "placeholder": "Enter ID",
        "step": "0.01" if id_field.type.value == "decimal" else None,
    }


def _build_template_path_field_descriptor(
    metadata: MetadataProject,
    entity: CanonicalEntity,
    *,
    input_id: str,
    route_template: str,
) -> dict[str, object]:
    descriptor = _build_id_field_descriptor(
        metadata,
        entity,
        input_id=input_id,
    )
    if not re.search(r"\{([^{}]+)\}", route_template):
        return descriptor
    path_variable_name = _path_variable_name_from_template(
        route_template,
        fallback=entity_id_field(entity).name,
    )
    descriptor["label"] = path_variable_name
    descriptor["canonicalName"] = path_variable_name
    descriptor["contractName"] = path_variable_name
    descriptor["placeholder"] = f"Enter {path_variable_name}"
    return descriptor


def _get_by_id_operation(metadata: MetadataProject, entity_name: str) -> CanonicalOperation | None:
    for operation in metadata.operations:
        if (
            operation_entity_name(operation) == entity_name
            and operation.http_method == HttpMethod.GET
            and operation.response_shape == ResponseShape.SINGLE
            and operation.path_parameters
        ):
            return operation
    return None


def _list_operation(metadata: MetadataProject, entity_name: str) -> CanonicalOperation | None:
    for operation in metadata.operations:
        if (
            operation_entity_name(operation) == entity_name
            and operation.http_method == HttpMethod.GET
            and operation.response_shape == ResponseShape.LIST
        ):
            return operation
    return None


def _build_query_parameter_descriptors(
    *,
    entity_name: str,
    tab_name: str,
    operation: CanonicalOperation | None,
    write: bool = False,
) -> list[dict[str, object]]:
    if operation is None:
        return []
    descriptors: list[dict[str, object]] = []
    for parameter in operation.operation_parameters:
        if parameter.location != OperationParameterLocation.QUERY and not write:
            continue
        descriptors.append(
            {
                "id": f"{tab_name}-{entity_name}-{_parameter_dom_suffix(parameter.name)}",
                "label": parameter.name,
                "canonicalName": parameter.name,
                "contractName": parameter.name,
                "inputType": _input_type_for_type(parameter.type),
                "required": parameter.required,
                "maxLength": None,
                "minLength": None,
                "pattern": parameter.pattern,
                "minValue": None,
                "maxValue": None,
                "defaultValue": None,
                "allowedValues": [],
                "placeholder": None,
                "step": "0.01" if parameter.type == CanonicalFieldType.DECIMAL else None,
            }
        )
        if write:
            descriptors[-1]["writeTransport"] = True
            descriptors[-1]["header" if parameter.location == OperationParameterLocation.HEADER else "query"] = True
            if parameter.type == CanonicalFieldType.BOOLEAN:
                descriptors[-1]["inputType"] = "select"
                descriptors[-1]["allowedValues"] = ["true", "false"]
    return descriptors


def _parameter_dom_suffix(name: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in name)


def _allowed_values(
    metadata: MetadataProject,
    entity_name: str,
    field: CanonicalField,
    *,
    fallback: list[str],
) -> list[str]:
    if fallback:
        return fallback
    for rule in metadata.rules:
        if (
            rule.entity_name == entity_name
            and rule.field_name == field.name
            and rule.type == RuleType.ALLOWED_VALUES
        ):
            return list(rule.values)
    return []


def _default_value(
    metadata: MetadataProject,
    entity_name: str,
    field: CanonicalField,
) -> str | bool | None:
    for rule in metadata.rules:
        if (
            rule.entity_name == entity_name
            and rule.field_name == field.name
            and rule.type == RuleType.DEFAULT
        ):
            return rule.value
    return None


def _input_type(field: CanonicalField) -> str:
    return _input_type_for_type(field.type)


def _input_type_for_type(field_type: CanonicalFieldType) -> str:
    if field_type == CanonicalFieldType.INTEGER:
        return "number"
    if field_type == CanonicalFieldType.DECIMAL:
        return "number"
    if field_type == CanonicalFieldType.BOOLEAN:
        return "checkbox"
    if field_type == CanonicalFieldType.DATE:
        return "date"
    if field_type == CanonicalFieldType.DATETIME:
        return "datetime-local"
    return "text"


def _coerce_default_value(value, field_type: str):
    if value is None:
        return None
    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).lower() == "true"
    return value


def _constraint_value(value: float | None) -> str | None:
    if value is None:
        return None
    return str(int(value)) if value.is_integer() else str(value)
