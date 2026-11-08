#!/usr/bin/env python3
"""Check package/tag agreement in the Python 3.11 CI job, including bootstrap."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

FRESH_REPOSITORY = "edgeforge-suite/EdgeForge"


def check_versions(
    project_version: str,
    package_version: str,
    tags: list[str],
    *,
    repository: str,
    event: str,
    ref: str,
) -> tuple[int, str]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", project_version):
        return 1, "Package version must be a full MAJOR.MINOR.PATCH value."
    if package_version != project_version:
        return 1, "appbuilder.__version__ does not match pyproject version."
    if not tags:
        if repository == FRESH_REPOSITORY:
            return 0, "First-release bootstrap: package versions agree; no tag/release acceptance established."
        return 1, "No git tags found; cannot verify pyproject version in this repository."
    latest = tags[0]
    if project_version != latest.removeprefix("v"):
        message = f"pyproject/appbuilder version {project_version} does not match latest tag {latest}."
        if event != "push" or ref != "refs/heads/main":
            return 0, f"::warning title=Release version pending tag::{message} Cut the matching tag before or with merge."
        return 1, message
    return 0, f"pyproject and appbuilder.__version__ match latest tag: {latest}"


def main() -> int:
    try:
        import tomllib

        import appbuilder

        data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        result = subprocess.run(
            ["git", "tag", "--sort=-v:refname"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        shallow = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        if shallow.stdout.strip() != "false":
            raise ValueError("complete repository history is required")
        code, message = check_versions(
            data["project"]["version"], appbuilder.__version__, result.stdout.splitlines(),
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            event=os.environ.get("GITHUB_EVENT_NAME", ""),
            ref=os.environ.get("GITHUB_REF", ""),
        )
    except Exception as exc:
        print(f"Version inspection failed: {type(exc).__name__}")
        return 1
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
