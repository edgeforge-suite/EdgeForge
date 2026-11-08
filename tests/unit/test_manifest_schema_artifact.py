import hashlib
import json
from pathlib import Path

from appbuilder.core import (
    CURRENT_MANIFEST_SCHEMA_FILENAME,
    CURRENT_MANIFEST_SCHEMA_VERSION,
    SUPPORTED_MANIFEST_SCHEMA_VERSIONS,
)

_CURRENT_NORMALIZED_SCHEMA_SHA256 = (
    "361c849f143edb11d7f6110d3f41a383fa3d6d966ca5655e44def76285ad539f"
)


def test_manifest_v2_schema_artifact_captures_current_contract() -> None:
    schema_path = Path("appbuilder/schema/manifest-v2.schema.json")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["title"] == "EdgeForge Manifest v2"
    assert "schema_version" in schema["required"]
    assert schema["properties"]["schema_version"]["enum"] == ["2.0"]
    assert schema["properties"]["app_archetype"]["default"] == "crud"
    assert schema["properties"]["app_archetype"]["enum"] == [
        "crud",
        "passthrough-router",
        "kafka-integration",
    ]
    assert "kafka_config" in schema["properties"]
    assert "async_routes" in schema["properties"]
    assert "kafka_config" not in schema["required"]
    assert "async_routes" not in schema["required"]
    assert schema["properties"]["async_routes"]["items"]["$ref"] == (
        "#/$defs/asyncRouteDefinition"
    )
    assert schema["$defs"]["asyncRouteDefinition"]["required"] == ["name", "pattern"]
    assert "router" in schema["$defs"]["asyncRouteDefinition"]["properties"]["pattern"]["enum"]
    assert (
        schema["$defs"]["asyncRouteDefinition"]["properties"]["router_config"]["$ref"]
        == "#/$defs/routerConfig"
    )
    assert "routerConfig" in schema["$defs"]
    assert schema["properties"]["upstream_interfaces"]["items"]["$ref"] == (
        "#/$defs/interfaceDefinition"
    )
    assert "xsd_path" in schema["$defs"]["interfaceDefinition"]["properties"]
    assert "wsdl_path" in schema["$defs"]["interfaceDefinition"]["properties"]
    assert "root_element" in schema["$defs"]["interfaceDefinition"]["properties"]
    assert "service" in schema["$defs"]["interfaceDefinition"]["properties"]
    assert "port" in schema["$defs"]["interfaceDefinition"]["properties"]
    assert "binding" in schema["$defs"]["interfaceDefinition"]["properties"]
    xml_branch = schema["$defs"]["interfaceDefinition"]["allOf"][0]
    assert xml_branch["if"]["properties"]["type"]["const"] == "xml-xsd"
    assert xml_branch["then"]["required"] == ["root_element"]
    assert xml_branch["then"]["oneOf"][0]["required"] == ["xsd_path"]
    assert xml_branch["then"]["oneOf"][1]["required"] == ["spec"]
    soap_branch = xml_branch["else"]
    assert soap_branch["if"]["properties"]["type"]["const"] == "soap-wsdl"
    assert soap_branch["then"]["oneOf"][0]["required"] == ["wsdl_path"]
    assert soap_branch["then"]["oneOf"][1]["required"] == ["spec"]
    assert schema["$defs"]["dataHandoffDefinition"]["properties"]["type"]["allOf"][1]["not"][
        "enum"
    ] == ["file-fixed-width", "file-csv", "xml-xsd", "soap-wsdl"]
    run_semantics = schema["$defs"]["runSemanticsDefinition"]
    assert run_semantics["additionalProperties"] is False
    assert run_semantics["required"] == ["run_id", "restart", "dedup_key"]
    assert run_semantics["properties"]["run_id"]["const"] == "caller_supplied"
    assert run_semantics["properties"]["restart"]["const"] == "resume"
    assert run_semantics["properties"]["dedup_key"]["minItems"] == 1
    staging_only = schema["$defs"]["dataHandoffDefinition"]["allOf"][0]
    assert staging_only["if"]["required"] == ["run_semantics"]
    assert staging_only["then"]["properties"]["type"]["const"] == "staging-table"
    crud_only = schema["allOf"][2]
    assert crud_only["if"]["properties"]["data_handoffs"]["contains"]["required"] == [
        "run_semantics"
    ]
    assert crud_only["then"]["properties"]["app_archetype"]["const"] == "crud"
    assert schema["$defs"]["interfaceOperationDefinition"]["anyOf"] == [
        {"required": ["request_sample"]},
        {"required": ["response_sample"]},
    ]


def test_manifest_version_constants_and_active_schema_artifact_agree() -> None:
    assert CURRENT_MANIFEST_SCHEMA_VERSION == "2.0"
    assert CURRENT_MANIFEST_SCHEMA_FILENAME == "manifest-v2.schema.json"
    assert SUPPORTED_MANIFEST_SCHEMA_VERSIONS == frozenset({"2.0"})
    assert Path("appbuilder/schema/manifest-v2.schema.json").is_file()
    assert not Path("appbuilder/schema/manifest-v1.schema.json").exists()


def test_manifest_v2_schema_matches_the_reviewed_m5a_s1_contract() -> None:
    schema = json.loads(
        Path("appbuilder/schema/manifest-v2.schema.json").read_text(encoding="utf-8")
    )
    schema["$id"] = "<manifest-schema>"
    schema["title"] = "EdgeForge Manifest"
    schema["properties"]["schema_version"]["enum"] = ["<manifest-version>"]
    normalized = json.dumps(
        schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    assert hashlib.sha256(normalized).hexdigest() == _CURRENT_NORMALIZED_SCHEMA_SHA256
