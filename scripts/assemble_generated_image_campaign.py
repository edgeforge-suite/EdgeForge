#!/usr/bin/env python3
"""Offline assembly of the fixed cc772 TLS-stop 20+10 image campaign only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath

SOURCE = "cc7721682f21009c6ad918ad021631213ff327a1"
COVERAGE = "85137707a8e8a965cda5f32f366f6f8cfee871be12ffd6e32527bedf35d8fdc5"
FIRST_RECEIPT = "58eac8349d0fc888a5490e51b74b87b217fb8e5a2955580e940b509101d32194"
FAILURE_RECEIPT = "1df0eaff6470bb9dd54b59ec286d00111d4819fccb4804c5a8e67ebc23d872fa"
FAILURE_STDERR = "7994f9c4bfe98bc1686db309eb1b3b36763958497a9d1a7fb51b3f2d79045119"
FAILED_CASE = "file-batch-pg-j21"
FIRST_CASES = (
    "crud-h2-j17", "crud-pg-j17", "crud-pg-j21", "crud-soap-h2-j17",
    "crud-soap-pg-j17", "crud-soap-pg-j21", "passthrough-h2-j17",
    "passthrough-pg-j17", "passthrough-pg-j21", "kafka-h2-j17",
    "kafka-pg-j17", "kafka-pg-j21", "kafka-router-h2-j17",
    "kafka-router-pg-j17", "kafka-router-pg-j21", "ordinary-batch-h2-j17",
    "ordinary-batch-pg-j17", "ordinary-batch-pg-j21", "file-batch-h2-j17",
    "file-batch-pg-j17",
)
KIND = "cc772-public-tls-fixed-20-plus-10-v1"
# Preserve validation of the immutable October 17 composition after CLI repairs.
# This is one known replay tool, not permission to trust arbitrary source hashes.
REPLAY_ASSEMBLER_SHA256 = "b1a3c7acbf84e10e3dc0248a729dccd56a1256adbbcc91f56dddd47a4023653e"
MANIFEST = "composition-copy-manifest.json"
MAX_FILES = 100000
FREE_FLOOR = 20 * 1024**3


class AssemblyError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AssemblyError(message)


def helpers():
    # Local imports allow the publisher to call this validator without a cycle.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts import assess_generated_images as images
    from scripts import publish_generated_image_evidence as publisher
    return images, publisher


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def safe_path(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)), "symlink in path")
    return path


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), "evidence directory missing or unsafe")
    result = []
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(parent) / name
            mode = path.lstat().st_mode
            require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), "nonregular evidence or symlink")
            if stat.S_ISREG(mode):
                result.append({"file": path.relative_to(root).as_posix(),
                               "bytes": path.stat().st_size, "sha256": digest(path)})
                require(len(result) <= MAX_FILES, "evidence file count exceeds bound")
    return sorted(result, key=lambda row: row["file"])


def safe_name(name):
    require(isinstance(name, str) and name and "\\" not in name
            and not PurePosixPath(name).is_absolute()
            and all(part not in ("", ".", "..") for part in name.split("/")),
            "unsafe copy-manifest path")


def verify_manifest(root, rows):
    require(isinstance(rows, list) and rows, "empty copy manifest")
    seen = set()
    for row in rows:
        name = row["file"]
        safe_name(name)
        require(name not in seen, "duplicate copy-manifest path")
        seen.add(name)
        path = safe_path(root / name)
        require(type(row["bytes"]) is int and row["bytes"] >= 0
                and path.is_file() and path.stat().st_size == row["bytes"]
                and digest(path) == row["sha256"], "copied evidence checksum/length mismatch")


def failure(root):
    images, publisher = helpers()
    receipt_path = root / "image-build.receipt.json"
    require(digest(receipt_path) == FAILURE_RECEIPT, "original TLS receipt changed")
    value = images.read_json(receipt_path)
    publisher.validate_span(value)
    require(value.get("exit_code") == 1 and value.get("status") == "incomplete"
            and value.get("owned_child_reaped") is True, "TLS command status invalid")
    for kind in ("stdout", "stderr"):
        require(digest(root / ("image-build." + kind)) == value[kind + "_sha256"],
                "TLS command stream hash mismatch")
    require(digest(root / "image-build.stderr") == FAILURE_STDERR, "original TLS stderr changed")
    stderr = (root / "image-build.stderr").read_text()
    require('auth.docker.io/token?scope=repository%3Alibrary%2Fmaven%3Apull' in stderr
            and "net/http: TLS handshake timeout" in stderr
            and "load metadata for docker.io/library/maven:3.9.9-eclipse-temurin-21" in stderr,
            "not the authorized public Maven TLS failure")
    return value


def validate_records(first, remaining, declaration, case_root, failure_root):
    """Validate real partial receipts without manufacturing a 30-case input root."""
    images, publisher = helpers()
    plan = images.make_plan(declaration)
    declared = {row["case"]: row for row in plan["cases"]}
    expected = set(declared)
    require(set(FIRST_CASES) < expected and len(expected) == 30, "declared case matrix differs")
    wanted = (set(FIRST_CASES), expected - set(FIRST_CASES))
    require(len(wanted[1]) == 10 and FAILED_CASE in wanted[1], "remaining partition differs")
    snapshots = None
    fragments, observations, stage_bindings, runtime_bindings = [], {}, [], []
    for index, summary in enumerate((first, remaining)):
        start, end = publisher.validate_span(summary)
        require(summary.get("generator_sha") == summary.get("collector_sha")
                == summary.get("runtime_helper_sha") == SOURCE
                and summary.get("generator_shas") == [SOURCE]
                and summary.get("coverage_sha256") == COVERAGE
                and summary.get("declared_cases") == 30
                and summary.get("campaign_complete") is False and summary.get("exit_code") == 2
                and summary.get("equivalence_claim") is False, "fragment source/coverage/count/status mismatch")
        require(not any(summary.get(name) for name in (
            "continuation", "capacity_continuation", "kafka_continuation", "storage_continuation", "composition")),
            "nested/arbitrary continuation is unsupported")
        require(summary.get("status") == ("incomplete" if index == 0 else "partial-affected-scope"),
                "fragment status is not the fixed stopped/affected scope")
        require(not summary.get("cleanup_failure") and (index == 0 or not summary.get("failure")),
                "fragment records an additional failure")
        entries = summary["cases"]
        require(isinstance(entries, list) and len(entries) == len(wanted[index])
                and {entry["case"] for entry in entries} == wanted[index], "fragment overlap/missing/duplicate cases")
        scope = 0
        for entry in entries:
            case = entry["case"]
            helper = SOURCE if case in images.RUNTIME_CASES else None
            require(entry.get("generator_sha") == entry.get("collector_sha") == SOURCE
                    and entry.get("runtime_helper_sha") == helper
                    and set(entry["stages"]) == set(images.STAGES), "case source/helper/stage-count mismatch")
            require(case not in observations, "overlapping case")
            shared = []
            directory = case_root(index, case)
            require(directory.name == case, "case root differs")
            for stage in images.STAGES:
                report, data, _ = publisher.validate_stage(directory.parent, declared[case], stage, SOURCE,
                                                          check_retention=True, assessment_helper_sha=SOURCE)
                low, high = publisher.validate_span(report)
                require(start <= low <= high <= end, "stage timestamp outside original fragment")
                require(report.get("generator_sha") == report.get("collector_sha") == SOURCE
                        and report.get("assessment_helper_sha", SOURCE) == SOURCE
                        and report.get("case") == case and report.get("stage") == stage
                        and type(report.get("exit_code")) is int and report["exit_code"] in (0, 1)
                        and type(entry["stages"][stage]) is int
                        and entry["stages"][stage] == report["exit_code"]
                        and report.get("status") == ("complete-with-findings" if report["exit_code"]
                                                     else "complete-no-matches"), "stage exit/source/status mismatch")
                current = (report["tools"], data["databases.json"])
                if snapshots is None:
                    snapshots = current
                require(current == snapshots, "tool/database snapshots differ")
                scope = max(scope, report["exit_code"])
                shared.append((report["image"]["jar_sha256"], data["packaged.json"], data["provenance.json"]["files"]))
                stage_bindings.append({"case": case, "stage": stage, "fragment": index,
                                       "assessment_sha256": digest(directory / stage / "assessment.json"),
                                       "started_at_utc": report["started_at_utc"],
                                       "ended_at_utc": report["ended_at_utc"],
                                       "image_id": report["image"]["image_id"],
                                       "jar_sha256": report["image"]["jar_sha256"], "source_sha": SOURCE})
            require(shared[0][:2] == shared[1][:2] and all(shared[0][2][name] == shared[1][2][name] for name in (
                "Dockerfile", "source.tar", "input.tar", "generation.json", "resolved-inventory.json",
                "dependency-policy.json", "base-images.json", "retained-maven-bom.json")), "stage pair/source inventory mismatch")
            if helper:
                runtime = publisher.validate_runtime(directory.parent, case, SOURCE)
                low, high = publisher.validate_span(runtime)
                final_span = publisher.validate_span(images.read_json(directory / images.STAGES[1] / "assessment.json"))
                require(start <= low <= high <= end and final_span[1] <= low,
                    "runtime outside original fragment/final assessment")
                require(runtime.get("runtime_helper_sha") == SOURCE and runtime.get("status") == "passed",
                        "runtime helper/status mismatch")
                runtime_bindings.append({"case": case, "fragment": index, "source_sha": SOURCE,
                                         "runtime_sha256": digest(directory / "runtime.json"),
                                         "started_at_utc": runtime["started_at_utc"], "ended_at_utc": runtime["ended_at_utc"]})
            else:
                require(not any(directory.glob("runtime.json*"))
                        and not any(directory.glob("runtime-identity.json*")), "undeclared or repeated runtime")
            observations[case] = copy.deepcopy(entry)
        require(summary.get("runtime_helper_shas") == ([SOURCE] if index == 0 else []), "runtime source-set mismatch")
        if index == 1:
            require(type(summary.get("affected_scope_exit_code")) is int
                    and summary["affected_scope_exit_code"] == scope, "affected-scope exit contradicts completed stages")
        fragments.append({"observed_scope_exit_code": scope,
                          "started_at_utc": summary["started_at_utc"], "ended_at_utc": summary["ended_at_utc"]})
    require(len(stage_bindings) == 60 and {r["case"] for r in runtime_bindings} == set(images.RUNTIME_CASES)
            and len(runtime_bindings) == 3, "assembled stage/runtime coverage incomplete")
    require(publisher.validate_span(first)[1] <= publisher.validate_span(remaining)[0], "fragment spans overlap or reverse")
    failed = failure(failure_root)
    low, high = publisher.validate_span(failed)
    require(publisher.validate_span(first)[0] <= low <= high <= publisher.validate_span(first)[1], "failure outside original fragment")
    result = copy.deepcopy(first)
    result.pop("failure", None)
    result.pop("affected_scope_exit_code", None)
    result.update(cases=[observations[row["case"]] for row in plan["cases"]],
                  started_at_utc=fragments[0]["started_at_utc"], ended_at_utc=fragments[1]["ended_at_utc"],
                  campaign_complete=True, exit_code=max(f["observed_scope_exit_code"] for f in fragments),
                  generator_sha_semantics="verified aggregate; original fragment outcomes remain unchanged",
                  completion_semantics="complete aggregate assessment coverage only; original campaigns did not complete; no clearance",
                  release_clearance=False, risk_accepted=False)
    result["status"] = "complete-with-findings" if result["exit_code"] else "complete-no-matches"
    images.campaign_case_sources(result, declaration)
    return result, fragments, stage_bindings, runtime_bindings


def prevalidate(first, remaining, declaration):
    images, _ = helpers()
    require(digest(declaration) == COVERAGE, "declaration checksum differs")
    require(digest(first / "campaign.json") == FIRST_RECEIPT, "original stopped root changed")
    originals = [inventory(root) for root in (first, remaining)]
    summaries = [images.read_json(root / "campaign.json") for root in (first, remaining)]
    for index, root in enumerate((first, remaining)):
        expected = set(FIRST_CASES) | {FAILED_CASE} if index == 0 else {
            row["case"] for row in summaries[index]["cases"]}
        require({path.name for path in root.iterdir() if path.is_dir()} == expected, "unexpected fragment case directory")
    failed = first / FAILED_CASE
    failed_bundle = failed / (images.STAGES[0] + "-bundle")
    require({row["file"] for row in inventory(failed_bundle)} == {
        "image-build.receipt.json", "image-build.stdout", "image-build.stderr"}
        and not any((failed / stage).exists() for stage in images.STAGES)
        and not (failed / (images.STAGES[1] + "-bundle")).exists(),
        "failed case is not the exact pre-export TLS shape")
    require(not any(failed.rglob("assessment.json*"))
            and not any(failed.rglob("image.tar*"))
            and not any(failed.rglob("build.iid"))
            and not any(path.is_file() and path.name.startswith(("syft.", "grype.", "trivy.", "grype-packaged."))
                        for path in failed.rglob("*")), "failed case contains export/scan credit")
    result = validate_records(*summaries, images.read_json(declaration),
                              lambda index, case: (first, remaining)[index] / case,
                              failed / (images.STAGES[0] + "-bundle"))
    require(originals == [inventory(root) for root in (first, remaining)], "input changed during validation")
    return result, originals


def _validate_composition(campaign, declaration, *, candidate=None):
    images, _ = helpers()
    campaign = safe_path(campaign)
    declaration = safe_path(declaration)
    require(digest(declaration) == COVERAGE, "declaration checksum differs")
    composition = images.read_json(campaign / "composition.json")
    require(composition.get("kind") == KIND and composition.get("source_sha") == SOURCE
            and composition.get("coverage_sha256") == COVERAGE
            and composition.get("assembly_source_sha256") in {digest(Path(__file__)), REPLAY_ASSEMBLER_SHA256},
            "assembly source/declaration mismatch")
    manifest_path = campaign / MANIFEST
    require(digest(manifest_path) == composition["copy_manifest_sha256"], "copy-manifest identity mismatch")
    manifest = images.read_json(manifest_path)
    verify_manifest(campaign, manifest["files"])
    first_cases = set(FIRST_CASES)
    remaining_cases = {row["case"] for row in images.make_plan(images.read_json(declaration))["cases"]} - first_cases
    for row in manifest["files"]:
        name = row["file"]
        head = name.split("/", 1)[0]
        if head in first_cases | remaining_cases:
            expected = ("first" if head in first_cases else "remaining", name)
        elif name in {f"composition-inputs/{label}/campaign.json" for label in ("first", "remaining")}:
            expected = (name.split("/")[1], "campaign.json")
        elif name in {"composition-inputs/tls-failure/image-build." + kind for kind in ("receipt.json", "stdout", "stderr")}:
            expected = ("first", f"{FAILED_CASE}/{images.STAGES[0]}-bundle/" + name.rsplit("/", 1)[1])
        else:
            raise AssemblyError("copy manifest contains an unsupported evidence path")
        require((row["fragment"], row["original_file"]) == expected, "copied file fragment lineage mismatch")
    files = {row["file"] for row in manifest["files"]}
    require(files == {row["file"] for row in inventory(campaign)
                      if row["file"] not in {MANIFEST, "composition.json", "campaign.json", "packaged-inventories.json"}},
            "assembled file set changed")
    require(set(composition["inputs"]) == {"first", "remaining"}, "exactly two fragment inputs required")
    for key in ("first", "remaining"):
        require(composition["inputs"][key]["receipt"] == f"composition-inputs/{key}/campaign.json"
                and digest(campaign / composition["inputs"][key]["receipt"]) == composition["inputs"][key]["sha256"],
                "fragment receipt hash mismatch")
    first = campaign / "composition-inputs/first/campaign.json"
    require(digest(first) == FIRST_RECEIPT, "original stopped receipt mismatch")
    remaining = campaign / "composition-inputs/remaining/campaign.json"
    derived, spans, stages, runtimes = validate_records(
        images.read_json(first), images.read_json(remaining), images.read_json(declaration),
        lambda index, case: campaign / case, campaign / "composition-inputs/tls-failure")
    require(composition["fragments"] == spans and composition["stages"] == stages
            and composition["runtimes"] == runtimes, "composition source/time/stage lineage mismatch")
    derived["composition"] = {"file": "composition.json", "sha256": digest(campaign / "composition.json")}
    root = images.read_json(campaign / "campaign.json") if candidate is None else candidate
    require(root == derived, "derived root differs from verified fragments")
    require(images.read_json(campaign / "packaged-inventories.json") == images.packaged_contract(
        campaign, images.read_json(declaration), SOURCE, summary=derived), "packaged contract differs")
    return composition


def validate_composition(campaign, declaration):
    """Publisher hook: verify only saved inputs/copies, never consult old paths."""
    return _validate_composition(campaign, declaration)


def assemble(first, remaining, declaration, output):
    images, _ = helpers()
    first, remaining, declaration, output = map(safe_path, (first, remaining, declaration, output))
    require(first != remaining and not first.is_relative_to(remaining) and not remaining.is_relative_to(first),
            "fragment roots overlap")
    require(not output.exists() and output.parent.is_dir()
            and all(not output.is_relative_to(root) and not root.is_relative_to(output) for root in (first, remaining)),
            "output must be new and independent of fragment roots")
    (derived, spans, stages, runtimes), originals = prevalidate(first, remaining, declaration)
    selected = []
    for index, root in enumerate((first, remaining)):
        label = ("first", "remaining")[index]
        for row in originals[index]:
            name = row["file"]
            head = name.split("/", 1)[0]
            if head in (set(FIRST_CASES) if index == 0 else {r["case"] for r in derived["cases"]} - set(FIRST_CASES)):
                target = name
            elif name == "campaign.json":
                target = f"composition-inputs/{label}/campaign.json"
            elif index == 0 and name in {f"{FAILED_CASE}/{images.STAGES[0]}-bundle/image-build.{kind}"
                                        for kind in ("receipt.json", "stdout", "stderr")}:
                target = "composition-inputs/tls-failure/" + name.rsplit("/", 1)[1]
            else:
                continue
            selected.append(({**row, "file": target, "fragment": label, "original_file": name}, root / name))
    require(len({row["file"] for row, _ in selected}) == len(selected), "copy destinations overlap")
    require(shutil.disk_usage(output.parent).free >= FREE_FLOOR + sum(row["bytes"] for row, _ in selected),
            "insufficient free space for copies plus unchanged 20GiB floor")
    output.mkdir()
    try:
        for row, source in selected:
            require(shutil.disk_usage(output).free >= FREE_FLOOR + row["bytes"], "assembly free-space floor reached")
            require(not source.is_symlink() and source.stat().st_size == row["bytes"]
                    and digest(source) == row["sha256"], "source changed before copying")
            target = output / row["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            require(target.stat().st_size == row["bytes"] and digest(target) == row["sha256"], "copied bytes differ")
        require(originals == [inventory(root) for root in (first, remaining)], "input changed during copy")
        manifest = {"schema_version": 1, "files": sorted((row for row, _ in selected), key=lambda row: row["file"])}
        write_json(output / MANIFEST, manifest)
        composition = {"schema_version": 1, "kind": KIND, "source_sha": SOURCE,
                       "assembly_source_sha256": digest(Path(__file__)),
                       "assembly_source_semantics": "exact offline assembler bytes; not generating/runtime source",
                       "coverage_sha256": COVERAGE, "copy_manifest_sha256": digest(output / MANIFEST),
                       "inputs": {label: {"receipt": f"composition-inputs/{label}/campaign.json",
                                          "sha256": digest(root / "campaign.json")}
                                  for label, root in (("first", first), ("remaining", remaining))},
                       "fragments": spans, "stages": stages, "runtimes": runtimes,
                       "failure_preservation": "composition-inputs/tls-failure; unchanged failed receipt/stdout/stderr",
                       "completion_semantics": derived["completion_semantics"], "release_clearance": False}
        write_json(output / "composition.json", composition)
        derived["composition"] = {"file": "composition.json", "sha256": digest(output / "composition.json")}
        write_json(output / "packaged-inventories.json", images.packaged_contract(
            output, images.read_json(declaration), SOURCE, summary=derived))
        # Public validation never accepts a missing root; only assembly can validate
        # the candidate before exposing a complete root as the final write.
        _validate_composition(output, declaration, candidate=derived)
        write_json(output / "campaign.json", derived)
    except BaseException as exc:
        if (output / "campaign.json").exists():
            (output / "campaign.json").unlink()
        write_json(output / "assembly-error.json", {"status": "incomplete", "exit_code": 2,
                   "error": str(exc), "campaign_complete": False, "release_clearance": False})
        raise
    return derived["exit_code"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("first", "remaining", "declaration", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return assemble(args.first, args.remaining, args.declaration, args.output)
    except Exception as exc:
        # Preserve SystemExit/interrupts, but never classify an ordinary crash as findings.
        print(f"Assembly incomplete: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
