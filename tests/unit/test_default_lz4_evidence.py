"""Temporary retained-proof fixtures only; never publish live evidence or invoke Docker."""

import copy
import gzip
import json
import socket
import subprocess
from pathlib import Path

import pytest

from scripts import publish_default_lz4_evidence as publisher
from scripts.smoke import boot41_kafka_lz4_default_proof as helper

SOURCE = "fe125b2d6c84aadacb2605f21d7bd146087afbab"
STAMP = "2026-10-14T22:39:57.926Z"


def write_json(path, value):
    path.write_bytes(publisher.canonical(value))


def observation(java):
    key = "default-lz4-test-correlation"
    return {
        "observer": "proof-only additive component; production sources/config/POM/recipe unchanged",
        "java": java + ".0.18", "uid": 999, "os": "Linux", "arch": "amd64",
        "java_command": "/app/app.jar", "jvm_args": [],
        "classloader": "org.springframework.boot.loader.launch.LaunchedClassLoader",
        "lz4_origin": "jar:nested:/app/app.jar/!BOOT-INF/lib/lz4-java-1.11.4.jar!/",
        "xxhash_origin": "jar:nested:/app/app.jar/!BOOT-INF/lib/lz4-java-1.11.4.jar!/",
        "kafka_origin": "jar:nested:/app/app.jar/!BOOT-INF/lib/kafka-clients-4.2.1.jar!/",
        "implementations": {
            "lz4_factory": "LZ4Factory:JavaSafe", "xxhash_factory": "XXHashFactory:JavaUnsafe",
            "compressor": "net.jpountz.lz4.LZ4JavaSafeCompressor",
            "kafka_compressor": "net.jpountz.lz4.LZ4JavaSafeCompressor",
            "checksum": "net.jpountz.xxhash.XXHash32JavaUnsafe",
            "kafka_checksum": "net.jpountz.xxhash.XXHash32JavaUnsafe",
            "native_loaded_after_traffic": False, "native_loaded_after_observation": False,
            "observation_scope": helper.SCOPE, "kafka_default_compression_level": 9,
            "kafka_compression_level_source": "CompressionType.LZ4.defaultLevel()",
        },
        "roundtrip": {
            "key": key, "input_partition_key": key, "output_partition_key": None,
            "output_partition_key_strategy": "round_robin", "input_compression": "lz4",
            "output_compression": helper.OUTPUT_COMPRESSION,
            "input": {"paymentId": key, "accountId": "A1", "amount": 12.34},
            "output": {"entryId": key, "accountRef": "A1", "amountMinorUnits": 1234, "channel": "KAFKA_HUB"},
            "input_position": {"topic": "abc.payments.posted.v1", "partition": 0, "offset": 0},
            "output_position": {"topic": "xyz.ledger.entries.v1", "partition": 0, "offset": 0},
        },
    }


@pytest.fixture
def retained(tmp_path):
    directory = tmp_path / "private-proof"
    directory.mkdir()
    receipt = {
        "status": "passed", "complete": True, "source_sha": SOURCE, "approved_source_sha": SOURCE,
        "source_dirty": False, "image_security_clearance": False,
        "proof_source_hashes": {"scripts/smoke/boot41_kafka_lz4_default_proof.py": "a" * 64,
                                "tests/fixtures/boot41-kafka/Lz4DefaultObserver.java": "b" * 64},
        "host_platform": {"system": "Darwin", "machine": "arm64", "environment": "private"},
        "docker_version": {"Client": {"Version": "29.6.1"}, "Server": {"Version": "29.6.1"}},
        "docker_info": {"Architecture": "aarch64", "Name": "private-laptop.example", "Env": ["DO_NOT_EXPORT"]},
        "broker_inspect": {"Image": "sha256:" + "c" * 64,
                           "Config": {"Image": "apache/kafka:4.2.1", "Hostname": "private-broker", "Env": ["DO_NOT_EXPORT"]}},
        "cases": [],
    }
    for java, profile in helper.CASES:
        app = helper.prepare_app(directory, java, profile)
        inventory = {"production": app.production, "instrumented": app.instrumented,
                     "observer_path": app.observer, "application_class": app.application_class}
        write_json(directory / ("sources-j" + java + ".json"), inventory)
        case = {
            "java": java, "profile": profile, "platform": "linux/amd64", "image_id": "sha256:" + java[-1] * 64,
            "user": "edgeforge", "entrypoint": helper.ENTRYPOINT, "process": helper.ENTRYPOINT, "exit_code": 0,
            "production_unchanged": True, "production_sha256": helper.inventory_digest(app.production),
            "instrumented_sha256": helper.inventory_digest(app.instrumented), "pom_sha256": app.production["pom.xml"],
            "dockerfile_sha256": app.production["Dockerfile"], "observer_sha256": app.instrumented[app.observer],
            "observer_path": app.observer, "runtime_log": "runtime-j" + java + ".log", "observation": observation(java),
        }
        receipt["cases"].append(case)
        write_json(directory / ("container-j" + java + ".json"), {
            "Image": case["image_id"], "Path": "java", "Args": helper.ENTRYPOINT[1:],
            "Config": {"User": "edgeforge", "Entrypoint": helper.ENTRYPOINT,
                       "Hostname": "private-container", "Env": ["DO_NOT_EXPORT"]},
            "State": {"ExitCode": 0, "Running": False, "OOMKilled": False, "Error": ""},
        })
        text = (STAMP + " INFO proof=" + str(directory) + " source=" + str(publisher.ROOT)
                + " home=" + str(Path.home()) + " supplied=/opt/private-checkout/file.java"
                + " unknown=/" "Users/private-owner/checkout private-laptop.example broker:9092 private-container\n"
                + "LZ4_DEFAULT_PROOF " + json.dumps(case["observation"]) + "\n")
        (directory / case["runtime_log"]).write_text(text)
    write_json(directory / "receipt.json", receipt)
    return directory, receipt


