"""Deterministic SOAP/WSDL contract parsing for EdgeForge manifests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from appbuilder.core.xml_safety import XmlParseBudget, parse_untrusted_xml_with_namespaces

WSDL_NAMESPACE = "http://schemas.xmlsoap.org/wsdl/"
SOAP_BINDING_NAMESPACE = "http://schemas.xmlsoap.org/wsdl/soap/"
XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
SOAP_HTTP_TRANSPORT = "http://schemas.xmlsoap.org/soap/http"

WSDL = f"{{{WSDL_NAMESPACE}}}"
SOAP = f"{{{SOAP_BINDING_NAMESPACE}}}"
XSD = f"{{{XSD_NAMESPACE}}}"

UNSUPPORTED_XSD_ELEMENTS = {
    "choice",
    "all",
    "any",
    "anyAttribute",
    "import",
    "list",
    "union",
}
SUPPORTED_XSD_TYPES = {
    "string",
    "int",
    "integer",
    "long",
    "decimal",
    "boolean",
    "date",
    "dateTime",
}


@dataclass(frozen=True)
class SoapContractFault:
    name: str
    message: str
    element: str


@dataclass(frozen=True)
class SoapContractField:
    name: str
    path: str
    kind: str
    type: str
    required: bool
    repeated: bool = False


@dataclass(frozen=True)
class SoapContractOperation:
    name: str
    soap_action: str | None
    input_message: str
    output_message: str | None
    input_element: str
    output_element: str | None
    input_fields: tuple[SoapContractField, ...] = ()
    output_fields: tuple[SoapContractField, ...] = ()
    faults: tuple[SoapContractFault, ...] = ()


@dataclass(frozen=True)
class SoapContractSpec:
    interface_name: str
    wsdl_path: str
    wsdl_paths: tuple[str, ...]
    target_namespace: str | None
    service: str
    port: str
    binding: str
    operations: tuple[SoapContractOperation, ...]

    def to_metadata(self) -> dict[str, Any]:
        """Return a JSON-serializable SOAP contract payload."""

        return asdict(self)


def load_soap_contract_spec(
    wsdl_path: Path,
    *,
    interface_name: str,
    service: str | None = None,
    port: str | None = None,
    binding: str | None = None,
    operation_names: tuple[str, ...] | None = None,
    source_wsdl_path: str | None = None,
    package_root: Path | None = None,
) -> SoapContractSpec:
    """Load and validate a supported SOAP/WSDL v1.1 contract."""

    if not wsdl_path.exists():
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' references missing WSDL '{wsdl_path}'."
        )
    package_boundary = (package_root or wsdl_path.parent).resolve()
    resolved_wsdl = wsdl_path.resolve()
    try:
        resolved_wsdl.relative_to(package_boundary)
    except ValueError as exc:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' must stay within "
            "the manifest package."
        ) from exc
    parse_budget = XmlParseBudget()
    try:
        root, namespace_map = _parse_xml_with_namespaces(
            wsdl_path,
            budget=parse_budget,
        )
    except ET.ParseError as exc:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' could not parse WSDL '{wsdl_path}': {exc}."
        ) from exc
    if root.tag != f"{WSDL}definitions":
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' expected WSDL 1.1 definitions root in "
            f"'{wsdl_path}'."
        )
    _reject_unsupported_wsdl_constructs(root, interface_name=interface_name, wsdl_path=wsdl_path)
    target_namespace = root.attrib.get("targetNamespace")
    schema_catalog = _load_schema_catalog(
        root,
        interface_name=interface_name,
        wsdl_path=wsdl_path,
        package_boundary=package_boundary,
        namespace_map=namespace_map,
        parse_budget=parse_budget,
    )

    messages = _collect_messages(
        root,
        interface_name=interface_name,
        wsdl_path=wsdl_path,
        namespace_map=namespace_map,
        schema_elements=schema_catalog.elements,
    )
    port_types = _collect_port_types(
        root,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name=interface_name,
        wsdl_path=wsdl_path,
    )
    bindings = _collect_bindings(
        root,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name=interface_name,
        wsdl_path=wsdl_path,
    )
    services = _collect_services(
        root,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name=interface_name,
        wsdl_path=wsdl_path,
    )
    selected_service, selected_port, selected_binding = _select_service_port_binding(
        services=services,
        bindings=bindings,
        interface_name=interface_name,
        wsdl_path=wsdl_path,
        service=service,
        port=port,
        binding=binding,
    )
    port_type_name = selected_binding["port_type"]
    port_type = port_types.get(port_type_name)
    if port_type is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' binding '{selected_binding['name']}' "
            f"references unknown portType '{port_type_name}' in '{wsdl_path}'."
        )
    _validate_selected_binding(
        selected_binding,
        interface_name=interface_name,
        wsdl_path=wsdl_path,
    )
    selected_operations = _select_operations(
        binding=selected_binding,
        port_type=port_type,
        messages=messages,
        interface_name=interface_name,
        wsdl_path=wsdl_path,
        operation_names=operation_names,
        schema_catalog=schema_catalog,
    )
    return SoapContractSpec(
        interface_name=interface_name,
        wsdl_path=source_wsdl_path or str(wsdl_path),
        wsdl_paths=_wsdl_source_paths(
            (resolved_wsdl,),
            wsdl_path=wsdl_path,
            source_wsdl_path=source_wsdl_path,
            package_root=package_root,
        ),
        target_namespace=target_namespace,
        service=selected_service,
        port=selected_port,
        binding=selected_binding["name"],
        operations=tuple(selected_operations),
    )


def _collect_messages(
    root: ET.Element,
    *,
    interface_name: str,
    wsdl_path: Path,
    namespace_map: dict[str, str],
    schema_elements: set[tuple[str | None, str]],
) -> dict[str, dict[str, str]]:
    messages: dict[str, dict[str, str]] = {}
    for message in root.findall(f"{WSDL}message"):
        name = message.attrib.get("name")
        if not name:
            continue
        parts = message.findall(f"{WSDL}part")
        if len(parts) != 1:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' message '{name}' in '{wsdl_path}' "
                "must use exactly one document/literal-wrapped message part."
            )
        part = parts[0]
        element = part.attrib.get("element")
        if not element:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' message '{name}' in '{wsdl_path}' "
                "must reference an XML element, not a type-only part."
            )
        element_namespace, element_local = _resolve_qname(
            element,
            namespace_map=namespace_map,
            interface_name=interface_name,
            wsdl_path=wsdl_path,
            context=f"message '{name}' part element",
        )
        if (element_namespace, element_local) not in schema_elements:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' message '{name}' references unknown "
                f"XSD element '{element}' in '{wsdl_path}'."
            )
        messages[name] = {
            "part": part.attrib.get("name") or "parameters",
            "element": element,
            "element_namespace": element_namespace or "",
            "element_local": element_local,
        }
    return messages


def _collect_port_types(
    root: ET.Element,
    *,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    interface_name: str,
    wsdl_path: Path,
) -> dict[str, dict[str, dict[str, Any]]]:
    port_types: dict[str, dict[str, dict[str, Any]]] = {}
    for port_type in root.findall(f"{WSDL}portType"):
        name = port_type.attrib.get("name")
        if not name:
            continue
        operations: dict[str, dict[str, Any]] = {}
        for operation in port_type.findall(f"{WSDL}operation"):
            operation_name = operation.attrib.get("name")
            if not operation_name:
                continue
            input_element = operation.find(f"{WSDL}input")
            output_element = operation.find(f"{WSDL}output")
            faults = []
            for fault in operation.findall(f"{WSDL}fault"):
                faults.append(
                    {
                        "name": fault.attrib.get("name") or "fault",
                        "message": _resolve_wsdl_qname(
                            fault.attrib.get("message") or "",
                            namespace_map=namespace_map,
                            target_namespace=target_namespace,
                            interface_name=interface_name,
                            wsdl_path=wsdl_path,
                            context=f"portType operation '{operation_name}' fault message",
                        ),
                    }
                )
            operations[operation_name] = {
                "input": _resolve_wsdl_qname(
                    input_element.attrib.get("message") if input_element is not None else "",
                    namespace_map=namespace_map,
                    target_namespace=target_namespace,
                    interface_name=interface_name,
                    wsdl_path=wsdl_path,
                    context=f"portType operation '{operation_name}' input message",
                ),
                "output": _resolve_wsdl_qname(
                    output_element.attrib.get("message") if output_element is not None else "",
                    namespace_map=namespace_map,
                    target_namespace=target_namespace,
                    interface_name=interface_name,
                    wsdl_path=wsdl_path,
                    context=f"portType operation '{operation_name}' output message",
                    allow_empty=True,
                ),
                "faults": faults,
            }
        port_types[name] = operations
    return port_types


def _collect_bindings(
    root: ET.Element,
    *,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    interface_name: str,
    wsdl_path: Path,
) -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for binding in root.findall(f"{WSDL}binding"):
        name = binding.attrib.get("name")
        if not name:
            continue
        soap_binding = binding.find(f"{SOAP}binding")
        operations: dict[str, dict[str, Any]] = {}
        for operation in binding.findall(f"{WSDL}operation"):
            operation_name = operation.attrib.get("name")
            if not operation_name:
                continue
            soap_operation = operation.find(f"{SOAP}operation")
            operations[operation_name] = {
                "soap_action": (
                    soap_operation.attrib.get("soapAction")
                    if soap_operation is not None
                    else None
                ),
                "operation_style": (
                    soap_operation.attrib.get("style") if soap_operation is not None else None
                ),
                "input": operation.find(f"{WSDL}input"),
                "output": operation.find(f"{WSDL}output"),
            }
        bindings[name] = {
            "name": name,
            "port_type": _resolve_wsdl_qname(
                binding.attrib.get("type") or "",
                namespace_map=namespace_map,
                target_namespace=target_namespace,
                interface_name=interface_name,
                wsdl_path=wsdl_path,
                context=f"binding '{name}' type",
            ),
            "soap_binding": soap_binding,
            "operations": operations,
        }
    return bindings


def _validate_selected_binding(
    binding: dict[str, Any],
    *,
    interface_name: str,
    wsdl_path: Path,
) -> None:
    soap_binding = binding.get("soap_binding")
    binding_name = binding["name"]
    if soap_binding is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' binding '{binding_name}' in '{wsdl_path}' "
            "does not declare a SOAP 1.1 binding."
        )
    style = soap_binding.attrib.get("style", "document")
    transport = soap_binding.attrib.get("transport")
    if style != "document":
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' binding '{binding_name}' uses unsupported "
            f"SOAP style '{style}'. Only document/literal-wrapped is supported."
        )
    if transport != SOAP_HTTP_TRANSPORT:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' binding '{binding_name}' uses unsupported "
            f"SOAP transport '{transport}'."
        )


def _validate_selected_binding_operation(
    binding: dict[str, Any],
    operation_name: str,
    *,
    interface_name: str,
    wsdl_path: Path,
) -> None:
    operation = binding["operations"][operation_name]
    operation_style = operation.get("operation_style")
    if operation_style == "rpc":
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' "
            "uses unsupported RPC style."
        )
    _validate_literal_body(
        operation.get("input"),
        interface_name=interface_name,
        wsdl_path=wsdl_path,
        binding_name=binding["name"],
        operation_name=operation_name,
    )
    _validate_literal_body(
        operation.get("output"),
        interface_name=interface_name,
        wsdl_path=wsdl_path,
        binding_name=binding["name"],
        operation_name=operation_name,
        allow_missing=True,
    )


def _collect_services(
    root: ET.Element,
    *,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    interface_name: str,
    wsdl_path: Path,
) -> dict[str, dict[str, str]]:
    services: dict[str, dict[str, str]] = {}
    for service in root.findall(f"{WSDL}service"):
        service_name = service.attrib.get("name")
        if not service_name:
            continue
        ports: dict[str, str] = {}
        for port in service.findall(f"{WSDL}port"):
            port_name = port.attrib.get("name")
            binding_name = _resolve_wsdl_qname(
                port.attrib.get("binding") or "",
                namespace_map=namespace_map,
                target_namespace=target_namespace,
                interface_name=interface_name,
                wsdl_path=wsdl_path,
                context=f"service '{service_name}' port '{port_name or '<unnamed>'}' binding",
            )
            if port_name and binding_name:
                ports[port_name] = binding_name
        services[service_name] = ports
    return services


def _select_service_port_binding(
    *,
    services: dict[str, dict[str, str]],
    bindings: dict[str, dict[str, Any]],
    interface_name: str,
    wsdl_path: Path,
    service: str | None,
    port: str | None,
    binding: str | None,
) -> tuple[str, str, dict[str, Any]]:
    if not services:
        raise ValueError(f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' declares no service.")
    service_name = _select_named(
        available=services,
        requested=service,
        label="service",
        interface_name=interface_name,
        wsdl_path=wsdl_path,
    )
    ports = services[service_name]
    if not ports:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' service '{service_name}' declares no ports."
        )
    if binding is not None:
        matching_ports = {
            port_name: binding_name
            for port_name, binding_name in ports.items()
            if binding_name == binding
        }
        if not matching_ports:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' service '{service_name}' has no port "
                f"using binding '{binding}'."
            )
        ports = matching_ports
    port_name = _select_named(
        available=ports,
        requested=port,
        label="port",
        interface_name=interface_name,
        wsdl_path=wsdl_path,
    )
    binding_name = ports[port_name]
    selected_binding = bindings.get(binding_name)
    if selected_binding is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' port '{port_name}' references unknown "
            f"binding '{binding_name}' in '{wsdl_path}'."
        )
    return service_name, port_name, selected_binding


def _select_named(
    *,
    available: dict[str, Any],
    requested: str | None,
    label: str,
    interface_name: str,
    wsdl_path: Path,
) -> str:
    if requested is not None:
        if requested not in available:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' requested {label} '{requested}' "
                f"was not found in '{wsdl_path}'."
            )
        return requested
    if len(available) != 1:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' declares multiple "
            f"{label}s; specify {label} in the manifest."
        )
    return next(iter(available))


def _select_operations(
    *,
    binding: dict[str, Any],
    port_type: dict[str, dict[str, Any]],
    messages: dict[str, dict[str, str]],
    interface_name: str,
    wsdl_path: Path,
    operation_names: tuple[str, ...] | None,
    schema_catalog: _SchemaCatalog,
) -> list[SoapContractOperation]:
    available_operations = binding["operations"]
    requested = operation_names or tuple(available_operations)
    selected: list[SoapContractOperation] = []
    for operation_name in requested:
        if operation_name not in available_operations or operation_name not in port_type:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' requested operation '{operation_name}' "
                f"was not found in binding '{binding['name']}' in '{wsdl_path}'."
            )
        _validate_selected_binding_operation(
            binding,
            operation_name,
            interface_name=interface_name,
            wsdl_path=wsdl_path,
        )
        port_operation = port_type[operation_name]
        input_message_name = port_operation["input"]
        output_message_name = port_operation["output"]
        input_message = _require_message(
            messages=messages,
            message_name=input_message_name,
            operation_name=operation_name,
            interface_name=interface_name,
            wsdl_path=wsdl_path,
        )
        output_message = (
            _require_message(
                messages=messages,
                message_name=output_message_name,
                operation_name=operation_name,
                interface_name=interface_name,
                wsdl_path=wsdl_path,
            )
            if output_message_name
            else None
        )
        faults: list[SoapContractFault] = []
        for fault in port_operation["faults"]:
            fault_message = _require_message(
                messages=messages,
                message_name=fault["message"],
                operation_name=operation_name,
                interface_name=interface_name,
                wsdl_path=wsdl_path,
            )
            faults.append(
                SoapContractFault(
                    name=fault["name"],
                    message=fault["message"],
                    element=fault_message["element"],
                )
            )
        selected.append(
            SoapContractOperation(
                name=operation_name,
                soap_action=available_operations[operation_name].get("soap_action"),
                input_message=input_message_name,
                output_message=output_message_name or None,
                input_element=input_message["element"],
                output_element=output_message["element"] if output_message is not None else None,
                input_fields=_message_schema_fields(schema_catalog, input_message),
                output_fields=(
                    _message_schema_fields(schema_catalog, output_message)
                    if output_message is not None
                    else ()
                ),
                faults=tuple(faults),
            )
        )
    return selected


def _require_message(
    *,
    messages: dict[str, dict[str, str]],
    message_name: str,
    operation_name: str,
    interface_name: str,
    wsdl_path: Path,
) -> dict[str, str]:
    message = messages.get(message_name)
    if message is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' operation '{operation_name}' references "
            f"unknown message '{message_name}' in '{wsdl_path}'."
        )
    return message


def _message_schema_fields(
    catalog: _SchemaCatalog,
    message: dict[str, str],
) -> tuple[SoapContractField, ...]:
    key = (message.get("element_namespace") or None, message["element_local"])
    definition = catalog.element_definitions.get(key)
    if definition is None:
        return ()
    element, namespace_map, source_path, target_namespace = definition
    return _collect_element_fields(
        element,
        catalog=catalog,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        source_path=source_path,
    )


def _collect_element_fields(
    element: ET.Element,
    *,
    catalog: _SchemaCatalog,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    source_path: Path,
) -> tuple[SoapContractField, ...]:
    root_name = element.attrib.get("name") or "<unnamed>"
    root_path = f"/{root_name}"
    complex_type = _element_complex_type(
        element,
        catalog=catalog,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
    )
    if complex_type is None:
        return (
            SoapContractField(
                name=root_name,
                path=root_path,
                kind="element",
                type=_element_scalar_type(
                    element,
                    catalog=catalog,
                    namespace_map=namespace_map,
                    target_namespace=target_namespace,
                ),
                required=True,
                repeated=False,
            ),
        )
    fields: list[SoapContractField] = []
    sequence = complex_type.find(f"{XSD}sequence")
    if sequence is not None:
        for child in sequence:
            if _local_name(child.tag) != "element":
                continue
            child_name = child.attrib.get("name") or "<unnamed>"
            min_occurs = _parse_occurs(child.attrib.get("minOccurs"), default=1, path=f"{root_path}/{child_name}")
            max_occurs_raw = child.attrib.get("maxOccurs")
            max_occurs = (
                None
                if max_occurs_raw == "unbounded"
                else _parse_occurs(max_occurs_raw, default=1, path=f"{root_path}/{child_name}")
            )
            fields.append(
                SoapContractField(
                    name=child_name,
                    path=f"{root_path}/{child_name}",
                    kind="element",
                    type=_element_scalar_type(
                        child,
                        catalog=catalog,
                        namespace_map=namespace_map,
                        target_namespace=target_namespace,
                    ),
                    required=min_occurs > 0,
                    repeated=max_occurs is None or max_occurs > 1,
                )
            )
    for attribute in complex_type.findall(f"{XSD}attribute"):
        attribute_name = attribute.attrib.get("name") or "<unnamed>"
        fields.append(
            SoapContractField(
                name=attribute_name,
                path=f"{root_path}/@{attribute_name}",
                kind="attribute",
                type=_attribute_scalar_type(
                    attribute,
                    catalog=catalog,
                    namespace_map=namespace_map,
                    target_namespace=target_namespace,
                ),
                required=attribute.attrib.get("use") == "required",
                repeated=False,
            )
        )
    return tuple(fields)


def _element_complex_type(
    element: ET.Element,
    *,
    catalog: _SchemaCatalog,
    namespace_map: dict[str, str],
    target_namespace: str | None,
) -> ET.Element | None:
    inline_complex = element.find(f"{XSD}complexType")
    if inline_complex is not None:
        return inline_complex
    type_name = element.attrib.get("type")
    if type_name is None:
        return None
    type_namespace, local_type = _resolve_xsd_qname(
        type_name,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name="SOAP/WSDL",
        source_path=Path("<metadata>"),
        context="element type",
    )
    return catalog.complex_types.get((type_namespace, local_type))


def _element_scalar_type(
    element: ET.Element,
    *,
    catalog: _SchemaCatalog,
    namespace_map: dict[str, str],
    target_namespace: str | None,
) -> str:
    inline_simple = element.find(f"{XSD}simpleType")
    if inline_simple is not None:
        return _simple_type_base(
            inline_simple,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=target_namespace,
        )
    type_name = element.attrib.get("type")
    if type_name is None:
        return "string"
    type_namespace, local_type = _resolve_xsd_qname(
        type_name,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name="SOAP/WSDL",
        source_path=Path("<metadata>"),
        context="element type",
    )
    if type_namespace == XSD_NAMESPACE:
        return local_type
    simple_type = catalog.simple_types.get((type_namespace, local_type))
    if simple_type is not None:
        return _simple_type_base(
            simple_type,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=type_namespace,
        )
    return "string"


def _attribute_scalar_type(
    attribute: ET.Element,
    *,
    catalog: _SchemaCatalog,
    namespace_map: dict[str, str],
    target_namespace: str | None,
) -> str:
    inline_simple = attribute.find(f"{XSD}simpleType")
    if inline_simple is not None:
        return _simple_type_base(
            inline_simple,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=target_namespace,
        )
    type_name = attribute.attrib.get("type")
    if type_name is None:
        return "string"
    type_namespace, local_type = _resolve_xsd_qname(
        type_name,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name="SOAP/WSDL",
        source_path=Path("<metadata>"),
        context="attribute type",
    )
    if type_namespace == XSD_NAMESPACE:
        return local_type
    simple_type = catalog.simple_types.get((type_namespace, local_type))
    if simple_type is not None:
        return _simple_type_base(
            simple_type,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=type_namespace,
        )
    return "string"


def _simple_type_base(
    simple_type: ET.Element,
    *,
    catalog: _SchemaCatalog,
    namespace_map: dict[str, str],
    target_namespace: str | None,
) -> str:
    restriction = simple_type.find(f"{XSD}restriction")
    if restriction is None:
        return "string"
    base = restriction.attrib.get("base")
    if base is None:
        return "string"
    base_namespace, local_base = _resolve_xsd_qname(
        base,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name="SOAP/WSDL",
        source_path=Path("<metadata>"),
        context="simple type base",
    )
    if base_namespace == XSD_NAMESPACE:
        return local_base
    nested = catalog.simple_types.get((base_namespace, local_base))
    if nested is not None:
        return _simple_type_base(
            nested,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=base_namespace,
        )
    return "string"


def _validate_literal_body(
    binding_io: ET.Element | None,
    *,
    interface_name: str,
    wsdl_path: Path,
    binding_name: str,
    operation_name: str,
    allow_missing: bool = False,
) -> None:
    if binding_io is None:
        if allow_missing:
            return
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' binding '{binding_name}' operation "
            f"'{operation_name}' is missing input binding."
        )
    body = binding_io.find(f"{SOAP}body")
    if body is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' binding '{binding_name}' operation "
            f"'{operation_name}' must declare a soap:body."
        )
    use = body.attrib.get("use", "literal")
    if use != "literal":
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' binding '{binding_name}' operation "
            f"'{operation_name}' uses unsupported soap:body use '{use}'."
        )


@dataclass
class _SchemaCatalog:
    elements: set[tuple[str | None, str]]
    element_definitions: dict[
        tuple[str | None, str],
        tuple[ET.Element, dict[str, str], Path, str | None],
    ]
    complex_types: dict[tuple[str | None, str], ET.Element]
    simple_types: dict[tuple[str | None, str], ET.Element]


def _load_schema_catalog(
    root: ET.Element,
    *,
    interface_name: str,
    wsdl_path: Path,
    package_boundary: Path,
    namespace_map: dict[str, str],
    parse_budget: XmlParseBudget,
) -> _SchemaCatalog:
    schema_sources: list[tuple[ET.Element, dict[str, str], Path, str | None]] = []
    visited_includes: set[Path] = set()

    def add_schema(
        schema: ET.Element,
        *,
        namespace_map: dict[str, str],
        source_path: Path,
        expected_namespace: str | None = None,
    ) -> None:
        _validate_schema_root(
            schema,
            interface_name=interface_name,
            wsdl_path=wsdl_path,
            source_path=source_path,
            expected_namespace=expected_namespace,
        )
        target_namespace = schema.attrib.get("targetNamespace")
        schema_sources.append((schema, namespace_map, source_path, target_namespace))
        for include in schema.findall(f"{XSD}include"):
            location = include.attrib.get("schemaLocation")
            if not location:
                raise ValueError(
                    f"SOAP/WSDL interface '{interface_name}' XSD schema in '{source_path}' "
                    "has xs:include without schemaLocation."
                )
            include_path = _resolve_local_contract_path(
                location=location,
                current_path=source_path,
                package_boundary=package_boundary,
                interface_name=interface_name,
            )
            if include_path in visited_includes:
                continue
            visited_includes.add(include_path)
            try:
                include_root, include_namespace_map = _parse_xml_with_namespaces(
                    include_path,
                    budget=parse_budget,
                )
            except ET.ParseError as exc:
                raise ValueError(
                    f"SOAP/WSDL interface '{interface_name}' could not parse included XSD "
                    f"'{include_path}': {exc}."
                ) from exc
            add_schema(
                include_root,
                namespace_map=include_namespace_map,
                source_path=include_path,
                expected_namespace=target_namespace,
            )

    for schema in root.findall(f"{WSDL}types/{XSD}schema"):
        add_schema(
            schema,
            namespace_map=namespace_map,
            source_path=wsdl_path,
        )

    if not schema_sources:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' must declare "
            "embedded XSD elements in wsdl:types."
        )

    catalog = _SchemaCatalog(
        elements=set(),
        element_definitions={},
        complex_types={},
        simple_types={},
    )
    for schema, _namespace_map, _source_path, target_namespace in schema_sources:
        for child in schema:
            local = _local_name(child.tag)
            name = child.attrib.get("name")
            if name:
                key = (target_namespace, name)
                if local == "element":
                    if key in catalog.elements:
                        raise ValueError(
                            f"SOAP/WSDL interface '{interface_name}' declares duplicate XSD "
                            f"element '{name}' in namespace '{target_namespace}'."
                        )
                    catalog.elements.add(key)
                    catalog.element_definitions[key] = (
                        child,
                        _namespace_map,
                        _source_path,
                        target_namespace,
                    )
                elif local == "complexType":
                    catalog.complex_types[key] = child
                elif local == "simpleType":
                    catalog.simple_types[key] = child

    if not catalog.elements:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' must declare "
            "embedded XSD elements in wsdl:types."
        )
    for schema, namespace_map, source_path, target_namespace in schema_sources:
        _reject_unsupported_xsd_constructs(
            schema,
            interface_name=interface_name,
            wsdl_path=wsdl_path,
            source_path=source_path,
        )
        for element in schema.findall(f"{XSD}element"):
            _validate_xsd_element(
                element,
                catalog=catalog,
                namespace_map=namespace_map,
                target_namespace=target_namespace,
                interface_name=interface_name,
                wsdl_path=wsdl_path,
                source_path=source_path,
                path=f"/{element.attrib.get('name', '<unnamed>')}",
                allow_complex=True,
            )
    return catalog


def _reject_unsupported_xsd_constructs(
    schema: ET.Element,
    *,
    interface_name: str,
    wsdl_path: Path,
    source_path: Path,
) -> None:
    for element in schema.iter():
        local = _local_name(element.tag)
        if local in UNSUPPORTED_XSD_ELEMENTS:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' XSD '{source_path}' from WSDL "
                f"'{wsdl_path}' uses unsupported xs:{local}."
            )
        if element.attrib.get("substitutionGroup"):
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' XSD '{source_path}' from WSDL "
                f"'{wsdl_path}' uses unsupported substitutionGroup."
            )
        if element.attrib.get("abstract") == "true":
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' XSD '{source_path}' from WSDL "
                f"'{wsdl_path}' uses unsupported abstract types."
            )
        if element.attrib.get("mixed") == "true":
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' XSD '{source_path}' from WSDL "
                f"'{wsdl_path}' uses unsupported mixed content."
            )


def _validate_schema_root(
    schema: ET.Element,
    *,
    interface_name: str,
    wsdl_path: Path,
    source_path: Path,
    expected_namespace: str | None,
) -> None:
    if schema.tag != f"{XSD}schema":
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' expected XSD schema root in '{source_path}'."
        )
    target_namespace = schema.attrib.get("targetNamespace")
    if expected_namespace is not None and target_namespace != expected_namespace:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' included XSD '{source_path}' targetNamespace "
            f"'{target_namespace}' does not match '{expected_namespace}' from WSDL '{wsdl_path}'."
        )


def _validate_xsd_element(
    element: ET.Element,
    *,
    catalog: _SchemaCatalog,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    interface_name: str,
    wsdl_path: Path,
    source_path: Path,
    path: str,
    allow_complex: bool,
) -> None:
    name = element.attrib.get("name")
    if not name:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' has an unnamed XSD element at '{path}' "
            f"in '{source_path}'."
        )
    min_occurs = _parse_occurs(element.attrib.get("minOccurs"), default=1, path=path)
    max_occurs_raw = element.attrib.get("maxOccurs")
    max_occurs = (
        None if max_occurs_raw == "unbounded" else _parse_occurs(max_occurs_raw, default=1, path=path)
    )
    if max_occurs is not None and min_occurs > max_occurs:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' element '{path}' has impossible "
            f"cardinality minOccurs={min_occurs} maxOccurs={max_occurs}."
        )
    inline_complex = element.find(f"{XSD}complexType")
    if inline_complex is not None:
        if not allow_complex:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' element '{path}' uses unsupported "
                "nested complex type."
            )
        _validate_complex_type(
            inline_complex,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=target_namespace,
            interface_name=interface_name,
            wsdl_path=wsdl_path,
            source_path=source_path,
            path=path,
        )
        return
    inline_simple = element.find(f"{XSD}simpleType")
    if inline_simple is not None:
        _validate_simple_type(
            inline_simple,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=target_namespace,
            interface_name=interface_name,
            source_path=source_path,
            path=path,
        )
        return
    type_name = element.attrib.get("type")
    if type_name is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' element '{path}' in '{source_path}' "
            "must declare a supported scalar type or complex sequence."
        )
    type_namespace, local_type = _resolve_xsd_qname(
        type_name,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name=interface_name,
        source_path=source_path,
        context=f"element '{path}' type",
    )
    if type_namespace == XSD_NAMESPACE:
        if local_type not in SUPPORTED_XSD_TYPES:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' element '{path}' uses unsupported "
                f"XSD type '{type_name}' in '{source_path}'."
            )
        return
    complex_type = catalog.complex_types.get((type_namespace, local_type))
    if complex_type is not None:
        if not allow_complex:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' element '{path}' uses unsupported "
                f"nested complex type '{type_name}'."
            )
        _validate_complex_type(
            complex_type,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=type_namespace,
            interface_name=interface_name,
            wsdl_path=wsdl_path,
            source_path=source_path,
            path=path,
        )
        return
    simple_type = catalog.simple_types.get((type_namespace, local_type))
    if simple_type is not None:
        _validate_simple_type(
            simple_type,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=type_namespace,
            interface_name=interface_name,
            source_path=source_path,
            path=path,
        )
        return
    raise ValueError(
        f"SOAP/WSDL interface '{interface_name}' element '{path}' references unsupported or "
        f"unknown XSD type '{type_name}' in '{source_path}'."
    )


def _validate_complex_type(
    complex_type: ET.Element,
    *,
    catalog: _SchemaCatalog,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    interface_name: str,
    wsdl_path: Path,
    source_path: Path,
    path: str,
) -> None:
    sequence = complex_type.find(f"{XSD}sequence")
    if sequence is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' complex type at '{path}' in '{source_path}' "
            "must use xs:sequence."
        )
    seen_children: set[str] = set()
    for child in sequence:
        if _local_name(child.tag) != "element":
            continue
        child_name = child.attrib.get("name")
        if child_name in seen_children:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' complex type at '{path}' declares "
                f"duplicate child element '{child_name}'."
            )
        if child_name:
            seen_children.add(child_name)
        _validate_xsd_element(
            child,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=target_namespace,
            interface_name=interface_name,
            wsdl_path=wsdl_path,
            source_path=source_path,
            path=f"{path}/{child_name or '<unnamed>'}",
            allow_complex=False,
        )
    seen_attributes: set[str] = set()
    for attribute in complex_type.findall(f"{XSD}attribute"):
        attribute_name = attribute.attrib.get("name")
        if attribute_name in seen_attributes:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' complex type at '{path}' declares "
                f"duplicate attribute '{attribute_name}'."
            )
        if attribute_name:
            seen_attributes.add(attribute_name)
        _validate_attribute(
            attribute,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=target_namespace,
            interface_name=interface_name,
            source_path=source_path,
            path=f"{path}/@{attribute_name or '<unnamed>'}",
        )


def _validate_attribute(
    attribute: ET.Element,
    *,
    catalog: _SchemaCatalog,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    interface_name: str,
    source_path: Path,
    path: str,
) -> None:
    if not attribute.attrib.get("name"):
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' has an unnamed XSD attribute at '{path}' "
            f"in '{source_path}'."
        )
    inline_simple = attribute.find(f"{XSD}simpleType")
    if inline_simple is not None:
        _validate_simple_type(
            inline_simple,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=target_namespace,
            interface_name=interface_name,
            source_path=source_path,
            path=path,
        )
        return
    type_name = attribute.attrib.get("type")
    if type_name is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' attribute '{path}' in '{source_path}' "
            "must declare a supported scalar type."
        )
    type_namespace, local_type = _resolve_xsd_qname(
        type_name,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name=interface_name,
        source_path=source_path,
        context=f"attribute '{path}' type",
    )
    if type_namespace == XSD_NAMESPACE:
        if local_type not in SUPPORTED_XSD_TYPES:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' attribute '{path}' uses unsupported "
                f"XSD type '{type_name}' in '{source_path}'."
            )
        return
    simple_type = catalog.simple_types.get((type_namespace, local_type))
    if simple_type is not None:
        _validate_simple_type(
            simple_type,
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=type_namespace,
            interface_name=interface_name,
            source_path=source_path,
            path=path,
        )
        return
    raise ValueError(
        f"SOAP/WSDL interface '{interface_name}' attribute '{path}' references unsupported or "
        f"unknown XSD type '{type_name}' in '{source_path}'."
    )


def _validate_simple_type(
    simple_type: ET.Element,
    *,
    catalog: _SchemaCatalog,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    interface_name: str,
    source_path: Path,
    path: str,
) -> None:
    restriction = simple_type.find(f"{XSD}restriction")
    if restriction is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' simple type at '{path}' in '{source_path}' "
            "must use xs:restriction."
        )
    base = restriction.attrib.get("base")
    if base is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' simple type at '{path}' in '{source_path}' "
            "is missing restriction base."
        )
    base_namespace, local_base = _resolve_xsd_qname(
        base,
        namespace_map=namespace_map,
        target_namespace=target_namespace,
        interface_name=interface_name,
        source_path=source_path,
        context=f"simple type '{path}' base",
    )
    if base_namespace == XSD_NAMESPACE:
        if local_base not in SUPPORTED_XSD_TYPES:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' simple type at '{path}' uses unsupported "
                f"restriction base '{base}' in '{source_path}'."
            )
    elif (base_namespace, local_base) in catalog.simple_types:
        _validate_simple_type(
            catalog.simple_types[(base_namespace, local_base)],
            catalog=catalog,
            namespace_map=namespace_map,
            target_namespace=base_namespace,
            interface_name=interface_name,
            source_path=source_path,
            path=path,
        )
    else:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' simple type at '{path}' references "
            f"unsupported restriction base '{base}' in '{source_path}'."
        )
    unsupported_facets = [
        _local_name(child.tag)
        for child in restriction
        if _local_name(child.tag) != "enumeration"
    ]
    if unsupported_facets:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' simple type at '{path}' uses unsupported "
            f"facet(s): {sorted(set(unsupported_facets))}."
        )


def _parse_occurs(value: str | None, *, default: int, path: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"SOAP/WSDL XSD element '{path}' has invalid occurs value '{value}'.") from exc
    if parsed < 0:
        raise ValueError(f"SOAP/WSDL XSD element '{path}' has negative occurs value '{value}'.")
    return parsed


def _reject_unsupported_wsdl_constructs(
    root: ET.Element,
    *,
    interface_name: str,
    wsdl_path: Path,
) -> None:
    if root.findall(f"{WSDL}import"):
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' uses unsupported "
            "wsdl:import."
        )
    for element in root.iter():
        local = _local_name(element.tag)
        namespace = _namespace_uri(element.tag).lower()
        if local in {"Policy", "PolicyReference"} or "policy" in namespace:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' uses unsupported "
                "WS-Policy."
            )
        if local in {"Security", "SecurityPolicy"} or "security" in namespace:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' uses unsupported "
                "WS-Security."
            )
        if "mime" in namespace:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' uses unsupported "
                "MIME/attachment constructs."
            )
        if local in {"addressing", "UsingAddressing"} or "addressing" in namespace:
            raise ValueError(
                f"SOAP/WSDL interface '{interface_name}' WSDL '{wsdl_path}' uses unsupported "
                "WS-Addressing."
            )


def _resolve_local_contract_path(
    *,
    location: str,
    current_path: Path,
    package_boundary: Path,
    interface_name: str,
) -> Path:
    raw_path = Path(location)
    candidate = raw_path if raw_path.is_absolute() else current_path.parent / raw_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(package_boundary)
    except ValueError as exc:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' referenced schema '{location}' in "
            f"'{current_path}' must stay within the manifest package."
        ) from exc
    return resolved


def _wsdl_source_paths(
    paths: tuple[Path, ...],
    *,
    wsdl_path: Path,
    source_wsdl_path: str | None,
    package_root: Path | None,
) -> tuple[str, ...]:
    if package_root is not None:
        package_boundary = package_root.resolve()
        source_paths: list[str] = []
        for path in paths:
            try:
                source_paths.append(path.resolve().relative_to(package_boundary).as_posix())
            except ValueError:
                source_paths.append(str(path))
        return tuple(source_paths)
    if source_wsdl_path is not None:
        return tuple(
            source_wsdl_path if path.resolve() == wsdl_path.resolve() else str(path)
            for path in paths
        )
    return tuple(str(path) for path in paths)


def _parse_xml_with_namespaces(
    path: Path,
    *,
    budget: XmlParseBudget,
) -> tuple[ET.Element, dict[str, str]]:
    root, prefixes = parse_untrusted_xml_with_namespaces(
        path,
        purpose=f"SOAP/WSDL contract file '{path}'",
        budget=budget,
    )
    namespace_map: dict[str, str] = {}
    for prefix, uri in prefixes:
        namespace_map[prefix] = uri
    return root, namespace_map


def _resolve_qname(
    value: str,
    *,
    namespace_map: dict[str, str],
    interface_name: str,
    wsdl_path: Path,
    context: str,
) -> tuple[str | None, str]:
    if ":" not in value:
        return None, value
    prefix, local = value.split(":", 1)
    namespace = namespace_map.get(prefix)
    if namespace is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' {context} references undeclared "
            f"namespace prefix '{prefix}' in '{wsdl_path}'."
        )
    return namespace, local


def _resolve_wsdl_qname(
    value: str,
    *,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    interface_name: str,
    wsdl_path: Path,
    context: str,
    allow_empty: bool = False,
) -> str:
    if not value:
        if allow_empty:
            return ""
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' {context} is missing a QName in "
            f"'{wsdl_path}'."
        )
    namespace, local = _resolve_qname(
        value,
        namespace_map=namespace_map,
        interface_name=interface_name,
        wsdl_path=wsdl_path,
        context=context,
    )
    # WSDL component references in this foundation only support same-document
    # services/messages/bindings/portTypes in the definitions target namespace.
    effective_namespace = namespace if namespace is not None else target_namespace
    if effective_namespace != target_namespace:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' {context} references QName '{value}' "
            f"outside WSDL targetNamespace '{target_namespace}' in '{wsdl_path}'."
        )
    return local


def _resolve_xsd_qname(
    value: str,
    *,
    namespace_map: dict[str, str],
    target_namespace: str | None,
    interface_name: str,
    source_path: Path,
    context: str,
) -> tuple[str | None, str]:
    if ":" not in value:
        return target_namespace, value
    prefix, local = value.split(":", 1)
    namespace = namespace_map.get(prefix)
    if namespace is None:
        raise ValueError(
            f"SOAP/WSDL interface '{interface_name}' {context} references undeclared "
            f"namespace prefix '{prefix}' in '{source_path}'."
        )
    return namespace, local


def _qname_local(value: str) -> str:
    return value.split(":", 1)[1] if ":" in value else value


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[1] if "}" in tag else tag


def _namespace_uri(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""
