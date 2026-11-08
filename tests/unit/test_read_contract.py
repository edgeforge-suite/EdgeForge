"""Support-or-refuse regressions for selected generated REST reads."""


import pytest

from appbuilder.generation.java_emitter import _render_service
from appbuilder.ingestion.openapi_classifier import ingest_openapi_operations
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    ContractMetadata,
    HttpMethod,
    MetadataProject,
    OperationParameter,
    OperationParameterLocation,
    PathParameter,
    ResponseShape,
)
from appbuilder.target_profiles.catalog import TARGET_PROFILES


def mapped_metadata(profile="springboot-legacy-compatible", *, mixed=False, pageable=False):
    operations = [
        CanonicalOperation(name="getAccount", interface_name="api", request_entity="Account",
                           response_entity="Account", http_method=HttpMethod.GET,
                           path="/accounts/{id}", path_parameters=[PathParameter(name="id")],
                           response_shape=ResponseShape.SINGLE),
        CanonicalOperation(name="listAccounts", interface_name="api", request_entity="Account",
                           response_entity="Account", http_method=HttpMethod.GET,
                           path="/accounts", response_shape=ResponseShape.LIST, pageable=pageable),
    ]
    if mixed:
        operations.append(CanonicalOperation(name="createAccount", interface_name="api",
                                             request_entity="Account", response_entity="Account",
                                             http_method=HttpMethod.POST, path="/accounts",
                                             response_shape=ResponseShape.CREATED))
    mappings = [FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                             contract_name="api", operation_name=operation.name,
                             source_path=f"api.{operation.name}.response.{field}",
                             target_path=f"Account.{field}")
                for operation in operations for field in ("id", "customerId")]
    return MetadataProject(app_name="Reads", bounded_context="reads", target_profile=profile,
                           entities=[account()], operations=operations, mappings=mappings,
                           contracts=[ContractMetadata(name="api", type="rest-json", source="")])


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def request_sample_metadata(root, *, shape="own-id", mixed=False,
                            profile="springboot-legacy-compatible", sample=True):
    """Ingest a selected GET with no request mappings or default mapping entity."""
    import json

    import yaml

    from appbuilder.metadata import build_metadata_project

    root.mkdir(parents=True)
    name, path = {
        "own-id": ("getAccount", "/accounts/{id}"),
        "owner-id": ("getAccountForCustomer", "/accounts/by-customer/{customerId}"),
        "computed": ("accountSummary", "/accounts/{id}/summary"),
        "list": ("listAccounts", "/accounts"),
        "body-list": ("listAccounts", "/accounts"),
        "query-list": ("listAccounts", "/accounts"),
    }[shape]
    collection = shape.endswith("list")
    account_schema = {"type": "object", "properties": {
        "id": {"type": "string"}, "customerId": {"type": "string"},
    }}
    operation = {"operationId": name, "responses": {"200": {"description": "Account",
                 "content": {"application/json": {"schema": (
                     {"type": "array", "items": account_schema} if collection else account_schema
                 )}}}}}
    if "{" in path:
        parameter = "customerId" if shape == "owner-id" else "id"
        operation["parameters"] = [{"name": parameter, "in": "path", "required": True,
                                    "schema": {"type": "string"}}]
    if shape == "query-list":
        operation["parameters"] = [{"name": "owner", "in": "query", "schema": {"type": "string"}}]
    if shape == "body-list":
        operation["requestBody"] = {"content": {"application/json": {"schema": account_schema}}}
    spec = {"openapi": "3.0.3", "info": {"title": "Reads", "version": "1"},
            "paths": {path: {"get": operation}}}
    selected = [{"name": name, "response_sample": "response.json"}]
    if sample:
        selected[0]["request_sample"] = "request.json"
    mapped = [{"name": name, "response_mappings": [
        {"source": "id", "target": "Account.id"},
        {"source": "customerId", "target": "Account.customerId"},
    ]}]
    if mixed:
        selected.append({"name": "createAccount", "request_sample": "response.json",
                         "response_sample": "response.json"})
        mapped.append({"name": "createAccount", "request_mappings": mapped[0]["response_mappings"],
                       "response_mappings": mapped[0]["response_mappings"]})
        spec["paths"].setdefault("/accounts", {})["post"] = {
            "operationId": "createAccount", "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": account_schema}}},
            "responses": {"201": {"description": "Created", "content": {
                "application/json": {"schema": account_schema}}}},
        }
    manifest = {
        "schema_version": "2.0", "app_name": "Reads", "bounded_context": "reads",
        "target_profile": profile,
        "identity_overrides": [{"entity": "Account", "persistence_id": "id"}],
        "upstream_interfaces": [{"name": "api", "system": "Reads", "type": "rest-json",
                                 "spec": "spec.yaml", "mapping": "mapping.yaml", "operations": selected}],
    }
    for filename, content in {"app-definition.yaml": manifest, "spec.yaml": spec,
                              "mapping.yaml": {"interface": "api", "operations": mapped}}.items():
        (root / filename).write_text(yaml.safe_dump(content, sort_keys=False))
    (root / "request.json").write_text(json.dumps({"owner": "CUST-1"}))
    (root / "response.json").write_text(json.dumps({"id": "ACC-7", "customerId": "CUST-1"}))
    return build_metadata_project(root / "app-definition.yaml")


