"""Selected write ingestion, early refusal and supported transport wiring."""
import json
from pathlib import Path

import pytest
import yaml

from appbuilder.generation import generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.change_plan import build_change_plan
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.models import MetadataProject

SHIPPED_PROFILES = ("springboot-legacy-compatible", "springboot-enterprise-postgres-java17", "springboot-standard-enterprise")


def package(root, *, method="post", path="/accounts", name=None, parameters=None,
            status=None, response_body=None, body_required=True, mapped=True, extra=None, selected=None):
    root.mkdir(parents=True, exist_ok=True)
    name = name or {"post": "createAccount", "put": "updateAccount", "delete": "deleteAccount", "patch": "adjustAccount"}[method]
    status = status or {"post": "201", "put": "200", "delete": "204", "patch": "200"}[method]
    fields = {field: {"type": "string"} for field in ("id", "status")}
    schema = {"type": "object", "properties": fields}
    operation = {"operationId": name, "parameters": parameters or [], "responses": {status: {"description": "Result"}}}
    if response_body is True or response_body is None and method != "delete":
        operation["responses"][status]["content"] = {"application/json": {"schema": schema}}
    if method != "delete":
        operation["requestBody"] = {"required": body_required, "content": {"application/json": {"schema": schema}}}
    mapping = [{"source": field, "target": "Account." + field} for field in fields]
    manifest = {"schema_version": "2.0", "app_name": "Write Probe", "bounded_context": "writeprobe",
        "target_profile": "springboot-legacy-compatible", "identity_overrides": [{"entity": "Account", "persistence_id": "id"}],
        "upstream_interfaces": [{"name": "api", "type": "rest-json", "spec": "spec.yaml", "mapping": "mapping.yaml",
            "operations": selected or [{"name": name, "request_sample": "request.json", **({"response_sample": "response.json"} if method != "delete" else {})}]}]}
    paths = {path: {method: operation}}
    if extra:
        for route, value in extra.items():
            paths.setdefault(route, {}).update(value)
    for filename, data in {"app-definition.yaml": manifest, "spec.yaml": {"openapi": "3.0.3",
        "info": {"title": "Write", "version": "1"}, "paths": paths}, "mapping.yaml": {"interface": "api", "operations": [
            {"name": name, "request_mappings": mapping if mapped else [], "response_mappings": mapping} ]}}.items():
        (root / filename).write_text(yaml.safe_dump(data, sort_keys=False))
    for filename in ("request.json", "response.json"):
        (root / filename).write_text(json.dumps({"id": "A", "status": "OPEN"}))
    return root / "app-definition.yaml"


def param(name, location="header", required=True, kind="string", **kwargs):
    return {"name": name, "in": location, "required": required, "schema": {"type": kind}, **kwargs}


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


UNSUPPORTED = [
    {"method": "delete", "path": "/accounts/{id}/erase", "parameters": [param("id", "path")]},
    {"method": "put"},
    {"path": "/accounts/"},
    {"path": '/accounts/quote"'},
    {"path": "/accounts/line\nbreak"},
    {"path": '/accounts") @SuppressWarnings("bad'},
    {"method": "patch", "path": "/accounts/{id}", "parameters": [param("id", "path")]},
    {"method": "put", "path": "/accounts/{id}", "name": "createAccount", "parameters": [param("id", "path")]},
    {"path": "/accounts/{id}", "parameters": [param("id", "path")]},
    {"method": "put", "path": "/customers/{owner}/accounts/{id}", "parameters": [param("owner", "path"), param("id", "path")]},
    {"method": "put", "path": "/accounts/{id}"},
    {"mapped": False},
    {"parameters": [param("session", "cookie")]},
    {"parameters": [param("branch", "query", kind="array")]},
    {"parameters": [param("If-Match")]},
    {"parameters": [param("trace", style="label")]},
    {"parameters": [{"$ref": "#/components/parameters/Missing"}]},
    {"parameters": [param("class")]},
    {"parameters": [param("created")]},
    {"parameters": [param("created", "query")]},
    {"method": "put", "path": "/accounts/{id}", "parameters": [param("id", "path"), param("updated")]},
    {"method": "put", "path": "/accounts/{id}", "parameters": [param("id", "path"), param("updated", "query")]},
    {"status": "200"},
    {"method": "delete", "path": "/accounts/{id}", "parameters": [param("id", "path")], "status": "200", "response_body": True},
    {"method": "put", "path": "/accounts/{id}", "parameters": [param("id", "path")], "status": "204", "response_body": False},
    {"body_required": False},
]


