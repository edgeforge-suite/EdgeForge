"""Selected REST write support-or-refuse boundary; no filesystem or network work."""
from __future__ import annotations

import re
from typing import Literal

from appbuilder.core import AppArchetype
from appbuilder.mapping import MappingDirection
from appbuilder.metadata.models import HttpMethod

from .utils import JAVA_RESERVED_IDENTIFIERS, entity_id_field, to_snake_case


def refuse(interface: str, operation: str, element: str) -> None:
    raise ValueError(f"Write operation '{operation}' on interface '{interface}' is unsupported: {element}. "
                     "Use a supported transport contract or remove the selected operation; "
                     "no query, conditional-write, authentication or action semantics are inferred.")


def safe_route(path: str, interface: str, operation: str) -> None:
    if (not isinstance(path, str) or not path.startswith("/") or path.endswith("/")
            or any(part in {"", ".", ".."} for part in path[1:].split("/"))
            or not re.fullmatch(r"/[A-Za-z0-9_/{\}-]+", path)):
        refuse(interface, operation, f"route {path!r} has unsupported syntax or unsafe Java literals")
    for segment in path[1:].split("/"):
        if ("{" in segment or "}" in segment) and not re.fullmatch(r"\{[A-Za-z_][A-Za-z0-9_]*\}", segment):
            refuse(interface, operation, "route variables must occupy complete literal segments")
    names = re.findall(r"\{([^}]+)\}", path)
    if len(names) != len(set(names)):
        refuse(interface, operation, "route repeats a variable")


def _body_object(value: dict | None) -> bool:
    if not value or not isinstance(value.get("content"), dict):
        return False
    return any(
        key.split(";", 1)[0].strip().lower() in {"application/json", "application/*", "*/*"} and isinstance(media, dict)
        and isinstance(media.get("schema"), dict)
        and (media["schema"].get("type") == "object" or "properties" in media["schema"])
        for key, media in value["content"].items()
    )


def passthrough_success_response(contract: dict, response_fields: list) -> tuple[str, bool]:
    interface, operation = contract["interface"], contract["operation"]
    if contract.get("errors"):
        refuse(interface, operation, "; ".join(contract["errors"]))
    responses = contract.get("responses", {})
    if len(responses) != 1 or next(iter(responses), None) not in {"200", "202"}:
        refuse(interface, operation, "passthrough requires one declared success response, 200 or 202")
    status, response = next(iter(responses.items()))
    if not isinstance(response, dict):
        refuse(interface, operation, "passthrough success response is malformed")
    if not response.get("content"):
        if response_fields:
            refuse(interface, operation, "canonical response fields contradict no response content")
        return status, False
    if not _body_object(response):
        refuse(interface, operation, "passthrough success response requires a JSON object or no content")
    return status, True


def passthrough_operation_response(metadata, operation) -> tuple[str, bool]:
    if operation.http_method != HttpMethod.POST:
        return "200", True  # This correction is limited to selected POST writes.
    matches = [contract for contract in metadata.selected_rest_contracts
               if (contract["interface"], contract["operation"]) == (operation.interface_name, operation.name)]
    if not matches:
        return "200", True  # Preserve genuine sample-only/no-source transport.
    if len(matches) != 1:
        refuse(operation.interface_name, operation.name, "passthrough response contract is ambiguous")
    return passthrough_success_response(matches[0], operation.response_fields)


