"""Actually emitted fixed-controller surfaces, scope and early refusal."""
import re
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.batch_metadata import has_batch_jobs
from appbuilder.generation.change_plan import build_change_plan
from appbuilder.generation.engine import _should_emit_demo_ui
from appbuilder.generation.java_emitter import (
    _java_type,
    _operation_contexts_for_entity,
    _render_controller,
    emit_demo_controller,
    emit_java_sources,
)
from appbuilder.generation.utils import entity_id_field, to_snake_case
from appbuilder.generation.write_contract import validate_write_contracts
from appbuilder.mapping import MappingDirection
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.models import (
    CanonicalEntity,
    ContractMetadata,
    HttpMethod,
    PathParameter,
    ResponseShape,
)
from appbuilder.target_profiles.catalog import TARGET_PROFILES
from tests.unit.test_read_contract import mapped_metadata
from tests.unit.test_write_contract import snapshot

SHIPPED_PROFILES = (
    "springboot-legacy-compatible",
    "springboot-enterprise-postgres-java17",
    "springboot-standard-enterprise",
)


def batch_metadata(*, jobs=True, route="/widgets", m5a=False):
    metadata = build_metadata_project(Path("tests/fixtures/boot41-batch/ordinary-app-definition.yaml"))
    if m5a:
        opted_in = build_metadata_project(Path("tests/fixtures/manifest-v2-cut/v2-run-semantics-app-definition.yaml"))
        next(c for c in metadata.contracts if c.type == "staging-table").run_semantics = next(
            c.run_semantics for c in opted_in.contracts if c.run_semantics is not None)
    if not jobs:
        metadata.contracts = [c for c in metadata.contracts if c.type != "staging-table"]
        metadata.mappings = [m for m in metadata.mappings if m.direction != MappingDirection.CANONICAL_TO_HANDOFF]
    for operation in metadata.operations:
        operation.path = route
    for contract in metadata.selected_rest_contracts:
        contract["path"] = route
    return metadata


def demo_metadata(kind):
    if kind == "fallback":
        return batch_metadata(jobs=False, route="/api/demo/entities")
    metadata = mapped_metadata()
    metadata.entities[0].name = "Entities"
    for operation in metadata.operations:
        operation.request_entity = operation.response_entity = "Entities"
    for mapping in metadata.mappings:
        mapping.target_path = mapping.target_path.replace("Account.", "Entities.")
    if kind == "list":
        metadata.operations = [metadata.operations[1]]
        metadata.operations[0].path = "/api/demo/entities"
    else:
        metadata.operations = [metadata.operations[0]]
        metadata.operations[0].path = "/api/demo/entities/{id}"
        metadata.operations[0].path_parameters = [PathParameter(name="id")]
    names = {op.name for op in metadata.operations}
    metadata.mappings = [m for m in metadata.mappings if m.operation_name in names]
    return metadata


def rendered_routes(metadata, profile):
    routes = []
    for entity in metadata.entities:
        if not entity.fields:
            continue
        source = _render_controller(
            entity=entity, root_package="validation",
            op_contexts=_operation_contexts_for_entity(metadata, entity),
            entity_path_base=f"/{to_snake_case(entity.name)}s",
            id_java_type=_java_type(entity_id_field(entity)), target_profile=profile,
            source_manifest="validation", generation_run_id="validation",
        )
        root = re.search(r'@RequestMapping\("([^"\n]*)"\)', source).group(1)
        routes.extend((method.upper(), root + suffix) for method, suffix in re.findall(
            r'@(Post|Put|Delete|Get)Mapping(?:\("([^"\n]*)"\))?', source))
    return routes


@pytest.mark.parametrize("profile_name", SHIPPED_PROFILES)
@pytest.mark.parametrize("kind", ["list", "item", "fallback"])
def test_demo_collision_uses_emitted_profile_and_reachable_routes(profile_name, kind):
    metadata = demo_metadata(kind)
    metadata.target_profile = profile_name
    profile = TARGET_PROFILES[profile_name]
    expected = "/api/demo/entities" + ("" if kind == "list" else "/{}")
    assert any(method == "GET" and re.sub(r"\{[^}]+\}", "{}", path) == expected
               for method, path in rendered_routes(metadata, profile))
    if profile.emit_test_console:
        with pytest.raises(ValueError, match=r"GET /api/demo/entities.*collides with DemoController"):
            validate_write_contracts(metadata)
    else:
        validate_write_contracts(metadata)


@pytest.mark.parametrize("profile_name", SHIPPED_PROFILES)
@pytest.mark.parametrize("m5a", [False, True])
def test_batch_literal_shadow_is_reachable_and_scoped_to_actual_jobs(profile_name, m5a):
    metadata = batch_metadata(route="/batch/run/export", m5a=m5a)
    metadata.target_profile = profile_name
    profile = TARGET_PROFILES[profile_name]
    assert ("POST", "/batch/run/export") in rendered_routes(metadata, profile)
    assert has_batch_jobs(metadata, profile)
    with pytest.raises(ValueError, match=r"POST /batch/run/export.*BatchTriggerController.runJob"):
        validate_write_contracts(metadata)
    validate_write_contracts(batch_metadata(jobs=False, route="/batch/run/export"), target_profile=profile)


