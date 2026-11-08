"""Trusted, synthetic case selection shared by Batch preview proof and tests."""

# ruff: noqa: E402 -- the optimization refusal intentionally precedes imports.

from scripts.smoke.boot41_batch_guard import require_unoptimized_python

require_unoptimized_python()

from appbuilder.metadata import build_metadata_project

M5A_FIXTURE = "tests/fixtures/manifest-v2-cut/v2-run-semantics-app-definition.yaml"
FILE_FIXTURE = "tests/fixtures/file-contracts/csv-downstream/app-definition.yaml"
ORDINARY_FIXTURE = "tests/fixtures/boot41-batch/ordinary-app-definition.yaml"
CASES = ("m5a", "ordinary", "file", "mixed")


def case_metadata(case: str, profile: str):
    if case not in CASES:
        raise ValueError(f"Unknown Batch proof case: {case}")
    fixture = (
        FILE_FIXTURE if case == "file" else ORDINARY_FIXTURE if case == "ordinary" else M5A_FIXTURE
    )
    metadata = build_metadata_project(fixture)
    if case == "mixed":
        file_metadata = build_metadata_project(FILE_FIXTURE)
        metadata.entities.extend(file_metadata.entities)
        metadata.contracts.extend(file_metadata.contracts)
        metadata.mappings.extend(file_metadata.mappings)
        metadata.operations.extend(file_metadata.operations)
    metadata.target_profile = profile
    return metadata
