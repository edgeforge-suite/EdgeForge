"""Design-time XML parser bounds (DTD/entity rejection, size and depth caps)."""

import shutil
from pathlib import Path

import pytest

from appbuilder.contracts.soap_contracts import load_soap_contract_spec
from appbuilder.contracts.xml_contracts import load_xml_contract_spec
from appbuilder.core.xml_safety import (
    MAX_BYTES_ENV,
    MAX_DEPTH_ENV,
    MAX_DOCUMENTS_ENV,
    MAX_TOTAL_BYTES_ENV,
    XmlSafetyError,
    parse_untrusted_xml,
    parse_untrusted_xml_with_namespaces,
)
from appbuilder.generation import generate_application
from appbuilder.metadata.translation import build_metadata_project

BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">&lol2;</xs:schema>
"""

EXTERNAL_ENTITY = """<?xml version="1.0"?>
<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">&xxe;</xs:schema>
"""

PLAIN_DOCTYPE = """<?xml version="1.0"?>
<!DOCTYPE xs:schema>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _insert_doctype(path: Path, root_name: str) -> None:
    content = path.read_text(encoding="utf-8")
    declaration_end = content.index("?>") + 2
    doctype = f'\n<!DOCTYPE {root_name} [ <!ENTITY marker "safe"> ]>'
    path.write_text(
        f"{content[:declaration_end]}{doctype}{content[declaration_end:]}",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("billion.xsd", BILLION_LAUGHS, "document type"),
        ("external.xsd", EXTERNAL_ENTITY, "document type"),
        ("doctype.xsd", PLAIN_DOCTYPE, "document type"),
    ],
)
def test_parse_untrusted_xml_rejects_dtds_and_entity_declarations(
    tmp_path: Path,
    name: str,
    content: str,
    expected: str,
) -> None:
    path = _write(tmp_path, name, content)

    with pytest.raises(XmlSafetyError) as excinfo:
        parse_untrusted_xml(path, purpose="test contract")

    assert expected in str(excinfo.value)
    assert "test contract" in str(excinfo.value)


def test_entity_expansion_is_blocked_before_any_expansion_occurs(tmp_path: Path) -> None:
    """The DTD is refused at declaration time, so no entity is ever expanded."""

    path = _write(tmp_path, "billion.xsd", BILLION_LAUGHS)

    with pytest.raises(XmlSafetyError, match="document type"):
        parse_untrusted_xml(path, purpose="test contract")


def test_parse_untrusted_xml_accepts_a_normal_schema(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "ok.xsd",
        '<?xml version="1.0"?>\n'
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:t">'
        '<xs:element name="A"/></xs:schema>\n',
    )

    root = parse_untrusted_xml(path, purpose="test contract")

    assert root.tag == "{http://www.w3.org/2001/XMLSchema}schema"
    assert root.attrib["targetNamespace"] == "urn:t"
    assert root[0].attrib["name"] == "A"


def test_namespace_pairs_are_returned_in_document_order(tmp_path: Path) -> None:
    """Callers keep their own precedence, so duplicates survive in order."""

    path = _write(
        tmp_path,
        "ns.xml",
        '<?xml version="1.0"?>\n'
        '<a xmlns="urn:default" xmlns:p="urn:one">'
        '<b xmlns:p="urn:two"/></a>\n',
    )

    root, prefixes = parse_untrusted_xml_with_namespaces(path, purpose="test contract")

    assert root.tag == "{urn:default}a"
    assert prefixes == [("", "urn:default"), ("p", "urn:one"), ("p", "urn:two")]


def test_oversize_documents_are_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(MAX_BYTES_ENV, "64")
    path = _write(
        tmp_path,
        "big.xsd",
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        + '<xs:element name="A"/>' * 20
        + "</xs:schema>",
    )

    with pytest.raises(XmlSafetyError) as excinfo:
        parse_untrusted_xml(path, purpose="test contract")

    assert "64-byte" in str(excinfo.value)
    assert MAX_BYTES_ENV in str(excinfo.value)


def test_xsd_include_bundle_rejects_aggregate_bytes(tmp_path: Path, monkeypatch) -> None:
    package_root = tmp_path / "pkg"
    contracts = package_root / "contracts"
    contracts.mkdir(parents=True)
    included = _write(
        contracts,
        "types.xsd",
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'targetNamespace="urn:test">'
        '<xs:simpleType name="Code"><xs:restriction base="xs:string"/></xs:simpleType>'
        "</xs:schema>",
    )
    root = _write(
        contracts,
        "root.xsd",
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'targetNamespace="urn:test">'
        '<xs:include schemaLocation="types.xsd"/>'
        '<xs:element name="Root" type="xs:string"/>'
        "</xs:schema>",
    )
    aggregate_size = root.stat().st_size + included.stat().st_size
    monkeypatch.setenv(MAX_TOTAL_BYTES_ENV, str(aggregate_size - 1))

    with pytest.raises(XmlSafetyError) as excinfo:
        load_xml_contract_spec(
            root,
            interface_name="bounded-xml",
            root_element="Root",
            package_root=package_root,
        )

    assert "aggregate XML parse limit" in str(excinfo.value)
    assert MAX_TOTAL_BYTES_ENV in str(excinfo.value)


