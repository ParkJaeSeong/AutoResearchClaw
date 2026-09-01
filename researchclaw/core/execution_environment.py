"""Closed, canonical evidence about the current Python execution environment."""

from __future__ import annotations

from collections.abc import Mapping
import ctypes
from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform as runtime_platform
import re
import stat
import sys
from types import MappingProxyType


_DISTRIBUTION_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_MACOS_PROC_PATH_BUFFER_BYTES = 4096


@dataclass(frozen=True)
class ExecutionEnvironment:
    """A closed description of the interpreter that will execute a package."""

    launcher: str
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
class _VerifiedExecutable:
    path: Path
    descriptor: int
    identity: Mapping[str, int | str]


@dataclass(frozen=True)
class _CurrentRuntimePaths:
    interpreter: Path
    process_image: Path
    base_interpreter: Path
    venv_prefix: Path | None


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
    process_image: str,
    process_image_identity: Mapping[str, object],
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
        "process_image": process_image,
        "process_image_identity": dict(process_image_identity),
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


def _require_exact_executable_path(path: Path) -> os.stat_result:
    """Require one canonical absolute path whose leaf and parents are not aliases."""
    if not path.is_absolute() or path != Path(os.path.abspath(path)):
        raise ValueError("execution_environment_unavailable")
    if path.resolve(strict=True) != path:
        raise ValueError("execution_environment_unavailable")
    path_status = os.lstat(path)
    if not stat.S_ISREG(path_status.st_mode) or not path_status.st_mode & 0o111:
        raise ValueError("execution_environment_unavailable")
    return path_status


def _canonical_runtime_executable(path: Path | str) -> Path:
    raw_path = Path(path)
    if not raw_path.is_absolute():
        raise ValueError("execution_environment_unavailable")
    resolved = raw_path.resolve(strict=True)
    _require_exact_executable_path(resolved)
    return resolved


def _open_verified_executable(path: Path) -> _VerifiedExecutable:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("execution_environment_unavailable")
    path_status = _require_exact_executable_path(path)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        )
        descriptor_status = os.fstat(descriptor)
        if (
            descriptor_status.st_dev != path_status.st_dev
            or descriptor_status.st_ino != path_status.st_ino
        ):
            raise ValueError("execution_environment_unavailable")
        identity = _descriptor_identity(descriptor)
        return _VerifiedExecutable(path, descriptor, identity)
    except (OSError, ValueError) as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError("execution_environment_unavailable") from error


def _linux_proc_self_executable() -> Path:
    """Return the kernel-attested process image name on Linux."""
    return Path(os.readlink("/proc/self/exe"))


def _macos_process_image_paths() -> tuple[Path, Path]:
    """Return independent libproc and dyld attestations of the loaded image."""
    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        proc_pidpath = libproc.proc_pidpath
        proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        proc_pidpath.restype = ctypes.c_int
        proc_buffer = ctypes.create_string_buffer(_MACOS_PROC_PATH_BUFFER_BYTES)
        proc_length = proc_pidpath(os.getpid(), proc_buffer, len(proc_buffer))
        if proc_length <= 0 or proc_length >= len(proc_buffer):
            raise ValueError("execution_environment_unavailable")

        libsystem = ctypes.CDLL(None, use_errno=True)
        get_executable_path = libsystem._NSGetExecutablePath
        get_executable_path.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        get_executable_path.restype = ctypes.c_int
        size = ctypes.c_uint32(0)
        if get_executable_path(None, ctypes.byref(size)) != -1 or size.value <= 1:
            raise ValueError("execution_environment_unavailable")
        dyld_buffer = ctypes.create_string_buffer(size.value)
        if get_executable_path(dyld_buffer, ctypes.byref(size)) != 0:
            raise ValueError("execution_environment_unavailable")

        proc_path = _canonical_runtime_executable(os.fsdecode(proc_buffer.value))
        dyld_path = _canonical_runtime_executable(os.fsdecode(dyld_buffer.value))
        return proc_path, dyld_path
    except (AttributeError, OSError, TypeError, ValueError, UnicodeError) as error:
        raise ValueError("execution_environment_unavailable") from error


