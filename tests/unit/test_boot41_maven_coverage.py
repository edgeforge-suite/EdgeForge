from pathlib import Path

import pytest

from appbuilder.metadata import build_metadata_project
from scripts import collect_generated_maven_baseline as collector
from scripts import finalize_generated_maven_evidence as finalizer
from scripts.assess_generated_maven import AssessmentError


@pytest.mark.parametrize("shape", list(collector.FIXTURES))
def test_promoted_matrix_has_reproducible_trusted_input(tmp_path: Path, shape: str):
    manifest = collector.prepare_case_input(tmp_path, shape, collector.FIXTURES[shape])
    metadata = build_metadata_project(manifest)
    if shape == "mixed-batch":
        assert {e.name for e in metadata.entities} == {"Widget", "Account"}
        assert any(c.run_semantics for c in metadata.contracts)
        assert any(c.type == "file-csv" for c in metadata.contracts)
    if shape == "kafka-mixed":
        assert metadata.routes and metadata.router_routes


def test_graph_classes_come_from_both_validated_passes_not_shape_assumptions():
    validated = {
        case: {run: {"graph_sha256": digest, "report": {"resolved_artifacts": 3}}
               for run in ("assessment", "repeat")}
        for case, digest in (("jobless", "a" * 64), ("batch", "b" * 64), ("mixed", "b" * 64))
    }
    groups = finalizer.observed_graph_classes(validated, list(validated))
    result = finalizer.build_graph_equivalence(validated, list(validated), groups)
    assert len(result["classes"]) == 2
    validated["mixed"]["repeat"]["graph_sha256"] = "c" * 64
    with pytest.raises(AssessmentError, match="repeat graph differs"):
        finalizer.build_graph_equivalence(validated, list(validated), groups)


@pytest.mark.parametrize("group", ["com.appbuilder", "com.customer", "org.private", ""])
def test_root_or_unreviewed_namespace_is_refused_before_query(group):
    with pytest.raises(AssessmentError, match="query not authorized"):
        collector.validate_public_query_inventory([{"group": group}])


def test_namespace_alone_does_not_authorize_a_private_artifact(tmp_path):
    record = {"group": "org.springframework.boot", "artifact": "private-customer", "version": "1"}
    with pytest.raises(AssessmentError, match="POM origin absent"):
        collector.validate_public_query_inventory([record], tmp_path)


def test_public_pom_inspection_is_required_and_checks_identity(tmp_path):
    record = {"group": "org.springframework.boot", "artifact": "spring-boot", "version": "4.1.1"}
    with pytest.raises(AssessmentError, match="inspection required"):
        collector.validate_public_query_inventory([record])
    directory = tmp_path / "org/springframework/boot/spring-boot/4.1.1"
    directory.mkdir(parents=True)
    (directory / "spring-boot-4.1.1.pom").write_text("<project><artifactId>spring-boot</artifactId></project>")
    (directory / "_remote.repositories").write_text("spring-boot-4.1.1.pom>central=\n")
    collector.validate_public_query_inventory([record], tmp_path)
    (directory / "spring-boot-4.1.1.pom").write_text("<project><artifactId>private-customer</artifactId></project>")
    with pytest.raises(AssessmentError, match="coordinate mismatch"):
        collector.validate_public_query_inventory([record], tmp_path)
