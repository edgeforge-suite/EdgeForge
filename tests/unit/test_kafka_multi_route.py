from pathlib import Path

from appbuilder.contracts import load_project_definition
from appbuilder.generation.kafka_build_emitter import emit as emit_build
from appbuilder.generation.kafka_emitter import emit as emit_sources
from appbuilder.metadata.kafka_translation import translate_kafka_project


def test_multi_route_generates_all_fire_and_forget_files() -> None:
    files = emit_sources(_fixture_metadata())

    for prefix in ("PaymentPosted", "PaymentReversed"):
        assert _java_path("consumer", f"{prefix}Consumer.java") in files
        assert _java_path("transform", f"{prefix}Transformer.java") in files
        assert _java_path("producer", f"{prefix}Producer.java") in files
        assert _java_path("consumer", f"{prefix}RequestConsumer.java") not in files
        assert _java_path("consumer", f"{prefix}ReplyConsumer.java") not in files
        assert _java_path("correlation", f"{prefix}CorrelationStore.java") not in files


def test_multi_route_generates_all_request_reply_files() -> None:
    files = emit_sources(_fixture_metadata())

    for prefix in ("AccountVerification", "FraudCheck"):
        assert _java_path("consumer", f"{prefix}RequestConsumer.java") in files
        assert _java_path("transform", f"{prefix}RequestTransformer.java") in files
        assert _java_path("producer", f"{prefix}RequestProducer.java") in files
        assert _java_path("consumer", f"{prefix}ReplyConsumer.java") in files
        assert _java_path("producer", f"{prefix}ResponseProducer.java") in files
        assert _java_path("correlation", f"{prefix}CorrelationStore.java") in files


def test_multi_route_generates_all_dto_files() -> None:
    files = emit_sources(_fixture_metadata())

    dto_paths = [path for path in files if "/dto/" in path and path.endswith(".java")]
    assert len(dto_paths) >= 12


def test_multi_route_no_dto_name_collisions() -> None:
    files = emit_sources(_fixture_metadata())

    dto_paths = [path for path in files if "/dto/" in path and path.endswith(".java")]
    assert len(dto_paths) == len(set(dto_paths))


def test_multi_route_application_java_has_scheduling_enabled() -> None:
    files = emit_sources(_fixture_metadata())

    application = files[
        "src/main/java/com/appbuilder/payment_mediation/PaymentMediationHubApplication.java"
    ]
    assert "@EnableScheduling" in application


def test_multi_route_consumer_config_has_error_handler() -> None:
    files = emit_sources(_fixture_metadata())
    consumer_config = files[
        "src/main/java/com/appbuilder/payment_mediation/config/KafkaConsumerConfig.java"
    ]

    assert "DefaultErrorHandler" in consumer_config
    assert "ExponentialBackOffWithMaxRetries" in consumer_config
    assert "DeadLetterPublishingRecoverer" in consumer_config
    assert "dlqKafkaTemplate" in consumer_config


def test_multi_route_pom_has_prometheus() -> None:
    files = emit_build(_fixture_metadata())
    assert "micrometer-registry-prometheus" in files["pom.xml"]


def test_multi_route_yaml_has_observation_enabled() -> None:
    files = emit_build(_fixture_metadata())
    assert "observation-enabled: true" in files["src/main/resources/application.yaml"]


def test_multi_route_yaml_has_dlq_topics_for_all_routes() -> None:
    yaml_content = emit_build(_fixture_metadata())["src/main/resources/application.yaml"]

    for route_name in ("payment-posted", "payment-reversed"):
        route_block = _route_block(yaml_content, route_name)
        assert "dlq:" in route_block
    for route_name in ("account-verification", "fraud-check"):
        route_block = _route_block(yaml_content, route_name)
        assert "dlq-inbound:" in route_block
        assert "dlq-reply:" in route_block


def test_multi_route_request_reply_routes_have_distinct_correlation_stores() -> None:
    files = emit_sources(_fixture_metadata())

    correlation_files = sorted(
        path for path in files if path.endswith("CorrelationStore.java")
    )
    assert correlation_files == [
        "src/main/java/com/appbuilder/payment_mediation/correlation/AccountVerificationCorrelationStore.java",
        "src/main/java/com/appbuilder/payment_mediation/correlation/FraudCheckCorrelationStore.java",
    ]


def test_multi_route_readme_documents_all_four_routes() -> None:
    readme = emit_build(_fixture_metadata())["README.md"]

    for route_name in (
        "payment-posted",
        "payment-reversed",
        "account-verification",
        "fraud-check",
    ):
        assert route_name in readme


def _fixture_metadata():
    manifest = Path("tests/fixtures/kafka-multi-route/manifest.yaml")
    definition = load_project_definition(manifest)
    return translate_kafka_project(definition, project_root=manifest.parent)


def _java_path(folder: str, filename: str) -> str:
    return f"src/main/java/com/appbuilder/payment_mediation/{folder}/{filename}"


def _route_block(yaml_content: str, route_name: str) -> str:
    lines = yaml_content.splitlines()
    marker = f"      {route_name}:"
    start_index = lines.index(marker)
    block_lines = [lines[start_index]]
    for line in lines[start_index + 1 :]:
        if line.startswith("      ") and not line.startswith("        "):
            break
        block_lines.append(line)
    return "\n".join(block_lines)
