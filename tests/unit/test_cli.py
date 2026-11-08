import copy
import io
import json
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from appbuilder.cli import main
from appbuilder.core.path_safety import ALLOWED_ROOTS_ENV, SHARED_MODE_ENV
from appbuilder.generation.engine import GenerationReport
from appbuilder.harness import HarnessCheck, HarnessCheckSeverity, HarnessReport
from appbuilder.metadata import MetadataProject


def test_cli_generate_command_creates_app(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    output_dir = tmp_path / "BuiltAppCli"
    stdout = io.StringIO()

    with redirect_stdout(stdout):
        exit_code = main(
            [
                "generate",
                "--manifest",
                "examples/input-projects/xyz-accounts-modernization/app-definition.yaml",
                "--output",
                str(output_dir),
                "--generation-run-id",
                "cli-test",
            ]
        )

    assert exit_code == 0
    assert (output_dir / "pom.xml").exists()
    assert "Harness: PASSED (static compatibility checks)" in stdout.getvalue()


def test_cli_returns_non_zero_when_harness_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    metadata = _load_xyz_metadata()
    harness_report = HarnessReport(
        output_dir=tmp_path / "BrokenApp",
        checks=[
            HarnessCheck(
                name="generated_app_has_no_appbuilder_imports",
                severity=HarnessCheckSeverity.ERROR,
                passed=False,
                message="Found forbidden import.",
            )
        ],
    )

    def fake_build_metadata_project(manifest_path: Path) -> MetadataProject:
        assert manifest_path == Path("fake-manifest.yaml")
        return metadata

    def fake_generate_application(*args, **kwargs) -> GenerationReport:
        return GenerationReport(
            output_dir=tmp_path / "BrokenApp",
            files_created=[],
            warnings=["harness:generated_app_has_no_appbuilder_imports: Found forbidden import."],
            harness_report=harness_report,
        )

    monkeypatch.setattr("appbuilder.cli.build_metadata_project", fake_build_metadata_project)
    monkeypatch.setattr("appbuilder.cli.generate_application", fake_generate_application)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(
            [
                "generate",
                "--manifest",
                "fake-manifest.yaml",
                "--output",
                str(tmp_path / "BrokenApp"),
            ]
        )

    output = stdout.getvalue()
    assert exit_code == 1
    assert "Harness: FAILED" in output
    assert "ERROR generated_app_has_no_appbuilder_imports" in output


def test_cli_prints_help_when_no_command_selected() -> None:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main([])

    assert exit_code == 1
    assert "usage:" in stdout.getvalue()


def test_assess_command_with_mock_spec(monkeypatch) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "CRM API", "version": "1.0"},
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "properties": {
                        "customerId": {"type": "string"},
                        "customerName": {"type": "string"},
                    },
                },
                "CreateCustomerRequest": {
                    "type": "object",
                    "properties": {"customerName": {"type": "string"}},
                },
                "PageableObject": {"type": "object"},
            }
        },
        "paths": {
            "/customers": {
                "post": {
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Customer"}
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    monkeypatch.setattr("appbuilder.cli.fetch_openapi_spec", lambda url: spec)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(["assess", "--swagger", "http://fake/v3/api-docs"])

    output = stdout.getvalue()
    assert exit_code == 0
    assert "EdgeForge Assessment — CRM API (1.0)" in output
    assert "Customer" in output
    assert "CreateCustomerRequest" in output


def test_cli_generate_validate_schema_flag_rejects_invalid_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    manifest = tmp_path / "invalid-app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "app_archetype: event-router",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        exit_code = main(
            [
                "generate",
                "--manifest",
                str(manifest),
                "--output",
                str(tmp_path / "out"),
                "--validate-schema",
            ]
        )

    output = stderr.getvalue()
    assert exit_code == 1
    assert "schema_version" in output
    assert "event-router" in output


def test_cli_local_dev_unconstrained_when_roots_and_shared_mode_unset(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    metadata = _load_xyz_metadata()
    manifest = Path("examples/input-projects/workspace-items/app-definition.yaml").resolve()
    output_dir = tmp_path / "local-dev-out-of-tree"

    def fake_build_metadata_project(manifest_path: Path) -> MetadataProject:
        assert manifest_path == manifest
        return metadata

    def fake_generate_application(*args, **kwargs) -> GenerationReport:
        assert args[1] == output_dir
        return GenerationReport(output_dir=output_dir, files_created=[], warnings=[])

    monkeypatch.setattr("appbuilder.cli.build_metadata_project", fake_build_metadata_project)
    monkeypatch.setattr("appbuilder.cli.generate_application", fake_generate_application)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(
            [
                "generate",
                "--manifest",
                str(manifest),
                "--output",
                str(output_dir),
            ]
        )

    assert exit_code == 0
    assert "Generated application at:" in stdout.getvalue()


def test_cli_generate_with_allowed_roots_accepts_in_root_paths(
    monkeypatch,
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "workspace-items"
    shutil.copytree(Path("examples/input-projects/workspace-items"), package_root)
    output_dir = tmp_path / "BuiltAppCliAllowed"
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(tmp_path))
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = main(
            [
                "generate",
                "--manifest",
                f"{package_root.name}/app-definition.yaml",
                "--output",
                output_dir.name,
                "--generation-run-id",
                "cli-allowed-root-test",
                "--validate-schema",
            ]
        )

    assert exit_code == 0
    assert (output_dir / "pom.xml").exists()


def test_cli_generate_with_allowed_roots_rejects_repo_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(tmp_path))
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        exit_code = main(
            [
                "generate",
                "--manifest",
                str(Path("examples/input-projects/workspace-items/app-definition.yaml").resolve()),
                "--output",
                str(tmp_path / "BuiltAppCliRejected"),
            ]
        )

    assert exit_code == 1
    assert "manifest_path must resolve inside an allowed root" in stderr.getvalue()
    assert not (tmp_path / "BuiltAppCliRejected").exists()


def test_cli_generate_with_allowed_roots_rejects_out_of_root_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "app-definition.yaml"
    manifest.write_text(
        "\n".join(
            [
                "app_name: Sample",
                "bounded_context: accounts",
                "schema_version: '2.0'",
                "app_archetype: crud",
                "target_profile: springboot-legacy-compatible",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(tmp_path))
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        exit_code = main(
            [
                "generate",
                "--manifest",
                str(manifest),
                "--output",
                str(tmp_path.parent / "outside-cli-output"),
            ]
        )

    assert exit_code == 1
    assert "output must resolve inside an allowed root" in stderr.getvalue()


def test_cli_validate_schema_with_allowed_roots_rejects_traversal(
    monkeypatch,
    tmp_path: Path,
) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    (outside_root / "app-definition.yaml").write_text(
        "schema_version: '2.0'\napp_name: Outside\nbounded_context: outside\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(allowed_root))
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        exit_code = main(
            [
                "generate",
                "--manifest",
                "../outside/app-definition.yaml",
                "--output",
                "generated",
                "--validate-schema",
            ]
        )

    assert exit_code == 1
    assert "manifest_path must resolve inside an allowed root" in stderr.getvalue()


def test_cli_assess_with_allowed_roots_rejects_symlink_output_escape(
    monkeypatch,
    tmp_path: Path,
) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    (allowed_root / "linked-outside").symlink_to(outside_root, target_is_directory=True)
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(allowed_root))
    monkeypatch.delenv(SHARED_MODE_ENV, raising=False)
    monkeypatch.setattr("appbuilder.cli.fetch_openapi_spec", lambda url: {"openapi": "3.0.0"})

    stderr = io.StringIO()
    with redirect_stderr(stderr):
        exit_code = main(
            [
                "assess",
                "--swagger",
                "http://fake/v3/api-docs",
                "--output",
                "linked-outside/report.json",
            ]
        )

    assert exit_code == 1
    assert "output must resolve inside an allowed root" in stderr.getvalue()
    assert not (outside_root / "report.json").exists()


def test_cli_shared_mode_requires_allowed_roots_for_generate_validate_and_assess(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    monkeypatch.setenv(SHARED_MODE_ENV, "1")

    scenarios = [
        [
            "generate",
            "--manifest",
            "examples/input-projects/workspace-items/app-definition.yaml",
            "--output",
            str(tmp_path / "shared-generate"),
        ],
        [
            "generate",
            "--manifest",
            "examples/input-projects/workspace-items/app-definition.yaml",
            "--output",
            str(tmp_path / "shared-validate"),
            "--validate-schema",
        ],
        ["assess", "--swagger", "http://fake/v3/api-docs"],
    ]
    for argv in scenarios:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(argv)

        assert exit_code == 1
        assert "EDGEFORGE_MCP_ALLOWED_ROOTS must be set" in stderr.getvalue()


def _load_xyz_metadata() -> MetadataProject:
    payload = json.loads(
        Path("tests/golden_contracts/xyz_accounts_metadata.json").read_text(encoding="utf-8")
    )
    return MetadataProject.model_validate(copy.deepcopy(payload))
