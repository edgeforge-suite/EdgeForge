#!/usr/bin/env python3
"""Verify that a generated application is an independent handoff repository.

The verifier is intentionally read-only and archetype-neutral. It checks source,
Maven, baseline, repository, and packaged-JAR boundaries without requiring the
EdgeForge Engine at generated-app build or runtime.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

FORBIDDEN_SUITE_TOKENS = {
    "edgeforge",
    "studio",
    "knowledge",
    "knowledgeassist",
    "knowledgeserver",
    "ks",
    "ka",
    "mcp",
    "testbench",
}
AUTHORING_ROOT_NAMES = {
    "contracts",
    "upstream",
    "downstream",
    "data-handoffs",
    "rules",
    "legacy",
}
AUTHORING_FILE_NAMES = {
    "app-definition.yaml",
    "app-definition.yml",
    "studio-project.json",
    "assessment-report.json",
    "completeness-report.json",
    "mapping-completeness-report.json",
}
TEXT_FILE_SUFFIXES = {
    "",
    ".gitignore",
    ".dockerignore",
    ".java",
    ".json",
    ".md",
    ".properties",
    ".sql",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
AUTHOR_PATH_PATTERNS = (
    re.compile(rb"/" rb"Users/[^/\s\x00]+(?:/|\\)"),
    re.compile(rb"/home/[^/\s\x00]+/"),
    re.compile(
        rb"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/\s\x00]+[\\/]"
    ),
)


class IndependenceVerificationError(AssertionError):
    """A check-specific generated-app independence failure."""

    def __init__(self, check: str, message: str):
        self.check = check
        self.message = message
        super().__init__(f"[{check}] {message}")


@dataclass(frozen=True)
class IndependenceCheck:
    name: str
    detail: str


@dataclass
class IndependenceReport:
    package: str
    checks: list[IndependenceCheck] = field(default_factory=list)
    baseline_generated_source_count: int = 0
    packaged_jar: str | None = None

    def add(self, name: str, detail: str) -> None:
        self.checks.append(IndependenceCheck(name=name, detail=detail))

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = "passed"
        return payload


def verify_generated_app_independence(
    package: Path | str,
    *,
    require_packaged_jar: bool = False,
    require_schema_baseline: bool = False,
) -> IndependenceReport:
    """Verify a generated repository without modifying it.

    Before Maven packaging, omit ``require_packaged_jar`` to run source and
    repository checks. After packaging, require the executable JAR so its
    ``BOOT-INF/lib`` and embedded path boundary are checked too.
    """

    package_path = Path(package).resolve()
    _require(
        "package-root",
        package_path.is_dir(),
        f"generated package directory does not exist: {package_path}",
    )
    report = IndependenceReport(package=package_path.as_posix())

    _verify_repository_boundary(package_path)
    report.add("repository-boundary", "no authoring-source package paths are present")

    _verify_java_imports(package_path)
    report.add("java-imports", "no suite runtime imports are present")

    project_coordinate = _verify_pom(package_path)
    report.add(
        "maven-boundary",
        f"no generator-owned/local Maven dependency; project={project_coordinate}",
    )

    baseline_count = _verify_schema_baseline(
        package_path,
        required=require_schema_baseline,
    )
    report.baseline_generated_source_count = baseline_count
    baseline_detail = (
        f"{baseline_count} generated source paths exist and carry generated ownership"
        if (package_path / "db/schema-baseline.json").is_file()
        else "not emitted for this archetype"
    )
    report.add("schema-baseline", baseline_detail)

    _verify_repository_hygiene(package_path)
    report.add("repository-hygiene", ".gitignore and .dockerignore are present")

    _verify_text_artifact_paths(package_path)
    report.add("author-paths", "no absolute author-machine path is embedded")

    packaged_jars = _packaged_jars(package_path)
    if require_packaged_jar:
        _require(
            "packaged-jar",
            bool(packaged_jars),
            "no executable Spring Boot JAR found under target/",
        )
    if packaged_jars:
        _require(
            "packaged-jar",
            len(packaged_jars) == 1,
            "expected one executable Spring Boot JAR, found "
            + ", ".join(path.name for path in packaged_jars),
        )
        jar_path = packaged_jars[0]
        _verify_packaged_jar(package_path, jar_path)
        report.packaged_jar = jar_path.relative_to(package_path).as_posix()
        report.add(
            "packaged-jar",
            f"{report.packaged_jar} has no generator-owned library or author path",
        )
    else:
        report.add("packaged-jar", "not present yet; packaged boundary check deferred")

    return report


def _verify_repository_boundary(package: Path) -> None:
    for root_name in sorted(AUTHORING_ROOT_NAMES):
        path = package / root_name
        _require(
            "repository-boundary",
            not path.exists(),
            f"authoring-only path is present: {root_name}/",
        )

    for path in sorted(package.rglob("*")):
        relative_path = path.relative_to(package)
        if _is_git_metadata(relative_path):
            continue
        if path.is_symlink():
            raise IndependenceVerificationError(
                "repository-boundary",
                f"generated repository contains a symbolic link: {relative_path.as_posix()}",
            )
        if not path.is_file():
            continue
        lowered_name = path.name.lower()
        if lowered_name in AUTHORING_FILE_NAMES:
            raise IndependenceVerificationError(
                "repository-boundary",
                f"authoring-only file is present: {relative_path.as_posix()}",
            )
        if (
            lowered_name.endswith(".json")
            and ("assessment" in lowered_name or "completeness" in lowered_name)
        ):
            raise IndependenceVerificationError(
                "repository-boundary",
                f"authoring-only report is present: {relative_path.as_posix()}",
            )


def _verify_java_imports(package: Path) -> None:
    java_root = package / "src" / "main" / "java"
    application_namespaces = _application_namespaces(java_root)
    for path in sorted(java_root.rglob("*.java")) if java_root.is_dir() else []:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            stripped = line.strip()
            if not stripped.startswith("import "):
                continue
            import_path = stripped.removeprefix("import ").strip().removesuffix(";")
            if import_path.startswith("static "):
                import_path = import_path.removeprefix("static ").strip()
            if (
                not _is_application_namespace(import_path, application_namespaces)
                and _contains_forbidden_suite_token(import_path)
            ):
                relative = path.relative_to(package).as_posix()
                raise IndependenceVerificationError(
                    "java-imports",
                    f"forbidden suite import in {relative}:{line_number}: {stripped}",
                )


def _verify_pom(package: Path) -> str:
    pom_path = package / "pom.xml"
    _require("maven-boundary", pom_path.is_file(), "pom.xml is missing")
    try:
        root = ET.parse(pom_path).getroot()
    except ET.ParseError as exc:
        raise IndependenceVerificationError(
            "maven-boundary",
            f"pom.xml is not valid XML: {exc}",
        ) from exc

    project_group = _child_text(root, "groupId") or _nested_text(root, "parent", "groupId")
    project_artifact = _child_text(root, "artifactId")
    _require(
        "maven-boundary",
        bool(project_group and project_artifact),
        "pom.xml must declare a resolvable project groupId and artifactId",
    )
    project_coordinate = (project_group or "", project_artifact or "")

    parent = _first_child(root, "parent")
    if parent is not None:
        relative_path = _first_child(parent, "relativePath")
        _require(
            "maven-boundary",
            relative_path is not None and not (relative_path.text or "").strip(),
            "Maven parent must disable parent-filesystem lookup with an empty <relativePath/>",
        )
        _reject_forbidden_coordinate(
            "parent",
            _child_text(parent, "groupId"),
            _child_text(parent, "artifactId"),
            project_coordinate,
        )

    modules = list(_descendants(root, "module"))
    _require(
        "maven-boundary",
        not modules,
        "local Maven modules are not allowed in a standalone generated repository",
    )

    for dependency in _descendants(root, "dependency"):
        group_id = _child_text(dependency, "groupId")
        artifact_id = _child_text(dependency, "artifactId")
        scope = (_child_text(dependency, "scope") or "").strip().lower()
        system_path = _child_text(dependency, "systemPath")
        _require(
            "maven-boundary",
            scope != "system" and not system_path,
            "Maven systemPath/system-scope dependencies are not allowed"
            + _coordinate_suffix(group_id, artifact_id),
        )
        _reject_forbidden_coordinate(
            "dependency",
            group_id,
            artifact_id,
            project_coordinate,
        )

    for plugin in _descendants(root, "plugin"):
        _reject_forbidden_coordinate(
            "plugin",
            _child_text(plugin, "groupId") or "org.apache.maven.plugins",
            _child_text(plugin, "artifactId"),
            project_coordinate,
        )

    for extension in _descendants(root, "extension"):
        _reject_forbidden_coordinate(
            "build extension",
            _child_text(extension, "groupId"),
            _child_text(extension, "artifactId"),
            project_coordinate,
        )

    for repository_url in _descendants(root, "url"):
        value = (repository_url.text or "").strip().lower()
        _require(
            "maven-boundary",
            not value.startswith("file:"),
            f"local file Maven repository URL is not allowed: {value}",
        )

    return f"{project_coordinate[0]}:{project_coordinate[1]}"


def _verify_schema_baseline(package: Path, *, required: bool) -> int:
    baseline_path = package / "db" / "schema-baseline.json"
    if not baseline_path.exists() and not required:
        return 0
    _require(
        "schema-baseline",
        baseline_path.is_file(),
        "db/schema-baseline.json is missing",
    )
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IndependenceVerificationError(
            "schema-baseline",
            f"db/schema-baseline.json is invalid: {exc}",
        ) from exc

    count = 0
    for entity in baseline.get("entities", []):
        entity_name = entity.get("entity", "<unknown>")
        for relative_value in entity.get("generated_source_files", []):
            count += 1
            relative_path = _safe_package_relative_path(
                relative_value,
                check="schema-baseline",
            )
            source_path = package.joinpath(*relative_path.parts)
            _require(
                "schema-baseline",
                source_path.is_file(),
                f"{entity_name} lists missing generated source: {relative_value}",
            )
            content = source_path.read_text(encoding="utf-8")
            _require(
                "schema-baseline",
                _ownership_marker(content) == "generated",
                f"{entity_name} baseline path is not generated-owned: {relative_value}",
            )
            _require(
                "schema-baseline",
                not (
                    source_path.name.endswith("Service.java")
                    and not source_path.name.endswith("ServiceBase.java")
                ),
                f"developer-owned service subclass appears in baseline: {relative_value}",
            )
    return count


def _verify_repository_hygiene(package: Path) -> None:
    for name in (".gitignore", ".dockerignore"):
        path = package / name
        _require("repository-hygiene", path.is_file(), f"{name} is missing")


def _verify_text_artifact_paths(package: Path) -> None:
    for path in sorted(package.rglob("*")):
        relative_path = path.relative_to(package)
        if (
            not path.is_file()
            or "target" in relative_path.parts
            or _is_git_metadata(relative_path)
        ):
            continue
        if path.suffix.lower() not in TEXT_FILE_SUFFIXES and path.name not in {
            ".gitignore",
            ".dockerignore",
        }:
            continue
        _reject_author_path_bytes(
            path.read_bytes(),
            check="author-paths",
            location=relative_path.as_posix(),
        )


def _packaged_jars(package: Path) -> list[Path]:
    target = package / "target"
    if not target.is_dir():
        return []
    candidates: list[Path] = []
    for path in sorted(target.glob("*.jar")):
        lowered = path.name.lower()
        if lowered.endswith(".jar.original") or "-sources." in lowered or "-javadoc." in lowered:
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                if "BOOT-INF/classes/" in {name.rstrip("/") + "/" for name in archive.namelist()}:
                    candidates.append(path)
                    continue
                if any(name.startswith("BOOT-INF/classes/") for name in archive.namelist()):
                    candidates.append(path)
        except zipfile.BadZipFile:
            continue
    return candidates


def _verify_packaged_jar(package: Path, jar_path: Path) -> None:
    try:
        with zipfile.ZipFile(jar_path) as archive:
            for info in archive.infolist():
                normalized = PurePosixPath(info.filename).as_posix()
                if normalized.startswith("BOOT-INF/lib/") and not info.is_dir():
                    library_name = PurePosixPath(normalized).name
                    if _coordinate_is_forbidden("", library_name, project_coordinate=None):
                        raise IndependenceVerificationError(
                            "packaged-jar",
                            f"forbidden suite library in executable JAR: {normalized}",
                        )
                if info.is_dir():
                    continue
                _reject_author_path_bytes(
                    archive.read(info),
                    check="packaged-jar",
                    location=f"{jar_path.relative_to(package).as_posix()}!/{normalized}",
                )
    except zipfile.BadZipFile as exc:
        raise IndependenceVerificationError(
            "packaged-jar",
            f"packaged JAR is invalid: {jar_path.name}",
        ) from exc


def _reject_forbidden_coordinate(
    kind: str,
    group_id: str | None,
    artifact_id: str | None,
    project_coordinate: tuple[str, str],
) -> None:
    if _coordinate_is_forbidden(group_id or "", artifact_id or "", project_coordinate):
        raise IndependenceVerificationError(
            "maven-boundary",
            f"generator-owned Maven {kind} is not allowed"
            + _coordinate_suffix(group_id, artifact_id),
        )


def _coordinate_is_forbidden(
    group_id: str,
    artifact_id: str,
    project_coordinate: tuple[str, str] | None,
) -> bool:
    coordinate = (group_id.strip(), artifact_id.strip())
    if project_coordinate is not None and coordinate == project_coordinate:
        return False
    tokens = _tokens(".".join(coordinate))
    if tokens & FORBIDDEN_SUITE_TOKENS:
        return True
    return "appbuilder" in tokens


def _contains_forbidden_suite_token(value: str) -> bool:
    return bool(_tokens(value) & FORBIDDEN_SUITE_TOKENS)


def _application_namespaces(java_root: Path) -> tuple[str, ...]:
    namespaces: set[str] = set()
    if not java_root.is_dir():
        return ()
    for source_path in sorted(java_root.rglob("*.java")):
        relative_parts = source_path.relative_to(java_root).parts
        if len(relative_parts) >= 4 and relative_parts[:2] == ("com", "appbuilder"):
            namespaces.add(".".join(relative_parts[:3]))
    return tuple(sorted(namespaces))


def _is_application_namespace(
    import_path: str,
    application_namespaces: tuple[str, ...],
) -> bool:
    return any(
        import_path == namespace or import_path.startswith(f"{namespace}.")
        for namespace in application_namespaces
    )


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if token
    }


def _is_git_metadata(relative_path: Path) -> bool:
    return bool(relative_path.parts) and relative_path.parts[0] == ".git"


def _reject_author_path_bytes(data: bytes, *, check: str, location: str) -> None:
    for pattern in AUTHOR_PATH_PATTERNS:
        match = pattern.search(data)
        if match:
            rendered = match.group(0).decode("utf-8", errors="replace")
            raise IndependenceVerificationError(
                check,
                f"absolute author-machine path in {location}: {rendered}",
            )


def _safe_package_relative_path(value: object, *, check: str) -> PurePosixPath:
    _require(check, isinstance(value, str) and bool(value), "baseline source path is invalid")
    path = PurePosixPath(str(value))
    _require(
        check,
        not path.is_absolute() and ".." not in path.parts,
        f"baseline source path escapes the package: {value}",
    )
    return path


def _ownership_marker(content: str) -> str | None:
    for line in content.splitlines()[:20]:
        if "EdgeForge-ownership:" not in line:
            continue
        return line.split("EdgeForge-ownership:", 1)[1].strip().split()[0].lower()
    return None


def _first_child(element: ET.Element, local_name: str) -> ET.Element | None:
    return next(
        (child for child in element if _local_name(child.tag) == local_name),
        None,
    )


def _child_text(element: ET.Element, local_name: str) -> str | None:
    child = _first_child(element, local_name)
    if child is None:
        return None
    return (child.text or "").strip() or None


def _nested_text(element: ET.Element, parent: str, child: str) -> str | None:
    parent_element = _first_child(element, parent)
    if parent_element is None:
        return None
    return _child_text(parent_element, child)


def _descendants(element: ET.Element, local_name: str) -> Iterable[ET.Element]:
    return (
        descendant
        for descendant in element.iter()
        if _local_name(descendant.tag) == local_name
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _coordinate_suffix(group_id: str | None, artifact_id: str | None) -> str:
    if not group_id and not artifact_id:
        return ""
    return f": {group_id or '<missing>'}:{artifact_id or '<missing>'}"


def _require(check: str, condition: bool, message: str) -> None:
    if not condition:
        raise IndependenceVerificationError(check, message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a generated app's standalone repository and packaged boundaries."
    )
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument(
        "--require-packaged-jar",
        action="store_true",
        help="Fail unless an executable Spring Boot JAR is present and clean.",
    )
    parser.add_argument(
        "--require-schema-baseline",
        action="store_true",
        help="Fail unless db/schema-baseline.json is present and internally consistent.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    try:
        report = verify_generated_app_independence(
            args.package,
            require_packaged_jar=args.require_packaged_jar,
            require_schema_baseline=args.require_schema_baseline,
        )
    except IndependenceVerificationError as exc:
        if args.as_json:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "check": exc.check,
                        "error": exc.message,
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for check in report.checks:
            print(f"[PASS] {check.name}: {check.detail}")
        print("[PASS] generated-app standalone independence verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
