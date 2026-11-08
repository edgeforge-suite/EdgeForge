"""Current-policy deterministic generation and standalone source contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from appbuilder.generation import generate_application
from appbuilder.generation.dependency_policy import DEPENDENCY_POLICY_ID
from appbuilder.metadata import build_metadata_project
from appbuilder.contracts import load_project_definition
from appbuilder.metadata.kafka_translation import translate_kafka_project
from appbuilder.target_profiles.catalog import TARGET_PROFILES
from scripts.assess_generated_maven import source_inventory
from scripts.smoke.boot41_batch_cases import CASES, case_metadata
from scripts.smoke.boot41_kafka_preview_proof import prepare_input

FIXTURES = {
    "crud": "examples/input-projects/generated-app-ci-smoke/app-definition.yaml",
    "soap": "tests/fixtures/edgecontracts/soap-wsdl/canonical-read-by-id-customer-service/app-definition.yaml",
    "soap-out": "tests/fixtures/edgecontracts/soap-wsdl/canonical-outbound-invoke-by-id-customer-client/app-definition.yaml",
    "passthrough": "examples/input-projects/country-router/app-definition.yaml",
    "batch": "examples/input-projects/obie-wire-transfer/app-definition.yaml",
    "kafka": "tests/fixtures/kafka-integration/manifest.yaml",
    "kafka-router": "tests/fixtures/kafka-router-contract/manifest.yaml",
}


def equivalence_case(root: Path, shape: str, profile: str) -> dict:
    if shape in CASES:
        metadata = case_metadata(shape, profile)
        source = "current-policy/" + shape
    else:
        fixture = (prepare_input(root / "mixed") / "manifest.yaml") if shape == "kafka-mixed" else Path(FIXTURES[shape])
        if shape.startswith("kafka"):
            definition = load_project_definition(fixture)
            definition.target_profile = profile
            metadata = translate_kafka_project(definition, fixture.parent)
        else:
            metadata = build_metadata_project(fixture)
            metadata.target_profile = profile
        source = "current-policy/" + shape if shape == "kafka-mixed" else FIXTURES[shape]
    outputs = [root / "first", root / "second"]
    for output in outputs:
        generate_application(metadata, output, source_manifest=source, generation_run_id="current-policy")
    first, second = (source_inventory(output) for output in outputs)
    if first != second:
        raise AssertionError(f"Nondeterministic current output: {shape}/{profile}")
    pom = (outputs[0] / "pom.xml").read_text()
    for declaration in ("<version>4.1.1</version>", "<tomcat.version>11.0.26</tomcat.version>",
                        "<jackson-bom.version>3.1.7</jackson-bom.version>",
                        "<jackson-2-bom.version>2.21.7</jackson-2-bom.version>"):
        if declaration not in pom:
            raise AssertionError(f"Missing policy declaration: {declaration}")
    if ("<artifactId>lz4-java</artifactId>" in pom) != shape.startswith("kafka"):
        raise AssertionError("LZ4 must be Kafka-only")
    record = json.loads((outputs[0] / "db/generation-provenance.json").read_text())
    if record["dependency_policy"] != DEPENDENCY_POLICY_ID:
        raise AssertionError("Missing dependency policy provenance")
    generate_application(metadata, outputs[0], source_manifest=source, generation_run_id="current-policy")
    if source_inventory(outputs[0]) != first:
        raise AssertionError("Same-policy regeneration changed source")
    return {"shape": shape, "profile": profile, "source_files": first,
            "dependency_policy": DEPENDENCY_POLICY_ID, "deterministic": True,
            "same_policy_regeneration": True}


def proof(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    shapes = tuple(FIXTURES) + tuple(CASES) + ("kafka-mixed",)
    rows = [equivalence_case(root / f"{shape}-{profile}", shape, profile)
            for shape in shapes for profile in TARGET_PROFILES]
    report = {"cases": rows, "result": "current-policy generation and regeneration deterministic"}
    (root / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(proof(args.work_dir), indent=2))
