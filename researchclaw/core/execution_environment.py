"""Closed, canonical evidence about a Python execution environment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
from types import MappingProxyType


_DISTRIBUTION_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_PROBE_TIMEOUT_SECONDS = 10
_SNAPSHOT_PREFIX = ".researchclaw-execution-"
_PROBE_SOURCE = """
import importlib.metadata
import json
import platform
import sys

required = json.loads(sys.argv[1])
dependencies = {name: importlib.metadata.version(name) for name in required}
print(json.dumps({
    \"python_implementation\": sys.implementation.name.strip().lower(),
    \"python_version\": platform.python_version().strip(),
    \"python_full_version\": sys.version.strip(),
    \"python_build\": list(platform.python_build()),
    \"platform\": sys.platform.strip().lower(),
    \"machine\": platform.machine().strip().lower(),
    \"dependencies\": dict(sorted(dependencies.items())),
}, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\"), allow_nan=False))
"""


@dataclass(frozen=True)
class ExecutionEnvironment:
    """A closed description of the interpreter that will execute a package."""

    interpreter: str
    python_implementation: str
    python_version: str
    python_full_version: str
    python_build: tuple[str, str]
    platform: str
    machine: str
    dependencies: Mapping[str, str]
    fingerprint: str


@dataclass(frozen=True)
class _VerifiedInterpreter:
    path: Path
    snapshot_directory: Path
    descriptor: int
    identity: Mapping[str, int | str]


@dataclass(frozen=True)
class _VerifiedSnapshot:
    path: Path
    descriptor: int
    identity: Mapping[str, int | str]


def normalize_required_distributions(
    required_distributions: tuple[str, ...],
) -> tuple[str, ...]:
    """Return the unique PEP-503-like names used by the closed contract."""
    normalized: list[str] = []
    for name in required_distributions:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("execution_environment_unavailable")
        canonical = re.sub(r"[-_.]+", "-", name.strip().lower())
        if _DISTRIBUTION_NAME.fullmatch(canonical) is None:
            raise ValueError("execution_environment_unavailable")
        normalized.append(canonical)
    if len(set(normalized)) != len(normalized):
        raise ValueError("execution_environment_unavailable")
    return tuple(sorted(normalized))


def canonical_environment_payload(
    *,
    interpreter: str,
    interpreter_identity: Mapping[str, object],
    python_implementation: str,
    python_version: str,
    python_full_version: str,
    python_build: tuple[str, str],
    platform: str,
    machine: str,
    dependencies: Mapping[str, str],
) -> dict[str, object]:
    """Build the one serialized payload that determines a fingerprint."""
    return {
        "schema_version": 1,
        "interpreter": interpreter,
        "interpreter_identity": dict(interpreter_identity),
        "python_implementation": python_implementation.strip().lower(),
        "python_version": python_version.strip(),
        "python_full_version": python_full_version.strip(),
        "python_build": list(python_build),
        "platform": platform.strip().lower(),
        "machine": machine.strip().lower(),
        "dependencies": dict(sorted(dependencies.items())),
    }


def execution_environment_fingerprint(payload: Mapping[str, object]) -> str:
    """Hash a canonical execution-environment payload."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _descriptor_identity(descriptor: int) -> dict[str, int | str]:
    file_status = os.fstat(descriptor)
    if not stat.S_ISREG(file_status.st_mode) or not file_status.st_mode & 0o111:
        raise ValueError("execution_environment_unavailable")
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return {
        "device": file_status.st_dev,
        "inode": file_status.st_ino,
        "size": file_status.st_size,
        "mtime_ns": file_status.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def _open_verified_interpreter(interpreter: Path) -> _VerifiedInterpreter:
    if not interpreter.is_absolute():
        raise ValueError("execution_environment_unavailable")
    descriptor: int | None = None
    try:
        contract_path = Path(os.path.abspath(interpreter))
        resolved = contract_path.resolve(strict=True)
        is_venv_entrypoint = (contract_path.parent.parent / "pyvenv.cfg").is_file()
        if (
            resolved.is_symlink()
            or not hasattr(os, "O_NOFOLLOW")
            or (interpreter.is_symlink() and not is_venv_entrypoint)
        ):
            raise ValueError("execution_environment_unavailable")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
        descriptor = os.open(resolved, flags)
    except (OSError, RuntimeError, ValueError) as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError("execution_environment_unavailable") from error
    try:
        identity = _descriptor_identity(descriptor)
    except (OSError, ValueError) as error:
        os.close(descriptor)
        raise ValueError("execution_environment_unavailable") from error
    return _VerifiedInterpreter(
        contract_path,
        contract_path.parent if is_venv_entrypoint else resolved.parent,
        descriptor,
        identity,
    )


def _before_descriptor_probe(_verified: _VerifiedInterpreter) -> None:
    """Test seam between descriptor verification and descriptor execution."""


def _descriptor_execution_path(descriptor: int) -> str:
    path = Path("/dev/fd") / str(descriptor)
    if not path.exists():
        raise ValueError("execution_environment_unavailable")
    return str(path)


def _before_snapshot_subprocess(_snapshot: _VerifiedSnapshot) -> None:
    """Test seam immediately before the final snapshot pathname check."""


def _snapshot_path(directory: Path) -> tuple[int, Path]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    for _ in range(32):
        path = directory / f"{_SNAPSHOT_PREFIX}{secrets.token_hex(16)}"
        try:
            return os.open(path, flags, 0o700), path
        except FileExistsError:
            continue
    raise OSError("could not allocate execution snapshot")


def _same_snapshot_identity(
    identity: Mapping[str, int | str], expected: Mapping[str, int | str]
) -> bool:
    return identity == expected


def _unlink_owned_snapshot(path: Path, descriptor: int) -> None:
    """Remove a snapshot only when the visible name still identifies our FD."""
    pathname_status = os.stat(path, follow_symlinks=False)
    descriptor_status = os.fstat(descriptor)
    if (
        pathname_status.st_dev != descriptor_status.st_dev
        or pathname_status.st_ino != descriptor_status.st_ino
    ):
        raise ValueError("execution_environment_unavailable")
    path.unlink()


def _snapshot_descriptor(verified: _VerifiedInterpreter) -> _VerifiedSnapshot:
    """Copy one verified descriptor to a private executable on its filesystem."""
    descriptor: int | None = None
    snapshot_descriptor: int | None = None
    snapshot_path: Path | None = None
    try:
        descriptor, snapshot_path = _snapshot_path(verified.snapshot_directory)
        if os.fstat(descriptor).st_dev != verified.identity["device"]:
            raise ValueError("execution_environment_unavailable")
        if _descriptor_identity(verified.descriptor) != verified.identity:
            raise ValueError("execution_environment_unavailable")
        os.lseek(verified.descriptor, 0, os.SEEK_SET)
        with os.fdopen(os.dup(descriptor), "wb", closefd=True) as snapshot_file:
            while chunk := os.read(verified.descriptor, 1024 * 1024):
                snapshot_file.write(chunk)
            snapshot_file.flush()
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o700)
        os.close(descriptor)
        descriptor = None
        snapshot_descriptor = os.open(
            snapshot_path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
        )
        identity_descriptor = os.dup(snapshot_descriptor)
        try:
            snapshot_identity = _descriptor_identity(identity_descriptor)
        finally:
            os.close(identity_descriptor)
        if not (
            snapshot_identity["size"] == verified.identity["size"]
            and snapshot_identity["sha256"] == verified.identity["sha256"]
        ):
            raise ValueError("execution_environment_unavailable")
        snapshot = _VerifiedSnapshot(snapshot_path, snapshot_descriptor, snapshot_identity)
        snapshot_descriptor = None
        return snapshot
    except (OSError, ValueError) as error:
        if snapshot_path is not None:
            try:
                owned_descriptor = (
                    snapshot_descriptor
                    if snapshot_descriptor is not None
                    else descriptor
                )
                if owned_descriptor is not None:
                    _unlink_owned_snapshot(snapshot_path, owned_descriptor)
            except (OSError, ValueError):
                pass
        if descriptor is not None:
            os.close(descriptor)
        if snapshot_descriptor is not None:
            os.close(snapshot_descriptor)
        raise ValueError("execution_environment_unavailable") from error


def _validate_snapshot_path(snapshot: _VerifiedSnapshot) -> None:
    descriptor = os.open(
        snapshot.path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
    )
    try:
        if not _same_snapshot_identity(
            _descriptor_identity(descriptor), snapshot.identity
        ):
            raise ValueError("execution_environment_unavailable")
    finally:
        os.close(descriptor)


def _cleanup_snapshot(snapshot: _VerifiedSnapshot) -> None:
    try:
        _unlink_owned_snapshot(snapshot.path, snapshot.descriptor)
    except FileNotFoundError as error:
        raise ValueError("execution_environment_unavailable") from error
    finally:
        os.close(snapshot.descriptor)


def _probe_command(
    executable: str, required_distributions: tuple[str, ...], *, pass_fds: tuple[int, ...]
) -> dict[str, object]:
    completed = subprocess.run(
        [
            executable,
            "-I",
            "-c",
            _PROBE_SOURCE,
            json.dumps(required_distributions, separators=(",", ":")),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT_SECONDS,
        pass_fds=pass_fds,
    )
    if completed.returncode != 0:
        raise ValueError("execution_environment_unavailable")
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("execution_environment_unavailable")
    return value


def _probe_snapshot(
    verified: _VerifiedInterpreter, required_distributions: tuple[str, ...]
) -> dict[str, object]:
    snapshot = _snapshot_descriptor(verified)
    try:
        _before_snapshot_subprocess(snapshot)
        _validate_snapshot_path(snapshot)
        value = _probe_command(
            str(snapshot.path), required_distributions, pass_fds=(snapshot.descriptor,)
        )
        _validate_snapshot_path(snapshot)
        return value
    finally:
        _cleanup_snapshot(snapshot)


def _probe_execution_environment(
    verified: _VerifiedInterpreter, required_distributions: tuple[str, ...]
) -> dict[str, object]:
    try:
        _before_descriptor_probe(verified)
        try:
            value = _probe_command(
                _descriptor_execution_path(verified.descriptor),
                required_distributions,
                pass_fds=(verified.descriptor,),
            )
        except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired):
            value = _probe_snapshot(verified, required_distributions)
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
        UnicodeError,
    ) as error:
        raise ValueError("execution_environment_unavailable") from error
    fields = {
        "python_implementation",
        "python_version",
        "python_full_version",
        "python_build",
        "platform",
        "machine",
        "dependencies",
    }
    dependencies = value.get("dependencies") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or not all(isinstance(value[field], str) and value[field] for field in fields - {"dependencies", "python_build"})
        or not isinstance(value["python_build"], list)
        or len(value["python_build"]) != 2
        or any(not isinstance(item, str) or not item for item in value["python_build"])
        or not isinstance(dependencies, dict)
        or tuple(dependencies) != required_distributions
        or any(not isinstance(version, str) or not version for version in dependencies.values())
    ):
        raise ValueError("execution_environment_unavailable")
    return value


