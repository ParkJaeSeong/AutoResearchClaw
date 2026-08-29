"""Crash-durable JSON replacement helpers."""

from __future__ import annotations

import errno
import json
import os
import tempfile
from pathlib import Path
from typing import Mapping


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        directory_fd = os.open(directory, flags)
    except OSError:
        return
    try:
        try:
            os.fsync(directory_fd)
        except OSError as error:
            unsupported = {errno.EBADF, errno.EINVAL, getattr(errno, "ENOTSUP", errno.EINVAL)}
            if error.errno not in unsupported:
                raise
    finally:
        os.close(directory_fd)


def atomic_write_json(path: Path, payload: Mapping[str, object], *, prefix: str) -> None:
    """Write JSON through an fsynced temporary file and durable atomic replace."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=prefix,
            suffix=".tmp",
            delete=False,
            dir=destination.parent,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(destination)
        temporary_path = None
        _fsync_directory(destination.parent)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
