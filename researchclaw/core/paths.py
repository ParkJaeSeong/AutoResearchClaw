"""Central containment checks for project-relative artifact paths."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath


def _reject_path(value: object, kind: str, reason: str) -> ValueError:
    return ValueError(f"unsafe {kind} path {value!r}: {reason}")


def validate_relative_path(value: object, *, kind: str = "artifact") -> str:
    """Return a normalized relative path string or reject unsafe syntax."""
    if not isinstance(value, str) or not value:
        raise _reject_path(value, kind, "path must be a non-empty string")
    if "\x00" in value:
        raise _reject_path(value, kind, "path contains a null byte")

    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise _reject_path(value, kind, "absolute paths are not allowed")

    raw_parts = re.split(r"[/\\]", value)
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise _reject_path(value, kind, "empty, current, and parent components are not allowed")
    if any(part == ".." for part in (*posix_path.parts, *windows_path.parts)):
        raise _reject_path(value, kind, "parent traversal is not allowed")
    return value


def resolve_contained_path(root: Path, relative_path: object, *, kind: str) -> Path:
    """Resolve a relative path beneath root without following symlink components."""
    value = validate_relative_path(relative_path, kind=kind)
    try:
        resolved_root = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise _reject_path(value, kind, f"root cannot be resolved: {error}") from error

    candidate = resolved_root / Path(value)
    cursor = resolved_root
    try:
        relative_parts = candidate.relative_to(resolved_root).parts
    except ValueError as error:
        raise _reject_path(value, kind, "path is outside the containing root") from error

    try:
        for part in relative_parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise _reject_path(value, kind, f"symlink component is not allowed: {part}")
        resolved_candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise _reject_path(value, kind, f"path cannot be resolved: {error}") from error

    if not resolved_candidate.is_relative_to(resolved_root):
        raise _reject_path(value, kind, "resolved path is outside the containing root")
    return candidate


def resolve_project_artifact(project_root: Path, relative_path: object) -> Path:
    """Resolve an artifact path safely beneath a research project root."""
    return resolve_contained_path(project_root, relative_path, kind="artifact")