@pytest.mark.parametrize("profile", list(TARGET_PROFILES))
@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("shape", ["owner-id", "body-list", "query-list"])
@pytest.mark.parametrize("entry", ["generate", "plan", "apply"])
def test_unmapped_get_request_sample_cannot_bypass_preflight(tmp_path, profile, mixed, shape, entry):
    from appbuilder.generation import generate_application
    from appbuilder.generation.apply import apply_change_plan
    from appbuilder.generation.change_plan import build_change_plan

    supported = request_sample_metadata(tmp_path / "supported", mixed=mixed, profile=profile, sample=False)
    output = tmp_path / "app"
    generate_application(supported, output, generation_run_id="supported")
    plan = build_change_plan(metadata=supported, package_dir=output)
    sentinel = output / "developer-owned.txt"
    sentinel.write_text("developer content\n")
    sentinel.chmod(0o444)
    metadata = request_sample_metadata(tmp_path / "input", shape=shape, mixed=mixed, profile=profile)
    operation = metadata.operations[0]
    assert operation.request_entity == "Record"
    assert operation.response_entity == "Account"
    assert not any(mapping.source_path.startswith(f"api.{operation.name}.request.")
                   for mapping in metadata.mappings)
    before = snapshot(output)
    directories = {str(path.relative_to(output)): path.stat().st_mtime_ns
                   for path in [output, *output.rglob("*")] if path.is_dir()}
    try:
        with pytest.raises(ValueError, match=f"Read operation '{operation.name}'.*Account"):
            if entry == "generate":
                generate_application(metadata, output, generation_run_id="unsupported")
            elif entry == "plan":
                build_change_plan(metadata=metadata, package_dir=output)
            else:
                apply_change_plan(metadata=metadata, package_dir=output,
                                  approved_plan_hash=plan["plan_hash"], generation_run_id="unsupported")
        assert snapshot(output) == before
        assert {str(path.relative_to(output)): path.stat().st_mtime_ns
                for path in [output, *output.rglob("*")] if path.is_dir()} == directories
        absent = tmp_path / "absent" / "app"
        with pytest.raises(ValueError, match=f"Read operation '{operation.name}'.*Account"):
            generate_application(metadata, absent, generation_run_id="unsupported")
        assert not absent.parent.exists()
    finally:
        sentinel.chmod(0o644)


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("shape", ["own-id", "computed", "list"])
def test_supported_get_request_sample_uses_returned_entity(tmp_path, mixed, shape):
    from appbuilder.generation import generate_application
    from appbuilder.generation.java_emitter import _operation_contexts_for_entity

    metadata = request_sample_metadata(tmp_path / "input", shape=shape, mixed=mixed)
    assert metadata.operations[0].request_entity == "Record"
    entity = next(entity for entity in metadata.entities if entity.name == "Account")
    contexts = _operation_contexts_for_entity(metadata, entity)
    context = next(ctx for ctx in contexts if ctx["operation_name"] == metadata.operations[0].name)
    assert context["raw_request_field_mappings"] == []
    report = generate_application(metadata, tmp_path / "app", generation_run_id="supported-sample")
    assert report.harness_report is not None and report.harness_report.passed
    service = next((tmp_path / "app").rglob("AccountServiceBase.java")).read_text()
    assert ("accountRepository.findAll(" if shape == "list" else "accountRepository.findById(id)") in service
    console = next((tmp_path / "app").rglob("index.html")).read_text()
    assert metadata.operations[0].path in console


@pytest.mark.parametrize("entity_name", ["Missing", "Fieldless"])
@pytest.mark.parametrize("entry", ["generate", "plan", "apply"])
def test_selected_read_cannot_skip_missing_returned_entity(tmp_path, entity_name, entry):
    from appbuilder.generation import generate_application
    from appbuilder.generation.apply import apply_change_plan
    from appbuilder.generation.change_plan import build_change_plan

    metadata = mapped_metadata()
    metadata.entities.append(CanonicalEntity(name="Fieldless"))
    metadata.operations[0].response_entity = entity_name
    output = tmp_path / "absent" / "app"
    with pytest.raises(ValueError, match="getAccount.*no resolved returned entity with fields"):
        if entry == "generate":
            generate_application(metadata, output)
        elif entry == "plan":
            build_change_plan(metadata=metadata, package_dir=output)
        else:
            apply_change_plan(metadata=metadata, package_dir=output, approved_plan_hash="unused")
    assert not output.parent.exists()


