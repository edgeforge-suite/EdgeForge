"""Shared path-root enforcement for Engine entrypoints."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

ALLOWED_ROOTS_ENV = "EDGEFORGE_MCP_ALLOWED_ROOTS"
SHARED_MODE_ENV = "EDGEFORGE_SHARED_MODE"

RootMode = Literal["required", "cli"]


def resolve_allowed_file(path_value: str, *, purpose: str, mode: RootMode) -> Path:
    """Resolve a file path, enforcing configured allowed roots when required."""

    candidates, allowed_roots = _candidate_paths(path_value, purpose=purpose, mode=mode)
    if allowed_roots is None:
        candidate = candidates[0]
        if candidate.is_file():
            return candidate
        raise ValueError(f"{purpose} must point to an existing file: {candidate}")

    in_root_candidates = [
        candidate for candidate in candidates if _is_within_any_root(candidate, allowed_roots)
    ]
    for candidate in in_root_candidates:
        if candidate.is_file():
            return candidate
    if in_root_candidates:
        resolved = ", ".join(str(path) for path in in_root_candidates)
        raise ValueError(f"{purpose} must point to an existing file: {resolved}")
    _raise_outside_allowed_roots(
        purpose=purpose,
        candidates=candidates,
        allowed_roots=allowed_roots,
    )


def resolve_allowed_path(path_value: str, *, purpose: str, mode: RootMode) -> Path:
    """Resolve a path, enforcing configured allowed roots when required."""

    candidates, allowed_roots = _candidate_paths(path_value, purpose=purpose, mode=mode)
    if allowed_roots is None:
        return candidates[0]

    for resolved_path in candidates:
        if _is_within_any_root(resolved_path, allowed_roots):
            return resolved_path

    _raise_outside_allowed_roots(
        purpose=purpose,
        candidates=candidates,
        allowed_roots=allowed_roots,
    )


def cli_allowed_roots_active() -> bool:
    """Return whether CLI paths should be constrained by configured roots."""

    return _configured_allowed_roots() is not None


def ensure_cli_allowed_roots_if_shared_mode() -> None:
    """Fail closed in shared mode unless per-session allowed roots are configured."""

    if _shared_mode_enabled() and _configured_allowed_roots() is None:
        _raise_missing_allowed_roots()


def _candidate_paths(
    path_value: str,
    *,
    purpose: str,
    mode: RootMode,
) -> tuple[list[Path], tuple[Path, ...] | None]:
    if not path_value or not path_value.strip():
        raise ValueError(f"{purpose} must not be empty")

    allowed_roots = _allowed_roots_for_mode(mode)
    candidate = Path(path_value).expanduser()
    if allowed_roots is None:
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return [candidate.resolve(strict=False)], None
    if candidate.is_absolute():
        return [candidate.resolve(strict=False)], allowed_roots
    return [(root / candidate).resolve(strict=False) for root in allowed_roots], allowed_roots


def _allowed_roots_for_mode(mode: RootMode) -> tuple[Path, ...] | None:
    allowed_roots = _configured_allowed_roots()
    if allowed_roots is not None:
        return allowed_roots
    if mode == "required" or _shared_mode_enabled():
        _raise_missing_allowed_roots()
    return None


def _configured_allowed_roots() -> tuple[Path, ...] | None:
    configured = os.environ.get(ALLOWED_ROOTS_ENV)
    if configured is None or not configured.strip():
        return None
    roots = [
        Path(part).expanduser()
        for part in configured.split(os.pathsep)
        if part.strip()
    ]
    if not roots:
        return None
    return tuple(root.resolve(strict=False) for root in roots)


def _raise_missing_allowed_roots() -> None:
    raise ValueError(
        f"{ALLOWED_ROOTS_ENV} must be set to per-session, server-owned root(s); "
        "the Engine install tree and process cwd are never implicit roots."
    )


def _raise_outside_allowed_roots(
    *,
    purpose: str,
    candidates: Iterable[Path],
    allowed_roots: Iterable[Path],
) -> None:
    allowed = ", ".join(str(root) for root in allowed_roots)
    resolved = ", ".join(str(path) for path in candidates)
    raise ValueError(
        f"{purpose} must resolve inside an allowed root. "
        f"Resolved path(s): {resolved}. Allowed roots: {allowed}"
    )


def _is_within_any_root(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def _shared_mode_enabled() -> bool:
    configured = os.environ.get(SHARED_MODE_ENV)
    if configured is None:
        return False
    return configured.strip().lower() not in {"", "0", "false", "no", "off"}
