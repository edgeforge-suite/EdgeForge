"""Portable pre-promotion controls from the actual merged source, without Git history."""

import hashlib
import json
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.change_plan import build_change_plan
from appbuilder.generation.regeneration import _load_baseline
from appbuilder.generation.schema_baseline import load_schema_baseline
from appbuilder.metadata import build_metadata_project
from appbuilder.target_profiles.catalog import TARGET_PROFILES
from scripts.assess_generated_maven import inventory_digest, source_inventory
from scripts.smoke.boot41_batch_cases import case_metadata

RECEIPT = json.loads(Path("tests/fixtures/boot41-promotion/prepromotion.json").read_text())
PROFILES = tuple(TARGET_PROFILES)


def metadata_for(shape, profile):
    value = (build_metadata_project("examples/input-projects/generated-app-ci-smoke/app-definition.yaml")
             if shape == "jobless" else case_metadata(shape, profile))
    value.target_profile = profile
    return value


def retained_package(path, case):
    for name, text in case["files"].items():
        destination = path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)
    return path


@pytest.mark.parametrize("case", RECEIPT["cases"], ids=lambda c: c["shape"] + "/" + c["profile"])
@pytest.mark.parametrize("entrypoint", ("generate", "plan", "apply"))
@pytest.mark.parametrize("state", ("retained", "incomplete", "ambiguous"))
def test_old_packages_refuse_before_writes(tmp_path, case, entrypoint, state):
    app = retained_package(tmp_path / "app", case)
    if state == "incomplete":
        (app / "db/schema-baseline.json").unlink()
    if state == "ambiguous":
        (app / "pom.xml").unlink()
    before = source_inventory(app)
    metadata = metadata_for(case["shape"], case["profile"])
    with pytest.raises(ValueError, match="Unsupported existing package transition"):
        if entrypoint == "generate":
            generate_application(metadata, app)
        elif entrypoint == "plan":
            build_change_plan(metadata=metadata, package_dir=app)
        else:
            apply_change_plan(metadata=metadata, package_dir=app, approved_plan_hash="old-approved-hash")
    assert source_inventory(app) == before


def test_receipts_match_captured_files_and_exact_base():
    assert RECEIPT["generator_sha"] == "76f7ab9ef1220e2bf5c94a78ce4e107cc965a5c2"
    assert len(RECEIPT["cases"]) == 9
    for case in RECEIPT["cases"]:
        source_files = {item["path"]: item["sha256"] for item in case["source_files"]}
        assert inventory_digest(source_files) == case["source_sha256"]
        for name, text in case["files"].items():
            assert hashlib.sha256(text.encode()).hexdigest() == source_files[name]
        assert "<version>3.3.5</version>" in case["files"]["pom.xml"]


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("entrypoint", ("generate", "plan", "apply"))
@pytest.mark.parametrize("provenance", ("retained", "absent"))
def test_unvalidated_patch_refuses_before_writes(tmp_path, profile, entrypoint, provenance):
    app = tmp_path / "app"
    metadata = metadata_for("jobless", profile)
    generate_application(metadata, app, generation_run_id="fixed")
    pom = app / "pom.xml"
    pom.write_text(pom.read_text().replace("<version>4.1.1</version>", "<version>4.1.2</version>"))
    record = app / "db/generation-provenance.json"
    if provenance == "retained":
        record.write_text(record.read_text().replace("4.1.1", "4.1.2"))
    else:
        record.unlink()
    before = source_inventory(app)
    with pytest.raises(ValueError, match="unvalidated patch baseline"):
        if entrypoint == "generate":
            generate_application(metadata, app)
        elif entrypoint == "plan":
            build_change_plan(metadata=metadata, package_dir=app)
        else:
            apply_change_plan(metadata=metadata, package_dir=app, approved_plan_hash="old-approved-hash")
    assert source_inventory(app) == before


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("shape", ("jobless", "ordinary", "file", "m5a", "mixed"))
def test_fresh_same_policy_preserves_migrations(tmp_path, shape, profile):
    app = tmp_path / "app"
    metadata = metadata_for(shape, profile)
    generate_application(metadata, app, generation_run_id="fixed")
    before = source_inventory(app)
    generate_application(metadata, app, generation_run_id="fixed")
    assert source_inventory(app) == before
    assert "<version>4.1.1</version>" in (app / "pom.xml").read_text()
    if shape == "jobless":
        assert "starter-batch" not in (app / "pom.xml").read_text()
    else:
        assert "spring-boot-starter-batch-jdbc" in (app / "pom.xml").read_text()
    migrations = {p: h for p, h in before.items() if p.endswith(".sql")}
    baseline = json.loads((app / "db/schema-baseline.json").read_text())
    metadata.target_profile = profile
    plan = build_change_plan(metadata=metadata, package_dir=app)
    assert plan["db_migration_deltas"] == []
    apply_change_plan(metadata=metadata, package_dir=app, approved_plan_hash=plan["plan_hash"], generation_run_id="fixed")
    after = source_inventory(app)
    assert {p: h for p, h in after.items() if p.endswith(".sql")} == migrations
    assert json.loads((app / "db/schema-baseline.json").read_text()).get("internal_schemas") == baseline.get("internal_schemas")