@pytest.mark.parametrize("profile", list(TARGET_PROFILES))
@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("defect", ["foreign-id", "filtered-list", "custom-header", "body", "bad-reference"])
@pytest.mark.parametrize("entry", ["generate", "plan", "apply"])
def test_read_refusal_preserves_output_at_all_entry_points(tmp_path, profile, mixed, defect, entry):
    from appbuilder.generation import generate_application
    from appbuilder.generation.apply import apply_change_plan
    from appbuilder.generation.change_plan import build_change_plan

    metadata = mapped_metadata(profile, mixed=mixed)
    output = tmp_path / "app"
    generate_application(metadata, output, generation_run_id="read-supported")
    sentinel = output / "developer-owned.txt"
    sentinel.write_text("unchanged developer content\n")
    sentinel.chmod(0o444)
    plan = build_change_plan(metadata=metadata, package_dir=output)
    before = snapshot(output)
    before_dirs = {str(path.relative_to(output)) for path in output.rglob("*") if path.is_dir()}
    operation = metadata.operations[0]
    if defect == "foreign-id":
        operation.path = "/customers/{id}"
    elif defect == "filtered-list":
        operation = metadata.operations[1]
        operation.operation_parameters = [OperationParameter(name="owner", location=OperationParameterLocation.QUERY)]
    elif defect == "custom-header":
        operation.operation_parameters = [OperationParameter(name="X-Owner", location=OperationParameterLocation.HEADER)]
    elif defect == "body":
        operation.has_request_body = True
    else:
        operation.read_input_errors = ["unresolved parameter reference"]
    try:
        with pytest.raises(ValueError, match="Read operation"):
            if entry == "generate":
                generate_application(metadata, output, generation_run_id="read-unsupported")
            elif entry == "plan":
                build_change_plan(metadata=metadata, package_dir=output)
            else:
                apply_change_plan(metadata=metadata, package_dir=output,
                                  approved_plan_hash=plan["plan_hash"], generation_run_id="read-unsupported")
        assert snapshot(output) == before
        assert {str(path.relative_to(output)) for path in output.rglob("*") if path.is_dir()} == before_dirs
        absent = tmp_path / "not-created" / "app"
        with pytest.raises(ValueError, match="Read operation"):
            generate_application(metadata, absent, generation_run_id="read-unsupported")
        assert not absent.parent.exists()
    finally:
        sentinel.chmod(0o644)


def test_shipped_selected_get_resolves_annotated_headers_and_keeps_route(tmp_path):
    from appbuilder.generation import generate_application
    from appbuilder.metadata import build_metadata_project

    metadata = build_metadata_project("examples/input-projects/obie-wire-transfer/app-definition.yaml")
    operation = next(op for op in metadata.operations if op.http_method == HttpMethod.GET)
    assert operation.read_input_errors == []
    roles = {parameter.name: parameter.read_input_role for parameter in operation.operation_parameters}
    assert roles == {
        "x-fapi-auth-date": "metadata", "x-fapi-customer-ip-address": "metadata",
        "x-fapi-interaction-id": "metadata", "x-customer-user-agent": "metadata",
        "x-client-id": "gateway-rate-limit",
    }
    generate_application(metadata, tmp_path / "app", generation_run_id="shipped-read")
    controller = next((tmp_path / "app").rglob("InternationalPaymentController.java")).read_text()
    assert '@RequestMapping("/international-payments")' in controller
    assert '@GetMapping("/{InternationalPaymentId}")' in controller
    assert '@PathVariable("InternationalPaymentId") String internationalPaymentId' in controller
    assert '@RequestHeader(name = "Authorization"' not in controller


def test_unselected_bad_parameter_reference_does_not_block_selected_operation(tmp_path):
    import json

    from appbuilder.generation import generate_application
    from appbuilder.metadata import build_metadata_project
    from tests.unit.test_operation_parameters import _write_parameter_project

    manifest = _write_parameter_project(tmp_path / "project", spec_with_parameters=True)
    spec_path = manifest.parent / "contracts/customer-api-spec.json"
    spec = json.loads(spec_path.read_text())
    for item in spec["paths"].values():
        if "get" in item:
            item["get"]["parameters"] = [p for p in item["get"]["parameters"] if p["in"] == "path"]
    spec["paths"]["/unselected"] = {"get": {"operationId": "unselected", "parameters": [{"$ref": "#/missing"}]}}
    spec_path.write_text(json.dumps(spec))
    metadata = build_metadata_project(manifest)
    assert "unselected" not in {op.name for op in metadata.operations}
    generate_application(metadata, tmp_path / "app", generation_run_id="selected-only")


def account():
    return CanonicalEntity(name="Account", fields=[
        CanonicalField(name="id", type=CanonicalFieldType.STRING, is_id=True),
        CanonicalField(name="customerId", type=CanonicalFieldType.STRING),
    ])


def read_context(name="getAccount", path="/accounts/{id}", shape=ResponseShape.SINGLE):
    import re

    return {
        "operation_name": name,
        "interface_name": "api",
        "java_operation_name": name,
        "request_class_name": name[:1].upper() + name[1:] + "Request",
        "response_class_name": name[:1].upper() + name[1:] + "Response",
        "path": "/accounts",
        "spec_path": path,
        "request_field_mappings": [],
        "response_field_mappings": [],
        "http_method": HttpMethod.GET,
        "response_shape": shape,
        "path_parameters": [PathParameter(name=n) for n in re.findall(r"\{([^}]+)\}", path)],
        "operation_parameters": [],
    }


def render_service(contexts):
    entity = account()
    metadata = MetadataProject(app_name="Reads", bounded_context="reads",
                               target_profile="springboot-legacy-compatible", entities=[entity])
    return _render_service(metadata=metadata, entity=entity, root_package="example.reads",
                           op_contexts=contexts, id_java_type="String",
                           target_profile=TARGET_PROFILES[metadata.target_profile],
                           source_manifest="test", generation_run_id="read-contract")


