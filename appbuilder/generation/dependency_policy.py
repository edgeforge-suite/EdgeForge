"""Immutable first supported generated-app dependency policy.

Never change a published policy's mapping; add a new ID for a future policy.
Applicability is explicit: LZ4 is Kafka-only, Batch requires jobs, and Jackson 2
is test-only. Boot's BOM supplies Batch and shared annotations.
"""

from types import MappingProxyType

DEPENDENCY_POLICY_ID = "ef-v5-maven-1"
DEPENDENCY_POLICIES = MappingProxyType({
    DEPENDENCY_POLICY_ID: MappingProxyType({
        "spring_boot": "4.1.1",
        "tomcat": "11.0.26",
        "jackson3": "3.1.7",
        "jackson2_test": "2.21.7",
        "jackson_annotations": "2.21",
        "kafka_lz4": "1.11.4",
        "spring_batch": "6.0.5",
        "router_validator": "3.0.6",
    }),
})


def policy_properties(enabled: bool) -> list[str]:
    if not enabled:
        return []
    policy = DEPENDENCY_POLICIES[DEPENDENCY_POLICY_ID]
    return [
        f"        <{name}>{policy[key]}</{name}>"
        for name, key in (("tomcat.version", "tomcat"),
                          ("jackson-bom.version", "jackson3"),
                          ("jackson-2-bom.version", "jackson2_test"))
    ]


def kafka_dependency_management(enabled: bool) -> list[str]:
    if not enabled:
        return []
    version = DEPENDENCY_POLICIES[DEPENDENCY_POLICY_ID]["kafka_lz4"]
    return [
        "    <dependencyManagement>",
        "        <dependencies>",
        "            <dependency>",
        "                <groupId>at.yawk.lz4</groupId>",
        "                <artifactId>lz4-java</artifactId>",
        f"                <version>{version}</version>",
        "            </dependency>",
        "        </dependencies>",
        "    </dependencyManagement>",
    ]
