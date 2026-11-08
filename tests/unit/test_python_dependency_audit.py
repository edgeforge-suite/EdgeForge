from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import python_dependency_audit as audit


@pytest.fixture
def sample() -> tuple[list[dict[str, str]], dict[str, str], dict[str, object]]:
    installed = [
        {"name": "pip", "version": "24.0"},
        {"name": "A_B", "version": "1.0"},
        {"name": "second", "version": "2.0"},
    ]
    lock = {"a-b": "1.0", "second": "2.0"}
    report = {
        "dependencies": [
            {"name": "a-b", "version": "1.0", "vulns": []},
            {"name": "second", "version": "2.0", "vulns": []},
        ],
        "fixes": [],
    }
    return installed, lock, report


def test_exact_clean_inventory_passes(sample: tuple) -> None:
    assert audit.validate(*sample, 0) == 0


def test_findings_block_and_require_exit_one(sample: tuple) -> None:
    installed, lock, report = copy.deepcopy(sample)
    report["dependencies"][0]["vulns"] = [{"id": "GHSA-example"}]
    assert audit.validate(installed, lock, report, 1) == 1
    with pytest.raises(audit.AuditError, match="exit status"):
        audit.validate(installed, lock, report, 0)


@pytest.mark.parametrize(
    "change",
    [
        lambda x: x[0].pop(),
        lambda x: x[0][1].update(version="9.0"),
        lambda x: x[0].append({"name": "extra", "version": "1.0"}),
        lambda x: x[2]["dependencies"].pop(),
        lambda x: x[2]["dependencies"][0].update(version="9.0"),
        lambda x: x[2]["dependencies"][0].pop("vulns"),
        lambda x: x[2]["dependencies"][0].update(skip_reason="unavailable"),
        lambda x: x[2]["dependencies"].append(copy.deepcopy(x[2]["dependencies"][0])),
        lambda x: x[2].update(skipped=["second"]),
        lambda x: x[2].update(fixes=[{"name": "second"}]),
        lambda x: x[2]["dependencies"][0].update(vulns=[{}]),
    ],
)
def test_incomplete_or_malformed_coverage_fails(sample: tuple, change) -> None:
    changed = copy.deepcopy(sample)
    change(changed)
    with pytest.raises(audit.AuditError):
        audit.validate(*changed, 0)


@pytest.mark.parametrize("lock", ["foo>=1", "foo==1\nfoo==2", "# only comments", "foo==1 --hash=abc"])
def test_lock_rejects_non_exact_or_empty_input(lock: str) -> None:
    with pytest.raises(audit.AuditError):
        audit.parse_lock(lock)


def test_scanner_failure_without_report_is_error(sample: tuple, tmp_path: Path, monkeypatch) -> None:
    installed, lock, _ = sample
    lock_path = tmp_path / "lock.txt"
    lock_path.write_text("A_B==1.0\nsecond==2.0\n", encoding="utf-8")

    def fake_run(argv: list[str], *, timeout: int = 300):
        if argv[-1] == "check":
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "list" in argv:
            return subprocess.CompletedProcess(argv, 0, json.dumps(installed), "")
        return subprocess.CompletedProcess(argv, 2, "", "network failure")

    monkeypatch.setattr(audit, "run", fake_run)
    with pytest.raises(audit.AuditError, match="valid report"):
        audit.check(lock_path, Path("python"), Path("scanner"), None)


@pytest.mark.parametrize("finding_count", [0, 1, 3])
@pytest.mark.parametrize("reverse", [False, True])
def test_command_validates_and_retains_complete_report(
    sample: tuple, tmp_path: Path, monkeypatch, capsys, finding_count: int, reverse: bool
) -> None:
    installed, _, report = copy.deepcopy(sample)
    expected = []
    report["dependencies"][0]["name"] = "A..B"
    if finding_count:
        report["dependencies"][0]["vulns"] = [
            {"id": "GHSA-example", "description": "private advisory body", "aliases": ["private alias"]}
        ]
        expected.append({"package": "a-b", "installed_version": "1.0", "advisory_id": "GHSA-example"})
    if finding_count == 3:
        report["dependencies"][0]["vulns"].append({"id": "CVE-example"})
        report["dependencies"][1]["vulns"] = [{"id": "GHSA-second"}]
        expected.insert(0, {"package": "a-b", "installed_version": "1.0", "advisory_id": "CVE-example"})
        expected.append({"package": "second", "installed_version": "2.0", "advisory_id": "GHSA-second"})
    if reverse:
        report["dependencies"].reverse()
        for dep in report["dependencies"]:
            dep["vulns"].reverse()
    exit_code = int(bool(finding_count))
    lock_path = tmp_path / "lock.txt"
    lock_path.write_text("A_B==1.0\nsecond==2.0\n", encoding="utf-8")
    output = tmp_path / "report.json"

    def fake_run(argv: list[str], *, timeout: int = 300):
        if argv[-1] == "check":
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "list" in argv:
            return subprocess.CompletedProcess(argv, 0, json.dumps(installed), "")
        Path(argv[argv.index("--output") + 1]).write_text(json.dumps(report), encoding="utf-8")
        return subprocess.CompletedProcess(argv, exit_code, "raw scanner output", "raw error /private/host-path")

    monkeypatch.setattr(audit, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "python_dependency_audit.py", "--lock", str(lock_path), "--python", "python",
        "--scanner", "scanner", "--output", str(output),
    ])
    assert audit.main() == exit_code
    assert json.loads(output.read_text(encoding="utf-8")) == report
    captured = capsys.readouterr()
    assert captured.out == json.dumps({
        "packages": 2, "findings": finding_count, "status": "findings" if finding_count else "clean",
    }, sort_keys=True) + "\n"
    assert captured.err == "".join(json.dumps(row, sort_keys=True) + "\n" for row in expected)