def _transport(contract: dict, category: str, parameters: list, response_fields: list) -> None:
    interface, operation = contract["interface"], contract["operation"]
    if contract.get("errors"):
        refuse(interface, operation, "; ".join(contract["errors"]))
    expected = {"create": ("POST", "201", True), "update": ("PUT", "200", True),
                "delete": ("DELETE", "204", False), "passthrough": ("POST", "200", True)}
    if category not in expected:
        refuse(interface, operation, "dispatch has no supported write handler")
    method, status, has_body = expected[category]
    if contract["method"] != method:
        refuse(interface, operation, f"declared method {contract['method']} would dispatch as {method}")
    body = contract.get("body")
    if has_body:
        if not _body_object(body) or body.get("required") is not True:
            refuse(interface, operation, "handler requires a required JSON-object request body")
    elif body is not None:
        refuse(interface, operation, "DELETE handler cannot consume a declared request body")
    if category == "passthrough":
        passthrough_success_response(contract, response_fields)
    else:
        responses = contract.get("responses", {})
        response = responses.get(status)
        if not isinstance(response, dict) or (_body_object(response) if has_body else not response.get("content")) is not True:
            refuse(interface, operation, f"handler emits {status} {'with JSON object' if has_body else 'without body'}; incompatible success response")
    raw = contract.get("parameters", [])
    paths = re.findall(r"\{([^}]+)\}", contract["path"])
    declared = [param["name"] for param in raw if param["in"] == "path"]
    if sorted(paths) != sorted(declared):
        refuse(interface, operation, "declared path parameters do not match route placeholders")
    for param in raw:
        name, location = param["name"], param["in"]
        schema = param.get("schema", {})
        if (not isinstance(schema, dict) or schema.get("type") not in {"string", "integer", "number", "boolean"}
                or "$ref" in schema or "content" in param or "default" in schema
                or schema.get("nullable") is True):
            refuse(interface, operation, f"input '{name}' requires a supported non-null scalar schema without defaults")
        if location not in {"path", "header", "query"}:
            refuse(interface, operation, f"{location} input '{name}' is unsupported")
        if "required" in param and not isinstance(param["required"], bool):
            refuse(interface, operation, f"input '{name}' has malformed requiredness")
        style = {"path": "simple", "header": "simple", "query": "form"}[location]
        if param.get("style", style) != style or param.get("allowReserved") or param.get("allowEmptyValue"):
            refuse(interface, operation, f"input '{name}' has unsupported serialization")
        if "explode" in param and not isinstance(param["explode"], bool):
            refuse(interface, operation, f"input '{name}' has malformed serialization")
        if location == "path" and (param.get("required") is not True or schema["type"] not in {"string", "integer"}):
            refuse(interface, operation, f"path input '{name}' must be required string/integer")
        if location == "header" and name.lower() in {"if-match", "if-none-match", "if-modified-since", "if-unmodified-since", "range", "if-range"}:
            refuse(interface, operation, f"precondition '{name}' is not enforced by the generated handler")
        if location != "path":
            matches = [p for p in parameters if p.name == name and p.location.value == location]
            types = {"string": "string", "integer": "integer", "number": "decimal", "boolean": "boolean"}
            if (len(matches) != 1 or matches[0].required != param.get("required", False)
                    or matches[0].type.value != types[schema["type"]]
                    or matches[0].format != schema.get("format")):
                refuse(interface, operation, f"declared {location} input '{name}' was lost or changed during ingestion")
    if len(parameters) != sum(param["in"] != "path" for param in raw):
        refuse(interface, operation, "canonical inputs differ from the retained declared contract")


def _bindings(entity, ctx: dict) -> None:
    from .java_emitter import _java_parameter_name, _read_mapping_input_name
    interface, operation = ctx.get("interface_name", "unspecified"), ctx["operation_name"]
    entity_var = entity.name[:1].lower() + entity.name[1:]
    reserved = JAVA_RESERVED_IDENTIFIERS | {"id", "request", "saved", "response", "entity", "record", "created", "updated",
        entity_var, entity_var + "Repository", entity_var + "Service",
        ctx["response_class_name"][:1].lower() + ctx["response_class_name"][1:]}
    names = set()
    from .utils import canonical_field_name, contract_field_name
    for mapping in [*ctx.get("raw_request_field_mappings", ctx.get("request_field_mappings", [])),
                    *ctx.get("response_field_mappings", [])]:
        wire = contract_field_name(mapping)
        if any(character in {'"', '\\'} or ord(character) < 32 for character in wire):
            refuse(interface, operation, f"body wire field {wire!r} has unsupported Java-literal characters")
        if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", canonical_field_name(mapping)):
            refuse(interface, operation, "body mapping has an unsupported Java canonical-field identifier")
    for param in ctx.get("operation_parameters", []):
        argument = _java_parameter_name(param.name)
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+", param.name) or argument in reserved or argument in names
                or param.type.value not in {"string", "integer", "decimal", "boolean"}
                or param.format not in {None, "int32", "int64", "float", "double"}):
            refuse(interface, operation, f"input '{param.name}' has unsupported or conflicting Java binding")
        names.add(argument)
        if param.name.lower() in {"if-match", "if-none-match", "if-modified-since", "if-unmodified-since", "range", "if-range"}:
            refuse(interface, operation, f"precondition '{param.name}' is not implemented")
        if any((_read_mapping_input_name(mapping, ctx) or "").lower() == param.name.lower()
               for mapping in ctx.get("raw_request_field_mappings", ctx.get("request_field_mappings", []))):
            refuse(interface, operation, f"input '{param.name}' contradicts a canonical record mapping")


