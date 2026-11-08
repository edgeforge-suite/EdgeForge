from pathlib import Path

import pytest

from appbuilder.contracts.soap_contracts import load_soap_contract_spec


def test_soap_wsdl_parser_loads_document_literal_wrapped_contract() -> None:
    wsdl = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/basic-customer-service/contracts/customer-service.wsdl"
    )

    spec = load_soap_contract_spec(
        wsdl,
        interface_name="customer-soap-service",
        service="CustomerService",
        port="CustomerServicePort",
        source_wsdl_path="contracts/customer-service.wsdl",
        package_root=wsdl.parents[1],
    )

    assert spec.wsdl_path == "contracts/customer-service.wsdl"
    assert spec.wsdl_paths == ("contracts/customer-service.wsdl",)
    assert spec.target_namespace == "urn:edgeforge:examples:customer-soap:v1"
    assert spec.service == "CustomerService"
    assert spec.port == "CustomerServicePort"
    assert spec.binding == "CustomerSoapBinding"
    assert len(spec.operations) == 1
    operation = spec.operations[0]
    assert operation.name == "getCustomer"
    assert operation.soap_action == "urn:getCustomer"
    assert operation.input_message == "GetCustomerRequestMessage"
    assert operation.output_message == "GetCustomerResponseMessage"
    assert operation.input_element == "tns:GetCustomerRequest"
    assert operation.output_element == "tns:GetCustomerResponse"
    assert operation.faults[0].element == "tns:CustomerFault"


def test_soap_wsdl_parser_requires_explicit_port_when_ambiguous() -> None:
    wsdl = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/ambiguous-bindings/contracts/ambiguous.wsdl"
    )

    with pytest.raises(ValueError, match="declares multiple ports; specify port"):
        load_soap_contract_spec(
            wsdl,
            interface_name="ambiguous-soap",
            service="AmbiguousService",
            package_root=wsdl.parents[1],
        )


def test_soap_wsdl_parser_rejects_missing_operation() -> None:
    wsdl = Path(
        "tests/fixtures/edgecontracts/soap-wsdl/basic-customer-service/contracts/customer-service.wsdl"
    )

    with pytest.raises(ValueError, match="requested operation 'missingOperation' was not found"):
        load_soap_contract_spec(
            wsdl,
            interface_name="customer-soap-service",
            service="CustomerService",
            port="CustomerServicePort",
            operation_names=("missingOperation",),
            package_root=wsdl.parents[1],
        )


def test_soap_wsdl_parser_rejects_rpc_encoded_binding() -> None:
    wsdl = Path("tests/fixtures/edgecontracts/soap-wsdl/unsupported-rpc-encoded/contracts/rpc.wsdl")

    with pytest.raises(ValueError, match="unsupported SOAP style 'rpc'"):
        load_soap_contract_spec(
            wsdl,
            interface_name="rpc-soap",
            package_root=wsdl.parents[1],
        )


def test_soap_wsdl_parser_rejects_unsupported_policy() -> None:
    wsdl = Path("tests/fixtures/edgecontracts/soap-wsdl/policy/contracts/policy.wsdl")

    with pytest.raises(ValueError, match="unsupported WS-Policy"):
        load_soap_contract_spec(
            wsdl,
            interface_name="policy-soap",
            package_root=wsdl.parents[1],
        )


def test_soap_wsdl_parser_rejects_unsupported_inherited_xsd_feature() -> None:
    wsdl = Path("tests/fixtures/edgecontracts/soap-wsdl/unsupported-choice/contracts/choice.wsdl")

    with pytest.raises(ValueError, match="unsupported xs:choice"):
        load_soap_contract_spec(
            wsdl,
            interface_name="choice-soap",
            package_root=wsdl.parents[1],
        )