@pytest.mark.parametrize(
    "change, scanner_exit",
    [
        (lambda r: r["dependencies"].pop(), 1),
        (lambda r: r["dependencies"][1].update(version="9.0"), 1),
        (lambda r: r["dependencies"][1].pop("vulns"), 1),
        (lambda r: r["dependencies"][1].update(skip_reason="/private/host-path"), 1),
        (lambda r: r["dependencies"][1].update(vulns=[{}]), 1),
        (lambda r: r["dependencies"][1].update(vulns=[{"id": ""}]), 1),
        (lambda r: r["dependencies"][1].update(vulns=[{"id": 123}]), 1),
        (lambda r: r.update(fixes=[{"name": "second"}]), 1),
        (lambda r: r.update(skipped=["second"]), 1),
        (lambda r: None, 0),
        (lambda r: None, 2),
    ],
)
def test_rejected_report_emits_no_finding_diagnostics(
    sample: tuple, tmp_path: Path, monkeypatch, capsys, change, scanner_exit: int
) -> None:
    installed, _, report = copy.deepcopy(sample)
    # A valid finding must not leak before a later report error is detected.
    report["dependencies"][0]["vulns"] = [{"id": "GHSA-example"}]
    change(report)
    lock_path = tmp_path / "lock.txt"
    lock_path.write_text("A_B==1.0\nsecond==2.0\n", encoding="utf-8")
    output = tmp_path / "report.json"

    def fake_run(argv: list[str], *, timeout: int = 300):
        if argv[-1] == "check":
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "list" in argv:
            return subprocess.CompletedProcess(argv, 0, json.dumps(installed), "")
        Path(argv[argv.index("--output") + 1]).write_text(json.dumps(report), encoding="utf-8")
        return subprocess.CompletedProcess(argv, scanner_exit, "raw scanner output", "raw error /private/host-path")

    monkeypatch.setattr(audit, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "python_dependency_audit.py", "--lock", str(lock_path), "--scanner", "scanner",
        "--output", str(output),
    ])
    assert audit.main() == 2
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert set(summary) == {"status", "reason"}
    assert summary["status"] == "error"
    assert captured.err == ""
    assert "GHSA-example" not in captured.out
    assert "raw" not in captured.out
    assert "/private/host-path" not in captured.out
    assert not output.exists()


def test_installation_drift_fails_before_advisory_query(sample: tuple, tmp_path: Path, monkeypatch) -> None:
    installed, _, _ = sample
    installed.pop()
    lock_path = tmp_path / "lock.txt"
    lock_path.write_text("A_B==1.0\nsecond==2.0\n", encoding="utf-8")
    scanner_calls = []

    def fake_run(argv: list[str], *, timeout: int = 300):
        if argv[-1] == "check":
            return subprocess.CompletedProcess(argv, 0, "", "")
        if "list" in argv:
            return subprocess.CompletedProcess(argv, 0, json.dumps(installed), "")
        scanner_calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(audit, "run", fake_run)
    with pytest.raises(audit.AuditError, match="reference lock"):
        audit.check(lock_path, Path("python"), Path("scanner"), None)
    assert not scanner_calls


def test_tool_timeout_fails(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("scanner", 1)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(audit.AuditError, match="unavailable"):
        audit.run(["scanner"])


def test_direct_declarations_and_reference_lock_agree() -> None:
    if sys.version_info < (3, 11):
        pytest.skip("stdlib TOML parser is available on Python 3.11+")
    import tomllib

    root = Path(__file__).resolve().parents[2]
    declared = [
        line.strip() for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert sorted(declared) == sorted(project["dependencies"] + project["optional-dependencies"]["dev"])
    lock = audit.parse_lock((root / "requirements-lock.txt").read_text(encoding="utf-8"))
    assert lock
    for requirement in declared:
        name, version = requirement.split("==", 1)
        assert lock[audit.normalize(name)] == version.split(";", 1)[0].strip()
