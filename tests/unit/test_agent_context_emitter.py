"""Generated-output tests for the C1 agent-context.md emitter.

Covers: emission for the CRUD and passthrough lanes, the factual sections,
identity-role modes, rules applied-vs-metadata framing, deterministic
(byte-identical) regeneration, opt-in tool stubs off by default, README
enrichment, and existing-behavior regression.
"""

from __future__ import annotations

from pathlib import Path

from appbuilder.core import AppArchetype
from appbuilder.generation.build_emitter import (
    _render_agent_context,
    emit_build_files,
    emit_passthrough_build_files,
)
from appbuilder.mapping import (
    FieldMapping,
    MappingCompletenessReport,
    MappingDirection,
    MappingIssue,
    MappingSeverity,
)
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    ContractMetadata,
    HttpMethod,
    IdentityRole,
    IdentityRoleMetadata,
    IdentityRoleMode,
    MetadataProject,
    ResponseShape,
    RouteEntry,
    RoutingRule,
    SystemParticipant,
)
from appbuilder.rules.models import CanonicalRule, RuleType
from appbuilder.target_profiles.catalog import TARGET_PROFILES

_PROFILE = TARGET_PROFILES["springboot-legacy-compatible"]
_RUN_ID = "agent-context-test-run"
_MANIFEST = "tests/fixtures/agent-context/app-definition.yaml"


def _rich_metadata() -> MetadataProject:
    """A CRUD project exercising every agent-context section: upstream REST +
    downstream file + staging handoff, entities with an id, both identity-role
    modes, a rule, ingestion notes, and a translation warning."""
    return MetadataProject(
        app_name="Test Ledger App",
        bounded_context="ledger",
        target_profile="springboot-legacy-compatible",
        app_archetype=AppArchetype.CRUD,
        systems=[
            SystemParticipant(name="CoreUpstream", role="upstream"),
            SystemParticipant(name="OpsDownstream", role="downstream"),
            SystemParticipant(name="ETL", role="handoff"),
        ],
        contracts=[
            ContractMetadata(
                name="ledger-api",
                type="rest-json",
                source="contracts/ledger-openapi.yaml",
                ingestion_notes=["Sample field 'note' auto-included in canonical model"],
            ),
            ContractMetadata(
                name="settlement-file",
                type="file-fixed-width",
                source="downstream/settlement-layout.yaml",
            ),
            ContractMetadata(
                name="ledger-stage",
                type="staging-table",
                source="data-handoffs/ledger-stage.sql",
                physical_name="ledger_stage",
            ),
        ],
        operations=[
            CanonicalOperation(
                name="createEntry",
                interface_name="ledger-api",
                http_method=HttpMethod.POST,
                path="/entries",
                request_entity="Entry",
                response_entity="Entry",
                response_shape=ResponseShape.CREATED,
                has_request_body=True,
            ),
            CanonicalOperation(
                name="getEntry",
                interface_name="ledger-api",
                http_method=HttpMethod.GET,
                path="/entries/{id}",
                response_entity="Entry",
                response_shape=ResponseShape.SINGLE,
            ),
        ],
        entities=[
            CanonicalEntity(
                name="Entry",
                fields=[
                    CanonicalField(name="entryId", type=CanonicalFieldType.STRING, is_id=True),
                    CanonicalField(name="amount", type=CanonicalFieldType.DECIMAL),
                    CanonicalField(name="parentAccountId", type=CanonicalFieldType.STRING),
                    CanonicalField(name="status", type=CanonicalFieldType.STRING),
                ],
            ),
        ],
        mappings=[
            FieldMapping(
                contract_name="ledger-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                source_path="$.amount",
                target_path="Entry.amount",
            ),
            FieldMapping(
                contract_name="settlement-file",
                direction=MappingDirection.CANONICAL_TO_DOWNSTREAM,
                source_path="Entry.amount",
                target_path="AMOUNT",
            ),
            FieldMapping(
                contract_name="ledger-stage",
                direction=MappingDirection.CANONICAL_TO_HANDOFF,
                source_path="Entry.amount",
                target_path="amount",
            ),
        ],
        mapping_reports=[
            MappingCompletenessReport(
                contract_name="ledger-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                status="incomplete",
                issues=[
                    MappingIssue(
                        contract_name="ledger-api",
                        direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                        severity=MappingSeverity.WARNING,
                        message="Sample field 'memo' auto-included in canonical model",
                    )
                ],
            )
        ],
        rules=[
            CanonicalRule(
                entity_name="Entry",
                field_name="status",
                type=RuleType.ALLOWED_VALUES,
                source_path="rules.Entry.status.allowed-values",
                values=["OPEN", "CLOSED"],
            ),
        ],
        identity_roles=[
            IdentityRoleMetadata(
                entity="Entry",
                field="parentAccountId",
                role=IdentityRole.PARENT_REFERENCE,
                mode=IdentityRoleMode.ACTIVE,
            ),
            IdentityRoleMetadata(
                entity="Entry",
                field="entryId",
                role=IdentityRole.BUSINESS_KEY,
                mode=IdentityRoleMode.METADATA_ONLY,
            ),
        ],
        warnings=["Entry: ambiguous id-field inference; selected 'entryId' by source order"],
        staging_table_ddls={"ledger_stage": "CREATE TABLE ledger_stage (id VARCHAR(36));"},
    )


