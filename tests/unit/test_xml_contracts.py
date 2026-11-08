from pathlib import Path

import pytest

from appbuilder.contracts.xml_contracts import load_xml_contract_spec


def test_xsd_parser_extracts_supported_elements_attributes_and_enums() -> None:
    xsd_path = Path("tests/fixtures/edgecontracts/xml-xsd/basic-customer/contracts/customer.xsd")

    contract = load_xml_contract_spec(
        xsd_path,
        interface_name="customer-xml-input",
        root_element="CustomerMessage",
        namespace="urn:edgeforge:examples:customer:v1",
        namespace_alias="cust",
        source_xsd_path="contracts/customer.xsd",
        package_root=Path("tests/fixtures/edgecontracts/xml-xsd/basic-customer"),
    )

    assert contract.namespace == "urn:edgeforge:examples:customer:v1"
    assert contract.namespace_alias == "cust"
    assert contract.xsd_path == "contracts/customer.xsd"
    assert contract.root_element == "CustomerMessage"
    fields = {field.name: field for field in contract.fields}
    assert fields["customerId"].type == "string"
    assert fields["customerId"].required is True
    assert fields["age"].type == "integer"
    assert fields["age"].required is False
    assert fields["balance"].type == "decimal"
    assert fields["active"].type == "boolean"
    assert fields["openedDate"].type == "date"
    assert fields["lastUpdatedAt"].type == "datetime"
    assert fields["lastUpdatedAt"].nillable is True
    assert fields["status"].enum_values == ("ACTIVE", "SUSPENDED")
    assert fields["alias"].repeated is True
    assert fields["alias"].max_occurs is None
    assert contract.attributes[0].name == "sourceSystem"
    assert contract.attributes[0].required is True
    assert contract.attributes[0].kind == "attribute"


def test_xsd_parser_supports_namespace_qualified_root_and_same_namespace_include() -> None:
    xsd_path = Path("tests/fixtures/edgecontracts/xml-xsd/order-with-attributes/contracts/order.xsd")

    contract = load_xml_contract_spec(
        xsd_path,
        interface_name="order-xml-output",
        root_element="ord:OrderMessage",
        namespace="urn:edgeforge:examples:order:v1",
    )

    fields = {field.name: field for field in contract.fields}
    assert contract.root_element == "OrderMessage"
    assert fields["currency"].enum_values == ("USD", "EUR")
    assert contract.attributes[0].name == "priority"
    assert contract.attributes[0].required is False


def test_xsd_parser_rejects_include_that_escapes_package(tmp_path: Path) -> None:
    contract_dir = tmp_path / "package" / "contracts"
    contract_dir.mkdir(parents=True)
    outside_xsd = tmp_path / "outside.xsd"
    outside_xsd.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>
""",
        encoding="utf-8",
    )
    xsd_path = contract_dir / "main.xsd"
    xsd_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:include schemaLocation="../../outside.xsd"/>
  <xs:element name="Root">
    <xs:complexType>
      <xs:sequence><xs:element name="value" type="xs:string"/></xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must stay within the manifest package"):
        load_xml_contract_spec(
            xsd_path,
            interface_name="escaping-include",
            root_element="Root",
            package_root=tmp_path / "package",
        )


def test_xsd_parser_rejects_absolute_include_path(tmp_path: Path) -> None:
    contract_dir = tmp_path / "package" / "contracts"
    contract_dir.mkdir(parents=True)
    outside_xsd = tmp_path / "outside.xsd"
    outside_xsd.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>
""",
        encoding="utf-8",
    )
    xsd_path = contract_dir / "main.xsd"
    xsd_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:include schemaLocation="{outside_xsd}"/>
  <xs:element name="Root">
    <xs:complexType>
      <xs:sequence><xs:element name="value" type="xs:string"/></xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must stay within the manifest package"):
        load_xml_contract_spec(
            xsd_path,
            interface_name="absolute-include",
            root_element="Root",
            package_root=tmp_path / "package",
        )


def test_xsd_parser_rejects_unknown_root_element() -> None:
    xsd_path = Path("tests/fixtures/edgecontracts/xml-xsd/basic-customer/contracts/customer.xsd")

    with pytest.raises(ValueError, match="root element 'MissingRoot' was not found"):
        load_xml_contract_spec(
            xsd_path,
            interface_name="customer-xml-input",
            root_element="MissingRoot",
        )


def test_xsd_parser_rejects_namespace_mismatch() -> None:
    xsd_path = Path("tests/fixtures/edgecontracts/xml-xsd/basic-customer/contracts/customer.xsd")

    with pytest.raises(ValueError, match="namespace 'urn:wrong' does not match"):
        load_xml_contract_spec(
            xsd_path,
            interface_name="customer-xml-input",
            root_element="CustomerMessage",
            namespace="urn:wrong",
        )


def test_xsd_parser_rejects_unsupported_choice() -> None:
    xsd_path = Path("tests/fixtures/edgecontracts/xml-xsd/unsupported-choice/contracts/choice.xsd")

    with pytest.raises(ValueError, match="unsupported xs:choice"):
        load_xml_contract_spec(
            xsd_path,
            interface_name="choice-xml-input",
            root_element="ChoiceMessage",
        )


@pytest.mark.parametrize(
    ("xsd_body", "expected"),
    [
        (
            """
            <xs:element name="BadRoot">
              <xs:complexType>
                <xs:all><xs:element name="a" type="xs:string"/></xs:all>
              </xs:complexType>
            </xs:element>
            """,
            "unsupported xs:all",
        ),
        (
            """
            <xs:element name="BadRoot">
              <xs:complexType>
                <xs:sequence><xs:any/></xs:sequence>
              </xs:complexType>
            </xs:element>
            """,
            "unsupported xs:any",
        ),
        (
            """
            <xs:import namespace="urn:other" schemaLocation="other.xsd"/>
            <xs:element name="BadRoot" type="xs:string"/>
            """,
            "unsupported xs:import",
        ),
    ],
)
def test_xsd_parser_rejects_unsupported_constructs(
    tmp_path: Path,
    xsd_body: str,
    expected: str,
) -> None:
    xsd_path = tmp_path / "bad.xsd"
    xsd_path.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">',
                xsd_body,
                "</xs:schema>",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=expected):
        load_xml_contract_spec(xsd_path, interface_name="bad-xml", root_element="BadRoot")


def test_xsd_parser_rejects_nested_complex_child(tmp_path: Path) -> None:
    nested_path = tmp_path / "nested.xsd"
    nested_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="NestedRoot">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="nested">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="value" type="xs:string"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported nested complex type"):
        load_xml_contract_spec(
            nested_path,
            interface_name="nested-xml",
            root_element="NestedRoot",
        )


def test_xsd_parser_rejects_duplicate_child_elements(tmp_path: Path) -> None:
    xsd_path = tmp_path / "duplicate.xsd"
    xsd_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="DuplicateRoot">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="value" type="xs:string"/>
        <xs:element name="value" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate child element 'value'"):
        load_xml_contract_spec(
            xsd_path,
            interface_name="duplicate-xml",
            root_element="DuplicateRoot",
        )


def test_xsd_parser_rejects_impossible_bounded_cardinality(tmp_path: Path) -> None:
    xsd_path = tmp_path / "cardinality.xsd"
    xsd_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="CardinalityRoot">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="value" type="xs:string" minOccurs="2" maxOccurs="1"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="impossible cardinality minOccurs=2 maxOccurs=1"):
        load_xml_contract_spec(
            xsd_path,
            interface_name="cardinality-xml",
            root_element="CardinalityRoot",
        )
