"""Package a complete sanitized filesystem into a compact core and private tar.

No Git commands/objects/commits, scans, network, source modification or decisions.
The legacy reviewed_commit field binds SOURCE ONLY, not independent approval.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import stat
import sys
import tarfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PLAIN = frozenset(
    {
        "README.md",
        "findings.md",
        "summary.json",
        "summary.txt",
        "publication.json",
        "maven-reconciliation.json",
    }
)
STAGES = frozenset({"generated-build-stage", "generated-final-image"})
MAX_MEMBER = 256 * 1024**2
MAX_ARCHIVE = 2 * 1024**3
CHUNK = 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_name(value):
    require(
        isinstance(value, str) and value and "\\" not in value and "\x00" not in value,
        "invalid relative path",
    )
    path = PurePosixPath(value)
    require(
        not path.is_absolute()
        and all(p not in {"", ".", ".."} for p in value.split("/"))
        and str(path) == value,
        "unsafe relative path",
    )
    return value


def absolute_unlinked(path):
    path = Path(path)
    require(".." not in path.parts, "parent traversal in filesystem argument")
    path = path.absolute()
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), "linked filesystem argument or ancestor")
    return path


def json_bytes(data):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("nonfinite JSON value")

    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)


def signature(details):
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_nlink,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


@dataclass(frozen=True)
class Member:
    path: Path
    fingerprint: tuple
    size: int
    sha256: str
    git_blob: str


@contextmanager
def checked_stream(member):
    descriptor = os.open(member.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        require(
            signature(os.fstat(stream.fileno())) == member.fingerprint, "input changed before read"
        )
        yield stream
        require(
            signature(os.fstat(stream.fileno())) == member.fingerprint, "input changed during read"
        )


def snapshot(path):
    details = path.lstat()
    require(stat.S_ISREG(details.st_mode) and details.st_nlink == 1, "linked or special input file")
    require(details.st_size <= MAX_MEMBER, "input member exceeds bound")
    require(not details.st_mode & 0o111, "sanitized data member must not be executable")
    temporary = Member(path, signature(details), details.st_size, "", "")
    sha = hashlib.sha256()
    blob = hashlib.sha1(b"blob " + str(details.st_size).encode("ascii") + b"\0")
    count = 0
    with checked_stream(temporary) as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            count += len(block)
            sha.update(block)
            blob.update(block)
    require(count == details.st_size, "input size changed")
    return Member(path, signature(details), count, sha.hexdigest(), blob.hexdigest())


def read_member(member):
    with checked_stream(member) as stream:
        data = stream.read(MAX_MEMBER + 1)
    require(
        len(data) == member.size and hashlib.sha256(data).hexdigest() == member.sha256,
        "input content changed",
    )
    return data


def directories(files):
    return {
        str(parent)
        for name in files
        for parent in PurePosixPath(name).parents
        if str(parent) != "."
    }


def inventory(bundle):
    files, dirs = {}, set()

    def walk(directory):
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda e: e.name.encode("utf-8")):
                path = directory / entry.name
                name = safe_name(path.relative_to(bundle).as_posix())
                require(not entry.is_symlink(), "input symlink")
                if entry.is_dir(follow_symlinks=False):
                    dirs.add(name)
                    walk(path)
                else:
                    require(name not in files, "duplicate input path")
                    files[name] = snapshot(path)

    walk(bundle)
    require(dirs == directories(files), "unexpected empty or missing input directory")
    return files


def verify_input(files, source_commit, expected_publication_sha256=None):
    require(PLAIN <= files.keys(), "missing required plain files")
    if expected_publication_sha256 is not None:
        require(
            re.fullmatch(r"[0-9a-f]{64}", expected_publication_sha256) is not None
            and files["publication.json"].sha256 == expected_publication_sha256,
            "publication source hash mismatch",
        )
    publication = json_bytes(read_member(files["publication.json"]))
    require(
        isinstance(publication, dict)
        and type(publication.get("schema_version")) is int
        and publication["schema_version"] == 1
        and publication.get("status") == "complete"
        and isinstance(publication.get("files"), list),
        "incomplete publication",
    )
    require(publication.get("generator_sha") == source_commit, "publication/source commit mismatch")
    indexed = {}
    for entry in publication["files"]:
        require(isinstance(entry, dict), "invalid publication entry")
        name = safe_name(entry.get("file"))
        require(
            name.endswith(".gz") and name not in indexed, "duplicate/non-gzip publication entry"
        )
        require(
            all(
                isinstance(entry.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", entry[key])
                for key in ("sanitized_gzip_sha256", "sanitized_json_sha256")
            ),
            "invalid publication hashes",
        )
        indexed[name] = entry
    require(set(files) == PLAIN | set(indexed), "unindexed or missing input member")
    for name, entry in indexed.items():
        member = files[name]
        require(member.sha256 == entry["sanitized_gzip_sha256"], "gzip hash mismatch")
        with checked_stream(member) as stream, gzip.GzipFile(fileobj=stream, mode="rb") as packed:
            raw = packed.read(MAX_MEMBER + 1)
        require(
            len(raw) <= MAX_MEMBER
            and hashlib.sha256(raw).hexdigest() == entry["sanitized_json_sha256"],
            "gzip decompressed hash/size mismatch",
        )
        json_bytes(raw)
    summary = json_bytes(read_member(files["summary.json"]))
    require(
        isinstance(summary, dict) and summary.get("generator_sha") == source_commit,
        "summary/source commit mismatch",
    )
    for name, key in (("summary.json", "summary_sha256"), ("summary.txt", "summary_text_sha256")):
        require(files[name].sha256 == publication.get(key), "summary publication hash mismatch")
    stage_files = {}
    for name in indexed:
        parts = PurePosixPath(name).parts
        if (
            len(parts) == 3
            and parts[1] in STAGES
            and parts[2] in {"assessment.json.gz", "databases.json.gz"}
        ):
            stage_files.setdefault(parts[0], set()).add((parts[1], parts[2]))
    required = {
        (stage, name) for stage in STAGES for name in ("assessment.json.gz", "databases.json.gz")
    }
    require(
        stage_files and all(values == required for values in stage_files.values()),
        "missing paired stage assessment/database records",
    )
    require(
        type(summary.get("cases")) is int
        and summary["cases"] == len(stage_files)
        and type(summary.get("stage_observations")) is int
        and summary["stage_observations"] == len(stage_files) * len(STAGES),
        "summary/case-stage file count mismatch",
    )
    try:
        from scripts.verify_generated_image_evidence_split import verify_public_projections
    except ModuleNotFoundError:
        from verify_generated_image_evidence_split import verify_public_projections
    verify_public_projections(publication, indexed,
                              lambda name: read_member(files[name]), with_sources=True)
    return indexed, stage_files


def core_names(files, cases):
    result = set(PLAIN)
    for name in files:
        parts = PurePosixPath(name).parts
        if len(parts) == 1 and name.endswith(".gz"):
            result.add(name)
        elif (
            len(parts) == 3
            and parts[0] in cases
            and parts[1] in STAGES
            and parts[2] in {"assessment.json.gz", "databases.json.gz"}
        ):
            result.add(name)
        elif (
            len(parts) == 2
            and parts[0] in cases
            and parts[1].startswith("runtime")
            and name.endswith(".gz")
        ):
            result.add(name)
    return result


def git_tree(files):
    """Git tree for the full bundle subtree; data files are non-executable 100644."""
    root = {}
    for name, member in files.items():
        node = root
        parts = PurePosixPath(name).parts
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = member.git_blob

    def tree(node):
        records = []
        for name in sorted(
            node, key=lambda n: n.encode("utf-8") + (b"/" if isinstance(node[n], dict) else b"")
        ):
            value = node[name]
            mode, identity = (
                (b"40000", tree(value)) if isinstance(value, dict) else (b"100644", value)
            )
            records.append(mode + b" " + name.encode("utf-8") + b"\0" + bytes.fromhex(identity))
        payload = b"".join(records)
        return hashlib.sha1(
            b"tree " + str(len(payload)).encode("ascii") + b"\0" + payload
        ).hexdigest()

    return tree(root)


class HashReader:
    def __init__(self, stream):
        self.stream, self.sha, self.count = stream, hashlib.sha256(), 0

    def read(self, size):
        block = self.stream.read(size)
        self.sha.update(block)
        self.count += len(block)
        return block


def checked_copy(member, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with checked_stream(member) as stream, target.open("xb") as output:
        reader = HashReader(stream)
        while block := reader.read(CHUNK):
            output.write(block)
    require(
        reader.count == member.size and reader.sha.hexdigest() == member.sha256,
        "input changed during copy",
    )
    target.chmod(0o644)


def hash_file(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            sha.update(block)
    return sha.hexdigest()


def write_new_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=True)
        stream.write("\n")
    path.chmod(0o600)


def package(
    input_root,
    output_root,
    evidence_dir,
    archive_dir,
    source_commit,
    *,
    expected_publication_sha256=None,
    archive_name=None,
):
    require(
        isinstance(source_commit, str) and re.fullmatch(r"[0-9a-f]{40}", source_commit),
        "invalid source commit",
    )
    safe_name(evidence_dir)
    if archive_name is not None:
        safe_name(archive_name)
        require('/' not in archive_name and archive_name.endswith('.tar'),
                'archive name must be a tar basename')
    input_root, output_root, archive_dir = map(
        absolute_unlinked, (input_root, output_root, archive_dir)
    )
    roots = (input_root, output_root, archive_dir)
    require(
        all(
            not a.is_relative_to(b) and not b.is_relative_to(a)
            for i, a in enumerate(roots)
            for b in roots[i + 1 :]
        ),
        "input/output/archive roots overlap",
    )
    require(input_root.is_dir(), "input root missing")
    require(
        not output_root.exists() and not archive_dir.exists(),
        "fresh output and archive directories required",
    )
    require(
        output_root.parent.is_dir() and archive_dir.parent.is_dir(), "output/archive parent missing"
    )
    bundle = absolute_unlinked(input_root / evidence_dir)
    require(bundle.is_dir(), "input bundle missing")
    files = inventory(bundle)
    indexed, cases = verify_input(files, source_commit, expected_publication_sha256)
    selected = core_names(files, cases)
    full_names = {evidence_dir + "/" + name for name in files}
    dir_names = directories(full_names)
    tree = git_tree(files)
    # No output is created until every indexed JSON/gzip and source label is validated.
    output_root.mkdir(mode=0o700)
    archive_dir.mkdir(mode=0o700)
    archive_path = archive_dir / (archive_name or (PurePosixPath(evidence_dir).name + "-sanitized.tar"))
    manifest_path = output_root / (evidence_dir + "-core-manifest.json")
    for name in sorted(selected):
        checked_copy(files[name], output_root / evidence_dir / name)
    descriptor = os.open(archive_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        with tarfile.open(
            fileobj=output,
            mode="w",
            format=tarfile.PAX_FORMAT,
            pax_headers={"comment": source_commit},
        ) as archive:
            for name in sorted(full_names | dir_names, key=lambda item: item.encode("utf-8")):
                item = tarfile.TarInfo(name + "/" if name in dir_names else name)
                item.uid = item.gid = item.mtime = 0
                item.uname = item.gname = ""
                item.mode = 0o755 if name in dir_names else 0o644
                if name in dir_names:
                    item.type = tarfile.DIRTYPE
                    archive.addfile(item)
                else:
                    member = files[name[len(evidence_dir) + 1 :]]
                    item.size = member.size
                    with checked_stream(member) as stream:
                        reader = HashReader(stream)
                        archive.addfile(item, reader)
                    require(
                        reader.count == member.size and reader.sha.hexdigest() == member.sha256,
                        "input changed during archive write",
                    )
                require(output.tell() <= MAX_ARCHIVE, "archive exceeds verifier bound")
    require(archive_path.stat().st_size <= MAX_ARCHIVE, "archive exceeds verifier bound")
    # Re-inventory catches added/removed/replaced files; never alter input to recover.
    after = inventory(bundle)
    require(after == files, "input filesystem changed during packaging")
    manifest = {
        "schema_version": "1.0",
        "reviewed_commit": source_commit,
        "bundle_tree": tree,
        "core_rule": [
            "reviewed_commit is legacy SOURCE binding only; no independent review approval or full-bundle Git commit claimed.",
            "Six plain files; every indexed top-level gzip; every case/stage assessment and database gzip; all emitted case/runtime gzip files.",
            "Full bundle tree is computed from the complete non-executable data filesystem using Git blob/tree encodings; no Git objects written.",
        ],
        "core": [
            {
                "path": evidence_dir + "/" + name,
                "git_blob": files[name].git_blob,
                "sha256": files[name].sha256,
                "bytes": files[name].size,
            }
            for name in sorted(selected)
        ],
        "archive": {
            "command": "package_generated_image_evidence.py filesystem PAX; explicit CLI inputs recorded privately",
            "git_version": "Git archive not used; Python tarfile.PAX_FORMAT; uid/gid/mtime=0, files=0644, dirs=0755",
            "tar_umask": "0002",
            "sha256": hash_file(archive_path),
            "bytes": archive_path.stat().st_size,
            "files": len(files),
            "directories": len(dir_names),
        },
        "archive_only_files": len(files) - len(selected),
    }
    write_new_json(manifest_path, manifest)
    receipt = {
        "status": "packaged-not-security-accepted",
        "source_commit": source_commit,
        "source_binding_not_review_approval": True,
        "publication_sha256": files["publication.json"].sha256,
        "bundle_tree": tree,
        "full_files": len(files),
        "core_files": len(selected),
        "archive_only_files": len(files) - len(selected),
        "case_count": len(cases),
        "stage_observations": len(cases) * len(STAGES),
        "indexed_gzip_files": len(indexed),
        "manifest": str(manifest_path.relative_to(output_root)),
        "manifest_sha256": hash_file(manifest_path),
        "archive_name": archive_path.name,
        "archive_sha256": manifest["archive"]["sha256"],
        "input_preserved": True,
        "git_objects_written": 0,
        "release_acceptance": "not established",
    }
    write_new_json(output_root / "packaging-receipt.json", receipt)
    return manifest_path, archive_path, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--archive-dir", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--expected-publication-sha256")
    parser.add_argument("--archive-name", help="optional distinct tar basename for a retention revision")
    args = parser.parse_args(argv)
    try:
        manifest, archive, receipt = package(**vars(args))
        print(
            json.dumps(
                {
                    "status": receipt["status"],
                    "manifest": str(manifest),
                    "archive": str(archive),
                    "core_files": receipt["core_files"],
                    "full_files": receipt["full_files"],
                }
            )
        )
        return 0
    except Exception as error:
        print(
            f"Packaging incomplete: {type(error).__name__}: {error}; preserve any partial outputs, no overwrite/retry.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