def _attested_process_image() -> Path:
    if sys.platform == "darwin":
        proc_path, dyld_path = _macos_process_image_paths()
        if proc_path != dyld_path:
            raise ValueError("execution_environment_unavailable")
        return proc_path
    if sys.platform.startswith("linux"):
        return _canonical_runtime_executable(_linux_proc_self_executable())
    raise ValueError("execution_environment_unavailable")


def _macos_framework_root(path: Path) -> Path | None:
    expected_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    matches = [
        index
        for index in range(len(path.parts) - 2)
        if path.parts[index : index + 2] == ("Python.framework", "Versions")
        and path.parts[index + 2] == expected_version
    ]
    if len(matches) != 1:
        return None
    return Path(*path.parts[: matches[0] + 3])


def _current_venv_prefix(interpreter: Path, launcher: Path) -> Path | None:
    if sys.prefix == sys.base_prefix:
        return None
    prefix = Path(sys.prefix).resolve(strict=True)
    configuration = prefix / "pyvenv.cfg"
    configuration_status = os.lstat(configuration)
    launcher_status = os.lstat(launcher)
    if (
        configuration.resolve(strict=True) != configuration
        or not stat.S_ISREG(configuration_status.st_mode)
        or not launcher.is_absolute()
        or launcher != Path(os.path.abspath(launcher))
        or launcher.parent != prefix / "bin"
        or not (
            stat.S_ISLNK(launcher_status.st_mode)
            or (
                stat.S_ISREG(launcher_status.st_mode)
                and launcher_status.st_mode & 0o111
            )
        )
        or launcher.resolve(strict=True) != interpreter
    ):
        raise ValueError("execution_environment_unavailable")
    return prefix


def _current_runtime_paths() -> _CurrentRuntimePaths:
    launcher = Path(sys.executable)
    interpreter = _canonical_runtime_executable(launcher)
    base_interpreter = _canonical_runtime_executable(
        getattr(sys, "_base_executable", sys.executable)
    )
    process_image = _attested_process_image()
    venv_prefix = _current_venv_prefix(interpreter, launcher)
    if venv_prefix is None and interpreter != base_interpreter:
        raise ValueError("execution_environment_unavailable")

    if sys.platform == "darwin":
        framework_root = _macos_framework_root(base_interpreter)
        image_framework_root = _macos_framework_root(process_image)
        if framework_root is None or image_framework_root is None:
            if base_interpreter != process_image:
                raise ValueError("execution_environment_unavailable")
        elif (
            framework_root != image_framework_root
            or base_interpreter.parent != framework_root / "bin"
            or base_interpreter.name
            != f"python{sys.version_info.major}.{sys.version_info.minor}"
            or process_image
            != framework_root / "Resources/Python.app/Contents/MacOS/Python"
        ):
            raise ValueError("execution_environment_unavailable")
    elif sys.platform.startswith("linux"):
        expected_process_image = interpreter if venv_prefix is not None else base_interpreter
        if expected_process_image != process_image:
            raise ValueError("execution_environment_unavailable")
    else:
        raise ValueError("execution_environment_unavailable")

    return _CurrentRuntimePaths(
        interpreter=interpreter,
        process_image=process_image,
        base_interpreter=base_interpreter,
        venv_prefix=venv_prefix,
    )


