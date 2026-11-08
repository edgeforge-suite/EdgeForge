"""No-Docker controls for ordinary Boot launch and fail-closed default observation."""

import ast
import copy
import json
import os
import subprocess
from pathlib import Path

import pytest

from appbuilder.generation.container_policy import base_references
from scripts.smoke import boot41_kafka_lz4_default_proof as proof


def observation(java="17", implementation="JavaUnsafe"):
    key = "default-lz4-unit-correlation"
    compressor = "net.jpountz.lz4.LZ4" + implementation + "Compressor"
    checksum = "net.jpountz.xxhash.XXHash32" + implementation
    native = implementation == "JNI"
    return {
        "observer": "proof-only additive component; production sources/config/POM/recipe unchanged",
        "java": java + ".0.18", "uid": 10001, "os": "Linux", "arch": "amd64",
        "java_command": "/app/app.jar", "jvm_args": [],
        "classloader": "org.springframework.boot.loader.launch.LaunchedClassLoader",
        "lz4_origin": "jar:nested:/app/app.jar/!BOOT-INF/lib/lz4-java-1.11.4.jar!/",
        "xxhash_origin": "jar:nested:/app/app.jar/!BOOT-INF/lib/lz4-java-1.11.4.jar!/",
        "kafka_origin": "jar:nested:/app/app.jar/!BOOT-INF/lib/kafka-clients-4.2.1.jar!/",
        "implementations": {
            "lz4_factory": "LZ4Factory:" + implementation, "xxhash_factory": "XXHashFactory:" + implementation,
            "compressor": compressor, "checksum": checksum,
            "kafka_compressor": compressor, "kafka_checksum": checksum,
            "native_loaded_after_traffic": native, "native_loaded_after_observation": native,
            "observation_scope": proof.SCOPE,
            "kafka_default_compression_level": 9,
            "kafka_compression_level_source": "CompressionType.LZ4.defaultLevel()",
        },
        "roundtrip": {
            "key": key, "input_compression": "lz4", "output_compression": proof.OUTPUT_COMPRESSION,
            "input_partition_key": key, "output_partition_key": None,
            "output_partition_key_strategy": "round_robin",
            "input": {"paymentId": key, "accountId": "A1", "amount": 12.34},
            "output": {"entryId": key, "accountRef": "A1", "amountMinorUnits": 1234, "channel": "KAFKA_HUB"},
            "input_position": {"topic": "abc.payments.posted.v1", "partition": 0, "offset": 0},
            "output_position": {"topic": "xyz.ledger.entries.v1", "partition": 0, "offset": 0},
        },
    }


@pytest.mark.parametrize("java,profile", proof.CASES)
def test_only_additive_observer_and_unchanged_generated_normal_launch(tmp_path, java, profile):
    app = proof.prepare_app(tmp_path, java, profile)
    proof.verify_sources(app)
    assert set(app.instrumented) - set(app.production) == {app.observer}
    assert all(app.instrumented[name] == digest for name, digest in app.production.items())
    dockerfile = (app.path / "Dockerfile").read_text()
    assert f"FROM {base_references(java)[1]}" in dockerfile
    assert "USER edgeforge" in dockerfile
    assert 'ENTRYPOINT ["java", "-jar", "/app/app.jar"]' in dockerfile
    main = app.path / ("src/main/java/" + app.application_class.replace(".", "/") + ".java")
    assert "SpringApplication.run(" in main.read_text()
    assert "Lz4Default" not in main.read_text()
    source = (app.path / app.observer).read_text()
    assert "__APP__" not in source and "__PACKAGE__" not in source
    assert "@Component" in source and "ApplicationReadyEvent" in source
    assert "public static void main" not in source
    for forbidden in ("Native.load", 'getMethod("load")', "System.setProperty", "System.setProperties",
                      'getMethod("nativeInstance")', 'getMethod("safeInstance")',
                      'getMethod("unsafeInstance")', 'getMethod("fastestJavaInstance")',
                      "PropertiesLauncher", "SpringApplication.run", "System.exit"):
        assert forbidden not in source
    assert source.index('require(observed,') < source.index('getMethod("fastestInstance")')
    assert 'getDeclaredField(name)' in source
    assert 'producerProps.put("compression.type", "lz4")' in source
    assert "spring.kafka.producer.compression" not in source
    assert "import net.jpountz" not in source  # LZ4 remains runtime-scoped.
    assert "isIntegralNumber()" in source and "isString()" in source
    consumer = next((app.path / "src/main/java").glob("**/consumer/PaymentPostedConsumer.java"))
    producer = next((app.path / "src/main/java").glob("**/producer/PaymentPostedProducer.java"))
    assert "producer.send(outbound, null);" in consumer.read_text()
    assert "kafkaTemplate.send(topic, partitionKey, message);" in producer.read_text()
    assert "require(record.key() == null," in source
    assert "key.equals(record.key())" not in source
    assert 'roundtrip.put("input_partition_key", key);' in source
    assert 'roundtrip.put("output_partition_key", record.key());' in source
    assert 'roundtrip.put("output_partition_key_strategy", "round_robin");' in source
    assert ".newInstance(output, CompressionType.LZ4.defaultLevel(), false)" in source
    assert "try (var stream = kafkaDefaultLz4Stream(new ByteArrayOutputStream()))" in source
    assert 'implementations.put("kafka_default_compression_level", CompressionType.LZ4.defaultLevel());' in source