@pytest.mark.parametrize("case", UNSUPPORTED)
@pytest.mark.parametrize("entry", ["generate", "plan", "apply"])
def test_write_refusal_precedes_all_output_changes(tmp_path, case, entry):
    metadata = build_metadata_project(package(tmp_path / "input", **case))
    output = tmp_path / "app"
    generate_application(build_metadata_project(package(tmp_path / "supported")), output, generation_run_id="initial")
    sentinel = output / "developer-owned.txt"
    sentinel.write_text("preserve developer content")
    sentinel.chmod(0o444)
    before = snapshot(output)
    dirs = {str(p): p.stat().st_mtime_ns for p in [output, *output.rglob("*")] if p.is_dir()}
    try:
        with pytest.raises(ValueError, match="Write operation.*unsupported"):
            if entry == "generate":
                generate_application(metadata, output)
            elif entry == "plan":
                build_change_plan(metadata=metadata, package_dir=output)
            else:
                apply_change_plan(metadata=metadata, package_dir=output, approved_plan_hash="unused")
        assert snapshot(output) == before
        assert {str(p): p.stat().st_mtime_ns for p in [output, *output.rglob("*")] if p.is_dir()} == dirs
        absent = tmp_path / "absent" / "app"
        with pytest.raises(ValueError, match="Write operation"):
            generate_application(metadata, absent)
        assert not absent.parent.exists()
    finally:
        sentinel.chmod(0o644)


@pytest.mark.parametrize("profile", SHIPPED_PROFILES)
@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_supported_write_inputs_reach_controller_base_and_developer(tmp_path, profile, method):
    parameters = [param("X-Trace"), param("branch", "query", False, "integer")]
    path = "/accounts"
    if method != "post":
        path += "/{accountId}"
        parameters.append(param("accountId", "path"))
    metadata = build_metadata_project(package(tmp_path / "input", method=method, path=path, parameters=parameters))
    metadata.target_profile = profile
    metadata = MetadataProject.model_validate(metadata.model_dump(mode="json"))
    output = tmp_path / "app"
    generate_application(metadata, output, generation_run_id="test")
    controller = next(output.rglob("AccountController.java")).read_text()
    base = next(output.rglob("AccountServiceBase.java")).read_text()
    developer = next(output.rglob("AccountService.java")).read_text()
    assert '@RequestHeader(name = "X-Trace", required = true) String xTrace' in controller
    assert '@RequestParam(name = "branch", required = false)' in controller
    for source in (base, developer):
        assert "String xTrace" in source and "branch" in source
    before = next(output.rglob("AccountService.java")).read_bytes()
    generate_application(metadata, output, generation_run_id="again")
    assert next(output.rglob("AccountService.java")).read_bytes() == before


def test_selected_inventory_cannot_lose_patch_or_unresolved_operation(tmp_path):
    manifest = package(tmp_path / "input", selected=[{"name": "missing", "request_sample": "request.json"}])
    metadata = build_metadata_project(manifest)
    assert metadata.selected_rest_contracts[0]["errors"]
    with pytest.raises(ValueError, match="unresolved"):
        generate_application(metadata, tmp_path / "app")


def test_unselected_unsupported_operations_do_not_block(tmp_path):
    manifest = package(tmp_path / "input", extra={"/unselected/{id}": {"patch": {"operationId": "unselected", "responses": {}}}})
    metadata = build_metadata_project(manifest)
    assert len(metadata.selected_rest_contracts) == 1
    generate_application(metadata, tmp_path / "app")


def test_multiple_selected_creates_are_not_silently_omitted(tmp_path):
    manifest = package(tmp_path / "input")
    raw = yaml.safe_load(manifest.read_text())
    raw["upstream_interfaces"][0]["operations"].append({"name": "approveAccount", "request_sample": "request.json", "response_sample": "response.json"})
    manifest.write_text(yaml.safe_dump(raw))
    path = manifest.parent / "spec.yaml"
    spec = yaml.safe_load(path.read_text())
    other = json.loads(json.dumps(spec["paths"]["/accounts"]["post"]))
    other["operationId"] = "approveAccount"
    spec["paths"]["/accounts/approve"] = {"post": other}
    path.write_text(yaml.safe_dump(spec))
    mapping = manifest.parent / "mapping.yaml"
    data = yaml.safe_load(mapping.read_text())
    data["operations"].append({**data["operations"][0], "name": "approveAccount"})
    mapping.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="additional selected write"):
        generate_application(build_metadata_project(manifest), tmp_path / "app")