def _render(metadata: MetadataProject | None = None) -> str:
    return _render_agent_context(
        metadata=metadata or _rich_metadata(),
        target_profile=_PROFILE,
        source_manifest=_MANIFEST,
        generation_run_id=_RUN_ID,
        emit_test_console=True,
    )


def _adapter_only_metadata() -> MetadataProject:
    return MetadataProject(
        app_name="SOAP Adapter",
        bounded_context="soap_adapter",
        target_profile="springboot-legacy-compatible",
        app_archetype=AppArchetype.CRUD,
        contracts=[
            ContractMetadata(
                name="customer-soap",
                type="soap-wsdl",
                source="contracts/customer.wsdl",
            )
        ],
        entities=[],
    )


# --- emission + wiring -------------------------------------------------------

def test_emit_build_files_writes_agent_context(tmp_path: Path) -> None:
    files = emit_build_files(
        metadata=_rich_metadata(),
        target_profile=_PROFILE,
        output_dir=tmp_path,
        source_manifest=_MANIFEST,
        generation_run_id=_RUN_ID,
        emit_test_console=False,
    )
    agent_context = tmp_path / "agent-context.md"
    assert agent_context in files
    assert agent_context.exists()
    assert "Demo/live-data endpoints" not in agent_context.read_text(encoding="utf-8")


def test_passthrough_lane_also_emits_agent_context(tmp_path: Path) -> None:
    metadata = MetadataProject(
        app_name="Router App",
        bounded_context="router",
        target_profile="springboot-legacy-compatible",
        app_archetype=AppArchetype.PASSTHROUGH_ROUTER,
        systems=[
            SystemParticipant(name="Inbound", role="upstream"),
            SystemParticipant(name="TargetA", role="downstream"),
        ],
        contracts=[
            ContractMetadata(name="inbound-api", type="rest-json", source="contracts/in.yaml"),
        ],
        routing_rules=[
            RoutingRule(
                route_field="country",
                routes=[RouteEntry(match="US", target="TargetA")],
                default_target="TargetA",
            )
        ],
    )
    files = emit_passthrough_build_files(
        metadata=metadata,
        target_profile=_PROFILE,
        output_dir=tmp_path,
        source_manifest=_MANIFEST,
        generation_run_id=_RUN_ID,
    )
    agent_context = tmp_path / "agent-context.md"
    assert agent_context in files and agent_context.exists()
    body = agent_context.read_text(encoding="utf-8")
    # archetype-aware "where to add logic" target for passthrough
    assert "`passthrough-router`" in body
    assert "does **not** emit the CRUD `Service`/`ServiceBase` subclass seam" in body
    assert "new adopter-owned classes" in body


# --- sections present + factual ----------------------------------------------

def test_all_ten_sections_present() -> None:
    body = _render()
    for header in [
        "# Agent context — Test Ledger App",
        "## 2. What this app is",
        "## 3. Preserved contracts",
        "## 4. Canonical entities & identity roles",
        "## 5. Business rules",
        "## 6. Generation notes & caveats",
        "## 7. Downstream handoff topology",
        "## 8. Config & secrets",
        "## 9. Where to add business logic",
        "## 10. Provenance",
    ]:
        assert header in body, f"missing section: {header}"