def snapshot(directory):
    return {str(path.relative_to(directory)): publisher.digest(path.read_bytes())
            for path in directory.rglob("*") if path.is_file()}


def test_publish_is_deterministic_read_only_safe_and_preserves_actual_identity(retained, tmp_path, monkeypatch):
    directory, receipt = retained
    before = snapshot(directory)
    monkeypatch.setenv("GIT_COMMIT", "f" * 40)  # Publisher HEAD must never replace observed identity.

    def forbidden(*args, **kwargs):
        raise AssertionError("Publisher must not execute processes or connect to a network")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    outputs = [tmp_path / "export-a", tmp_path / "export-b"]
    for output in outputs:
        publisher.publish(directory, output, host_prefixes=["/opt/private-checkout"])
    assert snapshot(outputs[0]) == snapshot(outputs[1])
    assert snapshot(directory) == before
    public = json.loads((outputs[0] / "receipt.json").read_text())
    assert public["source_sha"] == SOURCE and public["source_dirty"] is False
    assert public["cases"][0]["observation"] == receipt["cases"][0]["observation"]
    assert all((outputs[0] / case["runtime_log"]).is_file() and case["runtime_log"].endswith(".log.gz")
               for case in public["cases"])
    assert public["broker_image_id"] == receipt["broker_inspect"]["Image"]
    assert "docker_info" not in public and "broker_inspect" not in public
    assert "Env" not in json.dumps(public) and "DO_NOT_EXPORT" not in json.dumps(public)
    index = json.loads((outputs[0] / "publication.json").read_text())
    assert index["source_sha"] == SOURCE
    assert index["publisher"]["sha256"] == publisher.digest(Path(publisher.__file__).read_bytes())
    assert index["publisher"]["python"] and index["publisher"]["zlib"] and index["publisher"]["gzip_mtime"] == 0
    for artifact in index["artifacts"]:
        source_name = artifact["file"].removesuffix(".gz")
        assert artifact["original_sha256"] == before[source_name]
        path = outputs[0] / artifact["file"]
        raw = path.read_bytes()
        if path.suffix == ".gz":
            assert raw[4:8] == b"\x00" * 4
            assert artifact["gzip_sha256"] == publisher.digest(raw)
            raw = gzip.decompress(raw)
            assert artifact["timestamps"] == {"first": STAMP, "last": STAMP}
            assert STAMP.encode() in raw
            for private in (str(directory), str(publisher.ROOT), str(Path.home()), "/opt/private-checkout",
                            "/" "Users/private-owner", "private-laptop.example", "private-container", "broker:9092"):
                assert private.encode() not in raw
            assert b"/app/app.jar/!BOOT-INF/lib/lz4-java-1.11.4.jar!/" in raw
            assert b"net.jpountz.lz4.LZ4JavaSafeCompressor" in raw
        assert artifact["sanitized_sha256"] == publisher.digest(raw)


@pytest.mark.parametrize("change", ("incomplete", "missing-case", "duplicate-case", "dirty", "cleanup-errors",
                                    "cleanup-incomplete", "error", "wrong-pom", "wrong-recipe", "wrong-observer",
                                    "wrong-production", "wrong-instrumented", "exit-bool", "wrong-container-image"))
