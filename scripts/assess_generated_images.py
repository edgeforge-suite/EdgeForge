#!/usr/bin/env python3
"""Bounded local image evidence collection; no builds, uploads or DB updates.

The parent approves coverage and supplies retained exports from actual generated
recipes. Findings are not risk acceptance. Exit 2 means incomplete evidence,
exit 1 completed observations with findings, exit 0 completed with no matches.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from appbuilder.generation.container_policy import (  # noqa: E402
    declared_base_references,
    reference_sets,
)
from scripts.collect_generated_maven_baseline import FIXTURES, PROFILES  # noqa: E402

STAGES = ("generated-build-stage", "generated-final-image")
REUSE_CASE = "crud-h2-j17"
REUSE_SHA = "b7a55eacd188eb52c4fe25a844635d02f8747f66"
CAPACITY_RUNTIME_SHA = "4f30f440c08999b534a467eb85e9566f332cad1a"
KAFKA_PRIOR_SHA = "ee445d3e995ef68e3723189baf03b254213698ca"
STORAGE_PRIOR_SHA = "5954610d5102ae2f56f5ad19b90e02556af4b831"
STORAGE_PARTIAL_CASE = "kafka-pg-j21"
KAFKA_REUSE_CASES = ("crud-h2-j17", "crud-pg-j17", "crud-pg-j21", "crud-soap-h2-j17", "crud-soap-pg-j17",
                     "crud-soap-pg-j21", "passthrough-h2-j17", "passthrough-pg-j17", "passthrough-pg-j21")
STORAGE_PAIR_CASES = (*KAFKA_REUSE_CASES, "kafka-h2-j17", "kafka-pg-j17")
RUNTIME_CASES = ("crud-h2-j17", "passthrough-pg-j21", "kafka-router-h2-j17")
PINS = Path(__file__).with_name("image_assessment_tools.json")
LIMIT = 256 * 1024 * 1024
ARCHIVE_LIMIT = 6 * 1024**3
CLASSIFIER_JSON = ("build-classifiers.cdx.json", "grype-build-classifiers.json", "grype-build-classifiers-extracted.cdx.json")
STORAGE_GUARD = None
LIMITATIONS = [
    "Other platforms and exploitability are unassessed; no release clearance.",
    "JDK CPE/feed matches do not establish vendor-specific affectedness or absence.",
    "Native members are enumerated and hashed, not exhaustively identified by scanners.",
    "Embedded code without package metadata and dynamically fetched plugins remain unassessed.",
    "Build cache JAR bytes are extracted and hashed; inferred coordinates/feeds and plugin execution are not complete.",
    "Floating base tags and live Maven resolution can change a later rebuild; replay saved images.",
]


class ImageAssessmentError(RuntimeError):
    """A required observation is unavailable or inconsistent."""


class OwnedChildCleanupError(ImageAssessmentError):
    """Unconfirmed child exit forbids retention of potentially changing output."""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def require(condition, message):
    if not condition:
        raise ImageAssessmentError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def decode(data):
    try:
        def reject_constant(_):
            raise ValueError("nonfinite JSON constant")

        return json.loads(data, object_pairs_hook=unique, parse_constant=reject_constant)
    except (ValueError, UnicodeError) as exc:
        raise ImageAssessmentError("malformed JSON evidence") from exc


def read_json(path):
    return decode(evidence_bytes(path))


def evidence_bytes(path, limit=LIMIT):
    if path.exists():
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
                "evidence file unsafe or oversized")
        return path.read_bytes()
    packed = path.with_name(path.name + ".gz")
    require(packed.is_file() and not packed.is_symlink() and packed.stat().st_size <= limit + 1048576,
            "compressed evidence missing or unsafe")
    with gzip.open(packed, "rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "decompressed evidence exceeds size limit")
    return data


def evidence_digest(path):
    return digest(evidence_bytes(path))


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stream_digest(stream, *, max_bytes=None, expected_bytes=None):
    checksum = hashlib.sha256()
    size = 0
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        size += len(block)
        require(max_bytes is None or size <= max_bytes, "decompressed archive exceeds size limit")
        checksum.update(block)
    require(expected_bytes is None or size == expected_bytes, "decompressed archive size mismatch")
    return checksum.hexdigest()


def verify_gzip(path, checksum, size, *, limit=LIMIT):
    require(isinstance(size, int) and 0 <= size <= limit and path.is_file() and not path.is_symlink()
            and path.stat().st_size <= limit + 1048576, "compressed archive size/path invalid")
    with gzip.open(path, "rb") as stream:
        require(stream_digest(stream, max_bytes=size, expected_bytes=size) == checksum,
                "compressed archive original hash mismatch")


def check_storage():
    if STORAGE_GUARD is not None:
        STORAGE_GUARD()


def file_digest(path):
    with path.open("rb") as stream:
        return stream_digest(stream)


def identity(value):
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value)


def text(value):
    require(isinstance(value, str) and value and not any(ord(c) < 32 for c in value),
            "missing or invalid identity text")
    return value


def make_plan(declaration):
    expected = {f"{shape}-{suffix}": (shape, fixture, profile)
                for shape, fixture in FIXTURES.items() for suffix, profile in PROFILES.items()}
    require(declaration.get("declared_before_campaign") is True,
            "parent coverage declaration required")
    rows = declaration.get("cases")
    require(isinstance(rows, list) and len(rows) == len(expected), "expected all 30 cases")
    require({row["case"] for row in rows} == set(expected), "case checklist mismatch")
    cases = []
    references = set()
    for row in rows:
        case = row["case"]
        shape, fixture, profile = expected[case]
        require((row["shape"], row["fixture"], row["profile"]) == (shape, fixture, profile),
                "case/profile/fixture mismatch")
        require(row["platform"] == "linux/amd64" and row["assess"] == list(STAGES)
                and row["equivalence_claim"] is False, "unapproved platform/stage/equivalence")
        try:
            references.update(declared_base_references(row))
        except ValueError as exc:
            raise ImageAssessmentError(str(exc)) from exc
        cases.append({"case": case, "profile": profile, "fixture": fixture,
                      "historical_representative": row["historical_resolved_graph_representative"],
                      "artifacts": {stage: f"{case}/{stage}" for stage in STAGES},
                      "equivalence_claim": False})
        # Consumers must validate the declared pair, not fall back to historical bases.
        # Keep omitted historical fields omitted so their existing plans replay unchanged.
        cases[-1].update({key: row[key] for key in (
            "build_base", "runtime_base", "base_reference_policy") if key in row})
    require(frozenset(references) in reference_sets(), "mixed or unreviewed base reference policies")
    return {"schema_version": 1, "platform": "linux/amd64", "cases": cases,
            "status": "declared-not-scanned", "limitations": LIMITATIONS}


def isolated_env(home, grype_db=None, trivy_cache=None):
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(home), "LC_ALL": "C",
           "SYFT_CHECK_FOR_APP_UPDATE": "false", "SYFT_JAVA_USE_NETWORK": "false",
           "SYFT_GOLANG_SEARCH_REMOTE_LICENSES": "false",
           "GRYPE_CHECK_FOR_APP_UPDATE": "false", "GRYPE_DB_AUTO_UPDATE": "false",
           "GRYPE_EXTERNAL_SOURCES_ENABLE": "false",
           "TRIVY_SKIP_DB_UPDATE": "true", "TRIVY_SKIP_JAVA_DB_UPDATE": "true",
           "TRIVY_OFFLINE_SCAN": "true", "TRIVY_DISABLE_TELEMETRY": "true"}
    if grype_db is not None:
        env["GRYPE_DB_CACHE_DIR"] = str(grype_db)
    if trivy_cache is not None:
        env["TRIVY_CACHE_DIR"] = str(trivy_cache)
    return env


def run_tool(command, *, directory, label, env, timeout=600, offline=True, monitor=True):
    """Preserve even failed output privately and kill the process group on timeout."""
    command = [str(part) for part in command]
    if offline:
        sandbox = Path("/usr/bin/sandbox-exec")
        require(sys.platform == "darwin" and sandbox.is_file(),
                "network-denying execution unavailable; do not fall back to online scanning")
        command = [str(sandbox), "-p", "(version 1)(allow default)(deny network*)", *command]
    started = time.monotonic()
    receipt = {"command": command, "timeout_seconds": timeout, "status": "incomplete",
               "started_at_utc": utc_now(), "owned_child_reaped": True}
    stdout = directory / f"{label}.stdout"
    stderr = directory / f"{label}.stderr"
    try:
        with stdout.open("wb") as out, stderr.open("wb") as err:
            if monitor:
                check_storage()
            process = subprocess.Popen(command, cwd=directory, env=env, stdout=out,
                                       stderr=err, start_new_session=True)
            receipt["owned_child_reaped"] = False
            try:
                if STORAGE_GUARD is None or not monitor:
                    code = process.wait(timeout=timeout)
                else:
                    deadline = time.monotonic() + timeout
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(command, timeout)
                        try:
                            code = process.wait(timeout=min(2, remaining))
                            check_storage()
                            break
                        except subprocess.TimeoutExpired:
                            check_storage()
                receipt["owned_child_reaped"] = True
            except BaseException as exc:
                receipt["failure"] = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "storage safety stop"
                receipt["cause"] = error_diagnostic(exc, directory)
                try:
                    try:
                        if getattr(process, "poll", lambda: None)() is None:
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                    finally:
                        process.wait(timeout=10)
                        receipt["owned_child_reaped"] = True
                except BaseException as cleanup:
                    receipt["cleanup_failure"] = error_diagnostic(cleanup, directory)
                    if not receipt["owned_child_reaped"]:
                        raise OwnedChildCleanupError("owned scanner exit unconfirmed; raw retention forbidden") from cleanup
                    raise ImageAssessmentError("owned scanner cleanup failed; evidence incomplete") from cleanup
                if isinstance(exc, subprocess.TimeoutExpired):
                    raise ImageAssessmentError("scanner timed out; evidence incomplete") from exc
                if isinstance(exc, Exception) and not isinstance(exc, ImageAssessmentError):
                    raise ImageAssessmentError("tool/storage inspection failed; see diagnostic receipt") from exc
                raise
        receipt["exit_code"] = code
        require(code == 0, "tool failed; evidence incomplete (see private logs)")
        receipt["status"] = "completed-command-not-coverage"
    except OSError as exc:
        receipt["failure"] = "execution unavailable"
        receipt["cause"] = error_diagnostic(exc, directory)
        raise ImageAssessmentError("tool execution unavailable") from exc
    except Exception as exc:
        receipt.setdefault("failure", "tool/storage inspection failed")
        receipt.setdefault("cause", error_diagnostic(exc, directory))
        if isinstance(exc, ImageAssessmentError):
            raise
        raise ImageAssessmentError("tool/storage inspection failed; see diagnostic receipt") from exc
    finally:
        receipt["ended_at_utc"] = utc_now()
        receipt["elapsed_seconds"] = time.monotonic() - started
        for path in (stdout, stderr):
            if receipt["owned_child_reaped"] and path.exists():
                receipt[path.suffix[1:] + "_sha256"] = file_digest(path)
        write_json(directory / f"{label}.receipt.json", receipt)
    return stdout.read_bytes()


def error_diagnostic(exc, directory):
    def safe_path(value):
        if value is None:
            return None
        value = str(value)
        for prefix in sorted({str(directory), str(ROOT), str(Path.home()), "/private/tmp", "/private/var/folders"}, key=len, reverse=True):
            value = value.replace(prefix, "<private-path>")
        return "".join(character if ord(character) >= 32 else "?" for character in value)[:512]

    result = {"exception": type(exc).__name__}
    if isinstance(exc, OSError):
        result.update(errno=exc.errno, strerror=os.strerror(exc.errno) if exc.errno else "OS error",
                      filename=safe_path(exc.filename), filename2=safe_path(exc.filename2))
    if exc.__cause__ is not None:
        result["cause_exception"] = type(exc.__cause__).__name__
    return result


def verify_tools(tools, output, *, binary_dir=None):
    """Check official-list and pinned archive hashes BEFORE extracting/executing."""
    pins = read_json(PINS)
    require(sys.platform == "darwin" and os.uname().machine == "arm64",
            "tool pins are only approved for darwin/arm64")
    home = output / "home"
    home.mkdir(exist_ok=True)
    receipts = {}
    for name, pin in pins["tools"].items():
        archive = tools / pin["archive"]
        checksums = tools / pin["checksums"]
        lines = [line.split() for line in checksums.read_text().splitlines()]
        found = [parts[0] for parts in lines if len(parts) == 2
                 and parts[1].lstrip("*") == pin["archive"]]
        require(found == [pin["archive_sha256"]], "official checksum list/pin mismatch")
        require(file_digest(archive) == pin["archive_sha256"], "tool archive checksum mismatch")
        with tarfile.open(archive, "r:gz") as package:
            members = [member for member in package.getmembers() if member.name == name]
            require(len(members) == 1 and members[0].isfile() and members[0].size < LIMIT,
                    "tool archive binary missing or unsafe")
            binary = package.extractfile(members[0]).read()
        executable = (binary_dir or output) / name
        if binary_dir is None:
            executable.write_bytes(binary)
            executable.chmod(0o700)
        else:
            require(file_digest(executable) == digest(binary), "installed tool binary checksum mismatch")
        version = run_tool([executable, "--version"], directory=output, label=f"{name}-version",
                           env=isolated_env(home), timeout=20).decode("utf-8")
        require(re.search(r"(?<![\d.])" + re.escape(pin["version"]) + r"(?![\d.])", version),
                "pinned tool version mismatch")
        receipts[name] = {**pin, "binary_sha256": digest(binary),
                          "checksums_sha256": file_digest(checksums), "version_output": version}
    write_json(output / "tools.json", receipts)
    return receipts


def member_bytes(archive, name, limit=LIMIT):
    members = [member for member in archive.getmembers() if member.name == name]
    require(len(members) == 1 and members[0].isfile() and members[0].size <= limit,
            "archive member missing, duplicate, oversized or nonregular")
    return archive.extractfile(members[0]).read()


def image_archive(path, *, jar_path, stage, identity_output=None):
    """Bind the actual Boot JAR to verified config/rootfs bytes in a Docker save."""
    require(stage in STAGES, "unknown image stage")
    require(jar_path.startswith("/") and ".." not in PurePosixPath(jar_path).parts,
            "invalid image JAR path")
    jar = None
    cache = {}
    with tarfile.open(path, "r:*") as archive:
        manifest_bytes = member_bytes(archive, "manifest.json")
        manifest = decode(manifest_bytes)
        require(isinstance(manifest, list) and len(manifest) == 1, "expected single-image export")
        config_bytes = member_bytes(archive, manifest[0]["Config"])
        config = decode(config_bytes)
        if identity_output is not None:
            (identity_output / "image-config.json").write_bytes(config_bytes)
            (identity_output / "image-manifest.json").write_bytes(manifest_bytes)
        require((config.get("os"), config.get("architecture")) == ("linux", "amd64"),
                "image platform mismatch")
        layers = manifest[0]["Layers"]
        diffs = config.get("rootfs", {}).get("diff_ids")
        require(isinstance(layers, list) and layers and isinstance(diffs, list)
                and len(diffs) == len(layers) and all(identity(item) for item in diffs),
                "missing or invalid rootfs identity")
        for layer_name, expected in zip(layers, diffs, strict=True):
            raw = archive.extractfile(layer_name)
            require(raw is not None, "missing image layer")
            header = raw.read(2)
            raw.seek(0)
            stream = gzip.GzipFile(fileobj=raw) if header == b"\x1f\x8b" else raw
            require("sha256:" + stream_digest(stream) == expected, "image rootfs hash mismatch")
            raw = archive.extractfile(layer_name)
            with tarfile.open(fileobj=raw, mode="r|*") as layer:
                for member in layer:
                    name = member.name.removeprefix("./").lstrip("/")
                    require(".." not in PurePosixPath(name).parts, "unsafe image layer path")
                    # Fail closed rather than guess overlay semantics for selected content.
                    if ".wh." in name and (name.startswith(("workspace/", "app/", "root/.m2/"))):
                        raise ImageAssessmentError("selected image content has unsupported whiteouts")
                    if name == jar_path.lstrip("/"):
                        require(member.isfile() and member.size <= LIMIT, "invalid packaged image JAR")
                        jar = layer.extractfile(member).read()
                    if member.isfile() and name.endswith(".jar") and (
                            "/.m2/" in "/" + name or name.startswith("usr/share/maven/")):
                        require(member.size <= LIMIT, "oversized build cache JAR")
                        data = layer.extractfile(member).read()
                        with zipfile.ZipFile(io.BytesIO(data)) as cached:
                            require(cached.infolist() and len(cached.infolist()) <= 200000,
                                    "malformed build cache JAR")
                        cache["/" + name] = {"path": "/" + name, "sha256": digest(data), "bytes": len(data)}
    require(jar is not None, "actual image Boot JAR missing")
    settings = config.get("config", {})
    if stage == STAGES[1]:
        require(settings.get("User") == "edgeforge"
                and settings.get("Entrypoint") == ["java", "-jar", "/app/app.jar"],
                "final image launch contract mismatch")
    if stage == STAGES[0]:
        require(cache, "build-stage Maven/bootstrap cache missing")
    return {"image_id": "sha256:" + digest(config_bytes), "platform": "linux/amd64",
            "rootfs": diffs, "config_sha256": digest(config_bytes),
            "configuration_sha256": digest(json.dumps(settings, sort_keys=True).encode()),
            "jar_sha256": digest(jar), "cache_jars": sorted(cache),
            "cache_jar_inventory": [cache[path] for path in sorted(cache)]}, jar


def runtime_export_binding(bundle, report):
    """Verify the exact saved OCI manifest, config, compressed layers and Boot JAR."""
    provenance = read_json(bundle / "provenance.json")
    archive_path = bundle / "image.tar"
    require(file_digest(archive_path) == provenance["files"]["image.tar"], "runtime export hash mismatch")
    actual, _ = image_archive(archive_path, jar_path=provenance["jar_path"], stage=STAGES[1])
    require(actual == report["image"] and file_digest(bundle / "image-config.json") == actual["config_sha256"],
            "runtime export/config/rootfs/JAR differs from assessed image")
    with tarfile.open(archive_path, "r:*") as archive:
        index = decode(member_bytes(archive, "index.json"))
        require(index.get("schemaVersion") == 2 and len(index.get("manifests", [])) == 1,
                "runtime requires single-manifest OCI export")
        descriptor = index["manifests"][0]
        checksum = descriptor.get("digest")
        require(identity(checksum) and descriptor.get("platform") == {"architecture": "amd64", "os": "linux"},
                "runtime manifest identity/platform mismatch")
        manifest_bytes = member_bytes(archive, "blobs/sha256/" + checksum.split(":")[1])
        manifest = decode(manifest_bytes)
        saved = decode(member_bytes(archive, "manifest.json"))[0]
        config_bytes = member_bytes(archive, saved["Config"])
        require("sha256:" + digest(manifest_bytes) == checksum and descriptor["size"] == len(manifest_bytes)
                and manifest.get("mediaType") == descriptor.get("mediaType")
                and manifest["config"]["digest"] == actual["image_id"]
                and manifest["config"]["size"] == len(config_bytes)
                and "sha256:" + digest(config_bytes) == actual["image_id"]
                and saved["Layers"] == ["blobs/sha256/" + layer["digest"].split(":")[1] for layer in manifest["layers"]],
                "runtime OCI manifest/config/layer binding mismatch")
        for path, layer in zip(saved["Layers"], manifest["layers"], strict=True):
            members = [member for member in archive.getmembers() if member.name == path]
            require(len(members) == 1 and members[0].isfile() and members[0].size == layer["size"]
                    and "sha256:" + stream_digest(archive.extractfile(members[0]), max_bytes=ARCHIVE_LIMIT) == layer["digest"],
                    "runtime compressed layer digest/size mismatch")
        tags = saved.get("RepoTags", [])
        require(len(tags) == 1 and re.fullmatch(r"edgeforge-image-proof-[a-z0-9-]+:[a-z0-9-]+-final", tags[0]),
                "runtime export lacks unique task-owned local tag")
    return {"assessed_config_id": actual["image_id"], "manifest_digest": checksum,
            "export_sha256": provenance["files"]["image.tar"], "jar_sha256": actual["jar_sha256"],
            "rootfs": actual["rootfs"], "platform": "linux/amd64", "tag": tags[0],
            "generator_sha": provenance["generator_sha"],
            "collector_sha": provenance.get("collector_sha", provenance["generator_sha"])}, manifest_bytes


def config_semantics(value):
    if isinstance(value, dict):
        return {key: config_semantics(item) for key, item in value.items() if item not in (None, "", False, 0, [], {})}
    if isinstance(value, list):
        return [config_semantics(item) for item in value]
    return value


def validate_runtime_inspection(binding, inspected, config, manifest_bytes):
    manifest = decode(manifest_bytes)
    require("sha256:" + digest(manifest_bytes) == binding["manifest_digest"]
            and manifest["config"]["digest"] == binding["assessed_config_id"]
            and inspected.get("Descriptor", {}).get("digest") == binding["manifest_digest"]
            and inspected.get("Id") in {binding["manifest_digest"], binding["assessed_config_id"]}
            and (inspected.get("Os"), inspected.get("Architecture")) == ("linux", "amd64")
            and inspected.get("RootFS", {}).get("Layers") == binding["rootfs"] == config["rootfs"]["diff_ids"]
            and config_semantics(inspected.get("Config")) == config_semantics(config["config"])
            and config["config"].get("User") == "edgeforge"
            and config["config"].get("Entrypoint") == ["java", "-jar", "/app/app.jar"],
            "loaded local tag manifest/config/rootfs/default launch identity mismatch")


def jar_inventory(jar, policy, resolved):
    require(isinstance(resolved, list) and resolved, "empty resolved Maven inventory")
    expected = {}
    for row in resolved:
        if row["scope"] not in {"compile", "runtime"} or row["type"] != "jar":
            continue
        classifier = "-" + row["classifier"] if row.get("classifier") else ""
        filename = f"{row['artifact']}-{row['version']}{classifier}.jar"
        require(filename not in expected, "ambiguous resolved library filename")
        expected[filename] = row
    boot_versions = {row["version"] for row in resolved
                     if row["group"] == "org.springframework.boot" and row["artifact"] == "spring-boot"}
    if len(boot_versions) == 1:
        version = next(iter(boot_versions))
        expected[f"spring-boot-jarmode-tools-{version}.jar"] = {
            "group": "org.springframework.boot", "artifact": "spring-boot-jarmode-tools",
            "version": version, "classifier": "", "origin": "packaging-bootstrap"}
    require(policy.get("packaged_policy") == "passed" and policy.get("resolved_policy") == "passed"
            and policy.get("dependency_policy"), "dependency policy receipt missing or invalid")
    records, native = [], []
    with zipfile.ZipFile(io.BytesIO(jar)) as boot:
        libraries = [info for info in boot.infolist()
                     if info.filename.startswith("BOOT-INF/lib/") and info.filename.endswith(".jar")]
        names = sorted(info.filename.removeprefix("BOOT-INF/lib/") for info in libraries)
        require(names and names == sorted(set(names)) and all("/" not in name for name in names),
                "empty or malformed Boot library inventory")
        missing = set(expected) - set(names)
        # Boot omits metadata-only starter archives; the actual policy list is
        # still exact. No arbitrary runtime dependency may disappear this way.
        allowed_missing = {filename for filename, row in expected.items()
                           if row["group"] == "org.springframework.boot"
                           and (row["artifact"] == "spring-boot-starter"
                                or row["artifact"].startswith("spring-boot-starter-"))}
        require(names == policy["packaged_libraries"] and set(names) <= set(expected)
                and missing <= allowed_missing,
                "actual packaged/resolved/policy library mismatch")
        require(sum(info.file_size for info in libraries) <= 2 * 1024**3,
                "packaged inventory exceeds bounded extraction")
        for info in libraries:
            require(info.file_size <= LIMIT, "oversized packaged library")
            data = boot.read(info)
            filename = info.filename.removeprefix("BOOT-INF/lib/")
            row = expected[filename]
            records.append({"filename": filename, "group": row["group"], "artifact": row["artifact"],
                            "version": row["version"], "classifier": row.get("classifier", ""),
                            "sha256": digest(data), "origin": row.get("origin", "resolved-runtime")})
            with zipfile.ZipFile(io.BytesIO(data)) as library:
                require(len(library.infolist()) <= 200000, "oversized library member inventory")
                properties = []
                for member in library.infolist():
                    if member.filename.startswith("META-INF/maven/") and member.filename.endswith("/pom.properties"):
                        require(member.file_size <= 65536, "oversized Maven identity metadata")
                        properties.append(dict(re.findall(r"(?m)^([^#!\s=]+)\s*=\s*(.*?)\s*$",
                                                         library.read(member).decode("utf-8"))))
                    if re.search(r"(?:\.so(?:\.\d+)*|\.dll|\.dylib|\.jnilib)$", member.filename):
                        require(member.file_size <= LIMIT, "oversized native member")
                        native.append({"library": filename, "member": member.filename,
                                       "sha256": digest(library.read(member)),
                                       "assessment": "member-hash-only; native advisory identity unresolved"})
                if properties:
                    require(any((p.get("groupId"), p.get("artifactId"), p.get("version")) ==
                                (row["group"], row["artifact"], row["version"]) for p in properties),
                            "packaged Maven metadata identity/version mismatch")
    return sorted(records, key=lambda row: row["filename"]), sorted(native, key=lambda row: (row["library"], row["member"]))


def locations(artifact):
    return [location[field] for location in artifact.get("locations", [])
            for field in ("path", "realPath", "accessPath") if isinstance(location.get(field), str)]


def validate_packaged_bom(packaged, bom):
    from scripts.assess_generated_maven import AssessmentError, purl_coordinate

    require(bom.get("bomFormat") == "CycloneDX" and isinstance(bom.get("components"), list)
            and bom["components"], "retained Maven BOM missing or malformed")
    components = {}
    for component in bom["components"]:
        try:
            key = purl_coordinate(component)
        except (AssessmentError, ValueError, KeyError, TypeError) as exc:
            raise ImageAssessmentError("retained BOM component coordinate malformed") from exc
        components.setdefault(key, []).append(component)
    results = []
    for row in packaged:
        key = (row["group"], row["artifact"], row["version"], "jar", row.get("classifier", ""))
        matches = components.get(key, [])
        bootstrap = row.get("origin") == "packaging-bootstrap" and key[:2] == (
            "org.springframework.boot", "spring-boot-jarmode-tools")
        if bootstrap and not matches:
            require(any(item["group"] == "org.springframework.boot" and item["artifact"] == "spring-boot"
                        and item["version"] == row["version"] for item in packaged),
                    "packaging bootstrap version is not tied to packaged Spring Boot")
            results.append({"filename": row["filename"], "status": "not-covered-packaging-bootstrap",
                            "sha256": row["sha256"], "reason": "packaging-added same-version library absent from retained Maven BOM"})
            continue
        require(len(matches) == 1, "required packaged BOM component missing or duplicate")
        hashes = [item.get("content") for item in matches[0].get("hashes", []) if item.get("alg") == "SHA-256"]
        require(len(hashes) == 1 and isinstance(hashes[0], str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", hashes[0])
                and hashes[0].lower() == row["sha256"], "required packaged BOM SHA256 missing, duplicate or mismatched")
        results.append({"filename": row["filename"], "status": "matched-retained-bom-sha256", "sha256": row["sha256"]})
    return results


def packaged_sbom(jar, packaged, bom, source_tar, image):
    """Reuse retained components only after exact actual-image library hash checks."""
    from scripts.assess_generated_maven import purl_coordinate

    require(digest(jar) == image["jar_sha256"], "authoritative SBOM actual Boot JAR hash mismatch")
    integrity = validate_packaged_bom(packaged, bom)
    components = {purl_coordinate(component): component for component in bom["components"]}
    result, bootstrap = [], []
    with zipfile.ZipFile(io.BytesIO(jar)) as boot:
        names = [item.filename for item in boot.infolist()
                 if item.filename.startswith("BOOT-INF/lib/") and item.filename.endswith(".jar")]
        require(sorted(names) == sorted("BOOT-INF/lib/" + row["filename"] for row in packaged)
                and len(names) == len(set(names)), "authoritative SBOM actual package set mismatch")
        for row, receipt in zip(packaged, integrity, strict=True):
            data = boot.read("BOOT-INF/lib/" + row["filename"])
            require(digest(data) == row["sha256"], "authoritative SBOM actual JAR hash mismatch")
            key = (row["group"], row["artifact"], row["version"], "jar", row.get("classifier", ""))
            if receipt["status"] == "matched-retained-bom-sha256":
                component = copy.deepcopy(components[key])
            else:
                # This packaging-added library has no embedded Maven POM. Bind
                # its manifest to the actual generated POM, not its filename.
                with tarfile.open(source_tar, "r:*") as source:
                    pom = member_bytes(source, "pom.xml", limit=1024 * 1024)
                with zipfile.ZipFile(io.BytesIO(data)) as library:
                    manifest = library.read("META-INF/MANIFEST.MF").decode("utf-8")
                component = {"type": "library", "group": key[0], "name": key[1], "version": key[2]}
                bootstrap.append(bootstrap_receipt(manifest, row, pom))
            purl = f"pkg:maven/{quote(key[0], safe='.')}/{quote(key[1], safe='')}@{quote(key[2], safe='')}"
            qualifiers = ("classifier=" + quote(key[4], safe="") + "&") if key[4] else ""
            component.update({"type": "library", "bom-ref": purl + "?" + qualifiers + "type=jar",
                              "purl": purl + "?" + qualifiers + "type=jar",
                              "hashes": [{"alg": "SHA-256", "content": row["sha256"]}]})
            result.append(component)
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"properties": [{"name": "edgeforge:image-id", "value": image["image_id"]},
                                        {"name": "edgeforge:boot-jar-sha256", "value": image["jar_sha256"]}]},
            "components": result}, bootstrap


def bootstrap_receipt(manifest, row, pom):
    parent = ET.fromstring(pom).find("{*}parent")
    fields = dict(re.findall(r"(?m)^([^:\r\n]+): ([^\r\n]*)", manifest))
    require((row["group"], row["artifact"]) == ("org.springframework.boot", "spring-boot-jarmode-tools")
            and parent is not None and parent.findtext("{*}groupId") == "org.springframework.boot"
            and parent.findtext("{*}artifactId") == "spring-boot-starter-parent"
            and parent.findtext("{*}version") == row["version"]
            and fields.get("Automatic-Module-Name") == "spring.boot.jarmode.tools"
            and fields.get("Implementation-Title") == "Spring Boot Jarmode Tools"
            and fields.get("Implementation-Version") == row["version"], "bootstrap POM/manifest identity mismatch")
    return {"filename": row["filename"], "sha256": row["sha256"],
            "source_pom_sha256": digest(pom), "manifest_sha256": digest(manifest.encode()), "manifest": manifest,
            "identity_basis": "generated Boot parent POM plus actual jarmode manifest; no embedded Maven POM",
            "retained_bom": "not covered; packaging-added component"}


def validate_bootstrap_provenance(receipts, packaged, source_tar):
    expected = [row for row in packaged if row.get("origin") == "packaging-bootstrap"]
    require(isinstance(receipts, list) and len(receipts) == len(expected), "bootstrap identity receipt missing or duplicate")
    for receipt, row in zip(receipts, expected, strict=True):
        with tarfile.open(source_tar, "r:*") as source:
            pom = member_bytes(source, "pom.xml", limit=1024 * 1024)
        require(receipt == bootstrap_receipt(receipt.get("manifest", ""), row, pom), "bootstrap POM/manifest/hash receipt mismatch")


def grype_findings(report, indexed, scanner):
    require(report.get("descriptor", {}).get("version") == read_json(PINS)["tools"]["grype"]["version"],
            "unexpected Grype report version")
    db = report.get("descriptor", {}).get("db", {}).get("status", {})
    require(db.get("valid") is True and db.get("built") and db.get("schemaVersion"), "invalid Grype advisory database")
    findings = []
    for field in ("matches", "ignoredMatches"):
        matches = report.get(field, [] if field == "ignoredMatches" else None)
        require(isinstance(matches, list), "missing scanner findings array")
        for match in matches:
            artifact = match["artifact"]
            original = indexed.get(artifact.get("id"))
            require(original is not None and all(original[key] == artifact.get(key)
                    for key in ("name", "version", "type")), "finding/package identity mismatch")
            vulnerability = match["vulnerability"]
            item = {"scanner": scanner, "id": text(vulnerability.get("id")),
                    "type": artifact["type"], "name": artifact["name"], "version": artifact["version"],
                    "severity": vulnerability.get("severity") or "Unknown",
                    "fix": vulnerability.get("fix", {}), "excluded_by_scanner": field == "ignoredMatches"}
            if scanner in {"grype-packaged-authoritative", "grype-build-classifier-authoritative"}:
                item["purl"] = artifact["purl"]
            if field == "ignoredMatches":
                require(match.get("appliedIgnoreRules"), "ignored match lacks rule receipt")
                item["rules"] = match["appliedIgnoreRules"]
            findings.append(item)
    return findings, db


def validate_authoritative_sbom(sbom, packaged, image):
    from scripts.assess_generated_maven import purl_coordinate

    require(sbom.get("bomFormat") == "CycloneDX" and sbom.get("specVersion") == "1.6"
            and isinstance(sbom.get("components"), list), "malformed authoritative packaged SBOM")
    expected = {(row["group"], row["artifact"], row["version"], "jar", row.get("classifier", "")): row
                for row in packaged}
    require(len(expected) == len(packaged) and packaged, "duplicate or empty authoritative package set")
    actual = {}
    for component in sbom["components"]:
        key = purl_coordinate(component)
        require(key not in actual and key in expected and component.get("type") == "library"
                and component.get("hashes") == [{"alg": "SHA-256", "content": expected[key]["sha256"]}],
                "authoritative SBOM package/version/hash mismatch")
        actual[key] = component
    require(set(actual) == set(expected), "authoritative SBOM package set incomplete")
    require(sbom.get("metadata", {}).get("properties") == [
        {"name": "edgeforge:image-id", "value": image["image_id"]},
        {"name": "edgeforge:boot-jar-sha256", "value": image["jar_sha256"]}],
        "authoritative SBOM actual image/JAR identity mismatch")
    return actual


def validate_packaged_grype(sbom, extracted, report, packaged, image):
    expected = validate_authoritative_sbom(sbom, packaged, image)
    return validate_grype_sbom(sbom, extracted, report, expected, "packaged-authoritative.cdx.json", "grype-packaged-authoritative")


def validate_grype_sbom(sbom, extracted, report, expected, source_name, scanner):
    from scripts.assess_generated_maven import purl_coordinate

    require(report.get("source", {}).get("type") == "sbom-file"
            and Path(report["source"].get("target", "")).name == source_name,
            "supplemental Grype SBOM source mismatch")
    require(extracted.get("bomFormat") == "CycloneDX" and isinstance(extracted.get("components"), list),
            "missing Grype extracted packaged inventory")
    actual = [purl_coordinate(component) for component in extracted["components"]]
    require(len(actual) == len(set(actual)) and set(actual) == set(expected),
            "Grype authoritative packaged coordinate extraction incomplete")
    indexed = {}
    for field in ("matches", "ignoredMatches"):
        matches = report.get(field, [] if field == "ignoredMatches" else None)
        require(isinstance(matches, list), "missing supplemental scanner findings array")
        for match in matches:
            artifact = match["artifact"]
            purl = artifact.get("purl", "")
            component = next((c for c in sbom["components"] if c["purl"] == purl), None)
            require(component is not None and artifact.get("type") == "java-archive"
                    and artifact.get("version") == component["version"]
                    and artifact.get("name") in {component["name"], component["group"] + ":" + component["name"]},
                    "supplemental finding authoritative package identity mismatch")
            indexed[artifact["id"]] = artifact
    findings, db = grype_findings(report, indexed, scanner)
    return findings, db


def build_classifier_sbom(bom, resolved, image, provenance):
    """The two qualified Kafka test classifiers, never inferred from filenames."""
    from scripts.assess_generated_maven import purl_coordinate

    require(isinstance(bom, dict) and bom.get("bomFormat") == "CycloneDX"
            and isinstance(bom.get("components"), list) and bom["components"]
            and isinstance(resolved, list) and resolved, "build per-app BOM/resolved inventory missing")
    components = [(purl_coordinate(component), component) for component in bom["components"]]
    selected = [(key, component) for key, component in components if key[4]]
    if not selected:
        require(not any(row.get("classifier") for row in resolved), "classifier BOM/resolved set mismatch")
        return None
    expected = {("org.apache.kafka", artifact, "4.2.1", "jar", "test") for artifact in ("kafka-clients", "kafka-server-common")}
    require(len(selected) == 2 and {key for key, _ in selected} == expected,
            "unsupported, missing or duplicate build classifier coordinate")
    declared = [row for row in resolved if row.get("classifier")]
    require(len(declared) == 2 and {(row["group"], row["artifact"], row["version"], row["type"], row["classifier"])
                                  for row in declared if row["scope"] == "test"} == expected,
            "build classifier resolved identity/scope mismatch")
    result = []
    for key, component in sorted(selected):
        hashes = [item["content"] for item in component.get("hashes", []) if item.get("alg") == "SHA-256"]
        require(len(hashes) == 1 and isinstance(hashes[0], str) and re.fullmatch(r"[0-9a-fA-F]{64}", hashes[0]),
                "build classifier BOM hash missing or malformed")
        checksum = hashes[0].lower()
        paths = sorted(row["path"] for row in image["cache_jar_inventory"] if row["sha256"] == checksum)
        require(paths, "build classifier actual cache hash mismatch")
        result.append({"type": "library", "group": key[0], "name": key[1], "version": key[2],
                       "purl": component["purl"], "bom-ref": component["purl"], "scope": "required",
                       "hashes": [{"alg": "SHA-256", "content": checksum}],
                       "properties": [{"name": "edgeforge:resolved-scope", "value": "test"},
                                      *({"name": "edgeforge:cache-path", "value": path} for path in paths)]})
    require(isinstance(provenance, dict) and all(re.fullmatch(r"[0-9a-f]{40}", provenance.get(key, ""))
            for key in ("generator_sha", "collector_sha")), "build classifier source identity missing")
    properties = [{"name": "edgeforge:image-id", "value": image["image_id"]},
                  {"name": "edgeforge:boot-jar-sha256", "value": image["jar_sha256"]},
                  *({"name": "edgeforge:" + key.replace("_", "-"), "value": provenance[key]}
                    for key in ("generator_sha", "collector_sha"))]
    for name in ("source.tar", "retained-maven-bom.json", "resolved-inventory.json"):
        checksum = provenance["files"].get(name, "")
        require(re.fullmatch(r"[0-9a-f]{64}", checksum), "build classifier source hash missing")
        properties.append({"name": "edgeforge:" + name + "-sha256", "value": checksum})
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"properties": properties}, "components": result}


def scan_classifier_grype(binary, sbom, output, env):
    write_json(output / CLASSIFIER_JSON[0], sbom)
    run_tool([binary, f"sbom:{output / CLASSIFIER_JSON[0]}", "-o", f"json={output / CLASSIFIER_JSON[1]}",
              "-o", f"cyclonedx-json={output / CLASSIFIER_JSON[2]}"], directory=output, label="grype-build-classifiers", env=env)


def scan_packaged_grype(binary, sbom, output, env):
    write_json(output / "packaged-authoritative.cdx.json", sbom)
    run_tool([binary, f"sbom:{output / 'packaged-authoritative.cdx.json'}",
              "-o", f"json={output / 'grype-packaged.json'}",
              "-o", f"cyclonedx-json={output / 'grype-packaged-extracted.cdx.json'}"],
             directory=output, label="grype-packaged", env=env)


def build_bom_coverage(bom, resolved, image, trivy, authoritative, extracted, *, classifiers=None, classifier_extracted=None):
    """No declared app/test JAR may be relabeled an optional plugin/cache gap."""
    from scripts.assess_generated_maven import purl_coordinate

    require(isinstance(bom, dict) and bom.get("bomFormat") == "CycloneDX"
            and isinstance(bom.get("components"), list) and bom["components"]
            and isinstance(resolved, list) and resolved, "build per-app BOM/resolved inventory missing")
    declared = [row for row in resolved if row["type"] == "jar" and row["scope"] in {"compile", "runtime", "test", "provided"}]
    expected = {(row["group"], row["artifact"], row["version"], row["type"], row.get("classifier", "")): row["scope"]
                for row in declared}
    components = {purl_coordinate(component): component for component in bom["components"]}
    require(expected and len(expected) == len(declared) and len(components) == len(bom["components"])
            and set(components) == set(expected),
            "build per-app resolved/BOM component set missing, duplicate or mismatched")
    supplemental = {purl_coordinate(component): component for component in authoritative["components"]}
    imported = {purl_coordinate(component) for component in extracted["components"]}
    classifier_keys = set()
    if classifiers is not None:
        classifier_keys = {purl_coordinate(component) for component in classifiers["components"]}
        supplemental.update({purl_coordinate(component): component for component in classifiers["components"]})
        imported.update(purl_coordinate(component) for component in classifier_extracted["components"])
    packages = [package for result in trivy["Results"] if result.get("Class") == "lang-pkgs" and result.get("Type") == "jar"
                for package in result["Packages"]]
    coverage = []
    for key, component in sorted(components.items()):
        hashes = [item.get("content") for item in component.get("hashes", []) if item.get("alg") == "SHA-256"]
        require(len(hashes) == 1 and isinstance(hashes[0], str) and re.fullmatch(r"[0-9a-fA-F]{64}", hashes[0]),
                "build per-app BOM SHA256 missing, duplicate or malformed")
        checksum = hashes[0].lower()
        paths = sorted(row["path"] for row in image["cache_jar_inventory"] if row["sha256"] == checksum)
        require(paths, "required per-app application/test cache JAR missing or hash mismatched")
        matched = False
        for package in packages:
            if "/" + package.get("FilePath", "").lstrip("/") not in paths or package.get("Version") != key[2]:
                continue
            try:
                observed = purl_coordinate({"group": key[0], "name": key[1], "version": key[2],
                                            "purl": package.get("Identifier", {}).get("PURL", "")})
            except ValueError:
                continue
            if observed == key:
                matched = True
                break
        supplemental_match = key in imported and key in supplemental and supplemental[key].get("hashes") == [
            {"alg": "SHA-256", "content": checksum}]
        require(matched or supplemental_match,
                "required per-app application/test coordinate vulnerability-extractor coverage incomplete")
        coverage.append({"group": key[0], "artifact": key[1], "version": key[2], "classifier": key[4],
                         "scope": expected[key], "purl": component["purl"], "sha256": checksum, "cache_paths": paths,
                         "extractor": "trivy" if matched else ("grype-build-classifier-authoritative" if key in classifier_keys
                                                                else "grype-packaged-authoritative")})
    return coverage


def qualify_packaged(bundle, output, *, tools, grype_db, trivy_cache):
    require(not output.exists(), "qualification output exists; never overwrite an observation")
    output.mkdir(parents=True)
    receipt = {"status": "incomplete", "exit_code": 2, "started_at_utc": utc_now(),
               "purpose": "one offline retained-image packaged SBOM qualification; not campaign coverage",
               "collector_file_sha256": file_digest(Path(__file__))}
    try:
        provenance = read_json(bundle / "provenance.json")
        for name in ("image.tar", "source.tar", "retained-maven-bom.json", "resolved-inventory.json", "dependency-policy.json"):
            require(file_digest(bundle / name) == provenance["files"][name], "qualification retained input hash mismatch")
        image, jar = image_archive(bundle / "image.tar", jar_path=provenance["jar_path"], stage=provenance["stage"])
        packaged, _ = jar_inventory(jar, read_json(bundle / "dependency-policy.json"), read_json(bundle / "resolved-inventory.json"))
        sbom, bootstrap = packaged_sbom(jar, packaged, read_json(bundle / "retained-maven-bom.json"), bundle / "source.tar", image)
        validate_authoritative_sbom(sbom, packaged, image)
        verified = output / "verified-tools"
        verified.mkdir()
        binaries = tools.parent / "verified"
        receipt["tools"] = verify_tools(tools, verified, binary_dir=binaries)
        before = db_receipt(grype_db, trivy_cache)
        home = output / "home"
        home.mkdir()
        scan_packaged_grype(binaries / "grype", sbom, output, isolated_env(home, grype_db, trivy_cache))
        findings, _ = validate_packaged_grype(sbom, read_json(output / "grype-packaged-extracted.cdx.json"),
                                             read_json(output / "grype-packaged.json"), packaged, image)
        require(before == db_receipt(grype_db, trivy_cache), "qualification database changed")
        write_json(output / "databases.json", before)
        write_json(output / "packaged.json", packaged)
        write_json(output / "bootstrap-provenance.json", bootstrap)
        write_json(output / "findings.json", findings)
        receipt.update(status="qualified", exit_code=0, image=image, generator_sha=provenance["generator_sha"],
                       packages=len(packaged), findings=len(findings))
    except (ImageAssessmentError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile,
            tarfile.TarError, ET.ParseError) as exc:
        receipt["failure"] = str(exc)
    finally:
        receipt["retained_raw"] = retain_raw(output)
        receipt["ended_at_utc"] = utc_now()
        write_json(output / "qualification.json", receipt)
    return receipt["exit_code"]


def normalize(syft, grype, trivy, image, packaged, *, stage, authoritative, packaged_grype, extracted,
              bom=None, resolved=None, provenance=None, classifiers=None, classifier_grype=None, classifier_extracted=None):
    supplemental, supplemental_db = validate_packaged_grype(authoritative, extracted, packaged_grype, packaged, image)
    expected_classifiers = build_classifier_sbom(bom, resolved, image, provenance) if stage == STAGES[0] else None
    classifier_findings, classifier_db = [], None
    if expected_classifiers is not None:
        require(classifiers == expected_classifiers and classifier_grype is not None and classifier_extracted is not None,
                "required hash-bound build classifier assessment missing or mismatched")
        from scripts.assess_generated_maven import purl_coordinate

        classifier_findings, classifier_db = validate_grype_sbom(
            classifiers, classifier_extracted, classifier_grype,
            {purl_coordinate(component): component for component in classifiers["components"]},
            CLASSIFIER_JSON[0], "grype-build-classifier-authoritative")
        for finding in classifier_findings:
            finding.update(classifier="test", scope="test")
    else:
        require(classifiers is None and classifier_grype is None and classifier_extracted is None,
                "unexpected classifier evidence for image without qualified build classifiers")
    require(syft.get("descriptor", {}).get("version") == read_json(PINS)["tools"]["syft"]["version"],
            "unexpected Syft report version")
    source = syft.get("source", {})
    metadata = source.get("metadata", {})
    require(source.get("type") == "image" and metadata.get("imageID") == image["image_id"]
            and metadata.get("os") == "linux" and metadata.get("architecture") == "amd64"
            and [row["digest"] for row in metadata.get("layers", [])] == image["rootfs"],
            "Syft image/platform/rootfs mismatch")
    target = grype.get("source", {}).get("target", {})
    require(target.get("imageID") == image["image_id"]
            and target.get("architecture") == "amd64" and target.get("os") == "linux"
            and [row["digest"] for row in target.get("layers", [])] == image["rootfs"],
            "Grype image/platform/rootfs mismatch")
    require(grype.get("descriptor", {}).get("version") == read_json(PINS)["tools"]["grype"]["version"],
            "unexpected Grype report version")
    trivy_image = trivy.get("Metadata", {})
    require(trivy_image.get("ImageID") == image["image_id"]
            and trivy_image.get("DiffIDs") == image["rootfs"], "Trivy image/rootfs mismatch")
    artifacts = syft.get("artifacts")
    require(isinstance(artifacts, list) and artifacts, "empty scanner inventory")
    indexed = {}
    for row in artifacts:
        key = text(row.get("id"))
        require(key not in indexed, "duplicate scanner artifact identity")
        for field in ("type", "name", "version"):
            text(row.get(field))
        indexed[key] = row
    os_packages = [row for row in artifacts if row["type"] in {"deb", "rpm", "apk"}]
    jdks = [row for row in artifacts if row["type"] == "binary" and row["name"] == "openjdk"
            and any(path.endswith("/opt/java/openjdk/release") for path in locations(row))]
    require(os_packages and jdks, "OS or copied JDK extraction incomplete")
    java = [row for row in artifacts if row["type"] == "java-archive"]
    gaps = []
    for row in packaged:
        purl = f"pkg:maven/{row['group']}/{row['artifact']}@{row['version']}"
        physical = [artifact for artifact in java if any(path.endswith("BOOT-INF/lib/" + row["filename"])
                                                        for path in locations(artifact))]
        require(physical, "packaged library physical scanner location missing")
        candidates = {"syft": [(artifact.get("purl", ""), artifact["version"]) for artifact in physical],
                      "trivy": [(package.get("Identifier", {}).get("PURL", ""), package.get("Version"))
                                for result in trivy.get("Results", []) if result.get("Class") == "lang-pkgs"
                                for package in result.get("Packages", [])
                                if package.get("FilePath", "").endswith("BOOT-INF/lib/" + row["filename"])]}
        for scanner, observed in candidates.items():
            if not any(value.split("?", 1)[0] == purl and version == row["version"] for value, version in observed):
                gaps.append({"scanner": scanner, "filename": row["filename"], "authoritative_purl": purl,
                             "image_grype_uses_this_inferred_sbom": scanner == "syft",
                             "observed": [{"purl": value, "version": version} for value, version in sorted(set(observed))],
                             "coverage": "separate hash-bound authoritative packaged Grype scan; original unchanged"})
    cache_gaps = []
    if stage == STAGES[0]:
        cache = image.get("cache_jar_inventory", [])
        require(cache and [row["path"] for row in cache] == image["cache_jars"]
                and all(re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", ""))
                        and isinstance(row.get("bytes"), int) and row["bytes"] > 0 for row in cache),
                "build Maven/plugin/bootstrap physical extraction incomplete")
        scanned_paths = {path for artifact in java for path in locations(artifact)}
        cache_gaps = [{**row, "coverage": "physical JAR extracted/hashed; scanner coordinate/feed unsupported"}
                      for row in cache if row["path"] not in scanned_paths]
    findings, db = grype_findings(grype, indexed, "grype")
    require(supplemental_db == db, "authoritative/image Grype database identity mismatch")
    findings.extend(supplemental)
    require(classifier_db is None or classifier_db == db, "classifier/image Grype database identity mismatch")
    findings.extend(classifier_findings)
    results = trivy.get("Results")
    require(isinstance(results, list) and results, "missing Trivy extraction results")
    trivy_os = set()
    for result in results:
        kind = text(result.get("Type"))
        packages = result.get("Packages")
        require(isinstance(packages, list) and packages, "empty Trivy package inventory")
        installed = set()
        package_ids = set()
        for package in packages:
            name, version = text(package.get("Name")), text(package.get("Version"))
            if result.get("Class") == "os-pkgs":
                version = (str(package["Epoch"]) + ":" if package.get("Epoch") else "") + version
                version += "-" + text(package["Release"]) if package.get("Release") else ""
                package_id = package.get("ID", "")
                require(not package_id or package_id == name + "@" + version, "Trivy OS package ID/version mismatch")
                trivy_os.add((name, version))
            installed.add((name, version))
            if package.get("ID"):
                package_ids.add(package["ID"])
        vulnerabilities = result.get("Vulnerabilities", [])
        require(vulnerabilities is None or isinstance(vulnerabilities, list), "malformed Trivy findings")
        for vulnerability in vulnerabilities or []:
            name, version = text(vulnerability.get("PkgName")), text(vulnerability.get("InstalledVersion"))
            require((name, version) in installed and (not vulnerability.get("PkgID")
                    or vulnerability["PkgID"] in package_ids), "Trivy finding/package identity mismatch")
            findings.append({"scanner": "trivy", "id": text(vulnerability.get("VulnerabilityID")),
                             "type": kind, "name": name, "version": version,
                             "severity": vulnerability.get("Severity") or "UNKNOWN",
                             "fixed_version": vulnerability.get("FixedVersion") or "",
                             "excluded_by_scanner": False})
    require({(row["name"], row["version"]) for row in os_packages} == trivy_os,
            "OS inventory cross-check mismatch")
    build_coverage = build_bom_coverage(bom, resolved, image, trivy, authoritative, extracted,
                                      classifiers=classifiers, classifier_extracted=classifier_extracted) if stage == STAGES[0] else []
    declared_paths = {path for row in build_coverage for path in row["cache_paths"]}
    for gap in cache_gaps:
        gap["per_app_bom"] = gap["path"] in declared_paths
        gap["coverage"] = ("required per-app BOM JAR; covered by strict build BOM extractor receipt" if gap["per_app_bom"]
                           else "outside per-app BOM; physical JAR extracted/hashed; plugin/bootstrap coordinate/feed unsupported")
    findings.sort(key=lambda item: json.dumps(item, sort_keys=True))
    return {"inventory": [{key: row.get(key) for key in ("id", "type", "name", "version", "purl")}
                          for row in sorted(artifacts, key=lambda row: row["id"])],
            "findings": findings, "grype_db": db, "coordinate-gaps": gaps, "cache-scanner-gaps": cache_gaps,
            "build-bom-coverage": build_coverage,
            "coverage": {"os": "cross-checked", "jdk": "identified; vendor feed limitations",
                         "packaged_maven": "hash-bound authoritative SBOM; all coordinates extracted by supplemental Grype",
                         "native": "member hashes; feed limitations",
                         "build_cache": "physical JARs extracted/hashed; inferred coordinate/feed gaps explicit"
                         if stage == STAGES[0] else "not applicable",
                         "build_app_maven": "all declared per-app resolved/test BOM JARs hash-bound and vulnerability-extractor covered"
                         if stage == STAGES[0] else "not applicable"}}


def db_receipt(grype_db, trivy_cache):
    receipt = {}
    for name, directory, required in (
            ("grype", grype_db, "vulnerability.db"),
            ("trivy", trivy_cache / "db", "trivy.db"),
            ("trivy-java", trivy_cache / "java-db", "trivy-java.db")):
        files = sorted(path for path in directory.rglob("*") if path.is_file())
        require(any(path.name == required for path in files), "required local advisory database missing")
        metadata = [path for path in files if path.name in {"metadata.json", "import.json"}]
        require(metadata, "local database date/identity receipt missing")
        receipt[name] = {"files": [{"file": str(path.relative_to(directory)), "sha256": file_digest(path)}
                                   for path in files],
                         "metadata": [read_json(path) for path in metadata]}
    return receipt


def retain_raw(output):
    """Deterministic gzip aliases preserve originals without manual pruning."""
    receipts = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name not in {"assessment.json", "summary.txt"} and path.suffix != ".gz":
            target = path.with_name(path.name + ".gz")
            with path.open("rb") as source, target.open("wb") as dest:
                with gzip.GzipFile(filename="", mode="wb", fileobj=dest, mtime=0) as compressed:
                    shutil.copyfileobj(source, compressed)
            receipts.append({"file": path.name, "sha256": file_digest(path),
                             "bytes": path.stat().st_size, "gzip_sha256": file_digest(target)})
    return receipts


def check_freeze(approval, declaration, generator_sha):
    require(approval.get("campaign_approved") is True
            and approval.get("generator_sha") == generator_sha
            and approval.get("coverage_sha256") == file_digest(declaration),
            "parent clean-freeze/map approval required")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                         capture_output=True, text=True, timeout=10).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, check=True,
                            capture_output=True, text=True, timeout=10).stdout
    collector_sha = approval.get("collector_sha", generator_sha)
    require(sha == generator_sha == collector_sha and not status,
            "campaign requires generator/collector SHAs equal actual clean frozen HEAD")


def collect(bundle, output, *, case, stage, declaration, approval, tools, grype_db, trivy_cache, storage_continuation=False):
    require(not output.exists(), "output already exists; failed observations must not be overwritten")
    output.mkdir(parents=True)
    report = {"schema_version": 1, "case": case, "stage": stage, "status": "incomplete",
              "started_at_utc": utc_now(),
              "exit_code": 2, "limitations": LIMITATIONS, "release_acceptance": "not established"}
    try:
        plan = make_plan(read_json(declaration))
        selected = next((row for row in plan["cases"] if row["case"] == case), None)
        require(selected is not None and stage in STAGES, "undeclared case/stage")
        provenance = read_json(bundle / "provenance.json")
        sha = provenance["generator_sha"]
        require(re.fullmatch(r"[0-9a-f]{40}", sha) and provenance["case"] == case
                and provenance["profile"] == selected["profile"] and provenance["stage"] == stage,
                "generation provenance mismatch")
        authorized = read_json(approval)
        if storage_continuation:
            require(case == STORAGE_PARTIAL_CASE and stage == STAGES[1] and sha == STORAGE_PRIOR_SHA
                    and provenance.get("collector_sha") == STORAGE_PRIOR_SHA
                    and authorized.get("storage_continuation_approved") is True
                    and authorized.get("reuse_stages") == storage_reuse_bindings(), "only the approved saved final export may use a new assessment helper")
            manifest = bundle.parent.parent / "storage-prior-files.sha256"
            require(file_digest(manifest) == authorized.get("prior_manifest_sha256"), "saved final export approved manifest mismatch")
            for name in ("image.tar", "provenance.json"):
                suffix = f"/{STORAGE_PARTIAL_CASE}/{STAGES[1]}-bundle/{name}"
                hashes = [line.split("  ", 1)[0] for line in manifest.read_text(encoding="utf-8").splitlines()
                          if line.endswith(suffix) and "  " in line]
                require(hashes == [file_digest(bundle / name)], "saved final export differs from approved original manifest")
            check_freeze(authorized, declaration, authorized["generator_sha"])
            report["assessment_helper_sha"] = authorized["generator_sha"]
        else:
            check_freeze(authorized, declaration, sha)
        for name in ("Dockerfile", "source.tar", "input.tar", "generation.json", "resolved-inventory.json",
                     "dependency-policy.json", "image.tar", "base-images.json", "retained-maven-bom.json"):
            require(provenance["files"].get(name) == file_digest(bundle / name),
                    "retained source/recipe/config/image provenance hash mismatch")
        bases = read_json(bundle / "base-images.json")
        require(isinstance(bases, list) and len(bases) == 2
                and all(identity(row.get("image_id")) and row.get("platform") == "linux/amd64"
                        and isinstance(row.get("repo_digests"), list) and row["repo_digests"]
                        and all(identity(value.rsplit("@", 1)[-1]) for value in row["repo_digests"])
                        for row in bases), "resolved base digest receipts missing")
        image, jar = image_archive(bundle / "image.tar", jar_path=provenance["jar_path"], stage=stage)
        packaged, native = jar_inventory(jar, read_json(bundle / "dependency-policy.json"),
                                         read_json(bundle / "resolved-inventory.json"))
        bom_integrity = validate_packaged_bom(packaged, read_json(bundle / "retained-maven-bom.json"))
        authoritative, bootstrap = packaged_sbom(jar, packaged, read_json(bundle / "retained-maven-bom.json"),
                                                 bundle / "source.tar", image)
        validate_authoritative_sbom(authoritative, packaged, image)
        report.update(generator_sha=sha, collector_sha=provenance.get("collector_sha", sha), image=image, bases=bases)
        write_json(output / "packaged.json", packaged)
        write_json(output / "native-members.json", native)
        write_json(output / "packaged-bom-integrity.json", bom_integrity)
        write_json(output / "bootstrap-provenance.json", bootstrap)
        write_json(output / "provenance.json", provenance)
        shutil.copyfile(bundle / "Dockerfile", output / "Dockerfile")
        before = db_receipt(grype_db, trivy_cache)
        verified = output / "verified-tools"
        verified.mkdir()
        binary_dir = tools.parent / "verified"
        report["tools"] = verify_tools(tools, verified, binary_dir=binary_dir)
        scratch = output / "scan-scratch"
        scratch.mkdir()
        (scratch / "home").mkdir()
        scan_cache = scratch / "trivy-cache"
        scan_cache.mkdir()
        for name in ("db", "java-db"):
            (scan_cache / name).symlink_to(trivy_cache / name, target_is_directory=True)
        env = isolated_env(scratch / "home", grype_db, scan_cache)
        env["TMPDIR"] = str(scratch)
        archive = bundle / "image.tar"
        run_tool([binary_dir / "syft", "scan", f"docker-archive:{archive}", "--scope", "squashed",
                  "-o", f"syft-json={output / 'syft.json'}"], directory=output, label="syft", env=env)
        run_tool([binary_dir / "grype", f"sbom:{output / 'syft.json'}", "-o", "json",
                  "--file", output / "grype.json"], directory=output, label="grype", env=env)
        run_tool([binary_dir / "trivy", "image", "--input", archive, "--offline-scan", "--skip-db-update",
                  "--skip-java-db-update", "--skip-check-update", "--skip-version-check",
                  "--disable-telemetry", "--scanners", "vuln", "--list-all-pkgs", "--format", "json",
                  "--output", output / "trivy.json"], directory=output, label="trivy", env=env)
        scan_packaged_grype(binary_dir / "grype", authoritative, output, env)
        classifiers = build_classifier_sbom(read_json(bundle / "retained-maven-bom.json"),
                                            read_json(bundle / "resolved-inventory.json"), image, provenance) if stage == STAGES[0] else None
        if classifiers is not None:
            scan_classifier_grype(binary_dir / "grype", classifiers, output, env)
        require(before == db_receipt(grype_db, trivy_cache), "advisory database changed during scan")
        write_json(output / "databases.json", before)
        normalized = normalize(read_json(output / "syft.json"), read_json(output / "grype.json"),
                               read_json(output / "trivy.json"), image, packaged, stage=stage,
                               authoritative=authoritative, packaged_grype=read_json(output / "grype-packaged.json"),
                               extracted=read_json(output / "grype-packaged-extracted.cdx.json"),
                               provenance=provenance, classifiers=classifiers,
                               classifier_grype=read_json(output / CLASSIFIER_JSON[1]) if classifiers is not None else None,
                               classifier_extracted=read_json(output / CLASSIFIER_JSON[2]) if classifiers is not None else None,
                               bom=read_json(bundle / "retained-maven-bom.json"), resolved=read_json(bundle / "resolved-inventory.json"))
        write_json(output / "inventory.json", normalized["inventory"])
        write_json(output / "findings.json", normalized["findings"])
        write_json(output / "coordinate-gaps.json", normalized["coordinate-gaps"])
        write_json(output / "cache-scanner-gaps.json", normalized["cache-scanner-gaps"])
        write_json(output / "build-bom-coverage.json", normalized["build-bom-coverage"])
        report.update(coverage=normalized["coverage"], findings=len(normalized["findings"]),
                      packaged_libraries=[row["filename"] for row in packaged],
                      status="complete-with-findings" if normalized["findings"] else "complete-no-matches",
                      exit_code=1 if normalized["findings"] else 0)
    except (ImageAssessmentError, OSError, ValueError, KeyError, TypeError, AttributeError,
            StopIteration, zipfile.BadZipFile, tarfile.TarError, ET.ParseError, subprocess.SubprocessError) as exc:
        report["failure"] = str(exc) if isinstance(exc, ImageAssessmentError) else "malformed or unavailable required evidence"
        if isinstance(exc, OwnedChildCleanupError):
            report["retention_blocked"] = "owned scanner exit unconfirmed"
    finally:
        report["retained_raw"] = [] if report.get("retention_blocked") else retain_raw(output)
        report["ended_at_utc"] = utc_now()
        write_json(output / "assessment.json", report)
        (output / "summary.txt").write_text(
            f"{case} / {stage}: {report['status']} (exit {report['exit_code']})\n"
            "No security clearance or risk acceptance. Raw evidence stays private.\n", encoding="utf-8")
    return report["exit_code"]


def kafka_reuse_bindings():
    return [{"case": case, "generator_sha": REUSE_SHA if case == REUSE_CASE else KAFKA_PRIOR_SHA,
             "collector_sha": REUSE_SHA if case == REUSE_CASE else KAFKA_PRIOR_SHA,
             "runtime_helper_sha": (CAPACITY_RUNTIME_SHA if case == REUSE_CASE else KAFKA_PRIOR_SHA)
             if case in RUNTIME_CASES else None} for case in KAFKA_REUSE_CASES]


def storage_reuse_bindings():
    sources = {row["case"]: row["generator_sha"] for row in kafka_reuse_bindings()}
    return [{"case": case, "stage": stage, "generator_sha": sources.get(case, STORAGE_PRIOR_SHA),
             "collector_sha": sources.get(case, STORAGE_PRIOR_SHA), "assessment_helper_sha": sources.get(case, STORAGE_PRIOR_SHA)}
            for case in (*STORAGE_PAIR_CASES, STORAGE_PARTIAL_CASE) for stage in STAGES
            if case != STORAGE_PARTIAL_CASE or stage == STAGES[0]]


def stage_helper(summary, case, stage, source):
    return summary["generator_sha"] if summary.get("storage_continuation") and case == STORAGE_PARTIAL_CASE and stage == STAGES[1] else source


def campaign_case_sources(summary, declaration):
    current = summary["generator_sha"]
    require(re.fullmatch(r"[0-9a-f]{40}", current)
            and summary.get("collector_sha", current) == current
            and summary.get("runtime_helper_sha", current) == current, "campaign freeze/helper source mismatch")
    lineage = summary.get("continuation")
    capacity = summary.get("capacity_continuation")
    kafka = summary.get("kafka_continuation")
    storage = summary.get("storage_continuation")
    if storage:
        require(kafka and storage.get("reuse_stages") == storage_reuse_bindings(), "only the fixed 23-stage storage stop may continue")
    if kafka:
        require(capacity and kafka.get("reuse_cases") == kafka_reuse_bindings(), "only the fixed nine-case Kafka cohort may be reused")
    helper = CAPACITY_RUNTIME_SHA if capacity else current
    if capacity:
        require(lineage and capacity.get("case") == REUSE_CASE
                and capacity.get("generator_sha") == capacity.get("collector_sha") == REUSE_SHA
                and capacity.get("runtime_helper_sha") == CAPACITY_RUNTIME_SHA,
                "only the completed first-case capacity stop may continue")
    if lineage:
        require(lineage.get("case") == REUSE_CASE and lineage.get("generator_sha") == REUSE_SHA
                and lineage.get("collector_sha") == REUSE_SHA and lineage.get("runtime_helper_sha") == helper,
                "only the approved first-case source may be reused")
    expected = {row["case"] for row in declaration["cases"]}
    observed = summary["cases"]
    require(len(observed) == 30 and {row["case"] for row in observed} == expected, "case source map must contain exactly 30 cases")
    result = {}
    for row in observed:
        source = REUSE_SHA if lineage and row["case"] == REUSE_CASE else current
        if kafka and row["case"] in KAFKA_REUSE_CASES and row["case"] != REUSE_CASE:
            source = KAFKA_PRIOR_SHA
        if storage and row["case"] in {"kafka-h2-j17", "kafka-pg-j17", STORAGE_PARTIAL_CASE}:
            source = STORAGE_PRIOR_SHA
        require(row.get("generator_sha", current) == source and row.get("collector_sha", current) == source,
                "actual case generator/collector source mismatch")
        runtime_helper = helper if lineage and row["case"] == REUSE_CASE else current
        if kafka and row["case"] == "passthrough-pg-j21":
            runtime_helper = KAFKA_PRIOR_SHA
        runtime_helper = runtime_helper if row["case"] in RUNTIME_CASES else None
        require(row.get("runtime_helper_sha", None if capacity else runtime_helper) == runtime_helper,
                "actual case runtime helper source mismatch")
        result[row["case"]] = {"generator_sha": source, "collector_sha": source, "runtime_helper_sha": runtime_helper}
        if storage:
            helpers = {stage: stage_helper(summary, row["case"], stage, source) for stage in STAGES}
            require(row.get("assessment_helper_shas") == helpers, "per-stage assessment helper source mismatch")
            result[row["case"]]["assessment_helper_shas"] = helpers
    actual = sorted({row["generator_sha"] for row in result.values()})
    require(summary.get("generator_shas", actual) == actual, "actual generator source set mismatch")
    helpers = sorted({row["runtime_helper_sha"] for row in result.values() if row["runtime_helper_sha"]})
    require(summary.get("runtime_helper_shas", helpers) == helpers, "actual runtime helper source set mismatch")
    return result


def packaged_contract(campaign, declaration, generator_sha, *, summary=None):
    require(re.fullmatch(r"[0-9a-f]{40}", generator_sha), "invalid frozen generator SHA")
    require(summary is None or summary.get("generator_sha") == generator_sha, "packaged contract campaign freeze mismatch")
    plan = make_plan(declaration)
    sources = campaign_case_sources(summary, declaration) if summary is not None else None
    rows = []
    for case in plan["cases"]:
        report = read_json(campaign / case["case"] / STAGES[1] / "assessment.json")
        source = sources[case["case"]]["generator_sha"] if sources else generator_sha
        require(report.get("generator_sha") == source and report.get("collector_sha", source) == source
                and report.get("case") == case["case"]
                and report.get("stage") == STAGES[1] and identity(report.get("image", {}).get("image_id")),
                "final image identity missing or mismatched")
        if summary is not None:
            require(report.get("assessment_helper_sha", source) == stage_helper(summary, case["case"], STAGES[1], source),
                    "final assessment helper source mismatch")
        packaged = read_json(campaign / case["case"] / STAGES[1] / "packaged.json")
        names = sorted(row["filename"] for row in packaged)
        require(names and names == sorted(set(names)) and all("/" not in name and name.endswith(".jar") for name in names)
                and re.fullmatch(r"[0-9a-f]{64}", report["image"]["jar_sha256"]), "invalid actual packaged inventory")
        require(any(row.get("file") == "packaged.json" and row.get("sha256") ==
                    evidence_digest(campaign / case["case"] / STAGES[1] / "packaged.json")
                    for row in report.get("retained_raw", [])), "packaged inventory integrity mismatch")
        rows.append({"case": case["case"], "packaged_libraries": names,
                     "image_id": report["image"]["image_id"], "jar_sha256": report["image"]["jar_sha256"]})
        if sources:
            rows[-1].update(sources[case["case"]])
    if summary is not None:
        return {"schema_version": 2, "generator_sha": generator_sha,
                "generator_sha_semantics": "campaign freeze; actual generators are recorded per case",
                "generator_shas": sorted({row["generator_sha"] for row in rows}),
                "runtime_helper_sha": summary.get("runtime_helper_sha", generator_sha),
                "runtime_helper_shas": sorted({row["runtime_helper_sha"] for row in rows if row["runtime_helper_sha"]}),
                "continuation": summary.get("continuation"), "capacity_continuation": summary.get("capacity_continuation"),
                "kafka_continuation": summary.get("kafka_continuation"),
                "storage_continuation": summary.get("storage_continuation"),
                "cases": rows}
    return {"generator_sha": generator_sha, "cases": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    plan = sub.add_parser("plan", help="declare case/artifact paths without scanning")
    plan.add_argument("--declaration", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    setup = sub.add_parser("verify-tools", help="verify locally downloaded official archives")
    setup.add_argument("--tools", type=Path, required=True)
    setup.add_argument("--output", type=Path, required=True)
    scan = sub.add_parser("collect", help="scan one approved retained case/stage export")
    for argument in ("bundle", "output", "declaration", "approval", "tools", "grype-db", "trivy-cache"):
        scan.add_argument("--" + argument, type=Path, required=True)
    scan.add_argument("--case", required=True)
    scan.add_argument("--stage", choices=STAGES, required=True)
    export = sub.add_parser("packaged-inventories", help="emit all 30 actual final-image Boot inventories")
    export.add_argument("--campaign", type=Path, required=True)
    export.add_argument("--declaration", type=Path, required=True)
    export.add_argument("--generator-sha", required=True)
    export.add_argument("--output", type=Path, required=True)
    qualification = sub.add_parser("qualify-packaged", help="one offline retained-image SBOM qualification, not campaign coverage")
    for argument in ("bundle", "output", "tools", "grype-db", "trivy-cache"):
        qualification.add_argument("--" + argument, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation in {"collect", "qualify-packaged"}:
            operation = collect if args.operation == "collect" else qualify_packaged
            return operation(**{key: value.resolve() if isinstance(value, Path) else value
                                for key, value in vars(args).items() if key != "operation"})
        require(not args.output.exists(), "output exists; do not overwrite evidence")
        if args.operation == "plan":
            write_json(args.output, make_plan(read_json(args.declaration)))
        elif args.operation == "verify-tools":
            args.output.mkdir(parents=True)
            verify_tools(args.tools.resolve(), args.output.resolve())
        else:
            receipt = args.campaign / "campaign.json"
            summary = read_json(receipt) if receipt.exists() else None
            write_json(args.output, packaged_contract(args.campaign, read_json(args.declaration), args.generator_sha, summary=summary))
        return 0
    except Exception:
        print("Required image evidence incomplete; inspect private inputs/logs.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
