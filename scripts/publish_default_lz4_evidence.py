#!/usr/bin/env python3
"""Read retained default-LZ4 proof and export a new, sanitized local evidence bundle.

No Docker, subprocesses, builds, probes, scans, network, or acceptance decisions.
The source SHA belongs to the proof receipt, never the publisher's checkout.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import platform
import re
import sys
import zlib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.assess_generated_maven import (  # noqa: E402
    inventory_digest,
    sanitize_json,
    source_inventory,
    unique_object,
)
from scripts.smoke.boot41_kafka_lz4_default_proof import (  # noqa: E402
    ENTRYPOINT,
    validate_observation,
    validate_receipt,
)

LIMIT = 32 * 1024 * 1024
STAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b")
CASE_FIELDS = ("java", "profile", "platform", "image_id", "user", "entrypoint", "process", "exit_code",
               "production_unchanged", "production_sha256", "instrumented_sha256", "pom_sha256",
               "dockerfile_sha256", "observer_path", "observer_sha256", "runtime_log")
OBS_FIELDS = ("observer", "java", "uid", "os", "arch", "java_command", "jvm_args", "classloader",
              "lz4_origin", "xxhash_origin", "kafka_origin")
IMPL_FIELDS = ("lz4_factory", "xxhash_factory", "compressor", "checksum", "kafka_compressor", "kafka_checksum",
               "native_loaded_after_traffic", "native_loaded_after_observation", "observation_scope",
               "kafka_default_compression_level", "kafka_compression_level_source")
WIRE_FIELDS = ("key", "input_partition_key", "output_partition_key", "output_partition_key_strategy",
               "input_compression", "output_compression", "input", "output")


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()


def strict_json(text):
    def nonfinite(_):
        raise ValueError("Non-finite JSON evidence")

    return json.loads(text, object_pairs_hook=unique_object, parse_constant=nonfinite)


def read_bytes(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= LIMIT,
            "Required evidence missing, oversized, or symlinked")
    return path.read_bytes()


def read_json(path):
    raw = read_bytes(path)
    value = strict_json(raw.decode("utf-8"))
    require(isinstance(value, dict), "Expected JSON object")
    return value, raw


def runtime_observation(raw, java):
    text = raw.decode("utf-8")
    lines = [line.removeprefix("LZ4_DEFAULT_PROOF ") for line in text.splitlines()
             if line.startswith("LZ4_DEFAULT_PROOF ")]
    require(len(lines) == 1, "Missing or duplicate runtime observation")
    value = strict_json(lines[0])
    validate_observation(value, java)
    return value


def public_observation(value):
    result = {key: value[key] for key in OBS_FIELDS}
    result["implementations"] = {key: value["implementations"][key] for key in IMPL_FIELDS}
    result["roundtrip"] = {key: value["roundtrip"][key] for key in WIRE_FIELDS}
    for name in ("input_position", "output_position"):
        result["roundtrip"][name] = {key: value["roundtrip"][name][key] for key in ("topic", "partition", "offset")}
    return result


def verify_inventory(directory, case):
    java = case["java"]
    value, raw = read_json(directory / ("sources-j" + java + ".json"))
    require(set(value) == {"production", "instrumented", "observer_path", "application_class"},
            "Malformed source inventory")
    production, instrumented, observer = value["production"], value["instrumented"], value["observer_path"]
    for inventory in (production, instrumented):
        require(isinstance(inventory, dict) and inventory, "Empty source inventory")
        for name, sha in inventory.items():
            require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_./-]+", name)
                    and not Path(name).is_absolute() and not {".", ".."} & set(name.split("/"))
                    and isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha), "Invalid inventory entry")
    require(observer == case["observer_path"] and observer not in production
            and set(instrumented) == set(production) | {observer}
            and {k: v for k, v in instrumented.items() if k != observer} == production,
            "Not an observer-only source addition")
    app = directory / ("app-j" + java)
    require(app.is_dir() and not app.is_symlink(), "Saved app missing or symlinked")
    require(source_inventory(app) == instrumented, "Saved app source differs from retained inventory")
    require(inventory_digest(production) == case["production_sha256"]
            and inventory_digest(instrumented) == case["instrumented_sha256"]
            and production.get("pom.xml") == case["pom_sha256"]
            and production.get("Dockerfile") == case["dockerfile_sha256"]
            and instrumented[observer] == case["observer_sha256"], "Case/source digest mismatch")
    main = "src/main/java/" + value["application_class"].replace(".", "/") + ".java"
    require(main in production and observer == main.rsplit("/", 1)[0] + "/proof/Lz4DefaultObserver.java",
            "Inventory main/observer mismatch")
    return value, raw


def verify_container(directory, case):
    value, _ = read_json(directory / ("container-j" + case["java"] + ".json"))
    state = value["State"]
    require(value["Image"] == case["image_id"] and [value["Path"], *value["Args"]] == ENTRYPOINT
            and value["Config"]["User"] == case["user"] and value["Config"]["Entrypoint"] == ENTRYPOINT
            and type(state["ExitCode"]) is int and state["ExitCode"] == 0
            and state["Running"] is False and state["OOMKilled"] is False and not state.get("Error"),
            "Saved container contradicts successful case")
    return value


def redactor(directories, receipts, containers, supplied):
    paths = [(ROOT, "<source-directory>"), (Path.home(), "<home>")]
    for index, directory in enumerate(directories):
        label = "<proof-directory>" if index == 0 else f"<prior-failure-{index:02d}>"
        paths.append((directory, label))
        if str(directory).startswith("/private/tmp/"):
            paths.append((Path(str(directory).removeprefix("/private")), label))
    for index, prefix in enumerate(supplied):
        path = Path(prefix)
        require(path.is_absolute() and len(path.parts) > 1
                and not (str(path) == "/app" or str(path).startswith("/app/")),
                "Host prefixes must be absolute and must not redact image JAR paths")
        paths.append((path, f"<supplied-host-{index:02d}>"))
    hostnames = {"broker", "localhost"}
    for receipt in receipts:
        hostnames.add(receipt.get("docker_info", {}).get("Name", ""))
        hostnames.add(receipt.get("broker_inspect", {}).get("Config", {}).get("Hostname", ""))
    hostnames.update(value.get("Config", {}).get("Hostname", "") for value in containers)
    hostnames.discard("")

    def clean(value):
        value = sanitize_json(value, paths)
        if isinstance(value, str):
            for hostname in sorted(hostnames, key=lambda item: (-len(item), item)):
                value = re.sub(r"(?<![A-Za-z0-9_.-])" + re.escape(hostname) + r"(?![A-Za-z0-9_.-])",
                               "<hostname>", value)
            return value
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                key = clean(key)
                require(key not in result, "Redaction collides JSON keys")
                result[key] = clean(item)
            return result
        return value

    return clean


def publish(proof_directory, output, *, prior_failures=(), host_prefixes=()):
    inputs = [Path(proof_directory), *(Path(path) for path in prior_failures)]
    require(len(inputs) <= 9 and all(path.is_dir() and not path.is_symlink() for path in inputs),
            "Missing, symlinked, or excessive proof directories")
    directories = [path.resolve() for path in inputs]
    require(len(set(directories)) == len(directories), "Duplicate proof directories")
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), "Output must be new; originals are never overwritten")
    output = output.resolve()
    require(all(output != path and path not in output.parents and output not in path.parents for path in directories),
            "Output must be disjoint from all originals")
    receipt, receipt_raw = read_json(directories[0] / "receipt.json")
    validate_receipt(receipt)
    require("error" not in receipt and receipt.get("cleanup_errors", []) == []
            and receipt.get("cleanup_complete", True) is True, "Successful receipt contradicts cleanup/failure state")
    containers, records = [], [("receipt.json", receipt_raw, None)]
    public_cases = []
    for case in sorted(receipt["cases"], key=lambda row: row["java"]):
        require(type(case["exit_code"]) is int and case["exit_code"] == 0, "Malformed successful exit code")
        raw = read_bytes(directories[0] / case["runtime_log"])
        require(canonical(runtime_observation(raw, case["java"])) == canonical(case["observation"]),
                "Runtime observation differs from receipt case")
        inventory, inventory_raw = verify_inventory(directories[0], case)
        containers.append(verify_container(directories[0], case))
        public_case = {key: case[key] for key in CASE_FIELDS}
        public_case["runtime_log"] = case["runtime_log"] + ".gz"
        public_case["observation"] = public_observation(case["observation"])
        require(canonical(public_case["observation"]) == canonical(case["observation"]),
                "Unexpected runtime observation fields cannot be safely published")
        public_cases.append(public_case)
        records.extend((("sources-j" + case["java"] + ".json", inventory_raw, inventory),
                        (case["runtime_log"] + ".gz", raw, "log")))
    public = {key: receipt[key] for key in ("status", "complete", "source_sha", "approved_source_sha",
                                          "source_dirty", "proof_source_hashes", "image_security_clearance")}
    public.update(cases=public_cases,
                  host_platform={key: receipt["host_platform"][key] for key in ("system", "machine")},
                  tools={"docker_client": receipt["docker_version"]["Client"]["Version"],
                         "docker_server": receipt["docker_version"]["Server"]["Version"],
                         "docker_architecture": receipt["docker_info"]["Architecture"]},
                  broker_image=receipt["broker_inspect"]["Config"]["Image"],
                  broker_image_id=receipt["broker_inspect"]["Image"])
    require(all(isinstance(version, str) and re.fullmatch(r"[0-9][A-Za-z0-9.+_-]{0,63}", version)
                for version in (public["tools"]["docker_client"], public["tools"]["docker_server"])),
            "Missing or malformed tool versions")
    require(public["host_platform"]["system"] in ("Darwin", "Linux", "Windows")
            and public["host_platform"]["machine"] in ("arm64", "aarch64", "x86_64", "amd64", "AMD64")
            and public["tools"]["docker_architecture"] in ("arm64", "aarch64", "x86_64", "amd64"),
            "Malformed host/engine architecture")
    records[0] = ("receipt.json", receipt_raw, public)
    receipts = [receipt]
    failures = []
    for index, directory in enumerate(directories[1:], 1):
        failed, raw = read_json(directory / "receipt.json")
        require(failed.get("status") == "failed" and failed.get("complete") is False
                and isinstance(failed.get("error"), str) and failed["error"]
                and re.fullmatch(r"[0-9a-f]{40}", failed.get("source_sha", ""))
                and type(failed.get("source_dirty")) is bool, "Prior failure must remain explicitly failed")
        prefix = f"prior-failure-{index:02d}/"
        compact = {key: failed[key] for key in ("status", "complete", "source_sha", "source_dirty", "error")}
        if "cleanup_errors" in failed:
            require(isinstance(failed["cleanup_errors"], list)
                    and all(isinstance(error, str) for error in failed["cleanup_errors"]), "Malformed cleanup errors")
            compact["cleanup_errors"] = failed["cleanup_errors"]
        records.append((prefix + "receipt.json", raw, compact))
        failures.append({"receipt": prefix + "receipt.json", "source_sha": failed["source_sha"], "status": "failed"})
        records.append((prefix + "failure.log.gz", read_bytes(directory / "failure.log"), "log"))
        for java in ("17", "21"):
            path = directory / ("runtime-j" + java + ".log")
            if path.exists() or path.is_symlink():
                records.append((prefix + path.name + ".gz", read_bytes(path), "log"))
        receipts.append(failed)
    clean = redactor(directories, receipts, containers, host_prefixes)
    files, artifacts = {}, []
    for name, raw, value in records:
        artifact = {"file": name, "original_sha256": digest(raw)}
        if value == "log":
            text = raw.decode("utf-8")
            sanitized = clean(text)
            stamps = STAMP.findall(text)
            require(stamps == STAMP.findall(sanitized), "Redaction changed original log timestamps")
            for stamp in stamps:
                datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            require(stamps or name.startswith("prior-failure-"), "Successful runtime log has no timestamps")
            artifact["timestamps"] = {"first": stamps[0], "last": stamps[-1]} if stamps else None
            data = sanitized.encode()
            stream = io.BytesIO()
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as packed:
                packed.write(data)
            files[name] = stream.getvalue()
            artifact["gzip_sha256"] = digest(files[name])
        else:
            sanitized = clean(value)
            if name == "receipt.json":
                for case in sanitized["cases"]:
                    validate_observation(case["observation"], case["java"])
            data = canonical(sanitized)
            files[name] = data
        artifact["sanitized_sha256"] = digest(data)
        artifacts.append(artifact)
    publication = {"status": "published", "source_sha": receipt["source_sha"], "prior_failures": failures,
                   "image_security_clearance": False, "artifacts": artifacts,
                   "publisher": {"sha256": digest(Path(__file__).read_bytes()), "python": platform.python_version(),
                                 "zlib": zlib.ZLIB_RUNTIME_VERSION, "gzip_mtime": 0},
                   "hash_semantics": "original identifies untouched private bytes; sanitized identifies exported uncompressed bytes"}
    # Everything is validated and sanitized before reserving a new destination.
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (output / "publication.json").write_bytes(canonical(publication))
    return publication


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prior-failure", action="append", type=Path, default=[])
    parser.add_argument("--host-prefix", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        publish(args.proof_directory, args.output, prior_failures=args.prior_failure, host_prefixes=args.host_prefix)
    except (AssertionError, ValueError, OSError, TypeError, KeyError, AttributeError):
        print("Evidence publication refused: missing, contradictory, malformed, or unsafe retained evidence.", file=sys.stderr)
        return 2
    print("Default-LZ4 evidence published locally; originals unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