def test_header_states_standalone() -> None:
    body = _render()
    assert "standalone" in body
    assert "no runtime dependency on EdgeForge" in body


def test_what_this_app_is_uses_metadata_facts() -> None:
    body = _render()
    assert "Archetype: `crud`" in body
    assert "Bounded context: `ledger`" in body
    assert "- `CoreUpstream` — role: upstream" in body
    assert "- `OpsDownstream` — role: downstream" in body
    assert "- `ETL` — role: handoff" in body


def test_contracts_classified_by_direction() -> None:
    body = _render()
    upstream_idx = body.index("### Upstream interfaces")
    downstream_idx = body.index("### Downstream interfaces")
    handoff_idx = body.index("### Data handoffs")
    # upstream REST interface + its operations
    assert "`ledger-api` (rest-json)" in body
    assert "POST /entries" in body
    assert "GET /entries/{id}" in body
    # downstream file under downstream, staging under handoffs (positional checks)
    assert downstream_idx < body.index("`settlement-file` (file-fixed-width)")
    assert handoff_idx < body.index("`ledger-stage` (staging-table")
    assert body.index("`settlement-file` (file-fixed-width)") < handoff_idx
    # the upstream contract appears in the upstream section, before downstream
    assert upstream_idx < body.index("`ledger-api` (rest-json)") < downstream_idx


def test_entities_and_id_marker() -> None:
    body = _render()
    assert "- **Entry**" in body
    assert "- `entryId`: string (id)" in body
    assert "- `amount`: decimal" in body
    # no invented business description — the field line is exactly name: type
    assert "customer" not in body.lower().split("## 2.")[0]  # header has no invented domain text


def test_identity_roles_show_modes() -> None:
    body = _render()
    # active = generated/enforced
    assert (
        "`Entry.parentAccountId`: parent_reference — mode: active (generated/enforced)"
        in body
    )
    # metadata_only = recorded, not enforced
    assert (
        "`Entry.entryId`: business_key — mode: metadata_only (recorded, not enforced)"
        in body
    )


def test_identity_roles_empty_states_none() -> None:
    metadata = _rich_metadata()
    metadata.identity_roles = []
    body = _render(metadata)
    assert "No reviewed non-persistence identity roles" in body


def test_rules_applied_section_lists_enforced_rules() -> None:
    body = _render()
    assert "### Applied (generated & enforced)" in body
    assert "`Entry.status`: allowed-values — allowed values: OPEN, CLOSED" in body
    # the metadata-only framing for rules is stated explicitly
    assert "metadata-only selections from authoring are not emitted as enforced rules" in body


def test_generation_notes_surface_ingestion_notes_warnings_and_mapping_issues() -> None:
    body = _render()
    assert "Ingestion notes:" in body
    assert "Sample field 'note' auto-included" in body
    # mapping_reports issues are surfaced (the DDA-style "auto-included field" caveat)
    assert "Mapping completeness notes:" in body
    assert "Sample field 'memo' auto-included in canonical model (warning)" in body
    assert "Translation warnings:" in body
    assert "ambiguous id-field inference" in body


def test_handoff_topology_lists_staging_ddl() -> None:
    body = _render()
    assert "handoff `ledger-stage` -> table `ledger_stage`" in body
    assert "staging-table DDL: `ledger_stage`" in body


def test_provenance_footer_matches_inputs() -> None:
    body = _render()
    assert "Source manifest: `app-definition.yaml`" in body
    assert "Target profile: `springboot-legacy-compatible`" in body
    assert f"Generation run: `{_RUN_ID}`" in body


def test_where_to_add_logic_states_crud_ownership_seam_and_protects_edges() -> None:
    body = _render()
    section = body.split("## 9. Where to add business logic")[1]
    assert "`src/main/java/.../service/{Entity}Service.java` is scaffolded once" in section
    assert "`src/main/java/.../service/{Entity}ServiceBase.java` is refreshed" in section
    assert "domain classes, repositories" in section
    assert "generated DTOs" in section
    assert "never rewrite an existing generated Flyway migration" in section
    assert "`EdgeForge-ownership: generated`" in section
    assert "`EdgeForge-ownership: developer`" in section


