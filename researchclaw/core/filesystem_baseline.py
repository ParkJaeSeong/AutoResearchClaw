"""Typed project snapshots used to close the Stage-10 authoring delta."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


_MUTABLE_CONTROL_PATHS = frozenset(
    {
        ".researchclaw/state.json",
        "approvals/stage-09.json",
        "evaluation/events.jsonl",
    }
)
_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, order=True)
class FilesystemEntry:
    path: str
    kind: str
    sha256: str | None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _symlink_sha256(path: Path) -> str:
    return hashlib.sha256(os.readlink(path).encode("utf-8")).hexdigest()


def snapshot_project(root: Path) -> tuple[FilesystemEntry, ...]:
    """Snapshot authored/data paths without following symlinks.

    Engine-owned state, approvals, and evaluation logs are excluded because
    their contents change as part of validation and reapproval, not authoring.
    """
    root = Path(root)
    entries: list[FilesystemEntry] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as children:
            for child in sorted(children, key=lambda item: item.name):
                candidate = Path(child.path)
                relative = candidate.relative_to(root).as_posix()
                if relative in _MUTABLE_CONTROL_PATHS:
                    continue
                if child.is_symlink():
                    entries.append(
                        FilesystemEntry(relative, "symlink", _symlink_sha256(candidate))
                    )
                elif child.is_dir(follow_symlinks=False):
                    entries.append(FilesystemEntry(relative, "directory", None))
                    visit(candidate)
                elif child.is_file(follow_symlinks=False):
                    entries.append(
                        FilesystemEntry(relative, "regular_file", _file_sha256(candidate))
                    )
                else:
                    raise ValueError(f"unsupported filesystem entry at {relative}")

    visit(root)
    return tuple(sorted(entries))
