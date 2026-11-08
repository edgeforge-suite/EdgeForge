"""Synthetic fixed-fragment assembly tests; no live assessment fabrication."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE = Path(__file__).with_name("assemble_generated_image_campaign.py")
if not MODULE.exists():
    MODULE = Path(__file__).resolve().parents[2] / "scripts/assemble_generated_image_campaign.py"
SPEC = importlib.util.spec_from_file_location("image_assembler_under_test", MODULE)
assembler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assembler)
images, publisher = assembler.helpers()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def change(path, update):
    value = images.read_json(path)
    update(value)
    put(path, value)


@pytest.fixture
def fragments(tmp_path, monkeypatch):
    # Shapes/field names follow the retained --cases collector format, but every
    # image, package and byte here is synthetic and never written to real evidence.
    declaration = {"declared_before_campaign": True, "cases": [
        {"case": f"{shape}-{suffix}", "shape": shape, "fixture": fixture,
         "profile": profile, "platform": "linux/amd64", "assess": list(images.STAGES),
         "equivalence_claim": False, "historical_resolved_graph_representative": f"{shape}-{suffix}"}
        for shape, fixture in images.FIXTURES.items() for suffix, profile in images.PROFILES.items()]}
    declared = tmp_path / "declaration.json"
    put(declared, declaration)
    monkeypatch.setattr(assembler, "COVERAGE", assembler.digest(declared))
    first, remaining = tmp_path / "first", tmp_path / "remaining"
    roots = (first, remaining)
    monkeypatch.setattr(assembler.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3))
    calls = {"stages": [], "runtimes": []}
    for index, root in enumerate(roots):
        entries = []
        for row in declaration["cases"]:
            case = row["case"]
            if (case in assembler.FIRST_CASES) != (index == 0):
                continue
            entries.append({"case": case, "generator_sha": assembler.SOURCE,
                            "collector_sha": assembler.SOURCE,
                            "runtime_helper_sha": assembler.SOURCE if case in images.RUNTIME_CASES else None,
                            "stages": dict.fromkeys(images.STAGES, 1)})
            hour = "18" if index == 0 else "20"
            for stage in images.STAGES:
                directory = root / case / stage
                put(directory / "packaged.json", [{"filename": "synthetic-1.jar", "sha256": "a" * 64}])
                evidence = directory / "evidence.dat"
                evidence.write_bytes(b"synthetic scanner evidence\n")
                report = {"case": case, "stage": stage, "generator_sha": assembler.SOURCE,
                          "collector_sha": assembler.SOURCE, "status": "complete-with-findings", "exit_code": 1,
                          "started_at_utc": f"2026-10-17T{hour}:01:00Z", "ended_at_utc": f"2026-10-17T{hour}:02:00Z",
                          "tools": {"grype": {"version": "synthetic-pinned"}},
                          "image": {"jar_sha256": "b" * 64, "image_id": "sha256:" + "c" * 64},
                          "retained_raw": [{"file": name, "sha256": assembler.digest(directory / name)}
                                           for name in ("packaged.json", "evidence.dat")]}
                put(directory / "assessment.json", report)
                put(root / case / (stage + "-bundle") / "image-retention.json",
                    {"assessment_sha256": assembler.digest(directory / "assessment.json"), "validation": "complete"})
                put(directory / "data.json", {"databases.json": {"snapshot": "synthetic-frozen"},
                    "packaged.json": images.read_json(directory / "packaged.json"),
                    "provenance.json": {"files": {name: "d" * 64 for name in (
                        "Dockerfile", "source.tar", "input.tar", "generation.json", "resolved-inventory.json",
                        "dependency-policy.json", "base-images.json", "retained-maven-bom.json")}}})
            if case in images.RUNTIME_CASES:
                put(root / case / "runtime.json", {"status": "passed", "runtime_helper_sha": assembler.SOURCE,
                    "started_at_utc": "2026-10-17T18:03:00Z", "ended_at_utc": "2026-10-17T18:04:00Z",
                    "bound_default_launch": True})
        summary = {"cases": entries, "generator_sha": assembler.SOURCE, "collector_sha": assembler.SOURCE,
                   "runtime_helper_sha": assembler.SOURCE, "generator_shas": [assembler.SOURCE],
                   "runtime_helper_shas": [assembler.SOURCE] if index == 0 else [],
                   "coverage_sha256": assembler.COVERAGE, "declared_cases": 30, "campaign_complete": False,
                   "exit_code": 2, "equivalence_claim": False,
                   "started_at_utc": "2026-10-17T18:00:00Z" if index == 0 else "2026-10-17T20:00:00Z",
                   "ended_at_utc": "2026-10-17T19:00:00Z" if index == 0 else "2026-10-17T21:00:00Z",
                   "status": "incomplete" if index == 0 else "partial-affected-scope"}
        if index == 0:
            summary["failure"] = "tool failed; evidence incomplete (see private logs)"
        else:
            summary["affected_scope_exit_code"] = 1
        put(root / "campaign.json", summary)
    failed = first / assembler.FAILED_CASE / (images.STAGES[0] + "-bundle")
    failed.mkdir(parents=True)
    (failed / "image-build.stdout").write_bytes(b"")
    (failed / "image-build.stderr").write_text(
        "load metadata for docker.io/library/maven:3.9.9-eclipse-temurin-21\n"
        "https://auth.docker.io/token?scope=repository%3Alibrary%2Fmaven%3Apull&service=registry.docker.io"
        ": net/http: TLS handshake timeout\n")
    put(failed / "image-build.receipt.json", {"exit_code": 1, "status": "incomplete", "owned_child_reaped": True,
        "command": ["synthetic-docker-command-not-executed"],
        "stdout_sha256": assembler.digest(failed / "image-build.stdout"),
        "stderr_sha256": assembler.digest(failed / "image-build.stderr"),
        "started_at_utc": "2026-10-17T18:58:00Z", "ended_at_utc": "2026-10-17T18:59:00Z"})
    monkeypatch.setattr(assembler, "FIRST_RECEIPT", assembler.digest(first / "campaign.json"))
    monkeypatch.setattr(assembler, "FAILURE_RECEIPT", assembler.digest(failed / "image-build.receipt.json"))
    monkeypatch.setattr(assembler, "FAILURE_STDERR", assembler.digest(failed / "image-build.stderr"))

    def stage(root, row, name, source, *, check_retention, assessment_helper_sha):
        assert source == assessment_helper_sha == assembler.SOURCE and check_retention is True
        calls["stages"].append((row["case"], name))
        directory = root / row["case"] / name
        report = images.read_json(directory / "assessment.json")
        for retained in report["retained_raw"]:
            assembler.require(assembler.digest(directory / retained["file"]) == retained["sha256"], "synthetic retained checksum")
        retention = images.read_json(root / row["case"] / (name + "-bundle") / "image-retention.json")
        assembler.require(retention["validation"] == "complete" and retention["assessment_sha256"] == assembler.digest(
            directory / "assessment.json"), "synthetic retention checksum/status")
        return report, images.read_json(directory / "data.json"), {}

    def runtime(root, case, source):
        calls["runtimes"].append(case)
        value = images.read_json(root / case / "runtime.json")
        assembler.require(source == value["runtime_helper_sha"] and value["bound_default_launch"], "synthetic runtime identity")
        return value

    fake = SimpleNamespace(validate_stage=stage, validate_runtime=runtime, validate_span=publisher.validate_span)
    monkeypatch.setattr(assembler, "helpers", lambda: (images, fake))
    return SimpleNamespace(first=first, remaining=remaining, declaration=declared,
                           output=tmp_path / "assembled", failed=failed, calls=calls)


def run(f):
    return assembler.assemble(f.first, f.remaining, f.declaration, f.output)


def refresh_assessment(f, case, stage, root=None):
    root = root or f.remaining
    path = root / case / stage / "assessment.json"
    change(root / case / (stage + "-bundle") / "image-retention.json",
           lambda r: r.update(assessment_sha256=assembler.digest(path)))


def test_complete_assembly_is_read_only_exact_and_repeatable(fragments):
    f = fragments
    before = [assembler.inventory(p) for p in (f.first, f.remaining)]
    assert run(f) == 1
    assert before == [assembler.inventory(p) for p in (f.first, f.remaining)]
    assert len(f.calls["stages"]) == 120  # prevalidation and verification of copies
    assert len(f.calls["runtimes"]) == 6
    root = images.read_json(f.output / "campaign.json")
    assert root["campaign_complete"] and root["exit_code"] == 1 and len(root["cases"]) == 30
    assert root["started_at_utc"] == "2026-10-17T18:00:00Z" and root["ended_at_utc"] == "2026-10-17T21:00:00Z"
    assert images.read_json(f.output / "composition-inputs/first/campaign.json")["status"] == "incomplete"
    assert images.read_json(f.output / "composition-inputs/remaining/campaign.json")["exit_code"] == 2
    assert images.read_json(f.output / "packaged-inventories.json")["generator_shas"] == [assembler.SOURCE]
    second = f.output.with_name("assembled-again")
    assert assembler.assemble(f.first, f.remaining, f.declaration, second) == 1
    assert assembler.inventory(f.output) == assembler.inventory(second)


@pytest.mark.parametrize("field,value", [
    ("generator_sha", "a" * 40), ("collector_sha", "a" * 40), ("runtime_helper_sha", "a" * 40),
    ("generator_shas", []), ("runtime_helper_shas", [assembler.SOURCE]),
    ("coverage_sha256", "a" * 64), ("declared_cases", 10), ("exit_code", 1),
    ("status", "complete-with-findings"), ("campaign_complete", True), ("affected_scope_exit_code", 0),
    ("affected_scope_exit_code", True), ("failure", "another failure"), ("cleanup_failure", "failed"),
    ("ended_at_utc", "2026-10-17T20:00:01Z"),
])
def test_fragment_contract_fails_before_output(fragments, field, value):
    f = fragments
    change(f.remaining / "campaign.json", lambda r: r.update({field: value}))
    with pytest.raises((ValueError, RuntimeError)):
        run(f)
    assert not f.output.exists()


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "overlap", "undeclared", "stage-missing", "stage-exit", "case-source"])
def test_case_partition_and_counts_fail_closed(fragments, mutation):
    f = fragments
    def mutate(root):
        if mutation == "missing":
            root["cases"].pop()
        elif mutation in ("duplicate", "overlap", "undeclared"):
            root["cases"][-1] = copy.deepcopy(root["cases"][0])
            if mutation != "duplicate":
                root["cases"][-1]["case"] = assembler.FIRST_CASES[0] if mutation == "overlap" else "unknown-case"
        elif mutation == "stage-missing":
            root["cases"][0]["stages"].pop(images.STAGES[1])
        elif mutation == "stage-exit":
            root["cases"][0]["stages"][images.STAGES[0]] = 2
        else:
            root["cases"][0]["collector_sha"] = "a" * 40
    change(f.remaining / "campaign.json", mutate)
    with pytest.raises((ValueError, RuntimeError)):
        run(f)
    assert not f.output.exists()


@pytest.mark.parametrize("mutation", ["source", "status", "exit", "time", "db", "tools", "pair", "raw", "retention"])
def test_stage_identity_inventory_snapshot_or_integrity_fails(fragments, mutation):
    f = fragments
    case = assembler.FAILED_CASE
    stage = images.STAGES[1]
    directory = f.remaining / case / stage
    if mutation in ("source", "status", "exit", "time", "tools"):
        key, value = {"source": ("generator_sha", "a" * 40), "status": ("status", "incomplete"),
                      "exit": ("exit_code", 2), "time": ("started_at_utc", "2026-10-17T17:00:00Z"),
                      "tools": ("tools", {"grype": {"version": "different"}})}[mutation]
        change(directory / "assessment.json", lambda r: r.update({key: value}))
        refresh_assessment(f, case, stage)
    elif mutation == "raw":
        (directory / "evidence.dat").write_bytes(b"changed")
    elif mutation == "retention":
        change(f.remaining / case / (stage + "-bundle") / "image-retention.json", lambda r: r.update(validation="incomplete"))
    else:
        change(directory / "data.json", lambda r: r.update({"databases.json": {"snapshot": "changed"}})
               if mutation == "db" else r["provenance.json"]["files"].update({"source.tar": "e" * 64}))
    with pytest.raises((ValueError, RuntimeError)):
        run(f)
    assert not f.output.exists()


@pytest.mark.parametrize("mutation", ["root-receipt", "failure-receipt", "failure-stdout", "failure-stderr", "scan", "export", "runtime", "symlink"])
def test_original_failure_no_scan_and_file_safety(fragments, mutation):
    f = fragments
    if mutation == "root-receipt":
        (f.first / "campaign.json").write_text((f.first / "campaign.json").read_text() + " ")
    elif mutation.startswith("failure-"):
        suffix = mutation.removeprefix("failure-")
        name = "receipt.json" if suffix == "receipt" else suffix
        path = f.failed / ("image-build." + name)
        path.write_bytes(path.read_bytes() + b"changed")
    elif mutation in ("scan", "export"):
        (f.failed / ("syft.json" if mutation == "scan" else "image.tar")).write_bytes(b"unexpected")
    elif mutation == "runtime":
        put(f.remaining / assembler.FAILED_CASE / "runtime.json", {"status": "passed"})
    else:
        (f.remaining / "unsafe-link").symlink_to(f.first, target_is_directory=True)
    with pytest.raises((ValueError, RuntimeError)):
        run(f)
    assert not f.output.exists()


@pytest.mark.parametrize("mutation", ["copied", "root", "input", "composition", "time", "extra", "failure", "traversal", "lineage"])
def test_publisher_hook_rejects_copy_and_provenance_tampering(fragments, mutation):
    f = fragments
    run(f)
    if mutation == "copied":
        (f.output / assembler.FIRST_CASES[0] / images.STAGES[0] / "evidence.dat").write_bytes(b"changed")
    elif mutation == "root":
        change(f.output / "campaign.json", lambda r: r.update(started_at_utc="2026-10-17T17:00:00Z"))
    elif mutation == "input":
        change(f.output / "composition-inputs/remaining/campaign.json", lambda r: r.update(affected_scope_exit_code=0))
    elif mutation == "composition":
        change(f.output / "composition.json", lambda r: r["stages"][0].update(source_sha="a" * 40))
    elif mutation == "time":
        change(f.output / "composition.json", lambda r: r["stages"][0].update(started_at_utc="2026-10-17T18:00:00Z"))
    elif mutation == "extra":
        (f.output / "untracked.dat").write_bytes(b"extra")
    elif mutation == "failure":
        (f.output / "composition-inputs/tls-failure/image-build.stderr").write_bytes(b"changed")
    else:
        change(f.output / assembler.MANIFEST, lambda r: r["files"][0].update(
            {"file": "../outside"} if mutation == "traversal" else {"fragment": "remaining"}))
        change(f.output / "composition.json", lambda r: r.update(copy_manifest_sha256=assembler.digest(f.output / assembler.MANIFEST)))
    with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
        assembler.validate_composition(f.output, f.declaration)


def test_failed_copy_never_keeps_a_complete_root(fragments, monkeypatch):
    f = fragments
    def corrupt(src, dst, length):
        dst.write(b"corrupt")
    monkeypatch.setattr(assembler.shutil, "copyfileobj", corrupt)
    with pytest.raises(ValueError, match="copied bytes differ"):
        run(f)
    assert not (f.output / "campaign.json").exists()
    assert images.read_json(f.output / "assembly-error.json")["exit_code"] == 2


@pytest.mark.parametrize("target", ["existing", "under-first", "under-remaining", "ancestor", "symlink"])
def test_output_must_be_new_and_outside_inputs(fragments, target):
    f = fragments
    if target == "existing":
        f.output.mkdir()
    elif target == "under-first":
        f.output = f.first / "new-output"
    elif target == "under-remaining":
        f.output = f.remaining / "new-output"
    elif target == "ancestor":
        f.output = f.first.parent
    else:
        f.output.symlink_to(f.first, target_is_directory=True)
    with pytest.raises(ValueError):
        run(f)


def test_cli_incomplete_is_two_and_does_not_publish(fragments, capsys):
    f = fragments
    change(f.remaining / "campaign.json", lambda r: r.update(status="incomplete"))
    assert assembler.main(["--first", str(f.first), "--remaining", str(f.remaining),
                           "--declaration", str(f.declaration), "--output", str(f.output)]) == 2
    assert "incomplete" in capsys.readouterr().err
    assert not f.output.exists()


def test_cli_integer_fragment_timestamp_is_incomplete_not_findings(fragments, capsys):
    f = fragments
    change(f.remaining / "campaign.json", lambda r: r.update(started_at_utc=0))
    assert assembler.main(["--first", str(f.first), "--remaining", str(f.remaining),
                           "--declaration", str(f.declaration), "--output", str(f.output)]) == 2
    assert "Assembly incomplete" in capsys.readouterr().err
    assert not f.output.exists()


@pytest.mark.parametrize("source", [assembler.REPLAY_ASSEMBLER_SHA256, "a" * 64])
def test_immutable_replay_tool_is_pinned_not_arbitrary(fragments, source):
    f = fragments
    assert run(f) == 1
    path = f.output / "composition.json"
    change(path, lambda r: r.update(assembly_source_sha256=source))
    change(f.output / "campaign.json", lambda r: r["composition"].update(sha256=assembler.digest(path)))
    if source == assembler.REPLAY_ASSEMBLER_SHA256:
        assert assembler.validate_composition(f.output, f.declaration)["assembly_source_sha256"] == source
    else:
        with pytest.raises(assembler.AssemblyError, match="assembly source"):
            assembler.validate_composition(f.output, f.declaration)


@pytest.mark.parametrize("raw", ['{"cases": [], "cases": []}', '{"cases": NaN}', '{broken'])
def test_malformed_or_ambiguous_receipts_fail_before_output(fragments, raw):
    f = fragments
    (f.remaining / "campaign.json").write_text(raw)
    assert assembler.main(["--first", str(f.first), "--remaining", str(f.remaining),
                           "--declaration", str(f.declaration), "--output", str(f.output)]) == 2
    assert not f.output.exists()


@pytest.mark.parametrize("mutation", ["helper", "time", "default-launch"])
def test_runtime_identity_and_original_span_are_required(fragments, mutation):
    f = fragments
    path = f.first / assembler.FIRST_CASES[0] / "runtime.json"
    change(path, lambda r: r.update({"runtime_helper_sha": "a" * 40} if mutation == "helper"
                                  else {"started_at_utc": "2026-10-17T17:00:00Z"} if mutation == "time"
                                  else {"bound_default_launch": False}))
    with pytest.raises(ValueError):
        run(f)
    assert not f.output.exists()


def test_zero_affected_scope_is_not_mistaken_for_incomplete_scans(fragments):
    f = fragments
    summary = images.read_json(f.remaining / "campaign.json")
    summary["affected_scope_exit_code"] = 0
    for case in summary["cases"]:
        for stage in images.STAGES:
            case["stages"][stage] = 0
            change(f.remaining / case["case"] / stage / "assessment.json",
                   lambda r: r.update(exit_code=0, status="complete-no-matches"))
            refresh_assessment(f, case["case"], stage)
    put(f.remaining / "campaign.json", summary)
    assert run(f) == 1  # first fragment retains findings; both original roots remain exit 2
    assert images.read_json(f.output / "composition.json")["fragments"][1]["observed_scope_exit_code"] == 0


def test_no_complete_root_exists_if_final_copy_validation_fails(fragments, monkeypatch):
    f = fragments
    def fail(*args, **kwargs):
        assert not (f.output / "campaign.json").exists()
        raise assembler.AssemblyError("final copy validation failed")
    monkeypatch.setattr(assembler, "_validate_composition", fail)
    with pytest.raises(ValueError):
        run(f)
    assert not (f.output / "campaign.json").exists()
    assert (f.output / "assembly-error.json").is_file()


def test_capacity_floor_is_not_lowered(fragments, monkeypatch):
    monkeypatch.setattr(assembler.shutil, "disk_usage", lambda _: SimpleNamespace(free=assembler.FREE_FLOOR))
    with pytest.raises(ValueError, match="20GiB"):
        run(fragments)
    assert not fragments.output.exists()


def test_failed_bundle_cannot_hide_a_supplemental_scan(fragments):
    f = fragments
    put(f.failed / "grype-build-classifiers.json", {"matches": []})
    with pytest.raises(ValueError, match="TLS shape"):
        run(f)
    assert not f.output.exists()
