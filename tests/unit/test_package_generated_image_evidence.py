"""Only small synthetic data; reuse the committed verifier via explicit CLI args."""

import contextlib
import copy
import gzip
import hashlib
import io
import json
import os
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import package_generated_image_evidence as packager
from scripts import verify_generated_image_evidence_split as VERIFIER

HERE = Path(__file__).resolve().parent
SOURCE = "c8798275065a8a0b619046707fad053f8a9b9ad1"
BUNDLE = "docs/handover-evidence/generated-images/synthetic-new"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


def fixture(root, count=2):
    bundle = root / BUNDLE
    bundle.mkdir(parents=True)
    for name in packager.PLAIN:
        (bundle / name).write_bytes(b"{}\n")
    summary = {
        "generator_sha": SOURCE,
        "cases": count,
        "stage_observations": count * 2,
        "status": "complete-with-findings",
        "disposition": "OPEN",
    }
    write_json(bundle / "summary.json", summary)
    indexed = []
    names = ["campaign.json.gz", "coverage-declared.json.gz", "residual-history-map.json.gz"]
    for index in range(count):
        case = f"case-{index}"
        names.extend(
            f"{case}/{stage}/{name}.json.gz"
            for stage in sorted(packager.STAGES)
            for name in ("assessment", "databases", "syft")
        )
        if index == 0:
            names.extend(
                f"{case}/{name}.gz"
                for name in (
                    "runtime.json",
                    "runtime-identity.json",
                    "runtime-manifest.json",
                    "runtime-image-inspect.stdout",
                    "runtime-create.receipt.json",
                    "runtime-created-state.stdout",
                    "runtime-created-state.receipt.json",
                    "runtime-start.receipt.json",
                )
            )
    for name in names:
        data = json.dumps({"identity": name, "disposition": "OPEN"}, sort_keys=True).encode()
        packed = gzip.compress(data, mtime=0)
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(packed)
        indexed.append(
            {"file": name, "sanitized_gzip_sha256": sha(packed), "sanitized_json_sha256": sha(data)}
        )
    publication = {
        "schema_version": 1,
        "generator_sha": SOURCE,
        "status": "complete",
        "files": indexed,
        "summary_sha256": sha((bundle / "summary.json").read_bytes()),
        "summary_text_sha256": sha((bundle / "summary.txt").read_bytes()),
    }
    write_json(bundle / "publication.json", publication)
    return bundle


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="synthetic-packager-", dir=HERE)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "input"
        self.bundle = fixture(self.source)
        self.output = self.base / "core"
        self.archives = self.base / "archives"

    def package(self, **overrides):
        args = dict(
            input_root=self.source,
            output_root=self.output,
            evidence_dir=BUNDLE,
            archive_dir=self.archives,
            source_commit=SOURCE,
        )
        args.update(overrides)
        return packager.package(**args)

    def publication(self, mutate):
        path = self.bundle / "publication.json"
        value = json.loads(path.read_bytes())
        mutate(value)
        write_json(path, value)

    def reject_before_output(self, **overrides):
        with self.assertRaises((ValueError, OSError, EOFError)):
            self.package(**overrides)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.archives.exists())

    def verifier(self, manifest, archive=None):
        args = ["--root", str(self.output), "--manifest", str(manifest), "--evidence-dir", BUNDLE]
        if archive:
            args += ["--archive", str(archive)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return VERIFIER.main(args)

    def test_core_and_archive_pass_existing_verifier_explicit_args(self):
        before = {
            str(path.relative_to(self.source)): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
        }
        manifest, archive, receipt = self.package()
        self.assertEqual(self.verifier(manifest), 0)
        self.assertEqual(self.verifier(manifest, archive), 0)
        self.assertEqual(receipt["case_count"], 2)
        self.assertEqual(receipt["stage_observations"], 4)
        self.assertEqual(receipt["archive_only_files"], 4)
        for entry in json.loads(manifest.read_text())["core"]:
            self.assertEqual(
                (self.output / entry["path"]).read_bytes(),
                (self.source / entry["path"]).read_bytes(),
            )
        self.assertEqual(
            before,
            {
                str(path.relative_to(self.source)): path.read_bytes()
                for path in self.source.rglob("*")
                if path.is_file()
            },
        )
        self.assertTrue((self.output / BUNDLE / "residual-history-map.json.gz").is_file())
        self.assertTrue((self.output / BUNDLE / "case-0/runtime-created-state.stdout.gz").is_file())
        self.assertFalse(
            (self.output / BUNDLE / "case-0/generated-build-stage/syft.json.gz").exists()
        )

    def test_dynamic_counts_not_legacy_counts(self):
        other = self.base / "three-cases"
        fixture(other, count=3)
        manifest, archive, receipt = self.package(input_root=other)
        self.assertEqual(receipt["case_count"], 3)
        self.assertEqual(receipt["stage_observations"], 6)
        self.assertEqual(receipt["archive_only_files"], 6)
        self.assertNotIn(receipt["core_files"], (161, 1997))
        self.assertEqual(self.verifier(manifest, archive), 0)

    def test_distinct_retention_archive_name_preserves_members_and_verification(self):
        manifest, archive, receipt = self.package(archive_name="synthetic-retention-r2.tar")
        self.assertEqual(archive.name, "synthetic-retention-r2.tar")
        self.assertEqual(receipt["archive_name"], archive.name)
        self.assertEqual(self.verifier(manifest, archive), 0)

    def test_archive_name_cannot_escape_or_change_file_type(self):
        for name in ("../escape.tar", "/absolute.tar", "child/archive.tar", "bad\\name.tar", "wrong.zip", ""):
            with self.subTest(name=name):
                self.reject_before_output(archive_name=name)

    def test_retention_marker_requires_policy_before_any_output(self):
        self.publication(lambda value: value["files"][0].update(derived_retention_revision=2))
        self.reject_before_output()

    def test_null_retention_policy_is_not_a_legacy_declaration(self):
        self.publication(lambda value: value.update(public_retention=None))
        self.reject_before_output()

    def test_deterministic_two_archives_and_manifests(self):
        first_manifest, first_archive, _ = self.package()
        for path in self.bundle.rglob("*"):
            if path.is_file():
                path.chmod(0o600)
                os.utime(path, (123456, 123456))
        second_manifest, second_archive, _ = self.package(
            output_root=self.base / "core2", archive_dir=self.base / "archives2"
        )
        self.assertEqual(first_archive.read_bytes(), second_archive.read_bytes())
        self.assertEqual(first_manifest.read_bytes(), second_manifest.read_bytes())

    def test_pax_metadata_and_private_permissions(self):
        _, archive, _ = self.package()
        self.assertEqual(stat.S_IMODE(archive.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.archives.stat().st_mode), 0o700)
        with tarfile.open(archive, "r:") as stream:
            self.assertEqual(stream.pax_headers["comment"], SOURCE)
            names = []
            for item in stream.getmembers():
                names.append(item.name.rstrip("/"))
                self.assertEqual(
                    (item.uid, item.gid, item.mtime, item.uname, item.gname), (0, 0, 0, "", "")
                )
                self.assertEqual(item.mode, 0o755 if item.isdir() else 0o644)
                self.assertTrue(item.isfile() or item.isdir())
            self.assertEqual(names, sorted(names, key=lambda name: name.encode("utf-8")))

    def test_true_git_tree_encoding_and_directory_sort(self):
        # This independent literal Git encoding checks foo.bar sorts before foo/.
        member = packager.Member(
            Path("unused"), (), 0, "", "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
        )
        self.assertEqual(packager.git_tree({}), "4b825dc642cb6eb9a060e54bf8d69288fbee4904")
        leaf = b"100644 a\0" + bytes.fromhex(member.git_blob)
        subtree = hashlib.sha1(b"tree " + str(len(leaf)).encode() + b"\0" + leaf).digest()
        payload = b"100644 foo.bar\0" + bytes.fromhex(member.git_blob) + b"40000 foo\0" + subtree
        expected = hashlib.sha1(b"tree " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
        self.assertEqual(packager.git_tree({"foo/a": member, "foo.bar": member}), expected)
        manifest, _, _ = self.package()
        value = json.loads(manifest.read_text())
        self.assertEqual(value["bundle_tree"], packager.git_tree(packager.inventory(self.bundle)))
        self.assertIn("SOURCE binding only", value["core_rule"][0])
        self.assertIn("Git archive not used", value["archive"]["git_version"])
        self.assertNotIn(str(self.base), manifest.read_text())

    def test_expected_publication_source_hash(self):
        self.reject_before_output(expected_publication_sha256="0" * 64)
        expected = sha((self.bundle / "publication.json").read_bytes())
        manifest, archive, _ = self.package(expected_publication_sha256=expected)
        self.assertEqual(self.verifier(manifest, archive), 0)

    def test_corrupted_gzip_hash(self):
        (self.bundle / "campaign.json.gz").write_bytes(b"corrupt")
        self.reject_before_output()

    def test_bad_gzip_even_with_updated_compressed_hash(self):
        data = b"not gzip"
        (self.bundle / "campaign.json.gz").write_bytes(data)
        self.publication(lambda value: value["files"][0].update(sanitized_gzip_sha256=sha(data)))
        self.reject_before_output()

    def test_wrong_decompressed_hash(self):
        self.publication(lambda value: value["files"][0].update(sanitized_json_sha256="0" * 64))
        self.reject_before_output()

    def test_nonjson_compressed_payload(self):
        raw = b"not json"
        data = gzip.compress(raw, mtime=0)
        (self.bundle / "campaign.json.gz").write_bytes(data)
        self.publication(
            lambda value: value["files"][0].update(
                sanitized_gzip_sha256=sha(data), sanitized_json_sha256=sha(raw)
            )
        )
        self.reject_before_output()

    def test_summary_publication_hash(self):
        self.publication(lambda value: value.update(summary_sha256="0" * 64))
        self.reject_before_output()

    def test_duplicate_publication_member(self):
        self.publication(lambda value: value["files"].append(copy.deepcopy(value["files"][0])))
        self.reject_before_output()

    def test_duplicate_publication_json_key(self):
        path = self.bundle / "publication.json"
        data = path.read_bytes()
        path.write_bytes(data.replace(b"{", b'{"status":"complete",', 1))
        self.reject_before_output()

    def test_path_traversal_publication_member(self):
        self.publication(lambda value: value["files"][0].update(file="../campaign.json.gz"))
        self.reject_before_output()

    def test_absolute_publication_member(self):
        self.publication(lambda value: value["files"][0].update(file="/campaign.json.gz"))
        self.reject_before_output()

    def test_backslash_publication_member(self):
        self.publication(lambda value: value["files"][0].update(file="case\\escape.json.gz"))
        self.reject_before_output()

    def test_unindexed_file(self):
        (self.bundle / "unexpected.json").write_text("{}")
        self.reject_before_output()

    def test_missing_indexed_member(self):
        (self.bundle / "campaign.json.gz").unlink()
        self.reject_before_output()

    def test_empty_directory(self):
        (self.bundle / "unexpected-empty").mkdir()
        self.reject_before_output()

    def test_file_symlink(self):
        target = self.bundle / "campaign.json.gz"
        target.unlink()
        target.symlink_to("coverage-declared.json.gz")
        self.reject_before_output()

    def test_directory_symlink(self):
        (self.bundle / "linked").symlink_to(self.bundle / "case-0", target_is_directory=True)
        self.reject_before_output()

    def test_hardlink(self):
        os.link(self.bundle / "summary.txt", self.base / "hardlink")
        self.reject_before_output()

    def test_special_fifo_does_not_block(self):
        os.mkfifo(self.bundle / "fifo")
        self.reject_before_output()

    def test_executable_data_rejected(self):
        (self.bundle / "README.md").chmod(0o755)
        self.reject_before_output()

    def test_wrong_source_label(self):
        self.reject_before_output(source_commit="1" * 40)

    def test_invalid_commit(self):
        self.reject_before_output(source_commit="main")

    def test_incomplete_publication(self):
        self.publication(lambda value: value.update(status="incomplete"))
        self.reject_before_output()

    def test_missing_paired_database(self):
        name = "case-0/generated-build-stage/databases.json.gz"
        (self.bundle / name).unlink()
        self.publication(
            lambda value: value.update(
                files=[entry for entry in value["files"] if entry["file"] != name]
            )
        )
        self.reject_before_output()

    def test_unsafe_bundle_arguments(self):
        for value in ("../escape", "/absolute", "docs//empty", "docs/./dot", "docs/../escape"):
            with self.subTest(value=value):
                self.reject_before_output(evidence_dir=value)

    def test_roots_overlap(self):
        for overrides in (
            {"output_root": self.source / "out"},
            {"archive_dir": self.source / "archives"},
            {"archive_dir": self.output / "archives"},
            {"output_root": self.base},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.package(**overrides)

    def test_no_overwrite_or_restart(self):
        self.package()
        old = (self.output / "packaging-receipt.json").read_bytes()
        with self.assertRaises(ValueError):
            self.package()
        self.assertEqual((self.output / "packaging-receipt.json").read_bytes(), old)

    def test_archive_directory_must_be_fresh(self):
        self.archives.mkdir()
        with self.assertRaises(ValueError):
            self.package()
        self.assertFalse(self.output.exists())

    def test_output_parent_symlink(self):
        (self.base / "linked-parent").symlink_to(self.base, target_is_directory=True)
        self.reject_before_output(output_root=self.base / "linked-parent" / "new-core")

    def test_member_size_bound(self):
        with patch.object(packager, "MAX_MEMBER", 10):
            self.reject_before_output()

    def test_archive_bound_no_success_manifest(self):
        with patch.object(packager, "MAX_ARCHIVE", 1), self.assertRaises(ValueError):
            self.package()
        self.assertFalse((self.output / (BUNDLE + "-core-manifest.json")).exists())
        self.assertFalse((self.output / "packaging-receipt.json").exists())

    def test_changed_input_during_copy_no_success(self):
        original = packager.checked_copy
        changed = False

        def mutate(member, target):
            nonlocal changed
            if not changed:
                changed = True
                member.path.write_bytes(b"changed")
            original(member, target)

        with patch.object(packager, "checked_copy", mutate), self.assertRaises(ValueError):
            self.package()
        self.assertFalse((self.output / "packaging-receipt.json").exists())

    def test_verifier_rejects_changed_core(self):
        manifest, archive, _ = self.package()
        (self.output / BUNDLE / "README.md").write_text("changed")
        self.assertEqual(self.verifier(manifest), 2)
        self.assertEqual(self.verifier(manifest, archive), 2)

    def test_verifier_rejects_corrupted_tar(self):
        manifest, archive, _ = self.package()
        archive.write_bytes(b"not tar")
        self.assertEqual(self.verifier(manifest, archive), 2)

    def test_verifier_rejects_member_attacks_even_with_updated_archive_hash(self):
        manifest, archive, _ = self.package()
        initial = archive.read_bytes()
        metadata = json.loads(manifest.read_text())
        for attack in (
            "duplicate",
            "traversal",
            "absolute",
            "symlink",
            "device",
            "unindexed",
            "missing",
            "changed-gzip",
            "comment",
        ):
            with self.subTest(attack=attack):
                output = io.BytesIO()
                with tarfile.open(fileobj=io.BytesIO(initial), mode="r:") as source:
                    members = [
                        (copy.copy(item), source.extractfile(item).read() if item.isfile() else b"")
                        for item in source.getmembers()
                    ]
                position = next(i for i, (item, _) in enumerate(members) if item.isfile())
                item, data = members[position]
                if attack == "duplicate":
                    members.append((copy.copy(item), data))
                elif attack in ("traversal", "absolute", "unindexed"):
                    item.name = {
                        "traversal": "../escape",
                        "absolute": "/escape",
                        "unindexed": BUNDLE + "/unindexed",
                    }[attack]
                elif attack in ("symlink", "device"):
                    item.type = tarfile.SYMTYPE if attack == "symlink" else tarfile.CHRTYPE
                    item.linkname, item.size = "outside", 0
                    members[position] = (item, b"")
                elif attack == "missing":
                    members.pop(position)
                elif attack == "changed-gzip":
                    position = next(
                        i
                        for i, (entry, _) in enumerate(members)
                        if entry.name.endswith("/syft.json.gz")
                    )
                    item, _ = members[position]
                    data = gzip.compress(b"{}", mtime=0)
                    item.size = len(data)
                    members[position] = (item, data)
                with tarfile.open(
                    fileobj=output,
                    mode="w",
                    format=tarfile.PAX_FORMAT,
                    pax_headers={"comment": "0" * 40 if attack == "comment" else SOURCE},
                ) as target:
                    for entry, payload in members:
                        target.addfile(entry, io.BytesIO(payload))
                archive.write_bytes(output.getvalue())
                updated = copy.deepcopy(metadata)
                updated["archive"].update(
                    sha256=sha(output.getvalue()), bytes=len(output.getvalue())
                )
                write_json(manifest, updated)
                self.assertEqual(self.verifier(manifest, archive), 2)

    def test_cli_failure_is_exit_two_not_findings(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                packager.main(
                    [
                        "--input-root",
                        str(self.source),
                        "--output-root",
                        str(self.output),
                        "--evidence-dir",
                        "../escape",
                        "--archive-dir",
                        str(self.archives),
                        "--source-commit",
                        SOURCE,
                    ]
                ),
                2,
            )
