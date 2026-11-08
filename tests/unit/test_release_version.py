from __future__ import annotations

import subprocess

import pytest

import appbuilder
from scripts.ci import verify_release_version as version_check
from scripts.ci.verify_release_version import check_versions


@pytest.mark.parametrize("repository", ["edgeforge-suite/EdgeForge", "santosh-sh/EdgeForge", "other/EdgeForge", ""])
@pytest.mark.parametrize("tags", [[], ["v4.1.1"]])
def test_no_tag_bootstrap_is_scoped_to_fresh_repository(repository, tags):
    code, message = check_versions("4.1.1", "4.1.1", tags, repository=repository, event="push", ref="refs/heads/main")
    assert code == (0 if tags or repository == "edgeforge-suite/EdgeForge" else 1)
    if not tags and not code:
        assert "no tag/release acceptance" in message


@pytest.mark.parametrize("repository", ["edgeforge-suite/EdgeForge", "santosh-sh/EdgeForge"])
@pytest.mark.parametrize("tags", [[], ["v4.1.1"]])
def test_bootstrap_never_exempts_package_version_agreement(repository, tags):
    assert check_versions("4.1.1", "4.1.0", tags, repository=repository, event="pull_request", ref="refs/pull/1/merge")[0] == 1


@pytest.mark.parametrize("repository", ["edgeforge-suite/EdgeForge", "santosh-sh/EdgeForge"])
def test_tagged_main_mismatch_fails_but_existing_pr_warning_remains(repository):
    args = ("4.1.1", "4.1.1", ["v5.0.0", "v4.1.1"])
    assert check_versions(*args, repository=repository, event="push", ref="refs/heads/main")[0] == 1
    code, message = check_versions(*args, repository=repository, event="pull_request", ref="refs/pull/1/merge")
    assert code == 0
    assert message.startswith("::warning")


@pytest.mark.parametrize("repository,expected", [("edgeforge-suite/EdgeForge", 0), ("santosh-sh/EdgeForge", 1)])
def test_real_untagged_repository_entry_point(tmp_path, monkeypatch, capsys, repository, expected):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{appbuilder.__version__}"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", repository)
    assert version_check.main() == expected
    assert "match latest tag" not in capsys.readouterr().out


def test_git_inspection_error_never_bootstraps(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "4.1.1"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "edgeforge-suite/EdgeForge")
    assert version_check.main() == 1


def test_shallow_history_never_bootstraps(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "4.1.1"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "edgeforge-suite/EdgeForge")
    responses = iter(["", "true\n"])
    monkeypatch.setattr(version_check.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 0, next(responses), ""))
    assert version_check.main() == 1