def test_payment_headers_and_console_transport_are_explicit(tmp_path):
    from tests.unit.test_operator_dashboard import (
        _extract_descriptors,
        _extract_js_block,
        _run_node_script,
    )
    manifest = Path(__file__).resolve().parents[2] / "examples/input-projects/obie-wire-transfer/app-definition.yaml"
    metadata = build_metadata_project(manifest)
    output = tmp_path / "app"
    generate_application(metadata, output)
    source = next(output.rglob("InternationalPaymentController.java")).read_text()
    assert '@RequestHeader(name = "x-idempotency-key", required = true)' in source
    assert '@RequestHeader(name = "x-jws-signature", required = true)' in source
    developer = next(output.rglob("InternationalPaymentService.java")).read_text()
    assert "String xIdempotencyKey" in developer and "String xJwsSignature" in developer
    assert "Header presence is not replay protection" in developer
    html = next(output.rglob("index.html")).read_text()
    assert '"contractName": "x-idempotency-key"' in html
    assert '"header": true' in html and "inputState.transportHeaders" in html
    descriptor = next(item for item in _extract_descriptors(html)
        if any(action["verb"] == "POST" and action["endpoint"] == "/international-payments"
               for action in item["actions"]))
    js = _extract_js_block(html, "    function coerceValue", "    function actionButtonId")
    script = f"""
const descriptor = {json.dumps(descriptor)};
const action = descriptor.actions.find(a => a.verb === 'POST');
const body = {{ConsentId: 'proof', InstructionIdentification: 'instruction',
  EndToEndIdentification: 'end-to-end', CurrencyOfTransfer: 'USD',
  InstructedAmount: '42.50', CreditorName: 'recipient'}};
global.document = {{getElementById(id) {{
  const fd = descriptor.hints.find(h => h.id === id);
  return {{value: fd.header || fd.query ? 'transport-value' : body[fd.contractName], type: 'text'}};
}}}};
{js}
const input = collectActionInputs(descriptor, action, false);
if (input.errors.length) throw new Error(input.errors.join(','));
console.log(JSON.stringify(buildActionRequest(descriptor, action, input, false)));
"""
    request = json.loads(_run_node_script(script, tmp_path))
    assert request["endpoint"] == "/international-payments"
    assert request["fetchOptions"]["headers"]["x-idempotency-key"] == "transport-value"
    assert request["fetchOptions"]["headers"]["x-jws-signature"] == "transport-value"
    body = json.loads(request["fetchOptions"]["body"])
    assert body["ConsentId"] == "proof" and body["InstructedAmount"] == "42.50"
    assert "x-idempotency-key" not in body and "x-jws-signature" not in body


def test_shipped_payment_aliases_bind_explicit_sampled_fields_without_accessor_collision(tmp_path):
    manifest = Path(__file__).resolve().parents[2] / "examples/input-projects/obie-wire-transfer/app-definition.yaml"
    metadata = build_metadata_project(manifest)
    entity = next(entity for entity in metadata.entities if entity.name == "InternationalPayment")
    fields = {field.name: field for field in entity.fields}
    aliases = {
        "InternationalPaymentId": "Data.InternationalPaymentId",
        "ConsentId": "Data.ConsentId",
        "InstructionIdentification": "Data.Initiation.InstructionIdentification",
        "EndToEndIdentification": "Data.Initiation.EndToEndIdentification",
        "CurrencyOfTransfer": "Data.Initiation.CurrencyOfTransfer",
        "Status": "Data.Status",
        "StatusUpdateDateTime": "Data.StatusUpdateDateTime",
    }
    assert [field.name for field in entity.fields if field.is_id] == ["InternationalPaymentId"]
    for wire, sample_path in aliases.items():
        assert wire[0].lower() + wire[1:] not in fields
        assert "obie-payment-initiation-api.response." + sample_path in fields[wire].source_paths
        for mapping in metadata.mappings:
            if mapping.operation_name and mapping.source_path.endswith("." + wire):
                assert mapping.target_path == "InternationalPayment." + wire
    # Distinct meanings stay distinct; no case-insensitive emitter deduplication.
    assert {"Amount", "instructedAmount", "Currency", "CurrencyOfTransfer", "Name", "creditorName"} <= fields.keys()
    assert fields["instructedAmount"].type.value == "string"
    output = tmp_path / "app"
    generate_application(metadata, output)
    domain = next(output.rglob("InternationalPayment.java")).read_text()
    base = next(output.rglob("InternationalPaymentServiceBase.java")).read_text()
    request = next(output.rglob("CreateInternationalPaymentsRequest.java")).read_text()
    for name in ("ConsentId", "InstructionIdentification", "EndToEndIdentification", "CurrencyOfTransfer", "InstructedAmount", "CreditorName"):
        assert f'@JsonProperty("{name}")' in request
        assert f".set{name}(request.get{name}());" in base
        assert domain.count(f" get{name}()") == 1
    assert domain.count(" getInternationalPaymentId()") == 1