def invoke(entry, metadata, output, profile=None):
    if entry == "generate":
        return generate_application(metadata, output)
    if entry == "plan":
        return build_change_plan(metadata=metadata, package_dir=output)
    if entry == "apply":
        return apply_change_plan(metadata=metadata, package_dir=output, approved_plan_hash="unused")
    emitter = emit_java_sources if entry == "java" else emit_demo_controller
    return emitter(metadata=metadata, target_profile=profile or TARGET_PROFILES[metadata.target_profile],
                   output_dir=output, source_manifest="validation", generation_run_id="validation")


@pytest.mark.parametrize("kind,entry", [
    (kind, entry) for kind in ("list", "item", "fallback", "batch")
    for entry in ("generate", "plan", "apply", "java", "demo")
    if not (entry == "java" and kind != "batch" or entry == "demo" and kind == "batch")
])
def test_fixed_collision_refuses_without_touching_existing_or_absent_output(tmp_path, entry, kind):
    metadata = batch_metadata(route="/batch/run/export") if kind == "batch" else demo_metadata(kind)
    output = tmp_path / "app"
    generate_application(batch_metadata(jobs=False), output, generation_run_id="before")
    sentinel = output / "developer-owned.txt"
    sentinel.write_text("preserve developer content")
    sentinel.chmod(0o444)
    before = snapshot(output)
    directories = {str(p): (p.stat().st_mode, p.stat().st_mtime_ns)
                   for p in [output, *output.rglob("*")] if p.is_dir()}
    try:
        for destination in (output, tmp_path / "absent" / "app"):
            with pytest.raises(ValueError, match="route.*collides with.*Controller"):
                invoke(entry, metadata, destination)
        assert snapshot(output) == before
        assert {str(p): (p.stat().st_mode, p.stat().st_mtime_ns)
                for p in [output, *output.rglob("*")] if p.is_dir()} == directories
        assert not (tmp_path / "absent").exists()
    finally:
        sentinel.chmod(0o644)


def test_direct_emitters_check_only_their_fixed_controller_scope_and_supplied_profile(tmp_path):
    metadata = demo_metadata("fallback")
    invoke("java", metadata, tmp_path / "java")  # No demo emitted here.
    assert not list((tmp_path / "java").rglob("DemoController.java"))
    # Explicit demo emission registers mappings even if this profile disables the console.
    profile = TARGET_PROFILES["springboot-enterprise-postgres-java17"]
    with pytest.raises(ValueError, match="DemoController"):
        invoke("demo", metadata, tmp_path / "absent-demo" / "app", profile)
    assert not (tmp_path / "absent-demo").exists()
    metadata = batch_metadata(route="/batch/run/export")
    invoke("demo", metadata, tmp_path / "demo-only")  # Does not emit batch.
    disabled = profile.model_copy(update={"emit_spring_batch": False})
    invoke("java", metadata, tmp_path / "no-batch", disabled)
    assert not list((tmp_path / "no-batch").rglob("BatchTriggerController.java"))
    metadata.target_profile = "springboot-standard-enterprise"
    with pytest.raises(ValueError, match="BatchTriggerController"):
        invoke("java", metadata, tmp_path / "absent-java" / "app", TARGET_PROFILES["springboot-legacy-compatible"])
    assert not (tmp_path / "absent-java").exists()


@pytest.mark.parametrize("jobs", [False, True])
def test_noncolliding_methods_and_paths_generate_with_real_controllers(tmp_path, jobs):
    metadata = batch_metadata(jobs=jobs, route="/api/demo/entities/write/records")
    output = tmp_path / "app"
    generate_application(metadata, output, generation_run_id="controls")
    assert bool(list(output.rglob("BatchTriggerController.java"))) == jobs
    demo = next(output.rglob("DemoController.java")).read_text()
    assert '${appbuilder.demo.enabled:false}' in demo  # Registered even while disabled.
    assert "return ResponseEntity.status(403)" in demo
    metadata = batch_metadata(jobs=jobs, route="/batch/run/export")
    metadata.selected_rest_contracts = []
    operation = metadata.operations[0]
    operation.http_method = HttpMethod.GET
    operation.response_shape = ResponseShape.LIST
    operation.has_request_body = False
    operation.name = "listWidgets"
    metadata.mappings = [m for m in metadata.mappings if ".request." not in m.source_path]
    for mapping in metadata.mappings:
        if mapping.operation_name == "createWidget":
            mapping.operation_name = "listWidgets"
            mapping.source_path = mapping.source_path.replace("createWidget", "listWidgets")
    validate_write_contracts(metadata)  # GET is distinct from actual batch POST.