def test_soap_wsdl_parser_validates_only_manifest_selected_binding(tmp_path: Path) -> None:
    wsdl = tmp_path / "mixed.wsdl"
    wsdl.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  xmlns:xs="http://www.w3.org/2001/XMLSchema"
                  xmlns:tns="urn:example:mixed"
                  targetNamespace="urn:example:mixed">
  <wsdl:types>
    <xs:schema targetNamespace="urn:example:mixed" xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Request" type="xs:string"/>
      <xs:element name="Response" type="xs:string"/>
    </xs:schema>
  </wsdl:types>
  <wsdl:message name="RequestMessage"><wsdl:part name="parameters" element="tns:Request"/></wsdl:message>
  <wsdl:message name="ResponseMessage"><wsdl:part name="parameters" element="tns:Response"/></wsdl:message>
  <wsdl:portType name="PortType">
    <wsdl:operation name="call"><wsdl:input message="tns:RequestMessage"/><wsdl:output message="tns:ResponseMessage"/></wsdl:operation>
  </wsdl:portType>
  <wsdl:binding name="SelectedBinding" type="tns:PortType">
    <soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="call"><soap:operation soapAction="urn:call"/><wsdl:input><soap:body use="literal"/></wsdl:input><wsdl:output><soap:body use="literal"/></wsdl:output></wsdl:operation>
  </wsdl:binding>
  <wsdl:binding name="UnselectedRpcBinding" type="tns:PortType">
    <soap:binding style="rpc" transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="call"><soap:operation soapAction="urn:rpc" style="rpc"/><wsdl:input><soap:body use="encoded"/></wsdl:input><wsdl:output><soap:body use="encoded"/></wsdl:output></wsdl:operation>
  </wsdl:binding>
  <wsdl:service name="MixedService">
    <wsdl:port name="SelectedPort" binding="tns:SelectedBinding"><soap:address location="https://example.invalid/selected"/></wsdl:port>
    <wsdl:port name="RpcPort" binding="tns:UnselectedRpcBinding"><soap:address location="https://example.invalid/rpc"/></wsdl:port>
  </wsdl:service>
</wsdl:definitions>
""",
        encoding="utf-8",
    )

    spec = load_soap_contract_spec(
        wsdl,
        interface_name="mixed-soap",
        service="MixedService",
        port="SelectedPort",
        binding="SelectedBinding",
        package_root=tmp_path,
    )

    assert spec.binding == "SelectedBinding"
    assert spec.operations[0].name == "call"


def test_soap_wsdl_parser_rejects_unsupported_scalar_type(tmp_path: Path) -> None:
    wsdl = tmp_path / "binary.wsdl"
    wsdl.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  xmlns:xs="http://www.w3.org/2001/XMLSchema"
                  xmlns:tns="urn:example:binary"
                  targetNamespace="urn:example:binary">
  <wsdl:types>
    <xs:schema targetNamespace="urn:example:binary" xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Request" type="xs:base64Binary"/>
      <xs:element name="Response" type="xs:string"/>
    </xs:schema>
  </wsdl:types>
  <wsdl:message name="RequestMessage"><wsdl:part name="parameters" element="tns:Request"/></wsdl:message>
  <wsdl:message name="ResponseMessage"><wsdl:part name="parameters" element="tns:Response"/></wsdl:message>
  <wsdl:portType name="PortType"><wsdl:operation name="call"><wsdl:input message="tns:RequestMessage"/><wsdl:output message="tns:ResponseMessage"/></wsdl:operation></wsdl:portType>
  <wsdl:binding name="Binding" type="tns:PortType"><soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/><wsdl:operation name="call"><soap:operation soapAction="urn:call"/><wsdl:input><soap:body use="literal"/></wsdl:input><wsdl:output><soap:body use="literal"/></wsdl:output></wsdl:operation></wsdl:binding>
  <wsdl:service name="Service"><wsdl:port name="Port" binding="tns:Binding"><soap:address location="https://example.invalid"/></wsdl:port></wsdl:service>
</wsdl:definitions>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported XSD type 'xs:base64Binary'"):
        load_soap_contract_spec(wsdl, interface_name="binary-soap", package_root=tmp_path)


def test_soap_wsdl_parser_rejects_unsupported_construct_in_included_xsd(tmp_path: Path) -> None:
    (tmp_path / "common.xsd").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:include">
  <xs:element name="Request">
    <xs:complexType>
      <xs:choice>
        <xs:element name="a" type="xs:string"/>
        <xs:element name="b" type="xs:string"/>
      </xs:choice>
    </xs:complexType>
  </xs:element>
</xs:schema>
""",
        encoding="utf-8",
    )
    wsdl = tmp_path / "include.wsdl"
    wsdl.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  xmlns:xs="http://www.w3.org/2001/XMLSchema"
                  xmlns:tns="urn:example:include"
                  targetNamespace="urn:example:include">
  <wsdl:types>
    <xs:schema targetNamespace="urn:example:include" xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:include schemaLocation="common.xsd"/>
      <xs:element name="Response" type="xs:string"/>
    </xs:schema>
  </wsdl:types>
  <wsdl:message name="RequestMessage"><wsdl:part name="parameters" element="tns:Request"/></wsdl:message>
  <wsdl:message name="ResponseMessage"><wsdl:part name="parameters" element="tns:Response"/></wsdl:message>
  <wsdl:portType name="PortType"><wsdl:operation name="call"><wsdl:input message="tns:RequestMessage"/><wsdl:output message="tns:ResponseMessage"/></wsdl:operation></wsdl:portType>
  <wsdl:binding name="Binding" type="tns:PortType"><soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/><wsdl:operation name="call"><soap:operation soapAction="urn:call"/><wsdl:input><soap:body use="literal"/></wsdl:input><wsdl:output><soap:body use="literal"/></wsdl:output></wsdl:operation></wsdl:binding>
  <wsdl:service name="Service"><wsdl:port name="Port" binding="tns:Binding"><soap:address location="https://example.invalid"/></wsdl:port></wsdl:service>
