"""Generation entry points."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .audit import render_generated_file_header

if TYPE_CHECKING:
    from .engine import GenerationReport


def generate_application(*args: Any, **kwargs: Any):
    """Lazily import the generation engine to avoid package import cycles."""

    from .engine import generate_application as _generate_application

    return _generate_application(*args, **kwargs)


def __getattr__(name: str):
    if name == "GenerationReport":
        from .engine import GenerationReport

        return GenerationReport
    raise AttributeError(name)


__all__ = ["render_generated_file_header", "GenerationReport", "generate_application"]