def _identity_binding(entity, ctx: dict) -> None:
    from .java_emitter import _java_type, _read_mapping_input_name
    from .utils import canonical_field_name
    interface, operation = ctx.get("interface_name", "unspecified"), ctx["operation_name"]
    ids = [field for field in entity.fields if field.is_id]
    parameters = ctx.get("path_parameters", [])
    if len(ids) != 1 or len(parameters) != 1 or parameters[0].type != _java_type(ids[0]):
        refuse(interface, operation, "item write requires exactly one correctly typed persistence-ID path input")
    field, parameter = ids[0], parameters[0]
    # An alias must not name a different modeled field or contradict an explicit
    # input mapping, even when it looks like the entity's customary ID spelling.
    if any(candidate.name.lower() == parameter.name.lower() and candidate.name != field.name
           for candidate in entity.fields):
        refuse(interface, operation, "path input names a business field rather than the persistence identity")
    mapped = [mapping for mapping in ctx.get("raw_request_field_mappings", ctx.get("request_field_mappings", []))
              if (_read_mapping_input_name(mapping, ctx) or "").lower() == parameter.name.lower()]
    if any(canonical_field_name(mapping) != field.name for mapping in mapped):
        refuse(interface, operation, "path input mapping contradicts the selected persistence identity")
    allowed = {"id", field.name.lower()}
    if field.name.lower() == "id" or mapped:
        allowed.add(entity.name.lower() + "id")
    if parameter.name.lower() not in allowed:
        refuse(interface, operation, "path input is not an unambiguous persistence ID (business-key writes unsupported)")


def validate_write_context(entity, ctx: dict, route_base: str | None) -> None:
    from .java_emitter import _java_type, _operation_category
    if ctx.get("http_method") in {None, HttpMethod.GET}:
        return
    interface, operation = ctx.get("interface_name", "unspecified"), ctx["operation_name"]
    _bindings(entity, ctx)
    category = _operation_category(ctx)
    path_params = ctx.get("path_parameters", [])
    path = ctx.get("spec_path")
    if category == "state_transition" or (category in {"update", "delete"} and (path or path_params)):
        _identity_binding(entity, ctx)
    elif category == "create" and path_params:
        refuse(interface, operation, "create cannot consume path selectors")
    expected_method = {"create": HttpMethod.POST, "update": HttpMethod.PUT, "delete": HttpMethod.DELETE,
                       "state_transition": HttpMethod.POST}.get(category)
    if expected_method != ctx["http_method"]:
        refuse(interface, operation, "HTTP method/name dispatch is not faithfully represented")
    if category == "delete" and ctx.get("has_request_body"):
        refuse(interface, operation, "DELETE handler cannot consume a declared request body")
    if not path:
        return  # Explicit HTTP contexts were checked above; genuine no-HTTP samples returned earlier.
    safe_route(path, interface, operation)
    if route_base is None:
        refuse(interface, operation, "declared route bases are incompatible; entity-route fallback is refused")
    if category == "create":
        if path_params or path != route_base:
            refuse(interface, operation, "create requires a faithful collection route with no path selectors")
    else:
        field = entity_id_field(entity)
        if len(path_params) != 1 or path_params[0].type != _java_type(field):
            refuse(interface, operation, "item write requires exactly one correctly typed persistence-ID path input")
        parameter = path_params[0]
        item = route_base + "/{" + parameter.name + "}"
        faithful = path == item if category != "state_transition" else path.startswith(item + "/")
        if not faithful:
            refuse(interface, operation, "item write would drop a prefix, suffix or selector")
        spellings = {entity.name.lower(), to_snake_case(entity.name), to_snake_case(entity.name).replace("_", "-")}
        collections = spellings | {spelling + "s" for spelling in spellings}
        if route_base.rsplit("/", 1)[-1].lower() not in collections:
            refuse(interface, operation, "item path does not name the selected entity's own collection")


