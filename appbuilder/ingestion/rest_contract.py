"""Retain selected transport contracts without fetching or interpreting business semantics."""
from __future__ import annotations

from copy import deepcopy

from .openapi_classifier import _merge_parameter_definitions, _resolve_local_reference

METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "options", "trace"})


def selected_rest_contracts(spec: dict, interface: str, selected: list[str] | None) -> list[dict]:
    found: dict[str, list[dict]] = {}
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        paths = {}
    for path, raw_item in paths.items():
        try:
            item = _resolve_local_reference(raw_item, spec, kind="path item")
        except ValueError:
            continue
        for method, operation in item.items():
            if method not in METHODS or not isinstance(operation, dict):
                continue
            name = operation.get("operationId")
            if not isinstance(name, str) or not name:
                # Same fallback used by current ingestion, resolved below if selected.
                from .openapi_classifier import _resource_entity_name_from_path
                name = f"{method}{_resource_entity_name_from_path(path) or 'Resource'}"
            if selected is not None and name not in selected:
                continue
            errors: list[str] = []
            parameters = _merge_parameter_definitions(item, operation, spec=spec, errors=errors)
            body = None
            if "requestBody" in operation:
                try:
                    body = _resolve_local_reference(operation["requestBody"], spec, kind="request body")
                except ValueError as exc:
                    errors.append(str(exc))
            responses = {}
            raw_responses = operation.get("responses", {})
            if not isinstance(raw_responses, dict):
                errors.append("responses must be an object")
                raw_responses = {}
            for code, raw in raw_responses.items():
                code = str(code)
                if not code.startswith("2"):
                    continue
                try:
                    response = _resolve_local_reference(raw, spec, kind="response")
                    responses[code] = _resolve_content(response, spec)
                except ValueError as exc:
                    errors.append(f"success response {code}: {exc}")
            try:
                body = _resolve_content(body, spec) if body is not None else None
            except ValueError as exc:
                errors.append(f"request body: {exc}")
            found.setdefault(name, []).append({
                "interface": interface, "operation": name, "method": method.upper(),
                "path": path, "parameters": deepcopy(parameters), "body": body,
                "responses": responses, "errors": errors,
            })
    results = []
    for name in selected if selected is not None else found:
        matches = found.get(name, [])
        if len(matches) == 1:
            results.extend(matches)
        else:
            results.append({"interface": interface, "operation": name, "method": None,
                            "path": None, "parameters": [], "body": None, "responses": {},
                            "errors": ["selected operation is unresolved or ambiguous in source contract"]})
    return results


def _resolve_content(value: dict, spec: dict) -> dict:
    value = deepcopy(value)
    content = value.get("content", {})
    if not isinstance(content, dict):
        raise ValueError("content must be an object")
    for media in content.values():
        if not isinstance(media, dict) or "schema" not in media:
            raise ValueError("content requires a schema")
        media["schema"] = _resolve_local_reference(media["schema"], spec, kind="schema")
    return value
