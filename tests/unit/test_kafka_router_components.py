import json
from pathlib import Path

import pytest

from appbuilder.contracts import load_project_definition
from appbuilder.generation.engine import generate_application
from appbuilder.generation.kafka_build_emitter import emit as emit_build_files
from appbuilder.generation.kafka_emitter import emit as emit_kafka_sources
from appbuilder.generation.kafka_router_components import (
    render_router_core_components,
    transform_mapping_specs,
)
from appbuilder.metadata.kafka_models import KafkaTransformMapping
from appbuilder.metadata.kafka_translation import translate_kafka_project, translate_router_route

_ROUTER_FIXTURE = Path("tests/fixtures/kafka-router-contract")


def _router_metadata():
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    assert definition.async_routes is not None
    return translate_router_route(definition.async_routes[0], project_root=_ROUTER_FIXTURE)


def _router_kafka_metadata():
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    return translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)


def _router_sources() -> dict[str, str]:
    return render_router_core_components(
        java_package="com.appbuilder.payments",
        target_profile_name="springboot-legacy-compatible",
        route=_router_metadata(),
        source_manifest="tests/fixtures/kafka-router-contract/manifest.yaml",
        generation_run_id="router-core-test",
    )


def _source_named(sources: dict[str, str], filename: str) -> str:
    matches = [source for path, source in sources.items() if path.endswith(filename)]
    assert len(matches) == 1
    return matches[0]


def test_translate_router_route_produces_router_metadata() -> None:
    route = _router_metadata()

    assert route.name == "payment_router"
    assert route.route_class_prefix == "PaymentRouter"
    assert route.duplicate_correlation_policy == "reject-new"
    assert route.upstream_topics[0].name == "u1-payment-request"
    assert route.routing_fields[0].name == "country"
    assert route.routing_rules[0].target == "d1_processor"
    assert route.targets[0].request_topic == "d1-payment-request"
    assert route.targets[0].request_transform.mappings[2].value_map == {
        "APPROVED": "A",
        "DECLINED": "D",
    }
    assert route.nack_routing.mode == "fixed"
    assert route.nack_routing.fixed_topic == "payment-router-nack"
    assert route.correlation_store.type == "in_memory"


def test_render_router_core_components_returns_expected_files() -> None:
    sources = _router_sources()

    assert {
        "src/main/java/com/appbuilder/payments/router/RoutingCorrelationRecord.java",
        "src/main/java/com/appbuilder/payments/router/RoutingCorrelationStore.java",
        "src/main/java/com/appbuilder/payments/router/RoutingRuleEvaluator.java",
        "src/main/java/com/appbuilder/payments/router/RouterBusinessException.java",
        "src/main/java/com/appbuilder/payments/router/RouterTechnicalException.java",
        "src/main/java/com/appbuilder/payments/router/NackPublisher.java",
        "src/main/java/com/appbuilder/payments/router/RouterJsonSchemaValidator.java",
        "src/main/java/com/appbuilder/payments/router/RouterTransformService.java",
    }.issubset(sources)


def test_top_level_router_translation_returns_router_metadata() -> None:
    metadata = _router_kafka_metadata()

    assert metadata.routes == []
    assert len(metadata.router_routes) == 1
    assert metadata.router_routes[0].name == "payment_router"


def test_router_generation_emits_request_path_files(tmp_path: Path) -> None:
    metadata = _router_kafka_metadata()

    report = generate_application(
        metadata,
        tmp_path / "PaymentRouter",
        source_manifest="tests/fixtures/kafka-router-contract/manifest.yaml",
        generation_run_id="router-request-test",
    )

    assert (
        report.output_dir
        / "src/main/java/com/appbuilder/payments/router/RouterPatternListener.java"
    ).exists()
    assert (
        report.output_dir
        / "src/main/java/com/appbuilder/payments/router/RoutingService.java"
    ).exists()
    assert (
        report.output_dir
        / "src/main/java/com/appbuilder/payments/router/RoutingCorrelationStore.java"
    ).exists()
    assert (
        report.output_dir
        / "src/main/java/com/appbuilder/payments/router/DownstreamResponseListener.java"
    ).exists()
    assert (
        report.output_dir
        / "src/main/java/com/appbuilder/payments/router/CorrelationTimeoutScheduler.java"
    ).exists()
    assert (report.output_dir / "src/main/resources/schemas/ro-request.json").exists()
    assert (report.output_dir / "src/main/resources/schemas/d1-request.json").exists()


