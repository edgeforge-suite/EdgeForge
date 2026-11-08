"""Emit Java sources for the kafka-integration archetype."""

from __future__ import annotations

import re
from pathlib import Path

from appbuilder.metadata.kafka_models import (
    KafkaMetadata,
    KafkaTransformMapping,
    MessageField,
    MessageSchema,
    ResolvedAsyncRoute,
    RetryPolicy,
)

from .kafka_compatibility import is_boot41, jackson_import
from .kafka_router_components import (
    render_router_core_components,
    render_router_request_path_components,
)
from .utils import _java_file, package_path, to_pascal_case


def emit(
    metadata: KafkaMetadata,
    *,
    source_manifest: str = "metadata-project",
    generation_run_id: str = "kafka",
) -> dict[str, str]:
    """Return Java source files for a generated Kafka integration application."""

    root_path = Path("src") / "main" / "java" / package_path(metadata.java_package)
    files: dict[str, str] = {
        str(root_path / f"{_app_class_name(metadata)}Application.java"): _render_application(
            metadata,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "config" / "KafkaConsumerConfig.java"): _render_consumer_config(
            metadata,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
        str(root_path / "config" / "KafkaProducerConfig.java"): _render_producer_config(
            metadata,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
    }
    for route in metadata.routes:
        files[_dto_path(root_path, route.upstream_message)] = _render_dto(
            metadata,
            route.upstream_message,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
        files[_dto_path(root_path, route.downstream_message)] = _render_dto(
            metadata,
            route.downstream_message,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
        if route.pattern == "request-reply":
            if route.downstream_reply_message is None or route.upstream_reply_message is None:
                raise ValueError(
                    f"request-reply route '{route.name}' requires reply message schemas"
                )
            files[_dto_path(root_path, route.downstream_reply_message)] = _render_dto(
                metadata,
                route.downstream_reply_message,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
            files[_dto_path(root_path, route.upstream_reply_message)] = _render_dto(
                metadata,
                route.upstream_reply_message,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
            files[
                str(
                    root_path
                    / "transform"
                    / f"{route.route_class_prefix}RequestTransformer.java"
                )
            ] = _render_transformer(
                metadata,
                route,
                class_name=f"{route.route_class_prefix}RequestTransformer",
                inbound_schema=route.upstream_message,
                outbound_schema=route.downstream_message,
                mappings=route.transform_mappings,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
            files[
                str(root_path / "producer" / f"{route.route_class_prefix}RequestProducer.java")
            ] = _render_request_producer(
                metadata,
                route,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
            files[
                str(root_path / "consumer" / f"{route.route_class_prefix}RequestConsumer.java")
            ] = _render_request_consumer(
                metadata,
                route,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
            files[
                str(root_path / "transform" / f"{route.route_class_prefix}ReplyTransformer.java")
            ] = _render_transformer(
                metadata,
                route,
                class_name=f"{route.route_class_prefix}ReplyTransformer",
                inbound_schema=route.downstream_reply_message,
                outbound_schema=route.upstream_reply_message,
                mappings=route.response_transform_mappings or [],
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
            files[
                str(root_path / "producer" / f"{route.route_class_prefix}ResponseProducer.java")
            ] = _render_response_producer(
                metadata,
                route,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
            files[
                str(root_path / "consumer" / f"{route.route_class_prefix}ReplyConsumer.java")
            ] = _render_reply_consumer(
                metadata,
                route,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
            files[
                str(
                    root_path
                    / "correlation"
                    / f"{route.route_class_prefix}CorrelationStore.java"
                )
            ] = _render_correlation_store(
                metadata,
                route,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
            continue

        files[
            str(root_path / "transform" / f"{route.route_class_prefix}Transformer.java")
        ] = _render_transformer(
            metadata,
            route,
            class_name=f"{route.route_class_prefix}Transformer",
            inbound_schema=route.upstream_message,
            outbound_schema=route.downstream_message,
            mappings=route.transform_mappings,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
        files[
            str(root_path / "producer" / f"{route.route_class_prefix}Producer.java")
        ] = _render_producer(
            metadata,
            route,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
        files[
            str(root_path / "consumer" / f"{route.route_class_prefix}Consumer.java")
        ] = _render_consumer(
            metadata,
            route,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        )
    for route in metadata.router_routes:
        files.update(
            render_router_core_components(
                java_package=metadata.java_package,
                target_profile_name=metadata.target_profile_name,
                route=route,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
        )
        files.update(
            render_router_request_path_components(
                metadata=metadata,
                route=route,
                source_manifest=source_manifest,
                generation_run_id=generation_run_id,
            )
        )
    return files


def _render_application(
    metadata: KafkaMetadata,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    app_class = f"{_app_class_name(metadata)}Application"
    imports = [
        "org.springframework.boot.SpringApplication",
        "org.springframework.boot.autoconfigure.SpringBootApplication",
    ]
    annotations = ["@SpringBootApplication"]
    if _has_scheduled_components(metadata):
        imports.append("org.springframework.scheduling.annotation.EnableScheduling")
        annotations.append("@EnableScheduling")
    return _java_file(
        package_name=metadata.java_package,
        imports=imports,
        body=[
            *annotations,
            f"public class {app_class} {{",
            "",
            "    public static void main(String[] args) {",
            f"        SpringApplication.run({app_class}.class, args);",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_consumer_config(
    metadata: KafkaMetadata,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    retry_policy = metadata.retry_policy or RetryPolicy()
    dlq_policy = metadata.dlq_policy
    use_error_handler = metadata.retry_policy is not None or dlq_policy is not None
    use_exponential_backoff = retry_policy.backoff_multiplier > 1.0
    imports = [
        "java.util.HashMap",
        "java.util.Map",
        "org.apache.kafka.clients.consumer.ConsumerConfig",
        "org.apache.kafka.common.serialization.StringDeserializer",
        "org.springframework.beans.factory.annotation.Value",
        "org.springframework.context.annotation.Bean",
        "org.springframework.context.annotation.Configuration",
        "org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory",
        "org.springframework.kafka.core.ConsumerFactory",
        "org.springframework.kafka.core.DefaultKafkaConsumerFactory",
        "org.springframework.kafka.listener.ContainerProperties",
    ]
    body = [
        "@Configuration",
        "public class KafkaConsumerConfig {",
        "",
        "    @Value(\"${spring.kafka.bootstrap-servers}\")",
        "    private String bootstrapServers;",
        "",
        "    @Value(\"${spring.kafka.consumer.group-id}\")",
        "    private String groupId;",
        "",
        "    @Bean",
        "    public ConsumerFactory<String, String> consumerFactory() {",
        "        Map<String, Object> props = new HashMap<>();",
        "        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);",
        "        props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);",
        "        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, \"earliest\");",
        "        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);",
        "        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);",
        "        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);",
        "        return new DefaultKafkaConsumerFactory<>(props);",
        "    }",
    ]
    if dlq_policy is not None:
        imports.extend(
            [
                "org.apache.kafka.clients.producer.ProducerConfig",
                "org.apache.kafka.common.serialization.StringSerializer",
                "org.springframework.kafka.core.DefaultKafkaProducerFactory",
                "org.springframework.kafka.core.KafkaTemplate",
            ]
        )
        body.extend(
            [
                "",
                "    @Bean",
                "    public KafkaTemplate<String, String> dlqKafkaTemplate() {",
                "        Map<String, Object> props = new HashMap<>();",
                "        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);",
                "        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,",
                "                StringSerializer.class);",
                "        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,",
                "                StringSerializer.class);",
                "        props.put(ProducerConfig.ACKS_CONFIG, \"all\");",
                "        return new KafkaTemplate<>(new DefaultKafkaProducerFactory<>(props));",
                "    }",
            ]
        )
    if use_error_handler:
        imports.append("org.springframework.kafka.listener.DefaultErrorHandler")
        if use_exponential_backoff:
            imports.append("org.springframework.kafka.support.ExponentialBackOffWithMaxRetries")
        else:
            imports.append("org.springframework.util.backoff.FixedBackOff")
        if dlq_policy is not None:
            imports.append("org.springframework.kafka.listener.DeadLetterPublishingRecoverer")
        body.extend(
            [
                "",
                "    @Bean",
                "    public DefaultErrorHandler kafkaErrorHandler() {",
            ]
        )
        if use_exponential_backoff:
            body.extend(
                [
                    "        ExponentialBackOffWithMaxRetries backOff =",
                    f"                new ExponentialBackOffWithMaxRetries({retry_policy.max_attempts});",
                    f"        backOff.setInitialInterval({retry_policy.backoff_ms}L);",
                    f"        backOff.setMultiplier({retry_policy.backoff_multiplier});",
                ]
            )
        else:
            body.extend(
                [
                    f"        FixedBackOff backOff = new FixedBackOff({retry_policy.backoff_ms}L, {retry_policy.max_attempts}L);",
                ]
            )
        if dlq_policy is not None:
            body.extend(
                [
                    "        DeadLetterPublishingRecoverer recoverer = new DeadLetterPublishingRecoverer(",
                    "                dlqKafkaTemplate(),",
                    "                (record, ex) -> new org.apache.kafka.common.TopicPartition(",
                    f"                        record.topic() + \"{dlq_policy.topic_suffix}\", -1));",
                    "        return new DefaultErrorHandler(recoverer, backOff);",
                ]
            )
        else:
            body.append("        return new DefaultErrorHandler(backOff);")
        body.extend(["    }"])
    body.extend(
        [
            "",
            "    @Bean",
            "    public ConcurrentKafkaListenerContainerFactory<String, String> kafkaListenerContainerFactory() {",
            "        ConcurrentKafkaListenerContainerFactory<String, String> factory =",
            "                new ConcurrentKafkaListenerContainerFactory<>();",
            "        factory.setConsumerFactory(consumerFactory());",
            "        factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);",
            f"        factory.setConcurrency({metadata.concurrency});",
        ]
    )
    if use_error_handler:
        body.append("        factory.setCommonErrorHandler(kafkaErrorHandler());")
    body.extend(
        [
            "        return factory;",
            "    }",
            "}",
        ]
    )
    return _java_file(
        package_name=f"{metadata.java_package}.config",
        imports=sorted(set(imports)),
        body=body,
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_producer_config(
    metadata: KafkaMetadata,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    preview = is_boot41(metadata.target_profile_name)
    serializer = "JacksonJsonSerializer" if preview else "JsonSerializer"
    body = [
        "@Configuration",
        "public class KafkaProducerConfig {",
        "",
        "    @Value(\"${spring.kafka.bootstrap-servers}\")",
        "    private String bootstrapServers;",
        "",
        "    @Bean",
        "    public ProducerFactory<String, Object> producerFactory(JsonMapper objectMapper) {" if preview else "    public ProducerFactory<String, Object> producerFactory() {",
        "        Map<String, Object> props = new HashMap<>();",
        "        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);",
        "        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);",
        f"        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, {serializer}.class);",
        "        props.put(ProducerConfig.ACKS_CONFIG, \"all\");",
        "        return new DefaultKafkaProducerFactory<>(props, new StringSerializer()," if preview else "        return new DefaultKafkaProducerFactory<>(props);",
        *([
            "                new JacksonJsonSerializer<>(objectMapper.rebuild()",
            "                        .enable(DateTimeFeature.WRITE_DATES_AS_TIMESTAMPS).build()));",
        ] if preview else []),
        "    }",
        "",
        "    @Bean",
        "    public KafkaTemplate<String, Object> kafkaTemplate(ProducerFactory<String, Object> producerFactory) {" if preview else "    public KafkaTemplate<String, Object> kafkaTemplate() {",
        "        return new KafkaTemplate<>(producerFactory);" if preview else "        return new KafkaTemplate<>(producerFactory());",
        "    }",
    ]
    if _has_request_reply_routes(metadata):
        body.extend(
            [
                "",
                "    @Bean",
                "    public ProducerFactory<String, String> stringProducerFactory() {",
                "        Map<String, Object> props = new HashMap<>();",
                "        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);",
                "        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);",
                "        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);",
                "        props.put(ProducerConfig.ACKS_CONFIG, \"all\");",
                "        return new DefaultKafkaProducerFactory<>(props);",
                "    }",
                "",
                "    @Bean",
                "    public KafkaTemplate<String, String> kafkaStringTemplate() {",
                "        return new KafkaTemplate<>(stringProducerFactory());",
                "    }",
            ]
        )
    body.extend(["}", ""])
    return _java_file(
        package_name=f"{metadata.java_package}.config",
        imports=[
            *([
                "tools.jackson.databind.json.JsonMapper",
                "tools.jackson.databind.cfg.DateTimeFeature",
            ] if preview else []),
            "java.util.HashMap",
            "java.util.Map",
            "org.apache.kafka.clients.producer.ProducerConfig",
            "org.apache.kafka.common.serialization.StringSerializer",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.context.annotation.Bean",
            "org.springframework.context.annotation.Configuration",
            "org.springframework.kafka.core.DefaultKafkaProducerFactory",
            "org.springframework.kafka.core.KafkaTemplate",
            "org.springframework.kafka.core.ProducerFactory",
            f"org.springframework.kafka.support.serializer.{serializer}",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_dto(
    metadata: KafkaMetadata,
    schema: MessageSchema,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    imports = _imports_for_fields(schema.fields)
    body = [f"public class {schema.class_name} {{", ""]
    for field in schema.fields:
        body.append(f"    private {field.java_type} {field.name};")
    body.extend(["", f"    public {schema.class_name}() {{}}", ""])
    for field in schema.fields:
        suffix = to_pascal_case(field.name)
        body.extend(
            [
                f"    public {field.java_type} get{suffix}() {{",
                f"        return {field.name};",
                "    }",
                "",
                f"    public void set{suffix}({field.java_type} {field.name}) {{",
                f"        this.{field.name} = {field.name};",
                "    }",
                "",
            ]
        )
    body.append("}")
    return _java_file(
        package_name=_dto_package_name(metadata.java_package, schema.package_suffix),
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_transformer(
    metadata: KafkaMetadata,
    route: ResolvedAsyncRoute,
    *,
    class_name: str,
    inbound_schema: MessageSchema,
    outbound_schema: MessageSchema,
    mappings: list[KafkaTransformMapping],
    source_manifest: str,
    generation_run_id: str,
) -> str:
    uses_headers = _mappings_use_headers(mappings)
    method_params = f"{inbound_schema.class_name} inbound"
    if uses_headers:
        method_params += ", Headers headers"
    body = [
        "@Component",
        f"public class {class_name} {{",
        "",
        f"    public {outbound_schema.class_name} transform({method_params}) {{",
        f"        {outbound_schema.class_name} outbound = new {outbound_schema.class_name}();",
    ]
    helper_methods: list[str] = []
    for mapping in mappings:
        body.append(_transform_assignment(mapping))
        if mapping.value_map:
            helper_methods.extend(_value_map_helper(mapping))
    body.extend(
        [
            "        return outbound;",
            "    }",
        ]
    )
    if helper_methods:
        body.append("")
        body.extend(helper_methods)
    body.append("}")
    imports = [
        _dto_import(metadata.java_package, inbound_schema),
        _dto_import(metadata.java_package, outbound_schema),
        "org.springframework.stereotype.Component",
    ]
    if uses_headers:
        imports.append("org.apache.kafka.common.header.Headers")
    return _java_file(
        package_name=f"{metadata.java_package}.transform",
        imports=imports,
        body=body,
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_producer(
    metadata: KafkaMetadata,
    route: ResolvedAsyncRoute,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=f"{metadata.java_package}.producer",
        imports=[
            _dto_import(metadata.java_package, route.downstream_message),
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.kafka.core.KafkaTemplate",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            f"public class {route.route_class_prefix}Producer {{",
            "",
            "    private final KafkaTemplate<String, Object> kafkaTemplate;",
            "",
            f"    @Value(\"${{app.kafka.topics.{route.name}.outbound}}\")",
            "    private String topic;",
            "",
            f"    public {route.route_class_prefix}Producer(KafkaTemplate<String, Object> kafkaTemplate) {{",
            "        this.kafkaTemplate = kafkaTemplate;",
            "    }",
            "",
            f"    public void send({route.downstream_message.class_name} message, String partitionKey) {{",
            "        kafkaTemplate.send(topic, partitionKey, message);",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_request_producer(
    metadata: KafkaMetadata,
    route: ResolvedAsyncRoute,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    header_name = _correlation_header_name(route)
    return _java_file(
        package_name=f"{metadata.java_package}.producer",
        imports=[
            _dto_import(metadata.java_package, route.downstream_message),
            "java.nio.charset.StandardCharsets",
            "org.apache.kafka.clients.producer.ProducerRecord",
            "org.apache.kafka.common.header.internals.RecordHeader",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.kafka.core.KafkaTemplate",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            f"public class {route.route_class_prefix}RequestProducer {{",
            "",
            "    private final KafkaTemplate<String, Object> kafkaTemplate;",
            "",
            f"    @Value(\"${{app.kafka.topics.{route.name}.outbound}}\")",
            "    private String topic;",
            "",
            f"    public {route.route_class_prefix}RequestProducer(KafkaTemplate<String, Object> kafkaTemplate) {{",
            "        this.kafkaTemplate = kafkaTemplate;",
            "    }",
            "",
            f"    public void send({route.downstream_message.class_name} message, String correlationId, String partitionKey) {{",
            "        ProducerRecord<String, Object> record =",
            "                new ProducerRecord<>(topic, partitionKey, message);",
            f"        record.headers().add(new RecordHeader(\"{header_name}\", correlationId.getBytes(StandardCharsets.UTF_8)));",
            "        kafkaTemplate.send(record);",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_response_producer(
    metadata: KafkaMetadata,
    route: ResolvedAsyncRoute,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    upstream_reply_message = _require_reply_schema(route.upstream_reply_message, route.name)
    header_name = _correlation_header_name(route)
    return _java_file(
        package_name=f"{metadata.java_package}.producer",
        imports=[
            jackson_import(metadata.target_profile_name, "core.JacksonException" if is_boot41(metadata.target_profile_name) else "core.JsonProcessingException"),
            jackson_import(metadata.target_profile_name, "databind.ObjectMapper"),
            _dto_import(metadata.java_package, upstream_reply_message),
            "java.nio.charset.StandardCharsets",
            "org.apache.kafka.clients.producer.ProducerRecord",
            "org.apache.kafka.common.header.internals.RecordHeader",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.kafka.core.KafkaTemplate",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "@Component",
            f"public class {route.route_class_prefix}ResponseProducer {{",
            "",
            "    private final KafkaTemplate<String, String> kafkaStringTemplate;",
            "    private final ObjectMapper objectMapper;",
            "",
            f"    @Value(\"${{app.kafka.topics.{route.name}.upstream-reply}}\")",
            "    private String topic;",
            "",
            f"    public {route.route_class_prefix}ResponseProducer(",
            "            KafkaTemplate<String, String> kafkaStringTemplate,",
            "            ObjectMapper objectMapper) {",
            "        this.kafkaStringTemplate = kafkaStringTemplate;",
            "        this.objectMapper = objectMapper;",
            "    }",
            "",
            f"    public void send({upstream_reply_message.class_name} message, String correlationId) {{",
            "        try {",
            "            String payload = objectMapper.writeValueAsString(message);",
            "            ProducerRecord<String, String> record =",
            "                    new ProducerRecord<>(topic, correlationId, payload);",
            f"            record.headers().add(new RecordHeader(\"{header_name}\", correlationId.getBytes(StandardCharsets.UTF_8)));",
            "            kafkaStringTemplate.send(record);",
            f"        }} catch ({'JacksonException' if is_boot41(metadata.target_profile_name) else 'JsonProcessingException'} ex) {{",
            "            throw new IllegalStateException(\"Failed to serialize reply message\", ex);",
            "        }",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_consumer(
    metadata: KafkaMetadata,
    route: ResolvedAsyncRoute,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    partition_key_expression = _partition_key_expression(route)
    transformer_call = "transformer.transform(inbound, record.headers())"
    if not _route_uses_headers(route):
        transformer_call = "transformer.transform(inbound)"
    body = [
        "@Component",
        f"public class {route.route_class_prefix}Consumer {{",
        "",
        f"    private static final Logger log = LoggerFactory.getLogger({route.route_class_prefix}Consumer.class);",
        "",
        f"    private final {route.route_class_prefix}Transformer transformer;",
        f"    private final {route.route_class_prefix}Producer producer;",
        "    private final ObjectMapper objectMapper;",
        "",
        f"    public {route.route_class_prefix}Consumer({route.route_class_prefix}Transformer transformer,",
        f"                                      {route.route_class_prefix}Producer producer,",
        "                                      ObjectMapper objectMapper) {",
        "        this.transformer = transformer;",
        "        this.producer = producer;",
        "        this.objectMapper = objectMapper;",
        "    }",
        "",
        "    @KafkaListener(",
        f"            topics = \"${{app.kafka.topics.{route.name}.inbound}}\",",
        "            containerFactory = \"kafkaListenerContainerFactory\"",
        "    )",
        "    public void consume(ConsumerRecord<String, String> record,",
        "                        Acknowledgment acknowledgment) {",
        "        MDC.put(\"sourceTopic\", record.topic());",
        "        MDC.put(\"partition\", String.valueOf(record.partition()));",
        "        MDC.put(\"offset\", String.valueOf(record.offset()));",
        "        try {",
        "            log.info(\"Received message from topic={} partition={} offset={}\",",
        "                    record.topic(), record.partition(), record.offset());",
        f"            {route.upstream_message.class_name} inbound = objectMapper.readValue(",
        f"                    record.value(), {route.upstream_message.class_name}.class);",
        f"            {route.downstream_message.class_name} outbound = {transformer_call};",
        f"            producer.send(outbound, {partition_key_expression});",
        "            acknowledgment.acknowledge();",
        "        } catch (Exception ex) {",
        "            log.error(\"Failed to process Kafka message from topic={} partition={} offset={}\",",
        "                    record.topic(), record.partition(), record.offset(), ex);",
        "            throw new IllegalStateException(\"Failed to process Kafka message\", ex);",
        "        } finally {",
        "            MDC.clear();",
        "        }",
        "    }",
        "}",
    ]
    return _java_file(
        package_name=f"{metadata.java_package}.consumer",
        imports=[
            jackson_import(metadata.target_profile_name, "databind.ObjectMapper"),
            _dto_import(metadata.java_package, route.upstream_message),
            _dto_import(metadata.java_package, route.downstream_message),
            f"{metadata.java_package}.producer.{route.route_class_prefix}Producer",
            f"{metadata.java_package}.transform.{route.route_class_prefix}Transformer",
            "org.apache.kafka.clients.consumer.ConsumerRecord",
            "org.slf4j.Logger",
            "org.slf4j.LoggerFactory",
            "org.slf4j.MDC",
            "org.springframework.kafka.annotation.KafkaListener",
            "org.springframework.kafka.support.Acknowledgment",
            "org.springframework.stereotype.Component",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_request_consumer(
    metadata: KafkaMetadata,
    route: ResolvedAsyncRoute,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    partition_key_expression = _partition_key_expression(route)
    transformer_call = "requestTransformer.transform(inbound, record.headers())"
    if not _route_uses_headers(route):
        transformer_call = "requestTransformer.transform(inbound)"
    body = [
        "@Component",
        f"public class {route.route_class_prefix}RequestConsumer {{",
        "",
        f"    private static final Logger log = LoggerFactory.getLogger({route.route_class_prefix}RequestConsumer.class);",
        "",
        f"    private final {route.route_class_prefix}RequestTransformer requestTransformer;",
        f"    private final {route.route_class_prefix}RequestProducer requestProducer;",
        f"    private final {route.route_class_prefix}CorrelationStore correlationStore;",
        "    private final ObjectMapper objectMapper;",
        "",
        f"    public {route.route_class_prefix}RequestConsumer(",
        f"            {route.route_class_prefix}RequestTransformer requestTransformer,",
        f"            {route.route_class_prefix}RequestProducer requestProducer,",
        f"            {route.route_class_prefix}CorrelationStore correlationStore,",
        "            ObjectMapper objectMapper) {",
        "        this.requestTransformer = requestTransformer;",
        "        this.requestProducer = requestProducer;",
        "        this.correlationStore = correlationStore;",
        "        this.objectMapper = objectMapper;",
        "    }",
        "",
        "    @KafkaListener(",
        f"            topics = \"${{app.kafka.topics.{route.name}.inbound}}\",",
        "            containerFactory = \"kafkaListenerContainerFactory\"",
        "    )",
        "    public void consume(ConsumerRecord<String, String> record,",
        "                        Acknowledgment acknowledgment) {",
        "        MDC.put(\"sourceTopic\", record.topic());",
        "        MDC.put(\"partition\", String.valueOf(record.partition()));",
        "        MDC.put(\"offset\", String.valueOf(record.offset()));",
        "        try {",
        "            log.info(\"Received request message from topic={} partition={} offset={}\",",
        "                    record.topic(), record.partition(), record.offset());",
        f"            {route.upstream_message.class_name} inbound = objectMapper.readValue(",
        f"                    record.value(), {route.upstream_message.class_name}.class);",
        "            String correlationId = resolveCorrelationId(record, inbound);",
        "            correlationStore.register(correlationId);",
        f"            {route.downstream_message.class_name} outbound = {transformer_call};",
        f"            requestProducer.send(outbound, correlationId, {partition_key_expression});",
        "            acknowledgment.acknowledge();",
        "        } catch (Exception ex) {",
        "            log.error(\"Failed to process request message from topic={} partition={} offset={}\",",
        "                    record.topic(), record.partition(), record.offset(), ex);",
        "            throw new IllegalStateException(\"Failed to process request message\", ex);",
        "        } finally {",
        "            MDC.clear();",
        "        }",
        "    }",
        "",
        *_correlation_resolution_method_lines(route),
        "}",
    ]
    return _java_file(
        package_name=f"{metadata.java_package}.consumer",
        imports=[
            jackson_import(metadata.target_profile_name, "databind.ObjectMapper"),
            _dto_import(metadata.java_package, route.upstream_message),
            _dto_import(metadata.java_package, route.downstream_message),
            f"{metadata.java_package}.correlation.{route.route_class_prefix}CorrelationStore",
            f"{metadata.java_package}.producer.{route.route_class_prefix}RequestProducer",
            f"{metadata.java_package}.transform.{route.route_class_prefix}RequestTransformer",
            "java.nio.charset.StandardCharsets",
            "java.util.UUID",
            "org.apache.kafka.clients.consumer.ConsumerRecord",
            "org.apache.kafka.common.header.Header",
            "org.slf4j.Logger",
            "org.slf4j.LoggerFactory",
            "org.slf4j.MDC",
            "org.springframework.kafka.annotation.KafkaListener",
            "org.springframework.kafka.support.Acknowledgment",
            "org.springframework.stereotype.Component",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_reply_consumer(
    metadata: KafkaMetadata,
    route: ResolvedAsyncRoute,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    downstream_reply_message = _require_reply_schema(route.downstream_reply_message, route.name)
    upstream_reply_message = _require_reply_schema(route.upstream_reply_message, route.name)
    transformer_call = "replyTransformer.transform(inbound, record.headers())"
    if not _route_uses_response_headers(route):
        transformer_call = "replyTransformer.transform(inbound)"
    body = [
        "@Component",
        f"public class {route.route_class_prefix}ReplyConsumer {{",
        "",
        f"    private static final Logger log = LoggerFactory.getLogger({route.route_class_prefix}ReplyConsumer.class);",
        "",
        f"    private final {route.route_class_prefix}ReplyTransformer replyTransformer;",
        f"    private final {route.route_class_prefix}ResponseProducer responseProducer;",
        f"    private final {route.route_class_prefix}CorrelationStore correlationStore;",
        "    private final ObjectMapper objectMapper;",
        "",
        f"    public {route.route_class_prefix}ReplyConsumer(",
        f"            {route.route_class_prefix}ReplyTransformer replyTransformer,",
        f"            {route.route_class_prefix}ResponseProducer responseProducer,",
        f"            {route.route_class_prefix}CorrelationStore correlationStore,",
        "            ObjectMapper objectMapper) {",
        "        this.replyTransformer = replyTransformer;",
        "        this.responseProducer = responseProducer;",
        "        this.correlationStore = correlationStore;",
        "        this.objectMapper = objectMapper;",
        "    }",
        "",
        "    @KafkaListener(",
        f"            topics = \"${{app.kafka.topics.{route.name}.downstream-reply}}\",",
        "            containerFactory = \"kafkaListenerContainerFactory\"",
        "    )",
        "    public void consume(ConsumerRecord<String, String> record,",
        "                        Acknowledgment acknowledgment) {",
        "        MDC.put(\"sourceTopic\", record.topic());",
        "        MDC.put(\"partition\", String.valueOf(record.partition()));",
        "        MDC.put(\"offset\", String.valueOf(record.offset()));",
        "        try {",
        "            log.info(\"Received reply message from topic={} partition={} offset={}\",",
        "                    record.topic(), record.partition(), record.offset());",
        "            String correlationId = extractCorrelationId(record);",
        "            if (correlationStore.isExpired(correlationId)) {",
        "                log.warn(\"Dropping reply for expired/unknown correlationId={}\", correlationId);",
        "                acknowledgment.acknowledge();",
        "                return;",
        "            }",
        f"            {downstream_reply_message.class_name} inbound = objectMapper.readValue(",
        f"                    record.value(), {downstream_reply_message.class_name}.class);",
        f"            {upstream_reply_message.class_name} outbound = {transformer_call};",
        "            responseProducer.send(outbound, correlationId);",
        "            correlationStore.complete(correlationId);",
        "            acknowledgment.acknowledge();",
        "        } catch (Exception ex) {",
        "            log.error(\"Failed to process reply message from topic={} partition={} offset={}\",",
        "                    record.topic(), record.partition(), record.offset(), ex);",
        "            throw new IllegalStateException(\"Failed to process reply message\", ex);",
        "        } finally {",
        "            MDC.clear();",
        "        }",
        "    }",
        "",
        *_reply_correlation_extract_method_lines(route),
        "}",
    ]
    return _java_file(
        package_name=f"{metadata.java_package}.consumer",
        imports=[
            jackson_import(metadata.target_profile_name, "databind.ObjectMapper"),
            _dto_import(metadata.java_package, downstream_reply_message),
            _dto_import(metadata.java_package, upstream_reply_message),
            f"{metadata.java_package}.correlation.{route.route_class_prefix}CorrelationStore",
            f"{metadata.java_package}.producer.{route.route_class_prefix}ResponseProducer",
            f"{metadata.java_package}.transform.{route.route_class_prefix}ReplyTransformer",
            "java.nio.charset.StandardCharsets",
            "org.apache.kafka.clients.consumer.ConsumerRecord",
            "org.apache.kafka.common.header.Header",
            "org.slf4j.Logger",
            "org.slf4j.LoggerFactory",
            "org.slf4j.MDC",
            "org.springframework.kafka.annotation.KafkaListener",
            "org.springframework.kafka.support.Acknowledgment",
            "org.springframework.stereotype.Component",
        ],
        body=body,
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _render_correlation_store(
    metadata: KafkaMetadata,
    route: ResolvedAsyncRoute,
    *,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=f"{metadata.java_package}.correlation",
        imports=[
            "java.time.Duration",
            "java.time.Instant",
            "java.util.concurrent.ConcurrentHashMap",
            "org.springframework.beans.factory.annotation.Value",
            "org.springframework.scheduling.annotation.Scheduled",
            "org.springframework.stereotype.Component",
        ],
        body=[
            "/**",
            " * In-memory only. State is not persisted.",
            " * Requests in-flight at application restart will time out on the client side.",
            " * Not suitable for clustered deployments without an external store.",
            " */",
            "@Component",
            f"public class {route.route_class_prefix}CorrelationStore {{",
            "",
            "    private final ConcurrentHashMap<String, Instant> pending = new ConcurrentHashMap<>();",
            "    private final long timeoutMs;",
            "",
            f"    public {route.route_class_prefix}CorrelationStore(",
            f"            @Value(\"${{app.kafka.topics.{route.name}.timeout-ms}}\") long timeoutMs) {{",
            "        this.timeoutMs = timeoutMs;",
            "    }",
            "",
            "    public void register(String correlationId) {",
            "        pending.put(correlationId, Instant.now());",
            "    }",
            "",
            "    public boolean isExpired(String correlationId) {",
            "        if (correlationId == null || correlationId.isBlank()) {",
            "            return true;",
            "        }",
            "        Instant createdAt = pending.get(correlationId);",
            "        if (createdAt == null) {",
            "            return true;",
            "        }",
            "        return Duration.between(createdAt, Instant.now()).toMillis() > timeoutMs;",
            "    }",
            "",
            "    public void complete(String correlationId) {",
            "        if (correlationId != null) {",
            "            pending.remove(correlationId);",
            "        }",
            "    }",
            "",
            "    @Scheduled(fixedDelay = 60000)",
            "    void evictExpired() {",
            "        pending.entrySet().removeIf(",
            "                entry -> Duration.between(entry.getValue(), Instant.now()).toMillis() > timeoutMs);",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=metadata.target_profile_name,
        generation_run_id=generation_run_id,
    )


def _transform_assignment(mapping: KafkaTransformMapping) -> str:
    target_suffix = to_pascal_case(mapping.target)
    if mapping.constant is not None:
        return f"        outbound.set{target_suffix}({_java_literal(mapping.constant)});"
    if mapping.source is None:
        return f"        outbound.set{target_suffix}({_java_literal(mapping.default or '')});"
    if mapping.source.startswith("@header."):
        header_name = mapping.source.removeprefix("@header.")
        return (
            f"        outbound.set{target_suffix}(headers.lastHeader(\"{header_name}\") != null "
            f"? new String(headers.lastHeader(\"{header_name}\").value()) : null);"
        )
    source_suffix = to_pascal_case(mapping.source)
    if mapping.value_map:
        return f"        outbound.set{target_suffix}(map{target_suffix}(inbound.get{source_suffix}()));"
    if mapping.type_coercion == "major_to_minor_units":
        return (
            f"        outbound.set{target_suffix}(inbound.get{source_suffix}() != null "
            f"? inbound.get{source_suffix}().multiply(java.math.BigDecimal.valueOf(100)).longValue() : null);"
        )
    if mapping.type_coercion == "minor_to_major_units":
        return (
            f"        outbound.set{target_suffix}(inbound.get{source_suffix}() != null "
            f"? java.math.BigDecimal.valueOf(inbound.get{source_suffix}()).divide(java.math.BigDecimal.valueOf(100)) : null);"
        )
    if mapping.default is not None:
        return (
            f"        outbound.set{target_suffix}(inbound.get{source_suffix}() != null "
            f"? inbound.get{source_suffix}() : {_java_literal(mapping.default)});"
        )
    return f"        outbound.set{target_suffix}(inbound.get{source_suffix}());"


def _value_map_helper(mapping: KafkaTransformMapping) -> list[str]:
    target_suffix = to_pascal_case(mapping.target)
    lines = [
        f"    private String map{target_suffix}(String value) {{",
        "        if (value == null) {",
        "            return null;",
        "        }",
        "        return switch (value) {",
    ]
    for source, target in sorted((mapping.value_map or {}).items()):
        lines.append(
            f"            case \"{_escape_java_string(source)}\" -> \"{_escape_java_string(target)}\";"
        )
    lines.extend(
        [
            "            default -> value;",
            "        };",
            "    }",
        ]
    )
    return lines


def _imports_for_fields(fields: list[MessageField]) -> list[str]:
    imports: set[str] = set()
    for field in fields:
        if field.java_type == "BigDecimal":
            imports.add("java.math.BigDecimal")
        if field.java_type == "LocalDate":
            imports.add("java.time.LocalDate")
        if field.java_type == "OffsetDateTime":
            imports.add("java.time.OffsetDateTime")
    return sorted(imports)


def _partition_key_expression(route: ResolvedAsyncRoute) -> str:
    if route.partition_key_strategy == "field_value" and route.partition_key_source:
        partition_field = _resolve_outbound_partition_field(route)
        suffix = to_pascal_case(partition_field)
        return f"outbound.get{suffix}() != null ? outbound.get{suffix}().toString() : null"
    if route.partition_key_strategy == "correlation_id":
        return "record.key()"
    return "null"


def _resolve_outbound_partition_field(route: ResolvedAsyncRoute) -> str:
    downstream_fields = {field.name for field in route.downstream_message.fields}
    if route.partition_key_source in downstream_fields:
        return route.partition_key_source
    for mapping in route.transform_mappings:
        if mapping.source == route.partition_key_source and mapping.target in downstream_fields:
            return mapping.target
    return route.partition_key_source or ""


def _route_uses_headers(route: ResolvedAsyncRoute) -> bool:
    return _mappings_use_headers(route.transform_mappings)


def _route_uses_response_headers(route: ResolvedAsyncRoute) -> bool:
    return _mappings_use_headers(route.response_transform_mappings or [])


def _mappings_use_headers(mappings: list[KafkaTransformMapping]) -> bool:
    return any(
        mapping.source is not None and mapping.source.startswith("@header.")
        for mapping in mappings
    )


def _dto_path(root_path: Path, schema: MessageSchema) -> str:
    return str(
        root_path / "dto" / Path(*schema.package_suffix.split("/")) / f"{schema.class_name}.java"
    )


def _dto_package_name(java_package: str, package_suffix: str) -> str:
    return f"{java_package}.dto.{package_suffix.replace('/', '.')}"


def _dto_import(java_package: str, schema: MessageSchema) -> str:
    return f"{_dto_package_name(java_package, schema.package_suffix)}.{schema.class_name}"


def _has_request_reply_routes(metadata: KafkaMetadata) -> bool:
    return any(route.pattern == "request-reply" for route in metadata.routes)


def _has_scheduled_components(metadata: KafkaMetadata) -> bool:
    return _has_request_reply_routes(metadata) or bool(metadata.router_routes)


def _correlation_header_name(route: ResolvedAsyncRoute) -> str:
    return route.correlation_id_field_name or "correlationId"


def _correlation_resolution_method_lines(route: ResolvedAsyncRoute) -> list[str]:
    field_name = route.correlation_id_field_name or "correlationId"
    if route.correlation_id_source == "body_field":
        getter = to_pascal_case(field_name)
        return [
            f"    private String resolveCorrelationId(ConsumerRecord<String, String> record, {route.upstream_message.class_name} inbound) {{",
            f"        if (inbound.get{getter}() != null) {{",
            f"            return inbound.get{getter}().toString();",
            "        }",
            f'        log.warn("Missing correlation body field {field_name} for route {route.name}; generating UUID");',
            "        return UUID.randomUUID().toString();",
            "    }",
        ]
    return [
        f"    private String resolveCorrelationId(ConsumerRecord<String, String> record, {route.upstream_message.class_name} inbound) {{",
        f'        Header header = record.headers().lastHeader("{field_name}");',
        "        if (header != null) {",
        "            return new String(header.value(), StandardCharsets.UTF_8);",
        "        }",
        f'        log.warn("Missing correlation header {field_name} for route {route.name}; generating UUID");',
        "        return UUID.randomUUID().toString();",
        "    }",
    ]


def _reply_correlation_extract_method_lines(route: ResolvedAsyncRoute) -> list[str]:
    field_name = _correlation_header_name(route)
    return [
        "    private String extractCorrelationId(ConsumerRecord<String, String> record) {",
        f'        Header header = record.headers().lastHeader("{field_name}");',
        "        if (header == null) {",
        f'            log.warn("Reply message missing correlation header {field_name} for route {route.name}");',
        "            return null;",
        "        }",
        "        return new String(header.value(), StandardCharsets.UTF_8);",
        "    }",
    ]


def _require_reply_schema(schema: MessageSchema | None, route_name: str) -> MessageSchema:
    if schema is None:
        raise ValueError(f"request-reply route '{route_name}' requires reply schema metadata")
    return schema


def _app_class_name(metadata: KafkaMetadata) -> str:
    return to_pascal_case(metadata.app_name)


def _java_literal(value: str) -> str:
    if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return value
    return f"\"{_escape_java_string(value)}\""


def _escape_java_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
