#!/usr/bin/env python3
"""Validate 30x2 completed local observations and export sanitized evidence.

No scans, downloads, archive extraction, uploads, source copies or acceptance
decisions. Destination must be new; publication.json is written only on success.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from appbuilder.generation.container_policy import (  # noqa: E402
    declared_base_references,
    pinned_base,
)
from scripts.assess_generated_images import (  # noqa: E402
    ARCHIVE_LIMIT,
    CAPACITY_RUNTIME_SHA,
    CLASSIFIER_JSON,
    KAFKA_PRIOR_SHA,
    KAFKA_REUSE_CASES,
    LIMIT,
    PINS,
    REUSE_CASE,
    REUSE_SHA,
    RUNTIME_CASES,
    STAGES,
    STORAGE_PAIR_CASES,
    STORAGE_PARTIAL_CASE,
    STORAGE_PRIOR_SHA,
    ImageAssessmentError,
    build_classifier_sbom,
    campaign_case_sources,
    config_semantics,
    digest,
    evidence_bytes,
    evidence_digest,
    file_digest,
    identity,
    image_archive,
    kafka_reuse_bindings,
    make_plan,
    normalize,
    packaged_contract,
    read_json,
    require,
    stage_helper,
    storage_reuse_bindings,
    validate_authoritative_sbom,
    validate_bootstrap_provenance,
    validate_packaged_bom,
    validate_runtime_inspection,
    verify_gzip,
    write_json,
)
from scripts.collect_generated_images import (  # noqa: E402
    resource_check,
    verify_container_launch,
)

STAGE_JSON = ("syft.json", "grype.json", "trivy.json", "inventory.json", "findings.json",
              "native-members.json", "packaged.json", "provenance.json", "databases.json", "packaged-bom-integrity.json",
              "packaged-authoritative.cdx.json", "grype-packaged.json", "grype-packaged-extracted.cdx.json",
              "bootstrap-provenance.json", "coordinate-gaps.json", "cache-scanner-gaps.json", "build-bom-coverage.json")
BUNDLE_JSON = ("generation.json", "resolved-inventory.json", "dependency-policy.json", "base-images.json",
               "image-config.json", "image-manifest.json", "retained-maven-bom.json")
RUNTIME_JSON = ("runtime.json", "runtime-identity.json", "runtime-manifest.json", "runtime-image-inspect.stdout",
                "runtime-create.receipt.json", "runtime-created-state.stdout", "runtime-created-state.receipt.json", "runtime-start.receipt.json")


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)


def validate_span(receipt):
    start, end = (datetime.fromisoformat(receipt[key].replace("Z", "+00:00"))
                  for key in ("started_at_utc", "ended_at_utc"))
    require(start.tzinfo is not None and end.tzinfo is not None
            and start.utcoffset() == timezone.utc.utcoffset(start)
            and end.utcoffset() == timezone.utc.utcoffset(end) and end >= start,
            "actual UTC start/end span missing or inconsistent")
    return start, end


def bounded_json(path):
    return read_json(path)


def redact(value, prefixes, *, _path=()):
    """Only known host prefixes; never alter dependency identities or image paths."""
    def replace(string):
        for index, prefix in enumerate(prefixes):
            string = re.sub(re.escape(prefix) + r"(?=/|$|[\s:;\"'])",
                            lambda _, index=index: f"<host-{index}>", string)
        return string

    if isinstance(value, str):
        return replace(value)
    if isinstance(value, list):
        return [redact(item, prefixes, _path=(*_path, index)) for index, item in enumerate(value)]
    if isinstance(value, dict):
        # Syft's root image source name is the input archive path, not a package.
        image_source = (_path == ("source",) and value.get("type") == "image"
                        and not any(key in value for key in ("purl", "group", "artifact", "ecosystem"))
                        and isinstance(value.get("metadata"), dict)
                        and isinstance(value["metadata"].get("imageID"), str)
                        and re.fullmatch(r"sha256:[0-9a-f]{64}", value["metadata"]["imageID"]) is not None)
        dependency = not image_source and "version" in value and any(key in value for key in ("purl", "group", "artifact", "type", "ecosystem"))
        protected = {"id", "name", "version", "purl", "group", "artifact", "classifier"} if dependency else {"id", "version"} if image_source else set()
        result = {}
        for key, item in value.items():
            clean_key = replace(key)
            require(clean_key not in result, "host redaction would collide JSON keys")
            clean = redact(item, prefixes, _path=(*_path, key))
            if key in protected or key in {"contents", "content"}:
                require(clean == item, "host prefix inside dependency identity/content; refuse destructive redaction")
            result[clean_key] = clean
        return result
    return value


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()


def compressed(data):
    stream = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as output:
        output.write(data)
    return stream.getvalue()


def recorded_host_roots(campaign, cases):
    """Recover host roots from recorded command paths, not the replay location."""
    case_names = "|".join(re.escape(row["case"]) for row in cases)
    stages = "|".join(re.escape(stage) for stage in STAGES)
    campaign_path = re.compile(r"(?:^|[=:])(/.+?)/(?:(?:" + case_names
                               + r"))/(?:" + stages + r")(?:-bundle)?(?:/|$)")
    tool_path = re.compile(r"^(/.+)/verified/(?:syft|grype|trivy)$")
    case_cwd = re.compile(r"^(/.+?)/(?:" + case_names + r")(?:/|$)")
    roots = set()
    receipts = {path.with_suffix("") if path.suffix == ".gz" else path
                for path in campaign.rglob("*.receipt.json*")
                if path.name.endswith((".receipt.json", ".receipt.json.gz"))}
    for path in sorted(receipts):
        receipt = bounded_json(path)
        values = receipt.get("command", [])
        require(isinstance(values, list), "invalid command receipt")
        for value in values:
            if not isinstance(value, str):
                continue
            match = campaign_path.search(value)
            if match:
                roots.add(str(Path(match[1]).parent))
            tool = tool_path.search(value)
            if tool:
                roots.add(str(Path(tool[1]).parent))
        cwd = receipt.get("cwd")
        if isinstance(cwd, str) and cwd.startswith("/"):
            match = case_cwd.search(cwd)
            roots.add(str(Path(match[1]).parent) if match else cwd.rstrip("/"))
        for key in ("campaign_root", "tool_setup_root", "checkout_root"):
            value = receipt.get(key)
            if isinstance(value, str) and value.startswith("/"):
                roots.add(value.rstrip("/"))
    require(all(root not in {"", "/"} for root in roots), "unsafe recorded host root")
    # A recorded cwd/cache below an already known root needs no second boundary.
    return sorted(root for root in roots
                  if not any(root != parent and Path(root).is_relative_to(parent) for parent in roots))


def require_private_paths_redacted(payload, prefixes, recorded_roots):
    text = payload.decode("utf-8")
    forbidden = {"/" "Users/", str(Path.home())}
    for root in recorded_roots:
        forbidden.add(root)
        masked = redact(root, prefixes)
        # A home-only replacement can still expose the recorded private layout.
        # Only a full root placeholder removes that disclosure boundary.
        if not re.fullmatch(r"<host-[0-9]+>", masked):
            forbidden.add(masked)
    require(not any(value and value in text for value in forbidden),
            "residual host path in publication; supply --host-prefix for recorded roots")


def retained_integrity(directory, report, *, complete=True):
    entries = report.get("retained_raw")
    require(isinstance(entries, list) and entries, "private-original integrity receipts missing")
    indexed = {}
    compact = bounded_json(directory / "report-retention.json") if (directory / "report-retention.json").exists() else None
    for row in entries:
        name = row["file"]
        require(isinstance(name, str) and Path(name).name == name and name not in {".", ".."}
                and name not in indexed and sha(row.get("sha256")) and sha(row.get("gzip_sha256")),
                "invalid or duplicate private-original receipt")
        raw, packed = directory / name, directory / (name + ".gz")
        require(packed.is_file() and not packed.is_symlink()
                and packed.stat().st_size <= LIMIT + 1048576
                and evidence_digest(raw) == row["sha256"] and file_digest(packed) == row["gzip_sha256"],
                "private-original or gzip integrity mismatch")
        size = row.get("bytes", len(evidence_bytes(raw)))
        verify_gzip(packed, row["sha256"], size)
        if not raw.exists():
            require(compact is not None and compact.get("status") == "verified-compressed"
                    and compact.get("assessment_sha256") == evidence_digest(directory / "assessment.json")
                    and compact.get("records") == entries and name in compact.get("removed_originals", []),
                    "absent original lacks validated lossless retention receipt")
        indexed[name] = row
    if complete:
        require(set(STAGE_JSON) | {"Dockerfile", "syft.receipt.json", "grype.receipt.json", "trivy.receipt.json",
                                  "grype-packaged.receipt.json"}
                <= set(indexed), "required stage evidence receipt missing")
    return indexed


def validate_bases(bases, row):
    try:
        expected_references = declared_base_references(row)
    except ValueError as exc:
        raise ImageAssessmentError(str(exc)) from exc
    require(isinstance(bases, list) and len(bases) == 2
            and tuple(base.get("reference") for base in bases) == expected_references
            and all(identity(base.get("image_id")) and base.get("platform") == "linux/amd64"
                    and base.get("repo_digests") and all(identity(value.rsplit("@", 1)[-1])
                    for value in base["repo_digests"]) and base.get("rootfs")
                    and all(identity(layer) for layer in base["rootfs"]) for base in bases),
            "resolved base identity receipts incomplete")
    for observed in bases:
        pin = pinned_base(observed["reference"])
        if pin is not None:
            require(observed["image_id"] in {pin.amd64_manifest_digest, pin.config_digest}
                    and observed.get("tag_index_digest") == pin.index_digest
                    and observed.get("amd64_manifest_digest") == pin.amd64_manifest_digest
                    and observed.get("config_digest") == pin.config_digest
                    and pin.index_digest in {value.rsplit("@", 1)[-1] for value in observed["repo_digests"]},
                    "base platform/config/index differs from reviewed identities")


def validate_stage(campaign, row, stage, generator_sha, *, check_retention=True, assessment_helper_sha=None):
    directory = campaign / row["case"] / stage
    report = bounded_json(directory / "assessment.json")
    validate_span(report)
    require(report.get("case") == row["case"] and report.get("stage") == stage
            and report.get("generator_sha") == generator_sha and report.get("exit_code") in (0, 1)
            and report.get("status") == ("complete-with-findings" if report["exit_code"] else "complete-no-matches"),
            "incomplete or mismatched case/stage assessment")
    require(report.get("assessment_helper_sha", generator_sha) == (assessment_helper_sha or generator_sha),
            "assessment helper identity mismatch")
    receipts = retained_integrity(directory, report)
    for name in receipts:
        if name.endswith(".receipt.json"):
            validate_span(bounded_json(directory / name))
    data = {name: bounded_json(directory / name) for name in STAGE_JSON}
    image = report["image"]
    require(identity(image.get("image_id")) and image.get("platform") == "linux/amd64"
            and image.get("config_sha256") == image["image_id"].split(":", 1)[1]
            and sha(image.get("configuration_sha256")) and sha(image.get("jar_sha256"))
            and image.get("rootfs") and all(identity(layer) for layer in image["rootfs"]),
            "missing image/config/rootfs identity")
    bases = report.get("bases")
    validate_bases(bases, row)
    base = bases[0 if stage == STAGES[0] else 1]
    require(image["rootfs"][:len(base["rootfs"])] == base["rootfs"], "actual image/base rootfs mismatch")
    provenance = data["provenance.json"]
    require(report.get("collector_sha", generator_sha) == provenance.get("collector_sha", generator_sha),
            "collector/source provenance mismatch")
    require((provenance.get("generator_sha"), provenance.get("case"), provenance.get("profile"), provenance.get("stage"))
            == (generator_sha, row["case"], row["profile"], stage), "source/profile provenance mismatch")
    require(all(sha(provenance["files"].get(name)) for name in (
        "Dockerfile", "source.tar", "input.tar", "generation.json", "resolved-inventory.json",
        "dependency-policy.json", "image.tar", "base-images.json", "image-config.json", "image-manifest.json",
        "retained-maven-bom.json")),
        "source/input/image hash receipts missing")
    require(provenance["files"]["Dockerfile"] == receipts["Dockerfile"]["sha256"], "recipe integrity mismatch")
    packaged = data["packaged.json"]
    require(isinstance(packaged, list) and packaged
            and all(sha(item.get("sha256")) for item in packaged)
            and [item["filename"] for item in packaged] == report["packaged_libraries"],
            "packaged inventory/assessment mismatch")
    native = data["native-members.json"]
    require(isinstance(native, list) and all(isinstance(item, dict) and sha(item.get("sha256"))
            and item.get("library") in report["packaged_libraries"] and item.get("member") for item in native),
            "malformed native-member inventory")
    validate_authoritative_sbom(data["packaged-authoritative.cdx.json"], packaged, image)
    bundle = campaign / row["case"] / (stage + "-bundle")
    bom, resolved = bounded_json(bundle / "retained-maven-bom.json"), bounded_json(bundle / "resolved-inventory.json")
    classifiers = build_classifier_sbom(bom, resolved, image, provenance) if stage == STAGES[0] else None
    if classifiers is not None:
        require(set(CLASSIFIER_JSON) | {"grype-build-classifiers.receipt.json"} <= set(receipts),
                "required build classifier evidence receipts missing")
        data.update({name: bounded_json(directory / name) for name in CLASSIFIER_JSON})
        require(bounded_json(directory / "grype-build-classifiers.receipt.json").get("exit_code") == 0,
                "build classifier assessment command incomplete")
    else:
        require(not set(CLASSIFIER_JSON) & set(receipts), "unexpected classifier evidence receipts")
    normalized = normalize(data["syft.json"], data["grype.json"], data["trivy.json"], image, packaged, stage=stage,
                           authoritative=data["packaged-authoritative.cdx.json"], packaged_grype=data["grype-packaged.json"],
                           extracted=data["grype-packaged-extracted.cdx.json"],
                           bom=bom, resolved=resolved, provenance=provenance,
                           classifiers=data.get(CLASSIFIER_JSON[0]), classifier_grype=data.get(CLASSIFIER_JSON[1]),
                           classifier_extracted=data.get(CLASSIFIER_JSON[2]))
    require(normalized["inventory"] == data["inventory.json"] and normalized["findings"] == data["findings.json"]
            and normalized["coverage"] == report["coverage"]
            and len(normalized["findings"]) == report["findings"]
            and report["exit_code"] == int(bool(normalized["findings"])),
            "scanner normalization/findings/coverage mismatch")
    require(normalized["coordinate-gaps"] == data["coordinate-gaps.json"]
            and normalized["cache-scanner-gaps"] == data["cache-scanner-gaps.json"]
            and normalized["build-bom-coverage"] == data["build-bom-coverage.json"], "scanner extraction gap receipt mismatch")
    pins = read_json(PINS)["tools"]
    require(set(report["tools"]) == set(pins), "required tool receipt missing")
    for name, pin in pins.items():
        tool = report["tools"][name]
        require(tool.get("version") == pin["version"] and tool.get("archive_sha256") == pin["archive_sha256"]
                and sha(tool.get("binary_sha256")) and sha(tool.get("checksums_sha256")),
                "tool/version/checksum receipt mismatch")
    db = data["databases.json"]
    require(set(db) == {"grype", "trivy", "trivy-java"} and all(
        item.get("metadata") and item.get("files") and all(sha(file.get("sha256")) for file in item["files"])
        for item in db.values()), "database identity/date/hash receipts missing")
    for name in BUNDLE_JSON:
        bounded_json(bundle / name)
        require(file_digest(bundle / name) == provenance["files"][name], "bundle provenance integrity mismatch")
    require(validate_packaged_bom(packaged, bounded_json(bundle / "retained-maven-bom.json"))
            == data["packaged-bom-integrity.json"], "retained Maven BOM reconciliation receipt mismatch")
    validate_bootstrap_provenance(data["bootstrap-provenance.json"], packaged, bundle / "source.tar")
    for name in ("source.tar", "input.tar"):
        require((bundle / name).is_file() and not (bundle / name).is_symlink()
                and file_digest(bundle / name) == provenance["files"][name], "private source/input archive hash mismatch")
    config = bounded_json(bundle / "image-config.json")
    manifest = bounded_json(bundle / "image-manifest.json")
    require(file_digest(bundle / "image-config.json") == image["config_sha256"]
            and (config.get("os"), config.get("architecture")) == ("linux", "amd64")
            and config.get("rootfs", {}).get("diff_ids") == image["rootfs"]
            and isinstance(manifest, list) and len(manifest) == 1
            and len(manifest[0].get("Layers", [])) == len(image["rootfs"]),
            "retained image config/manifest identity mismatch")
    if check_retention:
        validate_image_retention(bundle, directory, row, stage, report, provenance)
    else:
        original = bundle / "image.tar"
        require(original.is_file() and not original.is_symlink() and original.stat().st_size <= ARCHIVE_LIMIT
                and file_digest(original) == provenance["files"]["image.tar"],
                "original export missing or changed before completed validation")
    require(bounded_json(bundle / "base-images.json") == report["bases"], "base identity receipt mismatch")
    return report, data, receipts


def validate_image_retention(bundle, directory, row, stage, report, provenance):
    receipt = bounded_json(bundle / "image-retention.json")
    retain = row["case"] in RUNTIME_CASES and stage == STAGES[1]
    size = receipt.get("image_tar_bytes")
    require(receipt.get("schema_version") == 2 and receipt.get("case") == row["case"]
            and receipt.get("stage") == stage and receipt.get("generator_sha") == report["generator_sha"]
            and receipt.get("image_id") == report["image"]["image_id"] and receipt.get("platform") == "linux/amd64"
            and receipt.get("assessment_sha256") == evidence_digest(directory / "assessment.json")
            and receipt.get("validation") == "complete" and receipt.get("assessment_exit_code") == report["exit_code"]
            and receipt.get("retained") is retain and receipt.get("image_tar_sha256") == provenance["files"]["image.tar"]
            and isinstance(size, int) and 0 < size <= ARCHIVE_LIMIT
            and receipt.get("cleanup") == {"status": "removed", "verified_export_sha256": provenance["files"]["image.tar"],
                                           "verified_export_bytes": size}
            and not (bundle / "image.tar").exists(), "export retention/cleanup identity receipt mismatch")
    packed = bundle / "image.tar.gz"
    if retain:
        require(file_digest(packed) == receipt.get("image_tar_gz_sha256"), "retained representative image hash mismatch")
        verify_gzip(packed, receipt["image_tar_sha256"], size, limit=ARCHIVE_LIMIT)
    else:
        require(not packed.exists() and receipt.get("replay") == "not retained; no exact image replay or rescan"
                and "image_tar_gz_sha256" not in receipt, "unretained export has false replay/retention claim")
    return receipt


def validate_runtime(campaign, case, helper_sha):
    directory = campaign / case
    runtime = bounded_json(directory / "runtime.json")
    validate_span(runtime)
    binding = bounded_json(directory / "runtime-identity.json")
    final = bounded_json(directory / STAGES[1] / "assessment.json")
    bundle = directory / (STAGES[1] + "-bundle")
    provenance = bounded_json(bundle / "provenance.json")
    inspected = bounded_json(directory / "runtime-image-inspect.stdout")
    require(isinstance(inspected, list) and len(inspected) == 1, "runtime inspection receipt malformed")
    require(runtime.get("status") == "passed" and runtime.get("image_id") == binding.get("assessed_config_id")
            == final["image"]["image_id"] and runtime.get("docker_image_id") == binding.get("docker_image_id") == inspected[0]["Id"]
            and runtime.get("runtime_helper_sha") == binding.get("runtime_helper_sha") == helper_sha
            and binding.get("generator_sha") == final["generator_sha"]
            and binding.get("collector_sha") == final.get("collector_sha", final["generator_sha"])
            and binding.get("export_sha256") == provenance["files"]["image.tar"]
            and binding.get("jar_sha256") == final["image"]["jar_sha256"] and binding.get("rootfs") == final["image"]["rootfs"]
            and binding.get("inspection_sha256") == file_digest(directory / "runtime-image-inspect.stdout")
            and file_digest(bundle / "image-config.json") == final["image"]["config_sha256"]
            and runtime.get("runtime_identity_sha256") == file_digest(directory / "runtime-identity.json")
            and runtime.get("uid", "").isdigit() and int(runtime["uid"]) != 0
            and runtime.get("default_user") is True and runtime.get("default_entrypoint") is True
            and runtime.get("application_health") == "UP" and runtime.get("schema_settings") == "generated defaults",
            "representative runtime/source/export identity incomplete")
    validate_runtime_inspection(binding, inspected[0], bounded_json(bundle / "image-config.json"),
                                evidence_bytes(directory / "runtime-manifest.json"))
    require(binding.get("default_launch") == config_semantics({key: inspected[0]["Config"].get(key)
            for key in ("User", "Entrypoint", "WorkingDir", "Healthcheck", "Cmd")}), "runtime default launch receipt mismatch")
    create = bounded_json(directory / "runtime-create.receipt.json")
    command = create.get("command", [])
    require(create.get("exit_code") == 0 and "--pull=never" in command and command[-1] == binding["docker_image_id"]
            and "--user" not in command and "--entrypoint" not in command, "runtime immutable no-pull create receipt missing")
    state = bounded_json(directory / "runtime-created-state.stdout")
    require(isinstance(state, list) and len(state) == 1, "created container identity receipt missing")
    verify_container_launch(state[0], binding)
    checked = bounded_json(directory / "runtime-created-state.receipt.json")
    started = bounded_json(directory / "runtime-start.receipt.json")
    require(checked.get("exit_code") == started.get("exit_code") == 0
            and checked.get("stdout_sha256") == file_digest(directory / "runtime-created-state.stdout")
            and validate_span(checked)[1] <= validate_span(started)[0], "container identity was not verified before start")
    return runtime


def validate_continuation(campaign, summary):
    lineage = summary.get("continuation")
    if not lineage:
        return None
    prior = bounded_json(campaign / "prior-campaign.json")
    require(file_digest(campaign / "prior-campaign.json") == lineage.get("prior_campaign_sha256")
            and prior.get("generator_sha") == prior.get("collector_sha") == REUSE_SHA
            and prior.get("status") == "incomplete" and prior.get("exit_code") == 2 and prior.get("campaign_complete") is False
            and prior.get("coverage_sha256") == summary["coverage_sha256"]
            and prior.get("cases") == [{"case": REUSE_CASE, "stages": {stage: 1 for stage in STAGES}}],
            "prior failed campaign/source lineage mismatch")
    reuse = bounded_json(campaign / REUSE_CASE / "reuse.json")
    require(file_digest(campaign / REUSE_CASE / "reuse.json") == lineage.get("reuse_sha256")
            and reuse.get("prior_campaign_sha256") == lineage["prior_campaign_sha256"]
            and reuse.get("generator_sha") == reuse.get("collector_sha") == REUSE_SHA
            and reuse.get("runtime_helper_sha") == (CAPACITY_RUNTIME_SHA if summary.get("capacity_continuation")
                                                    else summary["generator_sha"]), "copied case provenance mismatch")
    files = reuse.get("files")
    require(isinstance(files, list) and files and len(files) < 1000, "reused case file manifest missing")
    seen = set()
    for entry in files:
        name = entry["file"]
        require(isinstance(name, str) and not Path(name).is_absolute() and ".." not in Path(name).parts
                and name not in seen and sha(entry.get("sha256")), "unsafe or duplicate reused file receipt")
        seen.add(name)
        path = campaign / REUSE_CASE / name
        require(not path.is_symlink(), "reused evidence is a symlink")
        if path.name == "image.tar" and not path.exists():
            retained = bounded_json(path.parent / "image-retention.json")
            require(retained.get("image_tar_sha256") == entry["sha256"] and retained.get("image_tar_bytes") == entry["bytes"],
                    "reused export retention differs from original")
        else:
            require((file_digest(path) if path.exists() else evidence_digest(path)) == entry["sha256"],
                    "reused original file hash mismatch")
            require((path.stat().st_size if path.exists() else len(evidence_bytes(path))) == entry["bytes"],
                    "reused original file size mismatch")
    required = {f"{stage}/assessment.json" for stage in STAGES} | {
        f"{stage}-bundle/{name}" for stage in STAGES for name in (*BUNDLE_JSON, "image.tar", "source.tar", "input.tar", "provenance.json")}
    required |= {f"{stage}/{name}" for stage in STAGES for name in STAGE_JSON}
    require(required | {"prior-runtime/runtime.json"} <= seen, "reused case manifest omits required original evidence")
    old_runtime = bounded_json(campaign / REUSE_CASE / "prior-runtime/runtime.json")
    require(old_runtime.get("status") == "incomplete"
            and file_digest(campaign / REUSE_CASE / "prior-runtime/runtime.json") == reuse.get("prior_runtime_sha256"),
            "original failed runtime was modified or discarded")
    return prior


def validate_completed_capacity_case(campaign, summary, row, *, tools=None, databases=None):
    """Only the finalized first case from the fixed 4f capacity stop is reusable."""
    require(summary.get("generator_sha") == summary.get("collector_sha") == summary.get("runtime_helper_sha") == CAPACITY_RUNTIME_SHA
            and not summary.get("capacity_continuation")
            and summary.get("status") == "incomplete" and summary.get("exit_code") == 2
            and summary.get("campaign_complete") is False
            and summary.get("failure") == "disk safety floor reached; stop without pruning other resources"
            and summary.get("generator_shas") == [REUSE_SHA]
            and summary.get("continuation", {}).get("case") == REUSE_CASE
            and summary["continuation"].get("generator_sha") == summary["continuation"].get("collector_sha") == REUSE_SHA
            and summary["continuation"].get("runtime_helper_sha") == CAPACITY_RUNTIME_SHA
            and summary.get("cases") == [{"case": REUSE_CASE, "generator_sha": REUSE_SHA, "collector_sha": REUSE_SHA,
                                         "scans_reused": True, "stages": {stage: 1 for stage in STAGES}}]
            and row["case"] == REUSE_CASE, "only the original completed first-case capacity stop may continue")
    prior = validate_continuation(campaign, summary)
    scan_start, scan_end = validate_span(prior)
    capacity_start, capacity_end = validate_span(summary)
    require(scan_end <= capacity_start, "original scan and capacity runtime chronology mismatch")
    validated = []
    for stage in STAGES:
        report, data, _ = validate_stage(campaign, row, stage, REUSE_SHA)
        start, end = validate_span(report)
        require(scan_start <= start <= end <= scan_end and report["exit_code"] == 1,
                "completed first-case scan span/status mismatch")
        if tools is None:
            tools, databases = report["tools"], data["databases.json"]
        require(report["tools"] == tools and data["databases.json"] == databases,
                "completed first-case tool/DB snapshot mismatch")
        validated.append((report, data))
    require(validated[0][0]["image"]["jar_sha256"] == validated[1][0]["image"]["jar_sha256"]
            and validated[0][1]["packaged.json"] == validated[1][1]["packaged.json"]
            and all(validated[0][1]["provenance.json"]["files"][name] == validated[1][1]["provenance.json"]["files"][name]
                    for name in ("source.tar", "input.tar", "Dockerfile", *BUNDLE_JSON) if name != "image-config.json" and name != "image-manifest.json"),
            "completed first-case build/final source or inventory mismatch")
    runtime = validate_runtime(campaign, REUSE_CASE, CAPACITY_RUNTIME_SHA)
    start, end = validate_span(runtime)
    require(capacity_start <= start <= end <= capacity_end, "completed runtime lies outside original capacity span")
    return prior


def validate_capacity_continuation(campaign, summary, row):
    lineage = summary.get("capacity_continuation")
    if not lineage:
        return None
    prior_path = campaign / "capacity-prior-campaign.json"
    prior = bounded_json(prior_path)
    require(lineage.get("case") == REUSE_CASE
            and lineage.get("generator_sha") == lineage.get("collector_sha") == REUSE_SHA
            and lineage.get("runtime_helper_sha") == CAPACITY_RUNTIME_SHA
            and file_digest(prior_path) == lineage.get("prior_campaign_sha256")
            and prior.get("coverage_sha256") == summary["coverage_sha256"]
            and prior.get("continuation") == summary.get("continuation"), "capacity parent receipt/lineage mismatch")
    validate_completed_capacity_case(campaign, prior, row)
    require(validate_span(prior)[1] <= validate_span(summary)[0], "capacity continuation chronology mismatch")
    path = campaign / REUSE_CASE / "completed-case-copy.json"
    require(file_digest(path) == lineage.get("copy_manifest_sha256"), "completed case copy receipt mismatch")
    copied = bounded_json(path)
    require(copied.get("prior_campaign_sha256") == lineage["prior_campaign_sha256"], "completed copy parent mismatch")
    files = copied.get("files")
    require(isinstance(files, list) and 0 < len(files) < 1000, "completed case file manifest missing")
    expected = set()
    for entry in files:
        name = entry["file"]
        require(isinstance(name, str) and name and not Path(name).is_absolute() and ".." not in Path(name).parts
                and name not in expected and sha(entry.get("sha256")), "unsafe completed case file receipt")
        expected.add(name)
        target = campaign / REUSE_CASE / name
        require(target.is_file() and not target.is_symlink() and file_digest(target) == entry["sha256"]
                and target.stat().st_size == entry["bytes"], "completed case copy changed")
    actual = set()
    for target in (campaign / REUSE_CASE).rglob("*"):
        require(not target.is_symlink(), "completed case contains a symlink")
        if target.is_file() and target != path:
            actual.add(str(target.relative_to(campaign / REUSE_CASE)))
    require(actual == expected, "completed case copy file set mismatch")
    return prior


def validate_kafka_prior(campaign, summary, declaration, *, tools=None, databases=None, failure_directory=None):
    """Accept only the nine finalized ee cases followed by the recorded Kafka gap."""
    expected = [{**binding, "stages": {stage: 1 for stage in STAGES}} for binding in kafka_reuse_bindings()]
    expected[0].update(scans_reused=True, runtime_reused=True)
    expected.append({"case": "kafka-h2-j17", "generator_sha": KAFKA_PRIOR_SHA, "collector_sha": KAFKA_PRIOR_SHA,
                     "runtime_helper_sha": None, "stages": {STAGES[0]: 2}})
    require(summary.get("generator_sha") == summary.get("collector_sha") == summary.get("runtime_helper_sha") == KAFKA_PRIOR_SHA
            and summary.get("cases") == expected and not summary.get("kafka_continuation")
            and summary.get("generator_shas") == sorted([REUSE_SHA, KAFKA_PRIOR_SHA])
            and summary.get("runtime_helper_shas") == sorted([CAPACITY_RUNTIME_SHA, KAFKA_PRIOR_SHA])
            and summary.get("campaign_complete") is False and summary.get("status") == "incomplete" and summary.get("exit_code") == 2
            and summary.get("failure") == "required scan/inventory incomplete; diagnose before affected-only repair",
            "only the exact nine-case Kafka extraction stop may continue")
    rows = {row["case"]: row for row in declaration["cases"]}
    original = validate_continuation(campaign, summary)
    capacity = validate_capacity_continuation(campaign, summary, rows[REUSE_CASE])
    require(capacity is not None, "Kafka cohort original capacity lineage missing")
    old_start, old_end = validate_span(summary)
    for binding in kafka_reuse_bindings():
        pair = []
        for stage in STAGES:
            report, data, _ = validate_stage(campaign, rows[binding["case"]], stage, binding["generator_sha"])
            require(report.get("collector_sha", binding["collector_sha"]) == binding["collector_sha"] and report["exit_code"] == 1,
                    "Kafka cohort collector/stage status mismatch")
            start, end = validate_span(report)
            span_start, span_end = validate_span(original) if binding["case"] == REUSE_CASE else (old_start, old_end)
            require(span_start <= start <= end <= span_end, "Kafka cohort stage span mismatch")
            if tools is None:
                tools, databases = report["tools"], data["databases.json"]
            require(tools == report["tools"] and databases == data["databases.json"], "Kafka cohort tool/DB mismatch")
            pair.append((report, data))
        require(pair[0][0]["image"]["jar_sha256"] == pair[1][0]["image"]["jar_sha256"]
                and pair[0][1]["packaged.json"] == pair[1][1]["packaged.json"]
                and all(pair[0][1]["provenance.json"]["files"][name] == pair[1][1]["provenance.json"]["files"][name]
                        for name in ("Dockerfile", "source.tar", "input.tar", "generation.json", "resolved-inventory.json",
                                     "dependency-policy.json", "base-images.json", "retained-maven-bom.json")),
                "Kafka cohort build/final source or packaged inventory mismatch")
        if binding["runtime_helper_sha"]:
            runtime = validate_runtime(campaign, binding["case"], binding["runtime_helper_sha"])
            start, end = validate_span(runtime)
            span_start, span_end = validate_span(capacity) if binding["case"] == REUSE_CASE else (old_start, old_end)
            require(span_start <= start <= end <= span_end, "Kafka cohort runtime span mismatch")
    failed = failure_directory or campaign / "kafka-h2-j17" / STAGES[0]
    report = bounded_json(failed / "assessment.json")
    require(report.get("case") == "kafka-h2-j17" and report.get("stage") == STAGES[0]
            and report.get("generator_sha") == report.get("collector_sha") == KAFKA_PRIOR_SHA
            and report.get("status") == "incomplete" and report.get("exit_code") == 2
            and report.get("failure") == "required per-app application/test coordinate vulnerability-extractor coverage incomplete"
            and report.get("tools") == tools, "original failed Kafka assessment mismatch")
    start, end = validate_span(report)
    require(old_start <= start <= end <= old_end, "original failed Kafka span mismatch")
    receipts = retained_integrity(failed, report, complete=False)
    require({"syft.json", "grype.json", "trivy.json", "databases.json", "provenance.json", "packaged.json"} <= set(receipts)
            and bounded_json(failed / "databases.json") == databases, "original failed Kafka evidence/DB mismatch")


def validate_kafka_continuation(campaign, summary, declaration):
    lineage = summary.get("kafka_continuation")
    if not lineage:
        return None
    prior_path = campaign / "kafka-prior-campaign.json"
    prior = bounded_json(prior_path)
    require(lineage.get("reuse_cases") == kafka_reuse_bindings()
            and file_digest(prior_path) == lineage.get("prior_campaign_sha256")
            and prior.get("coverage_sha256") == summary["coverage_sha256"]
            and all(prior.get(key) == summary.get(key) for key in ("continuation", "capacity_continuation")),
            "Kafka cohort receipt/source lineage mismatch")
    validate_kafka_prior(campaign, prior, declaration, failure_directory=campaign / "prior-kafka-failure" / STAGES[0])
    require(validate_span(prior)[1] <= validate_span(summary)[0], "Kafka continuation chronology mismatch")
    path = campaign / "kafka-cohort-copy.json"
    require(file_digest(path) == lineage.get("copy_manifest_sha256"), "Kafka cohort copy receipt mismatch")
    manifest = bounded_json(path)
    require(manifest.get("prior_campaign_sha256") == lineage["prior_campaign_sha256"], "Kafka cohort copy parent mismatch")
    files = manifest.get("files")
    require(isinstance(files, list) and 0 < len(files) < 10000, "Kafka cohort file manifest missing")
    expected = set()
    roots = {*KAFKA_REUSE_CASES, "prior-kafka-failure"}
    root_files = {"prior-campaign.json", "capacity-prior-campaign.json", "kafka-prior-campaign.json"}
    for entry in files:
        name = entry["file"]
        require(isinstance(name, str) and name and not Path(name).is_absolute() and ".." not in Path(name).parts
                and (Path(name).parts[0] in roots or name in root_files) and name not in expected and sha(entry.get("sha256")),
                "unsafe or duplicate Kafka cohort file receipt")
        expected.add(name)
        target = campaign / name
        require(target.is_file() and not target.is_symlink() and file_digest(target) == entry["sha256"]
                and target.stat().st_size == entry["bytes"], "Kafka cohort copied bytes changed")
    actual = set(root_files)
    for root in roots:
        for target in (campaign / root).rglob("*"):
            require(not target.is_symlink(), "Kafka cohort contains a symlink")
            if target.is_file():
                actual.add(str(target.relative_to(campaign)))
    require(actual == expected, "Kafka cohort copied file set mismatch")
    return prior


def verify_storage_manifest(prior, manifest, expected_hash):
    require(file_digest(manifest) == expected_hash, "storage prior file manifest hash mismatch")
    records = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, "malformed storage prior file manifest")
        path = Path(match[2])
        require(path.is_absolute() and path.is_relative_to(prior) and ".." not in path.parts,
                "storage prior manifest escapes exact campaign")
        name = str(path.relative_to(prior))
        require(name not in records and path.is_file() and not path.is_symlink() and file_digest(path) == match[1],
                "storage prior manifest file missing, duplicate or changed")
        records[name] = {"sha256": match[1], "bytes": path.stat().st_size}
    require(records and "campaign.json" in records, "storage prior manifest empty or missing receipt")
    return records


def validate_storage_failure(directory):
    report = bounded_json(directory / "assessment.json")
    require(report.get("case") == STORAGE_PARTIAL_CASE and report.get("stage") == STAGES[1]
            and report.get("generator_sha") == report.get("collector_sha") == STORAGE_PRIOR_SHA
            and report.get("status") == "incomplete" and report.get("exit_code") == 2
            and report.get("failure") == "tool execution unavailable", "original storage failure must remain failed")
    entries = report.get("retained_raw")
    require(isinstance(entries, list) and entries and len({entry["file"] for entry in entries}) == len(entries),
            "original failed storage receipts missing or duplicate")
    observed = None
    for entry in entries:
        name = entry["file"]
        require(Path(name).name == name and name not in {".", ".."}, "unsafe original failed storage path")
        raw, packed = directory / name, directory / (name + ".gz")
        require(raw.is_file() and not raw.is_symlink() and file_digest(packed) == entry["gzip_sha256"], "failed storage original bytes missing")
        verify_gzip(packed, entry["sha256"], entry["bytes"])
        if name == "syft.json":
            require(entry["bytes"] == 0 and entry["sha256"] == digest(b"") and raw.stat().st_size > 0
                    and file_digest(raw) != entry["sha256"], "original failed Syft contradiction was repaired or lost")
            observed = {"status": "FAILED only; contradictory output is not assessment coverage",
                        "recorded_bytes": entry["bytes"], "recorded_sha256": entry["sha256"],
                        "actual_bytes": raw.stat().st_size, "actual_sha256": file_digest(raw),
                        "original_gzip_sha256": entry["gzip_sha256"], "original_errno": "unknown; not recoverable"}
        else:
            require(file_digest(raw) == entry["sha256"] and raw.stat().st_size == entry["bytes"], "failed storage original changed")
    require(observed is not None and bounded_json(directory / "syft.receipt.json").get("failure") == "execution unavailable",
            "original failed Syft command receipt missing")
    return observed


def validate_storage_prior(campaign, summary, declared, *, tools=None, databases=None, finalized=False):
    expected = [{**binding, "stages": {stage: 1 for stage in STAGES}, "scans_reused": True,
                 "runtime_reused": binding["runtime_helper_sha"] is not None} for binding in kafka_reuse_bindings()]
    expected += [{"case": case, "generator_sha": STORAGE_PRIOR_SHA, "collector_sha": STORAGE_PRIOR_SHA,
                  "runtime_helper_sha": None, "stages": {stage: 1 for stage in STAGES}}
                 for case in ("kafka-h2-j17", "kafka-pg-j17", STORAGE_PARTIAL_CASE)]
    expected[-1]["stages"][STAGES[1]] = 2
    require(summary.get("cases") == expected and not summary.get("storage_continuation")
            and summary.get("generator_sha") == summary.get("collector_sha") == summary.get("runtime_helper_sha") == STORAGE_PRIOR_SHA
            and summary.get("status") == "incomplete" and summary.get("exit_code") == 2 and summary.get("campaign_complete") is False
            and summary.get("failure") == "required scan/inventory incomplete; diagnose before affected-only repair"
            and summary.get("generator_shas") == sorted([REUSE_SHA, KAFKA_PRIOR_SHA, STORAGE_PRIOR_SHA])
            and summary.get("runtime_helper_shas") == sorted([CAPACITY_RUNTIME_SHA, KAFKA_PRIOR_SHA]),
            "only the exact 23-assessment storage stop may continue")
    require(validate_kafka_continuation(campaign, summary, declared) is not None, "23-stage original Kafka lineage missing")
    first = bounded_json(campaign / REUSE_CASE / STAGES[0] / "assessment.json")
    first_db = bounded_json(campaign / REUSE_CASE / STAGES[0] / "databases.json")
    tools, databases = (first["tools"] if tools is None else tools), (first_db if databases is None else databases)
    require(first["tools"] == tools and first_db == databases, "storage prior tool/DB snapshot mismatch")
    rows = {row["case"]: row for row in declared["cases"]}
    parent_start, parent_end = validate_span(summary)
    for case in ("kafka-h2-j17", "kafka-pg-j17", STORAGE_PARTIAL_CASE):
        validated = []
        for stage in STAGES if case != STORAGE_PARTIAL_CASE else (STAGES[0],):
            report, data, _ = validate_stage(campaign, rows[case], stage, STORAGE_PRIOR_SHA,
                                            check_retention=finalized or case != STORAGE_PARTIAL_CASE)
            start, end = validate_span(report)
            require(parent_start <= start <= end <= parent_end and report["exit_code"] == 1
                    and report.get("collector_sha") == STORAGE_PRIOR_SHA and report["tools"] == tools and data["databases.json"] == databases,
                    "storage prior stage source/span/status/tool/DB mismatch")
            validated.append((report, data))
        if len(validated) == 2:
            require(validated[0][0]["image"]["jar_sha256"] == validated[1][0]["image"]["jar_sha256"]
                    and validated[0][1]["packaged.json"] == validated[1][1]["packaged.json"]
                    and all(validated[0][1]["provenance.json"]["files"][name] == validated[1][1]["provenance.json"]["files"][name]
                            for name in ("Dockerfile", "source.tar", "input.tar", "generation.json", "resolved-inventory.json",
                                         "dependency-policy.json", "base-images.json", "retained-maven-bom.json")), "storage prior case pair differs")
    failed = campaign / "prior-storage-failure" if (campaign / "prior-storage-failure").exists() else campaign / STORAGE_PARTIAL_CASE / STAGES[1]
    failure = validate_storage_failure(failed)
    failed_report = bounded_json(failed / "assessment.json")
    start, end = validate_span(failed_report)
    require(parent_start <= start <= end <= parent_end and failed_report["tools"] == tools, "failed storage source/span/tool mismatch")
    bundle = campaign / STORAGE_PARTIAL_CASE / (STAGES[1] + "-bundle")
    if not finalized:
        provenance = bounded_json(bundle / "provenance.json")
        require(file_digest(bundle / "image.tar") == provenance["files"]["image.tar"], "saved final export changed")
        actual, _ = image_archive(bundle / "image.tar", jar_path=provenance["jar_path"], stage=STAGES[1])
        require(actual == failed_report["image"], "saved final export actual image identity mismatch")
    build = bounded_json(campaign / STORAGE_PARTIAL_CASE / STAGES[0] / "assessment.json")
    require(build["image"]["jar_sha256"] == failed_report["image"]["jar_sha256"]
            and bounded_json(campaign / STORAGE_PARTIAL_CASE / STAGES[0] / "packaged.json") == bounded_json(failed / "packaged.json"),
            "preserved partial build/final application differs")
    return failure


def validate_storage_continuation(campaign, summary, declared, *, finalized=True):
    lineage = summary.get("storage_continuation")
    if not lineage:
        return None
    prior = bounded_json(campaign / "storage-prior-campaign.json")
    require(lineage.get("reuse_stages") == storage_reuse_bindings()
            and file_digest(campaign / "storage-prior-campaign.json") == lineage.get("prior_campaign_sha256")
            and file_digest(campaign / "storage-prior-files.sha256") == lineage.get("prior_manifest_sha256")
            and prior.get("coverage_sha256") == summary["coverage_sha256"]
            and all(prior.get(key) == summary.get(key) for key in ("continuation", "capacity_continuation", "kafka_continuation")),
            "23-stage storage receipt/manifest/source lineage mismatch")
    failure = validate_storage_prior(campaign, prior, declared, finalized=finalized)
    require(bounded_json(campaign / "storage-failure-observation.json") == failure, "failed Syft contradiction observation changed")
    require(validate_span(prior)[1] <= validate_span(summary)[0], "storage continuation chronology mismatch")
    manifest_path = campaign / "storage-copy.json"
    require(file_digest(manifest_path) == lineage.get("copy_manifest_sha256"), "storage copy receipt mismatch")
    manifest = bounded_json(manifest_path)
    require(manifest.get("prior_campaign_sha256") == lineage["prior_campaign_sha256"], "storage copy parent mismatch")
    original = {}
    original_root = Path(manifest["prior_root"])
    for line in (campaign / "storage-prior-files.sha256").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None and Path(match[2]).is_relative_to(original_root), "storage original manifest path mismatch")
        name = str(Path(match[2]).relative_to(original_root))
        require(name not in original and ".." not in Path(name).parts, "storage original manifest duplicate or unsafe path")
        original[name] = match[1]
    transform = bounded_json(campaign / "storage-partial-transformation.json") if finalized else None
    if finalized:
        build = campaign / STORAGE_PARTIAL_CASE / STAGES[0]
        require(transform.get("copy_manifest_sha256") == lineage["copy_manifest_sha256"]
                and transform.get("assessment_sha256") == file_digest(build / "assessment.json")
                and transform.get("report_retention_sha256") == file_digest(build / "report-retention.json")
                and transform.get("image_retention_sha256") == file_digest(campaign / STORAGE_PARTIAL_CASE / (STAGES[0] + "-bundle") / "image-retention.json")
                and transform.get("final_image_retention_sha256") == file_digest(campaign / STORAGE_PARTIAL_CASE / (STAGES[1] + "-bundle") / "image-retention.json")
                and transform.get("assessment_helper_sha") == summary["generator_sha"], "partial-stage retention transformation mismatch")
        validate_span(transform)
    names = set()
    files = manifest.get("files")
    require(isinstance(files, list) and 0 < len(files) < 20000, "storage copied file manifest missing")
    for entry in files:
        name = entry["file"]
        require(isinstance(name, str) and name and not Path(name).is_absolute() and ".." not in Path(name).parts
                and name not in names and sha(entry.get("sha256")), "unsafe or duplicate storage copied path")
        names.add(name)
        source = "campaign.json" if name == "storage-prior-campaign.json" else (
            f"{STORAGE_PARTIAL_CASE}/{STAGES[1]}/" + name.removeprefix("prior-storage-failure/") if name.startswith("prior-storage-failure/") else name)
        require(original.get(source) == entry["sha256"], "storage copy differs from approved original file manifest")
        target = campaign / name
        require(not target.is_symlink(), "storage copied file is a symlink")
        if target.is_file():
            require(file_digest(target) == entry["sha256"] and target.stat().st_size == entry["bytes"], "storage copied bytes changed")
        elif finalized and Path(name).parts[0] == STORAGE_PARTIAL_CASE:
            if target.name == "image.tar":
                retained = bounded_json(target.parent / "image-retention.json")
                require(retained.get("image_tar_sha256") == entry["sha256"] and retained.get("image_tar_bytes") == entry["bytes"],
                        "partial export cleanup differs from copied bytes")
            else:
                require(Path(name).parts[1] == STAGES[0] and evidence_digest(target) == entry["sha256"]
                        and len(evidence_bytes(target)) == entry["bytes"], "partial report transformation changed original bytes")
        else:
            raise ImageAssessmentError("required storage copied evidence missing")
    required = {f"{binding['case']}/{binding['stage']}/assessment.json" for binding in storage_reuse_bindings()}
    require(required | {"prior-storage-failure/assessment.json", "prior-storage-failure/syft.json", "prior-storage-failure/syft.json.gz"} <= names,
            "storage copy manifest omits preserved assessments or contradiction")
    selected = set()
    roots = {*STORAGE_PAIR_CASES, STORAGE_PARTIAL_CASE, "prior-kafka-failure"}
    root_files = {"prior-campaign.json", "capacity-prior-campaign.json", "kafka-prior-campaign.json", "kafka-cohort-copy.json"}
    for source in original:
        parts = Path(source).parts
        if "scan-scratch" in parts or not (parts[0] in roots or source in root_files or source == "campaign.json"):
            continue
        target = "storage-prior-campaign.json" if source == "campaign.json" else (
            "prior-storage-failure/" + source.removeprefix(f"{STORAGE_PARTIAL_CASE}/{STAGES[1]}/")
            if source.startswith(f"{STORAGE_PARTIAL_CASE}/{STAGES[1]}/") else source)
        selected.add(target)
    require(names == selected, "storage copied cohort file set differs from approved original manifest")
    extras = {f"{STORAGE_PARTIAL_CASE}/{STAGES[0]}/assessment.json.gz", f"{STORAGE_PARTIAL_CASE}/{STAGES[0]}/report-retention.json",
              *(f"{STORAGE_PARTIAL_CASE}/{stage}-bundle/image-retention.json" for stage in STAGES)} if finalized else set()
    for root in (*STORAGE_PAIR_CASES, STORAGE_PARTIAL_CASE, "prior-storage-failure"):
        for target in (campaign / root).rglob("*"):
            require(not target.is_symlink(), "storage preserved cohort contains a symlink")
            if not target.is_file() or root == STORAGE_PARTIAL_CASE and target.is_relative_to(campaign / root / STAGES[1]):
                continue
            require(str(target.relative_to(campaign)) in names | extras, "storage preserved cohort has unexpected added files")
    return prior


def publish(campaign, declaration, output, *, host_prefixes=()):
    campaign, output = campaign.resolve(), output.resolve()
    require(not output.exists() and not output.is_relative_to(campaign), "publication requires new independent output")
    declared = bounded_json(declaration)
    plan = make_plan(declared)
    summary = bounded_json(campaign / "campaign.json")
    composition = None
    if "composition" in summary or (campaign / "composition.json").exists():
        from scripts.assemble_generated_image_campaign import validate_composition
        composition = validate_composition(campaign, declaration)
    campaign_start, campaign_end = validate_span(summary)
    generator_sha = summary.get("generator_sha")
    require(isinstance(generator_sha, str) and re.fullmatch(r"[0-9a-f]{40}", generator_sha)
            and summary.get("campaign_complete") is True and summary.get("exit_code") in (0, 1)
            and summary.get("status") == ("complete-with-findings" if summary["exit_code"] else "complete-no-matches")
            and summary.get("coverage_sha256") == file_digest(declaration),
            "complete frozen campaign/declaration receipt required")
    observed = summary.get("cases")
    require(isinstance(observed, list) and len(observed) == 30
            and {item["case"] for item in observed} == {row["case"] for row in plan["cases"]}
            and all(set(item["stages"]) == set(STAGES) for item in observed), "campaign must contain exactly 30x2 observations")
    by_case = {item["case"]: item for item in observed}
    sources = campaign_case_sources(summary, declared)
    prior = validate_continuation(campaign, summary)
    capacity_prior = validate_capacity_continuation(campaign, summary, next(row for row in plan["cases"] if row["case"] == REUSE_CASE))
    kafka_prior = validate_kafka_continuation(campaign, summary, declared)
    storage_prior = validate_storage_continuation(campaign, summary, declared)
    expected, ledger = [], {}
    totals = Counter()
    tools, databases = None, None
    for row in plan["cases"]:
        build_identity = None
        for stage in STAGES:
            source = sources[row["case"]]["generator_sha"]
            report, data, _ = validate_stage(campaign, row, stage, source,
                                            assessment_helper_sha=stage_helper(summary, row["case"], stage, source))
            require(report.get("collector_sha", source) == sources[row["case"]]["collector_sha"],
                    "collector commit changed across campaign")
            stage_start, stage_end = validate_span(report)
            parent = prior if prior and row["case"] == REUSE_CASE else (kafka_prior if kafka_prior and row["case"] in KAFKA_REUSE_CASES else None)
            if storage_prior and (row["case"] in {"kafka-h2-j17", "kafka-pg-j17"} or row["case"] == STORAGE_PARTIAL_CASE and stage == STAGES[0]):
                parent = storage_prior
            span_start, span_end = validate_span(parent) if parent else (campaign_start, campaign_end)
            require(span_start <= stage_start <= stage_end <= span_end,
                    "stage UTC span lies outside campaign")
            require(by_case[row["case"]]["stages"][stage] == report["exit_code"], "campaign/stage exit mismatch")
            if tools is None:
                tools, databases = report["tools"], data["databases.json"]
            require(tools == report["tools"] and databases == data["databases.json"], "tool/database snapshot changed across campaign")
            shared = (report["image"]["jar_sha256"], data["packaged.json"], data["provenance.json"]["files"])
            if stage == STAGES[0]:
                build_identity = shared
            else:
                require(shared[:2] == build_identity[:2] and all(
                    shared[2][name] == build_identity[2][name] for name in (
                        "Dockerfile", "source.tar", "input.tar", "generation.json", "resolved-inventory.json",
                        "dependency-policy.json", "base-images.json", "retained-maven-bom.json")), "build/final source or packaged inventory mismatch")
            expected.append((row, stage, evidence_digest(campaign / row["case"] / stage / "assessment.json")))
            for finding in data["findings.json"]:
                key = json.dumps(finding, sort_keys=True)
                ledger.setdefault(key, {"finding": finding, "disposition": "OPEN; applicability and risk acceptance not established",
                                        "observations": []})["observations"].append({"case": row["case"], "stage": stage})
                totals[finding["scanner"]] += 1
    require(summary["exit_code"] == int(bool(ledger)), "campaign findings status mismatch")
    packaged = packaged_contract(campaign, declared, generator_sha, summary=summary) if summary.get("generator_shas") else packaged_contract(campaign, declared, generator_sha)
    require(bounded_json(campaign / "packaged-inventories.json") == packaged, "30-case packaged contract mismatch")
    for case in RUNTIME_CASES:
        runtime = validate_runtime(campaign, case, sources[case]["runtime_helper_sha"])
        start, end = validate_span(runtime)
        parent = capacity_prior if capacity_prior and case == REUSE_CASE else (kafka_prior if kafka_prior and case in KAFKA_REUSE_CASES else None)
        span_start, span_end = validate_span(parent) if parent else (campaign_start, campaign_end)
        require(span_start <= start <= end <= span_end, "runtime helper UTC span lies outside continuation")
    prefixes = sorted({str(Path(prefix).resolve()) for prefix in (
        str(campaign.parent), str(ROOT), str(Path.home()), "/private/var/folders")}
        # Explicit prefixes identify recorded bytes, possibly from another host.
        # Resolving them locally can rewrite symlinks and miss the original path.
        | {str(Path(prefix)) if Path(prefix).is_absolute() else str(Path(prefix).resolve())
           for prefix in host_prefixes},
        key=lambda prefix: (-len(prefix), prefix))
    require(all(prefix != "/" for prefix in prefixes), "root path is not a safe redaction prefix")
    recorded_roots = recorded_host_roots(campaign, plan["cases"])
    output.mkdir(parents=True)
    resource_check(campaign, extra_output=output)
    exports = []

    def emit(relative, value, original_hash, private_gzip_hash=None):
        payload = canonical(redact(value, prefixes))
        require_private_paths_redacted(payload, prefixes, recorded_roots)
        packed = compressed(payload)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(packed)
        resource_check(campaign, extra_output=output)
        exports.append({"file": relative, "private_original_sha256": original_hash,
                        "private_original_gzip_sha256": private_gzip_hash,
                        "sanitized_json_sha256": digest(payload), "sanitized_gzip_sha256": digest(packed)})

    for row, stage, assessed_hash in expected:
        directory = campaign / row["case"] / stage
        require(evidence_digest(directory / "assessment.json") == assessed_hash, "assessment changed during publication")
        source = sources[row["case"]]["generator_sha"]
        report, data, receipts = validate_stage(campaign, row, stage, source,
                                               assessment_helper_sha=stage_helper(summary, row["case"], stage, source))
        prefix = f"{row['case']}/{stage}/"
        emit(prefix + "assessment.json.gz", report, assessed_hash)
        for name in (*STAGE_JSON, *(CLASSIFIER_JSON if CLASSIFIER_JSON[0] in data else ())):
            emit(prefix + name + ".gz", data[name], receipts[name]["sha256"], receipts[name]["gzip_sha256"])
        for name in sorted(receipts):
            if name.endswith(".receipt.json"):
                emit(prefix + name + ".gz", bounded_json(directory / name),
                     receipts[name]["sha256"], receipts[name]["gzip_sha256"])
        emit(prefix + "recipe.json.gz", {"recipe": evidence_bytes(directory / "Dockerfile").decode("utf-8")},
             receipts["Dockerfile"]["sha256"], receipts["Dockerfile"]["gzip_sha256"])
        bundle = campaign / row["case"] / (stage + "-bundle")
        for name in BUNDLE_JSON:
            emit(prefix + name + ".gz", bounded_json(bundle / name), file_digest(bundle / name))
        emit(prefix + "image-retention.json.gz", bounded_json(bundle / "image-retention.json"),
             file_digest(bundle / "image-retention.json"))
        if (directory / "report-retention.json").exists():
            emit(prefix + "report-retention.json.gz", bounded_json(directory / "report-retention.json"),
                 file_digest(directory / "report-retention.json"))
    for case in RUNTIME_CASES:
        for name in RUNTIME_JSON:
            path = campaign / case / name
            emit(case + "/" + name + ".gz", bounded_json(path), file_digest(path))
    if prior:
        for name in ("prior-campaign.json", REUSE_CASE + "/reuse.json", REUSE_CASE + "/prior-runtime/runtime.json"):
            path = campaign / name
            emit(name + ".gz", bounded_json(path), file_digest(path))
    if capacity_prior:
        for name in ("capacity-prior-campaign.json", REUSE_CASE + "/completed-case-copy.json"):
            path = campaign / name
            emit(name + ".gz", bounded_json(path), file_digest(path))
    if kafka_prior:
        for name in ("kafka-prior-campaign.json", "kafka-cohort-copy.json"):
            path = campaign / name
            emit(name + ".gz", bounded_json(path), file_digest(path))
        failed = campaign / "prior-kafka-failure" / STAGES[0]
        failed_report = bounded_json(failed / "assessment.json")
        emit("prior-kafka-failure/" + STAGES[0] + "/assessment.json.gz", failed_report, file_digest(failed / "assessment.json"))
        for entry in failed_report["retained_raw"]:
            if entry["file"].endswith((".json", ".stdout")):
                value = bounded_json(failed / entry["file"]) if entry["file"].endswith(".json") else None
                if value is not None:
                    emit("prior-kafka-failure/" + STAGES[0] + "/" + entry["file"] + ".gz", value,
                         entry["sha256"], entry["gzip_sha256"])
    if storage_prior:
        for name in ("storage-prior-campaign.json", "storage-copy.json", "storage-failure-observation.json", "storage-partial-transformation.json",
                     "prior-storage-failure/assessment.json", "prior-storage-failure/syft.receipt.json"):
            path = campaign / name
            emit(name + ".gz", bounded_json(path), file_digest(path))
    if composition is not None:
        for name in ("composition.json", "composition-copy-manifest.json",
                     "composition-inputs/first/campaign.json", "composition-inputs/remaining/campaign.json",
                     "composition-inputs/tls-failure/image-build.receipt.json"):
            emit(name + ".gz", bounded_json(campaign / name), file_digest(campaign / name))
        for stream in ("stdout", "stderr"):
            name = "composition-inputs/tls-failure/image-build." + stream
            emit(name + ".json.gz", {"text": evidence_bytes(campaign / name).decode("utf-8")},
                 file_digest(campaign / name))
    emit("campaign.json.gz", summary, file_digest(campaign / "campaign.json"))
    emit("coverage-declared.json.gz", declared, file_digest(declaration))
    emit("packaged-inventories.json.gz", packaged, file_digest(campaign / "packaged-inventories.json"))
    emit("open-findings.json.gz", list(ledger.values()), None)
    aggregate = {"cases": 30, "stage_observations": 60, "generator_sha": generator_sha,
                 "generator_shas": sorted({row["generator_sha"] for row in sources.values()}),
                 "generator_sha_semantics": summary.get("generator_sha_semantics", "campaign freeze; actual generators are recorded per case"),
                 "runtime_helper_sha": summary.get("runtime_helper_sha", generator_sha), "continuation": summary.get("continuation"),
                 "runtime_helper_shas": sorted({sources[case]["runtime_helper_sha"] for case in RUNTIME_CASES}),
                 "runtime_helpers_by_case": {case: sources[case]["runtime_helper_sha"] for case in RUNTIME_CASES},
                 "capacity_continuation": summary.get("capacity_continuation"),
                 "kafka_continuation": summary.get("kafka_continuation"),
                 "storage_continuation": summary.get("storage_continuation"),
                 "assessment_helpers_by_case": {case: value.get("assessment_helper_shas") for case, value in sources.items()}
                 if storage_prior else None,
                 "collector_sha": summary.get("collector_sha", generator_sha),
                 "started_at_utc": summary["started_at_utc"], "ended_at_utc": summary["ended_at_utc"],
                 "status": summary["status"], "match_observations_by_scanner": dict(sorted(totals.items())),
                 "distinct_finding_records": len(ledger), "disposition": "OPEN",
                 "release_acceptance": "not established",
                 "counting": "Scanner counts overlap; repeated case/stage observations are not unique vulnerabilities.",
                 "excluded": "Images, source/input tarballs, binaries, DB contents and raw logs remain private.",
                 "runtime_claim": "Health/nonroot startup and bounded read-only GET, not business certification."}
    aggregate["image_replay"] = (
        "The completed reduced campaign retains three representative final exports; its other 57 exports were removed after validated scans. "
        "Any retained failed-campaign archives are separate; their availability is recorded in dated evidence. "
        "No general replay promise for historical evidence or removed completed-campaign exports.")
    if composition is not None:
        aggregate["composition"] = {
            "kind": composition["kind"], "inputs": composition["inputs"],
            "completion_semantics": composition["completion_semantics"],
            "assessment_execution": "40 original validated assessments plus 20 affected-only assessments; no completed scans or startups repeated",
        }
    require_private_paths_redacted(canonical(aggregate), prefixes, recorded_roots)
    write_json(output / "summary.json", aggregate)
    (output / "summary.txt").write_text(
        f"30 cases / 60 stage observations: {summary['status']}\n"
        f"{len(ledger)} distinct finding records; all OPEN pending applicability/policy review.\n"
        "Scanner match counts overlap and must not be summed as unique vulnerabilities.\n"
        "No release clearance or business certification.\n", encoding="utf-8")
    publication = {"schema_version": 1, "status": "complete",
               "generator_sha": generator_sha, "files": exports,
               "summary_sha256": file_digest(output / "summary.json"),
               "summary_text_sha256": file_digest(output / "summary.txt"),
               "hash_semantics": "private_original hashes identify untouched private bytes; sanitized hashes identify exported bytes"}
    resource_check(campaign, extra_output=output, pending_bytes=len(canonical(publication)))
    require_private_paths_redacted(canonical(publication), prefixes, recorded_roots)
    write_json(output / "publication.json", publication)
    return aggregate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("campaign", "declaration", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--host-prefix", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        publish(args.campaign, args.declaration, args.output, host_prefixes=args.host_prefix)
        return 0
    except Exception:
        print("Image publication rejected: incomplete, mismatched or unsafe evidence; originals unchanged.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
