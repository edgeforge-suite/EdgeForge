from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.kafka_models import KafkaMetadata
from appbuilder.metadata.models import MetadataProject
from appbuilder.target_profiles import TARGET_PROFILES

_CRUD_MANIFEST = Path("examples/input-projects/generated-app-ci-smoke/app-definition.yaml")
_PASSTHROUGH_MANIFEST = Path("examples/input-projects/country-router/app-definition.yaml")
_KAFKA_MANIFEST = Path("tests/fixtures/kafka-integration/manifest.yaml")
_EXPECTED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "frame-ancestors 'none'",
}


def test_security_headers_emitter_uses_generated_provenance_and_exact_contract(
    tmp_path: Path,
) -> None:
    from appbuilder.generation.security_headers_emitter import (
        emit_security_headers_source,
    )

    output_path = emit_security_headers_source(
        root_package="com.appbuilder.headers",
        target_profile_name="springboot-legacy-compatible",
        output_dir=tmp_path,
        source_manifest="app-definition.yaml",
        generation_run_id="security-headers-unit",
    )

    assert output_path == (
        tmp_path
        / "src/main/java/com/appbuilder/headers/config/SecurityHeadersFilter.java"
    )
    source = output_path.read_text(encoding="utf-8")
    assert "// EdgeForge-ownership: generated" in source
    assert "public class SecurityHeadersFilter extends OncePerRequestFilter" in source
    assert "@Order(Ordered.HIGHEST_PRECEDENCE)" in source
    assert source.count("response.setHeader(") == 4
    for name, value in _EXPECTED_HEADERS.items():
        assert f'response.setHeader("{name}", "{value}");' in source
    assert "Strict-Transport-Security" not in source
    assert "authentication" not in source.lower()
    assert "authorization" not in source.lower()


@pytest.mark.parametrize("profile_name", sorted(TARGET_PROFILES))
@pytest.mark.parametrize("archetype", ["crud", "passthrough", "kafka"])
def test_every_shipped_profile_and_archetype_emits_one_security_headers_filter(
    tmp_path: Path,
    profile_name: str,
    archetype: str,
) -> None:
    metadata = _metadata_for(archetype, profile_name=profile_name)
    output_dir = tmp_path / f"{archetype}-{profile_name}"
    report = generate_application(
        metadata,
        output_dir,
        source_manifest=f"{archetype}-manifest.yaml",
        generation_run_id="security-headers-profile-matrix",
    )

    header_paths = [
        path for path in report.files_created if path.name == "SecurityHeadersFilter.java"
    ]
    assert len(header_paths) == 1
    relative_header_path = header_paths[0].relative_to(output_dir).as_posix()
    assert relative_header_path.startswith("src/main/java/")
    assert relative_header_path.endswith(
        "/config/SecurityHeadersFilter.java"
    )
    assert len(list(output_dir.rglob("SecurityHeadersFilter.java"))) == 1


@pytest.mark.parametrize("archetype", ["crud", "passthrough", "kafka"])
def test_security_header_generation_is_deterministic_for_every_archetype(
    tmp_path: Path,
    archetype: str,
) -> None:
    metadata = _metadata_for(archetype, profile_name="springboot-legacy-compatible")
    first_output = tmp_path / f"{archetype}-first"
    second_output = tmp_path / f"{archetype}-second"

    for output_dir in (first_output, second_output):
        generate_application(
            metadata,
            output_dir,
            source_manifest=f"{archetype}-manifest.yaml",
            generation_run_id="security-headers-determinism",
        )

    assert _project_bytes(first_output) == _project_bytes(second_output)


def _metadata_for(
    archetype: str,
    *,
    profile_name: str,
) -> MetadataProject | KafkaMetadata:
    if archetype == "crud":
        metadata = build_metadata_project(_CRUD_MANIFEST)
        assert isinstance(metadata, MetadataProject)
        return metadata.model_copy(update={"target_profile": profile_name})
    if archetype == "passthrough":
        metadata = build_metadata_project(_PASSTHROUGH_MANIFEST)
        assert isinstance(metadata, MetadataProject)
        return metadata.model_copy(update={"target_profile": profile_name})
    if archetype == "kafka":
        metadata = build_metadata_project(_KAFKA_MANIFEST)
        assert isinstance(metadata, KafkaMetadata)
        return metadata.model_copy(update={"target_profile_name": profile_name})
    raise AssertionError(f"unknown test archetype: {archetype}")


def _project_bytes(project: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in sorted(project.rglob("*"))
        if path.is_file()
    }