@pytest.mark.parametrize("java", ("17", "21"))
def test_compiled_observer_matches_real_kafka_default_and_rejects_historical_sentinel(tmp_path, java):
    """Opt-in cached-JAR contract test: no broker, Docker, Maven, or Boot startup.

    Set EDGEFORGE_LZ4_CONTRACT_CLASSPATH to the pinned cached runtime JARs and
    EDGEFORGE_LZ4_CONTRACT_JAVA17_HOME / JAVA21_HOME to the corresponding JDKs.
    Compiles the actual observer and invokes only its stream constructor, then
    compares it with Kafka's public default builder, not a copied expected level.
    """
    classpath = os.environ.get("EDGEFORGE_LZ4_CONTRACT_CLASSPATH")
    java_home = os.environ.get("EDGEFORGE_LZ4_CONTRACT_JAVA" + java + "_HOME")
    if not classpath or not java_home:
        pytest.skip("Offline LZ4 contract requires explicit cached classpath and JDK " + java)
    app = proof.prepare_app(tmp_path, *next(case for case in proof.CASES if case[0] == java))
    observer = app.path / app.observer
    observer_class = app.application_class.rsplit(".", 1)[0] + ".proof.Lz4DefaultObserver"
    harness = tmp_path / "KafkaDefaultLevelContract.java"
    harness.write_text('''
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.util.Arrays;
import org.apache.kafka.common.compress.Compression;
import org.apache.kafka.common.compress.Lz4BlockOutputStream;
import org.apache.kafka.common.record.CompressionType;
import org.apache.kafka.common.utils.ByteBufferOutputStream;

public class KafkaDefaultLevelContract {
    private static void require(boolean condition, String detail) {
        if (!condition) throw new AssertionError(detail);
    }
    private static Class<?> implementation(OutputStream stream, String name) throws Exception {
        var field = Lz4BlockOutputStream.class.getDeclaredField(name);
        field.setAccessible(true);
        return field.get(stream).getClass();
    }
    public static void main(String[] args) throws Exception {
        require(CompressionType.class.getProtectionDomain().getCodeSource().getLocation().toString()
                .endsWith("/kafka-clients-4.2.1.jar"), "Pinned Kafka JAR required");
        Class<?> lz4 = Class.forName("net.jpountz.lz4.LZ4Factory");
        require(lz4.getProtectionDomain().getCodeSource().getLocation().toString()
                .endsWith("/lz4-java-1.11.4.jar"), "Pinned LZ4 JAR required");
        int defaultLevel = CompressionType.LZ4.defaultLevel();
        require(Compression.lz4().build().equals(Compression.lz4().level(defaultLevel).build()),
                "Public builder and authoritative constant disagree");
        boolean sentinelRejected = false;
        try { Compression.lz4().level(-1); }
        catch (IllegalArgumentException expected) { sentinelRejected = true; }
        require(sentinelRejected, "Historical -1 is not a valid public-builder level");
        var constructor = Class.forName(args[0]).getDeclaredMethod("kafkaDefaultLz4Stream", OutputStream.class);
        constructor.setAccessible(true);
        var observerBytes = new ByteArrayOutputStream();
        var builderBytes = new ByteBufferOutputStream(65536);
        try (var observed = (OutputStream) constructor.invoke(null, observerBytes);
             var expected = Compression.lz4().build().wrapForOutput(builderBytes, (byte) 2);
             var historical = new Lz4BlockOutputStream(new ByteArrayOutputStream(), -1, false)) {
            Object factory = lz4.getMethod("fastestInstance").invoke(null);
            Class<?> fast = lz4.getMethod("fastCompressor").invoke(factory).getClass();
            require(implementation(expected, "compressor") == fast, "Kafka default is not the fast compressor");
            require(implementation(observed, "compressor") == implementation(expected, "compressor"),
                    "Observer constructor differs from actual Kafka default builder");
            require(implementation(observed, "checksum") == implementation(expected, "checksum"),
                    "Observer checksum differs from actual Kafka default builder");
            require(implementation(historical, "compressor") != implementation(expected, "compressor"),
                    "Regression did not distinguish 64927c8's -1 constructor");
            byte[] payload = "offline-default-contract-0123456789".repeat(100).getBytes(java.nio.charset.StandardCharsets.UTF_8);
            observed.write(payload);
            expected.write(payload);
        }
        byte[] expectedBytes = Arrays.copyOf(builderBytes.buffer().array(), builderBytes.position());
        require(Arrays.equals(observerBytes.toByteArray(), expectedBytes), "Default LZ4 frames differ");
        System.out.println("OFFLINE_KAFKA_DEFAULT_CONTRACT passed level=" + defaultLevel);
    }
}
''')
    classes = tmp_path / "classes"
    for label, command in (
        ("javac-j" + java, [str(Path(java_home) / "bin/javac"), "--release", java, "-cp", classpath,
                            "-d", str(classes), str(observer), str(harness)]),
        ("contract-j" + java, [str(Path(java_home) / "bin/java"), "-cp", str(classes) + os.pathsep + classpath,
                               "KafkaDefaultLevelContract", observer_class]),
    ):
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        (tmp_path / (label + ".log")).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    assert "OFFLINE_KAFKA_DEFAULT_CONTRACT passed" in result.stdout
    proof.verify_sources(app)


