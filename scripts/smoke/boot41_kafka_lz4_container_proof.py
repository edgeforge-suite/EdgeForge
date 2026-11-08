"""One LZ4 roundtrip per JDK inside the generated app's own non-root image."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
from pathlib import Path

from appbuilder.contracts import load_project_definition
from appbuilder.generation import generate_application
from appbuilder.generation.kafka_emitter import _app_class_name
from appbuilder.metadata.kafka_translation import translate_kafka_project
from scripts.assess_generated_maven import source_inventory, inventory_digest


def prepare_app(root: Path, java: str, profile: str) -> Path:
    fixture = Path("tests/fixtures/kafka-multi-route")
    definition = load_project_definition(fixture / "manifest.yaml")
    definition.target_profile = profile
    definition.async_routes = definition.async_routes[:1]
    metadata = translate_kafka_project(definition, fixture)
    app = root / ("app-j" + java)
    generate_application(metadata, app, source_manifest="lz4-proof/manifest.yaml",
                         generation_run_id="lz4-native-proof")
    app_class = _app_class_name(metadata) + "Application"
    source = Path("tests/fixtures/boot41-kafka/Lz4ContainerProof.java").read_text()
    source = source.replace("__APP__", metadata.java_package + "." + app_class)
    source = source.replace("__APP_CLASS__", app_class)
    destination = app / "src/main/java/proof/Lz4ContainerProof.java"
    destination.parent.mkdir(parents=True)
    destination.write_text(source)
    return app


def proof(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    token = "ef-lz4-" + uuid.uuid4().hex[:12]
    network, broker = token + "-net", token + "-broker"
    images = []
    app_containers = []
    network_created = broker_created = False
    rows = []
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    source_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
    proof_hashes = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in (
        "scripts/smoke/boot41_kafka_lz4_container_proof.py", "tests/fixtures/boot41-kafka/Lz4ContainerProof.java")}

    def run(command, *, timeout=120, log="infrastructure.log"):
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
        with (root / log).open("a") as output:
            output.write("$ " + " ".join(command) + "\n" + result.stdout + "\n")
        if result.returncode:
            raise AssertionError(f"Container proof failed ({result.returncode}); see {log}")
        return result.stdout

    try:
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
        broker_created = True
        run(["docker", "start", broker])
        # Kafka's own CLI waits for a usable controller; no arbitrary sleep or host port.
        for topic in ("abc.payments.posted.v1", "xyz.ledger.entries.v1"):
            run(["docker", "exec", broker, "/opt/kafka/bin/kafka-topics.sh",
                 "--bootstrap-server", "broker:9092", "--create", "--if-not-exists",
                 "--topic", topic, "--partitions", "1", "--replication-factor", "1"], timeout=120)
        for java, profile in (("17", "springboot-legacy-compatible"),
                              ("21", "springboot-standard-enterprise")):
            app = prepare_app(root, java, profile)
            generated_hashes = source_inventory(app)
            image = token + "-j" + java
            run(["docker", "build", "--platform", "linux/amd64", "-t", image, str(app)],
                timeout=600, log="build-j" + java + ".log")
            images.append(image)
            identity = json.loads(run(["docker", "image", "inspect", image]))[0]
            assert identity["Architecture"] == "amd64" and identity["Os"] == "linux"
            assert identity["Config"]["User"] == "edgeforge"
            container = token + "-app-j" + java
            run(["docker", "create", "--platform", "linux/amd64", "--name", container,
                          "--network", network, "-e", "KAFKA_BOOTSTRAP_SERVERS=broker:9092",
                          "--entrypoint", "/bin/sh", image, "-ec",
                          'temp=$(mktemp -d /tmp/ef-lz4-native.XXXXXXXXXX); '
                          'exec java -Djava.io.tmpdir="$temp" -Dloader.main=proof.Lz4ContainerProof '
                          '-cp /app/app.jar org.springframework.boot.loader.launch.PropertiesLauncher'],
                         timeout=120)
            app_containers.append(container)
            output = run(["docker", "start", "--attach", container], timeout=120,
                         log="runtime-j" + java + ".log")
            state = json.loads(run(["docker", "inspect", container]))[0]["State"]
            assert state["ExitCode"] == 0, "Generated container failed"
            assert "LZ4_NATIVE_PROOF" in output and "LZ4_ROUNDTRIP_PROOF" in output
            assert "compression.type=lz4" in output
            rows.append({"java": java, "profile": profile, "platform": "linux/amd64",
                         "image_id": identity["Id"], "user": identity["Config"]["User"],
                         "dockerfile": "generated, unchanged", "lz4": "1.11.4",
                         "native_and_roundtrip": "passed", "runtime_log": "runtime-j" + java + ".log",
                         "source_sha256": inventory_digest(generated_hashes),
                         "pom_sha256": generated_hashes["pom.xml"],
                         "dockerfile_sha256": generated_hashes["Dockerfile"],
                         "native_loading": "explicit Native.load; nested-loader Java fallback not credited"})
        return {"cases": rows, "result": "passed", "image_security_clearance": False}
    finally:
        for container in app_containers:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        if broker_created:
            with (root / "broker.log").open("w") as log:
                subprocess.run(["docker", "logs", broker], stdout=log, stderr=subprocess.STDOUT)
            subprocess.run(["docker", "rm", "-f", broker], capture_output=True)
        if network_created:
            subprocess.run(["docker", "network", "rm", network], capture_output=True)
        for image in images:
            subprocess.run(["docker", "image", "rm", image], capture_output=True)
        (root / "receipt.json").write_text(json.dumps({"cases": rows, "complete": len(rows) == 2,
            "source_sha": source_sha, "source_dirty": source_dirty, "proof_source_hashes": proof_hashes,
            "image_security_clearance": False}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(proof(args.work_dir), indent=2))