def test_p1_foreign_resource_id_cannot_return_an_unrelated_account():
    # CUST-1 can also be an Account.id owned by CUST-9; findById(customerId)
    # would return that wrong row rather than implement an owner-scoped lookup.
    with pytest.raises(ValueError, match="[Rr]ead.*getAccount"):
        render_service([read_context(path="/customers/{customerId}")])


def test_p1_owner_filtered_collection_cannot_return_every_owners_records():
    with pytest.raises(ValueError, match="[Rr]ead.*listAccounts"):
        render_service([read_context("listAccounts", "/customers/{customerId}/accounts",
                                     ResponseShape.LIST)])


@pytest.mark.parametrize("name", ["getAccount", "fetchAccount", "readAccount", "accountSummary", "createAccount", "updateAccount"])
@pytest.mark.parametrize("path", ["/customers/{id}", "/customers/{customerId}", "/accounts/{number}", "/customers/{ownerId}/accounts/{id}"])
def test_single_read_cannot_bypass_binding_by_name(name, path):
    with pytest.raises(ValueError, match="[Rr]ead"):
        render_service([read_context(name, path)])


@pytest.mark.parametrize("name", ["listAccounts", "readAccounts", "accountHistory", "createAccounts"])
@pytest.mark.parametrize("location", [OperationParameterLocation.QUERY, OperationParameterLocation.HEADER])
def test_collection_selectors_are_not_ignored(name, location):
    ctx = read_context(name, "/accounts", ResponseShape.LIST)
    ctx["operation_parameters"] = [OperationParameter(name="ownerId", location=location)]
    with pytest.raises(ValueError, match="[Rr]ead"):
        render_service([ctx])


