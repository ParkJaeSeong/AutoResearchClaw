"""Project-local immutable evidence objects, manifests, capacity, and garbage collection."""

from __future__ import annotations

from collections.abc import Mapping
import ctypes
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any

from .execution_gate import open_project_file_descriptor
from .models import ArtifactRef, ProjectState, StageStatus
from .events import EvaluationEvent, EventLog, event_log_for
from .project import ResearchProject
from .state import StateStore
from .paths import validate_relative_path
from .transactions import project_transaction


_CHUNK_SIZE = 1024 * 1024
_MANIFEST_MAX_BYTES = 1024 * 1024
_MINIMUM_CAPACITY_RESERVE = 16 * 1024 * 1024
_MAX_GC_ENTRIES = 4096
_MAX_GC_CONTEXT_FILES = 4096
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TEMPORARY_NAME = re.compile(r"\.publish-[A-Za-z0-9._-]+\.tmp\Z")
_QUARANTINE_ENTRY = re.compile(
    r"\.gc-([0-9a-f]{32})\.(data|json|moved|quarantined)\Z"
)
_REGISTRATION_ID = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?\Z")
_OBJECT_PREFIX = ".researchclaw/evidence/objects/"
_MANIFEST_PREFIX = ".researchclaw/evidence/manifests/"
_TEMPORARY_PREFIX = ".publish-"
_TEMPORARY_SUFFIX = ".tmp"
_QUARANTINE_PREFIX = ".gc-"
_QUARANTINE_MOVED_SUFFIX = ".moved"
_QUARANTINE_FINAL_SUFFIX = ".quarantined"
_QUARANTINE_METADATA_SUFFIX = ".json"
_QUARANTINE_DIRECTORY_RESERVE_PER_RECORD = 8192
RESULT_QUARANTINE_PENDING_PATH = ".researchclaw/evidence/quarantine/pending-result.json"
_RESULT_QUARANTINE_MAX_BYTES = 256 * 1024
_MANIFEST_SCAN_LIMIT = 4096
_MANIFEST_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?\.json\Z")


def _load_native_rename_noreplace():
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        try:
            operation = library.renameatx_np
        except AttributeError:
            return None
        flag = 0x00000004  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        try:
            operation = library.renameat2
        except AttributeError:
            return None
        flag = 0x00000001  # RENAME_NOREPLACE
    else:
        return None
    operation.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    operation.restype = ctypes.c_int
    return operation, flag


_NATIVE_RENAME_NOREPLACE = _load_native_rename_noreplace()


def _validate_dirfd_basename(name: str) -> None:
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise ValueError("unsafe evidence store basename")


def _native_rename_noreplace(
    source_descriptor: int,
    source_name: str,
    destination_descriptor: int,
    destination_name: str,
) -> None:
    _validate_dirfd_basename(source_name)
    _validate_dirfd_basename(destination_name)
    native = _NATIVE_RENAME_NOREPLACE
    if native is None:
        raise ValueError("native no-replace rename unavailable")
    operation, flag = native
    ctypes.set_errno(0)
    result = operation(
        source_descriptor,
        os.fsencode(source_name),
        destination_descriptor,
        os.fsencode(destination_name),
        flag,
    )
    if result != 0:
        error_number = ctypes.get_errno() or errno.EIO
        raise OSError(error_number, os.strerror(error_number), destination_name)


def _is_temporary_name(name: str) -> bool:
    if _TEMPORARY_NAME.fullmatch(name) is None:
        return False
    payload = name[len(_TEMPORARY_PREFIX) : -len(_TEMPORARY_SUFFIX)]
    return payload not in {".", ".."}


def _validate_gc_original_name(name: object) -> str:
    if not isinstance(name, str) or (
        _SHA256.fullmatch(name) is None and not _is_temporary_name(name)
    ):
        raise ValueError("invalid evidence GC original name")
    _validate_dirfd_basename(name)
    return name


@dataclass(frozen=True)
class EvidenceSource:
    role: str
    path: str
    expected_sha256: str
    expected_size: int


@dataclass(frozen=True)
class EvidenceObject:
    sha256: str
    size: int
    path: str


@dataclass(frozen=True)
class EvidenceCapacity:
    required_new_bytes: int
    available_bytes: int
    reusable_bytes: int


@dataclass(frozen=True)
class EvidenceGcPlan:
    objects: tuple[EvidenceObject, ...]
    temporary_paths: tuple[str, ...]
    total_bytes: int
    confirmation_token: str


@dataclass(frozen=True)
class EvidenceGcResult:
    collected_objects: tuple[EvidenceObject, ...]
    quarantined_objects: tuple[EvidenceObject, ...]
    quarantined_temporary_paths: tuple[str, ...]
    reclaimed_bytes: int
    quarantined_bytes: int


@dataclass(frozen=True)
class QuarantinedResult:
    original_path: str
    quarantine_path: str
    sha256: str
    size: int
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _after_result_quarantine_move() -> None:
    """Test seam after the durable move and before journal phase persistence."""


def _before_result_quarantine_move() -> None:
    """Test seam before the final source identity check and atomic move."""


def _after_result_quarantine_event() -> None:
    """Test seam after event append and before journal phase persistence."""


def _after_result_quarantine_state() -> None:
    """Test seam after state save and before journal removal."""


@dataclass(frozen=True)
class _FileSnapshot:
    name: str
    path: str
    device: int
    inode: int
    mode: int
    nlink: int
    size: int
    mtime_ns: int
    ctime_ns: int
    sha256: str | None


@dataclass(frozen=True)
class _GcSnapshot:
    plan: EvidenceGcPlan
    object_files: tuple[_FileSnapshot, ...]
    temporary_files: tuple[_FileSnapshot, ...]


def _validate_source(source: EvidenceSource) -> None:
    if not isinstance(source, EvidenceSource):
        raise TypeError("source must be an EvidenceSource")
    if not isinstance(source.role, str) or not source.role.strip():
        raise ValueError("evidence source role must be a non-empty string")
    validate_relative_path(source.path, kind="artifact")
    if _SHA256.fullmatch(source.expected_sha256) is None:
        raise ValueError("evidence source identity is invalid")
    if (
        not isinstance(source.expected_size, int)
        or isinstance(source.expected_size, bool)
        or source.expected_size < 0
    ):
        raise ValueError("evidence source identity is invalid")


def _same_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_dev == second.st_dev
        and first.st_ino == second.st_ino
        and first.st_mode == second.st_mode
        and first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
        and first.st_ctime_ns == second.st_ctime_ns
    )


def _write_all(descriptor: int, chunk: bytes) -> None:
    view = memoryview(chunk)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("evidence object write made no progress")
        view = view[written:]