</wsdl:definitions>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported xs:choice"):
        load_soap_contract_spec(wsdl, interface_name="include-soap", package_root=tmp_path)


def test_soap_wsdl_parser_rejects_message_element_with_wrong_namespace(tmp_path: Path) -> None:
    wsdl = tmp_path / "wrong-namespace.wsdl"
    wsdl.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  xmlns:xs="http://www.w3.org/2001/XMLSchema"
                  xmlns:tns="urn:example:correct"
                  xmlns:other="urn:example:other"
                  targetNamespace="urn:example:correct">
  <wsdl:types>
    <xs:schema targetNamespace="urn:example:correct" xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Request" type="xs:string"/>
      <xs:element name="Response" type="xs:string"/>
    </xs:schema>
  </wsdl:types>
  <wsdl:message name="RequestMessage"><wsdl:part name="parameters" element="other:Request"/></wsdl:message>
  <wsdl:message name="ResponseMessage"><wsdl:part name="parameters" element="tns:Response"/></wsdl:message>
  <wsdl:portType name="PortType"><wsdl:operation name="call"><wsdl:input message="tns:RequestMessage"/><wsdl:output message="tns:ResponseMessage"/></wsdl:operation></wsdl:portType>
  <wsdl:binding name="Binding" type="tns:PortType"><soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/><wsdl:operation name="call"><soap:operation soapAction="urn:call"/><wsdl:input><soap:body use="literal"/></wsdl:input><wsdl:output><soap:body use="literal"/></wsdl:output></wsdl:operation></wsdl:binding>
  <wsdl:service name="Service"><wsdl:port name="Port" binding="tns:Binding"><soap:address location="https://example.invalid"/></wsdl:port></wsdl:service>
</wsdl:definitions>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="references unknown XSD element 'other:Request'"):
        load_soap_contract_spec(wsdl, interface_name="wrong-namespace-soap", package_root=tmp_path)


