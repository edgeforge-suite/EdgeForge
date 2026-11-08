from __future__ import annotations

import os
import socket
import subprocess
import time
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

from appbuilder.generation import generate_application
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.kafka_models import KafkaMetadata
from appbuilder.metadata.models import MetadataProject
from appbuilder.target_profiles import TARGET_PROFILES

pytestmark = pytest.mark.skipif(
    os.getenv("EDGEFORGE_RUN_GENERATED_RUNTIME_TESTS") != "1",
    reason="generated-app Maven/runtime proof runs in the generated-app compile workflow",
)

_CRUD_MANIFEST = Path("examples/input-projects/generated-app-ci-smoke/app-definition.yaml")
_PASSTHROUGH_MANIFEST = Path("examples/input-projects/country-router/app-definition.yaml")
_KAFKA_MANIFEST = Path("tests/fixtures/kafka-integration/manifest.yaml")
_EXPECTED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "frame-ancestors 'none'",
}
_TEST_JWK_SET_URI = "http://127.0.0.1:1/unused-test-jwks"


@pytest.mark.parametrize(
    "archetype,profile",
    [
        ("crud", None),
        ("passthrough", None),
        ("kafka", None),
        ("crud", "springboot-legacy-compatible"),
        ("passthrough", "springboot-legacy-compatible"),
        ("kafka", "springboot-legacy-compatible"),
    ],
)
def test_generated_archetype_runtime_emits_single_security_header_values(
    tmp_path: Path,
    archetype: str,
    profile: str | None,
) -> None:
    metadata = _metadata_for(archetype)
    if profile is not None:
        if isinstance(metadata, KafkaMetadata):
            from appbuilder.contracts import load_project_definition
            from appbuilder.metadata.kafka_translation import translate_kafka_project

            definition = load_project_definition(_KAFKA_MANIFEST)
            definition.target_profile = profile
            metadata = translate_kafka_project(definition, _KAFKA_MANIFEST.parent)
        else:
            metadata.target_profile = profile
    first_output = tmp_path / f"{archetype}-first"
    second_output = tmp_path / f"{archetype}-second"
    for output_dir in (first_output, second_output):
        generate_application(
            metadata,
            output_dir,
            source_manifest=f"{archetype}-runtime-manifest.yaml",
            generation_run_id="security-headers-runtime",
        )

    assert _project_bytes(first_output) == _project_bytes(second_output)
    jar_path = _build_generated_application(first_output)
    _assert_runtime_headers(
        jar_path=jar_path,
        working_directory=first_output,
        log_path=tmp_path / f"{archetype}.log",
        kafka=archetype == "kafka",
    )


def test_emit_security_profile_keeps_headers_single_valued_without_an_idp(
    tmp_path: Path,
) -> None:
    profile_name = "springboot-test-security-headers"
    TARGET_PROFILES[profile_name] = TARGET_PROFILES[
        "springboot-legacy-compatible"
    ].model_copy(
        update={
            "name": profile_name,
            "emit_security": True,
            "emit_test_console": False,
        }
    )
    try:
        metadata = build_metadata_project(_CRUD_MANIFEST)
        assert isinstance(metadata, MetadataProject)
        metadata = metadata.model_copy(update={"target_profile": profile_name})
        first_output = tmp_path / "secured-crud-first"
        second_output = tmp_path / "secured-crud-second"
        for output_dir in (first_output, second_output):
            generate_application(
                metadata,
                output_dir,
                source_manifest="secured-crud-runtime-manifest.yaml",
                generation_run_id="security-headers-secured-runtime",
            )
    finally:
        TARGET_PROFILES.pop(profile_name, None)

    assert _project_bytes(first_output) == _project_bytes(second_output)
    jar_path = _build_generated_application(
        first_output,
        system_properties={
            "spring.security.oauth2.resourceserver.jwt.jwk-set-uri": _TEST_JWK_SET_URI,
        },
    )
    _assert_runtime_headers(
        jar_path=jar_path,
        working_directory=first_output,
        log_path=tmp_path / "secured-crud.log",
        application_properties={
            "spring.security.oauth2.resourceserver.jwt.jwk-set-uri": _TEST_JWK_SET_URI,
        },
        additional_paths=(("/security-header-probe", 401),),
    )


def _metadata_for(archetype: str) -> MetadataProject | KafkaMetadata:
    manifest = {
        "crud": _CRUD_MANIFEST,
        "passthrough": _PASSTHROUGH_MANIFEST,
        "kafka": _KAFKA_MANIFEST,
    }[archetype]
    metadata = build_metadata_project(manifest)
    assert isinstance(metadata, (MetadataProject, KafkaMetadata))
    return metadata


def _build_generated_application(
    project: Path,
    *,
    system_properties: dict[str, str] | None = None,
) -> Path:
    command = ["mvn", "-q"]
    command.extend(
        f"-D{name}={value}" for name, value in (system_properties or {}).items()
    )
    command.extend(["clean", "verify"])
    subprocess.run(command, cwd=project, check=True, timeout=180)
    return next(
        path
        for path in (project / "target").glob("*.jar")
        if not path.name.endswith(".jar.original")
    )


def _assert_runtime_headers(
    *,
    jar_path: Path,
    working_directory: Path,
    log_path: Path,
    kafka: bool = False,
    application_properties: dict[str, str] | None = None,
    additional_paths: tuple[tuple[str, int], ...] = (),
) -> None:
    port = _unused_local_port()
    command = ["java", "-jar", str(jar_path), f"--server.port={port}"]
    if kafka:
        command.append("--spring.kafka.listener.auto-startup=false")
    command.extend(
        f"--{name}={value}" for name, value in (application_properties or {}).items()
    )

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=working_directory,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            health_url = f"http://127.0.0.1:{port}/actuator/health"
            headers = _wait_for_headers(
                health_url,
                process=process,
                log_path=log_path,
            )
            _assert_exact_header_contract(headers)
            for path, expected_status in additional_paths:
                status, probe_headers = _request(f"http://127.0.0.1:{port}{path}")
                assert status == expected_status
                _assert_exact_header_contract(probe_headers)
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _assert_exact_header_contract(headers: dict[str, list[str]]) -> None:
    for name, value in _EXPECTED_HEADERS.items():
        assert headers.get(name.lower()) == [value]
    assert headers.get("strict-transport-security") is None


def _wait_for_headers(
    url: str,
    *,
    process: subprocess.Popen[str],
    log_path: Path,
) -> dict[str, list[str]]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                "Generated app exited before becoming healthy:\n"
                + log_path.read_text(encoding="utf-8")
            )
        try:
            status, headers = _request(url)
            if status == 200:
                return headers
        except URLError:
            pass
        time.sleep(0.25)
    raise AssertionError(
        f"Timed out waiting for {url}:\n" + log_path.read_text(encoding="utf-8")
    )


def _request(url: str) -> tuple[int, dict[str, list[str]]]:
    try:
        with urlopen(url, timeout=2) as response:
            return int(response.status), _normalized_headers(response.headers)
    except HTTPError as exc:
        return int(exc.code), _normalized_headers(exc.headers)


def _normalized_headers(headers: Message) -> dict[str, list[str]]:
    return {
        name.lower(): headers.get_all(name)
        for name in headers.keys()
    }


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _project_bytes(project: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in sorted(project.rglob("*"))
        if path.is_file()
    }
