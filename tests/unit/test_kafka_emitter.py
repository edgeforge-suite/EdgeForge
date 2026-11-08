from pathlib import Path

from appbuilder.contracts import load_project_definition
from appbuilder.generation.engine import generate_application
from appbuilder.generation.kafka_emitter import emit
from appbuilder.metadata.kafka_translation import translate_kafka_project


def test_kafka_emitter_generates_expected_files() -> None:
    files = emit(_fixture_metadata())

    assert "src/main/java/com/appbuilder/payment_mediation/PaymentMediationAdapterApplication.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/config/KafkaConsumerConfig.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/config/KafkaProducerConfig.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/consumer/PaymentInitiatedConsumer.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/producer/PaymentInitiatedProducer.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/transform/PaymentInitiatedTransformer.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/dto/inbound/PaymentInitiated.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/dto/outbound/SettlementRequest.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/consumer/BalanceUpdatedConsumer.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/producer/BalanceUpdatedProducer.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/transform/BalanceUpdatedTransformer.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/dto/inbound/BalanceUpdated.java" in files
    assert "src/main/java/com/appbuilder/payment_mediation/dto/outbound/LedgerUpdate.java" in files


def test_kafka_emitter_consumer_uses_manual_ack() -> None:
    files = emit(_fixture_metadata())

    consumer_config = files[
        "src/main/java/com/appbuilder/payment_mediation/config/KafkaConsumerConfig.java"
    ]
    consumer = files[
        "src/main/java/com/appbuilder/payment_mediation/consumer/PaymentInitiatedConsumer.java"
    ]
    assert "ContainerProperties.AckMode.MANUAL_IMMEDIATE" in consumer_config
    assert "acknowledgment.acknowledge();" in consumer


def test_kafka_emitter_consumes_raw_json_and_parses_with_object_mapper() -> None:
    files = emit(_fixture_metadata())

    consumer_config = files[
        "src/main/java/com/appbuilder/payment_mediation/config/KafkaConsumerConfig.java"
    ]
    consumer = files[
        "src/main/java/com/appbuilder/payment_mediation/consumer/PaymentInitiatedConsumer.java"
    ]
    assert "JsonDeserializer" not in consumer_config
    assert "TRUSTED_PACKAGES" not in consumer_config
    assert "ConsumerFactory<String, String>" in consumer_config
    assert "ConsumerRecord<String, String> record" in consumer
    assert "private final ObjectMapper objectMapper;" in consumer
    assert "objectMapper.readValue(" in consumer
    assert "record.value(), PaymentInitiated.class" in consumer
    assert "transformer.transform(inbound" in consumer


def test_kafka_emitter_logs_and_rethrows_consumer_failures() -> None:
    files = emit(_fixture_metadata())

    consumer = files[
        "src/main/java/com/appbuilder/payment_mediation/consumer/PaymentInitiatedConsumer.java"
    ]
    assert "log.error(\"Failed to process Kafka message" in consumer
    assert "throw new IllegalStateException(\"Failed to process Kafka message\", ex);" in consumer


def test_kafka_emitter_threads_generation_run_id() -> None:
    files = emit(_fixture_metadata(), generation_run_id="run-123")

    application = files[
        "src/main/java/com/appbuilder/payment_mediation/PaymentMediationAdapterApplication.java"
    ]
    assert "// Generation run: run-123" in application


def test_kafka_emitter_transformer_generates_field_copy() -> None:
    files = emit(_fixture_metadata())

    transformer = files[
        "src/main/java/com/appbuilder/payment_mediation/transform/PaymentInitiatedTransformer.java"
    ]
    assert "outbound.setSettlementAmount(inbound.getAmount());" in transformer


def test_kafka_emitter_transformer_generates_constant_injection() -> None:
    metadata = _fixture_metadata()
    metadata.routes[0].transform_mappings.append(
        metadata.routes[0].transform_mappings[0].model_copy(
            update={"source": None, "target": "channel", "constant": "KAFKA_BRIDGE"}
        )
    )

    transformer = emit(metadata)[
        "src/main/java/com/appbuilder/payment_mediation/transform/PaymentInitiatedTransformer.java"
    ]

    assert 'outbound.setChannel("KAFKA_BRIDGE");' in transformer
    assert "getChannel" not in transformer


def test_kafka_emitter_transformer_generates_value_map() -> None:
    metadata = _fixture_metadata()
    metadata.routes[0].transform_mappings.append(
        metadata.routes[0].transform_mappings[0].model_copy(
            update={
                "source": "paymentType",
                "target": "scheme",
                "value_map": {"INSTANT": "SCT_INST"},
            }
        )
    )

    transformer = emit(metadata)[
        "src/main/java/com/appbuilder/payment_mediation/transform/PaymentInitiatedTransformer.java"
    ]

    assert "private String mapScheme(String value)" in transformer
    assert 'case "INSTANT" -> "SCT_INST";' in transformer


