from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from appbuilder.cli import main as cli_main
from appbuilder.contracts import validate_package
from appbuilder.core.path_safety import resolve_allowed_file
from appbuilder.mcp.tools.catalog import (
    describe_target_profile,
    list_archetypes,
    list_target_profiles,
)
from appbuilder.mcp.tools.generation import (
    _ALLOWED_ROOTS_ENV,
    generate_app,
    translate_project,
    validate_manifest,
)
from appbuilder.mcp.tools.schema import get_manifest_schema
from appbuilder.mcp_server import create_mcp_server, register_tools

WORKSPACE_MANIFEST = Path("examples/input-projects/workspace-items/app-definition.yaml")


def _copy_fixture_into_allowed_root(tmp_path: Path, fixture_dir: Path) -> Path:
    package_root = tmp_path / fixture_dir.name
    shutil.copytree(fixture_dir, package_root)
    return package_root


def test_validate_manifest_matches_schema_validation_for_valid_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_root = _copy_fixture_into_allowed_root(tmp_path, WORKSPACE_MANIFEST.parent)
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))

    result = validate_manifest(str(package_root / "app-definition.yaml"))

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


def test_validate_manifest_reports_invalid_manifest_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))

    result = validate_manifest(str(manifest))

    assert result.valid is False
    assert any("schema_version" in error for error in result.errors)
    assert any("event-router" in error for error in result.errors)
    assert result.warnings == []


@pytest.mark.parametrize(
    "yaml_text",
    [
        "null\n",
        "42\n",
        "scalar\n",
        "- item\n",
    ],
    ids=["null", "number", "string", "sequence"],
)
def test_validate_manifest_reports_non_mapping_yaml_as_schema_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    yaml_text: str,
) -> None:
    manifest = tmp_path / "non-mapping-app-definition.yaml"
    manifest.write_text(yaml_text, encoding="utf-8")
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))

    raw_errors = validate_package(yaml.safe_load(yaml_text))
    result = validate_manifest(str(manifest))

    assert raw_errors
    assert all(error.startswith("$: ") for error in raw_errors)
    assert result.valid is False
    assert result.errors == raw_errors
    assert result.warnings == []


def test_translate_project_returns_workspace_summary_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "workspace-items"
    shutil.copytree(WORKSPACE_MANIFEST.parent, package_root)
    manifest = package_root / "app-definition.yaml"
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))
    response = package_root / "upstream/workspace-response.json"
    payload = json.loads(response.read_text())
    payload["annotation"] = "synthetic unmapped-field warning control"
    response.write_text(json.dumps(payload))
    before = _tree_snapshot(package_root)

    result = translate_project(str(manifest))

    assert result.app_name == "Workspace Items"
    assert result.app_archetype == "crud"
    assert result.entity_count == 2
    assert result.operation_count == 2
    assert result.warnings
    assert any("annotation" in warning for warning in result.warnings)
    assert _tree_snapshot(package_root) == before


def test_generate_app_matches_cli_generation_for_workspace_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixed_datetime = _fixed_datetime_class()
    monkeypatch.setattr("appbuilder.generation.engine.datetime", fixed_datetime)
    package_root = _copy_fixture_into_allowed_root(tmp_path, WORKSPACE_MANIFEST.parent)
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))
    cli_output = tmp_path / "cli-output"
    mcp_output = tmp_path / "mcp-output"

    exit_code = cli_main(
        [
            "generate",
            "--manifest",
            str(package_root / "app-definition.yaml"),
            "--output",
            str(cli_output),
        ]
    )
    result = generate_app(str(package_root / "app-definition.yaml"), str(mcp_output))

    assert exit_code == 0
    assert result.success is True
    assert result.errors == []
    assert result.files_written
    assert all(not Path(path).is_absolute() for path in result.files_written)
    assert sorted(_relative_file_paths(mcp_output)) == result.files_written
    assert _relative_file_paths(cli_output) == _relative_file_paths(mcp_output)
    assert _directory_diffs(cli_output, mcp_output) == []


def test_manifest_path_must_resolve_inside_allowed_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))

    with pytest.raises(ValueError, match="manifest_path must resolve inside an allowed root"):
        validate_manifest(str(WORKSPACE_MANIFEST.resolve()))


def test_mcp_tools_fail_closed_when_allowed_roots_unset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(_ALLOWED_ROOTS_ENV, raising=False)
    output_dir = tmp_path / "unexpected-output"

    expected = "EDGEFORGE_MCP_ALLOWED_ROOTS must be set"
    with pytest.raises(ValueError, match=expected):
        validate_manifest(str(WORKSPACE_MANIFEST))
    with pytest.raises(ValueError, match=expected):
        translate_project(str(WORKSPACE_MANIFEST))
    with pytest.raises(ValueError, match=expected):
        generate_app(str(WORKSPACE_MANIFEST), str(output_dir))

    assert not output_dir.exists()


def test_relative_manifest_resolves_under_allowed_root_not_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_root = _copy_fixture_into_allowed_root(tmp_path, WORKSPACE_MANIFEST.parent)
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))

    result = validate_manifest(f"{package_root.name}/app-definition.yaml")

    assert result.valid is True
    assert result.errors == []


def test_relative_file_resolution_uses_configured_root_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_manifest = first_root / "project" / "app-definition.yaml"
    second_manifest = second_root / "project" / "app-definition.yaml"
    first_manifest.parent.mkdir(parents=True)
    second_manifest.parent.mkdir(parents=True)
    first_manifest.write_text("schema_version: '2.0'\napp_name: First\n", encoding="utf-8")
    second_manifest.write_text("schema_version: '2.0'\napp_name: Second\n", encoding="utf-8")
    monkeypatch.setenv(
        _ALLOWED_ROOTS_ENV,
        os.pathsep.join([str(first_root), str(second_root)]),
    )

    resolved = resolve_allowed_file(
        "project/app-definition.yaml",
        purpose="manifest_path",
        mode="required",
    )

    assert resolved == first_manifest.resolve()


