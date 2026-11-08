from __future__ import annotations

from pathlib import Path

import pytest

from appbuilder.contracts import load_project_definition
from appbuilder.generation import generate_application
from appbuilder.generation.java_emitter import _render_service
from appbuilder.generation.kafka_build_emitter import emit as emit_kafka_build_files
from appbuilder.generation.kafka_emitter import emit as emit_kafka_sources
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata import build_metadata_project
from appbuilder.metadata.kafka_translation import translate_kafka_project
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    IdGenerationStrategy,
    MetadataProject,
)
from appbuilder.target_profiles.catalog import TARGET_PROFILES

QUALITY_FIXTURES = Path("tests/fixtures/generated-app-quality")
ROUTER_FIXTURE = Path("tests/fixtures/kafka-router-contract")


def test_crud_quality_gate_transaction_identity_and_wrapper_exclusion(tmp_path: Path) -> None:
    manifest_path = QUALITY_FIXTURES / "transaction-identity-wrapper-valid/app-definition.yaml"
    metadata = build_metadata_project(manifest_path)
    transaction_entity = next(
        entity for entity in metadata.entities if entity.name == "TransactionHistory"
    )

    wrapper_fields = {"transactions", "currentPage", "pageSize", "totalElements", "totalPages"}
    assert not wrapper_fields.intersection({field.name for field in transaction_entity.fields})
    assert not any(
        mapping.target_path.rsplit(".", 1)[-1] in wrapper_fields
        for mapping in metadata.mappings
        if mapping.target_path and "eod" in mapping.contract_name.lower()
    )

    output_dir = tmp_path / "TransactionIdentityWrapper"
    with pytest.raises(ValueError, match="listTransactionsByAccount.*collection selection"):
        generate_application(metadata, output_dir, generation_run_id="quality-unsupported-filter")
    assert not output_dir.exists()
    # Identity/wrapper quality is independent of an unsupported owner query.
    operation = next(op for op in metadata.operations if op.name == "listTransactionsByAccount")
    operation.path = "/transaction-history"
    operation.path_parameters = []
    operation.read_input_errors = []
    generate_application(
        metadata,
        output_dir,
        source_manifest=manifest_path.as_posix(),
        generation_run_id="quality-gate-identity-wrapper",
    )

    base = output_dir / "src/main/java/com/appbuilder/bankingquality"
    entity_source = (base / "domain/TransactionHistory.java").read_text(encoding="utf-8")
    service_source = (base / "service/TransactionHistoryService.java").read_text(encoding="utf-8")
    writer_source = (
        base / "adapter/outbound/TransactionHistoryEodHandoffFileWriter.java"
    ).read_text(encoding="utf-8")
    response_dto_source = (
        base / "adapter/inbound/ListTransactionsByAccountResponse.java"
    ).read_text(encoding="utf-8")
    ddl_source = (
        output_dir / "src/main/resources/db/migration/V1__create_transaction_history_table.sql"
    ).read_text(encoding="utf-8")

    transaction_row_section = entity_source.split("private String transactionRowId;", 1)[0]
    account_section = entity_source.split("private String accountId;", 1)[0]
    transaction_id_section = entity_source.split("private String transactionId;", 1)[0]
    assert "@Id" in transaction_row_section
    assert '@Column(name = "transaction_row_id", length = 36, updatable = false)' in transaction_row_section
    assert "@Id" not in account_section.rsplit("/**", 1)[-1]
    assert "@Id" not in transaction_id_section.rsplit("/**", 1)[-1]

    for forbidden in [
        "currentPage",
        "pageSize",
        "totalElements",
        "totalPages",
        "private String transactions;",
    ]:
        assert forbidden not in entity_source
    for forbidden_column in [
        "current_page",
        "page_size",
        "total_elements",
        "total_pages",
        "transactions",
    ]:
        assert forbidden_column not in ddl_source

    assert "transaction_row_id VARCHAR(36) PRIMARY KEY" in ddl_source
    assert "account_id VARCHAR(255) NOT NULL" in ddl_source
    assert "transaction_id VARCHAR(255) NOT NULL" in ddl_source
    assert "getAccountId()" in writer_source
    assert "getTransactionId()" in writer_source
    assert "getCurrentPage()" not in writer_source
    assert "getTotalElements()" not in writer_source
    assert "private Long currentPage;" in response_dto_source
    assert "private Long totalElements;" in response_dto_source
    assert "private String transactions;" in response_dto_source
    assert "record.getCurrentPage()" not in service_source
    assert "record.getTotalElements()" not in service_source


