
from pathlib import Path
from textwrap import dedent

import yaml

from appbuilder.contracts import load_project_definition
from appbuilder.generation import generate_application
from appbuilder.metadata import translate_project


def test_happy_path_xyz_accounts(tmp_path):
    """
    Full pipeline: load manifest -> translate metadata -> generate app -> run harness.
    All harness checks must pass.
    """

    project = load_project_definition(
        "examples/input-projects/xyz-accounts-modernization/app-definition.yaml"
    )
    metadata = translate_project(project)
    report = generate_application(
        metadata,
        tmp_path / "BuiltApp1",
        source_manifest="examples/input-projects/xyz-accounts-modernization/app-definition.yaml",
        generation_run_id="e2e-test",
    )

    assert report.harness_report is not None
    assert report.harness_report.passed, (
        f"Harness failed with errors: {[check.message for check in report.harness_report.errors]}"
    )


def test_happy_path_loans_modernization(tmp_path):
    """
    Second project proof: loans-modernization must generate and pass harness
    without any accounts-specific assumptions in the engine.
    """

    project = load_project_definition(
        "examples/input-projects/loans-modernization/app-definition.yaml"
    )
    metadata = translate_project(project)
    report = generate_application(
        metadata,
        tmp_path / "BuiltApp2",
        source_manifest="examples/input-projects/loans-modernization/app-definition.yaml",
        generation_run_id="loans-e2e-test",
    )

    assert report.harness_report is not None
    assert report.harness_report.passed, (
        f"Harness failed with errors: {[check.message for check in report.harness_report.errors]}"
    )
    assert (tmp_path / "BuiltApp2" / "pom.xml").exists()
    assert (tmp_path / "BuiltApp2" / "src" / "main" / "java").exists()


def test_crud_generation_preserves_legacy_nested_ref_and_all_of_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = tmp_path / "nested-crud-input"
    upstream = package / "upstream"
    upstream.mkdir(parents=True)
    manifest = package / "app-definition.yaml"
    manifest.write_text(
        dedent(
            """\
            app_name: Nested CRUD Compatibility
            bounded_context: nestedcrud
            schema_version: "2.0"
            app_archetype: crud
            upstream_interfaces:
              - name: customer-api
                system: CRM
                type: rest-json
                version: v1
                spec_url: https://example.invalid/customer-openapi.yaml
            target_profile: springboot-enterprise-postgres-java17
            """
        ),
        encoding="utf-8",
    )
    spec_path = upstream / "customer-openapi.yaml"
    spec_path.write_text(
        dedent(
            """\
            openapi: 3.1.0
            info:
              title: Nested CRUD Compatibility API
              version: "1.0"
            paths:
              /customers/{id}:
                get:
                  operationId: getCustomer
                  parameters:
                    - name: id
                      in: path
                      required: true
                      schema:
                        type: string
                  responses:
                    "200":
                      description: Customer
                      content:
                        application/json:
                          schema:
                            $ref: "#/components/schemas/Customer"
            components:
              schemas:
                Street:
                  type: string
                  maxLength: 12
                PreferenceCode:
                  allOf:
                    - type: string
                      maxLength: 20
                    - maxLength: 6
                Customer:
                  type: object
                  required: [id, address, preferences]
                  properties:
                    id:
                      type: string
                    address:
                      type: object
                      required: [street]
                      properties:
                        street:
                          $ref: "#/components/schemas/Street"
                    preferences:
                      type: object
                      required: [code]
                      properties:
                        code:
                          allOf:
                            - $ref: "#/components/schemas/PreferenceCode"
            """
        ),
        encoding="utf-8",
    )
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        "appbuilder.metadata.translation.fetch_openapi_spec",
        lambda _url: spec,
    )

    project = load_project_definition(manifest)
    metadata = translate_project(project)
    customer = next(entity for entity in metadata.entities if entity.name == "Customer")
    fields = {field.name: field for field in customer.fields}
    assert list(fields) == ["id", "preferencesCode"]
    assert fields["preferencesCode"].max_length is None

    output = tmp_path / "nested-crud-output"
    generate_application(
        metadata,
        output,
        source_manifest=str(manifest),
        generation_run_id="nested-crud-compatibility",
    )

    generated_java = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(output.rglob("*.java"))
    )
    assert "addressStreet" not in generated_java
    assert "preferencesCode" in generated_java
    assert "@CodePointLength(max=6)" not in generated_java