def test_contradictory_receipts_cannot_publish(retained, tmp_path, change):
    directory, receipt = retained
    case = receipt["cases"][0]
    if change == "incomplete":
        receipt["complete"] = False
    elif change == "missing-case":
        receipt["cases"].pop()
    elif change == "duplicate-case":
        receipt["cases"] = [case, case]
    elif change == "dirty":
        receipt["source_dirty"] = True
    elif change == "cleanup-errors":
        receipt["cleanup_errors"] = ["cleanup failed"]
    elif change == "cleanup-incomplete":
        receipt["cleanup_complete"] = False
    elif change == "error":
        receipt["error"] = "contradictory failure"
    elif change == "exit-bool":
        case["exit_code"] = False
    else:
        field = {"wrong-pom": "pom_sha256", "wrong-recipe": "dockerfile_sha256", "wrong-observer": "observer_sha256",
                 "wrong-production": "production_sha256", "wrong-instrumented": "instrumented_sha256",
                 "wrong-container-image": "image_id"}[change]
        case[field] = ("sha256:" if field == "image_id" else "") + "0" * 64
    write_json(directory / "receipt.json", receipt)
    with pytest.raises((AssertionError, ValueError)):
        publisher.publish(directory, tmp_path / "export")
    assert not (tmp_path / "export").exists()


@pytest.mark.parametrize("change", ("app", "observer", "inventory", "extra-source", "nonadditive", "symlink"))
def test_changed_saved_sources_and_inventories_fail(retained, tmp_path, change):
    directory, receipt = retained
    path = directory / "sources-j17.json"
    inventory = json.loads(path.read_text())
    app = directory / "app-j17"
    if change in {"app", "observer", "extra-source"}:
        name = {"app": "pom.xml", "observer": inventory["observer_path"], "extra-source": "extra.java"}[change]
        (app / name).write_text("changed")
    elif change == "inventory":
        inventory["instrumented"]["pom.xml"] = "0" * 64
    elif change == "nonadditive":
        observer = inventory["observer_path"]
        inventory["production"][observer] = inventory["instrumented"][observer]
    else:
        target = app / "pom.xml"
        target.unlink()
        target.symlink_to(app / "Dockerfile")
    write_json(path, inventory)
    with pytest.raises((AssertionError, ValueError)):
        publisher.publish(directory, tmp_path / "export")


@pytest.mark.parametrize("change", ("runtime-missing", "runtime-mismatch", "runtime-duplicate", "runtime-extra",
                                    "receipt-duplicate-key", "inventory-duplicate-key", "runtime-duplicate-key",
                                    "invalid-json", "nonfinite-json", "container-running", "no-timestamp"))
def test_missing_malformed_duplicate_or_contradictory_evidence_fails(retained, tmp_path, change):
    directory, receipt = retained
    path = directory / "runtime-j17.log"
    if change == "runtime-missing":
        path.unlink()
    elif change == "runtime-mismatch":
        path.write_text(path.read_text().replace('"uid": 999', '"uid": 1000'))
    elif change == "runtime-duplicate":
        path.write_text(path.read_text() * 2)
    elif change == "runtime-extra":
        receipt["cases"][0]["observation"]["environment"] = {"secret": "DO_NOT_EXPORT"}
        write_json(directory / "receipt.json", receipt)
        path.write_text(STAMP + " INFO\nLZ4_DEFAULT_PROOF " + json.dumps(receipt["cases"][0]["observation"]) + "\n")
    elif change == "runtime-duplicate-key":
        path.write_text(path.read_text().replace('"uid": 999', '"uid": 999, "uid": 999'))
    elif change in {"receipt-duplicate-key", "inventory-duplicate-key"}:
        path = directory / ("receipt.json" if change == "receipt-duplicate-key" else "sources-j17.json")
        path.write_text('{"duplicate": 1, "duplicate": 2}')
    elif change == "invalid-json":
        (directory / "receipt.json").write_text("{")
    elif change == "nonfinite-json":
        (directory / "receipt.json").write_text('{"status": NaN}')
    elif change == "no-timestamp":
        path.write_text(path.read_text().replace(STAMP, "no timestamp"))
    else:
        path = directory / "container-j17.json"
        container = json.loads(path.read_text())
        container["State"]["Running"] = True
        write_json(path, container)
    with pytest.raises((AssertionError, ValueError, OSError)):
        publisher.publish(directory, tmp_path / "export")