def test_crud_quality_gate_create_with_caller_supplied_row_identity_rejects_duplicates() -> None:
    entity = CanonicalEntity(
        name="TransactionHistory",
        fields=[
            CanonicalField(
                name="transactionRowId",
                type=CanonicalFieldType.STRING,
                is_id=True,
                required=True,
                server_generated_id=False,
                id_generation_strategy=IdGenerationStrategy.CALLER_SUPPLIED,
            ),
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, required=True),
            CanonicalField(name="transactionId", type=CanonicalFieldType.STRING, required=True),
        ],
    )
    operation = CanonicalOperation(
        name="createTransactionHistory",
        interface_name="transaction-api",
        request_entity="TransactionHistory",
        response_entity="TransactionHistory",
    )
    metadata = MetadataProject(
        app_name="Transaction Quality",
        bounded_context="bankingquality",
        target_profile="springboot-legacy-compatible",
        operations=[operation],
        entities=[entity],
        mappings=[
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="transaction-api",
                operation_name="createTransactionHistory",
                source_path="transaction-api.createTransactionHistory.request.transactionRowId",
                target_path="TransactionHistory.transactionRowId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="transaction-api",
                operation_name="createTransactionHistory",
                source_path="transaction-api.createTransactionHistory.request.accountId",
                target_path="TransactionHistory.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="transaction-api",
                operation_name="createTransactionHistory",
                source_path="transaction-api.createTransactionHistory.request.transactionId",
                target_path="TransactionHistory.transactionId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="transaction-api",
                operation_name="createTransactionHistory",
                source_path="transaction-api.createTransactionHistory.response.transactionRowId",
                target_path="TransactionHistory.transactionRowId",
            ),
        ],
    )
    op_context = {
        "operation": operation,
        "java_operation_name": "createTransactionHistory",
        "request_class_name": "CreateTransactionHistoryRequest",
        "response_class_name": "CreateTransactionHistoryResponse",
        "request_field_mappings": metadata.mappings[:3],
        "response_field_mappings": metadata.mappings[3:],
    }

    service_source = _render_service(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.bankingquality",
        op_contexts=[op_context],
        id_java_type="String",
        target_profile=TARGET_PROFILES["springboot-legacy-compatible"],
        source_manifest="test",
        generation_run_id="quality-gate-duplicate-create",
    )

    create_body = service_source.split(
        "public CreateTransactionHistoryResponse createTransactionHistory", 1
    )[1]
    assert "@Id" not in create_body
    assert "transactionHistory.setTransactionRowId(request.getTransactionRowId());" in create_body
    assert (
        "transactionHistoryRepository.existsById(transactionHistory.getTransactionRowId())"
        in create_body
    )
    assert (
        'throw new DuplicateResourceException("TransactionHistory already exists with id: " '
        "+ transactionHistory.getTransactionRowId());"
    ) in create_body
    assert create_body.index("transactionHistoryRepository.existsById") < create_body.index(
        "transactionHistoryRepository.save(transactionHistory)"
    )
    assert "transactionHistory.setAccountId(request.getAccountId());" in create_body
    assert "transactionHistory.setTransactionId(request.getTransactionId());" in create_body


