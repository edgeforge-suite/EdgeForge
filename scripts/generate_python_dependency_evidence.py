#!/usr/bin/env python3
"""Generate Python-only dependency evidence from the reviewed reference environment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .python_dependency_audit import AuditError, check, inventory, normalize, parse_lock, run
else:
    from python_dependency_audit import AuditError, check, inventory, normalize, parse_lock, run


def command(argv: list[str], *, timeout: int = 300) -> str:
    result = run(argv, timeout=timeout)
    if result.returncode != 0:
        raise AuditError("evidence tool failed")
    return result.stdout.strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def direct_dependencies(requirements: Path) -> set[str]:
    names = set()
    for line in requirements.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"([A-Za-z0-9._-]+)==", line)
        if not match:
            raise AuditError("declared requirement is not exactly pinned")
        names.add(normalize(match.group(1)))
    return names


def validate_sbom(path: Path, lock: dict[str, str]) -> dict:
    try:
        sbom = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError("invalid CycloneDX SBOM") from exc
    if not isinstance(sbom, dict) or sbom.get("bomFormat") != "CycloneDX":
        raise AuditError("invalid CycloneDX SBOM")
    components = sbom.get("components")
    if inventory(components) != lock:
        raise AuditError("SBOM coverage does not match reference lock")
    for component in components:
        if not isinstance(component.get("purl"), str) or not component["purl"].startswith("pkg:pypi/"):
            raise AuditError("SBOM component missing PyPI PURL")
    return sbom


def validate_licenses(contents: str, lock: dict[str, str], direct: set[str]) -> tuple[str, str, int]:
    try:
        raw_rows = json.loads(contents)
    except json.JSONDecodeError as exc:
        raise AuditError("invalid license inventory") from exc
    if not isinstance(raw_rows, list):
        raise AuditError("invalid license inventory")
    rows = [
        {"name": row.get("Name"), "version": row.get("Version"), "license": row.get("License")}
        for row in raw_rows if isinstance(row, dict)
    ]
    if len(rows) != len(raw_rows):
        raise AuditError("invalid license inventory")
    if inventory(rows) != lock:
        raise AuditError("license inventory does not match reference lock")
    flagged = []
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Name", "Version", "License", "Scope"])
    table = ["| Package | Version | License | Scope |", "|---|---|---|---|"]
    for row in sorted(rows, key=lambda item: normalize(item["name"])):
        name, version, license_name = row["name"], row["version"], row.get("license")
        if not isinstance(license_name, str) or not license_name:
            raise AuditError("license inventory has a missing classification")
        scope = "direct" if normalize(name) in direct else "transitive"
        writer.writerow([name, version, license_name, scope])
        table.append(f"| `{name}` | {version} | {license_name.replace('|', '/')} | {scope} |")
        if re.search(r"GPL|MPL|EPL", license_name, re.I) or license_name.upper() == "UNKNOWN":
            flagged.append(name)
    return output.getvalue(), "\n".join(table) + "\n", len(flagged)


def generate(args: argparse.Namespace) -> int:
    lock = parse_lock(args.lock.read_text(encoding="utf-8"))
    direct = direct_dependencies(args.requirements)
    if not direct.issubset(lock):
        raise AuditError("declared dependencies are missing from reference lock")
    with tempfile.TemporaryDirectory(prefix="edgeforge-python-evidence-") as tmp:
        temporary = Path(tmp)
        sbom_path = temporary / "sbom.cdx.json"
        result = run(
            [str(args.cyclonedx), "requirements", str(args.lock), "--of", "JSON", "-o", str(sbom_path)],
            timeout=180,
        )
        if result.returncode != 0:
            raise AuditError("CycloneDX generation failed")
        sbom = validate_sbom(sbom_path, lock)
        licenses = command(
            [str(args.licenses), "--python", str(args.python), "--format", "json",
             "--ignore-packages", "pip", "setuptools", "wheel"],
            timeout=180,
        )
        csv_data, license_table, flagged = validate_licenses(licenses, lock, direct)
        audit_path = temporary / "pip-audit.json"
        audit_exit = check(args.lock, args.python, args.scanner, audit_path)
        audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
        findings = [
            (dep["name"], dep["version"], vuln["id"])
            for dep in audit_data["dependencies"] for vuln in dep["vulns"]
        ]
        python_details = json.loads(command([str(args.python), "-c",
            "import json,platform,sys;print(json.dumps({'python':platform.python_version(),"
            "'system':platform.system(),'machine':platform.machine(),"
            "'libc':platform.libc_ver()[1]}))"]))
        tool_versions = {
            "cyclonedx_bom": command([str(args.cyclonedx), "--version"]),
            "pip_licenses": command([str(args.licenses), "--version"]),
            "pip_audit": command([str(args.scanner), "--version"]),
        }
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        provenance = {
            "schema_version": "1.0",
            "assessment_time_utc": timestamp,
            "engine_source_sha": args.engine_sha,
            "reference_image": args.reference_image,
            "reference_python": python_details,
            "requirements_sha256": digest(args.requirements),
            "lock_sha256": digest(args.lock),
            "tools": tool_versions,
            "dependency_count": len(lock),
            "sbom_component_count": len(sbom["components"]),
            "license_row_count": len(lock),
            "audit_dependency_count": len(audit_data["dependencies"]),
            "finding_count": len(findings),
            "audit_exit_code": audit_exit,
            "exclusions": ["local Engine package", "pip/setuptools/wheel bootstrap tools"],
        }
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "sbom.cdx.json").write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (args.output / "dependency-licenses.csv").write_text(csv_data, encoding="utf-8")
        (args.output / "pip-audit.json").write_text(json.dumps(audit_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (args.output / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        status = "No advisories reported at scan time" if not findings else f"{len(findings)} advisory matches remain open"
        (args.output / "pip-audit.md").write_text(
            f"# Engine Python dependency audit\n\nScan time: {timestamp}. "
            f"Tool: {tool_versions['pip_audit']}. Packages: {len(lock)}. "
            f"Scanner exit: {audit_exit}. {status}.\n\n"
            "The audit covers the complete third-party reference lock, not the local Engine package "
            "or installer bootstrap tools. A clean result is not release approval.\n\n"
            + ("| Package | Version | Advisory |\n|---|---|---|\n" + "".join(
                f"| `{name}` | {version} | {advisory} |\n" for name, version, advisory in findings
            ) if findings else "_No findings in this scan._\n"),
            encoding="utf-8",
        )
        (args.output / "dependency-licenses.md").write_text(
            f"# Engine Python dependency licenses\n\nScan time: {timestamp}. "
            f"Tool: {tool_versions['pip_licenses']}. Packages: {len(lock)}. "
            f"Copyleft/UNKNOWN classifications requiring review: {flagged}. "
            "This is inventory, not a license acceptance decision.\n\n" + license_table,
            encoding="utf-8",
        )
        return audit_exit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, default=Path("requirements.txt"))
    parser.add_argument("--lock", type=Path, default=Path("requirements-lock.txt"))
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--cyclonedx", type=Path, required=True)
    parser.add_argument("--licenses", type=Path, required=True)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine-sha", required=True)
    parser.add_argument("--reference-image", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.engine_sha):
        parser.error("engine source SHA must be a full commit SHA")
    try:
        return generate(args)
    except (AuditError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc) if isinstance(exc, AuditError) else "evidence generation failed"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