def test_adapter_only_guidance_does_not_advertise_missing_crud_service_seam(
    tmp_path: Path,
) -> None:
    metadata = _adapter_only_metadata()
    emit_build_files(
        metadata=metadata,
        target_profile=_PROFILE,
        output_dir=tmp_path,
        source_manifest=_MANIFEST,
        generation_run_id=_RUN_ID,
        emit_test_console=False,
    )
    agent_context = (tmp_path / "agent-context.md").read_text(encoding="utf-8")
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")

    for body in (readme, agent_context):
        assert "adapter-only application" in body
        assert "does not emit the CRUD `Service`/`ServiceBase` extension seam" in body
        assert "{Entity}Service.java` is scaffolded once" not in body
        assert "{Entity}ServiceBase.java` is" not in body
        assert "new developer-owned" in body
        assert "generated adapters" in body
        assert "Ownership" in body or "Authority" in body


# --- determinism -------------------------------------------------------------

def test_render_is_byte_identical_across_runs() -> None:
    assert _render() == _render()


def test_full_generation_is_byte_identical(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for out in (a, b):
        emit_build_files(
            metadata=_rich_metadata(),
            target_profile=_PROFILE,
            output_dir=out,
            source_manifest=_MANIFEST,
            generation_run_id=_RUN_ID,
            emit_test_console=False,
        )
    assert (a / "agent-context.md").read_text() == (b / "agent-context.md").read_text()


# --- opt-in tool stubs -------------------------------------------------------

def test_tool_stubs_off_by_default(tmp_path: Path) -> None:
    emit_build_files(
        metadata=_rich_metadata(),
        target_profile=_PROFILE,
        output_dir=tmp_path,
        source_manifest=_MANIFEST,
        generation_run_id=_RUN_ID,
        emit_test_console=False,
    )
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".github" / "copilot-instructions.md").exists()


def test_tool_stubs_emitted_only_when_opted_in(tmp_path: Path) -> None:
    files = emit_build_files(
        metadata=_rich_metadata(),
        target_profile=_PROFILE,
        output_dir=tmp_path,
        source_manifest=_MANIFEST,
        generation_run_id=_RUN_ID,
        emit_test_console=False,
        emit_tool_stubs=True,
    )
    claude = tmp_path / "CLAUDE.md"
    agents = tmp_path / "AGENTS.md"
    copilot = tmp_path / ".github" / "copilot-instructions.md"
    assert claude.exists() and agents.exists() and copilot.exists()
    assert {claude, agents, copilot}.issubset(set(files))
    # stubs are thin pointers to agent-context.md (correct relative link per location)
    assert "(agent-context.md)" in agents.read_text()
    assert "(../agent-context.md)" in copilot.read_text()


# --- README enrichment + regression -----------------------------------------

def test_readme_enriched_with_pointer(tmp_path: Path) -> None:
    emit_build_files(
        metadata=_rich_metadata(),
        target_profile=_PROFILE,
        output_dir=tmp_path,
        source_manifest=_MANIFEST,
        generation_run_id=_RUN_ID,
        emit_test_console=False,
    )
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "[`agent-context.md`](agent-context.md)" in readme
    assert "standalone" in readme
    # existing README behavior preserved (regression)
    assert "## Build" in readme
    assert "mvn clean package" in readme
    assert "## Preserved Contracts" in readme
    assert "## Ownership and regeneration" in readme
    assert "{Entity}Service.java` is scaffolded once" in readme
    assert "{Entity}ServiceBase.java` is marked `generated`" in readme
    assert "Domain classes, repositories, controllers/adapters" in readme
    assert "Ownership markers are authoritative" in readme


def test_build_files_unchanged_set_plus_agent_context(tmp_path: Path) -> None:
    files = emit_build_files(
        metadata=_rich_metadata(),
        target_profile=_PROFILE,
        output_dir=tmp_path,
        source_manifest=_MANIFEST,
        generation_run_id=_RUN_ID,
        emit_test_console=False,
    )
    names = {p.name for p in files}
    # all prior build files still emitted, plus the new doc
    assert {"pom.xml", "Dockerfile", "README.md", "application.yaml", "agent-context.md"}.issubset(names)