def inspect_execution_environment(
    interpreter: Path, required_distributions: tuple[str, ...]
) -> ExecutionEnvironment:
    """Inspect one regular, exact Python interpreter without a shell."""
    required = normalize_required_distributions(required_distributions)
    verified = _open_verified_interpreter(Path(interpreter))
    try:
        probe = _probe_execution_environment(verified, required)
        if _descriptor_identity(verified.descriptor) != verified.identity:
            raise ValueError("execution_environment_unavailable")
        dependencies = probe["dependencies"]
        assert isinstance(dependencies, dict)
        build = probe["python_build"]
        assert isinstance(build, list)
        payload = canonical_environment_payload(
            interpreter=str(verified.path),
            interpreter_identity=verified.identity,
            python_implementation=str(probe["python_implementation"]),
            python_version=str(probe["python_version"]),
            python_full_version=str(probe["python_full_version"]),
            python_build=(str(build[0]), str(build[1])),
            platform=str(probe["platform"]),
            machine=str(probe["machine"]),
            dependencies=dependencies,
        )
        return ExecutionEnvironment(
            interpreter=str(verified.path),
            python_implementation=str(payload["python_implementation"]),
            python_version=str(payload["python_version"]),
            python_full_version=str(payload["python_full_version"]),
            python_build=(str(build[0]), str(build[1])),
            platform=str(payload["platform"]),
            machine=str(payload["machine"]),
            dependencies=MappingProxyType(dict(sorted(dependencies.items()))),
            fingerprint=execution_environment_fingerprint(payload),
        )
    except (OSError, ValueError) as error:
        raise ValueError("execution_environment_unavailable") from error
    finally:
        os.close(verified.descriptor)