def test_router_source_generation_contains_request_path_wiring() -> None:
    files = emit_kafka_sources(_router_kafka_metadata())

    listener = _source_named(files, "RouterPatternListener.java")
    service = _source_named(files, "RoutingService.java")

    assert "routingService.handle(record.value(), toHeaderMap(record.headers()), \"u1_intake\")" in listener
    assert "schemaValidator.validate(payload, INBOUND_SCHEMA, \"V1\")" in service
    assert "RoutingRuleEvaluator.RoutingDecision routingDecision = routingRuleEvaluator.evaluate(routingFields);" in service
    assert "String targetId = routingDecision.targetId();" in service
    assert "correlationStore.register(new RoutingCorrelationRecord(" in service
    assert "transformService.transform(toMap(payload), target.requestMappings())" in service
    assert "schemaValidator.validate(downstreamPayload, target.requestSchema(), \"V2\")" in service
    assert "new ProducerRecord<>(" in service
    assert "target.requestTopic(), correlationId, transformedRequest" in service
    assert "waitForPublish(record, \"Failed to publish router request to topic \" + target.requestTopic())" in service
    assert "ReplyConsumer" not in str(files.keys())


def test_router_request_publish_is_confirmed_and_cancels_correlation_on_failure() -> None:
    files = emit_kafka_sources(_router_kafka_metadata())
    listener = _source_named(files, "RouterPatternListener.java")
    service = _source_named(files, "RoutingService.java")

    register = service.index("registerCorrelation(correlationId, sourceSystem, replyDestination, target)")
    publish = service.index("waitForPublish(record, \"Failed to publish router request to topic \" + target.requestTopic())")
    cancel = service.index("correlationStore.cancel(correlationId);", publish)
    rethrow = service.index("throw ex;", cancel)

    assert register < publish < cancel < rethrow
    assert "kafkaTemplate.send(record).get();" in service
    assert "catch (ExecutionException ex)" in service
    assert "Thread.currentThread().interrupt();" in service
    assert "catch (RouterTechnicalException" not in listener
    assert "catch (RouterBusinessException ex)" in listener


def test_router_request_path_fails_fast_before_validation_and_routing() -> None:
    service = _source_named(emit_kafka_sources(_router_kafka_metadata()), "RoutingService.java")

    reply_check = service.index("if (!isValidReplyDestination(replyDestination))")
    correlation_check = service.index("if (correlationId == null || correlationId.isBlank())", reply_check)
    v1_validation = service.index("schemaValidator.validate(payload, INBOUND_SCHEMA, \"V1\")")
    routing = service.index("routingRuleEvaluator.evaluate(routingFields)")
    downstream_publish = service.index("target.requestTopic(), correlationId, transformedRequest")

    assert reply_check < correlation_check < v1_validation < routing < downstream_publish
    assert "\"MISSING_CORRELATION_ID\"" in service
    assert "V1_VALIDATION_FAILED" in service
    assert "V2_VALIDATION_FAILED" in service
    assert "publishBusinessNack(sourceSystem, replyDestination, true" in service
    assert "DeadLetter" not in service
    assert "DLQ" not in service


