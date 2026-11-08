from __future__ import annotations

import io
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from appbuilder.cli import main
from appbuilder.core.path_safety import ALLOWED_ROOTS_ENV, SHARED_MODE_ENV
from appbuilder.generation.change_plan import build_change_plan
from appbuilder.generation.engine import generate_application
from appbuilder.metadata import build_metadata_project

FIXTURE_ROOT = Path("scripts/smoke/fixtures/engine-l1-l3")


def test_apply_shared_mode_without_allowed_roots_fails_closed_and_writes_nothing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(SHARED_MODE_ENV, "1")
    monkeypatch.delenv(ALLOWED_ROOTS_ENV, raising=False)
    package_dir = tmp_path / "package"
    before = _file_snapshot(tmp_path)

    exit_code, _stdout, stderr = _run_cli(
        [
            "apply",
            "--manifest",
            str(FIXTURE_ROOT / "additive/app-definition.yaml"),
            "--package",
            str(package_dir),
            "--approved-plan-hash",
            "irrelevant",
        ]
    )

    assert exit_code == 1
    assert "EDGEFORGE_MCP_ALLOWED_ROOTS must be set" in stderr
    assert _file_snapshot(tmp_path) == before
    assert not package_dir.exists()


def test_apply_rejects_manifest_paths_outside_allowed_root_without_mutating(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = _prepare_apply_isolation_layout(tmp_path)
    monkeypatch.setenv(SHARED_MODE_ENV, "1")
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, layout.allowed_root.as_posix())

    cases = [
        (
            "absolute out-of-root manifest",
            layout.outside_additive_manifest.as_posix(),
            layout.outside_additive_manifest,
        ),
        (
            "traversal manifest",
            "../outside/additive/app-definition.yaml",
            layout.outside_additive_manifest,
        ),
        (
            "symlink manifest",
            "linked-outside/additive/app-definition.yaml",
            layout.outside_additive_manifest,
        ),
        (
            "sibling-session manifest",
            layout.sibling_additive_manifest.as_posix(),
            layout.sibling_additive_manifest,
        ),
    ]

    for label, manifest_arg, plan_manifest in cases:
        plan = _plan_for(plan_manifest, layout.in_root_package)
        before = _file_snapshot(tmp_path)

        exit_code, _stdout, stderr = _run_cli(
            [
                "apply",
                "--manifest",
                manifest_arg,
                "--package",
                layout.in_root_package.as_posix(),
                "--approved-plan-hash",
                plan["plan_hash"],
                "--generation-run-id",
                f"apply-isolation-{label}",
            ]
        )

        assert exit_code == 1, label
        assert "manifest_path must resolve inside an allowed root" in stderr
        assert _file_snapshot(tmp_path) == before


def test_apply_rejects_package_paths_outside_allowed_root_without_mutating(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = _prepare_apply_isolation_layout(tmp_path)
    monkeypatch.setenv(SHARED_MODE_ENV, "1")
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, layout.allowed_root.as_posix())

    cases = [
        ("absolute out-of-root package", layout.outside_package.as_posix(), layout.outside_package),
        ("traversal package", "../outside/package", layout.outside_package),
        ("symlink package", "linked-outside/package", layout.outside_package),
        ("sibling-session package", layout.sibling_package.as_posix(), layout.sibling_package),
    ]

    for label, package_arg, plan_package in cases:
        plan = _plan_for(layout.in_root_additive_manifest, plan_package)
        before = _file_snapshot(tmp_path)

        exit_code, _stdout, stderr = _run_cli(
            [
                "apply",
                "--manifest",
                layout.in_root_additive_manifest.as_posix(),
                "--package",
                package_arg,
                "--approved-plan-hash",
                plan["plan_hash"],
                "--generation-run-id",
                f"apply-isolation-{label}",
            ]
        )

        assert exit_code == 1, label
        assert "package must resolve inside an allowed root" in stderr
        assert _file_snapshot(tmp_path) == before


def test_apply_inside_allowed_root_applies_and_writes_only_under_package(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = _prepare_apply_isolation_layout(tmp_path)
    monkeypatch.setenv(SHARED_MODE_ENV, "1")
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, layout.allowed_root.as_posix())
    plan = _plan_for(layout.in_root_additive_manifest, layout.in_root_package)
    before = _file_snapshot(tmp_path)

    exit_code, stdout, stderr = _run_cli(
        [
            "apply",
            "--manifest",
            layout.in_root_additive_manifest.as_posix(),
            "--package",
            layout.in_root_package.as_posix(),
            "--approved-plan-hash",
            plan["plan_hash"],
            "--generation-run-id",
            "apply-isolation-positive",
            "--validate-schema",
        ]
    )

    assert exit_code == 0, stderr
    assert "Applied Change Plan:" in stdout
    assert (
        layout.in_root_package
        / "src/main/resources/db/migration/V2__alter_widget_add_category.sql"
    ).is_file()
    touched = _touched_paths(before, _file_snapshot(tmp_path))
    assert touched
    assert all(_is_relative_to(path, layout.in_root_package) for path in touched)


class _ApplyIsolationLayout:
    def __init__(self, *, root: Path) -> None:
        self.allowed_root = root / "session-a"
        self.sibling_root = root / "session-b"
        self.outside_root = root / "outside"
        for path in (self.allowed_root, self.sibling_root, self.outside_root):
            path.mkdir(parents=True, exist_ok=True)

        self.in_root_initial_manifest = self.allowed_root / "initial/app-definition.yaml"
        self.in_root_additive_manifest = self.allowed_root / "additive/app-definition.yaml"
        self.outside_additive_manifest = self.outside_root / "additive/app-definition.yaml"
        self.sibling_additive_manifest = self.sibling_root / "additive/app-definition.yaml"

        _copy_fixture("initial", self.allowed_root / "initial")
        _copy_fixture("additive", self.allowed_root / "additive")
        _copy_fixture("additive", self.outside_root / "additive")
        _copy_fixture("additive", self.sibling_root / "additive")
        (self.allowed_root / "linked-outside").symlink_to(
            self.outside_root,
            target_is_directory=True,
        )

        self.in_root_package = self.allowed_root / "package"
        self.outside_package = self.outside_root / "package"
        self.sibling_package = self.sibling_root / "package"
        for package in (self.in_root_package, self.outside_package, self.sibling_package):
            _generate_initial_package(self.in_root_initial_manifest, package)


def _prepare_apply_isolation_layout(tmp_path: Path) -> _ApplyIsolationLayout:
    return _ApplyIsolationLayout(root=tmp_path)


def _copy_fixture(name: str, target: Path) -> None:
    shutil.copytree(FIXTURE_ROOT / name, target)


def _generate_initial_package(manifest: Path, package_dir: Path) -> None:
    generate_application(
        build_metadata_project(manifest),
        package_dir,
        source_manifest=str(manifest),
        generation_run_id="apply-isolation-baseline",
    )


def _plan_for(manifest: Path, package_dir: Path) -> dict:
    return build_change_plan(
        metadata=build_metadata_project(manifest),
        package_dir=package_dir,
    )


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _file_snapshot(root: Path) -> dict[Path, bytes]:
    if not root.exists():
        return {}
    return {
        path.resolve(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _touched_paths(before: dict[Path, bytes], after: dict[Path, bytes]) -> set[Path]:
    return {
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
