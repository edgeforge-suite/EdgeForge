"""Orchestration for the static compatibility harness."""

from __future__ import annotations

from pathlib import Path

from appbuilder.metadata.models import MetadataProject

from .checks import (
    check_downstream_file_field_order,
    check_flyway_columns_match_entity,
    check_no_appbuilder_runtime_imports,
    check_staging_table_required_columns_mapped,
    check_staging_table_run_identity_contract,
    check_upstream_dto_request_fields,
    check_upstream_dto_response_fields,
)
from .models import HarnessReport


def run_compatibility_harness(
    metadata: MetadataProject,
    output_dir: str | Path,
) -> HarnessReport:
    """Run all static compatibility checks against a generated app."""

    output_path = Path(output_dir)
    checks = [
        check_upstream_dto_request_fields(metadata, output_path),
        check_upstream_dto_response_fields(metadata, output_path),
        check_flyway_columns_match_entity(metadata, output_path),
        check_staging_table_required_columns_mapped(metadata, output_path),
        *check_staging_table_run_identity_contract(metadata, output_path),
        check_downstream_file_field_order(metadata, output_path),
        check_no_appbuilder_runtime_imports(metadata, output_path),
    ]
    return HarnessReport(output_dir=output_path, checks=checks)
