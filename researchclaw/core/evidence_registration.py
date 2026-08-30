"""Recoverable registration of Stage-12 results as immutable evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from collections.abc import Mapping

from .evidence_store import EvidenceObject, EvidenceSource, EvidenceStore
from .events import EvaluationEvent, EventLog, event_log_for
from .models import ArtifactRef, ProjectState, StageStatus
from .paths import resolve_project_artifact, validate_relative_path
from .persistence import _fsync_directory, atomic_write_json
from .project import ResearchProject
from .state import StateStore
from .transactions import project_transaction


EVIDENCE_PENDING_PATH = ".researchclaw/evidence/pending-registration.json"
_PENDING_MAX_BYTES = 256 * 1024
_MANIFEST_MAX_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PHASES = frozenset(
    {"publishing", "manifest_published", "state_saved", "event_written", "aborting"}
)


@dataclass(frozen=True)
class EvidenceRegistrationStatus:
    registration_id: str
    manifest_path: str
    result_object_sha256: str
    current_stage: int
    next_action: str

    # Compatibility for the pre-immutable public result status.  Stage 13 is
    # grounded by manifest_path/result_object_sha256, not these aliases.
    @property
    def readiness(self) -> str:
        return "research_result_registered"

    @property
    def approval_eligible(self) -> bool:
        return False

    @property
    def result_path(self) -> str:
        return "experiment/results.json"

    @property
    def result_sha256(self) -> str:
        return self.result_object_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "readiness": self.readiness,
            "approval_eligible": self.approval_eligible,
            "result_path": self.result_path,
            "result_sha256": self.result_sha256,
            "current_stage": self.current_stage,
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class _ManifestSnapshot:
    artifact: ArtifactRef
    payload: Mapping[str, object]
    device: int
    inode: int
    mode: int
    mtime_ns: int
    ctime_ns: int
    directory_identities: tuple[tuple[int, int, int], ...]


def _canonical_json(value: object, *, maximum: int = _PENDING_MAX_BYTES) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("evidence_registration_interrupted") from error
    if len(payload) > maximum:
        raise ValueError("evidence_registration_interrupted")
    return payload


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _pending_path(project: ResearchProject) -> Path:
    return resolve_project_artifact(project.root, EVIDENCE_PENDING_PATH)


def _persist_pending(project: ResearchProject, pending: Mapping[str, object]) -> None:
    encoded = _canonical_json(pending)
    atomic_write_json(
        _pending_path(project),
        json.loads(encoded.decode("utf-8")),
        prefix="evidence-registration-",
        compact=True,
    )


def _clear_pending(project: ResearchProject) -> None:
    path = _pending_path(project)
    path.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if not isinstance(key, str) or key in result:
            raise ValueError("evidence_registration_interrupted")
        result[key] = value
    return result


def _reject_constant(_value: str):
    raise ValueError("evidence_registration_interrupted")


def _read_regular_bounded(path: Path, maximum: int) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        initial = os.fstat(descriptor)
        if not stat.S_ISREG(initial.st_mode) or initial.st_size > maximum:
            raise ValueError("evidence_registration_interrupted")
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        final = os.fstat(descriptor)
        if (
            len(payload) > maximum
            or len(payload) != initial.st_size
            or (
                initial.st_dev,
                initial.st_ino,
                initial.st_size,
                initial.st_mtime_ns,
                initial.st_ctime_ns,
            )
            != (
                final.st_dev,
                final.st_ino,
                final.st_size,
                final.st_mtime_ns,
                final.st_ctime_ns,
            )
        ):
            raise ValueError("evidence_registration_interrupted")
        return payload
    finally:
        os.close(descriptor)


def _decode_pending_json(payload: bytes) -> object:
    return json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )


def _validate_pending_event_schema(
    value: object, *, event_type: str, payload_fields: frozenset[str]
) -> None:
    event_fields = {"schema_version", "timestamp", "type", "project_id", "payload"}
    if (
        not isinstance(value, dict)
        or set(value) != event_fields
        or not isinstance(value.get("schema_version"), int)
        or isinstance(value.get("schema_version"), bool)
        or value.get("schema_version") != 1
        or value.get("type") != event_type
        or not isinstance(value.get("timestamp"), str)
        or not isinstance(value.get("project_id"), str)
    ):
        raise ValueError("evidence_registration_interrupted")
    payload = value.get("payload")
    if not isinstance(payload, dict) or set(payload) != payload_fields:
        raise ValueError("evidence_registration_interrupted")
    string_fields = payload_fields - {"metric_count", "input_count"}
    if any(not isinstance(payload.get(field), str) for field in string_fields):
        raise ValueError("evidence_registration_interrupted")
    for field in payload_fields & {"metric_count", "input_count"}:
        count = payload.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("evidence_registration_interrupted")


def _load_pending(project: ResearchProject) -> dict[str, object] | None:
    path = _pending_path(project)
    if not os.path.lexists(path):
        return None
    try:
        raw = _decode_pending_json(_read_regular_bounded(path, _PENDING_MAX_BYTES))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as error:
        raise ValueError("evidence_registration_interrupted") from error
    required = {
        "schema_version",
        "registration_id",
        "project_id",
        "prior_state_sha256",
        "prior_state",
        "target_state_sha256",
        "sources",
        "objects",
        "manifest_path",
        "manifest_sha256",
        "manifest",
        "event",
        "event_sha256",
        "rollback_event",
        "rollback_event_sha256",
        "rollback_offset",
        "event_offset",
        "phase",
        "abort_intent",
        "abort_error",
    }
    if (
        not isinstance(raw, dict)
        or set(raw) != required
        or not isinstance(raw.get("schema_version"), int)
        or isinstance(raw.get("schema_version"), bool)
        or raw.get("schema_version") != 1
    ):
        raise ValueError("evidence_registration_interrupted")
    if raw.get("phase") not in _PHASES or not isinstance(raw.get("abort_intent"), bool):
        raise ValueError("evidence_registration_interrupted")
    if raw.get("abort_error") is not None and raw.get("abort_error") not in {
        "evidence_object_integrity_failure",
        "evidence_registration_interrupted",
    }:
        raise ValueError("evidence_registration_interrupted")
    if raw.get("project_id") != project.state.project_id:
        raise ValueError("evidence_registration_interrupted")
    _validate_pending_event_schema(
        raw.get("event"),
        event_type="research_result_registered",
        payload_fields=frozenset(
            {
                "contract_path",
                "contract_sha256",
                "result_path",
                "result_sha256",
                "metric_count",
                "input_count",
            }
        ),
    )
    _validate_pending_event_schema(
        raw.get("rollback_event"),
        event_type="research_result_registration_rolled_back",
        payload_fields=frozenset(
            {
                "contract_path",
                "contract_sha256",
                "result_path",
                "result_sha256",
                "registration_event_sha256",
            }
        ),
    )
    for field in (
        "prior_state_sha256",
        "target_state_sha256",
        "manifest_sha256",
        "event_sha256",
        "rollback_event_sha256",
    ):
        if not isinstance(raw.get(field), str) or _SHA256.fullmatch(raw[field]) is None:
            raise ValueError("evidence_registration_interrupted")
    if (
        _hash(raw["manifest"]) != raw["manifest_sha256"]
        or _hash(raw["event"]) != raw["event_sha256"]
        or _hash(raw["rollback_event"]) != raw["rollback_event_sha256"]
        or _hash(raw["prior_state"]) != raw["prior_state_sha256"]
    ):
        raise ValueError("evidence_registration_interrupted")
    try:
        prior = ProjectState.from_dict(raw["prior_state"])
    except (TypeError, ValueError) as error:
        raise ValueError("evidence_registration_interrupted") from error
    manifest = raw["manifest"]
    if (
        prior.project_id != raw["project_id"]
        or prior.current_stage != 12
        or not isinstance(raw["registration_id"], str)
        or not isinstance(manifest, dict)
        or manifest.get("registration_id") != raw["registration_id"]
        or manifest.get("project_id") != raw["project_id"]
        or raw["manifest_path"]
        != f".researchclaw/evidence/manifests/{raw['registration_id']}.json"
    ):
        raise ValueError("evidence_registration_interrupted")
    try:
        event = EvaluationEvent.from_dict(raw["event"])
        rollback_event = EvaluationEvent.from_dict(raw["rollback_event"])
    except (TypeError, ValueError) as error:
        raise ValueError("evidence_registration_interrupted") from error
    manifest_result = manifest.get("result")
    manifest_contract = manifest.get("execution_contract")
    manifest_objects = manifest.get("objects")
    if (
        event.type != "research_result_registered"
        or event.project_id != raw["project_id"]
        or not isinstance(manifest_result, dict)
        or not isinstance(manifest_contract, dict)
        or not isinstance(manifest_objects, list)
        or event.payload
        != {
            "contract_path": manifest_contract.get("path"),
            "contract_sha256": manifest_contract.get("sha256"),
            "result_path": "experiment/results.json",
            "result_sha256": manifest_result.get("sha256"),
            "metric_count": len(manifest.get("metrics", {})),
            "input_count": sum(
                1
                for entry in manifest_objects
                if isinstance(entry, dict) and entry.get("role") == "input"
            ),
        }
        or not isinstance(raw.get("event_offset"), int)
        or isinstance(raw.get("event_offset"), bool)
        or raw["event_offset"] < 0
        or (
            raw.get("rollback_offset") is not None
            and (
                not isinstance(raw["rollback_offset"], int)
                or isinstance(raw["rollback_offset"], bool)
                or raw["rollback_offset"] < raw["event_offset"]
                or raw["phase"] != "aborting"
                or raw["abort_intent"] is not True
            )
        )
        or rollback_event.type != "research_result_registration_rolled_back"
        or rollback_event.project_id != raw["project_id"]
        or rollback_event.payload
        != {
            "contract_path": event.payload.get("contract_path"),
            "contract_sha256": event.payload.get("contract_sha256"),
            "result_path": event.payload.get("result_path"),
            "result_sha256": event.payload.get("result_sha256"),
            "registration_event_sha256": raw["event_sha256"],
        }
    ):
        raise ValueError("evidence_registration_interrupted")
    expected_sources = [
        {
            "role": entry.get("role"),
            "path": entry.get("source_path"),
            "expected_sha256": entry.get("sha256"),
            "expected_size": entry.get("size"),
        }
        for entry in manifest_objects
        if isinstance(entry, dict)
    ]
    if raw.get("sources") != expected_sources or not isinstance(
        raw.get("objects"), list
    ):
        raise ValueError("evidence_registration_interrupted")
    expected_object_identities = {
        (entry.get("sha256"), entry.get("size"))
        for entry in manifest_objects
        if isinstance(entry, dict)
    }
    for published in raw["objects"]:
        if (
            not isinstance(published, dict)
            or set(published) != {"sha256", "size", "path"}
            or (published.get("sha256"), published.get("size"))
            not in expected_object_identities
            or published.get("path")
            != f".researchclaw/evidence/objects/{published.get('sha256')}"
        ):
            raise ValueError("evidence_registration_interrupted")
    return raw


def _source_size(root: Path, path: str) -> int:
    descriptor = os.open(root / path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        value = os.fstat(descriptor)
        if not stat.S_ISREG(value.st_mode):
            raise ValueError("research_result_provenance_mismatch")
        return value.st_size
    finally:
        os.close(descriptor)


def _collect_sources(project: ResearchProject, validated) -> tuple[EvidenceSource, ...]:
    payload = validated.payload
    provenance = payload.get("provenance")
    contract_ref = payload.get("execution_contract")
    if not isinstance(provenance, Mapping) or not isinstance(contract_ref, Mapping):
        raise ValueError("research_result_provenance_mismatch")
    candidates: list[EvidenceSource] = [
        EvidenceSource(
            "result",
            validated.result_path,
            validated.result_sha256,
            validated.result_size,
        ),
        EvidenceSource(
            "execution_contract",
            str(contract_ref["path"]),
            str(contract_ref["sha256"]),
            _source_size(project.root, str(contract_ref["path"])),
        ),
    ]
    bindings = provenance.get("bindings")
    if not isinstance(bindings, Mapping):
        raise ValueError("research_result_provenance_mismatch")
    for name, item in bindings.items():
        values = item if isinstance(item, (list, tuple)) else (item,)
        for entry in values:
            if not isinstance(entry, Mapping):
                raise ValueError("research_result_provenance_mismatch")
            path = entry.get("path")
            digest = entry.get("sha256")
            if not isinstance(path, str):
                raise ValueError("research_result_provenance_mismatch")
            role = (
                "package_file"
                if name in {"package_files", "package_manifest", "config"}
                else f"binding:{name}"
            )
            candidates.append(
                EvidenceSource(
                    role, path, str(digest), _source_size(project.root, path)
                )
            )
    inputs = provenance.get("inputs")
    if not isinstance(inputs, (list, tuple)):
        raise ValueError("research_result_provenance_mismatch")
    for entry in inputs:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
            raise ValueError("research_result_provenance_mismatch")
        candidates.append(
            EvidenceSource(
                "input",
                entry["path"],
                str(entry.get("sha256")),
                entry.get("size_bytes"),
            )
        )
    unique: dict[tuple[str, str], EvidenceSource] = {}
    for candidate in candidates:
        prior = unique.get((candidate.role, candidate.path))
        if prior is not None and prior != candidate:
            raise ValueError("research_result_provenance_mismatch")
        unique[(candidate.role, candidate.path)] = candidate
    return tuple(unique.values())


def _manifest_payload(
    project: ResearchProject,
    validated,
    registration_id: str,
    sources: tuple[EvidenceSource, ...],
) -> dict[str, object]:
    contract_ref = validated.payload["execution_contract"]
    assert isinstance(contract_ref, Mapping)
    approval = project.state.artifacts.get("approvals/stage-12.json")
    approval_payload = (
        asdict(approval)
        if approval is not None
        else {
            "path": "approvals/stage-12.json",
            "sha256": hashlib.sha256(
                (project.root / "approvals/stage-12.json").read_bytes()
            ).hexdigest(),
            "size": (project.root / "approvals/stage-12.json").stat().st_size,
        }
    )
    execution_payload = json.loads(
        (project.root / str(contract_ref["path"])).read_text(encoding="utf-8")
    )
    return {
        "schema_version": 1,
        "registration_id": registration_id,
        "project_id": project.state.project_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approval": approval_payload,
        "execution_contract": dict(contract_ref),
        "environment_fingerprint": execution_payload["environment_fingerprint"],
        "objects": [
            {
                "role": source.role,
                "source_path": source.path,
                "sha256": source.expected_sha256,
                "size": source.expected_size,
                "object_path": f".researchclaw/evidence/objects/{source.expected_sha256}",
            }
            for source in sources
        ],
        "result": {
            "sha256": validated.result_sha256,
            "size": validated.result_size,
            "object_path": f".researchclaw/evidence/objects/{validated.result_sha256}",
        },
        "metrics": _thaw(validated.payload["metrics"]),
        "split_summary": _thaw(validated.payload["split_summary"]),
        "runtime": _thaw(validated.payload["runtime"]),
    }


def _after_strict_validation(_validated) -> None:
    """Test seam after strict validation and before descriptor-backed publication."""


def _after_pending_persisted(_pending) -> None:
    """Durability test seam."""


def _after_object_published(_published: EvidenceObject, _index: int) -> None:
    """Durability test seam."""


def _after_manifest_published(_manifest: ArtifactRef) -> None:
    """Durability test seam."""


def _after_state_saved() -> None:
    """Durability test seam."""


def _after_event_written() -> None:
    """Durability test seam."""


def _after_pending_cleared() -> None:
    """Durability test seam."""


def _after_abort_intent_persisted() -> None:
    """Durability test seam after abort ownership is durable."""


def _after_abort_rollback_event() -> None:
    """Durability test seam after an owned success event is neutralized."""


def _after_abort_state_restored() -> None:
    """Durability test seam after Stage 12 prior state is restored."""


def _after_manifest_snapshot(_snapshot) -> None:
    """Race-test seam after one descriptor-backed manifest snapshot."""


def _open_manifest_descriptor(
    project_root: Path, manifest_path: str
) -> tuple[int, tuple[tuple[int, int, int], ...]]:
    parts = Path(manifest_path).parts
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(Path(project_root), directory_flags)
    identities: list[tuple[int, int, int]] = []
    try:
        root_stat = os.fstat(descriptor)
        identities.append((root_stat.st_dev, root_stat.st_ino, root_stat.st_mode))
        for part in parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            child_stat = os.fstat(descriptor)
            identities.append(
                (child_stat.st_dev, child_stat.st_ino, child_stat.st_mode)
            )
        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=descriptor,
        )
        return file_descriptor, tuple(identities)
    finally:
        os.close(descriptor)


def _read_manifest_snapshot(
    project_root: Path, manifest_path: str
) -> _ManifestSnapshot:
    validate_relative_path(manifest_path, kind="evidence manifest")
    if not manifest_path.startswith(".researchclaw/evidence/manifests/"):
        raise ValueError("evidence_object_integrity_failure")
    try:
        descriptor, directory_identities = _open_manifest_descriptor(
            project_root, manifest_path
        )
        try:
            initial = os.fstat(descriptor)
            if not stat.S_ISREG(initial.st_mode) or initial.st_size > _MANIFEST_MAX_BYTES:
                raise ValueError("evidence_object_integrity_failure")
            chunks = []
            remaining = _MANIFEST_MAX_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            encoded = b"".join(chunks)
            final = os.fstat(descriptor)
            if (
                len(encoded) > _MANIFEST_MAX_BYTES
                or len(encoded) != initial.st_size
                or (
                    initial.st_dev,
                    initial.st_ino,
                    initial.st_mode,
                    initial.st_size,
                    initial.st_mtime_ns,
                    initial.st_ctime_ns,
                )
                != (
                    final.st_dev,
                    final.st_ino,
                    final.st_mode,
                    final.st_size,
                    final.st_mtime_ns,
                    final.st_ctime_ns,
                )
            ):
                raise ValueError("evidence_object_integrity_failure")
        finally:
            os.close(descriptor)
        raw = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as error:
        raise ValueError("evidence_object_integrity_failure") from error
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "registration_id",
        "project_id",
        "created_at",
        "approval",
        "execution_contract",
        "environment_fingerprint",
        "objects",
        "result",
        "metrics",
        "split_summary",
        "runtime",
    }:
        raise ValueError("evidence_object_integrity_failure")
    snapshot = _ManifestSnapshot(
        ArtifactRef(
            manifest_path, hashlib.sha256(encoded).hexdigest(), len(encoded)
        ),
        raw,
        final.st_dev,
        final.st_ino,
        final.st_mode,
        final.st_mtime_ns,
        final.st_ctime_ns,
        directory_identities,
    )
    _after_manifest_snapshot(snapshot)
    return snapshot


def _revalidate_manifest_path(project_root: Path, snapshot: _ManifestSnapshot) -> None:
    try:
        descriptor, directory_identities = _open_manifest_descriptor(
            project_root, snapshot.artifact.path
        )
        try:
            current = os.fstat(descriptor)
            if (
                current.st_size != snapshot.artifact.size
                or current.st_size > _MANIFEST_MAX_BYTES
            ):
                raise ValueError("evidence_object_integrity_failure")
            digest = hashlib.sha256()
            size = 0
            remaining = snapshot.artifact.size + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                remaining -= len(chunk)
                if size > snapshot.artifact.size:
                    raise ValueError("evidence_object_integrity_failure")
            final = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("evidence_object_integrity_failure") from error
    if (
        directory_identities != snapshot.directory_identities
        or (
            current.st_dev,
            current.st_ino,
            current.st_mode,
            current.st_mtime_ns,
            current.st_ctime_ns,
        )
        != (
            snapshot.device,
            snapshot.inode,
            snapshot.mode,
            snapshot.mtime_ns,
            snapshot.ctime_ns,
        )
        or current.st_size != snapshot.artifact.size
        or size != snapshot.artifact.size
        or digest.hexdigest() != snapshot.artifact.sha256
        or not stat.S_ISREG(current.st_mode)
        or (
            final.st_dev,
            final.st_ino,
            final.st_mode,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        )
        != (
            current.st_dev,
            current.st_ino,
            current.st_mode,
            current.st_size,
            current.st_mtime_ns,
            current.st_ctime_ns,
        )
    ):
        raise ValueError("evidence_object_integrity_failure")


def load_evidence_manifest(project_root: Path, manifest_path: str) -> dict[str, object]:
    snapshot = _read_manifest_snapshot(project_root, manifest_path)
    _revalidate_manifest_path(project_root, snapshot)
    return dict(snapshot.payload)


def _validate_manifest_bindings(
    project: ResearchProject, manifest_path: str, manifest: Mapping[str, object]
) -> None:
    registration_id = manifest.get("registration_id")
    if (
        not isinstance(manifest.get("schema_version"), int)
        or isinstance(manifest.get("schema_version"), bool)
        or manifest.get("schema_version") != 1
        or not isinstance(registration_id, str)
        or manifest_path != f".researchclaw/evidence/manifests/{registration_id}.json"
        or manifest.get("project_id") != project.state.project_id
    ):
        raise ValueError("evidence_object_integrity_failure")
    entries = manifest.get("objects")
    result = manifest.get("result")
    if not isinstance(entries, list) or not isinstance(result, Mapping):
        raise ValueError("evidence_object_integrity_failure")
    result_entries = []
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "role",
            "source_path",
            "sha256",
            "size",
            "object_path",
        }:
            raise ValueError("evidence_object_integrity_failure")
        digest = entry.get("sha256")
        size = entry.get("size")
        if (
            not isinstance(entry.get("role"), str)
            or not isinstance(entry.get("source_path"), str)
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or entry.get("object_path") != f".researchclaw/evidence/objects/{digest}"
        ):
            raise ValueError("evidence_object_integrity_failure")
        if entry["role"] == "result":
            result_entries.append(entry)
    if (
        set(result) != {"sha256", "size", "object_path"}
        or len(result_entries) != 1
        or result_entries[0]["sha256"] != result.get("sha256")
        or result_entries[0]["size"] != result.get("size")
        or result_entries[0]["object_path"] != result.get("object_path")
    ):
        raise ValueError("evidence_object_integrity_failure")


def _verify_manifest_objects(
    project: ResearchProject, manifest: Mapping[str, object]
) -> None:
    entries = manifest.get("objects")
    if not isinstance(entries, list):
        raise ValueError("evidence_object_integrity_failure")
    store = EvidenceStore(project.root)
    directory = store._open_directory(store.objects_root)
    try:
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError("evidence_object_integrity_failure")
            digest, size = entry.get("sha256"), entry.get("size")
            if not isinstance(digest, str) or not isinstance(size, int):
                raise ValueError("evidence_object_integrity_failure")
            store._verify_object(directory, digest, size)
    finally:
        os.close(directory)


def _target_state(prior: ProjectState, pending: Mapping[str, object]) -> ProjectState:
    manifest_path = str(pending["manifest_path"])
    manifest = pending["manifest"]
    assert isinstance(manifest, Mapping)
    result = manifest["result"]
    assert isinstance(result, Mapping)
    manifest_bytes = _canonical_json(manifest, maximum=_MANIFEST_MAX_BYTES)
    manifest_ref = ArtifactRef(
        manifest_path, hashlib.sha256(manifest_bytes).hexdigest(), len(manifest_bytes)
    )
    result_object_path = str(result["object_path"])
    result_ref = ArtifactRef(
        result_object_path, str(result["sha256"]), int(result["size"])
    )
    compatibility_ref = ArtifactRef(
        "experiment/results.json", str(result["sha256"]), int(result["size"])
    )
    return replace(
        prior,
        current_stage=13,
        status=StageStatus.READY,
        completed_stages=(
            *tuple(stage for stage in prior.completed_stages if stage != 12),
            12,
        ),
        next_action="prepare_stage",
        artifacts={
            **prior.artifacts,
            manifest_path: manifest_ref,
            result_object_path: result_ref,
            "experiment/results.json": compatibility_ref,
        },
        last_error=None,
    )


def _event_present(project: ResearchProject, pending: Mapping[str, object]) -> bool:
    target = pending["event"]
    return any(
        event.to_dict() == target for event in event_log_for(project.root).iter_events()
    )


def _repair_owned_partial_event(
    project: ResearchProject, pending: Mapping[str, object]
) -> None:
    event = EvaluationEvent.from_dict(pending["event"])
    _repair_owned_partial_record(
        project,
        offset=int(pending["event_offset"]),
        record=EventLog._bounded_record(event),
    )


def _repair_owned_partial_rollback(
    project: ResearchProject, pending: Mapping[str, object]
) -> None:
    offset = pending.get("rollback_offset")
    if not isinstance(offset, int) or isinstance(offset, bool):
        raise ValueError("evidence_registration_interrupted")
    rollback = EvaluationEvent.from_dict(pending["rollback_event"])
    _repair_owned_partial_record(
        project, offset=offset, record=EventLog._bounded_record(rollback)
    )


def _repair_owned_partial_record(
    project: ResearchProject, *, offset: int, record: bytes
) -> None:
    path = project.root / "evaluation/events.jsonl"
    descriptor = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        total = os.fstat(descriptor).st_size
        if total <= offset or total - offset > 64 * 1024:
            raise ValueError("evidence_registration_interrupted")
        os.lseek(descriptor, offset, os.SEEK_SET)
        fragment = os.read(descriptor, total - offset)
        if not fragment or not record.startswith(fragment):
            raise ValueError("evidence_registration_interrupted")
        os.ftruncate(descriptor, offset)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _status(pending: Mapping[str, object]) -> EvidenceRegistrationStatus:
    manifest = pending["manifest"]
    assert isinstance(manifest, Mapping) and isinstance(manifest["result"], Mapping)
    return EvidenceRegistrationStatus(
        str(pending["registration_id"]),
        str(pending["manifest_path"]),
        str(manifest["result"]["sha256"]),
        13,
        "prepare_stage",
    )


def registered_evidence_status(
    project: ResearchProject
) -> EvidenceRegistrationStatus | None:
    """Return the single verified immutable registration already grounding Stage 13."""
    if project.state.current_stage != 13 or 12 not in project.state.completed_stages:
        return None
    paths = [
        path
        for path in project.state.artifacts
        if path.startswith(".researchclaw/evidence/manifests/")
    ]
    if len(paths) != 1:
        return None
    manifest_path = paths[0]
    manifest_reference = project.state.artifacts[manifest_path]
    snapshot = _read_manifest_snapshot(project.root, manifest_path)
    if snapshot.artifact != manifest_reference:
        raise ValueError("evidence_object_integrity_failure")
    _revalidate_manifest_path(project.root, snapshot)
    manifest = snapshot.payload
    _validate_manifest_bindings(project, manifest_path, manifest)
    _verify_manifest_objects(project, manifest)
    result = manifest.get("result")
    registration_id = manifest.get("registration_id")
    if (
        not isinstance(result, Mapping)
        or not isinstance(result.get("sha256"), str)
        or not isinstance(registration_id, str)
    ):
        raise ValueError("evidence_object_integrity_failure")
    result_object_path = result.get("object_path")
    result_size = result.get("size")
    result_digest = result.get("sha256")
    if (
        not isinstance(result_object_path, str)
        or not isinstance(result_size, int)
        or project.state.artifacts.get(result_object_path)
        != ArtifactRef(result_object_path, result_digest, result_size)
        or project.state.artifacts.get("experiment/results.json")
        != ArtifactRef("experiment/results.json", result_digest, result_size)
    ):
        raise ValueError("evidence_object_integrity_failure")
    _revalidate_manifest_path(project.root, snapshot)
    return EvidenceRegistrationStatus(
        registration_id,
        manifest_path,
        result["sha256"],
        13,
        project.state.next_action,
    )


def _prior_state(pending: Mapping[str, object]) -> ProjectState:
    try:
        prior = ProjectState.from_dict(pending["prior_state"])
    except (TypeError, ValueError) as error:
        raise ValueError("evidence_registration_interrupted") from error
    if _hash(prior.to_dict()) != pending["prior_state_sha256"]:
        raise ValueError("evidence_registration_interrupted")
    return prior


def _ensure_owned_success_neutralized(
    project: ResearchProject, pending: dict[str, object]
) -> None:
    success = pending["event"]
    rollback = pending["rollback_event"]
    success_present = False
    rollback_present = False
    try:
        for event in event_log_for(project.root).iter_events():
            event_dict = event.to_dict()
            success_present = success_present or event_dict == success
            rollback_present = rollback_present or event_dict == rollback
    except ValueError:
        if pending.get("rollback_offset") is None:
            _repair_owned_partial_event(project, pending)
        else:
            _repair_owned_partial_rollback(project, pending)
        success_present = False
        rollback_present = False
        for event in event_log_for(project.root).iter_events():
            event_dict = event.to_dict()
            success_present = success_present or event_dict == success
            rollback_present = rollback_present or event_dict == rollback
    if rollback_present or not success_present:
        return
    offset = pending.get("rollback_offset")
    if offset is None:
        offset = _validated_event_log_offset(project)
        pending["rollback_offset"] = offset
        _persist_pending(project, pending)
    if not isinstance(offset, int) or isinstance(offset, bool):
        raise ValueError("evidence_registration_interrupted")
    event_log_for(project.root).append_locked(
        EvaluationEvent.from_dict(rollback), expected_offset=offset
    )
    if not any(
        event.to_dict() == rollback
        for event in event_log_for(project.root).iter_events()
    ):
        raise ValueError("evidence_registration_interrupted")


def _finish_abort(project: ResearchProject, pending: dict[str, object]) -> None:
    prior = _prior_state(pending)
    current = ResearchProject.open_readonly(project.root)
    _ensure_owned_success_neutralized(current, pending)
    _after_abort_rollback_event()
    current_hash = _hash(current.state.to_dict())
    if current_hash == pending["target_state_sha256"]:
        StateStore(current.root / ".researchclaw").save(prior)
    elif current_hash != pending["prior_state_sha256"]:
        raise ValueError("evidence_registration_interrupted")
    _after_abort_state_restored()
    _clear_pending(ResearchProject.open_readonly(current.root))


def _begin_integrity_abort(
    project: ResearchProject,
    pending: dict[str, object],
) -> None:
    pending["phase"] = "aborting"
    pending["abort_intent"] = True
    pending["abort_error"] = "evidence_object_integrity_failure"
    _persist_pending(project, pending)
    _after_abort_intent_persisted()
    _finish_abort(project, pending)


def _validated_event_log_offset(project: ResearchProject) -> int:
    try:
        for _event in event_log_for(project.root).iter_events():
            pass
        return (project.root / "evaluation/events.jsonl").stat().st_size
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError("research_result_registration_recovery_invalid") from error


def _recover_locked(
    project: ResearchProject, pending: dict[str, object]
) -> EvidenceRegistrationStatus | None:
    current = ResearchProject.open_readonly(project.root)
    manifest_path = str(pending["manifest_path"])
    manifest_exists = os.path.lexists(current.root / manifest_path)
    if pending["phase"] == "aborting" or pending["abort_intent"]:
        _finish_abort(current, pending)
        return None
    if not manifest_exists:
        if pending["phase"] == "publishing":
            pending["phase"] = "aborting"
            pending["abort_intent"] = True
            _persist_pending(current, pending)
            _finish_abort(current, pending)
            return None
        _begin_integrity_abort(current, pending)
        raise ValueError("evidence_object_integrity_failure")
    try:
        snapshot = _read_manifest_snapshot(current.root, manifest_path)
        manifest = snapshot.payload
        _validate_manifest_bindings(current, manifest_path, manifest)
        if snapshot.artifact.sha256 != pending[
            "manifest_sha256"
        ] or snapshot.artifact.size != len(
            _canonical_json(pending["manifest"], maximum=_MANIFEST_MAX_BYTES)
        ):
            raise ValueError("evidence_object_integrity_failure")
        _revalidate_manifest_path(current.root, snapshot)
        _verify_manifest_objects(current, manifest)
        _revalidate_manifest_path(current.root, snapshot)
    except ValueError as error:
        if str(error) != "evidence_object_integrity_failure":
            raise
        _begin_integrity_abort(current, pending)
        raise
    prior = _prior_state(pending)
    derived_target = _target_state(prior, pending)
    derived_manifest_ref = derived_target.artifacts.get(manifest_path)
    if (
        _hash(derived_target.to_dict()) != pending["target_state_sha256"]
        or derived_manifest_ref != snapshot.artifact
    ):
        _begin_integrity_abort(current, pending)
        raise ValueError("evidence_object_integrity_failure")
    if current.state.current_stage == 12:
        if current.state != prior:
            raise ValueError("evidence_registration_interrupted")
        StateStore(current.root / ".researchclaw").save(derived_target)
        current = ResearchProject.open_readonly(current.root)
    elif current.state != derived_target:
        _begin_integrity_abort(current, pending)
        raise ValueError("evidence_object_integrity_failure")
    try:
        event_exists = _event_present(current, pending)
    except ValueError:
        _repair_owned_partial_event(current, pending)
        event_exists = False
    if not event_exists:
        event = EvaluationEvent.from_dict(pending["event"])
        path = current.root / "evaluation/events.jsonl"
        if path.stat().st_size != pending["event_offset"]:
            raise ValueError("evidence_registration_interrupted")
        event_log_for(current.root).append_locked(
            event, expected_offset=int(pending["event_offset"])
        )
    try:
        _verify_manifest_objects(current, manifest)
        _revalidate_manifest_path(current.root, snapshot)
    except ValueError as error:
        if str(error) == "evidence_object_integrity_failure":
            _begin_integrity_abort(current, pending)
        raise
    if (
        ResearchProject.open_readonly(current.root).state != derived_target
        or not _event_present(current, pending)
    ):
        raise ValueError("evidence_registration_interrupted")
    _clear_pending(current)
    return _status(pending)


def recover_pending_evidence_registration(
    project: ResearchProject
) -> EvidenceRegistrationStatus | None:
    with project_transaction(project.root, allow_pending=True):
        current = ResearchProject.open_readonly(project.root)
        pending = _load_pending(current)
        return None if pending is None else _recover_locked(current, pending)


def register_immutable_research_evidence(
    project: ResearchProject, validated_result
) -> EvidenceRegistrationStatus:
    """Publish validated Stage-12 sources and commit manifest/state/event atomically."""
    with project_transaction(project.root, allow_pending=True):
        current = ResearchProject.open_readonly(project.root)
        existing = _load_pending(current)
        if existing is not None:
            recovered = _recover_locked(current, existing)
            if recovered is None:
                raise ValueError("evidence_registration_interrupted")
            return recovered
        if current.state.current_stage != 12:
            raise ValueError("research_result_registration_conflict")
        _after_strict_validation(validated_result)
        sources = _collect_sources(current, validated_result)
        registration_id = secrets.token_hex(16)
        manifest = _manifest_payload(
            current, validated_result, registration_id, sources
        )
        manifest_path = f".researchclaw/evidence/manifests/{registration_id}.json"
        event = EvaluationEvent.create(
            "research_result_registered",
            current.state.project_id,
            {
                "contract_path": validated_result.payload["execution_contract"]["path"],
                "contract_sha256": validated_result.payload["execution_contract"][
                    "sha256"
                ],
                "result_path": validated_result.result_path,
                "result_sha256": validated_result.result_sha256,
                "metric_count": validated_result.metric_count,
                "input_count": validated_result.input_count,
            },
        )
        rollback_event = EvaluationEvent.create(
            "research_result_registration_rolled_back",
            current.state.project_id,
            {
                "contract_path": event.payload["contract_path"],
                "contract_sha256": event.payload["contract_sha256"],
                "result_path": event.payload["result_path"],
                "result_sha256": event.payload["result_sha256"],
                "registration_event_sha256": _hash(event.to_dict()),
            },
        )
        event_offset = _validated_event_log_offset(current)
        target_stub = {
            "manifest_path": manifest_path,
            "manifest": manifest,
        }
        target = _target_state(current.state, target_stub)
        pending: dict[str, object] = {
            "schema_version": 1,
            "registration_id": registration_id,
            "project_id": current.state.project_id,
            "prior_state_sha256": _hash(current.state.to_dict()),
            "prior_state": current.state.to_dict(),
            "target_state_sha256": _hash(target.to_dict()),
            "sources": [asdict(source) for source in sources],
            "objects": [],
            "manifest_path": manifest_path,
            "manifest_sha256": _hash(manifest),
            "manifest": manifest,
            "event": event.to_dict(),
            "event_sha256": _hash(event.to_dict()),
            "rollback_event": rollback_event.to_dict(),
            "rollback_event_sha256": _hash(rollback_event.to_dict()),
            "rollback_offset": None,
            "event_offset": event_offset,
            "phase": "publishing",
            "abort_intent": False,
            "abort_error": None,
        }
        _persist_pending(current, pending)
        _after_pending_persisted(pending)
        store = EvidenceStore(current.root)
        try:
            store.preflight(sources)
            published = []
            for index, source in enumerate(sources):
                evidence_object = store.publish(source)
                published.append(asdict(evidence_object))
                pending["objects"] = published
                _persist_pending(current, pending)
                _after_object_published(evidence_object, index)
            manifest_ref = store.write_manifest(registration_id, manifest)
            pending["phase"] = "manifest_published"
            _persist_pending(current, pending)
            _after_manifest_published(manifest_ref)
        except Exception as error:
            if not os.path.lexists(current.root / manifest_path):
                pending["phase"] = "aborting"
                pending["abort_intent"] = True
                _persist_pending(current, pending)
                _finish_abort(current, pending)
                if isinstance(error, ValueError) and str(error) in {
                    "evidence source identity mismatch",
                    "evidence source changed while publishing",
                }:
                    raise ValueError("research_result_file_invalid") from error
            raise
        _verify_manifest_objects(current, manifest)
        StateStore(current.root / ".researchclaw").save(target)
        pending["phase"] = "state_saved"
        _persist_pending(current, pending)
        _after_state_saved()
        event_log_for(current.root).append_locked(
            event, expected_offset=int(pending["event_offset"])
        )
        pending["phase"] = "event_written"
        _persist_pending(current, pending)
        _after_event_written()
        _verify_manifest_objects(current, manifest)
        if _hash(
            ResearchProject.open_readonly(current.root).state.to_dict()
        ) != pending["target_state_sha256"] or not _event_present(current, pending):
            raise ValueError("evidence_registration_interrupted")
        _clear_pending(current)
        _after_pending_cleared()
        return _status(pending)
