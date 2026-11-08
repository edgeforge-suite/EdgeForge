"""Render core Java components for future Kafka router generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from appbuilder.metadata.kafka_models import (
    KafkaMetadata,
    KafkaTransformMapping,
    RouterRouteMetadata,
    RouterRoutingConditionMetadata,
    RouterRoutingRuleMetadata,
    RouterTargetMetadata,
    RouterUpstreamTopicMetadata,
)

from .kafka_compatibility import is_boot41, jackson_import
from .utils import _java_file, package_path


def render_router_core_components(
    *,
    java_package: str,
    target_profile_name: str,
    route: RouterRouteMetadata,
    source_manifest: str = "metadata-project",
    generation_run_id: str = "kafka-router-core",
) -> dict[str, str]:
    """Return router core source files without wiring a generated router app."""

    router_package = f"{java_package}.router"
    root_path = Path("src") / "main" / "java" / package_path(router_package)
    return {
        str(root_path / "RoutingCorrelationRecord.java"): _render_correlation_record(
            router_package,
            target_profile_name=target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "RoutingCorrelationStore.java"): _render_correlation_store(
            router_package,
            route=route,
            target_profile_name=target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "RoutingRuleEvaluator.java"): _render_routing_rule_evaluator(
            router_package,
            route=route,
            target_profile_name=target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "RouterBusinessException.java"): _render_business_exception(
            router_package,
            target_profile_name=target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "RouterTechnicalException.java"): _render_technical_exception(
            router_package,
            target_profile_name=target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "NackPublisher.java"): _render_nack_publisher(
            router_package,
            route=route,
            target_profile_name=target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "RouterJsonSchemaValidator.java"): _render_json_schema_validator(
            router_package,
            target_profile_name=target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "RouterTransformService.java"): _render_transform_service(
            router_package,
            target_profile_name=target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
    }


def render_router_request_path_components(
    *,
    metadata: KafkaMetadata,
    route: RouterRouteMetadata,
    source_manifest: str = "metadata-project",
    generation_run_id: str = "kafka-router-request-path",
) -> dict[str, str]:
    """Return request-side router wiring source files for one router route."""

    router_package = f"{metadata.java_package}.router"
    root_path = Path("src") / "main" / "java" / package_path(router_package)
    return {
        str(root_path / "RouterPatternListener.java"): _render_router_pattern_listener(
            router_package,
            route=route,
            target_profile_name=metadata.target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "RoutingService.java"): _render_routing_service(
            router_package,
            route=route,
            target_profile_name=metadata.target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "DownstreamResponseListener.java"): _render_downstream_response_listener(
            router_package,
            route=route,
            target_profile_name=metadata.target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "CorrelationTimeoutScheduler.java"): _render_correlation_timeout_scheduler(
            router_package,
            route=route,
            target_profile_name=metadata.target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
    }


def _render_router_pattern_listener(
    package_name: str,
    *,
    route: RouterRouteMetadata,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    methods: list[str] = []
    for topic in route.upstream_topics:
        methods.extend(_router_listener_method_lines(route, topic))
        methods.append("")
    if methods:
        methods.pop()
    return _java_file(
        package_name=package_name,
        imports=[
            "java.nio.charset.StandardCharsets",
            "java.util.HashMap",
            "java.util.Map",
            "org.apache.kafka.clients.consumer.ConsumerRecord",
            "org.apache.kafka.common.header.Headers",
            "org.springframework.kafka.annotation.KafkaListener",
            "org.springframework.kafka.support.Acknowledgment",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            "public class RouterPatternListener {",
            "",
            "    private final RoutingService routingService;",
            "",
            "    public RouterPatternListener(RoutingService routingService) {",
            "        this.routingService = routingService;",
            "    }",
            "",
            *methods,
            "",
            "    private Map<String, String> toHeaderMap(Headers headers) {",
            "        Map<String, String> values = new HashMap<>();",
            "        headers.forEach(header -> values.put(header.key(), new String(header.value(), StandardCharsets.UTF_8)));",
            "        return values;",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_downstream_response_listener(
    package_name: str,
    *,
    route: RouterRouteMetadata,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    methods: list[str] = []
    for target in route.targets:
        methods.extend(_downstream_response_listener_method_lines(route, target))
        methods.append("")
    if methods:
        methods.pop()
    return _java_file(
        package_name=package_name,
        imports=[
            "java.nio.charset.StandardCharsets",
            "java.util.HashMap",
            "java.util.Map",
            "org.apache.kafka.clients.consumer.ConsumerRecord",
            "org.apache.kafka.common.header.Headers",
            "org.springframework.kafka.annotation.KafkaListener",
            "org.springframework.kafka.support.Acknowledgment",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            "public class DownstreamResponseListener {",
            "",
            "    private final RoutingService routingService;",
            "",
            "    public DownstreamResponseListener(RoutingService routingService) {",
            "        this.routingService = routingService;",
            "    }",
            "",
            *methods,
            "",
            "    private Map<String, String> toHeaderMap(Headers headers) {",
            "        Map<String, String> values = new HashMap<>();",
            "        headers.forEach(header -> values.put(header.key(), new String(header.value(), StandardCharsets.UTF_8)));",
            "        return values;",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_correlation_timeout_scheduler(
    package_name: str,
    *,
    route: RouterRouteMetadata,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=package_name,
        imports=[
            "java.time.Instant",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.scheduling.annotation.Scheduled",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            "public class CorrelationTimeoutScheduler {",
            "",
            "    private final RoutingCorrelationStore correlationStore;",
            "    private final NackPublisher nackPublisher;",
            "",
            f"    @Value(\"${{app.kafka.router.{route.name}.timeout.behavior-with-known-reply}}\")",
            "    private String behaviorWithKnownReply;",
            "",
            f"    @Value(\"${{app.kafka.router.{route.name}.timeout.behavior-without-reply}}\")",
            "    private String behaviorWithoutReply;",
            "",
            "    public CorrelationTimeoutScheduler(",
            "            RoutingCorrelationStore correlationStore,",
            "            NackPublisher nackPublisher) {",
            "        this.correlationStore = correlationStore;",
            "        this.nackPublisher = nackPublisher;",
            "    }",
            "",
            f"    @Scheduled(fixedDelayString = \"${{app.kafka.router.{route.name}.timeout.eviction-interval-ms}}\")",
            "    public void evictExpiredCorrelations() {",
            "        for (RoutingCorrelationRecord record : correlationStore.evictExpired(Instant.now())) {",
            "            publishTimeout(record);",
            "        }",
            "    }",
            "",
            "    private void publishTimeout(RoutingCorrelationRecord record) {",
            "        boolean hasReplyDestination = record.getReplyDestination() != null",
            "                && !record.getReplyDestination().isBlank();",
            "        boolean replyDestinationValid = hasReplyDestination",
            "                && \"nack\".equals(behaviorWithKnownReply);",
            "        if (!hasReplyDestination && !\"error_topic\".equals(behaviorWithoutReply)) {",
            "            replyDestinationValid = false;",
            "        }",
            "        nackPublisher.publishNack(",
            "                record.getSourceSystem(),",
            "                record.getReplyDestination(),",
            "                replyDestinationValid,",
            "                record.getCorrelationId(),",
            "                \"CORRELATION_TIMEOUT\",",
            "                \"Correlation timed out before downstream response\",",
            "                record.getBusinessFlow(),",
            "                record.getSelectedTargetId(),",
            "                \"timeout\",",
            "                null);",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_routing_service(
    package_name: str,
    *,
    route: RouterRouteMetadata,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=package_name,
        imports=[
            jackson_import(target_profile_name, "core.type.TypeReference"),
            jackson_import(target_profile_name, "databind.JsonNode"),
            jackson_import(target_profile_name, "databind.ObjectMapper"),
            "java.nio.charset.StandardCharsets",
            "java.time.Instant",
            "java.util.LinkedHashMap",
            "java.util.List",
            "java.util.Map",
            "java.util.UUID",
            "java.util.concurrent.ExecutionException",
            "org.apache.kafka.clients.producer.ProducerRecord",
            "org.apache.kafka.common.header.internals.RecordHeader",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.kafka.core.KafkaTemplate",
            "org.springframework.stereotype.Service",
            "org.slf4j.Logger",
            "org.slf4j.LoggerFactory",
        ],
        body=[
            "@Service",
            "public class RoutingService {",
            "",
            "    private static final Logger log = LoggerFactory.getLogger(RoutingService.class);",
            "    private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<>() {};",
            f"    private static final String INBOUND_SCHEMA = {_java_string(route.inbound_schema.file)};",
            f"    private static final String OUTBOUND_SCHEMA = {_java_string(route.outbound_schema.file)};",
            "",
            f"    @Value(\"${{app.kafka.router.{route.name}.reply-destination.allowed-topics:}}\")",
            "    private String allowedReplyTopics;",
            "",
            f"    @Value(\"${{app.kafka.router.{route.name}.reply-destination.allowed-prefixes:}}\")",
            "    private String allowedReplyPrefixes;",
            "",
            *_target_property_field_lines(route),
            "",
            "    private final ObjectMapper objectMapper;",
            "    private final RoutingRuleEvaluator routingRuleEvaluator;",
            "    private final RoutingCorrelationStore correlationStore;",
            "    private final RouterJsonSchemaValidator schemaValidator;",
            "    private final RouterTransformService transformService;",
            "    private final NackPublisher nackPublisher;",
            "    private final KafkaTemplate<String, Object> kafkaTemplate;",
            "",
            "    public RoutingService(",
            "            ObjectMapper objectMapper,",
            "            RoutingRuleEvaluator routingRuleEvaluator,",
            "            RoutingCorrelationStore correlationStore,",
            "            RouterJsonSchemaValidator schemaValidator,",
            "            RouterTransformService transformService,",
            "            NackPublisher nackPublisher,",
            "            KafkaTemplate<String, Object> kafkaTemplate) {",
            "        this.objectMapper = objectMapper;",
            "        this.routingRuleEvaluator = routingRuleEvaluator;",
            "        this.correlationStore = correlationStore;",
            "        this.schemaValidator = schemaValidator;",
            "        this.transformService = transformService;",
            "        this.nackPublisher = nackPublisher;",
            "        this.kafkaTemplate = kafkaTemplate;",
            "    }",
            "",
            "    public void handle(String payload, Map<String, String> headers, String upstreamTopicId) {",
            "        JsonNode root;",
            "        try {",
            "            root = readJson(payload);",
            "        } catch (RouterBusinessException.ValidationFailedException ex) {",
            "            String sourceSystem = extractSourceSystem(headers, null, upstreamTopicId);",
            "            String replyDestination = extractReplyDestination(headers, null, upstreamTopicId);",
            "            publishBusinessNack(sourceSystem, replyDestination, isValidReplyDestination(replyDestination),",
            "                    UUID.randomUUID().toString(), \"V1_VALIDATION_FAILED\",",
            "                    ex.getMessage(), null, \"V1\", null);",
            "            return;",
            "        }",
            "        String correlationId = resolveCorrelationId(headers, root);",
            "        String sourceSystem = extractSourceSystem(headers, root, upstreamTopicId);",
            "        String replyDestination = extractReplyDestination(headers, root, upstreamTopicId);",
            "        if (sourceSystem == null || sourceSystem.isBlank()) {",
            "            publishBusinessNack(null, replyDestination, false, correlationId, \"INVALID_SOURCE_SYSTEM\",",
            "                    \"Missing or invalid source system\", null, \"pre-v1\", null);",
            "            return;",
            "        }",
            "        if (!isValidReplyDestination(replyDestination)) {",
            "            publishBusinessNack(sourceSystem, replyDestination, false, correlationId, \"INVALID_REPLY_DESTINATION\",",
            "                    \"Missing or invalid reply destination\", null, \"pre-v1\", null);",
            "            return;",
            "        }",
            "        if (correlationId == null || correlationId.isBlank()) {",
            "            publishBusinessNack(sourceSystem, replyDestination, true, UUID.randomUUID().toString(),",
            "                    \"MISSING_CORRELATION_ID\", \"Missing or blank correlation ID\",",
            "                    null, \"pre-v1\", null);",
            "            return;",
            "        }",
            "        try {",
            "            schemaValidator.validate(payload, INBOUND_SCHEMA, \"V1\");",
            "        } catch (RouterBusinessException.ValidationFailedException ex) {",
            "            publishBusinessNack(sourceSystem, replyDestination, true, correlationId, \"V1_VALIDATION_FAILED\",",
            "                    ex.getMessage(), null, \"V1\", null);",
            "            return;",
            "        }",
            "        Map<String, Object> routingFields = extractRoutingFields(root);",
            "        RoutingRuleEvaluator.RoutingDecision routingDecision = routingRuleEvaluator.evaluate(routingFields);",
            "        String targetId = routingDecision.targetId();",
            "        if (targetId == null || targetId.isBlank()) {",
            "            publishBusinessNack(sourceSystem, replyDestination, true, correlationId, \"ROUTING_RULE_NOT_FOUND\",",
            "                    \"No router target matched request\", null, \"routing\", null);",
            "            return;",
            "        }",
            "        if (routingDecision.defaultTargetUsed()) {",
            f"            log.info(\"Kafka router default target selected route={{}} selectedTarget={{}}\", {_java_string(route.name)}, targetId);",
            "        }",
            "        TargetConfig target = targetConfig(targetId);",
            "        registerCorrelation(correlationId, sourceSystem, replyDestination, target);",
            "        Map<String, Object> transformedRequest;",
            "        try {",
            "            transformedRequest = transformService.transform(toMap(payload), target.requestMappings());",
            "        } catch (RouterBusinessException.TransformMappingException ex) {",
            "            correlationStore.cancel(correlationId);",
            "            publishBusinessNack(sourceSystem, replyDestination, true, correlationId, \"REQUEST_TRANSFORM_FAILED\",",
            "                    ex.getMessage(), target.id(), \"request-transform\", null);",
            "            return;",
            "        }",
            "        String downstreamPayload = writeJson(transformedRequest);",
            "        try {",
            "            schemaValidator.validate(downstreamPayload, target.requestSchema(), \"V2\");",
            "        } catch (RouterBusinessException.ValidationFailedException ex) {",
            "            correlationStore.cancel(correlationId);",
            "            publishBusinessNack(sourceSystem, replyDestination, true, correlationId, \"V2_VALIDATION_FAILED\",",
            "                    ex.getMessage(), target.id(), \"V2\", null);",
            "            return;",
            "        }",
            "        try {",
            "            ProducerRecord<String, Object> record = new ProducerRecord<>(",
            "                    target.requestTopic(), correlationId, transformedRequest);",
            "            record.headers().add(new RecordHeader(",
            "                    \"X-Correlation-ID\", correlationId.getBytes(StandardCharsets.UTF_8)));",
            "            waitForPublish(record, \"Failed to publish router request to topic \" + target.requestTopic());",
            "        } catch (RouterTechnicalException.KafkaPublishException ex) {",
            "            correlationStore.cancel(correlationId);",
            "            throw ex;",
            "        }",
            "    }",
            "",
            "    public void handleDownstreamResponse(String payload, Map<String, String> headers, String responseTopic) {",
            "        String correlationId = headers.get(\"X-Correlation-ID\");",
            "        if (correlationId == null || correlationId.isBlank()) {",
            "            publishOrphanedResponse(null, \"Missing correlation header\");",
            "            return;",
            "        }",
            "        RoutingCorrelationRecord record = correlationStore.retrieve(correlationId);",
            "        if (record == null) {",
            "            publishOrphanedResponse(correlationId, \"No pending correlation for downstream response\");",
            "            return;",
            "        }",
            "        if (!record.getSelectedResponseTopic().equals(responseTopic)) {",
            "            publishMismatchedResponseTopic(record, responseTopic);",
            "            return;",
            "        }",
            "        TargetConfig target = targetConfig(record.getSelectedTargetId());",
            "        try {",
            "            schemaValidator.validate(payload, target.responseSchema(), \"V3\");",
            "        } catch (RouterBusinessException.ValidationFailedException ex) {",
            "            completeAndPublishResponseNack(record, \"V3_VALIDATION_FAILED\", ex.getMessage(), \"V3\");",
            "            return;",
            "        }",
            "        Map<String, Object> transformedResponse;",
            "        try {",
            "            transformedResponse = transformService.transform(toMap(payload), target.responseMappings());",
            "        } catch (RouterBusinessException.TransformMappingException ex) {",
            "            completeAndPublishResponseNack(record, \"RESPONSE_TRANSFORM_FAILED\", ex.getMessage(), \"response-transform\");",
            "            return;",
            "        }",
            "        String upstreamPayload = writeJson(transformedResponse);",
            "        try {",
            "            schemaValidator.validate(upstreamPayload, OUTBOUND_SCHEMA, \"V4\");",
            "        } catch (RouterBusinessException.ValidationFailedException ex) {",
            "            completeAndPublishResponseNack(record, \"V4_VALIDATION_FAILED\", ex.getMessage(), \"V4\");",
            "            return;",
            "        }",
            "        ProducerRecord<String, Object> upstreamRecord = new ProducerRecord<>(",
            "                record.getReplyDestination(), record.getCorrelationId(), transformedResponse);",
            "        upstreamRecord.headers().add(new RecordHeader(",
            "                \"X-Correlation-ID\", record.getCorrelationId().getBytes(StandardCharsets.UTF_8)));",
            "        waitForPublish(upstreamRecord, \"Failed to publish router response to topic \" + record.getReplyDestination());",
            "        correlationStore.complete(correlationId);",
            "    }",
            "",
            "    private void waitForPublish(ProducerRecord<String, Object> record, String failureMessage) {",
            "        try {",
            "            kafkaTemplate.send(record).get();",
            "        } catch (InterruptedException ex) {",
            "            Thread.currentThread().interrupt();",
            "            throw new RouterTechnicalException.KafkaPublishException(failureMessage, ex);",
            "        } catch (ExecutionException ex) {",
            "            throw new RouterTechnicalException.KafkaPublishException(failureMessage, ex);",
            "        }",
            "    }",
            "",
            "    private void registerCorrelation(String correlationId, String sourceSystem, String replyDestination, TargetConfig target) {",
            "        try {",
            "            Instant now = Instant.now();",
            "            correlationStore.register(new RoutingCorrelationRecord(",
            "                    correlationId,",
            "                    sourceSystem,",
            "                    replyDestination,",
            f"                    {_java_string(route.name)},",
            "                    target.id(),",
            "                    target.requestTopic(),",
            "                    target.responseTopic(),",
            "                    target.requestSchema(),",
            "                    target.responseSchema(),",
            "                    now,",
            "                    now.plusMillis(target.timeoutMs())));",
            "        } catch (RouterBusinessException.InvalidCorrelationException ex) {",
            "            publishBusinessNack(sourceSystem, replyDestination, true,",
            "                    correlationId == null || correlationId.isBlank() ? UUID.randomUUID().toString() : correlationId,",
            "                    \"MISSING_CORRELATION_ID\", ex.getMessage(), target.id(), \"correlation\", null);",
            "            throw ex;",
            "        } catch (RouterBusinessException.DuplicateCorrelationException ex) {",
            "            publishBusinessNack(sourceSystem, replyDestination, true, correlationId, \"DUPLICATE_CORRELATION\",",
            "                    ex.getMessage(), target.id(), \"correlation\", null);",
            "            throw ex;",
            "        }",
            "    }",
            "",
            "    private void publishMismatchedResponseTopic(RoutingCorrelationRecord record, String responseTopic) {",
            "        nackPublisher.publishNack(",
            "                record.getSourceSystem(),",
            "                null,",
            "                false,",
            "                record.getCorrelationId(),",
            "                \"RESPONSE_TOPIC_MISMATCH\",",
            "                \"Downstream response arrived on \" + responseTopic",
            "                        + \" but expected \" + record.getSelectedResponseTopic(),",
            "                record.getBusinessFlow(),",
            "                record.getSelectedTargetId(),",
            "                \"response-topic\",",
            "                null);",
            "    }",
            "",
            "    private void completeAndPublishResponseNack(",
            "            RoutingCorrelationRecord record,",
            "            String errorCode,",
            "            String errorReason,",
            "            String validationBoundary) {",
            "        nackPublisher.publishNack(",
            "                record.getSourceSystem(),",
            "                record.getReplyDestination(),",
            "                isValidReplyDestination(record.getReplyDestination()),",
            "                record.getCorrelationId(),",
            "                errorCode,",
            "                errorReason,",
            "                record.getBusinessFlow(),",
            "                record.getSelectedTargetId(),",
            "                validationBoundary,",
            "                null);",
            "        correlationStore.complete(record.getCorrelationId());",
            "    }",
            "",
            "    private void publishOrphanedResponse(String correlationId, String reason) {",
            "        nackPublisher.publishNack(",
            "                null,",
            "                null,",
            "                false,",
            "                correlationId == null || correlationId.isBlank() ? UUID.randomUUID().toString() : correlationId,",
            "                \"ORPHANED_RESPONSE\",",
            "                reason,",
            f"                {_java_string(route.name)},",
            "                null,",
            "                \"response\",",
            "                null);",
            "    }",
            "",
            "    private Map<String, Object> extractRoutingFields(JsonNode root) {",
            "        Map<String, Object> fields = new LinkedHashMap<>();",
            *_routing_field_lines(route),
            "        return fields;",
            "    }",
            "",
            "    private TargetConfig targetConfig(String targetId) {",
            "        return switch (targetId) {",
            *_target_config_case_lines(route.targets),
            "            default -> throw new RouterBusinessException.RoutingRuleNotFoundException(",
            "                    \"Unknown router target: \" + targetId);",
            "        };",
            "    }",
            "",
            "    private String extractSourceSystem(Map<String, String> headers, JsonNode root, String upstreamTopicId) {",
            "        return switch (upstreamTopicId) {",
            *_extraction_case_lines(route.upstream_topics, source=True),
            "            default -> null;",
            "        };",
            "    }",
            "",
            "    private String extractReplyDestination(Map<String, String> headers, JsonNode root, String upstreamTopicId) {",
            "        return switch (upstreamTopicId) {",
            *_extraction_case_lines(route.upstream_topics, source=False),
            "            default -> null;",
            "        };",
            "    }",
            "",
            "    private boolean isValidReplyDestination(String replyDestination) {",
            "        if (replyDestination == null || replyDestination.isBlank()) {",
            "            return false;",
            "        }",
            "        boolean hasAllowedTopics = allowedReplyTopics != null && !allowedReplyTopics.isBlank();",
            "        boolean hasAllowedPrefixes = allowedReplyPrefixes != null && !allowedReplyPrefixes.isBlank();",
            "        if (!hasAllowedTopics && !hasAllowedPrefixes) {",
            "            return true;",
            "        }",
            "        if (hasAllowedTopics) {",
            "            for (String allowedTopic : allowedReplyTopics.split(\",\")) {",
            "                if (replyDestination.equals(allowedTopic.trim())) {",
            "                    return true;",
            "                }",
            "            }",
            "        }",
            "        if (hasAllowedPrefixes) {",
            "            for (String allowedPrefix : allowedReplyPrefixes.split(\",\")) {",
            "                String normalizedPrefix = allowedPrefix.trim();",
            "                if (!normalizedPrefix.isBlank() && replyDestination.startsWith(normalizedPrefix)) {",
            "                    return true;",
            "                }",
            "            }",
            "        }",
            "        return false;",
            "    }",
            "",
            "    private JsonNode readJson(String payload) {",
            "        try {",
            "            return objectMapper.readTree(payload);",
            "        } catch (Exception ex) {",
            "            throw new RouterBusinessException.ValidationFailedException(",
            "                    \"Request payload is not valid JSON: \" + ex.getMessage());",
            "        }",
            "    }",
            "",
            "    private Map<String, Object> toMap(String payload) {",
            "        try {",
            "            return objectMapper.readValue(payload, MAP_TYPE);",
            "        } catch (Exception ex) {",
            "            throw new RouterBusinessException.TransformMappingException(",
            "                    \"Request payload could not be converted to a transform map: \" + ex.getMessage());",
            "        }",
            "    }",
            "",
            "    private String writeJson(Object value) {",
            "        try {",
            "            return objectMapper.writeValueAsString(value);",
            "        } catch (Exception ex) {",
            "            throw new RouterBusinessException.TransformMappingException(",
            "                    \"Transformed request could not be serialized: \" + ex.getMessage());",
            "        }",
            "    }",
            "",
            "    private String resolveCorrelationId(Map<String, String> headers, JsonNode root) {",
            "        String headerValue = headers.get(\"X-Correlation-ID\");",
            "        if (headerValue != null && !headerValue.isBlank()) {",
            "            return headerValue;",
            "        }",
            "        String bodyValue = readText(root, \"$.correlationId\");",
            "        if (bodyValue != null && !bodyValue.isBlank()) {",
            "            return bodyValue;",
            "        }",
            "        return null;",
            "    }",
            "",
            "    private String readText(JsonNode root, String jsonPath) {",
            "        JsonNode value = readNode(root, jsonPath);",
            "        if (value == null || value.isNull() || value.isMissingNode()) {",
            "            return null;",
            "        }",
            "        return value.isTextual() ? value.asText() : value.toString();",
            "    }",
            "",
            "    private Object readValue(JsonNode root, String jsonPath) {",
            "        JsonNode value = readNode(root, jsonPath);",
            "        if (value == null || value.isNull() || value.isMissingNode()) {",
            "            return null;",
            "        }",
            "        if (value.isNumber()) {",
            "            return value.decimalValue();",
            "        }",
            "        if (value.isBoolean()) {",
            "            return value.booleanValue();",
            "        }",
            "        return value.isTextual() ? value.asText() : value.toString();",
            "    }",
            "",
            "    private JsonNode readNode(JsonNode root, String jsonPath) {",
            "        if (root == null) {",
            "            return null;",
            "        }",
            "        if (jsonPath == null || jsonPath.isBlank()) {",
            "            return null;",
            "        }",
            "        String normalized = jsonPath.startsWith(\"$.\") ? jsonPath.substring(2) : jsonPath;",
            "        normalized = normalized.startsWith(\"$\") ? normalized.substring(1) : normalized;",
            "        normalized = normalized.startsWith(\".\") ? normalized.substring(1) : normalized;",
            "        JsonNode current = root;",
            "        for (String part : normalized.split(\"\\\\.\")) {",
            "            if (part.isBlank()) {",
            "                continue;",
            "            }",
            "            current = current.path(part);",
            "        }",
            "        return current;",
            "    }",
            "",
            "    private void publishBusinessNack(",
            "            String sourceSystem,",
            "            String replyDestination,",
            "            boolean replyDestinationValid,",
            "            String correlationId,",
            "            String errorCode,",
            "            String errorReason,",
            "            String selectedTarget,",
            "            String validationBoundary,",
            "            String originalPayloadRef) {",
            "        nackPublisher.publishNack(",
            "                sourceSystem,",
            "                replyDestination,",
            "                replyDestinationValid,",
            "                correlationId,",
            "                errorCode,",
            "                errorReason,",
            f"                {_java_string(route.name)},",
            "                selectedTarget,",
            "                validationBoundary,",
            "                originalPayloadRef);",
            "    }",
            "",
            "    private record TargetConfig(",
            "            String id,",
            "            String requestTopic,",
            "            String responseTopic,",
            "            String requestSchema,",
            "            String responseSchema,",
            "            long timeoutMs,",
            "            List<RouterTransformService.TransformMapping> requestMappings,",
            "            List<RouterTransformService.TransformMapping> responseMappings) {",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _router_listener_method_lines(
    route: RouterRouteMetadata,
    topic: RouterUpstreamTopicMetadata,
) -> list[str]:
    method_name = f"consume{_java_identifier(topic.id, upper_camel=True)}"
    return [
        "    @KafkaListener(",
        f"            topics = \"${{app.kafka.router.{route.name}.upstream.{topic.id}.topic}}\",",
        f"            groupId = \"${{app.kafka.router.{route.name}.upstream.{topic.id}.consumer-group}}\",",
        "            containerFactory = \"kafkaListenerContainerFactory\"",
        "    )",
        f"    public void {method_name}(ConsumerRecord<String, String> record,",
        "            Acknowledgment acknowledgment) {",
        "        try {",
        f"            routingService.handle(record.value(), toHeaderMap(record.headers()), {_java_string(topic.id)});",
        "            acknowledgment.acknowledge();",
        "        } catch (RouterBusinessException ex) {",
        "            acknowledgment.acknowledge();",
        "        }",
        "    }",
    ]


def _downstream_response_listener_method_lines(
    route: RouterRouteMetadata,
    target: RouterTargetMetadata,
) -> list[str]:
    method_name = f"consume{_java_identifier(target.id, upper_camel=True)}Response"
    return [
        "    @KafkaListener(",
        f"            topics = \"${{app.kafka.router.{route.name}.targets.{target.id}.response-topic}}\",",
        "            containerFactory = \"kafkaListenerContainerFactory\"",
        "    )",
        f"    public void {method_name}(ConsumerRecord<String, String> record,",
        "            Acknowledgment acknowledgment) {",
        "        try {",
        "            routingService.handleDownstreamResponse(record.value(), toHeaderMap(record.headers()), record.topic());",
        "            acknowledgment.acknowledge();",
        "        } catch (RouterBusinessException ex) {",
        "            acknowledgment.acknowledge();",
        "        }",
        "    }",
    ]


def _routing_field_lines(route: RouterRouteMetadata) -> list[str]:
    return [
        f"        fields.put({_java_string(field.name)}, readValue(root, {_java_string(field.json_path)}));"
        for field in route.routing_fields
    ]


def _target_config_case_lines(targets: list[RouterTargetMetadata]) -> list[str]:
    lines: list[str] = []
    for target in targets:
        lines.extend(
            [
                f"            case {_java_string(target.id)} -> new TargetConfig(",
                f"                    {_java_string(target.id)},",
                f"                    {_target_property_name(target, 'requestTopic')},",
                f"                    {_target_property_name(target, 'responseTopic')},",
                f"                    {_java_string(target.request_schema.file)},",
                f"                    {_java_string(target.response_schema.file)},",
                f"                    {_target_property_name(target, 'timeoutMs')},",
                "                    List.of(",
                *_transform_mapping_case_lines(target.request_transform.mappings),
                "                    ),",
                "                    List.of(",
                *_transform_mapping_case_lines(target.response_transform.mappings),
                "                    ));",
            ]
        )
    return lines


def _target_property_field_lines(route: RouterRouteMetadata) -> list[str]:
    lines: list[str] = []
    for target in route.targets:
        lines.extend(
            [
                f"    @Value(\"${{app.kafka.router.{route.name}.targets.{target.id}.request-topic}}\")",
                f"    private String {_target_property_name(target, 'requestTopic')};",
                "",
                f"    @Value(\"${{app.kafka.router.{route.name}.targets.{target.id}.response-topic}}\")",
                f"    private String {_target_property_name(target, 'responseTopic')};",
                "",
                f"    @Value(\"${{app.kafka.router.{route.name}.targets.{target.id}.timeout-ms}}\")",
                f"    private long {_target_property_name(target, 'timeoutMs')};",
                "",
            ]
        )
    return lines


def _target_property_name(target: RouterTargetMetadata, suffix: str) -> str:
    return _java_identifier(f"{target.id}_{suffix}", upper_camel=False)


def _transform_mapping_case_lines(mappings: list[KafkaTransformMapping]) -> list[str]:
    specs = transform_mapping_specs(mappings)
    return [
        "                            " + spec + ("," if index < len(specs) - 1 else "")
        for index, spec in enumerate(specs)
    ]


def _extraction_case_lines(
    topics: list[RouterUpstreamTopicMetadata],
    *,
    source: bool,
) -> list[str]:
    lines: list[str] = []
    for topic in topics:
        extraction = (
            topic.source_system_extraction if source else topic.reply_destination_extraction
        )
        if extraction.mode == "header":
            expression = f"headers.get({_java_string(extraction.header_key or '')})"
        else:
            expression = f"readText(root, {_java_string(extraction.body_field_path or '')})"
        lines.append(f"            case {_java_string(topic.id)} -> {expression};")
    return lines


def _render_correlation_record(
    package_name: str,
    *,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    fields = [
        "correlationId",
        "sourceSystem",
        "replyDestination",
        "businessFlow",
        "selectedTargetId",
        "selectedRequestTopic",
        "selectedResponseTopic",
        "requestSchemaRef",
        "responseSchemaRef",
    ]
    body = [
        "public class RoutingCorrelationRecord {",
        *[f"    private final String {field};" for field in fields],
        "    private final Instant capturedAt;",
        "    private final Instant expiresAt;",
        "",
        "    public RoutingCorrelationRecord(",
        *[f"            String {field}," for field in fields],
        "            Instant capturedAt,",
        "            Instant expiresAt) {",
        *[f"        this.{field} = {field};" for field in fields],
        "        this.capturedAt = capturedAt;",
        "        this.expiresAt = expiresAt;",
        "    }",
        "",
    ]
    for field in fields:
        body.extend(
            [
                f"    public String get{field[:1].upper() + field[1:]}() {{",
                f"        return {field};",
                "    }",
                "",
            ]
        )
    body.extend(
        [
            "    public Instant getCapturedAt() {",
            "        return capturedAt;",
            "    }",
            "",
            "    public Instant getExpiresAt() {",
            "        return expiresAt;",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=package_name,
        imports=["java.time.Instant"],
        body=body,
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_correlation_store(
    package_name: str,
    *,
    route: RouterRouteMetadata,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=package_name,
        imports=[
            "java.time.Instant",
            "java.util.ArrayList",
            "java.util.List",
            "java.util.concurrent.ConcurrentHashMap",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            "public class RoutingCorrelationStore {",
            "",
            "    private final ConcurrentHashMap<String, RoutingCorrelationRecord> pending = new ConcurrentHashMap<>();",
            "",
            f"    @Value(\"${{app.kafka.router.{route.name}.duplicate-correlation-policy:{route.duplicate_correlation_policy}}}\")",
            "    private String duplicatePolicy;",
            "",
            "    public void register(RoutingCorrelationRecord record) {",
            "        if (record == null || record.getCorrelationId() == null || record.getCorrelationId().isBlank()) {",
            "            throw new RouterBusinessException.InvalidCorrelationException(\"correlationId is required\");",
            "        }",
            "        String policy = normalizedDuplicatePolicy();",
            "        RoutingCorrelationRecord existing = pending.putIfAbsent(record.getCorrelationId(), record);",
            "        if (existing != null && \"reject-new\".equals(policy)) {",
            "            throw new RouterBusinessException.DuplicateCorrelationException(",
            "                    \"Duplicate correlationId: \" + record.getCorrelationId());",
            "        }",
            "        if (existing != null && \"accept-last\".equals(policy)) {",
            "            pending.put(record.getCorrelationId(), record);",
            "        }",
            "    }",
            "",
            "    private String normalizedDuplicatePolicy() {",
            "        if (duplicatePolicy == null || duplicatePolicy.isBlank()) {",
            f"            return {_java_string(route.duplicate_correlation_policy)};",
            "        }",
            "        String normalized = duplicatePolicy.trim();",
            "        if (\"reject-new\".equals(normalized) || \"accept-last\".equals(normalized)) {",
            "            return normalized;",
            "        }",
            "        throw new IllegalStateException(",
            "                \"Unsupported duplicate-correlation-policy: \" + duplicatePolicy",
            "                        + \". Supported values are reject-new and accept-last.\");",
            "    }",
            "",
            "    public RoutingCorrelationRecord retrieve(String correlationId) {",
            "        return pending.get(correlationId);",
            "    }",
            "",
            "    public void complete(String correlationId) {",
            "        pending.remove(correlationId);",
            "    }",
            "",
            "    public void cancel(String correlationId) {",
            "        pending.remove(correlationId);",
            "    }",
            "",
            "    public List<RoutingCorrelationRecord> evictExpired(Instant now) {",
            "        List<RoutingCorrelationRecord> expired = new ArrayList<>();",
            "        pending.forEach((correlationId, record) -> {",
            "            if (record.getExpiresAt().isBefore(now) || record.getExpiresAt().equals(now)) {",
            "                if (pending.remove(correlationId, record)) {",
            "                    expired.add(record);",
            "                }",
            "            }",
            "        });",
            "        return expired;",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_routing_rule_evaluator(
    package_name: str,
    *,
    route: RouterRouteMetadata,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    rule_lines = _router_rule_lines(route.routing_rules)
    default_return = (
        "        return new RoutingDecision(null, false);"
        if route.default_target is None
        else f"        return new RoutingDecision({_java_string(route.default_target)}, true);"
    )
    return _java_file(
        package_name=package_name,
        imports=[
            "java.math.BigDecimal",
            "java.util.List",
            "java.util.Map",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            "public class RoutingRuleEvaluator {",
            "",
            "    public RoutingDecision evaluate(Map<String, Object> routingFields) {",
            "        for (RoutingRule rule : rules()) {",
            "            if (rule.matches(routingFields)) {",
            "                return new RoutingDecision(rule.targetId(), false);",
            "            }",
            "        }",
            default_return,
            "    }",
            "",
            "    public record RoutingDecision(String targetId, boolean defaultTargetUsed) {",
            "    }",
            "",
            "    private List<RoutingRule> rules() {",
            "        return List.of(",
            *rule_lines,
            "        );",
            "    }",
            "",
            "    private record RoutingRule(String id, String targetId, List<Condition> conditions) {",
            "        boolean matches(Map<String, Object> routingFields) {",
            "            return conditions.stream().allMatch(condition -> condition.matches(routingFields));",
            "        }",
            "    }",
            "",
            "    private record Condition(String field, String operator, Object expected) {",
            "        boolean matches(Map<String, Object> routingFields) {",
            "            Object actual = routingFields.get(field);",
            "            return switch (operator) {",
            "                case \"eq\" -> valuesMatch(actual, expected);",
            "                case \"in\" -> expected instanceof List<?> values && actual != null",
            "                        && values.stream().anyMatch(value -> valuesMatch(actual, value));",
            "                case \"lt\" -> isComparable(actual, expected) && compare(actual, expected) < 0;",
            "                case \"lte\" -> isComparable(actual, expected) && compare(actual, expected) <= 0;",
            "                case \"gt\" -> isComparable(actual, expected) && compare(actual, expected) > 0;",
            "                case \"gte\" -> isComparable(actual, expected) && compare(actual, expected) >= 0;",
            "                case \"not_null\" -> actual != null;",
            "                default -> false;",
            "            };",
            "        }",
            "    }",
            "",
            "    private static boolean isComparable(Object actual, Object expected) {",
            "        return actual != null && expected != null;",
            "    }",
            "",
            "    private static boolean valuesMatch(Object actual, Object expected) {",
            "        if (actual == null || expected == null) {",
            "            return false;",
            "        }",
            "        if (isNumeric(actual) && isNumeric(expected)) {",
            "            return compare(actual, expected) == 0;",
            "        }",
            "        return actual.toString().equals(expected.toString());",
            "    }",
            "",
            "    private static boolean isNumeric(Object value) {",
            "        try {",
            "            new BigDecimal(value.toString());",
            "            return true;",
            "        } catch (NumberFormatException ex) {",
            "            return false;",
            "        }",
            "    }",
            "",
            "    private static int compare(Object actual, Object expected) {",
            "        return new BigDecimal(actual.toString()).compareTo(new BigDecimal(expected.toString()));",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_business_exception(
    package_name: str,
    *,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=package_name,
        imports=[],
        body=[
            "public class RouterBusinessException extends RuntimeException {",
            "",
            "    public RouterBusinessException(String message) {",
            "        super(message);",
            "    }",
            "",
            "    public static class ValidationFailedException extends RouterBusinessException {",
            "        public ValidationFailedException(String message) { super(message); }",
            "    }",
            "",
            "    public static class RoutingRuleNotFoundException extends RouterBusinessException {",
            "        public RoutingRuleNotFoundException(String message) { super(message); }",
            "    }",
            "",
            "    public static class DuplicateCorrelationException extends RouterBusinessException {",
            "        public DuplicateCorrelationException(String message) { super(message); }",
            "    }",
            "",
            "    public static class InvalidCorrelationException extends RouterBusinessException {",
            "        public InvalidCorrelationException(String message) { super(message); }",
            "    }",
            "",
            "    public static class InvalidReplyDestinationException extends RouterBusinessException {",
            "        public InvalidReplyDestinationException(String message) { super(message); }",
            "    }",
            "",
            "    public static class TransformMappingException extends RouterBusinessException {",
            "        public TransformMappingException(String message) { super(message); }",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_technical_exception(
    package_name: str,
    *,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=package_name,
        imports=[],
        body=[
            "public class RouterTechnicalException extends RuntimeException {",
            "",
            "    public RouterTechnicalException(String message, Throwable cause) {",
            "        super(message, cause);",
            "    }",
            "",
            "    public static class KafkaPublishException extends RouterTechnicalException {",
            "        public KafkaPublishException(String message, Throwable cause) { super(message, cause); }",
            "    }",
            "",
            "    public static class UnexpectedProcessingException extends RouterTechnicalException {",
            "        public UnexpectedProcessingException(String message, Throwable cause) { super(message, cause); }",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_nack_publisher(
    package_name: str,
    *,
    route: RouterRouteMetadata,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    per_source_items = sorted(route.nack_routing.per_source_system.items())
    per_source_entries = [
        "            "
        + f"Map.entry({_java_string(source)}, {_java_string(topic)})"
        + ("," if index < len(per_source_items) - 1 else "")
        for index, (source, topic) in enumerate(per_source_items)
    ]
    if not per_source_entries:
        per_source_entries = ["            // no per-source entries configured"]
    return _java_file(
        package_name=package_name,
        imports=[
            "java.time.Instant",
            "java.util.LinkedHashMap",
            "java.util.Map",
            "java.util.concurrent.ExecutionException",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.kafka.core.KafkaTemplate",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            "public class NackPublisher {",
            "",
            "    private final KafkaTemplate<String, Object> kafkaTemplate;",
            f"    private final String mode = {_java_string(route.nack_routing.mode)};",
            "",
            f"    @Value(\"${{app.kafka.router.{route.name}.nack.fixed-topic}}\")",
            "    private String fixedTopic;",
            "",
            f"    @Value(\"${{app.kafka.router.{route.name}.nack.default-error-topic}}\")",
            "    private String defaultErrorTopic;",
            "",
            "    private final Map<String, String> perSourceSystem = Map.ofEntries(",
            *per_source_entries,
            "    );",
            "",
            "    public NackPublisher(KafkaTemplate<String, Object> kafkaTemplate) {",
            "        this.kafkaTemplate = kafkaTemplate;",
            "    }",
            "",
            "    public void publishNack(",
            "            String sourceSystem,",
            "            String replyDestination,",
            "            boolean replyDestinationValid,",
            "            String correlationId,",
            "            String errorCode,",
            "            String errorReason,",
            "            String businessFlow,",
            "            String selectedTarget,",
            "            String validationBoundary,",
            "            String originalPayloadRef) {",
            "        String destination = resolveDestination(sourceSystem, replyDestination, replyDestinationValid);",
            "        Map<String, Object> envelope = new LinkedHashMap<>();",
            "        envelope.put(\"correlationId\", correlationId);",
            "        envelope.put(\"errorCode\", errorCode);",
            "        envelope.put(\"errorReason\", errorReason);",
            "        envelope.put(\"sourceSystem\", sourceSystem);",
            "        envelope.put(\"replyDestination\", replyDestination);",
            "        envelope.put(\"businessFlow\", businessFlow);",
            "        envelope.put(\"selectedTarget\", selectedTarget);",
            "        envelope.put(\"validationBoundary\", validationBoundary);",
            "        envelope.put(\"timestamp\", Instant.now().toString());",
            "        envelope.put(\"payloadLoggingPolicy\", \"none\");",
            "        if (originalPayloadRef != null && !originalPayloadRef.isBlank()) {",
            "            envelope.put(\"originalPayloadRef\", originalPayloadRef);",
            "        }",
            "        waitForPublish(destination, envelope);",
            "    }",
            "",
            "    private void waitForPublish(String destination, Map<String, Object> envelope) {",
            "        try {",
            "            kafkaTemplate.send(destination, envelope).get();",
            "        } catch (InterruptedException ex) {",
            "            Thread.currentThread().interrupt();",
            "            throw new RouterTechnicalException.KafkaPublishException(",
            "                    \"Failed to publish router NACK to topic \" + destination, ex);",
            "        } catch (ExecutionException ex) {",
            "            throw new RouterTechnicalException.KafkaPublishException(",
            "                    \"Failed to publish router NACK to topic \" + destination, ex);",
            "        }",
            "    }",
            "",
            "    String resolveDestination(String sourceSystem, String replyDestination, boolean replyDestinationValid) {",
            "        if (!replyDestinationValid || replyDestination == null || replyDestination.isBlank()) {",
            "            return defaultErrorTopic;",
            "        }",
            "        return switch (mode) {",
            "            case \"same_as_reply\" -> replyDestination;",
            "            case \"per_source_system\" -> perSourceSystem.getOrDefault(sourceSystem, defaultErrorTopic);",
            "            case \"fixed\" -> fixedTopic;",
            "            case \"default_error\" -> defaultErrorTopic;",
            "            default -> defaultErrorTopic;",
            "        };",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_json_schema_validator(
    package_name: str,
    *,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    if is_boot41(target_profile_name):
        return _render_preview_json_schema_validator(
            package_name, target_profile_name=target_profile_name,
            source_manifest=source_manifest, generation_run_id=generation_run_id,
        )
    return _java_file(
        package_name=package_name,
        imports=[
            "com.fasterxml.jackson.databind.JsonNode",
            "com.fasterxml.jackson.databind.ObjectMapper",
            "com.networknt.schema.JsonSchema",
            "com.networknt.schema.JsonSchemaFactory",
            "com.networknt.schema.SpecVersion",
            "com.networknt.schema.ValidationMessage",
            "java.io.InputStream",
            "java.util.Set",
            "java.util.concurrent.ConcurrentHashMap",
            "java.util.concurrent.ConcurrentMap",
            "org.springframework.core.io.ClassPathResource",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            "public class RouterJsonSchemaValidator {",
            "",
            "    private final ObjectMapper objectMapper;",
            "    private final ConcurrentMap<String, JsonSchema> schemaCache = new ConcurrentHashMap<>();",
            "",
            "    public RouterJsonSchemaValidator(ObjectMapper objectMapper) {",
            "        this.objectMapper = objectMapper;",
            "    }",
            "",
            "    public void validate(String payload, String schemaRef, String boundary) {",
            "        try {",
            "            JsonNode payloadNode = objectMapper.readTree(payload);",
            "            JsonSchema schema = schemaCache.computeIfAbsent(schemaRef, this::loadSchema);",
            "            Set<ValidationMessage> errors = schema.validate(payloadNode);",
            "            if (!errors.isEmpty()) {",
            "                throw new RouterBusinessException.ValidationFailedException(",
            "                        boundary + \" validation failed for schema \" + schemaRef + \": \" + errors);",
            "            }",
            "        } catch (RouterBusinessException.ValidationFailedException ex) {",
            "            throw ex;",
            "        } catch (Exception ex) {",
            "            throw new RouterBusinessException.ValidationFailedException(",
            "                    boundary + \" validation failed for schema \" + schemaRef + \": \" + ex.getMessage());",
            "        }",
            "    }",
            "",
            "    private JsonSchema loadSchema(String schemaRef) {",
            "        ClassPathResource schemaResource = new ClassPathResource(schemaRef);",
            "        try (InputStream schemaStream = schemaResource.getInputStream()) {",
            "            JsonNode schemaNode = objectMapper.readTree(schemaStream);",
            "            SpecVersion.VersionFlag version = detectSchemaVersion(schemaNode);",
            "            return JsonSchemaFactory.getInstance(version).getSchema(schemaNode);",
            "        } catch (Exception ex) {",
            "            throw new IllegalStateException(",
            "                    \"Unable to load schema \" + schemaRef + \": \" + ex.getMessage(), ex);",
            "        }",
            "    }",
            "",
            "    private SpecVersion.VersionFlag detectSchemaVersion(JsonNode schemaNode) {",
            "        JsonNode declaration = schemaNode == null ? null : schemaNode.get(\"$schema\");",
            "        if (declaration == null || !declaration.isTextual()) {",
            "            return SpecVersion.VersionFlag.V7;",
            "        }",
            "        String schemaUri = declaration.asText();",
            "        if (schemaUri.contains(\"2020-12\")) {",
            "            return SpecVersion.VersionFlag.V202012;",
            "        }",
            "        if (schemaUri.contains(\"draft-07\") || schemaUri.contains(\"draft/7\")) {",
            "            return SpecVersion.VersionFlag.V7;",
            "        }",
            "        return SpecVersion.VersionFlag.V7;",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_preview_json_schema_validator(
    package_name: str,
    *,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=package_name,
        imports=[
            "tools.jackson.databind.JsonNode",
            "tools.jackson.databind.ObjectMapper",
            "tools.jackson.databind.node.ObjectNode",
            "com.networknt.schema.Error",
            "com.networknt.schema.Schema",
            "com.networknt.schema.SchemaRegistry",
            "com.networknt.schema.SchemaRegistryConfig",
            "com.networknt.schema.SpecificationVersion",
            "com.networknt.schema.resource.SchemaLoader",
            "java.io.InputStream",
            "java.util.List",
            "java.util.concurrent.ConcurrentHashMap",
            "java.util.concurrent.ConcurrentMap",
            "org.springframework.core.io.ClassPathResource",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            "public class RouterJsonSchemaValidator {",
            "    private final ObjectMapper objectMapper;",
            "    private final ConcurrentMap<String, Schema> schemaCache = new ConcurrentHashMap<>();",
            "",
            "    public RouterJsonSchemaValidator(ObjectMapper objectMapper) {",
            "        this.objectMapper = objectMapper;",
            "    }",
            "",
            "    public void validate(String payload, String schemaRef, String boundary) {",
            "        try {",
            "            JsonNode payloadNode = objectMapper.readTree(payload);",
            "            Schema schema = schemaCache.computeIfAbsent(schemaRef, this::loadSchema);",
            "            List<Error> errors = schema.validate(payloadNode);",
            "            if (!errors.isEmpty()) {",
            "                throw new RouterBusinessException.ValidationFailedException(",
            "                        boundary + \" validation failed for schema \" + schemaRef + \": \" + errors);",
            "            }",
            "        } catch (RouterBusinessException.ValidationFailedException ex) {",
            "            throw ex;",
            "        } catch (Exception ex) {",
            "            throw new RouterBusinessException.ValidationFailedException(",
            "                    boundary + \" validation failed for schema \" + schemaRef + \": \" + ex.getMessage());",
            "        }",
            "    }",
            "",
            "    private Schema loadSchema(String schemaRef) {",
            "        try (InputStream input = new ClassPathResource(schemaRef).getInputStream()) {",
            "            ObjectNode node = (ObjectNode) objectMapper.readTree(input);",
            "            JsonNode declaration = node.get(\"$schema\");",
            "            SpecificationVersion version = declaration != null && declaration.isTextual()",
            "                    && declaration.asText().contains(\"2020-12\")",
            "                    ? SpecificationVersion.DRAFT_2020_12 : SpecificationVersion.DRAFT_7;",
            "            node.put(\"$schema\", version.getDialectId());",
            "            SchemaRegistry registry = SchemaRegistry.withDefaultDialect(version, builder -> builder",
            "                    .nodeReader(reader -> reader.jsonMapper(objectMapper))",
            "                    .schemaLoader(SchemaLoader.builder().build())",
            "                    .schemaRegistryConfig(SchemaRegistryConfig.builder()",
            "                            .typeLoose(false).formatAssertionsEnabled(true).build()));",
            "            return registry.getSchema(node);",
            "        } catch (Exception ex) {",
            "            throw new IllegalStateException(",
            "                    \"Unable to load schema \" + schemaRef + \": \" + ex.getMessage(), ex);",
            "        }",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_transform_service(
    package_name: str,
    *,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=package_name,
        imports=[
            "java.math.BigDecimal",
            "java.math.RoundingMode",
            "java.util.LinkedHashMap",
            "java.util.List",
            "java.util.Map",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            "public class RouterTransformService {",
            "",
            "    public Map<String, Object> transform(Map<String, Object> input, List<TransformMapping> mappings) {",
            "        Map<String, Object> output = new LinkedHashMap<>();",
            "        for (TransformMapping mapping : mappings) {",
            "            boolean hasConstant = mapping.constant() != null;",
            "            boolean hasSource = mapping.source() != null && input.containsKey(mapping.source());",
            "            Object value = hasConstant ? mapping.constant() : input.get(mapping.source());",
            "            if (value == null) {",
            "                value = mapping.defaultValue();",
            "            }",
            "            if (value == null && !hasConstant && !hasSource) {",
            "                continue;",
            "            }",
            "            if (mapping.typeCoercion() != null && value != null) {",
            "                value = applyTypeCoercion(value, mapping);",
            "            }",
            "            if (mapping.valueMap() != null && !mapping.valueMap().isEmpty() && value != null) {",
            "                if (!mapping.valueMap().containsKey(value.toString())) {",
            "                    throw new RouterBusinessException.TransformMappingException(",
            "                            \"Missing value_map entry for \" + mapping.source() + \"=\" + value);",
            "                }",
            "                value = mapping.valueMap().get(value.toString());",
            "            }",
            "            output.put(mapping.target(), value);",
            "        }",
            "        return output;",
            "    }",
            "",
            "    private Object applyTypeCoercion(Object value, TransformMapping mapping) {",
            "        try {",
            "            BigDecimal decimal = new BigDecimal(value.toString());",
            "            return switch (mapping.typeCoercion()) {",
            "                case \"major_to_minor_units\" -> decimal.multiply(BigDecimal.valueOf(100)).setScale(0, RoundingMode.HALF_UP).longValueExact();",
            "                case \"minor_to_major_units\" -> decimal.divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);",
            "                default -> throw new RouterBusinessException.TransformMappingException(",
            "                        \"Unsupported type_coercion: \" + mapping.typeCoercion());",
            "            };",
            "        } catch (NumberFormatException ex) {",
            "            throw coercionFailure(value, mapping, ex);",
            "        } catch (ArithmeticException ex) {",
            "            throw coercionFailure(value, mapping, ex);",
            "        } catch (IllegalArgumentException ex) {",
            "            throw coercionFailure(value, mapping, ex);",
            "        }",
            "    }",
            "",
            "    private RouterBusinessException.TransformMappingException coercionFailure(",
            "            Object value, TransformMapping mapping, RuntimeException cause) {",
            "        return new RouterBusinessException.TransformMappingException(",
            "                \"Failed to apply type_coercion '\" + mapping.typeCoercion()",
            "                        + \"' for target '\" + mapping.target()",
            "                        + \"' from \" + mappingSourceLabel(mapping)",
            "                        + \" with value '\" + value + \"': \" + cause.getMessage());",
            "    }",
            "",
            "    private String mappingSourceLabel(TransformMapping mapping) {",
            "        if (mapping.source() != null) {",
            "            return \"source '\" + mapping.source() + \"'\";",
            "        }",
            "        if (mapping.constant() != null) {",
            "            return \"constant\";",
            "        }",
            "        if (mapping.defaultValue() != null) {",
            "            return \"default\";",
            "        }",
            "        return \"unknown source\";",
            "    }",
            "",
            "    public record TransformMapping(",
            "            String source,",
            "            String target,",
            "            String defaultValue,",
            "            String constant,",
            "            Map<String, String> valueMap,",
            "            String typeCoercion) {",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )


def _router_rule_lines(rules: list[RouterRoutingRuleMetadata]) -> list[str]:
    lines: list[str] = []
    for rule_index, rule in enumerate(rules):
        suffix = "," if rule_index < len(rules) - 1 else ""
        lines.extend(
            [
                "                new RoutingRule(",
                f"                        {_java_string(rule.id)},",
                f"                        {_java_string(rule.target)},",
                "                        List.of(",
                *_router_condition_lines(rule.conditions),
                f"                        )){suffix}",
            ]
        )
    return lines


def _router_condition_lines(conditions: list[RouterRoutingConditionMetadata]) -> list[str]:
    lines: list[str] = []
    for condition_index, condition in enumerate(conditions):
        suffix = "," if condition_index < len(conditions) - 1 else ""
        lines.append(
            "                                new Condition("
            f"{_java_string(condition.field)}, "
            f"{_java_string(condition.operator)}, "
            f"{_java_object_literal(condition.value)}){suffix}"
        )
    return lines


def _java_object_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "List.of(" + ", ".join(_java_object_literal(item) for item in value) + ")"
    return _java_string(str(value))


def _java_string(value: str) -> str:
    return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""


def transform_mapping_specs(mappings: list[KafkaTransformMapping]) -> list[str]:
    """Render mapping specs for future route wiring tests."""

    return [
        "new RouterTransformService.TransformMapping("
        f"{_java_nullable_string(_normalize_json_field_path(mapping.source))}, "
        f"{_java_string(_normalize_json_field_path(mapping.target) or mapping.target)}, "
        f"{_java_nullable_string(mapping.default)}, "
        f"{_java_nullable_string(mapping.constant)}, "
        f"{_java_map_literal(mapping.value_map)}, "
        f"{_java_nullable_string(mapping.type_coercion)})"
        for mapping in mappings
    ]


def _java_nullable_string(value: str | None) -> str:
    return "null" if value is None else _java_string(value)


def _java_map_literal(values: dict[str, str] | None) -> str:
    if values is None:
        return "null"
    if not values:
        return "Map.of()"
    entries = ", ".join(
        f"{_java_string(key)}, {_java_string(value)}" for key, value in sorted(values.items())
    )
    return f"Map.of({entries})"


def _normalize_json_field_path(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized.startswith("$."):
        normalized = normalized[2:]
    elif normalized.startswith("$"):
        normalized = normalized[1:]
    return normalized.lstrip(".")


def _java_identifier(value: str, *, upper_camel: bool) -> str:
    parts = [part for part in re.split(r"[^a-zA-Z0-9]+", value) if part]
    candidate = "".join(part[:1].upper() + part[1:] for part in parts) or "Value"
    if candidate[0].isdigit():
        candidate = f"Generated{candidate}"
    if upper_camel:
        return candidate
    return candidate[:1].lower() + candidate[1:]
