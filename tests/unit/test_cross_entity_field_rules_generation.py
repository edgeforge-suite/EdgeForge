"""Generation tests for cross-entity field rule runtime enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from appbuilder.generation import generate_application
from appbuilder.generation.java_emitter import _render_service
from appbuilder.mapping import FieldMapping, MappingDirection
from appbuilder.metadata.models import (
    CanonicalEntity,
    CanonicalField,
    CanonicalFieldType,
    CanonicalOperation,
    ContractMetadata,
    HttpMethod,
    MetadataProject,
    PathParameter,
    ResponseShape,
    SystemParticipant,
)
from appbuilder.rules.models import CanonicalRule, RuleType
from appbuilder.target_profiles.catalog import TARGET_PROFILES, TargetProfile

_TEST_PROFILE_NAME = "springboot-cross-entity-generation-test"
if _TEST_PROFILE_NAME not in TARGET_PROFILES:
    TARGET_PROFILES[_TEST_PROFILE_NAME] = TargetProfile(
        name=_TEST_PROFILE_NAME,
        language="java",
        framework="spring-boot",
        java_baseline="17",
        spring_boot_baseline="3.3.5",
        emit_flyway=False,
        emit_spring_batch=False,
        emit_security=False,
        emit_audit=False,
        supports_xml=False,
    )


def _account_entity() -> CanonicalEntity:
    return CanonicalEntity(
        name="Account",
        fields=[
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="status", type=CanonicalFieldType.STRING),
            CanonicalField(name="availableBalance", type=CanonicalFieldType.DECIMAL),
        ],
    )


def _counterparty_entity() -> CanonicalEntity:
    return CanonicalEntity(
        name="Counterparty",
        fields=[
            CanonicalField(name="counterpartyId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="sanctionsStatus", type=CanonicalFieldType.STRING),
        ],
    )


def _transaction_entity() -> CanonicalEntity:
    return CanonicalEntity(
        name="Transaction",
        fields=[
            CanonicalField(name="transactionId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="accountId", type=CanonicalFieldType.STRING, required=True),
            CanonicalField(name="counterpartyId", type=CanonicalFieldType.STRING),
            CanonicalField(name="amount", type=CanonicalFieldType.DECIMAL),
            CanonicalField(name="status", type=CanonicalFieldType.STRING),
        ],
    )


def _transfer_entity() -> CanonicalEntity:
    return CanonicalEntity(
        name="Transfer",
        fields=[
            CanonicalField(name="transferId", type=CanonicalFieldType.STRING, is_id=True, required=True),
            CanonicalField(name="sourceAccountId", type=CanonicalFieldType.STRING, required=True),
            CanonicalField(name="destinationAccountId", type=CanonicalFieldType.STRING, required=True),
            CanonicalField(name="amount", type=CanonicalFieldType.DECIMAL),
        ],
    )


def _cross_entity_exists_rule(
    *,
    entity_name: str,
    field_name: str,
    target_entity: str,
) -> CanonicalRule:
    return CanonicalRule(
        entity_name=entity_name,
        field_name=field_name,
        type=RuleType.CROSS_ENTITY_EXISTS,
        source_path=f"rules.{entity_name}.{field_name}.cross-entity-exists",
        target_entity=target_entity,
    )


def _transaction_cross_entity_rules() -> list[CanonicalRule]:
    return [
        _cross_entity_exists_rule(
            entity_name="Transaction",
            field_name="accountId",
            target_entity="Account",
        ),
        _cross_entity_exists_rule(
            entity_name="Transaction",
            field_name="counterpartyId",
            target_entity="Counterparty",
        ),
        CanonicalRule(
            entity_name="Transaction",
            field_name="accountId",
            type=RuleType.CROSS_ENTITY_FIELD_CHECK,
            source_path="rules.Transaction.accountId.cross-entity-field-check",
            target_entity="Account",
            target_field="status",
            operator="eq",
            expected_value="ACTIVE",
            error_message="Account must be active",
        ),
        CanonicalRule(
            entity_name="Transaction",
            field_name="accountId",
            type=RuleType.CROSS_ENTITY_FIELD_COMPARE,
            source_path="rules.Transaction.accountId.cross-entity-field-compare",
            target_entity="Account",
            target_field="availableBalance",
            source_field="amount",
            operator="lte",
        ),
        CanonicalRule(
            entity_name="Transaction",
            field_name="counterpartyId",
            type=RuleType.CROSS_ENTITY_FIELD_IN,
            source_path="rules.Transaction.counterpartyId.cross-entity-field-in",
            target_entity="Counterparty",
            target_field="sanctionsStatus",
            values=["CLEARED", "PENDING_REVIEW"],
        ),
    ]


def _transfer_cross_entity_rules() -> list[CanonicalRule]:
    return [
        _cross_entity_exists_rule(
            entity_name="Transfer",
            field_name="sourceAccountId",
            target_entity="Account",
        ),
        _cross_entity_exists_rule(
            entity_name="Transfer",
            field_name="destinationAccountId",
            target_entity="Account",
        ),
        CanonicalRule(
            entity_name="Transfer",
            field_name="sourceAccountId",
            type=RuleType.CROSS_ENTITY_FIELD_CHECK,
            source_path="rules.Transfer.sourceAccountId.cross-entity-field-check",
            target_entity="Account",
            target_field="status",
            operator="eq",
            expected_value="ACTIVE",
        ),
        CanonicalRule(
            entity_name="Transfer",
            field_name="destinationAccountId",
            type=RuleType.CROSS_ENTITY_FIELD_CHECK,
            source_path="rules.Transfer.destinationAccountId.cross-entity-field-check",
            target_entity="Account",
            target_field="status",
            operator="eq",
            expected_value="ACTIVE",
        ),
    ]


def _create_ctx(entity_name: str) -> dict:
    entity_var = entity_name[:1].lower() + entity_name[1:]
    entity_id_name = f"{entity_var}Id"
    return {
        "operation_name": f"create{entity_name}",
        "java_operation_name": f"create{entity_name}",
        "request_class_name": f"Create{entity_name}Request",
        "response_class_name": f"Create{entity_name}Response",
        "path": f"/{entity_name.lower()}s",
        "spec_path": None,
        "request_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name=f"create{entity_name}",
                source_path=f"test-api.create{entity_name}.request.accountId",
                target_path=f"{entity_name}.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name=f"create{entity_name}",
                source_path=f"test-api.create{entity_name}.request.counterpartyId",
                target_path=f"{entity_name}.counterpartyId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name=f"create{entity_name}",
                source_path=f"test-api.create{entity_name}.request.amount",
                target_path=f"{entity_name}.amount",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name=f"create{entity_name}",
                source_path=f"test-api.create{entity_name}.request.status",
                target_path=f"{entity_name}.status",
            ),
        ],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name=f"create{entity_name}",
                source_path=f"test-api.create{entity_name}.response.{entity_id_name}",
                target_path=f"{entity_name}.{entity_id_name}",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name=f"create{entity_name}",
                source_path=f"test-api.create{entity_name}.response.status",
                target_path=f"{entity_name}.status",
            ),
        ],
        "http_method": HttpMethod.POST,
        "response_shape": ResponseShape.CREATED,
        "path_parameters": [],
        "operation_parameters": [],
    }


def _update_ctx() -> dict:
    return {
        "operation_name": "updateTransaction",
        "java_operation_name": "updateTransaction",
        "request_class_name": "UpdateTransactionRequest",
        "response_class_name": "UpdateTransactionResponse",
        "path": "/transactions/{id}",
        "spec_path": None,
        "request_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="updateTransaction",
                source_path="test-api.updateTransaction.request.accountId",
                target_path="Transaction.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="updateTransaction",
                source_path="test-api.updateTransaction.request.counterpartyId",
                target_path="Transaction.counterpartyId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="updateTransaction",
                source_path="test-api.updateTransaction.request.amount",
                target_path="Transaction.amount",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="updateTransaction",
                source_path="test-api.updateTransaction.request.status",
                target_path="Transaction.status",
            ),
        ],
        "response_field_mappings": [],
        "http_method": HttpMethod.PUT,
        "response_shape": ResponseShape.SINGLE,
        "path_parameters": [PathParameter(name="id", type="String")],
        "operation_parameters": [],
    }


def _state_transition_ctx() -> dict:
    return {
        "operation_name": "approveTransaction",
        "java_operation_name": "approveTransaction",
        "request_class_name": "ApproveTransactionRequest",
        "response_class_name": "ApproveTransactionResponse",
        "path": "/transactions/approve_transaction",
        "spec_path": None,
        "request_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="approveTransaction",
                source_path="test-api.approveTransaction.request.accountId",
                target_path="Transaction.accountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="approveTransaction",
                source_path="test-api.approveTransaction.request.counterpartyId",
                target_path="Transaction.counterpartyId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="approveTransaction",
                source_path="test-api.approveTransaction.request.amount",
                target_path="Transaction.amount",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="approveTransaction",
                source_path="test-api.approveTransaction.request.status",
                target_path="Transaction.status",
            ),
        ],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="approveTransaction",
                source_path="test-api.approveTransaction.response.status",
                target_path="Transaction.status",
            ),
        ],
        "http_method": HttpMethod.POST,
        "response_shape": ResponseShape.SINGLE,
        "path_parameters": [PathParameter(name="id", type="String")],
        "operation_parameters": [],
    }


def _transfer_create_ctx() -> dict:
    return {
        "operation_name": "createTransfer",
        "java_operation_name": "createTransfer",
        "request_class_name": "CreateTransferRequest",
        "response_class_name": "CreateTransferResponse",
        "path": "/transfers",
        "spec_path": None,
        "request_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="createTransfer",
                source_path="test-api.createTransfer.request.sourceAccountId",
                target_path="Transfer.sourceAccountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="createTransfer",
                source_path="test-api.createTransfer.request.destinationAccountId",
                target_path="Transfer.destinationAccountId",
            ),
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="createTransfer",
                source_path="test-api.createTransfer.request.amount",
                target_path="Transfer.amount",
            ),
        ],
        "response_field_mappings": [
            FieldMapping(
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                contract_name="test-api",
                operation_name="createTransfer",
                source_path="test-api.createTransfer.response.transferId",
                target_path="Transfer.transferId",
            ),
        ],
        "http_method": HttpMethod.POST,
        "response_shape": ResponseShape.CREATED,
        "path_parameters": [],
        "operation_parameters": [],
    }


def _transaction_metadata(
    *,
    rules: list[CanonicalRule],
    operations: list[CanonicalOperation] | None = None,
    mappings: list[FieldMapping] | None = None,
) -> MetadataProject:
    if operations is None:
        operations = [
            CanonicalOperation(
                name="createAccount",
                interface_name="test-api",
                request_entity="Account",
                response_entity="Account",
                http_method=HttpMethod.POST,
                path="/accounts",
                has_request_body=True,
                response_shape=ResponseShape.CREATED,
            ),
            CanonicalOperation(
                name="createCounterparty",
                interface_name="test-api",
                request_entity="Counterparty",
                response_entity="Counterparty",
                http_method=HttpMethod.POST,
                path="/counterparties",
                has_request_body=True,
                response_shape=ResponseShape.CREATED,
            ),
            CanonicalOperation(
                name="createTransaction",
                interface_name="test-api",
                request_entity="Transaction",
                response_entity="Transaction",
                http_method=HttpMethod.POST,
                path="/transactions",
                has_request_body=True,
                response_shape=ResponseShape.CREATED,
            )
        ]
    if mappings is None:
        mappings = [
            FieldMapping(
                contract_name="test-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createAccount",
                source_path="test-api.createAccount.response.accountId",
                target_path="Account.accountId",
            ),
            FieldMapping(
                contract_name="test-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createCounterparty",
                source_path="test-api.createCounterparty.response.counterpartyId",
                target_path="Counterparty.counterpartyId",
            ),
            FieldMapping(
                contract_name="test-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createTransaction",
                source_path="test-api.createTransaction.response.transactionId",
                target_path="Transaction.transactionId",
            ),
            FieldMapping(
                contract_name="test-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createTransaction",
                source_path="test-api.createTransaction.request.accountId",
                target_path="Transaction.accountId",
            ),
            FieldMapping(
                contract_name="test-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createTransaction",
                source_path="test-api.createTransaction.request.counterpartyId",
                target_path="Transaction.counterpartyId",
            ),
            FieldMapping(
                contract_name="test-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createTransaction",
                source_path="test-api.createTransaction.request.amount",
                target_path="Transaction.amount",
            ),
        ]
    return MetadataProject(
        app_name="Transaction App",
        bounded_context="payments",
        target_profile=_TEST_PROFILE_NAME,
        systems=[SystemParticipant(name="test-api", role="upstream")],
        contracts=[ContractMetadata(name="test-api", type="rest-json", source="test-api-spec.json")],
        operations=operations,
        entities=[_account_entity(), _counterparty_entity(), _transaction_entity()],
        mappings=mappings,
        rules=rules,
    )


def _service_source(
    *,
    metadata: MetadataProject,
    entity: CanonicalEntity,
    op_contexts: list[dict],
) -> str:
    return _render_service(
        metadata=metadata,
        entity=entity,
        root_package="com.appbuilder.payments",
        op_contexts=op_contexts,
        id_java_type="String",
        target_profile=TARGET_PROFILES[_TEST_PROFILE_NAME],
        source_manifest="test-manifest.yaml",
        generation_run_id="cross-entity-generation-test",
    )


def _method_slice(source: str, signature: str, end_marker: str) -> str:
    start = source.index(signature)
    end = source.index(end_marker, start)
    return source[start:end]


def test_generate_application_emits_business_rule_exception_and_422_handler(tmp_path: Path) -> None:
    metadata = _transaction_metadata(rules=_transaction_cross_entity_rules())

    generate_application(
        metadata=metadata,
        output_dir=tmp_path,
        source_manifest="test-manifest.yaml",
        generation_run_id="cross-entity-exception-test",
    )

    exception_dir = tmp_path / "src/main/java/com/appbuilder/payments/exception"
    business_rule_source = (exception_dir / "BusinessRuleException.java").read_text(encoding="utf-8")
    handler_source = (exception_dir / "GlobalExceptionHandler.java").read_text(encoding="utf-8")

    assert "class BusinessRuleException extends RuntimeException" in business_rule_source
    assert "@ExceptionHandler(BusinessRuleException.class)" in handler_source
    assert "HttpStatus.UNPROCESSABLE_ENTITY" in handler_source
    assert '"Unprocessable Entity"' in handler_source
    assert "@ExceptionHandler(IllegalArgumentException.class)" in handler_source
    assert "HttpStatus.BAD_REQUEST" in handler_source
    assert "@ExceptionHandler(ResourceNotFoundException.class)" in handler_source
    assert "HttpStatus.NOT_FOUND" in handler_source


def test_create_operation_emits_deduplicated_find_by_id_checks_and_messages() -> None:
    metadata = _transaction_metadata(rules=_transaction_cross_entity_rules())
    service = _service_source(
        metadata=metadata,
        entity=_transaction_entity(),
        op_contexts=[_create_ctx("Transaction")],
    )

    create_method = _method_slice(
        service,
        "public CreateTransactionResponse createTransaction(CreateTransactionRequest request) {",
        "        applyBusinessRules(transaction);",
    )

    assert service.count("import com.appbuilder.payments.domain.Account;") == 1
    assert service.count("import com.appbuilder.payments.domain.Counterparty;") == 1
    assert service.count("protected AccountRepository accountRepository;") == 1
    assert service.count("protected CounterpartyRepository counterpartyRepository;") == 1
    assert create_method.count("accountRepository.findById(transaction.getAccountId())") == 1
    assert create_method.count("counterpartyRepository.findById(transaction.getCounterpartyId())") == 1
    assert "throw new BusinessRuleException(\"Account must be active\");" in create_method
    assert (
        'throw new BusinessRuleException("Account availableBalance does not satisfy rule for '
        'Transaction.accountId");'
    ) in create_method
    assert (
        'throw new BusinessRuleException("Counterparty sanctionsStatus does not satisfy rule for '
        'Transaction.counterpartyId");'
    ) in create_method
    assert "account.getStatus() == null || !(account.getStatus().compareTo(\"ACTIVE\") == 0)" in create_method
    assert (
        "transaction.getAmount() == null || account.getAvailableBalance() == null || "
        "!(transaction.getAmount().compareTo(account.getAvailableBalance()) <= 0)"
    ) in create_method
    assert (
        "counterparty.getSanctionsStatus() == null || "
        '!List.of("CLEARED", "PENDING_REVIEW").contains(counterparty.getSanctionsStatus())'
    ) in create_method


def test_update_dto_path_emits_cross_entity_checks_before_apply_business_rules() -> None:
    metadata = _transaction_metadata(rules=_transaction_cross_entity_rules())
    service = _service_source(
        metadata=metadata,
        entity=_transaction_entity(),
        op_contexts=[_create_ctx("Transaction"), _update_ctx()],
    )

    update_method = _method_slice(
        service,
        "public Transaction updateTransaction(String id, UpdateTransactionRequest request) {",
        "        afterUpdate(saved);",
    )
    assert "accountRepository.findById(transaction.getAccountId())" in update_method
    assert "counterpartyRepository.findById(transaction.getCounterpartyId())" in update_method
    assert update_method.index("accountRepository.findById(transaction.getAccountId())") < update_method.index(
        "applyBusinessRules(transaction);"
    )


def test_update_generic_path_emits_cross_entity_checks_before_apply_business_rules_and_not_delete() -> None:
    metadata = _transaction_metadata(rules=_transaction_cross_entity_rules())
    service = _service_source(
        metadata=metadata,
        entity=_transaction_entity(),
        op_contexts=[_create_ctx("Transaction")],
    )

    update_method = _method_slice(
        service,
        "public TransactionResponse update(String id, TransactionUpdateRequest request) {",
        "        return transactionResponse;",
    )
    delete_method = _method_slice(
        service,
        "public void delete(String id) {",
        "        transactionRepository.deleteById(id);",
    )

    assert "accountRepository.findById(transaction.getAccountId())" in update_method
    assert "counterpartyRepository.findById(transaction.getCounterpartyId())" in update_method
    assert update_method.index("accountRepository.findById(transaction.getAccountId())") < update_method.index(
        "applyBusinessRules(transaction);"
    )
    assert "BusinessRuleException" not in delete_method
    assert "accountRepository.findById" not in delete_method
    assert "counterpartyRepository.findById" not in delete_method


def test_state_transition_path_emits_cross_entity_checks_before_apply_business_rules() -> None:
    metadata = _transaction_metadata(rules=_transaction_cross_entity_rules())
    service = _service_source(
        metadata=metadata,
        entity=_transaction_entity(),
        op_contexts=[_create_ctx("Transaction"), _state_transition_ctx()],
    )

    transition_method = _method_slice(
        service,
        "public ApproveTransactionResponse approveTransaction(String id, ApproveTransactionRequest request) {",
        "        Transaction saved = transactionRepository.save(transaction);",
    )
    assert "accountRepository.findById(transaction.getAccountId())" in transition_method
    assert "counterpartyRepository.findById(transaction.getCounterpartyId())" in transition_method
    assert transition_method.index("accountRepository.findById(transaction.getAccountId())") < transition_method.index(
        "applyBusinessRules(transaction);"
    )


def test_same_target_entity_different_fk_fields_emit_two_find_by_id_calls_but_one_repository_injection() -> None:
    metadata = MetadataProject(
        app_name="Transfer App",
        bounded_context="payments",
        target_profile=_TEST_PROFILE_NAME,
        systems=[SystemParticipant(name="test-api", role="upstream")],
        contracts=[ContractMetadata(name="test-api", type="rest-json", source="test-api-spec.json")],
        operations=[
            CanonicalOperation(
                name="createTransfer",
                interface_name="test-api",
                request_entity="Transfer",
                response_entity="Transfer",
                http_method=HttpMethod.POST,
                path="/transfers",
                has_request_body=True,
                response_shape=ResponseShape.CREATED,
            )
        ],
        entities=[_account_entity(), _transfer_entity()],
        mappings=[
            FieldMapping(
                contract_name="test-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createTransfer",
                source_path="test-api.createTransfer.response.transferId",
                target_path="Transfer.transferId",
            ),
            FieldMapping(
                contract_name="test-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createTransfer",
                source_path="test-api.createTransfer.request.sourceAccountId",
                target_path="Transfer.sourceAccountId",
            ),
            FieldMapping(
                contract_name="test-api",
                direction=MappingDirection.UPSTREAM_TO_CANONICAL,
                operation_name="createTransfer",
                source_path="test-api.createTransfer.request.destinationAccountId",
                target_path="Transfer.destinationAccountId",
            ),
        ],
        rules=_transfer_cross_entity_rules(),
    )

    service = _render_service(
        metadata=metadata,
        entity=_transfer_entity(),
        root_package="com.appbuilder.payments",
        op_contexts=[_transfer_create_ctx()],
        id_java_type="String",
        target_profile=TARGET_PROFILES[_TEST_PROFILE_NAME],
        source_manifest="test-manifest.yaml",
        generation_run_id="cross-entity-generation-test",
    )

    create_method = _method_slice(
        service,
        "public CreateTransferResponse createTransfer(CreateTransferRequest request) {",
        "        applyBusinessRules(transfer);",
    )
    assert service.count("protected AccountRepository accountRepository;") == 1
    assert service.count("import com.appbuilder.payments.domain.Account;") == 1
    assert create_method.count("accountRepository.findById(transfer.getSourceAccountId())") == 1
    assert create_method.count("accountRepository.findById(transfer.getDestinationAccountId())") == 1


def test_datetime_expected_value_with_z_emits_offset_datetime_parse() -> None:
    metadata = _transaction_metadata(
        rules=[
            _cross_entity_exists_rule(
                entity_name="Transaction",
                field_name="accountId",
                target_entity="Account",
            ),
            CanonicalRule(
                entity_name="Transaction",
                field_name="accountId",
                type=RuleType.CROSS_ENTITY_FIELD_CHECK,
                source_path="rules.Transaction.accountId.cross-entity-field-check",
                target_entity="Account",
                target_field="openedAt",
                operator="eq",
                expected_value="2026-04-22T10:15:30Z",
            ),
        ],
    )
    account = next(entity for entity in metadata.entities if entity.name == "Account")
    account.fields.append(
        CanonicalField(name="openedAt", type=CanonicalFieldType.DATETIME)
    )

    service = _service_source(
        metadata=metadata,
        entity=_transaction_entity(),
        op_contexts=[_create_ctx("Transaction")],
    )

    assert (
        'java.time.OffsetDateTime.parse("2026-04-22T10:15:30Z").toLocalDateTime()'
        in service
    )


def test_date_expected_value_fails_closed_for_injection_payload() -> None:
    metadata = _transaction_metadata(
        rules=[
            _cross_entity_exists_rule(
                entity_name="Transaction",
                field_name="accountId",
                target_entity="Account",
            ),
            CanonicalRule(
                entity_name="Transaction",
                field_name="accountId",
                type=RuleType.CROSS_ENTITY_FIELD_CHECK,
                source_path="rules.Transaction.accountId.cross-entity-field-check",
                target_entity="Account",
                target_field="openedOn",
                operator="eq",
                expected_value='2026-04-22"); evil();//',
            ),
        ],
    )
    account = next(entity for entity in metadata.entities if entity.name == "Account")
    account.fields.append(CanonicalField(name="openedOn", type=CanonicalFieldType.DATE))

    with pytest.raises(ValueError, match="not compatible"):
        _service_source(
            metadata=metadata,
            entity=_transaction_entity(),
            op_contexts=[_create_ctx("Transaction")],
        )
