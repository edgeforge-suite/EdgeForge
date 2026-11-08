"""Ownership-aware sink for generated-application output.

This module is the intended central sink for all generation writes. P1a begins
routing the Java/file-map choke points (``java_emitter._write_java_file``,
``passthrough_helpers._write_java_file``, ``engine._write_file_map``) through it;
the remaining direct artifact writers (``build_emitter``, ``sql_emitter``,
``ui_emitter``, ``audit_emitter``, ``security_emitter``) are explicitly deferred
to P1a-2. It is dependency-free (stdlib only) so it sits at the bottom of the
generation import graph and never participates in import cycles. See
``docs/regenerate-maintain-model-design.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

Ownership = Literal["generated", "developer"]
_VALID_OWNERSHIP = ("generated", "developer")


def write_generated_file(path: Path, content: str, *, ownership: Ownership = "generated") -> Path:
    """Write generated output, honouring file ownership.

    ``ownership="generated"`` (the default) is EdgeForge-owned and is always
    overwritten on (re)generation. ``ownership="developer"`` is scaffolded once
    and never overwritten thereafter, so hand-added business logic survives
    regeneration. Developer-owned service subclasses and repository hygiene
    files both use this active preservation path.

    Raises:
        ValueError: if ``ownership`` is not a recognised value. Failing fast --
            before any directory or file is touched -- prevents a typo or stray
            dynamic value (e.g. ``"developper"``, ``None``) from silently taking
            the overwrite path and clobbering a developer-owned file, which is
            exactly the class of loss the regenerate/maintain model prevents.
    """
    if ownership not in _VALID_OWNERSHIP:
        raise ValueError(
            f"unknown ownership {ownership!r}; expected one of {_VALID_OWNERSHIP}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if ownership == "developer" and path.exists():
        return path
    path.write_text(content, encoding="utf-8")
    return path
