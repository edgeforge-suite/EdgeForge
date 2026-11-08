"""Integrity controls use small synthetic archives; the real archive is opt-in."""

import copy
import gzip
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from scripts import verify_generated_image_evidence_split as verifier


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def archive_bytes(contents, commit, mutate=None):
    stream = io.BytesIO()
    members = []
    for name in sorted(verifier.directory_names(contents)):
        item = tarfile.TarInfo(name + "/")
        item.type = tarfile.DIRTYPE
        members.append((item, b""))
    for name, data in sorted(contents.items()):
        item = tarfile.TarInfo(name)
        item.size = len(data)
        members.append((item, data))
    if mutate:
        mutate(members)
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT,
                      pax_headers={"comment": commit}) as archive:
        for item, data in members:
            archive.addfile(item, io.BytesIO(data))
    return stream.getvalue()


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / "repository"
    directory = root / verifier.BUNDLE
    directory.mkdir(parents=True)
    contents = {verifier.BUNDLE + "/" + name: b"{}\n" for name in verifier.PLAIN}
    indexed = []
    for name in ("campaign.json.gz", "case/stage/report.json.gz"):
        raw = b'{"status":"retained"}\n'
        packed = gzip.compress(raw, mtime=0)
        contents[verifier.BUNDLE + "/" + name] = packed
        indexed.append({"file": name, "sanitized_gzip_sha256": verifier.sha256(packed),
                        "sanitized_json_sha256": verifier.sha256(raw)})
    publication = {"schema_version": 1, "status": "complete", "files": indexed,
                   "summary_sha256": verifier.sha256(b"{}\n"),
                   "summary_text_sha256": verifier.sha256(b"{}\n")}
    contents[verifier.BUNDLE + "/publication.json"] = json.dumps(publication).encode()
    core = {name: data for name, data in contents.items() if not name.endswith("report.json.gz")}
    for name, data in core.items():
        (root / name).write_bytes(data)
    commit = "1" * 40
    archive = tmp_path / "archive.tar"
    archive.write_bytes(archive_bytes(contents, commit))
    manifest = {
        "schema_version": "1.0", "reviewed_commit": commit, "bundle_tree": "2" * 40,
        "core_rule": ["Synthetic integrity fixture; no external tools or downloads."],
        "core": [{"path": name, "git_blob": verifier.git_blob(data),
                  "sha256": verifier.sha256(data), "bytes": len(data)} for name, data in sorted(core.items())],
        "archive": {"command": "git -c tar.umask=0002 archive COMMIT -- PATH", "tar_umask": "0002",
                    "git_version": "git fixture", "sha256": verifier.sha256(archive.read_bytes()),
                    "bytes": archive.stat().st_size, "files": len(contents),
                    "directories": len(verifier.directory_names(contents))},
        "archive_only_files": len(contents) - len(core),
    }
    write_json(root / verifier.MANIFEST, manifest)
    return root, archive, manifest, contents


def run(fixture, *, archive=False):
    root, path, _, _ = fixture
    return verifier.main(["--root", str(root), *(["--archive", str(path)] if archive else [])])


def update_archive(fixture, data):
    root, archive, manifest, _ = fixture
    archive.write_bytes(data)
    manifest["archive"].update(sha256=verifier.sha256(data), bytes=len(data))
    write_json(root / verifier.MANIFEST, manifest)


def update_core_entry(fixture, name, data):
    root, _, manifest, _ = fixture
    (root / name).write_bytes(data)
    entry = next(item for item in manifest["core"] if item["path"] == name)
    entry.update(sha256=verifier.sha256(data), git_blob=verifier.git_blob(data), bytes=len(data))
    write_json(root / verifier.MANIFEST, manifest)


@pytest.mark.parametrize("with_archive", [False, True])
def test_synthetic_pass(fixture, with_archive, capsys):
    assert run(fixture, archive=with_archive) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "verified"
    assert report["release_acceptance"] == "not established"


@pytest.mark.parametrize("change", ["missing", "extra", "changed", "symlink"])
def test_core_integrity_errors_exit_two(fixture, change):
    root, _, _, _ = fixture
    target = root / verifier.BUNDLE / "README.md"
    if change == "missing":
        target.unlink()
    elif change == "extra":
        target.with_name("unexpected.json").write_text("{}")
    elif change == "changed":
        target.write_text("different")
    else:
        target.unlink()
        target.symlink_to("summary.json")
    assert run(fixture) == 2


@pytest.mark.parametrize("change", ["gzip", "decompressed", "summary", "duplicate", "malformed"])
def test_publication_mismatch_exit_two(fixture, change):
    root, _, _, _ = fixture
    name = verifier.BUNDLE + "/publication.json"
    publication = json.loads((root / name).read_bytes())
    if change == "gzip":
        publication["files"][0]["sanitized_gzip_sha256"] = "0" * 64
    elif change == "decompressed":
        publication["files"][0]["sanitized_json_sha256"] = "0" * 64
    elif change == "summary":
        publication["summary_sha256"] = "0" * 64
    elif change == "duplicate":
        publication["files"].append(copy.deepcopy(publication["files"][0]))
    data = b"[]" if change == "malformed" else json.dumps(publication).encode()
    update_core_entry(fixture, name, data)
    assert run(fixture) == 2