def test_wsdl_include_bundle_rejects_document_count(tmp_path: Path, monkeypatch) -> None:
    package_root = tmp_path / "pkg"
    contracts = package_root / "contracts"
    contracts.mkdir(parents=True)
    _write(
        contracts,
        "types.xsd",
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'targetNamespace="urn:test"/>',
    )
    wsdl = _write(
        contracts,
        "service.wsdl",
        '<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" '
        'xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:test">'
        "<wsdl:types><xs:schema targetNamespace=\"urn:test\">"
        '<xs:include schemaLocation="types.xsd"/>'
        "</xs:schema></wsdl:types>"
        "</wsdl:definitions>",
    )
    monkeypatch.setenv(MAX_DOCUMENTS_ENV, "1")

    with pytest.raises(XmlSafetyError) as excinfo:
        load_soap_contract_spec(
            wsdl,
            interface_name="bounded-soap",
            package_root=package_root,
        )

    assert "1-document aggregate XML parse limit" in str(excinfo.value)
    assert MAX_DOCUMENTS_ENV in str(excinfo.value)


def test_over_deep_documents_are_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(MAX_DEPTH_ENV, "10")
    path = _write(tmp_path, "deep.xml", "<a>" * 50 + "</a>" * 50)

    with pytest.raises(XmlSafetyError) as excinfo:
        parse_untrusted_xml(path, purpose="test contract")

    assert "10-level" in str(excinfo.value)
    assert MAX_DEPTH_ENV in str(excinfo.value)


def test_depth_within_the_limit_is_accepted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(MAX_DEPTH_ENV, "10")
    path = _write(tmp_path, "shallow.xml", "<a>" * 10 + "</a>" * 10)

    assert parse_untrusted_xml(path, purpose="test contract").tag == "a"


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_invalid_bound_overrides_fail_fast(tmp_path: Path, monkeypatch, value: str) -> None:
    monkeypatch.setenv(MAX_DEPTH_ENV, value)
    path = _write(tmp_path, "ok.xml", "<a/>")

    with pytest.raises(XmlSafetyError) as excinfo:
        parse_untrusted_xml(path, purpose="test contract")

    assert MAX_DEPTH_ENV in str(excinfo.value)


@pytest.mark.parametrize("env_var", [MAX_TOTAL_BYTES_ENV, MAX_DOCUMENTS_ENV])
def test_invalid_aggregate_bound_overrides_fail_fast(
    tmp_path: Path,
    monkeypatch,
    env_var: str,
) -> None:
    monkeypatch.setenv(env_var, "invalid")
    path = _write(tmp_path, "ok.xml", "<a/>")

    with pytest.raises(XmlSafetyError) as excinfo:
        parse_untrusted_xml(path, purpose="test contract")

    assert env_var in str(excinfo.value)


def test_malformed_xml_still_raises_the_canonical_parse_error(tmp_path: Path) -> None:
    """Bounds must not swallow malformed input into a different error type."""

    from xml.etree import ElementTree as ET

    path = _write(tmp_path, "bad.xml", "<a><b></a>")

    with pytest.raises(ET.ParseError):
        parse_untrusted_xml(path, purpose="test contract")


def test_xsd_contract_loader_rejects_entity_expansion(tmp_path: Path) -> None:
    """The bound is wired into the real XSD loader, not just the helper."""

    package_root = tmp_path / "pkg"
    (package_root / "contracts").mkdir(parents=True)
    xsd_path = package_root / "contracts" / "customer.xsd"
    xsd_path.write_text(BILLION_LAUGHS, encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_xml_contract_spec(
            xsd_path,
            interface_name="customer-xml-input",
            root_element="CustomerMessage",
            source_xsd_path="contracts/customer.xsd",
            package_root=package_root,
        )

    message = str(excinfo.value)
    assert "document type" in message
    assert "customer-xml-input" in message


def test_wsdl_contract_loader_rejects_entity_expansion(tmp_path: Path) -> None:
    """The bound is wired into the real WSDL loader, not just the helper."""

    package_root = tmp_path / "pkg"
    (package_root / "contracts").mkdir(parents=True)
    wsdl_path = package_root / "contracts" / "service.wsdl"
    wsdl_path.write_text(
        '<?xml version="1.0"?>\n'
        "<!DOCTYPE definitions [ <!ENTITY boom \"boom\"> ]>\n"
        '<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"/>\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        load_soap_contract_spec(
            wsdl_path,
            interface_name="customer-soap-input",
            source_wsdl_path="contracts/service.wsdl",
            package_root=package_root,
        )

    assert "document type" in str(excinfo.value)


def test_generation_revalidates_xsd_after_metadata_translation(tmp_path: Path) -> None:
    source_fixture = Path("tests/fixtures/edgecontracts/xml-xsd/basic-customer")
    fixture = tmp_path / "xml-toctou"
    shutil.copytree(source_fixture, fixture)
    manifest = fixture / "app-definition.yaml"
    metadata = build_metadata_project(manifest)
    _insert_doctype(fixture / "contracts/customer.xsd", "xs:schema")
    output = tmp_path / "generated-xml"

    with pytest.raises(XmlSafetyError, match="document type"):
        generate_application(metadata, output, source_manifest=str(manifest))

    assert not (
        output
        / "src/main/resources/xml-contracts/customer-xml-input/contracts/customer.xsd"
    ).exists()


def test_generation_revalidates_wsdl_after_metadata_translation(tmp_path: Path) -> None:
    source_fixture = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/basic-inbound-customer-service"
    )
    fixture = tmp_path / "soap-toctou"
    shutil.copytree(source_fixture, fixture)
    manifest = fixture / "app-definition.yaml"
    metadata = build_metadata_project(manifest)
    _insert_doctype(
        fixture / "contracts/customer-service.wsdl",
        "wsdl:definitions",
    )
    output = tmp_path / "generated-soap"

    with pytest.raises(XmlSafetyError, match="document type"):
        generate_application(metadata, output, source_manifest=str(manifest))

    assert not (
        output
        / (
            "src/main/resources/soap-contracts/customer-soap-service/"
            "contracts/customer-service.wsdl"
        )
    ).exists()
