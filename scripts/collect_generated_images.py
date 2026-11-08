#!/usr/bin/env python3
"""Prepare public tools/DBs or collect one approved generated-image campaign.

Never prunes Docker, rewrites generated recipes, queries Maven advisories, pushes
images, or changes Docker settings. A failed campaign is retained, not restarted.
"""

from __future__ import annotations

import argparse
import gzip
import os
import re
import shutil
import stat
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from appbuilder.generation import generate_application  # noqa: E402
from appbuilder.generation.container_policy import (  # noqa: E402
    BASE_REFERENCE_POLICIES,
    BASE_REFERENCE_POLICY_ID,
    HISTORICAL_BASE_REFERENCE_POLICY_ID,
    declared_base_references,
    pinned_base,
    reference_sets,
)
from appbuilder.metadata.translation import build_metadata_project  # noqa: E402
from scripts import assess_generated_images as assessment_tools  # noqa: E402
from scripts.assess_generated_images import (  # noqa: E402
    ARCHIVE_LIMIT,
    CAPACITY_RUNTIME_SHA,
    KAFKA_REUSE_CASES,
    PINS,
    REUSE_CASE,
    REUSE_SHA,
    RUNTIME_CASES,
    STAGES,
    STORAGE_PAIR_CASES,
    STORAGE_PARTIAL_CASE,
    STORAGE_PRIOR_SHA,
    ImageAssessmentError,
    check_freeze,
    collect,
    config_semantics,
    db_receipt,
    decode,
    digest,
    evidence_digest,
    file_digest,
    identity,
    image_archive,
    isolated_env,
    kafka_reuse_bindings,
    make_plan,
    packaged_contract,
    read_json,
    require,
    run_tool,
    runtime_export_binding,
    storage_reuse_bindings,
    utc_now,
    validate_runtime_inspection,
    verify_gzip,
    verify_tools,
    write_json,
)
from scripts.collect_generated_maven_baseline import prepare_case_input  # noqa: E402