def openapi_read(parameters, *, components=None, body=False, security=None):
    operation = {"operationId": "getAccount", "parameters": parameters,
                 "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}}}
    if body:
        operation["requestBody"] = {"$ref": "#/components/requestBodies/Selector"}
    if security is not None:
        operation["security"] = security
    spec = {"openapi": "3.0.3", "paths": {"/accounts/{id}": {"get": operation}},
            "components": components or {}}
    operation["parameters"] = [{"name": "id", "in": "path", "required": True,
                                "schema": {"type": "string"}}, *parameters]
    return ingest_openapi_operations(spec, "api")[0], spec


def operation_context(operation):
    ctx = read_context()
    ctx.update(operation_parameters=operation.operation_parameters,
               read_input_errors=operation.read_input_errors,
               has_request_body=operation.has_request_body)
    return ctx


@pytest.mark.parametrize("role", ["metadata", "gateway-rate-limit"])
@pytest.mark.parametrize("referenced", [False, True])
@pytest.mark.parametrize("name", ["X-Correlation-Id", "x-correlation-ID"])
def test_explicit_header_classification_survives_ingestion(role, referenced, name):
    parameter = {"name": name, "in": "header", "schema": {"type": "string"},
                 "x-edgeforge-read-input-role": role}
    operation, _ = openapi_read(
        [{"$ref": "#/components/parameters/Trace"}] if referenced else [parameter],
        components={"parameters": {"Trace": parameter}},
    )
    assert operation.read_input_errors == []
    assert operation.operation_parameters[0].read_input_role == role
    assert operation.model_dump()["operation_parameters"][0]["read_input_role"] == role
    assert "accountRepository.findById(id)" in render_service([operation_context(operation)])


@pytest.mark.parametrize("name", ["Authorization", "authorization", "AUTHORIZATION", "Accept", "aCCept", "Content-Type", "CONTENT-TYPE"])
def test_special_header_parameters_do_not_generate_authentication(name):
    operation, spec = openapi_read([{"name": name, "in": "header", "required": True,
                                    "schema": {"type": "string"}}], security=[{"Bearer": []}])
    assert operation.operation_parameters == []
    assert spec["paths"]["/accounts/{id}"]["get"]["security"] == [{"Bearer": []}]
    source = render_service([operation_context(operation)])
    assert "accountRepository.findById(id)" in source
    assert "Authorization" not in source


@pytest.mark.parametrize("role", [None, "", "selector", "Metadata", True, [], {}])
def test_invalid_or_unknown_header_classification_refused(role):
    parameter = {"name": "X-Owner", "in": "header", "schema": {"type": "string"}}
    if role is not None:
        parameter["x-edgeforge-read-input-role"] = role
    operation, _ = openapi_read([parameter])
    with pytest.raises(ValueError, match="[Rr]ead"):
        render_service([operation_context(operation)])


@pytest.mark.parametrize("location", ["query", "cookie", "path"])
def test_header_extension_never_exempts_other_selector_locations(location):
    operation, _ = openapi_read([{"name": "owner", "in": location,
                                 "schema": {"type": "string"},
                                 "x-edgeforge-read-input-role": "metadata"}])
    with pytest.raises(ValueError, match="[Rr]ead"):
        render_service([operation_context(operation)])


@pytest.mark.parametrize("parameter,components", [
    ({"$ref": "#/components/parameters/Missing"}, {}),
    ({"$ref": "#/components/parameters/A"}, {"parameters": {"A": {"$ref": "#/components/parameters/A"}}}),
    ({"$ref": "../../outside.json#/Selector"}, {}),
    ({"$ref": "https://example.invalid/parameter"}, {}),
    ({"$ref": 12}, {}),
    ({"$ref": "#/components/parameters/A~2"}, {}),
    ({"name": "owner", "in": []}, {}),
    (None, {}),
])
def test_malformed_or_unresolved_parameter_is_not_erased(parameter, components):
    operation, _ = openapi_read([parameter], components=components)
    assert operation.read_input_errors
    with pytest.raises(ValueError, match="[Rr]ead"):
        render_service([operation_context(operation)])


def test_role_on_reference_sibling_cannot_classify_parameter():
    operation, _ = openapi_read(
        [{"$ref": "#/components/parameters/Owner", "x-edgeforge-read-input-role": "metadata"}],
        components={"parameters": {"Owner": {"name": "X-Owner", "in": "header", "schema": {"type": "string"}}}},
    )
    assert operation.read_input_errors


def test_body_reference_cannot_disappear_before_refusal():
    operation, _ = openapi_read([], body=True)
    assert operation.has_request_body
    with pytest.raises(ValueError, match="request-body"):
        render_service([operation_context(operation)])


def test_security_usage_contradicts_metadata_header():
    operation, _ = openapi_read(
        [{"name": "X-Client", "in": "header", "schema": {"type": "string"},
          "x-edgeforge-read-input-role": "gateway-rate-limit"}],
        components={"securitySchemes": {"Client": {"type": "apiKey", "in": "header", "name": "x-client"}}},
        security=[{"Client": []}],
    )
    with pytest.raises(ValueError, match="contradicts"):
        render_service([operation_context(operation)])


@pytest.mark.parametrize("path", ["/accounts/{other}", "/accounts/{id}/../secret", "/accounts/{id};matrix=x", '/accounts/{id}/bad"literal', "/accounts/{id}/%2f", "/accounts/{id}/a b"])
def test_unsupported_read_routes_refused(path):
    ctx = read_context()
    ctx["spec_path"] = path
    with pytest.raises(ValueError, match="[Rr]ead"):
        render_service([ctx])


def test_supported_reads_still_render_lookup_and_unfiltered_collection():
    source = render_service([read_context()])
    assert "accountRepository.findById(id)" in source
    source = render_service([read_context("listAccounts", "/accounts", ResponseShape.LIST)])
    assert "accountRepository.findAll()" in source


def test_ambiguous_route_inference_cannot_establish_persistence_identity():
    from appbuilder.metadata.translation import _normalize_entity_id_fields

    entity = account()
    from appbuilder.metadata.models import CanonicalOperation
    operation = CanonicalOperation(name="getAccount", interface_name="api", request_entity="Account",
                                   http_method=HttpMethod.GET, path="/accounts/{customerId}",
                                   path_parameters=[PathParameter(name="customerId")])
    _normalize_entity_id_fields([entity], operations=[operation], mappings=[], identity_overrides={})
    assert next(field.name for field in entity.fields if field.is_id) == "customerId"
    assert entity.read_identity_verified is False
    assert entity.model_validate(entity.model_dump()).read_identity_verified is False


@pytest.mark.parametrize("path", ["/a.ccounts/{id}", "/a:ccounts/{id}", "/a+ccounts/{id}"])
def test_punctuation_is_not_an_inferred_resource_alias(path):
    with pytest.raises(ValueError, match="own resource"):
        render_service([read_context(path=path)])


@pytest.mark.parametrize("name", ['X-Owner"', "X-Owner\n", "X-Owner:Value", "id"])
def test_classified_header_cannot_inject_or_collide_with_path_argument(name):
    ctx = read_context()
    ctx["operation_parameters"] = [OperationParameter(
        name=name, location=OperationParameterLocation.HEADER, read_input_role="metadata",
    )]
    with pytest.raises(ValueError, match="Read operation"):
        render_service([ctx])


def test_path_and_operation_header_overrides_use_case_insensitive_names():
    from appbuilder.ingestion.openapi_classifier import _merge_parameter_definitions

    errors = []
    first = {"name": "X-Trace", "in": "header", "schema": {"type": "string"},
             "x-edgeforge-read-input-role": "metadata"}
    second = {**first, "name": "x-trace", "x-edgeforge-read-input-role": "gateway-rate-limit"}
    parameters = _merge_parameter_definitions(
        {"parameters": [first]}, {"parameters": [{"$ref": "#/components/parameters/Trace"}]},
        spec={"components": {"parameters": {"Trace": second}}}, errors=errors,
    )
    assert parameters == [second]
    assert errors == []


def test_ref_failure_diagnostics_survive_canonical_round_trip():
    operation, _ = openapi_read([{"$ref": "#/missing"}])
    restored = CanonicalOperation.model_validate(operation.model_dump())
    assert restored.read_input_errors == operation.read_input_errors
    with pytest.raises(ValueError, match="unresolved parameter reference"):
        render_service([operation_context(restored)])


def test_classified_header_cannot_be_mapped_to_a_record_field():
    ctx = read_context()
    ctx["operation_parameters"] = [OperationParameter(
        name="X-Owner", location=OperationParameterLocation.HEADER, read_input_role="metadata",
    )]
    ctx["request_field_mappings"] = [FieldMapping(
        direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api",
        operation_name="getAccount", source_path="api.getAccount.request.headers.x-owner",
        target_path="Account.customerId",
    )]
    with pytest.raises(ValueError, match="contradict"):
        render_service([ctx])


@pytest.mark.parametrize("computed", [False, True])
@pytest.mark.parametrize("field", ["request", "result"])
def test_response_property_is_not_a_request_selector(tmp_path, computed, field):
    import json

    import yaml

    from appbuilder.generation import generate_application
    from appbuilder.generation.java_emitter import _operation_contexts_for_entity
    from appbuilder.metadata import build_metadata_project

    root = tmp_path / "input"
    root.mkdir()
    name = "accountSummary" if computed else "getAccount"
    path = "/accounts/{id}/summary" if computed else "/accounts/{id}"
    manifest = {
        "schema_version": "2.0", "app_name": "Reads", "bounded_context": "reads",
        "target_profile": "springboot-legacy-compatible",
        "identity_overrides": [{"entity": "Account", "persistence_id": "id"}],
        "upstream_interfaces": [{
            "name": "api", "system": "Reads", "type": "rest-json",
            "spec": "spec.yaml", "mapping": "mapping.yaml",
            "operations": [{"name": name, "response_sample": "response.json"}],
        }],
    }
    spec = {"openapi": "3.0.3", "info": {"title": "Reads", "version": "1"},
            "paths": {path: {"get": {
                "operationId": name, "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
                ], "responses": {"200": {"description": "Account", "content": {
                    "application/json": {"schema": {"type": "object", "properties": {
                        field: {"type": "object", "properties": {"id": {"type": "string"}}},
                        "customerId": {"type": "string"},
                    }}},
                }}},
            }}}}
    mapping = {"interface": "api", "entity": "Account", "operations": [{
        "name": name, "response_mappings": [
            {"source": field + ".id", "target": "Account.id"},
            {"source": "customerId", "target": "Account.customerId"},
        ],
    }]}
    for filename, content in {"app-definition.yaml": manifest, "spec.yaml": spec,
                              "mapping.yaml": mapping}.items():
        (root / filename).write_text(yaml.safe_dump(content, sort_keys=False))
    (root / "response.json").write_text(json.dumps({field: {"id": "ACC-7"}, "customerId": "CUST-1"}))
    metadata = build_metadata_project(root / "app-definition.yaml")
    assert not metadata.operations[0].has_request_body
    assert all(report.status == "complete" for report in metadata.mapping_reports)
    context, = _operation_contexts_for_entity(metadata, metadata.entities[0])
    assert context["raw_request_field_mappings"] == []
    assert {m.source_path for m in context["response_field_mappings"]} == {
        f"api.{name}.response.{field}.id", f"api.{name}.response.customerId",
    }
    report = generate_application(metadata, tmp_path / "app", generation_run_id="response-context")
    assert report.harness_report is not None and report.harness_report.passed
    service = next((tmp_path / "app").rglob("AccountServiceBase.java")).read_text()
    assert "accountRepository.findById(id)" in service
    next((tmp_path / "app").rglob(name[:1].upper() + name[1:] + "Response.java")).unlink()
    from appbuilder.harness import run_compatibility_harness

    check = next(c for c in run_compatibility_harness(metadata, tmp_path / "app").checks
                 if c.name == "upstream_response_dto_fields_match_contract")
    assert not check.passed


