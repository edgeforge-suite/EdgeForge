from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.metadata.translation import build_metadata_project
from scripts.smoke.generated_app_independence import (
    IndependenceVerificationError,
    verify_generated_app_independence,
)

POM = """\
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.4</version>
    <relativePath/>
  </parent>
  <groupId>com.appbuilder</groupId>
  <artifactId>sample-app</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""


def _clean_package(tmp_path: Path, *, context: str = "sample") -> Path:
    package = tmp_path / "generated-app"
    generated_source = (
        package / f"src/main/java/com/appbuilder/{context}/domain/Widget.java"
    )
    generated_source.parent.mkdir(parents=True)
    generated_source.write_text(
        f"""\
// EdgeForge-ownership: generated
package com.appbuilder.{context}.domain;
import com.appbuilder.{context}.service.WidgetService;
public class Widget {{}}
""",
        encoding="utf-8",
    )
    developer_service = (
        package / f"src/main/java/com/appbuilder/{context}/service/WidgetService.java"
    )
    developer_service.parent.mkdir(parents=True)
    developer_service.write_text(
        f"""\
// EdgeForge-ownership: developer
package com.appbuilder.{context}.service;
public class WidgetService {{}}
""",
        encoding="utf-8",
    )
    (package / "db").mkdir()
    (package / "db/schema-baseline.json").write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "entity": "Widget",
                        "generated_source_files": [
                            f"src/main/java/com/appbuilder/{context}/domain/Widget.java"
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (package / "pom.xml").write_text(POM, encoding="utf-8")
    (package / ".gitignore").write_text(
        "# EdgeForge-ownership: developer\ntarget/\n",
        encoding="utf-8",
    )
    (package / ".dockerignore").write_text(
        "# EdgeForge-ownership: developer\ntarget/\n",
        encoding="utf-8",
    )
    (package / "README.md").write_text(
        """\
Source manifest: app-definition.yaml
Logical contract: upstream/customer-api.yaml
See agent-context.md for generated provenance.
""",
        encoding="utf-8",
    )
    (package / "agent-context.md").write_text(
        "Contract source: contracts/customer-openapi.json (logical provenance only)\n",
        encoding="utf-8",
    )
    return package


def _write_executable_jar(package: Path, *library_entries: str) -> Path:
    jar_path = package / "target/sample-app-0.0.1-SNAPSHOT.jar"
    jar_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(jar_path, "w") as archive:
        archive.writestr("BOOT-INF/classes/com/appbuilder/sample/Application.class", b"clean")
        for entry in library_entries:
            archive.writestr(f"BOOT-INF/lib/{entry}", b"library")
    return jar_path


def _replace_pom(package: Path, old: str, new: str) -> None:
    pom_path = package / "pom.xml"
    pom_path.write_text(
        pom_path.read_text(encoding="utf-8").replace(old, new),
        encoding="utf-8",
    )


def test_clean_package_accepts_own_namespace_coordinate_and_logical_provenance(
    tmp_path: Path,
) -> None:
    package = _clean_package(tmp_path)

    report = verify_generated_app_independence(package)

    assert report.baseline_generated_source_count == 1
    assert report.packaged_jar is None
    assert {check.name for check in report.checks} == {
        "repository-boundary",
        "java-imports",
        "maven-boundary",
        "schema-baseline",
        "repository-hygiene",
        "author-paths",
        "packaged-jar",
    }


def test_accepts_own_namespace_when_context_matches_forbidden_suite_token(
    tmp_path: Path,
) -> None:
    package = _clean_package(tmp_path, context="knowledge")

    report = verify_generated_app_independence(package)

    assert report.baseline_generated_source_count == 1


def test_rejects_forbidden_appbuilder_namespace_outside_current_application(
    tmp_path: Path,
) -> None:
    package = _clean_package(tmp_path)
    source = package / "src/main/java/com/appbuilder/sample/domain/Widget.java"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "import com.appbuilder.sample.service.WidgetService;",
            "import com.appbuilder.knowledge.runtime.KnowledgeClient;",
        ),
        encoding="utf-8",
    )

    with pytest.raises(IndependenceVerificationError, match=r"\[java-imports\]"):
        verify_generated_app_independence(package)


def test_rejects_forbidden_java_import(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    source = package / "src/main/java/com/appbuilder/sample/domain/Widget.java"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "import com.appbuilder.sample.service.WidgetService;",
            "import com.edgeforge.runtime.GenerationContext;",
        ),
        encoding="utf-8",
    )

    with pytest.raises(IndependenceVerificationError, match=r"\[java-imports\]"):
        verify_generated_app_independence(package)


@pytest.mark.parametrize("kind", ["dependency", "plugin"])
def test_rejects_generator_owned_maven_dependency_or_plugin(
    tmp_path: Path,
    kind: str,
) -> None:
    package = _clean_package(tmp_path)
    if kind == "dependency":
        block = """\
    <dependency>
      <groupId>com.edgeforge</groupId>
      <artifactId>appbuilder-runtime</artifactId>
    </dependency>
"""
        _replace_pom(package, "  </dependencies>", f"{block}  </dependencies>")
    else:
        block = """\
      <plugin>
        <groupId>com.edgeforge</groupId>
        <artifactId>appbuilder-maven-plugin</artifactId>
      </plugin>
"""
        _replace_pom(package, "    </plugins>", f"{block}    </plugins>")

    with pytest.raises(IndependenceVerificationError, match=r"\[maven-boundary\]"):
        verify_generated_app_independence(package)


def test_rejects_local_system_path_dependency(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    block = """\
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>local-runtime</artifactId>
      <version>1.0</version>
      <scope>system</scope>
      <systemPath>${project.basedir}/../lib/local-runtime.jar</systemPath>
    </dependency>
