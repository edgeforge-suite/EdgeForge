"""Cheap controls for the actual CI container scenario, without Docker access."""

import pytest

from appbuilder.generation.container_policy import base_references
from scripts.smoke.boot41_kafka_lz4_container_proof import prepare_app


@pytest.mark.parametrize("java,profile", (("17", "springboot-legacy-compatible"),
                                         ("21", "springboot-standard-enterprise")))
def test_native_probe_uses_unchanged_generated_nonroot_container_and_runtime_scope(tmp_path, java, profile):
    app = prepare_app(tmp_path, java, profile)
    dockerfile = (app / "Dockerfile").read_text()
    assert f"FROM {base_references(java)[1]}" in dockerfile
    assert "USER edgeforge" in dockerfile
    assert 'ENTRYPOINT ["java", "-jar", "/app/app.jar"]' in dockerfile
    pom = (app / "pom.xml").read_text()
    assert pom.count("<artifactId>lz4-java</artifactId>") == 1
    assert "<dependencyManagement>" in pom
    source = (app / "src/main/java/proof/Lz4ContainerProof.java").read_text()
    assert "__APP" not in source
    for guard in ('uid != 0', 'Native library unexpectedly loaded', 'Java fallback',
                  'compression.type', 'LZ4_ROUNDTRIP_PROOF', '/proc/self/maps',
                  'NOFOLLOW_LINKS', 'nlink', 'isLoaded', 'lz4-java-1.11.4.jar'):
        assert guard in source
    assert "import net.jpountz" not in source