@pytest.mark.parametrize("level", (-1, 0, 1, 17, True, 9.0, "9", None))
def test_nondefault_or_mistyped_level_receipts_fail(level):
    row = observation()
    row["implementations"]["kafka_default_compression_level"] = level
    with pytest.raises(AssertionError, match="compression-level contract"):
        proof.validate_observation(row, "17")


@pytest.mark.parametrize("field", ("kafka_default_compression_level", "kafka_compression_level_source"))
def test_missing_default_level_contract_fails(field):
    row = observation()
    del row["implementations"][field]
    with pytest.raises(AssertionError, match="compression-level contract"):
        proof.validate_observation(row, "17")


@pytest.mark.parametrize("strategy,source", (("field_value", "accountRef"), ("correlation_id", None)))
def test_changed_partition_contract_stops_proof_instead_of_changing_expectations(tmp_path, monkeypatch, strategy, source):
    translate = proof.translate_kafka_project

    def changed_contract(*args):
        metadata = translate(*args)
        metadata.routes[0].partition_key_strategy = strategy
        metadata.routes[0].partition_key_source = source
        return metadata

    monkeypatch.setattr(proof, "translate_kafka_project", changed_contract)
    with pytest.raises(AssertionError, match="partition-key contract changed"):
        proof.prepare_app(tmp_path, *proof.CASES[0])
    assert not (tmp_path / "app-j17").exists()


@pytest.mark.parametrize("actual", ("nonce", "A1", "", 0, False))
def test_output_partition_key_cannot_be_nonce_account_or_any_nonnull_value(actual):
    row = observation()
    row["roundtrip"]["output_partition_key"] = row["roundtrip"]["key"] if actual == "nonce" else actual
    with pytest.raises(AssertionError, match="explicit null"):
        proof.validate_observation(row, "17")


@pytest.mark.parametrize("field", ("input_partition_key", "output_partition_key", "output_partition_key_strategy"))
def test_missing_partition_key_evidence_is_not_null_evidence(field):
    row = observation()
    del row["roundtrip"][field]
    with pytest.raises(AssertionError, match="partition key"):
        proof.validate_observation(row, "17")