def test_crud_quality_gate_minor_units_dates_and_handoff_sources(tmp_path: Path) -> None:
    manifest_path = QUALITY_FIXTURES / "crud-minor-units-date/app-definition.yaml"
    metadata = build_metadata_project(manifest_path)
    output_dir = tmp_path / "CrudMinorUnitsDate"

    generate_application(
        metadata,
        output_dir,
        source_manifest=manifest_path.as_posix(),
        generation_run_id="quality-gate-minor-units-date",
    )

    base = output_dir / "src/main/java/com/appbuilder/minorunitsdate"
    entity_source = (base / "domain/Account.java").read_text(encoding="utf-8")
    request_dto_source = (
        base / "adapter/inbound/CreateAccountRequest.java"
    ).read_text(encoding="utf-8")
    response_dto_source = (
        base / "adapter/inbound/CreateAccountResponse.java"
    ).read_text(encoding="utf-8")
    file_writer_source = (
        base / "adapter/outbound/AccountEodHandoffFileWriter.java"
    ).read_text(encoding="utf-8")
    staging_writer_source = (base / "adapter/outbound/AccountStagingWriter.java").read_text(
        encoding="utf-8"
    )
    batch_job_source = (base / "batch/AccountEodBatchJob.java").read_text(encoding="utf-8")
    ddl_source = (
        output_dir / "src/main/resources/db/migration/V1__create_account_table.sql"
    ).read_text(encoding="utf-8")
    staging_ddl_source = (
        output_dir / "src/main/resources/db/migration/V2__create_account_staging_tbl_table.sql"
    ).read_text(encoding="utf-8")

    assert "import java.time.LocalDate;" in entity_source
    assert "private LocalDate openedDate;" in entity_source
    assert '@Column(name = "account_id", length = 36, updatable = false, nullable = false)' in entity_source
    assert "import java.time.LocalDate;" in request_dto_source
    assert "private LocalDate openedDate;" in request_dto_source
    assert "import java.time.LocalDate;" in response_dto_source
    assert "private LocalDate openedDate;" in response_dto_source
    assert "opened_date DATE NOT NULL" in ddl_source
    assert "opened_date VARCHAR" not in ddl_source
    assert "staging_row_id VARCHAR(36) NOT NULL PRIMARY KEY" in staging_ddl_source
    assert "run_id VARCHAR(64) NOT NULL" in staging_ddl_source
    assert "business_date DATE NOT NULL" in staging_ddl_source
    assert "opened_date DATE NOT NULL" in staging_ddl_source

    assert (
        "line.append(fixedWidthMinorUnitString(account.getAvailableBalance(), 14));"
        in file_writer_source
    )
    assert "value.movePointRight(2).toBigIntegerExact().toString()" in file_writer_source
    assert 'return "0".repeat(width - converted.length()) + converted;' in file_writer_source
    assert "Minor-unit value exceeds fixed width" in file_writer_source
    assert "leftZeroPad" not in file_writer_source
    assert "line.append(padRight(stringValue(account.getAvailableBalance()), 14));" not in file_writer_source
    assert "line.append(padRight(stringValue(account.getAccountNumber()), 12));" in file_writer_source
    assert "account.getOpenedDate()" in staging_writer_source
    assert "public void clear(String runId)" in staging_writer_source
    assert 'jdbcTemplate.update("DELETE FROM account_staging_tbl WHERE run_id = ?", runId);' in staging_writer_source
    assert 'jdbcTemplate.update("DELETE FROM account_staging_tbl");' not in staging_writer_source
    assert "UUID.randomUUID().toString()" in staging_writer_source
    assert "LocalDateTime.now()" in staging_writer_source
    assert "RepositoryItemReader<Account>" in batch_job_source
    assert ".<Account, Account>chunk(chunkSize, transactionManager)" in batch_job_source
    assert "java.util.List<Account> records = accountRepository.findAll();" not in batch_job_source
    assert "stagingWriter.clear(runId);" in batch_job_source
    assert "stagingWriter.clear();" not in batch_job_source
    assert 'stagingWriter.write(record, context.getString("runId"), LocalDate.parse(context.getString("businessDate")));' in batch_job_source
    assert ".next(accountEodFinalizeStep)" in batch_job_source
    assert "public Step accountEodFinalizeStep(" in batch_job_source
    assert "Files.move(tempFile, outputFile, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)" in batch_job_source
    assert "NO_RECORDS" in batch_job_source
    assert (base / "batch/AccountEodBatchJob.java").exists()