@pytest.mark.parametrize("evidence", ("pom", "provenance", "batch-version", "batch-fingerprint", "migration"))
def test_conflicting_retained_evidence_is_not_repaired(tmp_path, evidence):
    app = tmp_path / "app"
    metadata = metadata_for("m5a", PROFILES[0])
    generate_application(metadata, app)
    if evidence == "pom":
        path = app / "pom.xml"
        path.write_text(path.read_text().replace("4.1.1", "3.3.5"))
    elif evidence == "provenance":
        (app / "db/generation-provenance.json").write_text("{}")
    elif evidence in {"batch-version", "batch-fingerprint"}:
        path = app / "db/schema-baseline.json"
        value = json.loads(path.read_text())
        entry = next(e for e in value["internal_schemas"] if e["id"] == "pkg-batch-metadata")
        entry["spring_batch_metadata_schema_version" if evidence == "batch-version" else "content_sha256"] = "5.1.2" if evidence == "batch-version" else "0" * 64
        path.write_text(json.dumps(value))
    else:
        next(app.rglob("*create_pkg_batch_metadata.sql")).write_text("-- missing schema")
    before = source_inventory(app)
    with pytest.raises(ValueError):
        generate_application(metadata, app)
    assert source_inventory(app) == before


XML_AMBIGUITIES = (
    "duplicate-parent", "duplicate-identical-parent", "duplicate-version",
    "duplicate-group", "duplicate-artifact", "wrong-root", "missing-parent",
    "missing-version", "foreign-parent", "nested-version", "duplicate-project-version",
    "duplicate-model-version",
    "missing-project-group", "missing-project-artifact", "missing-project-version",
    "missing-model-version", "missing-parent-group", "missing-parent-artifact",
)


def ambiguous_pom(text, state):
    start, stop = text.index("<parent>"), text.index("</parent>") + len("</parent>")
    old_parent = text[start:stop]
    parent = old_parent.replace("3.3.5", "4.1.1")
    if state == "duplicate-parent":
        parent += "\n" + old_parent
    elif state == "duplicate-identical-parent":
        parent += "\n" + parent
    elif state == "duplicate-version":
        parent = parent.replace("<version>4.1.1</version>", "<version>4.1.1</version><version>3.3.5</version>")
    elif state == "duplicate-group":
        parent = parent.replace("</groupId>", "</groupId><groupId>ambiguous.synthetic</groupId>")
    elif state == "duplicate-artifact":
        parent = parent.replace("</artifactId>", "</artifactId><artifactId>ambiguous-parent</artifactId>")
    elif state == "missing-parent":
        parent = ""
    elif state == "missing-version":
        parent = parent.replace("<version>4.1.1</version>", "")
    elif state == "foreign-parent":
        parent = parent.replace("<parent>", '<parent xmlns="">')
    elif state == "nested-version":
        parent = parent.replace("4.1.1</version>", "4.1.1<ambiguous>3.3.5</ambiguous></version>")
    elif state in {"missing-parent-group", "missing-parent-artifact"}:
        name = "groupId" if state == "missing-parent-group" else "artifactId"
        first, last = parent.index(f"<{name}>"), parent.index(f"</{name}>") + len(f"</{name}>")
        parent = parent[:first] + parent[last:]
    result = text[:start] + parent + text[stop:]
    if state == "wrong-root":
        result = result.replace("<project ", "<not-a-project ").replace("</project>", "</not-a-project>")
    elif state == "duplicate-project-version":
        result = result.replace("<version>0.0.1-SNAPSHOT</version>", "<version>0.0.1-SNAPSHOT</version><version>ambiguous</version>")
    elif state == "duplicate-model-version":
        result = result.replace("<modelVersion>4.0.0</modelVersion>", "<modelVersion>4.0.0</modelVersion><modelVersion>3.0.0</modelVersion>")
    elif state in {"missing-project-group", "missing-project-artifact", "missing-project-version", "missing-model-version"}:
        name = {"missing-project-group": "groupId", "missing-project-artifact": "artifactId", "missing-project-version": "version", "missing-model-version": "modelVersion"}[state]
        search_from = result.index("</parent>") if name != "modelVersion" else 0
        first = result.index(f"<{name}>", search_from)
        last = result.index(f"</{name}>", first) + len(f"</{name}>")
        result = result[:first] + result[last:]
    return result


