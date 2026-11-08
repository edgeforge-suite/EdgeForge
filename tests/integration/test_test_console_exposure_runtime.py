from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from zipfile import ZipFile

import pytest

from appbuilder.generation import generate_application
from appbuilder.generation.batch_metadata import owns_batch_metadata
from appbuilder.metadata import build_metadata_project
from appbuilder.target_profiles.catalog import TARGET_PROFILES

pytestmark = pytest.mark.skipif(
    os.getenv("EDGEFORGE_RUN_GENERATED_RUNTIME_TESTS") != "1",
    reason="generated-app Maven/runtime proof runs in the generated-app compile workflow",
)


def test_legacy_console_transition_is_not_packaged_or_served(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "legacy-console-transition"
    # Console ownership adoption must not discard JDBC Batch schema provenance.
    metadata = build_metadata_project(
        Path("examples/input-projects/generated-app-ci-smoke/app-definition.yaml")
    )
    assert not owns_batch_metadata(metadata, TARGET_PROFILES[metadata.target_profile])
    generate_application(metadata, output_dir, generation_run_id="legacy-console-local")

    subprocess.run(
        ["mvn", "-q", "-DskipTests", "package"],
        cwd=output_dir,
        check=True,
        timeout=180,
    )
    stale_console_path = output_dir / "target/classes/static/index.html"
    assert stale_console_path.exists()

    (output_dir / "db/schema-baseline.json").unlink()
    console_path = output_dir / "src/main/resources/static/index.html"
    legacy_console = console_path.read_text(encoding="utf-8").replace(
        "<!-- EdgeForge-ownership: generated -->\n",
        "",
    )
    console_path.write_text(legacy_console, encoding="utf-8")

    profile_name = "springboot-runtime-proof-console-off"
    TARGET_PROFILES[profile_name] = TARGET_PROFILES[
        "springboot-legacy-compatible"
    ].model_copy(
        update={
            "name": profile_name,
            "emit_test_console": False,
        }
    )
    metadata.target_profile = profile_name
    try:
        report = generate_application(
            metadata,
            output_dir,
            generation_run_id="legacy-console-enterprise",
        )
    finally:
        TARGET_PROFILES.pop(profile_name, None)

    archive_path = (
        output_dir
        / ".edgeforge-backups/src/main/resources/static/index.html.legacy.bak"
    )
    assert report.generation_mode == "legacy"
    assert archive_path.read_text(encoding="utf-8") == legacy_console
    assert not console_path.exists()
    assert not list((output_dir / "src/main/resources").rglob("index.html*"))
    assert not (output_dir / "target").exists()
    assert any(
        "generated stale test-console build output pruned" in warning
        for warning in report.warnings
    )

    # Deliberately omit Maven's clean phase: generation itself must have removed
    # the stale console resource and controller bytecode from the prior build.
    subprocess.run(
        ["mvn", "-q", "-DskipTests", "package"],
        cwd=output_dir,
        check=True,
        timeout=180,
    )
    jar_path = next(
        path
        for path in (output_dir / "target").glob("*.jar")
        if not path.name.endswith(".jar.original")
    )
    with ZipFile(jar_path) as jar_file:
        leaked_entries = [
            name
            for name in jar_file.namelist()
            if "static/index" in name
            or "DemoController" in name
            or "legacy.bak" in name
            or "edgeforge-backups" in name
        ]
    assert leaked_entries == []

    port = _unused_local_port()
    log_path = tmp_path / "generated-app.log"
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                "java",
                "-jar",
                str(jar_path),
                f"--server.port={port}",
            ],
            cwd=output_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_for_status(f"http://127.0.0.1:{port}/actuator/health", 200)
            for path in (
                "/",
                "/index.html",
                "/index.html.legacy.bak",
                "/api/demo/entities",
            ):
                assert _http_status(f"http://127.0.0.1:{port}{path}") == 404
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


def _wait_for_status(url: str, expected_status: int) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if _http_status(url) == expected_status:
                return
        except URLError:
            pass
        time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for HTTP {expected_status} from {url}")


def _http_status(url: str) -> int:
    try:
        with urlopen(url, timeout=2) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
