from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

from appbuilder.generation import generate_application

pytestmark = pytest.mark.skipif(
    os.getenv("EDGEFORGE_RUN_GENERATED_RUNTIME_TESTS") != "1",
    reason="generated-app Maven/runtime proof runs in the generated-app compile workflow",
)

_MANIFEST = Path("tests/fixtures/kafka-integration/manifest.yaml")


@pytest.mark.parametrize("profile", ["springboot-legacy-compatible"])
def test_kafka_actuator_exposure_defaults_to_health_and_allows_explicit_opt_in(
    tmp_path: Path,
    profile: str,
) -> None:
    first_output = tmp_path / "kafka-first"
    second_output = tmp_path / "kafka-second"
    from appbuilder.contracts import load_project_definition
    from appbuilder.metadata.kafka_translation import translate_kafka_project

    definition = load_project_definition(_MANIFEST)
    definition.target_profile = profile
    metadata = translate_kafka_project(definition, _MANIFEST.parent)

    for output_dir in (first_output, second_output):
        generate_application(
            metadata,
            output_dir,
            source_manifest=str(_MANIFEST),
            generation_run_id="kafka-actuator-runtime",
        )

    assert _project_bytes(first_output) == _project_bytes(second_output)

    subprocess.run(
        ["mvn", "-q", "clean", "verify"],
        cwd=first_output,
        check=True,
        timeout=180,
    )
    jar_path = next(
        path
        for path in (first_output / "target").glob("*.jar")
        if not path.name.endswith(".jar.original")
    )

    _assert_actuator_surface(
        jar_path=jar_path,
        working_directory=first_output,
        tmp_path=tmp_path,
        exposure=None,
        expected_metrics_status=404,
        expected_prometheus_status=404,
    )
    _assert_actuator_surface(
        jar_path=jar_path,
        working_directory=first_output,
        tmp_path=tmp_path,
        exposure="health,metrics,prometheus",
        expected_metrics_status=200,
        expected_prometheus_status=200,
    )


def _project_bytes(project: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in sorted(project.rglob("*"))
        if path.is_file()
    }


def _assert_actuator_surface(
    *,
    jar_path: Path,
    working_directory: Path,
    tmp_path: Path,
    exposure: str | None,
    expected_metrics_status: int,
    expected_prometheus_status: int,
) -> None:
    port = _unused_local_port()
    mode = "default" if exposure is None else "opt-in"
    log_path = tmp_path / f"kafka-{mode}.log"
    environment = os.environ.copy()
    environment.pop("MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE", None)
    if exposure is not None:
        environment["MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE"] = exposure

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                "java",
                "-jar",
                str(jar_path),
                f"--server.port={port}",
                "--spring.kafka.listener.auto-startup=false",
            ],
            cwd=working_directory,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            health_url = f"http://127.0.0.1:{port}/actuator/health"
            _wait_for_status(health_url, 200, process=process, log_path=log_path)
            assert _http_status(f"http://127.0.0.1:{port}/actuator/metrics") == (
                expected_metrics_status
            )
            assert _http_status(f"http://127.0.0.1:{port}/actuator/prometheus") == (
                expected_prometheus_status
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_status(
    url: str,
    expected_status: int,
    *,
    process: subprocess.Popen[str],
    log_path: Path,
) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                "Generated Kafka app exited before becoming healthy:\n"
                + log_path.read_text(encoding="utf-8")
            )
        try:
            if _http_status(url) == expected_status:
                return
        except URLError:
            pass
        time.sleep(0.25)
    raise AssertionError(
        f"Timed out waiting for HTTP {expected_status} from {url}:\n"
        + log_path.read_text(encoding="utf-8")
    )


def _http_status(url: str) -> int:
    try:
        with urlopen(url, timeout=2) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