def prior_failure(tmp_path):
    directory = tmp_path / "prior-failure"
    directory.mkdir()
    receipt = {"status": "failed", "complete": False, "source_sha": "7" * 40, "source_dirty": False,
               "error": "failed in " + str(directory), "docker_info": {"Name": "private-failed-host"},
               "cleanup_errors": ["cleanup at /home/private-owner/cache"]}
    write_json(directory / "receipt.json", receipt)
    (directory / "failure.log").write_text("Traceback in " + str(directory) + " /home/private-owner/cache\n")
    (directory / "runtime-j17.log").write_text(STAMP + " ERROR failed private-failed-host at " + str(directory) + "\n")
    return directory, receipt


def test_optional_failures_remain_failed_and_originals_unchanged(retained, tmp_path):
    directory, _ = retained
    failed, receipt = prior_failure(tmp_path)
    before = snapshot(failed)
    output = tmp_path / "export"
    publisher.publish(directory, output, prior_failures=[failed])
    public = json.loads((output / "prior-failure-01/receipt.json").read_text())
    assert public["status"] == "failed" and public["complete"] is False
    assert public["source_sha"] == receipt["source_sha"] != SOURCE
    assert "docker_info" not in public
    assert str(failed) not in json.dumps(public) and "/home/private-owner" not in json.dumps(public)
    text = gzip.decompress((output / "prior-failure-01/runtime-j17.log.gz").read_bytes()).decode()
    assert STAMP in text and "private-failed-host" not in text
    assert snapshot(failed) == before
    index = json.loads((output / "publication.json").read_text())
    assert index["prior_failures"][0]["status"] == "failed"


@pytest.mark.parametrize("change", ("passed", "complete", "missing-failure-log", "duplicate-directory"))
def test_failures_cannot_be_promoted_or_silently_missing(retained, tmp_path, change):
    directory, _ = retained
    failed, receipt = prior_failure(tmp_path)
    if change == "passed":
        receipt["status"] = "passed"
    elif change == "complete":
        receipt["complete"] = True
    elif change == "missing-failure-log":
        (failed / "failure.log").unlink()
    write_json(failed / "receipt.json", receipt)
    with pytest.raises((AssertionError, ValueError)):
        publisher.publish(directory, tmp_path / "export", prior_failures=[failed] * (2 if change == "duplicate-directory" else 1))


def test_existing_or_overlapping_output_never_overwrites_originals(retained, tmp_path):
    directory, _ = retained
    before = snapshot(directory)
    for output in (directory, directory / "export", tmp_path):
        with pytest.raises(ValueError):
            publisher.publish(directory, output)
    assert snapshot(directory) == before


def test_recursive_path_redaction_preserves_image_paths_and_rejects_collisions():
    clean = publisher.redactor([], [], [], ["/opt/private-checkout"])
    value = {"nested": [{"/opt/private-checkout/key": "prefix /opt/private-checkout/file /home/private-owner/source"}],
             "jar": "jar:nested:/app/app.jar/!BOOT-INF/lib/lz4-java-1.11.4.jar!/"}
    sanitized = clean(copy.deepcopy(value))
    assert "/opt/private-checkout" not in json.dumps(sanitized) and "/home/private-owner" not in json.dumps(sanitized)
    assert sanitized["jar"] == value["jar"]
    with pytest.raises(ValueError, match="duplicate JSON key|collide"):
        clean({"/home/first/file": 1, "/home/second/file": 2})
    with pytest.raises(ValueError, match="image JAR"):
        publisher.redactor([], [], [], ["/app"])


@pytest.mark.parametrize("field", ("host-system", "host-arch", "engine-arch", "tool-version"))
def test_malformed_public_metadata_cannot_smuggle_raw_private_objects(retained, tmp_path, field):
    directory, receipt = retained
    private = {"environment": ["DO_NOT_EXPORT"]}
    if field == "host-system":
        receipt["host_platform"]["system"] = private
    elif field == "host-arch":
        receipt["host_platform"]["machine"] = private
    elif field == "engine-arch":
        receipt["docker_info"]["Architecture"] = private
    else:
        receipt["docker_version"]["Client"]["Version"] = private
    write_json(directory / "receipt.json", receipt)
    with pytest.raises(ValueError, match="architecture|tool versions"):
        publisher.publish(directory, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_cli_refuses_missing_evidence_without_leaking_paths(tmp_path, capsys):
    source = tmp_path / "private-not-present"
    assert publisher.main(["--proof-directory", str(source), "--output", str(tmp_path / "export")]) == 2
    assert str(source) not in capsys.readouterr().err
    assert not (tmp_path / "export").exists()