@pytest.mark.parametrize("change", ["hash", "member", "core", "traversal", "absolute", "symlink",
                                    "device", "duplicate", "missing", "unexpected", "malformed"])
def test_archive_errors_exit_two(fixture, change):
    _, archive, manifest, contents = fixture
    if change == "hash":
        archive.write_bytes(b"changed")
    elif change == "malformed":
        update_archive(fixture, b"not a tar archive")
    else:
        contents = dict(contents)
        if change in {"member", "core"}:
            key = verifier.BUNDLE + ("/case/stage/report.json.gz" if change == "member" else "/README.md")
            contents[key] = gzip.compress(b"{}", mtime=0) if change == "member" else b"different"

        def mutate(members):
            index = next(i for i, (item, _) in enumerate(members) if item.isfile())
            item, data = members[index]
            if change == "traversal":
                item.name = "../outside"
            elif change == "absolute":
                item.name = "/outside"
            elif change == "symlink":
                item.type, item.linkname, item.size = tarfile.SYMTYPE, "outside", 0
            elif change == "device":
                item.type, item.size = tarfile.CHRTYPE, 0
            elif change == "duplicate":
                members.append((copy.copy(item), data))
            elif change == "missing":
                members.pop(index)
            elif change == "unexpected":
                item.name = verifier.BUNDLE + "/unexpected"

        update_archive(fixture, archive_bytes(contents, manifest["reviewed_commit"], mutate))
    assert run(fixture, archive=True) == 2


@pytest.mark.parametrize("data", [b"[]", b"{", b'{"schema_version":1,"schema_version":2}'])
def test_malformed_manifest_exit_two(fixture, data):
    (fixture[0] / verifier.MANIFEST).write_bytes(data)
    assert run(fixture) == 2


def test_unexpected_exception_is_not_findings(fixture, monkeypatch):
    def fail(*args):
        raise AttributeError("synthetic tooling error")

    monkeypatch.setattr(verifier, "verify", fail)
    assert run(fixture) == 2


@pytest.mark.parametrize("policy", [None, [], "invalid", {}, {"schema_version": "unknown"}])
def test_invalid_retention_policy_is_not_legacy_success(fixture, policy):
    root = fixture[0]
    name = verifier.BUNDLE + "/publication.json"
    publication = json.loads((root / name).read_bytes())
    publication["public_retention"] = policy
    update_core_entry(fixture, name, json.dumps(publication).encode())
    assert run(fixture) == 2
    assert run(fixture, archive=True) == 2


def test_retention_index_marker_cannot_be_downgraded_to_legacy(fixture):
    root = fixture[0]
    name = verifier.BUNDLE + "/publication.json"
    publication = json.loads((root / name).read_bytes())
    publication["files"][0]["derived_retention_revision"] = 2
    update_core_entry(fixture, name, json.dumps(publication).encode())
    assert run(fixture) == 2
    assert run(fixture, archive=True) == 2


def test_real_committed_core():
    result = verifier.verify(verifier.ROOT, verifier.ROOT / verifier.MANIFEST)
    assert result["core_files"] == 161
    assert result["archive_files"] == 1997


def test_explicit_new_bundle_keeps_dynamic_counts_and_all_integrity_checks(fixture):
    root, archive, manifest, contents = fixture
    bundle = "docs/handover-evidence/generated-images/new-synthetic"
    updated = {name.replace(verifier.BUNDLE, bundle, 1): data for name, data in contents.items()}
    for entry in manifest["core"]:
        old = root / entry["path"]
        entry["path"] = entry["path"].replace(verifier.BUNDLE, bundle, 1)
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(old.read_bytes())
    data = archive_bytes(updated, manifest["reviewed_commit"])
    archive.write_bytes(data)
    manifest["archive"].update(sha256=verifier.sha256(data), bytes=len(data))
    path = root / "new-manifest.json"
    write_json(path, manifest)
    args = ["--root", str(root), "--manifest", str(path), "--evidence-dir", bundle,
            "--archive", str(archive)]
    assert verifier.main(args) == 0
    (root / bundle / "README.md").write_text("changed")
    assert verifier.main(args) == 2


@pytest.mark.parametrize("bundle", ("../escape", "/absolute", "docs/../escape", "docs//empty"))
def test_explicit_bundle_rejects_unsafe_paths(fixture, bundle):
    root = fixture[0]
    assert verifier.main(["--root", str(root), "--evidence-dir", bundle]) == 2


@pytest.mark.skipif(not os.environ.get("EDGEFORGE_IMAGE_EVIDENCE_ARCHIVE"),
                    reason="maintainer-held real image archive is opt-in")
def test_real_archive():
    result = verifier.verify(verifier.ROOT, verifier.ROOT / verifier.MANIFEST,
                             Path(os.environ["EDGEFORGE_IMAGE_EVIDENCE_ARCHIVE"]))
    assert result["archive"] == "verified"