def _cleanup_publication(
    *,
    source_descriptor: int,
    directory_descriptor: int,
    temporary_descriptor: int | None,
    temporary_name: str,
    temporary_exists: bool,
    directory_changed: bool,
) -> None:
    first_error: BaseException | None = None

    def attempt(operation) -> None:
        nonlocal first_error
        try:
            operation()
        except BaseException as error:
            if first_error is None:
                first_error = error

    if temporary_descriptor is not None:
        attempt(lambda: os.close(temporary_descriptor))
    if temporary_exists:
        attempt(lambda: os.unlink(temporary_name, dir_fd=directory_descriptor))
        directory_changed = True
    if directory_changed:
        attempt(lambda: os.fsync(directory_descriptor))
    attempt(lambda: os.close(directory_descriptor))
    attempt(lambda: os.close(source_descriptor))
    if first_error is not None:
        raise first_error


def _before_source_recheck(_descriptor: int) -> None:
    """Test seam after the stream and before the final source identity check."""


def _before_gc_removal() -> None:
    """Test seam immediately before GC repeats its complete dry-run scan."""


def _before_gc_candidate_quarantine(_snapshot: _FileSnapshot) -> None:
    """Test seam after final scan and before atomic candidate quarantine."""


def _before_gc_quarantine_verify(
    _snapshot: _FileSnapshot, _quarantine_name: str
) -> None:
    """Test seam after atomic quarantine and before moved-inode verification."""


def _before_gc_quarantine_delete(
    _snapshot: _FileSnapshot, _quarantine_name: str
) -> None:
    """Compatibility test seam before the final held-FD digest."""


def _after_gc_final_fd_digest(
    _snapshot: _FileSnapshot, _quarantine_name: str
) -> None:
    """Test seam after final digest, before non-mutating phase commit."""


def _after_gc_quarantine_destination_fsync(
    _snapshot: _FileSnapshot, _quarantine_name: str
) -> None:
    """Test seam after the move destination is durable, before source fsync."""


def _after_gc_quarantine_commit(
    _snapshot: _FileSnapshot, _quarantine_name: str
) -> None:
    """Test seam after the durable quarantined phase transition."""


def _before_capacity_measure(_directory_descriptor: int) -> None:
    """Test seam after destination open and before descriptor-bound capacity."""


def _descriptor_digest(descriptor: int) -> tuple[str, int, os.stat_result]:
    initial = os.fstat(descriptor)
    if not stat.S_ISREG(initial.st_mode):
        raise ValueError("evidence file is not regular")
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    observed_size = 0
    while chunk := os.read(descriptor, _CHUNK_SIZE):
        digest.update(chunk)
        observed_size += len(chunk)
    final = os.fstat(descriptor)
    if observed_size != initial.st_size or not _same_identity(initial, final):
        raise ValueError("evidence file changed while reading")
    return digest.hexdigest(), observed_size, final


def _snapshot(
    *, name: str, path: str, file_stat: os.stat_result, sha256: str | None
) -> _FileSnapshot:
    return _FileSnapshot(
        name=name,
        path=path,
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
        mode=file_stat.st_mode,
        nlink=file_stat.st_nlink,
        size=file_stat.st_size,
        mtime_ns=file_stat.st_mtime_ns,
        ctime_ns=file_stat.st_ctime_ns,
        sha256=sha256,
    )


