"""Opt-in ordinary java-jar default-LZ4 proof, separate from explicit JNI evidence.

Run only after parent clean-commit approval and coordination of the heavy build.
The image uses the unchanged generated main/ENTRYPOINT plus a labelled proof-only
component. Java fallback is valid. This helper performs no vulnerability assessment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shlex
import subprocess
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path

from appbuilder.contracts import load_project_definition
from appbuilder.generation import generate_application
from appbuilder.generation.kafka_emitter import _app_class_name
from appbuilder.metadata.kafka_translation import translate_kafka_project
from scripts.assess_generated_maven import inventory_digest, source_inventory

REPO = Path(__file__).resolve().parents[2]
OBSERVER = REPO / "tests/fixtures/boot41-kafka/Lz4DefaultObserver.java"
CASES = (("17", "springboot-legacy-compatible"), ("21", "springboot-standard-enterprise"))
ENTRYPOINT = ["java", "-jar", "/app/app.jar"]
SCOPE = "post-roundtrip Kafka default stream; not in-flight producer internals"
OUTPUT_COMPRESSION = "unchanged generated default; not claimed as LZ4"


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


@dataclass
class PreparedApp:
    path: Path
    production: dict[str, str]
    observer: str
    application_class: str
    instrumented: dict[str, str]


def prepare_app(root: Path, java: str, profile: str) -> PreparedApp:
    require((java, profile) in CASES, "Unsupported proof profile")
    fixture = REPO / "tests/fixtures/kafka-multi-route"
    definition = load_project_definition(fixture / "manifest.yaml")
    definition.target_profile = profile
    definition.async_routes = definition.async_routes[:1]
    metadata = translate_kafka_project(definition, fixture)
    require(definition.async_routes[0].partition_key is None
            and (metadata.routes[0].partition_key_strategy, metadata.routes[0].partition_key_source)
            == ("round_robin", None), "Proof fixture partition-key contract changed; stop and review")
    app = root / ("app-j" + java)
    require(not app.exists(), "Do not overwrite an existing proof app")
    generate_application(metadata, app, source_manifest="lz4-default-proof/manifest.yaml",
                         generation_run_id="lz4-default-proof")
    production = source_inventory(app)
    application_class = metadata.java_package + "." + _app_class_name(metadata) + "Application"
    observer = "src/main/java/" + metadata.java_package.replace(".", "/") + "/proof/Lz4DefaultObserver.java"
    require(observer not in production, "Observer would overwrite generated production")
    destination = app / observer
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(OBSERVER.read_text().replace("__PACKAGE__", metadata.java_package)
                           .replace("__APP__", application_class))
    prepared = PreparedApp(app, production, observer, application_class, source_inventory(app))
    verify_sources(prepared)
    return prepared


def verify_sources(app: PreparedApp) -> None:
    current = source_inventory(app.path)
    require(current == app.instrumented, "Build mutated instrumented sources/config/POM/recipe")
    require({k: v for k, v in current.items() if k != app.observer} == app.production,
            "Generated production changed beyond the declared observer addition")


def validate_observation(value: dict, java: str) -> None:
    require(value.get("java", "").startswith(java + "."), "Wrong actual Java runtime")
    require(type(value.get("uid")) is int and value["uid"] > 0, "Missing actual non-root UID")
    require((value.get("os"), value.get("arch")) == ("Linux", "amd64"), "Wrong actual process platform")
    require(value.get("java_command") == "/app/app.jar" and value.get("jvm_args") == [],
            "Not ordinary java-jar")
    require(value.get("classloader") == "org.springframework.boot.loader.launch.LaunchedClassLoader",
            "Missing Boot nested classloader")
    require(value.get("observer") == "proof-only additive component; production sources/config/POM/recipe unchanged",
            "Unlabelled observer")
    for name, artifact in (("lz4_origin", "lz4-java-1.11.4.jar"),
                           ("xxhash_origin", "lz4-java-1.11.4.jar"),
                           ("kafka_origin", "kafka-clients-4.2.1.jar")):
        origin = value.get(name, "")
        require("/app/app.jar/!BOOT-INF/lib/" in origin and artifact in origin,
                "Missing nested dependency origin: " + name)
    implementations = value.get("implementations", {})
    require(implementations.get("observation_scope") == SCOPE, "Missing observation boundary")
    # Pinned Kafka 4.2.1 reports 9; the observer obtains it from Kafka, not a constructor sentinel.
    require(type(implementations.get("kafka_default_compression_level")) is int
            and implementations["kafka_default_compression_level"] == 9
            and implementations.get("kafka_compression_level_source") == "CompressionType.LZ4.defaultLevel()",
            "Missing or incorrect Kafka default compression-level contract")
    for name, prefix in (("compressor", "net.jpountz.lz4."), ("checksum", "net.jpountz.xxhash.")):
        actual = implementations.get(name, "")
        require(actual.startswith(prefix) and implementations.get("kafka_" + name) == actual,
                "Missing/mismatched Kafka default " + name)
    for name, prefix in (("lz4_factory", "LZ4Factory:"), ("xxhash_factory", "XXHashFactory:")):
        require(implementations.get(name, "").startswith(prefix), "Missing default factory")
    for name in ("native_loaded_after_traffic", "native_loaded_after_observation"):
        require(type(implementations.get(name)) is bool, "Missing native observation")
    require(implementations["native_loaded_after_traffic"] == implementations["native_loaded_after_observation"],
            "Observation changed native loading state")
    wire = value.get("roundtrip", {})
    key = wire.get("key", "")
    require(key.startswith("default-lz4-") and len(key) > 12, "Missing correlated key")
    require(wire.get("input_partition_key") == key, "Input nonce partition key mismatch")
    require(wire.get("output_partition_key_strategy") == "round_robin"
            and "output_partition_key" in wire and wire["output_partition_key"] is None,
            "Output partition key must be explicit null for the fixture's round_robin contract")
    require(wire.get("input_compression") == "lz4" and wire.get("output_compression") == OUTPUT_COMPRESSION,
            "Compression scope incomplete")
    expected_input = {"paymentId": key, "accountId": "A1", "amount": 12.34}
    expected_output = {"entryId": key, "accountRef": "A1", "amountMinorUnits": 1234, "channel": "KAFKA_HUB"}
    for name, expected in (("input", expected_input), ("output", expected_output)):
        # JSON equality retains number/string/boolean distinctions unlike Python's ==.
        require(json.dumps(wire.get(name), sort_keys=True) == json.dumps(expected, sort_keys=True),
                "Wire values/types differ: " + name)
    for name, topic in (("input_position", "abc.payments.posted.v1"),
                        ("output_position", "xyz.ledger.entries.v1")):
        position = wire.get(name, {})
        require(position.get("topic") == topic, "Missing real broker topic")
        for field in ("partition", "offset"):
            require(type(position.get(field)) is int and position[field] >= 0, "Missing broker position")


def parse_observation(output: str, java: str) -> dict:
    lines = [line.removeprefix("LZ4_DEFAULT_PROOF ") for line in output.splitlines()
             if line.startswith("LZ4_DEFAULT_PROOF ")]
    require(len(lines) == 1, "Missing or duplicate default-LZ4 receipt")
    value = json.loads(lines[0])
    validate_observation(value, java)
    return value


def validate_receipt(receipt: dict) -> None:
    require(receipt.get("status") == "passed" and receipt.get("complete") is True, "Incomplete proof")
    require(receipt.get("source_dirty") is False and re.fullmatch(r"[0-9a-f]{40}", receipt.get("source_sha", "")),
            "Missing clean source identity")
    require(receipt.get("approved_source_sha") == receipt["source_sha"], "Approval/source mismatch")
    require(receipt.get("image_security_clearance") is False, "Not a security clearance")
    expected_helpers = {str(Path(__file__).resolve().relative_to(REPO)), str(OBSERVER.relative_to(REPO))}
    helpers = receipt.get("proof_source_hashes", {})
    require(set(helpers) == expected_helpers
            and all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in helpers.values()),
            "Missing proof helper identities")
    require(all(receipt.get("host_platform", {}).get(key) for key in ("system", "machine")),
            "Missing host platform")
    require(receipt.get("docker_version", {}).get("Server", {}).get("Version")
            and receipt.get("docker_info", {}).get("Architecture"), "Missing Docker engine identity")
    broker = receipt.get("broker_inspect", {})
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", broker.get("Image", ""))
            and broker.get("Config", {}).get("Image") == "apache/kafka:4.2.1", "Missing pinned broker identity")
    cases = receipt.get("cases", [])
    require(len(cases) == 2 and {(c.get("java"), c.get("profile")) for c in cases} == set(CASES),
            "Missing/duplicate JDK cases")
    for case in cases:
        validate_observation(case.get("observation", {}), case["java"])
        require(case.get("platform") == "linux/amd64" and case.get("user") == "edgeforge", "Wrong image identity")
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", case.get("image_id", "")), "Missing image ID")
        require(case.get("entrypoint") == ENTRYPOINT and case.get("process") == ENTRYPOINT,
                "Changed image launcher")
        require(case.get("exit_code") == 0 and case.get("production_unchanged") is True, "Failed/mutated case")
        for field in ("production_sha256", "instrumented_sha256", "pom_sha256", "dockerfile_sha256", "observer_sha256"):
            require(re.fullmatch(r"[0-9a-f]{64}", case.get(field, "")), "Missing source digest")
        require(case.get("observer_path", "").endswith("/proof/Lz4DefaultObserver.java"), "Missing additive observer")
        require(case.get("runtime_log") == "runtime-j" + case["java"] + ".log", "Missing runtime evidence link")


def run_logged(root: Path, command: list[str], *, timeout=120, log="infrastructure.log") -> str:
    with (root / log).open("a") as output:
        output.write("$ " + shlex.join(command) + "\n")
        output.flush()
        try:
            result = subprocess.run(command, cwd=REPO, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout or ""
            output.write(partial.decode(errors="replace") if isinstance(partial, bytes) else partial)
            output.write("\nTIMEOUT " + str(timeout) + "s\n")
            raise
        except OSError as exc:
            output.write(str(exc) + "\n")
            raise
        output.write(result.stdout + "\n")
        require(result.returncode == 0, f"Proof command failed ({result.returncode}); see {log}")
        return result.stdout


def proof(root: Path, approved_source_sha: str) -> dict:
    root = root.resolve()
    require(root != REPO and REPO not in root.parents, "Keep evidence outside the source checkout")
    root.mkdir(parents=True, exist_ok=False)
    receipt = {"status": "incomplete", "complete": False, "cases": [],
               "approved_source_sha": approved_source_sha, "image_security_clearance": False,
               "host_platform": {"system": platform.system(), "machine": platform.machine()}}
    token = "ef-default-lz4-" + uuid.uuid4().hex[:12]
    network, broker = token + "-net", token + "-broker"
    containers, images = [], []
    network_created = False

    def run(command, **kwargs):
        return run_logged(root, command, **kwargs)

    try:
        receipt["source_sha"] = run(["git", "rev-parse", "HEAD"]).strip()
        receipt["source_dirty"] = bool(run(["git", "status", "--porcelain", "--untracked-files=all"]).strip())
        require(re.fullmatch(r"[0-9a-f]{40}", approved_source_sha or "")
                and approved_source_sha == receipt["source_sha"] and not receipt["source_dirty"],
                "Parent-approved clean commit required before Docker proof")
        receipt["proof_source_hashes"] = {
            str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__).resolve(), OBSERVER)
        }
        receipt["docker_version"] = json.loads(run(["docker", "version", "--format", "{{json .}}"]))
        receipt["docker_info"] = json.loads(run(["docker", "info", "--format", "{{json .}}"]))
        run(["docker", "network", "create", network])
        network_created = True
        run(["docker", "create", "--platform", "linux/amd64", "--name", broker,
             "--network", network, "--network-alias", "broker",
             "-e", "KAFKA_NODE_ID=1", "-e", "KAFKA_PROCESS_ROLES=broker,controller",
             "-e", "KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093",
             "-e", "KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://broker:9092",
             "-e", "KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER",
             "-e", "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
             "-e", "KAFKA_CONTROLLER_QUORUM_VOTERS=1@broker:9093",
             "-e", "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1",
             "-e", "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1",
             "-e", "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1", "apache/kafka:4.2.1"], timeout=180)
        containers.append(broker)
        receipt["broker_inspect"] = json.loads(run(["docker", "inspect", broker]))[0]
        run(["docker", "start", broker])
        for topic in ("abc.payments.posted.v1", "xyz.ledger.entries.v1"):
            run(["docker", "exec", broker, "/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server", "broker:9092",
                 "--create", "--if-not-exists", "--topic", topic, "--partitions", "1", "--replication-factor", "1"])
        for java, profile in CASES:
            app = prepare_app(root, java, profile)
            (root / ("sources-j" + java + ".json")).write_text(json.dumps({
                "production": app.production, "instrumented": app.instrumented,
                "observer_path": app.observer, "application_class": app.application_class}, indent=2) + "\n")
            image = token + "-j" + java
            images.append(image)
            run(["docker", "build", "--platform", "linux/amd64", "-t", image, str(app.path)],
                timeout=600, log="build-j" + java + ".log")
            verify_sources(app)
            identity = json.loads(run(["docker", "image", "inspect", image]))[0]
            require((identity["Os"], identity["Architecture"], identity["Config"]["User"]) ==
                    ("linux", "amd64", "edgeforge"), "Wrong built image platform/user")
            require(identity["Config"]["Entrypoint"] == ENTRYPOINT and not identity["Config"].get("Cmd"),
                    "Changed generated image command")
            container = token + "-app-j" + java
            # No --entrypoint, launcher arguments, loader properties, or factory overrides.
            run(["docker", "create", "--platform", "linux/amd64", "--name", container,
                 "--network", network, "-e", "KAFKA_BOOTSTRAP_SERVERS=broker:9092", image])
            containers.append(container)
            run(["docker", "start", "--attach", container], timeout=180, log="runtime-j" + java + ".log")
            inspection = json.loads(run(["docker", "inspect", container]))[0]
            (root / ("container-j" + java + ".json")).write_text(json.dumps(inspection, indent=2) + "\n")
            require(inspection["Image"] == identity["Id"], "Running image identity mismatch")
            process = [inspection["Path"], *inspection["Args"]]
            require(process == ENTRYPOINT and inspection["State"]["ExitCode"] == 0
                    and not inspection["State"].get("OOMKilled") and not inspection["State"].get("Running"),
                    "Incomplete ordinary image execution")
            output = run(["docker", "logs", container], log="container-logs-j" + java + ".log")
            observation = parse_observation(output, java)
            verify_sources(app)
            receipt["cases"].append({
                "java": java, "profile": profile, "platform": "linux/amd64", "image_id": identity["Id"],
                "user": identity["Config"]["User"], "entrypoint": identity["Config"]["Entrypoint"],
                "process": process, "exit_code": inspection["State"]["ExitCode"], "production_unchanged": True,
                "production_sha256": inventory_digest(app.production),
                "instrumented_sha256": inventory_digest(app.instrumented), "pom_sha256": app.production["pom.xml"],
                "dockerfile_sha256": app.production["Dockerfile"], "observer_path": app.observer,
                "observer_sha256": app.instrumented[app.observer], "runtime_log": "runtime-j" + java + ".log",
                "observation": observation})
        require(run(["git", "rev-parse", "HEAD"]).strip() == approved_source_sha
                and not run(["git", "status", "--porcelain", "--untracked-files=all"]).strip(),
                "Source checkout changed during proof")
        receipt.update(status="passed", complete=True)
        validate_receipt(receipt)
    except BaseException as exc:
        receipt.update(status="failed", complete=False, error=f"{type(exc).__name__}: {exc}")
        (root / "failure.log").write_text(traceback.format_exc())
        raise
    finally:
        cleanup_errors = []
        for container in containers:
            for command in (["docker", "logs", container], ["docker", "inspect", container],
                            ["docker", "rm", "-f", container]):
                try:
                    run(command, timeout=30, log="cleanup-" + container + ".log")
                except (OSError, subprocess.SubprocessError, AssertionError) as exc:
                    cleanup_errors.append(str(exc))
        for command in (([["docker", "network", "rm", network]] if network_created else [])
                        + [["docker", "image", "rm", image] for image in images]):
            try:
                run(command, timeout=30, log="cleanup.log")
            except (OSError, subprocess.SubprocessError, AssertionError) as exc:
                cleanup_errors.append(str(exc))
        if cleanup_errors:
            receipt.update(status="failed", complete=False, cleanup_errors=cleanup_errors)
        (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    require(receipt["complete"], "Proof cleanup incomplete; see retained receipt")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--approved-source-sha", required=True,
                        help="Exact clean commit explicitly approved by parent for this bounded real proof")
    args = parser.parse_args(argv)
    print(json.dumps(proof(args.work_dir, args.approved_source_sha), indent=2))


if __name__ == "__main__":
    main()
