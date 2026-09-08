"""Low-level immutable byte I/O shared by version-isolated stores."""
import hashlib
import json
import math
import os
from pathlib import Path
import stat

def _checked_path(path: Path) -> Path:
    """Check original components before resolve can hide a symlink or link/.. ."""
    absolute = Path(path).absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('immutable_path_invalid')
    return absolute.resolve()


def _json_value(value: object) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError('immutable_record_invalid')


def _canonical(value: object) -> bytes:
    try:
        _json_value(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('immutable_record_invalid') from exc


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fsync_directory(path: Path) -> None:
    # Directory-open and fsync errors must not be hidden as durable success.
    path = _checked_path(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_file(path: Path, data: bytes) -> None:
    path = _checked_path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _read_file(path: Path) -> bytes:
    path = _checked_path(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('immutable_store_corrupt')
        return stream.read()