@pytest.mark.parametrize("profile", SHIPPED_PROFILES)
def test_cross_controller_collision_refused_before_normal_generation(tmp_path, profile):
    root = tmp_path / "inputs"
    first = package(root / "alpha")
    second = package(root / "beta")
    raw = yaml.safe_load(first.read_text())
    other = yaml.safe_load(second.read_text())
    other["identity_overrides"][0]["entity"] = "BetaRecord"
    interface = other["upstream_interfaces"][0]
    interface["name"] = "beta-api"
    interface["spec"] = "beta/spec.yaml"
    interface["mapping"] = "beta/mapping.yaml"
    interface["operations"][0]["request_sample"] = "beta/request.json"
    interface["operations"][0]["response_sample"] = "beta/response.json"
    raw["upstream_interfaces"].append(interface)
    raw["identity_overrides"].append(other["identity_overrides"][0])
    raw["target_profile"] = profile
    # Two valid source contracts use the same collection route, different entities.
    mapping = root / "beta/mapping.yaml"
    mapping.write_text(mapping.read_text().replace("api", "beta-api").replace("Account.", "BetaRecord."))
    (root / "app-definition.yaml").write_text(yaml.safe_dump(raw))
    # Alpha's paths are relative to the newly combined root.
    raw["upstream_interfaces"][0]["spec"] = "alpha/spec.yaml"
    raw["upstream_interfaces"][0]["mapping"] = "alpha/mapping.yaml"
    raw["upstream_interfaces"][0]["operations"][0]["request_sample"] = "alpha/request.json"
    raw["upstream_interfaces"][0]["operations"][0]["response_sample"] = "alpha/response.json"
    manifest = root / "app-definition.yaml"
    manifest.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="collides.*fallback"):
        generate_application(build_metadata_project(manifest), tmp_path / "app")
    assert not (tmp_path / "app").exists()