def validate_write_contracts(
    metadata, *, target_profile=None,
    controller_scope: Literal["application", "java", "demo"] = "application",
) -> None:
    if metadata.app_archetype not in {AppArchetype.CRUD, AppArchetype.PASSTHROUGH_ROUTER}:
        return
    from appbuilder.target_profiles.catalog import TARGET_PROFILES

    from .batch_metadata import has_batch_jobs
    from .utils import all_entities, should_emit_demo_ui

    profile = target_profile or TARGET_PROFILES[metadata.target_profile]

    from .java_emitter import (
        _common_spec_route_base,
        _java_type,
        _operation_category,
        _operation_contexts_for_entity,
        _render_controller,
        _validate_computed_read_runtime_support,
    )
    contracts = metadata.selected_rest_contracts
    contexts, surfaces = {}, []
    # Inspect the retained source inventory before entity helpers can erase an
    # unsupported method or fail on an unmapped default-Record association.
    for contract in contracts:
        if contract.get("method") == "GET":
            continue
        interface, operation = contract["interface"], contract["operation"]
        if contract.get("errors"):
            refuse(interface, operation, "; ".join(contract["errors"]))
        if contract.get("method") not in {"POST", "PUT", "DELETE"}:
            refuse(interface, operation, f"selected method {contract.get('method')} is not supported")
        selected_ops = [op for op in metadata.operations if (op.interface_name, op.name) == (interface, operation)]
        if metadata.app_archetype == AppArchetype.CRUD and (
            len(selected_ops) != 1 or not any(entity.name == selected_ops[0].request_entity and entity.fields for entity in metadata.entities)
        ):
            refuse(interface, operation, "selected body is unmapped or attributed to a fieldless/default entity")
        if metadata.app_archetype == AppArchetype.CRUD:
            entity_name = selected_ops[0].request_entity
            mappings = [mapping for mapping in metadata.mappings
                        if mapping.direction == MappingDirection.UPSTREAM_TO_CANONICAL
                        and (mapping.contract_name, mapping.operation_name) == (interface, operation)]
            if any(not mapping.target_path.startswith(entity_name + ".") for mapping in mappings):
                refuse(interface, operation, "selected operation maps to multiple incompatible entity associations")
            if contract["method"] in {"POST", "PUT"} and not any(
                mapping.source_path.startswith(f"{interface}.{operation}.request.") for mapping in mappings
            ):
                refuse(interface, operation, "selected request body has no canonical field mappings")
    if metadata.app_archetype == AppArchetype.CRUD:
        _validate_computed_read_runtime_support(metadata)
        for entity in all_entities(metadata):
            if not entity.fields:
                continue
            items = _operation_contexts_for_entity(metadata, entity)
            base = _common_spec_route_base(items)
            categories = set()
            write_categories = [_operation_category(ctx) for ctx in items if ctx.get("http_method") not in {None, HttpMethod.GET}]
            primary_categories = [category for category in write_categories if category in {"create", "update", "delete"}]
            if len(primary_categories) != len(set(primary_categories)):
                context = next(ctx for ctx in items if ctx.get("http_method") not in {None, HttpMethod.GET})
                refuse(context["interface_name"], context["operation_name"], "additional selected write would be omitted by first-context selection")
            for ctx in items:
                if ctx.get("http_method") not in {None, HttpMethod.GET}:
                    category = _operation_category(ctx)
                    if category in categories and category in {"create", "update", "delete"}:
                        refuse(ctx["interface_name"], ctx["operation_name"], "additional selected write would be omitted by first-context selection")
                    categories.add(category)
                    validate_write_context(entity, ctx, base)
                    contexts.setdefault((ctx["interface_name"], ctx["operation_name"]), []).append(ctx)
            source = _render_controller(entity=entity, root_package="validation", op_contexts=items,
                entity_path_base=f"/{to_snake_case(entity.name)}s", id_java_type=_java_type(entity_id_field(entity)),
                target_profile=profile, source_manifest="validation", generation_run_id="validation")
            root = re.search(r'@RequestMapping\("([^"\n]*)"\)', source).group(1)
            for method, suffix in re.findall(r'@(Post|Put|Delete|Get)Mapping(?:\("([^"\n]*)"\))?', source):
                surfaces.append((method.upper(), root + suffix, entity.name + "Controller"))
    else:
        # The passthrough emitter selects the first upstream contract.
        from .passthrough_helpers import _upstream_contract_name
        name = _upstream_contract_name(metadata)
        for operation in metadata.operations:
            if operation.interface_name != name:
                continue
            if operation.http_method == HttpMethod.GET:
                surfaces.append(("GET", operation.path or "/", operation.name))
                continue
            if operation.path:
                safe_route(operation.path, name, operation.name)
            if operation.path_parameters or operation.operation_parameters:
                refuse(name, operation.name, "passthrough supports body-only input; declared path/header/query values have no developer transport seam")
            contexts.setdefault((name, operation.name), []).append({"operation_parameters": []})
            surfaces.append(((operation.http_method or HttpMethod.POST).value, operation.path or "/", operation.name))
    for contract in contracts:
        if contract.get("method") == "GET":
            continue
        interface, operation = contract["interface"], contract["operation"]
        if contract.get("errors"):
            refuse(interface, operation, "; ".join(contract["errors"]))
        matches = contexts.get((interface, operation), [])
        if len(matches) != 1:
            refuse(interface, operation, "selected operation has no unique emitted entity/handler (unmapped or omitted input)")
        ctx = matches[0]
        if metadata.app_archetype == AppArchetype.CRUD and ctx.get("spec_path") != contract.get("path"):
            refuse(interface, operation, "selected source route was lost during ingestion")
        operations = [op for op in metadata.operations if (op.interface_name, op.name) == (interface, operation)]
        if metadata.app_archetype == AppArchetype.CRUD and (
            len(operations) != 1 or not any(entity.name == operations[0].request_entity and entity.fields for entity in metadata.entities)
        ):
            refuse(interface, operation, "selected body is unmapped or attributed to a fieldless/default entity")
        category = "passthrough" if metadata.app_archetype == AppArchetype.PASSTHROUGH_ROUTER else _operation_category(ctx)
        if category in {"create", "update"} and not ctx.get("request_field_mappings"):
            refuse(interface, operation, "selected request body has no canonical field mappings")
        _transport(contract, category, ctx.get("operation_parameters", []), operations[0].response_fields)
    if metadata.app_archetype == AppArchetype.CRUD:
        fixed = []
        if controller_scope == "demo" or (
            controller_scope == "application" and profile.emit_test_console and should_emit_demo_ui(metadata)
        ):
            fixed.extend([
                ("GET", "/api/demo/entities", "DemoController.listEntities"),
                ("GET", "/api/demo/entities/{entityName}", "DemoController.getEntityRows"),
            ])
        if controller_scope != "demo" and profile.emit_spring_batch and has_batch_jobs(metadata, profile):
            fixed.append(("POST", "/batch/run/{jobName}", "BatchTriggerController.runJob"))
        for method, path, owner in surfaces:
            for fixed_method, fixed_path, handler in fixed:
                if method == fixed_method and _fixed_route_overlap(path, fixed_path):
                    refuse("generated REST surface", owner,
                           f"route {method} {path} collides with {handler} ({fixed_method} {fixed_path}), including fallback endpoints")
    seen = {}
    for method, path, owner in surfaces:
        key = (method, re.sub(r"\{[^}]+\}", "{}", path))
        if key in seen:
            refuse("generated REST surface", owner, f"route {method} {path} collides with {seen[key]}, including fallback endpoints")
        seen[key] = owner


def _fixed_route_overlap(path: str, fixed_path: str) -> bool:
    """Intersect complete literal/variable segments on these fixed mappings only."""
    left, right = path.split("/"), fixed_path.split("/")
    return len(left) == len(right) and all(
        a == b or re.fullmatch(r"\{[^/{}]+\}", a) or re.fullmatch(r"\{[^/{}]+\}", b)
        for a, b in zip(left, right, strict=True)
    )