def test_router_build_files_add_router_only_dependency_and_config() -> None:
    router_files = emit_build_files(_router_kafka_metadata())
    non_router_definition = load_project_definition(Path("tests/fixtures/kafka-integration/manifest.yaml"))
    non_router_metadata = translate_kafka_project(
        non_router_definition,
        project_root=Path("tests/fixtures/kafka-integration"),
    )
    non_router_files = emit_build_files(non_router_metadata)

    assert "<artifactId>json-schema-validator</artifactId>" in router_files["pom.xml"]
    assert "<artifactId>json-schema-validator</artifactId>" not in non_router_files["pom.xml"]
    application_yaml = router_files["src/main/resources/application.yaml"]
    assert "router:" in application_yaml
    assert "u1_intake:" in application_yaml
    assert "TOPIC_PAYMENT_ROUTER_U1_INTAKE_UPSTREAM" in application_yaml
    assert "d1_processor:" in application_yaml
    assert "request-topic:" in application_yaml
    assert "default-error-topic:" in application_yaml
    assert "behavior-with-known-reply: nack" in application_yaml
    assert "behavior-without-reply: error_topic" in application_yaml
    assert "    topics:" not in application_yaml
    assert "reply-destination:" in application_yaml
    assert "allowed-topics: ${ROUTER_PAYMENT_ROUTER_REPLY_ALLOWED_TOPICS:}" in application_yaml
    assert "allowed-prefixes: ${ROUTER_PAYMENT_ROUTER_REPLY_ALLOWED_PREFIXES:}" in application_yaml
    assert "duplicate-correlation-policy: ${ROUTER_PAYMENT_ROUTER_DUPLICATE_CORRELATION_POLICY:reject-new}" in application_yaml
    assert "src/main/resources/schemas/ro-request.json" in router_files
    assert "src/main/resources/schemas/d1-request.json" in router_files


def test_router_source_generation_contains_response_path_wiring() -> None:
    files = emit_kafka_sources(_router_kafka_metadata())

    listener = _source_named(files, "DownstreamResponseListener.java")
    service = _source_named(files, "RoutingService.java")

    assert "d1_processor.response-topic" in listener
    assert "routingService.handleDownstreamResponse(record.value(), toHeaderMap(record.headers()), record.topic())" in listener
    assert "public void handleDownstreamResponse(String payload, Map<String, String> headers, String responseTopic)" in service
    assert "String correlationId = headers.get(\"X-Correlation-ID\")" in service
    assert "RoutingCorrelationRecord record = correlationStore.retrieve(correlationId)" in service
    assert "if (!record.getSelectedResponseTopic().equals(responseTopic))" in service
    assert "schemaValidator.validate(payload, target.responseSchema(), \"V3\")" in service
    assert "transformService.transform(toMap(payload), target.responseMappings())" in service
    assert "schemaValidator.validate(upstreamPayload, OUTBOUND_SCHEMA, \"V4\")" in service
    assert "record.getReplyDestination(), record.getCorrelationId(), transformedResponse" in service
    assert "waitForPublish(upstreamRecord, \"Failed to publish router response to topic \" + record.getReplyDestination())" in service
    assert "correlationStore.complete(correlationId)" in service


def test_router_response_publish_completes_only_after_confirmed_send() -> None:
    files = emit_kafka_sources(_router_kafka_metadata())
    listener = _source_named(files, "DownstreamResponseListener.java")
    service = _source_named(files, "RoutingService.java")

    record_create = service.index("ProducerRecord<String, Object> upstreamRecord = new ProducerRecord<>(")
    publish = service.index(
        "waitForPublish(upstreamRecord, \"Failed to publish router response to topic \" + record.getReplyDestination())"
    )
    complete = service.index("correlationStore.complete(correlationId)")

    assert record_create < publish < complete
    assert "kafkaTemplate.send(record).get();" in service
    assert "catch (RouterTechnicalException" not in listener
    assert "catch (RouterBusinessException ex)" in listener


def test_router_response_topic_mismatch_nacks_without_completing_correlation() -> None:
    service = _source_named(emit_kafka_sources(_router_kafka_metadata()), "RoutingService.java")

    mismatch_check = service.index("if (!record.getSelectedResponseTopic().equals(responseTopic))")
    v3_validation = service.index("schemaValidator.validate(payload, target.responseSchema(), \"V3\")")
    complete_success = service.index("correlationStore.complete(correlationId)")

    assert mismatch_check < v3_validation < complete_success
    assert "publishMismatchedResponseTopic(record, responseTopic)" in service
    assert "\"RESPONSE_TOPIC_MISMATCH\"" in service
    assert "record.getSelectedResponseTopic()" in service
    assert "correlationStore.complete(record.getCorrelationId())" in service


