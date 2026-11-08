"""Deterministic XML/XSD contract parsing for EdgeForge manifests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from appbuilder.core.xml_safety import XmlParseBudget, parse_untrusted_xml

XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
XSD = f"{{{XSD_NAMESPACE}}}"
SUPPORTED_XSD_TYPES = {
    "string": "string",
    "int": "integer",
    "integer": "integer",
    "long": "long",
    "decimal": "decimal",
    "boolean": "boolean",
    "date": "date",
    "dateTime": "datetime",
}
UNSUPPORTED_XSD_ELEMENTS = {
    "choice",
    "all",
    "any",
    "anyAttribute",
    "import",
    "list",
    "union",
}


@dataclass(frozen=True)
class XmlContractField:
    name: str
    kind: str
    type: str
    xsd_type: str
    required: bool
    repeated: bool = False
    max_occurs: int | None = 1
    nillable: bool = False
    enum_values: tuple[str, ...] = ()
    xsd_path: str = ""


@dataclass(frozen=True)
class XmlContractSpec:
    interface_name: str
    xsd_path: str
    xsd_paths: tuple[str, ...]
    namespace: str | None
    namespace_alias: str | None
    root_element: str
    fields: tuple[XmlContractField, ...]
    attributes: tuple[XmlContractField, ...]

    def to_metadata(self) -> dict[str, Any]:
        """Return a JSON-serializable XML contract payload."""

        return asdict(self)


def load_xml_contract_spec(
    xsd_path: Path,
    *,
    interface_name: str,
    root_element: str,
    namespace: str | None = None,
    namespace_alias: str | None = None,
    source_xsd_path: str | None = None,
    package_root: Path | None = None,
) -> XmlContractSpec:
    """Load and validate a supported XML/XSD v1 contract."""

    if not root_element or not root_element.strip():
        raise ValueError(f"XML/XSD interface '{interface_name}' requires root_element.")
    schema = _load_schema_bundle(
        xsd_path=xsd_path,
        interface_name=interface_name,
        package_root=package_root,
    )
    target_namespace = schema.target_namespace
    if namespace is not None and namespace != target_namespace:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' namespace '{namespace}' does not match "
            f"XSD targetNamespace '{target_namespace}' in {xsd_path}."
        )
    selected_root = _strip_namespace_prefix(root_element)
    root = schema.elements.get(selected_root)
    if root is None:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' root element '{selected_root}' was not found "
            f"in XSD '{xsd_path}'."
        )
    fields, attributes = _parse_root_element(
        schema=schema,
        root=root,
        interface_name=interface_name,
        xsd_path=xsd_path,
        root_name=selected_root,
    )
    return XmlContractSpec(
        interface_name=interface_name,
        xsd_path=source_xsd_path or str(xsd_path),
        xsd_paths=_schema_source_paths(
            schema.paths,
            xsd_path=xsd_path,
            source_xsd_path=source_xsd_path,
            package_root=package_root,
        ),
        namespace=target_namespace,
        namespace_alias=namespace_alias,
        root_element=selected_root,
        fields=tuple(fields),
        attributes=tuple(attributes),
    )


@dataclass
class _SchemaBundle:
    target_namespace: str | None
    elements: dict[str, ET.Element]
    complex_types: dict[str, ET.Element]
    simple_types: dict[str, ET.Element]
    paths: tuple[Path, ...]


def _load_schema_bundle(
    *,
    xsd_path: Path,
    interface_name: str,
    package_root: Path | None,
) -> _SchemaBundle:
    if not xsd_path.exists():
        raise ValueError(
            f"XML/XSD interface '{interface_name}' references missing XSD '{xsd_path}'."
        )
    package_boundary = (package_root or xsd_path.parent).resolve()
    visited: set[Path] = set()
    elements: dict[str, ET.Element] = {}
    complex_types: dict[str, ET.Element] = {}
    simple_types: dict[str, ET.Element] = {}
    target_namespace: str | None = None
    parse_budget = XmlParseBudget()

    def visit(path: Path) -> None:
        nonlocal target_namespace
        resolved = path.resolve()
        if resolved in visited:
            return
        visited.add(resolved)
        try:
            root = parse_untrusted_xml(
                path,
                purpose=f"XML/XSD interface '{interface_name}' XSD '{path}'",
                budget=parse_budget,
            )
        except ET.ParseError as exc:
            raise ValueError(
                f"XML/XSD interface '{interface_name}' could not parse XSD '{path}': {exc}."
            ) from exc
        if root.tag != f"{XSD}schema":
            raise ValueError(
                f"XML/XSD interface '{interface_name}' expected XSD schema root in '{path}'."
            )
        schema_namespace = root.attrib.get("targetNamespace")
        if target_namespace is None:
            target_namespace = schema_namespace
        elif schema_namespace != target_namespace:
            raise ValueError(
                f"XML/XSD interface '{interface_name}' include '{path}' targetNamespace "
                f"'{schema_namespace}' does not match '{target_namespace}'."
            )
        _reject_unsupported_constructs(root, interface_name=interface_name, xsd_path=path)
        for include in root.findall(f"{XSD}include"):
            location = include.attrib.get("schemaLocation")
            if not location:
                raise ValueError(
                    f"XML/XSD interface '{interface_name}' XSD '{path}' has xs:include without schemaLocation."
                )
            include_path = _resolve_include_path(
                include_location=location,
                current_xsd=path,
                package_boundary=package_boundary,
                interface_name=interface_name,
            )
            visit(include_path)
        for child in root:
            local = _local_name(child.tag)
            name = child.attrib.get("name")
            if not name:
                continue
            if local == "element":
                elements[name] = child
            elif local == "complexType":
                complex_types[name] = child
            elif local == "simpleType":
                simple_types[name] = child

    visit(xsd_path)
    return _SchemaBundle(
        target_namespace=target_namespace,
        elements=elements,
        complex_types=complex_types,
        simple_types=simple_types,
        paths=tuple(sorted(visited, key=lambda path: path.as_posix())),
    )


def _reject_unsupported_constructs(
    root: ET.Element,
    *,
    interface_name: str,
    xsd_path: Path,
) -> None:
    for element in root.iter():
        local = _local_name(element.tag)
        if local in UNSUPPORTED_XSD_ELEMENTS:
            raise ValueError(
                f"XML/XSD interface '{interface_name}' XSD '{xsd_path}' uses unsupported "
                f"xs:{local}."
            )
        if element.attrib.get("substitutionGroup"):
            raise ValueError(
                f"XML/XSD interface '{interface_name}' XSD '{xsd_path}' uses unsupported substitutionGroup."
            )
        if element.attrib.get("abstract") == "true":
            raise ValueError(
                f"XML/XSD interface '{interface_name}' XSD '{xsd_path}' uses unsupported abstract types."
            )
        if element.attrib.get("mixed") == "true":
            raise ValueError(
                f"XML/XSD interface '{interface_name}' XSD '{xsd_path}' uses unsupported mixed content."
            )


def _resolve_include_path(
    *,
    include_location: str,
    current_xsd: Path,
    package_boundary: Path,
    interface_name: str,
) -> Path:
    raw_path = Path(include_location)
    candidate = raw_path if raw_path.is_absolute() else current_xsd.parent / raw_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(package_boundary)
    except ValueError as exc:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' xs:include '{include_location}' in "
            f"'{current_xsd}' must stay within the manifest package."
        ) from exc
    return resolved


def _schema_source_paths(
    paths: tuple[Path, ...],
    *,
    xsd_path: Path,
    source_xsd_path: str | None,
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
    if source_xsd_path is not None:
        return tuple(
            source_xsd_path if path.resolve() == xsd_path.resolve() else str(path)
            for path in paths
        )
    return tuple(str(path) for path in paths)


def _parse_root_element(
    *,
    schema: _SchemaBundle,
    root: ET.Element,
    interface_name: str,
    xsd_path: Path,
    root_name: str,
) -> tuple[list[XmlContractField], list[XmlContractField]]:
    complex_type = _resolve_complex_type(
        schema=schema,
        element=root,
        interface_name=interface_name,
        xsd_path=xsd_path,
        path=f"/{root_name}",
    )
    sequence = complex_type.find(f"{XSD}sequence")
    if sequence is None:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' root element '{root_name}' must use xs:sequence."
        )
    fields: list[XmlContractField] = []
    attributes: list[XmlContractField] = []
    seen_fields: set[str] = set()
    for child in sequence:
        if _local_name(child.tag) != "element":
            continue
        child_name = child.attrib.get("name")
        if child_name in seen_fields:
            raise ValueError(
                f"XML/XSD interface '{interface_name}' root element '{root_name}' declares "
                f"duplicate child element '{child_name}'."
            )
        if child_name:
            seen_fields.add(child_name)
        fields.append(
            _parse_field(
                schema=schema,
                element=child,
                interface_name=interface_name,
                xsd_path=xsd_path,
                root_name=root_name,
            )
        )
    seen_attributes: set[str] = set()
    for attribute in complex_type.findall(f"{XSD}attribute"):
        attribute_name = attribute.attrib.get("name")
        if attribute_name in seen_attributes:
            raise ValueError(
                f"XML/XSD interface '{interface_name}' root element '{root_name}' declares "
                f"duplicate attribute '{attribute_name}'."
            )
        if attribute_name:
            seen_attributes.add(attribute_name)
        attributes.append(
            _parse_attribute(
                schema=schema,
                attribute=attribute,
                interface_name=interface_name,
                xsd_path=xsd_path,
                root_name=root_name,
            )
        )
    return fields, attributes


def _resolve_complex_type(
    *,
    schema: _SchemaBundle,
    element: ET.Element,
    interface_name: str,
    xsd_path: Path,
    path: str,
) -> ET.Element:
    type_name = element.attrib.get("type")
    inline_complex = element.find(f"{XSD}complexType")
    if inline_complex is not None:
        return inline_complex
    if type_name is None:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' element '{path}' must declare a complex type."
        )
    local_type = _strip_namespace_prefix(type_name)
    complex_type = schema.complex_types.get(local_type)
    if complex_type is None:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' element '{path}' references unknown "
            f"complex type '{type_name}' in XSD '{xsd_path}'."
        )
    return complex_type


def _parse_field(
    *,
    schema: _SchemaBundle,
    element: ET.Element,
    interface_name: str,
    xsd_path: Path,
    root_name: str,
) -> XmlContractField:
    name = element.attrib.get("name")
    if not name:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' has an unnamed child element in XSD '{xsd_path}'."
        )
    if element.find(f"{XSD}complexType") is not None:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' element '/{root_name}/{name}' uses unsupported "
            "nested complex type."
        )
    xsd_type, canonical_type, enum_values = _resolve_scalar_type(
        schema=schema,
        element=element,
        interface_name=interface_name,
        xsd_path=xsd_path,
        path=f"/{root_name}/{name}",
    )
    min_occurs = _parse_occurs(element.attrib.get("minOccurs"), default=1, field_name=name)
    max_occurs_raw = element.attrib.get("maxOccurs")
    max_occurs = None if max_occurs_raw == "unbounded" else _parse_occurs(max_occurs_raw, default=1, field_name=name)
    if max_occurs is not None and min_occurs > max_occurs:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' element '/{root_name}/{name}' has impossible "
            f"cardinality minOccurs={min_occurs} maxOccurs={max_occurs}."
        )
    return XmlContractField(
        name=name,
        kind="element",
        type=canonical_type,
        xsd_type=xsd_type,
        required=min_occurs > 0,
        repeated=max_occurs is None or max_occurs > 1,
        max_occurs=max_occurs,
        nillable=element.attrib.get("nillable") == "true",
        enum_values=enum_values,
        xsd_path=f"/{root_name}/{name}",
    )


def _parse_attribute(
    *,
    schema: _SchemaBundle,
    attribute: ET.Element,
    interface_name: str,
    xsd_path: Path,
    root_name: str,
) -> XmlContractField:
    name = attribute.attrib.get("name")
    if not name:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' has an unnamed attribute in XSD '{xsd_path}'."
        )
    xsd_type, canonical_type, enum_values = _resolve_scalar_type(
        schema=schema,
        element=attribute,
        interface_name=interface_name,
        xsd_path=xsd_path,
        path=f"/{root_name}/@{name}",
    )
    return XmlContractField(
        name=name,
        kind="attribute",
        type=canonical_type,
        xsd_type=xsd_type,
        required=attribute.attrib.get("use") == "required",
        enum_values=enum_values,
        xsd_path=f"/{root_name}/@{name}",
    )


def _resolve_scalar_type(
    *,
    schema: _SchemaBundle,
    element: ET.Element,
    interface_name: str,
    xsd_path: Path,
    path: str,
) -> tuple[str, str, tuple[str, ...]]:
    inline_simple = element.find(f"{XSD}simpleType")
    if inline_simple is not None:
        return _parse_simple_type(
            schema=schema,
            simple_type=inline_simple,
            interface_name=interface_name,
            xsd_path=xsd_path,
            path=path,
        )
    type_name = element.attrib.get("type")
    if type_name is None:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' element '{path}' must declare a scalar type."
        )
    local_type = _strip_namespace_prefix(type_name)
    if local_type in schema.complex_types:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' element '{path}' uses unsupported nested "
            f"complex type '{type_name}'."
        )
    if local_type in schema.simple_types:
        return _parse_simple_type(
            schema=schema,
            simple_type=schema.simple_types[local_type],
            interface_name=interface_name,
            xsd_path=xsd_path,
            path=path,
            named_type=local_type,
        )
    canonical = SUPPORTED_XSD_TYPES.get(local_type)
    if canonical is None:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' element '{path}' uses unsupported XSD type "
            f"'{type_name}' in '{xsd_path}'."
        )
    return local_type, canonical, ()


def _parse_simple_type(
    *,
    schema: _SchemaBundle,
    simple_type: ET.Element,
    interface_name: str,
    xsd_path: Path,
    path: str,
    named_type: str | None = None,
) -> tuple[str, str, tuple[str, ...]]:
    restriction = simple_type.find(f"{XSD}restriction")
    if restriction is None:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' simple type at '{path}' must use xs:restriction."
        )
    base = restriction.attrib.get("base")
    if base is None:
        raise ValueError(
            f"XML/XSD interface '{interface_name}' simple type at '{path}' is missing restriction base."
        )
    local_base = _strip_namespace_prefix(base)
    canonical = SUPPORTED_XSD_TYPES.get(local_base)
    if canonical is None:
        if local_base in schema.simple_types:
            return _parse_simple_type(
                schema=schema,
                simple_type=schema.simple_types[local_base],
                interface_name=interface_name,
                xsd_path=xsd_path,
                path=path,
                named_type=local_base,
            )
        raise ValueError(
            f"XML/XSD interface '{interface_name}' simple type at '{path}' uses unsupported "
            f"restriction base '{base}'."
        )
    enum_values = tuple(
        enum.attrib["value"]
        for enum in restriction.findall(f"{XSD}enumeration")
        if enum.attrib.get("value") is not None
    )
    if len(list(restriction)) != len(enum_values):
        unsupported_facets = [
            _local_name(child.tag)
            for child in restriction
            if _local_name(child.tag) != "enumeration"
        ]
        if unsupported_facets:
            raise ValueError(
                f"XML/XSD interface '{interface_name}' simple type at '{path}' uses unsupported "
                f"facet(s): {sorted(set(unsupported_facets))}."
            )
    return named_type or local_base, canonical, enum_values


def _parse_occurs(value: str | None, *, default: int, field_name: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"XML/XSD field '{field_name}' has invalid occurs value '{value}'.") from exc
    if parsed < 0:
        raise ValueError(f"XML/XSD field '{field_name}' has negative occurs value '{value}'.")
    return parsed


def _strip_namespace_prefix(value: str) -> str:
    return value.split(":", 1)[1] if ":" in value else value


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[1] if "}" in tag else tag
