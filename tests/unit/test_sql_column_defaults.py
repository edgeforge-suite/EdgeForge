from pathlib import Path

import pytest

from appbuilder.generation.sql_emitter import emit_sql_files
from appbuilder.metadata import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    MetadataProject,
)
from appbuilder.target_profiles.catalog import TARGET_PROFILES

# Other tests extend the shared catalog during collection; this matrix covers
# the three shipped profiles, not those temporary test-only registrations.
_SHIPPED_PROFILES = (
    "springboot-legacy-compatible",
    "springboot-enterprise-postgres-java17",
    "springboot-standard-enterprise",
)


@pytest.mark.parametrize("profile", _SHIPPED_PROFILES)
@pytest.mark.parametrize("required,not_null", [(False, False), (True, False), (False, True)])
def test_default_precedes_range_and_nullability_constraints(
    tmp_path: Path,
    profile: str,
    required: bool,
    not_null: bool,
) -> None:
    metadata = MetadataProject(
        app_name="Column Defaults",
        bounded_context="workspace",
        target_profile=profile,
        entities=[
            CanonicalEntity(
                name="Item",
                fields=[
                    CanonicalField(name="itemId", type=CanonicalFieldType.STRING, is_id=True),
                    CanonicalField(
                        name="priority",
                        type=CanonicalFieldType.INTEGER,
                        required=required,
                        not_null=not_null,
                        default_value="3",
                        range_min=1,
                        range_max=5,
                    ),
                ],
            )
        ],
    )
    files = emit_sql_files(
        metadata=metadata,
        target_profile=TARGET_PROFILES[profile],
        output_dir=tmp_path,
        source_manifest="synthetic-column-defaults",
        generation_run_id="column-defaults",
    )
    migration = files[0].read_text(encoding="utf-8")
    nullability = " NOT NULL" if required or not_null else ""
    assert (
        f"priority BIGINT DEFAULT 3{nullability} CHECK (priority >= 1 AND priority <= 5)"
        in migration
    )
    assert "item_id VARCHAR(36) PRIMARY KEY" in migration
