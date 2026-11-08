from pathlib import Path

from appbuilder.contracts import load_project_definition
from appbuilder.generation import generate_application
from appbuilder.generation.kafka_build_emitter import emit
from appbuilder.metadata.kafka_translation import translate_kafka_project


def test_kafka_build_emitter_pom_contains_spring_kafka() -> None:
    files = emit(_fixture_metadata())

    assert "<artifactId>spring-boot-starter-kafka</artifactId>" in files["pom.xml"]


def test_kafka_build_emitter_pom_does_not_contain_jpa_or_flyway() -> None:
    files = emit(_fixture_metadata())

    assert "spring-boot-starter-data-jpa" not in files["pom.xml"]
    assert "flyway-core" not in files["pom.xml"]


def test_kafka_build_emitter_application_yaml_contains_topic_config() -> None:
    files = emit(_fixture_metadata())
    application_yaml = files["src/main/resources/application.yaml"]

    assert "app:" in application_yaml
    assert "    topics:" in application_yaml
    assert "payment-initiated:" in application_yaml
    assert "abc.payments.initiated.v1" in application_yaml
    assert "xyz.settlement.request.v1" in application_yaml


def test_kafka_build_emitter_application_yaml_hardens_health_and_shutdown() -> None:
    files = emit(_fixture_metadata())
    application_yaml = files["src/main/resources/application.yaml"]

    assert "server:\n  port: 8080\n  shutdown: graceful" in application_yaml
    assert "  lifecycle:\n    timeout-per-shutdown-phase: 30s" in application_yaml
    assert "      show-details: when-authorized" in application_yaml
    assert "      roles: ACTUATOR" in application_yaml
    assert "show-details: always" not in application_yaml


def test_kafka_build_emitter_dockerfile_runs_as_non_root() -> None:
    files = emit(_fixture_metadata())
    dockerfile = files["Dockerfile"]

    assert "RUN groupadd --system edgeforge && useradd --system --gid edgeforge" in dockerfile
    assert "COPY --from=build --chown=edgeforge:edgeforge" in dockerfile
    assert "RUN chown -R edgeforge:edgeforge /app" in dockerfile
    assert "USER edgeforge" in dockerfile
    assert dockerfile.index("USER edgeforge") < dockerfile.index("ENTRYPOINT")


def test_kafka_build_emitter_router_only_yaml_omits_empty_topics_and_adds_router_ops_config() -> None:
    files = emit(_router_metadata())
    application_yaml = files["src/main/resources/application.yaml"]

    assert "    topics:" not in application_yaml
    assert "    router:" in application_yaml
    assert "reply-destination:" in application_yaml
    assert "allowed-topics: ${ROUTER_PAYMENT_ROUTER_REPLY_ALLOWED_TOPICS:}" in application_yaml
    assert "allowed-prefixes: ${ROUTER_PAYMENT_ROUTER_REPLY_ALLOWED_PREFIXES:}" in application_yaml
    assert "duplicate-correlation-policy: ${ROUTER_PAYMENT_ROUTER_DUPLICATE_CORRELATION_POLICY:reject-new}" in application_yaml


def test_kafka_build_emitter_mixed_yaml_keeps_topics_and_router_sections() -> None:
    non_router = _fixture_metadata()
    router = _router_metadata()
    mixed = non_router.model_copy(update={"router_routes": router.router_routes})

    files = emit(mixed)
    application_yaml = files["src/main/resources/application.yaml"]

    assert "    topics:" in application_yaml
    assert "payment-initiated:" in application_yaml
    assert "    router:" in application_yaml
    assert "payment_router:" in application_yaml


def test_kafka_build_emitter_readme_states_at_least_once_semantics() -> None:
    files = emit(_fixture_metadata())
    readme = files["README.md"]

    assert "at-least-once" in readme
    assert "Exactly-once end-to-end semantics are not provided" in readme
    assert "does not emit the CRUD `Service`/`ServiceBase` extension seam" in readme


def test_kafka_build_emitter_readme_warns_about_tls_gateway() -> None:
    files = emit(_fixture_metadata())
    readme = files["README.md"]

    assert "plain HTTP and no built-in authentication" in readme
    assert "TLS-terminating, authenticated gateway" in readme
    assert "application port must be unreachable except through that gateway" in readme
    assert "All authenticated callers share one authorization domain" in readme
    assert "Multi-tenant, per-user, object-level, and row-level authorization" in readme
    assert "`config/SecurityHeadersFilter.java` is a security control" in readme
    assert "`X-Content-Type-Options: nosniff`" in readme
    assert "`X-Frame-Options: DENY`" in readme
    assert "`Referrer-Policy: no-referrer`" in readme
    assert "`Content-Security-Policy: frame-ancestors 'none'`" in readme
    assert "does not emit `Strict-Transport-Security`" in readme
    assert "configure HSTS at the TLS-terminating gateway" in readme
    assert "Rate limiting is gateway-owned" in readme
    assert "trusted local network" not in readme


def test_kafka_build_emitter_threads_generation_run_id() -> None:
    files = emit(_fixture_metadata(), generation_run_id="run-123")

    assert "<!-- Generation run: run-123 -->" in files["pom.xml"]


