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
import shutil
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


def _before_source_recheck(_descriptor: int) -> None:
    """Test seam after the stream and before the final source identity check."""


def _before_gc_removal() -> None:
    """Test seam immediately before GC repeats its complete dry-run scan."""


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
        size=file_stat.st_size,
        mtime_ns=file_stat.st_mtime_ns,
        ctime_ns=file_stat.st_ctime_ns,
        sha256=sha256,
    )


def _matches_snapshot(file_stat: os.stat_result, snapshot: _FileSnapshot) -> bool:
    return (
        file_stat.st_dev == snapshot.device
        and file_stat.st_ino == snapshot.inode
        and file_stat.st_mode == snapshot.mode
        and file_stat.st_size == snapshot.size
        and file_stat.st_mtime_ns == snapshot.mtime_ns
        and file_stat.st_ctime_ns == snapshot.ctime_ns
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
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for relative_parts in (
            (".researchclaw", "evidence", "objects"),
            (".researchclaw", "evidence", "manifests"),
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
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise ValueError("evidence store path is not a directory")
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
            raise ValueError("evidence object integrity check failed") from error
        try:
            observed_digest, observed_size, file_stat = _descriptor_digest(descriptor)
        except (OSError, ValueError) as error:
            raise ValueError("evidence object integrity check failed") from error
        finally:
            os.close(descriptor)
        if observed_digest != digest or observed_size != expected_size:
            raise ValueError("evidence object integrity check failed")
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
        finally:
            os.close(directory_descriptor)
        available_bytes = shutil.disk_usage(self.objects_root).free
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
                evidence_object, _snapshot_value = self._verify_object(
                    directory_descriptor,
                    source.expected_sha256,
                    source.expected_size,
                )
                return evidence_object
            finally:
                if temporary_descriptor is not None:
                    os.close(temporary_descriptor)
                if temporary_exists:
                    try:
                        os.unlink(temporary_name, dir_fd=directory_descriptor)
                        directory_changed = True
                    except FileNotFoundError:
                        pass
                if directory_changed:
                    os.fsync(directory_descriptor)
                os.close(directory_descriptor)
                os.close(source_descriptor)

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
        self,
    ) -> tuple[set[str], tuple[dict[str, object], ...]]:
        referenced: set[str] = set()
        identities: list[dict[str, object]] = []
        manifest_descriptor = self._open_directory(self.manifests_root)
        try:
            manifest_names = sorted(os.listdir(manifest_descriptor))
            if len(manifest_names) > _MAX_GC_CONTEXT_FILES:
                raise ValueError("evidence GC context file limit exceeded")
            for name in manifest_names:
                relative_path = f"{_MANIFEST_PREFIX}{name}"
                value, identity = self._read_json_file(
                    manifest_descriptor, name, relative_path
                )
                identities.append(identity)
                self._find_references(value, referenced)
        finally:
            os.close(manifest_descriptor)

        metadata_root = self.project_root / ".researchclaw"
        metadata_descriptor = self._open_directory(metadata_root)
        try:
            active_names = sorted(
                name
                for name in os.listdir(metadata_descriptor)
                if "pending" in name.lower() or "journal" in name.lower()
            )
            if len(active_names) + len(identities) > _MAX_GC_CONTEXT_FILES:
                raise ValueError("evidence GC context file limit exceeded")
            for name in active_names:
                relative_path = f".researchclaw/{name}"
                value, identity = self._read_json_file(
                    metadata_descriptor, name, relative_path
                )
                identities.append(identity)
                self._find_references(value, referenced)
        finally:
            os.close(metadata_descriptor)
        return referenced, tuple(identities)

    def _find_references(self, value: object, references: set[str]) -> None:
        if isinstance(value, dict):
            path = value.get("path")
            digest = value.get("sha256")
            size = value.get("size")
            if isinstance(path, str) and path.startswith(_OBJECT_PREFIX):
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
                references.add(f"{_OBJECT_PREFIX}{digest}")
            for item in value.values():
                self._find_references(item, references)
        elif isinstance(value, list):
            for item in value:
                self._find_references(item, references)
        elif isinstance(value, str) and value.startswith(_OBJECT_PREFIX):
            references.add(value)

    def _gc_snapshot(self) -> _GcSnapshot:
        references, context_identities = self._context_references()
        directory_descriptor = self._open_directory(self.objects_root)
        object_pairs: list[tuple[EvidenceObject, _FileSnapshot]] = []
        temporary_files: list[_FileSnapshot] = []
        try:
            names = sorted(os.listdir(directory_descriptor))
            if len(names) > _MAX_GC_ENTRIES:
                raise ValueError("evidence GC entry limit exceeded")
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
                    if relative_path not in references:
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
                    if relative_path not in references:
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
            return self._gc_snapshot().plan

    def _remove_exact(self, directory_descriptor: int, snapshot: _FileSnapshot) -> None:
        descriptor = os.open(
            snapshot.name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_descriptor,
        )
        try:
            if snapshot.sha256 is None:
                file_stat = os.fstat(descriptor)
                if not stat.S_ISREG(file_stat.st_mode) or not _matches_snapshot(
                    file_stat, snapshot
                ):
                    raise ValueError("evidence GC plan is stale")
            else:
                digest, size, file_stat = _descriptor_digest(descriptor)
                if (
                    digest != snapshot.sha256
                    or size != snapshot.size
                    or not _matches_snapshot(file_stat, snapshot)
                ):
                    raise ValueError("evidence GC plan is stale")
            current_path_stat = os.stat(
                snapshot.name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if not _matches_snapshot(current_path_stat, snapshot):
                raise ValueError("evidence GC plan is stale")
            os.unlink(snapshot.name, dir_fd=directory_descriptor)
        finally:
            os.close(descriptor)

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
            current = self._gc_snapshot()
            if current.plan != plan:
                raise ValueError("evidence GC plan is stale")
            _before_gc_removal()
            current = self._gc_snapshot()
            if current.plan != plan:
                raise ValueError("evidence GC plan is stale")
            directory_descriptor = self._open_directory(self.objects_root)
            try:
                for snapshot in current.object_files:
                    self._remove_exact(directory_descriptor, snapshot)
                for snapshot in current.temporary_files:
                    self._remove_exact(directory_descriptor, snapshot)
                if current.object_files or current.temporary_files:
                    os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        return plan.objects