def test_kafka_emitter_transformer_generates_major_to_minor_units() -> None:
    metadata = _fixture_metadata()
    metadata.routes[0].transform_mappings.append(
        metadata.routes[0].transform_mappings[0].model_copy(
            update={
                "source": "amount",
                "target": "amountMinorUnits",
                "type_coercion": "major_to_minor_units",
            }
        )
    )

    transformer = emit(metadata)[
        "src/main/java/com/appbuilder/payment_mediation/transform/PaymentInitiatedTransformer.java"
    ]

    assert ".multiply(java.math.BigDecimal.valueOf(100)).longValue()" in transformer


def test_kafka_emitter_producer_uses_correct_topic_property() -> None:
    files = emit(_fixture_metadata())

    producer = files[
        "src/main/java/com/appbuilder/payment_mediation/producer/PaymentInitiatedProducer.java"
    ]
    assert '@Value("${app.kafka.topics.payment-initiated.outbound}")' in producer


def test_kafka_emitter_resolves_partition_key_source_through_transform_mapping() -> None:
    files = emit(_fixture_metadata())

    consumer = files[
        "src/main/java/com/appbuilder/payment_mediation/consumer/PaymentInitiatedConsumer.java"
    ]
    assert "outbound.getAccountReference()" in consumer
    assert "outbound.getAccountId()" not in consumer


def test_generate_application_writes_kafka_app_files(tmp_path: Path) -> None:
    metadata = _fixture_metadata()

    report = generate_application(metadata, tmp_path / "PaymentMediationAdapter")

    assert report.harness_report is None
    assert (report.output_dir / "pom.xml").exists()
    assert (
        report.output_dir
        / "src/main/java/com/appbuilder/payment_mediation/consumer/PaymentInitiatedConsumer.java"
    ).exists()


def test_kafka_emitter_request_reply_generates_reply_consumer() -> None:
    files = emit(_request_reply_metadata())

    reply_consumer_path = (
        "src/main/java/com/appbuilder/payment_verification/consumer/"
        "AccountVerificationReplyConsumer.java"
    )
    assert reply_consumer_path in files
    assert "${app.kafka.topics.account-verification.downstream-reply}" in files[
        reply_consumer_path
    ]


def test_kafka_emitter_request_reply_reply_consumer_checks_correlation_store() -> None:
    files = emit(_request_reply_metadata())

    reply_consumer = files[
        "src/main/java/com/appbuilder/payment_verification/consumer/"
        "AccountVerificationReplyConsumer.java"
    ]
    assert "correlationStore.isExpired" in reply_consumer
    assert "acknowledgment.acknowledge()" in reply_consumer


def test_kafka_emitter_request_reply_generates_response_producer() -> None:
    files = emit(_request_reply_metadata())

    assert (
        "src/main/java/com/appbuilder/payment_verification/producer/"
        "AccountVerificationResponseProducer.java"
    ) in files


def test_kafka_emitter_request_reply_generates_correlation_store() -> None:
    files = emit(_request_reply_metadata())

    store = files[
        "src/main/java/com/appbuilder/payment_verification/correlation/"
        "AccountVerificationCorrelationStore.java"
    ]
    assert "ConcurrentHashMap" in store
    assert "In-memory only" in store
    assert "State is not persisted" in store
    assert "not suitable for clustered deployments" in store.lower()
    assert "evictExpired" in store
    assert "@Scheduled" in store


def test_kafka_emitter_request_reply_generates_reply_transformer() -> None:
    files = emit(_request_reply_metadata())

    transformer = files[
        "src/main/java/com/appbuilder/payment_verification/transform/"
        "AccountVerificationReplyTransformer.java"
    ]
    assert "outbound.setPaymentId(inbound.getRequestId());" in transformer
    assert "outbound.setApproved(inbound.getVerified());" in transformer


def test_kafka_emitter_request_reply_application_has_enable_scheduling() -> None:
    files = emit(_request_reply_metadata())

    app = files[
        "src/main/java/com/appbuilder/payment_verification/"
        "PaymentVerificationGatewayApplication.java"
    ]
    assert "@EnableScheduling" in app


def test_kafka_emitter_fire_and_forget_unchanged_by_request_reply_code() -> None:
    files = emit(_fire_and_forget_metadata())
    file_keys = str(files.keys())

    assert "CorrelationStore" not in file_keys
    assert "ReplyConsumer" not in file_keys
    assert "ResponseProducer" not in file_keys


