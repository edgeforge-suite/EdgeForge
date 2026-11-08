#!/usr/bin/env python3
"""Verify the retained image-evidence core and, optionally, its private archive.

Read-only; no Git history, downloads, application execution or scanner required.
Exit 0 means integrity verified, not security acceptance. Every error exits 2.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "docs/handover-evidence/generated-images/2026-10-17"
MANIFEST = BUNDLE + "-core-manifest.json"
PLAIN = {"README.md", "findings.md", "summary.json", "summary.txt",
         "publication.json", "maven-reconciliation.json"}
MAX_MEMBER = 256 * 1024 * 1024
MAX_ARCHIVE = 2 * 1024 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def json_value(data):
    return json.loads(data, object_pairs_hook=pairs)


def path_name(value):
    require(isinstance(value, str) and value and "\\" not in value,
            "invalid member path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(part not in {"", ".", ".."}
            for part in value.split("/")) and str(path) == value,
            "unsafe member path")
    return value


def hex_value(value, length):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value)


def bounded_read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_MEMBER,
            "missing, linked or oversized evidence file")
    return path.read_bytes()


def manifest_value(path, bundle=BUNDLE):
    path_name(bundle)
    value = json_value(bounded_read(path))
    require(isinstance(value, dict) and set(value) == {
        "schema_version", "reviewed_commit", "bundle_tree", "core_rule", "core",
        "archive", "archive_only_files"}, "invalid manifest fields")
    require(value["schema_version"] == "1.0" and hex_value(value["reviewed_commit"], 40)
            and hex_value(value["bundle_tree"], 40)
            and isinstance(value["core_rule"], list) and value["core_rule"]
            and all(isinstance(item, str) and item for item in value["core_rule"]),
            "invalid manifest identity or rule")
    require(isinstance(value["core"], list) and value["core"], "empty core manifest")
    core = {}
    for entry in value["core"]:
        require(isinstance(entry, dict) and set(entry) == {"path", "git_blob", "sha256", "bytes"},
                "invalid core entry")
        name = path_name(entry["path"])
        require(name.startswith(bundle + "/") and name not in core
                and hex_value(entry["git_blob"], 40) and hex_value(entry["sha256"], 64)
                and type(entry["bytes"]) is int and 0 <= entry["bytes"] <= MAX_MEMBER,
                "invalid core identity")
        core[name] = entry
    archive = value["archive"]
    require(isinstance(archive, dict) and set(archive) == {
        "command", "git_version", "tar_umask", "sha256", "bytes", "files", "directories"},
        "invalid archive descriptor")
    require(all(isinstance(archive[key], str) and archive[key]
                for key in ("command", "git_version", "tar_umask"))
            and archive["tar_umask"] == "0002" and hex_value(archive["sha256"], 64)
            and all(type(archive[key]) is int and archive[key] > 0
                    for key in ("bytes", "files", "directories"))
            and archive["bytes"] <= MAX_ARCHIVE
            and type(value["archive_only_files"]) is int
            and value["archive_only_files"] >= 0
            and len(core) + value["archive_only_files"] == archive["files"],
            "inconsistent archive descriptor")
    return value, core


def publication_value(data):
    value = json_value(data)
    require(isinstance(value, dict) and value.get("schema_version") == 1
            and value.get("status") == "complete" and isinstance(value.get("files"), list),
            "incomplete publication index")
    indexed = {}
    for entry in value["files"]:
        require(isinstance(entry, dict), "invalid publication entry")
        name = path_name(entry["file"])
        require(name.endswith(".gz") and name not in indexed
                and all(hex_value(entry.get(key), 64)
                        for key in ("sanitized_gzip_sha256", "sanitized_json_sha256")),
                "invalid or duplicate publication identity")
        indexed[name] = entry
    require(all(hex_value(value.get(key), 64)
                for key in ("summary_sha256", "summary_text_sha256")),
            "missing summary identities")
    return value, indexed


def verify_gzip(data, entry):
    require(sha256(data) == entry["sanitized_gzip_sha256"], "gzip identity mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        raw = stream.read(MAX_MEMBER + 1)
    require(len(raw) <= MAX_MEMBER and sha256(raw) == entry["sanitized_json_sha256"],
            "decompressed identity mismatch")
    json_value(raw)


def verify_public_projections(publication, indexed, read, *, with_sources):
    """Validate the retention revision; original records are required for archive mode."""
    names = ["publication-replay.json.gz", "residual-vendor-current.json.gz"]
    reserved = {
        "retention-revision.json.gz", "reconciliation-replay-context.json.gz",
        "reconciliation/reviewed-publication.original.json.gz",
        "reconciliation/residual-vendor-current.original.json.gz",
        "reconciliation/publication-replay.original.json.gz",
    }
    derived = bool(reserved & indexed.keys()) or any(
        "derived_retention_revision" in entry for entry in indexed.values())
    records = {}
    for name in names:
        if name in indexed:
            raw = read(name)
            verify_gzip(raw, indexed[name])
            value = json_value(gzip.decompress(raw))
            require(isinstance(value, dict), "invalid retained projection record")
            records[name] = value
            derived |= ("publication_projection" in value
                        or str(value.get("schema_version", "")).startswith("residual-vendor-current-publication-"))
    if "public_retention" not in publication:
        require(not derived, "derived records require the public retention declaration")
        return
    policy = publication["public_retention"]
    require(isinstance(policy, dict) and set(policy) == {
        "schema_version", "reviewed_source_sha", "original_archive_sha256",
        "original_publication_sha256", "original_publication_member", "projection_files"},
        "invalid public retention declaration")
    require(policy["schema_version"] == "public-retention-r2"
            and hex_value(policy["reviewed_source_sha"], 40)
            and hex_value(policy["original_archive_sha256"], 64)
            and hex_value(policy["original_publication_sha256"], 64)
            and policy["projection_files"] == names, "invalid retention identity or projection set")
    original_name = path_name(policy["original_publication_member"])
    require(original_name == "reconciliation/reviewed-publication.original.json.gz"
            and original_name in indexed
            and indexed[original_name]["sanitized_json_sha256"] == policy["original_publication_sha256"],
            "original publication binding missing or mismatched")
    try:
        from scripts import project_generated_image_proof_evidence as projection
    except ModuleNotFoundError:
        import project_generated_image_proof_evidence as projection
    validators = {names[0]: projection.validate_replay_projection,
                  names[1]: projection.validate_vendor_projection}
    original_index = None
    if with_sources:
        original_raw = read(original_name)
        verify_gzip(original_raw, indexed[original_name])
        _, original_index = publication_value(gzip.decompress(original_raw))
    for name, validate in validators.items():
        require(name in indexed, "required public projection missing")
        value = records[name]
        validate(value)
        binding = value["publication_projection"]["source"]
        source_name = path_name(binding["archive_member"])
        require(source_name in indexed and source_name != name
                and binding["gzip_sha256"] == indexed[source_name]["sanitized_gzip_sha256"]
                and binding["json_sha256"] == indexed[source_name]["sanitized_json_sha256"],
                "projection source binding missing or mismatched")
        if with_sources:
            require(name in original_index
                    and indexed[source_name]["sanitized_gzip_sha256"] == original_index[name]["sanitized_gzip_sha256"]
                    and indexed[source_name]["sanitized_json_sha256"] == original_index[name]["sanitized_json_sha256"],
                    "projection original differs from reviewed publication")
            source = read(source_name)
            verify_gzip(source, indexed[source_name])
            validate(value, source_raw=source)


def directory_names(files):
    return {str(parent) for name in files for parent in PurePosixPath(name).parents
            if str(parent) != "."}


def verify(root, manifest_path, archive_path=None, *, evidence_dir=BUNDLE):
    root = root.resolve(strict=True)
    path_name(evidence_dir)
    manifest, core = manifest_value(manifest_path, evidence_dir)
    directory = root / evidence_dir
    require(directory.is_dir() and not any(p.is_symlink()
            for p in (directory, *directory.parents) if p != root.parent),
            "missing or linked bundle directory")
    entries = list(directory.rglob("*"))
    require(not any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in entries),
            "linked or unsupported core member")
    actual = {p.relative_to(root).as_posix() for p in entries if p.is_file()}
    require(actual == set(core), "missing or unexpected core files")
    for name, entry in core.items():
        data = bounded_read(root / name)
        require(len(data) == entry["bytes"] and sha256(data) == entry["sha256"]
                and git_blob(data) == entry["git_blob"], "core blob mismatch")
    publication, indexed = publication_value(bounded_read(directory / "publication.json"))
    expected = {evidence_dir + "/" + name for name in set(indexed) | PLAIN}
    require(set(core) <= expected and len(expected) == manifest["archive"]["files"]
            and len(directory_names(expected)) == manifest["archive"]["directories"],
            "publication/archive member count mismatch")
    for name in core:
        relative = name[len(evidence_dir) + 1:]
        if relative.endswith(".gz"):
            require(relative in indexed, "core member not indexed")
            verify_gzip(bounded_read(root / name), indexed[relative])
    for name, key in (("summary.json", "summary_sha256"), ("summary.txt", "summary_text_sha256")):
        require(sha256(bounded_read(directory / name)) == publication[key], "summary index mismatch")
    verify_public_projections(publication, indexed,
                              lambda name: bounded_read(directory / name), with_sources=False)
    if archive_path is not None:
        verify_archive(archive_path, root, manifest, core, expected, indexed, bundle=evidence_dir)
    return {"status": "verified", "core_files": len(core),
            "archive": "verified" if archive_path is not None else "not requested",
            "archive_files": manifest["archive"]["files"],
            "release_acceptance": "not established"}


def verify_archive(path, root, manifest, core, expected, indexed, *, bundle=BUNDLE):
    require(path.is_file() and not path.is_symlink()
            and path.stat().st_size == manifest["archive"]["bytes"], "archive size mismatch")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    require(hasher.hexdigest() == manifest["archive"]["sha256"], "archive hash mismatch")
    with tarfile.open(path, "r:") as archive, tempfile.TemporaryDirectory(prefix="edgeforge-evidence-verify-") as temporary:
        members = archive.getmembers()
        require(len(members) == len(expected) + manifest["archive"]["directories"],
                "archive member count mismatch")
        names, files, directories = set(), set(), set()
        for member in members:
            name = path_name(member.name.rstrip("/") if member.isdir() else member.name)
            require(name not in names and (member.isfile() or member.isdir())
                    and 0 <= member.size <= MAX_MEMBER, "duplicate or unsafe archive member")
            names.add(name)
            (directories if member.isdir() else files).add(name)
        require(files == expected and directories == directory_names(expected),
                "missing or unexpected archive members")
        require(archive.pax_headers.get("comment") == manifest["reviewed_commit"],
                "archive commit identity mismatch")
        destination = Path(temporary)
        # Never delegate extraction of untrusted paths, links or special files to tar.
        for member in members:
            if member.isdir():
                continue
            name = member.name
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            require(source is not None, "unreadable archive member")
            with source:
                data = source.read(MAX_MEMBER + 1)
            require(len(data) == member.size, "truncated archive member")
            with target.open("xb") as stream:
                stream.write(data)
            if name in core:
                require(data == bounded_read(root / name), "archive/core mismatch")
            relative = name[len(bundle) + 1:]
            if relative in indexed:
                verify_gzip(data, indexed[relative])
        publication, _ = publication_value(bounded_read(root / bundle / "publication.json"))
        verify_public_projections(publication, indexed,
                                  lambda name: bounded_read(destination / bundle / name),
                                  with_sources=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository or source-distribution root")
    parser.add_argument("--archive", type=Path, help="optional maintainer-held sanitized tar archive")
    parser.add_argument("--manifest", type=Path, help="explicit versioned core manifest")
    parser.add_argument("--evidence-dir", default=BUNDLE, help="bundle path relative to root")
    args = parser.parse_args(argv)
    try:
        result = verify(args.root, args.manifest or args.root / MANIFEST, args.archive,
                        evidence_dir=args.evidence_dir)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print("Image evidence split incomplete or mismatched; no release acceptance established.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