def test_router_response_business_failures_complete_and_nack_without_dlq() -> None:
    service = _source_named(emit_kafka_sources(_router_kafka_metadata()), "RoutingService.java")

    assert "completeAndPublishResponseNack(record, \"V3_VALIDATION_FAILED\"" in service
    assert "completeAndPublishResponseNack(record, \"RESPONSE_TRANSFORM_FAILED\"" in service
    assert "completeAndPublishResponseNack(record, \"V4_VALIDATION_FAILED\"" in service
    assert "correlationStore.complete(record.getCorrelationId())" in service
    assert "nackPublisher.publishNack(" in service
    helper_start = service.index("private void completeAndPublishResponseNack(")
    nack_publish = service.index("nackPublisher.publishNack(", helper_start)
    complete = service.index("correlationStore.complete(record.getCorrelationId())", helper_start)
    assert nack_publish < complete
    assert "DeadLetter" not in service
    assert "DLQ" not in service


def test_generated_nack_publisher_waits_for_confirmed_send() -> None:
    publisher = _source_named(_router_sources(), "NackPublisher.java")

    assert "kafkaTemplate.send(destination, envelope).get();" in publisher
    assert "catch (InterruptedException ex)" in publisher
    assert "Thread.currentThread().interrupt();" in publisher
    assert "catch (ExecutionException ex)" in publisher
    assert "Failed to publish router NACK to topic " in publisher


def test_router_orphaned_response_and_timeout_scheduler_are_generated() -> None:
    files = emit_kafka_sources(_router_kafka_metadata())
    service = _source_named(files, "RoutingService.java")
    scheduler = _source_named(files, "CorrelationTimeoutScheduler.java")

    assert "publishOrphanedResponse(correlationId, \"No pending correlation for downstream response\")" in service
    assert "\"ORPHANED_RESPONSE\"" in service
    assert "correlationStore.evictExpired(Instant.now())" in scheduler
    assert "\"CORRELATION_TIMEOUT\"" in scheduler
    assert "behaviorWithKnownReply" in scheduler
    assert "behaviorWithoutReply" in scheduler
    assert "@Scheduled(fixedDelayString = \"${app.kafka.router.payment_router.timeout.eviction-interval-ms}\")" in scheduler
    assert "DownstreamTimeoutException" not in scheduler
    assert "DeadLetter" not in scheduler
    assert "DLQ" not in scheduler


def test_router_strict_schema_resources_reject_extra_properties() -> None:
    router_files = emit_build_files(_router_kafka_metadata())

    inbound_schema = json.loads(router_files["src/main/resources/schemas/ro-request.json"])
    request_schema = json.loads(router_files["src/main/resources/schemas/d1-request.json"])

    assert inbound_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert inbound_schema["additionalProperties"] is False
    assert request_schema["additionalProperties"] is False


def test_router_strict_schema_resources_override_schema_level_additional_properties() -> None:
    metadata = _router_kafka_metadata()
    assert metadata.router_routes[0].inbound_schema.content is not None
    metadata.router_routes[0].inbound_schema.content["additionalProperties"] = True

    router_files = emit_build_files(metadata)

    inbound_schema = json.loads(router_files["src/main/resources/schemas/ro-request.json"])
    assert inbound_schema["additionalProperties"] is False


def test_multiple_router_routes_fail_before_generation_overwrite() -> None:
    definition = load_project_definition(_ROUTER_FIXTURE / "manifest.yaml")
    assert definition.async_routes is not None
    second_route = definition.async_routes[0].model_copy(deep=True, update={"name": "second_router"})
    definition.async_routes.append(second_route)

    with pytest.raises(ValueError, match="at most one router route"):
        translate_kafka_project(definition, project_root=_ROUTER_FIXTURE)