def _reject_duplicate_keys(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if not isinstance(key, str) or key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ValueError("non-finite JSON constant")


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    if not isinstance(payload, Mapping):
        raise TypeError("evidence manifest payload must be a mapping")
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    chunks: list[bytes] = []
    size = 0
    try:
        for text in encoder.iterencode(dict(payload)):
            encoded = text.encode("utf-8")
            size += len(encoded)
            if size > _MANIFEST_MAX_BYTES:
                raise ValueError("evidence manifest exceeds byte limit")
            chunks.append(encoded)
    except (TypeError, ValueError, RecursionError) as error:
        if str(error) == "evidence manifest exceeds byte limit":
            raise
        raise ValueError("evidence manifest is not canonical JSON") from error
    return b"".join(chunks)


def _bounded_directory_names(
    directory_descriptor: int, *, limit: int, error_message: str
) -> list[str]:
    names: list[str] = []
    with os.scandir(directory_descriptor) as entries:
        for entry in entries:
            if len(names) >= limit:
                raise ValueError(error_message)
            names.append(entry.name)
    return names


class EvidenceStore:
    """Immutable content-addressed storage contained within one project."""

    def __init__(self, project_root: Path) -> None:
        try:
            root = Path(project_root).resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError("evidence project root is unavailable") from error
        if not root.is_dir():
            raise ValueError("evidence project root must be a directory")
        self.project_root = root
        self.evidence_root = root / ".researchclaw/evidence"
        self.objects_root = self.evidence_root / "objects"
        self.manifests_root = self.evidence_root / "manifests"
        self.quarantine_root = self.evidence_root / "gc-quarantine"
        self.results_quarantine_root = self.evidence_root / "quarantine/results"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for relative_parts in (
            (".researchclaw", "evidence", "objects"),
            (".researchclaw", "evidence", "manifests"),
            (".researchclaw", "evidence", "gc-quarantine"),
            (".researchclaw", "evidence", "quarantine", "results"),
        ):
            self._ensure_directory_chain(relative_parts)

    def _ensure_directory_chain(self, relative_parts: tuple[str, ...]) -> None:
        descriptor = os.open(
            self.project_root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            for part in relative_parts:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
                child = os.open(
                    part,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=descriptor,
                )
                os.close(descriptor)
                descriptor = child
            if relative_parts[-1] in {"gc-quarantine", "results"}:
                os.fchmod(descriptor, 0o700)
                os.fsync(descriptor)
        except (OSError, ValueError) as error:
            raise ValueError("evidence store path is not a regular directory") from error
        finally:
            os.close(descriptor)

    def _open_directory(self, path: Path) -> int:
        try:
            relative_parts = Path(path).relative_to(self.project_root).parts
        except ValueError as error:
            raise ValueError("evidence store directory is outside the project") from error
        descriptor = os.open(
            self.project_root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            for part in relative_parts:
                child = os.open(
                    part,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=descriptor,
                )
                os.close(descriptor)
                descriptor = child
            directory_stat = os.fstat(descriptor)
            if not stat.S_ISDIR(directory_stat.st_mode):
                raise ValueError("evidence store path is not a directory")
            if (
                Path(path) == self.quarantine_root
                and stat.S_IMODE(directory_stat.st_mode) != 0o700
            ):
                raise ValueError("evidence GC quarantine is not private")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    def _verify_object(
        self, directory_descriptor: int, digest: str, expected_size: int
    ) -> tuple[EvidenceObject, _FileSnapshot]:
        try:
            descriptor = os.open(
                digest,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=directory_descriptor,
            )
        except OSError as error:
            raise ValueError("evidence_object_integrity_failure") from error
        try:
            observed_digest, observed_size, file_stat = _descriptor_digest(descriptor)
        except (OSError, ValueError) as error:
            raise ValueError("evidence_object_integrity_failure") from error
        finally:
            os.close(descriptor)
        if (
            observed_digest != digest
            or observed_size != expected_size
            or file_stat.st_nlink != 1
        ):
            raise ValueError("evidence_object_integrity_failure")
        path = f"{_OBJECT_PREFIX}{digest}"
        evidence_object = EvidenceObject(digest, observed_size, path)
        return evidence_object, _snapshot(
            name=digest,
            path=path,
            file_stat=file_stat,
            sha256=observed_digest,
        )

    def preflight(self, sources: tuple[EvidenceSource, ...]) -> EvidenceCapacity:
        if not isinstance(sources, tuple):
            raise TypeError("sources must be a tuple of EvidenceSource values")
        required_new_bytes = 0
        reusable_bytes = 0
        identities: dict[str, int] = {}
        directory_descriptor = self._open_directory(self.objects_root)
        try:
            for source in sources:
                _validate_source(source)
                prior_size = identities.get(source.expected_sha256)
                if prior_size is not None:
                    if prior_size != source.expected_size:
                        raise ValueError("conflicting evidence source identities")
                    continue
                identities[source.expected_sha256] = source.expected_size
                try:
                    os.stat(
                        source.expected_sha256,
                        dir_fd=directory_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    required_new_bytes += source.expected_size
                else:
                    self._verify_object(
                        directory_descriptor,
                        source.expected_sha256,
                        source.expected_size,
                    )
                    reusable_bytes += source.expected_size
            _before_capacity_measure(directory_descriptor)
            file_system = os.fstatvfs(directory_descriptor)
            available_bytes = file_system.f_bavail * file_system.f_frsize
        finally:
            os.close(directory_descriptor)
        reserve = max(_MINIMUM_CAPACITY_RESERVE, required_new_bytes // 20)
        if available_bytes < required_new_bytes + reserve:
            raise ValueError("insufficient evidence store capacity")
        return EvidenceCapacity(required_new_bytes, available_bytes, reusable_bytes)

    def publish(self, source: EvidenceSource) -> EvidenceObject:
        _validate_source(source)
        with project_transaction(self.project_root):
            source_descriptor, _path = open_project_file_descriptor(
                self.project_root, source.path
            )
            try:
                directory_descriptor = self._open_directory(self.objects_root)
            except Exception:
                os.close(source_descriptor)
                raise
            temporary_name = (
                f"{_TEMPORARY_PREFIX}{secrets.token_hex(16)}{_TEMPORARY_SUFFIX}"
            )
            temporary_descriptor: int | None = None
            temporary_exists = False
            directory_changed = False
            try:
                initial = os.fstat(source_descriptor)
                if initial.st_size != source.expected_size:
                    raise ValueError("evidence source identity mismatch")
                temporary_descriptor = os.open(
                    temporary_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=directory_descriptor,
                )
                temporary_exists = True
                directory_changed = True
                digest = hashlib.sha256()
                observed_size = 0
                while chunk := os.read(source_descriptor, _CHUNK_SIZE):
                    digest.update(chunk)
                    observed_size += len(chunk)
                    _write_all(temporary_descriptor, chunk)
                os.fsync(temporary_descriptor)
                _before_source_recheck(source_descriptor)
                final = os.fstat(source_descriptor)
                if observed_size != initial.st_size or not _same_identity(initial, final):
                    raise ValueError("evidence source changed while publishing")
                if (
                    observed_size != source.expected_size
                    or digest.hexdigest() != source.expected_sha256
                ):
                    raise ValueError("evidence source identity mismatch")
                os.close(temporary_descriptor)
                temporary_descriptor = None
                try:
                    os.link(
                        temporary_name,
                        source.expected_sha256,
                        src_dir_fd=directory_descriptor,
                        dst_dir_fd=directory_descriptor,
                        follow_symlinks=False,
                    )
                    directory_changed = True
                except FileExistsError:
                    pass
                os.unlink(temporary_name, dir_fd=directory_descriptor)
                temporary_exists = False
                directory_changed = True
                os.fsync(directory_descriptor)
                evidence_object, _snapshot_value = self._verify_object(
                    directory_descriptor,
                    source.expected_sha256,
                    source.expected_size,
                )
                return evidence_object
            finally:
                _cleanup_publication(
                    source_descriptor=source_descriptor,
                    directory_descriptor=directory_descriptor,
                    temporary_descriptor=temporary_descriptor,
                    temporary_name=temporary_name,
                    temporary_exists=temporary_exists,
                    directory_changed=directory_changed,
                )

    def write_manifest(
        self, registration_id: str, payload: Mapping[str, object]
    ) -> ArtifactRef:
        if (
            not isinstance(registration_id, str)
            or _REGISTRATION_ID.fullmatch(registration_id) is None
        ):
            raise ValueError("invalid evidence registration ID")
        encoded = _canonical_json(payload)
        name = f"{registration_id}.json"
        relative_path = f"{_MANIFEST_PREFIX}{name}"
        with project_transaction(self.project_root):
            directory_descriptor = self._open_directory(self.manifests_root)
            descriptor: int | None = None
            created = False
            try:
                descriptor = os.open(
                    name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=directory_descriptor,
                )
                created = True
                _write_all(descriptor, encoded)
                os.fsync(descriptor)
                os.close(descriptor)
                descriptor = None
                os.fsync(directory_descriptor)
            except Exception:
                if descriptor is not None:
                    os.close(descriptor)
                    descriptor = None
                if created:
                    try:
                        os.unlink(name, dir_fd=directory_descriptor)
                        os.fsync(directory_descriptor)
                    except FileNotFoundError:
                        pass
                raise
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                os.close(directory_descriptor)
        return ArtifactRef(
            path=relative_path,
            sha256=hashlib.sha256(encoded).hexdigest(),
            size=len(encoded),
        )

    def _read_json_file(
        self, directory_descriptor: int, name: str, relative_path: str
    ) -> tuple[dict[str, object], dict[str, object]]:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_descriptor,
        )
        try:
            initial = os.fstat(descriptor)
            if not stat.S_ISREG(initial.st_mode):
                raise ValueError(f"evidence GC context is not regular: {relative_path}")
            if initial.st_size > _MANIFEST_MAX_BYTES:
                raise ValueError(f"evidence GC context exceeds byte limit: {relative_path}")
            chunks: list[bytes] = []
            remaining = _MANIFEST_MAX_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(_CHUNK_SIZE, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            final = os.fstat(descriptor)
            if len(payload) > _MANIFEST_MAX_BYTES:
                raise ValueError(f"evidence GC context exceeds byte limit: {relative_path}")
            if len(payload) != initial.st_size or not _same_identity(initial, final):
                raise ValueError(f"evidence GC context changed while reading: {relative_path}")
        finally:
            os.close(descriptor)
        try:
            value = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_constant,
            )
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as error:
            if "duplicate JSON key" in str(error):
                raise ValueError(f"duplicate JSON key in evidence GC context: {relative_path}") from error
            raise ValueError(f"invalid evidence GC context: {relative_path}") from error
        if not isinstance(value, dict):
            raise ValueError(f"evidence GC context must be an object: {relative_path}")
        context_identity: dict[str, object] = {
            "path": relative_path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
            "device": final.st_dev,
            "inode": final.st_ino,
            "mtime_ns": final.st_mtime_ns,
            "ctime_ns": final.st_ctime_ns,
        }
        return value, context_identity

    def _context_references(
        self, candidate_paths: set[str]
    ) -> tuple[set[str], tuple[dict[str, object], ...]]:
        referenced: set[str] = set()
        identities: list[dict[str, object]] = []
        manifest_descriptor = self._open_directory(self.manifests_root)
        try:
            manifest_names = sorted(
                _bounded_directory_names(
                    manifest_descriptor,
                    limit=_MAX_GC_CONTEXT_FILES,
                    error_message="evidence GC context file limit exceeded",
                )
            )
            for name in manifest_names:
                relative_path = f"{_MANIFEST_PREFIX}{name}"
                value, identity = self._read_json_file(
                    manifest_descriptor, name, relative_path
                )
                identities.append(identity)
                self._find_references(value, referenced, candidate_paths)
        finally:
            os.close(manifest_descriptor)

        metadata_root = self.project_root / ".researchclaw"
        metadata_descriptor = self._open_directory(metadata_root)
        try:
            active_names: list[str] = []
            scanned_entries = 0
            with os.scandir(metadata_descriptor) as entries:
                for entry in entries:
                    if scanned_entries >= _MAX_GC_CONTEXT_FILES:
                        raise ValueError("evidence GC context file limit exceeded")
                    scanned_entries += 1
                    name = entry.name
                    if "pending" not in name.lower() and "journal" not in name.lower():
                        continue
                    if len(identities) + len(active_names) >= _MAX_GC_CONTEXT_FILES:
                        raise ValueError("evidence GC context file limit exceeded")
                    active_names.append(name)
            active_names.sort()
            for name in active_names:
                relative_path = f".researchclaw/{name}"
                value, identity = self._read_json_file(
                    metadata_descriptor, name, relative_path
                )
                identities.append(identity)
                self._find_references(value, referenced, candidate_paths)
        finally:
            os.close(metadata_descriptor)
        return referenced, tuple(identities)

    def _find_references(
        self, value: object, references: set[str], candidate_paths: set[str]
    ) -> None:
        if isinstance(value, dict):
            path = value.get("path")
            digest = value.get("sha256")
            size = value.get("size")
            if isinstance(path, str) and path.startswith(_OBJECT_PREFIX):
                if path in candidate_paths:
                    references.add(path)
                expected_digest = path.removeprefix(_OBJECT_PREFIX)
                if _is_temporary_name(expected_digest):
                    pass
                elif (
                    _SHA256.fullmatch(expected_digest) is None
                    or digest != expected_digest
                    or not isinstance(size, int)
                    or isinstance(size, bool)
                    or size < 0
                ):
                    raise ValueError("malformed evidence object reference")
            elif (
                isinstance(digest, str)
                and _SHA256.fullmatch(digest) is not None
                and isinstance(size, int)
                and not isinstance(size, bool)
                and size >= 0
            ):
                object_path = f"{_OBJECT_PREFIX}{digest}"
                if object_path in candidate_paths:
                    references.add(object_path)
            for item in value.values():
                self._find_references(item, references, candidate_paths)
        elif isinstance(value, list):
            for item in value:
                self._find_references(item, references, candidate_paths)
        elif isinstance(value, str) and value in candidate_paths:
            references.add(value)

    def _gc_snapshot(self) -> _GcSnapshot:
        directory_descriptor = self._open_directory(self.objects_root)
        object_pairs: list[tuple[EvidenceObject, _FileSnapshot]] = []
        temporary_files: list[_FileSnapshot] = []
        try:
            names = sorted(
                _bounded_directory_names(
                    directory_descriptor,
                    limit=_MAX_GC_ENTRIES,
                    error_message="evidence GC entry limit exceeded",
                )
            )
            for name in names:
                relative_path = f"{_OBJECT_PREFIX}{name}"
                if _SHA256.fullmatch(name) is not None:
                    file_stat = os.stat(
                        name,
                        dir_fd=directory_descriptor,
                        follow_symlinks=False,
                    )
                    evidence_object, object_snapshot = self._verify_object(
                        directory_descriptor, name, file_stat.st_size
                    )
                    object_pairs.append((evidence_object, object_snapshot))
                elif _is_temporary_name(name):
                    descriptor = os.open(
                        name,
                        os.O_RDONLY
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_NONBLOCK", 0),
                        dir_fd=directory_descriptor,
                    )
                    try:
                        digest, _size, file_stat = _descriptor_digest(descriptor)
                        if file_stat.st_nlink != 1:
                            raise ValueError("evidence temporary has unsafe link topology")
                        if not stat.S_ISREG(file_stat.st_mode):
                            raise ValueError("evidence temporary is not regular")
                    finally:
                        os.close(descriptor)
                    temporary_files.append(
                        _snapshot(
                            name=name,
                            path=relative_path,
                            file_stat=file_stat,
                            sha256=digest,
                        )
                    )
        finally:
            os.close(directory_descriptor)

        candidate_paths = {
            *(item.path for item, _snapshot_value in object_pairs),
            *(snapshot.path for snapshot in temporary_files),
        }
        references, context_identities = self._context_references(candidate_paths)
        object_pairs = [
            pair for pair in object_pairs if pair[0].path not in references
        ]
        temporary_files = [
            snapshot for snapshot in temporary_files if snapshot.path not in references
        ]

        token_payload: dict[str, Any] = {
            "schema_version": 1,
            "contexts": list(context_identities),
            "objects": [asdict(snapshot) for _object, snapshot in object_pairs],
            "temporary_files": [asdict(snapshot) for snapshot in temporary_files],
        }
        token = hashlib.sha256(
            json.dumps(
                token_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        objects = tuple(item for item, _snapshot_value in object_pairs)
        temporary_paths = tuple(item.path for item in temporary_files)
        total_bytes = sum(item.size for item in objects) + sum(
            item.size for item in temporary_files
        )
        return _GcSnapshot(
            plan=EvidenceGcPlan(objects, temporary_paths, total_bytes, token),
            object_files=tuple(snapshot for _item, snapshot in object_pairs),
            temporary_files=tuple(temporary_files),
        )

    def plan_gc(self) -> EvidenceGcPlan:
        with project_transaction(self.project_root):
            self._recover_quarantine()
            return self._gc_snapshot().plan

    @staticmethod
    def _quarantine_name(original_name: str) -> str:
        _validate_gc_original_name(original_name)
        return f"{_QUARANTINE_PREFIX}{secrets.token_hex(16)}{_QUARANTINE_MOVED_SUFFIX}"

    @staticmethod
    def _quarantine_metadata_name(data_name: str) -> str:
        match = _QUARANTINE_ENTRY.fullmatch(data_name)
        if match is None or match.group(2) not in {"data", "moved"}:
            raise ValueError("invalid evidence GC quarantine data name")
        return f"{_QUARANTINE_PREFIX}{match.group(1)}{_QUARANTINE_METADATA_SUFFIX}"

    @staticmethod
    def _quarantine_final_name(moved_name: str) -> str:
        match = _QUARANTINE_ENTRY.fullmatch(moved_name)
        if match is None or match.group(2) not in {"data", "moved"}:
            raise ValueError("invalid evidence GC quarantine moved name")
        return f"{_QUARANTINE_PREFIX}{match.group(1)}{_QUARANTINE_FINAL_SUFFIX}"

    @staticmethod
    def _snapshot_from_quarantine_record(value: object) -> _FileSnapshot:
        if not isinstance(value, dict) or set(value) not in (
            {"schema_version", "original_name", "snapshot"},
            {"schema_version", "phase", "original_name", "snapshot"},
        ):
            raise ValueError("invalid evidence GC quarantine journal")
        if value.get("schema_version") != 1:
            raise ValueError("invalid evidence GC quarantine journal")
        if "phase" in value and value.get("phase") != "prepared":
            raise ValueError("invalid evidence GC quarantine journal")
        original_name = _validate_gc_original_name(value.get("original_name"))
        snapshot_value = value.get("snapshot")
        field_names = {
            "name",
            "path",
            "device",
            "inode",
            "mode",
            "nlink",
            "size",
            "mtime_ns",
            "ctime_ns",
            "sha256",
        }
        if not isinstance(snapshot_value, dict) or set(snapshot_value) != field_names:
            raise ValueError("invalid evidence GC quarantine journal")
        if (
            snapshot_value.get("name") != original_name
            or snapshot_value.get("path") != f"{_OBJECT_PREFIX}{original_name}"
        ):
            raise ValueError("invalid evidence GC quarantine journal")
        integer_fields = (
            "device",
            "inode",
            "mode",
            "nlink",
            "size",
            "mtime_ns",
            "ctime_ns",
        )
        if any(
            not isinstance(snapshot_value.get(field), int)
            or isinstance(snapshot_value.get(field), bool)
            or snapshot_value[field] < 0
            for field in integer_fields
        ):
            raise ValueError("invalid evidence GC quarantine journal")
        digest = snapshot_value.get("sha256")
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ValueError("invalid evidence GC quarantine journal")
        if (
            not stat.S_ISREG(snapshot_value["mode"])
            or snapshot_value["nlink"] != 1
        ):
            raise ValueError("invalid evidence GC quarantine journal")
        return _FileSnapshot(
            name=original_name,
            path=snapshot_value["path"],
            device=snapshot_value["device"],
            inode=snapshot_value["inode"],
            mode=snapshot_value["mode"],
            nlink=snapshot_value["nlink"],
            size=snapshot_value["size"],
            mtime_ns=snapshot_value["mtime_ns"],
            ctime_ns=snapshot_value["ctime_ns"],
            sha256=digest,
        )

    @staticmethod
    def _quarantine_record_bytes(snapshot: _FileSnapshot) -> bytes:
        return _canonical_json(
            {
                "schema_version": 1,
                "phase": "prepared",
                "original_name": snapshot.name,
                "snapshot": asdict(snapshot),
            }
        )

    def _write_quarantine_record(
        self,
        quarantine_descriptor: int,
        metadata_name: str,
        snapshot: _FileSnapshot,
    ) -> None:
        encoded = self._quarantine_record_bytes(snapshot)
        descriptor = os.open(
            metadata_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=quarantine_descriptor,
        )
        try:
            _write_all(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(quarantine_descriptor)

    def _reserve_quarantine_capacity(
        self,
        quarantine_descriptor: int,
        snapshots: tuple[_FileSnapshot, ...],
    ) -> None:
        if not snapshots:
            return
        names = _bounded_directory_names(
            quarantine_descriptor,
            limit=_MAX_GC_ENTRIES,
            error_message=(
                "evidence GC quarantine tombstone/record entry limit exceeded"
            ),
        )
        required_entries = len(snapshots) * 2
        if len(names) + required_entries > _MAX_GC_ENTRIES:
            raise ValueError("evidence GC quarantine entry capacity exceeded")
        required_bytes = sum(
            len(self._quarantine_record_bytes(snapshot))
            + _QUARANTINE_DIRECTORY_RESERVE_PER_RECORD
            for snapshot in snapshots
        )
        file_system = os.fstatvfs(quarantine_descriptor)
        available_bytes = file_system.f_bavail * file_system.f_frsize
        if available_bytes < required_bytes:
            raise ValueError("evidence GC quarantine byte capacity exceeded")

    @staticmethod
    def _durable_rename_noreplace(
        source_descriptor: int,
        source_name: str,
        destination_descriptor: int,
        destination_name: str,
    ) -> None:
        _native_rename_noreplace(
            source_descriptor,
            source_name,
            destination_descriptor,
            destination_name,
        )
        os.fsync(destination_descriptor)
        os.fsync(source_descriptor)

    def _restore_quarantined(
        self,
        objects_descriptor: int,
        quarantine_descriptor: int,
        data_name: str,
        original_name: str,
    ) -> bool:
        try:
            self._durable_rename_noreplace(
                quarantine_descriptor,
                data_name,
                objects_descriptor,
                original_name,
            )
        except FileExistsError:
            return False
        return True

    def _recover_quarantine(self) -> None:
        objects_descriptor = self._open_directory(self.objects_root)
        try:
            quarantine_descriptor = self._open_directory(self.quarantine_root)
        except Exception:
            os.close(objects_descriptor)
            raise
        try:
            names = _bounded_directory_names(
                quarantine_descriptor,
                limit=_MAX_GC_ENTRIES,
                error_message=(
                    "evidence GC quarantine tombstone/record entry limit exceeded"
                ),
            )
            records: dict[str, dict[str, str]] = {}
            for name in names:
                match = _QUARANTINE_ENTRY.fullmatch(name)
                if match is None:
                    raise ValueError("evidence GC quarantine contains an unknown entry")
                records.setdefault(match.group(1), {})[match.group(2)] = name
            for record in records.values():
                metadata_name = record.get("json")
                if metadata_name is None:
                    raise ValueError("evidence GC quarantine data has no journal")
                value, _identity = self._read_json_file(
                    quarantine_descriptor,
                    metadata_name,
                    f".researchclaw/evidence/gc-quarantine/{metadata_name}",
                )
                snapshot = self._snapshot_from_quarantine_record(value)
                phase_names = [
                    name
                    for phase in ("data", "moved", "quarantined")
                    if (name := record.get(phase)) is not None
                ]
                if len(phase_names) > 1:
                    raise ValueError("evidence GC quarantine has conflicting phases")
                data_name = phase_names[0] if phase_names else None
                if data_name is None:
                    try:
                        os.stat(
                            snapshot.name,
                            dir_fd=objects_descriptor,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError as error:
                        raise ValueError(
                            "evidence GC quarantine journal has no data or original"
                        ) from error
                    continue
                descriptor = os.open(
                    data_name,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=quarantine_descriptor,
                )
                matches = False
                try:
                    file_stat = os.fstat(descriptor)
                    if not stat.S_ISREG(file_stat.st_mode):
                        raise ValueError("evidence GC quarantine entry is not regular")
                    digest, size, file_stat = _descriptor_digest(descriptor)
                    matches = (
                        digest == snapshot.sha256
                        and size == snapshot.size
                        and self._quarantined_snapshot_matches(file_stat, snapshot)
                    )
                finally:
                    os.close(descriptor)
                if record.get("quarantined") is not None:
                    if not matches:
                        raise ValueError("evidence GC quarantine identity mismatch")
                    continue
                if record.get("data") is not None and file_stat.st_size == 0:
                    final_name = self._quarantine_final_name(data_name)
                    self._durable_rename_noreplace(
                        quarantine_descriptor,
                        data_name,
                        quarantine_descriptor,
                        final_name,
                    )
                    continue
                restored = self._restore_quarantined(
                    objects_descriptor,
                    quarantine_descriptor,
                    data_name,
                    snapshot.name,
                )
                if not restored:
                    raise ValueError("evidence GC quarantine recovery is blocked")
                if not matches:
                    raise ValueError("evidence GC quarantine identity mismatch")
        finally:
            os.close(quarantine_descriptor)
            os.close(objects_descriptor)

    @staticmethod
    def _quarantined_snapshot_matches(
        file_stat: os.stat_result, snapshot: _FileSnapshot
    ) -> bool:
        return (
            file_stat.st_dev == snapshot.device
            and file_stat.st_ino == snapshot.inode
            and file_stat.st_mode == snapshot.mode
            and file_stat.st_nlink == snapshot.nlink
            and file_stat.st_size == snapshot.size
            and file_stat.st_mtime_ns == snapshot.mtime_ns
        )

    def _quarantine_candidate(
        self,
        objects_descriptor: int,
        quarantine_descriptor: int,
        snapshot: _FileSnapshot,
    ) -> None:
        moved_name = self._quarantine_name(snapshot.name)
        metadata_name = self._quarantine_metadata_name(moved_name)
        final_name = self._quarantine_final_name(moved_name)
        self._write_quarantine_record(
            quarantine_descriptor, metadata_name, snapshot
        )
        _before_gc_candidate_quarantine(snapshot)
        try:
            _native_rename_noreplace(
                objects_descriptor,
                snapshot.name,
                quarantine_descriptor,
                moved_name,
            )
        except FileNotFoundError as error:
            raise ValueError("evidence GC plan is stale") from error
        os.fsync(quarantine_descriptor)
        _after_gc_quarantine_destination_fsync(snapshot, moved_name)
        os.fsync(objects_descriptor)
        _before_gc_quarantine_verify(snapshot, moved_name)
        descriptor: int | None = None
        verification_error: BaseException | None = None
        restorable = False
        matches = False
        verified_stat: os.stat_result | None = None
        try:
            descriptor = os.open(
                moved_name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=quarantine_descriptor,
            )
            file_stat = os.fstat(descriptor)
            restorable = stat.S_ISREG(file_stat.st_mode)
            digest, size, verified_stat = _descriptor_digest(descriptor)
            matches = (
                digest == snapshot.sha256
                and size == snapshot.size
                and self._quarantined_snapshot_matches(verified_stat, snapshot)
            )
        except (OSError, ValueError) as error:
            verification_error = error
        if not matches:
            if descriptor is not None:
                os.close(descriptor)
                descriptor = None
            if restorable:
                self._restore_quarantined(
                    objects_descriptor,
                    quarantine_descriptor,
                    moved_name,
                    snapshot.name,
                )
            if verification_error is not None:
                raise verification_error
            raise ValueError("evidence GC plan is stale")
        assert descriptor is not None
        assert verified_stat is not None
        try:
            _before_gc_quarantine_delete(snapshot, moved_name)
            final_digest, final_size, final_verified_stat = _descriptor_digest(
                descriptor
            )
            if (
                final_digest != snapshot.sha256
                or final_size != snapshot.size
                or not self._quarantined_snapshot_matches(
                    final_verified_stat, snapshot
                )
            ):
                raise ValueError("evidence GC held inode changed before phase commit")
            _after_gc_final_fd_digest(snapshot, moved_name)
            # POSIX exposes no operation that atomically proves st_nlink == 1 and
            # reclaims an open inode. Mutating it here could damage a hardlink
            # added after the digest, so this transition preserves the full inode.
            self._durable_rename_noreplace(
                quarantine_descriptor,
                moved_name,
                quarantine_descriptor,
                final_name,
            )
            _after_gc_quarantine_commit(snapshot, final_name)
            held_stat = os.fstat(descriptor)
            try:
                current_path_stat = os.stat(
                    final_name,
                    dir_fd=quarantine_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError as error:
                raise ValueError("evidence GC quarantine pathname changed") from error
            if (
                current_path_stat.st_dev != held_stat.st_dev
                or current_path_stat.st_ino != held_stat.st_ino
                or not stat.S_ISREG(current_path_stat.st_mode)
            ):
                raise ValueError("evidence GC quarantine pathname changed")
        finally:
            os.close(descriptor)

    def collect(
        self, plan: EvidenceGcPlan, confirm_token: str
    ) -> EvidenceGcResult:
        if not isinstance(plan, EvidenceGcPlan):
            raise TypeError("plan must be an EvidenceGcPlan")
        if (
            not isinstance(confirm_token, str)
            or not hmac.compare_digest(plan.confirmation_token, confirm_token)
        ):
            raise ValueError("evidence GC confirmation token mismatch")
        with project_transaction(self.project_root):
            self._recover_quarantine()
            current = self._gc_snapshot()
            if current.plan != plan:
                raise ValueError("evidence GC plan is stale")
            _before_gc_removal()
            current = self._gc_snapshot()
            if current.plan != plan:
                raise ValueError("evidence GC plan is stale")
            directory_descriptor = self._open_directory(self.objects_root)
            try:
                quarantine_descriptor = self._open_directory(self.quarantine_root)
                try:
                    snapshots = (*current.object_files, *current.temporary_files)
                    self._reserve_quarantine_capacity(
                        quarantine_descriptor, snapshots
                    )
                    for snapshot in current.object_files:
                        self._quarantine_candidate(
                            directory_descriptor, quarantine_descriptor, snapshot
                        )
                    for snapshot in current.temporary_files:
                        self._quarantine_candidate(
                            directory_descriptor, quarantine_descriptor, snapshot
                        )
                finally:
                    os.close(quarantine_descriptor)
            finally:
                os.close(directory_descriptor)
        return EvidenceGcResult(
            collected_objects=(),
            quarantined_objects=plan.objects,
            quarantined_temporary_paths=plan.temporary_paths,
            reclaimed_bytes=0,
            quarantined_bytes=plan.total_bytes,
        )


def _result_quarantine_pending_path(project: ResearchProject) -> Path:
    return project.root / RESULT_QUARANTINE_PENDING_PATH


def _result_quarantine_target(state: ProjectState) -> ProjectState:
    relative = "experiment/results.json"
    return replace(
        state,
        current_stage=12,
        status=StageStatus.READY,
        completed_stages=tuple(stage for stage in state.completed_stages if stage != 12),
        next_action="prepare_run",
        artifacts={
            path: ref
            for path, ref in state.artifacts.items()
            if path != relative and not path.startswith(".researchclaw/evidence/")
        },
        last_error={
            "error_class": "needs_revision",
            "stage_id": 12,
            "attempt_number": state.retry_counts.get("12", 0) + 1,
            "issues": [{
                "code": "research_result_quarantined",
                "path": relative,
                "message": "Prepare a fresh execution contract before rerunning.",
            }],
            "artifact_hashes": {},
            "recommended_action": "prepare_run",
            "retry_state": "stage_twelve_registration_recovery",
        },
    )


def _persist_result_quarantine(project: ResearchProject, pending: Mapping[str, object]) -> None:
    encoded = _canonical_json(pending)
    if len(encoded) > _RESULT_QUARANTINE_MAX_BYTES:
        raise ValueError("result quarantine journal exceeds byte limit")
    from .persistence import atomic_write_json

    atomic_write_json(
        _result_quarantine_pending_path(project),
        json.loads(encoded.decode("utf-8")),
        prefix="result-quarantine-",
        compact=True,
    )


def _load_result_quarantine(project: ResearchProject) -> dict[str, object] | None:
    path = _result_quarantine_pending_path(project)
    if not os.path.lexists(path):
        return None
    try:
        descriptor, _ = open_project_file_descriptor(project.root, RESULT_QUARANTINE_PENDING_PATH)
        try:
            initial = os.fstat(descriptor)
            if initial.st_size > _RESULT_QUARANTINE_MAX_BYTES:
                raise ValueError
            chunks: list[bytes] = []
            observed = 0
            while chunk := os.read(descriptor, min(64 * 1024, _RESULT_QUARANTINE_MAX_BYTES + 1 - observed)):
                chunks.append(chunk)
                observed += len(chunk)
                if observed > _RESULT_QUARANTINE_MAX_BYTES:
                    raise ValueError
            final = os.fstat(descriptor)
            if observed != initial.st_size or not _same_identity(initial, final):
                raise ValueError
            encoded = b"".join(chunks)
        finally:
            os.close(descriptor)
        raw = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
        required = {
            "schema_version", "project_id", "reason", "original_path",
            "quarantine_path", "destination_name", "sha256", "size",
            "device", "inode", "mode", "mtime_ns", "ctime_ns",
            "prior_state", "target_state", "event", "event_offset", "phase",
        }
        if not isinstance(raw, dict) or set(raw) != required or raw.get("schema_version") != 1:
            raise ValueError
        prior = ProjectState.from_dict(raw["prior_state"])
        target = ProjectState.from_dict(raw["target_state"])
        destination_name = raw.get("destination_name")
        digest = raw.get("sha256")
        reason = raw.get("reason")
        integer_fields = ("size", "device", "inode", "mode", "mtime_ns", "ctime_ns")
        if (
            raw.get("project_id") != project.state.project_id
            or prior.project_id != project.state.project_id
            or target != _result_quarantine_target(prior)
            or raw.get("phase") not in {"prepared", "copied", "event_written", "state_saved"}
            or raw.get("original_path") != "experiment/results.json"
            or not isinstance(destination_name, str)
            or re.fullmatch(r"\d{8}T\d{12}Z-[0-9a-f]{64}\.json", destination_name) is None
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or not destination_name.endswith(f"-{digest}.json")
            or not isinstance(reason, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason) is None
            or any(
                not isinstance(raw.get(field), int)
                or isinstance(raw.get(field), bool)
                or raw[field] < 0
                for field in integer_fields
            )
            or not stat.S_ISREG(raw["mode"])
            or raw.get("quarantine_path")
            != f".researchclaw/evidence/quarantine/results/{raw['destination_name']}"
            or not isinstance(raw.get("event_offset"), int)
            or isinstance(raw.get("event_offset"), bool)
        ):
            raise ValueError
        event = EvaluationEvent.from_dict(raw["event"])
        if (
            event.project_id != project.state.project_id
            or event.type != "research_result_quarantined"
            or event.payload != {
                "original_path": raw["original_path"],
                "sha256": digest,
                "size": raw["size"],
                "reason": reason,
                "quarantine_path": raw["quarantine_path"],
            }
        ):
            raise ValueError
        return raw
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("result_quarantine_interrupted") from error


def _result_referenced_by_valid_manifest(project: ResearchProject, store: EvidenceStore) -> bool:
    from .evidence_registration import (
        EVIDENCE_PENDING_PATH,
        _read_manifest_snapshot,
        _revalidate_manifest_path,
        _validate_manifest_bindings,
        _verify_manifest_objects,
    )

    if os.path.lexists(project.root / EVIDENCE_PENDING_PATH):
        return True
    directory = store._open_directory(store.manifests_root)
    try:
        names = _bounded_directory_names(
            directory,
            limit=_MANIFEST_SCAN_LIMIT,
            error_message="evidence manifest scan limit exceeded",
        )
    finally:
        os.close(directory)
    for name in names:
        if _MANIFEST_NAME.fullmatch(name) is None:
            continue
        manifest_path = f".researchclaw/evidence/manifests/{name}"
        try:
            snapshot = _read_manifest_snapshot(project.root, manifest_path)
            _validate_manifest_bindings(project, manifest_path, snapshot.payload)
            _verify_manifest_objects(project, snapshot.payload)
            _revalidate_manifest_path(project.root, snapshot)
        except ValueError:
            continue
        entries = snapshot.payload.get("objects")
        if isinstance(entries, list) and any(
            isinstance(entry, Mapping)
            and entry.get("role") == "result"
            and entry.get("source_path") == "experiment/results.json"
            for entry in entries
        ):
            return True
    return False


def _result_quarantine_event_at_offset(
    project: ResearchProject, event: EvaluationEvent, offset: int
) -> bool:
    path = project.root / "evaluation/events.jsonl"
    descriptor = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        total = os.fstat(descriptor).st_size
        record = EventLog._bounded_record(event)
        if total < offset or total > offset + len(record):
            raise ValueError("result_quarantine_interrupted")
        if total == offset:
            return False
        os.lseek(descriptor, offset, os.SEEK_SET)
        remaining = total - offset
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ValueError("result_quarantine_interrupted")
            chunks.append(chunk)
            remaining -= len(chunk)
        fragment = b"".join(chunks)
        if fragment == record:
            return True
        if not fragment or len(fragment) >= len(record) or not record.startswith(fragment):
            raise ValueError("result_quarantine_interrupted")
        os.ftruncate(descriptor, offset)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return False


def _recover_result_quarantine_locked(
    project: ResearchProject, pending: dict[str, object]
) -> QuarantinedResult:
    prior = ProjectState.from_dict(pending["prior_state"])
    target = ProjectState.from_dict(pending["target_state"])
    store = EvidenceStore(project.root)
    quarantine_directory = store._open_directory(store.results_quarantine_root)
    destination_name = str(pending["destination_name"])
    try:
        destination_exists = True
        try:
            os.stat(destination_name, dir_fd=quarantine_directory, follow_symlinks=False)
        except FileNotFoundError:
            destination_exists = False
        if not destination_exists:
            if pending["phase"] != "prepared":
                raise ValueError("result_quarantine_interrupted")
            expected_identity = (
                pending["device"], pending["inode"], pending["mode"], pending["size"],
                pending["mtime_ns"], pending["ctime_ns"],
            )
            source_descriptor, _ = open_project_file_descriptor(
                project.root, "experiment/results.json"
            )
            destination: int | None = None
            try:
                source_stat = os.fstat(source_descriptor)
                if (
                    source_stat.st_dev, source_stat.st_ino, source_stat.st_mode,
                    source_stat.st_size, source_stat.st_mtime_ns, source_stat.st_ctime_ns,
                ) != expected_identity or source_stat.st_nlink != 1:
                    raise ValueError("result quarantine source changed")
                _before_result_quarantine_move()
                destination = os.open(
                    destination_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o400,
                    dir_fd=quarantine_directory,
                )
                digest = hashlib.sha256()
                observed = 0
                while chunk := os.read(source_descriptor, _CHUNK_SIZE):
                    digest.update(chunk)
                    observed += len(chunk)
                    _write_all(destination, chunk)
                os.fsync(destination)
                final_source = os.fstat(source_descriptor)
                if (
                    observed != pending["size"]
                    or digest.hexdigest() != pending["sha256"]
                    or (
                        source_stat.st_dev,
                        source_stat.st_ino,
                        source_stat.st_mode,
                        source_stat.st_size,
                        source_stat.st_mtime_ns,
                    )
                    != (
                        final_source.st_dev,
                        final_source.st_ino,
                        final_source.st_mode,
                        final_source.st_size,
                        final_source.st_mtime_ns,
                    )
                ):
                    raise ValueError("result quarantine source changed")
            finally:
                if destination is not None:
                    os.close(destination)
                os.close(source_descriptor)
            os.fsync(quarantine_directory)
            _after_result_quarantine_move()
        destination = os.open(
            destination_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=quarantine_directory,
        )
        try:
            digest, size, moved_stat = _descriptor_digest(destination)
        finally:
            os.close(destination)
        if (
            digest != pending["sha256"]
            or size != pending["size"]
            or moved_stat.st_nlink != 1
        ):
            raise ValueError("result quarantine identity changed")
        if pending["phase"] == "prepared":
            pending["phase"] = "copied"
            _persist_result_quarantine(project, pending)
    finally:
        os.close(quarantine_directory)

    event = EvaluationEvent.from_dict(pending["event"])
    event_present = _result_quarantine_event_at_offset(
        project, event, int(pending["event_offset"])
    )
    if not event_present:
        event_path = project.root / "evaluation/events.jsonl"
        actual_offset = event_path.stat().st_size if event_path.exists() else 0
        if actual_offset != pending["event_offset"]:
            raise ValueError("result_quarantine_interrupted")
        event_log_for(project.root).append_locked(
            event, expected_offset=int(pending["event_offset"])
        )
        _after_result_quarantine_event()
    pending["phase"] = "event_written"
    _persist_result_quarantine(project, pending)
    current = ResearchProject.open_readonly(project.root)
    if current.state == prior:
        StateStore(project.root / ".researchclaw").save(target)
        _after_result_quarantine_state()
    elif current.state != target:
        raise ValueError("result_quarantine_interrupted")
    pending["phase"] = "state_saved"
    _persist_result_quarantine(project, pending)
    path = _result_quarantine_pending_path(project)
    path.unlink()
    parent_descriptor = os.open(
        path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)
    return QuarantinedResult(
        str(pending["original_path"]), str(pending["quarantine_path"]),
        str(pending["sha256"]), int(pending["size"]), str(pending["reason"]),
    )


def recover_pending_result_quarantine(
    project: ResearchProject,
) -> QuarantinedResult | None:
    with project_transaction(project.root, allow_pending=True):
        current = ResearchProject.open_readonly(project.root)
        pending = _load_result_quarantine(current)
        return None if pending is None else _recover_result_quarantine_locked(current, pending)


def quarantine_unregistered_result(
    project: ResearchProject, reason: str, confirm: bool
) -> QuarantinedResult:
    """Copy one mutable result into owned quarantine without moving its pathname."""
    if confirm is not True:
        raise ValueError("result quarantine requires --confirm")
    if not isinstance(reason, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason) is None:
        raise ValueError("result quarantine reason is invalid")
    with project_transaction(project.root, allow_pending=True):
        from .evidence_registration import recover_pending_evidence_registration

        recover_pending_evidence_registration(project)
        current = ResearchProject.open_readonly(project.root)
        pending = _load_result_quarantine(current)
        if pending is not None:
            return _recover_result_quarantine_locked(current, pending)
        store = EvidenceStore(current.root)
        if _result_referenced_by_valid_manifest(current, store):
            raise ValueError("registered evidence cannot be quarantined")
        source_descriptor, _ = open_project_file_descriptor(
            current.root, "experiment/results.json"
        )
        try:
            digest, size, source_stat = _descriptor_digest(source_descriptor)
        finally:
            os.close(source_descriptor)
        if source_stat.st_nlink != 1:
            raise ValueError("result quarantine requires an unlinked regular file")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination_name = f"{timestamp}-{digest}.json"
        quarantine_path = f".researchclaw/evidence/quarantine/results/{destination_name}"
        target = _result_quarantine_target(current.state)
        event_path = current.root / "evaluation/events.jsonl"
        event_offset = event_path.stat().st_size if event_path.exists() else 0
        event = EvaluationEvent.create(
            "research_result_quarantined", current.state.project_id,
            {
                "original_path": "experiment/results.json", "sha256": digest,
                "size": size, "reason": reason, "quarantine_path": quarantine_path,
            },
        )
        pending = {
            "schema_version": 1, "project_id": current.state.project_id,
            "reason": reason, "original_path": "experiment/results.json",
            "quarantine_path": quarantine_path, "destination_name": destination_name,
            "sha256": digest, "size": size, "device": source_stat.st_dev,
            "inode": source_stat.st_ino, "mode": source_stat.st_mode,
            "mtime_ns": source_stat.st_mtime_ns, "ctime_ns": source_stat.st_ctime_ns,
            "prior_state": current.state.to_dict(), "target_state": target.to_dict(),
            "event": event.to_dict(), "event_offset": event_offset, "phase": "prepared",
        }
        _persist_result_quarantine(current, pending)
        return _recover_result_quarantine_locked(current, pending)