def test_kafka_emitter_router_generates_response_path_files() -> None:
    files = emit(_router_metadata())

    assert "src/main/java/com/appbuilder/payments/router/RouterPatternListener.java" in files
    assert "src/main/java/com/appbuilder/payments/router/DownstreamResponseListener.java" in files
    assert "src/main/java/com/appbuilder/payments/router/CorrelationTimeoutScheduler.java" in files
    assert "src/main/java/com/appbuilder/payments/router/RoutingService.java" in files


def test_kafka_emitter_router_application_enables_scheduling() -> None:
    files = emit(_router_metadata())

    app = files["src/main/java/com/appbuilder/payments/PaymentRouterApplication.java"]

    assert "@EnableScheduling" in app


def test_kafka_emitter_no_retry_config_omits_error_handler() -> None:
    files = emit(_fixture_metadata())
    consumer_config = files[
        "src/main/java/com/appbuilder/payment_mediation/config/KafkaConsumerConfig.java"
    ]

    assert "DefaultErrorHandler" not in consumer_config
    assert "setCommonErrorHandler" not in consumer_config


def test_kafka_emitter_retry_config_generates_error_handler() -> None:
    files = emit(_retry_dlq_metadata())
    consumer_config = files[
        "src/main/java/com/appbuilder/payment_processing/config/KafkaConsumerConfig.java"
    ]

    assert "DefaultErrorHandler" in consumer_config
    assert "setCommonErrorHandler" in consumer_config
    assert "kafkaErrorHandler" in consumer_config


def test_kafka_emitter_exponential_backoff_generated_for_multiplier_gt_1() -> None:
    files = emit(_retry_dlq_metadata())
    consumer_config = files[
        "src/main/java/com/appbuilder/payment_processing/config/KafkaConsumerConfig.java"
    ]

    assert "ExponentialBackOffWithMaxRetries" in consumer_config
    assert "FixedBackOff" not in consumer_config


def test_kafka_emitter_dlq_generates_recoverer_and_dlq_template() -> None:
    files = emit(_retry_dlq_metadata())
    consumer_config = files[
        "src/main/java/com/appbuilder/payment_processing/config/KafkaConsumerConfig.java"
    ]

    assert "DeadLetterPublishingRecoverer" in consumer_config
    assert "dlqKafkaTemplate" in consumer_config
    assert ".dlq" in consumer_config


def test_kafka_emitter_fixed_backoff_generated_for_multiplier_eq_1() -> None:
    metadata = _retry_dlq_metadata()
    metadata = metadata.model_copy(
        update={
            "retry_policy": metadata.retry_policy.model_copy(  # type: ignore[union-attr]
                update={"backoff_multiplier": 1.0}
            )
        }
    )
    files = emit(metadata)
    consumer_config = files[
        "src/main/java/com/appbuilder/payment_processing/config/KafkaConsumerConfig.java"
    ]

    assert "FixedBackOff" in consumer_config
    assert "ExponentialBackOffWithMaxRetries" not in consumer_config


def test_kafka_emitter_retry_without_dlq_omits_recoverer() -> None:
    metadata = _retry_dlq_metadata().model_copy(update={"dlq_policy": None})
    files = emit(metadata)
    consumer_config = files[
        "src/main/java/com/appbuilder/payment_processing/config/KafkaConsumerConfig.java"
    ]

    assert "DefaultErrorHandler" in consumer_config
    assert "DeadLetterPublishingRecoverer" not in consumer_config
    assert "dlqKafkaTemplate" not in consumer_config


def _fixture_metadata():
    manifest = Path("tests/fixtures/kafka-integration/manifest.yaml")
    definition = load_project_definition(manifest)
    return translate_kafka_project(definition, project_root=manifest.parent)


def _fire_and_forget_metadata():
    return _fixture_metadata()


def _retry_dlq_metadata():
    manifest = Path("tests/fixtures/kafka-retry-dlq/manifest.yaml")
    definition = load_project_definition(manifest)
    return translate_kafka_project(definition, project_root=manifest.parent)


def _request_reply_metadata():
    manifest = Path("tests/fixtures/kafka-request-reply/manifest.yaml")
    definition = load_project_definition(manifest)
    return translate_kafka_project(definition, project_root=manifest.parent)


def _router_metadata():
    manifest = Path("tests/fixtures/kafka-router-contract/manifest.yaml")
    definition = load_project_definition(manifest)
    return translate_kafka_project(definition, project_root=manifest.parent)
