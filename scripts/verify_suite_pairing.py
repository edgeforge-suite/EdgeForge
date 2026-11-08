#!/usr/bin/env python3
"""Verify clean Engine, Studio, and KS checkouts against a candidate pin set."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROLE_ORDER = ("engine", "studio", "ks")
EXPECTED_REPOSITORIES = {
    "engine": "santosh-sh/EdgeForge",
    "studio": "santosh-sh/EdgeForgeStudio",
    "ks": "santosh-sh/EdgeForgeKnowledgeServer",
}
PUBLIC_REPOSITORIES = {
    role: repository.replace("santosh-sh/", "edgeforge-suite/", 1)
    for role, repository in EXPECTED_REPOSITORIES.items()
}
TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "target_release",
        "status",
        "acceptance_status",
        "manifest_schema_version",
        "repos",
    }
)
REPO_KEYS = frozenset({"repository", "sha"})
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CANDIDATE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TARGET_RELEASE_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
FORMAT_VERSION_RE = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
GIT_TIMEOUT_SECONDS = 10
RELEASE_BOUNDARY = (
    "Matching clean Git revisions only; neither integration, security, nor release acceptance "
    "is established."
)


class CandidateValidationError(ValueError):
    """Raised when the candidate descriptor does not match the v1 contract."""


class CliInputError(ValueError):
    """Raised when required command-line input is invalid."""


class GitToolError(RuntimeError):
    """Raised when Git inspection cannot complete reliably."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CandidateRepo:
    repository: str
    sha: str


@dataclass(frozen=True)
class Candidate:
    schema_version: str
    candidate_id: str
    target_release: str
    status: str
    acceptance_status: str
    manifest_schema_version: str
    repos: dict[str, CandidateRepo]


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str