@pytest.mark.parametrize("mutation", ("production", "observer", "extra"))
def test_source_verifier_rejects_every_undeclared_change(tmp_path, mutation):
    app = proof.prepare_app(tmp_path, *proof.CASES[0])
    path = app.path / {"production": "pom.xml", "observer": app.observer, "extra": "unexpected.txt"}[mutation]
    path.write_text("tampered")
    with pytest.raises(AssertionError, match="mutated"):
        proof.verify_sources(app)


@pytest.mark.parametrize("implementation", ("JavaSafe", "JavaUnsafe", "JNI"))
def test_default_java_fallback_and_native_are_both_valid(implementation):
    value = observation(implementation=implementation)
    proof.validate_observation(value, "17")
    assert proof.parse_observation("Boot log\nLZ4_DEFAULT_PROOF " + json.dumps(value) + "\n", "17") == value


@pytest.mark.parametrize("path,value", (
    (("uid",), 0), (("uid",), True), (("java",), "21.0.1"), (("os",), "Darwin"),
    (("arch",), "aarch64"), (("classloader",), "AppClassLoader"),
    (("java_command",), "proof.ReplacementMain"), (("jvm_args",), ["-Dloader.main=proof.Main"]),
    (("lz4_origin",), "file:/tmp/lz4-java-1.11.4.jar"), (("xxhash_origin",), ""), (("kafka_origin",), ""),
    (("observer",), ""), (("implementations", "lz4_factory"), ""),
    (("implementations", "kafka_compressor"), "different"),
    (("implementations", "kafka_checksum"), "different"),
    (("implementations", "native_loaded_after_traffic"), None),
    (("implementations", "native_loaded_after_observation"), True),
    (("implementations", "observation_scope"), "in-flight native proof"),
    (("implementations", "kafka_compression_level_source"), "historical -1 sentinel"),
    (("roundtrip", "input_compression"), "none"), (("roundtrip", "output_compression"), "lz4"),
    (("roundtrip", "input_partition_key"), "different"),
    (("roundtrip", "output_partition_key_strategy"), "field_value"),
    (("roundtrip", "input", "paymentId"), "different"),
    (("roundtrip", "output", "entryId"), "different"),
    (("roundtrip", "input", "amount"), "12.34"),
    (("roundtrip", "output", "amountMinorUnits"), "1234"),
    (("roundtrip", "output", "amountMinorUnits"), 1234.0),
    (("roundtrip", "output", "channel"), "different"),
    (("roundtrip", "output_position", "offset"), -1),
    (("roundtrip", "input_position", "partition"), False),
    (("roundtrip", "output_position", "topic"), "different"),
))
def test_incomplete_or_contradictory_observations_fail(path, value):
    row = observation()
    target = row
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = value
    with pytest.raises(AssertionError):
        proof.validate_observation(row, "17")


@pytest.mark.parametrize("count", (0, 2))
def test_missing_and_duplicate_marker_fail(count):
    output = ("LZ4_DEFAULT_PROOF " + json.dumps(observation()) + "\n") * count
    with pytest.raises(AssertionError, match="Missing or duplicate"):
        proof.parse_observation(output, "17")


def fake_runner(monkeypatch, *, dirty=False, wrong_sha=False, build_failure=False):
    calls = []
    image_id = "sha256:" + "a" * 64
    identity = {"Id": image_id, "Os": "linux", "Architecture": "amd64",
                "Config": {"User": "edgeforge", "Entrypoint": proof.ENTRYPOINT, "Cmd": None}}

    def run(root, command, **kwargs):
        calls.append(command)
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return ("c" if wrong_sha else "b") * 40 + "\n"
        if command[:2] == ["git", "status"]:
            return "?? uncommitted\n" if dirty else ""
        if command[:2] == ["docker", "version"]:
            return json.dumps({"Server": {"Version": "29.3.0"}})
        if command[:2] == ["docker", "info"]:
            return json.dumps({"Architecture": "aarch64"})
        if command[:3] == ["docker", "image", "inspect"]:
            return json.dumps([identity])
        if command[:2] == ["docker", "inspect"]:
            return json.dumps([{"Image": image_id, "Path": "java", "Args": proof.ENTRYPOINT[1:],
                                "State": {"ExitCode": 0, "Running": False, "OOMKilled": False},
                                "Config": {"Image": "apache/kafka:4.2.1"}}])
        if command[:2] == ["docker", "build"] and build_failure:
            raise AssertionError("retained bounded build failure")
        if command[:2] == ["docker", "logs"] and "-app-j" in command[-1]:
            return "LZ4_DEFAULT_PROOF " + json.dumps(observation(command[-1][-2:])) + "\n"
        return ""

    monkeypatch.setattr(proof, "run_logged", run)
    return calls