@pytest.mark.parametrize("contract_type,direction,expected", [
    ("file-csv", MappingDirection.UPSTREAM_TO_CANONICAL, True),
    ("file-fixed-width", MappingDirection.CANONICAL_TO_DOWNSTREAM, True),
    ("xml-xsd", MappingDirection.CANONICAL_TO_DOWNSTREAM, True),
    ("staging-table", MappingDirection.CANONICAL_TO_HANDOFF, False),
])
def test_demo_applicability_matches_file_xml_and_handoff_conditions(contract_type, direction, expected):
    metadata = batch_metadata()
    metadata.operations = []
    metadata.selected_rest_contracts = []
    metadata.contracts = [ContractMetadata(name="edge", type=contract_type, source="")]
    metadata.mappings = [metadata.mappings[0].model_copy(update={"contract_name": "edge", "direction": direction})]
    assert _should_emit_demo_ui(metadata) == expected


def test_unassociated_or_fieldless_handoff_is_not_a_batch_job():
    metadata = batch_metadata(route="/batch/run/export")
    for mapping in metadata.mappings:
        if mapping.direction == MappingDirection.CANONICAL_TO_HANDOFF:
            mapping.source_path = "Unused." + mapping.source_path.split(".", 1)[1]
    metadata.entities.append(CanonicalEntity(name="Unused"))
    profile = TARGET_PROFILES[metadata.target_profile]
    assert not has_batch_jobs(metadata, profile)
    validate_write_contracts(metadata)


def test_downstream_file_alone_emits_batch_and_participates_in_refusal():
    metadata = build_metadata_project(Path(
        "tests/fixtures/generated-app-quality/crud-minor-units-date/app-definition.yaml"))
    metadata.contracts = [c for c in metadata.contracts if c.type != "staging-table"]
    metadata.mappings = [m for m in metadata.mappings if m.direction != MappingDirection.CANONICAL_TO_HANDOFF]
    for operation in metadata.operations:
        operation.path = "/batch/run/export"
    for contract in metadata.selected_rest_contracts:
        contract["path"] = "/batch/run/export"
    assert has_batch_jobs(metadata, TARGET_PROFILES[metadata.target_profile])
    assert ("POST", "/batch/run/export") in rendered_routes(metadata, TARGET_PROFILES[metadata.target_profile])
    with pytest.raises(ValueError, match="BatchTriggerController.runJob"):
        validate_write_contracts(metadata)


@pytest.mark.parametrize("profile_name", [name for name in SHIPPED_PROFILES
                                         if not TARGET_PROFILES[name].emit_test_console])
@pytest.mark.parametrize("kind", ["list", "item", "fallback"])
def test_absent_demo_does_not_reserve_its_routes_in_generated_output(tmp_path, profile_name, kind):
    metadata = demo_metadata(kind)
    metadata.target_profile = profile_name
    generate_application(metadata, tmp_path / "app", generation_run_id="no-demo")
    assert not list((tmp_path / "app").rglob("DemoController.java"))
    assert list((tmp_path / "app").rglob("*Controller.java"))


def test_runtime_helper_cases_use_real_applicability_without_profile_overrides():
    from scripts.smoke.endpoint_boundary_proof import _metadata

    for demo in (False, True):
        for batch in (False, True):
            metadata = _metadata(demo=demo, batch=batch)
            profile = TARGET_PROFILES[metadata.target_profile]
            assert profile.java_baseline == "17" and profile.runtime_database_dependency == "h2"
            assert _should_emit_demo_ui(metadata) == demo
            assert has_batch_jobs(metadata, profile) == batch
            validate_write_contracts(metadata)


@pytest.mark.parametrize("archetype", ["crud", "passthrough"])
@pytest.mark.parametrize("profile_name", SHIPPED_PROFILES)
def test_generated_guidance_states_exposure_and_int32_limitations(tmp_path, archetype, profile_name):
    metadata = (batch_metadata(jobs=False) if archetype == "crud" else build_metadata_project(
        Path("examples/input-projects/country-router/app-definition.yaml")))
    metadata.target_profile = profile_name
    output = tmp_path / "app"
    generate_application(metadata, output, generation_run_id="guidance")
    for filename in ("README.md", "agent-context.md"):
        text = (output / filename).read_text()
        for phrase in ("Selected OpenAPI operations are not the whole emitted API", "generic CRUD",
                       "emitted HTTP method/path surface", "only explicitly approved operations",
                       "keep unapproved CRUD/demo/batch", "Prohibit direct application-port access",
                       "Authentication is not endpoint exposure approval", "neither supplies business",
                       "deferred post-v5", "`int32`", "Java `Long`", "do not enforce 32-bit bounds",
                       "validate them before business effects"):
            assert phrase in text