GitRunner = Callable[[Path, Sequence[str]], GitResult]


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliInputError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        description=(
            "Verify clean Engine, Studio, and KS Git worktrees against an explicit "
            "Suite release-candidate descriptor."
        )
    )
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--engine-checkout", required=True, type=Path)
    parser.add_argument("--studio-checkout", required=True, type=Path)
    parser.add_argument("--ks-checkout", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except CliInputError:
        print(_serialize_report(_error_report("invalid-arguments")), end="")
        return 2

    try:
        candidate = load_candidate(args.candidate)
    except CandidateValidationError as exc:
        print(
            _serialize_report(_error_report("invalid-candidate", str(exc))),
            end="",
        )
        return 2

    checkouts = {
        "engine": args.engine_checkout,
        "studio": args.studio_checkout,
        "ks": args.ks_checkout,
    }
    report, exit_code = verify_candidate(candidate, checkouts)
    print(_serialize_report(report), end="")
    return exit_code


def load_candidate(path: Path) -> Candidate:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CandidateValidationError("candidate descriptor is unavailable") from exc

    try:
        document = json.loads(raw, object_pairs_hook=_object_without_duplicates)
    except CandidateValidationError:
        raise
    except json.JSONDecodeError as exc:
        raise CandidateValidationError("candidate descriptor is malformed JSON") from exc

    return validate_candidate(document)


def validate_candidate(document: Any) -> Candidate:
    if not isinstance(document, dict):
        raise CandidateValidationError("candidate descriptor must be a JSON object")
    _require_exact_keys(document, TOP_LEVEL_KEYS, "candidate descriptor")

    _require_exact_value(document, "schema_version", "1.0")
    candidate_id = _require_string(document, "candidate_id")
    if not CANDIDATE_ID_RE.fullmatch(candidate_id):
        raise CandidateValidationError("candidate_id must be a stable lowercase identifier")
    target_release = _require_string(document, "target_release")
    if not TARGET_RELEASE_RE.fullmatch(target_release):
        raise CandidateValidationError("target_release must be a full vMAJOR.MINOR.PATCH value")
    _require_exact_value(document, "status", "candidate")
    _require_exact_value(document, "acceptance_status", "pending")
    manifest_schema_version = _require_string(document, "manifest_schema_version")
    if not FORMAT_VERSION_RE.fullmatch(manifest_schema_version):
        raise CandidateValidationError("manifest_schema_version must be a MAJOR.MINOR value")

    repos_document = document["repos"]
    if not isinstance(repos_document, dict):
        raise CandidateValidationError("repos must be a JSON object")
    _require_exact_keys(repos_document, frozenset(ROLE_ORDER), "repos")

    repos: dict[str, CandidateRepo] = {}
    for role in ROLE_ORDER:
        repo_document = repos_document[role]
        if not isinstance(repo_document, dict):
            raise CandidateValidationError(f"repos.{role} must be a JSON object")
        _require_exact_keys(repo_document, REPO_KEYS, f"repos.{role}")
        repository = _require_string(repo_document, "repository", prefix=f"repos.{role}.")
        if repository not in (EXPECTED_REPOSITORIES[role], PUBLIC_REPOSITORIES[role]):
            raise CandidateValidationError(f"repos.{role}.repository is not the expected repository")
        sha = _require_string(repo_document, "sha", prefix=f"repos.{role}.")
        if not FULL_SHA_RE.fullmatch(sha):
            raise CandidateValidationError(f"repos.{role}.sha must be a full lowercase commit SHA")
        repos[role] = CandidateRepo(repository=repository, sha=sha)

    identities = {role: repo.repository for role, repo in repos.items()}
    if identities not in (EXPECTED_REPOSITORIES, PUBLIC_REPOSITORIES):
        raise CandidateValidationError("repos must select one complete archive or fresh-repository set")

    return Candidate(
        schema_version=document["schema_version"],
        candidate_id=candidate_id,
        target_release=target_release,
        status=document["status"],
        acceptance_status=document["acceptance_status"],
        manifest_schema_version=manifest_schema_version,
        repos=repos,
    )


def verify_candidate(
    candidate: Candidate,
    checkouts: dict[str, Path],
    *,
    git_runner: GitRunner | None = None,
) -> tuple[dict[str, Any], int]:
    runner = git_runner or _run_git
    repo_results: list[dict[str, Any]] = []
    tooling_failed = False

    for role in ROLE_ORDER:
        expected = candidate.repos[role]
        checkout = checkouts.get(role)
        if checkout is None:
            repo_results.append(_empty_role_result(role, expected, "checkout-not-supplied"))
            continue
        try:
            role_result = _verify_checkout(role, expected, checkout, runner)
        except GitToolError as exc:
            tooling_failed = True
            role_result = _empty_role_result(role, expected, exc.code, result="error")
        repo_results.append(role_result)

    if tooling_failed:
        result = "pins-mismatch"
        verification_status = "error"
        exit_code = 2
    elif all(item["result"] == "match" for item in repo_results):
        result = "pins-match"
        verification_status = "completed"
        exit_code = 0
    else:
        result = "pins-mismatch"
        verification_status = "completed"
        exit_code = 1

    return {
        "schema_version": "1.0",
        "candidate": _candidate_identity(candidate),
        "result": result,
        "verification_status": verification_status,
        "release_acceptance_established": False,
        "statement": RELEASE_BOUNDARY,
        "repos": repo_results,
    }, exit_code


def _verify_checkout(
    role: str,
    expected: CandidateRepo,
    checkout: Path,
    git_runner: GitRunner,
) -> dict[str, Any]:
    supplied = checkout.expanduser()
    if not supplied.is_dir():
        return _empty_role_result(role, expected, "checkout-unavailable")
    resolved = supplied.resolve()

    top_level_result = git_runner(resolved, ("rev-parse", "--show-toplevel"))
    if top_level_result.returncode != 0:
        return _empty_role_result(role, expected, "not-git-worktree")
    try:
        top_level = Path(top_level_result.stdout.strip()).resolve(strict=True)
    except (OSError, RuntimeError):
        raise GitToolError("git-inspection-failed") from None
    if top_level != resolved:
        return _empty_role_result(role, expected, "not-worktree-root")

    remote_result = git_runner(resolved, ("remote", "get-url", "origin"))
    if remote_result.returncode != 0:
        return _empty_role_result(
            role,
            expected,
            "repository-mismatch",
            worktree_root=True,
        )
    repository_match = _repository_from_remote(remote_result.stdout.strip()) == expected.repository

    head_result = git_runner(resolved, ("rev-parse", "--verify", "HEAD^{commit}"))
    if head_result.returncode != 0:
        return _empty_role_result(
            role,
            expected,
            "head-unavailable",
            worktree_root=True,
            repository_match=repository_match,
        )
    actual_sha = head_result.stdout.strip()
    if not FULL_SHA_RE.fullmatch(actual_sha):
        raise GitToolError("git-inspection-failed")

    index_result = git_runner(resolved, ("ls-files", "-v", "-z"))
    if index_result.returncode != 0:
        raise GitToolError("git-inspection-failed")
    hidden_index_state = _has_hidden_index_state(index_result.stdout)

    status_result = git_runner(
        resolved,
        ("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"),
    )
    if status_result.returncode != 0:
        raise GitToolError("git-inspection-failed")
    clean = not status_result.stdout and not hidden_index_state

    reasons: list[str] = []
    if not repository_match:
        reasons.append("repository-mismatch")
    if actual_sha != expected.sha:
        reasons.append("head-mismatch")
    if hidden_index_state:
        reasons.append("hidden-index-state")
    elif status_result.stdout:
        reasons.append("dirty-worktree")
    matches = not reasons
    return {
        "role": role,
        "repository": expected.repository,
        "expected_sha": expected.sha,
        "actual_sha": actual_sha,
        "worktree_root": True,
        "repository_match": repository_match,
        "clean": clean,
        "result": "match" if matches else "mismatch",
        "reason": "matched" if matches else ",".join(reasons),
    }


def _run_git(checkout: Path, arguments: Sequence[str]) -> GitResult:
    command = [
        "git",
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "maintenance.auto=false",
        *arguments,
    ]
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    try:
        completed = subprocess.run(
            command,
            cwd=checkout,
            env=env,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise GitToolError("git-unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitToolError("git-timeout") from exc
    except OSError as exc:
        raise GitToolError("git-inspection-failed") from exc
    return GitResult(returncode=completed.returncode, stdout=completed.stdout)


def _repository_from_remote(remote: str) -> str | None:
    if not remote or any(character in remote for character in "\r\n"):
        return None

    host: str | None
    path: str
    if remote.startswith("git@github.com:"):
        host = "github.com"
        path = remote.removeprefix("git@github.com:")
    else:
        try:
            parsed = urlparse(remote)
            host = parsed.hostname
        except ValueError:
            return None
        path = parsed.path.lstrip("/")
    if host != "github.com":
        return None
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return "/".join(parts)


def _has_hidden_index_state(output: str) -> bool:
    for entry in output.split("\0"):
        if not entry:
            continue
        if len(entry) < 3 or entry[1] != " ":
            raise GitToolError("git-inspection-failed")
        tag = entry[0]
        if tag == "S" or tag.islower():
            return True
    return False


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateValidationError("candidate descriptor contains a duplicate key")
        result[key] = value
    return result


def _require_exact_keys(document: dict[str, Any], expected: frozenset[str], name: str) -> None:
    actual = frozenset(document)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    details: list[str] = []
    if missing:
        details.append("missing " + ", ".join(missing))
    if actual - expected:
        details.append("contains unexpected fields")
    raise CandidateValidationError(f"{name} has invalid fields: {'; '.join(details)}")


def _require_string(document: dict[str, Any], key: str, *, prefix: str = "") -> str:
    value = document[key]
    if not isinstance(value, str) or not value:
        raise CandidateValidationError(f"{prefix}{key} must be a non-empty string")
    return value


def _require_exact_value(document: dict[str, Any], key: str, expected: str) -> None:
    value = _require_string(document, key)
    if value != expected:
        raise CandidateValidationError(f"{key} must be '{expected}'")


def _candidate_identity(candidate: Candidate) -> dict[str, str]:
    return {
        "candidate_id": candidate.candidate_id,
        "target_release": candidate.target_release,
        "status": candidate.status,
        "acceptance_status": candidate.acceptance_status,
        "manifest_schema_version": candidate.manifest_schema_version,
    }


def _empty_role_result(
    role: str,
    expected: CandidateRepo,
    reason: str,
    *,
    result: str = "mismatch",
    worktree_root: bool = False,
    repository_match: bool = False,
) -> dict[str, Any]:
    return {
        "role": role,
        "repository": expected.repository,
        "expected_sha": expected.sha,
        "actual_sha": None,
        "worktree_root": worktree_root,
        "repository_match": repository_match,
        "clean": None,
        "result": result,
        "reason": reason,
    }


def _error_report(code: str, detail: str | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "candidate": None,
        "result": "pins-mismatch",
        "verification_status": "error",
        "release_acceptance_established": False,
        "statement": RELEASE_BOUNDARY,
        "repos": [],
        "error": {"code": code},
    }
    if detail:
        report["error"]["detail"] = detail
    return report


def _serialize_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=True) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
