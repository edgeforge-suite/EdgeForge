"""Deterministic image evidence tests: no Docker, downloads or advisory queries."""

import copy
import errno
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from appbuilder.generation.container_policy import (
    BASE_REFERENCE_POLICY_ID,
    CONTAINER_BASES,
    base_references,
    declared_base_references,
    pinned_base,
)
from scripts import assemble_generated_image_campaign as assembly
from scripts import assess_generated_images as images
from scripts import collect_generated_images as driver
from scripts import publish_generated_image_evidence as publisher


def zipped(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return stream.getvalue()


def tarred(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return stream.getvalue()


def runtime_binding_fixture(config_id):
    return {"assessed_config_id": config_id, "docker_image_id": "sha256:" + "d" * 64,
            "tag": "edgeforge-image-proof-unit:crud-h2-j17-final", "runtime_helper_sha": "a" * 40,
            "runtime_identity_sha256": "b" * 64,
            "default_launch": {"User": "edgeforge", "Entrypoint": ["java", "-jar", "/app/app.jar"], "WorkingDir": "/app"}}


def write_runtime_fixture(directory, image, config, helper_sha, *, generator_sha=None):
    started = images.utc_now()
    manifest_bytes = json.dumps({"config": {"digest": image["image_id"]}, "layers": []}).encode()
    manifest_id = "sha256:" + images.digest(manifest_bytes)
    inspected = {"Id": manifest_id, "Descriptor": {"digest": manifest_id}, "Os": "linux", "Architecture": "amd64",
                 "Config": config["config"], "RootFS": {"Layers": image["rootfs"]}}
    images.write_json(directory / "runtime-image-inspect.stdout", [inspected])
    bundle = directory / (images.STAGES[1] + "-bundle")
    provenance = images.read_json(bundle / "provenance.json")
    binding = {"assessed_config_id": image["image_id"], "docker_image_id": manifest_id, "manifest_digest": manifest_id,
               "export_sha256": provenance["files"]["image.tar"], "jar_sha256": image["jar_sha256"], "rootfs": image["rootfs"],
               "generator_sha": generator_sha or helper_sha, "collector_sha": generator_sha or helper_sha,
               "runtime_helper_sha": helper_sha, "tag": "edgeforge-image-proof-unit:" + directory.name + "-final",
               "inspection_sha256": images.file_digest(directory / "runtime-image-inspect.stdout"),
               "default_launch": images.config_semantics({key: config["config"].get(key)
                                                           for key in ("User", "Entrypoint", "WorkingDir", "Healthcheck", "Cmd")})}
    (directory / "runtime-manifest.json").write_bytes(manifest_bytes)
    images.write_json(directory / "runtime-identity.json", binding)
    images.write_json(directory / "runtime-create.receipt.json", {"exit_code": 0,
                      "command": ["docker", "create", "--pull=never", "--platform", "linux/amd64", manifest_id]})
    images.write_json(directory / "runtime-created-state.stdout", [{"Image": manifest_id, "Config": config["config"]}])
    images.write_json(directory / "runtime-created-state.receipt.json", {"exit_code": 0,
                      "stdout_sha256": images.file_digest(directory / "runtime-created-state.stdout"),
                      "started_at_utc": images.utc_now(), "ended_at_utc": images.utc_now()})
    images.write_json(directory / "runtime-start.receipt.json", {"exit_code": 0,
                      "started_at_utc": images.utc_now(), "ended_at_utc": images.utc_now()})
    images.write_json(directory / "runtime.json", {"image_id": image["image_id"], "docker_image_id": manifest_id,
                      "runtime_helper_sha": helper_sha, "runtime_identity_sha256": images.file_digest(directory / "runtime-identity.json"),
                      "status": "passed", "uid": "1000", "application_health": "UP", "schema_settings": "generated defaults",
                      "default_user": True, "default_entrypoint": True, "started_at_utc": started, "ended_at_utc": images.utc_now()})


@pytest.fixture
def declaration(request):
    value = {"declared_before_campaign": True, "cases": [
        {"case": f"{shape}-{suffix}", "shape": shape, "fixture": fixture, "profile": profile,
         "platform": "linux/amd64", "assess": list(images.STAGES), "equivalence_claim": False,
         "historical_resolved_graph_representative": f"{shape}-{suffix}"}
        for shape, fixture in images.FIXTURES.items() for suffix, profile in images.PROFILES.items()]}
    if getattr(request, "param", None) == "noble":
        for row in value["cases"]:
            java = "21" if row["case"].endswith("j21") else "17"
            row.update(zip(("build_base", "runtime_base"), base_references(java), strict=True))
            row["base_reference_policy"] = BASE_REFERENCE_POLICY_ID
    return value


@pytest.fixture
def packaged():
    library = zipped({"META-INF/maven/g/a/pom.properties": b"groupId=g\nartifactId=a\nversion=1\n",
                      "native/linux/liba.so": b"native"})
    jar = zipped({"BOOT-INF/lib/a-1.jar": library})
    policy = {"dependency_policy": "policy-1", "packaged_policy": "passed", "resolved_policy": "passed",
              "packaged_libraries": ["a-1.jar"]}
    resolved = [{"group": "g", "artifact": "a", "version": "1", "type": "jar",
                 "classifier": "", "scope": "compile"}]
    return jar, policy, resolved


def saved_image(tmp_path, jar, *, stage=images.STAGES[1], platform="amd64", whiteout=False, wrong_hash=False):
    jar_path = "app/app.jar" if stage == images.STAGES[1] else "workspace/target/a.jar"
    files = {jar_path: jar}
    if stage == images.STAGES[0]:
        files["root/.m2/repository/g/a/1/a-1.jar"] = zipped({"META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n"})
    if whiteout:
        files["app/.wh.app.jar"] = b""
    layer = tarred(files)
    config = {"os": "linux", "architecture": platform,
              "rootfs": {"diff_ids": ["sha256:" + ("0" * 64 if wrong_hash else images.digest(layer))]},
              "config": {"User": "edgeforge", "Entrypoint": ["java", "-jar", "/app/app.jar"]}}
    raw_config = json.dumps(config).encode()
    result = tmp_path / "image.tar"
    result.write_bytes(tarred({"manifest.json": json.dumps([{"Config": "config.json", "Layers": ["layer.tar"]}]).encode(),
                              "config.json": raw_config, "layer.tar": layer}))
    return result, "/" + jar_path, "sha256:" + images.digest(raw_config)


@pytest.fixture
def reports():
    image = {"image_id": "sha256:" + "a" * 64, "rootfs": ["sha256:" + "b" * 64],
             "jar_sha256": "c" * 64, "cache_jars": ["/root/.m2/repository/g/a/1/a-1.jar"],
             "cache_jar_inventory": [{"path": "/root/.m2/repository/g/a/1/a-1.jar", "sha256": "d" * 64, "bytes": 100}]}
    metadata = {"imageID": image["image_id"], "os": "linux", "architecture": "amd64",
                "layers": [{"digest": value} for value in image["rootfs"]]}
    artifacts = [
        {"id": "os", "type": "deb", "name": "libc", "version": "1", "locations": []},
        {"id": "jdk", "type": "binary", "name": "openjdk", "version": "17.0.1",
         "locations": [{"path": "/opt/java/openjdk/release"}]},
        {"id": "jar", "type": "java-archive", "name": "a", "version": "1", "purl": "pkg:maven/g/a@1",
         "locations": [{"path": "/app/app.jar:BOOT-INF/lib/a-1.jar"},
                       {"path": image["cache_jars"][0]}]},
    ]
    syft = {"descriptor": {"version": "1.52.0"}, "source": {"type": "image", "metadata": metadata},
            "artifacts": artifacts}
    grype = {"descriptor": {"version": "0.119.0", "db": {"status": {
        "valid": True, "built": "2026-10-14T00:00:00Z", "schemaVersion": "6.1.9"}}},
        "source": {"type": "image", "target": copy.deepcopy(metadata)}, "matches": [], "ignoredMatches": []}
    trivy = {"Metadata": {"ImageID": image["image_id"], "DiffIDs": image["rootfs"]},
             "Results": [{"Class": "os-pkgs", "Type": "ubuntu", "Packages": [{"Name": "libc", "Version": "1"}],
                          "Vulnerabilities": []}]}
    packaged = [{"filename": "a-1.jar", "group": "g", "artifact": "a", "version": "1", "classifier": "", "sha256": "d" * 64}]
    return syft, grype, trivy, image, packaged


def supplemental(reports):
    _, grype, _, image, packaged = reports
    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [
        {"type": "library", "group": row["group"], "name": row["artifact"], "version": row["version"],
         "purl": f"pkg:maven/{row['group']}/{row['artifact']}@{row['version']}?type=jar",
         "hashes": [{"alg": "SHA-256", "content": row["sha256"]}]} for row in packaged],
        "metadata": {"properties": [{"name": "edgeforge:image-id", "value": image["image_id"]},
                                    {"name": "edgeforge:boot-jar-sha256", "value": image["jar_sha256"]}]}}
    report = {"descriptor": copy.deepcopy(grype["descriptor"]), "matches": [],
              "source": {"type": "sbom-file", "target": "packaged-authoritative.cdx.json"}}
    extracted = copy.deepcopy(sbom)
    for component in extracted["components"]:
        del component["hashes"]  # Grype's observed CDX output carries identities, not input digests.
        component["properties"] = [{"name": "syft:package:type", "value": "java-archive"}]
    return {"authoritative": sbom, "packaged_grype": report, "extracted": extracted}


def normalized(reports, stage=images.STAGES[1]):
    return images.normalize(*reports, stage=stage, **supplemental(reports), **build_inputs(reports))


def build_inputs(reports):
    return {"bom": {"bomFormat": "CycloneDX", "components": supplemental(reports)["authoritative"]["components"]},
            "resolved": [{"group": row["group"], "artifact": row["artifact"], "version": row["version"],
                          "classifier": row.get("classifier", ""), "type": "jar", "scope": "compile"} for row in reports[4]]}


def test_plan_all_30_both_stages_without_equivalence(declaration):
    plan = images.make_plan(declaration)
    assert len(plan["cases"]) == 30
    assert len({path for row in plan["cases"] for path in row["artifacts"].values()}) == 60
    assert all(not row["equivalence_claim"] for row in plan["cases"])


@pytest.mark.parametrize("change", ["missing", "duplicate", "profile", "stage", "equivalence", "platform"])
def test_plan_rejects_unapproved_coverage(declaration, change):
    row = declaration["cases"][0]
    if change == "missing":
        declaration["cases"].pop()
    elif change == "duplicate":
        declaration["cases"][1] = row
    elif change == "profile":
        row["profile"] = "wrong"
    elif change == "stage":
        row["assess"].pop()
    elif change == "equivalence":
        row["equivalence_claim"] = True
    else:
        row["platform"] = "linux/arm64"
    with pytest.raises(images.ImageAssessmentError):
        images.make_plan(declaration)


def test_actual_boot_jar_and_native_members(packaged):
    records, native = images.jar_inventory(*packaged)
    assert records[0]["filename"] == "a-1.jar"
    assert native[0]["sha256"] == images.digest(b"native")
    assert "unresolved" in native[0]["assessment"]


@pytest.mark.parametrize("change", ["empty", "malformed", "version", "missing-resolved", "policy", "metadata", "duplicate"])
def test_boot_inventory_failures(packaged, change):
    jar, policy, resolved = packaged
    if change == "empty":
        jar = zipped({})
    elif change == "malformed":
        jar = b"not a zip"
    elif change == "version":
        resolved[0]["version"] = "2"
    elif change == "missing-resolved":
        resolved = []
    elif change == "policy":
        policy["packaged_libraries"] = []
    elif change == "metadata":
        jar = zipped({"BOOT-INF/lib/a-1.jar": zipped({"META-INF/maven/g/a/pom.properties": b"groupId=other\nartifactId=a\nversion=1\n"})})
    else:
        resolved.append(copy.deepcopy(resolved[0]))
    with pytest.raises((images.ImageAssessmentError, zipfile.BadZipFile)):
        images.jar_inventory(jar, policy, resolved)


@pytest.mark.parametrize("stage", images.STAGES)
def test_saved_image_binds_actual_jar_config_rootfs(tmp_path, packaged, stage):
    path, jar_path, image_id = saved_image(tmp_path, packaged[0], stage=stage)
    receipt, actual = images.image_archive(path, jar_path=jar_path, stage=stage)
    assert actual == packaged[0]
    assert receipt["image_id"] == image_id
    assert receipt["jar_sha256"] == images.digest(actual)


@pytest.mark.parametrize("options", [{"platform": "arm64"}, {"whiteout": True}, {"wrong_hash": True}])
def test_saved_image_integrity_failures(tmp_path, packaged, options):
    path, jar_path, _ = saved_image(tmp_path, packaged[0], **options)
    with pytest.raises(images.ImageAssessmentError):
        images.image_archive(path, jar_path=jar_path, stage=images.STAGES[1])


def test_no_matches_means_validated_inventory_not_exit_code(reports):
    result = normalized(reports)
    assert result["findings"] == []
    assert "authoritative" in result["coverage"]["packaged_maven"]


@pytest.mark.parametrize("ignored", [False, True])
def test_active_and_scanner_excluded_findings_retained(reports, ignored):
    syft, grype, *_ = reports
    match = {"artifact": syft["artifacts"][0], "vulnerability": {"id": "CVE-test", "severity": "Low"}}
    if ignored:
        match["appliedIgnoreRules"] = [{"namespace": "default"}]
    grype["ignoredMatches" if ignored else "matches"].append(match)
    finding = normalized(reports)["findings"][0]
    assert finding["excluded_by_scanner"] is ignored
    assert finding["id"] == "CVE-test"


@pytest.mark.parametrize("change", ["empty", "jdk", "os", "image", "rootfs", "grype-image", "trivy-image", "db",
                                    "jar-location", "finding-identity", "missing-matches", "trivy-empty",
                                    "trivy-os", "trivy-finding", "tool-version", "duplicate-artifact", "cache"])
def test_malformed_incomplete_and_mismatched_reports(reports, change):
    syft, grype, trivy, image, _ = reports
    stage = images.STAGES[1]
    if change == "empty":
        syft["artifacts"] = []
    elif change == "jdk":
        syft["artifacts"].pop(1)
    elif change == "os":
        syft["artifacts"].pop(0)
    elif change == "image":
        syft["source"]["metadata"]["imageID"] = "sha256:" + "c" * 64
    elif change == "rootfs":
        syft["source"]["metadata"]["layers"] = []
    elif change == "grype-image":
        grype["source"]["target"]["imageID"] = "wrong"
    elif change == "trivy-image":
        trivy["Metadata"]["ImageID"] = "wrong"
    elif change == "db":
        grype["descriptor"]["db"]["status"]["valid"] = False
    elif change == "jar-location":
        syft["artifacts"][2]["locations"] = []
    elif change == "finding-identity":
        grype["matches"] = [{"artifact": {**syft["artifacts"][0], "version": "wrong"},
                             "vulnerability": {"id": "CVE-test"}}]
    elif change == "missing-matches":
        del grype["matches"]
    elif change == "trivy-empty":
        trivy["Results"] = []
    elif change == "trivy-os":
        trivy["Results"][0]["Packages"][0]["Version"] = "wrong"
    elif change == "trivy-finding":
        trivy["Results"][0]["Vulnerabilities"] = [{"PkgName": "absent", "InstalledVersion": "1", "VulnerabilityID": "CVE-test"}]
    elif change == "tool-version":
        syft["descriptor"]["version"] = "wrong"
    elif change == "duplicate-artifact":
        syft["artifacts"].append(syft["artifacts"][0])
    else:
        image["cache_jars"].append("/absent.jar")
        stage = images.STAGES[0]
    with pytest.raises(images.ImageAssessmentError):
        normalized(reports, stage)


def test_trivy_low_severity_finding_changes_summary(reports):
    before = normalized(reports)
    reports[2]["Results"][0]["Vulnerabilities"] = [{"PkgName": "libc", "InstalledVersion": "1",
                                                   "VulnerabilityID": "CVE-low", "Severity": "LOW"}]
    after = normalized(reports)
    assert after != before and after["findings"][0]["severity"] == "LOW"


def test_json_duplicate_keys_are_not_silently_accepted():
    with pytest.raises(images.ImageAssessmentError):
        images.decode(b'{"matches": [], "matches": null}')


@pytest.mark.parametrize("code", [1, 2])
def test_command_network_or_extractor_failure_is_incomplete(tmp_path, monkeypatch, code):
    monkeypatch.setattr(images.subprocess, "Popen", Mock(return_value=SimpleNamespace(wait=lambda **_: code)))
    with pytest.raises(images.ImageAssessmentError):
        images.run_tool(["scanner"], directory=tmp_path, label="failed", env={}, offline=False)
    assert images.read_json(tmp_path / "failed.receipt.json")["exit_code"] == code
    assert (tmp_path / "failed.stderr").exists()


def test_timeout_kills_process_group_and_retains_observation(tmp_path, monkeypatch):
    process = SimpleNamespace(pid=123, wait=Mock(side_effect=[subprocess.TimeoutExpired("scanner", 1), 0]))
    monkeypatch.setattr(images.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(images.os, "killpg", kill)
    with pytest.raises(images.ImageAssessmentError, match="timed out"):
        images.run_tool(["scanner"], directory=tmp_path, label="timeout", env={}, timeout=1, offline=False)
    kill.assert_called_once()
    assert images.read_json(tmp_path / "timeout.receipt.json")["failure"] == "timeout"


def test_no_implicit_network_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(images.sys, "platform", "linux")
    execute = Mock()
    monkeypatch.setattr(images.subprocess, "Popen", execute)
    with pytest.raises(images.ImageAssessmentError, match="network-denying"):
        images.run_tool(["scanner"], directory=tmp_path, label="offline", env={})
    execute.assert_not_called()


@pytest.mark.parametrize("change", ["checksum", "official-list", "version", "missing-binary"])
def test_tool_integrity_before_execution(tmp_path, monkeypatch, change):
    tools, output = tmp_path / "tools", tmp_path / "verified"
    tools.mkdir()
    output.mkdir()
    binary = b"verified official tool"
    archive = tarred({"tool" if change != "missing-binary" else "other": binary})
    archive = gzip.compress(archive, mtime=0)
    checksum = images.digest(archive)
    (tools / "tool.tar.gz").write_bytes(archive)
    (tools / "checksums.txt").write_text(f"{checksum if change != 'official-list' else 'bad'}  tool.tar.gz\n")
    pin = tmp_path / "pins.json"
    images.write_json(pin, {"tools": {"tool": {"archive": "tool.tar.gz", "checksums": "checksums.txt",
                                              "archive_sha256": checksum, "version": "1.2.3"}}})
    monkeypatch.setattr(images, "PINS", pin)
    monkeypatch.setattr(images.sys, "platform", "darwin")
    monkeypatch.setattr(images.os, "uname", lambda: SimpleNamespace(machine="arm64"))
    execute = Mock(return_value=b"tool 9.0.0")
    monkeypatch.setattr(images, "run_tool", execute)
    if change == "checksum":
        (tools / "tool.tar.gz").write_bytes(b"tampered")
    with pytest.raises(images.ImageAssessmentError):
        images.verify_tools(tools, output)
    assert execute.call_count == (1 if change == "version" else 0)


def test_gzip_retention_repeatable_and_originals_preserved(tmp_path):
    (tmp_path / "raw.json").write_bytes(b'{"private": "retained"}')
    first = images.retain_raw(tmp_path)
    second = images.retain_raw(tmp_path)
    assert first == second
    assert gzip.decompress((tmp_path / "raw.json.gz").read_bytes()) == (tmp_path / "raw.json").read_bytes()


@pytest.mark.parametrize("finding,bad_bom,bad_supplement", [(False, False, False), (True, False, False),
                                                        (False, True, False), (False, False, True)])
def test_collect_completed_exit_codes_and_offline_commands(tmp_path, monkeypatch, declaration, packaged, reports,
                                                         finding, bad_bom, bad_supplement):
    bundle, output = tmp_path / "bundle", tmp_path / "output"
    bundle.mkdir()
    declared = tmp_path / "declaration.json"
    images.write_json(declared, declaration)
    sha = "a" * 40
    case = declaration["cases"][0]
    path, jar_path, _ = saved_image(bundle, packaged[0])
    for name in ("Dockerfile", "source.tar", "input.tar", "generation.json"):
        (bundle / name).write_bytes(b"preserved")
    images.write_json(bundle / "dependency-policy.json", packaged[1])
    images.write_json(bundle / "resolved-inventory.json", packaged[2])
    component = {"group": "g", "name": "a", "version": "1", "purl": "pkg:maven/g/a@1?type=jar",
                 "hashes": [{"alg": "SHA-256", "content": images.jar_inventory(*packaged)[0][0]["sha256"]}]}
    if bad_bom:
        component["hashes"][0]["content"] = "0" * 64
    images.write_json(bundle / "retained-maven-bom.json", {"bomFormat": "CycloneDX", "components": [component]})
    images.write_json(bundle / "base-images.json", [{"image_id": "sha256:" + "a" * 64, "platform": "linux/amd64",
                                                   "repo_digests": ["base@sha256:" + "b" * 64]}] * 2)
    images.write_json(bundle / "provenance.json", {"generator_sha": sha, "case": case["case"], "profile": case["profile"],
                    "stage": images.STAGES[1], "jar_path": jar_path,
                    "files": {name: images.file_digest(bundle / name) for name in (
                        "Dockerfile", "source.tar", "input.tar", "generation.json", "dependency-policy.json",
                        "resolved-inventory.json", "base-images.json", "image.tar", "retained-maven-bom.json")}})
    approval = tmp_path / "approval.json"
    images.write_json(approval, {})
    monkeypatch.setattr(images, "check_freeze", Mock())
    monkeypatch.setattr(images, "db_receipt", lambda *_: {"database": "frozen"})
    monkeypatch.setattr(images, "verify_tools", lambda *_, **__: {"versions": "verified"})
    actual, _ = images.image_archive(path, jar_path=jar_path, stage=images.STAGES[1])
    syft, grype, trivy, _, _ = reports
    syft["source"]["metadata"]["imageID"] = actual["image_id"]
    syft["source"]["metadata"]["layers"] = [{"digest": value} for value in actual["rootfs"]]
    grype["source"]["target"] = syft["source"]["metadata"]
    trivy["Metadata"] = {"ImageID": actual["image_id"], "DiffIDs": actual["rootfs"]}
    actual_packaged = images.jar_inventory(*packaged)[0]
    supplement = supplemental((syft, grype, trivy, actual, actual_packaged))
    if bad_supplement:
        supplement["extracted"]["components"].clear()
    if finding:
        grype["matches"] = [{"artifact": syft["artifacts"][0], "vulnerability": {"id": "CVE-test"}}]
    commands = []

    def scanner(command, **kwargs):
        commands.append((command, kwargs))
        for name, data in (("syft", syft), ("grype", grype), ("trivy", trivy)):
            images.write_json(output / (name + ".json"), data)
        if kwargs["label"] == "grype-packaged":
            images.write_json(output / "grype-packaged.json", supplement["packaged_grype"])
            images.write_json(output / "grype-packaged-extracted.cdx.json", supplement["extracted"])

    monkeypatch.setattr(images, "run_tool", scanner)
    assert images.collect(bundle, output, case=case["case"], stage=images.STAGES[1], declaration=declared,
                          approval=approval, tools=tmp_path, grype_db=tmp_path, trivy_cache=tmp_path) == (
                              2 if bad_bom or bad_supplement else int(finding))
    result = images.read_json(output / "assessment.json")
    if bad_bom:
        assert result["status"] == "incomplete" and commands == []
        return
    if bad_supplement:
        assert result["status"] == "incomplete" and len(commands) == 4
        assert (output / "grype.json").exists() and (output / "grype.json.gz").exists()
        return
    assert result["status"] == ("complete-with-findings" if finding else "complete-no-matches")
    assert result["image"]["jar_sha256"] == images.digest(packaged[0])
    assert "--offline-scan" in commands[2][0] and "--skip-java-db-update" in commands[2][0]
    assert commands[-1][1]["label"] == "grype-packaged"
    assert commands[0][1]["env"]["SYFT_JAVA_USE_NETWORK"] == "false"
    assert commands[0][1]["env"]["TRIVY_CACHE_DIR"] == str(output / "scan-scratch/trivy-cache")
    assert (output / "scan-scratch/trivy-cache/db").is_symlink()


def test_missing_scan_output_is_incomplete_and_cannot_overwrite(tmp_path, declaration):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    declared = tmp_path / "declaration.json"
    images.write_json(declared, declaration)
    kwargs = {"case": "crud-h2-j17", "stage": images.STAGES[1], "declaration": declared,
              "approval": tmp_path / "absent", "tools": tmp_path, "grype_db": tmp_path, "trivy_cache": tmp_path}
    assert images.collect(bundle, tmp_path / "out", **kwargs) == 2
    assert images.read_json(tmp_path / "out" / "assessment.json")["status"] == "incomplete"
    with pytest.raises(images.ImageAssessmentError, match="already exists"):
        images.collect(bundle, tmp_path / "out", **kwargs)


def test_resource_floor_stops_without_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(driver.shutil, "disk_usage", lambda _: SimpleNamespace(free=19 * 1024**3))
    with pytest.raises(images.ImageAssessmentError, match="disk safety"):
        driver.resource_check(tmp_path)


def test_compressed_bytes_and_declared_size_are_verified(tmp_path):
    data = b"retained exact image"
    path = tmp_path / "image.tar.gz"
    path.write_bytes(publisher.compressed(data))
    images.verify_gzip(path, images.digest(data), len(data))
    with pytest.raises(images.ImageAssessmentError):
        images.verify_gzip(path, images.digest(data), len(data) - 1)


def test_packaged_contract_all30_and_tamper_rejection(tmp_path, declaration):
    sha = "a" * 40
    for row in declaration["cases"]:
        output = tmp_path / row["case"] / images.STAGES[1]
        output.mkdir(parents=True)
        images.write_json(output / "packaged.json", [{"filename": "a-1.jar"}])
        images.write_json(output / "assessment.json", {"case": row["case"], "stage": images.STAGES[1],
                          "generator_sha": sha, "image": {"image_id": "sha256:" + "a" * 64, "jar_sha256": "b" * 64},
                          "retained_raw": [{"file": "packaged.json", "sha256": images.file_digest(output / "packaged.json")}]})
    result = images.packaged_contract(tmp_path, declaration, sha)
    assert result["generator_sha"] == sha and len(result["cases"]) == 30
    assert set(result["cases"][0]) == {"case", "packaged_libraries", "image_id", "jar_sha256"}
    (tmp_path / declaration["cases"][0]["case"] / images.STAGES[1] / "packaged.json").write_text('[{"filename":"tampered.jar"}]')
    with pytest.raises(images.ImageAssessmentError, match="integrity"):
        images.packaged_contract(tmp_path, declaration, sha)


def test_dated_inventory_reconciliation_preflight():
    """Diagnose packaging-only components before any expensive image builds."""
    baseline = images.ROOT / "docs/handover-evidence/generated-maven/2026-10-05"
    differences = {}
    for shape in images.FIXTURES:
        for suffix in images.PROFILES:
            case = f"{shape}-{suffix}"
            receipt = images.read_json(baseline / case / "assessment-receipt.json")
            representative = receipt.get("representative_case", case)
            resolved = images.read_json(baseline / representative / "assessment/inventory.json")
            policy = images.read_json(baseline / case / "dependency-policy.json")
            expected = {f"{row['artifact']}-{row['version']}" +
                        (f"-{row['classifier']}" if row.get("classifier") else "") + ".jar"
                        for row in resolved if row["scope"] in {"compile", "runtime"} and row["type"] == "jar"}
            actual = set(policy["packaged_libraries"])
            packaging_only = {f"spring-boot-jarmode-tools-{row['version']}.jar" for row in resolved
                              if (row["group"], row["artifact"]) == ("org.springframework.boot", "spring-boot")}
            starter_only = {f"{row['artifact']}-{row['version']}.jar" for row in resolved
                            if row["group"] == "org.springframework.boot"
                            and row["artifact"].startswith("spring-boot-starter")}
            if actual - expected != packaging_only or not expected - actual <= starter_only:
                differences[case] = {"packaged-only": sorted(actual - expected), "resolved-only": sorted(expected - actual)}
    assert not differences, differences


@pytest.mark.parametrize("outcome,partial", [(0, False), (1, False), (2, False), (0, True)])
def test_campaign_stops_on_incomplete_never_findings(tmp_path, monkeypatch, declaration, outcome, partial):
    declared = tmp_path / "declaration.json"
    approved = tmp_path / "approval.json"
    images.write_json(declared, declaration)
    images.write_json(approved, {"generator_sha": "a" * 40})
    monkeypatch.setattr(driver, "check_freeze", Mock())
    monkeypatch.setattr(driver, "resource_check", Mock())
    monkeypatch.setattr(driver, "db_receipt", Mock())
    monkeypatch.setattr(driver, "local_docker_boundary", lambda *_: {"effective_endpoint": "unix:///local.sock"})
    monkeypatch.setattr(driver, "refresh_bases", lambda *_: {})
    commands = []
    monkeypatch.setattr(driver, "docker", lambda command, *_, **__: commands.append(command))
    built = []

    def build(row, destination, **_):
        built.append(row["case"])
        destination.mkdir()
        bundle = destination / (images.STAGES[1] + "-bundle")
        bundle.mkdir()
        (bundle / "image.iid").write_text("sha256:" + "a" * 64)

    monkeypatch.setattr(driver, "build_case", build)
    monkeypatch.setattr(driver, "collect", lambda *_, **__: outcome)
    monkeypatch.setattr(driver, "run_runtime", lambda *_, **__: {"status": "passed"})
    monkeypatch.setattr(driver, "finalize_case", Mock())
    monkeypatch.setattr(driver, "packaged_contract", lambda *_, **__: {"cases": []})
    output = tmp_path / "campaign"
    code = driver.campaign(output, declaration=declared, approval=approved, tool_setup=tmp_path, baseline=tmp_path,
                           cases=["crud-h2-j17"] if partial else None)
    assert code == (2 if partial else outcome)
    result = images.read_json(output / "campaign.json")
    assert len(built) == (1 if outcome == 2 or partial else 30)
    assert result["status"] == ("partial-affected-scope" if partial else {
        0: "complete-no-matches", 1: "complete-with-findings", 2: "incomplete"}[outcome])
    assert any(command[:3] == ["buildx", "rm", "--force"] for command in commands)
    assert not any("prune" in command for command in commands)
    creates = [command for command in commands if command[:2] == ["buildx", "create"]]
    removes = [command for command in commands if command[:3] == ["buildx", "rm", "--force"]]
    assert len(creates) == len(removes) == len(built)
    assert len({command[command.index("--name") + 1] for command in creates}) == len(built)
    assert {command[command.index("--name") + 1] for command in creates} == {command[-1] for command in removes}
    assert (output / "packaged-inventories.json").exists() is (outcome != 2 and not partial)


def test_freeze_requires_explicit_approval_before_docker(tmp_path, monkeypatch, declaration):
    declared, approved = tmp_path / "declaration.json", tmp_path / "approval.json"
    images.write_json(declared, declaration)
    images.write_json(approved, {"generator_sha": "a" * 40})
    docker = Mock()
    monkeypatch.setattr(driver, "docker", docker)
    with pytest.raises(images.ImageAssessmentError, match="approval"):
        driver.campaign(tmp_path / "campaign", declaration=declared, approval=approved, tool_setup=tmp_path, baseline=tmp_path)
    docker.assert_not_called()
    assert not (tmp_path / "campaign").exists()


def test_campaign_cli_list_approval_is_incomplete_not_findings(tmp_path, monkeypatch, declaration, capsys):
    declared, approved, output = tmp_path / "declaration.json", tmp_path / "approval.json", tmp_path / "output"
    images.write_json(declared, declaration)
    images.write_json(approved, [])
    docker = Mock(side_effect=AssertionError("invalid approval must not reach Docker"))
    monkeypatch.setattr(driver, "docker", docker)
    assert driver.main(["campaign", "--output", str(output), "--declaration", str(declared),
                        "--approval", str(approved), "--tool-setup", str(tmp_path),
                        "--baseline", str(tmp_path)]) == 2
    assert "incomplete" in capsys.readouterr().err
    docker.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize("error", [OSError, RuntimeError])
def test_campaign_cli_path_resolution_is_inside_incomplete_boundary(monkeypatch, error, capsys):
    def unavailable(_path):
        raise error("synthetic inaccessible or cyclic path")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", unavailable)
        assert driver.main(["campaign", "--output", "unused", "--declaration", "unused", "--approval", "unused",
                            "--tool-setup", "unused", "--baseline", "unused"]) == 2
    assert "incomplete" in capsys.readouterr().err


@pytest.mark.parametrize("module,operation,args", [
    (driver, "campaign", ["campaign", "--output", "unused", "--declaration", "unused", "--approval", "unused",
                          "--tool-setup", "unused", "--baseline", "unused"]),
    (assembly, "assemble", ["--first", "unused", "--remaining", "unused", "--declaration", "unused", "--output", "unused"]),
    (publisher, "publish", ["--campaign", "unused", "--declaration", "unused", "--output", "unused"]),
    (images, "collect", ["collect", "--bundle", "unused", "--output", "unused", "--declaration", "unused",
                         "--approval", "unused", "--tools", "unused", "--grype-db", "unused", "--trivy-cache", "unused",
                         "--case", "crud-h2-j17", "--stage", images.STAGES[0]]),
])
@pytest.mark.parametrize("error", [AttributeError, IndexError, OverflowError, RuntimeError, SystemExit, KeyboardInterrupt])
def test_all_image_cli_exception_boundaries_are_fail_closed(module, operation, args, error, monkeypatch):
    def fail(*_args, **_kwargs):
        raise error("synthetic inspection failure")
    monkeypatch.setattr(module, operation, fail)
    if issubclass(error, Exception):
        assert module.main(args) == 2
    else:
        with pytest.raises(error):
            module.main(args)


def test_default_nonroot_runtime_controls_and_owned_cleanup(tmp_path, monkeypatch):
    commands = []
    image_id = "sha256:" + "a" * 64
    binding = runtime_binding_fixture(image_id)

    def docker(command, *_args, **_kwargs):
        commands.append(command)
        if command[0] == "inspect":
            return json.dumps([{"Image": binding["docker_image_id"], "Config": binding["default_launch"],
                                "State": {"Running": True, "Health": {"Status": "healthy"}}}]).encode()
        if "id" in command:
            return b"1000\n"
        if "wget" in command:
            return b'{"status":"UP"}'
        return b""

    monkeypatch.setattr(driver, "docker", docker)
    outcome = driver.startup(binding, tmp_path, "owned-runtime")
    assert outcome["status"] == "passed"
    create = commands[0]
    assert create[-1] == binding["docker_image_id"] != image_id and "--pull=never" in create
    assert "--network" in create and "none" in create
    assert commands[1] == ["inspect", "owned-runtime"] and commands[2] == ["start", "owned-runtime"]
    assert "--user" not in create and "--entrypoint" not in create
    assert not any("DDL" in str(part) or "SCHEMA" in str(part) for part in create)
    assert commands[-1] == ["rm", "-f", "owned-runtime"]
    assert outcome["claim"] == "health/nonroot startup only; not business certification"


@pytest.mark.parametrize("endpoint", [
    "tcp://127.0.0.1:2375", "tcp://remote:2376", "ssh://host", "https://cloud.example",
    "unix://remote/docker.sock", "unix:///tmp/../docker.sock", "unix:///missing.sock",
])
def test_nonlocal_or_invalid_docker_endpoints_rejected(endpoint):
    with pytest.raises(images.ImageAssessmentError, match="local Unix socket"):
        driver.validate_local_endpoint(endpoint)


def test_context_guard_blocks_remote_before_submission(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.setattr(driver.shutil, "which", lambda _: "/docker")
    calls = []

    def execute(command, **_):
        calls.append(command)
        if command[-1] == "show":
            return b"desktop-linux"
        return b'[{"Endpoints":{"docker":{"Host":"ssh://remote"}}}]'

    monkeypatch.setattr(driver, "run_tool", execute)
    monkeypatch.setattr(driver, "_DOCKER_BOUNDARY", None)
    with pytest.raises(images.ImageAssessmentError):
        driver.docker(["buildx", "build", "private-source"], tmp_path, "forbidden-build")
    assert all(command[1] == "context" for command in calls)


def test_local_context_is_recorded_and_operations_pin_endpoint(tmp_path, monkeypatch):
    endpoint_path = tmp_path / "docker.sock"
    with monkeypatch.context() as context:
        context.setattr(type(endpoint_path), "is_socket", lambda path: path == endpoint_path)
        endpoint = "unix://" + str(endpoint_path)
        monkeypatch.delenv("DOCKER_HOST", raising=False)
        monkeypatch.setenv("DOCKER_CONTEXT", "desktop-linux")
        monkeypatch.setenv("BUILDX_BUILDER", "remote-builder")
        monkeypatch.setattr(driver.shutil, "which", lambda _: "/docker")
        calls = []

        def execute(command, **kwargs):
            calls.append((command, kwargs["env"]))
            if command[-1] == "show":
                return b"desktop-linux"
            if command[1] == "context":
                return json.dumps([{"Endpoints": {"docker": {"Host": endpoint}}}]).encode()
            return b"local-operation"

        monkeypatch.setattr(driver, "run_tool", execute)
        monkeypatch.setattr(driver, "_DOCKER_BOUNDARY", None)
        assert driver.docker(["version"], tmp_path, "local") == b"local-operation"
        assert calls[-1][0] == ["/docker", "--host", endpoint, "version"]
        assert "DOCKER_CONTEXT" not in calls[-1][1] and "BUILDX_BUILDER" not in calls[-1][1]
        receipt = images.read_json(tmp_path / "local-boundary.json")
        assert receipt["effective_endpoint"] == endpoint and receipt["offload_allowed"] is False


def test_remote_host_override_rejected_even_with_local_context(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote:2375")
    monkeypatch.setattr(driver.shutil, "which", lambda _: "/docker")
    execute = Mock()
    monkeypatch.setattr(driver, "run_tool", execute)
    with pytest.raises(images.ImageAssessmentError):
        driver.local_docker_boundary(tmp_path)
    execute.assert_not_called()


def test_public_bases_refreshed_once_not_assumed_from_daemon_cache(tmp_path, monkeypatch):
    old = {"Id": "sha256:" + "a" * 64, "Architecture": "arm64", "RepoDigests": ["old"]}
    new = {"Id": "sha256:" + "b" * 64, "Architecture": "amd64", "Os": "linux",
           "RepoDigests": ["base@sha256:" + "c" * 64], "RootFS": {"Layers": ["sha256:" + "d" * 64]}}
    calls, pulled = [], set()

    def docker(command, *_args, **_kwargs):
        calls.append(command)
        if command[0] == "pull":
            pulled.add(command[-1])
            return b"pulled"
        return json.dumps([new if command[-1] in pulled else old]).encode()

    monkeypatch.setattr(driver, "docker", docker)
    rows = [{"build_base": f"maven:3.9.9-eclipse-temurin-{java}", "runtime_base": f"eclipse-temurin:{java}-jre"}
            for java in ("17", "21")] * 15
    resolved = driver.refresh_bases(rows, tmp_path)
    pulls = [command for command in calls if command[0] == "pull"]
    assert len(pulls) == 4 and all(command[1:3] == ["--platform", "linux/amd64"] for command in pulls)
    assert set(resolved) == driver.DECLARED_BASES
    assert all(row["image_id"] == new["Id"] and row["cached_before"]["image_id"] == old["Id"]
               for row in resolved.values())
    assert images.read_json(tmp_path / "base-refresh.json") == resolved


def test_base_refresh_refuses_undeclared_reference_before_pull(tmp_path, monkeypatch):
    execute = Mock()
    monkeypatch.setattr(driver, "docker", execute)
    with pytest.raises(images.ImageAssessmentError):
        driver.refresh_bases([{"build_base": "private-base", "runtime_base": "other"}], tmp_path)
    execute.assert_not_called()


def test_known_crud_list_get_is_readonly_and_not_business_certification(tmp_path, monkeypatch):
    image_id = "sha256:" + "a" * 64
    binding = runtime_binding_fixture(image_id)
    calls = []

    def docker(command, *_args, **_kwargs):
        calls.append(command)
        if command[0] == "inspect":
            return json.dumps([{"Image": binding["docker_image_id"], "Config": binding["default_launch"],
                                "State": {"Running": True, "Health": {"Status": "healthy"}}}]).encode()
        if "id" in command:
            return b"1000"
        if command[-1].endswith("/api/v1/records"):
            return b"[]"
        if "wget" in command:
            return b'{"status":"UP"}'
        return b""

    monkeypatch.setattr(driver, "docker", docker)
    outcome = driver.startup(binding, tmp_path, "owned", list_path="/api/v1/records")
    assert outcome["status"] == "passed" and outcome["readonly_crud_list"]["status"] == "passed"
    assert outcome["readonly_crud_list"]["response_sha256"] == images.digest(b"[]")
    assert "not business certification" in outcome["claim"]
    assert not any("--post-data" in command for command in calls)


@pytest.fixture
def completed_campaign(tmp_path, declaration, reports, monkeypatch):
    monkeypatch.setattr(publisher, "resource_check", Mock())
    campaign_started = images.utc_now()
    campaign = tmp_path / "private-campaign"
    campaign.mkdir()
    declared = tmp_path / "declaration.json"
    images.write_json(declared, declaration)
    sha = "a" * 40
    pins = images.read_json(images.PINS)["tools"]
    tools = {name: {**pin, "binary_sha256": "b" * 64, "checksums_sha256": "c" * 64}
             for name, pin in pins.items()}
    databases = {name: {"metadata": [{"UpdatedAt": "2026-10-14T00:00:00Z"}],
                       "files": [{"file": "database", "sha256": "d" * 64}]}
                 for name in ("grype", "trivy", "trivy-java")}
    cases = []
    for row in declaration["cases"]:
        cases.append({"case": row["case"], "stages": {stage: 0 for stage in images.STAGES}})
        for stage in images.STAGES:
            stage_started = images.utc_now()
            directory = campaign / row["case"] / stage
            bundle = campaign / row["case"] / (stage + "-bundle")
            directory.mkdir(parents=True)
            bundle.mkdir()
            syft, grype, trivy, image, packaged_rows = copy.deepcopy(reports)
            config = {"os": "linux", "architecture": "amd64", "rootfs": {"diff_ids": image["rootfs"]},
                      "config": {"User": "edgeforge" if stage == images.STAGES[1] else "",
                                 "Entrypoint": ["java", "-jar", "/app/app.jar"], "WorkingDir": "/app"}}
            config_bytes = json.dumps(config).encode()
            image.update(platform="linux/amd64", config_sha256=images.digest(config_bytes),
                         image_id="sha256:" + images.digest(config_bytes),
                         configuration_sha256=images.digest(json.dumps(config["config"], sort_keys=True).encode()),
                         jar_sha256="c" * 64)
            syft["source"]["metadata"]["imageID"] = image["image_id"]
            grype["source"]["target"]["imageID"] = image["image_id"]
            trivy["Metadata"]["ImageID"] = image["image_id"]
            packaged_rows[0]["sha256"] = "d" * 64
            syft["source"]["metadata"]["userInput"] = "/" "Users/fixture/private/image.tar"
            syft["descriptor"]["configuration"] = {"cache": "/" "Users/fixture/private/cache", "image_path": "/app/app.jar"}
            supplement = supplemental((syft, grype, trivy, image, packaged_rows))
            build = build_inputs((syft, grype, trivy, image, packaged_rows))
            normalized = images.normalize(syft, grype, trivy, image, packaged_rows, stage=stage, **supplement, **build)
            bases = [{"image_id": "sha256:" + "e" * 64, "repo_digests": ["base@sha256:" + "f" * 64],
                      "platform": "linux/amd64", "rootfs": image["rootfs"], "reference": reference}
                     for reference in declared_base_references(row)]
            for base in bases:
                pin = pinned_base(base["reference"])
                if pin is not None:
                    base.update(image_id=pin.config_digest,
                                repo_digests=[pin.tag.split(":")[0] + "@" + pin.index_digest],
                                tag_index_digest=pin.index_digest,
                                amd64_manifest_digest=pin.amd64_manifest_digest,
                                config_digest=pin.config_digest)
            for name, value in (
                    ("generation.json", {"profile": row["profile"]}),
                    ("resolved-inventory.json", build["resolved"]),
                    ("dependency-policy.json", {"packaged_libraries": ["a-1.jar"]}),
                    ("retained-maven-bom.json", {"bomFormat": "CycloneDX", "components": [{
                        "group": "g", "name": "a", "version": "1", "purl": "pkg:maven/g/a@1?type=jar",
                        "hashes": [{"alg": "SHA-256", "content": packaged_rows[0]["sha256"]}]}]}),
                    ("base-images.json", bases)):
                images.write_json(bundle / name, value)
            (bundle / "image-config.json").write_bytes(config_bytes)
            images.write_json(bundle / "image-manifest.json", [{"Config": image["config_sha256"] + ".json",
                                                              "Layers": ["layer.tar"]}])
            for name in ("source.tar", "input.tar"):
                (bundle / name).write_bytes(b"PRIVATE-ARCHIVE-NOT-FOR-PUBLICATION")
            image_bytes = b"PRIVATE-IMAGE-NOT-FOR-PUBLICATION"
            (directory / "Dockerfile").write_text("FROM public\n# /" "Users/fixture/private/source\n")
            provenance = {"generator_sha": sha, "case": row["case"], "profile": row["profile"], "stage": stage,
                          "files": {name: images.file_digest(bundle / name) for name in (
                              *publisher.BUNDLE_JSON, "source.tar", "input.tar")}}
            provenance["files"].update(Dockerfile=images.file_digest(directory / "Dockerfile"),
                                       **{"image.tar": images.digest(image_bytes)})
            images.write_json(bundle / "provenance.json", provenance)
            for name, value in (
                    ("syft.json", syft), ("grype.json", grype), ("trivy.json", trivy),
                    ("inventory.json", normalized["inventory"]), ("findings.json", normalized["findings"]),
                    ("packaged.json", packaged_rows), ("native-members.json", []),
                    ("packaged-bom-integrity.json", images.validate_packaged_bom(
                        packaged_rows, images.read_json(bundle / "retained-maven-bom.json"))),
                    ("packaged-authoritative.cdx.json", supplement["authoritative"]),
                    ("grype-packaged.json", supplement["packaged_grype"]),
                    ("grype-packaged-extracted.cdx.json", supplement["extracted"]),
                    ("bootstrap-provenance.json", []),
                    ("coordinate-gaps.json", normalized["coordinate-gaps"]),
                    ("cache-scanner-gaps.json", normalized["cache-scanner-gaps"]),
                    ("build-bom-coverage.json", normalized["build-bom-coverage"]),
                    ("provenance.json", provenance), ("databases.json", databases),
                    ("syft.receipt.json", {"command": ["syft", "docker-archive:/" "Users/fixture/private/image.tar"],
                                           "exit_code": 0, "started_at_utc": images.utc_now(), "ended_at_utc": images.utc_now()}),
                    ("grype.receipt.json", {"command": ["grype"], "exit_code": 0,
                                            "started_at_utc": images.utc_now(), "ended_at_utc": images.utc_now()}),
                    ("grype-packaged.receipt.json", {"command": ["grype"], "exit_code": 0,
                                                     "started_at_utc": images.utc_now(), "ended_at_utc": images.utc_now()}),
                    ("trivy.receipt.json", {"command": ["trivy"], "exit_code": 0,
                                            "started_at_utc": images.utc_now(), "ended_at_utc": images.utc_now()})):
                images.write_json(directory / name, value)
            report = {"case": row["case"], "stage": stage, "generator_sha": sha,
                      "started_at_utc": stage_started, "ended_at_utc": images.utc_now(),
                      "status": "complete-no-matches", "exit_code": 0, "image": image,
                      "tools": tools, "bases": bases, "coverage": normalized["coverage"],
                      "findings": 0, "packaged_libraries": ["a-1.jar"],
                      "retained_raw": images.retain_raw(directory)}
            images.write_json(directory / "assessment.json", report)
            retained = row["case"] in driver.RUNTIME_CASES and stage == images.STAGES[1]
            retention = {"schema_version": 2, "case": row["case"], "stage": stage, "generator_sha": sha,
                         "image_id": image["image_id"], "platform": "linux/amd64",
                         "image_tar_sha256": images.digest(image_bytes), "image_tar_bytes": len(image_bytes),
                         "assessment_sha256": images.file_digest(directory / "assessment.json"),
                         "retained": retained, "validation": "complete", "assessment_exit_code": 0,
                         "cleanup": {"status": "removed", "verified_export_sha256": images.digest(image_bytes),
                                     "verified_export_bytes": len(image_bytes)},
                         "replay": "exact saved-image replay" if retained else "not retained; no exact image replay or rescan"}
            if retained:
                (bundle / "image.tar.gz").write_bytes(publisher.compressed(image_bytes))
                retention["image_tar_gz_sha256"] = images.file_digest(bundle / "image.tar.gz")
            images.write_json(bundle / "image-retention.json", retention)
        if row["case"] in driver.RUNTIME_CASES:
            write_runtime_fixture(campaign / row["case"], image, config, sha)
    images.write_json(campaign / "campaign.json", {
        "generator_sha": sha, "campaign_complete": True, "status": "complete-no-matches",
        "started_at_utc": campaign_started, "ended_at_utc": images.utc_now(),
        "exit_code": 0, "coverage_sha256": images.file_digest(declared), "cases": cases})
    images.write_json(campaign / "packaged-inventories.json", images.packaged_contract(campaign, declaration, sha))
    return campaign, declared


@pytest.mark.parametrize("declaration", ["noble"], indirect=True)
def test_noble_normalized_plan_publishes_all_declared_base_identities(tmp_path, completed_campaign):
    campaign, declared = completed_campaign
    original = images.read_json(declared)
    plan = images.make_plan(original)
    assert len(plan["cases"]) == 30
    for source, normalized in zip(original["cases"], plan["cases"], strict=True):
        for key in ("build_base", "runtime_base", "base_reference_policy"):
            assert normalized[key] == source[key]
        assert declared_base_references(normalized) == declared_base_references(source)
    output = tmp_path / "noble-publication"
    result = publisher.publish(campaign, declared, output, host_prefixes=["/" "Users/fixture"])
    assert result["cases"] == 30 and result["stage_observations"] == 60
    for row in plan["cases"]:
        java = "21" if row["case"].endswith("j21") else "17"
        for stage in images.STAGES:
            report = images.decode(gzip.decompress(
                (output / row["case"] / stage / "assessment.json.gz").read_bytes()))
            for observed, pin in zip(report["bases"], CONTAINER_BASES[java], strict=True):
                assert observed["reference"] == pin.reference
                assert observed["config_digest"] == pin.config_digest
                assert observed["amd64_manifest_digest"] == pin.amd64_manifest_digest
                assert observed["tag_index_digest"] == pin.index_digest


def test_publish_complete_sanitized_layout_repeatable_and_no_archive_contents(tmp_path, completed_campaign):
    campaign, declared = completed_campaign
    output, repeat = tmp_path / "published", tmp_path / "repeat"
    for target in (output, repeat):
        result = publisher.publish(campaign, declared, target, host_prefixes=["/" "Users/fixture"])
        assert result["cases"] == 30 and result["stage_observations"] == 60
    manifest = images.read_json(output / "publication.json")
    assert manifest == images.read_json(repeat / "publication.json")
    assert manifest["status"] == "complete"
    relative = "crud-h2-j17/" + images.STAGES[1] + "/syft.json.gz"
    raw = gzip.decompress((output / relative).read_bytes())
    sanitized = images.decode(raw)
    assert "/" "Users/fixture" not in raw.decode()
    assert sanitized["artifacts"][2]["purl"] == "pkg:maven/g/a@1"
    assert sanitized["artifacts"][2]["locations"][0]["path"] == "/app/app.jar:BOOT-INF/lib/a-1.jar"
    row = next(row for row in manifest["files"] if row["file"] == relative)
    assert row["private_original_sha256"] != row["sanitized_json_sha256"]
    assert row["sanitized_json_sha256"] == images.digest(raw)
    assert (output / relative).read_bytes() == (repeat / relative).read_bytes()
    assert (output / relative).read_bytes()[4:8] == b"\x00" * 4
    for path in output.rglob("*"):
        if path.is_file():
            assert ".tar" not in path.name and not path.name.endswith(".db")
            assert b"PRIVATE-ARCHIVE" not in path.read_bytes() and b"PRIVATE-IMAGE" not in path.read_bytes()
    assert images.read_json(campaign / "crud-h2-j17" / images.STAGES[1] / "syft.json")["source"]["metadata"]["userInput"].startswith("/" "Users/fixture")
    with pytest.raises(images.ImageAssessmentError, match="new independent"):
        publisher.publish(campaign, declared, output)


@pytest.mark.parametrize("change", [
    "partial", "missing-stage", "wrong-case", "raw-tamper", "gzip-tamper", "normalized-mismatch",
    "source-tamper", "image-tamper", "tool-version", "runtime-root", "packaged-contract",
    "pair-mismatch", "db-snapshot", "base-identity",
])
def test_publish_rejects_incomplete_or_mismatched_evidence_before_output(tmp_path, completed_campaign, change):
    campaign, declared = completed_campaign
    directory = campaign / "crud-h2-j17" / images.STAGES[1]
    bundle = campaign / "crud-h2-j17" / (images.STAGES[1] + "-bundle")
    report = images.read_json(directory / "assessment.json")
    if change == "partial":
        summary = images.read_json(campaign / "campaign.json")
        summary["campaign_complete"] = False
        images.write_json(campaign / "campaign.json", summary)
    elif change == "missing-stage":
        (directory / "trivy.json").unlink()
    elif change == "wrong-case":
        report["case"] = "wrong"
    elif change == "raw-tamper":
        (directory / "syft.json").write_text("{}")
    elif change == "gzip-tamper":
        (directory / "syft.json.gz").write_bytes(b"tampered")
    elif change == "normalized-mismatch":
        images.write_json(directory / "inventory.json", [])
        report["retained_raw"] = images.retain_raw(directory)
    elif change == "source-tamper":
        (bundle / "source.tar").write_bytes(b"tampered")
    elif change == "image-tamper":
        (bundle / "image.tar.gz").write_bytes(b"tampered")
    elif change == "tool-version":
        report["tools"]["syft"]["version"] = "wrong"
    elif change == "runtime-root":
        runtime = images.read_json(campaign / "crud-h2-j17" / "runtime.json")
        runtime["uid"] = "0"
        images.write_json(campaign / "crud-h2-j17" / "runtime.json", runtime)
    elif change == "packaged-contract":
        images.write_json(campaign / "packaged-inventories.json", {})
    elif change == "pair-mismatch":
        report["image"]["jar_sha256"] = "e" * 64
    elif change == "base-identity":
        report["bases"] = []
    else:
        database = images.read_json(directory / "databases.json")
        database["grype"]["files"][0]["sha256"] = "e" * 64
        images.write_json(directory / "databases.json", database)
        report["retained_raw"] = images.retain_raw(directory)
    images.write_json(directory / "assessment.json", report)
    output = tmp_path / "rejected"
    with pytest.raises((images.ImageAssessmentError, OSError)):
        publisher.publish(campaign, declared, output, host_prefixes=["/" "Users/fixture"])
    assert not output.exists()


def test_recursive_host_redaction_preserves_identities_and_rejects_collisions():
    original = {"nested": [{"path": "/" "Users/operator/cache/archive", "image": "/root/.m2/g/a.jar",
                            "type": "java-archive", "name": "a", "version": "1", "purl": "pkg:maven/g/a@1"}]}
    sanitized = publisher.redact(original, ["/" "Users/operator"])
    assert sanitized["nested"][0]["path"] == "<host-0>/cache/archive"
    assert sanitized["nested"][0]["image"] == "/root/.m2/g/a.jar"
    assert original["nested"][0]["path"].startswith("/" "Users/operator")
    with pytest.raises(images.ImageAssessmentError, match="identity/content"):
        publisher.redact({"type": "java-archive", "name": "/" "Users/operator", "version": "1"}, ["/" "Users/operator"])
    with pytest.raises(images.ImageAssessmentError, match="collide"):
        publisher.redact({"/" "Users/operator/file": 1, "<host-0>/file": 2}, ["/" "Users/operator"])


@pytest.mark.parametrize("different_home", [False, True])
def test_moved_publication_refuses_recorded_host_roots_until_explicitly_redacted(
        tmp_path, completed_campaign, monkeypatch, different_home):
    campaign, declared = completed_campaign
    original_home = Path("/home/recorded-operator")
    original_root = original_home / "retained-proof"
    monkeypatch.setattr(Path, "home", lambda: Path("/home/new-operator") if different_home else original_home)
    case, stage = "crud-h2-j17", images.STAGES[0]
    directory = campaign / case / stage
    receipt_path = directory / "syft.receipt.json"
    receipt = images.read_json(receipt_path)
    receipt["command"] = [str(original_root / "tools/verified/syft"), "scan",
                          "docker-archive:" + str(original_root / "old-campaign" / case / (stage + "-bundle/image.tar"))]
    images.write_json(receipt_path, receipt)
    packed_path = directory / "syft.receipt.json.gz"
    packed_path.write_bytes(publisher.compressed(receipt_path.read_bytes()))
    report_path = directory / "assessment.json"
    report = images.read_json(report_path)
    row = next(row for row in report["retained_raw"] if row["file"] == receipt_path.name)
    row.update(sha256=images.file_digest(receipt_path), gzip_sha256=images.file_digest(packed_path),
               bytes=receipt_path.stat().st_size)
    images.write_json(report_path, report)
    retention_path = campaign / case / (stage + "-bundle") / "image-retention.json"
    retention = images.read_json(retention_path)
    retention["assessment_sha256"] = images.file_digest(report_path)
    images.write_json(retention_path, retention)
    before = {str(path.relative_to(campaign)): images.file_digest(path)
              for path in campaign.rglob("*") if path.is_file()}
    output = tmp_path / "unsafe-publication"
    with pytest.raises(images.ImageAssessmentError, match="residual host path"):
        publisher.publish(campaign, declared, output, host_prefixes=["/" "Users/fixture"])
    assert not (output / "publication.json").exists()
    for path in output.rglob("*.gz"):
        payload = gzip.decompress(path.read_bytes()).decode()
        assert str(original_root) not in payload and "/" "Users/" not in payload
        assert "retained-proof" not in payload
    safe = tmp_path / "safe-publication"
    publisher.publish(campaign, declared, safe, host_prefixes=["/" "Users/fixture", str(original_root)])
    assert images.read_json(safe / "publication.json")["status"] == "complete"
    assert before == {str(path.relative_to(campaign)): images.file_digest(path)
                      for path in campaign.rglob("*") if path.is_file()}


@pytest.mark.parametrize("value", [
    {"path": "/" "Users/other-operator/report"},
    {"nested": [{"path": "/home/current-operator/report"}]},
    {"/mnt/recorded-proof/file": "key also needs guarding"},
])
def test_residual_privacy_guard_checks_values_and_keys(value, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: Path("/home/current-operator"))
    with pytest.raises(images.ImageAssessmentError, match="residual host path"):
        publisher.require_private_paths_redacted(publisher.canonical(value), [], ["/mnt/recorded-proof"])


def test_privacy_guard_preserves_container_paths_and_complete_root_placeholders(monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: Path("/home/current-operator"))
    value = {"host": "<host-0>/tools/cache", "container": "/root/.m2/repository/g/a/1/a-1.jar",
             "image": "/app/app.jar", "purl": "pkg:maven/g/a@1"}
    publisher.require_private_paths_redacted(publisher.canonical(value), ["/mnt/recorded-proof"], ["/mnt/recorded-proof"])


def test_recorded_privacy_roots_include_foreign_cwd_tools_and_explicit_roots(tmp_path):
    images.write_json(tmp_path / "tool.receipt.json", {
        "command": ["/mnt/original-proof/tools/verified/grype", "sbom:/app/app.jar"],
        "cwd": "/mnt/original-proof/work", "checkout_root": "/opt/old-checkout"})
    roots = publisher.recorded_host_roots(tmp_path, [{"case": "crud-h2-j17"}])
    assert roots == ["/mnt/original-proof", "/opt/old-checkout"]
    for root in roots:
        with pytest.raises(images.ImageAssessmentError, match="residual host path"):
            publisher.require_private_paths_redacted(publisher.canonical({"path": root + "/file"}), [], roots)


def test_publish_findings_remain_open_and_scanner_excluded_results_not_dropped(tmp_path, completed_campaign):
    campaign, declared = completed_campaign
    for stage in images.STAGES:
        directory = campaign / "crud-h2-j17" / stage
        syft = images.read_json(directory / "syft.json")
        grype = images.read_json(directory / "grype.json")
        grype["ignoredMatches"] = [{"artifact": syft["artifacts"][0],
                                   "vulnerability": {"id": "CVE-low", "severity": "Low"},
                                   "appliedIgnoreRules": [{"namespace": "scanner-default"}]}]
        images.write_json(directory / "grype.json", grype)
        report = images.read_json(directory / "assessment.json")
        normalized = images.normalize(syft, grype, images.read_json(directory / "trivy.json"),
                                      report["image"], images.read_json(directory / "packaged.json"), stage=stage,
                                      authoritative=images.read_json(directory / "packaged-authoritative.cdx.json"),
                                      packaged_grype=images.read_json(directory / "grype-packaged.json"),
                                      extracted=images.read_json(directory / "grype-packaged-extracted.cdx.json"),
                                      bom=images.read_json(campaign / "crud-h2-j17" / (stage + "-bundle") / "retained-maven-bom.json"),
                                      resolved=images.read_json(campaign / "crud-h2-j17" / (stage + "-bundle") / "resolved-inventory.json"))
        images.write_json(directory / "findings.json", normalized["findings"])
        report.update(exit_code=1, status="complete-with-findings", findings=1,
                      retained_raw=images.retain_raw(directory))
        images.write_json(directory / "assessment.json", report)
        bundle = campaign / "crud-h2-j17" / (stage + "-bundle")
        retention = images.read_json(bundle / "image-retention.json")
        retention.update(assessment_sha256=images.file_digest(directory / "assessment.json"), assessment_exit_code=1)
        images.write_json(bundle / "image-retention.json", retention)
    summary = images.read_json(campaign / "campaign.json")
    summary.update(exit_code=1, status="complete-with-findings")
    summary["cases"][0]["stages"] = {stage: 1 for stage in images.STAGES}
    images.write_json(campaign / "campaign.json", summary)
    output = tmp_path / "published-findings"
    result = publisher.publish(campaign, declared, output, host_prefixes=["/" "Users/fixture"])
    assert result["match_observations_by_scanner"] == {"grype": 2}
    ledger = images.decode(gzip.decompress((output / "open-findings.json.gz").read_bytes()))
    assert len(ledger) == 1 and len(ledger[0]["observations"]) == 2
    assert ledger[0]["finding"]["excluded_by_scanner"] is True
    assert ledger[0]["finding"]["severity"] == "Low" and ledger[0]["disposition"].startswith("OPEN")


def restore_case_exports(campaign, case):
    for stage in images.STAGES:
        bundle = campaign / case / (stage + "-bundle")
        packed = bundle / "image.tar.gz"
        if packed.exists():
            packed.unlink()
        (bundle / "image.tar").write_bytes(b"PRIVATE-IMAGE-NOT-FOR-PUBLICATION")


@pytest.mark.parametrize("case", ["crud-h2-j17", "crud-pg-j17"])
def test_compact_case_keeps_original_reports_and_only_representative_export(completed_campaign, case):
    campaign, declared = completed_campaign
    row = next(row for row in images.read_json(declared)["cases"] if row["case"] == case)
    restore_case_exports(campaign, case)
    before = {(stage, name): images.file_digest(campaign / case / stage / name)
              for stage in images.STAGES for name in publisher.STAGE_JSON}
    driver.finalize_case(campaign / case, row, "a" * 40)
    for stage in images.STAGES:
        report, _, _ = publisher.validate_stage(campaign, row, stage, "a" * 40)
        assert report["status"] == "complete-no-matches"
        for name in publisher.STAGE_JSON:
            path = campaign / case / stage / name
            assert not path.exists() and images.evidence_digest(path) == before[(stage, name)]
        bundle = campaign / case / (stage + "-bundle")
        receipt = images.read_json(bundle / "image-retention.json")
        retained = case in driver.RUNTIME_CASES and stage == images.STAGES[1]
        assert receipt["retained"] is retained and not (bundle / "image.tar").exists()
        assert (bundle / "image.tar.gz").exists() is retained
        if not retained:
            assert "no exact image replay" in receipt["replay"]


@pytest.mark.parametrize("failure", ["scan-incomplete", "bad-original-report", "export-hash", "representative-compression"])
def test_finalization_never_deletes_exports_on_failed_validation(completed_campaign, monkeypatch, failure):
    campaign, declared = completed_campaign
    row = images.read_json(declared)["cases"][0]
    case = row["case"]
    restore_case_exports(campaign, case)
    directory = campaign / case / images.STAGES[1]
    if failure == "scan-incomplete":
        report = images.read_json(directory / "assessment.json")
        report.update(status="incomplete", exit_code=2)
        images.write_json(directory / "assessment.json", report)
    elif failure == "bad-original-report":
        (directory / "syft.json").write_bytes(b"bad")
    elif failure == "export-hash":
        (campaign / case / (images.STAGES[1] + "-bundle") / "image.tar").write_bytes(b"changed")
    else:
        original = driver.verify_gzip

        def fail(path, *args, **kwargs):
            if path.name == "image.tar.gz":
                raise images.ImageAssessmentError("compression validation failed")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(driver, "verify_gzip", fail)
    with pytest.raises((images.ImageAssessmentError, OSError)):
        driver.finalize_case(campaign / case, row, "a" * 40)
    for stage in images.STAGES:
        assert (campaign / case / (stage + "-bundle") / "image.tar").exists()
        assert (campaign / case / stage / "inventory.json").exists()


@pytest.mark.parametrize("change", ["absent-representative", "false-replay", "wrong-image", "wrong-platform",
                                    "pending-cleanup", "oversized", "wrong-size", "unretained-present"])
def test_export_retention_receipts_fail_closed(completed_campaign, change):
    campaign, declared = completed_campaign
    case = "crud-pg-j17" if change in {"false-replay", "unretained-present"} else "crud-h2-j17"
    row = next(row for row in images.read_json(declared)["cases"] if row["case"] == case)
    stage = images.STAGES[1]
    bundle = campaign / case / (stage + "-bundle")
    receipt = images.read_json(bundle / "image-retention.json")
    if change == "absent-representative":
        (bundle / "image.tar.gz").unlink()
    elif change == "false-replay":
        receipt["replay"] = "exact saved-image replay"
    elif change == "wrong-image":
        receipt["image_id"] = "sha256:" + "f" * 64
    elif change == "wrong-platform":
        receipt["platform"] = "linux/arm64"
    elif change == "pending-cleanup":
        receipt["cleanup"]["status"] = "pending"
    elif change == "oversized":
        receipt["image_tar_bytes"] = images.ARCHIVE_LIMIT + 1
    elif change == "wrong-size":
        receipt["image_tar_bytes"] += 1
        receipt["cleanup"]["verified_export_bytes"] += 1
    else:
        (bundle / "image.tar.gz").write_bytes(b"unexpected retained copy")
    images.write_json(bundle / "image-retention.json", receipt)
    with pytest.raises((images.ImageAssessmentError, OSError)):
        publisher.validate_stage(campaign, row, stage, "a" * 40)


def test_syft_root_image_archive_name_is_not_a_dependency_identity():
    source = {"name": "/" "Users/fixture/private/image.tar", "version": "sha256:" + "a" * 64,
              "id": "a" * 64, "type": "image", "metadata": {"imageID": "sha256:" + "b" * 64}}
    sanitized = publisher.redact({"source": source}, ["/" "Users/fixture"])
    assert sanitized["source"]["name"] == "<host-0>/private/image.tar"
    assert sanitized["source"]["id"] == source["id"]
    assert sanitized["source"]["version"] == source["version"]
    assert source["name"].startswith("/" "Users/fixture")
    for other_context in ({"artifacts": [source]}, {"source": {**source, "purl": "pkg:generic/example@1"}}):
        with pytest.raises(images.ImageAssessmentError):
            publisher.redact(other_context, ["/" "Users/fixture"])


def test_publisher_supports_lossless_gzip_only_reports(tmp_path, completed_campaign):
    campaign, declared = completed_campaign
    row = images.read_json(declared)["cases"][0]
    restore_case_exports(campaign, row["case"])
    driver.finalize_case(campaign / row["case"], row, "a" * 40)
    result = publisher.publish(campaign, declared, tmp_path / "compact-publication", host_prefixes=["/" "Users/fixture"])
    assert result["stage_observations"] == 60 and "other 57 exports were removed" in result["image_replay"]
    assert "completed reduced campaign" in result["image_replay"]
    assert "their availability is recorded in dated evidence" in result["image_replay"]
    assert "Original failed campaigns are preserved separately" not in result["image_replay"]


@pytest.mark.parametrize("marker", ["receipt", "file"])
def test_publication_requires_composition_validation_before_output(tmp_path, completed_campaign, marker):
    campaign, declared = completed_campaign
    if marker == "receipt":
        summary = images.read_json(campaign / "campaign.json")
        summary["composition"] = {"file": "composition.json", "sha256": "f" * 64}
        images.write_json(campaign / "campaign.json", summary)
    else:
        images.write_json(campaign / "composition.json", {})
    output = tmp_path / "invalid-composition-publication"
    with pytest.raises((ValueError, OSError)):
        publisher.publish(campaign, declared, output)
    assert not output.exists()


def test_publication_exports_fragment_failures_without_relabelling(tmp_path, completed_campaign, monkeypatch):
    from scripts import assemble_generated_image_campaign as assembler

    campaign, declared = completed_campaign
    composition = {"kind": "synthetic-export-test", "inputs": {},
                   "completion_semantics": "aggregate coverage, not successful original campaigns"}
    files = {
        "composition.json": composition,
        "composition-copy-manifest.json": {"files": []},
        "composition-inputs/first/campaign.json": {"status": "incomplete", "exit_code": 2},
        "composition-inputs/remaining/campaign.json": {"status": "partial-affected-scope", "exit_code": 2},
        "composition-inputs/tls-failure/image-build.receipt.json": {"status": "incomplete", "exit_code": 1},
    }
    for name, value in files.items():
        path = campaign / name
        path.parent.mkdir(parents=True, exist_ok=True)
        images.write_json(path, value)
    for stream, text in (("stdout", ""), ("stderr", "TLS failure at /" "Users/fixture/private/build")):
        (campaign / ("composition-inputs/tls-failure/image-build." + stream)).write_text(text)
    calls = []

    def validated(root, descriptor):
        calls.append((root, descriptor))
        return composition

    monkeypatch.setattr(assembler, "validate_composition", validated)
    output = tmp_path / "fragment-publication"
    result = publisher.publish(campaign, declared, output, host_prefixes=["/" "Users/fixture"])
    assert calls == [(campaign, declared)]
    assert result["composition"]["completion_semantics"] == composition["completion_semantics"]
    original = json.loads(gzip.decompress((output / "composition-inputs/first/campaign.json.gz").read_bytes()))
    assert original == files["composition-inputs/first/campaign.json"]
    failure = gzip.decompress((output / "composition-inputs/tls-failure/image-build.stderr.json.gz").read_bytes())
    assert b"TLS failure" in failure and b"/" b"Users/fixture" not in failure
    exports = images.read_json(output / "publication.json")["files"]
    entry = next(row for row in exports if row["file"] == "composition-inputs/tls-failure/image-build.stderr.json.gz")
    assert entry["private_original_sha256"] == images.file_digest(campaign / "composition-inputs/tls-failure/image-build.stderr")


@pytest.mark.parametrize("fault", ["hash", "size", "bomb"])
def test_gzip_verification_has_hash_and_bounded_decompression_controls(tmp_path, fault):
    data = b"x" * 1000
    path = tmp_path / "data.gz"
    path.write_bytes(publisher.compressed(data))
    size = 1000 if fault == "hash" else (1001 if fault == "size" else 8)
    checksum = "0" * 64 if fault == "hash" else images.digest(data)
    with pytest.raises(images.ImageAssessmentError):
        images.verify_gzip(path, checksum, size, limit=2048)


@pytest.mark.parametrize("kind,size", [("reports", 2 * 1024**3 + 1), ("images", 1024**3 + 1)])
def test_persistent_storage_budgets_stop_without_pruning(tmp_path, monkeypatch, kind, size):
    path = tmp_path / ("report.bin" if kind == "reports" else "image.tar.gz")
    with path.open("wb") as stream:
        stream.truncate(size)
    monkeypatch.setattr(driver.shutil, "disk_usage", lambda _: SimpleNamespace(free=40 * 1024**3))
    with pytest.raises(images.ImageAssessmentError, match="3 GiB budget"):
        driver.resource_check(tmp_path)
    assert path.exists()


def test_six_gib_working_reservation_is_not_a_guaranteed_peak(tmp_path, monkeypatch):
    monkeypatch.setattr(driver.shutil, "disk_usage", lambda _: SimpleNamespace(free=25 * 1024**3))
    driver.resource_check(tmp_path)
    with pytest.raises(images.ImageAssessmentError, match="disk safety"):
        driver.resource_check(tmp_path, between_cases=True)


def test_long_command_storage_monitor_kills_owned_process_and_retains_logs(tmp_path, monkeypatch):
    process = SimpleNamespace(pid=123, poll=lambda: None,
                              wait=Mock(side_effect=[subprocess.TimeoutExpired("scanner", 2), 0]))
    monkeypatch.setattr(images.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(images.os, "killpg", kill)
    monkeypatch.setattr(images, "STORAGE_GUARD", Mock(side_effect=[None, images.ImageAssessmentError("disk floor")]))
    with pytest.raises(images.ImageAssessmentError, match="disk floor"):
        images.run_tool(["scanner"], directory=tmp_path, label="storage-stop", env={}, offline=False)
    kill.assert_called_once_with(123, images.signal.SIGKILL)
    receipt = images.read_json(tmp_path / "storage-stop.receipt.json")
    assert receipt["failure"] == "storage safety stop"
    start, end = publisher.validate_span(receipt)
    assert end >= start and receipt["elapsed_seconds"] >= 0
    assert (tmp_path / "storage-stop.stderr").exists()


def test_base_inspection_explicitly_selects_target_platform(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(driver, "docker", lambda command, *_: calls.append(command) or
                        b'[{"Os":"linux","Architecture":"amd64"}]')
    driver.inspect("base", tmp_path, "inspect")
    assert calls == [["image", "inspect", "--platform", "linux/amd64", "base"]]
    monkeypatch.setattr(driver, "docker", lambda *_: b'[{"Os":"linux","Architecture":"arm64"}]')
    with pytest.raises(images.ImageAssessmentError, match="platform mismatch"):
        driver.inspect("base", tmp_path, "inspect-wrong")


@pytest.mark.parametrize("fault", ["missing", "duplicate", "hash-missing", "hash-duplicate", "hash-mismatch", "classifier"])
def test_retained_bom_packaged_hash_integrity_fails_closed(packaged, fault):
    rows = images.jar_inventory(*packaged)[0]
    component = {"group": "g", "name": "a", "version": "1", "purl": "pkg:maven/g/a@1?type=jar",
                 "hashes": [{"alg": "SHA-256", "content": rows[0]["sha256"]}]}
    bom = {"bomFormat": "CycloneDX", "components": [component]}
    if fault == "missing":
        component["purl"] = "pkg:maven/g/other@1?type=jar"
        component["name"] = "other"
    elif fault == "duplicate":
        bom["components"].append(copy.deepcopy(component))
    elif fault == "hash-missing":
        component["hashes"] = []
    elif fault == "hash-duplicate":
        component["hashes"] *= 2
    elif fault == "hash-mismatch":
        component["hashes"][0]["content"] = "f" * 64
    else:
        component["purl"] += "&classifier=other"
    with pytest.raises(images.ImageAssessmentError):
        images.validate_packaged_bom(rows, bom)


def test_retained_bom_hash_match_and_explicit_bootstrap_gap(packaged):
    rows = images.jar_inventory(*packaged)[0]
    bom = {"bomFormat": "CycloneDX", "components": [{
        "group": "g", "name": "a", "version": "1", "purl": "pkg:maven/g/a@1?type=jar",
        "hashes": [{"alg": "SHA-256", "content": rows[0]["sha256"]}]}]}
    rows.append({"group": "org.springframework.boot", "artifact": "spring-boot", "version": "1",
                 "filename": "spring-boot-1.jar", "sha256": "b" * 64})
    bom["components"].append({"group": "org.springframework.boot", "name": "spring-boot", "version": "1",
                              "purl": "pkg:maven/org.springframework.boot/spring-boot@1?type=jar",
                              "hashes": [{"alg": "SHA-256", "content": "b" * 64}]})
    rows.append({"group": "org.springframework.boot", "artifact": "spring-boot-jarmode-tools", "version": "1",
                 "filename": "spring-boot-jarmode-tools-1.jar", "sha256": "a" * 64, "origin": "packaging-bootstrap"})
    result = images.validate_packaged_bom(rows, bom)
    assert result[0]["status"] == "matched-retained-bom-sha256"
    assert result[2]["status"] == "not-covered-packaging-bootstrap"


def test_actual_utc_spans_are_retained_without_fixed_test_clock(tmp_path, monkeypatch):
    monkeypatch.setattr(images.subprocess, "Popen", Mock(return_value=SimpleNamespace(wait=lambda **_: 0)))
    before = images.utc_now()
    images.run_tool(["command"], directory=tmp_path, label="timed", env={}, offline=False)
    after = images.utc_now()
    receipt = images.read_json(tmp_path / "timed.receipt.json")
    assert before <= receipt["started_at_utc"] <= receipt["ended_at_utc"] <= after
    publisher.validate_span(receipt)
    with pytest.raises(images.ImageAssessmentError):
        publisher.validate_span({**receipt, "started_at_utc": after, "ended_at_utc": before})


@pytest.mark.parametrize("same_sha", [False, True])
def test_freeze_requires_generator_and_collector_equal_actual_head(tmp_path, monkeypatch, same_sha):
    declaration = tmp_path / "declaration.json"
    declaration.write_text("{}")
    generator = "a" * 40
    collector = generator if same_sha else "b" * 40
    approval = {"campaign_approved": True, "generator_sha": generator, "collector_sha": collector,
                "coverage_sha256": images.file_digest(declaration)}
    calls = []

    def git(command, **_):
        calls.append(command)
        if command[1] == "rev-parse":
            return SimpleNamespace(stdout=collector + "\n")
        if command[1] == "status":
            return SimpleNamespace(stdout="")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(images.subprocess, "run", git)
    if same_sha:
        images.check_freeze(approval, declaration, generator)
    else:
        with pytest.raises(images.ImageAssessmentError, match="equal actual clean frozen HEAD"):
            images.check_freeze(approval, declaration, generator)
    assert [command[1] for command in calls] == ["rev-parse", "status"]


def test_publication_budget_failure_never_writes_complete_marker(tmp_path, completed_campaign, monkeypatch):
    campaign, declaration = completed_campaign
    output = tmp_path / "over-budget-publication"

    def budget(*_args, **kwargs):
        if kwargs.get("pending_bytes"):
            raise images.ImageAssessmentError("persistent budget reached")

    monkeypatch.setattr(publisher, "resource_check", budget)
    with pytest.raises(images.ImageAssessmentError, match="budget"):
        publisher.publish(campaign, declaration, output, host_prefixes=["/" "Users/fixture"])
    assert not (output / "publication.json").exists()
    assert (campaign / "crud-h2-j17" / images.STAGES[0] / "syft.json").exists()


def test_observed_first_stage_formats_preserve_originals_and_expose_inferred_gaps(reports):
    syft, grype, trivy, image, _ = reports
    del grype["ignoredMatches"]
    syft["artifacts"][0]["version"] = "1:2.42-4ubuntu2.5"
    library = syft["artifacts"][2]
    library["purl"] = "pkg:maven/inferred.wrong/a@1"
    library["locations"] = [{"path": "/workspace/target/a.jar", "accessPath": "/workspace/target/a.jar:BOOT-INF/lib/a-1.jar"}]
    trivy["Results"][0]["Packages"] = [{"ID": "libc@1:2.42-4ubuntu2.5", "Name": "libc", "Version": "2.42",
                                        "Release": "4ubuntu2.5", "Epoch": 1}]
    trivy["Results"][0]["Vulnerabilities"] = [{"VulnerabilityID": "CVE-format", "PkgID": "libc@1:2.42-4ubuntu2.5",
                                               "PkgName": "libc", "InstalledVersion": "1:2.42-4ubuntu2.5"}]
    trivy["Results"].append({"Class": "lang-pkgs", "Type": "jar", "Packages": [
        {"Name": "inferred.wrong:a", "Version": "0", "Identifier": {"PURL": "pkg:maven/inferred.wrong/a@0"},
         "FilePath": "workspace/target/a.jar/BOOT-INF/lib/a-1.jar"}]})
    original = copy.deepcopy(reports)
    result = normalized(reports, images.STAGES[0])
    assert reports == original
    assert {gap["scanner"] for gap in result["coordinate-gaps"]} == {"syft", "trivy"}
    assert result["cache-scanner-gaps"][0]["sha256"] == image["cache_jar_inventory"][0]["sha256"]
    assert result["findings"][0]["version"] == "1:2.42-4ubuntu2.5"


@pytest.mark.parametrize("change", ["missing", "duplicate", "hash", "version", "purl", "image", "malformed",
                                    "extracted-missing", "extracted-wrong", "extracted-duplicate", "source", "finding"])
def test_authoritative_supplement_rejects_incomplete_or_changed_packages(reports, change):
    supplement = supplemental(reports)
    sbom, grype, extracted = (supplement[k] for k in ("authoritative", "packaged_grype", "extracted"))
    component = sbom["components"][0]
    if change == "missing":
        sbom["components"].clear()
    elif change == "duplicate":
        sbom["components"].append(copy.deepcopy(component))
    elif change == "hash":
        component["hashes"][0]["content"] = "0" * 64
    elif change == "version":
        component["version"] = "2"
    elif change == "purl":
        component["purl"] = "pkg:maven/wrong/a@1"
    elif change == "image":
        sbom["metadata"]["properties"][0]["value"] = "sha256:" + "0" * 64
    elif change == "malformed":
        sbom["components"] = None
    elif change == "extracted-missing":
        extracted["components"].clear()
    elif change == "extracted-wrong":
        extracted["components"][0].update(group="wrong", purl="pkg:maven/wrong/a@1")
    elif change == "extracted-duplicate":
        extracted["components"].append(copy.deepcopy(extracted["components"][0]))
    elif change == "source":
        grype["source"]["type"] = "image"
    else:
        grype["matches"] = [{"artifact": {"id": "wrong", "type": "java-archive", "name": "a", "version": "2",
                                           "purl": component["purl"]}, "vulnerability": {"id": "CVE-wrong"}}]
    with pytest.raises((images.ImageAssessmentError, ValueError)):
        images.normalize(*reports, stage=images.STAGES[1], **supplement)


@pytest.mark.parametrize("ignored", [False, True])
def test_authoritative_findings_are_additive_and_scanner_exclusions_preserved(reports, ignored):
    supplement = supplemental(reports)
    component = supplement["authoritative"]["components"][0]
    match = {"artifact": {"id": "authoritative", "type": "java-archive", "name": "a", "version": "1",
                           "purl": component["purl"]}, "vulnerability": {"id": "CVE-authoritative", "severity": "Low"}}
    if ignored:
        match["appliedIgnoreRules"] = [{"namespace": "scanner-default"}]
    supplement["packaged_grype"]["ignoredMatches" if ignored else "matches"] = [match]
    reports[1]["matches"] = [{"artifact": reports[0]["artifacts"][0], "vulnerability": {"id": "CVE-original"}}]
    result = images.normalize(*reports, stage=images.STAGES[1], **supplement)
    assert {finding["id"] for finding in result["findings"]} == {"CVE-original", "CVE-authoritative"}
    authoritative = next(f for f in result["findings"] if f["id"] == "CVE-authoritative")
    assert authoritative["excluded_by_scanner"] is ignored
    assert authoritative["scanner"] == "grype-packaged-authoritative"
    assert authoritative["purl"] == component["purl"]


@pytest.mark.parametrize("change", [None, "jar-hash", "packages", "retained-hash", "bootstrap-manifest", "bootstrap-pom"])
def test_sbom_reuses_hash_verified_components_and_binds_bootstrap_to_actual_pom_manifest(tmp_path, change):
    manifest = ("Automatic-Module-Name: spring.boot.jarmode.tools\r\n"
                "Implementation-Title: Spring Boot Jarmode Tools\r\nImplementation-Version: 4.1.1\r\n")
    if change == "bootstrap-manifest":
        manifest = manifest.replace("4.1.1", "4.1.0")
    boot_library = zipped({"META-INF/maven/org.springframework.boot/spring-boot/pom.properties":
                           b"groupId=org.springframework.boot\nartifactId=spring-boot\nversion=4.1.1\n"})
    bootstrap = zipped({"META-INF/MANIFEST.MF": manifest.encode()})
    jar = zipped({"BOOT-INF/lib/spring-boot-4.1.1.jar": boot_library,
                  "BOOT-INF/lib/spring-boot-jarmode-tools-4.1.1.jar": bootstrap})
    resolved = [{"group": "org.springframework.boot", "artifact": "spring-boot", "version": "4.1.1",
                 "type": "jar", "scope": "compile", "classifier": ""}]
    policy = {"packaged_policy": "passed", "resolved_policy": "passed", "dependency_policy": "retained",
              "packaged_libraries": ["spring-boot-4.1.1.jar", "spring-boot-jarmode-tools-4.1.1.jar"]}
    rows, _ = images.jar_inventory(jar, policy, resolved)
    bom = {"bomFormat": "CycloneDX", "components": [{"type": "library", "group": "org.springframework.boot",
           "name": "spring-boot", "version": "4.1.1", "purl": "pkg:maven/org.springframework.boot/spring-boot@4.1.1",
           "hashes": [{"alg": "SHA-256", "content": images.digest(boot_library)}]}]}
    pom = ("<project><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId>"
           "<version>4.1.1</version></parent></project>")
    if change == "bootstrap-pom":
        pom = pom.replace("4.1.1", "4.1.0")
    source = tmp_path / "source.tar"
    source.write_bytes(tarred({"pom.xml": pom.encode()}))
    image = {"image_id": "sha256:" + "a" * 64, "jar_sha256": images.digest(jar)}
    if change == "jar-hash":
        rows[1]["sha256"] = "0" * 64
    elif change == "packages":
        rows.pop()
    elif change == "retained-hash":
        bom["components"][0]["hashes"][0]["content"] = "0" * 64
    if change:
        with pytest.raises(images.ImageAssessmentError):
            images.packaged_sbom(jar, rows, bom, source, image)
    else:
        original = copy.deepcopy(bom)
        sbom, receipts = images.packaged_sbom(jar, rows, bom, source, image)
        assert len(images.validate_authoritative_sbom(sbom, rows, image)) == 2
        assert bom == original
        images.validate_bootstrap_provenance(receipts, rows, source)
        receipts[0]["manifest"] = receipts[0]["manifest"].replace("4.1.1", "4.1.0")
        with pytest.raises(images.ImageAssessmentError):
            images.validate_bootstrap_provenance(receipts, rows, source)


@pytest.mark.parametrize("change", ["input-hash", "extracted-package", "coordinate-gap", "bootstrap-receipt", "build-coverage"])
def test_publication_revalidates_supplemental_semantics_not_just_file_hashes(tmp_path, completed_campaign, change):
    campaign, declaration = completed_campaign
    directory = campaign / "crud-h2-j17" / images.STAGES[0]
    if change == "input-hash":
        name = "packaged-authoritative.cdx.json"
        value = images.read_json(directory / name)
        value["components"][0]["hashes"][0]["content"] = "0" * 64
    elif change == "extracted-package":
        name = "grype-packaged-extracted.cdx.json"
        value = images.read_json(directory / name)
        value["components"] = []
    elif change == "coordinate-gap":
        name, value = "coordinate-gaps.json", []
    elif change == "build-coverage":
        name, value = "build-bom-coverage.json", []
    else:
        name, value = "bootstrap-provenance.json", [{"filename": "not-actual.jar"}]
    images.write_json(directory / name, value)
    report = images.read_json(directory / "assessment.json")
    report["retained_raw"] = images.retain_raw(directory)
    images.write_json(directory / "assessment.json", report)
    output = tmp_path / "rejected-supplement"
    with pytest.raises(images.ImageAssessmentError):
        publisher.publish(campaign, declaration, output)
    assert not (output / "publication.json").exists()


@pytest.mark.parametrize("change", ["missing-cache", "hash", "bytes"])
def test_cache_physical_extraction_must_remain_complete(reports, change):
    image = reports[3]
    if change == "missing-cache":
        image["cache_jar_inventory"].clear()
    elif change == "hash":
        image["cache_jar_inventory"][0]["sha256"] = "invalid"
    else:
        image["cache_jar_inventory"][0]["bytes"] = 0
    with pytest.raises(images.ImageAssessmentError, match="physical extraction incomplete"):
        normalized(reports, images.STAGES[0])


@pytest.mark.parametrize("change", [None, "missing-extractor", "coordinate", "version", "path", "classifier",
                                    "cache-hash", "bom-hash", "hash-missing", "duplicate", "missing-resolved",
                                    "missing-bom", "truncated-cache", "optional-scope", "duplicate-resolved", "wrong-feed"])
def test_declared_build_test_libraries_cannot_pass_as_optional_plugin_gaps(reports, change):
    syft, grype, trivy, image, _ = reports
    supplement = supplemental(reports)
    build = build_inputs(reports)
    path = "/root/.m2/repository/g/test-support/2/test-support-2.jar"
    image["cache_jars"].append(path)
    image["cache_jar_inventory"].append({"path": path, "sha256": "e" * 64, "bytes": 200})
    component = {"type": "library", "group": "g", "name": "test-support", "version": "2",
                 "purl": "pkg:maven/g/test-support@2?type=jar", "hashes": [{"alg": "SHA-256", "content": "e" * 64}]}
    build["bom"]["components"].append(component)
    build["resolved"].append({"group": "g", "artifact": "test-support", "version": "2", "type": "jar", "scope": "test"})
    package = {"Name": "g:test-support", "Version": "2", "FilePath": path.lstrip("/"),
               "Identifier": {"PURL": "pkg:maven/g/test-support@2"}}
    trivy["Results"].append({"Class": "lang-pkgs", "Type": "jar", "Packages": [package]})
    if change == "missing-extractor":
        trivy["Results"].pop()
    elif change == "coordinate":
        package["Identifier"]["PURL"] = "pkg:maven/wrong/test-support@2"
    elif change == "version":
        package["Version"] = "3"
    elif change == "path":
        package["FilePath"] = "unverified/test-support-2.jar"
    elif change == "classifier":
        package["Identifier"]["PURL"] += "?classifier=other"
    elif change == "cache-hash":
        image["cache_jar_inventory"][-1]["sha256"] = "f" * 64
    elif change == "bom-hash":
        component["hashes"][0]["content"] = "f" * 64
    elif change == "hash-missing":
        component["hashes"] = []
    elif change == "duplicate":
        build["bom"]["components"].append(copy.deepcopy(component))
    elif change == "missing-resolved":
        build["resolved"].pop()
    elif change == "missing-bom":
        build["bom"]["components"].pop()
    elif change == "truncated-cache":
        image["cache_jars"].pop()
        image["cache_jar_inventory"].pop()
    elif change == "optional-scope":
        build["resolved"][-1]["scope"] = "plugin"
    elif change == "duplicate-resolved":
        build["resolved"].append(copy.deepcopy(build["resolved"][-1]))
    elif change == "wrong-feed":
        trivy["Results"][-1]["Type"] = "not-jar"
    if change:
        with pytest.raises(images.ImageAssessmentError):
            images.normalize(syft, grype, trivy, image, reports[4], stage=images.STAGES[0], **supplement, **build)
    else:
        original = copy.deepcopy(reports)
        result = images.normalize(syft, grype, trivy, image, reports[4], stage=images.STAGES[0], **supplement, **build)
        assert reports == original
        assert len(result["build-bom-coverage"]) == 2
        test = next(row for row in result["build-bom-coverage"] if row["scope"] == "test")
        assert test["extractor"] == "trivy" and test["sha256"] == "e" * 64
        assert result["cache-scanner-gaps"][0]["per_app_bom"] is True


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_provenance_json_rejects_nonfinite_numbers(token):
    with pytest.raises(images.ImageAssessmentError, match="malformed JSON"):
        images.decode('{"identity":' + token + "}")


def oci_runtime_fixture(tmp_path, packaged):
    bundle = tmp_path / "oci-bundle"
    bundle.mkdir()
    archive, jar_path, _ = saved_image(bundle, packaged[0])
    with tarfile.open(archive) as saved:
        config = saved.extractfile("config.json").read()
        layer = saved.extractfile("layer.tar").read()
    compressed = gzip.compress(layer, mtime=0)
    config_id, layer_id = images.digest(config), images.digest(compressed)
    manifest = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                           "config": {"digest": "sha256:" + config_id, "size": len(config)},
                           "layers": [{"digest": "sha256:" + layer_id, "size": len(compressed)}]}).encode()
    manifest_id = images.digest(manifest)
    descriptor = {"digest": "sha256:" + manifest_id, "size": len(manifest),
                  "mediaType": "application/vnd.oci.image.manifest.v1+json", "platform": {"architecture": "amd64", "os": "linux"}}
    tag = "edgeforge-image-proof-fixture:crud-h2-j17-final"
    files = {"index.json": json.dumps({"schemaVersion": 2, "manifests": [descriptor]}).encode(),
             "manifest.json": json.dumps([{"Config": "blobs/sha256/" + config_id, "RepoTags": [tag],
                                           "Layers": ["blobs/sha256/" + layer_id]}]).encode(),
             "blobs/sha256/" + manifest_id: manifest, "blobs/sha256/" + config_id: config,
             "blobs/sha256/" + layer_id: compressed}
    archive.write_bytes(tarred(files))
    (bundle / "image-config.json").write_bytes(config)
    provenance = {"generator_sha": images.REUSE_SHA, "collector_sha": images.REUSE_SHA, "jar_path": jar_path,
                  "files": {"image.tar": images.file_digest(archive)}}
    images.write_json(bundle / "provenance.json", provenance)
    actual, _ = images.image_archive(archive, jar_path=jar_path, stage=images.STAGES[1])
    report = {"image": actual, "status": "complete-with-findings", "exit_code": 1}
    inspected = {"Id": "sha256:" + manifest_id, "Descriptor": descriptor, "Os": "linux", "Architecture": "amd64",
                 "RootFS": {"Layers": actual["rootfs"]}, "Config": images.decode(config)["config"]}
    return bundle, report, inspected, files


def test_exact_oci_export_binds_manifest_separately_from_config(tmp_path, packaged):
    bundle, report, inspected, _ = oci_runtime_fixture(tmp_path, packaged)
    binding, manifest = images.runtime_export_binding(bundle, report)
    assert binding["manifest_digest"] == inspected["Id"] != binding["assessed_config_id"]
    images.validate_runtime_inspection(binding, inspected, images.read_json(bundle / "image-config.json"), manifest)


@pytest.mark.parametrize("change", ["export-hash", "index-platform", "index-digest", "multiple-manifests", "compressed-layer", "foreign-tag"])
def test_runtime_export_rejects_unbound_bytes_or_foreign_tag(tmp_path, packaged, change):
    bundle, report, _, files = oci_runtime_fixture(tmp_path, packaged)
    index = images.decode(files["index.json"])
    if change == "index-platform":
        index["manifests"][0]["platform"]["architecture"] = "arm64"
    elif change == "index-digest":
        index["manifests"][0]["digest"] = "sha256:" + "0" * 64
    elif change == "multiple-manifests":
        index["manifests"].append(copy.deepcopy(index["manifests"][0]))
    elif change == "compressed-layer":
        saved = images.decode(files["manifest.json"])
        path = saved[0]["Layers"][0]
        data = bytearray(files[path])
        data[4] = 1  # Same decompressed layer, but not the manifest's compressed bytes.
        files[path] = bytes(data)
    elif change == "foreign-tag":
        saved = images.decode(files["manifest.json"])
        saved[0]["RepoTags"] = ["foreign.example/private:latest"]
        files["manifest.json"] = json.dumps(saved).encode()
    files["index.json"] = json.dumps(index).encode()
    (bundle / "image.tar").write_bytes(tarred(files))
    if change != "export-hash":
        provenance = images.read_json(bundle / "provenance.json")
        provenance["files"]["image.tar"] = images.file_digest(bundle / "image.tar")
        images.write_json(bundle / "provenance.json", provenance)
    else:
        (bundle / "image.tar").write_bytes(b"tampered")
    with pytest.raises((images.ImageAssessmentError, KeyError)):
        images.runtime_export_binding(bundle, report)


@pytest.mark.parametrize("change", ["manifest", "image-id", "platform", "rootfs", "entrypoint", "user", "health"])
def test_loaded_local_image_inspection_must_match_exact_export(tmp_path, packaged, change):
    bundle, report, inspected, _ = oci_runtime_fixture(tmp_path, packaged)
    binding, manifest = images.runtime_export_binding(bundle, report)
    if change == "manifest":
        inspected["Descriptor"]["digest"] = "sha256:" + "0" * 64
    elif change == "image-id":
        inspected["Id"] = "sha256:" + "0" * 64
    elif change == "platform":
        inspected["Architecture"] = "arm64"
    elif change == "rootfs":
        inspected["RootFS"]["Layers"] = []
    elif change == "entrypoint":
        inspected["Config"]["Entrypoint"] = ["sh"]
    elif change == "user":
        inspected["Config"]["User"] = "root"
    else:
        inspected["Config"]["Healthcheck"] = {"Test": ["NONE"]}
    with pytest.raises(images.ImageAssessmentError, match="identity mismatch"):
        images.validate_runtime_inspection(binding, inspected, images.read_json(bundle / "image-config.json"), manifest)


@pytest.mark.parametrize("change", ["Image", "User", "Entrypoint", "Healthcheck"])
def test_created_container_identity_failure_never_starts_bytes(tmp_path, monkeypatch, change):
    binding = runtime_binding_fixture("sha256:" + "a" * 64)
    state = {"Image": binding["docker_image_id"], "Config": copy.deepcopy(binding["default_launch"])}
    if change == "Image":
        state["Image"] = "sha256:" + "0" * 64
    else:
        state["Config"][change] = {"User": "root", "Entrypoint": ["sh"], "Healthcheck": {"Test": ["NONE"]}}[change]
    commands = []

    def docker(command, *_args, **_kwargs):
        commands.append(command)
        return json.dumps([state]).encode() if command[0] == "inspect" else b""

    monkeypatch.setattr(driver, "docker", docker)
    outcome = driver.startup(binding, tmp_path, "owned-only")
    assert outcome["status"] == "incomplete"
    assert not any(command[0] == "start" for command in commands)
    assert commands[-1] == ["rm", "-f", "owned-only"]


def test_free_space_preflight_excludes_existing_tool_cache_and_prior_campaigns(tmp_path, monkeypatch):
    monkeypatch.setattr(driver.shutil, "disk_usage", lambda _: SimpleNamespace(free=27 * 1024**3))
    with monkeypatch.context() as context:
        context.setattr(type(tmp_path), "rglob", Mock(side_effect=AssertionError("must not total parent evidence")))
        driver.resource_check(tmp_path, between_cases=True, free_only=True)
    output = tmp_path / "new-campaign"
    output.mkdir()
    driver.resource_check(output, between_cases=True)
    monkeypatch.setattr(driver.shutil, "disk_usage", lambda _: SimpleNamespace(free=25 * 1024**3))
    with pytest.raises(images.ImageAssessmentError, match="disk safety"):
        driver.resource_check(tmp_path, between_cases=True, free_only=True)


@pytest.mark.parametrize("change", [None, "tag-exists", "retargeted-tag"])
def test_runtime_load_uses_verified_owned_tag_then_immutable_local_id(tmp_path, packaged, monkeypatch, change):
    bundle, report, inspected, _ = oci_runtime_fixture(tmp_path, packaged)
    directory = tmp_path / "case"
    (directory / images.STAGES[1]).mkdir(parents=True)
    images.write_json(directory / images.STAGES[1] / "assessment.json", report)
    commands, started = [], []

    def docker(command, where, label, **_):
        commands.append(command)
        if command[:2] == ["image", "ls"]:
            return b"existing-task-tag" if change == "tag-exists" else b""
        if command[:2] == ["image", "inspect"]:
            value = copy.deepcopy(inspected)
            if change == "retargeted-tag":
                value["Descriptor"]["digest"] = "sha256:" + "0" * 64
            images.write_json(where / (label + ".stdout"), [value])
            return json.dumps([value]).encode()
        return b""

    def startup(row, binding, *_):
        started.append(binding)
        assert binding["docker_image_id"] == inspected["Id"] != binding["assessed_config_id"]
        return {"status": "passed"}

    monkeypatch.setattr(driver, "docker", docker)
    monkeypatch.setattr(driver, "representative_startup", startup)
    outcome = driver.run_runtime({"case": images.REUSE_CASE}, bundle, directory, "owned", "c" * 40)
    assert outcome["status"] == ("passed" if change is None else "incomplete")
    assert len(started) == int(change is None)
    assert not any(command[0] == "pull" for command in commands)
    if change == "tag-exists":
        assert not any(command[:2] in (["image", "load"], ["image", "rm"]) for command in commands)
    else:
        assert commands[-1][:2] == ["image", "rm"]


def prepare_reuse_fixture(completed_campaign, tmp_path, monkeypatch):
    campaign, declaration = completed_campaign
    row = images.read_json(declaration)["cases"][0]
    restore_case_exports(campaign, images.REUSE_CASE)
    for stage in images.STAGES:
        directory = campaign / images.REUSE_CASE / stage
        bundle = campaign / images.REUSE_CASE / (stage + "-bundle")
        (bundle / "image-retention.json").unlink()
        provenance = images.read_json(directory / "provenance.json")
        provenance.update(generator_sha=images.REUSE_SHA, collector_sha=images.REUSE_SHA, jar_path="/app/app.jar")
        images.write_json(directory / "provenance.json", provenance)
        images.write_json(bundle / "provenance.json", provenance)
        syft, grype, trivy = (images.read_json(directory / (name + ".json")) for name in ("syft", "grype", "trivy"))
        grype["matches"] = [{"artifact": syft["artifacts"][0], "vulnerability": {"id": "CVE-unit-fixture", "severity": "Low"}}]
        images.write_json(directory / "grype.json", grype)
        report = images.read_json(directory / "assessment.json")
        normalized = images.normalize(syft, grype, trivy, report["image"], images.read_json(directory / "packaged.json"), stage=stage,
                                      authoritative=images.read_json(directory / "packaged-authoritative.cdx.json"),
                                      extracted=images.read_json(directory / "grype-packaged-extracted.cdx.json"),
                                      packaged_grype=images.read_json(directory / "grype-packaged.json"),
                                      bom=images.read_json(bundle / "retained-maven-bom.json"), resolved=images.read_json(bundle / "resolved-inventory.json"))
        images.write_json(directory / "findings.json", normalized["findings"])
        report.update(generator_sha=images.REUSE_SHA, collector_sha=images.REUSE_SHA, findings=1,
                      status="complete-with-findings", exit_code=1, retained_raw=images.retain_raw(directory))
        images.write_json(directory / "assessment.json", report)
    failed = campaign / images.REUSE_CASE / "runtime.json"
    images.write_json(failed, {"status": "incomplete", "failure": "unit fixture config ID not addressable"})
    prior = images.read_json(campaign / "campaign.json")
    prior.update(generator_sha=images.REUSE_SHA, collector_sha=images.REUSE_SHA, campaign_complete=False,
                 status="incomplete", exit_code=2, cases=[{"case": images.REUSE_CASE, "stages": {stage: 1 for stage in images.STAGES}}])
    images.write_json(campaign / "campaign.json", prior)
    setup = tmp_path / "tool-setup-fixture"
    (setup / "verified").mkdir(parents=True)
    report = images.read_json(campaign / images.REUSE_CASE / images.STAGES[0] / "assessment.json")
    images.write_json(setup / "verified/tools.json", report["tools"])
    database = images.read_json(campaign / images.REUSE_CASE / images.STAGES[0] / "databases.json")
    monkeypatch.setattr(driver, "db_receipt", lambda *_: database)
    monkeypatch.setattr(driver, "image_archive", lambda path, **_: (
        images.read_json(path.parent.parent / path.parent.name.removesuffix("-bundle") / "assessment.json")["image"], b"unit-fixture"))
    approved = {"generator_sha": "a" * 40, "collector_sha": "a" * 40, "runtime_helper_sha": "a" * 40,
                "coverage_sha256": images.file_digest(declaration), "continuation_approved": True,
                "reuse_case": images.REUSE_CASE, "reuse_generator_sha": images.REUSE_SHA,
                "prior_campaign_sha256": images.file_digest(campaign / "campaign.json")}
    return campaign, declaration, row, setup, approved


@pytest.mark.parametrize("change", [None, "campaign-hash", "source", "db", "raw", "export", "old-runtime", "tools", "case", "helper"])
def test_first_case_reuse_is_strict_and_never_rewrites_failed_source(tmp_path, completed_campaign, monkeypatch, change):
    prior, declaration, row, setup, approved = prepare_reuse_fixture(completed_campaign, tmp_path, monkeypatch)
    source = prior / images.REUSE_CASE
    if change == "campaign-hash":
        approved["prior_campaign_sha256"] = "0" * 64
    elif change == "source":
        path = source / images.STAGES[0] / "assessment.json"
        report = images.read_json(path)
        report["generator_sha"] = "c" * 40
        images.write_json(path, report)
    elif change == "db":
        monkeypatch.setattr(driver, "db_receipt", lambda *_: {"changed": True})
    elif change == "raw":
        (source / images.STAGES[0] / "syft.json").write_text("tampered")
    elif change == "export":
        (source / (images.STAGES[0] + "-bundle") / "image.tar").write_text("tampered")
    elif change == "old-runtime":
        images.write_json(source / "runtime.json", {"status": "passed"})
    elif change == "tools":
        images.write_json(setup / "verified/tools.json", {"changed": True})
    elif change == "case":
        approved["reuse_case"] = "crud-pg-j17"
    elif change == "helper":
        approved["runtime_helper_sha"] = images.REUSE_SHA
    before = {str(path.relative_to(prior)): images.file_digest(path) for path in prior.rglob("*") if path.is_file()}
    output = tmp_path / "new-continuation"
    output.mkdir()
    docker = Mock()
    monkeypatch.setattr(driver, "docker", docker)
    if change:
        with pytest.raises(images.ImageAssessmentError):
            driver.copy_first_case(prior, output, row, approved, setup)
    else:
        lineage = driver.copy_first_case(prior, output, row, approved, setup)
        summary = {"generator_sha": "a" * 40, "coverage_sha256": images.file_digest(declaration), "continuation": lineage}
        publisher.validate_continuation(output, summary)
        for stage in images.STAGES:
            assert (output / images.REUSE_CASE / stage / "assessment.json").read_bytes() == (source / stage / "assessment.json").read_bytes()
        assert (output / images.REUSE_CASE / "prior-runtime/runtime.json").read_bytes() == (source / "runtime.json").read_bytes()
    assert before == {str(path.relative_to(prior)): images.file_digest(path) for path in prior.rglob("*") if path.is_file()}
    docker.assert_not_called()


@pytest.mark.parametrize("change", [None, "lineage-hash", "case-source", "missing-case", "old-relabel", "runtime-helper"])
def test_mixed_source_complete_publication_preserves_original_scans_and_lineage(tmp_path, completed_campaign, monkeypatch, change):
    prior, declaration, row, setup, approved = prepare_reuse_fixture(completed_campaign, tmp_path, monkeypatch)
    output = tmp_path / "continued"
    output.mkdir()
    lineage = driver.copy_first_case(prior, output, row, approved, setup)
    declared = images.read_json(declaration)
    for case in declared["cases"]:
        if case["case"] != images.REUSE_CASE:
            shutil.copytree(prior / case["case"], output / case["case"])
    directory = output / images.REUSE_CASE
    final = images.read_json(directory / images.STAGES[1] / "assessment.json")
    config = images.read_json(directory / (images.STAGES[1] + "-bundle") / "image-config.json")
    write_runtime_fixture(directory, final["image"], config, "a" * 40, generator_sha=images.REUSE_SHA)
    driver.finalize_case(directory, row, images.REUSE_SHA, runtime_helper_sha="a" * 40)
    summary = {"generator_sha": "a" * 40, "collector_sha": "a" * 40, "runtime_helper_sha": "a" * 40,
               "generator_shas": sorted(["a" * 40, images.REUSE_SHA]), "continuation": lineage,
               "coverage_sha256": images.file_digest(declaration), "campaign_complete": True, "exit_code": 1,
               "status": "complete-with-findings", "started_at_utc": final["ended_at_utc"], "ended_at_utc": images.utc_now(),
               "cases": [{"case": case["case"], "generator_sha": images.REUSE_SHA if case["case"] == images.REUSE_CASE else "a" * 40,
                          "collector_sha": images.REUSE_SHA if case["case"] == images.REUSE_CASE else "a" * 40,
                          "stages": {stage: int(case["case"] == images.REUSE_CASE) for stage in images.STAGES}}
                         for case in declared["cases"]]}
    contract = images.packaged_contract(output, declared, "a" * 40, summary=summary)
    assert contract["generator_shas"] == sorted(["a" * 40, images.REUSE_SHA])
    assert contract["cases"][0]["generator_sha"] == contract["cases"][0]["collector_sha"] == images.REUSE_SHA
    images.write_json(output / "packaged-inventories.json", contract)
    if change == "lineage-hash":
        summary["continuation"]["prior_campaign_sha256"] = "0" * 64
    elif change == "case-source":
        summary["cases"][1]["generator_sha"] = images.REUSE_SHA
    elif change == "missing-case":
        summary["cases"].pop()
    elif change == "old-relabel":
        summary["cases"][0].update(generator_sha="a" * 40, collector_sha="a" * 40)
    elif change == "runtime-helper":
        runtime = images.read_json(directory / "runtime.json")
        runtime["runtime_helper_sha"] = images.REUSE_SHA
        images.write_json(directory / "runtime.json", runtime)
    images.write_json(output / "campaign.json", summary)
    publication = tmp_path / "publication"
    if change:
        with pytest.raises(images.ImageAssessmentError):
            publisher.publish(output, declaration, publication)
        assert not (publication / "publication.json").exists()
    else:
        result = publisher.publish(output, declaration, publication, host_prefixes=["/" "Users/fixture"])
        assert result["stage_observations"] == 60 and result["generator_shas"] == contract["generator_shas"]
        assert (publication / images.REUSE_CASE / "prior-runtime/runtime.json.gz").exists()


@pytest.mark.parametrize("runtime_status", ["passed", "incomplete"])
def test_continuation_runs_first_runtime_only_then_29_new_builds_and_58_scans(tmp_path, declaration, monkeypatch, runtime_status):
    declared, approved = tmp_path / "declared.json", tmp_path / "approved.json"
    images.write_json(declared, declaration)
    images.write_json(approved, {"generator_sha": "a" * 40, "collector_sha": "a" * 40, "continuation_approved": True})
    monkeypatch.setattr(driver, "check_freeze", Mock())
    monkeypatch.setattr(driver, "resource_check", Mock())
    monkeypatch.setattr(driver, "db_receipt", Mock())
    monkeypatch.setattr(driver, "local_docker_boundary", lambda *_: {"effective_endpoint": "unix:///fixture.sock"})
    monkeypatch.setattr(driver, "docker", Mock(return_value=b""))
    monkeypatch.setattr(driver, "refresh_bases", Mock(return_value={}))
    lineage = {"case": images.REUSE_CASE, "generator_sha": images.REUSE_SHA, "collector_sha": images.REUSE_SHA,
               "runtime_helper_sha": "a" * 40}
    monkeypatch.setattr(driver, "copy_first_case", Mock(return_value=lineage))
    runtime = Mock(return_value={"status": runtime_status})
    monkeypatch.setattr(driver, "run_runtime", runtime)
    built, scanned = [], []

    def build(row, destination, **kwargs):
        assert kwargs["sha"] == kwargs["collector_sha"] == "a" * 40
        built.append(row["case"])
        destination.mkdir()

    def scan(*_, **kwargs):
        scanned.append((kwargs["case"], kwargs["stage"]))
        return 0

    monkeypatch.setattr(driver, "build_case", build)
    monkeypatch.setattr(driver, "collect", scan)
    monkeypatch.setattr(driver, "finalize_case", Mock())
    monkeypatch.setattr(driver, "packaged_contract", Mock(return_value={"unit-fixture": True}))
    output = tmp_path / "continuation"
    code = driver.campaign(output, declaration=declared, approval=approved, tool_setup=tmp_path,
                           baseline=tmp_path, prior_campaign=tmp_path / "preserved-old")
    summary = images.read_json(output / "campaign.json")
    assert summary["cases"][0]["generator_sha"] == summary["cases"][0]["collector_sha"] == images.REUSE_SHA
    assert summary["cases"][0]["scans_reused"] is True
    if runtime_status == "passed":
        assert code == 1 and len(built) == 29 and len(scanned) == 58
        assert images.REUSE_CASE not in built and all(case != images.REUSE_CASE for case, _ in scanned)
        assert summary["campaign_complete"] is True and summary["generator_shas"] == sorted(["a" * 40, images.REUSE_SHA])
    else:
        assert code == 2 and built == scanned == [] and summary["campaign_complete"] is False


def test_continuation_below_26_gib_stops_before_output_or_docker(tmp_path, declaration, monkeypatch):
    declared, approved = tmp_path / "declared.json", tmp_path / "approved.json"
    images.write_json(declared, declaration)
    images.write_json(approved, {"generator_sha": "a" * 40, "continuation_approved": True})
    monkeypatch.setattr(driver, "check_freeze", Mock())
    monkeypatch.setattr(driver.shutil, "disk_usage", lambda _: SimpleNamespace(free=25 * 1024**3))
    docker = Mock()
    monkeypatch.setattr(driver, "docker", docker)
    output = tmp_path / "must-not-start"
    with pytest.raises(images.ImageAssessmentError, match="disk safety"):
        driver.campaign(output, declaration=declared, approval=approved, tool_setup=tmp_path,
                        baseline=tmp_path, prior_campaign=tmp_path / "old")
    assert not output.exists()
    docker.assert_not_called()


@pytest.fixture
def completed_capacity_case(completed_campaign, tmp_path, monkeypatch):
    prior, declaration, row, setup, approved = prepare_reuse_fixture(completed_campaign, tmp_path, monkeypatch)
    old_helper = images.CAPACITY_RUNTIME_SHA
    approved.update(generator_sha=old_helper, collector_sha=old_helper, runtime_helper_sha=old_helper)
    capacity = tmp_path / "capacity-stop"
    capacity.mkdir()
    started = images.utc_now()
    lineage = driver.copy_first_case(prior, capacity, row, approved, setup)
    directory = capacity / images.REUSE_CASE
    final = images.read_json(directory / images.STAGES[1] / "assessment.json")
    config = images.read_json(directory / (images.STAGES[1] + "-bundle") / "image-config.json")
    write_runtime_fixture(directory, final["image"], config, old_helper, generator_sha=images.REUSE_SHA)
    driver.finalize_case(directory, row, images.REUSE_SHA, runtime_helper_sha=old_helper)
    receipt = {"generator_sha": old_helper, "collector_sha": old_helper, "runtime_helper_sha": old_helper,
               "generator_shas": [images.REUSE_SHA], "coverage_sha256": images.file_digest(declaration),
               "continuation": lineage, "status": "incomplete", "exit_code": 2, "campaign_complete": False,
               "failure": "disk safety floor reached; stop without pruning other resources",
               "started_at_utc": started, "ended_at_utc": images.utc_now(),
               "cases": [{"case": images.REUSE_CASE, "generator_sha": images.REUSE_SHA, "collector_sha": images.REUSE_SHA,
                          "stages": {stage: 1 for stage in images.STAGES}, "scans_reused": True}]}
    images.write_json(capacity / "campaign.json", receipt)
    approved.update(generator_sha="a" * 40, collector_sha="a" * 40, runtime_helper_sha="a" * 40,
                    continuation_approved=False, capacity_continuation_approved=True,
                    reuse_collector_sha=images.REUSE_SHA, reuse_runtime_helper_sha=old_helper,
                    prior_campaign_sha256=images.file_digest(capacity / "campaign.json"))
    return capacity, declaration, row, setup, approved


@pytest.mark.parametrize("change", [None, "hash", "approval-helper", "approval-collector", "approval-coverage", "source",
                                  "db", "tools", "raw-gzip", "retention", "export", "runtime", "lineage", "time", "symlink",
                                  "parent-helper", "parent-source", "parent-lineage", "parent-case", "parent-failure"])
def test_completed_capacity_copy_failclosed_and_original_bytes_immutable(tmp_path, completed_capacity_case, monkeypatch, change):
    prior, declaration, row, setup, approved = completed_capacity_case
    source = prior / images.REUSE_CASE
    if change == "hash":
        approved["prior_campaign_sha256"] = "0" * 64
    elif change == "approval-helper":
        approved["reuse_runtime_helper_sha"] = "a" * 40
    elif change == "approval-collector":
        approved["reuse_collector_sha"] = "a" * 40
    elif change == "approval-coverage":
        approved["coverage_sha256"] = "0" * 64
    elif change in ("source", "runtime", "time"):
        path = source / (images.STAGES[0] + "/assessment.json" if change == "source" else "runtime.json")
        value = images.read_json(path)
        value[{"source": "generator_sha", "runtime": "runtime_helper_sha", "time": "started_at_utc"}[change]] = (
            "a" * 40 if change != "time" else "2000-01-01T00:00:00Z")
        images.write_json(path, value)
    elif change == "db":
        monkeypatch.setattr(driver, "db_receipt", lambda *_: {"changed": True})
    elif change == "tools":
        images.write_json(setup / "verified/tools.json", {"changed": True})
    elif change == "raw-gzip":
        (source / images.STAGES[0] / "syft.json.gz").write_bytes(b"tampered")
    elif change == "retention":
        (source / (images.STAGES[0] + "-bundle") / "image-retention.json").unlink()
    elif change == "export":
        (source / (images.STAGES[1] + "-bundle") / "image.tar.gz").write_bytes(b"tampered")
    elif change == "lineage":
        images.write_json(source / "prior-runtime/runtime.json", {"status": "passed"})
    elif change == "symlink":
        (source / "unsafe-link").symlink_to(source / "runtime.json")
    elif change and change.startswith("parent-"):
        path = prior / "campaign.json"
        value = images.read_json(path)
        if change == "parent-helper":
            value["runtime_helper_sha"] = "a" * 40
        elif change == "parent-source":
            value["generator_sha"] = "a" * 40
        elif change == "parent-lineage":
            value["continuation"]["collector_sha"] = "a" * 40
        elif change == "parent-case":
            value["cases"].append(copy.deepcopy(value["cases"][0]))
        else:
            value["failure"] = "a different non-capacity failure"
        images.write_json(path, value)
        approved["prior_campaign_sha256"] = images.file_digest(path)
    before = {str(path.relative_to(prior)): images.file_digest(path) for path in prior.rglob("*") if path.is_file()}
    output = tmp_path / "capacity-copy"
    output.mkdir()
    operations = [Mock(side_effect=AssertionError("completed first case must never execute again")) for _ in range(4)]
    for name, mock in zip(("docker", "collect", "run_runtime", "finalize_case"), operations, strict=True):
        monkeypatch.setattr(driver, name, mock)
    if change:
        with pytest.raises((images.ImageAssessmentError, OSError)):
            driver.copy_completed_first_case(prior, output, row, approved, setup)
        assert not (output / images.REUSE_CASE).exists()
    else:
        lineage, capacity = driver.copy_completed_first_case(prior, output, row, approved, setup)
        assert lineage == images.read_json(prior / "campaign.json")["continuation"]
        assert capacity["runtime_helper_sha"] == images.CAPACITY_RUNTIME_SHA
        for path in source.rglob("*"):
            if path.is_file():
                assert (output / images.REUSE_CASE / path.relative_to(source)).read_bytes() == path.read_bytes()
        assert (output / "prior-campaign.json").read_bytes() == (prior / "prior-campaign.json").read_bytes()
        assert (output / "capacity-prior-campaign.json").read_bytes() == (prior / "campaign.json").read_bytes()
    assert before == {str(path.relative_to(prior)): images.file_digest(path) for path in prior.rglob("*") if path.is_file()}
    for mock in operations:
        mock.assert_not_called()


@pytest.mark.parametrize("change", [None, "parent-hash", "helper-relabel", "source-relabel", "missing-case", "copied-runtime", "runtime-span"])
def test_capacity_publication_mixed_actual_helpers_sources_and_spans(tmp_path, completed_capacity_case, declaration, reports, monkeypatch, change):
    prior, declared_path, row, setup, approved = completed_capacity_case
    started = images.utc_now()
    fresh = tmp_path / "fresh-cases"
    fresh.mkdir()
    output, _ = completed_campaign.__wrapped__(fresh, declaration, reports, monkeypatch)
    shutil.rmtree(output / images.REUSE_CASE)  # Synthetic new case is not evidence; replace with immutable completed copy.
    lineage, capacity = driver.copy_completed_first_case(prior, output, row, approved, setup)
    summary = images.read_json(output / "campaign.json")
    summary.update(collector_sha="a" * 40, runtime_helper_sha="a" * 40,
                   generator_shas=sorted(["a" * 40, images.REUSE_SHA]),
                   runtime_helper_shas=sorted(["a" * 40, images.CAPACITY_RUNTIME_SHA]),
                   continuation=lineage, capacity_continuation=capacity, started_at_utc=started,
                   ended_at_utc=images.utc_now(), exit_code=1, status="complete-with-findings")
    for item in summary["cases"]:
        reused = item["case"] == images.REUSE_CASE
        item.update(generator_sha=images.REUSE_SHA if reused else "a" * 40,
                    collector_sha=images.REUSE_SHA if reused else "a" * 40,
                    runtime_helper_sha=(images.CAPACITY_RUNTIME_SHA if reused else "a" * 40)
                    if item["case"] in images.RUNTIME_CASES else None)
        if reused:
            item.update(stages={stage: 1 for stage in images.STAGES}, scans_reused=True, runtime_reused=True)
    contract = images.packaged_contract(output, declaration, "a" * 40, summary=summary)
    assert contract["cases"][0]["runtime_helper_sha"] == images.CAPACITY_RUNTIME_SHA
    assert contract["cases"][0]["generator_sha"] == images.REUSE_SHA
    images.write_json(output / "packaged-inventories.json", contract)
    if change == "parent-hash":
        summary["capacity_continuation"]["prior_campaign_sha256"] = "0" * 64
    elif change == "helper-relabel":
        summary["cases"][0]["runtime_helper_sha"] = "a" * 40
    elif change == "source-relabel":
        summary["cases"][0]["generator_sha"] = "a" * 40
    elif change == "missing-case":
        summary["cases"].pop()
    elif change == "copied-runtime":
        with (output / images.REUSE_CASE / "runtime-start.receipt.json").open("ab") as stream:
            stream.write(b" ")
    elif change == "runtime-span":
        summary["started_at_utc"] = images.read_json(prior / "campaign.json")["started_at_utc"]
    images.write_json(output / "campaign.json", summary)
    publication = tmp_path / "published-capacity"
    if change:
        with pytest.raises(images.ImageAssessmentError):
            publisher.publish(output, declared_path, publication)
        assert not publication.exists()
    else:
        result = publisher.publish(output, declared_path, publication, host_prefixes=["/" "Users/fixture"])
        assert result["stage_observations"] == 60
        assert result["runtime_helpers_by_case"][images.REUSE_CASE] == images.CAPACITY_RUNTIME_SHA
        assert result["runtime_helper_shas"] == sorted(["a" * 40, images.CAPACITY_RUNTIME_SHA])
        assert result["generator_shas"] == sorted(["a" * 40, images.REUSE_SHA])
        for name in ("prior-campaign.json", "capacity-prior-campaign.json", images.REUSE_CASE + "/reuse.json",
                     images.REUSE_CASE + "/completed-case-copy.json", images.REUSE_CASE + "/prior-runtime/runtime.json"):
            assert (publication / (name + ".gz")).exists()


def test_capacity_continuation_runs_exactly_remaining_29_builds_58_scans_and_two_runtimes(tmp_path, declaration, monkeypatch):
    declared, approved = tmp_path / "declared.json", tmp_path / "approved.json"
    images.write_json(declared, declaration)
    images.write_json(approved, {"generator_sha": "a" * 40, "collector_sha": "a" * 40, "capacity_continuation_approved": True})
    for name in ("check_freeze", "resource_check", "db_receipt", "docker"):
        monkeypatch.setattr(driver, name, Mock())
    monkeypatch.setattr(driver, "local_docker_boundary", lambda *_: {"effective_endpoint": "unix:///fixture.sock"})
    monkeypatch.setattr(driver, "refresh_bases", Mock(return_value={}))
    lineage = {"case": images.REUSE_CASE, "generator_sha": images.REUSE_SHA, "collector_sha": images.REUSE_SHA,
               "runtime_helper_sha": images.CAPACITY_RUNTIME_SHA}
    copied = Mock(return_value=(lineage, {**lineage, "prior_campaign_sha256": "f" * 64}))
    monkeypatch.setattr(driver, "copy_completed_first_case", copied)
    monkeypatch.setattr(driver, "copy_first_case", Mock(side_effect=AssertionError("wrong continuation mode")))
    built, scanned, finalized, runtimes = [], [], [], []

    def build(row, destination, **kwargs):
        assert kwargs["sha"] == kwargs["collector_sha"] == "a" * 40 and row["case"] != images.REUSE_CASE
        built.append(row["case"])
        destination.mkdir()

    def scan(*_, **kwargs):
        assert kwargs["case"] != images.REUSE_CASE
        scanned.append((kwargs["case"], kwargs["stage"]))
        return 0

    def finalize(destination, row, sha):
        assert row["case"] != images.REUSE_CASE and sha == "a" * 40
        finalized.append(row["case"])

    def runtime(row, *_):
        assert row["case"] != images.REUSE_CASE
        runtimes.append(row["case"])
        return {"status": "passed"}

    for name, function in (("build_case", build), ("collect", scan), ("finalize_case", finalize), ("run_runtime", runtime)):
        monkeypatch.setattr(driver, name, function)
    monkeypatch.setattr(driver, "packaged_contract", Mock(return_value={}))
    output = tmp_path / "continued-capacity"
    assert driver.campaign(output, declaration=declared, approval=approved, tool_setup=tmp_path, baseline=tmp_path,
                           prior_campaign=tmp_path / "old-capacity", capacity_continuation=True) == 1
    expected = {row["case"] for row in declaration["cases"]} - {images.REUSE_CASE}
    assert set(built) == set(finalized) == expected and len(built) == len(finalized) == 29
    assert set(scanned) == {(case, stage) for case in expected for stage in images.STAGES} and len(scanned) == 58
    assert set(runtimes) == set(images.RUNTIME_CASES) - {images.REUSE_CASE} and len(runtimes) == 2
    first = images.read_json(output / "campaign.json")["cases"][0]
    assert first["runtime_reused"] and first["runtime_helper_sha"] == images.CAPACITY_RUNTIME_SHA


def classifier_inputs(reports, provenance=None):
    observed = copy.deepcopy(reports)
    build = build_inputs(observed)
    for artifact, checksum in (("kafka-clients", "e" * 64), ("kafka-server-common", "f" * 64)):
        purl = f"pkg:maven/org.apache.kafka/{artifact}@4.2.1?classifier=test&type=jar"
        build["bom"]["components"].append({"type": "library", "group": "org.apache.kafka", "name": artifact,
                                           "version": "4.2.1", "purl": purl, "hashes": [{"alg": "SHA-256", "content": checksum}]})
        build["resolved"].append({"group": "org.apache.kafka", "artifact": artifact, "version": "4.2.1",
                                  "type": "jar", "classifier": "test", "scope": "test"})
        path = f"/root/.m2/repository/org/apache/kafka/{artifact}/4.2.1/{artifact}-4.2.1-test.jar"
        observed[3]["cache_jars"].append(path)
        observed[3]["cache_jar_inventory"].append({"path": path, "sha256": checksum, "bytes": 100})
    provenance = provenance or {"generator_sha": "a" * 40, "collector_sha": "a" * 40,
                                "files": {name: "b" * 64 for name in ("source.tar", "retained-maven-bom.json", "resolved-inventory.json")}}
    sbom = images.build_classifier_sbom(build["bom"], build["resolved"], observed[3], provenance)
    extracted = copy.deepcopy(sbom)
    for component in extracted["components"]:
        component.pop("hashes")
    grype = {"descriptor": copy.deepcopy(observed[1]["descriptor"]), "matches": [],
             "source": {"type": "sbom-file", "target": images.CLASSIFIER_JSON[0]}}
    return observed, build, {"provenance": provenance, "classifiers": sbom,
                             "classifier_extracted": extracted, "classifier_grype": grype}


def classifier_finding(sbom):
    component = sbom["components"][0]
    return {"artifact": {"id": "classifier-only", "type": "java-archive", "name": component["name"],
                         "version": component["version"], "purl": component["purl"]},
            "vulnerability": {"id": "CVE-classifier-only", "severity": "High"}}


@pytest.mark.parametrize("change", [None, "missing", "empty-extraction", "duplicate-extraction", "lost-classifier", "version",
                                  "input-hash", "bom-hash", "cache-hash", "scope", "source", "source-hash", "wrong-source",
                                  "resolved-scope", "missing-resolved", "missing-component", "malformed", "db", "tool-version"])
def test_build_classifier_authority_is_hash_scope_source_and_extraction_bound(reports, change):
    observed, build, supplement = classifier_inputs(reports)
    if change == "missing":
        supplement["classifiers"] = None
    elif change == "empty-extraction":
        supplement["classifier_extracted"]["components"] = []
    elif change == "duplicate-extraction":
        supplement["classifier_extracted"]["components"].append(copy.deepcopy(supplement["classifier_extracted"]["components"][0]))
    elif change == "lost-classifier":
        supplement["classifier_extracted"]["components"][0]["purl"] = supplement["classifier_extracted"]["components"][0]["purl"].replace("classifier=test&", "")
    elif change == "version":
        supplement["classifier_extracted"]["components"][0]["version"] = "other"
    elif change == "input-hash":
        supplement["classifiers"]["components"][0]["hashes"][0]["content"] = "0" * 64
    elif change == "bom-hash":
        build["bom"]["components"][-1]["hashes"][0]["content"] = "0" * 64
    elif change == "cache-hash":
        observed[3]["cache_jar_inventory"][-1]["sha256"] = "0" * 64
    elif change == "scope":
        supplement["classifiers"]["components"][0]["scope"] = "excluded"
    elif change == "source":
        supplement["provenance"]["generator_sha"] = "c" * 40
    elif change == "source-hash":
        supplement["provenance"]["files"]["source.tar"] = "c" * 64
    elif change == "wrong-source":
        supplement["classifier_grype"]["source"]["target"] = "packaged-authoritative.cdx.json"
    elif change == "resolved-scope":
        build["resolved"][-1]["scope"] = "plugin"
    elif change == "missing-resolved":
        build["resolved"].pop()
    elif change == "missing-component":
        build["bom"]["components"].pop()
    elif change == "malformed":
        supplement["classifier_grype"]["matches"] = None
    elif change == "db":
        supplement["classifier_grype"]["descriptor"]["db"]["status"]["built"] = "other snapshot"
    elif change == "tool-version":
        supplement["classifier_grype"]["descriptor"]["version"] = "other"
    if change:
        with pytest.raises((images.ImageAssessmentError, ValueError)):
            images.normalize(*observed, stage=images.STAGES[0], **supplemental(observed), **build, **supplement)
    else:
        before = copy.deepcopy(observed)
        supplement["classifier_grype"]["matches"] = [classifier_finding(supplement["classifiers"])]
        result = images.normalize(*observed, stage=images.STAGES[0], **supplemental(observed), **build, **supplement)
        assert observed == before
        covered = [row for row in result["build-bom-coverage"] if row["classifier"]]
        assert len(covered) == 2 and all(row["scope"] == "test" and row["extractor"] == "grype-build-classifier-authoritative" for row in covered)
        assert len(result["findings"]) == 1
        assert result["findings"][0]["classifier"] == result["findings"][0]["scope"] == "test"
        assert result["findings"][0]["purl"].endswith("?classifier=test&type=jar")


@pytest.mark.parametrize("outcome", ["zero", "finding", "malformed", "empty", "timeout"])
def test_collector_classifier_only_findings_and_required_failures_affect_exit(tmp_path, declaration, reports, monkeypatch, outcome):
    observed, build, _ = classifier_inputs(reports)
    bundle, output = tmp_path / "classifier-bundle", tmp_path / "classifier-output"
    bundle.mkdir()
    row = next(row for row in declaration["cases"] if row["case"] == "kafka-h2-j17")
    for name in ("Dockerfile", "source.tar", "input.tar", "generation.json", "image.tar"):
        (bundle / name).write_bytes(b"synthetic classifier test input")
    bases = [{"image_id": "sha256:" + "a" * 64, "platform": "linux/amd64", "repo_digests": ["base@sha256:" + "b" * 64]}] * 2
    for name, data in (("base-images.json", bases), ("resolved-inventory.json", build["resolved"]),
                       ("retained-maven-bom.json", build["bom"]), ("dependency-policy.json", {})):
        images.write_json(bundle / name, data)
    provenance = {"generator_sha": "a" * 40, "collector_sha": "a" * 40, "case": row["case"], "profile": row["profile"],
                  "stage": images.STAGES[0], "jar_path": "/workspace/target/app.jar",
                  "files": {path.name: images.file_digest(path) for path in bundle.iterdir()}}
    images.write_json(bundle / "provenance.json", provenance)
    declared, approval = tmp_path / "declaration.json", tmp_path / "approval.json"
    images.write_json(declared, declaration)
    images.write_json(approval, {})
    monkeypatch.setattr(images, "check_freeze", Mock())
    monkeypatch.setattr(images, "db_receipt", lambda *_: {"same": "snapshot"})
    monkeypatch.setattr(images, "verify_tools", lambda *_, **__: {"verified": True})
    monkeypatch.setattr(images, "image_archive", lambda *_, **__: (observed[3], b"synthetic jar"))
    monkeypatch.setattr(images, "jar_inventory", lambda *_: (observed[4], []))
    package = supplemental(observed)
    monkeypatch.setattr(images, "packaged_sbom", lambda *_: (package["authoritative"], []))
    labels = []

    def scanner(command, *, directory, label, env):
        assert env["GRYPE_DB_AUTO_UPDATE"] == "false" and env["SYFT_JAVA_USE_NETWORK"] == "false"
        labels.append(label)
        for name, data in zip(("syft", "grype", "trivy"), observed[:3], strict=True):
            images.write_json(directory / (name + ".json"), data)
        if label == "grype-packaged":
            images.write_json(directory / "grype-packaged.json", package["packaged_grype"])
            images.write_json(directory / "grype-packaged-extracted.cdx.json", package["extracted"])
        if label == "grype-build-classifiers":
            if outcome == "timeout":
                raise images.ImageAssessmentError("required scanner timeout")
            sbom = images.read_json(directory / images.CLASSIFIER_JSON[0])
            report = {"descriptor": copy.deepcopy(observed[1]["descriptor"]), "source": {"type": "sbom-file", "target": images.CLASSIFIER_JSON[0]},
                      "matches": [classifier_finding(sbom)] if outcome == "finding" else None if outcome == "malformed" else []}
            extracted = copy.deepcopy(sbom)
            if outcome == "empty":
                extracted["components"] = []
            images.write_json(directory / images.CLASSIFIER_JSON[1], report)
            images.write_json(directory / images.CLASSIFIER_JSON[2], extracted)

    monkeypatch.setattr(images, "run_tool", scanner)
    expected = {"zero": 0, "finding": 1, "malformed": 2, "empty": 2, "timeout": 2}[outcome]
    assert images.collect(bundle, output, case=row["case"], stage=images.STAGES[0], declaration=declared,
                          approval=approval, tools=tmp_path, grype_db=tmp_path, trivy_cache=tmp_path) == expected
    assert labels[-1] == "grype-build-classifiers" and len(labels) == 5
    report = images.read_json(output / "assessment.json")
    assert report["exit_code"] == expected and (output / "grype.json.gz").exists()
    if outcome == "finding":
        assert report["findings"] == 1 and images.read_json(output / "findings.json")[0]["id"] == "CVE-classifier-only"


def rebind_completed_fixture_case(campaign, case, sha):
    """Create synthetic source/findings bindings, never touch retained campaign evidence."""
    for stage in images.STAGES:
        directory, bundle = campaign / case / stage, campaign / case / (stage + "-bundle")
        report = images.read_json(directory / "assessment.json")
        provenance = images.read_json(bundle / "provenance.json")
        provenance.update(generator_sha=sha, collector_sha=sha, jar_path="/app/app.jar" if stage == images.STAGES[1] else "/workspace/target/app.jar")
        images.write_json(bundle / "provenance.json", provenance)
        images.write_json(directory / "provenance.json", provenance)
        syft, grype, trivy = (images.read_json(directory / (name + ".json")) for name in ("syft", "grype", "trivy"))
        grype["matches"] = [{"artifact": syft["artifacts"][0], "vulnerability": {"id": "CVE-cohort-fixture", "severity": "Low"}}]
        images.write_json(directory / "grype.json", grype)
        result = images.normalize(syft, grype, trivy, report["image"], images.read_json(directory / "packaged.json"), stage=stage,
                                  authoritative=images.read_json(directory / "packaged-authoritative.cdx.json"),
                                  packaged_grype=images.read_json(directory / "grype-packaged.json"),
                                  extracted=images.read_json(directory / "grype-packaged-extracted.cdx.json"),
                                  bom=images.read_json(bundle / "retained-maven-bom.json"), resolved=images.read_json(bundle / "resolved-inventory.json"))
        images.write_json(directory / "findings.json", result["findings"])
        report.update(generator_sha=sha, collector_sha=sha, findings=1, exit_code=1, status="complete-with-findings",
                      retained_raw=images.retain_raw(directory))
        images.write_json(directory / "assessment.json", report)
        retention = images.read_json(bundle / "image-retention.json")
        retention.update(generator_sha=sha, assessment_exit_code=1, assessment_sha256=images.file_digest(directory / "assessment.json"))
        images.write_json(bundle / "image-retention.json", retention)
    if case in images.RUNTIME_CASES:
        write_runtime_fixture(campaign / case, report["image"], images.read_json(bundle / "image-config.json"), sha)


@pytest.fixture
def completed_kafka_cohort(completed_capacity_case, tmp_path, declaration, reports, monkeypatch):
    capacity, declared, row, setup, approved = completed_capacity_case
    started = images.utc_now()
    fresh = tmp_path / "old-ee-cohort"
    fresh.mkdir()
    prior, _ = completed_campaign.__wrapped__(fresh, declaration, reports, monkeypatch)
    shutil.rmtree(prior / images.REUSE_CASE)
    lineage, capacity_lineage = driver.copy_completed_first_case(capacity, prior, row, approved, setup)
    for item in declaration["cases"]:
        case = item["case"]
        if case in images.KAFKA_REUSE_CASES and case != images.REUSE_CASE or case == "kafka-h2-j17":
            rebind_completed_fixture_case(prior, case, images.KAFKA_PRIOR_SHA)
        elif case not in images.KAFKA_REUSE_CASES:
            shutil.rmtree(prior / case)
    failed_path = prior / "kafka-h2-j17" / images.STAGES[0] / "assessment.json"
    failed = images.read_json(failed_path)
    failed.update(status="incomplete", exit_code=2,
                  failure="required per-app application/test coordinate vulnerability-extractor coverage incomplete")
    images.write_json(failed_path, failed)
    cases = [{**binding, "stages": {stage: 1 for stage in images.STAGES}} for binding in images.kafka_reuse_bindings()]
    cases[0].update(scans_reused=True, runtime_reused=True)
    cases.append({"case": "kafka-h2-j17", "generator_sha": images.KAFKA_PRIOR_SHA, "collector_sha": images.KAFKA_PRIOR_SHA,
                  "runtime_helper_sha": None, "stages": {images.STAGES[0]: 2}})
    summary = {"generator_sha": images.KAFKA_PRIOR_SHA, "collector_sha": images.KAFKA_PRIOR_SHA,
               "runtime_helper_sha": images.KAFKA_PRIOR_SHA, "generator_shas": sorted([images.REUSE_SHA, images.KAFKA_PRIOR_SHA]),
               "runtime_helper_shas": sorted([images.CAPACITY_RUNTIME_SHA, images.KAFKA_PRIOR_SHA]),
               "cases": cases, "continuation": lineage, "capacity_continuation": capacity_lineage,
               "coverage_sha256": images.file_digest(declared), "started_at_utc": started, "ended_at_utc": images.utc_now(),
               "campaign_complete": False, "status": "incomplete", "exit_code": 2,
               "failure": "required scan/inventory incomplete; diagnose before affected-only repair"}
    images.write_json(prior / "campaign.json", summary)
    approved.update(capacity_continuation_approved=False, kafka_continuation_approved=True,
                    prior_campaign_sha256=images.file_digest(prior / "campaign.json"), reuse_cases=images.kafka_reuse_bindings())
    return prior, declared, setup, approved


@pytest.mark.parametrize("change", [None, "hash", "approval-source", "approval-helper", "approval-case", "source", "helper",
                                  "db", "tools", "raw", "retention", "span", "lineage", "incomplete", "wrong-case", "failed-report"])
def test_kafka_cohort_copy_preserves_nine_cases_both_runtimes_and_failure(tmp_path, completed_kafka_cohort, monkeypatch, change):
    prior, declared, setup, approved = completed_kafka_cohort
    if change == "hash":
        approved["prior_campaign_sha256"] = "0" * 64
    elif change == "approval-source":
        approved["reuse_cases"][1]["generator_sha"] = "a" * 40
    elif change == "approval-helper":
        approved["reuse_cases"][-1]["runtime_helper_sha"] = "a" * 40
    elif change == "approval-case":
        approved["reuse_cases"].pop()
    elif change == "db":
        monkeypatch.setattr(driver, "db_receipt", lambda *_: {"different": "snapshot"})
    elif change == "tools":
        images.write_json(setup / "verified/tools.json", {"different": "tools"})
    elif change == "raw":
        (prior / images.KAFKA_REUSE_CASES[1] / images.STAGES[0] / "grype.json.gz").write_bytes(b"tampered")
    elif change == "retention":
        (prior / images.KAFKA_REUSE_CASES[1] / (images.STAGES[0] + "-bundle") / "image-retention.json").unlink()
    elif change == "lineage":
        images.write_json(prior / images.REUSE_CASE / "prior-runtime/runtime.json", {"status": "passed"})
    elif change in ("incomplete", "wrong-case"):
        path = prior / "campaign.json"
        summary = images.read_json(path)
        if change == "incomplete":
            summary["cases"][1]["stages"][images.STAGES[1]] = 2
        else:
            summary["cases"][1]["case"] = "kafka-pg-j21"
        images.write_json(path, summary)
        approved["prior_campaign_sha256"] = images.file_digest(path)
    elif change:
        path = (prior / "passthrough-pg-j21/runtime.json" if change == "helper" else
                prior / ("kafka-h2-j17" if change == "failed-report" else images.KAFKA_REUSE_CASES[1]) / images.STAGES[0] / "assessment.json")
        value = images.read_json(path)
        key = {"source": "generator_sha", "helper": "runtime_helper_sha", "span": "started_at_utc", "failed-report": "status"}[change]
        value[key] = "2000-01-01T00:00:00Z" if change == "span" else "complete-with-findings" if change == "failed-report" else "a" * 40
        images.write_json(path, value)
    before = {str(path.relative_to(prior)): images.file_digest(path) for path in prior.rglob("*") if path.is_file()}
    output = tmp_path / "kafka-cohort-copy"
    output.mkdir()
    for name in ("build_case", "collect", "run_runtime", "finalize_case", "docker"):
        monkeypatch.setattr(driver, name, Mock(side_effect=AssertionError("no completed case may execute again")))
    if change:
        with pytest.raises((images.ImageAssessmentError, OSError)):
            driver.copy_kafka_cohort(prior, output, images.read_json(declared), approved, setup)
        assert not (output / images.REUSE_CASE).exists()
    else:
        receipt, lineage = driver.copy_kafka_cohort(prior, output, images.read_json(declared), approved, setup)
        assert lineage["reuse_cases"] == images.kafka_reuse_bindings()
        for case in images.KAFKA_REUSE_CASES:
            for path in (prior / case).rglob("*"):
                if path.is_file():
                    assert (output / path.relative_to(prior)).read_bytes() == path.read_bytes()
        assert receipt == images.read_json(prior / "campaign.json")
        assert (output / "prior-kafka-failure" / images.STAGES[0] / "assessment.json").read_bytes() == (
            prior / "kafka-h2-j17" / images.STAGES[0] / "assessment.json").read_bytes()
        assert not (output / images.REUSE_CASE / "kafka-cohort-copy.json").exists()
    assert before == {str(path.relative_to(prior)): images.file_digest(path) for path in prior.rglob("*") if path.is_file()}


@pytest.mark.parametrize("change", [None, "parent-hash", "helper-relabel", "source-relabel", "missing-case", "copied-bytes", "span"])
def test_kafka_full_publication_verifies_three_sources_helpers_and_nested_spans(tmp_path, completed_kafka_cohort, declaration, reports, monkeypatch, change):
    prior, declared, setup, approved = completed_kafka_cohort
    started = images.utc_now()
    fresh = tmp_path / "new-remaining-cases"
    fresh.mkdir()
    output, _ = completed_campaign.__wrapped__(fresh, declaration, reports, monkeypatch)
    for case in images.KAFKA_REUSE_CASES:
        shutil.rmtree(output / case)
    receipt, lineage = driver.copy_kafka_cohort(prior, output, declaration, approved, setup)
    summary = images.read_json(output / "campaign.json")
    summary.update(collector_sha="a" * 40, runtime_helper_sha="a" * 40,
                   generator_shas=sorted(["a" * 40, images.REUSE_SHA, images.KAFKA_PRIOR_SHA]),
                   runtime_helper_shas=sorted(["a" * 40, images.CAPACITY_RUNTIME_SHA, images.KAFKA_PRIOR_SHA]),
                   continuation=receipt["continuation"], capacity_continuation=receipt["capacity_continuation"], kafka_continuation=lineage,
                   started_at_utc=started, ended_at_utc=images.utc_now(), exit_code=1, status="complete-with-findings")
    reused = {binding["case"]: binding for binding in images.kafka_reuse_bindings()}
    for item in summary["cases"]:
        if item["case"] in reused:
            item.update(reused[item["case"]], stages={stage: 1 for stage in images.STAGES})
        else:
            item.update(generator_sha="a" * 40, collector_sha="a" * 40,
                        runtime_helper_sha="a" * 40 if item["case"] in images.RUNTIME_CASES else None)
    contract = images.packaged_contract(output, declaration, "a" * 40, summary=summary)
    images.write_json(output / "packaged-inventories.json", contract)
    if change == "parent-hash":
        summary["kafka_continuation"]["prior_campaign_sha256"] = "0" * 64
    elif change == "helper-relabel":
        summary["cases"][8]["runtime_helper_sha"] = "a" * 40
    elif change == "source-relabel":
        summary["cases"][1]["generator_sha"] = "a" * 40
    elif change == "missing-case":
        summary["cases"].pop()
    elif change == "copied-bytes":
        with (output / "passthrough-pg-j21/runtime.json").open("ab") as stream:
            stream.write(b" ")
    elif change == "span":
        summary["started_at_utc"] = receipt["started_at_utc"]
    images.write_json(output / "campaign.json", summary)
    publication = tmp_path / "published-kafka"
    if change:
        with pytest.raises(images.ImageAssessmentError):
            publisher.publish(output, declared, publication)
        assert not publication.exists()
    else:
        result = publisher.publish(output, declared, publication, host_prefixes=["/" "Users/fixture"])
        assert result["stage_observations"] == 60 and result["generator_shas"] == summary["generator_shas"]
        assert result["runtime_helper_shas"] == summary["runtime_helper_shas"]
        assert result["runtime_helpers_by_case"]["passthrough-pg-j21"] == images.KAFKA_PRIOR_SHA
        assert (publication / "kafka-cohort-copy.json.gz").exists()
        assert (publication / "prior-kafka-failure" / images.STAGES[0] / "assessment.json.gz").exists()


def test_kafka_continuation_runs_only_21_builds_42_scans_one_runtime(tmp_path, declaration, monkeypatch):
    declared, approved = tmp_path / "declared.json", tmp_path / "approved.json"
    images.write_json(declared, declaration)
    images.write_json(approved, {"generator_sha": "a" * 40, "collector_sha": "a" * 40, "kafka_continuation_approved": True})
    for name in ("check_freeze", "resource_check", "db_receipt", "docker"):
        monkeypatch.setattr(driver, name, Mock())
    monkeypatch.setattr(driver, "local_docker_boundary", lambda *_: {"effective_endpoint": "unix:///fixture.sock"})
    monkeypatch.setattr(driver, "refresh_bases", Mock(return_value={}))
    prior = {"cases": [{**binding, "stages": {stage: 1 for stage in images.STAGES}} for binding in images.kafka_reuse_bindings()],
             "continuation": {}, "capacity_continuation": {}}
    monkeypatch.setattr(driver, "copy_kafka_cohort", Mock(return_value=(prior, {"reuse_cases": images.kafka_reuse_bindings()})))
    built, scanned, finalized, runtimes = [], [], [], []

    def build(row, destination, **kwargs):
        assert kwargs["sha"] == kwargs["collector_sha"] == "a" * 40 and row["case"] not in images.KAFKA_REUSE_CASES
        built.append(row["case"])
        destination.mkdir()

    def scan(*_, **kwargs):
        assert kwargs["case"] not in images.KAFKA_REUSE_CASES
        scanned.append((kwargs["case"], kwargs["stage"]))
        return 0

    def finalize(destination, row, sha):
        assert row["case"] not in images.KAFKA_REUSE_CASES and sha == "a" * 40
        finalized.append(row["case"])

    def runtime(row, *_):
        assert row["case"] == "kafka-router-h2-j17"
        runtimes.append(row["case"])
        return {"status": "passed"}

    for name, function in (("build_case", build), ("collect", scan), ("finalize_case", finalize), ("run_runtime", runtime)):
        monkeypatch.setattr(driver, name, function)
    monkeypatch.setattr(driver, "packaged_contract", Mock(return_value={}))
    output = tmp_path / "continued-kafka"
    assert driver.campaign(output, declaration=declared, approval=approved, tool_setup=tmp_path, baseline=tmp_path,
                           prior_campaign=tmp_path / "old-kafka", kafka_continuation=True) == 1
    expected = {row["case"] for row in declaration["cases"]} - set(images.KAFKA_REUSE_CASES)
    assert set(built) == set(finalized) == expected and len(built) == len(finalized) == 21
    assert set(scanned) == {(case, stage) for case in expected for stage in images.STAGES} and len(scanned) == 42
    assert runtimes == ["kafka-router-h2-j17"]


def add_classifier_publication_fixture(campaign, case):
    build_directory = campaign / case / images.STAGES[0]
    original = [images.read_json(build_directory / (name + ".json")) for name in ("syft", "grype", "trivy")]
    original += [images.read_json(build_directory / "assessment.json")["image"], images.read_json(build_directory / "packaged.json")]
    observed, build, _ = classifier_inputs(original)
    for stage in images.STAGES:
        directory, bundle = campaign / case / stage, campaign / case / (stage + "-bundle")
        images.write_json(bundle / "retained-maven-bom.json", build["bom"])
        images.write_json(bundle / "resolved-inventory.json", build["resolved"])
        provenance = images.read_json(bundle / "provenance.json")
        provenance["collector_sha"] = provenance["generator_sha"]
        for name in ("retained-maven-bom.json", "resolved-inventory.json"):
            provenance["files"][name] = images.file_digest(bundle / name)
        images.write_json(bundle / "provenance.json", provenance)
        images.write_json(directory / "provenance.json", provenance)
        report = images.read_json(directory / "assessment.json")
        if stage == images.STAGES[0]:
            report["image"] = observed[3]
            sbom = images.build_classifier_sbom(build["bom"], build["resolved"], observed[3], provenance)
            grype = {"descriptor": copy.deepcopy(observed[1]["descriptor"]), "matches": [classifier_finding(sbom)],
                     "source": {"type": "sbom-file", "target": images.CLASSIFIER_JSON[0]}}
            for name, data in zip(images.CLASSIFIER_JSON, (sbom, grype, sbom), strict=True):
                images.write_json(directory / name, data)
            images.write_json(directory / "grype-build-classifiers.receipt.json", {
                "exit_code": 0, "command": ["grype", "sbom:" + images.CLASSIFIER_JSON[0]],
                "started_at_utc": images.utc_now(), "ended_at_utc": images.utc_now()})
            result = images.normalize(*observed, stage=stage, **supplemental(observed), **build, provenance=provenance,
                                      classifiers=sbom, classifier_grype=grype, classifier_extracted=sbom)
            for key in ("inventory", "findings", "coordinate-gaps", "cache-scanner-gaps", "build-bom-coverage"):
                images.write_json(directory / (key + ".json"), result[key])
            report.update(coverage=result["coverage"], findings=1, exit_code=1, status="complete-with-findings")
        report["retained_raw"] = images.retain_raw(directory)
        images.write_json(directory / "assessment.json", report)
        retention = images.read_json(bundle / "image-retention.json")
        retention.update(assessment_sha256=images.file_digest(directory / "assessment.json"), assessment_exit_code=report["exit_code"])
        images.write_json(bundle / "image-retention.json", retention)


@pytest.mark.parametrize("change", [None, "missing", "empty", "scope", "command-failed"])
def test_publisher_conditionally_requires_revalidates_and_retains_classifier_evidence(tmp_path, completed_campaign, change):
    campaign, declared = completed_campaign
    case = "kafka-h2-j17"
    add_classifier_publication_fixture(campaign, case)
    directory = campaign / case / images.STAGES[0]
    summary = images.read_json(campaign / "campaign.json")
    summary.update(exit_code=1, status="complete-with-findings", ended_at_utc=images.utc_now())
    next(row for row in summary["cases"] if row["case"] == case)["stages"][images.STAGES[0]] = 1
    images.write_json(campaign / "campaign.json", summary)
    if change == "missing":
        (directory / images.CLASSIFIER_JSON[0]).unlink()
        (directory / (images.CLASSIFIER_JSON[0] + ".gz")).unlink()
    elif change:
        name = images.CLASSIFIER_JSON[2] if change == "empty" else images.CLASSIFIER_JSON[0] if change == "scope" else "grype-build-classifiers.receipt.json"
        value = images.read_json(directory / name)
        if change == "empty":
            value["components"] = []
        elif change == "scope":
            value["components"][0]["scope"] = "excluded"
        else:
            value["exit_code"] = 2
        images.write_json(directory / name, value)
        report = images.read_json(directory / "assessment.json")
        report["retained_raw"] = images.retain_raw(directory)
        images.write_json(directory / "assessment.json", report)
        bundle = campaign / case / (images.STAGES[0] + "-bundle")
        retention = images.read_json(bundle / "image-retention.json")
        retention["assessment_sha256"] = images.file_digest(directory / "assessment.json")
        images.write_json(bundle / "image-retention.json", retention)
    publication = tmp_path / "published-classifiers"
    if change:
        with pytest.raises(images.ImageAssessmentError):
            publisher.publish(campaign, declared, publication)
        assert not publication.exists()
    else:
        result = publisher.publish(campaign, declared, publication, host_prefixes=["/" "Users/fixture"])
        assert result["match_observations_by_scanner"]["grype-build-classifier-authoritative"] == 1
        for name in images.CLASSIFIER_JSON:
            assert (publication / case / images.STAGES[0] / (name + ".gz")).exists()


@pytest.mark.parametrize("ephemeral", [True, False])
def test_storage_guard_prunes_scratch_before_real_directory_disappears(tmp_path, monkeypatch, ephemeral):
    monkeypatch.setattr(driver.shutil, "disk_usage", lambda _: SimpleNamespace(free=40 * 1024**3))
    (tmp_path / "retained.json").write_text('{"retained":true}')
    volatile = tmp_path / ("scan-scratch" if ephemeral else "persistent")
    volatile.mkdir()
    (volatile / "transient").write_bytes(b"owned temporary bytes")
    original = os.scandir
    visited = []

    class Disappearing:
        def __init__(self, path):
            self.resolved = Path(path) if not isinstance(path, int) else None
            if self.resolved is not None:
                visited.append(self.resolved)
            self.entries = original(path)

        def __enter__(self):
            return self

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.entries)

        def __exit__(self, *_):
            self.entries.close()
            if self.resolved == tmp_path and volatile.exists():
                shutil.rmtree(volatile)

    monkeypatch.setattr(driver.os, "scandir", Disappearing)
    if ephemeral:
        driver.resource_check(tmp_path)
        assert volatile not in visited
    else:
        with pytest.raises(FileNotFoundError):
            driver.resource_check(tmp_path)
    assert (tmp_path / "retained.json").read_text() == '{"retained":true}'


@pytest.mark.parametrize("kind", ["os", "runtime", "value"])
def test_storage_failure_stops_and_reaps_real_owned_writer_before_retention(tmp_path, monkeypatch, kind):
    calls = 0

    def guard():
        nonlocal calls
        calls += 1
        if calls > 1:
            if kind == "os":
                raise FileNotFoundError(errno.ENOENT, "private text discarded", str(tmp_path / "gone"))
            raise {"runtime": RuntimeError, "value": ValueError}[kind]("guard failed")

    monkeypatch.setattr(images, "STORAGE_GUARD", guard)
    code = "import os,time,pathlib; pathlib.Path('owned-pid').write_text(str(os.getpid())); f=open('changing','ab')\nwhile True: f.write(b'x'); f.flush(); time.sleep(.01)"
    with pytest.raises(images.ImageAssessmentError):
        images.run_tool([sys.executable, "-c", code], directory=tmp_path, label="owned-writer", env=os.environ.copy(), offline=False)
    pid = int((tmp_path / "owned-pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    before = images.retain_raw(tmp_path)
    time.sleep(.05)
    assert images.file_digest(tmp_path / "changing") == next(row["sha256"] for row in before if row["file"] == "changing")
    receipt = images.read_json(tmp_path / "owned-writer.receipt.json")
    assert receipt["owned_child_reaped"] is True and receipt["failure"] == "storage safety stop"
    if kind == "os":
        assert receipt["cause"]["errno"] == errno.ENOENT and str(tmp_path) not in receipt["cause"]["filename"]


def test_unconfirmed_owned_child_exit_forbids_output_hashes_and_collection_retention(tmp_path, monkeypatch, declaration):
    guard = Mock(side_effect=[None, FileNotFoundError(errno.ENOENT, "gone")])
    monkeypatch.setattr(images, "STORAGE_GUARD", guard)
    process = SimpleNamespace(pid=123, poll=lambda: None, wait=Mock(side_effect=subprocess.TimeoutExpired("owned", 1)))
    monkeypatch.setattr(images.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(images.os, "killpg", Mock())
    with pytest.raises(images.OwnedChildCleanupError):
        images.run_tool(["owned"], directory=tmp_path, label="unreaped", env={}, offline=False)
    receipt = images.read_json(tmp_path / "unreaped.receipt.json")
    assert receipt["owned_child_reaped"] is False and "stdout_sha256" not in receipt and process.wait.call_count == 2
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    row = declaration["cases"][0]
    images.write_json(bundle / "provenance.json", {"generator_sha": "a" * 40, "case": row["case"], "profile": row["profile"], "stage": images.STAGES[1]})
    declared, approval = tmp_path / "declared.json", tmp_path / "approval.json"
    images.write_json(declared, declaration)
    images.write_json(approval, {})
    monkeypatch.setattr(images, "check_freeze", Mock(side_effect=images.OwnedChildCleanupError("owned scanner exit unconfirmed")))
    output = tmp_path / "blocked-retention"
    assert images.collect(bundle, output, case=row["case"], stage=images.STAGES[1], declaration=declared,
                          approval=approval, tools=tmp_path, grype_db=tmp_path, trivy_cache=tmp_path) == 2
    assert images.read_json(output / "assessment.json")["retained_raw"] == []
    assert not list(output.glob("*.gz"))


def test_owned_cleanup_waits_even_if_signal_fails_and_keeps_os_cause(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "STORAGE_GUARD", Mock(side_effect=[None, RuntimeError("guard failed")]))
    process = SimpleNamespace(pid=123, poll=lambda: None, wait=Mock(side_effect=[subprocess.TimeoutExpired("owned", 1), 0]))
    monkeypatch.setattr(images.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(images.os, "killpg", Mock(side_effect=PermissionError(errno.EPERM, "denied")))
    with pytest.raises(images.ImageAssessmentError, match="cleanup failed"):
        images.run_tool(["owned"], directory=tmp_path, label="cleanup", env={}, offline=False)
    receipt = images.read_json(tmp_path / "cleanup.receipt.json")
    assert process.wait.call_count == 2 and receipt["owned_child_reaped"] is True
    assert receipt["cleanup_failure"]["errno"] == errno.EPERM


def write_owned_storage_manifest(prior, manifest):
    manifest.write_text("".join(f"{images.file_digest(path)}  {path}\n" for path in sorted(prior.rglob("*")) if path.is_file()))


@pytest.fixture
def completed_storage_boundary(completed_kafka_cohort, tmp_path, declaration, reports, monkeypatch):
    kafka, declared, setup, approved = completed_kafka_cohort
    started = images.utc_now()
    fresh = tmp_path / "old-storage-boundary"
    fresh.mkdir()
    prior, _ = completed_campaign.__wrapped__(fresh, declaration, reports, monkeypatch)
    for case in images.KAFKA_REUSE_CASES:
        shutil.rmtree(prior / case)
    receipt, kafka_lineage = driver.copy_kafka_cohort(kafka, prior, declaration, approved, setup)
    for item in declaration["cases"]:
        case = item["case"]
        if case in {"kafka-h2-j17", "kafka-pg-j17", images.STORAGE_PARTIAL_CASE}:
            rebind_completed_fixture_case(prior, case, images.STORAGE_PRIOR_SHA)
        elif case not in images.KAFKA_REUSE_CASES:
            shutil.rmtree(prior / case)
    restore_case_exports(prior, images.STORAGE_PARTIAL_CASE)
    for stage in images.STAGES:
        bundle = prior / images.STORAGE_PARTIAL_CASE / (stage + "-bundle")
        (bundle / "image-retention.json").unlink()
        shutil.copyfile(prior / images.STORAGE_PARTIAL_CASE / stage / "Dockerfile", bundle / "Dockerfile")
    failed = prior / images.STORAGE_PARTIAL_CASE / images.STAGES[1]
    failed_report = images.read_json(failed / "assessment.json")
    failed_report.update(status="incomplete", exit_code=2, failure="tool execution unavailable")
    command = images.read_json(failed / "syft.receipt.json")
    command.update(status="incomplete", failure="execution unavailable")
    command.pop("exit_code", None)
    images.write_json(failed / "syft.receipt.json", command)
    (failed / "syft.receipt.json.gz").write_bytes(publisher.compressed((failed / "syft.receipt.json").read_bytes()))
    for entry in failed_report["retained_raw"]:
        if entry["file"] == "syft.json":
            (failed / "syft.json.gz").write_bytes(publisher.compressed(b""))
            entry.update(bytes=0, sha256=images.digest(b""), gzip_sha256=images.file_digest(failed / "syft.json.gz"))
        elif entry["file"] == "syft.receipt.json":
            entry.update(bytes=(failed / entry["file"]).stat().st_size, sha256=images.file_digest(failed / entry["file"]),
                         gzip_sha256=images.file_digest(failed / (entry["file"] + ".gz")))
    images.write_json(failed / "assessment.json", failed_report)
    cases = [{**binding, "stages": {stage: 1 for stage in images.STAGES}, "scans_reused": True,
              "runtime_reused": binding["runtime_helper_sha"] is not None} for binding in images.kafka_reuse_bindings()]
    cases += [{"case": case, "generator_sha": images.STORAGE_PRIOR_SHA, "collector_sha": images.STORAGE_PRIOR_SHA,
               "runtime_helper_sha": None, "stages": {stage: 1 for stage in images.STAGES}}
              for case in ("kafka-h2-j17", "kafka-pg-j17", images.STORAGE_PARTIAL_CASE)]
    cases[-1]["stages"][images.STAGES[1]] = 2
    summary = {"generator_sha": images.STORAGE_PRIOR_SHA, "collector_sha": images.STORAGE_PRIOR_SHA, "runtime_helper_sha": images.STORAGE_PRIOR_SHA,
               "generator_shas": sorted([images.REUSE_SHA, images.KAFKA_PRIOR_SHA, images.STORAGE_PRIOR_SHA]),
               "runtime_helper_shas": sorted([images.CAPACITY_RUNTIME_SHA, images.KAFKA_PRIOR_SHA]),
               "cases": cases, "continuation": receipt["continuation"], "capacity_continuation": receipt["capacity_continuation"],
               "kafka_continuation": kafka_lineage, "coverage_sha256": images.file_digest(declared),
               "started_at_utc": started, "ended_at_utc": images.utc_now(), "campaign_complete": False, "status": "incomplete", "exit_code": 2,
               "failure": "required scan/inventory incomplete; diagnose before affected-only repair"}
    images.write_json(prior / "campaign.json", summary)
    manifest = tmp_path / "owned-storage-prior.sha256"
    write_owned_storage_manifest(prior, manifest)
    approved.update(kafka_continuation_approved=False, storage_continuation_approved=True,
                    prior_campaign_sha256=images.file_digest(prior / "campaign.json"),
                    prior_manifest_sha256=images.file_digest(manifest), reuse_stages=images.storage_reuse_bindings())
    monkeypatch.setattr(publisher, "image_archive", lambda *_, **__: (failed_report["image"], b"synthetic saved export"))
    return prior, declared, setup, approved, manifest


@pytest.mark.parametrize("change", [None, "receipt-hash", "manifest-hash", "source-file", "source", "helper", "db", "tools",
                                  "missing-build", "retention", "contradiction", "span", "wrong-case"])
def test_storage_copy_preserves_exact_23_and_failed_contradiction(tmp_path, completed_storage_boundary, monkeypatch, change):
    prior, declared, setup, approved, manifest = completed_storage_boundary
    if change == "receipt-hash":
        approved["prior_campaign_sha256"] = "0" * 64
    elif change == "manifest-hash":
        approved["prior_manifest_sha256"] = "0" * 64
    elif change == "source-file":
        (prior / images.STORAGE_PARTIAL_CASE / images.STAGES[0] / "syft.json").write_bytes(b"tampered")
    elif change == "db":
        monkeypatch.setattr(driver, "db_receipt", lambda *_: {"different": "snapshot"})
    elif change == "tools":
        images.write_json(setup / "verified/tools.json", {"different": "tools"})
    elif change == "missing-build":
        (prior / images.STORAGE_PARTIAL_CASE / images.STAGES[0] / "assessment.json").unlink()
    elif change == "retention":
        (prior / "kafka-pg-j17" / (images.STAGES[0] + "-bundle") / "image-retention.json").unlink()
    elif change == "contradiction":
        failed = prior / images.STORAGE_PARTIAL_CASE / images.STAGES[1]
        (failed / "syft.json.gz").write_bytes(publisher.compressed((failed / "syft.json").read_bytes()))
    elif change in ("source", "helper"):
        path = prior / images.STORAGE_PARTIAL_CASE / images.STAGES[0] / "assessment.json"
        value = images.read_json(path)
        value["generator_sha" if change == "source" else "assessment_helper_sha"] = "a" * 40
        images.write_json(path, value)
    elif change in ("span", "wrong-case"):
        path = prior / "campaign.json"
        value = images.read_json(path)
        if change == "span":
            value["started_at_utc"] = value["ended_at_utc"]
        else:
            value["cases"][-1]["case"] = "kafka-router-h2-j17"
        images.write_json(path, value)
        approved["prior_campaign_sha256"] = images.file_digest(path)
    if change in {"source", "helper", "contradiction", "span", "wrong-case"}:
        write_owned_storage_manifest(prior, manifest)
        approved["prior_manifest_sha256"] = images.file_digest(manifest)
    before = {str(path.relative_to(prior)): images.file_digest(path) for path in prior.rglob("*") if path.is_file()}
    output = tmp_path / "storage-copy"
    output.mkdir()
    for name in ("build_case", "collect", "run_runtime", "finalize_case", "docker"):
        monkeypatch.setattr(driver, name, Mock(side_effect=AssertionError("preserved assessments must not execute")))
    if change:
        with pytest.raises((images.ImageAssessmentError, OSError)):
            driver.copy_storage_cohort(prior, manifest, output, images.read_json(declared), approved, setup)
        assert not (output / images.REUSE_CASE).exists()
    else:
        _, lineage = driver.copy_storage_cohort(prior, manifest, output, images.read_json(declared), approved, setup)
        assert len(lineage["reuse_stages"]) == 23
        for binding in lineage["reuse_stages"]:
            old = prior / binding["case"] / binding["stage"] / "assessment.json"
            assert (output / binding["case"] / binding["stage"] / "assessment.json").read_bytes() == old.read_bytes()
        failed = prior / images.STORAGE_PARTIAL_CASE / images.STAGES[1]
        for name in ("assessment.json", "syft.json", "syft.json.gz"):
            assert (output / "prior-storage-failure" / name).read_bytes() == (failed / name).read_bytes()
        assert not (output / images.STORAGE_PARTIAL_CASE / images.STAGES[1]).exists()
    assert before == {str(path.relative_to(prior)): images.file_digest(path) for path in prior.rglob("*") if path.is_file()}


@pytest.mark.parametrize("change", [None, "new-helper", "transform", "extra-file", "missing-stage", "span"])
def test_storage_publication_preserves_partial_build_and_mixed_stage_helpers(tmp_path, completed_storage_boundary, declaration, reports, monkeypatch, change):
    prior, declared, setup, approved, manifest = completed_storage_boundary
    started = images.utc_now()
    fresh = tmp_path / "storage-remaining-cases"
    fresh.mkdir()
    output, _ = completed_campaign.__wrapped__(fresh, declaration, reports, monkeypatch)
    saved_final = tmp_path / "synthetic-new-final"
    shutil.copytree(output / images.STORAGE_PARTIAL_CASE / images.STAGES[1], saved_final)
    for case in (*images.STORAGE_PAIR_CASES, images.STORAGE_PARTIAL_CASE):
        shutil.rmtree(output / case)
    old, lineage = driver.copy_storage_cohort(prior, manifest, output, declaration, approved, setup)
    case_dir = output / images.STORAGE_PARTIAL_CASE
    shutil.copytree(saved_final, case_dir / images.STAGES[1])
    directory = case_dir / images.STAGES[1]
    bundle = case_dir / (images.STAGES[1] + "-bundle")
    provenance = images.read_json(bundle / "provenance.json")
    images.write_json(directory / "provenance.json", provenance)
    report = images.read_json(directory / "assessment.json")
    report.update(generator_sha=images.STORAGE_PRIOR_SHA, collector_sha=images.STORAGE_PRIOR_SHA,
                  assessment_helper_sha="a" * 40, retained_raw=images.retain_raw(directory))
    images.write_json(directory / "assessment.json", report)
    old_build_hash = images.file_digest(case_dir / images.STAGES[0] / "assessment.json")
    transformed = images.utc_now()
    driver.finalize_case(case_dir, next(row for row in declaration["cases"] if row["case"] == images.STORAGE_PARTIAL_CASE),
                         images.STORAGE_PRIOR_SHA, assessment_helper_sha="a" * 40)
    images.write_json(output / "storage-partial-transformation.json", {
        "copy_manifest_sha256": lineage["copy_manifest_sha256"], "assessment_helper_sha": "a" * 40,
        "assessment_sha256": old_build_hash,
        "report_retention_sha256": images.file_digest(case_dir / images.STAGES[0] / "report-retention.json"),
        "image_retention_sha256": images.file_digest(case_dir / (images.STAGES[0] + "-bundle") / "image-retention.json"),
        "final_image_retention_sha256": images.file_digest(case_dir / (images.STAGES[1] + "-bundle") / "image-retention.json"),
        "started_at_utc": transformed, "ended_at_utc": images.utc_now()})
    summary = images.read_json(output / "campaign.json")
    summary.update({key: old[key] for key in ("continuation", "capacity_continuation", "kafka_continuation")})
    summary.update(collector_sha="a" * 40, runtime_helper_sha="a" * 40, storage_continuation=lineage,
                   generator_shas=sorted(["a" * 40, images.REUSE_SHA, images.KAFKA_PRIOR_SHA, images.STORAGE_PRIOR_SHA]),
                   runtime_helper_shas=sorted(["a" * 40, images.CAPACITY_RUNTIME_SHA, images.KAFKA_PRIOR_SHA]),
                   started_at_utc=started, ended_at_utc=images.utc_now(), exit_code=1, status="complete-with-findings")
    original = {row["case"]: row for row in old["cases"]}
    for item in summary["cases"]:
        if item["case"] in original:
            source = original[item["case"]]["generator_sha"]
            item.update(generator_sha=source, collector_sha=source, runtime_helper_sha=original[item["case"]]["runtime_helper_sha"],
                        stages={stage: 1 for stage in images.STAGES})
            if item["case"] == images.STORAGE_PARTIAL_CASE:
                item["stages"][images.STAGES[1]] = 0
        else:
            source = "a" * 40
            item.update(generator_sha=source, collector_sha=source, runtime_helper_sha=source if item["case"] in images.RUNTIME_CASES else None)
        item["assessment_helper_shas"] = {stage: images.stage_helper(summary, item["case"], stage, source) for stage in images.STAGES}
    contract = images.packaged_contract(output, declaration, "a" * 40, summary=summary)
    images.write_json(output / "packaged-inventories.json", contract)
    if change == "new-helper":
        report["assessment_helper_sha"] = images.STORAGE_PRIOR_SHA
        images.write_json(directory / "assessment.json", report)
    elif change == "transform":
        value = images.read_json(output / "storage-partial-transformation.json")
        value["assessment_sha256"] = "0" * 64
        images.write_json(output / "storage-partial-transformation.json", value)
    elif change == "extra-file":
        (output / "kafka-h2-j17/untracked.txt").write_text("not in original preservation manifest")
    elif change == "missing-stage":
        (output / "kafka-pg-j17" / images.STAGES[0] / "assessment.json").unlink()
    elif change == "span":
        summary["started_at_utc"] = old["started_at_utc"]
    images.write_json(output / "campaign.json", summary)
    publication = tmp_path / "published-storage"
    if change:
        with pytest.raises((images.ImageAssessmentError, OSError)):
            publisher.publish(output, declared, publication)
        assert not publication.exists()
    else:
        result = publisher.publish(output, declared, publication, host_prefixes=["/" "Users/fixture"])
        assert result["stage_observations"] == 60 and result["generator_shas"] == summary["generator_shas"]
        assert result["assessment_helpers_by_case"][images.STORAGE_PARTIAL_CASE] == {images.STAGES[0]: images.STORAGE_PRIOR_SHA, images.STAGES[1]: "a" * 40}
        assert images.file_digest(case_dir / images.STAGES[0] / "assessment.json") == old_build_hash
        assert not (case_dir / images.STAGES[0] / "syft.json").exists()
        assert (case_dir / images.STAGES[0] / "syft.json.gz").exists()
        assert (publication / "storage-failure-observation.json.gz").exists()


@pytest.mark.parametrize("tamper", [False, True])
def test_saved_final_collection_binds_original_export_and_new_assessment_helper(tmp_path, completed_storage_boundary, monkeypatch, tamper):
    prior, declared, setup, approved, manifest = completed_storage_boundary
    output = tmp_path / "saved-final-collection"
    output.mkdir()
    driver.copy_storage_cohort(prior, manifest, output, images.read_json(declared), approved, setup)
    approval = tmp_path / "storage-approved.json"
    images.write_json(approval, approved)
    bundle = output / images.STORAGE_PARTIAL_CASE / (images.STAGES[1] + "-bundle")
    failed = output / "prior-storage-failure"
    old_report = images.read_json(failed / "assessment.json")
    packaged = images.read_json(failed / "packaged.json")
    freeze = Mock()
    monkeypatch.setattr(images, "check_freeze", freeze)
    monkeypatch.setattr(images, "image_archive", lambda *_, **__: (old_report["image"], b"synthetic saved jar"))
    monkeypatch.setattr(images, "jar_inventory", lambda *_: (packaged, []))
    authority = images.read_json(failed / "packaged-authoritative.cdx.json")
    monkeypatch.setattr(images, "packaged_sbom", lambda *_: (authority, []))
    monkeypatch.setattr(images, "verify_tools", lambda *_, **__: old_report["tools"])
    database = images.read_json(output / images.STORAGE_PARTIAL_CASE / images.STAGES[0] / "databases.json")
    monkeypatch.setattr(images, "db_receipt", lambda *_: database)
    commands = []

    def scanner(command, *, directory, label, env):
        commands.append(label)
        for name in ("syft.json", "grype.json", "trivy.json", "grype-packaged.json", "grype-packaged-extracted.cdx.json"):
            images.write_json(directory / name, images.read_json(failed / name))

    monkeypatch.setattr(images, "run_tool", scanner)
    old_provenance = (bundle / "provenance.json").read_bytes()
    if tamper:
        (bundle / "image.tar").write_bytes(b"substituted export")
    code = images.collect(bundle, output / images.STORAGE_PARTIAL_CASE / images.STAGES[1], case=images.STORAGE_PARTIAL_CASE, stage=images.STAGES[1],
                          declaration=declared, approval=approval, tools=setup / "archives", grype_db=setup / "grype-db",
                          trivy_cache=setup / "trivy-cache", storage_continuation=True)
    report = images.read_json(output / images.STORAGE_PARTIAL_CASE / images.STAGES[1] / "assessment.json")
    if tamper:
        assert code == 2 and commands == []
    else:
        assert code == 1 and report["generator_sha"] == report["collector_sha"] == images.STORAGE_PRIOR_SHA
        assert report["assessment_helper_sha"] == "a" * 40
        assert freeze.call_args.args[-1] == "a" * 40
    assert (bundle / "provenance.json").read_bytes() == old_provenance


@pytest.mark.parametrize("saved_status", [1, 2])
def test_storage_continuation_only_saved_final_then_18_builds_37_scans_one_runtime(tmp_path, declaration, monkeypatch, saved_status):
    declared, approved = tmp_path / "declared.json", tmp_path / "approved.json"
    images.write_json(declared, declaration)
    images.write_json(approved, {"generator_sha": "a" * 40, "collector_sha": "a" * 40, "storage_continuation_approved": True})
    for name in ("check_freeze", "resource_check", "db_receipt", "docker"):
        monkeypatch.setattr(driver, name, Mock())
    monkeypatch.setattr(driver, "local_docker_boundary", lambda *_: {"effective_endpoint": "unix:///fixture.sock"})
    monkeypatch.setattr(driver, "refresh_bases", Mock(return_value={}))
    old_cases = [{**binding, "stages": {stage: 1 for stage in images.STAGES}} for binding in images.kafka_reuse_bindings()]
    old_cases += [{"case": case, "generator_sha": images.STORAGE_PRIOR_SHA, "collector_sha": images.STORAGE_PRIOR_SHA,
                   "runtime_helper_sha": None, "stages": {stage: 1 for stage in images.STAGES}} for case in ("kafka-h2-j17", "kafka-pg-j17")]
    old = {"cases": old_cases, "continuation": {}, "capacity_continuation": {}, "kafka_continuation": {}}
    monkeypatch.setattr(driver, "copy_storage_cohort", Mock(return_value=(old, {"copy_manifest_sha256": "f" * 64})))
    monkeypatch.setattr(driver, "file_digest", lambda *_: "f" * 64)
    built, scanned, finalized, runtimes = [], [], [], []

    def build(row, destination, **kwargs):
        assert row["case"] not in {*images.STORAGE_PAIR_CASES, images.STORAGE_PARTIAL_CASE}
        assert kwargs["sha"] == kwargs["collector_sha"] == "a" * 40
        built.append(row["case"])
        destination.mkdir()

    def scan(*_, **kwargs):
        assert kwargs["case"] not in images.STORAGE_PAIR_CASES
        scanned.append((kwargs["case"], kwargs["stage"]))
        if kwargs["case"] == images.STORAGE_PARTIAL_CASE:
            assert kwargs["stage"] == images.STAGES[1] and kwargs["storage_continuation"] is True
            return saved_status
        return 0

    def finalize(destination, row, sha, **kwargs):
        assert row["case"] not in images.STORAGE_PAIR_CASES
        if row["case"] == images.STORAGE_PARTIAL_CASE:
            assert sha == images.STORAGE_PRIOR_SHA and kwargs["assessment_helper_sha"] == "a" * 40
        else:
            assert sha == "a" * 40
        finalized.append(row["case"])

    def runtime(row, *_):
        assert row["case"] == "kafka-router-h2-j17"
        runtimes.append(row["case"])
        return {"status": "passed"}

    for name, function in (("build_case", build), ("collect", scan), ("finalize_case", finalize), ("run_runtime", runtime)):
        monkeypatch.setattr(driver, name, function)
    monkeypatch.setattr(driver, "packaged_contract", Mock(return_value={}))
    output = tmp_path / "continued-storage"
    code = driver.campaign(output, declaration=declared, approval=approved, tool_setup=tmp_path, baseline=tmp_path,
                           prior_campaign=tmp_path / "old-storage", prior_manifest=tmp_path / "prior.sha256", storage_continuation=True)
    if saved_status == 2:
        assert code == 2 and built == finalized == runtimes == [] and scanned == [(images.STORAGE_PARTIAL_CASE, images.STAGES[1])]
    else:
        expected = {row["case"] for row in declaration["cases"]} - {*images.STORAGE_PAIR_CASES, images.STORAGE_PARTIAL_CASE}
        assert code == 1 and set(built) == expected and len(built) == 18
        assert len(scanned) == 37 and set(scanned) == {(case, stage) for case in expected for stage in images.STAGES} | {(images.STORAGE_PARTIAL_CASE, images.STAGES[1])}
        assert len(finalized) == 19 and runtimes == ["kafka-router-h2-j17"]