@pytest.mark.parametrize("source,expected", [
    ("api.getAccount.request.id", "request"),
    ("api.getAccount.request.response.id", "request"),
    ("api.getAccount.response.request.id", "response"),
    ("api.getAccount.response.result.id", "response"),
    ("other.getAccount.request.id", None),
    ("api.otherOperation.request.id", None),
    ("api.getAccount.request", None),
    ("api.getAccount.response.", None),
    ("api.getAccount.payload.request.id", None),
])
def test_transport_context_uses_the_selected_operation_prefix(source, expected):
    from appbuilder.generation.utils import operation_mapping_transport_context

    assert operation_mapping_transport_context(source, "api", "getAccount") == expected


@pytest.mark.parametrize("source,role", [
    ("api.getAccount.request.id", "request"),
    ("api.getAccount.request.response.id", "request"),
    ("api.getAccount.response.request.id", "response"),
    ("other.getAccount.request.id", "request"),
    ("other.getAccount.response.request.id", "request"),
])
def test_static_harness_uses_the_same_transport_context_boundary(source, role):
    from appbuilder.harness.checks import _upstream_role_mappings

    metadata = mapped_metadata()
    mapping = FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                           contract_name="api", operation_name="getAccount",
                           source_path=source, target_path="Account.id")
    metadata.mappings = [mapping]
    for candidate in ("request", "response"):
        assert _upstream_role_mappings(metadata, metadata.operations[0], role=candidate) == (
            [mapping] if candidate == role else []
        )