def test_happy_path_workspace_items(tmp_path):
    """
    Independent Workspace/Item example: two-entity bounded context.
    Verifies that multi-entity generation produces separate controllers, services,
    domain classes, repositories, and versioned Flyway migrations, and that all
    harness checks pass with no contract compatibility regressions.
    """

    project = load_project_definition(
        "examples/input-projects/workspace-items/app-definition.yaml"
    )
    metadata = translate_project(project)

    # Two entities must be extracted from the input package
    entity_names = {e.name for e in metadata.entities}
    assert "Workspace" in entity_names, f"Expected Workspace entity, got {entity_names}"
    assert "Item" in entity_names, f"Expected Item entity, got {entity_names}"

    report = generate_application(
        metadata,
        tmp_path / "WorkspaceItems",
        source_manifest="examples/input-projects/workspace-items/app-definition.yaml",
        generation_run_id="workspace-e2e-test",
    )

    out = tmp_path / "WorkspaceItems"

    # Harness must pass cleanly
    assert report.harness_report is not None
    assert report.harness_report.passed, (
        f"Harness failed: {[check.message for check in report.harness_report.errors]}"
    )

    # Build scaffold
    assert (out / "pom.xml").exists()
    assert (out / "Dockerfile").exists()

    java_root = out / "src" / "main" / "java" / "com" / "appbuilder" / "workspace"

    # Separate domain classes
    assert (java_root / "domain" / "Workspace.java").exists()
    assert (java_root / "domain" / "Item.java").exists()

    # Separate controllers
    assert (java_root / "adapter" / "inbound" / "WorkspaceController.java").exists()
    assert (java_root / "adapter" / "inbound" / "ItemController.java").exists()

    # Separate services and repositories
    assert (java_root / "service" / "WorkspaceService.java").exists()
    assert (java_root / "service" / "ItemService.java").exists()
    assert (java_root / "repository" / "WorkspaceRepository.java").exists()
    assert (java_root / "repository" / "ItemRepository.java").exists()

    # Versioned Flyway migrations — one per entity
    migrations = out / "src" / "main" / "resources" / "db" / "migration"
    assert (migrations / "V1__create_workspace_table.sql").exists()
    assert (migrations / "V2__create_item_table.sql").exists()

    # The independent example retains default-value migration coverage.
    workspace_sql = (migrations / "V1__create_workspace_table.sql").read_text()
    assert "state" in workspace_sql
    assert "OPEN" in workspace_sql

    item_sql = (migrations / "V2__create_item_table.sql").read_text()
    assert "priority" in item_sql
    assert "DEFAULT 3" in item_sql
    assert "REFERENCES workspace(workspace_id)" in item_sql

    # Request DTOs preserve upstream contract fields
    workspace_req = (java_root / "adapter" / "inbound" / "CreateWorkspaceRequest.java").read_text()
    for field in ("title", "state"):
        assert field in workspace_req, f"Missing field {field} in CreateWorkspaceRequest"
    assert "workspaceId" not in workspace_req
    assert "@CodePointLength(min=3, max=40)" in workspace_req

    item_req = (java_root / "adapter" / "inbound" / "CreateItemRequest.java").read_text()
    for field in ("workspaceId", "label", "priority"):
        assert field in item_req, f"Missing field {field} in CreateItemRequest"
    assert "itemId" not in item_req
    assert "@CodePointLength(min=2, max=60)" in item_req

    # Demo UI must include both entity forms
    index_html = (out / "src" / "main" / "resources" / "static" / "index.html").read_text()
    assert "createWorkspace" in index_html
    assert "createItem" in index_html


