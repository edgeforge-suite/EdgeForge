from __future__ import annotations

import copy
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts import verify_suite_pairing as pairing

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_PATH = REPO_ROOT / "docs" / "suite-release-candidate.json"


@dataclass(frozen=True)
class PairingFixture:
    candidate_path: Path
    checkouts: dict[str, Path]
    shas: dict[str, str]


def _git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_DATE": "2026-09-12T12:00:00Z",
            "GIT_COMMITTER_DATE": "2026-09-12T12:00:00Z",
        }
    )
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def _new_repo(root: Path, role: str) -> tuple[Path, str]:
    repo = root / f"{role} checkout"
    repo.mkdir(parents=True)
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Pairing Test")
    _git(repo, "config", "user.email", "pairing@example.invalid")
    _git(
        repo,
        "remote",
        "add",
        "origin",
        f"https://github.com/{pairing.EXPECTED_REPOSITORIES[role]}.git",
    )
    (repo / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    (repo / "tracked.txt").write_text(f"{role} fixture\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "tracked.txt")
    _git(repo, "commit", "--quiet", "-m", f"Create {role} fixture")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, sha


def _candidate_document(shas: dict[str, str] | None = None) -> dict[str, object]:
    document = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    if shas is not None:
        repos = document["repos"]
        assert isinstance(repos, dict)
        for role in pairing.ROLE_ORDER:
            entry = repos[role]
            assert isinstance(entry, dict)
            entry["sha"] = shas[role]
    return document


def _write_candidate(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def suite_fixture(tmp_path: Path) -> PairingFixture:
    root = tmp_path / "suite fixture with spaces"
    checkouts: dict[str, Path] = {}
    shas: dict[str, str] = {}
    for role in pairing.ROLE_ORDER:
        checkouts[role], shas[role] = _new_repo(root, role)
    candidate_path = root / "candidate files" / "candidate.json"
    _write_candidate(candidate_path, _candidate_document(shas))
    return PairingFixture(candidate_path=candidate_path, checkouts=checkouts, shas=shas)


def _cli_args(fixture: PairingFixture) -> list[str]:
    return [
        "--candidate",
        str(fixture.candidate_path),
        "--engine-checkout",
        str(fixture.checkouts["engine"]),
        "--studio-checkout",
        str(fixture.checkouts["studio"]),
        "--ks-checkout",
        str(fixture.checkouts["ks"]),
    ]


def _run_main(
    fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, dict[str, object]]:
    exit_code = pairing.main(_cli_args(fixture))
    output = capsys.readouterr().out
    return exit_code, output, json.loads(output)


def test_committed_candidate_is_exact_pending_three_repo_selection() -> None:
    document = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    candidate = pairing.load_candidate(CANDIDATE_PATH)

    assert set(document) == pairing.TOP_LEVEL_KEYS
    assert document["schema_version"] == "1.0"
    assert document["candidate_id"] == "public-v5-preparation"
    assert document["target_release"] == "v5.0.0"
    assert document["status"] == "candidate"
    assert document["acceptance_status"] == "pending"
    assert document["manifest_schema_version"] == "2.0"
    assert list(candidate.repos) == list(pairing.ROLE_ORDER)
    assert {
        role: {"repository": repo.repository, "sha": repo.sha}
        for role, repo in candidate.repos.items()
    } == document["repos"]


def test_fresh_repository_selection_matches_only_its_own_remotes(suite_fixture, capsys):
    document = _candidate_document(suite_fixture.shas)
    for role, repository in pairing.PUBLIC_REPOSITORIES.items():
        document["repos"][role]["repository"] = repository
    _write_candidate(suite_fixture.candidate_path, document)
    assert _run_main(suite_fixture, capsys)[0] == 1
    for role, repository in pairing.PUBLIC_REPOSITORIES.items():
        _git(suite_fixture.checkouts[role], "remote", "set-url", "origin", f"git@github.com:{repository}.git")
    assert _run_main(suite_fixture, capsys)[0] == 0
    (suite_fixture.checkouts["engine"] / "tracked.txt").write_text("changed")
    assert _run_main(suite_fixture, capsys)[0] == 1


@pytest.mark.parametrize("roles", [("engine",), ("studio", "ks")])
def test_mixed_archive_and_fresh_selections_are_rejected(roles):
    document = _candidate_document()
    for role in roles:
        document["repos"][role]["repository"] = pairing.PUBLIC_REPOSITORIES[role]
    with pytest.raises(pairing.CandidateValidationError, match="one complete"):
        pairing.validate_candidate(document)


@pytest.mark.parametrize(
    "case",
    [
        "missing-top-level",
        "extra-top-level",
        "wrong-type",
        "missing-role",
        "extra-role",
        "missing-repo-field",
        "extra-repo-field",
        "wrong-repository",
        "floating-ref",
        "uppercase-sha",
    ],
)
def test_candidate_validation_rejects_schema_drift(case: str) -> None:
    document = copy.deepcopy(_candidate_document())
    repos = document["repos"]
    assert isinstance(repos, dict)
    engine = repos["engine"]
    assert isinstance(engine, dict)

    if case == "missing-top-level":
        document.pop("status")
    elif case == "extra-top-level":
        document["evidence"] = "passed"
    elif case == "wrong-type":
        document["acceptance_status"] = False
    elif case == "missing-role":
        repos.pop("ks")
    elif case == "extra-role":
        repos["testbench"] = copy.deepcopy(engine)
    elif case == "missing-repo-field":
        engine.pop("repository")
    elif case == "extra-repo-field":
        engine["branch"] = "main"
    elif case == "wrong-repository":
        engine["repository"] = "santosh-sh/NotEdgeForge"
    elif case == "floating-ref":
        engine["sha"] = "main"
    elif case == "uppercase-sha":
        engine["sha"] = str(engine["sha"]).upper()

    with pytest.raises(pairing.CandidateValidationError):
        pairing.validate_candidate(document)


def test_candidate_validation_rejects_malformed_and_duplicate_json(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":"1.0","schema_version":"1.0"}\n',
        encoding="utf-8",
    )

    with pytest.raises(pairing.CandidateValidationError, match="malformed"):
        pairing.load_candidate(malformed)
    with pytest.raises(pairing.CandidateValidationError, match="duplicate key"):
        pairing.load_candidate(duplicate)


def test_invalid_candidate_is_rejected_before_git_inspection(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _candidate_document(suite_fixture.shas)
    document["status"] = "accepted"
    _write_candidate(suite_fixture.candidate_path, document)

    def fail_if_called(*_args: object, **_kwargs: object) -> pairing.GitResult:
        raise AssertionError("Git must not run before descriptor validation")

    monkeypatch.setattr(pairing, "_run_git", fail_if_called)

    exit_code = pairing.main(_cli_args(suite_fixture))
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert report["result"] == "pins-mismatch"
    assert report["verification_status"] == "error"
    assert report["error"]["code"] == "invalid-candidate"
    assert report["repos"] == []


@pytest.mark.parametrize(
    "flag",
    ["--engine-checkout", "--studio-checkout", "--ks-checkout"],
)
def test_cli_requires_every_checkout(
    flag: str,
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = _cli_args(suite_fixture)
    index = arguments.index(flag)
    del arguments[index : index + 2]

    exit_code = pairing.main(arguments)
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert report["error"]["code"] == "invalid-arguments"


def test_matching_clean_checkouts_support_spaces_and_detached_head(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _git(
        suite_fixture.checkouts["studio"],
        "checkout",
        "--quiet",
        "--detach",
        suite_fixture.shas["studio"],
    )

    exit_code, output, report = _run_main(suite_fixture, capsys)

    assert exit_code == 0
    assert report["result"] == "pins-match"
    assert report["release_acceptance_established"] is False
    assert report["statement"] == pairing.RELEASE_BOUNDARY
    repos = report["repos"]
    assert [entry["role"] for entry in repos] == list(pairing.ROLE_ORDER)
    assert all(entry["result"] == "match" for entry in repos)
    assert all(entry["actual_sha"] == suite_fixture.shas[entry["role"]] for entry in repos)
    assert all(str(path.resolve()) not in output for path in suite_fixture.checkouts.values())


@pytest.mark.parametrize("role", pairing.ROLE_ORDER)
def test_each_role_head_mismatch_fails_independently(
    role: str,
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = suite_fixture.checkouts[role]
    (repo / "tracked.txt").write_text(f"{role} second commit\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "--quiet", "-m", "Move selected head")

    exit_code, _, report = _run_main(suite_fixture, capsys)
    role_result = next(item for item in report["repos"] if item["role"] == role)

    assert exit_code == 1
    assert report["result"] == "pins-mismatch"
    assert role_result["reason"] == "head-mismatch"


@pytest.mark.parametrize("role", pairing.ROLE_ORDER)
def test_each_role_tracked_change_is_dirty(
    role: str,
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (suite_fixture.checkouts[role] / "tracked.txt").write_text("dirty\n", encoding="utf-8")

    exit_code, _, report = _run_main(suite_fixture, capsys)
    role_result = next(item for item in report["repos"] if item["role"] == role)

    assert exit_code == 1
    assert role_result["clean"] is False
    assert role_result["reason"] == "dirty-worktree"


@pytest.mark.parametrize("role", pairing.ROLE_ORDER)
def test_each_role_nonignored_untracked_file_is_dirty(
    role: str,
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (suite_fixture.checkouts[role] / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    exit_code, _, report = _run_main(suite_fixture, capsys)
    role_result = next(item for item in report["repos"] if item["role"] == role)

    assert exit_code == 1
    assert role_result["clean"] is False
    assert role_result["reason"] == "dirty-worktree"


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_hidden_index_state_cannot_mask_a_tracked_change(
    flag: str,
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = suite_fixture.checkouts["engine"]
    _git(repo, "update-index", flag, "tracked.txt")
    (repo / "tracked.txt").write_text("hidden change\n", encoding="utf-8")
    assert _git(repo, "status", "--porcelain=v1").stdout == ""

    exit_code, _, report = _run_main(suite_fixture, capsys)
    engine = report["repos"][0]

    assert exit_code == 1
    assert report["result"] == "pins-mismatch"
    assert engine["clean"] is False
    assert engine["reason"] == "hidden-index-state"


def test_ignored_untracked_file_does_not_make_checkout_dirty(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (suite_fixture.checkouts["ks"] / "ignored.log").write_text("ignored\n", encoding="utf-8")

    exit_code, _, report = _run_main(suite_fixture, capsys)

    assert exit_code == 0
    assert report["result"] == "pins-match"


@pytest.mark.parametrize("case", ["subdirectory", "non-repository", "missing"])
def test_invalid_checkout_location_fails_without_parent_repo_fallback(
    case: str,
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    checkouts = dict(suite_fixture.checkouts)
    if case == "subdirectory":
        invalid = checkouts["engine"] / "nested"
        invalid.mkdir()
        expected_reason = "not-worktree-root"
    elif case == "non-repository":
        invalid = tmp_path / "plain directory"
        invalid.mkdir()
        expected_reason = "not-git-worktree"
    else:
        invalid = tmp_path / "missing directory"
        expected_reason = "checkout-unavailable"
    checkouts["engine"] = invalid
    fixture = PairingFixture(suite_fixture.candidate_path, checkouts, suite_fixture.shas)

    exit_code, output, report = _run_main(fixture, capsys)
    engine = report["repos"][0]

    assert exit_code == 1
    assert engine["reason"] == expected_reason
    assert str(invalid) not in output


def test_repository_identity_mismatch_fails_without_echoing_remote(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "credential-that-must-not-appear"
    repo = suite_fixture.checkouts["engine"]
    _git(
        repo,
        "remote",
        "set-url",
        "origin",
        f"https://{secret}@github.com/santosh-sh/Unexpected.git",
    )

    exit_code, output, report = _run_main(suite_fixture, capsys)

    assert exit_code == 1
    assert report["repos"][0]["reason"] == "repository-mismatch"
    assert secret not in output


def test_malformed_remote_is_a_sanitized_repository_mismatch(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    malformed_remote = "https://[broken"
    _git(
        suite_fixture.checkouts["engine"],
        "remote",
        "set-url",
        "origin",
        malformed_remote,
    )

    exit_code, output, report = _run_main(suite_fixture, capsys)

    assert exit_code == 1
    assert report["result"] == "pins-mismatch"
    assert report["repos"][0]["reason"] == "repository-mismatch"
    assert malformed_remote not in output


def test_replacement_object_cannot_substitute_for_selected_commit(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = suite_fixture.checkouts["engine"]
    selected_sha = suite_fixture.shas["engine"]
    (repo / "tracked.txt").write_text("replacement tree\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "--quiet", "-m", "Create replacement tree")
    replacement_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "HEAD", selected_sha)
    _git(repo, "replace", selected_sha, replacement_sha)

    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == selected_sha
    assert _git(repo, "status", "--porcelain=v1").stdout == ""

    exit_code, _, report = _run_main(suite_fixture, capsys)
    engine = report["repos"][0]

    assert exit_code == 1
    assert report["result"] == "pins-mismatch"
    assert engine["actual_sha"] == selected_sha
    assert engine["clean"] is False
    assert engine["reason"] == "dirty-worktree"


def test_dirty_checkout_passes_again_after_input_is_restored(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tracked = suite_fixture.checkouts["engine"] / "tracked.txt"
    original = tracked.read_bytes()
    tracked.write_text("temporarily dirty\n", encoding="utf-8")

    first_exit, _, first_report = _run_main(suite_fixture, capsys)
    tracked.write_bytes(original)
    second_exit, _, second_report = _run_main(suite_fixture, capsys)

    assert first_exit == 1
    assert first_report["result"] == "pins-mismatch"
    assert second_exit == 0
    assert second_report["result"] == "pins-match"


def test_repeated_verification_is_byte_stable_and_read_only(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = {
        role: (
            _git(repo, "rev-parse", "HEAD").stdout,
            _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout,
            (repo / "tracked.txt").read_bytes(),
            (repo / ".git" / "index").read_bytes(),
        )
        for role, repo in suite_fixture.checkouts.items()
    }

    first_exit, first_output, _ = _run_main(suite_fixture, capsys)
    second_exit, second_output, _ = _run_main(suite_fixture, capsys)

    after = {
        role: (
            _git(repo, "rev-parse", "HEAD").stdout,
            _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout,
            (repo / "tracked.txt").read_bytes(),
            (repo / ".git" / "index").read_bytes(),
        )
        for role, repo in suite_fixture.checkouts.items()
    }
    assert first_exit == second_exit == 0
    assert first_output == second_output
    assert before == after
    assert str(suite_fixture.candidate_path.parent) not in first_output


def test_inherited_git_path_overrides_cannot_redirect_inspection(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    decoy, _ = _new_repo(tmp_path / "decoy root", "engine")
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy))
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / "alternate-index"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.bare")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")

    exit_code, _, report = _run_main(suite_fixture, capsys)

    assert exit_code == 0
    assert report["result"] == "pins-match"


def test_git_timeout_is_tooling_error_and_never_passes(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=pairing.GIT_TIMEOUT_SECONDS)

    monkeypatch.setattr(pairing.subprocess, "run", time_out)

    exit_code, output, report = _run_main(suite_fixture, capsys)

    assert exit_code == 2
    assert report["result"] == "pins-mismatch"
    assert report["verification_status"] == "error"
    assert all(item["reason"] == "git-timeout" for item in report["repos"])
    assert all(str(path) not in output for path in suite_fixture.checkouts.values())


def test_missing_git_is_tooling_error_and_never_passes(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_git(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    monkeypatch.setattr(pairing.subprocess, "run", missing_git)

    exit_code, _, report = _run_main(suite_fixture, capsys)

    assert exit_code == 2
    assert report["result"] == "pins-mismatch"
    assert report["verification_status"] == "error"
    assert all(item["reason"] == "git-unavailable" for item in report["repos"])


def test_failed_status_inspection_is_tooling_error(
    suite_fixture: PairingFixture,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_run = pairing.subprocess.run

    def fail_status(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "status" in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="private failure")
        return real_run(command, **kwargs)

    monkeypatch.setattr(pairing.subprocess, "run", fail_status)

    exit_code, output, report = _run_main(suite_fixture, capsys)

    assert exit_code == 2
    assert report["result"] == "pins-mismatch"
    assert report["verification_status"] == "error"
    assert all(item["reason"] == "git-inspection-failed" for item in report["repos"])
    assert "private failure" not in output