@pytest.mark.parametrize("target", ["response", "body", "parameter"])
def test_local_references_resolve_or_refuse_without_erasure(tmp_path, target):
    manifest = package(tmp_path / "input", parameters=[param("X-Trace")])
    path = manifest.parent / "spec.yaml"
    spec = yaml.safe_load(path.read_text())
    operation = spec["paths"]["/accounts"]["post"]
    value = {"response": operation["responses"]["201"], "body": operation["requestBody"],
             "parameter": operation["parameters"][0]}[target]
    spec["components"] = {"values": {"Selected": value}}
    if target == "response":
        operation["responses"]["201"] = {"$ref": "#/components/values/Selected"}
    elif target == "body":
        operation["requestBody"] = {"$ref": "#/components/values/Selected"}
    else:
        operation["parameters"] = [{"$ref": "#/components/values/Selected"}]
    path.write_text(yaml.safe_dump(spec))
    generate_application(build_metadata_project(manifest), tmp_path / "app")
    spec["components"]["values"]["Selected"] = {"$ref": "#/components/values/Selected"}
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ValueError, match="reference"):
        generate_application(build_metadata_project(manifest), tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


def test_header_requiredness_cannot_change_after_source_retention(tmp_path):
    metadata = build_metadata_project(package(tmp_path / "input", parameters=[param("X-Trace")]))
    metadata.operations[0].operation_parameters[0].required = False
    with pytest.raises(ValueError, match="lost or changed"):
        generate_application(metadata, tmp_path / "app")


def test_special_openapi_headers_are_not_authentication_parameters(tmp_path):
    metadata = build_metadata_project(package(tmp_path / "input", parameters=[
        param("Authorization"), param("Accept"), param("Content-Type")]))
    assert not metadata.operations[0].operation_parameters
    generate_application(metadata, tmp_path / "app")


def assert_refused_without_mutation(metadata, tmp_path, match):
    from appbuilder.generation.java_emitter import emit_java_sources
    from appbuilder.target_profiles.catalog import TARGET_PROFILES
    output = tmp_path / "existing"
    generate_application(build_metadata_project(package(tmp_path / "control")), output)
    before = snapshot(output)
    directories = {str(p): p.stat().st_mtime_ns for p in [output, *output.rglob("*")] if p.is_dir()}
    calls = [lambda: generate_application(metadata, output),
             lambda: build_change_plan(metadata=metadata, package_dir=output),
             lambda: apply_change_plan(metadata=metadata, package_dir=output, approved_plan_hash="unused"),
             lambda: emit_java_sources(metadata=metadata, target_profile=TARGET_PROFILES[metadata.target_profile],
                 output_dir=output, source_manifest="test", generation_run_id="test")]
    for call in calls:
        with pytest.raises(ValueError, match=match):
            call()
        assert snapshot(output) == before
        assert {str(p): p.stat().st_mtime_ns for p in [output, *output.rglob("*")] if p.is_dir()} == directories
    with pytest.raises(ValueError, match=match):
        generate_application(metadata, tmp_path / "absent" / "app")
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize("alias", ["accountId", "id"])
def test_business_key_alias_cannot_override_explicit_persistence_identity(tmp_path, method, alias):
    manifest = package(tmp_path / "input", method=method, path="/accounts/{" + alias + "}", parameters=[param(alias, "path")])
    raw = yaml.safe_load(manifest.read_text())
    raw["identity_overrides"] = [{"entity": "Account", "persistence_id": "internalId"}]
    manifest.write_text(yaml.safe_dump(raw))
    root = manifest.parent
    sample = {"internalId": "ROW-A", alias: "PUBLIC-A", "status": "OPEN-A"}
    for filename in ("request.json", "response.json"):
        (root / filename).write_text(json.dumps(sample))
    mappings = [{"source": key, "target": "Account." + ("accountId" if key == alias else key)} for key in sample]
    (root / "mapping.yaml").write_text(yaml.safe_dump({"operations": [{"name": raw["upstream_interfaces"][0]["operations"][0]["name"],
        "request_mappings": mappings, "response_mappings": mappings}]}))
    metadata = build_metadata_project(manifest)
    assert [field.name for field in metadata.entities[0].fields if field.is_id] == ["internalId"]
    assert_refused_without_mutation(metadata, tmp_path, "business field|contradicts.*identity")


@pytest.mark.parametrize("mapped", [False, True])
def test_entity_id_alias_for_differently_named_identity_requires_explicit_binding(tmp_path, mapped):
    from appbuilder.mapping import FieldMapping, MappingDirection
    metadata = build_metadata_project(package(tmp_path / "input", method="put", path="/accounts/{accountId}",
        parameters=[param("accountId", "path")]))
    entity = metadata.entities[0]
    next(field for field in entity.fields if field.is_id).name = "internalId"
    for mapping in metadata.mappings:
        if mapping.target_path == "Account.id":
            mapping.target_path = "Account.internalId"
    if mapped:
        metadata.mappings.append(FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api",
            operation_name="updateAccount", source_path="api.updateAccount.request.accountId", target_path="Account.internalId"))
        generate_application(metadata, tmp_path / "app")
    else:
        assert_refused_without_mutation(metadata, tmp_path, "unambiguous persistence ID")


@pytest.mark.parametrize("wire", ['sta"tus', "sta\ntus", "sta\\tus"])
def test_unsafe_body_wire_literals_are_refused_before_public_and_direct_output(tmp_path, wire):
    manifest = package(tmp_path / "input")
    root = manifest.parent
    mappings = yaml.safe_load((root / "mapping.yaml").read_text())
    for key in ("request_mappings", "response_mappings"):
        for mapping in mappings["operations"][0][key]:
            if mapping["source"] == "status":
                mapping["source"] = wire
    (root / "mapping.yaml").write_text(yaml.safe_dump(mappings))
    for filename in ("request.json", "response.json"):
        (root / filename).write_text(json.dumps({"id": "A", wire: "OPEN"}))
    assert_refused_without_mutation(build_metadata_project(manifest), tmp_path, "body wire field.*Java-literal")