def test_crud_quality_gate_dto_list_contract_fidelity(tmp_path: Path) -> None:
    manifest_path = QUALITY_FIXTURES / "crud-dto-list-contract/app-definition.yaml"
    metadata = build_metadata_project(manifest_path)
    output_dir = tmp_path / "CrudDtoListContract"

    generate_application(
        metadata,
        output_dir,
        source_manifest=manifest_path.as_posix(),
        generation_run_id="quality-gate-dto-list",
    )

    base = output_dir / "src/main/java/com/appbuilder/crmdto"
    entity_source = (base / "domain/Customer.java").read_text(encoding="utf-8")
    controller_source = (base / "adapter/inbound/CustomerController.java").read_text(
        encoding="utf-8"
    )
    service_source = (base / "service/CustomerServiceBase.java").read_text(encoding="utf-8")
    list_request_source = (
        base / "adapter/inbound/ListCustomersRequest.java"
    ).read_text(encoding="utf-8")
    page_request_source = (
        base / "adapter/inbound/PageCustomersRequest.java"
    ).read_text(encoding="utf-8")
    ddl_source = (
        output_dir / "src/main/resources/db/migration/V1__create_customer_table.sql"
    ).read_text(encoding="utf-8")

    assert "customer_id VARCHAR(36) PRIMARY KEY" in ddl_source
    assert '@Column(name = "customer_id", length = 36, updatable = false)' in entity_source

    assert "public ResponseEntity<GetCustomerResponse> getById(" in controller_source
    assert "public GetCustomerResponse findById(String id)" in service_source
    assert "ResponseEntity<Customer> getById" not in controller_source
    assert "public Customer findById" not in service_source

    assert "public ResponseEntity<List<ListCustomersResponse>> listAll()" in controller_source
    assert "public List<ListCustomersResponse> findAll()" in service_source
    assert "List<Customer> records = customerRepository.findAll();" in service_source
    assert "accountRepository.findById" not in service_source
    assert "customerRepository.findById" not in service_source.split(
        "public List<ListCustomersResponse> findAll", 1
    )[1].split("public UpdateCustomerResponse", 1)[0]

    assert "public ResponseEntity<Page<PageCustomersResponse>> pageCustomers(" in controller_source
    assert "Pageable pageable = PageRequest.of(page, size);" in controller_source
    assert controller_source.count("private static final int MAX_PAGE_SIZE = 200;") == 1
    assert controller_source.count("private static final long MAX_PAGE_OFFSET = 50_000L;") == 1
    page_method = controller_source.split(
        "public ResponseEntity<Page<PageCustomersResponse>> pageCustomers", 1
    )[1]
    page_request = page_method.index("Pageable pageable = PageRequest.of(page, size);")
    size_guard = page_method.index("if (size > MAX_PAGE_SIZE)", page_request)
    offset_guard = page_method.index(
        "if (pageable.getOffset() > MAX_PAGE_OFFSET)", size_guard
    )
    service_call = page_method.index(
        "customerService.pageCustomers(pageable)", offset_guard
    )
    assert page_request < size_guard < offset_guard < service_call
    assert '"size must not exceed " + MAX_PAGE_SIZE' in page_method
    assert '"page offset must not exceed " + MAX_PAGE_OFFSET' in page_method
    assert "public Page<PageCustomersResponse> pageCustomers(Pageable pageable)" in service_source
    assert "return customerRepository.findAll(pageable).map(record -> {" in service_source

    assert "public ResponseEntity<UpdateCustomerResponse> updateCustomer(" in controller_source
    assert "@Valid @RequestBody UpdateCustomerRequest request" in controller_source
    assert "ResponseEntity<Customer> updateCustomer" not in controller_source
    assert "public UpdateCustomerResponse updateCustomer(String id, UpdateCustomerRequest request)" in service_source
    assert "Customer customer = customerRepository.findById(id)" in service_source
    assert "customer.setCustomerId(id);  // path id always takes precedence" in service_source
    assert "Customer saved = customerRepository.save(customer);" in service_source

    assert "private String customerId;" not in list_request_source
    assert "private String customerId;" not in page_request_source


