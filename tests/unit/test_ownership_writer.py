"""Ownership-aware generated-file sink — regenerate/maintain model, Phase P1a.

These tests pin the contract of ``write_generated_file``: the single sink every
generation write path now routes through. The ``developer`` branch is dormant in
P1a (no emitter passes it yet) but is exercised here so the scaffold-once
preservation guarantee is locked before the service generation-gap (P1b) switches
it on. See ``docs/regenerate-maintain-model-design.md``.
"""

from pathlib import Path

import pytest

from appbuilder.generation.file_writer import write_generated_file


def test_generated_ownership_overwrites_on_regeneration(tmp_path: Path) -> None:
    target = tmp_path / "src" / "Foo.java"

    write_generated_file(target, "v1", ownership="generated")
    assert target.read_text(encoding="utf-8") == "v1"

    # EdgeForge-owned files are regenerated wholesale every run.
    result = write_generated_file(target, "v2")  # default ownership == "generated"
    assert result == target
    assert target.read_text(encoding="utf-8") == "v2"


def test_developer_ownership_scaffolds_once_then_preserves(tmp_path: Path) -> None:
    target = tmp_path / "src" / "FooService.java"

    # First generation scaffolds the developer-owned file.
    write_generated_file(target, "// scaffold", ownership="developer")
    assert target.read_text(encoding="utf-8") == "// scaffold"

    # A developer adds business logic to their file.
    target.write_text("// scaffold\n// hand-written business logic", encoding="utf-8")

    # Regeneration MUST NOT overwrite developer-owned content.
    result = write_generated_file(target, "// scaffold", ownership="developer")
    assert result == target
    assert target.read_text(encoding="utf-8") == "// scaffold\n// hand-written business logic"


def test_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c" / "App.java"

    write_generated_file(target, "x")

    assert target.read_text(encoding="utf-8") == "x"


def test_unknown_ownership_raises_fast_without_writing(tmp_path: Path) -> None:
    # An existing developer-owned file must be untouched on a bad ownership value.
    existing = tmp_path / "src" / "Foo.java"
    existing.parent.mkdir(parents=True)
    existing.write_text("developer content", encoding="utf-8")
    with pytest.raises(ValueError):
        write_generated_file(existing, "CLOBBER", ownership="developper")  # typo
    assert existing.read_text(encoding="utf-8") == "developer content"

    # And a bad value must not create a new file or its parent directories.
    fresh = tmp_path / "new" / "Bar.java"
    with pytest.raises(ValueError):
        write_generated_file(fresh, "x", ownership=None)  # type: ignore[arg-type]
    assert not fresh.exists()
    assert not fresh.parent.exists()