@pytest.mark.parametrize("selectors", [[], ["ownerId", "id"]])
def test_explicit_direct_http_action_cannot_drop_selectors(tmp_path, selectors):
    from appbuilder.mapping import FieldMapping, MappingDirection
    from appbuilder.metadata.models import (
        CanonicalOperation,
        HttpMethod,
        PathParameter,
        ResponseShape,
    )
    metadata = build_metadata_project(package(tmp_path / "input"))
    metadata.selected_rest_contracts = []
    metadata.operations = [CanonicalOperation(name="approveAccount", interface_name="api", request_entity="Account",
        response_entity="Account", http_method=HttpMethod.POST, response_shape=ResponseShape.SINGLE,
        path_parameters=[PathParameter(name=name, type="String") for name in selectors])]
    metadata.mappings = [FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api",
        operation_name="approveAccount", source_path="api.approveAccount." + context + ".status", target_path="Account.status")
        for context in ("request", "response")]
    assert_refused_without_mutation(metadata, tmp_path, "exactly one.*persistence-ID")


@pytest.mark.parametrize("name,declared,matching", [
    ("createAccount", "PUT", "POST"), ("updateAccount", "POST", "PUT"), ("deleteAccount", "POST", "DELETE")])
def test_direct_http_method_without_source_path_is_validated_before_output(tmp_path, name, declared, matching):
    from appbuilder.metadata.models import HttpMethod, PathParameter, ResponseShape
    metadata = build_metadata_project(package(tmp_path / "input"))
    metadata.selected_rest_contracts = []
    operation = metadata.operations[0]
    old = operation.name
    operation.name = name
    operation.http_method = HttpMethod(declared)
    operation.path = None
    operation.response_shape = ResponseShape.SINGLE
    operation.has_request_body = matching != "DELETE"
    operation.path_parameters = [] if name.startswith("create") else [PathParameter(name="id", type="String")]
    for mapping in metadata.mappings:
        mapping.operation_name = name
        mapping.source_path = mapping.source_path.replace("." + old + ".", "." + name + ".")
    assert_refused_without_mutation(metadata, tmp_path, "HTTP method/name dispatch")
    operation.http_method = HttpMethod(matching)
    generate_application(metadata, tmp_path / "matching")
    operation.http_method = None
    generate_application(metadata, tmp_path / "sample-only")


def test_direct_delete_declared_body_is_not_dropped_without_source_path(tmp_path):
    metadata = build_metadata_project(package(tmp_path / "input", method="delete", path="/accounts/{id}",
        parameters=[param("id", "path")]))
    metadata.selected_rest_contracts = []
    metadata.operations[0].path = None
    metadata.operations[0].has_request_body = True
    assert_refused_without_mutation(metadata, tmp_path, "DELETE handler cannot consume")


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("value", ["", "false", "true"])
def test_console_boolean_transport_preserves_absent_false_and_true(tmp_path, required, value):
    from tests.unit.test_operator_dashboard import (
        _extract_descriptors,
        _extract_js_block,
        _run_node_script,
    )
    metadata = build_metadata_project(package(tmp_path / "input", parameters=[
        param("notify", "query", required, "boolean"), param("X-Dry-Run", "header", required, "boolean")]))
    output = tmp_path / "app"
    generate_application(metadata, output)
    html = next(output.rglob("index.html")).read_text()
    descriptor = next(item for item in _extract_descriptors(html)
        if any(action["verb"] == "POST" and action["endpoint"] == "/accounts" for action in item["actions"]))
    for hint in descriptor["hints"]:
        if hint.get("writeTransport"):
            assert hint["inputType"] == "select" and hint["allowedValues"] == ["true", "false"]
    js = _extract_js_block(html, "    function coerceValue", "    function actionButtonId")
    script = f"""
const descriptor = {json.dumps(descriptor)};
const action = descriptor.actions.find(a => a.verb === 'POST');
global.document = {{getElementById(id) {{
  const fd = descriptor.hints.find(h => h.id === id);
  return {{value: fd.writeTransport ? {json.dumps(value)} : 'A', type: fd.inputType}};
}}}};
{js}
const input = collectActionInputs(descriptor, action, false);
console.log(JSON.stringify({{input, request: buildActionRequest(descriptor, action, input, false)}}));
"""
    result = json.loads(_run_node_script(script, tmp_path))
    assert len(result["input"]["errors"]) == (2 if required and not value else 0)
    if required and not value:
        return  # Submission is blocked by the two required-input errors.
    assert result["request"]["endpoint"] == "/accounts" + ("?notify=" + value if value else "")
    headers = result["request"]["fetchOptions"]["headers"]
    assert headers.get("X-Dry-Run") == (value or None)