def test_kafka_router_quality_gate_generated_output_regressions() -> None:
    definition = load_project_definition(ROUTER_FIXTURE / "manifest.yaml")
    metadata = translate_kafka_project(definition, project_root=ROUTER_FIXTURE)

    sources = emit_kafka_sources(metadata)
    build_files = emit_kafka_build_files(metadata)
    service = _source_named(sources, "RoutingService.java")
    request_listener = _source_named(sources, "RouterPatternListener.java")
    response_listener = _source_named(sources, "DownstreamResponseListener.java")
    validator = _source_named(sources, "RouterJsonSchemaValidator.java")
    transform_service = _source_named(sources, "RouterTransformService.java")

    register = service.index("registerCorrelation(correlationId, sourceSystem, replyDestination, target)")
    request_publish = service.index(
        "waitForPublish(record, \"Failed to publish router request to topic \" + target.requestTopic())"
    )
    request_cancel = service.index("correlationStore.cancel(correlationId);", request_publish)
    assert register < request_publish < request_cancel
    assert "catch (RouterTechnicalException" not in request_listener
    assert "catch (RouterBusinessException ex)" in request_listener

    response_record = service.index("ProducerRecord<String, Object> upstreamRecord = new ProducerRecord<>(")
    response_publish = service.index(
        "waitForPublish(upstreamRecord, \"Failed to publish router response to topic \" + record.getReplyDestination())"
    )
    response_complete = service.index("correlationStore.complete(correlationId)")
    assert response_record < response_publish < response_complete
    assert "routingService.handleDownstreamResponse(record.value(), toHeaderMap(record.headers()), record.topic())" in response_listener
    assert "schemaValidator.validate(payload, target.responseSchema(), \"V3\")" in service
    assert "schemaValidator.validate(upstreamPayload, OUTBOUND_SCHEMA, \"V4\")" in service
    assert "completeAndPublishResponseNack(record, \"V3_VALIDATION_FAILED\"" in service
    assert "completeAndPublishResponseNack(record, \"RESPONSE_TRANSFORM_FAILED\"" in service
    assert "completeAndPublishResponseNack(record, \"V4_VALIDATION_FAILED\"" in service
    nack_helper = service.index("private void completeAndPublishResponseNack(")
    nack_publish = service.index("nackPublisher.publishNack(", nack_helper)
    nack_complete = service.index("correlationStore.complete(record.getCorrelationId())", nack_helper)
    assert nack_publish < nack_complete
    assert "DeadLetter" not in service
    assert "DLQ" not in service

    absent_source = transform_service.index(
        "boolean hasSource = mapping.source() != null && input.containsKey(mapping.source());"
    )
    skip_absent = transform_service.index("if (value == null && !hasConstant && !hasSource)", absent_source)
    output_put = transform_service.index("output.put(mapping.target(), value);", skip_absent)
    assert skip_absent < output_put
    assert "continue;" in transform_service[skip_absent:output_put]

    assert "ConcurrentMap<String, Schema> schemaCache" in validator
    assert "schemaCache.computeIfAbsent(schemaRef, this::loadSchema)" in validator
    assert "SpecificationVersion.DRAFT_2020_12" in validator
    assert "private final JsonSchemaFactory schemaFactory" not in validator
    assert build_files["src/main/resources/schemas/ro-request.json"].startswith(
        '{\n  "$schema": "https://json-schema.org/draft/2020-12/schema"'
    )

    assert "catch (NumberFormatException ex)" in transform_service
    assert "catch (ArithmeticException ex)" in transform_service
    assert "catch (IllegalArgumentException ex)" in transform_service
    assert "RouterBusinessException.TransformMappingException" in transform_service

    missing_correlation = service.index("if (correlationId == null || correlationId.isBlank())")
    assert "\"MISSING_CORRELATION_ID\"" in service[missing_correlation:]
    assert "DuplicateCorrelationException(\"correlationId is required\")" not in _source_named(
        sources, "RoutingCorrelationStore.java"
    )
    assert "\"DUPLICATE_CORRELATION\"" in service


def _source_named(sources: dict[str, str], filename: str) -> str:
    matches = [source for path, source in sources.items() if path.endswith(filename)]
    assert len(matches) == 1
    return matches[0]