def test_soap_wsdl_parser_rejects_port_type_message_ref_with_wrong_namespace(
    tmp_path: Path,
) -> None:
    wsdl = tmp_path / "wrong-message-namespace.wsdl"
    wsdl.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  xmlns:xs="http://www.w3.org/2001/XMLSchema"
                  xmlns:tns="urn:example:correct"
                  xmlns:other="urn:example:other"
                  targetNamespace="urn:example:correct">
  <wsdl:types>
    <xs:schema targetNamespace="urn:example:correct" xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Request" type="xs:string"/>
      <xs:element name="Response" type="xs:string"/>
    </xs:schema>
  </wsdl:types>
  <wsdl:message name="RequestMessage"><wsdl:part name="parameters" element="tns:Request"/></wsdl:message>
  <wsdl:message name="ResponseMessage"><wsdl:part name="parameters" element="tns:Response"/></wsdl:message>
  <wsdl:portType name="PortType"><wsdl:operation name="call"><wsdl:input message="other:RequestMessage"/><wsdl:output message="tns:ResponseMessage"/></wsdl:operation></wsdl:portType>
  <wsdl:binding name="Binding" type="tns:PortType"><soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/><wsdl:operation name="call"><soap:operation soapAction="urn:call"/><wsdl:input><soap:body use="literal"/></wsdl:input><wsdl:output><soap:body use="literal"/></wsdl:output></wsdl:operation></wsdl:binding>
  <wsdl:service name="Service"><wsdl:port name="Port" binding="tns:Binding"><soap:address location="https://example.invalid"/></wsdl:port></wsdl:service>
</wsdl:definitions>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="input message references QName 'other:RequestMessage'"):
        load_soap_contract_spec(wsdl, interface_name="wrong-message-soap", package_root=tmp_path)


def test_soap_wsdl_parser_rejects_binding_type_with_wrong_namespace(tmp_path: Path) -> None:
    wsdl = tmp_path / "wrong-binding-type-namespace.wsdl"
    wsdl.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  xmlns:xs="http://www.w3.org/2001/XMLSchema"
                  xmlns:tns="urn:example:correct"
                  xmlns:other="urn:example:other"
                  targetNamespace="urn:example:correct">
  <wsdl:types>
    <xs:schema targetNamespace="urn:example:correct" xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Request" type="xs:string"/>
      <xs:element name="Response" type="xs:string"/>
    </xs:schema>
  </wsdl:types>
  <wsdl:message name="RequestMessage"><wsdl:part name="parameters" element="tns:Request"/></wsdl:message>
  <wsdl:message name="ResponseMessage"><wsdl:part name="parameters" element="tns:Response"/></wsdl:message>
  <wsdl:portType name="PortType"><wsdl:operation name="call"><wsdl:input message="tns:RequestMessage"/><wsdl:output message="tns:ResponseMessage"/></wsdl:operation></wsdl:portType>
  <wsdl:binding name="Binding" type="other:PortType"><soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/><wsdl:operation name="call"><soap:operation soapAction="urn:call"/><wsdl:input><soap:body use="literal"/></wsdl:input><wsdl:output><soap:body use="literal"/></wsdl:output></wsdl:operation></wsdl:binding>
  <wsdl:service name="Service"><wsdl:port name="Port" binding="tns:Binding"><soap:address location="https://example.invalid"/></wsdl:port></wsdl:service>
</wsdl:definitions>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="binding 'Binding' type references QName 'other:PortType'"):
        load_soap_contract_spec(wsdl, interface_name="wrong-binding-soap", package_root=tmp_path)