def invoke_existing(metadata, app, entrypoint, approved_hash):
    if entrypoint == "generate":
        return generate_application(metadata, app)
    if entrypoint == "plan":
        return build_change_plan(metadata=metadata, package_dir=app)
    return apply_change_plan(metadata=metadata, package_dir=app, approved_plan_hash=approved_hash)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("entrypoint", ("generate", "plan", "apply"))
@pytest.mark.parametrize("state", XML_AMBIGUITIES)
def test_ambiguous_captured_pom_refuses_before_writes(tmp_path, profile, entrypoint, state):
    case = next(c for c in RECEIPT["cases"] if c["shape"] == "jobless" and c["profile"] == profile)
    app = retained_package(tmp_path / "app", case)
    pom = app / "pom.xml"
    pom.write_text(ambiguous_pom(pom.read_text(), state))
    before = source_inventory(app)
    with pytest.raises(ValueError, match="Unsupported existing package transition"):
        invoke_existing(metadata_for("jobless", profile), app, entrypoint, "old-approved-hash")
    assert source_inventory(app) == before


JSON_AMBIGUITIES = (
    "provenance-version", "provenance-framework", "provenance-escaped-key",
    "schema-internal-schemas", "schema-batch-version", "schema-fingerprint",
    "schema-id", "schema-profile",
)


def duplicate_json_evidence(app, state):
    path = app / ("db/generation-provenance.json" if state.startswith("provenance") else "db/schema-baseline.json")
    text = path.read_text()
    value = json.loads(text)
    if state == "provenance-version":
        key, old, current = "spring_boot_version", "3.3.5", value["spring_boot_version"]
    elif state == "provenance-framework":
        key, old, current = "framework", "ambiguous", value["framework"]
    elif state == "provenance-escaped-key":
        key, old, current = "spring_boot_version", "3.3.5", value["spring_boot_version"]
    elif state == "schema-internal-schemas":
        path.write_text(text.replace('"internal_schemas":', '"internal_schemas": [], "internal_schemas":', 1))
        return path
    elif state == "schema-profile":
        key, old, current = "target_profile", "ambiguous", value["target_profile"]
    else:
        entry = next(e for e in value["internal_schemas"] if e["id"] == "pkg-batch-metadata")
        key = {"schema-batch-version": "spring_batch_metadata_schema_version", "schema-fingerprint": "content_sha256", "schema-id": "id"}[state]
        old, current = "ambiguous", entry[key]
    original = f"{json.dumps(key)}: {json.dumps(current)}"
    duplicate_key = '"spring_boot_vers\\u0069on"' if state == "provenance-escaped-key" else json.dumps(key)
    assert original in text
    path.write_text(text.replace(original, f"{duplicate_key}: {json.dumps(old)}, {original}", 1))
    return path


@pytest.mark.parametrize("profile", tuple(TARGET_PROFILES))
@pytest.mark.parametrize("entrypoint", ("generate", "plan", "apply"))
@pytest.mark.parametrize("state", JSON_AMBIGUITIES)
def test_duplicate_durable_keys_refuse_after_real_approval(tmp_path, profile, entrypoint, state):
    app = tmp_path / "app"
    metadata = metadata_for("m5a", profile)
    generate_application(metadata, app, generation_run_id="fixed")
    approved = build_change_plan(metadata=metadata, package_dir=app)
    assert approved["mode"] == "regenerate" and approved["classification"] == "none"
    duplicate_json_evidence(app, state)
    before = source_inventory(app)
    if state.startswith("schema"):
        for read in (lambda: load_schema_baseline(app), lambda: _load_baseline(app / "db/schema-baseline.json")):
            with pytest.raises(ValueError):
                read()
    with pytest.raises(ValueError, match="Unsupported existing package transition"):
        invoke_existing(metadata, app, entrypoint, approved["plan_hash"])
    assert source_inventory(app) == before
