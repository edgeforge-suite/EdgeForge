"""Fail closed on unsupported retained-package framework transitions."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from appbuilder.target_profiles.catalog import TargetProfile

from .durable_json import load_durable_json
from .dependency_policy import DEPENDENCY_POLICY_ID
from .file_writer import write_generated_file

PROVENANCE_PATH = Path("db/generation-provenance.json")
_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


def _unique_children(element: ET.Element) -> dict[str, ET.Element]:
    if (element.text or "").strip():
        raise ValueError("Non-element content in Maven identity")
    children = {}
    for child in element:
        name = child.tag.rsplit("}", 1)[-1]
        if child.tag != f"{{{_NS['m']}}}{name}" or name in children or (child.tail or "").strip():
            raise ValueError("Ambiguous Maven identity declaration")
        children[name] = child
    return children


def _identity_text(children: dict[str, ET.Element], name: str) -> str:
    element = children.get(name)
    if element is None or len(element) or element.attrib or not (element.text or "").strip():
        raise ValueError("Missing or non-scalar Maven identity declaration")
    return element.text.strip()


def require_compatible_package(package: Path, profile: TargetProfile) -> None:
    """Reconcile actual POM, internal schemas and persisted framework, never old IDs."""

    if not profile.experimental_boot41:
        return
    markers = ("pom.xml", "src", "db", "build.gradle", "build.gradle.kts")
    if not any((package / marker).exists() for marker in markers):
        return
    diagnostic = (
        "Unsupported existing package transition: Boot 3/Batch 5, an unvalidated patch "
        "baseline or ambiguous framework "
        "evidence cannot be generated, planned or applied as Boot 4.1/Batch 6. "
        "Keep the existing package unchanged; use a separate fresh package/database. "
        "No application, database or history migration is supported."
    )
    try:
        pom = ET.fromstring((package / "pom.xml").read_text(encoding="utf-8"))
        if pom.tag != f"{{{_NS['m']}}}project":
            raise ValueError(diagnostic)
        project = _unique_children(pom)
        if _identity_text(project, "modelVersion") != "4.0.0":
            raise ValueError(diagnostic)
        for name in ("groupId", "artifactId", "version"):
            _identity_text(project, name)
        parent = project.get("parent")
        if parent is None or parent.attrib:
            raise ValueError(diagnostic)
        identity = _unique_children(parent)
        relative = identity.get("relativePath")
        if relative is not None and (len(relative) or relative.attrib):
            raise ValueError(diagnostic)
        if set(identity) - {"groupId", "artifactId", "version", "relativePath"} or (
            _identity_text(identity, "groupId"),
            _identity_text(identity, "artifactId"),
        ) != ("org.springframework.boot", "spring-boot-starter-parent"):
            raise ValueError(diagnostic)
        version = _identity_text(identity, "version")
        if version != profile.spring_boot_baseline:
            raise ValueError(diagnostic)
        provenance = package / PROVENANCE_PATH
        if provenance.exists():
            record = load_durable_json(provenance)
            if record != framework_record(version):
                raise ValueError(diagnostic)
        baseline = package / "db/schema-baseline.json"
        if baseline.exists():
            value = load_durable_json(baseline)
            if not isinstance(value, dict):
                raise ValueError(diagnostic)
            entries = value.get("internal_schemas", [])
            if not isinstance(entries, list):
                raise ValueError(diagnostic)
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError(diagnostic)
                if entry.get("id") == "pkg-batch-metadata" and entry.get(
                    "spring_batch_metadata_schema_version"
                ) != "6.0.5":
                    raise ValueError(diagnostic)
    except (OSError, UnicodeError, ET.ParseError, ValueError, TypeError) as exc:
        raise ValueError(diagnostic) from exc


def framework_record(version: str) -> dict[str, str]:
    return {"provenance_schema_version": "1.0", "framework": "spring-boot", "spring_boot_version": version,
            "dependency_policy": DEPENDENCY_POLICY_ID}


def emit_framework_provenance(package: Path, profile: TargetProfile) -> Path:
    path = package / PROVENANCE_PATH
    if not path.exists():
        write_generated_file(
            path,
            json.dumps(framework_record(profile.spring_boot_baseline), indent=2, sort_keys=True) + "\n",
            ownership="generated",
        )
    return path