"""
    _replace_pom(package, "  </dependencies>", f"{block}  </dependencies>")

    with pytest.raises(
        IndependenceVerificationError,
        match=r"\[maven-boundary\].*systemPath",
    ):
        verify_generated_app_independence(package)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "  <build>",
            "  <modules><module>../shared-runtime</module></modules>\n  <build>",
            "local Maven modules",
        ),
        (
            "    <relativePath/>",
            "    <relativePath>../pom.xml</relativePath>",
            "parent-filesystem",
        ),
    ],
)
def test_rejects_local_module_or_parent_filesystem_dependency(
    tmp_path: Path,
    old: str,
    new: str,
    message: str,
) -> None:
    package = _clean_package(tmp_path)
    _replace_pom(package, old, new)

    with pytest.raises(
        IndependenceVerificationError,
        match=rf"\[maven-boundary\].*{message}",
    ):
        verify_generated_app_independence(package)


def test_rejects_authoring_only_directory(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    (package / "contracts").mkdir()
    (package / "contracts/customer.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")

    with pytest.raises(
        IndependenceVerificationError,
        match=r"\[repository-boundary\].*contracts/",
    ):
        verify_generated_app_independence(package)


def test_accepts_evidence_trail_as_provenance_metadata(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    (package / "evidence-trail.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "evidence": [
                    {
                        "type": "mapping",
                        "source_path": "upstream/customer-api.yaml",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = verify_generated_app_independence(package)

    assert report.baseline_generated_source_count == 1


def test_rejects_author_machine_path_inside_evidence_trail(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    (package / "evidence-trail.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "source_path": "/" + "Users/alice/work/contracts/customer-api.yaml",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(IndependenceVerificationError, match=r"\[author-paths\]"):
        verify_generated_app_independence(package)


@pytest.mark.parametrize("metadata_path", [Path(".git"), Path(".git/config")])
def test_ignores_git_worktree_metadata_when_scanning_author_paths(
    tmp_path: Path,
    metadata_path: Path,
) -> None:
    package = _clean_package(tmp_path)
    path = package / metadata_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "gitdir: /" + "Users/alice/worktrees/generated-app\n",
        encoding="utf-8",
    )

    report = verify_generated_app_independence(package)

    assert report.baseline_generated_source_count == 1


def test_rejects_missing_baseline_source_path(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    baseline_path = package / "db/schema-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["entities"][0]["generated_source_files"].append(
        "src/main/java/com/appbuilder/sample/domain/Missing.java"
    )
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    with pytest.raises(
        IndependenceVerificationError,
        match=r"\[schema-baseline\].*missing generated source",
    ):
        verify_generated_app_independence(package)


def test_baseline_is_optional_by_archetype_but_can_be_required(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    (package / "db/schema-baseline.json").unlink()

    report = verify_generated_app_independence(package)
    assert report.baseline_generated_source_count == 0

    with pytest.raises(
        IndependenceVerificationError,
        match=r"\[schema-baseline\].*missing",
    ):
        verify_generated_app_independence(package, require_schema_baseline=True)


def test_rejects_baseline_entry_for_developer_owned_service(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    baseline_path = package / "db/schema-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["entities"][0]["generated_source_files"] = [
        "src/main/java/com/appbuilder/sample/service/WidgetService.java"
    ]
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    with pytest.raises(
        IndependenceVerificationError,
        match=r"\[schema-baseline\].*not generated-owned",
    ):
        verify_generated_app_independence(package)


def test_rejects_forbidden_packaged_library(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    _write_executable_jar(package, "edgeforge-runtime-4.1.1.jar")

    with pytest.raises(
        IndependenceVerificationError,
        match=r"\[packaged-jar\].*edgeforge-runtime",
    ):
        verify_generated_app_independence(package, require_packaged_jar=True)


def test_accepts_clean_packaged_jar_with_application_namespace(tmp_path: Path) -> None:
    package = _clean_package(tmp_path)
    jar_path = _write_executable_jar(package, "spring-core-6.1.13.jar")

    report = verify_generated_app_independence(package, require_packaged_jar=True)

    assert report.packaged_jar == jar_path.relative_to(package).as_posix()


@pytest.mark.parametrize(
    "author_path",
    [
        "/" + "Users/alice/work/edgeforge/app-definition.yaml",
        "/home/alice/work/edgeforge/app-definition.yaml",
        r"C:\Users\alice\work\edgeforge\app-definition.yaml",
    ],
)
def test_rejects_absolute_author_machine_paths(
    tmp_path: Path,
    author_path: str,
) -> None:
    package = _clean_package(tmp_path)
    (package / "README.md").write_text(author_path, encoding="utf-8")

    with pytest.raises(IndependenceVerificationError, match=r"\[author-paths\]"):
        verify_generated_app_independence(package)


def test_accepts_clean_pr279_generated_output(tmp_path: Path) -> None:
    manifest = Path("examples/input-projects/workspace-items/app-definition.yaml")
    metadata = build_metadata_project(manifest)
    package = tmp_path / "workspace-generated-app"
    generate_application(
        metadata,
        package,
        source_manifest=str(manifest),
        generation_run_id="standalone-verifier-test",
    )

    report = verify_generated_app_independence(package)

    assert report.baseline_generated_source_count == 16
    assert report.packaged_jar is None