def test_happy_path_country_router_passthrough(tmp_path):
    """
    Passthrough-router proof: load manifest -> translate metadata -> generate app.
    This archetype intentionally skips the CRUD compatibility harness, but the
    end-to-end manifest path must still emit a standalone Spring Boot router app
    with the expected routing/transform/build scaffold and without persistence files.
    """

    project = load_project_definition(
        "examples/input-projects/country-router/app-definition.yaml"
    )
    metadata = translate_project(project)

    report = generate_application(
        metadata,
        tmp_path / "CountryRouter",
        source_manifest="examples/input-projects/country-router/app-definition.yaml",
        generation_run_id="country-router-e2e-test",
    )

    out = tmp_path / "CountryRouter"

    assert report.files_created
    assert report.harness_report is None
    assert report.warnings == []

    assert (out / "pom.xml").exists()
    assert (out / "Dockerfile").exists()
    assert (out / "README.md").exists()
    assert (out / "src" / "main" / "resources" / "application.yaml").exists()

    java_root = out / "src" / "main" / "java" / "com" / "appbuilder" / "payments"
    assert (java_root / "CountryRouterApplication.java").exists()
    assert (java_root / "controller" / "InboundController.java").exists()
    assert (java_root / "service" / "TransformService.java").exists()
    assert (java_root / "service" / "RoutingService.java").exists()
    assert (java_root / "dto" / "InboundRequestDto.java").exists()
    assert (java_root / "dto" / "InboundResponseDto.java").exists()
    assert (java_root / "dto" / "OutboundRequestDto.java").exists()
    assert (java_root / "dto" / "OutboundResponseDto.java").exists()
    assert (java_root / "client" / "AppAClient.java").exists()
    assert (java_root / "client" / "AppBClient.java").exists()
    assert (java_root / "client" / "AppCClient.java").exists()

    assert not list(out.rglob("*Entity.java"))
    assert not list(out.rglob("*Repository.java"))
    assert not (out / "src" / "main" / "resources" / "db" / "migration").exists()

    readme = (out / "README.md").read_text(encoding="utf-8")
    application_yaml = (
        out / "src" / "main" / "resources" / "application.yaml"
    ).read_text(encoding="utf-8")
    routing_service = (
        java_root / "service" / "RoutingService.java"
    ).read_text(encoding="utf-8")

    assert "passthrough-router" in readme
    assert "APP_A" in readme
    assert "APP_B" in readme
    assert "APP_C" in readme
    assert "downstream:" in application_yaml
    assert "app-a:" in application_yaml
    assert "app-b:" in application_yaml
    assert "app-c:" in application_yaml
    assert "countryCode" in routing_service
    assert "\"US\"" in routing_service
    assert "\"GB\"" in routing_service


def test_translation_only_obie_wire_transfer_excludes_envelope_fields():
    project = load_project_definition(
        "examples/input-projects/obie-wire-transfer/app-definition.yaml"
    )
    metadata = translate_project(project)

    entity = next(entity for entity in metadata.entities if entity.name == "InternationalPayment")
    field_names = {field.name for field in entity.fields}

    assert "Data" not in field_names
    assert "Links" not in field_names
    assert "Meta" not in field_names
    assert "ConsentId" in field_names
    assert "Status" in field_names
    assert "consentId" not in field_names
    assert "status" not in field_names

def test_obie_wire_transfer_generation_initializes_server_set_status(tmp_path):
    project = load_project_definition(
        "examples/input-projects/obie-wire-transfer/app-definition.yaml"
    )
    metadata = translate_project(project)

    report = generate_application(
        metadata,
        tmp_path / "ObieWireTransfer",
        source_manifest="examples/input-projects/obie-wire-transfer/app-definition.yaml",
        generation_run_id="obie-generation-test",
    )

    java_root = tmp_path / "ObieWireTransfer" / "src" / "main" / "java" / "com" / "appbuilder" / "wire_transfer"
    entity_source = (
        java_root / "domain" / "InternationalPayment.java"
    ).read_text(encoding="utf-8")
    service_source = (
        java_root / "service" / "InternationalPaymentServiceBase.java"
    ).read_text(encoding="utf-8")

    assert report.files_created
    assert "@PrePersist" in entity_source
    assert 'this.Status = "AcceptedSettlementInProcess";' in entity_source
    assert 'this.StatusUpdateDateTime = LocalDateTime.now();' in entity_source
    assert (
        "// Server-set fields (status, etc.) are initialized via @PrePersist on the entity."
        in service_source
    )


def test_obie_wire_transfer_generation_preserves_spec_routes(tmp_path):
    project = load_project_definition(
        "examples/input-projects/obie-wire-transfer/app-definition.yaml"
    )
    metadata = translate_project(project)

    generate_application(
        metadata,
        tmp_path / "ObieWireTransferRoutes",
        source_manifest="examples/input-projects/obie-wire-transfer/app-definition.yaml",
        generation_run_id="obie-route-test",
    )

    controller_source = (
        tmp_path
        / "ObieWireTransferRoutes"
        / "src"
        / "main"
        / "java"
        / "com"
        / "appbuilder"
        / "wire_transfer"
        / "adapter"
        / "inbound"
        / "InternationalPaymentController.java"
    ).read_text(encoding="utf-8")

    assert "/international-payments" in controller_source
    assert "/international_payments" not in controller_source
    assert "InternationalPaymentId" in controller_source
    assert '@GetMapping("/{InternationalPaymentId}")' in controller_source
    assert '@PathVariable("InternationalPaymentId") String internationalPaymentId' in controller_source