def download(url, destination):
    require(not destination.exists(), "public download destination already exists")
    request = urllib.request.Request(url, headers={"User-Agent": "local-image-assessment"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as stream:
        total = 0
        while block := response.read(1024 * 1024):
            total += len(block)
            require(total <= 256 * 1024 * 1024, "public tool download exceeds bound")
            stream.write(block)


def setup(output):
    require(not output.exists(), "setup output already exists; preserve prior tools/DBs")
    output.mkdir(parents=True)
    archives, binaries = output / "archives", output / "verified"
    archives.mkdir()
    binaries.mkdir()
    upstream = {"syft": "anchore/syft", "grype": "anchore/grype", "trivy": "aquasecurity/trivy"}
    for name, pin in read_json(PINS)["tools"].items():
        base = f"https://github.com/{upstream[name]}/releases/download/v{pin['version']}/"
        for filename in (pin["archive"], pin["checksums"]):
            download(base + filename, archives / filename)
    verify_tools(archives, binaries)
    env = isolated_env(binaries / "home", output / "grype-db", output / "trivy-cache")
    for key in ("TRIVY_SKIP_DB_UPDATE", "TRIVY_SKIP_JAVA_DB_UPDATE"):
        env.pop(key)
    run_tool([binaries / "grype", "db", "update"], directory=output, label="grype-db-download",
             env=env, timeout=600, offline=False)
    for kind in ("db", "java-db"):
        run_tool([binaries / "trivy", "image", f"--download-{kind}-only", "--disable-telemetry",
                  "--skip-version-check"], directory=output, label=f"trivy-{kind}-download",
                 env=env, timeout=600, offline=False)
    write_json(output / "databases.json", db_receipt(output / "grype-db", output / "trivy-cache"))


_DOCKER_BOUNDARY = None
DECLARED_BASES = frozenset(ref for pair in BASE_REFERENCE_POLICIES[
    HISTORICAL_BASE_REFERENCE_POLICY_ID].values() for ref in pair)


def base_policy_status(rows):
    references = frozenset(reference for row in rows for reference in declared_base_references(row))
    policy = next((name for name, mapping in BASE_REFERENCE_POLICIES.items()
                   if references == frozenset(ref for pair in mapping.values() for ref in pair)), None)
    require(policy is not None, "mixed or unreviewed base reference policies")
    return {"base_reference_policy": policy,
            "floating_policy": (
                "reviewed Noble multi-platform INDEX pins; Engine review before release/material security changes; "
                "moved tags fail; linux/amd64 proof only; live Maven resolution remains variable; no risk acceptance"
                if policy == BASE_REFERENCE_POLICY_ID else
                "unchanged; parent must decide pin versus float, no risk acceptance")}


def validate_local_endpoint(endpoint):
    parsed = urlsplit(endpoint)
    require(parsed.scheme == "unix" and not parsed.netloc and parsed.path.startswith("/")
            and not parsed.query and not parsed.fragment
            and ".." not in Path(parsed.path).parts and Path(parsed.path).is_socket(),
            "Docker endpoint must be an existing local Unix socket; remote/offloaded contexts forbidden")
    return endpoint


def local_docker_boundary(directory, label="docker-boundary"):
    """Context inspection is local metadata only, before any context submission."""
    executable = shutil.which("docker")
    require(executable, "Docker CLI unavailable")
    env = {key: os.environ[key] for key in ("HOME", "PATH", "DOCKER_HOST", "DOCKER_CONTEXT")
           if key in os.environ}
    host = env.get("DOCKER_HOST")
    if host:
        validate_local_endpoint(host)
    current = run_tool([executable, "context", "show"], directory=directory,
                       label=label + "-show", env=env, timeout=10, offline=False).decode().strip()
    require(current and not re.search(r"[\s/]", current)
            and not re.search(r"cloud|offload|ssh|remote", current, re.IGNORECASE),
            "nonlocal/offloaded Docker context forbidden")
    context = decode(run_tool([executable, "context", "inspect", current], directory=directory,
                              label=label + "-inspect", env=env, timeout=10, offline=False))
    require(isinstance(context, list) and len(context) == 1, "Docker context metadata unavailable")
    endpoint = context[0]["Endpoints"]["docker"]["Host"]
    # DOCKER_CONTEXT overrides DOCKER_HOST. Neither is inherited by operations.
    selected = endpoint if env.get("DOCKER_CONTEXT") or not host else host
    validate_local_endpoint(selected)
    receipt = {"context": current, "context_endpoint": endpoint, "effective_endpoint": selected,
               "transport": "local-unix-socket", "offload_allowed": False,
               "environment_host_override": bool(host)}
    write_json(directory / (label + ".json"), receipt)
    return receipt


def docker(command, directory, label, *, timeout=600):
    boundary = _DOCKER_BOUNDARY or local_docker_boundary(directory, label + "-boundary")
    executable = shutil.which("docker")
    require(executable, "Docker CLI unavailable")
    env = {key: os.environ[key] for key in ("HOME", "PATH") if key in os.environ}
    return run_tool([executable, "--host", boundary["effective_endpoint"], *command], directory=directory, label=label,
                    env=env, timeout=timeout, offline=False,
                    monitor=not (command[:3] == ["buildx", "rm", "--force"]
                                 or command[:2] in (["rm", "-f"], ["network", "rm"], ["image", "rm"])))


def inspect(reference, directory, label):
    result = decode(docker(["image", "inspect", "--platform", "linux/amd64", reference], directory, label))
    require(isinstance(result, list) and len(result) == 1, "Docker image inspect failed")
    row = result[0]
    require((row.get("Os"), row.get("Architecture")) == ("linux", "amd64"),
            "local base/image platform mismatch")
    return row


def refresh_bases(rows, directory):
    references = {row[key] for row in rows for key in ("build_base", "runtime_base")}
    require(references in reference_sets(), "only one complete reviewed four-base policy may be refreshed")
    resolved = {}
    for index, reference in enumerate(sorted(references)):
        prefix = f"base-refresh-{index}"
        before = decode(docker(["image", "inspect", "--platform", "linux/amd64", reference], directory, prefix + "-before"))
        require(isinstance(before, list) and len(before) == 1, "cached base observation unavailable")
        pin = pinned_base(reference)
        if pin is not None:
            metadata = docker(["buildx", "imagetools", "inspect", pin.tag], directory,
                              prefix + "-tag-index", timeout=60)
            # Cached RepoDigests may still contain an old index after tag drift.
            tag_digests = re.findall(r"(?m)^Digest:\s+(sha256:[0-9a-f]{64})\s*$", metadata.decode())
            require(tag_digests == [pin.index_digest],
                    "reviewed base tag moved or registry digest missing; stop for qualification")
        docker(["pull", "--platform", "linux/amd64", reference], directory, prefix + "-pull", timeout=600)
        after = inspect(reference, directory, prefix + "-after")
        require(identity(after.get("Id")) and after.get("RepoDigests")
                and all(identity(value.rsplit("@", 1)[-1]) for value in after["RepoDigests"]),
                "refreshed public base identity unavailable")
        if pin is not None:
            require(after["Id"] in {pin.amd64_manifest_digest, pin.config_digest}
                    and pin.index_digest in {value.rsplit("@", 1)[-1] for value in after["RepoDigests"]},
                    "pinned base platform/config/index differs from reviewed identities")
        resolved[reference] = {"reference": reference, "platform": "linux/amd64",
                               "image_id": after["Id"], "repo_digests": after["RepoDigests"],
                               "rootfs": after["RootFS"]["Layers"],
                               "cached_before": {"image_id": before[0].get("Id"),
                                                 "repo_digests": before[0].get("RepoDigests"),
                                                 "architecture": before[0].get("Architecture")},
                               "resolution": "controlled public pull before isolated BuildKit; actual output layers checked"}
        if pin is not None:
            resolved[reference].update(tag_index_digest=tag_digests[0],
                                       amd64_manifest_digest=pin.amd64_manifest_digest,
                                       config_digest=pin.config_digest)
    write_json(directory / "base-refresh.json", resolved)
    return resolved


def pack_directory(source, output):
    with tarfile.open(output, "w") as archive:
        for path in sorted(source.rglob("*")):
            require(not path.is_symlink(), "unexpected generated/input symlink")
            if path.is_file():
                archive.add(path, arcname=str(path.relative_to(source)), recursive=False)


def startup(binding, directory, name, *, timeout=120, network="none", environment=(), list_path=None):
    """Exact assessed image, default USER/ENTRYPOINT, no schema-validation override."""
    created = False
    image_id = binding["docker_image_id"]
    outcome = {"image_id": binding["assessed_config_id"], "docker_image_id": image_id,
               "runtime_helper_sha": binding["runtime_helper_sha"], "runtime_identity_sha256": binding["runtime_identity_sha256"],
               "status": "incomplete", "default_user": True,
               "default_entrypoint": True, "schema_settings": "generated defaults",
               "timeout_seconds": timeout, "claim": "health/nonroot startup only; not business certification"}
    try:
        docker(["create", "--pull=never", "--name", name, "--platform", "linux/amd64", "--network", network,
                "--memory", "768m", "--cpus", "1", *environment, image_id], directory, "runtime-create")
        created = True
        state = decode(docker(["inspect", name], directory, "runtime-created-state", timeout=10))[0]
        verify_container_launch(state, binding)
        docker(["start", name], directory, "runtime-start", timeout=20)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = decode(docker(["inspect", name], directory, "runtime-state", timeout=10))[0]
            verify_container_launch(state, binding)
            require(state["State"].get("Running"), "representative application exited before healthy")
            if state["State"].get("Health", {}).get("Status") == "healthy":
                uid = docker(["exec", name, "id", "-u"], directory, "runtime-uid", timeout=10).strip()
                require(uid.isdigit() and uid != b"0", "actual runtime user is root")
                health = docker(["exec", name, "wget", "-qO-", "http://localhost:8080/actuator/health"],
                                directory, "runtime-health", timeout=10)
                require(decode(health).get("status") == "UP", "application health check did not pass")
                if list_path is not None:
                    require(list_path == "/api/v1/records", "undeclared CRUD list control")
                    response = docker(["exec", name, "wget", "-qO-", "http://localhost:8080" + list_path],
                                      directory, "runtime-crud-list", timeout=10)
                    require(isinstance(decode(response), list), "CRUD list GET did not return a JSON list")
                    outcome["readonly_crud_list"] = {"path": list_path, "status": "passed",
                                                    "response_sha256": digest(response)}
                outcome.update(status="passed", uid=uid.decode(), application_health="UP")
                break
            time.sleep(2)
        require(outcome["status"] == "passed", "representative runtime health deadline exceeded")
    except (ImageAssessmentError, OSError, ValueError, KeyError, TypeError) as exc:
        outcome["failure"] = str(exc) if isinstance(exc, ImageAssessmentError) else "runtime evidence invalid"
    finally:
        if created:
            try:
                docker(["logs", name], directory, "runtime-logs", timeout=10)
            finally:
                docker(["rm", "-f", name], directory, "runtime-remove-owned", timeout=20)
        write_json(directory / "runtime.json", outcome)
    return outcome


def verify_container_launch(state, binding):
    fields = ("User", "Entrypoint", "WorkingDir", "Healthcheck", "Cmd")
    require(state.get("Image") == binding["docker_image_id"]
            and config_semantics({key: state["Config"].get(key) for key in fields}) == binding["default_launch"],
            "created container image/default user/entrypoint/health config mismatch")


def run_runtime(row, bundle, directory, task, helper_sha):
    """Load only a verified owned export; never resolve a floating runtime tag."""
    started = utc_now()
    loaded = False
    outcome = {"status": "incomplete", "runtime_helper_sha": helper_sha}
    try:
        report = read_json(directory / STAGES[1] / "assessment.json")
        binding, manifest = runtime_export_binding(bundle, report)
        binding["runtime_helper_sha"] = helper_sha
        present = docker(["image", "ls", "--format", "{{json .}}", "--filter", "reference=" + binding["tag"]],
                         directory, "runtime-tag-before")
        require(not present.strip(), "task runtime tag already exists; do not overwrite another resource")
        docker(["image", "load", "--input", str(bundle / "image.tar")], directory, "runtime-load")
        loaded = True
        inspected = inspect(binding["tag"], directory, "runtime-image-inspect")
        require(file_digest(bundle / "image-config.json") == binding["assessed_config_id"].split(":")[1],
                "runtime config bytes changed before load inspection")
        validate_runtime_inspection(binding, inspected, read_json(bundle / "image-config.json"), manifest)
        binding["docker_image_id"] = inspected["Id"]
        binding["default_launch"] = config_semantics({key: inspected["Config"].get(key)
                                                     for key in ("User", "Entrypoint", "WorkingDir", "Healthcheck", "Cmd")})
        (directory / "runtime-manifest.json").write_bytes(manifest)
        binding["inspection_sha256"] = file_digest(directory / "runtime-image-inspect.stdout")
        write_json(directory / "runtime-identity.json", binding)
        binding["runtime_identity_sha256"] = file_digest(directory / "runtime-identity.json")
        outcome = representative_startup(row, binding, directory, task)
    except (ImageAssessmentError, OSError, ValueError, KeyError, TypeError, tarfile.TarError) as exc:
        outcome["failure"] = str(exc) if isinstance(exc, ImageAssessmentError) else "runtime image binding unavailable"
    finally:
        if loaded:
            try:
                docker(["image", "rm", binding["tag"]], directory, "runtime-remove-owned-tag", timeout=30)
            except ImageAssessmentError:
                outcome.update(status="incomplete", failure="owned runtime tag cleanup failed; no retry")
        outcome.update(started_at_utc=started, ended_at_utc=utc_now())
        write_json(directory / "runtime.json", outcome)
    return outcome


def build_case(row, destination, *, sha, baseline, task, resolved_bases, collector_sha=None):
    destination.mkdir()
    work = destination / "generation-work"
    work.mkdir()
    manifest = prepare_case_input(work, row["shape"], row["fixture"])
    raw = yaml.safe_load(manifest.read_text())
    raw["target_profile"] = row["profile"]
    manifest.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    project = destination / "generated-app"
    generated = generate_application(build_metadata_project(manifest), project,
                                     source_manifest=str(manifest), generation_run_id=f"image-{task}-{row['case']}")
    require(generated.harness_report is None or generated.harness_report.passed,
            "generated application harness failed")
    if row["case"] == "crud-h2-j17":
        controllers = [path.read_text() for path in project.rglob("*Controller.java")]
        require(any('@RequestMapping("/api/v1/records")' in source and " listAll(" in source
                    for source in controllers), "known read-only CRUD list route missing from generated source")
    recipe = (project / "Dockerfile").read_text()
    jar_paths = re.findall(r"COPY --from=build --chown=edgeforge:edgeforge (\S+\.jar) app.jar", recipe)
    require(len(jar_paths) == 1 and "RUN mvn -q -DskipTests clean package" in recipe,
            "generated recipe does not match approved structure")
    bases = []
    for reference in (row["build_base"], row["runtime_base"]):
        require(reference in recipe, "declared base differs from actual recipe")
        bases.append(resolved_bases[reference])
    write_json(destination / "base-images.json", bases)
    write_json(destination / "generation.json", {"generation_run_id": f"image-{task}-{row['case']}",
                                                "warnings": generated.warnings, "profile": row["profile"]})
    pack_directory(manifest.parent, destination / "input.tar")
    pack_directory(project, destination / "source.tar")
    receipt = read_json(baseline / row["case"] / "assessment-receipt.json")
    representative = receipt.get("representative_case", row["case"])
    inventory = baseline / representative / "assessment" / "inventory.json"
    require(inventory.is_file(), "retained historical resolved inventory unavailable")
    jars = {}
    for stage, base in zip(STAGES, bases, strict=True):
        bundle = destination / (stage + "-bundle")
        bundle.mkdir()
        tag = f"edgeforge-image-proof-{task}:{row['case']}-{'build' if stage == STAGES[0] else 'final'}"
        command = ["buildx", "build", "--builder", task, "--platform", "linux/amd64", "--pull=false",
                   "--tag", tag, "--iidfile", str(bundle / "build.iid"),
                   "--metadata-file", str(bundle / "build-metadata.json"),
                   "--output", f"type=docker,dest={bundle / 'image.tar'}"]
        if stage == STAGES[0]:
            command.extend(["--target", "build"])
        docker([*command, str(project)], bundle, "image-build", timeout=1200)
        for name in ("base-images.json", "generation.json", "input.tar", "source.tar"):
            shutil.copyfile(destination / name, bundle / name)
        shutil.copyfile(project / "Dockerfile", bundle / "Dockerfile")
        shutil.copyfile(baseline / row["case"] / "dependency-policy.json", bundle / "dependency-policy.json")
        shutil.copyfile(inventory, bundle / "resolved-inventory.json")
        shutil.copyfile(baseline / representative / "assessment/bom.json", bundle / "retained-maven-bom.json")
        jar_path = jar_paths[0] if stage == STAGES[0] else "/app/app.jar"
        actual, _ = image_archive(bundle / "image.tar", jar_path=jar_path, stage=stage, identity_output=bundle)
        metadata = read_json(bundle / "build-metadata.json")
        require(metadata.get("containerimage.config.digest") == actual["image_id"],
                "exported image identity differs from build metadata")
        (bundle / "image.iid").write_text(actual["image_id"] + "\n", encoding="utf-8")
        require(actual["rootfs"][:len(base["rootfs"])] == base["rootfs"],
                "actual image does not use declared resolved base layers")
        jars[stage] = actual["jar_sha256"]
        provenance = {"generator_sha": sha, "collector_sha": collector_sha or sha,
                      "case": row["case"], "profile": row["profile"],
                      "stage": stage, "jar_path": jar_path,
                      "historical_resolved_inventory_case": representative,
                      "files": {name: file_digest(bundle / name) for name in (
                          "Dockerfile", "source.tar", "input.tar", "generation.json", "resolved-inventory.json",
                          "dependency-policy.json", "image.tar", "base-images.json",
                          "image-config.json", "image-manifest.json", "retained-maven-bom.json")}}
        write_json(bundle / "provenance.json", provenance)
    require(jars[STAGES[0]] == jars[STAGES[1]], "final/build Boot JAR differs; do not share inventories")
    for label, base in zip(("build", "runtime"), bases, strict=True):
        require(inspect(base["reference"], destination, f"{label}-base-after")["Id"] == base["image_id"],
                "floating base changed during build")


def resource_check(output, *, between_cases=False, extra_output=None, pending_bytes=0, free_only=False):
    floor = (26 if between_cases else 20) * 1024**3
    require(shutil.disk_usage(output).free >= floor,
            "disk safety floor reached; stop without pruning other resources")
    if free_only:
        return
    evidence, representatives = pending_bytes, 0
    roots = [output] + ([extra_output] if extra_output is not None and extra_output.exists() else [])
    def traversal_error(exc):
        raise exc

    for root in roots:
        for directory, children, filenames in os.walk(root, topdown=True, onerror=traversal_error, followlinks=False):
            children[:] = [name for name in children if name != "scan-scratch"]
            require(all(not (Path(directory) / name).is_symlink() for name in children), "unexpected evidence symlink")
            for name in filenames:
                if name == "image.tar":
                    continue
                path = Path(directory) / name
                require(not path.is_symlink(), "unexpected evidence symlink")
                details = path.stat()
                if not stat.S_ISREG(details.st_mode):
                    continue
                if name == "image.tar.gz":
                    representatives += details.st_size
                else:
                    evidence += details.st_size
    require(evidence <= 2 * 1024**3 and representatives <= 1024**3
            and evidence + representatives <= 3 * 1024**3,
            "persistent evidence exceeds 3 GiB budget (2 GiB reports/source, 1 GiB representatives)")


def compact_reports(directory, report, *, remove=True):
    records = report["retained_raw"]
    for record in records:
        raw = directory / record["file"]
        packed = directory / (record["file"] + ".gz")
        require(raw.is_file() and not raw.is_symlink() and file_digest(raw) == record["sha256"]
                and file_digest(packed) == record["gzip_sha256"], "report changed before lossless compaction")
        verify_gzip(packed, record["sha256"], record["bytes"])
    assessment = directory / "assessment.json"
    with assessment.open("rb") as source, (directory / "assessment.json.gz").open("wb") as stream:
        with gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as packed:
            shutil.copyfileobj(source, packed)
    verify_gzip(directory / "assessment.json.gz", file_digest(assessment), assessment.stat().st_size)
    receipt = {"status": "verified-compressed", "assessment_sha256": file_digest(assessment),
               "records": records, "removed_originals": [record["file"] for record in records]}
    if not remove:
        return receipt
    remove_report_originals(directory, receipt)
    return receipt


def remove_report_originals(directory, receipt):
    for record in receipt["records"]:
        require(file_digest(directory / record["file"]) == record["sha256"], "report changed before owned deletion")
        verify_gzip(directory / (record["file"] + ".gz"), record["sha256"], record["bytes"])
    write_json(directory / "report-retention.json", receipt)
    for record in receipt["records"]:
        (directory / record["file"]).unlink()
    scratch = directory / "scan-scratch"
    if scratch.exists():
        require(scratch.is_dir() and not scratch.is_symlink(), "unsafe task scan scratch")
        shutil.rmtree(scratch)


def finalize_case(destination, row, sha, *, runtime_helper_sha=None, assessment_helper_sha=None):
    from scripts.publish_generated_image_evidence import validate_runtime, validate_stage

    # All validation happens before any export/report removal. Failures retain raw bytes.
    validated = {}
    for stage in STAGES:
        report, data, _ = validate_stage(destination.parent, row, stage, sha, check_retention=False,
                                         assessment_helper_sha=assessment_helper_sha if stage == STAGES[1] else None)
        validated[stage] = (report, data)
    build, final = (validated[stage] for stage in STAGES)
    require(build[0]["image"]["jar_sha256"] == final[0]["image"]["jar_sha256"]
            and build[1]["packaged.json"] == final[1]["packaged.json"]
            and build[0]["tools"] == final[0]["tools"] and build[1]["databases.json"] == final[1]["databases.json"]
            and all(build[1]["provenance.json"]["files"][name] == final[1]["provenance.json"]["files"][name]
                    for name in ("Dockerfile", "source.tar", "input.tar", "generation.json", "resolved-inventory.json",
                                 "dependency-policy.json", "base-images.json", "retained-maven-bom.json")),
            "case source, packaged inventory, tools or databases differ between stages")
    if row["case"] in RUNTIME_CASES:
        validate_runtime(destination.parent, row["case"], runtime_helper_sha or sha)
    prepared = []
    for stage in STAGES:
        report = validated[stage][0]
        bundle = destination / (stage + "-bundle")
        source = bundle / "image.tar"
        target = bundle / "image.tar.gz"
        checksum = file_digest(source)
        size = source.stat().st_size
        require(size <= ARCHIVE_LIMIT and checksum == validated[stage][1]["provenance.json"]["files"]["image.tar"],
                "export changed or exceeds bounded archive size")
        retain = row["case"] in RUNTIME_CASES and stage == STAGES[1]
        receipt = {"schema_version": 2, "case": row["case"], "stage": stage, "generator_sha": sha,
                   "image_id": report["image"]["image_id"], "platform": "linux/amd64",
                   "image_tar_sha256": checksum, "image_tar_bytes": size, "retained": retain,
                   "assessment_sha256": evidence_digest(destination / stage / "assessment.json"),
                   "validation": "complete", "assessment_exit_code": report["exit_code"],
                   "cleanup": {"status": "pending", "verified_export_sha256": checksum, "verified_export_bytes": size},
                   "replay": "exact saved-image replay" if retain else "not retained; no exact image replay or rescan"}
        if retain:
            require(not target.exists(), "representative export target exists")
            with source.open("rb") as raw, target.open("wb") as stream:
                with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as packed:
                    for block in iter(lambda: raw.read(1024 * 1024), b""):
                        assessment_tools.check_storage()
                        packed.write(block)
            verify_gzip(target, checksum, size, limit=ARCHIVE_LIMIT)
            receipt["image_tar_gz_sha256"] = file_digest(target)
        report_receipt = compact_reports(destination / stage, report, remove=False)
        prepared.append((stage, bundle, source, checksum, receipt, report_receipt))
    assessment_tools.check_storage()
    for _stage, _bundle, source, checksum, _receipt, _report_receipt in prepared:
        require(file_digest(source) == checksum, "export changed before owned deletion")
    for stage, bundle, source, _checksum, receipt, report_receipt in prepared:
        remove_report_originals(destination / stage, report_receipt)
        write_json(bundle / "image-retention.json", receipt)
        source.unlink()
        receipt["cleanup"]["status"] = "removed"
        write_json(bundle / "image-retention.json", receipt)


def representative_startup(row, binding, directory, task):
    name = f"edgeforge-image-proof-{task}-{row['case']}"
    if not row["shape"].startswith("kafka"):
        return startup(binding, directory, name,
                       list_path="/api/v1/records" if row["case"] == "crud-h2-j17" else None)
    network, broker = name + "-net", name + "-broker"
    network_created = broker_created = False
    try:
        inspect("apache/kafka:4.2.1", directory, "runtime-broker-image")
        docker(["network", "create", "--internal", network], directory, "runtime-network-create")
        network_created = True
        docker(["create", "--pull=never", "--name", broker, "--platform", "linux/amd64", "--network", network,
                "--network-alias", "broker", "--memory", "1g", "--cpus", "1",
                "-e", "KAFKA_NODE_ID=1", "-e", "KAFKA_PROCESS_ROLES=broker,controller",
                "-e", "KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093",
                "-e", "KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://broker:9092",
                "-e", "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
                "-e", "KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER",
                "-e", "KAFKA_CONTROLLER_QUORUM_VOTERS=1@broker:9093",
                "-e", "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1",
                "-e", "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1",
                "-e", "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1", "apache/kafka:4.2.1"],
               directory, "runtime-broker-create")
        broker_created = True
        docker(["start", broker], directory, "runtime-broker-start")
        # Application startup itself has the finite broker/health readiness window.
        return startup(binding, directory, name, timeout=180, network=network,
                       environment=("-e", "SPRING_KAFKA_BOOTSTRAP_SERVERS=broker:9092"))
    finally:
        if broker_created:
            try:
                docker(["logs", broker], directory, "runtime-broker-logs", timeout=10)
            finally:
                docker(["rm", "-f", broker], directory, "runtime-broker-remove", timeout=20)
        if network_created:
            docker(["network", "rm", network], directory, "runtime-network-remove", timeout=20)


def copy_first_case(prior, output, row, authorized, tool_setup):
    """The sole approved reuse: two complete b7 scans, not a general registry."""
    from scripts.publish_generated_image_evidence import STAGE_JSON, validate_stage

    prior_hash = file_digest(prior / "campaign.json")
    receipt = read_json(prior / "campaign.json")
    require(authorized.get("continuation_approved") is True and authorized.get("reuse_case") == REUSE_CASE
            and authorized.get("reuse_generator_sha") == REUSE_SHA
            and authorized.get("prior_campaign_sha256") == prior_hash
            and authorized.get("runtime_helper_sha") == authorized["generator_sha"], "explicit first-case continuation approval missing")
    require(receipt.get("generator_sha") == receipt.get("collector_sha") == REUSE_SHA
            and receipt.get("coverage_sha256") == authorized["coverage_sha256"]
            and receipt.get("status") == "incomplete" and receipt.get("exit_code") == 2 and receipt.get("campaign_complete") is False
            and receipt.get("cases") == [{"case": REUSE_CASE, "stages": {stage: 1 for stage in STAGES}}],
            "only the preserved two-scan first-case runtime failure may continue")
    current_db = db_receipt(tool_setup / "grype-db", tool_setup / "trivy-cache")
    source = prior / REUSE_CASE
    old_runtime = read_json(source / "runtime.json")
    require(old_runtime.get("status") == "incomplete", "prior runtime failure must remain unchanged")
    validated = []
    for stage in STAGES:
        report, data, _ = validate_stage(prior, row, stage, REUSE_SHA, check_retention=False)
        require(report["exit_code"] == receipt["cases"][0]["stages"][stage]
                and not (source / (stage + "-bundle") / "image-retention.json").exists(),
                "prior stage is not the unchanged completed pre-retention observation")
        actual, _ = image_archive(source / (stage + "-bundle") / "image.tar",
                                  jar_path=data["provenance.json"]["jar_path"], stage=stage)
        require(actual == report["image"] and data["databases.json"] == current_db
                and report["tools"] == read_json(tool_setup / "verified/tools.json"),
                "reused image/tool/DB snapshot differs from preserved validated scans")
        validated.append((report, data))
    require(validated[0][0]["image"]["jar_sha256"] == validated[1][0]["image"]["jar_sha256"]
            and validated[0][1]["packaged.json"] == validated[1][1]["packaged.json"], "reused build/final application differs")
    destination = output / REUSE_CASE
    destination.mkdir()
    records = []

    def copy(path, relative):
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= ARCHIVE_LIMIT, "unsafe reused evidence file")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        checksum = file_digest(path)
        with path.open("rb") as raw, target.open("xb") as saved:
            for block in iter(lambda: raw.read(1024 * 1024), b""):
                assessment_tools.check_storage()
                saved.write(block)
        require(file_digest(target) == checksum == file_digest(path), "reused evidence changed while copying")
        records.append({"file": str(relative), "sha256": checksum, "bytes": target.stat().st_size})

    for stage, (report, _) in zip(STAGES, validated, strict=True):
        names = {"assessment.json", *STAGE_JSON}
        if (source / stage / "summary.txt").exists():
            names.add("summary.txt")
        names |= {entry["file"] for entry in report["retained_raw"]}
        names |= {entry["file"] + ".gz" for entry in report["retained_raw"]}
        for name in sorted(names):
            copy(source / stage / name, Path(stage) / name)
        bundle_name = stage + "-bundle"
        for path in sorted((source / bundle_name).iterdir()):
            require(path.is_file(), "unexpected directory in retained image bundle")
            copy(path, Path(bundle_name) / path.name)
    for path in sorted(source.glob("runtime*")):
        copy(path, Path("prior-runtime") / path.name)
    shutil.copyfile(prior / "campaign.json", output / "prior-campaign.json")
    require(file_digest(output / "prior-campaign.json") == prior_hash, "prior campaign changed while copying")
    reuse = {"generator_sha": REUSE_SHA, "collector_sha": REUSE_SHA, "runtime_helper_sha": authorized["generator_sha"],
             "prior_campaign_sha256": prior_hash, "prior_runtime_sha256": file_digest(source / "runtime.json"),
             "source_root": str(prior), "files": sorted(records, key=lambda entry: entry["file"])}
    write_json(destination / "reuse.json", reuse)
    return {"case": REUSE_CASE, "generator_sha": REUSE_SHA, "collector_sha": REUSE_SHA,
            "runtime_helper_sha": authorized["generator_sha"], "prior_campaign_sha256": prior_hash,
            "reuse_sha256": file_digest(destination / "reuse.json")}


def copy_completed_first_case(prior, output, row, authorized, tool_setup):
    """Preserve the one finalized 4f runtime case; never scan or finalize it again."""
    from scripts.publish_generated_image_evidence import (
        validate_capacity_continuation,
        validate_completed_capacity_case,
    )

    prior_hash = file_digest(prior / "campaign.json")
    receipt = read_json(prior / "campaign.json")
    require(authorized.get("capacity_continuation_approved") is True
            and authorized.get("continuation_approved") is not True
            and authorized.get("reuse_case") == REUSE_CASE
            and authorized.get("reuse_generator_sha") == authorized.get("reuse_collector_sha") == REUSE_SHA
            and authorized.get("reuse_runtime_helper_sha") == CAPACITY_RUNTIME_SHA
            and authorized.get("prior_campaign_sha256") == prior_hash
            and authorized.get("generator_sha") == authorized.get("collector_sha") == authorized.get("runtime_helper_sha")
            and receipt.get("coverage_sha256") == authorized["coverage_sha256"], "explicit completed capacity-case approval missing")
    validate_completed_capacity_case(prior, receipt, row, tools=read_json(tool_setup / "verified/tools.json"),
                                     databases=db_receipt(tool_setup / "grype-db", tool_setup / "trivy-cache"))
    source = prior / REUSE_CASE
    paths = sorted(source.rglob("*"))
    require(all(not path.is_symlink() and (path.is_file() or path.is_dir()) for path in paths)
            and not (source / "completed-case-copy.json").exists(), "unsafe or already continued capacity case")
    files = [path for path in paths if path.is_file()]
    require(0 < len(files) < 1000 and sum(path.stat().st_size for path in files) <= 3 * 1024**3,
            "completed capacity case exceeds retention bound")
    records = []

    def copy(path, target):
        require(path.is_file() and not path.is_symlink() and path.stat().st_size <= ARCHIVE_LIMIT, "unsafe capacity evidence file")
        checksum, size = file_digest(path), path.stat().st_size
        target.parent.mkdir(parents=True, exist_ok=True)
        with path.open("rb") as raw, target.open("xb") as saved:
            for block in iter(lambda: raw.read(1024 * 1024), b""):
                assessment_tools.check_storage()
                saved.write(block)
        require(file_digest(target) == checksum == file_digest(path) and target.stat().st_size == size == path.stat().st_size,
                "completed capacity evidence changed while copying")
        return {"sha256": checksum, "bytes": size}

    for path in files:
        relative = path.relative_to(source)
        records.append({"file": str(relative), **copy(path, output / REUSE_CASE / relative)})
    copy(prior / "prior-campaign.json", output / "prior-campaign.json")
    require(copy(prior / "campaign.json", output / "capacity-prior-campaign.json")["sha256"] == prior_hash,
            "capacity parent changed while copying")
    write_json(output / REUSE_CASE / "completed-case-copy.json", {"prior_campaign_sha256": prior_hash, "files": records})
    lineage = {"case": REUSE_CASE, "generator_sha": REUSE_SHA, "collector_sha": REUSE_SHA,
               "runtime_helper_sha": CAPACITY_RUNTIME_SHA, "prior_campaign_sha256": prior_hash,
               "copy_manifest_sha256": file_digest(output / REUSE_CASE / "completed-case-copy.json")}
    now = utc_now()
    validate_capacity_continuation(output, {"continuation": receipt["continuation"], "capacity_continuation": lineage,
                                          "coverage_sha256": authorized["coverage_sha256"],
                                          "started_at_utc": now, "ended_at_utc": now}, row)
    return receipt["continuation"], lineage


def copy_kafka_cohort(prior, output, declared, authorized, tool_setup):
    from scripts.publish_generated_image_evidence import (
        validate_kafka_continuation,
        validate_kafka_prior,
    )

    prior_hash = file_digest(prior / "campaign.json")
    receipt = read_json(prior / "campaign.json")
    require(authorized.get("kafka_continuation_approved") is True
            and not authorized.get("capacity_continuation_approved") and not authorized.get("continuation_approved")
            and authorized.get("prior_campaign_sha256") == prior_hash
            and authorized.get("reuse_cases") == kafka_reuse_bindings()
            and authorized.get("generator_sha") == authorized.get("collector_sha") == authorized.get("runtime_helper_sha")
            and receipt.get("coverage_sha256") == authorized["coverage_sha256"], "explicit nine-case Kafka continuation approval missing")
    validate_kafka_prior(prior, receipt, declared, tools=read_json(tool_setup / "verified/tools.json"),
                         databases=db_receipt(tool_setup / "grype-db", tool_setup / "trivy-cache"))
    sources = []
    for case in KAFKA_REUSE_CASES:
        paths = sorted((prior / case).rglob("*"))
        require(all(not path.is_symlink() and (path.is_file() or path.is_dir()) for path in paths), "unsafe finalized Kafka cohort case")
        sources.extend((path, path.relative_to(prior)) for path in paths if path.is_file())
    failed = prior / "kafka-h2-j17" / STAGES[0]
    sources.extend((path, Path("prior-kafka-failure") / STAGES[0] / path.name) for path in sorted(failed.iterdir()) if path.is_file())
    sources.extend((prior / name, Path(name)) for name in ("prior-campaign.json", "capacity-prior-campaign.json"))
    sources.append((prior / "campaign.json", Path("kafka-prior-campaign.json")))
    require(0 < len(sources) < 10000 and all(path.is_file() and not path.is_symlink() for path, _ in sources)
            and sum(path.stat().st_size for path, _ in sources) <= 3 * 1024**3, "Kafka cohort copy exceeds bounded safe retention")
    records = []
    for path, relative in sources:
        checksum, size = file_digest(path), path.stat().st_size
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with path.open("rb") as raw, target.open("xb") as saved:
            for block in iter(lambda: raw.read(1024 * 1024), b""):
                assessment_tools.check_storage()
                saved.write(block)
        require(file_digest(target) == checksum == file_digest(path) and target.stat().st_size == size == path.stat().st_size,
                "Kafka cohort changed while copying")
        records.append({"file": str(relative), "sha256": checksum, "bytes": size})
    require(file_digest(output / "kafka-prior-campaign.json") == prior_hash, "Kafka parent changed while copying")
    write_json(output / "kafka-cohort-copy.json", {"prior_campaign_sha256": prior_hash, "files": records})
    lineage = {"prior_campaign_sha256": prior_hash, "reuse_cases": kafka_reuse_bindings(),
               "copy_manifest_sha256": file_digest(output / "kafka-cohort-copy.json")}
    now = utc_now()
    summary = {key: receipt[key] for key in ("continuation", "capacity_continuation", "coverage_sha256")}
    summary.update(kafka_continuation=lineage, started_at_utc=now, ended_at_utc=now)
    validate_kafka_continuation(output, summary, declared)
    return receipt, lineage


def copy_storage_cohort(prior, prior_manifest, output, declared, authorized, tool_setup):
    from scripts.publish_generated_image_evidence import (
        validate_storage_continuation,
        validate_storage_prior,
        verify_storage_manifest,
    )

    prior_hash = file_digest(prior / "campaign.json")
    receipt = read_json(prior / "campaign.json")
    require(authorized.get("storage_continuation_approved") is True
            and not any(authorized.get(key) for key in ("continuation_approved", "capacity_continuation_approved", "kafka_continuation_approved"))
            and authorized.get("reuse_stages") == storage_reuse_bindings()
            and authorized.get("prior_campaign_sha256") == prior_hash
            and authorized.get("generator_sha") == authorized.get("collector_sha") == authorized.get("runtime_helper_sha")
            and receipt.get("coverage_sha256") == authorized["coverage_sha256"], "explicit 23-stage storage continuation approval missing")
    original = verify_storage_manifest(prior, prior_manifest, authorized.get("prior_manifest_sha256"))
    failure = validate_storage_prior(prior, receipt, declared, tools=read_json(tool_setup / "verified/tools.json"),
                                     databases=db_receipt(tool_setup / "grype-db", tool_setup / "trivy-cache"))
    roots = {*STORAGE_PAIR_CASES, STORAGE_PARTIAL_CASE, "prior-kafka-failure"}
    root_files = {"prior-campaign.json", "capacity-prior-campaign.json", "kafka-prior-campaign.json", "kafka-cohort-copy.json", "campaign.json"}
    records = []
    for name, entry in sorted(original.items()):
        parts = Path(name).parts
        if "scan-scratch" in parts or not (parts[0] in roots or name in root_files):
            continue
        relative = "storage-prior-campaign.json" if name == "campaign.json" else (
            "prior-storage-failure/" + name.removeprefix(f"{STORAGE_PARTIAL_CASE}/{STAGES[1]}/")
            if name.startswith(f"{STORAGE_PARTIAL_CASE}/{STAGES[1]}/") else name)
        source, target = prior / name, output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as raw, target.open("xb") as saved:
            for block in iter(lambda: raw.read(1024 * 1024), b""):
                assessment_tools.check_storage()
                saved.write(block)
        require(file_digest(target) == entry["sha256"] == file_digest(source)
                and target.stat().st_size == entry["bytes"] == source.stat().st_size, "storage preserved evidence changed while copying")
        records.append({"file": relative, **entry})
    shutil.copyfile(prior_manifest, output / "storage-prior-files.sha256")
    require(file_digest(output / "storage-prior-files.sha256") == authorized["prior_manifest_sha256"], "storage prior manifest changed while copying")
    write_json(output / "storage-copy.json", {"prior_campaign_sha256": prior_hash, "prior_root": str(prior), "files": records})
    write_json(output / "storage-failure-observation.json", failure)
    lineage = {"prior_campaign_sha256": prior_hash, "prior_manifest_sha256": authorized["prior_manifest_sha256"],
               "reuse_stages": storage_reuse_bindings(), "copy_manifest_sha256": file_digest(output / "storage-copy.json")}
    now = utc_now()
    summary = {key: receipt[key] for key in ("continuation", "capacity_continuation", "kafka_continuation", "coverage_sha256")}
    summary.update(storage_continuation=lineage, started_at_utc=now, ended_at_utc=now)
    validate_storage_continuation(output, summary, declared, finalized=False)
    return receipt, lineage


def campaign(output, *, declaration, approval, tool_setup, baseline, cases=None, prior_campaign=None,
             capacity_continuation=False, kafka_continuation=False, storage_continuation=False, prior_manifest=None):
    global _DOCKER_BOUNDARY
    declared = read_json(declaration)
    make_plan(declared)
    authorized = read_json(approval)
    sha = authorized.get("generator_sha")
    collector_sha = authorized.get("collector_sha", sha)
    check_freeze(authorized, declaration, sha)
    require(prior_campaign is not None or (authorized.get("continuation_approved") is not True
                                         and authorized.get("capacity_continuation_approved") is not True
                                         and authorized.get("kafka_continuation_approved") is not True
                                         and authorized.get("storage_continuation_approved") is not True),
            "continuation approval cannot start a replacement full rescan")
    require(not capacity_continuation or (prior_campaign is not None and authorized.get("capacity_continuation_approved") is True),
            "capacity continuation requires explicit approval and prior campaign")
    require(capacity_continuation or authorized.get("capacity_continuation_approved") is not True,
            "completed capacity case requires continue-capacity, not a repeated runtime")
    require(not kafka_continuation or (prior_campaign is not None and not capacity_continuation
                                      and authorized.get("kafka_continuation_approved") is True),
            "Kafka continuation requires explicit approval and prior campaign")
    require(kafka_continuation or authorized.get("kafka_continuation_approved") is not True,
            "nine-case cohort requires continue-kafka, not repeated completed cases")
    require(not storage_continuation or (prior_campaign is not None and prior_manifest is not None
                                        and not capacity_continuation and not kafka_continuation
                                        and authorized.get("storage_continuation_approved") is True),
            "23-stage continuation requires its explicit approval and original manifest")
    require(storage_continuation or (prior_manifest is None and authorized.get("storage_continuation_approved") is not True),
            "23-stage cohort requires continue-storage, not repeated completed cases")
    require(prior_campaign is None or not cases, "bounded continuation must cover all 30 cases, reusing only the first")
    require(not output.exists(), "campaign already exists; affected-only repair requires separate output")
    resource_check(output.parent, between_cases=True, free_only=True)
    output.mkdir(parents=True)
    task = f"ef-image-{sha[:8]}-{os.getpid()}"
    builder_created = False
    previous_boundary = _DOCKER_BOUNDARY
    previous_guard = assessment_tools.STORAGE_GUARD
    summary = {"generator_sha": sha, "collector_sha": collector_sha, "runtime_helper_sha": sha,
               "generator_sha_semantics": "campaign freeze; actual generators are recorded per case",
               "status": "incomplete", "exit_code": 2, "cases": [],
               "started_at_utc": utc_now(),
               "coverage_sha256": file_digest(declaration), "equivalence_claim": False,
               "declared_cases": 30, "campaign_complete": False,
               "storage_policy": {"persistent_limit_bytes": 3 * 1024**3, "report_source_limit_bytes": 2 * 1024**3,
                                  "representative_limit_bytes": 1024**3, "free_space_floor_bytes": 20 * 1024**3,
                                  "working_reservation_bytes": 6 * 1024**3, "working_peak_guaranteed": False,
                                  "cache": "unique owned builder per case; cached within pair only; no global prune"},
               **base_policy_status(declared["cases"])}
    try:
        db_receipt(tool_setup / "grype-db", tool_setup / "trivy-cache")
        available = {row["case"] for row in declared["cases"]}
        require(not cases or set(cases) <= available, "affected-only repair includes undeclared cases")
        resource_check(output, between_cases=True)
        assessment_tools.STORAGE_GUARD = lambda: resource_check(output)
        _DOCKER_BOUNDARY = local_docker_boundary(output)
        summary["docker_boundary"] = _DOCKER_BOUNDARY
        docker(["version", "--format", "{{json .}}"], output, "docker-version")
        docker(["info", "--format", "{{json .}}"], output, "docker-info")
        reused = set()
        if storage_continuation:
            prior, summary["storage_continuation"] = copy_storage_cohort(prior_campaign, prior_manifest, output, declared, authorized, tool_setup)
            summary.update({key: prior[key] for key in ("continuation", "capacity_continuation", "kafka_continuation")})
            for observation in prior["cases"][:11]:
                source = observation["generator_sha"]
                summary["cases"].append({**observation, "scans_reused": True, "runtime_reused": observation["runtime_helper_sha"] is not None,
                                         "assessment_helper_shas": {stage: source for stage in STAGES}})
            row = next(row for row in declared["cases"] if row["case"] == STORAGE_PARTIAL_CASE)
            observation = {"case": STORAGE_PARTIAL_CASE, "generator_sha": STORAGE_PRIOR_SHA, "collector_sha": STORAGE_PRIOR_SHA,
                           "runtime_helper_sha": None, "stages": {STAGES[0]: 1},
                           "assessment_helper_shas": {STAGES[0]: STORAGE_PRIOR_SHA, STAGES[1]: sha}}
            summary["cases"].append(observation)
            destination = output / STORAGE_PARTIAL_CASE
            print(f"{utc_now()} Preserved 23 assessments and both startups; assessing saved final export only", flush=True)
            code = collect(destination / (STAGES[1] + "-bundle"), destination / STAGES[1], case=STORAGE_PARTIAL_CASE, stage=STAGES[1],
                           declaration=declaration, approval=approval, tools=tool_setup / "archives", grype_db=tool_setup / "grype-db",
                           trivy_cache=tool_setup / "trivy-cache", storage_continuation=True)
            observation["stages"][STAGES[1]] = code
            require(code in (0, 1), "saved final assessment incomplete; stop without retry")
            transformed_at = utc_now()
            finalize_case(destination, row, STORAGE_PRIOR_SHA, assessment_helper_sha=sha)
            write_json(output / "storage-partial-transformation.json", {
                "copy_manifest_sha256": summary["storage_continuation"]["copy_manifest_sha256"],
                "assessment_sha256": file_digest(destination / STAGES[0] / "assessment.json"),
                "report_retention_sha256": file_digest(destination / STAGES[0] / "report-retention.json"),
                "image_retention_sha256": file_digest(destination / (STAGES[0] + "-bundle") / "image-retention.json"),
                "final_image_retention_sha256": file_digest(destination / (STAGES[1] + "-bundle") / "image-retention.json"),
                "assessment_helper_sha": sha, "started_at_utc": transformed_at, "ended_at_utc": utc_now()})
            reused.update((*STORAGE_PAIR_CASES, STORAGE_PARTIAL_CASE))
            resource_check(output, between_cases=True)
        elif kafka_continuation:
            prior, summary["kafka_continuation"] = copy_kafka_cohort(prior_campaign, output, declared, authorized, tool_setup)
            summary.update({key: prior[key] for key in ("continuation", "capacity_continuation")})
            for observation in prior["cases"][:9]:
                summary["cases"].append({**observation, "scans_reused": True,
                                         "runtime_reused": observation["runtime_helper_sha"] is not None})
            reused.update(KAFKA_REUSE_CASES)
            print(f"{utc_now()} Preserved nine complete pairs and both runtime proofs unchanged; 21 cases remain", flush=True)
            resource_check(output, between_cases=True)
        elif prior_campaign is not None:
            reused.add(REUSE_CASE)
            row = next(row for row in declared["cases"] if row["case"] == REUSE_CASE)
            if capacity_continuation:
                summary["continuation"], summary["capacity_continuation"] = copy_completed_first_case(
                    prior_campaign, output, row, authorized, tool_setup)
            else:
                summary["continuation"] = copy_first_case(prior_campaign, output, row, authorized, tool_setup)
            destination = output / REUSE_CASE
            summary["cases"].append({"case": REUSE_CASE, "generator_sha": REUSE_SHA, "collector_sha": REUSE_SHA,
                                     "stages": {stage: 1 for stage in STAGES}, "scans_reused": True,
                                     "runtime_helper_sha": CAPACITY_RUNTIME_SHA if capacity_continuation else sha})
            if capacity_continuation:
                summary["cases"][-1]["runtime_reused"] = True
                print(f"{utc_now()} Reused completed first case: original b7 scans and 4f runtime unchanged", flush=True)
            else:
                print(f"{utc_now()} Reused two validated {REUSE_SHA[:8]} scans; proving exact saved runtime", flush=True)
                runtime = run_runtime(row, destination / (STAGES[1] + "-bundle"), destination, task, sha)
                require(runtime["status"] == "passed", "continued first-case runtime incomplete; stop without retry")
                finalize_case(destination, row, REUSE_SHA, runtime_helper_sha=sha)
            resource_check(output, between_cases=True)
        resolved_bases = refresh_bases(declared["cases"], output)
        for row in declared["cases"]:
            if row["case"] in reused:
                continue
            if cases and row["case"] not in cases:
                continue
            destination = output / row["case"]
            print(f"{utc_now()} Building {row['case']} (both actual stages)", flush=True)
            resource_check(output, between_cases=True)
            builder = task + "-" + row["case"]
            docker(["buildx", "create", "--name", builder, "--driver", "docker-container",
                    "--driver-opt", "memory=4g", _DOCKER_BOUNDARY["effective_endpoint"]],
                   output, "builder-create-" + row["case"], timeout=120)
            builder_created = True
            build_case(row, destination, sha=sha, baseline=baseline, task=builder,
                       resolved_bases=resolved_bases, collector_sha=collector_sha)
            observation = {"case": row["case"], "generator_sha": sha, "collector_sha": collector_sha, "stages": {},
                           "runtime_helper_sha": sha if row["case"] in RUNTIME_CASES else None}
            if storage_continuation:
                observation["assessment_helper_shas"] = {stage: sha for stage in STAGES}
            for stage in STAGES:
                print(f"{utc_now()} Assessing {row['case']} / {stage}", flush=True)
                code = collect(destination / (stage + "-bundle"), destination / stage,
                               case=row["case"], stage=stage, declaration=declaration, approval=approval,
                               tools=tool_setup / "archives", grype_db=tool_setup / "grype-db",
                               trivy_cache=tool_setup / "trivy-cache")
                observation["stages"][stage] = code
                if code == 2:
                    summary["cases"].append(observation)
                    raise ImageAssessmentError("required scan/inventory incomplete; diagnose before affected-only repair")
            summary["cases"].append(observation)
            bundle = destination / (STAGES[1] + "-bundle")
            if row["case"] in RUNTIME_CASES:
                runtime = run_runtime(row, bundle, destination, task, sha)
                require(runtime["status"] == "passed", "required runtime proof incomplete; stop for diagnosis")
            finalize_case(destination, row, sha)
            docker(["buildx", "rm", "--force", builder], output, "builder-remove-owned-" + row["case"], timeout=120)
            builder_created = False
            resource_check(output)
            print(f"{utc_now()} Validated and retained evidence for {row['case']}", flush=True)
        if not cases:
            summary["generator_shas"] = sorted({row["generator_sha"] for row in summary["cases"]})
            write_json(output / "packaged-inventories.json", packaged_contract(output, declared, sha, summary=summary))
        scope_code = 1 if any(code for row in summary["cases"] for code in row["stages"].values()) else 0
        if cases:
            summary.update(status="partial-affected-scope", exit_code=2, affected_scope_exit_code=scope_code)
        else:
            require(len(summary["cases"]) == 30, "full campaign missing declared cases")
            summary.update(campaign_complete=True, exit_code=scope_code,
                           status="complete-with-findings" if scope_code else "complete-no-matches")
    except (ImageAssessmentError, OSError, ValueError, KeyError, TypeError, tarfile.TarError) as exc:
        summary["failure"] = str(exc) if isinstance(exc, ImageAssessmentError) else "required campaign evidence unavailable"
    finally:
        summary["generator_shas"] = sorted({row["generator_sha"] for row in summary["cases"]})
        summary["runtime_helper_shas"] = sorted({row["runtime_helper_sha"] for row in summary["cases"] if row.get("runtime_helper_sha")})
        if builder_created:
            try:
                docker(["buildx", "rm", "--force", builder], output, "builder-remove-owned", timeout=120)
            except ImageAssessmentError:
                summary.update(status="incomplete", exit_code=2, cleanup_failure="owned builder cleanup failed")
        summary["ended_at_utc"] = utc_now()
        write_json(output / "campaign.json", summary)
        _DOCKER_BOUNDARY = previous_boundary
        assessment_tools.STORAGE_GUARD = previous_guard
    return summary["exit_code"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    prepare = sub.add_parser("setup", help="download pinned public tools/DBs, never images/source uploads")
    prepare.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("campaign", help="one declared campaign, only after parent clean-freeze approval")
    for name in ("output", "declaration", "approval", "tool-setup", "baseline"):
        run.add_argument("--" + name, type=Path, required=True)
    run.add_argument("--cases", nargs="+", help="explicit affected-only repair scope, not equivalence")
    resume = sub.add_parser("continue-campaign", help="sole approved first-case runtime continuation; no repeated scans")
    for name in ("output", "declaration", "approval", "tool-setup", "baseline", "prior-campaign"):
        resume.add_argument("--" + name, type=Path, required=True)
    capacity = sub.add_parser("continue-capacity", help="reuse finalized first-case scans/runtime unchanged; execute remaining 29 cases")
    for name in ("output", "declaration", "approval", "tool-setup", "baseline", "prior-campaign"):
        capacity.add_argument("--" + name, type=Path, required=True)
    kafka = sub.add_parser("continue-kafka", help="preserve exactly nine completed cases; execute remaining 21 after classifier repair")
    for name in ("output", "declaration", "approval", "tool-setup", "baseline", "prior-campaign"):
        kafka.add_argument("--" + name, type=Path, required=True)
    storage = sub.add_parser("continue-storage", help="preserve exactly 23 assessments; assess saved final export and 18 remaining cases")
    for name in ("output", "declaration", "approval", "tool-setup", "baseline", "prior-campaign", "prior-manifest"):
        storage.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        kwargs = {key: value.resolve() if isinstance(value, Path) else value
                  for key, value in vars(args).items() if key != "operation"}
        if args.operation == "setup":
            setup(**kwargs)
            return 0
        if args.operation == "continue-capacity":
            kwargs["capacity_continuation"] = True
        if args.operation == "continue-kafka":
            kwargs["kafka_continuation"] = True
        if args.operation == "continue-storage":
            kwargs["storage_continuation"] = True
        return campaign(**kwargs)
    except Exception:
        # Exit 1 is reserved for complete findings-bearing proof, never a crash.
        print("Image tooling/campaign prerequisites incomplete; no automatic retry.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
