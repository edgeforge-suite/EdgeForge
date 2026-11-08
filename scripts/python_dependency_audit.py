#!/usr/bin/env python3
"""Fail-closed audit of the Engine reference Python dependency closure."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BOOTSTRAP = {"pip", "setuptools", "wheel"}
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9._+!-]*)$")


class AuditError(Exception):
    pass


def normalize(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise AuditError("invalid package name")
    return re.sub(r"[-_.]+", "-", name).lower()


def inventory(rows: object, *, report: bool = False) -> dict[str, str]:
    if not isinstance(rows, list) or not rows:
        raise AuditError("empty or malformed package inventory")
    packages: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise AuditError("malformed package inventory entry")
        name, version = row.get("name"), row.get("version")
        if not isinstance(version, str) or not version or not isinstance(name, str):
            raise AuditError("malformed package identity")
        key = normalize(name)
        if key in packages:
            raise AuditError("duplicate package identity")
        if report:
            if set(row) != {"name", "version", "vulns"} or not isinstance(row["vulns"], list):
                raise AuditError("missing or skipped vulnerability results")
        packages[key] = version
    return packages


def parse_lock(contents: str) -> dict[str, str]:
    rows = []
    for line in contents.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if not match:
            raise AuditError("lock contains a non-exact requirement")
        rows.append({"name": match.group(1), "version": match.group(2)})
    return inventory(rows)


def validate(installed: object, lock: dict[str, str], report: object, exit_code: int) -> int:
    installed_map = inventory(installed)
    installed_map = {k: v for k, v in installed_map.items() if k not in BOOTSTRAP}
    if installed_map != lock:
        raise AuditError("installed packages do not match the reference lock")
    if not isinstance(report, dict) or set(report) != {"dependencies", "fixes"}:
        raise AuditError("malformed or incomplete scanner report")
    report_map = inventory(report["dependencies"], report=True)
    if report_map != lock:
        raise AuditError("scanner coverage or versions do not match the reference lock")
    if report["fixes"] != []:
        raise AuditError("unexpected scanner remediation or malformed fixes")
    count = 0
    for dep in report["dependencies"]:
        for finding in dep["vulns"]:
            if not isinstance(finding, dict) or not isinstance(finding.get("id"), str) or not finding["id"]:
                raise AuditError("malformed vulnerability result")
            count += 1
    expected_exit = 1 if count else 0
    if exit_code != expected_exit:
        raise AuditError("scanner exit status contradicts its report")
    return count


def run(argv: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuditError("dependency inspection or scanner unavailable") from exc


def check(lock_path: Path, python: Path, scanner: Path, output: Path | None) -> int:
    try:
        lock = parse_lock(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise AuditError("cannot read reference lock") from exc
    consistency = run([str(python), "-m", "pip", "check"], timeout=60)
    if consistency.returncode != 0:
        raise AuditError("installed dependency consistency check failed")
    installed_result = run([str(python), "-m", "pip", "list", "--format=json"], timeout=60)
    if installed_result.returncode != 0:
        raise AuditError("cannot inspect installed dependencies")
    try:
        installed = json.loads(installed_result.stdout)
    except json.JSONDecodeError as exc:
        raise AuditError("malformed installed dependency inventory") from exc
    # Check the installed environment before making any advisory request.
    installed_map = inventory(installed)
    if {k: v for k, v in installed_map.items() if k not in BOOTSTRAP} != lock:
        raise AuditError("installed packages do not match the reference lock")
    with tempfile.TemporaryDirectory(prefix="edgeforge-python-audit-") as tmp:
        raw_path = Path(tmp) / "audit.json"
        result = run(
            [
                str(scanner), "-r", str(lock_path), "--no-deps", "--disable-pip",
                "--strict", "--vulnerability-service", "pypi", "--progress-spinner", "off",
                "--timeout", "20", "--cache-dir", str(Path(tmp) / "cache"),
                "--format", "json", "--output", str(raw_path),
            ],
            timeout=300,
        )
        try:
            report = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AuditError("scanner did not return a valid report") from exc
        count = validate(installed, lock, report, result.returncode)
    if output is not None:
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"packages": len(lock), "findings": count, "status": "findings" if count else "clean"}, sort_keys=True))
    # Emit only identities, and only after the entire report has passed validation.
    findings = sorted(
        (normalize(dep["name"]), dep["version"], finding["id"])
        for dep in report["dependencies"] for finding in dep["vulns"]
    )
    for package, version, advisory_id in findings:
        print(json.dumps({"package": package, "installed_version": version, "advisory_id": advisory_id}, sort_keys=True), file=sys.stderr)
    return 1 if count else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path("requirements-lock.txt"))
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        return check(args.lock, args.python, args.scanner, args.output)
    except AuditError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