def test_soap_wsdl_parser_rejects_service_port_binding_with_wrong_namespace(
    tmp_path: Path,
) -> None:
    wsdl = tmp_path / "wrong-port-binding-namespace.wsdl"
    wsdl.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  xmlns:xs="http://www.w3.org/2001/XMLSchema"
                  xmlns:tns="urn:example:correct"
                  xmlns:other="urn:example:other"
                  targetNamespace="urn:example:correct">
  <wsdl:types>
    <xs:schema targetNamespace="urn:example:correct" xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Request" type="xs:string"/>
      <xs:element name="Response" type="xs:string"/>
    </xs:schema>
  </wsdl:types>
  <wsdl:message name="RequestMessage"><wsdl:part name="parameters" element="tns:Request"/></wsdl:message>
  <wsdl:message name="ResponseMessage"><wsdl:part name="parameters" element="tns:Response"/></wsdl:message>
  <wsdl:portType name="PortType"><wsdl:operation name="call"><wsdl:input message="tns:RequestMessage"/><wsdl:output message="tns:ResponseMessage"/></wsdl:operation></wsdl:portType>
  <wsdl:binding name="Binding" type="tns:PortType"><soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/><wsdl:operation name="call"><soap:operation soapAction="urn:call"/><wsdl:input><soap:body use="literal"/></wsdl:input><wsdl:output><soap:body use="literal"/></wsdl:output></wsdl:operation></wsdl:binding>
  <wsdl:service name="Service"><wsdl:port name="Port" binding="other:Binding"><soap:address location="https://example.invalid"/></wsdl:port></wsdl:service>
</wsdl:definitions>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="port 'Port' binding references QName 'other:Binding'"):
        load_soap_contract_spec(wsdl, interface_name="wrong-port-soap", package_root=tmp_path)


@pytest.mark.parametrize(
    ("xsd_payload", "expected"),
    [
        (
            '<xs:complexType mixed="true"><xs:sequence><xs:element name="value" type="xs:string"/></xs:sequence></xs:complexType>',
            "unsupported mixed content",
        ),
        ('<xs:complexType abstract="true"><xs:sequence/></xs:complexType>', "unsupported abstract types"),
        ('<xs:element name="Request" type="xs:string" substitutionGroup="tns:Base"/>', "unsupported substitutionGroup"),
    ],
)
def test_soap_wsdl_parser_rejects_xml_xsd_boundary_flags(
    tmp_path: Path,
    xsd_payload: str,
    expected: str,
) -> None:
    request_definition = (
        f'<xs:element name="Request">{xsd_payload}</xs:element>'
        if xsd_payload.startswith("<xs:complexType")
        else xsd_payload
    )
    wsdl = tmp_path / "unsupported-xsd-boundary.wsdl"
    wsdl.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  xmlns:xs="http://www.w3.org/2001/XMLSchema"
                  xmlns:tns="urn:example:xsd-boundary"
                  targetNamespace="urn:example:xsd-boundary">
  <wsdl:types>
    <xs:schema targetNamespace="urn:example:xsd-boundary" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:tns="urn:example:xsd-boundary">
      {request_definition}
      <xs:element name="Response" type="xs:string"/>
    </xs:schema>
  </wsdl:types>
  <wsdl:message name="RequestMessage"><wsdl:part name="parameters" element="tns:Request"/></wsdl:message>
  <wsdl:message name="ResponseMessage"><wsdl:part name="parameters" element="tns:Response"/></wsdl:message>
  <wsdl:portType name="PortType"><wsdl:operation name="call"><wsdl:input message="tns:RequestMessage"/><wsdl:output message="tns:ResponseMessage"/></wsdl:operation></wsdl:portType>
  <wsdl:binding name="Binding" type="tns:PortType"><soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/><wsdl:operation name="call"><soap:operation soapAction="urn:call"/><wsdl:input><soap:body use="literal"/></wsdl:input><wsdl:output><soap:body use="literal"/></wsdl:output></wsdl:operation></wsdl:binding>
  <wsdl:service name="Service"><wsdl:port name="Port" binding="tns:Binding"><soap:address location="https://example.invalid"/></wsdl:port></wsdl:service>
</wsdl:definitions>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=expected):
        load_soap_contract_spec(wsdl, interface_name="xsd-boundary-soap", package_root=tmp_path)