def test_generated_correlation_store_contains_core_lifecycle_methods() -> None:
    store = _source_named(_router_sources(), "RoutingCorrelationStore.java")

    assert "ConcurrentHashMap<String, RoutingCorrelationRecord> pending" in store
    assert "@Value(\"${app.kafka.router.payment_router.duplicate-correlation-policy:reject-new}\")" in store
    assert "private String duplicatePolicy;" in store
    assert "public void register(RoutingCorrelationRecord record)" in store
    assert "public RoutingCorrelationRecord retrieve(String correlationId)" in store
    assert "public void complete(String correlationId)" in store
    assert "public void cancel(String correlationId)" in store
    assert "public List<RoutingCorrelationRecord> evictExpired(Instant now)" in store
    assert "private String normalizedDuplicatePolicy()" in store
    assert "\"reject-new\".equals(normalized) || \"accept-last\".equals(normalized)" in store
    assert "Unsupported duplicate-correlation-policy" in store
    assert "\"accept-last\".equals(policy)" in store
    assert "DuplicateCorrelationException" in store
    assert "InvalidCorrelationException(\"correlationId is required\")" in store
    assert "DuplicateCorrelationException(\"correlationId is required\")" not in store


def test_generated_correlation_record_contains_design_doc_fields() -> None:
    record = _source_named(_router_sources(), "RoutingCorrelationRecord.java")

    for field in [
        "correlationId",
        "sourceSystem",
        "replyDestination",
        "businessFlow",
        "selectedTargetId",
        "selectedRequestTopic",
        "selectedResponseTopic",
        "requestSchemaRef",
        "responseSchemaRef",
        "capturedAt",
        "expiresAt",
    ]:
        assert field in record
    assert "requestSchemaVersion" not in record
    assert "responseSchemaVersion" not in record


def test_generated_routing_rule_evaluator_supports_first_match_and_default_target() -> None:
    sources = render_router_core_components(
        java_package="com.appbuilder.payments",
        target_profile_name="springboot-legacy-compatible",
        route=_router_metadata().model_copy(update={"default_target": "d1_processor"}),
        source_manifest="tests/fixtures/kafka-router-contract/manifest.yaml",
        generation_run_id="router-core-test",
    )
    evaluator = _source_named(sources, "RoutingRuleEvaluator.java")

    assert "for (RoutingRule rule : rules())" in evaluator
    assert "if (rule.matches(routingFields))" in evaluator
    assert "return new RoutingDecision(rule.targetId(), false);" in evaluator
    assert "return new RoutingDecision(\"d1_processor\", true);" in evaluator
    assert "public record RoutingDecision(String targetId, boolean defaultTargetUsed)" in evaluator
    assert "isComparable(actual, expected) && compare(actual, expected) > 0" in evaluator
    assert "isComparable(actual, expected) && compare(actual, expected) >= 0" in evaluator
    assert "return actual != null && expected != null;" in evaluator
    assert "return 1;" not in evaluator
    for operator in ["eq", "in", "lt", "lte", "gt", "gte", "not_null"]:
        assert f'case "{operator}"' in evaluator
    assert "new RoutingRule(" in evaluator
    assert "\"uk_payments\"" in evaluator


def test_generated_routing_service_validates_reply_destination_allowlist() -> None:
    service = _source_named(emit_kafka_sources(_router_kafka_metadata()), "RoutingService.java")

    assert "private String allowedReplyTopics;" in service
    assert "private String allowedReplyPrefixes;" in service
    assert "if (replyDestination == null || replyDestination.isBlank())" in service
    assert "boolean hasAllowedTopics = allowedReplyTopics != null && !allowedReplyTopics.isBlank();" in service
    assert "boolean hasAllowedPrefixes = allowedReplyPrefixes != null && !allowedReplyPrefixes.isBlank();" in service
    assert "if (!hasAllowedTopics && !hasAllowedPrefixes)" in service
    assert "replyDestination.equals(allowedTopic.trim())" in service
    assert "replyDestination.startsWith(normalizedPrefix)" in service
    assert "\"INVALID_REPLY_DESTINATION\"" in service
    invalid_reply = service.index("if (!isValidReplyDestination(replyDestination))")
    downstream_publish = service.index("target.requestTopic(), correlationId, transformedRequest")
    assert invalid_reply < downstream_publish


