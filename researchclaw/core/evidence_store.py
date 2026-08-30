"""Project-local immutable evidence objects, manifests, capacity, and garbage collection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any

from .execution_gate import open_project_file_descriptor
from .models import ArtifactRef
from .paths import validate_relative_path
from .transactions import project_transaction


_CHUNK_SIZE = 1024 * 1024
_MANIFEST_MAX_BYTES = 1024 * 1024
_MINIMUM_CAPACITY_RESERVE = 16 * 1024 * 1024
_MAX_GC_ENTRIES = 4096
_MAX_GC_CONTEXT_FILES = 4096
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REGISTRATION_ID = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?\Z")
_OBJECT_PREFIX = ".researchclaw/evidence/objects/"
_MANIFEST_PREFIX = ".researchclaw/evidence/manifests/"
_TEMPORARY_PREFIX = ".publish-"
_TEMPORARY_SUFFIX = ".tmp"
_QUARANTINE_PREFIX = ".gc-"


def _is_temporary_name(name: str) -> bool:
    return name.startswith(_TEMPORARY_PREFIX) and name.endswith(_TEMPORARY_SUFFIX)


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
    """Test seam after moved-inode verification and before private deletion."""


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
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for relative_parts in (
            (".researchclaw", "evidence", "objects"),
            (".researchclaw", "evidence", "manifests"),
            (".researchclaw", "evidence", "gc-quarantine"),
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
            if relative_parts[-1] == "gc-quarantine":
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
                        file_stat = os.fstat(descriptor)
                        if not stat.S_ISREG(file_stat.st_mode):
                            raise ValueError("evidence temporary is not regular")
                    finally:
                        os.close(descriptor)
                    temporary_files.append(
                        _snapshot(
                            name=name,
                            path=relative_path,
                            file_stat=file_stat,
                            sha256=None,
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
        return (
            f"{_QUARANTINE_PREFIX}{secrets.token_hex(16)}-"
            f"{original_name.encode('utf-8').hex()}"
        )

    @staticmethod
    def _quarantine_original(name: str) -> str:
        if not name.startswith(_QUARANTINE_PREFIX):
            raise ValueError("evidence GC quarantine contains an unknown entry")
        token, separator, encoded = name.removeprefix(_QUARANTINE_PREFIX).partition("-")
        if (
            not separator
            or len(token) != 32
            or any(character not in "0123456789abcdef" for character in token)
        ):
            raise ValueError("evidence GC quarantine contains an unknown entry")
        try:
            original = bytes.fromhex(encoded).decode("utf-8")
        except (UnicodeError, ValueError) as error:
            raise ValueError(
                "evidence GC quarantine contains an unknown entry"
            ) from error
        if _SHA256.fullmatch(original) is None and not _is_temporary_name(original):
            raise ValueError("evidence GC quarantine contains an unknown entry")
        return original

    def _restore_quarantined(
        self,
        objects_descriptor: int,
        quarantine_descriptor: int,
        quarantine_name: str,
        original_name: str,
    ) -> bool:
        try:
            os.link(
                quarantine_name,
                original_name,
                src_dir_fd=quarantine_descriptor,
                dst_dir_fd=objects_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            quarantine_stat = os.stat(
                quarantine_name,
                dir_fd=quarantine_descriptor,
                follow_symlinks=False,
            )
            original_stat = os.stat(
                original_name,
                dir_fd=objects_descriptor,
                follow_symlinks=False,
            )
            if (
                stat.S_ISREG(quarantine_stat.st_mode)
                and stat.S_ISREG(original_stat.st_mode)
                and quarantine_stat.st_dev == original_stat.st_dev
                and quarantine_stat.st_ino == original_stat.st_ino
            ):
                os.unlink(quarantine_name, dir_fd=quarantine_descriptor)
                os.fsync(quarantine_descriptor)
                return True
            return False
        os.fsync(objects_descriptor)
        os.unlink(quarantine_name, dir_fd=quarantine_descriptor)
        os.fsync(quarantine_descriptor)
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
                error_message="evidence GC quarantine entry limit exceeded",
            )
            for name in sorted(names):
                original_name = self._quarantine_original(name)
                descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=quarantine_descriptor,
                )
                try:
                    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                        raise ValueError("evidence GC quarantine entry is not regular")
                finally:
                    os.close(descriptor)
                if not self._restore_quarantined(
                    objects_descriptor,
                    quarantine_descriptor,
                    name,
                    original_name,
                ):
                    raise ValueError("evidence GC quarantine recovery is blocked")
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

    def _quarantine_and_remove(
        self,
        objects_descriptor: int,
        quarantine_descriptor: int,
        snapshot: _FileSnapshot,
    ) -> None:
        _before_gc_candidate_quarantine(snapshot)
        quarantine_name = self._quarantine_name(snapshot.name)
        try:
            os.stat(
                quarantine_name,
                dir_fd=quarantine_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise ValueError("evidence GC quarantine name collision")
        try:
            os.rename(
                snapshot.name,
                quarantine_name,
                src_dir_fd=objects_descriptor,
                dst_dir_fd=quarantine_descriptor,
            )
        except FileNotFoundError as error:
            raise ValueError("evidence GC plan is stale") from error
        os.fsync(objects_descriptor)
        os.fsync(quarantine_descriptor)
        _before_gc_quarantine_verify(snapshot, quarantine_name)
        descriptor: int | None = None
        verification_error: BaseException | None = None
        restorable = False
        matches = False
        try:
            descriptor = os.open(
                quarantine_name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=quarantine_descriptor,
            )
            file_stat = os.fstat(descriptor)
            restorable = stat.S_ISREG(file_stat.st_mode)
            if snapshot.sha256 is None:
                matches = (
                    restorable
                    and self._quarantined_snapshot_matches(file_stat, snapshot)
                )
            else:
                digest, size, file_stat = _descriptor_digest(descriptor)
                matches = (
                    digest == snapshot.sha256
                    and size == snapshot.size
                    and self._quarantined_snapshot_matches(file_stat, snapshot)
                )
        except (OSError, ValueError) as error:
            verification_error = error
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if not matches:
            if restorable:
                self._restore_quarantined(
                    objects_descriptor,
                    quarantine_descriptor,
                    quarantine_name,
                    snapshot.name,
                )
            if verification_error is not None:
                raise verification_error
            raise ValueError("evidence GC plan is stale")
        _before_gc_quarantine_delete(snapshot, quarantine_name)
        os.unlink(quarantine_name, dir_fd=quarantine_descriptor)
        os.fsync(quarantine_descriptor)

    def collect(
        self, plan: EvidenceGcPlan, confirm_token: str
    ) -> tuple[EvidenceObject, ...]:
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
                    for snapshot in current.object_files:
                        self._quarantine_and_remove(
                            directory_descriptor, quarantine_descriptor, snapshot
                        )
                    for snapshot in current.temporary_files:
                        self._quarantine_and_remove(
                            directory_descriptor, quarantine_descriptor, snapshot
                        )
                finally:
                    os.close(quarantine_descriptor)
            finally:
                os.close(directory_descriptor)
        return plan.objects