@pytest.mark.parametrize("computed", [False, True])
@pytest.mark.parametrize("source", [
    "api.getAccount.request.headers.id", "api.getAccount.request.payload.id",
    "api.getAccount.request.response.id", "other.getAccount.request.id",
    "api.otherOperation.request.id", "api.getAccount.payload.id",
    "api.getAccount.request", "api.getAccount.response.",
    "other.getAccount.response.request.id",
])
def test_invalid_mapping_context_remains_visible_before_output_mutation(tmp_path, computed, source):
    from appbuilder.generation import generate_application

    metadata = mapped_metadata()
    if computed:
        metadata.operations[0].path += "/summary"
    output = tmp_path / "app"
    generate_application(metadata, output, generation_run_id="before-context-error")
    before = snapshot(output)
    metadata.mappings.append(FieldMapping(
        direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api",
        operation_name="getAccount", source_path=source, target_path="Account.id",
    ))
    with pytest.raises(ValueError, match="contradictory"):
        generate_application(metadata, output, generation_run_id="invalid-context")
    assert snapshot(output) == before
    with pytest.raises(ValueError, match="contradictory"):
        generate_application(metadata, tmp_path / "absent", generation_run_id="invalid-context")
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("computed", [False, True])
def test_exact_path_id_mapping_remains_supported(tmp_path, computed):
    from appbuilder.generation import generate_application
    from appbuilder.generation.java_emitter import _operation_contexts_for_entity

    metadata = mapped_metadata()
    if computed:
        metadata.operations[0].path += "/summary"
    mapping = FieldMapping(direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                           contract_name="api", operation_name="getAccount",
                           source_path="api.getAccount.request.id", target_path="Account.id")
    metadata.mappings.append(mapping)
    context = _operation_contexts_for_entity(metadata, metadata.entities[0])[0]
    assert context["raw_request_field_mappings"] == [mapping]
    assert all(".request." not in m.source_path for m in context["response_field_mappings"])
    generate_application(metadata, tmp_path / "app", generation_run_id="exact-id-context")
    assert "accountRepository.findById(id)" in next((tmp_path / "app").rglob("AccountServiceBase.java")).read_text()


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("entry", ["generate", "plan", "apply"])
def test_computed_header_uses_the_same_binding_at_preflight_and_render(tmp_path, mixed, entry):
    from appbuilder.generation import generate_application
    from appbuilder.generation.apply import apply_change_plan
    from appbuilder.generation.change_plan import build_change_plan

    metadata = mapped_metadata(mixed=mixed)
    operation = metadata.operations[0]
    operation.path = "/accounts/{id}/summary"
    output = tmp_path / "app"
    generate_application(metadata, output, generation_run_id="before")
    operation.operation_parameters = [OperationParameter(
        name="X-Trace", location=OperationParameterLocation.HEADER, read_input_role="metadata",
    )]
    plan = build_change_plan(metadata=metadata, package_dir=output)
    if entry == "apply":
        apply_change_plan(metadata=metadata, package_dir=output,
                          approved_plan_hash=plan["plan_hash"], generation_run_id="after")
    elif entry == "generate":
        generate_application(metadata, output, generation_run_id="after")
    service = next(output.rglob("AccountServiceBase.java")).read_text()
    if entry != "plan":
        assert "getAccount(String id, String xTrace)" in service
        assert ".findById(id)" in service
    before = snapshot(output)
    operation.operation_parameters[0].read_input_role = None
    with pytest.raises(ValueError):
        generate_application(metadata, output, generation_run_id="refused")
    assert snapshot(output) == before


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("pageable", [False, True])
def test_static_list_suffix_is_faithful_on_both_surfaces(tmp_path, mixed, pageable):
    import json
    import re

    from appbuilder.generation import generate_application

    metadata = mapped_metadata(mixed=mixed, pageable=pageable)
    metadata.operations[1].path = "/accounts/history"
    generate_application(metadata, tmp_path / "app", generation_run_id="static-list")
    controller = next((tmp_path / "app").rglob("AccountController.java")).read_text()
    assert '@RequestMapping("/accounts")' in controller
    assert '@GetMapping("/history")' in controller
    console = (tmp_path / "app/src/main/resources/static/index.html").read_text()
    descriptors = json.loads(re.search(r"const DESCRIPTORS = (\[.*?\]);\n    const DESCRIPTOR_BY_KEY", console, re.S).group(1))
    assert next(item for item in descriptors if item["coverageKey"] == "Account-list")["actions"][0]["endpoint"] == "/accounts/history"


@pytest.mark.parametrize("kind", ["get", "list"])
def test_multiple_mixed_crud_reads_are_not_silently_dropped(tmp_path, kind):
    from appbuilder.generation import generate_application

    metadata = mapped_metadata(mixed=True)
    original = metadata.operations[0 if kind == "get" else 1]
    extra = original.model_copy(deep=True)
    extra.name = "fetchAccount" if kind == "get" else "listAccountHistory"
    extra.path += "/history" if kind == "list" else ""
    metadata.operations.append(extra)
    metadata.mappings.extend([mapping.model_copy(update={"operation_name": extra.name})
                              for mapping in metadata.mappings if mapping.operation_name == original.name])
    with pytest.raises(ValueError, match="multiple selected CRUD reads"):
        generate_application(metadata, tmp_path / "app", generation_run_id="multiple")
    assert not (tmp_path / "app").exists()


@pytest.mark.parametrize("name", ["account", "class", "record", "records", "responses", "pageable",
                                  "getAccountResponse", "accountResponse", "accountRepository", "accountService", "id"])