def test_relative_traversal_outside_allowed_root_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(allowed_root))

    with pytest.raises(ValueError, match="manifest_path must resolve inside an allowed root"):
        validate_manifest("../outside/app-definition.yaml")


def test_symlink_escape_outside_allowed_root_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
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
    (allowed_root / "linked-outside").symlink_to(outside_root, target_is_directory=True)
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(allowed_root))

    with pytest.raises(ValueError, match="manifest_path must resolve inside an allowed root"):
        validate_manifest("linked-outside/app-definition.yaml")


def test_generate_app_rejects_output_dir_outside_allowed_roots(
    monkeypatch: pytest.MonkeyPatch,
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
    outside_output = tmp_path.parent / "outside-mcp-output"
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))

    with pytest.raises(ValueError, match="output_dir must resolve inside an allowed root"):
        generate_app(str(manifest), str(outside_output))


def test_list_target_profiles_returns_current_profile_metadata() -> None:
    profiles = {profile.name: profile for profile in list_target_profiles()}

    assert {
        "springboot-legacy-compatible",
        "springboot-enterprise-postgres-java17",
        "springboot-standard-enterprise",
    }.issubset(set(profiles))
    assert profiles["springboot-legacy-compatible"].java_version == "17"
    assert profiles["springboot-legacy-compatible"].database == "h2"
    assert profiles["springboot-legacy-compatible"].emit_audit is False
    assert profiles["springboot-enterprise-postgres-java17"].database == "postgresql"
    assert profiles["springboot-enterprise-postgres-java17"].emit_audit is True
    assert profiles["springboot-standard-enterprise"].java_version == "21"


def test_describe_target_profile_excludes_datasource_secrets() -> None:
    profile = describe_target_profile("springboot-standard-enterprise")
    dumped = profile.model_dump()

    assert profile.datasource_driver_class_name == "org.postgresql.Driver"
    assert "datasource_password" not in dumped
    assert "datasource_username" not in dumped
    assert "SPRING_DATASOURCE_PASSWORD" not in str(dumped)


def test_list_archetypes_returns_bounded_engine_archetypes() -> None:
    archetypes = {archetype.name: archetype.description for archetype in list_archetypes()}

    assert set(archetypes) == {"crud", "passthrough-router", "kafka-integration"}


def test_get_manifest_schema_returns_valid_schema_v2() -> None:
    schema = get_manifest_schema()

    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"]["enum"] == ["2.0"]
    assert get_manifest_schema("2.0") == schema


def test_get_manifest_schema_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="Unsupported manifest schema_version"):
        get_manifest_schema("1.0")


def test_mcp_server_registers_only_phase_4_engine_tools() -> None:
    registered: list[str] = []

    class FakeMCP:
        def tool(self):
            def decorator(function):
                registered.append(function.__name__)
                return function

            return decorator

    register_tools(FakeMCP())

    assert registered == [
        "validate_manifest",
        "translate_project",
        "generate_app",
        "list_target_profiles",
        "describe_target_profile",
        "list_archetypes",
        "get_manifest_schema",
    ]


def test_mcp_server_smoke_creates_fastmcp_server_when_available() -> None:
    if importlib.util.find_spec("fastmcp") is None:
        pytest.skip("FastMCP is not installed")

    server = create_mcp_server()

    assert server is not None
    assert callable(getattr(server, "run", None))


def test_mcp_client_lists_all_seven_tools_and_calls_catalogs(monkeypatch) -> None:
    from appbuilder.target_profiles.catalog import TARGET_PROFILES

    # Other generator tests register custom profiles. Test the shipped catalog
    # in a fresh process, including an explicit parent-state pollution control.
    monkeypatch.setitem(
        TARGET_PROFILES, "synthetic-parent-only-profile",
        TARGET_PROFILES["springboot-legacy-compatible"].model_copy(
            update={"name": "synthetic-parent-only-profile"}
        ),
    )
    assert "synthetic-parent-only-profile" in {profile.name for profile in list_target_profiles()}
    script = textwrap.dedent("""
        import asyncio
        from fastmcp import Client
        from appbuilder.mcp_server import create_mcp_server

        async def exercise():
            async with Client(create_mcp_server()) as client:
                assert {tool.name for tool in await client.list_tools()} == {
                    "validate_manifest", "translate_project", "generate_app",
                    "list_target_profiles", "describe_target_profile", "list_archetypes",
                    "get_manifest_schema",
                }
                profiles = await client.call_tool("list_target_profiles", {})
                assert {profile.name for profile in profiles.data} == {
                    "springboot-legacy-compatible", "springboot-enterprise-postgres-java17",
                    "springboot-standard-enterprise",
                }
                detail = await client.call_tool(
                    "describe_target_profile", {"profile_name": "springboot-standard-enterprise"}
                )
                assert detail.data.java_version == "21"
                assert detail.data.spring_boot_version == "4.1.1"

        asyncio.run(exercise())
    """)
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[2],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _tree_snapshot(root: Path) -> list[tuple[str, int, int]]:
    return sorted(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in root.rglob("*")
        if path.is_file()
    )


def _relative_file_paths(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def _directory_diffs(left: Path, right: Path) -> list[str]:
    diffs: list[str] = []
    for relative_path in _relative_file_paths(left):
        if (left / relative_path).read_bytes() != (right / relative_path).read_bytes():
            diffs.append(relative_path)
    return diffs


def _fixed_datetime_class():
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 11, 16, 0, 0, tzinfo=timezone.utc)

    return FixedDateTime