def test_mock_campaign_preserves_default_launcher_and_accepts_fallback(tmp_path, monkeypatch):
    calls = fake_runner(monkeypatch)
    receipt = proof.proof(tmp_path / "evidence", "b" * 40)
    proof.validate_receipt(receipt)
    assert receipt["complete"] is True
    app_creates = [c for c in calls if c[:2] == ["docker", "create"] and any("-app-j" in a for a in c)]
    assert len(app_creates) == 2
    for command in app_creates:
        assert command[-1].startswith("ef-default-lz4-")
        assert command[-2] == "KAFKA_BOOTSTRAP_SERVERS=broker:9092"
        assert "--entrypoint" not in command
    assert not any(any(token in " ".join(c) for token in ("PropertiesLauncher", "loader.main", "java.io.tmpdir"))
                   for c in calls)
    assert all(not any(word in c for word in ("prune", "push", "kill")) for c in calls)
    require_paths = {"production_sha256", "instrumented_sha256", "pom_sha256", "dockerfile_sha256", "observer_sha256"}
    for field in require_paths:
        damaged = copy.deepcopy(receipt)
        del damaged["cases"][0][field]
        with pytest.raises(AssertionError):
            proof.validate_receipt(damaged)
    for field in ("proof_source_hashes", "host_platform", "docker_version", "docker_info", "broker_inspect"):
        damaged = copy.deepcopy(receipt)
        del damaged[field]
        with pytest.raises(AssertionError):
            proof.validate_receipt(damaged)
    for cases in ([], receipt["cases"][:1], [receipt["cases"][0]] * 2):
        with pytest.raises(AssertionError):
            proof.validate_receipt({**receipt, "cases": cases})


@pytest.mark.parametrize("dirty,wrong_sha,approval", ((True, False, "b" * 40),
                                                    (False, True, "b" * 40), (False, False, "")))
def test_approval_gate_never_touches_docker_and_retains_failure(tmp_path, monkeypatch, dirty, wrong_sha, approval):
    calls = fake_runner(monkeypatch, dirty=dirty, wrong_sha=wrong_sha)
    root = tmp_path / "evidence"
    with pytest.raises(AssertionError, match="Parent-approved clean commit"):
        proof.proof(root, approval)
    assert not any(command[0] == "docker" for command in calls)
    receipt = json.loads((root / "receipt.json").read_text())
    assert receipt["complete"] is False and receipt["status"] == "failed"
    assert "Parent-approved" in (root / "failure.log").read_text()
    with pytest.raises(FileExistsError):
        proof.proof(root, approval)  # Evidence cannot be overwritten on an unchanged retry.


def test_build_failure_is_not_retried_and_only_owned_resources_are_cleaned(tmp_path, monkeypatch):
    calls = fake_runner(monkeypatch, build_failure=True)
    root = tmp_path / "evidence"
    with pytest.raises(AssertionError, match="retained bounded build failure"):
        proof.proof(root, "b" * 40)
    assert len([c for c in calls if c[:2] == ["docker", "build"]]) == 1
    assert json.loads((root / "receipt.json").read_text())["complete"] is False
    for command in calls:
        if command[:2] == ["docker", "rm"] or command[:3] in (["docker", "network", "rm"], ["docker", "image", "rm"]):
            assert command[-1].startswith("ef-default-lz4-")


def test_timeout_partial_output_is_retained_without_retry(tmp_path, monkeypatch):
    calls = []

    def timeout(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, 1, output=b"partial diagnostic")

    monkeypatch.setattr(proof.subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        proof.run_logged(tmp_path, ["missing-proof-tool"], timeout=1)
    assert len(calls) == 1
    assert "partial diagnostic\nTIMEOUT 1s" in (tmp_path / "infrastructure.log").read_text()


def test_helper_has_no_factory_or_launcher_override_calls():
    source = Path(proof.__file__).read_text()
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr in {"setdefault", "update"} and isinstance(node.func.value, ast.Attribute)
                   and node.func.value.attr == "environ" for node in ast.walk(tree))
    for forbidden in ("Native.load", "PropertiesLauncher", "loader.main", "spring.kafka.producer.compression-type"):
        assert forbidden not in source