def _open_runtime_executables(
    paths: _CurrentRuntimePaths,
) -> dict[Path, _VerifiedExecutable]:
    verified: dict[Path, _VerifiedExecutable] = {}
    try:
        for path in (paths.interpreter, paths.process_image, paths.base_interpreter):
            if path not in verified:
                verified[path] = _open_verified_executable(path)
        if paths.venv_prefix is not None:
            interpreter_identity = verified[paths.interpreter].identity
            base_identity = verified[paths.base_interpreter].identity
            if (
                interpreter_identity["size"] != base_identity["size"]
                or interpreter_identity["sha256"] != base_identity["sha256"]
            ):
                raise ValueError("execution_environment_unavailable")
        return verified
    except (OSError, ValueError) as error:
        for item in verified.values():
            os.close(item.descriptor)
        raise ValueError("execution_environment_unavailable") from error


def _revalidate_authoritative_paths(
    paths: _CurrentRuntimePaths,
    verified: Mapping[Path, _VerifiedExecutable],
) -> None:
    """Require every returned or loaded-image path to still name its held inode."""
    try:
        for path in dict.fromkeys((paths.interpreter, paths.process_image)):
            held = verified[path]
            reopened = _open_verified_executable(path)
            try:
                if reopened.identity != held.identity:
                    raise ValueError("execution_environment_unavailable")
            finally:
                os.close(reopened.descriptor)
    except (KeyError, OSError, ValueError) as error:
        raise ValueError("execution_environment_unavailable") from error


def inspect_execution_environment(
    interpreter: Path, required_distributions: tuple[str, ...]
) -> ExecutionEnvironment:
    """Inspect only the OS-attested interpreter running this process."""
    required = normalize_required_distributions(required_distributions)
    requested = Path(interpreter)
    verified: dict[Path, _VerifiedExecutable] = {}
    try:
        _require_exact_executable_path(requested)
        paths = _current_runtime_paths()
        if requested != paths.interpreter:
            raise ValueError("execution_environment_unavailable")
        verified = _open_runtime_executables(paths)
        dependencies = {
            name: importlib.metadata.version(name).strip() for name in required
        }
        if any(not version for version in dependencies.values()):
            raise ValueError("execution_environment_unavailable")
        implementation = sys.implementation.name.strip().lower()
        release = runtime_platform.python_version().strip()
        full_version = sys.version.strip()
        build = tuple(runtime_platform.python_build())
        system = sys.platform.strip().lower()
        architecture = runtime_platform.machine().strip().lower()
        if (
            not implementation
            or not release
            or not full_version
            or len(build) != 2
            or any(not item for item in build)
            or not system
            or not architecture
            or _current_runtime_paths() != paths
            or any(
                _descriptor_identity(item.descriptor) != item.identity
                for item in verified.values()
            )
        ):
            raise ValueError("execution_environment_unavailable")

        _revalidate_authoritative_paths(paths, verified)

        interpreter_identity = verified[paths.interpreter].identity
        process_image_identity = verified[paths.process_image].identity
        payload = canonical_environment_payload(
            interpreter=str(paths.interpreter),
            interpreter_identity=interpreter_identity,
            process_image=str(paths.process_image),
            process_image_identity=process_image_identity,
            python_implementation=implementation,
            python_version=release,
            python_full_version=full_version,
            python_build=(str(build[0]), str(build[1])),
            platform=system,
            machine=architecture,
            dependencies=dependencies,
        )
        return ExecutionEnvironment(
            launcher=(
                str(Path(sys.executable))
                if paths.venv_prefix is not None
                else str(paths.interpreter)
            ),
            interpreter=str(paths.interpreter),
            python_implementation=str(payload["python_implementation"]),
            python_version=str(payload["python_version"]),
            python_full_version=str(payload["python_full_version"]),
            python_build=(str(build[0]), str(build[1])),
            platform=str(payload["platform"]),
            machine=str(payload["machine"]),
            dependencies=MappingProxyType(dict(sorted(dependencies.items()))),
            fingerprint=execution_environment_fingerprint(payload),
        )
    except (
        AttributeError,
        importlib.metadata.PackageNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        UnicodeError,
    ) as error:
        raise ValueError("execution_environment_unavailable") from error
    finally:
        for item in verified.values():
            os.close(item.descriptor)