def test_kafka_build_emitter_request_reply_yaml_contains_all_four_topic_keys() -> None:
    files = emit(_request_reply_metadata())
    yaml_content = files["src/main/resources/application.yaml"]

    assert "downstream-reply:" in yaml_content
    assert "upstream-reply:" in yaml_content
    assert "timeout-ms:" in yaml_content
    assert "core.account.verify.reply.v1" in yaml_content
    assert "payments.verification.reply.v1" in yaml_content


def test_kafka_build_emitter_fire_and_forget_yaml_has_no_reply_keys() -> None:
    files = emit(_fixture_metadata())
    yaml_content = files["src/main/resources/application.yaml"]

    assert "downstream-reply" not in yaml_content
    assert "timeout-ms" not in yaml_content


def test_kafka_build_emitter_always_includes_prometheus_dependency() -> None:
    files = emit(_fixture_metadata())

    assert "micrometer-registry-prometheus" in files["pom.xml"]


def test_kafka_build_emitter_always_enables_kafka_observation() -> None:
    files = emit(_fixture_metadata())
    yaml_content = files["src/main/resources/application.yaml"]

    assert "observation-enabled: true" in yaml_content


def test_kafka_build_emitter_defaults_to_health_only_with_metrics_opt_in() -> None:
    files = emit(_fixture_metadata())
    yaml_content = files["src/main/resources/application.yaml"]
    readme = files["README.md"]

    assert (
        "include: ${MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE:health}"
        in yaml_content
    )
    assert "include: health,metrics,prometheus" not in yaml_content
    assert "Only `/actuator/health` is exposed by default." in readme
    assert (
        "`MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,metrics,prometheus`"
        in readme
    )
    assert "application port is unreachable except through" in readme


def test_kafka_build_emitter_is_deterministic() -> None:
    metadata = _fixture_metadata()

    first = emit(metadata, source_manifest="fixture", generation_run_id="stable-run")
    second = emit(metadata, source_manifest="fixture", generation_run_id="stable-run")

    assert first == second


def test_kafka_build_emitter_dlq_adds_dlq_topic_to_yaml() -> None:
    files = emit(_retry_dlq_metadata())
    yaml_content = files["src/main/resources/application.yaml"]

    assert "dlq:" in yaml_content
    assert "abc.payments.posted.v1.dlq" in yaml_content


def test_kafka_build_emitter_no_dlq_omits_dlq_from_yaml() -> None:
    files = emit(_fixture_metadata())
    yaml_content = files["src/main/resources/application.yaml"]

    assert "dlq:" not in yaml_content


def test_kafka_build_emitter_retry_readme_states_retry_policy() -> None:
    files = emit(_retry_dlq_metadata())
    readme = files["README.md"]

    assert "Retry Policy" in readme
    assert "3" in readme
    assert ".dlq" in readme


def test_kafka_build_emitter_no_retry_readme_states_no_retry_policy() -> None:
    files = emit(_fixture_metadata())
    readme = files["README.md"]

    assert "Observability" in readme
    assert "max_attempts" not in readme


def test_kafka_generation_scaffolds_and_preserves_repository_hygiene_files(
    tmp_path: Path,
) -> None:
    metadata = _fixture_metadata()
    output_dir = tmp_path / "KafkaApp"
    first_report = generate_application(
        metadata,
        output_dir,
        generation_run_id="kafka-hygiene-first",
    )
    relative_files = {
        path.relative_to(output_dir).as_posix()
        for path in first_report.files_created
    }
    assert {".gitignore", ".dockerignore"}.issubset(relative_files)

    for name in (".gitignore", ".dockerignore"):
        path = output_dir / name
        content = path.read_text(encoding="utf-8")
        assert "# EdgeForge-ownership: developer" in content
        assert "target/" in content
        assert f"{metadata.bounded_context}-eod/" in content
        path.write_text(content + "# adopter edit\n", encoding="utf-8")

    generate_application(
        metadata,
        output_dir,
        generation_run_id="kafka-hygiene-second",
    )
    for name in (".gitignore", ".dockerignore"):
        assert (output_dir / name).read_text(encoding="utf-8").endswith(
            "# adopter edit\n"
        )


def _fixture_metadata():
    manifest = Path("tests/fixtures/kafka-integration/manifest.yaml")
    definition = load_project_definition(manifest)
    return translate_kafka_project(definition, project_root=manifest.parent)


def _request_reply_metadata():
    manifest = Path("tests/fixtures/kafka-request-reply/manifest.yaml")
    definition = load_project_definition(manifest)
    return translate_kafka_project(definition, project_root=manifest.parent)


def _retry_dlq_metadata():
    manifest = Path("tests/fixtures/kafka-retry-dlq/manifest.yaml")
    definition = load_project_definition(manifest)
    return translate_kafka_project(definition, project_root=manifest.parent)


def _router_metadata():
    manifest = Path("tests/fixtures/kafka-router-contract/manifest.yaml")
    definition = load_project_definition(manifest)
    return translate_kafka_project(definition, project_root=manifest.parent)
