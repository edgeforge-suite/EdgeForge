"""Current-policy selection, fail-closed proof and retired public profiles."""

from pathlib import Path

import pytest

from appbuilder.generation.dependency_policy import DEPENDENCY_POLICIES, DEPENDENCY_POLICY_ID
from appbuilder.mcp.tools.catalog import describe_target_profile, list_target_profiles
from appbuilder.target_profiles.catalog import TARGET_PROFILES
from scripts.assess_generated_maven import AssessmentError
from scripts.collect_generated_maven_baseline import FIXTURES, PROFILES
from scripts.generated_maven_policy import validate_inventory, validate_libraries


def test_policy_mapping_is_immutable_and_exact():
    policy = DEPENDENCY_POLICIES[DEPENDENCY_POLICY_ID]
    assert dict(policy) == {"spring_boot": "4.1.1", "tomcat": "11.0.26", "jackson3": "3.1.7",
                            "jackson2_test": "2.21.7", "jackson_annotations": "2.21",
                            "kafka_lz4": "1.11.4", "spring_batch": "6.0.5", "router_validator": "3.0.6"}
    with pytest.raises(TypeError):
        policy["tomcat"] = "changed"
    with pytest.raises(TypeError):
        DEPENDENCY_POLICIES[DEPENDENCY_POLICY_ID] = {}


@pytest.mark.parametrize("profile", tuple(TARGET_PROFILES))
def test_retired_alias_has_normal_unsupported_diagnostic(profile):
    retired = profile + "-boot41-preview"
    assert retired not in {item.name for item in list_target_profiles()}
    with pytest.raises(ValueError, match="Unknown target profile.*Available profiles"):
        describe_target_profile(retired)


def test_collector_still_covers_thirty_ordinary_cases_twice():
    assert len(FIXTURES) == 10 and len(PROFILES) == 3
    assert set(PROFILES.values()) == {"springboot-legacy-compatible",
                                     "springboot-enterprise-postgres-java17", "springboot-standard-enterprise"}
    assert set(PROFILES.values()) <= set(TARGET_PROFILES)
    assert len({f"{shape}-{suffix}" for shape in FIXTURES for suffix in PROFILES}) == 30
    assert not Path("tests/fixtures/boot41-promotion/preview-identities.json").exists()


def records(kafka=False, batch=False, router=False):
    entries = {"org.apache.tomcat.embed:tomcat-embed-" + part: "11.0.26" for part in ("core", "el", "websocket")}
    entries.update({"tools.jackson.core:jackson-core": "3.1.7", "tools.jackson.core:jackson-databind": "3.1.7",
                    "com.fasterxml.jackson.core:jackson-annotations": "2.21"})
    if kafka:
        entries["at.yawk.lz4:lz4-java"] = "1.11.4"
    if batch:
        entries["org.springframework.batch:spring-batch-core"] = "6.0.5"
    if router:
        entries["com.networknt:json-schema-validator"] = "3.0.6"
    return [{"group": name.split(":")[0], "artifact": name.split(":")[1], "version": version, "scope": "compile"}
            for name, version in entries.items()]


@pytest.mark.parametrize("kafka,batch,router", ((False, False, False), (False, True, False), (True, False, False), (True, False, True)))
def test_policy_proof_checks_applicable_resolved_and_packaged_outputs(kafka, batch, router):
    inventory = records(kafka, batch, router)
    result = validate_inventory(inventory, kafka=kafka, batch=batch, router=router)
    assert result["dependency_policy"] == DEPENDENCY_POLICY_ID
    libraries = sorted(r["artifact"] + "-" + r["version"] + ".jar" for r in inventory)
    assert validate_libraries(libraries, kafka=kafka, batch=batch, router=router)["packaged_policy"] == "passed"
    inventory[0]["version"] = "11.0.24"
    with pytest.raises(AssessmentError, match="Tomcat"):
        validate_inventory(inventory, kafka=kafka, batch=batch, router=router)


@pytest.mark.parametrize("scope,version", (("compile", "2.21.7"), ("test", "2.21.5")))
def test_jackson2_proof_fails_for_runtime_or_old_test_version(scope, version):
    inventory = records()
    inventory.append({"group": "com.fasterxml.jackson.core", "artifact": "jackson-core", "version": version, "scope": scope})
    with pytest.raises(AssessmentError, match="Jackson 2"):
        validate_inventory(inventory, kafka=False, batch=False, router=False)


def test_jackson2_cannot_be_packaged():
    libraries = sorted([r["artifact"] + "-" + r["version"] + ".jar" for r in records()] + ["jackson-core-2.21.7.jar"])
    with pytest.raises(AssessmentError, match="Jackson 2"):
        validate_libraries(libraries, kafka=False, batch=False, router=False)
