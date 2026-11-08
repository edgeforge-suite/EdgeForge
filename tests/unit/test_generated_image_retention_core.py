"""Public-core semantic controls need no private evidence or product execution."""

import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from scripts import verify_generated_image_evidence_split as verifier

BUNDLE = "docs/handover-evidence/generated-images/2026-10-20-noble"
MANIFEST = BUNDLE + "-core-manifest.json"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def reseal(value):
    metadata = value["publication_projection"]
    if "rows" in metadata:
        for row, binding in zip(value["rows"], metadata["rows"], strict=True):
            binding["projected_sha256"] = digest(row)
            for role, entry in binding["bodies"].items():
                entry["projected_sha256"] = digest(row[role])
    metadata["projected_payload_sha256"] = digest(
        {key: item for key, item in value.items() if key != "publication_projection"}
    )


def write_core(root, manifest, name, data):
    path = root / BUNDLE / name
    path.write_bytes(data)
    entry = next(row for row in manifest["core"] if row["path"] == BUNDLE + "/" + name)
    entry.update(bytes=len(data), sha256=verifier.sha256(data), git_blob=verifier.git_blob(data))


def test_committed_retention_core_is_self_consistent_without_archive():
    result = verifier.verify(verifier.ROOT, verifier.ROOT / MANIFEST, evidence_dir=BUNDLE)
    assert result["status"] == "verified"
    assert result["archive"] == "not requested"
    vendor = json.loads(gzip.decompress((verifier.ROOT / BUNDLE / "residual-vendor-current.json.gz").read_bytes()))
    assert len(vendor["rows"]) == 6
    for row in vendor["rows"]:
        for role in ("global_advisory", "repository_advisory", "osv_advisory"):
            assert not {"description", "details", "summary"} & row[role].keys()


@pytest.mark.parametrize("change", ["range", "sources", "body", "source-hash", "interpreter", "source-index",
                                    "absent-policy", "null-policy"])
def test_coordinated_outer_hashes_do_not_bypass_projection_validation(tmp_path, change):
    root = tmp_path / "core"
    shutil.copytree(verifier.ROOT / BUNDLE, root / BUNDLE)
    manifest = json.loads((verifier.ROOT / MANIFEST).read_bytes())
    publication = json.loads((root / BUNDLE / "publication.json").read_bytes())
    name = "publication-replay.json.gz" if change == "interpreter" else "residual-vendor-current.json.gz"
    value = json.loads(gzip.decompress((root / BUNDLE / name).read_bytes()))
    if change == "range":
        del value["rows"][0]["affected_range"]
    elif change == "sources":
        del value["rows"][0]["source_evidence"]
    elif change == "body":
        value["rows"][0]["global_advisory"]["description"] = "synthetic non-public prose"
    elif change == "source-hash":
        value["publication_projection"]["source"]["gzip_sha256"] = "0" * 64
    elif change == "interpreter":
        value["command"][0] = "<host-0>/private-layout/python"
    elif change == "source-index":
        source = value["publication_projection"]["source"]["archive_member"]
        next(row for row in publication["files"] if row["file"] == source)["sanitized_gzip_sha256"] = "0" * 64
    else:
        value["rows"][0]["status"] = "CLOSED"
        if change == "absent-policy":
            del publication["public_retention"]
        else:
            publication["public_retention"] = None
    reseal(value)
    raw = canonical(value)
    packed = gzip.compress(raw, mtime=0)
    write_core(root, manifest, name, packed)
    entry = next(row for row in publication["files"] if row["file"] == name)
    entry.update(sanitized_json_sha256=verifier.sha256(raw), sanitized_gzip_sha256=verifier.sha256(packed))
    write_core(root, manifest, "publication.json", canonical(publication))
    target = root / MANIFEST
    target.write_bytes(canonical(manifest))
    assert verifier.main(["--root", str(root), "--manifest", str(target), "--evidence-dir", BUNDLE]) == 2


def test_inner_projection_marker_alone_requires_retention_declaration():
    name = "residual-vendor-current.json.gz"
    raw = (verifier.ROOT / BUNDLE / name).read_bytes()
    publication = json.loads((verifier.ROOT / BUNDLE / "publication.json").read_bytes())
    entry = next(row for row in publication["files"] if row["file"] == name)
    entry.pop("derived_retention_revision", None)
    with pytest.raises(ValueError, match="require.*retention declaration"):
        verifier.verify_public_projections({}, {name: entry}, lambda _: raw, with_sources=False)


@pytest.mark.skipif(not os.environ.get("EDGEFORGE_NOBLE_RETENTION_ARCHIVE"),
                    reason="private Noble retention archive is opt-in")
def test_real_retention_archive_reconstructs_public_projections():
    result = verifier.verify(verifier.ROOT, verifier.ROOT / MANIFEST,
                             Path(os.environ["EDGEFORGE_NOBLE_RETENTION_ARCHIVE"]), evidence_dir=BUNDLE)
    assert result["archive"] == "verified"
