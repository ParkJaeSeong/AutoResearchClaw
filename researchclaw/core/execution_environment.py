"""Closed, canonical evidence about a Python execution environment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from types import MappingProxyType


_DISTRIBUTION_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_PROBE_TIMEOUT_SECONDS = 10
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
    platform: str
    machine: str
    dependencies: Mapping[str, str]
    fingerprint: str


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
    platform: str,
    machine: str,
    dependencies: Mapping[str, str],
) -> dict[str, object]:
    """Build the one serialized payload that determines a fingerprint."""
    return {
        "schema_version": 1,
        "interpreter": interpreter,
        "interpreter_identity": dict(interpreter_identity),
        "python_implementation": python_implementation,
        "python_version": python_version,
        "platform": platform,
        "machine": machine,
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


def _open_verified_interpreter(interpreter: Path) -> tuple[Path, dict[str, int | str]]:
    if not interpreter.is_absolute() or interpreter.is_symlink():
        raise ValueError("execution_environment_unavailable")
    try:
        resolved = interpreter.resolve(strict=True)
        if resolved.is_symlink():
            raise ValueError("execution_environment_unavailable")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError("execution_environment_unavailable") from error
    try:
        file_status = os.fstat(descriptor)
        if not stat.S_ISREG(file_status.st_mode) or not file_status.st_mode & 0o111:
            raise ValueError("execution_environment_unavailable")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
    except OSError as error:
        raise ValueError("execution_environment_unavailable") from error
    finally:
        os.close(descriptor)
    return resolved, {
        "device": file_status.st_dev,
        "inode": file_status.st_ino,
        "size": file_status.st_size,
        "mtime_ns": file_status.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def _probe_execution_environment(
    interpreter: Path, required_distributions: tuple[str, ...]
) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [
                str(interpreter),
                "-I",
                "-c",
                _PROBE_SOURCE,
                json.dumps(required_distributions, separators=(",", ":")),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            raise ValueError("execution_environment_unavailable")
        value = json.loads(completed.stdout)
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
        "platform",
        "machine",
        "dependencies",
    }
    dependencies = value.get("dependencies") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or not all(isinstance(value[field], str) and value[field] for field in fields - {"dependencies"})
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
    resolved, identity = _open_verified_interpreter(Path(interpreter))
    probe = _probe_execution_environment(resolved, required)
    dependencies = probe["dependencies"]
    assert isinstance(dependencies, dict)
    payload = canonical_environment_payload(
        interpreter=str(resolved),
        interpreter_identity=identity,
        python_implementation=str(probe["python_implementation"]),
        python_version=str(probe["python_version"]),
        platform=str(probe["platform"]),
        machine=str(probe["machine"]),
        dependencies=dependencies,
    )
    return ExecutionEnvironment(
        interpreter=str(resolved),
        python_implementation=str(probe["python_implementation"]),
        python_version=str(probe["python_version"]),
        platform=str(probe["platform"]),
        machine=str(probe["machine"]),
        dependencies=MappingProxyType(dict(sorted(dependencies.items()))),
        fingerprint=execution_environment_fingerprint(payload),
    )
