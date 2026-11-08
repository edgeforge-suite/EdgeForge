"""Reviewed pins and plugin realms: no Docker, downloads or advisory queries."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from appbuilder.generation import generate_application
from appbuilder.generation.build_emitter import _render_passthrough_pom_xml, _render_pom_xml
from appbuilder.generation.container_policy import (
    BASE_REFERENCE_POLICIES,
    BASE_REFERENCE_POLICY_ID,
    CONTAINER_BASES,
    HISTORICAL_BASE_REFERENCE_POLICY_ID,
    base_references,
    declared_base_references,
)
from appbuilder.generation.kafka_build_emitter import _render_pom_xml as _render_kafka_pom_xml
from appbuilder.generation.plugin_policy import PLUGIN_REALM_DEPENDENCIES, build_plugins
from appbuilder.metadata.translation import build_metadata_project
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile
from scripts import assess_generated_images as images
from scripts import collect_generated_images as collector
from scripts import publish_generated_image_evidence as publisher
from scripts.assess_generated_maven import source_inventory
from scripts.collect_generated_maven_baseline import FIXTURES, PROFILES, prepare_case_input

_EXPECTED_PLUGIN_REALMS = {
    "maven-clean-plugin": (("org.codehaus.plexus", "plexus-utils", "4.0.3"),),
    "maven-compiler-plugin": (
        ("commons-io", "commons-io", "2.14.0"),
        ("org.codehaus.plexus", "plexus-utils", "4.0.3"),
    ),
    "maven-resources-plugin": (("org.codehaus.plexus", "plexus-utils", "3.6.1"),),
    "spring-boot-maven-plugin": (
        ("org.apache.commons", "commons-lang3", "3.18.0"),
        ("org.codehaus.plexus", "plexus-utils", "3.6.1"),
        ("tools.jackson.core", "jackson-core", "3.1.7"),
        ("tools.jackson.core", "jackson-databind", "3.1.7"),
    ),
}
_CLEAN_PLUGIN_BLOCK = """            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <dependencies>
                    <dependency>
                        <groupId>org.codehaus.plexus</groupId>
                        <artifactId>plexus-utils</artifactId>
                        <version>4.0.3</version>
                    </dependency>
                </dependencies>
            </plugin>