def test_read_header_cannot_shadow_java_keywords_locals_or_members(tmp_path, name):
    from appbuilder.generation import generate_application

    metadata = mapped_metadata()
    output = tmp_path / "app"
    generate_application(metadata, output, generation_run_id="before")
    before = snapshot(output)
    metadata.operations[0].operation_parameters = [OperationParameter(
        name=name, location=OperationParameterLocation.HEADER, read_input_role="metadata",
    )]
    with pytest.raises(ValueError, match="Java keyword|collide"):
        generate_application(metadata, output, generation_run_id="unsafe-binding")
    assert snapshot(output) == before


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("entry", ["generate", "plan", "apply"])
@pytest.mark.parametrize("target", ["Account.id", "Other.id"])
@pytest.mark.parametrize("header,source_prefix", [("X-Owner", ""), ("X.id", ""), ("X.id", "headers."), ("X.Owner.id", ""), ("X.Owner.id", "headers.")])
def test_raw_duplicate_target_mappings_cannot_hide_a_header_selector(tmp_path, reverse, entry, target, header, source_prefix):
    from appbuilder.generation import generate_application
    from appbuilder.generation.apply import apply_change_plan
    from appbuilder.generation.change_plan import build_change_plan

    metadata = mapped_metadata()
    output = tmp_path / "app"
    generate_application(metadata, output, generation_run_id="before")
    before = snapshot(output)
    plan = build_change_plan(metadata=metadata, package_dir=output)
    operation = metadata.operations[0]
    operation.operation_parameters = [OperationParameter(
        name=header, location=OperationParameterLocation.HEADER, read_input_role="metadata",
    )]
    sources = ["id", source_prefix + header]
    if reverse:
        sources.reverse()
    metadata.mappings.extend([FieldMapping(
        direction=MappingDirection.UPSTREAM_TO_CANONICAL, contract_name="api",
        operation_name=operation.name, source_path=f"api.{operation.name}.request.{source}",
        target_path=target,
    ) for source in sources])
    with pytest.raises(ValueError, match="contradicts|contradictory"):
        if entry == "generate":
            generate_application(metadata, output, generation_run_id="raw-mapping")
        elif entry == "plan":
            build_change_plan(metadata=metadata, package_dir=output)
        else:
            apply_change_plan(metadata=metadata, package_dir=output,
                              approved_plan_hash=plan["plan_hash"], generation_run_id="raw-mapping")
    assert snapshot(output) == before


@pytest.mark.parametrize("index", [0, 1])
def test_exact_duplicate_primary_read_can_still_be_deduplicated(tmp_path, index):
    from appbuilder.generation import generate_application

    metadata = mapped_metadata(mixed=True)
    metadata.operations.append(metadata.operations[index].model_copy(deep=True))
    generate_application(metadata, tmp_path / "app", generation_run_id="duplicate-read")
    controller = next((tmp_path / "app").rglob("AccountController.java")).read_text()
    assert controller.count('    @GetMapping("/{id}")') == 1


@pytest.mark.parametrize("reference", ["valid", "missing", "cyclic", "external", "malformed"])
def test_active_security_scheme_reference_cannot_hide_header_usage(reference):
    header = {"name": "X-Owner", "in": "header", "schema": {"type": "string"},
              "x-edgeforge-read-input-role": "metadata"}
    schemes = {
        "Owner": {"$ref": "#/components/securitySchemes/Definition"},
        "Definition": {"type": "apiKey", "in": "header", "name": "x-owner"},
    }
    if reference == "missing":
        del schemes["Definition"]
    elif reference == "cyclic":
        schemes["Definition"] = {"$ref": "#/components/securitySchemes/Owner"}
    elif reference == "external":
        schemes["Owner"] = {"$ref": "../private.yaml"}
    elif reference == "malformed":
        schemes["Definition"] = {"type": "apiKey", "in": "header", "name": []}
    operation, _ = openapi_read([header], components={"securitySchemes": schemes}, security=[{"Owner": []}])
    with pytest.raises(ValueError, match="contradicts|cannot verify"):
        render_service([operation_context(operation)])


@pytest.mark.parametrize("profile", list(TARGET_PROFILES))
def test_runtime_console_proof_respects_the_profile_boundary(tmp_path, profile):
    from appbuilder.generation import generate_application
    from scripts.smoke.read_contract_proof import _verify_console_list_endpoint

    metadata = mapped_metadata(profile, mixed=True)
    metadata.operations[1].path = "/accounts/history"
    generate_application(metadata, tmp_path / "app", generation_run_id="console-profile")
    expected = "/accounts/history" if TARGET_PROFILES[profile].emit_test_console else None
    assert _verify_console_list_endpoint(tmp_path / "app", profile) == expected


def test_runtime_console_proof_does_not_ignore_missing_or_wrong_required_console(tmp_path):
    from appbuilder.generation import generate_application
    from scripts.smoke.read_contract_proof import _verify_console_list_endpoint

    profile = "springboot-legacy-compatible"
    with pytest.raises(AssertionError, match="Required generated console"):
        _verify_console_list_endpoint(tmp_path / "missing", profile)
    generate_application(mapped_metadata(), tmp_path / "app", generation_run_id="wrong-console-route")
    with pytest.raises(AssertionError, match="does not match"):
        _verify_console_list_endpoint(tmp_path / "app", profile)
