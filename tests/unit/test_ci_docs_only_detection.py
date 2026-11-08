from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR = REPO_ROOT / "scripts" / "ci" / "detect-docs-only.sh"
MISSING_SHA = "f" * 40
ZERO_SHA = "0" * 40


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit_file(repo: Path, path: str, content: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "EdgeForge CI")
    _git(repo, "config", "user.email", "ci@example.invalid")
    main_sha = _commit_file(repo, "README.md", "# Test repository\n", "initial")
    _git(repo, "update-ref", "refs/remotes/origin/main", main_sha)
    return repo, main_sha


def _detect(
    repo: Path,
    *,
    event_name: str,
    head_sha: str,
    before_sha: str = "",
    pr_base_sha: str = "",
    pr_head_sha: str = "",
    ref_name: str = "feature",
) -> dict[str, str]:
    output = repo / "github-output"
    env = os.environ.copy()
    env.update(
        {
            "EVENT_NAME": event_name,
            "HEAD_SHA": head_sha,
            "BEFORE_SHA": before_sha,
            "PR_BASE_SHA": pr_base_sha,
            "PR_HEAD_SHA": pr_head_sha,
            "DEFAULT_BRANCH": "main",
            "REF_NAME": ref_name,
            "GITHUB_OUTPUT": str(output),
        }
    )
    subprocess.run(["bash", str(DETECTOR)], cwd=repo, env=env, check=True)
    return dict(
        line.split("=", 1)
        for line in output.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("docs/change.md", "true"),
        ("docs/handover-evidence/python-current/provenance.json", "false"),
        ("appbuilder/change.py", "false"),
    ],
)
def test_normal_push_uses_available_ancestor_range(
    git_repo: tuple[Path, str],
    path: str,
    expected: str,
) -> None:
    repo, main_sha = git_repo
    _git(repo, "switch", "-c", "feature")
    head_sha = _commit_file(repo, path, "change\n", "change")

    result = _detect(
        repo,
        event_name="push",
        before_sha=main_sha,
        head_sha=head_sha,
    )

    assert result == {"docs_only": expected, "comparison_kind": "push"}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("docs/change.md", "true"),
        ("docs/handover-evidence/python-current/sbom.cdx.json", "false"),
        ("appbuilder/change.py", "false"),
    ],
)
def test_pull_request_uses_explicit_base_and_head(
    git_repo: tuple[Path, str],
    path: str,
    expected: str,
) -> None:
    repo, main_sha = git_repo
    _git(repo, "switch", "-c", "feature")
    head_sha = _commit_file(repo, path, "change\n", "change")

    result = _detect(
        repo,
        event_name="pull_request",
        head_sha=head_sha,
        pr_base_sha=main_sha,
        pr_head_sha=head_sha,
    )

    assert result == {"docs_only": expected, "comparison_kind": "pull-request"}


def test_force_push_with_unavailable_before_checks_the_whole_branch(
    git_repo: tuple[Path, str],
) -> None:
    repo, _ = git_repo
    _git(repo, "switch", "-c", "feature")
    _commit_file(repo, "appbuilder/change.py", "code change\n", "code change")
    head_sha = _commit_file(repo, "docs/change.md", "docs change\n", "docs-only tip")

    result = _detect(
        repo,
        event_name="push",
        before_sha=MISSING_SHA,
        head_sha=head_sha,
    )

    assert result == {"docs_only": "false", "comparison_kind": "merge-base"}


def test_non_fast_forward_push_ignores_reachable_old_tip(
    git_repo: tuple[Path, str],
) -> None:
    repo, _ = git_repo
    _git(repo, "switch", "-c", "feature")
    old_tip = _commit_file(repo, "docs/old.md", "old history\n", "old history")
    _git(repo, "switch", "main")
    _git(repo, "switch", "-c", "rewritten")
    _commit_file(repo, "appbuilder/change.py", "code change\n", "code change")
    head_sha = _commit_file(repo, "docs/change.md", "docs change\n", "docs-only tip")

    result = _detect(
        repo,
        event_name="push",
        before_sha=old_tip,
        head_sha=head_sha,
    )

    assert result == {"docs_only": "false", "comparison_kind": "merge-base"}


@pytest.mark.parametrize("before_sha", [MISSING_SHA, ZERO_SHA])
def test_genuinely_docs_only_branch_still_skips(
    git_repo: tuple[Path, str],
    before_sha: str,
) -> None:
    repo, _ = git_repo
    _git(repo, "switch", "-c", "feature")
    head_sha = _commit_file(repo, "docs/change.md", "docs change\n", "docs change")

    result = _detect(
        repo,
        event_name="push",
        before_sha=before_sha,
        head_sha=head_sha,
    )

    assert result == {"docs_only": "true", "comparison_kind": "merge-base"}


def test_unknown_base_fails_safe_by_running_tests(
    git_repo: tuple[Path, str],
) -> None:
    repo, _ = git_repo
    _git(repo, "switch", "-c", "feature")
    head_sha = _commit_file(repo, "docs/change.md", "docs change\n", "docs change")
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")

    result = _detect(
        repo,
        event_name="push",
        before_sha=MISSING_SHA,
        head_sha=head_sha,
    )

    assert result == {"docs_only": "false", "comparison_kind": "unknown"}


def test_unavailable_before_on_default_branch_runs_tests(
    git_repo: tuple[Path, str],
) -> None:
    repo, _ = git_repo
    head_sha = _commit_file(repo, "docs/change.md", "docs change\n", "docs change")

    result = _detect(
        repo,
        event_name="push",
        before_sha=MISSING_SHA,
        head_sha=head_sha,
        ref_name="main",
    )

    assert result == {"docs_only": "false", "comparison_kind": "unknown"}