"""
_LEGACY_PLUGINS = [
    "            <plugin>",
    "                <groupId>org.springframework.boot</groupId>",
    "                <artifactId>spring-boot-maven-plugin</artifactId>",
    "            </plugin>",
]

# Captured before the policy edit from 417e224e18fa6069b48a77e89cbd574c73f21538,
# with actual copied fixture manifests and generation_run_id="policy-unit".
# These are original full-POM hashes, not hashes reconstructed from the candidate.
_BASE_POM_SHA256 = {
    "crud-h2-j17": "28805c8488a52dc28a3524e305945b80b635159757c00f7e669856b756edf2d7",
    "crud-pg-j17": "ac48860e5cf70e4c815da43197393469e3f0f9a666c756ce90666d704eae368a",
    "crud-pg-j21": "c88fdac7bffed634cb185770a4348c9e6acf6eed33dc59a19c575735050863d0",
    "crud-soap-h2-j17": "f83be11c137c98f0ce7f41bf6d15ea1dceefa044dc0319148f4dc85b8e788561",
    "crud-soap-pg-j17": "881b99b126e417797927b96663e677f241e66fc3af2004e1e8dc96edc9d72f68",
    "crud-soap-pg-j21": "ef80b9a1d8b5aa2cfe61f9c7df86e35e577acb6736ba83c5ad49a377195a3d30",
    "passthrough-h2-j17": "b62137ab886318d647717292a4a2e34106d0de9085758216f9b0ab1d8597a9dc",
    "passthrough-pg-j17": "fa9580c79a4267fa73d1b452edcdb043b8881cd954a254db8b4b524aafffb153",
    "passthrough-pg-j21": "b5a247c1395095cc0eef315389907b9e13665d09979070854af576c623df3599",
    "kafka-h2-j17": "af393564f8a650aae5a333f44d6a18b1a552bb788ee767e07a2416537d805e83",
    "kafka-pg-j17": "9ac9a1c98fe1331b56d4543ce19c851755597048c2113c2029e0da54e7c7127c",
    "kafka-pg-j21": "82038ac3809412dcc21578984788f6a940f0307f097a46146aff404739ff267a",
    "kafka-router-h2-j17": "51ccc94de4d966ad34cbc8fa877aeb4a62f62955c47ae0030b479eee696080f3",
    "kafka-router-pg-j17": "16f0a9fc4711feb1dd13ca802880ba0c27220bc742f265f136217554efba8f07",
    "kafka-router-pg-j21": "f30882fc0a2babafb2f1ba69a1d30d041554c3bb5c2ccc5dcb6c2b95151f9000",
    "ordinary-batch-h2-j17": "07d8ac9bc7b33b33441584796cd2e7122414c8bcec96031c5f3085b878558bb3",
    "ordinary-batch-pg-j17": "2fcc1d980086f0b64b842c3bbebdc39e020ffb668a9f56bec821635bd388a6ac",
    "ordinary-batch-pg-j21": "3a5e253ccd33d902d52342cfab3b8629fed5c8f7ef38f891e7a7b69d98c6c126",
    "file-batch-h2-j17": "6febc264afdf16b8defd083ec2e692fdff767a0913c1c730c3c2d52652dd4051",
    "file-batch-pg-j17": "471e2ef9b47e02b8f598471492273f81e54b5ed01d0926aaf0e9bd5d7d939a73",
    "file-batch-pg-j21": "94b98e6bee39a4c60d20bffe37673fe9d9933e151a4fe43a234a526170be8882",
    "m5a-h2-j17": "4e440f37daa06059b5f5e479b1e098d59f4643ce55fa6cbf6e65a74239cc2000",
    "m5a-pg-j17": "ba05673bbd4d5b1940d25d967482f8ffc8ff17a2a5029b0cc868e5a83f1661cc",
    "m5a-pg-j21": "14fd05bfcd25f95c73bfea9d3f530d598c452714c4d6c0bbab8236513e5385d9",
    "mixed-batch-h2-j17": "4e440f37daa06059b5f5e479b1e098d59f4643ce55fa6cbf6e65a74239cc2000",
    "mixed-batch-pg-j17": "ba05673bbd4d5b1940d25d967482f8ffc8ff17a2a5029b0cc868e5a83f1661cc",
    "mixed-batch-pg-j21": "14fd05bfcd25f95c73bfea9d3f530d598c452714c4d6c0bbab8236513e5385d9",
    "kafka-mixed-h2-j17": "0147761540bd7bac46e729630ee22565cbbb29c8f18ff2ffa3fbcc636db8f91a",
    "kafka-mixed-pg-j17": "d2ad135a3191ec0cdae20b17d784a51797333c745fe87d19938c4228da9b3aad",
    "kafka-mixed-pg-j21": "57845aa50605292cd6e71e8c69627413430b54cba5377d630c53e32713b08e8a",
}
_LEGACY_POM_SHA256 = {
    "crud": "12d88fed3a751cfb7d91c228b2cd2de404c9a8960ea4d91429f0338d5a6034a2",
    "crud-soap": "de76d7981f9cd1a9ecdd55cdd095049bab27455fc829cf0d80ce3631517f5e44",
    "passthrough": "a25063f0daf9665d691baeb0e3608a7732373ae4585560f638a7a9b45d958a2c",
    "kafka": "eb5a43b8624f5686e02b1b3a3388b37be2359f7be36abba8e603718f246873fb",
    "kafka-router": "e867a72b057ac885b32e9946a6afb473663cb6a6621f79e3b4a9a414ca0eefc6",
    "kafka-mixed": "a2879d643e0925de8a53665b2deb1d3b97e603e86402b0e8b5284ac907090b3c",
}


def _policy_metadata(root, shape, profile):
    manifest = prepare_case_input(root, shape, FIXTURES[shape])
    raw = yaml.safe_load(manifest.read_text())
    raw["target_profile"] = profile
    manifest.write_text(yaml.safe_dump(raw, sort_keys=False))
    return build_metadata_project(manifest), manifest


def test_plugin_policy_is_immutable_and_matches_independent_literal():
    assert dict(PLUGIN_REALM_DEPENDENCIES) == _EXPECTED_PLUGIN_REALMS
    with pytest.raises(TypeError):
        PLUGIN_REALM_DEPENDENCIES["maven-clean-plugin"] = ()


def test_frozen_base_covers_every_fixture_profile_pair():
    assert len(_BASE_POM_SHA256) == 30
    assert set(_BASE_POM_SHA256) == {
        f"{shape}-{suffix}" for shape in FIXTURES for suffix in PROFILES
    }


def test_disabled_plugin_policy_keeps_literal_boot3_output():
    assert build_plugins(False) == _LEGACY_PLUGINS


@pytest.mark.parametrize("shape", tuple(_LEGACY_POM_SHA256))
def test_disabled_boot3_renderers_keep_frozen_base_poms(tmp_path, monkeypatch, shape):
    metadata, manifest = _policy_metadata(tmp_path, shape, PROFILES["h2-j17"])
    # Direct renderer control only; do not re-enable Boot 3 public generation.
    legacy = TargetProfile(
        name="test-boot3-policy", language="java", framework="spring-boot",
        java_baseline="17", spring_boot_baseline="3.3.5", experimental_boot41=False,
        emit_flyway=True, emit_spring_batch=True, supports_xml=True,
    )
    monkeypatch.setitem(TARGET_PROFILES, legacy.name, legacy)
    common = {"source_manifest": str(manifest), "generation_run_id": "policy-unit"}
    if shape.startswith("kafka"):
        metadata = metadata.model_copy(update={"target_profile_name": legacy.name,
                                               "spring_boot_version": "3.3.5"})
        pom = _render_kafka_pom_xml(metadata, **common)
    else:
        renderer = _render_passthrough_pom_xml if shape == "passthrough" else _render_pom_xml
        pom = renderer(metadata=metadata, target_profile=legacy, **common)
    assert hashlib.sha256(pom.encode()).hexdigest() == _LEGACY_POM_SHA256[shape]
    root = ET.fromstring(pom)
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    assert root.findtext("m:parent/m:version", namespaces=ns) == "3.3.5"
    assert root.findtext("m:build/m:plugins/m:plugin/m:artifactId", namespaces=ns) == "spring-boot-maven-plugin"
    assert len(root.findall("m:build/m:plugins/m:plugin", ns)) == 1
    assert not root.findall("m:build/m:plugins/m:plugin/m:dependencies", ns)


@pytest.mark.parametrize("event", ("push", "pull_request"))
def test_compile_workflow_covers_requirements_lock_changes(event):
    workflow = Path(__file__).resolve().parents[2] / ".github/workflows/generated-app-compile.yml"
    document = yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)
    assert document["on"][event]["paths"].count("requirements-lock.txt") == 1
    steps = document["jobs"]["compile-representative-generated-app"]["steps"]
    install = next(step for step in steps if step.get("name") == "Install Engine dependencies")
    assert install["run"] == "python -m pip install -c requirements-lock.txt -r requirements.txt"


@pytest.mark.parametrize("java", ("17", "21"))
def test_reference_mapping_is_immutable_and_pins_indexes_not_children(java):
    for base, reference in zip(CONTAINER_BASES[java], base_references(java), strict=True):
        assert reference == base.tag + "@" + base.index_digest
        assert len({base.index_digest, base.amd64_manifest_digest, base.config_digest}) == 3
        assert all(images.identity(value) for value in
                   (base.index_digest, base.amd64_manifest_digest, base.config_digest))
    with pytest.raises(TypeError):
        CONTAINER_BASES[java] = ()
    with pytest.raises(TypeError):
        BASE_REFERENCE_POLICIES[BASE_REFERENCE_POLICY_ID][java] = ()


@pytest.mark.parametrize("java,policy", (("25", BASE_REFERENCE_POLICY_ID), ("17", "unreviewed")))
def test_unknown_reference_selections_fail(java, policy):
    with pytest.raises(ValueError):
        base_references(java, policy)


@pytest.mark.parametrize("shape", tuple(FIXTURES))
@pytest.mark.parametrize("suffix,profile", tuple(PROFILES.items()))
def test_all_pom_lanes_scope_overrides_to_proven_realms_and_emit_same_pins(tmp_path, shape, suffix, profile):
    metadata, manifest = _policy_metadata(tmp_path, shape, profile)
    first, second = tmp_path / "first", tmp_path / "second"
    for output in (first, second):
        generate_application(metadata, output, source_manifest=str(manifest), generation_run_id="policy-unit")
    inventory = source_inventory(first)
    assert inventory == source_inventory(second)
    generate_application(metadata, first, source_manifest=str(manifest), generation_run_id="policy-unit")
    assert source_inventory(first) == inventory
    pom = (first / "pom.xml").read_text()
    assert pom.count(_CLEAN_PLUGIN_BLOCK) == 1
    without_clean = pom.replace(_CLEAN_PLUGIN_BLOCK, "", 1)
    assert hashlib.sha256(without_clean.encode()).hexdigest() == _BASE_POM_SHA256[f"{shape}-{suffix}"]
    root = ET.fromstring(pom)
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    assert root.findtext("m:parent/m:version", namespaces=ns) == "4.1.1"
    plugins = root.findall("m:build/m:plugins/m:plugin", ns)
    actual = {p.findtext("m:artifactId", namespaces=ns): tuple(
        tuple(d.findtext("m:" + key, namespaces=ns) for key in ("groupId", "artifactId", "version"))
        for d in p.findall("m:dependencies/m:dependency", ns)) for p in plugins}
    assert len(plugins) == len(_EXPECTED_PLUGIN_REALMS)
    assert actual == _EXPECTED_PLUGIN_REALMS
    for plugin in plugins:
        artifact = plugin.findtext("m:artifactId", namespaces=ns)
        group = "org.springframework.boot" if artifact == "spring-boot-maven-plugin" else "org.apache.maven.plugins"
        assert plugin.findtext("m:groupId", namespaces=ns) == group
        assert plugin.find("m:version", ns) is None
    dependencies = root.findall("m:dependencies/m:dependency", ns)
    dependencies += root.findall("m:dependencyManagement/m:dependencies/m:dependency", ns)
    application = {d.findtext("m:artifactId", namespaces=ns) for d in dependencies}
    assert not application & {"plexus-utils", "commons-io", "commons-lang3", "jackson-core", "jackson-databind"}
    java = "21" if suffix.endswith("j21") else "17"
    recipe = (first / "Dockerfile").read_text()
    build, runtime = base_references(java)
    assert [line for line in recipe.splitlines() if line.startswith("FROM ")] == [
        f"FROM {build} AS build", f"FROM {runtime}"]
    assert "RUN mvn -q -DskipTests clean package" in recipe
    assert "USER edgeforge" in recipe and 'ENTRYPOINT ["java", "-jar", "/app/app.jar"]' in recipe


def declaration():
    return {"declared_before_campaign": True, "cases": [
        {"case": f"{shape}-{suffix}", "shape": shape, "fixture": fixture, "profile": profile,
         "platform": "linux/amd64", "assess": list(images.STAGES), "equivalence_claim": False,
         "build_base": base_references("21" if suffix.endswith("j21") else "17")[0],
         "runtime_base": base_references("21" if suffix.endswith("j21") else "17")[1],
         "historical_resolved_graph_representative": f"{shape}-{suffix}"}
        for shape, fixture in FIXTURES.items() for suffix, profile in PROFILES.items()]}


def test_new_and_historical_coverage_remain_thirty_by_two():
    current = declaration()
    assert len(images.make_plan(current)["cases"]) == 30
    status = collector.base_policy_status(current["cases"])
    assert status["base_reference_policy"] == BASE_REFERENCE_POLICY_ID
    assert "INDEX pins" in status["floating_policy"] and "live Maven" in status["floating_policy"]
    for row in current["cases"]:
        del row["build_base"], row["runtime_base"]
    assert len(images.make_plan(current)["cases"]) == 30
    assert declared_base_references(current["cases"][0]) == base_references("17", HISTORICAL_BASE_REFERENCE_POLICY_ID)
    assert collector.base_policy_status(current["cases"]) == {
        "base_reference_policy": HISTORICAL_BASE_REFERENCE_POLICY_ID,
        "floating_policy": "unchanged; parent must decide pin versus float, no risk acceptance"}


@pytest.mark.parametrize("explicit_policy", (False, True))
def test_normalized_plan_preserves_validated_base_contract(explicit_policy):
    current = declaration()
    if explicit_policy:
        for row in current["cases"]:
            row["base_reference_policy"] = BASE_REFERENCE_POLICY_ID
    plan = images.make_plan(current)
    for source, normalized in zip(current["cases"], plan["cases"], strict=True):
        assert declared_base_references(normalized) == declared_base_references(source)
        for key in ("build_base", "runtime_base", "base_reference_policy"):
            assert (key in normalized, normalized.get(key)) == (key in source, source.get(key))


def test_implicit_historical_plan_shape_and_policy_are_unchanged():
    current = declaration()
    for row in current["cases"]:
        del row["build_base"], row["runtime_base"]
    plan = images.make_plan(current)
    for row in plan["cases"]:
        assert set(row) == {"case", "profile", "fixture", "historical_representative",
                            "artifacts", "equivalence_claim"}
        java = "21" if row["case"].endswith("j21") else "17"
        assert declared_base_references(row) == base_references(java, HISTORICAL_BASE_REFERENCE_POLICY_ID)


def test_explicit_historical_plan_retains_historical_references():
    current = declaration()
    for row in current["cases"]:
        java = "21" if row["case"].endswith("j21") else "17"
        row["build_base"], row["runtime_base"] = base_references(java, HISTORICAL_BASE_REFERENCE_POLICY_ID)
        row["base_reference_policy"] = HISTORICAL_BASE_REFERENCE_POLICY_ID
    for source, normalized in zip(current["cases"], images.make_plan(current)["cases"], strict=True):
        assert declared_base_references(normalized) == declared_base_references(source)
        assert normalized["base_reference_policy"] == HISTORICAL_BASE_REFERENCE_POLICY_ID


@pytest.mark.parametrize("change", ("digest", "child-pin", "missing", "mixed", "unknown-policy"))
def test_unreviewed_or_mixed_campaign_references_fail(change):
    current = declaration()
    row = current["cases"][0]
    if change == "digest":
        row["build_base"] = row["build_base"][:-1] + "0"
    elif change == "child-pin":
        row["build_base"] = CONTAINER_BASES["17"][0].tag + "@" + CONTAINER_BASES["17"][0].amd64_manifest_digest
    elif change == "missing":
        del row["runtime_base"]
    elif change == "mixed":
        row["build_base"], row["runtime_base"] = base_references("17", HISTORICAL_BASE_REFERENCE_POLICY_ID)
    else:
        row["base_reference_policy"] = "unreviewed"
    with pytest.raises(images.ImageAssessmentError):
        images.make_plan(current)


def inspection(pin):
    return {"Id": pin.amd64_manifest_digest, "RepoDigests": [pin.tag.split(":")[0] + "@" + pin.index_digest],
            "Os": "linux", "Architecture": "amd64", "RootFS": {"Layers": ["sha256:" + "a" * 64]}}


@pytest.mark.parametrize("change", (None, "moved-tag", "stale-repodigests", "wrong-child"))
def test_collector_uses_reviewed_four_base_set_and_fails_on_drift(tmp_path, monkeypatch, change):
    calls = []
    pins = {key: pin for pair in CONTAINER_BASES.values() for pin in pair for key in (pin.tag, pin.reference)}

    def docker(command, *_args, **_kwargs):
        calls.append(command)
        if command[:3] == ["buildx", "imagetools", "inspect"]:
            digest = pins[command[-1]].index_digest
            if change in {"moved-tag", "stale-repodigests"}:
                digest = "sha256:" + "f" * 64
            return f"Digest: {digest}\n".encode()
        if command[0] == "pull":
            return b"pulled exact pin"
        reference = command[-1]
        state = inspection(pins[reference])
        if change == "moved-tag" and "@" not in reference:
            state["RepoDigests"] = ["maven@sha256:" + "f" * 64]
        if change == "wrong-child" and "@" in reference:
            state["Id"] = "sha256:" + "f" * 64
        return json.dumps([state]).encode()

    monkeypatch.setattr(collector, "docker", docker)
    if change:
        with pytest.raises(images.ImageAssessmentError):
            collector.refresh_bases(declaration()["cases"], tmp_path)
        assert not (tmp_path / "base-refresh.json").exists()
    else:
        resolved = collector.refresh_bases(declaration()["cases"], tmp_path)
        assert set(resolved) == {pin.reference for pair in CONTAINER_BASES.values() for pin in pair}
        pulls = [c for c in calls if c[0] == "pull"]
        assert len(pulls) == 4 and all("@sha256:" in c[-1] for c in pulls)


@pytest.mark.parametrize("change", (None, "index", "child", "platform", "missing", "reordered", "reference", "tag-receipt"))
def test_publisher_requires_exact_pinned_pair_and_actual_platform_identity(change):
    row = images.make_plan(declaration())["cases"][0]
    bases = [{"reference": pin.reference, "image_id": pin.amd64_manifest_digest,
              "platform": "linux/amd64", "repo_digests": inspection(pin)["RepoDigests"],
              "tag_index_digest": pin.index_digest, "amd64_manifest_digest": pin.amd64_manifest_digest,
              "config_digest": pin.config_digest,
              "rootfs": ["sha256:" + "a" * 64]} for pin in CONTAINER_BASES["17"]]
    if change == "index":
        bases[0]["repo_digests"] = ["maven@sha256:" + "f" * 64]
    elif change == "child":
        bases[0]["image_id"] = "sha256:" + "f" * 64
    elif change == "platform":
        bases[0]["platform"] = "linux/arm64"
    elif change == "missing":
        bases.pop()
    elif change == "reordered":
        bases.reverse()
    elif change == "reference":
        bases[0]["reference"] = "unreviewed"
    elif change == "tag-receipt":
        del bases[0]["tag_index_digest"]
    if change:
        with pytest.raises(images.ImageAssessmentError):
            publisher.validate_bases(bases, row)
    else:
        publisher.validate_bases(bases, row)