def test_generated_routing_service_logs_default_target_only_when_fallback_used() -> None:
    service = _source_named(emit_kafka_sources(_router_kafka_metadata()), "RoutingService.java")

    assert "private static final Logger log = LoggerFactory.getLogger(RoutingService.class);" in service
    assert "if (routingDecision.defaultTargetUsed())" in service
    assert "Kafka router default target selected route={} selectedTarget={}" in service
    assert "\"payment_router\", targetId" in service
    explicit_rule = service.index("RoutingRuleEvaluator.RoutingDecision routingDecision = routingRuleEvaluator.evaluate")
    fallback_guard = service.index("if (routingDecision.defaultTargetUsed())", explicit_rule)
    target_config = service.index("TargetConfig target = targetConfig(targetId);", fallback_guard)
    assert explicit_rule < fallback_guard < target_config


def test_generated_routing_rule_evaluator_handles_numeric_in_conditions() -> None:
    route = _router_metadata()
    route.routing_rules[0].conditions[0].operator = "in"
    route.routing_rules[0].conditions[0].value = [100]
    evaluator = _source_named(
        render_router_core_components(
            java_package="com.appbuilder.payments",
            target_profile_name="springboot-legacy-compatible",
            route=route,
            source_manifest="tests/fixtures/kafka-router-contract/manifest.yaml",
            generation_run_id="router-core-test",
        ),
        "RoutingRuleEvaluator.java",
    )

    assert "values.stream().anyMatch(value -> valuesMatch(actual, value))" in evaluator
    assert "return compare(actual, expected) == 0;" in evaluator
    assert "new BigDecimal(value.toString())" in evaluator


def test_generated_nack_publisher_supports_all_modes_and_default_error_fallback() -> None:
    publisher = _source_named(_router_sources(), "NackPublisher.java")

    for mode in ["same_as_reply", "per_source_system", "fixed", "default_error"]:
        assert f'case "{mode}"' in publisher
    assert "return defaultErrorTopic;" in publisher
    for envelope_field in [
        "correlationId",
        "errorCode",
        "errorReason",
        "sourceSystem",
        "replyDestination",
        "businessFlow",
        "selectedTarget",
        "validationBoundary",
        "timestamp",
        "originalPayloadRef",
    ]:
        assert f'envelope.put("{envelope_field}"' in publisher
    assert "payloadLoggingPolicy\", \"none\"" in publisher
    assert "String originalPayloadRef" in publisher


def test_generated_exception_hierarchy_is_bounded() -> None:
    business = _source_named(_router_sources(), "RouterBusinessException.java")
    technical = _source_named(_router_sources(), "RouterTechnicalException.java")

    assert "ValidationFailedException" in business
    assert "RoutingRuleNotFoundException" in business
    assert "DuplicateCorrelationException" in business
    assert "InvalidCorrelationException" in business
    assert "InvalidReplyDestinationException" in business
    assert "TransformMappingException" in business
    assert "KafkaPublishException" in technical
    assert "UnexpectedProcessingException" in technical
    assert "DownstreamTimeoutException" not in business
    assert "DownstreamTimeoutException" not in technical
    assert "DeadLetter" not in business
    assert "DLQ" not in business


