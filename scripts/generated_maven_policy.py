"""Read-only approved-policy assertions over actual build/assessment outputs."""

import zipfile
from pathlib import Path

from appbuilder.generation.dependency_policy import DEPENDENCY_POLICY_ID
from scripts.assess_generated_maven import require


def validate_inventory(records, *, kafka, batch, router):
    expected = {
        **{f"org.apache.tomcat.embed:tomcat-embed-{part}": "11.0.26"
           for part in ("core", "el", "websocket")},
        "tools.jackson.core:jackson-core": "3.1.7",
        "tools.jackson.core:jackson-databind": "3.1.7",
        "com.fasterxml.jackson.core:jackson-annotations": "2.21",
        **({"at.yawk.lz4:lz4-java": "1.11.4"} if kafka else {}),
        **({"org.springframework.batch:spring-batch-core": "6.0.5"} if batch else {}),
        **({"com.networknt:json-schema-validator": "3.0.6"} if router else {}),
    }
    actual = {}
    for record in records:
        coordinate = record["group"] + ":" + record["artifact"]
        actual.setdefault(coordinate, set()).add(record["version"])
        if record["group"].startswith("tools.jackson."):
            require(record["version"] == "3.1.7", "unaligned Jackson 3 module")
        if coordinate in {"com.fasterxml.jackson.core:jackson-core", "com.fasterxml.jackson.core:jackson-databind"}:
            require(record["version"] == "2.21.7" and record["scope"] == "test", "Jackson 2 must be corrected and test-only")
        if record["group"] == "org.apache.tomcat.embed":
            require(record["version"] == "11.0.26", "unaligned embedded Tomcat")
    for coordinate, version in expected.items():
        require(actual.get(coordinate) == {version}, f"approved policy mismatch: {coordinate}")
    require(("at.yawk.lz4:lz4-java" in actual) == kafka, "LZ4 must occur only in Kafka graphs")
    require("org.lz4:lz4-java" not in actual, "obsolete LZ4 coordinate")
    require(("org.springframework.batch:spring-batch-core" in actual) == batch, "Batch applicability mismatch")
    require(("com.networknt:json-schema-validator" in actual) == router, "router validator applicability mismatch")
    return {"dependency_policy": DEPENDENCY_POLICY_ID, "resolved_policy": "passed"}


def validate_package(app: Path, *, kafka, batch, router):
    jars = list((app / "target").glob("*.jar"))
    require(len(jars) == 1, "expected exactly one packaged app for policy inspection")
    jar = jars[0]
    with zipfile.ZipFile(jar) as archive:
        libraries = sorted(name.rsplit("/", 1)[-1] for name in archive.namelist()
                           if name.startswith("BOOT-INF/lib/") and name.endswith(".jar"))
    return validate_libraries(libraries, kafka=kafka, batch=batch, router=router)


def validate_libraries(libraries, *, kafka, batch, router):
    require(isinstance(libraries, list)
            and all(isinstance(name, str) and "/" not in name and name.endswith(".jar") for name in libraries)
            and libraries == sorted(set(libraries)),
            "invalid packaged library inventory")
    required = ["tomcat-embed-core-11.0.26.jar", "tomcat-embed-el-11.0.26.jar",
                "tomcat-embed-websocket-11.0.26.jar", "jackson-core-3.1.7.jar",
                "jackson-databind-3.1.7.jar", "jackson-annotations-2.21.jar"]
    if kafka:
        required.append("lz4-java-1.11.4.jar")
    if batch:
        required.append("spring-batch-core-6.0.5.jar")
    if router:
        required.append("json-schema-validator-3.0.6.jar")
    for library in required:
        require(library in libraries, f"missing approved packaged library: {library}")
    require(not any(name.startswith(("jackson-core-2", "jackson-databind-2")) for name in libraries),
            "Jackson 2 mapper/core packaged unexpectedly")
    for name in libraries:
        if name.startswith("jackson-") and name != "jackson-annotations-2.21.jar":
            require(name.endswith("-3.1.7.jar"), "unaligned packaged Jackson module")
        if name.startswith("tomcat-embed-"):
            require(name.endswith("-11.0.26.jar"), "unaligned packaged Tomcat")
    require(any(name.startswith("lz4-java-") for name in libraries) == kafka, "packaged LZ4 applicability mismatch")
    require(any(name.startswith("spring-batch-core-") for name in libraries) == batch, "packaged Batch applicability mismatch")
    require(any(name.startswith("json-schema-validator-") for name in libraries) == router, "packaged validator applicability mismatch")
    return {"dependency_policy": DEPENDENCY_POLICY_ID, "packaged_policy": "passed", "packaged_libraries": libraries}
