"""Durable project-file snapshots used to close authored stage deltas."""

from __future__ import annotations

import os
from pathlib import Path


def snapshot_project_paths(root: Path) -> tuple[str, ...]:
    """Return sorted project-relative file and symlink paths without following links."""
    root = Path(root)
    paths: set[str] = set()
    for directory, directories, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in directories:
            candidate = directory_path / name
            if candidate.is_symlink():
                paths.add(candidate.relative_to(root).as_posix())
        for name in files:
            candidate = directory_path / name
            paths.add(candidate.relative_to(root).as_posix())
    return tuple(sorted(paths))