def test_generated_json_validator_and_transform_service_are_core_contracts() -> None:
    sources = _router_sources()
    validator = _source_named(sources, "RouterJsonSchemaValidator.java")
    transform_service = _source_named(sources, "RouterTransformService.java")

    assert "RouterJsonSchemaValidator" in validator
    assert "ValidationFailedException" in validator
    assert "objectMapper.readTree(payload)" in validator
    assert "ConcurrentMap<String, Schema> schemaCache" in validator
    assert "new ConcurrentHashMap<>()" in validator
    assert "schemaCache.computeIfAbsent(schemaRef, this::loadSchema)" in validator
    assert "SchemaRegistry.withDefaultDialect(version, builder -> builder" in validator
    assert 'node.put("$schema", version.getDialectId())' in validator
    assert "SpecificationVersion.DRAFT_2020_12" in validator
    assert "SpecificationVersion.DRAFT_7" in validator
    assert "private final JsonSchemaFactory schemaFactory" not in validator
    assert "schema.validate(payloadNode)" in validator
    assert "RouterTransformService" in transform_service
    assert "TransformMappingException" in transform_service
    assert "applyTypeCoercion(value, mapping)" in transform_service
    assert "mapping.valueMap() != null && !mapping.valueMap().isEmpty()" in transform_service
    assert 'case "major_to_minor_units"' in transform_service
    assert 'case "minor_to_major_units"' in transform_service
    assert "Unsupported type_coercion" in transform_service
    assert "catch (NumberFormatException ex)" in transform_service
    assert "catch (ArithmeticException ex)" in transform_service
    assert "catch (IllegalArgumentException ex)" in transform_service
    assert "coercionFailure(value, mapping, ex)" in transform_service
    assert "\"' for target '\" + mapping.target()" in transform_service
    assert "\"source '\" + mapping.source() + \"'\"" in transform_service
    assert "valueMap" in transform_service
    assert "script" not in transform_service.lower()
    assert "SpEL" not in transform_service


def test_missing_correlation_id_is_business_taxonomy_not_duplicate() -> None:
    files = emit_kafka_sources(_router_kafka_metadata())
    service = _source_named(files, "RoutingService.java")
    store = _source_named(files, "RoutingCorrelationStore.java")

    missing_check = service.index("if (correlationId == null || correlationId.isBlank())")
    missing_nack = service.index("\"MISSING_CORRELATION_ID\"", missing_check)
    v1_validation = service.index("schemaValidator.validate(payload, INBOUND_SCHEMA, \"V1\")")
    register = service.index("registerCorrelation(correlationId, sourceSystem, replyDestination, target)")
    resolve = service.index("private String resolveCorrelationId")
    no_fallback = service.index("return null;", resolve)

    assert missing_check < missing_nack < v1_validation < register
    assert no_fallback > resolve
    assert "return UUID.randomUUID().toString();" not in service[resolve : service.index("private String readText")]
    assert "catch (RouterBusinessException.InvalidCorrelationException ex)" in service
    assert "\"DUPLICATE_CORRELATION\"" in service
    assert "pending.putIfAbsent(record.getCorrelationId(), record)" in store
    assert "InvalidCorrelationException(\"correlationId is required\")" in store
    assert "DuplicateCorrelationException(\"correlationId is required\")" not in store


def test_generated_transform_service_omits_absent_optional_source_fields() -> None:
    transform_service = _source_named(_router_sources(), "RouterTransformService.java")

    has_source = transform_service.index(
        "boolean hasSource = mapping.source() != null && input.containsKey(mapping.source());"
    )
    default_value = transform_service.index("value = mapping.defaultValue();", has_source)
    omit_absent = transform_service.index("if (value == null && !hasConstant && !hasSource)", default_value)
    output_put = transform_service.index("output.put(mapping.target(), value);", omit_absent)

    assert has_source < default_value < omit_absent < output_put
    assert "continue;" in transform_service[omit_absent:output_put]


def test_transform_mapping_specs_render_deterministic_value_maps() -> None:
    route = _router_metadata()
    specs = transform_mapping_specs(route.targets[0].request_transform.mappings)

    assert any('"decisionCode"' in spec for spec in specs)
    assert any('Map.of("APPROVED", "A", "DECLINED", "D")' in spec for spec in specs)


def test_transform_mapping_specs_emit_null_for_absent_value_maps() -> None:
    route = _router_metadata()
    specs = transform_mapping_specs(route.targets[0].request_transform.mappings)

    assert any('"paymentId", "transactionId", null, null, null, null' in spec for spec in specs)
    assert any('"amount", "amount", null, null, null, null' in spec for spec in specs)


def test_transform_mapping_specs_normalize_json_path_fields() -> None:
    mapping = KafkaTransformMapping(source="$.paymentId", target="$.transactionId")

    specs = transform_mapping_specs([mapping])

    assert specs == [
        'new RouterTransformService.TransformMapping("paymentId", "transactionId", null, null, null, null)'
    ]
